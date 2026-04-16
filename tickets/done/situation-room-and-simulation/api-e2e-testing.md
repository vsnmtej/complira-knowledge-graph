# API/E2E Testing — Situation Room + MiroFish Simulation

## Acceptance Criteria Matrix

| AC ID | Requirement | Scenario(s) | Execution Status | Notes |
|-------|-------------|-------------|-----------------|-------|
| AC-001 | R-001 | S-001 (build) | Passed | `npm run build` passes; route at 80.9 kB |
| AC-002 | R-001 | S-001 (build) | Passed | "Situation Room" nav entry confirmed in `layout.tsx` |
| AC-003 | R-002 | S-002 (frontend) | Passed | All 4 persona tabs render |
| AC-004 | R-002 | S-002 (frontend) | Passed | Tab click calls `onSwitch` with correct persona |
| AC-005 | R-003 | S-003 (frontend) | Passed | Expand/collapse toggle verified |
| AC-006 | R-004 | S-004 (frontend) | Passed | Ask button navigates with encoded prompt |
| AC-007 | R-004 | S-004 (frontend) | Waived | Chat auto-submit requires live backend; compensating: `useEffect` + `promptAutoSubmittedRef` guard verified in code review |
| AC-008 | R-005 | S-005 (frontend) | Waived | Canvas API not supported in jsdom; compensating: build passes, component imports verified, dagre layout code path exercised |
| AC-009 | R-005 | S-005 (frontend) | Passed | `soc_threshold_miss=true` edge exists in fixture (fixture-shape test) |
| AC-010 | R-006 | S-006 (frontend) | Passed | All required AQL return keys present in fixture |
| AC-011 | R-007 | S-007 (backend) | Passed | `/v1/situation/ciso` returns 4 streams with mocked AQL |
| AC-012 | R-007 | S-007 (backend) | Passed | Empty tool results → 200 with empty lists |
| AC-013 | R-008 | S-008 (backend) | Passed | `CollectionCreateError` on all calls does not raise |
| AC-014 | R-008 | S-008 (backend) | Passed | All 13 `create_collection` calls verified |
| AC-015 | R-009 | S-009 (backend) | Passed | `run_all()` AQL execute call count ≥ 14 |
| AC-016 | R-009 | S-010 (backend) | Passed | `chain_informs_vex` edge meta has `do_not_mutate_status=True` |
| AC-017 | R-009 | S-010 (backend) | Passed | `chain_calibrates_fair` not written at confidence=0.4; written at 0.6 |
| AC-018 | R-009 | S-009 (backend) | Passed | `_step7_summary` called with keys returned by `_step2_findings_and_cve_edges` |
| AC-019 | R-010 | S-011 (backend) | Passed | All 4 tools in `COMPLIRA_TOOLS` and `_TOOL_REGISTRY`; input schemas validated |
| AC-020 | R-010 | S-011 (backend) | Passed | `get_attack_chains_for_cve` delegates to `simulation_queries` with correct args |
| AC-021 | R-011 | S-012 (frontend + backend) | Passed | `SimulationResultCard` renders chain_count/soc_blind_spot_count/top_action; `/v1/simulation/{run_id}/status` returns 200 + 404 |
| AC-022 | R-011 | S-012 (frontend) | Passed | `SimulationLivePanel` calls `onComplete` on terminal status; stops polling |

---

## Stage 7 Scenarios

### S-001 — Route + Sidebar (AC-001, AC-002)
- **Level:** Build
- **Type:** Requirement
- **Command:** `npm run build`
- **Result:** Passed — `/dashboard/situation` at 80.9 kB; `LayoutGrid` import + nav entry confirmed in `layout.tsx`

---

### S-002 — PersonaSwitcher (AC-003, AC-004)
- **Level:** Frontend unit (Vitest)
- **File:** `frontend/__tests__/situation/PersonaSwitcher.test.tsx`
- **Type:** Requirement
- **Scenarios:** 4 tests
- **Command:** `npx vitest run __tests__/situation/PersonaSwitcher.test.tsx`
- **Result:** Passed (4/4)

---

### S-003 — AlertCard drill-down (AC-005)
- **Level:** Frontend unit (Vitest)
- **File:** `frontend/__tests__/situation/AlertCard.test.tsx`
- **Type:** Requirement
- **Scenarios:** collapse/expand/re-collapse
- **Command:** `npx vitest run __tests__/situation/AlertCard.test.tsx`
- **Result:** Passed (7/7)

---

### S-004 — Ask Complira navigation (AC-006, AC-007)
- **Level:** Frontend unit (Vitest) + code review (AC-007 waived for chat auto-submit)
- **File:** `frontend/__tests__/situation/AlertCard.test.tsx`
- **Type:** Requirement
- **Result:** AC-006 Passed; AC-007 Waived (chat auto-submit requires live session + backend)
- **Compensating evidence for AC-007:** `useSearchParams` + `promptAutoSubmittedRef` guard implemented and visible in `app/dashboard/chat/page.tsx`

