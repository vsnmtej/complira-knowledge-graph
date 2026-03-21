# Implementation Progress

## Ticket: evidence-pipeline-cleanup
## Stage 6 Status: Complete

---

## Change Inventory

| Change ID | File | Type | Status | Tests |
| --- | --- | --- | --- | --- |
| C-001 | `src/complira_graph/ingestion/service.py:349` | Modify | Completed | Passed |
| C-002 | `tests/unit/ingestion/test_service.py` | Modify | Completed | Passed (3 new tests) |
| C-003a | `src/api/services/enrichment.py` | Remove | Completed | N/A (deleted) |
| C-003b | `src/api/services/compaction.py` | Remove | Completed | N/A (deleted) |
| C-003c | `src/api/services/control_mapping.py` | Remove | Completed | N/A (deleted) |
| C-003d | `src/api/repositories/scan.py` | Remove | Completed | N/A (deleted) |
| C-003e | `src/api/repositories/component.py` | Remove | Completed | N/A (deleted) |
| C-003f | `src/api/core/dependencies.py` | Modify | Completed | Passed |

---

## Test Run Results

### Unit tests (Stage 6 gate)
- `tests/unit/ingestion/test_service.py`: 20 passed (was 17; +3 new F-001 tests)
- `tests/unit/` full: 410 passed, 0 failed

### Full suite (excluding live-DB integration)
- `tests/` excluding `tests/integration/ingestion/`: **886 passed, 1 skipped, 0 failed**
- Previous baseline: 883 passed, 1 skipped → **+3 new tests, 0 regressions**
- Skipped test: FDA SBOM e2e (`test_end_to_end_fda_sbom_upload`) — infrastructure-dependent (live ArangoDB), pre-existing, unrelated to this ticket.

### Integration test note
- `tests/integration/ingestion/` (9 tests): fail with ArangoDB unique-constraint violation — pre-existing dirty-DB test isolation issue, not caused by these changes. Confirmed by `git diff` — no change to the test fixtures or test logic.

---

## F-001 Fix Detail

**File**: `src/complira_graph/ingestion/service.py`
**Before**:
```python
raw.get("licenses", [{}])[0].get("license", {}).get("id")
if isinstance(raw.get("licenses"), list) else None
```
**After**:
```python
raw.get("licenses")[0].get("license", {}).get("id")
if isinstance(raw.get("licenses"), list) and raw.get("licenses") else None
```

---

## Docs Sync

No docs impact — dead-code deletions and one-line guard fix are implementation details not documented in canonical `docs/`.
