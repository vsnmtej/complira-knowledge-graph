"""
CSE simulation endpoints.

POST /v1/cse/simulations/create       — prepare + start a simulation run
GET  /v1/cse/simulations/{sim_id}/status — poll live run state

Auth: JWT (web UI) or API key.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.core.database import get_reference_db
from api.core.security import Customer, get_current_customer
from complira_graph.config import get_settings
from complira_graph.cse.simulation_manager import CyberSimulationManager

log = logging.getLogger(__name__)
router = APIRouter()

_VALID_TRIGGER_TYPES = frozenset({"kev_triggered", "monthly_posture_sim"})

_AQL_RUN_META = """
LET run = DOCUMENT(simulation_runs, @sim_id)
FILTER run != null AND run.tenant_id == @tenant_id

LET agent_output = FIRST(
  FOR ao IN simulation_agent_outputs
    FILTER ao.run_id == @sim_id
    FILTER ao.agent_type == "CISO"
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
    customer: Customer = Depends(get_current_customer),
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
    tenant_id = customer._key
    trigger_type = body.get("trigger_type", "kev_triggered")

    if trigger_type not in _VALID_TRIGGER_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"invalid_trigger_type: must be one of {sorted(_VALID_TRIGGER_TYPES)}",
        )

    manager = CyberSimulationManager()
    try:
        sim_id, runner = await manager.prepare(db, tenant_id, trigger_type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        log.error("cse_prepare_error", tenant_id=tenant_id, error=str(exc))
        raise HTTPException(status_code=500, detail="simulation_prepare_failed") from exc

    manager.start(runner)

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
    customer: Customer = Depends(get_current_customer),
) -> dict[str, Any]:
    """
    GET /v1/cse/simulations/{sim_id}/status

    Returns current CSE run state for the authenticated tenant.
    Includes board narrative and top actions when the run is completed.

    Returns 404 if the run does not exist or belongs to a different tenant.
    Designed for 3-second polling from SimulationLivePanel.
    """
    db = get_reference_db()
    tenant_id = customer._key

    cursor = db.aql.execute(
        _AQL_RUN_META,
        bind_vars={"sim_id": sim_id, "tenant_id": tenant_id},
    )
    rows = list(cursor)
    if not rows or rows[0] is None:
        raise HTTPException(status_code=404, detail=f"Simulation run '{sim_id}' not found")

    result: dict[str, Any] = rows[0]

    # Fetch recent events
    try:
        events_cursor = db.aql.execute(_AQL_RECENT_EVENTS, bind_vars={"sim_id": sim_id})
        result["recent_events"] = list(events_cursor)
    except Exception as exc:
        log.warning("cse_status_events_error", sim_id=sim_id, error=str(exc))
        result["recent_events"] = []

    # Read current_round / total_rounds from run_state.json when available
    result["current_round"] = None
    result["total_rounds"] = None
    try:
        settings = get_settings()
        state_path = Path(settings.CSE_DATA_DIR) / tenant_id / sim_id / "run_state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            result["current_round"] = state.get("current_round")
            result["total_rounds"] = state.get("total_rounds")
    except Exception:
        pass

    log.info(
        "cse_status_polled",
        sim_id=sim_id,
        tenant_id=tenant_id,
        status=result.get("status"),
    )
    return result
