"""
PipelineLLMClient — sync Anthropic Claude wrapper for the ingestion pipeline.

Responsibilities:
- Accept a batch of finding dicts (up to 10 per call)
- Build a structured JSON prompt and call the Claude Haiku API synchronously
- Parse the JSON response and return per-finding enrichment dicts

Design contract:
- Uses anthropic.Anthropic() sync client — no async, no Redis, no ClaudeLLMService dependency
- Raises anthropic.APIError or json.JSONDecodeError on failure; caller decides skip vs fail
- Token usage is returned in LLMBatchResult for aggregate logging by the pipeline stage
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import NamedTuple

import anthropic

log = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
_DEFAULT_MAX_TOKENS = 2048
_VALID_ATTACK_SURFACES = frozenset({"network", "local", "adjacent"})


class LLMBatchResult(NamedTuple):
    results: list[dict]      # Per-finding enrichment dicts (may contain empty dicts for failed entries)
    input_tokens: int        # Anthropic input token count for billing log
    output_tokens: int       # Anthropic output token count for billing log


class PipelineLLMClient:
    """
    Thin sync wrapper around anthropic.Anthropic().messages.create().

    Accepts a batch of finding dicts, builds a structured JSON prompt, calls
    the Claude Haiku API, and returns a LLMBatchResult with per-finding
    enrichment dicts plus aggregate token usage.
    """

    def __init__(
        self,
        model: str | None = None,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
        api_key: str | None = None,
    ) -> None:
        self._model = model or os.environ.get("ANTHROPIC_MODEL_HAIKU", _DEFAULT_MODEL)
        self._max_tokens = max_tokens
        self._client = anthropic.Anthropic(api_key=api_key)

    def call_batch(self, findings: list[dict]) -> LLMBatchResult:
        """
        Enrich a batch of findings (max 10) via the Claude API.

        Each finding dict must contain: _key (str), and any subset of
        cve_id, rule_id, severity, package_name, cvss_base.

        Returns LLMBatchResult with results list matching input order.
        Raises anthropic.APIError or json.JSONDecodeError on failure.
        """
        if not findings:
            return LLMBatchResult(results=[], input_tokens=0, output_tokens=0)

        finding_keys = [f["_key"] for f in findings]
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(findings)

        log.debug(
            "pipeline_llm_client.call_batch",
            extra={"model": self._model, "batch_size": len(findings)},
        )

        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        raw_text = response.content[0].text
        results = self._parse_response(raw_text, finding_keys)

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens

        log.debug(
            "pipeline_llm_client.call_batch_complete",
            extra={
                "batch_size": len(findings),
                "results_count": len(results),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            },
        )

        return LLMBatchResult(
            results=results,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        return (
            "You are a cybersecurity analyst. For each finding provided, return a JSON array.\n"
            "Each element must have:\n"
            '  "finding_key": string (exact value from input)\n'
            '  "risk_summary": string (<=3 sentences, plain language risk description)\n'
            '  "remediation": string (1-3 concrete remediation steps)\n'
            '  "attack_surface": one of ["network", "local", "adjacent"]\n\n'
            "Return ONLY valid JSON. No markdown. No explanations outside the JSON array."
        )

    def _build_user_prompt(self, findings: list[dict]) -> str:
        lines = []
        for f in findings:
            entry: dict = {"finding_key": f["_key"]}
            if f.get("cve_id"):
                entry["cve_id"] = f["cve_id"]
            if f.get("rule_id"):
                entry["rule_id"] = f["rule_id"]
            if f.get("severity"):
                entry["severity"] = f["severity"]
            if f.get("package_name"):
                entry["package_name"] = f["package_name"]
            if f.get("cvss_base") is not None:
                entry["cvss_base"] = f["cvss_base"]
            lines.append(json.dumps(entry, separators=(",", ":")))

        return "Analyze the following security findings:\n[\n" + ",\n".join(lines) + "\n]"

    def _parse_response(self, raw_text: str, finding_keys: list[str]) -> list[dict]:
        """
        Parse the Claude response into a list of enrichment dicts ordered by finding_keys.

        Attempts direct json.loads first; falls back to extracting from a markdown code block.
        Missing or unparseable entries yield empty dicts for that position.
        """
        text = raw_text.strip()

        # Try direct parse
        parsed = None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # Fall back: extract from ```json ... ``` or ``` ... ``` block
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
            if match:
                try:
                    parsed = json.loads(match.group(1).strip())
                except json.JSONDecodeError:
                    pass

        if parsed is None:
            log.error(
                "pipeline_llm_client.parse_response_failed",
                extra={"raw_length": len(raw_text)},
            )
            raise json.JSONDecodeError("Cannot parse LLM response as JSON", raw_text, 0)

        if not isinstance(parsed, list):
            log.error(
                "pipeline_llm_client.parse_response_not_list",
                extra={"type": type(parsed).__name__},
            )
            raise json.JSONDecodeError("LLM response is not a JSON array", raw_text, 0)

        # Build keyed lookup
        by_key: dict[str, dict] = {}
        for item in parsed:
            if isinstance(item, dict) and "finding_key" in item:
                by_key[item["finding_key"]] = item

        # Return in input order; missing entries become empty dicts
        results = []
        for key in finding_keys:
            entry = by_key.get(key, {})
            # Normalize attack_surface
            surface = entry.get("attack_surface", "")
            if isinstance(surface, str):
                surface = surface.lower()
            if surface not in _VALID_ATTACK_SURFACES:
                surface = "network"
            if entry:
                entry = {**entry, "attack_surface": surface}
            results.append(entry)

        return results
