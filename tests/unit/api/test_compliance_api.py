"""
Unit tests for Compliance API endpoints.

Covers:
  AC-CV-010: GET /v1/compliance/violations returns 200 with violations list
  AC-CV-011: Violation items include required fields
  AC-CV-012: GET /v1/compliance/violations returns 404 for wrong tenant
  AC-CV-013: GET /v1/compliance/coverage returns 200 with required fields
  AC-CV-014: by_framework items include framework, violated_control_count, control_ids
  AC-CV-015: GET /v1/compliance/coverage returns 404 for wrong tenant
  Extra: violations endpoint returns empty list when no violations exist
"""

from __future__ import annotations

from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_customer(tenant_id: str = "tenant_abc"):
    from api.core.security import Customer
    return Customer(
        **{"_key": tenant_id},
        name="Test Tenant",
        tier="pro",
        database_name=f"complira_tenant_{tenant_id}",
    )


def _make_client(aql_side_effect, tenant_id: str = "tenant_abc") -> TestClient:
    """Build a TestClient with mocked DB and auth dependencies."""
    from unittest.mock import patch
    from api.main import app
    from api.core.security import get_current_customer

    mock_db = MagicMock()
    mock_db.aql.execute.side_effect = aql_side_effect

    app.dependency_overrides[get_current_customer] = lambda: _make_customer(tenant_id)

    with patch("api.v1.endpoints.compliance.get_reference_db", return_value=mock_db):
        client = TestClient(app, raise_server_exceptions=False)
        yield client

    app.dependency_overrides.pop(get_current_customer, None)


# ---------------------------------------------------------------------------
# GET /v1/compliance/violations — happy path
# Covers AC-CV-010, AC-CV-011
# ---------------------------------------------------------------------------

@pytest.fixture
def client_violations_found():
    aql_result = {
        "run_exists": True,
        "items": [
            {
                "finding_id": "fp1",
                "cve_id": "CVE-2024-1234",
                "control_id": "SI-2",
                "framework": "NIST_800_53",
                "confidence": 1.0,
                "evidence_path": ["CVE_2024_1234", "CWE_79", "CAPEC_86", "T1190", "SI-2"],
            },
            {
                "finding_id": "fp2",
                "cve_id": "CVE-2021-44228",
                "control_id": "AC-2",
                "framework": "NIST_800_53",
                "confidence": 1.0,
                "evidence_path": ["CVE_2021_44228", "CWE_20", "CAPEC_10", "T1059", "AC-2"],
            },
        ],
    }

    def side_effect(query, bind_vars=None, **kwargs):
        return iter([aql_result])

    yield from _make_client(side_effect)


def test_violations_returns_200_with_items(client_violations_found):
    """AC-CV-010"""
    resp = client_violations_found.get("/v1/compliance/violations?scan_run_id=run123")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "items" in data
    assert data["total"] == 2


def test_violations_items_include_required_fields(client_violations_found):
    """AC-CV-011"""
    resp = client_violations_found.get("/v1/compliance/violations?scan_run_id=run123")
    assert resp.status_code == 200
    item = resp.json()["data"]["items"][0]
    assert "finding_id" in item
    assert "cve_id" in item
    assert "control_id" in item
    assert "framework" in item
    assert "confidence" in item
    assert "evidence_path" in item
    assert item["finding_id"] == "fp1"
    assert item["control_id"] == "SI-2"
    assert item["confidence"] == 1.0


# ---------------------------------------------------------------------------
# GET /v1/compliance/violations — empty violations
# ---------------------------------------------------------------------------

@pytest.fixture
def client_violations_empty():
    def side_effect(query, bind_vars=None, **kwargs):
        return iter([{"run_exists": True, "items": []}])

    yield from _make_client(side_effect)


def test_violations_empty_returns_200_with_zero_total(client_violations_empty):
    resp = client_violations_empty.get("/v1/compliance/violations?scan_run_id=run123")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["items"] == []
    assert data["total"] == 0


# ---------------------------------------------------------------------------
# GET /v1/compliance/violations — 404
# Covers AC-CV-012
# ---------------------------------------------------------------------------

@pytest.fixture
def client_violations_not_found():
    def side_effect(query, bind_vars=None, **kwargs):
        return iter([{"run_exists": False, "items": []}])

    yield from _make_client(side_effect)


def test_violations_404_for_wrong_tenant(client_violations_not_found):
    """AC-CV-012"""
    resp = client_violations_not_found.get("/v1/compliance/violations?scan_run_id=run_unknown")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /v1/compliance/coverage — happy path
# Covers AC-CV-013, AC-CV-014
# ---------------------------------------------------------------------------

@pytest.fixture
def client_coverage_found():
    aql_result = {
        "run_exists": True,
        "scan_run_id": "run123",
        "total_findings": 50,
        "findings_with_violations": 12,
        "by_framework": [
            {
                "framework": "NIST_800_53",
                "violated_control_count": 5,
                "control_ids": ["AC-2", "SI-2", "CM-6", "SC-7", "IA-5"],
            }
        ],
    }

    def side_effect(query, bind_vars=None, **kwargs):
        return iter([aql_result])

    yield from _make_client(side_effect)


def test_coverage_returns_200_with_required_fields(client_coverage_found):
    """AC-CV-013"""
    resp = client_coverage_found.get("/v1/compliance/coverage?scan_run_id=run123")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_findings"] == 50
    assert data["findings_with_violations"] == 12
    assert "by_framework" in data


def test_coverage_by_framework_includes_required_fields(client_coverage_found):
    """AC-CV-014"""
    resp = client_coverage_found.get("/v1/compliance/coverage?scan_run_id=run123")
    assert resp.status_code == 200
    fw = resp.json()["data"]["by_framework"][0]
    assert "framework" in fw
    assert "violated_control_count" in fw
    assert "control_ids" in fw
    assert fw["framework"] == "NIST_800_53"
    assert fw["violated_control_count"] == 5
    assert len(fw["control_ids"]) == 5


# ---------------------------------------------------------------------------
# GET /v1/compliance/coverage — 404
# Covers AC-CV-015
# ---------------------------------------------------------------------------

@pytest.fixture
def client_coverage_not_found():
    def side_effect(query, bind_vars=None, **kwargs):
        return iter([{
            "run_exists": False,
            "scan_run_id": "run_unknown",
            "total_findings": 0,
            "findings_with_violations": 0,
            "by_framework": [],
        }])

    yield from _make_client(side_effect)


def test_coverage_404_for_wrong_tenant(client_coverage_not_found):
    """AC-CV-015"""
    resp = client_coverage_not_found.get("/v1/compliance/coverage?scan_run_id=run_unknown")
    assert resp.status_code == 404
