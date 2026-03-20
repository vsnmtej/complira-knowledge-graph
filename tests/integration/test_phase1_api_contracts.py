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
        AC-005 Test 1: POST /v1/scan/ingest response structure — v2.2 ScanRun model.

        Verifies:
        - v2.2 ScanRun JSON structure contains required fields
        - Pydantic model serialization produces expected JSON
        """
        from complira_graph.models.evidence import ScanRun

        run = ScanRun(
            _key="run_123",
            tenant_id="customer_test",
            tools_invoked=["semgrep"],
            status="completed",
            finding_counts={"critical": 0, "high": 1, "medium": 0, "low": 0, "info": 0},
            components_count=0,
            started_at="2024-01-15T10:30:00Z",
            completed_at="2024-01-15T10:35:00Z",
        )

        response_json = run.model_dump()

        # Verify required fields present
        for field in ["tenant_id", "tools_invoked", "status", "finding_counts", "components_count", "started_at"]:
            assert field in response_json, f"Missing field: {field}"

        assert response_json["tenant_id"] == "customer_test"
        assert response_json["tools_invoked"] == ["semgrep"]
        assert response_json["status"] == "completed"
        assert response_json["finding_counts"]["high"] == 1

    @pytest.mark.integration
    def test_scan_finding_response_structure_unchanged(self, mock_customer_db):
        """
        AC-005 Test 2: Scan finding response structure — v2.2 V22Finding model.

        Verifies:
        - V22Finding JSON structure contains required fields
        - Optional fields (cve_id) can be None
        """
        from complira_graph.models.evidence import V22Finding

        finding = V22Finding(
            _key="fp_abc123",
            fingerprint="fp_abc123",
            tenant_id="customer_test",
            scan_run_id="run_123",
            finding_type="sast",
            tool="semgrep",
            severity="high",
            cve_id="CVE-2024-1234",
            message="SQL Injection vulnerability",
            file_path="src/app.py",
            line_start=42,
        )

        response_json = finding.model_dump()

        for field in ["fingerprint", "tenant_id", "scan_run_id", "finding_type", "tool"]:
            assert field in response_json, f"Missing field: {field}"

        assert response_json["tenant_id"] == "customer_test"
        assert response_json["tool"] == "semgrep"
        assert response_json["severity"] == "high"
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
        AC-005 Test 4: ScanRun model serialization produces expected dict.

        Verifies:
        - model.model_dump(by_alias=True) includes _key
        - All set fields are present in output
        """
        from complira_graph.models.evidence import ScanRun

        run = ScanRun(
            _key="run_test",
            tenant_id="customer_test",
            tools_invoked=["semgrep"],
            status="completed",
            finding_counts={"critical": 0, "high": 5, "medium": 2, "low": 3, "info": 0},
            components_count=10,
            started_at="2024-01-15T10:30:00Z",
            completed_at="2024-01-15T10:35:00Z",
        )

        model_json = run.model_dump(by_alias=True)

        assert model_json["_key"] == "run_test"
        assert model_json["tenant_id"] == "customer_test"
        assert model_json["tools_invoked"] == ["semgrep"]
        assert model_json["status"] == "completed"
        assert model_json["finding_counts"]["high"] == 5
        assert model_json["components_count"] == 10

    @pytest.mark.integration
    def test_model_serialization_handles_optional_fields(self):
        """
        AC-005 Test 5: V22Finding serialization handles optional/None fields correctly.

        Verifies:
        - Optional fields (e.g., cve_id) can be None
        - Serialization doesn't break on None values
        """
        from complira_graph.models.evidence import V22Finding

        finding = V22Finding(
            _key="fp_xyz",
            fingerprint="fp_xyz",
            tenant_id="customer_test",
            scan_run_id="run_test",
            finding_type="secrets",
            tool="gitleaks",
            severity="medium",
            cve_id=None,
            message="Hardcoded secret",
            file_path="src/config.py",
            line_start=10,
        )

        model_json = finding.model_dump()

        assert "cve_id" in model_json
        assert model_json["cve_id"] is None
        assert model_json["severity"] == "medium"
        assert model_json["message"] == "Hardcoded secret"

    @pytest.mark.integration
    def test_model_validation_prevents_invalid_data(self):
        """
        AC-005 Test 6: CustomerProfile validation prevents invalid tier values.

        Verifies:
        - Invalid tier values are rejected
        - Model validation ensures data quality
        """
        from complira_graph.models import CustomerProfile
        from pydantic import ValidationError

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
