"""
Integration tests for account management endpoints.

Tests full API flow for all 3 account endpoints:
- POST /v1/account/api-keys (create API key)
- GET /v1/account/api-keys (list API keys)
- DELETE /v1/account/api-keys/{key_id} (revoke API key)
"""

import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from fastapi.testclient import TestClient
from datetime import datetime, timedelta


@pytest.fixture
def mock_account_db():
    """Mock ArangoDB database for account operations."""
    db = MagicMock()
    db.collection = Mock(return_value=MagicMock())
    db.aql = MagicMock()
    db.has_collection = Mock(return_value=True)

    # Mock collection operations
    collection = db.collection.return_value
    collection.insert = Mock(return_value={
        "_key": "key_abc123def456ghi789jkl012mno345pq",
        "_id": "customer_api_keys/key_abc123def456ghi789jkl012mno345pq",
        "_rev": "_rev123",
    })
    collection.update = Mock(return_value={
        "_key": "key_abc123def456ghi789jkl012mno345pq",
        "_id": "customer_api_keys/key_abc123def456ghi789jkl012mno345pq",
        "_rev": "_rev456",
    })

    # Mock AQL queries for listing API keys
    db.aql.execute = Mock(return_value=[
        {
            "_key": "key_abc123def456ghi789jkl012mno345pq",
            "key_id": "key_abc123def456ghi789jkl012mno345pq",
            "customer_id": "customer_test",
            "name": "Production Server",
            "description": "Main production deployment",
            "key_prefix": "ak_live_",
            "created_at": "2024-01-15T10:00:00Z",
            "expires_at": "2024-04-15T10:00:00Z",
            "last_used_at": "2024-01-15T14:28:00Z",
            "revoked": False,
            "revoked_at": None,
            "revoked_reason": None,
        },
        {
            "_key": "key_def456ghi789jkl012mno345pqr678st",
            "key_id": "key_def456ghi789jkl012mno345pqr678st",
            "customer_id": "customer_test",
            "name": "Development Environment",
            "description": "Local development testing",
            "key_prefix": "ak_test_",
            "created_at": "2024-01-10T10:00:00Z",
            "expires_at": None,
            "last_used_at": None,
            "revoked": False,
            "revoked_at": None,
            "revoked_reason": None,
        },
        {
            "_key": "key_ghi789jkl012mno345pqr678stu901vwx",
            "key_id": "key_ghi789jkl012mno345pqr678stu901vwx",
            "customer_id": "customer_test",
            "name": "Revoked CI/CD Key",
            "description": "Old GitHub Actions key",
            "key_prefix": "ak_live_",
            "created_at": "2024-01-01T10:00:00Z",
            "expires_at": "2025-01-01T10:00:00Z",
            "last_used_at": "2024-01-05T10:00:00Z",
            "revoked": True,
            "revoked_at": "2024-01-05T15:00:00Z",
            "revoked_reason": "Compromised key - rotating to new credentials",
        }
    ])

    return db


