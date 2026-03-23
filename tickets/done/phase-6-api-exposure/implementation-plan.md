# Implementation Plan: Phase 6 — API Exposure of Phase 2 Intelligence Fields

**Ticket:** `phase-6-api-exposure`
**Scope:** Small
**Status:** Draft (pre-review)
**Date:** 2026-03-22

---

## Solution Sketch

### Target Architecture

Pure API layer additions. No new infrastructure, no new pipeline stages, no new DB collections.

```
GET /v1/scan/{run_id}/findings
  ↓
scan.py (endpoint) — new query params: epss_trend, min_blast_radius, sort_by
  ↓
AQL inline query (extended with optional FILTER + dynamic SORT)
  ↓
scan_findings collection (already has all Phase 1+2 fields)
  ↓
ScanFindingResponse (extended with Phase 1 + Phase 2 optional fields)

GET /v1/scan/{run_id}
  ↓
scan.py (endpoint) — extended to call aggregate AQL for phase2_summary
  ↓
scan_runs collection (get doc) + scan_findings (aggregate AQL)
  ↓
ScanSessionResponse (extended with llm_token_usage + phase2_summary)
```

### Layers / Boundaries

- **Response models** (`src/api/models/responses/scan.py`): data shape + Pydantic validation
- **Endpoints** (`src/api/v1/endpoints/scan.py`): query params, AQL construction, response assembly
- Existing inline AQL pattern is preserved — no new repository introduced (consistent with existing codebase style)

---

## Change Inventory

| ID | File | Change Type | Description |
| --- | --- | --- | --- |
| C1 | `src/api/models/responses/scan.py` | Modify | Add `LLMTokenUsage` model, `Phase2Summary` model, extend `ScanFindingResponse` with Phase 1 + Phase 2 fields, extend `ScanSessionResponse` with `llm_token_usage` + `phase2_summary` |
| C2 | `src/api/v1/endpoints/scan.py` | Modify | Add `epss_trend`, `min_blast_radius`, `sort_by` query params to `list_scan_findings`; update AQL with conditional filters + dynamic sort; add `phase2_summary` aggregate AQL call in `get_scan_run` |
| C3 | `tests/unit/api/test_scan_findings_api.py` | Add | Unit tests for all 17 ACs |

---

## Detailed Design

### C1: Response Model Changes

**New model: `LLMTokenUsage`**
```python
class LLMTokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    model: str
```

**New model: `Phase2Summary`**
```python
class Phase2Summary(BaseModel):
    rising_count: int = 0
    stable_count: int = 0
    falling_count: int = 0
    avg_blast_radius: Optional[float] = None
    top_blast_radius_findings: list[str] = Field(default_factory=list)
```

**Extended `ScanFindingResponse`** (all new fields optional):

Phase 1 fields (from UC-007 + UC-008):
- `cvss_base: Optional[float]`
- `epss_score: Optional[float]`
- `epss_percentile: Optional[float]`
- `in_kev: Optional[bool]`
- `cwe_chain: Optional[list[str]]`
- `d3fend_techniques: Optional[list[str]]`
- `risk_score: Optional[float]`
- `compaction_group_id: Optional[str]`
- `cluster_rank: Optional[int]`
- `compacted: Optional[bool]`

Phase 2 fields (from UC-010, UC-011, UC-012):
- `llm_risk_summary: Optional[str]`
- `llm_remediation: Optional[str]`
- `llm_attack_surface: Optional[Literal["network", "local", "adjacent"]]`
- `llm_enriched_at: Optional[str]`
- `blast_radius_score: Optional[float]`
- `affected_components: Optional[list[str]]`
- `blast_radius_path: Optional[list[str]]`
- `blast_radius_computed_at: Optional[str]`
- `epss_velocity: Optional[float]`
- `epss_trend: Optional[Literal["rising", "stable", "falling"]]`
- `epss_velocity_computed_at: Optional[str]`

**Extended `ScanSessionResponse`**:
- `llm_token_usage: Optional[LLMTokenUsage]`
- `phase2_summary: Optional[Phase2Summary]`
- `coverage_by_framework: Optional[dict]`

### C2: Endpoint Changes

**`list_scan_findings` new query params:**
```python
epss_trend: Optional[Literal["rising", "stable", "falling"]] = Query(None)
min_blast_radius: Optional[float] = Query(None, ge=0.0, le=1.0)
sort_by: Optional[Literal["blast_radius_score", "epss_velocity"]] = Query(None)
```

