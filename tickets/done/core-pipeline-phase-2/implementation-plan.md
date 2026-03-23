# Implementation Plan: Core Pipeline Phase 2

**Ticket:** `core-pipeline-phase-2`
**Stage:** 6 — Implementation Authorized (Go Confirmed, Code Edit Permission = Unlocked)
**Design Basis:** `proposed-design.md` v1.1
**Call Stack Basis:** `future-state-runtime-call-stack.md` v2
**Last Updated:** 2026-03-22

---

## Requirement → Design → Implementation Traceability

| Requirement | Use Case | Design Section | Implementation Task(s) |
|---|---|---|---|
| REQ-004 (UC-010 LLM Enrichment) | UC-010-* | §5.1 PipelineLLMClient, §5.2 ScanLLMEnrichmentRepository, §5.4 LLMEnrichmentPipeline, §5.7 Coordinator | TASK-1, TASK-2, TASK-4, TASK-8 |
| REQ-005 (UC-011 Blast Radius) | UC-011-* | §5.3 ScanBlastRadiusRepository, §5.5 BlastRadiusPipeline, §5.7 Coordinator | TASK-3, TASK-5, TASK-8 |
| REQ-006 (UC-012 EPSS Velocity) | UC-012-* | §5.8 ScanEnrichmentRepository (add method), §5.6 EPSSVelocityPipeline, §5.7 Coordinator | TASK-6, TASK-7, TASK-8 |
| Cross-cutting (AC-051–054) | UC-CROSS-* | §5.7 Coordinator status guards, §5.9 __init__.py | TASK-8, TASK-9 |

---

## Implementation Sequence (Bottom-Up)

Dependencies flow: repos/client → pipeline stages → coordinator → exports.

| Order | Task ID | File | Change Type | Blocks |
|---|---|---|---|---|
| 1 | TASK-1 | `pipeline_llm_client.py` | New | TASK-4 |
| 2 | TASK-2 | `scan_llm_enrichment_repository.py` | New | TASK-4 |
| 3 | TASK-3 | `scan_blast_radius_repository.py` | New | TASK-5 |
| 4 | TASK-6 | `scan_enrichment_repository.py` (add method) | Modify | TASK-7 |
| 5 | TASK-4 | `llm_enrichment_pipeline.py` | New | TASK-8 |
| 6 | TASK-5 | `blast_radius_pipeline.py` | New | TASK-8 |
| 7 | TASK-7 | `epss_velocity_pipeline.py` | New | TASK-8 |
| 8 | TASK-8 | `pipeline_coordinator.py` | Modify | TASK-9 |
| 9 | TASK-9 | `__init__.py` | Modify | — |

---

## Tasks

### TASK-1 — `pipeline_llm_client.py` (New)

**File:** `src/complira_graph/ingestion/pipeline_llm_client.py`
**Layer:** Repository / External Client
**Requirement:** REQ-004 (AC-035 model, AC-029–031 fields)

**Deliverables:**
- `LLMBatchResult` NamedTuple: `results: list[dict]`, `input_tokens: int`, `output_tokens: int`
- `PipelineLLMClient.__init__(model, max_tokens, api_key)` — sync `anthropic.Anthropic()` client; reads `ANTHROPIC_MODEL_HAIKU` env var for default model
- `PipelineLLMClient.call_batch(findings: list[dict]) -> LLMBatchResult`
  - `_build_system_prompt() -> str`
  - `_build_user_prompt(findings) -> str` — serializes each finding as compact JSON line
  - `_parse_response(raw_text, finding_keys) -> list[dict]` — `json.loads`; fallback to extract from ` ```json ``` ` block; missing keys → empty dict
- On `anthropic.APIError` or `json.JSONDecodeError`: log and re-raise (caller decides skip vs fail)
- No Redis, no async, no dependency on `ClaudeLLMService`

**System prompt:** instructs Claude to return JSON array with keys `finding_key`, `risk_summary`, `remediation`, `attack_surface`.
**Context fields per finding:** `finding_key` (_key), `cve_id` (nullable), `rule_id` (nullable), `severity`, `package_name` (nullable), `cvss_base` (nullable).

