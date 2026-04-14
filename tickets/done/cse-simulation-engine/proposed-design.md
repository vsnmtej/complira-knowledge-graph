# Proposed Design — cse-simulation-engine

## Design Version

- Current Version: `v2`

## Revision History

| Version | Trigger | Summary Of Changes | Related Review Round |
| --- | --- | --- | --- |
| v1 | Initial draft | Full CSE package architecture, mirofish removal, schema addition, subprocess pattern, Next.js page, 2 new API endpoints | Round 1 |
| v2 | Round 1 Design Impact (F-001, F-002, F-003) | Added CSERunStatus TypeScript type; described subprocess debrief phase in runner.py + simulation_manager; updated C-019b to reference CSERunStatus; updated C-019c to remove cve_id from data shape | Round 2 |

## Artifact Basis

- Investigation Notes: `tickets/in-progress/cse-simulation-engine/investigation-notes.md`
- Requirements: `tickets/in-progress/cse-simulation-engine/requirements.md`
- Requirements Status: `Design-ready`

---

## Summary

Build the **Complira Simulation Engine (CSE)** as a new `src/complira_graph/cse/` Python package. CSE is a self-contained cybersecurity domain simulation: it extracts the tenant's attack surface from ArangoDB, generates agent profiles via Claude, runs a configurable multi-round parallel simulation (attacker loop + defender loop + IPC polling), logs actions to a per-run JSONL file and per-run SQLite, then feeds a ReACT report agent whose output is written back via `SimulationWritebackService`. Two new FastAPI endpoints replace the mirofish endpoints. A new Next.js page replaces the MiroFish Vue.js wizard. The existing `src/complira_graph/mirofish/` module and `/v1/mirofish/` endpoints are fully removed in this ticket.

---

## Goals

1. Deliver all 15 requirements (R-CSE-01 through R-CSE-15).
2. Replace `/v1/mirofish/trigger` + `/v1/mirofish/status/{run_id}` with `/v1/cse/simulations/create` + `/v1/cse/simulations/{sim_id}/status`.
3. Remove `src/complira_graph/mirofish/` module completely (no dead imports remain).
4. Add `agent_action_logs` ArangoDB collection to `scripts/init_simulation_schema.py`.
5. Keep frontend stack as Next.js (no Vue.js SPA).

---

## Legacy Removal Policy (Mandatory)

- Policy: `No backward compatibility; remove legacy code paths.`
- Required actions:
  - Delete `src/complira_graph/mirofish/trigger_client.py`, `seed_extractor.py`, `__init__.py`.
  - Delete `src/api/v1/endpoints/mirofish.py`.
  - Remove `mirofish` import and router registration from `src/api/v1/router.py`.
  - Update any tests that reference `mirofish` imports.

---

## Requirements And Use Cases

| Requirement ID | Description | Acceptance Criteria ID(s) | Acceptance Criteria Summary | Use Case IDs |
| --- | --- | --- | --- | --- |
| R-CSE-01 | Simulation lifecycle (8 states) | AC-CSE-01, AC-CSE-02 | RUNNING state + run_state.json; STOPPED on CLOSE_ENV | UC-CSE-01 |
| R-CSE-02 | IPC layer (file-based) | AC-CSE-03, AC-CSE-04 | INJECT_VARIABLE < 5s; unknown cmd → error, no crash | UC-CSE-02 |
| R-CSE-03 | Attack surface extraction | AC-CSE-05, AC-CSE-06 | ≥1 CyberEntityNode; < 200ms | UC-CSE-03 |
| R-CSE-04 | Agent profile generation (5 types) | AC-CSE-07 | 5 valid profiles from asyncio.gather | UC-CSE-04 |
| R-CSE-05 | Simulation config synthesis | AC-CSE-08 | sim_config.json with cra_deadline_round=24, total_rounds=48 | UC-CSE-05 |
| R-CSE-06 | Preparation pipeline | AC-CSE-09 | CREATED→READY writes run_state.json + sim_config.json | UC-CSE-06 |
| R-CSE-07 | Parallel simulation execution | AC-CSE-10 | 48 rounds complete; run_state.json status=completed | UC-CSE-07 |
| R-CSE-08 | 15-action cybersecurity action space | AC-CSE-11, AC-CSE-12 | PATCH removes CVE; EXPLOIT_CVE sets chain step | UC-CSE-08 |
| R-CSE-09 | Action logging (JSONL) | AC-CSE-13 | 100-round JSONL has all 15 action type strings | UC-CSE-09 |
| R-CSE-10 | Agent working memory (SQLite) | AC-CSE-14 | Batch of 5 activities flushed with episode_text | UC-CSE-10 |
| R-CSE-11 | Post-simulation report generation | AC-CSE-15 | Report has chain_probability + board_narrative in < 30s | UC-CSE-11 |
| R-CSE-12 | Write-back integration | AC-CSE-16, AC-CSE-17 | CISO posture_score updated; no CVE IDs in output | UC-CSE-12 |
| R-CSE-13 | CSE API endpoints | AC-CSE-18, AC-CSE-19 | POST /create returns sim_id; 422 on empty surface | UC-CSE-13 |
| R-CSE-14 | mirofish module removal | AC-CSE-20 | No mirofish imports remain | UC-CSE-14 |
| R-CSE-15 | Concurrent tenant isolation | AC-CSE-21 | Two tenants → separate dirs, no cross-contamination | UC-CSE-15 |

---

## Codebase Understanding Snapshot (Pre-Design Mandatory)

