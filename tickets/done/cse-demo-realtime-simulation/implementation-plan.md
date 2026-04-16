# Implementation Plan — cse-demo-realtime-simulation

## Scope Classification

- Classification: `Large`
- Reasoning: 12 change items across agent domain (subprocess), orchestration, API, situation abstraction, and frontend. Multi-layer: new module, 7 modified modules, 2 new API routes, 1 new SSE endpoint, 1 new test file, 1 modified test file.
- Workflow Depth: `Large` → proposed design → runtime call stacks → review → implementation plan → progress tracking → API/E2E testing → code review → docs sync

---

## Upstream Artifacts (Required)

- Workflow state: `tickets/in-progress/cse-demo-realtime-simulation/workflow-state.md`
- Investigation notes: `tickets/in-progress/cse-demo-realtime-simulation/investigation-notes.md`
- Requirements: `tickets/in-progress/cse-demo-realtime-simulation/requirements.md` — `Design-ready`
- Runtime call stacks: `tickets/in-progress/cse-demo-realtime-simulation/future-state-runtime-call-stack.md` — `v2`
- Runtime review: `tickets/in-progress/cse-demo-realtime-simulation/future-state-runtime-call-stack-review.md` — `Go Confirmed`
- Proposed design: `tickets/in-progress/cse-demo-realtime-simulation/proposed-design.md` — `v2`

---

## Plan Maturity

- Current Status: `Ready For Implementation`
- Notes: Stage 5 Go Confirmed after 3 rounds (1 Design Impact round resolved via v2 artifacts, 2 clean rounds).

---

## Preconditions (All Met)

- `requirements.md` is `Design-ready`: Yes
- Acceptance criteria use stable IDs with measurable outcomes: Yes (AC-001 through AC-014)
- `workflow-state.md` is current with Stage 5 evidence: Yes
- Runtime call stack review artifact is current: Yes (v2)
- All 12 in-scope use cases reviewed: Yes
- No unresolved blocking findings: Yes
- `Go Confirmed` with two consecutive clean rounds: Yes (Rounds 2 + 3)
- Missing-use-case discovery sweeps completed for final two clean rounds: Yes
- No newly discovered use cases in final two rounds: Yes

---

## Runtime Call Stack Review Gate Summary

| Round | Result | Findings Requiring Updates | New UCs | Updates Completed | Classification | Re-Entry Path | Round State | Clean Streak |
|---|---|---|---|---|---|---|---|---|
| 1 | Fail | Yes | No | Yes | Design Impact | Stage 3 → Stage 4 → Stage 5 | Reset | 0 |
| 2 | Pass | No | No | N/A | N/A | N/A | Candidate Go | 1 |
| 3 | Pass | No | No | N/A | N/A | N/A | Go Confirmed | 2 |

---

## Go / No-Go Decision

- Decision: `Go`
- Final review round: 3
- Clean streak at final round: 2
- `Implementation can start`: Yes

---

## Principles

- Bottom-up: agent domain first, then orchestration, then API, then frontend, then tests
- No backward-compatibility shims (setInterval removal is clean-cut)
- `apply_action()` signature unchanged — no breaking change to existing callers
- One file at a time; cross-references flagged explicitly

---

## Dependency And Sequencing Map

| Order | Task ID | File | Depends On | Why This Order |
|---|---|---|---|---|
| 1 | T-01 | `cse/attack_surface_server.py` | Nothing | Foundation: new action constants + handlers + state fields used by all agents |
| 2 | T-02 | `cse/regulator_simulation.py` | T-01 | New agent uses surface_server Regulator actions |
| 3 | T-03 | `cse/run_parallel_cyber_simulation.py` | T-02 | Wires third coroutine + writes compliance_gaps.json |
| 4 | T-04 | `cse/report_agent.py` | T-03 | Reads compliance_gaps.json from sim_dir |
| 5 | T-05 | `simulation/simulation_manager.py` (writeback payload) | T-04 | Reads report["compliance_gaps"]; sends to writeback |
| 6 | T-06 | `api/v1/endpoints/cse.py` | T-03 | SimulationRegistry + SSE endpoint (depends on sim_dir pattern from T-03) |
| 7 | T-07 | `situation/abstraction_layer.py` | T-05 | compute_engineering + compute_reg_affairs read from ArangoDB after writeback |
| 8 | T-08 | `api/v1/endpoints/situation.py` | T-07 | New routes call abstraction layer methods |
| 9 | T-09 | `frontend/components/situation/SimulationLivePanel.tsx` | T-06 | SSE endpoint must exist first (for integration) |
| 10 | T-10 | `frontend/app/dashboard/situation/page.tsx` | T-08 | Live endpoints must exist |
| 11 | T-11 | `tests/unit/cse/test_regulator_simulation.py` | T-01, T-02 | Unit tests for new Regulator agent |
| 12 | T-12 | `tests/unit/cse/test_cse_api.py` | T-06 | SSE unit test scenario |

