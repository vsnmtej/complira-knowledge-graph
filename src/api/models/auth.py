"""
Authentication API models (Phase 5 - Web UI).

Pydantic models for authentication requests and responses:
- User signup and login
- Email verification
- Password reset
- Token refresh
"""

from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, Literal
from datetime import datetime
import re


# ========== Request Models ==========


class SignupRequest(BaseModel):
    """
    User signup request.

    Example:
        {
            "name": "John Doe",
            "email": "john@example.com",
            "password": "SecurePass123!",
            "organization_name": "Acme Corp",
            "organization_domain": "acme.com"
        }
    """
    name: str = Field(..., min_length=2, max_length=100, description="User's full name")
    email: EmailStr = Field(..., description="User's email address (will be used for login)")
    password: str = Field(..., min_length=8, max_length=128, description="Password (min 8 chars, must include uppercase, lowercase, number, special char)")
    organization_name: str = Field(..., min_length=2, max_length=100, description="Organization name")
    organization_domain: Optional[str] = Field(None, max_length=100, description="Organization primary domain (optional)")

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """
        Validate password meets security requirements.

        Requirements:
        - Min 8 characters
        - At least one uppercase letter
        - At least one lowercase letter
        - At least one number
        - At least one special character
        """
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")

        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")

        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")

        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number")

        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Password must contain at least one special character")

        return v


class LoginRequest(BaseModel):
    """
    User login request (username/password authentication).

    Example:
        {
            "email": "john@example.com",
            "password": "SecurePass123!"
        }
    """
    email: EmailStr = Field(..., description="User's email address")
    password: str = Field(..., description="User's password")


class EmailVerificationRequest(BaseModel):
    """
    Email verification request.

    Example:
        {
            "token": "abc123def456ghi789"
        }
    """
    token: str = Field(..., min_length=32, max_length=128, description="Email verification token (sent via email)")


class PasswordResetRequest(BaseModel):
    """
    Password reset request (initiate reset via email).

    Example:
        {
            "email": "john@example.com"
        }
    """
    email: EmailStr = Field(..., description="User's email address")


class PasswordResetConfirmRequest(BaseModel):
    """
    Password reset confirmation (complete reset with new password).

    Example:
        {
            "token": "abc123def456ghi789",
            "new_password": "NewSecurePass456!"
        }
    """
    token: str = Field(..., min_length=32, max_length=128, description="Password reset token (sent via email)")
    new_password: str = Field(..., min_length=8, max_length=128, description="New password")

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Validate new password meets security requirements."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")

        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")

        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")

        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number")

        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Password must contain at least one special character")

        return v


class RefreshTokenRequest(BaseModel):
    """
    Refresh token request (exchange refresh token for new access token).

    Example:
        {
            "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
        }
    """
    refresh_token: str = Field(..., description="Refresh token (obtained from login)")


# ========== Response Models ==========


class UserProfile(BaseModel):
    """
    User profile information (returned after authentication).

    Example:
        {
            "id": "users/abc123",
            "email": "john@example.com",
            "name": "John Doe",
            "email_verified": true,
            "organization_id": "org_xyz789",
            "organization_name": "Acme Corp",
            "role": "owner",
            "tier": "professional",
            "frameworks": ["FDA_524B", "IEC_62304"],
            "created_at": "2024-01-15T10:30:00Z"
        }
    """
    id: str = Field(..., description="User document key (users/{key})")
    email: str = Field(..., description="User's email address")
    name: str = Field(..., description="User's full name")
    email_verified: bool = Field(..., description="Whether email has been verified")
    organization_id: str = Field(..., description="Organization document key")
    organization_name: str = Field(..., description="Organization name")
    role: Literal["owner", "admin", "member"] = Field(..., description="User role in organization")
    tier: Literal["free", "professional", "enterprise"] = Field(..., description="Organization tier")
    frameworks: list[str] = Field(default_factory=list, description="Active compliance frameworks")
    created_at: str = Field(..., description="User creation timestamp (ISO 8601)")


class LoginResponse(BaseModel):
    """
    Login response with JWT tokens and user profile.

    Example:
        {
            "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "token_type": "bearer",
            "expires_in": 900,
            "user": {
                "id": "users/abc123",
                "email": "john@example.com",
                "name": "John Doe",
                "email_verified": true,
                "organization_id": "org_xyz789",
                "organization_name": "Acme Corp",
                "role": "owner",
                "tier": "professional",
                "frameworks": ["FDA_524B"],
                "created_at": "2024-01-15T10:30:00Z"
            }
        }
    """
    access_token: str = Field(..., description="JWT access token (15-minute expiry)")
    refresh_token: str = Field(..., description="JWT refresh token (7-day expiry)")
    token_type: Literal["bearer"] = Field(default="bearer", description="Token type (always 'bearer')")
    expires_in: int = Field(..., description="Access token expiry in seconds")
    user: UserProfile = Field(..., description="User profile information")


class RefreshTokenResponse(BaseModel):
    """
    Refresh token response (new access token).

    Example:
        {
            "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "token_type": "bearer",
            "expires_in": 900
        }
    """
    access_token: str = Field(..., description="New JWT access token (15-minute expiry)")
    token_type: Literal["bearer"] = Field(default="bearer", description="Token type (always 'bearer')")
    expires_in: int = Field(..., description="Access token expiry in seconds")


class EmailVerificationResponse(BaseModel):
    """
    Email verification response.

    Example:
        {
            "success": true,
            "message": "Email verified successfully"
        }
    """
    success: bool = Field(..., description="Whether verification succeeded")
    message: str = Field(..., description="Human-readable message")


class PasswordResetResponse(BaseModel):
    """
    Password reset initiation response.

    Example:
        {
            "success": true,
            "message": "Password reset email sent"
        }
    """
    success: bool = Field(..., description="Whether reset email was sent")
    message: str = Field(..., description="Human-readable message")


class SignupResponse(BaseModel):
    """
    Signup response (user created, verification email sent).

    Example:
        {
            "success": true,
            "message": "Account created. Please check your email to verify.",
            "user_id": "users/abc123",
            "email": "john@example.com"
        }
    """
    success: bool = Field(..., description="Whether signup succeeded")
    message: str = Field(..., description="Human-readable message")
    user_id: str = Field(..., description="Created user document key")
    email: str = Field(..., description="User's email address")
