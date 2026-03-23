"""
Compliance violation response models.
"""

from pydantic import BaseModel, Field
from typing import List


class ViolationItem(BaseModel):
    """Single compliance violation entry (finding → NIST 800-53 control)."""

    finding_id: str = Field(..., description="Scan finding key")
    cve_id: str = Field(..., description="CVE identifier")
    control_id: str = Field(..., description="NIST 800-53 control identifier (e.g. AC-2, SI-2)")
    framework: str = Field(..., description="Regulatory framework (e.g. NIST_800_53)")
    confidence: float = Field(..., description="Mapping confidence (1.0 for deterministic chain)")
    evidence_path: List[str] = Field(
        default_factory=list,
        description="Traversal chain vertex keys: [cve_key, cwe_key, capec_key, attack_key, control_key]",
    )


class ViolationsResponse(BaseModel):
    """Response model for GET /v1/compliance/violations."""

    items: List[ViolationItem] = Field(default_factory=list, description="Violation entries")
    total: int = Field(..., description="Total number of violation entries")


class FrameworkCoverage(BaseModel):
    """Per-framework coverage entry."""

    framework: str = Field(..., description="Framework identifier")
    violated_control_count: int = Field(..., description="Number of distinct controls violated")
    control_ids: List[str] = Field(default_factory=list, description="Violated control identifiers")


class CoverageResponse(BaseModel):
    """Response model for GET /v1/compliance/coverage."""

    scan_run_id: str = Field(..., description="Scan run identifier")
    total_findings: int = Field(..., description="Total scan findings in this run")
    findings_with_violations: int = Field(
        ..., description="Number of distinct findings that have at least one control violation"
    )
    by_framework: List[FrameworkCoverage] = Field(
        default_factory=list, description="Per-framework coverage breakdown"
    )
