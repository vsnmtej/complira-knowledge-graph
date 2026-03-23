# API/E2E Testing — compliance-violation-mapping

**Stage:** 7
**Last Updated:** 2026-03-22

---

## Acceptance Criteria Matrix

| AC ID | Requirement | Scenario | Status |
| --- | --- | --- | --- |
| AC-CV-001 | REQ-CV-001 | S-CV-001 | Passed ✅ |
| AC-CV-002 | REQ-CV-001 | S-CV-001 | Passed ✅ |
| AC-CV-003 | REQ-CV-001 | S-CV-002 | Passed ✅ |
| AC-CV-004 | REQ-CV-001 | S-CV-001 | Passed ✅ |
| AC-CV-005 | REQ-CV-001 | S-CV-003 | Passed ✅ |
| AC-CV-006 | REQ-CV-002 | S-CV-004 | Passed ✅ |
| AC-CV-007 | REQ-CV-002 | S-CV-005 | Passed ✅ |
| AC-CV-008 | REQ-CV-002 | S-CV-006 | Passed ✅ |
| AC-CV-009 | REQ-CV-002 | S-CV-007 | Passed ✅ |
| AC-CV-010 | REQ-CV-003 | S-CV-008 | Passed ✅ |
| AC-CV-011 | REQ-CV-003 | S-CV-008 | Passed ✅ |
| AC-CV-012 | REQ-CV-003 | S-CV-009 | Passed ✅ |
| AC-CV-013 | REQ-CV-004 | S-CV-010 | Passed ✅ |
| AC-CV-014 | REQ-CV-004 | S-CV-010 | Passed ✅ |
| AC-CV-015 | REQ-CV-004 | S-CV-011 | Passed ✅ |

---

## Scenarios

### S-CV-001: Pipeline creates edges for finding with CVE mapping
- **Requirement:** REQ-CV-001 | **Use case:** UC-CV-001
- **Type:** Ingestion unit test (mocked repo)
- **ACs:** AC-CV-001, AC-CV-002, AC-CV-004
- **Result:** Passed ✅ (`test_edges_written_for_finding_with_controls`, `test_status_set_to_violations_mapped_on_success`)
- **Evidence:** Edge has `_from=scan_findings/fp1`, `_to=oscal_controls/AC-2`, `tenant_id`, `control_id`, `framework`, `confidence=1.0`, `evidence_path`

### S-CV-002: Pipeline — CVE with no control mapping produces no edges
- **Requirement:** REQ-CV-001 | **Use case:** UC-CV-002
- **Type:** Ingestion unit test
- **ACs:** AC-CV-003
- **Result:** Passed ✅ (`test_no_edges_for_cve_with_no_controls`)

### S-CV-003: Edge _key is deterministic (idempotency)
- **Requirement:** REQ-CV-001 | **Use case:** UC-CV-007
- **Type:** Ingestion unit test
- **ACs:** AC-CV-005
- **Result:** Passed ✅ (`test_same_finding_and_control_produce_same_edge_key`)

### S-CV-004: Pipeline sets status to `violations_mapped`
- **Requirement:** REQ-CV-002 | **Use case:** UC-CV-003
- **Type:** Ingestion unit test
- **ACs:** AC-CV-006
- **Result:** Passed ✅ (`test_status_set_to_violations_mapped_on_success`, `test_status_still_set_when_no_controls`)

### S-CV-005: Pipeline with zero findings — no error, status set
- **Requirement:** REQ-CV-002 | **Use case:** UC-CV-006
- **Type:** Ingestion unit test
- **ACs:** AC-CV-007
- **Result:** Passed ✅ (`test_zero_findings_sets_status_without_error`)

### S-CV-006: PipelineCoordinator runs ViolationMappingPipeline after ControlMappingPipeline
- **Requirement:** REQ-CV-002 | **Use case:** UC-CV-003
- **Type:** Integration evidence — coordinator code inspection + `test_cve_dedup_one_traversal_per_unique_cve`
- **ACs:** AC-CV-008
- **Result:** Passed ✅ (coordinator wires stage after `_MAPPING_DONE` guard)

### S-CV-007: Coordinator skips stage when status is `violations_mapped`
- **Requirement:** REQ-CV-002 | **Use case:** UC-CV-008
- **Type:** Integration evidence — `_VIOLATION_DONE` guard set in coordinator
- **ACs:** AC-CV-009
- **Result:** Passed ✅ (`_VIOLATION_DONE = frozenset({"violations_mapped", ...})`)

### S-CV-008: GET /v1/compliance/violations returns 200 with items
- **Requirement:** REQ-CV-003 | **Use case:** UC-CV-004
- **Type:** API (TestClient)
- **ACs:** AC-CV-010, AC-CV-011
- **Command:** `TestClient.get("/v1/compliance/violations?scan_run_id=run123")`
- **Result:** Passed ✅ (`test_violations_returns_200_with_items`, `test_violations_items_include_required_fields`)

### S-CV-009: GET /v1/compliance/violations returns 404 for wrong tenant
- **Requirement:** REQ-CV-003 | **Use case:** UC-CV-004 (error path)
- **Type:** API (TestClient)
- **ACs:** AC-CV-012
- **Result:** Passed ✅ (`test_violations_404_for_wrong_tenant`)

### S-CV-010: GET /v1/compliance/coverage returns 200 with required fields
- **Requirement:** REQ-CV-004 | **Use case:** UC-CV-005
- **Type:** API (TestClient)
- **ACs:** AC-CV-013, AC-CV-014
- **Result:** Passed ✅ (`test_coverage_returns_200_with_required_fields`, `test_coverage_by_framework_includes_required_fields`)

### S-CV-011: GET /v1/compliance/coverage returns 404 for wrong tenant
- **Requirement:** REQ-CV-004 | **Use case:** UC-CV-005 (error path)
- **Type:** API (TestClient)
- **ACs:** AC-CV-015
- **Result:** Passed ✅ (`test_coverage_404_for_wrong_tenant`)

---

## Stage 7 Gate

All 15 acceptance criteria mapped to scenarios and passed. 17/17 unit+API tests pass. Full suite: 687/687.

**Stage 7 gate: PASS ✅**
