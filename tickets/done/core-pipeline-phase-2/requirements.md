# Requirements: Core Pipeline Phase 2

**Status:** `Design-ready`
**Last Updated:** 2026-03-22
**Ticket:** core-pipeline-phase-2
**Scope:** `LARGE`

---

## Goal / Problem Statement

Phase 1 delivered a deterministic three-stage post-ingestion pipeline (`completed → enriched → compacted → mapped`). Phase 2 adds three intelligence layers that extend the pipeline beyond `mapped`:

1. **UC-010 LLM Enrichment** — Use the Anthropic Claude API (Haiku model) to generate plain-language risk summaries, remediation guidance, and attack surface classification per finding.
2. **UC-011 Blast Radius Simulation** — Traverse the `depends_on` and `project_uses_component` component dependency graph to compute how widely a vulnerable component's impact propagates.
3. **UC-012 EPSS Velocity Detection** — Query `epss_history` for 30-day time series per CVE and compute trend slope (rising/stable/falling).

Phase 2 status chain extension: `mapped → llm_enriched → blast_radius_computed → velocity_computed`

---

## Scope Triage

**Classification:** `LARGE`

Signals:
- 3 new pipeline stage files
- 2 new repository files + 1 new LLM client wrapper
- 1 modified file (PipelineCoordinator — 3 new stage slots + status guards)
- External API boundary (Anthropic Claude)
- Multi-hop AQL traversal (depends_on depth 1..5)
- Time-series computation (EPSS 30-day linear regression)
- Cross-layer impact: coordinator → pipeline → repository → LLM API / ArangoDB graph

---

## In-Scope Use Cases

### UC-010: LLM Enrichment
**REQ-004**
**Actor:** Pipeline (auto, runs after UC-009)
**Trigger:** `scan_run.status == "mapped"`
**Expected outcome:**
- Every `scan_findings` document receives: `llm_risk_summary` (≤3 sentences), `llm_remediation` (1–3 steps), `llm_attack_surface` ∈ {network, local, adjacent}, `llm_enriched_at`
- Findings with no `cve_id` use `rule_id` + `severity` as LLM context (no skip)
- If LLM call fails for a finding: log and skip that finding; pipeline continues; partial writes retained
- LLM calls use `claude-haiku-4-5` model; token usage logged to `scan_run`
- Findings processed in batches of 10 per LLM prompt to control latency and cost
- `scan_run.status` transitions to `"llm_enriched"`

### UC-011: Blast Radius Simulation
**REQ-005**
**Actor:** Pipeline (auto, runs after UC-010)
**Trigger:** `scan_run.status == "llm_enriched"`
**Expected outcome:**
- Every `scan_findings` document with non-null `purl` receives: `blast_radius_score` ∈ [0, 1], `affected_components` (list of purls), `blast_radius_path` (list of component names, longest propagation path), `blast_radius_computed_at`
- Findings with no `purl`: `blast_radius_score = 0.0`, `affected_components = []`, `blast_radius_path = []`
- Traversal uses INBOUND `depends_on` edges from the vulnerable component, depth cap 1..5 hops
- `blast_radius_score = len(affected_components) / max(total_project_components, 1)`
- `scan_run.status` transitions to `"blast_radius_computed"`

### UC-012: EPSS Velocity Detection
**REQ-006**
**Actor:** Pipeline (auto, runs after UC-011)
**Trigger:** `scan_run.status == "blast_radius_computed"`
**Expected outcome:**
- Every `scan_findings` document with non-null `cve_id` receives: `epss_velocity` (float slope), `epss_trend` ∈ {rising, stable, falling}, `epss_velocity_computed_at`
- Findings with no `cve_id`: `epss_velocity = 0.0`, `epss_trend = "stable"`
- Velocity = linear regression slope over last 30 days of `epss_history` data (pure Python, no numpy)
- Threshold: `slope * 7 > 0.05` → "rising"; `slope * 7 < -0.05` → "falling"; else → "stable"
- If fewer than 2 data points in 30-day window: `epss_velocity = 0.0`, `epss_trend = "stable"`
- `scan_run.status` transitions to `"velocity_computed"`

---

## Acceptance Criteria

### UC-010 — LLM Enrichment

| AC-ID | Criterion | Measurable Expected Outcome |
|---|---|---|
| AC-029 | Risk summary populated | Every finding in scan_run has `llm_risk_summary` (non-empty string) after LLM enrichment |
| AC-030 | Remediation populated | Every finding has `llm_remediation` (non-empty string) |
| AC-031 | Attack surface classified | Every finding has `llm_attack_surface` ∈ {"network", "local", "adjacent"} |
| AC-032 | Non-CVE findings handled | Findings with no `cve_id` receive LLM output using `rule_id` + `severity` as context; no skip |
| AC-033 | Status transitions to `llm_enriched` | `scan_runs.status == "llm_enriched"` after pipeline completes |
| AC-034 | LLM failure isolation | If LLM call fails for a finding, that finding is logged and skipped; remaining findings continue; `pipeline_failed` only if ALL findings fail |
| AC-035 | Haiku model used | LLM calls use `claude-haiku-4-5-20251001`; token usage stored in `scan_run.llm_token_usage` |
| AC-036 | Idempotent | Re-running LLM enrichment for same `scan_run_id` does not create duplicate entries; `bulk_update_findings` upsert semantics |

### UC-011 — Blast Radius Simulation