**Unit tests** (`tests/ingestion/test_pipeline_llm_client.py`):
- `test_call_batch_success` — mock `anthropic.Anthropic().messages.create()` returning valid JSON; assert result length, field names, token counts
- `test_call_batch_non_cve_finding` — finding with `cve_id=None`; assert rule_id in prompt payload
- `test_call_batch_api_error` — mock raises `anthropic.APIError`; assert re-raises
- `test_call_batch_malformed_json` — mock returns non-JSON; assert re-raises `json.JSONDecodeError` or wraps
- `test_parse_response_missing_key` — response omits one finding_key; assert empty dict for that entry
- `test_parse_response_code_block_fallback` — response wrapped in markdown code block; assert parsed correctly
- `test_attack_surface_normalization` — response returns uppercase "NETWORK"; assert normalized to "network"

---

### TASK-2 — `scan_llm_enrichment_repository.py` (New)

**File:** `src/complira_graph/ingestion/scan_llm_enrichment_repository.py`
**Layer:** Repository
**Requirement:** REQ-004 (AC-029–033, AC-035, AC-036)

**Deliverables:**
- `ScanLLMEnrichmentRepository.__init__(db: StandardDatabase)`
- `bulk_write_llm_fields(updates: list[dict]) -> None`
  - Chunks at 500 per AQL call
  - AQL: `FOR u IN @updates UPDATE u._key WITH u IN scan_findings OPTIONS {keepNull: false}`
  - Log: `scan_llm_enrichment_repo.bulk_write_llm_fields` with `total` + `chunks`
- `write_token_usage(scan_run_id: str, token_usage: dict) -> None`
  - `self._db.collection("scan_runs").update({"_key": scan_run_id, "llm_token_usage": token_usage, "updated_at": utcnow()})`
- `update_scan_run_status(scan_run_key: str, status: str, extra_fields: dict | None = None) -> None`
  - Delegates to `self._db.collection("scan_runs").update({...})`

**Unit tests** (`tests/ingestion/test_scan_llm_enrichment_repository.py`):
- `test_bulk_write_llm_fields_empty` — empty list → no AQL call
- `test_bulk_write_llm_fields_chunking` — 1200 updates → 3 AQL chunks (500+500+200)
- `test_bulk_write_llm_fields_keeppnull_false` — verify AQL string contains `keepNull: false`
- `test_write_token_usage` — mock db.collection.update; assert payload structure
- `test_update_scan_run_status_with_extra` — assert extra_fields merged into update payload

---

### TASK-3 — `scan_blast_radius_repository.py` (New)

**File:** `src/complira_graph/ingestion/scan_blast_radius_repository.py`
**Layer:** Repository
**Requirement:** REQ-005 (AC-037–043)

**Deliverables:**
- `ScanBlastRadiusRepository.__init__(db: StandardDatabase)`
- `aql_blast_radius_for_purl(purl: str, depth_max: int = 5) -> dict`
  - Returns `{"affected_purls": list[str], "affected_names": list[str], "max_depth": int, "found": bool}`
  - On exception: log + return `{"affected_purls": [], "affected_names": [], "max_depth": 0, "found": False}`
  - AQL: LET start = FIRST(components FILTER purl); LET traversal = INBOUND 1..depth_max depends_on; return purls + names + max depth
- `aql_total_project_components(project_id: str | None = None) -> int`
  - On exception: log + return 1
- `bulk_write_blast_radius(updates: list[dict]) -> None`
  - Chunks at 500; `keepNull: false`
- `update_scan_run_status(scan_run_key: str, status: str, extra_fields: dict | None = None) -> None`

**Unit tests** (`tests/ingestion/test_scan_blast_radius_repository.py`):
- `test_aql_blast_radius_found` — mock AQL returns affected_purls + names; assert correct dict shape
- `test_aql_blast_radius_purl_not_in_db` — mock returns found=False; assert empty lists
- `test_aql_blast_radius_exception` — mock raises; assert returns empty dict (no re-raise)
- `test_aql_total_project_components` — mock AQL returns count; assert int
- `test_aql_total_project_components_exception` — mock raises; assert returns 1 (safe fallback)
- `test_bulk_write_blast_radius_chunking` — 600 updates → 2 chunks

---

### TASK-4 — `llm_enrichment_pipeline.py` (New)

**File:** `src/complira_graph/ingestion/llm_enrichment_pipeline.py`
**Layer:** Pipeline
**Requirement:** REQ-004 (AC-029–036)
**Depends on:** TASK-1 (PipelineLLMClient), TASK-2 (ScanLLMEnrichmentRepository), Phase 1 ScanEnrichmentRepository

