# Future-State Runtime Call Stack Review: Phase 6

**Ticket:** `phase-6-api-exposure`
**Scope:** Small
**Date:** 2026-03-22
**Clean-Review Streak:** 0

---

## Round 1 — Deep Review

**Date:** 2026-03-22
**Status:** In Progress

### Per-Use-Case Review

#### UC-P6-001 — GET findings, Phase 1+2 fields returned

| Check | Result | Notes |
| --- | --- | --- |
| Architecture fit | Pass | Pure response model extension — correct layer |
| Layering fitness | Pass | Endpoint → AQL → Pydantic model; no layer violations |
| Boundary placement | Pass | Field mapping in endpoint is correct; not leaking into service layer |
| Existing-structure bias | Pass | Consistent with existing inline AQL pattern |
| Anti-hack check | Pass | No bypass tricks |
| Local-fix degradation | Pass | Extension only, no degradation |
| Terminology / vocabulary | Pass | Field names match pipeline output names exactly |
| File/API naming clarity | Pass | `ScanFindingResponse` naming is clear |
| Name-to-responsibility alignment | Pass | Model name matches responsibility |
| Future-state alignment | Pass | Matches design basis |
| Use-case coverage completeness | Pass | Primary + fallback (empty list) + error (404, 500) covered |
| Use-case source traceability | Pass | REQ-P6-001 |
| Requirement coverage closure | Pass | REQ-P6-001 fully covered |
| Design-risk use-case justification | N/A | Requirement-sourced |
| Business flow completeness | Pass | All Phase 1+2 fields enumerated |
| Layer-appropriate SoC | Pass | Field extraction in endpoint, validation in Pydantic model |
| Dependency flow smells | Pass | None |
| Redundancy/duplication | Pass | None |
| Simplification opportunity | Pass | No over-engineering |
| Decommission/cleanup | Pass | No removals needed |
| No-legacy check | Pass | Clean extension |
| Overall verdict | **Pass** | |

#### UC-P6-002 — GET scan_run, Phase 2 fields + summary

| Check | Result | Notes |
| --- | --- | --- |
| Architecture fit | Pass | 3 AQL queries is appropriate; summary computed at request time |
| Layering fitness | Pass | All computation in endpoint layer, consistent with existing pattern |
| Boundary placement | Pass | |
| Existing-structure bias | Pass | Inline AQL, no new repository |
| Anti-hack check | Pass | |
| Local-fix degradation | Pass | |
| Terminology / vocabulary | Pass | `phase2_summary`, `llm_token_usage` are clear |
| File/API naming | Pass | `Phase2Summary`, `LLMTokenUsage` are clear |
| Name-to-responsibility alignment | Pass | |
| Future-state alignment | Pass | |
| Use-case coverage completeness | Pass | Primary + fallback (no findings → zeros/null) + error (404) covered |
| Use-case source traceability | Pass | REQ-P6-002, REQ-P6-006 |
| Requirement coverage closure | Pass | Both REQs covered |
| Business flow completeness | **Blocker** | **FINDING-R1-01**: The 3 AQL queries for summary stats could be combined into fewer queries. Current design calls 3 separate AQL executions. The trend counts and avg_blast_radius can be done in a single query using `COLLECT` + `AGGREGATE`. This is a simplification opportunity that should be resolved before implementation. |
| Layer-appropriate SoC | Pass | |
| Dependency flow smells | Pass | |
| Redundancy/duplication | **Fail** | **FINDING-R1-01** (same): 3 separate queries when 2 suffice — trend+avg in one, top-5 in another |
| Simplification opportunity | **Fail** | **FINDING-R1-01**: Merge trend-counts + avg_blast_radius into one AQL `COLLECT/AGGREGATE` query |
| Decommission/cleanup | Pass | |
| No-legacy check | Pass | |
| Overall verdict | **Fail** | FINDING-R1-01 requires design update |

#### UC-P6-003 — Filter by epss_trend

| Check | Result | Notes |
| --- | --- | --- |
| Architecture fit | Pass | |
| Layering fitness | Pass | Pydantic Literal validation at query param level is correct |
| Boundary placement | Pass | |
| Existing-structure bias | Pass | |
| Anti-hack check | Pass | bind_vars prevents AQL injection |
| Local-fix degradation | Pass | |
| Terminology / vocabulary | Pass | |
| File/API naming | Pass | |
| Name-to-responsibility alignment | Pass | |
| Future-state alignment | Pass | |
| Use-case coverage completeness | Pass | Primary + error (422) covered |
| Use-case source traceability | Pass | REQ-P6-003 |
| Requirement coverage closure | Pass | |
| Business flow completeness | Pass | |
| Layer-appropriate SoC | Pass | |
| Dependency flow smells | Pass | |
| Redundancy/duplication | Pass | |
| Simplification opportunity | Pass | |
| Decommission/cleanup | Pass | |
| No-legacy check | Pass | |
| Overall verdict | **Pass** | |

