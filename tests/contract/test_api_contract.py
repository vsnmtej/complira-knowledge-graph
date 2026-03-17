"""
API Contract Tests - Validate API responses match expected schema.

These tests ensure:
1. Backend API responses match the documented contract
2. Frontend mock data matches real API responses
3. No breaking changes to API structure
"""
import json
import pytest
from pathlib import Path
from pydantic import ValidationError

from api.models.responses.scan import (
    ScanIngestResponse,
    ScanSessionResponse,
    ScanFindingResponse,
)
from api.models.responses import APIResponse


class TestAPIContract:
    """Test API responses match expected contract."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses"""
        return Path("tests/fixtures/api_responses")

    def test_scan_ingest_response_contract(self, mock_responses_dir):
        """
        Test: POST /v1/scan/ingest response matches contract

        Validates:
        - Response structure matches APIResponse[ScanIngestResponse]
        - All required fields present
        - Field types correct
        """
        with open(mock_responses_dir / "scan_ingest.json") as f:
            mock_data = json.load(f)

        # Validate outer APIResponse wrapper
        assert "success" in mock_data
        assert "data" in mock_data
        assert "metadata" in mock_data

        # Validate ScanIngestResponse data
        data = mock_data["data"]
        required_fields = ["scan_session_id", "findings_count", "components_count", "status"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Validate field types
        assert isinstance(data["scan_session_id"], str)
        assert isinstance(data["findings_count"], int)
        assert isinstance(data["components_count"], int)
        assert isinstance(data["status"], str)
        assert data["status"] in ["pending", "processing", "completed", "failed"]

        # Validate using Pydantic model
        try:
            response = ScanIngestResponse(**data)
            assert response.scan_session_id == data["scan_session_id"]
            assert response.findings_count == data["findings_count"]
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match ScanIngestResponse schema: {e}")

    def test_scan_session_response_contract(self, mock_responses_dir):
        """
        Test: GET /v1/scan/{session_id} response matches contract
        """
        with open(mock_responses_dir / "scan_session.json") as f:
            mock_data = json.load(f)

        data = mock_data["data"]

        required_fields = [
            "session_id", "tool_name", "tool_version", "scan_type",
            "scan_timestamp", "status", "findings_count", "components_count",
            "created_at", "updated_at", "metadata"
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Validate using Pydantic model
        try:
            response = ScanSessionResponse(**data)
            assert response.session_id == data["session_id"]
            assert response.tool_name == data["tool_name"]
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match ScanSessionResponse schema: {e}")

    def test_scan_findings_response_contract(self, mock_responses_dir):
        """
        Test: GET /v1/scan/{session_id}/findings response matches contract
        """
        with open(mock_responses_dir / "scan_findings.json") as f:
            mock_data = json.load(f)

        findings_list = mock_data["data"]
        assert isinstance(findings_list, list)
        assert len(findings_list) > 0, "Mock should have at least one finding"

        # Validate each finding
        for finding in findings_list:
            required_fields = [
                "finding_id", "cve_id", "severity", "description",
                "location", "tool_name", "created_at"
            ]
            for field in required_fields:
                assert field in finding, f"Missing field {field} in finding"

            # Validate severity values
            assert finding["severity"] in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "UNKNOWN"]

            # Validate vulnerability ID format
            if finding["cve_id"]:
                valid_prefixes = ["CVE-", "GHSA-", "RUSTSEC-", "PYSEC-", "GO-", "GHSL-"]
                assert any(finding["cve_id"].startswith(prefix) for prefix in valid_prefixes), \
                    f"Invalid vulnerability ID: {finding['cve_id']}"

            # Validate using Pydantic model
            try:
                response = ScanFindingResponse(**finding)
                assert response.finding_id == finding["finding_id"]
            except ValidationError as e:
                pytest.fail(f"Finding doesn't match ScanFindingResponse schema: {e}")

    def test_error_responses_contract(self, mock_responses_dir):
        """
        Test: Error responses match FastAPI HTTPException format
        """
        with open(mock_responses_dir / "errors.json") as f:
            error_data = json.load(f)

        # All errors should have "detail" field
        for error_key, error_response in error_data.items():
            assert "detail" in error_response, f"Error {error_key} missing 'detail' field"
            assert isinstance(error_response["detail"], str)

    def test_mock_data_has_ghsa_vulnerabilities(self, mock_responses_dir):
        """
        Test: Mock data includes GHSA vulnerability IDs (testing our fix)
        """
        with open(mock_responses_dir / "scan_findings.json") as f:
            mock_data = json.load(f)

        findings = mock_data["data"]
        ghsa_findings = [f for f in findings if f["cve_id"] and f["cve_id"].startswith("GHSA-")]

        assert len(ghsa_findings) > 0, "Mock data should include GHSA vulnerabilities"
        print(f"✅ Mock data includes {len(ghsa_findings)} GHSA vulnerabilities")

    def test_mock_data_has_all_severity_levels(self, mock_responses_dir):
        """
        Test: Mock data includes all severity levels
        """
        with open(mock_responses_dir / "scan_findings.json") as f:
            mock_data = json.load(f)

        findings = mock_data["data"]
        severities = {f["severity"] for f in findings}

        # Should have at least CRITICAL, HIGH, MEDIUM, LOW
        expected_severities = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
        assert expected_severities.issubset(severities), \
            f"Mock data missing severities. Got: {severities}, Expected at least: {expected_severities}"
        print(f"✅ Mock data includes all severity levels: {severities}")

    def test_metadata_structure(self, mock_responses_dir):
        """
        Test: All responses include metadata with cache_hit and execution_time_ms
        """
        mock_files = ["scan_ingest.json", "scan_session.json", "scan_findings.json", "scans_list.json"]

        for mock_file in mock_files:
            with open(mock_responses_dir / mock_file) as f:
                mock_data = json.load(f)

            assert "metadata" in mock_data, f"{mock_file} missing metadata"
            metadata = mock_data["metadata"]

            assert "cache_hit" in metadata, f"{mock_file} metadata missing cache_hit"
            assert "execution_time_ms" in metadata, f"{mock_file} metadata missing execution_time_ms"

            assert isinstance(metadata["cache_hit"], bool)
            assert isinstance(metadata["execution_time_ms"], (int, float))
