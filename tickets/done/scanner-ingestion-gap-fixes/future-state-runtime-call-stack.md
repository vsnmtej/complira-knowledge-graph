# Future-State Runtime Call Stacks

**Ticket:** `scanner-ingestion-gap-fixes`
**Version:** v1
**Design Basis:** `proposed-design.md` v1
**Last Updated:** 2026-03-22

---

## UC-SI-001 — Trivy Native JSON Ingestion

**Source:** Requirement (REQ-SI-001)
**Type:** `Requirement`

### Primary Path

```
POST /v1/scan/ingest {tool: "trivy", raw_file: trivy_output.json}
  → src/api/v1/endpoints/scan.py:ingest_scan()
    → EvidenceIngestionService.ingest(tool_name="trivy", raw_file=..., scan_run_id, tenant_id)
      → src/complira_graph/ingestion/ingestion_engine.py:IngestionEngine.process()
        → ADAPTER_REGISTRY["trivy"] loaded ✅
        → _parse(adapter, raw_file)
          → fmt == "json_object"
          → json.loads(raw_file) → data = {"SchemaVersion": 2, "Results": [...]}
          → _extract_list(data, "Results[*].Vulnerabilities[*]")
            → "[*]." in path → head="Results", tail="Vulnerabilities[*]"
            → arr = _get_field(data, "Results") → list of result objects
            → for each result: _extract_list(result, "Vulnerabilities[*]")
              → path.endswith("[*]") → arr = result["Vulnerabilities"] → list of vuln dicts
          → returns flat list of vuln dicts
        → pre_process is None → skip
        → for each vuln in raw_findings:
          → _process_one(adapter, vuln, scan_run_id, tenant_id, "trivy")
            → _route() → result_routing["*"] = "component_has_vuln"
            → _fingerprint() → SHA256("CVE-2024-1234|python-packages|requests")[:32]
            → _map_fields()
              → "VulnerabilityID" → cve_id = "CVE-2024-1234"
              → "Severity" → severity = "HIGH"
              → "CweIDs" → _cwe_raw = ["CWE-79"]
              → "PkgName" → component_name = "requests"
              → "InstalledVersion" → component_version = "2.0.0"
            → _classify_severity() → severity_map["HIGH"] = "high"
            → _extract_cwe() → cwe_source="tool_direct"
              → _normalise_cwe_values(["CWE-79"]) → ["CWE-79"]
              → returns (["CWE-79"], "tool_direct")
            → _validate() → "CVE-2024-1234" matches regex → cve_id kept
            → doc["_key"] = fingerprint, doc["tool"] = "trivy"
            → _plan_edges() → collection != "scan_findings" → return []
            → returns IngestionBundle(collection="component_has_vuln", document=doc, edges=[])
      → EvidenceEdgeService.create_component_has_vuln_edges(bundles)
        [DB write: component_has_vuln edge]
```

### Fallback: Vulnerabilities array empty for a Result

```
_extract_list(result, "Vulnerabilities[*]")
  → result.get("Vulnerabilities") = None or []
  → returns []
→ no findings processed for that Result; pipeline continues with other Results
```

### Error: Unknown severity value

```
_classify_severity() → raw_sev = "MEDIUM" → sev_map["MEDIUM"] = "medium" ✅
_classify_severity() → raw_sev = "UNKNOWN" → sev_map["UNKNOWN"] = None → severity = None
```

**Coverage:** Primary ✅ | Fallback ✅ | Error ✅

---

## UC-SI-002 — npm-audit JSON Ingestion

**Source:** Requirement (REQ-SI-002)
**Type:** `Requirement`

### Primary Path

```
POST /v1/scan/ingest {tool: "npm_audit", raw_file: npm_audit.json}
  → IngestionEngine.process(tool_name="npm_audit", ...)
    → _parse(adapter, raw_file)
      → fmt == "json_object"
      → json.loads(raw_file) → data = {"vulnerabilities": {"lodash": {...}, ...}}
      → _extract_list(data, "vulnerabilities.*[]")
        → ".*[]" in path → parent_path = "vulnerabilities"
        → parent = _get_field(data, "vulnerabilities") → dict of {pkg_name: vuln_obj}
        → for each v in parent.values():
            isinstance(v, list)? No → yield [v]
        → result = [{"name": "lodash", "severity": "high", "range": ">=1 <4.17.21", ...}, ...]
    → pre_process is None → skip
    → for each vuln_dict:
      → _process_one(adapter, vuln_dict, ...)
        → _route() → "component_has_vuln"
        → _fingerprint() → SHA256("lodash|>=1 <4.17.21")[:32]
        → _map_fields()
          → "name" → component_name = "lodash"
          → "severity" → severity = "high"
          → "range" → description = ">=1 <4.17.21"
          → "isDirect" → tool_confidence = True
        → _classify_severity() → severity_map["high"] = "high"
        → _extract_cwe() → cwe_source="absent" → ([], None)
        → _validate() → no cve_id → skip
        → collection = "component_has_vuln" → edges = []
        → IngestionBundle(collection="component_has_vuln", document=doc)
```

