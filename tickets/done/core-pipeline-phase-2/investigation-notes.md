# Investigation Notes: Core Pipeline Phase 2

**Status:** Complete
**Scope Triage:** `LARGE`
**Last Updated:** 2026-03-22

---

## Sources Consulted

- `src/complira_graph/ingestion/pipeline_coordinator.py` — Phase 1 coordinator structure, status constants, idempotency guards
- `src/complira_graph/ingestion/scan_enrichment_repository.py` — Phase 1 repository pattern, constructor, AQL patterns
- `src/complira_graph/ingestion/enrichment_pipeline.py` — Phase 1 pipeline stage pattern
- `src/complira_graph/models/evidence.py` — ScanRun, V22Finding, purl field
- `src/complira_graph/models.py` — EPSSHistory model (cve_id, epss_score, score_date, percentile)
- `src/complira_graph/schema/complira_kg_schema_v2_2.py` — DB_PLACEMENT, edge schemas, blast radius AQL templates
- `src/complira_graph/db.py` — edge collection names (has_epss, has_epss_history, depends_on, project_uses_component)
- `src/api/services/llm.py` — ClaudeLLMService: constructor, _call_claude(), analyze_vulnerability(), Redis caching
- `src/api/core/database.py` — get_reference_db()

---

## Key Findings

### 1. Phase 1 Pipeline Coordinator — Extension Pattern

`PipelineCoordinator.__init__(db: StandardDatabase)` instantiates all 3 stage objects and wires them:
```python
self._enrichment = EnrichmentPipeline(db, self._repo)
self._compaction  = CompactionPipeline(db, self._repo)
self._control_mapping = ControlMappingPipeline(db, self._repo)
```

Status constants (from `pipeline_coordinator.py` lines 31–44):
- `_RETRIABLE_STATUSES = {"completed", "enriched", "compacted", "pipeline_failed", "enrichment_pending"}`
- Idempotency guards: `_ENRICHMENT_DONE = {"enriched", "compacted", "mapped"}`, `_COMPACTION_DONE = {"compacted", "mapped"}`, `_MAPPING_DONE = {"mapped"}`

**Phase 2 extension approach:** `PipelineCoordinator` must be modified to:
1. Add `_LLM_DONE`, `_BLAST_DONE`, `_VELOCITY_DONE` guard sets
2. Extend `_RETRIABLE_STATUSES` with `"mapped"`, `"llm_enriched"`, `"blast_radius_computed"`
3. Instantiate 3 new pipeline objects: `LLMEnrichmentPipeline`, `BlastRadiusPipeline`, `EPSSVelocityPipeline`
4. The Phase 2 stages run after `mapped` status, not after `completed`

### 2. Repository Separation (per Phase 1 code-review.md)

Phase 1 code-review explicitly noted: "if Phase 2 adds LLM-enrichment writes (a new write concern), extract a `ScanLLMEnrichmentRepository` at that time."

**Decision confirmed:** Phase 2 introduces 2 new repositories:
- `ScanLLMEnrichmentRepository` — LLM field writes to `scan_findings` (llm_risk_summary, llm_remediation, llm_attack_surface)
- `ScanBlastRadiusRepository` — blast radius AQL traversal + writes (blast_radius_score, affected_components, blast_radius_path)

EPSS velocity writes can share `ScanEnrichmentRepository` (reads epss_history, writes epss_velocity back to scan_findings — same concern as Phase 1 EPSS reads). OR a 3rd repo if line count warrants.

### 3. LLM Service — Existing Pattern

`ClaudeLLMService` at `src/api/services/llm.py`:
- `async def _call_claude(prompt, system, schema)` — core method using `anthropic.Anthropic().messages.create()`
- Currently uses `"claude-3-5-sonnet-20241022"` — Phase 2 will use `"claude-haiku-4-5-20251001"` for cost control (per .env: `ANTHROPIC_MODEL_HAIKU=claude-haiku-4-5`)
- Redis caching (24h TTL) — Phase 2 will cache per `(cve_id, framework)` key
- `ClaudeLLMService` is **async** (API-layer service). Pipeline stages are **sync** (run in BackgroundTask)

