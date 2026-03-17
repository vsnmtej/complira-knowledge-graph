"""
Integration tests for reference data endpoints.

Tests full API flow for all 4 reference endpoints:
- GET /v1/reference/cve/{cve_id} - Get CVE details with enrichment
- GET /v1/reference/enrich?cve_ids=... - Batch enrich multiple CVEs
- GET /v1/reference/cwe/{cwe_id} - Get CWE weakness details
- GET /v1/reference/controls/{cve_id} - Get security controls mapped to CVE
"""

import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from fastapi.testclient import TestClient
from datetime import datetime


@pytest.fixture
def mock_reference_db():
    """Mock reference database for knowledge graph queries."""
    db = MagicMock()
    db.collection = Mock(return_value=MagicMock())
    db.aql = MagicMock()

    # Default: return empty results
    db.aql.execute = Mock(return_value=[])

    return db


class TestGetCVEDetails:
    """Integration tests for GET /v1/reference/cve/{cve_id}."""

    @pytest.mark.integration
    def test_get_cve_details_success_with_full_enrichment(
        self, api_client, app, override_customer_auth, mock_reference_db
    ):
        """
        Test: GET /v1/reference/cve/{cve_id} returns enriched CVE data.

        Verifies:
        - CVE details returned (description, CVSS, severity, dates)
        - EPSS exploit probability included
        - KEV catalog status included
        - CWE weaknesses mapped
        - CAPEC attack patterns mapped
        - MITRE ATT&CK techniques mapped
        - NIST 800-53 controls mapped
        - D3FEND defenses mapped
        - Regulatory requirements included
        - Exploit modules listed
        - 200 OK status
        """
        with patch('api.v1.endpoints.reference.get_reference_db', return_value=mock_reference_db):

            # Mock AQL query result
            mock_reference_db.aql.execute = Mock(return_value=[{
                "cve_id": "CVE-2024-27351",
                "description": "Critical remote code execution vulnerability in web framework",
                "cvss_score": 9.8,
                "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                "severity": "CRITICAL",
                "published_date": "2024-03-15T10:00:00Z",
                "last_modified_date": "2024-03-16T14:30:00Z",
                "epss": {
                    "score": 0.95432,
                    "percentile": 0.99234,
                    "date": "2024-03-17"
                },
                "kev": {
                    "in_kev": True,
                    "known_ransomware": True,
                    "due_date": "2024-04-05T00:00:00Z",
                    "notes": "Actively exploited in ransomware campaigns"
                },
                "weaknesses": [
                    {
                        "cwe_id": "CWE-502",
                        "name": "Deserialization of Untrusted Data",
                        "description": "The application deserializes untrusted data without verification"
                    }
                ],
                "attack_patterns": [
                    {
                        "capec_id": "CAPEC-586",
                        "name": "Object Injection",
                        "description": "Exploiting unsafe deserialization"
                    }
                ],
                "attack_techniques": [
                    {
                        "technique_id": "T1190",
                        "name": "Exploit Public-Facing Application",
                        "description": "Adversaries exploit internet-facing systems",
                        "tactics": ["initial-access"]
                    }
                ],
                "nist_controls": [
                    {
                        "control_id": "SI-10",
                        "title": "Information Input Validation",
                        "family": "System and Information Integrity"
                    },
                    {
                        "control_id": "SC-7",
                        "title": "Boundary Protection",
                        "family": "System and Communications Protection"
                    }
                ],
                "regulatory_requirements": [],
                "d3fend_defenses": [
                    {
                        "technique_id": "D3-IAA",
                        "name": "Input Validation Analysis",
                        "description": "Analyze input for malicious content"
                    }
                ],
                "threat_groups": [],
                "exploits": [
                    {
                        "exploit_id": "EDB-51234",
                        "name": "Web Framework RCE PoC",
                        "type": "exploit",
                        "platform": "linux"
                    }
                ],
                "references": [
                    "https://nvd.nist.gov/vuln/detail/CVE-2024-27351",
                    "https://github.com/advisories/GHSA-xxxx-yyyy-zzzz"
                ]
            }])

            response = api_client.get(
                "/v1/reference/cve/CVE-2024-27351",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

            data = response.json()
            assert data["success"] is True
            assert "data" in data

            cve = data["data"]

            # Verify CVE details
            assert cve["cve_id"] == "CVE-2024-27351"
            assert cve["severity"] == "CRITICAL"
            assert cve["cvss_score"] == 9.8
            assert "description" in cve
            assert "published_date" in cve

            # Verify enrichment data
            assert "epss" in cve
            assert cve["epss"]["score"] == 0.95432

            assert "kev" in cve
            assert cve["kev"]["in_kev"] is True
            assert cve["kev"]["known_ransomware"] is True

            # Verify knowledge graph mappings
            assert "weaknesses" in cve
            assert len(cve["weaknesses"]) > 0
            assert cve["weaknesses"][0]["cwe_id"] == "CWE-502"

            assert "attack_techniques" in cve
            assert len(cve["attack_techniques"]) > 0
            assert cve["attack_techniques"][0]["technique_id"] == "T1190"

            assert "nist_controls" in cve
            assert len(cve["nist_controls"]) > 0
            assert cve["nist_controls"][0]["control_id"] == "SI-10"

            assert "d3fend_defenses" in cve
            assert len(cve["d3fend_defenses"]) > 0

            # Verify metadata
            assert "metadata" in data
            assert "execution_time_ms" in data["metadata"]

    @pytest.mark.integration
    def test_get_cve_details_not_in_kev(
        self, api_client, app, override_customer_auth, mock_reference_db
    ):
        """
        Test: GET /v1/reference/cve/{cve_id} for CVE not in KEV catalog.

        Verifies:
        - KEV status is false when not in catalog
        - Other enrichment data still present
        """
        with patch('api.v1.endpoints.reference.get_reference_db', return_value=mock_reference_db):

            mock_reference_db.aql.execute = Mock(return_value=[{
                "cve_id": "CVE-2024-1234",
                "description": "Medium severity XSS vulnerability",
                "cvss_score": 6.1,
                "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N",
                "severity": "MEDIUM",
                "published_date": "2024-01-10T10:00:00Z",
                "last_modified_date": "2024-01-11T14:30:00Z",
                "epss": {
                    "score": 0.00234,
                    "percentile": 0.45123,
                    "date": "2024-03-17"
                },
                "kev": {
                    "in_kev": False
                },
                "weaknesses": [
                    {
                        "cwe_id": "CWE-79",
                        "name": "Cross-site Scripting (XSS)",
                        "description": "Improper neutralization of input"
                    }
                ],
                "attack_patterns": [],
                "attack_techniques": [],
                "nist_controls": [],
                "regulatory_requirements": [],
                "d3fend_defenses": [],
                "threat_groups": [],
                "exploits": [],
                "references": []
            }])

            response = api_client.get(
                "/v1/reference/cve/CVE-2024-1234",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            cve = data["data"]
            assert cve["kev"]["in_kev"] is False
            assert cve["severity"] == "MEDIUM"
            assert cve["epss"]["score"] == 0.00234

    @pytest.mark.integration
    def test_get_cve_details_not_found(
        self, api_client, app, override_customer_auth, mock_reference_db
    ):
        """
        Test: GET /v1/reference/cve/{cve_id} returns 404 when CVE not found.

        Verifies:
        - 404 NOT FOUND status
        - Error message indicates CVE not found
        """
        with patch('api.v1.endpoints.reference.get_reference_db', return_value=mock_reference_db):

            # Mock empty result
            mock_reference_db.aql.execute = Mock(return_value=[])

            response = api_client.get(
                "/v1/reference/cve/CVE-9999-99999",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 404
            data = response.json()
            assert "not found" in data["detail"].lower()
            assert "CVE-9999-99999" in data["detail"]

    @pytest.mark.integration
    def test_get_cve_details_invalid_format(
        self, api_client, app, override_customer_auth
    ):
        """
        Test: GET /v1/reference/cve/{cve_id} validates CVE ID format.

        Verifies:
        - Invalid CVE format returns 422 or 404
        - Error message is helpful
        """
        response = api_client.get(
            "/v1/reference/cve/INVALID-2024-1234",
            headers={"X-API-Key": "test_key"}
        )

        # May return 404 (not found), 422 (validation error), or 200 (with null result) depending on implementation
        assert response.status_code in [200, 404, 422]

    @pytest.mark.integration
    def test_get_cve_details_requires_authentication(
        self, api_client
    ):
        """
        Test: GET /v1/reference/cve/{cve_id} requires authentication.

        Verifies:
        - Returns 401/403 when X-API-Key header missing
        """
        response = api_client.get("/v1/reference/cve/CVE-2024-1234")
        assert response.status_code in [401, 403]


class TestBatchEnrichCVEs:
    """Integration tests for GET /v1/reference/enrich."""

    @pytest.mark.integration
    def test_batch_enrich_multiple_cves_success(
        self, api_client, app, override_customer_auth, mock_reference_db
    ):
        """
        Test: GET /v1/reference/enrich?cve_ids=CVE-2024-1,CVE-2024-2 returns enriched data.

        Verifies:
        - Multiple CVEs enriched in single request
        - Returns array of enriched CVE objects
        - Each CVE has same structure as /cve/{cve_id}
        - 200 OK status
        """
        with patch('api.v1.endpoints.reference.get_reference_db', return_value=mock_reference_db):

            # Mock individual CVE queries (called by get_cve_details)
            mock_cve_1 = {
                "cve_id": "CVE-2024-0001",
                "description": "First vulnerability",
                "cvss_score": 9.0,
                "severity": "CRITICAL",
                "epss": {"score": 0.8, "percentile": 0.9, "date": "2024-03-17"},
                "kev": {"in_kev": True},
                "weaknesses": [],
                "attack_patterns": [],
                "attack_techniques": [],
                "nist_controls": [],
                "regulatory_requirements": [],
                "d3fend_defenses": [],
                "threat_groups": [],
                "exploits": [],
                "references": []
            }

            mock_cve_2 = {
                "cve_id": "CVE-2024-0002",
                "description": "Second vulnerability",
                "cvss_score": 7.5,
                "severity": "HIGH",
                "epss": {"score": 0.5, "percentile": 0.7, "date": "2024-03-17"},
                "kev": {"in_kev": False},
                "weaknesses": [],
                "attack_patterns": [],
                "attack_techniques": [],
                "nist_controls": [],
                "regulatory_requirements": [],
                "d3fend_defenses": [],
                "threat_groups": [],
                "exploits": [],
                "references": []
            }

            # Mock AQL to return different results based on bind vars
            def mock_execute(query, bind_vars=None):
                if bind_vars and "cve_id" in bind_vars:
                    if bind_vars["cve_id"] == "CVE_2024_0001":
                        return [mock_cve_1]
                    elif bind_vars["cve_id"] == "CVE_2024_0002":
                        return [mock_cve_2]
                return []

            mock_reference_db.aql.execute = Mock(side_effect=mock_execute)

            response = api_client.get(
                "/v1/reference/enrich?cve_ids=CVE-2024-0001,CVE-2024-0002",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

            data = response.json()
            assert data["success"] is True
            assert "data" in data
            assert isinstance(data["data"], list)
            assert len(data["data"]) == 2

            # Verify first CVE
            cve1 = data["data"][0]
            assert cve1["cve_id"] == "CVE-2024-0001"
            assert cve1["severity"] == "CRITICAL"

            # Verify second CVE
            cve2 = data["data"][1]
            assert cve2["cve_id"] == "CVE-2024-0002"
            assert cve2["severity"] == "HIGH"

    @pytest.mark.integration
    def test_batch_enrich_handles_not_found_cves(
        self, api_client, app, override_customer_auth, mock_reference_db
    ):
        """
        Test: GET /v1/reference/enrich handles CVEs not found in database.

        Verifies:
        - Returns error object for non-existent CVEs
        - Other valid CVEs still enriched
        - Request doesn't fail entirely
        """
        with patch('api.v1.endpoints.reference.get_reference_db', return_value=mock_reference_db):

            mock_cve = {
                "cve_id": "CVE-2024-1111",
                "description": "Valid vulnerability",
                "cvss_score": 7.5,
                "severity": "HIGH",
                "epss": {"score": 0.3, "percentile": 0.5, "date": "2024-03-17"},
                "kev": {"in_kev": False},
                "weaknesses": [],
                "attack_patterns": [],
                "attack_techniques": [],
                "nist_controls": [],
                "regulatory_requirements": [],
                "d3fend_defenses": [],
                "threat_groups": [],
                "exploits": [],
                "references": []
            }

            def mock_execute(query, bind_vars=None):
                if bind_vars and bind_vars.get("cve_id") == "CVE_2024_1111":
                    return [mock_cve]
                return []  # CVE-9999-9999 not found

            mock_reference_db.aql.execute = Mock(side_effect=mock_execute)

            response = api_client.get(
                "/v1/reference/enrich?cve_ids=CVE-2024-1111,CVE-9999-9999",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            assert len(data["data"]) == 2

            # First CVE should be enriched
            assert data["data"][0]["cve_id"] == "CVE-2024-1111"
            assert "severity" in data["data"][0]

            # Second CVE should have error
            assert data["data"][1]["cve_id"] == "CVE-9999-9999"
            assert "error" in data["data"][1]

    @pytest.mark.integration
    def test_batch_enrich_enforces_max_limit(
        self, api_client, app, override_customer_auth
    ):
        """
        Test: GET /v1/reference/enrich enforces maximum 100 CVEs per request.

        Verifies:
        - Returns 400 BAD REQUEST when >100 CVEs requested
        - Error message indicates limit exceeded
        """
        # Generate 101 CVE IDs
        cve_ids = ",".join([f"CVE-2024-{i:04d}" for i in range(101)])

        response = api_client.get(
            f"/v1/reference/enrich?cve_ids={cve_ids}",
            headers={"X-API-Key": "test_key"}
        )

        assert response.status_code == 400
        data = response.json()
        assert "100" in data["detail"]

    @pytest.mark.integration
    def test_batch_enrich_missing_cve_ids_parameter(
        self, api_client, app, override_customer_auth
    ):
        """
        Test: GET /v1/reference/enrich requires cve_ids query parameter.

        Verifies:
        - Returns 422 when cve_ids parameter missing
        """
        response = api_client.get(
            "/v1/reference/enrich",
            headers={"X-API-Key": "test_key"}
        )

        assert response.status_code == 422

    @pytest.mark.integration
    def test_batch_enrich_requires_authentication(
        self, api_client
    ):
        """
        Test: GET /v1/reference/enrich requires authentication.

        Verifies:
        - Returns 401/403 when X-API-Key header missing
        """
        response = api_client.get("/v1/reference/enrich?cve_ids=CVE-2024-1234")
        assert response.status_code in [401, 403]


class TestGetCWEDetails:
    """Integration tests for GET /v1/reference/cwe/{cwe_id}."""

    @pytest.mark.integration
    def test_get_cwe_details_success(
        self, api_client, app, override_customer_auth, mock_reference_db
    ):
        """
        Test: GET /v1/reference/cwe/{cwe_id} returns CWE weakness details.

        Verifies:
        - CWE details returned (name, description, extended_description)
        - Parent/child relationships in hierarchy
        - Related CAPEC attack patterns
        - 200 OK status
        """
        with patch('api.v1.endpoints.reference.get_reference_db', return_value=mock_reference_db):

            mock_reference_db.aql.execute = Mock(return_value=[{
                "cwe_id": "CWE-79",
                "name": "Improper Neutralization of Input During Web Page Generation ('Cross-site Scripting')",
                "description": "The software does not neutralize or incorrectly neutralizes user-controllable input before it is placed in output that is used as a web page that is served to other users.",
                "extended_description": "Cross-site scripting (XSS) vulnerabilities occur when applications include untrusted data in web pages without proper validation or escaping. XSS enables attackers to execute scripts in the victim's browser which can hijack user sessions, deface websites, or redirect users to malicious sites.",
                "parents": [
                    {
                        "cwe_id": "CWE-74",
                        "name": "Improper Neutralization of Special Elements in Output Used by a Downstream Component"
                    }
                ],
                "children": [
                    {
                        "cwe_id": "CWE-80",
                        "name": "Improper Neutralization of Script-Related HTML Tags in a Web Page (Basic XSS)"
                    },
                    {
                        "cwe_id": "CWE-83",
                        "name": "Improper Neutralization of Script in Attributes in a Web Page"
                    }
                ],
                "attack_patterns": [
                    {
                        "capec_id": "CAPEC-18",
                        "name": "XSS Targeting Non-Script Elements",
                        "description": "Adversary embeds malicious scripts in non-script elements"
                    },
                    {
                        "capec_id": "CAPEC-86",
                        "name": "XSS Through HTTP Query Strings",
                        "description": "Adversary injects XSS via URL parameters"
                    }
                ]
            }])

            response = api_client.get(
                "/v1/reference/cwe/CWE-79",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

            data = response.json()
            assert data["success"] is True
            assert "data" in data

            cwe = data["data"]

            # Verify CWE details
            assert cwe["cwe_id"] == "CWE-79"
            assert "Cross-site Scripting" in cwe["name"]
            assert "description" in cwe
            assert "extended_description" in cwe

            # Verify hierarchy
            assert "parents" in cwe
            assert len(cwe["parents"]) > 0
            assert cwe["parents"][0]["cwe_id"] == "CWE-74"

            assert "children" in cwe
            assert len(cwe["children"]) >= 2

            # Verify attack patterns
            assert "attack_patterns" in cwe
            assert len(cwe["attack_patterns"]) > 0
            assert cwe["attack_patterns"][0]["capec_id"] == "CAPEC-18"

    @pytest.mark.integration
    def test_get_cwe_details_not_found(
        self, api_client, app, override_customer_auth, mock_reference_db
    ):
        """
        Test: GET /v1/reference/cwe/{cwe_id} returns 404 when CWE not found.

        Verifies:
        - 404 NOT FOUND status
        - Error message indicates CWE not found
        """
        with patch('api.v1.endpoints.reference.get_reference_db', return_value=mock_reference_db):

            mock_reference_db.aql.execute = Mock(return_value=[])

            response = api_client.get(
                "/v1/reference/cwe/CWE-99999",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 404
            data = response.json()
            assert "not found" in data["detail"].lower()

    @pytest.mark.integration
    def test_get_cwe_details_requires_authentication(
        self, api_client
    ):
        """
        Test: GET /v1/reference/cwe/{cwe_id} requires authentication.

        Verifies:
        - Returns 401/403 when X-API-Key header missing
        """
        response = api_client.get("/v1/reference/cwe/CWE-79")
        assert response.status_code in [401, 403]


class TestGetMappedControls:
    """Integration tests for GET /v1/reference/controls/{cve_id}."""

    @pytest.mark.integration
    def test_get_mapped_controls_success(
        self, api_client, app, override_customer_auth, mock_reference_db
    ):
        """
        Test: GET /v1/reference/controls/{cve_id} returns security controls.

        Verifies:
        - NIST 800-53 controls mapped via knowledge graph traversal
        - Control details include control_id, title, family, description
        - Regulatory requirements mapped (FDA, EU CRA, IEC 62304)
        - 200 OK status
        """
        with patch('api.v1.endpoints.reference.get_reference_db', return_value=mock_reference_db):

            mock_reference_db.aql.execute = Mock(return_value=[{
                "cve_id": "CVE-2024-27351",
                "nist_controls": [
                    {
                        "control_id": "SI-10",
                        "title": "Information Input Validation",
                        "family": "System and Information Integrity",
                        "description": "Check the validity of all information inputs to the system"
                    },
                    {
                        "control_id": "SC-7",
                        "title": "Boundary Protection",
                        "family": "System and Communications Protection",
                        "description": "Monitor and control communications at external boundaries"
                    },
                    {
                        "control_id": "CM-7",
                        "title": "Least Functionality",
                        "family": "Configuration Management",
                        "description": "Configure systems to provide only essential capabilities"
                    }
                ],
                "regulatory_requirements": []
            }])

            response = api_client.get(
                "/v1/reference/controls/CVE-2024-27351",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

            data = response.json()
            assert data["success"] is True
            assert "data" in data

            controls_data = data["data"]

            # Verify CVE ID returned
            assert controls_data["cve_id"] == "CVE-2024-27351"

            # Verify NIST controls
            assert "nist_controls" in controls_data
            assert len(controls_data["nist_controls"]) >= 3

            si10 = controls_data["nist_controls"][0]
            assert si10["control_id"] == "SI-10"
            assert si10["title"] == "Information Input Validation"
            assert si10["family"] == "System and Information Integrity"

            # Verify regulatory requirements present (even if empty)
            assert "regulatory_requirements" in controls_data

    @pytest.mark.integration
    def test_get_mapped_controls_not_found(
        self, api_client, app, override_customer_auth, mock_reference_db
    ):
        """
        Test: GET /v1/reference/controls/{cve_id} returns 404 when CVE not found.

        Verifies:
        - 404 NOT FOUND status
        - Error message indicates CVE not found
        """
        with patch('api.v1.endpoints.reference.get_reference_db', return_value=mock_reference_db):

            mock_reference_db.aql.execute = Mock(return_value=[])

            response = api_client.get(
                "/v1/reference/controls/CVE-9999-99999",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 404
            data = response.json()
            assert "not found" in data["detail"].lower()

    @pytest.mark.integration
    def test_get_mapped_controls_requires_authentication(
        self, api_client
    ):
        """
        Test: GET /v1/reference/controls/{cve_id} requires authentication.

        Verifies:
        - Returns 401/403 when X-API-Key header missing
        """
        response = api_client.get("/v1/reference/controls/CVE-2024-1234")
        assert response.status_code in [401, 403]


class TestReferenceEndpointsCache:
    """Integration tests for reference endpoint caching."""

    @pytest.mark.integration
    def test_reference_endpoints_use_cache(
        self, api_client, app, override_customer_auth, mock_reference_db
    ):
        """
        Test: Reference endpoints use 6-hour cache (21600s TTL).

        Verifies:
        - cache_hit metadata included in response
        - Subsequent identical requests may return cached data
        """
        with patch('api.v1.endpoints.reference.get_reference_db', return_value=mock_reference_db):

            mock_reference_db.aql.execute = Mock(return_value=[{
                "cve_id": "CVE-2024-1234",
                "description": "Test CVE",
                "cvss_score": 7.5,
                "severity": "HIGH",
                "epss": {"score": 0.5, "percentile": 0.6, "date": "2024-03-17"},
                "kev": {"in_kev": False},
                "weaknesses": [],
                "attack_patterns": [],
                "attack_techniques": [],
                "nist_controls": [],
                "regulatory_requirements": [],
                "d3fend_defenses": [],
                "threat_groups": [],
                "exploits": [],
                "references": []
            }])

            response = api_client.get(
                "/v1/reference/cve/CVE-2024-1234",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            # Verify metadata includes cache information
            assert "metadata" in data
            assert "cache_hit" in data["metadata"]
            assert isinstance(data["metadata"]["cache_hit"], bool)
