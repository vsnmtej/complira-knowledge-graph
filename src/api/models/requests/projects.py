"""
Request models for project management endpoints.
"""

from pydantic import BaseModel, Field
from typing import Optional, List


class CreateProjectRequest(BaseModel):
    """Request to create a new project."""

    name: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Human-readable project name",
        examples=["Backend Services", "Mobile Apps"]
    )
    description: Optional[str] = Field(
        None,
        max_length=500,
        description="Optional project description"
    )
    tags: Optional[List[str]] = Field(
        default_factory=list,
        description="Tags for categorization and filtering",
        examples=[["backend", "api", "production"]]
    )


class UpdateProjectRequest(BaseModel):
    """Request to update an existing project."""

    name: Optional[str] = Field(
        None,
        min_length=3,
        max_length=100,
        description="Updated project name"
    )
    description: Optional[str] = Field(
        None,
        max_length=500,
        description="Updated project description"
    )
    tags: Optional[List[str]] = Field(
        None,
        description="Updated tags"
    )
    active: Optional[bool] = Field(
        None,
        description="Active status (false = soft delete)"
    )
