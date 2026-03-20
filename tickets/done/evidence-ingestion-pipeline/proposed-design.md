# Proposed Design Document: Evidence Data Ingestion Pipeline

## Design Version

- Current Version: `v3`

## Revision History

| Version | Trigger | Summary Of Changes | Related Review Round |
| --- | --- | --- | --- |
| v1 | Initial draft from investigation | Full replacement of ScanIngestionService with v2.2 reference-DB pipeline | Round 1 |
| v2 | Requirement Gap re-entry (Checkov) | Added Checkov IaC-specific fields to V22Finding, checkov_native source on finding_triggers_req, Checkov routing/normalisation block in IngestionNormaliser, UC-017/018/019 and AC-017–AC-023 | Round 4 |
| v3 | Design Impact re-entry (adapter registry) | Replaced `IngestionNormaliser` (per-tool branches) with `IngestionEngine + ADAPTER_REGISTRY` pattern; added `adapter_registry.py` + `ingestion_engine.py`; change inventory C-002 split into C-016 + C-017 | Round 6 |

## Artifact Basis

- Investigation Notes: `tickets/in-progress/evidence-ingestion-pipeline/investigation-notes.md`
- Requirements: `tickets/in-progress/evidence-ingestion-pipeline/requirements.md`
- Requirements Status: `Refined`

---

## Summary

Replace `ScanIngestionService` (customer-DB writer) with a new `EvidenceIngestionService` that writes scanner evidence into the v2.2 reference DB collections (`scan_runs`, `scan_findings`, `detected_controls`, `evidence_packages`, enriched `components`) and creates all 9 new edge collections. The replacement is clean (no backward-compat shims). The existing parsers (SARIF, CycloneDX, Grype) are reused unchanged. A `BackfillAdapter` migrates existing customer DB data.

---

## Goals

1. Populate v2.2 reference DB collections from scanner output
2. Create all 9 new edge collections with deterministic `_key` (idempotent)
3. Apply `INGESTION_NORMALISATION` constants for normalisation via tool-agnostic `IngestionEngine` + `ADAPTER_REGISTRY`
4. Enable Tier 1 AQL compliance traversals on ingested data
5. Migrate legacy customer DB scan data via `BackfillAdapter`
6. Support adding new scanner tools by adding one `ToolAdapter` dict entry — no engine code changes

---

## Legacy Removal Policy (Mandatory)

- Policy: `No backward compatibility; remove legacy code paths.`
- `ScanIngestionService` (`src/api/services/scan.py`) → **Remove** (replaced by `EvidenceIngestionService`)
- `ScanSessionRepository` → **Remove** (replaced by `EvidenceRunRepository`)
- `ScanFindingRepository` (customer DB) → **Remove** (replaced by reference-DB repository)
- `ComponentRepository` (customer DB) → **Remove** (replaced by reference-DB repository)
- `ScanSession` Pydantic model (`complira_graph/models/scan.py`) → **Remove** (replaced by `ScanRun` v2.2 model)
- `ScanFinding` Pydantic model (`complira_graph/models/scan.py`) → **Remove** (replaced by `V22Finding` model)

---

## Requirements And Use Cases

| Requirement ID | Description | Acceptance Criteria ID(s) | Acceptance Criteria Summary | Use Case IDs |
| --- | --- | --- | --- | --- |
| R-001 | Scan run lifecycle | AC-001, AC-002 | scan_runs created on start, updated on completion | UC-001 |
| R-002 | SAST/secrets/DAST finding ingestion | AC-003, AC-013 | fingerprint dedup, normalisation | UC-002, UC-016 |
| R-003 | SCA finding ingestion | AC-004 | CVE-keyed findings + component_has_vuln edge | UC-003, UC-006 |
| R-004 | SBOM component ingestion | AC-005, AC-006 | purl dedup, project_uses_component edge | UC-004, UC-005 |
| R-005 | Finding-to-weakness edge | AC-007 | finding_maps_to_weakness edge | UC-007 |
| R-006 | Finding-to-requirement edge | AC-008 | finding_triggers_req edge | UC-008 |
| R-007 | Finding-to-component edge | AC-009 | finding_in_component edge | UC-009 |
| R-008 | Detected controls | AC-010 | detected_controls + edges (stub) | UC-010, UC-011 |
| R-009 | Evidence package | AC-011 | evidence_packages + traceability edges | UC-012, UC-013 |
| R-010 | Multi-tenant isolation | AC-012 | tenant_id on all docs | All UCs |
| R-011 | Idempotent re-ingestion | AC-015 | deterministic _key, on_duplicate=update | UC-014 |
| R-012 | Backfill legacy data | AC-014 | scan_sessions→scan_runs, FIELD_MAP | UC-015 |
| R-013 | Checkov IaC finding ingestion | AC-017, AC-018, AC-023 | Checkov fields + result routing + fingerprint | UC-017 |
| R-014 | checkov_native finding_triggers_req | AC-019, AC-020 | bc_check_id deterministic mapping | UC-018 |
| R-015 | Checkov PASSED → detected_controls | AC-021, AC-022 | PASSED/SKIPPED routing | UC-019 |

