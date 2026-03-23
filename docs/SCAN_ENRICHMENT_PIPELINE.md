# Scan Enrichment Pipeline (Phase 1 + Phase 2)

**Status:** Implemented
**Last Updated:** 2026-03-22
**Module:** `src/complira_graph/ingestion/`

---

## Overview

After scan ingestion completes and a `scan_run` reaches `status = "completed"`, the Phase 1 enrichment pipeline runs automatically via FastAPI `BackgroundTasks`. It can also be triggered manually via the pipeline API endpoint.

The pipeline transforms raw scanner findings into actionable compliance intelligence through six sequential stages across two phases:

```
scan_run.status transitions (full chain):
  running → completed → enriched → compacted → mapped
                         (UC-007)   (UC-008)   (UC-009)
                                                  ↓
                                         llm_enriched → blast_radius_computed → velocity_computed
                                           (UC-010)           (UC-011)              (UC-012)

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
EnrichmentPipeline.run()              (UC-007: completed → enriched)
  ↓
CompactionPipeline.run()              (UC-008: enriched → compacted)
  ↓
ControlMappingPipeline.run()          (UC-009: compacted → mapped)
  ↓
LLMEnrichmentPipeline.run()           (UC-010: mapped → llm_enriched)        [Phase 2]
  ↓
BlastRadiusPipeline.run()             (UC-011: llm_enriched → blast_radius_computed) [Phase 2]
  ↓
EPSSVelocityPipeline.run()            (UC-012: blast_radius_computed → velocity_computed) [Phase 2]
  ↓
ScanEnrichmentRepository             (Phase 1 reads/writes + aql_get_epss_history_batch)
ScanLLMEnrichmentRepository          (Phase 2 LLM field writes)              [Phase 2]
ScanBlastRadiusRepository            (Phase 2 blast radius AQL + writes)     [Phase 2]
  ↓
ArangoDB Reference DB                (scan_findings, scan_runs, detected_controls, components, epss_history)
```

### Module Map

| File | Responsibility |
|---|---|
| `src/complira_graph/ingestion/pipeline_coordinator.py` | Orchestrates all 6 stages; reference DB ping; idempotency guards (single-read-at-top pattern); sets `pipeline_failed`/`enrichment_pending` on error |
| `src/complira_graph/ingestion/enrichment_pipeline.py` | UC-007: Traverses reference DB per finding; writes EPSS, KEV, CWE chain, D3FEND; upserts `detected_controls` + edges |
| `src/complira_graph/ingestion/compaction_pipeline.py` | UC-008: Deduplicates findings by CWE; computes composite risk score; assigns `compaction_group_id` and `cluster_rank` |
| `src/complira_graph/ingestion/control_mapping_pipeline.py` | UC-009: Resolves detected controls to frameworks; writes `evidence_chain`; computes `coverage_by_framework` |
| `src/complira_graph/ingestion/llm_enrichment_pipeline.py` | **[Phase 2]** UC-010: Calls Claude Haiku in batches of 10; writes `llm_risk_summary`, `llm_remediation`, `llm_attack_surface`, `llm_enriched_at`; logs token usage |
| `src/complira_graph/ingestion/blast_radius_pipeline.py` | **[Phase 2]** UC-011: Groups findings by purl; traverses INBOUND `depends_on` graph; writes `blast_radius_score`, `affected_components`, `blast_radius_path` |
| `src/complira_graph/ingestion/epss_velocity_pipeline.py` | **[Phase 2]** UC-012: Fetches 30-day EPSS history; pure-Python OLS slope; writes `epss_velocity`, `epss_trend` |
| `src/complira_graph/ingestion/scan_enrichment_repository.py` | Phase 1 AQL reads/writes + `aql_get_epss_history_batch()` (Phase 2 addition) |
| `src/complira_graph/ingestion/scan_llm_enrichment_repository.py` | **[Phase 2]** Write-only repo for LLM fields + token usage |
| `src/complira_graph/ingestion/scan_blast_radius_repository.py` | **[Phase 2]** AQL traversal + blast radius writes |
| `src/complira_graph/ingestion/pipeline_llm_client.py` | **[Phase 2]** Sync Anthropic Claude wrapper; `LLMBatchResult` NamedTuple; response parsing + attack_surface normalization |
| `src/api/v1/endpoints/pipeline.py` | `POST /v1/scans/{scan_run_id}/enrich` — 202 Accepted; queues full 6-stage pipeline as BackgroundTask |

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

