# Requirements: Fix Scanner Adapter Field Mappings

- Status: `Design-ready`
- Ticket: fix-scanner-adapter-field-mappings
- Branch: codex/fix-scanner-adapter-field-mappings
- Date: 2026-03-19

## Goal / Problem Statement

The `ADAPTER_REGISTRY` in `src/complira_graph/ingestion/adapter_registry.py` contains two adapters
whose `parse_root` and `field_map` configurations do not match the real JSON output of the tools
they represent.

**Semgrep**: The adapter uses `parse_root = "categories.*[]"` and field names (`rule_id`,
`file_path`, `line_number`) that match a custom pre-processed format stored in
`tests/fixtures/sboms/sarif_semgrep.json`. Native Semgrep CLI output (`semgrep --json`) has a
different structure: `{"results": [...]}` with fields `check_id`, `path`, and `start.line`/`end.line`
nested under each result's location. Submitting native Semgrep output to `POST /v1/scan/ingest`
with `format=json, scan_type=sast` currently ingests **zero findings** silently.

**Checkov**: The adapter uses `parse_root = "results.failed_checks"` and multi_root paths prefixed
with `results.`. Real Checkov 2.x CLI output (`checkov -o json`) places `failed_checks`,
`passed_checks`, and `skipped_checks` at the **top level** of the JSON object (not under a `results`
key). The unit test `CHECKOV_PAYLOAD` manually adds a `results` wrapper, masking this mismatch.

**Unit test fixtures**: The existing `SEMGREP_PAYLOAD` and `CHECKOV_PAYLOAD` in
`tests/unit/ingestion/test_ingestion_engine.py` fabricate payloads that match the broken adapter
configs rather than real scanner output. This means unit tests pass green while real-world ingestion
silently drops all findings.

## In-Scope Use Cases

| UC ID | Description |
| --- | --- |
| UC-001 | Native Semgrep JSON (`semgrep --json`) submitted to `POST /v1/scan/ingest` produces findings in `scan_findings` collection |
| UC-002 | Native Checkov JSON (`checkov -o json`) submitted to `POST /v1/scan/ingest` routes FAILED → `scan_findings`, PASSED → `detected_controls`, SKIPPED → `audit_log` |
| UC-003 | Semgrep CWE metadata (`extra.metadata.cwe`) is extracted and stored in `cwe_ids` |
| UC-004 | Semgrep fingerprint is deterministic from `check_id` + `path` + `start.line` |
| UC-005 | Checkov fingerprint is deterministic from `check_id` + `file_path` + `resource` (unchanged) |
| UC-006 | Existing `sarif_semgrep.json` custom format is preserved — either via a separate `semgrep_custom` adapter or documented as a breaking change |

## Acceptance Criteria

| AC ID | Criterion |
| --- | --- |
| AC-001 | Given native Semgrep JSON with `results` array, `IngestionEngine.process("semgrep", payload, ...)` returns ≥1 bundle with `collection = "scan_findings"` |
| AC-002 | Semgrep bundle document contains `rule_id` mapped from `check_id` |
| AC-003 | Semgrep bundle document contains `file_path` mapped from `path` |
| AC-004 | Semgrep bundle document contains `line_start` mapped from `start.line` |
| AC-005 | Semgrep bundle document contains `line_end` mapped from `end.line` |
| AC-006 | Semgrep bundle document contains `severity` mapped and normalized from `extra.severity` |
| AC-007 | Semgrep bundle document contains `message` mapped from `extra.message` |
| AC-008 | Semgrep CWE IDs extracted from `extra.metadata.cwe` (list format: `["CWE-78: ..."]`) |
| AC-009 | Semgrep fingerprint is computed from `check_id` + `path` + `start.line` |
| AC-010 | Given native Checkov JSON (no `results` wrapper) with top-level `failed_checks`, `passed_checks`, `skipped_checks`, `IngestionEngine.process("checkov", payload, ...)` returns 3 bundles |
| AC-011 | Checkov FAILED bundle routes to `scan_findings` |
| AC-012 | Checkov PASSED bundle routes to `detected_controls` |
| AC-013 | Checkov SKIPPED bundle routes to `audit_log` |
| AC-014 | Existing Checkov fingerprint fields (`check_id`, `file_path`, `resource`) are unchanged |
| AC-015 | `SEMGREP_PAYLOAD` in `test_ingestion_engine.py` uses native Semgrep JSON structure (no test adapter override of `parse_root`) |
| AC-016 | `CHECKOV_PAYLOAD` in `test_ingestion_engine.py` uses real Checkov JSON structure (no `results` wrapper) |
| AC-017 | All 176 existing unit tests remain passing after adapter changes |

## Constraints and Dependencies

- `IngestionEngine` code is not modified — only `ADAPTER_REGISTRY` entries and test fixtures
- The `sarif_semgrep.json` fixture documents the legacy custom format; a decision must be made:
  either add a `semgrep_custom` adapter entry or treat the fixture as a legacy/deprecated test artifact
- Native Semgrep JSON format reference: `semgrep --json` produces `{"results": [{"check_id": "...", "path": "...", "start": {"line": N, "col": N}, "end": {...}, "extra": {"severity": "ERROR", "message": "...", "metadata": {"cwe": [...], "owasp": [...], "confidence": "HIGH", "references": [...]}}}]}`
- Native Checkov 2.x JSON format reference: `checkov -o json` produces top-level `check_type`, `passed_checks`, `failed_checks`, `skipped_checks`, `parsing_errors`

## Assumptions

- The ingestion engine's `_get_field` and `_extract_list` already handle the nested path access required for native Semgrep fields (`extra.severity`, `extra.message`, `extra.metadata.cwe`, `start.line`)
- Checkov's top-level structure is the same whether run with or without `--bc-api-key`

## Design Decisions (from Investigation)

- **OQ-001 resolved**: Add `semgrep_custom` adapter entry retaining current `categories.*[]` config and field names. Update `semgrep` adapter to native CLI format. The FDA SBOM fixture (`sarif_semgrep.json`) continues to work via `semgrep_custom`.
- **OQ-002 resolved**: `_extract_cwe` line 425 calls `str(doc.get("_cwe_raw") or "")` — stringifying the CWE list `["CWE-78: ..."]` makes the regex work. Map `extra.metadata.cwe` → `_cwe_raw`; keep `cwe_source = "extracted"`. No engine changes.
- **Scope**: Small — 2 adapter entries changed + 1 new adapter entry added (`semgrep_custom`) + test payloads updated. No engine/service/endpoint changes.

## Requirement → Use Case Coverage Map

| Requirement | Mapped UC IDs |
| --- | --- |
| Native Semgrep ingestion works (parse_root, field_map) | UC-001, UC-003, UC-004 |
| Native Checkov ingestion works (no results wrapper) | UC-002, UC-005 |
| Existing custom format preserved | UC-006 |

## Acceptance Criteria → Stage 7 Scenario Map

| AC ID | Scenario ID |
| --- | --- |
| AC-001–AC-009 | S-001 (Semgrep native pipeline) |
| AC-010–AC-014 | S-002 (Checkov native pipeline) |
| AC-015–AC-016 | S-003 (test payload accuracy) |
| AC-017 | S-004 (regression: all existing tests pass) |

## Open Risks

- OQ-003: Checkov multi-framework output (list of objects) — out of scope
- Semgrep Pro / Supply Chain output format may differ — out of scope, limited to open-source Semgrep CLI 1.x
