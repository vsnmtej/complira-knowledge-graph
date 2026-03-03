"""
Unit tests for Phase 2: Enrichment Services.

Tests for services:
- EnrichmentService: Enrich scan findings with vulnerability intelligence
- CompactionService: Compact findings (deduplicate + CWE rollup)
- ControlMappingService: Map findings to regulatory controls
"""

import pytest
from unittest.mock import MagicMock, Mock, patch, AsyncMock

from api.services.enrichment import EnrichmentService
from api.services.compaction import CompactionService
from api.services.control_mapping import ControlMappingService
from complira_graph.models import (
    ScanFinding,
    Vulnerability,
    EPSSHistory,
    KEVEntry,
    Weakness,
    AttackPattern,
    ATTACKTechnique,
    ThreatIntelligence,
    EnrichResponse,
    CompactResponse,
    ControlMappingsResponse,
)


@pytest.fixture
def mock_cache():
    """Mock cache service."""
    cache = MagicMock()
    cache.get = Mock(return_value=None)
    cache.set = Mock()
    return cache


@pytest.fixture
def mock_db():
    """Mock database."""
    db = MagicMock()
    db.aql_execute = Mock(return_value=[])
    return db


# ============================================================================
# EnrichmentService Tests
# ============================================================================

class TestEnrichmentService:
    """Test EnrichmentService methods."""

    @pytest.mark.asyncio
    async def test_enrich_scan_session_success(self, mock_db, mock_cache):
        """Test enrich_scan_session with CVE findings."""
        service = EnrichmentService(mock_db, mock_cache)

        # Mock findings with CVE
        mock_findings = [
            ScanFinding(
                _key="finding_001",
                customer_id="customer_abc",
                scan_session_id="scan_sess_123",
                cve_id="CVE-2024-1234",
                severity="HIGH",
                description="Test finding 1",
                location="app.js:42",
                tool_name="Semgrep",
                raw_data={"cwe_ids": ["CWE-79"]},
                created_at="2024-01-15T00:00:00Z",
            ),
            ScanFinding(
                _key="finding_002",
                customer_id="customer_abc",
                scan_session_id="scan_sess_123",
                cve_id="CVE-2024-5678",
                severity="MEDIUM",
                description="Test finding 2",
                location="index.js:15",
                tool_name="Semgrep",
                raw_data={"cwe_ids": ["CWE-89"]},
                created_at="2024-01-15T00:00:00Z",
            ),
        ]

        # Mock vulnerability details
        mock_vuln1 = Vulnerability(
            _key="cve_2024_1234",
            vulnerability_id="CVE-2024-1234",
            cve_id="CVE-2024-1234",
            description="Test vuln 1",
            cvss_v3_score=9.8,
            cwe_ids=["CWE-79"],
            source="nvd",
            cisa_enriched=False,
            created_at="2024-01-15T00:00:00Z",
            updated_at="2024-01-15T00:00:00Z",
        )

        # Mock EPSS
        mock_epss1 = EPSSHistory(
            _key="cve_2024_1234_2024_01_15",
            cve_id="CVE-2024-1234",
            cve_key="cve_2024_1234",
            epss_score=0.95,
            percentile=0.99,
            score_date="2024-01-15",
            source="epss",
            created_at="2024-01-15T00:00:00Z",
            updated_at="2024-01-15T00:00:00Z",
        )

        # Mock KEV
        mock_kev1 = KEVEntry(
            _key="cve_2024_1234",
            cve_id="CVE-2024-1234",
            vendor_project="test_vendor",
            product="test_product",
            vulnerability_name="Test Vuln",
            short_description="Test description",
            required_action="Apply updates",
            known_ransomware_campaign_use="Yes",
            source="cisa_kev",
            created_at="2024-01-15T00:00:00Z",
            updated_at="2024-01-15T00:00:00Z",
        )

        with patch('api.core.database.get_customer_db') as mock_get_customer_db, \
             patch('api.core.database.get_reference_db') as mock_get_reference_db, \
             patch('api.repositories.scan.ScanFindingRepository') as MockFindingRepo, \
             patch('api.repositories.enrichment.EnrichmentRepository') as MockEnrichRepo:

            # Setup mock repositories
            mock_finding_repo = MockFindingRepo.return_value
            mock_finding_repo.list_session_findings = Mock(return_value=mock_findings)

            mock_enrich_repo = MockEnrichRepo.return_value
            mock_enrich_repo.batch_get_cve_details = Mock(return_value={
                "CVE-2024-1234": mock_vuln1
            })
            mock_enrich_repo.batch_get_latest_epss = Mock(return_value={
                "CVE-2024-1234": mock_epss1
            })
            mock_enrich_repo.batch_check_kev_status = Mock(return_value={
                "CVE-2024-1234": mock_kev1
            })
            mock_enrich_repo.batch_get_threat_intelligence_chain = Mock(return_value={
                "CWE-79": {
                    "cwe_id": "CWE-79",
                    "cwe": {
                        "_key": "cwe_79",
                        "cwe_id": "CWE-79",
                        "name": "XSS",
                        "abstraction": "Base",
                        "status": "Stable",
                        "description": "XSS",
                        "created_at": "2024-01-15T00:00:00Z",
                        "updated_at": "2024-01-15T00:00:00Z",
                    },
                    "capecs": [],
                    "attacks": []
                }
            })

            # Call service
            result = await service.enrich_scan_session(
                customer_id="customer_abc",
                scan_session_id="scan_sess_123",
                include_threat_intel=True,
                include_kev=True,
                include_epss=True,
            )

            # Verify response
            assert isinstance(result, EnrichResponse)
            assert result.scan_session_id == "scan_sess_123"
            assert result.total_findings == 2
            assert len(result.enriched_findings) == 2

            # Verify enrichment metadata
            assert result.enrichment_metadata.cve_enrichment_coverage == 50.0  # 1/2 CVEs enriched
            assert result.enrichment_metadata.epss_coverage == 50.0
            assert result.enrichment_metadata.kev_coverage == 50.0

    @pytest.mark.asyncio
    async def test_enrich_scan_session_no_findings(self, mock_db, mock_cache):
        """Test enrich_scan_session with no findings."""
        service = EnrichmentService(mock_db, mock_cache)

        with patch('api.core.database.get_customer_db') as mock_get_customer_db, \
             patch('api.repositories.scan.ScanFindingRepository') as MockFindingRepo:

            mock_finding_repo = MockFindingRepo.return_value
            mock_finding_repo.list_session_findings = Mock(return_value=[])

            result = await service.enrich_scan_session(
                customer_id="customer_abc",
                scan_session_id="scan_sess_123",
            )

            assert isinstance(result, EnrichResponse)
            assert result.total_findings == 0
            assert len(result.enriched_findings) == 0