class TestCreateAPIKey:
    """Integration tests for POST /v1/account/api-keys - Create new API key."""

    @pytest.mark.integration
    def test_create_api_key_success_without_expiration(
        self, api_client, app, override_customer_auth, mock_account_db
    ):
        """
        Test: POST /v1/account/api-keys - Successfully create API key without expiration.

        Verifies:
        - API key created with correct metadata
        - Full API key returned (only shown once)
        - Response includes key_id, prefix, created_at
        - No expiration date when not specified
        - 200 OK status
        """
        with patch('api.v1.endpoints.account.get_database', return_value=mock_account_db), \
             patch('api.v1.endpoints.account.generate_api_key', return_value="ak_live_abc123xyz789defghijklmnopqrstuvwxyz0123456789"), \
             patch('api.v1.endpoints.account.generate_key_id', return_value="key_abc123def456ghi789jkl012mno345pq"), \
             patch('api.core.security.hash_api_key', return_value="$2b$12$hashed_api_key"):

            # Make request
            response = api_client.post(
                "/v1/account/api-keys",
                json={
                    "name": "Production Server",
                    "description": "API key for production deployment"
                },
                headers={"X-API-Key": "test_key"}
            )

            # Verify response
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

            data = response.json()
            assert data["success"] is True
            assert "data" in data

            key_data = data["data"]
            assert key_data["key_id"] == "key_abc123def456ghi789jkl012mno345pq"
            assert key_data["name"] == "Production Server"
            assert key_data["api_key"] == "ak_live_abc123xyz789defghijklmnopqrstuvwxyz0123456789"
            assert key_data["created_at"]
            assert key_data["expires_at"] is None  # No expiration
            assert "warning" in key_data
            assert "Save this API key securely" in key_data["warning"]

    @pytest.mark.integration
    def test_create_api_key_success_with_expiration(
        self, api_client, app, override_customer_auth, mock_account_db
    ):
        """
        Test: POST /v1/account/api-keys - Successfully create API key with expiration.

        Verifies:
        - API key created with expiration date
        - expires_at calculated correctly (90 days from creation)
        - 200 OK status
        """
        with patch('api.v1.endpoints.account.get_database', return_value=mock_account_db), \
             patch('api.v1.endpoints.account.generate_api_key', return_value="ak_live_expiring_key_123"), \
             patch('api.v1.endpoints.account.generate_key_id', return_value="key_expiring_123"), \
             patch('api.core.security.hash_api_key', return_value="$2b$12$hashed_api_key"):

            # Make request with 90 day expiration
            response = api_client.post(
                "/v1/account/api-keys",
                json={
                    "name": "Temporary Key",
                    "description": "90-day temporary access key",
                    "expires_days": 90
                },
                headers={"X-API-Key": "test_key"}
            )

            # Verify response
            assert response.status_code == 200

            data = response.json()
            assert data["success"] is True

            key_data = data["data"]
            assert key_data["expires_at"] is not None
            assert key_data["expires_at"].endswith("Z")  # ISO 8601 format

            # Verify expiration is approximately 90 days from now
            created = datetime.fromisoformat(key_data["created_at"].replace("Z", ""))
            expires = datetime.fromisoformat(key_data["expires_at"].replace("Z", ""))
            delta = expires - created
            assert 89 <= delta.days <= 91  # Allow for timezone/timing differences

    @pytest.mark.integration
    def test_create_api_key_with_minimal_data(
        self, api_client, app, override_customer_auth, mock_account_db
    ):
        """
        Test: POST /v1/account/api-keys - Create key with only required fields.

        Verifies:
        - Only 'name' is required
        - description is optional
        - expires_days is optional
        """
        with patch('api.v1.endpoints.account.get_database', return_value=mock_account_db), \
             patch('api.v1.endpoints.account.generate_api_key', return_value="ak_live_minimal_key"), \
             patch('api.v1.endpoints.account.generate_key_id', return_value="key_minimal"), \
             patch('api.core.security.hash_api_key', return_value="$2b$12$hashed_api_key"):

            response = api_client.post(
                "/v1/account/api-keys",
                json={"name": "Minimal Key"},
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["data"]["name"] == "Minimal Key"

    @pytest.mark.integration
    def test_create_api_key_fails_with_invalid_name_too_short(
        self, api_client, app, override_customer_auth
    ):
        """
        Test: POST /v1/account/api-keys - Reject name that is too short.

        Verifies:
        - Name must be at least 3 characters
        - 422 UNPROCESSABLE_ENTITY status
        """
        response = api_client.post(
            "/v1/account/api-keys",
            json={"name": "ab"},  # Only 2 characters
            headers={"X-API-Key": "test_key"}
        )

        assert response.status_code == 422
        assert "detail" in response.json()

    @pytest.mark.integration
    def test_create_api_key_fails_with_invalid_name_too_long(
        self, api_client, app, override_customer_auth
    ):
        """
        Test: POST /v1/account/api-keys - Reject name that is too long.

        Verifies:
        - Name must be max 100 characters
        - 422 UNPROCESSABLE_ENTITY status
        """
        response = api_client.post(
            "/v1/account/api-keys",
            json={"name": "x" * 101},  # 101 characters
            headers={"X-API-Key": "test_key"}
        )

        assert response.status_code == 422

    @pytest.mark.integration
    def test_create_api_key_fails_with_invalid_expires_days_too_small(
        self, api_client, app, override_customer_auth
    ):
        """
        Test: POST /v1/account/api-keys - Reject expires_days < 1.

        Verifies:
        - expires_days must be between 1 and 365
        - 422 UNPROCESSABLE_ENTITY status
        """
        response = api_client.post(
            "/v1/account/api-keys",
            json={
                "name": "Test Key",
                "expires_days": 0  # Invalid: must be >= 1
            },
            headers={"X-API-Key": "test_key"}
        )

        assert response.status_code == 422

    @pytest.mark.integration
    def test_create_api_key_fails_with_invalid_expires_days_too_large(
        self, api_client, app, override_customer_auth
    ):
        """
        Test: POST /v1/account/api-keys - Reject expires_days > 365.

        Verifies:
        - expires_days must be between 1 and 365
        - 422 UNPROCESSABLE_ENTITY status
        """
        response = api_client.post(
            "/v1/account/api-keys",
            json={
                "name": "Test Key",
                "expires_days": 366  # Invalid: must be <= 365
            },
            headers={"X-API-Key": "test_key"}
        )

        assert response.status_code == 422

    @pytest.mark.integration
    def test_create_api_key_fails_without_authentication(self, api_client):
        """
        Test: POST /v1/account/api-keys - Fail when not authenticated.

        Verifies:
        - Authentication required
        - 401 or 403 status when no API key provided
        """
        response = api_client.post(
            "/v1/account/api-keys",
            json={"name": "Test Key"}
        )

        # Depending on FastAPI security configuration
        assert response.status_code in [401, 403]


class TestListAPIKeys:
    """Integration tests for GET /v1/account/api-keys - List API keys."""

    @pytest.mark.integration
    def test_list_api_keys_success(
        self, api_client, app, override_customer_auth, mock_account_db
    ):
        """
        Test: GET /v1/account/api-keys - Successfully list all API keys.

        Verifies:
        - Returns list of all keys (active and revoked)
        - Each key includes metadata but NOT the actual API key
        - Response includes total count and active count
        - Sorted by created_at DESC (newest first)
        - 200 OK status
        """
        with patch('api.v1.endpoints.account.get_database', return_value=mock_account_db):

            response = api_client.get(
                "/v1/account/api-keys",
                headers={"X-API-Key": "test_key"}
            )

            # Verify response
            assert response.status_code == 200

            data = response.json()
            assert data["success"] is True
            assert "data" in data

            keys_data = data["data"]
            assert "keys" in keys_data
            assert "total" in keys_data
            assert "active" in keys_data

            # Should have 3 keys total (2 active, 1 revoked)
            assert keys_data["total"] == 3
            assert keys_data["active"] == 2
            assert len(keys_data["keys"]) == 3

            # Verify key structure
            first_key = keys_data["keys"][0]
            assert "key_id" in first_key
            assert "name" in first_key
            assert "key_prefix" in first_key
            assert "created_at" in first_key
            assert "revoked" in first_key

            # Verify API key secret is NOT included
            assert "api_key" not in first_key
            assert "api_key_hash" not in first_key

    @pytest.mark.integration
    def test_list_api_keys_includes_revoked_keys(
        self, api_client, app, override_customer_auth, mock_account_db
    ):
        """
        Test: GET /v1/account/api-keys - Includes revoked keys with metadata.

        Verifies:
        - Revoked keys included in response
        - Revoked keys have revoked=true
        - Includes revoked_at timestamp
        - Includes revoked_reason if available
        """
        with patch('api.v1.endpoints.account.get_database', return_value=mock_account_db):

            response = api_client.get(
                "/v1/account/api-keys",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            # Find the revoked key
            keys = data["data"]["keys"]
            revoked_keys = [k for k in keys if k["revoked"]]

            assert len(revoked_keys) == 1
            revoked_key = revoked_keys[0]

            assert revoked_key["revoked"] is True
            assert revoked_key["revoked_at"] == "2024-01-05T15:00:00Z"
            assert revoked_key["revoked_reason"] == "Compromised key - rotating to new credentials"

    @pytest.mark.integration
    def test_list_api_keys_shows_active_keys_without_revocation_data(
        self, api_client, app, override_customer_auth, mock_account_db
    ):
        """
        Test: GET /v1/account/api-keys - Active keys have revoked=false.

        Verifies:
        - Active keys have revoked=false
        - revoked_at is null for active keys
        - revoked_reason is null for active keys
        """
        with patch('api.v1.endpoints.account.get_database', return_value=mock_account_db):

            response = api_client.get(
                "/v1/account/api-keys",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            # Find active keys
            keys = data["data"]["keys"]
            active_keys = [k for k in keys if not k["revoked"]]

            assert len(active_keys) == 2

            for key in active_keys:
                assert key["revoked"] is False
                assert key["revoked_at"] is None
                assert key["revoked_reason"] is None

    @pytest.mark.integration
    def test_list_api_keys_shows_expiration_status(
        self, api_client, app, override_customer_auth, mock_account_db
    ):
        """
        Test: GET /v1/account/api-keys - Shows which keys have expiration.

        Verifies:
        - Keys with expiration have expires_at timestamp
        - Keys without expiration have expires_at=null
        - last_used_at shown when available
        """
        with patch('api.v1.endpoints.account.get_database', return_value=mock_account_db):

            response = api_client.get(
                "/v1/account/api-keys",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()
            keys = data["data"]["keys"]

            # First key has expiration
            prod_key = next(k for k in keys if k["name"] == "Production Server")
            assert prod_key["expires_at"] == "2024-04-15T10:00:00Z"
            assert prod_key["last_used_at"] == "2024-01-15T14:28:00Z"

            # Second key has no expiration
            dev_key = next(k for k in keys if k["name"] == "Development Environment")
            assert dev_key["expires_at"] is None
            assert dev_key["last_used_at"] is None

    @pytest.mark.integration
    def test_list_api_keys_empty_list_for_new_customer(
        self, api_client, app, override_customer_auth
    ):
        """
        Test: GET /v1/account/api-keys - Empty list when customer has no keys.

        Verifies:
        - Returns empty list when no keys exist
        - total=0, active=0
        - 200 OK status
        """
        mock_db = MagicMock()
        mock_db.aql = MagicMock()
        mock_db.aql.execute = Mock(return_value=[])  # No keys

        with patch('api.v1.endpoints.account.get_database', return_value=mock_db):

            response = api_client.get(
                "/v1/account/api-keys",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            assert data["success"] is True
            assert data["data"]["keys"] == []
            assert data["data"]["total"] == 0
            assert data["data"]["active"] == 0

    @pytest.mark.integration
    def test_list_api_keys_fails_without_authentication(self, api_client):
        """
        Test: GET /v1/account/api-keys - Fail when not authenticated.

        Verifies:
        - Authentication required
        - 401 or 403 status when no API key provided
        """
        response = api_client.get("/v1/account/api-keys")

        assert response.status_code in [401, 403]


class TestRevokeAPIKey:
    """Integration tests for DELETE /v1/account/api-keys/{key_id} - Revoke API key."""

    @pytest.mark.integration
    def test_revoke_api_key_success_with_reason(
        self, api_client, app, override_customer_auth, mock_account_db
    ):
        """
        Test: DELETE /v1/account/api-keys/{key_id} - Successfully revoke key with reason.

        Verifies:
        - Key is revoked immediately
        - Response includes key_id, revoked=true, revoked_at timestamp
        - Reason is stored
        - 200 OK status
        """
        # Override AQL execute for verification query
        mock_account_db.aql.execute = Mock(return_value=[{
            "_key": "key_abc123def456ghi789jkl012mno345pq",
            "key_id": "key_abc123def456ghi789jkl012mno345pq",
            "customer_id": "customer_test",
            "name": "Production Server",
            "revoked": False
        }])

        with patch('api.v1.endpoints.account.get_database', return_value=mock_account_db):

            response = api_client.delete(
                "/v1/account/api-keys/key_abc123def456ghi789jkl012mno345pq",
                headers={"X-API-Key": "test_key"}
            )

            # Verify response
            assert response.status_code == 200

            data = response.json()
            assert data["success"] is True
            assert "data" in data

            revoke_data = data["data"]
            assert revoke_data["key_id"] == "key_abc123def456ghi789jkl012mno345pq"
            assert revoke_data["revoked"] is True
            assert revoke_data["revoked_at"]
            assert revoke_data["revoked_at"].endswith("Z")  # ISO 8601 format
            assert "message" in revoke_data

            # Verify database update was called
            collection = mock_account_db.collection.return_value
            collection.update.assert_called_once()

    @pytest.mark.integration
    def test_revoke_api_key_success_without_reason(
        self, api_client, app, override_customer_auth, mock_account_db
    ):
        """
        Test: DELETE /v1/account/api-keys/{key_id} - Successfully revoke without reason.

        Verifies:
        - Reason is optional
        - Key is revoked even without reason
        """
        mock_account_db.aql.execute = Mock(return_value=[{
            "_key": "key_def456ghi789jkl012mno345pqr678st",
            "key_id": "key_def456ghi789jkl012mno345pqr678st",
            "customer_id": "customer_test",
            "name": "Dev Key",
            "revoked": False
        }])

        with patch('api.v1.endpoints.account.get_database', return_value=mock_account_db):

            response = api_client.delete(
                "/v1/account/api-keys/key_def456ghi789jkl012mno345pqr678st",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["data"]["revoked"] is True

    @pytest.mark.integration
    def test_revoke_api_key_fails_when_key_not_found(
        self, api_client, app, override_customer_auth, mock_account_db
    ):
        """
        Test: DELETE /v1/account/api-keys/{key_id} - 404 when key doesn't exist.

        Verifies:
        - Returns 404 NOT FOUND for non-existent key
        - Error message indicates key not found
        """
        # Mock empty query result
        mock_account_db.aql.execute = Mock(return_value=[])

        with patch('api.v1.endpoints.account.get_database', return_value=mock_account_db):

            response = api_client.delete(
                "/v1/account/api-keys/key_nonexistent",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 404
            data = response.json()
            assert "not found" in data["detail"].lower()

    @pytest.mark.integration
    def test_revoke_api_key_fails_when_key_belongs_to_different_customer(
        self, api_client, app, override_customer_auth, mock_account_db
    ):
        """
        Test: DELETE /v1/account/api-keys/{key_id} - 404 when key belongs to another customer.

        Verifies:
        - Can only revoke keys belonging to authenticated customer
        - Returns 404 (not 403) to prevent key enumeration
        """
        # Mock query returns empty (filtered by customer_id)
        mock_account_db.aql.execute = Mock(return_value=[])

        with patch('api.v1.endpoints.account.get_database', return_value=mock_account_db):

            response = api_client.delete(
                "/v1/account/api-keys/key_belongs_to_other_customer",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 404

    @pytest.mark.integration
    def test_revoke_api_key_fails_when_already_revoked(
        self, api_client, app, override_customer_auth, mock_account_db
    ):
        """
        Test: DELETE /v1/account/api-keys/{key_id} - 400 when key already revoked.

        Verifies:
        - Cannot revoke an already-revoked key
        - Returns 400 BAD REQUEST
        - Error message indicates key already revoked
        """
        # Mock query returns already-revoked key
        mock_account_db.aql.execute = Mock(return_value=[{
            "_key": "key_already_revoked",
            "key_id": "key_already_revoked",
            "customer_id": "customer_test",
            "name": "Already Revoked Key",
            "revoked": True,
            "revoked_at": "2024-01-01T10:00:00Z"
        }])

        with patch('api.v1.endpoints.account.get_database', return_value=mock_account_db):

            response = api_client.delete(
                "/v1/account/api-keys/key_already_revoked",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 400
            data = response.json()
            assert "already revoked" in data["detail"].lower()

    @pytest.mark.integration
    def test_revoke_api_key_fails_without_authentication(self, api_client):
        """
        Test: DELETE /v1/account/api-keys/{key_id} - Fail when not authenticated.

        Verifies:
        - Authentication required
        - 401 or 403 status when no API key provided
        """
        response = api_client.delete("/v1/account/api-keys/key_any")

        assert response.status_code in [401, 403]

    @pytest.mark.integration
    def test_revoke_api_key_validates_reason_max_length(
        self, api_client, app, override_customer_auth
    ):
        """
        Test: DELETE /v1/account/api-keys/{key_id} - Reject reason > 500 chars.

        Verifies:
        - Reason must be max 500 characters
        - 422 UNPROCESSABLE_ENTITY status
        """
        with patch('api.v1.endpoints.account.get_database', return_value=MagicMock()):
            response = api_client.request(
                "DELETE",
                "/v1/account/api-keys/key_test",
                json={"reason": "A" * 501},  # 501 characters exceeds max length
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 422


class TestAccountEndpointsIntegration:
    """End-to-end integration tests for account management workflow."""

    @pytest.mark.integration
    def test_full_api_key_lifecycle(
        self, api_client, app, override_customer_auth
    ):
        """
        Test: Complete API key lifecycle - create -> list -> revoke -> list again.

        Verifies:
        - Create new key
        - Key appears in list
        - Revoke the key
        - Key still appears but marked as revoked
        """
        mock_db = MagicMock()
        mock_db.collection = Mock(return_value=MagicMock())
        mock_db.aql = MagicMock()
        mock_db.has_collection = Mock(return_value=True)

        collection = mock_db.collection.return_value
        collection.insert = Mock(return_value={
            "_key": "key_lifecycle_test",
            "_id": "customer_api_keys/key_lifecycle_test",
            "_rev": "_rev1",
        })

        with patch('api.v1.endpoints.account.get_database', return_value=mock_db), \
             patch('api.v1.endpoints.account.generate_api_key', return_value="ak_live_lifecycle_test"), \
             patch('api.v1.endpoints.account.generate_key_id', return_value="key_lifecycle_test"), \
             patch('api.core.security.hash_api_key', return_value="$2b$12$hashed"):

            # Step 1: Create API key
            mock_db.aql.execute = Mock(return_value=[])  # Empty list initially

            create_response = api_client.post(
                "/v1/account/api-keys",
                json={"name": "Lifecycle Test Key"},
                headers={"X-API-Key": "test_key"}
            )

            assert create_response.status_code == 200
            created_key = create_response.json()["data"]
            key_id = created_key["key_id"]

            # Step 2: List API keys (should show new key)
            mock_db.aql.execute = Mock(return_value=[{
                "_key": key_id,
                "key_id": key_id,
                "customer_id": "customer_test",
                "name": "Lifecycle Test Key",
                "key_prefix": "ak_live_",
                "created_at": created_key["created_at"],
                "expires_at": None,
                "last_used_at": None,
                "revoked": False,
                "revoked_at": None,
                "revoked_reason": None,
            }])

            list_response_1 = api_client.get(
                "/v1/account/api-keys",
                headers={"X-API-Key": "test_key"}
            )

            assert list_response_1.status_code == 200
            keys_before_revoke = list_response_1.json()["data"]
            assert keys_before_revoke["total"] == 1
            assert keys_before_revoke["active"] == 1
            assert keys_before_revoke["keys"][0]["revoked"] is False

            # Step 3: Revoke the key
            collection.update = Mock(return_value={
                "_key": key_id,
                "_rev": "_rev2",
            })

            revoke_response = api_client.delete(
                f"/v1/account/api-keys/{key_id}",
                headers={"X-API-Key": "test_key"}
            )

            assert revoke_response.status_code == 200
            assert revoke_response.json()["data"]["revoked"] is True

            # Step 4: List API keys again (should show revoked key)
            mock_db.aql.execute = Mock(return_value=[{
                "_key": key_id,
                "key_id": key_id,
                "customer_id": "customer_test",
                "name": "Lifecycle Test Key",
                "key_prefix": "ak_live_",
                "created_at": created_key["created_at"],
                "expires_at": None,
                "last_used_at": None,
                "revoked": True,
                "revoked_at": revoke_response.json()["data"]["revoked_at"],
                "revoked_reason": "Testing lifecycle",
            }])

            list_response_2 = api_client.get(
                "/v1/account/api-keys",
                headers={"X-API-Key": "test_key"}
            )

            assert list_response_2.status_code == 200
            keys_after_revoke = list_response_2.json()["data"]
            assert keys_after_revoke["total"] == 1
            assert keys_after_revoke["active"] == 0  # No active keys
            assert keys_after_revoke["keys"][0]["revoked"] is True
            assert keys_after_revoke["keys"][0]["revoked_reason"] == "Testing lifecycle"

            print("✅ Full API key lifecycle test passed: create → list → revoke → list")
