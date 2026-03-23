# Investigation Notes: Supply Chain Intelligence Layer

**Ticket:** `supply-chain-layer`
**Stage:** 1 — Investigation + Triage
**Date:** 2026-03-22
**Status:** Complete

---

## Sources Consulted

| File | Purpose |
| --- | --- |
| `src/api/v1/router.py` | Router registration pattern — how to add new routers |
| `src/api/v1/endpoints/reference.py` | AQL-in-endpoint pattern for read-only graph queries |
| `src/api/v1/endpoints/projects.py` | Auth + DB injection pattern (`get_current_customer`, `get_reference_db`) |
| `src/api/models/responses/__init__.py` | `APIResponse[T]` / `ResponseMetadata` wrapper pattern |
| `src/api/models/responses/projects.py` | Pydantic v2 response model style |
| `src/complira_graph/ingestion/scan_blast_radius_repository.py` | AQL patterns for `depends_on` traversal, `project_uses_component` counting |
| `src/complira_graph/ingestion/blast_radius_pipeline.py` | How INBOUND `depends_on` traversal works |
| `src/complira_graph/schema/complira_kg_schema_v2_2.py` | `component_has_vuln` edge schema — fields, required |
| `src/api/core/security.py` | `Customer`, `get_current_customer` — auth dependency |

---

## Key Findings

### FINDING-1: No Supply Chain Endpoint Exists — Fully New

No `supply_chain.py` router exists in `src/api/v1/endpoints/`. The router pattern from `router.py` shows the registration pattern:
```python
from api.v1.endpoints import supply_chain
api_router.include_router(supply_chain.router, prefix="/supply-chain", tags=["supply-chain"])
```

---

### FINDING-2: AQL-in-Endpoint Pattern Is Standard for Read Queries

`reference.py` shows the pattern for read-only graph queries: AQL runs directly inside the endpoint handler via `ref_db.aql.execute(...)`. No separate repository layer for read-only endpoints. `projects.py` does the same. This is the established pattern for this codebase — a new `SupplyChainRepository` would be an over-engineering smell for query-only endpoints.

---

### FINDING-3: Auth + DB Injection Pattern Is Consistent

All endpoints use:
```python
from api.core.database import get_reference_db
from api.core.security import Customer, get_current_customer
customer: Customer = Depends(get_current_customer)
ref_db = get_reference_db()
```
`customer.id` is the `tenant_id` for all queries.

---

### FINDING-4: `component_has_vuln` Edge Does NOT Require `tenant_id`

Schema shows `required: ["_from", "_to", "source"]`. The edge goes `components/{comp_key}` → `vulnerabilities/{cve_key}`. The `_to` key is the normalized CVE ID (e.g., `CVE_2021_44228`). `tenant_id` is set on the edge by `create_component_has_vuln_edges()` but is not schema-required.

**Implication for affected-projects query:** Tenant-scoping must happen via `project_uses_component` (which always has `tenant_id`), not via `component_has_vuln`.

---

### FINDING-5: AQL Shortest Path Pattern

ArangoDB AQL shortest path uses `K_SHORTEST_PATHS` or `SHORTEST_PATH`:
```aql
FOR path IN ANY SHORTEST_PATH "components/{from_key}" TO "components/{to_key}" depends_on
    RETURN path.vertices[*].purl
```
The `ScanBlastRadiusRepository` uses `FOR v, e, p IN 1..@depth_max INBOUND start depends_on` for traversal. For dependency path, `SHORTEST_PATH` is the correct primitive.

---

### FINDING-6: Components Are Global — Tenant Scoping via Edges

`components` has no `tenant_id`. Tenant scoping for component queries requires checking that at least one `project_uses_component` edge with the caller's `tenant_id` exists linking to that component. For the component detail endpoint, this is the 404 gate.

---

### FINDING-7: Vulnerabilities Collection Has CVE Key Format

`component_has_vuln._to = "vulnerabilities/{cve_key}"` where `cve_key = normalize_cve_id(cve_id)` = `CVE_2024_1234`. For the affected-projects query: given CVE ID string, normalize it to get the vulnerability `_key`, then find components via INBOUND `component_has_vuln` edges.

---

### FINDING-8: PURL in URL Path Needs URL Encoding Handling

FastAPI path parameters with `/`, `:`, `@` in a PURL like `pkg:npm/lodash@4.17.21` need special handling. The PURL should be a **query parameter** (not path parameter) to avoid routing conflicts. Change `GET /v1/supply-chain/component/{purl}` → `GET /v1/supply-chain/component?purl=...`. This is cleaner and avoids URL encoding headaches.

---

## Open Questions — Resolved

| OQ | Question | Resolution |
| --- | --- | --- |
| OQ-1 | Does a `supply_chain.py` router exist? | No — fully new |
| OQ-2 | How is the router registered? | `api_router.include_router(supply_chain.router, prefix="/supply-chain", ...)` in `router.py` |
| OQ-3 | AQL shortest path pattern? | ArangoDB `SHORTEST_PATH` or `K_SHORTEST_PATHS` AQL primitive |
| OQ-4 | Does `component_has_vuln` store severity on edge? | No — only `source`, `confidence`, `matched_cpe`. Severity is on the `vulnerabilities` document. For risk summary, query `vulnerabilities` documents joined via `component_has_vuln`. |

---

## Scope Triage

**Classification: Medium**

Signals:
- New public API surface (4 endpoints under `/v1/supply-chain/...`)
- 3 new/modified files + test file
- AQL graph traversal patterns (SHORTEST_PATH, multi-hop INBOUND/OUTBOUND)
- Cross-layer: response models + endpoint router + router registration

**Change inventory (preview):**

| File | Change Type | Summary |
| --- | --- | --- |
| `src/api/models/responses/supply_chain.py` | Add | Response models for all 4 endpoints |
| `src/api/v1/endpoints/supply_chain.py` | Add | 4 read-only endpoints with AQL |
| `src/api/v1/router.py` | Modify | Register new supply_chain router |
| `tests/unit/api/test_supply_chain_api.py` | Add | Unit tests for all ACs |

---

## Implications for Requirements / Design

1. `GET /v1/supply-chain/component/{purl}` should become `GET /v1/supply-chain/component?purl=...` (query param, not path param) to avoid URL-encoding issues with PURL special chars.
2. Affected-projects query: tenant scoping via `project_uses_component` edges, not via `component_has_vuln`.
3. Risk summary: severity counts require joining `vulnerabilities` documents through `component_has_vuln` edges.
4. No new collections, no service layer, no repository layer needed — AQL inline in endpoints follows established pattern.
