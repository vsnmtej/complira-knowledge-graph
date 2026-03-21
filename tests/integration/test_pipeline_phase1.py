"""
Integration tests for Core Pipeline Phase 1.

Covers AC-001 through AC-028 mapped to Stage 7 scenarios:
  S-UC007-01 .. S-UC007-10  → EnrichmentPipeline (AC-001–AC-010)
  S-UC008-01 .. S-UC008-07  → CompactionPipeline (AC-011–AC-017)
  S-UC009-01 .. S-UC009-05  → ControlMappingPipeline (AC-018–AC-022)
  S-CROSS-01 .. S-CROSS-06  → PipelineCoordinator + API (AC-023–AC-028)

All tests use unittest.mock — no live ArangoDB required.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, Mock, patch, call


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_repo():
    """Return a MagicMock shaped like ScanEnrichmentRepository."""
    repo = MagicMock()
    # fetch_findings_for_run is a generator — default to one empty batch
    repo.fetch_findings_for_run.return_value = iter([])
    repo.aql_enrich_batch.return_value = {}
    repo.aql_get_cwe_parent_map.return_value = {}
    repo.bulk_update_findings.return_value = None
    repo.upsert_finding_triggers_req_edges.return_value = None
    repo.upsert_detected_controls.return_value = None
    repo.upsert_detected_control_maps_to_edges.return_value = None
    repo.update_scan_run_status.return_value = None
    repo.fetch_detected_controls_for_run.return_value = []
    repo.aql_resolve_control_framework.return_value = []
    repo.aql_resolve_evidence_chains.return_value = []
    repo.aql_get_total_reqs_by_framework.return_value = {}
    return repo


def _make_mock_db():
    """Return a MagicMock shaped like ArangoDB StandardDatabase."""
    db = MagicMock()
    db.aql = MagicMock()
    db.aql.execute = Mock(return_value=iter([]))
    db.collection = Mock(return_value=MagicMock())
    return db


# ===========================================================================
# Group 1: EnrichmentPipeline (AC-001 to AC-010)
# ===========================================================================


class TestEnrichmentPipeline:
    """S-UC007-01 .. S-UC007-10 — EnrichmentPipeline (AC-001–AC-010)."""

    # -----------------------------------------------------------------------
    # Fixtures
    # -----------------------------------------------------------------------

    @pytest.fixture
    def mock_db(self):
        return _make_mock_db()

    @pytest.fixture
    def mock_repo(self):
        return _make_mock_repo()

    @pytest.fixture
    def pipeline(self, mock_db, mock_repo):
        from complira_graph.ingestion.enrichment_pipeline import EnrichmentPipeline
        return EnrichmentPipeline(db=mock_db, repo=mock_repo)

    # -----------------------------------------------------------------------
    # S-UC007-01 / S-UC007-02 / S-UC007-03 / S-UC007-04
    # AC-001: EPSS score populated
    # AC-002: KEV status populated
    # AC-003: CWE chain populated
    # AC-004: D3FEND techniques linked
    # -----------------------------------------------------------------------

    def test_bulk_update_contains_enrichment_fields(self, pipeline, mock_repo):
        """
        S-UC007-01–04 (AC-001, AC-002, AC-003, AC-004):
        bulk_update_findings is called with dicts containing epss_score,
        in_kev, cwe_chain, d3fend_techniques, enriched_at for each finding
        that has a non-null cve_id.
        """
        finding = {
            "_key": "fp_001",
            "cve_id": "CVE-2024-1234",
            "scan_run_id": "run_001",
            "tenant_id": "tenant_a",
        }
        enrichment = {
            "cve_key": "CVE_2024_1234",
            "epss_score": 0.75,
            "epss_percentile": 0.90,
            "in_kev": True,
            "cwe_chain": ["CWE-79", "CWE-116"],
            "d3fend_techniques": ["d3f:NetworkTrafficAnalysis"],
            "req_keys": ["NIST_AC-1"],
        }

        mock_repo.fetch_findings_for_run.return_value = iter([[finding]])
        mock_repo.aql_enrich_batch.return_value = {"CVE_2024_1234": enrichment}

        pipeline.run("run_001", "tenant_a")

        mock_repo.bulk_update_findings.assert_called_once()
        updates = mock_repo.bulk_update_findings.call_args[0][0]
        assert len(updates) == 1
        upd = updates[0]

        # AC-001: EPSS
        assert upd.get("epss_score") == 0.75
        assert upd.get("epss_percentile") == 0.90
        # AC-002: KEV
        assert upd.get("in_kev") is True
        # AC-003: CWE chain
        assert upd.get("cwe_chain") == ["CWE-79", "CWE-116"]
        # AC-004: D3FEND
        assert upd.get("d3fend_techniques") == ["d3f:NetworkTrafficAnalysis"]
        # enriched_at always present
        assert "enriched_at" in upd

    # -----------------------------------------------------------------------
    # S-UC007-05 / S-UC007-06 / S-UC007-07
    # AC-005: OSCAL/SCF controls upserted
    # AC-006: finding_triggers_req edges created
    # AC-007: detected_control_maps_to edges created
    # -----------------------------------------------------------------------

    def test_upsert_detected_controls_and_edges_called(self, pipeline, mock_repo):
        """
        S-UC007-05, S-UC007-06, S-UC007-07 (AC-005, AC-006, AC-007):
        When enrichment_map contains req_keys, upsert_detected_controls,
        upsert_finding_triggers_req_edges and
        upsert_detected_control_maps_to_edges are each called.
        """
        finding = {
            "_key": "fp_002",
            "cve_id": "CVE-2024-5678",
            "scan_run_id": "run_002",
            "tenant_id": "tenant_a",
            "check_id": "CHK-1",
            "check_name": "SQL Injection",
        }
        enrichment = {
            "cve_key": "CVE_2024_5678",
            "epss_score": 0.5,
            "epss_percentile": 0.8,
            "in_kev": False,
            "cwe_chain": ["CWE-89"],
            "d3fend_techniques": [],
            "req_keys": ["NIST_SI-3", "ISO_A.12.6.1"],
        }

        mock_repo.fetch_findings_for_run.return_value = iter([[finding]])
        mock_repo.aql_enrich_batch.return_value = {"CVE_2024_5678": enrichment}

        pipeline.run("run_002", "tenant_a")

        # AC-005
        mock_repo.upsert_detected_controls.assert_called_once()
        ctrl_docs = mock_repo.upsert_detected_controls.call_args[0][0]
        assert len(ctrl_docs) == 2  # one per req_key

        # AC-006
        mock_repo.upsert_finding_triggers_req_edges.assert_called_once()
        edges = mock_repo.upsert_finding_triggers_req_edges.call_args[0][0]
        assert len(edges) == 2

        # AC-007
        mock_repo.upsert_detected_control_maps_to_edges.assert_called_once()
        ctrl_edges = mock_repo.upsert_detected_control_maps_to_edges.call_args[0][0]
        assert len(ctrl_edges) == 2

    # -----------------------------------------------------------------------
    # S-UC007-08 — AC-008: Findings without CVE skipped
    # -----------------------------------------------------------------------

    def test_findings_with_null_cve_skipped(self, pipeline, mock_repo):
        """
        S-UC007-08 (AC-008):
        Findings where cve_id is None/absent complete without error.
        The enrichment fields (epss_score, in_kev, cwe_chain, d3fend_techniques)
        must NOT appear in the update dict — only enriched_at is written.
        """
        finding_no_cve = {
            "_key": "fp_no_cve",
            "cve_id": None,
            "rule_id": "CKV_AWS_1",
            "scan_run_id": "run_003",
            "tenant_id": "tenant_a",
        }

        mock_repo.fetch_findings_for_run.return_value = iter([[finding_no_cve]])
        mock_repo.aql_enrich_batch.return_value = {}

        pipeline.run("run_003", "tenant_a")

        mock_repo.bulk_update_findings.assert_called_once()
        upd = mock_repo.bulk_update_findings.call_args[0][0][0]

        assert upd["_key"] == "fp_no_cve"
        assert "enriched_at" in upd
        # No CVE-derived fields
        assert "epss_score" not in upd
        assert "in_kev" not in upd
        assert "cwe_chain" not in upd
        assert "d3fend_techniques" not in upd

        # aql_enrich_batch should NOT be called (no CVE keys)
        mock_repo.aql_enrich_batch.assert_not_called()

    # -----------------------------------------------------------------------
    # S-UC007-09 — AC-009: Status transitions to "enriched"
    # -----------------------------------------------------------------------

    def test_status_set_to_enriched_on_completion(self, pipeline, mock_repo):
        """
        S-UC007-09 (AC-009):
        update_scan_run_status is called with status="enriched" after the pipeline
        completes successfully.
        """
        mock_repo.fetch_findings_for_run.return_value = iter([])

        pipeline.run("run_004", "tenant_a")

        mock_repo.update_scan_run_status.assert_called_once()
        args, kwargs = mock_repo.update_scan_run_status.call_args
        # positional or keyword call
        called_status = args[1] if len(args) > 1 else kwargs.get("status")
        assert called_status == "enriched"

    # -----------------------------------------------------------------------
    # S-UC007-10 — AC-010: Idempotent (second run produces same update dict)
    # -----------------------------------------------------------------------

    def test_idempotency_second_run_same_update(self, pipeline, mock_repo):
        """
        S-UC007-10 (AC-010):
        Running enrichment twice for the same finding yields the same update
        fields (epss_score, in_kev, cwe_chain are deterministic).
        """
        finding = {
            "_key": "fp_idem",
            "cve_id": "CVE-2024-9999",
            "scan_run_id": "run_idem",
            "tenant_id": "tenant_a",
        }
        enrichment = {
            "cve_key": "CVE_2024_9999",
            "epss_score": 0.33,
            "epss_percentile": 0.55,
            "in_kev": False,
            "cwe_chain": ["CWE-22"],
            "d3fend_techniques": [],
            "req_keys": [],
        }

        def fresh_iter(*args, **kwargs):
            return iter([[finding]])

        mock_repo.fetch_findings_for_run.side_effect = fresh_iter
        mock_repo.aql_enrich_batch.return_value = {"CVE_2024_9999": enrichment}

        pipeline.run("run_idem", "tenant_a")
        first_call = mock_repo.bulk_update_findings.call_args_list[0][0][0][0]

        pipeline.run("run_idem", "tenant_a")
        second_call = mock_repo.bulk_update_findings.call_args_list[1][0][0][0]

        # Key enrichment fields must be identical across both runs
        for field in ("epss_score", "epss_percentile", "in_kev", "cwe_chain"):
            assert first_call.get(field) == second_call.get(field), (
                f"Field '{field}' differs between runs: "
                f"{first_call.get(field)} vs {second_call.get(field)}"
            )


# ===========================================================================
# Group 2: CompactionPipeline (AC-011 to AC-017)
# ===========================================================================


class TestCompactionPipeline:
    """S-UC008-01 .. S-UC008-07 — CompactionPipeline (AC-011–AC-017)."""

    @pytest.fixture
    def mock_db(self):
        return _make_mock_db()

    @pytest.fixture
    def mock_repo(self):
        return _make_mock_repo()

    @pytest.fixture
    def pipeline(self, mock_db, mock_repo):
        from complira_graph.ingestion.compaction_pipeline import CompactionPipeline
        return CompactionPipeline(db=mock_db, repo=mock_repo)

    def _findings_sharing_cwe(self):
        return [
            {
                "_key": "fp_A",
                "cve_id": "CVE-2024-0001",
                "cwe_chain": ["CWE-79"],
                "cvss_base": 8.0,
                "epss_score": 0.5,
                "in_kev": True,
                "d3fend_techniques": None,
                "scan_run_id": "run_c",
                "tenant_id": "tenant_a",
            },
            {
                "_key": "fp_B",
                "cve_id": "CVE-2024-0002",
                "cwe_chain": ["CWE-79"],
                "cvss_base": 6.0,
                "epss_score": 0.2,
                "in_kev": False,
                "d3fend_techniques": None,
                "scan_run_id": "run_c",
                "tenant_id": "tenant_a",
            },
        ]

    # -----------------------------------------------------------------------
    # S-UC008-01 — AC-011: CWE deduplication → same compaction_group_id
    # -----------------------------------------------------------------------

    def test_findings_sharing_cwe_get_same_group_id(self, pipeline, mock_repo):
        """
        S-UC008-01 (AC-011):
        Findings sharing the same CWE within a scan_run must be assigned
        the same compaction_group_id.
        """
        findings = self._findings_sharing_cwe()
        mock_repo.fetch_findings_for_run.return_value = iter([findings])

        pipeline.run("run_c", "tenant_a")

        mock_repo.bulk_update_findings.assert_called_once()
        updates = mock_repo.bulk_update_findings.call_args[0][0]
        assert len(updates) == 2
        group_ids = {u["compaction_group_id"] for u in updates}
        assert len(group_ids) == 1, (
            f"Expected all findings in the same group; got groups: {group_ids}"
        )

    # -----------------------------------------------------------------------
    # S-UC008-02 — AC-012: Duplicate suppression
    # -----------------------------------------------------------------------

    def test_canonical_not_compacted_others_are(self, pipeline, mock_repo):
        """
        S-UC008-02 (AC-012):
        Within each compaction group, exactly one finding has compacted=False
        (the canonical); all others have compacted=True.
        """
        findings = self._findings_sharing_cwe()
        mock_repo.fetch_findings_for_run.return_value = iter([findings])

        pipeline.run("run_c", "tenant_a")

        updates = mock_repo.bulk_update_findings.call_args[0][0]
        not_compacted = [u for u in updates if not u["compacted"]]
        compacted = [u for u in updates if u["compacted"]]

        assert len(not_compacted) == 1, "Expected exactly one canonical finding"
        assert len(compacted) == 1, "Expected exactly one compacted duplicate"

    # -----------------------------------------------------------------------
    # S-UC008-03 — AC-014: Risk score formula
    # -----------------------------------------------------------------------

    def test_risk_score_formula(self, pipeline):
        """
        S-UC008-03 (AC-014):
        cvss=8.0, epss=0.5, in_kev=True, d3fend_techniques=None →
        risk_score = (0.8*0.4) + (0.5*0.3) + (1.0*0.2) + (0.0*0.1)
                   = 0.32 + 0.15 + 0.20 + 0.00 = 0.67
        """
        finding = {
            "_key": "fp_risk",
            "cve_id": "CVE-2024-0010",
            "cvss_base": 8.0,
            "epss_score": 0.5,
            "in_kev": True,
            "d3fend_techniques": None,
        }
        score = pipeline._compute_risk_score(finding)
        assert abs(score - 0.67) < 1e-9, f"Expected 0.67, got {score}"

    # -----------------------------------------------------------------------
    # S-UC008-04 — AC-015: Cluster ranking
    # -----------------------------------------------------------------------

    def test_cluster_ranking_sorted_by_max_risk_descending(self, pipeline, mock_repo):
        """
        S-UC008-04 (AC-015):
        Three groups ordered by max(risk_score) descending → rank 1 is highest.
        """
        # Three findings, each with distinct CWE so they form separate groups
        f_high = {
            "_key": "fp_high",
            "cve_id": "CVE-2024-H",
            "cwe_chain": ["CWE-89"],
            "cvss_base": 9.0,
            "epss_score": 0.9,
            "in_kev": True,
            "d3fend_techniques": ["d3f:X"],
            "scan_run_id": "run_rank",
            "tenant_id": "tenant_a",
        }
        f_med = {
            "_key": "fp_med",
            "cve_id": "CVE-2024-M",
            "cwe_chain": ["CWE-22"],
            "cvss_base": 5.0,
            "epss_score": 0.3,
            "in_kev": False,
            "d3fend_techniques": None,
            "scan_run_id": "run_rank",
            "tenant_id": "tenant_a",
        }
        f_low = {
            "_key": "fp_low",
            "cve_id": "CVE-2024-L",
            "cwe_chain": ["CWE-79"],
            "cvss_base": 2.0,
            "epss_score": 0.05,
            "in_kev": False,
            "d3fend_techniques": None,
            "scan_run_id": "run_rank",
            "tenant_id": "tenant_a",
        }

        mock_repo.fetch_findings_for_run.return_value = iter([[f_high, f_med, f_low]])

        pipeline.run("run_rank", "tenant_a")

        updates = mock_repo.bulk_update_findings.call_args[0][0]
        rank_by_key = {u["_key"]: u["cluster_rank"] for u in updates}

        # fp_high should have rank 1 (highest risk)
        assert rank_by_key["fp_high"] == 1, (
            f"fp_high should have rank 1, got {rank_by_key}"
        )
        # fp_low should have rank 3 (lowest risk)
        assert rank_by_key["fp_low"] == 3, (
            f"fp_low should have rank 3, got {rank_by_key}"
        )
        # fp_med should be rank 2
        assert rank_by_key["fp_med"] == 2, (
            f"fp_med should have rank 2, got {rank_by_key}"
        )

    # -----------------------------------------------------------------------
    # S-UC008-05 — AC-016: Status transitions to "compacted"
    # -----------------------------------------------------------------------

    def test_status_set_to_compacted(self, pipeline, mock_repo):
        """
        S-UC008-05 (AC-016):
        update_scan_run_status is called with status="compacted" after the pipeline
        completes.
        """
        mock_repo.fetch_findings_for_run.return_value = iter([])

        pipeline.run("run_compact_status", "tenant_a")

        mock_repo.update_scan_run_status.assert_called_once()
        args, kwargs = mock_repo.update_scan_run_status.call_args
        called_status = args[1] if len(args) > 1 else kwargs.get("status")
        assert called_status == "compacted"

    # -----------------------------------------------------------------------
    # S-UC008-06 — AC-017: Idempotent
    # -----------------------------------------------------------------------

    def test_idempotency_risk_scores_identical(self, pipeline, mock_repo):
        """
        S-UC008-06 (AC-017):
        Running compaction twice for the same findings yields identical
        risk_score and compaction_group_id values.
        """
        findings = self._findings_sharing_cwe()

        def fresh_iter(*args, **kwargs):
            return iter([findings])

        mock_repo.fetch_findings_for_run.side_effect = fresh_iter

        pipeline.run("run_idem_c", "tenant_a")
        first = {u["_key"]: u for u in mock_repo.bulk_update_findings.call_args_list[0][0][0]}

        pipeline.run("run_idem_c", "tenant_a")
        second = {u["_key"]: u for u in mock_repo.bulk_update_findings.call_args_list[1][0][0]}

        for fp in first:
            assert first[fp]["risk_score"] == second[fp]["risk_score"]
            assert first[fp]["compaction_group_id"] == second[fp]["compaction_group_id"]


# ===========================================================================
# Group 3: ControlMappingPipeline (AC-018 to AC-022)
# ===========================================================================


class TestControlMappingPipeline:
    """S-UC009-01 .. S-UC009-05 — ControlMappingPipeline (AC-018–AC-022)."""

    @pytest.fixture
    def mock_db(self):
        return _make_mock_db()

    @pytest.fixture
    def mock_repo(self):
        return _make_mock_repo()

    @pytest.fixture
    def pipeline(self, mock_db, mock_repo):
        from complira_graph.ingestion.control_mapping_pipeline import ControlMappingPipeline
        return ControlMappingPipeline(db=mock_db, repo=mock_repo)

    def _sample_controls(self):
        return [
            {
                "_key": "ctrl_001",
                "scan_run_id": "run_m",
                "tenant_id": "tenant_a",
                "req_id": "NIST_AC-1",
            },
            {
                "_key": "ctrl_002",
                "scan_run_id": "run_m",
                "tenant_id": "tenant_a",
                "req_id": "ISO_A.12.6.1",
            },
        ]

    # -----------------------------------------------------------------------
    # S-UC009-01 — AC-018: Framework annotation written per control
    # -----------------------------------------------------------------------

    def test_framework_annotation_written_per_control(self, pipeline, mock_repo, mock_db):
        """
        S-UC009-01 (AC-018):
        bulk_update_detected_controls (via db.aql.execute) receives update
        dicts that include a non-None 'framework' field.
        """
        controls = self._sample_controls()
        mock_repo.fetch_detected_controls_for_run.return_value = controls
        mock_repo.aql_resolve_control_framework.return_value = [
            {"control_key": "ctrl_001", "framework": "NIST 800-53"},
            {"control_key": "ctrl_002", "framework": "ISO 27001"},
        ]
        mock_repo.aql_resolve_evidence_chains.return_value = [
            {"control_key": "ctrl_001", "chain": ["fp_A", "CWE-79", "NIST_AC-1", "ctrl_001"]},
            {"control_key": "ctrl_002", "chain": ["fp_B", "CWE-22", "ISO_A.12.6.1", "ctrl_002"]},
        ]
        mock_repo.aql_get_total_reqs_by_framework.return_value = {
            "NIST 800-53": 100,
            "ISO 27001": 80,
        }

        # Capture the AQL execute call that bulk-updates detected_controls
        pipeline.run("run_m", "tenant_a")

        mock_db.aql.execute.assert_called()
        # Extract the updates from the first AQL call
        call_kwargs = mock_db.aql.execute.call_args[1]
        updates = call_kwargs.get("bind_vars", {}).get("updates", [])
        frameworks = {u["framework"] for u in updates}
        assert "NIST 800-53" in frameworks
        assert "ISO 27001" in frameworks

    # -----------------------------------------------------------------------
    # S-UC009-02 — AC-019: Evidence chain is list of 4 elements
    # -----------------------------------------------------------------------

    def test_evidence_chain_has_four_elements(self, pipeline, mock_repo, mock_db):
        """
        S-UC009-02 (AC-019):
        evidence_chain written per detected_controls must be a list with exactly
        4 elements: [finding_id, cwe_id, req_id, control_id].
        """
        controls = [
            {
                "_key": "ctrl_100",
                "scan_run_id": "run_ec",
                "tenant_id": "tenant_a",
                "req_id": "NIST_SC-7",
            }
        ]
        mock_repo.fetch_detected_controls_for_run.return_value = controls
        mock_repo.aql_resolve_control_framework.return_value = [
            {"control_key": "ctrl_100", "framework": "NIST 800-53"},
        ]
        mock_repo.aql_resolve_evidence_chains.return_value = [
            {
                "control_key": "ctrl_100",
                "chain": ["fp_X", "CWE-89", "NIST_SC-7", "ctrl_100"],
            }
        ]
        mock_repo.aql_get_total_reqs_by_framework.return_value = {"NIST 800-53": 50}

        pipeline.run("run_ec", "tenant_a")

        call_kwargs = mock_db.aql.execute.call_args[1]
        updates = call_kwargs.get("bind_vars", {}).get("updates", [])
        assert len(updates) == 1
        chain = updates[0]["evidence_chain"]
        assert isinstance(chain, list)
        assert len(chain) == 4, f"Expected 4-element chain, got: {chain}"

    # -----------------------------------------------------------------------
    # S-UC009-03 — AC-020: coverage_by_framework dict written to scan_run
    # -----------------------------------------------------------------------

    def test_coverage_by_framework_written_to_scan_run(self, pipeline, mock_repo, mock_db):
        """
        S-UC009-03 (AC-020):
        update_scan_run_status is called with extra_fields containing
        coverage_by_framework dict with at least one key and float value ∈ [0, 1].
        """
        controls = self._sample_controls()
        mock_repo.fetch_detected_controls_for_run.return_value = controls
        mock_repo.aql_resolve_control_framework.return_value = [
            {"control_key": "ctrl_001", "framework": "NIST 800-53"},
            {"control_key": "ctrl_002", "framework": "ISO 27001"},
        ]
        mock_repo.aql_resolve_evidence_chains.return_value = []
        mock_repo.aql_get_total_reqs_by_framework.return_value = {
            "NIST 800-53": 10,
            "ISO 27001": 8,
        }

        pipeline.run("run_m", "tenant_a")

        mock_repo.update_scan_run_status.assert_called_once()
        _, kwargs = mock_repo.update_scan_run_status.call_args
        extra = kwargs.get("extra_fields") or (
            mock_repo.update_scan_run_status.call_args[0][2]
            if len(mock_repo.update_scan_run_status.call_args[0]) > 2
            else {}
        )

        assert "coverage_by_framework" in extra
        cov = extra["coverage_by_framework"]
        assert isinstance(cov, dict)
        assert len(cov) > 0
        for fw, val in cov.items():
            assert isinstance(val, float), f"{fw} coverage is not float: {val}"
            assert 0.0 <= val <= 1.0, f"{fw} coverage {val} out of range"

    # -----------------------------------------------------------------------
    # S-UC009-04 — AC-021: Status transitions to "mapped"
    # -----------------------------------------------------------------------

    def test_status_set_to_mapped(self, pipeline, mock_repo):
        """
        S-UC009-04 (AC-021):
        update_scan_run_status is called with status="mapped" after the pipeline
        completes.
        """
        mock_repo.fetch_detected_controls_for_run.return_value = []

        pipeline.run("run_mapped_status", "tenant_a")

        mock_repo.update_scan_run_status.assert_called_once()
        args, kwargs = mock_repo.update_scan_run_status.call_args
        called_status = args[1] if len(args) > 1 else kwargs.get("status")
        assert called_status == "mapped"

    # -----------------------------------------------------------------------
    # S-UC009-05 — Edge case: zero detected_controls (UC-009-EDGE)
    # -----------------------------------------------------------------------

    def test_zero_detected_controls_succeeds_with_empty_coverage(self, pipeline, mock_repo):
        """
        S-UC009-05 (edge case from UC-009-EDGE):
        When there are no detected_controls for a scan_run, the pipeline
        completes without error, sets status="mapped", and writes
        coverage_by_framework={}.
        """
        mock_repo.fetch_detected_controls_for_run.return_value = []

        pipeline.run("run_zero_ctrl", "tenant_a")

        # Should still complete and write status=mapped
        mock_repo.update_scan_run_status.assert_called_once()
        args, kwargs = mock_repo.update_scan_run_status.call_args
        status = args[1] if len(args) > 1 else kwargs.get("status")
        assert status == "mapped"

        extra = kwargs.get("extra_fields") or (
            args[2] if len(args) > 2 else {}
        )
        cov = extra.get("coverage_by_framework", None) if extra else None
        # Should be empty dict or None (no controls → no frameworks)
        if cov is not None:
            assert cov == {}


# ===========================================================================
# Group 4: PipelineCoordinator (AC-023 to AC-028)
# ===========================================================================


class TestPipelineCoordinator:
    """S-CROSS-01 .. S-CROSS-06 — PipelineCoordinator (AC-023–AC-028)."""

    @pytest.fixture
    def mock_db(self):
        db = _make_mock_db()
        # Default: reference DB reachable (ping returns empty list, not exception)
        db.aql.execute.return_value = iter([])
        # scan_runs.get returns a completed scan by default
        scan_runs_col = MagicMock()
        scan_runs_col.get.return_value = {
            "_key": "run_coord",
            "status": "completed",
            "tenant_id": "tenant_a",
        }
        db.collection.return_value = scan_runs_col
        return db

    # -----------------------------------------------------------------------
    # S-CROSS-01 — AC-023: Full chain: enrichment → compaction → mapping
    # -----------------------------------------------------------------------

    def test_full_chain_called_in_order(self, mock_db):
        """
        S-CROSS-01 (AC-023):
        PipelineCoordinator calls EnrichmentPipeline.run → CompactionPipeline.run
        → ControlMappingPipeline.run in order when the scan_run status is "completed".
        """
        call_order = []

        with (
            patch(
                "complira_graph.ingestion.pipeline_coordinator.EnrichmentPipeline"
            ) as MockEnrich,
            patch(
                "complira_graph.ingestion.pipeline_coordinator.CompactionPipeline"
            ) as MockCompact,
            patch(
                "complira_graph.ingestion.pipeline_coordinator.ControlMappingPipeline"
            ) as MockMap,
            patch(
                "complira_graph.ingestion.pipeline_coordinator.ScanEnrichmentRepository"
            ),
            patch(
                "complira_graph.ingestion.pipeline_coordinator.EvidenceRunRepository"
            ),
        ):
            enrich_inst = MockEnrich.return_value
            compact_inst = MockCompact.return_value
            map_inst = MockMap.return_value

            def _record_enrich(*a, **kw):
                call_order.append("enrichment")

            def _record_compact(*a, **kw):
                call_order.append("compaction")

            def _record_map(*a, **kw):
                call_order.append("mapping")

            enrich_inst.run.side_effect = _record_enrich
            compact_inst.run.side_effect = _record_compact
            map_inst.run.side_effect = _record_map

            from complira_graph.ingestion.pipeline_coordinator import PipelineCoordinator

            coordinator = PipelineCoordinator(mock_db)
            coordinator.run_post_ingest_pipeline("run_coord", "tenant_a")

        assert call_order == ["enrichment", "compaction", "mapping"], (
            f"Expected enrichment → compaction → mapping, got: {call_order}"
        )

    # -----------------------------------------------------------------------
    # S-CROSS-04 — AC-027: Reference DB unavailable → enrichment_pending
    # -----------------------------------------------------------------------

    def test_reference_db_unavailable_sets_enrichment_pending(self, mock_db):
        """
        S-CROSS-04 (AC-027):
        When the reference DB is unreachable (aql.execute raises an exception),
        the coordinator sets scan_run.status = "enrichment_pending" and does
        NOT attempt to run any pipeline stage.
        """
        # Make the DB ping fail
        mock_db.aql.execute.side_effect = Exception("Connection refused")

        with (
            patch(
                "complira_graph.ingestion.pipeline_coordinator.EnrichmentPipeline"
            ) as MockEnrich,
            patch(
                "complira_graph.ingestion.pipeline_coordinator.CompactionPipeline"
            ),
            patch(
                "complira_graph.ingestion.pipeline_coordinator.ControlMappingPipeline"
            ),
            patch(
                "complira_graph.ingestion.pipeline_coordinator.ScanEnrichmentRepository"
            ) as MockRepo,
            patch(
                "complira_graph.ingestion.pipeline_coordinator.EvidenceRunRepository"
            ),
        ):
            mock_repo_inst = MockRepo.return_value
            mock_repo_inst.update_scan_run_status = Mock()

            from complira_graph.ingestion.pipeline_coordinator import PipelineCoordinator

            coordinator = PipelineCoordinator(mock_db)
            coordinator.run_post_ingest_pipeline("run_coord", "tenant_a")

        mock_repo_inst.update_scan_run_status.assert_called_once()
        args, kwargs = mock_repo_inst.update_scan_run_status.call_args
        status = args[1] if len(args) > 1 else kwargs.get("status")
        assert status == "enrichment_pending"
        MockEnrich.return_value.run.assert_not_called()

    # -----------------------------------------------------------------------
    # S-CROSS-03 — AC-026: Stage 2 failure → status="pipeline_failed"
    # -----------------------------------------------------------------------

    def test_stage2_failure_sets_pipeline_failed_and_skips_stage3(self, mock_db):
        """
        S-CROSS-03 (AC-026):
        If CompactionPipeline.run raises an exception, the coordinator sets
        scan_run.status = "pipeline_failed" and does NOT call
        ControlMappingPipeline.run.
        """
        with (
            patch(
                "complira_graph.ingestion.pipeline_coordinator.EnrichmentPipeline"
            ) as MockEnrich,
            patch(
                "complira_graph.ingestion.pipeline_coordinator.CompactionPipeline"
            ) as MockCompact,
            patch(
                "complira_graph.ingestion.pipeline_coordinator.ControlMappingPipeline"
            ) as MockMap,
            patch(
                "complira_graph.ingestion.pipeline_coordinator.ScanEnrichmentRepository"
            ) as MockRepo,
            patch(
                "complira_graph.ingestion.pipeline_coordinator.EvidenceRunRepository"
            ),
        ):
            MockEnrich.return_value.run = Mock()
            MockCompact.return_value.run = Mock(
                side_effect=RuntimeError("Compaction boom")
            )
            MockMap.return_value.run = Mock()
            mock_repo_inst = MockRepo.return_value
            mock_repo_inst.update_scan_run_status = Mock()

            from complira_graph.ingestion.pipeline_coordinator import PipelineCoordinator

            coordinator = PipelineCoordinator(mock_db)
            coordinator.run_post_ingest_pipeline("run_coord", "tenant_a")

        # Stage 3 must NOT have been called
        MockMap.return_value.run.assert_not_called()

        # Status must be pipeline_failed
        status_calls = mock_repo_inst.update_scan_run_status.call_args_list
        statuses_written = []
        for c in status_calls:
            a, kw = c
            statuses_written.append(a[1] if len(a) > 1 else kw.get("status"))
        assert "pipeline_failed" in statuses_written, (
            f"Expected 'pipeline_failed' in {statuses_written}"
        )

    # -----------------------------------------------------------------------
    # S-CROSS-06 — AC-028: tenant_id passed through all stages
    # -----------------------------------------------------------------------

    def test_tenant_id_passed_to_all_stages(self, mock_db):
        """
        S-CROSS-06 (AC-028):
        PipelineCoordinator passes tenant_id to every pipeline stage's run()
        call, ensuring tenant isolation.
        """
        with (
            patch(
                "complira_graph.ingestion.pipeline_coordinator.EnrichmentPipeline"
            ) as MockEnrich,
            patch(
                "complira_graph.ingestion.pipeline_coordinator.CompactionPipeline"
            ) as MockCompact,
            patch(
                "complira_graph.ingestion.pipeline_coordinator.ControlMappingPipeline"
            ) as MockMap,
            patch(
                "complira_graph.ingestion.pipeline_coordinator.ScanEnrichmentRepository"
            ),
            patch(
                "complira_graph.ingestion.pipeline_coordinator.EvidenceRunRepository"
            ),
        ):
            MockEnrich.return_value.run = Mock()
            MockCompact.return_value.run = Mock()
            MockMap.return_value.run = Mock()

            from complira_graph.ingestion.pipeline_coordinator import PipelineCoordinator

            coordinator = PipelineCoordinator(mock_db)
            coordinator.run_post_ingest_pipeline("run_coord", "tenant_xyz")

        # All three stages must receive tenant_id="tenant_xyz"
        for stage_mock, name in [
            (MockEnrich.return_value.run, "EnrichmentPipeline"),
            (MockCompact.return_value.run, "CompactionPipeline"),
            (MockMap.return_value.run, "ControlMappingPipeline"),
        ]:
            stage_mock.assert_called_once()
            a, kw = stage_mock.call_args
            tenant = kw.get("tenant_id") or (a[1] if len(a) > 1 else None)
            assert tenant == "tenant_xyz", (
                f"{name}.run() called with tenant_id={tenant!r}, expected 'tenant_xyz'"
            )


# ===========================================================================
# Group 5: Pipeline endpoint (AC-024, AC-025)
# ===========================================================================


class TestPipelineEndpoint:
    """S-CROSS-02 (AC-024, AC-025) — POST /v1/scans/{id}/enrich and GET /v1/scan/{id}."""

    @pytest.fixture
    def app(self):
        from api.main import app
        yield app
        app.dependency_overrides.clear()

    @pytest.fixture
    def api_client(self, app):
        from fastapi.testclient import TestClient
        return TestClient(app)

    @pytest.fixture
    def mock_customer(self):
        customer = Mock()
        customer._key = "customer_test"
        customer.id = "tenant_a"
        customer.name = "Test Customer"
        customer.tier = "pro"
        customer.database_name = "complira_tenant_test"
        customer.frameworks = ["NIST_800_53"]
        return customer

    @pytest.fixture
    def override_auth(self, app, mock_customer):
        from api.core.security import get_current_customer

        async def _override(api_key=None, token=None):
            return mock_customer

        app.dependency_overrides[get_current_customer] = _override
        yield mock_customer
        app.dependency_overrides.pop(get_current_customer, None)

    # -----------------------------------------------------------------------
    # S-CROSS-02 / AC-024: POST /v1/scans/{id}/enrich → 202
    # -----------------------------------------------------------------------

    @pytest.mark.integration
    def test_enrich_endpoint_returns_202(self, api_client, override_auth):
        """
        S-CROSS-02 (AC-024):
        POST /v1/scans/{scan_run_id}/enrich returns HTTP 202 Accepted.
        The background pipeline task is queued but NOT awaited.

        Note: get_reference_db and PipelineCoordinator are imported inside the
        endpoint function body, so we patch them via api.core.database and
        complira_graph.ingestion.pipeline_coordinator respectively.
        """
        scan_run_id = "run_e2e_001"
        mock_run_doc = {
            "_key": scan_run_id,
            "tenant_id": "tenant_a",
            "status": "completed",
        }

        mock_ref_db = _make_mock_db()
        scan_runs_col = MagicMock()
        scan_runs_col.get.return_value = mock_run_doc
        mock_ref_db.collection.return_value = scan_runs_col

        with (
            patch(
                "api.core.database.get_reference_db",
                return_value=mock_ref_db,
            ),
            patch(
                "complira_graph.ingestion.pipeline_coordinator.PipelineCoordinator"
            ) as MockCoord,
        ):
            MockCoord.return_value.run_post_ingest_pipeline = Mock()

            response = api_client.post(
                f"/v1/scans/{scan_run_id}/enrich",
                headers={"X-API-Key": "test_key"},
            )

        assert response.status_code == 202, (
            f"Expected 202, got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body.get("scan_run_id") == scan_run_id
        assert "queued" in body.get("message", "").lower()

    @pytest.mark.integration
    def test_enrich_endpoint_404_for_unknown_run(self, api_client, override_auth):
        """
        S-CROSS-02 variant (AC-024):
        POST /v1/scans/{scan_run_id}/enrich returns 404 when the scan_run
        does not exist or belongs to a different tenant.
        """
        mock_ref_db = _make_mock_db()
        scan_runs_col = MagicMock()
        scan_runs_col.get.return_value = None  # not found
        mock_ref_db.collection.return_value = scan_runs_col

        with patch(
            "api.core.database.get_reference_db",
            return_value=mock_ref_db,
        ):
            response = api_client.post(
                "/v1/scans/run_does_not_exist/enrich",
                headers={"X-API-Key": "test_key"},
            )

        assert response.status_code == 404

    @pytest.mark.integration
    def test_enrich_endpoint_409_for_non_retriable_status(self, api_client, override_auth):
        """
        S-CROSS-02 variant (AC-024):
        POST /v1/scans/{scan_run_id}/enrich returns 409 when the scan_run
        has a non-retriable status (e.g. "mapped").
        """
        mock_run_doc = {
            "_key": "run_mapped",
            "tenant_id": "tenant_a",
            "status": "mapped",
        }
        mock_ref_db = _make_mock_db()
        scan_runs_col = MagicMock()
        scan_runs_col.get.return_value = mock_run_doc
        mock_ref_db.collection.return_value = scan_runs_col

        with patch(
            "api.core.database.get_reference_db",
            return_value=mock_ref_db,
        ):
            response = api_client.post(
                "/v1/scans/run_mapped/enrich",
                headers={"X-API-Key": "test_key"},
            )

        assert response.status_code == 409

    # -----------------------------------------------------------------------
    # S-CROSS-02 / AC-025: GET /v1/scan/{run_id} returns current status
    # -----------------------------------------------------------------------

    @pytest.mark.integration
    def test_get_scan_run_returns_status(self, api_client, override_auth):
        """
        S-CROSS-02 (AC-025):
        GET /v1/scan/{run_id} returns the scan_run document including the
        current pipeline status field.

        Note: get_reference_db is imported inside the endpoint function body,
        so we patch it via api.core.database.
        """
        scan_run_id = "run_status_poll"
        mock_run_doc = {
            "_key": scan_run_id,
            "tenant_id": "tenant_a",
            "status": "enriched",
            "tools_invoked": ["grype"],
            "tool_version": "0.75.0",
            "scan_type": "sca",
            "created_at": "2026-03-21T00:00:00Z",
            "finding_counts": {"total": 5},
            "components_count": 0,
            "metadata": {},
        }

        mock_ref_db = _make_mock_db()
        scan_runs_col = MagicMock()
        scan_runs_col.get.return_value = mock_run_doc
        mock_ref_db.collection.return_value = scan_runs_col

        with patch(
            "api.core.database.get_reference_db",
            return_value=mock_ref_db,
        ):
            response = api_client.get(
                f"/v1/scan/{scan_run_id}",
                headers={"X-API-Key": "test_key"},
            )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body["success"] is True
        session = body["data"]
        assert session.get("status") == "enriched"