| Area | Findings | Evidence (files/functions) | Open Unknowns |
| --- | --- | --- | --- |
| Entrypoints / Boundaries | FastAPI router at `src/api/v1/router.py`; mirofish endpoint at `src/api/v1/endpoints/mirofish.py`; CSE endpoint will be at `src/api/v1/endpoints/cse.py` | `router.py:48`, `mirofish.py:44` | None |
| Current Naming Conventions | snake_case modules under `src/complira_graph/`; pydantic-settings for config; `get_reference_db()` for DB access | `config.py`, `db.py` | None |
| Impacted Modules / Responsibilities | `complira_graph.mirofish` (remove); `complira_graph.simulation.writeback_service` (call from CSE); `complira_graph.situation.abstraction_layer` (downstream consumer); `scripts/init_simulation_schema.py` (add collection) | investigation-notes.md §2 | None |
| Data / Persistence / External IO | ArangoDB via `python-arango`; per-run SQLite via stdlib `sqlite3` with `check_same_thread=False`; per-run JSONL file; `data/simulations/{tenant}/{sim_id}/` directory; subprocess via `sys.executable -m` | investigation-notes.md §5–6 | SQLite check_same_thread confirmed needed |

---

## Current State (As-Is)

- `src/complira_graph/mirofish/` — HTTP client to external MiroFish server (trigger_client.py, seed_extractor.py, __init__.py)
- `src/api/v1/endpoints/mirofish.py` — POST /v1/mirofish/trigger + GET /v1/mirofish/status/{run_id}
- No CSE package exists
- `scripts/init_simulation_schema.py` — provisions simulation collections but is missing `agent_action_logs`
- `data/simulations/` directory does not exist
- Frontend: no CSE simulation page; existing `SimulationLivePanel.tsx` + `SimulationResultCard.tsx` components exist

---

## Target State (To-Be)

- `src/complira_graph/cse/` — 13-module CSE package (runner, ipc, action_logger, memory_updater, graph_reader, profile_generator, config_generator, simulation_manager, attack_surface_server, attacker_simulation, defender_simulation, run_parallel_cyber_simulation, report_agent) + `__init__.py`
- `src/api/v1/endpoints/cse.py` — POST /v1/cse/simulations/create + GET /v1/cse/simulations/{sim_id}/status
- `src/api/v1/router.py` — imports `cse` endpoint, removes `mirofish` import
- `scripts/init_simulation_schema.py` — adds `agent_action_logs` collection
- `src/complira_graph/config.py` — adds `CSE_DATA_DIR` + `CSE_LLM_PROVIDER`
- `data/simulations/{tenant_id}/{sim_id}/` — created at simulation start
- `frontend/app/dashboard/simulation/page.tsx` — CSE simulation wizard (Next.js, 5-step)
- `src/complira_graph/mirofish/` — **REMOVED**
- `src/api/v1/endpoints/mirofish.py` — **REMOVED**

---

## Architecture Direction Decision (Mandatory)

- **Chosen direction:** New standalone package `src/complira_graph/cse/` with clear internal layer boundaries: graph extraction → profile generation → config synthesis → subprocess execution → IPC control → action state server → action logging → memory → report → write-back. Subprocess boundary isolates simulation execution from the FastAPI process.
- **Rationale:**
  - `complexity`: 13 focused files vs one monolith — each file owns one simulation concern
  - `testability`: each layer is independently unit-testable without a running simulation
  - `operability`: subprocess isolation means a crashed simulation cannot kill the API server; `run_state.json` provides durable state across crashes
  - `evolution cost`: LLM provider swap (future) requires changing only the profile generator and report agent factory; domain-specific action space is isolated in `attack_surface_server.py`
- **Layering fitness assessment:** New package — no existing layering to assess. Chosen layering is coherent.
- **Outcome:** `Add` (new `cse` package) + `Remove` (mirofish module and endpoint)

---

## Change Inventory (Delta)

