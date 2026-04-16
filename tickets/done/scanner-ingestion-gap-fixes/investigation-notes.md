# Investigation Notes

**Ticket:** `scanner-ingestion-gap-fixes`
**Last Updated:** 2026-03-22

---

## Sources Consulted

| Source | Type | Relevance |
|---|---|---|
| `src/complira_graph/ingestion/adapter_registry.py` | Local file | Full adapter config structure, all 8 existing adapters |
| `src/complira_graph/ingestion/ingestion_engine.py` | Local file | _parse(), _map_fields(), _classify_severity(), _extract_cwe() |
| `tests/unit/ingestion/test_adapter_registry.py` | Local file | Test patterns, validation expectations |
| `AlertAPI.java alertToSet()` (ZAP GitHub) | Official source | Confirmed ZAP field names: `url`, `other`, `cweid`, `pluginid` |
| `vulnerability.go` + `report.go` (Trivy GitHub) | Official source | Confirmed Trivy field names: `VulnerabilityID`, `PkgName`, `InstalledVersion`, `CweIDs`, `Severity` |
| `arborist/vuln.js toJSON()` (npm CLI GitHub) | Official source | Confirmed npm v2 format: `vulnerabilities.*`, `name`, `severity`, `via`, `range` |
| `pip_audit/_format/json.py` (pypa GitHub) | Official source | Confirmed pip-audit structure: `{"dependencies": [...], "fixes": [...]}` |
| `SearchAction.java` (SonarQube GitHub) | Official source | Confirmed fields: `rule`, `severity` (deprecated v10+), `impacts[0].severity` (modern) |
| `BugInstance.java writeXML()` (SpotBugs GitHub) | Official source | Confirmed XML: `BugCollection/BugInstance[@type,@priority,@rank,@cweid]` |

---

## Key Findings

### Finding 1 — ZAP adapter has 2 wrong field names + 1 stale TODO

**Files:** `adapter_registry.py` lines 391, 407, 418

**Bugs confirmed:**
- `fingerprint_fields: ["pluginid", "uri", "param"]` — `"uri"` does not exist in ZAP JSON; correct field is `"url"` (`alertToSet()`: `"url": alert.getUri().toString()`)
- `field_map["uri"] = "file_path"` — must become `field_map["url"] = "file_path"`
- `"alert"` maps to `"message"` ✅ (correct per `alertToSet()`)
- `"other"` field exists in ZAP output (maps to `otherInfo` context) — currently NOT mapped; should add `"other": "description"`
- `pre_process: None  # TODO: zap_instances_fanout` — this TODO is wrong; ZAP JSON has no `instances` sub-array. The `alertsByRisk` grouped view produces a flat list of child alerts; there is no nested instances structure to fan out.

**Fix:** 2 lines changed in `adapter_registry.py`, 1 comment removed.

---

### Finding 2 — Checkov `severity_map[None] = None` causes all open-source findings to have `severity: None`

**Files:** `adapter_registry.py` line 246

**Current:** `None: None` — open-source Checkov (no `--bc-api-key`) always produces `severity: null`
**Fix:** Change to `None: "medium"` — conservative default, consistent with how security posture tools handle unknown severity.

---

### Finding 3 — Trivy adapter: all field names confirmed, `CweIDs` natively available

**Official struct fields confirmed from `vulnerability.go`:**
- `VulnerabilityID` — CVE identifier
- `PkgName` — package name
- `InstalledVersion` — installed version string
- `FixedVersion` — fix version string
- `Severity` — string: `UNKNOWN/LOW/MEDIUM/HIGH/CRITICAL`
- `Title` — short description
- `Description` — long description
- `PrimaryURL` — canonical reference URL
- `CweIDs` — `[]string` list of `"CWE-N"` values ← **directly usable as `cwe_source: "tool_direct"`**
- `Target` — result target (container layer, package type)

**parse_root:** `"Results[*].Vulnerabilities[*]"` — `_extract_list()` handles two-level `[*]` expansion ✅
**Routing:** `component_has_vuln` (same as grype)
**CWE:** `tool_direct`, map `"CweIDs": "_cwe_raw"`, `_normalise_cwe_values()` handles `[]string`

---

### Finding 4 — npm-audit: `vulnerabilities` is an object; `_extract_list(".*[]")` handles it

**Official format (npm 7+ / arborist):**
```json
{
  "vulnerabilities": {
    "package-name": {
      "name": "package-name",
      "severity": "high",
      "isDirect": true,
      "via": [...advisories],
      "effects": [...],
      "range": ">=1.0.0 <2.3.4",
      "nodes": ["node_modules/package-name"],
      "fixAvailable": true
    }
  }
}
```

**Engine support:** `_extract_list("vulnerabilities.*[]")` — the `".*[]"` branch flattens all dict values. Since each value is a dict (not a list), it gets wrapped in `[v]`. Result: list of vulnerability dicts. ✅

