"""
API authentication and authorization.

Provides:
- API key validation
- Customer identification and scoping
- FastAPI dependencies for authentication
"""

from typing import Optional
from fastapi import HTTPException, Header, Depends
from fastapi.security import APIKeyHeader
import bcrypt
import structlog

from api.core.config import get_cloud_settings
from api.core.database import get_database
from complira_graph.models import CustomerProfile

# Type alias for consistency with endpoint imports
Customer = CustomerProfile

logger = structlog.get_logger()


# FastAPI security scheme for API key header
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def hash_api_key(api_key: str) -> str:
    """
    Hash API key using bcrypt.

    Args:
        api_key: Plain text API key

    Returns:
        str: Bcrypt hash of API key
    """
    settings = get_cloud_settings()
    salt = bcrypt.gensalt(rounds=settings.API_KEY_HASH_ROUNDS)
    return bcrypt.hashpw(api_key.encode(), salt).decode()


def verify_api_key(api_key: str, api_key_hash: str) -> bool:
    """
    Verify API key against bcrypt hash.

    Args:
        api_key: Plain text API key from request
        api_key_hash: Bcrypt hash from database

    Returns:
        bool: True if API key matches hash
    """
    try:
        return bcrypt.checkpw(api_key.encode(), api_key_hash.encode())
    except Exception as e:
        logger.error(
            "API key verification error",
            error=str(e),
            error_type=type(e).__name__,
        )
        return False


async def get_customer_from_api_key(api_key: str):
    """
    Retrieve customer from API key using CustomerProfile model.

    Queries customer_profiles collection in reference database.

    Args:
        api_key: Plain text API key from request header

    Returns:
        CustomerProfile: Validated customer profile model if valid API key, None otherwise
    """
    if not api_key:
        return None

    try:
        db = get_database()

        # Query customer_profiles collection in reference database
        query = """
        FOR profile IN customer_profiles
            RETURN profile
        """

        cursor = db.aql.execute(query)
        profiles = list(cursor)

        # Check each profile's API key hash
        for profile_dict in profiles:
            api_key_hash = profile_dict.get('api_key_hash')
            if api_key_hash and verify_api_key(api_key, api_key_hash):
                # Validate and return CustomerProfile model
                customer_profile = CustomerProfile(**profile_dict)

                logger.debug(
                    "API key validated",
                    customer_id=customer_profile._key,
                    customer_name=customer_profile.name,
                )

                return customer_profile

        logger.warning("Invalid API key")
        return None

    except Exception as e:
        logger.error(
            "Customer lookup error",
            error=str(e),
            error_type=type(e).__name__,
        )
        return None


async def get_current_customer(
    api_key: Optional[str] = Depends(api_key_header),
):
    """
    FastAPI dependency for authenticating requests.

    Extracts API key from X-API-Key header and validates against database.

    Args:
        api_key: API key from request header (injected by FastAPI)

    Returns:
        CustomerProfile: Validated customer profile model

    Raises:
        HTTPException: 401 if API key is missing or invalid

    Usage:
        @app.get("/v1/scan/list")
        async def list_scans(
            customer: CustomerProfile = Depends(get_current_customer)
        ):
            # customer._key or customer.id (both work via property)
            # customer.database_name is the customer's isolated database
            ...
    """
    if not api_key:
        logger.warning("Missing API key in request")
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Provide X-API-Key header.",
        )

    customer = await get_customer_from_api_key(api_key)

    if customer is None:
        logger.warning("Invalid API key attempted")
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
        )

    logger.info(
        "Request authenticated",
        customer_id=customer._key,
        customer_name=customer.name,
    )

    return customer


async def validate_api_key_format(api_key: str) -> bool:
    """
    Validate API key format (length, characters).

    Args:
        api_key: API key to validate

    Returns:
        bool: True if format is valid
    """
    settings = get_cloud_settings()

    if len(api_key) < settings.API_KEY_MIN_LENGTH:
        return False

    # Check if alphanumeric (can be extended with more rules)
    if not api_key.isalnum():
        return False

    return True
