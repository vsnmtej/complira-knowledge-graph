"""
complira_kg_schema_v2_2.py
==========================
Extended ArangoDB schema for Complira Knowledge Graph — v2.2
Adds the scanner evidence ingestion layer on top of the existing v2.1 schema.

Architecture Fixes Applied (v2.2.1):
- Fix 1: Components are global entities (no project_id). Projects link via
         `project_uses_component` edge, enabling cross-project correlation.
- Fix 2: `tenant_id` is required on all evidence collections with composite
         indexes for multi-tenant data isolation at the index level.
- Fix 3: `project_uses_component` edge + 3 cross-project Tier 1 AQL templates
         for portfolio-level compliance intelligence.

New in v2.2
-----------
Document Collections (new):
  scan_runs            — one per pipeline execution
  scan_findings        — all SAST / secrets / DAST / SCA findings
  detected_controls    — positive control detections from scanner output
  evidence_packages    — top-level evidence bundle (SBOM + MCP + scan run)

Document Collections (activated from v2.1 empty):
  components           — SBOM-sourced software components (global, purl-keyed)

Edge Collections (new):
  component_has_vuln         components        → vulnerabilities
  finding_maps_to_weakness   scan_findings     → weaknesses
  finding_triggers_req       scan_findings     → regulatory_requirements
  detected_control_maps_to   detected_controls → oscal_controls | scf_controls
  control_in_component       detected_controls → components
  finding_in_component       scan_findings     → components
  evidence_links_finding     evidence_packages → scan_findings
  evidence_for_project       evidence_packages → projects
  project_uses_component     projects          → components  (Fix 1)

Edge Collections (activated from v2.1 empty):
  matched_by_cpe       components      → cpe_entries
  depends_on           components      → components
  licensed_under       components      → licenses
  component_eol_status components      → eol_products

Determinism tags (source field on edges):
  Deterministic  : nvd | curated | scf | rule_engine | semgrep | grype |
                   trivy | syft | cpe_match | scanner
  Probabilistic  : llm_classifier | llm_reg_mapper | embedding_matcher
                   (always carry a float `confidence` field, 0.0–1.0)

Usage
-----
  python -m complira_graph.schema.complira_kg_schema_v2_2 \\
         --host http://localhost:8529 \\
         --db complira_graph --user root --password <pw> [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Migration & compatibility constants
# ---------------------------------------------------------------------------

# Fix 1: All v2.2 evidence collections go to the reference DB.
# The 7 cross-DB edges (component_has_vuln, finding_maps_to_weakness,
# finding_triggers_req, control_in_component, finding_in_component,
# licensed_under, component_eol_status) are now all intra-reference-DB.
DB_PLACEMENT: dict[str, str] = {
    # v2.2 evidence layer — all in reference DB with tenant_id isolation
    "scan_runs":              "reference",
    "scan_findings":          "reference",
    "detected_controls":      "reference",
    "evidence_packages":      "reference",
    "components":             "reference",   # global, purl-keyed
    # Edges — all intra-reference-DB
    "component_has_vuln":         "reference",
    "finding_maps_to_weakness":   "reference",
    "finding_triggers_req":       "reference",
    "detected_control_maps_to":   "reference",
    "control_in_component":       "reference",
    "finding_in_component":       "reference",
    "evidence_links_finding":     "reference",
    "evidence_for_project":       "reference",
    "project_uses_component":     "reference",
    "matched_by_cpe":             "reference",
    "depends_on":                 "reference",
    "licensed_under":             "reference",
    "component_eol_status":       "reference",
}

# Fix 2: Canonical mapping from legacy customer-DB collection names to v2.2.
# The ingestion adapter reads from customer DBs using the old names,
# writes to reference DB using the new names.
LEGACY_COLLECTION_MAP: dict[str, str] = {
    "scan_sessions":      "scan_runs",       # customer DB → reference DB
    "customer_components": "components",      # customer DB → reference DB (global)
}

# Fix 3: Canonical field mapping from legacy to v2.2.
# Applied by the ingestion adapter when pulling documents from customer DBs.
# No customer DB documents are mutated.
FIELD_MAP: dict[str, str] = {
    "customer_id": "tenant_id",
}


# ---------------------------------------------------------------------------
# Schema definitions
# ---------------------------------------------------------------------------

# ── Document collections ────────────────────────────────────────────────────

DOCUMENT_COLLECTIONS: list[dict[str, Any]] = [

    # ── components (GLOBAL — Fix 1) ─────────────────────────────────────────
    # Components are global entities keyed by purl. Projects link to them via
    # the `project_uses_component` edge. This enables cross-project queries
    # like "which projects share this vulnerable component?"
    {
        "name": "components",
        "schema": {
            "rule": {
                "type": "object",
                "required": ["purl", "name", "version", "component_type"],
                "properties": {
                    # ── Identity ──────────────────────────────────────────
                    "purl": {
                        "type": "string",
                        "description": "Package URL (RFC 3420) — primary dedup key and _key basis. "
                                       "e.g. pkg:pypi/rich@13.5.2. "
                                       "Always present: sbom_direct if the SBOM carried it; "
                                       "generated (pkg:generic/<name>@<version>?bom_ref=<hash>) "
                                       "for components lacking a native purl."
                    },
                    "purl_source": {
                        "type": "string",
                        "enum": ["sbom_direct", "bom_ref_purl", "generated"],
                        "description": "sbom_direct   — purl present verbatim in SBOM component. "
                                       "bom_ref_purl  — extracted from CycloneDX bom-ref. "
                                       "generated     — no purl in source; constructed from "
                                       "               pkg:generic/<name>@<ver>?bom_ref=<hash16>."
                    },
                    "name":    {"type": "string"},
                    "version": {"type": "string"},
                    "component_type": {
                        "type": "string",
                        "enum": [
                            "library", "framework", "application", "container",
                            "device", "firmware", "file", "operating-system",
                            "github-action", "unknown"
                        ]
                    },

                    # ── CPE / identity extras ──────────────────────────────
                    "cpe": {
                        "type": ["string", "null"],
                        "description": "CPE 2.3 string if available from SBOM or resolved"
                    },
                    "cpe_confidence": {
                        "type": ["number", "null"],
                        "description": "Confidence of cpe_resolver agent result (0.0–1.0). "
                                       "Null if CPE came from SBOM directly (deterministic)."
                    },
                    "bom_ref": {
                        "type": ["string", "null"],
                        "description": "CycloneDX bom-ref or SPDX SPDXID"
                    },
                    "sbom_format": {
                        "type": ["string", "null"],
                        "enum": ["cyclonedx-1.6", "spdx-3.0", "spdx-2.3", None]
                    },

                    # ── Package metadata ──────────────────────────────────
                    "supplier": {"type": ["string", "null"]},
                    "author":   {"type": ["string", "null"]},
                    "description": {"type": ["string", "null"]},
                    "licenses": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "SPDX license expression list"
                    },
                    "hashes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["alg", "content"],
                            "properties": {
                                "alg":     {"type": "string"},
                                "content": {"type": "string"}
                            }
                        }
                    },
                    "package_manager": {
                        "type": ["string", "null"],
                        "description": "e.g. pip, npm, cargo, conan, yocto"
                    },

                    # ── Global provenance (Fix 1: no project_id here) ─────
                    "first_seen_globally": {
                        "type": "string",
                        "format": "date-time",
                        "description": "Earliest timestamp any project ingested this component"
                    },
                    "last_seen_globally": {
                        "type": ["string", "null"],
                        "format": "date-time",
                        "description": "Most recent timestamp any project ingested this component"
                    },

                    # ── Firmware / embedded extras ─────────────────────────
                    "firmware_layer": {
                        "type": ["string", "null"],
                        "enum": ["kernel", "bootloader", "userspace", "bsp", None],
                        "description": "EMBA-sourced layer classification"
                    },
                    "yocto_recipe": {"type": ["string", "null"]},
                    "kernel_config_flags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Relevant kernel config options (e.g. CONFIG_MODULES)"
                    },

                    # ── EOL status (denorm from component_eol_status) ──────
                    "eol_date":       {"type": ["string", "null"]},
                    "eol_lts_until":  {"type": ["string", "null"]}
                },
                "additionalProperties": True
            },
            "level": "moderate",
            "message": "Component document failed schema validation"
        },
        "indexes": [
            {"type": "persistent", "fields": ["purl"],            "unique": True,  "name": "idx_components_purl"},
            {"type": "persistent", "fields": ["cpe"],             "unique": False, "name": "idx_components_cpe"},
            {"type": "persistent", "fields": ["package_manager"], "unique": False, "name": "idx_components_pkg_mgr"},
            {"type": "persistent", "fields": ["firmware_layer"],  "unique": False, "name": "idx_components_fw_layer"},
            {"type": "persistent", "fields": ["name", "version"], "unique": False, "name": "idx_components_name_ver"},
        ]
    },

    # ── scan_runs (Fix 2: tenant_id required) ──────────────────────────────
    {
        "name": "scan_runs",
        "schema": {
            "rule": {
                "type": "object",
                "required": ["scan_run_id", "tenant_id", "project_id",
                             "commit_sha", "tools_invoked", "status",
                             "started_at"],
                "properties": {
                    "scan_run_id": {
                        "type": "string",
                        "description": "UUID v4. Also used as ArangoDB _key."
                    },
                    "tenant_id": {
                        "type": "string",
                        "description": "Organization/tenant ID for multi-tenant isolation"
                    },
                    "project_id":  {"type": "string"},
                    "repo_url":    {"type": ["string", "null"]},
                    "commit_sha":  {"type": "string"},
                    "branch":      {"type": ["string", "null"]},
                    "tag":         {"type": ["string", "null"]},
                    "triggered_by": {
                        "type": "string",
                        "enum": ["ci", "manual", "scheduled", "webhook", "api"]
                    },
                    "tools_invoked": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "e.g. ['semgrep','grype','trivy','syft','gitleaks']"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["running", "completed", "failed", "partial"]
                    },
                    "started_at":   {"type": "string", "format": "date-time"},
                    "completed_at": {"type": ["string", "null"], "format": "date-time"},
                    "duration_seconds": {"type": ["number", "null"]},

                    # ── Counts (denorm for fast dashboard queries) ─────────
                    "finding_counts": {
                        "type": "object",
                        "properties": {
                            "critical": {"type": "integer"},
                            "high":     {"type": "integer"},
                            "medium":   {"type": "integer"},
                            "low":      {"type": "integer"},
                            "info":     {"type": "integer"}
                        }
                    },
                    "component_count":        {"type": ["integer", "null"]},
                    "detected_control_count": {"type": ["integer", "null"]},

                    # ── Compliance snapshot ───────────────────────────────
                    "violated_requirements": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Req IDs found violated in this run"
                    },
                    "compliance_score": {
                        "type": ["number", "null"],
                        "description": "0–100. Computed post-run."
                    },

                    # ── Diff anchoring ────────────────────────────────────
                    "previous_scan_run_id": {"type": ["string", "null"]},
                    "new_findings_count":     {"type": ["integer", "null"]},
                    "resolved_findings_count": {"type": ["integer", "null"]}
                },
                "additionalProperties": True
            },
            "level": "moderate",
            "message": "scan_run document failed schema validation"
        },
        "indexes": [
            {"type": "persistent", "fields": ["scan_run_id"],              "unique": True,  "name": "idx_scan_runs_id"},
            {"type": "persistent", "fields": ["tenant_id", "project_id"],  "unique": False, "name": "idx_scan_runs_tenant_project"},
            {"type": "persistent", "fields": ["tenant_id", "started_at"],  "unique": False, "name": "idx_scan_runs_tenant_started"},
            {"type": "persistent", "fields": ["commit_sha"],               "unique": False, "name": "idx_scan_runs_commit"},
            {"type": "persistent", "fields": ["status"],                   "unique": False, "name": "idx_scan_runs_status"},
        ]
    },

    # ── scan_findings (Fix 2: tenant_id required) ──────────────────────────
    {
        "name": "scan_findings",
        "schema": {
            "rule": {
                "type": "object",
                "required": ["fingerprint", "tool", "finding_type",
                             "severity", "tenant_id", "scan_run_id",
                             "project_id"],
                "properties": {
                    # ── Dedup / traceability key ──────────────────────────
                    "fingerprint": {
                        "type": "string",
                        "description": "sha256(tool + file_path + line_start + rule_id). "
                                       "Used as ArangoDB _key after slug-encoding."
                    },

                    # ── Tenant isolation (Fix 2) ─────────────────────────
                    "tenant_id": {
                        "type": "string",
                        "description": "Organization/tenant ID for multi-tenant isolation"
                    },

                    # ── Source ────────────────────────────────────────────
                    "tool": {
                        "type": "string",
                        "enum": [
                            "semgrep", "bandit", "gitleaks", "trufflehog",
                            "checkov", "njsscan", "gosec", "zap",
                            "nuclei", "trivy-config", "emba", "custom"
                        ]
                    },
                    "finding_type": {
                        "type": "string",
                        "enum": [
                            "sast", "secret", "iac_misconfig",
                            "dast", "firmware", "supply_chain"
                        ]
                    },
                    "tool_version": {"type": ["string", "null"]},
                    "rule_id": {"type": ["string", "null"]},

                    # ── Location ──────────────────────────────────────────
                    "file_path":    {"type": ["string", "null"]},
                    "line_start":   {"type": ["integer", "null"]},
                    "line_end":     {"type": ["integer", "null"]},
                    "column_start": {"type": ["integer", "null"]},
                    "column_end":   {"type": ["integer", "null"]},
                    "code_snippet": {"type": ["string", "null"]},

                    # ── Tool-native identity ──────────────────────────────
                    "tool_vuln_id": {
                        "type": ["string", "null"],
                        "description": "Tool-native vulnerability identifier stored verbatim. "
                                       "NOT used as a CVE reference."
                    },
                    "cve_id": {
                        "type": ["string", "null"],
                        "description": "Real NVD CVE identifier only. Must match CVE-\\d{4}-\\d{4,}."
                    },

                    # ── Classification ────────────────────────────────────
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "high", "medium", "low", "info",
                                 "error", "warning", "note"]
                    },
                    "severity_normalised": {
                        "type": ["string", "null"],
                        "enum": ["critical", "high", "medium", "low", "info", None]
                    },
                    "cwe_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Short CWE codes: ['CWE-78', 'CWE-94']"
                    },
                    "cwe_source": {
                        "type": ["string", "null"],
                        "enum": ["tool_direct", "extracted", "llm_inferred", None]
                    },
                    "semgrep_vuln_category": {
                        "type": ["string", "null"],
                        "enum": [
                            "INJECTION", "XSS", "SENSITIVE_DATA", "SECURITY_MISCONFIG",
                            "BROKEN_ACCESS", "AUTHENTICATION", "CRYPTO_WEAKNESS",
                            "SUPPLY_CHAIN", None
                        ]
                    },
                    "owasp_category": {"type": ["string", "null"]},
                    "category":       {"type": ["string", "null"]},

                    # ── Secret-specific ───────────────────────────────────
                    "secret_type": {
                        "type": ["string", "null"],
                        "enum": [
                            "api_key", "aws_credential", "github_token",
                            "private_key", "password", "jwt_secret",
                            "database_url", "generic_secret", None
                        ]
                    },
                    "secret_entropy":  {"type": ["number", "null"]},
                    "secret_redacted": {"type": ["string", "null"]},

                    # ── Firmware-specific (EMBA) ──────────────────────────
                    "firmware_module": {"type": ["string", "null"]},
                    "firmware_layer":  {
                        "type": ["string", "null"],
                        "enum": ["kernel", "bootloader", "userspace", "bsp", None]
                    },

                    # ── Message / fix ─────────────────────────────────────
                    "message":      {"type": ["string", "null"]},
                    "fix_guidance": {"type": ["string", "null"]},
                    "references":   {"type": "array", "items": {"type": "string"}},

                    # ── Triage state ──────────────────────────────────────
                    "triage_status": {
                        "type": "string",
                        "enum": ["open", "accepted_risk", "false_positive",
                                 "in_remediation", "resolved"],
                        "default": "open"
                    },
                    "triage_note":  {"type": ["string", "null"]},
                    "triaged_by":   {"type": ["string", "null"]},
                    "triaged_at":   {"type": ["string", "null"], "format": "date-time"},

                    # ── VEX support ───────────────────────────────────────
                    "vex_excluded": {"type": "boolean", "default": False},

                    # ── Provenance ────────────────────────────────────────
                    "scan_run_id": {"type": "string"},
                    "project_id":  {"type": "string"},
                    "commit_sha":  {"type": "string"},
                    "detected_at": {"type": "string", "format": "date-time"},
                    "first_seen_at": {"type": ["string", "null"], "format": "date-time"},

                    # ── LLM enrichment ────────────────────────────────────
                    "llm_summary":         {"type": ["string", "null"]},
                    "llm_attack_scenario": {"type": ["string", "null"]},
                    "llm_confidence":      {"type": ["number", "null"]}
                },
                "additionalProperties": True
            },
            "level": "moderate",
            "message": "scan_finding document failed schema validation"
        },
        "indexes": [
            {"type": "persistent", "fields": ["fingerprint"],                                     "unique": True,  "name": "idx_findings_fp"},
            {"type": "persistent", "fields": ["tenant_id", "project_id"],                         "unique": False, "name": "idx_findings_tenant_project"},
            {"type": "persistent", "fields": ["tenant_id", "scan_run_id"],                        "unique": False, "name": "idx_findings_tenant_run"},
            {"type": "persistent", "fields": ["tool"],                                            "unique": False, "name": "idx_findings_tool"},
            {"type": "persistent", "fields": ["finding_type"],                                    "unique": False, "name": "idx_findings_type"},
            {"type": "persistent", "fields": ["severity_normalised"],                             "unique": False, "name": "idx_findings_severity"},
            {"type": "persistent", "fields": ["triage_status"],                                   "unique": False, "name": "idx_findings_triage"},
            {"type": "persistent", "fields": ["cwe_ids[*]"],                                      "unique": False, "name": "idx_findings_cwe"},
            {"type": "persistent", "fields": ["secret_type"],                                     "unique": False, "name": "idx_findings_secret_type"},
            {"type": "persistent", "fields": ["tenant_id", "project_id", "triage_status", "severity_normalised"],
             "unique": False, "name": "idx_findings_tenant_project_triage_sev"},
        ]
    },

    # ── detected_controls (Fix 2: tenant_id required) ──────────────────────
    {
        "name": "detected_controls",
        "schema": {
            "rule": {
                "type": "object",
                "required": ["fingerprint", "control_type", "file_path",
                             "tenant_id", "scan_run_id", "project_id",
                             "confidence"],
                "properties": {
                    "fingerprint": {
                        "type": "string",
                        "description": "sha256(tool + file_path + line_number + control_type)"
                    },
                    "tenant_id": {
                        "type": "string",
                        "description": "Organization/tenant ID for multi-tenant isolation"
                    },
                    "control_type": {"type": "string"},
                    "control_category": {
                        "type": ["string", "null"],
                        "enum": [
                            "authentication", "authorization", "cryptography",
                            "input_validation", "output_encoding", "logging_monitoring",
                            "error_handling", "session_management", "secrets_management",
                            "network_security", "rate_limiting", "supply_chain", None
                        ]
                    },

                    # ── Location ──────────────────────────────────────────
                    "file_path":    {"type": ["string", "null"]},
                    "line_number":  {"type": ["integer", "null"]},
                    "code_snippet": {"type": ["string", "null"]},

                    # ── Confidence ────────────────────────────────────────
                    "confidence": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0
                    },
                    "detection_method": {
                        "type": ["string", "null"],
                        "enum": ["pattern_match", "ast_analysis", "import_scan",
                                 "config_parse", "llm_assisted", None]
                    },

                    # ── Mapped framework IDs ──────────────────────────────
                    "oscal_control_id": {"type": ["string", "null"]},
                    "scf_control_id":   {"type": ["string", "null"]},
                    "mapping_confidence": {"type": ["number", "null"]},

                    # ── Provenance ────────────────────────────────────────
                    "scan_run_id": {"type": "string"},
                    "project_id":  {"type": "string"},
                    "commit_sha":  {"type": ["string", "null"]},
                    "detected_at": {"type": "string", "format": "date-time"},

                    # ── VEX / compliance use ──────────────────────────────
                    "used_in_vex": {"type": "boolean", "default": False},
                    "addresses_requirement_ids": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "additionalProperties": True
            },
            "level": "moderate",
            "message": "detected_control document failed schema validation"
        },
        "indexes": [
            {"type": "persistent", "fields": ["fingerprint"],                    "unique": True,  "name": "idx_dctrl_fp"},
            {"type": "persistent", "fields": ["tenant_id", "project_id"],        "unique": False, "name": "idx_dctrl_tenant_project"},
            {"type": "persistent", "fields": ["tenant_id", "scan_run_id"],       "unique": False, "name": "idx_dctrl_tenant_run"},
            {"type": "persistent", "fields": ["control_type"],                   "unique": False, "name": "idx_dctrl_type"},
            {"type": "persistent", "fields": ["control_category"],               "unique": False, "name": "idx_dctrl_cat"},
            {"type": "persistent", "fields": ["oscal_control_id"],               "unique": False, "name": "idx_dctrl_oscal"},
            {"type": "persistent", "fields": ["scf_control_id"],                 "unique": False, "name": "idx_dctrl_scf"},
        ]
    },

    # ── evidence_packages (Fix 2: tenant_id required) ──────────────────────
    {
        "name": "evidence_packages",
        "schema": {
            "rule": {
                "type": "object",
                "required": ["package_id", "tenant_id", "project_id",
                             "scan_run_id", "generated_at", "format_version"],
                "properties": {
                    "package_id": {
                        "type": "string",
                        "description": "UUID v4. Also used as ArangoDB _key."
                    },
                    "tenant_id": {
                        "type": "string",
                        "description": "Organization/tenant ID for multi-tenant isolation"
                    },
                    "project_id":  {"type": "string"},
                    "scan_run_id": {"type": "string"},
                    "product_name":    {"type": ["string", "null"]},
                    "product_version": {"type": ["string", "null"]},
                    "commit_sha":      {"type": ["string", "null"]},

                    # ── Format ────────────────────────────────────────────
                    "format_version": {"type": "string"},
                    "target_regulation": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "e.g. ['FDA_524B', 'EU_CRA', 'IEC_62304']"
                    },

                    # ── MCP-sourced links ─────────────────────────────────
                    "github_repo":       {"type": ["string", "null"]},
                    "github_commit_url": {"type": ["string", "null"]},
                    "github_workflow_runs": {"type": "array", "items": {"type": "string"}},
                    "jira_tickets":         {"type": "array", "items": {"type": "string"}},
                    "confluence_doc_urls":  {"type": "array", "items": {"type": "string"}},

                    # ── Embedded docs ─────────────────────────────────────
                    "sbom_path":   {"type": ["string", "null"]},
                    "sbom_format": {
                        "type": ["string", "null"],
                        "enum": ["cyclonedx-1.6", "spdx-3.0", "spdx-2.3", None]
                    },
                    "vex_path":   {"type": ["string", "null"]},
                    "vex_format": {
                        "type": ["string", "null"],
                        "enum": ["csaf-2.0", "cyclonedx-1.6", None]
                    },
                    "compliance_report_path": {"type": ["string", "null"]},

                    # ── Integrity ─────────────────────────────────────────
                    "package_hash":   {"type": ["string", "null"]},
                    "signing_key_id": {"type": ["string", "null"]},
                    "signed_at":      {"type": ["string", "null"], "format": "date-time"},

                    # ── Retention / audit (EU CRA Art. 14) ───────────────
                    "retention_until": {
                        "type": ["string", "null"],
                        "format": "date-time",
                        "description": "EOL date + 10 years per CRA retention formula"
                    },
                    "submission_ready": {"type": "boolean", "default": False},
                    "submission_ready_at": {"type": ["string", "null"], "format": "date-time"},

                    "generated_at": {"type": "string", "format": "date-time"},
                    "generated_by": {"type": ["string", "null"]}
                },
                "additionalProperties": True
            },
            "level": "moderate",
            "message": "evidence_package document failed schema validation"
        },
        "indexes": [
            {"type": "persistent", "fields": ["package_id"],                    "unique": True,  "name": "idx_evpkg_id"},
            {"type": "persistent", "fields": ["tenant_id", "project_id"],       "unique": False, "name": "idx_evpkg_tenant_project"},
            {"type": "persistent", "fields": ["tenant_id", "scan_run_id"],      "unique": False, "name": "idx_evpkg_tenant_run"},
            {"type": "persistent", "fields": ["submission_ready"],              "unique": False, "name": "idx_evpkg_ready"},
            {"type": "persistent", "fields": ["retention_until"],               "unique": False, "name": "idx_evpkg_retention"},
            {"type": "persistent", "fields": ["target_regulation[*]"],          "unique": False, "name": "idx_evpkg_reg"},
        ]
    },
]


# ── Edge collections ─────────────────────────────────────────────────────────

EDGE_COLLECTIONS: list[dict[str, Any]] = [

    # ── NEW: component → vulnerability ──────────────────────────────────────
    {
        "name": "component_has_vuln",
        "from_collections": ["components"],
        "to_collections":   ["vulnerabilities"],
        "schema": {
            "rule": {
                "type": "object",
                "required": ["_from", "_to", "source"],
                "properties": {
                    "source": {
                        "type": "string",
                        "enum": ["cpe_match", "grype", "trivy", "pip_audit",
                                 "npm_audit", "syft", "scanner"]
                    },
                    "confidence":          {"type": ["number", "null"]},
                    "matched_cpe":         {"type": ["string", "null"]},
                    "match_criteria":      {"type": ["string", "null"], "enum": ["exact", "version_range", "partial", None]},
                    "scanner_run_id":      {"type": ["string", "null"]},
                    "scanner_fix_version": {"type": ["string", "null"]},
                    "epss_score_at_detection": {"type": ["number", "null"]},
                    "is_kev_at_detection":     {"type": ["boolean", "null"]},
                    "vex_status":          {"type": ["string", "null"], "enum": ["affected", "not_affected", "fixed", "under_investigation", None]},
                    "vex_justification":   {"type": ["string", "null"]},
                    "detected_at":         {"type": "string", "format": "date-time"}
                },
                "additionalProperties": True
            },
            "level": "moderate",
            "message": "component_has_vuln edge failed validation"
        },
        "indexes": [
            {"type": "persistent", "fields": ["_from"],      "unique": False, "name": "idx_chv_from"},
            {"type": "persistent", "fields": ["_to"],         "unique": False, "name": "idx_chv_to"},
            {"type": "persistent", "fields": ["source"],      "unique": False, "name": "idx_chv_source"},
            {"type": "persistent", "fields": ["vex_status"],  "unique": False, "name": "idx_chv_vex"},
            {"type": "persistent", "fields": ["is_kev_at_detection"], "unique": False, "name": "idx_chv_kev"},
        ]
    },

    # ── NEW: scan_finding → weakness (CWE) ──────────────────────────────────
    {
        "name": "finding_maps_to_weakness",
        "from_collections": ["scan_findings"],
        "to_collections":   ["weaknesses"],
        "schema": {
            "rule": {
                "type": "object",
                "required": ["_from", "_to", "source"],
                "properties": {
                    "source":     {"type": "string", "enum": ["semgrep", "bandit", "checkov", "emba", "llm_classifier", "manual"]},
                    "confidence": {"type": ["number", "null"]},
                    "cwe_id":     {"type": "string"}
                },
                "additionalProperties": False
            },
            "level": "moderate",
            "message": "finding_maps_to_weakness edge failed validation"
        },
        "indexes": [
            {"type": "persistent", "fields": ["_from"],  "unique": False, "name": "idx_fmtw_from"},
            {"type": "persistent", "fields": ["_to"],    "unique": False, "name": "idx_fmtw_to"},
            {"type": "persistent", "fields": ["source"], "unique": False, "name": "idx_fmtw_source"},
        ]
    },

    # ── NEW: scan_finding → regulatory_requirement ──────────────────────────
    {
        "name": "finding_triggers_req",
        "from_collections": ["scan_findings"],
        "to_collections":   ["regulatory_requirements"],
        "schema": {
            "rule": {
                "type": "object",
                "required": ["_from", "_to", "source"],
                "properties": {
                    "source":         {"type": "string", "enum": ["rule_engine", "llm_reg_mapper"]},
                    "confidence":     {"type": ["number", "null"]},
                    "via_cwe_id":     {"type": ["string", "null"]},
                    "mapping_rule_id": {"type": ["string", "null"]}
                },
                "additionalProperties": False
            },
            "level": "moderate",
            "message": "finding_triggers_req edge failed validation"
        },
        "indexes": [
            {"type": "persistent", "fields": ["_from"],  "unique": False, "name": "idx_ftr_from"},
            {"type": "persistent", "fields": ["_to"],    "unique": False, "name": "idx_ftr_to"},
            {"type": "persistent", "fields": ["source"], "unique": False, "name": "idx_ftr_source"},
        ]
    },

    # ── NEW: detected_control → oscal_controls | scf_controls ───────────────
    {
        "name": "detected_control_maps_to",
        "from_collections": ["detected_controls"],
        "to_collections":   ["oscal_controls", "scf_controls"],
        "schema": {
            "rule": {
                "type": "object",
                "required": ["_from", "_to", "source", "confidence"],
                "properties": {
                    "source":            {"type": "string", "enum": ["embedding_matcher", "rule_engine", "manual"]},
                    "confidence":        {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "embedding_model":   {"type": ["string", "null"]},
                    "target_collection": {"type": "string", "enum": ["oscal_controls", "scf_controls"]}
                },
                "additionalProperties": False
            },
            "level": "moderate",
            "message": "detected_control_maps_to edge failed validation"
        },
        "indexes": [
            {"type": "persistent", "fields": ["_from"],             "unique": False, "name": "idx_dcmt_from"},
            {"type": "persistent", "fields": ["_to"],               "unique": False, "name": "idx_dcmt_to"},
            {"type": "persistent", "fields": ["confidence"],        "unique": False, "name": "idx_dcmt_conf"},
            {"type": "persistent", "fields": ["target_collection"], "unique": False, "name": "idx_dcmt_target"},
        ]
    },

    # ── NEW: detected_control → component ───────────────────────────────────
    {
        "name": "control_in_component",
        "from_collections": ["detected_controls"],
        "to_collections":   ["components"],
        "schema": {
            "rule": {
                "type": "object",
                "required": ["_from", "_to", "source"],
                "properties": {
                    "source":    {"type": "string", "enum": ["scanner"]},
                    "file_path": {"type": ["string", "null"]}
                },
                "additionalProperties": False
            },
            "level": "moderate",
            "message": "control_in_component edge failed validation"
        },
        "indexes": [
            {"type": "persistent", "fields": ["_from"], "unique": False, "name": "idx_cic_from"},
            {"type": "persistent", "fields": ["_to"],   "unique": False, "name": "idx_cic_to"},
        ]
    },

    # ── NEW: scan_finding → component ───────────────────────────────────────
    {
        "name": "finding_in_component",
        "from_collections": ["scan_findings"],
        "to_collections":   ["components"],
        "schema": {
            "rule": {
                "type": "object",
                "required": ["_from", "_to", "source"],
                "properties": {
                    "source": {"type": "string", "enum": ["scanner", "cpe_match", "purl_match"]}
                },
                "additionalProperties": False
            },
            "level": "moderate",
            "message": "finding_in_component edge failed validation"
        },
        "indexes": [
            {"type": "persistent", "fields": ["_from"], "unique": False, "name": "idx_fic_from"},
            {"type": "persistent", "fields": ["_to"],   "unique": False, "name": "idx_fic_to"},
        ]
    },

    # ── NEW: evidence_package → scan_finding ────────────────────────────────
    {
        "name": "evidence_links_finding",
        "from_collections": ["evidence_packages"],
        "to_collections":   ["scan_findings"],
        "schema": {
            "rule": {
                "type": "object",
                "required": ["_from", "_to", "source"],
                "properties": {
                    "source":            {"type": "string", "enum": ["pipeline"]},
                    "included_in_report": {"type": "boolean"}
                },
                "additionalProperties": False
            },
            "level": "moderate",
            "message": "evidence_links_finding edge failed validation"
        },
        "indexes": [
            {"type": "persistent", "fields": ["_from"], "unique": False, "name": "idx_elf_from"},
            {"type": "persistent", "fields": ["_to"],   "unique": False, "name": "idx_elf_to"},
        ]
    },

    # ── NEW: evidence_package → project ─────────────────────────────────────
    {
        "name": "evidence_for_project",
        "from_collections": ["evidence_packages"],
        "to_collections":   ["projects"],
        "schema": {
            "rule": {
                "type": "object",
                "required": ["_from", "_to", "source"],
                "properties": {
                    "source": {"type": "string", "enum": ["pipeline"]}
                },
                "additionalProperties": False
            },
            "level": "moderate",
            "message": "evidence_for_project edge failed validation"
        },
        "indexes": [
            {"type": "persistent", "fields": ["_from"], "unique": False, "name": "idx_efp_from"},
            {"type": "persistent", "fields": ["_to"],   "unique": False, "name": "idx_efp_to"},
        ]
    },

    # ── NEW: project → component (Fix 1 + Fix 3) ───────────────────────────
    # Decouples component identity from project ownership. A component is a
    # global entity; a project *uses* it. Enables cross-project correlation.
    {
        "name": "project_uses_component",
        "from_collections": ["projects"],
        "to_collections":   ["components"],
        "schema": {
            "rule": {
                "type": "object",
                "required": ["_from", "_to", "source", "tenant_id"],
                "properties": {
                    "source": {
                        "type": "string",
                        "enum": ["sbom", "scanner", "manual"],
                        "description": "How the relationship was discovered"
                    },
                    "tenant_id": {
                        "type": "string",
                        "description": "Tenant isolation for cross-project queries"
                    },
                    "project_id": {
                        "type": "string",
                        "description": "Denorm of _from project for fast filtering"
                    },
                    "first_seen_at": {
                        "type": "string",
                        "format": "date-time",
                        "description": "When this project first ingested this component"
                    },
                    "last_seen_at": {
                        "type": ["string", "null"],
                        "format": "date-time"
                    },
                    "scan_run_id": {
                        "type": ["string", "null"],
                        "description": "Most recent scan run that confirmed this usage"
                    },
                    "version_pinned": {
                        "type": ["boolean", "null"],
                        "description": "True if project pins this exact version"
                    },
                    "dependency_type": {
                        "type": ["string", "null"],
                        "enum": ["direct", "transitive", "dev", "optional", "build", None]
                    }
                },
                "additionalProperties": False
            },
            "level": "moderate",
            "message": "project_uses_component edge failed validation"
        },
        "indexes": [
            {"type": "persistent", "fields": ["_from"],                  "unique": False, "name": "idx_puc_from"},
            {"type": "persistent", "fields": ["_to"],                    "unique": False, "name": "idx_puc_to"},
            {"type": "persistent", "fields": ["tenant_id"],              "unique": False, "name": "idx_puc_tenant"},
            {"type": "persistent", "fields": ["tenant_id", "project_id"], "unique": False, "name": "idx_puc_tenant_project"},
        ]
    },

    # ── ACTIVATE from v2.1: component → cpe_entries ─────────────────────────
    {
        "name": "matched_by_cpe",
        "from_collections": ["components"],
        "to_collections":   ["cpe_entries"],
        "schema": {
            "rule": {
                "type": "object",
                "required": ["_from", "_to", "source"],
                "properties": {
                    "source":     {"type": "string", "enum": ["cpe_resolver", "sbom_direct"]},
                    "confidence": {"type": ["number", "null"]},
                    "match_type": {"type": ["string", "null"], "enum": ["exact", "version_range", "vendor_product_only", None]}
                },
                "additionalProperties": False
            },
            "level": "moderate",
            "message": "matched_by_cpe edge failed validation"
        },
        "indexes": [
            {"type": "persistent", "fields": ["_from"],  "unique": False, "name": "idx_mbc_from"},
            {"type": "persistent", "fields": ["_to"],    "unique": False, "name": "idx_mbc_to"},
            {"type": "persistent", "fields": ["source"], "unique": False, "name": "idx_mbc_source"},
        ]
    },

    # ── ACTIVATE from v2.1: component → component (dependency graph) ────────
    {
        "name": "depends_on",
        "from_collections": ["components"],
        "to_collections":   ["components"],
        "schema": {
            "rule": {
                "type": "object",
                "required": ["_from", "_to", "source"],
                "properties": {
                    "source":             {"type": "string", "enum": ["cyclonedx", "spdx", "syft", "grype", "cargo", "npm", "pip", "conan"]},
                    "dependency_type":    {"type": ["string", "null"], "enum": ["direct", "transitive", "dev", "optional", "build", None]},
                    "version_constraint": {"type": ["string", "null"]}
                },
                "additionalProperties": False
            },
            "level": "moderate",
            "message": "depends_on edge failed validation"
        },
        "indexes": [
            {"type": "persistent", "fields": ["_from"],           "unique": False, "name": "idx_dep_from"},
            {"type": "persistent", "fields": ["_to"],             "unique": False, "name": "idx_dep_to"},
            {"type": "persistent", "fields": ["dependency_type"], "unique": False, "name": "idx_dep_type"},
        ]
    },

    # ── ACTIVATE from v2.1: component → licenses ────────────────────────────
    {
        "name": "licensed_under",
        "from_collections": ["components"],
        "to_collections":   ["licenses"],
        "schema": {
            "rule": {
                "type": "object",
                "required": ["_from", "_to", "source"],
                "properties": {
                    "source":             {"type": "string", "enum": ["sbom", "scanner", "scancode"]},
                    "license_expression": {"type": ["string", "null"]},
                    "copyleft":           {"type": ["boolean", "null"]},
                    "commercial_use":     {"type": ["boolean", "null"]},
                    "compliance_risk":    {"type": ["string", "null"], "enum": ["low", "medium", "high", None]}
                },
                "additionalProperties": False
            },
            "level": "moderate",
            "message": "licensed_under edge failed validation"
        },
        "indexes": [
            {"type": "persistent", "fields": ["_from"],           "unique": False, "name": "idx_lu_from"},
            {"type": "persistent", "fields": ["_to"],             "unique": False, "name": "idx_lu_to"},
            {"type": "persistent", "fields": ["compliance_risk"], "unique": False, "name": "idx_lu_risk"},
        ]
    },

    # ── ACTIVATE from v2.1: component → eol_products ────────────────────────
    {
        "name": "component_eol_status",
        "from_collections": ["components"],
        "to_collections":   ["eol_products"],
        "schema": {
            "rule": {
                "type": "object",
                "required": ["_from", "_to", "source"],
                "properties": {
                    "source":       {"type": "string", "enum": ["endoflife.date", "vendor", "nvd", "manual"]},
                    "eol_date":     {"type": ["string", "null"]},
                    "eol_lts_until": {"type": ["string", "null"]},
                    "is_eol":       {"type": ["boolean", "null"]},
                    "support_tier": {"type": ["string", "null"], "enum": ["active", "maintenance", "eol", "lts", None]}
                },
                "additionalProperties": False
            },
            "level": "moderate",
            "message": "component_eol_status edge failed validation"
        },
        "indexes": [
            {"type": "persistent", "fields": ["_from"],  "unique": False, "name": "idx_ces_from"},
            {"type": "persistent", "fields": ["_to"],    "unique": False, "name": "idx_ces_to"},
            {"type": "persistent", "fields": ["is_eol"], "unique": False, "name": "idx_ces_eol"},
        ]
    },
]


# ── Named graph extensions ───────────────────────────────────────────────────

GRAPH_EDGE_DEFINITIONS_V2_2: list[dict[str, Any]] = [
    {
        "edge_collection": ec["name"],
        "from_vertex_collections": ec["from_collections"],
        "to_vertex_collections":   ec["to_collections"]
    }
    for ec in EDGE_COLLECTIONS
]


# ── Tier 1 AQL Template Registry ─────────────────────────────────────────────

TIER1_AQL_TEMPLATES: dict[str, dict[str, Any]] = {

    # ── Original 6 templates (updated with tenant_id) ─────────────────────

    "component_regulatory_blast_radius": {
        "description": "All regulatory requirements violated by a given component "
                       "via CVE traversal.",
        "params": ["tenant_id", "project_id", "purl"],
        "aql": """
