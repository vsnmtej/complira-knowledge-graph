# Future-State Runtime Call Stack
# Core Pipeline Phase 1 — Three-Stage Post-Ingestion Intelligence Pipeline

**Ticket:** `core-pipeline-phase-1`
**Document Type:** To-Be Execution Model
**Derived From:** `proposed-design.md` (2026-03-21)
**Status:** Design
**Author:** Claude Code (claude-sonnet-4-6)
**Date:** 2026-03-21

> **Scope note:** This document describes the future-state runtime execution model.
> It is NOT a trace of current code. Every call stack below is derived entirely from
> the proposed design. No frame in this document exists in the current codebase.

---

## Architectural Boundary Key

```
[HTTP]          src/api/v1/endpoints/
[ORCHESTRATOR]  src/complira_graph/ingestion/pipeline_coordinator.py
[PIPELINE]      src/complira_graph/ingestion/{enrichment,compaction,control_mapping}_pipeline.py
[REPOSITORY]    src/complira_graph/ingestion/scan_enrichment_repository.py
                src/complira_graph/ingestion/repositories.py  (existing, reused)
                src/complira_graph/ingestion/edge_service.py  (existing, reused)
[DB]            ArangoDB reference DB (StandardDatabase via src/api/core/database.py)
```

Notation:
- `await` — async suspension point (coroutine boundary)
- `→ DB WRITE` — document insert or update committed to ArangoDB
- `→ DB READ` — AQL query or document fetch from ArangoDB
- `[IF]` — decision gate; branch taken is labelled
- `[TRANSFORM]` — in-memory data transformation (no I/O)
- `[STATE]` — scan_runs.status mutation

---

## UC-007-PRIMARY: Enrichment Pipeline — Happy Path

**Source Type:** Requirement
**Requirement Reference:** REQ-001
**Coverage:** Primary

**Trigger:** `POST /v1/scans/{scan_run_id}/enrich` (manual) OR auto-trigger BackgroundTask
after `POST /v1/scan/ingest` completes with `status="completed"`.

**Preconditions:**
- `scan_runs.status == "completed"`
- Reference DB reachable
- `scan_findings` populated for `scan_run_id` (at least one finding with `cve_id`)

**Status transition:** `completed → enriched`

```
══════════════════════════════════════════════════════════════════════════
[HTTP THREAD]  src/api/v1/endpoints/pipeline.py
══════════════════════════════════════════════════════════════════════════

pipeline.py:enrich_scan_endpoint(scan_run_id, background_tasks, customer)
  │
  ├── database.py:get_reference_db()
  │     → DB READ  (connection handle; no query)
  │     → ref_db: StandardDatabase
  │
  ├── ref_db.collection("scan_runs").get(scan_run_id)
  │     → DB READ  ArangoDB document fetch: scan_runs/{scan_run_id}
  │     → run_doc: {status, tenant_id, ...}
  │
  ├── [IF] run_doc is None OR run_doc["tenant_id"] != customer.id
  │     → raise HTTPException(404)                             [EXIT — not this path]
  │
  ├── [IF] run_doc["status"] not in RETRIABLE_STATUSES
  │     → raise HTTPException(409)                             [EXIT — not this path]
  │     RETRIABLE_STATUSES = {"completed","enriched","compacted",
  │                           "pipeline_failed","enrichment_pending"}
  │
  ├── [TRANSFORM] PipelineCoordinator(ref_db)
  │     → coordinator instance (no I/O; wires sub-services)
  │
  └── background_tasks.add_task(
            coordinator.run_post_ingest_pipeline,
            scan_run_id=scan_run_id,
            tenant_id=customer.id
        )
      → Response: 202 {"scan_run_id": ..., "message": "enrichment queued"}

══════════════════════════════════════════════════════════════════════════
[BACKGROUND TASK — after HTTP 202 response sent]
══════════════════════════════════════════════════════════════════════════

orchestrator.py:PipelineCoordinator.run_post_ingest_pipeline(scan_run_id, tenant_id)
  │
  ├── orchestrator.py:PipelineCoordinator._verify_reference_db()
  │     → DB READ  ref_db.collection("vulnerabilities").get(<any_doc>)
  │     → True                                   [reference DB reachable — this path]
  │
  ├── orchestrator.py:PipelineCoordinator._get_run_status(scan_run_id)
  │     → DB READ  ref_db.collection("scan_runs").get(scan_run_id)["status"]
  │     → "completed"
  │
  ├── [IF] status == "completed"  → proceed to EnrichmentPipeline.run()
  │
  │  ┌─────────────────────────────────────────────────────────────────
  │  │  [PIPELINE BOUNDARY]  enrichment_pipeline.py:EnrichmentPipeline.run()
  │  └─────────────────────────────────────────────────────────────────
  │
  └── enrichment_pipeline.py:EnrichmentPipeline.run(scan_run_id, tenant_id)
        │
        │  ════════ BATCH LOOP (batch_size=500) ════════
        │
        ├── scan_enrichment_repository.py:ScanEnrichmentRepository.fetch_findings_for_run(
        │       scan_run_id, tenant_id, batch_size=500
        │   )
        │     → DB READ  AQL:
        │         FOR f IN scan_findings
        │           FILTER f.scan_run_id == @run_id
        │             AND f.tenant_id == @tenant_id
        │           LIMIT @offset, 500
        │           RETURN f
        │     → Iterator[list[dict]]  (yields one batch of ≤500 findings)
        │
        │  ── FOR EACH BATCH ──────────────────────────────────────────
        │
        ├── [TRANSFORM] enrichment_pipeline.py:EnrichmentPipeline._normalize_cve_to_key()
        │     Input:  batch[i]["cve_id"]  (dashed format: "CVE-2024-1234", nullable)
        │     [IF] cve_id is None → skip; finding added to no-cve list
        │     [IF] cve_id present → "CVE-2024-1234" → "CVE_2024_1234"
        │     → cve_keys: list[str]  (underscore format, deduplicated across batch)
        │
        ├── scan_enrichment_repository.py:ScanEnrichmentRepository.aql_enrich_findings_batch(
        │       cve_keys
        │   )
        │     → DB READ  AQL traversal (single round-trip for entire batch):
        │         FOR cve_key IN @cve_keys
        │           LET cve_doc = DOCUMENT(CONCAT("vulnerabilities/", cve_key))
        │           LET epss = FIRST(
        │             FOR e IN 1..1 OUTBOUND cve_doc has_epss
        │             SORT e.score_date DESC LIMIT 1 RETURN e
        │           )
        │           LET in_kev = (LENGTH(
        │             FOR k IN kev_entries
        │             FILTER k.cve_id == REGEX_REPLACE(cve_key, "_", "-") LIMIT 1 RETURN 1
        │           ) > 0)
        │           LET cwes = (
        │             FOR w IN 1..1 OUTBOUND cve_doc has_weakness RETURN w.cwe_id
        │           )
        │           LET req_keys = (
        │             FOR req IN 1..2 OUTBOUND cve_doc
        │               violates_requirement, maps_to_requirement
        │             RETURN DISTINCT req._key
        │           )
        │           LET attack_techs = (
        │             FOR w IN 1..1 OUTBOUND cve_doc has_weakness
        │               FOR t IN 1..1 INBOUND w technique_exploits_weakness
        │               RETURN DISTINCT t._key
        │           )
        │           LET d3fend = (
        │             FOR tech IN attack_techs
        │               FOR d IN 1..1 INBOUND DOCUMENT(CONCAT("attack_techniques/", tech))
        │                 d3fend_counters_technique
        │               RETURN DISTINCT d.d3fend_id
        │           )
        │           RETURN {cve_key, epss_score, epss_percentile, in_kev,
        │                   cwe_chain: cwes, d3fend_techniques: d3fend, req_keys}
        │     → enrichment_map: dict[str, dict]
        │         {"CVE_2024_1234": {epss_score: 0.23, in_kev: false,
        │                            cwe_chain: ["CWE-79"], req_keys: ["REQ_NIST_SI-3"], ...}}
        │
        ├── [TRANSFORM] enrichment_pipeline.py:EnrichmentPipeline._build_finding_updates(
        │       batch, enrichment_map
        │   )
        │     For each finding in batch:
        │       [IF] cve_id present AND cve_key in enrichment_map:
        │            merge: epss_score, epss_percentile, in_kev,
        │                   cwe_chain, d3fend_techniques
        │       Always append: enriched_at = utcnow().isoformat()
        │     → updates: list[{"_key": fingerprint, epss_score, ..., enriched_at}]
        │
        ├── scan_enrichment_repository.py:ScanEnrichmentRepository.bulk_update_findings(updates)
        │     → DB WRITE  AQL (batches internally at 500):
        │         FOR update IN @updates
        │           UPDATE update._key WITH update IN scan_findings
        │     Fields written to scan_findings:
        │       epss_score, epss_percentile, in_kev, cwe_chain,
        │       d3fend_techniques, enriched_at
        │
        ├── [TRANSFORM] enrichment_pipeline.py:EnrichmentPipeline._build_req_edges(
        │       batch, enrichment_map, tenant_id
        │   )
        │     For each finding with cve_id and req_keys in enrichment_map:
        │       Build edge dict per req_key:
        │         _key:    generate_edge_key(fingerprint, req_key, "triggers_req")
        │         _from:   "scan_findings/<fingerprint>"
        │         _to:     "regulatory_requirements/<req_key>"
        │         tenant_id: tenant_id
        │         source:  "cve_violates_req"
        │     Deduplicate by _key
        │     → req_edges: list[dict]
        │
        ├── scan_enrichment_repository.py:ScanEnrichmentRepository.upsert_finding_triggers_req_edges(
        │       req_edges
        │   )
        │     → DB WRITE  db.collection("finding_triggers_req")
        │                   .import_bulk(req_edges, on_duplicate="update")
        │
        ├── [TRANSFORM] enrichment_pipeline.py:EnrichmentPipeline._build_detected_controls(
        │       batch, enrichment_map, tenant_id
        │   )
        │     For each (finding, req_key) pair in enrichment_map:
        │       Build detected_control doc:
        │         _key:    generate_edge_key(scan_run_id, req_key, "ctrl")
        │         scan_run_id, tenant_id
        │         req_id:  req_key
        │         check_id, check_name (from finding)
        │         triage_status: "compliant"
        │     → control_docs: list[dict]
        │
        ├── scan_enrichment_repository.py:ScanEnrichmentRepository.bulk_upsert_detected_controls(
        │       control_docs
        │   )
        │     → DB WRITE  db.collection("detected_controls")
        │                   .import_bulk(control_docs, on_duplicate="update")
        │
        ├── [TRANSFORM] enrichment_pipeline.py:EnrichmentPipeline._build_detected_control_maps_to_edges(
        │       control_docs, tenant_id
        │   )
        │     For each control_doc:
        │       Build edge dict:
        │         _key:    generate_edge_key(control_key, req_key, "maps_to")
        │         _from:   "detected_controls/<control_key>"
        │         _to:     "regulatory_requirements/<req_key>"
        │         tenant_id: tenant_id
        │         source:  "enrichment_pipeline"
        │     → ctrl_edges: list[dict]
        │
        ├── scan_enrichment_repository.py:ScanEnrichmentRepository.upsert_detected_control_maps_to_edges(
        │       ctrl_edges
        │   )
        │     → DB WRITE  db.collection("detected_control_maps_to")
        │                   .import_bulk(ctrl_edges, on_duplicate="update")
        │
        │  ── END BATCH LOOP (repeat for each 500-finding batch) ──────
        │
        └── scan_enrichment_repository.py:ScanEnrichmentRepository.update_scan_run_status(
                scan_run_id, "enriched", extra_fields={"enriched_at": utcnow().isoformat()}
            )
              → DB WRITE  AQL UPDATE scan_runs/{scan_run_id}
                          WITH {status: "enriched", enriched_at: ..., updated_at: ...}
              [STATE]  scan_runs.status: "completed" → "enriched"
```

