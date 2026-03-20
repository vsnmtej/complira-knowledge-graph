# Requirements: Evidence Data Ingestion Pipeline (v2.2 Scanner Evidence Layer)

**Status:** `Refined`
**Scope Triage:** `Large`
**Branch:** codex/evidence-ingestion-pipeline

---

## Goal / Problem Statement

Build the evidence data ingestion pipeline that populates the v2.2 scanner evidence layer collections now live in ArangoDB. The v2.2 schema (42 doc + 49 edge collections) is already merged into `db.py` and deployed. What is missing is the production ingestion code that reads parsed scanner output (SARIF, CycloneDX, Grype, Checkov) and writes structured evidence into the new collections (`scan_runs`, `scan_findings`, `detected_controls`, `evidence_packages`, enriched `components`) along with the 9 new edge collections.

The pipeline must be multi-tenant (reference DB with `tenant_id` isolation), idempotent (re-ingestion produces updates not duplicates), and aligned with the `INGESTION_NORMALISATION`, `FIELD_MAP`, and `LEGACY_COLLECTION_MAP` constants defined in `complira_kg_schema_v2_2.py`.

The pipeline also handles Checkov IaC findings with framework-specific fields (`check_id`, `bc_check_id`, `iac_framework`, `resource_address`, `check_result`, `check_name`, `check_class`, `guideline`), result routing (FAILED→`scan_findings`, PASSED→`detected_controls`, SKIPPED→`audit_log` field on `scan_run`), and deterministic compliance mapping via `bc_check_id` (`checkov_native` source on `finding_triggers_req`).

---

## In-Scope Use Cases

| ID | Use Case | Description |
| --- | --- | --- |
| UC-001 | Scan run lifecycle management | Create/update `scan_runs` records tracking pipeline execution metadata, tool list, finding counts, compliance snapshot |
| UC-002 | SAST/secrets/DAST finding ingestion | Ingest findings from SARIF parser output into `scan_findings` with fingerprint-based dedup |
| UC-003 | SCA/Grype vulnerability finding ingestion | Ingest SCA findings (CVE-keyed) from Grype parser into `scan_findings` |
| UC-004 | SBOM component ingestion | Ingest CycloneDX SBOM components into global `components` collection (purl-keyed dedup) |
| UC-005 | Project-to-component linking | Create `project_uses_component` edges linking projects to ingested components |
| UC-006 | Component-to-vulnerability edge creation | Create `component_has_vuln` edges from SCA findings (component → vulnerability) |
| UC-007 | Finding-to-weakness edge creation | Create `finding_maps_to_weakness` edges (scan_finding → CWE weakness) |
| UC-008 | Finding-to-requirement edge creation | Create `finding_triggers_req` edges (scan_finding → regulatory_requirement) |
| UC-009 | Finding-to-component edge creation | Create `finding_in_component` edges (scan_finding → component) |
| UC-010 | Detected control ingestion | Ingest positive security control detections into `detected_controls` collection |
| UC-011 | Control mapping edge creation | Create `detected_control_maps_to` (→ OSCAL/SCF) and `control_in_component` edges |
| UC-012 | Evidence package assembly | Create `evidence_packages` linking scan runs, findings, and projects for regulatory submission |
| UC-013 | Evidence-to-finding edge creation | Create `evidence_links_finding` and `evidence_for_project` edges |
| UC-014 | Idempotent re-ingestion | Re-running ingestion on same data produces updates not duplicates (fingerprint/purl dedup + `_ensure_keys()`) |
| UC-015 | Legacy data backfill | Migrate existing customer DB `scan_sessions`/`customer_components` to v2.2 reference DB format using `LEGACY_COLLECTION_MAP` + `FIELD_MAP` |
| UC-016 | Ingestion normalisation | Apply `INGESTION_NORMALISATION` constants: semgrep severity mapping, CWE extraction, CVE validation |
| UC-017 | Checkov IaC finding ingestion | Ingest Checkov FAILED findings into `scan_findings` with IaC-specific fields (`check_id`, `bc_check_id`, `iac_framework`, `resource_address`, `check_result`, `check_name`, `check_class`, `guideline`); route PASSED → `detected_controls`, SKIPPED → `audit_log` on `scan_run` |
| UC-018 | checkov_native finding_triggers_req | When `bc_check_id` is present, create `finding_triggers_req` edge with `source="checkov_native"` (deterministic, no AQL lookup); when absent, fall back to `source="llm_reg_mapper"` |
| UC-019 | Checkov PASSED → detected_controls | Route Checkov checks with result `PASSED` to `detected_controls` collection via existing UC-010 stub path, with `iac_framework` and `check_id` stored |

