"""
Unit tests for adapter_registry.py.

Covers: registry loads at import, all required keys present,
register_adapter accepts valid + rejects invalid, DFL-001 iam_reg_mapper reserved.
"""

import pytest
from complira_graph.ingestion.adapter_registry import (
    ADAPTER_REGISTRY,
    register_adapter,
    _REQUIRED_ADAPTER_KEYS,
    pip_audit_flatten,
)


class TestAdapterRegistryLoads:
    def test_registry_is_not_empty(self):
        assert len(ADAPTER_REGISTRY) >= 8

    def test_all_expected_tools_present(self):
        expected = {
            "semgrep", "semgrep_custom", "checkov", "gitleaks", "grype",
            "trufflehog", "zap", "sarif",
            "trivy", "npm_audit", "pip_audit", "sonarqube", "spotbugs",
        }
        assert expected.issubset(set(ADAPTER_REGISTRY.keys()))

    def test_all_adapters_have_required_keys(self):
        for name, adapter in ADAPTER_REGISTRY.items():
            missing = _REQUIRED_ADAPTER_KEYS - set(adapter.keys())
            assert not missing, f"Adapter '{name}' missing keys: {missing}"


class TestCheckovAdapterConfig:
    def test_multi_root_configured(self):
        ck = ADAPTER_REGISTRY["checkov"]
        assert "failed_checks" in ck["multi_root"]
        assert "passed_checks" in ck["multi_root"]
        assert "skipped_checks" in ck["multi_root"]

    def test_result_state_field_is_nested(self):
        assert ADAPTER_REGISTRY["checkov"]["result_state_field"] == "check_result.result"

    def test_result_routing_covers_all_states(self):
        routing = ADAPTER_REGISTRY["checkov"]["result_routing"]
        assert routing["FAILED"] == "scan_findings"
        assert routing["PASSED"] == "detected_controls"
        assert routing["SKIPPED"] == "audit_log"

    def test_iac_framework_injection_key(self):
        assert "@check_type" in ADAPTER_REGISTRY["checkov"]["field_map"]

    def test_resource_maps_to_resource_address(self):
        assert ADAPTER_REGISTRY["checkov"]["field_map"]["resource"] == "resource_address"

    def test_req_mapping_source_is_checkov_native(self):
        assert ADAPTER_REGISTRY["checkov"]["req_mapping_source"] == "checkov_native"

    def test_deterministic_req_fields_contains_bc_check_id(self):
        assert "bc_check_id" in ADAPTER_REGISTRY["checkov"]["deterministic_req_fields"]

    def test_cwe_source_is_absent(self):
        assert ADAPTER_REGISTRY["checkov"]["cwe_source"] == "absent"


class TestGrypeAdapterConfig:
    def test_routes_to_component_has_vuln(self):
        assert ADAPTER_REGISTRY["grype"]["result_routing"]["*"] == "component_has_vuln"

    def test_location_anchor_is_purl(self):
        assert ADAPTER_REGISTRY["grype"]["location_anchor"] == "purl"

    def test_req_mapping_source_is_none(self):
        assert ADAPTER_REGISTRY["grype"]["req_mapping_source"] == "none"


class TestSemgrepAdapterConfig:
    def test_cwe_source_is_extracted(self):
        assert ADAPTER_REGISTRY["semgrep"]["cwe_source"] == "extracted"

    def test_cwe_extract_pattern_present(self):
        assert ADAPTER_REGISTRY["semgrep"]["cwe_extract_pattern"] is not None

    def test_req_mapping_source_is_rule_engine(self):
        assert ADAPTER_REGISTRY["semgrep"]["req_mapping_source"] == "rule_engine"


class TestReqMappingSourceLiteral:
    """DFL-001: iam_reg_mapper must be reserved in the Literal type."""

    def test_iam_reg_mapper_is_valid_value(self):
        # Verify the Literal includes iam_reg_mapper by attempting registration
        # with it — if it were not in the Literal, TypedDict would still accept it
        # at runtime, but we validate this by checking the string is a known value.
        from complira_graph.ingestion.adapter_registry import ReqMappingSource
        import typing
        args = typing.get_args(ReqMappingSource)
        assert "iam_reg_mapper" in args, (
            "DFL-001: iam_reg_mapper must be reserved in ReqMappingSource Literal"
        )


class TestRegisterAdapter:
    def test_register_valid_adapter(self):
        adapter = {
            "tool_name": "_test_tool",
            "parse_format": "json_array",
            "fingerprint_fields": ["id", "file"],
            "severity_map": {"HIGH": "high"},
            "default_finding_type": "sast",
            "result_routing": {"*": "scan_findings"},
            "location_anchor": "file_line",
            "field_map": {"id": "rule_id"},
            "cwe_source": "absent",
            "req_mapping_source": "none",
        }
        register_adapter(adapter)
        assert "_test_tool" in ADAPTER_REGISTRY
        # cleanup
        del ADAPTER_REGISTRY["_test_tool"]

    def test_register_missing_required_key_raises(self):
        with pytest.raises(ValueError, match="missing required keys"):
            register_adapter({"tool_name": "_bad"})  # missing almost everything

    def test_register_overwrites_existing(self):
        original = dict(ADAPTER_REGISTRY.get("sarif", {}))
        register_adapter({**original, "tool_name": "sarif"})
        assert ADAPTER_REGISTRY["sarif"]["tool_name"] == "sarif"


