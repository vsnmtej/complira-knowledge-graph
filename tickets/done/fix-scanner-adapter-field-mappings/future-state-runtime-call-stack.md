# Future-State Runtime Call Stacks

- Ticket: fix-scanner-adapter-field-mappings
- Version: v1
- Design basis: implementation-plan.md solution sketch
- Date: 2026-03-19

---

## UC-001 — Native Semgrep JSON ingestion produces findings in scan_findings

**Type**: Requirement
**Source requirement**: AC-001–AC-009
**Entry point**: `POST /v1/scan/ingest` with `format=json, scan_type=sast`, body = native Semgrep JSON

```
[API Endpoint] src/api/v1/endpoints/scan.py:ingest_scan_endpoint(request, customer)
  → _derive_tool_name(request)
      lookup: (format="json", scan_type="sast") → "semgrep"
      return "semgrep"
  → EvidenceIngestionService.ingest_scan(payload_bytes, tool_name="semgrep", ...)
      [DB write: scan_runs — create run, status=running]

      → IngestionEngine.process(tool_name="semgrep", payload, scan_run_id, tenant_id)
          adapter = ADAPTER_REGISTRY["semgrep"]
          # parse_root = "results" → extracts list directly from {"results": [...]}
          raw_items = _extract_list(parsed_json, "results")    # [{"check_id": ..., "path": ..., "start": {...}, "extra": {...}}]

          for raw in raw_items:
              → _parse(adapter, raw)      # returns raw (json_object adapter does no extra parse)
              → _route(adapter, raw)      # result_routing = {"*": "scan_findings"} → "scan_findings"
              → _fingerprint(adapter, raw)
                  fields = [_get_field(raw, "check_id"), _get_field(raw, "path"), _get_field(raw, "start.line")]
                  # → ["python.lang.security.audit.sqli.sqli", "app/db.py", 42]
                  sha256("|".join(fields))[:32] → "ab12cd34..." (deterministic)
              → _map_fields(adapter, raw)
                  # Applies field_map:
                  # check_id → rule_id = "python.lang.security.audit.sqli.sqli"
                  # path → file_path = "app/db.py"
                  # start.line → line_start = 42
                  # end.line → line_end = 42
                  # extra.severity → severity = "ERROR"
                  # extra.message → message = "SQL injection detected"
                  # extra.metadata.cwe → _cwe_raw = ["CWE-89: Improper Neutralization..."]
                  # extra.metadata.owasp → owasp_category = ["A01:2021 - Injection"]
                  # extra.metadata.confidence → tool_confidence = "HIGH"
                  # extra.lines → code_snippet = "cursor.execute(...)"
                  doc = {rule_id: ..., file_path: ..., line_start: 42, ..., _cwe_raw: ["CWE-89: ..."]}
              → _classify_severity(adapter, raw, doc)
                  # severity_map["ERROR"] → "high"
                  doc["severity"] = "high"
              → _extract_cwe(adapter, raw, doc)
                  # cwe_source = "extracted"
                  # combined = str(doc["_cwe_raw"]) = "['CWE-89: Improper Neutralization...']"
                  # re.findall(r"(CWE-\d+)", combined) → ["CWE-89"]
                  doc["cwe_ids"] = ["CWE-89"]
                  doc["cwe_source"] = "extracted"
              → _redact(adapter, doc)    # secret_raw_field = None → no-op
              → _validate(doc)           # no cve_id → no-op
              → _plan_edges(adapter, doc, "scan_findings")
                  # req_mapping_source = "rule_engine" → plan edge with source="rule_engine"
                  edges = [{"_from": "scan_findings/ab12cd34...", "source": "rule_engine", ...}]
              → inject canonical metadata: tenant_id, scan_run_id, tool="semgrep", finding_type="sast", _key=fingerprint
              → remove staging fields (_cwe_raw, _riskdesc_raw, etc.)
              yield IngestionBundle(collection="scan_findings", document=doc, edges=edges)

      [DB write: EvidenceFindingRepository.upsert_batch([doc])]
      [DB write: EvidenceEdgeService.create_all_edges(bundles)]
      [DB write: scan_runs — complete run, status=completed]
      return ScanIngestResult(run_id=..., findings_count=1, ...)
```

**Coverage**: primary path ✓, error path (parse failure → run marked failed) ✓ (engine raises → service catches)
**Fallback**: `parse_root = "results"` not present in payload → `_extract_list` returns `[]` → 0 bundles → run completes with 0 findings (no exception)

---

## UC-002 — Native Checkov JSON (no `results` wrapper) routes to three collections