---

## Codebase Understanding Snapshot

| Area | Findings | Evidence | Open Unknowns |
| --- | --- | --- | --- |
| Entrypoints / Boundaries | `POST /v1/scan/ingest` → `ScanIngestionService.ingest_scan()` → parser → customer DB | `src/api/v1/endpoints/scan.py`, `scan.py` service | None |
| Current Naming | Services in `src/api/services/`, models in `src/complira_graph/models/`, repositories in `src/api/repositories/` | consistent across codebase | — |
| Impacted Modules | `ScanIngestionService`, `ScanSessionRepository`, `ScanFindingRepository`, `ComponentRepository`, `ScanSession`/`ScanFinding` models, scan API endpoints | see files above | None |
| Data / Persistence | Existing: customer DB. Target: reference DB via `get_reference_db()` | `api/core/database.py` | `finding_triggers_req` AQL resolution depth |

---

## Current State (As-Is)

```
POST /v1/scan/ingest
  → ScanIngestionService.ingest_scan()
      → ParserFactory.get_parser(format)
      → parser.parse(payload)                    [ParsedScanData]
      → get_customer_db(customer_id)             [customer DB]
      → ScanSessionRepository.create_session()   → scan_sessions (customer DB)
      → ScanFindingRepository.create_finding()   → scan_findings (customer DB)
      → ComponentRepository.bulk_create()        → customer_components (customer DB)
      → ScanEdgeRepository.create_edges()        → finding_to_cve, component_to_finding (customer DB)
```

**Problems**:
- Writes to customer DB, not reference DB
- No fingerprint dedup
- No v2.2 edges (finding→CWE, component→vulnerability, etc.)
- `customer_id` not `tenant_id`
- No compliance traversal support

---

## Target State (To-Be)

```
POST /v1/scan/ingest
  → EvidenceIngestionService.ingest_scan()
      → ParserFactory.get_parser(format)         [reused, unchanged]
      → parser.parse(payload)                    [ParsedScanData — unchanged]
      → get_reference_db()                       [reference DB]
      → EvidenceRunRepository.create_run()       → scan_runs (reference DB, tenant_id)
      → IngestionNormaliser.normalise_findings() → List[V22FindingRecord]
      → EvidenceFindingRepository.upsert_batch() → scan_findings (reference DB, fingerprint dedup)
      → EvidenceComponentRepository.upsert_sbom()→ components (reference DB, purl-keyed global)
      → IngestionEngine.process(tool_name, raw_file, scan_run_id, project_id, tenant_id)
          # reads ToolAdapter from ADAPTER_REGISTRY[tool_name]
          # 9 steps: parse → fingerprint → severity → route → field_map → cwe → redact → validate → plan_edges
          # routing: FAILED→scan_findings, PASSED→detected_controls, SKIPPED→audit_log (per adapter)
          → List[{"collection": str, "document": dict, "edges": list}]
      → EvidenceEdgeService.create_all_edges()
          → component_has_vuln
          → finding_maps_to_weakness
          → finding_triggers_req               (checkov_native if bc_check_id present; else AQL CWE→req)
          → finding_in_component
          → project_uses_component
          → evidence_links_finding
          → evidence_for_project
      → EvidenceRunRepository.complete_run()     → scan_runs updated (counts, compliance_score)
```

