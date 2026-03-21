"""
API Contract Tests for Account Management Endpoints.

These tests ensure:
1. Backend API responses match the documented contract
2. Frontend mock data matches real API responses
3. No breaking changes to API structure
4. Response models validate correctly with Pydantic
"""

import json
import pytest
from pathlib import Path
from pydantic import ValidationError

from api.models.responses.account import (
    CreateAPIKeyResponse,
    ListAPIKeysResponse,
    APIKeyResponse,
    RevokeAPIKeyResponse,
)
from api.models.responses import APIResponse


class TestAccountContractCreateAPIKey:
    """Contract tests for POST /v1/account/api-keys - Create API key."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses."""
        return Path("tests/fixtures/api_responses")

    def test_create_api_key_response_contract(self, mock_responses_dir):
        """
        Test: POST /v1/account/api-keys response matches contract.

        Validates:
        - Response structure matches APIResponse[CreateAPIKeyResponse]
        - All required fields present
        - Field types correct
        - API key format is valid
        """
        with open(mock_responses_dir / "account_create_api_key.json") as f:
            mock_data = json.load(f)

        # Validate outer APIResponse wrapper
        assert "success" in mock_data
        assert "data" in mock_data
        assert "metadata" in mock_data

        # Validate CreateAPIKeyResponse data
        data = mock_data["data"]
        required_fields = ["key_id", "name", "api_key", "created_at", "warning"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Validate field types
        assert isinstance(data["key_id"], str)
        assert isinstance(data["name"], str)
        assert isinstance(data["api_key"], str)
        assert isinstance(data["created_at"], str)
        assert isinstance(data["warning"], str)

        # Validate API key format
        assert data["api_key"].startswith("ak_"), "API key should start with 'ak_'"
        assert len(data["api_key"]) >= 40, "API key should be at least 40 characters"

        # Validate key_id format
        assert data["key_id"].startswith("key_"), "Key ID should start with 'key_'"

        # Validate ISO 8601 timestamp format
        assert data["created_at"].endswith("Z"), "Timestamp should be in ISO 8601 format with Z suffix"

        # Validate expires_at if present
        if "expires_at" in data and data["expires_at"] is not None:
            assert data["expires_at"].endswith("Z"), "Expiration should be ISO 8601 with Z suffix"

        # Validate using Pydantic model
        try:
            response = CreateAPIKeyResponse(**data)
            assert response.key_id == data["key_id"]
            assert response.name == data["name"]
            assert response.api_key == data["api_key"]
            assert "Save this API key securely" in response.warning
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match CreateAPIKeyResponse schema: {e}")

    def test_create_api_key_with_expiration_response_contract(self, mock_responses_dir):
        """
        Test: POST /v1/account/api-keys with expiration response matches contract.

        Validates:
        - expires_at field is present and valid when set
        - expires_at is ISO 8601 timestamp
        """
        # This test uses the same mock file but validates expiration handling
        with open(mock_responses_dir / "account_create_api_key.json") as f:
            mock_data = json.load(f)

        data = mock_data["data"]

        # If expires_at is set, validate it
        if data.get("expires_at"):
            assert isinstance(data["expires_at"], str)
            assert data["expires_at"].endswith("Z")

            # Validate using Pydantic
            try:
                response = CreateAPIKeyResponse(**data)
                assert response.expires_at == data["expires_at"]
            except ValidationError as e:
                pytest.fail(f"Expiration validation failed: {e}")

    def test_create_api_key_metadata_structure(self, mock_responses_dir):
        """
        Test: POST /v1/account/api-keys metadata includes cache_hit and execution_time_ms.

        Validates:
        - metadata field present
        - cache_hit is boolean
        - execution_time_ms is number
        """
        with open(mock_responses_dir / "account_create_api_key.json") as f:
            mock_data = json.load(f)

        assert "metadata" in mock_data
        metadata = mock_data["metadata"]

        assert "cache_hit" in metadata
        assert "execution_time_ms" in metadata

        assert isinstance(metadata["cache_hit"], bool)
        assert isinstance(metadata["execution_time_ms"], (int, float))
        assert metadata["cache_hit"] is False  # Create operations are never cached


class TestAccountContractListAPIKeys:
    """Contract tests for GET /v1/account/api-keys - List API keys."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses."""
        return Path("tests/fixtures/api_responses")

    def test_list_api_keys_response_contract(self, mock_responses_dir):
        """
        Test: GET /v1/account/api-keys response matches contract.

        Validates:
        - Response structure matches APIResponse[ListAPIKeysResponse]
        - Contains keys array, total count, active count
        - Each key matches APIKeyResponse schema
        """
        with open(mock_responses_dir / "account_list_api_keys.json") as f:
            mock_data = json.load(f)

        # Validate outer APIResponse wrapper
        assert "success" in mock_data
        assert "data" in mock_data
        assert "metadata" in mock_data

        # Validate ListAPIKeysResponse data
        data = mock_data["data"]
        required_fields = ["keys", "total", "active"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Validate field types
        assert isinstance(data["keys"], list)
        assert isinstance(data["total"], int)
        assert isinstance(data["active"], int)

        # Validate counts are consistent
        assert data["total"] >= data["active"], "Total should be >= active"
        assert data["total"] == len(data["keys"]), "Total should match keys array length"

        # Validate using Pydantic model
        try:
            response = ListAPIKeysResponse(**data)
            assert response.total == data["total"]
            assert response.active == data["active"]
            assert len(response.keys) == len(data["keys"])
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match ListAPIKeysResponse schema: {e}")

    def test_list_api_keys_individual_key_structure(self, mock_responses_dir):
        """
        Test: Each key in GET /v1/account/api-keys matches APIKeyResponse schema.

        Validates:
        - All required fields present in each key
        - Field types correct
        - API key secret NOT included
        """
        with open(mock_responses_dir / "account_list_api_keys.json") as f:
            mock_data = json.load(f)

        keys = mock_data["data"]["keys"]
        assert len(keys) > 0, "Mock should have at least one key"

        for key in keys:
            required_fields = [
                "key_id", "name", "key_prefix", "created_at", "revoked"
            ]
            for field in required_fields:
                assert field in key, f"Missing field {field} in key"

            # Validate types
            assert isinstance(key["key_id"], str)
            assert isinstance(key["name"], str)
            assert isinstance(key["key_prefix"], str)
            assert isinstance(key["created_at"], str)
            assert isinstance(key["revoked"], bool)

            # Validate key prefix format
            assert key["key_prefix"].startswith("ak_"), "Key prefix should start with 'ak_'"

            # Validate timestamps
            assert key["created_at"].endswith("Z"), "Created timestamp should end with Z"

            if key.get("expires_at"):
                assert key["expires_at"].endswith("Z"), "Expiration timestamp should end with Z"

            if key.get("last_used_at"):
                assert key["last_used_at"].endswith("Z"), "Last used timestamp should end with Z"

            # IMPORTANT: Verify API key secret is NEVER included
            assert "api_key" not in key, "API key secret should NEVER be in list response"
            assert "api_key_hash" not in key, "API key hash should NEVER be in list response"

            # Validate using Pydantic model
            try:
                api_key_response = APIKeyResponse(**key)
                assert api_key_response.key_id == key["key_id"]
                assert api_key_response.revoked == key["revoked"]
            except ValidationError as e:
                pytest.fail(f"Key doesn't match APIKeyResponse schema: {e}")

    def test_list_api_keys_includes_active_and_revoked(self, mock_responses_dir):
        """
        Test: GET /v1/account/api-keys includes both active and revoked keys.

        Validates:
        - Mock data includes at least one active key
        - Mock data includes at least one revoked key
        - Revoked keys have revoked_at and revoked_reason
        - Active keys have revoked=false
        """
        with open(mock_responses_dir / "account_list_api_keys.json") as f:
            mock_data = json.load(f)

        keys = mock_data["data"]["keys"]

        active_keys = [k for k in keys if not k["revoked"]]
        revoked_keys = [k for k in keys if k["revoked"]]

        # Should have both types for comprehensive testing
        assert len(active_keys) > 0, "Mock should include at least one active key"
        assert len(revoked_keys) > 0, "Mock should include at least one revoked key"

        # Validate active keys
        for key in active_keys:
            assert key["revoked"] is False
            assert key["revoked_at"] is None
            assert key["revoked_reason"] is None

        # Validate revoked keys
        for key in revoked_keys:
            assert key["revoked"] is True
            assert key["revoked_at"] is not None
            assert key["revoked_at"].endswith("Z")
            # revoked_reason is optional but should be present in mock for testing

    def test_list_api_keys_metadata_structure(self, mock_responses_dir):
        """
        Test: GET /v1/account/api-keys metadata structure.

        Validates:
        - metadata includes cache_hit and execution_time_ms
        """
        with open(mock_responses_dir / "account_list_api_keys.json") as f:
            mock_data = json.load(f)

        assert "metadata" in mock_data
        metadata = mock_data["metadata"]

        assert "cache_hit" in metadata
        assert "execution_time_ms" in metadata

        assert isinstance(metadata["cache_hit"], bool)
        assert isinstance(metadata["execution_time_ms"], (int, float))


class TestAccountContractRevokeAPIKey:
    """Contract tests for DELETE /v1/account/api-keys/{key_id} - Revoke API key."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses."""
        return Path("tests/fixtures/api_responses")

    def test_revoke_api_key_response_contract(self, mock_responses_dir):
        """
        Test: DELETE /v1/account/api-keys/{key_id} response matches contract.

        Validates:
        - Response structure matches APIResponse[RevokeAPIKeyResponse]
        - All required fields present
        - Field types correct
        - revoked is always true in response
        """
        with open(mock_responses_dir / "account_revoke_api_key.json") as f:
            mock_data = json.load(f)

        # Validate outer APIResponse wrapper
        assert "success" in mock_data
        assert "data" in mock_data
        assert "metadata" in mock_data

        # Validate RevokeAPIKeyResponse data
        data = mock_data["data"]
        required_fields = ["key_id", "revoked", "revoked_at", "message"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Validate field types
        assert isinstance(data["key_id"], str)
        assert isinstance(data["revoked"], bool)
        assert isinstance(data["revoked_at"], str)
        assert isinstance(data["message"], str)

        # Validate values
        assert data["revoked"] is True, "Revoked should always be true in response"
        assert data["revoked_at"].endswith("Z"), "Revoked timestamp should end with Z"
        assert len(data["message"]) > 0, "Message should not be empty"

        # Validate using Pydantic model
        try:
            response = RevokeAPIKeyResponse(**data)
            assert response.key_id == data["key_id"]
            assert response.revoked is True
            assert response.revoked_at == data["revoked_at"]
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match RevokeAPIKeyResponse schema: {e}")

    def test_revoke_api_key_message_content(self, mock_responses_dir):
        """
        Test: DELETE /v1/account/api-keys/{key_id} message is informative.

        Validates:
        - Message indicates key was revoked
        - Message is user-friendly
        """
        with open(mock_responses_dir / "account_revoke_api_key.json") as f:
            mock_data = json.load(f)

        data = mock_data["data"]
        message = data["message"]

        # Message should indicate revocation
        assert "revoke" in message.lower() or "deactivate" in message.lower()
        assert len(message) > 10, "Message should be meaningful"

    def test_revoke_api_key_metadata_structure(self, mock_responses_dir):
        """
        Test: DELETE /v1/account/api-keys/{key_id} metadata structure.

        Validates:
        - metadata includes cache_hit and execution_time_ms
        - cache_hit is false for revoke operations
        """
        with open(mock_responses_dir / "account_revoke_api_key.json") as f:
            mock_data = json.load(f)

        assert "metadata" in mock_data
        metadata = mock_data["metadata"]

        assert "cache_hit" in metadata
        assert "execution_time_ms" in metadata

        assert isinstance(metadata["cache_hit"], bool)
        assert isinstance(metadata["execution_time_ms"], (int, float))
        assert metadata["cache_hit"] is False  # Revoke operations are never cached


class TestAccountContractKeyPrefixFormats:
    """Tests for API key prefix format validation."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses."""
        return Path("tests/fixtures/api_responses")

    def test_api_key_prefix_formats_are_consistent(self, mock_responses_dir):
        """
        Test: All mock responses use consistent API key prefix format.

        Validates:
        - Create response: api_key starts with 'ak_'
        - List response: key_prefix values start with 'ak_'
        - Prefixes indicate environment (ak_live_, ak_test_)
        """
        # Check create response
        with open(mock_responses_dir / "account_create_api_key.json") as f:
            create_data = json.load(f)

        api_key = create_data["data"]["api_key"]
        assert api_key.startswith("ak_"), "Created API key should start with 'ak_'"
        assert api_key.startswith("ak_live_") or api_key.startswith("ak_test_"), \
            "API key should indicate environment (live or test)"

        # Check list response
        with open(mock_responses_dir / "account_list_api_keys.json") as f:
            list_data = json.load(f)

        for key in list_data["data"]["keys"]:
            prefix = key["key_prefix"]
            assert prefix.startswith("ak_"), f"Key prefix should start with 'ak_': {prefix}"


class TestAccountContractTimestampFormats:
    """Tests for timestamp format validation across all account endpoints."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses."""
        return Path("tests/fixtures/api_responses")

    def test_all_timestamps_use_iso8601_with_z_suffix(self, mock_responses_dir):
        """
        Test: All timestamps across account endpoints use ISO 8601 with Z suffix.

        Validates:
        - created_at timestamps
        - expires_at timestamps
        - revoked_at timestamps
        - last_used_at timestamps
        """
        # Check create response
        with open(mock_responses_dir / "account_create_api_key.json") as f:
            create_data = json.load(f)

        assert create_data["data"]["created_at"].endswith("Z")
        if create_data["data"].get("expires_at"):
            assert create_data["data"]["expires_at"].endswith("Z")

        # Check list response
        with open(mock_responses_dir / "account_list_api_keys.json") as f:
            list_data = json.load(f)

        for key in list_data["data"]["keys"]:
            assert key["created_at"].endswith("Z")

            if key.get("expires_at"):
                assert key["expires_at"].endswith("Z")

            if key.get("last_used_at"):
                assert key["last_used_at"].endswith("Z")

            if key.get("revoked_at"):
                assert key["revoked_at"].endswith("Z")

        # Check revoke response
        with open(mock_responses_dir / "account_revoke_api_key.json") as f:
            revoke_data = json.load(f)

        assert revoke_data["data"]["revoked_at"].endswith("Z")


class TestAccountContractErrorResponses:
    """Tests for error response contract validation."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses."""
        return Path("tests/fixtures/api_responses")

    def test_error_responses_have_detail_field(self, mock_responses_dir):
        """
        Test: Error responses follow FastAPI HTTPException format.

        Validates:
        - All errors have "detail" field
        - detail is a string
        """
        # Account endpoints should use the general errors.json or have their own
        with open(mock_responses_dir / "errors.json") as f:
            error_data = json.load(f)

        # Check account-related errors if they exist
        account_errors = {
            k: v for k, v in error_data.items()
            if "api" in k.lower() or "key" in k.lower() or "account" in k.lower()
        }

        for error_key, error_response in account_errors.items():
            assert "detail" in error_response, f"Error {error_key} missing 'detail' field"
            assert isinstance(error_response["detail"], str)


class TestAccountContractBackwardCompatibility:
    """Tests to ensure no breaking changes to existing contracts."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses."""
        return Path("tests/fixtures/api_responses")

    def test_create_api_key_required_fields_not_removed(self, mock_responses_dir):
        """
        Test: CreateAPIKeyResponse required fields are never removed.

        This test will fail if someone removes required fields,
        preventing breaking changes to the API contract.
        """
        with open(mock_responses_dir / "account_create_api_key.json") as f:
            mock_data = json.load(f)

        data = mock_data["data"]

        # These fields MUST always be present
        mandatory_fields = ["key_id", "name", "api_key", "created_at"]

        for field in mandatory_fields:
            assert field in data, \
                f"Breaking change detected: Required field '{field}' missing from CreateAPIKeyResponse"

    def test_list_api_keys_required_fields_not_removed(self, mock_responses_dir):
        """
        Test: ListAPIKeysResponse required fields are never removed.

        Prevents breaking changes to list endpoint contract.
        """
        with open(mock_responses_dir / "account_list_api_keys.json") as f:
            mock_data = json.load(f)

        data = mock_data["data"]

        # These fields MUST always be present
        mandatory_fields = ["keys", "total", "active"]

        for field in mandatory_fields:
            assert field in data, \
                f"Breaking change detected: Required field '{field}' missing from ListAPIKeysResponse"

        # Each key must have these fields
        if len(data["keys"]) > 0:
            key_mandatory_fields = ["key_id", "name", "key_prefix", "created_at", "revoked"]

            for field in key_mandatory_fields:
                assert field in data["keys"][0], \
                    f"Breaking change detected: Required field '{field}' missing from APIKeyResponse"

    def test_revoke_api_key_required_fields_not_removed(self, mock_responses_dir):
        """
        Test: RevokeAPIKeyResponse required fields are never removed.

        Prevents breaking changes to revoke endpoint contract.
        """
        with open(mock_responses_dir / "account_revoke_api_key.json") as f:
            mock_data = json.load(f)

        data = mock_data["data"]

        # These fields MUST always be present
        mandatory_fields = ["key_id", "revoked", "revoked_at"]

        for field in mandatory_fields:
            assert field in data, \
                f"Breaking change detected: Required field '{field}' missing from RevokeAPIKeyResponse"
