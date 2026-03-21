# Proposed Design: Core Pipeline Phase 1
# Three-Stage Post-Ingestion Intelligence Pipeline

**Ticket:** `core-pipeline-phase-1`
**Status:** `Design`
**Scope:** `LARGE`
**Last Updated:** 2026-03-21
**Author:** Claude Code (claude-sonnet-4-6)

---

## Table of Contents

1. Current State Summary (Phase 0 As-Is)
2. Target State Summary (Phase 1 To-Be)
3. Architecture Direction Decision
4. Layering Fitness Check
5. Change Inventory Table
6. Per-Module Specification
7. Naming Decisions
8. Naming-Drift Check
9. Dependency Flow
10. Data Models
11. Error Handling
12. Use-Case Coverage Matrix

---

## 1. Current State Summary (Phase 0 As-Is)

### 1.1 Ingestion Pipeline Today

Phase 0 delivered the scan ingestion infrastructure. The pipeline is synchronous, invoked from the HTTP request thread, and terminates when the scan run record reaches `status="completed"`.

**Pipeline sequence (from `EvidenceIngestionService.ingest_scan()`):**

```
POST /v1/scan/ingest
  └── EvidenceIngestionService.ingest_scan()
        ├── EvidenceRunRepository.create_run()          → scan_runs {status=running}
        ├── IngestionEngine.process()                    → List[IngestionBundle]
        ├── EvidenceFindingRepository.upsert_batch()    → scan_findings
        ├── EvidenceDetectedControlRepository.upsert_batch() → detected_controls
        ├── EvidenceRunRepository.append_audit_log()    → scan_runs.audit_log
        ├── EvidenceEdgeService.create_all_edges()
        │     ├── create_component_has_vuln_edges()
        │     ├── create_finding_weakness_edges()       → finding_maps_to_weakness
        │     ├── create_finding_req_edges()             → finding_triggers_req (rule_engine/checkov_native)
        │     ├── create_finding_in_component_edges()   → finding_in_component
        │     └── create_detected_control_edges()        → stub (no-op)
        ├── _assemble_evidence_package()                → evidence_packages
        ├── EvidenceEdgeService.create_evidence_finding_edges() → evidence_links_finding
        ├── EvidenceEdgeService.create_evidence_project_edge()  → evidence_for_project
        └── EvidenceRunRepository.complete_run(status="completed")
```

**Status chain today:** `running → completed | failed`

### 1.2 What scan_findings Documents Contain After Phase 0

Fields written by ingestion (present after `status="completed"`):

| Field | Source | Phase 0 |
|---|---|---|
| `_key` / `fingerprint` | IngestionEngine | Written |
| `scan_run_id` | IngestionEngine | Written |
| `tenant_id` | IngestionEngine | Written |
| `cve_id` | IngestionEngine field_map | Written (nullable) |
| `cwe_ids` | IngestionEngine step 6 | Written (list, tool-sourced) |
| `severity` | IngestionEngine step 5 | Written (normalized) |
| `rule_id` / `check_id` | IngestionEngine field_map | Written |
| `file_path`, `line_start` | IngestionEngine field_map | Written |
| `tool` | IngestionEngine | Written |
| `triage_status` | IngestionEngine | Written (`open`) |
| `epss_score` | Not written | Absent |
| `epss_percentile` | Not written | Absent |
| `in_kev` | Not written | Absent |
| `cwe_chain` | Not written | Absent |
| `d3fend_techniques` | Not written | Absent |
| `risk_score` | Not written | Absent |
| `compaction_group_id` | Not written | Absent |
| `cluster_rank` | Not written | Absent |
| `compacted` | Not written | Absent |
| `enriched_at` | Not written | Absent |

### 1.3 What detected_controls Documents Contain After Phase 0

| Field | Phase 0 |
|---|---|
| `_key` / `fingerprint` | Written |
| `scan_run_id`, `tenant_id` | Written |
| `check_id`, `check_name` | Written |
| `triage_status` | Written (`compliant`) |
| `framework` | Absent |
| `evidence_chain` | Absent |
| `control_status` | Absent |

### 1.4 What scan_runs Documents Contain After Phase 0

| Field | Phase 0 |
|---|---|
| `status` | Written (`running` → `completed` or `failed`) |
| `finding_counts` | Written |
| `compliance_score` | Written (None) |
| `coverage_by_framework` | Absent |

### 1.5 Existing Service: EnrichmentService (NOT extended)

`src/api/services/enrichment_service.py` performs single-CVE enrichment via sequential AQL queries. It is scan-run-unaware, does not write back to `scan_findings`, and does not create edges. Phase 1 does **not** extend this service. It remains available for the `/v1/enrich` endpoint (per-CVE on-demand use). Phase 1 builds a separate bulk pipeline approach.

### 1.6 Known Gaps Entering Phase 1

- No EPSS, KEV, D3FEND data on any `scan_findings` document
- No composite risk scores — triage is purely scanner-severity-based
- `finding_triggers_req` edges exist only from scanner rule IDs (rule_engine path), not from CVE → `violates_requirement` traversal
- `detected_control_maps_to` edges are a no-op stub in `EvidenceEdgeService.create_detected_control_edges()`
- No compliance coverage computation

---

## 2. Target State Summary (Phase 1 To-Be)

### 2.1 Extended Status Chain

```
running → completed → enriched → compacted → mapped
```

Failure states at each stage:
- `pipeline_failed` — unhandled exception mid-stage (partial writes retained)
- `enrichment_pending` — reference DB unreachable at pipeline entry (retriable)

### 2.2 What Phase 1 Adds

**Three new pipeline services** in `src/complira_graph/ingestion/`:

| Module | Use Case | Status Transition |
|---|---|---|
| `enrichment_pipeline.py` | UC-007 | `completed → enriched` |
| `compaction_pipeline.py` | UC-008 | `enriched → compacted` |
| `control_mapping_pipeline.py` | UC-009 | `compacted → mapped` |

**One new repository** in `src/complira_graph/ingestion/`:

| Module | Purpose |
|---|---|
| `scan_enrichment_repository.py` | Bulk reads/writes for pipeline stages; distinct from ingestion-time repositories |

**One new API endpoint** in `src/api/v1/endpoints/`:

| Module | Routes |
|---|---|
| `pipeline.py` | `POST /v1/scans/{scan_run_id}/enrich` (manual trigger, 202) |

**Auto-trigger mechanism** added to `src/api/v1/endpoints/scan.py`:
- After `ingest_scan` returns `status="completed"`, the endpoint adds the three pipeline stages as a FastAPI `BackgroundTask`

### 2.3 New Coordinator Service

`src/complira_graph/ingestion/pipeline_coordinator.py` owns the three-stage orchestration: it is invoked by both the BackgroundTask path and the manual trigger endpoint. It accepts `scan_run_id` and `tenant_id`, checks the current status, and calls the three pipeline stages in order.

### 2.4 New Pipeline Trigger Flow (Auto)

```
POST /v1/scan/ingest  (unchanged request/response)
  └── ingest_scan_endpoint()
        ├── EvidenceIngestionService.ingest_scan()  → ScanIngestResult {status="completed"}
        └── background_tasks.add_task(
                PipelineCoordinator.run_post_ingest_pipeline,
                scan_run_id=result.scan_run_id,
                tenant_id=customer.id
            )
      Response: 200 {scan_run_id, status="completed"}
      [Background]:
        PipelineCoordinator.run_post_ingest_pipeline()
          ├── EnrichmentPipeline.run()     → status="enriched"
          ├── CompactionPipeline.run()     → status="compacted"
          └── ControlMappingPipeline.run() → status="mapped"
```

### 2.5 New Pipeline Trigger Flow (Manual)

```
POST /v1/scans/{scan_run_id}/enrich
  └── enrich_scan_endpoint()
        ├── Verify scan_run ownership (tenant_id check)
        ├── Verify status in {completed, enriched, compacted, pipeline_failed, enrichment_pending}
        └── background_tasks.add_task(
                PipelineCoordinator.run_post_ingest_pipeline,
                scan_run_id, tenant_id
            )
      Response: 202 {scan_run_id, message="enrichment queued"}
```

---

## 3. Architecture Direction Decision

### 3.1 Decision: Bulk AQL Pipeline in `complira_graph/ingestion/` (NOT extension of EnrichmentService)

**Chosen direction:** New pipeline modules in `src/complira_graph/ingestion/`. Single reference DB handle (`get_reference_db()`). No LLM calls. Bulk AQL per stage.

**Rationale:**

1. **Placement fitness:** `complira_graph/ingestion/` already contains the full Phase 0 evidence pipeline. Post-ingestion stages are a logical continuation of the same evidence assembly process. They belong in the same package.

