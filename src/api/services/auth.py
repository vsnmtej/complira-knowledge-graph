"""
Authentication service.

Wraps user and organization repositories for auth endpoints.
"""

from typing import Optional, Dict, Any
from api.repositories.user import UserRepository
from api.repositories.organization import OrganizationRepository
from api.core.security import hash_password, verify_password, create_access_token, create_refresh_token, verify_jwt_token
import structlog

logger = structlog.get_logger()


class AuthService:
    """Service layer for authentication operations."""

    def __init__(self, db):
        self.user_repo = UserRepository(db)
        self.org_repo = OrganizationRepository(db)

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Look up user by email."""
        return self.user_repo.get_user_by_email(email)

    def create_user_and_organization(
        self,
        email: str,
        password: str,
        name: str,
        organization_name: str,
        organization_domain: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new user and organization.

        Returns:
            Dict with 'user' and 'org' keys.
        """
        org = self.org_repo.create_organization(
            name=organization_name,
            domain=organization_domain,
            tier="free",
            frameworks=[],
        )

        password_hash = hash_password(password)

        user = self.user_repo.create_user(
            email=email,
            password_hash=password_hash,
            name=name,
            organization_id=org["_key"],
            role="owner",
        )

        return {"user": user, "org": org}

    def authenticate(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Authenticate user with email/password.

        Returns:
            User dict if valid, None otherwise.
        """
        user = self.user_repo.get_user_by_email(email)
        if not user:
            return None

        if not verify_password(password, user["password_hash"]):
            return None

        return user

    def get_user_organization(self, user_key: str) -> Optional[Dict[str, Any]]:
        """Get the organization a user belongs to."""
        return self.user_repo.get_user_organization(user_key)

    def verify_email(self, token: str) -> bool:
        """Verify user email with token."""
        return self.user_repo.verify_email(token)

    def create_password_reset_token(self, email: str) -> Optional[str]:
        """Create password reset token for email."""
        return self.user_repo.create_password_reset_token(email)

    def reset_password(self, token: str, new_password: str) -> bool:
        """Reset password using token."""
        new_password_hash = hash_password(new_password)
        return self.user_repo.reset_password(token, new_password_hash)

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        return self.user_repo.get_user_by_id(user_id)

    def create_tokens(self, user: Dict[str, Any], org: Dict[str, Any]) -> Dict[str, str]:
        """Create access and refresh tokens for a user."""
        access_token = create_access_token(
            user_id=user["_key"],
            email=user["email"],
            org_id=org["_key"],
            role=org.get("role", "member"),
        )
        refresh_token = create_refresh_token(user_id=user["_key"])
        return {"access_token": access_token, "refresh_token": refresh_token}

    def verify_refresh_token(self, token: str) -> Dict[str, Any]:
        """Verify and decode a refresh token."""
        return verify_jwt_token(token)
