# Requirements — cse-simulation-engine

**Status:** Design-ready
**Triage:** `Large` — 15 new Python files, 1 new API endpoint file, 1 Next.js page, subprocess lifecycle, SQLite + ArangoDB, removal of mirofish module
**Last Updated:** 2026-04-14
**Source:** `cse_impl_plan_v1.1.docx` (v1.1) + `investigation-notes.md`

---

## Goal / Problem Statement

Build the **Complira Simulation Engine (CSE)** — a cybersecurity-domain agent simulation engine
ported from MiroFish's architecture. Agents model emergent attack/defence behaviour over a
virtual attack surface (CVEs, components, regulatory obligations) extracted from complira_graph.

CSE is a **scenario intelligence tool**: no real payloads, no real network traffic. Simulation
output feeds the existing `SimulationWritebackService` → ArangoDB → `SituationAbstractionLayer`
→ CISO/Board dashboard views.

CSE **replaces** the existing `src/complira_graph/mirofish/` module and `/v1/mirofish/` endpoints.

---

## Triage Rationale

- **15+ new Python files** in `src/complira_graph/cse/`
- **Multi-layer**: subprocess lifecycle + file IPC + SQLite (working memory) + ArangoDB + FastAPI + Next.js frontend
- **Removes** 2 mirofish module files + 1 endpoint file
- **New domain** (agent simulation) not yet in codebase
- **8-week build plan** confirms Large

---

## In-Scope Requirements

### R-CSE-01 — Simulation lifecycle management
**Expected outcome:** `CyberSimulationRunner` transitions through 8 states (IDLE → STARTING → RUNNING → PAUSED → STOPPING → STOPPED → COMPLETED → FAILED). `run_state.json` is written on every transition. Start/stop work via IPC.

### R-CSE-02 — IPC layer
**Expected outcome:** File-based IPC (ipc_commands/ + ipc_responses/ directories per sim run). `CyberIPCHandler` dispatches INJECT_VARIABLE, PAUSE_AND_SNAPSHOT, CLOSE_ENV, DEBRIEF_AGENT commands. Response received within 5 seconds for INJECT_VARIABLE.

### R-CSE-03 — Attack surface extraction
**Expected outcome:** `CompliraGraphReader` fetches `CyberEntityNode` list (CVEs + components + regulatory obligations) from ArangoDB for a tenant in < 200ms. Returns structured dataclass matching downstream profile generator contract.

### R-CSE-04 — Agent profile generation
**Expected outcome:** `CyberAgentProfileGenerator` generates all 5 profile types (Attacker, SOCAnalyst, DevSecOps, CISO, Regulator) in parallel (asyncio.gather). All profiles are valid JSON matching `cyber_simulation_config.json` schema.

### R-CSE-05 — Simulation config synthesis
**Expected outcome:** `CyberSimConfigGenerator` produces `simulation_config.json` with `total_rounds` (48 for KEV, 720 for monthly posture), `hours_per_round=1`, `cra_deadline_round=24`, `agent_profiles[]`, `scheduled_events[]`, and `narrative_provider`.

### R-CSE-06 — Simulation preparation pipeline
**Expected outcome:** `CyberSimulationManager` orchestrates: graph read → profile generation → config generation → CREATED → READY state. `run_state.json` + `simulation_config.json` both written to `data/simulations/{tenant_id}/{sim_id}/`.

### R-CSE-07 — Parallel simulation execution
**Expected outcome:** `run_parallel_cyber_simulation.py` runs `run_attacker_loop` + `run_defender_loop` + `ipc.poll_commands()` concurrently via `asyncio.gather`. Completes `total_rounds` rounds. Debrief mode active after completion.

### R-CSE-08 — Cybersecurity action space (15 actions)
**Expected outcome:** All 15 actions (SCAN_SURFACE, EXPLOIT_CVE, LATERAL_MOVE, ESCALATE_PRIVILEGES, PIVOT_TARGET, MONITOR, DETECT, INVESTIGATE, ESCALATE_TO_CISO, PATCH, DEPLOY_CONTROL, ROTATE_CREDENTIAL, FILE_CRA_NOTIFICATION, NOTIFY_BOARD, ACKNOWLEDGE) are defined, logged, and produce correct state changes in `AttackSurfaceServer`.

### R-CSE-09 — Action logging (JSONL)
**Expected outcome:** `CyberActionLogger` writes valid JSONL to `cyber_actions.jsonl` for all 15 action types. `simulation_start`, `round_start`, and per-action entries all written correctly.

### R-CSE-10 — Agent working memory (SQLite)
**Expected outcome:** `CyberMemoryUpdater` writes agent activities to per-run `cyber_agent_memory.db` via Queue + background thread (batch_size=5). Batch of 5 activities flushed to ArangoDB `agent_action_logs` collection with `episode_text` readable.

