# Implementation Plan: Evidence Data Ingestion Pipeline

## Scope Classification

- Classification: `Large`
- Reasoning: 12–18 files touched, multi-layer (models + engine + repositories + edge service + service + API endpoints), clean replacement of existing service + repositories
- Workflow Depth: `Large` → proposed design doc → call stacks → review → this plan → progress tracking → API/E2E → code review → docs sync

## Upstream Artifacts (Required)

- Workflow state: `tickets/in-progress/evidence-ingestion-pipeline/workflow-state.md`
- Investigation notes: `tickets/in-progress/evidence-ingestion-pipeline/investigation-notes.md`
- Requirements: `tickets/in-progress/evidence-ingestion-pipeline/requirements.md` (status `Refined`)
- Runtime call stacks: `tickets/in-progress/evidence-ingestion-pipeline/future-state-runtime-call-stack.md` (v3)
- Runtime review: `tickets/in-progress/evidence-ingestion-pipeline/future-state-runtime-call-stack-review.md`
- Proposed design: `tickets/in-progress/evidence-ingestion-pipeline/proposed-design.md` (v3)

## Plan Maturity

- Current Status: `Ready For Implementation`
- Notes: Stage 5 Go Confirmed (Rounds 7 + 8 clean, T-007). All upstream artifacts current.

## Preconditions (Must Be True Before Finalizing This Plan)

- `requirements.md` is at least `Design-ready`: Yes — `Refined` with UC-001–UC-019 + AC-001–AC-023
- Acceptance criteria use stable IDs (`AC-*`) with measurable expected outcomes: Yes
- `workflow-state.md` is current and Stage 5 review-gate evidence is recorded: Yes — T-007
- Runtime call stack review artifact exists and is current: Yes — v3
- All in-scope use cases reviewed: Yes — UC-001 to UC-019 + DR-001–DR-003
- No unresolved blocking findings: Yes
- Runtime review has `Go Confirmed` with two consecutive clean deep-review rounds: Yes (Rounds 7 + 8)
- Missing-use-case discovery sweeps completed for the final two clean rounds: Yes
- No newly discovered use cases in the final two clean rounds: Yes

## Runtime Call Stack Review Gate Summary (Required)

| Round | Review Result | Findings Requiring Persisted Updates | New Use Cases Discovered | Persisted Updates Completed | Classification | Required Re-Entry Path | Round State | Clean Streak After Round |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Fail | Yes | No | Yes | Design Impact | Stage 3→4→5 | Reset | 0 |
| 2 | Pass | No | No | N/A | N/A | N/A | Candidate Go | 1 |
| 3 | Pass (base scope Go Confirmed) | No | No | N/A | N/A | N/A | Go Confirmed | 2 |
| 4 | Pass (Checkov re-entry applied) | No | No | Yes | Requirement Gap | Stage 2→3→4→5 | Candidate Go | 1 |
| 5 | Pass (full scope Go Confirmed) | No | No | N/A | N/A | N/A | Go Confirmed | 2 |
| 6 | Re-entry (Design Impact: adapter registry) | Yes | No | Yes | Design Impact | Stage 3→4→5 | Reset | 0 |
| 7 | Pass | No | No | N/A | N/A | N/A | Candidate Go | 1 |
| 8 | Pass | No | No | N/A | N/A | N/A | Go Confirmed | 2 |

## Go / No-Go Decision

- Decision: `Go`
- Evidence:
  - Final review round: Round 8
  - Clean streak at final round: 2
  - Final review gate line: "Gate: Go Confirmed — Implementation can start (full scope: base pipeline + Checkov + adapter registry)."

---

## Principles

- Bottom-up: implement dependencies before dependents
- Test-driven: unit tests alongside each module; integration tests at service layer
- Mandatory modernization: no backward-compat shims; remove old service/repos in same ticket
- One file at a time default; limited parallel work allowed for __init__ and package setup

---

## Dependency And Sequencing Map

