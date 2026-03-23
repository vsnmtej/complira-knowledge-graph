"""
PipelineCoordinator — orchestrates all six post-ingestion pipeline stages.

Single entry point for both the BackgroundTask auto-trigger path (from the scan
ingest endpoint) and the manual trigger path (POST /v1/scans/{id}/enrich).

Stage sequence: EnrichmentPipeline → CompactionPipeline → ControlMappingPipeline
                → LLMEnrichmentPipeline → BlastRadiusPipeline → EPSSVelocityPipeline
Status chain:   completed → enriched → compacted → mapped
                → llm_enriched → blast_radius_computed → velocity_computed

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
from complira_graph.ingestion.pipeline_llm_client import PipelineLLMClient
from complira_graph.ingestion.scan_llm_enrichment_repository import ScanLLMEnrichmentRepository
from complira_graph.ingestion.scan_blast_radius_repository import ScanBlastRadiusRepository
from complira_graph.ingestion.llm_enrichment_pipeline import LLMEnrichmentPipeline
from complira_graph.ingestion.blast_radius_pipeline import BlastRadiusPipeline
from complira_graph.ingestion.epss_velocity_pipeline import EPSSVelocityPipeline
from complira_graph.ingestion.violation_mapping_pipeline import ViolationMappingPipeline
from complira_graph.ingestion.scan_violation_repository import ScanViolationRepository

log = logging.getLogger(__name__)

# Statuses that allow the full pipeline to be (re-)run from the beginning
_RETRIABLE_STATUSES = frozenset(
    {
        "completed",
        "enriched",
        "compacted",
        "pipeline_failed",
        "enrichment_pending",
        # Phase 2 — re-trigger from any intermediate Phase 2 status (AC-052)
        "mapped",
        "violations_mapped",
        "llm_enriched",
        "blast_radius_computed",
    }
)

# Statuses that allow skipping Phase 1 stages already completed
_ENRICHMENT_DONE = frozenset(
    {
        "enriched", "compacted", "mapped", "violations_mapped",
        "llm_enriched", "blast_radius_computed", "velocity_computed",
    }
)
_COMPACTION_DONE = frozenset(
    {
        "compacted", "mapped", "violations_mapped",
        "llm_enriched", "blast_radius_computed", "velocity_computed",
    }
)
_MAPPING_DONE = frozenset(
    {
        "mapped", "violations_mapped",
        "llm_enriched", "blast_radius_computed", "velocity_computed",
    }
)

# Compliance violation mapping guard set
_VIOLATION_DONE = frozenset(
    {"violations_mapped", "llm_enriched", "blast_radius_computed", "velocity_computed"}
)

# Phase 2 guard sets (single-read-at-top pattern — same as Phase 1)
_LLM_DONE      = frozenset({"llm_enriched", "blast_radius_computed", "velocity_computed"})
_BLAST_DONE    = frozenset({"blast_radius_computed", "velocity_computed"})
_VELOCITY_DONE = frozenset({"velocity_computed"})


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
        # Phase 1 stages (unchanged)
        self._enrichment = EnrichmentPipeline(db, self._repo)
        self._compaction = CompactionPipeline(db, self._repo)
        self._control_mapping = ControlMappingPipeline(db, self._repo)
        # Phase 2 repositories and client
        self._llm_repo = ScanLLMEnrichmentRepository(db)
        self._blast_repo = ScanBlastRadiusRepository(db)
        self._llm_client = PipelineLLMClient()
        # Phase 2 stages
        self._llm_enrichment = LLMEnrichmentPipeline(db, self._repo, self._llm_repo, self._llm_client)
        self._blast_radius = BlastRadiusPipeline(db, self._repo, self._blast_repo)
        self._epss_velocity = EPSSVelocityPipeline(db, self._repo)
        # Compliance violation mapping
        self._violation_repo = ScanViolationRepository(db)
        self._violation_mapping = ViolationMappingPipeline(db, self._repo, self._violation_repo)

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

        # Stage 3B: Violation Mapping (Compliance)
        if force or current_status not in _VIOLATION_DONE:
            try:
                self._violation_mapping.run(scan_run_id, tenant_id)
            except Exception as exc:
                log.exception(
                    "pipeline_coordinator.violation_mapping_failed",
                    extra={"scan_run_id": scan_run_id, "error": str(exc)},
                )
                self._mark_failed(scan_run_id, str(exc))
                return
        else:
            log.info(
                "pipeline_coordinator.violation_mapping_skipped",
                extra={"scan_run_id": scan_run_id, "status": current_status},
            )

        # Stage 4: LLM Enrichment (Phase 2)
        if force or current_status not in _LLM_DONE:
            try:
                self._llm_enrichment.run(scan_run_id, tenant_id)
            except Exception as exc:
                log.exception(
                    "pipeline_coordinator.llm_enrichment_failed",
                    extra={"scan_run_id": scan_run_id, "error": str(exc)},
                )
                self._mark_failed(scan_run_id, str(exc))
                return
        else:
            log.info(
                "pipeline_coordinator.llm_enrichment_skipped",
                extra={"scan_run_id": scan_run_id, "status": current_status},
            )

        # Stage 5: Blast Radius (Phase 2)
        if force or current_status not in _BLAST_DONE:
            try:
                self._blast_radius.run(scan_run_id, tenant_id)
            except Exception as exc:
                log.exception(
                    "pipeline_coordinator.blast_radius_failed",
                    extra={"scan_run_id": scan_run_id, "error": str(exc)},
                )
                self._mark_failed(scan_run_id, str(exc))
                return
        else:
            log.info(
                "pipeline_coordinator.blast_radius_skipped",
                extra={"scan_run_id": scan_run_id, "status": current_status},
            )

        # Stage 6: EPSS Velocity (Phase 2)
        if force or current_status not in _VELOCITY_DONE:
            try:
                self._epss_velocity.run(scan_run_id, tenant_id)
            except Exception as exc:
                log.exception(
                    "pipeline_coordinator.epss_velocity_failed",
                    extra={"scan_run_id": scan_run_id, "error": str(exc)},
                )
                self._mark_failed(scan_run_id, str(exc))
                return
        else:
            log.info(
                "pipeline_coordinator.epss_velocity_skipped",
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
