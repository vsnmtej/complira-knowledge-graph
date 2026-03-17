"""
API Token management endpoints (Phase 5 - Web UI).

Endpoints for creating, managing, rotating, and revoking API tokens.

Routes:
    GET    /v1/tokens              - List all tokens for organization
    POST   /v1/tokens              - Create new API token
    GET    /v1/tokens/{token_id}   - Get token details
    PATCH  /v1/tokens/{token_id}   - Update token (name, scopes)
    POST   /v1/tokens/{token_id}/rotate  - Rotate token secret
    POST   /v1/tokens/{token_id}/revoke  - Revoke token
    DELETE /v1/tokens/{token_id}   - Delete token (permanent)
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Annotated

from api.core.database import get_database
from api.core.security import get_current_user
from api.services.token import TokenService
from api.models.tokens import (
    CreateTokenRequest,
    UpdateTokenRequest,
    RotateTokenRequest,
    CreateTokenResponse,
    RotateTokenResponse,
    RevokeTokenResponse,
    ListTokensResponse,
    APIToken,
)
from api.models.auth import UserProfile
import structlog

logger = structlog.get_logger()

router = APIRouter(prefix="/tokens", tags=["API Tokens"])


@router.post("", response_model=CreateTokenResponse, status_code=status.HTTP_201_CREATED)
async def create_token(
    request: CreateTokenRequest,
    db=Depends(get_database),
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Create new API token.

    **Authorization**: Requires authenticated user with admin or owner role.

    **Request Body**:
    ```json
    {
        "name": "CI/CD Pipeline Token",
        "description": "GitHub Actions for main repo",
        "scopes": ["scan:write", "reference:read"],
        "rate_limit": 1000,
        "expires_in_days": 365
    }
    ```

    **Response** (201 CREATED):
    ```json
    {
        "success": true,
        "message": "Token created successfully. Save this token - you won't see it again!",
        "token": "complira_tk_abc123xyz789...",
        "token_id": "token_abc123",
        "token_prefix": "complira_tk_abc123",
        "expires_at": "2025-01-15T10:00:00Z"
    }
    ```

    **Security**:
    - Token secret shown ONLY once (not retrievable later)
    - Hashed using bcrypt before storage
    - User must save token immediately

    **Rate Limits**:
    - Max 100 tokens per organization
    - Token creation rate limited to 10/hour per user
    """
    # Authorization check (only admin/owner can create tokens)
    if current_user["role"] not in ["owner", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization owners and admins can create API tokens"
        )

    # Create token service
    token_service = TokenService(db)

    # Check token limit (100 per org)
    existing_tokens = token_service.list_tokens(
        organization_id=current_user["org_id"],
        include_revoked=False
    )
    if existing_tokens["total"] >= 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization has reached maximum token limit (100 active tokens)"
        )

    # Create token
    try:
        token_doc = token_service.create_token(
            organization_id=current_user["org_id"],
            created_by_user_id=current_user["sub"],
            name=request.name,
            scopes=request.scopes,
            description=request.description,
            rate_limit=request.rate_limit or 1000,
            expires_in_days=request.expires_in_days or 365
        )

        logger.info(
            "token_created_via_api",
            token_id=token_doc["_key"],
            organization_id=current_user["org_id"],
            user_id=current_user["sub"],
            scopes=request.scopes
        )

        return CreateTokenResponse(
            success=True,
            message="Token created successfully. Save this token - you won't see it again!",
            token=token_doc["token_secret"],
            token_id=token_doc["_key"],
            token_prefix=token_doc["token_prefix"],
            expires_at=token_doc["expires_at"]
        )

    except Exception as e:
        logger.error("token_creation_failed", error=str(e), user_id=current_user["sub"])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create token: {str(e)}"
        )


