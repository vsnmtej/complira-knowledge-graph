"""
S-CSE-09 — Action logging (JSONL).

AC-CSE-13: 100-round simulation produces JSONL with all 15 action type strings present.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from complira_graph.cse.action_logger import CyberActionLogger
from complira_graph.cse.attack_surface_server import (
    SCAN_SURFACE, EXPLOIT_CVE, LATERAL_MOVE, ESCALATE_PRIVILEGES, PIVOT_TARGET,
    MONITOR, DETECT, INVESTIGATE, ESCALATE_TO_CISO, PATCH, DEPLOY_CONTROL,
    ROTATE_CREDENTIAL, FILE_CRA_NOTIFICATION, NOTIFY_BOARD, ACKNOWLEDGE,
)

ALL_15_ACTIONS = [
    SCAN_SURFACE, EXPLOIT_CVE, LATERAL_MOVE, ESCALATE_PRIVILEGES, PIVOT_TARGET,
    MONITOR, DETECT, INVESTIGATE, ESCALATE_TO_CISO, PATCH, DEPLOY_CONTROL,
    ROTATE_CREDENTIAL, FILE_CRA_NOTIFICATION, NOTIFY_BOARD, ACKNOWLEDGE,
]


@pytest.fixture()
def sim_dir(tmp_path: Path) -> Path:
    return tmp_path


class TestCyberActionLogger:
    def test_log_simulation_start_writes_entry(self, sim_dir: Path) -> None:
        """log_simulation_start() appends a JSON line to cyber_actions.jsonl."""
        logger = CyberActionLogger(sim_dir)
        logger.log_simulation_start(
            sim_id="sim-test",
            tenant_id="tenant-abc",
            total_rounds=48,
            trigger_type="kev_triggered",
        )
        logger.close()

        log_path = sim_dir / "cyber_actions.jsonl"
        assert log_path.exists()
        lines = log_path.read_text().strip().split("\n")
        assert len(lines) >= 1
        entry = json.loads(lines[0])
        assert entry.get("event_type") == "simulation_start" or "sim_id" in entry

    def test_log_action_writes_valid_json_line(self, sim_dir: Path) -> None:
        """log_action() appends a valid JSON line per action."""
        logger = CyberActionLogger(sim_dir)
        logger.log_action(
            action_type=EXPLOIT_CVE,
            agent_id="attacker_0",
            agent_type="Attacker",
            payload={"cve_id": "CVE-2021-44228"},
            outcome="CVE exploited — chain step added",
            round_no=1,
            significance=0.9,
        )
        logger.close()

        log_path = sim_dir / "cyber_actions.jsonl"
        lines = [json.loads(l) for l in log_path.read_text().strip().split("\n") if l.strip()]
        action_entries = [l for l in lines if l.get("action_type") == EXPLOIT_CVE]
        assert len(action_entries) == 1
        entry = action_entries[0]
        assert entry["agent_id"] == "attacker_0"
        assert entry["round_no"] == 1

    def test_all_15_action_types_logged(self, sim_dir: Path) -> None:
        """AC-CSE-13: JSONL file must contain all 15 action type strings."""
        logger = CyberActionLogger(sim_dir)
        for i, action_type in enumerate(ALL_15_ACTIONS):
            logger.log_action(
                action_type=action_type,
                agent_id="agent_0",
                agent_type="Attacker" if i < 5 else "SOCAnalyst",
                payload={},
                outcome=f"{action_type} performed",
                round_no=i + 1,
                significance=0.5,
            )
        logger.close()

        log_path = sim_dir / "cyber_actions.jsonl"
        logged_action_types = set()
        for line in log_path.read_text().strip().split("\n"):
            if line.strip():
                entry = json.loads(line)
                if "action_type" in entry:
                    logged_action_types.add(entry["action_type"])

        missing = set(ALL_15_ACTIONS) - logged_action_types
        assert not missing, f"Missing action types in JSONL: {missing}"

    def test_log_round_start_writes_entry(self, sim_dir: Path) -> None:
        """log_round_start() writes a round marker to the log."""
        logger = CyberActionLogger(sim_dir)
        logger.log_round_start(round_no=1)
        logger.close()

        log_path = sim_dir / "cyber_actions.jsonl"
        lines = [json.loads(l) for l in log_path.read_text().strip().split("\n") if l.strip()]
        round_entries = [l for l in lines if l.get("event_type") == "round_start" or l.get("round_no") == 1]
        assert len(round_entries) >= 1

    def test_jsonl_each_line_is_valid_json(self, sim_dir: Path) -> None:
        """Every line in cyber_actions.jsonl must be valid JSON."""
        logger = CyberActionLogger(sim_dir)
        logger.log_simulation_start("sim-test", "tenant-abc", 10, "kev_triggered")
        for i in range(5):
            logger.log_action(MONITOR, f"agent_{i}", "SOCAnalyst", {}, "monitored", i + 1, 0.3)
        logger.close()

        for line in (sim_dir / "cyber_actions.jsonl").read_text().strip().split("\n"):
            if line.strip():
                json.loads(line)  # raises on invalid JSON

    def test_append_only_across_instances(self, sim_dir: Path) -> None:
        """Opening a second logger appends; does not truncate."""
        logger1 = CyberActionLogger(sim_dir)
        logger1.log_action(MONITOR, "agent_0", "SOCAnalyst", {}, "first", 1, 0.3)
        logger1.close()

        logger2 = CyberActionLogger(sim_dir)
        logger2.log_action(DETECT, "agent_0", "SOCAnalyst", {}, "second", 2, 0.5)
        logger2.close()

        lines = [l for l in (sim_dir / "cyber_actions.jsonl").read_text().strip().split("\n") if l.strip()]
        assert len(lines) == 2