2. **EnrichmentService is per-CVE, not per-run:** `EnrichmentService._get_cve_data()` executes one AQL per CVE with multiple sub-queries. For a scan with 500 findings, that is 500 sequential AQL round-trips. Phase 1 needs bulk-first: single AQL traversal over all CVE IDs in a run.

3. **Separation of concerns:** The Phase 0 `EnrichmentService` is an API-layer service used by `GET /v1/enrich` for interactive single-CVE queries. Coupling it to pipeline bulk operations would create two different call patterns through the same class and complicate both.

4. **Reference DB consistency:** All v2.2 evidence collections (`scan_findings`, `scan_runs`, `detected_controls`, all edge collections) are in the reference DB. `get_reference_db()` is the single DB handle needed. No customer DB routing is required.

5. **Idempotency:** `import_bulk(on_duplicate="update")` is the existing contract for all evidence upserts. Pipeline stages must follow the same contract.

**Alternatives rejected:**

- *Extend EnrichmentService:* Rejected because it is per-CVE and API-response-shaped; restructuring it for bulk pipeline would break the existing `/v1/enrich` contract.
- *Separate worker process / Celery task:* Out of scope for Phase 1. FastAPI `BackgroundTasks` is sufficient for target < 30s on 500 findings.
- *Inline in EvidenceIngestionService:* Rejected because it would make the already-long ingestion service responsible for three additional complex stages. Single-responsibility principle violated.

---

## 4. Layering Fitness Check

```
Layer 0: HTTP / FastAPI
  src/api/v1/endpoints/scan.py         ← adds BackgroundTask trigger
  src/api/v1/endpoints/pipeline.py     ← new manual trigger endpoint

Layer 1: Service Orchestration
  src/complira_graph/ingestion/pipeline_coordinator.py  ← new
  src/complira_graph/ingestion/enrichment_pipeline.py   ← new
  src/complira_graph/ingestion/compaction_pipeline.py   ← new
  src/complira_graph/ingestion/control_mapping_pipeline.py ← new
  (existing: service.py, edge_service.py, ingestion_engine.py)

Layer 2: Data Access
  src/complira_graph/ingestion/scan_enrichment_repository.py ← new
  (existing: repositories.py — EvidenceRunRepository.complete_run() reused)

Layer 3: Database
  ArangoDB reference DB (StandardDatabase)
  Collections: scan_findings, scan_runs, detected_controls, edge collections
  Reference graph: vulnerabilities, weaknesses, kev_entries, epss_history,
                   oscal_controls, scf_controls, regulatory_requirements
```

**Fitness rules verified:**

| Rule | Check |
|---|---|
| Layer N calls only Layer N+1 or same-layer peers | Pass: endpoint → coordinator → pipelines → repository → ArangoDB |
| API layer contains no AQL | Pass: endpoints only call coordinator; all AQL in repository |
| Repository layer contains no business logic | Pass: risk score formula is in CompactionPipeline, not repository |
| Service layer does not import FastAPI types | Pass: pipeline services receive `scan_run_id: str`, `db: StandardDatabase` — no FastAPI deps |
| Single DB handle throughout pipeline | Pass: `get_reference_db()` obtained once at endpoint, passed down via coordinator |

---

## 5. Change Inventory Table

| # | Action | File | Change Type | Notes |
|---|---|---|---|---|
| 1 | Add | `src/complira_graph/ingestion/enrichment_pipeline.py` | New file | UC-007 EnrichmentPipeline |
| 2 | Add | `src/complira_graph/ingestion/compaction_pipeline.py` | New file | UC-008 CompactionPipeline |
| 3 | Add | `src/complira_graph/ingestion/control_mapping_pipeline.py` | New file | UC-009 ControlMappingPipeline |
| 4 | Add | `src/complira_graph/ingestion/pipeline_coordinator.py` | New file | Orchestrates all three stages; entry point for both auto and manual triggers |
| 5 | Add | `src/complira_graph/ingestion/scan_enrichment_repository.py` | New file | Bulk read/write repository for pipeline stages |
| 6 | Add | `src/api/v1/endpoints/pipeline.py` | New file | `POST /v1/scans/{scan_run_id}/enrich` manual trigger |
| 7 | Modify | `src/api/v1/endpoints/scan.py` | Modify | Add BackgroundTask trigger after successful `ingest_scan` |
| 8 | Modify | `src/complira_graph/ingestion/__init__.py` | Modify | Export new pipeline classes |
| 9 | Modify | `src/api/v1/router.py` (or equivalent) | Modify | Register pipeline endpoint router |
| 10 | No change | `src/complira_graph/ingestion/repositories.py` | Read-only reuse | `EvidenceRunRepository.complete_run()` reused as-is for status transitions |
| 11 | No change | `src/complira_graph/ingestion/edge_service.py` | Read-only reuse | `create_detected_control_edges()` stub is superseded by `ControlMappingPipeline`; stub remains in place |
| 12 | No change | `src/api/services/enrichment_service.py` | Untouched | Per-CVE API enrichment; not part of pipeline |
| 13 | No change | `src/complira_graph/ingestion/service.py` | Read-only reuse | `EvidenceIngestionService.ingest_scan()` result consumed by endpoint to get `scan_run_id` |

---

## 6. Per-Module Specification

---

### 6.1 `scan_enrichment_repository.py`

**Responsibility:** Single data-access class for all bulk reads and writes required by the three pipeline stages. Owns all AQL queries for the pipeline. Service-layer pipeline classes hold no AQL.

**Change type:** New file

**Class:** `ScanEnrichmentRepository`

**Constructor:**
```python
def __init__(self, db: StandardDatabase) -> None:
    self._db = db
```

**Key APIs:**

