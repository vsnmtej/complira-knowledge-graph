# Future-State Runtime Call Stack: Supply Chain Intelligence Layer

**Version:** v1
**Ticket:** `supply-chain-layer`
**Design Basis:** `proposed-design.md` v1
**Date:** 2026-03-22

---

## UC-SC-001 — Component Detail Query

**Source:** Requirement (REQ-SC-001)
**Coverage:** Primary path ✅ | Fallback (404) ✅ | Error (500) ✅

### Primary Path — Component Found, Tenant Has Access

```
HTTP GET /v1/supply-chain/component?purl=pkg:npm/lodash@4.17.21
  → FastAPI routing → supply_chain.router

src/api/v1/endpoints/supply_chain.py:get_component_detail(purl, customer, ...)
  → purl = "pkg:npm/lodash@4.17.21"                              [query param — no URL encoding issues]
  → customer = Customer(id="tenant_abc")                         [auth injection via Depends(get_current_customer)]
  → db = get_reference_db()                                      [DB injection]
  → comp_key = normalize_purl(purl)                              [→ "pkg_npm_lodash_4_17_21"]
      src/complira_graph/utils/keys.py:normalize_purl()
  → db.aql.execute(COMPONENT_DETAIL_QUERY, bind_vars={
        "comp_key": comp_key,
        "tenant_id": customer.id
    })                                                             [AQL: inline in handler]
      AQL:
        LET comp = DOCUMENT("components", @comp_key)
        // Tenant access gate: must have at least one project_uses_component edge
        LET tenant_projects = (
          FOR e IN project_uses_component
            FILTER e._to == comp._id AND e.tenant_id == @tenant_id
            RETURN PARSE_IDENTIFIER(e._from).key
        )
        // Direct dependencies (OUTBOUND 1-hop depends_on)
        LET deps = (
          FOR v IN 1..1 OUTBOUND comp depends_on RETURN v.purl
        )
        // Direct dependents (INBOUND 1-hop depends_on)
        LET dependents = (
          FOR v IN 1..1 INBOUND comp depends_on RETURN v.purl
        )
        // Associated CVEs (OUTBOUND component_has_vuln)
        LET vuln_ids = (
          FOR v IN 1..1 OUTBOUND comp component_has_vuln
            RETURN v.cve_id
        )
        RETURN {
          purl: comp.purl,
          name: comp.name,
          version: comp.version,
          type: comp.type,
          projects: tenant_projects,
          dependencies: deps,
          dependents: dependents,
          vulnerabilities: vuln_ids
        }
  → result = list(cursor)                                        [cursor to list]
  → result[0] is not None AND result[0].projects not empty       [tenant access gate check]
  → ComponentDetailResponse(**result[0])                        [Pydantic model construction]
  → return APIResponse(success=True, data=response, metadata=ResponseMetadata(api_version="v1"))
                                                                  [200 OK]
```

### Fallback Path — Unknown PURL or No Tenant Access

```
  → db.aql.execute(COMPONENT_DETAIL_QUERY, ...)
  → result = list(cursor)
  → result is empty OR result[0] is None OR result[0]["projects"] is empty
  → raise HTTPException(status_code=404, detail="Component not found: <purl>")
                                                                  [404 Not Found]
```

### Error Path — AQL Exception

```
  → db.aql.execute(...) raises Exception
  → except Exception as e:
      logger.error("supply_chain.component_detail.error", purl=purl, error=str(e))
      raise HTTPException(status_code=500, detail="Internal server error")
                                                                  [500 Internal Server Error]
```

---

## UC-SC-002 — Affected Projects Query

**Source:** Requirement (REQ-SC-002)
**Coverage:** Primary path ✅ | Fallback (empty list) ✅ | Error (500) ✅

### Primary Path — CVE Exists, Affected Components Found

