"""
Unit tests for enrichment_pipeline.py

Covers:
- EnrichmentPipeline._normalize_cve_key: CVE ID normalization to ArangoDB key format
- EnrichmentPipeline._build_finding_updates: enrichment field merging
- EnrichmentPipeline._build_detected_controls: detected_control doc generation
- EnrichmentPipeline._build_req_edges: edge generation from enrichment_map
- EnrichmentPipeline._build_detected_control_maps_to_edges: maps-to edge generation
- EnrichmentPipeline.run: integration of repo calls (with mock repo)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest

from complira_graph.ingestion.enrichment_pipeline import EnrichmentPipeline
from complira_graph.ingestion.scan_enrichment_repository import ScanEnrichmentRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pipeline() -> tuple[EnrichmentPipeline, MagicMock]:
    """Return (pipeline, mock_repo)."""
    db = MagicMock()
    repo = MagicMock(spec=ScanEnrichmentRepository)
    pipeline = EnrichmentPipeline(db, repo)
    return pipeline, repo


def _finding(
    fingerprint: str = "fp1",
    cve_id: str | None = "CVE-2024-1234",
    check_id: str = "CKV_AWS_1",
    rule_id: str = "",
) -> dict:
    return {
        "_key": fingerprint,
        "fingerprint": fingerprint,
        "cve_id": cve_id,
        "check_id": check_id,
        "rule_id": rule_id,
        "message": "some issue",
        "tenant_id": "t1",
        "scan_run_id": "run1",
    }


def _enrichment(
    cve_key: str = "CVE_2024_1234",
    epss_score: float = 0.23,
    epss_percentile: float = 0.85,
    in_kev: bool = False,
    cwe_chain: list | None = None,
    d3fend: list | None = None,
    req_keys: list | None = None,
) -> dict:
    return {
        "cve_key": cve_key,
        "epss_score": epss_score,
        "epss_percentile": epss_percentile,
        "in_kev": in_kev,
        "cwe_chain": cwe_chain or ["CWE-79"],
        "d3fend_techniques": d3fend or ["D3-OTF"],
        "req_keys": req_keys or ["REQ_NIST_SI_3"],
    }


# ---------------------------------------------------------------------------
# _normalize_cve_key
# ---------------------------------------------------------------------------

class TestNormalizeCveKey:
    def test_standard_cve_id(self):
        p, _ = _make_pipeline()
        assert p._normalize_cve_key("CVE-2024-1234") == "CVE_2024_1234"

    def test_already_normalized(self):
        p, _ = _make_pipeline()
        assert p._normalize_cve_key("CVE_2024_1234") == "CVE_2024_1234"

    def test_lowercase_input_uppercased(self):
        p, _ = _make_pipeline()
        assert p._normalize_cve_key("cve-2024-1234") == "CVE_2024_1234"

    def test_long_cve_id(self):
        p, _ = _make_pipeline()
        assert p._normalize_cve_key("CVE-2024-123456789") == "CVE_2024_123456789"

    def test_multiple_hyphens(self):
        p, _ = _make_pipeline()
        assert p._normalize_cve_key("CVE-2023-99999") == "CVE_2023_99999"


# ---------------------------------------------------------------------------
# _build_finding_updates
# ---------------------------------------------------------------------------

class TestBuildFindingUpdates:
    def test_finding_with_cve_gets_enrichment_fields(self):
        p, _ = _make_pipeline()
        f = _finding("fp1", cve_id="CVE-2024-1234")
        enrichment_map = {"CVE_2024_1234": _enrichment()}

        updates = p._build_finding_updates([f], enrichment_map)

        assert len(updates) == 1
        u = updates[0]
        assert u["_key"] == "fp1"
        assert u["epss_score"] == 0.23
        assert u["epss_percentile"] == 0.85
        assert u["in_kev"] is False
        assert u["cwe_chain"] == ["CWE-79"]
        assert u["d3fend_techniques"] == ["D3-OTF"]
        assert "enriched_at" in u

    def test_finding_without_cve_gets_only_enriched_at(self):
        p, _ = _make_pipeline()
        f = _finding("fp2", cve_id=None)
        enrichment_map: dict = {}

        updates = p._build_finding_updates([f], enrichment_map)

        assert len(updates) == 1
        u = updates[0]
        assert u["_key"] == "fp2"
        assert "enriched_at" in u
        assert "epss_score" not in u
        assert "in_kev" not in u

    def test_finding_with_cve_not_in_enrichment_map_gets_only_enriched_at(self):
        p, _ = _make_pipeline()
        f = _finding("fp3", cve_id="CVE-2024-9999")
        enrichment_map: dict = {}  # cve not found in reference DB

        updates = p._build_finding_updates([f], enrichment_map)

        u = updates[0]
        assert "enriched_at" in u
        assert "epss_score" not in u

    def test_multiple_findings_all_get_enriched_at(self):
        p, _ = _make_pipeline()
        findings = [
            _finding("fp1", cve_id="CVE-2024-1234"),
            _finding("fp2", cve_id=None),
        ]
        enrichment_map = {"CVE_2024_1234": _enrichment()}

        updates = p._build_finding_updates(findings, enrichment_map)
        assert len(updates) == 2
        for u in updates:
            assert "enriched_at" in u

    def test_null_epss_score_not_written(self):
        """If enrichment_map has epss_score=None, field should not be in update."""
        p, _ = _make_pipeline()
        f = _finding("fp1", cve_id="CVE-2024-1234")
        enrichment_map = {
            "CVE_2024_1234": {
                "cve_key": "CVE_2024_1234",
                "epss_score": None,
                "epss_percentile": None,
                "in_kev": False,
                "cwe_chain": [],
                "d3fend_techniques": [],
                "req_keys": [],
            }
        }

        updates = p._build_finding_updates([f], enrichment_map)
        u = updates[0]
        # epss_score=None should not be written
        assert "epss_score" not in u
        assert "epss_percentile" not in u

    def test_in_kev_true_written_correctly(self):
        p, _ = _make_pipeline()
        f = _finding("fp1", cve_id="CVE-2024-1234")
        enrichment_map = {"CVE_2024_1234": _enrichment(in_kev=True)}

        updates = p._build_finding_updates([f], enrichment_map)
        assert updates[0]["in_kev"] is True


# ---------------------------------------------------------------------------
# _build_detected_controls
# ---------------------------------------------------------------------------

class TestBuildDetectedControls:
    def test_finding_with_cve_and_req_keys_produces_control(self):
        p, _ = _make_pipeline()
        f = _finding("fp1", cve_id="CVE-2024-1234")
        enrichment_map = {"CVE_2024_1234": _enrichment(req_keys=["REQ_NIST_SI_3"])}

        controls = p._build_detected_controls("run1", [f], enrichment_map, "t1")

        assert len(controls) == 1
        ctrl = controls[0]
        assert ctrl["scan_run_id"] == "run1"
        assert ctrl["tenant_id"] == "t1"
        assert ctrl["req_id"] == "REQ_NIST_SI_3"
        assert ctrl["triage_status"] == "compliant"
        assert ctrl["source"] == "enrichment_pipeline"
        assert "_key" in ctrl

    def test_finding_without_cve_produces_no_control(self):
        p, _ = _make_pipeline()
        f = _finding("fp2", cve_id=None)
        enrichment_map: dict = {}

        controls = p._build_detected_controls("run1", [f], enrichment_map, "t1")
        assert controls == []

    def test_duplicate_req_key_across_findings_deduped(self):
        """Two findings pointing to the same req_key should produce one control doc."""
        p, _ = _make_pipeline()
        f1 = _finding("fp1", cve_id="CVE-2024-1234")
        f2 = _finding("fp2", cve_id="CVE-2024-5678")
        shared_enrichment = _enrichment(req_keys=["REQ_NIST_SI_3"])
        enrichment_map = {
            "CVE_2024_1234": shared_enrichment,
            "CVE_2024_5678": shared_enrichment,
        }

        controls = p._build_detected_controls("run1", [f1, f2], enrichment_map, "t1")
        # Both findings map to same req_key → same _key → deduplicated
        assert len(controls) == 1

    def test_multiple_req_keys_produce_multiple_controls(self):
        p, _ = _make_pipeline()
        f = _finding("fp1", cve_id="CVE-2024-1234")
        enrichment_map = {
            "CVE_2024_1234": _enrichment(req_keys=["REQ_1", "REQ_2", "REQ_3"])
        }

        controls = p._build_detected_controls("run1", [f], enrichment_map, "t1")
        assert len(controls) == 3


# ---------------------------------------------------------------------------
# _build_req_edges
# ---------------------------------------------------------------------------

class TestBuildReqEdges:
    def test_finding_with_req_keys_produces_edges(self):
        p, _ = _make_pipeline()
        f = _finding("fp1", cve_id="CVE-2024-1234")
        enrichment_map = {"CVE_2024_1234": _enrichment(req_keys=["REQ_1", "REQ_2"])}

        edges = p._build_req_edges([f], enrichment_map, "t1")

        assert len(edges) == 2
        for edge in edges:
            assert edge["_from"] == "scan_findings/fp1"
            assert edge["source"] == "cve_violates_req"
            assert edge["tenant_id"] == "t1"

    def test_finding_without_cve_produces_no_edges(self):
        p, _ = _make_pipeline()
        f = _finding("fp1", cve_id=None)

        edges = p._build_req_edges([f], {}, "t1")
        assert edges == []

    def test_deduplication_by_edge_key(self):
        """Same finding + same req_key from two list entries → one edge."""
        p, _ = _make_pipeline()
        f1 = _finding("fp1", cve_id="CVE-2024-1234")
        f2 = _finding("fp1", cve_id="CVE-2024-1234")  # same fingerprint
        enrichment_map = {"CVE_2024_1234": _enrichment(req_keys=["REQ_1"])}

        edges = p._build_req_edges([f1, f2], enrichment_map, "t1")
        assert len(edges) == 1


# ---------------------------------------------------------------------------
# _build_detected_control_maps_to_edges
# ---------------------------------------------------------------------------

class TestBuildDetectedControlMapsToEdges:
    def test_produces_edge_per_control(self):
        p, _ = _make_pipeline()
        ctrl = {"_key": "ctrl1", "req_id": "REQ_1"}
        edges = p._build_detected_control_maps_to_edges([ctrl], "t1")

        assert len(edges) == 1
        e = edges[0]
        assert e["_from"] == "detected_controls/ctrl1"
        assert e["_to"] == "regulatory_requirements/REQ_1"
        assert e["tenant_id"] == "t1"
        assert e["source"] == "enrichment_pipeline"

    def test_missing_key_or_req_id_produces_no_edge(self):
        p, _ = _make_pipeline()
        bad_ctrl = {"_key": "", "req_id": "REQ_1"}
        edges = p._build_detected_control_maps_to_edges([bad_ctrl], "t1")
        assert edges == []

    def test_deduplication(self):
        p, _ = _make_pipeline()
        ctrl1 = {"_key": "ctrl1", "req_id": "REQ_1"}
        ctrl2 = {"_key": "ctrl1", "req_id": "REQ_1"}  # duplicate
        edges = p._build_detected_control_maps_to_edges([ctrl1, ctrl2], "t1")
        assert len(edges) == 1


# ---------------------------------------------------------------------------
# run() — integration with mock repo
# ---------------------------------------------------------------------------

class TestEnrichmentPipelineRun:
    def test_run_with_empty_findings_still_updates_status(self):
        p, repo = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([])

        p.run("run1", "t1")

        repo.update_scan_run_status.assert_called_once_with(
            "run1", "enriched", extra_fields={"enriched_at": repo.update_scan_run_status.call_args[1]["extra_fields"]["enriched_at"]}
        )

    def test_run_calls_bulk_update_for_each_batch(self):
        p, repo = _make_pipeline()

        batch1 = [_finding("fp1")]
        batch2 = [_finding("fp2")]
        repo.fetch_findings_for_run.return_value = iter([batch1, batch2])
        repo.aql_enrich_batch.return_value = {
            "CVE_2024_1234": _enrichment(),
        }

        p.run("run1", "t1")

        # bulk_update_findings called once per batch
        assert repo.bulk_update_findings.call_count == 2

    def test_run_calls_upsert_edges_for_each_batch(self):
        p, repo = _make_pipeline()
        batch = [_finding("fp1", cve_id="CVE-2024-1234")]
        repo.fetch_findings_for_run.return_value = iter([batch])
        repo.aql_enrich_batch.return_value = {
            "CVE_2024_1234": _enrichment(req_keys=["REQ_1"])
        }

        p.run("run1", "t1")

        repo.upsert_finding_triggers_req_edges.assert_called_once()
        repo.upsert_detected_controls.assert_called_once()
        repo.upsert_detected_control_maps_to_edges.assert_called_once()

    def test_run_status_set_to_enriched_at_end(self):
        p, repo = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([])

        p.run("run1", "t1")

        call_kwargs = repo.update_scan_run_status.call_args
        assert call_kwargs[0][0] == "run1"
        assert call_kwargs[0][1] == "enriched"
