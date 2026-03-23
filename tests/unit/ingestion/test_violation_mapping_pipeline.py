"""
Unit tests for violation_mapping_pipeline.py

Covers:
- run: finding with CVE that maps to controls → edges written
- run: finding with CVE that has no controls → no edges, status still set
- run: finding without CVE → skipped
- run: scan run with zero findings → status set, no errors
- run: CVE deduplication — one AQL call per unique CVE
- run: idempotent edge keys (same finding+control = same key)
- run: status set to violations_mapped on success
- _build_edges: correct edge fields (tenant_id, cve_id, control_id, framework, etc.)
- direct-ref path: nist_control_refs → NIST-800-53 edges
- direct-ref path: hipaa_refs → HIPAA edges
- direct-ref path: control ID not in oscal_controls → edge skipped gracefully
- direct-ref path: deduplication (same finding+control from two ref fields → one edge)
- _parse_control_refs: comma-separated string parsing + dedup
"""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from complira_graph.ingestion.violation_mapping_pipeline import (
    ViolationMappingPipeline,
    _parse_control_refs,
)
from complira_graph.ingestion.scan_enrichment_repository import ScanEnrichmentRepository
from complira_graph.ingestion.scan_violation_repository import ScanViolationRepository


def _make_pipeline():
    db = MagicMock()
    repo = MagicMock(spec=ScanEnrichmentRepository)
    violation_repo = MagicMock(spec=ScanViolationRepository)
    pipeline = ViolationMappingPipeline(db, repo, violation_repo)
    return pipeline, repo, violation_repo


def _finding(
    key: str,
    cve_id: str | None = None,
    nist_control_refs: str = "",
    hipaa_refs: str = "",
) -> dict:
    doc: dict = {"_key": key, "cve_id": cve_id}
    if nist_control_refs:
        doc["nist_control_refs"] = nist_control_refs
    if hipaa_refs:
        doc["hipaa_refs"] = hipaa_refs
    return doc


def _control(control_key: str, control_id: str = "SI-2", framework: str = "NIST_800_53") -> dict:
    return {
        "control_key": control_key,
        "control_id": control_id,
        "framework": framework,
        "evidence_path": ["CVE_2024_1234", "CWE_79", "CAPEC_86", "T1190", control_key],
    }


# ---------------------------------------------------------------------------
# Happy path — finding with CVE that maps to controls
# ---------------------------------------------------------------------------

class TestRunHappyPath:
    def test_edges_written_for_finding_with_controls(self):
        pipeline, repo, violation_repo = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([
            [_finding("fp1", cve_id="CVE-2024-1234")]
        ])
        violation_repo.aql_traverse_controls_for_cves.return_value = {
            "CVE_2024_1234": [_control("AC-2")]
        }

        pipeline.run("run1", "tenant1")

        violation_repo.upsert_finding_violates_control_edges.assert_called_once()
        edges = violation_repo.upsert_finding_violates_control_edges.call_args.args[0]
        assert len(edges) == 1
        edge = edges[0]
        assert edge["_from"] == "scan_findings/fp1"
        assert edge["_to"] == "oscal_controls/AC-2"
        assert edge["tenant_id"] == "tenant1"
        assert edge["scan_run_id"] == "run1"
        assert edge["control_id"] == "SI-2"
        assert edge["framework"] == "NIST_800_53"
        assert edge["confidence"] == 1.0

    def test_status_set_to_violations_mapped_on_success(self):
        pipeline, repo, violation_repo = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([
            [_finding("fp1", cve_id="CVE-2024-1234")]
        ])
        violation_repo.aql_traverse_controls_for_cves.return_value = {
            "CVE_2024_1234": [_control("AC-2")]
        }

        pipeline.run("run1", "tenant1")

        repo.update_scan_run_status.assert_called_once_with("run1", "violations_mapped")

    def test_cve_id_normalized_to_key_format(self):
        """CVE-2024-1234 must be normalized to CVE_2024_1234 for traversal."""
        pipeline, repo, violation_repo = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([
            [_finding("fp1", cve_id="CVE-2024-1234")]
        ])
        violation_repo.aql_traverse_controls_for_cves.return_value = {}

        pipeline.run("run1", "tenant1")

        called_keys = violation_repo.aql_traverse_controls_for_cves.call_args.args[0]
        assert "CVE_2024_1234" in called_keys

    def test_cve_dedup_one_traversal_per_unique_cve(self):
        """Two findings with the same CVE must result in one AQL traversal."""
        pipeline, repo, violation_repo = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([
            [
                _finding("fp1", cve_id="CVE-2024-1234"),
                _finding("fp2", cve_id="CVE-2024-1234"),
            ]
        ])
        violation_repo.aql_traverse_controls_for_cves.return_value = {
            "CVE_2024_1234": [_control("AC-2")]
        }

        pipeline.run("run1", "tenant1")

        violation_repo.aql_traverse_controls_for_cves.assert_called_once()
        cve_keys = violation_repo.aql_traverse_controls_for_cves.call_args.args[0]
        assert len(cve_keys) == 1
        assert "CVE_2024_1234" in cve_keys

    def test_two_findings_same_cve_produce_two_edges(self):
        """Each finding gets its own edge even when sharing a CVE."""
        pipeline, repo, violation_repo = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([
            [
                _finding("fp1", cve_id="CVE-2024-1234"),
                _finding("fp2", cve_id="CVE-2024-1234"),
            ]
        ])
        violation_repo.aql_traverse_controls_for_cves.return_value = {
            "CVE_2024_1234": [_control("AC-2")]
        }

        pipeline.run("run1", "tenant1")

        edges = violation_repo.upsert_finding_violates_control_edges.call_args.args[0]
        froms = {e["_from"] for e in edges}
        assert "scan_findings/fp1" in froms
        assert "scan_findings/fp2" in froms


