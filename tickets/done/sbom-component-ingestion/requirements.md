# Requirements: SBOM Component Ingestion

**Status:** Design-ready
**Ticket:** `sbom-component-ingestion`
**Branch:** `codex/sbom-component-ingestion`
**Date:** 2026-03-22
**Scope:** Small

---

## Goal / Problem Statement

The Phase 2 blast radius pipeline (UC-011) already queries `depends_on` and `project_uses_component` edges in ArangoDB to compute propagation impact scores, but always returns 0.0 because these collections are empty — no `depends_on` edge ingestion has been implemented. This ticket implements CycloneDX `dependencies[]` parsing and `depends_on` edge writes, and extends component documents with `supplier`, `licenses`, and `hashes` fields, giving blast radius real data to traverse.

---

## Architecture Alignment Note

**Components are global entities** (purl-keyed, no `tenant_id` on the document). `tenant_id` is carried on the edges (`project_uses_component`, `depends_on`), not on the component document. This is intentional per the v2.2 schema design. Requirements in this document reflect this architecture.

---

## In-Scope Use Cases

| use_case_id | Description |
| --- | --- |
| UC-SBOM-001 | `POST /v1/scan/ingest` with `format=cyclonedx` parses components and upserts them to `components` collection with `supplier`, `licenses`, `hashes` fields |
| UC-SBOM-002 | CycloneDX `dependencies[]` are parsed and written as `depends_on` edges |
| UC-SBOM-003 | `project_uses_component` edges are created for each component when `project_id` is set (already implemented — verify no regression) |
| UC-SBOM-004 | PURL normalization to valid ArangoDB `_key` using `normalize_purl()` |
| UC-SBOM-005 | Re-ingesting the same SBOM is idempotent (upsert, no duplicates) |
| UC-SBOM-006 | Components without a PURL get a derived key from `pkg:generic/{name}@{version}` |

---

## Requirements

### REQ-SBOM-001 — Component Document Field Extension

Extend `V22Component` model and `_build_component_docs()` to capture additional fields from CycloneDX: `supplier` (from `supplier.name`), `licenses` (full list of license expressions), `hashes` (list of `{alg, content}` dicts). These fields are optional and stored on the global component document.

**Existing fields preserved:** `_key` (normalize_purl), `purl`, `name`, `version`, `type`, `purl_source`, `sbom_format`, `cpe`, `license`.

### REQ-SBOM-002 — Dependency Edge Ingestion

Extract CycloneDX `dependencies[]` array at the API endpoint layer and pass it to `ingest_sbom()`. The service calls `EvidenceEdgeService.create_depends_on_edges()` to upsert `depends_on` edges from `components/{from_key}` to `components/{to_key}` with `tenant_id` and `scan_run_id`.

**CycloneDX dependencies format:**
```json
[{"ref": "<purl_from>", "dependsOn": ["<purl_to_1>", "<purl_to_2>"]}]
```

### REQ-SBOM-003 — `project_uses_component` Edge Idempotency (No Regression)

Existing `project_uses_component` edge wiring must continue to function correctly. No changes required — verify by test coverage.

### REQ-SBOM-004 — PURL Key Normalization

Use existing `normalize_purl()` utility from `complira_graph/utils/keys.py`. Normalizes any PURL to a valid ArangoDB `_key` by replacing all non-alphanumeric characters with `_`. For long PURLs (>254 chars) a hash-based key is used. This utility is already tested.

### REQ-SBOM-005 — Idempotency

Re-ingesting the same SBOM must upsert (not duplicate) components and edges. `EvidenceComponentRepository` already uses `import_bulk(on_duplicate="update")`. `create_depends_on_edges()` must use the same pattern with deterministic `_key` from `generate_edge_key()`.

### REQ-SBOM-006 — `ingest_sbom()` Returns `components_count`

`ingest_sbom()` already returns `components_count = len(component_docs)`. Must continue to return the count of components processed (not edges). Verify no regression.

---

## Acceptance Criteria

