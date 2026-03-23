"""
Complira RAG Chat — full streaming agentic loop with AQL-backed tools.

POST /v1/chat/stream
  Body:     {"messages": [{"role": "user", "content": "..."}, ...]}
  Response: text/event-stream SSE

Agentic loop (true streaming throughout, not hybrid):
  1. Stream from Claude — yield text tokens as they arrive
  2. Detect tool_use blocks in the stream via content_block events
  3. Accumulate input_json_delta fragments into complete tool inputs
  4. On content_block_stop for a tool block: execute AQL in threadpool
  5. Inject tool_result → loop until Claude stops calling tools
  6. MAX_LOOPS=6 guard prevents infinite tool spirals

Extend: add an entry to COMPLIRA_TOOLS + _TOOL_REGISTRY. No other changes needed.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.core.config import load_cloud_settings
from api.core.database import get_reference_db
from api.core.security import Customer, get_current_customer

_settings = load_cloud_settings()

log = logging.getLogger(__name__)
router = APIRouter()

MODEL = "claude-sonnet-4-6"
MAX_LOOPS = 6       # maximum tool-call rounds per conversation turn
MAX_TOKENS = 4096   # Claude only generates JSON data — HTML rendered server-side

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are Complira, a cybersecurity intelligence assistant for security, engineering, compliance, and executive stakeholders.

You have real-time access to live vulnerability and compliance data via query tools.
ALWAYS call a tool before answering questions about findings, components, compliance, or CVE details.
Never invent numbers, CVE IDs, component names, or regulatory statuses.

## Tool routing guide — use the closest match, always call something

| User says | Tool |
|-----------|------|
| "executive summary", "overall posture", "how many findings" | get_vulnerability_summary |
| "show me critical/high findings", "top risks", "urgent attention" | get_critical_findings |
| "firmware findings", "npm findings", "EPSS > 0.7", "patchable only", "open 30+ days" | search_findings |
| "tell me about CVE-X", "is CVE-X in our stack" | get_cve_detail + get_regulatory_blast_radius |
| "blast radius of CVE-X", "regulatory impact of CVE-X" | get_regulatory_blast_radius |
| "where is openssl?", "find log4j", "is this component in multiple repos?" | search_components |
| "what weaknesses dominate?", "CWE breakdown" | get_cwe_breakdown |
| "ATT&CK exposure", "what techniques can attackers use?" | get_attack_surface |
| "compliance posture", "framework violations" | get_compliance_posture |
| "NIST 800-53 coverage", "control families" | get_nist_control_coverage |
| "what changed since last scan?", "what's new this week?" | get_new_findings |
| "scanner comparison", "ecosystem breakdown", "npm vs java findings" | get_ecosystem_breakdown |
| "which project is riskiest?", "per project breakdown" | get_project_risk_breakdown |
| "actively exploited", "KEV findings", "ransomware-linked" | get_kev_exposure |
| "IAM blast radius", "cloud permissions if X is exploited" | get_iam_blast_radius |
| "EPSS rising", "what's becoming more dangerous?" | get_epss_rising_findings |
| "scan history", "trend over time" | get_scan_trend |
| "FAIR analysis", "annualised loss", "ALE", "VaR", "financial risk of CVE" | get_fair_analysis |
| "control effectiveness", "FAIR-CAM", "resistance score", "patch management maturity" | get_control_effectiveness |
| "penalty exposure", "regulatory fines", "HIPAA penalty", "CRA fine", "FDA fine" | get_penalty_exposure |
| "ROI of patching", "cost-benefit of fixing", "remediation value" | get_remediation_roi |
| "risk heatmap", "exploit chain diagram", "attack path visual", "risk matrix", "likelihood vs impact chart" | get_risk_heatmap_data (ALWAYS call BEFORE emit_artifact for any heatmap/exploit-chain visual — without it emit_artifact renders zeros) |
| user asks to BUILD/CREATE/GENERATE a dashboard, report, heatmap, slides | emit_artifact (after data tools) |

## Multi-tool answers
- "What should I fix first?" → get_vulnerability_summary + get_kev_exposure + get_critical_findings
- "Full CVE profile for Log4Shell" → get_cve_detail + get_regulatory_blast_radius + get_iam_blast_radius
- "Compliance health" → get_compliance_posture + get_nist_control_coverage

## Response style
- Lead with the most urgent finding or risk
- Use markdown tables for finding lists
- **Bold** CVE IDs, severity labels, and regulatory articles
- ⚠️ flag CISA KEV findings — these are actively exploited
- For EU CRA Art. 14 KEV: always show the 24h / 72h / 14-day notification clock
- For ATT&CK: ONLY list techniques directly enabled by this CVE's exploitation vector — not post-exploitation steps the attacker hasn't taken yet
- For NIST 800-53: list the 5-8 most directly implicated controls — not every possible family
- Close every answer with 1-3 prioritised "Recommended Actions" (P0 / P1 / P2)

## Artifacts
When user asks to build/generate/create/visualize a dashboard, report, heatmap, or slides:
1. Call data tools first. 2. Call emit_artifact with subtype + title + data object. 3. Confirm in 2-3 sentences.
For FAIR report include: cve_id, cvss, epss, in_kev, tef_pct, tc_pct, lm_low_usd, lm_high_usd, ale_usd, risk_tier, cwe_ids, controls_count, findings, projects, kev_list, frameworks, summary.

## What makes Complira different
Graph traversal: CVE → CWE → ATT&CK → NIST 800-53 → regulatory requirement in one query.
A single exploit surfaces obligations across FDA, EU CRA, IEC 62304, ISO 21434 simultaneously.
IAM blast radius connects CVE exploitation directly to cloud privilege escalation chains.
No other tool draws these connections deterministically from ground-truth scanner data."""

# ---------------------------------------------------------------------------
# Tool definitions sent to Claude
# ---------------------------------------------------------------------------

COMPLIRA_TOOLS: list[dict] = [
    {
        "name": "get_vulnerability_summary",
        "description": (
            "Overall vulnerability posture: total findings, severity breakdown, "
            "CISA KEV count, and findings with EPSS ≥ 0.5. Use for executive summary questions."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_critical_findings",
        "description": (
            "Top N critical/high findings sorted by EPSS then CVSS. "
            "Returns: CVE ID, severity, CVSS, EPSS, KEV flag, affected component, "
            "LLM risk summary, blast radius score, triage status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max findings (default 10)", "default": 10}
            },
            "required": [],
        },
    },
    {
        "name": "get_kev_exposure",
        "description": (
            "All CISA Known Exploited Vulnerabilities present in this tenant's SBOM. "
            "Returns CVE ID, component, KEV date added, ransomware association, "
            "and EU CRA Article 14 notification status. Use for active threat questions."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_top_affected_components",
        "description": (
            "Software components ranked by critical/high CVE count. "
            "Shows purl, name, version, critical count, high count, KEV count. "
            "Use for supply chain risk questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max components (default 10)", "default": 10}
            },
            "required": [],
        },
    },
    {
        "name": "get_compliance_posture",
        "description": (
            "NIST 800-53 and regulatory compliance status: "
            "detected controls (Checkov PASSED) vs violations per framework. "
            "Use for 'how are we doing on compliance' questions."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_regulatory_blast_radius",
        "description": (
            "For a specific CVE: traverse the knowledge graph chain "
            "(CVE → CWE → CAPEC → ATT&CK → NIST 800-53 → regulatory requirement) "
            "and return ALL regulatory requirements triggered across every framework. "
            "This is Complira's unique differentiator — ALWAYS call this when a CVE is mentioned."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cve_id": {"type": "string", "description": "e.g. CVE-2021-44228"}
            },
            "required": ["cve_id"],
        },
    },
    {
        "name": "get_scan_trend",
        "description": (
            "Finding counts per scan run, newest first. Shows whether posture is improving."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Scan runs to include (default 10)", "default": 10}
            },
            "required": [],
        },
    },
    {
        "name": "get_project_risk_breakdown",
        "description": (
            "Per-project critical/high/medium/low/KEV finding counts with a computed risk score. "
            "Use for 'which project is most exposed' questions."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_nist_control_coverage",
        "description": (
            "NIST 800-53 control family coverage: per family (AC, SC, AU, SI, RA…) "
            "how many controls are positively detected vs violated. "
            "Use for 'which control families have gaps' questions."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_epss_rising_findings",
        "description": (
            "Findings whose EPSS exploit probability is trending upward (epss_trend=rising). "
            "These are CVEs becoming more likely to be exploited — high priority even at medium CVSS. "
            "Use for 'what's becoming more dangerous' questions."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "search_findings",
        "description": (
            "Flexible finding filter — use for any question with a filter condition. "
            "Handles: specific severity, a single project, a scanner, ecosystem (npm/pom/yocto/iac), "
            "KEV-only, EPSS threshold, whether a fix exists, or findings older than N days. "
            "Examples: 'firmware findings' → project_id; 'EPSS > 0.7' → epss_min=0.7; "
            "'everything patchable' → has_fix=true; 'HIGH npm findings' → severities=['HIGH'], ecosystem='npm'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "severities": {"type": "array", "items": {"type": "string"}, "description": "CRITICAL, HIGH, MEDIUM, LOW"},
                "project_id": {"type": "string", "description": "Filter to one project"},
                "scanner": {"type": "string", "description": "trivy, grype, checkov, prowler, semgrep"},
                "ecosystem": {"type": "string", "description": "npm, pom, yocto, iac"},
                "kev_only": {"type": "boolean", "default": False},
                "epss_min": {"type": "number", "description": "Minimum EPSS score 0.0-1.0"},
                "has_fix": {"type": "boolean", "description": "true=only patchable; false=only unpatched"},
                "older_than_days": {"type": "integer"},
                "limit": {"type": "integer", "default": 20},
            },
            "required": [],
        },
    },
    {
        "name": "get_cve_detail",
        "description": (
            "Full profile of a single CVE: description, max CVSS/EPSS, KEV status, "
            "every finding across all projects, affected components and versions, fix availability. "
            "Use when user asks about a specific CVE: 'tell me about CVE-X', 'is CVE-X in our stack'. "
            "Call alongside get_regulatory_blast_radius for a complete CVE answer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"cve_id": {"type": "string", "description": "e.g. CVE-2021-44228"}},
            "required": ["cve_id"],
        },
    },
    {
        "name": "search_components",
        "description": (
            "Find a software component by name (partial, case-insensitive) across all projects. "
            "Returns which repos it appears in, versions, CVE count, KEV count, cross_repo flag. "
            "Use for: 'is openssl in multiple repos?', 'where is log4j used?', 'find all uses of curl'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Partial component name"}},
            "required": ["name"],
        },
    },
    {
        "name": "get_cwe_breakdown",
        "description": (
            "Groups findings by CWE weakness category ranked by frequency. "
            "Each row: CWE ID, name, count, severity breakdown, sample CVEs, primary ATT&CK technique. "
            "Use for: 'what weaknesses are most common?', 'injection vs deserialization?'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 15}},
            "required": [],
        },
    },
    {
        "name": "get_attack_surface",
        "description": (
            "Graph traversal: findings → CWE → ATT&CK techniques. "
            "Returns which MITRE ATT&CK techniques an attacker could use RIGHT NOW, ranked by exposure. "
            "Use for: 'what ATT&CK techniques are we exposed to?', 'map our vulns to MITRE'. "
            "NEVER guess ATT&CK mappings — always use this tool."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_new_findings",
        "description": (
            "Compares latest scan vs previous scan: net-new CVEs, resolved CVEs, trend label "
            "(IMPROVING/DEGRADING/STABLE). "
            "Use for: 'what changed since last scan?', 'what's new this week?', 'are we making progress?'. "
            "Optional: filter to one project with project_id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"project_id": {"type": "string", "description": "Optional project scope"}},
            "required": [],
        },
    },
    {
        "name": "get_ecosystem_breakdown",
        "description": (
            "Groups findings by ecosystem (npm, pom, yocto, iac) and scanner. "
            "Shows total, severity breakdown, KEV count, and patchable_pct. "
            "Use for: 'which scanner finds the most?', 'compare Java vs npm', 'how many are patchable?'"
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_iam_blast_radius",
        "description": (
            "CROSS-CORRELATION: For a CVE, look up which IAM role the affected workload inherits "
            "(from the PMapper privilege escalation graph), then return: "
            "(1) the IAM role name + trust type, "
            "(2) all data assets directly accessible (S3 buckets, DynamoDB tables, data classification, record count), "
            "(3) the full privilege escalation chain to admin with hop count, required API calls, and whether an automated exploit exists. "
            "Use this whenever a CVE is mentioned in a cloud workload context to show the real-world IAM blast radius. "
            "ALWAYS call this alongside get_regulatory_blast_radius for KEV findings in cloud environments."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cve_id": {"type": "string", "description": "e.g. CVE-2021-44228"}
            },
            "required": ["cve_id"],
        },
    },
    {
        "name": "get_fair_analysis",
        "description": (
            "FAIR risk quantification for a specific CVE: annualised loss expectancy (ALE), "
            "Value-at-Risk (VaR95/VaR99), threat event frequency, loss magnitude range, "
            "and which FAIR scenario applies (asset, threat actor, attack method). "
            "Use for: 'what is the financial risk of Log4Shell?', 'ALE for CVE-X', "
            "'show me the FAIR breakdown', 'quantify the risk in dollars'. "
            "Always call alongside get_regulatory_blast_radius for a complete risk picture."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cve_id": {"type": "string", "description": "e.g. CVE-2021-44228"}
            },
            "required": ["cve_id"],
        },
    },
    {
        "name": "get_control_effectiveness",
        "description": (
            "FAIR-CAM control effectiveness scores for a project: resistance, detection, and avoidance "
            "capability scores (0.0–1.0 scale). Shows which control gaps are driving susceptibility. "
            "Use for: 'how effective are our controls?', 'control maturity for project X', "
            "'why is our resistance score so low?', 'FAIR-CAM scores'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project key e.g. proj_08b7668d7af14fc2e9e847ff"}
            },
            "required": [],
        },
    },
    {
        "name": "get_penalty_exposure",
        "description": (
            "Regulatory secondary loss exposure: HIPAA OCR penalty range, EU CRA Article 13/14 "
            "fine tiers, FDA 524B refuse-to-accept and consent decree costs. "
            "Includes probability-weighted expected penalty and MedCore-specific exposure values. "
            "Use for: 'what fines are we exposed to?', 'HIPAA penalty', 'CRA fine', 'FDA enforcement'."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_remediation_roi",
        "description": (
            "Cost-benefit of patching a CVE: compares ALE before vs after patching, "
            "estimates remediation cost, and returns risk reduction value and ROI ratio. "
            "Shows which remediation option (patch, WAF rule, egress block, compensating control) "
            "delivers the best risk-adjusted return. "
            "Use for: 'what is the ROI of patching CVE-X?', 'is it worth fixing?', "
            "'prioritise by remediation value'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cve_id": {"type": "string", "description": "e.g. CVE-2021-44228"}
            },
            "required": ["cve_id"],
        },
    },
    {
        "name": "get_risk_heatmap_data",
        "description": (
            "Returns structured exploit-chain data for rendering a risk heatmap. "
            "Each step in the attack chain includes: cumulative likelihood percentage, "
            "financial impact in USD, FAIR-CAM resistance score, and control gap evidence. "
            "Also returns ALE, VaR 95/99, revenue context, frameworks violated, and the top "
            "intervention (action + risk removed + effort). "
            "ALWAYS call this tool before calling emit_artifact to render a risk heatmap, "
            "exploit chain diagram, or risk matrix. Without this call the heatmap will have "
            "no real financial data — emit_artifact will produce zeros or hallucinated values. "
            "Use when the user asks for: risk heatmap, exploit chain diagram, attack path "
            "visualisation, risk matrix, or any visual showing likelihood vs financial impact."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cve_id": {
                    "type": "string",
                    "description": "CVE identifier e.g. CVE-2021-44228",
                }
            },
            "required": ["cve_id"],
        },
    },
    {
        "name": "emit_artifact",
        "description": (
            "Render a visual artifact (dashboard, FAIR report, heatmap, slides) in the UI. "
            "Call AFTER fetching data with AQL tools. Pass structured data — the backend renders HTML. "
            "ONLY call when user explicitly asks to build/generate/create/visualize something."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "subtype": {
                    "type": "string",
                    "enum": ["dashboard", "fair_report", "heatmap", "slides"],
                    "description": "dashboard=metrics+charts, fair_report=FAIR risk model, heatmap=risk matrix, slides=board deck",
                },
                "title": {
                    "type": "string",
                    "description": "Short tab label e.g. 'Log4Shell FAIR Report'",
                },
                "data": {
                    "type": "object",
                    "description": (
                        "Structured data to render. Include all values retrieved from tools. "
                        "For fair_report: {cve_id, cvss, epss, in_kev, tef_pct, tc_pct, "
                        "lm_low_usd, lm_high_usd, ale_usd, risk_tier, cwe_ids, controls_count, "
                        "findings: [{file, severity, tool}], projects: [{name, critical, high}], "
                        "kev_list: [{cve_id, epss, ransomware_use}], frameworks: [str], summary: str}. "
                        "For dashboard: {total, critical, high, medium, low, kev_count, epss_high, "
                        "projects: [{name, risk_score, critical, high}], "
                        "top_cves: [{cve_id, severity, epss}], scan_trend: [{date, critical, high}]}. "
                        "For heatmap: pass the COMPLETE dict returned by get_risk_heatmap_data — "
                        "keys include chain_steps, ale_total_usd, var_95_usd, var_99_usd, "
                        "revenue_context_usd, ale_as_pct_revenue, frameworks_violated, "
                        "top_intervention, iam_intervention. Do NOT reshape or summarise it. "
                        "Spread/pass through the full object as data. "
                        "For slides: {title, org, date, slides: [{heading, bullets: [str], metric?: str}]}."
                    ),
                },
            },
            "required": ["subtype", "title", "data"],
        },
    },
]