FOR edge IN project_uses_component
  FILTER edge.tenant_id == @tenant_id AND edge.project_id == @project_id
  LET comp = DOCUMENT(edge._to)
  FILTER comp.purl == @purl
  FOR vuln IN 1..1 OUTBOUND comp component_has_vuln
    FOR req IN 1..1 OUTBOUND vuln violates_requirement
      COLLECT req_id = req._key,
              reg    = req.framework,
              title  = req.description
      RETURN { req_id, reg, title,
               vuln_count: COUNT(vuln._key) }
""",
        "routing": "tier1",
        "compliance_critical": True
    },

    "sast_finding_attack_chain": {
        "description": "CWE → ATT&CK → D3FEND traversal for a given scan_finding.",
        "params": ["finding_fingerprint"],
        "aql": """
FOR f IN scan_findings
  FILTER f.fingerprint == @finding_fingerprint
  FOR w IN 1..1 OUTBOUND f finding_maps_to_weakness
    FOR t IN 1..1 OUTBOUND w technique_exploits_weakness
      LET mitigations = (
        FOR d IN 1..1 OUTBOUND t d3fend_counters_technique RETURN d
      )
      RETURN {
        weakness:   { id: w.cwe_id, name: w.name },
        technique:  { id: t.technique_id, name: t.name },
        mitigations: mitigations[*].{ id: _key, name: name }
      }