| AC ID | Requirement | Criterion |
| --- | --- | --- |
| AC-SBOM-001 | REQ-SBOM-001 | A CycloneDX SBOM with 3 components produces 3 `components` documents in the upsert batch |
| AC-SBOM-002 | REQ-SBOM-001 | Each component doc has correct `purl`, `name`, `version`, `type` fields |
| AC-SBOM-003 | REQ-SBOM-001 | Component with `supplier.name` populates `supplier` field on the document |
| AC-SBOM-004 | REQ-SBOM-001 | Component with `licenses` list populates `licenses` field as list of strings |
| AC-SBOM-005 | REQ-SBOM-001 | Component with `hashes` list populates `hashes` field as list of `{alg, content}` dicts |
| AC-SBOM-006 | REQ-SBOM-002 | A SBOM with 2 dependency entries produces 2 `depends_on` edges via `create_depends_on_edges()` |
| AC-SBOM-007 | REQ-SBOM-002 | Each `depends_on` edge has `_from=components/{from_key}`, `_to=components/{to_key}`, `tenant_id`, `scan_run_id` |
| AC-SBOM-008 | REQ-SBOM-002 | `dependencies_raw` with empty `dependsOn` list for a ref produces no edges for that ref |
| AC-SBOM-009 | REQ-SBOM-003 | Components with `project_id` produce `project_uses_component` edges (existing behavior preserved) |
| AC-SBOM-010 | REQ-SBOM-003 | Components without `project_id` produce no `project_uses_component` edges |
| AC-SBOM-011 | REQ-SBOM-004 | `pkg:npm/lodash@4.17.21` normalizes to `pkg_npm_lodash_4_17_21` as component `_key` |
| AC-SBOM-012 | REQ-SBOM-004 | Component without PURL derives key using `pkg:generic/{name}@{version}` fallback pattern |
| AC-SBOM-013 | REQ-SBOM-005 | Re-ingesting identical SBOM does not duplicate components or edges (upsert semantics verified) |
| AC-SBOM-014 | REQ-SBOM-006 | `ingest_sbom()` returns `components_count = 3` for a 3-component SBOM |

---

## Requirement → Use Case Coverage Map

| Requirement | Use Cases |
| --- | --- |
| REQ-SBOM-001 | UC-SBOM-001, UC-SBOM-004, UC-SBOM-006 |
| REQ-SBOM-002 | UC-SBOM-002, UC-SBOM-004 |
| REQ-SBOM-003 | UC-SBOM-003 |
| REQ-SBOM-004 | UC-SBOM-004 |
| REQ-SBOM-005 | UC-SBOM-005 |
| REQ-SBOM-006 | UC-SBOM-001, UC-SBOM-002 |

---

## Acceptance Criteria → Stage 7 Scenario Map

| AC ID | Stage 7 Scenario (planned) |
| --- | --- |
| AC-SBOM-001 | `test_three_components_produces_three_docs` |
| AC-SBOM-002 | `test_component_fields_purl_name_version_type` |
| AC-SBOM-003 | `test_supplier_extracted_from_supplier_name` |
| AC-SBOM-004 | `test_licenses_extracted_as_list` |
| AC-SBOM-005 | `test_hashes_extracted_as_list` |
| AC-SBOM-006 | `test_two_dependencies_produce_two_edges` |
| AC-SBOM-007 | `test_depends_on_edge_fields` |
| AC-SBOM-008 | `test_empty_depends_on_list_produces_no_edges` |
| AC-SBOM-009 | `test_project_uses_component_edges_with_project_id` |
| AC-SBOM-010 | `test_no_project_uses_component_without_project_id` |
| AC-SBOM-011 | `test_purl_normalization_npm_lodash` |
| AC-SBOM-012 | `test_fallback_purl_from_name_version` |
| AC-SBOM-013 | `test_idempotent_reingest` |
| AC-SBOM-014 | `test_components_count_returned` |

---

## Constraints / Dependencies

- CycloneDX 1.4/1.5 format only (JSON)
- `depends_on` and `project_uses_component` collections already exist in DB schema v2.2 — no creation needed
- Must not break existing scan_run ingestion or Phase 1/2 pipeline
- `normalize_purl()` and `generate_edge_key()` used as-is (no changes)
- `V22Component` is a global model — `tenant_id` is **not** added to the document; it lives on edges
- `EvidenceIngestionService.ingest_sbom()` extended, not replaced

---

## Assumptions

- CycloneDX `components[]` is the only supported format for now
- `dependencies[]` array may be absent — treat as empty list
- `supplier` may be absent — store as `None`
- `licenses` may be empty list or absent
- `hashes` may be empty list or absent
- `dependsOn` refs that do not match any component in the batch are tolerated (dangling edges OK per schema)

---

## Open Questions / Risks

| # | Question | Status |
| --- | --- | --- |
| OQ-1 | What does `ingest_sbom()` currently write? | Resolved — creates scan_run, upserts components, creates `project_uses_component` edges. Missing: `depends_on` edges. |
| OQ-2 | Do `depends_on` and `project_uses_component` edge collections exist? | Resolved — both exist in schema v2.2. |
| OQ-3 | Does CycloneDX parser extract `dependencies[]`? | Resolved — No. Extraction happens inline at the endpoint (one line, matching existing `components_raw` pattern). |
| OQ-4 | Is there a `SBOMComponentRepository` pattern? | Resolved — No. `EvidenceComponentRepository` handles bulk upsert. |
