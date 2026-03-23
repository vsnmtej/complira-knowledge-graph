# Future-State Runtime Call Stack Review: Supply Chain Intelligence Layer

**Ticket:** `supply-chain-layer`
**Design Basis:** `proposed-design.md` v1 / `future-state-runtime-call-stack.md` v1
**Date:** 2026-03-22

---

## Round 1

**Round status:** Candidate Go
**Clean-review streak:** 1 / 2

### Missing-Use-Case Discovery Sweep

Boundary crossings checked:
- Auth boundary: all 4 handlers use `Depends(get_current_customer)` ✅
- DB boundary: all 4 handlers use `get_reference_db()` ✅
- Tenant-scoping boundary: all 4 handlers scope via `tenant_id` on `project_uses_component` edges ✅

Fallback/error branches checked:
- UC-SC-001: 404 for unknown PURL or no tenant access ✅
- UC-SC-002: empty list when no CVE match ✅
- UC-SC-003: `found=false` when no path ✅
- UC-SC-004: 404 for unknown project_id ✅
- All 4: 500 on unexpected exception ✅

Design-risk scenarios:
- PURL special chars: PURL is a query parameter, no routing conflict ✅
- tenant isolation: `project_uses_component` edge filter is the correct gate per FINDING-4 and FINDING-6 ✅
- AQL SHORTEST_PATH: returns 0 rows when no path → `found=false` correctly handled ✅
- `component_has_vuln` has no required `tenant_id` → scoping via `project_uses_component` correct ✅

No new use cases discovered in this sweep.

### Per-Use-Case Review

#### UC-SC-001 — Component Detail

| Check | Result | Notes |
| --- | --- | --- |
| Architecture fit | Pass | AQL-in-endpoint is established pattern; appropriate for read-only query |
| Layering fitness | Pass | No unnecessary layers; flat handler → AQL → response model |
| Boundary placement | Pass | Auth/DB injected; no logic leak to models |
| Existing-structure bias | Pass | Pattern matches reference.py; not forced to current layout unnecessarily |
| Anti-hack check | Pass | No workarounds |
| Local-fix degradation | N/A | New feature |
| Terminology/vocabulary | Pass | `dependencies`, `dependents`, `vulnerabilities`, `projects` — all natural |
| File/API naming | Pass | `get_component_detail`, `ComponentDetailResponse` clear |
| Name-to-responsibility alignment | Pass | No drift |
| Future-state alignment | Pass | Matches proposed-design.md v1 |
| Use-case coverage completeness | Pass | Primary + 404 fallback + 500 error all covered |
| Use-case source traceability | Pass | Source = REQ-SC-001 |
| Requirement coverage closure | Pass | REQ-SC-001 fully mapped |
| Layer-appropriate SoC | Pass | Response models in own file; AQL inline per pattern |
| Dependency flow smells | Pass | None |
| Redundancy/duplication | Pass | None |
| Simplification opportunity | Pass | Single AQL query covers all subfields; appropriate |
| Decommission/cleanup | N/A | New file |
| No-legacy check | Pass | No compatibility shims |
| **Overall verdict** | **Pass** | |

**Issue:** The call stack uses `PARSE_IDENTIFIER(e._from).key` for project IDs. This AQL function returns the collection-local `_key` from a document ID string. This is correct for extracting `project_id` from `projects/<key>`. ✅

#### UC-SC-002 — Affected Projects

| Check | Result | Notes |
| --- | --- | --- |
| Architecture fit | Pass | AQL traversal for INBOUND CVE → component → project |
| Layering fitness | Pass | Flat handler pattern |
| Boundary placement | Pass | Tenant scoping via `project_uses_component` correct per FINDING-4 |
| Existing-structure bias | Pass | |
| Anti-hack check | Pass | |
| Local-fix degradation | N/A | New feature |
| Terminology/vocabulary | Pass | `affected_projects`, `items`, `AffectedProjectItem` clear |
| File/API naming | Pass | `get_affected_projects` clear |
| Name-to-responsibility alignment | Pass | |
| Future-state alignment | Pass | Matches proposed-design.md v1 |
| Use-case coverage completeness | Pass | Primary + empty-list fallback + 500 error covered |
| Use-case source traceability | Pass | Source = REQ-SC-002 |
| Requirement coverage closure | Pass | REQ-SC-002 fully mapped |
| Layer-appropriate SoC | Pass | |
| Dependency flow smells | Pass | |
| Redundancy/duplication | Pass | |
| Simplification opportunity | Pass | |
| Decommission/cleanup | N/A | |
| No-legacy check | Pass | |
| **Overall verdict** | **Pass** | |

**AQL note:** The call stack uses a nested FOR loop (component FOR → project edge FOR). This is correct for ArangoDB — the nested structure is idiomatic for multi-hop traversals. `FILTER LENGTH(projects) > 0` correctly excludes components not used by this tenant. ✅

