"""
Unit tests for Phase 1: Scan Repository Model Adoption.

Tests for AC-001 and AC-002:
- AC-001: ScanSessionRepository returns ScanSession models
- AC-002: ScanFindingRepository returns ScanFinding models
"""

import pytest
from unittest.mock import MagicMock, Mock
from datetime import datetime

from api.repositories.scan import ScanSessionRepository, ScanFindingRepository
from complira_graph.models import ScanSession, ScanFinding


@pytest.fixture
def mock_customer_db():
    """Mock customer database."""
    db = MagicMock()

    # Mock collection for repositories
    mock_collection = MagicMock()
    mock_collection.insert = Mock(return_value={
        "_key": "test_key_123",
        "_id": "scan_sessions/test_key_123",
        "_rev": "_test_rev",
    })
    mock_collection.update = Mock()

    db.collection = Mock(return_value=mock_collection)
    db.aql_execute = Mock(return_value=[])

    return db


# ============================================================================
# AC-001: ScanSessionRepository Returns ScanSession Models
# ============================================================================

class TestAC001_ScanSessionRepository:
    """Test AC-001: ScanSessionRepository returns ScanSession models."""

    def test_create_session_returns_scan_session_model(self, mock_customer_db):
        """
        AC-001 Test 1: create_session() returns ScanSession instance.

        Verifies:
        - create_session() return type is ScanSession
        - All required fields are validated (customer_id, tool_name, etc.)
        - Model has _key attribute from database
        """
        repo = ScanSessionRepository(mock_customer_db)

        # Mock collection insert to return full document
        mock_collection = mock_customer_db.collection.return_value
        mock_collection.insert.return_value = {
            "_key": "session_123",
            "_id": "scan_sessions/session_123",
            "_rev": "_rev123",
            "customer_id": "customer_abc",
            "tool_name": "Semgrep",
            "tool_version": "1.0.0",
            "scan_timestamp": "2024-01-15T10:30:00Z",
            "scan_type": "sarif",
            "status": "processing",
            "findings_count": 0,
            "components_count": 0,
            "metadata": {"branch": "main"},
            "created_at": "2024-01-15T10:30:00Z",
            "updated_at": "2024-01-15T10:30:00Z",
        }

        # Create session
        result = repo.create_session(
            customer_id="customer_abc",
            tool_name="Semgrep",
            tool_version="1.0.0",
            scan_timestamp="2024-01-15T10:30:00Z",
            scan_type="sarif",
            metadata={"branch": "main"},
        )

        # Verify return type is ScanSession model
        assert isinstance(result, ScanSession)

        # Verify required fields
        assert result.customer_id == "customer_abc"
        assert result.tool_name == "Semgrep"
        assert result.tool_version == "1.0.0"
        assert result.scan_type == "sarif"
        assert result.status == "processing"
        assert result._key == "session_123"

    def test_update_session_status_returns_scan_session_model(self, mock_customer_db):
        """
        AC-001 Test 2: update_session_status() returns ScanSession instance.

        Verifies:
        - update_session_status() return type is ScanSession
        - Model has updated status and counts
        """
        repo = ScanSessionRepository(mock_customer_db)

        # Mock collection update to return updated document
        mock_collection = mock_customer_db.collection.return_value
        mock_collection.update.return_value = {
            "_key": "session_123",
            "_id": "scan_sessions/session_123",
            "_rev": "_rev456",
            "customer_id": "customer_abc",
            "tool_name": "Semgrep",
            "tool_version": "1.0.0",
            "scan_timestamp": "2024-01-15T10:30:00Z",
            "scan_type": "sarif",
            "status": "completed",
            "findings_count": 25,
            "components_count": 10,
            "metadata": {},
            "created_at": "2024-01-15T10:30:00Z",
            "updated_at": "2024-01-15T10:35:00Z",
        }

        # Update session
        result = repo.update_session_status(
            session_key="session_123",
            status="completed",
            findings_count=25,
            components_count=10,
        )

        # Verify return type is ScanSession model
        assert isinstance(result, ScanSession)

        # Verify updated fields
        assert result.status == "completed"
        assert result.findings_count == 25
        assert result.components_count == 10

    def test_list_customer_sessions_returns_list_of_scan_session_models(self, mock_customer_db):
        """
        AC-001 Test 3: list_customer_sessions() returns List[ScanSession].

        Verifies:
        - list_customer_sessions() returns list of ScanSession instances
        - All items in list are ScanSession models
        """
        repo = ScanSessionRepository(mock_customer_db)

        # Mock AQL query to return multiple sessions
        mock_customer_db.aql_execute.return_value = [
            {
                "_key": "session_1",
                "_id": "scan_sessions/session_1",
                "_rev": "_rev1",
                "customer_id": "customer_abc",
                "tool_name": "Semgrep",
                "tool_version": "1.0.0",
                "scan_timestamp": "2024-01-15T10:30:00Z",
                "scan_type": "sarif",
                "status": "completed",
                "findings_count": 10,
                "components_count": 5,
                "metadata": {},
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T10:35:00Z",
            },
            {
                "_key": "session_2",
                "_id": "scan_sessions/session_2",
                "_rev": "_rev2",
                "customer_id": "customer_abc",
                "tool_name": "Trivy",
                "tool_version": "0.5.0",
                "scan_timestamp": "2024-01-16T10:30:00Z",
                "scan_type": "cyclonedx",
                "status": "completed",
                "findings_count": 5,
                "components_count": 20,
                "metadata": {},
                "created_at": "2024-01-16T10:30:00Z",
                "updated_at": "2024-01-16T10:35:00Z",
            }
        ]

        # List sessions
        result = repo.list_customer_sessions(
            customer_id="customer_abc",
            limit=100,
            offset=0,
        )

        # Verify return type is list
        assert isinstance(result, list)

        # Verify all items are ScanSession models
        assert len(result) == 2
        for session in result:
            assert isinstance(session, ScanSession)

        # Verify first session
        assert result[0]._key == "session_1"
        assert result[0].tool_name == "Semgrep"

        # Verify second session
        assert result[1]._key == "session_2"
        assert result[1].tool_name == "Trivy"


