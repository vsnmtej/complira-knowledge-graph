# Code Review: SBOM Component Ingestion

**Ticket:** `sbom-component-ingestion`
**Stage:** 8
**Date:** 2026-03-22

---

## Files Reviewed

| File | Effective Lines | Delta (this ticket) | Threshold |
| --- | --- | --- | --- |
| `src/complira_graph/ingestion/edge_service.py` | 492 | +42 (new method) | ≤500: normal |
| `src/complira_graph/ingestion/service.py` | 384 | +53 | ≤500: normal |
| `src/complira_graph/models/evidence.py` | 220 | +3 | ≤500: normal |
| `src/api/v1/endpoints/scan.py` | 474 | +2 (sbom-specific) | ≤500: normal |
| `tests/unit/ingestion/test_sbom_ingestion.py` | new | +~280 | new file |

Note: `scan.py` git diff shows 155 lines vs HEAD — this includes Phase 6 changes already reviewed. SBOM-specific delta is 2 lines only.

---

## Review Checks

### Separation of Concerns / Responsibility Boundaries

| Check | File | Result | Notes |
| --- | --- | --- | --- |
| SoC | `edge_service.py` | Pass | `create_depends_on_edges()` correctly placed in EvidenceEdgeService — matches all other edge methods |
| SoC | `service.py` | Pass | Service orchestrates; edge method handles write logic; no leakage |
| SoC | `evidence.py` | Pass | Model owns schema only; no business logic |
| SoC | `scan.py` | Pass | Endpoint extracts raw data only; delegates to service |

### Architecture / Layer Boundary Consistency

| Check | Result | Notes |
| --- | --- | --- |
| Endpoint → Service → EdgeService → DB | Pass | Clean boundary chain; no layer bypass |
| `dependencies_raw` param flow | Pass | Extracted at endpoint (data boundary), passed through service, processed in edge service |
| No direct DB access from endpoint | Pass | `ingest_sbom()` call is the only cross-boundary call |

### Naming-to-Responsibility Alignment

| Check | Result | Notes |
| --- | --- | --- |
| `create_depends_on_edges` | Pass | Clear, matches collection name, consistent with `create_project_uses_component_edges`, `create_component_has_vuln_edges` |
| `dependencies_raw` param | Pass | Consistent naming with `components_raw` pattern in the same service |
| `supplier`, `licenses`, `hashes` field names | Pass | Match CycloneDX field names exactly |

### Security

| Check | Result | Notes |
| --- | --- | --- |
| No user input interpolated into AQL | Pass | `import_bulk()` used; no f-string AQL construction |
| Multi-tenancy on edges | Pass | `tenant_id` passed to all edge writes |
| Global component model (no tenant_id on doc) | Pass | Matches architecture contract; tenant isolated via edge |

### Duplication / Patch-on-Patch

| Check | Result | Notes |
| --- | --- | --- |
| `create_depends_on_edges` pattern | Pass | Clean new method; no duplication; follows existing pattern precisely |
| `_build_component_docs` extension | Pass | New fields extracted cleanly; no code smell |
| No backwards-compat shims | Pass | `legacy_license` field preserved (single license) but this is an existing field, not a compat shim |

### Test Quality

| Check | Result | Notes |
| --- | --- | --- |
| AC coverage | Pass | All 14 ACs have explicit test scenarios |
| Branch coverage | Pass | Empty lists, missing fields, skip conditions all tested |
| Isolation | Pass | DB mocked; no env dependencies |
| Assertions specificity | Pass | Tests verify field values, collection names, call count, on_duplicate flag |

### Delta Gate

| File | Delta | Gate | Result |
| --- | --- | --- | --- |
| `edge_service.py` | +42 | <220 | Pass |
| `service.py` | +53 | <220 | Pass |
| `evidence.py` | +3 | <220 | Pass |
| `scan.py` (sbom delta) | +2 | <220 | Pass |
| `test_sbom_ingestion.py` | new | test file | Pass |

---

## Gate Decision: **PASS**

No source changes required. All checks Pass.