```
POST /v1/scan/backfill  (admin only)
  → BackfillAdapter.run()
      → get_all_customer_dbs()
      → read scan_sessions / customer_components from each customer DB
      → apply FIELD_MAP (customer_id → tenant_id)
      → apply LEGACY_COLLECTION_MAP (→ scan_runs / components)
      → write to reference DB
```

---

## Architecture Direction Decision (Mandatory)

- **Chosen direction**: Add new service layer (`EvidenceIngestionService`) + new repository layer (`EvidenceRunRepository`, `EvidenceFindingRepository`, `EvidenceComponentRepository`) + new Pydantic models (`src/complira_graph/models/evidence.py`) + edge creation service (`EvidenceEdgeService`). Remove old service + repositories.
- **Rationale**:
  - `complexity`: linear addition of new modules at correct layer boundaries, no cross-layer entanglement
  - `testability`: each module is independently testable; edge service can be tested with mock reference DB
  - `operability`: single reference DB write target simplifies monitoring and debugging
  - `evolution cost`: clean boundary allows future agents to read evidence collections for Tier 1 AQL without knowing about ingestion history
- **Layering fitness**: No — current layering (customer DB service pattern) is wrong for v2.2. New layering needed.
- **Outcome**: `Add` new modules + `Remove` old modules

### Alternatives Considered

| Option | Summary | Pros | Cons | Decision | Rationale |
| --- | --- | --- | --- | --- | --- |
| A: Dual-write | New service writes to both customer DB AND reference DB | Zero customer impact | Dual-write adds complexity, breaks single source of truth | Rejected | Violates Core Modernization Policy |
| B: Extend existing service | Add reference DB writes inside `ScanIngestionService` | Minimal refactor | Service grows beyond SRP, backward compat complexity | Rejected | Same policy violation |
| C: Clean replacement (chosen) | New `EvidenceIngestionService` replaces old | Clean SRP boundaries, zero compat debt | API response field change (`scan_session_id` → `scan_run_id`) | Chosen | Aligns with Core Modernization Policy |

---

## Change Inventory (Delta)

| Change ID | Change Type | Current Path | Target Path | Rationale | Impacted Areas |
| --- | --- | --- | --- | --- | --- |
| C-001 | Add | — | `src/complira_graph/models/evidence.py` | New v2.2 Pydantic models (ScanRun, V22Finding, V22Component, DetectedControl, EvidencePackage, V22FindingRecord) | Models layer |
| C-002 | Add | — | `src/complira_graph/ingestion/adapter_registry.py` | `ToolAdapter` TypedDict + `ADAPTER_REGISTRY` dict (semgrep, checkov, gitleaks, grype, wiz, trufflehog, zap, sarif); `register_adapter()` public helper | Ingestion config layer |
| C-016 | Add | — | `src/complira_graph/ingestion/ingestion_engine.py` | `IngestionEngine` — single generic 9-step pipeline; reads `ToolAdapter` from registry; adds new tool = one dict entry, no engine code change | Ingestion engine layer |
| C-003 | Add | — | `src/complira_graph/ingestion/repositories.py` | `EvidenceRunRepository`, `EvidenceFindingRepository`, `EvidenceComponentRepository` for reference DB writes | Repository layer |
| C-004 | Add | — | `src/complira_graph/ingestion/edge_service.py` | `EvidenceEdgeService`: creates all 9 new edge collections with generate_edge_key | Edge creation layer |
| C-005 | Add | — | `src/complira_graph/ingestion/service.py` | `EvidenceIngestionService`: orchestrates ingestion pipeline | Service layer |
| C-006 | Add | — | `src/complira_graph/ingestion/backfill.py` | `BackfillAdapter`: reads legacy customer DB data, writes to reference DB | Admin / migration |
| C-007 | Add | — | `src/complira_graph/ingestion/__init__.py` | Package init | — |
| C-008 | Remove | `src/api/services/scan.py` | — | Replaced by `EvidenceIngestionService` | Service layer |
| C-009 | Remove | `src/api/repositories/scan.py` | — | ScanSessionRepository, ScanFindingRepository replaced by reference-DB repos | Repository layer |
| C-010 | Remove | `src/api/repositories/component.py` | — | ComponentRepository (customer DB) replaced | Repository layer |
| C-011 | Modify | `src/api/v1/endpoints/scan.py` | same | Update to call `EvidenceIngestionService`, update response field `scan_session_id` → `scan_run_id` | API layer |
| C-012 | Modify | `src/complira_graph/models/scan.py` | same | Remove `ScanSession`, `ScanFinding` (replaced by `evidence.py` models) | Models layer |
| C-013 | Modify | `src/api/models/responses/scan.py` | same | Update `ScanIngestResponse` to use `scan_run_id` | API response models |
| C-014 | Add | — | `tests/unit/ingestion/` | Unit tests for normaliser, repositories, edge service | Testing |
| C-015 | Add | — | `tests/integration/ingestion/` | Integration tests against reference DB | Testing |

