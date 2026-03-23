"""
API authentication and authorization.

Provides:
- API key validation (legacy + multi-tenant)
- JWT authentication (web UI users)
- Password hashing and verification
- Dual authentication support (JWT priority, API key fallback)
- Customer identification and scoping
- FastAPI dependencies for authentication
"""

from typing import Optional
from datetime import datetime, timedelta
from fastapi import HTTPException, Header, Depends
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from jose import jwt, JWTError
import bcrypt
import structlog

from api.core.config import get_cloud_settings
from api.core.database import get_database
from complira_graph.models import CustomerProfile

# Type alias for consistency with endpoint imports
Customer = CustomerProfile

logger = structlog.get_logger()


# FastAPI security schemes
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login", auto_error=False)


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

    Checks both customer_profiles and customer_api_keys collections.

    Args:
        api_key: Plain text API key from request header

    Returns:
        CustomerProfile: Validated customer profile model if valid API key, None otherwise
    """
    if not api_key:
        return None

    try:
        db = get_database()

        # First, check customer_api_keys collection (newer multi-key system)
        if db.has_collection("customer_api_keys"):
            query_api_keys = """
            FOR key IN customer_api_keys
                FILTER key.revoked != true
                RETURN key
            """

            cursor = db.aql.execute(query_api_keys)
            api_keys = list(cursor)

            for key_doc in api_keys:
                api_key_hash = key_doc.get('api_key_hash')
                if api_key_hash and verify_api_key(api_key, api_key_hash):
                    # Check if key has expired
                    if key_doc.get('expires_at'):
                        from datetime import datetime
                        expires_at = datetime.fromisoformat(key_doc['expires_at'].replace('Z', '+00:00'))
                        if datetime.now(expires_at.tzinfo) > expires_at:
                            logger.warning(
                                "API key expired",
                                key_id=key_doc.get('key_id'),
                                expired_at=key_doc.get('expires_at'),
                            )
                            continue

                    # Valid API key found - fetch customer profile
                    customer_id = key_doc.get('customer_id')
                    query_profile = """
                    FOR profile IN customer_profiles
                        FILTER profile.id == @customer_id OR profile._key == @customer_id
                        RETURN profile
                    """

                    profile_cursor = db.aql.execute(query_profile, bind_vars={"customer_id": customer_id})
                    profiles = list(profile_cursor)

                    if profiles:
                        customer_profile = CustomerProfile(**profiles[0])

                        logger.debug(
                            "API key validated (multi-key)",
                            customer_id=customer_profile._key,
                            customer_name=customer_profile.name,
                            key_id=key_doc.get('key_id'),
                        )

                        return customer_profile

                    # Fallback: customer_id may be an org _key (new JWT-created API keys)
                    if db.has_collection("organizations"):
                        org_cursor = db.aql.execute(
                            "FOR org IN organizations FILTER org._key == @id RETURN org",
                            bind_vars={"id": customer_id},
                        )
                        orgs = list(org_cursor)
                        if orgs:
                            org = orgs[0]
                            customer_profile = CustomerProfile(
                                _key=org["_key"],
                                name=org["name"],
                                tier=org.get("tier", "free"),
                                frameworks=org.get("frameworks", []),
                                database_name=f"complira_tenant_{org['_key']}",
                            )
                            logger.debug(
                                "API key validated (multi-key, org-based)",
                                customer_id=customer_profile._key,
                                customer_name=customer_profile.name,
                                key_id=key_doc.get('key_id'),
                            )
                            return customer_profile

        # Fallback: Check customer_profiles collection (legacy single-key system)
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
                    "API key validated (legacy)",
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
    token: Optional[str] = Depends(oauth2_scheme),
):
    """
    FastAPI dependency for dual authentication (JWT + API Key).

    Supports both:
    1. JWT authentication (web UI users) - checks Authorization header first
    2. API key authentication (programmatic clients) - falls back to X-API-Key header

    This ensures backward compatibility with existing API key clients while
    supporting new JWT-based web UI authentication.

    Args:
        api_key: API key from X-API-Key header (injected by FastAPI)
        token: JWT token from Authorization header (injected by FastAPI)

    Returns:
        CustomerProfile: Validated customer profile model

    Raises:
        HTTPException: 401 if both authentication methods fail or are missing

    Usage:
        @app.get("/v1/scan/list")
        async def list_scans(
            customer: CustomerProfile = Depends(get_current_customer)
        ):
            # customer._key or customer.id (both work via property)
            # customer.database_name is the customer's isolated database
            ...
    """
    # Strategy 1: Try JWT authentication first (web UI users)
    if token:
        try:
            payload = verify_jwt_token(token)

            # Verify token type
            if payload.get("type") == "access":
                org_id = payload.get("org_id")

                # Fetch organization and return as CustomerProfile for compatibility
                db = get_database()
                query = """
                FOR org IN organizations
                    FILTER org._key == @org_id
                    RETURN org
                """
                cursor = db.aql.execute(query, bind_vars={"org_id": org_id})
                orgs = list(cursor)

                if orgs:
                    org = orgs[0]
                    # Map organization to CustomerProfile for backward compatibility
                    customer = CustomerProfile(
                        _key=org["_key"],
                        name=org["name"],
                        tier=org.get("tier", "free"),
                        frameworks=org.get("frameworks", []),
                        database_name=f"complira_tenant_{org['_key']}"
                    )

                    logger.info(
                        "Request authenticated via JWT",
                        user_id=payload.get("sub"),
                        email=payload.get("email"),
                        org_id=org_id,
                        org_name=customer.name,
                    )

                    return customer
        except HTTPException:
            # JWT verification failed, fall through to API key
            pass
        except Exception as e:
            logger.warning("JWT authentication error, falling back to API key", error=str(e))

    # Strategy 2: Fall back to API key authentication (programmatic clients)
    if api_key:
        customer = await get_customer_from_api_key(api_key)

        if customer is not None:
            logger.info(
                "Request authenticated via API key",
                customer_id=customer._key,
                customer_name=customer.name,
            )
            return customer
        else:
            logger.warning("Invalid API key attempted")
            raise HTTPException(
                status_code=401,
                detail="Invalid API key",
            )

    # No authentication provided
    logger.warning("No authentication provided (missing both JWT and API key)")
    raise HTTPException(
        status_code=401,
        detail="Authentication required. Provide either 'Authorization: Bearer <token>' or 'X-API-Key' header.",
    )


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


# ========== JWT Authentication (Phase 5 - Web UI) ==========


def create_access_token(
    user_id: str,
    email: str,
    org_id: str,
    role: str = "member",
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create JWT access token for web UI authentication.

    Args:
        user_id: User document _key from users collection
        email: User email address
        org_id: Organization document _key from organizations collection
        role: User role (owner, admin, member)
        expires_delta: Optional custom expiration time (default: 15 minutes)

    Returns:
        str: Encoded JWT token

    Example payload:
        {
            "sub": "users/abc123",
            "email": "user@example.com",
            "org_id": "org_xyz789",
            "role": "admin",
            "exp": 1234567890,
            "iat": 1234567800,
            "type": "access"
        }
    """
    settings = get_cloud_settings()

    if expires_delta is None:
        expires_delta = timedelta(minutes=15)

    now = datetime.utcnow()
    expire = now + expires_delta

    payload = {
        "sub": user_id,  # Subject (user ID)
        "email": email,
        "org_id": org_id,
        "role": role,
        "exp": expire,  # Expiration time
        "iat": now,  # Issued at
        "type": "access"
    }

    encoded_jwt = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )

    return encoded_jwt