@router.get("", response_model=ListTokensResponse)
async def list_tokens(
    include_revoked: Annotated[bool, Query(description="Include revoked tokens")] = False,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    db=Depends(get_database),
    current_user: UserProfile = Depends(get_current_user)
):
    """
    List all API tokens for the current organization.

    **Authorization**: Requires authenticated user (any role).

    **Query Parameters**:
    - `include_revoked` (bool): Include revoked tokens (default: false)
    - `page` (int): Page number (default: 1)
    - `page_size` (int): Items per page (1-100, default: 20)

    **Response** (200 OK):
    ```json
    {
        "tokens": [
            {
                "id": "token_abc123",
                "name": "CI/CD Pipeline Token",
                "token_prefix": "complira_tk_abc123",
                "scopes": ["scan:write", "reference:read"],
                "last_used": "2024-01-15T14:28:00Z",
                "expires_at": "2025-01-15T10:00:00Z",
                "revoked": false
            }
        ],
        "total": 3,
        "page": 1,
        "page_size": 20
    }
    ```
    """
    token_service = TokenService(db)

    result = token_service.list_tokens(
        organization_id=current_user["org_id"],
        include_revoked=include_revoked,
        page=page,
        page_size=page_size
    )

    # Convert to response model
    tokens = [
        APIToken(
            id=t["_key"],
            organization_id=t["organization_id"],
            created_by_user_id=t["created_by_user_id"],
            name=t["name"],
            description=t.get("description"),
            token_prefix=t["token_prefix"],
            scopes=t["scopes"],
            rate_limit=t["rate_limit"],
            created_at=t["created_at"],
            expires_at=t["expires_at"],
            last_used=t.get("last_used"),
            revoked=t["revoked"],
            revoked_at=t.get("revoked_at"),
            revoked_by_user_id=t.get("revoked_by_user_id")
        )
        for t in result["tokens"]
    ]

    return ListTokensResponse(
        tokens=tokens,
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"]
    )


