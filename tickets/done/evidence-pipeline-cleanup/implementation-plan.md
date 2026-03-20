# Implementation Plan

## Ticket: evidence-pipeline-cleanup
## Scope: Small
## Status: Draft (design basis for runtime call stacks)

---

## Solution Sketch

### Architecture Direction

No new layers, modules, or design changes. Pure deletion + one-line guard fix.

Target changes:
1. **C-001**: Fix `service.py:349` — add truthiness guard for empty `licenses` list.
2. **C-002**: Add 3 unit tests to `test_service.py` covering `licenses=[]`, `licenses=None`, `licenses=[{...}]`.
3. **C-003**: Delete 5 dead-code files; remove 2 dead factory functions from `dependencies.py`.
4. **C-004**: Run full test suite to confirm 0 failures.

### Change Inventory

| Change ID | File | Change Type | Description |
| --- | --- | --- | --- |
| C-001 | `src/complira_graph/ingestion/service.py` | Modify | Add `and raw.get("licenses")` guard at line 349 |
| C-002 | `tests/unit/ingestion/test_service.py` | Modify | Add 3 test methods to `TestBuildComponentDocs` |
| C-003a | `src/api/services/enrichment.py` | Remove | Delete dead service file |
| C-003b | `src/api/services/compaction.py` | Remove | Delete dead service file |
| C-003c | `src/api/services/control_mapping.py` | Remove | Delete dead service file |
| C-003d | `src/api/repositories/scan.py` | Remove | Delete dead repository file |
| C-003e | `src/api/repositories/component.py` | Remove | Delete dead repository file |
| C-003f | `src/api/core/dependencies.py` | Modify | Remove `get_enrichment_service()` and `get_compaction_service()` functions |

### Execution Order

1. Delete dead service files (C-003a, C-003b, C-003c)
2. Delete dead repository files (C-003d, C-003e)
3. Remove dead factory functions from `dependencies.py` (C-003f)
4. Apply F-001 fix (C-001)
5. Add unit tests (C-002)
6. Run test suite

### F-001 Fix Detail

**Before** (line 348-351):
```python
license=raw.get("license") or (
    raw.get("licenses", [{}])[0].get("license", {}).get("id")
    if isinstance(raw.get("licenses"), list) else None
),
```

**After**:
```python
license=raw.get("license") or (
    raw.get("licenses")[0].get("license", {}).get("id")
    if isinstance(raw.get("licenses"), list) and raw.get("licenses") else None
),
```

### Requirement Traceability

| Requirement | Design Section | Use Cases | Tasks |
| --- | --- | --- | --- |
| F-001 fix | C-001, C-002 | UC-001, UC-002, UC-003 | Modify service.py, add tests |
| T-DEL-002 | C-003a, C-003b, C-003c, C-003d, C-003f | UC-004, UC-005 | Delete files, remove functions |
| T-DEL-003 | C-003e | UC-006 | Delete component.py |
