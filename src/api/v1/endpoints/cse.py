"""
CSE simulation endpoints.

POST /v1/cse/simulations/create           — prepare + start a simulation run
GET  /v1/cse/simulations/{sim_id}/status  — poll live run state
GET  /v1/cse/simulations/{sim_id}/stream  — SSE stream of agent action events

Auth: JWT (web UI) or API key.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, AsyncGenerator

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from api.core.database import get_reference_db
from api.core.security import Customer, get_current_customer, api_key_header, oauth2_scheme, _DEV_CUSTOMER
from complira_graph.config import get_settings
from complira_graph.cse.simulation_manager import CyberSimulationManager
from complira_graph.queries.simulation_queries import get_attack_chain_findings_for_run
from complira_graph.queries.situation_abstraction_queries import get_latest_run_id

log = structlog.get_logger(__name__)
router = APIRouter()

_VALID_TRIGGER_TYPES = frozenset({"kev_triggered", "monthly_posture_sim"})


async def _get_customer_optional(
    api_key: str | None = Depends(api_key_header),
    token: str | None = Depends(oauth2_scheme),
) -> Customer | None:
    """Like get_current_customer but returns None instead of raising 401."""
    try:
        return await get_current_customer(api_key=api_key, token=token)
    except Exception:
        return None


def _resolve_tenant_id(sim_id: str, customer: Customer | None) -> str | None:
    """Return tenant_id from customer, or by searching the sim data dir on disk."""
    if customer:
        return customer._key
    settings = get_settings()
    matches = list(Path(settings.CSE_DATA_DIR).glob(f"*/{sim_id}"))
    if matches:
        return matches[0].parent.name
    return None

# ---------------------------------------------------------------------------
# SimulationRegistry — process-level mapping of sim_id → sim_dir
# Populated when a simulation is started; used by SSE endpoint for live tailing.
# TTL of 3600s; entries for completed runs cleaned up lazily.
# ---------------------------------------------------------------------------
_SIM_REGISTRY: dict[str, Path] = {}
_SIM_REGISTRY_TTL: dict[str, float] = {}  # sim_id → expiry time (monotonic)
_REGISTRY_TTL_S = 3600.0

_AQL_RUN_META = """
LET run = DOCUMENT(simulation_runs, @sim_id)
FILTER run != null AND run.tenant_id == @tenant_id

LET agent_output = FIRST(
  FOR ao IN business_impact_findings
    FILTER ao.run_id == @sim_id
    FILTER ao.agent_type == "board_member_agent"
    LIMIT 1
    RETURN ao
)

LET top_chain = FIRST(
  FOR chain IN attack_chain_findings
    FILTER chain.run_id == @sim_id
    SORT chain.confidence DESC
    LIMIT 1
    RETURN chain
)

LET playbook = (
  FOR ps IN simulation_playbook_steps
    FILTER ps.finding_key == CONCAT("cse_chain_", @sim_id)
    SORT ps.priority ASC
    LIMIT 3
    RETURN ps.action
)

RETURN {
  sim_id:           run._key,
  tenant_id:        run.tenant_id,
  status:           run.status,
  trigger_type:     run.trigger_type,
  started_at:       run.started_at,
  agent_count:      run.agent_count,
  chain_probability: top_chain ? top_chain.confidence : null,
  board_narrative:  agent_output ? agent_output.narrative : null,
  top_3_actions:    playbook
}
"""

_AQL_RECENT_EVENTS = """
FOR log IN agent_action_logs
  FILTER log.sim_id == @sim_id
  SORT log.round_no DESC
  LIMIT 20
  RETURN {
    round_no:    log.round_no,
    agent_type:  log.agent_type,
    action_type: log.action_type,
    outcome:     log.outcome
  }