### Fallback: `fixAvailable` is an object (not boolean)

```
_map_fields() → "isDirect" → doc["tool_confidence"] = True/False (boolean)
"fixAvailable" not in field_map → not mapped → stored in raw_data only
→ no breakage; fixAvailable is informational metadata
```

### Error: `via` is a list of strings (transitive dep, no advisory object)

```
"via" not in field_map → not mapped → no error
→ CWE extraction skipped (cwe_source="absent") → no impact
```

**Coverage:** Primary ✅ | Fallback ✅ | Error ✅

---

## UC-SI-003 — pip-audit JSON Ingestion

**Source:** Requirement (REQ-SI-003)
**Type:** `Requirement`

### Primary Path

```
POST /v1/scan/ingest {tool: "pip_audit", raw_file: pip_audit.json}
  → IngestionEngine.process(tool_name="pip_audit", ...)
    → _parse(adapter, raw_file)
      → fmt == "json_object"
      → parse_root = None → returns [full_json_object]
      → raw_findings = [{"dependencies": [...], "fixes": [...]}]
    → pre_process = pip_audit_flatten → called with [full_json_object]
      → for each dep in dependencies:
          name="requests", version="2.28.0"
          for each vuln in dep["vulns"]:
            entry = {"id": "PYSEC-2022-48", "aliases": ["CVE-2022-29244"], ...}
            entry["pkg_name"] = "requests"
            entry["pkg_version"] = "2.28.0"
            for alias in aliases:
              re.match(CVE pattern, "CVE-2022-29244") → match!
              entry["cve_id"] = "CVE-2022-29244"
              break
            flat.append(entry)
      → returns [{"id": "PYSEC-2022-48", "cve_id": "CVE-2022-29244", "pkg_name": "requests", ...}]
    → for each flat_entry:
      → _process_one(adapter, flat_entry, ...)
        → _route() → "component_has_vuln"
        → _fingerprint() → SHA256("PYSEC-2022-48|requests")[:32]
        → _map_fields()
          → "id" → tool_vuln_id = "PYSEC-2022-48"
          → "cve_id" → cve_id = "CVE-2022-29244"
          → "description" → description = "..."
          → "fix_versions" → fix_guidance = ["2.29.0"]
        → _classify_severity() → severity_map[None] = None (no severity in pip-audit)
        → _extract_cwe() → cwe_source="absent" → ([], None)
        → _validate() → "CVE-2022-29244" matches regex → cve_id kept
        → IngestionBundle(collection="component_has_vuln", document=doc)
```

### Fallback: No CVE in aliases (PYSEC-only vuln)

```
pip_audit_flatten:
  for alias in aliases:  # aliases = ["GHSA-xxxx"] only
    re.match(CVE pattern, "GHSA-xxxx") → no match
  → entry["cve_id"] not set
→ _map_fields(): "cve_id" not in entry → not mapped
→ _validate(): no cve_id → skip
→ doc has tool_vuln_id only ✅
```

### Fallback: Dependency has no vulns (skip_reason present)

```
pip_audit_flatten:
  dep = {"name": "safe-pkg", "skip_reason": "no data"}
  dep.get("vulns", []) = []
  → inner loop not executed
  → nothing appended to flat
→ no finding created ✅
```

**Coverage:** Primary ✅ | Fallback ✅ | Error N/A

---

## UC-SI-004 — SonarQube JSON Ingestion (Dual-Path Severity)

**Source:** Requirement (REQ-SI-004)
**Type:** `Requirement`

### Primary Path (SonarQube v10+ with `impacts`)

