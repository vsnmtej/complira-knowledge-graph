"""
Scan session and finding models for vulnerability ingestion.

Represents scan data from SAST/DAST/SCA tools like Snyk, Trivy, Semgrep.
"""

from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, Dict, Any


class ScanSession(BaseModel):
    """
    Scan session metadata.

    Collection: scan_sessions (customer database)

    Represents a single scan execution from CI/CD pipeline.
    Stored in customer-specific database for data isolation.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        ser_json_by_alias=True,  # Serialize using aliases (_key instead of key)
    )

    # ArangoDB document key - use 'key' field with '_key' alias
    key: Optional[str] = Field(
        None,
        alias="_key",
        serialization_alias="_key",  # Serialize as _key in model_dump()
        description="Session identifier (auto-generated if not provided)",
    )
    customer_id: str = Field(
        ...,
        description="Customer identifier",
        min_length=1,
    )
    tool_name: str = Field(
        ...,
        description="Scanner tool name (e.g., 'Snyk', 'Trivy', 'Semgrep')",
        min_length=1,
    )
    tool_version: str = Field(
        ...,
        description="Scanner tool version",
        min_length=1,
    )
    scan_timestamp: str = Field(
        ...,
        description="Scan execution timestamp (ISO 8601)",
    )
    scan_type: str = Field(
        ...,
        description="Scan format type (sarif, cyclonedx)",
    )
    status: str = Field(
        default="processing",
        description="Scan processing status (pending, processing, completed, failed)",
    )
    findings_count: int = Field(
        default=0,
        description="Number of findings in this scan",
        ge=0,
    )
    components_count: int = Field(
        default=0,
        description="Number of SBOM components in this scan",
        ge=0,
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional scan metadata",
    )
    project_id: Optional[str] = Field(
        None,
        description="Project identifier (optional, for multi-tenant hierarchy)",
    )
    repository_id: Optional[str] = Field(
        None,
        description="Repository identifier (optional, for multi-tenant hierarchy)",
    )
    created_at: Optional[str] = Field(
        None,
        description="Session creation timestamp (ISO 8601)",
    )
    updated_at: Optional[str] = Field(
        None,
        description="Session last update timestamp (ISO 8601)",
    )

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validate status is one of allowed values."""
        allowed_statuses = ["pending", "processing", "completed", "failed"]
        if v not in allowed_statuses:
            raise ValueError(f"status must be one of {allowed_statuses}")
        return v

    @field_validator("scan_type")
    @classmethod
    def validate_scan_type(cls, v: str) -> str:
        """Validate scan_type is supported."""
        supported_types = ["sarif", "cyclonedx"]
        if v not in supported_types:
            raise ValueError(f"scan_type must be one of {supported_types}")
        return v

    @property
    def _key(self) -> Optional[str]:
        """ArangoDB document key (for backward compatibility)."""
        return self.key

    @property
    def id(self) -> Optional[str]:
        """Alias for key (session ID)."""
        return self.key

    @property
    def session_id(self) -> Optional[str]:
        """Alias for key (session ID)."""
        return self.key


class ScanFinding(BaseModel):
    """
    Individual scan finding (vulnerability or issue).

    Collection: scan_findings (customer database)

    Represents a single vulnerability or issue discovered by scanner.
    Stored in customer-specific database for data isolation.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        ser_json_by_alias=True,  # Serialize using aliases (_key instead of key)
    )

    # ArangoDB document key - use 'key' field with '_key' alias
    key: Optional[str] = Field(
        None,
        alias="_key",
        serialization_alias="_key",  # Serialize as _key in model_dump()
        description="Finding identifier (auto-generated if not provided)",
    )
    customer_id: str = Field(
        ...,
        description="Customer identifier",
        min_length=1,
    )
    scan_session_id: str = Field(
        ...,
        description="Scan session _key this finding belongs to",
        min_length=1,
    )
    cve_id: Optional[str] = Field(
        None,
        description="CVE identifier (e.g., 'CVE-2021-44228') if applicable",
    )
    severity: str = Field(
        ...,
        description="Normalized severity level (CRITICAL, HIGH, MEDIUM, LOW, INFO, UNKNOWN)",
    )
    description: str = Field(
        ...,
        description="Finding description",
        min_length=1,
    )
    location: str = Field(
        ...,
        description="Finding location (file:line or component@version)",
        min_length=1,
    )
    tool_name: str = Field(
        ...,
        description="Scanner tool that reported this finding",
        min_length=1,
    )
    raw_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Original finding data from scanner",
    )
    created_at: Optional[str] = Field(
        None,
        description="Finding creation timestamp (ISO 8601)",
    )

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        """Validate severity is normalized."""
        allowed_severities = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "UNKNOWN"]
        if v.upper() not in allowed_severities:
            raise ValueError(f"severity must be one of {allowed_severities}")
        return v.upper()

    @field_validator("cve_id")
    @classmethod
    def validate_cve_id(cls, v: Optional[str]) -> Optional[str]:
        """Validate CVE ID format if provided."""
        if v and not v.upper().startswith("CVE-"):
            raise ValueError("cve_id must start with 'CVE-' if provided")
        return v.upper() if v else None

    @property
    def _key(self) -> Optional[str]:
        """ArangoDB document key (for backward compatibility)."""
        return self.key

    @property
    def id(self) -> Optional[str]:
        """Alias for key (finding ID)."""
        return self.key

    @property
    def finding_id(self) -> Optional[str]:
        """Alias for key (finding ID)."""
        return self.key
