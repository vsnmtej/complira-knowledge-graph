# Future-State Runtime Call Stack Review — compliance-violation-mapping

**Design Basis:** `proposed-design.md` v1
**Call Stack Version:** v1

---

## Round 1 — Deep Review

**Date:** 2026-03-22
**Clean-review streak before this round:** 0

---

### Use Case Reviews

#### UC-CV-001: Edge creation for CVE with controls

| Check | Result | Notes |
| --- | --- | --- |
| Architecture fit | Pass | Pipeline→Repository→DB pattern is appropriate and follows established precedent |
| Layering fitness | Pass | AQL in repository, zero AQL in pipeline, coordinator wires stages |
| Boundary placement | Pass | `ScanViolationRepository` owns all traversal AQL; pipeline owns orchestration |
| Existing-structure bias | Pass | New classes introduced; no forced mimicry of inappropriate existing structure |
| Anti-hack | Pass | Clean new collection; no edge-case workarounds |
| Local-fix degradation | N/A | New feature, not a fix |
| Terminology | Pass | `finding_violates_control` is precise; `confidence=1.0` accurately reflects determinism |
| File/API naming | Pass | `ViolationMappingPipeline`, `ScanViolationRepository` are clear and consistent with naming pattern |
| Name-to-responsibility alignment | Pass | Both names accurately describe their scope |
| Future-state alignment | Pass | Call stack matches proposed design exactly |
| Use-case coverage completeness | Pass | Primary path + CVE-not-found error path both covered |
| Use-case source traceability | Pass | REQ-CV-001 |
| Requirement coverage closure | Pass | REQ-CV-001 covered |
| Design-risk justification | N/A | Not a design-risk UC |
| Business flow completeness | Pass | Full trace from pipeline.run() → fetch → traverse → build → upsert → status update |
| Layer-appropriate SoC | Pass | Non-UI: file/module boundary; pipeline and repo are distinct modules |
| Dependency flow | Pass | Pipeline depends on repo; no reverse dependency |
| Redundancy/duplication | Pass | No duplication with existing `finding_triggers_req` (different chain, different edge) |
| Simplification opportunity | Pass | Dedup-by-CVE pattern from BlastRadiusPipeline is correct and DRY |
| Cleanup completeness | Pass | New collection; nothing to decommission |
| No-legacy check | Pass | No legacy paths introduced |
| **Overall verdict** | **Pass** | |

**Findings:** None.

---

#### UC-CV-002: No-control CVE (empty result)

| Check | Result | Notes |
| --- | --- | --- |
| Architecture fit | Pass | |
| Layering fitness | Pass | |
| Boundary placement | Pass | |
| Future-state alignment | Pass | FILTER + early return handled in both repo and pipeline |
| Use-case coverage | Pass | Primary path (empty result case) covered |
| **Overall verdict** | **Pass** | |

**Findings:** None.

---

#### UC-CV-003: Pipeline status transition `mapped → violations_mapped`

| Check | Result | Notes |
| --- | --- | --- |
| Architecture fit | Pass | Status chain extension follows exact pattern |
| Layering fitness | Pass | `update_scan_run_status` in existing `ScanEnrichmentRepository` |
| Future-state alignment | Pass | Coordinator block shown, guard set `_VIOLATION_DONE` defined |
| Use-case coverage | Pass | Primary + exception→`pipeline_failed` paths covered |
| **Overall verdict** | **Pass** | |

**Finding — MINOR (non-blocking):** The call stack shows coordinator calling `update_scan_run_status` inside `ViolationMappingPipeline.run()`, but the status-transition flow in the coordinator shows `self._violation_mapping.run(...)` with exception path calling `self._mark_failed(...)`. This is consistent with all other stages. Confirmed non-blocking.

---

#### UC-CV-004: GET /v1/compliance/violations

| Check | Result | Notes |
| --- | --- | --- |
| Architecture fit | Pass | AQL-in-endpoint pattern follows supply_chain.py exactly |
| Layering fitness | Pass | No extra service layer needed |
| Boundary placement | Pass | |
| Anti-hack | Pass | |
| Terminology | Pass | |
| File/API naming | Pass | `/v1/compliance/violations` is clear |
| Future-state alignment | Pass | |
| Use-case coverage | Pass | Happy path + 404 covered |
| **Overall verdict** | **Pass** | |

**Finding — BLOCKING: `findings_with_violations` computation in COVERAGE query uses `violation_edges[*].finding_id` but the edge stores `_from` not `finding_id` as a field.** The coverage AQL in the design doc references `violation_edges[*].finding_id` but the edge schema only has `_from = scan_findings/<key>`. The field `finding_id` is NOT an explicit field on the edge — it must be extracted via `PARSE_IDENTIFIER(e._from).key`. This affects `findings_with_violations` computation. Required fix: update coverage AQL in proposed-design.md.

