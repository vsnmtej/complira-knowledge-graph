"""
ScanLLMEnrichmentRepository — writes LLM-generated fields to scan_findings and scan_runs.

Responsibilities:
- Bulk-update scan_findings with llm_risk_summary, llm_remediation, llm_attack_surface,
  llm_enriched_at
- Write aggregate token usage to scan_runs.llm_token_usage
- Update scan_run status to "llm_enriched"

Design contract:
- All writes use OPTIONS {keepNull: false} to avoid overwriting existing values with null
- Chunks at 500 items per AQL call (same as Phase 1 ScanEnrichmentRepository pattern)
- No AQL reads — this repository is write-only
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from arango.database import StandardDatabase

log = logging.getLogger(__name__)

_CHUNK_SIZE = 500


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class ScanLLMEnrichmentRepository:
    """
    Write-only repository for LLM enrichment fields.

    Injected into LLMEnrichmentPipeline via PipelineCoordinator.__init__.
    """

    def __init__(self, db: StandardDatabase) -> None:
        self._db = db

    def bulk_write_llm_fields(self, updates: list[dict]) -> None:
        """
        Bulk-update scan_findings with LLM-generated fields.

        Each dict must have '_key' plus any subset of:
        llm_risk_summary, llm_remediation, llm_attack_surface, llm_enriched_at.

        Chunks internally at 500 items per AQL call.
        OPTIONS {keepNull: false} ensures null values do not overwrite existing data.
        """
        if not updates:
            return
        total = 0
        chunks = 0
        for i in range(0, len(updates), _CHUNK_SIZE):
            chunk = updates[i : i + _CHUNK_SIZE]
            self._db.aql.execute(
                """
                FOR u IN @updates
                    UPDATE u._key WITH u IN scan_findings
                    OPTIONS {keepNull: false}
                """,
                bind_vars={"updates": chunk},
            )
            total += len(chunk)
            chunks += 1
        log.info(
            "scan_llm_enrichment_repo.bulk_write_llm_fields",
            extra={"total": total, "chunks": chunks},
        )

    def write_token_usage(self, scan_run_id: str, token_usage: dict) -> None:
        """
        Write aggregate LLM token usage to scan_runs document.

        token_usage dict is expected to have keys:
        input_tokens (int), output_tokens (int), total_tokens (int), model (str).
        """
        self._db.collection("scan_runs").update(
            {
                "_key": scan_run_id,
                "llm_token_usage": token_usage,
                "updated_at": _utcnow(),
            }
        )
        log.info(
            "scan_llm_enrichment_repo.write_token_usage",
            extra={
                "scan_run_id": scan_run_id,
                "total_tokens": token_usage.get("total_tokens", 0),
            },
        )

    def update_scan_run_status(
        self,
        scan_run_key: str,
        status: str,
        extra_fields: Optional[dict] = None,
    ) -> None:
        """Update scan_runs status plus optional extra fields."""
        payload: dict = {"_key": scan_run_key, "status": status, "updated_at": _utcnow()}
        if extra_fields:
            payload.update(extra_fields)
        self._db.collection("scan_runs").update(payload)
        log.info(
            "scan_llm_enrichment_repo.update_scan_run_status",
            extra={"scan_run_id": scan_run_key, "status": status},
        )
