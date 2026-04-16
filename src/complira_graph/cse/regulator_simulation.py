"""
complira_graph.cse.regulator_simulation
=========================================
Regulator agent loop for CSE simulation (subprocess side).

Runs for total_rounds, selecting one compliance audit action per round
using a lightweight LLM call, then applying it to AttackSurfaceServer.
Writes compliance gap findings to surface_server.compliance_gaps.
"""

from __future__ import annotations

import asyncio
import structlog
import random
from typing import Any

import anthropic

from complira_graph.config import get_settings
from complira_graph.cse.action_logger import CyberActionLogger
from complira_graph.cse.attack_surface_server import (
    AttackSurfaceServer,
    AUDIT_VULNERABILITY,
    ISSUE_COMPLIANCE_FINDING,
    FILE_INCIDENT_REPORT,
    NOTIFY_REGULATOR,
    APPROVE_EXCEPTION,
)
from complira_graph.cse.constants import VALID_FRAMEWORKS, VALID_SEVERITIES, REQUIREMENT_KEYS
from complira_graph.cse.memory_updater import CyberAgentActivity, CyberMemoryUpdater

log = structlog.get_logger(__name__)

REGULATOR_ACTIONS = [
    AUDIT_VULNERABILITY,
    ISSUE_COMPLIANCE_FINDING,
    FILE_INCIDENT_REPORT,
    NOTIFY_REGULATOR,
    APPROVE_EXCEPTION,
]

_MAX_LLM_ATTEMPTS  = 3
_LLM_BACKOFF_BASE  = 0.5
_FRAMEWORKS        = sorted(VALID_FRAMEWORKS)   # keep for backward compat
_SEVERITIES        = sorted(VALID_SEVERITIES)


async def run_regulator_loop(
    config: dict[str, Any],
    surface_server: AttackSurfaceServer,
    logger: CyberActionLogger,
    memory: CyberMemoryUpdater,
    ipc_handler: Any,
) -> None:
    """Regulator coroutine — runs total_rounds, one compliance action per round."""
    total_rounds: int = config["total_rounds"]
    agent_id = "regulator_0"
    agent_type = "Regulator"
    profile = _get_profile(config, agent_type)

    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    for round_no in range(1, total_rounds + 1):
        while ipc_handler.pause_requested:
            await asyncio.sleep(0.2)
        if ipc_handler.stop_requested:
            break

        # F-007: snapshot BEFORE decision
        game_state = surface_server.get_state_snapshot()

        action_type, payload, decision_source, reasoning = await _decide_action(
            client, settings.ANTHROPIC_MODEL_HAIKU,
            round_no, surface_server, profile, config, game_state,
        )

        try:
            result = surface_server.apply_action(action_type, payload, round_no)
        except ValueError as val_err:
            # C-09 / C-12: validation failed — log and continue
            log.warning("cse_regulator_payload_invalid", round_no=round_no, error=str(val_err))
            result_outcome = f"validation_failed: {val_err}"
            from complira_graph.cse.attack_surface_server import ActionResult
            result = ActionResult(action_type, result_outcome, {}, significance=0.1)

        logger.log_action(
            action_type, agent_id, agent_type, payload, result.outcome, round_no, result.significance,
            decision_source=decision_source,
            decision_reasoning=reasoning,
            game_state_snapshot=game_state,
        )

        episode = f"Round {round_no}: {agent_type} executed {action_type}. {result.outcome}"
        memory.record(CyberAgentActivity(
            sim_id=config["sim_id"],
            agent_id=agent_id,
            agent_type=agent_type,
            round_no=round_no,
            action_type=action_type,
            target=payload.get("cve_id", payload.get("requirement_key", "")),
            outcome=result.outcome,
            episode_text=episode,
        ))

        await asyncio.sleep(0)  # yield to attacker + defender + IPC poller


