"""
ScanBlastRadiusRepository — AQL traversal and writes for blast radius simulation.

Responsibilities:
- Resolve a purl to a component vertex and traverse INBOUND depends_on edges (depth 1..5)
- Count total project components for score normalization
- Bulk-update scan_findings with blast_radius_score, affected_components, blast_radius_path,
  blast_radius_computed_at
- Update scan_run status to "blast_radius_computed"

Design contract:
- All AQL is contained here; BlastRadiusPipeline holds zero AQL
- On AQL exception, methods return safe empty/fallback values — no re-raise from query methods
- Depth cap: 1..5 hops on depends_on (prevents runaway on large graphs, Risk-1)
- Global component count used as denominator (cross-project comparability)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from arango.database import StandardDatabase

log = logging.getLogger(__name__)

_CHUNK_SIZE = 500


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class ScanBlastRadiusRepository:
    """
    AQL reads and writes for blast radius simulation.

    Injected into BlastRadiusPipeline via PipelineCoordinator.__init__.
    """

    def __init__(self, db: StandardDatabase) -> None:
        self._db = db

    def aql_blast_radius_for_purl(
        self,
        purl: str,
        depth_max: int = 5,
    ) -> dict:
        """
        Traverse INBOUND depends_on edges from the component matching purl.

        Returns dict:
          affected_purls: list[str]   — purls of all reachable dependent components
          affected_names: list[str]   — component names along longest traversal path
          max_depth:      int         — depth of the longest path found
          found:          bool        — whether purl resolved to a component vertex

        On AQL exception returns empty result (not an error — treated as no blast radius).
        """
        try:
            cursor = self._db.aql.execute(
                """
                LET start = FIRST(
                    FOR c IN components
                        FILTER c.purl == @purl
                        LIMIT 1
                        RETURN c
                )
                LET traversal = (
                    start != null
                    ? (
                        FOR v, e, p IN 1..@depth_max INBOUND start depends_on
                            RETURN DISTINCT {
                                purl:  v.purl,
                                name:  v.name,
                                depth: LENGTH(p.edges)
                            }
                    )
                    : []
                )
                LET max_depth_row = FIRST(
                    FOR row IN traversal
                        SORT row.depth DESC
                        LIMIT 1
                        RETURN row
                )
                RETURN {
                    affected_purls: traversal[*].purl,
                    affected_names: traversal[*].name,
                    max_depth:      max_depth_row != null ? max_depth_row.depth : 0,
                    found:          start != null
                }
                """,
                bind_vars={"purl": purl, "depth_max": depth_max},
            )
            rows = list(cursor)
            if rows:
                row = rows[0]
                return {
                    "affected_purls": row.get("affected_purls") or [],
                    "affected_names": row.get("affected_names") or [],
                    "max_depth": row.get("max_depth") or 0,
                    "found": bool(row.get("found")),
                }
        except Exception:
            log.exception(
                "scan_blast_radius_repo.aql_blast_radius_for_purl_failed",
                extra={"purl": purl},
            )
        return {"affected_purls": [], "affected_names": [], "max_depth": 0, "found": False}

    def aql_total_project_components(
        self,
        project_id: Optional[str] = None,
    ) -> int:
        """
        Count total components for blast radius score normalization.

        If project_id is provided, counts components used by that project via
        project_uses_component edges. Otherwise counts all components reachable
        via any project_uses_component edge (global denominator).

        On exception returns 1 to prevent division by zero.
        """
        try:
            if project_id:
                cursor = self._db.aql.execute(
                    """
                    RETURN LENGTH(
                        FOR e IN project_uses_component
                            FILTER e._from == CONCAT("projects/", @project_id)
                            RETURN 1
                    )
                    """,
                    bind_vars={"project_id": project_id},
                )
            else:
                cursor = self._db.aql.execute(
                    """
                    RETURN LENGTH(
                        FOR c IN components
                            FILTER LENGTH(
                                FOR e IN 1..1 INBOUND c project_uses_component
                                    LIMIT 1 RETURN 1
                            ) > 0
                            RETURN 1
                    )
                    """
                )
            rows = list(cursor)
            if rows and rows[0] is not None:
                return int(rows[0])
        except Exception:
            log.exception(
                "scan_blast_radius_repo.aql_total_project_components_failed",
                extra={"project_id": project_id},
            )
        return 1

    def bulk_write_blast_radius(self, updates: list[dict]) -> None:
        """
        Bulk-update scan_findings with blast radius fields.

        Each dict must have '_key' plus:
        blast_radius_score, affected_components, blast_radius_path, blast_radius_computed_at.

        Chunks at 500; OPTIONS {keepNull: false}.
        """
        if not updates:
            return
        total = 0
        chunks = 0
        for i in range(0, len(updates), _CHUNK_SIZE):
            chunk = updates[i : i + _CHUNK_SIZE]
            self._db.aql.execute(
                """
                FOR u IN @updates
                    UPDATE u._key WITH u IN scan_findings
                    OPTIONS {keepNull: false}
                """,
                bind_vars={"updates": chunk},
            )
            total += len(chunk)
            chunks += 1
        log.info(
            "scan_blast_radius_repo.bulk_write_blast_radius",
            extra={"total": total, "chunks": chunks},
        )

    def update_scan_run_status(
        self,
        scan_run_key: str,
        status: str,
        extra_fields: Optional[dict] = None,
    ) -> None:
        """Update scan_runs status plus optional extra fields."""
        payload: dict = {"_key": scan_run_key, "status": status, "updated_at": _utcnow()}
        if extra_fields:
            payload.update(extra_fields)
        self._db.collection("scan_runs").update(payload)
        log.info(
            "scan_blast_radius_repo.update_scan_run_status",
            extra={"scan_run_id": scan_run_key, "status": status},
        )
