# Requirements: Phase 6 — API Exposure of Phase 2 Pipeline Intelligence Fields

**Status:** Design-ready
**Ticket:** `phase-6-api-exposure`
**Branch:** `codex/phase-6-api-exposure`
**Date:** 2026-03-22

---

## Goal / Problem Statement

Phase 2 pipeline stages (UC-010 LLM enrichment, UC-011 blast radius simulation, UC-012 EPSS velocity detection) write intelligence fields to `scan_findings` and `scan_runs` documents in ArangoDB. These fields are not returned by any API endpoint. This ticket surfaces all Phase 2 fields through the existing FastAPI API, adds new filter/sort query parameters, and exposes summary statistics on scan runs.

---

## In-Scope Use Cases

| use_case_id | Description |
| --- | --- |
| UC-P6-001 | `GET /v1/scans/{scan_run_id}/findings` returns all Phase 2 fields on each finding (nullable) |
| UC-P6-002 | `GET /v1/scans/{scan_run_id}` returns `llm_token_usage` and Phase 2 pipeline statuses on scan run |
| UC-P6-003 | `GET /v1/scans/{scan_run_id}/findings?epss_trend=rising` filters findings by trend value |
| UC-P6-004 | `GET /v1/scans/{scan_run_id}/findings?min_blast_radius=0.5` filters findings by blast radius minimum |
| UC-P6-005 | `GET /v1/scans/{scan_run_id}/findings?sort_by=blast_radius_score` and `?sort_by=epss_velocity` sort findings descending |
| UC-P6-006 | `GET /v1/scans/{scan_run_id}` includes summary stats: rising/stable/falling counts, avg blast radius, top-5 blast radius findings |

---

## Requirements

### REQ-P6-001 — scan_findings Phase 2 Field Exposure
All Phase 2 fields written to `scan_findings` by UC-010, UC-011, UC-012 must be returned in findings API responses. All fields are optional (null when pipeline stage not yet complete).

**Fields:**
- `llm_risk_summary: str | None`
- `llm_remediation: str | None`
- `llm_attack_surface: Literal["network", "local", "adjacent"] | None`
- `llm_enriched_at: datetime | None`
- `blast_radius_score: float | None` (∈ [0, 1])
- `affected_components: list[str] | None`
- `blast_radius_path: list[str] | None`
- `blast_radius_computed_at: datetime | None`
- `epss_velocity: float | None`
- `epss_trend: Literal["rising", "stable", "falling"] | None`
- `epss_velocity_computed_at: datetime | None`

### REQ-P6-002 — scan_run Phase 2 Field Exposure
`GET /v1/scans/{scan_run_id}` must include:
- `llm_token_usage: dict | None` (keys: `input_tokens`, `output_tokens`, `total_tokens`, `model`)
- Phase 2 statuses (`llm_enriched`, `blast_radius_computed`, `velocity_computed`) accepted as valid `status` values

### REQ-P6-003 — Filter by epss_trend
`GET /v1/scans/{scan_run_id}/findings?epss_trend=<value>` filters results to findings where `epss_trend == value`. Valid values: `rising`, `stable`, `falling`. Invalid value → 422.

### REQ-P6-004 — Filter by min_blast_radius
`GET /v1/scans/{scan_run_id}/findings?min_blast_radius=<float>` filters results to findings where `blast_radius_score >= value`. Must be in [0, 1]. Out-of-range → 422.

### REQ-P6-005 — Sort by blast_radius_score or epss_velocity
`GET /v1/scans/{scan_run_id}/findings?sort_by=blast_radius_score` or `?sort_by=epss_velocity` returns findings sorted by the specified field descending (nulls last). Invalid `sort_by` value → 422.

### REQ-P6-006 — Scan Run Summary Stats
`GET /v1/scans/{scan_run_id}` must include `phase2_summary` object:
- `rising_count: int` — findings where `epss_trend == "rising"`
- `stable_count: int` — findings where `epss_trend == "stable"`
- `falling_count: int` — findings where `epss_trend == "falling"`
- `avg_blast_radius: float | None` — mean `blast_radius_score` across all findings (null if no findings have blast radius)
- `top_blast_radius_findings: list[str]` — top 5 finding `_key` values by `blast_radius_score` DESC

---

## Acceptance Criteria