""",
        "routing": "tier1",
        "compliance_critical": False
    },

    "control_gap_analysis": {
        "description": "Violated requirements with NO detected control mitigating them.",
        "params": ["tenant_id", "scan_run_id", "project_id"],
        "aql": """
LET violated_req_ids = (
  FOR f IN scan_findings
    FILTER f.tenant_id == @tenant_id
    FILTER f.scan_run_id == @scan_run_id AND f.project_id == @project_id
    FOR req IN 1..1 OUTBOUND f finding_triggers_req
      RETURN DISTINCT req._key
)
LET covered_req_ids = (
  FOR dc IN detected_controls
    FILTER dc.tenant_id == @tenant_id
    FILTER dc.scan_run_id == @scan_run_id AND dc.project_id == @project_id
    FOR ctrl IN 1..1 OUTBOUND dc detected_control_maps_to
      FOR req IN 1..1 OUTBOUND ctrl maps_to_requirement
        RETURN DISTINCT req._key
)
FOR req_id IN MINUS(violated_req_ids, covered_req_ids)
  FOR req IN regulatory_requirements
    FILTER req._key == req_id
    RETURN { req_id, framework: req.framework,
             title: req.description, risk_category: req.risk_category }
""",
        "routing": "tier1",
        "compliance_critical": True
    },

    "firmware_kev_exposure": {
        "description": "Firmware components with KEV-listed CVEs.",
        "params": ["tenant_id", "project_id"],
        "aql": """