# ============================================================================
# CompactionService Tests
# ============================================================================

class TestCompactionService:
    """Test CompactionService methods."""

    @pytest.mark.asyncio
    async def test_compact_findings_success(self, mock_db, mock_cache):
        """Test compact_findings with duplicate CVEs."""
        service = CompactionService(mock_db, mock_cache)

        # Mock findings with duplicate CVE
        mock_findings = [
            ScanFinding(
                _key="finding_001",
                customer_id="customer_abc",
                scan_session_id="scan_sess_123",
                cve_id="CVE-2024-1234",
                severity="HIGH",
                description="Test finding 1",
                location="app.js:42",
                tool_name="Semgrep",
                raw_data={"cwe_ids": ["CWE-79"]},
                created_at="2024-01-15T00:00:00Z",
            ),
            ScanFinding(
                _key="finding_002",
                customer_id="customer_abc",
                scan_session_id="scan_sess_123",
                cve_id="CVE-2024-1234",  # Same CVE
                severity="HIGH",
                description="Test finding 2",
                location="index.js:15",
                tool_name="Semgrep",
                raw_data={"cwe_ids": ["CWE-79"]},
                created_at="2024-01-15T00:00:00Z",
            ),
        ]

        # Mock rolled-up CWE
        mock_rolled_cwe = Weakness(
            _key="cwe_74",
            cwe_id="CWE-74",
            name="Improper Neutralization",
            abstraction="Class",
            status="Stable",
            description="Improper neutralization",
            created_at="2024-01-15T00:00:00Z",
            updated_at="2024-01-15T00:00:00Z",
        )

        with patch('api.core.database.get_customer_db') as mock_get_customer_db, \
             patch('api.core.database.get_reference_db') as mock_get_reference_db, \
             patch('api.repositories.scan.ScanFindingRepository') as MockFindingRepo, \
             patch('api.repositories.cwe.CWERepository') as MockCWERepo:

            mock_finding_repo = MockFindingRepo.return_value
            mock_finding_repo.list_session_findings = Mock(return_value=mock_findings)

            mock_cwe_repo = MockCWERepo.return_value
            mock_cwe_repo.batch_rollup_to_abstraction_level = Mock(return_value={
                "CWE-79": mock_rolled_cwe
            })

            result = await service.compact_findings(
                customer_id="customer_abc",
                scan_session_id="scan_sess_123",
                deduplication_strategy="by_cve",
                cwe_rollup_level="Class",
            )

            # Verify response
            assert isinstance(result, CompactResponse)
            assert result.original_finding_count == 2
            assert result.compacted_finding_count == 1  # 2 findings → 1 compacted
            assert result.reduction_percentage == 50.0

            # Verify compacted finding
            assert len(result.compacted_findings) == 1
            compacted = result.compacted_findings[0]
            assert compacted.vulnerability_id == "CVE-2024-1234"
            assert compacted.occurrences == 2
            assert len(compacted.affected_locations) == 2


