# Investigation Notes — cse-demo-realtime-simulation

**Date:** 2026-04-15
**Scope:** Large
**Investigator:** Claude Sonnet 4.6

---

## Sources Consulted

| Source | Path / Reference |
|---|---|
| CSE commit | `git show 63f2807` (branch `codex/cse-simulation-engine`) |
| Attacker agent | `src/complira_graph/cse/attacker_simulation.py` |
| Defender agent | `src/complira_graph/cse/defender_simulation.py` |
| Simulation manager | `src/complira_graph/cse/simulation_manager.py` |
| Runner | `src/complira_graph/cse/runner.py` |
| IPC | `src/complira_graph/cse/ipc.py` |
| Action logger | `src/complira_graph/cse/action_logger.py` |
| Memory updater | `src/complira_graph/cse/memory_updater.py` |
| AttackSurfaceServer | `src/complira_graph/cse/attack_surface_server.py` |
| Parallel runner | `src/complira_graph/cse/run_parallel_cyber_simulation.py` |
| CSE API | `src/api/v1/endpoints/cse.py` |
| Simulation writeback | `src/complira_graph/simulation/writeback_service.py` |
| Situation abstraction | `src/complira_graph/situation/abstraction_layer.py` |
| Situation Room frontend | `frontend/app/dashboard/situation/page.tsx` |
| Simulation frontend | `frontend/app/dashboard/simulation/page.tsx` (via git show) |
| SimulationLivePanel | `frontend/components/situation/SimulationLivePanel.tsx` (via git show) |
| Existing simulation status endpoint | `src/api/v1/endpoints/simulation.py` |

---

## Key Findings

### 1. CSE Source Files Are on `codex/cse-simulation-engine`, Not Current Branch

The `src/complira_graph/cse/` directory only has `.pyc` cache files on the working branch. The full source (13 Python modules) lives on `codex/cse-simulation-engine` (commit `63f2807`). The new ticket branch was forked from that branch so all CSE source is available.

### 2. Agent Architecture — Two Concurrent Coroutines, Not Three

`run_parallel_cyber_simulation.py` runs `asyncio.gather(run_attacker_loop(...), run_defender_loop(...), ipc_poll_loop(...))`. There are **two agent coroutines** (Attacker, Defender) plus the IPC poller. No Regulator coroutine exists.

`defender_simulation.py` embeds regulatory actions (`FILE_CRA_NOTIFICATION`, `NOTIFY_BOARD`) inside the Defender loop but the role label is `"SOCAnalyst"`, not `"Regulator"`. This means:
- There is no distinct Regulator persona in the simulation game
- Regulatory compliance actions are handled opportunistically by the Defender, not by a dedicated regulatory actor

**Design implication**: Adding a `regulator_simulation.py` with its own LLM-driven loop and dedicated action set (AUDIT_VULNERABILITY, ISSUE_COMPLIANCE_FINDING, FILE_INCIDENT_REPORT, NOTIFY_REGULATOR, APPROVE_EXCEPTION) requires wiring a third coroutine into `run_parallel_cyber_simulation.py`.

### 3. AttackSurfaceServer Is Shared Mutable State

`AttackSurfaceServer` is passed to all coroutines. It tracks `chain_steps`, `ciso_alerted`, `cra_notified`, `controls_deployed`, `patched_cves`, etc. All writes go through `apply_action()`. The server uses no locking — this works because Python's GIL + `asyncio.sleep(0)` yield pattern ensures only one coroutine runs at a time.

**Regulator concurrency risk**: Adding a third coroutine is safe under the same pattern. The Regulator should call `apply_action()` with its actions, and the server needs to handle those new action types. New actions must be added to `_ACTION_HANDLERS` in `attack_surface_server.py`.

### 4. SSE Streaming Gap

The current status endpoint `GET /v1/cse/simulations/{sim_id}/status` (and the older `GET /v1/simulation/{run_id}/status`) returns a snapshot via polling. The frontend `SimulationLivePanel` polls every 3 seconds using `setInterval`.

For real-time streaming, need `GET /v1/cse/simulations/{sim_id}/stream` returning `Content-Type: text/event-stream`. This should poll `agent_action_logs` (or `cyber_agent_activities`) in a loop and emit new events as they appear.

**Important**: `agent_action_logs` is the table in the CSE write path (populated by `CyberActionLogger`). Each log entry has `sim_id`, `round_no`, `agent_type`, `action_type`, `outcome`, `significance`, `timestamp`.

### 5. Situation Room — Engineering and RegAffairs Are Fixture-Only