---

## Requirement And Design Traceability

| Requirement | AC IDs | Design Section | Use Case | Task ID(s) | Stage 6 Verification | Stage 7 Scenario(s) |
|---|---|---|---|---|---|---|
| Regulator agent | AC-001, AC-013 | C-01 | UC-01 | T-02, T-11 | Unit: test_regulator_simulation.py | S-001, S-013 |
| Regulator actions | AC-002 | C-02 | UC-07 | T-01, T-11 | Unit: apply_action handler tests | S-002 |
| Three-coroutine runner | AC-003 | C-03 | UC-02 | T-03, T-11 | Unit: run_parallel test | S-003 |
| SSE endpoint | AC-004, AC-005, AC-006, AC-014 | C-06 | UC-03, UC-09 | T-06, T-12 | Unit: test_cse_api.py SSE scenario | S-004, S-005, S-006, S-014 |
| Frontend SSE | AC-007 | C-09 | UC-04 | T-09 | Manual smoke (demo) | S-007 |
| Engineering endpoint | AC-008, AC-010 | C-07, C-08 | UC-05, UC-11 | T-07, T-08 | Unit: abstraction_layer tests | S-008, S-010 |
| RegAffairs endpoint | AC-009, AC-011 | C-07, C-08 | UC-06, UC-11 | T-07, T-08 | Unit: abstraction_layer tests | S-009, S-011 |
| Existing 76 CSE tests | AC-012 | — | — | All T-01..T-06 | Unit: pytest tests/unit/cse/ | S-012 |

---

## Acceptance Criteria To Stage 7 Mapping

| AC ID | Requirement | Expected Outcome | Stage 7 Scenario | Test Level | Status |
|---|---|---|---|---|---|
| AC-001 | Regulator agent class | `run_regulator_loop()` executes 5 rounds without error | S-001 | API (via run) | Planned |
| AC-002 | Regulator action constants | All 5 constants defined + handled in apply_action() | S-002 | API | Planned |
| AC-003 | Three-coroutine run | asyncio.gather with 3 agents runs N=3 rounds without error | S-003 | API | Planned |
| AC-004 | SSE endpoint exists | GET /v1/cse/simulations/{id}/stream returns 200 text/event-stream | S-004 | API | Planned |
| AC-005 | SSE event fields | Each emitted event has round_no, agent_type, action_type, outcome | S-005 | API | Planned |
| AC-006 | SSE done event | Client receives `event: done` after run completes | S-006 | API | Planned |
| AC-007 | Frontend SSE render | SimulationLivePanel renders Attacker/Defender/Regulator events | S-007 | E2E (Playwright or smoke) | Planned |
| AC-008 | Engineering endpoint | GET /v1/situation/engineering returns patch_priority array with required fields | S-008 | API | Planned |
| AC-009 | RegAffairs endpoint | GET /v1/situation/reg_affairs returns regulatory_deadlines with required fields | S-009 | API | Planned |
| AC-010 | Engineering live call | SituationRoomPage calls /v1/situation/engineering | S-010 | API/E2E | Planned |
| AC-011 | RegAffairs live call | SituationRoomPage calls /v1/situation/reg_affairs | S-011 | API/E2E | Planned |
| AC-012 | Existing 76 CSE tests | pytest tests/unit/cse/ -q exits 0 | S-012 | Unit | Planned |
| AC-013 | Regulator unit tests | test_regulator_simulation.py ≥6 passing tests | S-013 | Unit | Planned |
| AC-014 | SSE API unit test | test_cse_api.py SSE scenario added and passing | S-014 | API | Planned |

---

## Design Delta Traceability

