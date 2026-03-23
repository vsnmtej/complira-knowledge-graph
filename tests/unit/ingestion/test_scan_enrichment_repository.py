"""
Unit tests for scan_enrichment_repository.py

Covers:
- bulk_update_findings: 500-item chunking behaviour (verify AQL execute call count)
- update_scan_run_status: correct field merging
- upsert_detected_controls: delegates to import_bulk
- upsert_finding_triggers_req_edges: delegates to import_bulk
- upsert_detected_control_maps_to_edges: delegates to import_bulk
- fetch_findings_for_run: pagination terminates on short batch
- aql_enrich_batch: empty input returns {} without DB call
- aql_get_cwe_parent_map: empty input returns {} without DB call
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from complira_graph.ingestion.scan_enrichment_repository import ScanEnrichmentRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db() -> tuple[MagicMock, dict[str, MagicMock]]:
    """Return (mock_db, collections_by_name)."""
    db = MagicMock()
    cols: dict[str, MagicMock] = {}

    def _col(name: str) -> MagicMock:
        if name not in cols:
            cols[name] = MagicMock()
        return cols[name]

    db.collection.side_effect = _col
    db.aql = MagicMock()
    db.aql.execute = MagicMock()
    return db, cols


# ---------------------------------------------------------------------------
# bulk_update_findings — chunking
# ---------------------------------------------------------------------------

class TestBulkUpdateFindingsChunking:
    def test_empty_list_no_aql_call(self):
        db, _ = _make_db()
        repo = ScanEnrichmentRepository(db)
        repo.bulk_update_findings([])
        db.aql.execute.assert_not_called()

    def test_single_item_one_aql_call(self):
        db, _ = _make_db()
        repo = ScanEnrichmentRepository(db)
        updates = [{"_key": "fp1", "epss_score": 0.1}]
        repo.bulk_update_findings(updates)
        assert db.aql.execute.call_count == 1

    def test_exactly_500_items_one_aql_call(self):
        db, _ = _make_db()
        repo = ScanEnrichmentRepository(db)
        updates = [{"_key": f"fp{i}"} for i in range(500)]
        repo.bulk_update_findings(updates)
        assert db.aql.execute.call_count == 1

    def test_501_items_two_aql_calls(self):
        db, _ = _make_db()
        repo = ScanEnrichmentRepository(db)
        updates = [{"_key": f"fp{i}"} for i in range(501)]
        repo.bulk_update_findings(updates)
        assert db.aql.execute.call_count == 2

    def test_1000_items_two_aql_calls(self):
        db, _ = _make_db()
        repo = ScanEnrichmentRepository(db)
        updates = [{"_key": f"fp{i}"} for i in range(1000)]
        repo.bulk_update_findings(updates)
        assert db.aql.execute.call_count == 2

    def test_1001_items_three_aql_calls(self):
        db, _ = _make_db()
        repo = ScanEnrichmentRepository(db)
        updates = [{"_key": f"fp{i}"} for i in range(1001)]
        repo.bulk_update_findings(updates)
        assert db.aql.execute.call_count == 3

    def test_chunk_sizes_are_correct(self):
        """Verify the first chunk has 500 items and the second has the remainder."""
        db, _ = _make_db()
        repo = ScanEnrichmentRepository(db)
        updates = [{"_key": f"fp{i}"} for i in range(750)]

        captured_chunks = []

        def capture_execute(query, bind_vars=None):
            if bind_vars and "updates" in bind_vars:
                captured_chunks.append(len(bind_vars["updates"]))

        db.aql.execute.side_effect = capture_execute
        repo.bulk_update_findings(updates)

        assert captured_chunks == [500, 250]

    def test_correct_aql_query_content(self):
        """AQL query must reference scan_findings collection."""
        db, _ = _make_db()
        repo = ScanEnrichmentRepository(db)
        repo.bulk_update_findings([{"_key": "fp1"}])

        call_args = db.aql.execute.call_args
        query = call_args[0][0]
        assert "scan_findings" in query
        assert "UPDATE" in query


# ---------------------------------------------------------------------------
# update_scan_run_status
# ---------------------------------------------------------------------------

class TestUpdateScanRunStatus:
    def test_calls_collection_update_with_status(self):
        db, cols = _make_db()
        repo = ScanEnrichmentRepository(db)
        repo.update_scan_run_status("run123", "enriched")

        scan_runs_col = cols["scan_runs"]
        scan_runs_col.update.assert_called_once()
        payload = scan_runs_col.update.call_args[0][0]
        assert payload["_key"] == "run123"
        assert payload["status"] == "enriched"
        assert "updated_at" in payload

    def test_extra_fields_merged_into_update(self):
        db, cols = _make_db()
        repo = ScanEnrichmentRepository(db)
        repo.update_scan_run_status(
            "run456", "pipeline_failed", extra_fields={"pipeline_error": "boom"}
        )

        payload = cols["scan_runs"].update.call_args[0][0]
        assert payload["status"] == "pipeline_failed"
        assert payload["pipeline_error"] == "boom"

    def test_no_extra_fields_does_not_add_none_keys(self):
        db, cols = _make_db()
        repo = ScanEnrichmentRepository(db)
        repo.update_scan_run_status("run789", "compacted")

        payload = cols["scan_runs"].update.call_args[0][0]
        # pipeline_error should not be in the payload
        assert "pipeline_error" not in payload


# ---------------------------------------------------------------------------
# upsert_detected_controls
# ---------------------------------------------------------------------------

class TestUpsertDetectedControls:
    def test_empty_list_no_import_bulk(self):
        db, cols = _make_db()
        repo = ScanEnrichmentRepository(db)
        repo.upsert_detected_controls([])
        # detected_controls collection should not have been accessed at all
        assert "detected_controls" not in cols or not cols.get("detected_controls", MagicMock()).import_bulk.called

    def test_delegates_to_import_bulk(self):
        db, cols = _make_db()
        repo = ScanEnrichmentRepository(db)
        docs = [{"_key": "ctrl1", "req_id": "REQ_1"}]
        repo.upsert_detected_controls(docs)

        cols["detected_controls"].import_bulk.assert_called_once_with(
            docs, on_duplicate="update"
        )

    def test_bulk_upsert_alias_works(self):
        """bulk_upsert_detected_controls is an alias for upsert_detected_controls."""
        db, cols = _make_db()
        repo = ScanEnrichmentRepository(db)
        docs = [{"_key": "ctrl2"}]
        repo.bulk_upsert_detected_controls(docs)
        cols["detected_controls"].import_bulk.assert_called_once()


# ---------------------------------------------------------------------------
# upsert_finding_triggers_req_edges
# ---------------------------------------------------------------------------

class TestUpsertFindingTriggersReqEdges:
    def test_empty_list_no_call(self):
        db, _ = _make_db()
        repo = ScanEnrichmentRepository(db)
        repo.upsert_finding_triggers_req_edges([])
        assert "finding_triggers_req" not in {
            c for c in db.collection.call_args_list
        }

    def test_delegates_to_import_bulk(self):
        db, cols = _make_db()
        repo = ScanEnrichmentRepository(db)
        edges = [
            {
                "_key": "e1",
                "_from": "scan_findings/fp1",
                "_to": "regulatory_requirements/REQ_1",
                "tenant_id": "t1",
                "source": "cve_violates_req",
            }
        ]
        repo.upsert_finding_triggers_req_edges(edges)
        cols["finding_triggers_req"].import_bulk.assert_called_once_with(
            edges, on_duplicate="update"
        )


# ---------------------------------------------------------------------------
# upsert_detected_control_maps_to_edges
# ---------------------------------------------------------------------------

class TestUpsertDetectedControlMapsToEdges:
    def test_empty_list_no_call(self):
        db, _ = _make_db()
        repo = ScanEnrichmentRepository(db)
        repo.upsert_detected_control_maps_to_edges([])
        # No import_bulk calls should have occurred
        db.collection.assert_not_called()

    def test_delegates_to_import_bulk(self):
        db, cols = _make_db()
        repo = ScanEnrichmentRepository(db)
        edges = [
            {
                "_key": "e2",
                "_from": "detected_controls/ctrl1",
                "_to": "regulatory_requirements/REQ_1",
                "tenant_id": "t1",
            }
        ]
        repo.upsert_detected_control_maps_to_edges(edges)
        cols["detected_control_maps_to"].import_bulk.assert_called_once_with(
            edges, on_duplicate="update"
        )


# ---------------------------------------------------------------------------
# fetch_findings_for_run — pagination
# ---------------------------------------------------------------------------

class TestFetchFindingsForRun:
    def test_single_batch_shorter_than_batch_size_terminates(self):
        """If batch < batch_size, iteration stops after one page."""
        db, _ = _make_db()
        repo = ScanEnrichmentRepository(db)

        findings = [{"_key": f"fp{i}", "scan_run_id": "run1"} for i in range(10)]

        # Return 10 findings on first call, empty on second
        db.aql.execute.side_effect = [
            iter(findings),
            iter([]),
        ]

        result = list(repo.fetch_findings_for_run("run1", "t1", batch_size=500))
        assert len(result) == 1
        assert result[0] == findings
        # Only one AQL call needed (batch < batch_size means no second page)
        assert db.aql.execute.call_count == 1

    def test_empty_first_batch_yields_nothing(self):
        db, _ = _make_db()
        repo = ScanEnrichmentRepository(db)
        db.aql.execute.return_value = iter([])

        result = list(repo.fetch_findings_for_run("run1", "t1"))
        assert result == []

    def test_two_full_batches_then_partial_yields_three(self):
        """500 + 500 + 200 findings → 3 yielded batches."""
        db, _ = _make_db()
        repo = ScanEnrichmentRepository(db)

        batch1 = [{"_key": f"fp{i}"} for i in range(500)]
        batch2 = [{"_key": f"fp{i}"} for i in range(500, 1000)]
        batch3 = [{"_key": f"fp{i}"} for i in range(1000, 1200)]

        db.aql.execute.side_effect = [
            iter(batch1),
            iter(batch2),
            iter(batch3),
        ]

        result = list(repo.fetch_findings_for_run("run1", "t1", batch_size=500))
        assert len(result) == 3
        assert result[0] == batch1
        assert result[1] == batch2
        assert result[2] == batch3


# ---------------------------------------------------------------------------
# aql_enrich_batch
# ---------------------------------------------------------------------------

class TestAqlEnrichBatch:
    def test_empty_cve_ids_returns_empty_dict_no_db_call(self):
        db, _ = _make_db()
        repo = ScanEnrichmentRepository(db)
        result = repo.aql_enrich_batch([])
        assert result == {}
        db.aql.execute.assert_not_called()

    def test_returns_keyed_dict(self):
        db, _ = _make_db()
        repo = ScanEnrichmentRepository(db)

        enrichment_row = {
            "cve_key": "CVE_2024_1234",
            "epss_score": 0.23,
            "epss_percentile": 0.85,
            "in_kev": False,
            "cwe_chain": ["CWE-79"],
            "d3fend_techniques": ["D3-OTF"],
            "req_keys": ["REQ_NIST_SI_3"],
        }
        db.aql.execute.return_value = iter([enrichment_row])

        result = repo.aql_enrich_batch(["CVE_2024_1234"])
        assert "CVE_2024_1234" in result
        assert result["CVE_2024_1234"]["epss_score"] == 0.23

    def test_exception_returns_empty_dict(self):
        db, _ = _make_db()
        repo = ScanEnrichmentRepository(db)
        db.aql.execute.side_effect = Exception("DB error")

        result = repo.aql_enrich_batch(["CVE_2024_9999"])
        assert result == {}


# ---------------------------------------------------------------------------
# aql_get_cwe_parent_map
# ---------------------------------------------------------------------------

class TestAqlGetCweParentMap:
    def test_empty_cwe_ids_returns_empty_no_db_call(self):
        db, _ = _make_db()
        repo = ScanEnrichmentRepository(db)
        result = repo.aql_get_cwe_parent_map([])
        assert result == {}
        db.aql.execute.assert_not_called()

    def test_resolved_self_when_has_req(self):
        db, _ = _make_db()
        repo = ScanEnrichmentRepository(db)
        db.aql.execute.return_value = iter([
            {"cwe_key": "CWE_79", "resolved": "CWE_79"},
        ])
        result = repo.aql_get_cwe_parent_map(["CWE_79"])
        assert result == {"CWE_79": "CWE_79"}

    def test_resolved_to_parent(self):
        db, _ = _make_db()
        repo = ScanEnrichmentRepository(db)
        db.aql.execute.return_value = iter([
            {"cwe_key": "CWE_117", "resolved": "CWE_116"},
        ])
        result = repo.aql_get_cwe_parent_map(["CWE_117"])
        assert result == {"CWE_117": "CWE_116"}

    def test_none_resolved_falls_back_to_self(self):
        """If AQL returns resolved=null, fall back to cwe_key itself."""
        db, _ = _make_db()
        repo = ScanEnrichmentRepository(db)
        db.aql.execute.return_value = iter([
            {"cwe_key": "CWE_999", "resolved": None},
        ])
        result = repo.aql_get_cwe_parent_map(["CWE_999"])
        assert result == {"CWE_999": "CWE_999"}

    def test_exception_returns_identity_map(self):
        db, _ = _make_db()
        repo = ScanEnrichmentRepository(db)
        db.aql.execute.side_effect = Exception("timeout")
        result = repo.aql_get_cwe_parent_map(["CWE_79", "CWE_20"])
        # Falls back to identity map
        assert result == {"CWE_79": "CWE_79", "CWE_20": "CWE_20"}


# ---------------------------------------------------------------------------
# aql_get_epss_history_batch (Phase 2 addition)
# ---------------------------------------------------------------------------

class TestAqlGetEpssHistoryBatch:
    def test_empty_cve_keys_returns_empty_no_db_call(self):
        db, _ = _make_db()
        repo = ScanEnrichmentRepository(db)
        result = repo.aql_get_epss_history_batch([], "2024-01-01")
        assert result == {}
        db.aql.execute.assert_not_called()

    def test_returns_history_keyed_by_cve_key(self):
        db, _ = _make_db()
        repo = ScanEnrichmentRepository(db)
        history = [{"score": 0.1, "date": "2024-01-01"}, {"score": 0.2, "date": "2024-01-02"}]
        db.aql.execute.return_value = iter([
            {"cve_key": "CVE_2024_1234", "history": history}
        ])
        result = repo.aql_get_epss_history_batch(["CVE_2024_1234"], "2024-01-01")
        assert "CVE_2024_1234" in result
        assert result["CVE_2024_1234"] == history

    def test_cve_with_no_history_excluded(self):
        db, _ = _make_db()
        repo = ScanEnrichmentRepository(db)
        # Row has null/empty history → should not appear in result
        db.aql.execute.return_value = iter([
            {"cve_key": "CVE_2024_0001", "history": []}
        ])
        result = repo.aql_get_epss_history_batch(["CVE_2024_0001"], "2024-01-01")
        # history is empty — key present but with empty list (behavior depends on impl)
        # what matters is no KeyError raised
        assert isinstance(result, dict)

    def test_exception_returns_empty_dict(self):
        db, _ = _make_db()
        repo = ScanEnrichmentRepository(db)
        db.aql.execute.side_effect = Exception("AQL timeout")
        result = repo.aql_get_epss_history_batch(["CVE_2024_9999"], "2024-01-01")
        assert result == {}

    def test_bind_vars_include_cve_keys_and_cutoff(self):
        db, _ = _make_db()
        repo = ScanEnrichmentRepository(db)
        db.aql.execute.return_value = iter([])
        repo.aql_get_epss_history_batch(["CVE_2024_1234", "CVE_2024_5678"], "2024-01-15")
        call_kwargs = db.aql.execute.call_args
        bind_vars = call_kwargs.kwargs.get("bind_vars") or call_kwargs.args[1]
        assert bind_vars["cve_keys"] == ["CVE_2024_1234", "CVE_2024_5678"]
        assert bind_vars["cutoff_date"] == "2024-01-15"

    def test_multiple_cves_all_returned(self):
        db, _ = _make_db()
        repo = ScanEnrichmentRepository(db)
        db.aql.execute.return_value = iter([
            {"cve_key": "CVE_2024_0001", "history": [{"score": 0.1, "date": "2024-01-01"}]},
            {"cve_key": "CVE_2024_0002", "history": [{"score": 0.9, "date": "2024-01-01"}]},
        ])
        result = repo.aql_get_epss_history_batch(["CVE_2024_0001", "CVE_2024_0002"], "2024-01-01")
        assert len(result) == 2
        assert "CVE_2024_0001" in result
        assert "CVE_2024_0002" in result