# ---------------------------------------------------------------------------
# AQL tool implementations — real queries against Complira's v2.2 schema
# ---------------------------------------------------------------------------

def _tool_vulnerability_summary(db: Any, tenant_id: str, _: dict) -> dict:
    rows = list(db.aql.execute(
        """
        LET sev = (
            FOR f IN scan_findings FILTER f.tenant_id == @tid
            COLLECT s = f.severity WITH COUNT INTO n
            RETURN {severity: s, count: n}
        )
        LET kev = LENGTH(
            FOR f IN scan_findings FILTER f.tenant_id == @tid AND f.in_kev == true RETURN 1
        )
        LET high_epss = LENGTH(
            FOR f IN scan_findings FILTER f.tenant_id == @tid AND f.epss_score >= 0.5 RETURN 1
        )
        LET total = LENGTH(FOR f IN scan_findings FILTER f.tenant_id == @tid RETURN 1)
        LET runs  = LENGTH(FOR r IN scan_runs FILTER r.tenant_id == @tid RETURN 1)
        RETURN {total_findings: total, severity_breakdown: sev,
                kev_count: kev, high_epss_count: high_epss, total_scan_runs: runs}
        """,
        bind_vars={"tid": tenant_id},
    ))
    return rows[0] if rows else {}


def _tool_critical_findings(db: Any, tenant_id: str, inp: dict) -> list:
    return list(db.aql.execute(
        """
        FOR f IN scan_findings
            FILTER f.tenant_id == @tid AND f.severity IN ["critical","high"]
            SORT f.blast_radius_score DESC, f.epss_score DESC
            LIMIT @lim
            RETURN {
                finding_id: f._key, rule_id: f.rule_id, severity: f.severity,
                tool: f.tool, file_path: f.file_path,
                cvss_base: f.cvss_base, epss_score: f.epss_score,
                blast_radius_score: f.blast_radius_score, in_kev: f.in_kev,
                llm_risk_summary: f.llm_risk_summary,
                llm_remediation: f.llm_remediation, triage_status: f.triage_status
            }
        """,
        bind_vars={"tid": tenant_id, "lim": int(inp.get("limit", 10))},
    ))


def _tool_kev_exposure(db: Any, tenant_id: str, _: dict) -> list:
    # Query KEV-flagged findings directly from scan_findings, then enrich with KEV catalog
    return list(db.aql.execute(
        """
        FOR f IN scan_findings
            FILTER f.tenant_id == @tid AND f.in_kev == true AND f.cve_id != null
            LET k = FIRST(FOR kev IN kev_entries FILTER kev.cveID == f.cve_id RETURN kev)
            LET v = FIRST(FOR vuln IN vulnerabilities FILTER vuln.cve_id == f.cve_id RETURN vuln)
            COLLECT cve = f.cve_id INTO grp KEEP f, k, v
            RETURN DISTINCT {
                cve_id: cve,
                severity: grp[0].f.severity,
                epss_score: grp[0].f.epss_score,
                file_path: grp[0].f.file_path,
                cvss_v3: grp[0].v.cvss_v3_score,
                kev_date_added: grp[0].k.dateAdded,
                required_action: grp[0].k.requiredAction,
                ransomware_use: grp[0].k.knownRansomwareCampaignUse,
                vulnerability_name: grp[0].k.vulnerabilityName
            }
        """,
        bind_vars={"tid": tenant_id},
    ))


def _tool_top_affected_components(db: Any, tenant_id: str, inp: dict) -> list:
    # Derive affected "components" from scan findings grouped by file path / tool
    return list(db.aql.execute(
        """
        FOR f IN scan_findings
            FILTER f.tenant_id == @tid AND f.cve_id != null
            COLLECT component = f.file_path INTO grp
            LET crit = LENGTH(FOR g IN grp FILTER g.f.severity == "critical" RETURN 1)
            LET high = LENGTH(FOR g IN grp FILTER g.f.severity == "high" RETURN 1)
            FILTER crit + high > 0
            SORT crit DESC, high DESC
            LIMIT @lim
            RETURN {component: component, total_cves: LENGTH(grp), critical: crit, high: high,
                    cves: UNIQUE(grp[*].f.cve_id)}
        """,
        bind_vars={"tid": tenant_id, "lim": int(inp.get("limit", 10))},
    ))


def _tool_compliance_posture(db: Any, tenant_id: str, _: dict) -> dict:
    rows = list(db.aql.execute(
        """
        LET detected = LENGTH(
            FOR d IN detected_controls FILTER d.tenant_id == @tid RETURN 1
        )
        LET vio_by_fw = (
            FOR e IN finding_violates_control FILTER e.tenant_id == @tid
            COLLECT fw = e.framework INTO grp
            RETURN {framework: fw,
                    violated_controls: LENGTH(UNIQUE(grp[*].e.control_id)),
                    violation_count: LENGTH(grp)}
        )
        RETURN {detected_controls_count: detected, violations_by_framework: vio_by_fw,
                total_violations: SUM(vio_by_fw[*].violation_count)}
        """,
        bind_vars={"tid": tenant_id},
    ))
    return rows[0] if rows else {}


def _tool_regulatory_blast_radius(db: Any, tenant_id: str, inp: dict) -> dict:
    from complira_graph.utils.keys import normalize_cve_id
    cve_id = inp.get("cve_id", "")
    if not cve_id:
        return {"error": "cve_id required"}
    cve_key = normalize_cve_id(cve_id)
    rows = list(db.aql.execute(
        """
        LET cve_doc = DOCUMENT(CONCAT("vulnerabilities/", @cve_key))

        // Path 1: direct CVE → OSCAL control via maps_to_requirement
        LET direct_controls = (
            FOR ctrl IN 1..1 OUTBOUND cve_doc maps_to_requirement
                RETURN DISTINCT {
                    path: "direct",
                    control_id: ctrl._key,
                    control_family: ctrl.family,
                    control_title: ctrl.title
                }
        )

        // Path 2: CVE → CWE → ATT&CK technique (via technique_exploits_weakness) → control
        LET technique_controls = (
            FOR w IN 1..1 OUTBOUND cve_doc has_weakness
                FOR tech IN 1..1 INBOUND w technique_exploits_weakness
                    FOR ctrl IN 1..1 OUTBOUND tech technique_mitigated_by_control
                        RETURN DISTINCT {
                            path: "technique",
                            cwe_id: w.cwe_id,
                            attack_technique: tech.technique_id,
                            control_id: ctrl._key,
                            control_family: ctrl.family,
                            control_title: ctrl.title
                        }
        )

        // CWE list for context
        LET cwes = (FOR w IN 1..1 OUTBOUND cve_doc has_weakness RETURN w.cwe_id)

        // Tenant findings that match this CVE
        LET tenant_findings = (
            FOR f IN scan_findings
                FILTER f.tenant_id == @tid AND f.cve_id == @cve_id
                RETURN {file: f.file_path, severity: f.severity, epss: f.epss_score, in_kev: f.in_kev}
        )

        LET all_controls = UNION_DISTINCT(direct_controls, technique_controls)

        RETURN {
            cve_id: @cve_id,
            found_in_graph: cve_doc != null,
            cvss_v3: cve_doc.cvss_v3_score,
            cwe_ids: cwes,
            affected_controls_count: LENGTH(all_controls),
            controls: all_controls,
            tenant_findings: tenant_findings
        }
        """,
        bind_vars={"cve_key": cve_key, "cve_id": cve_id, "tid": tenant_id},
    ))
    return rows[0] if rows else {"cve_id": cve_id, "found_in_graph": False, "controls": [], "tenant_findings": []}


def _tool_scan_trend(db: Any, tenant_id: str, inp: dict) -> list:
    return list(db.aql.execute(
        """
        FOR r IN scan_runs FILTER r.tenant_id == @tid
            SORT r.started_at DESC LIMIT @lim
            RETURN {scan_run_id: r._key, started_at: r.started_at,
                    completed_at: r.completed_at, tools: r.tools_invoked,
                    finding_counts: r.finding_counts, project_id: r.project_id}
        """,
        bind_vars={"tid": tenant_id, "lim": int(inp.get("limit", 10))},
    ))


def _tool_project_risk_breakdown(db: Any, tenant_id: str, _: dict) -> list:
    return list(db.aql.execute(
        """
        FOR p IN projects FILTER p.tenant_id == @tid OR p.customer_id == @tid
            LET sev = (
                FOR r IN scan_runs FILTER r.tenant_id == @tid AND r.project_id == p._key
                    FOR f IN scan_findings FILTER f.scan_run_id == r._key AND f.tenant_id == @tid
                        COLLECT s = f.severity WITH COUNT INTO n
                        RETURN {severity: s, count: n}
            )
            FILTER LENGTH(sev) > 0
            LET crit_val = FIRST(FOR x IN sev FILTER x.severity == "critical" RETURN x.count)
            LET crit = IS_NULL(crit_val) ? 0 : crit_val
            LET high_val = FIRST(FOR x IN sev FILTER x.severity == "high" RETURN x.count)
            LET high = IS_NULL(high_val) ? 0 : high_val
            SORT crit DESC, high DESC
            RETURN {project_id: p._key, project_name: p.name,
                    findings_by_severity: sev, critical: crit, high: high,
                    risk_score: (crit * 10) + (high * 5)}
        """,
        bind_vars={"tid": tenant_id},
    ))


def _tool_nist_control_coverage(db: Any, tenant_id: str, _: dict) -> list:
    return list(db.aql.execute(
        """
        LET detected_by_family = (
            FOR d IN detected_controls FILTER d.tenant_id == @tid
                FOR e IN detected_control_maps_to FILTER e._from == d._id
                    FOR ctrl IN oscal_controls FILTER ctrl._id == e._to
                        COLLECT fam = ctrl.family WITH COUNT INTO n
                        RETURN {family: fam, detected: n}
        )
        LET violated_by_family = (
            FOR e IN finding_violates_control FILTER e.tenant_id == @tid
                FOR ctrl IN oscal_controls FILTER ctrl.control_id == e.control_id
                    COLLECT fam = ctrl.family WITH COUNT INTO n
                    RETURN {family: fam, violated: n}
        )
        LET families = UNION_DISTINCT(
            detected_by_family[*].family, violated_by_family[*].family
        )
        FOR fam IN families
            LET det = FIRST(FOR d IN detected_by_family FILTER d.family == fam RETURN d.detected) ?? 0
            LET vio = FIRST(FOR v IN violated_by_family FILTER v.family == fam RETURN v.violated) ?? 0
            SORT vio DESC
            RETURN {control_family: fam, controls_detected: det, controls_violated: vio}
        """,
        bind_vars={"tid": tenant_id},
    ))


