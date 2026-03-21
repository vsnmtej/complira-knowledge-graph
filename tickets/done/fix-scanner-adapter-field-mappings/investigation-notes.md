# Investigation Notes: Fix Scanner Adapter Field Mappings

- Ticket: fix-scanner-adapter-field-mappings
- Date: 2026-03-19
- Scope Triage: `Small`

## Sources Consulted

- `src/complira_graph/ingestion/adapter_registry.py` — ADAPTER_REGISTRY entries for semgrep, checkov
- `tests/unit/ingestion/test_ingestion_engine.py` — SEMGREP_PAYLOAD, CHECKOV_PAYLOAD, full pipeline tests
- `tests/fixtures/sboms/sarif_semgrep.json` — custom pre-processed Semgrep format fixture
- Native Semgrep CLI JSON schema (semgrep 1.x `--json` output, well-known public format)
- Native Checkov 2.x CLI JSON schema (`checkov -o json`, well-known public format)
- `src/complira_graph/ingestion/ingestion_engine.py` — `_get_field`, `_extract_list`, `process()`, field_map application
- `src/api/v1/endpoints/scan.py` — `_FORMAT_SCAN_TYPE_TO_TOOL` dispatch, `ingest_scan_endpoint`

## Key Findings

### Finding 1: Semgrep adapter `parse_root` targets a custom format, not native Semgrep CLI output

**Adapter config** (`adapter_registry.py:148`):
```python
"parse_root": "categories.*[]"
"field_map": {
    "rule_id": "rule_id",
    "file_path": "file_path",
    "line_number": "line_start",
    ...
}
```

**Custom format** (what the adapter expects — matches `sarif_semgrep.json`):
```json
{
  "total_findings": 100,
  "categories": {
    "sast": [...],
    "other_security_issues": [
      {"rule_id": "...", "file_path": "...", "line_number": 42, "severity": "ERROR", "cwe": "CWE-78: ..."}
    ]
  }
}
```

**Native Semgrep 1.x CLI output** (`semgrep --json`):
```json
{
  "results": [
    {
      "check_id": "python.lang.security.audit.exec-used",
      "path": "src/main.py",
      "start": {"line": 42, "col": 1},
      "end": {"line": 42, "col": 10},
      "extra": {
        "severity": "ERROR",
        "message": "Use of exec detected",
        "metadata": {
          "cwe": ["CWE-78: Improper Neutralization..."],
          "owasp": ["A01:2021 - Broken Access Control"],
          "confidence": "HIGH",
          "references": ["https://..."]
        },
        "lines": "exec(user_input)"
      }
    }
  ],
  "errors": [],
  "paths": {"scanned": [...], "ignored": []}
}
```

**Gap**: `parse_root = "categories.*[]"` extracts nothing from native Semgrep output → silent zero findings. Field names `rule_id`, `file_path`, `line_number` don't exist in native output.

**Required field_map updates for native Semgrep**:
| Native Semgrep field | Current adapter key | Required adapter key |
|---|---|---|
| `check_id` | `rule_id` | `check_id` |
| `path` | `file_path` | `path` |
| `start.line` | `line_number` | `start.line` |
| `end.line` | `end_line` | `end.line` |
| `extra.severity` | `severity` | `extra.severity` |
| `extra.message` | `message` | `extra.message` |
| `extra.metadata.cwe` | `cwe` | `extra.metadata.cwe` |
| `extra.metadata.owasp` | `owasp` | `extra.metadata.owasp` |
| `extra.metadata.confidence` | `confidence` | `extra.metadata.confidence` |
| `extra.metadata.references` | `references` | `extra.metadata.references` |
| `extra.lines` | `code_snippet` | `extra.lines` |

**Fingerprint**: Must change from `["rule_id", "file_path", "line_number"]` to `["check_id", "path", "start.line"]` — these are the stable identity fields for native Semgrep output.

**CWE extraction**: Native Semgrep provides CWE as a list of strings (`["CWE-78: ..."]`) in `extra.metadata.cwe`. The `cwe_extract_pattern = r"(CWE-\d+)"` regex will correctly extract `CWE-78` from these strings IF the field is mapped to the text that `_extract_cwe` inspects. Two options:
  - Map `extra.metadata.cwe` → `_cwe_raw` (list) and handle list in `_extract_cwe` (list join + regex)
  - Keep `cwe_source = "extracted"` with the message text approach — but `extra.message` may not always include CWE

  Investigation: `_extract_cwe` in `ingestion_engine.py` uses `_get_field` to extract from `doc[cwe_extract_field]` using `cwe_extract_pattern`. The `doc` at that point is the already-mapped document. If `extra.metadata.cwe` is mapped to `_cwe_raw`, it would need special handling. The cleaner approach: map `extra.metadata.cwe` to `_cwe_raw` and join the list to a string before regex extraction (or handle list type in `_extract_cwe`). Need to check `_extract_cwe` implementation.

  **Alternative**: Map `extra.message` → `message` and rely on the existing `extracted` source from the message string. This works when the message contains CWE IDs, but Semgrep messages don't always include CWE. Better: use `tool_direct` source with `extra.metadata.cwe` mapped to a cwe list field.

  Actually the simplest fix: map `extra.metadata.cwe[0]` → `_cwe_raw_text` — but `_get_field` on a list key would return the list. We need to confirm how `_extract_cwe` handles a list value vs string.

### Finding 2: Checkov adapter `parse_root` and `multi_root` assume a `results` wrapper that doesn't exist in real Checkov output

**Adapter config** (`adapter_registry.py:191-196`):
```python
"parse_root": "results.failed_checks",
"multi_root": [
    "results.failed_checks",
    "results.passed_checks",
    "results.skipped_checks",
],
```