| Change ID | Change Type | Current Path | Target Path | Rationale | Impacted Areas | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| C-001 | Add | — | `src/complira_graph/cse/__init__.py` | CSE package root | None | Re-exports public API |
| C-002 | Add | — | `src/complira_graph/cse/runner.py` | Simulation lifecycle manager | API endpoint, subprocess | CyberSimulationRunner, CyberRunnerStatus, CyberSimulationRunState |
| C-003 | Add | — | `src/complira_graph/cse/ipc.py` | File-based IPC | runner.py, subprocess | CyberIPCClient (subprocess side), CyberIPCHandler (main process side) |
| C-004 | Add | — | `src/complira_graph/cse/action_logger.py` | JSONL action logging | attacker_simulation.py, defender_simulation.py | CyberActionLogger |
| C-005 | Add | — | `src/complira_graph/cse/memory_updater.py` | SQLite working memory | attacker_simulation.py, defender_simulation.py | CyberMemoryUpdater, CyberAgentActivity; background thread + Queue |
| C-006 | Add | — | `src/complira_graph/cse/graph_reader.py` | Attack surface extraction from ArangoDB | simulation_manager.py | CompliraGraphReader, CyberEntityNode; replaces mirofish.seed_extractor |
| C-007 | Add | — | `src/complira_graph/cse/profile_generator.py` | 5-agent profile generation via Claude | simulation_manager.py | CyberAgentProfileGenerator; asyncio.gather for 5 concurrent LLM calls |
| C-008 | Add | — | `src/complira_graph/cse/config_generator.py` | simulation_config.json synthesis | simulation_manager.py | CyberSimConfigGenerator |
| C-009 | Add | — | `src/complira_graph/cse/simulation_manager.py` | Orchestrates prepare pipeline (CREATED→READY) | cse.py API endpoint | CyberSimulationManager |
| C-010 | Add | — | `src/complira_graph/cse/attack_surface_server.py` | In-process attack surface state (15 actions) | attacker_simulation.py, defender_simulation.py | AttackSurfaceServer; owns CVE exploitability, chain steps, patch tracking |
| C-011 | Add | — | `src/complira_graph/cse/attacker_simulation.py` | Attacker agent loop | run_parallel_cyber_simulation.py | run_attacker_loop() coroutine |
| C-012 | Add | — | `src/complira_graph/cse/defender_simulation.py` | Defender agent loop | run_parallel_cyber_simulation.py | run_defender_loop() coroutine |
| C-013 | Add | — | `src/complira_graph/cse/run_parallel_cyber_simulation.py` | Subprocess entry point; asyncio orchestrator | runner.py (Popen) | main() runs attacker + defender + ipc.poll_commands() via asyncio.gather |
| C-014 | Add | — | `src/complira_graph/cse/report_agent.py` | ReACT report agent | simulation_manager.py (post-run) | CyberReportAgent, REPORT_TOOLS (3 AQL tools) |
| C-015 | Add | — | `src/api/v1/endpoints/cse.py` | CSE API (create + status) | router.py | Replaces mirofish endpoint |
| C-016 | Modify | `src/api/v1/router.py` | same | Add cse import; remove mirofish import | None | |
| C-017 | Modify | `src/complira_graph/config.py` | same | Add CSE_DATA_DIR, CSE_LLM_PROVIDER settings | All CSE modules | |
| C-018 | Modify | `scripts/init_simulation_schema.py` | same | Add agent_action_logs collection + sim_id+agent_id index | memory_updater.py | Gap discovered in investigation |
| C-019 | Add | — | `frontend/app/dashboard/simulation/page.tsx` | CSE simulation wizard (Next.js 5-step) | Dashboard nav | Replaces MiroFish Vue.js wizard |
| C-019b | Modify | `frontend/components/situation/SimulationLivePanel.tsx` | same | Update polling endpoint `/v1/simulation/` → `/v1/cse/simulations/`; update data shape for CSE fields | simulation/page.tsx | Visual structure fully reused |
| C-019c | Modify | `frontend/components/situation/SimulationResultCard.tsx` | same | Update to CSE report shape: chain_probability, board_narrative, top_3_actions; remove cve_id dependency | simulation/page.tsx | |
| C-019d | Modify | `frontend/app/dashboard/situation/page.tsx` | same | Replace "Trigger a MiroFish run" string in PERSONA_EMPTY_MSG with CSE reference | None | 1-line string fix |
| C-020 | Remove | `src/complira_graph/mirofish/trigger_client.py` | — | Replaced by CSE — no external server | mirofish.py endpoint | |
| C-021 | Remove | `src/complira_graph/mirofish/seed_extractor.py` | — | Logic ported to CompliraGraphReader | mirofish.py endpoint | |
| C-022 | Remove | `src/complira_graph/mirofish/__init__.py` | — | Package deleted | router.py | |
| C-023 | Remove | `src/api/v1/endpoints/mirofish.py` | — | Replaced by cse.py endpoint | router.py | |

---

## Target Architecture Shape And Boundaries (Mandatory)

| Layer/Boundary | Purpose | Owns | Must Not Own | Notes |
| --- | --- | --- | --- | --- |
| API Layer (`src/api/v1/endpoints/cse.py`) | Request validation, auth, start CSE run, return status | HTTP contract, input validation, tenant auth | Simulation logic, ArangoDB queries | Thin — delegates to CyberSimulationManager |
| Simulation Orchestration (`simulation_manager.py`) | Prepare pipeline + post-run report + write-back invocation | Graph read → profile gen → config gen → CREATED→READY; start subprocess; call report agent and write-back after subprocess completes | Simulation execution details, IPC wire protocol | Owns prepare and post-completion phases only |
| Subprocess Boundary (`runner.py` + `run_parallel_cyber_simulation.py`) | Lifecycle isolation — simulation runs in a child process | Run state file writes, subprocess Popen, IPC client calls, asyncio.gather loop | ArangoDB access (except via queue/file), API concerns | Subprocess is launched with `sys.executable -m complira_graph.cse.run_parallel_cyber_simulation` |
| IPC Layer (`ipc.py`) | Command dispatch between main process and subprocess | File-based command/response in ipc_commands/ + ipc_responses/ directories | Simulation state, business logic | CyberIPCClient (written by main), CyberIPCHandler (polled in subprocess) |
| Domain State (`attack_surface_server.py`) | In-memory simulation state | CVE exploitability map, chain steps, patched CVEs, detection state | Persistence, logging, LLM calls | Mutable state accessed by both attacker and defender loops within the subprocess |
| Action Layer (`attacker_simulation.py`, `defender_simulation.py`) | Per-round agent decision → action execution | Agent action selection (LLM call), action dispatch to AttackSurfaceServer, logger call | State ownership, IPC | Thin loops that call into AttackSurfaceServer |
| Logging (`action_logger.py`) | JSONL action record per round | JSONL file writes | State mutations | Append-only |
| Memory (`memory_updater.py`) | SQLite per-agent working memory | Background Queue + batch SQLite writes, final ArangoDB flush to agent_action_logs | State mutations, ArangoDB non-memory writes | Batch size=5; check_same_thread=False |
| Graph Reader (`graph_reader.py`) | Attack surface extraction | AQL queries for CVEs + components + regulatory obligations | Profile generation, config, simulation logic | Replaces mirofish.seed_extractor; returns CyberEntityNode list |
| Profile Generator (`profile_generator.py`) | LLM-generated agent profiles | 5 profile types via asyncio.gather (Semaphore(3) fallback) | Simulation execution, config | Returns 5 JSON-serializable profile dicts |
| Config Generator (`config_generator.py`) | simulation_config.json synthesis | Merge entity data + profiles → simulation_config.json | LLM calls, state | Pure data assembly |
| Report Agent (`report_agent.py`) | ReACT loop post-simulation | 3 AQL tool calls (deep_chain_analysis, timeline_reconstruction, agent_state_query), final report dict | Write-back | Returns structured dict with chain_probability, board_narrative, etc. |
| Schema (`scripts/init_simulation_schema.py`) | ArangoDB collection provisioning | agent_action_logs collection + index | Application logic | Idempotent migration |
| Frontend (`frontend/app/dashboard/simulation/page.tsx`) | CSE simulation wizard | 5-step React page using existing SimulationLivePanel.tsx + SimulationResultCard.tsx | Backend logic | Next.js only |

