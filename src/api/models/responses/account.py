"""
Response models for account management endpoints.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class APIKeyResponse(BaseModel):
    """Response model for API key details."""

    key_id: str = Field(..., description="Unique identifier for this API key")
    name: str = Field(..., description="Human-readable name")
    description: Optional[str] = Field(None, description="Description of key usage")

    # Security: Never return the actual API key after creation
    key_prefix: str = Field(..., description="First 8 characters of the key (for identification)")

    created_at: str = Field(..., description="ISO 8601 timestamp when key was created")
    expires_at: Optional[str] = Field(None, description="ISO 8601 timestamp when key expires")
    last_used_at: Optional[str] = Field(None, description="ISO 8601 timestamp of last use")

    revoked: bool = Field(False, description="Whether this key has been revoked")
    revoked_at: Optional[str] = Field(None, description="ISO 8601 timestamp when revoked")
    revoked_reason: Optional[str] = Field(None, description="Reason for revocation")


class CreateAPIKeyResponse(BaseModel):
    """Response when creating a new API key."""

    key_id: str = Field(..., description="Unique identifier for this API key")
    name: str = Field(..., description="Human-readable name")

    # IMPORTANT: API key is only returned once at creation time
    api_key: str = Field(
        ...,
        description="The actual API key - SAVE THIS NOW! It will not be shown again."
    )

    created_at: str = Field(..., description="ISO 8601 timestamp")
    expires_at: Optional[str] = Field(None, description="ISO 8601 timestamp when key expires")

    warning: str = Field(
        default="⚠️ Save this API key securely. You will not be able to retrieve it again.",
        description="Security warning"
    )


class ListAPIKeysResponse(BaseModel):
    """Response for listing API keys."""

    keys: List[APIKeyResponse] = Field(..., description="List of API keys for this customer")
    total: int = Field(..., description="Total number of keys (including revoked)")
    active: int = Field(..., description="Number of active (non-revoked) keys")


class RevokeAPIKeyResponse(BaseModel):
    """Response when revoking an API key."""

    key_id: str = Field(..., description="Revoked key ID")
    revoked: bool = Field(True, description="Confirmation that key was revoked")
    revoked_at: str = Field(..., description="ISO 8601 timestamp when revoked")
    message: str = Field(
        default="API key has been revoked and can no longer be used",
        description="Confirmation message"
    )