---

## Target Architecture Shape And Boundaries (Mandatory)

| Layer/Boundary | Purpose | Owns | Must Not Own |
| --- | --- | --- | --- |
| `complira_graph/ingestion/` | Evidence ingestion pipeline (new package) | ScanRun lifecycle, finding/component upserts, edge creation, backfill | Parser logic, API routing, auth |
| `complira_graph/models/evidence.py` | v2.2 Pydantic models | ScanRun, V22Finding, V22Component, DetectedControl, EvidencePackage, V22FindingRecord (adapter) | DB access, business logic |
| `complira_graph/ingestion/adapter_registry.py` | Tool adapter configuration | `ToolAdapter` TypedDict; per-tool variation data (parse_format, fingerprint_fields, severity_map, result_routing, field_map, cwe_source, req_mapping_source) | Engine logic, DB writes |
| `complira_graph/ingestion/ingestion_engine.py` | Single generic normalisation engine | 9 invariant steps: parse, fingerprint, severity, route, field_map, CWE extract, redact, validate, plan_edges | Tool-specific branching, DB writes |
| `complira_graph/ingestion/repositories.py` | Reference DB read/write | scan_runs, scan_findings, components, detected_controls, evidence_packages upserts | Edge creation, normalisation logic |
| `complira_graph/ingestion/edge_service.py` | Edge creation for all 9 new edge collections | `generate_edge_key()` usage, AQL lookups for reference resolution, `on_duplicate="update"` | Document upserts, normalisation |
| `complira_graph/ingestion/service.py` | Orchestration | Calls normaliser → repositories → edge service in order | Parser logic, DB access |
| `complira_graph/ingestion/backfill.py` | Legacy migration | Read customer DBs, apply FIELD_MAP, write to reference DB | Runtime ingestion path |
| `api/v1/endpoints/scan.py` | HTTP entrypoint | Route, auth, request validation, response serialization | Business logic |

---

## File And Module Breakdown

| File/Module | Change | Layer | Responsibility | Public APIs | Key Deps |
| --- | --- | --- | --- | --- | --- |
| `complira_graph/models/evidence.py` | Add | Models | v2.2 Pydantic models | `ScanRun`, `V22Finding`, `V22Component`, `DetectedControl`, `EvidencePackage`, `V22FindingRecord` | pydantic, datetime |
| `complira_graph/ingestion/adapter_registry.py` | Add | Config | `ToolAdapter` TypedDict definitions + `ADAPTER_REGISTRY` dict; `register_adapter()` | `ADAPTER_REGISTRY`, `ToolAdapter`, `register_adapter()` | — (pure config, no deps) |
| `complira_graph/ingestion/ingestion_engine.py` | Add | Engine | Single 9-step tool-agnostic normalisation pipeline | `IngestionEngine.process(tool_name, raw_file, scan_run_id, project_id, tenant_id)` | `adapter_registry.py`, `models/evidence.py`, `utils/keys.py` |
| `complira_graph/ingestion/repositories.py` | Add | Repository | Reference DB document upserts | `EvidenceRunRepository`, `EvidenceFindingRepository`, `EvidenceComponentRepository` | `api/core/database.py` (get_reference_db), `models/evidence.py` |
| `complira_graph/ingestion/edge_service.py` | Add | Edge creation | 9 edge collection writes | `EvidenceEdgeService.create_edges(scan_run_doc, findings, components, tenant_id, project_id)` | `utils/keys.py`, `api/core/database.py`, reference DB |
| `complira_graph/ingestion/service.py` | Add | Service | Pipeline orchestration | `EvidenceIngestionService.ingest_scan(tenant_id, request)` | normaliser, repositories, edge_service, parsers |
| `complira_graph/ingestion/backfill.py` | Add | Admin/Migration | Legacy data migration | `BackfillAdapter.run(customer_ids)` | `api/core/database.py` (both DBs), `LEGACY_COLLECTION_MAP`, `FIELD_MAP` |
| `api/services/scan.py` | Remove | — | DELETED | — | — |
| `api/repositories/scan.py` | Remove | — | DELETED | — | — |
| `api/repositories/component.py` | Remove | — | DELETED | — | — |
| `api/v1/endpoints/scan.py` | Modify | API | HTTP routing | Update to `EvidenceIngestionService` | `complira_graph/ingestion/service.py` |
| `complira_graph/models/scan.py` | Modify | Models | Remove `ScanSession`, `ScanFinding` | — | — |
| `api/models/responses/scan.py` | Modify | API models | `scan_run_id` field | `ScanIngestResponse` | — |