---

## UC-007-FALLBACK: Enrichment — Reference DB Unavailable

**Source Type:** Requirement
**Requirement Reference:** REQ-001, AC-027
**Coverage:** Fallback

**Trigger:** Same as UC-007-PRIMARY.
**Precondition:** Reference DB unreachable (network timeout, ArangoDB down).
**Status transition:** `completed → enrichment_pending`

```
══════════════════════════════════════════════════════════════════════════
[HTTP THREAD]  src/api/v1/endpoints/pipeline.py
══════════════════════════════════════════════════════════════════════════

pipeline.py:enrich_scan_endpoint(scan_run_id, background_tasks, customer)
  │
  │  [HTTP thread proceeds identically to UC-007-PRIMARY]
  │  202 response sent; BackgroundTask enqueued.
  │
══════════════════════════════════════════════════════════════════════════
[BACKGROUND TASK]
══════════════════════════════════════════════════════════════════════════

orchestrator.py:PipelineCoordinator.run_post_ingest_pipeline(scan_run_id, tenant_id)
  │
  ├── orchestrator.py:PipelineCoordinator._verify_reference_db()
  │     → DB READ ATTEMPT  ref_db.collection("vulnerabilities").get(<any_doc>)
  │     → ArangoConnectionError / ArangoServerError raised
  │     → returns False
  │
  ├── [IF] _verify_reference_db() returns False → FALLBACK PATH
  │
  ├── scan_enrichment_repository.py:ScanEnrichmentRepository.update_scan_run_status(
  │       scan_run_id,
  │       "enrichment_pending",
  │       extra_fields={"pipeline_error": "reference_db_unavailable"}
  │   )
  │     → DB WRITE  AQL UPDATE scan_runs/{scan_run_id}
  │                 WITH {status: "enrichment_pending",
  │                       pipeline_error: "reference_db_unavailable",
  │                       updated_at: ...}
  │     [STATE]  scan_runs.status: "completed" → "enrichment_pending"
  │
  └── return  (EnrichmentPipeline.run() never called)

Recovery path (after reference DB is restored):
  POST /v1/scans/{scan_run_id}/enrich
    "enrichment_pending" is in RETRIABLE_STATUSES → UC-007-PRIMARY executes
```

---

## UC-007-EDGE: Enrichment — Findings With No CVE ID

**Source Type:** Requirement
**Requirement Reference:** REQ-001, AC-008
**Coverage:** Error / Edge

**Trigger:** Same as UC-007-PRIMARY, but at least one finding in the batch has `cve_id == null`.
**Behaviour:** Null-CVE findings are skipped for enrichment field population;
`enriched_at` is still written to all findings.

