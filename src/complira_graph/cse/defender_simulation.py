"""
complira_graph.cse.defender_simulation
=========================================
Defender agent loop for CSE simulation (subprocess side).

Runs SOCAnalyst + DevSecOps + CISO + Regulator in a single coroutine
(one defender action per round, role chosen by LLM based on game state).
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
    MONITOR, DETECT, INVESTIGATE, ESCALATE_TO_CISO,
    PATCH, DEPLOY_CONTROL, ROTATE_CREDENTIAL,
    FILE_CRA_NOTIFICATION, NOTIFY_BOARD, ACKNOWLEDGE,
)
from complira_graph.cse.memory_updater import CyberAgentActivity, CyberMemoryUpdater

log = structlog.get_logger(__name__)

DEFENDER_ACTIONS = [
    MONITOR, DETECT, INVESTIGATE, ESCALATE_TO_CISO,
    PATCH, DEPLOY_CONTROL, ROTATE_CREDENTIAL,
    FILE_CRA_NOTIFICATION, NOTIFY_BOARD, ACKNOWLEDGE,
]


async def run_defender_loop(
    config: dict[str, Any],
    surface_server: AttackSurfaceServer,
    logger: CyberActionLogger,
    memory: CyberMemoryUpdater,
    ipc_handler: Any,
) -> None:
    """Defender coroutine — runs total_rounds, one action per round."""
    total_rounds: int = config["total_rounds"]
    cra_deadline_round: int = config.get("cra_deadline_round", 24)
    agent_id = "defender_0"
    agent_type = "SOCAnalyst"

    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    profile = _get_profile(config, agent_type)

    for round_no in range(1, total_rounds + 1):
        while ipc_handler.pause_requested:
            await asyncio.sleep(0.2)
        if ipc_handler.stop_requested:
            break

        # F-007: snapshot BEFORE decision
        game_state = surface_server.get_state_snapshot()

        action_type, payload, decision_source, reasoning = await _decide_defender_action(
            client, settings.ANTHROPIC_MODEL_HAIKU,
            round_no, cra_deadline_round, surface_server, profile, config, game_state,
        )

        result = surface_server.apply_action(action_type, payload, round_no)
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
            target=payload.get("cve_id", ""),
            outcome=result.outcome,
            episode_text=episode,
        ))

        await asyncio.sleep(0)  # yield to attacker + IPC poller


_MAX_LLM_ATTEMPTS = 3
_LLM_BACKOFF_BASE  = 0.5


async def _decide_defender_action(
    client: anthropic.Anthropic,
    model: str,
    round_no: int,
    cra_deadline_round: int,
    surface_server: AttackSurfaceServer,
    profile: dict[str, Any],
    config: dict[str, Any],
    game_state: dict[str, Any],
) -> tuple[str, dict[str, Any], str, str]:
    """
    Returns (action_type, payload, decision_source, reasoning).
    C-06: 3 LLM attempts with backoff → aligned heuristic fallback.
    """
    exploitable = surface_server.get_exploitable_cves()

    prompt = (
        f"Round {round_no}/{config['total_rounds']}. "
        f"CRA deadline at round {cra_deadline_round}. "
        f"Exploitable CVEs: {exploitable[:5]}. "
        f"CVEs in attack chain: {[s.cve_id for s in surface_server.chain_steps[:5]]}. "
        f"Chain steps detected: {game_state['chain_step_count']}. "
        f"CISO alerted: {game_state['ciso_alerted']}. "
        f"CRA notified: {game_state['cra_notified']}. "
        f"Controls deployed: {len(game_state['controls_deployed'])}. "
        f"Your role: {profile.get('role', 'defender')}. "
        "Choose ONE defensive action: MONITOR, DETECT, INVESTIGATE, ESCALATE_TO_CISO, "
        "PATCH, DEPLOY_CONTROL, ROTATE_CREDENTIAL, FILE_CRA_NOTIFICATION, NOTIFY_BOARD, ACKNOWLEDGE. "
        "Prioritise patching CVEs that are in the attack chain. "
        "If PATCH or INVESTIGATE, include a cve_id from the chain or exploitable list. "
        'Reply JSON only: {"action": "ACTION_NAME", "cve_id": "CVE-..."}.'
    )

    for attempt in range(_MAX_LLM_ATTEMPTS):
        try:
            response = await asyncio.to_thread(
                client.messages.create,
                model=model,
                max_tokens=128,
                messages=[{"role": "user", "content": prompt}],
            )
            action, payload = _parse_defender_response(
                response.content[0].text, exploitable, round_no, cra_deadline_round, game_state, surface_server
            )
            reasoning = f"llm_chose_{action}"
            if action == PATCH:
                reasoning = f"LLM chose PATCH({payload.get('cve_id','')}): chain_steps={game_state['chain_step_count']}"
            return action, payload, "llm", reasoning
        except anthropic.RateLimitError:
            wait = _LLM_BACKOFF_BASE * (2 ** attempt)
            log.warning("cse_defender_rate_limit", round_no=round_no, attempt=attempt, wait=wait)
            await asyncio.sleep(wait)
        except Exception as exc:
            log.warning("cse_defender_llm_error", round_no=round_no, attempt=attempt, error=str(exc))

    # C-06: aligned heuristic fallback
    action, payload, reasoning = _heuristic_defender(surface_server, exploitable, round_no, cra_deadline_round, game_state)
    return action, payload, "heuristic", reasoning


def _heuristic_defender(
    surface_server: AttackSurfaceServer,
    exploitable: list[str],
    round_no: int,
    cra_deadline: int,
    state: dict[str, Any],
) -> tuple[str, dict[str, Any], str]:
    """Aligned fallback — patches chain CVEs first (F-004 / H-4 fix)."""
    chain_cves = [s.cve_id for s in surface_server.chain_steps if s.cve_id in exploitable]

    if state["chain_step_count"] > 0 and not state["ciso_alerted"]:
        return ESCALATE_TO_CISO, {}, "heuristic_escalate_chain_detected"
    if round_no >= cra_deadline - 2 and not state["cra_notified"]:
        return FILE_CRA_NOTIFICATION, {}, "heuristic_cra_deadline"
    if chain_cves:
        return PATCH, {"cve_id": chain_cves[0]}, f"heuristic_patch_chain_cve({chain_cves[0]})"
    if exploitable:
        return PATCH, {"cve_id": exploitable[0]}, f"heuristic_patch_exploitable({exploitable[0]})"
    if not state["monitoring_active"]:
        return MONITOR, {}, "heuristic_activate_monitoring"
    return MONITOR, {}, "heuristic_default_monitor"


def _parse_defender_response(
    raw: str,
    exploitable: list[str],
    round_no: int,
    cra_deadline: int,
    state: dict[str, Any],
    surface_server: AttackSurfaceServer,
) -> tuple[str, dict[str, Any]]:
    import json
    raw = raw.strip().strip("`").strip()
    chain_cves = [s.cve_id for s in surface_server.chain_steps if s.cve_id in exploitable]
    try:
        data   = json.loads(raw)
        action = data.get("action", MONITOR)
        if action not in DEFENDER_ACTIONS:
            action = MONITOR
        payload: dict[str, Any] = {}
        if action in (PATCH, INVESTIGATE, DETECT, ACKNOWLEDGE):
            cve_id = data.get("cve_id")
            if not cve_id:
                # Prefer chain CVEs over random (H-4 fix)
                cve_id = chain_cves[0] if chain_cves else (exploitable[0] if exploitable else "")
            payload = {"cve_id": cve_id}
        elif action == DEPLOY_CONTROL:
            cve_id = data.get("cve_id", "")
            ctrl   = data.get("control_id", f"ctrl_{round_no}" + (f"_{cve_id}" if cve_id else ""))
            payload = {"control_id": ctrl, "cve_id": cve_id}
        return action, payload
    except Exception:
        action, payload, _ = _heuristic_defender(surface_server, exploitable, round_no, cra_deadline, state)
        return action, payload


def _get_profile(config: dict[str, Any], agent_type: str) -> dict[str, Any]:
    for p in config.get("agent_profiles", []):
        if p.get("agent_type") == agent_type:
            return p
    return {}
