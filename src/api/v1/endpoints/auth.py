"""
Authentication endpoints (Phase 5 - Web UI).

Provides:
- POST /v1/auth/signup - User registration
- POST /v1/auth/login - User authentication
- POST /v1/auth/verify-email - Email verification
- POST /v1/auth/forgot-password - Password reset initiation
- POST /v1/auth/reset-password - Password reset confirmation
- POST /v1/auth/refresh - Token refresh
- GET /v1/auth/me - Get current user profile
"""

from fastapi import APIRouter, HTTPException, Depends
from api.models.auth import (
    SignupRequest,
    SignupResponse,
    LoginRequest,
    LoginResponse,
    EmailVerificationRequest,
    EmailVerificationResponse,
    PasswordResetRequest,
    PasswordResetResponse,
    PasswordResetConfirmRequest,
    RefreshTokenRequest,
    RefreshTokenResponse,
    UserProfile,
)
from api.services.auth import AuthService
from api.core.security import (
    get_current_user,
)
from api.core.database import get_database
from api.core.config import get_cloud_settings
import structlog

logger = structlog.get_logger()
router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/signup", response_model=SignupResponse, status_code=201)
async def signup(request: SignupRequest):
    """
    Register new user and organization.

    Creates:
    1. New organization
    2. New user (as owner)
    3. User-organization relationship edge
    4. Email verification token

    Returns:
        SignupResponse: Success message with user ID

    Raises:
        HTTPException: 400 if email already exists
    """
    db = get_database()
    auth_service = AuthService(db)

    # Check if email already exists
    existing_user = auth_service.get_user_by_email(request.email)
    if existing_user:
        logger.warning("Signup attempt with existing email", email=request.email)
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    try:
        # Create organization and user
        result = auth_service.create_user_and_organization(
            email=request.email,
            password=request.password,
            name=request.name,
            organization_name=request.organization_name,
            organization_domain=request.organization_domain,
        )
        user = result["user"]
        org = result["org"]

        # TODO: Send verification email (Phase 5.1 - Email service)
        # await email_service.send_verification_email(
        #     email=user["email"],
        #     name=user["name"],
        #     token=user["email_verification_token"]
        # )

        logger.info(
            "User signup successful",
            user_id=user["_key"],
            email=request.email,
            org_id=org["_key"]
        )

        return SignupResponse(
            success=True,
            message="Account created successfully. Please check your email to verify your account.",
            user_id=f"users/{user['_key']}",
            email=user["email"]
        )

    except Exception as e:
        logger.error("Signup error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to create account. Please try again."
        )


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    Authenticate user with email/password.

    Returns:
        LoginResponse: JWT tokens and user profile

    Raises:
        HTTPException: 401 if credentials are invalid
    """
    db = get_database()
    settings = get_cloud_settings()
    auth_service = AuthService(db)

    # Authenticate user
    user = auth_service.authenticate(request.email, request.password)
    if not user:
        logger.warning("Login attempt failed", email=request.email)
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    # Get user's organization
    org = auth_service.get_user_organization(user["_key"])
    if not org:
        logger.error("User has no organization", user_id=user["_key"])
        raise HTTPException(
            status_code=500,
            detail="Account configuration error. Please contact support."
        )

    # Create JWT tokens
    tokens = auth_service.create_tokens(user, org)
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]

    # Build user profile
    user_profile = UserProfile(
        id=f"users/{user['_key']}",
        email=user["email"],
        name=user["name"],
        email_verified=user.get("email_verified", False),
        organization_id=org["_key"],
        organization_name=org["name"],
        role=org.get("role", "member"),
        tier=org.get("tier", "free"),
        frameworks=org.get("frameworks", []),
        created_at=user["created_at"]
    )

    logger.info(
        "Login successful",
        user_id=user["_key"],
        email=user["email"],
        org_id=org["_key"]
    )

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # Convert to seconds
        user=user_profile
    )


@router.post("/verify-email", response_model=EmailVerificationResponse)
async def verify_email(request: EmailVerificationRequest):
    """
    Verify user email with token.

    Returns:
        EmailVerificationResponse: Success message

    Raises:
        HTTPException: 400 if token is invalid or expired
    """
    db = get_database()
    auth_service = AuthService(db)

    success = auth_service.verify_email(request.token)

    if success:
        return EmailVerificationResponse(
            success=True,
            message="Email verified successfully. You can now log in."
        )
    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired verification token"
        )


@router.post("/forgot-password", response_model=PasswordResetResponse)
async def forgot_password(request: PasswordResetRequest):
    """
    Initiate password reset (sends email with token).

    Returns:
        PasswordResetResponse: Success message (always returns success to prevent email enumeration)
    """
    db = get_database()
    auth_service = AuthService(db)

    # Always return success to prevent email enumeration attacks
    token = auth_service.create_password_reset_token(request.email)

    if token:
        # TODO: Send password reset email (Phase 5.1 - Email service)
        # await email_service.send_password_reset_email(
        #     email=request.email,
        #     token=token
        # )
        logger.info("Password reset requested", email=request.email)
    else:
        logger.warning("Password reset requested for non-existent email", email=request.email)

    # Always return success (security best practice)
    return PasswordResetResponse(
        success=True,
        message="If an account exists with this email, a password reset link has been sent."
    )


@router.post("/reset-password", response_model=EmailVerificationResponse)
async def reset_password(request: PasswordResetConfirmRequest):
    """
    Reset password with token.

    Returns:
        EmailVerificationResponse: Success message

    Raises:
        HTTPException: 400 if token is invalid or expired
    """
    db = get_database()
    auth_service = AuthService(db)

    # Reset password
    success = auth_service.reset_password(request.token, request.new_password)

    if success:
        return EmailVerificationResponse(
            success=True,
            message="Password reset successfully. You can now log in with your new password."
        )
    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired reset token"
        )


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_token(request: RefreshTokenRequest):
    """
    Refresh access token using refresh token.

    Returns:
        RefreshTokenResponse: New access token

    Raises:
        HTTPException: 401 if refresh token is invalid or expired
    """
    db = get_database()
    settings = get_cloud_settings()
    auth_service = AuthService(db)

    try:
        # Verify refresh token
        payload = auth_service.verify_refresh_token(request.refresh_token)

        # Check token type
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=401,
                detail="Invalid token type. Use refresh token."
            )

        user_id = payload.get("sub")

        # Get user
        user = auth_service.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=401,
                detail="User not found"
            )

        # Get organization
        org = auth_service.get_user_organization(user_id)
        if not org:
            raise HTTPException(
                status_code=500,
                detail="Account configuration error"
            )

        # Create new access token
        tokens = auth_service.create_tokens(user, org)
        access_token = tokens["access_token"]

        logger.info("Token refreshed", user_id=user_id, email=user["email"])

        return RefreshTokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Token refresh error", error=str(e))
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired refresh token"
        )


@router.get("/me", response_model=UserProfile)
async def get_current_user_profile(user: dict = Depends(get_current_user)):
    """
    Get current authenticated user's profile.

    Requires:
        Authorization: Bearer <access_token>

    Returns:
        UserProfile: User profile information
    """
    db = get_database()
    auth_service = AuthService(db)

    user_id = user.get("sub")

    # Get full user document
    user_doc = auth_service.get_user_by_id(user_id)
    if not user_doc:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    # Get organization
    org = auth_service.get_user_organization(user_id)
    if not org:
        raise HTTPException(
            status_code=500,
            detail="Account configuration error"
        )

    return UserProfile(
        id=f"users/{user_id}",
        email=user_doc["email"],
        name=user_doc["name"],
        email_verified=user_doc.get("email_verified", False),
        organization_id=org["_key"],
        organization_name=org["name"],
        role=org.get("role", "member"),
        tier=org.get("tier", "free"),
        frameworks=org.get("frameworks", []),
        created_at=user_doc["created_at"]
    )