```
══════════════════════════════════════════════════════════════════════════
[BACKGROUND TASK — diverges at EnrichmentPipeline batch processing]
══════════════════════════════════════════════════════════════════════════

enrichment_pipeline.py:EnrichmentPipeline.run(scan_run_id, tenant_id)
  │
  ├── scan_enrichment_repository.py:ScanEnrichmentRepository.fetch_findings_for_run(...)
  │     → DB READ  (batch contains mix: some findings with cve_id, some without)
  │
  │  ── BATCH PROCESSING (focus on null-CVE path) ──────────────────────
  │
  ├── [TRANSFORM] EnrichmentPipeline._normalize_cve_to_key()
  │     For finding A: cve_id = "CVE-2024-1234" → cve_key = "CVE_2024_1234"  (added to batch)
  │     For finding B: cve_id = None
  │       [IF] cve_id is None → SKIP  (finding B not added to cve_keys list)
  │     → cve_keys = ["CVE_2024_1234"]  (finding B absent)
  │
  ├── scan_enrichment_repository.py:ScanEnrichmentRepository.aql_enrich_findings_batch(
  │       cve_keys=["CVE_2024_1234"]
  │   )
  │     → DB READ  AQL traversal (finding B never queried)
  │     → enrichment_map = {"CVE_2024_1234": {...}}
  │                          (no entry for finding B — by design)
  │
  ├── [TRANSFORM] EnrichmentPipeline._build_finding_updates(batch, enrichment_map)
  │     For finding A (cve_id present, key in enrichment_map):
  │       update = {_key: A._key, epss_score: ..., in_kev: ..., cwe_chain: [...],
  │                 d3fend_techniques: [...], enriched_at: utcnow()}
  │     For finding B (cve_id absent):
  │       [IF] cve_id is None → enrich fields NOT set
  │       update = {_key: B._key, enriched_at: utcnow()}
  │                 (enriched_at written; no enrichment fields)
  │     → updates: [{_key: A._key, epss_score, ...enriched_at},
  │                 {_key: B._key, enriched_at}]
  │
  ├── scan_enrichment_repository.py:ScanEnrichmentRepository.bulk_update_findings(updates)
  │     → DB WRITE  Both findings updated; finding B gets only enriched_at
  │
  ├── [TRANSFORM] EnrichmentPipeline._build_req_edges(batch, enrichment_map, tenant_id)
  │     For finding A: req_edges built (has req_keys in enrichment_map)
  │     For finding B: cve_id None → no entry in enrichment_map → no req_edges
  │     → req_edges = [{...finding A edges only...}]
  │
  ├── scan_enrichment_repository.py:ScanEnrichmentRepository.upsert_finding_triggers_req_edges(
  │       req_edges
  │   )
  │     → DB WRITE  Only finding A edges written; finding B produces no edges
  │
  ├── [TRANSFORM] EnrichmentPipeline._build_detected_controls(...)
  │     → control_docs for finding A only; finding B produces no detected_controls
  │
  ├── scan_enrichment_repository.py:ScanEnrichmentRepository.bulk_upsert_detected_controls(...)
  │     → DB WRITE  (finding A controls only)
  │
  ├── [TRANSFORM] EnrichmentPipeline._build_detected_control_maps_to_edges(...)
  │     → ctrl_edges for finding A only
  │
  ├── scan_enrichment_repository.py:ScanEnrichmentRepository.upsert_detected_control_maps_to_edges(...)
  │     → DB WRITE  (finding A edges only)
  │
  │  ── END BATCH (finding B silently skipped for all enrichment fields) ──
  │
  └── scan_enrichment_repository.py:ScanEnrichmentRepository.update_scan_run_status(
          scan_run_id, "enriched", {"enriched_at": utcnow()}
      )
        → DB WRITE  status → "enriched"
        [STATE]  scan_runs.status: "completed" → "enriched"

Key invariant: enriched_at is written to ALL findings regardless of cve_id.
               Enrichment fields (epss_score, in_kev, cwe_chain, d3fend_techniques)
               are absent (not null) on findings where cve_id was None.
```

---

## MUC-4: Partial Batch Failure Mid-Enrichment (Write Error on Non-First Batch)

**Source Type:** Design-Risk
**Requirement Reference:** REQ-001, AC-026
**Coverage:** Error / Partial Failure

**Scenario:** A scan_run has 1500 findings (3 batches of 500). Batches 1 and 2 of
`EnrichmentPipeline.run()` complete successfully. During batch 3, `bulk_update_findings()`
raises `ArangoServerError` (e.g., write timeout or server-side error).

**Preconditions:**
- `scan_run.status == "completed"`
- Reference DB reachable (`UC-007-FALLBACK` does not apply)
- Batches 1 and 2 have been successfully written to `scan_findings` and edge collections

```
══════════════════════════════════════════════════════════════════════════
[BACKGROUND TASK — EnrichmentPipeline.run(), batch 3 of 3]
══════════════════════════════════════════════════════════════════════════

enrichment_pipeline.py:EnrichmentPipeline.run(scan_run_id, tenant_id)
  │
  │  [Batches 1 and 2 complete successfully — enrichment fields + edges written]
  │
  │  ── BATCH 3 (final batch) ──────────────────────────────────────────
  │
  ├── scan_enrichment_repository.py:ScanEnrichmentRepository.fetch_findings_for_run(...)
  │     → DB READ  (batch 3 of 3 fetched successfully)
  │
  ├── [TRANSFORM] EnrichmentPipeline._normalize_cve_to_key() → cve_keys
  │
  ├── scan_enrichment_repository.py:ScanEnrichmentRepository.aql_enrich_findings_batch(cve_keys)
  │     → DB READ  (traversal succeeds)
  │     → enrichment_map: dict
  │
  ├── [TRANSFORM] EnrichmentPipeline._build_finding_updates(batch_3, enrichment_map) → updates
  │
  ├── scan_enrichment_repository.py:ScanEnrichmentRepository.bulk_update_findings(updates)
  │     → DB WRITE  FAILS  → ArangoServerError raised
  │     (Exception propagates; no batch-level try/except in EnrichmentPipeline)
  │
  └── Exception propagates out of EnrichmentPipeline.run()
        (stage-level exception; caught by PipelineCoordinator)

══════════════════════════════════════════════════════════════════════════
[COORDINATOR catches stage-level exception]
══════════════════════════════════════════════════════════════════════════

orchestrator.py:PipelineCoordinator.run_post_ingest_pipeline(scan_run_id, tenant_id)
  │
  ├── try:
  │     EnrichmentPipeline.run(...)   ← raises ArangoServerError at batch 3
  │   except Exception as e:
  │     scan_enrichment_repository.py:ScanEnrichmentRepository.update_scan_run_status(
  │         scan_run_id, "pipeline_failed",
  │         {"pipeline_error": str(e)}
  │     )
  │     → DB WRITE  AQL UPDATE scan_runs/{scan_run_id}
  │                 WITH {status: "pipeline_failed", pipeline_error: <error_msg>}
  │     [STATE]  scan_runs.status: "completed" → "pipeline_failed"
  │
  └── return  (CompactionPipeline and ControlMappingPipeline NOT called)

Partial DB state after failure:
  - scan_findings batch 1 (findings 1–500):   enriched fields written
  - scan_findings batch 2 (findings 501–1000): enriched fields written
  - scan_findings batch 3 (findings 1001–1500): NOT written (still Phase 0 state)
  - finding_triggers_req edges (batches 1+2):  created
  - detected_controls (batches 1+2):           upserted
  - detected_control_maps_to edges (batches 1+2): created
  - scan_run.status:         "pipeline_failed"
  - scan_run.pipeline_error: <ArangoServerError message>

Recovery path:
  POST /v1/scans/{scan_run_id}/enrich
    "pipeline_failed" is in RETRIABLE_STATUSES.
    PipelineCoordinator restarts from UC-007 beginning.
    Batches 1 and 2 re-written idempotently (AQL UPDATE by _key; no data corruption).
    Batch 3 written on re-run.
    Pipeline completes normally: status → "enriched" → "compacted" → "mapped".

Design-Safety verdict: SAFE.
  Partial writes are retained and are idempotent on re-run.
  No rollback is performed (partial enrichment is better than total data loss).
  Re-trigger from "pipeline_failed" produces complete, correct enrichment.
  No duplicate documents or edges (import_bulk on_duplicate="update" + AQL UPDATE by _key).
```

