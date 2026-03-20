"""
Unit tests for ingestion_engine.py.

Covers: _get_field, _extract_list, all 9 pipeline steps, semgrep + checkov full
pipeline, bc_check_id dynamic override (DR-003), secret redaction, CVE validation.
"""

import hashlib
import json
import pytest

from complira_graph.ingestion.ingestion_engine import (
    IngestionEngine,
    IngestionBundle,
    _get_field,
    _extract_list,
)
from complira_graph.ingestion.adapter_registry import ADAPTER_REGISTRY, register_adapter


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

class TestGetField:
    def test_simple_key(self):
        assert _get_field({"a": 1}, "a") == 1

    def test_nested_dot_path(self):
        assert _get_field({"a": {"b": {"c": 42}}}, "a.b.c") == 42

    def test_check_result_nested(self):
        assert _get_field({"check_result": {"result": "FAILED"}}, "check_result.result") == "FAILED"

    def test_array_index(self):
        assert _get_field({"arr": [10, 20, 30]}, "arr[0]") == 10
        assert _get_field({"arr": [10, 20, 30]}, "arr[2]") == 30

    def test_mixed_dot_and_index(self):
        obj = {"locations": [{"physicalLocation": {"region": {"startLine": 5}}}]}
        assert _get_field(obj, "locations[0].physicalLocation.region.startLine") == 5

    def test_missing_key_returns_none(self):
        assert _get_field({"a": 1}, "b") is None

    def test_missing_nested_key_returns_none(self):
        assert _get_field({"a": {}}, "a.b.c") is None

    def test_none_input_returns_none(self):
        assert _get_field(None, "a.b") is None

    def test_out_of_range_index_returns_none(self):
        assert _get_field({"arr": [1]}, "arr[5]") is None

    def test_deep_trufflehog_path(self):
        obj = {"SourceMetadata": {"Data": {"Git": {"file": "foo.py", "line": 42}}}}
        assert _get_field(obj, "SourceMetadata.Data.Git.file") == "foo.py"
        assert _get_field(obj, "SourceMetadata.Data.Git.line") == 42


class TestExtractList:
    def test_simple_key(self):
        assert _extract_list({"matches": [1, 2]}, "matches") == [1, 2]

    def test_dot_path(self):
        data = {"results": {"failed_checks": [{"id": 1}, {"id": 2}]}}
        assert _extract_list(data, "results.failed_checks") == [{"id": 1}, {"id": 2}]

    def test_star_expansion_two_levels(self):
        data = {"site": [{"alerts": [{"id": 1}]}, {"alerts": [{"id": 2}]}]}
        assert _extract_list(data, "site[*].alerts[*]") == [{"id": 1}, {"id": 2}]

    def test_runs_results_sarif_pattern(self):
        data = {"runs": [{"results": [{"r": 1}]}, {"results": [{"r": 2}]}]}
        assert _extract_list(data, "runs[*].results[*]") == [{"r": 1}, {"r": 2}]

    def test_dot_star_flatten(self):
        data = {"categories": {"sast": [{"a": 1}], "secrets": [{"b": 2}]}}
        result = _extract_list(data, "categories.*[]")
        assert len(result) == 2

    def test_empty_path_returns_data(self):
        assert _extract_list([1, 2, 3], "") == [1, 2, 3]

    def test_missing_key_returns_empty(self):
        assert _extract_list({}, "results.findings") == []


# ---------------------------------------------------------------------------
# Fingerprint
# ---------------------------------------------------------------------------

