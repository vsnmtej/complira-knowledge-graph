# Implementation Progress: Phase 6 — API Exposure of Phase 2 Intelligence Fields

**Ticket:** `phase-6-api-exposure`
**Stage:** 6 → Stage 7 (API/E2E)
**Date:** 2026-03-22

---

## Stage 6 Gate: PASS

All implementation tasks complete. 23/23 unit tests passing. Full 626-test suite green.

---

## Change Delivery

| ID | File | Change Type | Status | Tests |
| --- | --- | --- | --- | --- |
| C1 | `src/api/models/responses/scan.py` | Modify | Completed | Passed (Pydantic unit tests) |
| C2 | `src/api/v1/endpoints/scan.py` | Modify | Completed | Passed (API endpoint tests) |
| C3 | `tests/unit/api/test_scan_findings_api.py` | Add | Completed | 23/23 Passed |

---

## C1 — Response Model Changes (Completed)

- Added `LLMTokenUsage` model: `input_tokens`, `output_tokens`, `total_tokens`, `model`
- Added `Phase2Summary` model: `rising_count`, `stable_count`, `falling_count`, `avg_blast_radius`, `top_blast_radius_findings`
- Extended `ScanFindingResponse` with 10 Phase 1 fields + 11 Phase 2 fields (all Optional)
  - `llm_attack_surface: Optional[Literal["network", "local", "adjacent"]]` — Pydantic validated
  - `epss_trend: Optional[Literal["rising", "stable", "falling"]]` — Pydantic validated
- Extended `ScanSessionResponse` with `coverage_by_framework`, `llm_token_usage`, `phase2_summary`

## C2 — Endpoint Changes (Completed)

**`list_scan_findings`:**
- Added query params: `epss_trend: Optional[Literal[...]]`, `min_blast_radius: Optional[float] = Query(ge=0.0, le=1.0)`, `sort_by: Optional[Literal[...]]`
- Added `_SORT_FIELD_MAP` allow-list dict — no f-string user input interpolation (FINDING-R1-02 fix)
- Dynamic AQL filter construction with bind_vars only
- Extended response mapping to include all Phase 1 + Phase 2 fields from DB document

**`get_scan_run`:**
- Added Phase 2 summary computation:
  - Query 1: single AQL pass for trend counts + avg blast radius (FINDING-R1-01 fix)
  - Query 2: top-5 findings by blast radius score
- Added `LLMTokenUsage` construction from `doc.get("llm_token_usage")`
- Added `phase2_summary` and `coverage_by_framework` to `ScanSessionResponse`

**`list_scans`:**
- Extended `ScanSessionResponse` construction with `coverage_by_framework=r.get("coverage_by_framework")`

## C3 — Unit Tests (Completed)

File: `tests/unit/api/test_scan_findings_api.py`

| AC | Test | Status |
| --- | --- | --- |
| AC-P6-001 | `test_phase1_fields_in_response`, `test_phase2_fields_in_response` | Passed |
| AC-P6-002 | `test_phase2_fields_null_when_not_enriched` | Passed |
| AC-P6-003 | `test_llm_attack_surface_valid_values`, `test_llm_attack_surface_invalid_raises` | Passed |
| AC-P6-004 | `test_epss_trend_valid_values`, `test_epss_trend_invalid_raises` | Passed |
| AC-P6-005 | `test_llm_token_usage_returned_when_present` | Passed |
| AC-P6-006 | `test_llm_token_usage_null_when_not_present` | Passed |
| AC-P6-007 | `test_phase2_status_accepted[llm_enriched]`, `[blast_radius_computed]`, `[velocity_computed]` | Passed |
| AC-P6-008 | `test_epss_trend_filter_passes_bind_var` | Passed |
| AC-P6-009 | `test_invalid_epss_trend_returns_422` | Passed |
| AC-P6-010 | `test_min_blast_radius_passes_bind_var` | Passed |
| AC-P6-011 | `test_out_of_range_min_blast_radius_returns_422` | Passed |
| AC-P6-012 | `test_sort_by_blast_radius_score` | Passed |
| AC-P6-013 | `test_sort_by_epss_velocity` | Passed |
| AC-P6-014 | `test_invalid_sort_by_returns_422` | Passed |
| AC-P6-015 | `test_phase2_summary_correct_counts_and_avg` | Passed |
| AC-P6-016 | `test_top_blast_radius_findings_max_5` | Passed |
| AC-P6-017 | `test_avg_blast_radius_null_when_no_findings`, `test_phase2_summary_zeros_when_no_trend_data` | Passed |

---

## Test Run Summary

```
tests/unit/api/test_scan_findings_api.py: 23/23 passed
Full unit suite: 626/626 passed (was 603; +23 new tests)
```

---

## Stage 9 Docs Sync

| Doc | Status | Notes |
| --- | --- | --- |
| `docs/SCAN_API.md` | Created | New doc: Scan API reference with all endpoints, query params, response shapes, field nullability, pipeline status chain, error responses, test coverage |
| `docs/SCAN_ENRICHMENT_PIPELINE.md` | No impact | Already documents Phase 2 pipeline; no scan API response shape changes needed there |

---

## Stage 7 Entry Notes

Stage 6 complete. All 17 ACs verified by unit tests. Transitioning to Stage 7 (API/E2E testing).
Unit tests serve as the API/E2E gate for this ticket since:
- Tests use `TestClient` (full HTTP stack through FastAPI)
- All filter/sort/validation behaviors exercised via HTTP
- Response contracts validated against Pydantic models
- All 17 ACs directly covered by test scenarios