```python
def fetch_findings_for_run(
    self,
    scan_run_id: str,
    tenant_id: str,
    batch_size: int = 500,
) -> Iterator[list[dict]]:
    """
    Yield batches of scan_findings for the given scan_run.
    Filters: scan_run_id == @run_id AND tenant_id == @tenant_id.
    Batch size <= 500 per transaction (Risk-3 constraint).
    AQL: FOR f IN scan_findings FILTER ... LIMIT @offset, @batch RETURN f
    Yields list[dict] per batch until exhausted.
    """

def fetch_enriched_findings_for_run(
    self,
    scan_run_id: str,
    tenant_id: str,
    batch_size: int = 500,
) -> Iterator[list[dict]]:
    """
    Yield batches of scan_findings that have cve_id (non-null) and enriched_at set.
    Used by CompactionPipeline.
    """

def fetch_detected_controls_for_run(
    self,
    scan_run_id: str,
    tenant_id: str,
) -> list[dict]:
    """
    Return all detected_controls for the run in one query.
    Filters: scan_run_id == @run_id AND tenant_id == @tenant_id.
    """

def bulk_update_findings(
    self,
    updates: list[dict],
) -> None:
    """
    Bulk-update scan_findings documents by _key.
    Uses AQL FOR update IN @updates UPDATE update._key WITH update IN scan_findings.
    Each dict in updates must have '_key' plus the fields to update.
    Does not require tenant_id re-check (called with pre-validated docs).
    Batches internally at 500.
    """

def bulk_upsert_detected_controls(
    self,
    docs: list[dict],
) -> None:
    """
    Upsert detected_controls documents.
    Delegates to db.collection("detected_controls").import_bulk(on_duplicate="update").
    """

def upsert_finding_triggers_req_edges(
    self,
    edges: list[dict],
) -> None:
    """
    Upsert finding_triggers_req edges.
    Uses db.collection("finding_triggers_req").import_bulk(on_duplicate="update").
    """

def upsert_detected_control_maps_to_edges(
    self,
    edges: list[dict],
) -> None:
    """
    Upsert detected_control_maps_to edges.
    Uses db.collection("detected_control_maps_to").import_bulk(on_duplicate="update").
    """

def update_scan_run_status(
    self,
    scan_run_key: str,
    status: str,
    extra_fields: Optional[dict] = None,
) -> None:
    """
    Convenience wrapper around EvidenceRunRepository-style update.
    Updates scan_runs._key with {status, ...extra_fields, updated_at}.
    """

def update_scan_run_coverage(
    self,
    scan_run_key: str,
    coverage_by_framework: dict,
) -> None:
    """
    Write coverage_by_framework to scan_runs document.
    """

def aql_enrich_findings_batch(
    self,
    cve_keys: list[str],
) -> dict[str, dict]:
    """
    Single AQL traversal over a batch of CVE keys.
    Returns dict keyed by cve_key with enrichment payload:
      {epss_score, epss_percentile, in_kev, cwe_chain, d3fend_techniques, req_keys}

    AQL pattern:
      FOR cve_key IN @cve_keys
        LET cve_doc = DOCUMENT(CONCAT("vulnerabilities/", cve_key))
        LET epss = FIRST(
          FOR e, edge IN 1..1 OUTBOUND cve_doc has_epss
          SORT e.score_date DESC LIMIT 1 RETURN e
        )
        LET in_kev = (LENGTH(
          FOR k IN kev_entries
          FILTER k.cve_id == REGEX_REPLACE(cve_key, "_", "-")
          LIMIT 1 RETURN 1
        ) > 0)
        LET cwes = (
          FOR w IN 1..1 OUTBOUND cve_doc has_weakness
          RETURN w.cwe_id
        )
        LET req_keys = (
          FOR req IN 1..2 OUTBOUND cve_doc
            violates_requirement, maps_to_requirement
          RETURN DISTINCT req._key
        )
        LET attack_techs = (
          FOR w IN 1..1 OUTBOUND cve_doc has_weakness
            FOR t IN 1..1 INBOUND w technique_exploits_weakness
            RETURN DISTINCT t._key
        )
        LET d3fend = (
          FOR tech IN attack_techs
            FOR d IN 1..1 INBOUND DOCUMENT(CONCAT("attack_techniques/", tech))
              d3fend_counters_technique
            RETURN DISTINCT d.d3fend_id
        )
        RETURN {
          cve_key: cve_key,
          epss_score: epss.epss_score,
          epss_percentile: epss.percentile,
          in_kev: in_kev,
          cwe_chain: cwes,
          d3fend_techniques: d3fend,
          req_keys: req_keys
        }
    """

def aql_get_cwe_parent_map(
    self,
    cwe_keys: list[str],
) -> dict[str, str]:
    """
    For CWEs without a maps_to_requirement edge, find the nearest parent
    that does have one via child_of traversal.
    Returns dict: {cwe_key -> parent_cwe_key_with_req} or {cwe_key -> cwe_key} if self has req.

    AQL pattern:
      FOR cwe_key IN @cwe_keys
        LET has_req = LENGTH(
          FOR req IN 1..1 OUTBOUND DOCUMENT(CONCAT("weaknesses/", cwe_key))
            maps_to_requirement RETURN 1
        ) > 0
        LET parent = (
          FILTER !has_req
          FOR p IN 1..5 OUTBOUND DOCUMENT(CONCAT("weaknesses/", cwe_key)) child_of
            FILTER LENGTH(
              FOR r IN 1..1 OUTBOUND p maps_to_requirement RETURN 1
            ) > 0
            LIMIT 1
            RETURN p._key
        )
        RETURN {cwe_key: cwe_key, resolved: has_req ? cwe_key : FIRST(parent)}
    """

def aql_resolve_control_framework(
    self,
    control_keys: list[str],
) -> dict[str, str]:
    """
    Look up each control key in oscal_controls and scf_controls.
    Returns dict: {control_key -> framework_name}
    Framework names: "NIST 800-53", "ISO 27001", "FDA 510(k)", "IEC 62304", "CRA"
    """

def aql_resolve_evidence_chains(
    self,
    controls: list[dict],
    scan_run_id: str,
) -> dict[str, list[str]]:
    """
    For each detected_control, resolve the evidence chain:
      [finding_id, cwe_id, req_id, control_id]

    For each control with a req_id:
      finding_id: FIRST finding in scan_run that triggers that req_id
        (via finding_triggers_req edge traversal)
      cwe_id: FIRST element of that finding's cwe_chain
      req_id: control.req_id
      control_id: control._key

    Missing elements (no edge found, no cwe_chain) are empty string "".

    AQL pattern (batched over all controls in one round-trip):
      FOR ctrl IN @controls
        LET finding_id = FIRST(
          FOR edge IN finding_triggers_req
            FILTER edge._to == CONCAT("regulatory_requirements/", ctrl.req_id)
              AND edge.scan_run_id == @scan_run_id
            LIMIT 1
            RETURN PARSE_IDENTIFIER(edge._from).key
        )
        LET cwe_id = (finding_id != null ?
          FIRST(DOCUMENT(CONCAT("scan_findings/", finding_id)).cwe_chain) : "")
        RETURN {
          control_key: ctrl._key,
          chain: [
            finding_id != null ? finding_id : "",
            cwe_id != null ? cwe_id : "",
            ctrl.req_id,
            ctrl._key
          ]
        }

    Returns dict: {control_key -> [finding_id, cwe_id, req_id, control_id]}
    """
```

**Inputs:** `db: StandardDatabase`, various `scan_run_id: str`, `tenant_id: str`, `list[dict]` payloads
**Outputs:** batched iterators, dict lookup maps, None (for write methods)
**Dependencies:** `arango.database.StandardDatabase`, `complira_graph.utils.keys`

---

### 6.2 `pipeline_coordinator.py`

**Responsibility:** Orchestrates the three pipeline stages in order. Single entry point for both the BackgroundTask path and the manual API trigger. Checks scan_run status before each stage, skips stages already completed, catches stage failures, and advances or fails the scan_run status.

**Change type:** New file

**Class:** `PipelineCoordinator`

**Constructor:**
```python
def __init__(self, db: StandardDatabase) -> None:
    self._db = db
    self._run_repo = EvidenceRunRepository(db)
    self._repo = ScanEnrichmentRepository(db)
    self._enrichment = EnrichmentPipeline(db, self._repo)
    self._compaction = CompactionPipeline(db, self._repo)
    self._control_mapping = ControlMappingPipeline(db, self._repo)
```

**Key APIs:**

```python
async def run_post_ingest_pipeline(
    self,
    scan_run_id: str,
    tenant_id: str,
) -> None:
    """
    Run all three pipeline stages in order for a completed scan_run.

    Pre-condition: scan_run.status == "completed" (enforced by status check).
    If reference DB unavailable, sets status="enrichment_pending" and returns.
    Each stage is called in sequence. If a stage raises, status="pipeline_failed".
    Idempotent: if status is already "enriched", skips UC-007. If "compacted", skips UC-007 and UC-008.

    Call stack:
      1. _verify_reference_db()
      2. _get_run_status(scan_run_id) → current_status
      3. if current_status not in retriable → return early
      4. EnrichmentPipeline.run(scan_run_id, tenant_id)
      5. CompactionPipeline.run(scan_run_id, tenant_id)
      6. ControlMappingPipeline.run(scan_run_id, tenant_id)
    """

def _verify_reference_db(self) -> bool:
    """
    Lightweight ping: try to read one document from vulnerabilities collection.
    Returns False if connection fails; caller sets enrichment_pending.
    """

def _get_run_status(self, scan_run_id: str) -> str:
    """Fetch scan_runs._key status field."""
```

**Inputs:** `scan_run_id: str`, `tenant_id: str`, `db: StandardDatabase`
**Outputs:** None (side effects only — status updates, enrichment writes)
**Dependencies:** `ScanEnrichmentRepository`, `EnrichmentPipeline`, `CompactionPipeline`, `ControlMappingPipeline`, `EvidenceRunRepository`

---

### 6.3 `enrichment_pipeline.py`

**Responsibility:** UC-007 Vulnerability Enrichment. Reads all `scan_findings` for the run in batches, identifies findings with `cve_id`, executes bulk AQL traversal against the reference knowledge graph, writes enrichment fields back to `scan_findings`, upserts new `detected_controls`, creates `finding_triggers_req` and `detected_control_maps_to` edges. Advances scan_run to `enriched`.

**Change type:** New file

**Class:** `EnrichmentPipeline`

**Constructor:**
```python
def __init__(self, db: StandardDatabase, repo: ScanEnrichmentRepository) -> None:
    self._db = db
    self._repo = repo
```

**Key APIs:**

