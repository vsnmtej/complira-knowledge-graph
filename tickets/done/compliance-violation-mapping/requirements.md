# Requirements — compliance-violation-mapping

**Status:** `Design-ready`
**Last Updated:** 2026-03-22
**Scope Triage:** `Medium`

---

## Goal / Problem Statement

Wire up per-finding compliance violation edges by traversing the existing deterministic reference graph chain (CVE → CWE → CAPEC → ATT&CK → NIST 800-53 Control). The chain is already verified and used by `GET /v1/reference/controls/{cve_id}`. This ticket creates:
1. A new edge collection `finding_violates_control` linking scan findings to NIST 800-53 controls
2. A `ViolationMappingPipeline` stage (status: `mapped → violations_mapped`)
3. Read-only compliance query API (`GET /v1/compliance/violations`, `GET /v1/compliance/coverage`)

**Important context:** `violates_requirement` is an existing CVE→regulatory_requirement edge collection (5.27M edges). The new `finding_violates_control` edge collection is distinct — it links `scan_findings` documents to `nist_controls`/`oscal_controls` documents.

---

## In-Scope Use Cases

| ID | Type | Description |
| --- | --- | --- |
| UC-CV-001 | Requirement | Create `finding_violates_control` edges for a finding whose CVE maps to NIST 800-53 controls |
| UC-CV-002 | Requirement | Handle finding whose CVE has no control mapping — no edges written, no error |
| UC-CV-003 | Requirement | `ViolationMappingPipeline.run()` transitions scan run status `mapped → violations_mapped` |
| UC-CV-004 | Requirement | Query all violations for a scan run — `GET /v1/compliance/violations?scan_run_id=...` |
| UC-CV-005 | Requirement | Query per-framework coverage summary — `GET /v1/compliance/coverage?scan_run_id=...` |
| UC-CV-006 | Requirement | Pipeline handles scan run with zero findings gracefully |
| UC-CV-007 | Design-Risk | Pipeline re-run is idempotent — edges are upserted, not duplicated |
| UC-CV-008 | Design-Risk | Coordinator skip logic — `violations_mapped` status causes stage to be skipped on re-run |

---

## Requirements (Design-ready)

### REQ-CV-001 — `finding_violates_control` Edge Creation
For each scan finding with a non-null `cve_id` in the scan run, traverse the reference graph chain (CVE → `has_weakness` → CWE → `capec_relates_to_cwe` ← CAPEC → `capec_maps_to_attack` → ATT&CK → `technique_mitigated_by_control` → NIST 800-53 control) and upsert `finding_violates_control` edges. Edge schema: `_from = scan_findings/<finding_key>`, `_to = nist_controls/<control_key>`, plus `tenant_id`, `scan_run_id`, `cve_id`, `control_id`, `framework`, `confidence = 1.0`, `evidence_path` (list of vertex `_key` values along the traversal chain), `created_at`.

**Expected outcome:** Each finding with a mapped CVE has at least one `finding_violates_control` edge; findings with no CVE or no mapping produce no edges (not an error).

### REQ-CV-002 — Pipeline Stage Integration
`ViolationMappingPipeline` runs after `ControlMappingPipeline` (status `mapped`), transitions scan run to `violations_mapped`. Follows the existing pipeline pattern (constructor injection: `db`, `repo: ScanEnrichmentRepository`, `violation_repo: ScanViolationRepository`). Zero AQL in pipeline class. `PipelineCoordinator` updated to add `Stage 7: ViolationMappingPipeline` with `_VIOLATION_DONE = frozenset({"violations_mapped"})` guard.

**Expected outcome:** After `mapped` status, coordinator runs `ViolationMappingPipeline` and sets `violations_mapped` on success.

### REQ-CV-003 — Violations Query API
`GET /v1/compliance/violations?scan_run_id=...` returns all `finding_violates_control` edges for the scan run, scoped to caller's tenant. Response: `{ items: [...], total: int }` where each item has `finding_id`, `cve_id`, `control_id`, `framework`, `confidence`, `evidence_path`. Returns 404 if scan run does not exist or does not belong to caller's tenant.

**Expected outcome:** Caller retrieves per-finding compliance violations for a scan run.

### REQ-CV-004 — Coverage Summary API
`GET /v1/compliance/coverage?scan_run_id=...` returns per-framework coverage summary. Response: `{ scan_run_id, total_findings, findings_with_violations, by_framework: [{framework, violated_control_count, control_ids}] }`. Returns 404 if scan run not found or not in caller's tenant.

**Expected outcome:** Caller gets compliance coverage breakdown by framework for a scan run.

---

## Acceptance Criteria (Design-ready)

