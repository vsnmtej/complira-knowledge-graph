"""
Unit tests for blast_radius_pipeline.py

Covers:
- run: findings with purl get traversal; findings without purl get zero score
- run: purl deduplication — one AQL call per unique purl
- run: blast radius score formula (affected / total)
- run: score capped at 1.0
- run: status written on success
- _build_blast_updates_for_purl: correct fields
- _build_zero_blast_updates: zero score and empty lists
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from complira_graph.ingestion.blast_radius_pipeline import BlastRadiusPipeline
from complira_graph.ingestion.scan_blast_radius_repository import ScanBlastRadiusRepository
from complira_graph.ingestion.scan_enrichment_repository import ScanEnrichmentRepository


def _make_pipeline():
    db = MagicMock()
    repo = MagicMock(spec=ScanEnrichmentRepository)
    blast_repo = MagicMock(spec=ScanBlastRadiusRepository)
    pipeline = BlastRadiusPipeline(db, repo, blast_repo)
    return pipeline, repo, blast_repo


def _finding(key: str, purl: str | None = None) -> dict:
    return {"_key": key, "purl": purl}


# ---------------------------------------------------------------------------
# run — happy path
# ---------------------------------------------------------------------------

class TestRunHappyPath:
    def test_finding_with_purl_gets_blast_score(self):
        pipeline, repo, blast_repo = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([
            [_finding("fp1", purl="pkg:npm/vuln@1.0")]
        ])
        blast_repo.aql_total_project_components.return_value = 10
        blast_repo.aql_blast_radius_for_purl.return_value = {
            "affected_purls": ["pkg:npm/dep1@1.0", "pkg:npm/dep2@1.0"],
            "affected_names": ["dep1", "dep2"],
            "max_depth": 1,
            "found": True,
        }

        pipeline.run("run1", "t1")

        blast_repo.bulk_write_blast_radius.assert_called_once()
        updates = blast_repo.bulk_write_blast_radius.call_args.args[0]
        assert updates[0]["_key"] == "fp1"
        assert updates[0]["blast_radius_score"] == pytest.approx(0.2)  # 2/10
        assert updates[0]["affected_components"] == ["pkg:npm/dep1@1.0", "pkg:npm/dep2@1.0"]

    def test_finding_without_purl_gets_zero_score(self):
        pipeline, repo, blast_repo = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([
            [_finding("fp1")]  # no purl
        ])
        blast_repo.aql_total_project_components.return_value = 5

        pipeline.run("run1", "t1")

        updates = blast_repo.bulk_write_blast_radius.call_args.args[0]
        assert updates[0]["blast_radius_score"] == 0.0
        assert updates[0]["affected_components"] == []
        blast_repo.aql_blast_radius_for_purl.assert_not_called()

    def test_purl_deduplication_issues_one_aql_per_unique_purl(self):
        pipeline, repo, blast_repo = _make_pipeline()
        # Three findings sharing two unique purls
        repo.fetch_findings_for_run.return_value = iter([
            [
                _finding("fp1", purl="pkg:npm/a@1"),
                _finding("fp2", purl="pkg:npm/a@1"),  # duplicate
                _finding("fp3", purl="pkg:npm/b@1"),
            ]
        ])
        blast_repo.aql_total_project_components.return_value = 10
        blast_repo.aql_blast_radius_for_purl.return_value = {
            "affected_purls": [], "affected_names": [], "max_depth": 0, "found": False
        }

        pipeline.run("run1", "t1")

        assert blast_repo.aql_blast_radius_for_purl.call_count == 2

    def test_score_capped_at_one(self):
        pipeline, repo, blast_repo = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([
            [_finding("fp1", purl="pkg:npm/a@1")]
        ])
        blast_repo.aql_total_project_components.return_value = 1
        blast_repo.aql_blast_radius_for_purl.return_value = {
            "affected_purls": ["p1", "p2", "p3"],
            "affected_names": ["n1", "n2", "n3"],
            "max_depth": 2,
            "found": True,
        }

        pipeline.run("run1", "t1")

        updates = blast_repo.bulk_write_blast_radius.call_args.args[0]
        assert updates[0]["blast_radius_score"] == 1.0

    def test_status_written_on_success(self):
        pipeline, repo, blast_repo = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([[]])
        blast_repo.aql_total_project_components.return_value = 1

        pipeline.run("run1", "t1")

        blast_repo.update_scan_run_status.assert_called_once()
        call_args = blast_repo.update_scan_run_status.call_args
        assert call_args.args[1] == "blast_radius_computed"


# ---------------------------------------------------------------------------
# _build_blast_updates_for_purl
# ---------------------------------------------------------------------------

class TestBuildBlastUpdatesForPurl:
    def test_all_fingerprints_receive_same_traversal(self):
        pipeline, *_ = _make_pipeline()
        traversal = {"affected_purls": ["pkg:x@1"], "affected_names": ["x"], "max_depth": 1}
        updates = pipeline._build_blast_updates_for_purl(["fp1", "fp2"], traversal, 0.5)
        assert len(updates) == 2
        for u in updates:
            assert u["blast_radius_score"] == 0.5
            assert u["affected_components"] == ["pkg:x@1"]
            assert u["blast_radius_path"] == ["x"]
            assert "blast_radius_computed_at" in u


# ---------------------------------------------------------------------------
# _build_zero_blast_updates
# ---------------------------------------------------------------------------

class TestBuildZeroBlastUpdates:
    def test_zero_score_and_empty_lists(self):
        pipeline, *_ = _make_pipeline()
        updates = pipeline._build_zero_blast_updates(["fp1", "fp2"])
        assert all(u["blast_radius_score"] == 0.0 for u in updates)
        assert all(u["affected_components"] == [] for u in updates)
        assert all(u["blast_radius_path"] == [] for u in updates)
        assert all("blast_radius_computed_at" in u for u in updates)