FOR edge IN project_uses_component
  FILTER edge.tenant_id == @tenant_id AND edge.project_id == @project_id
  LET comp = DOCUMENT(edge._to)
  FILTER comp.firmware_layer != null
  FOR vuln IN 1..1 OUTBOUND comp component_has_vuln
    FOR kev IN 1..1 OUTBOUND vuln exploited_in_wild
      LET epss = FIRST(
        FOR e IN 1..1 OUTBOUND vuln has_epss
          SORT e.score_date DESC LIMIT 1 RETURN e.epss_score
      )
      RETURN {
        purl:           comp.purl,
        firmware_layer: comp.firmware_layer,
        cve_id:         vuln.cve_id,
        cvss:           vuln.cvss_v3_score,
        epss:           epss,
        kev_date_added: kev.date_added
      }
""",
        "routing": "tier1",
        "compliance_critical": True
    },

    "vex_not_affected_candidates": {
        "description": "Components with CVE exposure but no SAST finding for CWE — "
                       "candidates for not_affected VEX.",
        "params": ["tenant_id", "project_id", "scan_run_id"],
        "aql": """
FOR edge IN project_uses_component
  FILTER edge.tenant_id == @tenant_id AND edge.project_id == @project_id
  LET comp = DOCUMENT(edge._to)
  FOR vuln, chv_edge IN 1..1 OUTBOUND comp component_has_vuln
    FILTER chv_edge.vex_status == null OR chv_edge.vex_status == 'under_investigation'
    LET cwe_ids_for_vuln = (
      FOR w IN 1..1 OUTBOUND vuln has_weakness RETURN w.cwe_id
    )
    LET findings_for_cwe = (
      FOR f IN scan_findings
        FILTER f.tenant_id   == @tenant_id
        FILTER f.scan_run_id == @scan_run_id
        FILTER f.project_id  == @project_id
        FILTER LENGTH(INTERSECTION(f.cwe_ids, cwe_ids_for_vuln)) > 0
        RETURN f._key
    )
    FILTER LENGTH(findings_for_cwe) == 0
    RETURN {
      purl:        comp.purl,
      cve_id:      vuln.cve_id,
      cwe_ids:     cwe_ids_for_vuln,
      vex_status_was: chv_edge.vex_status,
      vex_justification: "vulnerable_code_not_present",
      auto_derivable: true
    }
