# Implementation Plan: Fix Scanner Adapter Field Mappings

- Ticket: fix-scanner-adapter-field-mappings
- Scope: `Small`
- Status: Draft (pre-Stage 5 Go Confirmed)
- Date: 2026-03-19

## Solution Sketch

**Architecture layer**: `src/complira_graph/ingestion/adapter_registry.py` only — configuration data, no logic changes.

**Target layers/boundaries**:
- `adapter_registry.py` — adapter configuration (data layer); no imports from other modules
- `test_ingestion_engine.py` — unit tests; no production code

**No new modules/files** (beyond possibly a native Semgrep fixture for tests).

## Change Inventory

| ID | File | Change Type | Description |
| --- | --- | --- | --- |
| C-001 | `src/complira_graph/ingestion/adapter_registry.py` | Modify | Update `semgrep` adapter: `parse_root`, `fingerprint_fields`, `field_map` |
| C-002 | `src/complira_graph/ingestion/adapter_registry.py` | Add | Add `semgrep_custom` adapter: copy of current `semgrep` adapter (categories format) |
| C-003 | `src/complira_graph/ingestion/adapter_registry.py` | Modify | Update `checkov` adapter: remove `results.` prefix from `parse_root` and `multi_root` |
| C-004 | `tests/unit/ingestion/test_ingestion_engine.py` | Modify | Update `SEMGREP_PAYLOAD` to native Semgrep format; remove `parse_root` override in `TestSemgrepPipeline.setup_method` |
| C-005 | `tests/unit/ingestion/test_ingestion_engine.py` | Modify | Update `CHECKOV_PAYLOAD` to remove `results` wrapper |

## Implementation Steps

### Step 1: Add `semgrep_custom` adapter (C-002)

Copy the current `semgrep` entry verbatim but with `tool_name = "semgrep_custom"`. This preserves the FDA SBOM test fixture behavior and ensures no test regressions from existing fixtures.

### Step 2: Update `semgrep` adapter (C-001)

```python
"semgrep": {
    "tool_name":            "semgrep",
    "parse_format":         "json_object",
    "parse_root":           "results",          # was: "categories.*[]"
    "multi_root":           [],
    "fingerprint_fields":   ["check_id", "path", "start.line"],  # was: ["rule_id", "file_path", "line_number"]
    "severity_map": {
        "ERROR":    "high",    "WARNING":  "medium",
        "INFO":     "info",    "NOTE":     "info",
        "CRITICAL": "critical","HIGH":     "high",
        "MEDIUM":   "medium",  "LOW":      "low",
    },
    "default_finding_type": "sast",
    "result_routing":       {"*": "scan_findings"},
    "result_state_field":   None,
    "location_anchor":      "file_line",
    "field_map": {
        "check_id":                   "rule_id",         # native: check_id → canonical: rule_id
        "path":                       "file_path",       # native: path → canonical: file_path
        "start.line":                 "line_start",      # native: start.line
        "end.line":                   "line_end",        # native: end.line
        "extra.lines":                "code_snippet",    # native: extra.lines (source snippet)
        "extra.metadata.cwe":         "_cwe_raw",        # list: ["CWE-78: ..."] → str() + regex
        "extra.metadata.owasp":       "owasp_category",
        "extra.metadata.confidence":  "tool_confidence",
        "extra.metadata.references":  "references",
        "extra.severity":             "severity",        # native: extra.severity
        "extra.message":              "message",         # native: extra.message
        "extra.fix":                  "fix_guidance",    # native: extra.fix (when present)
    },
    "cwe_source":               "extracted",            # str(list) → regex works
    "cwe_extract_pattern":      r"(CWE-\d+)",
    "req_mapping_source":       "rule_engine",
    "deterministic_req_fields": [],
    "secret_raw_field":         None,
    "pre_process":              None,
},
```

### Step 3: Update `checkov` adapter (C-003)

Change only:
- `parse_root`: `"results.failed_checks"` → `"failed_checks"`
- `multi_root`: remove `"results."` prefix from all three paths

### Step 4: Update `SEMGREP_PAYLOAD` in tests (C-004)

Replace `SEMGREP_PAYLOAD` with native Semgrep JSON:
```python
SEMGREP_PAYLOAD = json.dumps({
    "results": [
        {
            "check_id": "python.lang.security.audit.sqli.sqli",
            "path": "app/db.py",
            "start": {"line": 42, "col": 1},
            "end": {"line": 42, "col": 50},
            "extra": {
                "severity": "ERROR",
                "message": "SQL injection detected",
                "metadata": {
                    "cwe": ["CWE-89: Improper Neutralization of Special Elements used in an SQL Command"],
                    "owasp": ["A01:2021 - Injection"],
                    "confidence": "HIGH",
                    "references": ["https://owasp.org/"]
                },
                "lines": "cursor.execute(f\"SELECT * FROM users WHERE id={user_id}\")"
            }
        }
    ],
    "errors": [],
    "paths": {"scanned": ["app/db.py"], "ignored": []}
}).encode()
```

Remove the `setup_method` `parse_root` override in `TestSemgrepPipeline` — the native semgrep adapter's `parse_root = "results"` now works directly.

Update field-specific assertions:
- `test_cwe_extracted_from_message` → CWE now comes from `extra.metadata.cwe` list, not the `message` string; the test should verify `"CWE-89" in bundles[0].document["cwe_ids"]`
- `test_severity_mapped_to_high` → severity still maps from `extra.severity = "ERROR"` → `"high"` (unchanged)

### Step 5: Update `CHECKOV_PAYLOAD` in tests (C-005)

Remove the `results` wrapper:
```python
CHECKOV_PAYLOAD = json.dumps({
    "check_type": "terraform",
    "failed_checks": [...],    # was: "results": {"failed_checks": [...], ...}
    "passed_checks": [...],
    "skipped_checks": [...],
}).encode()
```

## Verification

- Run full unit test suite: `uv run pytest tests/unit/ingestion/ -v`
- Confirm 0 regressions; updated tests exercise native payloads
- Confirm `semgrep_custom` adapter is registered and passes `test_all_expected_tools_present` (add to expected set)