```
HTTP GET /v1/supply-chain/affected-projects?cve_id=CVE-2021-44228
  → FastAPI routing → supply_chain.router

src/api/v1/endpoints/supply_chain.py:get_affected_projects(cve_id, customer, ...)
  → cve_id = "CVE-2021-44228"                                    [query param]
  → customer = Customer(id="tenant_abc")                         [auth injection]
  → db = get_reference_db()
  → cve_key = normalize_cve_id(cve_id)                          [→ "CVE_2021_44228"]
      src/complira_graph/utils/keys.py:normalize_cve_id()
  → db.aql.execute(AFFECTED_PROJECTS_QUERY, bind_vars={
        "cve_key": cve_key,
        "cve_id": cve_id,
        "tenant_id": customer.id
    })
      AQL:
        LET vuln = DOCUMENT("vulnerabilities", @cve_key)
        // INBOUND traversal: vulnerability → components with this vuln
        LET affected = (
          FOR comp IN 1..1 INBOUND vuln component_has_vuln
            // For each affected component, find projects for this tenant
            LET projects = (
              FOR e IN project_uses_component
                FILTER e._to == comp._id AND e.tenant_id == @tenant_id
                RETURN PARSE_IDENTIFIER(e._from).key
            )
            FILTER LENGTH(projects) > 0
            FOR proj_id IN projects
              RETURN {
                project_id: proj_id,
                component_purl: comp.purl,
                cve_id: @cve_id
              }
        )
        RETURN affected
  → items = result[0] if result else []                          [unwrap outer list]
  → AffectedProjectsResponse(items=[AffectedProjectItem(**r) for r in items], total=len(items))
  → return APIResponse(success=True, data=response, ...)
                                                                  [200 OK — may have items or be empty]
```

### Fallback Path — CVE Unknown or No Matching Components for Tenant

```
  → items = [] (AQL returns empty affected list)
  → AffectedProjectsResponse(items=[], total=0)
  → return APIResponse(success=True, data=response, ...)
                                                                  [200 OK with empty items]
```

### Error Path — AQL Exception

```
  → raise HTTPException(status_code=500, detail="Internal server error")
```

---

## UC-SC-003 — Dependency Path Query

**Source:** Requirement (REQ-SC-003)
**Coverage:** Primary path ✅ | Fallback (no path) ✅ | Error (500) ✅

### Primary Path — Path Exists Between Two Components

```
HTTP GET /v1/supply-chain/dependency-path?from_purl=pkg:npm/a@1.0&to_purl=pkg:npm/c@1.0
  → FastAPI routing → supply_chain.router

src/api/v1/endpoints/supply_chain.py:get_dependency_path(from_purl, to_purl, customer, ...)
  → from_key = normalize_purl(from_purl)                        [→ "pkg_npm_a_1_0"]
  → to_key = normalize_purl(to_purl)                            [→ "pkg_npm_c_1_0"]
  → db = get_reference_db()
  → db.aql.execute(DEPENDENCY_PATH_QUERY, bind_vars={
        "from_id": f"components/{from_key}",
        "to_id": f"components/{to_key}",
        "tenant_id": customer.id
    })
      AQL:
        // Verify from-component is accessible to tenant
        LET from_access = FIRST(
          FOR e IN project_uses_component
            FILTER e._to == @from_id AND e.tenant_id == @tenant_id
            LIMIT 1
            RETURN 1
        )
        // Verify to-component is accessible to tenant
        LET to_access = FIRST(
          FOR e IN project_uses_component
            FILTER e._to == @to_id AND e.tenant_id == @tenant_id
            LIMIT 1
            RETURN 1
        )
        // Find shortest path if both accessible
        LET path_result = (
          from_access != null AND to_access != null
            ? (
                FOR path IN OUTBOUND SHORTEST_PATH @from_id TO @to_id depends_on
                  RETURN path.vertices[*].purl
              )
            : []
        )
        RETURN path_result
  → path_vertices = result[0][0] if result and result[0] else []
  → found = len(path_vertices) > 0
  → DependencyPathResponse(found=found, path=path_vertices, path_length=len(path_vertices))
  → return APIResponse(success=True, data=response, ...)
                                                                  [200 OK — found=true, path=[...]]
```

**Note on SHORTEST_PATH AQL:** `FOR path IN OUTBOUND SHORTEST_PATH @from_id TO @to_id depends_on` returns path object with `.vertices` array. Each vertex is a component document with `.purl`. If no path exists, the FOR loop returns zero rows.

### Fallback Path — No Path Exists

```
  → path_vertices = []
  → DependencyPathResponse(found=False, path=[], path_length=0)
  → return APIResponse(success=True, data=response, ...)
                                                                  [200 OK — found=false]
```

### Fallback Path — Component Not Accessible to Tenant

