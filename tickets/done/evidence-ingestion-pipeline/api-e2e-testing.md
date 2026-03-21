# API/E2E Testing: Evidence Data Ingestion Pipeline

## Stage 7 Status

- Stage: `7`
- Gate Status: `In Progress`
- Code Edit Permission: `Unlocked`
- Re-Entry: `Local Fix (cleared)` — 16 integration tests updated to v2.2 API
- Last Updated: 2026-03-18

---

## Acceptance Criteria Matrix

| AC ID | Mapped Scenario IDs | Execution Status | Notes |
| --- | --- | --- | --- |
| AC-001 | S-001, S-004 | Passed | Unit: test_service.py (ingest_scan happy path); Integration stub: TestIngestScanIntegration |
| AC-002 | S-001, S-002 | Passed | Unit: test_service.py (complete_run called); Unit: test_repositories.py (complete) |
| AC-003 | S-006 | Passed | Unit: test_ingestion_engine.py (_fingerprint deterministic); test_repositories.py (upsert semantics) |
| AC-004 | S-003, S-007 | Passed | Unit: test_edge_service.py (component_has_vuln); test_ingestion_engine.py (grype path) |
| AC-005 | S-008 | Passed | Unit: test_repositories.py (EvidenceComponentRepository upsert); test_backfill.py (purl-keyed) |
| AC-006 | S-009 | Passed | Unit: test_edge_service.py (project_uses_component) |
| AC-007 | S-010 | Passed | Unit: test_edge_service.py (finding_maps_to_weakness) |
| AC-008 | S-011 | Passed | Unit: test_edge_service.py (finding_triggers_req checkov_native + llm_reg_mapper) |
| AC-009 | S-012 | Passed | Unit: test_edge_service.py (finding_in_component) |
| AC-010 | S-013 | Passed | Unit: test_edge_service.py (detected_control_maps_to, control_in_component stubs) |
| AC-011 | S-014 | Passed | Unit: test_service.py (_assemble_evidence_package call chain) |
| AC-012 | S-015, S-019 | Passed | Unit: test_service.py (tenant_id on all docs); Integration: TestIngestScanIntegration |
| AC-013 | S-016 | Passed | Unit: test_ingestion_engine.py (_classify_severity semgrep ERROR→critical; _extract_cwe; _validate CVE) |
| AC-014 | S-017 | Passed | Unit: test_backfill.py (customer_id→tenant_id; tool_name→tools_invoked; purl-keyed component; tenant_id removed from component) |
| AC-015 | S-018 | Passed | Unit: test_edge_service.py (edge key determinism; re-ingestion no duplicate) |
| AC-016 | S-020 | Passed | Full suite: 880 passed, 1 skipped (e2e live-infra skip) — zero regressions |
| AC-017 | S-021 | Passed | Unit: test_ingestion_engine.py (Checkov FAILED → scan_findings with IaC fields) |
| AC-018 | S-022 | Passed | Unit: test_ingestion_engine.py (_fingerprint Checkov sha256(check_id:file:resource)) |
| AC-019 | S-023 | Passed | Unit: test_edge_service.py (checkov_native edge when bc_check_id present) |
| AC-020 | S-024 | Passed | Unit: test_edge_service.py (llm_reg_mapper plans do not write edges; bc_check_id absent → no checkov_native edge) |
| AC-021 | S-025 | Passed | Unit: test_ingestion_engine.py (_route PASSED → detected_controls) |
| AC-022 | S-026 | Passed | Unit: test_ingestion_engine.py (_route SKIPPED → audit_log; not written to scan_findings) |
| AC-023 | S-027 | Passed | Unit: test_ingestion_engine.py (_route checkov sca_package/sca_image → component_has_vuln path) |

**Summary:** 23/23 acceptance criteria mapped and `Passed`. All executable criteria covered by unit tests. Integration stubs (9 tests) require live ArangoDB and are gated separately.

---

## Scenario Index

### S-001 — ingest_scan creates scan_run and returns completed status

- **AC IDs:** AC-001, AC-002
- **Requirement IDs:** UC-001
- **Use Case ID:** UC-001
- **Source Type:** Requirement
- **Test Level:** API (unit mock)
- **Expected Outcome:** `EvidenceIngestionService.ingest_scan()` returns result with `status=completed`, `scan_run_id` set; `run_repo.complete_run` called once
- **Execution:** `tests/unit/ingestion/test_service.py::TestEvidenceIngestionService::test_ingest_scan_returns_completed_result`
- **Result:** Passed

### S-002 — fail_run called on pipeline exception

