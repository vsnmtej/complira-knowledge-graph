# Future-State Runtime Call Stack Review

## Round 1 — Deep Review

**Date:** 2026-03-22
**Basis:** `future-state-runtime-call-stack.md` v1, `implementation-plan.md` solution sketch

### UC-1: Create detected_control_maps_to edges

| Check | Result | Notes |
| --- | --- | --- |
| Architecture fit | Pass | Single edge-service method; correct layer placement |
| Layering fitness | Pass | Edge creation belongs in EvidenceEdgeService; no layer boundary violations |
| Boundary placement | Pass | CHECKOV_NIST_MAP in separate data module; logic in service |
| Existing-structure bias | Pass | Follows exact pattern of `create_component_has_vuln_edges` |
| Anti-hack | Pass | No patch-on-patch; clean replacement of stub |
| Local-fix degradation | Pass | Clean architectural fit |
| Terminology | Pass | `detected_control_maps_to`, `maps_to_edges` — natural names |
| File/API naming | Pass | `checkov_control_map.py` clear; `_normalize_oscal_key` clear |
| Name-to-responsibility | Pass | No drift |
| Future-state alignment | Pass | Matches implementation plan exactly |
| Use-case coverage completeness | Pass | Primary + empty-list fallback covered |
| Use-case source traceability | Pass | Requirement source (AC-001, AC-002) |
| Requirement coverage closure | Pass | AC-001, AC-002 fully covered |
| Design-risk justification | N/A | N/A for UC-1 |
| Business flow completeness | Pass | Full write path included |
| Layer-appropriate SoC | Pass | Data module separate from logic |
| Dependency flow smells | Pass | None |
| Redundancy/duplication | Pass | None |
| Simplification opportunity | Pass | Accumulator + single import_bulk is minimal |
| Decommission/cleanup | Pass | Old stub tests will be replaced |
| No-legacy/no-backward-compat | Pass | Full stub replacement |
| Overall verdict | **Pass** | |

### UC-2: Skip unknown check_id

| Check | Result | Notes |
| --- | --- | --- |
| Architecture fit | Pass | |
| Use-case coverage completeness | Pass | Empty list + unknown check_id both covered |
| Overall verdict | **Pass** | |

### UC-3: control_in_component edge

| Check | Result | Notes |
| --- | --- | --- |
| Architecture fit | Pass | |
| Boundary placement | Pass | file_path from doc → correct field (schema allows it) |
| Use-case coverage completeness | Pass | purl present + absent both covered |
| Overall verdict | **Pass** | |

### UC-DR1: Batch efficiency

| Check | Result | Notes |
| --- | --- | --- |
| Architecture fit | Pass | Accumulator pattern proven in other edge methods |
| Simplification opportunity | Pass | Minimal — can't batch further |
| Overall verdict | **Pass** | |

### UC-DR2: Schema compliance

| Check | Result | Notes |
| --- | --- | --- |
| Architecture fit | Pass | Static construction prevents extra fields |
| Anti-hack | Pass | No workaround needed |
| Overall verdict | **Pass** | |

### Missing Use-Case Discovery Sweep

- Requirement coverage: all 8 ACs mapped to at least one UC ✓
- Boundary crossings: `self._db.collection(...).import_bulk` is the only DB call — no missing boundary handling
- Fallback/error branches: both edge methods have non-empty guard before import_bulk — correct
- Design-risk scenarios: UC-DR1 (batching) and UC-DR2 (schema) both covered
- **No new use cases discovered**

### Round 1 Summary

- Blockers: **None**
- Required artifact updates: **None**
- New use cases discovered: **None**
- Clean-review streak: **1 (Candidate Go)**

---

## Round 2 — Deep Review (Stability Confirmation)

**Date:** 2026-03-22
**Basis:** Same artifacts — no updates from Round 1 (no blockers)

### Full re-check sweep

All 5 use cases re-reviewed:

**UC-1:** Re-checked edge doc fields against schema. `_normalize_oscal_key` is a free function importable from checkov_control_map or defined inline in edge_service — placement decision: define as module-level private function in `edge_service.py` (single use site, no need to export from data module). This does NOT change the call stack. ✓

**UC-2:** Re-checked early return on empty list. `if not detected_controls: return` is the first check — consistent with other methods. ✓

**UC-3:** Re-checked `file_path` handling. Schema allows `file_path: ["string", "null"]`. `doc.get("file_path") or None` handles both missing key and empty string correctly → produces `None` (schema allows null). ✓

**UC-DR1:** Re-checked that accumulator pattern is consistent with `create_component_has_vuln_edges` (lines 114-141 in edge_service.py). Exact same structure. ✓

**UC-DR2:** Re-confirmed field sets. No extra fields sneak in via `**doc` spread or similar. ✓

### Missing Use-Case Discovery Sweep

- Requirement coverage: verified all 8 ACs still mapped ✓
- No new edge cases found for purl normalization (already uses `normalize_purl` which handles None input)
- No new use cases discovered

### Round 2 Summary

- Blockers: **None**
- Required artifact updates: **None**
- New use cases discovered: **None**
- Clean-review streak: **2 (Go Confirmed)**

---

## Gate Decision: Go Confirmed ✅

Both consecutive deep-review rounds clean. Implementation may proceed.

**Applied Updates:** None (no blocking rounds)
