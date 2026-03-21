"""
Customer profile models for multi-tenant API.

Represents customer/organization entities with API access credentials.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Literal
from datetime import datetime


class CustomerProfile(BaseModel):
    """
    Customer profile for multi-tenant API access.

    Stored in customer_profiles collection in reference database.
    Each customer gets an isolated database for their scan data.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        ser_json_by_alias=True,  # Serialize using aliases (_key instead of key)
        json_schema_extra={
            "example": {
                "_key": "acme_corp",
                "name": "Acme Corporation",
                "email": "security@acme.com",
                "api_key_hash": "$2b$12$...",
                "database_name": "complira_customer_acme_corp",
                "tier": "professional",
                "rate_limit": 600,
                "created_at": "2026-03-01T00:00:00Z",
                "updated_at": "2026-03-05T12:00:00Z",
                "active": True,
                "metadata": {
                    "industry": "healthcare",
                    "company_size": "500-1000"
                }
            }
        }
    )

    # ArangoDB document key - use 'key' field with '_key' alias
    key: str = Field(
        ...,
        alias="_key",
        serialization_alias="_key",  # Serialize as _key in model_dump()
        description="Customer ID (unique identifier)",
    )
    name: str = Field(..., description="Organization name")
    email: Optional[str] = Field(None, description="Primary contact email")
    api_key_hash: Optional[str] = Field(None, description="Bcrypt hash of API key (optional for JWT-only users)")

    # Database routing
    database_name: str = Field(..., description="Customer's isolated database name (e.g., complira_customer_acme_corp)")

    # Subscription info
    tier: Literal["free", "pro", "enterprise"] = Field(default="free", description="Subscription tier (free, pro, enterprise)")
    rate_limit: int = Field(default=60, description="Requests per minute")

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Account creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")
    active: bool = Field(default=True, description="Account active status")

    # Additional metadata
    metadata: dict = Field(default_factory=dict, description="Additional customer metadata")

    # Optional fields (for feature parity with organizations)
    frameworks: list[str] = Field(default_factory=list, description="Selected compliance frameworks")

    @property
    def _key(self) -> str:
        """ArangoDB document key (for backward compatibility)."""
        return self.key

    @property
    def id(self) -> str:
        """Alias for key (customer ID)."""
        return self.key

    @property
    def customer_id(self) -> str:
        """Alias for key (customer ID)."""
        return self.key
