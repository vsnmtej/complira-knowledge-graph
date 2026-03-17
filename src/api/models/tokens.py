"""
API Token management models (Phase 5 - Web UI).

Pydantic models for API token CRUD operations:
- Token creation and management
- Token rotation and revocation
- Scope-based access control
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
from datetime import datetime


# ========== Request Models ==========


class CreateTokenRequest(BaseModel):
    """
    API token creation request.

    Example:
        {
            "name": "CI/CD Pipeline Token",
            "description": "GitHub Actions for main repo",
            "scopes": ["scan:write", "reference:read"],
            "rate_limit": 1000,
            "expires_in_days": 365
        }
    """
    name: str = Field(..., min_length=3, max_length=100, description="Token name (for identification)")
    description: Optional[str] = Field(None, max_length=500, description="Optional description")
    scopes: list[str] = Field(..., min_items=1, description="Token scopes (e.g., 'scan:write', 'reference:read')")
    rate_limit: Optional[int] = Field(1000, ge=100, le=10000, description="Requests per hour limit")
    expires_in_days: Optional[int] = Field(365, ge=1, le=3650, description="Token expiry in days (default: 365, max: 3650/10 years)")

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, v: list[str]) -> list[str]:
        """Validate scopes against allowed values."""
        allowed_scopes = {
            "scan:write",      # Upload SBOM/SARIF
            "scan:read",       # Read scan results
            "reference:read",  # Query reference data (CVEs, NIST, etc.)
            "vex:generate",    # Generate VEX documents
            "admin:all",       # Full admin access (organization owners only)
        }

        for scope in v:
            if scope not in allowed_scopes:
                raise ValueError(f"Invalid scope: {scope}. Allowed: {', '.join(allowed_scopes)}")

        return v


class UpdateTokenRequest(BaseModel):
    """
    API token update request (name, description, scopes).

    Example:
        {
            "name": "Updated Token Name",
            "description": "Updated description",
            "scopes": ["scan:write", "reference:read", "vex:generate"]
        }
    """
    name: Optional[str] = Field(None, min_length=3, max_length=100, description="New token name")
    description: Optional[str] = Field(None, max_length=500, description="New description")
    scopes: Optional[list[str]] = Field(None, min_items=1, description="New scopes")

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        """Validate scopes against allowed values."""
        if v is None:
            return v

        allowed_scopes = {
            "scan:write",
            "scan:read",
            "reference:read",
            "vex:generate",
            "admin:all",
        }

        for scope in v:
            if scope not in allowed_scopes:
                raise ValueError(f"Invalid scope: {scope}. Allowed: {', '.join(allowed_scopes)}")

        return v


class RotateTokenRequest(BaseModel):
    """
    Token rotation request (generates new secret, old valid for 24h).

    Example:
        {
            "grace_period_hours": 24
        }
    """
    grace_period_hours: int = Field(24, ge=1, le=168, description="Hours old token remains valid (1-168h/7 days)")


# ========== Response Models ==========


class APIToken(BaseModel):
    """
    API token details (secret NOT included after creation).

    Example:
        {
            "id": "token_abc123",
            "organization_id": "org_xyz789",
            "created_by_user_id": "users/user123",
            "name": "CI/CD Pipeline Token",
            "description": "GitHub Actions for main repo",
            "token_prefix": "complira_tk_abc123",
            "scopes": ["scan:write", "reference:read"],
            "rate_limit": 1000,
            "created_at": "2024-01-15T10:00:00Z",
            "expires_at": "2025-01-15T10:00:00Z",
            "last_used": "2024-01-15T14:28:00Z",
            "revoked": false
        }
    """
    id: str = Field(..., description="Token document key")
    organization_id: str = Field(..., description="Organization ID")
    created_by_user_id: str = Field(..., description="User who created the token")
    name: str = Field(..., description="Token name")
    description: Optional[str] = Field(None, description="Token description")
    token_prefix: str = Field(..., description="Token prefix (e.g., 'complira_tk_abc123...')")
    scopes: list[str] = Field(..., description="Token scopes")
    rate_limit: int = Field(..., description="Requests per hour")
    created_at: str = Field(..., description="Creation timestamp (ISO 8601)")
    expires_at: str = Field(..., description="Expiration timestamp (ISO 8601)")
    last_used: Optional[str] = Field(None, description="Last use timestamp (ISO 8601)")
    revoked: bool = Field(..., description="Whether token is revoked")
    revoked_at: Optional[str] = Field(None, description="Revocation timestamp (ISO 8601)")
    revoked_by_user_id: Optional[str] = Field(None, description="User who revoked the token")


class CreateTokenResponse(BaseModel):
    """
    Token creation response (includes full secret - SHOWN ONCE).

    Example:
        {
            "success": true,
            "message": "Token created successfully. Save this token - you won't see it again!",
            "token": "complira_tk_abc123xyz789defghijklmnopqrstuvwxyz0123456789ABCDEFGHIJK",
            "token_id": "token_abc123",
            "token_prefix": "complira_tk_abc123",
            "expires_at": "2025-01-15T10:00:00Z"
        }
    """
    success: bool = Field(..., description="Whether creation succeeded")
    message: str = Field(..., description="Human-readable message")
    token: str = Field(..., description="Full token secret (ONLY shown once)")
    token_id: str = Field(..., description="Token document key")
    token_prefix: str = Field(..., description="Token prefix for UI identification")
    expires_at: str = Field(..., description="Expiration timestamp (ISO 8601)")


class RotateTokenResponse(BaseModel):
    """
    Token rotation response (new secret + grace period info).

    Example:
        {
            "success": true,
            "message": "Token rotated successfully. Old token expires in 24 hours.",
            "new_token": "complira_tk_xyz789abc456newtoken...",
            "token_id": "token_abc123",
            "token_prefix": "complira_tk_xyz789",
            "old_token_expires_at": "2024-01-16T10:00:00Z",
            "new_token_expires_at": "2025-01-15T10:00:00Z"
        }
    """
    success: bool = Field(..., description="Whether rotation succeeded")
    message: str = Field(..., description="Human-readable message")
    new_token: str = Field(..., description="New token secret (ONLY shown once)")
    token_id: str = Field(..., description="Token document key")
    token_prefix: str = Field(..., description="New token prefix")
    old_token_expires_at: str = Field(..., description="When old token becomes invalid (ISO 8601)")
    new_token_expires_at: str = Field(..., description="When new token expires (ISO 8601)")


class RevokeTokenResponse(BaseModel):
    """
    Token revocation response.

    Example:
        {
            "success": true,
            "message": "Token revoked successfully",
            "token_id": "token_abc123",
            "revoked_at": "2024-01-15T15:00:00Z"
        }
    """
    success: bool = Field(..., description="Whether revocation succeeded")
    message: str = Field(..., description="Human-readable message")
    token_id: str = Field(..., description="Token document key")
    revoked_at: str = Field(..., description="Revocation timestamp (ISO 8601)")


class ListTokensResponse(BaseModel):
    """
    List tokens response (paginated).

    Example:
        {
            "tokens": [
                {
                    "id": "token_abc123",
                    "name": "CI/CD Pipeline Token",
                    "token_prefix": "complira_tk_abc123",
                    "scopes": ["scan:write"],
                    "last_used": "2024-01-15T14:28:00Z",
                    "expires_at": "2025-01-15T10:00:00Z",
                    "revoked": false
                }
            ],
            "total": 3,
            "page": 1,
            "page_size": 20
        }
    """
    tokens: list[APIToken] = Field(..., description="List of tokens")
    total: int = Field(..., description="Total tokens (across all pages)")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Items per page")
