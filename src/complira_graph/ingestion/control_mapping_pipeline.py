"""
ControlMappingPipeline — UC-009 Compliance Coverage Computation.

Reads detected_controls for the scan run, resolves each to its regulatory
framework, builds evidence chains, computes per-framework coverage ratios,
and writes coverage_by_framework back to the scan_run document.

Status transition: compacted → mapped
"""

from __future__ import annotations

import logging

from arango.database import StandardDatabase

from complira_graph.ingestion.scan_enrichment_repository import ScanEnrichmentRepository

log = logging.getLogger(__name__)


class ControlMappingPipeline:
    """
    UC-009 Control Mapping pipeline stage.

    Resolves detected_controls to frameworks and computes coverage percentages.
    Zero AQL in this class.
    """

    def __init__(self, db: StandardDatabase, repo: ScanEnrichmentRepository) -> None:
        self._db = db
        self._repo = repo

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self, scan_run_id: str, tenant_id: str) -> None:
        """
        Entry point for UC-009.

        Full call sequence:
          1. Fetch detected_controls for scan run
          2. aql_resolve_control_framework(control_keys) → framework_map
          3. aql_resolve_evidence_chains(scan_run_id, tenant_id) → evidence_chains
          4. Build control updates with framework + evidence_chain + control_status
          5. bulk_update_detected_controls
          6. aql_get_total_reqs_by_framework → total_reqs_by_framework
          7. _compute_coverage → coverage_by_framework
          8. Update scan_run: coverage_by_framework + status="mapped"
        """
        log.info(
            "control_mapping_pipeline.start",
            extra={"scan_run_id": scan_run_id, "tenant_id": tenant_id},
        )

        controls = self._repo.fetch_detected_controls_for_run(scan_run_id, tenant_id)
        if not controls:
            log.info(
                "control_mapping_pipeline.no_controls",
                extra={"scan_run_id": scan_run_id},
            )
            self._repo.update_scan_run_status(
                scan_run_id,
                "mapped",
                extra_fields={"coverage_by_framework": {}},
            )
            return

        control_keys = [c["_key"] for c in controls if c.get("_key")]

        # Resolve each control to its framework
        framework_rows = self._repo.aql_resolve_control_framework(control_keys)
        framework_map: dict[str, str] = {
            r["control_key"]: r.get("framework") or "unknown"
            for r in framework_rows
        }

        # Resolve evidence chains
        chain_rows = self._repo.aql_resolve_evidence_chains(scan_run_id, tenant_id)
        chain_map: dict[str, list[str]] = {
            r["control_key"]: r.get("chain") or []
            for r in chain_rows
        }

        # Build updates for detected_controls
        updates = []
        for ctrl in controls:
            ctrl_key = ctrl.get("_key", "")
            framework = framework_map.get(ctrl_key, "unknown")
            evidence_chain = chain_map.get(ctrl_key, [])
            updates.append(
                {
                    "_key": ctrl_key,
                    "framework": framework,
                    "evidence_chain": evidence_chain,
                    "control_status": "present",
                }
            )

        if updates:
            self._bulk_update_detected_controls(updates)

        # Compute coverage
        total_reqs_by_framework = self._repo.aql_get_total_reqs_by_framework()
        coverage_by_framework = self._compute_coverage(controls, total_reqs_by_framework)

        self._repo.update_scan_run_status(
            scan_run_id,
            "mapped",
            extra_fields={"coverage_by_framework": coverage_by_framework},
        )
        log.info(
            "control_mapping_pipeline.complete",
            extra={
                "scan_run_id": scan_run_id,
                "controls": len(controls),
                "frameworks": list(coverage_by_framework.keys()),
            },
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_coverage(
        self,
        detected_controls: list[dict],
        total_reqs_by_framework: dict[str, int],
    ) -> dict[str, float]:
        """
        Compute per-framework coverage ratio.

        coverage = detected_controls_for_framework / total_requirements_in_framework

        Controls without a resolvable framework are counted under "unknown".
        Returns {framework -> ratio} where 0.0 <= ratio <= 1.0.
        Zero-control or zero-total edge cases return 0.0.
        """
        if not detected_controls:
            return {}

        # Count detected controls per framework
        detected_counts: dict[str, int] = {}
        for ctrl in detected_controls:
            framework = ctrl.get("framework") or "unknown"
            detected_counts[framework] = detected_counts.get(framework, 0) + 1

        coverage: dict[str, float] = {}
        for framework, detected in detected_counts.items():
            total = total_reqs_by_framework.get(framework, 0)
            if total > 0:
                coverage[framework] = min(1.0, detected / total)
            else:
                coverage[framework] = 0.0
        return coverage

    def _bulk_update_detected_controls(self, updates: list[dict]) -> None:
        """
        Bulk-update detected_controls documents by _key.

        Chunks at 500 per AQL call.
        """
        _CHUNK_SIZE = 500
        if not updates:
            return
        for i in range(0, len(updates), _CHUNK_SIZE):
            chunk = updates[i : i + _CHUNK_SIZE]
            self._db.aql.execute(
                """
                FOR update IN @updates
                    UPDATE update._key WITH update IN detected_controls
                    OPTIONS {keepNull: false}
                """,
                bind_vars={"updates": chunk},
            )
        log.info(
            "control_mapping_pipeline.bulk_update_detected_controls",
            extra={"count": len(updates)},
        )