**Deliverables:**
- `LLMEnrichmentPipeline.__init__(db, repo: ScanEnrichmentRepository, llm_repo: ScanLLMEnrichmentRepository, llm_client: PipelineLLMClient)`
- `run(scan_run_id: str, tenant_id: str) -> None`
  - Fetch findings via `repo.fetch_findings_for_run()`
  - Sub-batch size: 10
  - Per sub-batch: `llm_client.call_batch()` → on exception log + increment `llm_failure_count`, continue
  - `_build_llm_updates(sub_batch, results)` → write via `llm_repo.bulk_write_llm_fields()`
  - Accumulate token counts across all batches
  - After all batches: `llm_repo.write_token_usage()`
  - If all sub-batches failed: raise `RuntimeError("all_llm_batches_failed")`
  - On success: `llm_repo.update_scan_run_status(scan_run_id, "llm_enriched", extra_fields={"llm_enriched_at": utcnow()})`
- `_context_for_finding(finding: dict) -> dict` — CVE path vs non-CVE fallback (rule_id + severity)
- `_build_llm_updates(findings, llm_results) -> list[dict]`
  - Normalize `llm_attack_surface` to lowercase; default `"network"` if invalid/missing
  - None result → write only `llm_enriched_at`

**Unit tests** (`tests/ingestion/test_llm_enrichment_pipeline.py`):
- `test_run_success_all_findings` — mock llm_client.call_batch returning valid results; assert bulk_write_llm_fields called; assert update_scan_run_status("llm_enriched")
- `test_run_non_cve_fallback` — finding with cve_id=None; assert _context_for_finding returns rule_id path; llm called with it
- `test_run_partial_batch_failure` — first sub-batch fails, second succeeds; assert status → "llm_enriched" (AC-034)
- `test_run_all_batches_fail` — all sub-batches raise; assert RuntimeError raised; status NOT set to llm_enriched
- `test_run_idempotent_rewrites` — run twice; second call overwrites fields (upsert semantics, AC-036)
- `test_attack_surface_normalization` — llm returns "ADJACENT"; assert stored as "adjacent"
- `test_attack_surface_invalid_default` — llm returns "physical"; assert stored as "network"
- `test_token_usage_accumulation` — two sub-batches with known token counts; assert write_token_usage called with sum
- `test_context_for_finding_cve` — assert finding_key, cve_id, severity, package_name in output
- `test_context_for_finding_no_cve` — assert finding_key, rule_id, severity in output; cve_id=null

**Integration tests** (`tests/ingestion/test_llm_enrichment_pipeline_integration.py`):
- `test_llm_enrichment_pipeline_end_to_end` — real ArangoDB (test DB), mock Anthropic API, seed scan_findings; run pipeline; assert fields written to DB; assert scan_run status = "llm_enriched"

---

### TASK-5 — `blast_radius_pipeline.py` (New)

**File:** `src/complira_graph/ingestion/blast_radius_pipeline.py`
**Layer:** Pipeline
**Requirement:** REQ-005 (AC-037–043)
**Depends on:** TASK-3 (ScanBlastRadiusRepository), Phase 1 ScanEnrichmentRepository

**Deliverables:**
- `BlastRadiusPipeline.__init__(db, repo: ScanEnrichmentRepository, blast_repo: ScanBlastRadiusRepository)`
- `run(scan_run_id: str, tenant_id: str) -> None`
  - Fetch all findings; group by purl (non-null) vs no-purl
  - `blast_repo.aql_total_project_components()` once
  - For each unique purl: `blast_repo.aql_blast_radius_for_purl(purl)` → compute score
  - `_build_blast_updates_for_purl(fingerprints, traversal_result, score)` for purl findings
  - `_build_zero_blast_updates(no_purl_fingerprints)` for no-purl findings
  - `blast_repo.bulk_write_blast_radius(all_updates)` — single bulk call
  - `blast_repo.update_scan_run_status(scan_run_id, "blast_radius_computed", extra_fields={"blast_radius_computed_at": utcnow()})`
- `_build_blast_updates_for_purl(fingerprints, traversal_result, score) -> list[dict]`
  - `affected_components = traversal_result["affected_purls"]`
  - `blast_radius_path = traversal_result["affected_names"]`
- `_build_zero_blast_updates(fingerprints) -> list[dict]`
  - score=0.0, affected_components=[], blast_radius_path=[]

