"""
PipelineCoordinator — orchestrates the three post-ingestion pipeline stages.

Single entry point for both the BackgroundTask auto-trigger path (from the scan
ingest endpoint) and the manual trigger path (POST /v1/scans/{id}/enrich).

Stage sequence: EnrichmentPipeline → CompactionPipeline → ControlMappingPipeline
Status chain:   completed → enriched → compacted → mapped

Error handling:
  - Reference DB unreachable: status="enrichment_pending" (retriable)
  - Any stage exception: status="pipeline_failed" (retriable)
  - Idempotent: stages already completed are skipped on re-run
"""

from __future__ import annotations

import logging

from arango.database import StandardDatabase

from complira_graph.ingestion.repositories import EvidenceRunRepository
from complira_graph.ingestion.scan_enrichment_repository import ScanEnrichmentRepository
from complira_graph.ingestion.enrichment_pipeline import EnrichmentPipeline
from complira_graph.ingestion.compaction_pipeline import CompactionPipeline
from complira_graph.ingestion.control_mapping_pipeline import ControlMappingPipeline

log = logging.getLogger(__name__)

# Statuses that allow the full pipeline to be (re-)run from the beginning
_RETRIABLE_STATUSES = frozenset(
    {
        "completed",
        "enriched",
        "compacted",
        "pipeline_failed",
        "enrichment_pending",
    }
)

# Statuses that allow skipping stages already completed
_ENRICHMENT_DONE = frozenset({"enriched", "compacted", "mapped"})
_COMPACTION_DONE = frozenset({"compacted", "mapped"})
_MAPPING_DONE = frozenset({"mapped"})


class PipelineCoordinator:
    """
    Orchestrates EnrichmentPipeline → CompactionPipeline → ControlMappingPipeline.

    Usage:
        coordinator = PipelineCoordinator(ref_db)
        coordinator.run_post_ingest_pipeline(scan_run_id, tenant_id)

    Can be called synchronously from a FastAPI BackgroundTask.
    """

    def __init__(self, db: StandardDatabase) -> None:
        self._db = db
        self._repo = ScanEnrichmentRepository(db)
        self._run_repo = EvidenceRunRepository(db)
        self._enrichment = EnrichmentPipeline(db, self._repo)
        self._compaction = CompactionPipeline(db, self._repo)
        self._control_mapping = ControlMappingPipeline(db, self._repo)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run_post_ingest_pipeline(
        self,
        scan_run_id: str,
        tenant_id: str,
        force: bool = False,
    ) -> None:
        """
        Run all three pipeline stages in order for a completed scan_run.

        Idempotency:
          - Reads current status before each stage.
          - Skips stages whose terminal status is already recorded.
          - force=True bypasses the "already done" guard (full re-run).

        Error handling:
          - Reference DB unavailable → status="enrichment_pending"
          - Stage exception → status="pipeline_failed" with error message
        """
        log.info(
            "pipeline_coordinator.start",
            extra={"scan_run_id": scan_run_id, "tenant_id": tenant_id, "force": force},
        )

        # Verify reference DB is reachable
        if not self._verify_reference_db():
            log.warning(
                "pipeline_coordinator.reference_db_unavailable",
                extra={"scan_run_id": scan_run_id},
            )
            try:
                self._repo.update_scan_run_status(
                    scan_run_id,
                    "enrichment_pending",
                    extra_fields={"pipeline_error": "reference_db_unavailable"},
                )
            except Exception:
                log.exception(
                    "pipeline_coordinator.cannot_write_enrichment_pending",
                    extra={"scan_run_id": scan_run_id},
                )
            return

        # Check current status
        current_status = self._get_run_status(scan_run_id)
        if current_status not in _RETRIABLE_STATUSES:
            log.info(
                "pipeline_coordinator.skip_non_retriable",
                extra={"scan_run_id": scan_run_id, "status": current_status},
            )
            return

        # Stage 1: Enrichment
        if force or current_status not in _ENRICHMENT_DONE:
            try:
                self._enrichment.run(scan_run_id, tenant_id)
            except Exception as exc:
                log.exception(
                    "pipeline_coordinator.enrichment_failed",
                    extra={"scan_run_id": scan_run_id, "error": str(exc)},
                )
                self._mark_failed(scan_run_id, str(exc))
                return
        else:
            log.info(
                "pipeline_coordinator.enrichment_skipped",
                extra={"scan_run_id": scan_run_id, "status": current_status},
            )

        # Stage 2: Compaction
        if force or current_status not in _COMPACTION_DONE:
            try:
                self._compaction.run(scan_run_id, tenant_id)
            except Exception as exc:
                log.exception(
                    "pipeline_coordinator.compaction_failed",
                    extra={"scan_run_id": scan_run_id, "error": str(exc)},
                )
                self._mark_failed(scan_run_id, str(exc))
                return
        else:
            log.info(
                "pipeline_coordinator.compaction_skipped",
                extra={"scan_run_id": scan_run_id, "status": current_status},
            )

        # Stage 3: Control Mapping
        if force or current_status not in _MAPPING_DONE:
            try:
                self._control_mapping.run(scan_run_id, tenant_id)
            except Exception as exc:
                log.exception(
                    "pipeline_coordinator.control_mapping_failed",
                    extra={"scan_run_id": scan_run_id, "error": str(exc)},
                )
                self._mark_failed(scan_run_id, str(exc))
                return
        else:
            log.info(
                "pipeline_coordinator.control_mapping_skipped",
                extra={"scan_run_id": scan_run_id, "status": current_status},
            )

        log.info(
            "pipeline_coordinator.complete",
            extra={"scan_run_id": scan_run_id},
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _verify_reference_db(self) -> bool:
        """
        Lightweight ping against the reference DB.

        Attempts to read one document from the vulnerabilities collection.
        Returns False if the connection or server error is raised.
        """
        try:
            col = self._db.collection("vulnerabilities")
            # Fetch any single document as a connectivity probe
            cursor = self._db.aql.execute(
                "FOR v IN vulnerabilities LIMIT 1 RETURN v._key"
            )
            list(cursor)  # consume the cursor
            return True
        except Exception:
            log.warning("pipeline_coordinator.reference_db_ping_failed")
            return False

    def _get_run_status(self, scan_run_id: str) -> str:
        """
        Fetch current scan_runs status field.

        Returns "unknown" if the document cannot be read.
        """
        try:
            doc = self._db.collection("scan_runs").get(scan_run_id)
            if doc:
                return doc.get("status", "unknown")
        except Exception:
            log.exception(
                "pipeline_coordinator.get_run_status_failed",
                extra={"scan_run_id": scan_run_id},
            )
        return "unknown"

    def _mark_failed(self, scan_run_id: str, error_message: str) -> None:
        """Set scan_run status to pipeline_failed with error message."""
        try:
            self._repo.update_scan_run_status(
                scan_run_id,
                "pipeline_failed",
                extra_fields={"pipeline_error": error_message[:2000]},
            )
        except Exception:
            log.exception(
                "pipeline_coordinator.cannot_write_pipeline_failed",
                extra={"scan_run_id": scan_run_id},
            )
