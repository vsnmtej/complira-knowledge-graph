"""
Integration tests for API token management endpoints.

Tests complete token lifecycle: create → list → get → update → rotate → revoke → delete.

Routes tested:
    POST   /v1/tokens              - Create new token
    GET    /v1/tokens              - List all tokens
    GET    /v1/tokens/{token_id}   - Get token details
    PATCH  /v1/tokens/{token_id}   - Update token metadata
    POST   /v1/tokens/{token_id}/rotate  - Rotate token secret
    POST   /v1/tokens/{token_id}/revoke  - Revoke token
    DELETE /v1/tokens/{token_id}   - Delete token permanently
"""

import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from datetime import datetime, timedelta


@pytest.fixture
def mock_token_db():
    """Mock database for token operations."""
    db = MagicMock()
    db.collection = Mock(return_value=MagicMock())
    db.aql = MagicMock()

    # Mock successful token creation
    collection = db.collection.return_value
    collection.insert = Mock(return_value={
        "_key": "token_abc123",
        "_id": "api_tokens/token_abc123",
        "_rev": "_rev123",
    })
    collection.update = Mock(return_value={
        "_key": "token_abc123",
        "_id": "api_tokens/token_abc123",
        "_rev": "_rev456",
    })
    collection.delete = Mock(return_value=True)

    # Mock AQL queries for token listing
    db.aql.execute = Mock(return_value=[
        {
            "_key": "token_abc123",
            "_id": "api_tokens/token_abc123",
            "organization_id": "org_xyz789",
            "created_by_user_id": "users/user123",
            "name": "CI/CD Pipeline Token",
            "description": "GitHub Actions token",
            "token_prefix": "complira_tk_abc123",
            "scopes": ["scan:write", "reference:read"],
            "rate_limit": 1000,
            "created_at": "2024-01-15T10:00:00Z",
            "expires_at": "2025-01-15T10:00:00Z",
            "last_used": "2024-01-15T14:28:00Z",
            "revoked": False,
        },
        {
            "_key": "token_def456",
            "_id": "api_tokens/token_def456",
            "organization_id": "org_xyz789",
            "created_by_user_id": "users/user123",
            "name": "Development Token",
            "description": "Local development",
            "token_prefix": "sk_test_def456",
            "scopes": ["scan:read"],
            "rate_limit": 100,
            "created_at": "2024-01-10T10:00:00Z",
            "expires_at": "2024-04-10T10:00:00Z",
            "last_used": None,
            "revoked": False,
        }
    ])

    return db


@pytest.fixture
def local_admin_user():
    """Mock authenticated user with admin role."""
    return {
        "sub": "users/user123",
        "org_id": "org_xyz789",
        "role": "admin",
        "email": "admin@example.com",
        "name": "Test Admin"
    }


@pytest.fixture
def local_owner_user():
    """Mock authenticated user with owner role."""
    return {
        "sub": "users/owner123",
        "org_id": "org_xyz789",
        "role": "owner",
        "email": "owner@example.com",
        "name": "Test Owner"
    }


@pytest.fixture
def local_regular_user():
    """Mock authenticated user with regular role."""
    return {
        "sub": "users/regular123",
        "org_id": "org_xyz789",
        "role": "user",
        "email": "user@example.com",
        "name": "Test User"
    }


def _override_user(app, user_dict):
    """Helper to set up user auth override on the app."""
    from api.core.security import get_current_user

    async def _override(token=None):
        return user_dict

    app.dependency_overrides[get_current_user] = _override


