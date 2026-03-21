# Code Review: Fix Scanner Adapter Field Mappings

## Review Metadata

- Stage: `8`
- Code Edit Permission: `Locked`
- Reviewer: Claude Sonnet 4.6 (automated)
- Review Date: 2026-03-19
- Gate Decision: **Pass**

---

## File Size Inventory

| File | Change Type | Effective Non-Empty Lines | Delta Assessment |
| --- | --- | --- | --- |
| `src/complira_graph/ingestion/adapter_registry.py` | Modify + Add | 460 | < 500. New `semgrep_custom` entry (~50 lines) + semgrep field_map update (~15 lines changed). |
| `tests/unit/ingestion/test_ingestion_engine.py` | Modify | 464 | < 500. SEMGREP_PAYLOAD updated, CHECKOV_PAYLOAD updated, TestSemgrepPipeline refactored. |
| `tests/unit/ingestion/test_adapter_registry.py` | Modify | 95 | < 500. 3 assertions updated. |

**Size policy**: All files ≤ 500 effective non-empty lines. No SoC split assessment triggered.

---

## Review Checks — Per File

### `src/complira_graph/ingestion/adapter_registry.py`

| Check | Result | Notes |
| --- | --- | --- |
| Architecture fit | Pass | Config-only change; registry pattern maintained — per-tool config in data, engine logic unchanged |
| Layering fitness | Pass | No new imports; no upward deps |
| Boundary placement | Pass | `semgrep` owns native CLI format; `semgrep_custom` owns pre-processed format — clean split |
| Existing-structure bias | Pass | Fix moves toward canonical tool output, not away |
| Anti-hack | Pass | No workarounds; clean field_map update with inline comments |
| Terminology/vocabulary | Pass | `semgrep_custom` naming is explicit about its purpose; comment block documents the distinction |
| SoC | Pass | Registry is data-only; no logic mixed in |
| Duplication | Pass | `semgrep_custom` is an intentional preserved-compat copy, not accidental duplication; documented with a comment block explaining its purpose |
| Simplification | Pass | `parse_root = "results"` simpler than `"categories.*[]"`; no unnecessary complexity |
| Decommission/cleanup | Pass | Old semgrep format not retained in `semgrep` adapter; preserved explicitly as `semgrep_custom` with documentation |
| No-legacy | Pass | `semgrep` adapter is clean; no backward compat shims |

---

### `tests/unit/ingestion/test_ingestion_engine.py`

| Check | Result | Notes |
| --- | --- | --- |
| Architecture fit | Pass | Test exercises real `semgrep`/`checkov` adapter entries directly — no adapter overrides needed |
| Test quality | Pass | Added field-specific assertions (`test_rule_id_mapped_from_check_id`, `test_file_path_mapped_from_path`, `test_line_start_mapped_from_start_line`) for direct AC coverage |
| Payload realism | Pass | `SEMGREP_PAYLOAD` now uses native Semgrep 1.x format; `CHECKOV_PAYLOAD` uses real top-level structure with `parsing_errors` array |
| No-legacy | Pass | Removed `setup_method`/`teardown_method` test adapter override — no longer needed |
| Test naming | Pass | `test_cwe_extracted_from_message` → `test_cwe_extracted_from_metadata` accurately reflects that CWE now comes from `extra.metadata.cwe`, not the message string |

---

### `tests/unit/ingestion/test_adapter_registry.py`

| Check | Result | Notes |
| --- | --- | --- |
| Architecture fit | Pass | Registry count and expected-tools set correctly updated |
| Correctness | Pass | `multi_root` assertion updated to match real Checkov paths; `semgrep_custom` added to expected set |

---

## Overall Findings Summary

| ID | Severity | File | Observation | Action Required |
| --- | --- | --- | --- | --- |
| — | — | — | No findings | — |

---

## Gate Decision

**Result: Pass**

All mandatory review checks pass. No findings. Advancing to Stage 9 (Docs Sync).