---

## Layer-Appropriate Separation Of Concerns Check

- `adapter_registry.py` owns only configuration data (no DB access, no logic): ✓
- `ingestion_engine.py` owns only engine logic (no tool-specific branches, no DB access): ✓
- `repositories.py` owns only DB reads/writes (no business logic): ✓
- `edge_service.py` owns only edge creation (no document writes, no normalisation): ✓
- `service.py` owns only orchestration (no direct DB access): ✓
- `backfill.py` owns only migration (no runtime path): ✓

---

## Adapter Registry Pattern (v3 Addition)

### Design Principle

The 9 normalisation operations (parse, fingerprint, severity, route, field_map, CWE extract, redact, validate, plan_edges) are **invariant** across all tools. Only the *configuration* varies per tool. Encoding variation in code (per-tool `if` branches) means every new tool touches the engine. Encoding variation in data (adapter dict) means adding a tool = one new dict entry.

### ToolAdapter TypedDict (10 required axes)

| Axis | Field | Purpose |
|---|---|---|
| Identity | `tool_name` | Must match `tool` enum in `scan_findings` |
| Parse | `parse_format`, `parse_root`, `multi_root` | How to read the raw file and extract finding array |
| Fingerprint | `fingerprint_fields` | Fields to SHA256-hash for dedup key |
| Severity | `severity_map` | Raw severity → canonical enum |
| Routing | `result_routing`, `result_state_field` | Result state → target collection |
| Location | `location_anchor` | file_line / file_resource / url / cloud_resource / purl |
| Field mapping | `field_map` | Raw field path → canonical scan_findings field; `@prefix` = document-level injection |
| CWE | `cwe_source`, `cwe_extract_pattern` | How CWE IDs are extracted |
| Regulatory | `req_mapping_source`, `deterministic_req_fields` | Source for finding_triggers_req edge |
| Secrets | `secret_raw_field` | Field to redact before storage |

### Escape Hatch: `pre_process`

Optional `Callable[[list[dict]], list[dict]]` runs before the engine loop for structural anomalies: Wiz toxic combination fan-out (1 issue → N resource findings), ZAP instances fan-out.

### Registered Adapters (v3)

| Tool | finding_type | location_anchor | req_mapping_source | notes |
|---|---|---|---|---|
| `semgrep` | sast | file_line | rule_engine | severity_map: ERROR→high, WARNING→medium |
| `checkov` | iac_misconfig | file_resource | checkov_native | multi_root: failed/passed/skipped arrays; check_result nested object |
| `gitleaks` | secret | file_line | none | native Fingerprint field; Match field redacted |
| `grype` | sca | purl | none | routes to component_has_vuln, not scan_findings |
| `wiz` | cspm | cloud_resource | wiz_native | securitySubCategories → deterministic req mapping |
| `trufflehog` | secret | file_line | none | json_lines format; Raw field redacted |
| `zap` | dast | url | rule_engine | cweid integer → CWE-N; instances pre_process fan-out |
| `sarif` (generic) | sast/dast | file_line | rule_engine | generic SARIF 2.1 parser |

### Adding A New Tool