class TestZapAdapterConfig:
    def test_fingerprint_uses_url_not_uri(self):
        zap = ADAPTER_REGISTRY["zap"]
        assert "url" in zap["fingerprint_fields"]
        assert "uri" not in zap["fingerprint_fields"]

    def test_field_map_uses_url(self):
        zap = ADAPTER_REGISTRY["zap"]
        assert "url" in zap["field_map"]
        assert "uri" not in zap["field_map"]

    def test_field_map_includes_other(self):
        assert "other" in ADAPTER_REGISTRY["zap"]["field_map"]

    def test_no_instances_fanout_comment(self):
        # pre_process should be None with no lingering TODO comment (code-level check only)
        assert ADAPTER_REGISTRY["zap"]["pre_process"] is None


class TestCheckovSeverityFallback:
    def test_severity_map_none_is_medium(self):
        assert ADAPTER_REGISTRY["checkov"]["severity_map"][None] == "medium"


class TestTrivyAdapterConfig:
    def test_routes_to_component_has_vuln(self):
        assert ADAPTER_REGISTRY["trivy"]["result_routing"]["*"] == "component_has_vuln"

    def test_parse_root_covers_nested_vulnerabilities(self):
        assert ADAPTER_REGISTRY["trivy"]["parse_root"] == "Results[*].Vulnerabilities[*]"

    def test_cve_id_mapped_from_vulnerability_id(self):
        assert ADAPTER_REGISTRY["trivy"]["field_map"]["VulnerabilityID"] == "cve_id"

    def test_cwe_source_is_tool_direct(self):
        assert ADAPTER_REGISTRY["trivy"]["cwe_source"] == "tool_direct"

    def test_cwe_raw_mapped_from_cwe_ids(self):
        assert ADAPTER_REGISTRY["trivy"]["field_map"]["CweIDs"] == "_cwe_raw"

    def test_severity_map_covers_all_trivy_levels(self):
        sev = ADAPTER_REGISTRY["trivy"]["severity_map"]
        assert sev["CRITICAL"] == "critical"
        assert sev["HIGH"] == "high"
        assert sev["MEDIUM"] == "medium"
        assert sev["LOW"] == "low"
        assert sev["UNKNOWN"] is None

    def test_req_mapping_is_none(self):
        assert ADAPTER_REGISTRY["trivy"]["req_mapping_source"] == "none"


class TestNpmAuditAdapterConfig:
    def test_routes_to_component_has_vuln(self):
        assert ADAPTER_REGISTRY["npm_audit"]["result_routing"]["*"] == "component_has_vuln"

    def test_parse_root_flattens_vulnerabilities_object(self):
        assert ADAPTER_REGISTRY["npm_audit"]["parse_root"] == "vulnerabilities.*[]"

    def test_fingerprint_uses_name_and_range(self):
        fp = ADAPTER_REGISTRY["npm_audit"]["fingerprint_fields"]
        assert "name" in fp
        assert "range" in fp

    def test_severity_map_covers_npm_levels(self):
        sev = ADAPTER_REGISTRY["npm_audit"]["severity_map"]
        assert sev["critical"] == "critical"
        assert sev["high"] == "high"
        assert sev["moderate"] == "medium"
        assert sev["low"] == "low"
        assert sev["info"] == "info"

    def test_req_mapping_is_none(self):
        assert ADAPTER_REGISTRY["npm_audit"]["req_mapping_source"] == "none"


class TestPipAuditAdapterConfig:
    def test_routes_to_component_has_vuln(self):
        assert ADAPTER_REGISTRY["pip_audit"]["result_routing"]["*"] == "component_has_vuln"

    def test_parse_root_is_none(self):
        assert ADAPTER_REGISTRY["pip_audit"]["parse_root"] is None

    def test_pre_process_is_pip_audit_flatten(self):
        assert ADAPTER_REGISTRY["pip_audit"]["pre_process"] is pip_audit_flatten

    def test_fingerprint_uses_id_and_pkg_name(self):
        fp = ADAPTER_REGISTRY["pip_audit"]["fingerprint_fields"]
        assert "id" in fp
        assert "pkg_name" in fp

    def test_severity_map_has_no_defaults(self):
        assert ADAPTER_REGISTRY["pip_audit"]["severity_map"].get(None) is None

    def test_req_mapping_is_none(self):
        assert ADAPTER_REGISTRY["pip_audit"]["req_mapping_source"] == "none"


