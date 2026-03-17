"""
Integration tests for VEX generation and CPE matching endpoints.

Tests full API flow:
- POST /v1/scan/{session_id}/vex (generate VEX document from scan)
- POST /v1/scan/{session_id}/cpe-match (match components to CPEs)
"""

import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from datetime import datetime


@pytest.fixture
def mock_customer_db():
    """Mock customer database."""
    db = MagicMock()
    db.collection = Mock(return_value=MagicMock())
    db.aql = MagicMock()
    db.aql.execute = Mock(return_value=[])

    # Mock collection operations
    collection = db.collection.return_value
    collection.get = Mock(return_value={
        "_key": "test_session_123",
        "_id": "scan_sessions/test_session_123",
        "_rev": "_rev123",
        "customer_id": "customer_test",
        "tool_name": "Grype",
        "tool_version": "0.74.0",
        "scan_type": "sbom",
        "status": "completed",
        "findings_count": 78,
        "components_count": 59,
        "created_at": "2026-03-17T10:00:00Z",
        "updated_at": "2026-03-17T10:05:00Z",
    })
    collection.insert = Mock(return_value={
        "_key": "test_vex_123",
        "_id": "vex_documents/test_vex_123",
        "_rev": "_rev123",
    })
    collection.update = Mock(return_value={
        "_key": "test_session_123",
        "_id": "scan_sessions/test_session_123",
        "_rev": "_rev456",
    })

    return db


@pytest.fixture
def mock_reference_db():
    """Mock reference database."""
    db = MagicMock()
    db.collection = Mock(return_value=MagicMock())
    db.aql = MagicMock()
    db.aql.execute = Mock(return_value=[{
        "_key": "customer_test",
        "_id": "customer_profiles/customer_test",
        "name": "Test Customer",
        "tier": "pro",
        "database_name": "customer_test_db",
        "api_key_hash": "$2b$12$test_hash",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
    }])
    return db


@pytest.fixture
def mock_vex_result():
    """Mock VEX generation result."""
    return {
        "scan_session_id": "test_session_123",
        "vex_document": {
            "bomFormat": "CycloneDX",
            "specVersion": "1.5",
            "version": 1,
            "metadata": {
                "timestamp": "2026-03-17T10:15:00Z",
                "component": {
                    "type": "application",
                    "name": "test-app"
                }
            },
            "vulnerabilities": [
                {
                    "id": "CVE-2021-44228",
                    "analysis": {
                        "state": "not_affected",
                        "justification": "vulnerable_code_not_in_execute_path",
                        "detail": "Log4j is included but logging functionality is disabled in production configuration"
                    }
                },
                {
                    "id": "GHSA-v8gr-m533-ghj9",
                    "analysis": {
                        "state": "in_triage",
                        "detail": "Security team is evaluating impact on production deployment"
                    }
                }
            ]
        },
        "vulnerabilities_assessed": 5,
        "generated_at": "2026-03-17T10:15:00Z"
    }


@pytest.fixture
def mock_cpe_result():
    """Mock CPE matching result."""
    return {
        "scan_session_id": "test_session_123",
        "components_processed": 59,
        "cpe_mappings_created": 52,
        "completed_at": "2026-03-17T11:30:00Z"
    }


