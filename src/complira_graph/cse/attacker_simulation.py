"""
complira_graph.cse.attacker_simulation
=========================================
Attacker agent loop for CSE simulation (subprocess side).

Runs for total_rounds, selecting one cybersecurity attack action per round
using a lightweight LLM call, then applying it to AttackSurfaceServer.

C-01: Technique resolved from entity_techniques in config (graph or fallback).
C-04: Action state machine — SCAN→EXPLOIT→LATERAL→ESCALATE→PIVOT with phase gates.
C-05: LLM retry (3 attempts with backoff) + structured heuristic fallback.
C-10: Scheduled events auto-fire before LLM decision each round.
"""

from __future__ import annotations

import asyncio
import random
import structlog
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

log = structlog.get_logger(__name__)

ATTACKER_ACTIONS = [SCAN_SURFACE, EXPLOIT_CVE, LATERAL_MOVE, ESCALATE_PRIVILEGES, PIVOT_TARGET]
_MAX_LLM_ATTEMPTS = 3
_LLM_BACKOFF_BASE  = 0.5  # seconds


async def run_attacker_loop(
    config: dict[str, Any],
    surface_server: AttackSurfaceServer,
    logger: CyberActionLogger,
    memory: CyberMemoryUpdater,
    ipc_handler: Any,
) -> None:
    """Attacker coroutine — runs total_rounds, one action per round."""
    total_rounds: int = config["total_rounds"]
    agent_id   = "attacker_0"
    agent_type = "Attacker"
    profile    = _get_profile(config, agent_type)
    entity_techniques: dict[str, list[str]] = config.get("entity_techniques", {})
    scheduled_events: list[dict[str, Any]]  = config.get("scheduled_events", [])

    settings = get_settings()
    client   = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    for round_no in range(1, total_rounds + 1):
        while ipc_handler.pause_requested:
            await asyncio.sleep(0.2)
        if ipc_handler.stop_requested:
            break

        # C-10: fire scheduled events BEFORE LLM decision
        for event in [e for e in scheduled_events if e.get("round") == round_no]:
            payload = {"cve_id": event.get("cve_id", ""), "technique": "T1190", "agent_id": agent_id}
            result  = surface_server.apply_action(event.get("action", EXPLOIT_CVE), payload, round_no)
            logger.log_action(
                event.get("action", EXPLOIT_CVE), agent_id, agent_type,
                payload, result.outcome, round_no, result.significance,
                decision_source="scheduled",
                decision_reasoning=f"Scheduled event: KEV CVE {event.get('cve_id', '')}",
            )

        # F-007: snapshot BEFORE decision
        game_state = surface_server.get_state_snapshot()
        available  = surface_server.get_available_attacker_actions()

        action_type, payload, decision_source, reasoning = await _decide_action(
            client, settings.ANTHROPIC_MODEL_HAIKU,
            round_no, surface_server, profile, config,
            available, entity_techniques, game_state,
        )

        result = surface_server.apply_action(action_type, payload, round_no)

        logger.log_action(
            action_type, agent_id, agent_type,
            payload, result.outcome, round_no, result.significance,
            decision_source=decision_source,
            decision_reasoning=reasoning,
            game_state_snapshot=game_state,
            technique_id=payload.get("technique"),
            technique_source=payload.get("technique_source"),
        )

        memory.record(CyberAgentActivity(
            sim_id=config["sim_id"],
            agent_id=agent_id,
            agent_type=agent_type,
            round_no=round_no,
            action_type=action_type,
            target=payload.get("cve_id", payload.get("target_component", "")),
            outcome=result.outcome,
            episode_text=f"Round {round_no}: {agent_type} executed {action_type}. {result.outcome}",
        ))

        await asyncio.sleep(0)  # yield to defender + IPC poller


