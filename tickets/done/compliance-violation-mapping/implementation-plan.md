# Implementation Plan — compliance-violation-mapping

**Last Updated:** 2026-03-22
**Design Basis:** `proposed-design.md` v2

## Sequence

1. **DB schema** — add `finding_violates_control` to `db.py`
2. **Repository** — `scan_violation_repository.py` (AQL traversal + upsert)
3. **Pipeline** — `violation_mapping_pipeline.py` (orchestration, zero AQL)
4. **Coordinator update** — wire Stage 7 + update guard sets
5. **Response models** — `src/api/models/responses/compliance.py`
6. **Endpoint** — `src/api/v1/endpoints/compliance.py`
7. **Router** — register `/compliance` prefix in `router.py`
8. **Tests** — unit tests for pipeline (mocked repo) + endpoints (TestClient)

## Traceability

| Requirement | Design section | Use Case | Implementation step |
| --- | --- | --- | --- |
| REQ-CV-001 | Proposed design §2,§5 | UC-CV-001, UC-CV-002, UC-CV-006, UC-CV-007 | Steps 2–3 |
| REQ-CV-002 | Proposed design §2 | UC-CV-003, UC-CV-008 | Steps 3–4 |
| REQ-CV-003 | Proposed design §5 | UC-CV-004 | Steps 5–6 |
| REQ-CV-004 | Proposed design §5 | UC-CV-005 | Steps 5–6 |