def _tool_epss_rising_findings(db: Any, tenant_id: str, _: dict) -> list:
    return list(db.aql.execute(
        """
        FOR f IN scan_findings FILTER f.tenant_id == @tid AND f.epss_trend == "rising"
            SORT f.epss_score DESC LIMIT 15
            RETURN {finding_id: f._key, rule_id: f.rule_id, severity: f.severity,
                    epss_score: f.epss_score, epss_velocity: f.epss_velocity,
                    in_kev: f.in_kev, file_path: f.file_path, tool: f.tool}
        """,
        bind_vars={"tid": tenant_id},
    ))


def _tool_iam_blast_radius(db: Any, tenant_id: str, inp: dict) -> dict:
    """
    Query the PMapper IAM graph stored in iam_graphs for this tenant.
    Filter privilege escalation paths associated with the given CVE and
    return: entry role, data access targets, escalation chain to admin.
    """
    cve_id = inp.get("cve_id", "").strip()
    if not cve_id:
        return {"error": "cve_id required"}

    rows = list(db.aql.execute(
        "FOR g IN iam_graphs FILTER g.tenant_id == @tid LIMIT 1 RETURN g",
        bind_vars={"tid": tenant_id},
    ))
    if not rows:
        return {"error": "No IAM graph data found for this tenant", "cve_id": cve_id}

    graph = rows[0]
    nodes_by_arn = {n["arn"]: n for n in graph.get("nodes", [])}

    # Find the internet-reachable entry role associated with this CVE
    entry_role = None
    for node in graph.get("nodes", []):
        note = node.get("note", "")
        if node.get("reachable_from_internet") and cve_id in note:
            entry_role = node
            break

    # Fallback: any internet-reachable non-admin role
    if not entry_role:
        for node in graph.get("nodes", []):
            if node.get("reachable_from_internet") and not node.get("is_admin"):
                entry_role = node
                break

    if not entry_role:
        return {
            "cve_id": cve_id,
            "finding": "No internet-reachable IAM role found in graph",
            "nodes": len(graph.get("nodes", [])),
        }

    entry_arn = entry_role["arn"]

    # Data assets directly accessible from entry role
    data_access = [
        {
            "target": e["target"].split(":::")[-1] if ":::" in e["target"] else e["target"].split(":")[-1],
            "target_full": e["target"],
            "permissions": e.get("permissions", []),
            "data_classification": e.get("data_classification"),
            "record_count": e.get("record_count"),
            "regulatory_flags": e.get("regulatory_flags", []),
            "note": e.get("note"),
        }
        for e in graph.get("data_access_edges", [])
        if e.get("source") == entry_arn
    ]

    # Privilege escalation paths from entry role
    privesc_paths = [
        {
            "target": nodes_by_arn.get(e["target"], {}).get("friendly_name", e["target"].split("/")[-1]),
            "target_is_admin": nodes_by_arn.get(e["target"], {}).get("is_admin", False),
            "reason": e.get("reason"),
            "escalation_type": e.get("escalation_type"),
            "hop_count": e.get("hop_count", 1),
            "full_path": e.get("full_path"),
            "api_calls_required": e.get("api_calls_required", []),
            "severity": e.get("severity"),
            "automated_exploit_available": e.get("automated_exploit_available", False),
            "attack_narrative": e.get("attack_narrative"),
            "combined_with_cve": e.get("combined_with_cve"),
        }
        for e in graph.get("edges", [])
        if e.get("source") == entry_arn
    ]

    # Sort: CVE-correlated paths first, then by hop count
    privesc_paths.sort(key=lambda p: (
        0 if p.get("combined_with_cve") == cve_id else 1,
        p.get("hop_count", 99),
    ))

    # Summary stats
    admin_paths = [p for p in privesc_paths if p.get("target_is_admin")]
    min_hops = min((p["hop_count"] for p in admin_paths), default=None)
    total_api_calls = len({
        call
        for p in privesc_paths
        if p.get("combined_with_cve") == cve_id
        for call in p.get("api_calls_required", [])
    }) or None

    return {
        "cve_id": cve_id,
        "entry_role": {
            "name": entry_role.get("friendly_name"),
            "arn": entry_arn,
            "trust_type": entry_role.get("trust_policy_type"),
            "is_admin": entry_role.get("is_admin", False),
            "tags": entry_role.get("tags", {}),
        },
        "data_access": data_access,
        "privesc_paths": privesc_paths,
        "summary": {
            "direct_data_assets": len(data_access),
            "phi_assets": sum(1 for d in data_access if d.get("data_classification") == "PHI"),
            "escalation_paths_to_admin": len(admin_paths),
            "min_hops_to_admin": min_hops,
            "api_calls_to_compromise": total_api_calls,
            "automated_exploit_exists": any(p.get("automated_exploit_available") for p in admin_paths),
            "blast_radius": "FULL_ACCOUNT_COMPROMISE" if admin_paths else "PARTIAL",
        },
    }


def _tool_search_findings(db: Any, tenant_id: str, inp: dict) -> list:
    filters = ["f.tenant_id == @tid"]
    bind: dict = {"tid": tenant_id, "lim": int(inp.get("limit", 20))}

    if inp.get("severities"):
        filters.append("UPPER(f.severity) IN @severities")
        bind["severities"] = [s.upper() for s in inp["severities"]]
    if inp.get("project_id"):
        filters.append("f.project_id == @project_id")
        bind["project_id"] = inp["project_id"]
    if inp.get("scanner"):
        filters.append("f.tool == @scanner")
        bind["scanner"] = inp["scanner"]
    if inp.get("ecosystem"):
        filters.append("f.ecosystem == @ecosystem")
        bind["ecosystem"] = inp["ecosystem"]
    if inp.get("kev_only"):
        filters.append("f.in_kev == true")
    if inp.get("epss_min") is not None:
        filters.append("f.epss_score >= @epss_min")
        bind["epss_min"] = float(inp["epss_min"])
    if inp.get("has_fix") is True:
        filters.append("f.fixed_version != null")
    elif inp.get("has_fix") is False:
        filters.append("f.fixed_version == null")
    if inp.get("older_than_days") is not None:
        filters.append(
            "DATE_DIFF(DATE_NOW(), DATE_TIMESTAMP(f.scan_timestamp), 'd') >= @days"
        )
        bind["days"] = int(inp["older_than_days"])

    where = " AND ".join(filters)
    return list(db.aql.execute(
        f"""
        FOR f IN scan_findings FILTER {where}
            SORT f.epss_score DESC, f.cvss_score DESC
            LIMIT @lim
            RETURN {{finding_id: f._key, cve_id: f.cve_id, severity: f.severity,
                     cvss_score: f.cvss_score, epss_score: f.epss_score,
                     in_kev: f.in_kev, project_id: f.project_id, tool: f.tool,
                     component: f.component_name, version: f.component_version,
                     fixed_version: f.fixed_version, ecosystem: f.ecosystem,
                     file_path: f.file_path, scan_timestamp: f.scan_timestamp}}
        """,
        bind_vars=bind,
    ))


def _tool_get_cve_detail(db: Any, tenant_id: str, inp: dict) -> dict:
    cve_id = inp.get("cve_id", "")
    if not cve_id:
        return {"error": "cve_id required"}
    rows = list(db.aql.execute(
        """
        LET findings = (
            FOR f IN scan_findings FILTER f.tenant_id == @tid AND f.cve_id == @cve
                LET proj = FIRST(FOR p IN projects FILTER p._key == f.project_id
                               OR p.project_id == f.project_id RETURN p.name)
                RETURN {project: proj, severity: f.severity, cvss_score: f.cvss_score,
                        epss_score: f.epss_score, in_kev: f.in_kev, tool: f.tool,
                        component: f.component_name, version: f.component_version,
                        fixed_version: f.fixed_version, file_path: f.file_path}
        )
        LET vul = FIRST(FOR v IN vulnerabilities FILTER v._key == SUBSTITUTE(@cve, "-", "_")
                        RETURN {desc: v.description, cvss: v.cvss_v3_score, epss: v.epss_score})
        RETURN {
            cve_id: @cve,
            description: vul.desc,
            max_cvss: MAX(findings[*].cvss_score) ?? vul.cvss,
            max_epss: MAX(findings[*].epss_score),
            kev: LENGTH(findings[* FILTER CURRENT.in_kev == true]) > 0,
            total_findings: LENGTH(findings),
            projects_affected: UNIQUE(findings[*].project),
            fix_available: LENGTH(findings[* FILTER CURRENT.fixed_version != null]) > 0,
            fixed_version: FIRST(findings[* FILTER CURRENT.fixed_version != null][*].fixed_version),
            findings_detail: findings
        }
        """,
        bind_vars={"tid": tenant_id, "cve": cve_id},
    ))
    return rows[0] if rows else {"cve_id": cve_id, "error": "CVE not found"}


def _tool_search_components(db: Any, tenant_id: str, inp: dict) -> list:
    name = inp.get("name", "")
    if not name:
        return []
    return list(db.aql.execute(
        """
        FOR f IN scan_findings FILTER f.tenant_id == @tid
            FILTER CONTAINS(LOWER(f.component_name ?? ""), LOWER(@name))
            COLLECT component = f.component_name, version = f.component_version,
                    ecosystem = f.ecosystem
            AGGREGATE project_ids = UNIQUE(f.project_id),
                      total_cves   = COUNT_DISTINCT(f.cve_id),
                      crit_count   = SUM(UPPER(f.severity) == "CRITICAL" ? 1 : 0),
                      high_count   = SUM(UPPER(f.severity) == "HIGH" ? 1 : 0),
                      kev_count    = SUM(f.in_kev == true ? 1 : 0),
                      max_epss     = MAX(f.epss_score),
                      sample_cves  = UNIQUE(f.cve_id)[* LIMIT 5]
            SORT total_cves DESC
            RETURN {component_name: component, version, ecosystem,
                    project_count: LENGTH(project_ids), cross_repo: LENGTH(project_ids) > 1,
                    total_cves, critical: crit_count, high: high_count,
                    kev_count, max_epss, sample_cves}
        """,
        bind_vars={"tid": tenant_id, "name": name},
    ))


def _tool_get_cwe_breakdown(db: Any, tenant_id: str, inp: dict) -> list:
    return list(db.aql.execute(
        """
        FOR f IN scan_findings FILTER f.tenant_id == @tid
            FOR w IN 1..1 OUTBOUND DOCUMENT(CONCAT("vulnerabilities/", SUBSTITUTE(f.cve_id, "-", "_")))
                          has_weakness
                COLLECT cwe_id = w.cwe_id, cwe_name = w.name
                AGGREGATE finding_count = COUNT(1),
                          crit_count    = SUM(UPPER(f.severity) == "CRITICAL" ? 1 : 0),
                          high_count    = SUM(UPPER(f.severity) == "HIGH" ? 1 : 0),
                          kev_count     = SUM(f.in_kev == true ? 1 : 0),
                          cve_examples  = UNIQUE(f.cve_id)[* LIMIT 3]
                SORT finding_count DESC
                LIMIT @lim
                LET technique = FIRST(
                    FOR t IN 1..1 INBOUND w technique_exploits_weakness
                        RETURN {id: t.technique_id, name: t.name}
                )
                RETURN {cwe_id, cwe_name, finding_count, critical: crit_count,
                        high: high_count, kev_count, cve_examples,
                        primary_attack_technique: technique}
        """,
        bind_vars={"tid": tenant_id, "lim": int(inp.get("limit", 15))},
    ))


def _tool_get_attack_surface(db: Any, tenant_id: str, _: dict) -> dict:
    rows = list(db.aql.execute(
        """
        LET technique_exposure = (
            FOR f IN scan_findings FILTER f.tenant_id == @tid FILTER f.cve_id != null
                FOR w IN 1..1 OUTBOUND DOCUMENT(CONCAT("vulnerabilities/", SUBSTITUTE(f.cve_id,"-","_")))
                              has_weakness
                    FOR t IN 1..1 INBOUND w technique_exploits_weakness
                        COLLECT tid2 = t.technique_id, tname = t.name, tactic = t.tactic
                        AGGREGATE exposure_count = COUNT(1),
                                  crit_count     = SUM(UPPER(f.severity) == "CRITICAL" ? 1 : 0),
                                  kev_count      = SUM(f.in_kev == true ? 1 : 0),
                                  cve_ids        = UNIQUE(f.cve_id)[* LIMIT 4]
                        SORT exposure_count DESC
                        RETURN {technique_id: tid2, technique_name: tname, tactic,
                                exposure_count, critical: crit_count, kev_count, cve_ids}
        )
        LET tactic_summary = (
            FOR t IN technique_exposure
                COLLECT tac = t.tactic AGGREGATE cnt = COUNT(1)
                SORT cnt DESC
                RETURN {tactic: tac, technique_count: cnt}
        )
        RETURN {total_techniques: LENGTH(technique_exposure),
                tactics: tactic_summary, techniques: technique_exposure}
        """,
        bind_vars={"tid": tenant_id},
    ))
    return rows[0] if rows else {"total_techniques": 0, "tactics": [], "techniques": []}


