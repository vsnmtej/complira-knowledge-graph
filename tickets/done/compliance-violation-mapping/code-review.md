# Code Review — compliance-violation-mapping

**Stage:** 8
**Date:** 2026-03-22
**Design Basis:** `proposed-design.md` v2

---

## Files Reviewed

| File | Effective Lines | Delta Lines |
| --- | --- | --- |
| `src/complira_graph/db.py` | (existing, small addition) | ~7 |
| `src/complira_graph/ingestion/scan_violation_repository.py` | 92 | 92 (new) |
| `src/complira_graph/ingestion/violation_mapping_pipeline.py` | 126 | 126 (new) |
| `src/complira_graph/ingestion/pipeline_coordinator.py` | (existing, additions) | ~25 |
| `src/api/models/responses/compliance.py` | 35 | 35 (new) |
| `src/api/v1/endpoints/compliance.py` | 146 | 146 (new) |
| `src/api/v1/router.py` | (existing, additions) | ~4 |
| `tests/unit/ingestion/test_violation_mapping_pipeline.py` | 163 | 163 (new) |
| `tests/unit/api/test_compliance_api.py` | 176 | 176 (new) |

All files ≤ 500 effective lines. No delta gate triggered (all new files < 220 changed lines threshold in context).

---

## Checks

### Separation of Concerns and Responsibility Boundaries

- `ScanViolationRepository`: owns all AQL — control traversal + edge upsert. Zero logic. ✅
- `ViolationMappingPipeline`: owns orchestration — fetch→group→traverse→build→upsert→status. Zero AQL. ✅
- `compliance.py` endpoint: inline AQL for read-only queries; follows supply_chain.py pattern exactly. ✅
- `compliance.py` response models: pure Pydantic, no logic. ✅
- `router.py`: registration only. ✅

### Architecture/Layer Boundary Consistency with Design Basis

All layer boundaries match `proposed-design.md` v2:
- Repository → pipeline → coordinator → API is the correct dependency flow ✅
- No reverse dependencies introduced ✅
- `get_reference_db()` called directly in endpoint (not via Depends) — consistent with supply_chain pattern ✅

### Naming-to-Responsibility Alignment

- `ScanViolationRepository` ↔ "scan violation AQL" — aligned ✅
- `ViolationMappingPipeline` ↔ "maps findings to violations" — aligned ✅
- `finding_violates_control` edge collection — precise, direction-explicit ✅
- `violations_mapped` status — past-tense, consistent with `blast_radius_computed` ✅

### Duplication and Patch-on-Patch Smells

- CVE key normalization: implemented inline `_normalize_cve_key()` in pipeline module. Same logic exists in `enrichment_pipeline.py`. Minor DRY violation — acceptable given it's a trivial one-liner and `complira_graph.utils.keys` doesn't expose this specific function publicly. Not blocking.
- No patch-on-patch issues. ✅

### Test Quality and Maintainability

- `test_violation_mapping_pipeline.py`: uses `MagicMock(spec=...)` for type-safe mocking. All 10 tests cover distinct behavior. Fixture pattern clean. ✅
- `test_compliance_api.py`: uses `yield from _make_client(...)` pattern consistent with supply_chain tests. Context manager ensures patch teardown. ✅
- Tests cover: happy path, empty result, zero findings, dedup behavior, idempotency, 404 paths. Good coverage distribution. ✅

### Edge Cases

- `_build_edges()` deduplicates by `edge_key` (dict keyed by `_key`) — correct ✅
- `cve_id` reconstruction from `cve_key`: `cve_key.replace("_", "-", 2)` — this replaces only first 2 underscores. For `CVE_2024_1234` → `CVE-2024-1234` correct; but for `CVE_2024_12345` → `CVE-2024-12345` also correct (exactly 2 underscores in CVE format). ✅
- `upsert_finding_violates_control_edges` chunks at 500 — handles large batches correctly ✅
- Coverage AQL: `findings_with_violations` uses COLLECT on `PARSE_IDENTIFIER(e._from).key` — correctly counts unique findings ✅

### No-Legacy Check

No backward-compatibility wrappers, aliases, or legacy paths introduced. ✅

---

## Gate Decision

**PASS ✅**

All checks pass. No blocking findings. No source changes needed.
