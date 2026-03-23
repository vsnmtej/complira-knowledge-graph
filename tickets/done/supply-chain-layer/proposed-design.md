# Proposed Design: Supply Chain Intelligence Layer

**Version:** v1
**Status:** Draft
**Ticket:** `supply-chain-layer`
**Date:** 2026-03-22

---

## Current State (As-Is)

SBOM ingestion populates three graph collections:
- `components` — global component documents keyed by normalized PURL; no `tenant_id`
- `depends_on` — directed edges `components/A → components/B` (A depends on B); has `tenant_id`
- `project_uses_component` — edges `projects/P → components/C`; has `tenant_id`
- `component_has_vuln` — edges `components/C → vulnerabilities/V`; has `source`, optional `tenant_id`

No query API exists for these collections. There is no `supply_chain.py` endpoint file. No response models for supply chain data.

---

## Target State (To-Be)

Four read-only endpoints under `/v1/supply-chain/` backed by AQL graph queries against existing collections. Each endpoint is tenant-scoped via `project_uses_component` edges.

---

## Architecture Direction

**Decision: AQL-inline endpoint pattern — no separate repository layer.**

Rationale: All existing read-only graph query endpoints (`reference.py`, `projects.py`) run AQL inline in the endpoint handler via `db.aql.execute()`. A new `SupplyChainRepository` class would be over-engineering — it would own no state, provide no reuse, and add an abstraction layer with zero benefit for query-only operations. The pattern is established and consistent.

**Layering:**
```
HTTP Request
  → FastAPI router (supply_chain.router)
    → endpoint handler (async def)
      → auth injection (Depends(get_current_customer))
      → db injection (get_reference_db())
      → AQL query execution (db.aql.execute())
      → Pydantic response model construction
  → HTTP Response (APIResponse[T])
```

No service layer. No repository layer. Direct AQL in handler per established pattern.

---

## Change Inventory

| File | Change Type | Summary |
| --- | --- | --- |
| `src/api/models/responses/supply_chain.py` | Add | Response models for all 4 endpoints |
| `src/api/v1/endpoints/supply_chain.py` | Add | 4 read-only endpoints with inline AQL |
| `src/api/v1/router.py` | Modify | Register `supply_chain.router` under `/supply-chain` |
| `tests/unit/api/test_supply_chain_api.py` | Add | Unit tests for all 13 ACs |

---

## File/Module Descriptions

### `src/api/models/responses/supply_chain.py` (Add)

**Layer:** API response models
**Responsibility:** Pydantic v2 response models for supply chain endpoints; data shape contracts only
**Key types:**

```
ComponentDetailResponse
  purl: str
  name: str
  version: Optional[str]
  type: Optional[str]
  projects: List[str]          # project_id values
  dependencies: List[str]      # PURL values (OUTBOUND 1-hop)
  dependents: List[str]        # PURL values (INBOUND 1-hop)
  vulnerabilities: List[str]   # CVE ID strings

AffectedProjectItem
  project_id: str
  component_purl: str
  cve_id: str

AffectedProjectsResponse
  items: List[AffectedProjectItem]
  total: int

DependencyPathResponse
  found: bool
  path: List[str]              # PURL values
  path_length: int

TopComponent
  purl: str
  dependent_count: int

RiskSummaryResponse
  project_id: str
  total_components: int
  vulnerable_components: int
  critical_count: int
  high_count: int
  top_depended_on: List[TopComponent]   # up to 5
```

**Dependencies:** `pydantic`, `typing`

---

### `src/api/v1/endpoints/supply_chain.py` (Add)

**Layer:** API endpoint handlers
**Responsibility:** FastAPI router with 4 read-only endpoints; AQL inline per established pattern
**Key APIs:**

```
GET /component?purl=...           → APIResponse[ComponentDetailResponse]
GET /affected-projects?cve_id=... → APIResponse[AffectedProjectsResponse]
GET /dependency-path?from_purl=...&to_purl=... → APIResponse[DependencyPathResponse]
GET /risk-summary?project_id=...  → APIResponse[RiskSummaryResponse]
```

**AQL patterns per endpoint:**