def _tool_get_new_findings(db: Any, tenant_id: str, inp: dict) -> dict:
    project_filter = "AND run.project_id == @pid" if inp.get("project_id") else ""
    bind: dict = {"tid": tenant_id}
    if inp.get("project_id"):
        bind["pid"] = inp["project_id"]
    rows = list(db.aql.execute(
        f"""
        LET all_runs = (
            FOR run IN scan_runs FILTER run.tenant_id == @tid {project_filter}
                SORT run.started_at DESC RETURN run
        )
        LET latest  = FIRST(all_runs)
        LET prev    = all_runs[1]
        LET new_cves = (
            FOR f IN scan_findings FILTER f.tenant_id == @tid AND f.scan_run_id == latest._key
                RETURN DISTINCT f.cve_id
        )
        LET prev_cves = (
            FOR f IN scan_findings FILTER f.tenant_id == @tid
                FILTER prev != null AND f.scan_run_id == prev._key
                RETURN DISTINCT f.cve_id
        )
        LET net_new     = new_cves[* FILTER CURRENT NOT IN prev_cves]
        LET resolved    = prev_cves[* FILTER CURRENT NOT IN new_cves]
        LET new_detail  = (
            FOR f IN scan_findings FILTER f.tenant_id == @tid AND f.scan_run_id == latest._key
                FILTER f.cve_id IN net_new SORT f.epss_score DESC LIMIT 10
                RETURN {{cve_id: f.cve_id, severity: f.severity, epss_score: f.epss_score,
                         in_kev: f.in_kev, component: f.component_name, tool: f.tool}}
        )
        RETURN {{latest_scan: latest.started_at, previous_scan: prev.started_at,
                new_finding_count: LENGTH(net_new), resolved_count: LENGTH(resolved),
                net_change: LENGTH(net_new) - LENGTH(resolved),
                trend: LENGTH(net_new) < LENGTH(resolved) ? "IMPROVING" :
                       LENGTH(net_new) > LENGTH(resolved) ? "DEGRADING" : "STABLE",
                new_findings: new_detail, resolved_cve_ids: resolved}}
        """,
        bind_vars=bind,
    ))
    return rows[0] if rows else {"error": "No scan runs found"}


def _tool_get_ecosystem_breakdown(db: Any, tenant_id: str, _: dict) -> list:
    return list(db.aql.execute(
        """
        FOR f IN scan_findings FILTER f.tenant_id == @tid
            COLLECT ecosystem = f.ecosystem ?? "unknown", scanner = f.tool ?? "unknown"
            AGGREGATE total   = COUNT(1),
                      critical = SUM(UPPER(f.severity) == "CRITICAL" ? 1 : 0),
                      high     = SUM(UPPER(f.severity) == "HIGH" ? 1 : 0),
                      medium   = SUM(UPPER(f.severity) == "MEDIUM" ? 1 : 0),
                      low      = SUM(UPPER(f.severity) == "LOW" ? 1 : 0),
                      kev      = SUM(f.in_kev == true ? 1 : 0),
                      has_fix  = SUM(f.fixed_version != null ? 1 : 0)
            SORT total DESC
            RETURN {ecosystem, scanner, total, critical, high, medium, low,
                    kev_count: kev, fixable: has_fix,
                    patchable_pct: total > 0 ? ROUND(has_fix / total * 100) : 0}
        """,
        bind_vars={"tid": tenant_id},
    ))


def _tool_get_fair_analysis(db: Any, tenant_id: str, inp: dict) -> dict:
    cve_id = inp.get("cve_id", "").strip()
    if not cve_id:
        return {"error": "cve_id required"}

    rows = list(db.aql.execute(
        """
        FOR s IN fair_scenarios
            FILTER s.tenant_id == @tid AND @cve IN s.cve_ids
            LET threat = DOCUMENT(CONCAT("threat_profiles/", s.threat_profile_key))
            LET asset  = DOCUMENT(CONCAT("asset_valuations/", s.asset_key))
            RETURN {
                scenario_key:    s._key,
                scenario_name:   s.name,
                cve_ids:         s.cve_ids,
                asset_name:      asset.asset_name,
                asset_type:      asset.asset_type,
                criticality:     asset.criticality,
                threat_actor:    threat.threat_community,
                attack_method:   s.attack_method,
                primary_effect:  s.primary_effect,
                max_blast_radius: s.max_blast_radius,
                tef_most_likely: s.tef_most_likely,
                susceptibility:  s.susceptibility,
                resistance_strength: s.resistance_strength,
                control_gaps:    s.control_gaps,
                primary_loss_most_likely:   s.primary_loss_most_likely,
                secondary_loss_most_likely: s.secondary_loss_most_likely,
                ale_usd:         s.ale_usd,
                var_90_usd:      s.var_90_usd,
                var_95_usd:      s.var_95_usd,
                var_99_usd:      s.var_99_usd,
                median_loss_usd: s.median_loss_usd,
                min_loss_usd:    s.min_loss_usd,
                max_loss_usd:    s.max_loss_usd,
                iterations:      s.iterations,
                computed:        s.computed
            }
        """,
        bind_vars={"tid": tenant_id, "cve": cve_id},
    ))

    if not rows:
        return {"cve_id": cve_id, "error": "No FAIR scenario found for this CVE", "tip": "FAIR scenarios are pre-seeded for CVE-2021-44228, CVE-2021-45046, CVE-2022-0778"}

    return {
        "cve_id": cve_id,
        "scenarios": rows,
        "summary": {
            "total_ale_usd":    sum(r.get("ale_usd") or 0 for r in rows),
            "max_var_95_usd":   max((r.get("var_95_usd") or 0 for r in rows), default=0),
            "max_var_99_usd":   max((r.get("var_99_usd") or 0 for r in rows), default=0),
            "blast_radius":     rows[0].get("max_blast_radius"),
        },
    }


def _tool_get_control_effectiveness(db: Any, tenant_id: str, inp: dict) -> dict:
    bind: dict = {"tid": tenant_id}
    project_filter = ""
    if inp.get("project_id"):
        project_filter = "AND c.project_id == @pid"
        bind["pid"] = inp["project_id"]

    rows = list(db.aql.execute(
        f"""
        FOR c IN control_assessments
            FILTER c.tenant_id == @tid {project_filter}
            SORT c.composite_effectiveness ASC
            RETURN {{
                project_id:             c.project_id,
                fair_cam_function:      c.fair_cam_function,
                control_name:           c.control_name,
                framework_mapping:      c.framework_mapping,
                capability_score:       c.capability_score,
                coverage_score:         c.coverage_score,
                reliability_score:      c.reliability_score,
                composite_effectiveness: c.composite_effectiveness,
                evidence:               c.evidence,
                scanner_findings:       c.scanner_findings,
                notes:                  c.notes
            }}
        """,
        bind_vars=bind,
    ))

    if not rows:
        return {"error": "No control assessments found", "tip": "Run ingest_fair.py to seed FAIR-CAM data"}

    avg_score = sum(r.get("composite_effectiveness", 0) for r in rows) / len(rows)
    tier = "Critical" if avg_score < 0.2 else "High" if avg_score < 0.4 else "Medium" if avg_score < 0.6 else "Low"

    return {
        "control_assessments": rows,
        "summary": {
            "average_effectiveness": round(avg_score, 3),
            "risk_tier": tier,
            "weakest_control": rows[0].get("control_name") if rows else None,
            "weakest_score":   rows[0].get("composite_effectiveness") if rows else None,
            "total_assessed":  len(rows),
        },
    }


def _tool_get_penalty_exposure(db: Any, tenant_id: str, _: dict) -> dict:
    profile_rows = list(db.aql.execute(
        "FOR fp IN financial_profiles FILTER fp.tenant_id == @tid LIMIT 1 RETURN fp",
        bind_vars={"tid": tenant_id},
    ))

    penalty_rows = list(db.aql.execute(
        """
        FOR p IN penalty_structures
            SORT p.framework, p.tier
            RETURN {
                framework:       p.framework,
                tier:            p.tier,
                obligation:      p.obligation,
                currency:        p.currency,
                fixed_max:       p.fixed_max,
                revenue_pct_max: p.revenue_pct_max,
                penalty_per_violation_min: p.penalty_per_violation_min,
                penalty_per_violation_max: p.penalty_per_violation_max,
                annual_cap:      p.annual_cap,
                cost_min:        p.cost_min,
                cost_most_likely: p.cost_most_likely,
                cost_max:        p.cost_max,
                probability_of_action_given_breach: p.probability_of_action_given_breach,
                probability_of_action: p.probability_of_action,
                triggering_event: p.triggering_event,
                source:          p.source
            }
        """
    ))

    profile = profile_rows[0] if profile_rows else {}
    annual_revenue_eu = profile.get("annual_revenue_eu_usd", 0)
    phi_records = profile.get("phi_records_count", 0)

    # Compute MedCore-specific expected penalty for HIPAA
    hipaa = next((p for p in penalty_rows if p.get("framework") == "HIPAA"), {})
    hipaa_expected = round(
        (hipaa.get("penalty_per_violation_most_likely") or hipaa.get("annual_cap", 321_000))
        * (hipaa.get("probability_of_action_given_breach") or 0.12),
        0,
    )

    # EU CRA worst-case: higher of fixed_max or 2.5% of EU revenue
    cra = next((p for p in penalty_rows if p.get("framework") == "EU_CRA"), {})
    cra_fixed = cra.get("fixed_max", 15_000_000)
    cra_revenue = round(annual_revenue_eu * (cra.get("revenue_pct_max") or 0.025), 0)
    cra_max = max(cra_fixed, cra_revenue)

    return {
        "financial_profile": {
            "tenant_id": tenant_id,
            "annual_revenue_usd": profile.get("annual_revenue_usd"),
            "annual_revenue_eu_usd": annual_revenue_eu,
            "phi_records_count": phi_records,
            "hipaa_covered_entity": profile.get("hipaa_covered_entity"),
            "cyber_policy_limit_usd": profile.get("cyber_policy_limit_usd"),
        },
        "penalty_structures": penalty_rows,
        "medcore_exposure_summary": {
            "hipaa_expected_penalty_usd": hipaa_expected,
            "hipaa_max_penalty_usd": hipaa.get("annual_cap", 2_190_294),
            "hipaa_class_action_range": f"$625K–$11M (per IBM/HCA patterns)",
            "eu_cra_max_penalty_eur": cra_max,
            "eu_cra_market_access_risk": cra.get("market_access_denial_risk", True),
            "fda_rta_probability_open_kev": 0.35,
            "fda_rta_revenue_at_risk_per_day_usd": 500_000,
        },
    }


def _tool_get_remediation_roi(db: Any, tenant_id: str, inp: dict) -> dict:
    cve_id = inp.get("cve_id", "").strip()
    if not cve_id:
        return {"error": "cve_id required"}

    rows = list(db.aql.execute(
        """
        FOR s IN fair_scenarios
            FILTER s.tenant_id == @tid AND @cve IN s.cve_ids
            RETURN {
                scenario_key:    s._key,
                scenario_name:   s.name,
                ale_usd:         s.ale_usd,
                var_95_usd:      s.var_95_usd,
                resistance_strength: s.resistance_strength,
                susceptibility:  s.susceptibility,
                control_gaps:    s.control_gaps,
                tef_most_likely: s.tef_most_likely,
                primary_loss_most_likely:   s.primary_loss_most_likely,
                secondary_loss_most_likely: s.secondary_loss_most_likely
            }
        """,
        bind_vars={"tid": tenant_id, "cve": cve_id},
    ))

    if not rows:
        return {"cve_id": cve_id, "error": "No FAIR scenario found for this CVE"}

    scenario = rows[0]
    current_ale = scenario.get("ale_usd") or 0
    current_resist = scenario.get("resistance_strength") or 0.05
    tef = scenario.get("tef_most_likely") or 12.0
    p_loss = scenario.get("primary_loss_most_likely") or 1_000_000
    s_loss = scenario.get("secondary_loss_most_likely") or 500_000
    total_loss_per_event = p_loss + s_loss

    # Model 4 remediation options and their estimated ALE reduction
    options = [
        {
            "option": "Apply vendor patch",
            "new_resistance_strength": 0.85,
            "estimated_remediation_cost_usd": 15_000,
            "description": "Patch log4j-core / spring-webmvc; test in staging; deploy",
        },
        {
            "option": "WAF rule block (JNDI/LDAP egress)",
            "new_resistance_strength": 0.60,
            "estimated_remediation_cost_usd": 3_000,
            "description": "Block outbound JNDI callbacks at WAF/NACLs — compensating control",
        },
        {
            "option": "Disable JNDI lookup flag",
            "new_resistance_strength": 0.70,
            "estimated_remediation_cost_usd": 2_000,
            "description": "Set log4j2.formatMsgNoLookups=true or LOG4J_FORMAT_MSG_NO_LOOKUPS=true",
        },
        {
            "option": "Patch + WAF + egress block (combined)",
            "new_resistance_strength": 0.95,
            "estimated_remediation_cost_usd": 20_000,
            "description": "All three: patch, WAF rule, egress block — recommended",
        },
    ]

    results = []
    for opt in options:
        new_resist = opt["new_resistance_strength"]
        new_susceptibility = 1.0 - new_resist
        # Simplified ALE after remediation: scale by new LEF ratio
        new_lef = tef * new_susceptibility
        old_lef = tef * (1.0 - current_resist)
        ratio = new_lef / old_lef if old_lef > 0 else 0
        new_ale = round(current_ale * ratio, 0)
        risk_reduction = round(current_ale - new_ale, 0)
        cost = opt["estimated_remediation_cost_usd"]
        roi = round(risk_reduction / cost, 1) if cost > 0 else None

        results.append({
            "option":                      opt["option"],
            "description":                 opt["description"],
            "new_resistance_strength":     new_resist,
            "estimated_remediation_cost_usd": cost,
            "ale_before_usd":              round(current_ale, 0),
            "ale_after_usd":               new_ale,
            "risk_reduction_usd":          risk_reduction,
            "roi_ratio":                   roi,
            "roi_label":                   f"{roi}x return" if roi else "N/A",
        })

    # Sort by ROI descending
    results.sort(key=lambda r: r.get("roi_ratio") or 0, reverse=True)

    return {
        "cve_id":          cve_id,
        "scenario_name":   scenario.get("scenario_name"),
        "current_ale_usd": round(current_ale, 0),
        "current_var_95_usd": round(scenario.get("var_95_usd") or 0, 0),
        "remediation_options": results,
        "recommended":     results[0]["option"] if results else None,
    }


