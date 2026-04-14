"""
complira_graph.cse.run_parallel_cyber_simulation
==================================================
Subprocess entry point for CSE simulation.

Launched by CyberSimulationRunner via:
  sys.executable -m complira_graph.cse.run_parallel_cyber_simulation
      --sim-dir /path/to/data/simulations/{tenant}/{sim_id}
      --config  /path/to/.../simulation_config.json

Runs three asyncio tasks concurrently:
  1. run_attacker_loop  — attacker agent actions
  2. run_defender_loop  — defender agent actions
  3. CyberIPCHandler.poll_commands — IPC dispatch

After total_rounds complete, enters debrief loop (polls DEBRIEF_AGENT/CLOSE_ENV)
until main process sends CLOSE_ENV.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from complira_graph.cse.action_logger import CyberActionLogger
from complira_graph.cse.attack_surface_server import AttackSurfaceServer
from complira_graph.cse.attacker_simulation import run_attacker_loop
from complira_graph.cse.defender_simulation import run_defender_loop
from complira_graph.cse.ipc import CyberIPCHandler
from complira_graph.cse.memory_updater import CyberMemoryUpdater

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger(__name__)


async def main(sim_dir: Path, config_path: Path) -> None:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    sim_id = config["sim_id"]
    log.info("cse_subprocess_start", sim_id=sim_id, total_rounds=config["total_rounds"])

    ipc_handler = CyberIPCHandler(sim_dir)
    surface_server = AttackSurfaceServer(config.get("entities", []))
    logger = CyberActionLogger(sim_dir)
    memory = CyberMemoryUpdater(sim_dir)

    logger.log_simulation_start(
        sim_id=sim_id,
        tenant_id=config["tenant_id"],
        total_rounds=config["total_rounds"],
        trigger_type=config["trigger_type"],
    )

    try:
        await asyncio.gather(
            run_attacker_loop(config, surface_server, logger, memory, ipc_handler),
            run_defender_loop(config, surface_server, logger, memory, ipc_handler),
            ipc_handler.poll_commands(),
        )
    except Exception as exc:
        log.error("cse_simulation_error", sim_id=sim_id, error=str(exc))
        _write_state(sim_dir, sim_id, "failed", config["total_rounds"], config["total_rounds"])
        memory.flush_remaining()
        logger.close()
        sys.exit(1)

    # Flush memory to SQLite (ArangoDB flush happens in main process via simulation_manager)
    memory.flush_remaining()
    logger.close()

    _write_state(sim_dir, sim_id, "completed", config["total_rounds"], config["total_rounds"])
    log.info("cse_subprocess_rounds_complete", sim_id=sim_id)

    # Debrief phase — stay alive for DEBRIEF_AGENT queries until CLOSE_ENV
    await _debrief_loop(ipc_handler)
    log.info("cse_subprocess_exit", sim_id=sim_id)


async def _debrief_loop(ipc_handler: CyberIPCHandler) -> None:
    """Poll IPC for DEBRIEF_AGENT / CLOSE_ENV after simulation rounds complete."""
    while not ipc_handler.stop_requested:
        try:
            ipc_handler._process_pending()
        except Exception as exc:
            log.error("cse_debrief_poll_error", error=str(exc))
        await asyncio.sleep(0.2)


def _write_state(sim_dir: Path, sim_id: str, status: str, current_round: int, total_rounds: int) -> None:
    from datetime import datetime, timezone
    state = {
        "sim_id": sim_id,
        "status": status,
        "current_round": current_round,
        "total_rounds": total_rounds,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        (sim_dir / "run_state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as exc:
        log.error("cse_write_state_error", error=str(exc))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CSE parallel simulation subprocess")
    parser.add_argument("--sim-dir", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    asyncio.run(main(args.sim_dir, args.config))
