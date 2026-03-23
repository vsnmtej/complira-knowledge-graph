# Code Review: Phase 6 — API Exposure of Phase 2 Intelligence Fields

**Ticket:** `phase-6-api-exposure`
**Stage:** 8
**Date:** 2026-03-22

---

## Files Reviewed

| File | Change Type | Effective Lines | Changed Lines | Size Policy |
| --- | --- | --- | --- | --- |
| `src/api/models/responses/scan.py` | Modify | 293 | +150/-12 | ≤500 → Normal review |
| `src/api/v1/endpoints/scan.py` | Modify | 472 | +153/-10 | ≤500 → Normal review |
| `tests/unit/api/test_scan_findings_api.py` | Add | 536 | +536/-0 | Test file (policy applies to source only) |

Delta gate: both source files have ≤220 changed lines — no additional design-impact assessment required.

---

## Mandatory Review Checks

### `src/api/models/responses/scan.py`

| Check | Result | Notes |
| --- | --- | --- |
| Separation of concerns / responsibility boundaries | Pass | File owns response model shapes. `LLMTokenUsage`, `Phase2Summary`, `ScanFindingResponse`, `ScanSessionResponse` each own a clear schema responsibility. |
| Architecture/layer boundary consistency | Pass | Models have no business logic; pure Pydantic data shapes. No layer violations. |
| Naming-to-responsibility alignment | Pass | `LLMTokenUsage` = LLM token stats; `Phase2Summary` = aggregate stats; `ScanFindingResponse` = finding API shape. All clear. |
| Duplication/patch-on-patch smells | Pass | No duplication. `LLMTokenUsage` is a proper sub-model, not repeated inline. |
| Test quality | Pass | Pydantic validation tested directly in `TestPydanticValidation`; literal constraints tested. |

### `src/api/v1/endpoints/scan.py`

| Check | Result | Notes |
| --- | --- | --- |
| Separation of concerns | Pass | Endpoint handles: auth → DB fetch → AQL → response assembly. Each step is bounded. |
| Architecture/layer boundary consistency | Pass | Inline AQL pattern is consistent with existing endpoints. No layer violations introduced. |
| Naming-to-responsibility alignment | Pass | `_SORT_FIELD_MAP` is clearly named and does exactly one thing. |
| Duplication / patch smells | Pass | `_SORT_FIELD_MAP` allows-list approach is the correct pattern. No patch-on-patch. |
| Security: AQL injection | Pass | All user-supplied values use bind_vars. `_SORT_FIELD_MAP` provides belt-and-suspenders protection for sort field. `filter_parts` only appends hardcoded clause strings — never user input. |
| Security: tenant isolation | Pass | All AQL queries include `f.tenant_id == @tenant_id` / `AND f.tenant_id == @tenant_id` filter. |
| Query efficiency | Pass | Phase 2 summary uses 2 AQL queries (FINDING-R1-01 fix applied). Query 1 single-pass over findings for trend counts + avg. Query 2 indexed sort for top-5. Both bounded to one scan_run_id. |
| Null handling | Pass | `llm_token_usage_raw = doc.get("llm_token_usage")` → conditional `LLMTokenUsage(**raw) if raw else None`. Correct. |
| Error propagation | Pass | `HTTPException` re-raised; all other exceptions caught as 500. Pattern matches existing endpoints. |
| Test quality | Pass | All endpoint behaviors tested via TestClient: 422 validation, filter bind_vars, sort clause content, summary stats. |

### `tests/unit/api/test_scan_findings_api.py`

| Check | Result | Notes |
| --- | --- | --- |
| Test isolation | Pass | Each test class creates its own mocked DB via `patch("api.core.database.get_reference_db")`. No shared state. |
| Fixture correctness | Pass | `_make_finding` and `_make_scan_run_doc` produce realistic DB documents. `CustomerProfile` constructed correctly with `_key` + `database_name`. |
| AC coverage | Pass | All 17 ACs have at least one test. AC-P6-017 has 2 tests. |
| AQL behavior verification | Pass | `test_sort_by_blast_radius_score` and `test_sort_by_epss_velocity` inspect the actual AQL string passed to the DB mock — verify SORT clause content and field reference. |
| Validation boundary tests | Pass | 422 behavior verified for all 3 invalid-value scenarios (epss_trend, min_blast_radius, sort_by). |

---

## Code Review Summary

| Category | Result |
| --- | --- |
| All source file SoC checks | Pass |
| Architecture/layer consistency | Pass |
| Security (injection, tenant isolation) | Pass |
| Naming clarity | Pass |
| No duplication or hacks | Pass |
| Test quality and AC closure | Pass |
| File size within normal review range | Pass |
| Delta within design-impact threshold | Pass |

---

## Gate Decision: **Pass**

No source changes required. Proceeding to Stage 9 (Docs Sync).
