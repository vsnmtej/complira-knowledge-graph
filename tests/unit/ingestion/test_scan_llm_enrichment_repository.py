"""
Unit tests for scan_llm_enrichment_repository.py

Covers:
- bulk_write_llm_fields: empty input skips AQL, single chunk, multi-chunk at boundary
- write_token_usage: collection update called with correct payload
- update_scan_run_status: status and extra fields merged correctly
"""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from complira_graph.ingestion.scan_llm_enrichment_repository import (
    ScanLLMEnrichmentRepository,
    _CHUNK_SIZE,
)


def _make_repo() -> tuple[ScanLLMEnrichmentRepository, MagicMock]:
    db = MagicMock()
    repo = ScanLLMEnrichmentRepository(db)
    return repo, db


# ---------------------------------------------------------------------------
# bulk_write_llm_fields
# ---------------------------------------------------------------------------

class TestBulkWriteLLMFields:
    def test_empty_updates_skips_aql(self):
        repo, db = _make_repo()
        repo.bulk_write_llm_fields([])
        db.aql.execute.assert_not_called()

    def test_single_chunk_executes_once(self):
        repo, db = _make_repo()
        updates = [{"_key": f"fp{i}", "llm_risk_summary": "x"} for i in range(3)]
        repo.bulk_write_llm_fields(updates)
        assert db.aql.execute.call_count == 1
        call_kwargs = db.aql.execute.call_args
        bind_vars = call_kwargs.kwargs.get("bind_vars") or call_kwargs.args[1]
        assert bind_vars["updates"] == updates

    def test_multi_chunk_executes_per_chunk(self):
        repo, db = _make_repo()
        # _CHUNK_SIZE + 1 items → 2 chunks
        updates = [{"_key": f"fp{i}"} for i in range(_CHUNK_SIZE + 1)]
        repo.bulk_write_llm_fields(updates)
        assert db.aql.execute.call_count == 2
        first_call = db.aql.execute.call_args_list[0]
        second_call = db.aql.execute.call_args_list[1]
        first_bind = first_call.kwargs.get("bind_vars") or first_call.args[1]
        second_bind = second_call.kwargs.get("bind_vars") or second_call.args[1]
        assert len(first_bind["updates"]) == _CHUNK_SIZE
        assert len(second_bind["updates"]) == 1

    def test_aql_uses_keepnull_false(self):
        repo, db = _make_repo()
        repo.bulk_write_llm_fields([{"_key": "fp1"}])
        aql_text = db.aql.execute.call_args.args[0]
        assert "keepNull: false" in aql_text

    def test_exact_chunk_boundary_single_call(self):
        repo, db = _make_repo()
        updates = [{"_key": f"fp{i}"} for i in range(_CHUNK_SIZE)]
        repo.bulk_write_llm_fields(updates)
        assert db.aql.execute.call_count == 1


# ---------------------------------------------------------------------------
# write_token_usage
# ---------------------------------------------------------------------------

class TestWriteTokenUsage:
    def test_updates_scan_runs_collection(self):
        repo, db = _make_repo()
        usage = {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30, "model": "haiku"}
        repo.write_token_usage("run1", usage)
        db.collection.assert_called_with("scan_runs")
        update_payload = db.collection.return_value.update.call_args.args[0]
        assert update_payload["_key"] == "run1"
        assert update_payload["llm_token_usage"] == usage
        assert "updated_at" in update_payload

    def test_empty_token_usage_still_writes(self):
        repo, db = _make_repo()
        repo.write_token_usage("run2", {})
        db.collection.return_value.update.assert_called_once()


# ---------------------------------------------------------------------------
# update_scan_run_status
# ---------------------------------------------------------------------------

class TestUpdateScanRunStatus:
    def test_status_written(self):
        repo, db = _make_repo()
        repo.update_scan_run_status("run1", "llm_enriched")
        payload = db.collection.return_value.update.call_args.args[0]
        assert payload["_key"] == "run1"
        assert payload["status"] == "llm_enriched"
        assert "updated_at" in payload

    def test_extra_fields_merged(self):
        repo, db = _make_repo()
        repo.update_scan_run_status("run1", "llm_enriched", extra_fields={"llm_enriched_at": "2026-01-01T00:00:00+00:00"})
        payload = db.collection.return_value.update.call_args.args[0]
        assert payload["llm_enriched_at"] == "2026-01-01T00:00:00+00:00"

    def test_no_extra_fields_omits_extra(self):
        repo, db = _make_repo()
        repo.update_scan_run_status("run1", "llm_enriched")
        payload = db.collection.return_value.update.call_args.args[0]
        assert set(payload.keys()) == {"_key", "status", "updated_at"}
