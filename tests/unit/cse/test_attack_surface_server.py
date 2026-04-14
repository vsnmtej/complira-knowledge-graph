"""
S-CSE-08 — Attack surface state machine.

AC-CSE-11: Patching a CVE removes it from the exploitable list.
AC-CSE-12: EXPLOIT_CVE action sets a chain step in AttackSurfaceServer state.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from complira_graph.cse.attack_surface_server import (
    AttackSurfaceServer,
    EXPLOIT_CVE,
    PATCH,
    SCAN_SURFACE,
    LATERAL_MOVE,
    ESCALATE_PRIVILEGES,
    PIVOT_TARGET,
    MONITOR,
    DETECT,
    INVESTIGATE,
    ESCALATE_TO_CISO,
    DEPLOY_CONTROL,
    ROTATE_CREDENTIAL,
    FILE_CRA_NOTIFICATION,
    NOTIFY_BOARD,
    ACKNOWLEDGE,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_entities(cve_ids: list[str]) -> list[dict]:
    return [
        {
            "entity_id": cve_id,
            "entity_type": "cve",
            "severity": 8.5,
            "is_kev": True,
            "regulatory_refs": ["FDA_524B"],
            "component_name": f"comp_{i}",
        }
        for i, cve_id in enumerate(cve_ids)
    ]


# ---------------------------------------------------------------------------
# S-CSE-08 / AC-CSE-12: EXPLOIT_CVE sets chain step
# ---------------------------------------------------------------------------

class TestExploitCVE:
    def test_exploit_cve_adds_chain_step(self):
        """AC-CSE-12: EXPLOIT_CVE sets chain step count in state."""
        entities = _make_entities(["CVE-2021-44228", "CVE-2022-0001"])
        server = AttackSurfaceServer(entities)

        initial_state = server.get_state_snapshot()
        assert initial_state["chain_step_count"] == 0

        result = server.apply_action(EXPLOIT_CVE, {"cve_id": "CVE-2021-44228"}, round_no=1)

        state_after = server.get_state_snapshot()
        assert state_after["chain_step_count"] >= 1, "EXPLOIT_CVE must increment chain step count"
        assert result.outcome  # outcome string is non-empty

    def test_exploit_cve_unknown_cve_graceful(self):
        """EXPLOIT_CVE on unknown CVE returns outcome without crashing."""
        server = AttackSurfaceServer(_make_entities(["CVE-2021-44228"]))
        result = server.apply_action(EXPLOIT_CVE, {"cve_id": "CVE-9999-9999"}, round_no=1)
        assert result.outcome  # must return something without raising

    def test_exploit_cve_changes_exploitable_list(self):
        """After EXPLOIT_CVE, the CVE may still appear in exploitable list (not patched yet)."""
        entities = _make_entities(["CVE-2021-44228"])
        server = AttackSurfaceServer(entities)
        exploitable_before = server.get_exploitable_cves()
        assert "CVE-2021-44228" in exploitable_before

        server.apply_action(EXPLOIT_CVE, {"cve_id": "CVE-2021-44228"}, round_no=1)
        # CVE remains exploitable until patched
        exploitable_after = server.get_exploitable_cves()
        assert "CVE-2021-44228" in exploitable_after


# ---------------------------------------------------------------------------
# S-CSE-08 / AC-CSE-11: PATCH removes CVE from exploitable list
# ---------------------------------------------------------------------------

class TestPatch:
    def test_patch_removes_cve_from_exploitable(self):
        """AC-CSE-11: PATCH action removes CVE from exploitable list."""
        entities = _make_entities(["CVE-2021-44228", "CVE-2022-0001"])
        server = AttackSurfaceServer(entities)

        assert "CVE-2021-44228" in server.get_exploitable_cves()

        result = server.apply_action(PATCH, {"cve_id": "CVE-2021-44228"}, round_no=2)

        exploitable_after = server.get_exploitable_cves()
        assert "CVE-2021-44228" not in exploitable_after, "PATCH must remove CVE from exploitable list"
        assert result.outcome

    def test_patch_unknown_cve_does_not_crash(self):
        """PATCH on non-existent CVE completes without exception."""
        server = AttackSurfaceServer(_make_entities(["CVE-2021-44228"]))
        result = server.apply_action(PATCH, {"cve_id": "CVE-9999-9999"}, round_no=2)
        assert result.outcome

    def test_patch_all_cves_results_in_empty_exploitable(self):
        """Patching all CVEs empties exploitable list."""
        cve_ids = ["CVE-2021-44228", "CVE-2022-0001", "CVE-2023-0002"]
        server = AttackSurfaceServer(_make_entities(cve_ids))

        for cve_id in cve_ids:
            server.apply_action(PATCH, {"cve_id": cve_id}, round_no=1)

        assert server.get_exploitable_cves() == []


# ---------------------------------------------------------------------------
# All 15 actions smoke-test (no crash)
# ---------------------------------------------------------------------------

ALL_ACTIONS = [
    (SCAN_SURFACE,          {}),
    (EXPLOIT_CVE,           {"cve_id": "CVE-2021-44228"}),
    (LATERAL_MOVE,          {}),
    (ESCALATE_PRIVILEGES,   {}),
    (PIVOT_TARGET,          {}),
    (MONITOR,               {}),
    (DETECT,                {"cve_id": "CVE-2021-44228"}),
    (INVESTIGATE,           {"cve_id": "CVE-2021-44228"}),
    (ESCALATE_TO_CISO,      {}),
    (PATCH,                 {"cve_id": "CVE-2021-44228"}),
    (DEPLOY_CONTROL,        {"control_id": "ctrl_1"}),
    (ROTATE_CREDENTIAL,     {}),
    (FILE_CRA_NOTIFICATION, {}),
    (NOTIFY_BOARD,          {}),
    (ACKNOWLEDGE,           {"cve_id": "CVE-2021-44228"}),
]


@pytest.mark.parametrize("action_type,payload", ALL_ACTIONS)
def test_all_actions_return_result(action_type: str, payload: dict) -> None:
    """All 15 action types must return an ActionResult without raising."""
    entities = _make_entities(["CVE-2021-44228", "CVE-2022-0001"])
    server = AttackSurfaceServer(entities)
    result = server.apply_action(action_type, payload, round_no=1)
    assert result.outcome, f"{action_type} returned empty outcome"


class TestStateSnapshot:
    def test_initial_state_defaults(self):
        """Initial state has correct zero values."""
        server = AttackSurfaceServer(_make_entities(["CVE-2021-44228"]))
        state = server.get_state_snapshot()
        assert state["chain_step_count"] == 0
        assert state["ciso_alerted"] is False
        assert state["cra_notified"] is False
        assert isinstance(state["controls_deployed"], list)

    def test_escalate_to_ciso_sets_flag(self):
        server = AttackSurfaceServer(_make_entities(["CVE-2021-44228"]))
        server.apply_action(ESCALATE_TO_CISO, {}, round_no=1)
        assert server.get_state_snapshot()["ciso_alerted"] is True

    def test_file_cra_notification_sets_flag(self):
        server = AttackSurfaceServer(_make_entities(["CVE-2021-44228"]))
        server.apply_action(FILE_CRA_NOTIFICATION, {}, round_no=1)
        assert server.get_state_snapshot()["cra_notified"] is True
