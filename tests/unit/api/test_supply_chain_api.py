"""
Unit tests for Supply Chain Intelligence API.

Covers all 13 acceptance criteria:
  AC-SC-001: Component detail includes purl, name, version, type
  AC-SC-002: Component detail includes projects list
  AC-SC-003: Component detail includes dependencies and dependents
  AC-SC-004: Component detail includes vulnerabilities list
  AC-SC-005: Returns 404 for unknown PURL or PURL not accessible to tenant
  AC-SC-006: Affected-projects items include project_id, component_purl, cve_id
  AC-SC-007: Returns empty items list for CVE with no affected components
  AC-SC-008: Affected-projects results scoped to caller tenant_id
  AC-SC-009: Dependency path returns path list and path_length when path exists
  AC-SC-010: Dependency path returns found=false and empty path when no path
  AC-SC-011: Risk summary includes total_components, vulnerable_components, critical_count, high_count
  AC-SC-012: top_depended_on contains up to 5 entries with purl and dependent_count
  AC-SC-013: Returns 404 when project_id not found for tenant
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

    with patch("api.v1.endpoints.supply_chain.get_reference_db", return_value=mock_db):
        client = TestClient(app, raise_server_exceptions=False)
        yield client

    app.dependency_overrides.pop(get_current_customer, None)


# ---------------------------------------------------------------------------
# S-SC-001 / S-SC-002 / S-SC-003 / S-SC-004: Component detail happy path
# Covers AC-SC-001, AC-SC-002, AC-SC-003, AC-SC-004
# ---------------------------------------------------------------------------

@pytest.fixture
def client_component_found():
    aql_row = {
        "purl": "pkg:npm/lodash@4.17.21",
        "name": "lodash",
        "version": "4.17.21",
        "type": "library",
        "projects": ["proj_123"],
        "dependencies": ["pkg:npm/foo@1.0"],
        "dependents": ["pkg:npm/bar@2.0"],
        "vulnerabilities": ["CVE-2021-23337"],
    }

    def side_effect(query, bind_vars=None, **kwargs):
        return iter([aql_row])

    yield from _make_client(side_effect)


def test_component_detail_includes_purl_name_version_type(client_component_found):
    """AC-SC-001"""
    resp = client_component_found.get("/v1/supply-chain/component?purl=pkg:npm/lodash@4.17.21")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["purl"] == "pkg:npm/lodash@4.17.21"
    assert data["name"] == "lodash"
    assert data["version"] == "4.17.21"
    assert data["type"] == "library"


def test_component_detail_includes_projects(client_component_found):
    """AC-SC-002"""
    resp = client_component_found.get("/v1/supply-chain/component?purl=pkg:npm/lodash@4.17.21")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "projects" in data
    assert "proj_123" in data["projects"]


def test_component_detail_includes_dependencies_and_dependents(client_component_found):
    """AC-SC-003"""
    resp = client_component_found.get("/v1/supply-chain/component?purl=pkg:npm/lodash@4.17.21")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "dependencies" in data
    assert "dependents" in data
    assert "pkg:npm/foo@1.0" in data["dependencies"]
    assert "pkg:npm/bar@2.0" in data["dependents"]


def test_component_detail_includes_vulnerabilities(client_component_found):
    """AC-SC-004"""
    resp = client_component_found.get("/v1/supply-chain/component?purl=pkg:npm/lodash@4.17.21")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "vulnerabilities" in data
    assert "CVE-2021-23337" in data["vulnerabilities"]


# ---------------------------------------------------------------------------
# S-SC-002: Component detail 404 — unknown PURL / no tenant access
# Covers AC-SC-005
# ---------------------------------------------------------------------------

@pytest.fixture
def client_component_not_found():
    def side_effect(query, bind_vars=None, **kwargs):
        # Return row with None purl (component does not exist)
        return iter([{"purl": None, "name": None, "version": None, "type": None,
                      "projects": [], "dependencies": [], "dependents": [], "vulnerabilities": []}])

    yield from _make_client(side_effect)


@pytest.fixture
def client_component_no_tenant_access():
    def side_effect(query, bind_vars=None, **kwargs):
        # Component exists but tenant has no projects using it
        return iter([{
            "purl": "pkg:npm/lodash@4.17.21",
            "name": "lodash",
            "version": "4.17.21",
            "type": "library",
            "projects": [],  # no tenant projects
            "dependencies": [],
            "dependents": [],
            "vulnerabilities": [],
        }])

    yield from _make_client(side_effect)


def test_component_detail_404_unknown_purl(client_component_not_found):
    """AC-SC-005 — component does not exist"""
    resp = client_component_not_found.get("/v1/supply-chain/component?purl=pkg:npm/unknown@9.9.9")
    assert resp.status_code == 404


def test_component_detail_404_no_tenant_access(client_component_no_tenant_access):
    """AC-SC-005 — component exists but tenant has no access"""
    resp = client_component_no_tenant_access.get("/v1/supply-chain/component?purl=pkg:npm/lodash@4.17.21")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# S-SC-003: Affected projects happy path
# Covers AC-SC-006, AC-SC-008
# ---------------------------------------------------------------------------

@pytest.fixture
def client_affected_projects_found():
    aql_result = [
        {"project_id": "proj_123", "component_purl": "pkg:npm/log4j@2.14.1", "cve_id": "CVE-2021-44228"},
        {"project_id": "proj_456", "component_purl": "pkg:npm/log4j@2.14.1", "cve_id": "CVE-2021-44228"},
    ]

    def side_effect(query, bind_vars=None, **kwargs):
        return iter([aql_result])

    yield from _make_client(side_effect)


def test_affected_projects_items_include_required_fields(client_affected_projects_found):
    """AC-SC-006"""
    resp = client_affected_projects_found.get("/v1/supply-chain/affected-projects?cve_id=CVE-2021-44228")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "items" in data
    assert len(data["items"]) == 2
    item = data["items"][0]
    assert "project_id" in item
    assert "component_purl" in item
    assert "cve_id" in item


def test_affected_projects_tenant_scoped(client_affected_projects_found):
    """AC-SC-008 — only caller tenant's projects returned (tenant_id in AQL bind_vars)"""
    from unittest.mock import patch
    from api.main import app
    from api.core.security import get_current_customer, Customer

    aql_calls = []

    def tracking_side_effect(query, bind_vars=None, **kwargs):
        aql_calls.append(bind_vars or {})
        return iter([[]])

    mock_db = MagicMock()
    mock_db.aql.execute.side_effect = tracking_side_effect

    app.dependency_overrides[get_current_customer] = lambda: Customer(
        **{"_key": "other_tenant"},
        name="Other",
        tier="pro",
        database_name="complira_tenant_other_tenant",
    )

    with patch("api.v1.endpoints.supply_chain.get_reference_db", return_value=mock_db):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/v1/supply-chain/affected-projects?cve_id=CVE-2021-44228")

    app.dependency_overrides.pop(get_current_customer, None)

    assert resp.status_code == 200
    assert len(aql_calls) == 1
    assert aql_calls[0].get("tenant_id") == "other_tenant"


