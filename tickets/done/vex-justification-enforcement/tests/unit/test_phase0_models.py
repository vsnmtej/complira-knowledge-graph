"""
Unit tests for Phase 0 Foundation models.

Tests coverage for acceptance criteria:
- AC-001: customer_profiles Collection Defined in Schema
- AC-002: CustomerProfile Model Defined
- AC-003: ScanSession Model Defined
- AC-004: ScanFinding Model Defined
"""

import pytest
from pydantic import ValidationError

from complira_graph.models import CustomerProfile, ScanSession, ScanFinding
from complira_graph.db import DOCUMENT_COLLECTIONS


class TestSchemaDefinition:
    """Test AC-001: customer_profiles Collection Defined in Schema."""

    def test_customer_profiles_in_document_collections(self):
        """Verify customer_profiles is defined in DOCUMENT_COLLECTIONS."""
        assert "customer_profiles" in DOCUMENT_COLLECTIONS, \
            "customer_profiles collection not found in DOCUMENT_COLLECTIONS"

    def test_customer_profiles_position(self):
        """Verify customer_profiles is in the Multi-Tenant SaaS section."""
        # Should be after agent_checkpoints (last system collection)
        idx = DOCUMENT_COLLECTIONS.index("customer_profiles")
        agent_checkpoint_idx = DOCUMENT_COLLECTIONS.index("agent_checkpoints")
        assert idx > agent_checkpoint_idx, \
            "customer_profiles should come after agent_checkpoints"


class TestCustomerProfileModel:
    """Test AC-002: CustomerProfile Model Defined."""

    def test_customer_profile_valid_data(self):
        """Test valid CustomerProfile instantiation."""
        profile = CustomerProfile(
            _key="acme",
            name="Acme Corp",
            api_key_hash="a" * 60,  # Valid 60-char bcrypt hash
            database_name="complira_customer_acme",
            tier="free",
            created_at="2026-03-02T10:00:00Z",
        )

        assert profile._key == "acme"
        assert profile.name == "Acme Corp"
        assert profile.api_key_hash == "a" * 60
        assert profile.database_name == "complira_customer_acme"
        assert profile.tier == "free"
        assert profile.created_at == "2026-03-02T10:00:00Z"

    def test_customer_profile_tier_validation(self):
        """Test tier field validation."""
        # Valid tiers
        for tier in ["free", "pro", "enterprise"]:
            profile = CustomerProfile(
                _key="test",
                name="Test",
                api_key_hash="a" * 60,
                database_name="complira_customer_test",
                tier=tier,
            )
            assert profile.tier == tier

        # Invalid tier
        with pytest.raises(ValidationError) as exc_info:
            CustomerProfile(
                _key="test",
                name="Test",
                api_key_hash="a" * 60,
                database_name="complira_customer_test",
                tier="invalid_tier",
            )
        assert "tier must be one of" in str(exc_info.value)

    def test_customer_profile_database_name_validation(self):
        """Test database_name field validation."""
        # Valid database_name
        profile = CustomerProfile(
            _key="test",
            name="Test",
            api_key_hash="a" * 60,
            database_name="complira_customer_test",
        )
        assert profile.database_name == "complira_customer_test"

        # Invalid database_name (wrong prefix)
        with pytest.raises(ValidationError) as exc_info:
            CustomerProfile(
                _key="test",
                name="Test",
                api_key_hash="a" * 60,
                database_name="wrong_prefix_test",
            )
        assert "database_name must start with 'complira_customer_'" in str(exc_info.value)

    def test_customer_profile_api_key_hash_length(self):
        """Test api_key_hash length validation (bcrypt is always 60 chars)."""
        # Valid 60-char hash
        profile = CustomerProfile(
            _key="test",
            name="Test",
            api_key_hash="a" * 60,
            database_name="complira_customer_test",
        )
        assert len(profile.api_key_hash) == 60

        # Invalid length (too short)
        with pytest.raises(ValidationError) as exc_info:
            CustomerProfile(
                _key="test",
                name="Test",
                api_key_hash="short",
                database_name="complira_customer_test",
            )
        assert "at least 60 characters" in str(exc_info.value)

        # Invalid length (too long)
        with pytest.raises(ValidationError) as exc_info:
            CustomerProfile(
                _key="test",
                name="Test",
                api_key_hash="a" * 61,
                database_name="complira_customer_test",
            )
        assert "at most 60 characters" in str(exc_info.value)

    def test_customer_profile_generate_key(self):
        """Test CustomerProfile.generate_key() static method."""
        # Test basic normalization
        assert CustomerProfile.generate_key("acme") == "acme"
        assert CustomerProfile.generate_key("Acme Corp") == "acme_corp"
        assert CustomerProfile.generate_key("acme-inc") == "acme_inc"
        assert CustomerProfile.generate_key("ACME") == "acme"

    def test_customer_profile_default_tier(self):
        """Test tier defaults to 'free' if not provided."""
        profile = CustomerProfile(
            _key="test",
            name="Test",
            api_key_hash="a" * 60,
            database_name="complira_customer_test",
        )
        assert profile.tier == "free"


