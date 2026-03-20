# Future-State Runtime Call Stack Review

## Ticket: evidence-pipeline-cleanup
## Date: 2026-03-19

---

## Round 1

### Review Criteria — UC-001 (empty licenses)

| Check | Result | Notes |
| --- | --- | --- |
| Architecture fit | Pass | One-line guard within existing method; no layer change |
| Layering fitness | Pass | Guard stays in service layer; no cross-layer impact |
| Boundary placement | Pass | License extraction is correctly in `_build_component_docs`; not pushed to model layer |
| Existing-structure bias | Pass | Fix uses existing truthiness check idiom (`and raw.get(...)`) |
| Anti-hack | Pass | Not patching over a deeper issue; root cause is the guard itself |
| Local-fix degradation | Pass | No architectural degradation; single line change |
| Terminology / vocabulary | Pass | `license`, `licenses`, `_build_component_docs` are all clear |
| File/API naming | Pass | No renaming involved |
| Name-to-responsibility alignment | Pass | No drift |
| Future-state alignment | Pass | Matches implementation-plan.md C-001 exactly |
| Use-case coverage completeness | Pass | UC-001 covers empty list; UC-002 covers None; UC-003 covers populated |
| Use-case source traceability | Pass | Requirement-derived from AC-001 |
| Requirement coverage closure | Pass | AC-001, AC-002, AC-003 all mapped |
| Design-risk justification | N/A | No design-risk use cases |
| Business flow completeness | Pass | All three license input shapes covered |
| Layer-appropriate SoC | Pass | Service-layer guard; no concern boundary crossed |
| Dependency flow smells | Pass | None |
| Redundancy/duplication | Pass | None |
| Simplification opportunity | Pass | Guard `and raw.get("licenses")` is the simplest correct form |
| Remove/decommission completeness | N/A | Not applicable for this UC |
| No-legacy/no-backward-compat | Pass | Guard is a correctness fix, not compatibility shim |
| **Overall verdict** | **Pass** | |

### Review Criteria — UC-004/005/006 (dead-code deletions)

| Check | Result | Notes |
| --- | --- | --- |
| Architecture fit | Pass | Deletions reduce surface area; no new layers introduced |
| Layering fitness | Pass | Removing dead layers improves clarity |
| Boundary placement | Pass | Active enrichment path (`enrichment_service.py`) is correctly retained |
| Existing-structure bias | Pass | Not keeping dead code for compatibility |
| Anti-hack | Pass | Pure deletion — no workaround |
| Local-fix degradation | Pass | No functional code affected |
| Terminology / vocabulary | Pass | Deletion inventory is unambiguous |
| File/API naming | Pass | No renaming; deleted files are removed entirely |
| Name-to-responsibility alignment | Pass | Active `enrichment_service.py` name is clear and retained |
| Future-state alignment | Pass | Matches C-003a–C-003f in implementation-plan.md |
| Use-case coverage completeness | Pass | UC-004, UC-005, UC-006 cover all three deletion groups |
| Use-case source traceability | Pass | Requirement-derived from T-DEL-002/003 |
| Requirement coverage closure | Pass | AC-004–AC-009 all mapped |
| Business flow completeness | Pass | Import graph traced fully; no active flow interrupted |
| Layer-appropriate SoC | Pass | Dead code removed from all layers cleanly |
| Dependency flow smells | Pass | No cycles introduced; deletes simplify graph |
| Redundancy/duplication | Pass | Eliminates duplication between `enrichment.py` and `enrichment_service.py` |
| Simplification opportunity | Pass | No further simplification needed |
| Remove/decommission completeness | Pass | All 5 dead files + 2 dead factory functions in scope |
| No-legacy/no-backward-compat | Pass | No compatibility shims kept |
| **Overall verdict** | **Pass** | |

### Missing Use-Case Discovery Sweep

- All 3 license input shapes covered (empty list, None, valid list).
- Import graph traces confirmed by grep — no additional dead importers found.
- `enrichment_service.py` (active) confirmed distinct from `enrichment.py` (dead) — no risk of double-deletion.
- No newly discovered use cases.

### Round 1 Verdict: Candidate Go

Clean-review streak: 1

---

## Round 2

### Deep Review — Challenge Assumptions

**UC-001 challenge**: Could the `else None` branch ever mask a real non-list value (e.g., `licenses="MIT"` as a string)?
- `isinstance(str, list)` = False → else None; license field absent.
- Is that correct? Raw CycloneDX/SPDX format always uses list for `licenses` when present. String format would be caught by `raw.get("license")` (singular) first in the outer `or` chain. ✓

**UC-004 challenge**: Is `api/services/enrichment.py` definitively not needed for any future path (e.g., background worker, scheduled task)?
- Grep across entire `src/` for `from api.services.enrichment import` → 0 matches.
- Grep for `enrichment.EnrichmentService` → 0 matches outside `enrichment.py` itself.
- The factory `get_enrichment_service()` in `dependencies.py` is the only wiring point; it is never referenced by any endpoint or router. ✓

**UC-005 challenge**: Could `api/repositories/scan.py` be used transitively via `__init__.py` star import?
- `api/repositories/__init__.py` is empty (no imports, no re-exports). ✓

**UC-006 challenge**: Same star-import concern for `component.py` — confirmed same empty `__init__.py`. ✓

**Missing-use-case sweep Round 2**:
- No error path for malformed licenses entries (e.g., `[{"wrong_key": ...}]`) — current behavior: `[0].get("license", {}).get("id")` returns None (safe fallback). No new UC needed.
- No boundary concern for `control_mapping.py` deletion — it uses `ScanFindingRepository` only via conditional import inside a method body; deletion of all three (compaction, enrichment, control_mapping) is atomic and safe.
- No newly discovered use cases.

### Round 2 Verdict: Go Confirmed

Clean-review streak: 2 (consecutive clean rounds, no blockers, no new use cases, no required artifact updates)

---

## Gate Decision: Go Confirmed

All checks Pass. Implementation may begin.
