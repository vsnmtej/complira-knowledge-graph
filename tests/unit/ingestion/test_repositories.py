"""
Unit tests for ingestion/repositories.py.

Covers: EvidenceRunRepository (create/complete/fail/append_audit_log),
EvidenceFindingRepository, EvidenceComponentRepository,
EvidenceDetectedControlRepository — all with mock DB.
"""

from unittest.mock import MagicMock, call
import pytest

from complira_graph.ingestion.repositories import (
    EvidenceRunRepository,
    EvidenceFindingRepository,
    EvidenceComponentRepository,
    EvidenceDetectedControlRepository,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_db(col_name="scan_runs"):
    db = MagicMock()
    col = MagicMock()
    db.collection.return_value = col
    return db, col


# ---------------------------------------------------------------------------
# EvidenceRunRepository
# ---------------------------------------------------------------------------

class TestEvidenceRunRepositoryCreate:
    def test_create_returns_new_doc(self):
        db, col = _mock_db()
        col.insert.return_value = {"_key": "abc", "new": {"_key": "abc", "status": "running"}}
        repo = EvidenceRunRepository(db)

        result = repo.create_run(tenant_id="t1")

        assert result["_key"] == "abc"
        assert result["status"] == "running"

    def test_create_calls_insert_with_required_fields(self):
        db, col = _mock_db()
        inserted_docs = []

        def capture_insert(doc, return_new=False):
            inserted_docs.append(doc)
            return {"_key": doc["_key"], "new": dict(doc)}

        col.insert.side_effect = capture_insert
        repo = EvidenceRunRepository(db)
        repo.create_run(tenant_id="tenant_x", project_id="proj1", tools_invoked=["semgrep"])

        assert len(inserted_docs) == 1
        d = inserted_docs[0]
        assert d["tenant_id"] == "tenant_x"
        assert d["project_id"] == "proj1"
        assert "semgrep" in d["tools_invoked"]
        assert d["status"] == "running"

    def test_create_generates_unique_keys(self):
        db, col = _mock_db()
        keys = []

        def capture(doc, return_new=False):
            keys.append(doc["_key"])
            return {"_key": doc["_key"], "new": dict(doc)}

        col.insert.side_effect = capture
        repo = EvidenceRunRepository(db)
        repo.create_run(tenant_id="t1")
        repo.create_run(tenant_id="t1")

        assert keys[0] != keys[1]


class TestEvidenceRunRepositoryComplete:
    def test_complete_calls_update_with_status_completed(self):
        db, col = _mock_db()
        repo = EvidenceRunRepository(db)

        repo.complete_run("key1", finding_counts={"high": 2})

        update_arg = col.update.call_args[0][0]
        assert update_arg["_key"] == "key1"
        assert update_arg["status"] == "completed"
        assert update_arg["finding_counts"]["high"] == 2
        assert "completed_at" in update_arg

    def test_complete_passes_custom_status(self):
        db, col = _mock_db()
        repo = EvidenceRunRepository(db)

        repo.complete_run("key1", finding_counts={}, status="partial")

        update_arg = col.update.call_args[0][0]
        assert update_arg["status"] == "partial"


class TestEvidenceRunRepositoryFail:
    def test_fail_sets_status_failed(self):
        db, col = _mock_db()
        repo = EvidenceRunRepository(db)

        repo.fail_run("key2", "something went wrong")

        update_arg = col.update.call_args[0][0]
        assert update_arg["_key"] == "key2"
        assert update_arg["status"] == "failed"
        assert update_arg["error_message"] == "something went wrong"
        assert "completed_at" in update_arg


class TestEvidenceRunRepositoryAuditLog:
    def test_append_audit_log_noop_on_empty(self):
        db, col = _mock_db()
        repo = EvidenceRunRepository(db)

        repo.append_audit_log("key3", [])

        db.aql.execute.assert_not_called()

    def test_append_audit_log_calls_aql_with_entries(self):
        db, col = _mock_db()
        repo = EvidenceRunRepository(db)
        entries = [{"check_id": "CKV_AWS_1", "file": "main.tf"}]

        repo.append_audit_log("key3", entries)

        db.aql.execute.assert_called_once()
        call_kwargs = db.aql.execute.call_args[1]
        assert call_kwargs["bind_vars"]["key"] == "key3"
        assert call_kwargs["bind_vars"]["entries"] == entries

    def test_append_audit_log_aql_contains_append_keyword(self):
        db, col = _mock_db()
        repo = EvidenceRunRepository(db)

        repo.append_audit_log("key4", [{"x": 1}])

        aql_query = db.aql.execute.call_args[0][0]
        assert "APPEND" in aql_query
        assert "scan_runs" in aql_query


# ---------------------------------------------------------------------------
# EvidenceFindingRepository
# ---------------------------------------------------------------------------

class TestEvidenceFindingRepository:
    def test_upsert_batch_empty_returns_zeros(self):
        db, col = _mock_db()
        db.collection.return_value = col
        repo = EvidenceFindingRepository(db)

        result = repo.upsert_batch([])

        assert result["created"] == 0
        col.import_bulk.assert_not_called()

    def test_upsert_batch_calls_import_bulk_with_update(self):
        db, col = _mock_db()
        col.import_bulk.return_value = {"created": 2, "updated": 0, "errors": 0}
        repo = EvidenceFindingRepository(db)

        docs = [{"_key": "fp1", "rule_id": "sqli"}, {"_key": "fp2", "rule_id": "xss"}]
        result = repo.upsert_batch(docs)

        col.import_bulk.assert_called_once_with(docs, on_duplicate="update")
        assert result["created"] == 2

    def test_upsert_batch_returns_import_result(self):
        db, col = _mock_db()
        col.import_bulk.return_value = {"created": 0, "updated": 3, "errors": 0}
        repo = EvidenceFindingRepository(db)

        result = repo.upsert_batch([{"_key": "x"}])

        assert result["updated"] == 3

    def test_upsert_batch_idempotent_on_duplicate(self):
        """Same docs upserted twice — second call still uses on_duplicate=update."""
        db, col = _mock_db()
        col.import_bulk.return_value = {"created": 0, "updated": 1, "errors": 0}
        repo = EvidenceFindingRepository(db)

        docs = [{"_key": "dup_fp"}]
        repo.upsert_batch(docs)
        repo.upsert_batch(docs)

        assert col.import_bulk.call_count == 2
        for c in col.import_bulk.call_args_list:
            assert c[1]["on_duplicate"] == "update"


# ---------------------------------------------------------------------------
# EvidenceComponentRepository
# ---------------------------------------------------------------------------

class TestEvidenceComponentRepository:
    def test_upsert_batch_empty_returns_zeros(self):
        db = MagicMock()
        col = MagicMock()
        db.collection.return_value = col
        repo = EvidenceComponentRepository(db)

        result = repo.upsert_batch([])

        assert result["created"] == 0
        col.import_bulk.assert_not_called()

    def test_upsert_batch_calls_import_bulk(self):
        db = MagicMock()
        col = MagicMock()
        col.import_bulk.return_value = {"created": 1, "updated": 0}
        db.collection.return_value = col
        repo = EvidenceComponentRepository(db)

        docs = [{"_key": "pkg_express_4_18_2", "purl": "pkg:npm/express@4.18.2"}]
        result = repo.upsert_batch(docs)

        col.import_bulk.assert_called_once_with(docs, on_duplicate="update")
        assert result["created"] == 1


# ---------------------------------------------------------------------------
# EvidenceDetectedControlRepository
# ---------------------------------------------------------------------------

class TestEvidenceDetectedControlRepository:
    def test_upsert_batch_empty_returns_zeros(self):
        db = MagicMock()
        col = MagicMock()
        db.collection.return_value = col
        repo = EvidenceDetectedControlRepository(db)

        result = repo.upsert_batch([])

        assert result["created"] == 0

    def test_upsert_batch_calls_import_bulk(self):
        db = MagicMock()
        col = MagicMock()
        col.import_bulk.return_value = {"created": 1, "updated": 0}
        db.collection.return_value = col
        repo = EvidenceDetectedControlRepository(db)

        docs = [{"_key": "fp_ctrl_1", "check_id": "CKV_AWS_1", "triage_status": "compliant"}]
        result = repo.upsert_batch(docs)

        col.import_bulk.assert_called_once_with(docs, on_duplicate="update")
        assert result["created"] == 1
