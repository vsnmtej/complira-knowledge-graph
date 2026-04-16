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
import structlog
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from complira_graph.config import get_settings
from complira_graph.cse.config_generator import CyberSimConfigGenerator
from complira_graph.cse.graph_reader import CompliraGraphReader
from complira_graph.cse.profile_generator import CyberAgentProfileGenerator
from complira_graph.cse.technique_resolver import TechniqueResolver
from complira_graph.cse.report_agent import CyberReportAgent
from complira_graph.cse.runner import CyberRunnerStatus, CyberSimulationRunner
from complira_graph.simulation.writeback_service import SimulationWritebackService

if TYPE_CHECKING:
    from arango.database import StandardDatabase

log = structlog.get_logger(__name__)

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
        total_rounds: int | None = None,
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

        # Technique resolution (C-01): resolve CVE → ATT&CK techniques once at prepare time
        entity_techniques = TechniqueResolver(db).resolve_all(entities)

        # Config synthesis
        config_gen = CyberSimConfigGenerator()
        config_gen.generate(sim_id, tenant_id, trigger_type, profiles, entities, sim_dir,
                           total_rounds_override=total_rounds,
                           entity_techniques=entity_techniques)

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

        # Flush JSONL action logs → ArangoDB before report agent queries them
        self._flush_action_logs_to_arango(db, sim_id, tenant_id, runner.sim_dir)

        # Run report agent
        report_agent = CyberReportAgent()
        report = report_agent.run(db, sim_id, tenant_id, sim_dir=runner.sim_dir)

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

    def _flush_action_logs_to_arango(
        self,
        db: "StandardDatabase",
        sim_id: str,
        tenant_id: str,
        sim_dir: Path,
    ) -> None:
        """Read cyber_actions.jsonl and upsert action entries into agent_action_logs."""
        import json as _json
        jsonl_path = sim_dir / "cyber_actions.jsonl"
        if not jsonl_path.exists():
            return
        try:
            lines = jsonl_path.read_text(encoding="utf-8").splitlines()
        except Exception as exc:
            log.warning("cse_flush_logs_read_error", sim_id=sim_id, error=str(exc))
            return

        _AQL = """
        UPSERT { _key: @key }
        INSERT {
          _key: @key, sim_id: @sim_id, tenant_id: @tenant_id,
          agent_id: @agent_id, agent_type: @agent_type,
          action_type: @action_type, outcome: @outcome,
          round_no: @round_no, significance: @significance,
          episode_text: @episode_text, timestamp: @timestamp,
          decision_source: @decision_source,
          decision_reasoning: @decision_reasoning,
          game_state_snapshot: @game_state_snapshot,
          technique_id: @technique_id,
          technique_source: @technique_source
        }
        UPDATE {}
        IN agent_action_logs
        """
        written = 0
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entry = _json.loads(line)
            except Exception:
                continue
            if entry.get("type") != "action":
                continue
            try:
                # F-004: key uses line index (i) to prevent collision on multi-action rounds
                db.aql.execute(_AQL, bind_vars={
                    "key":               f"{sim_id}_{i:06d}",
                    "sim_id":            sim_id,
                    "tenant_id":         tenant_id,
                    "agent_id":          entry.get("agent_id", ""),
                    "agent_type":        entry.get("agent_type", ""),
                    "action_type":       entry.get("action_type", ""),
                    "outcome":           entry.get("outcome", ""),
                    "round_no":          entry.get("round_no", 0),
                    "significance":      entry.get("significance", 0.0),
                    "episode_text":      entry.get("episode_text", ""),
                    "timestamp":         entry.get("timestamp", ""),
                    # C-09 / C-16: explainability fields
                    "decision_source":   entry.get("decision_source", "llm"),
                    "decision_reasoning": entry.get("decision_reasoning", ""),
                    "game_state_snapshot": entry.get("game_state_snapshot", {}),
                    "technique_id":      entry.get("technique_id"),
                    "technique_source":  entry.get("technique_source"),
                })
                written += 1
            except Exception as exc:
                log.warning("cse_flush_log_write_error", sim_id=sim_id, error=str(exc))
        log.info("cse_action_logs_flushed", sim_id=sim_id, count=written)

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

        jsonl_actions = _read_jsonl_actions(runner.sim_dir)

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
            "attack_chains": _build_attack_chains(report, sim_id, jsonl_actions),
            "playbook_steps": _build_playbook_steps(report, sim_id),
            "compliance_gaps": _build_compliance_gaps(report, sim_id, tenant_id, jsonl_actions),
            "agent_outputs": _build_agent_outputs(report),
        }