| Order | Task ID | File/Module | Depends On | Why This Order |
| --- | --- | --- | --- | --- |
| 1 | T-001 | `src/complira_graph/models/evidence.py` | pydantic (external) | No internal deps — foundational data models |
| 2 | T-002 | `src/complira_graph/ingestion/__init__.py` | — | Package init (empty to start, re-export public API at end) |
| 3 | T-003 | `src/complira_graph/ingestion/adapter_registry.py` | No internal deps | Pure config TypedDict; validates required keys at import |
| 4 | T-004 | `src/complira_graph/ingestion/ingestion_engine.py` | T-003 (adapter_registry), T-001 (models), `utils/keys.py` | Engine reads adapter config and produces documents |
| 5 | T-005 | `src/complira_graph/ingestion/repositories.py` | T-001 (models), `api/core/database.py` | DB writes depend on models |
| 6 | T-006 | `src/complira_graph/ingestion/edge_service.py` | `utils/keys.py`, `api/core/database.py` | Edge creation depends on keys utility |
| 7 | T-007 | `src/complira_graph/ingestion/service.py` | T-004, T-005, T-006, `api/parsers/`, T-001 | Orchestration — all dependencies must exist first |
| 8 | T-008 | `src/complira_graph/ingestion/backfill.py` | T-005, `api/core/database.py`, schema constants | Migration path — separate from runtime |
| 9 | T-009 | Unit tests (`tests/unit/ingestion/`) | T-001–T-006 | Verify each module in isolation |
| 10 | T-010 | Integration tests stubs (`tests/integration/ingestion/`) | T-007 | Cross-module verification |
| 11 | T-011 | `src/api/v1/endpoints/scan.py` (modify) | T-007 (EvidenceIngestionService must exist) | Swap service call + update response field |
| 12 | T-012 | `src/api/models/responses/scan.py` (modify) | — | Add `scan_run_id`, keep `scan_session_id` until endpoint is updated |
| 13 | T-013 | `src/complira_graph/models/scan.py` (modify) | T-011 done (no more imports of ScanSession/ScanFinding) | Remove models only after endpoint updated |
| 14 | T-DEL-001 | `src/api/services/scan.py` (remove) | T-011 done | Remove only after endpoint no longer imports it |
| 15 | T-DEL-002 | `src/api/repositories/scan.py` (remove) | T-DEL-001 done | Remove only after service is gone |
| 16 | T-DEL-003 | `src/api/repositories/component.py` (remove) | T-DEL-001 done | Remove only after service is gone |

---

## Requirement And Design Traceability

| Requirement | AC ID(s) | Design Section | Use Case | Planned Task ID(s) | Stage 6 Verification | Stage 7 Scenario ID(s) |
| --- | --- | --- | --- | --- | --- | --- |
| R-001 | AC-001, AC-002 | ScanRun lifecycle | UC-001 | T-005, T-007 | unit: EvidenceRunRepository; integration: service create+complete | S-001, S-002 |
| R-002 | AC-003, AC-013 | SAST finding ingestion | UC-002 | T-003, T-004, T-005 | unit: IngestionEngine semgrep; integration: SARIF→scan_findings | S-003, S-013 |
| R-003 | AC-004 | SCA finding ingestion | UC-003, UC-006 | T-004, T-005, T-006 | unit: Grype adapter + CVE edge | S-004 |
| R-004 | AC-005, AC-006 | SBOM component upsert | UC-004, UC-005 | T-005, T-006 | unit: purl dedup; integration: CycloneDX→components | S-005, S-006 |
| R-005 | AC-007 | finding_maps_to_weakness edge | UC-007 | T-006 | unit: edge key generation | S-007 |
| R-006 | AC-008 | finding_triggers_req AQL | UC-008 | T-006 | unit: AQL skip on empty result | S-008 |
| R-007 | AC-009 | finding_in_component edge | UC-009 | T-006 | unit: edge creation | S-009 |
| R-008 | AC-010 | detected_controls stub | UC-010, UC-011 | T-005, T-006 | unit: stub creates doc | S-010 |
| R-009 | AC-011 | Evidence package | UC-012, UC-013 | T-005, T-006 | unit: evidence package + edges | S-011 |
| R-010 | AC-012 | Multi-tenant isolation | DR-001 | T-005, T-007 | unit: wrong tenant returns empty | S-012 |
| R-011 | AC-015 | Idempotent re-ingestion | UC-014 | T-004, T-005, T-006 | unit: on_duplicate=update + generate_edge_key | S-015 |
| R-012 | AC-014 | Backfill | UC-015 | T-008 | unit: FIELD_MAP rename | S-014 |
| R-013 | AC-017, AC-018, AC-023 | Checkov IaC ingestion | UC-017 | T-003, T-004 | unit: checkov adapter routing | S-017, S-018, S-023 |
| R-014 | AC-019, AC-020 | checkov_native req edge | UC-018 | T-003, T-004, T-006 | unit: bc_check_id present/absent | S-019, S-020 |
| R-015 | AC-021, AC-022 | Checkov PASSED→detected_controls | UC-019 | T-003, T-004, T-005 | unit: PASSED routing | S-021, S-022 |