---

## UC-008-PRIMARY: Compaction Pipeline — Happy Path

**Source Type:** Requirement
**Requirement Reference:** REQ-002
**Coverage:** Primary

**Trigger:** Auto-trigger after UC-007 completes (`scan_runs.status == "enriched"`).
Called sequentially by `PipelineCoordinator.run_post_ingest_pipeline()` immediately
after `EnrichmentPipeline.run()` returns.

**Status transition:** `enriched → compacted`

```
══════════════════════════════════════════════════════════════════════════
[BACKGROUND TASK — continuing from UC-007-PRIMARY, inside PipelineCoordinator]
══════════════════════════════════════════════════════════════════════════

orchestrator.py:PipelineCoordinator.run_post_ingest_pipeline(scan_run_id, tenant_id)
  │
  │  [EnrichmentPipeline.run() has already returned; status is now "enriched"]
  │
  └── compaction_pipeline.py:CompactionPipeline.run(scan_run_id, tenant_id)
        │
        │  ════════ ACCUMULATE ALL FINDINGS ════════
        │  (CompactionPipeline needs global view for cluster ranking)
        │
        ├── scan_enrichment_repository.py:ScanEnrichmentRepository.fetch_findings_for_run(
        │       scan_run_id, tenant_id, batch_size=500
        │   )
        │     → DB READ  AQL batched reads; all batches accumulated into all_findings
        │         FOR f IN scan_findings
        │           FILTER f.scan_run_id == @run_id AND f.tenant_id == @tenant_id
        │           LIMIT @offset, 500
        │           RETURN f
        │     → all_findings: list[dict]  (full list, all batches merged in memory)
        │
        ├── [TRANSFORM] CompactionPipeline._collect_cwe_keys(all_findings)
        │     Flatten all_findings[i]["cwe_chain"] lists → deduplicated cwe_keys
        │     Convert CWE IDs to ArangoDB _key format (e.g. "CWE_79")
        │     → cwe_keys: list[str]
        │
        ├── scan_enrichment_repository.py:ScanEnrichmentRepository.aql_get_cwe_parent_map(
        │       cwe_keys
        │   )
        │     → DB READ  AQL traversal:
        │         FOR cwe_key IN @cwe_keys
        │           LET has_req = LENGTH(
        │             FOR req IN 1..1 OUTBOUND DOCUMENT(CONCAT("weaknesses/", cwe_key))
        │               maps_to_requirement RETURN 1
        │           ) > 0
        │           LET parent = (
        │             FILTER !has_req
        │             FOR p IN 1..5 OUTBOUND DOCUMENT(CONCAT("weaknesses/", cwe_key))
        │               child_of
        │             FILTER LENGTH(
        │               FOR r IN 1..1 OUTBOUND p maps_to_requirement RETURN 1
        │             ) > 0
        │             LIMIT 1
        │             RETURN p._key
        │           )
        │           RETURN {cwe_key, resolved: has_req ? cwe_key : FIRST(parent)}
        │     → cwe_parent_map: dict[str, str]
        │         {"CWE_79": "CWE_79",          ← self (has direct maps_to_requirement)
        │          "CWE_20": "CWE_20",
        │          "CWE_117": "CWE_116"}         ← rolled up to parent
        │
        ├── [TRANSFORM] compaction_pipeline.py:CompactionPipeline._assign_compaction_groups(
        │       all_findings, cwe_parent_map
        │   )
        │     For each finding:
        │       [IF] cwe_chain non-empty:
        │            resolved_cwe = cwe_parent_map.get(cwe_chain[0], cwe_chain[0])
        │            group_id = resolved_cwe
        │       [IF] cwe_chain empty:
        │            group_id = "no_cwe_<fingerprint>"
        │     Within each group: sort by fingerprint → first = canonical (compacted=False)
        │                                               rest = duplicates (compacted=True)
        │     → group_map: dict[str, str]  {fingerprint → compaction_group_id}
        │
        ├── [TRANSFORM] compaction_pipeline.py:CompactionPipeline._compute_risk_scores(
        │       all_findings
        │   )
        │     For each finding:
        │       cvss_normalized = (finding.get("cvss_base") or 0.0) / 10.0
        │       epss            = finding.get("epss_score") or 0.0
        │       kev_bonus       = 1.0 if finding.get("in_kev") else 0.0
        │       exploit_bonus   = 0.1 if finding.get("d3fend_techniques") else 0.0
        │       risk_score      = cvss_normalized*0.4 + epss*0.3 + kev_bonus*0.2 + exploit_bonus*0.1
        │       [IF] finding has no cve_id → risk_score = 0.0
        │     → risk_score_map: dict[str, float]  {fingerprint → risk_score}
        │
        ├── [TRANSFORM] compaction_pipeline.py:CompactionPipeline._compute_cluster_ranks(
        │       all_findings, group_map, risk_score_map
        │   )
        │     Per group: max_risk = max(risk_score_map[f] for f in group)
        │     Sort groups by max_risk descending; ties broken by group_id alphabetically
        │     Assign rank 1..N to groups; all findings in group get the group's rank
        │     → rank_map: dict[str, int]  {fingerprint → cluster_rank}
        │
        ├── [TRANSFORM] compaction_pipeline.py:CompactionPipeline._build_compaction_updates(
        │       all_findings, group_map, risk_score_map, rank_map
        │   )
        │     For each finding:
        │       update = {
        │         _key:                finding["_key"],
        │         risk_score:          risk_score_map[fingerprint],
        │         compaction_group_id: group_map[fingerprint],
        │         cluster_rank:        rank_map[fingerprint],
        │         compacted:           fingerprint != canonical_in_group
        │       }
        │     → updates: list[dict]  (len == len(all_findings))
        │
        ├── scan_enrichment_repository.py:ScanEnrichmentRepository.bulk_update_findings(updates)
        │     [NOTE] bulk_update_findings() chunks internally at 500 per AQL call
        │     → DB WRITE  (multiple AQL calls if > 500 findings):
        │         FOR update IN @updates_chunk
        │           UPDATE update._key WITH update IN scan_findings
        │     Fields written: risk_score, compaction_group_id, cluster_rank, compacted
        │
        └── scan_enrichment_repository.py:ScanEnrichmentRepository.update_scan_run_status(
                scan_run_id, "compacted"
            )
              → DB WRITE  AQL UPDATE scan_runs/{scan_run_id}
                          WITH {status: "compacted", updated_at: ...}
              [STATE]  scan_runs.status: "enriched" → "compacted"
```