def _tool_get_risk_heatmap_data(db: Any, tenant_id: str, inp: dict) -> dict:
    """
    Returns structured exploit-chain data for risk heatmap visualisation.

    Each chain step has:
      likelihood_pct   — cumulative probability of reaching this step (0-100)
      financial_impact_usd — expected loss if attacker reaches this step
      resistance_score — FAIR-CAM composite effectiveness for controls at this step (0-1)
      severity_tier    — CRITICAL | HIGH | MEDIUM for colour coding

    Data sources: scan_findings (CVE/EPSS/KEV), fair_scenarios (ALE/VaR/loss magnitudes),
    iam_graphs (privilege escalation chain), control_assessments (FAIR-CAM scores).
    """
    cve_id = inp.get("cve_id", "").strip()
    if not cve_id:
        return {"error": "cve_id required"}

    # ── CVE base data ──────────────────────────────────────────────────────
    cve_rows = list(db.aql.execute(
        """
        FOR f IN scan_findings
            FILTER f.tenant_id == @tid AND f.cve_id == @cve
            SORT f.epss_score == null ? 0 : f.epss_score DESC
            LIMIT 1
            RETURN {
                cve_id:    f.cve_id,
                cvss:      f.cvss_v3_base_score,
                epss:      f.epss_score,
                kev:       f.kev,
                severity:  f.severity,
                component: f.component_name,
                version:   f.component_version
            }
        """,
        bind_vars={"tid": tenant_id, "cve": cve_id},
    ))
    cve_data = cve_rows[0] if cve_rows else {}

    # ── FAIR scenarios ─────────────────────────────────────────────────────
    scenario_rows = list(db.aql.execute(
        """
        FOR s IN fair_scenarios
            FILTER s.tenant_id == @tid AND @cve IN s.cve_ids
            LET threat = DOCUMENT(CONCAT("threat_profiles/", s.threat_profile_key))
            LET asset  = DOCUMENT(CONCAT("asset_valuations/", s.asset_key))
            RETURN {
                name:               s.name,
                primary_effect:     s.primary_effect,
                tef_most_likely:    s.tef_most_likely,
                susceptibility:     s.susceptibility,
                resistance:         s.resistance_strength,
                ale_usd:            s.ale_usd,
                var_95_usd:         s.var_95_usd,
                var_99_usd:         s.var_99_usd,
                primary_loss_ml:    s.primary_loss_most_likely,
                secondary_loss_ml:  s.secondary_loss_most_likely,
                control_gaps:       s.control_gaps,
                max_blast_radius:   s.max_blast_radius,
                revenue_context:    s.annual_revenue_context_usd,
                asset_name:         asset.asset_name,
                asset_type:         asset.asset_type,
                record_count:       asset.record_count,
                sensitivity:        asset.sensitivity,
                threat_community:   threat.threat_community
            }
        """,
        bind_vars={"tid": tenant_id, "cve": cve_id},
    ))

    # ── Control assessments (FAIR-CAM) ─────────────────────────────────────
    ctrl_rows = list(db.aql.execute(
        """
        FOR c IN control_assessments
            FILTER c.tenant_id == @tid
            RETURN {function: c.fair_cam_function, effectiveness: c.composite_effectiveness}
        """,
        bind_vars={"tid": tenant_id},
    ))

    # ── IAM graph ─────────────────────────────────────────────────────────
    iam_rows = list(db.aql.execute(
        "FOR g IN iam_graphs FILTER g.tenant_id == @tid LIMIT 1 RETURN g",
        bind_vars={"tid": tenant_id},
    ))
    iam_graph = iam_rows[0] if iam_rows else {}

    # ── Regulatory frameworks (from finding_violates_control edges) ────────
    fw_rows = list(db.aql.execute(
        """
        RETURN SORTED_UNIQUE(
            FOR e IN finding_violates_control
                FILTER e.tenant_id == @tid
                RETURN e.framework
        )
        """,
        bind_vars={"tid": tenant_id},
    ))
    frameworks = fw_rows[0] if fw_rows else []

    # ── Assemble values ────────────────────────────────────────────────────
    epss     = cve_data.get("epss") or 0.0
    cvss     = cve_data.get("cvss") or 0.0
    kev      = cve_data.get("kev", False)
    comp     = cve_data.get("component") or "unknown component"
    ver      = cve_data.get("version") or ""

    scenarios_sorted = sorted(scenario_rows, key=lambda s: s.get("ale_usd") or 0, reverse=True)
    worst       = scenarios_sorted[0] if scenarios_sorted else {}
    total_ale   = sum(s.get("ale_usd") or 0 for s in scenario_rows)
    var95       = max((s.get("var_95_usd") or 0 for s in scenario_rows), default=0)
    var99       = max((s.get("var_99_usd") or 0 for s in scenario_rows), default=0)
    revenue     = worst.get("revenue_context") or 85_000_000
    pl_ml       = worst.get("primary_loss_ml") or 5_000_000
    sl_ml       = worst.get("secondary_loss_ml") or 8_000_000
    susceptibility = worst.get("susceptibility") or (0.85 if kev else 0.5)

    ctrl_map = {c["function"]: c["effectiveness"] for c in ctrl_rows}
    resistance_exploit = ctrl_map.get("Resistance", 0.05)
    resistance_detect  = ctrl_map.get("Detection",  0.20)
    resistance_egress  = ctrl_map.get("Avoidance",  0.10)

    # IAM: find internet-reachable entry role associated with this CVE
    nodes_by_arn = {n["arn"]: n for n in iam_graph.get("nodes", [])}
    entry_role = None
    for node in iam_graph.get("nodes", []):
        if node.get("reachable_from_internet") and cve_id in node.get("note", ""):
            entry_role = node
            break
    if not entry_role:
        for node in iam_graph.get("nodes", []):
            if node.get("reachable_from_internet") and not node.get("is_admin"):
                entry_role = node
                break

    entry_arn = entry_role["arn"] if entry_role else None
    privesc_paths = [
        e for e in iam_graph.get("edges", [])
        if e.get("source") == entry_arn
    ] if entry_arn else []
    privesc_paths.sort(key=lambda p: (
        0 if p.get("combined_with_cve") == cve_id else 1,
        p.get("hop_count", 99),
    ))
    data_access_edges = [
        e for e in iam_graph.get("data_access_edges", [])
        if e.get("source") == entry_arn
    ] if entry_arn else []
    has_admin = any(
        nodes_by_arn.get(e["target"], {}).get("is_admin", False) for e in privesc_paths
    )

    phi_assets = [
        e for e in data_access_edges
        if e.get("data_classification") == "PHI" or (e.get("record_count") or 0) > 100_000
    ]
    total_phi_records = sum(e.get("record_count") or 0 for e in phi_assets)

    # ── Build chain steps ──────────────────────────────────────────────────
    p1 = min(epss * 100, 99.0) if epss else (97.0 if kev else 50.0)
    chain_steps = [
        {
            "step":                 1,
            "label":                f"Initial exploitation ({comp} {ver})".strip(),
            "attack_action":        f"RCE/injection via {cve_id}",
            "likelihood_pct":       round(p1, 1),
            "resistance_score":     round(resistance_exploit, 2),
            "financial_impact_usd": round(pl_ml * 0.3),
            "control_gap":          "Unpatched CVE — near-zero resistance",
            "severity_tier":        "CRITICAL" if cvss >= 9.0 or kev else "HIGH",
            "kev":                  kev,
        }
    ]

    # Step 2: credential / data access
    p2 = round(p1 * susceptibility, 1)
    chain_steps.append({
        "step":                 2,
        "label":                "Credential theft + data access" if data_access_edges else "Lateral movement",
        "attack_action":        "Query IMDS → inherit IAM credentials → enumerate S3/DynamoDB" if data_access_edges else "Move to adjacent service",
        "likelihood_pct":       p2,
        "resistance_score":     round(resistance_egress, 2),
        "financial_impact_usd": round(pl_ml * 0.7),
        "control_gap":          "No egress blocking; IMDS v1 accessible" if data_access_edges else "Insufficient network segmentation",
        "severity_tier":        "CRITICAL",
        "data_assets":          [
            f"{e.get('target', '?')} ({e.get('record_count', 0):,} records)"
            for e in data_access_edges[:3]
        ],
    })

    p3 = p2
    if phi_assets:
        p3 = round(p2 * (1 - resistance_detect), 1)
        chain_steps.append({
            "step":                 3,
            "label":                f"PHI exfiltration ({total_phi_records:,} records)",
            "attack_action":        "Bulk S3 GetObject; exfil before detection",
            "likelihood_pct":       p3,
            "resistance_score":     round(resistance_detect, 2),
            "financial_impact_usd": round(pl_ml + sl_ml * 0.4),
            "control_gap":          "S3 access logging insufficient — exfiltration undetected",
            "severity_tier":        "CRITICAL",
            "record_count":         total_phi_records,
        })

    # IAM escalation hops
    p_current = p3
    iam_financial_base = pl_ml + sl_ml * 0.6
    for i, hop in enumerate(privesc_paths[:3]):
        p_current = round(p_current * 0.98, 1)
        target_node = nodes_by_arn.get(hop.get("target", ""), {})
        target_name = target_node.get("friendly_name") or hop.get("target", "?").split("/")[-1]
        financial = iam_financial_base * (1.5 ** (i + 1))
        chain_steps.append({
            "step":                 len(chain_steps) + 1,
            "label":                f"IAM escalation hop {i + 1}: {target_name}",
            "attack_action":        hop.get("reason") or "Role assumption via over-permissioned policy",
            "likelihood_pct":       p_current,
            "resistance_score":     0.02,
            "financial_impact_usd": round(min(financial, revenue * 5)),
            "control_gap":          "iam:PassRole over-permissioned on service role",
            "severity_tier":        "CRITICAL",
            "blast_radius":         "FULL_ACCOUNT_COMPROMISE" if target_node.get("is_admin") else "ELEVATED_PRIVILEGES",
        })

    if has_admin:
        p_final = round(p_current * 0.95, 1)
        chain_steps.append({
            "step":                 len(chain_steps) + 1,
            "label":                "Full account compromise + ransomware",
            "attack_action":        "iam:CreatePolicyVersion → admin policy → mass encrypt S3 + delete snapshots",
            "likelihood_pct":       p_final,
            "resistance_score":     0.01,
            "financial_impact_usd": round(min(pl_ml + sl_ml, revenue * 3)),
            "control_gap":          "No MFA on break-glass admin; no SCPs blocking destructive actions",
            "severity_tier":        "CRITICAL",
            "blast_radius":         "FULL_ACCOUNT_COMPROMISE",
        })

    top_intervention = {
        "action":               f"Patch {comp} — eliminates entire chain at step 1",
        "risk_removed_usd":     round(total_ale),
        "effort":               "Low — library version bump",
        "breaks_chain_at_step": 1,
    }
    iam_intervention = None
    if len(chain_steps) >= 4:
        iam_intervention = {
            "action":               "Remove iam:PassRole from service role — severs escalation at hop 1",
            "risk_removed_usd":     round(total_ale * 0.70),
            "effort":               "Very low — IAM policy edit (30 min)",
            "breaks_chain_at_step": 4,
        }

    return {
        "cve_id":              cve_id,
        "component":           f"{comp} {ver}".strip(),
        "cvss":                cvss,
        "epss_pct":            round(epss * 100, 1) if epss else None,
        "kev":                 kev,
        "chain_steps":         chain_steps,
        "total_steps":         len(chain_steps),
        "ale_total_usd":       round(total_ale) if total_ale else None,
        "var_95_usd":          round(var95) if var95 else None,
        "var_99_usd":          round(var99) if var99 else None,
        "revenue_context_usd": revenue,
        "ale_as_pct_revenue":  round(total_ale / revenue * 100, 1) if total_ale and revenue else None,
        "frameworks_violated": frameworks,
        "top_intervention":    top_intervention,
        "iam_intervention":    iam_intervention,
        "heatmap_axes": {
            "x_axis":  "likelihood_pct (0-100%)",
            "y_axis":  "financial_impact_usd",
            "size":    "resistance_score (smaller = weaker controls = bigger bubble = bigger problem)",
            "colour":  "severity_tier (CRITICAL=red, HIGH=amber, MEDIUM=yellow)",
        },
    }


# ---------------------------------------------------------------------------
# Tool dispatch registry
# ---------------------------------------------------------------------------

_TOOL_REGISTRY: dict[str, Any] = {
    "get_vulnerability_summary":   _tool_vulnerability_summary,
    "get_critical_findings":       _tool_critical_findings,
    "get_kev_exposure":            _tool_kev_exposure,
    "get_top_affected_components": _tool_top_affected_components,
    "get_compliance_posture":      _tool_compliance_posture,
    "get_regulatory_blast_radius": _tool_regulatory_blast_radius,
    "get_scan_trend":              _tool_scan_trend,
    "get_project_risk_breakdown":  _tool_project_risk_breakdown,
    "get_nist_control_coverage":   _tool_nist_control_coverage,
    "get_epss_rising_findings":    _tool_epss_rising_findings,
    "get_iam_blast_radius":        _tool_iam_blast_radius,
    "search_findings":             _tool_search_findings,
    "get_cve_detail":              _tool_get_cve_detail,
    "search_components":           _tool_search_components,
    "get_cwe_breakdown":           _tool_get_cwe_breakdown,
    "get_attack_surface":          _tool_get_attack_surface,
    "get_new_findings":            _tool_get_new_findings,
    "get_ecosystem_breakdown":     _tool_get_ecosystem_breakdown,
    "get_fair_analysis":           _tool_get_fair_analysis,
    "get_control_effectiveness":   _tool_get_control_effectiveness,
    "get_penalty_exposure":        _tool_get_penalty_exposure,
    "get_remediation_roi":         _tool_get_remediation_roi,
    "get_risk_heatmap_data":       _tool_get_risk_heatmap_data,
}


def _execute_tool(name: str, tool_input: dict, tenant_id: str, db: Any) -> str:
    """Execute a registered tool; return JSON string for tool_result block."""
    fn = _TOOL_REGISTRY.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        return json.dumps(fn(db, tenant_id, tool_input), default=str)
    except Exception as exc:
        log.warning("chat.tool_error", extra={"tool": name, "error": str(exc)})
        return json.dumps({"error": str(exc), "tool": name})