**Unit tests** (`tests/ingestion/test_blast_radius_pipeline.py`):
- `test_run_with_purl_findings` — mock blast_repo.aql_blast_radius_for_purl returning dependents; assert score formula (AC-041); assert bulk_write called
- `test_run_no_purl_findings` — findings with null purl; assert zero scores written (AC-038)
- `test_run_purl_no_edges` — mock returns found=True but empty affected_purls; assert score=0.0 (AC-039 edge)
- `test_run_purl_deduplication` — 3 findings share same purl; assert aql_blast_radius_for_purl called once (UC-DR-BLAST-DEDUP)
- `test_run_score_clamped_to_one` — affected_components > total_components; assert score=1.0 (AC-041 clamp)
- `test_run_status_transition` — assert update_scan_run_status("blast_radius_computed") called at end (AC-042)
- `test_run_idempotent` — run twice; same scores; no error (AC-043)
- `test_run_mixed_purl_and_no_purl` — both types in same batch; assert correct split and writes

**Integration tests** (`tests/ingestion/test_blast_radius_pipeline_integration.py`):
- `test_blast_radius_pipeline_end_to_end` — real ArangoDB (test DB); seed components + depends_on edges; run pipeline; assert blast_radius_score written; assert status = "blast_radius_computed"

---

### TASK-6 — `scan_enrichment_repository.py` — add `aql_get_epss_history_batch`

**File:** `src/complira_graph/ingestion/scan_enrichment_repository.py`
**Change:** Add one method; no other changes
**Requirement:** REQ-006

**Deliverables:**
- `aql_get_epss_history_batch(cve_keys: list[str], cutoff_date: str) -> dict[str, list[dict]]`
  - Returns `{cve_key: [{"score": float, "date": "YYYY-MM-DD"}, ...]}` sorted ascending by date
  - Missing CVEs (no vulnerability doc): key absent from result (empty list semantics)
  - On exception: log `scan_enrichment_repo.aql_get_epss_history_batch_failed`; return `{}`
  - AQL: `FOR cve_key IN @cve_keys` → `DOCUMENT(CONCAT("vulnerabilities/", cve_key))` → `FOR e IN has_epss FILTER e._from == cve_doc._id` → `FILTER point.score_date >= @cutoff_date SORT point.score_date ASC`

**Unit tests** (append to `tests/ingestion/test_scan_enrichment_repository.py`):
- `test_aql_get_epss_history_batch_returns_timeseries` — mock AQL returns list of score+date dicts per CVE; assert structure
- `test_aql_get_epss_history_batch_empty_cve_list` — empty input → returns `{}`
- `test_aql_get_epss_history_batch_exception` — mock AQL raises; returns `{}`
- `test_aql_get_epss_history_batch_missing_cve` — CVE key not in DB; assert absent from result dict

---

### TASK-7 — `epss_velocity_pipeline.py` (New)

**File:** `src/complira_graph/ingestion/epss_velocity_pipeline.py`
**Layer:** Pipeline
**Requirement:** REQ-006 (AC-044–050)
**Depends on:** TASK-6 (aql_get_epss_history_batch on ScanEnrichmentRepository)

**Deliverables:**
- `EPSSVelocityPipeline.__init__(db, repo: ScanEnrichmentRepository)`
- `run(scan_run_id: str, tenant_id: str) -> None`
  - Fetch all findings; group by cve_key (normalize: `CVE-2024-1234` → `CVE_2024_1234`) vs no-cve
  - `cutoff_date = (datetime.now(utc) - timedelta(days=30)).strftime("%Y-%m-%d")`
  - `history_map = repo.aql_get_epss_history_batch(cve_keys, cutoff_date)`
  - For each cve_key: `slope = _compute_slope(history_map.get(cve_key, []))` → `trend = _classify_trend(slope)`
  - `_build_velocity_updates(fingerprints, slope, trend)` for CVE findings
  - `_build_zero_velocity_updates(no_cve_fingerprints)` for no-CVE findings
  - `repo.bulk_update_findings(all_updates)` — reuse Phase 1 write method
  - `repo.update_scan_run_status(scan_run_id, "velocity_computed", extra_fields={"velocity_computed_at": utcnow()})`
