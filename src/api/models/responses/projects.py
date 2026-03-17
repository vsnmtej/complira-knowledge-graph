"""
Project response models.
"""

from pydantic import BaseModel, Field
from typing import Optional, List


class ProjectResponse(BaseModel):
    """Response model for project details."""

    project_id: str = Field(..., description="Unique project identifier")
    name: str = Field(..., description="Project name")
    description: Optional[str] = Field(None, description="Project description")
    tags: List[str] = Field(default_factory=list, description="Project tags")
    repository_count: int = Field(0, description="Number of repositories in this project")
    created_at: str = Field(..., description="Creation timestamp (ISO 8601)")
    updated_at: str = Field(..., description="Last update timestamp (ISO 8601)")
    last_scan_at: Optional[str] = Field(None, description="Most recent scan timestamp across all repositories")
    active: bool = Field(True, description="Active status (false = soft deleted)")


class CreateProjectResponse(BaseModel):
    """Response when creating a new project."""

    project_id: str = Field(..., description="Unique project identifier")
    name: str = Field(..., description="Project name")
    description: Optional[str] = Field(None, description="Project description")
    tags: List[str] = Field(default_factory=list, description="Project tags")
    created_at: str = Field(..., description="Creation timestamp (ISO 8601)")
    repository_count: int = Field(0, description="Number of repositories (always 0 at creation)")


class ListProjectsResponse(BaseModel):
    """Response for listing projects."""

    projects: List[ProjectResponse] = Field(..., description="List of projects")
    total: int = Field(..., description="Total number of projects")


class ProjectSummaryResponse(BaseModel):
    """Response for project-level aggregation/summary."""

    project_id: str = Field(..., description="Project identifier")
    project_name: str = Field(..., description="Project name")
    repository_count: int = Field(..., description="Number of repositories in project")
    total_scans: int = Field(..., description="Total scan sessions across all repositories")
    findings: dict = Field(..., description="Aggregated findings breakdown")
    top_vulnerabilities: List[dict] = Field(default_factory=list, description="Top CVEs across project")
    compliance_status: Optional[dict] = Field(None, description="Compliance status summary")
    repositories: List[dict] = Field(default_factory=list, description="Repository breakdown with findings")


class DeleteProjectResponse(BaseModel):
    """Response when deleting (soft delete) a project."""

    project_id: str = Field(..., description="Deleted project identifier")
    name: str = Field(..., description="Project name")
    deleted_at: str = Field(..., description="Deletion timestamp (ISO 8601)")
    message: str = Field(..., description="Deletion confirmation message")
