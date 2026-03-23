# Future-State Runtime Call Stacks — compliance-violation-mapping

**Version:** v2
**Last Updated:** 2026-03-22
**Design Basis:** `proposed-design.md` v1

---

## UC-CV-001: Create `finding_violates_control` edges for a CVE with controls

**Type:** Requirement (REQ-CV-001)
**Entry:** `ViolationMappingPipeline.run(scan_run_id, tenant_id)` — inner per-CVE batch

### Primary Path

```
ViolationMappingPipeline.run(scan_run_id, tenant_id)
  [src/complira_graph/ingestion/violation_mapping_pipeline.py:ViolationMappingPipeline.run]
  │
  ├─ ScanEnrichmentRepository.fetch_findings_for_run(scan_run_id, tenant_id) → Iterator[list[dict]]
  │   [src/complira_graph/ingestion/scan_enrichment_repository.py:fetch_findings_for_run]
  │   AQL: FOR f IN scan_findings FILTER f.scan_run_id==@run_id AND f.tenant_id==@tenant_id
  │         LIMIT @offset, @batch_size RETURN f
  │   → yields batches of {_key, cve_id, ...}
  │
  ├─ [for each batch] group findings by cve_id, deduplicate
  │   → purl_to_fingerprints: dict[cve_key, list[finding_key]]
  │   [KEY MUTATION: normalize cve_id to cve_key via normalize_cve_id()]
  │
  ├─ ScanViolationRepository.aql_traverse_controls_for_cves(cve_keys: list[str])
  │   [src/complira_graph/ingestion/scan_violation_repository.py:aql_traverse_controls_for_cves]
  │   AQL: FOR cve_key IN @cve_keys
  │           LET cve_doc = DOCUMENT(CONCAT("vulnerabilities/", cve_key))
  │           LET controls = (
  │               FOR w IN 1..1 OUTBOUND cve_doc has_weakness
  │                   FOR ca IN 1..1 INBOUND w capec_relates_to_cwe
  │                       FOR at IN 1..1 OUTBOUND ca capec_maps_to_attack
  │                           FOR ctrl IN 1..1 OUTBOUND at technique_mitigated_by_control
  │                               RETURN DISTINCT {
  │                                   control_key: ctrl._key,
  │                                   control_id: ctrl.control_id,
  │                                   framework: ctrl.framework,
  │                                   evidence_path: [cve_key, w._key, ca._key, at._key, ctrl._key]
  │                               }
  │           )
  │           FILTER LENGTH(controls) > 0
  │           RETURN {cve_key: cve_key, controls: controls}
  │   → dict[cve_key → list[{control_key, control_id, framework, evidence_path}]]
  │
  ├─ [in pipeline] _build_edges(findings_batch, control_map, tenant_id, scan_run_id) → list[dict]
  │   For each finding:
  │     cve_key = normalize_cve_id(finding.cve_id)
  │     if cve_key not in control_map: skip
  │     for each control in control_map[cve_key]:
  │       edge_key = generate_edge_key(finding._key, control.control_key, "violates_ctrl")
  │       edge = {
  │           _key: edge_key,
  │           _from: f"scan_findings/{finding._key}",
  │           _to: f"oscal_controls/{control.control_key}",
  │           tenant_id, scan_run_id, cve_id, control_id, framework, confidence=1.0,
  │           evidence_path, created_at
  │       }
  │   [IN-MEMORY DEDUP: dict keyed by edge_key]
  │
  ├─ ScanViolationRepository.upsert_finding_violates_control_edges(edges: list[dict]) → None
  │   [src/complira_graph/ingestion/scan_violation_repository.py:upsert_finding_violates_control_edges]
  │   → db.collection("finding_violates_control").import_bulk(edges, on_duplicate="update")
  │   [DB WRITE: upserted to finding_violates_control edge collection]
  │
  └─ ScanEnrichmentRepository.update_scan_run_status(scan_run_id, "violations_mapped", ...)
      [src/complira_graph/ingestion/scan_enrichment_repository.py:update_scan_run_status]
      [DB WRITE: scan_runs document updated, status = "violations_mapped"]
```

**Coverage:** Primary ✅ | Fallback N/A | Error → UC-CV-001 Error Path below

### Error Path — CVE document not found in reference DB

```
ScanViolationRepository.aql_traverse_controls_for_cves(cve_keys)
  AQL: DOCUMENT(CONCAT("vulnerabilities/", cve_key)) → null
  → FILTER LENGTH(controls) > 0 excludes this row from result
  → cve_key NOT in returned dict
  [NO ERROR raised — silently skipped]

Pipeline:
  cve_key not in control_map → finding skipped
  → no edge written for that finding
  → pipeline continues to remaining findings
  → status still set to "violations_mapped"
```

---

## UC-CV-002: Finding with CVE that has no control mapping

