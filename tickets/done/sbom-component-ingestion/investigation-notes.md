# Investigation Notes: SBOM Component Ingestion

**Ticket:** `sbom-component-ingestion`
**Stage:** 1 — Investigation + Triage
**Date:** 2026-03-22
**Status:** Complete

---

## Sources Consulted

| File | Purpose |
| --- | --- |
| `src/api/v1/endpoints/scan.py` | SBOM routing path — how CycloneDX payload is dispatched |
| `src/complira_graph/ingestion/service.py` | `ingest_sbom()` + `_build_component_docs()` — current implementation |
| `src/api/parsers/cyclonedx.py` | `_extract_components()` — current CycloneDX parser |
| `src/complira_graph/ingestion/blast_radius_pipeline.py` | UC-011 blast radius — what it queries and why it returns 0.0 |
| `src/complira_graph/ingestion/repositories.py` | `EvidenceComponentRepository.upsert_batch()` — uses `import_bulk(on_duplicate="update")` |
| `src/complira_graph/ingestion/edge_service.py` | `EvidenceEdgeService` — all edge methods; `create_project_uses_component_edges()` fully implemented |
| `src/complira_graph/models/evidence.py` | `V22Component` model — current field set |
| `src/complira_graph/utils/keys.py` | `normalize_purl()` + `generate_edge_key()` — existing utilities |
| `src/complira_graph/schema/complira_kg_schema_v2_2.py` | DB schema — `depends_on` and `project_uses_component` edge collection definitions |

---

## Key Findings

### FINDING-1: Primary Gap — `dependencies[]` Discarded at Endpoint Layer

**Location:** `src/api/v1/endpoints/scan.py` lines 114–123

```python
if request.format == "cyclonedx" or request.scan_type == "sbom":
    components_raw = request.payload.get("components", [])   # extracts components
    result = await svc.ingest_sbom(
        tenant_id=customer.id,
        components_raw=components_raw,   # passes only components
        sbom_format="cyclonedx",
        ...
    )
```

The `dependencies[]` array in the CycloneDX payload is **never extracted** and **never passed to `ingest_sbom()`**. This is why blast radius returns 0.0 — no `depends_on` edges are ever written.

**Fix:** Extract `dependencies_raw = request.payload.get("dependencies", [])` at the endpoint and pass it as a new parameter to `ingest_sbom()`.

---

### FINDING-2: `ingest_sbom()` Already Has Component + `project_uses_component` Edge Wiring

**Location:** `src/complira_graph/ingestion/service.py` lines 243–308

- `ingest_sbom()` already calls `_build_component_docs()` → `component_repo.upsert_batch()` → `edge_svc.create_project_uses_component_edges()`
- Only missing: `depends_on` edge ingestion
- Signature: `ingest_sbom(tenant_id, components_raw, sbom_format, project_id, repository_id, scan_run_key)`
- Adding `dependencies_raw: list[dict] = []` as a new parameter is the targeted change

---

### FINDING-3: `V22Component` Is a Global Model (No `tenant_id`)

**Location:** `src/complira_graph/models/evidence.py` lines 155–181

`V22Component` is intentionally global — no `tenant_id`, `project_id`, `repository_id`, or `scan_run_id` on the document. The model comment is explicit: "Components are global (purl-keyed, no tenant_id on document); the `project_uses_component` edge carries tenant_id."

**Implication for requirements.md:** The requirements.md draft lists `tenant_id`, `project_id`, `repository_id`, `scan_run_id`, `ingested_at` as component document fields. These must be **corrected** to reflect the actual architecture. The non-tenant metadata fields (`supplier`, `licenses` full list, `hashes`) are the correct targets for V22Component extension.

---

### FINDING-4: `_build_component_docs()` Does Not Extract `supplier`, Full `licenses`, or `hashes`

**Location:** `src/complira_graph/ingestion/service.py` lines 310–354

Current `V22Component` fields populated from raw:
- `_key` (normalize_purl), `purl`, `name`, `version`, `type`, `purl_source`, `sbom_format`, `cpe`
- `license`: only first license expression (fragile access pattern)

**Missing from V22Component model and `_build_component_docs()`:**
- `supplier`: `raw.get("supplier", {}).get("name")`
- `licenses`: full list of license expressions (not just first)
- `hashes`: list of `{alg, content}` dicts

These require: (a) extending `V22Component` with 3 new optional fields, (b) updating `_build_component_docs()` extraction logic.

---

### FINDING-5: `depends_on` Edge Collection Exists in Schema