**AQL construction (dynamic) — allow-list for sort field (FINDING-R1-02 fix):**
```python
# Allow-list: maps sort_by param value to safe AQL field reference
_SORT_FIELD_MAP = {
    "blast_radius_score": "f.blast_radius_score",
    "epss_velocity": "f.epss_velocity",
}

filters = "FILTER f.scan_run_id == @run_id AND f.tenant_id == @tenant_id"
if epss_trend:
    filters += " AND f.epss_trend == @epss_trend"
    bind_vars["epss_trend"] = epss_trend
if min_blast_radius is not None:
    filters += " AND f.blast_radius_score >= @min_blast_radius"
    bind_vars["min_blast_radius"] = min_blast_radius

# Use allow-list mapping — no f-string interpolation of user input
sort_field = _SORT_FIELD_MAP.get(sort_by) if sort_by else None
sort = f"SORT {sort_field} DESC" if sort_field else "SORT f.severity ASC"

aql = f"""
FOR f IN scan_findings
    {filters}
    {sort}
    LIMIT @offset, @limit
    RETURN f
"""
```

Note: `sort_by` is `Optional[Literal[...]]` so FastAPI rejects unknown values at 422. The allow-list dict is belt-and-suspenders — it maps to a hardcoded string, never user input.

**`get_scan_run` — phase2_summary computation (FINDING-R1-01 fix — 2 queries, not 3):**

Query 1 — trend counts + avg blast radius in one pass:
```aql
LET all_findings = (
    FOR f IN scan_findings
    FILTER f.scan_run_id == @run_id AND f.tenant_id == @tenant_id
    RETURN {trend: f.epss_trend, br: f.blast_radius_score}
)
LET br_scores = (FOR x IN all_findings FILTER x.br != null RETURN x.br)
LET trend_groups = (
    FOR x IN all_findings
    COLLECT trend = x.trend WITH COUNT INTO cnt
    RETURN {trend: trend, count: cnt}
)
RETURN {
    trend_groups: trend_groups,
    avg_blast_radius: LENGTH(br_scores) > 0 ? AVG(br_scores) : null
}
```

Query 2 — top-5 by blast radius:
```aql
FOR f IN scan_findings
    FILTER f.scan_run_id == @run_id AND f.tenant_id == @tenant_id
           AND f.blast_radius_score != null
    SORT f.blast_radius_score DESC
    LIMIT 5
    RETURN f._key
```

### C3: Test Strategy

Test file: `tests/unit/api/test_scan_findings_api.py`

Use `TestClient` from FastAPI + mocked ArangoDB (`MagicMock`). Tests cover:
- Phase 1 + Phase 2 fields returned correctly (AC-P6-001)
- Null fields when DB returns None (AC-P6-002)
- Pydantic validation for `llm_attack_surface`, `epss_trend` (AC-P6-003/004)
- `llm_token_usage` present/null (AC-P6-005/006)
- Filter `epss_trend=rising` constructs correct AQL bind_vars (AC-P6-008)
- Filter `epss_trend=invalid` returns 422 (AC-P6-009)
- Filter `min_blast_radius=0.5` constructs correct bind_vars (AC-P6-010)
- Filter `min_blast_radius=1.5` returns 422 (AC-P6-011)
- Sort `blast_radius_score` constructs AQL with correct SORT clause (AC-P6-012)
- Sort `epss_velocity` constructs correct sort (AC-P6-013)
- Sort `invalid_field` returns 422 (AC-P6-014)
- `phase2_summary` returns correct counts and avg (AC-P6-015)
- `top_blast_radius_findings` ≤ 5 items (AC-P6-016)
- `avg_blast_radius` null when no findings have blast radius (AC-P6-017)

---

## Implementation Sequence

1. **C1** — extend response models (`scan.py`) — no DB dependency, testable standalone
2. **C2** — extend endpoints (`scan.py`) — depends on C1 response models
3. **C3** — write unit tests — depends on C1 + C2

---

## Requirement Traceability

| Requirement | Design Section | Use Case | Implementation Tasks |
| --- | --- | --- | --- |
| REQ-P6-001 | C1: ScanFindingResponse Phase 1+2 fields | UC-P6-001 | C1, C2 (response assembly), C3 |
| REQ-P6-002 | C1: ScanSessionResponse + LLMTokenUsage | UC-P6-002 | C1, C2 (scan_run assembly + summary AQL), C3 |
| REQ-P6-003 | C2: epss_trend query param + AQL filter | UC-P6-003 | C2, C3 |
| REQ-P6-004 | C2: min_blast_radius query param + AQL filter | UC-P6-004 | C2, C3 |
| REQ-P6-005 | C2: sort_by query param + dynamic SORT | UC-P6-005 | C2, C3 |
| REQ-P6-006 | C1: Phase2Summary + C2: aggregate AQL | UC-P6-006 | C1, C2, C3 |