```python
def run(self, scan_run_id: str, tenant_id: str) -> None:
    """
    Entry point for UC-007.

    Full call sequence:
      1. Fetch findings in batches via repo.fetch_findings_for_run()
      2. For each batch:
         a. Extract distinct cve_ids → normalize to cve_keys (underscore format)
         b. repo.aql_enrich_findings_batch(cve_keys) → enrichment_map
         c. _build_finding_updates(batch, enrichment_map) → updates
         d. repo.bulk_update_findings(updates)
         e. _build_req_edges(batch, enrichment_map, tenant_id) → req_edges
         f. repo.upsert_finding_triggers_req_edges(req_edges)
         g. _build_detected_controls(batch, enrichment_map, tenant_id) → control_docs
         h. repo.bulk_upsert_detected_controls(control_docs)
         i. _build_detected_control_maps_to_edges(control_docs, tenant_id) → ctrl_edges
         j. repo.upsert_detected_control_maps_to_edges(ctrl_edges)
      3. repo.update_scan_run_status(scan_run_id, "enriched", {enriched_at: utcnow()})
    """

def _build_finding_updates(
    self,
    findings: list[dict],
    enrichment_map: dict[str, dict],
) -> list[dict]:
    """
    Build update dicts for scan_findings.
    For each finding with cve_id: merge enrichment_map[cve_key] fields.
    Fields written: epss_score, epss_percentile, in_kev, cwe_chain,
                    d3fend_techniques, enriched_at.
    Findings without cve_id: update with enriched_at only (no enrichment fields).
    Returns list of {_key, ...fields} dicts.
    """

def _build_req_edges(
    self,
    findings: list[dict],
    enrichment_map: dict[str, dict],
    tenant_id: str,
) -> list[dict]:
    """
    Build finding_triggers_req edge dicts from CVE → violates_requirement traversal.
    _from: scan_findings/<fingerprint>
    _to: regulatory_requirements/<req_key>
    source: "cve_violates_req"
    Deduplicates by edge _key (generate_edge_key(fingerprint, req_key, "triggers_req")).
    """

def _build_detected_controls(
    self,
    findings: list[dict],
    enrichment_map: dict[str, dict],
    tenant_id: str,
) -> list[dict]:
    """
    Upsert detected_controls for every OSCAL/SCF control reachable via
    CVE → violates_requirement → ... chain.
    _key: generate_edge_key(scan_run_id, req_key, "ctrl")
    """

def _build_detected_control_maps_to_edges(
    self,
    control_docs: list[dict],
    tenant_id: str,
) -> list[dict]:
    """
    Build detected_control_maps_to edge dicts.
    _from: detected_controls/<control_key>
    _to: regulatory_requirements/<req_key>
    """

def _normalize_cve_to_key(self, cve_id: str) -> str:
    """CVE-2024-1234 → CVE_2024_1234 (underscore format for ArangoDB _key)."""
```

**Inputs:** `scan_run_id: str`, `tenant_id: str`
**Outputs:** None (side effects: scan_findings updated, edges created, status advanced)
**Dependencies:** `ScanEnrichmentRepository`, `complira_graph.utils.keys.generate_edge_key`

**Batch contract:** All reads and writes respect `batch_size=500`.

---

### 6.4 `compaction_pipeline.py`

**Responsibility:** UC-008 Finding Compaction and Risk Scoring. Reads enriched findings in batches, groups by CWE (with parent roll-up), computes composite risk scores, assigns compaction_group_id, sets compacted flag, assigns cluster_rank. Advances scan_run to `compacted`.

**Change type:** New file

**Class:** `CompactionPipeline`

**Constructor:**
```python
def __init__(self, db: StandardDatabase, repo: ScanEnrichmentRepository) -> None:
    self._db = db
    self._repo = repo
```

**Key APIs:**

```python
def run(self, scan_run_id: str, tenant_id: str) -> None:
    """
    Entry point for UC-008.

    Full call sequence:
      1. Fetch ALL findings for run (accumulate across batches — risk scoring needs global view)
      2. Collect unique CWE keys from cwe_chain across all findings
      3. repo.aql_get_cwe_parent_map(cwe_keys) → cwe_parent_map
      4. _assign_compaction_groups(all_findings, cwe_parent_map) → group_map
      5. _compute_risk_scores(all_findings) → risk_score_map
      6. _compute_cluster_ranks(all_findings, group_map, risk_score_map) → rank_map
      7. _build_compaction_updates(all_findings, group_map, risk_score_map, rank_map) → updates
      8. repo.bulk_update_findings(updates)  [batches internally at 500]
      9. repo.update_scan_run_status(scan_run_id, "compacted")
    """

def _assign_compaction_groups(
    self,
    findings: list[dict],
    cwe_parent_map: dict[str, str],
) -> dict[str, str]:
    """
    Group findings by resolved CWE key.
    Resolution: use first CWE in cwe_chain after parent roll-up.
    Returns dict: {finding_fingerprint -> compaction_group_id}
    compaction_group_id = resolved_cwe_key (stable, deterministic).
    Findings with empty cwe_chain: group_id = "no_cwe_<fingerprint>".
    Within each group: first finding (by fingerprint sort) is canonical; rest are compacted.
    """

def _compute_risk_scores(
    self,
    findings: list[dict],
) -> dict[str, float]:
    """
    Compute risk_score per finding.

    Formula:
      cvss_normalized = (cvss_base or 0.0) / 10.0
      epss = epss_score or 0.0
      kev_bonus = 1.0 if in_kev else 0.0
      exploit_bonus = min(exploit_count / 5.0, 1.0)  [exploit_count from scan_finding.d3fend_techniques length proxy if no explicit field]

      risk_score = cvss_normalized * 0.4 + epss * 0.3 + kev_bonus * 0.2 + exploit_bonus * 0.1

    Findings with no cve_id: risk_score = 0.0
    Returns dict: {fingerprint -> risk_score}

    Note on exploit_bonus: Phase 1 uses len(d3fend_techniques) > 0 as a binary
    exploit signal (exploit_bonus = 0.1 if d3fend_techniques non-empty else 0.0).
    Exact exploit count enrichment deferred to Phase 2.
    """

def _compute_cluster_ranks(
    self,
    findings: list[dict],
    group_map: dict[str, str],
    risk_score_map: dict[str, float],
) -> dict[str, int]:
    """
    Assign cluster_rank to each finding based on its compaction_group's
    max(risk_score). Rank 1 = cluster with highest max_risk_score.
    Ties broken by group_id alphabetically (deterministic).
    Returns dict: {fingerprint -> cluster_rank}
    """

def _build_compaction_updates(
    self,
    findings: list[dict],
    group_map: dict[str, str],
    risk_score_map: dict[str, float],
    rank_map: dict[str, int],
) -> list[dict]:
    """
    Build update dicts for scan_findings.
    Fields: risk_score, compaction_group_id, cluster_rank, compacted (bool).
    Returns list of {_key, risk_score, compaction_group_id, cluster_rank, compacted}.
    """
```

**Inputs:** `scan_run_id: str`, `tenant_id: str`
**Outputs:** None (side effects: scan_findings updated, status advanced)
**Dependencies:** `ScanEnrichmentRepository`

**Note on accumulate-all pattern:** Step 1 accumulates all findings across batches before computing cluster ranks. For scans with > 5000 findings, this holds the full list in memory. This is acceptable for Phase 1 (target: < 30s on 500 findings). A streaming rank approach is deferred to Phase 2.

---

### 6.5 `control_mapping_pipeline.py`

**Responsibility:** UC-009 Control Mapping. Reads all `detected_controls` for the run, resolves each control to a framework, generates evidence chains, computes coverage percentages per framework, writes results back to `detected_controls`, updates `scan_runs.coverage_by_framework`. Advances scan_run to `mapped`.

**Change type:** New file

**Class:** `ControlMappingPipeline`

**Constructor:**
```python
def __init__(self, db: StandardDatabase, repo: ScanEnrichmentRepository) -> None:
    self._db = db
    self._repo = repo
```

**Key APIs:**

```python
def run(self, scan_run_id: str, tenant_id: str) -> None:
    """
    Entry point for UC-009.

    Full call sequence:
      1. repo.fetch_detected_controls_for_run(scan_run_id, tenant_id) → controls
      2. Collect unique control keys
      3. repo.aql_resolve_control_framework(control_keys) → framework_map
      4. _build_evidence_chains(controls, scan_run_id, tenant_id) → chain_map
      5. _build_control_updates(controls, framework_map, chain_map) → updates
      6. repo.bulk_upsert_detected_controls(updates)
      7. _compute_coverage(controls, framework_map) → coverage_by_framework
      8. repo.update_scan_run_coverage(scan_run_id, coverage_by_framework)
      9. repo.update_scan_run_status(scan_run_id, "mapped")
    """

def _build_evidence_chains(
    self,
    controls: list[dict],
    scan_run_id: str,
    tenant_id: str,
) -> dict[str, list[str]]:
    """
    For each detected_control, build evidence_chain:
      [finding_id, cwe_id, req_id, control_id]

    Delegates to repo.aql_resolve_evidence_chains(controls, scan_run_id).
    This method prepares the call and receives the chain map; all AQL is in
    the repository layer (ScanEnrichmentRepository.aql_resolve_evidence_chains).

    If chain cannot be fully resolved (e.g. no finding_triggers_req edge for this req),
    chain is partial: missing elements are empty string "".
    Returns dict: {control_key -> [finding_id, cwe_id, req_id, control_id]}
    """

def _build_control_updates(
    self,
    controls: list[dict],
    framework_map: dict[str, str],
    chain_map: dict[str, list[str]],
) -> list[dict]:
    """
    Build upsert dicts for detected_controls.
    Fields: framework, evidence_chain, control_status.
    control_status: "present" (Phase 1 default for all detected controls).
    """

def _compute_coverage(
    self,
    controls: list[dict],
    framework_map: dict[str, str],
) -> dict[str, float]:
    """
    Compute coverage_by_framework.

    For each framework: count distinct req_ids covered by at least one detected_control.
    Total reqs per framework: queried from regulatory_requirements collection.
    coverage_pct = (covered_reqs / total_reqs) * 100.0

    Returns dict: {"NIST 800-53": 12.5, "ISO 27001": 8.3, ...}
    """

def _get_total_reqs_by_framework(self) -> dict[str, int]:
    """
    AQL: FOR r IN regulatory_requirements
         COLLECT framework = r.framework WITH COUNT INTO cnt
         RETURN {framework, cnt}
    Returns dict: {framework -> total_req_count}
    """
```