**Real Checkov 2.x output** (`checkov -o json`):
```json
{
  "check_type": "terraform",
  "passed_checks": [...],
  "failed_checks": [...],
  "skipped_checks": [...],
  "parsing_errors": []
}
```

**Required fix**: Remove `results.` prefix from all paths:
```python
"parse_root": "failed_checks",
"multi_root": ["failed_checks", "passed_checks", "skipped_checks"],
```

**Unit test**: `CHECKOV_PAYLOAD` in `test_ingestion_engine.py` wraps checks under `"results": {...}` — this must be updated to the real top-level structure.

### Finding 3: The custom `sarif_semgrep.json` format must be preserved

The fixture at `tests/fixtures/sboms/sarif_semgrep.json` uses the `categories.*[]` custom format and field names matching the current (broken) semgrep adapter. The FDA SBOM e2e test uses this fixture.

Decision needed: add a `semgrep_custom` adapter entry (for the pre-processed format) alongside the fixed `semgrep` adapter (for native CLI output), OR deprecate the custom format.

**Recommendation**: Add `semgrep_custom` adapter that retains the current `categories.*[]` config and field_map. This keeps FDA SBOM test coverage intact and allows users who already pre-process Semgrep output to continue using the custom format. The `semgrep` adapter is updated to accept native CLI output.

### Finding 4: `_extract_list` already handles `categories.*[]` via `".*[]"` pattern

`ingestion_engine.py:_extract_list` has a `.*[]` handler that flattens nested category dicts. This logic is reused correctly by the `semgrep_custom` adapter. The fixed `semgrep` adapter uses `parse_root = "results"` which is a simple key lookup — no special path handling required.

### Finding 5: `_get_field` supports dot-notation nested paths

`_get_field(obj, "start.line")` will correctly traverse `{"start": {"line": 42}}` → `42`. Similarly `_get_field(obj, "extra.severity")` works. The engine handles this natively; no engine changes needed.

### Finding 6: CWE field — native Semgrep provides a list, not a string

Native Semgrep: `extra.metadata.cwe = ["CWE-78: Improper Neutralization..."]`

The `_extract_cwe` method in the engine runs a regex on a string (from a mapped doc field). If the field value is a list, joining it first will work. Investigation shows `_extract_cwe` receives the doc (already field-mapped). The CWE list from native Semgrep can be handled by mapping it to a staging field `_cwe_list` and joining in a `pre_process` hook, OR by changing `cwe_source` to `tool_direct` and handling list-type values in the engine — but that would require engine changes.

**Simplest no-engine-change approach**: Map `extra.message` → `message` (already done) and keep `cwe_source = "extracted"` — Semgrep messages don't reliably contain CWE IDs. Also add a `pre_process` function on the native semgrep adapter that flattens `extra.metadata.cwe` list into a string appended to the message, allowing the regex to pick it up.

**Alternative no-engine-change approach**: Map `extra.metadata.cwe` to a staging `_cwe_str` field using a `pre_process` that joins the list items into a space-separated string; then `_extract_cwe` extracts from `_cwe_str` via the existing regex. This is cleaner.

**Decision**: Use `pre_process` to flatten `extra.metadata.cwe` (list) into a space-separated string stored under `cwe` (top-level on each result item). Then `cwe_source = "extracted"` with `cwe_extract_pattern = r"(CWE-\d+)"` extracts correctly from the mapped `_cwe_raw` field. Alternatively, after field mapping, `_cwe_raw` holds the list and `_extract_cwe` must handle it — but this would need engine changes.

**Confirmed decision**: Use `pre_process` on the native semgrep adapter to normalize `extra.metadata.cwe` from list → space-separated string before the engine sees each result item. OR: since `_get_field` with `extra.metadata.cwe` returns a list, and `_extract_cwe` would get that list from the doc... need to check if `re.findall(pattern, str(value))` would work on a stringified list. That would work — the string representation would be `"['CWE-78: ...']"` and the regex would find `CWE-78`.

Actually, the cleanest path is a simple `pre_process` function that runs on the list of raw finding dicts and injects a `_cwe_str` field from `extra.metadata.cwe`.

## Scope Triage: `Small`

- Files touched: 2 source files (`adapter_registry.py`, `test_ingestion_engine.py`) + possibly a new native Semgrep fixture
- No engine code changes
- No new public APIs
- No cross-cutting behavior changes
- No schema/storage changes
- Estimated change delta: <100 lines

## Open Unknowns — RESOLVED

- OQ-001: **Resolved** — add `semgrep_custom` adapter entry retaining `categories.*[]` config. Keep `semgrep` adapter for native CLI output.
- OQ-002: **Resolved** — `_extract_cwe` with `cwe_source = "extracted"` calls `str(doc.get("_cwe_raw") or "")` (line 425 of `ingestion_engine.py`). Mapping `extra.metadata.cwe` → `_cwe_raw` means the list `["CWE-78: ..."]` gets stringified to `"['CWE-78: ...']"` and `re.findall(r"(CWE-\d+)", ...)` correctly extracts `CWE-78`. No `pre_process` function needed.

## Implications for Design

- Only `adapter_registry.py` changes needed (no engine, no service, no endpoint changes)
- Add `semgrep_custom` adapter entry to preserve existing `sarif_semgrep.json` fixture behavior
- Update `semgrep` adapter: `parse_root = "results"`, updated `fingerprint_fields` and `field_map`
- Update `checkov` adapter: remove `results.` prefix from `parse_root` and `multi_root`
- Update `SEMGREP_PAYLOAD` and `CHECKOV_PAYLOAD` in `test_ingestion_engine.py`
- Add a native Semgrep fixture JSON (or inline it in tests)
- Pre-edit checklist: Stage 6 unlocked after Stage 5 Go Confirmed
