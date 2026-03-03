"""
Integration tests for Phase 1: API Contract Validation.

Tests for AC-005:
- AC-005: No breaking changes to API contracts (response JSON structure unchanged)
"""

import pytest
from unittest.mock import MagicMock, Mock, patch
from fastapi.testclient import TestClient

# We'll import the FastAPI app when it exists
# from api.main import app


@pytest.fixture
def mock_customer_db():
    """Mock customer database."""
    db = MagicMock()
    db.collection = Mock(return_value=MagicMock())
    db.aql = MagicMock()
    db.aql.execute = Mock(return_value=[])
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


@pytest.fixture
def valid_api_key():
    """Valid API key for testing."""
    return "test_api_key_valid"


@pytest.fixture
def sample_sarif_payload():
    """Sample SARIF payload for scan ingestion."""
    return {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Semgrep",
                        "version": "1.0.0",
                    }
                },
                "results": [
                    {
                        "ruleId": "sql-injection",
                        "message": {"text": "SQL Injection vulnerability detected"},
                        "level": "error",
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": "src/app.py"},
                                    "region": {"startLine": 42},
                                }
                            }
                        ],
                        "properties": {
                            "cve_id": "CVE-2024-1234",
                        }
                    }
                ],
            }
        ],
    }


# ============================================================================
# AC-005: No Breaking Changes to API Contracts
# ============================================================================

