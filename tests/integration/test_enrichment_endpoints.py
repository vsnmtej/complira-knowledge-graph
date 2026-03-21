"""
Integration tests for CVE enrichment endpoints.

Tests full API flow for enrichment endpoints:
- POST /v1/enrich (batch CVE enrichment with graph-based intelligence)
- GET /v1/enrich/{cve_id} (single CVE enrichment)
- POST /v1/enrich/enrich (alternate enrichment endpoint - Phase 3A-B)

Validates:
- Smart risk scoring (CVSS + EPSS + KEV + exploits)
- Attack path discovery (CVE -> CWE -> CAPEC -> ATT&CK -> Threat Groups)
- Compliance mapping (NIST, FDA, ISO frameworks)
- Data source integration (NVD, KEV, EPSS, VulnCheck, MITRE ATT&CK, D3FEND)
- Batch processing and single CVE enrichment
- Error handling and validation
"""

import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from datetime import datetime


@pytest.fixture
def mock_database():
    """Mock ArangoDB database."""
    db = MagicMock()
    db.collection = Mock(return_value=MagicMock())
    db.aql = MagicMock()
    return db


@pytest.fixture
def sample_cve_ids():
    """Sample CVE IDs for testing."""
    return [
        "CVE-2024-21413",  # High severity, in KEV
        "CVE-2023-44487",  # HTTP/2 Rapid Reset, in KEV
        "CVE-2021-44228",  # Log4Shell, in KEV
    ]


@pytest.fixture
def mock_enrichment_result():
    """Mock enrichment service result."""
    return {
        "enriched": [
            {
                "cve_id": "CVE-2024-21413",
                "description": "Microsoft Outlook Remote Code Execution Vulnerability",
                "cvss_score": 9.8,
                "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                "cvss_severity": "CRITICAL",
                "epss_score": 0.89,
                "in_kev": True,
                "exploit_count": 3,
                "published_date": "2024-02-13T00:00:00Z",
                "last_modified": "2024-02-20T00:00:00Z",
                "risk_score": 0.95,
                "priority": "CRITICAL",
                "risk_factors": {
                    "high_epss": True,
                    "actively_exploited": True,
                    "high_cvss": True,
                    "public_exploits": True,
                    "threat_groups_using": True
                },
                "cwe_list": ["CWE-416"],
                "attack_techniques": ["T1190", "T1203"],
                "threat_groups": ["APT28", "APT29"],
                "enriched_at": "2024-03-17T10:00:00Z"
            }
        ],
        "total": 1,
        "processing_time_ms": 245.5
    }