""",
        "routing": "tier1",
        "compliance_critical": True
    },

    "compliance_delta_between_runs": {
        "description": "New requirements violated in run B vs run A (regression/remediation).",
        "params": ["tenant_id", "project_id", "scan_run_id_a", "scan_run_id_b"],
        "aql": """
LET reqs_a = (
  FOR f IN scan_findings
    FILTER f.tenant_id == @tenant_id
    FILTER f.scan_run_id == @scan_run_id_a AND f.project_id == @project_id
    FOR req IN 1..1 OUTBOUND f finding_triggers_req
      RETURN DISTINCT req._key
)
LET reqs_b = (
  FOR f IN scan_findings
    FILTER f.tenant_id == @tenant_id
    FILTER f.scan_run_id == @scan_run_id_b AND f.project_id == @project_id
    FOR req IN 1..1 OUTBOUND f finding_triggers_req
      RETURN DISTINCT req._key
)
RETURN {
  regressions:  MINUS(reqs_b, reqs_a),
  remediations: MINUS(reqs_a, reqs_b),
  persistent:   INTERSECTION(reqs_a, reqs_b)
}
""",
        "routing": "tier1",
        "compliance_critical": True
    },

    # ── Fix 3: Cross-project Tier 1 templates ─────────────────────────────

    "shared_component_blast_radius": {
        "description": "All projects using a given component across the tenant, "
                       "with union of their regulatory violations. "
                       "Answers: 'N projects share lodash@4.17.20, collectively "
                       "triggering M distinct CRA obligations.'",
        "params": ["tenant_id", "purl"],
        "aql": """