`situation/page.tsx` currently:
- **CISO**: calls `/v1/situation/ciso` → live data ✓
- **Board**: calls `/v1/situation/board` → live data ✓
- **Engineering**: uses `fixtureData.patch_priority` → fixture only ✗
- **RegAffairs**: uses `fixtureData.regulatory_deadlines` → fixture only ✗

Need two new API endpoints:
- `GET /v1/situation/engineering` → derives patch priority from `attack_chain_findings` + CVE EPSS/KEV/CVSS data
- `GET /v1/situation/reg_affairs` → derives regulatory deadlines from `compliance_gap_findings` written by the Regulator agent

### 6. CyberActionLogger Writes to `cyber_agent_activities` (SQLite), Not ArangoDB

Investigation of `action_logger.py` reveals it writes to a **SQLite** database (per-simulation temp file), not directly to ArangoDB. The `CyberMemoryUpdater` also uses SQLite for episodic memory. These are subprocess-side ephemeral stores.

The ArangoDB `agent_action_logs` collection is populated during **writeback** (SimulationWritebackService step 5), not in real time during the run.

**SSE design implication**: SSE cannot poll ArangoDB `agent_action_logs` during the run because writeback only happens after completion. For real-time streaming, the SSE must either:
  - **Option A**: Read from SQLite (the temp dir created by the runner) — possible but requires knowing the sim dir path
  - **Option B**: Use an in-memory asyncio Queue pushed by a hook in `CyberActionLogger` — requires the subprocess to communicate back to the API process
  - **Option C**: Write action events directly to ArangoDB in real time (not in batch at writeback) — adds DB writes per round but is the cleanest SSE source

**Recommended: Option C** — add a thin ArangoDB write in `CyberActionLogger.log_action()` using the reference DB for live SSE events. This is a minimal change to `action_logger.py` and uses the existing `agent_action_logs` collection (or a new `simulation_stream_events` collection). This makes the SSE endpoint a straightforward AQL poller.

Wait — let me reconsider. The action logger runs inside the **subprocess** (via `run_parallel_cyber_simulation.py`). The subprocess does not have the FastAPI database connection. The runner spawns a subprocess. So Option A (SQLite polling from the parent process) or Option B (in-memory queue via IPC) are more viable.

Actually, re-reading the runner: `CyberSimulationRunner` starts a subprocess that runs `run_parallel_cyber_simulation.py`. The parent process (`simulation_manager.py`) polls `runner.status`. The IPC uses Unix sockets or stdin/stdout.

The SSE endpoint lives in the parent API process. It needs live events from the simulation subprocess.

**Revised Option D**: The simulation runner already writes `CyberActionLogger` to SQLite. The SSE endpoint can tail the SQLite file from the parent process by polling `cyber_agent_activities` table (known sim_dir). This is viable.

**Revised Option E**: During writeback (step 5), batch-write all agent logs to `simulation_agent_logs` in ArangoDB. The SSE can poll this collection. For real-time, the agent logger writes to both SQLite (subprocess side) AND streams events via the existing IPC socket to the parent. The parent process maintains an asyncio Queue per sim_id. SSE reads from the Queue.

For a demo, the simplest approach: write events to ArangoDB incrementally (not at writeback batch). Change `CyberActionLogger` to write to ArangoDB directly during the simulation. Then SSE polls ArangoDB.

BUT: the subprocess doesn't have the DB. So:
- Change `run_parallel_cyber_simulation.py` to accept a DB connection (the manager already has it)
- Pass it to `CyberActionLogger`
- `CyberActionLogger` writes to ArangoDB `agent_action_logs` per-round
- SSE endpoint polls `agent_action_logs` for new entries after a cursor position

This is the cleanest approach. `simulation_manager.py` already connects to `db`. It passes `db` to the simulation subprocess. Wait — the subprocess doesn't share the parent's DB connection because it's a separate process.

Actually, let me re-read the runner. The `CyberSimulationRunner` calls `subprocess.Popen(["python3", "-m", "complira_graph.cse.run_parallel_cyber_simulation", ...])`. The subprocess starts a fresh Python interpreter. It would need to create its own DB connection.

For demo purposes: the cleanest approach is:
- `run_parallel_cyber_simulation.py` creates its own ArangoDB connection at startup (reads ARANGO_URL from env, same as the main process)
- `CyberActionLogger` is extended with an optional `db` parameter; when present, writes to `agent_action_logs` per round
- SSE endpoint polls `agent_action_logs` with AQL, ordering by `_key`, using offset-based pagination to stream new events

