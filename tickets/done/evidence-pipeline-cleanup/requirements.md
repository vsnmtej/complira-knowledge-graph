# Requirements

## Status: Design-ready

## Goal / Problem Statement

Three bugs/debt items remain from the evidence ingestion pipeline work:

1. **F-001**: `service.py:349` — `raw.get("licenses", [{}])[0]` raises `IndexError` when `licenses` is an empty list `[]`. The `[{}]` default only guards `None`, not an empty list.
2. **T-DEL-002**: `src/api/repositories/scan.py` cannot be deleted because `api/services/enrichment.py`, `api/services/compaction.py`, and `api/services/control_mapping.py` still import `ScanFindingRepository` from it — but all three service files are unreachable dead code (no v1 endpoint or factory calls them).
3. **T-DEL-003**: `src/api/repositories/component.py` has zero importers and is unused dead code (`ComponentRepository` is not called by anything).

Goal: fix F-001 + delete dead-code service/repository files (T-DEL-002/003) with zero regressions.

## In-Scope Use Cases

- UC-001: Ingestion of an SBOM with one or more components where a component's `licenses` field is an empty list — must not raise `IndexError`.
- UC-002: Ingestion of an SBOM component with `licenses: null` (None) — must not raise `IndexError`.
- UC-003: Ingestion of an SBOM component with `licenses: [{"license": {"id": "MIT"}}]` — must correctly extract license id.
- UC-004: Delete dead-code files (`enrichment.py`, `compaction.py`, `control_mapping.py` in `api/services/`; `get_enrichment_service`, `get_compaction_service` in `dependencies.py`).
- UC-005: Delete `src/api/repositories/scan.py` after dead-code blockers are removed.
- UC-006: Delete `src/api/repositories/component.py` (has zero importers, is unused).

## Acceptance Criteria

| ID | Criterion |
| --- | --- |
| AC-001 | Ingesting an SBOM payload where a component has `licenses: []` completes without `IndexError`; `license_id` field is `None`. |
| AC-002 | Ingesting a component with `licenses: null` completes without `IndexError`; `license_id` is `None`. |
| AC-003 | Ingesting a component with `licenses: [{"license": {"id": "MIT"}}]` yields `license_id = "MIT"`. |
| AC-004 | `src/api/services/enrichment.py` is deleted; no import errors in remaining codebase. |
| AC-005 | `src/api/services/compaction.py` is deleted; no import errors in remaining codebase. |
| AC-006 | `src/api/services/control_mapping.py` is deleted; no import errors in remaining codebase. |
| AC-007 | `get_enrichment_service` and `get_compaction_service` removed from `src/api/core/dependencies.py`; no import errors. |
| AC-008 | `src/api/repositories/scan.py` is deleted; no import errors in remaining codebase. |
| AC-009 | `src/api/repositories/component.py` is deleted; no import errors in remaining codebase. |
| AC-010 | Full test suite passes (883+ tests, 0 failures) after all changes. |
| AC-011 | Three new unit tests cover: `licenses=[]` → `license=None`, `licenses=None` → `license=None`, `licenses=[{"license":{"id":"MIT"}}]` → `license="MIT"`. All pass. |

## Constraints / Dependencies

- No behavior preserved from deleted files — clean deletion only.
- `api/services/enrichment_service.py` (the active v1 enrichment service) must NOT be touched.
- Scope is limited to the dead-code layer and the one-line F-001 guard; no other changes.

## Assumptions

- `api/services/enrichment.py`, `api/services/compaction.py`, `api/services/control_mapping.py` are confirmed dead code (no v1 endpoint reaches them, their factory functions `get_enrichment_service`/`get_compaction_service` in `dependencies.py` are never called by any endpoint).
- `api/repositories/component.py` `ComponentRepository` has zero importers (confirmed by grep).
- The skipped FDA SBOM test is skipped solely due to F-001.

## Open Questions / Risks — Resolved

- Skipped FDA SBOM e2e test is infrastructure-dependent (live ArangoDB), not F-001. Remains skipped — out of scope.
- Confirmed no test file imports `ScanFindingRepository`, `ScanSessionRepository`, `ScanEdgeRepository`, `ComponentRepository`, `CompactionService`, or `ControlMappingService`. Deletions are safe.

## Requirement Coverage Map (to use cases)

| Requirement | Use Cases |
| --- | --- |
| F-001 fix (AC-001, AC-002, AC-003, AC-011) | UC-001, UC-002, UC-003 |
| T-DEL-002/003 deletions (AC-004–AC-009) | UC-004, UC-005, UC-006 |
| No regressions (AC-010) | UC-001–UC-006 |

## Acceptance Criteria Coverage Map (to Stage 7 scenarios)

| AC-ID | Stage 7 Scenario |
| --- | --- |
| AC-001 | S-001: `_build_component_docs` with `licenses=[]` → no error, `license` field absent |
| AC-002 | S-002: `_build_component_docs` with `licenses=None` → no error, `license` field absent |
| AC-003 | S-003: `_build_component_docs` with `licenses=[{"license":{"id":"MIT"}}]` → `license="MIT"` |
| AC-004–AC-009 | S-004: full test suite runs without import errors on deleted files |
| AC-010 | S-005: `pytest` suite passes 883+ tests, 0 failures |
| AC-011 | Covered by S-001, S-002, S-003 (unit tests) |

## Triage

- Scope: `Small` — 1-line fix, straight deletions, no new logic or design changes.
- Files touched: ~7 deletions + 1 edit (`service.py`) + 1 edit (`dependencies.py`) + 1 test unskip.