FOR comp IN components
  FILTER comp.purl == @purl
  LET project_edges = (
    FOR edge IN INBOUND comp project_uses_component
      FILTER edge.tenant_id == @tenant_id
      LET proj = DOCUMENT(edge._from)
      RETURN { project_id: proj._key, project_name: proj.name,
               first_seen: edge.first_seen_at }
  )
  LET violations = (
    FOR vuln IN 1..1 OUTBOUND comp component_has_vuln
      FOR req IN 1..1 OUTBOUND vuln violates_requirement
        RETURN DISTINCT { req_id: req._key, framework: req.framework,
                          title: req.description }
  )
  RETURN {
    purl:             comp.purl,
    component_name:   comp.name,
    version:          comp.version,
    project_count:    LENGTH(project_edges),
    projects:         project_edges,
    violation_count:  LENGTH(violations),
    violations:       violations,
    eol_date:         comp.eol_date,
    firmware_layer:   comp.firmware_layer
  }
""",
        "routing": "tier1",
        "compliance_critical": True
    },

    "cross_project_weakness_prevalence": {
        "description": "Which projects have scan_findings for a given CWE, "
                       "and which have compensating controls. "
                       "Answers: 'CWE-78 present in 4/7 projects, only 2 have "
                       "script execution analysis controls.'",
        "params": ["tenant_id", "cwe_id"],
        "aql": """
