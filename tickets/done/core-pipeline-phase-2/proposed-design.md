# Proposed Design: Core Pipeline Phase 2

**Document Version:** 1.1
**Status:** Draft — Pending Review (Round 1 Design Impact fix applied)
**Ticket:** `core-pipeline-phase-2`
**Scope Classification:** LARGE
**Author(s):** Engineering
**Created:** 2026-03-22
**Last Updated:** 2026-03-22
**Requirements Ref:** `tickets/in-progress/core-pipeline-phase-2/requirements.md`
**Investigation Ref:** `tickets/in-progress/core-pipeline-phase-2/investigation-notes.md`

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Direction Decision](#2-architecture-direction-decision)
3. [Four-Layer Architecture Diagram](#3-four-layer-architecture-diagram)
4. [Change Inventory](#4-change-inventory)
5. [Module Specifications](#5-module-specifications)
   - 5.1 [pipeline_llm_client.py (New)](#51-pipeline_llm_clientpy-new)
   - 5.2 [scan_llm_enrichment_repository.py (New)](#52-scan_llm_enrichment_repositorypy-new)
   - 5.3 [scan_blast_radius_repository.py (New)](#53-scan_blast_radius_repositorypy-new)
   - 5.4 [llm_enrichment_pipeline.py (New)](#54-llm_enrichment_pipelinepy-new)
   - 5.5 [blast_radius_pipeline.py (New)](#55-blast_radius_pipelinepy-new)
   - 5.6 [epss_velocity_pipeline.py (New)](#56-epss_velocity_pipelinepy-new)
   - 5.7 [pipeline_coordinator.py (Modified)](#57-pipeline_coordinatorpy-modified)
   - 5.8 [scan_enrichment_repository.py (Modified)](#58-scan_enrichment_repositorypy-modified)
   - 5.9 [__init__.py (Modified)](#59-__init__py-modified)
6. [Data Models](#6-data-models)
7. [Error Handling](#7-error-handling)
8. [Naming Decisions](#8-naming-decisions)
9. [Naming-Drift Check](#9-naming-drift-check)
10. [Use-Case Coverage Matrix](#10-use-case-coverage-matrix)

---

## 1. Executive Summary

### 1.1 As-Is State

Phase 1 delivered a deterministic three-stage post-ingestion pipeline that enriches scan findings against the reference knowledge graph and computes compliance coverage. The current status chain is:

```
running → completed → enriched → compacted → mapped
```

The three Phase 1 stages are:
- **UC-007 EnrichmentPipeline** — bulk AQL traversal: CVE → EPSS, KEV, CWE chain, D3FEND techniques, regulatory requirement keys
- **UC-008 CompactionPipeline** — CWE-based grouping, composite risk scoring, canonical selection, cluster ranking
- **UC-009 ControlMappingPipeline** — detected_controls resolution, framework assignment, evidence chains, coverage_by_framework

All three stages are orchestrated by `PipelineCoordinator`, which enforces idempotency via status-guard frozensets and supports force-rerun. All AQL is isolated in `ScanEnrichmentRepository`; pipeline classes hold zero AQL.

At `mapped` status, a scan run has deterministic enrichment fields (EPSS score, CVSS base, KEV flag, CWE chain) and coverage ratios. It does **not** yet have:
- Plain-language risk summaries or remediation guidance
- Dependency propagation blast radius scores
- EPSS trend signals (rising/stable/falling)

### 1.2 To-Be State

Phase 2 extends the pipeline by adding three intelligence layers that activate after `mapped` status. The extended status chain becomes:

```
running → completed → enriched → compacted → mapped
                                              ↓
                                         llm_enriched
                                              ↓
                                    blast_radius_computed
                                              ↓
                                      velocity_computed
```

The three Phase 2 stages are:
- **UC-010 LLMEnrichmentPipeline** — Calls Claude Haiku API in batches of 10 findings per prompt; writes `llm_risk_summary`, `llm_remediation`, `llm_attack_surface`, `llm_enriched_at` to every `scan_findings` document. Non-CVE findings fall back to `rule_id + severity` as LLM context.
- **UC-011 BlastRadiusPipeline** — AQL traversal of INBOUND `depends_on` edges (depth 1..5) from each finding's purl component; computes `blast_radius_score`, `affected_components`, `blast_radius_path`. SAST/IaC findings with no purl receive score=0.
- **UC-012 EPSSVelocityPipeline** — Fetches 30-day `epss_history` time series per CVE; computes linear regression slope (pure Python, no numpy); classifies trend as rising/stable/falling.

The `PipelineCoordinator` is extended with three new stage slots and a corresponding set of idempotency guards. New statuses are added to `_RETRIABLE_STATUSES` to support manual re-trigger from any Phase 2 intermediate state.

---

## 2. Architecture Direction Decision

### 2.1 Decision: Sync `PipelineLLMClient` in Ingestion Layer (not `ClaudeLLMService` reuse)

**Options considered:**

| Option | Description | Verdict |
|---|---|---|
| A | `asyncio.run()` to call async `ClaudeLLMService._call_claude()` from sync pipeline | Rejected — nested event loops are fragile; `asyncio.run()` fails if an event loop is already running in the BackgroundTask context |
| B | New sync `PipelineLLMClient` in `src/complira_graph/ingestion/` — sync `anthropic.Anthropic()` client, no Redis | **Selected** |
| C | Inline `anthropic.Anthropic()` calls directly in `LLMEnrichmentPipeline` | Rejected — not testable as a unit; hard to mock; violates zero-external-call rule in pipeline classes |

**Rationale for Option B:**
- Pipeline stages run in `BackgroundTask` (synchronous context). The `ClaudeLLMService` is designed for the async API request/response cycle and carries a Redis dependency that is inappropriate in the ingestion layer.
- A dedicated `PipelineLLMClient` wrapper keeps the ingestion package independently testable (mock the client, not the API layer).
- Separation of concerns: the API services layer and the ingestion layer share no direct dependency.
- The sync `anthropic.Anthropic().messages.create()` call is the simplest correct path.

### 2.2 Decision: Repository Separation for Phase 2 Write Concerns

Phase 1 code-review explicitly noted: "if Phase 2 adds LLM-enrichment writes (a new write concern), extract a `ScanLLMEnrichmentRepository` at that time."

**Repository allocation for Phase 2:**

| Repository | Phase | Responsibility |
|---|---|---|
| `ScanEnrichmentRepository` | Phase 1 (extended) | EPSS/KEV/CWE reads; bulk_update_findings; add `aql_get_epss_history_batch()` for velocity reads; EPSS velocity field writes reuse `bulk_update_findings` |
| `ScanLLMEnrichmentRepository` | Phase 2 (new) | LLM field writes: `llm_risk_summary`, `llm_remediation`, `llm_attack_surface`, `llm_enriched_at`; token usage tracking |
| `ScanBlastRadiusRepository` | Phase 2 (new) | Blast radius AQL traversal (`depends_on`, `project_uses_component`); blast radius field writes |

**Rationale:** EPSS velocity shares the same write path as Phase 1 enrichment (`bulk_update_findings`) and the same read collection (`epss_history` via `has_epss` edge). Adding `aql_get_epss_history_batch()` to `ScanEnrichmentRepository` is the correct cohesion point; it does not warrant a third new repository.

### 2.3 Decision: Status Guard Frozensets — Phase 2 Pattern

Phase 1 uses three guard frozensets (`_ENRICHMENT_DONE`, `_COMPACTION_DONE`, `_MAPPING_DONE`). Phase 2 adds three analogous sets:
- `_LLM_DONE = frozenset({"llm_enriched", "blast_radius_computed", "velocity_computed"})`
- `_BLAST_DONE = frozenset({"blast_radius_computed", "velocity_computed"})`
- `_VELOCITY_DONE = frozenset({"velocity_computed"})`

`_RETRIABLE_STATUSES` is extended with `"mapped"`, `"llm_enriched"`, `"blast_radius_computed"` to allow manual re-trigger from any Phase 2 intermediate state.

---

## 3. Four-Layer Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  LAYER 1: HTTP / BackgroundTask Trigger                                      │
│                                                                             │
│  POST /v1/scans/{id}/enrich          BackgroundTask (scan ingest endpoint)  │
│         │                                        │                          │
│         └────────────────┬───────────────────────┘                          │
│                          ▼                                                  │
└──────────────────────────┬──────────────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────────────┐
│  LAYER 2: Coordinator (Orchestration)                                        │
│                                                                             │
│  PipelineCoordinator.run_post_ingest_pipeline(scan_run_id, tenant_id)       │
│                                                                             │
│  Phase 1 stages:                  Phase 2 stages (new):                     │
│  ┌──────────────────┐             ┌────────────────────────┐                │
│  │ EnrichmentPipeline│            │ LLMEnrichmentPipeline  │                │
│  │  (UC-007)        │            │  (UC-010)              │                │
│  └────────┬─────────┘            └───────────┬────────────┘                │
│           │                                  │                             │
│  ┌────────▼─────────┐             ┌──────────▼─────────────┐               │
│  │ CompactionPipeline│            │  BlastRadiusPipeline   │               │
│  │  (UC-008)        │            │  (UC-011)              │               │
│  └────────┬─────────┘            └───────────┬────────────┘               │
│           │                                  │                             │
│  ┌────────▼─────────┐             ┌──────────▼─────────────┐               │
│  │ControlMappingPipeline│         │  EPSSVelocityPipeline  │               │
│  │  (UC-009)        │            │  (UC-012)              │               │
│  └──────────────────┘            └────────────────────────┘               │
└──────────────────────────┬──────────────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────────────┐
│  LAYER 3: Repository / External Client                                       │
│                                                                             │
│  ┌─────────────────────────────┐   ┌────────────────────────────────────┐  │
│  │  ScanEnrichmentRepository   │   │  ScanLLMEnrichmentRepository (new) │  │
│  │  (Phase 1 + aql_get_epss_  │   │  bulk_write_llm_fields()           │  │
│  │   history_batch() added)    │   │  write_token_usage()               │  │
│  └─────────────────────────────┘   └────────────────────────────────────┘  │
│                                                                             │
│  ┌──────────────────────────────┐  ┌────────────────────────────────────┐  │
│  │ ScanBlastRadiusRepository    │  │  PipelineLLMClient (new)           │  │
│  │ (new)                        │  │  call_batch(findings) → list[dict] │  │
│  │ aql_blast_radius_for_purl()  │  │  sync anthropic.Anthropic()        │  │
│  │ aql_total_project_components │  │  no Redis, no async                │  │
│  │ bulk_write_blast_radius()    │  └────────────────────────────────────┘  │
│  └──────────────────────────────┘                                          │
└──────────────────────────┬──────────────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────────────┐
│  LAYER 4: Storage / External API                                             │
│                                                                             │
│  ArangoDB (scan findings DB)     ArangoDB (reference DB)   Anthropic API   │
│  ┌──────────────────┐            ┌─────────────────────┐   ┌─────────────┐ │
│  │ scan_findings    │            │ components           │   │ Claude Haiku│ │
│  │ scan_runs        │            │ depends_on (edges)   │   │ 4-5-2025100 │ │
│  │ detected_controls│            │ project_uses_component   └─────────────┘ │
│  └──────────────────┘            │ vulnerabilities      │                  │
│                                  │ epss_history         │                  │
│                                  │ has_epss (edges)     │                  │
│                                  └─────────────────────┘                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Status chain across layers:**
```
scan_runs.status progression:
  completed → enriched → compacted → mapped
                                       ↓  (Phase 2 begins)
                                  llm_enriched
                                       ↓
                              blast_radius_computed
                                       ↓
                               velocity_computed
```

---

## 4. Change Inventory

| Action | File | Responsibility | Change Type |
|---|---|---|---|
| **Add** | `src/complira_graph/ingestion/pipeline_llm_client.py` | Sync Anthropic Claude wrapper for pipeline layer; call_batch() method; no Redis; no async | New class |
| **Add** | `src/complira_graph/ingestion/scan_llm_enrichment_repository.py` | Write LLM fields to scan_findings; write token usage to scan_runs | New class |
| **Add** | `src/complira_graph/ingestion/scan_blast_radius_repository.py` | AQL traversal of depends_on + project_uses_component; write blast radius fields to scan_findings | New class |
| **Add** | `src/complira_graph/ingestion/llm_enrichment_pipeline.py` | UC-010: batch findings → PipelineLLMClient → ScanLLMEnrichmentRepository writes | New class |
| **Add** | `src/complira_graph/ingestion/blast_radius_pipeline.py` | UC-011: per-purl blast radius AQL traversal → score computation → writes | New class |
| **Add** | `src/complira_graph/ingestion/epss_velocity_pipeline.py` | UC-012: EPSS history batch fetch → linear regression → trend writes | New class |
| **Modify** | `src/complira_graph/ingestion/pipeline_coordinator.py` | Add Phase 2 stage slots; extend _RETRIABLE_STATUSES; add _LLM_DONE, _BLAST_DONE, _VELOCITY_DONE guards; instantiate 3 new pipelines in __init__ | Status guards + stage wiring |
| **Modify** | `src/complira_graph/ingestion/scan_enrichment_repository.py` | Add aql_get_epss_history_batch(cve_ids, cutoff_date) method for 30-day EPSS time-series | New method |
| **Modify** | `src/complira_graph/ingestion/__init__.py` | Export 6 new public symbols | Export additions |

**Summary:** 6 new files (6 new classes), 3 modified files, 0 removed files.

---

## 5. Module Specifications

### 5.1 `pipeline_llm_client.py` (New)

**Location:** `src/complira_graph/ingestion/pipeline_llm_client.py`
**Layer:** Repository / External Client (Layer 3)
**Responsibility:** Thin sync wrapper around `anthropic.Anthropic().messages.create()`. Accepts a batch of finding dicts, builds a structured JSON prompt, calls the Claude Haiku API, and returns a list of enrichment dicts. Has no dependency on `ClaudeLLMService`, Redis, or any async machinery.

**Dependencies:**
- `anthropic` (sync client only)
- `os` (for `ANTHROPIC_API_KEY` env var)
- `json` (prompt construction and response parsing)
- `logging`

**Key class: `PipelineLLMClient`**

**Constructor:**
```python
def __init__(
    self,
    model: str = "claude-haiku-4-5-20251001",
    max_tokens: int = 2048,
    api_key: str | None = None,
) -> None:
```
- `model`: Defaults to `claude-haiku-4-5-20251001`; overridable via env `ANTHROPIC_MODEL_HAIKU`.
- `max_tokens`: Controls cost/latency; 2048 is sufficient for 10 findings.
- `api_key`: If `None`, reads from `ANTHROPIC_API_KEY` env var (via `anthropic.Anthropic()`'s default resolution).
- Instantiates `self._client = anthropic.Anthropic(api_key=api_key)` — sync client.

**Primary method:**
```python
def call_batch(
    self,
    findings: list[dict],
) -> list[dict]:
```
- **Input:** `findings` — list of at most 10 finding dicts, each containing keys: `_key`, `cve_id` (nullable), `rule_id` (nullable), `severity`, `package_name` (nullable), `cvss_base` (nullable).
- **Output:** list of dicts with keys: `_key`, `llm_risk_summary`, `llm_remediation`, `llm_attack_surface`. Length matches `findings` length; on per-finding parse failure, returns `None` for that finding's entry.
- **Logic:**
  1. Build system prompt: instructs Claude to return a JSON array of objects with keys `finding_key`, `risk_summary`, `remediation`, `attack_surface`.
  2. Build user prompt: serialize each finding as a compact JSON line with context fields.
  3. Call `self._client.messages.create(model=self._model, max_tokens=self._max_tokens, messages=[...])`.
  4. Parse `response.content[0].text` as JSON.
  5. Build result map keyed by `finding_key`; merge with input order.
  6. Return `(results_list, input_tokens, output_tokens)` as a named tuple `LLMBatchResult`.
- **Failure handling:** If `anthropic.APIError` or `json.JSONDecodeError` is raised, log the error and re-raise. The calling pipeline decides whether to skip or fail the run.

**Named tuple:**
```python
from typing import NamedTuple

class LLMBatchResult(NamedTuple):
    results: list[dict]        # Per-finding enrichment dicts (may contain None entries)
    input_tokens: int          # Anthropic token count for billing log
    output_tokens: int         # Anthropic token count for billing log
```

**System prompt design:**
```
You are a cybersecurity analyst. For each finding provided, return a JSON array.
Each element must have:
  "finding_key": string (exact value from input)
  "risk_summary": string (≤3 sentences, plain language risk description)
  "remediation": string (1–3 concrete remediation steps)
  "attack_surface": one of ["network", "local", "adjacent"]

Return ONLY valid JSON. No markdown. No explanations outside the JSON array.
```

**User prompt structure:**
```
Analyze the following security findings:
[
  {"finding_key": "abc123", "cve_id": "CVE-2024-1234", "severity": "HIGH", ...},
  {"finding_key": "def456", "rule_id": "CWE-89", "severity": "MEDIUM", ...},
  ...
]
```

**Private helpers:**
```python
def _build_system_prompt(self) -> str: ...

def _build_user_prompt(self, findings: list[dict]) -> str: ...

def _parse_response(
    self,
    raw_text: str,
    finding_keys: list[str],
) -> list[dict]: ...
    # Attempts json.loads(raw_text)
    # Falls back to extracting from ```json ... ``` code blocks
    # Returns list matching finding_keys order; missing keys yield empty dict
```

---

### 5.2 `scan_llm_enrichment_repository.py` (New)

**Location:** `src/complira_graph/ingestion/scan_llm_enrichment_repository.py`
**Layer:** Repository (Layer 3)
**Responsibility:** Write LLM-generated fields to `scan_findings` documents; write aggregate token usage to `scan_runs`.

**Dependencies:**
- `arango.database.StandardDatabase`
- `datetime`, `logging`

**Constructor (follows Phase 1 pattern):**
```python
def __init__(self, db: StandardDatabase) -> None:
    self._db = db
```

**Methods:**

```python
def bulk_write_llm_fields(self, updates: list[dict]) -> None:
```
- **Input:** `updates` — list of dicts, each with `_key` plus zero or more of: `llm_risk_summary`, `llm_remediation`, `llm_attack_surface`, `llm_enriched_at`.
- **Output:** None (side-effect: AQL UPDATE).
- **Logic:** Chunks at 500 per AQL call (same as Phase 1 `bulk_update_findings`). Uses `OPTIONS {keepNull: false}` to avoid overwriting existing values with null.
- **AQL pattern:**
```aql
FOR u IN @updates
    UPDATE u._key WITH u IN scan_findings
    OPTIONS {keepNull: false}
```
- **Log:** `scan_llm_enrichment_repo.bulk_write_llm_fields` with `total` and `chunks` counts.

```python
def write_token_usage(
    self,
    scan_run_id: str,
    token_usage: dict,
) -> None:
```
- **Input:** `scan_run_id`, `token_usage` — dict with keys `input_tokens: int`, `output_tokens: int`, `total_tokens: int`, `model: str`.
- **Output:** None (side-effect: update `scan_runs` document).
- **Logic:** Merges `llm_token_usage` field into `scan_runs` document via `collection.update()`.
- **AQL pattern (single document update):**
```python
self._db.collection("scan_runs").update(
    {"_key": scan_run_id, "llm_token_usage": token_usage, "updated_at": _utcnow()}
)
```

```python
def update_scan_run_status(
    self,
    scan_run_key: str,
    status: str,
    extra_fields: dict | None = None,
) -> None:
```
- Convenience wrapper matching Phase 1 pattern; delegates to `_db.collection("scan_runs").update()`.
- Used to write `status="llm_enriched"` at stage completion.

---

### 5.3 `scan_blast_radius_repository.py` (New)

**Location:** `src/complira_graph/ingestion/scan_blast_radius_repository.py`
**Layer:** Repository (Layer 3)
**Responsibility:** All AQL related to blast radius: component lookup by purl, INBOUND `depends_on` traversal, `project_uses_component` count for score normalization, and bulk writes of blast radius fields to `scan_findings`.

**Dependencies:**
- `arango.database.StandardDatabase`
- `datetime`, `logging`

**Constructor:**
```python
def __init__(self, db: StandardDatabase) -> None:
    self._db = db
```

**Methods:**

```python
def aql_blast_radius_for_purl(
    self,
    purl: str,
    depth_max: int = 5,
) -> dict:
```
- **Input:** `purl` — package URL string (e.g. `pkg:npm/lodash@4.17.21`). `depth_max` — INBOUND traversal depth cap (default 5, per constraint).
- **Output:** dict with keys:
  - `affected_components: list[str]` — purls of all reachable components (deduplicated)
  - `blast_radius_path: list[str]` — component names along the longest traversal path
  - `component_found: bool` — whether the purl resolved to a component vertex
- **Logic:**
  1. `LET start = FIRST(FOR c IN components FILTER c.purl == @purl RETURN c)` — resolve purl to component vertex.
  2. If start is null, return empty result (component not in reference DB — normal for SAST findings that have no purl in DB).
  3. INBOUND traversal on `depends_on` edge collection from start vertex.
  4. Collect all visited vertex purls; compute longest path via `PATH` variable.
- **AQL pattern:**
```aql
LET start = FIRST(
    FOR c IN components
        FILTER c.purl == @purl
        LIMIT 1
        RETURN c
)
LET traversal = (
    start != null
    ? (
        FOR v, e, p IN 1..@depth_max INBOUND start depends_on
            RETURN DISTINCT {
                purl:  v.purl,
                name:  v.name,
                depth: LENGTH(p.edges)
            }
    )
    : []
)
LET max_depth_row = FIRST(
    FOR row IN traversal
        SORT row.depth DESC
        LIMIT 1
        RETURN row
)
RETURN {
    affected_purls: traversal[*].purl,
    affected_names: traversal[*].name,
    max_depth:      max_depth_row != null ? max_depth_row.depth : 0,
    found:          start != null
}
```
- **Failure handling:** On AQL exception, log and return `{"affected_components": [], "blast_radius_path": [], "component_found": False}`.

```python
def aql_total_project_components(
    self,
    project_id: str | None = None,
) -> int:
```
- **Input:** Optional `project_id`. If provided, counts components used by that specific project; otherwise counts total components reachable via any `project_uses_component` edge.
- **Output:** `int` — total component count for score denominator.
- **AQL pattern:**
```aql
-- With project_id:
RETURN LENGTH(
    FOR e IN project_uses_component
        FILTER e._from == CONCAT("projects/", @project_id)
        RETURN 1
)

-- Without project_id (global count):
RETURN LENGTH(
    FOR c IN components
        FILTER LENGTH(
            FOR e IN 1..1 INBOUND c project_uses_component
                LIMIT 1 RETURN 1
        ) > 0
        RETURN 1
)
```
- **Failure handling:** On exception, log and return `1` (prevents division by zero; blast_radius_score will be floored to min value rather than erroring).

```python
def bulk_write_blast_radius(self, updates: list[dict]) -> None:
```
- **Input:** `updates` — list of dicts each with `_key` plus: `blast_radius_score`, `affected_components`, `blast_radius_path`, `blast_radius_computed_at`.
- **Output:** None (side-effect: AQL UPDATE on `scan_findings`).
- **Logic:** Chunks at 500. `OPTIONS {keepNull: false}`.
- **AQL pattern:**
```aql
FOR u IN @updates
    UPDATE u._key WITH u IN scan_findings
    OPTIONS {keepNull: false}
```

```python
def update_scan_run_status(
    self,
    scan_run_key: str,
    status: str,
    extra_fields: dict | None = None,
) -> None:
```
- Convenience wrapper matching Phase 1 pattern; writes `status="blast_radius_computed"` at stage completion.

---

### 5.4 `llm_enrichment_pipeline.py` (New)

**Location:** `src/complira_graph/ingestion/llm_enrichment_pipeline.py`
**Layer:** Pipeline (Layer 2)
**Responsibility:** UC-010. Reads all `scan_findings` for the run in batches of 10, dispatches each batch to `PipelineLLMClient.call_batch()`, accumulates token usage, and writes LLM fields back via `ScanLLMEnrichmentRepository`. Transitions `scan_run.status` to `"llm_enriched"`.

**Dependencies:**
- `ScanEnrichmentRepository` (for `fetch_findings_for_run()`)
- `ScanLLMEnrichmentRepository` (for field writes + token usage)
- `PipelineLLMClient` (for LLM calls)
- `arango.database.StandardDatabase`, `logging`

**Constructor:**
```python
def __init__(
    self,
    db: StandardDatabase,
    repo: ScanEnrichmentRepository,
    llm_repo: ScanLLMEnrichmentRepository,
    llm_client: PipelineLLMClient,
) -> None:
    self._db = db
    self._repo = repo
    self._llm_repo = llm_repo
    self._llm_client = llm_client
```

Note: `PipelineCoordinator.__init__` instantiates `PipelineLLMClient` and `ScanLLMEnrichmentRepository` and passes them in. `LLMEnrichmentPipeline` holds zero LLM API calls directly.

**Primary method:**
```python
def run(self, scan_run_id: str, tenant_id: str) -> None:
```
- **Status trigger:** Called when `scan_run.status == "mapped"`.
- **Status result:** `scan_run.status = "llm_enriched"` on success; `pipeline_failed` on exception (set by coordinator).
- **Call sequence:**
  1. Initialize `total_input_tokens = 0`, `total_output_tokens = 0`, `llm_failure_count = 0`.
  2. `for batch in self._repo.fetch_findings_for_run(scan_run_id, tenant_id, batch_size=500):`
  3. For each batch, split into sub-batches of 10: `for i in range(0, len(batch), 10): sub_batch = batch[i:i+10]`.
  4. `try: result = self._llm_client.call_batch(sub_batch)` — if exception, log + increment `llm_failure_count`, skip sub-batch (do not re-raise unless all sub-batches fail).
  5. `updates = self._build_llm_updates(sub_batch, result.results)` — merges LLM output with `_key`.
  6. `self._llm_repo.bulk_write_llm_fields(updates)`.
  7. Accumulate `total_input_tokens += result.input_tokens`, `total_output_tokens += result.output_tokens`.
  8. After all batches: `self._llm_repo.write_token_usage(scan_run_id, {...})`.
  9. If `llm_failure_count > 0` and all sub-batches failed: raise `RuntimeError("all_llm_batches_failed")`.
  10. `self._llm_repo.update_scan_run_status(scan_run_id, "llm_enriched", extra_fields={"llm_enriched_at": _utcnow()})`.

**Private helpers:**

```python
def _build_llm_updates(
    self,
    findings: list[dict],
    llm_results: list[dict],
) -> list[dict]:
```
- **Input:** original findings list and corresponding LLM results (same order, may have `None` entries for failed findings).
- **Output:** list of update dicts: `{"_key": fp, "llm_risk_summary": ..., "llm_remediation": ..., "llm_attack_surface": ..., "llm_enriched_at": now}`.
- **Logic:** Zip `findings` with `llm_results`. If `llm_results[i]` is `None` or empty, skip that finding's LLM fields (write only `llm_enriched_at` to mark the attempt). Normalize `llm_attack_surface` to lowercase; if not in `{"network", "local", "adjacent"}`, default to `"network"`.

```python
def _context_for_finding(self, finding: dict) -> dict:
```
- **Input:** Single finding dict.
- **Output:** Compact context dict for LLM prompt: `{"finding_key": _key, "cve_id": ...|null, "rule_id": ...|null, "severity": ..., "package_name": ...|null, "cvss_base": ...|null}`.
- **Logic:** Returns CVE-based context if `cve_id` is present; falls back to `rule_id + severity` for SAST/IaC findings (AC-032).

---

### 5.5 `blast_radius_pipeline.py` (New)

**Location:** `src/complira_graph/ingestion/blast_radius_pipeline.py`
**Layer:** Pipeline (Layer 2)
**Responsibility:** UC-011. Reads all `scan_findings` for the run, groups by unique purl values, executes one `aql_blast_radius_for_purl()` call per unique purl (not per finding), applies results to all findings sharing that purl, computes scores, and writes blast radius fields. Transitions `scan_run.status` to `"blast_radius_computed"`.

**Dependencies:**
- `ScanEnrichmentRepository` (for `fetch_findings_for_run()`)
- `ScanBlastRadiusRepository` (for traversal + writes)
- `arango.database.StandardDatabase`, `logging`

**Constructor:**
```python
def __init__(
    self,
    db: StandardDatabase,
    repo: ScanEnrichmentRepository,
    blast_repo: ScanBlastRadiusRepository,
) -> None:
    self._db = db
    self._repo = repo
    self._blast_repo = blast_repo
```

**Primary method:**
```python
def run(self, scan_run_id: str, tenant_id: str) -> None:
```
- **Status trigger:** Called when `scan_run.status == "llm_enriched"`.
- **Status result:** `scan_run.status = "blast_radius_computed"` on success.
- **Call sequence:**
  1. Accumulate all findings: `for batch in self._repo.fetch_findings_for_run(...)`.
  2. Build `purl_to_fingerprints: dict[str, list[str]]` — group fingerprints by purl (non-null purls only).
  3. Build `no_purl_fingerprints: list[str]` — fingerprints with null/empty purl.
  4. `total_components = self._blast_repo.aql_total_project_components()` — global denominator (all components reachable via any `project_uses_component` edge). Global count is chosen for consistent cross-project score comparability; project-id-scoped counting is supported by `aql_total_project_components(project_id)` for future use if per-project normalization is required.
  5. For each unique purl: `traversal = self._blast_repo.aql_blast_radius_for_purl(purl)`.
  6. Compute `score = min(1.0, len(traversal["affected_components"]) / max(total_components, 1))`.
  7. Build update dicts for all findings sharing this purl.
  8. Build zero-value update dicts for no-purl findings.
  9. `self._blast_repo.bulk_write_blast_radius(all_updates)` — single bulk write call.
  10. `self._blast_repo.update_scan_run_status(scan_run_id, "blast_radius_computed", ...)`.

**Private helpers:**

```python
def _build_blast_updates_for_purl(
    self,
    fingerprints: list[str],
    traversal_result: dict,
    score: float,
) -> list[dict]:
```
- **Input:** fingerprints sharing a purl, traversal result dict, computed score.
- **Output:** list of update dicts: `{"_key": fp, "blast_radius_score": score, "affected_components": [...purls], "blast_radius_path": [...names], "blast_radius_computed_at": now}`.

```python
def _build_zero_blast_updates(
    self,
    fingerprints: list[str],
) -> list[dict]:
```
- **Input:** fingerprints with no purl (SAST/IaC findings).
- **Output:** list of update dicts: `{"_key": fp, "blast_radius_score": 0.0, "affected_components": [], "blast_radius_path": [], "blast_radius_computed_at": now}`.

**Optimization note:** Deduplicating by purl before AQL traversal is important for large scan runs with many findings referencing the same component. A scan of 2000 findings may have only 50 unique purls; this reduces AQL round-trips from 2000 to 50.

---

### 5.6 `epss_velocity_pipeline.py` (New)

**Location:** `src/complira_graph/ingestion/epss_velocity_pipeline.py`
**Layer:** Pipeline (Layer 2)
**Responsibility:** UC-012. Reads all `scan_findings` for the run, collects distinct CVE IDs, fetches 30-day EPSS history in batch from `ScanEnrichmentRepository.aql_get_epss_history_batch()`, computes linear regression slope per CVE (pure Python), classifies trend, and writes velocity fields back via `ScanEnrichmentRepository.bulk_update_findings()`. Transitions `scan_run.status` to `"velocity_computed"`.

**Dependencies:**
- `ScanEnrichmentRepository` (for `fetch_findings_for_run()` + `aql_get_epss_history_batch()` + `bulk_update_findings()` + `update_scan_run_status()`)
- `datetime`, `logging`

**Constructor:**
```python
def __init__(
    self,
    db: StandardDatabase,
    repo: ScanEnrichmentRepository,
) -> None:
    self._db = db
    self._repo = repo
```

Note: `EPSSVelocityPipeline` uses only `ScanEnrichmentRepository` — it does not need a new repository. EPSS velocity reads and writes use the same collection access patterns as Phase 1 enrichment.

**Primary method:**
```python
def run(self, scan_run_id: str, tenant_id: str) -> None:
```
- **Status trigger:** Called when `scan_run.status == "blast_radius_computed"`.
- **Status result:** `scan_run.status = "velocity_computed"` on success.
- **Call sequence:**
  1. Accumulate all findings.
  2. Build `cve_key_to_fingerprints: dict[str, list[str]]` — normalized CVE key → list of fingerprints.
  3. Build `no_cve_fingerprints: list[str]` — fingerprints with null/empty cve_id.
  4. `cutoff_date = (datetime.now(utc) - timedelta(days=30)).strftime("%Y-%m-%d")`.
  5. `history_map = self._repo.aql_get_epss_history_batch(list(cve_key_to_fingerprints.keys()), cutoff_date)` → `dict[cve_key, list[{"score": float, "date": str}]]`.
  6. For each CVE key: `slope = self._compute_slope(history_map.get(cve_key, []))`.
  7. `trend = self._classify_trend(slope)`.
  8. Build update dicts for all findings with this CVE key.
  9. Build zero-value update dicts for no-CVE findings.
  10. `self._repo.bulk_update_findings(all_updates)`.
  11. `self._repo.update_scan_run_status(scan_run_id, "velocity_computed", ...)`.

**Private helpers:**

```python
def _compute_slope(self, history: list[dict]) -> float:
```
- **Input:** `history` — list of `{"score": float, "date": "YYYY-MM-DD"}` sorted ascending by date. If fewer than 2 data points, returns `0.0` (AC-048).
- **Output:** Linear regression slope (float). Pure Python implementation — no numpy.
- **Algorithm:**
  ```python
  n = len(history)
  if n < 2:
      return 0.0
  xs = list(range(n))         # x = day index (0, 1, 2, ...)
  ys = [h["score"] for h in history]
  mean_x = sum(xs) / n
  mean_y = sum(ys) / n
  numerator   = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
  denominator = sum((xs[i] - mean_x) ** 2 for i in range(n))
  if denominator == 0:
      return 0.0
  return numerator / denominator
  ```

```python
def _classify_trend(self, slope: float) -> str:
```
- **Input:** Linear regression slope.
- **Output:** `"rising"` | `"stable"` | `"falling"`.
- **Logic:**
  ```python
  weekly_delta = slope * 7
  if weekly_delta > 0.05:
      return "rising"
  if weekly_delta < -0.05:
      return "falling"
  return "stable"
  ```
- Thresholds: `slope * 7 > 0.05` → rising (AC-046); `slope * 7 < -0.05` → falling (AC-047); else → stable.

```python
def _build_velocity_updates(
    self,
    fingerprints: list[str],
    slope: float,
    trend: str,
) -> list[dict]:
```
- **Output:** `{"_key": fp, "epss_velocity": slope, "epss_trend": trend, "epss_velocity_computed_at": now}`.

```python
def _build_zero_velocity_updates(
    self,
    fingerprints: list[str],
) -> list[dict]:
```
- **Output:** `{"_key": fp, "epss_velocity": 0.0, "epss_trend": "stable", "epss_velocity_computed_at": now}` (AC-045).

---

### 5.7 `pipeline_coordinator.py` (Modified)

**Location:** `src/complira_graph/ingestion/pipeline_coordinator.py`
**Change Type:** Status guard extension + Phase 2 stage wiring

**Delta — Status Constants (as-is → to-be):**

```python
# AS-IS:
_RETRIABLE_STATUSES = frozenset({
    "completed", "enriched", "compacted",
    "pipeline_failed", "enrichment_pending",
})
_ENRICHMENT_DONE = frozenset({"enriched", "compacted", "mapped"})
_COMPACTION_DONE = frozenset({"compacted", "mapped"})
_MAPPING_DONE    = frozenset({"mapped"})

# TO-BE (additions in bold):
_RETRIABLE_STATUSES = frozenset({
    "completed", "enriched", "compacted",
    "pipeline_failed", "enrichment_pending",
    "mapped",                    # NEW — Phase 2 starts here
    "llm_enriched",              # NEW — re-trigger from mid-Phase 2
    "blast_radius_computed",     # NEW — re-trigger from mid-Phase 2
})
_ENRICHMENT_DONE = frozenset({"enriched", "compacted", "mapped",
                               "llm_enriched", "blast_radius_computed",
                               "velocity_computed"})          # NEW
_COMPACTION_DONE = frozenset({"compacted", "mapped",
                               "llm_enriched", "blast_radius_computed",
                               "velocity_computed"})          # NEW
_MAPPING_DONE    = frozenset({"mapped",
                               "llm_enriched", "blast_radius_computed",
                               "velocity_computed"})          # NEW
_LLM_DONE   = frozenset({"llm_enriched", "blast_radius_computed", "velocity_computed"})  # NEW
_BLAST_DONE = frozenset({"blast_radius_computed", "velocity_computed"})                   # NEW
_VELOCITY_DONE = frozenset({"velocity_computed"})                                         # NEW
```

**Delta — `__init__` (as-is → to-be):**

```python
# AS-IS:
def __init__(self, db: StandardDatabase) -> None:
    self._db = db
    self._repo = ScanEnrichmentRepository(db)
    self._run_repo = EvidenceRunRepository(db)
    self._enrichment    = EnrichmentPipeline(db, self._repo)
    self._compaction    = CompactionPipeline(db, self._repo)
    self._control_mapping = ControlMappingPipeline(db, self._repo)

# TO-BE — new lines only:
def __init__(self, db: StandardDatabase) -> None:
    self._db = db
    self._repo     = ScanEnrichmentRepository(db)
    self._run_repo = EvidenceRunRepository(db)
    # Phase 1 stages (unchanged)
    self._enrichment      = EnrichmentPipeline(db, self._repo)
    self._compaction      = CompactionPipeline(db, self._repo)
    self._control_mapping = ControlMappingPipeline(db, self._repo)
    # Phase 2 stages (new)
    self._llm_repo     = ScanLLMEnrichmentRepository(db)
    self._blast_repo   = ScanBlastRadiusRepository(db)
    self._llm_client   = PipelineLLMClient()
    self._llm_enrichment  = LLMEnrichmentPipeline(db, self._repo, self._llm_repo, self._llm_client)
    self._blast_radius    = BlastRadiusPipeline(db, self._repo, self._blast_repo)
    self._epss_velocity   = EPSSVelocityPipeline(db, self._repo)
```

**Delta — `run_post_ingest_pipeline` (as-is → to-be):**

After Stage 3 (control_mapping) completes or is skipped, add three new stage blocks:

```python
# Stage 4: LLM Enrichment (NEW)
# current_status from the single read at top of method — same pattern as Phase 1 stages
if force or current_status not in _LLM_DONE:
    try:
        self._llm_enrichment.run(scan_run_id, tenant_id)
    except Exception as exc:
        log.exception("pipeline_coordinator.llm_enrichment_failed", ...)
        self._mark_failed(scan_run_id, str(exc))
        return
else:
    log.info("pipeline_coordinator.llm_enrichment_skipped", ...)

# Stage 5: Blast Radius (NEW)
if force or current_status not in _BLAST_DONE:
    try:
        self._blast_radius.run(scan_run_id, tenant_id)
    except Exception as exc:
        log.exception("pipeline_coordinator.blast_radius_failed", ...)
        self._mark_failed(scan_run_id, str(exc))
        return
else:
    log.info("pipeline_coordinator.blast_radius_skipped", ...)

# Stage 6: EPSS Velocity (NEW)
if force or current_status not in _VELOCITY_DONE:
    try:
        self._epss_velocity.run(scan_run_id, tenant_id)
    except Exception as exc:
        log.exception("pipeline_coordinator.epss_velocity_failed", ...)
        self._mark_failed(scan_run_id, str(exc))
        return
else:
    log.info("pipeline_coordinator.epss_velocity_skipped", ...)
```

**Pattern note (single-read-at-top):** Phase 2 stage guards use the same `current_status` variable read once at the top of `run_post_ingest_pipeline()`, identical to Phase 1. Re-reads between Phase 2 stages are unnecessary: all Phase 2 guard frozensets (`_LLM_DONE`, `_BLAST_DONE`, `_VELOCITY_DONE`) are defined such that any initial `current_status` value correctly drives skip/run decisions for all three stages without needing the intermediate status written by the preceding stage. Verified correctness for all entry points: `"completed"` → runs all three; `"llm_enriched"` → skips LLM, runs blast+velocity; `"blast_radius_computed"` → skips LLM+blast, runs velocity; `"velocity_computed"` → skips all (not retriable, returned at top). No extra DB round-trips.

**Docstring update (module-level):**
```
Stage sequence: EnrichmentPipeline → CompactionPipeline → ControlMappingPipeline
                → LLMEnrichmentPipeline → BlastRadiusPipeline → EPSSVelocityPipeline
Status chain:   completed → enriched → compacted → mapped
                → llm_enriched → blast_radius_computed → velocity_computed
```

---

### 5.8 `scan_enrichment_repository.py` (Modified)

**Location:** `src/complira_graph/ingestion/scan_enrichment_repository.py`
**Change Type:** New method — `aql_get_epss_history_batch()`

**New method:**

```python
def aql_get_epss_history_batch(
    self,
    cve_keys: list[str],
    cutoff_date: str,
) -> dict[str, list[dict]]:
```
- **Input:**
  - `cve_keys` — list of normalized CVE keys in ArangoDB `_key` format (e.g. `"CVE_2024_1234"`).
  - `cutoff_date` — ISO date string `"YYYY-MM-DD"` representing the 30-day lookback floor.
- **Output:** `dict[str, list[dict]]` — maps each `cve_key` to a time-ordered list of `{"score": float, "date": "YYYY-MM-DD"}` dicts. Missing CVEs return empty list.
- **AQL pattern:**
```aql
FOR cve_key IN @cve_keys
    LET cve_doc = DOCUMENT(CONCAT("vulnerabilities/", cve_key))
    LET history = (
        cve_doc != null
        ? (
            FOR e IN has_epss
                FILTER e._from == cve_doc._id
                LET point = DOCUMENT(e._to)
                FILTER point != null
                  AND point.score_date >= @cutoff_date
                SORT point.score_date ASC
                RETURN {
                    score: point.epss_score,
                    date:  point.score_date
                }
          )
        : []
    )
    RETURN {
        cve_key: cve_key,
        history: history
    }
```
- **Failure handling:** On AQL exception, log `scan_enrichment_repo.aql_get_epss_history_batch_failed` with `cve_count`; return `{}` (EPSSVelocityPipeline handles empty map as no-data → stable trend).
- **Log:** `scan_enrichment_repo.aql_get_epss_history_batch_complete` with `queried` and `found_with_history` counts.

**No other changes to `ScanEnrichmentRepository`.** The `bulk_update_findings()` method is reused by `EPSSVelocityPipeline` for velocity field writes — no new write method needed.

---

### 5.9 `__init__.py` (Modified)

**Location:** `src/complira_graph/ingestion/__init__.py`

**Delta — new imports and exports:**

```python
# New imports to add:
from complira_graph.ingestion.pipeline_llm_client import PipelineLLMClient
from complira_graph.ingestion.scan_llm_enrichment_repository import ScanLLMEnrichmentRepository
from complira_graph.ingestion.scan_blast_radius_repository import ScanBlastRadiusRepository
from complira_graph.ingestion.llm_enrichment_pipeline import LLMEnrichmentPipeline
from complira_graph.ingestion.blast_radius_pipeline import BlastRadiusPipeline
from complira_graph.ingestion.epss_velocity_pipeline import EPSSVelocityPipeline

# __all__ additions:
"PipelineLLMClient",
"ScanLLMEnrichmentRepository",
"ScanBlastRadiusRepository",
"LLMEnrichmentPipeline",
"BlastRadiusPipeline",
"EPSSVelocityPipeline",
```

**Updated module docstring addition:**
```python
"""
Phase 2 additions:
- PipelineLLMClient: sync Anthropic Claude wrapper for pipeline layer
- ScanLLMEnrichmentRepository: write LLM fields to scan_findings
- ScanBlastRadiusRepository: blast radius AQL + writes
- LLMEnrichmentPipeline: UC-010 LLM enrichment stage
- BlastRadiusPipeline: UC-011 blast radius simulation stage
- EPSSVelocityPipeline: UC-012 EPSS velocity detection stage
"""
```

---

## 6. Data Models

### 6.1 `scan_findings` — New Fields (Phase 2)

The following fields are added to `scan_findings` documents. All are nullable before Phase 2 processing.

#### UC-010 LLM Enrichment Fields

| Field | Type | Description | Constraint |
|---|---|---|---|
| `llm_risk_summary` | `str` | Plain-language risk description | ≤3 sentences; set by Claude Haiku |
| `llm_remediation` | `str` | Remediation guidance | 1–3 steps; set by Claude Haiku |
| `llm_attack_surface` | `str` | Attack surface classification | ∈ `{"network", "local", "adjacent"}` |
| `llm_enriched_at` | `str` | ISO 8601 UTC timestamp of LLM enrichment | Set by `LLMEnrichmentPipeline` |

#### UC-011 Blast Radius Fields

| Field | Type | Description | Constraint |
|---|---|---|---|
| `blast_radius_score` | `float` | Proportion of project components affected | ∈ [0.0, 1.0]; 0.0 for SAST/IaC findings |
| `affected_components` | `list[str]` | Purls of all reachable dependent components | Deduplicated; empty list for no-purl findings |
| `blast_radius_path` | `list[str]` | Component names along longest traversal path | Empty list for no-purl findings |
| `blast_radius_computed_at` | `str` | ISO 8601 UTC timestamp | Set by `BlastRadiusPipeline` |

#### UC-012 EPSS Velocity Fields

| Field | Type | Description | Constraint |
|---|---|---|---|
| `epss_velocity` | `float` | Linear regression slope over 30-day EPSS history | 0.0 for no-CVE findings or insufficient data |
| `epss_trend` | `str` | Trend classification | ∈ `{"rising", "stable", "falling"}` |
| `epss_velocity_computed_at` | `str` | ISO 8601 UTC timestamp | Set by `EPSSVelocityPipeline` |

### 6.2 `scan_runs` — New Fields (Phase 2)

| Field | Type | Description | Set By |
|---|---|---|---|
| `llm_enriched_at` | `str` | ISO 8601 UTC timestamp when LLM enrichment completed | `ScanLLMEnrichmentRepository.update_scan_run_status()` |
| `llm_token_usage` | `dict` | Aggregate token counts: `{input_tokens, output_tokens, total_tokens, model}` | `ScanLLMEnrichmentRepository.write_token_usage()` |
| `blast_radius_computed_at` | `str` | ISO 8601 UTC timestamp | `ScanBlastRadiusRepository.update_scan_run_status()` |
| `velocity_computed_at` | `str` | ISO 8601 UTC timestamp | `ScanEnrichmentRepository.update_scan_run_status()` |

### 6.3 `scan_runs` — Status Chain Extension

Phase 1 terminal status `"mapped"` becomes an intermediate status in Phase 2. Full status chain:

```
running
  → completed          (ingestion done)
  → enriched           (UC-007 done)
  → compacted          (UC-008 done)
  → mapped             (UC-009 done; Phase 1 terminal; Phase 2 trigger)
  → llm_enriched       (UC-010 done)
  → blast_radius_computed  (UC-011 done)
  → velocity_computed  (UC-012 done; Phase 2 terminal)
  → pipeline_failed    (any stage failed; retriable)
  → enrichment_pending (reference DB unreachable; retriable)
```

### 6.4 `epss_history` — Read Model (Reference, No Changes)

Phase 2 reads from `epss_history` via the `has_epss` edge. No writes. Existing schema:

| Field | Type | Description |
|---|---|---|
| `cve_id` | `str` | CVE identifier (hyphen format, e.g. `CVE-2024-1234`) |
| `epss_score` | `float` | EPSS probability score ∈ [0, 1] |
| `percentile` | `float` | EPSS percentile ∈ [0, 1] |
| `score_date` | `str` | ISO date `YYYY-MM-DD` |

Document key format: `{normalized_cve_key}_{YYYY_MM_DD}` (e.g. `CVE_2024_1234_2026_03_22`).

### 6.5 `components` — Read Model (Reference, No Changes)

Phase 2 reads from `components` via the `depends_on` and `project_uses_component` edges. No writes.

| Field | Type | Description |
|---|---|---|
| `purl` | `str` | Package URL (e.g. `pkg:npm/lodash@4.17.21`) |
| `name` | `str` | Component display name |
| `version` | `str` | Component version |

---

## 7. Error Handling

### 7.1 Error Handling Philosophy

Phase 2 follows the Phase 1 contract:
- **Stage exception → `pipeline_failed`**: Any unhandled exception from a Phase 2 stage causes the coordinator to set `scan_run.status = "pipeline_failed"` with the error message (truncated to 2000 chars). Partial writes are retained (idempotent re-run restores state).
- **Per-item failure → log and skip**: Within a stage, individual item failures (e.g. one LLM batch call) are logged and skipped without aborting the stage, unless ALL items fail (which becomes a stage-level exception).
- **External API unavailability**: LLM API failures that persist across all batches propagate as `RuntimeError` from the pipeline stage, triggering `pipeline_failed` in the coordinator.

### 7.2 Phase 2 Error Matrix

| Error Scenario | Detection Point | Handling | Status Result |
|---|---|---|---|
| Anthropic API connection failure (single batch) | `PipelineLLMClient.call_batch()` | Log + skip batch; continue remaining batches | Stage continues |
| Anthropic API connection failure (ALL batches) | `LLMEnrichmentPipeline.run()` | Raise `RuntimeError("all_llm_batches_failed")` | `pipeline_failed` |
| LLM response JSON parse error (single batch) | `PipelineLLMClient._parse_response()` | Log + return empty results for batch | Stage continues with no LLM fields for that batch |
| `depends_on` traversal AQL error | `ScanBlastRadiusRepository.aql_blast_radius_for_purl()` | Log + return empty result (blast_radius_score=0.0 for that purl) | Stage continues |
| `project_uses_component` count AQL error | `ScanBlastRadiusRepository.aql_total_project_components()` | Log + return `1` (safe denominator) | Stage continues with score based on /1 denominator |
| `has_epss` traversal AQL error | `ScanEnrichmentRepository.aql_get_epss_history_batch()` | Log + return `{}` (empty map) | All CVEs treated as no-history → stable trend |
| `bulk_write_llm_fields` AQL error | `ScanLLMEnrichmentRepository.bulk_write_llm_fields()` | Re-raise (write failure = stage failure) | `pipeline_failed` |
| `bulk_write_blast_radius` AQL error | `ScanBlastRadiusRepository.bulk_write_blast_radius()` | Re-raise | `pipeline_failed` |
| `bulk_update_findings` (velocity) AQL error | `ScanEnrichmentRepository.bulk_update_findings()` | Re-raise | `pipeline_failed` |
| No `scan_findings` for run | Any pipeline stage `run()` | Log + skip batch loop + write terminal status | Correct (empty scan) |
| `depends_on` edges empty (no SBOM ingested) | `aql_blast_radius_for_purl()` | Returns `affected_components=[]`; score=0.0 | Correct behavior; documented |
| `epss_history` empty (EPSS agent not run) | `aql_get_epss_history_batch()` | Returns `{}`; all velocity=0.0, trend=stable | Correct behavior; documented |
| Reference DB unreachable at Phase 2 entry | `PipelineCoordinator._verify_reference_db()` | Sets `enrichment_pending` | `enrichment_pending` |

### 7.3 Idempotency Guarantee

All Phase 2 writes use `UPDATE u._key WITH u IN <collection> OPTIONS {keepNull: false}` semantics (same as Phase 1). A re-run after `pipeline_failed` will:
1. Coordinator reads current status; if in `_RETRIABLE_STATUSES`, proceeds.
2. Stage guards check whether each Phase 2 stage's terminal status is already recorded; skip if done.
3. Writes are UPDATE (not INSERT) — no duplicate documents.
4. LLM token usage is overwritten (not accumulated) on re-run — last write wins.

### 7.4 Logging Standards

All Phase 2 modules follow the Phase 1 logging convention:
- `log.info("module.event", extra={...})` for stage boundaries and batch counts.
- `log.debug("module.event", extra={...})` for per-batch details.
- `log.warning("module.event", extra={...})` for recoverable per-item failures.
- `log.exception("module.event", extra={...})` for unexpected exceptions (includes traceback).

Structured log key naming: `{module_short_name}.{event_name}` e.g. `llm_enrichment_pipeline.batch_failed`, `blast_radius_pipeline.no_purl_skip`, `epss_velocity_pipeline.insufficient_history`.

---

## 8. Naming Decisions

### 8.1 New Class Names

| Class Name | Location | Rationale |
|---|---|---|
| `PipelineLLMClient` | `pipeline_llm_client.py` | Distinguishes from `ClaudeLLMService` (API layer); "Pipeline" prefix signals layer membership; "LLM" is the capability; "Client" signals it wraps an external API client |
| `ScanLLMEnrichmentRepository` | `scan_llm_enrichment_repository.py` | Follows Phase 1 `ScanEnrichmentRepository` naming convention; "LLM" distinguishes write concern |
| `ScanBlastRadiusRepository` | `scan_blast_radius_repository.py` | Same convention; "BlastRadius" is the domain term from requirements |
| `LLMEnrichmentPipeline` | `llm_enrichment_pipeline.py` | Follows `EnrichmentPipeline` pattern; "LLM" prefix distinguishes from Phase 1 enrichment |
| `BlastRadiusPipeline` | `blast_radius_pipeline.py` | Follows pipeline naming convention; domain term from requirements |
| `EPSSVelocityPipeline` | `epss_velocity_pipeline.py` | EPSS is standard acronym; "Velocity" is the feature name; follows pipeline pattern |

### 8.2 New Method Names

| Method | Class | Rationale |
|---|---|---|
| `call_batch(findings)` | `PipelineLLMClient` | "call" signals external API invocation; "batch" signals multi-item processing; matches Phase 1 `aql_enrich_batch` pattern |
| `bulk_write_llm_fields(updates)` | `ScanLLMEnrichmentRepository` | "bulk_write" parallels `bulk_update_findings`; "llm_fields" specifies the concern |
| `write_token_usage(scan_run_id, token_usage)` | `ScanLLMEnrichmentRepository` | "write" (not "update") because this is a first-time write on each run; clear purpose |
| `aql_blast_radius_for_purl(purl)` | `ScanBlastRadiusRepository` | "aql_" prefix follows Phase 1 convention for AQL methods; "for_purl" describes the input |
| `aql_total_project_components()` | `ScanBlastRadiusRepository` | "aql_" prefix; "total_project_components" matches requirements terminology |
| `bulk_write_blast_radius(updates)` | `ScanBlastRadiusRepository` | "bulk_write" parallel to LLM repo; "blast_radius" specifies concern |
| `aql_get_epss_history_batch(cve_keys, cutoff_date)` | `ScanEnrichmentRepository` | "aql_get" prefix follows `aql_enrich_batch`, `aql_get_cwe_parent_map`; "epss_history_batch" describes the read |
| `_compute_slope(history)` | `EPSSVelocityPipeline` | "compute" signals pure computation; "slope" is the mathematical output |
| `_classify_trend(slope)` | `EPSSVelocityPipeline` | "classify" signals categorization; "trend" is the domain output |

### 8.3 New Field Names (scan_findings)

| Field Name | Rationale |
|---|---|
| `llm_risk_summary` | "llm_" prefix signals AI-generated content; "risk_summary" matches requirements language |
| `llm_remediation` | "llm_" prefix; "remediation" is standard security terminology |
| `llm_attack_surface` | "llm_" prefix; "attack_surface" matches MITRE/CVSS terminology |
| `llm_enriched_at` | Pattern matches Phase 1's `enriched_at`; "llm_" prefix distinguishes origin |
| `blast_radius_score` | Exact requirements language; "score" suffix consistent with `risk_score`, `epss_score` |
| `affected_components` | Plural noun; matches requirements list of purls |
| `blast_radius_path` | "path" signals graph traversal path; "blast_radius_" prefix groups related fields |
| `blast_radius_computed_at` | Pattern matches `llm_enriched_at`, `epss_velocity_computed_at` |
| `epss_velocity` | "epss_" prefix groups EPSS-related fields (alongside `epss_score`, `epss_percentile`) |
| `epss_trend` | Groups with `epss_velocity`; "trend" is the domain term |
| `epss_velocity_computed_at` | Consistent `computed_at` suffix pattern |

### 8.4 Status String Decisions

| Status String | Rationale |
|---|---|
| `"llm_enriched"` | Past-tense verb pattern matches `"enriched"`, `"compacted"`, `"mapped"`; "llm_" prefix distinguishes from Phase 1 `"enriched"` |
| `"blast_radius_computed"` | "computed" pattern; "blast_radius_" domain prefix |
| `"velocity_computed"` | Consistent "computed" suffix; "velocity_" specifies which computation |

---

## 9. Naming-Drift Check

This section checks for inconsistencies between Phase 1 naming conventions and the Phase 2 additions proposed in this document.

### 9.1 Status String Consistency

| Phase 1 Statuses | Phase 2 Statuses | Pattern | Drift? |
|---|---|---|---|
| `running`, `completed`, `enriched`, `compacted`, `mapped` | `llm_enriched`, `blast_radius_computed`, `velocity_computed` | Lowercase, underscored, past-tense verb or compound noun | No drift — Phase 2 follows pattern with domain prefix |
| `pipeline_failed`, `enrichment_pending` | (retained as-is) | Compound descriptors | N/A |

Phase 2 note: `"llm_enriched"` deviates from the simple-verb pattern of `"enriched"` and `"mapped"` by adding a prefix. This is intentional and necessary to distinguish Phase 1 enrichment from Phase 2 LLM enrichment. The prefix `"llm_"` is consistent across all Phase 2 LLM-related fields.

### 9.2 Repository Naming

| Phase 1 | Phase 2 | Pattern |
|---|---|---|
| `ScanEnrichmentRepository` | `ScanLLMEnrichmentRepository`, `ScanBlastRadiusRepository` | `Scan{Domain}Repository` | Consistent |

### 9.3 Pipeline Stage Naming

| Phase 1 | Phase 2 | Pattern |
|---|---|---|
| `EnrichmentPipeline`, `CompactionPipeline`, `ControlMappingPipeline` | `LLMEnrichmentPipeline`, `BlastRadiusPipeline`, `EPSSVelocityPipeline` | `{Domain}Pipeline` | Consistent |

### 9.4 AQL Method Naming

| Phase 1 | Phase 2 | Pattern |
|---|---|---|
| `aql_enrich_batch(cve_ids)` | `aql_get_epss_history_batch(cve_keys, cutoff_date)` | `aql_{verb}_{noun}` | Minor drift: Phase 2 uses `_get_` while Phase 1 uses bare verb. Accepted — `aql_get_cwe_parent_map` also uses `_get_` in Phase 1. Consistent with that sub-pattern. |
| `aql_get_cwe_parent_map(cwe_ids)` | `aql_blast_radius_for_purl(purl)` | `aql_{description}` | Consistent |

### 9.5 Timestamp Field Naming

| Phase 1 | Phase 2 | Pattern |
|---|---|---|
| `enriched_at` (scan_runs) | `llm_enriched_at` (scan_findings + scan_runs), `blast_radius_computed_at`, `velocity_computed_at` | `{operation}_at` | Consistent — Phase 2 adds domain prefix to disambiguate |

### 9.6 Guard Frozenset Naming

| Phase 1 | Phase 2 | Pattern |
|---|---|---|
| `_ENRICHMENT_DONE`, `_COMPACTION_DONE`, `_MAPPING_DONE` | `_LLM_DONE`, `_BLAST_DONE`, `_VELOCITY_DONE` | `_{STAGE}_DONE` | Consistent — Phase 2 uses abbreviated stage names (`LLM`, `BLAST`, `VELOCITY`) matching the abbreviated style of `_MAPPING_DONE` |

### 9.7 Constructor Parameter Naming

| Phase 1 | Phase 2 | Drift? |
|---|---|---|
| `EnrichmentPipeline(db, repo)` | `LLMEnrichmentPipeline(db, repo, llm_repo, llm_client)` | Extra parameters follow `_repo` naming convention | No drift |
| `ScanEnrichmentRepository(db: StandardDatabase)` | `ScanLLMEnrichmentRepository(db: StandardDatabase)` | Identical pattern | No drift |

### 9.8 Logging Key Naming

| Phase 1 Log Keys | Phase 2 Log Keys | Pattern |
|---|---|---|
| `enrichment_pipeline.start`, `enrichment_pipeline.batch`, `enrichment_pipeline.complete` | `llm_enrichment_pipeline.start`, `llm_enrichment_pipeline.batch_failed`, `llm_enrichment_pipeline.complete` | `{module_snake_case}.{event}` | Consistent |
| `scan_enrichment_repo.aql_enrich_batch_complete` | `scan_llm_enrichment_repo.bulk_write_llm_fields`, `scan_blast_radius_repo.aql_blast_radius_for_purl_failed` | `{repo_snake_case}.{method_name}` | Consistent |

### 9.9 Potential Drift Issues — Decisions Required

| Issue | Risk Level | Resolution |
|---|---|---|
| `EPSSVelocityPipeline` does not own a repository — it uses `ScanEnrichmentRepository` directly | Low — intentional; EPSS velocity writes use same `bulk_update_findings` path as Phase 1 | Documented as intentional in design; no new repo needed |
| `PipelineLLMClient` is in `ingestion/` package not `services/` | Low — intentional architectural decision (see Section 2.1) | Documented |
| `llm_enriched` status uses past-tense adjective while `blast_radius_computed` and `velocity_computed` use past-participle form | Very low — minor semantic variation within Phase 2 itself | Acceptable; all three are unambiguous past-event markers |

---

## 10. Use-Case Coverage Matrix

### 10.1 Requirements → Use Cases → Acceptance Criteria

| REQ-ID | Use Case | AC Range | Stage | Status Transition |
|---|---|---|---|---|
| REQ-004 | UC-010 LLM Enrichment | AC-029 – AC-036 | `LLMEnrichmentPipeline` | `mapped → llm_enriched` |
| REQ-005 | UC-011 Blast Radius Simulation | AC-037 – AC-043 | `BlastRadiusPipeline` | `llm_enriched → blast_radius_computed` |
| REQ-006 | UC-012 EPSS Velocity Detection | AC-044 – AC-050 | `EPSSVelocityPipeline` | `blast_radius_computed → velocity_computed` |
| — | Cross-cutting | AC-051 – AC-054 | `PipelineCoordinator` | All Phase 2 |

### 10.2 Acceptance Criteria → Module Coverage

#### UC-010 LLM Enrichment (AC-029 – AC-036)

| AC-ID | Criterion | Module | Method |
|---|---|---|---|
| AC-029 | `llm_risk_summary` populated | `LLMEnrichmentPipeline` | `_build_llm_updates()` writes field if LLM result present |
| AC-030 | `llm_remediation` populated | `LLMEnrichmentPipeline` | `_build_llm_updates()` writes field if LLM result present |
| AC-031 | `llm_attack_surface ∈ {network, local, adjacent}` | `LLMEnrichmentPipeline` | `_build_llm_updates()` normalizes and validates; defaults to "network" |
| AC-032 | Non-CVE findings receive LLM output | `LLMEnrichmentPipeline` | `_context_for_finding()` uses `rule_id + severity` fallback |
| AC-033 | Status → `llm_enriched` | `ScanLLMEnrichmentRepository` | `update_scan_run_status("llm_enriched")` |
| AC-034 | LLM failure isolation (partial) | `LLMEnrichmentPipeline` | Per-batch try/except; only raises if ALL batches fail |
| AC-035 | Haiku model; token usage logged | `PipelineLLMClient` + `ScanLLMEnrichmentRepository` | `model` constructor param; `write_token_usage()` |
| AC-036 | Idempotent re-run | `ScanLLMEnrichmentRepository` | `bulk_write_llm_fields()` uses AQL UPDATE (upsert semantics) |

#### UC-011 Blast Radius Simulation (AC-037 – AC-043)

| AC-ID | Criterion | Module | Method |
|---|---|---|---|
| AC-037 | `blast_radius_score ∈ [0, 1]` for SCA findings | `BlastRadiusPipeline` | Score formula with `min(1.0, ...)` clamp |
| AC-038 | SAST/IaC findings: score=0, lists=[] | `BlastRadiusPipeline` | `_build_zero_blast_updates()` for no-purl findings |
| AC-039 | `affected_components` correct (INBOUND depth ≤5) | `ScanBlastRadiusRepository` | `aql_blast_radius_for_purl()` with `1..@depth_max` |
| AC-040 | `blast_radius_path` = longest traversal chain | `ScanBlastRadiusRepository` | AQL `SORT row.depth DESC LIMIT 1` to find max-depth path |
| AC-041 | Score formula enforced | `BlastRadiusPipeline` | `len(affected) / max(total, 1)` clamped to [0, 1] |
| AC-042 | Status → `blast_radius_computed` | `ScanBlastRadiusRepository` | `update_scan_run_status("blast_radius_computed")` |
| AC-043 | Idempotent | `ScanBlastRadiusRepository` | `bulk_write_blast_radius()` uses AQL UPDATE |

#### UC-012 EPSS Velocity Detection (AC-044 – AC-050)

| AC-ID | Criterion | Module | Method |
|---|---|---|---|
| AC-044 | `epss_velocity` + `epss_trend` for CVE findings | `EPSSVelocityPipeline` | `_compute_slope()` + `_classify_trend()` + `_build_velocity_updates()` |
| AC-045 | Non-CVE findings: velocity=0.0, trend=stable | `EPSSVelocityPipeline` | `_build_zero_velocity_updates()` |
| AC-046 | Rising threshold: `slope * 7 > 0.05` | `EPSSVelocityPipeline` | `_classify_trend()` |
| AC-047 | Falling threshold: `slope * 7 < -0.05` | `EPSSVelocityPipeline` | `_classify_trend()` |
| AC-048 | Insufficient history → 0.0 / stable | `EPSSVelocityPipeline` | `_compute_slope()` returns 0.0 if `n < 2` |
| AC-049 | Status → `velocity_computed` | `ScanEnrichmentRepository` | `update_scan_run_status("velocity_computed")` |
| AC-050 | Idempotent | `ScanEnrichmentRepository` | `bulk_update_findings()` uses AQL UPDATE |

#### Cross-Cutting (AC-051 – AC-054)

| AC-ID | Criterion | Module | Implementation |
|---|---|---|---|
| AC-051 | Phase 2 runs automatically after Phase 1 | `PipelineCoordinator` | Phase 2 stages wired after Stage 3 in `run_post_ingest_pipeline()`; `"mapped"` added to `_RETRIABLE_STATUSES` |
| AC-052 | Manual re-trigger from Phase 2 intermediate states | `PipelineCoordinator` | `"llm_enriched"`, `"blast_radius_computed"` added to `_RETRIABLE_STATUSES` |
| AC-053 | Phase 2 failure → `pipeline_failed`; partial writes retained | `PipelineCoordinator` | Each Phase 2 stage wrapped in try/except → `_mark_failed()` |
| AC-054 | `tenant_id` scoping in all Phase 2 reads/writes | All new modules | `tenant_id` passed to `fetch_findings_for_run()`; all AQL FILTERs include `tenant_id` where collection has it |

### 10.3 Risk Coverage

| Risk | Mitigation | Module |
|---|---|---|
| Risk-1: `depends_on` empty → blast radius 0 | Documented expected behavior; `aql_blast_radius_for_purl()` returns empty result cleanly | `ScanBlastRadiusRepository` |
| Risk-2: LLM latency for large scan_runs | Batch 10 findings per LLM prompt (not 1); batch failures skip but don't abort | `LLMEnrichmentPipeline`, `PipelineLLMClient` |
| Risk-3: `epss_history` empty → all stable | `aql_get_epss_history_batch()` returns `{}`; `EPSSVelocityPipeline` treats no-history as stable | `EPSSVelocityPipeline` |
| Risk-4: Phase 2 statuses not retriable | `"mapped"`, `"llm_enriched"`, `"blast_radius_computed"` added to `_RETRIABLE_STATUSES` | `PipelineCoordinator` |
| Risk-5: Non-CVE LLM context | `_context_for_finding()` fallback to `rule_id + severity` | `LLMEnrichmentPipeline` |

### 10.4 Test Scenario Index

The following test scenario IDs are referenced in requirements.md Section "Acceptance Criteria Coverage Map." Each maps to one or more ACs above.

| Scenario ID | UC | AC Coverage | Test Type |
|---|---|---|---|
| S-UC010-01 | UC-010 | AC-029, AC-030, AC-031 | Integration — LLM fields written |
| S-UC010-02 | UC-010 | AC-032 | Unit — non-CVE context fallback |
| S-UC010-03 | UC-010 | AC-033 | Integration — status transition |
| S-UC010-04 | UC-010 | AC-034 | Unit — partial batch failure isolation |
| S-UC010-05 | UC-010 | AC-035 | Unit — model name + token tracking |
| S-UC010-06 | UC-010 | AC-036 | Integration — idempotent re-run |
| S-UC010-07 | UC-010 | AC-031 | Unit — invalid attack_surface defaults to "network" |
| S-UC010-08 | UC-010 | AC-034 | Unit — ALL batches fail → pipeline_failed |
| S-UC011-01 | UC-011 | AC-037 | Integration — SCA finding score ∈ [0,1] |
| S-UC011-02 | UC-011 | AC-038 | Unit — SAST finding zero blast radius |
| S-UC011-03 | UC-011 | AC-039 | Integration — affected_components from AQL traversal |
| S-UC011-04 | UC-011 | AC-040 | Integration — blast_radius_path longest path |
| S-UC011-05 | UC-011 | AC-041 | Unit — score formula |
| S-UC011-06 | UC-011 | AC-042 | Integration — status transition |
| S-UC011-07 | UC-011 | AC-043 | Integration — idempotent re-run |
| S-UC012-01 | UC-012 | AC-044 | Integration — velocity fields written |
| S-UC012-02 | UC-012 | AC-045 | Unit — non-CVE zero velocity |
| S-UC012-03 | UC-012 | AC-046 | Unit — rising threshold |
| S-UC012-04 | UC-012 | AC-047 | Unit — falling threshold |
| S-UC012-05 | UC-012 | AC-048 | Unit — insufficient history → stable |
| S-UC012-06 | UC-012 | AC-049 | Integration — status transition |
| S-UC012-07 | UC-012 | AC-050 | Integration — idempotent re-run |
| S-CROSS-01 | Cross | AC-051 | E2E — full Phase 1 + Phase 2 chain |
| S-CROSS-02 | Cross | AC-052 | Integration — manual re-trigger from `llm_enriched` |
| S-CROSS-03 | Cross | AC-053 | Integration — stage failure → `pipeline_failed` |
| S-CROSS-04 | Cross | AC-054 | Integration — tenant_id isolation |

---

*End of proposed design document.*

*Document covers all 6 new files, 3 modified files, full AQL patterns, data model additions, error matrix, naming decisions, naming-drift check, and UC-010/UC-011/UC-012 coverage across AC-029 through AC-054.*
