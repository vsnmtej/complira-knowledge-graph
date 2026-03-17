"""
Request models for account management endpoints.
"""

from pydantic import BaseModel, Field
from typing import Optional


class CreateAPIKeyRequest(BaseModel):
    """Request to create a new API key."""

    name: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Human-readable name for this API key (e.g., 'Production Server', 'CI/CD Pipeline')"
    )

    description: Optional[str] = Field(
        None,
        max_length=500,
        description="Optional description of what this key is used for"
    )

    expires_days: Optional[int] = Field(
        None,
        ge=1,
        le=365,
        description="Optional expiration in days (1-365). If not set, key never expires."
    )


class RevokeAPIKeyRequest(BaseModel):
    """Request to revoke an API key."""

    reason: Optional[str] = Field(
        None,
        max_length=500,
        description="Optional reason for revocation"
    )
