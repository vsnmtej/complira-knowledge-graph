# API / E2E Testing

## Ticket: evidence-pipeline-cleanup
## Stage 7 Status: Pass

---

## Acceptance Criteria Matrix

| AC-ID | Scenario ID | Status |
| --- | --- | --- |
| AC-001 | S-001 | Passed |
| AC-002 | S-002 | Passed |
| AC-003 | S-003 | Passed |
| AC-004 | S-004 | Passed |
| AC-005 | S-004 | Passed |
| AC-006 | S-004 | Passed |
| AC-007 | S-004 | Passed |
| AC-008 | S-004 | Passed |
| AC-009 | S-004 | Passed |
| AC-010 | S-005 | Passed |
| AC-011 | S-001, S-002, S-003 | Passed |

---

## Scenarios

### S-001: `licenses=[]` — no IndexError, license absent

| Field | Value |
| --- | --- |
| Scenario ID | S-001 |
| AC IDs | AC-001, AC-011 |
| Requirement IDs | F-001 |
| Use Case ID | UC-001 |
| Source Type | Requirement |
| Test Level | Unit |
| Expected Outcome | No exception; `license` key absent in output doc |
| Test | `TestBuildComponentDocs::test_empty_licenses_list_does_not_raise` |
| Result | **Passed** |

### S-002: `licenses=None` — no IndexError, license absent

| Field | Value |
| --- | --- |
| Scenario ID | S-002 |
| AC IDs | AC-002, AC-011 |
| Requirement IDs | F-001 |
| Use Case ID | UC-002 |
| Source Type | Requirement |
| Test Level | Unit |
| Expected Outcome | No exception; `license` key absent |
| Test | `TestBuildComponentDocs::test_none_licenses_does_not_raise` |
| Result | **Passed** |

### S-003: `licenses=[{"license":{"id":"MIT"}}]` — correct extraction

| Field | Value |
| --- | --- |
| Scenario ID | S-003 |
| AC IDs | AC-003, AC-011 |
| Requirement IDs | F-001 |
| Use Case ID | UC-003 |
| Source Type | Requirement |
| Test Level | Unit |
| Expected Outcome | `license == "MIT"` |
| Test | `TestBuildComponentDocs::test_licenses_list_extracts_id` |
| Result | **Passed** |

### S-004: Full suite imports cleanly after dead-code deletion

| Field | Value |
| --- | --- |
| Scenario ID | S-004 |
| AC IDs | AC-004–AC-009 |
| Requirement IDs | T-DEL-002, T-DEL-003 |
| Use Case IDs | UC-004, UC-005, UC-006 |
| Source Type | Requirement |
| Test Level | Unit + Integration |
| Expected Outcome | No import errors; pytest collection succeeds |
| Command | `.venv/bin/pytest tests/ --ignore=tests/integration/ingestion -q` |
| Result | **Passed** — 886 passed, 1 skipped, 0 failures |

### S-005: Full test suite — no regressions

| Field | Value |
| --- | --- |
| Scenario ID | S-005 |
| AC IDs | AC-010 |
| Use Case IDs | UC-001–UC-006 |
| Source Type | Requirement |
| Test Level | Unit + Integration |
| Expected Outcome | ≥886 passed, 0 new failures |
| Command | `.venv/bin/pytest tests/ --ignore=tests/integration/ingestion -q` |
| Result | **Passed** — 886 passed (was 883; +3 new tests) |

---

## Stage 7 Gate Decision: Pass

All 11 acceptance criteria Passed. No waivers needed.