---

## UC-010: LLM Enrichment (Phase 2)

**Trigger:** `scan_run.status == "mapped"`
**Outcome status:** `"llm_enriched"`

For every `scan_findings` document, calls the Anthropic Claude Haiku API in sub-batches of 10 findings per prompt:

| Field Written | Description |
|---|---|
| `llm_risk_summary` | ≤3 sentence plain-language risk description tailored to framework context |
| `llm_remediation` | 1–3 actionable remediation steps |
| `llm_attack_surface` | One of: `"network"`, `"local"`, `"adjacent"` (derived from CVSS AV vector or LLM-inferred) |
| `llm_enriched_at` | ISO 8601 UTC timestamp |

On `scan_run`: `llm_token_usage` dict is written with `input_tokens`, `output_tokens`, `total_tokens`, `model`.

**Non-CVE findings:** Context uses `rule_id` + `severity` instead of `cve_id`. Not skipped.

**Failure isolation:** Per-batch LLM failures are logged and skipped. `RuntimeError` is only raised if every sub-batch fails.

**Model:** `claude-haiku-4-5-20251001` (configurable via `ANTHROPIC_MODEL_HAIKU` env var)

---

## UC-011: Blast Radius Simulation (Phase 2)

**Trigger:** `scan_run.status == "llm_enriched"`
**Outcome status:** `"blast_radius_computed"`

For every `scan_findings` document with a non-null `purl`, traverses the INBOUND `depends_on` dependency graph to compute propagation impact:

| Field Written | Description |
|---|---|
| `blast_radius_score` | `len(affected_purls) / max(total_project_components, 1)`, clamped to [0, 1] |
| `affected_components` | List of purls of all reachable dependent components (depth 1–5) |
| `blast_radius_path` | List of component names along the traversal |
| `blast_radius_computed_at` | ISO 8601 UTC timestamp |

Findings with no `purl` (SAST/IaC) receive `blast_radius_score = 0.0` and empty lists.

**Deduplication:** Findings sharing the same `purl` reuse a single AQL traversal — O(unique_purls) database round-trips, not O(findings).

**Score denominator:** Global count of all components reachable via `project_uses_component` edges (cross-project comparability).

---

## UC-012: EPSS Velocity Detection (Phase 2)

**Trigger:** `scan_run.status == "blast_radius_computed"`
**Outcome status:** `"velocity_computed"`

For every `scan_findings` document with a non-null `cve_id`, fetches the last 30 days of EPSS score history and computes a linear regression slope:

| Field Written | Description |
|---|---|
| `epss_velocity` | OLS slope (per-day change in EPSS score) |
| `epss_trend` | `"rising"` if `slope*7 > 0.05`; `"falling"` if `slope*7 < -0.05`; else `"stable"` |
| `epss_velocity_computed_at` | ISO 8601 UTC timestamp |

Findings with no `cve_id` receive `epss_velocity = 0.0` and `epss_trend = "stable"`.

Fewer than 2 EPSS data points in the 30-day window → `epss_velocity = 0.0`, `epss_trend = "stable"`.

**Algorithm:** Pure Python OLS (no numpy/scipy dependency).

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