**Key decision required:** Phase 2 `LLMEnrichmentPipeline` must call the Anthropic API. Options:
- **Option A**: Use `asyncio.run()` inside sync pipeline to call async `ClaudeLLMService._call_claude()`
- **Option B**: Create a sync `PipelineLLMClient` that calls `anthropic.Anthropic().messages.create()` directly (sync client, no Redis)
- **Option C**: Use `anthropic.Anthropic()` sync client directly in `LLMEnrichmentPipeline` (no Redis caching)

Option B is cleanest: a dedicated `PipelineLLMClient` wrapper in `src/complira_graph/ingestion/` that uses the sync Anthropic client and does NOT depend on the Redis-backed async `ClaudeLLMService`. Keeps pipeline layer independent of API service layer.

### 4. Blast Radius Graph — Edge Collections

Both `project_uses_component` and `depends_on` edges are in the **reference DB** (DB_PLACEMENT, lines 87, 89).

**Traversal plan for UC-011:**
1. Find component by `purl`: `FOR c IN components FILTER c.purl == @purl`
2. Find all components that depend on it (inbound `depends_on` traversal): `FOR dep IN 1..5 INBOUND c depends_on`
3. Count project usages of affected components via `project_uses_component` (tenant-scoped)
4. `blast_radius_score = len(affected_components) / total_project_components`

**Depth cap:** AQL `1..5` hops (max 5 hops in `depends_on` traversal) to prevent runaway on large graphs.

**Risk:** `depends_on` edges are only populated when SBOM (CycloneDX) scans are ingested. If no SBOM, blast radius = 0 for all findings — correct behavior (not an error).

**Note:** `purl` field on `scan_findings` is only populated by Grype/SCA scanner adapter. SAST findings (Semgrep, Checkov) have no `purl` — blast radius = 0 for those.

### 5. EPSS Velocity — Data Model

`EPSSHistory` model in `src/complira_graph/models.py` (line 242):
- Fields: `cve_id: str`, `epss_score: float`, `percentile: float`, `score_date: str` (ISO YYYY-MM-DD)
- Key: `{normalized_cve_id}_{YYYY_MM_DD}` — one document per CVE per day

**Velocity AQL pattern:**
```aql
FOR e IN has_epss
  FILTER e._from == CONCAT("vulnerabilities/", @cve_key)
  LET doc = DOCUMENT(e._to)
  FILTER doc.score_date >= @cutoff_date
  SORT doc.score_date ASC
  RETURN { score: doc.epss_score, date: doc.score_date }
```

Linear regression slope = `(sum(x*y) - n*mean_x*mean_y) / (sum(x^2) - n*mean_x^2)` where x = day index, y = epss_score. No numpy required — pure Python.

**Threshold (from requirements draft):** `delta > 0.05 over 7-day window = "rising"`. Using slope approach: `slope * 7 > 0.05` → rising, `slope * 7 < -0.05` → falling, else → stable.

### 6. Phase 1 scan_run Status Extension

Current Phase 1 terminal status: `"mapped"`.

Phase 2 extends the chain:
```
mapped → llm_enriched → blast_radius_computed → velocity_computed
```

`EvidenceRunRepository.complete_run()` accepts arbitrary status string — no schema change needed.

Phase 2 must add retriable statuses: `"mapped"`, `"llm_enriched"`, `"blast_radius_computed"`.

### 7. `epss_history` Edge Name Ambiguity

`src/complira_graph/db.py` lists both `"has_epss"` and `"has_epss_history"` as edge collections. Phase 1 `scan_enrichment_repository.py` uses `has_epss`. This is the correct edge for velocity detection too.

### 8. Scope Triage Signals

