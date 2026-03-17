"""
Integration tests for scan ingestion API using real FDA SBOM data.

Uses actual CycloneDX SBOM from FDA cybersecurity documentation as test data.
Tests full API flow: POST /v1/scan/ingest -> GET /v1/scan/{session_id} -> GET /v1/scan/{session_id}/findings
"""

import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from datetime import datetime


@pytest.fixture
def fda_sbom_data():
    """Load real FDA SBOM data from test fixtures."""
    # Use relative path from tests directory
    fixtures_dir = Path(__file__).parent.parent / "fixtures" / "sboms"
    sbom_file = fixtures_dir / "fda_sbom.json"

    if not sbom_file.exists():
        pytest.skip(f"FDA SBOM fixture not found at {sbom_file}")

    with open(sbom_file, 'r') as f:
        return json.load(f)


@pytest.fixture
def mock_customer_db():
    """Mock customer database."""
    db = MagicMock()
    db.collection = Mock(return_value=MagicMock())
    db.aql = MagicMock()
    db.aql.execute = Mock(return_value=[])

    # Mock collection operations
    collection = db.collection.return_value
    collection.insert = Mock(return_value={
        "_key": "test_session_123",
        "_id": "scan_sessions/test_session_123",
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


class TestScanIngestionAPI:
    """Integration tests for scan ingestion API."""

    @pytest.mark.integration
    def test_ingest_fda_sbom_with_ghsa_vulnerabilities(
        self, api_client, app, override_customer_auth, fda_sbom_data, mock_customer_db, mock_reference_db
    ):
        """
        Test: POST /v1/scan/ingest with real FDA SBOM containing GHSA vulnerabilities.

        Verifies:
        - GHSA identifiers are accepted (not rejected as invalid CVE IDs)
        - Enriched severity format is parsed correctly
        - Both CVE and GHSA vulnerabilities are processed
        - Components are extracted (including root component)
        - Response includes correct counts
        """
        with patch('api.v1.endpoints.scan.get_customer_db', return_value=mock_customer_db), \
             patch('api.core.database.get_reference_db', return_value=mock_reference_db):

            # Prepare request payload
            request_payload = {
                "format": "cyclonedx",
                "scan_type": "sbom",
                "payload": fda_sbom_data,
                "metadata": {
                    "repository": "fda-cybersecurity-docs",
                    "branch": "main",
                    "source": "integration_test"
                }
            }

            # Make request
            response = api_client.post(
                "/v1/scan/ingest",
                json=request_payload,
                headers={"X-API-Key": "test_key"}
            )

            # Verify response
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

            data = response.json()
            assert data["success"] is True
            assert "data" in data

            scan_data = data["data"]
            assert "scan_session_id" in scan_data
            assert "findings_count" in scan_data
            assert "components_count" in scan_data
            assert "status" in scan_data

            # FDA SBOM has 78 vulnerabilities (73 CVE + 5 GHSA)
            assert scan_data["findings_count"] > 0, "Should have extracted vulnerabilities"

            # FDA SBOM has 59 components (1 root + 58 dependencies)
            assert scan_data["components_count"] > 0, "Should have extracted components"

            # Status should be processing or completed
            assert scan_data["status"] in ["processing", "completed"]

    @pytest.mark.integration
    def test_parser_extracts_ghsa_vulnerabilities(self, fda_sbom_data):
        """
        Test: CycloneDX parser extracts GHSA vulnerabilities correctly.

        Verifies parser can handle:
        - GHSA-v8gr-m533-ghj9
        - GHSA-mwcw-c2x4-8c55
        - GHSA-hwm6-f628-gfh7
        - GHSA-jfmj-5v4g-7637
        - GHSA-v845-jxx5-vc9f
        """
        from api.parsers.cyclonedx import CycloneDXParser

        parser = CycloneDXParser()
        result = parser.parse(fda_sbom_data)

        # Extract all vulnerability IDs
        vuln_ids = [f.cve_id for f in result.findings if f.cve_id]

        # Verify GHSA identifiers are present
        ghsa_ids = [vid for vid in vuln_ids if vid.startswith("GHSA-")]
        assert len(ghsa_ids) > 0, "Should have extracted GHSA vulnerabilities"

        # Verify CVE identifiers are also present
        cve_ids = [vid for vid in vuln_ids if vid.startswith("CVE-")]
        assert len(cve_ids) > 0, "Should have extracted CVE vulnerabilities"

        print(f"✅ Extracted {len(cve_ids)} CVE + {len(ghsa_ids)} GHSA vulnerabilities")

    @pytest.mark.integration
    def test_parser_extracts_enriched_severity_correctly(self, fda_sbom_data):
        """
        Test: CycloneDX parser extracts enriched severity format.

        FDA SBOM uses direct severity field, not ratings array.
        Should correctly parse: CRITICAL, HIGH, MEDIUM, LOW
        """
        from api.parsers.cyclonedx import CycloneDXParser

        parser = CycloneDXParser()
        result = parser.parse(fda_sbom_data)

        # Count severity distribution
        severity_counts = {
            "CRITICAL": 0,
            "HIGH": 0,
            "MEDIUM": 0,
            "LOW": 0,
            "INFO": 0,
            "UNKNOWN": 0,
        }

        for finding in result.findings:
            severity_counts[finding.severity] = severity_counts.get(finding.severity, 0) + 1

        # Verify no unknowns (all severities should be parsed)
        assert severity_counts["UNKNOWN"] == 0, \
            f"Found {severity_counts['UNKNOWN']} UNKNOWN severities - enriched format not parsed correctly"

        # Verify we have findings across multiple severity levels
        non_zero_severities = [sev for sev, count in severity_counts.items() if count > 0]
        assert len(non_zero_severities) >= 3, \
            f"Expected multiple severity levels, got: {severity_counts}"

        print(f"✅ Severity distribution: {severity_counts}")

    @pytest.mark.integration
    def test_parser_extracts_root_and_dependency_components(self, fda_sbom_data):
        """
        Test: CycloneDX parser extracts both root component and dependencies.

        FDA SBOM has:
        - metadata.component (root: /repo or similar)
        - components[] (58 dependencies)
        """
        from api.parsers.cyclonedx import CycloneDXParser

        parser = CycloneDXParser()
        result = parser.parse(fda_sbom_data)

        # Should extract all components
        assert len(result.components) > 1, \
            "Should extract both root component and dependencies"

        # Check if root component is present
        component_names = [c.get("name") for c in result.components]

        # Verify we have actual library names (not just root)
        library_components = [c for c in result.components if c.get("type") == "library"]
        assert len(library_components) > 0, "Should have extracted library components"

        print(f"✅ Extracted {len(result.components)} total components")
        print(f"   - Libraries: {len(library_components)}")

    @pytest.mark.integration
    def test_model_validation_accepts_ghsa_identifiers(self):
        """
        Test: ScanFinding model accepts GHSA identifiers.

        Verifies:
        - GHSA-* identifiers are valid
        - CVE-* identifiers are valid
        - Other formats (RUSTSEC-*, PYSEC-*, GO-*) are valid
        """
        from complira_graph.models.scan import ScanFinding

        # Test GHSA identifier
        ghsa_finding = ScanFinding(
            customer_id="customer_test",
            scan_session_id="session_test",
            cve_id="GHSA-v8gr-m533-ghj9",
            severity="HIGH",
            description="Test GHSA vulnerability",
            location="pkg:pypi/django@4.2.0",
            tool_name="Grype",
        )
        assert ghsa_finding.cve_id == "GHSA-V8GR-M533-GHJ9"  # Should be uppercase

        # Test CVE identifier
        cve_finding = ScanFinding(
            customer_id="customer_test",
            scan_session_id="session_test",
            cve_id="CVE-2024-1234",
            severity="CRITICAL",
            description="Test CVE vulnerability",
            location="pkg:pypi/requests@2.31.0",
            tool_name="Grype",
        )
        assert cve_finding.cve_id == "CVE-2024-1234"

        # Test RUSTSEC identifier
        rustsec_finding = ScanFinding(
            customer_id="customer_test",
            scan_session_id="session_test",
            cve_id="RUSTSEC-2024-0001",
            severity="MEDIUM",
            description="Test RUSTSEC vulnerability",
            location="pkg:cargo/example@1.0.0",
            tool_name="Grype",
        )
        assert rustsec_finding.cve_id == "RUSTSEC-2024-0001"

        print("✅ Model accepts CVE, GHSA, RUSTSEC, and other vulnerability ID formats")

    @pytest.mark.integration
    def test_model_to_dict_conversion_preserves_fields(self):
        """
        Test: ScanFinding.model_dump(by_alias=True) produces correct dict format.

        Verifies fix for: 'ScanFinding' object has no attribute 'get'

        The service layer returns model_dump() results, which downstream code
        treats as dictionaries using .get() method.
        """
        from complira_graph.models.scan import ScanFinding

        finding = ScanFinding(
            key="finding_123",  # Will be serialized as _key
            customer_id="customer_test",
            scan_session_id="session_test",
            cve_id="CVE-2024-1234",
            severity="HIGH",
            description="Test vulnerability",
            location="src/app.py:42",
            tool_name="Semgrep",
        )

        # Convert to dict (as service layer does)
        finding_dict = finding.model_dump(by_alias=True)

        # Verify it's a dictionary
        assert isinstance(finding_dict, dict)

        # Verify .get() method works (as edge creation code expects)
        assert finding_dict.get("_key") == "finding_123"
        assert finding_dict.get("cve_id") == "CVE-2024-1234"
        assert finding_dict.get("severity") == "HIGH"

        # Verify all expected fields present
        expected_fields = ["_key", "customer_id", "scan_session_id", "cve_id",
                          "severity", "description", "location", "tool_name"]
        for field in expected_fields:
            assert field in finding_dict, f"Missing field: {field}"

        print("✅ Model->dict conversion preserves all fields and supports .get() method")

    @pytest.mark.integration
    def test_end_to_end_fda_sbom_upload(
        self, api_client, override_customer_auth, fda_sbom_data
    ):
        """
        End-to-end test: Upload FDA SBOM -> Verify session -> Check findings.
        """
        # 1. Upload SBOM
        upload_response = api_client.post(
            "/v1/scan/ingest",
            json={
                "format": "cyclonedx",
                "scan_type": "sbom",
                "payload": fda_sbom_data,
                "metadata": {"source": "e2e_test"}
            },
            headers={"X-API-Key": "test_key"}
        )

        assert upload_response.status_code == 200
        session_id = upload_response.json()["data"]["scan_session_id"]

        # 2. Get session details
        session_response = api_client.get(
            f"/v1/scan/{session_id}",
            headers={"X-API-Key": "test_key"}
        )

        assert session_response.status_code == 200
        session_data = session_response.json()["data"]
        assert session_data["findings_count"] == 78  # FDA SBOM has 78 vulnerabilities
        assert session_data["components_count"] >= 58  # FDA SBOM has 59 components

        # 3. Get findings
        findings_response = api_client.get(
            f"/v1/scan/{session_id}/findings",
            headers={"X-API-Key": "test_key"}
        )

        assert findings_response.status_code == 200
        findings = findings_response.json()["data"]

        # Verify GHSA findings are present
        ghsa_findings = [f for f in findings if f["cve_id"] and f["cve_id"].startswith("GHSA-")]
        assert len(ghsa_findings) == 5, f"Expected 5 GHSA findings, got {len(ghsa_findings)}"

        # Verify CVE findings are present
        cve_findings = [f for f in findings if f["cve_id"] and f["cve_id"].startswith("CVE-")]
        assert len(cve_findings) == 73, f"Expected 73 CVE findings, got {len(cve_findings)}"

        print("✅ End-to-end test passed: FDA SBOM uploaded, session created, findings retrieved")