#### UC-SC-003 — Dependency Path

| Check | Result | Notes |
| --- | --- | --- |
| Architecture fit | Pass | SHORTEST_PATH is the right AQL primitive; no in-memory BFS |
| Layering fitness | Pass | |
| Boundary placement | Pass | Tenant access gate before SHORTEST_PATH is correct — avoids leaking cross-tenant path info |
| Existing-structure bias | Pass | |
| Anti-hack check | Pass | |
| Local-fix degradation | N/A | New feature |
| Terminology/vocabulary | Pass | `found`, `path`, `path_length` clear |
| File/API naming | Pass | `get_dependency_path`, `DependencyPathResponse` clear |
| Name-to-responsibility alignment | Pass | |
| Future-state alignment | Pass | |
| Use-case coverage completeness | Pass | Path found + no path + inaccessible component (returns found=false silently) covered |
| Use-case source traceability | Pass | Source = REQ-SC-003 |
| Requirement coverage closure | Pass | REQ-SC-003 fully mapped |
| Layer-appropriate SoC | Pass | |
| Dependency flow smells | Pass | |
| Redundancy/duplication | Pass | |
| Simplification opportunity | Pass | |
| Decommission/cleanup | N/A | |
| No-legacy check | Pass | |
| **Overall verdict** | **Pass** | |

**AQL note:** The call stack uses a ternary expression in AQL (`from_access != null AND to_access != null ? (...) : []`). ArangoDB AQL supports ternary operators. The inner `SHORTEST_PATH` FOR loop returns 0–1 result objects; wrapping in `path_result = (...)` makes it a subquery list. If no path exists the inner FOR returns nothing, so `path_result = []`. ✅

**Correction noted:** AQL ternary in a LET is valid but the `RETURN path_result` returns a list-of-lists `[[...]]`. Implementation will need to handle `result[0][0]` extraction. This is an implementation-level detail, not a design issue. Will be handled correctly in the endpoint code. ✅

#### UC-SC-004 — Risk Summary

| Check | Result | Notes |
| --- | --- | --- |
| Architecture fit | Pass | Single AQL query aggregates all counts; appropriate for dashboard-style read |
| Layering fitness | Pass | |
| Boundary placement | Pass | `project_exists` flag allows 404 gate without a second DB round-trip |
| Existing-structure bias | Pass | |
| Anti-hack check | Pass | |
| Local-fix degradation | N/A | New feature |
| Terminology/vocabulary | Pass | `total_components`, `vulnerable_components`, `critical_count`, `high_count`, `top_depended_on` all natural |
| File/API naming | Pass | `get_risk_summary`, `RiskSummaryResponse`, `TopComponent` clear |
| Name-to-responsibility alignment | Pass | |
| Future-state alignment | Pass | |
| Use-case coverage completeness | Pass | Happy path + 404 project not found + 500 error covered |
| Use-case source traceability | Pass | Source = REQ-SC-004 |
| Requirement coverage closure | Pass | REQ-SC-004 fully mapped |
| Layer-appropriate SoC | Pass | |
| Dependency flow smells | Pass | |
| Redundancy/duplication | Pass | `project_components` LET reused in vuln + top-depended computations — correct DRY use |
| Simplification opportunity | Pass | Single AQL query is correct — avoids N+1 round trips |
| Decommission/cleanup | N/A | |
| No-legacy check | Pass | |
| **Overall verdict** | **Pass** | |

**AQL note:** The call stack uses `comp` (document object) in nested FOR loops (`FOR vuln IN 1..1 OUTBOUND comp`). In ArangoDB, if `comp` is a document (not an ID string), the `OUTBOUND` traversal needs the document's `_id`, not the document itself. AQL traversal `FOR v IN 1..1 OUTBOUND comp edge_collection` does accept a document variable (ArangoDB implicitly uses `_id`). ✅

### Round 1 Summary

| Dimension | Result |
| --- | --- |
| All use cases Pass | ✅ |
| No blockers requiring persisted artifact updates | ✅ |
| No new use cases discovered | ✅ |
| Architecture fit all Pass | ✅ |
| Requirement coverage closure | ✅ (REQ-SC-001–004 all mapped) |
| AC coverage closure | ✅ (AC-SC-001–013 all mapped in requirements.md) |

**Round 1 verdict: Candidate Go** — no blockers, no required artifact updates, no new use cases discovered.

---

## Round 2

**Round status:** Go Confirmed
**Clean-review streak:** 2 / 2

### Missing-Use-Case Discovery Sweep (Round 2)

Re-checking boundary crossings and edge cases with deeper scrutiny:

**Auth boundary:** All 4 endpoints depend on `get_current_customer`. If the customer is unauthenticated, FastAPI raises 401 before the handler runs — this is handled by the auth middleware, not by the handler. No additional handling needed. ✅

**Tenant isolation — deeper check:**
- UC-SC-001: `tenant_projects` LET filters `project_uses_component` by both `_to == comp._id` AND `e.tenant_id == @tenant_id`. If a component is used by multiple tenants, only the caller's projects are returned. Correct. ✅
- UC-SC-002: `FILTER e._to == comp._id AND e.tenant_id == @tenant_id` in inner loop. Cross-tenant project IDs cannot appear in results. Correct. ✅
- UC-SC-003: Tenant gate uses `LIMIT 1 RETURN 1` — only checks existence, not count. Returns `null` if no edge exists, meaning inaccessible components return `found=false` silently (no 401/403 leak). This is correct behavior per design intent — supply chain paths are only meaningful within tenant scope. ✅
- UC-SC-004: `FILTER p._key == @project_id AND p.tenant_id == @tenant_id` in project verification. Correct. ✅

**SHORTEST_PATH output shape — re-verification:**
ArangoDB `FOR path IN OUTBOUND SHORTEST_PATH @from_id TO @to_id graph_or_edge` returns objects with `.vertices` array. The call stack uses `path.vertices[*].purl` in the RETURN. This is correct array expansion syntax for AQL. The LET wraps it in `(FOR path IN ... RETURN path.vertices[*].purl)` which produces a list of lists. The outer result after `RETURN path_result` is `[ [[purl1, purl2, ...]] ]`. Handler needs `result[0][0] if result and result[0] else []`. This detail is noted for implementation but does not require a design change. ✅

**Severity field on `vulnerabilities`:** Requirements assume `severity` is a string field on the `vulnerabilities` document. The `reference.py` endpoint confirms `cve.severity` is accessed directly. UPPER() is applied in the AQL for case-insensitive comparison. ✅

**No new use cases discovered.**

### Per-Use-Case Re-Review (Round 2)

Focused deep-review pass:

**UC-SC-001:**
- Response model `ComponentDetailResponse` wraps results correctly. Fields `purl`, `name`, `version`, `type` come from `comp.*` — these are present on `V22Component` documents per investigation FINDING-7/AC-SC-001. ✅
- `projects` field returns list of project `_key` values via `PARSE_IDENTIFIER(e._from).key`. ✅
- No issues. **Overall: Pass** ✅

**UC-SC-002:**
- `result[0]` is the `affected` list from AQL. The AQL `RETURN affected` returns a list at the outer level, so `result` from cursor is `[ [item1, item2, ...] ]`. Handler needs `result[0] if result else []`. The call stack says `result[0] if result else []`. ✅
- `total` field = `len(items)`. ✅
- No issues. **Overall: Pass** ✅

**UC-SC-003:**
- When `from_purl == to_purl`, SHORTEST_PATH returns a single-vertex path (the node itself). `path_length = 1`, `found = True`. This is mathematically correct and acceptable behavior. ✅
- No issues. **Overall: Pass** ✅

**UC-SC-004:**
- `project_exists` field used as 404 gate then stripped from response model construction: `{k: v for k, v in result[0].items() if k != "project_exists"}`. This is the correct approach to avoid Pydantic validation errors on extra fields. ✅
- `top_depended_on` up to 5 entries per AC-SC-012. `LIMIT 5` in AQL enforces this. ✅
- No issues. **Overall: Pass** ✅

### Round 2 Summary

| Dimension | Result |
| --- | --- |
| All use cases Pass | ✅ |
| No blockers requiring persisted artifact updates | ✅ |
| No new use cases discovered | ✅ |
| No required design/call-stack updates | ✅ |

**Round 2 verdict: Go Confirmed** — two consecutive clean rounds. Stage 5 gate is satisfied.

---

## Applied Updates

None. Both rounds found no required artifact updates.

---

## Gate Summary

| Gate | Status |
| --- | --- |
| Architecture fit (all UCs) | Pass ✅ |
| Layering fitness (all UCs) | Pass ✅ |
| Boundary placement (all UCs) | Pass ✅ |
| Existing-structure bias (all UCs) | Pass ✅ |
| Anti-hack check (all UCs) | Pass ✅ |
| Terminology/vocabulary (all UCs) | Pass ✅ |
| File/API naming clarity (all UCs) | Pass ✅ |
| Future-state alignment (all UCs) | Pass ✅ |
| Use-case coverage completeness (all UCs) | Pass ✅ |
| Requirement coverage closure | Pass ✅ |
| Decommission/cleanup (N/A new files) | Pass ✅ |
| No-legacy check | Pass ✅ |
| Clean-review streak | 2 consecutive ✅ |

**Stage 5 Gate: GO CONFIRMED** ✅