---

## Acceptance Criteria To Stage 7 Mapping (Mandatory)

| AC ID | Requirement ID | Expected Outcome | Stage 7 Scenario ID(s) | Test Level | Initial Status |
| --- | --- | --- | --- | --- | --- |
| AC-001 | R-001 | scan_runs doc with status=running created before findings written | S-001 | API | Planned |
| AC-002 | R-001 | scan_runs doc updated with counts/status=completed | S-002 | API | Planned |
| AC-003 | R-002 | Double-ingest same SARIF finding → single scan_findings doc | S-003 | API | Planned |
| AC-004 | R-003 | SCA ingest → scan_findings + component_has_vuln edge in reference DB | S-004 | API | Planned |
| AC-005 | R-004 | Double CycloneDX ingest same purl → single components doc | S-005 | API | Planned |
| AC-006 | R-004 | SBOM ingest → project_uses_component edges in reference DB | S-006 | API | Planned |
| AC-007 | R-005 | SAST finding with CWE → finding_maps_to_weakness edge exists | S-007 | API | Planned |
| AC-008 | R-006 | Finding with CWE → finding_triggers_req edge if mapping found | S-008 | API | Planned |
| AC-009 | R-007 | Finding with purl → finding_in_component edge exists | S-009 | API | Planned |
| AC-010 | R-008 | detected_controls doc + edges (stub) | S-010 | API | Planned |
| AC-011 | R-009 | evidence_packages doc + evidence_links_finding + evidence_for_project | S-011 | API | Planned |
| AC-012 | R-010 | All evidence docs have non-null tenant_id; wrong tenant returns empty | S-012 | API | Planned |
| AC-013 | R-002 | Semgrep ERROR→high, CWE extracted, CVE validated | S-013 | API | Planned |
| AC-014 | R-012 | Backfill scan_session → scan_run with customer_id→tenant_id | S-014 | API | Planned |
| AC-015 | R-011 | Re-ingest same data → deterministic edge _key, no duplicates | S-015 | API | Planned |
| AC-016 | R-002 | Existing 705 tests still pass | S-016 | E2E | Planned |
| AC-017 | R-013 | Checkov FAILED → scan_findings with IaC-specific fields | S-017 | API | Planned |
| AC-018 | R-013 | Double-ingest same Checkov check → single doc (resource-scoped fingerprint) | S-018 | API | Planned |
| AC-019 | R-014 | Checkov FAILED with bc_check_id → finding_triggers_req source=checkov_native | S-019 | API | Planned |
| AC-020 | R-014 | Checkov FAILED without bc_check_id → llm_reg_mapper source | S-020 | API | Planned |
| AC-021 | R-015 | Checkov PASSED → detected_controls doc (not scan_findings) | S-021 | API | Planned |
| AC-022 | R-015 | Checkov SKIPPED → audit_log on scan_run (not scan_findings) | S-022 | API | Planned |
| AC-023 | R-013 | Checkov sca_package → component_has_vuln path; secrets → secrets path | S-023 | API | Planned |

---

## Design Delta Traceability (Required For `Medium/Large`)

| Change ID | Change Type | Planned Task ID(s) | Includes Remove/Rename Work | Verification |
| --- | --- | --- | --- | --- |
| C-001 | Add | T-001 | No | unit: model instantiation, field validation |
| C-002 | Add | T-003 | No | unit: registry loads, register_adapter validates |
| C-003 | Add | T-005 | No | unit + integration: upsert_batch idempotency |
| C-004 | Add | T-006 | No | unit: edge key generation, AQL skip |
| C-005 | Add | T-007 | No | integration: full pipeline |
| C-006 | Add | T-008 | No | unit: FIELD_MAP transformation |
| C-007 | Add | T-002 | No | import smoke test |
| C-008 | Remove | T-DEL-001 | Yes | grep -r ScanIngestionService src/ returns empty |
| C-009 | Remove | T-DEL-002 | Yes | grep -r ScanSessionRepository src/ returns empty |
| C-010 | Remove | T-DEL-003 | Yes | grep -r ComponentRepository src/ returns empty (old) |
| C-011 | Modify | T-011 | No | unit: endpoint uses EvidenceIngestionService, returns scan_run_id |
| C-012 | Modify | T-013 | Yes | grep -r 'class ScanSession' → only in migration docs |
| C-013 | Modify | T-012 | No | unit: ScanIngestResponse has scan_run_id field |
| C-016 | Add | T-004 | No | unit: IngestionEngine all 9 steps |
| C-017 | Add (tests) | T-009, T-010 | No | tests pass |