#### UC-P6-004 — Filter by min_blast_radius

| Check | Result | Notes |
| --- | --- | --- |
| Architecture fit | Pass | FastAPI `Query(ge=0.0, le=1.0)` validation is correct layer |
| Layering fitness | Pass | |
| Boundary placement | Pass | |
| Existing-structure bias | Pass | |
| Anti-hack check | Pass | bind_vars only |
| All other checks | Pass | |
| Overall verdict | **Pass** | |

#### UC-P6-005 — Sort by Phase 2 field

| Check | Result | Notes |
| --- | --- | --- |
| Architecture fit | Pass | |
| Layering fitness | Pass | |
| Boundary placement | Pass | |
| Anti-hack check | **Blocker** | **FINDING-R1-02**: `sort_clause = f"SORT f.{sort_by} DESC"` uses f-string interpolation with user-provided value into AQL. Although FastAPI `Literal` validation constrains the value to known safe strings, the implementation plan shows string interpolation. This should be replaced with a safe mapping: `_SORT_FIELDS = {"blast_radius_score": "f.blast_radius_score", "epss_velocity": "f.epss_velocity"}` to avoid any f-string AQL interpolation pattern, even if currently safe. Belt-and-suspenders defense. |
| Future-state alignment | Pass | |
| Use-case coverage completeness | Pass | |
| Use-case source traceability | Pass | REQ-P6-005 |
| Simplification opportunity | Pass | |
| Overall verdict | **Fail** | FINDING-R1-02: Replace f-string sort interpolation with allow-list mapping |

#### UC-P6-006 — Combined filters (Design-Risk)

| Check | Result | Notes |
| --- | --- | --- |
| Architecture fit | Pass | |
| Layering fitness | Pass | |
| Boundary placement | Pass | |
| Anti-hack check | Pass | All values in bind_vars, no filter clause interpolation |
| Future-state alignment | Pass | Confirms AND-semantics and combined AQL work correctly |
| Design-risk justification quality | Pass | Clear objective: verify combined AQL + bind_var correctness |
| Expected observable outcome | Pass | "AQL with all three filter clauses AND'd, SORT by epss_velocity DESC" — clear and testable |
| Use-case coverage completeness | Pass | Primary path sufficient for risk validation |
| Overall verdict | **Pass** | |

---

### Missing-Use-Case Discovery Sweep

| Category | Finding |
| --- | --- |
| Requirement coverage | All 6 REQs covered by at least one use case ✓ |
| Boundary crossings | tenant_id scoping present in all AQL queries ✓ |
| Fallback/error branches | Empty findings (200 OK) covered in UC-P6-001; no-blast-radius-data (null avg) covered in UC-P6-002 |
| Design-risk scenarios | UC-P6-006 covers combined-filter AQL correctness |
| New use cases needed | None discovered |

---

### Round 1 Findings Summary

| ID | Use Case | Check | Severity | Description |
| --- | --- | --- | --- | --- |
| FINDING-R1-01 | UC-P6-002 | Redundancy/Simplification | Blocking | 3 AQL queries for summary stats — merge trend-counts + avg_blast_radius into single COLLECT/AGGREGATE query; keep top-5 as separate |
| FINDING-R1-02 | UC-P6-005 | Anti-hack / AQL injection defense | Blocking | f-string interpolation for sort field — replace with allow-list dict mapping |

**Round 1 Verdict:** `Fail` — 2 blocking findings require design update

**Classification:** `Design Impact` (clear, bounded, high-confidence — AQL pattern fixes)

**Return path:** `Stage 3 → Stage 4 → Stage 5`

**Clean-review streak:** Reset to 0

---

### Applied Updates After Round 1

**Transition to Stage 3:** Update `implementation-plan.md` with:
1. Merge summary stats AQL from 3 queries to 2 (trend+avg COLLECT in one; top-5 in another)
2. Replace f-string sort interpolation with allow-list dict mapping

**Transition to Stage 4:** Regenerate affected UC-P6-002 and UC-P6-005 call stacks (v1 → v2)

---

## Round 2 — Deep Review (after Stage 3 → 4 updates)

**Date:** 2026-03-22
**Status:** Complete
**Design Basis Version:** implementation-plan.md v2, future-state-runtime-call-stack.md v2

### Applied Updates From Round 1

| Finding | Update Applied | Files Changed |
| --- | --- | --- |
| FINDING-R1-01 | Merged 3 summary AQL queries into 2: Query 1 = trend counts + avg in one LET/COLLECT; Query 2 = top-5 | implementation-plan.md (C2 section), future-state-runtime-call-stack.md (UC-P6-002) |
| FINDING-R1-02 | Replaced f-string sort interpolation with `_SORT_FIELD_MAP` allow-list dict | implementation-plan.md (C2 section), future-state-runtime-call-stack.md (UC-P6-005) |

