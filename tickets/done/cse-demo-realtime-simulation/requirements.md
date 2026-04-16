# Requirements — cse-demo-realtime-simulation

**Status:** Design-ready
**Scope:** Large
**Branch:** codex/cse-demo-realtime-simulation

---

## Goal / Problem Statement

The Complira platform has a complete CSE simulation engine (Attacker + Defender agents, runner, IPC, action logger, memory updater, report agent, writeback) and a Situation Room with 4 personas. However:

1. **No Regulator agent** — only Attacker and Defender run in the simulation. The Regulator persona (compliance auditor) is missing as a distinct simulation actor.
2. **Engineering and RegAffairs personas are fixture-only** — the Situation Room shows static JSON data for these two personas; no live simulation data flows there.
3. **No SSE streaming** — the frontend polls every 3 seconds. A full demo requires real-time round-by-round streaming so viewers see agents acting as it happens.
4. **No live patch priority data** — Engineering persona needs a live endpoint serving ranked CVE patch priorities computed from the latest simulation run.
5. **No live regulatory deadline data** — RegAffairs persona needs a live endpoint serving compliance gap findings surfaced by the Regulator agent.

The goal is to deliver a **complete, demoable end-to-end experience**: trigger a simulation run → watch three agent personas (Attacker, Defender, Regulator) act in real time via SSE streaming → see Situation Room update across all four personas (CISO, Board, Engineering, RegAffairs) from live simulation data.

---

## In-Scope Use Cases

| ID | Use Case | Source Type |
|---|---|---|
| UC-01 | Regulator agent runs in simulation — monitors game state, issues compliance gap findings, notifies board | Requirement |
| UC-02 | Simulation runner executes three concurrent coroutines: Attacker, Defender, Regulator | Requirement |
| UC-03 | SSE streaming endpoint emits round events as they are written to `agent_action_logs` | Requirement |
| UC-04 | Frontend SimulationLivePanel consumes SSE stream and renders live round events by persona | Requirement |
| UC-05 | Engineering persona shows live patch priority data from latest simulation (not fixture) | Requirement |
| UC-06 | RegAffairs persona shows live regulatory deadlines from Regulator agent gap findings | Requirement |
| UC-07 | Regulator agent actions include AUDIT_VULNERABILITY, ISSUE_COMPLIANCE_FINDING, FILE_INCIDENT_REPORT, NOTIFY_REGULATOR, APPROVE_EXCEPTION | Requirement |
| UC-08 | Simulation completes → Situation Room CISO/Board/Engineering/RegAffairs all show live data from the run | Requirement |
| UC-09 | SSE stream closes cleanly when simulation status becomes COMPLETED or FAILED | Design-Risk |
| UC-10 | Regulator agent does not race-condition with Defender on AttackSurfaceServer (shared mutable state) | Design-Risk |
| UC-11 | Engineering live endpoint gracefully returns empty state when no simulation has run | Design-Risk |
| UC-12 | SSE stream backpressure — slow client does not block agent loop | Design-Risk |

---

## Acceptance Criteria

| ID | Criterion | Verifiable Outcome |
|---|---|---|
| AC-001 | Regulator agent class exists with its own action set | `regulator_simulation.py` importable; `run_regulator_loop()` executes without error for 5 rounds in unit test |
| AC-002 | Regulator actions include AUDIT_VULNERABILITY, ISSUE_COMPLIANCE_FINDING, FILE_INCIDENT_REPORT, NOTIFY_REGULATOR, APPROVE_EXCEPTION | All 5 action constants defined in attack_surface_server.py and handled by `apply_action()` |
| AC-003 | Three-coroutine simulation runs end-to-end | `run_parallel_cyber_simulation.py` runs Attacker + Defender + Regulator; all finish without error for N=3 rounds in unit test |
| AC-004 | SSE endpoint exists at `GET /v1/cse/simulations/{sim_id}/stream` | Endpoint returns `Content-Type: text/event-stream`; emits at least one `data:` event for a known run |
| AC-005 | SSE events include agent_type, round_no, action_type, outcome fields | Each emitted event parses to a valid JSON dict with those 4 fields |
| AC-006 | SSE stream closes with `event: done` when simulation status is COMPLETED | Client receives `event: done` after run completes |
| AC-007 | SimulationLivePanel consumes SSE and renders events by agent persona colour | Frontend renders events with correct persona labels (Attacker/Defender/Regulator) |
| AC-008 | `GET /v1/situation/engineering` returns patch priority list from latest simulation | Response includes `patch_priority` array; top entry has `cve_id`, `composite_score`, `patch_urgency` fields |
| AC-009 | `GET /v1/situation/reg_affairs` returns regulatory deadline list from latest simulation gap findings | Response includes `regulatory_deadlines` array; entries have `title`, `regulatory_labels`, `hours_remaining`, `urgency_tier` fields |
| AC-010 | Situation Room Engineering persona renders from live API not fixture | `SituationRoomPage` calls `/v1/situation/engineering`; fixture fallback only on API error |
| AC-011 | Situation Room RegAffairs persona renders from live API not fixture | `SituationRoomPage` calls `/v1/situation/reg_affairs`; fixture fallback only on API error |
| AC-012 | All 76 existing CSE unit tests continue to pass | `pytest tests/unit/cse/ -q` exits 0 |
| AC-013 | Regulator agent unit tests written and passing | `tests/unit/cse/test_regulator_simulation.py` — at least 6 tests passing |
| AC-014 | SSE endpoint unit test written and passing | `tests/unit/cse/test_cse_api.py` — SSE streaming scenario added |

