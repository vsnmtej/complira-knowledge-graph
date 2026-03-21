"""
Unit tests for ingestion/backfill.py.

Covers: apply_field_map (FIELD_MAP transformation), _migrate_scan_sessions
(field renaming), _migrate_components (purl re-keying, tenant_id removal,
purl missing → skip), unreachable DB error handling, run() summary totals.
"""

from unittest.mock import MagicMock, patch, call
import pytest

from complira_graph.ingestion.backfill import BackfillAdapter


# ---------------------------------------------------------------------------
# apply_field_map
# ---------------------------------------------------------------------------

class TestApplyFieldMap:
    def test_renames_customer_id_to_tenant_id(self):
        doc = {"customer_id": "cust_abc", "status": "completed"}
        result = BackfillAdapter.apply_field_map(doc)
        assert "tenant_id" in result
        assert result["tenant_id"] == "cust_abc"
        assert "customer_id" not in result

    def test_no_rename_when_field_absent(self):
        doc = {"status": "completed", "tool_name": "semgrep"}
        result = BackfillAdapter.apply_field_map(doc)
        assert result == doc

    def test_accepts_custom_field_map(self):
        doc = {"old_name": "value", "keep": "this"}
        result = BackfillAdapter.apply_field_map(doc, field_map={"old_name": "new_name"})
        assert result["new_name"] == "value"
        assert "old_name" not in result
        assert result["keep"] == "this"

    def test_does_not_mutate_input(self):
        doc = {"customer_id": "cust_xyz"}
        original = dict(doc)
        BackfillAdapter.apply_field_map(doc)
        assert doc == original


# ---------------------------------------------------------------------------
# _migrate_scan_sessions
# ---------------------------------------------------------------------------

class TestMigrateScanSessions:
    def _make_ref_db(self):
        ref_db = MagicMock()
        col = MagicMock()
        col.import_bulk.return_value = {"created": 2, "updated": 0}
        ref_db.collection.return_value = col
        return ref_db, col

    def _make_cust_db(self, docs, has_col=True):
        cust_db = MagicMock()
        cust_db.has_collection.return_value = has_col
        col = MagicMock()
        col.all.return_value = iter(docs)
        cust_db.collection.return_value = col
        return cust_db

    def test_renames_customer_id_to_tenant_id(self):
        ref_db, ref_col = self._make_ref_db()
        cust_db = self._make_cust_db([
            {"_key": "s1", "customer_id": "cust1", "tool_name": "semgrep", "findings_count": 5}
        ])

        adapter = BackfillAdapter(ref_db)
        adapter._migrate_scan_sessions("cust1", cust_db)

        imported = ref_col.import_bulk.call_args[0][0]
        doc = imported[0]
        assert doc["tenant_id"] == "cust1"
        assert "customer_id" not in doc

    def test_converts_tool_name_to_tools_invoked_list(self):
        ref_db, ref_col = self._make_ref_db()
        cust_db = self._make_cust_db([
            {"_key": "s2", "tool_name": "checkov"}
        ])

        adapter = BackfillAdapter(ref_db)
        adapter._migrate_scan_sessions("cust2", cust_db)

        imported = ref_col.import_bulk.call_args[0][0]
        doc = imported[0]
        assert doc["tools_invoked"] == ["checkov"]
        assert "tool_name" not in doc

    def test_converts_findings_count_to_finding_counts_total(self):
        ref_db, ref_col = self._make_ref_db()
        cust_db = self._make_cust_db([
            {"_key": "s3", "findings_count": 12}
        ])

        adapter = BackfillAdapter(ref_db)
        adapter._migrate_scan_sessions("cust3", cust_db)

        imported = ref_col.import_bulk.call_args[0][0]
        doc = imported[0]
        assert doc["finding_counts"] == {"total": 12}
        assert "findings_count" not in doc

    def test_skips_when_scan_sessions_collection_missing(self):
        ref_db, ref_col = self._make_ref_db()
        cust_db = self._make_cust_db([], has_col=False)

        adapter = BackfillAdapter(ref_db)
        count = adapter._migrate_scan_sessions("cust4", cust_db)

        assert count == 0
        ref_col.import_bulk.assert_not_called()

    def test_returns_zero_when_no_docs(self):
        ref_db, ref_col = self._make_ref_db()
        cust_db = self._make_cust_db([])

        adapter = BackfillAdapter(ref_db)
        count = adapter._migrate_scan_sessions("cust5", cust_db)

        assert count == 0
        ref_col.import_bulk.assert_not_called()

    def test_uses_on_duplicate_update(self):
        ref_db, ref_col = self._make_ref_db()
        cust_db = self._make_cust_db([{"_key": "s6"}])

        adapter = BackfillAdapter(ref_db)
        adapter._migrate_scan_sessions("cust6", cust_db)

        assert ref_col.import_bulk.call_args[1]["on_duplicate"] == "update"