- 3 new pipeline stage files (LLMEnrichmentPipeline, BlastRadiusPipeline, EPSSVelocityPipeline)
- 2 new repository files (ScanLLMEnrichmentRepository, ScanBlastRadiusRepository)
- 1 new LLM client wrapper (PipelineLLMClient — sync Anthropic client for pipeline layer)
- 1 modified file (PipelineCoordinator — add 3 stage slots + status guard sets)
- Multi-layer impact: coordinator → pipeline → repository → LLM API / AQL → writes
- Cross-boundary: LLM API (external), ArangoDB reference DB (internal), epss_history time-series

**Triage result: LARGE**

---

## Architecture Implications

### Layer Placement
All Phase 2 pipeline stages belong in `src/complira_graph/ingestion/` alongside Phase 1:
- `src/complira_graph/ingestion/llm_enrichment_pipeline.py` — UC-010
- `src/complira_graph/ingestion/blast_radius_pipeline.py` — UC-011
- `src/complira_graph/ingestion/epss_velocity_pipeline.py` — UC-012
- `src/complira_graph/ingestion/scan_llm_enrichment_repository.py` — LLM field writes
- `src/complira_graph/ingestion/scan_blast_radius_repository.py` — blast radius AQL + writes
- `src/complira_graph/ingestion/pipeline_llm_client.py` — sync Anthropic client wrapper

### Repository Allocation
| Repository | Responsibility |
|---|---|
| `ScanEnrichmentRepository` (Phase 1, unchanged) | EPSS/KEV/CWE reads + bulk writes; add `aql_get_epss_history()` for 30-day time series |
| `ScanLLMEnrichmentRepository` (new) | Write llm_risk_summary, llm_remediation, llm_attack_surface to scan_findings |
| `ScanBlastRadiusRepository` (new) | AQL traversal of depends_on + project_uses_component; write blast_radius fields |

EPSS velocity reads can extend `ScanEnrichmentRepository` (adding `aql_get_epss_history_batch()`); velocity writes to `scan_findings` go via `ScanEnrichmentRepository.bulk_update_findings()`.

### PipelineLLMClient Rationale
`ClaudeLLMService` is async and Redis-backed — designed for API request/response cycle. The pipeline runs in `BackgroundTask` (sync context). Creating a minimal `PipelineLLMClient` in the ingestion layer avoids a cross-layer dependency on the API services layer, keeps the pipeline independently testable, and uses the sync `anthropic.Anthropic()` client directly.

---

## Open Questions — Resolved

| OQ | Question | Resolution |
|---|---|---|
| OQ-1 | Extend ClaudeLLMService or new client? | New `PipelineLLMClient` (sync, no Redis) in ingestion layer — cleaner SoC |
| OQ-2 | Which Anthropic model for Phase 2? | `claude-haiku-4-5-20251001` (from .env `ANTHROPIC_MODEL_HAIKU`) for cost control |
| OQ-3 | depends_on direction for blast radius? | INBOUND traversal from vulnerable component (who depends on it?) |
| OQ-4 | EPSS velocity: numpy or pure Python? | Pure Python linear regression (no extra dependency) |
| OQ-5 | EPSS velocity repo: new or extend Phase 1? | Extend `ScanEnrichmentRepository` with `aql_get_epss_history_batch()` method |

---

## Unknowns / Risks

- **Risk-1**: `depends_on` edges only populated by SBOM ingestion — blast radius will be 0 for all findings if no SBOM has been ingested. This is correct behavior but may appear as a bug to users. Needs clear documentation.
- **Risk-2**: LLM calls per-finding are expensive in time; 500 findings × ~0.5s/call = 4+ minutes. Need batching strategy (send 10 findings per prompt, not 1).
- **Risk-3**: `epss_history` collection may be empty (agents not run) — velocity returns `stable` for all findings. Correct behavior.
- **Risk-4**: Phase 1 `PipelineCoordinator.run_post_ingest_pipeline()` is called from both scan.py (auto) and pipeline.py (manual). Phase 2 stages should run in the same call — no new API endpoint needed; `POST /v1/scans/{id}/enrich` already re-triggers the full coordinator.
- **Risk-5**: LLM enrichment with no `cve_id` — pipeline must fall back to rule_id + severity for context. LLM prompt must handle both CVE and non-CVE findings gracefully.