---

## Constraints / Dependencies

- Must not break existing 76 CSE unit tests
- Regulator agent uses same LLM call pattern as Attacker/Defender (Claude Haiku via Anthropic SDK)
- `AttackSurfaceServer` is the shared mutable state; Regulator reads but minimally writes (compliance gap findings only)
- SSE endpoint uses FastAPI `StreamingResponse` with `text/event-stream` content type
- `agent_action_logs` collection is the source of truth for SSE events (poll-from-DB approach — no in-memory queue needed)
- Engineering live data derives from `attack_chain_findings` + EPSS/CVE metadata already in the reference graph
- RegAffairs live data derives from `compliance_gap_findings` written by the Regulator agent + `incidents` with CRA/FDA labels
- No changes to the `SimulationWritebackService` contract (payload schema is frozen)
- Frontend changes target `simulation/page.tsx`, `SimulationLivePanel.tsx`, `situation/page.tsx` only

---

## Assumptions

- ArangoDB collections `agent_action_logs`, `compliance_gap_findings`, `attack_chain_findings` exist and are populated after a simulation run
- The simulation runs as a background asyncio task (FastAPI background task) — SSE polling queries ArangoDB, not an in-memory queue
- Three-agent simulation adds ~50% execution time overhead (acceptable for demo)
- Regulator agent uses the same `CyberActionLogger` and `CyberMemoryUpdater` as Attacker/Defender
- Engineering patch priority is computed on-request from graph data (not pre-computed); acceptable latency for demo

---

## Open Questions / Risks

| ID | Question | Risk Level |
|---|---|---|
| OQ-01 | Should SSE poll ArangoDB or use an in-memory asyncio Queue? | Medium — DB poll is simpler and stateless; Queue is faster but requires process-scoped state |
| OQ-02 | Regulator concurrency model: dedicated coroutine or interleaved with Defender? | Medium — dedicated coroutine is cleaner; interleaved is simpler but reduces persona distinction |
| OQ-03 | Engineering live data: compute from `attack_chain_findings` + CVE metadata vs. pre-compute at writeback | Low — on-request computation is correct; if slow, add a query index |
| OQ-04 | How to handle SSE when simulation is already COMPLETED before client connects? | Low — emit all historical events then `event: done` |

---

## Scope Triage

**Scope: Large**

Rationale:
- New domain module (`regulator_simulation.py`)
- Modified orchestration module (`run_parallel_cyber_simulation.py`)
- New API endpoint (`SSE stream`)
- Two new Situation Room API endpoints (`/situation/engineering`, `/situation/reg_affairs`)
- Frontend changes across 3 files
- New unit tests for Regulator agent
- Multi-layer impact: agent domain → orchestration → API → frontend

---

## Requirement Coverage Map (to call-stack use cases)

| Requirement | Use Case |
|---|---|
| Regulator agent | UC-01, UC-07, UC-10 |
| Three-coroutine runner | UC-02 |
| SSE streaming endpoint | UC-03, UC-09, UC-12 |
| Frontend SSE consumption | UC-04 |
| Engineering live endpoint | UC-05, UC-11 |
| RegAffairs live endpoint | UC-06, UC-11 |
| End-to-end demo flow | UC-08 |

---

## Acceptance Criteria Coverage Map (to Stage 7 scenarios)

| AC | Stage 7 Scenario |
|---|---|
| AC-001 | S-001: Regulator loop runs 5 rounds without error |
| AC-002 | S-002: All 5 Regulator action constants resolvable by apply_action() |
| AC-003 | S-003: Three-coroutine run completes for N=3 rounds |
| AC-004 | S-004: SSE endpoint returns 200 text/event-stream |
| AC-005 | S-005: SSE event JSON fields validation |
| AC-006 | S-006: SSE stream emits done event on COMPLETED status |
| AC-007 | S-007: Frontend renders Regulator events (Playwright or component test) |
| AC-008 | S-008: Engineering endpoint returns valid patch_priority array |
| AC-009 | S-009: RegAffairs endpoint returns valid regulatory_deadlines array |
| AC-010 | S-010: Situation Room calls live engineering endpoint |
| AC-011 | S-011: Situation Room calls live reg_affairs endpoint |
| AC-012 | S-012: Existing 76 CSE tests still pass |
| AC-013 | S-013: Regulator unit tests pass |
| AC-014 | S-014: SSE API unit test passes |