Actually — wait. Looking at the violations query, the `items` are built using:
```
RETURN {finding_id: PARSE_IDENTIFIER(e._from).key, ...}
```
And coverage query's `findings_with_violations` uses:
```
LET findings_with_violations = LENGTH(UNIQUE(violation_edges[*].finding_id))
```
But `violation_edges` = raw edges (not projected), so `violation_edges[*].finding_id` would be null/undefined. The correct expression is `UNIQUE(violation_edges[*] RETURN PARSE_IDENTIFIER(CURRENT._from).key)` or simply compute as part of a subquery.

**Classification: Design Impact** — AQL design detail in `proposed-design.md`.

---

#### UC-CV-005: GET /v1/compliance/coverage

Covered by the same finding above (F-001).

---

#### UC-CV-006: Zero findings

| Check | Result | Notes |
| --- | --- | --- |
| Future-state alignment | Pass | `if not cve_keys: return {}` early exit in repo; empty edges list early-exits upsert |
| Use-case coverage | Pass | |
| **Overall verdict** | **Pass** | |

---

#### UC-CV-007: Idempotency

| Check | Result | Notes |
| --- | --- | --- |
| Future-state alignment | Pass | `import_bulk(on_duplicate="update")` + deterministic `_key` correctly handles re-runs |
| Design-risk justification | Pass | Clear objective: prevent edge duplication; expected outcome: count unchanged on re-run |
| **Overall verdict** | **Pass** | |

---

#### UC-CV-008: Coordinator skip

| Check | Result | Notes |
| --- | --- | --- |
| Future-state alignment | Pass | `_VIOLATION_DONE = frozenset({"violations_mapped"})` guard shown; skip path traced correctly |
| Design-risk justification | Pass | Objective: coordinator must honor already-complete status; expected outcome: stage skipped |
| **Overall verdict** | **Pass** | |

**Additional check — `_LLM_DONE` guard set must also include `violations_mapped` and all later statuses.**

UC-CV-008 shows `_LLM_DONE = frozenset({"llm_enriched", "blast_radius_computed", "velocity_computed"})` — this does NOT include `violations_mapped`. This is actually correct behavior: when status is `violations_mapped`, `_LLM_DONE` does not contain it, so LLM stage runs. The coordinator design is: each guard set covers "statuses where THIS stage and ALL LATER stages are done". Since `violations_mapped` means "violation stage done but LLM not yet done", LLM should run. ✅

But: the existing guard sets in `_ENRICHMENT_DONE`, `_COMPACTION_DONE`, `_MAPPING_DONE` do NOT include `violations_mapped`. This means when re-running with `force=False` and status `violations_mapped`, stages 1-3 would be skipped (correct: `violations_mapped` is after `mapped` so it implies stages 1-3 are done). But `violations_mapped` is NOT in `_ENRICHMENT_DONE`, `_COMPACTION_DONE`, `_MAPPING_DONE` — so those stages would re-run unnecessarily.

**BLOCKING: `violations_mapped` must be added to `_ENRICHMENT_DONE`, `_COMPACTION_DONE`, `_MAPPING_DONE` in the coordinator**, so all prior stages are skipped correctly when status is already `violations_mapped`.

**Classification: Design Impact** — minor coordinator guard set update required in `proposed-design.md` and `future-state-runtime-call-stack.md` UC-CV-008.

---

### Missing Use Case Discovery Sweep

**Requirement coverage check:**
- REQ-CV-001: UC-CV-001, UC-CV-002, UC-CV-005 (idempotency), UC-CV-006 (zero findings) ✅
- REQ-CV-002: UC-CV-003, UC-CV-006, UC-CV-008 ✅
- REQ-CV-003: UC-CV-004 ✅
- REQ-CV-004: UC-CV-005 ✅

**Missing use cases found:**
- None missing at requirement level.

**Boundary crossing checks:**
- No new use case needed; the coordinator guard-set fix (F-002) is a design artifact update, not a new use case.

**Design-risk scenarios check:**
- Idempotency (UC-CV-007) ✅, coordinator skip (UC-CV-008) ✅

---

### Round 1 Summary

| Finding | Severity | Classification | Action Required |
| --- | --- | --- | --- |
| F-001: Coverage AQL uses `violation_edges[*].finding_id` but field doesn't exist on raw edges | Blocking | Design Impact | Update coverage AQL in `proposed-design.md` to use `PARSE_IDENTIFIER(e._from).key` |
| F-002: `violations_mapped` not in coordinator's `_ENRICHMENT_DONE`, `_COMPACTION_DONE`, `_MAPPING_DONE` guard sets | Blocking | Design Impact | Update `proposed-design.md` Section 2 coordinator design; update UC-CV-008 call stack |