def create_refresh_token(user_id: str, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create JWT refresh token for extending sessions.

    Args:
        user_id: User document _key from users collection
        expires_delta: Optional custom expiration time (default: 7 days)

    Returns:
        str: Encoded JWT refresh token

    Example payload:
        {
            "sub": "users/abc123",
            "exp": 1234567890,
            "iat": 1234567800,
            "type": "refresh"
        }
    """
    settings = get_cloud_settings()

    if expires_delta is None:
        expires_delta = timedelta(days=7)

    now = datetime.utcnow()
    expire = now + expires_delta

    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": now,
        "type": "refresh"
    }

    encoded_jwt = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )

    return encoded_jwt


def verify_jwt_token(token: str) -> dict:
    """
    Verify and decode JWT token.

    Args:
        token: JWT token string

    Returns:
        dict: Decoded payload if valid

    Raises:
        HTTPException: 401 if token is invalid, expired, or malformed
    """
    settings = get_cloud_settings()

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError as e:
        logger.warning("JWT verification failed", error=str(e))
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )


def hash_password(password: str) -> str:
    """
    Hash user password using bcrypt.

    Args:
        password: Plain text password

    Returns:
        str: Bcrypt hash of password
    """
    settings = get_cloud_settings()
    salt = bcrypt.gensalt(rounds=12)  # User passwords use 12 rounds (more secure than API keys)
    return bcrypt.hashpw(password.encode(), salt).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify password against bcrypt hash.

    Args:
        plain_password: Plain text password from login request
        hashed_password: Bcrypt hash from database

    Returns:
        bool: True if password matches hash
    """
    try:
        return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())
    except Exception as e:
        logger.error(
            "Password verification error",
            error=str(e),
            error_type=type(e).__name__,
        )
        return False


async def get_current_user(token: Optional[str] = Depends(oauth2_scheme)):
    """
    FastAPI dependency for JWT authentication (web UI users).

    Uses OAuth2PasswordBearer to extract and validate JWT tokens.

    Args:
        token: JWT token from Authorization header (injected by FastAPI)

    Returns:
        dict: User information from JWT payload

    Raises:
        HTTPException: 401 if token is missing or invalid

    Usage:
        @app.get("/v1/user/profile")
        async def get_profile(
            user: dict = Depends(get_current_user)
        ):
            user_id = user["sub"]
            email = user["email"]
            org_id = user["org_id"]
            role = user["role"]
            ...
    """
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Missing authorization. Provide 'Authorization: Bearer <token>' header"
        )

    payload = verify_jwt_token(token)

    # Verify token type
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=401,
            detail="Invalid token type. Use access token, not refresh token"
        )

    logger.info(
        "JWT authenticated",
        user_id=payload.get("sub"),
        email=payload.get("email"),
        org_id=payload.get("org_id")
    )

    return payload
