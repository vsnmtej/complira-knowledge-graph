"""
S-CSE-01 — Runner lifecycle.
S-CSE-15 — Tenant isolation (path construction).

AC-CSE-01: start_simulation() → RUNNING; run_state.json shows status: running.
AC-CSE-02: stop_simulation() sends CLOSE_ENV IPC, transitions to STOPPED.
AC-CSE-21: Two concurrent tenant runs use distinct sim_dir paths.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from complira_graph.cse.runner import CyberRunnerStatus, CyberSimulationRunner


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sim_dir(tmp_path: Path) -> Path:
    sim_dir = tmp_path / "sim"
    (sim_dir / "ipc_commands").mkdir(parents=True)
    (sim_dir / "ipc_responses").mkdir(parents=True)
    return sim_dir


def _make_runner(sim_dir: Path, tenant_id: str = "tenant_abc") -> CyberSimulationRunner:
    return CyberSimulationRunner(
        sim_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        sim_dir=sim_dir,
    )


# ---------------------------------------------------------------------------
# S-CSE-01 / AC-CSE-01: start_simulation() → RUNNING
# ---------------------------------------------------------------------------

class TestStartSimulation:
    def test_initial_status_is_idle(self, sim_dir: Path) -> None:
        runner = _make_runner(sim_dir)
        assert runner.status == CyberRunnerStatus.IDLE

    def test_start_transitions_to_running(self, sim_dir: Path) -> None:
        """AC-CSE-01: start_simulation() must reach RUNNING state."""
        runner = _make_runner(sim_dir)
        runner._monitor_subprocess = lambda: None  # prevent race to COMPLETED

        mock_proc = MagicMock()
        mock_proc.wait = MagicMock(return_value=0)

        with patch("complira_graph.cse.runner.subprocess.Popen", return_value=mock_proc) as mock_popen:
            runner.start_simulation()

        assert runner.status == CyberRunnerStatus.RUNNING
        mock_popen.assert_called_once()

    def test_run_state_json_written_on_transition(self, sim_dir: Path) -> None:
        """AC-CSE-01: run_state.json written with status=running after start."""
        runner = _make_runner(sim_dir)
        runner._monitor_subprocess = lambda: None

        mock_proc = MagicMock()
        mock_proc.wait = MagicMock(return_value=0)

        with patch("complira_graph.cse.runner.subprocess.Popen", return_value=mock_proc):
            runner.start_simulation()

        state_path = sim_dir / "run_state.json"
        assert state_path.exists(), "run_state.json must be written on transition"
        state = json.loads(state_path.read_text())
        assert state["status"] == "running"
        assert state["sim_id"] == runner.sim_id

    def test_started_at_set_on_running(self, sim_dir: Path) -> None:
        runner = _make_runner(sim_dir)
        runner._monitor_subprocess = lambda: None

        mock_proc = MagicMock()
        mock_proc.wait = MagicMock(return_value=0)

        with patch("complira_graph.cse.runner.subprocess.Popen", return_value=mock_proc):
            runner.start_simulation()

        assert runner._started_at is not None

    def test_subprocess_launched_with_correct_args(self, sim_dir: Path) -> None:
        runner = _make_runner(sim_dir)
        runner._monitor_subprocess = lambda: None

        mock_proc = MagicMock()
        mock_proc.wait = MagicMock(return_value=0)

        with patch("complira_graph.cse.runner.subprocess.Popen", return_value=mock_proc) as mock_popen:
            runner.start_simulation()

        cmd = mock_popen.call_args[0][0]
        assert "-m" in cmd
        assert "complira_graph.cse.run_parallel_cyber_simulation" in cmd
        assert "--sim-dir" in cmd
        assert "--config" in cmd


# ---------------------------------------------------------------------------
# S-CSE-01 / AC-CSE-02: stop_simulation() → STOPPED
# ---------------------------------------------------------------------------

class TestStopSimulation:
    def test_stop_transitions_to_stopped(self, sim_dir: Path) -> None:
        """AC-CSE-02: stop_simulation() must transition to STOPPED."""
        runner = _make_runner(sim_dir)
        runner._monitor_subprocess = lambda: None
        runner._ipc = MagicMock()  # avoid real IPC timeout

        mock_proc = MagicMock()
        mock_proc.wait = MagicMock(return_value=0)

        with patch("complira_graph.cse.runner.subprocess.Popen", return_value=mock_proc):
            runner.start_simulation()

        runner.stop_simulation()

        assert runner.status == CyberRunnerStatus.STOPPED

    def test_stop_not_running_is_noop(self, sim_dir: Path) -> None:
        """stop_simulation() on IDLE runner does nothing."""
        runner = _make_runner(sim_dir)
        runner.stop_simulation()  # must not raise
        assert runner.status == CyberRunnerStatus.IDLE

    def test_run_state_json_updated_to_stopped(self, sim_dir: Path) -> None:
        runner = _make_runner(sim_dir)
        runner._monitor_subprocess = lambda: None
        runner._ipc = MagicMock()

        mock_proc = MagicMock()
        mock_proc.wait = MagicMock(return_value=0)

        with patch("complira_graph.cse.runner.subprocess.Popen", return_value=mock_proc):
            runner.start_simulation()

        runner.stop_simulation()

        state = json.loads((sim_dir / "run_state.json").read_text())
        assert state["status"] == "stopped"


# ---------------------------------------------------------------------------
# Pause / Resume
# ---------------------------------------------------------------------------

class TestPauseResume:
    def test_pause_sets_paused_status(self, sim_dir: Path) -> None:
        runner = _make_runner(sim_dir)
        runner._monitor_subprocess = lambda: None
        runner._ipc = MagicMock()  # avoid real IPC timeout

        mock_proc = MagicMock()
        mock_proc.wait = MagicMock(return_value=0)

        with patch("complira_graph.cse.runner.subprocess.Popen", return_value=mock_proc):
            runner.start_simulation()

        runner.pause_simulation()
        assert runner.status == CyberRunnerStatus.PAUSED

    def test_resume_sets_running_status(self, sim_dir: Path) -> None:
        runner = _make_runner(sim_dir)
        runner._monitor_subprocess = lambda: None
        runner._ipc = MagicMock()

        mock_proc = MagicMock()
        mock_proc.wait = MagicMock(return_value=0)

        with patch("complira_graph.cse.runner.subprocess.Popen", return_value=mock_proc):
            runner.start_simulation()

        runner.pause_simulation()
        runner.resume_simulation()
        assert runner.status == CyberRunnerStatus.RUNNING


# ---------------------------------------------------------------------------
# S-CSE-15 / AC-CSE-21: Tenant isolation — distinct sim_dir paths
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    def test_two_tenants_use_separate_dirs(self, tmp_path: Path) -> None:
        """AC-CSE-21: Two runs must produce distinct sim_dir paths."""
        sim_dir_a = tmp_path / "tenant_a" / "sim_a"
        sim_dir_b = tmp_path / "tenant_b" / "sim_b"

        for d in (sim_dir_a, sim_dir_b):
            (d / "ipc_commands").mkdir(parents=True)
            (d / "ipc_responses").mkdir(parents=True)

        runner_a = CyberSimulationRunner("sim_a", "tenant_a", sim_dir_a)
        runner_b = CyberSimulationRunner("sim_b", "tenant_b", sim_dir_b)

        assert runner_a.sim_dir != runner_b.sim_dir
        assert "tenant_a" in str(runner_a.sim_dir)
        assert "tenant_b" in str(runner_b.sim_dir)

    def test_run_state_written_to_correct_dir(self, tmp_path: Path) -> None:
        """run_state.json is written only to the runner's own sim_dir."""
        sim_dir_a = tmp_path / "tenant_a" / "sim_a"
        sim_dir_b = tmp_path / "tenant_b" / "sim_b"
        for d in (sim_dir_a, sim_dir_b):
            (d / "ipc_commands").mkdir(parents=True)
            (d / "ipc_responses").mkdir(parents=True)

        runner_a = CyberSimulationRunner("sim_a", "tenant_a", sim_dir_a)
        runner_b = CyberSimulationRunner("sim_b", "tenant_b", sim_dir_b)

        # Manually trigger a transition on runner_a
        runner_a._transition(CyberRunnerStatus.STARTING)

        assert (sim_dir_a / "run_state.json").exists()
        assert not (sim_dir_b / "run_state.json").exists()