**Inputs:** `scan_run_id: str`, `tenant_id: str`
**Outputs:** None (side effects: detected_controls updated, scan_runs.coverage_by_framework updated, status advanced)
**Dependencies:** `ScanEnrichmentRepository`

---

### 6.6 `src/api/v1/endpoints/pipeline.py`

**Responsibility:** HTTP endpoint for manual pipeline trigger. Validates scan_run ownership (tenant_id check), validates status is re-triggerable, enqueues as BackgroundTask, returns 202 Accepted. Contains no pipeline logic.

**Change type:** New file

**Router:** `APIRouter()`

**Endpoints:**

```
POST /v1/scans/{scan_run_id}/enrich
  → 202 Accepted {scan_run_id, message="enrichment queued"}
  → 404 if scan_run not found or belongs to different tenant
  → 409 if scan_run status not in retriable set
  → 500 internal error
```

**Re-triggerable statuses:** `{"completed", "enriched", "compacted", "pipeline_failed", "enrichment_pending"}`

**Call sequence:**

```python
@router.post("/{scan_run_id}/enrich", status_code=202)
async def enrich_scan_endpoint(
    scan_run_id: str,
    background_tasks: BackgroundTasks,
    customer: Customer = Depends(get_current_customer),
):
    ref_db = get_reference_db()
    run_doc = ref_db.collection("scan_runs").get(scan_run_id)
    if not run_doc or run_doc.get("tenant_id") != customer.id:
        raise HTTPException(404)
    if run_doc.get("status") not in RETRIABLE_STATUSES:
        raise HTTPException(409, detail=f"scan_run status {run_doc['status']} is not re-triggerable")
    coordinator = PipelineCoordinator(ref_db)
    background_tasks.add_task(
        coordinator.run_post_ingest_pipeline,
        scan_run_id=scan_run_id,
        tenant_id=customer.id,
    )
    return {"scan_run_id": scan_run_id, "message": "enrichment queued"}
```

**Inputs:** `scan_run_id: str` (path), `Customer` (auth)
**Outputs:** `{"scan_run_id": str, "message": str}` (202)
**Dependencies:** `PipelineCoordinator`, `get_reference_db`, `get_current_customer`

---

### 6.7 Modified: `src/api/v1/endpoints/scan.py`

**Responsibility:** Existing ingest endpoint. Change: add BackgroundTask trigger after successful `ingest_scan` result.

**Change type:** Modify — add ~10 lines to `ingest_scan_endpoint()`

**Change description:**

Add `background_tasks: BackgroundTasks` parameter to `ingest_scan_endpoint()`. After `result = await svc.ingest_scan(...)` returns with `result.status == "completed"`, add:

```python
if result.status == "completed":
    from complira_graph.ingestion.pipeline_coordinator import PipelineCoordinator
    coordinator = PipelineCoordinator(ref_db)
    background_tasks.add_task(
        coordinator.run_post_ingest_pipeline,
        scan_run_id=result.scan_run_id,
        tenant_id=customer.id,
    )
```

The HTTP response is unchanged (200 with `status="completed"`). The pipeline runs asynchronously after the response is sent.

**Import addition:** `from fastapi import BackgroundTasks`

---

## 7. Naming Decisions

### 7.1 Module Names

| Decision | Name Chosen | Rationale |
|---|---|---|
| UC-007 pipeline module | `enrichment_pipeline.py` | Matches `EnrichmentPipeline` class; aligns with `compaction_pipeline` and `control_mapping_pipeline` naming pattern |
| UC-008 pipeline module | `compaction_pipeline.py` | Consistent suffix `_pipeline`; matches UC-008 name "Finding Compaction" |
| UC-009 pipeline module | `control_mapping_pipeline.py` | Consistent suffix; matches UC-009 name "Control Mapping" |
| Coordinator module | `pipeline_coordinator.py` | Single word `coordinator` signals orchestration role, distinct from individual pipeline `*_pipeline.py` files |
| Repository module | `scan_enrichment_repository.py` | `scan_enrichment` scopes it to the post-ingestion phase; avoids conflict with existing `repositories.py` |
| API endpoint module | `pipeline.py` | Short, matches the resource being controlled; parallel to `scan.py`, `enrich.py`, `meta.py` |

### 7.2 Class Names

| Class | Module | Rationale |
|---|---|---|
| `EnrichmentPipeline` | `enrichment_pipeline.py` | PascalCase of module name |
| `CompactionPipeline` | `compaction_pipeline.py` | PascalCase of module name |
| `ControlMappingPipeline` | `control_mapping_pipeline.py` | PascalCase of module name |
| `PipelineCoordinator` | `pipeline_coordinator.py` | Agent-style noun (`Coordinator`) |
| `ScanEnrichmentRepository` | `scan_enrichment_repository.py` | Consistent with existing `EvidenceRunRepository`, `EvidenceFindingRepository` pattern |

### 7.3 Status Value Strings

| Value | Meaning | Transition From |
|---|---|---|
| `"enriched"` | UC-007 complete | `"completed"` |
| `"compacted"` | UC-008 complete | `"enriched"` |
| `"mapped"` | UC-009 complete | `"compacted"` |
| `"pipeline_failed"` | Unhandled exception in any stage | Any stage |
| `"enrichment_pending"` | Reference DB unreachable | `"completed"` |

### 7.4 New scan_findings Fields

| Field | Type | UC |
|---|---|---|
| `epss_score` | `float` | UC-007 |
| `epss_percentile` | `float` | UC-007 |
| `in_kev` | `bool` | UC-007 |
| `cwe_chain` | `list[str]` | UC-007 |
| `d3fend_techniques` | `list[str]` | UC-007 |
| `enriched_at` | `str` (ISO datetime) | UC-007 |
| `risk_score` | `float` [0.0, 1.0] | UC-008 |
| `compaction_group_id` | `str` | UC-008 |
| `cluster_rank` | `int` (1-based) | UC-008 |
| `compacted` | `bool` | UC-008 |

### 7.5 New detected_controls Fields

| Field | Type | UC |
|---|---|---|
| `framework` | `str` | UC-009 |
| `evidence_chain` | `list[str]` [4 elements] | UC-009 |
| `control_status` | `str` | UC-009 |
| `req_id` | `str` | UC-007 (written during enrichment for chain resolution) |

### 7.6 New scan_runs Fields

| Field | Type | UC |
|---|---|---|
| `coverage_by_framework` | `dict[str, float]` | UC-009 |
| `enriched_at` | `str` (ISO datetime) | UC-007 |
| `pipeline_error` | `str` | Cross-cutting (failure mode) |

### 7.7 Edge Source Labels (finding_triggers_req)

| Source Label | Meaning | Existing or New |
|---|---|---|
| `"rule_engine"` | CWE → req traversal from scanner CWE (Phase 0) | Existing |
| `"checkov_native"` | bc_check_id lookup (Phase 0) | Existing |
| `"cve_violates_req"` | CVE → `violates_requirement` traversal (Phase 1) | New |

---

## 8. Naming-Drift Check

Phase 1 introduces new names. The following table checks each against existing codebase conventions to ensure consistency and catch potential collisions.