---

## UC-008-EDGE: Compaction — All Findings in One CWE Group

**Source Type:** Design-Risk
**Risk Reference:** Risk-3 (bulk AQL transaction size limit)
**Coverage:** Error / Edge

**Scenario:** 100 findings all share `cwe_chain = ["CWE-79"]` (e.g., XSS findings from a
web scanner). After alias deduplication and parent roll-up they all resolve to the same
`compaction_group_id = "CWE_79"`. The question is whether `bulk_update_findings()` stays
within the 500-document batch limit when flushing all 100 (or more) updates.

```
══════════════════════════════════════════════════════════════════════════
[BACKGROUND TASK — CompactionPipeline.run(), diverges at _assign_compaction_groups]
══════════════════════════════════════════════════════════════════════════

compaction_pipeline.py:CompactionPipeline.run(scan_run_id, tenant_id)
  │
  ├── [ACCUMULATE] fetch_findings_for_run() → all_findings (100 findings)
  │
  ├── aql_get_cwe_parent_map(["CWE_79"]) → {"CWE_79": "CWE_79"}
  │
  ├── [TRANSFORM] _assign_compaction_groups(all_findings, {"CWE_79": "CWE_79"})
  │     All 100 findings → group_id = "CWE_79"
  │     Sort by fingerprint → findings[0] = canonical (compacted=False)
  │                            findings[1..99] = duplicates (compacted=True)
  │     → group_map: {fp_0: "CWE_79", fp_1: "CWE_79", ..., fp_99: "CWE_79"}
  │
  ├── [TRANSFORM] _compute_risk_scores(all_findings) → risk_score_map (100 entries)
  │
  ├── [TRANSFORM] _compute_cluster_ranks(...)
  │     Single group "CWE_79" → max_risk = max(risk_score_map.values())
  │     One group → rank = 1 for all findings
  │     → rank_map: {fp_0: 1, ..., fp_99: 1}
  │
  ├── [TRANSFORM] _build_compaction_updates(...) → updates (100 dicts)
  │
  └── scan_enrichment_repository.py:ScanEnrichmentRepository.bulk_update_findings(updates)
        │
        │  [SAFETY CHECK — internal to bulk_update_findings()]
        │
        ├── [IF] len(updates) <= 500 → single AQL call                [THIS PATH: 100 ≤ 500]
        │     → DB WRITE  single AQL:
        │         FOR update IN @updates  (100 docs)
        │           UPDATE update._key WITH update IN scan_findings
        │     → all 100 findings updated in one transaction; within limit
        │
        ├── [IF] len(updates) > 500 → chunk into ceil(N/500) AQL calls
        │     Example: 600 findings in CWE-79 group →
        │       Chunk 1: updates[0:500]  → AQL call 1  → DB WRITE
        │       Chunk 2: updates[500:600] → AQL call 2  → DB WRITE
        │     Each chunk is a separate AQL transaction; no single call exceeds 500 docs.
        │
        └── [STATE outcome] All findings in the single CWE group receive:
              compaction_group_id = "CWE_79"
              cluster_rank        = 1
              compacted           = True (all except fingerprint-sorted first)
              risk_score          = computed per-finding

Design-Risk verdict: SAFE.
  bulk_update_findings() enforces ≤500 per AQL call regardless of group distribution.
  A single CWE group containing all findings is handled correctly because the batch
  boundary is on the update list length, not on the group count.
  100-finding single-group scenario: 1 AQL call (well within limit).
  Pathological case (600 findings, one CWE): 2 AQL calls (chunks enforced internally).
```

---

## UC-009-PRIMARY: Control Mapping Pipeline — Happy Path

**Source Type:** Requirement
**Requirement Reference:** REQ-003
**Coverage:** Primary

**Trigger:** Auto-trigger after UC-008 completes (`scan_runs.status == "compacted"`).
Called sequentially by `PipelineCoordinator.run_post_ingest_pipeline()` immediately
after `CompactionPipeline.run()` returns.

**Status transition:** `compacted → mapped`