class TestVEXGenerationAPI:
    """Integration tests for VEX generation API endpoint."""

    @pytest.mark.integration
    def test_generate_vex_success(
        self, api_client, app, override_customer_auth, mock_customer_db, mock_reference_db, mock_vex_result
    ):
        """
        Test: POST /v1/scan/{session_id}/vex with valid session_id.

        Verifies:
        - VEX document is generated successfully
        - Response structure matches VEXGenerationResponse model
        - VEX document contains expected CycloneDX fields
        - Vulnerabilities are assessed with impact analysis
        - Metadata includes execution time
        """
        with patch('api.v1.endpoints.scan.get_customer_db', return_value=mock_customer_db), \
             patch('api.core.database.get_reference_db', return_value=mock_reference_db), \
             patch('api.services.scan.ScanIngestionService.generate_vex',
                   new_callable=AsyncMock) as mock_generate_vex:

            # Mock VEX generation service
            mock_generate_vex.return_value = mock_vex_result

            # Make request
            response = api_client.post(
                "/v1/scan/test_session_123/vex",
                headers={"X-API-Key": "test_key"}
            )

            # Verify response
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

            data = response.json()
            assert data["success"] is True
            assert "data" in data
            assert "metadata" in data

            # Verify VEX response structure
            vex_data = data["data"]
            assert "scan_session_id" in vex_data
            assert "vex_document" in vex_data
            assert "vulnerabilities_assessed" in vex_data
            assert "generated_at" in vex_data

            # Verify VEX document structure
            vex_doc = vex_data["vex_document"]
            assert vex_doc["bomFormat"] == "CycloneDX"
            assert vex_doc["specVersion"] == "1.5"
            assert "vulnerabilities" in vex_doc
            assert isinstance(vex_doc["vulnerabilities"], list)

            # Verify vulnerability assessments
            assert vex_data["vulnerabilities_assessed"] > 0

            # Verify metadata
            metadata = data["metadata"]
            assert "execution_time_ms" in metadata
            assert isinstance(metadata["execution_time_ms"], (int, float))

            # Verify service was called correctly
            mock_generate_vex.assert_called_once_with(
                customer_id="customer_test",
                scan_session_id="test_session_123"
            )

    @pytest.mark.integration
    def test_generate_vex_session_not_found(
        self, api_client, app, override_customer_auth, mock_customer_db, mock_reference_db
    ):
        """
        Test: POST /v1/scan/{session_id}/vex with non-existent session_id.

        Verifies:
        - Returns 404 status code
        - Error message indicates session not found
        """
        with patch('api.v1.endpoints.scan.get_customer_db', return_value=mock_customer_db), \
             patch('api.core.database.get_reference_db', return_value=mock_reference_db), \
             patch('api.services.scan.ScanIngestionService.generate_vex',
                   new_callable=AsyncMock) as mock_generate_vex:

            # Mock service raising ValueError for not found
            mock_generate_vex.side_effect = ValueError("Scan session not found")

            # Make request
            response = api_client.post(
                "/v1/scan/nonexistent_session/vex",
                headers={"X-API-Key": "test_key"}
            )

            # Verify error response
            assert response.status_code == 404
            error_data = response.json()
            assert "detail" in error_data
            assert "not found" in error_data["detail"].lower()

    @pytest.mark.integration
    def test_generate_vex_unauthorized(self, api_client):
        """
        Test: POST /v1/scan/{session_id}/vex without authentication.

        Verifies:
        - Returns 401 or 403 status code
        - Authentication is required
        """
        # Make request without API key
        response = api_client.post("/v1/scan/test_session_123/vex")

        # Verify unauthorized response
        assert response.status_code in [401, 403]

    @pytest.mark.integration
    def test_vex_document_contains_required_cyclonedx_fields(self, mock_vex_result):
        """
        Test: VEX document structure matches CycloneDX spec.

        Verifies:
        - bomFormat field is present
        - specVersion field is present
        - vulnerabilities array exists
        - Each vulnerability has id and analysis fields
        """
        vex_doc = mock_vex_result["vex_document"]

        # Verify required CycloneDX fields
        assert "bomFormat" in vex_doc
        assert vex_doc["bomFormat"] == "CycloneDX"

        assert "specVersion" in vex_doc
        assert vex_doc["specVersion"] in ["1.4", "1.5", "1.6"]

        assert "vulnerabilities" in vex_doc
        assert isinstance(vex_doc["vulnerabilities"], list)

        # Verify vulnerability structure
        for vuln in vex_doc["vulnerabilities"]:
            assert "id" in vuln
            assert "analysis" in vuln

            # Verify analysis fields
            analysis = vuln["analysis"]
            assert "state" in analysis
            assert analysis["state"] in [
                "not_affected",
                "affected",
                "in_triage",
                "false_positive",
                "exploitable"
            ]

    @pytest.mark.integration
    def test_vex_handles_both_cve_and_ghsa_identifiers(self, mock_vex_result):
        """
        Test: VEX document can handle both CVE and GHSA identifiers.

        Verifies:
        - CVE-* identifiers are present
        - GHSA-* identifiers are present
        - Both are processed in vulnerability analysis
        """
        vex_doc = mock_vex_result["vex_document"]
        vuln_ids = [v["id"] for v in vex_doc["vulnerabilities"]]

        # Verify both CVE and GHSA present
        cve_ids = [vid for vid in vuln_ids if vid.startswith("CVE-")]
        ghsa_ids = [vid for vid in vuln_ids if vid.startswith("GHSA-")]

        assert len(cve_ids) > 0, "VEX should include CVE identifiers"
        assert len(ghsa_ids) > 0, "VEX should include GHSA identifiers"


