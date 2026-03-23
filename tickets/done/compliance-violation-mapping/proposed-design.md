# Proposed Design — compliance-violation-mapping

**Version:** v2
**Last Updated:** 2026-03-22
**Scope:** Medium

---

## 1. Current State (As-Is)

### Pipeline chain (current)
```
completed → enriched → compacted → mapped → llm_enriched → blast_radius_computed → velocity_computed
```
`ControlMappingPipeline` sets `mapped`. After `mapped`, control coverage ratios are stored in `scan_runs.coverage_by_framework`. No per-finding control violation edges exist.

`finding_triggers_req` edges (`scan_findings → regulatory_requirements`) are created by `EnrichmentPipeline` using `violates_requirement` + `maps_to_requirement` traversal. These link findings to regulatory requirements but do NOT use the full CVE→CWE→CAPEC→ATT&CK→Control chain and carry no control-level metadata.

### Missing
- No `finding_violates_control` edge collection
- No pipeline stage consuming the CVE→CWE→CAPEC→ATT&CK→Control chain at per-finding granularity
- No compliance query API for per-finding violations or per-framework coverage with finding-level detail

---

## 2. Target State (To-Be)

### Pipeline chain (target)
```
completed → enriched → compacted → mapped → violations_mapped → llm_enriched → blast_radius_computed → velocity_computed
```
New `ViolationMappingPipeline` inserts between `mapped` and `llm_enriched`. It traverses the full control chain per finding and writes `finding_violates_control` edges.

### New edge collection: `finding_violates_control`
```
_from: scan_findings/<fingerprint_key>
_to:   oscal_controls/<control_key>
Extra fields:
  tenant_id:     string
  scan_run_id:   string
  cve_id:        string (original CVE-YYYY-NNNNN format)
  control_id:    string (e.g. "AC-2", "SI-2")
  framework:     string (e.g. "NIST_800_53")
  confidence:    float  (1.0 for deterministic chain)
  evidence_path: list[string]  [cve_key, cwe_key, capec_key, attack_key, control_key]
  created_at:    ISO 8601 UTC string
```
Edge `_key` = deterministic hash of `(finding_key, control_key)` using existing `generate_edge_key(finding_key, control_key, "violates_ctrl")`.

### New files
- `src/complira_graph/ingestion/scan_violation_repository.py` — AQL for chain traversal + edge upsert
- `src/complira_graph/ingestion/violation_mapping_pipeline.py` — pipeline stage (zero AQL)
- `src/api/models/responses/compliance.py` — response models
- `src/api/v1/endpoints/compliance.py` — 2 endpoint handlers

### Modified files
- `src/complira_graph/db.py` — add `finding_violates_control` to `EDGE_COLLECTIONS` + `INDEXES`
- `src/complira_graph/ingestion/pipeline_coordinator.py` — add Stage 7 (`ViolationMappingPipeline`); add `violations_mapped` to `_ENRICHMENT_DONE`, `_COMPACTION_DONE`, `_MAPPING_DONE`
- `src/api/v1/router.py` — register compliance router

---

## 3. Architecture Direction

### Layering
Follows the identical pattern established by `BlastRadiusPipeline` + `ScanBlastRadiusRepository`:
- **Repository layer** (`ScanViolationRepository`): all AQL — two methods:
  1. `aql_traverse_controls_for_cves(cve_keys)` → dict keyed by `cve_key`; returns list of `{control_key, control_id, framework, evidence_path}` per CVE
  2. `upsert_finding_violates_control_edges(edges)` → `import_bulk(on_duplicate="update")`
- **Pipeline layer** (`ViolationMappingPipeline`): no AQL; orchestrates read→transform→write; calls `ScanEnrichmentRepository.fetch_findings_for_run()` (existing) and `ScanViolationRepository` methods
- **Coordinator layer** (`PipelineCoordinator`): adds Stage 7; adds `_VIOLATION_DONE` guard set

### Separation of concerns
| Layer | Class | Responsibility |
| --- | --- | --- |
| Repository | `ScanViolationRepository` | AQL for control traversal + edge bulk upsert |
| Pipeline | `ViolationMappingPipeline` | Orchestrate: fetch findings → group by CVE → traverse controls → build edges → upsert → update status |
| Coordinator | `PipelineCoordinator` | Wire stage 7 after stage 3 (control mapping) |
| API models | `compliance.py` | Response models for violations + coverage |
| API endpoint | `compliance.py` | 2 endpoint handlers, tenant-scoped AQL queries |
| Router | `router.py` | Register compliance router under `/compliance` |

### Naming decisions
| Name | Rationale |
| --- | --- |
| `finding_violates_control` | Clear direction (finding → control), mirrors `finding_triggers_req` naming convention |
| `ScanViolationRepository` | Parallel to `ScanBlastRadiusRepository` |
| `ViolationMappingPipeline` | Parallel to `ControlMappingPipeline`, `BlastRadiusPipeline` |
| `violations_mapped` | Clear past-tense status value, consistent with `blast_radius_computed`, `velocity_computed` |
| `/v1/compliance/violations` | Resource-oriented, plural noun |
| `/v1/compliance/coverage` | Summary endpoint, separate from violations list |

### Dependency flow
```
PipelineCoordinator
  → ScanEnrichmentRepository (existing, for fetch_findings_for_run)
  → ViolationMappingPipeline
      → ScanEnrichmentRepository (fetch)
      → ScanViolationRepository (traverse + upsert)

compliance endpoint
  → get_reference_db() (direct)
  → get_current_customer() (Depends)
```
No new cross-layer cycles.

