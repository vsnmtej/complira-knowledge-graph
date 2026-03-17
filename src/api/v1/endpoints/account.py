"""
Account management endpoints.

POST /v1/account/api-keys - Create new API key
GET /v1/account/api-keys - List API keys
DELETE /v1/account/api-keys/{key_id} - Revoke API key
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import List
import structlog
import secrets
import string
from datetime import datetime, timedelta

from api.core.security import Customer, get_current_customer, hash_api_key
from api.core.database import get_database
from api.models.requests.account import CreateAPIKeyRequest, RevokeAPIKeyRequest
from api.models.responses.account import (
    CreateAPIKeyResponse,
    ListAPIKeysResponse,
    APIKeyResponse,
    RevokeAPIKeyResponse,
)
from api.models.responses import APIResponse, ResponseMetadata

logger = structlog.get_logger()

router = APIRouter()


def generate_api_key(length: int = 48) -> str:
    """
    Generate a secure random API key.

    Args:
        length: Length of the API key (default 48 characters)

    Returns:
        str: Secure random API key
    """
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def generate_key_id() -> str:
    """Generate a unique key ID."""
    return f"key_{secrets.token_hex(16)}"


@router.post("/api-keys", response_model=APIResponse[CreateAPIKeyResponse])
async def create_api_key(
    request: CreateAPIKeyRequest,
    customer: Customer = Depends(get_current_customer),
):
    """
    POST /v1/account/api-keys

    Create a new API key for the authenticated customer.

    **Important:**
    - The API key is only shown once at creation time
    - Save it securely - you cannot retrieve it later
    - You can create multiple API keys for different use cases

    **Use Cases:**
    - Separate keys for production, staging, development
    - Different keys for different applications
    - Time-limited keys for temporary access

    **Example:**
    ```bash
    curl -X POST https://api.complira.dev/v1/account/api-keys \
      -H "X-API-Key: your_current_api_key" \
      -H "Content-Type: application/json" \
      -d '{
        "name": "Production Server",
        "description": "API key for production deployment",
        "expires_days": 90
      }'
    ```
    """
    import time
    start_time = time.time()

    try:
        db = get_database()

        # Generate new API key
        api_key = generate_api_key()
        key_id = generate_key_id()

        # Hash the API key for storage
        api_key_hash = hash_api_key(api_key)

        # Calculate expiration if requested
        created_at = datetime.utcnow()
        expires_at = None
        if request.expires_days:
            expires_at = created_at + timedelta(days=request.expires_days)

        # Create API key document
        api_key_doc = {
            "_key": key_id,
            "key_id": key_id,
            "customer_id": customer.id,
            "name": request.name,
            "description": request.description,
            "api_key_hash": api_key_hash,
            "key_prefix": api_key[:8],  # Store first 8 chars for identification
            "created_at": created_at.isoformat() + "Z",
            "expires_at": expires_at.isoformat() + "Z" if expires_at else None,
            "last_used_at": None,
            "revoked": False,
            "revoked_at": None,
            "revoked_reason": None,
        }

        # Ensure api_keys collection exists
        if not db.has_collection("customer_api_keys"):
            db.create_collection("customer_api_keys", edge=False)

        # Insert API key
        collection = db.collection("customer_api_keys")
        collection.insert(api_key_doc)

        logger.info(
            "API key created",
            customer_id=customer.id,
            key_id=key_id,
            key_name=request.name,
        )

        execution_time_ms = (time.time() - start_time) * 1000

        return APIResponse(
            success=True,
            data=CreateAPIKeyResponse(
                key_id=key_id,
                name=request.name,
                api_key=api_key,  # Only time this is returned!
                created_at=created_at.isoformat() + "Z",
                expires_at=expires_at.isoformat() + "Z" if expires_at else None,
            ),
            metadata=ResponseMetadata(
                cache_hit=False,
                execution_time_ms=execution_time_ms,
            ),
        )

    except Exception as e:
        logger.error(
            "API key creation failed",
            customer_id=customer.id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error during API key creation"
        )


@router.get("/api-keys", response_model=APIResponse[ListAPIKeysResponse])
async def list_api_keys(
    customer: Customer = Depends(get_current_customer),
):
    """
    GET /v1/account/api-keys

    List all API keys for the authenticated customer.

    **Returns:**
    - Active API keys (non-revoked)
    - Revoked API keys (for audit purposes)
    - Never returns the actual API key values

    **Example:**
    ```bash
    curl https://api.complira.dev/v1/account/api-keys \
      -H "X-API-Key: your_api_key"
    ```
    """
    import time
    start_time = time.time()

    try:
        db = get_database()

        # Query all API keys for this customer
        query = """
        FOR key IN customer_api_keys
            FILTER key.customer_id == @customer_id
            SORT key.created_at DESC
            RETURN key
        """

        cursor = db.aql.execute(query, bind_vars={"customer_id": customer.id})
        keys = list(cursor)

        # Convert to response models
        api_keys = [
            APIKeyResponse(
                key_id=key["key_id"],
                name=key["name"],
                description=key.get("description"),
                key_prefix=key["key_prefix"],
                created_at=key["created_at"],
                expires_at=key.get("expires_at"),
                last_used_at=key.get("last_used_at"),
                revoked=key.get("revoked", False),
                revoked_at=key.get("revoked_at"),
                revoked_reason=key.get("revoked_reason"),
            )
            for key in keys
        ]

        active_count = sum(1 for k in keys if not k.get("revoked", False))

        execution_time_ms = (time.time() - start_time) * 1000

        return APIResponse(
            success=True,
            data=ListAPIKeysResponse(
                keys=api_keys,
                total=len(api_keys),
                active=active_count,
            ),
            metadata=ResponseMetadata(
                cache_hit=False,
                execution_time_ms=execution_time_ms,
            ),
        )

    except Exception as e:
        logger.error(
            "API key listing failed",
            customer_id=customer.id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/api-keys/{key_id}", response_model=APIResponse[RevokeAPIKeyResponse])
async def revoke_api_key(
    key_id: str,
    request: RevokeAPIKeyRequest = None,
    customer: Customer = Depends(get_current_customer),
):
    """
    DELETE /v1/account/api-keys/{key_id}

    Revoke an API key immediately.

    **Important:**
    - Revoked keys can no longer be used for authentication
    - Revocation is permanent and cannot be undone
    - You can only revoke keys belonging to your customer account

    **Example:**
    ```bash
    curl -X DELETE https://api.complira.dev/v1/account/api-keys/key_abc123 \
      -H "X-API-Key: your_api_key" \
      -H "Content-Type: application/json" \
      -d '{"reason": "Key compromised"}'
    ```
    """
    import time
    start_time = time.time()

    try:
        db = get_database()
        collection = db.collection("customer_api_keys")

        # Verify key exists and belongs to this customer
        query = """
        FOR key IN customer_api_keys
            FILTER key.key_id == @key_id
            FILTER key.customer_id == @customer_id
            RETURN key
        """

        cursor = db.aql.execute(
            query,
            bind_vars={"key_id": key_id, "customer_id": customer.id}
        )
        keys = list(cursor)

        if not keys:
            raise HTTPException(
                status_code=404,
                detail=f"API key not found: {key_id}"
            )

        key = keys[0]

        # Check if already revoked
        if key.get("revoked", False):
            raise HTTPException(
                status_code=400,
                detail=f"API key already revoked: {key_id}"
            )

        # Revoke the key
        revoked_at = datetime.utcnow()
        collection.update(
            {
                "_key": key["_key"],
                "revoked": True,
                "revoked_at": revoked_at.isoformat() + "Z",
                "revoked_reason": request.reason if request else None,
            }
        )

        logger.warning(
            "API key revoked",
            customer_id=customer.id,
            key_id=key_id,
            key_name=key["name"],
            reason=request.reason if request else None,
        )

        execution_time_ms = (time.time() - start_time) * 1000

        return APIResponse(
            success=True,
            data=RevokeAPIKeyResponse(
                key_id=key_id,
                revoked=True,
                revoked_at=revoked_at.isoformat() + "Z",
            ),
            metadata=ResponseMetadata(
                cache_hit=False,
                execution_time_ms=execution_time_ms,
            ),
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            "API key revocation failed",
            customer_id=customer.id,
            key_id=key_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error during API key revocation"
        )
