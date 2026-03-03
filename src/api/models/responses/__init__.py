"""
Response models.

Standard API response format with generic APIResponse[T] wrapper.
"""

from typing import TypeVar, Generic, Optional
from pydantic import BaseModel, Field


T = TypeVar('T')


class ResponseMetadata(BaseModel):
    """
    Standard response metadata.

    Included in all API responses.
    """
    cache_hit: bool = Field(False, description="Whether response was served from cache")
    execution_time_ms: Optional[float] = Field(None, description="Execution time in milliseconds")
    api_version: str = Field("v1", description="API version")


class APIResponse(BaseModel, Generic[T]):
    """
    Generic response wrapper (DRY).

    Used by all endpoints for consistent response format.

    Example:
        @app.get("/v1/scan/{session_id}", response_model=APIResponse[ScanSessionResponse])
        def get_scan(session_id: str):
            data = get_scan_data(session_id)
            return APIResponse(
                success=True,
                data=data,
                metadata=ResponseMetadata(cache_hit=False)
            )
    """
    success: bool = Field(..., description="Whether request was successful")
    data: Optional[T] = Field(None, description="Response data (type varies by endpoint)")
    error: Optional[str] = Field(None, description="Error message if success=false")
    metadata: ResponseMetadata = Field(default_factory=ResponseMetadata, description="Response metadata")