def _summarize_tool_result(tool_name: str, result_json: str) -> str:
    """Return a concise human-readable summary of a tool result for the activity feed."""
    try:
        data = json.loads(result_json)
    except Exception:
        return result_json[:120]

    try:
        if tool_name == "get_vulnerability_summary":
            total = data.get("total_findings", 0)
            kev   = data.get("kev_count", 0)
            sev   = {s["severity"]: s["count"] for s in data.get("severity_breakdown", [])}
            crit  = sev.get("critical", 0)
            high  = sev.get("high", 0)
            kev_str = f" · {kev} KEV-flagged" if kev else ""
            return f"{total} total findings · {crit} critical, {high} high{kev_str}"

        if tool_name == "get_kev_exposure":
            items = data if isinstance(data, list) else []
            n = len(items)
            if n == 0:
                return "No CISA KEV-flagged CVEs in your scan data"
            names = [i.get("cve_id", "") for i in items[:2]]
            extra = f" +{n - 2} more" if n > 2 else ""
            return f"{n} KEV CVE{'s' if n != 1 else ''}: {', '.join(names)}{extra}"

        if tool_name == "get_critical_findings":
            items = data if isinstance(data, list) else []
            crit  = sum(1 for i in items if i.get("severity") == "critical")
            return f"{len(items)} critical/high findings · {crit} critical"

        if tool_name == "get_top_affected_components":
            items = data if isinstance(data, list) else []
            if not items:
                return "No affected components found"
            top = items[0]
            return (
                f"{len(items)} components · highest: "
                f"{(top.get('component') or '?').split('/')[-1]} "
                f"({top.get('total_cves', 0)} CVEs)"
            )

        if tool_name == "get_compliance_posture":
            total_vio = data.get("total_violations", 0)
            detected  = data.get("detected_controls_count", 0)
            by_fw     = data.get("violations_by_framework", [])
            if not by_fw:
                return f"{detected} controls detected · {total_vio} violations"
            top_fw = by_fw[0]
            return (
                f"{total_vio} violations · "
                f"{top_fw.get('framework', '?')}: {top_fw.get('violation_count', 0)}"
            )

        if tool_name == "get_regulatory_blast_radius":
            cve      = data.get("cve_id", "")
            n        = data.get("affected_controls_count", 0)
            controls = data.get("controls", [])
            if n == 0:
                return f"{cve}: no NIST control mappings found"
            families = list({c.get("control_family", "") for c in controls[:6] if c.get("control_family")})
            return f"{cve} → {n} NIST 800-53 controls · families: {', '.join(sorted(families)[:3])}"

        if tool_name == "get_scan_trend":
            items = data if isinstance(data, list) else []
            return f"{len(items)} scan run{'s' if len(items) != 1 else ''} in history"

        if tool_name == "get_project_risk_breakdown":
            items = data if isinstance(data, list) else []
            if not items:
                return "No projects with findings"
            top = items[0]
            return (
                f"{len(items)} project{'s' if len(items) != 1 else ''} · "
                f"highest risk: {top.get('project_name', '?')} "
                f"({top.get('critical', 0)} critical)"
            )

        if tool_name == "get_nist_control_coverage":
            items     = data if isinstance(data, list) else []
            total_vio = sum(i.get("controls_violated", 0) for i in items)
            return f"{len(items)} control families · {total_vio} total violations"

        if tool_name == "get_epss_rising_findings":
            items = data if isinstance(data, list) else []
            if not items:
                return "No rising EPSS trends detected"
            top = items[0]
            score = top.get("epss_score") or 0
            return (
                f"{len(items)} rising-risk findings · "
                f"top: {top.get('rule_id', '?')} (EPSS {score:.2f})"
            )

        if tool_name == "search_findings":
            items = data if isinstance(data, list) else []
            kev = sum(1 for i in items if i.get("in_kev"))
            kev_str = f" · {kev} KEV" if kev else ""
            return f"{len(items)} findings returned{kev_str}"

        if tool_name == "get_cve_detail":
            n = data.get("total_findings", 0)
            projects = len(data.get("projects_affected") or [])
            kev = "⚠️ KEV · " if data.get("kev") else ""
            fix = " · fix available" if data.get("fix_available") else ""
            return f"{kev}{data.get('cve_id', '?')} · {n} findings across {projects} project{'s' if projects != 1 else ''}{fix}"

        if tool_name == "search_components":
            items = data if isinstance(data, list) else []
            cross = sum(1 for i in items if i.get("cross_repo"))
            return f"{len(items)} component match{'es' if len(items) != 1 else ''} · {cross} cross-repo"

        if tool_name == "get_cwe_breakdown":
            items = data if isinstance(data, list) else []
            if not items:
                return "No CWE mappings found"
            top = items[0]
            return f"{len(items)} CWE categories · top: {top.get('cwe_id', '?')} ({top.get('finding_count', 0)} findings)"

        if tool_name == "get_attack_surface":
            n = data.get("total_techniques", 0)
            tactics = data.get("tactics") or []
            tactic_names = [t.get("tactic", "") for t in tactics[:3] if t.get("tactic")]
            return f"{n} ATT&CK technique{'s' if n != 1 else ''} · tactics: {', '.join(tactic_names)}" if tactic_names else f"{n} ATT&CK techniques exposed"

        if tool_name == "get_new_findings":
            trend = data.get("trend", "?")
            new_n = data.get("new_finding_count", 0)
            res_n = data.get("resolved_count", 0)
            return f"{trend} · +{new_n} new, -{res_n} resolved since last scan"

        if tool_name == "get_ecosystem_breakdown":
            items = data if isinstance(data, list) else []
            if not items:
                return "No ecosystem data"
            top = items[0]
            return f"{len(items)} ecosystem/scanner rows · most findings: {top.get('ecosystem', '?')} via {top.get('scanner', '?')} ({top.get('total', 0)})"

        if tool_name == "get_iam_blast_radius":
            if "error" in data:
                return f"IAM graph: {data['error']}"
            role  = (data.get("entry_role") or {}).get("name", "unknown role")
            summ  = data.get("summary", {})
            hops  = summ.get("min_hops_to_admin")
            calls = summ.get("api_calls_to_compromise")
            phi   = summ.get("phi_assets", 0)
            blast = summ.get("blast_radius", "")
            hops_str  = f" · {hops}-hop admin escalation" if hops is not None else ""
            calls_str = f" in {calls} API calls" if calls else ""
            phi_str   = f" · {phi} PHI asset{'s' if phi != 1 else ''}" if phi else ""
            return f"{role}{hops_str}{calls_str}{phi_str} → {blast}"

        if tool_name == "get_fair_analysis":
            if "error" in data:
                return f"FAIR: {data['error']}"
            summ = data.get("summary", {})
            ale  = summ.get("total_ale_usd", 0)
            v95  = summ.get("max_var_95_usd", 0)
            blast = summ.get("blast_radius", "")
            scenarios = len(data.get("scenarios", []))
            return f"{data.get('cve_id', '?')} · ALE ${ale/1e6:.1f}M · VaR95 ${v95/1e6:.1f}M · {scenarios} scenario{'s' if scenarios != 1 else ''} · {blast}"

        if tool_name == "get_control_effectiveness":
            if "error" in data:
                return f"FAIR-CAM: {data['error']}"
            summ = data.get("summary", {})
            avg  = summ.get("average_effectiveness", 0)
            tier = summ.get("risk_tier", "?")
            weak = summ.get("weakest_control", "?")
            score = summ.get("weakest_score", 0)
            return f"Avg effectiveness {avg:.2f} ({tier} risk) · weakest: {weak} ({score:.2f})"

        if tool_name == "get_penalty_exposure":
            summ = data.get("medcore_exposure_summary", {})
            hipaa_max = summ.get("hipaa_max_penalty_usd", 0)
            cra_max   = summ.get("eu_cra_max_penalty_eur", 0)
            fda_rta   = summ.get("fda_rta_probability_open_kev", 0)
            return f"HIPAA max ${hipaa_max/1e6:.1f}M · EU CRA max €{cra_max/1e6:.1f}M · FDA RTA {int(fda_rta*100)}% probability"

        if tool_name == "get_remediation_roi":
            if "error" in data:
                return f"ROI: {data['error']}"
            recommended = data.get("recommended", "?")
            options = data.get("remediation_options", [])
            best = options[0] if options else {}
            roi  = best.get("roi_ratio", 0)
            reduction = best.get("risk_reduction_usd", 0)
            return f"{data.get('cve_id', '?')} · best ROI: {recommended} ({roi}x · ${reduction/1e6:.1f}M risk reduction)"

    except Exception:
        pass

    if isinstance(data, list):
        return f"{len(data)} items returned"
    if isinstance(data, dict) and "error" in data:
        return f"Error: {data['error']}"
    return "Data retrieved"


# Maps each tool to the data sources it queries — shown in the activity feed
TOOL_SOURCES: dict[str, list[str]] = {
    "get_vulnerability_summary":   ["Scan Findings", "EPSS"],
    "get_kev_exposure":            ["CISA KEV", "Scan Findings"],
    "get_critical_findings":       ["Scan Findings", "EPSS", "CVSS"],
    "get_top_affected_components": ["Scan Findings"],
    "get_compliance_posture":      ["NIST 800-53", "Detected Controls"],
    "get_regulatory_blast_radius": ["NIST 800-53", "MITRE ATT&CK", "CWE"],
    "get_scan_trend":              ["Scan Runs"],
    "get_project_risk_breakdown":  ["Projects", "Scan Findings"],
    "get_nist_control_coverage":   ["NIST 800-53", "Detected Controls"],
    "get_epss_rising_findings":    ["EPSS", "Scan Findings"],
    "get_iam_blast_radius":        ["PMapper IAM Graph", "AWS IAM"],
    "search_findings":             ["Scan Findings"],
    "get_cve_detail":              ["Scan Findings", "EPSS", "CVSS"],
    "search_components":           ["Scan Findings", "SBOM"],
    "get_cwe_breakdown":           ["CWE", "MITRE ATT&CK", "Scan Findings"],
    "get_attack_surface":          ["MITRE ATT&CK", "CWE", "Scan Findings"],
    "get_new_findings":            ["Scan Runs", "Scan Findings"],
    "get_ecosystem_breakdown":     ["Scan Findings"],
    "get_fair_analysis":           ["FAIR Scenarios", "Monte Carlo", "EPSS"],
    "get_control_effectiveness":   ["FAIR-CAM", "Control Assessments"],
    "get_penalty_exposure":        ["HIPAA OCR", "EU CRA", "FDA 524B", "Financial Profiles"],
    "get_remediation_roi":         ["FAIR Scenarios", "Monte Carlo"],
    "emit_artifact":               ["Chart.js"],
}


# ---------------------------------------------------------------------------
# SSE helper
# ---------------------------------------------------------------------------

def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


# ---------------------------------------------------------------------------
# Server-side artifact HTML renderers
# ---------------------------------------------------------------------------

