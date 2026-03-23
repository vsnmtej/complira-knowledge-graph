"""
Canonical Data Model + Typed Adapter Registry for Complira's multi-tool ingestion layer.

Design principle
----------------
Each scanner tool has a different output format, field vocabulary, severity
scale, and fingerprint formula. The 9 operations required to normalise any
tool's output into a canonical scan_finding document are INVARIANT. What
varies is the *configuration* supplied to those operations.

Adding a new tool = one new entry in ADAPTER_REGISTRY. No engine code changes.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Literal, Optional

try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict  # type: ignore


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

ToolName = str
FieldPath = str       # dot-path into raw finding: "check_result.result"
CanonicalField = str  # field name on scan_findings document

ParseFormat = Literal[
    "json_array",   # [{...}, {...}]
    "json_lines",   # one JSON object per line (trufflehog)
    "json_object",  # single root object with nested arrays (semgrep, checkov)
    "sarif",        # OASIS SARIF 2.1
    "xml",          # JUnit / checkstyle
    "csv",          # CSV with header row
    "graphql",      # Wiz: paginated GraphQL response
]

CollectionTarget = Literal[
    "scan_findings",      # SAST / IaC / DAST / CSPM / firmware findings
    "detected_controls",  # positive evidence (Checkov PASSED, Semgrep control hits)
    "component_has_vuln", # SCA CVE hits → component edge, not scan_findings
    "audit_log",          # suppressed / skipped — appended to scan_run.audit_log
    "drop",               # discard entirely
]

CweSource = Literal[
    "tool_direct",  # tool emits CWE-N code directly → deterministic edge
    "extracted",    # regex from description → deterministic
    "absent",       # tool never emits CWE → trigger llm_classifier
]

ReqMappingSource = Literal[
    "rule_engine",      # CWE → SCF crosswalk → deterministic
    "checkov_native",   # bc_check_id lookup → deterministic
    "wiz_native",       # securitySubCategories array → deterministic
    "llm_reg_mapper",   # no deterministic path → probabilistic, confidence required
    "iam_reg_mapper",   # IAM permission → regulatory requirement (Layer 3, reserved)
    "none",             # SCA / secret tools: req mapping not applicable
]

LocationAnchor = Literal[
    "file_line",      # file_path + line_start: SAST, secrets, firmware
    "file_resource",  # file_path + resource_address: IaC (Checkov, tfsec)
    "url",            # file_path stores URL, line fields null: DAST
    "cloud_resource", # cloud_resource_id + cloud_platform + region: CSPM
    "purl",           # component purl: SCA (routes to component_has_vuln)
]


# ---------------------------------------------------------------------------
# ToolAdapter TypedDict
# ---------------------------------------------------------------------------

class ToolAdapter(TypedDict, total=False):
    """
    Complete specification for one scanner tool's normalisation.

    Required keys (validated at registration):
      tool_name, parse_format, fingerprint_fields, severity_map,
      default_finding_type, result_routing, location_anchor,
      field_map, cwe_source, req_mapping_source

    Optional keys:
      parse_root, multi_root, result_state_field, cwe_extract_pattern,
      secret_raw_field, deterministic_req_fields, pre_process
    """

    # Identity
    tool_name: str

    # Parse
    parse_format: ParseFormat
    parse_root: Optional[str]      # jmespath to findings array; None = top-level
    multi_root: list[str]          # multiple arrays (Checkov: failed/passed/skipped)

    # Fingerprint
    fingerprint_fields: list[FieldPath]

    # Severity
    severity_map: dict[Any, Optional[str]]

    # Classification
    default_finding_type: str

    # Routing
    result_routing: dict[str, CollectionTarget]
    result_state_field: Optional[str]    # dot-path; None = always → scan_findings

    # Location
    location_anchor: LocationAnchor

    # Field mapping
    field_map: dict[FieldPath, CanonicalField]
    # Conventions:
    #   "@field_name" prefix = inject from document-level wrapper (Checkov check_type)
    #   "_field_name" prefix = internal staging field, not written directly

    # CWE extraction
    cwe_source: CweSource
    cwe_extract_pattern: Optional[str]

    # Regulatory mapping
    req_mapping_source: ReqMappingSource
    deterministic_req_fields: list[FieldPath]

    # Secrets
    secret_raw_field: Optional[str]

    # Escape hatch for structural anomalies
    pre_process: Optional[Callable[[list[dict]], list[dict]]]


# ---------------------------------------------------------------------------
# ADAPTER_REGISTRY — one entry per tool
# ---------------------------------------------------------------------------

ADAPTER_REGISTRY: dict[ToolName, ToolAdapter] = {

    # ── semgrep (native CLI JSON: semgrep --json) ────────────────────────────
    # Output shape: {"results": [{"check_id": ..., "path": ..., "start": {"line": N},
    #   "end": {...}, "extra": {"severity": ..., "message": ..., "metadata": {"cwe": [...]}}}]}
    "semgrep": {
        "tool_name":            "semgrep",
        "parse_format":         "json_object",
        "parse_root":           "results",
        "multi_root":           [],
        "fingerprint_fields":   ["check_id", "path", "start.line"],
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
            "check_id":                   "rule_id",
            "path":                       "file_path",
            "start.line":                 "line_start",
            "end.line":                   "line_end",
            "extra.lines":                "code_snippet",
            "extra.metadata.cwe":         "_cwe_raw",        # list → str() + regex in _extract_cwe
            "extra.metadata.owasp":       "owasp_category",
            "extra.metadata.confidence":  "tool_confidence",
            "extra.metadata.references":  "references",
            "extra.severity":             "severity",
            "extra.message":              "message",
            "extra.fix":                  "fix_guidance",
        },
        "cwe_source":               "extracted",
        "cwe_extract_pattern":      r"(CWE-\d+)",
        "req_mapping_source":       "rule_engine",
        "deterministic_req_fields": [],
        "secret_raw_field":         None,
        "pre_process":              None,
    },

    # ── semgrep_custom (pre-processed categories format) ─────────────────────
    # Accepts the Complira-specific pre-processed format:
    # {"categories": {"sast": [...], "other_security_issues": [...]}, "total_findings": N}
    # Each finding has flat fields: rule_id, file_path, line_number, severity, cwe, etc.
    # Used by: sarif_semgrep.json fixture; FDA SBOM pipeline; clients that pre-process output.
    "semgrep_custom": {
        "tool_name":            "semgrep_custom",
        "parse_format":         "json_object",
        "parse_root":           "categories.*[]",
        "multi_root":           [],
        "fingerprint_fields":   ["rule_id", "file_path", "line_number"],
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
            "rule_id":                    "rule_id",
            "file_path":                  "file_path",
            "line_number":                "line_start",
            "end_line":                   "line_end",
            "code_snippet":               "code_snippet",
            "cwe":                        "_cwe_raw",
            "vulnerability_id":           "tool_vuln_id",
            "owasp":                      "owasp_category",
            "vulnerability_category":     "semgrep_vuln_category",
            "severity":                   "severity",
            "confidence":                 "tool_confidence",
            "references":                 "references",
            "remediation":                "fix_guidance",
            "message":                    "message",
        },
        "cwe_source":               "extracted",
        "cwe_extract_pattern":      r"(CWE-\d+)",
        "req_mapping_source":       "rule_engine",
        "deterministic_req_fields": [],
        "secret_raw_field":         None,
        "pre_process":              None,
    },

    # ── checkov ─────────────────────────────────────────────────────────────
    # checkov_sca and checkov_secrets are separate tools in the registry;
    # the IngestionEngine caller pre-filters by iac_framework before dispatch.
    "checkov": {
        "tool_name":            "checkov",
        "parse_format":         "json_object",
        "parse_root":           "failed_checks",
        "multi_root": [
            "failed_checks",   # → scan_findings
            "passed_checks",   # → detected_controls
            "skipped_checks",  # → audit_log
        ],
        "fingerprint_fields":   ["check_id", "file_path", "resource"],
        "severity_map": {
            "CRITICAL": "critical", "HIGH":   "high",
            "MEDIUM":   "medium",   "LOW":    "low",
            None:       "medium",  # absent without --bc-api-key → default to medium
        },
        "default_finding_type": "iac_misconfig",
        "result_routing": {
            "FAILED":  "scan_findings",
            "PASSED":  "detected_controls",
            "SKIPPED": "audit_log",
        },
        "result_state_field":   "check_result.result",   # nested object
        "location_anchor":      "file_resource",
        "field_map": {
            "check_id":              "check_id",
            "check_name":            "check_name",
            "check_result.result":   "check_result",
            "check_class":           "check_class",
            "file_path":             "file_path",
            "file_line_range[0]":    "line_start",
            "file_line_range[1]":    "line_end",
            "resource":              "resource_address",
            "guideline":             "guideline",
            "bc_check_id":           "bc_check_id",
            "severity":              "severity",
            "@check_type":           "iac_framework",    # document-level injection
        },
        "cwe_source":               "absent",
        "cwe_extract_pattern":      None,
        # bc_check_id present → "checkov_native" (deterministic); absent → "llm_reg_mapper"
        # IngestionEngine._plan_edges() overrides dynamically based on bc_check_id field
        "req_mapping_source":       "checkov_native",
        "deterministic_req_fields": ["bc_check_id"],
        "secret_raw_field":         None,
        "pre_process":              None,
    },

    # ── gitleaks ─────────────────────────────────────────────────────────────
    "gitleaks": {
        "tool_name":            "gitleaks",
        "parse_format":         "json_array",
        "parse_root":           None,
        "multi_root":           [],
        "fingerprint_fields":   ["Fingerprint"],
        "severity_map": {
            None:     "high",
            "":       "high",
            "HIGH":   "high",
            "MEDIUM": "medium",
            "LOW":    "low",
        },
        "default_finding_type": "secret",
        "result_routing":       {"*": "scan_findings"},
        "result_state_field":   None,
        "location_anchor":      "file_line",
        "field_map": {
            "RuleID":      "rule_id",
            "File":        "file_path",
            "StartLine":   "line_start",
            "EndLine":     "line_end",
            "Description": "message",
            "Commit":      "commit_sha",
            "Match":       "_secret_raw",
            "Secret":      "_secret_raw",
        },
        "cwe_source":               "absent",
        "cwe_extract_pattern":      None,
        "req_mapping_source":       "none",
        "deterministic_req_fields": [],
        "secret_raw_field":         "Match",
        "pre_process":              None,
    },

    # ── grype (SCA) ──────────────────────────────────────────────────────────
    "grype": {
        "tool_name":            "grype",
        "parse_format":         "json_object",
        "parse_root":           "matches",
        "multi_root":           [],
        "fingerprint_fields":   ["vulnerability.id", "artifact.purl"],
        "severity_map": {
            "Critical":    "critical",
            "High":        "high",
            "Medium":      "medium",
            "Low":         "low",
            "Negligible":  "info",
            "Unknown":     None,
        },
        "default_finding_type": "sca",
        "result_routing":       {"*": "component_has_vuln"},  # routes to edge, not scan_findings
        "result_state_field":   None,
        "location_anchor":      "purl",
        "field_map": {
            "vulnerability.id":          "cve_id",
            "vulnerability.severity":    "severity",
            "vulnerability.description": "description",
            "vulnerability.cvss":        "_cvss_raw",
            "artifact.purl":             "purl",
            "artifact.name":             "component_name",
            "artifact.version":          "component_version",
            "artifact.type":             "component_type",
        },
        "cwe_source":               "absent",
        "cwe_extract_pattern":      None,
        "req_mapping_source":       "none",
        "deterministic_req_fields": [],
        "secret_raw_field":         None,
        "pre_process":              None,
    },

    # ── trufflehog ──────────────────────────────────────────────────────────
    "trufflehog": {
        "tool_name":            "trufflehog",
        "parse_format":         "json_lines",
        "parse_root":           None,
        "multi_root":           [],
        "fingerprint_fields": [
            "DetectorName",
            "SourceMetadata.Data.Git.file",
            "SourceMetadata.Data.Git.line",
        ],
        "severity_map": {None: "high", "": "high"},
        "default_finding_type": "secret",
        "result_routing":       {"*": "scan_findings"},
        "result_state_field":   None,
        "location_anchor":      "file_line",
        "field_map": {
            "DetectorName":                    "rule_id",
            "SourceMetadata.Data.Git.file":    "file_path",
            "SourceMetadata.Data.Git.line":    "line_start",
            "SourceMetadata.Data.Git.commit":  "commit_sha",
            "Raw":                             "_secret_raw",
            "RawV2":                           "_secret_raw",
            "Verified":                        "secret_verified",
        },
        "cwe_source":               "absent",
        "cwe_extract_pattern":      None,
        "req_mapping_source":       "none",
        "deterministic_req_fields": [],
        "secret_raw_field":         "Raw",
        "pre_process":              None,
    },

    # ── zap (DAST) ──────────────────────────────────────────────────────────
    "zap": {
        "tool_name":            "zap",
        "parse_format":         "json_object",
        "parse_root":           "site[*].alerts[*]",
        "multi_root":           [],
        "fingerprint_fields":   ["pluginid", "url", "param"],
        "severity_map": {
            "High":          "high",
            "Medium":        "medium",
            "Low":           "low",
            "Informational": "info",
            "0": "info", "1": "low", "2": "medium", "3": "high",
        },
        "default_finding_type": "dast",
        "result_routing":       {"*": "scan_findings"},
        "result_state_field":   None,
        "location_anchor":      "url",
        "field_map": {
            "pluginid":   "rule_id",
            "alert":      "message",
            "solution":   "fix_guidance",
            "url":        "file_path",
            "other":      "description",
            "cweid":      "_cwe_int",
            "riskdesc":   "_riskdesc_raw",
            "confidence": "tool_confidence",
            "reference":  "references",
        },
        "cwe_source":               "extracted",
        "cwe_extract_pattern":      r"(\d+)",
        "req_mapping_source":       "rule_engine",
        "deterministic_req_fields": [],
        "secret_raw_field":         None,
        "pre_process":              None,
    },

    # ── trivy (SCA — container/OS/code) ─────────────────────────────────────
    # Output: trivy --format json
    # Shape: {"Results": [{"Target": "...", "Type": "...", "Vulnerabilities": [...]}]}
    # Each Vulnerability: {VulnerabilityID, PkgName, InstalledVersion, FixedVersion,
    #   Severity, Title, Description, PrimaryURL, CweIDs: []string}
    # Routes to component_has_vuln (same as grype).
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
            "VulnerabilityID":  "cve_id",
            "Severity":         "severity",
            "Title":            "rule_id",
            "Description":      "description",
            "FixedVersion":     "fix_guidance",
            "PrimaryURL":       "references",
            "PkgName":          "component_name",
            "InstalledVersion": "component_version",
            "Target":           "file_path",
            "CweIDs":           "_cwe_raw",
        },
        "cwe_source":               "tool_direct",
        "cwe_extract_pattern":      None,
        "req_mapping_source":       "none",
        "deterministic_req_fields": [],
        "secret_raw_field":         None,
        "pre_process":              None,
    },

    # ── npm_audit (SCA — npm 7+ audit JSON) ──────────────────────────────────
    # Output: npm audit --json  (npm 7+ / arborist v2 format)
    # Shape: {"vulnerabilities": {"pkg-name": {name, severity, via, range, ...}}}
    # parse_root "vulnerabilities.*[]" flattens dict values via _extract_list.
    # npm 6 (advisories format) is out of scope.
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
            "name":      "component_name",
            "severity":  "severity",
            "range":     "description",
            "isDirect":  "tool_confidence",
        },
        "cwe_source":               "absent",
        "cwe_extract_pattern":      None,
        "req_mapping_source":       "none",
        "deterministic_req_fields": [],
        "secret_raw_field":         None,
        "pre_process":              None,
    },

    # ── pip_audit (SCA — Python package audit) ───────────────────────────────
    # Output: pip-audit --format json --aliases --desc
    # Shape: {"dependencies": [{name, version, vulns: [{id, fix_versions, aliases, description}]}]}
    # parse_root=None + pre_process=pip_audit_flatten handles denormalization
    # (vuln dicts don't carry parent name/version; flatten injects them).
    # pip-audit does not emit severity; all findings have severity=None.
    "pip_audit": {
        "tool_name":            "pip_audit",
        "parse_format":         "json_object",
        "parse_root":           None,         # pre_process handles full-output flattening
        "multi_root":           [],
        "fingerprint_fields":   ["id", "pkg_name"],
        "severity_map":         {None: None},  # pip-audit has no severity ratings
        "default_finding_type": "sca",
        "result_routing":       {"*": "component_has_vuln"},
        "result_state_field":   None,
        "location_anchor":      "purl",
        "field_map": {
            "id":           "tool_vuln_id",
            "cve_id":       "cve_id",         # injected by pip_audit_flatten from aliases
            "description":  "description",
            "fix_versions": "fix_guidance",
            "pkg_name":     "component_name",
            "pkg_version":  "component_version",
        },
        "cwe_source":               "absent",
        "cwe_extract_pattern":      None,
        "req_mapping_source":       "none",
        "deterministic_req_fields": [],
        "secret_raw_field":         None,
        "pre_process":              None,      # assigned after function definition below
    },

    # ── sonarqube (SAST — SonarQube Web API issues/search JSON) ─────────────
    # Output: GET /api/issues/search → {"issues": [...]}
    # Dual-path severity: field_map lists legacy "severity" first (MAJOR/CRITICAL/...),
    # then "impacts[0].severity" second (HIGH/MEDIUM/LOW) which overwrites for v10+ output.
    # Both paths covered in severity_map.
    "sonarqube": {
        "tool_name":            "sonarqube",
        "parse_format":         "json_object",
        "parse_root":           "issues",
        "multi_root":           [],
        "fingerprint_fields":   ["key"],
        "severity_map": {
            # Legacy severity (pre-v10)
            "BLOCKER":  "critical",
            "CRITICAL": "critical",
            "MAJOR":    "high",
            "MINOR":    "low",
            "INFO":     "info",
            # Modern severity (v10+, from impacts[0].severity)
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
            # Legacy fields first; impacts[0].severity overwrites if present (v10+)
            "severity":             "severity",
            "rule":                 "rule_id",
            "message":              "message",
            "component":            "file_path",
            "line":                 "line_start",
            "key":                  "tool_vuln_id",
            "type":                 "check_name",
            "impacts[0].severity":  "severity",   # v10+: overwrites legacy severity
        },
        "cwe_source":               "extracted",
        "cwe_extract_pattern":      r"(CWE-\d+)",
        "req_mapping_source":       "rule_engine",
        "deterministic_req_fields": [],
        "secret_raw_field":         None,
        "pre_process":              None,
    },

    # ── spotbugs (SAST — SpotBugs XML report) ───────────────────────────────
    # Output: SpotBugs --xml:withMessages  (addMessages=true required for cweid attribute)
    # Shape: <BugCollection><BugInstance type="..." priority="1" rank="5" cweid="670">
    #          <SourceLine classname="..." start="42" end="45" sourcepath="..." primary="true"/>
    #        </BugInstance></BugCollection>
    # Engine XML branch flattens element attributes + primary SourceLine as sl_* keys.
    # priority: 1=High, 2=Normal(medium), 3=Low, 4=Experimental(info)
    "spotbugs": {
        "tool_name":            "spotbugs",
        "parse_format":         "xml",
        "parse_root":           "BugCollection/BugInstance",
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
            "type":          "rule_id",
            "priority":      "severity",
            "rank":          "tool_confidence",
            "category":      "check_name",
            "cweid":         "_cwe_int",
            "sl_sourcepath": "file_path",
            "sl_start":      "line_start",
            "sl_end":        "line_end",
            "sl_classname":  "description",
        },
        "cwe_source":               "extracted",
        "cwe_extract_pattern":      r"(\d+)",
        "req_mapping_source":       "rule_engine",
        "deterministic_req_fields": [],
        "secret_raw_field":         None,
        "pre_process":              None,
    },

    # ── sarif (generic SARIF 2.1) ────────────────────────────────────────────
    "sarif": {
        "tool_name":            "sarif",
        "parse_format":         "sarif",
        "parse_root":           "runs[*].results[*]",
        "multi_root":           [],
        "fingerprint_fields":   ["ruleId", "locations[0].physicalLocation.artifactLocation.uri", "locations[0].physicalLocation.region.startLine"],
        "severity_map": {
            "error":   "high",
            "warning": "medium",
            "note":    "info",
            "none":    "info",
        },
        "default_finding_type": "sast",
        "result_routing":       {"*": "scan_findings"},
        "result_state_field":   None,
        "location_anchor":      "file_line",
        "field_map": {
            "ruleId":                                                              "rule_id",
            "locations[0].physicalLocation.artifactLocation.uri":                 "file_path",
            "locations[0].physicalLocation.region.startLine":                     "line_start",
            "locations[0].physicalLocation.region.endLine":                       "line_end",
            "message.text":                                                        "message",
            "level":                                                               "severity",
        },
        "cwe_source":               "extracted",
        "cwe_extract_pattern":      r"(CWE-\d+)",
        "req_mapping_source":       "rule_engine",
        "deterministic_req_fields": [],
        "secret_raw_field":         None,
        "pre_process":              None,
    },
}


# ---------------------------------------------------------------------------
# Required keys for registration validation
# ---------------------------------------------------------------------------

_REQUIRED_ADAPTER_KEYS = {
    "tool_name", "parse_format", "fingerprint_fields",
    "severity_map", "default_finding_type", "result_routing",
    "location_anchor", "field_map", "cwe_source", "req_mapping_source",
}


def _validate_registry() -> None:
    for name, adapter in ADAPTER_REGISTRY.items():
        missing = _REQUIRED_ADAPTER_KEYS - set(adapter.keys())
        if missing:
            raise ValueError(
                f"ToolAdapter '{name}' is missing required keys: {missing}"
            )


_validate_registry()


# ---------------------------------------------------------------------------
# Pre-process helpers (defined after registry to avoid forward-reference issues)
# ---------------------------------------------------------------------------

def pip_audit_flatten(findings: list[dict]) -> list[dict]:
    """
    Pre-process hook for pip_audit adapter.

    pip-audit JSON emits a top-level object; the engine passes [full_output_dict]
    when parse_root=None. This hook denormalizes dependencies[*].vulns[*] into
    a flat list, injecting parent name/version into each vuln dict, and hoisting
    the first CVE-format alias into a `cve_id` field.

    Requires: pip-audit --format json --aliases --desc
    """
    raw_data = findings[0] if findings else {}
    flat: list[dict] = []
    for dep in raw_data.get("dependencies", []):
        name = dep.get("name", "")
        version = dep.get("version", "")
        for vuln in dep.get("vulns", []):
            entry = dict(vuln)
            entry["pkg_name"] = name
            entry["pkg_version"] = version
            for alias in entry.get("aliases") or []:
                if re.match(r"^CVE-\d{4}-\d{4,}$", alias, re.IGNORECASE):
                    entry["cve_id"] = alias
                    break
            flat.append(entry)
    return flat


# Wire pre_process hooks after function definition
ADAPTER_REGISTRY["pip_audit"]["pre_process"] = pip_audit_flatten


# ---------------------------------------------------------------------------
# Prowler (Cloud Security Posture Management — AWS/GCP/Azure)
# Output: prowler -M json  →  top-level JSON array of findings
# Shape: [{CheckID, CheckTitle, Status, Severity, ResourceArn,
#           ServiceName, Region, AccountId, Compliance, Remediation, ...}]
# Routes FAIL/WARNING → scan_findings; PASS/MUTED → dropped.
# NIST 800-53 control IDs are embedded in Compliance["NIST-800-53-Rev5"].
# ---------------------------------------------------------------------------

def prowler_flatten(items: list) -> list:
    """Flatten nested Prowler fields and filter to actionable statuses."""
    result = []
    for item in items:
        if item.get("Status") not in ("FAIL", "WARNING"):
            continue
        flat = dict(item)
        # Flatten Remediation
        rem = flat.get("Remediation") or {}
        flat["_fix_guidance"] = rem.get("Recommendation") or rem.get("Code") or ""
        # Flatten Compliance — extract NIST 800-53 control IDs
        comp = flat.get("Compliance") or {}
        nist_controls = comp.get("NIST-800-53-Rev5") or []
        flat["_nist_controls"] = ", ".join(nist_controls) if nist_controls else ""
        flat["_hipaa_refs"] = ", ".join(comp.get("HIPAA") or [])
        flat["_cis_refs"]   = ", ".join(comp.get("CIS-AWS-Foundations-Benchmark-1.4") or [])
        result.append(flat)
    return result


ADAPTER_REGISTRY["prowler"] = {
    "tool_name":            "prowler",
    "parse_format":         "json_array",
    "parse_root":           None,
    "multi_root":           [],
    "fingerprint_fields":   ["FindingUniqueId"],
    "severity_map": {
        "critical":      "critical",
        "high":          "high",
        "medium":        "medium",
        "low":           "low",
        "informational": "info",
        "info":          "info",
    },
    "default_finding_type": "cspm",
    "result_state_field":   "Status",
    "result_routing": {
        "FAIL":    "scan_findings",
        "WARNING": "scan_findings",
        "*":       "_ignored",
    },
    "location_anchor":      "line",
    "field_map": {
        "CheckID":       "rule_id",
        "CheckTitle":    "message",
        "StatusExtended": "description",
        "Severity":      "severity",
        "ResourceArn":   "file_path",
        "ResourceType":  "resource_type",
        "ServiceName":   "component_name",
        "Region":        "region",
        "AccountId":     "account_id",
        "_fix_guidance": "fix_guidance",
        "_nist_controls": "nist_control_refs",
        "_hipaa_refs":   "hipaa_refs",
        "_cis_refs":     "cis_refs",
    },
    "cwe_source":               "none",
    "cwe_extract_pattern":      None,
    "req_mapping_source":       "none",
    "deterministic_req_fields": [],
    "secret_raw_field":         None,
    "pre_process":              prowler_flatten,
}


# ---------------------------------------------------------------------------
# Public helper: register a new tool at runtime
# ---------------------------------------------------------------------------

def register_adapter(adapter: ToolAdapter) -> None:
    """
    Register a new tool adapter.

    Validates required keys before registration.
    Call this from the tool's own module rather than editing this file.

    Example::

        register_adapter({
            "tool_name":          "bandit",
            "parse_format":       "json_object",
            "parse_root":         "results[*]",
            "fingerprint_fields": ["test_id", "filename", "line_number"],
            "severity_map":       {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"},
            "default_finding_type": "sast",
            "result_routing":     {"*": "scan_findings"},
            "result_state_field": None,
            "location_anchor":    "file_line",
            "field_map":          {"test_id": "rule_id", "filename": "file_path"},
            "cwe_source":         "tool_direct",
            "req_mapping_source": "rule_engine",
            "deterministic_req_fields": [],
            "secret_raw_field":   None,
            "pre_process":        None,
        })
    """
    name = adapter.get("tool_name", "<unknown>")
    missing = _REQUIRED_ADAPTER_KEYS - set(adapter.keys())
    if missing:
        raise ValueError(f"Cannot register '{name}': missing required keys {missing}")
    ADAPTER_REGISTRY[name] = adapter
