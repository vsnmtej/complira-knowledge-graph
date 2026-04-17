# Code Review — cse-situation-explainability

**Reviewer:** Claude Sonnet 4.6  
**Date:** 2026-04-17  
**Files reviewed:** 5  
**Gate Decision:** PASS — No Blockers  

---

## Summary

| File | Status | Blocker | Major | Minor | Nitpick |
|------|--------|---------|-------|-------|---------|
| `situation/models.py` | PASS | 0 | 0 | 0 | 0 |
| `queries/situation_abstraction_queries.py` | PASS | 0 | 0 | 0 | 1 |
| `situation/abstraction_layer.py` | PASS | 0 | 0 | 0 | 1 |
| `frontend/lib/types/situation.ts` | PASS | 0 | 0 | 0 | 0 |
| `frontend/app/dashboard/situation/page.tsx` | PASS | 0 | 0 | 0 | 0 |

---

## File Reviews

### `situation/models.py` — PASS
`ThreatCategoryExplanation` and `ExposureDerivation` are correctly defined with Optional
fields defaulting to safe values (`[]`, `""`, `None`). Both are placed above their parent
models, so forward-reference issues cannot arise. CVE abstraction boundary comment
preserved on models module. No issues.

### `queries/situation_abstraction_queries.py` — PASS
`_AQL_CHAIN_NARRATIVES_FOR_BUCKET`: F-001 fix (`SORT r.computed_at DESC LIMIT 1`) is
present. Inner join on `f.run_id == r.run_id` correctly limits findings to the rollup's
run. `FILTER f.explanation != null` prevents partial documents from surfacing. `LIMIT 3`
caps response size. No CVE fields returned.

`_AQL_COUNTERFACTUALS_FOR_RUN`: Correctly scoped to tenant + completed status, sorted
by `completed_at DESC`. Returns `counterfactuals`, `chain_count`, `audit_trail` — all
fields written by the report agent, all CVE-free by construction.

- **Nitpick:** `_AQL_CHAIN_NARRATIVES_FOR_BUCKET` is a nested-loop AQL (outer loop over
  rollups, inner over findings). For tenants with many findings per run, this could be
  slow without an index on `attack_chain_findings.run_id`. The existing `LIMIT 3` bounds
  the inner result, so performance is acceptable for current scale. If the collection
  grows beyond ~100k findings, an index on `(run_id, confidence)` would help.

### `situation/abstraction_layer.py` — PASS
`_build_threat_category_explanations`: Exception handler per bucket correctly uses
`continue` (not `break`) so one bucket failure doesn't suppress others. Empty narrative
check (`if not narratives: continue`) is correct. Field extraction guards missing keys
with `.get()`. Clean implementation.

`_build_exposure_derivation`: F-002 fix confirmed — `impact` is stripped and conditionally
appended with `f" {impact}"` only when truthy. Unicode en-dash `\u2013` used for narrative
formatting. `or 0` guards for None exposure values. Clean implementation.

- **Nitpick:** `_build_exposure_derivation` is called with `financial_exposure_low` and
  `financial_exposure_high` which can be `None` when no CFO agent data exists (new tenants).
  The guard `(financial_exposure_low or 0) / 1_000_000` produces `"$0.0M–$0.0M"` in that
  case. This is technically correct but could be confusing. Could conditionally omit the
  range: `f"Exposure range undetermined"` when both are None. Low priority — acceptable
  for current milestone.

### `frontend/lib/types/situation.ts` — PASS
`ThreatCategoryExplanation` and `ExposureDerivation` interfaces correctly defined.
Optional fields on parent interfaces use `?:` (TypeScript optional, not `| undefined`),
matching the Pydantic model's optional default behaviour. No issues.

### `frontend/app/dashboard/situation/page.tsx` — PASS
`cisoAlerts()`: explanation lookup by `bucket_name` is correct and safe (`.find()` returns
`undefined` when no match → optional chain `?.what_would_have_helped` short-circuits).
`detail_rows` augmentation is additive — no existing rows are modified.

`boardAlerts()`: refactored from `const items: AlertItem[] = s.regulatory_fine_risk.map(...)`
to `forEach` + push pattern to support the derivation card prepend. `as const` and
`as AlertItem["severity"]` casts correctly resolve the TypeScript literal union issue. The
derivation card is prepended (first in feed) so it gets visibility before fine-risk cards.

---

## Cross-Cutting Checks

**CVE abstraction boundary:** Both new AQL queries return only `explanation.*` and
`counterfactuals[]` fields, neither of which contain CVE IDs by construction (enforced
by report agent). AC-12 test confirms this. ✓

**Backwards compatibility:** New model fields have defaults (`[]` / `None`). Existing
callers that don't pass these fields continue to work. `model_dump()` serialises them
as `[]` and `null` respectively. ✓

**No new LLM calls:** Both builders assemble data from stored ArangoDB fields. No
inference cost added per API request. ✓

**Error isolation:** Per-bucket exception handler in `_build_threat_category_explanations`
ensures one AQL failure doesn't degrade the entire CISO response. ✓

---

## Gate: PASS
