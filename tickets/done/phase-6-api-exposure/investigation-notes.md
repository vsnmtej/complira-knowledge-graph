# Investigation Notes: Phase 6 — API Exposure of Phase 2 Intelligence Fields

**Ticket:** `phase-6-api-exposure`
**Date:** 2026-03-22
**Status:** Complete

---

## Sources Consulted

| Source | Path |
| --- | --- |
| Scan endpoint | `src/api/v1/endpoints/scan.py` |
| Scan response models | `src/api/models/responses/scan.py` |
| Pipeline docs | `docs/SCAN_ENRICHMENT_PIPELINE.md` |
| Existing integration tests | `tests/integration/test_scan_ingestion_api.py` |
| Test conftest | `tests/conftest.py` |

---

## Key Findings

### 1. Findings Endpoint: Inline AQL, No Repository Pattern

`GET /v1/scan/{run_id}/findings` (line 241 in `scan.py`) executes AQL **inline** — no `ScanFindingsRepository` exists for this layer. The query is:

```aql
FOR f IN scan_findings
    FILTER f.scan_run_id == @run_id AND f.tenant_id == @tenant_id
    SORT f.severity ASC
    LIMIT @offset, @limit
    RETURN f
```

- Uses offset/limit pagination (not cursor-based) — filter/sort additions must preserve this pattern.
- Sorts by `severity ASC` by default; the new `sort_by` param must override this.
- **Implication:** Filter/sort additions go into the same inline AQL with bind_vars. For summary stats, a second AQL query runs against `scan_findings` in the scan_run endpoint.

### 2. ScanFindingResponse Is Minimal — Phase 1 Fields Also Missing

`ScanFindingResponse` currently only maps 7 fields:
- `finding_id` (`_key`), `cve_id`, `severity`, `description`, `location`, `tool_name`, `created_at`

**Phase 1 pipeline fields present in DB but absent from response:**
`epss_score`, `epss_percentile`, `in_kev`, `cwe_chain`, `d3fend_techniques`, `risk_score`, `compaction_group_id`, `cluster_rank`, `compacted`, `cvss_base`

Phase 6 must add **both** Phase 1 and Phase 2 fields to `ScanFindingResponse`. All fields are optional/nullable (pipeline may not have run).

### 3. ScanSessionResponse Missing Phase 2 Fields

`ScanSessionResponse` (line 47 in `scan.py`) has no `llm_token_usage`, `phase2_summary`, or Phase 2 status values. The `status` field is a plain `str` — no Pydantic literal validation. Phase 2 status values (`llm_enriched`, `blast_radius_computed`, `velocity_computed`) will be returned without error by existing string field, but should be validated.

### 4. Scan Run Endpoint: Direct Collection Fetch

`GET /v1/scan/{run_id}` uses `ref_db.collection("scan_runs").get(run_id)` — simple document fetch. Summary stats require a **separate AQL aggregate query** against `scan_findings` with `AGGREGATE` or `COLLECT`. This runs at query time (not cached).

### 5. Testing Pattern

- Unit tests use `MagicMock` for DB and repos (no live ArangoDB needed)
- Integration tests exist in `tests/integration/` using `TestClient` + mocked DB
- Phase 2 pipeline tests live in `tests/unit/ingestion/` and `tests/e2e/ingestion/`
- New API tests should follow the `tests/unit/api/` pattern (to be created) or `tests/integration/` pattern

---

## Resolved Open Questions

| # | Question | Resolution |
| --- | --- | --- |
| OQ-1 | Does findings repository do AQL or Python-side filtering? | **Inline AQL in endpoint** — filter additions go directly into the AQL query with bind_vars. No Python-side post-filtering needed or desired. |
| OQ-2 | Is `phase2_summary` single AQL or separate aggregate query? | **Separate AQL aggregate query** in scan_run endpoint. `COLLECT` with `AGGREGATE` for counts and avg. |
| OQ-3 | Pagination contract? | **Offset/limit** pagination. Filters add `AND` clauses before the `SORT`/`LIMIT`. Contract is preserved. |

---

## Scope Classification

**Scope: `Small`**

Rationale:
- Touches 2 primary files: `src/api/models/responses/scan.py` (add fields) + `src/api/v1/endpoints/scan.py` (add params + AQL updates)
- No new infrastructure, no new dependencies, no new collections
- No cross-cutting architectural changes
- New test file: `tests/unit/api/test_scan_findings_api.py`
- Phase 1 fields also need to be added (gap discovered) — still within `Small` scope (same files)

---

## Implementation Constraints

1. **AQL filter construction:** Use bind_vars for all dynamic values (no string interpolation) — prevent AQL injection
2. **Nulls-last sort:** ArangoDB `SORT field DESC` naturally places nulls last in descending sorts — leverage this
3. **Combined filters:** `?epss_trend=rising&min_blast_radius=0.3` uses AND semantics — build filter clauses conditionally
4. **Summary stats AQL:** Single `AGGREGATE` query over `scan_findings` filtered by `scan_run_id + tenant_id`; return `rising_count`, `stable_count`, `falling_count`, `avg_blast_radius`, `top_blast_radius_findings` (top 5 keys by score)
5. **Pydantic v2:** Use `Optional[Literal[...]]` for `llm_attack_surface` and `epss_trend` fields
6. **No backward compat:** Replace `ScanFindingResponse.cve_id` string-required field with Optional (since DB stores either `cve_id` or `rule_id`)

---

## Unknowns / Risks

| Risk | Mitigation |
| --- | --- |
| AQL aggregate query over large `scan_findings` collection may be slow | Use `scan_run_id` index (already exists from ingest) — bounded to one scan run |
| `ScanFindingResponse` field rename: `cve_id` was `str` (required), now needs to be `Optional[str]` | Unit tests will catch breakage; endpoint already does `f.get("cve_id") or f.get("rule_id") or "N/A"` — can keep `str` with fallback |

---

## File Change Inventory (Preliminary)

| File | Change Type | Description |
| --- | --- | --- |
| `src/api/models/responses/scan.py` | Modify | Add Phase 1 + Phase 2 fields to `ScanFindingResponse`; add `LLMTokenUsage`, `Phase2Summary`, update `ScanSessionResponse` |
| `src/api/v1/endpoints/scan.py` | Modify | Add `epss_trend`, `min_blast_radius`, `sort_by` query params; update findings AQL; add summary stats AQL to scan_run endpoint |
| `tests/unit/api/test_scan_findings_api.py` | Add | Unit tests for new fields, filter/sort params, summary stats, validation errors |
