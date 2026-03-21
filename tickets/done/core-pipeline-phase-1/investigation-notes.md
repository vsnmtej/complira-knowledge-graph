# Investigation Notes: Core Pipeline Phase 1

**Status:** Complete
**Scope Triage:** `LARGE`
**Last Updated:** 2026-03-21

---

## Sources Consulted

- `src/complira_graph/schema/complira_kg_schema_v2_2.py` — DB_PLACEMENT, TIER1_AQL_TEMPLATES, edge collection names
- `src/complira_graph/ingestion/service.py` — EvidenceIngestionService pipeline sequence
- `src/complira_graph/ingestion/repositories.py` — EvidenceRunRepository (create_run, complete_run, fail_run)
- `src/complira_graph/ingestion/edge_service.py` — EvidenceEdgeService public API
- `src/api/services/enrichment_service.py` — existing per-CVE EnrichmentService (AQL patterns)
- `src/api/v1/endpoints/enrich.py` — existing standalone CVE enrichment endpoint
- `src/api/v1/endpoints/scan.py` — scan ingest endpoint, scan_run status field
- `src/api/core/database.py` — get_reference_db(), get_customer_db() routing
- `src/complira_graph/db.py` — edge collection names: `aliases`, `child_of`, `maps_to_requirement`, `violates_requirement`, `technique_exploits_weakness`, `has_epss`, `has_weakness`

---

## Key Findings

### 1. Reference DB placement (all v2.2 evidence collections)
All Phase 1 target collections are in the **reference DB** (not per-customer DB):
- `scan_findings`, `scan_runs`, `detected_controls` — `tenant_id` field for isolation
- All edge collections (`finding_maps_to_weakness`, `finding_triggers_req`, `detected_control_maps_to`) — also reference DB

`get_reference_db()` is the correct DB handle for all Phase 1 reads and writes.

### 2. scan_run status field and existing transitions
`EvidenceRunRepository.complete_run()` accepts arbitrary `status` string. Current pipeline:
```
running → completed | failed
```
Phase 1 extends this chain:
```
completed → enriched → compacted → mapped
```
`complete_run()` can be called with `status="enriched"` etc — no schema change needed for status field.

### 3. What ingestion already creates (Phase 0 baseline)
- `scan_findings` documents: have `cve_id` (nullable), `rule_id`, `severity`, `tenant_id`, `scan_run_id`, `project_id`
- `finding_maps_to_weakness` edges: created by `EvidenceEdgeService.create_finding_weakness_edges()` when `cwe_id` present in scanner output
- `finding_triggers_req` edges: created by `_create_rule_engine_req_edges()` from Checkov/Semgrep rule IDs
- `detected_controls` documents: created from scanner-detected positive controls

### 4. What Phase 1 needs to add (net-new)
**UC-007 enrichment fields on scan_findings** (not set by ingestion):
- `epss_score`, `epss_percentile` — from `epss_history` via `has_epss` edge
- `in_kev: bool` — from `kev_entries` collection
- `cwe_chain: list[str]` — CVE → CWE via `has_weakness`; CWE → CAPEC via `exploited_by`; CAPEC → ATT&CK
- `d3fend_techniques: list[str]` — ATT&CK → D3FEND via `d3fend_counters_technique`
- `enriched_at: datetime`

**UC-007 new edges** (from reference DB graph traversal, not scanner output):
- `finding_triggers_req` — from CVE → `violates_requirement` traversal (regulatory chain, not just rule_engine)
- `detected_control_maps_to` — map detected_controls to OSCAL/SCF controls

**UC-008 new fields on scan_findings**:
- `risk_score: float` — composite formula
- `compaction_group_id: str` — CWE-keyed group
- `cluster_rank: int` — cluster position sorted by max_risk_score
- `compacted: bool` — True for alias/duplicate findings suppressed

**UC-009 new fields on detected_controls**:
- `framework: str` — NIST 800-53 | ISO 27001 | FDA 510(k) | IEC 62304
- `evidence_chain: list[str]` — finding_id → cwe_id → req_id → control_id
- `control_status: str` — present | absent | partial

**New field on scan_runs** (UC-009):
- `coverage_by_framework: dict[str, float]` — {framework: coverage_pct}

### 5. Key reference DB edge collections for traversal
| Edge | From → To | Used For |
|---|---|---|
| `has_weakness` | vulnerabilities → weaknesses | CVE → CWE |
| `child_of` | weaknesses → weaknesses | CWE roll-up to parent |
| `aliases` | vulnerabilities → vulnerabilities | CVE alias deduplication |
| `maps_to_requirement` | weaknesses → regulatory_requirements | CWE → regulatory |
| `violates_requirement` | vulnerabilities → regulatory_requirements | CVE → regulatory (direct) |
| `technique_exploits_weakness` | attack_techniques → weaknesses | ATT&CK → CWE |
| `d3fend_counters_technique` | d3fend_techniques → attack_techniques | D3FEND → ATT&CK |
| `has_epss` | vulnerabilities → epss_history | CVE → EPSS score |

