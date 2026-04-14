# Implementation Plan — cse-simulation-engine

## Basis

- Design: `proposed-design.md` v2
- Call Stacks: `future-state-runtime-call-stack.md` v2
- Stage 5 Gate: `Go Confirmed` (Round 3)

---

## Execution Strategy

Bottom-up: foundational modules first, then orchestration, then API, then frontend.
Each group builds on the previous. Tests written alongside each file.

---

## Task Groups

### Group 1 — Foundation (no external deps beyond stdlib + arango)

| Task | Change ID | File | Type | Dependencies |
|------|-----------|------|------|--------------|
| T-01 | C-017 | `src/complira_graph/config.py` | Modify | None |
| T-02 | C-018 | `scripts/init_simulation_schema.py` | Modify | None |
| T-03 | C-004 | `src/complira_graph/cse/action_logger.py` | Add | None |
| T-04 | C-010 | `src/complira_graph/cse/attack_surface_server.py` | Add | None |
| T-05 | C-003 | `src/complira_graph/cse/ipc.py` | Add | None |

### Group 2 — Memory + Graph

| Task | Change ID | File | Type | Dependencies |
|------|-----------|------|------|--------------|
| T-06 | C-005 | `src/complira_graph/cse/memory_updater.py` | Add | T-01 (config) |
| T-07 | C-006 | `src/complira_graph/cse/graph_reader.py` | Add | T-01 (config) |

### Group 3 — Profile + Config Generation

| Task | Change ID | File | Type | Dependencies |
|------|-----------|------|------|--------------|
| T-08 | C-007 | `src/complira_graph/cse/profile_generator.py` | Add | T-07 (graph_reader), T-01 |
| T-09 | C-008 | `src/complira_graph/cse/config_generator.py` | Add | T-07, T-08 |

### Group 4 — Simulation Loops + Runner

| Task | Change ID | File | Type | Dependencies |
|------|-----------|------|------|--------------|
| T-10 | C-011 | `src/complira_graph/cse/attacker_simulation.py` | Add | T-03, T-04, T-05, T-06 |
| T-11 | C-012 | `src/complira_graph/cse/defender_simulation.py` | Add | T-03, T-04, T-05, T-06 |
| T-12 | C-013 | `src/complira_graph/cse/run_parallel_cyber_simulation.py` | Add | T-10, T-11, T-05 |
| T-13 | C-002 | `src/complira_graph/cse/runner.py` | Add | T-05, T-12 |

### Group 5 — Report + Manager + Package Init

| Task | Change ID | File | Type | Dependencies |
|------|-----------|------|------|--------------|
| T-14 | C-014 | `src/complira_graph/cse/report_agent.py` | Add | T-01 |
| T-15 | C-009 | `src/complira_graph/cse/simulation_manager.py` | Add | T-07→T-14, T-13 |
| T-16 | C-001 | `src/complira_graph/cse/__init__.py` | Add | T-15 |

### Group 6 — API + Router

| Task | Change ID | File | Type | Dependencies |
|------|-----------|------|------|--------------|
| T-17 | C-015 | `src/api/v1/endpoints/cse.py` | Add | T-15, T-16 |
| T-18 | C-016 | `src/api/v1/router.py` | Modify | T-17 |

### Group 7 — mirofish Removal

| Task | Change ID | File | Type | Dependencies |
|------|-----------|------|------|--------------|
| T-19 | C-020 | `src/complira_graph/mirofish/trigger_client.py` | Remove | T-18 (router updated) |
| T-20 | C-021 | `src/complira_graph/mirofish/seed_extractor.py` | Remove | T-18 |
| T-21 | C-022 | `src/complira_graph/mirofish/__init__.py` | Remove | T-18 |
| T-22 | C-023 | `src/api/v1/endpoints/mirofish.py` | Remove | T-18 |

### Group 8 — Frontend

| Task | Change ID | File | Type | Dependencies |
|------|-----------|------|------|--------------|
| T-23 | C-019b | `frontend/components/situation/SimulationLivePanel.tsx` | Modify | T-17 (CSE API) |
| T-24 | C-019c | `frontend/components/situation/SimulationResultCard.tsx` | Modify | T-17 |
| T-25 | C-019d | `frontend/app/dashboard/situation/page.tsx` | Modify | None |
| T-26 | C-019 | `frontend/app/dashboard/simulation/page.tsx` | Add | T-23, T-24 |

---

## Unit Test Coverage Plan

| File | Test File | Key Test Scenarios |
|------|-----------|-------------------|
| `action_logger.py` | `tests/unit/cse/test_action_logger.py` | All 15 action types logged; simulation_start + round_start; valid JSONL |
| `attack_surface_server.py` | `tests/unit/cse/test_attack_surface_server.py` | PATCH removes CVE; EXPLOIT_CVE adds chain step; all 15 actions produce state change |
| `ipc.py` | `tests/unit/cse/test_ipc.py` | Command file written; response read; unknown command error; timeout |
| `memory_updater.py` | `tests/unit/cse/test_memory_updater.py` | Batch of 5 flushed to SQLite; flush_remaining; check_same_thread=False |
| `graph_reader.py` | `tests/integration/cse/test_graph_reader.py` | Returns ≥1 CyberEntityNode; empty → []; < 200ms |
| `profile_generator.py` | `tests/unit/cse/test_profile_generator.py` | 5 profiles returned; Semaphore(3); rate limit retry |
| `config_generator.py` | `tests/unit/cse/test_config_generator.py` | total_rounds=48 for kev; cra_deadline_round=24; simulation_config.json written |
| `runner.py` | `tests/unit/cse/test_runner.py` | State transitions; run_state.json written; stop sends CLOSE_ENV |
| `simulation_manager.py` | `tests/integration/cse/test_simulation_manager.py` | prepare() returns sim_id; CREATED→READY; empty surface → ValueError |
| `report_agent.py` | `tests/unit/cse/test_report_agent.py` | ReACT loop; 3 AQL tools; returns chain_probability + board_narrative |
| `cse.py` endpoint | `tests/integration/cse/test_cse_api.py` | POST create 200; POST create 422; GET status 200; GET status 404 |

---

## Requirement Traceability

| Requirement | Tasks | Test Coverage |
|-------------|-------|---------------|
| R-CSE-01 | T-13 | test_runner.py |
| R-CSE-02 | T-05 | test_ipc.py |
| R-CSE-03 | T-07 | test_graph_reader.py |
| R-CSE-04 | T-08 | test_profile_generator.py |
| R-CSE-05 | T-09 | test_config_generator.py |
| R-CSE-06 | T-15 | test_simulation_manager.py |
| R-CSE-07 | T-12 | test_simulation_manager.py (integration) |
| R-CSE-08 | T-04 | test_attack_surface_server.py |
| R-CSE-09 | T-03 | test_action_logger.py |
| R-CSE-10 | T-06 | test_memory_updater.py |
| R-CSE-11 | T-14 | test_report_agent.py |
| R-CSE-12 | T-15 | test_simulation_manager.py |
| R-CSE-13 | T-17 | test_cse_api.py |
| R-CSE-14 | T-19→T-22 | grep verification |
| R-CSE-15 | T-13, T-15 | test_simulation_manager.py (two-tenant scenario) |
