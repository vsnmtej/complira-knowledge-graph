"""
VEX (Vulnerability Exploitability eXchange) response models.

Returns enriched VEX documents with knowledge graph data.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class VEXEnrichment(BaseModel):
    """
    Knowledge graph enrichment data added by API.
    """

    # KEV data
    in_kev: bool = Field(
        False,
        description="Whether CVE is in CISA KEV catalog (actively exploited)"
    )

    kev_date_added: Optional[str] = Field(
        None,
        description="Date added to KEV catalog (ISO 8601)"
    )

    kev_due_date: Optional[str] = Field(
        None,
        description="Federal remediation deadline (ISO 8601)"
    )

    # EPSS data
    epss_score: Optional[float] = Field(
        None,
        description="EPSS probability score (0.0-1.0)"
    )

    epss_percentile: Optional[float] = Field(
        None,
        description="EPSS percentile ranking (0.0-1.0)"
    )

    # CVSS data
    cvss_score: Optional[float] = Field(
        None,
        description="CVSS v3 base score (0.0-10.0)"
    )

    cvss_severity: Optional[str] = Field(
        None,
        description="CVSS severity (CRITICAL, HIGH, MEDIUM, LOW)"
    )

    # CWE weaknesses
    weaknesses: List[Dict[str, str]] = Field(
        default_factory=list,
        description="CWE weakness types (e.g., [{'cwe_id': 'CWE-502', 'name': 'Deserialization...'}])"
    )

    # ATT&CK techniques
    attack_techniques: List[Dict[str, str]] = Field(
        default_factory=list,
        description="MITRE ATT&CK techniques (e.g., [{'technique_id': 'T1190', 'name': 'Exploit Public-Facing Application'}])"
    )

    # NIST controls
    nist_controls: List[Dict[str, str]] = Field(
        default_factory=list,
        description="NIST 800-53 mitigation controls (e.g., [{'control_id': 'SI-10', 'title': 'Information Input Validation'}])"
    )

    # D3FEND defenses
    d3fend_defenses: List[Dict[str, str]] = Field(
        default_factory=list,
        description="D3FEND defensive techniques"
    )

    # Regulatory requirements
    regulatory_violations: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Violated regulatory requirements (e.g., [{'framework': 'EU_CRA', 'requirement_id': 'ANNEX_I_1_a'}])"
    )


class VEXVulnerabilityResponse(BaseModel):
    """
    Single vulnerability entry in enriched VEX document.
    """

    # Original client data
    cve_id: str = Field(
        ...,
        description="CVE identifier"
    )

    state: str = Field(
        ...,
        description="VEX assessment state (exploitable, not_affected, etc.)"
    )

    justification: Optional[str] = Field(
        None,
        description="Justification for assessment"
    )

    response: Optional[List[str]] = Field(
        None,
        description="Response actions"
    )

    detail: Optional[str] = Field(
        None,
        description="Detailed explanation"
    )

    # Knowledge graph enrichment (added by API)
    enrichment: VEXEnrichment = Field(
        ...,
        description="Knowledge graph enrichment data from API"
    )


class VEXDocumentResponse(BaseModel):
    """
    Enriched VEX document returned by API.

    Combines client-provided assessments with knowledge graph enrichment.
    """

    vex_id: str = Field(
        ...,
        description="Unique VEX document identifier"
    )

    # CycloneDX metadata
    bomFormat: str = Field(
        "CycloneDX",
        description="BOM format identifier"
    )

    specVersion: str = Field(
        "1.5",
        description="CycloneDX specification version"
    )

    version: int = Field(
        ...,
        description="VEX document version number"
    )

    # Enriched vulnerabilities
    vulnerabilities: List[VEXVulnerabilityResponse] = Field(
        ...,
        description="List of vulnerability assessments with enrichment"
    )

    # Metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="VEX document metadata"
    )

    # Timestamps
    created_at: str = Field(
        ...,
        description="When VEX was created (ISO 8601)"
    )

    updated_at: str = Field(
        ...,
        description="When VEX was last updated (ISO 8601)"
    )

    # Customer
    customer_id: str = Field(
        ...,
        description="Customer ID who owns this VEX"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "vex_id": "vex_abc123",
                "bomFormat": "CycloneDX",
                "specVersion": "1.5",
                "version": 1,
                "vulnerabilities": [
                    {
                        "cve_id": "CVE-2021-44228",
                        "state": "not_affected",
                        "justification": "code_not_reachable",
                        "detail": "Log4j included but logging disabled",
                        "enrichment": {
                            "in_kev": True,
                            "kev_date_added": "2021-12-10T00:00:00Z",
                            "kev_due_date": "2021-12-24T00:00:00Z",
                            "epss_score": 0.97542,
                            "epss_percentile": 0.99876,
                            "cvss_score": 10.0,
                            "cvss_severity": "CRITICAL",
                            "weaknesses": [
                                {
                                    "cwe_id": "CWE-502",
                                    "name": "Deserialization of Untrusted Data"
                                }
                            ],
                            "attack_techniques": [
                                {
                                    "technique_id": "T1190",
                                    "name": "Exploit Public-Facing Application"
                                }
                            ],
                            "nist_controls": [
                                {
                                    "control_id": "SI-10",
                                    "title": "Information Input Validation"
                                }
                            ],
                            "d3fend_defenses": [],
                            "regulatory_violations": [
                                {
                                    "framework": "EU_CRA",
                                    "requirement_id": "ANNEX_I_1_a"
                                }
                            ]
                        }
                    }
                ],
                "metadata": {
                    "component": {
                        "type": "application",
                        "name": "my-app",
                        "version": "1.0.0"
                    }
                },
                "created_at": "2026-03-10T10:00:00Z",
                "updated_at": "2026-03-10T10:00:00Z",
                "customer_id": "customer_123"
            }
        }


class VEXCreateResponse(BaseModel):
    """
    Response after creating a VEX document.
    """

    vex_id: str = Field(
        ...,
        description="Unique VEX document identifier"
    )

    vulnerabilities_count: int = Field(
        ...,
        description="Number of vulnerabilities assessed"
    )

    enriched_count: int = Field(
        ...,
        description="Number of vulnerabilities successfully enriched with knowledge graph data"
    )

    created_at: str = Field(
        ...,
        description="When VEX was created (ISO 8601)"
    )


class VEXUpdateResponse(BaseModel):
    """
    Response after updating a VEX document.
    """

    vex_id: str = Field(
        ...,
        description="VEX document identifier"
    )

    updated_at: str = Field(
        ...,
        description="When VEX was updated (ISO 8601)"
    )

    vulnerabilities_count: int = Field(
        ...,
        description="Total vulnerability count after update"
    )


class VEXListResponse(BaseModel):
    """
    Response for listing VEX documents.
    """

    vex_id: str = Field(
        ...,
        description="VEX document identifier"
    )

    vulnerabilities_count: int = Field(
        ...,
        description="Number of vulnerability assessments"
    )

    created_at: str = Field(
        ...,
        description="When VEX was created (ISO 8601)"
    )

    updated_at: str = Field(
        ...,
        description="When VEX was last updated (ISO 8601)"
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="VEX metadata"
    )