async def _decide_action(
    client: anthropic.Anthropic,
    model: str,
    round_no: int,
    surface_server: AttackSurfaceServer,
    profile: dict[str, Any],
    config: dict[str, Any],
    available: list[str],
    entity_techniques: dict[str, list[str]],
    game_state: dict[str, Any],
) -> tuple[str, dict[str, Any], str, str]:
    """
    Returns (action_type, payload, decision_source, reasoning).
    C-05: 3 LLM attempts with backoff → heuristic fallback.
    """
    exploitable = surface_server.get_exploitable_cves()
    detected    = game_state.get("detected_cves", [])
    undetected  = game_state.get("undetected_exploitable", exploitable)

    if not exploitable:
        return SCAN_SURFACE, {}, "heuristic", "no_exploitable_cves_scan"

    prompt = (
        f"Round {round_no}/{config['total_rounds']}. "
        f"Attacker phase: {game_state.get('attacker_phase', 'recon')}. "
        f"Available actions THIS round: {available}. "
        f"Undetected exploitable CVEs (prefer these): {undetected[:5]}. "
        f"CVEs detected by SOC (risky to exploit): {detected[:3]}. "
        f"Chain steps so far: {game_state.get('chain_step_count', 0)}. "
        f"Your role: {profile.get('role', 'attacker')}. "
        "Choose ONE action from the available list only. "
        "If EXPLOIT_CVE, pick a CVE from undetected list when possible. "
        'Reply JSON only: {"action": "ACTION_NAME", "cve_id": "CVE-...", "target_component": "..."}. '
        "Omit irrelevant fields."
    )

    for attempt in range(_MAX_LLM_ATTEMPTS):
        try:
            response = await asyncio.to_thread(
                client.messages.create,
                model=model,
                max_tokens=128,
                messages=[{"role": "user", "content": prompt}],
            )
            action, payload = _parse_action_response(
                response.content[0].text, exploitable, undetected, available, entity_techniques
            )
            reasoning = f"llm_chose_{action}"
            if action == EXPLOIT_CVE:
                reasoning = (
                    f"LLM chose EXPLOIT_CVE({payload.get('cve_id','')}): "
                    f"phase={game_state.get('attacker_phase')}, "
                    f"chain_steps={game_state.get('chain_step_count',0)}"
                )
            return action, payload, "llm", reasoning
        except anthropic.RateLimitError:
            wait = _LLM_BACKOFF_BASE * (2 ** attempt)
            log.warning("cse_attacker_rate_limit", round_no=round_no, attempt=attempt, wait=wait)
            await asyncio.sleep(wait)
        except Exception as exc:
            log.warning("cse_attacker_llm_error", round_no=round_no, attempt=attempt, error=str(exc))

    # C-05: heuristic fallback
    surface_server.llm_failure_count += 1
    total = config["total_rounds"]
    if round_no > 5 and surface_server.llm_failure_count / round_no > 0.20:
        surface_server.simulation_degraded = True
        log.error("cse_attacker_degraded", failure_rate=surface_server.llm_failure_count / round_no)

    action, payload, reasoning = _heuristic_attacker(surface_server, available, undetected, entity_techniques, round_no)
    return action, payload, "heuristic", reasoning


def _heuristic_attacker(
    surface_server: AttackSurfaceServer,
    available: list[str],
    undetected: list[str],
    entity_techniques: dict[str, list[str]],
    round_no: int,
) -> tuple[str, dict[str, Any], str]:
    """Game-state-aware fallback — not a passive default."""
    exploitable = surface_server.get_exploitable_cves()

    if EXPLOIT_CVE in available and undetected:
        cve_id  = undetected[0]
        payload = _build_exploit_payload(cve_id, entity_techniques)
        return EXPLOIT_CVE, payload, f"heuristic_exploit_undetected({cve_id})"

    if EXPLOIT_CVE in available and exploitable:
        # Pick highest-risk CVE (KEV first, then first available)
        kev = [c for c in exploitable if c in surface_server.kev_cves]
        cve_id  = kev[0] if kev else exploitable[0]
        payload = _build_exploit_payload(cve_id, entity_techniques)
        return EXPLOIT_CVE, payload, f"heuristic_exploit_kev({cve_id})"

    if LATERAL_MOVE in available and surface_server.chain_steps:
        return LATERAL_MOVE, {"target_component": "unknown"}, "heuristic_lateral_post_exploit"

    if ESCALATE_PRIVILEGES in available and surface_server.reached_components:
        return ESCALATE_PRIVILEGES, {}, "heuristic_escalate_post_lateral"

    return SCAN_SURFACE, {}, "heuristic_scan_default"


def _build_exploit_payload(
    cve_id: str,
    entity_techniques: dict[str, list[str]],
) -> dict[str, Any]:
    techniques = entity_techniques.get(cve_id, ["T1190"])
    technique  = random.choice(techniques)
    source     = "graph" if cve_id in entity_techniques else "fallback"
    return {"cve_id": cve_id, "technique": technique, "technique_source": source, "agent_id": "attacker_0"}


def _parse_action_response(
    raw: str,
    exploitable: list[str],
    undetected: list[str],
    available: list[str],
    entity_techniques: dict[str, list[str]],
) -> tuple[str, dict[str, Any]]:
    import json
    raw = raw.strip().strip("`").strip()
    try:
        data   = json.loads(raw)
        action = data.get("action", SCAN_SURFACE)
        if action not in available:          # reject out-of-phase actions
            action = available[0]
        payload: dict[str, Any] = {}
        if action == EXPLOIT_CVE:
            preferred = undetected if undetected else exploitable
            cve_id    = data.get("cve_id") or (random.choice(preferred) if preferred else "")
            if cve_id not in exploitable:
                cve_id = random.choice(preferred) if preferred else ""
            payload = _build_exploit_payload(cve_id, entity_techniques)
        elif action == LATERAL_MOVE:
            payload = {"target_component": data.get("target_component", "unknown")}
        return action, payload
    except Exception:
        preferred = undetected if undetected else exploitable
        if EXPLOIT_CVE in available and preferred:
            cve_id = random.choice(preferred)
            return EXPLOIT_CVE, _build_exploit_payload(cve_id, entity_techniques)
        return available[0], {}


def _get_profile(config: dict[str, Any], agent_type: str) -> dict[str, Any]:
    for p in config.get("agent_profiles", []):
        if p.get("agent_type") == agent_type:
            return p
    return {}