### 6. Existing per-CVE enrichment service (usable but wrong scope)
`EnrichmentService` in `src/api/services/enrichment_service.py` does single-CVE enrichment via multiple AQL queries. It calls `get_db()` (reference DB singleton). It is NOT scan-run-aware — it doesn't write back to scan_findings or create edges.

Phase 1 does NOT extend `EnrichmentService`. Instead, it builds a **bulk pipeline** that operates on all findings for a `scan_run_id` in one AQL pass per stage.

### 7. Sync vs async execution model
`EvidenceIngestionService.ingest_scan()` runs synchronously (blocking). After ingestion completes and scan_run is `completed`, Phase 1 pipeline can be:
- **Option A**: Triggered automatically as a FastAPI `BackgroundTask` at the end of `ingest_scan` endpoint response
- **Option B**: Triggered explicitly via `POST /v1/scans/{scan_run_id}/enrich`

Both are needed:
- Auto-trigger (Option A) for normal flow: ingestion → enrichment → compaction → mapping without manual intervention
- Manual trigger (Option B) for re-enrichment when reference DB is updated

### 8. Scope triage signals
- 3 new pipeline service files (enrichment, compaction, control mapping)
- 1 new repository file (`scan_enrichment_repository.py`) for bulk reads/writes to scan_findings + detected_controls
- 1 new API endpoint (`pipeline.py` or extend `scan.py`) for manual trigger + status
- 3 complex AQL queries per pipeline stage (bulk, multi-hop traversal)
- Multi-layer impact: endpoint → pipeline service → repository → AQL → edge writes
- Cross-boundary: reference DB reads (knowledge graph) + reference DB writes (evidence layer)

**Triage result: LARGE**

---

## Architecture Implications

### Layer placement decision
Phase 1 pipeline stages are post-ingestion intelligence transformations. They belong in `src/complira_graph/ingestion/` alongside the existing ingestion service:
- `src/complira_graph/ingestion/enrichment_pipeline.py` — UC-007
- `src/complira_graph/ingestion/compaction_pipeline.py` — UC-008
- `src/complira_graph/ingestion/control_mapping_pipeline.py` — UC-009

This keeps the full evidence pipeline in one package. The API layer (`src/api/v1/endpoints/`) only orchestrates trigger + status — it does not contain pipeline logic.

### Repository strategy
A new `ScanEnrichmentRepository` handles bulk reads/writes for the pipeline:
- Bulk fetch findings by scan_run_id + tenant_id
- Bulk update finding fields (EPSS, risk_score, compaction_group_id)
- Bulk upsert detected_controls
- Update scan_run status + coverage fields

This keeps AQL queries co-located with the data they operate on, not scattered in service files.

---

## Open Questions — Resolved

| OQ | Question | Resolution |
|---|---|---|
| OQ-1 | Sync vs async? | Both — auto-trigger via BackgroundTask + manual trigger via API |
| OQ-2 | Latency SLA? | No hard SLA for Phase 1; target < 30s for 500 findings |
| OQ-3 | EPSS latest vs time-series? | Latest via `SORT score_date DESC LIMIT 1` on `has_epss` edge traversal |
| OQ-4 | CWE alias edge name? | `aliases` (vulnerability-to-vulnerability equivalence); CWE dedup uses `child_of` |
| OQ-5 | scan_run status enum? | String field; current values: `running`, `completed`, `failed`. Adding: `enriched`, `compacted`, `mapped` |

---

## Unknowns / Risks

- **Risk-1**: `kev_entries` collection uses `cve_id` with dashes (`CVE-2024-1234`) while `scan_findings.cve_id` may use the same or underscored format — need AQL FILTER that normalizes format
- **Risk-2**: `d3fend_counters_technique` traversal requires ATT&CK techniques to exist for a CVE's CWE; many CVEs have no ATT&CK mapping — pipeline must handle empty traversal gracefully
- **Risk-3**: Bulk AQL update of thousands of `scan_findings` in one transaction may hit ArangoDB transaction size limits — consider batching by 500 findings
- **Risk-4**: `detected_control_maps_to` edges require OSCAL/SCF control documents to exist in reference DB — if knowledge graph agents haven't run, this will produce zero mappings (not an error, but a coverage gap)