Triggers the full 6-stage pipeline for an existing scan_run. Valid for scan_runs in status `completed`, `enrichment_pending`, `pipeline_failed`, `mapped`, `llm_enriched`, or `blast_radius_computed`. Phase 2 stages that are already complete are skipped automatically (idempotent).

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
| LLM API error (single batch) | Batch logged and skipped; partial writes retained; pipeline continues |
| LLM API error (all batches) | `RuntimeError("all_llm_batches_failed")` raised; coordinator sets `pipeline_failed` |
| `purl` absent from finding | `blast_radius_score = 0.0`, `affected_components = []`; not an error |
| `depends_on` edges absent | `blast_radius_score = 0.0`; not an error (SBOM not yet ingested) |
| `epss_history` absent for CVE | `epss_velocity = 0.0`, `epss_trend = "stable"`; not an error (EPSS agent not run) |
| Fewer than 2 EPSS data points | `epss_velocity = 0.0`, `epss_trend = "stable"` (insufficient data for regression) |

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
| `scan_findings` | UC-007 (enrichment fields), UC-008 (risk/compaction fields), UC-010 (LLM fields), UC-011 (blast radius fields), UC-012 (velocity fields) |
| `detected_controls` | UC-007 (upsert), UC-009 (framework + evidence_chain) |
| `scan_runs` | All stages (status transitions, coverage_by_framework, llm_token_usage) |
| `finding_triggers_req` (edge) | UC-007 |
| `detected_control_maps_to` (edge) | UC-007 |

### Knowledge Graph Collections (read by pipeline, not written)

`vulnerabilities`, `weaknesses`, `kev_entries`, `epss_history`, `oscal_controls`, `scf_controls`, `attack_techniques`, `d3fend_techniques`, `components`, `project_uses_component`

Edge traversals: `has_weakness`, `child_of`, `aliases`, `maps_to_requirement`, `violates_requirement`, `has_epss`, `d3fend_counters_technique`, `technique_exploits_weakness`, `depends_on` (Phase 2 blast radius, INBOUND), `project_uses_component` (Phase 2 total count)

---

## Performance Notes

- Bulk AQL updates are chunked at ≤ 500 findings per transaction to stay within ArangoDB transaction size limits
- Target: < 30 seconds for 500 findings end-to-end (no hard SLA for Phase 1)
- Redis cache may be used for reference DB traversal results (TTL = 6 hours, per Phase 0 config)

---

## Tests

### Phase 1 Tests

| Test File | Type | Count |
|---|---|---|
| `tests/unit/ingestion/test_scan_enrichment_repository.py` | Unit | 35 (+6 Phase 2 additions) |
| `tests/unit/ingestion/test_enrichment_pipeline.py` | Unit | 22 |
| `tests/unit/ingestion/test_compaction_pipeline.py` | Unit | 26 |
| `tests/unit/ingestion/test_control_mapping_pipeline.py` | Unit | 13 |
| `tests/integration/test_pipeline_phase1.py` | Integration | 24 |

### Phase 2 Tests

| Test File | Type | Count |
|---|---|---|
| `tests/unit/ingestion/test_pipeline_llm_client.py` | Unit | 15 |
| `tests/unit/ingestion/test_scan_llm_enrichment_repository.py` | Unit | 12 |
| `tests/unit/ingestion/test_scan_blast_radius_repository.py` | Unit | 13 |
| `tests/unit/ingestion/test_llm_enrichment_pipeline.py` | Unit | 12 |
| `tests/unit/ingestion/test_blast_radius_pipeline.py` | Unit | 9 |
| `tests/unit/ingestion/test_epss_velocity_pipeline.py` | Unit | 16 |
| `tests/unit/ingestion/test_pipeline_coordinator_phase2.py` | Unit | 15 |
| `tests/e2e/ingestion/test_phase2_pipeline_e2e.py` | Component-Integration | 26 |

**Total: 603 tests passing** (full unit suite)

AC coverage: All 26 Phase 2 ACs (AC-029–AC-054) Passed. All 26 Phase 1 ACs Passed (2 Waived for live ArangoDB).