**Type:** Requirement (REQ-CV-001 — empty result case)
**Entry:** `ViolationMappingPipeline.run()` — batch contains finding with CVE that traversal returns no controls for

```
aql_traverse_controls_for_cves([cve_key_no_controls])
  AQL: traversal finds CWE but no CAPEC→ATT&CK→Control path
  → controls = []
  → FILTER LENGTH(controls) > 0 → row excluded
  → result dict does not contain cve_key_no_controls

Pipeline._build_edges(...)
  cve_key_no_controls not in control_map → finding skipped
  → no edges added to batch
  → upsert_finding_violates_control_edges([]) called with empty list
    → if not edges: return  (early exit)
  → scan_run status still updated to "violations_mapped"
```

**Coverage:** Primary ✅ (empty result case) | Error N/A

---

## UC-CV-003: ViolationMappingPipeline status transition `mapped → violations_mapped`

**Type:** Requirement (REQ-CV-002)
**Entry:** `PipelineCoordinator.run_post_ingest_pipeline()` — Stage 7

```
PipelineCoordinator.run_post_ingest_pipeline(scan_run_id, tenant_id)
  [src/complira_graph/ingestion/pipeline_coordinator.py]

  current_status = "mapped"  (after Stage 3 ControlMappingPipeline completes)

  # Stage 7: ViolationMappingPipeline
  if force or current_status not in _VIOLATION_DONE:
      self._violation_mapping.run(scan_run_id, tenant_id)
      → ViolationMappingPipeline.run(...)  [see UC-CV-001]
      → on success: scan_run.status = "violations_mapped"

  # Stage 4: LLMEnrichmentPipeline (unchanged)
  if force or current_status not in _LLM_DONE:
      self._llm_enrichment.run(scan_run_id, tenant_id)
      ...
```

### Error Path — ViolationMappingPipeline raises exception

```
self._violation_mapping.run(scan_run_id, tenant_id)
  → raises Exception

PipelineCoordinator:
  except Exception as exc:
      log.exception("pipeline_coordinator.violation_mapping_failed", ...)
      self._mark_failed(scan_run_id, str(exc))
      return  ← pipeline stops; LLM/blast stages do not run
```

**Coverage:** Primary ✅ | Error ✅

---

## UC-CV-004: `GET /v1/compliance/violations?scan_run_id=...`

**Type:** Requirement (REQ-CV-003)
**Entry:** HTTP GET request

### Primary Path — scan run found, violations exist

```
HTTP GET /v1/compliance/violations?scan_run_id=run_abc123
  → FastAPI router → compliance.py:get_violations()
    [src/api/v1/endpoints/compliance.py:get_violations]

  customer: Customer = Depends(get_current_customer)
    [auth check passes]

  db = get_reference_db()

  cursor = db.aql.execute(_VIOLATIONS_QUERY, bind_vars={
      "scan_run_id": scan_run_id, "tenant_id": customer.id
  })
  result = list(cursor)[0]
    → {run_exists: true, items: [{finding_id, cve_id, control_id, framework, confidence, evidence_path}, ...]}

  if not result["run_exists"]:
      raise HTTPException(404, ...)  ← not taken

  items = [ViolationItem(**r) for r in result["items"]]
  return APIResponse(data=ViolationsResponse(items=items, total=len(items)), ...)
  → HTTP 200
  [DATA SHAPE: {success: true, data: {items: [...], total: N}, metadata: {api_version: "v1"}}]
```

### Error Path — scan run not found or wrong tenant

```
_VIOLATIONS_QUERY returns {run_exists: false, items: []}
  → result["run_exists"] is False
  → raise HTTPException(status_code=404, detail="Scan run not found: ...")
  → HTTP 404
```

**Coverage:** Primary ✅ | Error ✅ (404)

---

## UC-CV-005: `GET /v1/compliance/coverage?scan_run_id=...`

**Type:** Requirement (REQ-CV-004)
**Entry:** HTTP GET request

### Primary Path

```
HTTP GET /v1/compliance/coverage?scan_run_id=run_abc123
  → compliance.py:get_coverage()
    [src/api/v1/endpoints/compliance.py:get_coverage]

  customer = Depends(get_current_customer)
  db = get_reference_db()

  cursor = db.aql.execute(_COVERAGE_QUERY, bind_vars={...})
  result = list(cursor)[0]
    → {run_exists: true, scan_run_id, total_findings, findings_with_violations, by_framework: [...]}

  if not result["run_exists"]:
      raise HTTPException(404, ...)  ← not taken

  by_framework = [FrameworkCoverage(**fw) for fw in result["by_framework"]]
  return APIResponse(data=CoverageResponse(
      scan_run_id=...,
      total_findings=...,
      findings_with_violations=...,
      by_framework=by_framework
  ), ...)
  → HTTP 200
```

