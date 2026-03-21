"""
Unit tests for control_mapping_pipeline.py

Covers:
- ControlMappingPipeline._compute_coverage:
    - zero detected controls → {}
    - single framework
    - multiple frameworks
    - framework with zero total_reqs → coverage 0.0
    - controls exceeding total_reqs → clamped to 1.0
- ControlMappingPipeline.run: integration with mock repo (no controls, with controls)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from complira_graph.ingestion.control_mapping_pipeline import ControlMappingPipeline
from complira_graph.ingestion.scan_enrichment_repository import ScanEnrichmentRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pipeline() -> tuple[ControlMappingPipeline, MagicMock]:
    db = MagicMock()
    repo = MagicMock(spec=ScanEnrichmentRepository)
    pipeline = ControlMappingPipeline(db, repo)
    return pipeline, repo


def _ctrl(key: str, framework: str = "NIST 800-53", req_id: str = "REQ_1") -> dict:
    return {
        "_key": key,
        "framework": framework,
        "req_id": req_id,
        "scan_run_id": "run1",
        "tenant_id": "t1",
    }


# ---------------------------------------------------------------------------
# _compute_coverage
# ---------------------------------------------------------------------------

class TestComputeCoverage:
    def test_zero_controls_returns_empty_dict(self):
        p, _ = _make_pipeline()
        result = p._compute_coverage([], {"NIST 800-53": 100})
        assert result == {}

    def test_single_framework_correct_ratio(self):
        p, _ = _make_pipeline()
        controls = [_ctrl("c1"), _ctrl("c2"), _ctrl("c3")]
        total_reqs = {"NIST 800-53": 10}

        result = p._compute_coverage(controls, total_reqs)

        assert "NIST 800-53" in result
        assert abs(result["NIST 800-53"] - 0.3) < 1e-9  # 3/10

    def test_multiple_frameworks(self):
        p, _ = _make_pipeline()
        controls = [
            _ctrl("c1", framework="NIST 800-53"),
            _ctrl("c2", framework="NIST 800-53"),
            _ctrl("c3", framework="ISO 27001"),
        ]
        total_reqs = {"NIST 800-53": 10, "ISO 27001": 5}

        result = p._compute_coverage(controls, total_reqs)

        assert abs(result["NIST 800-53"] - 0.2) < 1e-9  # 2/10
        assert abs(result["ISO 27001"] - 0.2) < 1e-9    # 1/5

    def test_framework_not_in_total_reqs_gives_zero(self):
        """Controls with a framework not tracked in total_reqs get coverage=0.0."""
        p, _ = _make_pipeline()
        controls = [_ctrl("c1", framework="SOC2")]
        total_reqs: dict = {}  # SOC2 not tracked

        result = p._compute_coverage(controls, total_reqs)
        assert result["SOC2"] == 0.0

    def test_controls_exceeding_total_reqs_clamped_to_1(self):
        """More detected controls than total_reqs should be clamped to 1.0."""
        p, _ = _make_pipeline()
        controls = [_ctrl(f"c{i}") for i in range(15)]  # 15 controls
        total_reqs = {"NIST 800-53": 10}

        result = p._compute_coverage(controls, total_reqs)
        assert result["NIST 800-53"] == 1.0

    def test_exactly_100_percent_coverage(self):
        p, _ = _make_pipeline()
        controls = [_ctrl(f"c{i}") for i in range(10)]
        total_reqs = {"NIST 800-53": 10}

        result = p._compute_coverage(controls, total_reqs)
        assert abs(result["NIST 800-53"] - 1.0) < 1e-9

    def test_null_framework_counted_as_unknown(self):
        """Controls with no framework field should be grouped under 'unknown'."""
        p, _ = _make_pipeline()
        ctrl_no_framework = {"_key": "c1", "req_id": "REQ_1"}  # no framework key
        controls = [ctrl_no_framework]
        total_reqs: dict = {}

        result = p._compute_coverage(controls, total_reqs)
        # Should appear under "unknown" with 0.0 coverage (no total for unknown)
        assert "unknown" in result
        assert result["unknown"] == 0.0

    def test_three_frameworks_independent_ratios(self):
        p, _ = _make_pipeline()
        controls = [
            _ctrl("c1", framework="F1"),
            _ctrl("c2", framework="F1"),
            _ctrl("c3", framework="F2"),
            _ctrl("c4", framework="F3"),
            _ctrl("c5", framework="F3"),
            _ctrl("c6", framework="F3"),
        ]
        total_reqs = {"F1": 4, "F2": 10, "F3": 6}

        result = p._compute_coverage(controls, total_reqs)

        assert abs(result["F1"] - 0.5) < 1e-9   # 2/4
        assert abs(result["F2"] - 0.1) < 1e-9   # 1/10
        assert abs(result["F3"] - 0.5) < 1e-9   # 3/6


# ---------------------------------------------------------------------------
# run() — integration with mock repo
# ---------------------------------------------------------------------------

class TestControlMappingPipelineRun:
    def test_run_no_controls_sets_mapped_with_empty_coverage(self):
        p, repo = _make_pipeline()
        repo.fetch_detected_controls_for_run.return_value = []

        p.run("run1", "t1")

        repo.update_scan_run_status.assert_called_once_with(
            "run1",
            "mapped",
            extra_fields={"coverage_by_framework": {}},
        )

    def test_run_with_controls_calls_framework_resolution(self):
        p, repo = _make_pipeline()
        controls = [_ctrl("c1")]
        repo.fetch_detected_controls_for_run.return_value = controls
        repo.aql_resolve_control_framework.return_value = [
            {"control_key": "c1", "framework": "NIST 800-53"}
        ]
        repo.aql_resolve_evidence_chains.return_value = [
            {"control_key": "c1", "chain": ["fp1", "CWE-79", "REQ_1", "c1"]}
        ]
        repo.aql_get_total_reqs_by_framework.return_value = {"NIST 800-53": 100}

        p.run("run1", "t1")

        repo.aql_resolve_control_framework.assert_called_once_with(["c1"])
        repo.aql_resolve_evidence_chains.assert_called_once_with("run1", "t1")
        repo.aql_get_total_reqs_by_framework.assert_called_once()

    def test_run_with_controls_sets_status_mapped(self):
        p, repo = _make_pipeline()
        controls = [_ctrl("c1")]
        repo.fetch_detected_controls_for_run.return_value = controls
        repo.aql_resolve_control_framework.return_value = [
            {"control_key": "c1", "framework": "NIST 800-53"}
        ]
        repo.aql_resolve_evidence_chains.return_value = []
        repo.aql_get_total_reqs_by_framework.return_value = {"NIST 800-53": 10}

        p.run("run1", "t1")

        call_args = repo.update_scan_run_status.call_args
        assert call_args[0][0] == "run1"
        assert call_args[0][1] == "mapped"
        coverage = call_args[1]["extra_fields"]["coverage_by_framework"]
        assert "NIST 800-53" in coverage

    def test_run_with_controls_bulk_updates_detected_controls(self):
        """Verify that detected_controls are updated with framework + evidence_chain."""
        p, repo = _make_pipeline()
        controls = [_ctrl("c1"), _ctrl("c2", framework="ISO 27001")]
        repo.fetch_detected_controls_for_run.return_value = controls
        repo.aql_resolve_control_framework.return_value = [
            {"control_key": "c1", "framework": "NIST 800-53"},
            {"control_key": "c2", "framework": "ISO 27001"},
        ]
        repo.aql_resolve_evidence_chains.return_value = []
        repo.aql_get_total_reqs_by_framework.return_value = {
            "NIST 800-53": 100,
            "ISO 27001": 50,
        }

        # Intercept AQL execute for the bulk update call
        p._db.aql.execute = MagicMock()

        p.run("run1", "t1")

        # The pipeline should have called db.aql.execute for the detected_controls update
        p._db.aql.execute.assert_called()

    def test_run_coverage_computation_reflected_in_status_update(self):
        p, repo = _make_pipeline()
        controls = [_ctrl("c1"), _ctrl("c2")]
        repo.fetch_detected_controls_for_run.return_value = controls
        repo.aql_resolve_control_framework.return_value = [
            {"control_key": "c1", "framework": "NIST 800-53"},
            {"control_key": "c2", "framework": "NIST 800-53"},
        ]
        repo.aql_resolve_evidence_chains.return_value = []
        repo.aql_get_total_reqs_by_framework.return_value = {"NIST 800-53": 10}

        p.run("run1", "t1")

        call_args = repo.update_scan_run_status.call_args
        coverage = call_args[1]["extra_fields"]["coverage_by_framework"]
        # 2 controls / 10 total = 0.2
        assert abs(coverage["NIST 800-53"] - 0.2) < 1e-9