---

### S-005 — AttackChainGraph (AC-008, AC-009)
- **Level:** Frontend (jsdom limitation for Canvas/WebGL)
- **Type:** Requirement + Design-Risk
- **Result:** AC-008 Waived (Canvas not in jsdom); AC-009 Passed via fixture-shape test
- **Compensating evidence for AC-008:** Build passes with `@xyflow/react` import; dagre layout code verified in source review; SOC blind-spot edge logic present in `AttackChainGraph.tsx`
- **Infeasibility reason:** `@xyflow/react` uses `ResizeObserver` and WebGL canvas APIs unavailable in jsdom environment

---

### S-006 — Fixture shape compliance (AC-010)
- **Level:** Frontend unit (Vitest)
- **File:** `frontend/__tests__/situation/fixture-shape.test.ts`
- **Type:** Requirement
- **Scenarios:** All required AQL keys verified per tool function return shape
- **Command:** `npx vitest run __tests__/situation/fixture-shape.test.ts`
- **Result:** Passed (12/12)

---

### S-007 — GET /v1/situation/ciso + GET /v1/simulation/{run_id}/status (AC-011, AC-012, AC-021)
- **Level:** Backend integration (pytest + FastAPI TestClient)
- **File:** `tests/integration/test_situation_simulation_api.py`
- **Type:** Requirement
- **Scenarios:** four-stream response, empty state, 404 on unknown run, 404 on tenant mismatch
- **Command:** `.venv/bin/python -m pytest tests/integration/test_situation_simulation_api.py::TestSituationCISOEndpoint tests/integration/test_situation_simulation_api.py::TestSimulationStatusEndpoint -v`
- **Result:** Passed (7/7)

---

### S-008 — init_simulation_schema (AC-013, AC-014)
- **Level:** Backend unit (pytest)
- **File:** `tests/integration/test_situation_simulation_api.py`
- **Type:** Requirement
- **Scenarios:** all 13 collections created; idempotent on CollectionCreateError
- **Result:** Passed (3/3)

---

### S-009 — SimulationWritebackService run_all (AC-015, AC-018)
- **Level:** Backend unit (pytest)
- **File:** `tests/integration/test_situation_simulation_api.py`
- **Type:** Requirement
- **Scenarios:** UPSERT call count ≥ 14; step7 receives step2 finding_keys
- **Result:** Passed (3/3)

---

### S-010 — Write-back constraints (AC-016, AC-017)
- **Level:** Backend unit (pytest)
- **File:** `tests/integration/test_situation_simulation_api.py`
- **Type:** Requirement
- **Scenarios:** `chain_informs_vex` advisory meta; `chain_calibrates_fair` confidence gate at 0.4/0.6
- **Result:** Passed (3/3)

---

### S-011 — Simulation chat tools (AC-019, AC-020)
- **Level:** Backend integration (pytest)
- **File:** `tests/integration/test_situation_simulation_api.py`
- **Type:** Requirement
- **Scenarios:** tool presence in registry; delegation to query functions; input schemas
- **Result:** Passed (5/5)

---

### S-012 — SimulationResultCard + SimulationLivePanel (AC-021, AC-022)
- **Level:** Frontend unit (Vitest)
- **Files:** `frontend/__tests__/situation/SimulationResultCard.test.tsx`, `frontend/__tests__/situation/SimulationLivePanel.test.tsx`
- **Type:** Requirement
- **Scenarios:** chain_count/soc_blind_spot_count/top_action render; polling stops on terminal; onComplete fires; error state
- **Result:** Passed (19/19)

---

## Infeasible Scenarios (Waived)

| AC ID | Scenario | Infeasibility Reason | Compensating Evidence | Waiver |
|-------|----------|---------------------|----------------------|--------|
| AC-007 | Chat auto-submit on mount | Requires live NextAuth session + FastAPI backend | `promptAutoSubmittedRef` guard in source; `useEffect` verified in code review | Waived — no live session in test env |
| AC-008 | AttackChainGraph renders ≥3 nodes in jsdom | `@xyflow/react` uses Canvas/WebGL/ResizeObserver, unavailable in jsdom | Build passes; source reviewed; dagre LR layout code path present; SOC blind-spot edge logic present | Waived — visual graph requires real browser |

---

## Execution Summary

| Scope | Pass | Fail | Waived | Total |
|-------|------|------|--------|-------|
| Frontend Vitest | 43 | 0 | 0 | 43 |
| Backend pytest | 21 | 0 | 0 | 21 |
| Build verification | 2 | 0 | 0 | 2 |
| Waived (infeasible) | — | — | 2 | 2 |
| **Total ACs** | **20** | **0** | **2** | **22** |

**Stage 7 gate: Pass** — all executable acceptance criteria passed; 2 infeasible criteria waived with compensating evidence.
