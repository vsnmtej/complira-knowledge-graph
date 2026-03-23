"""
Scan ingestion response models.
"""

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class ScanIngestResponse(BaseModel):
    """
    Response model for POST /v1/scan/ingest.

    Returns scan session ID and processing statistics.
    """

    scan_run_id: str = Field(
        ...,
        description="Unique identifier for this scan run (use to query scan status and findings)"
    )

    findings_count: int = Field(
        ...,
        description="Number of vulnerability findings ingested"
    )

    components_count: int = Field(
        0,
        description="Number of SBOM components ingested (for SCA/SBOM scans only)"
    )

    status: str = Field(
        "processing",
        description="Scan processing status (processing, completed, failed)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "scan_run_id": "scan_abc123",
                "findings_count": 42,
                "components_count": 150,
                "status": "completed"
            }
        }


class LLMTokenUsage(BaseModel):
    """Token usage from Phase 2 LLM enrichment (UC-010)."""

    input_tokens: int = Field(..., description="Tokens consumed in prompts")
    output_tokens: int = Field(..., description="Tokens generated in completions")
    total_tokens: int = Field(..., description="Total tokens consumed")
    model: str = Field(..., description="LLM model ID used")


class Phase2Summary(BaseModel):
    """
    Aggregate Phase 2 intelligence summary over all findings for a scan run.
    Computed at query time from scan_findings.
    """

    rising_count: int = Field(0, description="Findings with epss_trend == 'rising'")
    stable_count: int = Field(0, description="Findings with epss_trend == 'stable'")
    falling_count: int = Field(0, description="Findings with epss_trend == 'falling'")
    avg_blast_radius: Optional[float] = Field(
        None, description="Mean blast_radius_score across findings with score (null if none)"
    )
    top_blast_radius_findings: List[str] = Field(
        default_factory=list,
        description="Top 5 finding _key values by blast_radius_score DESC"
    )


class ScanSessionResponse(BaseModel):
    """
    Response model for GET /v1/scan/{session_id}.

    Returns detailed scan session information.
    """

    session_id: str = Field(..., description="Scan session identifier")
    tool_name: str = Field(..., description="Scanner tool name")
    tool_version: str = Field(..., description="Scanner tool version")
    scan_type: str = Field(..., description="Type of scan (sast, dast, sca, etc.)")
    scan_timestamp: str = Field(..., description="When scan was executed (ISO 8601)")
    status: str = Field(..., description="Processing status")
    findings_count: int = Field(..., description="Number of findings")
    components_count: int = Field(0, description="Number of components")
    created_at: str = Field(..., description="When session was created (ISO 8601)")
    updated_at: str = Field(..., description="When session was last updated (ISO 8601)")
    metadata: dict = Field(default_factory=dict, description="Scan metadata")
    project_id: Optional[str] = Field(None, description="Project ID (if assigned)")
    repository_id: Optional[str] = Field(None, description="Repository ID (if assigned)")

    # Phase 1 pipeline fields
    coverage_by_framework: Optional[Dict[str, float]] = Field(
        None, description="Framework coverage percentages written by UC-009"
    )

    # Phase 2 pipeline fields
    llm_token_usage: Optional[LLMTokenUsage] = Field(
        None, description="LLM token usage from UC-010 (null if LLM stage not run)"
    )
    phase2_summary: Optional[Phase2Summary] = Field(
        None, description="Aggregate Phase 2 stats computed from findings at query time"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "scan_abc123",
                "tool_name": "Semgrep",
                "tool_version": "1.0.0",
                "scan_type": "sast",
                "scan_timestamp": "2026-03-02T10:00:00Z",
                "status": "velocity_computed",
                "findings_count": 42,
                "components_count": 0,
                "created_at": "2026-03-02T10:05:00Z",
                "updated_at": "2026-03-02T10:06:00Z",
                "metadata": {},
                "coverage_by_framework": {"NIST 800-53": 42.7, "ISO 27001": 31.2},
                "llm_token_usage": {
                    "input_tokens": 3500,
                    "output_tokens": 800,
                    "total_tokens": 4300,
                    "model": "claude-haiku-4-5-20251001"
                },
                "phase2_summary": {
                    "rising_count": 5,
                    "stable_count": 30,
                    "falling_count": 7,
                    "avg_blast_radius": 0.23,
                    "top_blast_radius_findings": ["fp1", "fp2", "fp3", "fp4", "fp5"]
                }
            }
        }