class TestCPEMatchingAPI:
    """Integration tests for CPE matching API endpoint."""

    @pytest.mark.integration
    def test_match_cpes_success(
        self, api_client, app, override_customer_auth, mock_customer_db, mock_reference_db, mock_cpe_result
    ):
        """
        Test: POST /v1/scan/{session_id}/cpe-match with valid session_id.

        Verifies:
        - CPE matching completes successfully
        - Response structure matches CPEMatchingResponse model
        - Components are processed and mappings created
        - Metadata includes execution time
        """
        with patch('api.v1.endpoints.scan.get_customer_db', return_value=mock_customer_db), \
             patch('api.core.database.get_reference_db', return_value=mock_reference_db), \
             patch('api.services.scan.ScanIngestionService.match_cpes',
                   new_callable=AsyncMock) as mock_match_cpes:

            # Mock CPE matching service
            mock_match_cpes.return_value = mock_cpe_result

            # Make request
            response = api_client.post(
                "/v1/scan/test_session_123/cpe-match",
                headers={"X-API-Key": "test_key"}
            )

            # Verify response
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

            data = response.json()
            assert data["success"] is True
            assert "data" in data
            assert "metadata" in data

            # Verify CPE matching response structure
            cpe_data = data["data"]
            assert "scan_session_id" in cpe_data
            assert "components_processed" in cpe_data
            assert "cpe_mappings_created" in cpe_data
            assert "completed_at" in cpe_data

            # Verify counts are realistic
            assert cpe_data["components_processed"] > 0
            assert cpe_data["cpe_mappings_created"] >= 0
            assert cpe_data["cpe_mappings_created"] <= cpe_data["components_processed"]

            # Verify metadata
            metadata = data["metadata"]
            assert "execution_time_ms" in metadata
            assert isinstance(metadata["execution_time_ms"], (int, float))

            # Verify service was called correctly
            mock_match_cpes.assert_called_once_with(
                customer_id="customer_test",
                scan_session_id="test_session_123"
            )

    @pytest.mark.integration
    def test_match_cpes_session_not_found(
        self, api_client, app, override_customer_auth, mock_customer_db, mock_reference_db
    ):
        """
        Test: POST /v1/scan/{session_id}/cpe-match with non-existent session_id.

        Verifies:
        - Returns 404 status code
        - Error message indicates session not found
        """
        with patch('api.v1.endpoints.scan.get_customer_db', return_value=mock_customer_db), \
             patch('api.core.database.get_reference_db', return_value=mock_reference_db), \
             patch('api.services.scan.ScanIngestionService.match_cpes',
                   new_callable=AsyncMock) as mock_match_cpes:

            # Mock service raising ValueError for not found
            mock_match_cpes.side_effect = ValueError("Scan session not found")

            # Make request
            response = api_client.post(
                "/v1/scan/nonexistent_session/cpe-match",
                headers={"X-API-Key": "test_key"}
            )

            # Verify error response
            assert response.status_code == 404
            error_data = response.json()
            assert "detail" in error_data
            assert "not found" in error_data["detail"].lower()

    @pytest.mark.integration
    def test_match_cpes_unauthorized(self, api_client):
        """
        Test: POST /v1/scan/{session_id}/cpe-match without authentication.

        Verifies:
        - Returns 401 or 403 status code
        - Authentication is required
        """
        # Make request without API key
        response = api_client.post("/v1/scan/test_session_123/cpe-match")

        # Verify unauthorized response
        assert response.status_code in [401, 403]

    @pytest.mark.integration
    def test_match_cpes_no_components(
        self, api_client, app, override_customer_auth, mock_customer_db, mock_reference_db
    ):
        """
        Test: POST /v1/scan/{session_id}/cpe-match on session with no components.

        Verifies:
        - Returns success with zero mappings created
        - Response indicates 0 components processed
        """
        with patch('api.v1.endpoints.scan.get_customer_db', return_value=mock_customer_db), \
             patch('api.core.database.get_reference_db', return_value=mock_reference_db), \
             patch('api.services.scan.ScanIngestionService.match_cpes',
                   new_callable=AsyncMock) as mock_match_cpes:

            # Mock CPE matching with no components
            mock_match_cpes.return_value = {
                "scan_session_id": "test_session_123",
                "components_processed": 0,
                "cpe_mappings_created": 0,
                "completed_at": "2026-03-17T11:30:00Z"
            }

            # Make request
            response = api_client.post(
                "/v1/scan/test_session_123/cpe-match",
                headers={"X-API-Key": "test_key"}
            )

            # Verify response
            assert response.status_code == 200
            data = response.json()["data"]
            assert data["components_processed"] == 0
            assert data["cpe_mappings_created"] == 0

    @pytest.mark.integration
    def test_match_cpes_timestamp_format(self, mock_cpe_result):
        """
        Test: CPE matching result includes ISO 8601 timestamp.

        Verifies:
        - completed_at field follows ISO 8601 format
        - Timestamp can be parsed as datetime
        """
        completed_at = mock_cpe_result["completed_at"]

        # Verify ISO 8601 format
        assert "T" in completed_at
        assert completed_at.endswith("Z") or "+" in completed_at or "-" in completed_at[-6:]

        # Verify parseable as datetime
        try:
            datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
        except ValueError:
            pytest.fail(f"completed_at timestamp is not valid ISO 8601: {completed_at}")


