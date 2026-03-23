# Proposed Design — scanner-ingestion-gap-fixes

**Version:** v1
**Status:** Design-ready
**Last Updated:** 2026-03-22

---

## 1. Current State (As-Is)

- `adapter_registry.py` contains 8 adapters. ZAP adapter has `"uri"` (wrong) and no `"other"` mapping. Checkov `severity_map[None] = None`.
- `ingestion_engine._parse()` raises `NotImplementedError` for `parse_format="xml"`.
- No adapters for: Trivy, npm-audit, pip-audit, SonarQube, SpotBugs.
- Tests assert `len(ADAPTER_REGISTRY) >= 8` and enumerate exactly 8 expected tools.

---

## 2. Target State (To-Be)

- `adapter_registry.py` contains 13 adapters (8 existing + 5 new). ZAP corrected. Checkov fallback is `"medium"`.
- `ingestion_engine._parse()` handles `parse_format="xml"` via stdlib `xml.etree.ElementTree`.
- XML-to-flat-dict flattening: element attributes + primary SourceLine child injected as `sl_*` prefixed keys.
- Tests updated for 13 adapters.

---

## 3. Architecture Direction

**Decision: Keep existing architecture shape. Add XML parse branch to engine. Add 5 adapter configs.**

Rationale:
- The adapter-registry + engine separation is the right architecture — all tool variation is config, engine is invariant.
- XML tools need a new parse branch in the engine (unavoidable — XML is structurally different from JSON).
- The XML-to-flat-dict conversion belongs in the engine parse step, controlled by a standard flattening strategy.
- No new layers, modules, or boundary interfaces needed.
- No alternatives: extracting XML parsing to a separate module would be premature abstraction for one parse format.

**Layering check:** Change stays entirely within the ingestion layer's config + parse step. No cross-layer impact.

---

## 4. Change Inventory

| # | File | Change Type | Description |
|---|---|---|---|
| C-01 | `src/complira_graph/ingestion/adapter_registry.py` | Modify | Fix ZAP field map: `uri`→`url`, add `other`→`description`, remove fanout TODO |
| C-02 | `src/complira_graph/ingestion/adapter_registry.py` | Modify | Checkov `severity_map[None]` = `"medium"` |
| C-03 | `src/complira_graph/ingestion/adapter_registry.py` | Add | Trivy adapter (SCA, `component_has_vuln`, `tool_direct` CWE) |
| C-04 | `src/complira_graph/ingestion/adapter_registry.py` | Add | npm-audit adapter (SCA, `component_has_vuln`, `pre_process` for structure) |
| C-05 | `src/complira_graph/ingestion/adapter_registry.py` | Add | pip-audit adapter (SCA, `component_has_vuln`, `pre_process` for CVE hoist) |
| C-06 | `src/complira_graph/ingestion/adapter_registry.py` | Add | SonarQube adapter (SAST, `scan_findings`, dual-path severity via field_map order) |
| C-07 | `src/complira_graph/ingestion/adapter_registry.py` | Add | SpotBugs adapter (SAST, `scan_findings`, `parse_format="xml"`) |
| C-08 | `src/complira_graph/ingestion/ingestion_engine.py` | Add | XML parse branch in `_parse()` using `xml.etree.ElementTree` |
| C-09 | `tests/unit/ingestion/test_adapter_registry.py` | Modify | Update expected tool set; add per-adapter config tests for 5 new adapters |

---

## 5. File/Module Specifications

### C-01+C-02: ZAP fix + Checkov fix (`adapter_registry.py`)

**ZAP changes:**
- `fingerprint_fields`: `["pluginid", "uri", "param"]` → `["pluginid", "url", "param"]`
- `field_map`: remove `"uri": "file_path"`, add `"url": "file_path"` and `"other": "description"`
- `pre_process`: `None  # TODO: zap_instances_fanout` → `None` (comment removed)

**Checkov change:**
- `severity_map[None]`: `None` → `"medium"`

---

