# Implementation Progress

## Summary

| Change | File | Type | State | Tests |
| --- | --- | --- | --- | --- |
| C-01 | `src/complira_graph/ingestion/checkov_control_map.py` | Add | Completed ✅ | N/A (data module) |
| C-02 | `src/complira_graph/ingestion/edge_service.py` | Modify | Completed ✅ | Passed ✅ |
| C-03 | `tests/unit/ingestion/test_edge_service.py` | Modify | Completed ✅ | 11/11 Passed ✅ |

## Unit/Integration Test Results

- `tests/unit/ingestion/` — **467 tests pass**, 0 failures
- New test class `TestDetectedControlEdges`: 11 tests pass (all 8 ACs covered)

## Stage 7 — API/E2E Testing

See `api-e2e-testing.md`.

## Stage 8 — Code Review

See `code-review.md`.

## Stage 9 — Docs Sync

`docs/SCANNER_INGESTION.md` — No impact from this ticket (the edge wiring is internal to the ingestion service; the public adapter/scanner docs do not describe edge implementation internals).

Decision: **No docs impact** — `EvidenceEdgeService` internals are not documented in `docs/`; the schema itself (`complira_kg_schema_v2_2.py`) already documents the edge collection definitions. No new public-facing behavior to document.