# ---------------------------------------------------------------------------
# _migrate_components
# ---------------------------------------------------------------------------

class TestMigrateComponents:
    def _make_ref_db(self):
        ref_db = MagicMock()
        col = MagicMock()
        col.import_bulk.return_value = {"created": 1, "updated": 0}
        ref_db.collection.return_value = col
        return ref_db, col

    def _make_cust_db(self, docs, has_col=True):
        cust_db = MagicMock()
        cust_db.has_collection.return_value = has_col
        col = MagicMock()
        col.all.return_value = iter(docs)
        cust_db.collection.return_value = col
        return cust_db

    def test_rekeys_by_normalized_purl(self):
        ref_db, ref_col = self._make_ref_db()
        cust_db = self._make_cust_db([
            {"_key": "old_key", "purl": "pkg:npm/express@4.18.2", "name": "express"}
        ])

        adapter = BackfillAdapter(ref_db)
        adapter._migrate_components("cust1", cust_db)

        imported = ref_col.import_bulk.call_args[0][0]
        doc = imported[0]
        assert doc["_key"] != "old_key"
        # purl-based key doesn't contain slashes or @ raw
        assert "@" not in doc["_key"]

    def test_removes_tenant_id_from_component(self):
        ref_db, ref_col = self._make_ref_db()
        cust_db = self._make_cust_db([
            {"_key": "c1", "purl": "pkg:pypi/flask@2.0.0", "tenant_id": "cust1", "name": "flask"}
        ])

        adapter = BackfillAdapter(ref_db)
        adapter._migrate_components("cust1", cust_db)

        imported = ref_col.import_bulk.call_args[0][0]
        doc = imported[0]
        assert "tenant_id" not in doc

    def test_removes_customer_id_from_component(self):
        ref_db, ref_col = self._make_ref_db()
        cust_db = self._make_cust_db([
            {"_key": "c2", "purl": "pkg:pypi/flask@2.0.0", "customer_id": "cust1", "name": "flask"}
        ])

        adapter = BackfillAdapter(ref_db)
        adapter._migrate_components("cust1", cust_db)

        imported = ref_col.import_bulk.call_args[0][0]
        doc = imported[0]
        assert "customer_id" not in doc

    def test_removes_arango_internal_fields(self):
        ref_db, ref_col = self._make_ref_db()
        cust_db = self._make_cust_db([
            {"_id": "customer_components/c3", "_key": "c3", "_rev": "rev123",
             "purl": "pkg:npm/react@18.0.0", "name": "react"}
        ])

        adapter = BackfillAdapter(ref_db)
        adapter._migrate_components("cust1", cust_db)

        imported = ref_col.import_bulk.call_args[0][0]
        doc = imported[0]
        assert "_id" not in doc
        assert "_rev" not in doc

    def test_skips_component_without_purl(self):
        ref_db, ref_col = self._make_ref_db()
        cust_db = self._make_cust_db([
            {"_key": "c4", "name": "no-purl-comp"}
        ])

        adapter = BackfillAdapter(ref_db)
        count = adapter._migrate_components("cust1", cust_db)

        assert count == 0
        ref_col.import_bulk.assert_not_called()

    def test_skips_when_collection_missing(self):
        ref_db, ref_col = self._make_ref_db()
        cust_db = self._make_cust_db([], has_col=False)

        adapter = BackfillAdapter(ref_db)
        count = adapter._migrate_components("cust2", cust_db)

        assert count == 0
        ref_col.import_bulk.assert_not_called()


