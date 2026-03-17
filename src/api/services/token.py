"""
API Token management service.

Wraps APITokenRepository for token endpoints.
"""

from typing import Dict, Any, Optional
from api.repositories.api_token import APITokenRepository
import structlog

logger = structlog.get_logger()


class TokenService:
    """Service layer for API token management."""

    def __init__(self, db):
        self.token_repo = APITokenRepository(db)

    def create_token(self, **kwargs) -> Dict[str, Any]:
        """Create a new API token."""
        return self.token_repo.create_token(**kwargs)

    def list_tokens(self, **kwargs) -> Dict[str, Any]:
        """List tokens for an organization."""
        return self.token_repo.list_tokens(**kwargs)

    def get_token_by_id(self, token_id: str, organization_id: str) -> Optional[Dict[str, Any]]:
        """Get token by ID."""
        return self.token_repo.get_token_by_id(token_id, organization_id)

    def update_token(self, **kwargs) -> Optional[Dict[str, Any]]:
        """Update token metadata."""
        return self.token_repo.update_token(**kwargs)

    def rotate_token(self, **kwargs) -> Dict[str, Any]:
        """Rotate token secret."""
        return self.token_repo.rotate_token(**kwargs)

    def revoke_token(self, **kwargs) -> Optional[Dict[str, Any]]:
        """Revoke a token."""
        return self.token_repo.revoke_token(**kwargs)

    def delete_token(self, **kwargs) -> bool:
        """Permanently delete a token."""
        return self.token_repo.delete_token(**kwargs)
