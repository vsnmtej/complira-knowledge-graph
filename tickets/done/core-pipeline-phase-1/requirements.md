# Requirements: Core Pipeline Phase 1

**Status:** `Design-ready`
**Last Updated:** 2026-03-21
**Ticket:** core-pipeline-phase-1
**Scope:** `LARGE`

---

## Goal / Problem Statement

Phase 0 delivered scan ingestion infrastructure: raw findings stored in `scan_findings` with `cve_id`, `severity`, `rule_id`, and basic scanner-sourced edges. Findings have no enrichment (no EPSS, no KEV, no regulatory chain, no risk score).

Phase 1 delivers the **three-stage post-ingestion intelligence pipeline** that transforms raw findings into actionable compliance intelligence:

1. **UC-007 Vulnerability Enrichment** — Traverse the reference knowledge graph per finding; write EPSS, KEV, CWE chain, D3FEND, OSCAL/SCF controls back to the evidence layer.
2. **UC-008 Finding Compaction & Risk Scoring** — Deduplicate by CWE, roll up to parent CWE, compute composite risk scores, cluster and rank findings.
3. **UC-009 Control Mapping** — Resolve detected controls to regulatory frameworks (NIST 800-53, ISO 27001, FDA 510(k)), generate evidence chains, compute coverage %.

Pipeline is triggered automatically after ingestion completes and manually via API.

---

## Scope Triage

**Classification:** `LARGE`

Signals:
- 3 new pipeline service files (enrichment, compaction, control mapping)
- 1 new repository (bulk read/write for scan_findings + detected_controls)
- 1 new API endpoint (manual trigger + status polling)
- Multi-hop AQL traversal queries (3–5 hops per pipeline stage)
- Multi-layer impact: API endpoint → pipeline service → repository → AQL → edge writes
- Cross-boundary: reference DB reads (knowledge graph) + reference DB writes (evidence layer) in same pipeline

---

## In-Scope Use Cases

### UC-007: Vulnerability Enrichment
**REQ-001**
**Actor:** Pipeline (auto) / API consumer (manual)
**Trigger:** `scan_run.status == "completed"`
**Expected outcome:**
- Every `scan_findings` document with a non-null `cve_id` is updated with: `epss_score`, `epss_percentile`, `in_kev`, `cwe_chain` (list), `d3fend_techniques` (list), `enriched_at`
- `detected_controls` documents are upserted for every OSCAL/SCF control reached via the CVE → regulatory chain
- `finding_triggers_req` edges are created from reference DB `violates_requirement` traversal (in addition to rule-engine edges created at ingestion)
- `detected_control_maps_to` edges are created for each new detected_control → OSCAL/SCF control
- `scan_run.status` transitions to `"enriched"`

### UC-008: Finding Compaction & Risk Scoring
**REQ-002**
**Actor:** Pipeline (auto, runs after UC-007)
**Trigger:** `scan_run.status == "enriched"`
**Expected outcome:**
- Findings sharing the same CWE (direct or via `aliases` edge in reference DB) are grouped into a `compaction_group_id`
- Duplicate findings within a group are marked `compacted: true`; the canonical finding is kept
- Findings whose CWE has no regulatory mapping are rolled up to parent CWE via `child_of` traversal
- Every finding receives a `risk_score` computed as: `cvss_base * 0.4 + epss_score * 0.3 + kev_bonus * 0.2 + exploit_bonus * 0.1` where `kev_bonus = 1.0 if in_kev else 0.0` and `exploit_bonus` is capped at 1.0
- Findings are clustered by CWE and each cluster is assigned a `cluster_rank` (1 = highest aggregate risk)
- `scan_run.status` transitions to `"compacted"`

### UC-009: Control Mapping
**REQ-003**
**Actor:** Pipeline (auto, runs after UC-008)
**Trigger:** `scan_run.status == "compacted"`
**Expected outcome:**
- Each `detected_controls` document is annotated with `framework` (NIST 800-53, ISO 27001, FDA 510(k), IEC 62304, CRA)
- An `evidence_chain` list is written per control: `[finding_id, cwe_id, req_id, control_id]`
- `coverage_by_framework` is computed and written to the `scan_run` document: `{framework: covered_pct}`
- `scan_run.status` transitions to `"mapped"`

---

## Acceptance Criteria

### UC-007 — Vulnerability Enrichment

| AC-ID | Criterion | Measurable Expected Outcome |
|---|---|---|
| AC-001 | EPSS score populated | Every `scan_findings` doc with non-null `cve_id` has `epss_score` and `epss_percentile` set (latest date from `has_epss` traversal); findings with no CVE have these fields absent |
| AC-002 | KEV status populated | Every `scan_findings` doc with non-null `cve_id` has `in_kev: bool` set from `kev_entries` lookup |
| AC-003 | CWE chain populated | Every enriched finding has `cwe_chain: list[str]` with 1+ CWE IDs from `has_weakness` traversal; empty list for CVEs with no known CWE |
| AC-004 | D3FEND techniques linked | Findings with ATT&CK technique coverage have `d3fend_techniques: list[str]` populated; otherwise empty list |
| AC-005 | OSCAL/SCF controls upserted | `detected_controls` documents are created for every control reachable via CVE → `violates_requirement` → `maps_to_requirement` chain |
| AC-006 | `finding_triggers_req` edges created | AQL confirms edges from `scan_findings` to `regulatory_requirements` for each enriched finding |
| AC-007 | `detected_control_maps_to` edges created | AQL confirms edges from new `detected_controls` to `oscal_controls` or `scf_controls` |
| AC-008 | Findings without CVE skipped | Findings where `cve_id is null` complete without error; no enrichment fields written |
| AC-009 | Status transitions to `enriched` | `scan_runs.status == "enriched"` after pipeline completes |
| AC-010 | Idempotent | Re-running enrichment for the same `scan_run_id` does not create duplicate edges or documents; upserts are used throughout |