class TestFingerprint:
    def test_deterministic(self):
        engine = IngestionEngine()
        adapter = ADAPTER_REGISTRY["semgrep"]
        raw = {"check_id": "rule1", "path": "foo.py", "start": {"line": 10}}
        fp1 = engine._fingerprint(adapter, raw)
        fp2 = engine._fingerprint(adapter, raw)
        assert fp1 == fp2

    def test_different_inputs_produce_different_fingerprints(self):
        engine = IngestionEngine()
        adapter = ADAPTER_REGISTRY["semgrep"]
        raw1 = {"check_id": "rule1", "path": "foo.py", "start": {"line": 10}}
        raw2 = {"check_id": "rule1", "path": "foo.py", "start": {"line": 11}}
        assert engine._fingerprint(adapter, raw1) != engine._fingerprint(adapter, raw2)

    def test_fingerprint_is_32_hex_chars(self):
        engine = IngestionEngine()
        adapter = ADAPTER_REGISTRY["gitleaks"]
        raw = {"Fingerprint": "abc123xyz"}
        fp = engine._fingerprint(adapter, raw)
        assert len(fp) == 32 and all(c in "0123456789abcdef" for c in fp)

    def test_checkov_fingerprint_uses_check_id_file_resource(self):
        engine = IngestionEngine()
        adapter = ADAPTER_REGISTRY["checkov"]
        raw = {"check_id": "CKV_AWS_1", "file_path": "main.tf", "resource": "aws_s3.foo"}
        fp = engine._fingerprint(adapter, raw)
        expected = hashlib.sha256("CKV_AWS_1|main.tf|aws_s3.foo".encode()).hexdigest()[:32]
        assert fp == expected


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

class TestRoute:
    def test_semgrep_routes_to_scan_findings(self):
        engine = IngestionEngine()
        adapter = ADAPTER_REGISTRY["semgrep"]
        assert engine._route(adapter, {}) == "scan_findings"

    def test_grype_routes_to_component_has_vuln(self):
        engine = IngestionEngine()
        adapter = ADAPTER_REGISTRY["grype"]
        assert engine._route(adapter, {}) == "component_has_vuln"

    def test_checkov_failed_routes_to_scan_findings(self):
        engine = IngestionEngine()
        adapter = ADAPTER_REGISTRY["checkov"]
        raw = {"check_result": {"result": "FAILED"}}
        assert engine._route(adapter, raw) == "scan_findings"

    def test_checkov_passed_routes_to_detected_controls(self):
        engine = IngestionEngine()
        adapter = ADAPTER_REGISTRY["checkov"]
        raw = {"check_result": {"result": "PASSED"}}
        assert engine._route(adapter, raw) == "detected_controls"

    def test_checkov_skipped_routes_to_audit_log(self):
        engine = IngestionEngine()
        adapter = ADAPTER_REGISTRY["checkov"]
        raw = {"check_result": {"result": "SKIPPED"}}
        assert engine._route(adapter, raw) == "audit_log"


# ---------------------------------------------------------------------------
# Severity classification
# ---------------------------------------------------------------------------

class TestClassifySeverity:
    def test_semgrep_error_maps_to_high(self):
        engine = IngestionEngine()
        adapter = ADAPTER_REGISTRY["semgrep"]
        assert engine._classify_severity(adapter, {"severity": "ERROR"}, {}) == "high"

    def test_semgrep_warning_maps_to_medium(self):
        engine = IngestionEngine()
        adapter = ADAPTER_REGISTRY["semgrep"]
        assert engine._classify_severity(adapter, {"severity": "WARNING"}, {}) == "medium"

    def test_checkov_none_severity_maps_to_none(self):
        engine = IngestionEngine()
        adapter = ADAPTER_REGISTRY["checkov"]
        assert engine._classify_severity(adapter, {}, {}) is None

    def test_grype_critical_maps_to_critical(self):
        # _classify_severity runs after _map_fields — severity is already extracted to top-level doc
        engine = IngestionEngine()
        adapter = ADAPTER_REGISTRY["grype"]
        assert engine._classify_severity(adapter, {}, {"severity": "Critical"}) == "critical"


# ---------------------------------------------------------------------------
# CWE extraction
# ---------------------------------------------------------------------------