---

## 4. Change Inventory

| # | File | Change Type | Description |
| --- | --- | --- | --- |
| 1 | `src/complira_graph/db.py` | Modify | Add `finding_violates_control` to `EDGE_COLLECTIONS` list and `INDEXES` dict |
| 2 | `src/complira_graph/ingestion/scan_violation_repository.py` | Add | New repository: `aql_traverse_controls_for_cves`, `upsert_finding_violates_control_edges` |
| 3 | `src/complira_graph/ingestion/violation_mapping_pipeline.py` | Add | New pipeline: `run(scan_run_id, tenant_id)` with dedup-by-CVE pattern |
| 4 | `src/complira_graph/ingestion/pipeline_coordinator.py` | Modify | Import + instantiate `ViolationMappingPipeline`; add `_VIOLATION_DONE` guard; add Stage 7 block |
| 5 | `src/api/models/responses/compliance.py` | Add | `ViolationItem`, `ViolationsResponse`, `FrameworkCoverage`, `CoverageResponse` |
| 6 | `src/api/v1/endpoints/compliance.py` | Add | `GET /violations`, `GET /coverage` handlers; inline AQL for query |
| 7 | `src/api/v1/router.py` | Modify | Import + `include_router(compliance.router, prefix="/compliance", ...)` |
| 8 | `tests/unit/...` | Add | Unit tests: pipeline (7 tests), endpoints (7 tests) |

---

## 5. Key AQL Design

### Control traversal AQL (in `ScanViolationRepository.aql_traverse_controls_for_cves`)
```aql
FOR cve_key IN @cve_keys
    LET cve_doc = DOCUMENT(CONCAT("vulnerabilities/", cve_key))
    LET controls = (
        FOR w IN 1..1 OUTBOUND cve_doc has_weakness
            FOR ca IN 1..1 INBOUND w capec_relates_to_cwe
                FOR at IN 1..1 OUTBOUND ca capec_maps_to_attack
                    FOR ctrl IN 1..1 OUTBOUND at technique_mitigated_by_control
                        RETURN DISTINCT {
                            control_key: ctrl._key,
                            control_id: ctrl.control_id,
                            framework: ctrl.framework,
                            evidence_path: [cve_key, w._key, ca._key, at._key, ctrl._key]
                        }
    )
    FILTER LENGTH(controls) > 0
    RETURN {cve_key: cve_key, controls: controls}
```

### Violations query AQL (in `compliance.py` endpoint)
```aql
LET run_doc = FIRST(
    FOR r IN scan_runs
        FILTER r._key == @scan_run_id AND r.tenant_id == @tenant_id
        RETURN 1
)
LET items = (
    FOR e IN finding_violates_control
        FILTER e.scan_run_id == @scan_run_id AND e.tenant_id == @tenant_id
        RETURN {
            finding_id: PARSE_IDENTIFIER(e._from).key,
            cve_id: e.cve_id,
            control_id: e.control_id,
            framework: e.framework,
            confidence: e.confidence,
            evidence_path: e.evidence_path
        }
)
RETURN {run_exists: run_doc != null, items: items}
```

### Coverage query AQL (in `compliance.py` endpoint)
```aql
LET run_doc = FIRST(
    FOR r IN scan_runs
        FILTER r._key == @scan_run_id AND r.tenant_id == @tenant_id
        RETURN r
)
LET total_findings = LENGTH(
    FOR f IN scan_findings
        FILTER f.scan_run_id == @scan_run_id AND f.tenant_id == @tenant_id
        RETURN 1
)
LET findings_with_violations = LENGTH(
    FOR e IN finding_violates_control
        FILTER e.scan_run_id == @scan_run_id AND e.tenant_id == @tenant_id
        COLLECT finding = PARSE_IDENTIFIER(e._from).key
        RETURN finding
)
LET by_framework = (
    FOR e IN finding_violates_control
        FILTER e.scan_run_id == @scan_run_id AND e.tenant_id == @tenant_id
        COLLECT framework = e.framework INTO grouped
        RETURN {
            framework: framework,
            violated_control_count: LENGTH(UNIQUE(grouped[*].e.control_id)),
            control_ids: UNIQUE(grouped[*].e.control_id)
        }
)
RETURN {
    run_exists: run_doc != null,
    scan_run_id: @scan_run_id,
    total_findings: total_findings,
    findings_with_violations: findings_with_violations,
    by_framework: by_framework
}
```

---

## 6. Use Case Coverage Matrix

| Use Case | Primary Path | Fallback Path | Error Path | Runtime Call Stack Section |
| --- | --- | --- | --- | --- |
| UC-CV-001 | Yes | N/A | Yes (CVE doc null) | UC-CV-001 |
| UC-CV-002 | Yes (empty result) | N/A | N/A | UC-CV-002 |
| UC-CV-003 | Yes | N/A | Yes (exception) | UC-CV-003 |
| UC-CV-004 | Yes | N/A | Yes (404) | UC-CV-004 |
| UC-CV-005 | Yes | N/A | Yes (404) | UC-CV-005 |
| UC-CV-006 | Yes | N/A | N/A | UC-CV-006 |
| UC-CV-007 | Yes (idempotent) | N/A | N/A | UC-CV-007 |
| UC-CV-008 | Yes (skip) | N/A | N/A | UC-CV-008 |
