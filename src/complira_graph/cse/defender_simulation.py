"""
complira_graph.cse.defender_simulation
=========================================
Defender agent loop for CSE simulation (subprocess side).

Runs SOCAnalyst + DevSecOps + CISO + Regulator in a single coroutine
(one defender action per round, role chosen by LLM based on game state).
"""

from __future__ import annotations

import asyncio
import logging
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

log = logging.getLogger(__name__)

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

        try:
            action_type, payload = await _decide_defender_action(
                client, settings.ANTHROPIC_MODEL_HAIKU,
                round_no, cra_deadline_round, surface_server, profile, config,
            )
        except Exception as exc:
            log.warning("cse_defender_decide_error", round_no=round_no, error=str(exc))
            action_type = MONITOR
            payload = {}

        result = surface_server.apply_action(action_type, payload, round_no)
        logger.log_action(action_type, agent_id, agent_type, payload, result.outcome, round_no, result.significance)

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


async def _decide_defender_action(
    client: anthropic.Anthropic,
    model: str,
    round_no: int,
    cra_deadline_round: int,
    surface_server: AttackSurfaceServer,
    profile: dict[str, Any],
    config: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    state = surface_server.get_state_snapshot()
    exploitable = surface_server.get_exploitable_cves()

    prompt = (
        f"Round {round_no}/{config['total_rounds']}. "
        f"CRA deadline at round {cra_deadline_round}. "
        f"Exploitable CVEs: {exploitable[:5]}. "
        f"Chain steps detected: {state['chain_step_count']}. "
        f"CISO alerted: {state['ciso_alerted']}. "
        f"CRA notified: {state['cra_notified']}. "
        f"Controls deployed: {len(state['controls_deployed'])}. "
        f"Your role: {profile.get('role', 'defender')}. "
        "Choose ONE defensive action: MONITOR, DETECT, INVESTIGATE, ESCALATE_TO_CISO, "
        "PATCH, DEPLOY_CONTROL, ROTATE_CREDENTIAL, FILE_CRA_NOTIFICATION, NOTIFY_BOARD, ACKNOWLEDGE. "
        "If PATCH or INVESTIGATE, include a cve_id. "
        "Reply JSON only: {\"action\": \"ACTION_NAME\", \"cve_id\": \"CVE-...\"}."
    )

    response = await asyncio.to_thread(
        client.messages.create,
        model=model,
        max_tokens=128,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_defender_response(response.content[0].text, exploitable, round_no, cra_deadline_round, state)


def _parse_defender_response(
    raw: str,
    exploitable: list[str],
    round_no: int,
    cra_deadline: int,
    state: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    import json
    raw = raw.strip().strip("`").strip()
    try:
        data = json.loads(raw)
        action = data.get("action", MONITOR)
        if action not in DEFENDER_ACTIONS:
            action = MONITOR
        payload: dict[str, Any] = {}
        if action in (PATCH, INVESTIGATE, DETECT, ACKNOWLEDGE) and exploitable:
            cve_id = data.get("cve_id", random.choice(exploitable))
            payload = {"cve_id": cve_id}
        elif action == DEPLOY_CONTROL:
            payload = {"control_id": data.get("control_id", f"ctrl_{round_no}")}
        return action, payload
    except Exception:
        # Heuristic fallback based on game state
        if state["chain_step_count"] > 0 and not state["ciso_alerted"]:
            return ESCALATE_TO_CISO, {}
        if round_no >= cra_deadline - 2 and not state["cra_notified"]:
            return FILE_CRA_NOTIFICATION, {}
        if exploitable:
            return PATCH, {"cve_id": random.choice(exploitable)}
        return MONITOR, {}


def _get_profile(config: dict[str, Any], agent_type: str) -> dict[str, Any]:
    for p in config.get("agent_profiles", []):
        if p.get("agent_type") == agent_type:
            return p
    return {}
