"""
Unit tests for llm_enrichment_pipeline.py

Covers:
- run: happy path writes findings + token usage + status
- run: partial batch failure continues; all batches fail raises RuntimeError
- run: empty scan (no findings) skips LLM + still writes status
- _context_for_finding: CVE path, non-CVE path, missing optional fields
- _build_llm_updates: non-empty result, empty result fallback, attack_surface normalization
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from complira_graph.ingestion.llm_enrichment_pipeline import LLMEnrichmentPipeline
from complira_graph.ingestion.pipeline_llm_client import LLMBatchResult
from complira_graph.ingestion.scan_enrichment_repository import ScanEnrichmentRepository
from complira_graph.ingestion.scan_llm_enrichment_repository import ScanLLMEnrichmentRepository


def _make_pipeline():
    db = MagicMock()
    repo = MagicMock(spec=ScanEnrichmentRepository)
    llm_repo = MagicMock(spec=ScanLLMEnrichmentRepository)
    llm_client = MagicMock()
    llm_client._model = "claude-haiku-4-5"
    pipeline = LLMEnrichmentPipeline(db, repo, llm_repo, llm_client)
    return pipeline, repo, llm_repo, llm_client


def _finding(key: str, **kwargs) -> dict:
    base = {"_key": key, "severity": "HIGH"}
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# run — happy path
# ---------------------------------------------------------------------------

class TestRunHappyPath:
    def test_writes_findings_and_status(self):
        pipeline, repo, llm_repo, llm_client = _make_pipeline()
        findings = [_finding("fp1", cve_id="CVE-2024-1", package_name="log4j", cvss_base=9.8)]
        repo.fetch_findings_for_run.return_value = iter([findings])
        llm_client.call_batch.return_value = LLMBatchResult(
            results=[{"finding_key": "fp1", "risk_summary": "RCE risk.", "remediation": "Patch.", "attack_surface": "network"}],
            input_tokens=10,
            output_tokens=20,
        )

        pipeline.run("run1", "t1")

        llm_repo.bulk_write_llm_fields.assert_called_once()
        updates = llm_repo.bulk_write_llm_fields.call_args.args[0]
        assert updates[0]["_key"] == "fp1"
        assert updates[0]["llm_risk_summary"] == "RCE risk."
        assert updates[0]["llm_attack_surface"] == "network"

        llm_repo.write_token_usage.assert_called_once()
        token_call = llm_repo.write_token_usage.call_args.args
        assert token_call[0] == "run1"
        assert token_call[1]["input_tokens"] == 10
        assert token_call[1]["total_tokens"] == 30

        llm_repo.update_scan_run_status.assert_called_once()
        status_call = llm_repo.update_scan_run_status.call_args
        assert status_call.args[1] == "llm_enriched"

    def test_token_counts_accumulated_across_batches(self):
        pipeline, repo, llm_repo, llm_client = _make_pipeline()
        # Two batches of 1 each
        repo.fetch_findings_for_run.return_value = iter([
            [_finding("fp1")],
            [_finding("fp2")],
        ])
        llm_client.call_batch.return_value = LLMBatchResult(
            results=[{"finding_key": "fp1", "risk_summary": "r", "remediation": "rem", "attack_surface": "local"}],
            input_tokens=5,
            output_tokens=5,
        )

        pipeline.run("run1", "t1")

        token_call = llm_repo.write_token_usage.call_args.args[1]
        assert token_call["total_tokens"] == 20  # 5+5 per batch, 2 batches


# ---------------------------------------------------------------------------
# run — error handling
# ---------------------------------------------------------------------------

class TestRunErrors:
    def test_all_batches_fail_raises_runtime_error(self):
        pipeline, repo, llm_repo, llm_client = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([[_finding("fp1")]])
        llm_client.call_batch.side_effect = Exception("API down")

        with pytest.raises(RuntimeError, match="all_llm_batches_failed"):
            pipeline.run("run1", "t1")

        llm_repo.update_scan_run_status.assert_not_called()

    def test_partial_batch_failure_continues(self):
        pipeline, repo, llm_repo, llm_client = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([
            [_finding("fp1")],
            [_finding("fp2")],
        ])
        # First call fails, second succeeds
        llm_client.call_batch.side_effect = [
            Exception("API error"),
            LLMBatchResult(
                results=[{"finding_key": "fp2", "risk_summary": "ok", "remediation": "ok", "attack_surface": "local"}],
                input_tokens=5,
                output_tokens=5,
            ),
        ]

        pipeline.run("run1", "t1")  # must not raise

        # Only second batch wrote
        assert llm_repo.bulk_write_llm_fields.call_count == 1
        llm_repo.update_scan_run_status.assert_called_once()

    def test_no_findings_writes_zero_tokens_and_status(self):
        pipeline, repo, llm_repo, llm_client = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([[]])

        pipeline.run("run1", "t1")

        llm_client.call_batch.assert_not_called()
        llm_repo.write_token_usage.assert_called_once()
        token_payload = llm_repo.write_token_usage.call_args.args[1]
        assert token_payload["total_tokens"] == 0
        llm_repo.update_scan_run_status.assert_called_once()


# ---------------------------------------------------------------------------
# _context_for_finding
# ---------------------------------------------------------------------------

class TestContextForFinding:
    def test_cve_finding_includes_cve_fields(self):
        pipeline, *_ = _make_pipeline()
        f = _finding("fp1", cve_id="CVE-2024-1", package_name="log4j", cvss_base=9.8)
        ctx = pipeline._context_for_finding(f)
        assert ctx["cve_id"] == "CVE-2024-1"
        assert ctx["package_name"] == "log4j"
        assert ctx["cvss_base"] == 9.8
        assert "rule_id" not in ctx

    def test_non_cve_finding_includes_rule_id(self):
        pipeline, *_ = _make_pipeline()
        f = _finding("fp2", rule_id="semgrep.sql-injection")
        ctx = pipeline._context_for_finding(f)
        assert ctx["rule_id"] == "semgrep.sql-injection"
        assert "cve_id" not in ctx

    def test_missing_optional_fields_omitted(self):
        pipeline, *_ = _make_pipeline()
        f = {"_key": "fp3", "severity": "LOW"}
        ctx = pipeline._context_for_finding(f)
        assert ctx["_key"] == "fp3"
        assert "cve_id" not in ctx
        assert "package_name" not in ctx
        assert "cvss_base" not in ctx


# ---------------------------------------------------------------------------
# _build_llm_updates
# ---------------------------------------------------------------------------

class TestBuildLLMUpdates:
    def test_full_result_written(self):
        pipeline, *_ = _make_pipeline()
        findings = [_finding("fp1")]
        llm_results = [{"risk_summary": "RCE", "remediation": "Patch", "attack_surface": "network"}]
        updates = pipeline._build_llm_updates(findings, llm_results)
        assert updates[0]["llm_risk_summary"] == "RCE"
        assert updates[0]["llm_attack_surface"] == "network"
        assert "llm_enriched_at" in updates[0]

    def test_empty_result_writes_only_timestamp(self):
        pipeline, *_ = _make_pipeline()
        findings = [_finding("fp1")]
        llm_results = [{}]
        updates = pipeline._build_llm_updates(findings, llm_results)
        assert set(updates[0].keys()) == {"_key", "llm_enriched_at"}

    def test_attack_surface_uppercase_normalized(self):
        pipeline, *_ = _make_pipeline()
        findings = [_finding("fp1")]
        llm_results = [{"risk_summary": "x", "remediation": "y", "attack_surface": "NETWORK"}]
        updates = pipeline._build_llm_updates(findings, llm_results)
        assert updates[0]["llm_attack_surface"] == "network"

    def test_invalid_attack_surface_defaults_to_network(self):
        pipeline, *_ = _make_pipeline()
        findings = [_finding("fp1")]
        llm_results = [{"risk_summary": "x", "remediation": "y", "attack_surface": "physical"}]
        updates = pipeline._build_llm_updates(findings, llm_results)
        assert updates[0]["llm_attack_surface"] == "network"
