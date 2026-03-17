"""
User repository (Phase 5 - Web UI Authentication).

Handles CRUD operations for users collection and user_belongs_to_org edges.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from arango.database import StandardDatabase
import structlog
import secrets

logger = structlog.get_logger()


class UserRepository:
    """
    Repository for user-related database operations.

    Handles:
    - User creation and lookup
    - Email verification
    - Password reset tokens
    - User-organization relationships
    """

    def __init__(self, db: StandardDatabase):
        """
        Initialize user repository.

        Args:
            db: ArangoDB database instance
        """
        self.db = db
        self.users = db.collection("users")
        self.user_belongs_to_org = db.collection("user_belongs_to_org")

    def create_user(
        self,
        email: str,
        password_hash: str,
        name: str,
        organization_id: str,
        role: str = "owner"
    ) -> dict:
        """
        Create new user with email verification token.

        Args:
            email: User's email address
            password_hash: Bcrypt password hash
            name: User's full name
            organization_id: Organization _key
            role: User role (owner, admin, member)

        Returns:
            dict: Created user document

        Example:
            {
                "_key": "abc123",
                "email": "john@example.com",
                "name": "John Doe",
                "password_hash": "$2b$12$...",
                "email_verified": false,
                "email_verification_token": "abc123def456",
                "email_verification_expires_at": "2024-01-15T12:00:00Z",
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T10:00:00Z"
            }
        """
        now = datetime.utcnow().isoformat() + "Z"
        verification_token = secrets.token_urlsafe(32)
        verification_expires = (datetime.utcnow() + timedelta(hours=24)).isoformat() + "Z"

        user_doc = {
            "email": email.lower(),  # Normalize email
            "password_hash": password_hash,
            "name": name,
            "email_verified": False,
            "email_verification_token": verification_token,
            "email_verification_expires_at": verification_expires,
            "password_reset_token": None,
            "password_reset_expires_at": None,
            "created_at": now,
            "updated_at": now,
        }

        # Insert user
        result = self.users.insert(user_doc, return_new=True)
        user = result["new"]

        # Create user-organization relationship edge
        edge_doc = {
            "_from": f"users/{user['_key']}",
            "_to": f"organizations/{organization_id}",
            "role": role,
            "created_at": now,
        }
        self.user_belongs_to_org.insert(edge_doc)

        logger.info(
            "User created",
            user_id=user["_key"],
            email=email,
            org_id=organization_id,
            role=role
        )

        return user

    def get_user_by_email(self, email: str) -> Optional[dict]:
        """
        Get user by email address.

        Args:
            email: User's email address

        Returns:
            dict: User document or None if not found
        """
        query = """
        FOR user IN users
            FILTER user.email == @email
            LIMIT 1
            RETURN user
        """

        cursor = self.db.aql.execute(query, bind_vars={"email": email.lower()})
        users = list(cursor)

        return users[0] if users else None

    def get_user_by_id(self, user_id: str) -> Optional[dict]:
        """
        Get user by ID (_key).

        Args:
            user_id: User document _key

        Returns:
            dict: User document or None if not found
        """
        try:
            return self.users.get(user_id)
        except Exception as e:
            logger.error("User lookup error", user_id=user_id, error=str(e))
            return None

    def get_user_organization(self, user_id: str) -> Optional[dict]:
        """
        Get user's organization via user_belongs_to_org edge.

        Args:
            user_id: User document _key

        Returns:
            dict: Organization document with user's role, or None

        Example:
            {
                "_key": "org_xyz",
                "name": "Acme Corp",
                "slug": "acme-corp",
                "tier": "professional",
                "frameworks": ["FDA_524B"],
                "role": "owner"  # User's role in this org
            }
        """
        query = """
        FOR user IN users
            FILTER user._key == @user_id
            FOR org IN 1..1 OUTBOUND user user_belongs_to_org
                LET edge = (
                    FOR e IN user_belongs_to_org
                        FILTER e._from == user._id AND e._to == org._id
                        RETURN e
                )[0]
                RETURN MERGE(org, {role: edge.role})
        """

        cursor = self.db.aql.execute(query, bind_vars={"user_id": user_id})
        orgs = list(cursor)

        return orgs[0] if orgs else None

    def verify_email(self, token: str) -> bool:
        """
        Verify user email with token.

        Args:
            token: Email verification token

        Returns:
            bool: True if verification succeeded, False otherwise
        """
        now = datetime.utcnow().isoformat() + "Z"

        query = """
        FOR user IN users
            FILTER user.email_verification_token == @token
            FILTER user.email_verification_expires_at > @now
            UPDATE user WITH {
                email_verified: true,
                email_verification_token: null,
                email_verification_expires_at: null,
                updated_at: @now
            } IN users
            RETURN NEW
        """

        cursor = self.db.aql.execute(query, bind_vars={"token": token, "now": now})
        results = list(cursor)

        if results:
            logger.info("Email verified", user_id=results[0]["_key"], email=results[0]["email"])
            return True
        else:
            logger.warning("Email verification failed (invalid or expired token)", token=token[:8] + "...")
            return False

    def create_password_reset_token(self, email: str) -> Optional[str]:
        """
        Create password reset token for user.

        Args:
            email: User's email address

        Returns:
            str: Reset token if user found, None otherwise
        """
        user = self.get_user_by_email(email)
        if not user:
            return None

        reset_token = secrets.token_urlsafe(32)
        reset_expires = (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z"
        now = datetime.utcnow().isoformat() + "Z"

        self.users.update(
            user["_key"],
            {
                "password_reset_token": reset_token,
                "password_reset_expires_at": reset_expires,
                "updated_at": now,
            }
        )

        logger.info("Password reset token created", user_id=user["_key"], email=email)

        return reset_token

    def reset_password(self, token: str, new_password_hash: str) -> bool:
        """
        Reset user password with token.

        Args:
            token: Password reset token
            new_password_hash: New bcrypt password hash

        Returns:
            bool: True if reset succeeded, False otherwise
        """
        now = datetime.utcnow().isoformat() + "Z"

        query = """
        FOR user IN users
            FILTER user.password_reset_token == @token
            FILTER user.password_reset_expires_at > @now
            UPDATE user WITH {
                password_hash: @password_hash,
                password_reset_token: null,
                password_reset_expires_at: null,
                updated_at: @now
            } IN users
            RETURN NEW
        """

        cursor = self.db.aql.execute(
            query,
            bind_vars={
                "token": token,
                "password_hash": new_password_hash,
                "now": now
            }
        )
        results = list(cursor)

        if results:
            logger.info("Password reset", user_id=results[0]["_key"], email=results[0]["email"])
            return True
        else:
            logger.warning("Password reset failed (invalid or expired token)", token=token[:8] + "...")
            return False

    def update_user(self, user_id: str, updates: Dict[str, Any]) -> Optional[dict]:
        """
        Update user fields.

        Args:
            user_id: User document _key
            updates: Fields to update

        Returns:
            dict: Updated user document or None
        """
        now = datetime.utcnow().isoformat() + "Z"
        updates["updated_at"] = now

        try:
            result = self.users.update(user_id, updates, return_new=True)
            logger.info("User updated", user_id=user_id, fields=list(updates.keys()))
            return result["new"]
        except Exception as e:
            logger.error("User update error", user_id=user_id, error=str(e))
            return None

    def delete_user(self, user_id: str) -> bool:
        """
        Delete user and associated edges.

        Args:
            user_id: User document _key

        Returns:
            bool: True if deletion succeeded
        """
        try:
            # Delete user-organization edges
            query = """
            FOR edge IN user_belongs_to_org
                FILTER edge._from == @user_id
                REMOVE edge IN user_belongs_to_org
            """
            self.db.aql.execute(query, bind_vars={"user_id": f"users/{user_id}"})

            # Delete user document
            self.users.delete(user_id)

            logger.info("User deleted", user_id=user_id)
            return True
        except Exception as e:
            logger.error("User deletion error", user_id=user_id, error=str(e))
            return False