class TestPipAuditFlatten:
    def _sample_output(self):
        return [{
            "dependencies": [
                {
                    "name": "requests",
                    "version": "2.28.0",
                    "vulns": [
                        {
                            "id": "PYSEC-2022-48",
                            "fix_versions": ["2.29.0"],
                            "aliases": ["CVE-2022-29244"],
                            "description": "A vulnerability...",
                        }
                    ],
                },
                {
                    "name": "safe-pkg",
                    "version": "1.0.0",
                    "vulns": [],
                },
            ],
            "fixes": [],
        }]

    def test_flattens_vulns_with_parent_name(self):
        result = pip_audit_flatten(self._sample_output())
        assert len(result) == 1
        assert result[0]["pkg_name"] == "requests"
        assert result[0]["pkg_version"] == "2.28.0"

    def test_hoists_cve_from_aliases(self):
        result = pip_audit_flatten(self._sample_output())
        assert result[0]["cve_id"] == "CVE-2022-29244"

    def test_preserves_original_id(self):
        result = pip_audit_flatten(self._sample_output())
        assert result[0]["id"] == "PYSEC-2022-48"

    def test_dep_with_no_vulns_not_included(self):
        result = pip_audit_flatten(self._sample_output())
        pkg_names = [r["pkg_name"] for r in result]
        assert "safe-pkg" not in pkg_names

    def test_empty_input_returns_empty(self):
        assert pip_audit_flatten([]) == []

    def test_no_cve_alias_skipped_gracefully(self):
        findings = [{"dependencies": [
            {"name": "pkg", "version": "1.0", "vulns": [
                {"id": "GHSA-xxxx-yyyy", "aliases": ["GHSA-xxxx-yyyy"], "fix_versions": []}
            ]}
        ], "fixes": []}]
        result = pip_audit_flatten(findings)
        assert result[0].get("cve_id") is None
        assert result[0]["id"] == "GHSA-xxxx-yyyy"


class TestSonarqubeAdapterConfig:
    def test_routes_to_scan_findings(self):
        assert ADAPTER_REGISTRY["sonarqube"]["result_routing"]["*"] == "scan_findings"

    def test_parse_root_is_issues(self):
        assert ADAPTER_REGISTRY["sonarqube"]["parse_root"] == "issues"

    def test_fingerprint_uses_key(self):
        assert ADAPTER_REGISTRY["sonarqube"]["fingerprint_fields"] == ["key"]

    def test_field_map_has_both_severity_paths(self):
        fm = ADAPTER_REGISTRY["sonarqube"]["field_map"]
        assert "severity" in fm              # legacy (pre-v10)
        assert "impacts[0].severity" in fm   # modern (v10+)

    def test_modern_severity_comes_after_legacy_in_field_map(self):
        keys = list(ADAPTER_REGISTRY["sonarqube"]["field_map"].keys())
        assert keys.index("severity") < keys.index("impacts[0].severity")

    def test_severity_map_covers_legacy_and_modern(self):
        sev = ADAPTER_REGISTRY["sonarqube"]["severity_map"]
        assert sev["BLOCKER"] == "critical"
        assert sev["CRITICAL"] == "critical"
        assert sev["MAJOR"] == "high"
        assert sev["MINOR"] == "low"
        assert sev["INFO"] == "info"
        assert sev["HIGH"] == "high"
        assert sev["MEDIUM"] == "medium"
        assert sev["LOW"] == "low"

    def test_cwe_source_is_extracted(self):
        assert ADAPTER_REGISTRY["sonarqube"]["cwe_source"] == "extracted"


class TestSpotBugsAdapterConfig:
    def test_parse_format_is_xml(self):
        assert ADAPTER_REGISTRY["spotbugs"]["parse_format"] == "xml"

    def test_parse_root_is_bugcollection_buginstance(self):
        assert ADAPTER_REGISTRY["spotbugs"]["parse_root"] == "BugCollection/BugInstance"

    def test_fingerprint_uses_type_and_source_line(self):
        fp = ADAPTER_REGISTRY["spotbugs"]["fingerprint_fields"]
        assert "type" in fp
        assert "sl_classname" in fp
        assert "sl_start" in fp

    def test_severity_map_covers_priority_values(self):
        sev = ADAPTER_REGISTRY["spotbugs"]["severity_map"]
        assert sev["1"] == "high"
        assert sev["2"] == "medium"
        assert sev["3"] == "low"
        assert sev["4"] == "info"

    def test_routes_to_scan_findings(self):
        assert ADAPTER_REGISTRY["spotbugs"]["result_routing"]["*"] == "scan_findings"

    def test_cwe_source_is_extracted(self):
        assert ADAPTER_REGISTRY["spotbugs"]["cwe_source"] == "extracted"

    def test_sl_sourcepath_maps_to_file_path(self):
        assert ADAPTER_REGISTRY["spotbugs"]["field_map"]["sl_sourcepath"] == "file_path"
