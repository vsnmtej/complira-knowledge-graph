# Supply Chain Intelligence API Reference

**Status:** Implemented
**Last Updated:** 2026-03-22
**Base Path:** `/v1/supply-chain`

---

## Overview

The Supply Chain Intelligence API exposes graph query endpoints over the SBOM dependency graph populated by the scan ingestion pipeline. Given a component PURL, CVE ID, or project ID, it returns dependency relationships, affected projects, traversal paths, and supply chain risk summaries.

All endpoints require authentication (`X-API-Key` or JWT). All results are tenant-scoped via `project_uses_component` edges.

**Data sources (read-only):**

| Collection | Purpose |
| --- | --- |
| `components` | Global component documents keyed by normalized PURL |
| `depends_on` | Directed dependency edges between components |
| `project_uses_component` | Edges linking tenant projects to components |
| `component_has_vuln` | Edges linking components to vulnerability documents |
| `vulnerabilities` | Vulnerability documents with CVE ID and severity |

**Tenant scoping:** Components are globally stored (no `tenant_id` on documents). All results are scoped to the caller's tenant via `project_uses_component` edges which carry `tenant_id`.

---

## Endpoints

### GET /v1/supply-chain/component

Returns component metadata, projects using it, direct dependencies, direct dependents, and CVE associations.

#### Query Parameters

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `purl` | `string` | Yes | Package URL (PURL) of the component |

#### Response: `ComponentDetailResponse`

```json
{
  "success": true,
  "data": {
    "purl": "pkg:npm/lodash@4.17.21",
    "name": "lodash",
    "version": "4.17.21",
    "type": "library",
    "projects": ["proj_abc123"],
    "dependencies": ["pkg:npm/foo@1.0.0"],
    "dependents": ["pkg:npm/my-app@2.0.0"],
    "vulnerabilities": ["CVE-2021-23337"]
  },
  "metadata": {"api_version": "v1"}
}
```

**Fields:**
- `projects` — project IDs for the caller's tenant that use this component (via `project_uses_component`)
- `dependencies` — PURLs of components this component directly depends on (OUTBOUND 1-hop `depends_on`)
- `dependents` — PURLs of components that directly depend on this component (INBOUND 1-hop `depends_on`)
- `vulnerabilities` — CVE IDs associated with this component (via `component_has_vuln`)

**Error responses:**
- `404` — component PURL unknown, or no project in the caller's tenant uses it

---

### GET /v1/supply-chain/affected-projects

Returns all projects (for the caller's tenant) that use a component affected by a given CVE.

#### Query Parameters

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `cve_id` | `string` | Yes | CVE identifier (e.g. `CVE-2021-44228`) |

#### Response: `AffectedProjectsResponse`

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "project_id": "proj_abc123",
        "component_purl": "pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
        "cve_id": "CVE-2021-44228"
      }
    ],
    "total": 1
  },
  "metadata": {"api_version": "v1"}
}
```

**Traversal:** CVE → `component_has_vuln` (INBOUND) → affected components → `project_uses_component` (INBOUND, tenant-filtered) → projects

Returns `items: []` with `total: 0` if no components are affected or no tenant projects use affected components.

---

### GET /v1/supply-chain/dependency-path

Finds the shortest dependency path between two components on `depends_on` edges.

#### Query Parameters

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `from_purl` | `string` | Yes | Source component PURL |
| `to_purl` | `string` | Yes | Target component PURL |

#### Response: `DependencyPathResponse`

```json
{
  "success": true,
  "data": {
    "found": true,
    "path": [
      "pkg:npm/my-app@1.0.0",
      "pkg:npm/express@4.18.0",
      "pkg:npm/lodash@4.17.21"
    ],
    "path_length": 3
  },
  "metadata": {"api_version": "v1"}
}
```

When no path exists:

```json
{
  "success": true,
  "data": {
    "found": false,
    "path": [],
    "path_length": 0
  },
  "metadata": {"api_version": "v1"}
}
```

**Tenant scoping:** Both source and target components must be accessible to the caller's tenant (at least one `project_uses_component` edge with the caller's `tenant_id` must exist for each). Components not accessible to the tenant silently return `found=false`.

---

### GET /v1/supply-chain/risk-summary

Returns a supply chain risk summary for a project.

#### Query Parameters

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `project_id` | `string` | Yes | Project identifier |

#### Response: `RiskSummaryResponse`

```json
{
  "success": true,
  "data": {
    "project_id": "proj_abc123",
    "total_components": 87,
    "vulnerable_components": 12,
    "critical_count": 2,
    "high_count": 7,
    "top_depended_on": [
      {"purl": "pkg:npm/lodash@4.17.21", "dependent_count": 23},
      {"purl": "pkg:npm/express@4.18.0", "dependent_count": 18},
      {"purl": "pkg:npm/axios@1.4.0", "dependent_count": 11}
    ]
  },
  "metadata": {"api_version": "v1"}
}
```

**Fields:**
- `total_components` — total components used by the project (via `project_uses_component`)
- `vulnerable_components` — components with at least one known CVE (via `component_has_vuln`)
- `critical_count` — count of CRITICAL severity vulnerabilities across all project components
- `high_count` — count of HIGH severity vulnerabilities across all project components
- `top_depended_on` — up to 5 most-depended-on components by INBOUND `depends_on` edge count

**Error responses:**
- `404` — project does not exist or does not belong to the caller's tenant

---

## Error Responses

| Status | Scenario |
| --- | --- |
| 401 | Missing or invalid authentication |
| 404 | Component/project not found or not accessible to tenant |
| 500 | Internal server error |

---

## Implementation

| File | Purpose |
| --- | --- |
| `src/api/models/responses/supply_chain.py` | Response models (`ComponentDetailResponse`, `AffectedProjectsResponse`, `DependencyPathResponse`, `RiskSummaryResponse`) |
| `src/api/v1/endpoints/supply_chain.py` | 4 endpoint handlers with inline AQL |
| `src/api/v1/router.py` | Router registration under `/supply-chain` prefix |

---

## Tests

| File | Type | Count |
| --- | --- | --- |
| `tests/unit/api/test_supply_chain_api.py` | Unit (TestClient) | 14 |

**AC Coverage:** 13/13 acceptance criteria (AC-SC-001 – AC-SC-013) closed.