async def _decide_action(
    client: anthropic.Anthropic,
    model: str,
    round_no: int,
    surface_server: AttackSurfaceServer,
    profile: dict[str, Any],
    config: dict[str, Any],
    game_state: dict[str, Any],
) -> tuple[str, dict[str, Any], str, str]:
    """
    Use LLM to pick Regulator action. Returns (action, payload, source, reasoning).
    C-07: 3 LLM attempts with backoff → heuristic fallback.
    """
    exploited_cves = [step.cve_id for step in surface_server.chain_steps]
    gap_count      = len(surface_server.compliance_gaps)

    prompt = (
        f"Round {round_no}/{config['total_rounds']}. "
        "You are a compliance regulator. "
        f"Exploited CVEs in attack chain: {exploited_cves[:5]}. "
        f"Existing compliance gaps recorded: {gap_count}. "
        f"Incident report filed: {surface_server.incident_report_filed}. "
        f"Regulator notified: {surface_server.regulator_notified}. "
        f"Your role: {profile.get('role', 'compliance_auditor')}. "
        "Choose ONE action from: AUDIT_VULNERABILITY, ISSUE_COMPLIANCE_FINDING, "
        "FILE_INCIDENT_REPORT, NOTIFY_REGULATOR, APPROVE_EXCEPTION. "
        "If AUDIT_VULNERABILITY or ISSUE_COMPLIANCE_FINDING, include cve_id (MUST be non-empty, from exploited list). "
        f"If ISSUE_COMPLIANCE_FINDING, include: framework ({'/'.join(sorted(VALID_FRAMEWORKS))}), "
        f"requirement_key (from: {REQUIREMENT_KEYS[:4]}), description, severity (critical|high|medium|low). "
        'Reply with JSON only: {"action": "...", "cve_id": "...", "framework": "...", '
        '"requirement_key": "...", "description": "...", "severity": "..."}. '
        "Omit fields not relevant to the chosen action."
    )

    for attempt in range(_MAX_LLM_ATTEMPTS):
        try:
            response = await asyncio.to_thread(
                client.messages.create,
                model=model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            action, payload = _parse_action_response(response.content[0].text, surface_server, round_no)
            return action, payload, "llm", f"llm_chose_{action}"
        except anthropic.RateLimitError:
            wait = _LLM_BACKOFF_BASE * (2 ** attempt)
            log.warning("cse_regulator_rate_limit", round_no=round_no, attempt=attempt, wait=wait)
            await asyncio.sleep(wait)
        except Exception as exc:
            log.warning("cse_regulator_llm_error", round_no=round_no, attempt=attempt, error=str(exc))

    # Heuristic fallback
    action = AUDIT_VULNERABILITY
    payload = _fallback_payload(action, surface_server, round_no)
    return action, payload, "heuristic", "heuristic_audit_fallback"


def _parse_action_response(
    raw: str,
    surface_server: AttackSurfaceServer,
    round_no: int,
) -> tuple[str, dict[str, Any]]:
    import json
    raw = raw.strip().strip("`").strip()
    try:
        data = json.loads(raw)
        action = data.get("action", AUDIT_VULNERABILITY)
        if action not in REGULATOR_ACTIONS:
            action = AUDIT_VULNERABILITY
        payload = _build_payload(action, data, surface_server, round_no)
        return action, payload
    except Exception:
        action = AUDIT_VULNERABILITY
        return action, _fallback_payload(action, surface_server, round_no)


def _build_payload(
    action: str,
    data: dict[str, Any],
    surface_server: AttackSurfaceServer,
    round_no: int,
) -> dict[str, Any]:
    exploited_cves = [step.cve_id for step in surface_server.chain_steps]
    cve_id = data.get("cve_id") or (random.choice(exploited_cves) if exploited_cves else "")

    if action == AUDIT_VULNERABILITY:
        return {"cve_id": cve_id}
    if action == ISSUE_COMPLIANCE_FINDING:
        framework = data.get("framework") or random.choice(_FRAMEWORKS)
        if framework not in VALID_FRAMEWORKS:
            framework = "CRA"
        severity = data.get("severity") or random.choice(_SEVERITIES)
        if severity not in VALID_SEVERITIES:
            severity = "medium"
        return {
            "cve_id": cve_id,
            "framework": framework,
            "requirement_key": data.get("requirement_key") or random.choice(REQUIREMENT_KEYS),
            "description": data.get("description", f"Compliance gap detected at round {round_no}"),
            "severity": severity,
            "round_no": round_no,
        }
    if action == APPROVE_EXCEPTION:
        return {"cve_id": cve_id}
    return {}


def _fallback_payload(
    action: str,
    surface_server: AttackSurfaceServer,
    round_no: int,
) -> dict[str, Any]:
    exploited_cves = [step.cve_id for step in surface_server.chain_steps]
    cve_id = random.choice(exploited_cves) if exploited_cves else ""
    if action == ISSUE_COMPLIANCE_FINDING:
        return {
            "cve_id": cve_id,
            "framework": "CRA",
            "requirement_key": "CRA_art_24",
            "description": f"Automated compliance gap: round {round_no}",
            "severity": "medium",
            "round_no": round_no,
        }
    return {"cve_id": cve_id}


def _get_profile(config: dict[str, Any], agent_type: str) -> dict[str, Any]:
    for p in config.get("agent_profiles", []):
        if p.get("agent_type") == agent_type:
            return p
    return {}