### UC-008 — Finding Compaction & Risk Scoring

| AC-ID | Criterion | Measurable Expected Outcome |
|---|---|---|
| AC-011 | CWE deduplication | Findings sharing the same CWE (`cwe_chain` overlap) within a scan_run are assigned the same `compaction_group_id` |
| AC-012 | Duplicate suppression | All but one finding per compaction group has `compacted: true`; canonical finding has `compacted: false` |
| AC-013 | CWE roll-up | Findings whose CWE has no `maps_to_requirement` edge get `cwe_chain` updated with the nearest parent CWE that does have one |
| AC-014 | Risk score formula | Every finding has `risk_score` ∈ [0, 1] computed by the defined formula; score 0 for findings with no CVE |
| AC-015 | Cluster ranking | Findings have `cluster_rank` integer; rank 1 = cluster with highest `max(risk_score)` |
| AC-016 | Status transitions to `compacted` | `scan_runs.status == "compacted"` after pipeline completes |
| AC-017 | Idempotent | Re-running compaction produces identical risk scores and group assignments |

### UC-009 — Control Mapping

| AC-ID | Criterion | Measurable Expected Outcome |
|---|---|---|
| AC-018 | Framework annotation | Every `detected_controls` document has `framework` field set from reference DB lookup |
| AC-019 | Evidence chain | Every `detected_controls` document has `evidence_chain: list[str]` with 4 elements: `[finding_id, cwe_id, req_id, control_id]` |
| AC-020 | Coverage % by framework | `scan_runs.coverage_by_framework` is a dict with at least one framework key and a float value ∈ [0, 100] |
| AC-021 | Status transitions to `mapped` | `scan_runs.status == "mapped"` after pipeline completes |
| AC-022 | Idempotent | Re-running control mapping produces identical framework annotations and coverage % |

### Cross-cutting

| AC-ID | Criterion | Measurable Expected Outcome |
|---|---|---|
| AC-023 | Auto-trigger after ingestion | After a successful scan ingest, enrichment pipeline starts automatically (scan_run status progresses from `completed` to `enriched` without manual API call) |
| AC-024 | Manual trigger API | `POST /v1/scans/{scan_run_id}/enrich` triggers the full pipeline for an existing scan_run; returns 202 Accepted |
| AC-025 | Status polling | `GET /v1/scans/{scan_run_id}` returns current `status` field reflecting pipeline progress |
| AC-026 | Pipeline failure isolation | If any pipeline stage fails, `scan_run.status` is set to `"pipeline_failed"` with `error_message`; partial writes are retained (not rolled back) |
| AC-027 | Reference DB unavailable | If reference DB is unreachable at pipeline start, enrichment fails gracefully with retriable error; scan_run status set to `"enrichment_pending"` |
| AC-028 | tenant_id scoping | All pipeline reads and writes include `tenant_id` filter; no cross-tenant data access possible |

---

## Constraints / Dependencies

- All v2.2 evidence collections (`scan_findings`, `scan_runs`, `detected_controls`) are in the **reference DB** — `get_reference_db()` is the correct handle
- Reference DB knowledge graph collections (`vulnerabilities`, `weaknesses`, `kev_entries`, `epss_history`, `oscal_controls`, `scf_controls`) must be populated by knowledge graph agents prior to enrichment
- No LLM calls in Phase 1 — all enrichment is deterministic graph traversal
- Redis cache may be used for reference DB traversal results (TTL = 6 hours per Phase 0 config)
- Bulk AQL updates must batch at ≤ 500 findings per transaction to avoid ArangoDB transaction size limits (Risk-3 from investigation)
- `kev_entries.cve_id` uses dashed format (`CVE-2024-1234`) — AQL must normalize scan_findings.cve_id format before comparison

---

## Assumptions

- `scan_findings.cve_id` uses the same canonical format as `vulnerabilities._key` (or can be normalized with simple string substitution)
- `scan_runs.compliance_score` field exists (written by `complete_run()`); Phase 1 may update it after control mapping
- FastAPI `BackgroundTasks` is sufficient for async pipeline trigger (no separate worker process needed for Phase 1)
- `EvidenceRunRepository.complete_run()` can be called with any status string to advance the pipeline

---

## Requirement Coverage Map → Use Cases

| Requirement | Use Case | Call Stack Section |
|---|---|---|
| REQ-001 | UC-007 | `EnrichmentPipeline.run()` |
| REQ-002 | UC-008 | `CompactionPipeline.run()` |
| REQ-003 | UC-009 | `ControlMappingPipeline.run()` |

## Acceptance Criteria Coverage Map → Stage 7 Scenarios

| AC-ID | Stage 7 Scenario |
|---|---|
| AC-001–AC-010 | S-UC007-01 through S-UC007-10 |
| AC-011–AC-017 | S-UC008-01 through S-UC008-07 |
| AC-018–AC-022 | S-UC009-01 through S-UC009-05 |
| AC-023–AC-028 | S-CROSS-01 through S-CROSS-06 |

---

## Out of Scope

- LLM enrichment (Phase 2)
- Blast radius simulation (Phase 2)
- EPSS velocity / trending detection (Phase 2)
- Backfill of existing scan_runs created before Phase 1 deployment