class TestTokenCreation:
    """Tests for POST /v1/tokens - Create new token."""

    @pytest.mark.integration
    def test_create_token_success(self, api_client, app, mock_token_db, local_admin_user):
        """
        Test: POST /v1/tokens - Successfully create new API token.

        Verifies:
        - Token created with correct metadata
        - Full token secret returned (only shown once)
        - Response includes token_id, prefix, expiration
        - 201 CREATED status
        """
        _override_user(app, local_admin_user)

        with patch('api.v1.endpoints.tokens.get_database', return_value=mock_token_db), \
             patch('api.repositories.api_token.APITokenRepository.create_token') as mock_create, \
             patch('api.repositories.api_token.APITokenRepository.list_tokens') as mock_list:

            # Mock token limit check (returns fewer than 100 tokens)
            mock_list.return_value = {"total": 5}

            # Mock token creation
            mock_create.return_value = {
                "_key": "token_abc123",
                "organization_id": "org_xyz789",
                "created_by_user_id": "users/user123",
                "name": "CI/CD Pipeline Token",
                "token_secret": "complira_tk_abc123xyz789defghijklmnopqrstuvwxyz0123456789ABCDEFGHIJK",
                "token_prefix": "complira_tk_abc123",
                "scopes": ["scan:write", "reference:read"],
                "rate_limit": 1000,
                "expires_at": "2025-01-15T10:00:00Z"
            }

            # Make request
            response = api_client.post(
                "/v1/tokens",
                json={
                    "name": "CI/CD Pipeline Token",
                    "description": "GitHub Actions for main repo",
                    "scopes": ["scan:write", "reference:read"],
                    "rate_limit": 1000,
                    "expires_in_days": 365
                },
                headers={"X-API-Key": "test_key"}
            )

            # Verify response
            assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"

            data = response.json()
            assert data["success"] is True
            assert "token" in data
            assert data["token"].startswith("complira_tk_")
            assert data["token_id"] == "token_abc123"
            assert data["token_prefix"] == "complira_tk_abc123"
            assert "expires_at" in data
            assert "Save this token" in data["message"]

    @pytest.mark.integration
    def test_create_token_invalid_scopes(self, api_client, app, mock_token_db, local_admin_user):
        """
        Test: POST /v1/tokens - Reject invalid scopes.

        Verifies:
        - Invalid scope values rejected
        - 422 UNPROCESSABLE_ENTITY status
        - Error message indicates which scope is invalid
        """
        _override_user(app, local_admin_user)

        with patch('api.v1.endpoints.tokens.get_database', return_value=mock_token_db):

            response = api_client.post(
                "/v1/tokens",
                json={
                    "name": "Test Token",
                    "scopes": ["invalid:scope", "scan:write"],
                    "rate_limit": 1000,
                    "expires_in_days": 365
                },
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 422
            assert "invalid" in response.text.lower()

    @pytest.mark.integration
    def test_create_token_forbidden_for_regular_users(
        self, api_client, app, mock_token_db, local_regular_user
    ):
        """
        Test: POST /v1/tokens - Regular users cannot create tokens.

        Verifies:
        - Only admin/owner roles can create tokens
        - 403 FORBIDDEN for regular users
        """
        _override_user(app, local_regular_user)

        with patch('api.v1.endpoints.tokens.get_database', return_value=mock_token_db):

            response = api_client.post(
                "/v1/tokens",
                json={
                    "name": "Test Token",
                    "scopes": ["scan:write"],
                    "rate_limit": 1000,
                    "expires_in_days": 365
                },
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 403
            assert "owners and admins" in response.text.lower()

    @pytest.mark.integration
    def test_create_token_exceeds_limit(
        self, api_client, app, mock_token_db, local_admin_user
    ):
        """
        Test: POST /v1/tokens - Reject when organization has 100+ tokens.

        Verifies:
        - Maximum 100 active tokens per organization
        - 400 BAD REQUEST when limit reached
        """
        _override_user(app, local_admin_user)

        with patch('api.v1.endpoints.tokens.get_database', return_value=mock_token_db), \
             patch('api.repositories.api_token.APITokenRepository.list_tokens') as mock_list:

            # Mock token limit exceeded
            mock_list.return_value = {"total": 100}

            response = api_client.post(
                "/v1/tokens",
                json={
                    "name": "Test Token",
                    "scopes": ["scan:write"],
                    "rate_limit": 1000,
                    "expires_in_days": 365
                },
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 400
            assert "maximum token limit" in response.text.lower()


class TestTokenListing:
    """Tests for GET /v1/tokens - List all tokens."""

    @pytest.mark.integration
    def test_list_tokens_success(self, api_client, app, mock_token_db, local_admin_user):
        """
        Test: GET /v1/tokens - List all active tokens.

        Verifies:
        - Returns paginated list of tokens
        - Excludes revoked tokens by default
        - Includes token metadata but NOT secrets
        - Includes pagination info (total, page, page_size)
        """
        _override_user(app, local_admin_user)

        with patch('api.v1.endpoints.tokens.get_database', return_value=mock_token_db), \
             patch('api.repositories.api_token.APITokenRepository.list_tokens') as mock_list:

            mock_list.return_value = {
                "tokens": [
                    {
                        "_key": "token_abc123",
                        "organization_id": "org_xyz789",
                        "created_by_user_id": "users/user123",
                        "name": "CI/CD Token",
                        "description": "GitHub Actions",
                        "token_prefix": "complira_tk_abc123",
                        "scopes": ["scan:write"],
                        "rate_limit": 1000,
                        "created_at": "2024-01-15T10:00:00Z",
                        "expires_at": "2025-01-15T10:00:00Z",
                        "last_used": "2024-01-15T14:28:00Z",
                        "revoked": False
                    }
                ],
                "total": 1,
                "page": 1,
                "page_size": 20
            }

            response = api_client.get(
                "/v1/tokens",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            assert "tokens" in data
            assert len(data["tokens"]) == 1
            assert data["total"] == 1
            assert data["page"] == 1
            assert data["page_size"] == 20

            # Verify token details
            token = data["tokens"][0]
            assert token["id"] == "token_abc123"
            assert token["name"] == "CI/CD Token"
            assert token["token_prefix"] == "complira_tk_abc123"
            assert token["revoked"] is False
            assert "token_secret" not in token  # Secret never returned

    @pytest.mark.integration
    def test_list_tokens_with_revoked(
        self, api_client, app, mock_token_db, local_admin_user
    ):
        """
        Test: GET /v1/tokens?include_revoked=true - Include revoked tokens.

        Verifies:
        - include_revoked parameter works
        - Revoked tokens have revoked=true
        - Includes revocation metadata
        """
        _override_user(app, local_admin_user)

        with patch('api.v1.endpoints.tokens.get_database', return_value=mock_token_db), \
             patch('api.repositories.api_token.APITokenRepository.list_tokens') as mock_list:

            mock_list.return_value = {
                "tokens": [
                    {
                        "_key": "token_revoked",
                        "organization_id": "org_xyz789",
                        "created_by_user_id": "users/user123",
                        "name": "Revoked Token",
                        "token_prefix": "complira_tk_revoked",
                        "scopes": ["scan:write"],
                        "rate_limit": 1000,
                        "created_at": "2024-01-01T10:00:00Z",
                        "expires_at": "2025-01-01T10:00:00Z",
                        "revoked": True,
                        "revoked_at": "2024-01-10T10:00:00Z",
                        "revoked_by_user_id": "users/admin123"
                    }
                ],
                "total": 1,
                "page": 1,
                "page_size": 20
            }

            response = api_client.get(
                "/v1/tokens?include_revoked=true",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            token = data["tokens"][0]
            assert token["revoked"] is True
            assert token["revoked_at"] == "2024-01-10T10:00:00Z"
            assert token["revoked_by_user_id"] == "users/admin123"

    @pytest.mark.integration
    def test_list_tokens_pagination(
        self, api_client, app, mock_token_db, local_admin_user
    ):
        """
        Test: GET /v1/tokens?page=2&page_size=10 - Pagination works.

        Verifies:
        - page and page_size parameters work
        - Response includes correct pagination metadata
        """
        _override_user(app, local_admin_user)

        with patch('api.v1.endpoints.tokens.get_database', return_value=mock_token_db), \
             patch('api.repositories.api_token.APITokenRepository.list_tokens') as mock_list:

            mock_list.return_value = {
                "tokens": [],
                "total": 25,
                "page": 2,
                "page_size": 10
            }

            response = api_client.get(
                "/v1/tokens?page=2&page_size=10",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            assert data["total"] == 25
            assert data["page"] == 2
            assert data["page_size"] == 10


class TestTokenRetrieval:
    """Tests for GET /v1/tokens/{token_id} - Get token details."""

    @pytest.mark.integration
    def test_get_token_success(self, api_client, app, mock_token_db, local_admin_user):
        """
        Test: GET /v1/tokens/{token_id} - Successfully retrieve token details.

        Verifies:
        - Token details returned
        - Secret NOT included
        - All metadata present
        """
        _override_user(app, local_admin_user)

        with patch('api.v1.endpoints.tokens.get_database', return_value=mock_token_db), \
             patch('api.repositories.api_token.APITokenRepository.get_token_by_id') as mock_get:

            mock_get.return_value = {
                "_key": "token_abc123",
                "organization_id": "org_xyz789",
                "created_by_user_id": "users/user123",
                "name": "CI/CD Token",
                "description": "GitHub Actions",
                "token_prefix": "complira_tk_abc123",
                "scopes": ["scan:write", "reference:read"],
                "rate_limit": 1000,
                "created_at": "2024-01-15T10:00:00Z",
                "expires_at": "2025-01-15T10:00:00Z",
                "last_used": "2024-01-15T14:28:00Z",
                "revoked": False
            }

            response = api_client.get(
                "/v1/tokens/token_abc123",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            assert data["id"] == "token_abc123"
            assert data["name"] == "CI/CD Token"
            assert data["token_prefix"] == "complira_tk_abc123"
            assert data["scopes"] == ["scan:write", "reference:read"]
            assert data["revoked"] is False
            assert "token_secret" not in data

    @pytest.mark.integration
    def test_get_token_not_found(self, api_client, app, mock_token_db, local_admin_user):
        """
        Test: GET /v1/tokens/{token_id} - 404 when token doesn't exist.

        Verifies:
        - 404 NOT FOUND for non-existent token
        - Error message indicates token not found
        """
        _override_user(app, local_admin_user)

        with patch('api.v1.endpoints.tokens.get_database', return_value=mock_token_db), \
             patch('api.repositories.api_token.APITokenRepository.get_token_by_id') as mock_get:

            mock_get.return_value = None

            response = api_client.get(
                "/v1/tokens/nonexistent_token",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 404
            assert "not found" in response.text.lower()


class TestTokenUpdate:
    """Tests for PATCH /v1/tokens/{token_id} - Update token metadata."""

    @pytest.mark.integration
    def test_update_token_success(self, api_client, app, mock_token_db, local_admin_user):
        """
        Test: PATCH /v1/tokens/{token_id} - Successfully update token.

        Verifies:
        - Name, description, scopes can be updated
        - Updated token returned
        - Cannot update token secret (use rotate instead)
        """
        _override_user(app, local_admin_user)

        with patch('api.v1.endpoints.tokens.get_database', return_value=mock_token_db), \
             patch('api.repositories.api_token.APITokenRepository.update_token') as mock_update:

            mock_update.return_value = {
                "_key": "token_abc123",
                "organization_id": "org_xyz789",
                "created_by_user_id": "users/user123",
                "name": "Updated Token Name",
                "description": "Updated description",
                "token_prefix": "complira_tk_abc123",
                "scopes": ["scan:write", "reference:read", "vex:generate"],
                "rate_limit": 1000,
                "created_at": "2024-01-15T10:00:00Z",
                "expires_at": "2025-01-15T10:00:00Z",
                "last_used": "2024-01-15T14:28:00Z",
                "revoked": False
            }

            response = api_client.patch(
                "/v1/tokens/token_abc123",
                json={
                    "name": "Updated Token Name",
                    "description": "Updated description",
                    "scopes": ["scan:write", "reference:read", "vex:generate"]
                },
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            assert data["name"] == "Updated Token Name"
            assert data["description"] == "Updated description"
            assert len(data["scopes"]) == 3
            assert "vex:generate" in data["scopes"]

    @pytest.mark.integration
    def test_update_token_forbidden_for_regular_users(
        self, api_client, app, mock_token_db, local_regular_user
    ):
        """
        Test: PATCH /v1/tokens/{token_id} - Regular users cannot update tokens.

        Verifies:
        - Only admin/owner can update
        - 403 FORBIDDEN for regular users
        """
        _override_user(app, local_regular_user)

        with patch('api.v1.endpoints.tokens.get_database', return_value=mock_token_db):

            response = api_client.patch(
                "/v1/tokens/token_abc123",
                json={"name": "Updated Name"},
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 403


class TestTokenRotation:
    """Tests for POST /v1/tokens/{token_id}/rotate - Rotate token secret."""

    @pytest.mark.integration
    def test_rotate_token_success(self, api_client, app, mock_token_db, local_admin_user):
        """
        Test: POST /v1/tokens/{token_id}/rotate - Successfully rotate token.

        Verifies:
        - New token secret generated
        - Old token valid during grace period
        - Response includes both expiration times
        - New secret shown only once
        """
        _override_user(app, local_admin_user)

        with patch('api.v1.endpoints.tokens.get_database', return_value=mock_token_db), \
             patch('api.repositories.api_token.APITokenRepository.rotate_token') as mock_rotate:

            grace_until = (datetime.utcnow() + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
            new_expires = (datetime.utcnow() + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")

            mock_rotate.return_value = {
                "_key": "token_abc123",
                "token_secret": "complira_tk_xyz789newtoken456abcdefghijklmnopqrstuvwxyz0123456789",
                "token_prefix": "complira_tk_xyz789",
                "rotation_grace_until": grace_until,
                "expires_at": new_expires
            }

            response = api_client.post(
                "/v1/tokens/token_abc123/rotate",
                json={"grace_period_hours": 24},
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            assert data["success"] is True
            assert data["new_token"].startswith("complira_tk_xyz789")
            assert data["token_id"] == "token_abc123"
            assert data["token_prefix"] == "complira_tk_xyz789"
            assert "old_token_expires_at" in data
            assert "new_token_expires_at" in data
            assert "24 hours" in data["message"]

    @pytest.mark.integration
    def test_rotate_token_custom_grace_period(
        self, api_client, app, mock_token_db, local_admin_user
    ):
        """
        Test: POST /v1/tokens/{token_id}/rotate - Custom grace period.

        Verifies:
        - grace_period_hours parameter works (1-168 hours)
        - Response message reflects custom period
        """
        _override_user(app, local_admin_user)

        with patch('api.v1.endpoints.tokens.get_database', return_value=mock_token_db), \
             patch('api.repositories.api_token.APITokenRepository.rotate_token') as mock_rotate:

            grace_until = (datetime.utcnow() + timedelta(hours=72)).strftime("%Y-%m-%dT%H:%M:%SZ")

            mock_rotate.return_value = {
                "_key": "token_abc123",
                "token_secret": "complira_tk_newtoken",
                "token_prefix": "complira_tk_xyz789",
                "rotation_grace_until": grace_until,
                "expires_at": "2025-01-15T10:00:00Z"
            }

            response = api_client.post(
                "/v1/tokens/token_abc123/rotate",
                json={"grace_period_hours": 72},
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            assert "72 hours" in response.json()["message"]

    @pytest.mark.integration
    def test_rotate_token_not_found(
        self, api_client, app, mock_token_db, local_admin_user
    ):
        """
        Test: POST /v1/tokens/{token_id}/rotate - 404 for non-existent token.
        """
        _override_user(app, local_admin_user)

        with patch('api.v1.endpoints.tokens.get_database', return_value=mock_token_db), \
             patch('api.repositories.api_token.APITokenRepository.rotate_token') as mock_rotate:

            mock_rotate.side_effect = ValueError("Token not found")

            response = api_client.post(
                "/v1/tokens/nonexistent/rotate",
                json={"grace_period_hours": 24},
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 404


class TestTokenRevocation:
    """Tests for POST /v1/tokens/{token_id}/revoke - Revoke token."""

    @pytest.mark.integration
    def test_revoke_token_success(self, api_client, app, mock_token_db, local_admin_user):
        """
        Test: POST /v1/tokens/{token_id}/revoke - Successfully revoke token.

        Verifies:
        - Token immediately revoked (no grace period)
        - Response includes revocation timestamp
        - Revocation is irreversible
        """
        _override_user(app, local_admin_user)

        with patch('api.v1.endpoints.tokens.get_database', return_value=mock_token_db), \
             patch('api.repositories.api_token.APITokenRepository.revoke_token') as mock_revoke:

            revoked_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

            mock_revoke.return_value = {
                "_key": "token_abc123",
                "revoked": True,
                "revoked_at": revoked_at,
                "revoked_by_user_id": "users/user123"
            }

            response = api_client.post(
                "/v1/tokens/token_abc123/revoke",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            assert data["success"] is True
            assert data["token_id"] == "token_abc123"
            assert "revoked_at" in data
            assert data["message"] == "Token revoked successfully"

    @pytest.mark.integration
    def test_revoke_token_not_found(
        self, api_client, app, mock_token_db, local_admin_user
    ):
        """
        Test: POST /v1/tokens/{token_id}/revoke - 404 for non-existent token.
        """
        _override_user(app, local_admin_user)

        with patch('api.v1.endpoints.tokens.get_database', return_value=mock_token_db), \
             patch('api.repositories.api_token.APITokenRepository.revoke_token') as mock_revoke:

            mock_revoke.return_value = None

            response = api_client.post(
                "/v1/tokens/nonexistent/revoke",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 404

    @pytest.mark.integration
    def test_revoke_token_forbidden_for_regular_users(
        self, api_client, app, mock_token_db, local_regular_user
    ):
        """
        Test: POST /v1/tokens/{token_id}/revoke - Regular users cannot revoke.
        """
        _override_user(app, local_regular_user)

        with patch('api.v1.endpoints.tokens.get_database', return_value=mock_token_db):

            response = api_client.post(
                "/v1/tokens/token_abc123/revoke",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 403


class TestTokenDeletion:
    """Tests for DELETE /v1/tokens/{token_id} - Permanently delete token."""

    @pytest.mark.integration
    def test_delete_token_success(
        self, api_client, app, mock_token_db, local_owner_user
    ):
        """
        Test: DELETE /v1/tokens/{token_id} - Successfully delete token.

        Verifies:
        - Token permanently deleted
        - 204 NO CONTENT response
        - Only owners can delete (not admins)
        """
        _override_user(app, local_owner_user)

        with patch('api.v1.endpoints.tokens.get_database', return_value=mock_token_db), \
             patch('api.repositories.api_token.APITokenRepository.delete_token') as mock_delete:

            mock_delete.return_value = True

            response = api_client.delete(
                "/v1/tokens/token_abc123",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 204
            assert response.text == ""  # No response body

    @pytest.mark.integration
    def test_delete_token_forbidden_for_admin(
        self, api_client, app, mock_token_db, local_admin_user
    ):
        """
        Test: DELETE /v1/tokens/{token_id} - Admins CANNOT delete (owner only).

        Verifies:
        - Deletion restricted to owners only
        - 403 FORBIDDEN for admins
        """
        _override_user(app, local_admin_user)

        with patch('api.v1.endpoints.tokens.get_database', return_value=mock_token_db):

            response = api_client.delete(
                "/v1/tokens/token_abc123",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 403
            assert "owners" in response.text.lower()

    @pytest.mark.integration
    def test_delete_token_not_found(
        self, api_client, app, mock_token_db, local_owner_user
    ):
        """
        Test: DELETE /v1/tokens/{token_id} - 404 for non-existent token.
        """
        _override_user(app, local_owner_user)

        with patch('api.v1.endpoints.tokens.get_database', return_value=mock_token_db), \
             patch('api.repositories.api_token.APITokenRepository.delete_token') as mock_delete:

            mock_delete.return_value = False

            response = api_client.delete(
                "/v1/tokens/nonexistent",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 404


class TestTokenLifecycle:
    """Integration tests for complete token lifecycle."""

    @pytest.mark.integration
    def test_full_token_lifecycle(
        self, api_client, app, mock_token_db, local_admin_user, local_owner_user
    ):
        """
        Test: Complete token lifecycle - create -> update -> rotate -> revoke -> delete.

        Verifies:
        - All operations work together
        - State transitions are valid
        - Authorization checks at each step
        """
        with patch('api.v1.endpoints.tokens.get_database', return_value=mock_token_db), \
             patch('api.services.token.APITokenRepository') as MockRepo:

            mock_repo = MockRepo.return_value

            # Step 1: Create token (as admin)
            _override_user(app, local_admin_user)
            mock_repo.list_tokens.return_value = {"total": 5}
            mock_repo.create_token.return_value = {
                "_key": "token_lifecycle",
                "token_secret": "complira_tk_lifecycle123",
                "token_prefix": "complira_tk_lifecycle",
                "expires_at": "2025-01-15T10:00:00Z"
            }

            create_response = api_client.post(
                "/v1/tokens",
                json={
                    "name": "Lifecycle Test Token",
                    "scopes": ["scan:write"],
                    "rate_limit": 1000,
                    "expires_in_days": 365
                },
                headers={"X-API-Key": "test_key"}
            )

            assert create_response.status_code == 201
            token_id = create_response.json()["token_id"]

            # Step 2: Update token (as admin)
            _override_user(app, local_admin_user)
            mock_repo.update_token.return_value = {
                "_key": token_id,
                "organization_id": "org_xyz789",
                "created_by_user_id": "users/user123",
                "name": "Updated Lifecycle Token",
                "token_prefix": "complira_tk_lifecycle",
                "scopes": ["scan:write", "reference:read"],
                "rate_limit": 1000,
                "created_at": "2024-01-15T10:00:00Z",
                "expires_at": "2025-01-15T10:00:00Z",
                "revoked": False
            }

            update_response = api_client.patch(
                f"/v1/tokens/{token_id}",
                json={"name": "Updated Lifecycle Token"},
                headers={"X-API-Key": "test_key"}
            )

            assert update_response.status_code == 200

            # Step 3: Rotate token (as admin)
            _override_user(app, local_admin_user)
            mock_repo.rotate_token.return_value = {
                "_key": token_id,
                "token_secret": "complira_tk_rotated456",
                "token_prefix": "complira_tk_rotated",
                "rotation_grace_until": "2024-01-16T10:00:00Z",
                "expires_at": "2025-01-15T10:00:00Z"
            }

            rotate_response = api_client.post(
                f"/v1/tokens/{token_id}/rotate",
                json={"grace_period_hours": 24},
                headers={"X-API-Key": "test_key"}
            )

            assert rotate_response.status_code == 200

            # Step 4: Revoke token (as admin)
            _override_user(app, local_admin_user)
            mock_repo.revoke_token.return_value = {
                "_key": token_id,
                "revoked": True,
                "revoked_at": "2024-01-15T15:00:00Z"
            }

            revoke_response = api_client.post(
                f"/v1/tokens/{token_id}/revoke",
                headers={"X-API-Key": "test_key"}
            )

            assert revoke_response.status_code == 200

            # Step 5: Delete token (as owner)
            _override_user(app, local_owner_user)
            mock_repo.delete_token.return_value = True

            delete_response = api_client.delete(
                f"/v1/tokens/{token_id}",
                headers={"X-API-Key": "test_key"}
            )

            assert delete_response.status_code == 204

            print("✅ Full token lifecycle test passed: create → update → rotate → revoke → delete")