class ScanFindingResponse(BaseModel):
    """
    Response model for individual scan finding.

    Includes Phase 1 enrichment fields (UC-007/008) and Phase 2 intelligence
    fields (UC-010/011/012). All enrichment fields are Optional — they are null
    when the pipeline stage has not yet completed for this finding.
    """

    # Core fields (always present)
    finding_id: str = Field(..., description="Finding identifier (_key)")
    cve_id: str = Field(..., description="CVE identifier or rule_id")
    severity: str = Field(..., description="Severity level (CRITICAL, HIGH, MEDIUM, LOW, INFO)")
    description: str = Field(..., description="Finding description")
    location: str = Field(..., description="Location (file:line or component@version)")
    tool_name: str = Field(..., description="Scanner tool name")
    created_at: str = Field(..., description="When finding was ingested (ISO 8601)")

    # Phase 1 enrichment fields (UC-007: vulnerability enrichment)
    cvss_base: Optional[float] = Field(None, description="CVSS base score [0, 10]")
    epss_score: Optional[float] = Field(None, description="EPSS probability score [0, 1]")
    epss_percentile: Optional[float] = Field(None, description="EPSS percentile [0, 1]")
    in_kev: Optional[bool] = Field(None, description="True if CVE is in CISA KEV catalog")
    cwe_chain: Optional[List[str]] = Field(None, description="CWE weakness chain for this CVE")
    d3fend_techniques: Optional[List[str]] = Field(
        None, description="D3FEND defensive techniques applicable to this finding"
    )

    # Phase 1 compaction/risk fields (UC-008)
    risk_score: Optional[float] = Field(None, description="Composite risk score [0, 1]")
    compaction_group_id: Optional[str] = Field(
        None, description="CWE-based compaction group identifier"
    )
    cluster_rank: Optional[int] = Field(
        None, description="Cluster rank (1 = highest risk cluster)"
    )
    compacted: Optional[bool] = Field(
        None, description="True if this finding is a duplicate within its compaction group"
    )

    # Phase 2 LLM enrichment fields (UC-010)
    llm_risk_summary: Optional[str] = Field(
        None, description="Plain-language risk description (≤3 sentences)"
    )
    llm_remediation: Optional[str] = Field(
        None, description="1–3 actionable remediation steps"
    )
    llm_attack_surface: Optional[Literal["network", "local", "adjacent"]] = Field(
        None, description="Attack surface derived from CVSS AV or LLM inference"
    )
    llm_enriched_at: Optional[str] = Field(
        None, description="ISO 8601 timestamp when LLM enrichment completed"
    )

    # Phase 2 blast radius fields (UC-011)
    blast_radius_score: Optional[float] = Field(
        None, description="Blast radius score [0, 1] — fraction of project components affected"
    )
    affected_components: Optional[List[str]] = Field(
        None, description="PURLs of all reachable dependent components"
    )
    blast_radius_path: Optional[List[str]] = Field(
        None, description="Component names along the blast radius traversal path"
    )
    blast_radius_computed_at: Optional[str] = Field(
        None, description="ISO 8601 timestamp when blast radius was computed"
    )

    # Phase 2 EPSS velocity fields (UC-012)
    epss_velocity: Optional[float] = Field(
        None, description="OLS slope of EPSS score per day (positive = rising)"
    )
    epss_trend: Optional[Literal["rising", "stable", "falling"]] = Field(
        None, description="EPSS trend classification"
    )
    epss_velocity_computed_at: Optional[str] = Field(
        None, description="ISO 8601 timestamp when EPSS velocity was computed"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "finding_id": "fp_xyz789",
                "cve_id": "CVE-2021-44228",
                "severity": "CRITICAL",
                "description": "Log4Shell remote code execution vulnerability",
                "location": "src/main/java/App.java:42",
                "tool_name": "Grype",
                "created_at": "2026-03-02T10:05:30Z",
                "cvss_base": 10.0,
                "epss_score": 0.974,
                "epss_percentile": 0.999,
                "in_kev": True,
                "cwe_chain": ["CWE-917"],
                "d3fend_techniques": ["D3-NTF"],
                "risk_score": 0.89,
                "compaction_group_id": "cg_cwe917",
                "cluster_rank": 1,
                "compacted": False,
                "llm_risk_summary": "This Log4Shell vulnerability allows unauthenticated RCE.",
                "llm_remediation": "Upgrade log4j to 2.17.1 or later.",
                "llm_attack_surface": "network",
                "llm_enriched_at": "2026-03-02T10:07:00Z",
                "blast_radius_score": 0.42,
                "affected_components": ["pkg:maven/org.example/service@1.0"],
                "blast_radius_path": ["log4j-core", "service"],
                "blast_radius_computed_at": "2026-03-02T10:07:30Z",
                "epss_velocity": 0.009,
                "epss_trend": "rising",
                "epss_velocity_computed_at": "2026-03-02T10:08:00Z"
            }
        }


class VEXGenerationResponse(BaseModel):
    """
    Response model for POST /v1/scan/{session_id}/vex.

    Returns VEX (Vulnerability Exploitability eXchange) document.
    """

    scan_session_id: str = Field(
        ...,
        description="Scan session identifier this VEX was generated for"
    )

    vex_document: dict = Field(
        ...,
        description="CycloneDX VEX document (JSON format)"
    )

    vulnerabilities_assessed: int = Field(
        ...,
        description="Number of vulnerabilities assessed in this VEX"
    )

    generated_at: str = Field(
        ...,
        description="When VEX was generated (ISO 8601)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "scan_session_id": "scan_abc123",
                "vex_document": {
                    "bomFormat": "CycloneDX",
                    "specVersion": "1.5",
                    "version": 1,
                    "vulnerabilities": [
                        {
                            "id": "CVE-2021-44228",
                            "analysis": {
                                "state": "not_affected",
                                "justification": "vulnerable_code_not_in_execute_path",
                                "detail": "Log4j is included but logging is disabled"
                            }
                        }
                    ]
                },
                "vulnerabilities_assessed": 5,
                "generated_at": "2026-03-06T10:15:00Z"
            }
        }


class CPEMatchingResponse(BaseModel):
    """
    Response model for POST /v1/scan/{session_id}/cpe-match.

    Returns CPE matching results for SBOM components.
    """

    scan_session_id: str = Field(
        ...,
        description="Scan session identifier CPE matching was performed for"
    )

    components_processed: int = Field(
        ...,
        description="Number of components analyzed for CPE matching"
    )

    cpe_mappings_created: int = Field(
        ...,
        description="Number of matched_by_cpe edges created"
    )

    completed_at: str = Field(
        ...,
        description="When CPE matching completed (ISO 8601)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "scan_session_id": "scan_abc123",
                "components_processed": 150,
                "cpe_mappings_created": 142,
                "completed_at": "2026-03-06T11:30:00Z"
            }
        }