---

## File And Module Breakdown

| File/Module | Change Type | Layer / Boundary | Concern / Responsibility | Public APIs | Inputs/Outputs | Dependencies |
| --- | --- | --- | --- | --- | --- | --- |
| `cse/__init__.py` | Add | Package | Re-exports: CyberSimulationManager, CyberSimulationRunner, CyberRunnerStatus | — | — | All CSE submodules |
| `cse/runner.py` | Add | Subprocess Boundary | Lifecycle states; Popen subprocess; write run_state.json on every transition | `CyberSimulationRunner.start_simulation()`, `stop_simulation()`, `get_state()` | tenant_id, sim_id, sim_dir → `run_state.json` | `ipc.py`, `config.py`, `subprocess`, `json` |
| `cse/ipc.py` | Add | IPC Layer | File-based IPC; CyberIPCClient writes commands, CyberIPCHandler polls and dispatches | `CyberIPCClient.send_command(cmd, payload)`, `CyberIPCHandler.poll_commands()`, `dispatch(cmd)` | sim_dir → ipc_commands/ + ipc_responses/ files | `json`, `pathlib`, `asyncio` |
| `cse/action_logger.py` | Add | Logging | Append-only JSONL log for all 15 action types | `CyberActionLogger.log_action(action_type, payload)`, `log_simulation_start()`, `log_round_start(round_no)` | sim_dir → `cyber_actions.jsonl` | `json`, `pathlib` |
| `cse/memory_updater.py` | Add | Memory | Queue + background thread → batch SQLite write; final ArangoDB flush | `CyberMemoryUpdater.record(CyberAgentActivity)`, `flush_to_arango(db)` | `CyberAgentActivity` dataclass → `cyber_agent_memory.db` + ArangoDB `agent_action_logs` | `sqlite3`, `queue`, `threading`, `python-arango` |
| `cse/graph_reader.py` | Add | Graph Reader | AQL query for CyberEntityNode list (CVEs + components + regs) | `CompliraGraphReader.get_attack_surface(db, tenant_id) -> list[CyberEntityNode]` | ArangoDB → `list[CyberEntityNode]` | `python-arango`, `dataclasses` |
| `cse/profile_generator.py` | Add | Profile Generator | 5-type agent profile generation via Claude (asyncio.gather + Semaphore(3)) | `CyberAgentProfileGenerator.generate_all(entity_nodes) -> list[dict]` | `list[CyberEntityNode]` → 5 profile dicts | `anthropic`, `asyncio`, `config.py` |
| `cse/config_generator.py` | Add | Config Generator | Produce `simulation_config.json` from profiles + entities | `CyberSimConfigGenerator.generate(trigger_type, profiles, entities) -> dict` | profiles + entities → `simulation_config.json` dict | `dataclasses`, `json` |
| `cse/simulation_manager.py` | Add | Simulation Orchestration | Prepare pipeline; launch subprocess; post-completion report + write-back | `CyberSimulationManager.prepare(db, tenant_id, trigger_type) -> sim_id`, `run(sim_id)`, `complete(db, sim_id)` | ArangoDB + trigger_type → sim_id; subprocess stdout → report | `graph_reader`, `profile_generator`, `config_generator`, `runner`, `report_agent`, `writeback_service` |
| `cse/attack_surface_server.py` | Add | Domain State | In-memory CVE/component state; 15-action handler methods | `AttackSurfaceServer.apply_action(action_type, payload)`, `get_exploitable_cves()`, `get_chain_steps()` | Action type + payload → state mutation | `dataclasses`, stdlib only |
| `cse/attacker_simulation.py` | Add | Action Layer | Per-round LLM-driven attacker decision → AttackSurfaceServer | `run_attacker_loop(config, surface_server, logger, memory) -> None` (coroutine) | `simulation_config.json` + surface state → actions | `anthropic`, `attack_surface_server`, `action_logger`, `memory_updater` |
| `cse/defender_simulation.py` | Add | Action Layer | Per-round LLM-driven defender decision → AttackSurfaceServer | `run_defender_loop(config, surface_server, logger, memory) -> None` (coroutine) | `simulation_config.json` + surface state → actions | `anthropic`, `attack_surface_server`, `action_logger`, `memory_updater` |
| `cse/run_parallel_cyber_simulation.py` | Add | Subprocess Entry Point | asyncio.gather(attacker, defender, ipc.poll) for N rounds; debrief mode | `main()` async (called via `python -m`) | CLI args: sim_dir, config_path → run_state.json updates | `attacker_simulation`, `defender_simulation`, `ipc`, `action_logger`, `memory_updater`, `attack_surface_server` |
| `cse/report_agent.py` | Add | Report Agent | ReACT loop with 3 AQL tools → final report dict | `CyberReportAgent.run(db, sim_id, tenant_id) -> dict` | ArangoDB sim data → report dict | `anthropic`, `python-arango`, `config.py` |
| `api/v1/endpoints/cse.py` | Add | API Layer | POST /v1/cse/simulations/create; GET /v1/cse/simulations/{sim_id}/status | Two route handlers | HTTP request → JSON response | `simulation_manager`, `db`, `security` |
| `api/v1/router.py` | Modify | API Layer | Add cse router; remove mirofish router | — | — | `cse.py` endpoint |
| `complira_graph/config.py` | Modify | Config | Add `CSE_DATA_DIR: str = "data/simulations"`, `CSE_LLM_PROVIDER: str = "claude"` | `get_settings()` | env vars → Settings | pydantic-settings |
| `scripts/init_simulation_schema.py` | Modify | Schema | Add `agent_action_logs` collection + composite index on `sim_id + agent_id` | Script (run once) | ArangoDB | python-arango |
| `frontend/app/dashboard/simulation/page.tsx` | Add | Frontend | 5-step CSE wizard (configure → preview → run → monitor → results) | React page component | REST API calls → UI state | `SimulationLivePanel.tsx`, `SimulationResultCard.tsx` |
| `frontend/components/situation/SimulationLivePanel.tsx` | Modify | Frontend | Live simulation poller — endpoint updated to CSE status route; data shape updated | `SimulationLivePanel` component | `/v1/cse/simulations/{sim_id}/status` → UI state | next-auth |
| `frontend/components/situation/SimulationResultCard.tsx` | Modify | Frontend | Completed run display — updated to CSE report fields (chain_probability, board_narrative, top_3_actions) | `SimulationResultCard` component | CSE report dict → UI display | next/navigation |
| `frontend/app/dashboard/situation/page.tsx` | Modify | Frontend | Situation Room — remove mirofish empty message reference | Page component | Live data → UI | existing situation components |
| `complira_graph/mirofish/trigger_client.py` | Remove | — | REMOVED | — | — | — |
| `complira_graph/mirofish/seed_extractor.py` | Remove | — | REMOVED | — | — | — |
| `complira_graph/mirofish/__init__.py` | Remove | — | REMOVED | — | — | — |
| `api/v1/endpoints/mirofish.py` | Remove | — | REMOVED | — | — | — |

