"""
complira_graph.cse.simulation_manager
========================================
Orchestrates the full CSE simulation lifecycle.

prepare()  — graph read → profile gen → config gen → CREATED → READY
run()      — start subprocess (RUNNING)
complete() — wait for COMPLETED → report agent → write-back → CLOSE_ENV

Called by the CSE API endpoint. Does not own simulation execution details.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from complira_graph.config import get_settings
from complira_graph.cse.config_generator import CyberSimConfigGenerator
from complira_graph.cse.graph_reader import CompliraGraphReader
from complira_graph.cse.profile_generator import CyberAgentProfileGenerator
from complira_graph.cse.report_agent import CyberReportAgent
from complira_graph.cse.runner import CyberRunnerStatus, CyberSimulationRunner
from complira_graph.simulation.writeback_service import SimulationWritebackService

if TYPE_CHECKING:
    from arango.database import StandardDatabase

log = logging.getLogger(__name__)

_COMPLETION_POLL_INTERVAL_S = 2.0
_COMPLETION_TIMEOUT_S = 7200.0  # 2 hours max


class CyberSimulationManager:
    """Orchestrates CSE simulation prepare + run + complete pipeline."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._data_dir = Path(self._settings.CSE_DATA_DIR)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def prepare(
        self,
        db: "StandardDatabase",
        tenant_id: str,
        trigger_type: str = "kev_triggered",
    ) -> tuple[str, CyberSimulationRunner]:
        """
        Run prepare pipeline. Returns (sim_id, runner).
        Raises ValueError if attack surface is empty.
        """
        sim_id = str(uuid.uuid4())
        sim_dir = self._data_dir / tenant_id / sim_id
        self._create_sim_directories(sim_dir)

        runner = CyberSimulationRunner(sim_id, tenant_id, sim_dir)
        runner._transition(CyberRunnerStatus.IDLE)  # noqa: SLF001

        # Graph read
        reader = CompliraGraphReader(db)
        entities = reader.get_attack_surface(tenant_id)
        if not entities:
            raise ValueError("insufficient_attack_surface")

        # Profile generation
        profile_gen = CyberAgentProfileGenerator()
        profiles = await profile_gen.generate_all(entities)

        # Config synthesis
        config_gen = CyberSimConfigGenerator()
        config_gen.generate(sim_id, tenant_id, trigger_type, profiles, entities, sim_dir)

        # Upsert simulation_runs in ArangoDB
        self._upsert_simulation_run(db, sim_id, tenant_id, trigger_type, "ready")

        # Transition runner to READY
        runner._transition(CyberRunnerStatus.RUNNING)  # noqa: SLF001
        # Immediately set back to a logical "ready" — runner starts at IDLE then will RUNNING on start_simulation
        # Actually: use the IDLE→RUNNING transition only on start_simulation().
        # Here we mark the run as READY in the DB; the runner status is IDLE until start_simulation().
        # Re-sync:
        runner._status = CyberRunnerStatus.IDLE  # noqa: SLF001
        _write_ready_state(sim_dir, sim_id, tenant_id)

        log.info("cse_prepare_complete", sim_id=sim_id, tenant_id=tenant_id)
        return sim_id, runner

    def start(self, runner: CyberSimulationRunner) -> None:
        """Start the subprocess."""
        runner.start_simulation()

    async def complete(
        self,
        db: "StandardDatabase",
        runner: CyberSimulationRunner,
    ) -> dict[str, Any]:
        """
        Wait for subprocess to reach COMPLETED, run report agent,
        call write-back, send CLOSE_ENV. Returns report dict.
        """
        sim_id = runner.sim_id
        tenant_id = runner.tenant_id

        # Wait for subprocess to write completed status
        await self._wait_for_completion(runner)

        state = _read_run_state(runner.sim_dir)
        if (state or {}).get("status") == "failed":
            log.error("cse_complete_subprocess_failed", sim_id=sim_id)
            return {"sim_id": sim_id, "status": "failed"}

        # Run report agent
        report_agent = CyberReportAgent()
        report = report_agent.run(db, sim_id, tenant_id)

        # Write-back
        try:
            payload = self._build_writeback_payload(sim_id, tenant_id, report, runner)
            SimulationWritebackService(db).run_all(payload)
            log.info("cse_writeback_complete", sim_id=sim_id)
        except Exception as exc:
            log.error("cse_writeback_error", sim_id=sim_id, error=str(exc))

        # Terminate debrief loop in subprocess
        runner.send_close_env()

        log.info("cse_complete", sim_id=sim_id)
        return report

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _create_sim_directories(self, sim_dir: Path) -> None:
        (sim_dir / "ipc_commands").mkdir(parents=True, exist_ok=True)
        (sim_dir / "ipc_responses").mkdir(parents=True, exist_ok=True)

    def _upsert_simulation_run(
        self,
        db: "StandardDatabase",
        sim_id: str,
        tenant_id: str,
        trigger_type: str,
        status: str,
    ) -> None:
        doc = {
            "_key":        sim_id,
            "sim_id":      sim_id,
            "tenant_id":   tenant_id,
            "trigger_type": trigger_type,
            "status":      status,
            "started_at":  _now(),
        }
        try:
            db.collection("simulation_runs").insert(doc, silent=True)
        except Exception:
            try:
                db.collection("simulation_runs").update({"_key": sim_id, "status": status})
            except Exception as exc:
                log.error("cse_upsert_sim_run_error", sim_id=sim_id, error=str(exc))

    async def _wait_for_completion(self, runner: CyberSimulationRunner) -> None:
        deadline = time.monotonic() + _COMPLETION_TIMEOUT_S
        while time.monotonic() < deadline:
            state = _read_run_state(runner.sim_dir)
            if state and state.get("status") in ("completed", "failed"):
                return
            await asyncio.sleep(_COMPLETION_POLL_INTERVAL_S)
        log.error("cse_completion_timeout", sim_id=runner.sim_id)

    def _build_writeback_payload(
        self,
        sim_id: str,
        tenant_id: str,
        report: dict[str, Any],
        runner: CyberSimulationRunner,
    ) -> dict[str, Any]:
        config_path = runner.sim_dir / "simulation_config.json"
        config: dict[str, Any] = {}
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            pass

        return {
            "run_id":      sim_id,
            "tenant_id":   tenant_id,
            "cve_id":      "attack_surface_sim",  # no single CVE — attack surface run
            "incident_id": None,
            "device_keys": [],
            "started_at":  runner._started_at or _now(),  # noqa: SLF001
            "completed_at": report.get("completed_at", _now()),
            "status":      "completed",
            "agent_count": len(config.get("agent_profiles", [])),
            "round_count": config.get("total_rounds", 0),
            "attack_chains": _build_attack_chains(report),
            "playbook_steps": _build_playbook_steps(report, sim_id),
            "compliance_gaps": [],
            "agent_outputs": _build_agent_outputs(report),
        }


