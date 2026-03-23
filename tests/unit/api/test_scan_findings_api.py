"""
Unit tests for Phase 6 API exposure of Phase 2 pipeline intelligence fields.

Covers all 17 acceptance criteria:
  AC-P6-001: findings response includes all Phase 1 + Phase 2 fields
  AC-P6-002: Phase 2 fields are null when pipeline not run
  AC-P6-003: llm_attack_surface validated as Literal
  AC-P6-004: epss_trend on finding validated as Literal
  AC-P6-005: scan_run includes llm_token_usage
  AC-P6-006: llm_token_usage is null when LLM stage not run
  AC-P6-007: Phase 2 status values accepted without validation error
  AC-P6-008: ?epss_trend=rising filters correctly
  AC-P6-009: ?epss_trend=invalid returns 422
  AC-P6-010: ?min_blast_radius=0.5 filters correctly
  AC-P6-011: ?min_blast_radius=1.5 returns 422
  AC-P6-012: ?sort_by=blast_radius_score sorts DESC
  AC-P6-013: ?sort_by=epss_velocity sorts DESC
  AC-P6-014: ?sort_by=invalid_field returns 422
  AC-P6-015: phase2_summary has correct counts and avg
  AC-P6-016: top_blast_radius_findings contains <= 5 items
  AC-P6-017: avg_blast_radius is null when no findings have blast radius
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_finding(key: str, **overrides) -> dict:
    """Return a minimal scan_findings DB document."""
    base = {
        "_key": key,
        "scan_run_id": "run1",
        "tenant_id": "t1",
        "cve_id": "CVE-2024-1234",
        "severity": "HIGH",
        "message": "test finding",
        "file_path": "src/main.py",
        "tool": "grype",
        "ingested_at": "2026-03-22T00:00:00Z",
        # Phase 1 fields
        "cvss_base": 7.5,
        "epss_score": 0.5,
        "epss_percentile": 0.8,
        "in_kev": False,
        "cwe_chain": ["CWE-79"],
        "d3fend_techniques": ["D3-NTF"],
        "risk_score": 0.55,
        "compaction_group_id": "cg_cwe79",
        "cluster_rank": 2,
        "compacted": False,
        # Phase 2 fields
        "llm_risk_summary": "This is a test risk summary.",
        "llm_remediation": "Upgrade the package.",
        "llm_attack_surface": "network",
        "llm_enriched_at": "2026-03-22T01:00:00Z",
        "blast_radius_score": 0.3,
        "affected_components": ["pkg:npm/foo@1.0"],
        "blast_radius_path": ["foo", "bar"],
        "blast_radius_computed_at": "2026-03-22T01:01:00Z",
        "epss_velocity": 0.005,
        "epss_trend": "rising",
        "epss_velocity_computed_at": "2026-03-22T01:02:00Z",
    }
    base.update(overrides)
    return base


def _make_scan_run_doc(key: str = "run1", tenant_id: str = "t1", **overrides) -> dict:
    base = {
        "_key": key,
        "tenant_id": tenant_id,
        "tools_invoked": ["grype"],
        "tool_version": "0.70.0",
        "scan_type": "sca",
        "created_at": "2026-03-22T00:00:00Z",
        "completed_at": "2026-03-22T00:01:00Z",
        "status": "velocity_computed",
        "finding_counts": {"total": 1},
        "components_count": 0,
        "metadata": {},
        "coverage_by_framework": {"NIST 800-53": 42.7},
        "llm_token_usage": {
            "input_tokens": 3500,
            "output_tokens": 800,
            "total_tokens": 4300,
            "model": "claude-haiku-4-5-20251001",
        },
    }
    base.update(overrides)
    return base


def _make_app_with_mocks(
    run_doc,
    findings=None,
    summary_raw=None,
    top5_keys=None,
):
    """
    Build FastAPI test app with mocked DB returning the supplied data.
    `summary_raw` = result of the Phase 2 summary AQL (list with one dict).
    `top5_keys` = list of _key strings for top-5 blast radius.
    """
    from api.main import app

    mock_db = MagicMock()

    # scan_runs.get(run_id) → run_doc
    mock_collection = MagicMock()
    mock_collection.get.return_value = run_doc
    mock_db.collection.return_value = mock_collection

    findings = findings or []

    # AQL execute is called multiple times in GET /{run_id} and GET /{run_id}/findings
    # We use side_effect to return different iterators for each call.
    if summary_raw is None:
        summary_raw = [
            {
                "trend_groups": [
                    {"trend": "rising", "count": 1},
                    {"trend": "stable", "count": 0},
                ],
                "avg_blast_radius": 0.3,
            }
        ]
    if top5_keys is None:
        top5_keys = ["fp1"]

    call_count = [0]

    def aql_side_effect(query, bind_vars=None, **kwargs):
        call_count[0] += 1
        # Determine which call this is based on query content
        if "scan_runs" in query or ("scan_run_id" not in query and "FILTER" not in query):
            return iter([])
        if "trend_groups" in query or "avg_blast_radius" in query:
            return iter(summary_raw)
        if "SORT f.blast_radius_score DESC" in query and "LIMIT 5" in query:
            return iter(top5_keys)
        # Default: findings query
        return iter(findings)

    mock_db.aql.execute.side_effect = aql_side_effect

    def override_db():
        return mock_db

    def override_customer():
        from api.core.security import Customer
        return Customer(id="t1", name="Test Tenant", tier="pro")

    with patch("api.core.database.get_reference_db", return_value=mock_db):
        return app, mock_db, override_db, override_customer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client_with_finding():
    """TestClient with one fully enriched finding."""
    from api.main import app
    from api.core.security import Customer

    run_doc = _make_scan_run_doc()
    finding = _make_finding("fp1")

    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_collection.get.return_value = run_doc
    mock_db.collection.return_value = mock_collection

    summary_raw = [{"trend_groups": [{"trend": "rising", "count": 1}], "avg_blast_radius": 0.3}]

    def aql_side_effect(query, bind_vars=None, **kwargs):
        if "trend_groups" in query:
            return iter(summary_raw)
        if "SORT f.blast_radius_score DESC" in query and "LIMIT 5" in query:
            return iter(["fp1"])
        return iter([finding])

    mock_db.aql.execute.side_effect = aql_side_effect

    with patch("api.core.database.get_reference_db", return_value=mock_db):
        from api.core.dependencies import get_current_customer as dep
        app.dependency_overrides[dep] = lambda: Customer(**{"_key": "t1", "name": "T", "database_name": "db_t1"})
        yield TestClient(app), mock_db
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# AC-P6-001: findings include all Phase 1 + Phase 2 fields
# ---------------------------------------------------------------------------

class TestFindingsFields:
    def test_phase1_fields_in_response(self, client_with_finding):
        client, _ = client_with_finding
        resp = client.get("/v1/scan/run1/findings")
        assert resp.status_code == 200
        findings = resp.json()["data"]
        assert len(findings) == 1
        f = findings[0]
        assert f["cvss_base"] == 7.5
        assert f["epss_score"] == 0.5
        assert f["epss_percentile"] == 0.8
        assert f["in_kev"] is False
        assert f["cwe_chain"] == ["CWE-79"]
        assert f["d3fend_techniques"] == ["D3-NTF"]
        assert f["risk_score"] == 0.55
        assert f["compaction_group_id"] == "cg_cwe79"
        assert f["cluster_rank"] == 2
        assert f["compacted"] is False

    def test_phase2_fields_in_response(self, client_with_finding):
        client, _ = client_with_finding
        resp = client.get("/v1/scan/run1/findings")
        assert resp.status_code == 200
        f = resp.json()["data"][0]
        assert f["llm_risk_summary"] == "This is a test risk summary."
        assert f["llm_remediation"] == "Upgrade the package."
        assert f["llm_attack_surface"] == "network"
        assert f["llm_enriched_at"] == "2026-03-22T01:00:00Z"
        assert f["blast_radius_score"] == 0.3
        assert f["affected_components"] == ["pkg:npm/foo@1.0"]
        assert f["blast_radius_path"] == ["foo", "bar"]
        assert f["blast_radius_computed_at"] == "2026-03-22T01:01:00Z"
        assert f["epss_velocity"] == 0.005
        assert f["epss_trend"] == "rising"
        assert f["epss_velocity_computed_at"] == "2026-03-22T01:02:00Z"


# ---------------------------------------------------------------------------
# AC-P6-002: Phase 2 fields are null when pipeline not run
# ---------------------------------------------------------------------------

class TestNullFields:
    def test_phase2_fields_null_when_not_enriched(self):
        from api.main import app
        from api.core.security import Customer
        from api.core.dependencies import get_current_customer as dep

        run_doc = _make_scan_run_doc(llm_token_usage=None)
        finding = _make_finding(
            "fp1",
            llm_risk_summary=None,
            llm_remediation=None,
            llm_attack_surface=None,
            llm_enriched_at=None,
            blast_radius_score=None,
            affected_components=None,
            blast_radius_path=None,
            blast_radius_computed_at=None,
            epss_velocity=None,
            epss_trend=None,
            epss_velocity_computed_at=None,
        )

        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.get.return_value = run_doc
        mock_db.collection.return_value = mock_collection

        def aql_side_effect(query, bind_vars=None, **kwargs):
            if "trend_groups" in query:
                return iter([{"trend_groups": [], "avg_blast_radius": None}])
            if "LIMIT 5" in query:
                return iter([])
            return iter([finding])

        mock_db.aql.execute.side_effect = aql_side_effect

        with patch("api.core.database.get_reference_db", return_value=mock_db):
            app.dependency_overrides[dep] = lambda: Customer(**{"_key": "t1", "name": "T", "database_name": "db_t1"})
            client = TestClient(app)
            resp = client.get("/v1/scan/run1/findings")
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        f = resp.json()["data"][0]
        assert f["llm_risk_summary"] is None
        assert f["blast_radius_score"] is None
        assert f["epss_velocity"] is None
        assert f["epss_trend"] is None


# ---------------------------------------------------------------------------
# AC-P6-003 + AC-P6-004: Pydantic Literal validation on response fields
# ---------------------------------------------------------------------------

class TestPydanticValidation:
    def test_llm_attack_surface_valid_values(self):
        from api.models.responses.scan import ScanFindingResponse
        for val in ("network", "local", "adjacent", None):
            f = ScanFindingResponse(
                finding_id="x", cve_id="CVE-1", severity="HIGH",
                description="d", location="l", tool_name="t", created_at="2026-01-01",
                llm_attack_surface=val,
            )
            assert f.llm_attack_surface == val

    def test_llm_attack_surface_invalid_raises(self):
        from api.models.responses.scan import ScanFindingResponse
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ScanFindingResponse(
                finding_id="x", cve_id="CVE-1", severity="HIGH",
                description="d", location="l", tool_name="t", created_at="2026-01-01",
                llm_attack_surface="physical",  # not in Literal
            )

    def test_epss_trend_valid_values(self):
        from api.models.responses.scan import ScanFindingResponse
        for val in ("rising", "stable", "falling", None):
            f = ScanFindingResponse(
                finding_id="x", cve_id="CVE-1", severity="HIGH",
                description="d", location="l", tool_name="t", created_at="2026-01-01",
                epss_trend=val,
            )
            assert f.epss_trend == val

    def test_epss_trend_invalid_raises(self):
        from api.models.responses.scan import ScanFindingResponse
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ScanFindingResponse(
                finding_id="x", cve_id="CVE-1", severity="HIGH",
                description="d", location="l", tool_name="t", created_at="2026-01-01",
                epss_trend="plateau",  # not in Literal
            )


# ---------------------------------------------------------------------------
# AC-P6-005 + AC-P6-006: scan_run includes llm_token_usage
# ---------------------------------------------------------------------------

class TestScanRunLLMTokenUsage:
    def _make_client(self, run_doc):
        from api.main import app
        from api.core.security import Customer
        from api.core.dependencies import get_current_customer as dep

        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.get.return_value = run_doc
        mock_db.collection.return_value = mock_collection

        def aql_side_effect(query, bind_vars=None, **kwargs):
            if "trend_groups" in query:
                return iter([{"trend_groups": [], "avg_blast_radius": None}])
            return iter([])

        mock_db.aql.execute.side_effect = aql_side_effect

        with patch("api.core.database.get_reference_db", return_value=mock_db):
            app.dependency_overrides[dep] = lambda: Customer(**{"_key": "t1", "name": "T", "database_name": "db_t1"})
            client = TestClient(app)
            resp = client.get("/v1/scan/run1")
            app.dependency_overrides.clear()
        return resp

    def test_llm_token_usage_returned_when_present(self):
        run_doc = _make_scan_run_doc()
        resp = self._make_client(run_doc)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["llm_token_usage"] is not None
        assert data["llm_token_usage"]["total_tokens"] == 4300
        assert data["llm_token_usage"]["model"] == "claude-haiku-4-5-20251001"

    def test_llm_token_usage_null_when_not_present(self):
        run_doc = _make_scan_run_doc(llm_token_usage=None)
        resp = self._make_client(run_doc)
        assert resp.status_code == 200
        assert resp.json()["data"]["llm_token_usage"] is None


# ---------------------------------------------------------------------------
# AC-P6-007: Phase 2 pipeline statuses accepted in status field
# ---------------------------------------------------------------------------

class TestPhase2StatusValues:
    @pytest.mark.parametrize("status", [
        "llm_enriched", "blast_radius_computed", "velocity_computed"
    ])
    def test_phase2_status_accepted(self, status):
        from api.models.responses.scan import ScanSessionResponse
        r = ScanSessionResponse(
            session_id="x", tool_name="t", tool_version="1", scan_type="sca",
            scan_timestamp="2026-01-01", status=status, findings_count=0,
            created_at="2026-01-01", updated_at="2026-01-01",
        )
        assert r.status == status


# ---------------------------------------------------------------------------
# AC-P6-008: filter ?epss_trend=rising
# ---------------------------------------------------------------------------

class TestFilterEpssTrend:
    def test_epss_trend_filter_passes_bind_var(self):
        from api.main import app
        from api.core.security import Customer
        from api.core.dependencies import get_current_customer as dep

        run_doc = _make_scan_run_doc()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.get.return_value = run_doc
        mock_db.collection.return_value = mock_collection

        captured_bind_vars = {}

        def aql_side_effect(query, bind_vars=None, **kwargs):
            if "epss_trend" in (bind_vars or {}):
                captured_bind_vars.update(bind_vars)
            if "trend_groups" in query:
                return iter([{"trend_groups": [], "avg_blast_radius": None}])
            return iter([_make_finding("fp1", epss_trend="rising")])

        mock_db.aql.execute.side_effect = aql_side_effect

        with patch("api.core.database.get_reference_db", return_value=mock_db):
            app.dependency_overrides[dep] = lambda: Customer(**{"_key": "t1", "name": "T", "database_name": "db_t1"})
            client = TestClient(app)
            resp = client.get("/v1/scan/run1/findings?epss_trend=rising")
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        assert captured_bind_vars.get("epss_trend") == "rising"


# ---------------------------------------------------------------------------
# AC-P6-009: ?epss_trend=invalid returns 422
# ---------------------------------------------------------------------------

    def test_invalid_epss_trend_returns_422(self):
        from api.main import app
        from api.core.security import Customer
        from api.core.dependencies import get_current_customer as dep

        mock_db = MagicMock()
        mock_db.collection.return_value.get.return_value = _make_scan_run_doc()
        mock_db.aql.execute.return_value = iter([])

        with patch("api.core.database.get_reference_db", return_value=mock_db):
            app.dependency_overrides[dep] = lambda: Customer(**{"_key": "t1", "name": "T", "database_name": "db_t1"})
            client = TestClient(app)
            resp = client.get("/v1/scan/run1/findings?epss_trend=plateau")
            app.dependency_overrides.clear()

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# AC-P6-010: ?min_blast_radius=0.5 filters
# ---------------------------------------------------------------------------

class TestFilterMinBlastRadius:
    def test_min_blast_radius_passes_bind_var(self):
        from api.main import app
        from api.core.security import Customer
        from api.core.dependencies import get_current_customer as dep

        run_doc = _make_scan_run_doc()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.get.return_value = run_doc
        mock_db.collection.return_value = mock_collection

        captured_bind_vars = {}

        def aql_side_effect(query, bind_vars=None, **kwargs):
            if "min_blast_radius" in (bind_vars or {}):
                captured_bind_vars.update(bind_vars)
            if "trend_groups" in query:
                return iter([{"trend_groups": [], "avg_blast_radius": None}])
            return iter([_make_finding("fp1", blast_radius_score=0.7)])

        mock_db.aql.execute.side_effect = aql_side_effect

        with patch("api.core.database.get_reference_db", return_value=mock_db):
            app.dependency_overrides[dep] = lambda: Customer(**{"_key": "t1", "name": "T", "database_name": "db_t1"})
            client = TestClient(app)
            resp = client.get("/v1/scan/run1/findings?min_blast_radius=0.5")
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        assert captured_bind_vars.get("min_blast_radius") == 0.5

    # AC-P6-011: ?min_blast_radius=1.5 returns 422
    def test_out_of_range_min_blast_radius_returns_422(self):
        from api.main import app
        from api.core.security import Customer
        from api.core.dependencies import get_current_customer as dep

        mock_db = MagicMock()
        mock_db.collection.return_value.get.return_value = _make_scan_run_doc()
        mock_db.aql.execute.return_value = iter([])

        with patch("api.core.database.get_reference_db", return_value=mock_db):
            app.dependency_overrides[dep] = lambda: Customer(**{"_key": "t1", "name": "T", "database_name": "db_t1"})
            client = TestClient(app)
            resp = client.get("/v1/scan/run1/findings?min_blast_radius=1.5")
            app.dependency_overrides.clear()

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# AC-P6-012 + AC-P6-013: sort_by params
# ---------------------------------------------------------------------------

class TestSortBy:
    def _run_sort_test(self, sort_param, expected_field):
        from api.main import app
        from api.core.security import Customer
        from api.core.dependencies import get_current_customer as dep

        run_doc = _make_scan_run_doc()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.get.return_value = run_doc
        mock_db.collection.return_value = mock_collection

        captured_queries = []

        def aql_side_effect(query, bind_vars=None, **kwargs):
            captured_queries.append(query)
            if "trend_groups" in query:
                return iter([{"trend_groups": [], "avg_blast_radius": None}])
            return iter([_make_finding("fp1")])

        mock_db.aql.execute.side_effect = aql_side_effect

        with patch("api.core.database.get_reference_db", return_value=mock_db):
            app.dependency_overrides[dep] = lambda: Customer(**{"_key": "t1", "name": "T", "database_name": "db_t1"})
            client = TestClient(app)
            resp = client.get(f"/v1/scan/run1/findings?sort_by={sort_param}")
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        # Find the findings query (not the summary query)
        findings_query = next(q for q in captured_queries if "LIMIT @offset" in q)
        assert expected_field in findings_query
        assert "DESC" in findings_query

    def test_sort_by_blast_radius_score(self):
        self._run_sort_test("blast_radius_score", "f.blast_radius_score")

    def test_sort_by_epss_velocity(self):
        self._run_sort_test("epss_velocity", "f.epss_velocity")

    # AC-P6-014: invalid sort_by returns 422
    def test_invalid_sort_by_returns_422(self):
        from api.main import app
        from api.core.security import Customer
        from api.core.dependencies import get_current_customer as dep

        mock_db = MagicMock()
        mock_db.collection.return_value.get.return_value = _make_scan_run_doc()
        mock_db.aql.execute.return_value = iter([])

        with patch("api.core.database.get_reference_db", return_value=mock_db):
            app.dependency_overrides[dep] = lambda: Customer(**{"_key": "t1", "name": "T", "database_name": "db_t1"})
            client = TestClient(app)
            resp = client.get("/v1/scan/run1/findings?sort_by=invalid_field")
            app.dependency_overrides.clear()

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# AC-P6-015 + AC-P6-016 + AC-P6-017: phase2_summary on scan_run
# ---------------------------------------------------------------------------

class TestPhase2Summary:
    def _get_scan_run(self, run_doc, summary_raw, top5_keys):
        from api.main import app
        from api.core.security import Customer
        from api.core.dependencies import get_current_customer as dep

        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.get.return_value = run_doc
        mock_db.collection.return_value = mock_collection

        def aql_side_effect(query, bind_vars=None, **kwargs):
            if "trend_groups" in query:
                return iter(summary_raw)
            if "LIMIT 5" in query:
                return iter(top5_keys)
            return iter([])

        mock_db.aql.execute.side_effect = aql_side_effect

        with patch("api.core.database.get_reference_db", return_value=mock_db):
            app.dependency_overrides[dep] = lambda: Customer(**{"_key": "t1", "name": "T", "database_name": "db_t1"})
            client = TestClient(app)
            resp = client.get("/v1/scan/run1")
            app.dependency_overrides.clear()

        return resp

    def test_phase2_summary_correct_counts_and_avg(self):
        summary_raw = [{
            "trend_groups": [
                {"trend": "rising", "count": 5},
                {"trend": "stable", "count": 30},
                {"trend": "falling", "count": 7},
            ],
            "avg_blast_radius": 0.23,
        }]
        top5 = ["fp1", "fp2", "fp3", "fp4", "fp5"]
        resp = self._get_scan_run(_make_scan_run_doc(), summary_raw, top5)

        assert resp.status_code == 200
        s = resp.json()["data"]["phase2_summary"]
        assert s["rising_count"] == 5
        assert s["stable_count"] == 30
        assert s["falling_count"] == 7
        assert s["avg_blast_radius"] == 0.23

    def test_top_blast_radius_findings_max_5(self):
        summary_raw = [{"trend_groups": [], "avg_blast_radius": 0.1}]
        top5 = ["fp1", "fp2", "fp3", "fp4", "fp5"]
        resp = self._get_scan_run(_make_scan_run_doc(), summary_raw, top5)

        s = resp.json()["data"]["phase2_summary"]
        assert len(s["top_blast_radius_findings"]) <= 5
        assert s["top_blast_radius_findings"] == top5

    def test_avg_blast_radius_null_when_no_findings(self):
        summary_raw = [{"trend_groups": [], "avg_blast_radius": None}]
        resp = self._get_scan_run(_make_scan_run_doc(), summary_raw, [])

        s = resp.json()["data"]["phase2_summary"]
        assert s["avg_blast_radius"] is None

    def test_phase2_summary_zeros_when_no_trend_data(self):
        summary_raw = [{"trend_groups": [], "avg_blast_radius": None}]
        resp = self._get_scan_run(_make_scan_run_doc(), summary_raw, [])

        s = resp.json()["data"]["phase2_summary"]
        assert s["rising_count"] == 0
        assert s["stable_count"] == 0
        assert s["falling_count"] == 0
