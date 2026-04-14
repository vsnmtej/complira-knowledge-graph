"""
complira_graph.cse.runner
===========================
CyberSimulationRunner — lifecycle state machine for a CSE simulation run.

Owns:
  - State transitions (IDLE → STARTING → RUNNING → ... → COMPLETED/FAILED)
  - run_state.json writes on every transition
  - subprocess.Popen launch via sys.executable -m
  - Background monitor thread that detects subprocess exit

Does NOT own: simulation logic, IPC commands (delegates to CyberIPCClient),
report generation, write-back.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from complira_graph.cse.ipc import CyberIPCClient

log = logging.getLogger(__name__)


class CyberRunnerStatus(str, Enum):
    IDLE       = "idle"
    STARTING   = "starting"
    RUNNING    = "running"
    PAUSED     = "paused"
    STOPPING   = "stopping"
    STOPPED    = "stopped"
    COMPLETED  = "completed"
    FAILED     = "failed"


TERMINAL_STATUSES = frozenset({
    CyberRunnerStatus.STOPPED,
    CyberRunnerStatus.COMPLETED,
    CyberRunnerStatus.FAILED,
})


class CyberSimulationRunner:
    """Manages lifecycle of a single CSE simulation subprocess."""

    def __init__(self, sim_id: str, tenant_id: str, sim_dir: str | Path) -> None:
        self.sim_id    = sim_id
        self.tenant_id = tenant_id
        self.sim_dir   = Path(sim_dir)
        self._status   = CyberRunnerStatus.IDLE
        self._proc: subprocess.Popen | None = None
        self._monitor_thread: threading.Thread | None = None
        self._ipc = CyberIPCClient(sim_dir)
        self._started_at: str | None = None
        self._completed_at: str | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def status(self) -> CyberRunnerStatus:
        return self._status

    def start_simulation(self) -> None:
        """Transition IDLE → STARTING → RUNNING and spawn subprocess."""
        self._transition(CyberRunnerStatus.STARTING)
        config_path = self.sim_dir / "simulation_config.json"
        cmd = [
            sys.executable, "-m", "complira_graph.cse.run_parallel_cyber_simulation",
            "--sim-dir", str(self.sim_dir),
            "--config", str(config_path),
        ]
        log.info("cse_runner_launching", sim_id=self.sim_id, cmd=" ".join(cmd))
        self._proc = subprocess.Popen(cmd, cwd=_project_root())
        self._transition(CyberRunnerStatus.RUNNING)
        self._monitor_thread = threading.Thread(target=self._monitor_subprocess, daemon=True)
        self._monitor_thread.start()

    def stop_simulation(self) -> None:
        """Send CLOSE_ENV IPC → transition STOPPING → STOPPED."""
        if self._status not in (CyberRunnerStatus.RUNNING, CyberRunnerStatus.PAUSED):
            return
        self._transition(CyberRunnerStatus.STOPPING)
        try:
            self._ipc.send_command("CLOSE_ENV", {})
        except Exception as exc:
            log.warning("cse_runner_stop_ipc_error", sim_id=self.sim_id, error=str(exc))
        if self._proc:
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._transition(CyberRunnerStatus.STOPPED)

    def pause_simulation(self) -> None:
        if self._status != CyberRunnerStatus.RUNNING:
            return
        try:
            self._ipc.send_command("PAUSE_AND_SNAPSHOT", {})
        except Exception as exc:
            log.warning("cse_runner_pause_ipc_error", sim_id=self.sim_id, error=str(exc))
        self._transition(CyberRunnerStatus.PAUSED)

    def resume_simulation(self) -> None:
        if self._status != CyberRunnerStatus.PAUSED:
            return
        try:
            self._ipc.send_command("INJECT_VARIABLE", {"resume": True})
        except Exception as exc:
            log.warning("cse_runner_resume_ipc_error", sim_id=self.sim_id, error=str(exc))
        self._transition(CyberRunnerStatus.RUNNING)

    def send_close_env(self) -> None:
        """Send CLOSE_ENV to terminate debrief loop after report agent finishes."""
        try:
            self._ipc.send_command("CLOSE_ENV", {})
        except Exception as exc:
            log.warning("cse_runner_close_env_error", sim_id=self.sim_id, error=str(exc))

    def get_state(self) -> dict[str, Any]:
        return _read_run_state(self.sim_dir) or {
            "sim_id": self.sim_id,
            "tenant_id": self.tenant_id,
            "status": self._status.value,
            "started_at": self._started_at,
            "updated_at": _now(),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _transition(self, new_status: CyberRunnerStatus) -> None:
        old = self._status
        self._status = new_status
        if new_status == CyberRunnerStatus.RUNNING and self._started_at is None:
            self._started_at = _now()
        if new_status in TERMINAL_STATUSES:
            self._completed_at = _now()
        log.info("cse_runner_transition", sim_id=self.sim_id, from_status=old.value, to_status=new_status.value)
        self._write_run_state()

    def _write_run_state(self) -> None:
        state: dict[str, Any] = {
            "sim_id":    self.sim_id,
            "tenant_id": self.tenant_id,
            "status":    self._status.value,
            "started_at":    self._started_at,
            "completed_at":  self._completed_at,
            "updated_at":    _now(),
        }
        try:
            (self.sim_dir / "run_state.json").write_text(
                json.dumps(state, indent=2), encoding="utf-8"
            )
        except Exception as exc:
            log.error("cse_runner_write_state_error", sim_id=self.sim_id, error=str(exc))

    def _monitor_subprocess(self) -> None:
        """Background thread: wait for subprocess exit and update status."""
        if self._proc is None:
            return
        exit_code = self._proc.wait()
        if self._status in TERMINAL_STATUSES:
            return  # already set by stop_simulation() or subprocess itself
        if exit_code == 0:
            # Subprocess wrote completed status itself; sync runner state
            self._status = CyberRunnerStatus.COMPLETED
            self._completed_at = _now()
            log.info("cse_runner_subprocess_completed", sim_id=self.sim_id)
        else:
            self._transition(CyberRunnerStatus.FAILED)
            log.error("cse_runner_subprocess_failed", sim_id=self.sim_id, exit_code=exit_code)


def _read_run_state(sim_dir: Path) -> dict[str, Any] | None:
    state_path = sim_dir / "run_state.json"
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project_root() -> Path:
    """Return project root (parent of src/)."""
    return Path(__file__).parent.parent.parent.parent
