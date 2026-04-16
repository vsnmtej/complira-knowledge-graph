# Code Review — cse-demo-realtime-simulation

## Stage 8 Entry State

- Entered: 2026-04-15
- Stage 7 gate: Pass (all 14 ACs, 91 unit tests, infeasibility waivers documented)
- Code Edit Permission: Locked

---

## Scope

Changed/new source files reviewed:

| File | Type | Effective Lines | Changed Lines | SoC Risk Tier |
|---|---|---|---|---|
| `src/complira_graph/cse/attack_surface_server.py` | Modify | 291 | ~100 | Normal |
| `src/complira_graph/cse/regulator_simulation.py` | Add | 178 | 178 (new) | Normal |
| `src/complira_graph/cse/run_parallel_cyber_simulation.py` | Modify | 105 | ~30 | Normal |
| `src/complira_graph/cse/report_agent.py` | Modify | 221 | ~35 | Normal |
| `src/complira_graph/cse/simulation_manager.py` | Modify | 248 | ~50 | Normal |
| `src/api/v1/endpoints/cse.py` | Modify | 307 | ~202 | Normal |
| `src/complira_graph/situation/abstraction_layer.py` | Add | 552 | 552 (new) | **SoC split assessment required (501–700)** |
| `src/api/v1/endpoints/situation.py` | Add | 113 | 113 (new) | Normal |
| `frontend/components/situation/SimulationLivePanel.tsx` | Modify | ~180 | ~103 | Normal |
| `frontend/app/dashboard/situation/page.tsx` | Modify | ~350 | ~40 | Normal |

Test files (not scored for line limits):
- `tests/unit/cse/test_regulator_simulation.py` (new, 14 tests)
- `tests/unit/cse/test_report_agent.py` (new, 7 tests)
- `tests/unit/cse/test_cse_api.py` (modified, +3 SSE tests)
- `tests/unit/situation/test_situation_api.py` (new, 11 tests)
- `frontend/__tests__/situation/SimulationLivePanel.test.tsx` (rewritten, 8 tests)
- `frontend/__tests__/situation/SimulationResultCard.test.tsx` (rewritten, 11 tests)

---

## Per-File Review

### `attack_surface_server.py` — Modify

| Check | Result | Notes |
|---|---|---|
| Architecture fit | Pass | Regulator actions follow existing action handler pattern exactly |
| Layering fitness | Pass | State machine layer; handlers are pure functions; no leakage |
| Boundary placement | Pass | All Regulator state fields in `AttackSurfaceServer.__init__` alongside existing fields |
| No existing-structure bias | Pass | Added handlers follow `_ACTION_HANDLERS` dict pattern |
| Anti-hack | Pass | No workarounds; handlers are symmetric to attacker/defender actions |
| Local-fix degradation | N/A | New functionality, not a fix |
| Naming clarity | Pass | `compliance_gaps`, `incident_report_filed`, `regulator_notified`, `exceptions_approved` — all self-explanatory |
| Name-to-responsibility | Pass | `AttackSurfaceServer` owns shared simulation state; Regulator state fields are appropriate here |
| Redundancy | Pass | No duplication; handlers reuse `ActionResult` pattern |
| Cleanup | Pass | No dead code; 5 constants, 5 handlers, 4 state fields, all wired |
| No legacy/compat | Pass | No backward compatibility shims |
| **Overall** | **Pass** | |

---

### `regulator_simulation.py` — Add (new file)

| Check | Result | Notes |
|---|---|---|
| Architecture fit | Pass | Mirrors `attacker_simulation.py` / `defender_simulation.py` exactly — correct pattern |
| Layering fitness | Pass | Pure async coroutine; calls surface_server, logger, memory — same boundary as peers |
| Boundary placement | Pass | Subprocess-side only; no imports from parent-process modules |
| No existing-structure bias | Pass | New file; correct placement in `complira_graph/cse/` |
| Anti-hack | Pass | `asyncio.to_thread` for LLM same as attacker/defender |
| Naming clarity | Pass | `run_regulator_loop`, `_decide_action`, `_build_payload`, `_fallback_payload`, `_get_profile` — all clear |
| Name-to-responsibility | Pass | File name matches function: regulator agent loop |
| Redundancy | Pass | `_get_profile` is a local helper; acceptable duplication given subprocess isolation |
| Cleanup | Pass | No dead code |
| No legacy/compat | Pass | Brand new file |
| **Overall** | **Pass** | |