---

## Layer-Appropriate Separation Of Concerns Check

- **API layer (`cse.py`)**: owns request validation + auth + status polling only. All preparation logic delegated to `CyberSimulationManager`. No business logic in endpoint handlers.
- **Simulation orchestration (`simulation_manager.py`)**: owns prepare pipeline + subprocess launch + post-run reporting. Does not own simulation execution internals or IPC wire protocol.
- **Subprocess boundary**: `runner.py` owns lifecycle state + Popen. `run_parallel_cyber_simulation.py` owns asyncio execution within the subprocess. Neither knows about FastAPI or HTTP.
- **Domain state (`attack_surface_server.py`)**: owns CVE/component state mutations only. No I/O, no logging, no LLM calls.
- **Memory (`memory_updater.py`)**: owns SQLite write + ArangoDB flush. Does not own action decisions or state.
- **Report agent (`report_agent.py`)**: owns ReACT loop + AQL tool dispatch. Does not own write-back (delegated to `SimulationWritebackService`).
- **Frontend (`page.tsx`)**: owns 5-step wizard UI. No direct ArangoDB access; all data via REST endpoints.

---

## Naming Decisions (Natural And Implementation-Friendly)

| Item Type | Current Name | Proposed Name | Reason | Notes |
| --- | --- | --- | --- | --- |
| Module | `mirofish/` | `cse/` | CSE = Complira Simulation Engine — domain-specific name | Canonical name from plan |
| File | (new) | `run_parallel_cyber_simulation.py` | `run_parallel_*` matches MiroFish subprocess convention; `cyber_*` scope prefix | Also used as `-m` module target |
| Class | (new) | `CyberSimulationRunner` | `Cyber` prefix scopes to cybersecurity domain; `Runner` = lifecycle | Consistent with `CyberSimConfigGenerator`, etc. |
| Class | (new) | `CompliraGraphReader` | `Complira` = product name; `Graph` = ArangoDB graph; `Reader` = read-only | Replaces `extract_monthly_posture_seed` |
| Class | (new) | `AttackSurfaceServer` | `AttackSurface` = domain; `Server` = shared in-process state server | Matches MiroFish `TweetServer` pattern |
| Class | (new) | `CyberReportAgent` | `Cyber` = domain; `ReportAgent` = ReACT loop producing report | Matches `CyberAgentProfileGenerator` pattern |
| API | (new) | `POST /v1/cse/simulations/create` | `cse` namespace; `simulations` resource; `create` action | Replaces `/v1/mirofish/trigger` |
| API | (new) | `GET /v1/cse/simulations/{sim_id}/status` | `{sim_id}` path param; `status` sub-resource | Replaces `/v1/mirofish/status/{run_id}` |
| Setting | (new) | `CSE_DATA_DIR` | Standard SCREAMING_SNAKE env var pattern; unambiguous scope | Default: `data/simulations` |
| Setting | (new) | `CSE_LLM_PROVIDER` | Signals future swap-ability (claude / ollama) | Default: `claude` |

---

## Naming Drift Check (Mandatory)

| Item | Current Responsibility | Does Name Still Match? | Corrective Action | Mapped Change ID |
| --- | --- | --- | --- | --- |
| `mirofish/trigger_client.py` | HTTP client to external server | N/A — REMOVED | Remove | C-020 |
| `mirofish/seed_extractor.py` | Graph extraction for seed | N/A — REMOVED | Remove (logic ported to CompliraGraphReader) | C-021 |
| `simulation_manager.py` | Orchestrates preparation + post-run | Yes — `simulation_manager` is correct | N/A | C-009 |
| `run_parallel_cyber_simulation.py` | Subprocess entry point, asyncio parallel loops | Yes | N/A | C-013 |
| `attack_surface_server.py` | In-memory shared state for simulation | Yes — `server` = shared state | N/A | C-010 |

---

## Existing-Structure Bias Check (Mandatory)