class TestExtractCWE:
    def test_extracted_from_message_text(self):
        engine = IngestionEngine()
        adapter = ADAPTER_REGISTRY["semgrep"]
        doc = {"message": "SQL injection CWE-89 detected"}
        cwe_ids, source = engine._extract_cwe(adapter, {}, doc)
        assert "CWE-89" in cwe_ids
        assert source == "extracted"

    def test_extracted_deduplicates(self):
        engine = IngestionEngine()
        adapter = ADAPTER_REGISTRY["semgrep"]
        doc = {"message": "CWE-79 and CWE-79 again"}
        cwe_ids, _ = engine._extract_cwe(adapter, {}, doc)
        assert cwe_ids.count("CWE-79") == 1

    def test_absent_source_returns_empty(self):
        engine = IngestionEngine()
        adapter = ADAPTER_REGISTRY["checkov"]
        cwe_ids, source = engine._extract_cwe(adapter, {}, {"message": "something"})
        assert cwe_ids == []
        assert source is None

    def test_zap_int_cwe_normalised(self):
        engine = IngestionEngine()
        adapter = ADAPTER_REGISTRY["zap"]
        doc = {"_cwe_int": "79"}
        cwe_ids, source = engine._extract_cwe(adapter, {}, doc)
        assert "CWE-79" in cwe_ids
        assert source == "extracted"

    def test_normalise_cwe_values_list(self):
        result = IngestionEngine._normalise_cwe_values(["CWE-79", "CWE-89"])
        assert result == ["CWE-79", "CWE-89"]

    def test_normalise_cwe_values_int(self):
        assert IngestionEngine._normalise_cwe_values(79) == ["CWE-79"]

    def test_normalise_cwe_values_digit_string(self):
        assert IngestionEngine._normalise_cwe_values("89") == ["CWE-89"]


# ---------------------------------------------------------------------------
# Secret redaction
# ---------------------------------------------------------------------------

class TestRedact:
    def test_secret_is_redacted(self):
        engine = IngestionEngine()
        adapter = ADAPTER_REGISTRY["gitleaks"]
        doc = {"_secret_raw": "sk-REAL_SECRET_VALUE"}
        engine._redact(adapter, doc)
        assert "secret_redacted" in doc
        assert doc["secret_redacted"].startswith("[REDACTED:")
        assert "sk-REAL_SECRET_VALUE" not in doc["secret_redacted"]
        assert "_secret_raw" not in doc

    def test_no_secret_field_is_noop(self):
        engine = IngestionEngine()
        adapter = ADAPTER_REGISTRY["semgrep"]  # no secret_raw_field
        doc = {"rule_id": "r1"}
        engine._redact(adapter, doc)
        assert doc == {"rule_id": "r1"}

    def test_redacted_value_is_deterministic(self):
        engine = IngestionEngine()
        adapter = ADAPTER_REGISTRY["gitleaks"]
        doc1 = {"_secret_raw": "same_secret"}
        doc2 = {"_secret_raw": "same_secret"}
        engine._redact(adapter, doc1)
        engine._redact(adapter, doc2)
        assert doc1["secret_redacted"] == doc2["secret_redacted"]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidate:
    def test_valid_cve_kept(self):
        engine = IngestionEngine()
        doc = {"cve_id": "CVE-2024-12345"}
        engine._validate(doc)
        assert doc["cve_id"] == "CVE-2024-12345"

    def test_invalid_cve_demoted_to_tool_vuln_id(self):
        engine = IngestionEngine()
        doc = {"cve_id": "GHSA-1234-5678-abcd"}
        engine._validate(doc)
        assert "cve_id" not in doc
        assert doc["tool_vuln_id"] == "GHSA-1234-5678-abcd"

    def test_invalid_cve_does_not_overwrite_existing_tool_vuln_id(self):
        engine = IngestionEngine()
        doc = {"cve_id": "GHSA-bad", "tool_vuln_id": "existing"}
        engine._validate(doc)
        assert doc["tool_vuln_id"] == "existing"


# ---------------------------------------------------------------------------
# Plan edges — DR-003: bc_check_id dynamic override
# ---------------------------------------------------------------------------

