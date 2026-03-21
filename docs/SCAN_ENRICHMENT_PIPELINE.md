# Scan Enrichment Pipeline (Phase 1)

**Status:** Implemented
**Last Updated:** 2026-03-21
**Module:** `src/complira_graph/ingestion/`

---

## Overview

After scan ingestion completes and a `scan_run` reaches `status = "completed"`, the Phase 1 enrichment pipeline runs automatically via FastAPI `BackgroundTasks`. It can also be triggered manually via the pipeline API endpoint.

The pipeline transforms raw scanner findings into actionable compliance intelligence through three sequential stages:

```
scan_run.status transitions:
  running → completed → enriched → compacted → mapped
                         (UC-007)   (UC-008)   (UC-009)

Failure states:
  enrichment_pending   — reference DB unavailable at pipeline start
  pipeline_failed      — stage failure mid-run (partial writes retained)
```

---

## Architecture

### Layer Hierarchy

```
POST /v1/scans/{scan_run_id}/enrich   (pipeline.py endpoint)
  ↓
src/api/v1/endpoints/scan.py          (auto-trigger via BackgroundTasks after ingest)
  ↓
PipelineCoordinator.run_post_ingest_pipeline()
  ↓
EnrichmentPipeline.run()              (UC-007: status completed → enriched)
  ↓
CompactionPipeline.run()              (UC-008: status enriched → compacted)
  ↓
ControlMappingPipeline.run()          (UC-009: status compacted → mapped)
  ↓
ScanEnrichmentRepository             (all AQL reads/writes — single class)
  ↓
ArangoDB Reference DB                (scan_findings, scan_runs, detected_controls)
```

### Module Map

| File | Responsibility |
|---|---|
| `src/complira_graph/ingestion/pipeline_coordinator.py` | Orchestrates all 3 stages; handles reference DB availability check; manages idempotency (skips completed stages unless `force=True`); sets `pipeline_failed`/`enrichment_pending` on error |
| `src/complira_graph/ingestion/enrichment_pipeline.py` | UC-007: Traverses reference DB per finding; writes EPSS, KEV, CWE chain, D3FEND; upserts `detected_controls`; creates `finding_triggers_req` and `detected_control_maps_to` edges |
| `src/complira_graph/ingestion/compaction_pipeline.py` | UC-008: Deduplicates findings by CWE via alias edges; rolls up to parent CWE; computes composite risk score; assigns `compaction_group_id` and `cluster_rank` |
| `src/complira_graph/ingestion/control_mapping_pipeline.py` | UC-009: Resolves detected controls to regulatory frameworks; writes `evidence_chain` per control; computes `coverage_by_framework` on `scan_run` |
| `src/complira_graph/ingestion/scan_enrichment_repository.py` | All AQL queries and bulk writes for the pipeline — single data-access class; no AQL in pipeline service files |
| `src/api/v1/endpoints/pipeline.py` | `POST /v1/scans/{scan_run_id}/enrich` — 202 Accepted; queues pipeline as BackgroundTask |

---

## UC-007: Vulnerability Enrichment

**Trigger:** `scan_run.status == "completed"`
**Outcome status:** `"enriched"`

For every `scan_findings` document with a non-null `cve_id`, the pipeline traverses the reference knowledge graph and writes:

| Field | Source Traversal |
|---|---|
| `epss_score`, `epss_percentile` | CVE → `has_epss` → `epss_history` (latest by `score_date DESC LIMIT 1`) |
| `in_kev: bool` | CVE lookup in `kev_entries` (normalizes `CVE-YYYY-NNNN` format) |
| `cwe_chain: list[str]` | CVE → `has_weakness` → weaknesses (1-hop chain) |
| `d3fend_techniques: list[str]` | ATT&CK → `d3fend_counters_technique` → D3FEND (may be empty) |
| `enriched_at` | Pipeline execution timestamp |

Additionally:
- `detected_controls` documents are upserted for every OSCAL/SCF control reachable via `CVE → violates_requirement → maps_to_requirement`
- `finding_triggers_req` edges are created from findings to `regulatory_requirements`
- `detected_control_maps_to` edges are created from new controls to `oscal_controls`/`scf_controls`
- Findings with no `cve_id` are skipped without error

---

## UC-008: Finding Compaction & Risk Scoring

**Trigger:** `scan_run.status == "enriched"`
**Outcome status:** `"compacted"`

### Composite Risk Score Formula

```
risk_score = cvss_base * 0.4
           + epss_score * 0.3
           + kev_bonus * 0.2       (1.0 if in_kev else 0.0)
           + exploit_bonus * 0.1   (capped at 1.0)

Result: float ∈ [0, 1]
```

### Deduplication and Compaction