---

### `run_parallel_cyber_simulation.py` — Modify

| Check | Result | Notes |
|---|---|---|
| Architecture fit | Pass | 3rd coroutine added symmetrically; `asyncio.gather` call extended cleanly |
| Layering fitness | Pass | Orchestration layer only; no new cross-layer coupling |
| Boundary placement | Pass | `_write_compliance_gaps()` is subprocess-side helper — correct placement |
| Anti-hack | Pass | File write after gather is the designed subprocess/parent boundary pattern |
| Naming clarity | Pass | `_write_compliance_gaps` — clear intent |
| Redundancy | Pass | No duplication |
| Cleanup | Pass | No dead code; both success and error paths write compliance_gaps.json |
| **Overall** | **Pass** | |

---

### `report_agent.py` — Modify

| Check | Result | Notes |
|---|---|---|
| Architecture fit | Pass | `sim_dir: Path | None = None` added to `run()` signature as optional backward-compat param; clean |
| Layering fitness | Pass | Report agent owns report assembly; reading compliance_gaps.json is in-scope |
| Boundary placement | Pass | `_read_compliance_gaps` is a module-level pure helper — correct |
| Anti-hack | Pass | File read is the cleanest subprocess/parent handoff possible |
| Naming clarity | Pass | `_read_compliance_gaps` matches exactly what it does |
| Redundancy | Pass | No duplication |
| Cleanup | Pass | No dead code |
| **Overall** | **Pass** | |

---

### `simulation_manager.py` — Modify

| Check | Result | Notes |
|---|---|---|
| Architecture fit | Pass | `_build_compliance_gaps()` helper correctly shapes ArangoDB-ready gap records |
| Layering fitness | Pass | Manager layer owns DB write preparation; helper is module-level |
| Boundary placement | Pass | `report_agent.run(sim_dir=runner.sim_dir)` correctly passes sim_dir |
| Anti-hack | Pass | Clean delegation |
| Naming clarity | Pass | `_build_compliance_gaps` unambiguous |
| Redundancy | Pass | No duplication with writeback_service |
| Cleanup | Pass | No dead code |
| **Overall** | **Pass** | |

---

### `endpoints/cse.py` — Modify

| Check | Result | Notes |
|---|---|---|
| Architecture fit | Pass | SimulationRegistry is module-level dict — correct for single-process FastAPI |
| Layering fitness | Pass | SSE streaming logic properly isolated in `_stream_from_jsonl` and `_stream_from_arango` |
| Boundary placement | Pass | Endpoint layer; no domain logic leakage into handlers |
| Anti-hack | Pass | Byte-offset JSONL tail is the correct approach for live streaming without in-memory queues |
| Naming clarity | Pass | `_SIM_REGISTRY`, `_purge_expired_registry`, `_stream_from_jsonl`, `_stream_from_arango` — all clear |
| Name-to-responsibility | Pass | All names match their function |
| Redundancy | Pass | Two stream sources (JSONL, ArangoDB) are intentional and necessary |
| Delta check | Note | 202 changed lines — exceeds 220-line delta gate? Check: 202 < 220 → **within gate** |
| Cleanup | Pass | `_purge_expired_registry` lazy TTL cleanup present; no leaked state |
| No legacy/compat | Pass | No old endpoint preserved |
| **Overall** | **Pass** | |

---

### `situation/abstraction_layer.py` — Add (552 effective lines)

**SoC Split Assessment (mandatory for 501–700 range):**

| Candidate | Current Responsibility | Split Viable? | Decision |
|---|---|---|---|
| AQL queries | 4 long AQL strings embedded in methods | Extract to `situation_abstraction_queries.py` (file already exists as untracked) | **Not required now** — queries are method-local constants, not shared. File `situation_abstraction_queries.py` exists separately. Current approach is acceptable. |
| `compute_engineering` + `compute_reg_affairs` | New methods on `SituationAbstractionLayer` | Could split into separate layer classes | **Not required** — cohesive class, reasonable size; 552 lines includes docstrings and constants |
| `_composite_score` / `_patch_urgency` / `_FRAMEWORK_SLA_HOURS` | Module-level helpers | Already extracted as module-level functions | **Already appropriately split** |

**Conclusion**: 552 effective lines is within the 501–700 SoC assessment range. Split candidates identified but none are required: the class has a single clear responsibility (translate raw graph data to persona-ready output), helpers are already extracted, and the AQL queries are method-local to avoid coupling. No split is mandated.