# ---------------------------------------------------------------------------
# S-SC-004: Affected projects — empty result
# Covers AC-SC-007
# ---------------------------------------------------------------------------

@pytest.fixture
def client_affected_projects_empty():
    def side_effect(query, bind_vars=None, **kwargs):
        return iter([[]])  # outer list wraps empty affected list

    yield from _make_client(side_effect)


def test_affected_projects_empty_for_unknown_cve(client_affected_projects_empty):
    """AC-SC-007"""
    resp = client_affected_projects_empty.get("/v1/supply-chain/affected-projects?cve_id=CVE-1999-0001")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["items"] == []
    assert data["total"] == 0


# ---------------------------------------------------------------------------
# S-SC-006: Dependency path — path found
# Covers AC-SC-009
# ---------------------------------------------------------------------------

@pytest.fixture
def client_dependency_path_found():
    path_purls = ["pkg:npm/a@1.0", "pkg:npm/b@2.0", "pkg:npm/c@3.0"]

    def side_effect(query, bind_vars=None, **kwargs):
        # path_result is [[purl1, purl2, purl3]]
        return iter([[path_purls]])

    yield from _make_client(side_effect)


def test_dependency_path_found(client_dependency_path_found):
    """AC-SC-009"""
    resp = client_dependency_path_found.get(
        "/v1/supply-chain/dependency-path?from_purl=pkg:npm/a@1.0&to_purl=pkg:npm/c@3.0"
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["found"] is True
    assert len(data["path"]) == 3
    assert data["path_length"] == 3
    assert data["path"][0] == "pkg:npm/a@1.0"
    assert data["path"][-1] == "pkg:npm/c@3.0"


# ---------------------------------------------------------------------------
# S-SC-007: Dependency path — no path
# Covers AC-SC-010
# ---------------------------------------------------------------------------

@pytest.fixture
def client_dependency_path_not_found():
    def side_effect(query, bind_vars=None, **kwargs):
        return iter([[[]]])  # path_result = [[]] — no path

    yield from _make_client(side_effect)


def test_dependency_path_not_found(client_dependency_path_not_found):
    """AC-SC-010"""
    resp = client_dependency_path_not_found.get(
        "/v1/supply-chain/dependency-path?from_purl=pkg:npm/a@1.0&to_purl=pkg:npm/z@9.9"
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["found"] is False
    assert data["path"] == []
    assert data["path_length"] == 0


# ---------------------------------------------------------------------------
# S-SC-008: Risk summary happy path
# Covers AC-SC-011, AC-SC-012
# ---------------------------------------------------------------------------

@pytest.fixture
def client_risk_summary_found():
    aql_row = {
        "project_exists": True,
        "project_id": "proj_123",
        "total_components": 42,
        "vulnerable_components": 7,
        "critical_count": 2,
        "high_count": 5,
        "top_depended_on": [
            {"purl": "pkg:npm/lodash@4.17.21", "dependent_count": 15},
            {"purl": "pkg:npm/express@4.18.0", "dependent_count": 12},
            {"purl": "pkg:npm/axios@1.4.0", "dependent_count": 8},
        ],
    }

    def side_effect(query, bind_vars=None, **kwargs):
        return iter([aql_row])

    yield from _make_client(side_effect)


def test_risk_summary_includes_required_fields(client_risk_summary_found):
    """AC-SC-011"""
    resp = client_risk_summary_found.get("/v1/supply-chain/risk-summary?project_id=proj_123")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_components"] == 42
    assert data["vulnerable_components"] == 7
    assert data["critical_count"] == 2
    assert data["high_count"] == 5


def test_risk_summary_top_depended_on(client_risk_summary_found):
    """AC-SC-012"""
    resp = client_risk_summary_found.get("/v1/supply-chain/risk-summary?project_id=proj_123")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "top_depended_on" in data
    assert len(data["top_depended_on"]) <= 5
    entry = data["top_depended_on"][0]
    assert "purl" in entry
    assert "dependent_count" in entry


# ---------------------------------------------------------------------------
# S-SC-009: Risk summary 404 — project not found for tenant
# Covers AC-SC-013
# ---------------------------------------------------------------------------

@pytest.fixture
def client_risk_summary_project_not_found():
    aql_row = {
        "project_exists": False,
        "project_id": "proj_999",
        "total_components": 0,
        "vulnerable_components": 0,
        "critical_count": 0,
        "high_count": 0,
        "top_depended_on": [],
    }

    def side_effect(query, bind_vars=None, **kwargs):
        return iter([aql_row])

    yield from _make_client(side_effect)


def test_risk_summary_404_project_not_found(client_risk_summary_project_not_found):
    """AC-SC-013"""
    resp = client_risk_summary_project_not_found.get("/v1/supply-chain/risk-summary?project_id=proj_999")
    assert resp.status_code == 404