- Findings sharing the same CWE (direct or via `aliases` edge in reference DB) are grouped under a shared `compaction_group_id`
- Within each group, all but one finding are marked `compacted: true`; the canonical finding has `compacted: false`
- Findings whose CWE has no `maps_to_requirement` edge are rolled up to the nearest parent CWE via `child_of` traversal in the reference DB

### Cluster Ranking

- Findings are clustered by CWE and each cluster is assigned a `cluster_rank` integer (1 = cluster with highest `max(risk_score)`)

---

## UC-009: Control Mapping

**Trigger:** `scan_run.status == "compacted"`
**Outcome status:** `"mapped"`

For each `detected_controls` document (populated by UC-007):
- `framework` field is set from reference DB control lookup (NIST 800-53, ISO 27001, FDA 510(k), IEC 62304, CRA)
- `evidence_chain: list[str]` is written as `[finding_id, cwe_id, req_id, control_id]`

On `scan_run`:
- `coverage_by_framework: dict[str, float]` is written — e.g., `{"NIST 800-53": 42.7, "ISO 27001": 31.2}`
- Values represent percentage of total framework requirements covered by this scan

---

## Triggers

### Automatic (post-ingest)

`src/api/v1/endpoints/scan.py` — after successful `ingest_scan()`, queues:

```python
background_tasks.add_task(coordinator.run_post_ingest_pipeline, scan_run_id, tenant_id)
```

### Manual (re-enrichment)

```
POST /v1/scans/{scan_run_id}/enrich
→ 202 Accepted
```

Triggers the full pipeline for an existing scan_run. Valid for scan_runs in status `completed`, `enrichment_pending`, or `pipeline_failed`.

### Status Polling

```
GET /v1/scans/{scan_run_id}
→ returns scan_run document including current status field
```

---

## Error Handling

| Scenario | Behavior |
|---|---|
| Reference DB unreachable at pipeline start | `scan_run.status = "enrichment_pending"` — pipeline exits immediately, retriable via manual trigger |
| Stage failure mid-run | `scan_run.status = "pipeline_failed"`, `scan_run.error_message` set with stage + exception; partial writes from completed stages are retained |
| Finding with no `cve_id` | Skipped in enrichment; receives `risk_score = 0`, `compacted: false`, no edges created |
| D3FEND traversal returns empty | Empty list written to `d3fend_techniques`; not an error |
| `detected_control_maps_to` edges with missing OSCAL/SCF controls | Zero mappings written; not an error; coverage gap logged |

---

## Idempotency

All writes use `UPSERT` in AQL. Re-running any pipeline stage for the same `scan_run_id`:
- Does not create duplicate edges or documents
- Produces identical risk scores and group assignments (deterministic formula)
- `PipelineCoordinator` skips stages already at target status unless `force=True`

---

## Multi-tenancy

All pipeline reads and writes include `tenant_id` filter. The `ScanEnrichmentRepository` enforces `tenant_id` scoping on every AQL query — no cross-tenant data access is possible.

---

## Database Collections (Reference DB)

### Evidence Collections (written by pipeline)

| Collection | Writer |
|---|---|
| `scan_findings` | UC-007 (enrichment fields), UC-008 (risk/compaction fields) |
| `detected_controls` | UC-007 (upsert), UC-009 (framework + evidence_chain) |
| `scan_runs` | All stages (status transitions, coverage_by_framework) |
| `finding_triggers_req` (edge) | UC-007 |
| `detected_control_maps_to` (edge) | UC-007 |

### Knowledge Graph Collections (read by pipeline, not written)

`vulnerabilities`, `weaknesses`, `kev_entries`, `epss_history`, `oscal_controls`, `scf_controls`, `attack_techniques`, `d3fend_techniques`

Edge traversals used: `has_weakness`, `child_of`, `aliases`, `maps_to_requirement`, `violates_requirement`, `has_epss`, `d3fend_counters_technique`, `technique_exploits_weakness`

---

## Performance Notes

- Bulk AQL updates are chunked at ≤ 500 findings per transaction to stay within ArangoDB transaction size limits
- Target: < 30 seconds for 500 findings end-to-end (no hard SLA for Phase 1)
- Redis cache may be used for reference DB traversal results (TTL = 6 hours, per Phase 0 config)

---

## Tests

| Test File | Type | Count |
|---|---|---|
| `tests/unit/ingestion/test_scan_enrichment_repository.py` | Unit | 29 |
| `tests/unit/ingestion/test_enrichment_pipeline.py` | Unit | 22 |
| `tests/unit/ingestion/test_compaction_pipeline.py` | Unit | 26 |
| `tests/unit/ingestion/test_control_mapping_pipeline.py` | Unit | 13 |
| `tests/integration/test_pipeline_phase1.py` | Integration | 24 |

**Total: 114 tests** (95 unit + 24 integration via mock-based boundary testing)

AC coverage: 26/28 ACs Passed, 2 Waived (live ArangoDB required — AC-013 CWE roll-up live AQL traversal, AC-022 control mapping idempotency live).