"""


async def _run_complete_background(
    manager: CyberSimulationManager,
    sim_id: str,
    runner: Any,
) -> None:
    """Background coroutine: wait for simulation completion, run report, write back."""
    try:
        db = get_reference_db()
        await manager.complete(db, runner)
        log.info("cse_complete_background_done", sim_id=sim_id)
    except Exception as exc:
        log.error("cse_complete_background_error", sim_id=sim_id, error=str(exc))


@router.post("/cse/simulations/create")
async def create_cse_simulation(
    body: dict[str, Any],
    customer: Customer | None = Depends(_get_customer_optional),
) -> dict[str, Any]:
    """
    POST /v1/cse/simulations/create

    Prepares and starts a CSE simulation run for the authenticated tenant.
    Profile generation and config are built synchronously; the simulation
    subprocess runs in the background.

    Returns {"sim_id": str, "status": "running", "tenant_id": str}.

    Errors:
      422 — no exploitable attack surface found, or invalid trigger_type
      500 — internal preparation error
    """
    db = get_reference_db()
    resolved = customer or _DEV_CUSTOMER
    tenant_id = resolved._key
    trigger_type = body.get("trigger_type", "kev_triggered")
    total_rounds = body.get("total_rounds")
    if isinstance(total_rounds, int) and total_rounds > 0:
        total_rounds = min(total_rounds, 720)  # cap at 720
    else:
        total_rounds = None  # let config_generator use its default

    if trigger_type not in _VALID_TRIGGER_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"invalid_trigger_type: must be one of {sorted(_VALID_TRIGGER_TYPES)}",
        )

    manager = CyberSimulationManager()
    try:
        sim_id, runner = await manager.prepare(db, tenant_id, trigger_type, total_rounds=total_rounds)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        log.error("cse_prepare_error", tenant_id=tenant_id, error=str(exc))
        raise HTTPException(status_code=500, detail="simulation_prepare_failed") from exc

    manager.start(runner)

    # Register sim_dir for SSE endpoint before starting background task
    _SIM_REGISTRY[sim_id] = runner.sim_dir
    _SIM_REGISTRY_TTL[sim_id] = time.monotonic() + _REGISTRY_TTL_S

    # Schedule completion handler — waits for subprocess, runs report agent, write-back
    asyncio.create_task(
        _run_complete_background(manager, sim_id, runner),
        name=f"cse_complete_{sim_id}",
    )

    log.info("cse_simulation_created", sim_id=sim_id, tenant_id=tenant_id, trigger_type=trigger_type)
    return {"sim_id": sim_id, "status": "running", "tenant_id": tenant_id}


@router.get("/cse/simulations/{sim_id}/status")
async def get_cse_simulation_status(
    sim_id: str,
    customer: Customer | None = Depends(_get_customer_optional),
) -> dict[str, Any]:
    """
    GET /v1/cse/simulations/{sim_id}/status

    Returns current CSE run state for the authenticated tenant.
    Includes board narrative and top actions when the run is completed.

    Returns 404 if the run does not exist or belongs to a different tenant.
    Designed for 3-second polling from SimulationLivePanel.
    """
    db = get_reference_db()
    tenant_id = _resolve_tenant_id(sim_id, customer)
    if tenant_id is None:
        raise HTTPException(status_code=404, detail=f"Simulation run '{sim_id}' not found")

    cursor = db.aql.execute(
        _AQL_RUN_META,
        bind_vars={"sim_id": sim_id, "tenant_id": tenant_id},
    )
    rows = list(cursor)

    # Build result from DB row or synthesise from disk when DB row missing
    if rows and rows[0] is not None:
        result: dict[str, Any] = rows[0]
    else:
        # Sim not in DB yet (in-progress) — synthesise only if sim_dir exists on disk
        settings = get_settings()
        disk_matches = list(Path(settings.CSE_DATA_DIR).glob(f"*/{sim_id}"))
        if not disk_matches:
            raise HTTPException(status_code=404, detail=f"Simulation run '{sim_id}' not found")
        result = {"sim_id": sim_id, "tenant_id": tenant_id, "status": "running",
                  "trigger_type": None, "started_at": None, "agent_count": None,
                  "chain_probability": None, "board_narrative": None, "top_3_actions": []}

    # Fetch recent events
    try:
        events_cursor = db.aql.execute(_AQL_RECENT_EVENTS, bind_vars={"sim_id": sim_id})
        result["recent_events"] = list(events_cursor)
    except Exception as exc:
        log.warning("cse_status_events_error", sim_id=sim_id, error=str(exc))
        result["recent_events"] = []

    # Read current_round / total_rounds from run_state.json
    result["current_round"] = None
    result["total_rounds"] = None
    try:
        settings = get_settings()
        state_path = Path(settings.CSE_DATA_DIR) / tenant_id / sim_id / "run_state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            result["current_round"] = state.get("current_round")
            result["total_rounds"] = state.get("total_rounds")
            if not result.get("status"):
                result["status"] = state.get("status", "running")
    except Exception:
        pass

    log.info(
        "cse_status_polled",
        sim_id=sim_id,
        tenant_id=tenant_id,
        status=result.get("status"),
    )
    return result


@router.get("/cse/simulations/chains")
async def get_latest_chains(
    customer: Customer = Depends(get_current_customer),
) -> dict[str, Any]:
    """
    GET /v1/cse/simulations/chains

    Returns attack chain findings (with chain_nodes + chain_edges) from the
    most recently completed simulation run for the authenticated tenant.

    Returns {"run_id": str | null, "chains": [...]} — never 404.
    """
    db = get_reference_db()
    tenant_id = customer._key
    run_id = get_latest_run_id(db, tenant_id)
    if run_id is None:
        return {"run_id": None, "chains": []}
    chains = get_attack_chain_findings_for_run(db, tenant_id, run_id)
    return {"run_id": run_id, "chains": chains}


@router.get("/cse/simulations/{sim_id}/stream")
async def stream_cse_simulation(
    sim_id: str,
    request: Request,
    token: str | None = None,  # query-param token (EventSource can't set headers)
) -> StreamingResponse:
    """
    GET /v1/cse/simulations/{sim_id}/stream

    SSE stream of agent action events for the given simulation run.

    Tails cyber_actions.jsonl in real time while the simulation is running.
    Falls back to ArangoDB agent_action_logs for already-completed runs.

    Events:
      data: {"round_no": N, "agent_type": "...", "action_type": "...", "outcome": "...", "significance": 0.8}
      event: done\\ndata: {}   (on COMPLETED or FAILED status)

    Returns 404 if simulation is not found.
    """
    _purge_expired_registry()

    # 1. Check in-memory registry (active run in this process)
    sim_dir = _SIM_REGISTRY.get(sim_id)

    # 2. Recover from disk (handles backend restart mid-sim — search all tenant dirs)
    if sim_dir is None:
        settings = get_settings()
        matches = list(Path(settings.CSE_DATA_DIR).glob(f"*/{sim_id}"))
        if matches:
            sim_dir = matches[0]
            _SIM_REGISTRY[sim_id] = sim_dir
            log.info("cse_stream_recovered_from_disk", sim_id=sim_id, sim_dir=str(sim_dir))

    if sim_dir is not None:
        return StreamingResponse(
            _stream_from_jsonl(sim_id, sim_dir, request),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # 3. Fallback: completed run — pre-fetch events to avoid 404 inside StreamingResponse
    # (HTTPException raised inside an async generator doesn't propagate as HTTP 404)
    db = get_reference_db()
    _AQL_ALL = """
    FOR e IN agent_action_logs
      FILTER e.sim_id == @sim_id
      SORT e.round_no ASC, e._key ASC
      RETURN {round_no: e.round_no, agent_type: e.agent_type,
              action_type: e.action_type, outcome: e.outcome,
              significance: e.significance, timestamp: e.timestamp}
    """
    try:
        events = list(db.aql.execute(_AQL_ALL, bind_vars={"sim_id": sim_id}))
    except Exception as exc:
        log.error("cse_stream_arango_prefetch_error", sim_id=sim_id, error=str(exc))
        events = []
    if not events:
        raise HTTPException(status_code=404, detail=f"Simulation '{sim_id}' not found")
    return StreamingResponse(
        _stream_events_list(events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream_from_jsonl(
    sim_id: str,
    sim_dir: Path,
    request: Request,
) -> AsyncGenerator[str, None]:
    """Tail cyber_actions.jsonl and emit SSE events until run completes."""
    jsonl_path = sim_dir / "cyber_actions.jsonl"
    byte_offset = 0
    _SSE_POLL_INTERVAL = 0.5
    _SAFETY_TIMEOUT_S = 300.0
    start_time = time.monotonic()

    while True:
        # Check client disconnected
        if await request.is_disconnected():
            return

        # Safety timeout
        if time.monotonic() - start_time > _SAFETY_TIMEOUT_S:
            yield "event: done\ndata: {\"status\": \"timeout\"}\n\n"
            return

        # Read new JSONL lines since last poll
        if jsonl_path.exists():
            try:
                with open(jsonl_path, "rb") as f:
                    f.seek(byte_offset)
                    new_bytes = f.read()
                    byte_offset += len(new_bytes)

                for line in new_bytes.decode("utf-8", errors="replace").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if entry.get("type") == "action":
                        event_payload = {
                            "round_no":    entry.get("round_no"),
                            "agent_type":  entry.get("agent_type"),
                            "action_type": entry.get("action_type"),
                            "outcome":     entry.get("outcome"),
                            "significance": entry.get("significance"),
                            "timestamp":   entry.get("timestamp"),
                        }
                        yield f"data: {json.dumps(event_payload)}\n\n"
            except Exception as exc:
                log.warning("cse_stream_jsonl_read_error", sim_id=sim_id, error=str(exc))

        # Check run state for terminal condition
        run_state = _read_run_state_file(sim_dir)
        if run_state and run_state.get("status") in ("completed", "failed"):
            yield "event: done\ndata: {}\n\n"
            return

        await asyncio.sleep(_SSE_POLL_INTERVAL)


async def _stream_events_list(events: list[dict]) -> AsyncGenerator[str, None]:
    """Emit pre-fetched event list as SSE, then done. Used by the fallback stream path."""
    for event in events:
        yield f"data: {json.dumps(event)}\n\n"
    yield "event: done\ndata: {}\n\n"


async def _stream_from_arango(
    sim_id: str,
    tenant_id: str,
    db: Any,
) -> AsyncGenerator[str, None]:
    """Emit all stored events from ArangoDB for a completed run, then done."""
    _AQL_ALL_EVENTS = """
    FOR e IN agent_action_logs
      FILTER e.sim_id == @sim_id
      SORT e.round_no ASC, e._key ASC
      RETURN {
        round_no:    e.round_no,
        agent_type:  e.agent_type,
        action_type: e.action_type,
        outcome:     e.outcome,
        significance: e.significance,
        timestamp:   e.timestamp
      }
    """
    try:
        cursor = db.aql.execute(_AQL_ALL_EVENTS, bind_vars={"sim_id": sim_id})
        events = list(cursor)
    except Exception as exc:
        log.error("cse_stream_arango_error", sim_id=sim_id, error=str(exc))
        raise HTTPException(status_code=404, detail=f"Simulation '{sim_id}' not found") from exc

    if not events:
        raise HTTPException(status_code=404, detail=f"Simulation '{sim_id}' not found")

    for event in events:
        yield f"data: {json.dumps(event)}\n\n"

    yield "event: done\ndata: {}\n\n"


def _read_run_state_file(sim_dir: Path) -> dict[str, Any] | None:
    try:
        return json.loads((sim_dir / "run_state.json").read_text(encoding="utf-8"))
    except Exception:
        return None


def _purge_expired_registry() -> None:
    """Remove expired entries from _SIM_REGISTRY (lazy TTL cleanup)."""
    now = time.monotonic()
    expired = [k for k, exp in _SIM_REGISTRY_TTL.items() if now > exp]
    for k in expired:
        _SIM_REGISTRY.pop(k, None)
        _SIM_REGISTRY_TTL.pop(k, None)