**Round 1 verdict:** Fail (2 blocking findings)
**Clean-review streak after Round 1:** Reset (0)

---

## Applied Updates — Round 1 → Round 2

**Classification:** Design Impact
**Return path:** Stage 3 → Stage 4 → Stage 5

### Updates applied:

**`proposed-design.md` v1 → v2:**
- Section 5 (Coverage query AQL): Fixed `findings_with_violations` computation from `violation_edges[*].finding_id` to use inline COLLECT that counts unique `_from` values
- Section 2 (To-be pipeline chain description): Added `violations_mapped` to coordinator guard sets `_ENRICHMENT_DONE`, `_COMPACTION_DONE`, `_MAPPING_DONE`

**`future-state-runtime-call-stack.md` v1 → v2:**
- UC-CV-008: Updated `_ENRICHMENT_DONE`, `_COMPACTION_DONE`, `_MAPPING_DONE` to include `violations_mapped`

---

## Round 2 — Deep Review

**Date:** 2026-03-22
**Clean-review streak before this round:** 0 (reset after Round 1 findings)

### Changes verified

**F-001 fix:** Coverage AQL now uses:
```aql
LET findings_with_violations = LENGTH(
    FOR e IN finding_violates_control
        FILTER e.scan_run_id == @scan_run_id AND e.tenant_id == @tenant_id
        COLLECT finding = PARSE_IDENTIFIER(e._from).key
        RETURN finding
)
```
This correctly computes unique findings with at least one violation. ✅

**F-002 fix:** Coordinator guard sets updated:
```python
_ENRICHMENT_DONE = frozenset({
    "enriched", "compacted", "mapped", "violations_mapped",
    "llm_enriched", "blast_radius_computed", "velocity_computed"
})
_COMPACTION_DONE = frozenset({
    "compacted", "mapped", "violations_mapped",
    "llm_enriched", "blast_radius_computed", "velocity_computed"
})
_MAPPING_DONE = frozenset({
    "mapped", "violations_mapped",
    "llm_enriched", "blast_radius_computed", "velocity_computed"
})
```
UC-CV-008 call stack updated to show all three guard sets include `violations_mapped`. ✅

### Full re-review of all use cases (abbreviated — focus on previously clean items)

All UC-CV-001, UC-CV-002, UC-CV-003, UC-CV-006, UC-CV-007 re-verified — no new findings.

UC-CV-004 (violations endpoint): `_VIOLATIONS_QUERY` design intact. 404 logic via `run_exists` sentinel ✅.

UC-CV-005 (coverage endpoint): Fixed AQL verified. 404 logic via `run_exists` sentinel ✅.

UC-CV-008 (coordinator skip): Updated guard sets cover all statuses after `violations_mapped`. When status is `violations_mapped`, stages 1-3 skipped, stage 7 skipped, stage 4 (LLM) runs. Correct behavior. ✅

### Missing use case discovery sweep (Round 2)

- No new use cases discovered.
- All requirements covered by existing use cases.
- No new boundary crossings identified.

### Round 2 Summary

| Finding | Severity | Action |
| --- | --- | --- |
| None | — | — |

**Round 2 verdict:** Clean — no blockers, no required persisted artifact updates, no new use cases
**Clean-review streak after Round 2:** 1 (`Candidate Go`)

---

## Round 3 — Deep Review (Stability Confirmation)

**Date:** 2026-03-22
**Clean-review streak before this round:** 1 (`Candidate Go`)

### Final checks

All 8 use cases re-verified:
- Architecture fit, layering fitness, boundary placement: all Pass across all UCs ✅
- Anti-hack check: no workarounds ✅
- Terminology: `finding_violates_control`, `violations_mapped`, `ScanViolationRepository`, `ViolationMappingPipeline` all natural and precise ✅
- Requirement coverage closure: REQ-CV-001 through REQ-CV-004 all mapped ✅
- Decommission/cleanup: new collection only, nothing to remove ✅
- No-legacy check: no backward-compat wrappers ✅
- Idempotency design-risk UC fully traced ✅
- Coordinator skip design-risk UC fully traced with correct guard set behavior ✅

### Missing use case discovery sweep (Round 3)

No new use cases. Confirmation: all requirement boundaries, error paths, and design risks are covered.

### Round 3 Summary

**Round 3 verdict:** Clean — no blockers, no required persisted artifact updates, no new use cases
**Clean-review streak after Round 3:** 2 (`Go Confirmed`)

---

## Final Gate Status

**Stage 5 Gate: `Go Confirmed`**

Two consecutive clean rounds (Round 2 + Round 3). No blockers, no required persisted artifact updates, no newly discovered use cases in either clean round.

**Code Edit Permission:** Ready to unlock at Stage 6 entry.