# ============================================================================
# AC-002: ScanFindingRepository Returns ScanFinding Models
# ============================================================================

class TestAC002_ScanFindingRepository:
    """Test AC-002: ScanFindingRepository returns ScanFinding models."""

    def test_create_finding_returns_scan_finding_model(self, mock_customer_db):
        """
        AC-002 Test 1: create_finding() returns ScanFinding instance.

        Verifies:
        - create_finding() return type is ScanFinding
        - Model validates and normalizes severity (high → HIGH)
        - Model validates CVE ID format
        """
        repo = ScanFindingRepository(mock_customer_db)

        # Mock collection insert to return full document
        mock_collection = mock_customer_db.collection.return_value
        mock_collection.insert.return_value = {
            "_key": "finding_123",
            "_id": "scan_findings/finding_123",
            "_rev": "_rev123",
            "customer_id": "customer_abc",
            "scan_session_id": "session_123",
            "cve_id": "CVE-2024-1234",
            "severity": "HIGH",
            "description": "SQL Injection vulnerability",
            "location": "src/app.py:line 42",
            "tool_name": "Semgrep",
            "raw_data": {"rule_id": "sql-injection"},
            "created_at": "2024-01-15T10:30:00Z",
        }

        # Create finding
        result = repo.create_finding(
            customer_id="customer_abc",
            scan_session_id="session_123",
            cve_id="cve-2024-1234",  # lowercase - should be normalized
            severity="high",  # lowercase - should be normalized
            description="SQL Injection vulnerability",
            location="src/app.py:line 42",
            tool_name="Semgrep",
            raw_data={"rule_id": "sql-injection"},
        )

        # Verify return type is ScanFinding model
        assert isinstance(result, ScanFinding)

        # Verify severity normalization (high → HIGH)
        assert result.severity == "HIGH"

        # Verify CVE ID normalization (cve-2024-1234 → CVE-2024-1234)
        assert result.cve_id == "CVE-2024-1234"

        # Verify other required fields
        assert result.customer_id == "customer_abc"
        assert result.scan_session_id == "session_123"
        assert result.description == "SQL Injection vulnerability"
        assert result._key == "finding_123"

    def test_create_finding_with_none_cve_id(self, mock_customer_db):
        """
        AC-002 Test 2: create_finding() handles None CVE ID (non-CVE findings).

        Verifies:
        - create_finding() accepts None for cve_id
        - Model validates findings without CVE IDs (e.g., SAST findings)
        """
        repo = ScanFindingRepository(mock_customer_db)

        # Mock collection insert
        mock_collection = mock_customer_db.collection.return_value
        mock_collection.insert.return_value = {
            "_key": "finding_456",
            "_id": "scan_findings/finding_456",
            "_rev": "_rev456",
            "customer_id": "customer_abc",
            "scan_session_id": "session_123",
            "cve_id": None,  # No CVE ID for this finding
            "severity": "MEDIUM",
            "description": "Hardcoded secret detected",
            "location": "src/config.py:line 10",
            "tool_name": "Semgrep",
            "raw_data": {"rule_id": "hardcoded-secret"},
            "created_at": "2024-01-15T10:30:00Z",
        }

        # Create finding without CVE ID
        result = repo.create_finding(
            customer_id="customer_abc",
            scan_session_id="session_123",
            cve_id=None,  # Non-CVE finding
            severity="medium",
            description="Hardcoded secret detected",
            location="src/config.py:line 10",
            tool_name="Semgrep",
            raw_data={"rule_id": "hardcoded-secret"},
        )

        # Verify return type is ScanFinding model
        assert isinstance(result, ScanFinding)

        # Verify CVE ID is None
        assert result.cve_id is None

        # Verify severity normalization
        assert result.severity == "MEDIUM"

    def test_list_session_findings_returns_list_of_scan_finding_models(self, mock_customer_db):
        """
        AC-002 Test 3: list_session_findings() returns List[ScanFinding].

        Verifies:
        - list_session_findings() returns list of ScanFinding instances
        - All items in list are ScanFinding models
        """
        repo = ScanFindingRepository(mock_customer_db)

        # Mock AQL query to return multiple findings
        mock_customer_db.aql_execute.return_value = [
            {
                "_key": "finding_1",
                "_id": "scan_findings/finding_1",
                "_rev": "_rev1",
                "customer_id": "customer_abc",
                "scan_session_id": "session_123",
                "cve_id": "CVE-2024-1234",
                "severity": "HIGH",
                "description": "SQL Injection",
                "location": "src/app.py:42",
                "tool_name": "Semgrep",
                "raw_data": {},
                "created_at": "2024-01-15T10:30:00Z",
            },
            {
                "_key": "finding_2",
                "_id": "scan_findings/finding_2",
                "_rev": "_rev2",
                "customer_id": "customer_abc",
                "scan_session_id": "session_123",
                "cve_id": None,
                "severity": "MEDIUM",
                "description": "Hardcoded secret",
                "location": "src/config.py:10",
                "tool_name": "Semgrep",
                "raw_data": {},
                "created_at": "2024-01-15T10:31:00Z",
            }
        ]

        # List findings
        result = repo.list_session_findings(
            customer_id="customer_abc",
            scan_session_id="session_123",
            limit=1000,
            offset=0,
        )

        # Verify return type is list
        assert isinstance(result, list)

        # Verify all items are ScanFinding models
        assert len(result) == 2
        for finding in result:
            assert isinstance(finding, ScanFinding)

        # Verify first finding
        assert result[0]._key == "finding_1"
        assert result[0].cve_id == "CVE-2024-1234"
        assert result[0].severity == "HIGH"

        # Verify second finding (no CVE ID)
        assert result[1]._key == "finding_2"
        assert result[1].cve_id is None
        assert result[1].severity == "MEDIUM"

    def test_severity_normalization_validation(self, mock_customer_db):
        """
        AC-002 Test 4: Verify ScanFinding model normalizes severity to uppercase.

        Verifies:
        - Model automatically normalizes severity values
        - Supported severities: critical, high, medium, low, info
        """
        repo = ScanFindingRepository(mock_customer_db)

        test_cases = [
            ("critical", "CRITICAL"),
            ("high", "HIGH"),
            ("medium", "MEDIUM"),
            ("low", "LOW"),
            ("info", "INFO"),
            ("CRITICAL", "CRITICAL"),  # Already uppercase
            ("High", "HIGH"),  # Mixed case
        ]

        for input_severity, expected_severity in test_cases:
            # Mock collection insert
            mock_collection = mock_customer_db.collection.return_value
            mock_collection.insert.return_value = {
                "_key": "finding_test",
                "_id": "scan_findings/finding_test",
                "_rev": "_rev_test",
                "customer_id": "customer_abc",
                "scan_session_id": "session_123",
                "cve_id": None,
                "severity": expected_severity,
                "description": "Test finding",
                "location": "test.py:1",
                "tool_name": "Test",
                "raw_data": {},
                "created_at": "2024-01-15T10:30:00Z",
            }

            # Create finding with input severity
            result = repo.create_finding(
                customer_id="customer_abc",
                scan_session_id="session_123",
                cve_id=None,
                severity=input_severity,
                description="Test finding",
                location="test.py:1",
                tool_name="Test",
                raw_data={},
            )

            # Verify severity is normalized
            assert result.severity == expected_severity, \
                f"Expected {input_severity} → {expected_severity}, got {result.severity}"