---

## Acceptance Criteria

| AC ID | Requirement | Measurable Expected Outcome |
| --- | --- | --- |
| AC-001 | Scan run created on ingestion start | A `scan_runs` document with correct `tenant_id`, `project_id`, `tools_invoked`, `status=running` is created before findings are written |
| AC-002 | Scan run updated on completion | `scan_runs` document updated with `status=completed`, `finding_counts`, `compliance_score`, `violated_requirements` after pipeline finishes |
| AC-003 | SARIF findings ingested with dedup | Two SARIF ingestions of same finding produce one `scan_findings` doc (matched by `fingerprint`), second updates first |
| AC-004 | Grype/SCA findings ingested with CVE link | SCA findings create `scan_findings` docs + `component_has_vuln` edges pointing to reference DB `vulnerabilities` collection |
| AC-005 | SBOM components upserted by purl | Two CycloneDX ingestions of same component (same purl) produce one `components` doc, second updates first |
| AC-006 | `project_uses_component` edges created | After SBOM ingestion, edges exist from `projects/<project_id>` to each ingested component |
| AC-007 | `finding_maps_to_weakness` edges created | For findings with CWE IDs, edges exist to reference DB `weaknesses` collection documents |
| AC-008 | `finding_triggers_req` edges created | For findings mapped to regulatory requirements, edges exist to `regulatory_requirements` documents |
| AC-009 | `finding_in_component` edges created | For findings with component context, edges exist to `components` documents |
| AC-010 | Detected controls ingested with edges | `detected_controls` docs + `detected_control_maps_to` + `control_in_component` edges created correctly |
| AC-011 | Evidence package assembled | `evidence_packages` doc created linking scan run + tenant + project, with `evidence_links_finding` and `evidence_for_project` edges |
| AC-012 | Multi-tenant isolation enforced | All evidence documents have non-empty `tenant_id`; query by `tenant_id` returns only that tenant's data |
| AC-013 | Ingestion normalisation applied | Semgrep `ERROR` severity maps to `critical`, CWE IDs extracted from rule IDs, CVE IDs validated by regex before edge creation |
| AC-014 | Legacy backfill produces correct output | `scan_sessions` backfill creates `scan_runs` docs with `customer_id` renamed to `tenant_id`; `customer_components` backfill creates `components` docs |
| AC-015 | Deterministic edge keys | All new edge collections use `generate_edge_key()` to produce deterministic `_key`; re-ingestion does not create duplicate edges |
| AC-016 | Existing 705 tests still pass | No regression in existing test suite after pipeline code is added |
| AC-017 | Checkov FAILED findings ingested with IaC fields | Checkov FAILED findings produce `scan_findings` docs with `check_id`, `bc_check_id`, `iac_framework`, `resource_address`, `check_result`, `check_name`, `check_class`, `guideline` fields populated from Checkov JSON |
| AC-018 | Checkov fingerprint uses resource scope | Two Checkov FAILED ingestions of same check produce one `scan_findings` doc keyed by `sha256(check_id:file_path:resource)[:32]`; second ingestion updates first |
| AC-019 | checkov_native finding_triggers_req edge created | When `bc_check_id` is present, a `finding_triggers_req` edge exists with `source="checkov_native"` for that finding |
| AC-020 | checkov_native falls back to llm_reg_mapper | When `bc_check_id` is absent (open-source Checkov without `--bc-api-key`), `finding_triggers_req` source is `"llm_reg_mapper"` (or no edge if LLM mapper not invoked) |
| AC-021 | Checkov PASSED results routed to detected_controls | Checkov checks with `check_result.result == "PASSED"` create `detected_controls` docs (not `scan_findings`), with `iac_framework` and `check_id` fields |
| AC-022 | Checkov SKIPPED results recorded in audit_log | Checkov checks with `check_result.result == "SKIPPED"` are recorded in the `audit_log` field of the parent `scan_run` doc; not written to `scan_findings` |
| AC-023 | Checkov SCA/secrets frameworks rerouted | Checkov findings with `iac_framework` in `[sca_package, sca_image]` are routed to `component_has_vuln` path (not `scan_findings`); `secrets` framework findings are routed as SAST-type secrets findings |

---

## Constraints / Dependencies