---

## Decommission / Rename Execution Tasks

| Task ID | Item | Action | Cleanup Steps | Risk Notes |
| --- | --- | --- | --- | --- |
| T-DEL-001 | `src/api/services/scan.py` | Remove | 1. Verify T-011 done (endpoint no longer imports). 2. Delete file. 3. Check `grep -r ScanIngestionService src/` | 1048 lines; ensure no test fixtures import it |
| T-DEL-002 | `src/api/repositories/scan.py` | Remove | 1. Verify T-DEL-001 done. 2. Check `grep -r ScanSessionRepository src/`. 3. Delete. | Check for test fixtures |
| T-DEL-003 | `src/api/repositories/component.py` | Remove | 1. Verify T-DEL-001 done. 2. Check `grep -r ComponentRepository src/`. 3. Delete. | Check for test fixtures |
| T-DEL-004 | `ScanSession`/`ScanFinding` in `scan.py` | Remove from file | 1. Verify no imports. 2. Remove classes from `complira_graph/models/scan.py`. Keep file if other models remain. | Scan for imports first |

---

## Step-By-Step Plan

1. **T-001** Create `src/complira_graph/models/evidence.py` — `ScanRun`, `V22Finding`, `V22Component`, `DetectedControl`, `EvidencePackage` Pydantic models
2. **T-002** Create `src/complira_graph/ingestion/__init__.py` — empty package init
3. **T-003** Create `src/complira_graph/ingestion/adapter_registry.py` — `ToolAdapter` TypedDict, `ADAPTER_REGISTRY` (semgrep, checkov, gitleaks, grype, zap, trufflehog, sarif), `register_adapter()`; includes ReqMappingSource with `"iam_reg_mapper"` reserved
4. **T-004** Create `src/complira_graph/ingestion/ingestion_engine.py` — `IngestionEngine` with 9 steps; dynamic bc_check_id→req_mapping_source override
5. **T-005** Create `src/complira_graph/ingestion/repositories.py` — `EvidenceRunRepository`, `EvidenceFindingRepository`, `EvidenceComponentRepository`; includes `append_audit_log()`
6. **T-006** Create `src/complira_graph/ingestion/edge_service.py` — `EvidenceEdgeService.create_edges()` for all 9 edge collections; `_resolve_checkov_req_edge()`
7. **T-007** Create `src/complira_graph/ingestion/service.py` — `EvidenceIngestionService.ingest_scan()` orchestration
8. **T-008** Create `src/complira_graph/ingestion/backfill.py` — `BackfillAdapter.run(customer_ids)`
9. **T-009** Create `tests/unit/ingestion/` — unit tests for models, adapter registry, engine, repositories, edge service
10. **T-010** Create `tests/integration/ingestion/` — integration test stubs (DB required; mark with `pytest.mark.integration`)
11. **T-011** Modify `src/api/v1/endpoints/scan.py` — swap `ScanIngestionService` → `EvidenceIngestionService`; return `scan_run_id`
12. **T-012** Modify `src/api/models/responses/scan.py` — replace `scan_session_id` with `scan_run_id` in `ScanIngestResponse`
13. **T-013** Remove `ScanSession`/`ScanFinding` from `src/complira_graph/models/scan.py`
14. **T-DEL-001** Delete `src/api/services/scan.py` (after verifying no remaining imports)
15. **T-DEL-002** Delete `src/api/repositories/scan.py` (after verifying no remaining imports)
16. **T-DEL-003** Delete `src/api/repositories/component.py` (after verifying no remaining imports)
17. **Verify** Run full test suite; confirm existing 705 tests pass

---

## Per-File Definition Of Done