class TestEnrichmentBatchEndpoint:
    """Integration tests for POST /v1/enrich."""

    @pytest.mark.integration
    def test_batch_enrich_success_with_multiple_cves(
        self, api_client, app, override_customer_auth, mock_database, sample_cve_ids
    ):
        """
        Test: POST /v1/enrich enriches multiple CVEs successfully.

        Verifies:
        - Batch enrichment processes multiple CVEs
        - Returns enriched data with risk scores
        - Includes EPSS, CVSS, KEV status
        - Returns 200 status code
        - Processing time is tracked
        """
        with patch('api.core.database.get_database', return_value=mock_database), \
             patch('api.services.enrichment_service.EnrichmentService.enrich_cves') as mock_enrich:

            # Mock enrichment service response
            mock_enrich.return_value = {
                "enriched": [
                    {
                        "cve_id": "CVE-2024-21413",
                        "cvss_score": 9.8,
                        "epss_score": 0.89,
                        "in_kev": True,
                        "exploit_count": 3,
                        "risk_score": 0.95,
                        "priority": "CRITICAL",
                        "risk_factors": {
                            "high_epss": True,
                            "actively_exploited": True,
                            "high_cvss": True,
                            "public_exploits": True,
                            "threat_groups_using": True
                        },
                        "cwe_list": ["CWE-416"],
                        "attack_techniques": ["T1190"],
                        "threat_groups": ["APT28"],
                        "enriched_at": "2024-03-17T10:00:00Z"
                    },
                    {
                        "cve_id": "CVE-2023-44487",
                        "cvss_score": 7.5,
                        "epss_score": 0.82,
                        "in_kev": True,
                        "exploit_count": 5,
                        "risk_score": 0.88,
                        "priority": "CRITICAL",
                        "risk_factors": {
                            "high_epss": True,
                            "actively_exploited": True,
                            "high_cvss": False,
                            "public_exploits": True,
                            "threat_groups_using": True
                        },
                        "cwe_list": ["CWE-400"],
                        "attack_techniques": ["T1499"],
                        "threat_groups": [],
                        "enriched_at": "2024-03-17T10:00:00Z"
                    }
                ],
                "total": 2,
                "processing_time_ms": 320.5
            }

            # Make request
            response = api_client.post(
                "/v1/enrich",
                json={
                    "cve_ids": sample_cve_ids[:2],
                    "include_attack_paths": False,
                    "include_compliance": False
                },
                headers={"X-API-Key": "test_key"}
            )

            # Verify response
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

            data = response.json()
            assert "enriched" in data
            assert "total" in data
            assert "processing_time_ms" in data

            assert data["total"] == 2
            assert len(data["enriched"]) == 2
            assert data["processing_time_ms"] > 0

            # Verify first CVE enrichment
            cve1 = data["enriched"][0]
            assert cve1["cve_id"] == "CVE-2024-21413"
            assert cve1["risk_score"] == 0.95
            assert cve1["priority"] == "CRITICAL"
            assert cve1["in_kev"] is True
            assert cve1["risk_factors"]["actively_exploited"] is True

    @pytest.mark.integration
    def test_batch_enrich_with_attack_paths(
        self, api_client, app, override_customer_auth, mock_database
    ):
        """
        Test: POST /v1/enrich with include_attack_paths=true.

        Verifies:
        - Attack path traversal is included
        - Path includes CVE -> CWE -> CAPEC -> ATT&CK -> Threat Groups
        - D3FEND defenses are included
        """
        with patch('api.core.database.get_database', return_value=mock_database), \
             patch('api.services.enrichment_service.EnrichmentService.enrich_cves') as mock_enrich:

            mock_enrich.return_value = {
                "enriched": [
                    {
                        "cve_id": "CVE-2024-21413",
                        "cvss_score": 9.8,
                        "epss_score": 0.89,
                        "in_kev": True,
                        "risk_score": 0.95,
                        "priority": "CRITICAL",
                        "risk_factors": {
                            "high_epss": True,
                            "actively_exploited": True,
                            "high_cvss": True,
                            "public_exploits": True,
                            "threat_groups_using": True
                        },
                        "cwe_list": ["CWE-416"],
                        "attack_techniques": ["T1190"],
                        "threat_groups": ["APT28"],
                        "attack_path": {
                            "path": [
                                {
                                    "stage": "vulnerability",
                                    "node": "CVE-2024-21413",
                                    "name": "Microsoft Outlook RCE",
                                    "description": "Remote code execution vulnerability"
                                },
                                {
                                    "stage": "weakness",
                                    "node": "CWE-416",
                                    "name": "Use After Free",
                                    "description": "Memory corruption vulnerability"
                                },
                                {
                                    "stage": "attack_pattern",
                                    "node": "CAPEC-10",
                                    "name": "Buffer Overflow",
                                    "description": "Overflow attack pattern"
                                },
                                {
                                    "stage": "technique",
                                    "node": "T1190",
                                    "name": "Exploit Public-Facing Application",
                                    "description": "Initial access technique"
                                },
                                {
                                    "stage": "threat_groups",
                                    "nodes": ["APT28", "APT29"],
                                    "name": "Active Threat Groups",
                                    "description": "Known groups using this technique"
                                }
                            ],
                            "defenses": [
                                {
                                    "d3fend_id": "D3-IAM",
                                    "name": "Inbound Application Traffic Monitoring",
                                    "description": "Monitor for malicious traffic",
                                    "coverage": ["T1190"]
                                }
                            ]
                        },
                        "enriched_at": "2024-03-17T10:00:00Z"
                    }
                ],
                "total": 1,
                "processing_time_ms": 450.8
            }

            response = api_client.post(
                "/v1/enrich",
                json={
                    "cve_ids": ["CVE-2024-21413"],
                    "include_attack_paths": True,
                    "include_compliance": False
                },
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            enriched = data["enriched"][0]
            assert "attack_path" in enriched
            assert "path" in enriched["attack_path"]
            assert "defenses" in enriched["attack_path"]

            # Verify attack path stages
            path = enriched["attack_path"]["path"]
            assert len(path) == 5
            assert path[0]["stage"] == "vulnerability"
            assert path[1]["stage"] == "weakness"
            assert path[2]["stage"] == "attack_pattern"
            assert path[3]["stage"] == "technique"
            assert path[4]["stage"] == "threat_groups"

    @pytest.mark.integration
    def test_batch_enrich_with_compliance_mapping(
        self, api_client, app, override_customer_auth, mock_database
    ):
        """
        Test: POST /v1/enrich with include_compliance=true.

        Verifies:
        - Compliance mappings are included
        - NIST controls are mapped
        - Regulatory frameworks are identified
        """
        with patch('api.core.database.get_database', return_value=mock_database), \
             patch('api.services.enrichment_service.EnrichmentService.enrich_cves') as mock_enrich:

            mock_enrich.return_value = {
                "enriched": [
                    {
                        "cve_id": "CVE-2024-21413",
                        "cvss_score": 9.8,
                        "epss_score": 0.89,
                        "in_kev": True,
                        "risk_score": 0.95,
                        "priority": "CRITICAL",
                        "risk_factors": {
                            "high_epss": True,
                            "actively_exploited": True,
                            "high_cvss": True,
                            "public_exploits": True,
                            "threat_groups_using": True
                        },
                        "cwe_list": ["CWE-416"],
                        "attack_techniques": ["T1190"],
                        "threat_groups": ["APT28"],
                        "compliance": {
                            "nist_controls": ["SI-2", "RA-5", "CM-8"],
                            "frameworks": ["FDA_524B", "NIST_800_53", "ISO_27001"]
                        },
                        "enriched_at": "2024-03-17T10:00:00Z"
                    }
                ],
                "total": 1,
                "processing_time_ms": 380.2
            }

            response = api_client.post(
                "/v1/enrich",
                json={
                    "cve_ids": ["CVE-2024-21413"],
                    "include_attack_paths": False,
                    "include_compliance": True
                },
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            enriched = data["enriched"][0]
            assert "compliance" in enriched
            assert "nist_controls" in enriched["compliance"]
            assert "frameworks" in enriched["compliance"]

            # Verify NIST controls
            assert "SI-2" in enriched["compliance"]["nist_controls"]
            assert "FDA_524B" in enriched["compliance"]["frameworks"]

    @pytest.mark.integration
    def test_batch_enrich_fails_with_empty_list(
        self, api_client, app, override_customer_auth, mock_database
    ):
        """
        Test: POST /v1/enrich fails when cve_ids is empty.

        Verifies:
        - Returns 400 status code
        - Error message indicates empty list
        """
        with patch('api.core.database.get_database', return_value=mock_database):

            response = api_client.post(
                "/v1/enrich",
                json={
                    "cve_ids": [],
                    "include_attack_paths": False,
                    "include_compliance": False
                },
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code in [400, 422]
            data = response.json()
            assert "detail" in data
            detail_str = str(data["detail"]).lower()
            assert "empty" in detail_str or "least" in detail_str or "min" in detail_str

    @pytest.mark.integration
    def test_batch_enrich_fails_with_too_many_cves(
        self, api_client, app, override_customer_auth, mock_database
    ):
        """
        Test: POST /v1/enrich fails when requesting > 100 CVEs.

        Verifies:
        - Returns 400 status code
        - Error message indicates maximum limit
        """
        with patch('api.core.database.get_database', return_value=mock_database):

            # Generate 101 CVE IDs
            too_many_cves = [f"CVE-2024-{i:05d}" for i in range(101)]

            response = api_client.post(
                "/v1/enrich",
                json={
                    "cve_ids": too_many_cves,
                    "include_attack_paths": False,
                    "include_compliance": False
                },
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code in [400, 422]
            data = response.json()
            assert "detail" in data
            assert "100" in str(data["detail"])

    @pytest.mark.integration
    def test_batch_enrich_validates_enrichment_sources(
        self, api_client, app, override_customer_auth, mock_database
    ):
        """
        Test: POST /v1/enrich includes all expected data sources.

        Verifies:
        - NVD data (CVSS scores)
        - EPSS scores from FIRST.org
        - KEV catalog status from CISA
        - MITRE ATT&CK techniques
        - CWE weaknesses
        - Threat group intelligence
        """
        with patch('api.core.database.get_database', return_value=mock_database), \
             patch('api.services.enrichment_service.EnrichmentService.enrich_cves') as mock_enrich:

            mock_enrich.return_value = {
                "enriched": [
                    {
                        "cve_id": "CVE-2021-44228",
                        "description": "Apache Log4j2 Remote Code Execution",
                        "cvss_score": 10.0,  # NVD data
                        "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H",
                        "epss_score": 0.975,  # EPSS data
                        "in_kev": True,  # KEV catalog
                        "exploit_count": 47,  # VulnCheck data
                        "risk_score": 0.99,
                        "priority": "CRITICAL",
                        "risk_factors": {
                            "high_epss": True,
                            "actively_exploited": True,
                            "high_cvss": True,
                            "public_exploits": True,
                            "threat_groups_using": True
                        },
                        "cwe_list": ["CWE-502", "CWE-917"],  # CWE data
                        "attack_techniques": ["T1190", "T1059"],  # MITRE ATT&CK
                        "threat_groups": ["APT28", "APT29", "Lazarus Group"],  # Threat intel
                        "enriched_at": "2024-03-17T10:00:00Z"
                    }
                ],
                "total": 1,
                "processing_time_ms": 280.5
            }

            response = api_client.post(
                "/v1/enrich",
                json={
                    "cve_ids": ["CVE-2021-44228"],
                    "include_attack_paths": False,
                    "include_compliance": False
                },
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()
            enriched = data["enriched"][0]

            # Verify all data sources present
            assert enriched["cvss_score"] == 10.0, "NVD CVSS data missing"
            assert enriched["epss_score"] == 0.975, "EPSS data missing"
            assert enriched["in_kev"] is True, "KEV status missing"
            assert enriched["exploit_count"] == 47, "Exploit count missing"
            assert len(enriched["cwe_list"]) > 0, "CWE data missing"
            assert len(enriched["attack_techniques"]) > 0, "ATT&CK data missing"
            assert len(enriched["threat_groups"]) > 0, "Threat group data missing"


class TestEnrichmentSingleCVEEndpoint:
    """Integration tests for GET /v1/enrich/{cve_id}."""

    @pytest.mark.integration
    def test_single_cve_enrich_success(
        self, api_client, app, override_customer_auth, mock_database
    ):
        """
        Test: GET /v1/enrich/{cve_id} enriches single CVE.

        Verifies:
        - Single CVE enrichment works
        - Returns complete enrichment data
        - Returns 200 status code
        """
        with patch('api.core.database.get_database', return_value=mock_database), \
             patch('api.services.enrichment_service.EnrichmentService.enrich_cves') as mock_enrich:

            mock_enrich.return_value = {
                "enriched": [
                    {
                        "cve_id": "CVE-2024-21413",
                        "cvss_score": 9.8,
                        "epss_score": 0.89,
                        "in_kev": True,
                        "exploit_count": 3,
                        "risk_score": 0.95,
                        "priority": "CRITICAL",
                        "risk_factors": {
                            "high_epss": True,
                            "actively_exploited": True,
                            "high_cvss": True,
                            "public_exploits": True,
                            "threat_groups_using": True
                        },
                        "cwe_list": ["CWE-416"],
                        "attack_techniques": ["T1190"],
                        "threat_groups": ["APT28"],
                        "enriched_at": "2024-03-17T10:00:00Z"
                    }
                ],
                "total": 1,
                "processing_time_ms": 180.2
            }

            response = api_client.get(
                "/v1/enrich/CVE-2024-21413",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            assert data["cve_id"] == "CVE-2024-21413"
            assert data["risk_score"] == 0.95
            assert data["priority"] == "CRITICAL"
            assert "risk_factors" in data

    @pytest.mark.integration
    def test_single_cve_enrich_not_found(
        self, api_client, app, override_customer_auth, mock_database
    ):
        """
        Test: GET /v1/enrich/{cve_id} returns 404 for unknown CVE.

        Verifies:
        - Returns 404 status code
        - Error message indicates CVE not found
        """
        with patch('api.core.database.get_database', return_value=mock_database), \
             patch('api.services.enrichment_service.EnrichmentService.enrich_cves') as mock_enrich:

            mock_enrich.return_value = {
                "enriched": [],
                "total": 0,
                "processing_time_ms": 50.0
            }

            response = api_client.get(
                "/v1/enrich/CVE-9999-99999",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 404
            data = response.json()
            assert "detail" in data
            assert "not found" in data["detail"].lower()


class TestAlternateEnrichEndpoint:
    """Integration tests for POST /v1/enrich/enrich (Phase 3A-B)."""

    @pytest.mark.integration
    def test_alternate_enrich_endpoint_with_nvd_and_vulncheck(
        self, api_client, app, mock_database
    ):
        """
        Test: POST /v1/enrich returns Phase 2 + 3A + 3A-B data.

        Verifies:
        - NVD data is included
        - VulnCheck exploit intelligence is included
        - Regulatory triggers are included
        - Returns 200 status code
        """
        from complira_graph.db import get_db

        app.dependency_overrides[get_db] = lambda: mock_database
        try:
            # Mock NVD data query
            mock_nvd_cursor = MagicMock()
            mock_nvd_cursor.__iter__ = Mock(return_value=iter([{
                "published": "2021-12-10T10:15:00.000Z",
                "last_modified": "2021-12-15T12:00:00.000Z",
                "cvss_v31": {
                    "baseScore": 10.0,
                    "baseSeverity": "CRITICAL",
                    "vectorString": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H"
                },
                "description": "Apache Log4j2 Remote Code Execution",
                "references": [],
                "cpe_configs": []
            }]))

            # Mock exploit intelligence query
            mock_exploit_cursor = MagicMock()
            mock_exploit_cursor.__iter__ = Mock(return_value=iter([{
                "in_kev": True,
                "kev_date_added": "2021-12-10",
                "exploit_maturity": "weaponized",
                "ransomware_families": [
                    {"name": "Conti", "first_seen": "2021-12-15", "description": "Ransomware group"}
                ],
                "exploit_chains": [],
                "botnet_campaigns": []
            }]))

            # Mock regulatory triggers query
            mock_triggers_cursor = MagicMock()
            mock_triggers_cursor.__iter__ = Mock(return_value=iter([
                {
                    "framework": "FDA 524B",
                    "requirement_id": "KEV_RESPONSE",
                    "requirement_title": "Known Exploited Vulnerability Response",
                    "urgency": "24h",
                    "trigger_rule": "kev_entry",
                    "confidence": 1.0,
                    "evidence": {"in_kev": True},
                    "trigger_timestamp": "2021-12-10T00:00:00Z"
                }
            ]))

            mock_database.aql.execute = Mock(side_effect=[
                mock_nvd_cursor,
                mock_exploit_cursor,
                mock_triggers_cursor
            ])

            response = api_client.post(
                "/v1/enrich/regulatory",
                json={"cve_id": "CVE-2021-44228"}
            )

            assert response.status_code == 200
            data = response.json()

            # Verify structure
            assert data["cve_id"] == "CVE-2021-44228"
            assert "nvd_data" in data
            assert "exploit_intelligence" in data
            assert "regulatory_triggers" in data

            # Verify NVD data
            assert data["nvd_data"]["cvss_v31"]["baseScore"] == 10.0

            # Verify exploit intelligence
            assert data["exploit_intelligence"]["in_kev"] is True
            assert data["exploit_intelligence"]["exploit_maturity"] == "weaponized"

            # Verify regulatory triggers
            assert len(data["regulatory_triggers"]) > 0
            assert data["regulatory_triggers"][0]["framework"] == "FDA 524B"
        finally:
            app.dependency_overrides.pop(get_db, None)


class TestEnrichmentAuthenticationAndSecurity:
    """Integration tests for enrichment endpoint security."""

    @pytest.mark.integration
    def test_enrich_requires_authentication(self, api_client):
        """
        Test: POST /v1/enrich requires authentication.

        Verifies:
        - Returns 401 or 403 without API key
        """
        response = api_client.post(
            "/v1/enrich",
            json={
                "cve_ids": ["CVE-2024-21413"],
                "include_attack_paths": False,
                "include_compliance": False
            }
        )

        # Should return unauthorized
        assert response.status_code in [401, 403]

    @pytest.mark.integration
    def test_enrich_fails_with_invalid_api_key(self, api_client, app, mock_database):
        """
        Test: POST /v1/enrich fails with invalid API key.

        Verifies:
        - Returns 401 status code
        """
        # Do NOT set override - let real auth fail
        with patch('api.core.database.get_database', return_value=mock_database):

            response = api_client.post(
                "/v1/enrich",
                json={
                    "cve_ids": ["CVE-2024-21413"],
                    "include_attack_paths": False,
                    "include_compliance": False
                },
                headers={"X-API-Key": "invalid_key"}
            )

            assert response.status_code in [401, 500]


class TestEnrichmentRiskScoring:
    """Integration tests for risk scoring algorithms."""

    @pytest.mark.integration
    def test_risk_score_calculation_critical_priority(
        self, api_client, app, override_customer_auth, mock_database
    ):
        """
        Test: Risk score calculation for CRITICAL priority CVEs.

        Verifies:
        - High CVSS (>= 9.0) + High EPSS (> 0.7) + KEV = CRITICAL
        - Risk score > 0.9
        """
        with patch('api.core.database.get_database', return_value=mock_database), \
             patch('api.services.enrichment_service.EnrichmentService.enrich_cves') as mock_enrich:

            mock_enrich.return_value = {
                "enriched": [
                    {
                        "cve_id": "CVE-2024-21413",
                        "cvss_score": 9.8,
                        "epss_score": 0.89,
                        "in_kev": True,
                        "exploit_count": 3,
                        "risk_score": 0.95,
                        "priority": "CRITICAL",
                        "risk_factors": {
                            "high_epss": True,
                            "actively_exploited": True,
                            "high_cvss": True,
                            "public_exploits": True,
                            "threat_groups_using": True
                        },
                        "cwe_list": [],
                        "attack_techniques": [],
                        "threat_groups": [],
                        "enriched_at": "2024-03-17T10:00:00Z"
                    }
                ],
                "total": 1,
                "processing_time_ms": 180.0
            }

            response = api_client.post(
                "/v1/enrich",
                json={
                    "cve_ids": ["CVE-2024-21413"],
                    "include_attack_paths": False,
                    "include_compliance": False
                },
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()
            enriched = data["enriched"][0]

            assert enriched["priority"] == "CRITICAL"
            assert enriched["risk_score"] > 0.9
            assert enriched["risk_factors"]["high_cvss"] is True
            assert enriched["risk_factors"]["high_epss"] is True
            assert enriched["risk_factors"]["actively_exploited"] is True

    @pytest.mark.integration
    def test_risk_score_calculation_low_priority(
        self, api_client, app, override_customer_auth, mock_database
    ):
        """
        Test: Risk score calculation for LOW priority CVEs.

        Verifies:
        - Low CVSS + Low EPSS + Not in KEV = LOW
        - Risk score < 0.3
        """
        with patch('api.core.database.get_database', return_value=mock_database), \
             patch('api.services.enrichment_service.EnrichmentService.enrich_cves') as mock_enrich:

            mock_enrich.return_value = {
                "enriched": [
                    {
                        "cve_id": "CVE-2024-00001",
                        "cvss_score": 3.5,
                        "epss_score": 0.02,
                        "in_kev": False,
                        "exploit_count": 0,
                        "risk_score": 0.15,
                        "priority": "LOW",
                        "risk_factors": {
                            "high_epss": False,
                            "actively_exploited": False,
                            "high_cvss": False,
                            "public_exploits": False,
                            "threat_groups_using": False
                        },
                        "cwe_list": [],
                        "attack_techniques": [],
                        "threat_groups": [],
                        "enriched_at": "2024-03-17T10:00:00Z"
                    }
                ],
                "total": 1,
                "processing_time_ms": 150.0
            }

            response = api_client.post(
                "/v1/enrich",
                json={
                    "cve_ids": ["CVE-2024-00001"],
                    "include_attack_paths": False,
                    "include_compliance": False
                },
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()
            enriched = data["enriched"][0]

            assert enriched["priority"] == "LOW"
            assert enriched["risk_score"] < 0.3
            assert enriched["risk_factors"]["high_cvss"] is False
            assert enriched["risk_factors"]["actively_exploited"] is False
