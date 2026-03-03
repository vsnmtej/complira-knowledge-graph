"""
Unit tests for Phase 1: Scan Service Model Adoption.

Tests for AC-003:
- AC-003: ScanIngestionService uses models throughout
"""

import pytest
from unittest.mock import MagicMock, Mock, AsyncMock, patch
from datetime import datetime

from api.services.scan import ScanIngestionService
from api.models.requests.scan import ScanIngestRequest
from complira_graph.models import ScanSession, ScanFinding


@pytest.fixture
def mock_customer_db():
    """Mock customer database."""
    db = MagicMock()
    db.collection = Mock(return_value=MagicMock())
    return db


@pytest.fixture
def mock_scan_request():
    """Mock scan ingestion request."""
    return ScanIngestRequest(
        format="sarif",
        scan_type="sarif",
        payload={
            "version": "2.1.0",
            "runs": [{
                "tool": {
                    "driver": {
                        "name": "Semgrep",
                        "version": "1.0.0",
                    }
                },
                "results": []
            }]
        },
        metadata={"branch": "main", "commit": "abc123"}
    )


# ============================================================================
# AC-003: ScanIngestionService Uses Models
# ============================================================================

class TestAC003_ScanIngestionService:
    """Test AC-003: ScanIngestionService uses models throughout."""

    @pytest.mark.asyncio
    async def test_ingest_scan_returns_scan_session_model(self, mock_customer_db, mock_scan_request):
        """
        AC-003 Test 1: ingest_scan() returns ScanSession model instance.

        Verifies:
        - ingest_scan() return type is ScanSession (not dict)
        - Service uses model attributes (not dict access)
        """
        # Mock dependencies
        with patch('api.services.scan.ParserFactory') as mock_parser_factory, \
             patch('api.services.scan.get_customer_db', return_value=mock_customer_db):

            # Mock parser
            mock_parser = MagicMock()
            mock_parsed_data = MagicMock()
            mock_parsed_data.tool_name = "Semgrep"
            mock_parsed_data.tool_version = "1.0.0"
            mock_parsed_data.scan_timestamp = "2024-01-15T10:30:00Z"
            mock_parsed_data.metadata = {}
            mock_parsed_data.findings = []
            mock_parsed_data.components = []

            mock_parser.parse = Mock(return_value=mock_parsed_data)
            mock_parser_factory.get_parser = Mock(return_value=mock_parser)

            # Mock repository - return ScanSession model
            with patch('api.services.scan.ScanSessionRepository') as mock_session_repo_class, \
                 patch('api.services.scan.ScanFindingRepository') as mock_finding_repo_class, \
                 patch('api.services.scan.ComponentRepository') as mock_component_repo_class:

                mock_session_repo = MagicMock()
                mock_finding_repo = MagicMock()
                mock_component_repo = MagicMock()

                # create_session returns ScanSession model
                mock_session = ScanSession(
                    _key="session_123",
                    customer_id="customer_abc",
                    tool_name="Semgrep",
                    tool_version="1.0.0",
                    scan_timestamp="2024-01-15T10:30:00Z",
                    scan_type="sarif",
                    status="processing",
                    findings_count=0,
                    components_count=0,
                    metadata={},
                    created_at="2024-01-15T10:30:00Z",
                    updated_at="2024-01-15T10:30:00Z",
                )

                mock_session_repo.create_session = Mock(return_value=mock_session)

                # update_session_status returns updated ScanSession model
                mock_updated_session = ScanSession(
                    _key="session_123",
                    customer_id="customer_abc",
                    tool_name="Semgrep",
                    tool_version="1.0.0",
                    scan_timestamp="2024-01-15T10:30:00Z",
                    scan_type="sarif",
                    status="completed",
                    findings_count=0,
                    components_count=0,
                    metadata={},
                    created_at="2024-01-15T10:30:00Z",
                    updated_at="2024-01-15T10:35:00Z",
                )

                mock_session_repo.update_session_status = Mock(return_value=mock_updated_session)

                mock_session_repo_class.return_value = mock_session_repo
                mock_finding_repo_class.return_value = mock_finding_repo
                mock_component_repo_class.return_value = mock_component_repo

                # Create service and ingest scan
                service = ScanIngestionService()
                result = await service.ingest_scan(
                    customer_id="customer_abc",
                    scan_request=mock_scan_request,
                )

                # Verify return type is ScanSession model
                assert isinstance(result, ScanSession)

                # Verify model attributes
                assert result._key == "session_123"
                assert result.status == "completed"
                assert result.customer_id == "customer_abc"
                assert result.tool_name == "Semgrep"

    @pytest.mark.asyncio
    async def test_store_findings_maps_parsed_finding_to_scan_finding(self, mock_customer_db):
        """
        AC-003 Test 2: _store_findings() maps ParsedFinding → ScanFinding.

        Verifies:
        - Service maps ParsedFinding (parser output) to ScanFinding (DB model)
        - Repository receives ScanFinding model fields
        """
        # Create mock parsed findings (parser output)
        mock_parsed_finding = MagicMock()
        mock_parsed_finding.cve_id = "cve-2024-1234"  # lowercase from parser
        mock_parsed_finding.severity = "high"  # lowercase from parser
        mock_parsed_finding.description = "SQL Injection"
        mock_parsed_finding.location = "src/app.py:42"
        mock_parsed_finding.tool_name = "Semgrep"
        mock_parsed_finding.raw_data = {"rule_id": "sql-injection"}

        # Mock finding repository
        mock_finding_repo = MagicMock()

        # create_finding returns ScanFinding model
        mock_scan_finding = ScanFinding(
            _key="finding_123",
            customer_id="customer_abc",
            scan_session_id="session_123",
            cve_id="CVE-2024-1234",  # Normalized to uppercase
            severity="HIGH",  # Normalized to uppercase
            description="SQL Injection",
            location="src/app.py:42",
            tool_name="Semgrep",
            raw_data={"rule_id": "sql-injection"},
            created_at="2024-01-15T10:30:00Z",
        )

        mock_finding_repo.create_finding = Mock(return_value=mock_scan_finding)

        # Create service and call _store_findings
        service = ScanIngestionService()
        result = await service._store_findings(
            customer_id="customer_abc",
            scan_session_id="session_123",
            findings=[mock_parsed_finding],
            finding_repo=mock_finding_repo,
        )

        # Verify create_finding was called with ParsedFinding attributes
        mock_finding_repo.create_finding.assert_called_once_with(
            customer_id="customer_abc",
            scan_session_id="session_123",
            cve_id="cve-2024-1234",  # From ParsedFinding
            severity="high",  # From ParsedFinding (will be normalized by model)
            description="SQL Injection",
            location="src/app.py:42",
            tool_name="Semgrep",
            raw_data={"rule_id": "sql-injection"},
        )

        # Verify result contains ScanFinding models
        assert len(result) == 1
        assert isinstance(result[0], ScanFinding)
        assert result[0].cve_id == "CVE-2024-1234"  # Normalized
        assert result[0].severity == "HIGH"  # Normalized

    @pytest.mark.asyncio
    async def test_service_uses_model_attributes_not_dict_access(self, mock_customer_db, mock_scan_request):
        """
        AC-003 Test 3: Service uses model attributes (not dict access).

        Verifies:
        - Service calls scan_session._key (not scan_session.get("_key"))
        - Service works with typed models throughout
        """
        with patch('api.services.scan.ParserFactory') as mock_parser_factory, \
             patch('api.services.scan.get_customer_db', return_value=mock_customer_db):

            # Mock parser
            mock_parser = MagicMock()
            mock_parsed_data = MagicMock()
            mock_parsed_data.tool_name = "Semgrep"
            mock_parsed_data.tool_version = "1.0.0"
            mock_parsed_data.scan_timestamp = "2024-01-15T10:30:00Z"
            mock_parsed_data.metadata = {}
            mock_parsed_data.findings = []
            mock_parsed_data.components = []

            mock_parser.parse = Mock(return_value=mock_parsed_data)
            mock_parser_factory.get_parser = Mock(return_value=mock_parser)

            # Mock repository
            with patch('api.services.scan.ScanSessionRepository') as mock_session_repo_class, \
                 patch('api.services.scan.ScanFindingRepository') as mock_finding_repo_class, \
                 patch('api.services.scan.ComponentRepository') as mock_component_repo_class:

                mock_session_repo = MagicMock()
                mock_finding_repo = MagicMock()
                mock_component_repo = MagicMock()

                # create_session returns ScanSession model with _key attribute
                mock_session = ScanSession(
                    _key="session_456",
                    customer_id="customer_abc",
                    tool_name="Semgrep",
                    tool_version="1.0.0",
                    scan_timestamp="2024-01-15T10:30:00Z",
                    scan_type="sarif",
                    status="processing",
                    findings_count=0,
                    components_count=0,
                    metadata={},
                    created_at="2024-01-15T10:30:00Z",
                    updated_at="2024-01-15T10:30:00Z",
                )

                mock_session_repo.create_session = Mock(return_value=mock_session)

                mock_updated_session = ScanSession(
                    _key="session_456",
                    customer_id="customer_abc",
                    tool_name="Semgrep",
                    tool_version="1.0.0",
                    scan_timestamp="2024-01-15T10:30:00Z",
                    scan_type="sarif",
                    status="completed",
                    findings_count=0,
                    components_count=0,
                    metadata={},
                    created_at="2024-01-15T10:30:00Z",
                    updated_at="2024-01-15T10:35:00Z",
                )

                mock_session_repo.update_session_status = Mock(return_value=mock_updated_session)

                mock_session_repo_class.return_value = mock_session_repo
                mock_finding_repo_class.return_value = mock_finding_repo
                mock_component_repo_class.return_value = mock_component_repo

                # Create service and ingest scan
                service = ScanIngestionService()
                result = await service.ingest_scan(
                    customer_id="customer_abc",
                    scan_request=mock_scan_request,
                )

                # Verify update_session_status was called with session_key from model attribute
                mock_session_repo.update_session_status.assert_called_once()
                call_kwargs = mock_session_repo.update_session_status.call_args[1]
                assert call_kwargs['session_key'] == "session_456"  # From mock_session._key

                # Verify result is ScanSession model
                assert isinstance(result, ScanSession)
                assert result._key == "session_456"

    @pytest.mark.asyncio
    async def test_service_handles_empty_findings_and_components(self, mock_customer_db, mock_scan_request):
        """
        AC-003 Test 4: Service handles empty findings/components lists.

        Verifies:
        - Service correctly processes scans with no findings
        - Service returns ScanSession with zero counts
        """
        with patch('api.services.scan.ParserFactory') as mock_parser_factory, \
             patch('api.services.scan.get_customer_db', return_value=mock_customer_db):

            # Mock parser with no findings/components
            mock_parser = MagicMock()
            mock_parsed_data = MagicMock()
            mock_parsed_data.tool_name = "Semgrep"
            mock_parsed_data.tool_version = "1.0.0"
            mock_parsed_data.scan_timestamp = "2024-01-15T10:30:00Z"
            mock_parsed_data.metadata = {}
            mock_parsed_data.findings = []  # Empty findings
            mock_parsed_data.components = []  # Empty components

            mock_parser.parse = Mock(return_value=mock_parsed_data)
            mock_parser_factory.get_parser = Mock(return_value=mock_parser)

            # Mock repository
            with patch('api.services.scan.ScanSessionRepository') as mock_session_repo_class, \
                 patch('api.services.scan.ScanFindingRepository') as mock_finding_repo_class, \
                 patch('api.services.scan.ComponentRepository') as mock_component_repo_class:

                mock_session_repo = MagicMock()
                mock_finding_repo = MagicMock()
                mock_component_repo = MagicMock()

                mock_session = ScanSession(
                    _key="session_789",
                    customer_id="customer_abc",
                    tool_name="Semgrep",
                    tool_version="1.0.0",
                    scan_timestamp="2024-01-15T10:30:00Z",
                    scan_type="sarif",
                    status="processing",
                    findings_count=0,
                    components_count=0,
                    metadata={},
                    created_at="2024-01-15T10:30:00Z",
                    updated_at="2024-01-15T10:30:00Z",
                )

                mock_updated_session = ScanSession(
                    _key="session_789",
                    customer_id="customer_abc",
                    tool_name="Semgrep",
                    tool_version="1.0.0",
                    scan_timestamp="2024-01-15T10:30:00Z",
                    scan_type="sarif",
                    status="completed",
                    findings_count=0,  # Zero findings
                    components_count=0,  # Zero components
                    metadata={},
                    created_at="2024-01-15T10:30:00Z",
                    updated_at="2024-01-15T10:35:00Z",
                )

                mock_session_repo.create_session = Mock(return_value=mock_session)
                mock_session_repo.update_session_status = Mock(return_value=mock_updated_session)

                mock_session_repo_class.return_value = mock_session_repo
                mock_finding_repo_class.return_value = mock_finding_repo
                mock_component_repo_class.return_value = mock_component_repo

                # Create service and ingest scan
                service = ScanIngestionService()
                result = await service.ingest_scan(
                    customer_id="customer_abc",
                    scan_request=mock_scan_request,
                )

                # Verify result is ScanSession with zero counts
                assert isinstance(result, ScanSession)
                assert result.findings_count == 0
                assert result.components_count == 0
                assert result.status == "completed"
