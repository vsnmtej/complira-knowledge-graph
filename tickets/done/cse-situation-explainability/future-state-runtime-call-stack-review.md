# Runtime Call Stack Review — cse-situation-explainability

**Review Round:** 1  
**Date:** 2026-04-17  
**Artifact:** `future-state-runtime-call-stack.md` v1  

---

## Findings

### F-001 — Logic Error (Medium)
**UC:** UC-01  
**Issue:** `_AQL_CHAIN_NARRATIVES_FOR_BUCKET` does a nested loop: for each rollup it queries
`attack_chain_findings` filtered by `r.run_id`. But the outer loop iterates over ALL rollups
for the tenant — if there are 3 buckets (remote_code_execution, patch_gaps, lateral_movement),
the AQL fires 3 separate DB round-trips per `compute_ciso()` call.

For the current scale (≤5 buckets per tenant) this is fine. But the AQL itself has a bug:
the outer `FOR r IN threat_category_rollups FILTER r.bucket_name == @bucket_name LIMIT 1`
returns only 1 rollup row, then the inner loop reads findings for that `run_id`. If multiple
simulation runs exist, only the most recent rollup's `run_id` is used — which is correct, but
only guaranteed if rollups are sorted by recency. The current `_AQL_THREAT_CATEGORY_ROLLUP`
sorts by `max_chain_probability DESC`, not by time. If an older run had higher probability,
`LIMIT 1` would pick the wrong rollup.

**Required correction:** Add `SORT r.computed_at DESC LIMIT 1` to
`_AQL_CHAIN_NARRATIVES_FOR_BUCKET` (independent of probability) to always use the most
recent rollup's run_id.

**Classification:** Logic Error  
**Action:** Update UC-01 AQL and C-05 implementation note.

---

### F-002 — Missing Edge Case (Low)
**UC:** UC-02, UC-04  
**Issue:** `_build_exposure_derivation()` constructs `narrative` using
`top_cf.get("impact_if_applied", "") or ""`. If `counterfactuals` is an empty list
(simulation completed but report agent returned no counterfactuals due to fallback),
`top_cf = {}` and the narrative ends with an empty string, producing:
`"Exposure of $1.2M–$5.1M is derived from 2 confirmed attack chains with 91% breach
probability. "` — a trailing space and incomplete sentence.

**Required correction:** Guard the narrative assembly:
```python
impact = (top_cf.get("impact_if_applied") or "").strip()
narrative = (
    f"Exposure of ${low_m:.1f}M–${high_m:.1f}M derived from "
    f"{chain_count} confirmed attack chain{'s' if chain_count != 1 else ''} "
    f"({breach_probability_pct:.0f}% breach probability)."
    + (f" {impact}" if impact else "")
)
```

**Classification:** Missing Edge Case  
**Action:** Update UC-02 `_build_exposure_derivation()` code snippet.

---

### F-003 — Interface Gap (Low)
**UC:** UC-05  
**Issue:** The call stack shows `cisoAlerts()` receiving the full `CISOSituation` object and
accessing `ciso.threat_category_explanations`. But the current `cisoAlerts()` function
signature is `cisoAlerts(s: CISOSituation)` and the new field is `threat_category_explanations`
(optional, defaults to `[]`). This is compatible. However, the frontend TypeScript interface
`CISOSituation` needs `threat_category_explanations?: ThreatCategoryExplanation[]` added
(C-08) before `cisoAlerts()` can compile. The call stack should note this dependency
explicitly.

**Classification:** Interface Gap (documentation only)  
**Action:** Add dependency note to UC-05 — C-08 must be completed before C-09.

---

## Round 1 Gate Decision: Candidate Go (F-001 correction needed, F-002/F-003 minor)

---

## Review Round 2 (2026-04-17)

Corrections applied to proposed-design.md and call-stack:

| Finding | Fix |
|---------|-----|
| F-001 | `_AQL_CHAIN_NARRATIVES_FOR_BUCKET` adds `SORT r.computed_at DESC` before `LIMIT 1` |
| F-002 | `_build_exposure_derivation()` guards trailing space with conditional append |
| F-003 | UC-05 dependency note added: C-08 TypeScript types must precede C-09 |

No new findings in Round 2 scan.

**Round 2 Gate Decision: Go Confirmed**  
**Stage 5 Result: PASS**  
**Advance to Stage 6 — Source Implementation**
