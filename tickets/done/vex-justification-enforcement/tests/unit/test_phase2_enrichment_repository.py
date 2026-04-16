"""
Unit tests for Phase 2: Enrichment Repositories.

Tests for repositories:
- EnrichmentRepository: CVE details, EPSS, KEV, threat intel queries
- CWERepository: CWE hierarchy and rollup queries
- RegulatoryRepository: CWE → Control mappings
"""

import pytest
from unittest.mock import MagicMock, Mock

from api.repositories.enrichment import EnrichmentRepository
from api.repositories.cwe import CWERepository
from api.repositories.regulatory import RegulatoryRepository
from complira_graph.models import (
    Vulnerability,
    EPSSHistory,
    KEVEntry,
    Weakness,
    AttackPattern,
    ATTACKTechnique,
    RegulatoryRequirement,
    OSCALControl,
)


@pytest.fixture
def mock_reference_db():
    """Mock reference database."""
    db = MagicMock()
    db.collection = Mock(return_value=MagicMock())
    db.aql_execute = Mock(return_value=[])
    return db


# ============================================================================
# EnrichmentRepository Tests
# ============================================================================

class TestEnrichmentRepository:
    """Test EnrichmentRepository methods."""

    def test_get_cve_details_success(self, mock_reference_db):
        """Test get_cve_details returns Vulnerability model."""
        # Mock AQL result
        mock_reference_db.aql_execute.return_value = [{
            "_key": "cve_2024_1234",
            "vulnerability_id": "CVE-2024-1234",
            "cve_id": "CVE-2024-1234",
            "description": "Test vulnerability",
            "cvss_v3_score": 9.8,
            "cvss_v3_severity": "CRITICAL",
            "cwe_ids": ["CWE-79"],
            "source": "nvd",
            "cisa_enriched": False,
            "created_at": "2024-01-15T00:00:00Z",
            "updated_at": "2024-01-15T00:00:00Z",
        }]

        repo = EnrichmentRepository(mock_reference_db)
        result = repo.get_cve_details("CVE-2024-1234")

        assert isinstance(result, Vulnerability)
        assert result.cve_id == "CVE-2024-1234"
        assert result.cvss_v3_score == 9.8
        assert "CWE-79" in result.cwe_ids

    def test_get_cve_details_not_found(self, mock_reference_db):
        """Test get_cve_details returns None when CVE not found."""
        mock_reference_db.aql_execute.return_value = []

        repo = EnrichmentRepository(mock_reference_db)
        result = repo.get_cve_details("CVE-9999-9999")

        assert result is None

    def test_batch_get_cve_details_success(self, mock_reference_db):
        """Test batch_get_cve_details returns dict of Vulnerability models."""
        mock_reference_db.aql_execute.return_value = [
            {
                "_key": "cve_2024_1234",
                "vulnerability_id": "CVE-2024-1234",
                "cve_id": "CVE-2024-1234",
                "description": "Test vuln 1",
                "cvss_v3_score": 9.8,
                "cwe_ids": ["CWE-79"],
                "source": "nvd",
                "cisa_enriched": False,
                "created_at": "2024-01-15T00:00:00Z",
                "updated_at": "2024-01-15T00:00:00Z",
            },
            {
                "_key": "cve_2024_5678",
                "vulnerability_id": "CVE-2024-5678",
                "cve_id": "CVE-2024-5678",
                "description": "Test vuln 2",
                "cvss_v3_score": 7.5,
                "cwe_ids": ["CWE-89"],
                "source": "nvd",
                "cisa_enriched": False,
                "created_at": "2024-01-15T00:00:00Z",
                "updated_at": "2024-01-15T00:00:00Z",
            }
        ]

        repo = EnrichmentRepository(mock_reference_db)
        result = repo.batch_get_cve_details(["CVE-2024-1234", "CVE-2024-5678"])

        assert len(result) == 2
        assert "CVE-2024-1234" in result
        assert "CVE-2024-5678" in result
        assert isinstance(result["CVE-2024-1234"], Vulnerability)
        assert result["CVE-2024-1234"].cvss_v3_score == 9.8

    def test_get_latest_epss_success(self, mock_reference_db):
        """Test get_latest_epss returns EPSSHistory model."""
        mock_reference_db.aql_execute.return_value = [{
            "_key": "cve_2024_1234_2024_01_15",
            "cve_id": "CVE-2024-1234",
            "cve_key": "cve_2024_1234",
            "epss_score": 0.95,
            "percentile": 0.99,
            "score_date": "2024-01-15",
            "source": "epss",
            "created_at": "2024-01-15T00:00:00Z",
            "updated_at": "2024-01-15T00:00:00Z",
        }]

        repo = EnrichmentRepository(mock_reference_db)
        result = repo.get_latest_epss("CVE-2024-1234")

        assert isinstance(result, EPSSHistory)
        assert result.epss_score == 0.95
        assert result.percentile == 0.99

    def test_check_kev_status_success(self, mock_reference_db):
        """Test check_kev_status returns KEVEntry model."""
        mock_reference_db.aql_execute.return_value = [{
            "_key": "cve_2024_1234",
            "cve_id": "CVE-2024-1234",
            "vendor_project": "test_vendor",
            "product": "test_product",
            "vulnerability_name": "Test Vuln",
            "short_description": "Test description",
            "required_action": "Apply updates",
            "date_added": "2024-01-15",
            "known_ransomware_campaign_use": "Yes",
            "source": "cisa_kev",
            "created_at": "2024-01-15T00:00:00Z",
            "updated_at": "2024-01-15T00:00:00Z",
        }]

        repo = EnrichmentRepository(mock_reference_db)
        result = repo.check_kev_status("CVE-2024-1234")

        assert isinstance(result, KEVEntry)
        assert result.cve_id == "CVE-2024-1234"
        assert result.known_ransomware_campaign_use == "Yes"

    def test_get_threat_intelligence_chain_success(self, mock_reference_db):
        """Test get_threat_intelligence_chain returns complete chain."""
        mock_reference_db.aql_execute.return_value = [{
            "cwe": {
                "_key": "cwe_79",
                "cwe_id": "CWE-79",
                "name": "Cross-site Scripting",
                "abstraction": "Base",
                "status": "Stable",
                "description": "XSS vulnerability",
                "created_at": "2024-01-15T00:00:00Z",
                "updated_at": "2024-01-15T00:00:00Z",
            },
            "capecs": [
                {
                    "_key": "capec_86",
                    "capec_id": "CAPEC-86",
                    "name": "XSS Through HTTP Query Strings",
                    "description": "XSS via query strings",
                    "abstraction": "Detailed",
                    "status": "Stable",
                }
            ],
            "attacks": [
                {
                    "_key": "t1059",
                    "technique_id": "T1059",
                    "name": "Command and Scripting Interpreter",
                    "description": "Execute commands",
                    "tactic_names": ["execution"],
                    "is_subtechnique": False,
                    "platforms": ["Windows", "Linux"],
                }
            ]
        }]

        repo = EnrichmentRepository(mock_reference_db)
        result = repo.get_threat_intelligence_chain("CWE-79")

        assert result is not None
        assert "cwe" in result
        assert "capecs" in result
        assert "attacks" in result
        assert result["cwe"]["cwe_id"] == "CWE-79"
        assert len(result["capecs"]) == 1
        assert len(result["attacks"]) == 1