### R-CSE-11 — Post-simulation report generation
**Expected outcome:** `CyberReportAgent` executes ReACT loop with 3 AQL tools (deep_chain_analysis, timeline_reconstruction, agent_state_query). Produces report with `chain_probability`, `soc_miss_probability`, `tef_estimate`, `board_narrative`, `top_3_actions` in < 30 seconds.

### R-CSE-12 — Write-back integration
**Expected outcome:** After `CyberReportAgent` completes, `SimulationWritebackService.run_all()` is called with report payload. ArangoDB `attack_chain_findings`, `threat_category_rollups`, `business_impact_findings` all populated. `SituationAbstractionLayer` returns updated CISO/Board views from new data.

### R-CSE-13 — CSE API endpoints
**Expected outcome:**
- `POST /v1/cse/simulations/create` — validates seed data, starts CSE run, returns `{sim_id, status: "queued"}`
- `GET /v1/cse/simulations/{sim_id}/status` — returns run state from `simulation_runs` + `run_state.json`
- Previous `/v1/mirofish/trigger` and `/v1/mirofish/status/` endpoints are removed

### R-CSE-14 — mirofish module removal
**Expected outcome:** `src/complira_graph/mirofish/` module (trigger_client.py, seed_extractor.py, __init__.py) removed. `src/api/v1/endpoints/mirofish.py` removed. All imports and router registrations updated. No dead code.

### R-CSE-15 — Concurrent tenant isolation
**Expected outcome:** Two concurrent tenant simulations run without cross-contamination. Each run has isolated `data/simulations/{tenant}/{sim_id}/` directory, isolated SQLite, isolated IPC directories.

---

## Acceptance Criteria

| AC ID | Requirement | Expected Outcome |
|-------|-------------|-----------------|
| AC-CSE-01 | R-CSE-01 | `CyberSimulationRunner.start_simulation()` transitions state to RUNNING; `run_state.json` shows `status: running` |
| AC-CSE-02 | R-CSE-01 | `stop_simulation()` sends CLOSE_ENV IPC command and transitions to STOPPED |
| AC-CSE-03 | R-CSE-02 | INJECT_VARIABLE IPC command dispatched and response received in < 5s |
| AC-CSE-04 | R-CSE-02 | Unknown IPC command returns error response; simulation does not crash |
| AC-CSE-05 | R-CSE-03 | `CompliraGraphReader.get_attack_surface()` returns ≥ 1 `CyberEntityNode` for demo tenant |
| AC-CSE-06 | R-CSE-03 | Response time < 200ms for typical tenant (< 100 CVEs) |
| AC-CSE-07 | R-CSE-04 | `generate_all()` returns 5 valid profile dicts (one per agent type) |
| AC-CSE-08 | R-CSE-05 | `simulation_config.json` has `cra_deadline_round: 24`, `hours_per_round: 1`, `total_rounds: 48` for KEV trigger |
| AC-CSE-09 | R-CSE-06 | CREATED → READY transition writes both `run_state.json` and `simulation_config.json` |
| AC-CSE-10 | R-CSE-07 | 48-round simulation completes; `run_state.json` shows `status: completed` |
| AC-CSE-11 | R-CSE-08 | Patching a CVE removes it from `AttackSurfaceServer` exploitable list |
| AC-CSE-12 | R-CSE-08 | EXPLOIT_CVE action sets chain step in `AttackSurfaceServer` state |
| AC-CSE-13 | R-CSE-09 | 100-round simulation produces JSONL with all 15 action type strings present |
| AC-CSE-14 | R-CSE-10 | Batch of 5 `CyberAgentActivity` objects flushed to `agent_action_logs` with `episode_text` present |
| AC-CSE-15 | R-CSE-11 | `CyberReportAgent` returns report with non-null `chain_probability` and `board_narrative` |
| AC-CSE-16 | R-CSE-12 | After write-back, `GET /v1/situation/ciso` returns updated `posture_score` |
| AC-CSE-17 | R-CSE-12 | No CVE IDs in `/v1/situation/ciso` or `/v1/situation/board` after write-back |
| AC-CSE-18 | R-CSE-13 | `POST /v1/cse/simulations/create` returns 200 with `sim_id` for valid tenant |
| AC-CSE-19 | R-CSE-13 | `POST /v1/cse/simulations/create` returns 422 when attack surface is empty |
| AC-CSE-20 | R-CSE-14 | No imports of `complira_graph.mirofish` remain in codebase after removal |
| AC-CSE-21 | R-CSE-15 | Two concurrent tenant runs write to separate `data/simulations/{tenant}/` directories with no cross-contamination |

---

## Constraints / Dependencies