# ---------------------------------------------------------------------------
# No-control CVE — no edges, status still set
# ---------------------------------------------------------------------------

class TestNoCveMapping:
    def test_no_edges_for_cve_with_no_controls(self):
        pipeline, repo, violation_repo = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([
            [_finding("fp1", cve_id="CVE-1999-0001")]
        ])
        violation_repo.aql_traverse_controls_for_cves.return_value = {}

        pipeline.run("run1", "tenant1")

        # upsert is skipped entirely when there are no edges to write
        violation_repo.upsert_finding_violates_control_edges.assert_not_called()

    def test_status_still_set_when_no_controls(self):
        pipeline, repo, violation_repo = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([
            [_finding("fp1", cve_id="CVE-1999-0001")]
        ])
        violation_repo.aql_traverse_controls_for_cves.return_value = {}

        pipeline.run("run1", "tenant1")

        repo.update_scan_run_status.assert_called_once_with("run1", "violations_mapped")


# ---------------------------------------------------------------------------
# Zero findings
# ---------------------------------------------------------------------------

class TestZeroFindings:
    def test_zero_findings_sets_status_without_error(self):
        pipeline, repo, violation_repo = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([])

        pipeline.run("run1", "tenant1")

        violation_repo.aql_traverse_controls_for_cves.assert_not_called()
        violation_repo.upsert_finding_violates_control_edges.assert_not_called()
        repo.update_scan_run_status.assert_called_once_with("run1", "violations_mapped")

    def test_findings_without_cve_treated_as_zero(self):
        pipeline, repo, violation_repo = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([
            [_finding("fp1", cve_id=None), _finding("fp2", cve_id="")]
        ])

        pipeline.run("run1", "tenant1")

        violation_repo.aql_traverse_controls_for_cves.assert_not_called()
        repo.update_scan_run_status.assert_called_once_with("run1", "violations_mapped")


# ---------------------------------------------------------------------------
# Edge key determinism (idempotency)
# ---------------------------------------------------------------------------

class TestEdgeIdempotency:
    def test_same_finding_and_control_produce_same_edge_key(self):
        pipeline, repo, violation_repo = _make_pipeline()

        # Simulate building edges twice with same input
        cve_to_findings = {"CVE_2024_1234": ["fp1"]}
        control_map = {"CVE_2024_1234": [_control("AC-2")]}

        edges_first = pipeline._build_edges(cve_to_findings, control_map, "t1", "run1")
        edges_second = pipeline._build_edges(cve_to_findings, control_map, "t1", "run1")

        assert edges_first[0]["_key"] == edges_second[0]["_key"]


# ---------------------------------------------------------------------------
# _parse_control_refs helper
# ---------------------------------------------------------------------------

