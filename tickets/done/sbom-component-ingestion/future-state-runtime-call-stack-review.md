# Future-State Runtime Call Stack Review: SBOM Component Ingestion

**Ticket:** `sbom-component-ingestion`
**Date:** 2026-03-22

---

## Round 1 — Deep Review

### Architecture Fit

| UC | Check | Result | Notes |
| --- | --- | --- | --- |
| UC-SBOM-001 | Architecture fit | Pass | Extends existing upsert pattern; no new layers |
| UC-SBOM-002 | Architecture fit | Pass | New edge method follows `create_project_uses_component_edges()` pattern exactly |
| UC-SBOM-003 | Architecture fit | Pass | No change; existing wiring preserved |
| UC-SBOM-004/005 | Architecture fit | Pass | Reuses existing utilities; no duplication |
| UC-SBOM-006 | Architecture fit | Pass | Fallback purl already exists in current code |
| DR-SBOM-001 | Architecture fit | Pass | Dangling edge tolerance matches existing component_has_vuln design |

### Layering Fitness

| UC | Check | Result | Notes |
| --- | --- | --- | --- |
| All | Layering fitness | Pass | Endpoint extracts raw data; service orchestrates; edge_service writes edges; model owns schema |
| UC-SBOM-002 | Boundary placement | Pass | `dependencies_raw` passes through endpoint → service → edge_service cleanly; no layer bypass |

### Existing-Structure Bias Check

| UC | Check | Result | Notes |
| --- | --- | --- | --- |
| All | Existing-structure bias | Pass | Changes extend existing structures correctly; not forcing layout that harms design |

### Anti-Hack / Local-Fix Degradation Check

| UC | Check | Result | Notes |
| --- | --- | --- | --- |
| All | Anti-hack | Pass | No bypass of collection access; `import_bulk` used consistently |
| All | Local-fix degradation | Pass | Changes are clean extensions; no SoC degradation |

### Naming and Vocabulary

| UC | Check | Result | Notes |
| --- | --- | --- | --- |
| UC-SBOM-002 | Terminology | Pass | `create_depends_on_edges` — clear, matches collection name and existing method naming convention |
| UC-SBOM-002 | File/API naming | Pass | Method added to `EvidenceEdgeService` — correct owner |
| All | Name-to-responsibility alignment | Pass | No scope drift detected |

### Coverage Completeness

| UC | Primary | Fallback | Error | Source |
| --- | --- | --- | --- | --- |
| UC-SBOM-001 | Pass | Pass (fallback purl) | Pass (skip no-name/no-purl) | Requirement |
| UC-SBOM-002 | Pass | Pass (empty dependsOn) | Pass (missing ref → skip) | Requirement |
| UC-SBOM-003 | Pass | Pass (no project_id → skip) | N/A | Requirement |
| UC-SBOM-004/005 | Pass | N/A | N/A | Requirement |
| UC-SBOM-006 | Pass | N/A | N/A | Requirement |
| DR-SBOM-001 | Pass | N/A | N/A | Design-Risk |

### Requirement Coverage Closure

| Requirement | Covered by Use Case | Status |
| --- | --- | --- |
| REQ-SBOM-001 | UC-SBOM-001, UC-SBOM-004, UC-SBOM-006 | Pass |
| REQ-SBOM-002 | UC-SBOM-002, UC-SBOM-004 | Pass |
| REQ-SBOM-003 | UC-SBOM-003 | Pass |
| REQ-SBOM-004 | UC-SBOM-004 | Pass |
| REQ-SBOM-005 | UC-SBOM-005 | Pass |
| REQ-SBOM-006 | UC-SBOM-001, UC-SBOM-002 | Pass |

All requirements covered. ✓

### Missing Use Case Discovery Sweep