| AC ID | Requirement | Criterion |
| --- | --- | --- |
| AC-P6-001 | REQ-P6-001 | `GET /v1/scans/{id}/findings` response includes all 11 Phase 2 fields on each finding |
| AC-P6-002 | REQ-P6-001 | Phase 2 fields are `null` (not absent/error) when pipeline stage not yet complete |
| AC-P6-003 | REQ-P6-001 | `llm_attack_surface` accepts only `"network"`, `"local"`, `"adjacent"` (or null) — validated by Pydantic |
| AC-P6-004 | REQ-P6-001 | `epss_trend` accepts only `"rising"`, `"stable"`, `"falling"` (or null) — validated by Pydantic |
| AC-P6-005 | REQ-P6-002 | `GET /v1/scans/{id}` response includes `llm_token_usage` field |
| AC-P6-006 | REQ-P6-002 | `llm_token_usage` is `null` when LLM stage not yet complete |
| AC-P6-007 | REQ-P6-002 | `status` field on scan_run accepts Phase 2 statuses without validation error |
| AC-P6-008 | REQ-P6-003 | `?epss_trend=rising` returns only findings with `epss_trend == "rising"` |
| AC-P6-009 | REQ-P6-003 | `?epss_trend=invalid` returns HTTP 422 |
| AC-P6-010 | REQ-P6-004 | `?min_blast_radius=0.5` returns only findings with `blast_radius_score >= 0.5` |
| AC-P6-011 | REQ-P6-004 | `?min_blast_radius=1.5` returns HTTP 422 (out of range) |
| AC-P6-012 | REQ-P6-005 | `?sort_by=blast_radius_score` returns findings sorted by score descending, nulls last |
| AC-P6-013 | REQ-P6-005 | `?sort_by=epss_velocity` returns findings sorted by velocity descending, nulls last |
| AC-P6-014 | REQ-P6-005 | `?sort_by=invalid_field` returns HTTP 422 |
| AC-P6-015 | REQ-P6-006 | `GET /v1/scans/{id}` includes `phase2_summary` with correct counts and avg |
| AC-P6-016 | REQ-P6-006 | `phase2_summary.top_blast_radius_findings` contains at most 5 finding keys |
| AC-P6-017 | REQ-P6-006 | `phase2_summary.avg_blast_radius` is `null` when no findings have blast radius data |

---

## Constraints / Dependencies

- FastAPI + Pydantic v2 — all new fields must use Pydantic v2 `Optional` / `Literal` patterns
- ArangoDB — all filter/sort/stats queries must run as AQL (no Python-side post-filtering for large result sets)
- All Phase 2 fields are already written to ArangoDB by Phase 2 pipeline — this ticket is API layer only, no DB schema changes
- Existing Phase 1 fields must not be disturbed — backward-compatible response model extension
- No authentication changes — existing tenant_id scoping applies to all new queries
- Multi-tenancy — all new AQL queries must include `tenant_id` filter

---

## Phase 1 Field Gap (Discovered in Stage 1)

Investigation revealed that Phase 1 enrichment fields written to `scan_findings` by the pipeline are also absent from the current `ScanFindingResponse`. These fields are in-scope for Phase 6 as part of making the response model complete:

- `epss_score: float | None`, `epss_percentile: float | None`
- `in_kev: bool | None`
- `cwe_chain: list[str] | None`
- `d3fend_techniques: list[str] | None`
- `risk_score: float | None`
- `compaction_group_id: str | None`
- `cluster_rank: int | None`
- `compacted: bool | None`
- `cvss_base: float | None`

These are added to REQ-P6-001 scope. All are optional (null when pipeline not run).

---

## Assumptions

- Phase 2 pipeline may or may not have run when the API is called — null fields are expected and normal
- `phase2_summary` stats are computed at query time from `scan_findings` (not pre-cached on `scan_runs`)
- Filters can be combined (e.g., `?epss_trend=rising&min_blast_radius=0.3`) — AND semantics
- Default sort order (no `sort_by` param) remains unchanged from Phase 1 behavior

---

## Open Questions / Risks

| # | Question | Status |
| --- | --- | --- |
| OQ-1 | Does the existing findings repository do AQL or Python-side filtering? Need to confirm before designing filter layer | Open — to resolve in Stage 1 |
| OQ-2 | Is `phase2_summary` computed in a single AQL query on `scan_findings`, or via a separate aggregate query? | Open — to resolve in Stage 1 |
| OQ-3 | Current findings pagination — does it use cursor/offset? Filter must not break pagination contract | Open — to resolve in Stage 1 |

---

## Scope Triage

**Triage:** `Small` — pure API layer additions (2 primary files: response models + endpoint). No new infrastructure, no new DB collections, no new pipeline stages.

---

## Requirement Coverage Map

| requirement_id | use_case_ids |
| --- | --- |
| REQ-P6-001 | UC-P6-001 |
| REQ-P6-002 | UC-P6-002 |
| REQ-P6-003 | UC-P6-003 |
| REQ-P6-004 | UC-P6-004 |
| REQ-P6-005 | UC-P6-005 |
| REQ-P6-006 | UC-P6-006 |

---

## Acceptance Criteria Coverage Map (Stage 7 preview)

| AC ID | Mapped Scenario (Stage 7) |
| --- | --- |
| AC-P6-001 | S-P6-001 (findings response fields) |
| AC-P6-002 | S-P6-002 (null fields pre-pipeline) |
| AC-P6-003 | S-P6-003 (llm_attack_surface validation) |
| AC-P6-004 | S-P6-004 (epss_trend validation) |
| AC-P6-005 | S-P6-005 (scan_run token usage) |
| AC-P6-006 | S-P6-006 (null token usage) |
| AC-P6-007 | S-P6-007 (phase 2 status values) |
| AC-P6-008 | S-P6-008 (filter epss_trend=rising) |
| AC-P6-009 | S-P6-009 (invalid epss_trend 422) |
| AC-P6-010 | S-P6-010 (filter min_blast_radius) |
| AC-P6-011 | S-P6-011 (invalid min_blast_radius 422) |
| AC-P6-012 | S-P6-012 (sort by blast_radius_score) |
| AC-P6-013 | S-P6-013 (sort by epss_velocity) |
| AC-P6-014 | S-P6-014 (invalid sort_by 422) |
| AC-P6-015 | S-P6-015 (phase2_summary counts+avg) |
| AC-P6-016 | S-P6-016 (top_blast_radius_findings max 5) |
| AC-P6-017 | S-P6-017 (avg_blast_radius null) |