- `_compute_slope(history: list[dict]) -> float`
  - `n < 2` → return 0.0
  - Pure Python linear regression: `xs = range(n)`, `ys = [h["score"] for h in history]`
  - `denominator == 0` → return 0.0
- `_classify_trend(slope: float) -> str`
  - `slope * 7 > 0.05` → "rising"
  - `slope * 7 < -0.05` → "falling"
  - else → "stable"
- `_build_velocity_updates(fingerprints, slope, trend) -> list[dict]`
- `_build_zero_velocity_updates(fingerprints) -> list[dict]` — velocity=0.0, trend="stable"

**Unit tests** (`tests/ingestion/test_epss_velocity_pipeline.py`):
- `test_compute_slope_rising` — history with clear upward trend; assert slope > 0 and classify_trend = "rising"
- `test_compute_slope_falling` — downward trend; assert "falling"
- `test_compute_slope_stable` — flat line; assert "stable"
- `test_compute_slope_insufficient_data_zero` — 0 or 1 data points; assert slope=0.0, trend="stable" (AC-048)
- `test_compute_slope_denominator_zero` — all same x value; assert 0.0 (no ZeroDivisionError)
- `test_run_no_cve_findings` — findings with null cve_id; assert velocity=0.0 trend=stable (AC-045)
- `test_run_empty_epss_history` — history_map returns empty lists; all stable (AC-048 empty-history variant)
- `test_run_rising_threshold` — slope = 0.0072 (weekly delta 0.0504 > 0.05); assert "rising" (AC-046)
- `test_run_falling_threshold` — slope = -0.0072 (weekly delta < -0.05); assert "falling" (AC-047)
- `test_run_status_transition` — assert update_scan_run_status("velocity_computed") called (AC-049)
- `test_run_idempotent` — run twice with same history_map; same results (AC-050)
- `test_run_cve_normalization` — finding with cve_id="CVE-2024-1234"; assert cve_key="CVE_2024_1234" used for lookup

**Integration tests** (`tests/ingestion/test_epss_velocity_pipeline_integration.py`):
- `test_epss_velocity_pipeline_end_to_end` — real ArangoDB (test DB); seed vulnerabilities + has_epss + epss_history docs; run pipeline; assert velocity fields written; assert status = "velocity_computed"

---

### TASK-8 — `pipeline_coordinator.py` (Modify)

**File:** `src/complira_graph/ingestion/pipeline_coordinator.py`
**Change:** Status guard extension + Phase 2 stage wiring
**Requirement:** All (AC-051–054, pipeline chain)

**Deliverables — status constants delta:**
```python
_RETRIABLE_STATUSES: add "mapped", "llm_enriched", "blast_radius_computed"
_ENRICHMENT_DONE: add "llm_enriched", "blast_radius_computed", "velocity_computed"
_COMPACTION_DONE: add "llm_enriched", "blast_radius_computed", "velocity_computed"
_MAPPING_DONE:    add "llm_enriched", "blast_radius_computed", "velocity_computed"
_LLM_DONE   = frozenset({"llm_enriched", "blast_radius_computed", "velocity_computed"})
_BLAST_DONE = frozenset({"blast_radius_computed", "velocity_computed"})
_VELOCITY_DONE = frozenset({"velocity_computed"})
```

**Deliverables — `__init__` delta:**
```python
# Phase 2 additions:
self._llm_repo     = ScanLLMEnrichmentRepository(db)
self._blast_repo   = ScanBlastRadiusRepository(db)
self._llm_client   = PipelineLLMClient()
self._llm_enrichment  = LLMEnrichmentPipeline(db, self._repo, self._llm_repo, self._llm_client)
self._blast_radius    = BlastRadiusPipeline(db, self._repo, self._blast_repo)
self._epss_velocity   = EPSSVelocityPipeline(db, self._repo)
```

**Deliverables — `run_post_ingest_pipeline` delta:**
- After Stage 3 block, add Stage 4/5/6 blocks using single-read `current_status` (from top of method)
- No re-reads between Phase 2 stages (single-read-at-top pattern per v1.1 design)
- Each Phase 2 stage block: `if force or current_status not in _X_DONE: try/except → _mark_failed; else: skip log`

**Deliverables — module docstring delta:**
- Update Stage sequence line to include Phase 2 stages
- Update Status chain line to include Phase 2 statuses

