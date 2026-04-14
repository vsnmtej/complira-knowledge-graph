# Investigation Notes — cse-simulation-engine

**Stage:** 1
**Date:** 2026-04-14
**Triage result:** `Large`

---

## Sources Consulted

| Source | Type | Purpose |
|--------|------|---------|
| `/Users/venkatapydialli/Downloads/cse_impl_plan_v1.1.docx` | Local file | Primary design reference — full CSE plan |
| `src/complira_graph/simulation/writeback_service.py` | Local file | Existing write-back contract to integrate with |
| `src/complira_graph/situation/abstraction_layer.py` | Local file | Downstream consumer of CSE output |
| `src/complira_graph/mirofish/trigger_client.py` | Local file | Existing MiroFish HTTP wrapper — to be replaced |
| `src/complira_graph/mirofish/seed_extractor.py` | Local file | Existing graph extraction — to be ported/replaced |
| `src/api/v1/router.py` | Local file | API registration pattern |
| `src/api/v1/endpoints/mirofish.py` | Local file | Existing trigger endpoint — to be replaced |
| `src/complira_graph/config.py` | Local file | Settings pattern (pydantic-settings) |
| `frontend/app/dashboard/situation/page.tsx` | Local file | Existing simulation UI entry point |
| `frontend/components/situation/SimulationLivePanel.tsx` | Local file | Existing live panel component |
| `data/` directory layout | Local directory | Confirms `data/regulations/`, `data/scf/` exist; `data/simulations/` does not yet |

---

## Key Findings

### 1. Package location

The plan says `complira/cse/` but the existing codebase uses `src/complira_graph/` as the root Python package. All existing modules (simulation, situation, mirofish, queries, etc.) live under `src/complira_graph/`. CSE must live at `src/complira_graph/cse/` to match the existing import tree.

### 2. Existing infrastructure inventory

| Component | Location | Status | CSE relationship |
|-----------|----------|--------|-----------------|
| `SimulationWritebackService` | `src/complira_graph/simulation/writeback_service.py` | Built | CSE calls this after simulation completes |
| `SituationAbstractionLayer` | `src/complira_graph/situation/abstraction_layer.py` | Built | Reads from collections CSE writes |
| ArangoDB simulation collections | Provisioned by `scripts/init_simulation_schema.py` | Built | CSE writes to `attack_chain_findings`, `threat_category_rollups`, etc. |
| `MiroFishTriggerClient` | `src/complira_graph/mirofish/trigger_client.py` | Built | **REPLACED** by CSE — CSE is the engine, not a client |
| `extract_monthly_posture_seed` | `src/complira_graph/mirofish/seed_extractor.py` | Built | Logic ported into `CompliraGraphReader`; original module removed |
| `/v1/mirofish/trigger` endpoint | `src/api/v1/endpoints/mirofish.py` | Built | **REPLACED** by `/v1/cse/simulations/create` |
| Simulation status endpoint | `src/api/v1/endpoints/simulation.py` | Built | Reused for CSE runs (already reads `simulation_runs` collection) |

### 3. MiroFish module fate

`src/complira_graph/mirofish/` exists to call an external MiroFish server. Once CSE is running, there is no external server to call — CSE IS the simulation engine. Both `trigger_client.py` and `seed_extractor.py` should be **removed** in this ticket (seed extraction logic ports into `CompliraGraphReader`). The `/v1/mirofish/trigger` + `/v1/mirofish/status/` endpoints should be replaced by `/v1/cse/simulations/create` + `/v1/cse/simulations/{sim_id}/status`.

**Impact:** Any existing tests that mock `MiroFishTriggerClient` or patch `mirofish` endpoint will need updating. `tests/integration/test_situation_simulation_api.py` has `TestMiroFishTriggerAPI` — those scenarios will be rewritten for the CSE endpoint.

### 4. Frontend decision: Next.js, not Vue.js

The plan says ~65% of MiroFish's Vue.js 3 wizard is reusable. MiroFish defaults to Chinese (`zh` locale, must be changed to `en`). However:

- The existing Complira dashboard is **Next.js/React** with existing simulation components (`SimulationLivePanel.tsx`, `SimulationResultCard.tsx`) already in `frontend/components/situation/`
- Adding a Vue.js SPA would require a separate port, separate build, and a split tech stack
- The plan's 5-step wizard maps cleanly to a Next.js multi-step page

**Decision:** Build the CSE simulation wizard in **Next.js** (not Vue.js) at `frontend/app/dashboard/simulation/`. The existing `SimulationLivePanel.tsx` and `SimulationResultCard.tsx` components are the foundation. This keeps a single frontend stack.

The MiroFish Vue.js frontend reuse assessment in the plan (section 10) is superseded by this decision. Functionality parity is achieved in Next.js components.

### 5. Per-run SQLite for agent working memory

The plan (section 11.3) explicitly decides: agent working memory uses per-run SQLite (`cyber_agent_memory.db` in the sim directory), not ArangoDB. This matches MiroFish's pattern exactly and avoids per-round ArangoDB queries during simulation execution.

