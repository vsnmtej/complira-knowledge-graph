# Requirements: Supply Chain Intelligence Layer

**Status:** Design-ready
**Ticket:** `supply-chain-layer`
**Branch:** `codex/supply-chain-layer`
**Date:** 2026-03-22

---

## Goal / Problem Statement

SBOM component ingestion is complete — `components`, `depends_on`, and `project_uses_component` collections are populated. This ticket exposes supply chain intelligence through a query API: given a PURL or CVE ID or project ID, return dependency relationships, affected projects, traversal paths, and risk summaries. This turns the passive graph data into actionable supply chain intelligence.

---

## Scope Triage

**Classification: Medium**

Signals:
- New public API surface (4 endpoints under `/v1/supply-chain/...`)
- 4 new/modified files: response models, endpoint file, router registration, test file
- AQL graph traversal patterns (SHORTEST_PATH, multi-hop INBOUND/OUTBOUND)
- Cross-layer change: response models + endpoint router + router registration

---

## In-Scope Use Cases

| use_case_id | Description |
| --- | --- |
| UC-SC-001 | `GET /v1/supply-chain/component?purl=...` — returns component metadata, projects using it, direct deps/dependents, and vulnerability associations |
| UC-SC-002 | `GET /v1/supply-chain/affected-projects?cve_id=...` — returns all projects transitively using a CVE-affected component |
| UC-SC-003 | `GET /v1/supply-chain/dependency-path?from_purl=...&to_purl=...` — finds shortest dependency path between two components |
| UC-SC-004 | `GET /v1/supply-chain/risk-summary?project_id=...` — returns supply chain risk summary for a project |

---

## Requirements

### REQ-SC-001 — Component Detail Query

`GET /v1/supply-chain/component?purl=<encoded_purl>` returns component document plus: projects using it (via `project_uses_component` edges, scoped to caller `tenant_id`), direct dependency PURLs (OUTBOUND 1-hop `depends_on`), direct dependent PURLs (INBOUND 1-hop `depends_on`), and associated CVE IDs (via `component_has_vuln` edges). Tenant scoping via `project_uses_component`. Returns 404 if no component with that PURL exists or the tenant has no project using it.

**Expected outcome:** `200 OK` with `ComponentDetailResponse` when component exists and tenant has at least one project using it; `404` otherwise.

### REQ-SC-002 — Affected Projects Query

`GET /v1/supply-chain/affected-projects?cve_id=CVE-XXXX` normalizes the CVE ID to a key (e.g., `CVE_2021_44228`), traverses `component_has_vuln` INBOUND to find components associated with that CVE, then traverses `project_uses_component` INBOUND to find projects using those components. Returns list of `{project_id, component_purl, cve_id}`. Tenant-scoped via `tenant_id` on `project_uses_component` edges. Returns empty list when no affected components exist.

**Expected outcome:** `200 OK` with `AffectedProjectsResponse` (possibly empty `items` list) for any valid CVE ID string.

### REQ-SC-003 — Dependency Path Query

`GET /v1/supply-chain/dependency-path?from_purl=...&to_purl=...` finds shortest path between two components on `depends_on` edges using ArangoDB `SHORTEST_PATH`. Returns `{path: [purl, ...], path_length: N, found: bool}`. Returns `found=false` and empty path when no path exists. Tenant scoping: both `from_purl` and `to_purl` must be accessible to the caller's tenant (at least one `project_uses_component` edge with the caller's `tenant_id` must exist for each component).

**Expected outcome:** `200 OK` with `DependencyPathResponse`; `found=true` with populated path when path exists; `found=false` with empty path and `path_length=0` when no path.

### REQ-SC-004 — Risk Summary Query

`GET /v1/supply-chain/risk-summary?project_id=...` returns supply chain risk summary for a project belonging to the caller's tenant: `{total_components, vulnerable_components, critical_count, high_count, top_depended_on: [{purl, dependent_count}]}`. Tenant-scoped: project must belong to caller's `tenant_id`. Returns 404 if project does not exist for the tenant. `top_depended_on` contains up to 5 entries sorted DESC by INBOUND `depends_on` edge count.

**Expected outcome:** `200 OK` with `RiskSummaryResponse` when project belongs to tenant; `404` if project not found.

---

## Acceptance Criteria

