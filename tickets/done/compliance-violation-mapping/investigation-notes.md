# Investigation Notes — compliance-violation-mapping

**Stage:** 1
**Last Updated:** 2026-03-22

---

## Sources Consulted

- `src/complira_graph/ingestion/pipeline_coordinator.py`
- `src/complira_graph/ingestion/control_mapping_pipeline.py`
- `src/complira_graph/ingestion/blast_radius_pipeline.py`
- `src/complira_graph/ingestion/scan_enrichment_repository.py`
- `src/complira_graph/ingestion/enrichment_pipeline.py`
- `src/complira_graph/db.py`
- `src/complira_graph/queries/compliance.py`
- `src/api/v1/endpoints/reference.py` (GET /v1/reference/controls/{cve_id})
- `src/api/v1/endpoints/pipeline.py`
- `src/api/v1/endpoints/meta.py`
- `docs/ARCHITECTURAL_GAPS_REMEDIATION_PLAN.md`

---

## Key Findings

### F-001: `violates_requirement` collection already exists — CVE→requirement edges
`violates_requirement` is an existing edge collection in the reference DB holding `vulnerabilities/<CVE_key>` → `regulatory_requirements/<req_key>` edges (5.27M edges per meta.py count endpoint). This is NOT the same as finding→control edges. The task description uses "violates_requirement" loosely to describe the concept; a new edge collection is needed.

### F-002: `finding_triggers_req` is the existing finding→requirement edge collection
`enrichment_pipeline.py` already creates `finding_triggers_req` edges (`scan_findings/<fingerprint>` → `regulatory_requirements/<req_key>`) using `violates_requirement, maps_to_requirement` traversal via `aql_enrich_batch`. This covers CVE→req mapping but NOT the full CVE→CWE→CAPEC→ATT&CK→Control chain.

### F-003: Reference graph chain for control mapping (verified)
`GET /v1/reference/controls/{cve_id}` in `reference.py` traverses:
```
CVE → has_weakness → CWE (OUTBOUND)
    → capec_relates_to_cwe (INBOUND from CWE)
    → capec_maps_to_attack (OUTBOUND)
    → technique_mitigated_by_control (OUTBOUND)
    → NIST 800-53 controls
```
This chain terminates at `nist_controls`/`oscal_controls` documents with `control_id`, `title`, `family` fields. The new pipeline should use this SAME chain.

### F-004: Pipeline status chain and coordinator pattern
Current status chain: `completed → enriched → compacted → mapped → llm_enriched → blast_radius_computed → velocity_computed`.
`PipelineCoordinator` uses guard sets (`_MAPPING_DONE`, `_BLAST_DONE`, etc.) to skip completed stages.
New stage `violations_mapped` should be added AFTER `mapped` (control mapping complete), since the violation chain relies on the same graph data that controls use.
Actually: the violation chain is independent of `detected_controls` — it only needs CVE IDs from `scan_findings`. So it can run after `mapped` or even `compacted`. After `mapped` is the cleanest fit (consistent with data being enriched by then).

### F-005: Repository pattern — all AQL in repo class, zero AQL in pipeline class
Pattern: Pipeline classes call repository methods; repositories hold all AQL. Repositories injected via constructor. Existing: `ScanEnrichmentRepository`, `ScanBlastRadiusRepository`, `ScanLLMEnrichmentRepository`. New: `ScanViolationRepository`.

### F-006: `nist_controls`/`oscal_controls` is the control collection name
The reference.py traversal returns `control_id`, `title`, `family` fields. The `_key` of the destination collection is the NIST control identifier. The collection name is likely `nist_controls` or `oscal_controls` (from the reference AQL using `technique_mitigated_by_control` edge). Need to use correct collection name in `_to` for the new edge.

### F-007: New edge collection required — `finding_violates_control`
The new edge collection should be `finding_violates_control`:
- `_from`: `scan_findings/<fingerprint_key>`
- `_to`: `nist_controls/<control_key>` (destination of `technique_mitigated_by_control`)
- Additional fields: `tenant_id`, `scan_run_id`, `cve_id`, `control_id`, `framework`, `confidence` (1.0 for deterministic), `evidence_path` (array of vertex keys along the chain), `created_at`
This collection is NEW and does not exist in `db.py` yet. It must be added to `EDGE_COLLECTIONS` and `INDEXES`.

### F-008: Compliance query API — follows supply_chain endpoint pattern
New endpoints `GET /v1/compliance/violations` and `GET /v1/compliance/coverage` follow the same pattern as supply_chain.py: AQL-in-endpoint, `get_reference_db()` direct call, `customer: Customer = Depends(get_current_customer)`, tenant scoping via `tenant_id` filter on `finding_violates_control` edges.

---

## Open Unknowns

- OQ-1 (Resolved): `violates_requirement` collection is CVE→requirement (existing). New collection needed: `finding_violates_control`.
- OQ-2: Exact `_key` format in the `nist_controls` or `oscal_controls` collection — verify from schema/db.py.
- OQ-3: Pipeline status chain: `violations_mapped` inserts AFTER `mapped`, before `llm_enriched` in the coordinator's guard sets. Confirm coordinator update will not break existing skip logic.
- OQ-4: `PipelineCoordinator` `_RETRIABLE_STATUSES` — must add `mapped` is already in it; `violations_mapped` must also be added.

---

## Scope Triage

**Classification: Medium**

Signals:
- 6+ files to create or modify
- New pipeline stage, new repository class, new edge collection schema
- New API endpoints (2) + response models
- Cross-layer impact: ingestion layer (pipeline/repo), DB schema (db.py), API layer (endpoints, router, models)
- No structural architecture changes; follows established patterns exactly
- No new graph traversal primitives — the chain is verified/working in reference.py

**Files impacted:**
| File | Change Type |
| --- | --- |
| `src/complira_graph/db.py` | Modify — add `finding_violates_control` to schema |
| `src/complira_graph/ingestion/scan_violation_repository.py` | Add — new repository class |
| `src/complira_graph/ingestion/violation_mapping_pipeline.py` | Add — new pipeline stage |
| `src/complira_graph/ingestion/pipeline_coordinator.py` | Modify — add stage 7 (`violations_mapped`) |
| `src/api/models/responses/compliance.py` | Add — new response models |
| `src/api/v1/endpoints/compliance.py` | Add — two new endpoints |
| `src/api/v1/router.py` | Modify — register compliance router |
| `tests/unit/...` | Add — unit tests for pipeline + endpoints |
