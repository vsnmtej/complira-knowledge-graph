"""
complira_graph.cse.action_logger
=================================
Append-only JSONL action log for CSE simulation runs.

Writes one JSON line per event to cyber_actions.jsonl in the simulation
run directory. Three event types:
  - simulation_start   — written once at simulation startup
  - round_start        — written once per round
  - action             — written once per agent action per round

Thread-safety: all writes happen from the subprocess main thread only.
"""

from __future__ import annotations

import json
import structlog
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = structlog.get_logger(__name__)


class CyberActionLogger:
    """Append-only JSONL logger for CSE simulation actions."""

    def __init__(self, sim_dir: str | Path) -> None:
        self._path = Path(sim_dir) / "cyber_actions.jsonl"
        self._file = self._path.open("a", encoding="utf-8")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log_simulation_start(
        self,
        sim_id: str,
        tenant_id: str,
        total_rounds: int,
        trigger_type: str,
    ) -> None:
        self._write(
            {
                "type": "simulation_start",
                "sim_id": sim_id,
                "tenant_id": tenant_id,
                "total_rounds": total_rounds,
                "trigger_type": trigger_type,
                "timestamp": _now(),
            }
        )

    def log_round_start(self, round_no: int) -> None:
        self._write({"type": "round_start", "round_no": round_no, "timestamp": _now()})

    def log_action(
        self,
        action_type: str,
        agent_id: str,
        agent_type: str,
        payload: dict[str, Any],
        outcome: str,
        round_no: int,
        significance: float = 0.5,
        # C-16: explainability fields
        decision_source: str = "llm",           # "llm" | "heuristic" | "scheduled"
        decision_reasoning: str = "",
        game_state_snapshot: dict[str, Any] | None = None,
        technique_id: str | None = None,
        technique_source: str | None = None,
    ) -> None:
        record: dict[str, Any] = {
            "type":              "action",
            "action_type":       action_type,
            "agent_id":          agent_id,
            "agent_type":        agent_type,
            "payload":           payload,
            "outcome":           outcome,
            "round_no":          round_no,
            "significance":      significance,
            "timestamp":         _now(),
            "decision_source":   decision_source,
            "decision_reasoning": decision_reasoning,
        }
        if game_state_snapshot is not None:
            # Compact snapshot — only key fields to keep JSONL size manageable
            record["game_state_snapshot"] = {
                "exploitable_count": len(game_state_snapshot.get("exploitable_cves", [])),
                "patched_count":     len(game_state_snapshot.get("patched_cves", [])),
                "chain_steps":       game_state_snapshot.get("chain_step_count", 0),
                "monitoring":        game_state_snapshot.get("monitoring_active", False),
                "privilege_level":   game_state_snapshot.get("privilege_level", 0),
                "attacker_phase":    game_state_snapshot.get("attacker_phase", ""),
            }
        if technique_id:
            record["technique_id"]     = technique_id
            record["technique_source"] = technique_source
        self._write(record)

    def close(self) -> None:
        try:
            self._file.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _write(self, record: dict[str, Any]) -> None:
        try:
            self._file.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._file.flush()
        except Exception as exc:
            log.error("cse_action_logger_write_error", error=str(exc))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
