"""
v2.2 evidence layer Pydantic models.

These models represent documents in the ArangoDB reference DB (complira_graph)
for the scanner evidence layer: scan_runs, scan_findings, components,
detected_controls, evidence_packages.

All evidence documents (except components) carry tenant_id for multi-tenant isolation.
Components are global (purl-keyed, no tenant_id on document); the
project_uses_component edge carries tenant_id.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# ScanRun — maps to scan_runs collection
# ---------------------------------------------------------------------------

class ScanRun(BaseModel):
    """
    Scan pipeline execution record.

    Collection: scan_runs (reference DB, tenant_id scoped)
    _key: UUID assigned at run creation
    """

    model_config = ConfigDict(populate_by_name=True, ser_json_by_alias=True)

    key: Optional[str] = Field(
        None,
        alias="_key",
        serialization_alias="_key",
        description="UUID (auto-assigned at creation)",
    )
    scan_run_id: Optional[str] = Field(
        None,
        description="UUID v4 — mirrors _key; satisfies unique index idx_scan_runs_id",
    )
    tenant_id: str = Field(..., description="Tenant identifier (= customer_id)")
    project_id: Optional[str] = Field(None)
    repository_id: Optional[str] = Field(None)
    tools_invoked: List[str] = Field(default_factory=list)
    status: str = Field(
        "running",
        description="running | completed | failed",
    )
    finding_counts: Dict[str, int] = Field(
        default_factory=lambda: {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0},
    )
    components_count: int = Field(0)
    compliance_score: Optional[float] = Field(None)
    violated_requirements: List[str] = Field(default_factory=list)
    audit_log: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Checkov SKIPPED entries and other audit events",
    )
    started_at: str = Field(default_factory=_utcnow)
    completed_at: Optional[str] = Field(None)
    error_message: Optional[str] = Field(None)


# ---------------------------------------------------------------------------
# V22Finding — maps to scan_findings collection
# ---------------------------------------------------------------------------

class V22Finding(BaseModel):
    """
    Normalised scanner finding in v2.2 reference DB.

    Collection: scan_findings (reference DB, tenant_id scoped)
    _key: fingerprint (sha256-derived, tool-dependent)
    """

    model_config = ConfigDict(populate_by_name=True, ser_json_by_alias=True)

    key: Optional[str] = Field(
        None,
        alias="_key",
        serialization_alias="_key",
        description="Fingerprint-derived key (idempotent upsert key)",
    )
    fingerprint: str = Field(...)
    tenant_id: str = Field(...)
    scan_run_id: str = Field(..., description="scan_runs _key")
    finding_type: str = Field(
        ...,
        description="sast | secrets | dast | sca | iac_misconfig | supply_chain | firmware | cspm",
    )
    tool: str = Field(..., description="Tool name (matches tool enum in schema)")
    severity: Optional[str] = Field(
        None,
        description="critical | high | medium | low | info | None (absent without API key)",
    )
    severity_normalised: Optional[str] = Field(None)
    cve_id: Optional[str] = Field(None)
    cwe_ids: List[str] = Field(default_factory=list)
    cwe_source: Optional[str] = Field(None, description="tool_direct | extracted | absent")
    rule_id: Optional[str] = Field(None)
    file_path: Optional[str] = Field(None)
    line_start: Optional[int] = Field(None)
    line_end: Optional[int] = Field(None)
    message: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    purl: Optional[str] = Field(None, description="Component context for SCA findings")
    triage_status: str = Field("open")
    tool_vuln_id: Optional[str] = Field(None, description="Non-CVE vuln ID (e.g. GHSA)")
    tool_confidence: Optional[str] = Field(None)
    fix_guidance: Optional[str] = Field(None)
    references: Optional[Any] = Field(None)
    # Checkov IaC-specific fields (optional — only populated for Checkov findings)
    check_id: Optional[str] = Field(None, description="e.g. CKV_AWS_1")
    bc_check_id: Optional[str] = Field(
        None, description="e.g. BC_AWS_1 — only present with --bc-api-key"
    )
    iac_framework: Optional[str] = Field(
        None,
        description="Injected from document-level check_type (terraform, cloudformation, etc.)",
    )
    resource_address: Optional[str] = Field(
        None, description="Checkov resource field mapped to canonical name"
    )
    check_result: Optional[str] = Field(
        None, description="FAILED (extracted from nested {result: 'FAILED'})"
    )
    check_name: Optional[str] = Field(None)
    check_class: Optional[str] = Field(None)
    guideline: Optional[str] = Field(None, description="Remediation URL")
    # Cloud/CSPM fields (Wiz, Orca etc.)
    cloud_resource_id: Optional[str] = Field(None)
    cloud_resource_type: Optional[str] = Field(None)
    cloud_platform: Optional[str] = Field(None)
    cloud_region: Optional[str] = Field(None)
    # Secrets fields
    secret_redacted: Optional[str] = Field(None)
    secret_verified: Optional[bool] = Field(None)
    commit_sha: Optional[str] = Field(None)
    raw_data: Dict[str, Any] = Field(default_factory=dict)
    ingested_at: str = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# V22Component — maps to components collection (global, purl-keyed)
# ---------------------------------------------------------------------------

class V22Component(BaseModel):
    """
    Global component record in reference DB.

    Collection: components (reference DB, global — no tenant_id on document)
    _key: normalize_purl(purl)
    tenant_id is on the project_uses_component edge, not here.
    """

    model_config = ConfigDict(populate_by_name=True, ser_json_by_alias=True)

    key: Optional[str] = Field(
        None,
        alias="_key",
        serialization_alias="_key",
        description="normalize_purl(purl) — global dedup key",
    )
    purl: str = Field(...)
    name: str = Field(...)
    version: Optional[str] = Field(None)
    type: Optional[str] = Field(None, description="library | framework | container | etc.")
    purl_source: str = Field("sbom", description="sbom | scanner")
    sbom_format: Optional[str] = Field(None, description="cyclonedx | spdx")
    cpe: Optional[str] = Field(None)
    license: Optional[str] = Field(None)
    firmware_layer: Optional[str] = Field(None)
    updated_at: str = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# DetectedControl — maps to detected_controls collection
# ---------------------------------------------------------------------------

class DetectedControl(BaseModel):
    """
    Positive security control detection.

    Collection: detected_controls (reference DB, tenant_id scoped)
    _key: fingerprint or check_id-based key

    Sources:
    - Checkov PASSED checks (iac_framework populated)
    - Future: Semgrep control-hit rules
    """

    model_config = ConfigDict(populate_by_name=True, ser_json_by_alias=True)

    key: Optional[str] = Field(
        None,
        alias="_key",
        serialization_alias="_key",
    )
    fingerprint: str = Field(...)
    tenant_id: str = Field(...)
    scan_run_id: str = Field(...)
    tool: str = Field(...)
    control_type: str = Field(
        "iac_check",
        description="iac_check | semgrep_rule | manual",
    )
    check_id: Optional[str] = Field(None, description="Checkov check_id or rule_id")
    check_name: Optional[str] = Field(None)
    iac_framework: Optional[str] = Field(None)
    file_path: Optional[str] = Field(None)
    resource_address: Optional[str] = Field(None)
    triage_status: str = Field("compliant")
    ingested_at: str = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# EvidencePackage — maps to evidence_packages collection
# ---------------------------------------------------------------------------

class EvidencePackage(BaseModel):
    """
    Evidence package for regulatory submission.

    Collection: evidence_packages (reference DB, tenant_id scoped)
    _key: UUID

    Links scan run + findings + project for a point-in-time compliance snapshot.
    """

    model_config = ConfigDict(populate_by_name=True, ser_json_by_alias=True)

    key: Optional[str] = Field(
        None,
        alias="_key",
        serialization_alias="_key",
    )
    tenant_id: str = Field(...)
    project_id: Optional[str] = Field(None)
    scan_run_id: str = Field(...)
    finding_count: int = Field(0)
    component_count: int = Field(0)
    compliance_score: Optional[float] = Field(None)
    violated_requirements: List[str] = Field(default_factory=list)
    package_type: str = Field(
        "scan_evidence",
        description="scan_evidence | audit_package | certification_snapshot",
    )
    assembled_at: str = Field(default_factory=_utcnow)