This adds ~1 DB write per round per agent. For a 48-round simulation with 3 agents = 144 writes = acceptable for demo.

**Final decision for SSE**: Option C (real-time ArangoDB writes from subprocess, SSE polls ArangoDB).

### 7. Simulation Manager → Subprocess Communication

The `CyberSimulationManager.complete()` method calls `runner.wait_for_completion()`, then `report_agent.generate()`, then `SimulationWritebackService.run_all(payload)`. This is a blocking background task running in the FastAPI background task executor.

The subprocess writes to SQLite; the parent polls `runner.status`. The IPC socket is used for pause/stop commands only.

### 8. Frontend Architecture

- `simulation/page.tsx`: 4-step wizard (select → confirm → running → complete)
- Step "running": renders `<SimulationLivePanel sim_id={simId} onComplete={...} />`
- `SimulationLivePanel`: polls `GET /v1/cse/simulations/{sim_id}/status` every 3 seconds
- For SSE: replace the `setInterval` with `EventSource(streamUrl)`

### 9. Regulator Actions — AttackSurfaceServer

Current action handlers in `attack_surface_server.py`:
- Attacker: SCAN_SURFACE, EXPLOIT_CVE, LATERAL_MOVE, ESCALATE_PRIVILEGES, PIVOT_TARGET
- Defender: MONITOR, DETECT, INVESTIGATE, ESCALATE_TO_CISO, PATCH, DEPLOY_CONTROL, ROTATE_CREDENTIAL, FILE_CRA_NOTIFICATION, NOTIFY_BOARD, ACKNOWLEDGE

New Regulator actions needed:
- `AUDIT_VULNERABILITY` — triggers a compliance check on exploited CVEs
- `ISSUE_COMPLIANCE_FINDING` — records a gap in gap tracker
- `FILE_INCIDENT_REPORT` — marks an incident filed with the regulatory body
- `NOTIFY_REGULATOR` — marks external regulatory notification sent
- `APPROVE_EXCEPTION` — marks a risk exception for a known gap

These need handlers in `AttackSurfaceServer._ACTION_HANDLERS`.

---

## Constraints and Implications

| Constraint | Implication |
|---|---|
| Subprocess has no parent's DB connection | `action_logger.py` must create its own ArangoDB connection for incremental writes |
| No locking in AttackSurfaceServer | Third coroutine is safe under asyncio GIL + yield pattern |
| SSE must work for already-completed runs | SSE endpoint emits all stored events then `event: done` |
| Writeback service contract is frozen | Regulator outputs (gap findings) must map to existing payload fields |
| `compliance_gap_findings` already written by writeback | Regulator agent's findings are surfaced via existing AQL queries |

---

## Files and Modules to Add/Modify

| File | Change Type | Reason |
|---|---|---|
| `src/complira_graph/cse/regulator_simulation.py` | Add | New Regulator agent loop |
| `src/complira_graph/cse/attack_surface_server.py` | Modify | Add 5 Regulator action handlers |
| `src/complira_graph/cse/action_logger.py` | Modify | Optional ArangoDB write path for live SSE |
| `src/complira_graph/cse/run_parallel_cyber_simulation.py` | Modify | Wire third Regulator coroutine |
| `src/api/v1/endpoints/cse.py` | Modify | Add SSE streaming endpoint |
| `src/complira_graph/situation/abstraction_layer.py` | Modify | Add `compute_engineering()` and `compute_reg_affairs()` |
| `src/api/v1/endpoints/situation.py` | Modify | Add `/situation/engineering` and `/situation/reg_affairs` routes |
| `frontend/components/situation/SimulationLivePanel.tsx` | Modify | Switch from poll to SSE |
| `frontend/app/dashboard/situation/page.tsx` | Modify | Wire Engineering/RegAffairs to live API |
| `tests/unit/cse/test_regulator_simulation.py` | Add | Regulator agent unit tests |
| `tests/unit/cse/test_cse_api.py` | Modify | Add SSE scenario |

---

## Open Unknowns

| ID | Unknown | Impact |
|---|---|---|
| U-01 | Does `action_logger.py` already accept a DB parameter? | Low — needs reading |
| U-02 | Does `run_parallel_cyber_simulation.py` accept ArangoDB URL arg? | Medium — needs design decision |
| U-03 | Exactly how does `SimulationLivePanel` implement polling (setInterval, react-query, etc.)? | Low — needs reading |
| U-04 | What AQL indexes exist on `agent_action_logs`? | Low — SSE polling needs an index on `(sim_id, _key)` |
