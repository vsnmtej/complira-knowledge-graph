"""
BlastRadiusPipeline — UC-011 Blast Radius Simulation stage.

For each scan_findings document with a non-null purl, traverses the INBOUND
depends_on dependency graph to compute how widely the vulnerable component's
impact propagates.

Deduplicates by purl before issuing AQL traversals: N findings sharing the same
purl result in exactly 1 AQL round-trip, not N.

Writes per-finding:
  - blast_radius_score       ∈ [0.0, 1.0]
  - affected_components      list of purls of all reachable dependent components
  - blast_radius_path        list of component names along longest traversal path
  - blast_radius_computed_at ISO 8601 UTC timestamp

Findings with no purl (SAST/IaC) receive score=0.0 and empty lists.

Status transition: llm_enriched → blast_radius_computed
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from arango.database import StandardDatabase

from complira_graph.ingestion.scan_blast_radius_repository import ScanBlastRadiusRepository
from complira_graph.ingestion.scan_enrichment_repository import ScanEnrichmentRepository

log = logging.getLogger(__name__)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class BlastRadiusPipeline:
    """
    UC-011: Blast radius simulation stage.

    Reads findings via ScanEnrichmentRepository, runs graph traversal via
    ScanBlastRadiusRepository, writes results back via ScanBlastRadiusRepository.
    Holds zero AQL directly.
    """

    def __init__(
        self,
        db: StandardDatabase,
        repo: ScanEnrichmentRepository,
        blast_repo: ScanBlastRadiusRepository,
    ) -> None:
        self._db = db
        self._repo = repo
        self._blast_repo = blast_repo

    def run(self, scan_run_id: str, tenant_id: str) -> None:
        """
        Compute blast radius for all findings in scan_run_id.

        Trigger: scan_run.status == "llm_enriched"
        Result:  scan_run.status = "blast_radius_computed" on success
        """
        log.info(
            "blast_radius_pipeline.start",
            extra={"scan_run_id": scan_run_id, "tenant_id": tenant_id},
        )

        # Accumulate all findings and group by purl
        purl_to_fingerprints: dict[str, list[str]] = {}
        no_purl_fingerprints: list[str] = []

        for batch in self._repo.fetch_findings_for_run(scan_run_id, tenant_id):
            for finding in batch:
                purl = finding.get("purl") or ""
                if purl:
                    purl_to_fingerprints.setdefault(purl, []).append(finding["_key"])
                else:
                    no_purl_fingerprints.append(finding["_key"])

        total_components = self._blast_repo.aql_total_project_components()
        all_updates: list[dict] = []

        for purl, fingerprints in purl_to_fingerprints.items():
            traversal = self._blast_repo.aql_blast_radius_for_purl(purl)
            score = min(
                1.0,
                len(traversal["affected_purls"]) / max(total_components, 1),
            )
            all_updates.extend(
                self._build_blast_updates_for_purl(fingerprints, traversal, score)
            )

        all_updates.extend(self._build_zero_blast_updates(no_purl_fingerprints))

        self._blast_repo.bulk_write_blast_radius(all_updates)
        self._blast_repo.update_scan_run_status(
            scan_run_id,
            "blast_radius_computed",
            extra_fields={"blast_radius_computed_at": _utcnow()},
        )
        log.info(
            "blast_radius_pipeline.complete",
            extra={
                "scan_run_id": scan_run_id,
                "unique_purls": len(purl_to_fingerprints),
                "no_purl_count": len(no_purl_fingerprints),
                "total_updates": len(all_updates),
            },
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_blast_updates_for_purl(
        self,
        fingerprints: list[str],
        traversal_result: dict,
        score: float,
    ) -> list[dict]:
        now = _utcnow()
        return [
            {
                "_key": fp,
                "blast_radius_score": score,
                "affected_components": traversal_result["affected_purls"],
                "blast_radius_path": traversal_result["affected_names"],
                "blast_radius_computed_at": now,
            }
            for fp in fingerprints
        ]

    def _build_zero_blast_updates(self, fingerprints: list[str]) -> list[dict]:
        now = _utcnow()
        return [
            {
                "_key": fp,
                "blast_radius_score": 0.0,
                "affected_components": [],
                "blast_radius_path": [],
                "blast_radius_computed_at": now,
            }
            for fp in fingerprints
        ]