**Location:** `src/complira_graph/schema/complira_kg_schema_v2_2.py` lines 959–987

```
depends_on: components → components (component dependency graph)
```

Schema requires: `_from`, `_to`, `tenant_id`, `scan_run_id`. Collection already activated in DB schema v2.2. No collection creation needed — it exists.

---

### FINDING-6: `EvidenceEdgeService` Has No `create_depends_on_edges()` Method

**Location:** `src/complira_graph/ingestion/edge_service.py`

All other edge collection methods follow the same pattern: build list of edge dicts, call `self._db.collection("...").import_bulk(edges, on_duplicate="update")`. Adding `create_depends_on_edges(dependencies_raw, scan_run_key, tenant_id)` follows this exact pattern.

CycloneDX `dependencies[]` structure:
```json
[
  {"ref": "pkg:npm/lodash@4.17.21", "dependsOn": ["pkg:npm/lodash-clone@4.0.0"]},
  ...
]
```
Each `ref` is the PURL of the dependent component. Each `dependsOn[]` entry is a PURL of a dependency. PURL-to-key normalization is already handled by `normalize_purl()`.

---

### FINDING-7: `project_uses_component` Edge Collection Fully Wired

`EvidenceEdgeService.create_project_uses_component_edges()` is fully implemented and called by `ingest_sbom()`. This part requires **no changes**.

---

### FINDING-8: `EvidenceComponentRepository` Uses `import_bulk(on_duplicate="update")`

Idempotency is already built in — re-ingesting the same PURL key will update the existing component document. No AQL UPSERT needed.

---

### FINDING-9: `scan_run_id` Not on Component — Edge Schema Has It

The `depends_on` edge schema requires `scan_run_id`. This is available as `scan_run_key` in `ingest_sbom()` — pass it through to the new `create_depends_on_edges()` call.

---

## Open Questions — Resolved

| OQ | Question | Resolution |
| --- | --- | --- |
| OQ-1 | What does `ingest_sbom()` currently write? | Creates scan_run, upserts component docs, creates `project_uses_component` edges. Missing: `depends_on` edges. |
| OQ-2 | Do `depends_on` and `project_uses_component` collections exist in DB schema? | Yes — both defined in schema v2.2, already activated. |
| OQ-3 | Does CycloneDX parser extract `dependencies[]`? | No — `_extract_components()` only extracts `components[]`. `dependencies[]` must be extracted at endpoint. |
| OQ-4 | Is there a `SBOMComponentRepository` pattern? | No — `EvidenceComponentRepository` handles bulk upsert directly. Service orchestrates. |

---

## Scope Triage

**Classification: Small**

Signals:
- 4 files touched: `scan.py` (endpoint), `service.py` (add param + call), `edge_service.py` (add method), `evidence.py` (model extension)
- No new collections needed (schema already has `depends_on`, `project_uses_component`)
- No new repositories needed
- No architectural changes — extends existing pattern
- All utilities (`normalize_purl`, `generate_edge_key`, `import_bulk`) already exist

**Change inventory (preview):**

| File | Change Type | Summary |
| --- | --- | --- |
| `src/api/v1/endpoints/scan.py` | Modify | Extract `dependencies_raw` from payload; pass to `ingest_sbom()` |
| `src/complira_graph/ingestion/service.py` | Modify | Add `dependencies_raw` param to `ingest_sbom()`; call `create_depends_on_edges()` |
| `src/complira_graph/ingestion/edge_service.py` | Modify | Add `create_depends_on_edges()` method |
| `src/complira_graph/models/evidence.py` | Modify | Extend `V22Component` with `supplier`, `licenses`, `hashes` |

---

## Implications for Requirements/Design

1. **Requirements correction needed**: Remove `tenant_id`, `project_id`, `repository_id`, `scan_run_id`, `ingested_at` from component document field list — these don't exist on V22Component (global model by architecture). Replace with `supplier`, `licenses` (full list), `hashes`.

2. **AC-SBOM-002 correction**: "Each component doc has correct `purl`, `name`, `version`, `type`, `tenant_id`" → remove `tenant_id` (not on component doc); add `supplier`.

3. **No parser layer change needed**: `dependencies[]` extraction can happen inline at the endpoint (one line), matching the existing `components_raw` pattern. No need to extend `cyclonedx.py`.

4. **`scan_run_id` on edges, not documents**: `depends_on` schema requires `scan_run_id` on the edge. This is passed through from `ingest_sbom()` to `create_depends_on_edges()`.