```
══════════════════════════════════════════════════════════════════════════
[BACKGROUND TASK — continuing from UC-008-PRIMARY, inside PipelineCoordinator]
══════════════════════════════════════════════════════════════════════════

orchestrator.py:PipelineCoordinator.run_post_ingest_pipeline(scan_run_id, tenant_id)
  │
  │  [CompactionPipeline.run() has already returned; status is now "compacted"]
  │
  └── control_mapping_pipeline.py:ControlMappingPipeline.run(scan_run_id, tenant_id)
        │
        ├── scan_enrichment_repository.py:ScanEnrichmentRepository.fetch_detected_controls_for_run(
        │       scan_run_id, tenant_id
        │   )
        │     → DB READ  AQL (single query, no batching — controls fit in one call):
        │         FOR c IN detected_controls
        │           FILTER c.scan_run_id == @run_id AND c.tenant_id == @tenant_id
        │           RETURN c
        │     → controls: list[dict]
        │         [{_key, req_id, check_id, check_name, scan_run_id, tenant_id, ...}, ...]
        │
        ├── [TRANSFORM] ControlMappingPipeline._collect_control_keys(controls)
        │     → control_keys: list[str]  (deduplicated _key values)
        │
        ├── scan_enrichment_repository.py:ScanEnrichmentRepository.aql_resolve_control_framework(
        │       control_keys
        │   )
        │     → DB READ  AQL:
        │         FOR ck IN @control_keys
        │           LET in_oscal = DOCUMENT(CONCAT("oscal_controls/", ck))
        │           LET in_scf   = DOCUMENT(CONCAT("scf_controls/", ck))
        │           RETURN {
        │             control_key: ck,
        │             framework: in_oscal ? in_oscal.framework :
        │                        in_scf   ? in_scf.framework   : null
        │           }
        │     → framework_map: dict[str, str]
        │         {"ctrl_key_1": "NIST 800-53", "ctrl_key_2": "ISO 27001", ...}
        │
        ├── control_mapping_pipeline.py:ControlMappingPipeline._build_evidence_chains(
        │       controls, scan_run_id, tenant_id
        │   )
        │     [TRANSFORM] Prepares controls list for repository call
        │     │
        │     └── scan_enrichment_repository.py:ScanEnrichmentRepository.aql_resolve_evidence_chains(
        │             controls, scan_run_id
        │         )
        │               → DB READ  AQL traversal (one round-trip for all controls):
        │                   FOR ctrl IN @controls
        │                     LET finding_id = FIRST(
        │                       FOR edge IN finding_triggers_req
        │                         FILTER edge._to == CONCAT("regulatory_requirements/", ctrl.req_id)
        │                           AND edge.scan_run_id == @scan_run_id
        │                         LIMIT 1
        │                         RETURN PARSE_IDENTIFIER(edge._from).key
        │                     )
        │                     LET cwe_id = (finding_id != null ?
        │                       FIRST(DOCUMENT(CONCAT("scan_findings/", finding_id)).cwe_chain) : "")
        │                     RETURN {
        │                       control_key: ctrl._key,
        │                       chain: [
        │                         finding_id != null ? finding_id : "",
        │                         cwe_id != null ? cwe_id : "",
        │                         ctrl.req_id,
        │                         ctrl._key
        │                       ]
        │                     }
        │               → chain_map: dict[str, list[str]]
        │                   {"ctrl_key_1": ["fp_abc", "CWE-79", "REQ_NIST_SI-3", "ctrl_key_1"],
        │                    "ctrl_key_2": ["",       "",        "REQ_ISO_A.12",  "ctrl_key_2"]}
        │
        ├── [TRANSFORM] control_mapping_pipeline.py:ControlMappingPipeline._build_control_updates(
        │       controls, framework_map, chain_map
        │   )
        │     For each detected_control:
        │       update = {
        │         _key:           ctrl["_key"],
        │         framework:      framework_map.get(ctrl["_key"], ""),
        │         evidence_chain: chain_map.get(ctrl["_key"], ["","","",""]),
        │         control_status: "present"
        │       }
        │     → updates: list[dict]
        │
        ├── scan_enrichment_repository.py:ScanEnrichmentRepository.bulk_upsert_detected_controls(
        │       updates
        │   )
        │     → DB WRITE  db.collection("detected_controls")
        │                   .import_bulk(updates, on_duplicate="update")
        │     Fields written: framework, evidence_chain, control_status
        │
        ├── [TRANSFORM] control_mapping_pipeline.py:ControlMappingPipeline._compute_coverage(
        │       controls, framework_map
        │   )
        │     For each framework in framework_map.values():
        │       covered_reqs = count distinct req_ids in controls where framework matches
        │
        ├── control_mapping_pipeline.py:ControlMappingPipeline._get_total_reqs_by_framework()
        │     → DB READ  AQL:
        │         FOR r IN regulatory_requirements
        │           COLLECT framework = r.framework WITH COUNT INTO cnt
        │           RETURN {framework, cnt}
        │     → total_reqs_map: dict[str, int]
        │         {"NIST 800-53": 800, "ISO 27001": 114, ...}
        │
        │     [TRANSFORM] coverage_by_framework:
        │       For each framework:
        │         coverage_pct = (covered_reqs / total_reqs_map[framework]) * 100.0
        │     → coverage_by_framework: dict[str, float]
        │         {"NIST 800-53": 12.5, "ISO 27001": 8.3, ...}
        │
        ├── scan_enrichment_repository.py:ScanEnrichmentRepository.update_scan_run_coverage(
        │       scan_run_id, coverage_by_framework
        │   )
        │     → DB WRITE  AQL UPDATE scan_runs/{scan_run_id}
        │                 WITH {coverage_by_framework: {...}, updated_at: ...}
        │
        └── scan_enrichment_repository.py:ScanEnrichmentRepository.update_scan_run_status(
                scan_run_id, "mapped"
            )
              → DB WRITE  AQL UPDATE scan_runs/{scan_run_id}
                          WITH {status: "mapped", updated_at: ...}
              [STATE]  scan_runs.status: "compacted" → "mapped"
```

---

## UC-009-EDGE: Control Mapping — No OSCAL/SCF Controls in Reference DB

**Source Type:** Design-Risk
**Risk Reference:** Risk-4
**Coverage:** Error / Edge

**Scenario:** Knowledge graph agents have not yet populated `oscal_controls` or `scf_controls`
(e.g., first deployment, or reference DB reset). `fetch_detected_controls_for_run()` returns
an empty list (zero detected_controls from UC-007, because UC-007 found no req_keys from
CVE traversal into unpopulated `regulatory_requirements`). Coverage should be reported as
0% and status should still advance to `"mapped"`.

```
══════════════════════════════════════════════════════════════════════════
[BACKGROUND TASK — ControlMappingPipeline.run(), diverges at fetch_detected_controls]
══════════════════════════════════════════════════════════════════════════

control_mapping_pipeline.py:ControlMappingPipeline.run(scan_run_id, tenant_id)
  │
  ├── scan_enrichment_repository.py:ScanEnrichmentRepository.fetch_detected_controls_for_run(
  │       scan_run_id, tenant_id
  │   )
  │     → DB READ  AQL returns empty cursor (no detected_controls for this run)
  │     → controls: []
  │
  ├── [IF] controls is empty list:
  │     control_keys = []
  │
  ├── scan_enrichment_repository.py:ScanEnrichmentRepository.aql_resolve_control_framework([])
  │     → DB READ  AQL over empty @control_keys → returns empty result set immediately
  │     → framework_map: {}
  │
  ├── control_mapping_pipeline.py:ControlMappingPipeline._build_evidence_chains([], ...)
  │     → No AQL executed (empty input)
  │     → chain_map: {}
  │
  ├── [TRANSFORM] _build_control_updates([], {}, {})
  │     → updates: []
  │
  ├── scan_enrichment_repository.py:ScanEnrichmentRepository.bulk_upsert_detected_controls([])
  │     → DB WRITE  import_bulk([], on_duplicate="update")
  │                 (no-op; ArangoDB accepts empty import)
  │
  ├── [TRANSFORM] _compute_coverage([], {})
  │     For each framework: covered_reqs = 0
  │     → partial_coverage = {}  (no frameworks detected → empty dict)
  │
  ├── control_mapping_pipeline.py:ControlMappingPipeline._get_total_reqs_by_framework()
  │     → DB READ  AQL over regulatory_requirements
  │     [IF] regulatory_requirements is also empty → total_reqs_map: {}
  │     [IF] regulatory_requirements has data but no controls detected:
  │          total_reqs_map: {"NIST 800-53": 800, ...}
  │          coverage_by_framework: {"NIST 800-53": 0.0, "ISO 27001": 0.0, ...}
  │
  ├── scan_enrichment_repository.py:ScanEnrichmentRepository.update_scan_run_coverage(
  │       scan_run_id, coverage_by_framework={}  OR  {"NIST 800-53": 0.0, ...}
  │   )
  │     → DB WRITE  scan_runs/{scan_run_id}.coverage_by_framework = {}
  │                 (or all-zeros dict — not an error condition)
  │
  └── scan_enrichment_repository.py:ScanEnrichmentRepository.update_scan_run_status(
          scan_run_id, "mapped"
      )
        → DB WRITE  status → "mapped"
        [STATE]  scan_runs.status: "compacted" → "mapped"

Design-Risk verdict: SAFE.
  Zero detected_controls is an expected data state, not an error.
  coverage_by_framework is written as {} or all-zeros.
  Status still transitions to "mapped".
  HTTP clients polling GET /v1/scan/{run_id} will see status="mapped" and
  coverage_by_framework={} — indicating pipeline ran to completion with no
  control coverage detected.
```

---

## UC-CROSS-001: Auto-Trigger Chain

**Source Type:** Design-Risk
**Coverage:** N/A (cross-cutting chain validation)

**Scenario:** Validates that the auto-trigger via `POST /v1/scan/ingest` correctly
chains UC-007 → UC-008 → UC-009 as sequential BackgroundTasks without blocking
the HTTP response, and that no stage is skipped or inverted.

