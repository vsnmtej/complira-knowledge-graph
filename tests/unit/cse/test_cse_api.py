"""
S-CSE-13 — CSE API endpoints.

AC-CSE-18: POST /v1/cse/simulations/create returns 200 + sim_id for valid tenant.
AC-CSE-19: POST /v1/cse/simulations/create returns 422 when attack surface is empty.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))


# ---------------------------------------------------------------------------
# FastAPI test client setup
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def app_client():
    """FastAPI TestClient with auth + db dependencies overridden."""
    try:
        from fastapi.testclient import TestClient
        from api.main import app
        from api.core.security import get_current_customer
    except Exception as e:
        pytest.skip(f"Cannot import app: {e}")

    # Mock customer
    mock_customer = MagicMock()
    mock_customer._key = "test_tenant_cse"

    # Mock db — default: no run found
    mock_db = MagicMock()
    mock_db.aql.execute = MagicMock(return_value=iter([]))

    # get_reference_db is called directly (not via Depends) in background tasks,
    # so we patch at the module level instead of using dependency_overrides.
    with patch("api.v1.endpoints.cse.get_reference_db", return_value=mock_db):
        # Override both the full auth dep and the optional wrapper used by status/stream/create
        from api.v1.endpoints.cse import _get_customer_optional
        app.dependency_overrides[get_current_customer]  = lambda: mock_customer
        app.dependency_overrides[_get_customer_optional] = lambda: mock_customer

        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, mock_db

        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# AC-CSE-18: POST create returns 200 + sim_id
# ---------------------------------------------------------------------------

class TestCreateEndpoint:
    def test_create_returns_200_with_sim_id(self, app_client) -> None:
        """AC-CSE-18: POST /v1/cse/simulations/create returns 200 + sim_id."""
        client, mock_db = app_client

        fake_sim_id = str(uuid.uuid4())
        mock_runner = MagicMock()
        mock_runner.sim_id = fake_sim_id
        mock_runner.tenant_id = "test_tenant_cse"

        with patch(
            "api.v1.endpoints.cse.CyberSimulationManager"
        ) as MockManager:
            instance = MockManager.return_value
            instance.prepare = AsyncMock(return_value=(fake_sim_id, mock_runner))
            instance.start = MagicMock()

            resp = client.post(
                "/v1/cse/simulations/create",
                json={"trigger_type": "kev_triggered"},
            )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "sim_id" in data
        assert data["sim_id"] == fake_sim_id
        assert data["status"] == "running"

    def test_create_returns_sim_id_monthly_posture(self, app_client) -> None:
        """POST with monthly_posture_sim trigger type also returns 200 + sim_id."""
        client, mock_db = app_client

        fake_sim_id = str(uuid.uuid4())
        mock_runner = MagicMock()
        mock_runner.sim_id = fake_sim_id

        with patch("api.v1.endpoints.cse.CyberSimulationManager") as MockManager:
            instance = MockManager.return_value
            instance.prepare = AsyncMock(return_value=(fake_sim_id, mock_runner))
            instance.start = MagicMock()

            resp = client.post(
                "/v1/cse/simulations/create",
                json={"trigger_type": "monthly_posture_sim"},
            )

        assert resp.status_code == 200
        assert resp.json()["sim_id"] == fake_sim_id


# ---------------------------------------------------------------------------
# AC-CSE-19: POST create returns 422 when attack surface is empty
# ---------------------------------------------------------------------------

    def test_create_returns_422_on_insufficient_attack_surface(self, app_client) -> None:
        """AC-CSE-19: prepare() raises ValueError → 422 insufficient_attack_surface."""
        client, mock_db = app_client

        with patch("api.v1.endpoints.cse.CyberSimulationManager") as MockManager:
            instance = MockManager.return_value
            instance.prepare = AsyncMock(side_effect=ValueError("insufficient_attack_surface"))

            resp = client.post(
                "/v1/cse/simulations/create",
                json={"trigger_type": "kev_triggered"},
            )

        assert resp.status_code == 422
        detail = resp.json().get("detail", "")
        assert "insufficient_attack_surface" in detail

    def test_create_invalid_trigger_type_returns_422(self, app_client) -> None:
        """POST with unknown trigger_type returns 422."""
        client, mock_db = app_client

        resp = client.post(
            "/v1/cse/simulations/create",
            json={"trigger_type": "invalid_type"},
        )
        assert resp.status_code == 422

    def test_create_uses_kev_triggered_default(self, app_client) -> None:
        """POST without trigger_type defaults to kev_triggered."""
        client, mock_db = app_client

        fake_sim_id = str(uuid.uuid4())
        mock_runner = MagicMock()
        mock_runner.sim_id = fake_sim_id

        captured_args = {}

        async def mock_prepare(db, tenant_id, trigger_type="kev_triggered", total_rounds=None):
            captured_args["trigger_type"] = trigger_type
            return fake_sim_id, mock_runner

        with patch("api.v1.endpoints.cse.CyberSimulationManager") as MockManager:
            instance = MockManager.return_value
            instance.prepare = mock_prepare
            instance.start = MagicMock()

            resp = client.post("/v1/cse/simulations/create", json={})

        assert resp.status_code == 200
        assert captured_args.get("trigger_type") == "kev_triggered"


# ---------------------------------------------------------------------------
# GET status endpoint
# ---------------------------------------------------------------------------

class TestStatusEndpoint:
    def test_status_returns_404_for_unknown_run(self, app_client) -> None:
        """GET /v1/cse/simulations/{sim_id}/status returns 404 for unknown run."""
        client, mock_db = app_client
        mock_db.aql.execute = MagicMock(return_value=iter([None]))

        resp = client.get("/v1/cse/simulations/nonexistent-sim-id/status")
        assert resp.status_code == 404

    def test_status_returns_200_for_known_run(self, app_client) -> None:
        """GET status returns 200 with run metadata for known run."""
        client, mock_db = app_client

        run_doc = {
            "_key": "sim-known",
            "sim_id": "sim-known",
            "tenant_id": "test_tenant_cse",
            "status": "running",
            "trigger_type": "kev_triggered",
            "started_at": "2026-04-14T10:00:00Z",
            "agent_count": 5,
            "chain_probability": None,
            "board_narrative": None,
            "top_3_actions": [],
        }

        # First call: _AQL_RUN_META returns run doc
        # Second call: _AQL_RECENT_EVENTS returns events
        call_count = [0]

        def mock_execute(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return iter([run_doc])
            return iter([])

        mock_db.aql.execute = MagicMock(side_effect=mock_execute)

        resp = client.get("/v1/cse/simulations/sim-known/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["sim_id"] == "sim-known"
        assert data["status"] == "running"


# ---------------------------------------------------------------------------
# AC-004 / AC-014: GET stream endpoint emits SSE events (T-12)
# ---------------------------------------------------------------------------

class TestStreamEndpoint:
    def test_stream_falls_back_to_arango_for_completed_run(self, app_client) -> None:
        """AC-004: GET /stream for a completed run streams events from ArangoDB."""
        client, mock_db = app_client

        stored_events = [
            {
                "round_no": 1,
                "agent_type": "Attacker",
                "action_type": "EXPLOIT_CVE",
                "outcome": "success",
                "significance": 0.9,
                "timestamp": "2026-04-14T10:01:00Z",
            }
        ]

        mock_db.aql.execute = MagicMock(return_value=iter(stored_events))

        # sim_id not in _SIM_REGISTRY → falls back to ArangoDB stream
        resp = client.get("/v1/cse/simulations/completed-sim/stream")
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        body = resp.text
        # At least one data: line and a done event
        assert "data:" in body
        assert "event: done" in body

    def test_stream_contains_action_payload(self, app_client) -> None:
        """AC-004: Streamed event payload includes round_no, agent_type, action_type."""
        client, mock_db = app_client

        event = {
            "round_no": 2,
            "agent_type": "Regulator",
            "action_type": "ISSUE_COMPLIANCE_FINDING",
            "outcome": "gap_recorded: CRA CRA_art_24",
            "significance": 0.8,
            "timestamp": "2026-04-14T10:02:00Z",
        }
        mock_db.aql.execute = MagicMock(return_value=iter([event]))

        resp = client.get("/v1/cse/simulations/reg-sim/stream")
        assert resp.status_code == 200
        body = resp.text
        assert "ISSUE_COMPLIANCE_FINDING" in body
        assert "Regulator" in body

    def test_stream_returns_404_when_no_events_in_arango(self, app_client) -> None:
        """AC-004: GET /stream returns 404 when run has no stored events."""
        client, mock_db = app_client

        mock_db.aql.execute = MagicMock(return_value=iter([]))

        resp = client.get("/v1/cse/simulations/missing-sim/stream")
        assert resp.status_code == 404
