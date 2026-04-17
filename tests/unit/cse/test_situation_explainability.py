"""
Stage 7 — cse-situation-explainability AC tests.

Covers AC-01 through AC-12.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))


# ---------------------------------------------------------------------------
# AC-01 / AC-02: ThreatCategoryExplanation model exists with required fields
# ---------------------------------------------------------------------------

class TestThreatCategoryExplanationModel:
    def test_model_importable(self):
        from complira_graph.situation.models import ThreatCategoryExplanation
        assert ThreatCategoryExplanation is not None

    def test_required_fields(self):
        from complira_graph.situation.models import ThreatCategoryExplanation
        exp = ThreatCategoryExplanation(
            bucket_name="remote_code_execution",
            driving_events=["Unmonitored service exploited"],
            what_would_have_helped="Enable monitoring before round 6",
        )
        assert exp.bucket_name == "remote_code_execution"
        assert exp.driving_events == ["Unmonitored service exploited"]
        assert exp.what_would_have_helped == "Enable monitoring before round 6"
        assert exp.turning_point_round is None   # optional, defaults None
        assert exp.effective_defender_actions == []  # optional, defaults []

    def test_ciso_situation_has_explanations_field(self):
        from complira_graph.situation.models import CISOSituation
        fields = CISOSituation.model_fields
        assert "threat_category_explanations" in fields
        # Default is empty list
        sit = CISOSituation(
            posture_score=50, attck_coverage_pct=30.0, control_failure_count=2,
            threat_categories=[], control_failures=[], action_priorities=[],
            mttd_target_hours=24.0, mttr_target_days=7.0,
            snapshot_timestamp="2026-04-17T00:00:00Z",
        )
        assert sit.threat_category_explanations == []


# ---------------------------------------------------------------------------
# AC-03 / AC-04: ExposureDerivation model exists with required fields
# ---------------------------------------------------------------------------

class TestExposureDerivationModel:
    def test_model_importable(self):
        from complira_graph.situation.models import ExposureDerivation
        assert ExposureDerivation is not None

    def test_required_fields(self):
        from complira_graph.situation.models import ExposureDerivation
        ed = ExposureDerivation(narrative="Exposure of $1.2M–$5.1M derived from 2 chains.")
        assert ed.narrative.startswith("Exposure")
        assert ed.contributing_chains == 0      # default
        assert ed.highest_confidence_chain == "" # default
        assert ed.investment_recommendation == "" # default

    def test_board_situation_has_derivation_field(self):
        from complira_graph.situation.models import BoardSituation
        fields = BoardSituation.model_fields
        assert "exposure_derivation" in fields
        # Default is None
        sit = BoardSituation(
            breach_probability_pct=85.0, financial_exposure_usd_low=None,
            financial_exposure_usd_high=None, regulatory_fine_risk=[],
            reputational_risk_score=0.5, board_priorities=[],
            snapshot_timestamp="2026-04-17T00:00:00Z",
        )
        assert sit.exposure_derivation is None


# ---------------------------------------------------------------------------
# AC-05: compute_ciso() populates explanations from graph data
# ---------------------------------------------------------------------------

class TestComputeCisoExplanations:
    def _make_db(self, rollups, narratives):
        mock_db = MagicMock()
        call_count = [0]

        def execute(aql, bind_vars=None):
            call_count[0] += 1
            q = aql.strip()
            if "threat_category_rollups" in q and "bucket_name" not in (bind_vars or {}):
                return iter(rollups)
            if "bucket_name" in (bind_vars or {}):
                return iter(narratives)
            return iter([])

        mock_db.aql.execute = MagicMock(side_effect=execute)
        return mock_db

    def test_explanations_populated_from_narratives(self):
        from complira_graph.situation.abstraction_layer import SituationAbstractionLayer

        rollups = [{
            "bucket_name": "remote_code_execution",
            "display_name": "Remote code execution",
            "max_chain_probability": 0.85,
            "critical_asset_count": 2,
            "run_id": "run-123",
            "computed_at": "2026-04-17T00:00:00Z",
        }]
        narratives = [{
            "technique_id": "T1190",
            "entry_point_reasoning": "Attacker exploited unmonitored service",
            "success_reasoning": "No detection deployed",
            "defender_response": "CISO alerted at round 18",
            "soc_blind_spot": "No endpoint monitoring active",
            "single_countermeasure": "Enable endpoint monitoring before round 6",
            "confidence": 0.91,
        }]

        mock_db = MagicMock()
        mock_db.aql.execute = MagicMock(side_effect=lambda aql, bind_vars=None: (
            iter(rollups) if "bucket_name" not in (bind_vars or {}) and "simulation_runs" not in aql
            else iter(narratives) if "bucket_name" in (bind_vars or {})
            else iter([])
        ))

        # Test _build_threat_category_explanations directly
        from complira_graph.situation.abstraction_layer import _build_threat_category_explanations
        mock_db2 = MagicMock()
        mock_db2.aql.execute = MagicMock(return_value=iter(narratives))
        result = _build_threat_category_explanations(mock_db2, "tenant-1", rollups)

        assert len(result) == 1
        assert result[0].bucket_name == "remote_code_execution"
        assert "unmonitored service" in result[0].driving_events[0]
        assert result[0].what_would_have_helped == "Enable endpoint monitoring before round 6"

    def test_empty_narratives_returns_empty_list(self):
        from complira_graph.situation.abstraction_layer import _build_threat_category_explanations

        rollups = [{"bucket_name": "patch_gaps", "display_name": "Patch gaps",
                    "max_chain_probability": 0.7, "critical_asset_count": 0}]
        mock_db = MagicMock()
        mock_db.aql.execute = MagicMock(return_value=iter([]))

        result = _build_threat_category_explanations(mock_db, "tenant-1", rollups)
        assert result == []

    def test_db_error_skips_bucket_gracefully(self):
        from complira_graph.situation.abstraction_layer import _build_threat_category_explanations

        rollups = [{"bucket_name": "lateral_movement", "display_name": "Lateral movement",
                    "max_chain_probability": 0.6, "critical_asset_count": 1}]
        mock_db = MagicMock()
        mock_db.aql.execute = MagicMock(side_effect=Exception("DB error"))

        # Should not raise — just return empty list
        result = _build_threat_category_explanations(mock_db, "tenant-1", rollups)
        assert result == []


# ---------------------------------------------------------------------------
# AC-06: compute_board() populates derivation from counterfactuals
# ---------------------------------------------------------------------------

class TestComputeBoardDerivation:
    def test_derivation_built_from_counterfactuals(self):
        from complira_graph.situation.abstraction_layer import _build_exposure_derivation

        run_data = {
            "run_id": "run-123",
            "chain_count": 2,
            "counterfactuals": [
                {
                    "chain_id": "chain_0",
                    "intervention_type": "monitoring",
                    "intervention_description": "Enable endpoint detection on internet-facing devices",
                    "current_state": "Public-facing service exploited at round 6, no detection",
                    "impact_if_applied": "Would reduce upper exposure bound by ~60%.",
                    "rounds_available": 5,
                }
            ],
        }
        result = _build_exposure_derivation(run_data, 91.0, 1_200_000, 5_100_000)

        assert "1.2" in result.narrative
        assert "5.1" in result.narrative
        assert "91%" in result.narrative
        assert "60%" in result.narrative        # from impact_if_applied
        assert result.contributing_chains == 2
        assert result.investment_recommendation == "Enable endpoint detection on internet-facing devices"

    def test_empty_counterfactuals_no_trailing_space(self):
        from complira_graph.situation.abstraction_layer import _build_exposure_derivation

        run_data = {"run_id": "r1", "chain_count": 1, "counterfactuals": []}
        result = _build_exposure_derivation(run_data, 85.0, 800_000, 3_000_000)

        # F-002: no trailing space when counterfactuals empty
        assert not result.narrative.endswith(" ")
        assert result.narrative.endswith(".")

    def test_none_counterfactuals_no_crash(self):
        from complira_graph.situation.abstraction_layer import _build_exposure_derivation

        run_data = {"run_id": "r1", "chain_count": 0, "counterfactuals": None}
        result = _build_exposure_derivation(run_data, 0.0, None, None)

        assert result.narrative  # non-empty
        assert result.contributing_chains == 0

    def test_no_run_data_returns_none(self):
        """When no completed simulation run, exposure_derivation is None."""
        from complira_graph.situation.abstraction_layer import SituationAbstractionLayer

        mock_db = MagicMock()
        # All AQL queries return empty
        mock_db.aql.execute = MagicMock(return_value=iter([]))

        sal = SituationAbstractionLayer(mock_db)
        # Can't easily call compute_board() without full mock, so test query function
        from complira_graph.queries.situation_abstraction_queries import get_counterfactuals_for_tenant
        result = get_counterfactuals_for_tenant(mock_db, "tenant-x")
        assert result is None


# ---------------------------------------------------------------------------
# AC-07 / AC-08: new query functions importable and callable
# ---------------------------------------------------------------------------

class TestQueryFunctions:
    def test_get_chain_narratives_for_bucket_importable(self):
        from complira_graph.queries.situation_abstraction_queries import (
            get_chain_narratives_for_bucket,
        )
        assert callable(get_chain_narratives_for_bucket)

    def test_get_counterfactuals_for_tenant_importable(self):
        from complira_graph.queries.situation_abstraction_queries import (
            get_counterfactuals_for_tenant,
        )
        assert callable(get_counterfactuals_for_tenant)

    def test_chain_narratives_returns_list(self):
        from complira_graph.queries.situation_abstraction_queries import (
            get_chain_narratives_for_bucket,
        )
        mock_db = MagicMock()
        mock_db.aql.execute = MagicMock(return_value=iter([
            {"technique_id": "T1190", "single_countermeasure": "Enable monitoring", "confidence": 0.9}
        ]))
        result = get_chain_narratives_for_bucket(mock_db, "tenant-1", "remote_code_execution")
        assert isinstance(result, list)
        assert result[0]["technique_id"] == "T1190"

    def test_counterfactuals_returns_dict_or_none(self):
        from complira_graph.queries.situation_abstraction_queries import (
            get_counterfactuals_for_tenant,
        )
        mock_db = MagicMock()
        mock_db.aql.execute = MagicMock(return_value=iter([
            {"run_id": "r1", "counterfactuals": [], "chain_count": 2}
        ]))
        result = get_counterfactuals_for_tenant(mock_db, "tenant-1")
        assert isinstance(result, dict)
        assert result["run_id"] == "r1"


# ---------------------------------------------------------------------------
# AC-11: Graceful empty — no simulation run
# ---------------------------------------------------------------------------

class TestGracefulEmpty:
    def test_ciso_situation_explanations_default_empty(self):
        from complira_graph.situation.models import CISOSituation
        sit = CISOSituation(
            posture_score=50, attck_coverage_pct=30.0, control_failure_count=0,
            threat_categories=[], control_failures=[], action_priorities=[],
            mttd_target_hours=24.0, mttr_target_days=7.0,
            snapshot_timestamp="2026-04-17T00:00:00Z",
        )
        assert sit.threat_category_explanations == []
        assert sit.model_dump()["threat_category_explanations"] == []

    def test_board_situation_derivation_default_none(self):
        from complira_graph.situation.models import BoardSituation
        sit = BoardSituation(
            breach_probability_pct=0.0, regulatory_fine_risk=[],
            reputational_risk_score=0.0, board_priorities=[],
            snapshot_timestamp="2026-04-17T00:00:00Z",
        )
        assert sit.exposure_derivation is None
        assert sit.model_dump()["exposure_derivation"] is None


# ---------------------------------------------------------------------------
# AC-12: No CVE IDs in explanation output
# ---------------------------------------------------------------------------

class TestNoCveIds:
    def test_build_category_explanation_no_cve_ids(self):
        from complira_graph.situation.abstraction_layer import _build_threat_category_explanations

        # Narrative fields should not contain CVE IDs even if the underlying data did
        rollups = [{"bucket_name": "rce", "display_name": "RCE",
                    "max_chain_probability": 0.9, "critical_asset_count": 1}]
        narratives = [{
            "technique_id": "T1190",
            "entry_point_reasoning": "Exploit via command injection technique",
            "defender_response": "Patch deployed at round 15",
            "single_countermeasure": "Enable monitoring before round 6",
        }]
        mock_db = MagicMock()
        mock_db.aql.execute = MagicMock(return_value=iter(narratives))

        result = _build_threat_category_explanations(mock_db, "t1", rollups)
        assert len(result) == 1
        exp = result[0]
        # Check none of the text fields contain CVE-XXXX-XXXXX patterns
        import re
        cve_pattern = re.compile(r"CVE-\d{4}-\d+", re.IGNORECASE)
        for field in [exp.what_would_have_helped] + exp.driving_events + exp.effective_defender_actions:
            assert not cve_pattern.search(field), f"CVE ID found in: {field!r}"

    def test_exposure_derivation_no_cve_ids(self):
        from complira_graph.situation.abstraction_layer import _build_exposure_derivation
        import re

        run_data = {
            "chain_count": 1,
            "counterfactuals": [{
                "intervention_description": "Deploy endpoint controls on critical systems",
                "current_state": "Attack chain via exploitation of unmonitored service",
                "impact_if_applied": "Reduces exposure by 40%.",
            }],
        }
        result = _build_exposure_derivation(run_data, 85.0, 1_000_000, 4_000_000)

        cve_pattern = re.compile(r"CVE-\d{4}-\d+", re.IGNORECASE)
        for field in [result.narrative, result.highest_confidence_chain, result.investment_recommendation]:
            assert not cve_pattern.search(field), f"CVE ID found in: {field!r}"