# ---------------------------------------------------------------------------
# run() — orchestration + error handling
# ---------------------------------------------------------------------------

class TestBackfillAdapterRun:
    def test_run_returns_summary_with_totals(self):
        ref_db = MagicMock()
        ref_col = MagicMock()
        ref_col.import_bulk.return_value = {"created": 2, "updated": 0}
        ref_db.collection.return_value = ref_col

        cust_db = MagicMock()
        cust_db.has_collection.return_value = True
        col = MagicMock()
        col.all.return_value = iter([
            {"_key": "s1", "customer_id": "c1", "tool_name": "semgrep"}
        ])
        cust_db.collection.return_value = col

        adapter = BackfillAdapter(ref_db)
        result = adapter.run(["c1"], get_customer_db_fn=lambda cid: cust_db)

        assert "scan_runs_migrated" in result
        assert "errors" in result
        assert "per_customer" in result
        assert result["errors"] == 0

    def test_run_records_error_on_unreachable_db(self):
        ref_db = MagicMock()

        def bad_db(cid):
            raise ConnectionError("db unreachable")

        adapter = BackfillAdapter(ref_db)
        result = adapter.run(["c_bad"], get_customer_db_fn=bad_db)

        assert result["errors"] == 1
        assert result["per_customer"]["c_bad"]["error"] == "db_unreachable"

    def test_run_continues_after_one_bad_customer(self):
        ref_db = MagicMock()
        ref_col = MagicMock()
        ref_col.import_bulk.return_value = {"created": 1, "updated": 0}
        ref_db.collection.return_value = ref_col

        good_cust_db = MagicMock()
        good_cust_db.has_collection.return_value = False  # no collections to migrate

        call_count = [0]

        def get_db(cid):
            call_count[0] += 1
            if cid == "bad":
                raise RuntimeError("bad db")
            return good_cust_db

        adapter = BackfillAdapter(ref_db)
        result = adapter.run(["bad", "good1", "good2"], get_customer_db_fn=get_db)

        assert call_count[0] == 3
        assert result["errors"] == 1
        assert "good1" in result["per_customer"]
        assert "good2" in result["per_customer"]

    def test_run_accumulates_counts_across_customers(self):
        ref_db = MagicMock()
        ref_col = MagicMock()
        ref_db.collection.return_value = ref_col

        call_idx = [0]

        def get_db(cid):
            db = MagicMock()
            db.has_collection.return_value = True
            col = MagicMock()
            if cid == "c1":
                col.all.return_value = iter([
                    {"_key": "s1", "tool_name": "semgrep", "customer_id": "c1"}
                ])
                ref_col.import_bulk.return_value = {"created": 1, "updated": 0}
            elif cid == "c2":
                col.all.return_value = iter([
                    {"_key": "s2", "tool_name": "checkov", "customer_id": "c2"},
                    {"_key": "s3", "tool_name": "grype", "customer_id": "c2"},
                ])
                ref_col.import_bulk.return_value = {"created": 2, "updated": 0}
            db.collection.return_value = col
            return db

        adapter = BackfillAdapter(ref_db)
        result = adapter.run(["c1", "c2"], get_customer_db_fn=get_db)

        # per_customer should have both
        assert "c1" in result["per_customer"]
        assert "c2" in result["per_customer"]
