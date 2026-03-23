"""
Unit tests for scan_blast_radius_repository.py

Covers:
- aql_blast_radius_for_purl: success path, empty traversal, AQL exception fallback
- aql_total_project_components: global count, project-scoped count, exception fallback
- bulk_write_blast_radius: empty skip, single chunk, multi-chunk
- update_scan_run_status: status + extra_fields
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from complira_graph.ingestion.scan_blast_radius_repository import (
    ScanBlastRadiusRepository,
    _CHUNK_SIZE,
)


def _make_repo() -> tuple[ScanBlastRadiusRepository, MagicMock]:
    db = MagicMock()
    repo = ScanBlastRadiusRepository(db)
    return repo, db


# ---------------------------------------------------------------------------
# aql_blast_radius_for_purl
# ---------------------------------------------------------------------------

class TestAqlBlastRadiusForPurl:
    def test_returns_traversal_result(self):
        repo, db = _make_repo()
        db.aql.execute.return_value = iter([
            {
                "affected_purls": ["pkg:npm/lodash@4.17.15"],
                "affected_names": ["lodash"],
                "max_depth": 1,
                "found": True,
            }
        ])
        result = repo.aql_blast_radius_for_purl("pkg:npm/vulnerable@1.0.0")
        assert result["found"] is True
        assert result["affected_purls"] == ["pkg:npm/lodash@4.17.15"]
        assert result["affected_names"] == ["lodash"]
        assert result["max_depth"] == 1

    def test_empty_traversal_returns_empty_lists(self):
        repo, db = _make_repo()
        db.aql.execute.return_value = iter([
            {"affected_purls": [], "affected_names": [], "max_depth": 0, "found": False}
        ])
        result = repo.aql_blast_radius_for_purl("pkg:pypi/unknown@0.0.1")
        assert result["affected_purls"] == []
        assert result["found"] is False

    def test_aql_exception_returns_empty_fallback(self):
        repo, db = _make_repo()
        db.aql.execute.side_effect = Exception("ArangoDB unreachable")
        result = repo.aql_blast_radius_for_purl("pkg:npm/x@1")
        assert result == {"affected_purls": [], "affected_names": [], "max_depth": 0, "found": False}

    def test_null_affected_purls_coerced_to_empty_list(self):
        repo, db = _make_repo()
        db.aql.execute.return_value = iter([
            {"affected_purls": None, "affected_names": None, "max_depth": 0, "found": True}
        ])
        result = repo.aql_blast_radius_for_purl("pkg:npm/x@1")
        assert result["affected_purls"] == []
        assert result["affected_names"] == []

    def test_bind_vars_include_purl_and_depth_max(self):
        repo, db = _make_repo()
        db.aql.execute.return_value = iter([
            {"affected_purls": [], "affected_names": [], "max_depth": 0, "found": False}
        ])
        repo.aql_blast_radius_for_purl("pkg:npm/x@1", depth_max=3)
        call_kwargs = db.aql.execute.call_args
        bind_vars = call_kwargs.kwargs.get("bind_vars") or call_kwargs.args[1]
        assert bind_vars["purl"] == "pkg:npm/x@1"
        assert bind_vars["depth_max"] == 3


# ---------------------------------------------------------------------------
# aql_total_project_components
# ---------------------------------------------------------------------------

class TestAqlTotalProjectComponents:
    def test_global_count_returned(self):
        repo, db = _make_repo()
        db.aql.execute.return_value = iter([42])
        count = repo.aql_total_project_components()
        assert count == 42

    def test_project_scoped_count(self):
        repo, db = _make_repo()
        db.aql.execute.return_value = iter([10])
        count = repo.aql_total_project_components(project_id="proj1")
        assert count == 10
        call_kwargs = db.aql.execute.call_args
        bind_vars = call_kwargs.kwargs.get("bind_vars") or call_kwargs.args[1]
        assert bind_vars["project_id"] == "proj1"

    def test_exception_returns_one(self):
        repo, db = _make_repo()
        db.aql.execute.side_effect = Exception("db error")
        count = repo.aql_total_project_components()
        assert count == 1

    def test_none_result_returns_one(self):
        repo, db = _make_repo()
        db.aql.execute.return_value = iter([None])
        count = repo.aql_total_project_components()
        assert count == 1


# ---------------------------------------------------------------------------
# bulk_write_blast_radius
# ---------------------------------------------------------------------------

class TestBulkWriteBlastRadius:
    def test_empty_updates_skips_aql(self):
        repo, db = _make_repo()
        repo.bulk_write_blast_radius([])
        db.aql.execute.assert_not_called()

    def test_single_chunk(self):
        repo, db = _make_repo()
        updates = [{"_key": "fp1", "blast_radius_score": 0.5, "affected_components": [], "blast_radius_path": [], "blast_radius_computed_at": "t"}]
        repo.bulk_write_blast_radius(updates)
        assert db.aql.execute.call_count == 1

    def test_multi_chunk(self):
        repo, db = _make_repo()
        updates = [{"_key": f"fp{i}"} for i in range(_CHUNK_SIZE + 2)]
        repo.bulk_write_blast_radius(updates)
        assert db.aql.execute.call_count == 2

    def test_aql_uses_keepnull_false(self):
        repo, db = _make_repo()
        repo.bulk_write_blast_radius([{"_key": "fp1"}])
        aql_text = db.aql.execute.call_args.args[0]
        assert "keepNull: false" in aql_text


# ---------------------------------------------------------------------------
# update_scan_run_status
# ---------------------------------------------------------------------------

class TestUpdateScanRunStatus:
    def test_updates_collection_with_status(self):
        repo, db = _make_repo()
        repo.update_scan_run_status("run1", "blast_radius_computed")
        payload = db.collection.return_value.update.call_args.args[0]
        assert payload["_key"] == "run1"
        assert payload["status"] == "blast_radius_computed"

    def test_extra_fields_included(self):
        repo, db = _make_repo()
        repo.update_scan_run_status("run1", "blast_radius_computed", extra_fields={"blast_radius_computed_at": "ts"})
        payload = db.collection.return_value.update.call_args.args[0]
        assert payload["blast_radius_computed_at"] == "ts"
