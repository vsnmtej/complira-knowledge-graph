"""
complira_graph.cse.ipc
========================
File-based IPC for CSE simulation.

Two sides:
  CyberIPCClient  — used by the main process (FastAPI) to send commands and
                    wait for responses from the subprocess.
  CyberIPCHandler — used by the subprocess to poll for incoming commands,
                    dispatch them, and write response files.

Wire protocol:
  ipc_commands/{cmd_id}.json   — command written by CyberIPCClient
  ipc_responses/{cmd_id}.json  — response written by CyberIPCHandler

Both directories are created by CyberSimulationRunner before the subprocess starts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

# IPC command constants
CMD_INJECT_VARIABLE     = "INJECT_VARIABLE"
CMD_PAUSE_AND_SNAPSHOT  = "PAUSE_AND_SNAPSHOT"
CMD_CLOSE_ENV           = "CLOSE_ENV"
CMD_DEBRIEF_AGENT       = "DEBRIEF_AGENT"

IPC_RESPONSE_TIMEOUT_S  = 5.0
IPC_POLL_INTERVAL_S     = 0.1


class IPCTimeoutError(Exception):
    pass


# ---------------------------------------------------------------------------
# Main-process side
# ---------------------------------------------------------------------------

class CyberIPCClient:
    """Writes command files and reads response files (main process side)."""

    def __init__(self, sim_dir: str | Path) -> None:
        self._cmd_dir  = Path(sim_dir) / "ipc_commands"
        self._resp_dir = Path(sim_dir) / "ipc_responses"

    def send_command(self, command: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Write command file, block until response arrives or timeout."""
        cmd_id = str(uuid.uuid4())
        cmd_path = self._cmd_dir / f"{cmd_id}.json"
        cmd_path.write_text(
            json.dumps({"command": command, "payload": payload, "cmd_id": cmd_id, "sent_at": _now()}),
            encoding="utf-8",
        )
        log.debug("ipc_command_sent", command=command, cmd_id=cmd_id)

        resp_path = self._resp_dir / f"{cmd_id}.json"
        deadline = time.monotonic() + IPC_RESPONSE_TIMEOUT_S
        while time.monotonic() < deadline:
            if resp_path.exists():
                try:
                    result = json.loads(resp_path.read_text(encoding="utf-8"))
                    resp_path.unlink(missing_ok=True)
                    return result
                except Exception:
                    pass
            time.sleep(IPC_POLL_INTERVAL_S)

        raise IPCTimeoutError(f"IPC command {command} (id={cmd_id}) timed out after {IPC_RESPONSE_TIMEOUT_S}s")


# ---------------------------------------------------------------------------
# Subprocess side
# ---------------------------------------------------------------------------

class CyberIPCHandler:
    """Polls command files and dispatches them (subprocess side)."""

    def __init__(self, sim_dir: str | Path) -> None:
        self._cmd_dir  = Path(sim_dir) / "ipc_commands"
        self._resp_dir = Path(sim_dir) / "ipc_responses"
        self._stop_flag = False
        self._pause_flag = False
        # Registered dispatch hooks (set by run_parallel_cyber_simulation.py)
        self._handlers: dict[str, Callable[[dict], dict]] = {}

    def register(self, command: str, handler: Callable[[dict], dict]) -> None:
        self._handlers[command] = handler

    @property
    def stop_requested(self) -> bool:
        return self._stop_flag

    @property
    def pause_requested(self) -> bool:
        return self._pause_flag

    async def poll_commands(self) -> None:
        """Async poll loop — runs as one of the asyncio.gather tasks."""
        while not self._stop_flag:
            try:
                self._process_pending()
            except Exception as exc:
                log.error("ipc_poll_error", error=str(exc))
            await asyncio.sleep(IPC_POLL_INTERVAL_S)

    def _process_pending(self) -> None:
        for cmd_path in sorted(self._cmd_dir.glob("*.json")):
            try:
                data = json.loads(cmd_path.read_text(encoding="utf-8"))
                cmd_id = data.get("cmd_id", cmd_path.stem)
                command = data.get("command", "")
                payload = data.get("payload", {})

                result = self._dispatch(command, payload)

                resp_path = self._resp_dir / f"{cmd_id}.json"
                resp_path.write_text(
                    json.dumps({"cmd_id": cmd_id, "result": result, "responded_at": _now()}),
                    encoding="utf-8",
                )
                cmd_path.unlink(missing_ok=True)
                log.debug("ipc_command_dispatched", command=command, cmd_id=cmd_id)
            except Exception as exc:
                log.error("ipc_dispatch_error", path=str(cmd_path), error=str(exc))
                try:
                    cmd_path.unlink(missing_ok=True)
                except Exception:
                    pass

    def _dispatch(self, command: str, payload: dict) -> dict[str, Any]:
        if command == CMD_CLOSE_ENV:
            self._stop_flag = True
            return {"status": "stopping"}

        if command == CMD_PAUSE_AND_SNAPSHOT:
            self._pause_flag = True
            return {"status": "paused"}

        if command == CMD_INJECT_VARIABLE:
            if payload.get("resume"):
                self._pause_flag = False
                return {"status": "resumed"}
            # Forward to registered handler
            handler = self._handlers.get(CMD_INJECT_VARIABLE)
            if handler:
                return handler(payload)
            return {"status": "injected"}

        if command == CMD_DEBRIEF_AGENT:
            handler = self._handlers.get(CMD_DEBRIEF_AGENT)
            if handler:
                return handler(payload)
            return {"status": "debrief_noop"}

        log.warning("ipc_unknown_command", command=command)
        return {"error": "unknown_command", "command": command}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
