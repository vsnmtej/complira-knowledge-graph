# Code Review

## Scope

- `src/complira_graph/ingestion/checkov_control_map.py` (new, ~120 effective lines)
- `src/complira_graph/ingestion/edge_service.py` (modified, +55 lines net)
- `tests/unit/ingestion/test_edge_service.py` (modified, replaced ~20 stub lines with ~100 test lines)

## File Size Assessment

| File | Effective non-empty lines | Delta | Assessment |
| --- | --- | --- | --- |
| `checkov_control_map.py` | ~120 | +120 (new) | Under 500 — normal review ✅ |
| `edge_service.py` | ~400 (est) | +55 | Under 500 — normal review ✅ |
| `test_edge_service.py` | ~420 (est) | +80 net | Under 500 — normal review ✅ |

Delta gate: no single file exceeds 220 changed lines. ✅

## Review Checks

### checkov_control_map.py

| Check | Result | Notes |
| --- | --- | --- |
| SoC | Pass | Pure data module — no DB/logic; `_normalize_oscal_key` helper co-located with data it serves |
| Architecture fit | Pass | Data separate from logic; imported by edge_service only |
| Naming | Pass | `CHECKOV_NIST_MAP`, `_normalize_oscal_key` — clear and unsurprising |
| Anti-hack | Pass | No clever tricks; straightforward dict + normalization |
| No-legacy | Pass | New file only |
| Duplication | Pass | `_normalize_oscal_key` follows same pattern as `regulatory_mapper.py` line 383 — not duplicated in edge_service |
| Test coverage | Pass | N/A for data module; normalization tested implicitly via edge key assertions |

### edge_service.py (modified method only)

| Check | Result | Notes |
| --- | --- | --- |
| SoC | Pass | Method only calls `CHECKOV_NIST_MAP.get()` + accumulates + single import_bulk per edge type |
| Architecture fit | Pass | Follows existing pattern of `create_component_has_vuln_edges` exactly |
| Layer boundary | Pass | No AQL added — static map lookup + collection.import_bulk is correct at this layer |
| Naming | Pass | `maps_to_edges`, `in_comp_edges` — clear local names |
| Anti-hack | Pass | No workarounds; clean stub replacement |
| Local-fix degradation | Pass | Improves existing stub; no SoC degradation |
| Docstring | Pass | Documents edge field constraints and purl-absent behavior |
| Schema compliance | Pass | Edge doc field sets verified against schema in tests |
| Idempotency | Pass | `import_bulk(on_duplicate="update")` consistent with all other edge methods |
| Error handling | Pass | Exceptions from import_bulk propagate to caller — consistent with other edge methods (no try/except needed) |

### test_edge_service.py

| Check | Result | Notes |
| --- | --- | --- |
| Coverage | Pass | All 8 ACs covered; negative cases (unknown check_id, no purl) covered |
| Test quality | Pass | Each test has a single assertion focus; docstrings reference AC |
| Maintainability | Pass | No complex setup; `_make_svc()` helper reused from existing pattern |
| Schema compliance tests | Pass | Separate tests for maps_to and control_in_component field sets |

## Gate Decision: Pass ✅

No blocking findings. No re-entry required.
