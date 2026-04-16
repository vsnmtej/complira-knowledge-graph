# Requirements

**Status:** `Draft`
**Ticket:** `scanner-ingestion-gap-fixes`
**Last Updated:** 2026-03-22

---

## Goal / Problem Statement

The scanner ingestion layer has several verified gaps identified through official documentation cross-checking:

1. **ZAP adapter field map is wrong** — uses `uri` (incorrect) instead of `url`, and `otherinfo` instead of `other` per `AlertAPI.java alertToSet()`. The `zap_instances_fanout` TODO is based on a misunderstanding; there is no `instances` sub-array in ZAP JSON output.
2. **Missing Trivy adapter** — Trivy is a widely-used container/OS/code scanner with a well-defined native JSON format. CweIDs field exists natively. Currently users must re-export as SARIF, losing native fields.
3. **Missing npm-audit adapter** — npm 7+ JSON format uses `vulnerabilities` object keyed by package name. SARIF workaround loses severity and fix metadata.
4. **Missing pip-audit adapter** — `{"dependencies": [...], "fixes": [...]}` structure. CVE aliases available via `--aliases` flag.
5. **Missing SonarQube adapter** — JSON API output format. Dual-path severity required: `impacts[0].severity` (v10+) with fallback to legacy `severity` field.
6. **Missing SpotBugs adapter** — XML output format. Requires XML parse format support in `ingestion_engine.py` (currently raises `NotImplementedError`).
7. **Checkov severity fallback missing** — open-source Checkov (no `--bc-api-key`) emits no severity; `severity_map[None] = None` leaves all findings with `severity: None`, unusable for risk prioritization.

---

## In-Scope Use Cases (Draft)

- UC-SI-001: Ingest Trivy native JSON output — findings route to `component_has_vuln`
- UC-SI-002: Ingest npm-audit JSON output — findings route to `component_has_vuln`
- UC-SI-003: Ingest pip-audit JSON output — findings route to `component_has_vuln`
- UC-SI-004: Ingest SonarQube JSON API output — findings route to `scan_findings`
- UC-SI-005: Ingest SpotBugs XML output — findings route to `scan_findings`
- UC-SI-006: ZAP ingestion uses correct field names (`url`, `other`)
- UC-SI-007: Checkov open-source mode produces usable severity fallback

---

## Acceptance Criteria (Draft)

- AC-SI-001: Trivy adapter normalizes `VulnerabilityID` → `cve_id`, `Severity` → severity, `CweIDs` → `cwe_ids`, routes to `component_has_vuln`
- AC-SI-002: npm-audit adapter fingerprints on `["name", "range"]`, routes to `component_has_vuln`
- AC-SI-003: pip-audit adapter handles `dependencies[*].vulns[*]` structure, `aliases` → CVE extraction
- AC-SI-004: SonarQube adapter maps `impacts[0].severity` first, falls back to `severity` for pre-v10
- AC-SI-005: SpotBugs adapter parses `BugCollection/BugInstance` XML, `priority` → severity (1→high, 2→medium, 3→low, 4→info)
- AC-SI-006: XML parse format implemented in `ingestion_engine._parse()` for SpotBugs
- AC-SI-007: ZAP adapter field map corrected: `url` (not `uri`), `other` (not `otherinfo`), `zap_instances_fanout` TODO removed
- AC-SI-008: Checkov `severity_map[None]` changed from `None` to `"medium"`
- AC-SI-009: All new adapters pass `_validate_registry()` structural validation
- AC-SI-010: Existing adapter tests continue to pass (no regression)

---

## Constraints / Dependencies

- `adapter_registry.py` is the single config layer — no engine logic changes for JSON adapters
- SpotBugs XML requires `ingestion_engine.py` change (XML parse branch)
- SonarQube dual-path severity requires either: (a) a pre_process hook or (b) a new `severity_source` field in the adapter; decision pending investigation
- `_validate_registry()` must accept new adapters without structural changes
- All new SCA adapters must use `location_anchor: "purl"` and `result_routing: {"*": "component_has_vuln"}` consistent with grype
- No backward compatibility paths — clean implementation only

---

## Assumptions (Draft)

- SonarQube target is the Web API JSON format (`/api/issues/search`), not XML file export
- npm-audit target is npm 7+ format (v2 report with `vulnerabilities` object); npm 6 (`advisories`) is out of scope
- pip-audit `--aliases` flag is assumed enabled for CVE extraction from `aliases[]`
- SpotBugs XML generated with `addMessages=true` (needed for `cweid` attribute on `BugInstance`)
- Trivy output is `--format json` (default), targeting `Results[*].Vulnerabilities[*]`

---

## Open Questions / Risks (Draft)

- How does the SonarQube dual-path severity mapping work in the current adapter config model? Does `field_map` support fallback paths, or does it require a `pre_process` hook?
- Does `_extract_list()` support `".*"` dict-value expansion needed for npm-audit `vulnerabilities` object?
- What does `_validate_registry()` check exactly — will new `ParseFormat` literal values need updating?
- Is `cweid` attribute available on `BugInstance` without `addMessages=true` in SpotBugs?
