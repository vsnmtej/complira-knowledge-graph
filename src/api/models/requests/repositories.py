"""
Request models for repository management endpoints.
"""

from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List


class CreateRepositoryRequest(BaseModel):
    """Request to create a new repository."""

    name: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Repository name",
        examples=["backend-api", "mobile-app"]
    )
    project_id: Optional[str] = Field(
        None,
        description="Parent project identifier (null = unassigned repository)",
        examples=["proj_abc123"]
    )
    description: Optional[str] = Field(
        None,
        max_length=500,
        description="Optional repository description"
    )
    repository_url: Optional[str] = Field(
        None,
        description="Git repository URL (e.g., https://github.com/org/repo)",
        examples=["https://github.com/myorg/backend-api"]
    )
    default_branch: Optional[str] = Field(
        None,
        max_length=100,
        description="Default branch name",
        examples=["main", "master", "develop"]
    )
    tags: Optional[List[str]] = Field(
        default_factory=list,
        description="Tags for categorization and filtering",
        examples=[["backend", "production", "critical"]]
    )


class UpdateRepositoryRequest(BaseModel):
    """Request to update an existing repository."""

    name: Optional[str] = Field(
        None,
        min_length=3,
        max_length=100,
        description="Updated repository name"
    )
    project_id: Optional[str] = Field(
        None,
        description="Updated parent project identifier (set to null to unassign)"
    )
    description: Optional[str] = Field(
        None,
        max_length=500,
        description="Updated repository description"
    )
    repository_url: Optional[str] = Field(
        None,
        description="Updated Git repository URL"
    )
    default_branch: Optional[str] = Field(
        None,
        max_length=100,
        description="Updated default branch name"
    )
    tags: Optional[List[str]] = Field(
        None,
        description="Updated tags"
    )
    active: Optional[bool] = Field(
        None,
        description="Active status (false = soft delete)"
    )