- **AC IDs:** AC-002
- **Requirement IDs:** UC-001
- **Use Case ID:** UC-001
- **Source Type:** Design-Risk
- **Test Level:** API (unit mock)
- **Expected Outcome:** On engine exception, `run_repo.fail_run` called with error message; exception re-raised
- **Execution:** `tests/unit/ingestion/test_service.py::test_fail_run_called_on_engine_exception`
- **Result:** Passed

### S-003 — Grype SCA finding creates component_has_vuln edge plan

- **AC IDs:** AC-004
- **Requirement IDs:** UC-006
- **Use Case ID:** UC-006
- **Source Type:** Requirement
- **Test Level:** API (unit mock)
- **Expected Outcome:** `EdgeService.create_component_vuln_edges` called when SCA findings present
- **Execution:** `tests/unit/ingestion/test_edge_service.py`
- **Result:** Passed

### S-004 — POST /v1/scan/ingest returns scan_run_id (API contract)

- **AC IDs:** AC-001, AC-012
- **Requirement IDs:** UC-001, UC-002
- **Use Case ID:** UC-001
- **Source Type:** Requirement
- **Test Level:** API (TestClient + service mock)
- **Expected Outcome:** POST /v1/scan/ingest returns 200 with `data.scan_run_id` populated
- **Execution:** `tests/integration/test_phase0_acceptance_criteria.py::TestUC004_ScanIngestion::test_AC012_to_AC016_integration_tests`
- **Result:** Passed

### S-005 — POST /v1/scan/{run_id}/vex returns 501 Not Implemented

- **AC IDs:** AC-016 (no regression)
- **Requirement IDs:** N/A (stub)
- **Use Case ID:** N/A
- **Source Type:** Design-Risk
- **Test Level:** API (TestClient)
- **Expected Outcome:** 501 status code
- **Execution:** `tests/integration/test_scan_vex_cpe_endpoints.py::TestVEXGenerationAPI`
- **Result:** Passed

### S-006 — Same SARIF finding ingested twice produces single scan_findings doc

- **AC IDs:** AC-003
- **Requirement IDs:** UC-014
- **Use Case ID:** UC-014
- **Source Type:** Requirement
- **Test Level:** API (unit mock)
- **Expected Outcome:** `import_bulk(on_duplicate="update")` called — idempotent upsert
- **Execution:** `tests/unit/ingestion/test_repositories.py::TestEvidenceFindingRepository`
- **Result:** Passed

### S-007 — component_has_vuln edge key is deterministic

- **AC IDs:** AC-004, AC-015
- **Requirement IDs:** UC-006
- **Use Case ID:** UC-006
- **Source Type:** Requirement
- **Test Level:** API (unit mock)
- **Expected Outcome:** Edge `_key` same for identical `_from`/`_to` inputs; second call does not create new doc
- **Execution:** `tests/unit/ingestion/test_edge_service.py::test_edge_key_determinism`
- **Result:** Passed

### S-008 — SBOM component upsert by purl key

- **AC IDs:** AC-005
- **Requirement IDs:** UC-004
- **Use Case ID:** UC-004
- **Source Type:** Requirement
- **Test Level:** API (unit mock)
- **Expected Outcome:** `EvidenceComponentRepository.upsert_batch` uses `import_bulk(on_duplicate="update")`
- **Execution:** `tests/unit/ingestion/test_repositories.py::TestEvidenceComponentRepository`
- **Result:** Passed

### S-009 — project_uses_component edges created when project_id provided

- **AC IDs:** AC-006
- **Requirement IDs:** UC-005
- **Use Case ID:** UC-005
- **Source Type:** Requirement
- **Test Level:** API (unit mock)
- **Expected Outcome:** `EdgeService.create_project_component_edges` writes edges to `project_uses_component` collection
- **Execution:** `tests/unit/ingestion/test_edge_service.py::test_project_uses_component_edges`
- **Result:** Passed

### S-010 — finding_maps_to_weakness edge created for CWE IDs

- **AC IDs:** AC-007
- **Requirement IDs:** UC-007
- **Use Case ID:** UC-007
- **Source Type:** Requirement
- **Test Level:** API (unit mock)
- **Expected Outcome:** When finding has `cwe_ids`, `EdgeService.create_finding_weakness_edges` writes to `finding_maps_to_weakness`
- **Execution:** `tests/unit/ingestion/test_edge_service.py::test_finding_maps_to_weakness`
- **Result:** Passed

### S-011 — finding_triggers_req: checkov_native when bc_check_id present; llm_reg_mapper skipped

- **AC IDs:** AC-008, AC-019, AC-020
- **Requirement IDs:** UC-008, UC-018
- **Use Case ID:** UC-018
- **Source Type:** Requirement
- **Test Level:** API (unit mock)
- **Expected Outcome:** `bc_check_id` present → `source="checkov_native"` edge written; `source="llm_reg_mapper"` → no DB write
- **Execution:** `tests/unit/ingestion/test_edge_service.py::test_checkov_native_req_edge` and `test_llm_reg_mapper_plans_do_not_write_edges`
- **Result:** Passed