- Requirement coverage: all 6 REQs mapped. ✓
- Boundary crossings: endpoint → service → edge_service → DB — all covered. ✓
- Fallback/error branches: fallback purl (UC-006), skip no-name/no-purl (UC-001), skip missing ref (UC-002), empty dependsOn (UC-002), no project_id (UC-003). ✓
- Design-risk scenarios: dangling edge tolerance (DR-SBOM-001). ✓
- **Newly discovered use cases:** None.

### Redundancy / Duplication / Simplification

| Check | Result | Notes |
| --- | --- | --- |
| Redundancy | Pass | No code duplicated; normalize_purl and generate_edge_key reused |
| Simplification | Pass | Cannot simplify further without losing coverage |

### Decommission / Legacy Check

| Check | Result | Notes |
| --- | --- | --- |
| No-legacy check | Pass | No backward-compat shims; `license` (single) field preserved on V22Component as existing code uses it |
| Dead-path cleanup | Pass | No dead code introduced |

### Overall Verdicts

| UC | Verdict |
| --- | --- |
| UC-SBOM-001 | Pass |
| UC-SBOM-002 | Pass |
| UC-SBOM-003 | Pass |
| UC-SBOM-004/005 | Pass |
| UC-SBOM-006 | Pass |
| DR-SBOM-001 | Pass |

### Round 1 Outcome

- Blockers: **None**
- Required persisted artifact updates: **None**
- Newly discovered use cases: **None**
- Clean-review streak: **1 (Candidate Go)**

---

## Round 2 — Deep Review (Stability Confirmation)

### Re-check All Gate Criteria

**Architecture / Layering / Boundary / Naming:** All Pass — same as Round 1; no changes between rounds.

**Missing Use Case Discovery Sweep (Round 2):**
- Checked: does `dependencies_raw=[]` (absent `dependencies[]`) cause any issue?
  - In `ingest_sbom()`: `if dependencies_raw:` → no-op. ✓
  - In `create_depends_on_edges()`: called only when `dependencies_raw` truthy. ✓
- Checked: does passing `dependencies_raw` as default mutable `[]` in function signature cause issues?
  - Python mutable default argument antipattern: `def ingest_sbom(..., dependencies_raw: list[dict] = [])` is technically risky (shared default). Recommend using `None` default with `or []` guard inside.
  - **This is a design note but NOT a blocker** — both patterns produce correct results in practice for this flow (no mutation of the default). Document as implementation note.
- Checked: `scan_run_key` is available when `create_depends_on_edges()` is called in `ingest_sbom()`?
  - Yes — `scan_run_key` is set either from `create_run()` (lines 271–277) or passed in as parameter. Both paths ensure it's available before the edge call. ✓
- Checked: does `V22Component` `model_dump(by_alias=True, exclude_none=True)` correctly include new fields when set?
  - `exclude_none=True` means `supplier=None` is excluded from the dict (not written to ArangoDB). This is correct behavior — absent optional fields are not stored. ✓
- Checked: `licenses` list contains `None` values if a license entry lacks both `id` and `name`?
  - In solution sketch: `lic.get("license", {}).get("id") or lic.get("license", {}).get("name")` may produce `None` entries in the list. Recommend filtering with `if entry` to exclude None entries from the list.
  - **Implementation note, not a blocker.**

**Newly discovered use cases:** None.
**Required persisted artifact updates:** None (notes are implementation guidance, not architecture changes).

### Round 2 Outcome

- Blockers: **None**
- Required persisted artifact updates: **None**
- Newly discovered use cases: **None**
- Clean-review streak: **2 → Go Confirmed**

---

## Final Gate Decision

**Go Confirmed** ✓

All gate criteria satisfied across two consecutive clean deep-review rounds. Implementation can start.

### Implementation Notes (Non-Blocking, for Stage 6)

1. Use `dependencies_raw: Optional[list[dict]] = None` default in `ingest_sbom()` and guard with `dependencies_raw or []` inside to avoid mutable default antipattern.
2. Filter `None` values from `licenses` list in `_build_component_docs()`.
3. `scan_run_id` must be passed through to `create_depends_on_edges()` — available in all code paths.
