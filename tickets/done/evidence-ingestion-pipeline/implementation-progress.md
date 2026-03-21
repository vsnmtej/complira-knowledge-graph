# Implementation Progress: Evidence Data Ingestion Pipeline

## Status Summary

- Stage: `6` (Source Implementation + Unit/Integration)
- Code Edit Permission: `Unlocked`
- Overall Progress: `In Progress`
- Last Updated: 2026-03-18

## File Build State

| Task ID | File | Change Type | Build State | Unit Test State | Integration Test State | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| T-001 | `src/complira_graph/models/evidence.py` | Add | Completed | Not Started | N/A | ScanRun, V22Finding, V22Component, DetectedControl, EvidencePackage |
| T-002 | `src/complira_graph/ingestion/__init__.py` | Add | Completed | Not Started | N/A | Public re-exports |
| T-003 | `src/complira_graph/ingestion/adapter_registry.py` | Add | Completed | Not Started | N/A | 7 tools; iam_reg_mapper reserved; DFL-001 resolved |
| T-004 | `src/complira_graph/ingestion/ingestion_engine.py` | Add | Completed | Not Started | N/A | 9 steps; bc_check_id dynamic override; multi_root; @inject |
| T-005 | `src/complira_graph/ingestion/repositories.py` | Add | Completed | Not Started | Not Started | EvidenceRunRepository (create/complete/fail/append_audit_log), EvidenceFindingRepository, EvidenceComponentRepository, EvidenceDetectedControlRepository |
| T-006 | `src/complira_graph/ingestion/edge_service.py` | Add | Completed | Not Started | Not Started | All 9 edge collections; _resolve_checkov_req_edge; rule_engine CWE AQL; llm_reg_mapper defer; stubs for detected_control edges |
| T-007 | `src/complira_graph/ingestion/service.py` | Add | Completed | Not Started | Not Started | EvidenceIngestionService: ingest_scan (finding engine path), ingest_sbom (SBOM component path), _assemble_evidence_package, fail_run on exception |
| T-008 | `src/complira_graph/ingestion/backfill.py` | Add | Completed | Not Started | N/A | BackfillAdapter.run(customer_ids); _migrate_scan_sessions (customer_id→tenant_id, tool_name→tools_invoked); _migrate_components (global purl-keyed, tenant_id removed); apply_field_map static helper |
| T-009 | `tests/unit/ingestion/` | Add | Completed | Passed | N/A | 176 tests pass: adapter_registry, ingestion_engine, repositories, edge_service, service, backfill |
| T-010 | `tests/integration/ingestion/` | Add | Completed | N/A | Pending | Integration stubs: 9 tests marked @pytest.mark.integration covering ingest_scan, ingest_sbom, BackfillAdapter |
| T-011 | `src/api/v1/endpoints/scan.py` | Modify | Completed | N/A | N/A | Rewired POST /ingest → EvidenceIngestionService; GET endpoints query scan_runs directly; VEX/CPE stub 501 |
| T-012 | `src/api/models/responses/scan.py` | Modify | Completed | N/A | N/A | scan_session_id → scan_run_id in ScanIngestResponse; fixture + contract test updated |
| T-013 | `src/complira_graph/models/scan.py` | Modify (Remove models) | Completed | N/A | N/A | ScanSession/ScanFinding removed; models/__init__.py cleaned; stub comment retained for T-DEL-002 dependency |
| T-DEL-001 | `src/api/services/scan.py` | Remove | Completed | N/A | N/A | Deleted; api/core/dependencies.py get_scan_service updated to EvidenceIngestionService |
| T-DEL-002 | `src/api/repositories/scan.py` | Remove | Blocked | N/A | N/A | Blocked: enrichment.py + compaction.py still import ScanFindingRepository; out of current scope |
| T-DEL-003 | `src/api/repositories/component.py` | Remove | Blocked | N/A | N/A | Blocked: depends on T-DEL-002 |

## Blockers

None.

## Design Feedback Log

| ID | File | Observation | Action | Status |
| --- | --- | --- | --- | --- |
| DFL-001 | `adapter_registry.py` | Reserve `"iam_reg_mapper"` in ReqMappingSource Literal | Add to Literal at implementation time | Resolved — included in T-003 |

## Execution Log

| Entry | Task ID | File | Event | Detail |
| --- | --- | --- | --- | --- |
| 1 | — | — | Stage 6 kickoff | implementation-plan.md created; implementation-progress.md initialized |
| 2 | T-001 | `models/evidence.py` | Completed | ScanRun, V22Finding (incl. Checkov IaC fields), V22Component, DetectedControl, EvidencePackage |
| 3 | T-002 | `ingestion/__init__.py` | Completed | Package init with public re-exports |
| 4 | T-003 | `ingestion/adapter_registry.py` | Completed | ToolAdapter TypedDict, ADAPTER_REGISTRY (7 tools), register_adapter(), _validate_registry(); DFL-001 resolved |
| 5 | T-004 | `ingestion/ingestion_engine.py` | Completed | 9-step pipeline; multi_root; @inject; bc_check_id→llm_reg_mapper dynamic override |
| 6 | T-005 | `ingestion/repositories.py` | Completed | EvidenceRunRepository (create/complete/fail/append_audit_log AQL); EvidenceFindingRepository; EvidenceComponentRepository; EvidenceDetectedControlRepository; all upsert_batch use import_bulk(on_duplicate=update) | IngestionEngine with 9 steps; _parse (json_array/json_lines/json_object/sarif + multi_root + @inject); _route (result_state_field + wildcard); _fingerprint; _map_fields; _classify_severity; _extract_cwe (tool_direct/extracted/absent); _redact; _validate (CVE format); _plan_edges (checkov_native bc_check_id dynamic override → llm_reg_mapper) |
| 7 | T-009 | `tests/unit/ingestion/` | Completed | 176 unit tests; 6 test files; 404 total unit tests passing; test_adapter_registry + test_ingestion_engine (adapter config + pipeline + path traversal + all 9 steps); test_repositories (create/complete/fail/audit_log + all 4 repos); test_edge_service (9 edge methods + orchestrator); test_service (severity count + SBOM + fail path); test_backfill (FIELD_MAP + purl re-key + tenant_id removal) |