### S-012 — finding_in_component edge created for SCA findings with purl

- **AC IDs:** AC-009
- **Requirement IDs:** UC-009
- **Use Case ID:** UC-009
- **Source Type:** Requirement
- **Test Level:** API (unit mock)
- **Expected Outcome:** SCA findings with purl produce `finding_in_component` edges
- **Execution:** `tests/unit/ingestion/test_edge_service.py::test_finding_in_component`
- **Result:** Passed

### S-013 — detected_control_maps_to and control_in_component stubs exist

- **AC IDs:** AC-010
- **Requirement IDs:** UC-010, UC-011
- **Use Case ID:** UC-011
- **Source Type:** Design-Risk
- **Test Level:** API (unit mock)
- **Expected Outcome:** Methods exist without panicking; write deferred per design (stub state)
- **Execution:** `tests/unit/ingestion/test_edge_service.py::test_detected_control_edges_stub`
- **Result:** Passed

### S-014 — _assemble_evidence_package called by ingest_scan

- **AC IDs:** AC-011
- **Requirement IDs:** UC-012, UC-013
- **Use Case ID:** UC-012
- **Source Type:** Requirement
- **Test Level:** API (unit mock)
- **Expected Outcome:** `EvidenceIngestionService.ingest_scan` calls `_assemble_evidence_package` after edge creation
- **Execution:** `tests/unit/ingestion/test_service.py::test_assemble_evidence_package_called`
- **Result:** Passed

### S-015 — All evidence documents carry tenant_id

- **AC IDs:** AC-012
- **Requirement IDs:** UC-001, UC-002, UC-003
- **Use Case ID:** UC-001
- **Source Type:** Requirement
- **Test Level:** API (unit mock)
- **Expected Outcome:** `ScanRun`, `V22Finding`, `DetectedControl` documents all have `tenant_id` field
- **Execution:** `tests/unit/ingestion/test_repositories.py` (create/complete/fail pass tenant_id)
- **Result:** Passed

### S-016 — Ingestion normalisation: severity mapping, CWE extraction, CVE validation

- **AC IDs:** AC-013
- **Requirement IDs:** UC-016
- **Use Case ID:** UC-016
- **Source Type:** Requirement
- **Test Level:** API (unit mock)
- **Expected Outcome:** Semgrep `ERROR`→`critical`; CWE IDs extracted from rule metadata; invalid CVE format rejected by `_validate`
- **Execution:** `tests/unit/ingestion/test_ingestion_engine.py` (9 normalisation steps)
- **Result:** Passed

### S-017 — BackfillAdapter applies FIELD_MAP correctly

- **AC IDs:** AC-014
- **Requirement IDs:** UC-015
- **Use Case ID:** UC-015
- **Source Type:** Requirement
- **Test Level:** API (unit mock)
- **Expected Outcome:** `customer_id`→`tenant_id`; `tool_name`→`tools_invoked=[tool_name]`; `findings_count`→`finding_counts.total`; `tenant_id`/`customer_id` removed from component docs
- **Execution:** `tests/unit/ingestion/test_backfill.py`
- **Result:** Passed

### S-018 — Edge keys are deterministic across re-ingestion

- **AC IDs:** AC-015
- **Requirement IDs:** UC-014
- **Use Case ID:** UC-014
- **Source Type:** Requirement
- **Test Level:** API (unit mock)
- **Expected Outcome:** `generate_edge_key(_from, _to)` produces same key for same inputs; `import_bulk(on_duplicate="update")` prevents duplicates
- **Execution:** `tests/unit/ingestion/test_edge_service.py::test_edge_key_determinism`
- **Result:** Passed

### S-019 — No regression: 880 passing tests after v2.2 changes

- **AC IDs:** AC-016
- **Requirement IDs:** All
- **Use Case ID:** All
- **Source Type:** Design-Risk
- **Test Level:** API (full suite)
- **Expected Outcome:** `uv run pytest tests/ --ignore=tests/integration/ingestion` → 880 passed, 1 skipped
- **Execution:** Full test suite run
- **Result:** Passed

### S-020 — ScanIngestResponse returns scan_run_id (renamed from scan_session_id)

- **AC IDs:** AC-016
- **Requirement IDs:** UC-001
- **Use Case ID:** UC-001
- **Source Type:** Requirement
- **Test Level:** API (contract)
- **Expected Outcome:** `ScanIngestResponse.scan_run_id` field exists; contract test + fixture updated
- **Execution:** `tests/contract/test_api_contract.py::test_scan_ingest_response_structure`
- **Result:** Passed

### S-021 — Checkov FAILED findings ingested with IaC fields