# ============================================================================
# CWERepository Tests
# ============================================================================

class TestCWERepository:
    """Test CWERepository methods."""

    def test_get_parent_cwe_success(self, mock_reference_db):
        """Test get_parent_cwe returns parent Weakness model."""
        mock_reference_db.aql_execute.return_value = [{
            "_key": "cwe_74",
            "cwe_id": "CWE-74",
            "name": "Improper Neutralization",
            "abstraction": "Class",
            "status": "Stable",
            "description": "Improper neutralization of special elements",
            "created_at": "2024-01-15T00:00:00Z",
            "updated_at": "2024-01-15T00:00:00Z",
        }]

        repo = CWERepository(mock_reference_db)
        result = repo.get_parent_cwe("CWE-79")

        assert isinstance(result, Weakness)
        assert result.cwe_id == "CWE-74"
        assert result.abstraction == "Class"

    def test_rollup_to_abstraction_level_success(self, mock_reference_db):
        """Test rollup_to_abstraction_level returns Class-level CWE."""
        mock_reference_db.aql_execute.return_value = [{
            "_key": "cwe_74",
            "cwe_id": "CWE-74",
            "name": "Improper Neutralization",
            "abstraction": "Class",
            "status": "Stable",
            "description": "Improper neutralization of special elements",
            "created_at": "2024-01-15T00:00:00Z",
            "updated_at": "2024-01-15T00:00:00Z",
        }]

        repo = CWERepository(mock_reference_db)
        result = repo.rollup_to_abstraction_level("CWE-79", target_level="Class")

        assert isinstance(result, Weakness)
        assert result.cwe_id == "CWE-74"
        assert result.abstraction == "Class"

    def test_batch_rollup_to_abstraction_level_success(self, mock_reference_db):
        """Test batch_rollup_to_abstraction_level returns dict of rolled-up CWEs."""
        mock_reference_db.aql_execute.return_value = [
            {
                "original_cwe_id": "CWE-79",
                "rolled_up_cwe": {
                    "_key": "cwe_74",
                    "cwe_id": "CWE-74",
                    "name": "Improper Neutralization",
                    "abstraction": "Class",
                    "status": "Stable",
                    "description": "Improper neutralization",
                    "created_at": "2024-01-15T00:00:00Z",
                    "updated_at": "2024-01-15T00:00:00Z",
                }
            },
            {
                "original_cwe_id": "CWE-89",
                "rolled_up_cwe": {
                    "_key": "cwe_74",
                    "cwe_id": "CWE-74",
                    "name": "Improper Neutralization",
                    "abstraction": "Class",
                    "status": "Stable",
                    "description": "Improper neutralization",
                    "created_at": "2024-01-15T00:00:00Z",
                    "updated_at": "2024-01-15T00:00:00Z",
                }
            }
        ]

        repo = CWERepository(mock_reference_db)
        result = repo.batch_rollup_to_abstraction_level(
            ["CWE-79", "CWE-89"],
            target_level="Class"
        )

        assert len(result) == 2
        assert "CWE-79" in result
        assert "CWE-89" in result
        assert isinstance(result["CWE-79"], Weakness)
        assert result["CWE-79"].cwe_id == "CWE-74"