| New Name | Convention Check | Drift Risk |
|---|---|---|
| `EnrichmentPipeline` | Existing: `EvidenceIngestionService`, `IngestionEngine` — CamelCase service/engine pattern. Match. | None |
| `ScanEnrichmentRepository` | Existing: `EvidenceRunRepository`, `EvidenceFindingRepository` — `*Repository` suffix. Match. | None |
| `PipelineCoordinator` | No prior coordinator class. Consistent with existing naming style. | None |
| `enrichment_pipeline.py` | Existing modules: `service.py`, `edge_service.py`, `repositories.py`, `ingestion_engine.py`, `adapter_registry.py`. New `*_pipeline.py` suffix is new but clear. | Acceptable — explicit suffix avoids confusion with `service.py` |
| `scan_run.status="enriched"` | Existing: `"running"`, `"completed"`, `"failed"`. Past-tense verb pattern. Match. | None |
| `scan_run.status="pipeline_failed"` | Existing: `"failed"`. `pipeline_failed` disambiguates from ingestion `failed`. | Minor drift — two different failed states. Justified by different recoverability. |
| `cwe_chain` (finding field) | Existing: `cwe_ids` (set at ingestion). `cwe_chain` is the enriched traversal result. Distinct name avoids overwriting ingestion field. | None |
| `evidence_chain` (control field) | No existing field. New concept. | None |
| `coverage_by_framework` (scan_run field) | No existing field. `compliance_score` exists (float). `coverage_by_framework` is a dict. Compatible. | None |
| `cve_violates_req` (edge source label) | Existing labels: `rule_engine`, `checkov_native`. Underscore format match. | None |
| `aql_enrich_findings_batch` | Methods on repo class. Prefix `aql_` signals AQL-executing methods. New convention, internal to repo. | Acceptable — scoped to `ScanEnrichmentRepository` |

**Collision check on `cwe_chain` vs `cwe_ids`:**
- `cwe_ids` (Phase 0): set by `IngestionEngine._extract_cwe()` from scanner tool output. Contains raw CWE IDs as the scanner reports them.
- `cwe_chain` (Phase 1): set by `EnrichmentPipeline` from `has_weakness` reference graph traversal. Contains the authoritative CVE → CWE chain from the knowledge graph.
- These are intentionally separate fields. `cwe_ids` reflects what the scanner found; `cwe_chain` reflects what the reference graph resolves from the CVE. Both may be present simultaneously.

**No name collisions detected.**

---

## 9. Dependency Flow Between Layers

### 9.1 Module Dependency Graph

```
src/api/v1/endpoints/scan.py
  import: complira_graph.ingestion.pipeline_coordinator.PipelineCoordinator
  import: api.core.database.get_reference_db
  import: fastapi.BackgroundTasks

src/api/v1/endpoints/pipeline.py
  import: complira_graph.ingestion.pipeline_coordinator.PipelineCoordinator
  import: api.core.database.get_reference_db
  import: api.core.security.get_current_customer
  import: fastapi.{APIRouter, BackgroundTasks, HTTPException, Depends}

src/complira_graph/ingestion/pipeline_coordinator.py
  import: complira_graph.ingestion.enrichment_pipeline.EnrichmentPipeline
  import: complira_graph.ingestion.compaction_pipeline.CompactionPipeline
  import: complira_graph.ingestion.control_mapping_pipeline.ControlMappingPipeline
  import: complira_graph.ingestion.scan_enrichment_repository.ScanEnrichmentRepository
  import: complira_graph.ingestion.repositories.EvidenceRunRepository
  import: arango.database.StandardDatabase

src/complira_graph/ingestion/enrichment_pipeline.py
  import: complira_graph.ingestion.scan_enrichment_repository.ScanEnrichmentRepository
  import: complira_graph.utils.keys.generate_edge_key
  import: arango.database.StandardDatabase

src/complira_graph/ingestion/compaction_pipeline.py
  import: complira_graph.ingestion.scan_enrichment_repository.ScanEnrichmentRepository
  import: arango.database.StandardDatabase

src/complira_graph/ingestion/control_mapping_pipeline.py
  import: complira_graph.ingestion.scan_enrichment_repository.ScanEnrichmentRepository
  import: arango.database.StandardDatabase

src/complira_graph/ingestion/scan_enrichment_repository.py
  import: arango.database.StandardDatabase
  import: complira_graph.utils.keys.generate_edge_key
```

### 9.2 Layered Call Stack: Auto-Trigger Path (Happy Path)

```
[HTTP Thread]
POST /v1/scan/ingest
 └── ingest_scan_endpoint(request, customer, background_tasks)
       ├── get_reference_db() → ref_db
       ├── EvidenceIngestionService(ref_db).ingest_scan(...) → ScanIngestResult
       └── background_tasks.add_task(PipelineCoordinator(ref_db).run_post_ingest_pipeline, ...)

[Background Thread — after HTTP response sent]
PipelineCoordinator.run_post_ingest_pipeline(scan_run_id, tenant_id)
 ├── _verify_reference_db() → True
 ├── _get_run_status(scan_run_id) → "completed"
 │
 ├── EnrichmentPipeline.run(scan_run_id, tenant_id)
 │     ├── repo.fetch_findings_for_run(scan_run_id, tenant_id, batch_size=500) → Iterator[batch]
 │     │     FOR EACH BATCH:
 │     ├── _extract_cve_keys(batch) → cve_keys
 │     ├── repo.aql_enrich_findings_batch(cve_keys) → enrichment_map
 │     ├── _build_finding_updates(batch, enrichment_map) → updates
 │     ├── repo.bulk_update_findings(updates)
 │     ├── _build_req_edges(batch, enrichment_map, tenant_id) → req_edges
 │     ├── repo.upsert_finding_triggers_req_edges(req_edges)
 │     ├── _build_detected_controls(batch, enrichment_map, tenant_id) → ctrl_docs
 │     ├── repo.bulk_upsert_detected_controls(ctrl_docs)
 │     ├── _build_detected_control_maps_to_edges(ctrl_docs, tenant_id) → ctrl_edges
 │     └── repo.upsert_detected_control_maps_to_edges(ctrl_edges)
 │     └── repo.update_scan_run_status(scan_run_id, "enriched", {enriched_at: ...})
 │
 ├── CompactionPipeline.run(scan_run_id, tenant_id)
 │     ├── repo.fetch_findings_for_run(scan_run_id, tenant_id) → all findings accumulated
 │     ├── _collect_cwe_keys(all_findings) → cwe_keys
 │     ├── repo.aql_get_cwe_parent_map(cwe_keys) → cwe_parent_map
 │     ├── _assign_compaction_groups(all_findings, cwe_parent_map) → group_map
 │     ├── _compute_risk_scores(all_findings) → risk_score_map
 │     ├── _compute_cluster_ranks(all_findings, group_map, risk_score_map) → rank_map
 │     ├── _build_compaction_updates(all_findings, group_map, risk_score_map, rank_map) → updates
 │     ├── repo.bulk_update_findings(updates)   [internal batching at 500]
 │     └── repo.update_scan_run_status(scan_run_id, "compacted")
 │
 └── ControlMappingPipeline.run(scan_run_id, tenant_id)
       ├── repo.fetch_detected_controls_for_run(scan_run_id, tenant_id) → controls
       ├── _collect_control_keys(controls) → control_keys
       ├── repo.aql_resolve_control_framework(control_keys) → framework_map
       ├── _build_evidence_chains(controls, scan_run_id, tenant_id) → chain_map
       ├── _build_control_updates(controls, framework_map, chain_map) → updates
       ├── repo.bulk_upsert_detected_controls(updates)
       ├── _compute_coverage(controls, framework_map) → coverage_by_framework
       ├── repo.update_scan_run_coverage(scan_run_id, coverage_by_framework)
       └── repo.update_scan_run_status(scan_run_id, "mapped")
```

### 9.3 Layered Call Stack: Manual Trigger Path

```
[HTTP Thread]
POST /v1/scans/{scan_run_id}/enrich
 └── enrich_scan_endpoint(scan_run_id, background_tasks, customer)
       ├── get_reference_db() → ref_db
       ├── ref_db.collection("scan_runs").get(scan_run_id) → run_doc
       ├── [tenant_id check] → 404 if mismatch
       ├── [status check] → 409 if not retriable
       ├── PipelineCoordinator(ref_db)
       └── background_tasks.add_task(coordinator.run_post_ingest_pipeline, ...)
 Response: 202

[Background Thread — identical to auto-trigger from PipelineCoordinator.run_post_ingest_pipeline() onwards]
```

### 9.4 Reference DB Edge Collections Accessed by Phase 1

| Collection | Access Type | Stage |
|---|---|---|
| `scan_findings` | Read + Update | All stages |
| `scan_runs` | Read + Update | All stages (status + coverage) |
| `detected_controls` | Read + Upsert | UC-007, UC-009 |
| `finding_triggers_req` | Upsert (edges) | UC-007 |
| `detected_control_maps_to` | Upsert (edges) | UC-007 |
| `vulnerabilities` | Read (reference graph) | UC-007 |
| `weaknesses` | Read (reference graph) | UC-007, UC-008 |
| `kev_entries` | Read (reference graph) | UC-007 |
| `epss_history` | Read (via `has_epss` edge traversal) | UC-007 |
| `oscal_controls` | Read (reference graph) | UC-009 |
| `scf_controls` | Read (reference graph) | UC-009 |
| `regulatory_requirements` | Read (reference graph) | UC-007, UC-009 |
| `has_weakness` | Traversal | UC-007 |
| `has_epss` | Traversal | UC-007 |
| `violates_requirement` | Traversal | UC-007 |
| `maps_to_requirement` | Traversal | UC-007, UC-008 |
| `child_of` | Traversal | UC-008 |
| `d3fend_counters_technique` | Traversal | UC-007 |
| `technique_exploits_weakness` | Traversal | UC-007 |