```
══════════════════════════════════════════════════════════════════════════
[HTTP THREAD]  src/api/v1/endpoints/scan.py
══════════════════════════════════════════════════════════════════════════

scan.py:ingest_scan_endpoint(request, customer, background_tasks)
  │
  ├── [existing] EvidenceIngestionService(ref_db).ingest_scan(...)
  │       → ScanIngestResult {scan_run_id, status="completed"}
  │
  ├── [IF] result.status == "completed":  [NEW — Phase 1 addition]
  │     │
  │     ├── [TRANSFORM] PipelineCoordinator(ref_db)
  │     │     (wires: EnrichmentPipeline, CompactionPipeline, ControlMappingPipeline,
  │     │             ScanEnrichmentRepository, EvidenceRunRepository)
  │     │
  │     └── background_tasks.add_task(
  │               coordinator.run_post_ingest_pipeline,
  │               scan_run_id=result.scan_run_id,
  │               tenant_id=customer.id
  │           )
  │         [NOTE] add_task() returns immediately; no await here.
  │                Pipeline is enqueued, NOT started yet.
  │
  └── return Response: 200 {"scan_run_id": ..., "status": "completed"}
      [HTTP response sent to client]

══════════════════════════════════════════════════════════════════════════
[BACKGROUND TASK — starts after HTTP response is sent]
  Triggered by FastAPI's BackgroundTasks mechanism (runs in same event loop,
  after response is finalized; does NOT block the HTTP response)
══════════════════════════════════════════════════════════════════════════

orchestrator.py:PipelineCoordinator.run_post_ingest_pipeline(scan_run_id, tenant_id)
  │
  │  STAGE GATE: verify DB and status before each stage
  │
  ├── Step 1: _verify_reference_db() → True
  │
  ├── Step 2: _get_run_status(scan_run_id) → "completed"
  │
  ├── Step 3: [IF] status in {"completed"} → run EnrichmentPipeline
  │
  ├── Step 4: [AWAIT] EnrichmentPipeline.run(scan_run_id, tenant_id)
  │               → completes synchronously within the background coroutine
  │               → DB WRITE  status → "enriched"
  │               → returns
  │
  │           [ORDER GUARANTEE: CompactionPipeline.run() is called only after
  │            EnrichmentPipeline.run() returns. There is no concurrency between
  │            stages. PipelineCoordinator.run_post_ingest_pipeline() is a single
  │            coroutine with sequential awaits / calls.]
  │
  ├── Step 5: [IF] status now "enriched" → run CompactionPipeline
  │
  ├── Step 6: [AWAIT] CompactionPipeline.run(scan_run_id, tenant_id)
  │               → completes; DB WRITE  status → "compacted"
  │               → returns
  │
  ├── Step 7: [IF] status now "compacted" → run ControlMappingPipeline
  │
  └── Step 8: [AWAIT] ControlMappingPipeline.run(scan_run_id, tenant_id)
                  → completes; DB WRITE  status → "mapped"
                  → returns

  Pipeline complete. scan_runs.status = "mapped".

══════════════════════════════════════════════════════════════════════════
Error isolation within the chain
══════════════════════════════════════════════════════════════════════════

orchestrator.py:PipelineCoordinator.run_post_ingest_pipeline(scan_run_id, tenant_id)
  │
  │  Each stage is wrapped in try/except:
  │
  ├── try:
  │     EnrichmentPipeline.run(...)
  │   except Exception as e:
  │     repo.update_scan_run_status(scan_run_id, "pipeline_failed",
  │                                 {"pipeline_error": str(e)})
  │     return   ← CompactionPipeline and ControlMappingPipeline are NOT called
  │
  ├── try:
  │     CompactionPipeline.run(...)
  │   except Exception as e:
  │     repo.update_scan_run_status(scan_run_id, "pipeline_failed",
  │                                 {"pipeline_error": str(e)})
  │     return   ← ControlMappingPipeline is NOT called
  │
  └── try:
        ControlMappingPipeline.run(...)
      except Exception as e:
        repo.update_scan_run_status(scan_run_id, "pipeline_failed",
                                    {"pipeline_error": str(e)})
        return

Chain ordering invariant:
  UC-007 always completes (status="enriched") before UC-008 starts.
  UC-008 always completes (status="compacted") before UC-009 starts.
  HTTP 200 response is always sent before any pipeline stage begins.
  No stage can interleave with another (single background coroutine, sequential calls).
```

---

## MUC-1: Concurrent Enrichment Requests for Same scan_run_id

**Source Type:** Design-Risk
**Coverage:** Race Condition / Operational
**Classification:** Accepted Risk — no code guard required in Phase 1

**Scenario:** Two simultaneous `POST /v1/scans/{scan_run_id}/enrich` requests arrive. Both pass
the HTTP-layer status check (`status="completed"` is in `RETRIABLE_STATUSES`). Both enqueue a
`PipelineCoordinator.run_post_ingest_pipeline()` BackgroundTask before either has executed.

```
══════════════════════════════════════════════════════════════════════════
[HTTP THREAD — Request A and Request B, arriving near-simultaneously]
══════════════════════════════════════════════════════════════════════════

Request A: enrich_scan_endpoint(scan_run_id, background_tasks, customer)
  ├── ref_db.collection("scan_runs").get(scan_run_id) → {status: "completed"}
  ├── [IF] "completed" in RETRIABLE_STATUSES → True  (passes gate)
  ├── background_tasks.add_task(coordinator_A.run_post_ingest_pipeline, scan_run_id, ...)
  └── Response: 202

Request B: enrich_scan_endpoint(scan_run_id, background_tasks, customer)
  ├── ref_db.collection("scan_runs").get(scan_run_id) → {status: "completed"}
  │     [NOTE: Request B reads status before Request A's background task has run]
  ├── [IF] "completed" in RETRIABLE_STATUSES → True  (passes gate)
  ├── background_tasks.add_task(coordinator_B.run_post_ingest_pipeline, scan_run_id, ...)
  └── Response: 202

══════════════════════════════════════════════════════════════════════════
[BACKGROUND TASKS — FastAPI executes tasks sequentially in event loop]
══════════════════════════════════════════════════════════════════════════

Task A: PipelineCoordinator.run_post_ingest_pipeline(scan_run_id, tenant_id)
  ├── _verify_reference_db() → True
  ├── _get_run_status(scan_run_id) → "completed"
  ├── EnrichmentPipeline.run(...)  → status → "enriched"
  ├── CompactionPipeline.run(...)  → status → "compacted"
  └── ControlMappingPipeline.run() → status → "mapped"
      → DB state: complete, correct

Task B: PipelineCoordinator.run_post_ingest_pipeline(scan_run_id, tenant_id)
  ├── _verify_reference_db() → True
  ├── _get_run_status(scan_run_id) → "mapped"  (Task A has already completed)
  │     [NOTE: "mapped" is NOT in RETRIABLE_STATUSES at the coordinator level]
  │     [IF] status not in {"completed","enriched","compacted","pipeline_failed","enrichment_pending"}
  │     → return early (no pipeline stages executed)
  └── [no pipeline stages run; scan_run unchanged]

OR (if Task B starts before Task A completes):
  Task B status check returns "enriched" or "compacted" → coordinator skips
  already-completed stages and runs only remaining stages.
  All writes are idempotent → identical final DB state.

DB state after both tasks complete: identical to single-execution result.
  scan_findings: enriched, compacted, risk_scored (same values as single run)
  scan_runs.status: "mapped"
  All edges and detected_controls: idempotent upserts (no duplicates)

Concurrency model note:
  FastAPI BackgroundTasks in a single-worker ASGI process executes tasks sequentially
  in the event loop after the HTTP response is finalized. True parallel execution of
  Task A and Task B only occurs if two separate worker processes handle the requests
  (e.g., multi-worker uvicorn deployment). In that case, both tasks may run concurrently;
  all writes remain idempotent and the final state is still correct.

Design policy: ACCEPTED RISK for Phase 1.
  No concurrency guard (mutex, task deduplication) is introduced in Phase 1.
  Cost of double-execution: doubled DB write load; no data corruption.
  Phase 1 target: single-worker deployment, < 30s per run.
  Mitigation for Phase 2: Celery task queue with deduplication by scan_run_id
    (prevents double enqueue at the queue level before any execution begins).
```