def _build_attack_chains(report: dict[str, Any]) -> list[dict[str, Any]]:
    if not report.get("chain_probability"):
        return []
    return [{
        "finding_key":      f"cse_chain_{report.get('sim_id', 'unknown')}",
        "cve_id":           "attack_surface_sim",
        "chain_nodes":      [],
        "chain_edges":      [],
        "soc_blind_spots":  [],
        "confidence":       float(report.get("chain_probability", 0.0)),
        "vex_statement_key": None,
        "component_keys":   [],
        "fair_scenario_key": None,
    }]


def _build_playbook_steps(report: dict[str, Any], sim_id: str) -> list[dict[str, Any]]:
    steps = []
    for i, action in enumerate(report.get("top_3_actions", [])[:3]):
        steps.append({
            "step_key":    f"{sim_id}_step_{i}",
            "finding_key": f"cse_chain_{sim_id}",
            "action":      action,
            "priority":    i + 1,
            "description": action,
        })
    return steps


def _build_agent_outputs(report: dict[str, Any]) -> list[dict[str, Any]]:
    narrative = report.get("board_narrative", "")
    if not narrative:
        return []
    return [{
        "agent_type":    "CISO",
        "impact_type":   "board_narrative",
        "narrative":     narrative,
        "tef_estimate":  report.get("tef_estimate"),
        "soc_miss_probability": report.get("soc_miss_probability"),
    }]


def _read_run_state(sim_dir: Path) -> dict[str, Any] | None:
    try:
        return json.loads((sim_dir / "run_state.json").read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_ready_state(sim_dir: Path, sim_id: str, tenant_id: str) -> None:
    state = {
        "sim_id": sim_id,
        "tenant_id": tenant_id,
        "status": "ready",
        "current_round": 0,
        "updated_at": _now(),
    }
    try:
        (sim_dir / "run_state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as exc:
        log.error("cse_write_ready_state_error", sim_id=sim_id, error=str(exc))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