LET cwe_key = CONCAT("CWE_", SUBSTITUTE(@cwe_id, "CWE-", ""))
LET cwe_node = DOCUMENT(CONCAT("weaknesses/", cwe_key))

LET affected_projects = (
  FOR f IN scan_findings
    FILTER f.tenant_id == @tenant_id
    FILTER @cwe_id IN f.cwe_ids
    COLLECT project_id = f.project_id WITH COUNT INTO finding_count
    LET has_control = LENGTH(
      FOR dc IN detected_controls
        FILTER dc.tenant_id == @tenant_id AND dc.project_id == project_id
        FOR ctrl_edge IN OUTBOUND dc detected_control_maps_to
          FOR req_edge IN OUTBOUND ctrl_edge maps_to_requirement
            FILTER req_edge._key IN (
              FOR w_edge IN INBOUND cwe_node maps_to_requirement
                RETURN w_edge._key
            )
            LIMIT 1 RETURN 1
    ) > 0
    RETURN {
      project_id:    project_id,
      finding_count: finding_count,
      has_compensating_control: has_control
    }
)
RETURN {
  cwe_id:              @cwe_id,
  cwe_name:            cwe_node.name,
  total_affected:      LENGTH(affected_projects),
  with_controls:       LENGTH(FOR p IN affected_projects FILTER p.has_compensating_control RETURN 1),
  without_controls:    LENGTH(FOR p IN affected_projects FILTER NOT p.has_compensating_control RETURN 1),
  projects:            affected_projects
}
""",
        "routing": "tier1",
        "compliance_critical": True
    },

    "portfolio_compliance_score": {
        "description": "Compliance score per project per scan_run, trending over time. "
                       "Feeds the Complira Pass dashboard at portfolio level.",
        "params": ["tenant_id"],
        "aql": """
FOR run IN scan_runs
  FILTER run.tenant_id == @tenant_id
  FILTER run.status == "completed"
  FILTER run.compliance_score != null
  SORT run.started_at DESC
  COLLECT project_id = run.project_id INTO runs_group
  LET latest = runs_group[0].run
  LET previous = LENGTH(runs_group) > 1 ? runs_group[1].run : null
  LET trend = previous != null AND previous.compliance_score != null
    ? latest.compliance_score - previous.compliance_score
    : null
  RETURN {
    project_id:       project_id,
    latest_score:     latest.compliance_score,
    previous_score:   previous.compliance_score,
    trend:            trend,
    latest_run_id:    latest.scan_run_id,
    latest_run_date:  latest.started_at,
    total_runs:       LENGTH(runs_group),
    violated_reqs:    latest.violated_requirements
  }