```python
from complira_graph.ingestion.adapter_registry import register_adapter

register_adapter({
    "tool_name":          "bandit",
    "parse_format":       "json_object",
    "parse_root":         "results[*]",
    "fingerprint_fields": ["test_id", "filename", "line_number"],
    "severity_map":       {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"},
    "default_finding_type": "sast",
    "result_routing":     {"*": "scan_findings"},
    "result_state_field": None,
    "location_anchor":    "file_line",
    "field_map":          {"test_id": "rule_id", "filename": "file_path", ...},
    "cwe_source":         "tool_direct",
    "req_mapping_source": "rule_engine",
    "deterministic_req_fields": [],
    "secret_raw_field":   None,
    "pre_process":        None,
})
```

Zero engine code changes. Registry validates required keys at registration time.

---

## Naming Decisions

| Item Type | Current Name | Proposed Name | Reason |
| --- | --- | --- | --- |
| Service | `ScanIngestionService` | `EvidenceIngestionService` | "Evidence" is the v2.2 domain concept; "Scan" is too narrow |
| Package | (none) | `complira_graph/ingestion/` | Evidence ingestion is a `complira_graph` concern (writes to reference DB graph) |
| Model file | `models/scan.py` | `models/evidence.py` (new) | v2.2 models represent evidence layer, not scanner output |
| Adapter model | (none) | `V22FindingRecord` | Explicitly marks it as a v2.2 adapter (transformation output) |
| Repository | `ScanSessionRepository` | `EvidenceRunRepository` | Matches `scan_runs` collection name |

---

## Naming Drift Check

| Item | Current Responsibility | Name Match? | Corrective Action | Change ID |
| --- | --- | --- | --- | --- |
| `ScanIngestionService` | Customer DB writer | No — target is reference DB | Remove | C-008 |
| `ScanSessionRepository` | scan_sessions in customer DB | No — target is scan_runs in reference DB | Remove | C-009 |
| `ScanFinding` model | Customer DB finding (old schema) | No — v2.2 finding has different fields | Remove from scan.py | C-012 |

---

## Existing-Structure Bias Check

| Area | Bias Risk | Architecture-First Alternative | Decision |
| --- | --- | --- | --- |
| Placing new ingestion in `src/api/services/` | High — `api/services/` is for customer-DB API services | `complira_graph/ingestion/` (reference DB pipeline) | Change |
| Reusing `ScanFindingRepository` | High — it's a customer-DB repo | New `EvidenceFindingRepository` in `complira_graph/ingestion/` | Change |
| Keeping `models/scan.py` for new models | Medium — would bloat old file | New `models/evidence.py` | Change |

---

## Anti-Hack Check

| Candidate Change | Hack Risk | Proper Fix | Decision |
| --- | --- | --- | --- |
| Add reference DB writes inside `ScanIngestionService` | High — dual-write in one service, SRP violation | New `EvidenceIngestionService` | Proper fix |
| Alias `customer_id` → `tenant_id` at DB write time in old service | Medium — field aliasing hidden in service | Remove old service, use `FIELD_MAP` in new normaliser explicitly | Proper fix |
| Keep `scan_sessions` collection and add `scan_runs` as alias | High — two sources of truth | Clean cut: `scan_runs` is the only collection going forward | Proper fix |

---

## Dependency Flow And Cross-Reference Risk

| Module | Upstream Deps | Downstream Dependents | Risk | Mitigation |
| --- | --- | --- | --- | --- |
| `models/evidence.py` | pydantic | `normaliser.py`, `repositories.py`, `edge_service.py`, `service.py`, `backfill.py` | Low | Simple data models |
| `normaliser.py` | `models/evidence.py`, `schema/v2_2.py`, `utils/keys.py` | `service.py` | Low | No DB access |
| `repositories.py` | `api/core/database.py`, `models/evidence.py` | `service.py`, `backfill.py` | Low | Single DB target (reference) |
| `edge_service.py` | `utils/keys.py`, `api/core/database.py` | `service.py` | Medium | AQL lookups for `finding_triggers_req` resolution — if CWE→req mapping missing, edge silently skipped |
| `service.py` | `normaliser.py`, `repositories.py`, `edge_service.py`, parsers | `api/v1/endpoints/scan.py` | Low | Clean orchestration |
| `backfill.py` | `api/core/database.py` (both DBs), `LEGACY_COLLECTION_MAP`, `FIELD_MAP` | Admin script / CLI | Medium | Must enumerate all customer DBs — needs discovery mechanism |