| Check | Result | Notes |
|---|---|---|
| Architecture fit | Pass | Abstraction layer pattern: isolates persona views from raw graph data |
| Layering fitness | Pass | No CVE IDs returned; enforces abstraction boundary |
| Boundary placement | Pass | One class, one responsibility: situation abstraction |
| Anti-hack | Pass | |
| Naming clarity | Pass | `compute_ciso`, `compute_board`, `compute_engineering`, `compute_reg_affairs` — clear persona mapping |
| Name-to-responsibility | Pass | `SituationAbstractionLayer` — accurate name |
| SoC split assessment | Pass | 552 lines, split candidates assessed, no mandatory split |
| Redundancy | Pass | `get_latest_run_id` is a shared helper — not duplicated |
| Cleanup | Pass | No dead code |
| No legacy/compat | Pass | New file |
| **Overall** | **Pass** | |

---

### `endpoints/situation.py` — Add

| Check | Result | Notes |
|---|---|---|
| Architecture fit | Pass | 4 persona endpoints, symmetric structure |
| Layering fitness | Pass | Thin endpoint layer; delegates to `SituationAbstractionLayer` |
| Boundary placement | Pass | All graph queries behind abstraction layer |
| Naming clarity | Pass | `/situation/engineering`, `/situation/reg_affairs` — clear |
| Redundancy | Pass | No duplication across the 4 endpoints |
| Cleanup | Pass | No dead code |
| **Overall** | **Pass** | |

---

### `SimulationLivePanel.tsx` — Modify (frontend)

| Check | Result | Notes |
|---|---|---|
| Architecture fit | Pass | SSE via EventSource is the correct browser API for server-sent events |
| Layer-appropriate SoC | Pass | Component owns stream lifecycle + state; no logic in render |
| Boundary placement | Pass | Token as query param is documented as demo-acceptable |
| Anti-hack | Pass | Removed setInterval polling entirely — clean cut |
| Naming clarity | Pass | `simId` (not `runId`) aligns with backend `sim_id` field |
| Redundancy | Pass | `displayEvents` fallback to `recent_events` is the correct graceful degradation |
| Cleanup | Pass | Old polling code fully removed |
| No legacy/compat | Pass | `runId` prop removed; clean break |
| **Overall** | **Pass** | |

---

### `situation/page.tsx` — Modify (frontend)

| Check | Result | Notes |
|---|---|---|
| Architecture fit | Pass | `Promise.all` for all 4 endpoints is the correct pattern |
| Layer-appropriate SoC | Pass | Page owns data fetch + state; delegates display to persona components |
| Naming clarity | Pass | `engineeringData`, `regAffairsData` — clear |
| Redundancy | Pass | Fixture fallback is intentional and documented |
| Cleanup | Pass | No dead code |
| **Overall** | **Pass** | |

---

## Test Quality Assessment

| Test File | Test Count | Coverage Quality | Issues |
|---|---|---|---|
| `test_regulator_simulation.py` | 14 | Covers happy path, fallback, error, stop condition, compliance gap append | None |
| `test_report_agent.py` | 7 | Covers `_read_compliance_gaps` edge cases + `run()` with/without sim_dir | None |
| `test_cse_api.py` (added) | +3 | SSE arango fallback, payload content, 404 on empty | None |
| `test_situation_api.py` | 11 | All 4 endpoints: 200, empty list, 503, populated data | None |
| `SimulationLivePanel.test.tsx` | 8 | SSE lifecycle: connect, events, done, error, terminal-on-mount | None |
| `SimulationResultCard.test.tsx` | 11 | New CSERunStatus fields: chain_probability, board_narrative, top_3_actions | None |

---

## Gate Decision

| Category | Result |
|---|---|
| All source files Pass SoC review | Yes |
| `abstraction_layer.py` SoC split assessment completed | Yes — no mandatory split |
| No file exceeds 700 effective lines | Yes (max 552) |
| Delta gate: no single file > 220 changed lines | Yes (max 202 in `cse.py`) |
| No patch-on-patch hacks | Yes |
| No backward compatibility shims | Yes |
| Naming consistent with design document | Yes |
| Test quality acceptable | Yes |

**Code Review Gate Decision: PASS**

Proceed to Stage 9 (Docs Sync).