| File | Implementation Done Criteria | Unit Test Criteria | Integration Test Criteria | Notes |
| --- | --- | --- | --- | --- |
| `models/evidence.py` | All 5 models defined with correct fields + validators | Model instantiation + field validation + fingerprint key | N/A | Checkov IaC fields Optional |
| `ingestion/__init__.py` | Package importable | Import smoke test | N/A | |
| `adapter_registry.py` | ADAPTER_REGISTRY has 7+ tools; register_adapter validates | Registry loads at import; register_adapter accepts + rejects correctly | N/A | |
| `ingestion_engine.py` | All 9 steps implemented; bc_check_id dynamic override | Per-step unit tests; semgrep + checkov full pipeline | N/A | |
| `repositories.py` | EvidenceRunRepository (create/complete/fail/audit_log); EvidenceFindingRepository (upsert_batch); EvidenceComponentRepository | Idempotency: upsert_batch with duplicate _key | import_bulk idempotency with real ArangoDB | |
| `edge_service.py` | All 9 edge collections; checkov_native resolution; AQL graceful skip | Edge key determinism; CWE missing→skip; bc_check_id absent→llm_reg_mapper | AQL traversal integration | |
| `service.py` | ingest_scan() orchestration: run lifecycle + findings + components + edges | Mock repos/edge_service; fail path marks run failed | Full pipeline integration | |
| `backfill.py` | BackfillAdapter.run() with FIELD_MAP + LEGACY_COLLECTION_MAP | FIELD_MAP transformation unit test | N/A (manual run) | |
| `api/v1/endpoints/scan.py` | Uses EvidenceIngestionService; returns scan_run_id | Endpoint unit test: returns scan_run_id | API test via Stage 7 | |
| `models/responses/scan.py` | ScanIngestResponse has scan_run_id (not scan_session_id) | Schema test | N/A | |
| `models/scan.py` | ScanSession/ScanFinding removed | grep returns empty | N/A | |
| `api/services/scan.py` | Deleted | grep -r ScanIngestionService src/ empty | N/A | |
| `api/repositories/scan.py` | Deleted | grep returns empty | N/A | |
| `api/repositories/component.py` | Deleted | grep returns empty | N/A | |

---

## Code Review Gate Plan (Stage 8)

- Gate artifact path: `tickets/in-progress/evidence-ingestion-pipeline/code-review.md`
- Scope: all new files in `complira_graph/ingestion/`, `complira_graph/models/evidence.py`, modified endpoint + response model + scan.py models, deleted files, unit tests
- Line-count commands:
  - effective non-empty: `rg -n "\S" <file> | wc -l`
  - changed-line delta: `git diff --numstat codex/evidence-ingestion-pipeline...HEAD -- <file>`
- `501-700` line files: mandatory SoC split assessment with itemized split candidates
- `>700` line files with new functionality: default Design Impact classification; exception requires rationale
- Per-file diff delta gate: if `>220` changed lines in single file, record design-impact assessment

| File | Est. Line Count | Adds/Expands Functionality | SoC Risk | Required Action |
| --- | --- | --- | --- | --- |
| `adapter_registry.py` | ~300 | Yes | Low | Normal review |
| `ingestion_engine.py` | ~200 | Yes | Low | Normal review |
| `repositories.py` | ~200 | Yes | Low | Normal review |
| `edge_service.py` | ~250 | Yes | Medium | Normal review; watch for AQL size |
| `service.py` | ~100 | Yes | Low | Normal review |
| `models/evidence.py` | ~150 | Yes | Low | Normal review |

---

## Test Strategy

- Unit tests: test each module in isolation with mocked dependencies; focus on normalisation logic (IngestionEngine steps), adapter routing (FAILED/PASSED/SKIPPED), edge key determinism, fingerprint generation
- Integration tests: use real ArangoDB reference DB (local or CI); verify on_duplicate=update idempotency; verify wrong-tenant isolation
- Stage 6 boundary: file/module/service-level verification only (unit + integration for document writes and edge creation)
- Stage 7 handoff notes:
  - expected acceptance criteria count: 23 (AC-001 to AC-023)
  - critical flows: scan_run lifecycle, fingerprint dedup, Checkov result routing, checkov_native edge, tenant isolation
  - expected scenario count: 23 (S-001 to S-023)
  - known environment constraints: integration tests require running ArangoDB reference DB; S-014 (backfill) requires populated customer DB test fixtures

---

## API/E2E Testing Scenario Catalog (Stage 7 Input)

