"""
Unit tests for ingestion/edge_service.py.

Covers: edge key determinism, CWE missing → skip, bc_check_id lookup,
llm_reg_mapper defer, detected_controls stub, project_uses_component,
evidence_links_finding, evidence_for_project.
"""

from unittest.mock import MagicMock, patch, call
import pytest

from complira_graph.ingestion.edge_service import EvidenceEdgeService
from complira_graph.utils.keys import generate_edge_key, normalize_purl, normalize_cwe_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_svc():
    db = MagicMock()
    col = MagicMock()
    col.import_bulk.return_value = {"created": 1}
    db.collection.return_value = col
    return EvidenceEdgeService(db), db, col


# ---------------------------------------------------------------------------
# component_has_vuln edges
# ---------------------------------------------------------------------------

class TestComponentHasVulnEdges:
    def test_creates_edge_for_valid_sca_doc(self):
        svc, db, col = _make_svc()
        docs = [{"purl": "pkg:npm/lodash@4.17.21", "cve_id": "CVE-2021-23337", "tool": "grype"}]

        svc.create_component_has_vuln_edges(docs, tenant_id="t1")

        col.import_bulk.assert_called_once()
        edges = col.import_bulk.call_args[0][0]
        assert len(edges) == 1
        assert edges[0]["tenant_id"] == "t1"
        assert "components/" in edges[0]["_from"]
        assert "vulnerabilities/" in edges[0]["_to"]

    def test_skips_doc_missing_purl(self):
        svc, db, col = _make_svc()
        docs = [{"cve_id": "CVE-2021-23337"}]

        svc.create_component_has_vuln_edges(docs, tenant_id="t1")

        col.import_bulk.assert_not_called()

    def test_skips_doc_missing_cve_id(self):
        svc, db, col = _make_svc()
        docs = [{"purl": "pkg:npm/lodash@4.17.21"}]

        svc.create_component_has_vuln_edges(docs, tenant_id="t1")

        col.import_bulk.assert_not_called()

    def test_edge_key_is_deterministic(self):
        svc, db, col = _make_svc()
        docs = [{"purl": "pkg:npm/express@4.18.2", "cve_id": "CVE-2022-24999", "tool": "grype"}]

        calls_made = []
        col.import_bulk.side_effect = lambda edges, **kw: calls_made.extend(edges)

        svc.create_component_has_vuln_edges(docs, tenant_id="t1")
        svc.create_component_has_vuln_edges(docs, tenant_id="t1")

        assert calls_made[0]["_key"] == calls_made[1]["_key"]


# ---------------------------------------------------------------------------
# finding_maps_to_weakness edges
# ---------------------------------------------------------------------------

class TestFindingWeaknessEdges:
    def test_creates_edge_for_finding_with_cwe(self):
        svc, db, col = _make_svc()
        findings = [{"fingerprint": "fp1", "cwe_ids": ["CWE-89"], "cwe_source": "extracted"}]

        svc.create_finding_weakness_edges(findings, tenant_id="t1")

        col.import_bulk.assert_called_once()
        edges = col.import_bulk.call_args[0][0]
        assert edges[0]["_from"] == "scan_findings/fp1"
        assert "weaknesses/" in edges[0]["_to"]
        assert edges[0]["tenant_id"] == "t1"

    def test_skips_finding_without_cwe(self):
        svc, db, col = _make_svc()
        findings = [{"fingerprint": "fp2", "cwe_ids": []}]

        svc.create_finding_weakness_edges(findings, tenant_id="t1")

        col.import_bulk.assert_not_called()

    def test_creates_multiple_edges_for_multiple_cwes(self):
        svc, db, col = _make_svc()
        findings = [{"fingerprint": "fp3", "cwe_ids": ["CWE-79", "CWE-89"]}]
        edges_created = []
        col.import_bulk.side_effect = lambda edges, **kw: edges_created.extend(edges)

        svc.create_finding_weakness_edges(findings, tenant_id="t1")

        assert len(edges_created) == 2

    def test_edge_key_is_deterministic(self):
        svc1, db1, col1 = _make_svc()
        svc2, db2, col2 = _make_svc()
        findings = [{"fingerprint": "fp4", "cwe_ids": ["CWE-22"]}]

        edges1 = []
        edges2 = []
        col1.import_bulk.side_effect = lambda e, **kw: edges1.extend(e)
        col2.import_bulk.side_effect = lambda e, **kw: edges2.extend(e)

        svc1.create_finding_weakness_edges(findings, tenant_id="t1")
        svc2.create_finding_weakness_edges(findings, tenant_id="t1")

        assert edges1[0]["_key"] == edges2[0]["_key"]


# ---------------------------------------------------------------------------
# finding_triggers_req — llm_reg_mapper defer
# ---------------------------------------------------------------------------

