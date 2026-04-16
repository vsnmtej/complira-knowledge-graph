"""
complira_graph.cse.report_agent
=================================
Post-simulation ReACT report agent for CSE.

Executes a ReACT loop (up to 5 iterations) using 3 AQL tools to query
simulation results from ArangoDB, then produces the final report dict.

Output fields:
  chain_probability, soc_miss_probability, tef_estimate,
  board_narrative, top_3_actions, completed_at

No CVE IDs in board_narrative or top_3_actions (SituationAbstractionLayer constraint).
"""

from __future__ import annotations

import asyncio
import json
import structlog
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import anthropic

from complira_graph.config import get_settings

if TYPE_CHECKING:
    from arango.database import StandardDatabase

log = structlog.get_logger(__name__)

MAX_REACT_ITERATIONS = 5

# AQL tools for ReACT loop
_AQL_DEEP_CHAIN = """
FOR finding IN attack_chain_findings
    FILTER finding.run_id == @sim_id
    SORT finding.confidence DESC
    LIMIT 10
    RETURN {
        finding_key:    finding._key,
        confidence:     finding.confidence,
        chain_length:   LENGTH(finding.chain_nodes),
        soc_blind_spots: finding.soc_blind_spots
    }
"""

_AQL_TIMELINE = """
FOR log IN agent_action_logs
    FILTER log.sim_id == @sim_id
    SORT log.round_no ASC
    LIMIT 50
    RETURN {
        round_no:    log.round_no,
        agent_type:  log.agent_type,
        action_type: log.action_type,
        outcome:     log.outcome
    }
"""

_AQL_AGENT_STATE = """
FOR log IN agent_action_logs
    FILTER log.sim_id == @sim_id
    FILTER log.agent_id == @agent_id
    SORT log.round_no DESC
    LIMIT 10
    RETURN {
        round_no:     log.round_no,
        action_type:  log.action_type,
        outcome:      log.outcome,
        episode_text: log.episode_text
    }
"""

REPORT_TOOLS = [
    {
        "name": "deep_chain_analysis",
        "description": "Query the top attack chain findings for this simulation run. Returns chain confidence, length, and SOC blind spots.",
        "input_schema": {
            "type": "object",
            "properties": {"sim_id": {"type": "string"}},
            "required": ["sim_id"],
        },
    },
    {
        "name": "timeline_reconstruction",
        "description": "Reconstruct the action timeline for this simulation run. Returns round-by-round agent actions and outcomes.",
        "input_schema": {
            "type": "object",
            "properties": {"sim_id": {"type": "string"}},
            "required": ["sim_id"],
        },
    },
    {
        "name": "agent_state_query",
        "description": "Query the recent actions of a specific agent. Returns last 10 actions with episode text.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sim_id":   {"type": "string"},
                "agent_id": {"type": "string"},
            },
            "required": ["sim_id", "agent_id"],
        },
    },
]