### Per-Use-Case Review (Round 2)

#### UC-P6-001 — All fields returned (unchanged from Round 1 Pass)

| Check | Result |
| --- | --- |
| All checks (from Round 1) | Pass (unchanged) |
| No new issues discovered | ✓ |
| Overall verdict | **Pass** |

#### UC-P6-002 — Scan run summary (updated: 2 AQL queries)

| Check | Result | Notes |
| --- | --- | --- |
| Architecture fit | Pass | 2 AQL queries sufficient |
| Layering fitness | Pass | |
| Boundary placement | Pass | |
| Existing-structure bias | Pass | |
| Anti-hack check | Pass | All values via bind_vars |
| Local-fix degradation | Pass | |
| Terminology / vocabulary | Pass | |
| File/API naming | Pass | |
| Name-to-responsibility alignment | Pass | |
| Future-state alignment | Pass | Matches v2 design |
| Use-case coverage completeness | Pass | Primary + fallback (no findings → zeros/null) + error |
| Use-case source traceability | Pass | REQ-P6-002, REQ-P6-006 |
| Requirement coverage closure | Pass | |
| Business flow completeness | Pass | FINDING-R1-01 resolved; 2-query approach correct |
| Layer-appropriate SoC | Pass | |
| Redundancy/duplication | Pass | Resolved |
| Simplification opportunity | Pass | Resolved |
| Decommission/cleanup | Pass | |
| No-legacy check | Pass | |
| Overall verdict | **Pass** | |

#### UC-P6-003 — Filter by epss_trend (unchanged from Round 1 Pass)

All checks Pass (unchanged). **Overall: Pass**.

#### UC-P6-004 — Filter by min_blast_radius (unchanged from Round 1 Pass)

All checks Pass (unchanged). **Overall: Pass**.

#### UC-P6-005 — Sort by Phase 2 field (updated: allow-list sort)

| Check | Result | Notes |
| --- | --- | --- |
| Architecture fit | Pass | |
| Anti-hack check | Pass | FINDING-R1-02 resolved — `_SORT_FIELD_MAP` dict maps to hardcoded AQL strings; no user input interpolated |
| Future-state alignment | Pass | Matches v2 design |
| All other checks | Pass | |
| Overall verdict | **Pass** | |

#### UC-P6-006 — Combined filters Design-Risk (unchanged from Round 1 Pass)

All checks Pass (unchanged). **Overall: Pass**.

### Missing-Use-Case Discovery Sweep (Round 2)

| Category | Finding |
| --- | --- |
| Requirement coverage | All 6 REQs covered ✓ |
| Boundary crossings | tenant_id scoping in all AQL queries ✓ |
| Fallback/error branches | All null/empty cases handled ✓ |
| Design-risk scenarios | UC-P6-006 covers combined-filter risk ✓ |
| New use cases needed | None discovered ✓ |

### Round 2 Summary

| Check | Result |
| --- | --- |
| All 6 use cases Pass | ✓ |
| No blocking findings | ✓ |
| No new use cases discovered | ✓ |
| No required artifact updates | ✓ |

**Round 2 Verdict:** `Pass — Candidate Go`
**Clean-review streak:** 1

---

## Round 3 — Stability Confirmation

**Date:** 2026-03-22
**Status:** Complete

No changes to design basis since Round 2. This round confirms stability.

### Checklist

| Gate Go Criterion | Status |
| --- | --- |
| Architecture fit — all use cases | Pass |
| Layering fitness — all use cases | Pass |
| Boundary placement — all use cases | Pass |
| Existing-structure bias — all use cases | Pass |
| Anti-hack check — all use cases | Pass |
| Terminology/vocabulary — all use cases | Pass |
| File/API naming clarity — all use cases | Pass |
| Name-to-responsibility alignment — all use cases | Pass |
| Future-state alignment — all use cases | Pass |
| Layer-appropriate SoC — all use cases | Pass |
| Use-case coverage completeness — all use cases | Pass |
| Use-case source traceability — all use cases | Pass |
| Requirement coverage closure | Pass (6/6 REQs) |
| Design-risk justification quality | Pass (UC-P6-006) |
| Redundancy/duplication — all use cases | Pass |
| Simplification opportunity — all use cases | Pass |
| Decommission/cleanup | Pass |
| No-legacy check | Pass |
| No unresolved blocking findings | Pass |
| No new use cases in this round | ✓ |

### Missing-Use-Case Discovery Sweep (Round 3)

No new use cases. No artifact updates required.

**Round 3 Verdict:** `Pass — Go Confirmed`
**Clean-review streak:** 2 ✓

---

## Final Gate Decision

**Gate: Go Confirmed** — Two consecutive clean rounds (Round 2 + Round 3) with no blockers, no artifact updates required, no new use cases discovered.

Implementation may proceed. Stage 6 unlocked.
