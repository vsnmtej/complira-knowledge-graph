"""
Repository response models.
"""

from pydantic import BaseModel, Field
from typing import Optional, List


class RepositoryResponse(BaseModel):
    """Response model for repository details."""

    repository_id: str = Field(..., description="Unique repository identifier")
    project_id: Optional[str] = Field(None, description="Parent project identifier (null if unassigned)")
    project_name: Optional[str] = Field(None, description="Parent project name (null if unassigned)")
    name: str = Field(..., description="Repository name")
    description: Optional[str] = Field(None, description="Repository description")
    repository_url: Optional[str] = Field(None, description="Git repository URL")
    default_branch: Optional[str] = Field(None, description="Default branch name (e.g., 'main', 'master')")
    tags: List[str] = Field(default_factory=list, description="Repository tags")
    scan_count: int = Field(0, description="Number of scan sessions for this repository")
    created_at: str = Field(..., description="Creation timestamp (ISO 8601)")
    updated_at: str = Field(..., description="Last update timestamp (ISO 8601)")
    last_scan_at: Optional[str] = Field(None, description="Most recent scan timestamp")
    active: bool = Field(True, description="Active status (false = soft deleted)")


class CreateRepositoryResponse(BaseModel):
    """Response when creating a new repository."""

    repository_id: str = Field(..., description="Unique repository identifier")
    project_id: Optional[str] = Field(None, description="Parent project identifier")
    name: str = Field(..., description="Repository name")
    description: Optional[str] = Field(None, description="Repository description")
    repository_url: Optional[str] = Field(None, description="Git repository URL")
    default_branch: Optional[str] = Field(None, description="Default branch name")
    tags: List[str] = Field(default_factory=list, description="Repository tags")
    created_at: str = Field(..., description="Creation timestamp (ISO 8601)")
    scan_count: int = Field(0, description="Number of scans (always 0 at creation)")


class ListRepositoriesResponse(BaseModel):
    """Response for listing repositories."""

    repositories: List[RepositoryResponse] = Field(..., description="List of repositories")
    total: int = Field(..., description="Total number of repositories")


class RepositorySummaryResponse(BaseModel):
    """Response for repository-level aggregation/summary."""

    repository_id: str = Field(..., description="Repository identifier")
    repository_name: str = Field(..., description="Repository name")
    project_id: Optional[str] = Field(None, description="Parent project identifier")
    project_name: Optional[str] = Field(None, description="Parent project name")
    scan_count: int = Field(..., description="Total scan sessions")
    first_scan: Optional[str] = Field(None, description="First scan timestamp (ISO 8601)")
    last_scan: Optional[str] = Field(None, description="Most recent scan timestamp (ISO 8601)")
    current_findings: dict = Field(..., description="Current findings from latest scan")
    trends: dict = Field(..., description="Vulnerability trends (new vs resolved over time)")
    top_vulnerabilities: List[dict] = Field(default_factory=list, description="Top CVEs in this repository")


class DeleteRepositoryResponse(BaseModel):
    """Response when deleting (soft delete) a repository."""

    repository_id: str = Field(..., description="Deleted repository identifier")
    name: str = Field(..., description="Repository name")
    deleted_at: str = Field(..., description="Deletion timestamp (ISO 8601)")
    message: str = Field(..., description="Deletion confirmation message")