class TestFindingReqEdgesLlmDefer:
    def test_llm_reg_mapper_plans_do_not_write_edges(self):
        svc, db, col = _make_svc()
        findings = [{"fingerprint": "fp5", "cwe_ids": ["CWE-89"]}]
        edge_plans = [
            {
                "collection": "finding_triggers_req",
                "source": "llm_reg_mapper",
                "_from": "scan_findings/fp5",
            }
        ]

        svc.create_finding_req_edges(findings, edge_plans, tenant_id="t1")

        # llm_reg_mapper defers — no collection write (only logging)
        col.import_bulk.assert_not_called()
        db.aql.execute.assert_not_called()

    def test_no_req_plans_returns_early(self):
        svc, db, col = _make_svc()

        svc.create_finding_req_edges([], [], tenant_id="t1")

        col.import_bulk.assert_not_called()


# ---------------------------------------------------------------------------
# finding_triggers_req — checkov_native bc_check_id
# ---------------------------------------------------------------------------

class TestCheckovReqEdge:
    def test_skips_when_no_bc_check_id(self):
        svc, db, col = _make_svc()
        plan = {
            "collection": "finding_triggers_req",
            "source": "checkov_native",
            "_from": "scan_findings/fp6",
            "bc_check_id": None,
        }

        svc._resolve_checkov_req_edge(plan, tenant_id="t1")

        db.aql.execute.assert_not_called()

    def test_creates_edge_when_req_found(self):
        svc, db, col = _make_svc()
        db.aql.execute.return_value = iter(["req_key_abc"])
        plan = {
            "collection": "finding_triggers_req",
            "source": "checkov_native",
            "_from": "scan_findings/fp7",
            "bc_check_id": "BC_AWS_1",
        }

        svc._resolve_checkov_req_edge(plan, tenant_id="t1")

        col.insert.assert_called_once()
        insert_doc = col.insert.call_args[0][0]
        assert insert_doc["_from"] == "scan_findings/fp7"
        assert insert_doc["_to"] == "regulatory_requirements/req_key_abc"
        assert insert_doc["source"] == "checkov_native"
        assert insert_doc["bc_check_id"] == "BC_AWS_1"

    def test_skips_gracefully_when_req_not_found(self):
        svc, db, col = _make_svc()
        db.aql.execute.return_value = iter([])  # no match
        plan = {
            "collection": "finding_triggers_req",
            "source": "checkov_native",
            "_from": "scan_findings/fp8",
            "bc_check_id": "BC_UNKNOWN_99",
        }

        # Should not raise
        svc._resolve_checkov_req_edge(plan, tenant_id="t1")

        col.insert.assert_not_called()

    def test_aql_exception_does_not_propagate(self):
        svc, db, col = _make_svc()
        db.aql.execute.side_effect = RuntimeError("AQL error")
        plan = {
            "collection": "finding_triggers_req",
            "source": "checkov_native",
            "_from": "scan_findings/fp9",
            "bc_check_id": "BC_AWS_2",
        }

        # Should not raise
        svc._resolve_checkov_req_edge(plan, tenant_id="t1")

        col.insert.assert_not_called()


# ---------------------------------------------------------------------------
# finding_in_component edges
# ---------------------------------------------------------------------------

class TestFindingInComponentEdges:
    def test_creates_edge_for_finding_with_purl(self):
        svc, db, col = _make_svc()
        findings = [{"fingerprint": "fp10", "purl": "pkg:npm/axios@1.0.0"}]

        svc.create_finding_in_component_edges(findings, tenant_id="t1")

        col.import_bulk.assert_called_once()
        edges = col.import_bulk.call_args[0][0]
        assert edges[0]["_from"] == "scan_findings/fp10"
        assert "components/" in edges[0]["_to"]

    def test_skips_finding_without_purl(self):
        svc, db, col = _make_svc()
        findings = [{"fingerprint": "fp11"}]

        svc.create_finding_in_component_edges(findings, tenant_id="t1")

        col.import_bulk.assert_not_called()


# ---------------------------------------------------------------------------
# project_uses_component edges
# ---------------------------------------------------------------------------

class TestProjectUsesComponentEdges:
    def test_creates_edges_for_each_component(self):
        svc, db, col = _make_svc()
        comp_docs = [
            {"_key": "comp1", "purl": "pkg:npm/react@18.0.0"},
            {"_key": "comp2", "purl": "pkg:npm/axios@1.0.0"},
        ]

        svc.create_project_uses_component_edges(comp_docs, "proj1", tenant_id="t1")

        col.import_bulk.assert_called_once()
        edges = col.import_bulk.call_args[0][0]
        assert len(edges) == 2
        for e in edges:
            assert e["_from"] == "projects/proj1"
            assert e["tenant_id"] == "t1"

    def test_skips_component_without_purl(self):
        svc, db, col = _make_svc()
        comp_docs = [{"_key": "comp3", "name": "no_purl"}]

        svc.create_project_uses_component_edges(comp_docs, "proj1", tenant_id="t1")

        col.import_bulk.assert_not_called()

    def test_no_op_without_project_id(self):
        svc, db, col = _make_svc()
        comp_docs = [{"_key": "comp4", "purl": "pkg:npm/react@18.0.0"}]

        svc.create_project_uses_component_edges(comp_docs, None, tenant_id="t1")

        col.import_bulk.assert_not_called()