---

## Coverage Summary

| UC ID | Name | Source Type | Requirement/Risk Ref | Primary | Fallback | Error/Edge |
|---|---|---|---|---|---|---|
| UC-007-PRIMARY | Enrichment pipeline — happy path | Requirement | REQ-001 | Yes | N/A | N/A |
| UC-007-FALLBACK | Enrichment — reference DB unavailable | Requirement | REQ-001, AC-027 | N/A | Yes | N/A |
| UC-007-EDGE | Enrichment — findings with no CVE ID | Requirement | REQ-001, AC-008 | N/A | N/A | Yes |
| MUC-4 | Partial batch failure mid-enrichment | Design-Risk | REQ-001, AC-026 | N/A | N/A | Yes |
| UC-008-PRIMARY | Compaction pipeline — happy path | Requirement | REQ-002 | Yes | N/A | N/A |
| UC-008-EDGE | Compaction — all findings in one CWE group | Design-Risk | Risk-3 | N/A | N/A | Yes |
| UC-009-PRIMARY | Control mapping pipeline — happy path | Requirement | REQ-003 | Yes | N/A | N/A |
| UC-009-EDGE | Control mapping — no OSCAL/SCF controls | Design-Risk | Risk-4 | N/A | N/A | Yes |
| UC-CROSS-001 | Auto-trigger chain | Design-Risk | AC-023, AC-024 | N/A | N/A | N/A |
| MUC-1 | Concurrent enrichment for same scan_run_id | Design-Risk | AC-026 (operational) | N/A | N/A | Race Condition |

### DB Write Inventory (all use cases)

| Write Target | Collection | Stage | UC |
|---|---|---|---|
| `scan_findings` — enrichment fields | `scan_findings` | EnrichmentPipeline | UC-007 |
| `finding_triggers_req` edges | `finding_triggers_req` | EnrichmentPipeline | UC-007 |
| `detected_controls` — upsert | `detected_controls` | EnrichmentPipeline | UC-007 |
| `detected_control_maps_to` edges | `detected_control_maps_to` | EnrichmentPipeline | UC-007 |
| `scan_runs.status` = `"enriched"` | `scan_runs` | EnrichmentPipeline | UC-007 |
| `scan_findings` — compaction fields | `scan_findings` | CompactionPipeline | UC-008 |
| `scan_runs.status` = `"compacted"` | `scan_runs` | CompactionPipeline | UC-008 |
| `detected_controls` — framework + chain | `detected_controls` | ControlMappingPipeline | UC-009 |
| `scan_runs.coverage_by_framework` | `scan_runs` | ControlMappingPipeline | UC-009 |
| `scan_runs.status` = `"mapped"` | `scan_runs` | ControlMappingPipeline | UC-009 |
| `scan_runs.status` = `"enrichment_pending"` | `scan_runs` | PipelineCoordinator | UC-007-FALLBACK |
| `scan_runs.status` = `"pipeline_failed"` | `scan_runs` | PipelineCoordinator | Any stage error |

### Idempotency Contract

All writes in every use case use one of two idempotent patterns:
- `import_bulk(on_duplicate="update")` — edges and detected_controls upserts
- `AQL UPDATE <_key> WITH <fields>` — scan_findings and scan_runs field updates

Re-running any use case produces identical document state for the same input data.

### Acceptance Criteria Traceability

| AC-ID | Covered By UC | Frame |
|---|---|---|
| AC-001 | UC-007-PRIMARY | `aql_enrich_findings_batch` → `has_epss` traversal |
| AC-002 | UC-007-PRIMARY | `aql_enrich_findings_batch` → `kev_entries` FILTER |
| AC-003 | UC-007-PRIMARY | `aql_enrich_findings_batch` → `has_weakness` traversal |
| AC-004 | UC-007-PRIMARY | `aql_enrich_findings_batch` → `d3fend_counters_technique` |
| AC-005 | UC-007-PRIMARY | `_build_detected_controls` → `bulk_upsert_detected_controls` |
| AC-006 | UC-007-PRIMARY | `_build_req_edges` → `upsert_finding_triggers_req_edges` |
| AC-007 | UC-007-PRIMARY | `_build_detected_control_maps_to_edges` → `upsert_detected_control_maps_to_edges` |
| AC-008 | UC-007-EDGE | `_normalize_cve_to_key` null-CVE skip gate |
| AC-009 | UC-007-PRIMARY | `update_scan_run_status(..."enriched"...)` |
| AC-010 | UC-007-PRIMARY | `import_bulk(on_duplicate="update")` + AQL UPDATE |
| AC-011 | UC-008-PRIMARY | `_assign_compaction_groups` → group by resolved CWE |
| AC-012 | UC-008-PRIMARY | `_assign_compaction_groups` → canonical/compacted flag |
| AC-013 | UC-008-PRIMARY | `aql_get_cwe_parent_map` → `child_of` traversal |
| AC-014 | UC-008-PRIMARY | `_compute_risk_scores` formula |
| AC-015 | UC-008-PRIMARY | `_compute_cluster_ranks` → rank assignment |
| AC-016 | UC-008-PRIMARY | `update_scan_run_status(..."compacted"...)` |
| AC-017 | UC-008-PRIMARY | AQL UPDATE + deterministic group/rank |
| AC-018 | UC-009-PRIMARY | `aql_resolve_control_framework` → framework annotation |
| AC-019 | UC-009-PRIMARY | `_build_evidence_chains` → evidence chain assembly |
| AC-020 | UC-009-PRIMARY | `_compute_coverage` + `_get_total_reqs_by_framework` |
| AC-021 | UC-009-PRIMARY | `update_scan_run_status(..."mapped"...)` |
| AC-022 | UC-009-PRIMARY | `import_bulk(on_duplicate="update")` |
| AC-023 | UC-CROSS-001 | `scan.py` BackgroundTask add after `status=="completed"` |
| AC-024 | UC-CROSS-001 | `pipeline.py` 202 + BackgroundTask enqueue |
| AC-026 | UC-CROSS-001 | `PipelineCoordinator` try/except per stage |
| AC-027 | UC-007-FALLBACK | `_verify_reference_db()` → `enrichment_pending` |
| AC-028 | UC-007-PRIMARY | `tenant_id` FILTER in all AQL reads |

---

*Document complete. Derived entirely from proposed-design.md. No current code traced.*
