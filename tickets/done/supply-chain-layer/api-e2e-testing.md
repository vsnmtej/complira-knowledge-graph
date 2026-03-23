# API/E2E Testing: Supply Chain Intelligence Layer

**Ticket:** `supply-chain-layer`
**Stage:** 7
**Date:** 2026-03-22

---

## Acceptance Criteria Matrix

| AC ID | Requirement | Stage 7 Scenario | Status |
| --- | --- | --- | --- |
| AC-SC-001 | REQ-SC-001 | S-SC-001 | Passed ✅ |
| AC-SC-002 | REQ-SC-001 | S-SC-001 | Passed ✅ |
| AC-SC-003 | REQ-SC-001 | S-SC-001 | Passed ✅ |
| AC-SC-004 | REQ-SC-001 | S-SC-001 | Passed ✅ |
| AC-SC-005 | REQ-SC-001 | S-SC-002 | Passed ✅ |
| AC-SC-006 | REQ-SC-002 | S-SC-003 | Passed ✅ |
| AC-SC-007 | REQ-SC-002 | S-SC-004 | Passed ✅ |
| AC-SC-008 | REQ-SC-002 | S-SC-005 | Passed ✅ |
| AC-SC-009 | REQ-SC-003 | S-SC-006 | Passed ✅ |
| AC-SC-010 | REQ-SC-003 | S-SC-007 | Passed ✅ |
| AC-SC-011 | REQ-SC-004 | S-SC-008 | Passed ✅ |
| AC-SC-012 | REQ-SC-004 | S-SC-008 | Passed ✅ |
| AC-SC-013 | REQ-SC-004 | S-SC-009 | Passed ✅ |

All 13 ACs mapped and passed.

---

## Test Scenarios

### S-SC-001 — Component detail happy path
- **AC coverage:** AC-SC-001, AC-SC-002, AC-SC-003, AC-SC-004
- **Requirement:** REQ-SC-001
- **Use case:** UC-SC-001
- **Source:** Requirement
- **Level:** API (TestClient)
- **Expected:** 200 OK; response includes `purl`, `name`, `version`, `type`, `projects`, `dependencies`, `dependents`, `vulnerabilities`
- **Tests:** `test_component_detail_includes_purl_name_version_type`, `test_component_detail_includes_projects`, `test_component_detail_includes_dependencies_and_dependents`, `test_component_detail_includes_vulnerabilities`
- **Result:** Passed ✅

### S-SC-002 — Component detail 404
- **AC coverage:** AC-SC-005
- **Requirement:** REQ-SC-001
- **Use case:** UC-SC-001 (error path)
- **Source:** Requirement
- **Level:** API (TestClient)
- **Expected:** 404 for unknown PURL; 404 when tenant has no project using component
- **Tests:** `test_component_detail_404_unknown_purl`, `test_component_detail_404_no_tenant_access`
- **Result:** Passed ✅

### S-SC-003 — Affected projects happy path
- **AC coverage:** AC-SC-006
- **Requirement:** REQ-SC-002
- **Use case:** UC-SC-002
- **Source:** Requirement
- **Level:** API (TestClient)
- **Expected:** 200 OK; items include `project_id`, `component_purl`, `cve_id`
- **Tests:** `test_affected_projects_items_include_required_fields`
- **Result:** Passed ✅

### S-SC-004 — Affected projects empty result
- **AC coverage:** AC-SC-007
- **Requirement:** REQ-SC-002
- **Use case:** UC-SC-002 (fallback path)
- **Source:** Requirement
- **Level:** API (TestClient)
- **Expected:** 200 OK; `items=[]`, `total=0`
- **Tests:** `test_affected_projects_empty_for_unknown_cve`
- **Result:** Passed ✅

### S-SC-005 — Affected projects tenant scoping
- **AC coverage:** AC-SC-008
- **Requirement:** REQ-SC-002
- **Use case:** UC-SC-002
- **Source:** Requirement
- **Level:** API (TestClient)
- **Expected:** AQL bind_vars contains `tenant_id` matching the caller's tenant; verified via call tracking mock
- **Tests:** `test_affected_projects_tenant_scoped`
- **Result:** Passed ✅

### S-SC-006 — Dependency path found
- **AC coverage:** AC-SC-009
- **Requirement:** REQ-SC-003
- **Use case:** UC-SC-003
- **Source:** Requirement
- **Level:** API (TestClient)
- **Expected:** 200 OK; `found=true`, `path` list populated, `path_length > 0`
- **Tests:** `test_dependency_path_found`
- **Result:** Passed ✅

### S-SC-007 — Dependency path not found
- **AC coverage:** AC-SC-010
- **Requirement:** REQ-SC-003
- **Use case:** UC-SC-003 (fallback path)
- **Source:** Requirement
- **Level:** API (TestClient)
- **Expected:** 200 OK; `found=false`, `path=[]`, `path_length=0`
- **Tests:** `test_dependency_path_not_found`
- **Result:** Passed ✅

### S-SC-008 — Risk summary happy path
- **AC coverage:** AC-SC-011, AC-SC-012
- **Requirement:** REQ-SC-004
- **Use case:** UC-SC-004
- **Source:** Requirement
- **Level:** API (TestClient)
- **Expected:** 200 OK; includes `total_components`, `vulnerable_components`, `critical_count`, `high_count`, `top_depended_on` with `purl` and `dependent_count`; `top_depended_on` ≤ 5 entries
- **Tests:** `test_risk_summary_includes_required_fields`, `test_risk_summary_top_depended_on`
- **Result:** Passed ✅

### S-SC-009 — Risk summary 404
- **AC coverage:** AC-SC-013
- **Requirement:** REQ-SC-004
- **Use case:** UC-SC-004 (error path)
- **Source:** Requirement
- **Level:** API (TestClient)
- **Expected:** 404 when project not found for tenant
- **Tests:** `test_risk_summary_404_project_not_found`
- **Result:** Passed ✅

---

## Execution

**Command:**
```bash
.venv/bin/python -m pytest tests/unit/api/test_supply_chain_api.py --override-ini="addopts=" -v
```

**Result:** 14 passed, 0 failed

**Full suite:** 670 passed, 0 failed — no regressions

---

## Feasibility Notes

All 9 scenarios are fully executable via `TestClient` with mocked ArangoDB. No infeasible scenarios. No environment blockers. No user waivers required.

---

## Stage 7 Gate Decision

All 13 acceptance criteria mapped and passed. All 9 scenarios passed. No failures, no blockers.

**Stage 7 Gate: PASS** ✅
