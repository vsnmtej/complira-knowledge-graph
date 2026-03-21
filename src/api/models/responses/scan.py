"""
Scan ingestion response models.
"""

from typing import Optional
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
    status: str = Field(..., description="Processing status (processing, completed, failed)")
    findings_count: int = Field(..., description="Number of findings")
    components_count: int = Field(0, description="Number of components")
    created_at: str = Field(..., description="When session was created (ISO 8601)")
    updated_at: str = Field(..., description="When session was last updated (ISO 8601)")
    metadata: dict = Field(default_factory=dict, description="Scan metadata")
    project_id: Optional[str] = Field(None, description="Project ID (if assigned)")
    repository_id: Optional[str] = Field(None, description="Repository ID (if assigned)")

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "scan_abc123",
                "tool_name": "Semgrep",
                "tool_version": "1.0.0",
                "scan_type": "sast",
                "scan_timestamp": "2026-03-02T10:00:00Z",
                "status": "completed",
                "findings_count": 42,
                "components_count": 0,
                "created_at": "2026-03-02T10:05:00Z",
                "updated_at": "2026-03-02T10:06:00Z",
                "metadata": {
                    "repository": "https://github.com/org/repo",
                    "branch": "main"
                }
            }
        }


class ScanFindingResponse(BaseModel):
    """
    Response model for individual scan finding.
    """

    finding_id: str = Field(..., description="Finding identifier")
    cve_id: str = Field(..., description="CVE identifier")
    severity: str = Field(..., description="Severity level (CRITICAL, HIGH, MEDIUM, LOW, INFO)")
    description: str = Field(..., description="Finding description")
    location: str = Field(..., description="Location (file:line or component@version)")
    tool_name: str = Field(..., description="Scanner tool name")
    created_at: str = Field(..., description="When finding was created (ISO 8601)")

    class Config:
        json_schema_extra = {
            "example": {
                "finding_id": "finding_xyz789",
                "cve_id": "CVE-2021-44228",
                "severity": "CRITICAL",
                "description": "Log4Shell remote code execution vulnerability",
                "location": "src/main/java/App.java:42",
                "tool_name": "Semgrep",
                "created_at": "2026-03-02T10:05:30Z"
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