### Error Path — scan run not found or wrong tenant

```
_COVERAGE_QUERY: run_doc = FIRST(FOR r IN scan_runs FILTER ... RETURN r) → null
  → result["run_exists"] = false
  → raise HTTPException(404)
  → HTTP 404
```

**Coverage:** Primary ✅ | Error ✅ (404)

---

## UC-CV-006: Pipeline handles scan run with zero findings

**Type:** Requirement (REQ-CV-002)

```
ViolationMappingPipeline.run(scan_run_id, tenant_id)
  ScanEnrichmentRepository.fetch_findings_for_run(...)
    → first AQL page returns []  (no findings)
    → generator yields nothing (empty)

  purl_to_fingerprints = {}  (empty)
  → aql_traverse_controls_for_cves([])  ← called with empty list
    → "if not cve_keys: return {}"  (early exit in repo)
  → no edges to build or upsert

  ScanEnrichmentRepository.update_scan_run_status(scan_run_id, "violations_mapped", ...)
    → scan_run updated normally
  → HTTP 202 / status "violations_mapped" set
```

**Coverage:** Primary ✅

---

## UC-CV-007: Pipeline re-run is idempotent

**Type:** Design-Risk — `import_bulk(on_duplicate="update")` must not duplicate edges

```
ViolationMappingPipeline.run(scan_run_id, tenant_id)  [first run]
  → _build_edges produces edges with deterministic _key = generate_edge_key(finding_key, ctrl_key, "violates_ctrl")
  → upsert_finding_violates_control_edges(edges)
      db.collection("finding_violates_control").import_bulk(edges, on_duplicate="update")
      → edges inserted

ViolationMappingPipeline.run(scan_run_id, tenant_id)  [second run, same data]
  → _build_edges produces same edge _key values
  → upsert_finding_violates_control_edges(edges)
      import_bulk(on_duplicate="update") → updates existing docs in place, no new documents
      [DB: collection count unchanged]

Coordinator: current_status = "violations_mapped" → _VIOLATION_DONE contains it → Stage 7 skipped
  → no second run unless force=True
```

**Coverage:** Primary ✅

---

## UC-CV-008: Coordinator skips `ViolationMappingPipeline` when status is `violations_mapped`

**Type:** Design-Risk — guard set must cover `violations_mapped` status

```
PipelineCoordinator._VIOLATION_DONE = frozenset({"violations_mapped",
    "llm_enriched", "blast_radius_computed", "velocity_computed"})

_ENRICHMENT_DONE = frozenset({
    "enriched", "compacted", "mapped", "violations_mapped",
    "llm_enriched", "blast_radius_computed", "velocity_computed"
})
_COMPACTION_DONE = frozenset({
    "compacted", "mapped", "violations_mapped",
    "llm_enriched", "blast_radius_computed", "velocity_computed"
})
_MAPPING_DONE = frozenset({
    "mapped", "violations_mapped",
    "llm_enriched", "blast_radius_computed", "velocity_computed"
})

PipelineCoordinator.run_post_ingest_pipeline(scan_run_id, tenant_id, force=False)
  current_status = self._get_run_status(scan_run_id)  → "violations_mapped"

  # Stages 1-3 skipped (violations_mapped in _ENRICHMENT_DONE, _COMPACTION_DONE, _MAPPING_DONE)
  log.info("pipeline_coordinator.enrichment_skipped", ...)
  log.info("pipeline_coordinator.compaction_skipped", ...)
  log.info("pipeline_coordinator.control_mapping_skipped", ...)

  # Stage 7: Violation Mapping
  if force or current_status not in _VIOLATION_DONE:  ← False (violations_mapped IS in _VIOLATION_DONE)
      ...  ← SKIPPED
  else:
      log.info("pipeline_coordinator.violation_mapping_skipped", ...)

  # Stage 4: LLM Enrichment continues normally
  _LLM_DONE = frozenset({"llm_enriched", "blast_radius_computed", "velocity_computed"})
  "violations_mapped" not in _LLM_DONE → LLM stage runs as expected
```

**Coverage:** Primary ✅

---

## Use Case Summary

| Use Case | Primary | Fallback | Error | Status |
| --- | --- | --- | --- | --- |
| UC-CV-001 | ✅ | N/A | ✅ | Covered |
| UC-CV-002 | ✅ | N/A | N/A | Covered |
| UC-CV-003 | ✅ | N/A | ✅ | Covered |
| UC-CV-004 | ✅ | N/A | ✅ | Covered |
| UC-CV-005 | ✅ | N/A | ✅ | Covered |
| UC-CV-006 | ✅ | N/A | N/A | Covered |
| UC-CV-007 | ✅ | N/A | N/A | Covered |
| UC-CV-008 | ✅ | N/A | N/A | Covered |