class TestPlanEdges:
    def test_rule_engine_plans_req_edge(self):
        engine = IngestionEngine()
        adapter = ADAPTER_REGISTRY["semgrep"]
        doc = {"fingerprint": "fp1", "cwe_ids": ["CWE-89"]}
        edges = engine._plan_edges(adapter, doc, "scan_findings")
        assert len(edges) == 1
        assert edges[0]["source"] == "rule_engine"
        assert edges[0]["_from"] == "scan_findings/fp1"

    def test_none_req_mapping_source_returns_empty(self):
        engine = IngestionEngine()
        adapter = ADAPTER_REGISTRY["gitleaks"]
        doc = {"fingerprint": "fp1"}
        edges = engine._plan_edges(adapter, doc, "scan_findings")
        assert edges == []

    def test_grype_routes_to_component_has_vuln_no_req_edges(self):
        engine = IngestionEngine()
        adapter = ADAPTER_REGISTRY["grype"]
        doc = {"fingerprint": "fp1"}
        # grype collection = component_has_vuln, not scan_findings → no edges
        edges = engine._plan_edges(adapter, doc, "component_has_vuln")
        assert edges == []

    def test_checkov_native_with_bc_check_id_stays_checkov_native(self):
        """DR-003 primary path: bc_check_id present → checkov_native kept."""
        engine = IngestionEngine()
        adapter = ADAPTER_REGISTRY["checkov"]
        doc = {"fingerprint": "fp1", "bc_check_id": "BC_AWS_1"}
        edges = engine._plan_edges(adapter, doc, "scan_findings")
        assert edges[0]["source"] == "checkov_native"
        assert edges[0]["bc_check_id"] == "BC_AWS_1"

    def test_checkov_native_without_bc_check_id_overrides_to_llm_reg_mapper(self):
        """DR-003 fallback: bc_check_id absent → override to llm_reg_mapper."""
        engine = IngestionEngine()
        adapter = ADAPTER_REGISTRY["checkov"]
        doc = {"fingerprint": "fp1"}  # no bc_check_id
        edges = engine._plan_edges(adapter, doc, "scan_findings")
        assert edges[0]["source"] == "llm_reg_mapper"
        assert edges[0]["bc_check_id"] is None

    def test_detected_controls_collection_returns_no_edges(self):
        engine = IngestionEngine()
        adapter = ADAPTER_REGISTRY["checkov"]
        doc = {"fingerprint": "fp1", "bc_check_id": "BC_AWS_1"}
        edges = engine._plan_edges(adapter, doc, "detected_controls")
        assert edges == []


# ---------------------------------------------------------------------------
# Full pipeline: semgrep end-to-end
# ---------------------------------------------------------------------------

SEMGREP_PAYLOAD = json.dumps({
    "results": [
        {
            "check_id": "python.lang.security.audit.sqli.sqli",
            "path": "app/db.py",
            "start": {"line": 42, "col": 1},
            "end": {"line": 42, "col": 50},
            "extra": {
                "severity": "ERROR",
                "message": "SQL injection detected",
                "metadata": {
                    "cwe": ["CWE-89: Improper Neutralization of Special Elements used in an SQL Command"],
                    "owasp": ["A01:2021 - Injection"],
                    "confidence": "HIGH",
                    "references": ["https://owasp.org/Top10/A03_2021-Injection/"],
                },
                "lines": "cursor.execute(f\"SELECT * FROM users WHERE id={user_id}\")",
            },
        }
    ],
    "errors": [],
    "paths": {"scanned": ["app/db.py"], "ignored": []},
}).encode()