---

## Allowed Dependency Direction

- `api/v1/endpoints/` → `complira_graph/ingestion/service.py` (API → domain service): allowed
- `complira_graph/ingestion/*` → `api/core/database.py` (domain → infra): allowed
- `complira_graph/ingestion/*` → `api/parsers/*` (domain → infra parser): allowed (parsers are standalone)
- `api/models/responses/` → (no dependency on ingestion): ✓
- **No** `complira_graph/ingestion/` → `api/services/` (would be circular): enforced by removal

---

## Decommission / Cleanup Plan

| Item To Remove | Cleanup Actions | Verification |
| --- | --- | --- |
| `src/api/services/scan.py` | Delete file; remove import from `api/core/dependencies.py` and scan endpoint | `grep -r ScanIngestionService src/` returns empty |
| `src/api/repositories/scan.py` | Delete file; remove imports in scan endpoint | `grep -r ScanSessionRepository src/` returns empty |
| `src/api/repositories/component.py` | Delete file; remove imports in scan endpoint | `grep -r ComponentRepository src/` returns empty |
| `ScanSession` / `ScanFinding` in `scan.py` | Remove from `complira_graph/models/scan.py` (keep file if other models exist) | No import of removed models |
| `scan_sessions` customer DB collection | NOT deleted from customer DB — backfill reads from it; leave in place | Backfill runs before decommission |

---

## Data Models

### `V22FindingRecord` (adapter model — transformation output)
```
fingerprint: str           # sha256(rule_id:file_path:line_number)[:32] for SAST
                           # sha256(cve_id:purl)[:32] for SCA
                           # sha256(check_id:file_path:resource)[:32] for Checkov IaC
tenant_id: str             # from customer context
scan_run_id: str           # scan_runs _key
finding_type: str          # sast | secrets | dast | sca | iac_misconfig | supply_chain | firmware
tool: str                  # tool name
severity: str              # critical | high | medium | low | info | None (if no --bc-api-key)
cve_id: Optional[str]      # CVE/GHSA if present
cwe_ids: List[str]         # extracted from rule metadata
rule_id: Optional[str]
file_path: Optional[str]
line_number: Optional[int]
description: str
purl: Optional[str]        # component context for SCA
triage_status: str         # default "open"
semgrep_vuln_category: Optional[str]
raw_data: dict
# Checkov IaC-specific fields (Optional — only populated for Checkov findings)
check_id: Optional[str]           # e.g. "CKV_AWS_1"
bc_check_id: Optional[str]        # e.g. "BC_AWS_1" — only present with --bc-api-key
iac_framework: Optional[str]      # injected from document-level check_type (e.g. "terraform", "cloudformation")
resource_address: Optional[str]   # from Checkov "resource" field
check_result: Optional[str]       # "FAILED" (extracted from nested {"result": "FAILED"})
check_name: Optional[str]         # human-readable check description
check_class: Optional[str]        # check class name
guideline: Optional[str]          # remediation URL
```

### `ScanRun` (reference DB doc)
```
_key: str                  # UUID
tenant_id: str
project_id: Optional[str]
repository_id: Optional[str]
tools_invoked: List[str]
status: str                # running | completed | failed
finding_counts: dict       # {critical: N, high: N, ...}
compliance_score: Optional[float]
violated_requirements: List[str]
started_at: str
completed_at: Optional[str]
audit_log: List[dict]      # Checkov SKIPPED entries: [{check_id, resource, file_path, suppression}]
```

### `V22Component` (reference DB doc)
```
_key: str                  # normalize_purl(purl)
purl: str                  # global key — no tenant_id on document
name: str
version: str
type: str
purl_source: str           # sbom | scanner
sbom_format: Optional[str]
firmware_layer: Optional[str]
cpe: Optional[str]
```

---

## Error Handling And Edge Cases