| Candidate Area | Current-File-Layout Bias Risk | Architecture-First Alternative | Decision | Why |
| --- | --- | --- | --- | --- |
| Put simulation logic inside `simulation/` (existing package) | Medium — existing `simulation/writeback_service.py` is in `simulation/`; temptation to add CSE there | Separate `cse/` package — CSE is the engine, `simulation/` is write-back infrastructure | Change (new `cse/` package) | CSE is a complete domain simulation system, not write-back infrastructure |
| Reuse existing `MiroFishTriggerClient` wrapper pattern | Medium — could wrap CSE as an HTTP client just like MiroFish did | CSE IS the engine; no HTTP wrapping needed | Change (Remove mirofish wrapper entirely) | No external server to call |
| Add CSE endpoint to existing `mirofish.py` | Low — just modify the existing file | New file `cse.py` — clean separation, no dead code risk | Change (new `cse.py`) | mirofish.py is removed entirely |

---

## Anti-Hack Check (Mandatory)

| Candidate Change | Shortcut/Hack Risk | Proper Structural Fix | Decision | Notes |
| --- | --- | --- | --- | --- |
| Keep mirofish module, add CSE as a thin wrapper | High — dual code paths, legacy imports survive | Remove mirofish entirely, CSE replaces it | Clean cut | R-CSE-14 mandates full removal |
| Use FastAPI background_tasks instead of subprocess | Medium — couples simulation lifecycle to API worker; crash kills simulation | subprocess.Popen isolation — simulation outlives HTTP request | Subprocess pattern | Subprocess isolation is a hard requirement |
| Share SQLite file between tenants | High — cross-tenant contamination | Per-run SQLite in isolated `data/simulations/{tenant}/{sim_id}/` | Per-run isolation | R-CSE-15 |
| Write simulation logs directly to ArangoDB per round | Medium — per-round network round-trips during hot loop | SQLite per-run → batch ArangoDB flush at end | Batch pattern | Per spec in investigation-notes.md §5 |
| Run profile generator LLM calls sequentially | Low — safe but slower | asyncio.gather with Semaphore(3) fallback for rate limits | asyncio.gather | OQ-2 mitigation |

---

## Dependency Flow And Cross-Reference Risk

| Module/File | Upstream Dependencies | Downstream Dependents | Cross-Reference Risk | Mitigation / Boundary Strategy |
| --- | --- | --- | --- | --- |
| `cse/graph_reader.py` | `python-arango`, `config.py` | `simulation_manager.py` | Low | Read-only; no mutation |
| `cse/profile_generator.py` | `anthropic`, `config.py`, `graph_reader.py` (data) | `simulation_manager.py` | Low | Stateless LLM calls |
| `cse/config_generator.py` | `profile_generator.py` (data), `graph_reader.py` (data) | `simulation_manager.py` | Low | Pure data assembly |
| `cse/simulation_manager.py` | `graph_reader`, `profile_generator`, `config_generator`, `runner`, `report_agent`, `writeback_service` | `api/v1/endpoints/cse.py` | Medium | Orchestrator only — no simulation execution logic |
| `cse/attack_surface_server.py` | stdlib only | `attacker_simulation.py`, `defender_simulation.py` | Low | No I/O; pure state |
| `cse/attacker_simulation.py` | `attack_surface_server`, `action_logger`, `memory_updater`, `anthropic` | `run_parallel_cyber_simulation.py` | Low | One direction only |
| `cse/defender_simulation.py` | `attack_surface_server`, `action_logger`, `memory_updater`, `anthropic` | `run_parallel_cyber_simulation.py` | Low | One direction only |
| `cse/run_parallel_cyber_simulation.py` | `attacker_simulation`, `defender_simulation`, `ipc`, `attack_surface_server`, `action_logger`, `memory_updater` | `runner.py` (Popen target) | Low | Subprocess entry — no API imports |
| `cse/report_agent.py` | `anthropic`, `python-arango`, `config.py` | `simulation_manager.py` | Low | Post-run only; no mutation outside agent_action_logs + report dict |
| `api/v1/endpoints/cse.py` | `simulation_manager`, `db`, `security` | `router.py` | Low | Thin endpoint |
| `complira_graph/simulation/writeback_service.py` | `python-arango` | `simulation_manager.py` (called after report) | Low | Already built; CSE only calls `run_all(payload)` |

---

## Allowed Dependency Direction (Mandatory)

- Allowed direction: `API → Orchestration (simulation_manager) → CSE submodules → stdlib/arango/anthropic`
- Subprocess side: `run_parallel_cyber_simulation → attack_surface_server + action_logger + memory_updater + ipc + attacker/defender loops`
- `report_agent` → `writeback_service` (via `simulation_manager` — not a direct import from report_agent)
- **Forbidden directions:**
  - CSE submodules must not import from `api/` package
  - `run_parallel_cyber_simulation.py` must not import from `api/` package (subprocess isolation)
  - `attack_surface_server.py` must not import from logging or memory layers (pure state)
- **Temporary violations:** None expected

---

## Decommission / Cleanup Plan

| Item To Remove/Rename | Cleanup Actions | Legacy Removal Notes | Verification |
| --- | --- | --- | --- |
| `src/complira_graph/mirofish/trigger_client.py` | Delete file | No references should remain in codebase | `grep -r "trigger_client"` returns nothing |
| `src/complira_graph/mirofish/seed_extractor.py` | Delete file; seed extraction logic ported to `CompliraGraphReader` | Logic replicated, not dependent | `grep -r "seed_extractor"` returns nothing |
| `src/complira_graph/mirofish/__init__.py` | Delete file | Package deleted | AC-CSE-20 |
| `src/api/v1/endpoints/mirofish.py` | Delete file | Tests updating `test_situation_simulation_api.py::TestMiroFishTriggerAPI` | `grep -r "from api.v1.endpoints import mirofish"` returns nothing |
| `router.py` mirofish lines | Remove import + include_router lines for mirofish | Two line removals | Import error if forgotten |
| `tests/integration/test_situation_simulation_api.py` | Rewrite `TestMiroFishTriggerAPI` class for CSE endpoint | Scenarios rewritten; no `mirofish` mock imports | AC-CSE-20 |