class CyberReportAgent:
    """ReACT loop report agent. Queries ArangoDB via tools, produces report dict."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self._model = settings.ANTHROPIC_MODEL_SONNET
        self._timeout = settings.ANTHROPIC_TIMEOUT

    def run(
        self,
        db: "StandardDatabase",
        sim_id: str,
        tenant_id: str,
        sim_dir: Path | None = None,
    ) -> dict[str, Any]:
        """
        Execute ReACT loop and return report dict.
        C-13/14/15: Also generates chain narratives, counterfactuals, audit trail in parallel.
        sim_dir: when provided, compliance_gaps.json and cyber_actions.jsonl are read.
        """
        messages = [
            {
                "role": "user",
                "content": (
                    f"Analyse simulation run {sim_id} for tenant {tenant_id}. "
                    "Use the available tools to query attack chains, timeline, and agent state. "
                    "Then produce a JSON report (no markdown) with exactly these fields:\n"
                    "chain_probability (float 0-1), soc_miss_probability (float 0-1), "
                    "tef_estimate (float, annualised loss expectancy in USD millions), "
                    "board_narrative (string, 2-3 sentences for board — NO CVE IDs, use ATT&CK tactic names), "
                    "top_3_actions (list of 3 action descriptions — no CVE IDs)."
                ),
            }
        ]

        for iteration in range(MAX_REACT_ITERATIONS):
            try:
                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=2048,
                    tools=REPORT_TOOLS,
                    messages=messages,
                    timeout=self._timeout,
                )
            except anthropic.APITimeoutError:
                log.error("cse_report_timeout", sim_id=sim_id, iteration=iteration)
                break
            except Exception as exc:
                log.error("cse_report_llm_error", sim_id=sim_id, error=str(exc))
                break

            log.info("cse_report_react_iteration", sim_id=sim_id, iteration_no=iteration + 1, stop_reason=response.stop_reason)

            if response.stop_reason == "end_turn":
                # Extract final text response
                for block in response.content:
                    if hasattr(block, "text"):
                        report = _parse_report(block.text, sim_id)
                        report["compliance_gaps"] = _read_compliance_gaps(sim_dir)
                        # C-13/14/15: generate explainability fields in parallel (F-005 fix)
                        try:
                            narratives, counterfactuals, audit_trail = asyncio.run(
                                _generate_explainability_parallel(
                                    self._client, self._model, sim_id, report, sim_dir,
                                )
                            )
                            report["chain_narratives"] = narratives
                            report["counterfactuals"]  = counterfactuals
                            report["audit_trail"]      = audit_trail
                        except Exception as exc:
                            log.warning("cse_report_explainability_error", sim_id=sim_id, error=str(exc))
                            report["chain_narratives"] = []
                            report["counterfactuals"]  = []
                            report["audit_trail"]      = []
                        return report
                break

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = self._dispatch_tool(db, block.name, block.input)
                        log.info("cse_report_react_iteration", sim_id=sim_id, iteration_no=iteration + 1, tool_called=block.name)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        })
                messages.append({"role": "user", "content": tool_results})
                continue

            break

        report = _fallback_report(sim_id)
        report["compliance_gaps"] = _read_compliance_gaps(sim_dir)
        report["chain_narratives"]  = []
        report["counterfactuals"]   = []
        report["audit_trail"]       = []
        return report

    def _dispatch_tool(self, db: "StandardDatabase", tool_name: str, inputs: dict) -> Any:
        sim_id = inputs.get("sim_id", "")
        try:
            if tool_name == "deep_chain_analysis":
                cursor = db.aql.execute(_AQL_DEEP_CHAIN, bind_vars={"sim_id": sim_id})
                return list(cursor)
            if tool_name == "timeline_reconstruction":
                cursor = db.aql.execute(_AQL_TIMELINE, bind_vars={"sim_id": sim_id})
                return list(cursor)
            if tool_name == "agent_state_query":
                agent_id = inputs.get("agent_id", "attacker_0")
                cursor = db.aql.execute(_AQL_AGENT_STATE, bind_vars={"sim_id": sim_id, "agent_id": agent_id})
                return list(cursor)
        except Exception as exc:
            log.error("cse_report_tool_error", tool=tool_name, error=str(exc))
            return {"error": str(exc)}
        return {}


def _parse_report(raw: str, sim_id: str) -> dict[str, Any]:
    import re as _re
    raw = raw.strip()
    # Strip markdown code fence
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    # Try direct parse
    try:
        report = json.loads(raw)
        report.setdefault("sim_id", sim_id)
        report.setdefault("completed_at", _now())
        return report
    except json.JSONDecodeError:
        pass
    # Try to find JSON object embedded in text
    match = _re.search(r'\{.*?\}', raw, _re.DOTALL)
    if match:
        try:
            report = json.loads(match.group())
            report.setdefault("sim_id", sim_id)
            report.setdefault("completed_at", _now())
            return report
        except json.JSONDecodeError:
            pass
    log.warning("cse_report_parse_fallback", sim_id=sim_id, raw_preview=raw[:200])
    return _fallback_report(sim_id)


def _fallback_report(sim_id: str) -> dict[str, Any]:
    return {
        "sim_id": sim_id,
        "chain_probability": None,
        "soc_miss_probability": None,
        "tef_estimate": None,
        "board_narrative": "Simulation analysis incomplete — report generation timed out.",
        "top_3_actions": [],
        "completed_at": _now(),
    }


def _read_compliance_gaps(sim_dir: Path | None) -> list[dict]:
    """Read compliance_gaps.json written by the Regulator agent in the subprocess."""
    if sim_dir is None:
        return []
    gaps_path = sim_dir / "compliance_gaps.json"
    if not gaps_path.exists():
        return []
    try:
        return json.loads(gaps_path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("cse_report_compliance_gaps_read_error", error=str(exc))
        return []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# C-13, C-14, C-15: Explainability generation (parallel LLM calls — AD-06)
# ---------------------------------------------------------------------------

async def _generate_explainability_parallel(
    client: anthropic.Anthropic,
    model: str,
    sim_id: str,
    report: dict[str, Any],
    sim_dir: Path | None,
) -> tuple[list, list, list]:
    """
    Run chain narrative, counterfactual, and audit trail generation in parallel.
    F-005: wall-clock ≈ slowest single call (~5s) vs ~15s sequential.
    """
    action_log = _read_action_log_summary(sim_dir)
    chain_data = {
        "board_narrative":    report.get("board_narrative", ""),
        "chain_probability":  report.get("chain_probability"),
        "soc_miss_prob":      report.get("soc_miss_probability"),
        "tef_estimate":       report.get("tef_estimate"),
        "compliance_gaps":    report.get("compliance_gaps", []),
        "top_3_actions":      report.get("top_3_actions", []),
    }

    narratives_coro     = _gen_chain_narratives(client, model, sim_id, chain_data, action_log)
    counterfactuals_coro = _gen_counterfactuals(client, model, sim_id, chain_data, action_log)
    audit_trail_coro    = _gen_audit_trail(client, model, sim_id, chain_data, action_log)

    results = await asyncio.gather(
        narratives_coro, counterfactuals_coro, audit_trail_coro,
        return_exceptions=True,
    )

    def _safe(r: Any, default: list) -> list:
        return r if isinstance(r, list) else default

    return _safe(results[0], []), _safe(results[1], []), _safe(results[2], [])


async def _gen_chain_narratives(
    client: anthropic.Anthropic,
    model: str,
    sim_id: str,
    chain_data: dict[str, Any],
    action_log: list[dict],
) -> list[dict]:
    """C-13: Per-chain narrative — entry point, technique, defender response, countermeasure."""
    attacker_actions = [e for e in action_log if e.get("agent_type") == "Attacker"]
    defender_actions = [e for e in action_log if e.get("agent_type") in ("SOCAnalyst", "DevSecOps", "CISO")]

    prompt = (
        "You are a cybersecurity analyst writing chain explanations for a CISO simulation report. "
        "No CVE IDs in output — use ATT&CK technique names and tactic names only.\n\n"
        f"Attack summary: {json.dumps(chain_data)}\n"
        f"Key attacker actions (last 10): {json.dumps(attacker_actions[-10:])}\n"
        f"Key defender actions (last 10): {json.dumps(defender_actions[-10:])}\n\n"
        "Generate a JSON array of chain narrative objects. Each object:\n"
        "- chain_id: string (e.g. 'chain_0')\n"
        "- technique_id: ATT&CK technique observed\n"
        "- entry_point_reasoning: why attacker chose this vector (1-2 sentences, no CVE IDs)\n"
        "- success_reasoning: why exploit succeeded given defender posture (1-2 sentences)\n"
        "- defender_response: what defender did in response (1 sentence)\n"
        "- soc_blind_spot_explanation: what detection would have caught this, or null\n"
        "- single_countermeasure: one specific action that would have stopped this chain\n\n"
        "Return only the JSON array. If data is insufficient, return []."
    )
    return await _llm_json_list(client, model, prompt, sim_id, "chain_narratives")


async def _gen_counterfactuals(
    client: anthropic.Anthropic,
    model: str,
    sim_id: str,
    chain_data: dict[str, Any],
    action_log: list[dict],
) -> list[dict]:
    """C-14: Counterfactual analysis — what would have broken each chain."""
    patch_events = [e for e in action_log if e.get("action_type") == "PATCH"]
    cra_events   = [e for e in action_log if e.get("action_type") == "FILE_CRA_NOTIFICATION"]

    prompt = (
        "You are a cybersecurity risk analyst generating counterfactual analysis. "
        "No CVE IDs in output.\n\n"
        f"Simulation summary: {json.dumps(chain_data)}\n"
        f"Patch actions taken: {json.dumps(patch_events[:5])}\n"
        f"Regulatory notifications: {json.dumps(cra_events[:3])}\n\n"
        "Generate a JSON array of counterfactual objects. Each object:\n"
        "- chain_id: string\n"
        "- intervention_type: 'patch' | 'monitoring' | 'control' | 'notification'\n"
        "- intervention_description: specific action in plain English (no CVE IDs)\n"
        "- current_state: what actually happened with timing\n"
        "- impact_if_applied: what outcome would change and by how much\n"
        "- rounds_available: how many rounds were available to act before the breach\n\n"
        "Return only the JSON array. If data is insufficient, return []."
    )
    return await _llm_json_list(client, model, prompt, sim_id, "counterfactuals")


async def _gen_audit_trail(
    client: anthropic.Anthropic,
    model: str,
    sim_id: str,
    chain_data: dict[str, Any],
    action_log: list[dict],
) -> list[dict]:
    """C-15: Ordered regulatory timeline — which obligations were met or missed."""
    significant = [
        e for e in action_log
        if e.get("significance", 0) >= 0.7 or e.get("action_type") in (
            "FILE_CRA_NOTIFICATION", "NOTIFY_BOARD", "ESCALATE_TO_CISO",
            "FILE_INCIDENT_REPORT", "NOTIFY_REGULATOR",
        )
    ]

    prompt = (
        "You are a compliance officer generating an audit trail for a cybersecurity simulation. "
        "No CVE IDs in output.\n\n"
        f"Simulation summary: {json.dumps(chain_data)}\n"
        f"Significant events: {json.dumps(significant[:20])}\n\n"
        "Generate a chronological JSON array of audit events. Each object:\n"
        "- round_no: integer\n"
        "- event_type: 'exploit' | 'detection' | 'patch' | 'deadline' | 'notification' | 'escalation'\n"
        "- description: plain English (no CVE IDs, use tactic names)\n"
        "- regulatory_obligation: framework + article number, or null\n"
        "- outcome: 'met' | 'missed' | 'not_applicable'\n\n"
        "Return only the JSON array sorted by round_no. If data is insufficient, return []."
    )
    return await _llm_json_list(client, model, prompt, sim_id, "audit_trail")


async def _llm_json_list(
    client: anthropic.Anthropic,
    model: str,
    prompt: str,
    sim_id: str,
    field: str,
) -> list:
    """Helper: call LLM and parse JSON list response."""
    try:
        response = await asyncio.to_thread(
            client.messages.create,
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip().strip("`").strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:-1])
        result = json.loads(raw)
        if isinstance(result, list):
            return result
    except Exception as exc:
        log.warning(f"cse_report_{field}_error", sim_id=sim_id, error=str(exc))
    return []


def _read_action_log_summary(sim_dir: Path | None) -> list[dict]:
    """Read significant actions from cyber_actions.jsonl for explainability context."""
    if sim_dir is None:
        return []
    jsonl_path = sim_dir / "cyber_actions.jsonl"
    if not jsonl_path.exists():
        return []
    entries = []
    try:
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("type") == "action" and entry.get("significance", 0) >= 0.6:
                    entries.append({
                        "round_no":        entry.get("round_no"),
                        "agent_type":      entry.get("agent_type"),
                        "action_type":     entry.get("action_type"),
                        "outcome":         entry.get("outcome", "")[:120],
                        "significance":    entry.get("significance"),
                        "decision_source": entry.get("decision_source", "llm"),
                        "technique_id":    entry.get("technique_id"),
                    })
            except Exception:
                continue
    except Exception as exc:
        log.warning("cse_report_action_log_read_error", error=str(exc))
    return entries
