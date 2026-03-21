"""
API Token repository (Phase 5 - Web UI Token Management).

Handles CRUD operations for api_tokens collection:
- Token creation with secure secret generation
- Token lookup and validation
- Token rotation with grace period
- Token revocation
- Usage tracking
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from arango.database import StandardDatabase
import structlog
import secrets
import bcrypt

logger = structlog.get_logger()


class APITokenRepository:
    """
    Repository for API token-related database operations.

    Handles:
    - Secure token generation (secrets library)
    - Bcrypt hashing for token storage
    - Token lifecycle (create, rotate, revoke)
    - Last-used timestamp updates
    - Token validation and lookup
    """

    # Token format: sk_{env}_{random}
    # - sk = secret key prefix
    # - env = live|test (environment)
    # - random = 48-char random string (36 bytes base64)
    TOKEN_PREFIX_LIVE = "complira_tk_"
    TOKEN_PREFIX_TEST = "complira_tk_test_"
    TOKEN_LENGTH = 60  # Total length (complira_tk_ + 52 chars)

    def __init__(self, db: StandardDatabase, environment: str = "live"):
        """
        Initialize API token repository.

        Args:
            db: ArangoDB database instance
            environment: Environment (live or test)
        """
        self.db = db
        self.api_tokens = db.collection("api_tokens")
        self.audit_log = db.collection("audit_log")
        self.environment = environment
        self.token_prefix = self.TOKEN_PREFIX_LIVE if environment == "live" else self.TOKEN_PREFIX_TEST

    def _generate_token_secret(self) -> str:
        """
        Generate cryptographically secure random token.

        Format: complira_tk_XXXXXXXXXX... (60 chars total)

        Returns:
            str: Full token secret

        Example:
            "complira_tk_abc123xyz789defghijklmnopqrstuvwxyz0123456789ABCD"
        """
        # Generate 36 random bytes, encode as base64-like string
        random_part = secrets.token_urlsafe(36)[:52]  # 52 chars after prefix
        return f"{self.token_prefix}{random_part}"

    def _hash_token(self, token: str) -> str:
        """
        Hash token using bcrypt.

        Args:
            token: Plain token string

        Returns:
            str: Bcrypt hash

        Security:
            - Uses bcrypt with cost factor 12
            - Salted automatically by bcrypt
            - Hash stored in database, never plaintext
        """
        return bcrypt.hashpw(token.encode(), bcrypt.gensalt(rounds=12)).decode()

    def _verify_token(self, token: str, token_hash: str) -> bool:
        """
        Verify token against hash.

        Args:
            token: Plain token string
            token_hash: Bcrypt hash from database

        Returns:
            bool: True if token matches hash
        """
        try:
            return bcrypt.checkpw(token.encode(), token_hash.encode())
        except Exception as e:
            logger.error("token_verification_failed", error=str(e))
            return False

    def _extract_prefix(self, token: str) -> str:
        """
        Extract display prefix from token (first 16 chars).

        Args:
            token: Full token string

        Returns:
            str: Token prefix for UI display

        Example:
            "complira_tk_abc123xyz789..." -> "complira_tk_abc123"
        """
        return token[:16] if len(token) >= 16 else token

    def create_token(
        self,
        organization_id: str,
        created_by_user_id: str,
        name: str,
        scopes: List[str],
        description: Optional[str] = None,
        rate_limit: int = 1000,
        expires_in_days: int = 365
    ) -> Dict[str, Any]:
        """
        Create new API token.

        Args:
            organization_id: Organization ID
            created_by_user_id: User creating the token
            name: Token name (for identification)
            scopes: List of scopes (e.g., ['scan:write', 'reference:read'])
            description: Optional description
            rate_limit: Requests per hour limit (default: 1000)
            expires_in_days: Days until expiration (default: 365)

        Returns:
            dict: Token document with PLAINTEXT secret (only time it's returned)

        Example:
            {
                "_key": "token_abc123",
                "organization_id": "org_xyz789",
                "created_by_user_id": "users/user123",
                "name": "CI/CD Pipeline Token",
                "description": "GitHub Actions",
                "token_hash": "$2b$12$...",
                "token_prefix": "complira_tk_abc123",
                "token_secret": "complira_tk_abc123xyz789...",  # ONLY in return value
                "scopes": ["scan:write", "reference:read"],
                "rate_limit": 1000,
                "created_at": "2024-01-15T10:00:00Z",
                "expires_at": "2025-01-15T10:00:00Z",
                "last_used": null,
                "revoked": false,
                "revoked_at": null,
                "revoked_by_user_id": null,
                "rotation_grace_until": null  # Set during rotation
            }
        """
        # Generate token secret
        token_secret = self._generate_token_secret()
        token_hash = self._hash_token(token_secret)
        token_prefix = self._extract_prefix(token_secret)

        # Calculate expiration
        now = datetime.utcnow()
        expires_at = now + timedelta(days=expires_in_days)

        # Create document
        document = {
            "organization_id": organization_id,
            "created_by_user_id": created_by_user_id,
            "name": name,
            "description": description,
            "token_hash": token_hash,
            "token_prefix": token_prefix,
            "scopes": scopes,
            "rate_limit": rate_limit,
            "created_at": now.isoformat() + "Z",
            "expires_at": expires_at.isoformat() + "Z",
            "last_used": None,
            "revoked": False,
            "revoked_at": None,
            "revoked_by_user_id": None,
            "rotation_grace_until": None,
        }

        # Insert into database
        meta = self.api_tokens.insert(document, return_new=True)
        token_doc = meta["new"]
        token_doc["_id"] = meta["_id"]
        token_doc["_key"] = meta["_key"]

        # Log creation in audit log
        self._log_audit_event(
            organization_id=organization_id,
            user_id=created_by_user_id,
            action="token.created",
            resource_type="api_token",
            resource_id=meta["_key"],
            metadata={"token_name": name, "scopes": scopes}
        )

        # Add plaintext secret to response (ONLY time it's returned)
        token_doc["token_secret"] = token_secret

        logger.info(
            "token_created",
            token_id=meta["_key"],
            organization_id=organization_id,
            name=name,
            scopes=scopes
        )

        return token_doc

    def get_token_by_id(self, token_id: str, organization_id: str) -> Optional[Dict[str, Any]]:
        """
        Get token by ID (without secret).

        Args:
            token_id: Token document key
            organization_id: Organization ID (for authorization check)

        Returns:
            dict or None: Token document (without token_secret)
        """
        query = """
        FOR token IN api_tokens
            FILTER token._key == @token_id
            FILTER token.organization_id == @organization_id
            RETURN token
        """

        cursor = self.db.aql.execute(
            query,
            bind_vars={"token_id": token_id, "organization_id": organization_id}
        )

        return next(cursor, None)

    def list_tokens(
        self,
        organization_id: str,
        include_revoked: bool = False,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """
        List all tokens for an organization.

        Args:
            organization_id: Organization ID
            include_revoked: Whether to include revoked tokens (default: False)
            page: Page number (1-indexed)
            page_size: Items per page

        Returns:
            dict: Paginated token list
                {
                    "tokens": [...],
                    "total": 10,
                    "page": 1,
                    "page_size": 20
                }
        """
        # Build filter
        revoked_filter = "" if include_revoked else "FILTER token.revoked == false"

        # Count query
        count_query = f"""
        FOR token IN api_tokens
            FILTER token.organization_id == @organization_id
            {revoked_filter}
            COLLECT WITH COUNT INTO total
            RETURN total
        """

        total = next(self.db.aql.execute(count_query, bind_vars={"organization_id": organization_id}), 0)

        # Data query
        offset = (page - 1) * page_size
        data_query = f"""
        FOR token IN api_tokens
            FILTER token.organization_id == @organization_id
            {revoked_filter}
            SORT token.created_at DESC
            LIMIT @offset, @page_size
            RETURN token
        """

        cursor = self.db.aql.execute(
            data_query,
            bind_vars={
                "organization_id": organization_id,
                "offset": offset,
                "page_size": page_size
            }
        )

        tokens = list(cursor)

        return {
            "tokens": tokens,
            "total": total,
            "page": page,
            "page_size": page_size
        }

    def validate_token(self, token_secret: str) -> Optional[Dict[str, Any]]:
        """
        Validate token and return associated document.

        Args:
            token_secret: Full token secret (from Authorization header)

        Returns:
            dict or None: Token document if valid, None if invalid/expired/revoked

        Checks:
            - Token exists and hash matches
            - Token not revoked
            - Token not expired
            - If rotation in progress, check grace period
        """
        # Extract prefix to narrow search
        token_prefix = self._extract_prefix(token_secret)

        # Find candidate tokens with matching prefix
        query = """
        FOR token IN api_tokens
            FILTER token.token_prefix == @token_prefix
            FILTER token.revoked == false
            FILTER token.expires_at > @now
            RETURN token
        """

        now = datetime.utcnow().isoformat() + "Z"
        cursor = self.db.aql.execute(
            query,
            bind_vars={"token_prefix": token_prefix, "now": now}
        )

        # Check hash for each candidate
        for token_doc in cursor:
            if self._verify_token(token_secret, token_doc["token_hash"]):
                # Valid token found
                logger.info(
                    "token_validated",
                    token_id=token_doc["_key"],
                    organization_id=token_doc["organization_id"]
                )
                return token_doc

        # No valid token found
        logger.warning("token_validation_failed", token_prefix=token_prefix)
        return None

    def update_last_used(self, token_id: str) -> None:
        """
        Update token's last_used timestamp.

        Args:
            token_id: Token document key

        Note:
            Called after successful API request authentication.
            Updates asynchronously to avoid blocking requests.
        """
        now = datetime.utcnow().isoformat() + "Z"

        self.api_tokens.update(
            {"_key": token_id},
            {"last_used": now}
        )

    def update_token(
        self,
        token_id: str,
        organization_id: str,
        user_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        scopes: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update token metadata (name, description, scopes).

        Args:
            token_id: Token document key
            organization_id: Organization ID (for authorization)
            user_id: User performing update
            name: New name (optional)
            description: New description (optional)
            scopes: New scopes (optional)

        Returns:
            dict or None: Updated token document
        """
        # Build update dict
        update_doc = {}
        if name is not None:
            update_doc["name"] = name
        if description is not None:
            update_doc["description"] = description
        if scopes is not None:
            update_doc["scopes"] = scopes

        if not update_doc:
            # No updates provided
            return self.get_token_by_id(token_id, organization_id)

        # Update document
        try:
            meta = self.api_tokens.update(
                {"_key": token_id, "organization_id": organization_id},
                update_doc,
                return_new=True
            )

            # Log update
            self._log_audit_event(
                organization_id=organization_id,
                user_id=user_id,
                action="token.updated",
                resource_type="api_token",
                resource_id=token_id,
                metadata=update_doc
            )

            logger.info("token_updated", token_id=token_id, updates=update_doc)
            return meta["new"]

        except Exception as e:
            logger.error("token_update_failed", token_id=token_id, error=str(e))
            return None

    def rotate_token(
        self,
        token_id: str,
        organization_id: str,
        user_id: str,
        grace_period_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Rotate token secret (old token valid for grace period).

        Args:
            token_id: Token document key
            organization_id: Organization ID (for authorization)
            user_id: User performing rotation
            grace_period_hours: Hours old token remains valid (default: 24)

        Returns:
            dict: New token document with plaintext secret

        Process:
            1. Generate new token secret
            2. Update token_hash and token_prefix
            3. Set rotation_grace_until timestamp
            4. Return new secret (ONLY time it's shown)

        Note:
            Old token will be valid until rotation_grace_until expires.
            Validation logic checks both current hash and rotation_grace_until.
        """
        # Get existing token
        existing = self.get_token_by_id(token_id, organization_id)
        if not existing:
            raise ValueError(f"Token {token_id} not found")

        # Generate new token
        new_token_secret = self._generate_token_secret()
        new_token_hash = self._hash_token(new_token_secret)
        new_token_prefix = self._extract_prefix(new_token_secret)

        # Calculate grace period
        grace_until = datetime.utcnow() + timedelta(hours=grace_period_hours)

        # Update document
        update_doc = {
            "token_hash": new_token_hash,
            "token_prefix": new_token_prefix,
            "rotation_grace_until": grace_until.isoformat() + "Z",
        }

        meta = self.api_tokens.update(
            {"_key": token_id},
            update_doc,
            return_new=True
        )

        # Log rotation
        self._log_audit_event(
            organization_id=organization_id,
            user_id=user_id,
            action="token.rotated",
            resource_type="api_token",
            resource_id=token_id,
            metadata={"grace_period_hours": grace_period_hours}
        )

        logger.info("token_rotated", token_id=token_id, grace_until=grace_until.isoformat())

        # Return new document with plaintext secret
        new_doc = meta["new"]
        new_doc["token_secret"] = new_token_secret
        return new_doc

    def revoke_token(
        self,
        token_id: str,
        organization_id: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Revoke token (immediate, irreversible).

        Args:
            token_id: Token document key
            organization_id: Organization ID (for authorization)
            user_id: User performing revocation

        Returns:
            dict or None: Revoked token document
        """
        now = datetime.utcnow().isoformat() + "Z"

        try:
            meta = self.api_tokens.update(
                {"_key": token_id, "organization_id": organization_id},
                {
                    "revoked": True,
                    "revoked_at": now,
                    "revoked_by_user_id": user_id
                },
                return_new=True
            )

            # Log revocation
            self._log_audit_event(
                organization_id=organization_id,
                user_id=user_id,
                action="token.revoked",
                resource_type="api_token",
                resource_id=token_id,
                metadata={"revoked_at": now}
            )

            logger.info("token_revoked", token_id=token_id, revoked_by=user_id)
            return meta["new"]

        except Exception as e:
            logger.error("token_revocation_failed", token_id=token_id, error=str(e))
            return None

    def delete_token(
        self,
        token_id: str,
        organization_id: str,
        user_id: str
    ) -> bool:
        """
        Permanently delete token.

        Args:
            token_id: Token document key
            organization_id: Organization ID (for authorization)
            user_id: User performing deletion

        Returns:
            bool: True if deleted, False if not found

        Warning:
            This is permanent deletion. Prefer revoke_token() for most cases.
        """
        try:
            self.api_tokens.delete(
                {"_key": token_id, "organization_id": organization_id}
            )

            # Log deletion
            self._log_audit_event(
                organization_id=organization_id,
                user_id=user_id,
                action="token.deleted",
                resource_type="api_token",
                resource_id=token_id,
                metadata={}
            )

            logger.info("token_deleted", token_id=token_id, deleted_by=user_id)
            return True

        except Exception as e:
            logger.error("token_deletion_failed", token_id=token_id, error=str(e))
            return False

    def _log_audit_event(
        self,
        organization_id: str,
        user_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        metadata: Dict[str, Any]
    ) -> None:
        """
        Log audit event for token operations.

        Args:
            organization_id: Organization ID
            user_id: User performing action
            action: Action type (e.g., 'token.created', 'token.revoked')
            resource_type: Resource type (always 'api_token')
            resource_id: Token ID
            metadata: Additional metadata
        """
        try:
            audit_doc = {
                "organization_id": organization_id,
                "user_id": user_id,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "metadata": metadata,
                # IP and user_agent should be added by endpoint layer
            }

            self.audit_log.insert(audit_doc)

        except Exception as e:
            # Don't fail token operation if audit log fails
            logger.error("audit_log_failed", error=str(e), action=action)