---

## Data Models

### CyberEntityNode
```python
@dataclass
class CyberEntityNode:
    entity_id: str          # CVE-ID, component _key, or regulatory obligation _key
    entity_type: str        # "cve" | "component" | "regulatory_obligation"
    severity: float         # CVSS base score or 0.0
    is_kev: bool            # In CISA KEV?
    regulatory_refs: list[str]  # CRA/NIS2 article keys
    component_name: str     # readable name
```

### CyberSimulationRunState
```python
@dataclass
class CyberSimulationRunState:
    sim_id: str
    tenant_id: str
    status: str             # CyberRunnerStatus value
    trigger_type: str       # "kev_triggered" | "monthly_posture_sim"
    total_rounds: int
    current_round: int
    started_at: str         # ISO-8601
    updated_at: str         # ISO-8601
```

### CyberAgentActivity
```python
@dataclass
class CyberAgentActivity:
    sim_id: str
    agent_id: str
    agent_type: str         # "Attacker" | "SOCAnalyst" | etc.
    round_no: int
    action_type: str        # one of 15 action constants
    target: str
    outcome: str
    episode_text: str       # human-readable LLM narrative
    timestamp: str          # ISO-8601
```

### CyberRunnerStatus (Enum)
```
IDLE → STARTING → RUNNING → PAUSED → STOPPING → STOPPED → COMPLETED → FAILED
```

### 15 Cybersecurity Actions (Constants)
```
SCAN_SURFACE, EXPLOIT_CVE, LATERAL_MOVE, ESCALATE_PRIVILEGES, PIVOT_TARGET,
MONITOR, DETECT, INVESTIGATE, ESCALATE_TO_CISO, PATCH, DEPLOY_CONTROL,
ROTATE_CREDENTIAL, FILE_CRA_NOTIFICATION, NOTIFY_BOARD, ACKNOWLEDGE
```

### simulation_config.json Schema
```json
{
  "sim_id": "str",
  "tenant_id": "str",
  "trigger_type": "kev_triggered | monthly_posture_sim",
  "total_rounds": 48,
  "hours_per_round": 1,
  "cra_deadline_round": 24,
  "narrative_provider": "claude",
  "agent_profiles": [...],
  "scheduled_events": [...]
}
```

### CyberReportAgent Output Dict
```python
{
  "sim_id": str,
  "tenant_id": str,
  "chain_probability": float,
  "soc_miss_probability": float,
  "tef_estimate": float,
  "board_narrative": str,
  "top_3_actions": list[str],
  "completed_at": str
}
```

### CSERunStatus (TypeScript — frontend consumption)
```typescript
interface CSERunStatus {
  sim_id: string;
  tenant_id: string;
  status: "idle" | "starting" | "running" | "paused" | "stopping" | "stopped" | "completed" | "failed";
  trigger_type: "kev_triggered" | "monthly_posture_sim";
  current_round: number;
  total_rounds: number;
  agent_count: number;
  chain_count: number | null;      // populated after report write-back
  started_at: string;              // ISO-8601
  updated_at: string;              // ISO-8601
  recent_events: CSEActionEvent[]; // last 20 high-significance action log entries
}

interface CSEActionEvent {
  log_key: string;
  event_type: string;    // action_type constant
  agent_id: string;
  agent_type: string;
  round_no: number;
  outcome: string;
  significance: number;  // 0.0–1.0
  timestamp: string;     // ISO-8601
}
```
Note: `cve_id` is NOT in `CSERunStatus`. CSE operates on attack surfaces, not single CVEs. The `SimulationLivePanel` and `SimulationResultCard` components are updated (C-019b, C-019c) to use `CSERunStatus` instead of the old `SimulationRunStatus`.

### Subprocess Debrief Phase
After completing `total_rounds`:
1. `run_parallel_cyber_simulation.py` writes `status: completed` to `run_state.json`
2. Subprocess enters debrief loop: polls `ipc_commands/` for `DEBRIEF_AGENT` or `CLOSE_ENV` commands
3. Main process (`simulation_manager.complete()`) detects `status: completed` in `run_state.json`
4. Main process runs `CyberReportAgent.run()` (direct AQL queries — no IPC needed)
5. Main process calls `SimulationWritebackService.run_all()`
6. Main process sends `CLOSE_ENV` IPC command → subprocess exits debrief loop → `sys.exit(0)`
7. Monitor thread in `runner.py` sees clean exit → `_transition(COMPLETED)` already set; no state change needed

---

## Error Handling And Edge Cases

| Scenario | Handler | Response |
| --- | --- | --- |
| Empty attack surface at `POST /create` | `simulation_manager.prepare()` raises ValueError | API returns 422 `insufficient_attack_surface` |
| Subprocess crash (run_state.json shows FAILED) | `runner.py` sets status=FAILED before Popen exit | `GET /status` returns `status: failed`; write-back NOT called |
| IPC command timeout > 5s | `CyberIPCHandler` timeout path | Returns error response; simulation continues |
| Unknown IPC command | `CyberIPCHandler.dispatch()` default branch | Returns `{error: "unknown_command"}`; no crash |
| Claude API rate limit during profile gen | `asyncio.Semaphore(3)` limits concurrency | Slower but succeeds; retry on 429 |
| SQLite check_same_thread | `sqlite3.connect(..., check_same_thread=False)` | Background thread safe |
| Cross-tenant sim directory access | Per-run dir includes `{tenant_id}/` prefix | Isolation by construction |
| Report agent > 30s | Claude timeout `ANTHROPIC_TIMEOUT` setting | Returns partial report; write-back still called with available data |

---

## Use-Case Coverage Matrix (Design Gate)