class TestSemgrepPipeline:
    def setup_method(self):
        self.engine = IngestionEngine()

    def test_produces_one_bundle(self):
        bundles = self.engine.process("semgrep", SEMGREP_PAYLOAD, "run1", "t1")
        assert len(bundles) == 1

    def test_routes_to_scan_findings(self):
        bundles = self.engine.process("semgrep", SEMGREP_PAYLOAD, "run1", "t1")
        assert bundles[0].collection == "scan_findings"

    def test_severity_mapped_to_high(self):
        bundles = self.engine.process("semgrep", SEMGREP_PAYLOAD, "run1", "t1")
        assert bundles[0].document["severity"] == "high"

    def test_cwe_extracted_from_metadata(self):
        bundles = self.engine.process("semgrep", SEMGREP_PAYLOAD, "run1", "t1")
        assert "CWE-89" in bundles[0].document["cwe_ids"]

    def test_rule_id_mapped_from_check_id(self):
        bundles = self.engine.process("semgrep", SEMGREP_PAYLOAD, "run1", "t1")
        assert bundles[0].document["rule_id"] == "python.lang.security.audit.sqli.sqli"

    def test_file_path_mapped_from_path(self):
        bundles = self.engine.process("semgrep", SEMGREP_PAYLOAD, "run1", "t1")
        assert bundles[0].document["file_path"] == "app/db.py"

    def test_line_start_mapped_from_start_line(self):
        bundles = self.engine.process("semgrep", SEMGREP_PAYLOAD, "run1", "t1")
        assert bundles[0].document["line_start"] == 42

    def test_canonical_metadata_set(self):
        bundles = self.engine.process("semgrep", SEMGREP_PAYLOAD, "run1", "t1")
        doc = bundles[0].document
        assert doc["tenant_id"] == "t1"
        assert doc["scan_run_id"] == "run1"
        assert doc["tool"] == "semgrep"
        assert doc["finding_type"] == "sast"

    def test_fingerprint_present_and_32_chars(self):
        bundles = self.engine.process("semgrep", SEMGREP_PAYLOAD, "run1", "t1")
        fp = bundles[0].document["fingerprint"]
        assert len(fp) == 32

    def test_key_equals_fingerprint(self):
        bundles = self.engine.process("semgrep", SEMGREP_PAYLOAD, "run1", "t1")
        doc = bundles[0].document
        assert doc["_key"] == doc["fingerprint"]

    def test_req_edge_planned_with_rule_engine(self):
        bundles = self.engine.process("semgrep", SEMGREP_PAYLOAD, "run1", "t1")
        edges = bundles[0].edges
        assert len(edges) == 1
        assert edges[0]["source"] == "rule_engine"

    def test_idempotent_same_payload_same_fingerprint(self):
        b1 = self.engine.process("semgrep", SEMGREP_PAYLOAD, "run1", "t1")
        b2 = self.engine.process("semgrep", SEMGREP_PAYLOAD, "run1", "t1")
        assert b1[0].document["fingerprint"] == b2[0].document["fingerprint"]

    def test_no_staging_fields_in_output(self):
        bundles = self.engine.process("semgrep", SEMGREP_PAYLOAD, "run1", "t1")
        for key in bundles[0].document:
            assert not key.startswith("_") or key == "_key", f"Staging field leaked: {key}"


# ---------------------------------------------------------------------------
# Full pipeline: checkov end-to-end (UC-017, UC-018, UC-019)
# ---------------------------------------------------------------------------

CHECKOV_PAYLOAD = json.dumps({
    "check_type": "terraform",
    "failed_checks": [
        {
            "check_id": "CKV_AWS_1",
            "check_name": "Encryption",
            "check_result": {"result": "FAILED"},
            "file_path": "main.tf",
            "resource": "aws_s3_bucket.data",
            "file_line_range": [1, 10],
            "guideline": "https://docs.example.com/ckv_aws_1",
        }
    ],
    "passed_checks": [
        {
            "check_id": "CKV_AWS_2",
            "check_name": "Versioning",
            "check_result": {"result": "PASSED"},
            "file_path": "main.tf",
            "resource": "aws_s3_bucket.data",
            "file_line_range": [1, 10],
        }
    ],
    "skipped_checks": [
        {
            "check_id": "CKV_AWS_3",
            "check_name": "Logging",
            "check_result": {"result": "SKIPPED"},
            "file_path": "main.tf",
            "resource": "aws_s3_bucket.data",
            "suppress_comment": "Not applicable",
        }
    ],
    "parsing_errors": [],
}).encode()