- `SimulationWritebackService` (built) — CSE calls `run_all(payload)` after report generation
- `SituationAbstractionLayer` (built) — reads from ArangoDB collections CSE writes
- ArangoDB simulation collections (provisioned) — `attack_chain_findings`, `threat_category_rollups`, `business_impact_findings`, `posture_snapshots`, `simulation_runs`, `simulation_agent_logs`
- **`agent_action_logs` collection must be added** to `scripts/init_simulation_schema.py` (gap found in investigation)
- Per-run SQLite for agent working memory (not ArangoDB — avoids per-round network round-trips)
- Python 3.11+, FastAPI, python-arango, `aiosqlite` or `sqlite3` (stdlib)
- LLM provider: Claude `claude-sonnet-4-6` (primary); Ollama swap-ability is a future concern
- Frontend: Next.js (existing dashboard) — MiroFish Vue.js frontend is NOT adopted
- `data/simulations/{tenant_id}/{sim_id}/` directory layout — configurable via `Settings.CSE_DATA_DIR`

---

## Assumptions

- The 8-week plan in `cse_impl_plan_v1.1.docx` represents the full delivery scope for this ticket
- `src/complira_graph/cse/` is the canonical Python package path
- `subprocess.Popen` with `sys.executable` + module path (`-m complira_graph.cse.run_parallel_cyber_simulation`) is the subprocess invocation pattern
- OpenAEV integration (section 12) is out of scope for this ticket
- Ollama/qwen provider swap (Week 8 hardening) is in scope for this ticket
- MiroFish frontend (section 10) is superseded by Next.js approach

---

## Open Questions / Risks

| # | Question | Risk if wrong | Resolution |
|---|----------|--------------|------------|
| OQ-1 | Subprocess invocation: `sys.executable -m module` vs console_scripts entry point? | Wrong path breaks subprocess launch | Resolve in Stage 3 design — use `sys.executable -m` pattern |
| OQ-2 | Claude API rate limits for 5 concurrent asyncio LLM calls in profile generator? | Profile generation fails for larger tenants | Add sequential fallback with `asyncio.Semaphore(3)` |
| OQ-3 | SQLite `check_same_thread=False` needed for `CyberMemoryUpdater` background thread? | Thread safety error on SQLite write | Yes — confirmed needed in design |
| OQ-4 | `agent_action_logs` AQL schema — which fields are indexed? | Slow debrief queries | Add `sim_id + agent_id` composite index in schema migration |

---

## Requirement Coverage Map

| Requirement ID | Use Case IDs (from Stage 4 call stacks) |
|---------------|----------------------------------------|
| R-CSE-01 | UC-CSE-01 (runner lifecycle) |
| R-CSE-02 | UC-CSE-02 (IPC dispatch) |
| R-CSE-03 | UC-CSE-03 (graph extraction) |
| R-CSE-04 | UC-CSE-04 (profile generation) |
| R-CSE-05 | UC-CSE-05 (config synthesis) |
| R-CSE-06 | UC-CSE-06 (preparation pipeline) |
| R-CSE-07 | UC-CSE-07 (parallel execution) |
| R-CSE-08 | UC-CSE-08 (attack surface state) |
| R-CSE-09 | UC-CSE-09 (action logging) |
| R-CSE-10 | UC-CSE-10 (memory updater) |
| R-CSE-11 | UC-CSE-11 (report agent) |
| R-CSE-12 | UC-CSE-12 (write-back integration) |
| R-CSE-13 | UC-CSE-13 (API endpoints) |
| R-CSE-14 | UC-CSE-14 (mirofish removal) |
| R-CSE-15 | UC-CSE-15 (tenant isolation) |

*(Use case IDs assigned in Stage 4 runtime call stacks)*

## Acceptance Criteria Coverage Map

| AC ID | Stage 7 Scenario IDs |
|-------|---------------------|
| AC-CSE-01 | S-CSE-01 |
| AC-CSE-02 | S-CSE-01 |
| AC-CSE-03 | S-CSE-02 |
| AC-CSE-04 | S-CSE-02 |
| AC-CSE-05 | S-CSE-03 |
| AC-CSE-06 | S-CSE-03 |
| AC-CSE-07 | S-CSE-04 |
| AC-CSE-08 | S-CSE-05 |
| AC-CSE-09 | S-CSE-06 |
| AC-CSE-10 | S-CSE-07 |
| AC-CSE-11 | S-CSE-08 |
| AC-CSE-12 | S-CSE-08 |
| AC-CSE-13 | S-CSE-09 |
| AC-CSE-14 | S-CSE-10 |
| AC-CSE-15 | S-CSE-11 |
| AC-CSE-16 | S-CSE-12 |
| AC-CSE-17 | S-CSE-12 |
| AC-CSE-18 | S-CSE-13 |
| AC-CSE-19 | S-CSE-13 |
| AC-CSE-20 | S-CSE-14 |
| AC-CSE-21 | S-CSE-15 |

*(Scenario IDs assigned in Stage 7)*