```
POST /v1/scan/ingest {tool: "sonarqube", raw_file: sonarqube_issues.json}
  → _parse(adapter, raw_file)
    → fmt == "json_object", parse_root = "issues"
    → _extract_list(data, "issues") → list of issue dicts
  → for each issue:
    → _map_fields(adapter, raw_issue)
      → "severity": "MAJOR" → doc["severity"] = "MAJOR"       # legacy first
      → "rule": "java:S1134" → doc["rule_id"] = "java:S1134"
      → "message": "Fix this" → doc["message"] = "Fix this"
      → "component": "proj:src/Foo.java" → doc["file_path"] = "proj:src/Foo.java"
      → "line": 42 → doc["line_start"] = 42
      → "impacts[0].severity": "HIGH" → doc["severity"] = "HIGH"  # overwrites ✅
    → _classify_severity() → severity_map["HIGH"] = "high" ✅
    → _extract_cwe() → cwe_source="extracted", pattern=r"(CWE-\d+)"
      → combined = "Fix this" (no CWE in message)
      → returns ([], None)
    → _validate() → no cve_id → skip
    → collection = "scan_findings"
    → _plan_edges() → req_src = "rule_engine" → edge planned
    → IngestionBundle(collection="scan_findings", document=doc, edges=[...])
```

### Fallback: SonarQube pre-v10 (no `impacts` field)

```
_map_fields():
  → "severity": "MAJOR" → doc["severity"] = "MAJOR"      # legacy written
  → "impacts[0].severity": _get_field(raw, "impacts[0].severity")
    → raw.get("impacts") = None → _get_field returns None
    → None check: value is None → skip (not written to doc)
  → doc["severity"] = "MAJOR" preserved ✅
→ _classify_severity() → severity_map["MAJOR"] = "high" ✅
```

### Error: Missing `key` field (malformed issue)

```
_fingerprint(): SHA256("" + ...)[:32]  # key is None → str(None or "") = ""
→ fingerprint still computed → partial fingerprint
→ finding ingested with partial key fingerprint
→ log.exception not triggered (no exception thrown)
```

**Coverage:** Primary ✅ | Fallback ✅ | Error ✅

---

## UC-SI-005 — SpotBugs XML Ingestion

**Source:** Requirement (REQ-SI-005)
**Type:** `Requirement`

### Primary Path

```
POST /v1/scan/ingest {tool: "spotbugs", raw_file: spotbugs_report.xml}
  → _parse(adapter, raw_file)
    → fmt == "xml"
    → import xml.etree.ElementTree as ET (stdlib, lazy import)
    → root = ET.fromstring(raw_file)  [state: parsed XML tree]
    → parse_root = "BugCollection/BugInstance"
    → elements = root.findall("BugCollection/BugInstance")
      → returns list of BugInstance Element objects
    → for each elem in elements:
        finding = dict(elem.attrib)
          → {"type": "DM_EXIT", "priority": "1", "rank": "5", "cweid": "670", ...}
        for sl in elem.iter("SourceLine"):
          → finds all SourceLine elements (direct children + nested in Class/Method)
          → check sl.get("primary") == "true" → match first primary one
          → finding["sl_classname"] = "com.example.Foo"
          → finding["sl_start"] = "42"
          → finding["sl_end"] = "45"
          → finding["sl_sourcepath"] = "com/example/Foo.java"
          → break
        lm = elem.find("LongMessage")
          → finding["long_message"] = "Consider using..."
        findings_xml.append(finding)
    → returns [{"type": "DM_EXIT", "priority": "1", "cweid": "670",
               "sl_sourcepath": "com/example/Foo.java", "sl_start": "42", ...}]
  → pre_process = None → skip
  → for each finding_dict:
    → _process_one(adapter, finding_dict, ...)
      → _route() → "scan_findings"
      → _fingerprint() → SHA256("DM_EXIT|com.example.Foo|42")[:32]
      → _map_fields()
        → "type" → rule_id = "DM_EXIT"
        → "priority" → severity = "1"   (raw value, classified next)
        → "rank" → tool_confidence = "5"
        → "category" → check_name = "PERFORMANCE"
        → "cweid" → _cwe_int = "670"
        → "sl_sourcepath" → file_path = "com/example/Foo.java"
        → "sl_start" → line_start = "42"
        → "sl_end" → line_end = "45"
      → _classify_severity() → raw_sev = "1" → severity_map["1"] = "high"
      → _extract_cwe() → cwe_source="extracted", pattern=r"(\d+)"
        → combined includes "_cwe_int" = "670"
        → re.findall(r"(\d+)", "670") → ["670"]
        → m = "670" → isdigit() → append "CWE-670"
        → returns (["CWE-670"], "extracted") ✅
      → _validate() → no cve_id → skip
      → collection = "scan_findings"
      → _plan_edges() → req_src = "rule_engine" → edge planned
      → IngestionBundle(collection="scan_findings", ...)
```