class TestParseControlRefs:
    def test_comma_separated(self):
        assert _parse_control_refs("AC-6, IA-2") == ["AC-6", "IA-2"]

    def test_deduplicates(self):
        assert _parse_control_refs("AC-6, IA-2, AC-6") == ["AC-6", "IA-2"]

    def test_empty_string(self):
        assert _parse_control_refs("") == []

    def test_none_treated_as_empty(self):
        assert _parse_control_refs(None) == []

    def test_single_entry(self):
        assert _parse_control_refs("AC-2") == ["AC-2"]

    def test_strips_whitespace(self):
        assert _parse_control_refs("  AC-6 ,  IA-2  ") == ["AC-6", "IA-2"]


# ---------------------------------------------------------------------------
# Direct-ref path — nist_control_refs / hipaa_refs
# ---------------------------------------------------------------------------

class TestDirectRefPath:
    def test_nist_refs_produce_nist_edges(self):
        pipeline, repo, violation_repo = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([
            [_finding("fp1", nist_control_refs="AC-6, IA-2")]
        ])
        violation_repo.aql_lookup_controls_by_ids.return_value = {
            "AC-6": "AC-6",
            "IA-2": "IA-2",
        }

        pipeline.run("run1", "tenant1")

        edges = violation_repo.upsert_finding_violates_control_edges.call_args.args[0]
        frameworks = {e["framework"] for e in edges}
        control_ids = {e["control_id"] for e in edges}
        assert frameworks == {"NIST-800-53"}
        assert control_ids == {"AC-6", "IA-2"}

    def test_hipaa_refs_produce_hipaa_edges(self):
        pipeline, repo, violation_repo = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([
            [_finding("fp1", hipaa_refs="164.312(a)(1)")]
        ])
        violation_repo.aql_lookup_controls_by_ids.return_value = {
            "164.312(a)(1)": "hipaa_164_312_a_1",
        }

        pipeline.run("run1", "tenant1")

        edges = violation_repo.upsert_finding_violates_control_edges.call_args.args[0]
        assert len(edges) == 1
        assert edges[0]["framework"] == "HIPAA"

    def test_unknown_control_id_skipped(self):
        pipeline, repo, violation_repo = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([
            [_finding("fp1", nist_control_refs="AC-6, UNKNOWN-99")]
        ])
        # Only AC-6 found in oscal_controls
        violation_repo.aql_lookup_controls_by_ids.return_value = {"AC-6": "AC-6"}

        pipeline.run("run1", "tenant1")

        edges = violation_repo.upsert_finding_violates_control_edges.call_args.args[0]
        assert len(edges) == 1
        assert edges[0]["control_id"] == "AC-6"

    def test_no_controls_found_no_upsert(self):
        pipeline, repo, violation_repo = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([
            [_finding("fp1", nist_control_refs="UNKNOWN-1")]
        ])
        violation_repo.aql_lookup_controls_by_ids.return_value = {}

        pipeline.run("run1", "tenant1")

        violation_repo.upsert_finding_violates_control_edges.assert_not_called()

    def test_direct_ref_edge_fields(self):
        pipeline, repo, violation_repo = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([
            [_finding("fp1", nist_control_refs="AC-6")]
        ])
        violation_repo.aql_lookup_controls_by_ids.return_value = {"AC-6": "ctrl_AC-6"}

        pipeline.run("run1", "tenant1")

        edges = violation_repo.upsert_finding_violates_control_edges.call_args.args[0]
        e = edges[0]
        assert e["_from"] == "scan_findings/fp1"
        assert e["_to"] == "oscal_controls/ctrl_AC-6"
        assert e["tenant_id"] == "tenant1"
        assert e["scan_run_id"] == "run1"
        assert e["control_id"] == "AC-6"
        assert e["framework"] == "NIST-800-53"
        assert e["confidence"] == 1.0
        assert e["evidence_path"] == ["fp1", "ctrl_AC-6"]
        assert "created_at" in e

    def test_status_set_after_direct_refs(self):
        pipeline, repo, violation_repo = _make_pipeline()
        repo.fetch_findings_for_run.return_value = iter([
            [_finding("fp1", nist_control_refs="AC-6")]
        ])
        violation_repo.aql_lookup_controls_by_ids.return_value = {"AC-6": "AC-6"}

        pipeline.run("run1", "tenant1")

        repo.update_scan_run_status.assert_called_once_with("run1", "violations_mapped")
