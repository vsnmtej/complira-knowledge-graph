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

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import anthropic

from complira_graph.config import get_settings

if TYPE_CHECKING:
    from arango.database import StandardDatabase

log = logging.getLogger(__name__)

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

    def run(self, db: "StandardDatabase", sim_id: str, tenant_id: str) -> dict[str, Any]:
        """Execute ReACT loop and return report dict."""
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
                        return _parse_report(block.text, sim_id)
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

        return _fallback_report(sim_id)

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
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        report = json.loads(raw)
        report.setdefault("sim_id", sim_id)
        report.setdefault("completed_at", _now())
        return report
    except json.JSONDecodeError:
        log.warning("cse_report_parse_fallback", sim_id=sim_id)
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
