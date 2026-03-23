"""
Unit tests for pipeline_llm_client.py

Covers:
- call_batch: success, non-CVE finding, API error, malformed JSON, code-block fallback
- _parse_response: missing key, attack_surface normalization
- Token usage returned correctly
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from complira_graph.ingestion.pipeline_llm_client import LLMBatchResult, PipelineLLMClient


def _make_client() -> PipelineLLMClient:
    with patch("complira_graph.ingestion.pipeline_llm_client.anthropic.Anthropic"):
        client = PipelineLLMClient(api_key="test-key")
    return client


def _mock_response(text: str, input_tokens: int = 10, output_tokens: int = 20) -> MagicMock:
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    resp.usage = MagicMock(input_tokens=input_tokens, output_tokens=output_tokens)
    return resp


# ---------------------------------------------------------------------------
# call_batch — success
# ---------------------------------------------------------------------------

class TestCallBatchSuccess:
    def test_returns_llm_batch_result(self):
        client = _make_client()
        findings = [
            {"_key": "fp1", "cve_id": "CVE-2024-1234", "severity": "HIGH", "package_name": "log4j", "cvss_base": 9.8},
        ]
        payload = json.dumps([
            {"finding_key": "fp1", "risk_summary": "RCE risk.", "remediation": "Patch now.", "attack_surface": "network"}
        ])
        client._client.messages.create.return_value = _mock_response(payload, 15, 25)

        result = client.call_batch(findings)

        assert isinstance(result, LLMBatchResult)
        assert len(result.results) == 1
        assert result.results[0]["risk_summary"] == "RCE risk."
        assert result.results[0]["attack_surface"] == "network"
        assert result.input_tokens == 15
        assert result.output_tokens == 25

    def test_empty_findings_returns_empty(self):
        client = _make_client()
        result = client.call_batch([])
        assert result.results == []
        assert result.input_tokens == 0
        client._client.messages.create.assert_not_called()

    def test_uses_haiku_model(self):
        client = _make_client()
        findings = [{"_key": "fp1", "severity": "LOW"}]
        payload = json.dumps([{"finding_key": "fp1", "risk_summary": "x", "remediation": "y", "attack_surface": "local"}])
        client._client.messages.create.return_value = _mock_response(payload)

        client.call_batch(findings)

        call_kwargs = client._client.messages.create.call_args
        assert "haiku" in call_kwargs.kwargs.get("model", call_kwargs.args[0] if call_kwargs.args else "").lower()


# ---------------------------------------------------------------------------
# call_batch — non-CVE finding (rule_id fallback)
# ---------------------------------------------------------------------------

class TestNonCveFinding:
    def test_rule_id_included_in_prompt(self):
        client = _make_client()
        findings = [{"_key": "fp2", "rule_id": "semgrep.sql-injection", "severity": "MEDIUM"}]
        payload = json.dumps([{"finding_key": "fp2", "risk_summary": "SQL.", "remediation": "Sanitize.", "attack_surface": "network"}])
        client._client.messages.create.return_value = _mock_response(payload)

        result = client.call_batch(findings)

        # Verify the user prompt included rule_id
        call_kwargs = client._client.messages.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs.args[0]
        user_content = messages[0]["content"] if isinstance(messages, list) else str(messages)
        assert "sql-injection" in user_content
        assert len(result.results) == 1

    def test_cve_id_absent_from_prompt_when_none(self):
        client = _make_client()
        findings = [{"_key": "fp3", "severity": "HIGH"}]  # no cve_id, no rule_id
        payload = json.dumps([{"finding_key": "fp3", "risk_summary": "x", "remediation": "y", "attack_surface": "local"}])
        client._client.messages.create.return_value = _mock_response(payload)

        client.call_batch(findings)

        call_kwargs = client._client.messages.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs.args[0]
        user_content = messages[0]["content"]
        assert "cve_id" not in user_content


# ---------------------------------------------------------------------------
# call_batch — error handling
# ---------------------------------------------------------------------------

class TestCallBatchErrors:
    def test_api_error_reraises(self):
        import anthropic as _anthropic
        client = _make_client()
        findings = [{"_key": "fp1", "severity": "HIGH"}]
        client._client.messages.create.side_effect = _anthropic.APIError(
            message="rate limit", request=MagicMock(), body={}
        )

        with pytest.raises(_anthropic.APIError):
            client.call_batch(findings)

    def test_malformed_json_raises_json_decode_error(self):
        client = _make_client()
        findings = [{"_key": "fp1", "severity": "HIGH"}]
        client._client.messages.create.return_value = _mock_response("not valid json at all")

        with pytest.raises(Exception):
            client.call_batch(findings)


# ---------------------------------------------------------------------------
# _parse_response — edge cases
# ---------------------------------------------------------------------------

class TestParseResponse:
    def test_missing_finding_key_yields_empty_dict(self):
        client = _make_client()
        # Response only has fp1, fp2 is missing
        raw = json.dumps([
            {"finding_key": "fp1", "risk_summary": "x", "remediation": "y", "attack_surface": "network"}
        ])
        results = client._parse_response(raw, ["fp1", "fp2"])
        assert len(results) == 2
        assert results[0]["risk_summary"] == "x"
        assert results[1] == {}

    def test_code_block_fallback(self):
        client = _make_client()
        raw = '```json\n[{"finding_key": "fp1", "risk_summary": "r", "remediation": "rem", "attack_surface": "local"}]\n```'
        results = client._parse_response(raw, ["fp1"])
        assert results[0]["risk_summary"] == "r"
        assert results[0]["attack_surface"] == "local"

    def test_attack_surface_uppercase_normalized(self):
        client = _make_client()
        raw = json.dumps([{"finding_key": "fp1", "risk_summary": "x", "remediation": "y", "attack_surface": "NETWORK"}])
        results = client._parse_response(raw, ["fp1"])
        assert results[0]["attack_surface"] == "network"

    def test_attack_surface_invalid_defaults_to_network(self):
        client = _make_client()
        raw = json.dumps([{"finding_key": "fp1", "risk_summary": "x", "remediation": "y", "attack_surface": "physical"}])
        results = client._parse_response(raw, ["fp1"])
        assert results[0]["attack_surface"] == "network"

    def test_attack_surface_adjacent(self):
        client = _make_client()
        raw = json.dumps([{"finding_key": "fp1", "risk_summary": "x", "remediation": "y", "attack_surface": "adjacent"}])
        results = client._parse_response(raw, ["fp1"])
        assert results[0]["attack_surface"] == "adjacent"
