"""
S-CSE-02 — IPC dispatch.

AC-CSE-03: INJECT_VARIABLE dispatched and response written within 5s.
AC-CSE-04: Unknown command returns error dict; simulation does not crash.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from unittest.mock import patch

from complira_graph.cse.ipc import (
    CyberIPCClient,
    CyberIPCHandler,
    IPCTimeoutError,
    CMD_INJECT_VARIABLE,
    CMD_CLOSE_ENV,
    CMD_PAUSE_AND_SNAPSHOT,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sim_dir(tmp_path: Path) -> Path:
    (tmp_path / "ipc_commands").mkdir()
    (tmp_path / "ipc_responses").mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# CyberIPCHandler dispatch tests
# ---------------------------------------------------------------------------

class TestIPCHandler:
    def test_close_env_sets_stop_flag(self, sim_dir: Path) -> None:
        """CLOSE_ENV must set stop_requested=True."""
        handler = CyberIPCHandler(sim_dir)
        assert not handler.stop_requested

        result = handler._dispatch(CMD_CLOSE_ENV, {})

        assert handler.stop_requested is True
        assert result.get("status") == "stopping"

    def test_pause_and_snapshot_sets_pause_flag(self, sim_dir: Path) -> None:
        handler = CyberIPCHandler(sim_dir)
        assert not handler.pause_requested

        result = handler._dispatch(CMD_PAUSE_AND_SNAPSHOT, {})

        assert handler.pause_requested is True
        assert result.get("status") == "paused"

    def test_inject_variable_resume_clears_pause(self, sim_dir: Path) -> None:
        handler = CyberIPCHandler(sim_dir)
        handler._dispatch(CMD_PAUSE_AND_SNAPSHOT, {})  # pause first
        assert handler.pause_requested

        result = handler._dispatch(CMD_INJECT_VARIABLE, {"resume": True})

        assert not handler.pause_requested
        assert result.get("status") == "resumed"

    @patch("complira_graph.cse.ipc.log")
    def test_unknown_command_returns_error_dict(self, _mock_log, sim_dir: Path) -> None:
        """AC-CSE-04: Unknown command returns error dict; no exception raised."""
        handler = CyberIPCHandler(sim_dir)
        result = handler._dispatch("NONEXISTENT_COMMAND", {})

        assert "error" in result
        assert result["error"] == "unknown_command"
        assert not handler.stop_requested  # simulation continues

    @patch("complira_graph.cse.ipc.log")
    def test_unknown_command_does_not_crash_process_pending(self, _mock_log, sim_dir: Path) -> None:
        """AC-CSE-04: _process_pending with unknown command does not raise."""
        # Write an unknown command file
        cmd_file = sim_dir / "ipc_commands" / "test_cmd.json"
        cmd_file.write_text(
            json.dumps({"command": "UNKNOWN_CMD", "payload": {}, "cmd_id": "test_cmd", "sent_at": "2026-01-01T00:00:00Z"}),
            encoding="utf-8",
        )

        handler = CyberIPCHandler(sim_dir)
        handler._process_pending()  # must not raise

        # Response file written
        resp = sim_dir / "ipc_responses" / "test_cmd.json"
        assert resp.exists()
        data = json.loads(resp.read_text())
        assert "error" in data["result"]

    def test_inject_variable_registered_handler(self, sim_dir: Path) -> None:
        """INJECT_VARIABLE forwards to registered handler when payload is not resume."""
        called_with = {}

        def custom_handler(payload: dict) -> dict:
            called_with.update(payload)
            return {"handled": True}

        handler = CyberIPCHandler(sim_dir)
        handler.register(CMD_INJECT_VARIABLE, custom_handler)

        result = handler._dispatch(CMD_INJECT_VARIABLE, {"some_var": 42})

        assert called_with == {"some_var": 42}
        assert result.get("handled") is True


# ---------------------------------------------------------------------------
# AC-CSE-03: CyberIPCClient — send_command receives response within 5s
# ---------------------------------------------------------------------------

class TestIPCClient:
    def test_send_command_receives_response(self, sim_dir: Path) -> None:
        """AC-CSE-03: INJECT_VARIABLE sent → response received in < 5s."""
        handler = CyberIPCHandler(sim_dir)

        # Background thread simulates subprocess responding to commands
        def subprocess_simulator():
            deadline = time.monotonic() + 4.0
            while time.monotonic() < deadline:
                handler._process_pending()
                time.sleep(0.05)

        t = threading.Thread(target=subprocess_simulator, daemon=True)
        t.start()

        client = CyberIPCClient(sim_dir)
        start = time.monotonic()
        result = client.send_command(CMD_INJECT_VARIABLE, {"key": "val"})
        elapsed = time.monotonic() - start

        assert elapsed < 5.0, f"IPC round-trip took {elapsed:.2f}s, must be < 5s"
        assert result  # non-empty response dict

    def test_send_command_timeout_raises(self, sim_dir: Path) -> None:
        """IPCTimeoutError raised when no subprocess responds."""
        client = CyberIPCClient(sim_dir)
        # Monkeypatch timeout to 0.3s for test speed
        import complira_graph.cse.ipc as ipc_module
        original = ipc_module.IPC_RESPONSE_TIMEOUT_S
        ipc_module.IPC_RESPONSE_TIMEOUT_S = 0.3
        try:
            with pytest.raises(IPCTimeoutError):
                client.send_command(CMD_INJECT_VARIABLE, {})
        finally:
            ipc_module.IPC_RESPONSE_TIMEOUT_S = original