### Fallback: No `primary="true"` SourceLine in BugInstance

```
for sl in elem.iter("SourceLine"):
  → check: sl.get("primary") == "true" → no match for any
  → fallback condition: `not any(s.get("primary") == "true" for s in elem.iter("SourceLine"))`
    → True → use first SourceLine regardless of primary flag
    → finding populated with first SourceLine data
→ file_path and line_start available ✅
```

### Error: Malformed XML (parse failure)

```
ET.fromstring(raw_file)
  → xml.etree.ElementTree.ParseError raised
  → propagates up to IngestionEngine.process()
  → NOT caught by per-finding try/except (parse happens before loop)
  → raises from IngestionEngine.process()
  → EvidenceIngestionService catches and logs → scan_run status = "failed"
```

**Coverage:** Primary ✅ | Fallback ✅ | Error ✅

---

## UC-SI-006 — ZAP Field Map Correction

**Source:** Requirement (REQ-SI-006)
**Type:** `Requirement`

### Primary Path (corrected)

```
POST /v1/scan/ingest {tool: "zap", raw_file: zap_output.json}
  → _parse(adapter, raw_file)
    → _extract_list(data, "site[*].alerts[*]") → list of alert dicts
      → each alert has: {"pluginid": "40018", "url": "https://...", "param": "q", "other": "..."}
  → _fingerprint() → SHA256("40018|https://example.com/page|q")[:32]
    ← uses "url" field (not "uri") ✅
  → _map_fields()
    → "url" → file_path = "https://example.com/page"   ✅ (was "uri" — now correct)
    → "other" → description = "Additional information"  ✅ (was missing)
    → "pluginid" → rule_id = "40018"
    → "alert" → message = "Cross Site Scripting"
    → "cweid" → _cwe_int = "79"
  → _extract_cwe() → combined includes "_cwe_int" = "79"
    → re.findall(r"(\d+)", "79") → ["79"]
    → "CWE-79" ✅
```

**Coverage:** Primary ✅ | Fallback N/A | Error N/A

---

## UC-SI-007 — Checkov Severity Fallback

**Source:** Requirement (REQ-SI-007)
**Type:** `Requirement`

### Primary Path (open-source Checkov, no `--bc-api-key`)

```
POST /v1/scan/ingest {tool: "checkov", raw_file: checkov_output.json}
  → checkov_output["failed_checks"][0]["severity"] = null (open-source mode)
  → _classify_severity()
    → raw_sev = None (severity field absent from finding)
    → sev_map[None] = "medium"   ← changed from None → "medium" ✅
    → returns "medium"
  → doc["severity"] = "medium" (usable for risk prioritization)
```

### Fallback Path (paid Checkov with `--bc-api-key`)

```
checkov_output["failed_checks"][0]["severity"] = "HIGH"
→ _classify_severity() → sev_map["HIGH"] = "high" → "high" (unchanged behavior)
```

**Coverage:** Primary ✅ | Fallback ✅ | Error N/A

---

## UC-SI-DR-001 — pre_process Hook Wiring

**Source:** Design-Risk
**Risk:** `pip_audit_flatten` pre_process is defined but `_parse()` never calls it; pip-audit would process `[full_output_dict]` as a single finding (wrong behavior).
**Expected Outcome:** Engine wires `pre_process` call between `_parse()` and the per-finding loop.

### Primary Path

```
IngestionEngine.process()
  raw_findings = self._parse(adapter, raw_file)
  [NEW] pre_process = adapter.get("pre_process")
  [NEW] if pre_process is not None:
  [NEW]     raw_findings = pre_process(raw_findings)
  for raw in raw_findings:
    → _process_one(...)
```

### Error: pre_process raises exception

```
pre_process(raw_findings) → raises ValueError
→ NOT caught by per-finding try/except (called before the loop)
→ propagates to EvidenceIngestionService → scan_run status = "failed"
→ log.exception emitted ✅
```

**Coverage:** Primary ✅ | Fallback N/A | Error ✅

---

## UC-SI-DR-002 — XML Parse Branch

**Source:** Design-Risk
**Risk:** `xml.etree.ElementTree.fromstring()` is called inline; malformed XML raises `ParseError` before any finding is processed; this must propagate cleanly (not silently swallowed).
**Expected Outcome:** XML parse errors surface at the service layer and mark the scan run as failed.

*(Detailed path covered in UC-SI-005 Error path above.)*

**Coverage:** Error ✅