| Change ID | Change Type | Task ID | Verification |
|---|---|---|---|
| C-01 | Add | T-02, T-11 | Unit: test_regulator_simulation.py |
| C-02 | Modify | T-01, T-11 | Unit: apply_action handler tests |
| C-03 | Modify | T-03 | Unit: run_parallel test |
| C-04 | Modify | T-04 | Unit: report_agent test (read compliance_gaps.json) |
| C-05 | Modify | T-05 | Unit: simulation_manager writeback payload test |
| C-06 | Modify | T-06, T-12 | Unit: test_cse_api.py SSE |
| C-07 | Modify | T-07 | Unit: abstraction_layer compute tests |
| C-08 | Modify | T-08 | API: situation route tests |
| C-09 | Modify | T-09 | E2E/smoke |
| C-10 | Modify | T-10 | E2E/smoke |
| C-11 | Add | T-11 | Unit (is the test file itself) |
| C-12 | Modify | T-12 | API (is the test scenario itself) |

---

## Step-By-Step Plan

1. **T-01** — Modify `attack_surface_server.py`: add 5 Regulator action constants, 5 handler methods, 4 new state fields (`compliance_gaps`, `incident_report_filed`, `regulator_notified`, `exceptions_approved`)
2. **T-02** — Add `regulator_simulation.py`: `run_regulator_loop()` with LLM-driven Regulator agent, fallback heuristic, uses T-01 action constants
3. **T-03** — Modify `run_parallel_cyber_simulation.py`: add `run_regulator_loop` as 3rd coroutine in `asyncio.gather()`; write `compliance_gaps.json` after gather completes
4. **T-04** — Modify `report_agent.py`: read `compliance_gaps.json` from `sim_dir` and include in report dict
5. **T-05** — Modify `simulation_manager.py` (`_build_writeback_payload`): replace hardcoded `[]` with `_build_compliance_gaps(report, sim_id, tenant_id)`
6. **T-06** — Modify `endpoints/cse.py`: add `_SIM_REGISTRY` dict; modify `POST /create` to register `sim_dir`; add `GET /stream` SSE endpoint with JSONL-tailing generator
7. **T-07** — Modify `situation/abstraction_layer.py`: add `compute_engineering(tenant_id)` and `compute_reg_affairs(tenant_id)` with AQL queries
8. **T-08** — Modify `endpoints/situation.py`: add `GET /v1/situation/engineering` and `GET /v1/situation/reg_affairs` routes
9. **T-09** — Modify `SimulationLivePanel.tsx`: replace `setInterval` polling with `EventSource` SSE; add `done` event handler
10. **T-10** — Modify `situation/page.tsx`: call live Engineering + RegAffairs endpoints; fixture fallback on error
11. **T-11** — Add `tests/unit/cse/test_regulator_simulation.py`: ≥6 unit tests for Regulator agent
12. **T-12** — Modify `tests/unit/cse/test_cse_api.py`: add SSE streaming scenario

---

## Per-File Definition Of Done

| Task | File | Implementation Done | Unit Test Criteria | Integration Test Criteria |
|---|---|---|---|---|
| T-01 | `attack_surface_server.py` | 5 constants, 5 handlers, 4 state fields added | Handler tests in T-11 | N/A |
| T-02 | `regulator_simulation.py` | run_regulator_loop() complete with LLM + fallback | ≥6 tests in T-11 pass | N/A |
| T-03 | `run_parallel_cyber_simulation.py` | 3rd coroutine wired + compliance_gaps.json written | 3-coroutine test passes | N/A |
| T-04 | `report_agent.py` | compliance_gaps.json read + report field populated | Unit test for file read | N/A |
| T-05 | `simulation_manager.py` | _build_compliance_gaps() + payload updated | Unit test payload builder | N/A |
| T-06 | `endpoints/cse.py` | SimulationRegistry + /stream endpoint | T-12 SSE test passes | N/A |
| T-07 | `abstraction_layer.py` | compute_engineering() + compute_reg_affairs() | Unit tests with mock DB | N/A |
| T-08 | `endpoints/situation.py` | 2 new routes added | Route test (HTTP 200) | N/A |
| T-09 | `SimulationLivePanel.tsx` | EventSource replaces setInterval | TS compile clean | N/A |
| T-10 | `situation/page.tsx` | Live API calls + fixture fallback | TS compile clean | N/A |
| T-11 | `test_regulator_simulation.py` | ≥6 tests written | All pass (pytest) | N/A |
| T-12 | `test_cse_api.py` | SSE scenario added | SSE test passes | N/A |