# ============================================================================
# ControlMappingService Tests
# ============================================================================

class TestControlMappingService:
    """Test ControlMappingService methods."""

    @pytest.mark.asyncio
    async def test_map_controls_with_compaction(self, mock_db, mock_cache):
        """Test map_controls with compacted view."""
        service = ControlMappingService(mock_db, mock_cache)

        # Mock compacted findings
        from complira_graph.models import CompactedFinding, CompactResponse, CompactionMetadata

        mock_compacted_findings = [
            CompactedFinding(
                vulnerability_id="CVE-2024-1234",
                severity="HIGH",
                occurrences=2,
                affected_locations=[
                    {"file": "app.js:42", "tool": "Semgrep"},
                    {"file": "index.js:15", "tool": "Semgrep"},
                ],
                cwe_ids=["CWE-74"],  # Rolled up to Class
                original_cwe_ids=["CWE-79"],
            )
        ]

        mock_compact_response = CompactResponse(
            scan_session_id="scan_sess_123",
            original_finding_count=2,
            compacted_finding_count=1,
            reduction_percentage=50.0,
            compacted_findings=mock_compacted_findings,
            compaction_metadata=CompactionMetadata(
                deduplication_strategy="by_cve",
                cwe_rollup_level="Class",
                original_cwe_count=1,
                rolled_up_cwe_count=1,
                cwe_reduction_percentage=0.0,
            )
        )

        # Mock regulatory requirements
        from complira_graph.models import RegulatoryRequirement, OSCALControl

        mock_requirement = RegulatoryRequirement(
            _key="nist_800_53_si_10",
            requirement_id="NIST-800-53-SI-10",
            framework="NIST 800-53",
            title="Information Input Validation",
            description="Check validity",
            created_at="2024-01-15T00:00:00Z",
            updated_at="2024-01-15T00:00:00Z",
        )

        mock_control = OSCALControl(
            _key="si_10",
            control_id="SI-10",
            title="Information Input Validation",
            family_id="SI",
            family_title="System and Information Integrity",
            baseline_impact=["moderate", "high"],
            created_at="2024-01-15T00:00:00Z",
            updated_at="2024-01-15T00:00:00Z",
        )

        with patch.object(CompactionService, 'compact_findings', new_callable=AsyncMock) as mock_compact, \
             patch('api.core.database.get_reference_db') as mock_get_reference_db, \
             patch('api.repositories.regulatory.RegulatoryRepository') as MockRegRepo:

            mock_compact.return_value = mock_compact_response

            mock_reg_repo = MockRegRepo.return_value
            mock_reg_repo.batch_get_requirements_for_cwes = Mock(return_value={
                "CWE-74": [mock_requirement]
            })
            mock_reg_repo.batch_get_nist_controls = Mock(return_value={
                "NIST-800-53-SI-10": mock_control
            })

            result = await service.map_controls(
                customer_id="customer_abc",
                scan_session_id="scan_sess_123",
                frameworks=["NIST 800-53"],
                use_compacted_view=True,
            )

            # Verify response
            assert isinstance(result, ControlMappingsResponse)
            assert result.scan_session_id == "scan_sess_123"
            assert result.used_compacted_view is True
            assert len(result.control_mappings) == 1

            # Verify control mapping
            mapping = result.control_mappings[0]
            assert mapping.finding_id == "CVE-2024-1234"
            assert "CWE-74" in mapping.cwe_ids
            assert len(mapping.nist_controls) == 1
            assert mapping.nist_controls[0].control_id == "SI-10"

            # Verify statistics
            stats = result.control_statistics
            assert stats.total_findings_mapped == 1
            assert stats.total_nist_controls == 1
            assert stats.coverage_percentage["NIST 800-53"] == 100.0