class TestScanSessionModel:
    """Test AC-003: ScanSession Model Defined."""

    def test_scan_session_valid_data(self):
        """Test valid ScanSession instantiation."""
        session = ScanSession(
            customer_id="acme",
            tool_name="Trivy",
            tool_version="0.48.0",
            scan_timestamp="2026-03-02T10:00:00Z",
            scan_type="sarif",
            status="processing",
            findings_count=42,
            components_count=15,
            metadata={"branch": "main", "commit": "abc123"},
            created_at="2026-03-02T10:00:00Z",
            updated_at="2026-03-02T10:00:01Z",
        )

        assert session.customer_id == "acme"
        assert session.tool_name == "Trivy"
        assert session.tool_version == "0.48.0"
        assert session.scan_timestamp == "2026-03-02T10:00:00Z"
        assert session.scan_type == "sarif"
        assert session.status == "processing"
        assert session.findings_count == 42
        assert session.components_count == 15
        assert session.metadata == {"branch": "main", "commit": "abc123"}

    def test_scan_session_status_validation(self):
        """Test status field validation."""
        # Valid statuses
        for status in ["pending", "processing", "completed", "failed"]:
            session = ScanSession(
                customer_id="test",
                tool_name="Trivy",
                tool_version="1.0.0",
                scan_timestamp="2026-03-02T10:00:00Z",
                scan_type="sarif",
                status=status,
            )
            assert session.status == status

        # Invalid status
        with pytest.raises(ValidationError) as exc_info:
            ScanSession(
                customer_id="test",
                tool_name="Trivy",
                tool_version="1.0.0",
                scan_timestamp="2026-03-02T10:00:00Z",
                scan_type="sarif",
                status="invalid_status",
            )
        assert "status must be one of" in str(exc_info.value)

    def test_scan_session_scan_type_validation(self):
        """Test scan_type field validation."""
        # Valid scan types
        for scan_type in ["sarif", "cyclonedx"]:
            session = ScanSession(
                customer_id="test",
                tool_name="Trivy",
                tool_version="1.0.0",
                scan_timestamp="2026-03-02T10:00:00Z",
                scan_type=scan_type,
            )
            assert session.scan_type == scan_type

        # Invalid scan_type
        with pytest.raises(ValidationError) as exc_info:
            ScanSession(
                customer_id="test",
                tool_name="Trivy",
                tool_version="1.0.0",
                scan_timestamp="2026-03-02T10:00:00Z",
                scan_type="invalid_format",
            )
        assert "scan_type must be one of" in str(exc_info.value)

    def test_scan_session_counts_validation(self):
        """Test findings_count and components_count are non-negative."""
        # Valid counts (zero)
        session = ScanSession(
            customer_id="test",
            tool_name="Trivy",
            tool_version="1.0.0",
            scan_timestamp="2026-03-02T10:00:00Z",
            scan_type="sarif",
            findings_count=0,
            components_count=0,
        )
        assert session.findings_count == 0
        assert session.components_count == 0

        # Valid counts (positive)
        session = ScanSession(
            customer_id="test",
            tool_name="Trivy",
            tool_version="1.0.0",
            scan_timestamp="2026-03-02T10:00:00Z",
            scan_type="sarif",
            findings_count=100,
            components_count=50,
        )
        assert session.findings_count == 100
        assert session.components_count == 50

        # Invalid counts (negative)
        with pytest.raises(ValidationError) as exc_info:
            ScanSession(
                customer_id="test",
                tool_name="Trivy",
                tool_version="1.0.0",
                scan_timestamp="2026-03-02T10:00:00Z",
                scan_type="sarif",
                findings_count=-5,
            )
        assert "greater than or equal to 0" in str(exc_info.value)

    def test_scan_session_default_values(self):
        """Test ScanSession default values."""
        session = ScanSession(
            customer_id="test",
            tool_name="Trivy",
            tool_version="1.0.0",
            scan_timestamp="2026-03-02T10:00:00Z",
            scan_type="sarif",
        )

        assert session.status == "processing"  # Default status
        assert session.findings_count == 0  # Default count
        assert session.components_count == 0  # Default count
        assert session.metadata == {}  # Default metadata


