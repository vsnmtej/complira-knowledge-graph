# Implementation Plan: Supply Chain Intelligence Layer

**Status:** Final
**Ticket:** `supply-chain-layer`
**Design Basis:** `proposed-design.md` v1
**Date:** 2026-03-22

---

## Implementation Order

Bottom-up: response models → endpoint file → router registration → tests.

| Step | File | Change Type | Depends On |
| --- | --- | --- | --- |
| 1 | `src/api/models/responses/supply_chain.py` | Add | nothing |
| 2 | `src/api/v1/endpoints/supply_chain.py` | Add | Step 1 |
| 3 | `src/api/v1/router.py` | Modify | Step 2 |
| 4 | `tests/unit/api/test_supply_chain_api.py` | Add | Steps 1–3 |

---

## Step 1 — Response Models

File: `src/api/models/responses/supply_chain.py`

Models:
- `ComponentDetailResponse`: `purl`, `name`, `version: Optional[str]`, `type: Optional[str]`, `projects: List[str]`, `dependencies: List[str]`, `dependents: List[str]`, `vulnerabilities: List[str]`
- `AffectedProjectItem`: `project_id`, `component_purl`, `cve_id`
- `AffectedProjectsResponse`: `items: List[AffectedProjectItem]`, `total: int`
- `DependencyPathResponse`: `found: bool`, `path: List[str]`, `path_length: int`
- `TopComponent`: `purl: str`, `dependent_count: int`
- `RiskSummaryResponse`: `project_id`, `total_components`, `vulnerable_components`, `critical_count`, `high_count`, `top_depended_on: List[TopComponent]`

---

## Step 2 — Endpoint File

File: `src/api/v1/endpoints/supply_chain.py`

4 endpoints:
- `GET /component?purl=...` → `get_component_detail()`
- `GET /affected-projects?cve_id=...` → `get_affected_projects()`
- `GET /dependency-path?from_purl=...&to_purl=...` → `get_dependency_path()`
- `GET /risk-summary?project_id=...` → `get_risk_summary()`

AQL constants: define as module-level string constants for readability.
Error handling: `HTTPException` for 404; catch-all `except Exception` for 500.
Imports: `normalize_purl`, `normalize_cve_id` from `complira_graph.utils.keys`.

---

## Step 3 — Router Registration

File: `src/api/v1/router.py`

Add after Phase 6 pipeline router:
```python
from api.v1.endpoints import supply_chain
api_router.include_router(supply_chain.router, prefix="/supply-chain", tags=["supply-chain"])
```

---

## Step 4 — Unit Tests

File: `tests/unit/api/test_supply_chain_api.py`

Pattern: `app.dependency_overrides`, `TestClient`, `unittest.mock.MagicMock`
Scenarios: 9 test functions covering all 13 ACs (S-SC-001 through S-SC-009)

---

## Requirement Traceability

| Requirement | Design Section | Use Case | Implementation Tasks |
| --- | --- | --- | --- |
| REQ-SC-001 | §Component Detail Query | UC-SC-001 | Step 1 (models) + Step 2 (endpoint) |
| REQ-SC-002 | §Affected Projects Query | UC-SC-002 | Step 1 (models) + Step 2 (endpoint) |
| REQ-SC-003 | §Dependency Path Query | UC-SC-003 | Step 1 (models) + Step 2 (endpoint) |
| REQ-SC-004 | §Risk Summary Query | UC-SC-004 | Step 1 (models) + Step 2 (endpoint) |
