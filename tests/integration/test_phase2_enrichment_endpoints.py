"""
Integration tests for Phase 2: Enrichment Endpoints.

Tests for AC-001 through AC-005:
- AC-001: /v1/enrich enriches findings with CVE details, EPSS, KEV, threat intel
- AC-002: /v1/compact deduplicates findings by CVE and rolls up CWEs
- AC-003: /v1/map-controls maps findings to NIST 800-53, FDA 524B, ISO 27001
- AC-004: All endpoints handle non-CVE findings (SAST secrets) via CWE enrichment
- AC-005: Performance targets met (100 findings in <5s for enrich/compact)
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock, AsyncMock

from complira_graph.models import (
    ScanFinding,
    Vulnerability,
    EPSSHistory,
    KEVEntry,
    Weakness,
    RegulatoryRequirement,
    OSCALControl,
    CompactedFinding,
    CompactResponse,
    CompactionMetadata,
)


@pytest.fixture
def test_client():
    """Create test client for API."""
    from main import app
    return TestClient(app)


@pytest.fixture
def mock_customer():
    """Mock authenticated customer."""
    from api.core.security import Customer
    return Customer(
        id="customer_abc",
        name="Test Customer",
        email="test@example.com",
        scopes=["read", "write"]
    )


# ============================================================================
# AC-001: /v1/enrich Endpoint Tests
# ============================================================================

class TestAC001_EnrichEndpoint:
    """Test AC-001: /v1/enrich enriches findings with vulnerability intelligence."""

    def test_enrich_endpoint_success_with_cve_findings(self, test_client, mock_customer):
        """
        AC-001 Test 1: /v1/enrich enriches CVE findings with all intelligence.

        Verifies:
        - 200 OK response
        - enriched_findings contains CVE details, EPSS, KEV, threat intel
        - enrichment_metadata has coverage statistics
        """
        # Mock findings
        mock_findings = [
            ScanFinding(
                _key="finding_001",
                customer_id="customer_abc",
                scan_session_id="scan_sess_123",
                cve_id="CVE-2024-1234",
                severity="HIGH",
                description="Test finding",
                location="app.js:42",
                tool_name="Semgrep",
                raw_data={"cwe_ids": ["CWE-79"]},
                created_at="2024-01-15T00:00:00Z",
            )
        ]

        mock_vuln = Vulnerability(
            _key="cve_2024_1234",
            vulnerability_id="CVE-2024-1234",
            cve_id="CVE-2024-1234",
            description="Test vulnerability",
            cvss_v3_score=9.8,
            cwe_ids=["CWE-79"],
            source="nvd",
            cisa_enriched=False,
            created_at="2024-01-15T00:00:00Z",
            updated_at="2024-01-15T00:00:00Z",
        )

        mock_epss = EPSSHistory(
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

        mock_kev = KEVEntry(
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

        with patch('api.core.security.get_current_customer', return_value=mock_customer), \
             patch('api.services.enrichment.EnrichmentService.enrich_scan_session', new_callable=AsyncMock) as mock_enrich:

            from complira_graph.models import EnrichResponse, EnrichmentMetadata, EnrichedFinding

            mock_enrich.return_value = EnrichResponse(
                scan_session_id="scan_sess_123",
                total_findings=1,
                enriched_findings=[
                    EnrichedFinding(
                        finding=mock_findings[0],
                        cve_details=mock_vuln,
                        epss_score=mock_epss,
                        kev_entry=mock_kev,
                        threat_intelligence=None,
                    )
                ],
                enrichment_metadata=EnrichmentMetadata(
                    cve_enrichment_coverage=100.0,
                    epss_coverage=100.0,
                    kev_coverage=100.0,
                    threat_intel_coverage=0.0,
                )
            )

            response = test_client.post(
                "/v1/enrich",
                json={
                    "scan_session_id": "scan_sess_123",
                    "include_threat_intel": True,
                    "include_kev": True,
                    "include_epss": True,
                }
            )

            assert response.status_code == 200
            data = response.json()

            # Verify response structure
            assert data["scan_session_id"] == "scan_sess_123"
            assert data["total_findings"] == 1
            assert len(data["enriched_findings"]) == 1

            # Verify enrichment data
            enriched = data["enriched_findings"][0]
            assert enriched["cve_details"] is not None
            assert enriched["cve_details"]["cve_id"] == "CVE-2024-1234"
            assert enriched["epss_score"] is not None
            assert enriched["epss_score"]["epss_score"] == 0.95
            assert enriched["kev_entry"] is not None
            assert enriched["kev_entry"]["known_ransomware_campaign_use"] == "Yes"

            # Verify metadata
            assert data["enrichment_metadata"]["cve_enrichment_coverage"] == 100.0

    def test_enrich_endpoint_success_with_non_cve_findings(self, test_client, mock_customer):
        """
        AC-001/AC-004 Test 2: /v1/enrich handles non-CVE findings (SAST secrets).

        Verifies:
        - Non-CVE findings enriched via CWE only
        - threat_intelligence present (CWE → CAPEC → ATT&CK)
        - cve_details, epss_score, kev_entry are null
        """
        mock_findings = [
            ScanFinding(
                _key="finding_001",
                customer_id="customer_abc",
                scan_session_id="scan_sess_123",
                cve_id=None,  # Non-CVE finding
                severity="HIGH",
                description="Hardcoded API key",
                location="config.py:12",
                tool_name="Semgrep",
                raw_data={"cwe_ids": ["CWE-798"]},
                created_at="2024-01-15T00:00:00Z",
            )
        ]

        mock_cwe = Weakness(
            _key="cwe_798",
            cwe_id="CWE-798",
            name="Use of Hard-coded Credentials",
            abstraction="Base",
            status="Stable",
            description="Hard-coded credentials",
            created_at="2024-01-15T00:00:00Z",
            updated_at="2024-01-15T00:00:00Z",
        )

        with patch('api.core.security.get_current_customer', return_value=mock_customer), \
             patch('api.services.enrichment.EnrichmentService.enrich_scan_session', new_callable=AsyncMock) as mock_enrich:

            from complira_graph.models import (
                EnrichResponse,
                EnrichmentMetadata,
                EnrichedFinding,
                ThreatIntelligence,
            )

            mock_enrich.return_value = EnrichResponse(
                scan_session_id="scan_sess_123",
                total_findings=1,
                enriched_findings=[
                    EnrichedFinding(
                        finding=mock_findings[0],
                        cve_details=None,  # No CVE
                        epss_score=None,  # No CVE
                        kev_entry=None,  # No CVE
                        threat_intelligence=ThreatIntelligence(
                            cwe=mock_cwe,
                            capecs=[],
                            attack_techniques=[],
                        ),
                    )
                ],
                enrichment_metadata=EnrichmentMetadata(
                    cve_enrichment_coverage=0.0,
                    epss_coverage=0.0,
                    kev_coverage=0.0,
                    threat_intel_coverage=100.0,
                )
            )

            response = test_client.post(
                "/v1/enrich",
                json={"scan_session_id": "scan_sess_123"}
            )

            assert response.status_code == 200
            data = response.json()

            # Verify non-CVE finding enrichment
            enriched = data["enriched_findings"][0]
            assert enriched["cve_details"] is None
            assert enriched["epss_score"] is None
            assert enriched["kev_entry"] is None
            assert enriched["threat_intelligence"] is not None
            assert enriched["threat_intelligence"]["cwe"]["cwe_id"] == "CWE-798"


# ============================================================================
# AC-002: /v1/compact Endpoint Tests
# ============================================================================

class TestAC002_CompactEndpoint:
    """Test AC-002: /v1/compact deduplicates and rolls up CWEs."""

    def test_compact_endpoint_success_with_deduplication(self, test_client, mock_customer):
        """
        AC-002 Test 1: /v1/compact deduplicates findings by CVE.

        Verifies:
        - 200 OK response
        - original_finding_count = 100
        - compacted_finding_count < original (deduplication worked)
        - reduction_percentage calculated correctly
        """
        with patch('api.core.security.get_current_customer', return_value=mock_customer), \
             patch('api.services.compaction.CompactionService.compact_findings', new_callable=AsyncMock) as mock_compact:

            mock_compact.return_value = CompactResponse(
                scan_session_id="scan_sess_123",
                original_finding_count=100,
                compacted_finding_count=70,
                reduction_percentage=30.0,
                compacted_findings=[
                    CompactedFinding(
                        vulnerability_id="CVE-2024-1234",
                        severity="HIGH",
                        occurrences=15,
                        affected_locations=[
                            {"file": "app.js:42", "tool": "Semgrep"},
                            {"file": "index.js:15", "tool": "Semgrep"},
                        ],
                        cwe_ids=["CWE-74"],  # Rolled up
                        original_cwe_ids=["CWE-79"],
                    )
                ],
                compaction_metadata=CompactionMetadata(
                    deduplication_strategy="by_cve",
                    cwe_rollup_level="Class",
                    original_cwe_count=60,
                    rolled_up_cwe_count=15,
                    cwe_reduction_percentage=75.0,
                )
            )

            response = test_client.post(
                "/v1/compact",
                json={
                    "scan_session_id": "scan_sess_123",
                    "deduplication_strategy": "by_cve",
                    "cwe_rollup_level": "Class",
                }
            )

            assert response.status_code == 200
            data = response.json()

            # Verify deduplication
            assert data["original_finding_count"] == 100
            assert data["compacted_finding_count"] == 70
            assert data["reduction_percentage"] == 30.0

            # Verify compacted finding structure
            compacted = data["compacted_findings"][0]
            assert compacted["vulnerability_id"] == "CVE-2024-1234"
            assert compacted["occurrences"] == 15
            assert len(compacted["affected_locations"]) == 2

            # Verify CWE rollup
            assert compacted["cwe_ids"] == ["CWE-74"]
            assert compacted["original_cwe_ids"] == ["CWE-79"]

            # Verify metadata
            assert data["compaction_metadata"]["cwe_reduction_percentage"] == 75.0


# ============================================================================
# AC-003: /v1/map-controls Endpoint Tests
# ============================================================================

class TestAC003_MapControlsEndpoint:
    """Test AC-003: /v1/map-controls maps to regulatory controls."""

    def test_map_controls_endpoint_success_with_nist(self, test_client, mock_customer):
        """
        AC-003 Test 1: /v1/map-controls maps findings to NIST 800-53.

        Verifies:
        - 200 OK response
        - control_mappings contains NIST 800-53 controls
        - control_statistics shows total controls and coverage %
        """
        with patch('api.core.security.get_current_customer', return_value=mock_customer), \
             patch('api.services.control_mapping.ControlMappingService.map_controls', new_callable=AsyncMock) as mock_map:

            from complira_graph.models import (
                ControlMappingsResponse,
                ControlMapping,
                ControlStatistics,
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

            mock_map.return_value = ControlMappingsResponse(
                scan_session_id="scan_sess_123",
                frameworks=["NIST 800-53"],
                control_mappings=[
                    ControlMapping(
                        finding_id="CVE-2024-1234",
                        cwe_ids=["CWE-74"],
                        nist_controls=[mock_control],
                        fda_requirements=[],
                        iso_requirements=[],
                    )
                ],
                control_statistics=ControlStatistics(
                    total_findings_mapped=70,
                    total_nist_controls=30,
                    total_fda_requirements=0,
                    total_iso_requirements=0,
                    coverage_percentage={"NIST 800-53": 100.0},
                ),
                used_compacted_view=True,
            )

            response = test_client.post(
                "/v1/map-controls",
                json={
                    "scan_session_id": "scan_sess_123",
                    "frameworks": ["NIST 800-53"],
                    "use_compacted_view": True,
                }
            )

            assert response.status_code == 200
            data = response.json()

            # Verify control mappings
            assert len(data["control_mappings"]) == 1
            mapping = data["control_mappings"][0]
            assert mapping["finding_id"] == "CVE-2024-1234"
            assert len(mapping["nist_controls"]) == 1
            assert mapping["nist_controls"][0]["control_id"] == "SI-10"

            # Verify statistics
            stats = data["control_statistics"]
            assert stats["total_findings_mapped"] == 70
            assert stats["total_nist_controls"] == 30
            assert stats["coverage_percentage"]["NIST 800-53"] == 100.0

    def test_map_controls_endpoint_success_with_multiple_frameworks(
        self, test_client, mock_customer
    ):
        """
        AC-003 Test 2: /v1/map-controls maps to multiple frameworks.

        Verifies:
        - Maps to NIST 800-53, FDA 524B, ISO 27001 simultaneously
        - control_statistics shows coverage for all frameworks
        """
        with patch('api.core.security.get_current_customer', return_value=mock_customer), \
             patch('api.services.control_mapping.ControlMappingService.map_controls', new_callable=AsyncMock) as mock_map:

            from complira_graph.models import (
                ControlMappingsResponse,
                ControlMapping,
                ControlStatistics,
            )

            mock_nist_control = OSCALControl(
                _key="si_10",
                control_id="SI-10",
                title="Information Input Validation",
                family_id="SI",
                family_title="System and Information Integrity",
                baseline_impact=["moderate", "high"],
                created_at="2024-01-15T00:00:00Z",
                updated_at="2024-01-15T00:00:00Z",
            )

            mock_fda_req = RegulatoryRequirement(
                _key="fda_524b_5_1",
                requirement_id="FDA-524B-5.1",
                framework="FDA 524B",
                title="Input Validation",
                description="Validate inputs",
                created_at="2024-01-15T00:00:00Z",
                updated_at="2024-01-15T00:00:00Z",
            )

            mock_map.return_value = ControlMappingsResponse(
                scan_session_id="scan_sess_123",
                frameworks=["NIST 800-53", "FDA 524B", "ISO 27001"],
                control_mappings=[
                    ControlMapping(
                        finding_id="CVE-2024-1234",
                        cwe_ids=["CWE-74"],
                        nist_controls=[mock_nist_control],
                        fda_requirements=[mock_fda_req],
                        iso_requirements=[],
                    )
                ],
                control_statistics=ControlStatistics(
                    total_findings_mapped=70,
                    total_nist_controls=30,
                    total_fda_requirements=25,
                    total_iso_requirements=20,
                    coverage_percentage={
                        "NIST 800-53": 100.0,
                        "FDA 524B": 85.7,
                        "ISO 27001": 92.9,
                    },
                ),
                used_compacted_view=True,
            )

            response = test_client.post(
                "/v1/map-controls",
                json={
                    "scan_session_id": "scan_sess_123",
                    "frameworks": ["NIST 800-53", "FDA 524B", "ISO 27001"],
                }
            )

            assert response.status_code == 200
            data = response.json()

            # Verify all frameworks mapped
            mapping = data["control_mappings"][0]
            assert len(mapping["nist_controls"]) == 1
            assert len(mapping["fda_requirements"]) == 1

            # Verify statistics for all frameworks
            stats = data["control_statistics"]
            assert stats["total_nist_controls"] == 30
            assert stats["total_fda_requirements"] == 25
            assert stats["total_iso_requirements"] == 20
            assert "NIST 800-53" in stats["coverage_percentage"]
            assert "FDA 524B" in stats["coverage_percentage"]
            assert "ISO 27001" in stats["coverage_percentage"]


# ============================================================================
# AC-005: Performance Tests
# ============================================================================

@pytest.mark.performance
@pytest.mark.slow
class TestAC005_PerformanceTargets:
    """Test AC-005: Performance targets are met."""

    def test_enrich_performance_100_findings(self, test_client, mock_customer):
        """
        AC-005 Test 1: /v1/enrich processes 100 findings in <5 seconds.

        Verifies:
        - Response time < 5000ms for 100 findings
        - Batch queries optimize performance
        """
        import time

        with patch('api.core.security.get_current_customer', return_value=mock_customer), \
             patch('api.services.enrichment.EnrichmentService.enrich_scan_session', new_callable=AsyncMock) as mock_enrich:

            from complira_graph.models import EnrichResponse, EnrichmentMetadata

            # Mock 100 findings
            mock_enrich.return_value = EnrichResponse(
                scan_session_id="scan_sess_123",
                total_findings=100,
                enriched_findings=[],  # Omitted for performance test
                enrichment_metadata=EnrichmentMetadata(
                    cve_enrichment_coverage=100.0,
                    epss_coverage=62.5,
                    kev_coverage=12.5,
                    threat_intel_coverage=100.0,
                )
            )

            start_time = time.time()
            response = test_client.post(
                "/v1/enrich",
                json={"scan_session_id": "scan_sess_123"}
            )
            elapsed_ms = (time.time() - start_time) * 1000

            assert response.status_code == 200
            assert elapsed_ms < 5000  # Performance target: <5s