---

## 10. Data Models

### 10.1 `scan_findings` Document — Enrichment Fields (Phase 1 Additions)

All fields below are written by `EnrichmentPipeline._build_finding_updates()`. They do not exist on findings after Phase 0 ingestion. Absent fields (e.g., for findings without `cve_id`) remain absent — no null-padding.

```python
{
    # Existing Phase 0 fields (not modified by Phase 1 except enriched_at)
    "_key":          str,   # fingerprint (set at ingestion)
    "fingerprint":   str,
    "scan_run_id":   str,
    "tenant_id":     str,
    "cve_id":        Optional[str],
    "cwe_ids":       list[str],   # scanner-sourced (Phase 0)
    "severity":      str,
    "tool":          str,
    "triage_status": str,

    # Phase 1 enrichment additions (UC-007)
    "epss_score":        float,         # 0.0–1.0; absent if no CVE or CVE not in reference DB
    "epss_percentile":   float,         # 0.0–1.0; co-present with epss_score
    "in_kev":            bool,          # False if CVE not in kev_entries; absent if no CVE
    "cwe_chain":         list[str],     # ["CWE-79", "CWE-20"]; empty list if no CVE or no has_weakness edges
    "d3fend_techniques": list[str],     # ["D3-HBPI", ...]; empty list if no ATT&CK path
    "enriched_at":       str,           # ISO datetime; set on ALL findings (CVE or not)

    # Phase 1 compaction additions (UC-008)
    "risk_score":           float,      # [0.0, 1.0]; 0.0 for no-CVE findings
    "compaction_group_id":  str,        # resolved CWE key or "no_cwe_<fingerprint>"
    "cluster_rank":         int,        # 1-based; 1 = highest-risk cluster
    "compacted":            bool,       # True for duplicate findings; False for canonical
}
```

**Update sequence:** `enriched_at` is written by `EnrichmentPipeline`; `risk_score`, `compaction_group_id`, `cluster_rank`, `compacted` are written by `CompactionPipeline`.

**Idempotency:** All writes use `bulk_update_findings()` which issues AQL `UPDATE ... WITH ...`. Re-running produces identical values for deterministic inputs (same EPSS date, same KEV membership).

### 10.2 `detected_controls` Document — Control Mapping Fields (Phase 1 Additions)

Existing Phase 0 fields: `_key`, `fingerprint`, `scan_run_id`, `tenant_id`, `check_id`, `check_name`, `triage_status`.

Phase 1 adds:

```python
{
    # Phase 1 enrichment addition (UC-007, written by EnrichmentPipeline)
    "req_id":       str,    # regulatory_requirements._key that this control maps to; absent if not resolved

    # Phase 1 control mapping additions (UC-009, written by ControlMappingPipeline)
    "framework":        str,        # "NIST 800-53" | "ISO 27001" | "FDA 510(k)" | "IEC 62304" | "CRA"
    "evidence_chain":   list[str],  # [finding_id, cwe_id, req_id, control_id]; "" for unresolved elements
    "control_status":   str,        # "present" | "absent" | "partial" — Phase 1 default: "present"
}
```

### 10.3 `scan_runs` Document — Pipeline Fields (Phase 1 Additions)

Existing Phase 0 fields: `_key`, `status`, `finding_counts`, `compliance_score`, `tenant_id`, `created_at`, `completed_at`, `tools_invoked`, `audit_log`.

Phase 1 adds:

```python
{
    # Phase 1 status chain (written by repo.update_scan_run_status())
    "status": str,   # extended: "enriched" | "compacted" | "mapped" | "pipeline_failed" | "enrichment_pending"

    # Phase 1 enrichment timestamp (UC-007)
    "enriched_at": str,     # ISO datetime; set when status → "enriched"

    # Phase 1 coverage computation (UC-009)
    "coverage_by_framework": dict,   # {"NIST 800-53": 12.5, "ISO 27001": 0.0, ...}

    # Phase 1 failure field
    "pipeline_error": str,   # error message if status == "pipeline_failed"; absent on success
}
```

### 10.4 Edge Document Shapes

**`finding_triggers_req` edge (Phase 1 addition, source="cve_violates_req"):**
```python
{
    "_key":   str,   # generate_edge_key(fingerprint, req_key, "triggers_req")
    "_from":  "scan_findings/<fingerprint>",
    "_to":    "regulatory_requirements/<req_key>",
    "tenant_id": str,
    "source": "cve_violates_req",
}
```

**`detected_control_maps_to` edge (Phase 1 — supersedes stub):**
```python
{
    "_key":   str,   # generate_edge_key(control_key, req_key, "maps_to")
    "_from":  "detected_controls/<control_key>",
    "_to":    "regulatory_requirements/<req_key>",
    "tenant_id": str,
    "source": "enrichment_pipeline",
}
```

### 10.5 AQL Format Normalization Contract

`kev_entries.cve_id` uses dashed format (`CVE-2024-1234`). `scan_findings.cve_id` uses the same dashed format (ingestion-time validator at `IngestionEngine._validate()` enforces `CVE-\d{4}-\d{4,}`). ArangoDB `_key` fields cannot contain dashes, so `vulnerabilities._key` uses underscored format (`CVE_2024_1234`).

AQL in `aql_enrich_findings_batch()` must handle both:
- `DOCUMENT(CONCAT("vulnerabilities/", cve_key))` — uses underscore format as passed in
- `kev_entries` FILTER — uses dashed format: `REGEX_REPLACE(cve_key, "_", "-")`

Callers of `aql_enrich_findings_batch()` must pass `cve_keys` in **underscore format** (reference DB `_key` format). `EnrichmentPipeline._normalize_cve_to_key()` handles the conversion from `scan_findings.cve_id` (dashed) to key format (underscored).

---

## 11. Error Handling

### 11.1 Reference DB Unavailable at Pipeline Entry

**Detection:** `PipelineCoordinator._verify_reference_db()` — lightweight read attempt on `vulnerabilities` collection.

**Response:**
```python
scan_runs.status = "enrichment_pending"
scan_runs.pipeline_error = "reference_db_unavailable"
```

**Recovery:** Manual re-trigger via `POST /v1/scans/{scan_run_id}/enrich` once reference DB is available. `enrichment_pending` is in `RETRIABLE_STATUSES`.

### 11.2 Stage Failure (Unhandled Exception)

**Detection:** try/except around each pipeline stage `run()` call in `PipelineCoordinator.run_post_ingest_pipeline()`.

**Response:**
```python
scan_runs.status = "pipeline_failed"
scan_runs.pipeline_error = str(exception)
```

Partial writes from the failed stage are retained (not rolled back). This preserves partial enrichment data; re-running will overwrite with correct values once the error is resolved.

**Recovery:** Manual re-trigger via `POST /v1/scans/{scan_run_id}/enrich`. `pipeline_failed` is in `RETRIABLE_STATUSES`.

### 11.3 Individual Batch AQL Failure

**Detection:** try/except around `aql_enrich_findings_batch()`, `aql_get_cwe_parent_map()`, and `aql_resolve_control_framework()` in the repository layer.

**Response:** Log the error. If the failure is in the traversal query (not a network failure), return empty dict (`{}`). The pipeline continues; affected findings receive no enrichment for that batch. The error is logged with batch details.

**Rationale:** A malformed CVE key (e.g., custom scanner output) should not abort enrichment for the entire run. Partial enrichment is better than total failure.

### 11.4 Missing Reference Graph Data

These are not errors — they are expected data gaps handled silently:

| Scenario | Handling |
|---|---|
| CVE not in `vulnerabilities` collection | `epss_score`, `in_kev`, `cwe_chain`, `d3fend_techniques` all absent; `enriched_at` still set |
| CVE in `vulnerabilities` but no `has_epss` edge | `epss_score` absent |
| CVE has no `has_weakness` edge | `cwe_chain = []`, `d3fend_techniques = []` |
| CWE has no `maps_to_requirement` edge and no parent with one (traversal depth 5) | Finding compacts into `no_cwe` group; cluster_rank assigned |
| ATT&CK → D3FEND path does not exist | `d3fend_techniques = []` |
| `detected_controls` is empty for run | UC-009 returns `coverage_by_framework = {}`, status still transitions to `"mapped"` |

### 11.5 Idempotency Guarantee

All pipeline writes use:
- `import_bulk(on_duplicate="update")` for edges and detected_controls upserts
- `AQL UPDATE ... WITH ...` for scan_findings field updates (idempotent by `_key`)