| Scenario | Handling |
| --- | --- |
| Parser fails (invalid SARIF) | Raise `ValueError`, scan_run marked `failed` before raising |
| CWE not found in reference DB for `finding_maps_to_weakness` | Skip edge, log warning — not an error |
| `finding_triggers_req` — no req mapping in reference DB | Skip edge, log info |
| Component purl missing | Generate `pkg:generic/{name}@{version}` fallback (reuse existing scan.py logic) |
| `component_has_vuln` — CVE not in reference DB `vulnerabilities` | Skip edge, log warning |
| Fingerprint collision (sha256 truncation) | Probabilistically negligible; on_duplicate=update handles it correctly |
| Backfill: customer DB not reachable | Skip that customer, log error, continue with others |
| Checkov `check_result` nested object | Extract with `finding["check_result"]["result"]` — never treat as string |
| Checkov `severity` absent (no `--bc-api-key`) | Store `None`; do not default to arbitrary severity |
| Checkov `bc_check_id` absent | Fall back to `llm_reg_mapper` source (or no `finding_triggers_req` edge if LLM not invoked) |
| Checkov `iac_framework` | Inject from document-level `check_type` per-finding in adapter (not from individual finding field) |
| Checkov SCA result (`sca_package`/`sca_image`) | Route to `component_has_vuln` path — not `scan_findings` |
| Checkov SKIPPED result | Append entry to `scan_run.audit_log` list — not written to `scan_findings` |

---

## Use-Case Coverage Matrix

| use_case_id | Primary Path | Fallback Path | Error Path | Call Stack Section |
| --- | --- | --- | --- | --- |
| UC-001 | Yes | N/A | Yes (status=failed) | UC-001 |
| UC-002 | Yes | N/A | Yes (parser fail) | UC-002 |
| UC-003 | Yes | N/A | Yes | UC-003 |
| UC-004 | Yes | Yes (purl fallback) | Yes | UC-004 |
| UC-005 | Yes | N/A | Yes (project not found) | UC-005 |
| UC-006 | Yes | Yes (CVE missing → skip edge) | N/A | UC-006 |
| UC-007 | Yes | Yes (CWE missing → skip edge) | N/A | UC-007 |
| UC-008 | Yes | Yes (no mapping → skip edge) | N/A | UC-008 |
| UC-009 | Yes | Yes (no purl → skip edge) | N/A | UC-009 |
| UC-010 | Stub | N/A | N/A | UC-010 |
| UC-011 | Stub | N/A | N/A | UC-011 |
| UC-012 | Yes | N/A | Yes | UC-012 |
| UC-013 | Yes | N/A | N/A | UC-013 |
| UC-014 | Yes | N/A | N/A | UC-014 |
| UC-015 | Yes | Yes (customer DB unreachable → skip) | Yes | UC-015 |
| UC-016 | Yes | N/A | N/A | UC-016 |
| UC-017 | Yes | Yes (Checkov multi_root routing) | Yes | UC-017 |
| UC-018 | Yes | Yes (bc_check_id absent → llm_reg_mapper) | N/A | UC-018 |
| UC-019 | Yes | N/A | N/A | UC-019 |

---

## Performance / Security Considerations

- **Bulk upserts**: Use `db.collection().import_bulk(docs, on_duplicate="update")` for `scan_findings` and `components` — not per-document inserts
- **Batch edge creation**: Create edges in one `import_bulk()` call per edge collection
- **`tenant_id` isolation**: All evidence queries must bind `tenant_id` (enforced by `INGESTION_NORMALISATION["required_bind_variables"]`)
- **AQL injection**: All AQL in `edge_service.py` uses `bind_vars` — no string interpolation

---

## Migration / Rollout

1. Run `BackfillAdapter` to migrate existing customer DB data to reference DB (admin step)
2. Deploy new `EvidenceIngestionService` and updated API endpoints
3. Decommission `ScanIngestionService` (file deletion — old customer DB data remains accessible via AQL if needed)

---

## Open Questions

1. **`finding_triggers_req` AQL**: What is the path in reference DB from CWE → regulatory_requirement? Need to verify collection + edge structure in reference DB before implementing this in `edge_service.py`.
2. **Customer DB discovery for backfill**: How to enumerate all `complira_customer_*` DBs? Need to check if `api/core/database.py` exposes a list-all-customers function.
3. **API response breaking change**: `scan_session_id` → `scan_run_id` in `ScanIngestResponse`. Flag for API version bump discussion.
