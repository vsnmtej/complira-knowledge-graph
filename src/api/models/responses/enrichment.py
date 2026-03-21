"""
Pydantic models for enrichment API responses.

Used by Phase 1 graph-based intelligence endpoints.
All data is authoritative (EPSS, KEV, CVSS, ATT&CK, D3FEND) - no LLM.
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime


class RiskFactors(BaseModel):
    """
    Risk factors calculated from authoritative data.
    """
    high_epss: bool = Field(
        default=False,
        description="EPSS > 0.7 (high exploitation probability)"
    )
    actively_exploited: bool = Field(
        default=False,
        description="In CISA KEV catalog (confirmed active exploitation)"
    )
    high_cvss: bool = Field(
        default=False,
        description="CVSS >= 9.0 (critical severity)"
    )
    public_exploits: bool = Field(
        default=False,
        description="Public exploits available"
    )
    threat_groups_using: bool = Field(
        default=False,
        description="Known threat groups using related techniques"
    )


class Defense(BaseModel):
    """
    D3FEND defensive countermeasure.
    """
    d3fend_id: str = Field(..., description="D3FEND identifier")
    name: str = Field(..., description="Defense technique name")
    description: Optional[str] = Field(None, description="Description")
    coverage: List[str] = Field(
        default_factory=list,
        description="What this defense covers (CWE, CAPEC, ATT&CK)"
    )


class AttackPathStage(BaseModel):
    """
    Single stage in an attack path (pure graph traversal).
    """
    stage: str = Field(
        ...,
        description="Stage type: vulnerability, weakness, attack_pattern, technique, threat_groups"
    )
    node: Optional[str] = Field(
        None,
        description="Node identifier (CVE, CWE, CAPEC, ATT&CK technique)"
    )
    nodes: Optional[List[str]] = Field(
        None,
        description="Multiple nodes (for threat groups)"
    )
    name: Optional[str] = Field(None, description="Human-readable name")
    description: Optional[str] = Field(None, description="Description from graph")


class AttackPath(BaseModel):
    """
    Complete attack path from CVE to threat groups (pure graph traversal).
    """
    path: List[AttackPathStage] = Field(
        default_factory=list,
        description="Attack chain stages (CVE → CWE → CAPEC → ATT&CK → Threat Groups)"
    )
    defenses: List[Defense] = Field(
        default_factory=list,
        description="D3FEND defensive countermeasures"
    )


class ComplianceMapping(BaseModel):
    """
    Compliance framework mapping (graph traversal).
    """
    nist_controls: List[str] = Field(
        default_factory=list,
        description="NIST 800-53 controls"
    )
    frameworks: List[str] = Field(
        default_factory=list,
        description="Applicable regulatory frameworks (FDA_524B, ISO_27001, etc.)"
    )


class CVEEnrichment(BaseModel):
    """
    Complete CVE enrichment with graph-based intelligence.
    All data is authoritative (EPSS, KEV, CVSS, ATT&CK, D3FEND) - no LLM.
    """
    cve_id: str = Field(..., description="CVE identifier")

    # Authoritative scores
    description: Optional[str] = Field(None, description="CVE description")
    cvss_score: Optional[float] = Field(None, description="CVSS v3 base score")
    cvss_vector: Optional[str] = Field(None, description="CVSS vector string")
    cvss_severity: Optional[str] = Field(None, description="Severity level (CRITICAL, HIGH, MEDIUM, LOW)")
    epss_score: Optional[float] = Field(None, description="EPSS exploitation probability (0.0-1.0)")
    in_kev: bool = Field(default=False, description="In CISA KEV catalog (actively exploited)")
    exploit_count: int = Field(default=0, description="Number of known public exploits")
    published_date: Optional[str] = Field(None, description="CVE publication date")
    last_modified: Optional[str] = Field(None, description="CVE last modified date")

    # Smart risk score (calculated from authoritative data)
    risk_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Calculated risk score (0.0-1.0) based on CVSS + EPSS + KEV + exploits"
    )
    priority: str = Field(
        ...,
        description="Priority level: CRITICAL, HIGH, MEDIUM, LOW"
    )
    risk_factors: RiskFactors = Field(
        ...,
        description="Boolean risk factors"
    )

    # Graph intelligence
    cwe_list: List[str] = Field(
        default_factory=list,
        description="Associated CWE weakness IDs"
    )
    attack_techniques: List[str] = Field(
        default_factory=list,
        description="MITRE ATT&CK technique IDs"
    )
    threat_groups: List[str] = Field(
        default_factory=list,
        description="Known threat groups using related techniques"
    )

    # Optional detailed analysis
    attack_path: Optional[AttackPath] = Field(
        None,
        description="Attack path from CVE to threat groups (if requested)"
    )
    compliance: Optional[ComplianceMapping] = Field(
        None,
        description="Compliance framework mappings (if requested)"
    )

    enriched_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Timestamp of enrichment"
    )


class EnrichmentRequest(BaseModel):
    """
    Request for CVE enrichment.
    """
    cve_ids: List[str] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of CVE IDs to enrich (max 100)"
    )
    include_attack_paths: bool = Field(
        default=False,
        description="Include full attack path traversal (CVE → CWE → CAPEC → ATT&CK → Threat Groups)"
    )
    include_compliance: bool = Field(
        default=False,
        description="Include compliance framework mappings (NIST, FDA, ISO)"
    )


class EnrichmentResponse(BaseModel):
    """
    Response from enrichment endpoint.
    """
    enriched: List[CVEEnrichment] = Field(
        ...,
        description="Enriched CVE data with graph-based intelligence"
    )
    total: int = Field(
        ...,
        description="Total CVEs enriched"
    )
    processing_time_ms: float = Field(
        ...,
        description="Total processing time in milliseconds"
    )


class ControlMapping(BaseModel):
    """
    Mapping of a finding to a compliance control.
    """
    control_id: str = Field(..., description="Control identifier (e.g., SI-2)")
    title: str = Field(..., description="Control title")
    findings_count: int = Field(..., description="Number of findings mapped to this control")
    critical_findings: int = Field(..., description="Number of critical findings")
    high_findings: int = Field(default=0, description="Number of high severity findings")
    medium_findings: int = Field(default=0, description="Number of medium severity findings")
    low_findings: int = Field(default=0, description="Number of low severity findings")
    rationale: str = Field(..., description="Why this control applies to these findings")


class ComplianceGap(BaseModel):
    """
    Identified gap in compliance coverage.
    """
    control_id: str = Field(..., description="Control identifier")
    title: str = Field(..., description="Control title")
    issue: str = Field(..., description="Description of the gap")
    recommendation: str = Field(..., description="How to address the gap")


class FrameworkMapping(BaseModel):
    """
    Compliance framework mapping with controls and gaps.
    """
    framework: str = Field(..., description="Framework name (NIST_800_53, FDA_524B, etc.)")
    controls: List[ControlMapping] = Field(
        ...,
        description="Controls with findings mapped"
    )
    coverage: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Coverage percentage (0-100)"
    )
    gaps: List[ComplianceGap] = Field(
        default_factory=list,
        description="Identified gaps in coverage"
    )


class ComplianceMappingRequest(BaseModel):
    """
    Request for compliance mapping.
    """
    scan_session_id: Optional[str] = Field(
        None,
        description="Scan session ID to map (customer-specific)"
    )
    cve_ids: Optional[List[str]] = Field(
        None,
        description="List of CVE IDs to map (alternative to scan_session_id)"
    )
    frameworks: List[str] = Field(
        ...,
        min_length=1,
        description="Frameworks to map to (NIST_800_53, FDA_524B, ISO_27001, EU_CRA)"
    )
    include_gap_analysis: bool = Field(
        default=True,
        description="Include LLM-powered gap analysis"
    )


class ComplianceMappingResponse(BaseModel):
    """
    Response from compliance mapping endpoint.
    """
    mappings: Dict[str, FrameworkMapping] = Field(
        ...,
        description="Mappings by framework"
    )
    total_findings: int = Field(
        ...,
        description="Total findings analyzed"
    )
    llm_enabled: bool = Field(
        ...,
        description="Whether LLM gap analysis was available"
    )
    processing_time_ms: float = Field(
        ...,
        description="Total processing time in milliseconds"
    )


class BlastRadiusRequest(BaseModel):
    """
    Request for blast radius analysis.
    """
    cve_id: str = Field(
        ...,
        description="CVE identifier to analyze"
    )
    customer_context: bool = Field(
        default=False,
        description="Include customer-specific context (requires authentication)"
    )


class AttackSurface(BaseModel):
    """
    Attack surface analysis.
    """
    entry_points: List[str] = Field(
        default_factory=list,
        description="Potential entry points"
    )
    data_at_risk: List[str] = Field(
        default_factory=list,
        description="Types of data at risk"
    )
    business_impact: str = Field(
        ...,
        description="Business impact level: SEVERE, HIGH, MEDIUM, LOW"
    )


class ThreatLandscape(BaseModel):
    """
    Threat landscape analysis.
    """
    active_exploits: int = Field(
        default=0,
        description="Number of active exploits in the wild"
    )
    threat_groups: List[str] = Field(
        default_factory=list,
        description="Known threat groups exploiting this vulnerability"
    )
    ransomware_risk: str = Field(
        default="UNKNOWN",
        description="Ransomware risk level: CRITICAL, HIGH, MEDIUM, LOW, UNKNOWN"
    )


class ComplianceImpact(BaseModel):
    """
    Compliance impact analysis.
    """
    frameworks_affected: List[str] = Field(
        default_factory=list,
        description="Regulatory frameworks affected"
    )
    regulatory_deadlines: List[str] = Field(
        default_factory=list,
        description="Applicable regulatory deadlines"
    )
    disclosure_requirements: List[str] = Field(
        default_factory=list,
        description="Disclosure requirements"
    )


class BlastRadiusData(BaseModel):
    """
    Blast radius analysis data.
    """
    affected_components: int = Field(
        ...,
        description="Number of affected components in customer environment"
    )
    affected_codebases: List[str] = Field(
        default_factory=list,
        description="Affected codebases/repositories"
    )
    attack_surface: AttackSurface = Field(
        ...,
        description="Attack surface analysis"
    )
    threat_landscape: ThreatLandscape = Field(
        ...,
        description="Threat landscape analysis"
    )
    compliance_impact: ComplianceImpact = Field(
        ...,
        description="Compliance impact analysis"
    )


class BlastRadiusResponse(BaseModel):
    """
    Response from blast radius endpoint.
    """
    cve_id: str = Field(..., description="CVE identifier")
    blast_radius: BlastRadiusData = Field(
        ...,
        description="Blast radius analysis"
    )
    llm_enabled: bool = Field(
        ...,
        description="Whether LLM analysis was available"
    )
    processing_time_ms: float = Field(
        ...,
        description="Total processing time in milliseconds"
    )
