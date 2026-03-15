"""
VEX (Vulnerability Exploitability eXchange) request models.

Supports CycloneDX 1.5 VEX format from client applications.
"""

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime


class VEXAnalysisRequest(BaseModel):
    """
    VEX vulnerability analysis from client (CycloneDX 1.5 format).

    Represents the exploitability assessment for a single vulnerability.
    """

    state: Literal["exploitable", "in_triage", "not_affected", "resolved", "false_positive"] = Field(
        ...,
        description="VEX assessment state"
    )

    justification: Optional[Literal[
        "code_not_present",
        "code_not_reachable",
        "requires_configuration",
        "requires_dependency",
        "requires_environment",
        "protected_by_compiler",
        "protected_at_runtime",
        "protected_at_perimeter",
        "protected_by_mitigating_control"
    ]] = Field(
        None,
        description="Justification for 'not_affected' state"
    )

    response: Optional[List[Literal["can_not_fix", "will_not_fix", "update", "rollback", "workaround_available"]]] = Field(
        None,
        description="Response actions (for exploitable/affected vulnerabilities)"
    )

    detail: Optional[str] = Field(
        None,
        description="Detailed explanation of the assessment",
        max_length=4000
    )


class VEXVulnerabilityRequest(BaseModel):
    """
    Single vulnerability entry in VEX document from client.
    """

    id: str = Field(
        ...,
        description="CVE identifier (e.g., CVE-2021-44228)",
        pattern=r"^CVE-\d{4}-\d{4,}$"
    )

    analysis: VEXAnalysisRequest = Field(
        ...,
        description="VEX analysis assessment"
    )

    affects: Optional[List[Dict[str, str]]] = Field(
        None,
        description="List of affected components (CycloneDX format with 'ref' field)"
    )


class VEXDocumentRequest(BaseModel):
    """
    VEX document from client application (CycloneDX 1.5 format).

    Clients generate VEX documents with their reachability analysis,
    and the API enriches them with knowledge graph data.
    """

    # Optional CycloneDX metadata
    bomFormat: Optional[str] = Field(
        "CycloneDX",
        description="BOM format identifier"
    )

    specVersion: Optional[str] = Field(
        "1.5",
        description="CycloneDX specification version"
    )

    version: Optional[int] = Field(
        1,
        description="VEX document version number"
    )

    # Core VEX data
    vulnerabilities: List[VEXVulnerabilityRequest] = Field(
        ...,
        description="List of vulnerability assessments",
        min_length=1
    )

    # Metadata
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional metadata (component info, timestamp, etc.)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "bomFormat": "CycloneDX",
                "specVersion": "1.5",
                "version": 1,
                "vulnerabilities": [
                    {
                        "id": "CVE-2021-44228",
                        "analysis": {
                            "state": "not_affected",
                            "justification": "code_not_reachable",
                            "detail": "Log4j is included but logging is disabled in production configuration"
                        }
                    },
                    {
                        "id": "CVE-2024-2508",
                        "analysis": {
                            "state": "exploitable",
                            "response": ["update"],
                            "detail": "Vulnerability confirmed exploitable, patch available"
                        }
                    }
                ],
                "metadata": {
                    "component": {
                        "type": "application",
                        "name": "my-app",
                        "version": "1.0.0"
                    },
                    "timestamp": "2026-03-10T10:00:00Z"
                }
            }
        }


class VEXUpdateRequest(BaseModel):
    """
    Request to update entire VEX document (PUT operation).
    """

    vulnerabilities: List[VEXVulnerabilityRequest] = Field(
        ...,
        description="Updated list of vulnerability assessments",
        min_length=1
    )

    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Updated metadata"
    )


class VEXVulnerabilityPatchRequest(BaseModel):
    """
    Request to update single vulnerability assessment (PATCH operation).
    """

    analysis: VEXAnalysisRequest = Field(
        ...,
        description="Updated VEX analysis for this vulnerability"
    )