**`via[]` structure:** Each entry is either a string (transitive dep name) or an advisory object with `{source, name, dependency, title, url, severity, cwe, cvss, range}`. The `cwe` field in advisory objects exists — extractable via CWE regex on `via[0].title` or as `extracted` from description.

**Fingerprint:** `["name", "range"]` — `name` is the package, `range` is the affected version range. `via[0].source` (numeric advisory ID) is less stable. Confirmed: `name` and `range` are both present in `toJSON()`.

---

### Finding 5 — pip-audit: `id` is PYSEC format; CVE in `aliases[]`

**Official format (pip-audit `_format/json.py`):**
```json
{
  "dependencies": [
    {
      "name": "package",
      "version": "1.2.3",
      "vulns": [
        {
          "id": "PYSEC-2019-179",
          "fix_versions": ["1.0"],
          "aliases": ["CVE-2019-1010083"],
          "description": "..."
        }
      ]
    }
  ],
  "fixes": [...]
}
```

**parse_root:** `"dependencies[*].vulns[*]"` — engine `_extract_list()` handles two-level `[*]` expansion ✅
**CVE extraction:** `id` is `PYSEC-YYYY-NNN`, not CVE format. CVE IDs are in `aliases[]`. Strategy: map `id` → `tool_vuln_id` directly; use `extracted` CWE source + regex on `description`; add `pre_process` to hoist CVE from `aliases[0]` into a `cve_id` field before engine processing.
**Severity:** pip-audit does NOT emit severity — all findings are unrated. Use `severity_map: {None: None}` (severity stays null — different from Checkov because pip-audit severity absence is accurate; Checkov severity absence is a tooling limitation).

---

### Finding 6 — SonarQube: dual-path severity via field_map ordering

**Official fields (SearchAction.java):**
- `rule` — rule key (e.g. `java:S1134`)
- `severity` — `BLOCKER/CRITICAL/MAJOR/MINOR/INFO` (deprecated v10+, still present)
- `impacts[0].severity` — `HIGH/MEDIUM/LOW` (modern v10+)
- `impacts[0].softwareQuality` — `SECURITY/RELIABILITY/MAINTAINABILITY`
- `component` — `project:src/Foo.java`
- `line` — integer line number
- `message` — issue text
- `key` — unique issue key (use as fingerprint)
- `type` — `BUG/VULNERABILITY/CODE_SMELL` (deprecated v10+)

**Dual-path severity strategy:** Python dict insertion order is preserved (3.7+). In `field_map`, list legacy `severity` first, then `impacts[0].severity` second. `_map_fields()` iterates in order and overwrites:
- Pre-v10: `severity` field exists → maps; `impacts` absent → no overwrite. Legacy severity preserved ✅
- v10+: both fields exist → legacy writes first, `impacts[0].severity` overwrites second with modern value ✅

**`_classify_severity()`** then maps via `severity_map`:
- Legacy: `"BLOCKER"→"critical"`, `"CRITICAL"→"critical"`, `"MAJOR"→"high"`, `"MINOR"→"low"`, `"INFO"→"info"`
- Modern: `"HIGH"→"high"`, `"MEDIUM"→"medium"`, `"LOW"→"low"`
Both need to be in the same `severity_map` dict.

**Fingerprint:** `["key"]` — issue key is globally unique in SonarQube ✅

**`component` field** format: `"project:src/main/java/Foo.java"` — need to strip project prefix before storing as `file_path`. Strategy: use `pre_process` hook `sonarqube_strip_component_prefix` to normalize component → just the path portion, OR accept full value and document the format.

Decision: **no pre_process** — store full `component` value as `file_path` and document the format. SonarQube-consuming code can strip the project prefix when needed. Avoids pre_process complexity.

---

### Finding 7 — SpotBugs XML requires engine change in `_parse()`

**Official XML confirmed (BugInstance.java writeXML()):**
```xml
<BugCollection>
  <BugInstance type="..." priority="1" rank="..." abbrev="..." category="..." cweid="79">
    <ShortMessage>...</ShortMessage>
    <LongMessage>...</LongMessage>
    <Class classname="com.example.Foo" primary="true">
      <SourceLine classname="..." start="42" end="45" sourcepath="com/example/Foo.java"/>
    </Class>
    <Method ...>
      <SourceLine .../>
    </Method>
    <SourceLine classname="..." start="42" end="45" sourcepath="com/example/Foo.java" primary="true"/>
  </BugInstance>
</BugCollection>
```

**Key decisions:**
- `cweid` attribute is only present with `addMessages=true` (explicitly noted in source: "only when addMessages=true AND cweid != 0")
- `priority` attribute: `1=High, 2=Normal, 3=Low, 4=Experimental` — map to `critical/high/medium/low/info`... wait: priority 1=High, 2=Normal(medium), 3=Low, 4=Experimental(info). There is no "critical" in SpotBugs priority.
- `SourceLine` child with `primary="true"` is the canonical location. For XML parsing, we'll use the first `SourceLine` with `primary="true"` or the direct child `SourceLine` of `BugInstance`.
- Fingerprint: `["type", "@classname_primary", "@start_primary"]` — needs XML-level extraction