- v2.2 schema is already live in ArangoDB (42 doc + 49 edge collections) — no schema changes needed in this ticket
- Must use reference DB (`complira_graph`) for all v2.2 evidence collections (not customer DBs)
- Must use `tenant_id` (not `customer_id`) on all evidence documents — `FIELD_MAP` constant defines this
- Must use `generate_edge_key()` from `src/complira_graph/utils/keys.py` for all edge `_key` generation
- Must integrate with existing parser factory at `src/api/parsers/` (SARIF, CycloneDX, Grype)
- Must use `INGESTION_NORMALISATION` constants from `complira_kg_schema_v2_2.py` for normalisation
- Must use `LEGACY_COLLECTION_MAP` and `FIELD_MAP` from `complira_kg_schema_v2_2.py` for backfill
- Existing ingestion in `src/api/services/scan.py` writes to customer DB — new pipeline writes to reference DB
- Python-arango >= 7.x required (already in use)
- Must not break existing 705-passing test suite

---

## Architecture Decisions (Post-Investigation)

| Decision | Choice | Rationale |
| --- | --- | --- |
| Relationship to `ScanIngestionService` | **Clean replacement** | Core Modernization Policy: no backward compat. New `EvidenceIngestionService` replaces old. API endpoint updated. |
| DB target | **Reference DB only** | `DB_PLACEMENT` confirms all v2.2 collections → reference DB with `tenant_id` isolation |
| Model placement | **`src/complira_graph/models/evidence.py`** | v2.2 models belong in `complira_graph` (they model graph entities, not API contracts) |
| Service pattern | **Service (not BaseAgent)** | Ingestion is on-demand (API-triggered), not batch seeding. BaseAgent pattern is for seeding. |
| `ParsedFinding` | **Keep unchanged** | Parser output model stays minimal. New `V22FindingRecord` adapter model handles mapping to v2.2 schema. |
| Fingerprint generation | **`sha256(rule_id:file_path:line_number)[:32]` for SAST, `sha256(cve_id:purl)[:32]` for SCA** | `INGESTION_NORMALISATION["semgrep_fingerprint_fields"]` defines the fields |
| `components` key | **`normalize_purl(purl)`** | Global, purl-keyed, no tenant_id on document |
| `project_uses_component` edge | **Created at SBOM ingestion time** | Links `projects/<project_id>` → `components/<purl_key>` with `tenant_id` |
| `detected_controls` | **Stub implementation** | No current parser emits positive control detections; implement model + edge skeleton, skip normalisation |
| `finding_triggers_req` | **AQL lookup via CWE→req path in reference DB** | CWE IDs extracted from finding, then AQL traversal finds linked requirements |
| `finding_triggers_req` — Checkov path | **`bc_check_id` → `checkov_native` source (deterministic); absent → `llm_reg_mapper`** | `bc_check_id` is stable Prisma policy ID → deterministic regulatory mapping without AQL CWE traversal |
| Checkov fingerprint | **`sha256(check_id:file_path:resource)[:32]`** | `INGESTION_NORMALISATION["checkov_fingerprint_fields"]` defines fields; `resource` is the Checkov field name (not `resource_address`) |
| Checkov result routing | **`FAILED→scan_findings`, `PASSED→detected_controls`, `SKIPPED→audit_log`** | FDA/CRA compliance requires audit trail of all check outcomes, not just failures |
| Backfill | **Separate `BackfillAdapter` module** | One-time admin operation, not runtime path |

---

## Requirement Coverage Map

| Requirement (UC) | Design Section | Call Stack Use Case |
| --- | --- | --- |
| UC-001 | ScanRun lifecycle | UC-001 call stack |
| UC-002 | SAST finding ingestion + V22FindingRecord | UC-002 call stack |
| UC-003 | SCA finding ingestion | UC-003 call stack |
| UC-004 | SBOM component upsert | UC-004 call stack |
| UC-005 | project_uses_component edge | UC-005 call stack |
| UC-006 | component_has_vuln edge | UC-006 call stack |
| UC-007 | finding_maps_to_weakness edge | UC-007 call stack |
| UC-008 | finding_triggers_req AQL lookup + edge | UC-008 call stack |
| UC-009 | finding_in_component edge | UC-009 call stack |
| UC-010 | detected_controls stub | UC-010 call stack |
| UC-011 | detected_control_maps_to + control_in_component edges | UC-011 call stack |
| UC-012 | evidence_packages + evidence_links_finding + evidence_for_project | UC-012/UC-013 call stack |
| UC-013 | (same as UC-012) | UC-012/UC-013 call stack |
| UC-014 | fingerprint dedup + generate_edge_key idempotency | UC-014 call stack |
| UC-015 | BackfillAdapter | UC-015 call stack |
| UC-016 | INGESTION_NORMALISATION transformer | UC-016 call stack |
| UC-017 | Checkov IaC ingestion: IaC-specific fields + result routing | UC-017 call stack |
| UC-018 | checkov_native finding_triggers_req edge | UC-018 call stack |
| UC-019 | Checkov PASSED → detected_controls routing | UC-019 call stack |

