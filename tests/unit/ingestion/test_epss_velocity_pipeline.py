"""
Unit tests for epss_velocity_pipeline.py

Covers:
- run: findings with cve_id get velocity computed; findings without cve_id get zero
- run: cve_id normalization (CVE-2024-1234 → CVE_2024_1234)
- run: batch EPSS history fetch; status written
- _compute_slope: single point, two points, flat series, rising series, falling series, zero denominator
- _classify_trend: rising threshold, falling threshold, stable
- _build_velocity_updates, _build_zero_velocity_updates: field correctness
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from complira_graph.ingestion.epss_velocity_pipeline import (
    EPSSVelocityPipeline,
    _normalize_cve_key,
)
from complira_graph.ingestion.scan_enrichment_repository import ScanEnrichmentRepository


def _make_pipeline():
    db = MagicMock()
    repo = MagicMock(spec=ScanEnrichmentRepository)
    pipeline = EPSSVelocityPipeline(db, repo)
    return pipeline, repo


def _finding(key: str, cve_id: str | None = None) -> dict:
    return {"_key": key, "cve_id": cve_id}


# ---------------------------------------------------------------------------
# _normalize_cve_key
# ---------------------------------------------------------------------------

class TestNormalizeCveKey:
    def test_dashes_replaced_with_underscores(self):
        assert _normalize_cve_key("CVE-2024-1234") == "CVE_2024_1234"

    def test_no_dashes_unchanged(self):
        assert _normalize_cve_key("CVE_2024_1234") == "CVE_2024_1234"


# ---------------------------------------------------------------------------
# _compute_slope
# ---------------------------------------------------------------------------

class TestComputeSlope:
    def _slope(self, history):
        pipeline, _ = _make_pipeline()
        return pipeline._compute_slope(history)

    def test_zero_points_returns_zero(self):
        assert self._slope([]) == 0.0

    def test_one_point_returns_zero(self):
        assert self._slope([{"score": 0.5, "date": "2024-01-01"}]) == 0.0

    def test_flat_series_returns_zero(self):
        history = [{"score": 0.1, "date": f"2024-01-0{i}"} for i in range(1, 5)]
        assert self._slope(history) == pytest.approx(0.0, abs=1e-9)

    def test_rising_series_positive_slope(self):
        history = [{"score": i * 0.01, "date": f"2024-01-{i:02d}"} for i in range(1, 8)]
        slope = self._slope(history)
        assert slope > 0

    def test_falling_series_negative_slope(self):
        history = [{"score": (8 - i) * 0.01, "date": f"2024-01-{i:02d}"} for i in range(1, 8)]
        slope = self._slope(history)
        assert slope < 0

    def test_two_points_computes_slope_correctly(self):
        # x=[0,1], y=[0.1, 0.2] → slope = 0.1
        history = [
            {"score": 0.1, "date": "2024-01-01"},
            {"score": 0.2, "date": "2024-01-02"},
        ]
        slope = self._slope(history)
        assert slope == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# _classify_trend
# ---------------------------------------------------------------------------

class TestClassifyTrend:
    def _trend(self, slope):
        pipeline, _ = _make_pipeline()
        return pipeline._classify_trend(slope)

    def test_rising(self):
        # slope * 7 = 0.056 > 0.05
        assert self._trend(0.008) == "rising"

    def test_falling(self):
        # slope * 7 = -0.056 < -0.05
        assert self._trend(-0.008) == "falling"

    def test_stable_near_zero(self):
        assert self._trend(0.0) == "stable"

    def test_stable_at_upper_boundary(self):
        # slope * 7 = exactly 0.05 → not rising (strict >)
        assert self._trend(0.05 / 7) == "stable"

    def test_stable_at_lower_boundary(self):
        # slope * 7 = exactly -0.05 → not falling (strict <)
        assert self._trend(-0.05 / 7) == "stable"


# ---------------------------------------------------------------------------
# run — integration
# ---------------------------------------------------------------------------

class TestRun:
    def test_cve_findings_get_velocity_updates(self):
        pipeline, repo = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([
            [_finding("fp1", cve_id="CVE-2024-1234")]
        ])
        rising_history = [{"score": i * 0.01, "date": f"2024-01-{i:02d}"} for i in range(1, 20)]
        repo.aql_get_epss_history_batch.return_value = {"CVE_2024_1234": rising_history}

        pipeline.run("run1", "t1")

        repo.bulk_update_findings.assert_called_once()
        updates = repo.bulk_update_findings.call_args.args[0]
        assert updates[0]["_key"] == "fp1"
        assert "epss_velocity" in updates[0]
        assert "epss_trend" in updates[0]
        assert "epss_velocity_computed_at" in updates[0]

    def test_no_cve_findings_get_zero_velocity(self):
        pipeline, repo = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([
            [_finding("fp1")]  # no cve_id
        ])
        repo.aql_get_epss_history_batch.return_value = {}

        pipeline.run("run1", "t1")

        updates = repo.bulk_update_findings.call_args.args[0]
        assert updates[0]["epss_velocity"] == 0.0
        assert updates[0]["epss_trend"] == "stable"
        repo.aql_get_epss_history_batch.assert_called_once()
        # Called with empty list (no CVE keys)
        cve_keys_arg = repo.aql_get_epss_history_batch.call_args.args[0]
        assert cve_keys_arg == []

    def test_status_written_on_success(self):
        pipeline, repo = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([[]])
        repo.aql_get_epss_history_batch.return_value = {}

        pipeline.run("run1", "t1")

        repo.update_scan_run_status.assert_called_once()
        assert repo.update_scan_run_status.call_args.args[1] == "velocity_computed"

    def test_cve_key_normalized_in_batch_fetch(self):
        pipeline, repo = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([
            [_finding("fp1", cve_id="CVE-2024-1234")]
        ])
        repo.aql_get_epss_history_batch.return_value = {}

        pipeline.run("run1", "t1")

        cve_keys_arg = repo.aql_get_epss_history_batch.call_args.args[0]
        assert "CVE_2024_1234" in cve_keys_arg

    def test_empty_history_yields_zero_velocity(self):
        pipeline, repo = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([
            [_finding("fp1", cve_id="CVE-2024-1")]
        ])
        repo.aql_get_epss_history_batch.return_value = {"CVE_2024_1": []}

        pipeline.run("run1", "t1")

        updates = repo.bulk_update_findings.call_args.args[0]
        assert updates[0]["epss_velocity"] == 0.0
        assert updates[0]["epss_trend"] == "stable"


# ---------------------------------------------------------------------------
# _build_velocity_updates / _build_zero_velocity_updates
# ---------------------------------------------------------------------------

class TestBuildVelocityUpdates:
    def test_velocity_update_fields(self):
        pipeline, _ = _make_pipeline()
        updates = pipeline._build_velocity_updates(["fp1", "fp2"], 0.005, "rising")
        assert len(updates) == 2
        for u in updates:
            assert u["epss_velocity"] == 0.005
            assert u["epss_trend"] == "rising"
            assert "epss_velocity_computed_at" in u

    def test_zero_velocity_update_fields(self):
        pipeline, _ = _make_pipeline()
        updates = pipeline._build_zero_velocity_updates(["fp1"])
        assert updates[0]["epss_velocity"] == 0.0
        assert updates[0]["epss_trend"] == "stable"
        assert "epss_velocity_computed_at" in updates[0]