| AC ID | Requirement | Criterion |
| --- | --- | --- |
| AC-SC-001 | REQ-SC-001 | Component detail response includes `purl`, `name`, `version`, `type` fields |
| AC-SC-002 | REQ-SC-001 | Response includes `projects` list with project IDs |
| AC-SC-003 | REQ-SC-001 | Response includes `dependencies` and `dependents` lists (PURLs) |
| AC-SC-004 | REQ-SC-001 | Response includes `vulnerabilities` list of CVE IDs |
| AC-SC-005 | REQ-SC-001 | Returns 404 for unknown PURL or PURL not accessible to tenant |
| AC-SC-006 | REQ-SC-002 | Affected-projects response items include `project_id`, `component_purl`, `cve_id` fields |
| AC-SC-007 | REQ-SC-002 | Returns empty `items` list for CVE with no affected components |
| AC-SC-008 | REQ-SC-002 | Results are scoped to caller's `tenant_id` only |
| AC-SC-009 | REQ-SC-003 | Returns path list and `path_length` when path exists |
| AC-SC-010 | REQ-SC-003 | Returns `found=false` and empty path when no path exists |
| AC-SC-011 | REQ-SC-004 | Risk summary includes `total_components`, `vulnerable_components`, `critical_count`, `high_count` |
| AC-SC-012 | REQ-SC-004 | `top_depended_on` contains up to 5 entries with `purl` and `dependent_count` |
| AC-SC-013 | REQ-SC-004 | Returns 404 when `project_id` not found for tenant |

---

## Constraints / Dependencies

- No new ArangoDB collections — all queries use existing collections (`components`, `depends_on`, `project_uses_component`, `component_has_vuln`, `vulnerabilities`)
- All queries use AQL via `db.aql.execute()` — no in-memory graph traversal
- All results tenant-scoped via `tenant_id` on `project_uses_component` edges (not on `component_has_vuln` or `components` documents)
- PURL must be a **query parameter** (not path parameter) to avoid URL encoding conflicts with PURL special characters (`:`, `/`, `@`)
- New FastAPI router `GET /v1/supply-chain/...`
- New Pydantic v2 response models in `src/api/models/responses/supply_chain.py`
- Auth + DB injection pattern: `customer: Customer = Depends(get_current_customer)`, `ref_db = get_reference_db()`
- PURL key normalization via `normalize_purl()` from `src/complira_graph/utils/keys.py`
- CVE key normalization via `normalize_cve_id()` from `src/complira_graph/utils/keys.py`

---

## Assumptions

- `components` documents have `purl`, `name`, `version`, `type` fields
- `project_uses_component` edges have `tenant_id`, `_from` (projects/*), `_to` (components/*)
- `component_has_vuln` edges have `_from` (components/*), `_to` (vulnerabilities/*)
- `vulnerabilities` documents have `severity` field (CRITICAL/HIGH/MEDIUM/LOW)
- `depends_on` edges are directed from dependant to dependency (OUTBOUND = dependencies, INBOUND = dependents)
- Severity count for risk summary: query `vulnerabilities` document via INBOUND traversal from `component_has_vuln` edge; `severity` is a string field on `vulnerabilities`

---

## Open Questions / Risks

| # | Question | Status |
| --- | --- | --- |
| OQ-1 | Does a `supply_chain.py` router already exist? | Resolved — fully new (FINDING-1) |
| OQ-2 | How is the router registered? | Resolved — `api_router.include_router(supply_chain.router, prefix="/supply-chain", ...)` in `router.py` (FINDING-1) |
| OQ-3 | AQL shortest path pattern? | Resolved — ArangoDB `SHORTEST_PATH` AQL primitive (FINDING-5) |
| OQ-4 | Does `component_has_vuln` store severity? | Resolved — No; severity is on `vulnerabilities` document (OQ-4 in investigation-notes) |

---

## Requirement Coverage Map (Req → Use Case)

| Requirement | Use Case |
| --- | --- |
| REQ-SC-001 | UC-SC-001 |
| REQ-SC-002 | UC-SC-002 |
| REQ-SC-003 | UC-SC-003 |
| REQ-SC-004 | UC-SC-004 |

## Acceptance Criteria Coverage Map (AC → Stage 7 Scenario)

| AC ID | Mapped Stage 7 Scenario(s) |
| --- | --- |
| AC-SC-001 | S-SC-001 (component detail happy path) |
| AC-SC-002 | S-SC-001 (component detail happy path) |
| AC-SC-003 | S-SC-001 (component detail happy path) |
| AC-SC-004 | S-SC-001 (component detail happy path) |
| AC-SC-005 | S-SC-002 (component detail 404) |
| AC-SC-006 | S-SC-003 (affected projects happy path) |
| AC-SC-007 | S-SC-004 (affected projects empty result) |
| AC-SC-008 | S-SC-005 (affected projects tenant scoping) |
| AC-SC-009 | S-SC-006 (dependency path found) |
| AC-SC-010 | S-SC-007 (dependency path not found) |
| AC-SC-011 | S-SC-008 (risk summary happy path) |
| AC-SC-012 | S-SC-008 (risk summary happy path) |
| AC-SC-013 | S-SC-009 (risk summary 404) |