---

## Code Review Gate Plan (Stage 8)

- Gate artifact path: `tickets/in-progress/cse-demo-realtime-simulation/code-review.md`
- Scope: all 12 changed/added files + their test files
- Line count measurement: `rg -n "\\S" <file-path> | wc -l`
- Delta measurement: `git diff --numstat codex/cse-simulation-engine...HEAD -- <file-path>`
- Files likely to be large:
  - `attack_surface_server.py` — existing file, adds ~50 lines (handlers + fields)
  - `endpoints/cse.py` — existing file, adds ~80 lines (registry + SSE endpoint)
  - `abstraction_layer.py` — existing file, adds ~80 lines (2 new methods)

| File | Estimated Final Line Count | Adds/Expands | SoC Risk | Required Action |
|---|---|---|---|---|
| `attack_surface_server.py` | ~250 | Yes | Low | Keep |
| `regulator_simulation.py` | ~180 | Yes (new) | Low | Keep |
| `endpoints/cse.py` | ~300 | Yes | Low | Keep |
| `abstraction_layer.py` | ~250 | Yes | Low | Keep |
| `SimulationLivePanel.tsx` | ~200 | No (refactor) | Low | Keep |

---

## Test Strategy

- Unit tests: per-module, mocking DB and LLM calls (same pattern as existing CSE tests)
- Integration tests: not required for this change (all interactions through well-defined file/API boundaries); no cross-process integration test feasible in unit environment
- Stage 7 handoff:
  - Expected AC count: 14 (AC-001 through AC-014)
  - Critical flows: SSE streaming (AC-004–006), Engineering/RegAffairs endpoints (AC-008–009), existing tests regression (AC-012)
  - Expected scenario count: 14 (S-001 through S-014)
  - Known constraints: AC-007 (frontend rendering) may require smoke test rather than automated Playwright (depends on test environment)

---

## API/E2E Testing Scenario Catalog (Stage 7 Input)

| Scenario ID | Source Type | AC ID(s) | Requirement ID | Use Case ID | Test Level | Expected Outcome |
|---|---|---|---|---|---|---|
| S-001 | Requirement | AC-001 | UC-01 | UC-01 | Unit | run_regulator_loop() executes 5 rounds, no exception |
| S-002 | Requirement | AC-002 | UC-07 | UC-07 | Unit | All 5 action constants defined; apply_action() handles each |
| S-003 | Requirement | AC-003 | UC-02 | UC-02 | Unit | asyncio.gather with 3 agents runs N=3 rounds, no exception |
| S-004 | Requirement | AC-004 | UC-03 | UC-03 | API | GET /stream returns 200, Content-Type: text/event-stream |
| S-005 | Requirement | AC-005 | UC-03 | UC-03 | API | Each event JSON has round_no, agent_type, action_type, outcome |
| S-006 | Requirement | AC-006 | UC-09 | UC-09 | API | Stream emits `event: done` after run COMPLETED |
| S-007 | Requirement | AC-007 | UC-04 | UC-04 | E2E | SimulationLivePanel renders Regulator events (smoke/Playwright) |
| S-008 | Requirement | AC-008 | UC-05 | UC-05 | API | GET /situation/engineering → patch_priority array with required fields |
| S-009 | Requirement | AC-009 | UC-06 | UC-06 | API | GET /situation/reg_affairs → regulatory_deadlines with required fields |
| S-010 | Requirement | AC-010 | UC-08 | UC-08 | API | SituationRoomPage calls /v1/situation/engineering live |
| S-011 | Requirement | AC-011 | UC-08 | UC-08 | API | SituationRoomPage calls /v1/situation/reg_affairs live |
| S-012 | Requirement | AC-012 | — | — | Unit | pytest tests/unit/cse/ -q exits 0 (76 existing tests) |
| S-013 | Requirement | AC-013 | UC-01 | UC-01 | Unit | test_regulator_simulation.py ≥6 tests pass |
| S-014 | Requirement | AC-014 | UC-03 | UC-03 | API | test_cse_api.py SSE scenario passes |