### C-03: Trivy adapter

```python
"trivy": {
    "tool_name":            "trivy",
    "parse_format":         "json_object",
    "parse_root":           "Results[*].Vulnerabilities[*]",
    "multi_root":           [],
    "fingerprint_fields":   ["VulnerabilityID", "Target", "PkgName"],
    "severity_map": {
        "CRITICAL": "critical", "HIGH":    "high",
        "MEDIUM":   "medium",   "LOW":     "low",
        "UNKNOWN":  None,
    },
    "default_finding_type": "sca",
    "result_routing":       {"*": "component_has_vuln"},
    "result_state_field":   None,
    "location_anchor":      "purl",
    "field_map": {
        "VulnerabilityID":   "cve_id",
        "Severity":          "severity",
        "Title":             "rule_id",
        "Description":       "description",
        "FixedVersion":      "fix_guidance",
        "PrimaryURL":        "references",
        "PkgName":           "component_name",
        "InstalledVersion":  "component_version",
        "Target":            "file_path",       # container layer or package type
        "CweIDs":            "_cwe_raw",
    },
    "cwe_source":               "tool_direct",
    "cwe_extract_pattern":      None,
    "req_mapping_source":       "none",
    "deterministic_req_fields": [],
    "secret_raw_field":         None,
    "pre_process":              None,
}
```