| Scenario ID | Source Type | AC ID(s) | Req ID(s) | UC ID(s) | Test Level | Expected Outcome |
| --- | --- | --- | --- | --- | --- | --- |
| S-001 | Requirement | AC-001 | R-001 | UC-001 | API | scan_runs doc with status=running exists after POST |
| S-002 | Requirement | AC-002 | R-001 | UC-001 | API | scan_runs doc updated to status=completed with finding_counts |
| S-003 | Requirement | AC-003 | R-002 | UC-002, UC-014 | API | Double SARIF ingest → single scan_findings doc |
| S-004 | Requirement | AC-004 | R-003 | UC-003, UC-006 | API | Grype ingest → scan_findings + component_has_vuln edge |
| S-005 | Requirement | AC-005 | R-004 | UC-004, UC-014 | API | Double CycloneDX → single components doc |
| S-006 | Requirement | AC-006 | R-004 | UC-005 | API | SBOM → project_uses_component edges exist |
| S-007 | Requirement | AC-007 | R-005 | UC-007 | API | SAST finding with CWE → finding_maps_to_weakness edge |
| S-008 | Requirement | AC-008 | R-006 | UC-008 | API | Finding with CWE → finding_triggers_req edge if mapping found |
| S-009 | Requirement | AC-009 | R-007 | UC-009 | API | Finding with purl → finding_in_component edge |
| S-010 | Requirement | AC-010 | R-008 | UC-010, UC-011 | API | detected_controls doc + stub edges created |
| S-011 | Requirement | AC-011 | R-009 | UC-012, UC-013 | API | evidence_packages + evidence_links_finding + evidence_for_project |
| S-012 | Design-Risk | AC-012 | R-010 | DR-001 | API | Wrong tenant_id query returns empty result |
| S-013 | Requirement | AC-013 | R-002 | UC-016 | API | Semgrep ERROR→high, CWE extracted, CVE validated |
| S-014 | Requirement | AC-014 | R-012 | UC-015 | API | Backfill scan_session → scan_run with customer_id→tenant_id |
| S-015 | Design-Risk | AC-015 | R-011 | UC-014, DR-002 | API | Re-ingest → deterministic edge _key, no duplicates |
| S-016 | Requirement | AC-016 | R-002 | All | E2E | pytest test suite — all 705 existing tests pass |
| S-017 | Requirement | AC-017 | R-013 | UC-017 | API | Checkov FAILED → scan_findings with IaC fields |
| S-018 | Requirement | AC-018 | R-013 | UC-017, UC-014 | API | Double Checkov ingest → single doc (resource fingerprint) |
| S-019 | Requirement | AC-019 | R-014 | UC-018 | API | Checkov with bc_check_id → finding_triggers_req source=checkov_native |
| S-020 | Requirement | AC-020 | R-014 | UC-018, DR-003 | API | Checkov without bc_check_id → llm_reg_mapper source |
| S-021 | Requirement | AC-021 | R-015 | UC-019 | API | Checkov PASSED → detected_controls (not scan_findings) |
| S-022 | Requirement | AC-022 | R-015 | UC-019 | API | Checkov SKIPPED → audit_log field on scan_run |
| S-023 | Requirement | AC-023 | R-013 | UC-017 | API | sca_package → component_has_vuln path; secrets → scan_findings secrets path |

---

## API/E2E Testing Escalation Policy (Stage 7 Guardrail)

- Classification rules for failing Stage 7 scenarios: choose exactly one of `Local Fix`, `Design Impact`, `Requirement Gap`, `Unclear`
- `Local Fix`: no boundary changes, no new UCs/ACs, fix within Stage 6 scope → update artifacts, rerun Stage 6→7
- `Design Impact`: boundary drift, new architectural constraint → investigation checkpoint first (Stage 1→3→4→5→6→7)
- `Requirement Gap`: missing/ambiguous AC → update requirements first (Stage 2→3→4→5→6→7)
- `Unclear`: cross-cutting root cause → Stage 0→1→2→3→4→5→6→7

---

## Cross-Reference Exception Protocol

| File | Cross-Reference With | Why Unavoidable | Temporary Strategy | Unblock Condition | Follow-Up Status | Owner |
| --- | --- | --- | --- | --- | --- | --- |
| `edge_service.py` | `repositories.py` (EvidenceRunRepository.append_audit_log) | Checkov SKIPPED → audit_log requires run update | Import in service.py and pass audit entries as separate call | Both files completed in same session | Not Needed | — |

---

## Design Feedback Loop

| Smell/Issue | Evidence | Design Section | Action | Status |
| --- | --- | --- | --- | --- |
| INGESTION_NORMALISATION sync risk | adapter_registry.py encodes maps directly vs schema constants | Adapter Registry Pattern | Implementation note: adapters MAY import from INGESTION_NORMALISATION at init; no structural change needed | Pending |
| `ReqMappingSource` enum future extensibility | iam_reg_mapper is 5th deterministic path (future Layer 3) | adapter_registry.py | Reserve `"iam_reg_mapper"` in Literal type now | Pending |