@router.get("/{token_id}", response_model=APIToken)
async def get_token(
    token_id: str,
    db=Depends(get_database),
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Get API token details by ID.

    **Authorization**: Requires authenticated user (any role).

    **Path Parameters**:
    - `token_id` (str): Token ID

    **Response** (200 OK):
    ```json
    {
        "id": "token_abc123",
        "organization_id": "org_xyz789",
        "name": "CI/CD Pipeline Token",
        "token_prefix": "complira_tk_abc123",
        "scopes": ["scan:write"],
        "created_at": "2024-01-15T10:00:00Z",
        "expires_at": "2025-01-15T10:00:00Z",
        "revoked": false
    }
    ```

    **Note**: Token secret is NEVER returned after creation.
    """
    token_service = TokenService(db)

    token = token_service.get_token_by_id(token_id, current_user["org_id"])

    if not token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Token {token_id} not found"
        )

    return APIToken(
        id=token["_key"],
        organization_id=token["organization_id"],
        created_by_user_id=token["created_by_user_id"],
        name=token["name"],
        description=token.get("description"),
        token_prefix=token["token_prefix"],
        scopes=token["scopes"],
        rate_limit=token["rate_limit"],
        created_at=token["created_at"],
        expires_at=token["expires_at"],
        last_used=token.get("last_used"),
        revoked=token["revoked"],
        revoked_at=token.get("revoked_at"),
        revoked_by_user_id=token.get("revoked_by_user_id")
    )


@router.patch("/{token_id}", response_model=APIToken)
async def update_token(
    token_id: str,
    request: UpdateTokenRequest,
    db=Depends(get_database),
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Update API token metadata (name, description, scopes).

    **Authorization**: Requires authenticated user with admin or owner role.

    **Path Parameters**:
    - `token_id` (str): Token ID

    **Request Body**:
    ```json
    {
        "name": "Updated Token Name",
        "description": "Updated description",
        "scopes": ["scan:write", "reference:read", "vex:generate"]
    }
    ```

    **Response** (200 OK): Updated token object

    **Note**: Cannot update token secret (use rotate endpoint instead).
    """
    # Authorization check
    if current_user["role"] not in ["owner", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization owners and admins can update API tokens"
        )

    token_service = TokenService(db)

    updated = token_service.update_token(
        token_id=token_id,
        organization_id=current_user["org_id"],
        user_id=current_user["sub"],
        name=request.name,
        description=request.description,
        scopes=request.scopes
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Token {token_id} not found or update failed"
        )

    return APIToken(
        id=updated["_key"],
        organization_id=updated["organization_id"],
        created_by_user_id=updated["created_by_user_id"],
        name=updated["name"],
        description=updated.get("description"),
        token_prefix=updated["token_prefix"],
        scopes=updated["scopes"],
        rate_limit=updated["rate_limit"],
        created_at=updated["created_at"],
        expires_at=updated["expires_at"],
        last_used=updated.get("last_used"),
        revoked=updated["revoked"],
        revoked_at=updated.get("revoked_at"),
        revoked_by_user_id=updated.get("revoked_by_user_id")
    )


@router.post("/{token_id}/rotate", response_model=RotateTokenResponse)
async def rotate_token(
    token_id: str,
    request: RotateTokenRequest = RotateTokenRequest(),
    db=Depends(get_database),
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Rotate API token secret (old token valid during grace period).

    **Authorization**: Requires authenticated user with admin or owner role.

    **Path Parameters**:
    - `token_id` (str): Token ID

    **Request Body**:
    ```json
    {
        "grace_period_hours": 24
    }
    ```

    **Response** (200 OK):
    ```json
    {
        "success": true,
        "message": "Token rotated successfully. Old token expires in 24 hours.",
        "new_token": "complira_tk_xyz789abc456...",
        "token_id": "token_abc123",
        "token_prefix": "complira_tk_xyz789",
        "old_token_expires_at": "2024-01-16T10:00:00Z",
        "new_token_expires_at": "2025-01-15T10:00:00Z"
    }
    ```

    **Process**:
    1. New token generated
    2. Old token remains valid for grace_period_hours (default: 24h)
    3. Update integrations with new token within grace period
    4. After grace period, old token becomes invalid

    **Security**:
    - New token secret shown ONLY once
    - Recommended for 90-day token rotation policies
    """
    # Authorization check
    if current_user["role"] not in ["owner", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization owners and admins can rotate API tokens"
        )

    token_service = TokenService(db)

    try:
        rotated = token_service.rotate_token(
            token_id=token_id,
            organization_id=current_user["org_id"],
            user_id=current_user["sub"],
            grace_period_hours=request.grace_period_hours
        )

        logger.info(
            "token_rotated_via_api",
            token_id=token_id,
            user_id=current_user["sub"],
            grace_period_hours=request.grace_period_hours
        )

        return RotateTokenResponse(
            success=True,
            message=f"Token rotated successfully. Old token expires in {request.grace_period_hours} hours.",
            new_token=rotated["token_secret"],
            token_id=rotated["_key"],
            token_prefix=rotated["token_prefix"],
            old_token_expires_at=rotated["rotation_grace_until"],
            new_token_expires_at=rotated["expires_at"]
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error("token_rotation_failed", error=str(e), token_id=token_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rotate token: {str(e)}"
        )


@router.post("/{token_id}/revoke", response_model=RevokeTokenResponse)
async def revoke_token(
    token_id: str,
    db=Depends(get_database),
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Revoke API token (immediate, irreversible).

    **Authorization**: Requires authenticated user with admin or owner role.

    **Path Parameters**:
    - `token_id` (str): Token ID

    **Response** (200 OK):
    ```json
    {
        "success": true,
        "message": "Token revoked successfully",
        "token_id": "token_abc123",
        "revoked_at": "2024-01-15T15:00:00Z"
    }
    ```

    **Process**:
    - Token immediately invalid (no grace period)
    - All API requests with this token will fail
    - Cannot be undone (create new token instead)

    **Use Cases**:
    - Compromised token
    - Decommissioned service
    - Security incident response
    """
    # Authorization check
    if current_user["role"] not in ["owner", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization owners and admins can revoke API tokens"
        )

    token_service = TokenService(db)

    revoked = token_service.revoke_token(
        token_id=token_id,
        organization_id=current_user["org_id"],
        user_id=current_user["sub"]
    )

    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Token {token_id} not found or revocation failed"
        )

    logger.info(
        "token_revoked_via_api",
        token_id=token_id,
        user_id=current_user["sub"],
        revoked_at=revoked["revoked_at"]
    )

    return RevokeTokenResponse(
        success=True,
        message="Token revoked successfully",
        token_id=revoked["_key"],
        revoked_at=revoked["revoked_at"]
    )


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_token(
    token_id: str,
    db=Depends(get_database),
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Permanently delete API token.

    **Authorization**: Requires authenticated user with owner role only.

    **Path Parameters**:
    - `token_id` (str): Token ID

    **Response** (204 NO CONTENT): Empty response

    **Warning**:
    - This is PERMANENT deletion
    - Prefer revoke_token() for most cases
    - Only owners can delete (not admins)
    - Cannot be undone

    **Use Cases**:
    - Cleanup after security audit
    - Remove obsolete tokens
    - Compliance requirements (data retention)
    """
    # Authorization check (ONLY owners)
    if current_user["role"] != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization owners can permanently delete API tokens"
        )

    token_service = TokenService(db)

    deleted = token_service.delete_token(
        token_id=token_id,
        organization_id=current_user["org_id"],
        user_id=current_user["sub"]
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Token {token_id} not found or deletion failed"
        )

    logger.info(
        "token_deleted_via_api",
        token_id=token_id,
        user_id=current_user["sub"]
    )

    # 204 NO CONTENT (no response body)
