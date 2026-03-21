# API / E2E Testing

## Ticket: multi-tenant-hierarchy
## Stage 7 Status: Pass
## Date: 2026-03-20

---

## Summary

54 ACs total: 52 covered by automated API/contract tests (all Passed), 2 documentation ACs waived (manual, N/A).

Test suites executed:
- `tests/integration/test_project_endpoints.py` — project CRUD, scoping, soft delete
- `tests/integration/test_repository_endpoints.py` — repository CRUD, project linking, filtering
- `tests/contract/test_project_contract.py` — contract-level response schema
- `tests/contract/test_repository_contract.py` — contract-level response schema
- **79 tests, 79 passed, 0 failed**

---

## Acceptance Criteria Matrix

| AC-ID | Description | Status |
| --- | --- | --- |
| AC-001 | Project document validates with all required fields | Passed |
| AC-002 | Project scoped to customer | Passed |
| AC-003 | Project name unique within customer | Passed |
| AC-004 | Soft delete preserves data integrity | Passed |
| AC-005 | Repository document validates | Passed |
| AC-006 | Repository scoped to customer | Passed |
| AC-007 | Repository name unique within customer | Passed |
| AC-008 | Repository can exist without project_id | Passed |
| AC-009 | Repository soft delete preserves data | Passed |
| AC-010 | Scan submission accepts optional project_id/repository_id | Passed |
| AC-011 | Existing scans without project/repo IDs still work | Passed |
| AC-012 | Invalid project/repo IDs rejected with clear error | Passed |
| AC-013 | Scan linked to customer's project/repo only | Passed |
| AC-014 | Create project returns project_id | Passed |
| AC-015 | List projects returns all active for customer | Passed |
| AC-016 | Get project details includes repo_count and last_scan_at | Passed |
| AC-017 | Update project allows name/description/tags change | Passed |
| AC-018 | Delete project soft deletes, prevents if repos exist | Passed |
| AC-019 | All project endpoints require auth | Passed |
| AC-020 | Project endpoints return proper error codes | Passed |
| AC-021 | Create repository returns repository_id | Passed |
| AC-022 | List repositories supports project_id filter | Passed |
| AC-023 | Get repository details includes scan_count/last_scan_at | Passed |
| AC-024 | Update repository allows changing project_id | Passed |
| AC-025 | Delete repository soft deletes, prevents if scans exist | Passed |
| AC-026 | Repository endpoints require auth | Passed |
| AC-027 | Repository endpoints return proper error codes | Passed |
| AC-028 | Filter by project_id returns only scans in project | Passed |
| AC-029 | Filter by repository_id returns only scans in repo | Passed |
| AC-030 | Filter by both returns scans matching both | Passed |
| AC-031 | Invalid IDs return empty list (not error) | Passed |
| AC-032 | Filtering respects customer scoping | Passed |
| AC-033 | Project summary includes all repositories | Passed |
| AC-034 | Findings aggregated from latest scan per repo | Passed |
| AC-035 | Top vulns sorted by severity and repo count | Passed |
| AC-036 | Empty project returns valid response with zero counts | Passed |
| AC-037 | Summary respects customer scoping | Passed |
| AC-038–AC-049 | Scan association, customer isolation, error handling | Passed |
| AC-050 | Docs include hierarchy examples | Waived — manual/documentation AC, N/A for automated testing |
| AC-051 | Docs include use case examples | Waived — manual/documentation AC, N/A for automated testing |
| AC-052 | Test script completes successfully | Passed |
| AC-053 | Test script validates aggregation endpoints | Passed |
| AC-054 | Test script demonstrates filtering | Passed |

---

## Stage 7 Gate Decision: Pass

52/52 automated ACs Passed. AC-050/AC-051 Waived (documentation ACs, manual scope, N/A for CI).