---

## Acceptance Criteria Coverage Map (AC → Stage 7 Scenario)

| AC ID | Stage 7 Scenario |
| --- | --- |
| AC-001 | S-001: Verify scan_run doc created with status=running on ingest start |
| AC-002 | S-002: Verify scan_run updated with counts/status after completion |
| AC-003 | S-003: Double-ingest same SARIF → single scan_findings doc (fingerprint dedup) |
| AC-004 | S-004: SCA ingest → scan_findings + component_has_vuln edge in reference DB |
| AC-005 | S-005: Double CycloneDX ingest same purl → single components doc |
| AC-006 | S-006: SBOM ingest → project_uses_component edges exist in reference DB |
| AC-007 | S-007: SAST finding with CWE → finding_maps_to_weakness edge exists |
| AC-008 | S-008: Finding with CWE → finding_triggers_req edge exists if req mapping found |
| AC-009 | S-009: Finding with purl context → finding_in_component edge exists |
| AC-010 | S-010: detected_controls doc created with correct edges (stub test) |
| AC-011 | S-011: evidence_packages doc created with evidence_links_finding + evidence_for_project |
| AC-012 | S-012: All evidence docs have non-null tenant_id; query by wrong tenant returns empty |
| AC-013 | S-013: Semgrep ERROR → severity=high, CWE extracted, CVE validated |
| AC-014 | S-014: Backfill scan_session → scan_run with customer_id→tenant_id rename |
| AC-015 | S-015: Re-ingest same data → deterministic edge _key, no duplicates |
| AC-016 | S-016: Existing 705 tests still pass after implementation |
| AC-017 | S-017: Checkov FAILED ingest → scan_findings doc with check_id, bc_check_id, iac_framework, resource_address populated |
| AC-018 | S-018: Double-ingest same Checkov check → single scan_findings doc (resource-scoped fingerprint dedup) |
| AC-019 | S-019: Checkov FAILED finding with bc_check_id → finding_triggers_req edge with source=checkov_native |
| AC-020 | S-020: Checkov FAILED finding without bc_check_id → no checkov_native edge; llm_reg_mapper source used or edge absent |
| AC-021 | S-021: Checkov PASSED check → detected_controls doc created (not scan_findings) |
| AC-022 | S-022: Checkov SKIPPED check → audit_log field on scan_run updated; not in scan_findings |
| AC-023 | S-023: Checkov sca_package/sca_image finding → component_has_vuln path; secrets finding → secrets/SAST path |

---

## Assumptions

- ArangoDB reference DB is accessible via `get_reference_db()` from `api.core.database`
- Reference DB `vulnerabilities`, `weaknesses`, `regulatory_requirements`, `oscal_controls`, `scf_controls` collections already populated
- `ParsedFinding` and `ParsedScanData` parser models remain unchanged
- `tenant_id` is the `customer_id` from the authenticated customer context
- Backfill is one-time/manual — not a runtime path

---

## Open Questions / Risks

1. **`finding_triggers_req` resolution depth**: AQL must traverse CWE → regulatory_requirement. If no mapping exists in reference DB, edge is silently skipped (not an error). Need to confirm the reference DB has populated `cwe_to_regulation` or equivalent traversal.
2. **API response change**: `ScanIngestResponse` returns `scan_session_id`. Replacing `ScanIngestionService` means the response should return `scan_run_id`. This is a breaking change to the API contract — needs to be flagged.
3. **Existing customer DB scan queries**: API read endpoints (`GET /v1/scan/{session_id}`, `GET /v1/scans`) currently query customer DB `scan_sessions`. After replacement, these must query reference DB `scan_runs` filtered by `tenant_id`. These endpoints are in scope for update.
4. **`detected_controls` source**: No current scanner emits positive control detections — stub is correct for now, flagged for follow-up.