Final write-back uses ArangoDB via `SimulationWritebackService` as before. SQLite is transient per-run storage only.

### 6. Data directory layout

`data/` currently contains `regulations/` and `scf/`. Per-run simulation directories at:
```
data/simulations/{tenant_id}/{sim_id}/
  cyber_actions.jsonl
  cyber_agent_memory.db
  run_state.json
  simulation_config.json
  ipc_commands/
  ipc_responses/
```

This directory must be created at simulation start and configurable via `Settings.CSE_DATA_DIR` (default: `data/simulations`).

### 7. 13-file CSE package

The plan's file structure maps to `src/complira_graph/cse/`:

| File | Class | Week |
|------|-------|------|
| `runner.py` | `CyberSimulationRunner`, `CyberRunnerStatus`, `CyberSimulationRunState` | 1 |
| `ipc.py` | `CyberIPCClient`, `CyberIPCHandler` | 1 |
| `action_logger.py` | `CyberActionLogger` | 2 |
| `memory_updater.py` | `CyberMemoryUpdater`, `CyberAgentActivity` | 2 |
| `graph_reader.py` | `CompliraGraphReader`, `CyberEntityNode` | 3 |
| `profile_generator.py` | `CyberAgentProfileGenerator` + 5 profile dataclasses | 3 |
| `config_generator.py` | `CyberSimConfigGenerator` | 4 |
| `simulation_manager.py` | `CyberSimulationManager` | 4 |
| `attack_surface_server.py` | `AttackSurfaceServer` | 5 |
| `attacker_simulation.py` | `run_attacker_loop()` | 5 |
| `defender_simulation.py` | `run_defender_loop()` | 6 |
| `run_parallel_cyber_simulation.py` | `main()` async orchestrator | 6 |
| `report_agent.py` | `CyberReportAgent`, `REPORT_TOOLS` | 7 |

Plus `__init__.py` and test files.

### 8. New API endpoints

Two new CSE API endpoints (replace mirofish):
- `POST /v1/cse/simulations/create` — triggers CSE run
- `GET  /v1/cse/simulations/{sim_id}/status` — polls run status

`GET /v1/simulation/{run_id}/status` already exists and reads `simulation_runs` collection — it can be **reused** for CSE status polling (since CSE writes to the same collection).

### 9. LLM provider swap

The plan calls for `narrative_provider: claude | openai | ollama | qwen` in `simulation_config.json`. `CyberAgentProfileGenerator` and `CyberReportAgent` both make LLM calls. An abstraction layer (factory function) selects the provider based on config. This maps to existing `Settings.ANTHROPIC_MODEL` patterns. Ollama swap-ability must be verified in Stage 7 (out of scope for this ticket — basic Claude path only).

### 10. Scope triage signals

| Signal | Value |
|--------|-------|
| New source files | ~15 Python + 1 Next.js page + 1 API endpoint file |
| New public APIs | `POST /v1/cse/simulations/create`, `GET /v1/cse/simulations/{sim_id}/status` |
| Schema changes | New AQL collections: `agent_action_logs` (add), `simulation_runs` (already exists) |
| Cross-cutting | subprocess + file IPC + SQLite + ArangoDB + API + Frontend |
| Architectural impact | Subprocess lifecycle management, asyncio parallel loops, new package |
| Removed modules | `src/complira_graph/mirofish/` (both files + __init__), `src/api/v1/endpoints/mirofish.py` |
| Build horizon | 8 weeks per plan |

**Triage: `Large`**

---

## Open Unknowns

1. **Rate limits on parallel Claude calls**: `CyberAgentProfileGenerator` uses `asyncio.gather` for 5 concurrent LLM calls. With Claude sonnet-4-6, need to verify if 5 concurrent calls are within rate limits or if sequential fallback is needed.

2. **`agent_action_logs` collection**: The plan references writing to `agent_action_logs` from `CyberMemoryUpdater`. This collection does not appear in `scripts/init_simulation_schema.py` currently. It must be added to the schema migration script.

3. **Subprocess path resolution**: `run_parallel_cyber_simulation.py` will be launched via `subprocess.Popen(['python', 'run_parallel_cyber_simulation.py', ...])`. The path must be resolvable. Options: (a) install CSE as a console script entry point, (b) use `sys.executable` + absolute module path. Decision needed in design.

4. **SQLite thread safety**: `CyberMemoryUpdater` writes from a background thread. Need `check_same_thread=False` on SQLite connection or connection-per-thread.

---

## Implications for Requirements / Design

1. Package root is `src/complira_graph/cse/` (not `complira/cse/`).
2. `mirofish/` module and `/v1/mirofish/` endpoint are removed in same ticket.
3. Frontend is Next.js, not Vue.js. MiroFish frontend assessment (section 10 of plan) is superseded.
4. `agent_action_logs` collection must be added to `scripts/init_simulation_schema.py`.
5. `data/simulations/` directory layout must be created and configurable.
6. Subprocess path needs a design decision: entry point vs module path.