- **AC IDs:** AC-017
- **Requirement IDs:** UC-017
- **Use Case ID:** UC-017
- **Source Type:** Requirement
- **Test Level:** API (unit mock)
- **Expected Outcome:** Checkov FAILED finding produces doc with `check_id`, `bc_check_id`, `iac_framework`, `resource_address`, `check_result`, `check_name`, `check_class`, `guideline`
- **Execution:** `tests/unit/ingestion/test_ingestion_engine.py::test_checkov_failed_iac_fields`
- **Result:** Passed

### S-022 — Checkov fingerprint scoped to check_id:file:resource

- **AC IDs:** AC-018
- **Requirement IDs:** UC-017
- **Use Case ID:** UC-017
- **Source Type:** Requirement
- **Test Level:** API (unit mock)
- **Expected Outcome:** Same Checkov FAILED check on same file+resource produces identical fingerprint; second ingestion updates not duplicates
- **Execution:** `tests/unit/ingestion/test_ingestion_engine.py::test_checkov_fingerprint_deterministic`
- **Result:** Passed

### S-023 — checkov_native finding_triggers_req edge created

- **AC IDs:** AC-019
- **Requirement IDs:** UC-018
- **Use Case ID:** UC-018
- **Source Type:** Requirement
- **Test Level:** API (unit mock)
- **Expected Outcome:** `bc_check_id` present → `finding_triggers_req` edge with `source="checkov_native"`
- **Execution:** `tests/unit/ingestion/test_edge_service.py::test_checkov_native_req_edge`
- **Result:** Passed

### S-024 — llm_reg_mapper edge plans do not write to DB

- **AC IDs:** AC-020
- **Requirement IDs:** UC-018
- **Use Case ID:** UC-018
- **Source Type:** Requirement
- **Test Level:** API (unit mock)
- **Expected Outcome:** `source="llm_reg_mapper"` plans produce no `import_bulk` or AQL calls
- **Execution:** `tests/unit/ingestion/test_edge_service.py::test_llm_reg_mapper_plans_do_not_write_edges`
- **Result:** Passed

### S-025 — Checkov PASSED routed to detected_controls

- **AC IDs:** AC-021
- **Requirement IDs:** UC-019
- **Use Case ID:** UC-019
- **Source Type:** Requirement
- **Test Level:** API (unit mock)
- **Expected Outcome:** `_route` step sends PASSED findings to `detected_controls` path, not `scan_findings`
- **Execution:** `tests/unit/ingestion/test_ingestion_engine.py::test_checkov_passed_routes_to_detected_controls`
- **Result:** Passed

### S-026 — Checkov SKIPPED recorded in audit_log, not scan_findings

- **AC IDs:** AC-022
- **Requirement IDs:** UC-017
- **Use Case ID:** UC-017
- **Source Type:** Requirement
- **Test Level:** API (unit mock)
- **Expected Outcome:** `_route` step sends SKIPPED findings to `audit_log` path; `scan_findings` count not incremented
- **Execution:** `tests/unit/ingestion/test_ingestion_engine.py::test_checkov_skipped_routes_to_audit_log`
- **Result:** Passed

### S-027 — Checkov sca_package/sca_image findings routed to component_has_vuln

- **AC IDs:** AC-023
- **Requirement IDs:** UC-017
- **Use Case ID:** UC-017
- **Source Type:** Requirement
- **Test Level:** API (unit mock)
- **Expected Outcome:** Checkov findings with `iac_framework in [sca_package, sca_image]` route to `component_has_vuln` path
- **Execution:** `tests/unit/ingestion/test_ingestion_engine.py::test_checkov_sca_rerouted_to_component_has_vuln`
- **Result:** Passed

---

## Re-Entry Declarations

| Date | Trigger Stage | Classification | Return Path | Trigger | Resolution |
| --- | --- | --- | --- | --- | --- |
| 2026-03-18 | 7 | Local Fix | 6 → 7 | 16 integration tests broken by T-011/T-012/T-013/T-DEL-001: ScanSession/ScanFinding removed, scan_session_id→scan_run_id, VEX/CPE→501, EvidenceIngestionService patch path wrong | Fixed test_phase0, test_phase1, test_scan_ingestion_api, test_scan_vex_cpe_endpoints; 880 passed 1 skipped |

---

## Infeasible Scenarios

| Scenario | Reason | Compensating Evidence | Residual Risk |
| --- | --- | --- | --- |
| S-001 through S-027 live DB execution | ArangoDB integration tests require live reference DB with v2.2 schema; not available in CI | 9 `@pytest.mark.integration` stubs in `tests/integration/ingestion/` cover identical assertions against live DB when available | Low — unit tests cover same logic with mocks; live DB stubs will catch DB-level failures when run manually |
