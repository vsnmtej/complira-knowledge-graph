"""
Supply chain intelligence response models.
"""

from pydantic import BaseModel, Field
from typing import Optional, List


class ComponentDetailResponse(BaseModel):
    """Response model for component detail endpoint."""

    purl: str = Field(..., description="Package URL (PURL)")
    name: str = Field(..., description="Component name")
    version: Optional[str] = Field(None, description="Component version")
    type: Optional[str] = Field(None, description="Component type (e.g. library, framework)")
    projects: List[str] = Field(default_factory=list, description="Project IDs using this component (tenant-scoped)")
    dependencies: List[str] = Field(default_factory=list, description="PURLs of direct dependencies (OUTBOUND 1-hop)")
    dependents: List[str] = Field(default_factory=list, description="PURLs of direct dependents (INBOUND 1-hop)")
    vulnerabilities: List[str] = Field(default_factory=list, description="CVE IDs associated with this component")


class AffectedProjectItem(BaseModel):
    """Single affected project entry."""

    project_id: str = Field(..., description="Project identifier")
    component_purl: str = Field(..., description="PURL of the vulnerable component")
    cve_id: str = Field(..., description="CVE identifier")


class AffectedProjectsResponse(BaseModel):
    """Response model for affected-projects endpoint."""

    items: List[AffectedProjectItem] = Field(default_factory=list, description="Affected project/component/CVE tuples")
    total: int = Field(..., description="Total number of affected project entries")


class DependencyPathResponse(BaseModel):
    """Response model for dependency-path endpoint."""

    found: bool = Field(..., description="Whether a dependency path was found")
    path: List[str] = Field(default_factory=list, description="Ordered list of PURLs from source to target")
    path_length: int = Field(..., description="Number of components in the path (0 if not found)")


class TopComponent(BaseModel):
    """Component entry in the top-depended-on list."""

    purl: str = Field(..., description="Package URL (PURL)")
    dependent_count: int = Field(..., description="Number of other components that depend on this component")


class RiskSummaryResponse(BaseModel):
    """Response model for supply chain risk summary endpoint."""

    project_id: str = Field(..., description="Project identifier")
    total_components: int = Field(..., description="Total components used by this project")
    vulnerable_components: int = Field(..., description="Components with at least one known CVE")
    critical_count: int = Field(..., description="Count of CRITICAL severity vulnerabilities across all components")
    high_count: int = Field(..., description="Count of HIGH severity vulnerabilities across all components")
    top_depended_on: List[TopComponent] = Field(
        default_factory=list,
        description="Up to 5 most-depended-on components by INBOUND depends_on edge count",
    )