| use_case_id | Requirement | Use Case | Primary Path Covered | Fallback Path Covered | Error Path Covered | Runtime Call Stack Section |
| --- | --- | --- | --- | --- | --- | --- |
| UC-CSE-01 | R-CSE-01 | Simulation lifecycle state machine | Yes | Yes (FAILED state) | Yes (FAILED transition) | UC-CSE-01 |
| UC-CSE-02 | R-CSE-02 | IPC command dispatch | Yes | Yes (unknown cmd error) | Yes (timeout path) | UC-CSE-02 |
| UC-CSE-03 | R-CSE-03 | Attack surface extraction | Yes | N/A | Yes (empty surface → 422) | UC-CSE-03 |
| UC-CSE-04 | R-CSE-04 | Parallel profile generation | Yes | Yes (Semaphore(3) fallback) | Yes (rate limit) | UC-CSE-04 |
| UC-CSE-05 | R-CSE-05 | Config synthesis | Yes | N/A | N/A | UC-CSE-05 |
| UC-CSE-06 | R-CSE-06 | Preparation pipeline | Yes | N/A | Yes (ArangoDB error) | UC-CSE-06 |
| UC-CSE-07 | R-CSE-07 | Parallel simulation execution | Yes | N/A | Yes (subprocess crash) | UC-CSE-07 |
| UC-CSE-08 | R-CSE-08 | 15-action cybersecurity action space | Yes | N/A | N/A | UC-CSE-08 |
| UC-CSE-09 | R-CSE-09 | JSONL action logging | Yes | N/A | N/A | UC-CSE-09 |
| UC-CSE-10 | R-CSE-10 | SQLite agent working memory + ArangoDB flush | Yes | Yes (batch flush) | Yes (SQLite thread safety) | UC-CSE-10 |
| UC-CSE-11 | R-CSE-11 | ReACT report generation | Yes | N/A | Yes (timeout) | UC-CSE-11 |
| UC-CSE-12 | R-CSE-12 | Write-back integration | Yes | N/A | Yes (failed run no write-back) | UC-CSE-12 |
| UC-CSE-13 | R-CSE-13 | CSE API endpoints | Yes | N/A | Yes (422 empty surface) | UC-CSE-13 |
| UC-CSE-14 | R-CSE-14 | mirofish module removal | Yes | N/A | N/A | UC-CSE-14 |
| UC-CSE-15 | R-CSE-15 | Concurrent tenant isolation | Yes | N/A | N/A | UC-CSE-15 |

---

## Performance / Security Considerations

- **Attack surface query < 200ms**: ArangoDB query in `graph_reader.py` must filter by `tenant_id` index; use existing `idx_simrun_tenant` pattern.
- **No CVE IDs in write-back output**: `CyberReportAgent` must not include raw CVE IDs in `board_narrative` or `top_3_actions`; uses ATT&CK tactic names and impact categories only (consistent with `SituationAbstractionLayer` constraint).
- **Tenant isolation**: All file I/O paths include `{tenant_id}/{sim_id}/`; AQL queries always include `FILTER r.tenant_id == @tenant_id`.
- **Subprocess security**: No user-controlled data passed as shell arguments; subprocess receives only `sim_dir` path and `config_path` (both constructed server-side).
- **LLM prompt injection**: Agent profiles and simulation_config.json are constructed server-side from structured ArangoDB data; no raw user text injected into LLM prompts.

---

## Migration / Rollout

1. Add `agent_action_logs` collection via `scripts/init_simulation_schema.py` (idempotent — safe to run on existing DB).
2. Deploy new CSE package + API endpoint.
3. Remove mirofish module and endpoint atomically in the same deploy.
4. `data/simulations/` directory created on first run by `CyberSimulationRunner` (`mkdir -p`).
5. No data migration needed — simulation_runs collection is reused (CSE writes same schema).

---

## Change Traceability To Implementation Plan

| Change ID | Implementation Plan Task(s) | Verification (Unit/Integration/API/E2E) | Status |
| --- | --- | --- | --- |
| C-001–C-014 | Week 1–7 build tasks per investigation-notes.md §7 | Unit tests per module + integration tests for cross-boundary flows | Planned |
| C-015 | API endpoint file | API/E2E: AC-CSE-18, AC-CSE-19 | Planned |
| C-016 | Router modification | Integration: no import error | Planned |
| C-017 | Config settings | Unit: defaults verified | Planned |
| C-018 | Schema migration | Integration: collection exists after script | Planned |
| C-019 | Frontend wizard page | E2E: 5-step flow | Planned |
| C-019b | SimulationLivePanel endpoint update | Integration: polls CSE status endpoint | Planned |
| C-019c | SimulationResultCard CSE fields | Integration: renders CSE report dict | Planned |
| C-019d | Situation Room MiroFish string | N/A (string only) | Planned |
| C-020–C-023 | mirofish removal | AC-CSE-20: grep clean | Planned |

---

## Design Feedback Loop Notes (From Review/Implementation)

| Date | Trigger | Classification | Design Smell | Requirements Updated? | Design Update Applied | Status |
| --- | --- | --- | --- | --- | --- | --- |
| — | — | — | — | No | — | — |

---

## Open Questions

| # | Question | Design Decision |
|---|----------|----------------|
| OQ-1 | Subprocess invocation pattern | `sys.executable -m complira_graph.cse.run_parallel_cyber_simulation` — no console_scripts entry point needed |
| OQ-2 | Claude API rate limits for 5 concurrent asyncio LLM calls | `asyncio.Semaphore(3)` in `CyberAgentProfileGenerator.generate_all()` |
| OQ-3 | SQLite `check_same_thread=False` | Yes — confirmed needed in `CyberMemoryUpdater` background thread |
| OQ-4 | `agent_action_logs` AQL schema — indexed fields | Add `sim_id + agent_id` composite index (C-018) |
