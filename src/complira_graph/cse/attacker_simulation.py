"""
complira_graph.cse.attacker_simulation
=========================================
Attacker agent loop for CSE simulation (subprocess side).

Runs for total_rounds, selecting one cybersecurity attack action per round
using a lightweight LLM call, then applying it to AttackSurfaceServer.
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
    SCAN_SURFACE, EXPLOIT_CVE, LATERAL_MOVE,
    ESCALATE_PRIVILEGES, PIVOT_TARGET,
)
from complira_graph.cse.memory_updater import CyberAgentActivity, CyberMemoryUpdater

log = logging.getLogger(__name__)

ATTACKER_ACTIONS = [SCAN_SURFACE, EXPLOIT_CVE, LATERAL_MOVE, ESCALATE_PRIVILEGES, PIVOT_TARGET]


async def run_attacker_loop(
    config: dict[str, Any],
    surface_server: AttackSurfaceServer,
    logger: CyberActionLogger,
    memory: CyberMemoryUpdater,
    ipc_handler: Any,
) -> None:
    """Attacker coroutine — runs total_rounds, one action per round."""
    total_rounds: int = config["total_rounds"]
    agent_id = "attacker_0"
    agent_type = "Attacker"
    profile = _get_profile(config, agent_type)

    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    for round_no in range(1, total_rounds + 1):
        # Respect pause flag
        while ipc_handler.pause_requested:
            await asyncio.sleep(0.2)
        if ipc_handler.stop_requested:
            break

        try:
            action_type, payload = await _decide_action(
                client, settings.ANTHROPIC_MODEL_HAIKU,
                round_no, surface_server, profile, config,
            )
        except Exception as exc:
            log.warning("cse_attacker_decide_error", round_no=round_no, error=str(exc))
            action_type = SCAN_SURFACE
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
            target=payload.get("cve_id", payload.get("target_component", "")),
            outcome=result.outcome,
            episode_text=episode,
        ))

        await asyncio.sleep(0)  # yield to defender + IPC poller


async def _decide_action(
    client: anthropic.Anthropic,
    model: str,
    round_no: int,
    surface_server: AttackSurfaceServer,
    profile: dict[str, Any],
    config: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Use LLM to pick attacker action; fallback to heuristic on error."""
    exploitable = surface_server.get_exploitable_cves()

    if not exploitable:
        return SCAN_SURFACE, {}

    prompt = (
        f"Round {round_no}/{config['total_rounds']}. "
        f"Exploitable CVEs: {exploitable[:5]}. "
        f"Chain steps so far: {len(surface_server.chain_steps)}. "
        f"Your role: {profile.get('role', 'attacker')}. "
        "Choose ONE action from: SCAN_SURFACE, EXPLOIT_CVE, LATERAL_MOVE, ESCALATE_PRIVILEGES, PIVOT_TARGET. "
        "If EXPLOIT_CVE, also choose a cve_id from the exploitable list. "
        "Reply with JSON only: {\"action\": \"ACTION_NAME\", \"cve_id\": \"CVE-...\"}. "
        "If action does not need cve_id, omit it."
    )

    response = await asyncio.to_thread(
        client.messages.create,
        model=model,
        max_tokens=128,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_action_response(response.content[0].text, exploitable)


def _parse_action_response(raw: str, exploitable: list[str]) -> tuple[str, dict[str, Any]]:
    import json
    raw = raw.strip().strip("`").strip()
    try:
        data = json.loads(raw)
        action = data.get("action", SCAN_SURFACE)
        if action not in ATTACKER_ACTIONS:
            action = SCAN_SURFACE
        payload: dict[str, Any] = {}
        if action == EXPLOIT_CVE and exploitable:
            cve_id = data.get("cve_id", random.choice(exploitable))
            if cve_id not in exploitable:
                cve_id = random.choice(exploitable)
            payload = {"cve_id": cve_id, "technique": "T1190", "agent_id": "attacker_0"}
        elif action == LATERAL_MOVE:
            payload = {"target_component": data.get("target_component", "unknown")}
        return action, payload
    except Exception:
        if exploitable:
            return EXPLOIT_CVE, {"cve_id": random.choice(exploitable), "technique": "T1190", "agent_id": "attacker_0"}
        return SCAN_SURFACE, {}


def _get_profile(config: dict[str, Any], agent_type: str) -> dict[str, Any]:
    for p in config.get("agent_profiles", []):
        if p.get("agent_type") == agent_type:
            return p
    return {}