""",
        "routing": "tier1",
        "compliance_critical": True
    },
}


# ── Ingestion normalisation constants ─────────────────────────────────────────

INGESTION_NORMALISATION = {

    "semgrep_severity_map": {
        "ERROR":    "high",
        "WARNING":  "medium",
        "INFO":     "info",
        "NOTE":     "info",
        "CRITICAL": "critical",
        "HIGH":     "high",
        "MEDIUM":   "medium",
        "LOW":      "low",
    },

    "semgrep_category_to_finding_type": {
        "INJECTION":          "sast",
        "XSS":                "sast",
        "SENSITIVE_DATA":     "sast",
        "AUTHENTICATION":     "sast",
        "CRYPTO_WEAKNESS":    "sast",
        "SECURITY_MISCONFIG": "iac_misconfig",
        "BROKEN_ACCESS":      "iac_misconfig",
        "SUPPLY_CHAIN":       "supply_chain",
    },

    "cwe_extract_pattern": r"(CWE-\d+)",
    "cve_validate_pattern": r"^CVE-\d{4}-\d{4,}$",

    "purl_fallback_template": "pkg:generic/{name}@{version}?bom_ref={bom_ref_hash}",

    "semgrep_source_field":          "categories",
    "semgrep_cwe_field":             "cwe",
    "semgrep_severity_field":        "severity",
    "semgrep_fingerprint_fields":    ["rule_id", "file_path", "line_number"],
    "semgrep_vuln_category_field":   "vulnerability_category",

    "cwe_source_values": {
        "tool_direct":  "deterministic",
        "extracted":    "deterministic",
        "llm_inferred": "probabilistic",
    },

    # Fix 2: tenant_id is a required bind variable for all evidence queries
    "required_bind_variables": ["tenant_id"],
}


# ── Schema change log ─────────────────────────────────────────────────────────

SCHEMA_VERSION = "2.2.1"
SCHEMA_CHANGES = [
    {"version": "2.2",   "type": "new_collection",      "name": "scan_runs",                "description": "Pipeline execution metadata"},
    {"version": "2.2",   "type": "new_collection",      "name": "scan_findings",             "description": "Universal scanner finding node"},
    {"version": "2.2",   "type": "new_collection",      "name": "detected_controls",         "description": "Positive security control detections"},
    {"version": "2.2",   "type": "new_collection",      "name": "evidence_packages",          "description": "FDA/CRA evidence bundle"},
    {"version": "2.2",   "type": "activate_collection", "name": "components",                 "description": "SBOM component nodes (global, purl-keyed)"},
    {"version": "2.2",   "type": "new_edge",            "name": "component_has_vuln",         "description": "Component→CVE link with VEX status"},
    {"version": "2.2",   "type": "new_edge",            "name": "finding_maps_to_weakness",   "description": "CWE bridge for ATT&CK traversal"},
    {"version": "2.2",   "type": "new_edge",            "name": "finding_triggers_req",       "description": "Finding→requirement via CWE rule engine"},
    {"version": "2.2",   "type": "new_edge",            "name": "detected_control_maps_to",   "description": "Control→OSCAL/SCF mapping"},
    {"version": "2.2",   "type": "new_edge",            "name": "control_in_component",       "description": "Control scoped to component"},
    {"version": "2.2",   "type": "new_edge",            "name": "finding_in_component",       "description": "Finding scoped to component"},
    {"version": "2.2",   "type": "new_edge",            "name": "evidence_links_finding",     "description": "Evidence→finding traceability"},
    {"version": "2.2",   "type": "new_edge",            "name": "evidence_for_project",       "description": "Evidence→project ownership"},
    {"version": "2.2.1", "type": "new_edge",            "name": "project_uses_component",     "description": "Fix 1: project→component usage (global components)"},
    {"version": "2.2",   "type": "activate_edge",       "name": "matched_by_cpe",             "description": "Component→CPE entry"},
    {"version": "2.2",   "type": "activate_edge",       "name": "depends_on",                 "description": "Component dependency graph"},
    {"version": "2.2",   "type": "activate_edge",       "name": "licensed_under",             "description": "Component→license"},
    {"version": "2.2",   "type": "activate_edge",       "name": "component_eol_status",       "description": "Component→EOL entry"},
    {"version": "2.2.1", "type": "architecture_fix",    "name": "tenant_id_required",         "description": "Fix 2: tenant_id added to all evidence collections"},
    {"version": "2.2.1", "type": "architecture_fix",    "name": "global_components",           "description": "Fix 1: components decoupled from project ownership"},
    {"version": "2.2.1", "type": "new_templates",       "name": "cross_project_tier1",         "description": "Fix 3: 3 cross-project Tier 1 AQL templates"},
]


# ── Migration runner ──────────────────────────────────────────────────────────

def run_migration(host: str, db_name: str, username: str,
                  password: str, dry_run: bool = False) -> None:
    """
    Apply v2.2.1 schema changes to a running ArangoDB instance.
    Idempotent: existing collections/indexes are skipped, not overwritten.
    """
    try:
        from arango import ArangoClient
    except ImportError:
        print("ERROR: python-arango not installed. Run: pip install python-arango")
        sys.exit(1)

    client = ArangoClient(hosts=host)
    db = client.db(db_name, username=username, password=password)

    existing_collections = {c["name"] for c in db.collections()}
    graph = db.graph("complira_graph") if db.has_graph("complira_graph") else None

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Applying schema v{SCHEMA_VERSION}...")
    print(f"Database : {db_name} @ {host}")
    print(f"Graph    : {'complira_graph (found)' if graph else 'complira_graph (NOT FOUND — will create)'}")
    print()

    # 1. Document collections
    for coll_def in DOCUMENT_COLLECTIONS:
        name = coll_def["name"]
        if name in existing_collections:
            print(f"  [SKIP]   collection '{name}' already exists")
            if not dry_run:
                coll = db.collection(name)
                try:
                    coll.configure(schema=coll_def["schema"])
                    print(f"           └─ schema validator updated")
                except Exception as e:
                    print(f"           └─ WARNING: schema update failed: {e}")
        else:
            print(f"  [CREATE] collection '{name}'")
            if not dry_run:
                db.create_collection(name, schema=coll_def["schema"])

        # Indexes
        if not dry_run:
            coll = db.collection(name)
            existing_indexes = {idx["name"] for idx in coll.indexes() if "name" in idx}
            for idx in coll_def.get("indexes", []):
                if idx["name"] not in existing_indexes:
                    print(f"  [INDEX]  {name}.{idx['name']}")
                    coll.add_persistent_index(
                        fields=idx["fields"],
                        unique=idx.get("unique", False),
                        name=idx["name"]
                    )

    print()

    # 2. Edge collections
    for ec_def in EDGE_COLLECTIONS:
        name = ec_def["name"]
        if name in existing_collections:
            print(f"  [SKIP]   edge collection '{name}' already exists")
            if not dry_run:
                coll = db.collection(name)
                try:
                    coll.configure(schema=ec_def["schema"])
                    print(f"           └─ schema validator updated")
                except Exception as e:
                    print(f"           └─ WARNING: schema update failed: {e}")
        else:
            print(f"  [CREATE] edge collection '{name}'")
            if not dry_run:
                db.create_collection(name, edge=True, schema=ec_def["schema"])

        # Indexes
        if not dry_run:
            coll = db.collection(name)
            existing_indexes = {idx["name"] for idx in coll.indexes() if "name" in idx}
            for idx in ec_def.get("indexes", []):
                if idx["name"] not in existing_indexes:
                    print(f"  [INDEX]  {name}.{idx['name']}")
                    coll.add_persistent_index(
                        fields=idx["fields"],
                        unique=idx.get("unique", False),
                        name=idx["name"]
                    )

    print()

    # 3. Named graph edge definitions
    if graph and not dry_run:
        existing_edge_defs = {
            ed["edge_collection"]
            for ed in graph.edge_definitions()
        }
        for ed in GRAPH_EDGE_DEFINITIONS_V2_2:
            ec_name = ed["edge_collection"]
            if ec_name not in existing_edge_defs:
                print(f"  [GRAPH]  adding edge def '{ec_name}' to complira_graph")
                graph.create_edge_definition(**ed)
            else:
                print(f"  [SKIP]   edge def '{ec_name}' already in graph")
    elif not graph and not dry_run:
        print("  [WARN]   complira_graph not found — create graph manually "
              "and re-run to register edge definitions")
    else:
        for ed in GRAPH_EDGE_DEFINITIONS_V2_2:
            print(f"  [DRY]    would add edge def: {ed['edge_collection']}")

    print()
    print(f"{'[DRY RUN] ' if dry_run else ''}Schema v{SCHEMA_VERSION} migration complete.")
    print(f"  {len(DOCUMENT_COLLECTIONS)} document collections processed")
    print(f"  {len(EDGE_COLLECTIONS)} edge collections processed")
    print(f"  {len(TIER1_AQL_TEMPLATES)} Tier 1 AQL templates defined (register separately)")


def print_summary() -> None:
    """Print a human-readable schema summary."""
    print(f"\nComplira KG Schema v{SCHEMA_VERSION} — Summary\n{'='*56}")

    print("\nDocument Collections:")
    for c in DOCUMENT_COLLECTIONS:
        required = c["schema"]["rule"].get("required", [])
        print(f"  {c['name']:30s}  required={required}")

    print("\nEdge Collections:")
    col_w = max(len(e["name"]) for e in EDGE_COLLECTIONS) + 2
    for e in EDGE_COLLECTIONS:
        frm = ", ".join(e["from_collections"])
        to  = ", ".join(e["to_collections"])
        print(f"  {e['name']:{col_w}s}  {frm} → {to}")

    print(f"\nTier 1 AQL Templates ({len(TIER1_AQL_TEMPLATES)}):")
    for k, v in TIER1_AQL_TEMPLATES.items():
        cc = "✓ compliance-critical" if v["compliance_critical"] else ""
        print(f"  {k:48s}  {cc}")

    print("\nArchitecture Fixes Applied:")
    print("  Fix 1: components are global (no project_id); projects link via project_uses_component edge")
    print("  Fix 2: tenant_id required on scan_runs, scan_findings, detected_controls, evidence_packages")
    print("  Fix 3: 3 cross-project Tier 1 AQL templates for portfolio intelligence")

    print("\nSchema Change Log:")
    for ch in SCHEMA_CHANGES:
        print(f"  [{ch['type']:20s}]  {ch['name']:35s}  {ch['description']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply Complira KG schema v2.2.1")
    parser.add_argument("--host",     default="http://localhost:8529")
    parser.add_argument("--db",       default="complira_graph")
    parser.add_argument("--user",     default="root")
    parser.add_argument("--password", default="")
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--summary",  action="store_true")
    args = parser.parse_args()

    if args.summary:
        print_summary()
    else:
        run_migration(args.host, args.db, args.user, args.password, args.dry_run)
