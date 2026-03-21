# Implementation Progress: Fix Scanner Adapter Field Mappings

- Ticket: fix-scanner-adapter-field-mappings
- Date: 2026-03-19

## Change Status

| ID | File | Change Type | Status | Notes |
| --- | --- | --- | --- | --- |
| C-001 | `src/complira_graph/ingestion/adapter_registry.py` | Modify | Completed | semgrep adapter: parse_root="results", fingerprint_fields=["check_id","path","start.line"], updated field_map |
| C-002 | `src/complira_graph/ingestion/adapter_registry.py` | Add | Completed | semgrep_custom adapter: preserves categories.*[] format for FDA SBOM fixture |
| C-003 | `src/complira_graph/ingestion/adapter_registry.py` | Modify | Completed | checkov adapter: parse_root="failed_checks", multi_root without results. prefix |
| C-004 | `tests/unit/ingestion/test_ingestion_engine.py` | Modify | Completed | SEMGREP_PAYLOAD → native Semgrep format; removed parse_root override; added field-specific assertions; renamed test_cwe_extracted_from_message → test_cwe_extracted_from_metadata |
| C-005 | `tests/unit/ingestion/test_ingestion_engine.py` | Modify | Completed | CHECKOV_PAYLOAD → no results wrapper; inline bc_check_id test payload also fixed |
| C-006 | `tests/unit/ingestion/test_adapter_registry.py` | Modify | Completed | test_registry_is_not_empty ≥8; test_all_expected_tools_present includes semgrep_custom; test_multi_root_configured uses paths without results. prefix |

## Test Results

- `uv run pytest tests/unit/ingestion/` → 179 passed, 0 failed
- `uv run pytest tests/ --ignore=tests/integration/ingestion` → 883 passed, 1 skipped, 0 failed

## Stage 6 Gate

All implementation tasks complete. Required unit verification: Pass (179/179 unit ingestion + 883/883 total).

## Stage 9 Docs Sync

**Decision**: No docs impact.

**Rationale**: `docs/GRAPH_ARCHITECTURE.md` references Semgrep/Checkov at architecture level only (ingestion entry points, collection names). No canonical doc specifies per-tool JSON field schemas or parse_root values — those are implementation details of `adapter_registry.py`. The v2.2 Scanner Evidence Layer section added in the evidence-ingestion-pipeline ticket remains accurate. No docs updates required.