def _render_fair_report(data: dict, title: str) -> str:
    cve_id       = data.get("cve_id", "N/A")
    cvss         = data.get("cvss", "N/A")
    epss         = data.get("epss", 0)
    in_kev       = data.get("in_kev", False)
    tef          = data.get("tef_pct", 85)
    tc           = data.get("tc_pct", 70)
    lm_low       = data.get("lm_low_usd", 50_000)
    lm_high      = data.get("lm_high_usd", 2_500_000)
    ale          = data.get("ale_usd", 850_000)
    risk_tier    = data.get("risk_tier", "High")
    cwe_ids      = data.get("cwe_ids", [])
    ctrl_count   = data.get("controls_count", 0)
    findings     = data.get("findings", [])
    projects     = data.get("projects", [])
    kev_list     = data.get("kev_list", [])
    frameworks   = data.get("frameworks", ["NIST 800-53", "PCI DSS", "HIPAA", "SOC 2"])
    summary      = data.get("summary", "")

    tier_color = {"Critical": "#ef4444", "High": "#f59e0b", "Medium": "#3b82f6", "Low": "#10b981"}.get(risk_tier, "#f59e0b")

    findings_rows = "".join(
        f'<tr><td>{f.get("file","")}</td><td style="color:{"#ef4444" if f.get("severity")=="critical" else "#f59e0b"}">'
        f'{f.get("severity","").upper()}</td><td>{f.get("tool","")}</td></tr>'
        for f in findings[:10]
    )
    kev_rows = "".join(
        f'<tr><td style="color:#10b981">{k.get("cve_id","")}</td>'
        f'<td>{round(k.get("epss",0)*100,1)}%</td>'
        f'<td>{"⚠️ Yes" if k.get("ransomware_use") else "No"}</td></tr>'
        for k in kev_list[:8]
    )
    proj_js  = json.dumps([p.get("name","") for p in projects])
    proj_crit = json.dumps([p.get("critical", 0) for p in projects])
    proj_high = json.dumps([p.get("high", 0) for p in projects])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:#0f1117;color:#e4e4e7;font-family:system-ui,-apple-system,sans-serif;font-size:13px;padding:20px}}
  h1{{font-size:18px;font-weight:700;color:#fff;margin-bottom:4px}}
  .sub{{color:#71717a;font-size:12px;margin-bottom:20px}}
  .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:20px}}
  .card{{background:#18181b;border:1px solid #27272a;border-radius:12px;padding:14px}}
  .card-label{{font-size:11px;color:#71717a;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px}}
  .card-value{{font-size:22px;font-weight:700;color:#fff}}
  .card-sub{{font-size:11px;color:#52525b;margin-top:3px}}
  .tier{{display:inline-block;padding:3px 10px;border-radius:6px;font-size:12px;font-weight:600}}
  .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}}
  .grid2 .full{{grid-column:1/-1}}
  .box{{background:#18181b;border:1px solid #27272a;border-radius:12px;padding:16px}}
  .box h3{{font-size:13px;font-weight:600;color:#a1a1aa;margin-bottom:12px}}
  table{{width:100%;border-collapse:collapse}}
  th{{text-align:left;font-size:11px;color:#52525b;text-transform:uppercase;padding:0 8px 8px}}
  td{{padding:6px 8px;border-top:1px solid #27272a;color:#d4d4d8}}
  .bar-bg{{background:#27272a;border-radius:4px;height:8px;margin-top:4px}}
  .bar{{height:8px;border-radius:4px;background:#10b981}}
  .kev{{color:#fbbf24;font-weight:600}}
  .footer{{margin-top:20px;text-align:center;font-size:11px;color:#3f3f46}}
  canvas{{max-height:180px}}
</style>
</head>
<body>
<h1>⚡ {title}</h1>
<div class="sub">FAIR Risk Quantification · {cve_id} · Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC</div>

<div class="cards">
  <div class="card">
    <div class="card-label">Risk Tier</div>
    <div class="card-value"><span class="tier" style="background:{tier_color}22;color:{tier_color}">{risk_tier}</span></div>
    <div class="card-sub">FAIR composite</div>
  </div>
  <div class="card">
    <div class="card-label">CVSSv3</div>
    <div class="card-value" style="color:{'#ef4444' if float(cvss or 0)>=9 else '#f59e0b'}">{cvss}</div>
    <div class="card-sub">{'CRITICAL' if float(cvss or 0)>=9 else 'HIGH'}</div>
  </div>
  <div class="card">
    <div class="card-label">EPSS</div>
    <div class="card-value" style="color:#f59e0b">{round(float(epss or 0)*100,1)}%</div>
    <div class="card-sub">Exploit probability</div>
  </div>
  <div class="card">
    <div class="card-label">CISA KEV</div>
    <div class="card-value" style="color:{'#ef4444' if in_kev else '#10b981'}">{'YES ⚠️' if in_kev else 'No'}</div>
    <div class="card-sub">Actively exploited</div>
  </div>
  <div class="card">
    <div class="card-label">Ann. Loss Est.</div>
    <div class="card-value" style="color:#f59e0b">${ale//1000:,}K</div>
    <div class="card-sub">${lm_low//1000:,}K–${lm_high//1000:,}K range</div>
  </div>
  <div class="card">
    <div class="card-label">Controls Hit</div>
    <div class="card-value">{ctrl_count}</div>
    <div class="card-sub">NIST 800-53</div>
  </div>
</div>

<div class="grid2">
  <div class="box">
    <h3>FAIR Model — Threat Factors</h3>
    <div style="margin-bottom:10px">
      <div style="display:flex;justify-content:space-between"><span style="color:#a1a1aa">Threat Event Freq.</span><span style="color:#fff">{tef}%</span></div>
      <div class="bar-bg"><div class="bar" style="width:{tef}%;background:#ef4444"></div></div>
    </div>
    <div style="margin-bottom:10px">
      <div style="display:flex;justify-content:space-between"><span style="color:#a1a1aa">Threat Capability</span><span style="color:#fff">{tc}%</span></div>
      <div class="bar-bg"><div class="bar" style="width:{tc}%;background:#f59e0b"></div></div>
    </div>
    <div>
      <div style="display:flex;justify-content:space-between"><span style="color:#a1a1aa">Loss Magnitude</span><span style="color:#fff">${lm_low//1000:,}K – ${lm_high//1000:,}K</span></div>
      <div class="bar-bg"><div class="bar" style="width:80%;background:#10b981"></div></div>
    </div>
    <div style="margin-top:14px;padding-top:12px;border-top:1px solid #27272a;font-size:11px;color:#71717a">
      CWEs: {", ".join(cwe_ids[:4]) if cwe_ids else "N/A"} · Frameworks: {len(frameworks)}
    </div>
  </div>

  <div class="box">
    <h3>Project Risk Breakdown</h3>
    <canvas id="projChart"></canvas>
  </div>

  <div class="box">
    <h3>CISA KEV Exposure ({len(kev_list)} CVEs)</h3>
    {'<table><thead><tr><th>CVE</th><th>EPSS</th><th>Ransomware</th></tr></thead><tbody>' + kev_rows + '</tbody></table>' if kev_list else '<p style="color:#52525b">No KEV findings</p>'}
  </div>

  <div class="box">
    <h3>Active Findings ({len(findings)})</h3>
    {'<table><thead><tr><th>File</th><th>Severity</th><th>Tool</th></tr></thead><tbody>' + findings_rows + '</tbody></table>' if findings else '<p style="color:#52525b">No findings</p>'}
  </div>

  {'<div class="box full"><h3>Executive Summary</h3><p style="color:#a1a1aa;line-height:1.6">' + summary + '</p></div>' if summary else ''}
</div>

<div class="footer">Complira Security Intelligence · complira.dev</div>

<script>
new Chart(document.getElementById('projChart'), {{
  type: 'bar',
  data: {{
    labels: {proj_js},
    datasets: [
      {{label:'Critical',data:{proj_crit},backgroundColor:'#ef4444',borderRadius:4}},
      {{label:'High',data:{proj_high},backgroundColor:'#f59e0b',borderRadius:4}}
    ]
  }},
  options:{{
    responsive:true,maintainAspectRatio:true,
    plugins:{{legend:{{labels:{{color:'#a1a1aa',font:{{size:11}}}}}}}},
    scales:{{
      x:{{stacked:false,ticks:{{color:'#71717a',font:{{size:10}}}},grid:{{color:'#27272a'}}}},
      y:{{ticks:{{color:'#71717a',font:{{size:10}}}},grid:{{color:'#27272a'}}}}
    }}
  }}
}});
</script>
</body></html>"""


def _render_dashboard(data: dict, title: str) -> str:
    total    = data.get("total", 0)
    critical = data.get("critical", 0)
    high     = data.get("high", 0)
    medium   = data.get("medium", 0)
    low      = data.get("low", 0)
    kev      = data.get("kev_count", 0)
    epss_h   = data.get("epss_high", 0)
    projects = data.get("projects", [])
    top_cves = data.get("top_cves", [])
    trend    = data.get("scan_trend", [])

    proj_js    = json.dumps([p.get("name","") for p in projects])
    proj_score = json.dumps([p.get("risk_score", 0) for p in projects])
    trend_labels = json.dumps([t.get("date","") for t in trend])
    trend_crit   = json.dumps([t.get("critical",0) for t in trend])
    trend_high   = json.dumps([t.get("high",0) for t in trend])

    cve_rows = "".join(
        f'<tr><td style="color:#10b981;font-family:monospace">{c.get("cve_id","")}</td>'
        f'<td style="color:{"#ef4444" if c.get("severity")=="critical" else "#f59e0b"}">{c.get("severity","").upper()}</td>'
        f'<td>{round(c.get("epss",0)*100,1)}%</td></tr>'
        for c in top_cves[:8]
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:#0f1117;color:#e4e4e7;font-family:system-ui,-apple-system,sans-serif;font-size:13px;padding:20px}}
  h1{{font-size:18px;font-weight:700;color:#fff;margin-bottom:4px}}
  .sub{{color:#71717a;font-size:12px;margin-bottom:20px}}
  .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:12px;margin-bottom:20px}}
  .card{{background:#18181b;border:1px solid #27272a;border-radius:12px;padding:14px}}
  .card-label{{font-size:11px;color:#71717a;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px}}
  .card-value{{font-size:24px;font-weight:700;color:#fff}}
  .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}}
  .box{{background:#18181b;border:1px solid #27272a;border-radius:12px;padding:16px}}
  .box h3{{font-size:13px;font-weight:600;color:#a1a1aa;margin-bottom:12px}}
  table{{width:100%;border-collapse:collapse}}
  th{{text-align:left;font-size:11px;color:#52525b;text-transform:uppercase;padding:0 8px 8px}}
  td{{padding:6px 8px;border-top:1px solid #27272a;color:#d4d4d8}}
  .footer{{margin-top:20px;text-align:center;font-size:11px;color:#3f3f46}}
  canvas{{max-height:180px}}
</style>
</head>
<body>
<h1>📊 {title}</h1>
<div class="sub">Live vulnerability posture · Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC</div>
<div class="cards">
  <div class="card"><div class="card-label">Total Findings</div><div class="card-value">{total}</div></div>
  <div class="card"><div class="card-label">Critical</div><div class="card-value" style="color:#ef4444">{critical}</div></div>
  <div class="card"><div class="card-label">High</div><div class="card-value" style="color:#f59e0b">{high}</div></div>
  <div class="card"><div class="card-label">CISA KEV</div><div class="card-value" style="color:#f59e0b">{kev} ⚠️</div></div>
  <div class="card"><div class="card-label">EPSS ≥ 50%</div><div class="card-value" style="color:#a78bfa">{epss_h}</div></div>
  <div class="card"><div class="card-label">Medium / Low</div><div class="card-value" style="color:#10b981">{medium}/{low}</div></div>
</div>
<div class="grid2">
  <div class="box"><h3>Scan Trend</h3><canvas id="trendChart"></canvas></div>
  <div class="box"><h3>Project Risk Score</h3><canvas id="projChart"></canvas></div>
  <div class="box"><h3>Top CVEs by EPSS</h3>
    <table><thead><tr><th>CVE</th><th>Severity</th><th>EPSS</th></tr></thead><tbody>{cve_rows}</tbody></table>
  </div>
  <div class="box"><h3>Severity Mix</h3><canvas id="sev"></canvas></div>
</div>
<div class="footer">Complira Security Intelligence · complira.dev</div>
<script>
new Chart(document.getElementById('trendChart'),{{type:'line',data:{{labels:{trend_labels},datasets:[{{label:'Critical',data:{trend_crit},borderColor:'#ef4444',backgroundColor:'#ef444420',tension:.3,fill:true}},{{label:'High',data:{trend_high},borderColor:'#f59e0b',backgroundColor:'#f59e0b20',tension:.3,fill:true}}]}},options:{{responsive:true,maintainAspectRatio:true,plugins:{{legend:{{labels:{{color:'#a1a1aa',font:{{size:11}}}}}}}},scales:{{x:{{ticks:{{color:'#71717a',font:{{size:10}}}},grid:{{color:'#27272a'}}}},y:{{ticks:{{color:'#71717a',font:{{size:10}}}},grid:{{color:'#27272a'}}}}}}}}}});
new Chart(document.getElementById('projChart'),{{type:'bar',data:{{labels:{proj_js},datasets:[{{label:'Risk Score',data:{proj_score},backgroundColor:'#10b981',borderRadius:4}}]}},options:{{responsive:true,maintainAspectRatio:true,indexAxis:'y',plugins:{{legend:{{display:false}}}},scales:{{x:{{ticks:{{color:'#71717a',font:{{size:10}}}},grid:{{color:'#27272a'}}}},y:{{ticks:{{color:'#71717a',font:{{size:10}}}},grid:{{color:'#27272a'}}}}}}}}}});
new Chart(document.getElementById('sev'),{{type:'doughnut',data:{{labels:['Critical','High','Medium','Low'],datasets:[{{data:[{critical},{high},{medium},{low}],backgroundColor:['#ef4444','#f59e0b','#3b82f6','#10b981'],borderWidth:0}}]}},options:{{responsive:true,maintainAspectRatio:true,plugins:{{legend:{{position:'right',labels:{{color:'#a1a1aa',font:{{size:11}}}}}}}}}}}});
</script>
</body></html>"""


def _render_heatmap(data: dict, title: str) -> str:
    """Render an exploit-chain risk heatmap using get_risk_heatmap_data output."""
    steps        = data.get("chain_steps") or []
    ale          = data.get("ale_total_usd") or 0
    var95        = data.get("var_95_usd") or 0
    var99        = data.get("var_99_usd") or 0
    revenue      = data.get("revenue_context_usd") or 85_000_000
    ale_pct      = data.get("ale_as_pct_revenue") or 0
    cve_id       = data.get("cve_id") or ""
    component    = data.get("component") or ""
    epss_pct     = data.get("epss_pct")
    kev          = data.get("kev", False)
    frameworks   = data.get("frameworks_violated") or []
    intervention = data.get("top_intervention") or {}
    iam_fix      = data.get("iam_intervention")

    def fmt_usd(v: float) -> str:
        if v >= 1_000_000_000:
            return f"${v/1_000_000_000:.1f}B"
        if v >= 1_000_000:
            return f"${v/1_000_000:.1f}M"
        if v >= 1_000:
            return f"${v/1_000:.0f}K"
        return f"${v:.0f}"

    # Bubble chart: x=likelihood_pct, y=financial_impact_usd, r∝1/resistance
    TIER_COLOUR = {"CRITICAL": "#ef4444", "HIGH": "#f59e0b", "MEDIUM": "#3b82f6"}
    bubble_data = []
    for s in steps:
        r = s.get("resistance_score") or 0.05
        bubble_r = max(8, min(40, int((1 - r) * 35 + 6)))
        tier      = s.get("severity_tier", "HIGH")
        colour    = TIER_COLOUR.get(tier, "#f59e0b")
        bubble_data.append({
            "x":     s.get("likelihood_pct", 0),
            "y":     s.get("financial_impact_usd", 0),
            "r":     bubble_r,
            "label": s.get("label", f"Step {s.get('step')}"),
            "step":  s.get("step", 0),
            "colour": colour,
            "tier":  tier,
        })

    # Build per-step HTML rows
    step_rows = ""
    for s in steps:
        tier   = s.get("severity_tier", "HIGH")
        colour = TIER_COLOUR.get(tier, "#f59e0b")
        r_val  = s.get("resistance_score", 0)
        r_pct  = int(r_val * 100)
        r_bar_colour = "#ef4444" if r_pct < 20 else "#f59e0b" if r_pct < 50 else "#10b981"
        step_rows += (
            f'<tr>'
            f'<td style="color:{colour};font-weight:700">Step {s.get("step")}</td>'
            f'<td>{s.get("label","")}</td>'
            f'<td style="text-align:right;color:#a78bfa">{s.get("likelihood_pct",0):.1f}%</td>'
            f'<td style="text-align:right;color:#10b981">{fmt_usd(s.get("financial_impact_usd",0))}</td>'
            f'<td style="text-align:center">'
            f'  <div style="display:inline-flex;align-items:center;gap:4px">'
            f'    <div style="width:40px;height:6px;background:#27272a;border-radius:3px;overflow:hidden">'
            f'      <div style="width:{r_pct}%;height:100%;background:{r_bar_colour}"></div></div>'
            f'    <span style="color:{r_bar_colour};font-size:10px">{r_pct}%</span>'
            f'  </div>'
            f'</td>'
            f'<td style="color:#71717a;font-size:11px">{s.get("control_gap","")}</td>'
            f'</tr>'
        )

    fw_badges = "".join(
        f'<span style="background:#27272a;color:#a1a1aa;padding:2px 8px;border-radius:12px;font-size:11px">{f}</span> '
        for f in frameworks[:6]
    )

    intervention_html = ""
    if intervention:
        intervention_html = f"""
<div style="background:#052e16;border:1px solid #16a34a;border-radius:12px;padding:16px;margin-bottom:16px">
  <div style="font-size:11px;color:#4ade80;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px">⚡ Highest-Leverage Intervention</div>
  <div style="font-weight:600;color:#fff;margin-bottom:4px">{intervention.get('action','')}</div>
  <div style="display:flex;gap:20px;font-size:12px;color:#a1a1aa">
    <span>Risk removed: <strong style="color:#4ade80">{fmt_usd(intervention.get('risk_removed_usd',0))}</strong></span>
    <span>Effort: <strong style="color:#4ade80">{intervention.get('effort','')}</strong></span>
    <span>Breaks chain at: <strong style="color:#4ade80">Step {intervention.get('breaks_chain_at_step','?')}</strong></span>
  </div>
</div>"""
    if iam_fix:
        intervention_html += f"""
<div style="background:#1c1400;border:1px solid #ca8a04;border-radius:12px;padding:14px;margin-bottom:16px">
  <div style="font-size:11px;color:#fbbf24;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px">🔐 IAM Hardening (defence-in-depth)</div>
  <div style="font-weight:600;color:#fff;margin-bottom:4px">{iam_fix.get('action','')}</div>
  <div style="display:flex;gap:20px;font-size:12px;color:#a1a1aa">
    <span>Risk removed: <strong style="color:#fbbf24">{fmt_usd(iam_fix.get('risk_removed_usd',0))}</strong></span>
    <span>Effort: <strong style="color:#fbbf24">{iam_fix.get('effort','')}</strong></span>
  </div>
</div>"""

    # Build Chart.js bubble datasets — one per severity tier for legend
    datasets_by_tier: dict = {}
    for b in bubble_data:
        t = b["tier"]
        if t not in datasets_by_tier:
            datasets_by_tier[t] = {"label": t, "backgroundColor": b["colour"] + "cc", "borderColor": b["colour"], "data": []}
        datasets_by_tier[t]["data"].append({"x": b["x"], "y": b["y"], "r": b["r"], "_label": b["label"]})
    datasets_json = json.dumps(list(datasets_by_tier.values()))

    # Horizontal annotation lines for ALE / VaR
    ale_annotation  = json.dumps({"type": "line", "yMin": ale,  "yMax": ale,  "borderColor": "#f59e0b", "borderWidth": 1, "borderDash": [4, 4], "label": {"display": True, "content": f"ALE {fmt_usd(ale)}", "color": "#f59e0b", "font": {"size": 10}}})
    var95_annotation = json.dumps({"type": "line", "yMin": var95, "yMax": var95, "borderColor": "#ef4444", "borderWidth": 1, "borderDash": [4, 4], "label": {"display": True, "content": f"VaR95 {fmt_usd(var95)}", "color": "#ef4444", "font": {"size": 10}}})

    kev_badge = ' <span style="background:#7c2d12;color:#fca5a5;padding:1px 6px;border-radius:4px;font-size:11px">CISA KEV</span>' if kev else ""
    epss_str  = f" · EPSS {epss_pct}%" if epss_pct is not None else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3.0.1/dist/chartjs-plugin-annotation.min.js"></script>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:#0f1117;color:#e4e4e7;font-family:system-ui,-apple-system,sans-serif;font-size:13px;padding:20px}}
  h1{{font-size:18px;font-weight:700;color:#fff;margin-bottom:2px}}
  .sub{{color:#71717a;font-size:12px;margin-bottom:16px}}
  .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:16px}}
  .card{{background:#18181b;border:1px solid #27272a;border-radius:10px;padding:12px}}
  .card-label{{font-size:10px;color:#71717a;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px}}
  .card-value{{font-size:20px;font-weight:700}}
  .section{{background:#18181b;border:1px solid #27272a;border-radius:12px;padding:16px;margin-bottom:16px}}
  .section h3{{font-size:12px;font-weight:600;color:#a1a1aa;text-transform:uppercase;letter-spacing:.05em;margin-bottom:12px}}
  table{{width:100%;border-collapse:collapse}}
  th{{text-align:left;font-size:10px;color:#52525b;text-transform:uppercase;padding:0 8px 8px}}
  th.r{{text-align:right}}
  td{{padding:7px 8px;border-top:1px solid #1f1f23;color:#d4d4d8;vertical-align:middle}}
  .footer{{margin-top:16px;text-align:center;font-size:11px;color:#3f3f46}}
  canvas{{max-height:280px}}
</style>
</head>
<body>
<h1>🔥 {title}</h1>
<div class="sub">{cve_id} · {component}{epss_str}{kev_badge} · Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC</div>

<div class="cards">
  <div class="card"><div class="card-label">ALE (Annual)</div><div class="card-value" style="color:#f59e0b">{fmt_usd(ale)}</div></div>
  <div class="card"><div class="card-label">VaR 95th pct</div><div class="card-value" style="color:#ef4444">{fmt_usd(var95)}</div></div>
  <div class="card"><div class="card-label">VaR 99th pct</div><div class="card-value" style="color:#ef4444">{fmt_usd(var99)}</div></div>
  <div class="card"><div class="card-label">ALE / Revenue</div><div class="card-value" style="color:#a78bfa">{ale_pct}%</div></div>
  <div class="card"><div class="card-label">Chain Steps</div><div class="card-value" style="color:#fff">{len(steps)}</div></div>
  <div class="card"><div class="card-label">Frameworks</div><div class="card-value" style="color:#10b981">{len(frameworks)}</div></div>
</div>

{intervention_html}

<div class="section">
  <h3>Exploit Chain — Likelihood × Financial Impact</h3>
  <canvas id="heatmap"></canvas>
</div>

<div class="section">
  <h3>Chain Step Breakdown</h3>
  <table>
    <thead><tr>
      <th>Step</th><th>Label</th>
      <th class="r">Likelihood</th><th class="r">Financial Impact</th>
      <th style="text-align:center">Control Resistance</th><th>Gap</th>
    </tr></thead>
    <tbody>{step_rows}</tbody>
  </table>
</div>

<div class="section">
  <h3>Regulatory Frameworks at Risk</h3>
  <div style="display:flex;flex-wrap:wrap;gap:6px">{fw_badges or '<span style="color:#71717a">None detected</span>'}</div>
</div>

<div class="footer">Complira Security Intelligence · complira.dev</div>
<script>
Chart.register(window['chartjs-plugin-annotation']);
const datasets = {datasets_json};
const ctx = document.getElementById('heatmap').getContext('2d');
new Chart(ctx, {{
  type: 'bubble',
  data: {{ datasets }},
  options: {{
    responsive: true,
    maintainAspectRatio: true,
    plugins: {{
      legend: {{ labels: {{ color: '#a1a1aa', font: {{ size: 11 }} }} }},
      tooltip: {{
        callbacks: {{
          label: function(ctx) {{
            const d = ctx.raw;
            const label = d._label || '';
            const usd = new Intl.NumberFormat('en-US', {{style:'currency',currency:'USD',maximumFractionDigits:0}}).format(d.y);
            return [label, `Likelihood: ${{d.x}}%`, `Impact: ${{usd}}`];
          }}
        }}
      }},
      annotation: {{
        annotations: {{
          ale: {ale_annotation},
          var95: {var95_annotation}
        }}
      }}
    }},
    scales: {{
      x: {{
        title: {{ display: true, text: 'Cumulative Likelihood (%)', color: '#71717a', font: {{ size: 11 }} }},
        min: 0, max: 100,
        ticks: {{ color: '#71717a', font: {{ size: 10 }}, callback: v => v + '%' }},
        grid: {{ color: '#1f1f23' }}
      }},
      y: {{
        title: {{ display: true, text: 'Financial Impact (USD)', color: '#71717a', font: {{ size: 11 }} }},
        ticks: {{
          color: '#71717a', font: {{ size: 10 }},
          callback: v => v >= 1e9 ? '$' + (v/1e9).toFixed(1) + 'B' : v >= 1e6 ? '$' + (v/1e6).toFixed(0) + 'M' : '$' + (v/1e3).toFixed(0) + 'K'
        }},
        grid: {{ color: '#1f1f23' }}
      }}
    }}
  }}
}});
</script>
</body></html>"""


def _render_artifact(subtype: str, title: str, data: dict) -> str:
    """Dispatch to the correct server-side renderer."""
    if subtype == "fair_report":
        return _render_fair_report(data, title)
    if subtype == "heatmap":
        return _render_heatmap(data, title)
    return _render_dashboard(data, title)


# ---------------------------------------------------------------------------
# Full streaming agentic loop
# ---------------------------------------------------------------------------

async def _agentic_stream(
    messages: list[dict],
    tenant_id: str,
    db: Any,
) -> AsyncGenerator[str, None]:
    """
    True streaming agentic loop — text tokens flow from the first call;
    tool blocks are detected inline, executed in a threadpool, and injected
    before the next streaming turn.

    SSE event types emitted:
      {"type": "text",        "content": "<token>"}
      {"type": "tool_call",   "name": "<tool>", "args": {...}}
      {"type": "tool_result", "name": "<tool>", "preview": "<truncated>"}
      {"type": "done"}
      {"type": "error",       "content": "<message>"}
    """
    client = anthropic.Anthropic(api_key=_settings.ANTHROPIC_API_KEY)
    current_messages = list(messages)

    for _loop in range(MAX_LOOPS):
        accumulated_text = ""
        tool_blocks: list[dict] = []          # completed tool_use blocks this turn
        active_tool: dict | None = None       # block being assembled
        active_tool_json = ""                 # accumulate input_json_delta fragments

        try:
            with client.messages.stream(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=COMPLIRA_TOOLS,
                tool_choice={"type": "auto"},
                messages=current_messages,
            ) as stream:
                for event in stream:
                    etype = event.type

                    if etype == "content_block_start":
                        block = event.content_block
                        if block.type == "tool_use":
                            active_tool = {"id": block.id, "name": block.name}
                            active_tool_json = ""
                            yield _sse({
                                "type": "tool_call",
                                "name": block.name,
                                "args": {},
                                "source_labels": TOOL_SOURCES.get(block.name, []),
                            })

                    elif etype == "content_block_delta":
                        delta = event.delta
                        if delta.type == "text_delta":
                            accumulated_text += delta.text
                            yield _sse({"type": "text", "content": delta.text})
                        elif delta.type == "input_json_delta":
                            active_tool_json += delta.partial_json

                    elif etype == "content_block_stop":
                        if active_tool is not None:
                            try:
                                parsed = json.loads(active_tool_json) if active_tool_json else {}
                            except json.JSONDecodeError:
                                parsed = {}
                            active_tool["input"] = parsed
                            tool_blocks.append(active_tool)
                            active_tool = None
                            active_tool_json = ""

        except anthropic.RateLimitError as exc:
            yield _sse({"type": "error", "content": "API usage limit reached. Please try again later."})
            return
        except anthropic.APIStatusError as exc:
            if exc.status_code == 400 and "usage limits" in str(exc):
                yield _sse({"type": "error", "content": "API usage limit reached. Please try again later."})
            else:
                msg = exc.message if hasattr(exc, "message") else str(exc)
                yield _sse({"type": "error", "content": msg})
            return
        except anthropic.APIError as exc:
            yield _sse({"type": "error", "content": f"Claude API error: {exc}"})
            return

        # No tools called → Claude is done
        if not tool_blocks:
            yield _sse({"type": "done"})
            return

        # Build assistant content for next turn
        assistant_content: list[dict] = []
        if accumulated_text:
            assistant_content.append({"type": "text", "text": accumulated_text})
        for tb in tool_blocks:
            assistant_content.append({
                "type": "tool_use",
                "id": tb["id"],
                "name": tb["name"],
                "input": tb["input"],
            })
        current_messages.append({"role": "assistant", "content": assistant_content})

        # Execute tools (in threadpool — AQL is synchronous)
        tool_results: list[dict] = []
        for tb in tool_blocks:
            # emit_artifact is handled here — not dispatched to AQL registry.
            # Claude has already generated the full HTML; push it to the frontend
            # as an artifact SSE event and return a synthetic tool_result.
            if tb["name"] == "emit_artifact":
                args = tb["input"]
                subtype = args.get("subtype", "dashboard")
                title   = args.get("title", "Artifact")
                data    = args.get("data", {})
                log.info("emit_artifact called: subtype=%s title=%s data_keys=%s", subtype, title, list(data.keys()))
                try:
                    html = _render_artifact(subtype, title, data)
                    yield _sse({"type": "artifact", "subtype": subtype, "title": title, "html": html})
                    result_content = json.dumps({"status": "rendered", "title": title})
                except Exception as exc:
                    log.error("emit_artifact render failed: %s", exc)
                    result_content = json.dumps({"status": "error", "message": str(exc)})
                yield _sse({"type": "tool_result", "name": tb["name"], "preview": f"Rendered: {title}"})
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tb["id"],
                    "content": result_content,
                })
                continue

            result_json: str = await asyncio.to_thread(
                _execute_tool, tb["name"], tb["input"], tenant_id, db
            )
            preview = _summarize_tool_result(tb["name"], result_json)
            yield _sse({"type": "tool_result", "name": tb["name"], "preview": preview})
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tb["id"],
                "content": result_json,
            })

        current_messages.append({"role": "user", "content": tool_results})

    yield _sse({"type": "error", "content": "Max tool-call rounds reached without final answer"})


# ---------------------------------------------------------------------------
# Request schema + endpoint
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str     # "user" | "assistant"
    content: str

class ChatRequest(BaseModel):
    messages: list[ChatMessage]


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    customer: Customer = Depends(get_current_customer),
):
    """
    POST /v1/chat/stream

    Full conversation history in, server-sent events out.

    SSE event types:
      text        — streamed answer token
      tool_call   — Claude invoked a tool (shows which one)
      tool_result — tool executed (brief data preview)
      done        — stream complete
      error       — something went wrong
    """
    if not body.messages:
        raise HTTPException(status_code=400, detail="messages cannot be empty")

    messages = [{"role": m.role, "content": m.content} for m in body.messages]
    db = get_reference_db()

    return StreamingResponse(
        _agentic_stream(messages, customer.id, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering
        },
    )
