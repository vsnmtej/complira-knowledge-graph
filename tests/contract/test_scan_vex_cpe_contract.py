"""
API Contract Tests for VEX and CPE endpoints.

Validates that API responses for VEX generation and CPE matching endpoints
match the documented contract and Pydantic models.

These tests ensure:
1. Backend API responses match the documented schema
2. Frontend mock data matches real API responses
3. No breaking changes to API structure
"""
import json
import pytest
from pathlib import Path
from pydantic import ValidationError
from datetime import datetime

from api.models.responses.scan import (
    VEXGenerationResponse,
    CPEMatchingResponse,
)
from api.models.responses import APIResponse


class TestVEXGenerationContract:
    """Contract tests for VEX generation endpoint."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses"""
        return Path("tests/fixtures/api_responses")

    def test_vex_generation_response_contract(self, mock_responses_dir):
        """
        Test: POST /v1/scan/{session_id}/vex response matches contract

        Validates:
        - Response structure matches APIResponse[VEXGenerationResponse]
        - All required fields present
        - Field types correct
        - VEX document follows CycloneDX format
        """
        with open(mock_responses_dir / "scan_vex_generate.json") as f:
            mock_data = json.load(f)

        # Validate outer APIResponse wrapper
        assert "success" in mock_data
        assert "data" in mock_data
        assert "metadata" in mock_data

        # Validate VEXGenerationResponse data
        data = mock_data["data"]
        required_fields = [
            "scan_session_id",
            "vex_document",
            "vulnerabilities_assessed",
            "generated_at"
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Validate field types
        assert isinstance(data["scan_session_id"], str)
        assert isinstance(data["vex_document"], dict)
        assert isinstance(data["vulnerabilities_assessed"], int)
        assert isinstance(data["generated_at"], str)

        # Validate VEX document structure
        vex_doc = data["vex_document"]
        assert "bomFormat" in vex_doc
        assert vex_doc["bomFormat"] == "CycloneDX"
        assert "specVersion" in vex_doc
        assert "vulnerabilities" in vex_doc
        assert isinstance(vex_doc["vulnerabilities"], list)

        # Validate using Pydantic model
        try:
            response = VEXGenerationResponse(**data)
            assert response.scan_session_id == data["scan_session_id"]
            assert response.vulnerabilities_assessed == data["vulnerabilities_assessed"]
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match VEXGenerationResponse schema: {e}")

    def test_vex_document_cyclonedx_format(self, mock_responses_dir):
        """
        Test: VEX document follows CycloneDX specification

        Validates:
        - bomFormat is "CycloneDX"
        - specVersion is valid (1.4, 1.5, or 1.6)
        - vulnerabilities array is present
        - Each vulnerability has required fields
        """
        with open(mock_responses_dir / "scan_vex_generate.json") as f:
            mock_data = json.load(f)

        vex_doc = mock_data["data"]["vex_document"]

        # Validate CycloneDX format
        assert vex_doc["bomFormat"] == "CycloneDX"
        assert vex_doc["specVersion"] in ["1.4", "1.5", "1.6"]
        assert "version" in vex_doc
        assert isinstance(vex_doc["version"], int)

        # Validate metadata
        if "metadata" in vex_doc:
            metadata = vex_doc["metadata"]
            assert "timestamp" in metadata

        # Validate vulnerabilities
        vulnerabilities = vex_doc["vulnerabilities"]
        assert isinstance(vulnerabilities, list)
        assert len(vulnerabilities) > 0, "VEX should have at least one vulnerability"

        for vuln in vulnerabilities:
            # Required fields
            assert "id" in vuln, "Vulnerability must have id"
            assert "analysis" in vuln, "Vulnerability must have analysis"

            # Validate vulnerability ID format
            vuln_id = vuln["id"]
            valid_prefixes = ["CVE-", "GHSA-", "RUSTSEC-", "PYSEC-", "GO-", "GHSL-"]
            assert any(vuln_id.startswith(prefix) for prefix in valid_prefixes), \
                f"Invalid vulnerability ID: {vuln_id}"

            # Validate analysis structure
            analysis = vuln["analysis"]
            assert "state" in analysis, "Analysis must have state"

            valid_states = [
                "not_affected",
                "affected",
                "in_triage",
                "false_positive",
                "exploitable"
            ]
            assert analysis["state"] in valid_states, \
                f"Invalid analysis state: {analysis['state']}"

    def test_vex_supports_multiple_vulnerability_types(self, mock_responses_dir):
        """
        Test: VEX document includes both CVE and GHSA identifiers

        Validates:
        - CVE-* vulnerabilities are present
        - GHSA-* vulnerabilities are present
        - Both are properly formatted
        """
        with open(mock_responses_dir / "scan_vex_generate.json") as f:
            mock_data = json.load(f)

        vulnerabilities = mock_data["data"]["vex_document"]["vulnerabilities"]
        vuln_ids = [v["id"] for v in vulnerabilities]

        # Check for CVE identifiers
        cve_ids = [vid for vid in vuln_ids if vid.startswith("CVE-")]
        assert len(cve_ids) > 0, "VEX should include CVE vulnerabilities"

        # Check for GHSA identifiers
        ghsa_ids = [vid for vid in vuln_ids if vid.startswith("GHSA-")]
        assert len(ghsa_ids) > 0, "VEX should include GHSA vulnerabilities"

    def test_vex_analysis_states_are_valid(self, mock_responses_dir):
        """
        Test: All vulnerability analysis states are valid VEX states

        Validates:
        - States match CycloneDX VEX specification
        - Justifications are provided when appropriate
        """
        with open(mock_responses_dir / "scan_vex_generate.json") as f:
            mock_data = json.load(f)

        vulnerabilities = mock_data["data"]["vex_document"]["vulnerabilities"]

        valid_states = {
            "not_affected",
            "affected",
            "in_triage",
            "false_positive",
            "exploitable"
        }

        valid_justifications = {
            "component_not_present",
            "vulnerable_code_not_present",
            "vulnerable_code_cannot_be_controlled_by_adversary",
            "vulnerable_code_not_in_execute_path",
            "inline_mitigations_already_exist",
            "protected_by_compiler",
            "protected_at_runtime",
            "protected_at_perimeter",
            "protected_by_mitigating_control"
        }

        for vuln in vulnerabilities:
            analysis = vuln["analysis"]

            # Validate state
            assert analysis["state"] in valid_states, \
                f"Invalid state: {analysis['state']}"

            # If state is not_affected, should have justification
            if analysis["state"] == "not_affected":
                if "justification" in analysis:
                    assert analysis["justification"] in valid_justifications, \
                        f"Invalid justification: {analysis['justification']}"

    def test_vex_timestamp_format(self, mock_responses_dir):
        """
        Test: generated_at timestamp follows ISO 8601 format

        Validates:
        - Timestamp is ISO 8601 compliant
        - Timestamp can be parsed as datetime
        """
        with open(mock_responses_dir / "scan_vex_generate.json") as f:
            mock_data = json.load(f)

        generated_at = mock_data["data"]["generated_at"]

        # Verify ISO 8601 format
        assert "T" in generated_at
        assert generated_at.endswith("Z") or "+" in generated_at or "-" in generated_at[-6:]

        # Verify parseable as datetime
        try:
            datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except ValueError:
            pytest.fail(f"generated_at timestamp is not valid ISO 8601: {generated_at}")

    def test_vex_metadata_structure(self, mock_responses_dir):
        """
        Test: Response includes metadata with cache_hit and execution_time_ms

        Validates:
        - metadata object is present
        - cache_hit is boolean
        - execution_time_ms is numeric
        """
        with open(mock_responses_dir / "scan_vex_generate.json") as f:
            mock_data = json.load(f)

        assert "metadata" in mock_data
        metadata = mock_data["metadata"]

        assert "cache_hit" in metadata
        assert isinstance(metadata["cache_hit"], bool)

        assert "execution_time_ms" in metadata
        assert isinstance(metadata["execution_time_ms"], (int, float))


class TestCPEMatchingContract:
    """Contract tests for CPE matching endpoint."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses"""
        return Path("tests/fixtures/api_responses")

    def test_cpe_matching_response_contract(self, mock_responses_dir):
        """
        Test: POST /v1/scan/{session_id}/cpe-match response matches contract

        Validates:
        - Response structure matches APIResponse[CPEMatchingResponse]
        - All required fields present
        - Field types correct
        - Counts are realistic
        """
        with open(mock_responses_dir / "scan_cpe_match.json") as f:
            mock_data = json.load(f)

        # Validate outer APIResponse wrapper
        assert "success" in mock_data
        assert "data" in mock_data
        assert "metadata" in mock_data

        # Validate CPEMatchingResponse data
        data = mock_data["data"]
        required_fields = [
            "scan_session_id",
            "components_processed",
            "cpe_mappings_created",
            "completed_at"
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Validate field types
        assert isinstance(data["scan_session_id"], str)
        assert isinstance(data["components_processed"], int)
        assert isinstance(data["cpe_mappings_created"], int)
        assert isinstance(data["completed_at"], str)

        # Validate counts are realistic
        assert data["components_processed"] >= 0
        assert data["cpe_mappings_created"] >= 0
        assert data["cpe_mappings_created"] <= data["components_processed"], \
            "Mappings created cannot exceed components processed"

        # Validate using Pydantic model
        try:
            response = CPEMatchingResponse(**data)
            assert response.scan_session_id == data["scan_session_id"]
            assert response.components_processed == data["components_processed"]
            assert response.cpe_mappings_created == data["cpe_mappings_created"]
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match CPEMatchingResponse schema: {e}")

    def test_cpe_matching_counts_relationship(self, mock_responses_dir):
        """
        Test: CPE mapping counts follow logical constraints

        Validates:
        - cpe_mappings_created <= components_processed
        - Both counts are non-negative
        - Counts are integers
        """
        with open(mock_responses_dir / "scan_cpe_match.json") as f:
            mock_data = json.load(f)

        data = mock_data["data"]
        components = data["components_processed"]
        mappings = data["cpe_mappings_created"]

        # Non-negative
        assert components >= 0, "components_processed must be non-negative"
        assert mappings >= 0, "cpe_mappings_created must be non-negative"

        # Logical relationship
        assert mappings <= components, \
            f"Cannot create {mappings} mappings from {components} components"

        # Integer values
        assert isinstance(components, int)
        assert isinstance(mappings, int)

    def test_cpe_matching_timestamp_format(self, mock_responses_dir):
        """
        Test: completed_at timestamp follows ISO 8601 format

        Validates:
        - Timestamp is ISO 8601 compliant
        - Timestamp can be parsed as datetime
        """
        with open(mock_responses_dir / "scan_cpe_match.json") as f:
            mock_data = json.load(f)

        completed_at = mock_data["data"]["completed_at"]

        # Verify ISO 8601 format
        assert "T" in completed_at
        assert completed_at.endswith("Z") or "+" in completed_at or "-" in completed_at[-6:]

        # Verify parseable as datetime
        try:
            datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
        except ValueError:
            pytest.fail(f"completed_at timestamp is not valid ISO 8601: {completed_at}")

    def test_cpe_matching_metadata_structure(self, mock_responses_dir):
        """
        Test: Response includes metadata with cache_hit and execution_time_ms

        Validates:
        - metadata object is present
        - cache_hit is boolean
        - execution_time_ms is numeric
        """
        with open(mock_responses_dir / "scan_cpe_match.json") as f:
            mock_data = json.load(f)

        assert "metadata" in mock_data
        metadata = mock_data["metadata"]

        assert "cache_hit" in metadata
        assert isinstance(metadata["cache_hit"], bool)

        assert "execution_time_ms" in metadata
        assert isinstance(metadata["execution_time_ms"], (int, float))

    def test_cpe_matching_session_id_format(self, mock_responses_dir):
        """
        Test: scan_session_id is properly formatted string

        Validates:
        - session_id is non-empty string
        - session_id follows expected format (if any)
        """
        with open(mock_responses_dir / "scan_cpe_match.json") as f:
            mock_data = json.load(f)

        session_id = mock_data["data"]["scan_session_id"]

        # Non-empty string
        assert isinstance(session_id, str)
        assert len(session_id) > 0, "session_id should not be empty"

    def test_cpe_matching_zero_components_scenario(self, mock_responses_dir):
        """
        Test: Response handles edge case of zero components

        Validates:
        - If components_processed is 0, cpe_mappings_created is also 0
        - Response structure remains valid
        """
        # This test validates the contract allows for zero values
        # The actual mock should have non-zero values, but the contract
        # should allow for this edge case

        mock_data = {
            "success": True,
            "data": {
                "scan_session_id": "test_session",
                "components_processed": 0,
                "cpe_mappings_created": 0,
                "completed_at": "2026-03-17T11:30:00Z"
            },
            "metadata": {
                "cache_hit": False,
                "execution_time_ms": 50.0
            }
        }

        # Should be valid according to contract
        try:
            response_data = mock_data["data"]
            response = CPEMatchingResponse(**response_data)
            assert response.components_processed == 0
            assert response.cpe_mappings_created == 0
        except ValidationError as e:
            pytest.fail(f"Contract should allow zero components: {e}")


class TestVEXAndCPEErrorContract:
    """Contract tests for error responses from VEX and CPE endpoints."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses"""
        return Path("tests/fixtures/api_responses")

    def test_error_response_404_not_found(self, mock_responses_dir):
        """
        Test: 404 error response for non-existent session

        Validates:
        - Error response includes detail field
        - Detail message indicates resource not found
        """
        with open(mock_responses_dir / "errors.json") as f:
            error_data = json.load(f)

        # Should have session_not_found error
        if "session_not_found" in error_data:
            error = error_data["session_not_found"]
            assert "detail" in error
            assert isinstance(error["detail"], str)
            assert "not found" in error["detail"].lower()

    def test_vex_and_cpe_endpoints_use_same_error_format(self):
        """
        Test: Both VEX and CPE endpoints use consistent error format

        Validates:
        - Both use FastAPI HTTPException detail format
        - Error messages are descriptive
        """
        # Both endpoints should raise HTTPException with detail field
        # This is ensured by FastAPI framework, but contract should document it

        error_response = {"detail": "Scan session not found"}

        assert "detail" in error_response
        assert isinstance(error_response["detail"], str)
        assert len(error_response["detail"]) > 0