class TestCheckovPipeline:
    def setup_method(self):
        self.engine = IngestionEngine()
        bundles = self.engine.process("checkov", CHECKOV_PAYLOAD, "run_ck", "tenant_ck")
        self.by_col = {b.collection: b for b in bundles}

    def test_three_bundles_produced(self):
        bundles = self.engine.process("checkov", CHECKOV_PAYLOAD, "run_ck", "tenant_ck")
        assert len(bundles) == 3

    def test_failed_routes_to_scan_findings(self):
        assert "scan_findings" in self.by_col

    def test_passed_routes_to_detected_controls(self):
        assert "detected_controls" in self.by_col

    def test_skipped_routes_to_audit_log(self):
        assert "audit_log" in self.by_col

    def test_failed_check_id_mapped(self):
        assert self.by_col["scan_findings"].document["check_id"] == "CKV_AWS_1"

    def test_iac_framework_injected_from_doc_level(self):
        """UC-017: @check_type injection populates iac_framework."""
        assert self.by_col["scan_findings"].document["iac_framework"] == "terraform"

    def test_resource_maps_to_resource_address(self):
        assert self.by_col["scan_findings"].document["resource_address"] == "aws_s3_bucket.data"

    def test_check_result_value_is_string(self):
        assert self.by_col["scan_findings"].document["check_result"] == "FAILED"

    def test_triage_status_compliant_on_detected_control(self):
        """UC-019: PASSED → detected_controls with triage_status=compliant."""
        assert self.by_col["detected_controls"].document["triage_status"] == "compliant"

    def test_audit_log_check_id_present(self):
        assert self.by_col["audit_log"].document["check_id"] == "CKV_AWS_3"

    def test_failed_no_bc_check_id_produces_llm_reg_mapper_edge(self):
        """DR-003: bc_check_id absent → llm_reg_mapper override."""
        edges = self.by_col["scan_findings"].edges
        assert edges[0]["source"] == "llm_reg_mapper"

    def test_bc_check_id_present_produces_checkov_native_edge(self):
        """UC-018 primary: bc_check_id present → checkov_native."""
        payload = json.dumps({
            "check_type": "terraform",
            "failed_checks": [{
                "check_id": "CKV_AWS_1", "bc_check_id": "BC_AWS_1",
                "check_name": "Enc", "check_result": {"result": "FAILED"},
                "file_path": "main.tf", "resource": "aws_s3.b",
            }],
            "passed_checks": [], "skipped_checks": [], "parsing_errors": [],
        }).encode()
        bundles = self.engine.process("checkov", payload, "run2", "t2")
        finding_bundle = next(b for b in bundles if b.collection == "scan_findings")
        assert finding_bundle.edges[0]["source"] == "checkov_native"
        assert finding_bundle.edges[0]["bc_check_id"] == "BC_AWS_1"


# ---------------------------------------------------------------------------
# Gitleaks secret redaction pipeline
# ---------------------------------------------------------------------------

GITLEAKS_PAYLOAD = json.dumps([
    {
        "RuleID": "generic-api-key",
        "File": "config.py",
        "StartLine": 42,
        "EndLine": 42,
        "Description": "API key found",
        "Match": "sk-real_secret_value",
        "Commit": "deadbeef",
        "Fingerprint": "fp_gl_1",
    }
]).encode()


class TestGitleaksPipeline:
    def setup_method(self):
        self.engine = IngestionEngine()
        self.bundles = self.engine.process("gitleaks", GITLEAKS_PAYLOAD, "run_gl", "t_gl")

    def test_produces_one_bundle(self):
        assert len(self.bundles) == 1

    def test_secret_is_redacted(self):
        doc = self.bundles[0].document
        assert "secret_redacted" in doc
        assert "sk-real_secret_value" not in str(doc)

    def test_no_req_edge_planned(self):
        assert self.bundles[0].edges == []

    def test_finding_type_is_secret(self):
        assert self.bundles[0].document["finding_type"] == "secret"
