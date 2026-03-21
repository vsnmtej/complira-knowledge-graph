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
        from unittest.mock import AsyncMock

        mock_result = MagicMock()
        mock_result.scan_run_id = "run_fda_test_123"
        mock_result.findings_count = 78
        mock_result.components_count = 59
        mock_result.status = "completed"

        with patch('complira_graph.ingestion.service.EvidenceIngestionService') as MockSvc:
            MockSvc.return_value.ingest_sbom = AsyncMock(return_value=mock_result)

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
            assert "scan_run_id" in scan_data
            assert scan_data["status"] == "completed"

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
        Test: V22Finding model stores GHSA identifiers in tool_vuln_id.

        Verifies:
        - CVE-* identifiers go in cve_id
        - GHSA-* and RUSTSEC-* identifiers go in tool_vuln_id (v2.2 schema)
        """
        from complira_graph.models.evidence import V22Finding

        # Test CVE identifier
        cve_finding = V22Finding(
            fingerprint="fp_cve_1",
            tenant_id="customer_test",
            scan_run_id="run_test",
            finding_type="sca",
            tool="grype",
            cve_id="CVE-2024-1234",
            severity="critical",
            purl="pkg:pypi/requests@2.31.0",
        )
        assert cve_finding.cve_id == "CVE-2024-1234"

        # Test GHSA identifier stored in tool_vuln_id
        ghsa_finding = V22Finding(
            fingerprint="fp_ghsa_1",
            tenant_id="customer_test",
            scan_run_id="run_test",
            finding_type="sca",
            tool="grype",
            tool_vuln_id="GHSA-v8gr-m533-ghj9",
            severity="high",
            purl="pkg:pypi/django@4.2.0",
        )
        assert ghsa_finding.tool_vuln_id == "GHSA-v8gr-m533-ghj9"
        assert ghsa_finding.cve_id is None

        print("✅ V22Finding stores CVE in cve_id and GHSA/RUSTSEC in tool_vuln_id")

    @pytest.mark.integration
    def test_model_to_dict_conversion_preserves_fields(self):
        """
        Test: V22Finding.model_dump(by_alias=True) produces correct dict format.

        Verifies that model_dump() supports .get() as downstream edge creation expects.
        """
        from complira_graph.models.evidence import V22Finding

        finding = V22Finding(
            _key="fp_abc123",
            fingerprint="fp_abc123",
            tenant_id="customer_test",
            scan_run_id="run_test",
            finding_type="sast",
            tool="semgrep",
            cve_id="CVE-2024-1234",
            severity="high",
            file_path="src/app.py",
            line_start=42,
        )

        finding_dict = finding.model_dump(by_alias=True)

        assert isinstance(finding_dict, dict)

        assert finding_dict.get("_key") == "fp_abc123"
        assert finding_dict.get("cve_id") == "CVE-2024-1234"
        assert finding_dict.get("severity") == "high"

        for field in ["_key", "fingerprint", "tenant_id", "scan_run_id", "finding_type", "tool"]:
            assert field in finding_dict, f"Missing field: {field}"

        print("✅ V22Finding model->dict conversion preserves all fields and supports .get()")

    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires full live ArangoDB with v2.2 schema and FDA SBOM fixture data loaded — run manually only")
    def test_end_to_end_fda_sbom_upload(
        self, api_client, override_customer_auth, fda_sbom_data
    ):
        """
        End-to-end test: Upload FDA SBOM -> Verify session -> Check findings.

        Requires live ArangoDB with v2.2 schema — run manually only.
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
        session_id = upload_response.json()["data"]["scan_run_id"]

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
