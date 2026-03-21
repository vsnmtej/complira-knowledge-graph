"""
Unit tests for compaction_pipeline.py

Covers:
- CompactionPipeline._compute_risk_score: formula correctness
- CompactionPipeline._assign_compaction_groups: CWE grouping and no-cwe fallback
- CompactionPipeline._compute_cluster_ranks: rank ordering
- CompactionPipeline._canonical_map: canonical finding selection
- CompactionPipeline._build_compaction_updates: update dict construction
- CompactionPipeline.run: integration with mock repo
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from complira_graph.ingestion.compaction_pipeline import CompactionPipeline
from complira_graph.ingestion.scan_enrichment_repository import ScanEnrichmentRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pipeline() -> tuple[CompactionPipeline, MagicMock]:
    db = MagicMock()
    repo = MagicMock(spec=ScanEnrichmentRepository)
    pipeline = CompactionPipeline(db, repo)
    return pipeline, repo


_SENTINEL = object()


def _finding(
    fingerprint: str,
    cve_id: str | None = "CVE-2024-1234",
    cvss_base: float = 7.5,
    epss_score: float = 0.1,
    in_kev: bool = False,
    d3fend_techniques: list | None = None,
    cwe_chain: object = _SENTINEL,
) -> dict:
    # Default cwe_chain to ["CWE-79"] when not specified, but allow explicit []
    resolved_cwe_chain = ["CWE-79"] if cwe_chain is _SENTINEL else cwe_chain
    return {
        "_key": fingerprint,
        "fingerprint": fingerprint,
        "cve_id": cve_id,
        "cvss_base": cvss_base,
        "epss_score": epss_score,
        "in_kev": in_kev,
        "d3fend_techniques": d3fend_techniques,
        "cwe_chain": resolved_cwe_chain,
        "tenant_id": "t1",
        "scan_run_id": "run1",
    }


# ---------------------------------------------------------------------------
# _compute_risk_score
# ---------------------------------------------------------------------------

class TestComputeRiskScore:
    def test_zero_for_no_cve(self):
        p, _ = _make_pipeline()
        f = _finding("fp1", cve_id=None)
        assert p._compute_risk_score(f) == 0.0

    def test_formula_all_components(self):
        """
        cvss_base=10 → normalized=1.0, weight=0.4 → 0.4
        epss_score=1.0, weight=0.3 → 0.3
        in_kev=True → 1.0*0.2 → 0.2
        d3fend non-empty → 0.1*0.1 → 0.01 (actually exploit_bonus is 0.1, weight 0.1 → 0.01)
        total = 0.4 + 0.3 + 0.2 + 0.01 = 0.91
        """
        p, _ = _make_pipeline()
        f = _finding(
            "fp1",
            cvss_base=10.0,
            epss_score=1.0,
            in_kev=True,
            d3fend_techniques=["D3-OTF"],
        )
        score = p._compute_risk_score(f)
        assert abs(score - 0.91) < 1e-9

    def test_formula_no_kev_no_d3fend(self):
        """
        cvss_base=5.0 → normalized=0.5 → *0.4 = 0.2
        epss_score=0.5 → *0.3 = 0.15
        in_kev=False → 0.0
        no d3fend → 0.0
        total = 0.35
        """
        p, _ = _make_pipeline()
        f = _finding("fp1", cvss_base=5.0, epss_score=0.5, in_kev=False)
        score = p._compute_risk_score(f)
        assert abs(score - 0.35) < 1e-9

    def test_score_clamped_to_one(self):
        """Score should never exceed 1.0."""
        p, _ = _make_pipeline()
        f = _finding(
            "fp1",
            cvss_base=10.0,
            epss_score=1.0,
            in_kev=True,
            d3fend_techniques=["D3-OTF"],
        )
        score = p._compute_risk_score(f)
        assert score <= 1.0

    def test_zero_cvss_zero_epss_kev_gives_0_2(self):
        """Only KEV bonus contributes."""
        p, _ = _make_pipeline()
        f = _finding("fp1", cvss_base=0.0, epss_score=0.0, in_kev=True)
        score = p._compute_risk_score(f)
        assert abs(score - 0.2) < 1e-9

    def test_zero_all_inputs(self):
        p, _ = _make_pipeline()
        f = _finding("fp1", cvss_base=0.0, epss_score=0.0, in_kev=False)
        assert p._compute_risk_score(f) == 0.0


# ---------------------------------------------------------------------------
# _assign_compaction_groups
# ---------------------------------------------------------------------------

class TestAssignCompactionGroups:
    def test_cwe_chain_uses_parent_map(self):
        p, _ = _make_pipeline()
        f = _finding("fp1", cwe_chain=["CWE-117"])
        cwe_parent_map = {"CWE_117": "CWE_116"}

        groups = p._assign_compaction_groups([f], cwe_parent_map)
        assert groups["fp1"] == "CWE_116"

    def test_cwe_without_parent_uses_self(self):
        p, _ = _make_pipeline()
        f = _finding("fp1", cwe_chain=["CWE-79"])
        cwe_parent_map = {"CWE_79": "CWE_79"}

        groups = p._assign_compaction_groups([f], cwe_parent_map)
        assert groups["fp1"] == "CWE_79"

    def test_no_cwe_chain_uses_no_cwe_prefix(self):
        p, _ = _make_pipeline()
        f = _finding("fp1", cwe_chain=[])

        groups = p._assign_compaction_groups([f], {})
        assert groups["fp1"] == "no_cwe_fp1"

    def test_multiple_findings_same_cwe_same_group(self):
        p, _ = _make_pipeline()
        f1 = _finding("fp1", cwe_chain=["CWE-79"])
        f2 = _finding("fp2", cwe_chain=["CWE-79"])
        cwe_parent_map = {"CWE_79": "CWE_79"}

        groups = p._assign_compaction_groups([f1, f2], cwe_parent_map)
        assert groups["fp1"] == groups["fp2"] == "CWE_79"

    def test_mixed_cwe_and_no_cwe(self):
        p, _ = _make_pipeline()
        f1 = _finding("fp1", cwe_chain=["CWE-79"])
        f2 = _finding("fp2", cwe_chain=[])
        cwe_parent_map = {"CWE_79": "CWE_79"}

        groups = p._assign_compaction_groups([f1, f2], cwe_parent_map)
        assert groups["fp1"] == "CWE_79"
        assert groups["fp2"] == "no_cwe_fp2"

    def test_missing_cwe_in_parent_map_falls_back_to_normalized(self):
        """If CWE not in parent_map, fall back to the normalized cwe_key."""
        p, _ = _make_pipeline()
        f = _finding("fp1", cwe_chain=["CWE-20"])
        # CWE_20 not in parent_map

        groups = p._assign_compaction_groups([f], {})
        assert groups["fp1"] == "CWE_20"


# ---------------------------------------------------------------------------
# _compute_cluster_ranks
# ---------------------------------------------------------------------------

class TestComputeClusterRanks:
    def test_single_finding_gets_rank_1(self):
        p, _ = _make_pipeline()
        f = _finding("fp1")
        group_map = {"fp1": "CWE_79"}
        risk_map = {"fp1": 0.5}

        ranks = p._compute_cluster_ranks([f], group_map, risk_map)
        assert ranks["fp1"] == 1

    def test_two_groups_higher_risk_gets_rank_1(self):
        p, _ = _make_pipeline()
        f1 = _finding("fp1", cwe_chain=["CWE-79"])
        f2 = _finding("fp2", cwe_chain=["CWE-20"])
        group_map = {"fp1": "CWE_79", "fp2": "CWE_20"}
        risk_map = {"fp1": 0.8, "fp2": 0.3}

        ranks = p._compute_cluster_ranks([f1, f2], group_map, risk_map)
        assert ranks["fp1"] == 1  # higher risk
        assert ranks["fp2"] == 2  # lower risk

    def test_all_findings_in_same_group_same_rank(self):
        p, _ = _make_pipeline()
        findings = [_finding(f"fp{i}") for i in range(5)]
        group_map = {f"fp{i}": "CWE_79" for i in range(5)}
        risk_map = {f"fp{i}": 0.5 for i in range(5)}

        ranks = p._compute_cluster_ranks(findings, group_map, risk_map)
        assert all(ranks[f"fp{i}"] == 1 for i in range(5))

    def test_tie_broken_by_group_id_alphabetically(self):
        """When two groups have equal max_risk, lower alphabetical group_id gets rank 1."""
        p, _ = _make_pipeline()
        f1 = _finding("fp1", cwe_chain=["CWE-20"])
        f2 = _finding("fp2", cwe_chain=["CWE-79"])
        group_map = {"fp1": "CWE_20", "fp2": "CWE_79"}
        risk_map = {"fp1": 0.5, "fp2": 0.5}  # equal risk

        ranks = p._compute_cluster_ranks([f1, f2], group_map, risk_map)
        # CWE_20 < CWE_79 alphabetically → CWE_20 gets rank 1
        assert ranks["fp1"] == 1
        assert ranks["fp2"] == 2

    def test_three_groups_ordered_correctly(self):
        p, _ = _make_pipeline()
        f1 = _finding("fp1")
        f2 = _finding("fp2")
        f3 = _finding("fp3")
        group_map = {"fp1": "G1", "fp2": "G2", "fp3": "G3"}
        risk_map = {"fp1": 0.3, "fp2": 0.9, "fp3": 0.6}

        ranks = p._compute_cluster_ranks([f1, f2, f3], group_map, risk_map)
        assert ranks["fp2"] == 1  # highest risk
        assert ranks["fp3"] == 2
        assert ranks["fp1"] == 3


# ---------------------------------------------------------------------------
# _canonical_map
# ---------------------------------------------------------------------------

class TestCanonicalMap:
    def test_single_finding_is_canonical(self):
        p, _ = _make_pipeline()
        f = _finding("fp1")
        group_map = {"fp1": "CWE_79"}

        canon = p._canonical_map([f], group_map)
        assert canon["fp1"] == "fp1"

    def test_alphabetically_first_is_canonical(self):
        p, _ = _make_pipeline()
        f1 = _finding("fp_b")
        f2 = _finding("fp_a")  # lexicographically first
        group_map = {"fp_a": "CWE_79", "fp_b": "CWE_79"}

        canon = p._canonical_map([f1, f2], group_map)
        assert canon["fp_a"] == "fp_a"  # canonical = self
        assert canon["fp_b"] == "fp_a"  # non-canonical points to canonical


# ---------------------------------------------------------------------------
# _build_compaction_updates
# ---------------------------------------------------------------------------

class TestBuildCompactionUpdates:
    def test_canonical_finding_compacted_false(self):
        p, _ = _make_pipeline()
        f = _finding("fp1")
        group_map = {"fp1": "CWE_79"}
        risk_map = {"fp1": 0.5}
        rank_map = {"fp1": 1}
        canon_map = {"fp1": "fp1"}

        updates = p._build_compaction_updates([f], group_map, risk_map, rank_map, canon_map)
        assert updates[0]["compacted"] is False

    def test_non_canonical_finding_compacted_true(self):
        p, _ = _make_pipeline()
        f1 = _finding("fp1")  # canonical
        f2 = _finding("fp2")  # duplicate
        group_map = {"fp1": "CWE_79", "fp2": "CWE_79"}
        risk_map = {"fp1": 0.5, "fp2": 0.3}
        rank_map = {"fp1": 1, "fp2": 1}
        canon_map = {"fp1": "fp1", "fp2": "fp1"}

        updates = p._build_compaction_updates([f1, f2], group_map, risk_map, rank_map, canon_map)
        update_by_key = {u["_key"]: u for u in updates}
        assert update_by_key["fp1"]["compacted"] is False
        assert update_by_key["fp2"]["compacted"] is True

    def test_risk_score_written(self):
        p, _ = _make_pipeline()
        f = _finding("fp1")
        group_map = {"fp1": "G1"}
        risk_map = {"fp1": 0.75}
        rank_map = {"fp1": 1}
        canon_map = {"fp1": "fp1"}

        updates = p._build_compaction_updates([f], group_map, risk_map, rank_map, canon_map)
        assert updates[0]["risk_score"] == 0.75

    def test_cluster_rank_written(self):
        p, _ = _make_pipeline()
        f = _finding("fp1")
        group_map = {"fp1": "G1"}
        risk_map = {"fp1": 0.0}
        rank_map = {"fp1": 3}
        canon_map = {"fp1": "fp1"}

        updates = p._build_compaction_updates([f], group_map, risk_map, rank_map, canon_map)
        assert updates[0]["cluster_rank"] == 3


# ---------------------------------------------------------------------------
# run() — integration with mock repo
# ---------------------------------------------------------------------------

class TestCompactionPipelineRun:
    def test_run_with_no_findings_sets_compacted(self):
        p, repo = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([])

        p.run("run1", "t1")

        repo.update_scan_run_status.assert_called_once_with("run1", "compacted")

    def test_run_calls_cwe_parent_map_with_cwe_keys(self):
        p, repo = _make_pipeline()
        findings = [_finding("fp1", cwe_chain=["CWE-79"])]
        repo.fetch_findings_for_run.return_value = iter([findings])
        repo.aql_get_cwe_parent_map.return_value = {"CWE_79": "CWE_79"}

        p.run("run1", "t1")

        repo.aql_get_cwe_parent_map.assert_called_once()
        args = repo.aql_get_cwe_parent_map.call_args[0][0]
        assert "CWE_79" in args

    def test_run_calls_bulk_update_findings(self):
        p, repo = _make_pipeline()
        findings = [_finding("fp1")]
        repo.fetch_findings_for_run.return_value = iter([findings])
        repo.aql_get_cwe_parent_map.return_value = {"CWE_79": "CWE_79"}

        p.run("run1", "t1")

        repo.bulk_update_findings.assert_called_once()

    def test_run_sets_status_compacted_at_end(self):
        p, repo = _make_pipeline()
        findings = [_finding("fp1")]
        repo.fetch_findings_for_run.return_value = iter([findings])
        repo.aql_get_cwe_parent_map.return_value = {}

        p.run("run1", "t1")

        repo.update_scan_run_status.assert_called_with("run1", "compacted")

    def test_run_no_cwe_keys_skips_cwe_parent_map_call(self):
        """If no findings have cwe_chain, aql_get_cwe_parent_map should not be called."""
        p, repo = _make_pipeline()
        findings = [_finding("fp1", cwe_chain=[])]
        repo.fetch_findings_for_run.return_value = iter([findings])

        p.run("run1", "t1")

        repo.aql_get_cwe_parent_map.assert_not_called()