```
  → from_access or to_access is null → path_result = []
  → DependencyPathResponse(found=False, path=[], path_length=0)
                                                                  [200 OK — found=false, access denied silently]
```

---

## UC-SC-004 — Risk Summary Query

**Source:** Requirement (REQ-SC-004)
**Coverage:** Primary path ✅ | Fallback (404) ✅ | Error (500) ✅

### Primary Path — Project Found for Tenant

```
HTTP GET /v1/supply-chain/risk-summary?project_id=proj_123
  → FastAPI routing → supply_chain.router

src/api/v1/endpoints/supply_chain.py:get_risk_summary(project_id, customer, ...)
  → project_id = "proj_123"
  → customer = Customer(id="tenant_abc")
  → db = get_reference_db()
  → db.aql.execute(RISK_SUMMARY_QUERY, bind_vars={
        "project_id": project_id,
        "tenant_id": customer.id
    })
      AQL:
        // Verify project belongs to tenant
        LET project_doc = FIRST(
          FOR p IN projects
            FILTER p._key == @project_id AND p.tenant_id == @tenant_id
            RETURN p
        )
        // All components used by this project
        LET project_components = (
          FOR e IN project_uses_component
            FILTER e._from == CONCAT("projects/", @project_id) AND e.tenant_id == @tenant_id
            RETURN DOCUMENT(e._to)
        )
        // Vulnerable components (have at least one component_has_vuln edge)
        LET vuln_components = (
          FOR comp IN project_components
            LET vuln_count = LENGTH(
              FOR e IN 1..1 OUTBOUND comp component_has_vuln RETURN 1
            )
            FILTER vuln_count > 0
            RETURN comp
        )
        // Critical + High severity counts
        LET crit_count = LENGTH(
          FOR comp IN vuln_components
            FOR vuln IN 1..1 OUTBOUND comp component_has_vuln
              FILTER UPPER(vuln.severity) == "CRITICAL"
              RETURN 1
        )
        LET high_count = LENGTH(
          FOR comp IN vuln_components
            FOR vuln IN 1..1 OUTBOUND comp component_has_vuln
              FILTER UPPER(vuln.severity) == "HIGH"
              RETURN 1
        )
        // Top 5 most-depended-on components (by INBOUND depends_on count)
        LET top_depended = (
          FOR comp IN project_components
            LET dep_count = LENGTH(
              FOR e IN 1..1 INBOUND comp depends_on RETURN 1
            )
            SORT dep_count DESC
            LIMIT 5
            RETURN { purl: comp.purl, dependent_count: dep_count }
        )
        RETURN {
          project_exists: project_doc != null,
          project_id: @project_id,
          total_components: LENGTH(project_components),
          vulnerable_components: LENGTH(vuln_components),
          critical_count: crit_count,
          high_count: high_count,
          top_depended_on: top_depended
        }
  → result = list(cursor)
  → result[0]["project_exists"] == False → raise HTTPException(status_code=404, ...)
  → RiskSummaryResponse(**{k: v for k, v in result[0].items() if k != "project_exists"})
  → return APIResponse(success=True, data=response, ...)
                                                                  [200 OK]
```

### Fallback Path — Project Not Found for Tenant

```
  → result[0]["project_exists"] == False
  → raise HTTPException(status_code=404, detail="Project not found: <project_id>")
                                                                  [404 Not Found]
```

### Error Path — AQL Exception

```
  → raise HTTPException(status_code=500, detail="Internal server error")
```

---

## Async / State Boundaries

- All endpoint handlers are `async def` (FastAPI standard)
- `db.aql.execute()` is synchronous (ArangoDB Python driver); runs in async context but does not block event loop in test harness since TestClient is used in unit tests
- No background tasks, queues, or external async I/O in this feature
- No in-memory state mutations — all queries are read-only

---

## Data Transformations Per Use Case

| UC | Input | AQL Output | Response Model |
| --- | --- | --- | --- |
| UC-SC-001 | raw PURL string | component doc + edge traversal results | `ComponentDetailResponse` |
| UC-SC-002 | CVE ID string | list of {project_id, component_purl, cve_id} | `AffectedProjectsResponse` |
| UC-SC-003 | two PURL strings | path vertices with purl field | `DependencyPathResponse` |
| UC-SC-004 | project_id string | aggregated counts + top components | `RiskSummaryResponse` |