# ============================================================================
# RegulatoryRepository Tests
# ============================================================================

class TestRegulatoryRepository:
    """Test RegulatoryRepository methods."""

    def test_get_requirements_for_cwe_success(self, mock_reference_db):
        """Test get_requirements_for_cwe returns list of RegulatoryRequirement models."""
        mock_reference_db.aql_execute.return_value = [[
            {
                "_key": "nist_800_53_si_10",
                "requirement_id": "NIST-800-53-SI-10",
                "framework": "NIST 800-53",
                "title": "Information Input Validation",
                "description": "Check validity of information inputs",
                "created_at": "2024-01-15T00:00:00Z",
                "updated_at": "2024-01-15T00:00:00Z",
            }
        ]]

        repo = RegulatoryRepository(mock_reference_db)
        result = repo.get_requirements_for_cwe("CWE-74", frameworks=["NIST 800-53"])

        assert len(result) == 1
        assert isinstance(result[0], RegulatoryRequirement)
        assert result[0].framework == "NIST 800-53"

    def test_batch_get_requirements_for_cwes_success(self, mock_reference_db):
        """Test batch_get_requirements_for_cwes returns dict of requirements."""
        mock_reference_db.aql_execute.return_value = [
            {
                "cwe_id": "CWE-74",
                "requirements": [
                    {
                        "_key": "nist_800_53_si_10",
                        "requirement_id": "NIST-800-53-SI-10",
                        "framework": "NIST 800-53",
                        "title": "Information Input Validation",
                        "description": "Check validity",
                        "created_at": "2024-01-15T00:00:00Z",
                        "updated_at": "2024-01-15T00:00:00Z",
                    }
                ]
            }
        ]

        repo = RegulatoryRepository(mock_reference_db)
        result = repo.batch_get_requirements_for_cwes(
            ["CWE-74"],
            frameworks=["NIST 800-53"]
        )

        assert "CWE-74" in result
        assert len(result["CWE-74"]) == 1
        assert isinstance(result["CWE-74"][0], RegulatoryRequirement)

    def test_batch_get_nist_controls_success(self, mock_reference_db):
        """Test batch_get_nist_controls returns dict of OSCALControl models."""
        mock_reference_db.aql_execute.return_value = [
            {
                "requirement_id": "NIST-800-53-SI-10",
                "control": {
                    "_key": "si_10",
                    "control_id": "SI-10",
                    "title": "Information Input Validation",
                    "family_id": "SI",
                    "family_title": "System and Information Integrity",
                    "baseline_impact": ["moderate", "high"],
                    "created_at": "2024-01-15T00:00:00Z",
                    "updated_at": "2024-01-15T00:00:00Z",
                }
            }
        ]

        repo = RegulatoryRepository(mock_reference_db)
        result = repo.batch_get_nist_controls(["NIST-800-53-SI-10"])

        assert "NIST-800-53-SI-10" in result
        assert isinstance(result["NIST-800-53-SI-10"], OSCALControl)
        assert result["NIST-800-53-SI-10"].control_id == "SI-10"
