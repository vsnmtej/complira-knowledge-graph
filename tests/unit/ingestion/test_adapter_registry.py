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
)


class TestAdapterRegistryLoads:
    def test_registry_is_not_empty(self):
        assert len(ADAPTER_REGISTRY) >= 8

    def test_all_expected_tools_present(self):
        expected = {"semgrep", "semgrep_custom", "checkov", "gitleaks", "grype", "trufflehog", "zap", "sarif"}
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