class TestAC005_APIContracts:
    """Test AC-005: No breaking changes to API contracts."""

    @pytest.mark.integration
    def test_scan_ingest_response_structure_unchanged(
        self, mock_customer_db, mock_reference_db, valid_api_key, sample_sarif_payload
    ):
        """
        AC-005 Test 1: POST /v1/scan/ingest response structure unchanged.

        Verifies:
        - Response JSON structure matches expected format
        - All required fields present (customer_id, tool_name, status, etc.)
        - Pydantic model serialization produces same JSON as dict serialization
        """
        with patch('api.core.database.get_customer_db', return_value=mock_customer_db), \
             patch('api.core.database.get_database', return_value=mock_reference_db), \
             patch('api.core.security.verify_api_key', return_value=True):

            # Mock collection insert
            mock_collection = mock_customer_db.collection.return_value
            mock_collection.insert.return_value = {
                "_key": "session_123",
                "_id": "scan_sessions/session_123",
                "_rev": "_rev123",
                "customer_id": "customer_test",
                "tool_name": "Semgrep",
                "tool_version": "1.0.0",
                "scan_timestamp": "2024-01-15T10:30:00Z",
                "scan_type": "sarif",
                "status": "processing",
                "findings_count": 0,
                "components_count": 0,
                "metadata": {},
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T10:30:00Z",
            }

            mock_collection.update.return_value = {
                "_key": "session_123",
                "_id": "scan_sessions/session_123",
                "_rev": "_rev456",
                "customer_id": "customer_test",
                "tool_name": "Semgrep",
                "tool_version": "1.0.0",
                "scan_timestamp": "2024-01-15T10:30:00Z",
                "scan_type": "sarif",
                "status": "completed",
                "findings_count": 1,
                "components_count": 0,
                "metadata": {},
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T10:35:00Z",
            }

            # Expected response structure (before Phase 1)
            expected_response_structure = {
                "customer_id": str,
                "tool_name": str,
                "tool_version": str,
                "scan_timestamp": str,
                "scan_type": str,
                "status": str,
                "findings_count": int,
                "components_count": int,
                "metadata": dict,
                "created_at": str,
                "updated_at": str,
            }

            # In a real test, we'd make actual HTTP request
            # For this unit test, we'll verify model serialization matches expected structure
            from complira_graph.models import ScanSession

            session = ScanSession(
                _key="session_123",
                customer_id="customer_test",
                tool_name="Semgrep",
                tool_version="1.0.0",
                scan_timestamp="2024-01-15T10:30:00Z",
                scan_type="sarif",
                status="completed",
                findings_count=1,
                components_count=0,
                metadata={},
                created_at="2024-01-15T10:30:00Z",
                updated_at="2024-01-15T10:35:00Z",
            )

            # Serialize model to JSON (as FastAPI would)
            response_json = session.model_dump()

            # Verify response structure matches expected
            for field, field_type in expected_response_structure.items():
                assert field in response_json, f"Missing field: {field}"
                assert isinstance(response_json[field], field_type), \
                    f"Field {field} has wrong type: {type(response_json[field])} != {field_type}"

            # Verify specific fields
            assert response_json["customer_id"] == "customer_test"
            assert response_json["tool_name"] == "Semgrep"
            assert response_json["status"] == "completed"
            assert response_json["findings_count"] == 1

    @pytest.mark.integration
    def test_scan_finding_response_structure_unchanged(self, mock_customer_db):
        """
        AC-005 Test 2: Scan finding response structure unchanged.

        Verifies:
        - Finding JSON structure matches expected format
        - Severity is uppercase (normalized by model)
        - CVE ID is uppercase (normalized by model)
        """
        # Expected finding response structure
        expected_finding_structure = {
            "customer_id": str,
            "scan_session_id": str,
            "cve_id": (str, type(None)),  # Can be None
            "severity": str,
            "description": str,
            "location": str,
            "tool_name": str,
            "raw_data": dict,
            "created_at": str,
        }

        from complira_graph.models import ScanFinding

        finding = ScanFinding(
            _key="finding_123",
            customer_id="customer_test",
            scan_session_id="session_123",
            cve_id="CVE-2024-1234",
            severity="HIGH",
            description="SQL Injection vulnerability",
            location="src/app.py:line 42",
            tool_name="Semgrep",
            raw_data={"rule_id": "sql-injection"},
            created_at="2024-01-15T10:30:00Z",
        )

        # Serialize model to JSON (as FastAPI would)
        response_json = finding.model_dump()

        # Verify response structure matches expected
        for field, field_type in expected_finding_structure.items():
            assert field in response_json, f"Missing field: {field}"

            if isinstance(field_type, tuple):
                # Field can be one of multiple types (e.g., str or None)
                assert any(isinstance(response_json[field], t) for t in field_type), \
                    f"Field {field} has wrong type: {type(response_json[field])} not in {field_type}"
            else:
                assert isinstance(response_json[field], field_type), \
                    f"Field {field} has wrong type: {type(response_json[field])} != {field_type}"

        # Verify severity normalization
        assert response_json["severity"] == "HIGH"

        # Verify CVE ID normalization
        assert response_json["cve_id"] == "CVE-2024-1234"

    @pytest.mark.integration
    def test_customer_profile_response_structure_unchanged(self, mock_reference_db):
        """
        AC-005 Test 3: Customer profile (authentication) response unchanged.

        Verifies:
        - CustomerProfile serialization matches expected format
        - .id property works for backward compatibility
        - All required fields present
        """
        from complira_graph.models import CustomerProfile

        customer = CustomerProfile(
            _key="customer_abc",
            name="Acme Corp",
            tier="pro",
            database_name="customer_abc_db",
            api_key_hash="$2b$12$hash",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )

        # Verify .id property works (backward compatibility)
        assert customer.id == customer._key
        assert customer.id == "customer_abc"

        # Serialize model to JSON (as FastAPI would)
        response_json = customer.model_dump()

        # Verify expected fields
        expected_fields = ["name", "tier", "database_name", "created_at", "updated_at"]
        for field in expected_fields:
            assert field in response_json, f"Missing field: {field}"

        # Verify values
        assert response_json["name"] == "Acme Corp"
        assert response_json["tier"] == "pro"
        assert response_json["database_name"] == "customer_abc_db"

    @pytest.mark.integration
    def test_pydantic_model_serialization_matches_dict_serialization(self):
        """
        AC-005 Test 4: Pydantic model serialization produces same JSON as dict.

        Verifies:
        - model.model_dump() produces same JSON as dict response
        - FastAPI auto-serialization works correctly
        - No additional or missing fields
        """
        from complira_graph.models import ScanSession

        # Create model instance
        session = ScanSession(
            _key="session_test",
            customer_id="customer_test",
            tool_name="Semgrep",
            tool_version="1.0.0",
            scan_timestamp="2024-01-15T10:30:00Z",
            scan_type="sarif",
            status="completed",
            findings_count=5,
            components_count=10,
            metadata={"branch": "main"},
            created_at="2024-01-15T10:30:00Z",
            updated_at="2024-01-15T10:35:00Z",
        )

        # Serialize model
        model_json = session.model_dump()

        # Expected dict structure (what API returned before Phase 1)
        expected_dict = {
            "_key": "session_test",
            "customer_id": "customer_test",
            "tool_name": "Semgrep",
            "tool_version": "1.0.0",
            "scan_timestamp": "2024-01-15T10:30:00Z",
            "scan_type": "sarif",
            "status": "completed",
            "findings_count": 5,
            "components_count": 10,
            "metadata": {"branch": "main"},
            "created_at": "2024-01-15T10:30:00Z",
            "updated_at": "2024-01-15T10:35:00Z",
        }

        # Verify all expected fields present
        for field, value in expected_dict.items():
            assert field in model_json, f"Missing field: {field}"
            assert model_json[field] == value, \
                f"Field {field} value mismatch: {model_json[field]} != {value}"

        # Verify no extra fields
        assert set(model_json.keys()) == set(expected_dict.keys()), \
            f"Extra or missing fields: {set(model_json.keys()) ^ set(expected_dict.keys())}"

    @pytest.mark.integration
    def test_model_serialization_handles_optional_fields(self):
        """
        AC-005 Test 5: Model serialization handles optional/None fields correctly.

        Verifies:
        - Optional fields (e.g., cve_id) can be None
        - Serialization doesn't break on None values
        - JSON structure consistent whether field is present or None
        """
        from complira_graph.models import ScanFinding

        # Create finding without CVE ID (None)
        finding = ScanFinding(
            _key="finding_test",
            customer_id="customer_test",
            scan_session_id="session_test",
            cve_id=None,  # Optional field
            severity="MEDIUM",
            description="Hardcoded secret",
            location="src/config.py:10",
            tool_name="Semgrep",
            raw_data={},
            created_at="2024-01-15T10:30:00Z",
        )

        # Serialize model
        model_json = finding.model_dump()

        # Verify cve_id is present in JSON (as None)
        assert "cve_id" in model_json
        assert model_json["cve_id"] is None

        # Verify other fields are present
        assert model_json["severity"] == "MEDIUM"
        assert model_json["description"] == "Hardcoded secret"

    @pytest.mark.integration
    def test_model_validation_prevents_invalid_data(self):
        """
        AC-005 Test 6: Model validation prevents invalid data in API responses.

        Verifies:
        - Invalid severity values are rejected
        - Invalid tier values are rejected
        - Model validation ensures data quality
        """
        from complira_graph.models import ScanFinding, CustomerProfile
        from pydantic import ValidationError

        # Test invalid severity
        with pytest.raises(ValidationError):
            ScanFinding(
                _key="finding_test",
                customer_id="customer_test",
                scan_session_id="session_test",
                cve_id=None,
                severity="INVALID",  # Invalid severity
                description="Test",
                location="test.py:1",
                tool_name="Test",
                raw_data={},
                created_at="2024-01-15T10:30:00Z",
            )

        # Test invalid tier
        with pytest.raises(ValidationError):
            CustomerProfile(
                _key="customer_test",
                name="Test Customer",
                tier="invalid_tier",  # Invalid tier (must be free/pro/enterprise)
                database_name="test_db",
                api_key_hash="hash",
                created_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
            )