# ---------------------------------------------------------------------------
# evidence_links_finding + evidence_for_project edges
# ---------------------------------------------------------------------------

class TestEvidenceEdges:
    def test_evidence_links_finding_creates_one_edge_per_finding(self):
        svc, db, col = _make_svc()
        findings = [
            {"fingerprint": "fp12"},
            {"fingerprint": "fp13"},
        ]

        svc.create_evidence_finding_edges("pkg_key_1", findings, tenant_id="t1")

        edges = col.import_bulk.call_args[0][0]
        assert len(edges) == 2
        assert edges[0]["_from"] == "evidence_packages/pkg_key_1"
        assert edges[0]["_to"] == "scan_findings/fp12"

    def test_evidence_for_project_creates_single_edge(self):
        svc, db, col = _make_svc()

        svc.create_evidence_project_edge("pkg_key_2", "proj2", tenant_id="t1")

        col.import_bulk.assert_called_once()
        edges = col.import_bulk.call_args[0][0]
        assert len(edges) == 1
        assert edges[0]["_from"] == "evidence_packages/pkg_key_2"
        assert edges[0]["_to"] == "projects/proj2"

    def test_evidence_for_project_noop_without_project(self):
        svc, db, col = _make_svc()

        svc.create_evidence_project_edge("pkg_key_3", None, tenant_id="t1")

        col.import_bulk.assert_not_called()


# ---------------------------------------------------------------------------
# detected_control_edges stub
# ---------------------------------------------------------------------------

class TestDetectedControlEdgesStub:
    def test_stub_does_not_write_edges(self):
        svc, db, col = _make_svc()
        controls = [{"_key": "ctrl1", "check_id": "CKV_AWS_1"}]

        svc.create_detected_control_edges(controls, tenant_id="t1")

        col.import_bulk.assert_not_called()
        db.aql.execute.assert_not_called()

    def test_stub_noop_on_empty(self):
        svc, db, col = _make_svc()

        svc.create_detected_control_edges([], tenant_id="t1")

        col.import_bulk.assert_not_called()


# ---------------------------------------------------------------------------
# create_all_edges orchestrator
# ---------------------------------------------------------------------------

class TestCreateAllEdgesOrchestrator:
    def test_calls_all_creation_methods(self):
        svc, db, col = _make_svc()
        svc.create_component_has_vuln_edges = MagicMock()
        svc.create_finding_weakness_edges = MagicMock()
        svc.create_finding_in_component_edges = MagicMock()
        svc.create_finding_req_edges = MagicMock()
        svc.create_project_uses_component_edges = MagicMock()
        svc.create_detected_control_edges = MagicMock()
        svc.create_evidence_finding_edges = MagicMock()
        svc.create_evidence_project_edge = MagicMock()

        findings = [{"fingerprint": "fp20"}]
        sca_docs = [{"purl": "pkg:npm/x@1.0", "cve_id": "CVE-2023-1234"}]
        controls = [{"_key": "ctrl1"}]
        comp_docs = [{"purl": "pkg:npm/y@1.0"}]
        plans = []

        svc.create_all_edges(
            finding_docs=findings,
            component_docs=comp_docs,
            sca_vuln_docs=sca_docs,
            detected_control_docs=controls,
            edge_plans=plans,
            tenant_id="t1",
            project_id="proj1",
            evidence_pkg_key="pkg1",
        )

        svc.create_component_has_vuln_edges.assert_called_once_with(sca_docs, "t1")
        svc.create_finding_weakness_edges.assert_called_once_with(findings, "t1")
        svc.create_finding_in_component_edges.assert_called_once_with(findings, "t1")
        svc.create_finding_req_edges.assert_called_once_with(findings, plans, "t1")
        svc.create_project_uses_component_edges.assert_called_once_with(comp_docs, "proj1", "t1")
        svc.create_detected_control_edges.assert_called_once_with(controls, "t1")
        svc.create_evidence_finding_edges.assert_called_once_with("pkg1", findings, "t1")
        svc.create_evidence_project_edge.assert_called_once_with("pkg1", "proj1", "t1")

    def test_skips_sca_when_empty(self):
        svc, db, col = _make_svc()
        svc.create_component_has_vuln_edges = MagicMock()

        svc.create_all_edges(
            finding_docs=[],
            component_docs=[],
            sca_vuln_docs=[],
            detected_control_docs=[],
            edge_plans=[],
            tenant_id="t1",
        )

        svc.create_component_has_vuln_edges.assert_not_called()
