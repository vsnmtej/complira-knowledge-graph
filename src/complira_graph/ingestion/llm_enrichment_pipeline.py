"""
LLMEnrichmentPipeline — UC-010 LLM Enrichment stage.

For each scan_findings document in a scan run, calls the Claude Haiku API in
batches of 10 findings per prompt to generate:
  - llm_risk_summary  (<=3 sentence plain-language risk description)
  - llm_remediation   (1-3 actionable remediation steps)
  - llm_attack_surface ∈ {network, local, adjacent}
  - llm_enriched_at   (ISO 8601 UTC timestamp)

Also writes aggregate token usage to scan_runs.llm_token_usage.

Status transition: mapped → llm_enriched

Error handling:
  - Per-batch LLM failure: log and skip that batch; continue (partial writes retained)
  - All batches fail: raise RuntimeError("all_llm_batches_failed") — coordinator sets pipeline_failed
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from arango.database import StandardDatabase

from complira_graph.ingestion.pipeline_llm_client import PipelineLLMClient, _VALID_ATTACK_SURFACES
from complira_graph.ingestion.scan_enrichment_repository import ScanEnrichmentRepository
from complira_graph.ingestion.scan_llm_enrichment_repository import ScanLLMEnrichmentRepository

log = logging.getLogger(__name__)

_LLM_SUB_BATCH_SIZE = 10


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class LLMEnrichmentPipeline:
    """
    UC-010: LLM enrichment stage.

    Reads findings via ScanEnrichmentRepository, enriches via PipelineLLMClient,
    writes results via ScanLLMEnrichmentRepository. Holds zero LLM API calls directly.
    """

    def __init__(
        self,
        db: StandardDatabase,
        repo: ScanEnrichmentRepository,
        llm_repo: ScanLLMEnrichmentRepository,
        llm_client: PipelineLLMClient,
    ) -> None:
        self._db = db
        self._repo = repo
        self._llm_repo = llm_repo
        self._llm_client = llm_client

    def run(self, scan_run_id: str, tenant_id: str) -> None:
        """
        Enrich all findings for scan_run_id with LLM-generated fields.

        Trigger: scan_run.status == "mapped"
        Result:  scan_run.status = "llm_enriched" on success
                 raises RuntimeError("all_llm_batches_failed") if every sub-batch fails
        """
        log.info(
            "llm_enrichment_pipeline.start",
            extra={"scan_run_id": scan_run_id, "tenant_id": tenant_id},
        )

        total_input_tokens = 0
        total_output_tokens = 0
        llm_failure_count = 0
        total_sub_batches = 0

        for batch in self._repo.fetch_findings_for_run(scan_run_id, tenant_id):
            for i in range(0, len(batch), _LLM_SUB_BATCH_SIZE):
                sub_batch = batch[i : i + _LLM_SUB_BATCH_SIZE]
                total_sub_batches += 1
                context_batch = [self._context_for_finding(f) for f in sub_batch]

                try:
                    result = self._llm_client.call_batch(context_batch)
                except Exception:
                    log.warning(
                        "llm_enrichment_pipeline.batch_failed",
                        extra={
                            "scan_run_id": scan_run_id,
                            "batch_index": total_sub_batches,
                            "batch_size": len(sub_batch),
                        },
                    )
                    llm_failure_count += 1
                    continue

                updates = self._build_llm_updates(sub_batch, result.results)
                self._llm_repo.bulk_write_llm_fields(updates)
                total_input_tokens += result.input_tokens
                total_output_tokens += result.output_tokens

        if total_sub_batches > 0 and llm_failure_count == total_sub_batches:
            log.error(
                "llm_enrichment_pipeline.all_batches_failed",
                extra={"scan_run_id": scan_run_id, "total_sub_batches": total_sub_batches},
            )
            raise RuntimeError("all_llm_batches_failed")

        self._llm_repo.write_token_usage(
            scan_run_id,
            {
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "total_tokens": total_input_tokens + total_output_tokens,
                "model": self._llm_client._model,
            },
        )
        self._llm_repo.update_scan_run_status(
            scan_run_id,
            "llm_enriched",
            extra_fields={"llm_enriched_at": _utcnow()},
        )
        log.info(
            "llm_enrichment_pipeline.complete",
            extra={
                "scan_run_id": scan_run_id,
                "total_sub_batches": total_sub_batches,
                "llm_failure_count": llm_failure_count,
                "total_tokens": total_input_tokens + total_output_tokens,
            },
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _context_for_finding(self, finding: dict) -> dict:
        """
        Build compact context dict for LLM prompt from a finding document.

        CVE findings: include cve_id, severity, package_name, cvss_base.
        Non-CVE findings: include rule_id, severity (no cve_id).
        """
        entry: dict = {"_key": finding["_key"]}
        if finding.get("cve_id"):
            entry["cve_id"] = finding["cve_id"]
        if finding.get("rule_id"):
            entry["rule_id"] = finding["rule_id"]
        if finding.get("severity"):
            entry["severity"] = finding["severity"]
        if finding.get("package_name"):
            entry["package_name"] = finding["package_name"]
        if finding.get("cvss_base") is not None:
            entry["cvss_base"] = finding["cvss_base"]
        return entry

    def _build_llm_updates(
        self,
        findings: list[dict],
        llm_results: list[dict],
    ) -> list[dict]:
        """
        Merge LLM results with finding _keys into update dicts for bulk write.

        For findings where the LLM result is empty (parse failure or skipped entry):
        writes only llm_enriched_at to mark the attempt without overwriting with nulls.
        attack_surface is normalized to lowercase; defaults to "network" if invalid.
        """
        now = _utcnow()
        updates = []
        for finding, llm_result in zip(findings, llm_results):
            key = finding["_key"]
            if llm_result:
                surface = llm_result.get("attack_surface", "")
                if isinstance(surface, str):
                    surface = surface.lower()
                if surface not in _VALID_ATTACK_SURFACES:
                    surface = "network"
                updates.append(
                    {
                        "_key": key,
                        "llm_risk_summary": llm_result.get("risk_summary", ""),
                        "llm_remediation": llm_result.get("remediation", ""),
                        "llm_attack_surface": surface,
                        "llm_enriched_at": now,
                    }
                )
            else:
                updates.append({"_key": key, "llm_enriched_at": now})
        return updates