**component detail:**
- `DOCUMENT("components", normalize_purl(purl))` for component doc
- check tenant access via `project_uses_component` edge filter on `tenant_id`
- OUTBOUND 1-hop `depends_on` for `dependencies`
- INBOUND 1-hop `depends_on` for `dependents`
- OUTBOUND `component_has_vuln` for `vulnerabilities`
- project IDs via `project_uses_component` INBOUND on component

**affected-projects:**
- normalize CVE ID to key
- `DOCUMENT("vulnerabilities", cve_key)` → validate exists
- INBOUND `component_has_vuln` traversal to find affected components
- For each component: filter `project_uses_component` by `tenant_id` to find projects

**dependency-path:**
- normalize `from_purl`, `to_purl` to keys
- validate both accessible to tenant
- AQL `SHORTEST_PATH` on `depends_on`
- if no path returned, `found=false`, empty path

**risk-summary:**
- verify project belongs to tenant
- `project_uses_component` edge count for `total_components`
- join with `component_has_vuln` + `vulnerabilities` for severity counts
- INBOUND `depends_on` edge count per component for `top_depended_on`

**Dependencies:**
- `api.core.database.get_reference_db`
- `api.core.security.Customer, get_current_customer`
- `api.models.responses.APIResponse, ResponseMetadata`
- `api.models.responses.supply_chain.*`
- `complira_graph.utils.keys.normalize_purl, normalize_cve_id`

---

### `src/api/v1/router.py` (Modify)

**Change:** Add import + `include_router` call for `supply_chain.router` under prefix `/supply-chain`.

```python
from api.v1.endpoints import supply_chain
api_router.include_router(supply_chain.router, prefix="/supply-chain", tags=["supply-chain"])
```

---

### `tests/unit/api/test_supply_chain_api.py` (Add)

**Layer:** Unit tests
**Responsibility:** TestClient-based unit tests for all 13 ACs; mock DB + auth dependencies
**Pattern:** Matches `test_scan_findings_api.py` style — `app.dependency_overrides`, `TestClient`

---

## Naming Decisions

| Name | Rationale |
| --- | --- |
| `supply_chain.py` | Matches kebab→snake convention of other endpoint files (`projects.py`, `reference.py`) |
| `ComponentDetailResponse` | Mirrors `ProjectResponse` / `ScanSessionResponse` naming: noun + `Response` suffix |
| `AffectedProjectsResponse` | Plural noun phrase matches query semantics |
| `DependencyPathResponse` | Direct mapping to use case description |
| `RiskSummaryResponse` | Direct mapping to use case description |
| `AffectedProjectItem` | `Item` suffix for list element models, matching `findings` patterns |
| `TopComponent` | Short embedded model; `Top` prefix signals the ranked subset semantics |
| `/supply-chain` prefix | Kebab URL convention matching all other prefixes |

---

## Naming Drift Check

No existing files being renamed. All new files follow established conventions. No drift identified.

---

## Dependency Flow

```
router.py  ←imports→  supply_chain.py  ←imports→  supply_chain (models)
                                         ←imports→  api.core.database
                                         ←imports→  api.core.security
                                         ←imports→  api.models.responses (APIResponse)
                                         ←imports→  complira_graph.utils.keys
```

No cycles. All dependencies are downward (endpoint → core infrastructure → graph utils).

---

## Use Case Coverage Matrix

| use_case_id | Source | Primary Path | Fallback/Error Path | Mapped Call Stack Section |
| --- | --- | --- | --- | --- |
| UC-SC-001 | Requirement | Yes | Yes (404 unknown PURL) | §UC-SC-001 |
| UC-SC-002 | Requirement | Yes | Yes (empty list, no CVE match) | §UC-SC-002 |
| UC-SC-003 | Requirement | Yes | Yes (found=false, no path) | §UC-SC-003 |
| UC-SC-004 | Requirement | Yes | Yes (404 unknown project_id) | §UC-SC-004 |

---

## Design-Risk Use Cases

None required — design is a straight AQL-in-endpoint pattern with no novel architectural choices.

---

## Decommission / Cleanup

No files removed. No legacy behavior replaced. No backward-compat shims.

---

## Version History

| Version | Changes |
| --- | --- |
| v1 | Initial design — 4 files, AQL-in-endpoint pattern, PURL as query param |