**Unit tests** (append to `tests/ingestion/test_pipeline_coordinator.py`):
- `test_phase2_runs_after_mapped` — mock Phase 1 stages as no-ops; initial status = "mapped"; assert all 3 Phase 2 stages called in order (AC-051)
- `test_phase2_skipped_when_velocity_computed` — initial status = "velocity_computed"; assert no Phase 2 stage called
- `test_phase2_retrigger_from_llm_enriched` — initial status = "llm_enriched"; assert only blast+velocity called (AC-052)
- `test_phase2_retrigger_from_blast_radius_computed` — initial status = "blast_radius_computed"; assert only velocity called (AC-052)
- `test_phase2_llm_failure_marks_pipeline_failed` — llm_enrichment.run() raises; assert _mark_failed called; blast+velocity NOT called (AC-053)
- `test_phase2_blast_failure_marks_pipeline_failed` — blast_radius.run() raises; assert _mark_failed; velocity NOT called (AC-053)
- `test_phase2_force_reruns_all` — force=True with status "velocity_computed"; assert all 3 Phase 2 stages called
- `test_retriable_statuses_include_phase2` — assert "mapped", "llm_enriched", "blast_radius_computed" in _RETRIABLE_STATUSES (AC-052)

**Integration tests:**
- `test_coordinator_full_phase2_chain` — real DB; seed scan_run with status "mapped"; run coordinator; assert final status = "velocity_computed" (with mocked Anthropic API)

---

### TASK-9 — `__init__.py` (Modify)

**File:** `src/complira_graph/ingestion/__init__.py`
**Change:** Export 6 new public symbols

**Deliverables:**
- Add imports for: `PipelineLLMClient`, `ScanLLMEnrichmentRepository`, `ScanBlastRadiusRepository`, `LLMEnrichmentPipeline`, `BlastRadiusPipeline`, `EPSSVelocityPipeline`
- Add all 6 to `__all__`
- Update module docstring

**No separate tests needed** — covered by coordinator integration tests.

---

## File Build State Reference

| Task | File | Status |
|---|---|---|
| TASK-1 | `src/complira_graph/ingestion/pipeline_llm_client.py` | Pending |
| TASK-2 | `src/complira_graph/ingestion/scan_llm_enrichment_repository.py` | Pending |
| TASK-3 | `src/complira_graph/ingestion/scan_blast_radius_repository.py` | Pending |
| TASK-6 | `src/complira_graph/ingestion/scan_enrichment_repository.py` (add method) | Pending |
| TASK-4 | `src/complira_graph/ingestion/llm_enrichment_pipeline.py` | Pending |
| TASK-5 | `src/complira_graph/ingestion/blast_radius_pipeline.py` | Pending |
| TASK-7 | `src/complira_graph/ingestion/epss_velocity_pipeline.py` | Pending |
| TASK-8 | `src/complira_graph/ingestion/pipeline_coordinator.py` (modify) | Pending |
| TASK-9 | `src/complira_graph/ingestion/__init__.py` (modify) | Pending |

---

## Test Files

| Test File | Covers | Type |
|---|---|---|
| `tests/ingestion/test_pipeline_llm_client.py` | TASK-1 | Unit |
| `tests/ingestion/test_scan_llm_enrichment_repository.py` | TASK-2 | Unit |
| `tests/ingestion/test_scan_blast_radius_repository.py` | TASK-3 | Unit |
| `tests/ingestion/test_scan_enrichment_repository.py` (append) | TASK-6 | Unit |
| `tests/ingestion/test_llm_enrichment_pipeline.py` | TASK-4 | Unit |
| `tests/ingestion/test_blast_radius_pipeline.py` | TASK-5 | Unit |
| `tests/ingestion/test_epss_velocity_pipeline.py` | TASK-7 | Unit |
| `tests/ingestion/test_pipeline_coordinator.py` (append) | TASK-8 | Unit |
| `tests/ingestion/test_llm_enrichment_pipeline_integration.py` | TASK-4 | Integration |
| `tests/ingestion/test_blast_radius_pipeline_integration.py` | TASK-5 | Integration |
| `tests/ingestion/test_epss_velocity_pipeline_integration.py` | TASK-7 | Integration |

---

## Out of Scope

- Changes to API routes (POST /enrich already supports Phase 2 via extended `_RETRIABLE_STATUSES`)
- Database schema migration (new fields are nullable; no collection changes required)
- Frontend changes
- Knowledge graph agent execution (reference DB population is outside this ticket)
