# Investigation Notes

## Ticket: evidence-pipeline-cleanup
## Date: 2026-03-19
## Scope: Small

---

## Sources Consulted

- `src/complira_graph/ingestion/service.py` (read, lines 340-354)
- `src/api/services/enrichment.py` (read, confirmed dead code)
- `src/api/services/compaction.py` (read, confirmed dead code)
- `src/api/services/control_mapping.py` (grep, confirmed dead code)
- `src/api/repositories/scan.py` (read, confirmed orphaned by dead services)
- `src/api/repositories/component.py` (read, zero importers)
- `src/api/core/dependencies.py` (read, lines 165-204)
- `src/api/repositories/__init__.py` (empty — no re-exports)
- `tests/unit/ingestion/test_service.py` (read, lines 87-130)
- `tests/integration/test_scan_ingestion_api.py` (read, line 302)
- Grep: `ComponentRepository`, `ScanFindingRepository`, `get_enrichment_service`, `get_compaction_service` across `src/` and `tests/`

---

## Key Findings

### F-001: Empty licenses IndexError

- **Location**: `service.py:349`
- **Code**: `raw.get("licenses", [{}])[0].get("license", {}).get("id") if isinstance(raw.get("licenses"), list) else None`
- **Bug**: When `licenses = []`, `isinstance` check passes (True), but `[][0]` raises `IndexError`. The `[{}]` default is only used when `raw.get("licenses")` returns `None`.
- **Fix**: Add `and raw.get("licenses")` truthiness guard before indexing.
- **Test gap**: `TestBuildComponentDocs` has no `licenses` test cases. Three new tests needed: empty list, None, populated list.
- **Skipped integration test**: `test_end_to_end_fda_sbom_upload` is skipped due to live ArangoDB requirement, not F-001. AC-011 (unskip) is out of scope — that test remains infrastructure-dependent.

### T-DEL-002: api/repositories/scan.py

- Importers confirmed: `api/services/enrichment.py:15`, `api/services/compaction.py:15`, `api/services/control_mapping.py:91`
- All three importers are dead code (no v1 endpoint reaches them)
- `get_enrichment_service()` in `dependencies.py:173` and `get_compaction_service()` in `dependencies.py:189` are never called by any endpoint
- Tests: no test file imports `ScanFindingRepository`, `ScanSessionRepository`, or `ScanEdgeRepository` from `api.repositories.scan`
- Tests DO import `api.services.enrichment_service.EnrichmentService` (the active service, different file) — must not be deleted

### T-DEL-003: api/repositories/component.py

- Zero importers — `ComponentRepository` grep returns only its own definition line
- Not re-exported from `api/repositories/__init__.py` (empty file)
- No test imports it

### Dead-code files to delete

| File | Reason |
| --- | --- |
| `src/api/services/enrichment.py` | Dead — no endpoint calls `get_enrichment_service()`; active enrichment is `enrichment_service.py` |
| `src/api/services/compaction.py` | Dead — no endpoint calls `get_compaction_service()` |
| `src/api/services/control_mapping.py` | Dead — `ControlMappingService` only called by `compaction.py` (also dead) |
| `src/api/repositories/scan.py` | Dead — only imported by above dead services |
| `src/api/repositories/component.py` | Dead — zero importers |

### Dependencies.py functions to remove

- `get_enrichment_service()` (lines 173-186): imports from dead `api.services.enrichment`
- `get_compaction_service()` (lines 189-202): imports from dead `api.services.compaction`

---

## Open Questions Resolved

- The FDA SBOM e2e test skip is infrastructure-dependent, not F-001. Leave it skipped (out of scope).
- No test file imports the dead repositories/services. Deletions are safe.

---

## Implications for Design

- Scope confirmed `Small`: 1-line guard fix + 3 new unit tests + 5 file deletions + 2 function removals in `dependencies.py`.
- No new modules, no interface changes, no design risk.
- Execution order: delete dead services first → delete dead repositories → fix F-001 → add unit tests.