**Type**: Requirement
**Source requirement**: AC-010–AC-014

```
[API Endpoint] src/api/v1/endpoints/scan.py:ingest_scan_endpoint(...)
  → _derive_tool_name(request)
      lookup: (format="json", scan_type="iac") → "checkov"

  → IngestionEngine.process("checkov", payload, ...)
      adapter = ADAPTER_REGISTRY["checkov"]
      # multi_root = ["failed_checks", "passed_checks", "skipped_checks"]

      for root_path in multi_root:
          raw_items = _extract_list(parsed_json, root_path)
          # root_path="failed_checks" → extracts from top-level {"check_type": ..., "failed_checks": [...]}
          # root_path="passed_checks" → extracts passed_checks list
          # root_path="skipped_checks" → extracts skipped_checks list

          for raw in raw_items:
              → _route(adapter, raw)
                  result_state = _get_field(raw, "check_result.result")  # "FAILED"/"PASSED"/"SKIPPED"
                  collection = result_routing[result_state]
                  # "FAILED" → "scan_findings"
                  # "PASSED" → "detected_controls"
                  # "SKIPPED" → "audit_log"
              → _fingerprint: sha256("check_id|file_path|resource")[:32]  # unchanged
              → _map_fields: check_id, check_name, file_path, resource→resource_address, bc_check_id, @check_type→iac_framework
              → _plan_edges:
                  if collection == "scan_findings":
                      bc_check_id present → source="checkov_native"
                      bc_check_id absent  → source="llm_reg_mapper"  (DR-003)
              yield IngestionBundle(collection=..., ...)
      # Result: 3 bundles (FAILED→scan_findings, PASSED→detected_controls, SKIPPED→audit_log)
```

**Coverage**: primary path ✓, all three routing branches ✓, DR-003 bc_check_id override ✓

---

## UC-003 — CWE IDs extracted from native Semgrep `extra.metadata.cwe` list

**Type**: Requirement
**Source requirement**: AC-008

```
[In UC-001 pipeline, at _extract_cwe step]
  doc["_cwe_raw"] = ["CWE-89: Improper Neutralization of Special Elements used in an SQL Command"]

  _extract_cwe(adapter, raw, doc):
      cwe_source = "extracted"
      combined = " ".join([
          str(doc.get("message") or ""),          # "SQL injection detected"
          str(doc.get("description") or ""),       # ""
          str(doc.get("_cwe_raw") or ""),          # "['CWE-89: Improper Neutralization...']"
          str(doc.get("_cwe_int") or ""),          # ""
      ])
      matches = re.findall(r"(CWE-\d+)", combined)   # → ["CWE-89"]
      return ["CWE-89"], "extracted"
```

**Coverage**: primary path ✓

---

## UC-004 — Semgrep fingerprint is deterministic from `check_id` + `path` + `start.line`

**Type**: Requirement
**Source requirement**: AC-009

```
[In UC-001 pipeline, at _fingerprint step]
  fingerprint_fields = ["check_id", "path", "start.line"]
  values = [_get_field(raw, "check_id"), _get_field(raw, "path"), _get_field(raw, "start.line")]
  # → ["python.lang.security.audit.sqli.sqli", "app/db.py", 42]
  key_string = "|".join(str(v) for v in values)
  fingerprint = sha256(key_string.encode()).hexdigest()[:32]
  # Deterministic: same input → same fingerprint across runs
```

**Coverage**: primary path ✓

---

## UC-005 — Checkov fingerprint unchanged (`check_id`, `file_path`, `resource`)

**Type**: Requirement
**Source requirement**: AC-014

No change to `fingerprint_fields` for checkov adapter. Covered implicitly by existing `test_checkov_fingerprint_uses_check_id_file_resource` test.

**Coverage**: N/A (no change)

---

## UC-006 — `semgrep_custom` adapter preserves categories format

**Type**: Requirement
**Source requirement**: AC-017 (no regression for existing fixture-based tests)

```
[No code change — semgrep_custom adapter is a copy of current semgrep adapter]
  ADAPTER_REGISTRY["semgrep_custom"] = {
      "parse_root": "categories.*[]",
      "fingerprint_fields": ["rule_id", "file_path", "line_number"],
      "field_map": { ... same as current semgrep ... }
  }

  IngestionEngine.process("semgrep_custom", sarif_semgrep_payload, ...)
      # Same behavior as current "semgrep" adapter
      # sarif_semgrep.json fixture continues to work unchanged
```

**Coverage**: primary path ✓ (no new logic, adapter config copy)
