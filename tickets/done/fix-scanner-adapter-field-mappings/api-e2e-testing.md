# API/E2E Testing: Fix Scanner Adapter Field Mappings

- Stage: 7
- Date: 2026-03-19

## Acceptance Criteria Matrix

| AC ID | Mapped Scenario | Status |
| --- | --- | --- |
| AC-001 | S-001 (Semgrep native pipeline) | Passed |
| AC-002 | S-001 | Passed |
| AC-003 | S-001 | Passed |
| AC-004 | S-001 | Passed |
| AC-005 | S-001 | Passed |
| AC-006 | S-001 | Passed |
| AC-007 | S-001 | Passed |
| AC-008 | S-001 | Passed |
| AC-009 | S-001 | Passed |
| AC-010 | S-002 (Checkov native pipeline) | Passed |
| AC-011 | S-002 | Passed |
| AC-012 | S-002 | Passed |
| AC-013 | S-002 | Passed |
| AC-014 | S-002 | Passed |
| AC-015 | S-003 (test payload accuracy) | Passed |
| AC-016 | S-003 | Passed |
| AC-017 | S-004 (regression: all tests pass) | Passed |

**All 17/17 ACs Passed.**

## Scenarios

### S-001: Semgrep native pipeline

- **Source**: Requirement (AC-001–AC-009)
- **Level**: Unit (IngestionEngine.process with native Semgrep payload)
- **Scenarios exercised**: `TestSemgrepPipeline` (12 tests)
- **Payload**: native `semgrep --json` format with `check_id`, `path`, `start.line`, `extra.severity`, `extra.message`, `extra.metadata.cwe`
- **Result**: Passed — 1 bundle produced, collection=scan_findings, severity=high, cwe_ids=["CWE-89"], rule_id mapped from check_id, file_path from path, line_start from start.line; fingerprint deterministic; no staging fields leaked; req edge planned with source=rule_engine

### S-002: Checkov native pipeline (no `results` wrapper)

- **Source**: Requirement (AC-010–AC-014)
- **Level**: Unit (IngestionEngine.process with real Checkov JSON)
- **Scenarios exercised**: `TestCheckovPipeline` (11 tests)
- **Payload**: top-level `failed_checks`, `passed_checks`, `skipped_checks` (no `results` wrapper)
- **Result**: Passed — 3 bundles produced; FAILED→scan_findings, PASSED→detected_controls, SKIPPED→audit_log; @check_type injection works; DR-003 bc_check_id override works

### S-003: Test payload accuracy (no adapter override needed)

- **Source**: Requirement (AC-015–AC-016)
- **Level**: Unit
- **Test**: `TestSemgrepPipeline` no longer uses `setup_method` adapter override; `TestCheckovPipeline` uses payload without `results` wrapper
- **Result**: Passed — payload changes confirmed by running tests directly against `"semgrep"` and `"checkov"` adapter entries

### S-004: Regression — all existing tests pass

- **Source**: Requirement (AC-017)
- **Command**: `uv run pytest tests/ --ignore=tests/integration/ingestion -q`
- **Result**: 883 passed, 1 skipped, 0 failed

## Infeasible Scenarios

None — all ACs are exercised by unit tests and the existing full test suite.

## Gate Decision

**Pass** — 17/17 ACs Passed. Advancing to Stage 8 (Code Review).
