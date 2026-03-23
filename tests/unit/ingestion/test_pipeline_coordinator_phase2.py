"""
Unit tests for pipeline_coordinator.py — Phase 2 extensions

Covers:
- _RETRIABLE_STATUSES includes Phase 2 statuses
- Phase 2 guard sets (_LLM_DONE, _BLAST_DONE, _VELOCITY_DONE) are correct
- run_post_ingest_pipeline: Phase 2 stages run when current_status == "mapped"
- run_post_ingest_pipeline: Phase 2 stages skipped when already done
- run_post_ingest_pipeline: LLM stage failure sets pipeline_failed and returns
- run_post_ingest_pipeline: blast radius stage failure sets pipeline_failed and returns
- run_post_ingest_pipeline: EPSS velocity failure sets pipeline_failed and returns
- run_post_ingest_pipeline: status "llm_enriched" skips LLM, runs blast+velocity
- run_post_ingest_pipeline: status "blast_radius_computed" skips LLM+blast, runs velocity
- force=True runs all Phase 2 stages regardless of current_status
- single_read_at_top: current_status is read once at top (no re-reads mid-pipeline)
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from complira_graph.ingestion.pipeline_coordinator import (
    PipelineCoordinator,
    _RETRIABLE_STATUSES,
    _LLM_DONE,
    _BLAST_DONE,
    _VELOCITY_DONE,
)


# ---------------------------------------------------------------------------
# Guard-set membership tests
# ---------------------------------------------------------------------------

class TestGuardSets:
    def test_retriable_includes_phase2_statuses(self):
        assert "mapped" in _RETRIABLE_STATUSES
        assert "llm_enriched" in _RETRIABLE_STATUSES
        assert "blast_radius_computed" in _RETRIABLE_STATUSES

    def test_retriable_includes_phase1_statuses(self):
        assert "completed" in _RETRIABLE_STATUSES
        assert "enriched" in _RETRIABLE_STATUSES
        assert "compacted" in _RETRIABLE_STATUSES
        assert "pipeline_failed" in _RETRIABLE_STATUSES
        assert "enrichment_pending" in _RETRIABLE_STATUSES

    def test_velocity_computed_not_retriable(self):
        assert "velocity_computed" not in _RETRIABLE_STATUSES

    def test_llm_done_set(self):
        assert "llm_enriched" in _LLM_DONE
        assert "blast_radius_computed" in _LLM_DONE
        assert "velocity_computed" in _LLM_DONE
        assert "mapped" not in _LLM_DONE

    def test_blast_done_set(self):
        assert "blast_radius_computed" in _BLAST_DONE
        assert "velocity_computed" in _BLAST_DONE
        assert "llm_enriched" not in _BLAST_DONE

    def test_velocity_done_set(self):
        assert "velocity_computed" in _VELOCITY_DONE
        assert "blast_radius_computed" not in _VELOCITY_DONE


# ---------------------------------------------------------------------------
# Coordinator construction helper
# ---------------------------------------------------------------------------

def _make_coordinator():
    """Build a PipelineCoordinator with all dependencies mocked."""
    with patch.multiple(
        "complira_graph.ingestion.pipeline_coordinator",
        ScanEnrichmentRepository=MagicMock(),
        EvidenceRunRepository=MagicMock(),
        EnrichmentPipeline=MagicMock(),
        CompactionPipeline=MagicMock(),
        ControlMappingPipeline=MagicMock(),
        ScanLLMEnrichmentRepository=MagicMock(),
        ScanBlastRadiusRepository=MagicMock(),
        PipelineLLMClient=MagicMock(),
        LLMEnrichmentPipeline=MagicMock(),
        BlastRadiusPipeline=MagicMock(),
        EPSSVelocityPipeline=MagicMock(),
    ):
        db = MagicMock()
        coordinator = PipelineCoordinator(db)

    return coordinator


def _setup_coordinator(status: str):
    """Return coordinator + mocked pipeline objects with configured status."""
    coordinator = _make_coordinator()
    # Make reference DB ping succeed
    coordinator._db.aql.execute.return_value = iter(["some_key"])
    coordinator._db.collection.return_value.get.return_value = {"status": status}
    return coordinator


# ---------------------------------------------------------------------------
# Phase 2 stages run from "mapped"
# ---------------------------------------------------------------------------

class TestPhase2FromMapped:
    def test_all_three_phase2_stages_run(self):
        coordinator = _setup_coordinator("mapped")

        coordinator.run_post_ingest_pipeline("run1", "t1")

        coordinator._llm_enrichment.run.assert_called_once_with("run1", "t1")
        coordinator._blast_radius.run.assert_called_once_with("run1", "t1")
        coordinator._epss_velocity.run.assert_called_once_with("run1", "t1")

    def test_phase1_stages_skipped_when_mapped(self):
        """status=mapped → enrichment/compaction/mapping already done → skipped."""
        coordinator = _setup_coordinator("mapped")

        coordinator.run_post_ingest_pipeline("run1", "t1")

        coordinator._enrichment.run.assert_not_called()
        coordinator._compaction.run.assert_not_called()
        coordinator._control_mapping.run.assert_not_called()


# ---------------------------------------------------------------------------
# Idempotency: Phase 2 stages skipped when already done
# ---------------------------------------------------------------------------

class TestPhase2IdempotencySkips:
    def test_llm_enriched_skips_llm_runs_blast_and_velocity(self):
        coordinator = _setup_coordinator("llm_enriched")

        coordinator.run_post_ingest_pipeline("run1", "t1")

        coordinator._llm_enrichment.run.assert_not_called()
        coordinator._blast_radius.run.assert_called_once()
        coordinator._epss_velocity.run.assert_called_once()

    def test_blast_radius_computed_skips_llm_and_blast_runs_velocity(self):
        coordinator = _setup_coordinator("blast_radius_computed")

        coordinator.run_post_ingest_pipeline("run1", "t1")

        coordinator._llm_enrichment.run.assert_not_called()
        coordinator._blast_radius.run.assert_not_called()
        coordinator._epss_velocity.run.assert_called_once()

    def test_velocity_computed_not_retriable_returns_immediately(self):
        coordinator = _setup_coordinator("velocity_computed")

        coordinator.run_post_ingest_pipeline("run1", "t1")

        coordinator._llm_enrichment.run.assert_not_called()
        coordinator._blast_radius.run.assert_not_called()
        coordinator._epss_velocity.run.assert_not_called()


# ---------------------------------------------------------------------------
# Force re-run
# ---------------------------------------------------------------------------

class TestForceRerun:
    def test_force_runs_all_stages_when_llm_enriched(self):
        coordinator = _setup_coordinator("llm_enriched")

        coordinator.run_post_ingest_pipeline("run1", "t1", force=True)

        coordinator._llm_enrichment.run.assert_called_once()
        coordinator._blast_radius.run.assert_called_once()
        coordinator._epss_velocity.run.assert_called_once()


# ---------------------------------------------------------------------------
# Phase 2 stage failure → pipeline_failed
# ---------------------------------------------------------------------------

class TestPhase2StageFailures:
    def test_llm_enrichment_failure_sets_pipeline_failed(self):
        coordinator = _setup_coordinator("mapped")
        coordinator._llm_enrichment.run.side_effect = RuntimeError("all_llm_batches_failed")

        coordinator.run_post_ingest_pipeline("run1", "t1")

        coordinator._repo.update_scan_run_status.assert_called_with(
            "run1",
            "pipeline_failed",
            extra_fields={"pipeline_error": "all_llm_batches_failed"},
        )
        # Downstream stages must not run
        coordinator._blast_radius.run.assert_not_called()
        coordinator._epss_velocity.run.assert_not_called()

    def test_blast_radius_failure_sets_pipeline_failed(self):
        coordinator = _setup_coordinator("mapped")
        coordinator._blast_radius.run.side_effect = Exception("blast error")

        coordinator.run_post_ingest_pipeline("run1", "t1")

        coordinator._repo.update_scan_run_status.assert_called_with(
            "run1",
            "pipeline_failed",
            extra_fields={"pipeline_error": "blast error"},
        )
        coordinator._epss_velocity.run.assert_not_called()

    def test_epss_velocity_failure_sets_pipeline_failed(self):
        coordinator = _setup_coordinator("mapped")
        coordinator._epss_velocity.run.side_effect = Exception("epss error")

        coordinator.run_post_ingest_pipeline("run1", "t1")

        coordinator._repo.update_scan_run_status.assert_called_with(
            "run1",
            "pipeline_failed",
            extra_fields={"pipeline_error": "epss error"},
        )


# ---------------------------------------------------------------------------
# Single-read-at-top: status is NOT re-read between Phase 2 stages
# ---------------------------------------------------------------------------

class TestSingleReadAtTop:
    def test_get_run_status_called_exactly_once(self):
        coordinator = _setup_coordinator("mapped")

        coordinator.run_post_ingest_pipeline("run1", "t1")

        # _get_run_status reads from db.collection("scan_runs").get()
        # The status is read once via _get_run_status; verify only one get() for scan_runs
        scan_runs_get_calls = [
            c for c in coordinator._db.collection.return_value.get.call_args_list
        ]
        assert len(scan_runs_get_calls) == 1
