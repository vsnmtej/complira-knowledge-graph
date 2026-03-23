# Requirements

**Status:** Draft

## Goal / Problem Statement

`EvidenceEdgeService.create_detected_control_edges()` is a full stub that returns immediately, so Checkov PASSED checks persisted in `detected_controls` have no outbound graph edges. This means:

1. No `detected_control_maps_to` edges exist → NIST 800-53 controls that were _positively_ detected by Checkov scans are invisible in the compliance graph.
2. No `control_in_component` edges exist → when a purl context is available, no component-scoping edge is created.

## In-Scope Use Cases

- UC-1: Create `detected_control_maps_to` edge for each Checkov PASSED check with a known NIST 800-53 control mapping
- UC-2: Gracefully skip detected controls with no mapping (no error, debug log)
- UC-3: Create `control_in_component` edge when detected_control doc has a `purl` field
- UC-DR1 (Design-Risk): Batch multiple detected_controls without N+1 AQL calls
- UC-DR2 (Design-Risk): Edge schema `additionalProperties: False` — edge doc must not include fields outside schema

## Acceptance Criteria

| ID | Criterion |
| --- | --- |
| AC-001 | `create_detected_control_edges()` calls `import_bulk` on `detected_control_maps_to` for each doc whose `check_id` is in the static mapping |
| AC-002 | Edge has `_from: detected_controls/<fp>`, `_to: oscal_controls/<control_key>`, `source: "rule_engine"`, `confidence: 1.0`, `target_collection: "oscal_controls"` |
| AC-003 | Docs with unknown `check_id` (not in static map) are skipped without error |
| AC-004 | Empty `detected_controls` list → no DB calls, no error |
| AC-005 | `control_in_component` edge is created when `purl` field is present on the detected_control doc |
| AC-006 | Edge keys are deterministic (same inputs → same `_key`) |
| AC-007 | `import_bulk(on_duplicate="update")` is used for idempotent upsert |
| AC-008 | No fields outside the schema are included in either edge type |

## Constraints / Dependencies

- `detected_control_maps_to` schema: `required: [_from, _to, source, confidence]`; `additionalProperties: False` — only `source`, `confidence`, `embedding_model`, `target_collection` are user fields
- `control_in_component` schema: `required: [_from, _to, source]`; `additionalProperties: False` — only `source`, `file_path` are user fields
- `oscal_controls` key format: `control_id.lower().replace('.', '_').replace('(', '').replace(')', '')` (e.g., `AC-2` → `ac-2`, `AC-2.1` → `ac-2_1`)
- Static Checkov→NIST mapping bundled as Python module (no external API required)
- No `tenant_id`/`scan_run_id` on edge docs (schema prohibits them via `additionalProperties: False`)

## Assumptions

- Checkov PASSED check docs in `detected_controls` always have `_key` (= fingerprint), `check_id`
- `control_in_component` edges for Checkov IaC output are a no-op in practice (no purl field on IaC findings) — wiring must exist for future scanners that emit purl
- Dangling `_to` references to `oscal_controls/<key>` are tolerated by ArangoDB (consistent with pattern used by other edge methods)

## Open Questions / Risks

- None outstanding; investigation resolved all open questions.

## Scope Triage

- **Scope: Small** — 3 files (1 new: `checkov_control_map.py`, 1 modify: `edge_service.py`, 1 modify: `test_edge_service.py`), single layer (ingestion edge service), no new public API, no schema changes

## Requirement Coverage Map

| Requirement | Use Case |
| --- | --- |
| AC-001, AC-002 | UC-1 |
| AC-003 | UC-2 |
| AC-004 | UC-2 |
| AC-005, AC-008 | UC-3 |
| AC-006, AC-007 | UC-DR1 |
| AC-008 | UC-DR2 |