**Note:** `purl` field will be `None` for Trivy findings (Trivy doesn't emit purl directly). `component_name` + `component_version` are set. EvidenceEdgeService handles `component_has_vuln` routing from either purl or name+version.

---

### C-04: npm-audit adapter

**Pre-process function `npm_audit_inject_name`:**
```python
def npm_audit_inject_name(findings: list[dict]) -> list[dict]:
    """
    npm-audit v2: vulnerabilities object keyed by package name.
    The engine's _extract_list("vulnerabilities.*[]") flattens values,
    but the package name (key) is already present as 'name' in each value.
    No structural injection needed — name is already in the finding dict.
    This hook is a no-op placeholder for future v1/v2 format detection.
    """
    return findings
```

Actually — `name` IS present in each vulnerability value (confirmed from `vuln.js toJSON()`). No pre_process needed.

```python
"npm_audit": {
    "tool_name":            "npm_audit",
    "parse_format":         "json_object",
    "parse_root":           "vulnerabilities.*[]",
    "multi_root":           [],
    "fingerprint_fields":   ["name", "range"],
    "severity_map": {
        "critical": "critical", "high":     "high",
        "moderate": "medium",   "low":      "low",
        "info":     "info",     None:       None,
    },
    "default_finding_type": "sca",
    "result_routing":       {"*": "component_has_vuln"},
    "result_state_field":   None,
    "location_anchor":      "purl",
    "field_map": {
        "name":         "component_name",
        "severity":     "severity",
        "range":        "description",
        "isDirect":     "tool_confidence",
    },
    "cwe_source":               "absent",
    "cwe_extract_pattern":      None,
    "req_mapping_source":       "none",
    "deterministic_req_fields": [],
    "secret_raw_field":         None,
    "pre_process":              None,
}
```

**Note on CWE:** `via[0].cwe` could contain CWE data in advisory objects, but `via` is a heterogeneous array (strings + objects). Attempting `via[0].cwe` via `_get_field` would fail if `via[0]` is a string. Safe choice: `cwe_source: "absent"`. Future enhancement can add pre_process for CWE extraction from `via` entries.

---

### C-05: pip-audit adapter

**Pre-process function `pip_audit_hoist_cve`:**
```python
def pip_audit_hoist_cve(findings: list[dict]) -> list[dict]:
    """
    pip-audit: id is PYSEC-YYYY-NNN format; CVE IDs are in aliases[].
    Hoists first CVE-format alias as cve_id before engine mapping.
    """
    for finding in findings:
        aliases = finding.get("aliases") or []
        for alias in aliases:
            if re.match(r"^CVE-\d{4}-\d{4,}$", alias, re.IGNORECASE):
                finding["cve_id"] = alias
                break
    return findings
```

```python
"pip_audit": {
    "tool_name":            "pip_audit",
    "parse_format":         "json_object",
    "parse_root":           "dependencies[*].vulns[*]",
    "multi_root":           [],
    "fingerprint_fields":   ["id", "name"],    # "name" injected by pre_process context
    "severity_map":         {None: None},       # pip-audit has no severity ratings
    "default_finding_type": "sca",
    "result_routing":       {"*": "component_has_vuln"},
    "result_state_field":   None,
    "location_anchor":      "purl",
    "field_map": {
        "id":           "tool_vuln_id",
        "cve_id":       "cve_id",              # hoisted by pre_process
        "description":  "description",
        "fix_versions": "fix_guidance",
    },
    "cwe_source":               "absent",
    "cwe_extract_pattern":      None,
    "req_mapping_source":       "none",
    "deterministic_req_fields": [],
    "secret_raw_field":         None,
    "pre_process":              pip_audit_hoist_cve,
}
```

**Problem:** `parse_root = "dependencies[*].vulns[*]"` extracts vuln objects, but they don't have the package `name`. The `name` is on the parent dependency, not on each vuln. Fingerprinting with `["id", "name"]` won't work — `name` is not in the vuln dict.

**Solution:** Use `pre_process` to denormalize: before engine parse, flatten `dependencies[*]` into a list of vulns with `name` and `version` injected from parent.

**Revised pre_process `pip_audit_flatten`:**
```python
def pip_audit_flatten(raw_data: dict) -> list[dict]:
    """
    pip-audit: flatten dependencies[*].vulns[*] into a flat list,
    injecting parent name/version into each vuln dict.
    Also hoist first CVE-format alias as cve_id.
    """
    flat = []
    for dep in raw_data.get("dependencies", []):
        name = dep.get("name", "")
        version = dep.get("version", "")
        for vuln in dep.get("vulns", []):
            entry = dict(vuln)
            entry["pkg_name"] = name
            entry["pkg_version"] = version
            # Hoist CVE from aliases
            for alias in entry.get("aliases") or []:
                if re.match(r"^CVE-\d{4}-\d{4,}$", alias, re.IGNORECASE):
                    entry["cve_id"] = alias
                    break
            flat.append(entry)
    return flat
```

**But:** `pre_process` signature per `ToolAdapter` is `Callable[[list[dict]], list[dict]]` — takes a list of pre-parsed finding dicts, not the raw file. The engine calls `pre_process` AFTER `_parse()`, not before.

**Problem:** `_parse()` extracts `dependencies[*].vulns[*]` first (losing parent context), then `pre_process` runs on the extracted vuln list (no parent context anymore).

**Design Decision: Use `parse_root = None` + `pre_process` for pip-audit.**

Set `parse_root = None` so `_parse()` returns `[full_json_object]` (the whole pip-audit output as one dict). Then `pre_process` receives `[full_output_dict]` and flattens it into individual findings with parent context injected.

```python
"pip_audit": {
    "parse_format":  "json_object",
    "parse_root":    None,           # don't extract; let pre_process handle flattening
    "pre_process":   pip_audit_flatten,  # receives [full_output], returns [flat_vuln_dicts]
    "fingerprint_fields": ["id", "pkg_name"],
    ...
}
```

**But again:** `pre_process` is called AFTER `_parse()` in the engine (currently NOT called at all — it's defined but never invoked). We need to wire `pre_process` into the engine.

**Engine wiring:** After `_parse()` returns `raw_findings`, check if `adapter.get("pre_process")` is set and call it:
```python
raw_findings = self._parse(adapter, raw_file)
pre_process = adapter.get("pre_process")
if pre_process is not None:
    raw_findings = pre_process(raw_findings)
```

This enables both pip-audit (full-output flattening) and any future pre_process needs.

**Final pip-audit design:**
- `parse_root = None` → `_parse()` returns `[full_json_object]`
- `pre_process = pip_audit_flatten` → flattens to `[{id, pkg_name, pkg_version, cve_id?, description, fix_versions}, ...]`
- `fingerprint_fields = ["id", "pkg_name"]`

---

### C-06: SonarQube adapter

```python
"sonarqube": {
    "tool_name":            "sonarqube",
    "parse_format":         "json_object",
    "parse_root":           "issues",
    "multi_root":           [],
    "fingerprint_fields":   ["key"],
    "severity_map": {
        # Legacy severity (pre-v10): BLOCKER/CRITICAL/MAJOR/MINOR/INFO
        "BLOCKER":  "critical",
        "CRITICAL": "critical",
        "MAJOR":    "high",
        "MINOR":    "low",
        "INFO":     "info",
        # Modern severity (v10+, from impacts[0].severity): HIGH/MEDIUM/LOW
        "HIGH":     "high",
        "MEDIUM":   "medium",
        "LOW":      "low",
        None:       None,
    },
    "default_finding_type": "sast",
    "result_routing":       {"*": "scan_findings"},
    "result_state_field":   None,
    "location_anchor":      "file_line",
    "field_map": {
        # Legacy fields first, modern fields second (overwrite pattern)
        "severity":              "severity",   # pre-v10 fallback
        "rule":                  "rule_id",
        "message":               "message",
        "component":             "file_path",
        "line":                  "line_start",
        "key":                   "tool_vuln_id",
        "type":                  "check_name",
        # Modern: impacts[0].severity overwrites legacy severity if present
        "impacts[0].severity":   "severity",
    },
    "cwe_source":               "extracted",
    "cwe_extract_pattern":      r"(CWE-\d+)",
    "req_mapping_source":       "rule_engine",
    "deterministic_req_fields": [],
    "secret_raw_field":         None,
    "pre_process":              None,
}
```

**Note:** `_get_field(raw, "impacts[0].severity")` — this path uses array indexing `[0]`, which `_get_field` handles via bracket parsing (line 71-76 of engine). `impacts` is a list, `impacts[0]` gets first element, `.severity` gets the field. ✅

---

### C-07: SpotBugs adapter

```python
"spotbugs": {
    "tool_name":            "spotbugs",
    "parse_format":         "xml",
    "parse_root":           "BugCollection/BugInstance",   # XPath for ElementTree.findall
    "multi_root":           [],
    "fingerprint_fields":   ["type", "sl_classname", "sl_start"],
    "severity_map": {
        "1": "high",
        "2": "medium",
        "3": "low",
        "4": "info",
        None: None,
    },
    "default_finding_type": "sast",
    "result_routing":       {"*": "scan_findings"},
    "result_state_field":   None,
    "location_anchor":      "file_line",
    "field_map": {
        "type":         "rule_id",
        "priority":     "severity",
        "rank":         "tool_confidence",
        "category":     "check_name",
        "cweid":        "_cwe_int",
        "sl_sourcepath": "file_path",
        "sl_start":     "line_start",
        "sl_end":       "line_end",
        "sl_classname": "description",
    },
    "cwe_source":               "extracted",
    "cwe_extract_pattern":      r"(\d+)",    # cweid is a raw integer string
    "req_mapping_source":       "rule_engine",
    "deterministic_req_fields": [],
    "secret_raw_field":         None,
    "pre_process":              None,
}
```

---

### C-08: XML parse branch in `ingestion_engine._parse()`

```python
if fmt == "xml":
    import xml.etree.ElementTree as ET
    root = ET.fromstring(raw_file)
    parse_root_path: str = adapter.get("parse_root") or ""
    elements = root.findall(parse_root_path) if parse_root_path else [root]
    findings_xml: list[dict] = []
    for elem in elements:
        finding = dict(elem.attrib)          # all XML attributes as flat keys
        # Inject primary SourceLine child as sl_* keys
        for sl in elem.iter("SourceLine"):
            if sl.get("primary") == "true" or not any(
                s.get("primary") == "true" for s in elem.iter("SourceLine")
            ):
                finding["sl_classname"] = sl.get("classname", "")
                finding["sl_start"]     = sl.get("start", "")
                finding["sl_end"]       = sl.get("end", "")
                finding["sl_sourcepath"] = sl.get("sourcepath", "")
                break
        # Inject LongMessage text if present
        lm = elem.find("LongMessage")
        if lm is not None and lm.text:
            finding["long_message"] = lm.text.strip()
        findings_xml.append(finding)
    return findings_xml
```

**Import placement:** `import xml.etree.ElementTree as ET` inside the branch avoids adding a top-level import for a format used only by SpotBugs. This is idiomatic for rarely-needed stdlib modules.

---

### C-09: Test updates (`test_adapter_registry.py`)

- `test_all_expected_tools_present`: add `"trivy", "npm_audit", "pip_audit", "sonarqube", "spotbugs"` to expected set
- Add `TestTrivyAdapterConfig`, `TestNpmAuditAdapterConfig`, `TestPipAuditAdapterConfig`, `TestSonarqubeAdapterConfig`, `TestSpotBugsAdapterConfig` classes with targeted config assertions
- `TestZapAdapterConfig`: assert `"url"` in fingerprint_fields (not `"uri"`); assert `"url"` in field_map; assert `"other"` in field_map
- `TestCheckovAdapterConfig`: add assertion that `severity_map[None] == "medium"`

---

## 6. Naming Decisions

| Name | Rationale |
|---|---|
| `trivy` | Matches tool binary name (consistent with `grype`, `semgrep`) |
| `npm_audit` | Underscore matches Python identifier convention; avoids `npm-audit` with hyphen |
| `pip_audit` | Same underscore convention as `npm_audit` |
| `sonarqube` | Single word, matches tool name |
| `spotbugs` | Single word, matches tool name (not `spot_bugs`) |
| `sl_classname`, `sl_start`, `sl_end`, `sl_sourcepath` | `sl_` prefix = SourceLine; avoids collision with top-level `classname` attributes |
| `pip_audit_flatten` | Action verb + tool name; clear function purpose |

---

## 7. Naming Drift Check

| Module/API | Current Name | Drift? | Action |
|---|---|---|---|
| `adapter_registry.py` | unchanged | No | N/A |
| `ingestion_engine.py` | unchanged | No | N/A |
| `test_adapter_registry.py` | unchanged | No | N/A |

No naming drift. All new names are additive.

---

## 8. Dependency Flow

```
adapter_registry.py
  └── ingestion_engine.py (imports ADAPTER_REGISTRY, ToolAdapter)
       └── xml.etree.ElementTree (stdlib, import-on-demand in XML branch)

pip_audit_flatten (defined in adapter_registry.py, referenced in adapter config)
```

No cycles. No new cross-module dependencies.

---

## 9. Use-Case Coverage Matrix

| use_case_id | Primary | Fallback | Error | Call Stack UC |
|---|---|---|---|---|
| UC-SI-001 Trivy ingest | Yes | Yes | Yes | UC-SI-001 |
| UC-SI-002 npm-audit ingest | Yes | Yes | Yes | UC-SI-002 |
| UC-SI-003 pip-audit ingest | Yes | Yes | Yes | UC-SI-003 |
| UC-SI-004 SonarQube ingest | Yes | Yes | Yes | UC-SI-004 |
| UC-SI-005 SpotBugs ingest | Yes | Yes | Yes | UC-SI-005 |
| UC-SI-006 ZAP field correction | Yes | N/A | N/A | UC-SI-006 |
| UC-SI-007 Checkov severity fallback | Yes | N/A | N/A | UC-SI-007 |
| UC-SI-DR-001 pre_process hook wiring | N/A | N/A | Yes | UC-SI-DR-001 |
| UC-SI-DR-002 XML parse branch | Yes | N/A | Yes | UC-SI-DR-002 |