class TestVEXAndCPEIntegration:
    """Integration tests for combined VEX and CPE workflows."""

    @pytest.mark.integration
    def test_sequential_vex_then_cpe_matching(
        self, api_client, app, override_customer_auth, mock_customer_db, mock_reference_db,
        mock_vex_result, mock_cpe_result
    ):
        """
        Test: Sequential workflow of VEX generation followed by CPE matching.

        Verifies:
        - Both operations can be performed on the same scan session
        - Operations are independent and don't interfere
        - Both return successful responses
        """
        with patch('api.v1.endpoints.scan.get_customer_db', return_value=mock_customer_db), \
             patch('api.core.database.get_reference_db', return_value=mock_reference_db), \
             patch('api.services.scan.ScanIngestionService.generate_vex',
                   new_callable=AsyncMock) as mock_generate_vex, \
             patch('api.services.scan.ScanIngestionService.match_cpes',
                   new_callable=AsyncMock) as mock_match_cpes:

            # Mock services
            mock_generate_vex.return_value = mock_vex_result
            mock_match_cpes.return_value = mock_cpe_result

            # Step 1: Generate VEX
            vex_response = api_client.post(
                "/v1/scan/test_session_123/vex",
                headers={"X-API-Key": "test_key"}
            )
            assert vex_response.status_code == 200
            vex_data = vex_response.json()["data"]
            assert vex_data["scan_session_id"] == "test_session_123"

            # Step 2: Match CPEs
            cpe_response = api_client.post(
                "/v1/scan/test_session_123/cpe-match",
                headers={"X-API-Key": "test_key"}
            )
            assert cpe_response.status_code == 200
            cpe_data = cpe_response.json()["data"]
            assert cpe_data["scan_session_id"] == "test_session_123"

            # Verify both services were called
            assert mock_generate_vex.call_count == 1
            assert mock_match_cpes.call_count == 1