| ID | Requirement | Criterion |
| --- | --- | --- |
| AC-CV-001 | REQ-CV-001 | `finding_violates_control` edge is created for a finding whose CVE maps to at least one NIST 800-53 control |
| AC-CV-002 | REQ-CV-001 | Edge carries `tenant_id`, `scan_run_id`, `cve_id`, `control_id`, `framework`, `confidence`, `evidence_path`, `created_at` |
| AC-CV-003 | REQ-CV-001 | Finding whose CVE has no control mapping produces zero `finding_violates_control` edges (no error raised) |
| AC-CV-004 | REQ-CV-001 | Edges are tenant-scoped (`tenant_id` field present on each edge) |
| AC-CV-005 | REQ-CV-001 | Edge upsert is idempotent — re-running pipeline does not duplicate edges |
| AC-CV-006 | REQ-CV-002 | `ViolationMappingPipeline.run()` sets scan run status to `violations_mapped` |
| AC-CV-007 | REQ-CV-002 | Pipeline handles scan run with zero findings without error (status still set to `violations_mapped`) |
| AC-CV-008 | REQ-CV-002 | `PipelineCoordinator` runs `ViolationMappingPipeline` after `ControlMappingPipeline` (status `mapped`) |
| AC-CV-009 | REQ-CV-002 | Coordinator skips `ViolationMappingPipeline` when status is already `violations_mapped` |
| AC-CV-010 | REQ-CV-003 | `GET /v1/compliance/violations` returns 200 with violations list for a valid scan run |
| AC-CV-011 | REQ-CV-003 | Violation items include `finding_id`, `cve_id`, `control_id`, `framework`, `confidence`, `evidence_path` |
| AC-CV-012 | REQ-CV-003 | `GET /v1/compliance/violations` returns 404 for a scan run not belonging to the caller's tenant |
| AC-CV-013 | REQ-CV-004 | `GET /v1/compliance/coverage` returns 200 with `total_findings`, `findings_with_violations`, `by_framework` |
| AC-CV-014 | REQ-CV-004 | `by_framework` items include `framework`, `violated_control_count`, `control_ids` |
| AC-CV-015 | REQ-CV-004 | `GET /v1/compliance/coverage` returns 404 for scan run not belonging to caller's tenant |

---

## Requirement Coverage Map (Use Case → Requirement)

| Use Case | Requirement(s) Covered |
| --- | --- |
| UC-CV-001 | REQ-CV-001 |
| UC-CV-002 | REQ-CV-001 |
| UC-CV-003 | REQ-CV-002 |
| UC-CV-004 | REQ-CV-003 |
| UC-CV-005 | REQ-CV-004 |
| UC-CV-006 | REQ-CV-002 |
| UC-CV-007 | REQ-CV-001 (idempotency) |
| UC-CV-008 | REQ-CV-002 (coordinator skip) |

## AC Coverage Map (AC → Stage 7 Scenario)

| AC | Stage 7 Scenario (planned) |
| --- | --- |
| AC-CV-001 | S-CV-001: pipeline run with CVE that maps to controls |
| AC-CV-002 | S-CV-001 (edge fields verified) |
| AC-CV-003 | S-CV-002: pipeline run with CVE that has no controls |
| AC-CV-004 | S-CV-001 (tenant_id in edge) |
| AC-CV-005 | S-CV-003: pipeline idempotency run |
| AC-CV-006 | S-CV-004: pipeline status transition |
| AC-CV-007 | S-CV-005: pipeline with zero findings |
| AC-CV-008 | S-CV-006: coordinator flow |
| AC-CV-009 | S-CV-007: coordinator skip when violations_mapped |
| AC-CV-010 | S-CV-008: GET /v1/compliance/violations 200 |
| AC-CV-011 | S-CV-008 (item fields) |
| AC-CV-012 | S-CV-009: GET /v1/compliance/violations 404 |
| AC-CV-013 | S-CV-010: GET /v1/compliance/coverage 200 |
| AC-CV-014 | S-CV-010 (by_framework fields) |
| AC-CV-015 | S-CV-011: GET /v1/compliance/coverage 404 |

---

## Constraints / Dependencies

- Reference DB graph chain (CVE→CWE→CAPEC→ATT&CK→Control) must be intact — verified working via `GET /v1/reference/controls/{cve_id}`
- `finding_violates_control` edge collection must be added to `db.py` schema
- Pipeline status after `mapped` must not break existing guard-set skip logic in coordinator
- Auth: `customer: Customer = Depends(get_current_customer)`, `get_reference_db()`
- Do NOT use LLM mapping — deterministic traversal only
- `confidence = 1.0` for all deterministic traversal edges

## Assumptions

- NIST control documents reside in collection accessible via `technique_mitigated_by_control` edge `_to` (`nist_controls` or `oscal_controls`)
- Edge `_key` = deterministic hash of `(finding_key, control_key)` for idempotency
- `evidence_path` = list of `_key` values: `[cve_key, cwe_key, capec_key, attack_technique_key, control_key]`
- `framework` field on control documents (e.g., `"NIST_800_53"`) is available in the destination vertex
- AQL `UPSERT` or `import_bulk(on_duplicate="update")` handles idempotency

## Open Questions / Risks (Post-Investigation)

- OQ-2 (Partially resolved): Collection name for NIST 800-53 controls is `nist_controls` or `oscal_controls` — confirm during design by inspecting `technique_mitigated_by_control` target collection
- OQ-3 (Resolved): Coordinator `_RETRIABLE_STATUSES` already includes `"mapped"`, so `violations_mapped` correctly slots in after it