**XML parse implementation:**
- Use `xml.etree.ElementTree` (stdlib, no extra deps)
- `parse_root` for XML adapters: XPath string (`"BugCollection/BugInstance"`)
- `_parse()` XML branch: `root = ET.fromstring(raw_file)`, `elements = root.findall(parse_root)`, convert each Element to dict (attributes + child text)
- XML-to-dict conversion: flatten attributes as top-level keys; child elements with text as `element_tag: element_text`; child `SourceLine` with `primary="true"` as `source_line_start`, `source_line_path`

**Critical design decision:** XML adapters need a different extraction model than JSON adapters because XML has attributes, child elements, and nested structure. Two options:
1. **Convert element to flat dict** (attributes + selected children) in the engine, then let `_map_fields` work normally using the flattened dict keys
2. **Pre_process hook** that converts XML Element objects to dicts before engine processing

Option 1 is cleaner — define a standard XML-to-flat-dict conversion in the engine, controlled by an optional `xml_child_maps` config in the adapter. But this adds a new required adapter key for XML tools.

Simpler option: standard flattening that:
- Includes all XML attributes as keys (e.g. `type`, `priority`, `rank`, `cweid`)
- Includes `SourceLine` child: finds first one with `primary="true"`, injects `sl_start`, `sl_end`, `sl_sourcepath`, `sl_classname` as flat keys

This makes field_map clean: `"type": "rule_id"`, `"priority": "severity"`, `"sl_sourcepath": "file_path"`, `"sl_start": "line_start"`, `"sl_end": "line_end"`, `"cweid": "_cwe_int"`

---

### Finding 8 — `_extract_list()` multi-level `[*]` support confirmed

Both `"Results[*].Vulnerabilities[*]"` (Trivy) and `"dependencies[*].vulns[*]"` (pip-audit) use the `"[*]." in path` branch in `_extract_list()` (line 126). This recursively handles two levels of array expansion. ✅

---

## Scope Triage

**Classification: Medium**

Signals:
- 2 source files modified (`adapter_registry.py`, `ingestion_engine.py`)
- 1 test file updated (`test_adapter_registry.py`)
- Novel behavior: XML parse format branch in engine (new code path, requires design)
- 6 new adapters — substantial new config but no engine logic changes for 5 of them
- SonarQube dual-path severity requires a careful field_map ordering design decision
- No API changes, no schema changes, no pipeline changes

Medium depth: proposed design doc required for XML engine change + multi-adapter config design.

---

## Constraints / Implications for Design

1. **Zero new dependencies** — XML via `xml.etree.ElementTree` (stdlib); no lxml, no xmltodict
2. **Zero engine changes for JSON adapters** — Trivy, npm-audit, pip-audit, SonarQube: adapter config only
3. **One engine change required** — XML parse branch for SpotBugs; standard attribute+SourceLine flattening
4. **field_map dict order matters for SonarQube** — Python 3.7+ insertion order is preserved; legacy first, modern second
5. **`_validate_registry()` unchanged** — new adapters need same required keys; `ParseFormat` Literal already includes `"xml"` (line 37) ✅
6. **Test `test_all_expected_tools_present`** hardcodes `{"semgrep", ..., "sarif"}` (8 tools) — will need updating to include new tools, or the assertion style needs changing
7. **`test_registry_is_not_empty`** asserts `>= 8` — still passes with more tools ✅
8. **pip-audit severity**: all-null is correct behavior (pip-audit provides no severity ratings); severity_map should NOT default to "medium" unlike Checkov

---

## Open Questions Resolved

| Question | Resolution |
|---|---|
| Does `_extract_list()` handle `vulnerabilities.*[]` for npm-audit? | Yes — `".*[]"` branch flattens all dict values ✅ |
| Does `_validate_registry()` need updating for new ParseFormat values? | No — `ParseFormat` Literal already includes `"xml"` and `"csv"` (line 37) ✅ |
| Is `cweid` available without `addMessages=true` in SpotBugs? | No — only with `addMessages=true`. Adapter must document this requirement. |
| SonarQube dual-path severity: pre_process or field_map ordering? | field_map ordering (legacy first, modern second). Simpler, no pre_process needed. |
| npm-audit: `via[0].source` as fingerprint? | Wrong — `via[0].source` is a numeric advisory ID, not a stable key. Use `["name", "range"]`. |
| pip-audit CVE extraction: pre_process or mapping? | pre_process `pip_audit_hoist_cve` to scan `aliases[]` for CVE-format ID and set `cve_id`. |