Re-running any pipeline stage produces identical results for the same input data. Status transitions do not prevent re-run (status is checked at coordinator entry for idempotency skip; once a stage is skipped, its status is verified before proceeding to the next stage).

### 11.6 ArangoDB Transaction Size Limit (Risk-3)

All bulk operations involving `scan_findings` updates batch at `<= 500` documents per AQL transaction. The `ScanEnrichmentRepository.bulk_update_findings()` method enforces this internally by chunking the input list and issuing separate AQL calls per chunk.

### 11.7 Logging Contract

All pipeline stages log:
- Entry: `{stage}.started` with `scan_run_id`, `tenant_id`
- Per-batch: `{stage}.batch_processed` with batch index and counts
- Completion: `{stage}.completed` with total counts and elapsed_ms
- Error: `{stage}.failed` with exception type and message

Log format matches existing `structlog` usage in the codebase.

---

## 12. Use-Case Coverage Matrix

### 12.1 UC-007 Vulnerability Enrichment

| AC-ID | Criterion | Module Responsible | AQL / Method |
|---|---|---|---|
| AC-001 | EPSS score populated | `EnrichmentPipeline._build_finding_updates` | `aql_enrich_findings_batch` → `has_epss` traversal |
| AC-002 | KEV status populated | `EnrichmentPipeline._build_finding_updates` | `aql_enrich_findings_batch` → `kev_entries` FILTER |
| AC-003 | CWE chain populated | `EnrichmentPipeline._build_finding_updates` | `aql_enrich_findings_batch` → `has_weakness` traversal |
| AC-004 | D3FEND techniques linked | `EnrichmentPipeline._build_finding_updates` | `aql_enrich_findings_batch` → `technique_exploits_weakness` + `d3fend_counters_technique` |
| AC-005 | OSCAL/SCF controls upserted | `EnrichmentPipeline._build_detected_controls` | `aql_enrich_findings_batch` → `violates_requirement` path |
| AC-006 | `finding_triggers_req` edges created | `EnrichmentPipeline._build_req_edges` + `repo.upsert_finding_triggers_req_edges` | source="cve_violates_req" |
| AC-007 | `detected_control_maps_to` edges created | `EnrichmentPipeline._build_detected_control_maps_to_edges` + `repo.upsert_detected_control_maps_to_edges` | `import_bulk(on_duplicate="update")` |
| AC-008 | Findings without CVE skipped gracefully | `EnrichmentPipeline._build_finding_updates` | Checks `cve_id` before adding to cve_keys batch |
| AC-009 | Status transitions to `enriched` | `repo.update_scan_run_status(scan_run_id, "enriched")` | Called at end of `EnrichmentPipeline.run()` |
| AC-010 | Idempotent | `import_bulk(on_duplicate="update")` + AQL UPDATE | All writes are upsert-safe |

### 12.2 UC-008 Finding Compaction & Risk Scoring

| AC-ID | Criterion | Module Responsible | AQL / Method |
|---|---|---|---|
| AC-011 | CWE deduplication | `CompactionPipeline._assign_compaction_groups` | Group by resolved CWE key from `cwe_chain` |
| AC-012 | Duplicate suppression | `CompactionPipeline._assign_compaction_groups` | Canonical = first fingerprint by sort; rest get `compacted=True` |
| AC-013 | CWE roll-up | `CompactionPipeline.run` step 3 + `_assign_compaction_groups` | `aql_get_cwe_parent_map` → `child_of` traversal |
| AC-014 | Risk score formula | `CompactionPipeline._compute_risk_scores` | `cvss * 0.4 + epss * 0.3 + kev * 0.2 + exploit * 0.1` |
| AC-015 | Cluster ranking | `CompactionPipeline._compute_cluster_ranks` | Sort group max(risk_score) descending; assign rank 1-N |
| AC-016 | Status transitions to `compacted` | `repo.update_scan_run_status(scan_run_id, "compacted")` | Called at end of `CompactionPipeline.run()` |
| AC-017 | Idempotent | AQL UPDATE + deterministic group/rank computation | Same inputs produce same outputs |

### 12.3 UC-009 Control Mapping

| AC-ID | Criterion | Module Responsible | AQL / Method |
|---|---|---|---|
| AC-018 | Framework annotation | `ControlMappingPipeline._build_control_updates` | `aql_resolve_control_framework` lookup in `oscal_controls` / `scf_controls` |
| AC-019 | Evidence chain | `ControlMappingPipeline._build_evidence_chains` | AQL traversal: detected_control → finding_triggers_req → scan_findings |
| AC-020 | Coverage % by framework | `ControlMappingPipeline._compute_coverage` + `_get_total_reqs_by_framework` | Covered / total × 100 |
| AC-021 | Status transitions to `mapped` | `repo.update_scan_run_status(scan_run_id, "mapped")` | Called at end of `ControlMappingPipeline.run()` |
| AC-022 | Idempotent | `import_bulk(on_duplicate="update")` for controls; deterministic coverage formula | Idempotent |

### 12.4 Cross-Cutting

| AC-ID | Criterion | Module Responsible | Implementation |
|---|---|---|---|
| AC-023 | Auto-trigger after ingestion | `scan.py` endpoint modification | `background_tasks.add_task(coordinator.run_post_ingest_pipeline, ...)` after `result.status == "completed"` |
| AC-024 | Manual trigger API returns 202 | `pipeline.py` endpoint | `POST /v1/scans/{scan_run_id}/enrich` → 202 + BackgroundTask |
| AC-025 | Status polling | Existing `GET /v1/scan/{run_id}` endpoint | Returns `scan_runs.status` — no change needed; new status values are valid strings |
| AC-026 | Pipeline failure isolation | `PipelineCoordinator.run_post_ingest_pipeline()` | try/except per stage → `pipeline_failed` status; partial writes retained |
| AC-027 | Reference DB unavailable | `PipelineCoordinator._verify_reference_db()` | Sets `enrichment_pending` with retriable flag |
| AC-028 | tenant_id scoping | `ScanEnrichmentRepository.fetch_findings_for_run()` + `fetch_detected_controls_for_run()` | All AQL FILTERs include `tenant_id == @tenant_id` |

### 12.5 Requirement → Module Traceability

| Requirement | Use Case | Primary Module | Repository Method |
|---|---|---|---|
| REQ-001 | UC-007 | `EnrichmentPipeline` | `aql_enrich_findings_batch`, `bulk_update_findings`, `upsert_finding_triggers_req_edges`, `upsert_detected_control_maps_to_edges`, `bulk_upsert_detected_controls` |
| REQ-002 | UC-008 | `CompactionPipeline` | `fetch_findings_for_run`, `aql_get_cwe_parent_map`, `bulk_update_findings` |
| REQ-003 | UC-009 | `ControlMappingPipeline` | `fetch_detected_controls_for_run`, `aql_resolve_control_framework`, `bulk_upsert_detected_controls`, `update_scan_run_coverage` |

---

## Appendix A: Risk Register

| Risk ID | Description | Mitigation |
|---|---|---|
| Risk-1 | `kev_entries.cve_id` uses dashes; `vulnerabilities._key` uses underscores | `aql_enrich_findings_batch` applies `REGEX_REPLACE(cve_key, "_", "-")` for KEV FILTER; all callers pass underscore-format keys |
| Risk-2 | Many CVEs have no ATT&CK/D3FEND mapping → empty traversal | Empty traversal returns empty list; pipeline continues; `d3fend_techniques=[]` is a valid state |
| Risk-3 | Bulk AQL update transaction size limit | `bulk_update_findings()` chunks at 500; `fetch_findings_for_run()` yields batches at 500 |
| Risk-4 | `oscal_controls` / `scf_controls` not populated → zero detected_controls coverage | Zero detected_controls is valid; coverage_by_framework returns zeros; status still transitions to mapped |

---

## Appendix B: Out-of-Scope Decisions (Phase 1)

These items were considered and explicitly deferred:

| Item | Deferred To |
|---|---|
| LLM-based enrichment (probabilistic CWE→req mapping) | Phase 2 |
| Blast radius simulation | Phase 2 |
| EPSS velocity / trending detection | Phase 2 |
| Backfill of scan_runs created before Phase 1 deployment | Phase 2 (or manual operational task) |
| Separate Celery/worker process for pipeline | Phase 2 (FastAPI BackgroundTasks sufficient for Phase 1 scale) |
| Streaming cluster rank for > 5000 findings | Phase 2 |
| Exact exploit count in risk formula (d3fend as proxy for Phase 1) | Phase 2 |
| `vex_documents` integration with enriched findings | Phase 2 |

---

*Document complete. Sufficient detail for runtime call stack derivation (Stage 4).*