| AC-ID | Criterion | Measurable Expected Outcome |
|---|---|---|
| AC-037 | Blast radius computed for SCA findings | Every finding with non-null `purl` has `blast_radius_score` ∈ [0, 1] |
| AC-038 | SAST/IaC findings handled | Findings with no `purl` have `blast_radius_score = 0.0`, `affected_components = []` |
| AC-039 | Affected components list correct | `affected_components` contains purls of all components reachable via INBOUND `depends_on` traversal (max depth 5) |
| AC-040 | Propagation path returned | `blast_radius_path` is a list of component names along the longest traversal chain |
| AC-041 | Score formula | `blast_radius_score = len(affected_components) / max(total_project_components, 1)` clamped to [0, 1] |
| AC-042 | Status transitions to `blast_radius_computed` | `scan_runs.status == "blast_radius_computed"` after pipeline completes |
| AC-043 | Idempotent | Re-running blast radius simulation produces identical scores for same dependency graph state |

### UC-012 — EPSS Velocity Detection

| AC-ID | Criterion | Measurable Expected Outcome |
|---|---|---|
| AC-044 | Velocity computed for CVE findings | Every finding with non-null `cve_id` has `epss_velocity` (float) and `epss_trend` ∈ {"rising", "stable", "falling"} |
| AC-045 | Non-CVE findings handled | Findings with no `cve_id` have `epss_velocity = 0.0`, `epss_trend = "stable"` |
| AC-046 | Rising threshold | `epss_trend = "rising"` when `epss_velocity * 7 > 0.05` |
| AC-047 | Falling threshold | `epss_trend = "falling"` when `epss_velocity * 7 < -0.05` |
| AC-048 | Insufficient history | If fewer than 2 data points in 30-day window, `epss_velocity = 0.0`, `epss_trend = "stable"` |
| AC-049 | Status transitions to `velocity_computed` | `scan_runs.status == "velocity_computed"` after pipeline completes |
| AC-050 | Idempotent | Re-running velocity detection produces same results for same `epss_history` data |

### Cross-Cutting

| AC-ID | Criterion | Measurable Expected Outcome |
|---|---|---|
| AC-051 | Pipeline chain | Phase 2 runs automatically after Phase 1 completes; `mapped → llm_enriched → blast_radius_computed → velocity_computed` without manual intervention |
| AC-052 | Manual re-trigger | `POST /v1/scans/{scan_run_id}/enrich` re-triggers full pipeline including Phase 2 stages for scan_runs in status `mapped`, `llm_enriched`, `blast_radius_computed`, `pipeline_failed` |
| AC-053 | Pipeline failure isolation | If any Phase 2 stage fails, `scan_run.status = "pipeline_failed"`; partial writes retained |
| AC-054 | tenant_id scoping | All Phase 2 reads and writes include `tenant_id` filter |

---

## Constraints / Dependencies

- Phase 1 `mapped` status is the Phase 2 trigger — Phase 2 stages cannot run before Phase 1 completes
- `PipelineLLMClient` must use sync `anthropic.Anthropic()` client (pipeline runs in sync BackgroundTask context)
- Must NOT depend on `ClaudeLLMService` (API services layer) — keep pipeline layer independent
- LLM model: `claude-haiku-4-5-20251001` (from .env `ANTHROPIC_MODEL_HAIKU`)
- `depends_on` traversal capped at depth 5 to prevent runaway on large graphs (Risk-1)
- `epss_history` may be empty if EPSS agent hasn't run — velocity returns `stable` for all; not an error
- `project_uses_component` and `depends_on` are in the reference DB — `get_reference_db()` handle applies
- EPSS velocity uses pure Python linear regression (no numpy/scipy dependency)

---

## Assumptions

- `PipelineCoordinator.__init__` will be modified to instantiate Phase 2 pipeline objects
- `ScanEnrichmentRepository` is extended with `aql_get_epss_history_batch()` for 30-day time-series fetch
- `EvidenceRunRepository.complete_run()` accepts `"llm_enriched"`, `"blast_radius_computed"`, `"velocity_computed"` as valid status strings (confirmed — accepts arbitrary string)
- Token usage tracking uses `update_scan_run()` on `scan_runs` — new field `llm_token_usage: dict`

---

## Open Questions / Risks

- **Risk-1**: `depends_on` edges empty if no SBOM ingested — blast radius 0 for all findings (correct, documented)
- **Risk-2**: LLM latency for large scan_runs — mitigated by batching 10 findings per prompt
- **Risk-3**: `epss_history` empty if EPSS agent not run — velocity `stable` for all (correct, documented)
- **Risk-4**: Phase 2 must be added to `_RETRIABLE_STATUSES` in coordinator to allow manual re-trigger from intermediate Phase 2 states
- **Risk-5**: LLM prompt must handle non-CVE findings gracefully (fallback to rule_id + severity)

---

## Requirement Coverage Map → Use Cases

| Requirement | Use Case | Call Stack Section |
|---|---|---|
| REQ-004 | UC-010 | `LLMEnrichmentPipeline.run()` |
| REQ-005 | UC-011 | `BlastRadiusPipeline.run()` |
| REQ-006 | UC-012 | `EPSSVelocityPipeline.run()` |

## Acceptance Criteria Coverage Map → Stage 7 Scenarios

| AC-ID | Stage 7 Scenario |
|---|---|
| AC-029–AC-036 | S-UC010-01 through S-UC010-08 |
| AC-037–AC-043 | S-UC011-01 through S-UC011-07 |
| AC-044–AC-050 | S-UC012-01 through S-UC012-07 |
| AC-051–AC-054 | S-CROSS-01 through S-CROSS-04 |

---

## Out of Scope

- LLM-based regulatory control mapping (Phase 3)
- Real-time alerting on EPSS velocity spikes
- Blast radius across multi-project boundaries
- Backfill of existing scan_runs created before Phase 2 deployment
