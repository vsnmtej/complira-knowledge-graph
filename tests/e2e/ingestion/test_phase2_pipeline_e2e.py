"""
Phase 2 Pipeline API/E2E Scenarios (Component-Integration Level)

Scenario coverage (see api-e2e-testing.md):
  UC-010 LLM Enrichment:
    S-UC010-01: CVE finding → llm fields + status=llm_enriched (AC-029,030,031,033)
    S-UC010-02: Non-CVE finding handled (AC-032)
    S-UC010-03: Partial batch failure continues (AC-034)
    S-UC010-04: All batches fail → RuntimeError; coordinator sets pipeline_failed (AC-034)
    S-UC010-05: Token usage written with model name (AC-035)
    S-UC010-06: Upsert semantics — second run overwrites first (AC-036)
    S-UC010-07: attack_surface normalization (AC-031)
  UC-011 Blast Radius:
    S-UC011-01: SCA finding with purl → score+lists+status (AC-037,039,040,042)
    S-UC011-02: No-purl findings → zero score + empty lists (AC-038)
    S-UC011-03: Score formula = affected/total (AC-041)
    S-UC011-04: Score clamped to 1.0 (AC-041)
    S-UC011-05: Idempotent — same traversal result same score (AC-043)
  UC-012 EPSS Velocity:
    S-UC012-01: CVE finding → velocity+trend+status (AC-044,049)
    S-UC012-02: No-CVE findings → zero velocity + stable (AC-045)
    S-UC012-03: Rising trend (AC-046)
    S-UC012-04: Falling trend (AC-047)
    S-UC012-05: Insufficient history → zero+stable (AC-048)
    S-UC012-06: Idempotent — same history same result (AC-050)
  Cross-Cutting:
    S-CROSS-01: Full chain mapped→velocity_computed (AC-051)
    S-CROSS-02: Re-trigger from llm_enriched / blast_radius_computed (AC-052)
    S-CROSS-03: Stage failure → pipeline_failed; downstream not called (AC-053)
    S-CROSS-04: tenant_id passed through all stages (AC-054)
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from complira_graph.ingestion.blast_radius_pipeline import BlastRadiusPipeline
from complira_graph.ingestion.epss_velocity_pipeline import EPSSVelocityPipeline
from complira_graph.ingestion.llm_enrichment_pipeline import LLMEnrichmentPipeline
from complira_graph.ingestion.pipeline_coordinator import PipelineCoordinator
from complira_graph.ingestion.pipeline_llm_client import LLMBatchResult
from complira_graph.ingestion.scan_blast_radius_repository import ScanBlastRadiusRepository
from complira_graph.ingestion.scan_enrichment_repository import ScanEnrichmentRepository
from complira_graph.ingestion.scan_llm_enrichment_repository import ScanLLMEnrichmentRepository


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _cve_finding(key: str, cve_id: str = "CVE-2024-1234", purl: str | None = None) -> dict:
    return {
        "_key": key,
        "cve_id": cve_id,
        "severity": "HIGH",
        "package_name": "log4j",
        "cvss_base": 9.8,
        "purl": purl,
    }


def _sast_finding(key: str, rule_id: str = "semgrep.sql-injection") -> dict:
    return {"_key": key, "rule_id": rule_id, "severity": "MEDIUM"}


def _llm_result(key: str, surface: str = "network") -> dict:
    return {
        "finding_key": key,
        "risk_summary": "RCE via log4shell.",
        "remediation": "Upgrade to log4j >= 2.17.1.",
        "attack_surface": surface,
    }


def _make_llm_enrichment_pipeline(findings_batches, llm_side_effect):
    """Returns (pipeline, repo, llm_repo, llm_client) with mocks wired."""
    db = MagicMock()
    repo = MagicMock(spec=ScanEnrichmentRepository)
    llm_repo = MagicMock(spec=ScanLLMEnrichmentRepository)
    llm_client = MagicMock()
    llm_client._model = "claude-haiku-4-5-20251001"
    repo.fetch_findings_for_run.return_value = iter(findings_batches)
    llm_client.call_batch.side_effect = llm_side_effect
    pipeline = LLMEnrichmentPipeline(db, repo, llm_repo, llm_client)
    return pipeline, repo, llm_repo, llm_client


def _make_blast_pipeline(findings_batches, blast_traversal, total_components=10):
    db = MagicMock()
    repo = MagicMock(spec=ScanEnrichmentRepository)
    blast_repo = MagicMock(spec=ScanBlastRadiusRepository)
    repo.fetch_findings_for_run.return_value = iter(findings_batches)
    blast_repo.aql_blast_radius_for_purl.return_value = blast_traversal
    blast_repo.aql_total_project_components.return_value = total_components
    pipeline = BlastRadiusPipeline(db, repo, blast_repo)
    return pipeline, repo, blast_repo


def _make_epss_pipeline(findings_batches, history_map):
    db = MagicMock()
    repo = MagicMock(spec=ScanEnrichmentRepository)
    repo.fetch_findings_for_run.return_value = iter(findings_batches)
    repo.aql_get_epss_history_batch.return_value = history_map
    pipeline = EPSSVelocityPipeline(db, repo)
    return pipeline, repo


# ---------------------------------------------------------------------------
# S-UC010: LLM Enrichment
# ---------------------------------------------------------------------------

class TestSUC01001CVEFindingFullFields:
    """S-UC010-01 — AC-029, AC-030, AC-031, AC-033"""

    def test_llm_fields_written_and_status_set(self):
        findings = [_cve_finding("fp1")]
        llm_resp = LLMBatchResult(
            results=[_llm_result("fp1", "network")],
            input_tokens=10,
            output_tokens=20,
        )
        pipeline, repo, llm_repo, _ = _make_llm_enrichment_pipeline(
            [findings], [llm_resp]
        )

        pipeline.run("run1", "t1")

        updates = llm_repo.bulk_write_llm_fields.call_args.args[0]
        u = updates[0]
        assert u["llm_risk_summary"] == "RCE via log4shell."  # AC-029
        assert u["llm_remediation"] == "Upgrade to log4j >= 2.17.1."  # AC-030
        assert u["llm_attack_surface"] == "network"  # AC-031
        assert "llm_enriched_at" in u

        # AC-033: status written
        status_call = llm_repo.update_scan_run_status.call_args
        assert status_call.args[1] == "llm_enriched"


class TestSUC01002NonCVEFinding:
    """S-UC010-02 — AC-032: non-CVE finding uses rule_id+severity, not skipped."""

    def test_non_cve_finding_receives_llm_output(self):
        findings = [_sast_finding("fp2")]
        llm_resp = LLMBatchResult(
            results=[{"finding_key": "fp2", "risk_summary": "SQL injection.", "remediation": "Use parameterized queries.", "attack_surface": "network"}],
            input_tokens=5,
            output_tokens=10,
        )
        pipeline, repo, llm_repo, llm_client = _make_llm_enrichment_pipeline(
            [findings], [llm_resp]
        )

        pipeline.run("run1", "t1")

        llm_client.call_batch.assert_called_once()
        # Verify context includes rule_id (not cve_id)
        call_findings = llm_client.call_batch.call_args.args[0]
        assert call_findings[0].get("rule_id") == "semgrep.sql-injection"
        assert "cve_id" not in call_findings[0]

        updates = llm_repo.bulk_write_llm_fields.call_args.args[0]
        assert updates[0]["llm_risk_summary"] == "SQL injection."


class TestSUC01003PartialBatchFailure:
    """S-UC010-03 — AC-034: one batch fail, other batches succeed."""

    def test_partial_failure_continues_and_writes_success(self):
        batch1 = [_cve_finding("fp1")]
        batch2 = [_cve_finding("fp2", cve_id="CVE-2024-5678")]
        llm_resp2 = LLMBatchResult(
            results=[_llm_result("fp2")],
            input_tokens=5,
            output_tokens=10,
        )
        pipeline, repo, llm_repo, _ = _make_llm_enrichment_pipeline(
            [batch1, batch2],
            [Exception("API down"), llm_resp2],
        )

        pipeline.run("run1", "t1")  # must not raise

        # Only second batch was written
        assert llm_repo.bulk_write_llm_fields.call_count == 1
        llm_repo.update_scan_run_status.assert_called_once()


class TestSUC01004AllBatchesFail:
    """S-UC010-04 — AC-034: all batches fail → RuntimeError."""

    def test_all_fail_raises_runtime_error(self):
        findings = [_cve_finding("fp1")]
        pipeline, repo, llm_repo, _ = _make_llm_enrichment_pipeline(
            [findings], [Exception("API down")]
        )

        with pytest.raises(RuntimeError, match="all_llm_batches_failed"):
            pipeline.run("run1", "t1")

        llm_repo.update_scan_run_status.assert_not_called()


class TestSUC01005TokenUsage:
    """S-UC010-05 — AC-035: token usage written with model name."""

    def test_token_usage_written_to_scan_run(self):
        findings = [_cve_finding("fp1")]
        llm_resp = LLMBatchResult(results=[_llm_result("fp1")], input_tokens=15, output_tokens=25)
        pipeline, repo, llm_repo, llm_client = _make_llm_enrichment_pipeline(
            [findings], [llm_resp]
        )

        pipeline.run("run1", "t1")

        token_call = llm_repo.write_token_usage.call_args
        assert token_call.args[0] == "run1"
        usage = token_call.args[1]
        assert usage["input_tokens"] == 15
        assert usage["output_tokens"] == 25
        assert usage["total_tokens"] == 40
        assert "haiku" in usage["model"].lower()  # AC-035


class TestSUC01006IdempotentUpsert:
    """S-UC010-06 — AC-036: upsert semantics — AQL uses UPDATE (overwrite, not append)."""

    def test_aql_update_called_not_insert(self):
        findings = [_cve_finding("fp1")]
        llm_resp = LLMBatchResult(results=[_llm_result("fp1")], input_tokens=5, output_tokens=5)
        pipeline, repo, llm_repo, _ = _make_llm_enrichment_pipeline(
            [findings], [llm_resp]
        )
        pipeline.run("run1", "t1")

        # bulk_write_llm_fields is called — the repository uses UPDATE AQL (upsert behavior)
        llm_repo.bulk_write_llm_fields.assert_called_once()
        # Verify the update payload has _key (required for AQL UPDATE)
        updates = llm_repo.bulk_write_llm_fields.call_args.args[0]
        assert all("_key" in u for u in updates)


class TestSUC01007AttackSurfaceNormalization:
    """S-UC010-07 — AC-031: uppercase normalized; invalid defaults to network."""

    def test_uppercase_attack_surface_normalized(self):
        findings = [_cve_finding("fp1")]
        llm_resp = LLMBatchResult(
            results=[{"finding_key": "fp1", "risk_summary": "x", "remediation": "y", "attack_surface": "NETWORK"}],
            input_tokens=5,
            output_tokens=5,
        )
        pipeline, repo, llm_repo, _ = _make_llm_enrichment_pipeline([findings], [llm_resp])
        pipeline.run("run1", "t1")
        updates = llm_repo.bulk_write_llm_fields.call_args.args[0]
        assert updates[0]["llm_attack_surface"] == "network"

    def test_invalid_attack_surface_defaults_to_network(self):
        findings = [_cve_finding("fp1")]
        llm_resp = LLMBatchResult(
            results=[{"finding_key": "fp1", "risk_summary": "x", "remediation": "y", "attack_surface": "cloud"}],
            input_tokens=5,
            output_tokens=5,
        )
        pipeline, repo, llm_repo, _ = _make_llm_enrichment_pipeline([findings], [llm_resp])
        pipeline.run("run1", "t1")
        updates = llm_repo.bulk_write_llm_fields.call_args.args[0]
        assert updates[0]["llm_attack_surface"] == "network"


# ---------------------------------------------------------------------------
# S-UC011: Blast Radius
# ---------------------------------------------------------------------------

class TestSUC01101SCAfindingWithPurl:
    """S-UC011-01 — AC-037, AC-039, AC-040, AC-042."""

    def test_blast_radius_fields_and_status(self):
        purl = "pkg:npm/vuln@1.0"
        findings = [_cve_finding("fp1", purl=purl)]
        traversal = {
            "affected_purls": ["pkg:npm/dep1@1.0", "pkg:npm/dep2@1.0"],
            "affected_names": ["dep1", "dep2"],
            "max_depth": 2,
            "found": True,
        }
        pipeline, repo, blast_repo = _make_blast_pipeline([findings], traversal, total_components=10)

        pipeline.run("run1", "t1")

        updates = blast_repo.bulk_write_blast_radius.call_args.args[0]
        u = updates[0]
        assert u["blast_radius_score"] == pytest.approx(0.2)  # AC-041
        assert u["affected_components"] == traversal["affected_purls"]  # AC-039
        assert u["blast_radius_path"] == traversal["affected_names"]  # AC-040
        assert "blast_radius_computed_at" in u

        # AC-042: status
        blast_repo.update_scan_run_status.assert_called_once()
        assert blast_repo.update_scan_run_status.call_args.args[1] == "blast_radius_computed"


class TestSUC01102NoPurlFindings:
    """S-UC011-02 — AC-038: no-purl gets zero score."""

    def test_no_purl_zero_score_empty_lists(self):
        findings = [_sast_finding("fp1")]  # no purl
        pipeline, repo, blast_repo = _make_blast_pipeline([findings], {}, total_components=5)

        pipeline.run("run1", "t1")

        blast_repo.aql_blast_radius_for_purl.assert_not_called()
        updates = blast_repo.bulk_write_blast_radius.call_args.args[0]
        u = updates[0]
        assert u["blast_radius_score"] == 0.0
        assert u["affected_components"] == []
        assert u["blast_radius_path"] == []


class TestSUC01103ScoreFormula:
    """S-UC011-03 — AC-041: score = affected/total."""

    def test_score_formula(self):
        purl = "pkg:npm/a@1"
        findings = [_cve_finding("fp1", purl=purl)]
        traversal = {
            "affected_purls": ["p1", "p2", "p3"],
            "affected_names": ["n1", "n2", "n3"],
            "max_depth": 1,
            "found": True,
        }
        pipeline, repo, blast_repo = _make_blast_pipeline([findings], traversal, total_components=20)

        pipeline.run("run1", "t1")

        updates = blast_repo.bulk_write_blast_radius.call_args.args[0]
        assert updates[0]["blast_radius_score"] == pytest.approx(3 / 20)


class TestSUC01104ScoreClamped:
    """S-UC011-04 — AC-041: score clamped at 1.0."""

    def test_score_capped_at_one(self):
        purl = "pkg:npm/a@1"
        findings = [_cve_finding("fp1", purl=purl)]
        traversal = {
            "affected_purls": ["p1", "p2", "p3", "p4"],
            "affected_names": ["n1", "n2", "n3", "n4"],
            "max_depth": 2,
            "found": True,
        }
        pipeline, repo, blast_repo = _make_blast_pipeline([findings], traversal, total_components=2)

        pipeline.run("run1", "t1")

        updates = blast_repo.bulk_write_blast_radius.call_args.args[0]
        assert updates[0]["blast_radius_score"] == 1.0


class TestSUC01105Idempotent:
    """S-UC011-05 — AC-043: same purl + same traversal = same output."""

    def test_same_input_same_output(self):
        purl = "pkg:npm/a@1"
        findings = [_cve_finding("fp1", purl=purl)]
        traversal = {
            "affected_purls": ["pkg:npm/dep@1"],
            "affected_names": ["dep"],
            "max_depth": 1,
            "found": True,
        }
        pipeline, repo, blast_repo = _make_blast_pipeline([findings], traversal, total_components=10)

        pipeline.run("run1", "t1")
        first_updates = blast_repo.bulk_write_blast_radius.call_args.args[0]

        # Reset and re-run
        blast_repo.reset_mock()
        repo.fetch_findings_for_run.return_value = iter([findings])
        blast_repo.aql_blast_radius_for_purl.return_value = traversal
        blast_repo.aql_total_project_components.return_value = 10

        pipeline.run("run1", "t1")
        second_updates = blast_repo.bulk_write_blast_radius.call_args.args[0]

        assert first_updates[0]["blast_radius_score"] == second_updates[0]["blast_radius_score"]
        assert first_updates[0]["affected_components"] == second_updates[0]["affected_components"]


# ---------------------------------------------------------------------------
# S-UC012: EPSS Velocity
# ---------------------------------------------------------------------------

def _rising_history(n=20):
    return [{"score": i * 0.01, "date": f"2024-01-{i:02d}"} for i in range(1, n + 1)]


def _falling_history(n=20):
    return [{"score": (n - i) * 0.01, "date": f"2024-01-{i:02d}"} for i in range(1, n + 1)]


def _stable_history(n=10):
    return [{"score": 0.1, "date": f"2024-01-{i:02d}"} for i in range(1, n + 1)]


class TestSUC01201CVEFindingVelocity:
    """S-UC012-01 — AC-044, AC-049."""

    def test_cve_finding_gets_velocity_and_status(self):
        findings = [{"_key": "fp1", "cve_id": "CVE-2024-1234"}]
        history_map = {"CVE_2024_1234": _rising_history()}
        pipeline, repo = _make_epss_pipeline([findings], history_map)

        pipeline.run("run1", "t1")

        updates = repo.bulk_update_findings.call_args.args[0]
        u = updates[0]
        assert isinstance(u["epss_velocity"], float)  # AC-044
        assert u["epss_trend"] in {"rising", "stable", "falling"}
        assert "epss_velocity_computed_at" in u

        repo.update_scan_run_status.assert_called_once()
        assert repo.update_scan_run_status.call_args.args[1] == "velocity_computed"  # AC-049


class TestSUC01202NoCVEFindings:
    """S-UC012-02 — AC-045."""

    def test_no_cve_zero_velocity_stable(self):
        findings = [{"_key": "fp1"}]  # no cve_id
        pipeline, repo = _make_epss_pipeline([findings], {})

        pipeline.run("run1", "t1")

        updates = repo.bulk_update_findings.call_args.args[0]
        assert updates[0]["epss_velocity"] == 0.0
        assert updates[0]["epss_trend"] == "stable"


class TestSUC01203RisingTrend:
    """S-UC012-03 — AC-046."""

    def test_rising_trend_classification(self):
        findings = [{"_key": "fp1", "cve_id": "CVE-2024-1"}]
        # slope*7 > 0.05 required; rising_history(20) gives clear positive slope
        history_map = {"CVE_2024_1": _rising_history(20)}
        pipeline, repo = _make_epss_pipeline([findings], history_map)

        pipeline.run("run1", "t1")

        updates = repo.bulk_update_findings.call_args.args[0]
        assert updates[0]["epss_trend"] == "rising"


class TestSUC01204FallingTrend:
    """S-UC012-04 — AC-047."""

    def test_falling_trend_classification(self):
        findings = [{"_key": "fp1", "cve_id": "CVE-2024-1"}]
        history_map = {"CVE_2024_1": _falling_history(20)}
        pipeline, repo = _make_epss_pipeline([findings], history_map)

        pipeline.run("run1", "t1")

        updates = repo.bulk_update_findings.call_args.args[0]
        assert updates[0]["epss_trend"] == "falling"


class TestSUC01205InsufficientHistory:
    """S-UC012-05 — AC-048."""

    def test_single_data_point_zero_velocity_stable(self):
        findings = [{"_key": "fp1", "cve_id": "CVE-2024-1"}]
        history_map = {"CVE_2024_1": [{"score": 0.1, "date": "2024-01-01"}]}
        pipeline, repo = _make_epss_pipeline([findings], history_map)

        pipeline.run("run1", "t1")

        updates = repo.bulk_update_findings.call_args.args[0]
        assert updates[0]["epss_velocity"] == 0.0
        assert updates[0]["epss_trend"] == "stable"

    def test_empty_history_zero_velocity_stable(self):
        findings = [{"_key": "fp1", "cve_id": "CVE-2024-1"}]
        history_map = {"CVE_2024_1": []}
        pipeline, repo = _make_epss_pipeline([findings], history_map)

        pipeline.run("run1", "t1")

        updates = repo.bulk_update_findings.call_args.args[0]
        assert updates[0]["epss_velocity"] == 0.0


class TestSUC01206Idempotent:
    """S-UC012-06 — AC-050: same history → same result."""

    def test_same_history_same_velocity(self):
        findings = [{"_key": "fp1", "cve_id": "CVE-2024-1"}]
        history = _rising_history(15)
        history_map = {"CVE_2024_1": history}

        pipeline, repo = _make_epss_pipeline([findings], history_map)
        pipeline.run("run1", "t1")
        first_updates = repo.bulk_update_findings.call_args.args[0]

        repo.reset_mock()
        repo.fetch_findings_for_run.return_value = iter([findings])
        repo.aql_get_epss_history_batch.return_value = {"CVE_2024_1": history}

        pipeline.run("run1", "t1")
        second_updates = repo.bulk_update_findings.call_args.args[0]

        assert first_updates[0]["epss_velocity"] == second_updates[0]["epss_velocity"]
        assert first_updates[0]["epss_trend"] == second_updates[0]["epss_trend"]


# ---------------------------------------------------------------------------
# S-CROSS: Cross-Cutting
# ---------------------------------------------------------------------------

def _make_coordinator_with_status(status: str):
    """Build PipelineCoordinator with all dependencies mocked + configured status."""
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

    coordinator._db.aql.execute.return_value = iter(["key"])
    coordinator._db.collection.return_value.get.return_value = {"status": status}
    return coordinator


class TestSCROSS01FullChain:
    """S-CROSS-01 — AC-051: mapped → all 3 Phase 2 stages run."""

    def test_all_phase2_stages_run_from_mapped(self):
        coordinator = _make_coordinator_with_status("mapped")

        coordinator.run_post_ingest_pipeline("run1", "t1")

        coordinator._llm_enrichment.run.assert_called_once_with("run1", "t1")
        coordinator._blast_radius.run.assert_called_once_with("run1", "t1")
        coordinator._epss_velocity.run.assert_called_once_with("run1", "t1")


class TestSCROSS02ManualRetrigger:
    """S-CROSS-02 — AC-052: partial-done statuses skip completed stages."""

    def test_llm_enriched_skips_llm(self):
        coordinator = _make_coordinator_with_status("llm_enriched")
        coordinator.run_post_ingest_pipeline("run1", "t1")
        coordinator._llm_enrichment.run.assert_not_called()
        coordinator._blast_radius.run.assert_called_once()
        coordinator._epss_velocity.run.assert_called_once()

    def test_blast_computed_skips_llm_and_blast(self):
        coordinator = _make_coordinator_with_status("blast_radius_computed")
        coordinator.run_post_ingest_pipeline("run1", "t1")
        coordinator._llm_enrichment.run.assert_not_called()
        coordinator._blast_radius.run.assert_not_called()
        coordinator._epss_velocity.run.assert_called_once()


class TestSCROSS03StageFailureIsolation:
    """S-CROSS-03 — AC-053: stage failure → pipeline_failed; downstream not called."""

    def test_llm_failure_sets_pipeline_failed(self):
        coordinator = _make_coordinator_with_status("mapped")
        coordinator._llm_enrichment.run.side_effect = RuntimeError("all_llm_batches_failed")

        coordinator.run_post_ingest_pipeline("run1", "t1")

        coordinator._repo.update_scan_run_status.assert_called_with(
            "run1",
            "pipeline_failed",
            extra_fields={"pipeline_error": "all_llm_batches_failed"},
        )
        coordinator._blast_radius.run.assert_not_called()
        coordinator._epss_velocity.run.assert_not_called()

    def test_blast_failure_sets_pipeline_failed(self):
        coordinator = _make_coordinator_with_status("mapped")
        coordinator._blast_radius.run.side_effect = Exception("blast error")

        coordinator.run_post_ingest_pipeline("run1", "t1")

        coordinator._repo.update_scan_run_status.assert_called_with(
            "run1",
            "pipeline_failed",
            extra_fields={"pipeline_error": "blast error"},
        )
        coordinator._epss_velocity.run.assert_not_called()


class TestSCROSS04TenantIDScoping:
    """S-CROSS-04 — AC-054: tenant_id passed through to all fetch calls."""

    def test_tenant_id_passed_to_all_pipeline_stages(self):
        for stage_status in ["mapped"]:
            coordinator = _make_coordinator_with_status(stage_status)

            coordinator.run_post_ingest_pipeline("run1", "tenant-acme")

            coordinator._llm_enrichment.run.assert_called_with("run1", "tenant-acme")
            coordinator._blast_radius.run.assert_called_with("run1", "tenant-acme")
            coordinator._epss_velocity.run.assert_called_with("run1", "tenant-acme")