def _read_jsonl_actions(sim_dir: Path) -> list[dict[str, Any]]:
    """Read action entries from cyber_actions.jsonl."""
    jsonl_path = sim_dir / "cyber_actions.jsonl"
    if not jsonl_path.exists():
        return []
    result = []
    try:
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("type") == "action":
                    result.append(entry)
            except Exception:
                pass
    except Exception:
        pass
    return result


def _build_compliance_gaps(
    report: dict[str, Any],
    sim_id: str,
    tenant_id: str,
    jsonl_actions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Map Regulator compliance gaps from report; synthesize from AUDIT actions if empty."""
    gaps = report.get("compliance_gaps") or []
    if not gaps and jsonl_actions:
        # Synthesize gaps from Regulator AUDIT_VULNERABILITY actions
        audit_actions = [a for a in jsonl_actions if a.get("action_type") == "AUDIT_VULNERABILITY"]
        for i, action in enumerate(audit_actions[:5]):
            cve = action.get("payload", {}).get("cve_id", f"unknown_{i}")
            gaps.append({
                "requirement_key": f"CRA_ART13_{i}",
                "framework": "CRA",
                "description": f"Vulnerability {cve} exploited in simulation without timely remediation",
                "severity": "high",
                "cve_id": cve,
                "round_no": action.get("round_no", 0),
            })
    result = []
    for i, gap in enumerate(gaps):
        result.append({
            "gap_key":         f"{sim_id}_gap_{i}",
            "run_id":          sim_id,
            "tenant_id":       tenant_id,
            "requirement_key": gap.get("requirement_key", "unknown"),
            "framework":       gap.get("framework", "CRA"),
            "description":     gap.get("description", ""),
            "severity":        gap.get("severity", "medium"),
            "cve_id":          gap.get("cve_id"),
            "round_no":        gap.get("round_no", 0),
        })
    return result


def _build_attack_chains(
    report: dict[str, Any],
    sim_id: str,
    jsonl_actions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build attack chain finding from report + JSONL technique data."""
    probability = report.get("chain_probability") or 0.0

    # Extract techniques from attacker exploit actions in JSONL
    chain_steps: list[dict[str, Any]] = []
    if jsonl_actions:
        exploit_actions = [a for a in jsonl_actions if a.get("action_type") == "EXPLOIT_CVE"]
        seen_techniques: set[str] = set()
        for action in exploit_actions:
            technique = action.get("payload", {}).get("technique", "T1190")
            if technique not in seen_techniques:
                chain_steps.append({"technique": technique, "outcome": action.get("outcome", "")})
                seen_techniques.add(technique)
        if not probability and exploit_actions:
            # Derive probability from exploit success rate
            successes = sum(1 for a in exploit_actions if "success" in a.get("outcome", "").lower())
            probability = min(0.95, successes / max(len(exploit_actions), 1) * 0.9)

    if not probability and not chain_steps:
        return []

    return [{
        "finding_key":      f"cse_chain_{sim_id}",
        "cve_id":           "attack_surface_sim",
        "chain_nodes":      [],
        "chain_edges":      [],
        "chain_steps":      chain_steps,
        "soc_blind_spots":  [],
        "confidence":       float(probability),
        "chain_probability": float(probability),
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
    tef = report.get("tef_estimate") or 0.0
    outputs = []
    if narrative:
        # board_member_agent — written to business_impact_findings by step 8b
        outputs.append({
            "agent_type":      "board_member_agent",
            "impact_type":     "reputational_risk",
            "narrative":       narrative,
            "estimated_value": 0.0,
            "currency":        "USD",
            "framework":       None,
            "confidence":      report.get("soc_miss_probability") or 0.7,
        })
        # cfo_agent — financial exposure from tef_estimate
        if tef:
            outputs.append({
                "agent_type":      "cfo_agent",
                "impact_type":     "financial_exposure",
                "narrative":       f"Annualised loss expectancy estimated at ${tef:.1f}M based on exploit chain analysis.",
                "estimated_value": float(tef) * 1_000_000,
                "currency":        "USD",
                "framework":       None,
                "confidence":      0.65,
            })
    return outputs


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