class TestScanFindingModel:
    """Test AC-004: ScanFinding Model Defined."""

    def test_scan_finding_valid_data(self):
        """Test valid ScanFinding instantiation."""
        finding = ScanFinding(
            customer_id="acme",
            scan_session_id="scan_abc123",
            cve_id="CVE-2021-44228",
            severity="HIGH",
            description="Log4Shell remote code execution vulnerability",
            location="log4j-core@2.14.1",
            tool_name="Trivy",
            raw_data={"rule_id": "CVE-2021-44228", "confidence": "high"},
            created_at="2026-03-02T10:00:00Z",
        )

        assert finding.customer_id == "acme"
        assert finding.scan_session_id == "scan_abc123"
        assert finding.cve_id == "CVE-2021-44228"
        assert finding.severity == "HIGH"
        assert finding.description == "Log4Shell remote code execution vulnerability"
        assert finding.location == "log4j-core@2.14.1"
        assert finding.tool_name == "Trivy"
        assert finding.raw_data == {"rule_id": "CVE-2021-44228", "confidence": "high"}

    def test_scan_finding_severity_normalization(self):
        """Test severity is normalized to uppercase."""
        # Lowercase input
        finding = ScanFinding(
            customer_id="test",
            scan_session_id="scan_123",
            severity="high",
            description="Test",
            location="test.py:10",
            tool_name="Trivy",
        )
        assert finding.severity == "HIGH"

        # Mixed case input
        finding = ScanFinding(
            customer_id="test",
            scan_session_id="scan_123",
            severity="Medium",
            description="Test",
            location="test.py:10",
            tool_name="Trivy",
        )
        assert finding.severity == "MEDIUM"

    def test_scan_finding_severity_validation(self):
        """Test severity field validation."""
        # Valid severities
        for severity in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "UNKNOWN"]:
            finding = ScanFinding(
                customer_id="test",
                scan_session_id="scan_123",
                severity=severity.lower(),  # Test with lowercase
                description="Test",
                location="test.py:10",
                tool_name="Trivy",
            )
            assert finding.severity == severity  # Should be normalized to uppercase

        # Invalid severity
        with pytest.raises(ValidationError) as exc_info:
            ScanFinding(
                customer_id="test",
                scan_session_id="scan_123",
                severity="invalid_severity",
                description="Test",
                location="test.py:10",
                tool_name="Trivy",
            )
        assert "severity must be one of" in str(exc_info.value)

    def test_scan_finding_cve_id_normalization(self):
        """Test CVE ID is normalized to uppercase."""
        # Lowercase CVE ID
        finding = ScanFinding(
            customer_id="test",
            scan_session_id="scan_123",
            cve_id="cve-2021-44228",
            severity="HIGH",
            description="Test",
            location="test.py:10",
            tool_name="Trivy",
        )
        assert finding.cve_id == "CVE-2021-44228"

        # Mixed case CVE ID
        finding = ScanFinding(
            customer_id="test",
            scan_session_id="scan_123",
            cve_id="Cve-2021-44228",
            severity="HIGH",
            description="Test",
            location="test.py:10",
            tool_name="Trivy",
        )
        assert finding.cve_id == "CVE-2021-44228"

    def test_scan_finding_cve_id_validation(self):
        """Test CVE ID format validation."""
        # Valid CVE ID
        finding = ScanFinding(
            customer_id="test",
            scan_session_id="scan_123",
            cve_id="CVE-2021-44228",
            severity="HIGH",
            description="Test",
            location="test.py:10",
            tool_name="Trivy",
        )
        assert finding.cve_id == "CVE-2021-44228"

        # Invalid CVE ID (doesn't start with CVE-)
        with pytest.raises(ValidationError) as exc_info:
            ScanFinding(
                customer_id="test",
                scan_session_id="scan_123",
                cve_id="VULN-2021-12345",
                severity="HIGH",
                description="Test",
                location="test.py:10",
                tool_name="Trivy",
            )
        assert "cve_id must start with 'CVE-'" in str(exc_info.value)

    def test_scan_finding_cve_id_optional(self):
        """Test CVE ID is optional (None is allowed)."""
        finding = ScanFinding(
            customer_id="test",
            scan_session_id="scan_123",
            cve_id=None,
            severity="MEDIUM",
            description="Generic security issue without CVE",
            location="test.py:10",
            tool_name="Trivy",
        )
        assert finding.cve_id is None

    def test_scan_finding_default_raw_data(self):
        """Test raw_data defaults to empty dict."""
        finding = ScanFinding(
            customer_id="test",
            scan_session_id="scan_123",
            severity="LOW",
            description="Test",
            location="test.py:10",
            tool_name="Trivy",
        )
        assert finding.raw_data == {}
