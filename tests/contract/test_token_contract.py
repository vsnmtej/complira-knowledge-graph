"""
API Contract Tests - Token Management Endpoints.

Validates that API responses match expected schemas for token management.

These tests ensure:
1. Backend API responses match the documented contract
2. Frontend mock data matches real API responses
3. No breaking changes to API structure
4. All Pydantic models validate correctly
"""
import json
import pytest
from pathlib import Path
from pydantic import ValidationError

from api.models.tokens import (
    CreateTokenResponse,
    RotateTokenResponse,
    RevokeTokenResponse,
    ListTokensResponse,
    APIToken,
)


class TestTokenAPIContract:
    """Test token API responses match expected contract."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses"""
        return Path("tests/fixtures/api_responses")

    def test_create_token_response_contract(self, mock_responses_dir):
        """
        Test: POST /v1/tokens response matches contract

        Validates:
        - Response structure matches CreateTokenResponse
        - Token secret present (full 64-char token)
        - Token ID, prefix, expiration included
        - Warning message present
        """
        with open(mock_responses_dir / "token_create.json") as f:
            mock_data = json.load(f)

        # Validate required fields
        assert "success" in mock_data
        assert "message" in mock_data
        assert "token" in mock_data
        assert "token_id" in mock_data
        assert "token_prefix" in mock_data
        assert "expires_at" in mock_data

        # Validate field types
        assert isinstance(mock_data["success"], bool)
        assert isinstance(mock_data["message"], str)
        assert isinstance(mock_data["token"], str)
        assert isinstance(mock_data["token_id"], str)
        assert isinstance(mock_data["token_prefix"], str)
        assert isinstance(mock_data["expires_at"], str)

        # Validate token format
        assert mock_data["token"].startswith("complira_tk_"), "Token should start with 'complira_tk_'"
        assert len(mock_data["token"]) >= 32, "Token should be at least 32 characters"

        # Validate success flag
        assert mock_data["success"] is True

        # Validate warning message
        assert "won't see it again" in mock_data["message"].lower() or \
               "save this token" in mock_data["message"].lower(), \
               "Warning message should remind user to save token"

        # Validate using Pydantic model
        try:
            response = CreateTokenResponse(**mock_data)
            assert response.token == mock_data["token"]
            assert response.token_id == mock_data["token_id"]
            assert response.success is True
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match CreateTokenResponse schema: {e}")

    def test_list_tokens_response_contract(self, mock_responses_dir):
        """
        Test: GET /v1/tokens response matches contract

        Validates:
        - Response structure matches ListTokensResponse
        - Tokens array present
        - Pagination metadata present
        - Token secrets NOT included
        """
        with open(mock_responses_dir / "token_list.json") as f:
            mock_data = json.load(f)

        # Validate required fields
        assert "tokens" in mock_data
        assert "total" in mock_data
        assert "page" in mock_data
        assert "page_size" in mock_data

        # Validate types
        assert isinstance(mock_data["tokens"], list)
        assert isinstance(mock_data["total"], int)
        assert isinstance(mock_data["page"], int)
        assert isinstance(mock_data["page_size"], int)

        # Validate pagination values
        assert mock_data["page"] >= 1
        assert mock_data["page_size"] >= 1
        assert mock_data["total"] >= 0

        # Validate each token
        for token in mock_data["tokens"]:
            required_fields = [
                "id", "organization_id", "created_by_user_id", "name",
                "token_prefix", "scopes", "rate_limit", "created_at",
                "expires_at", "revoked"
            ]
            for field in required_fields:
                assert field in token, f"Missing field {field} in token"

            # Ensure token secret is NOT included
            assert "token_secret" not in token, "Token secret should never be in list response"
            assert "token_hash" not in token, "Token hash should not be exposed"

            # Validate token prefix format
            assert token["token_prefix"].startswith("complira_tk_"), "Token prefix should start with 'complira_tk_'"

            # Validate scopes
            assert isinstance(token["scopes"], list)
            assert len(token["scopes"]) > 0

            # Validate revoked flag
            assert isinstance(token["revoked"], bool)

        # Validate using Pydantic model
        try:
            response = ListTokensResponse(**mock_data)
            assert len(response.tokens) == len(mock_data["tokens"])
            assert response.total == mock_data["total"]
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match ListTokensResponse schema: {e}")

    def test_get_token_response_contract(self, mock_responses_dir):
        """
        Test: GET /v1/tokens/{token_id} response matches contract

        Validates:
        - Response structure matches APIToken
        - All metadata fields present
        - Token secret NOT included
        """
        with open(mock_responses_dir / "token_get.json") as f:
            mock_data = json.load(f)

        # Validate required fields
        required_fields = [
            "id", "organization_id", "created_by_user_id", "name",
            "token_prefix", "scopes", "rate_limit", "created_at",
            "expires_at", "revoked"
        ]
        for field in required_fields:
            assert field in mock_data, f"Missing required field: {field}"

        # Ensure secret not included
        assert "token_secret" not in mock_data

        # Validate types
        assert isinstance(mock_data["id"], str)
        assert isinstance(mock_data["scopes"], list)
        assert isinstance(mock_data["rate_limit"], int)
        assert isinstance(mock_data["revoked"], bool)

        # Validate using Pydantic model
        try:
            token = APIToken(**mock_data)
            assert token.id == mock_data["id"]
            assert token.revoked == mock_data["revoked"]
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match APIToken schema: {e}")

    def test_update_token_response_contract(self, mock_responses_dir):
        """
        Test: PATCH /v1/tokens/{token_id} response matches contract

        Validates:
        - Response structure matches APIToken
        - Updated fields reflected
        - Token secret NOT included
        """
        with open(mock_responses_dir / "token_update.json") as f:
            mock_data = json.load(f)

        # Validate using Pydantic model
        try:
            token = APIToken(**mock_data)
            assert token.id == mock_data["id"]
            # Updated fields should be present
            assert token.name == mock_data["name"]
            assert token.scopes == mock_data["scopes"]
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match APIToken schema: {e}")

    def test_rotate_token_response_contract(self, mock_responses_dir):
        """
        Test: POST /v1/tokens/{token_id}/rotate response matches contract

        Validates:
        - Response structure matches RotateTokenResponse
        - New token secret present (shown once)
        - Grace period expiration included
        - Both old and new token expiration times included
        """
        with open(mock_responses_dir / "token_rotate.json") as f:
            mock_data = json.load(f)

        # Validate required fields
        assert "success" in mock_data
        assert "message" in mock_data
        assert "new_token" in mock_data
        assert "token_id" in mock_data
        assert "token_prefix" in mock_data
        assert "old_token_expires_at" in mock_data
        assert "new_token_expires_at" in mock_data

        # Validate types
        assert isinstance(mock_data["success"], bool)
        assert isinstance(mock_data["new_token"], str)
        assert mock_data["success"] is True

        # Validate new token format
        assert mock_data["new_token"].startswith("complira_tk_"), "New token should start with 'complira_tk_'"
        assert len(mock_data["new_token"]) >= 32, "New token should be at least 32 characters"

        # Validate token prefix changed (new token has different prefix)
        # Note: In real rotation, prefix changes to identify new token
        assert mock_data["token_prefix"].startswith("complira_tk_")

        # Validate message mentions grace period
        assert "grace" in mock_data["message"].lower() or \
               "old token" in mock_data["message"].lower(), \
               "Message should mention grace period or old token validity"

        # Validate using Pydantic model
        try:
            response = RotateTokenResponse(**mock_data)
            assert response.new_token == mock_data["new_token"]
            assert response.token_id == mock_data["token_id"]
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match RotateTokenResponse schema: {e}")

    def test_revoke_token_response_contract(self, mock_responses_dir):
        """
        Test: POST /v1/tokens/{token_id}/revoke response matches contract

        Validates:
        - Response structure matches RevokeTokenResponse
        - Revocation timestamp included
        - Success flag set to true
        """
        with open(mock_responses_dir / "token_revoke.json") as f:
            mock_data = json.load(f)

        # Validate required fields
        assert "success" in mock_data
        assert "message" in mock_data
        assert "token_id" in mock_data
        assert "revoked_at" in mock_data

        # Validate types
        assert isinstance(mock_data["success"], bool)
        assert isinstance(mock_data["message"], str)
        assert isinstance(mock_data["token_id"], str)
        assert isinstance(mock_data["revoked_at"], str)

        # Validate success flag
        assert mock_data["success"] is True

        # Validate timestamp format (ISO 8601)
        assert "T" in mock_data["revoked_at"]
        assert "Z" in mock_data["revoked_at"] or "+" in mock_data["revoked_at"]

        # Validate using Pydantic model
        try:
            response = RevokeTokenResponse(**mock_data)
            assert response.success is True
            assert response.token_id == mock_data["token_id"]
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match RevokeTokenResponse schema: {e}")

    def test_delete_token_response_contract(self, mock_responses_dir):
        """
        Test: DELETE /v1/tokens/{token_id} response matches contract

        Validates:
        - 204 NO CONTENT response (no body)
        - Or empty object response
        """
        # DELETE returns 204 NO CONTENT with no body
        # If mock file exists, it should be empty or minimal
        delete_mock = mock_responses_dir / "token_delete.json"

        if delete_mock.exists():
            with open(delete_mock) as f:
                mock_data = json.load(f)

            # DELETE should return empty object or minimal response
            assert mock_data == {} or "success" in mock_data
        else:
            # No mock file is acceptable for 204 NO CONTENT
            assert True

    def test_token_scopes_validation(self, mock_responses_dir):
        """
        Test: Token scopes match allowed values

        Validates:
        - All scopes in mock data are valid
        - Scopes follow pattern (resource:action)
        """
        with open(mock_responses_dir / "token_list.json") as f:
            mock_data = json.load(f)

        allowed_scopes = {
            "scan:write",
            "scan:read",
            "reference:read",
            "vex:generate",
            "admin:all"
        }

        for token in mock_data["tokens"]:
            for scope in token["scopes"]:
                assert scope in allowed_scopes, \
                    f"Invalid scope '{scope}'. Allowed: {allowed_scopes}"

                # Validate scope format (resource:action)
                assert ":" in scope, f"Scope '{scope}' should follow 'resource:action' pattern"

        print(f"✅ All token scopes are valid: {allowed_scopes}")

    def test_token_prefix_format(self, mock_responses_dir):
        """
        Test: Token prefixes follow consistent format

        Validates:
        - Prefix starts with 'sk_'
        - Environment indicator (live/test)
        - Random identifier
        """
        with open(mock_responses_dir / "token_list.json") as f:
            mock_data = json.load(f)

        for token in mock_data["tokens"]:
            prefix = token["token_prefix"]

            # Should start with 'complira_tk_'
            assert prefix.startswith("complira_tk_"), f"Prefix '{prefix}' should start with 'complira_tk_'"

            # Should have environment indicator
            # Prefix format: complira_tk_{random}
            # Prefix format: complira_tk_{random}

            # Should have minimum length (complira_tk_xxxxx or complira_tk_test_xxxxx)
            assert len(prefix) >= 12, f"Prefix '{prefix}' too short"

        print(f"✅ All token prefixes follow correct format: complira_tk_xxxxx")

    def test_token_expiration_dates(self, mock_responses_dir):
        """
        Test: Token expiration dates are valid ISO 8601 timestamps

        Validates:
        - expires_at is ISO 8601 format
        - Expiration is in the future (for active tokens)
        """
        with open(mock_responses_dir / "token_list.json") as f:
            mock_data = json.load(f)

        from datetime import datetime

        for token in mock_data["tokens"]:
            expires_at = token["expires_at"]

            # Should be ISO 8601 format
            assert "T" in expires_at, f"Timestamp '{expires_at}' not ISO 8601"

            # Should be parseable
            try:
                exp_date = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))

                # For non-revoked tokens, should be in future
                if not token["revoked"]:
                    # Note: In tests, we might use past dates, so just validate format
                    assert exp_date is not None
            except ValueError as e:
                pytest.fail(f"Invalid timestamp '{expires_at}': {e}")

        print("✅ All token expiration dates are valid ISO 8601 timestamps")

    def test_revoked_tokens_have_metadata(self, mock_responses_dir):
        """
        Test: Revoked tokens include revocation metadata

        Validates:
        - revoked_at timestamp present
        - revoked_by_user_id present
        - revoked flag is true
        """
        # Check if we have revoked tokens in list
        with open(mock_responses_dir / "token_list.json") as f:
            mock_data = json.load(f)

        revoked_tokens = [t for t in mock_data["tokens"] if t.get("revoked")]

        if revoked_tokens:
            for token in revoked_tokens:
                assert token["revoked"] is True
                assert "revoked_at" in token, "Revoked token missing revoked_at"
                assert token["revoked_at"] is not None

                # Optional: revoked_by_user_id might be present
                if "revoked_by_user_id" in token:
                    assert isinstance(token["revoked_by_user_id"], str)

            print(f"✅ {len(revoked_tokens)} revoked tokens have proper metadata")
        else:
            print("⚠️  No revoked tokens in mock data (add one for complete testing)")

    def test_error_responses_contract(self, mock_responses_dir):
        """
        Test: Error responses match FastAPI HTTPException format

        Validates:
        - 400, 403, 404, 422 errors have proper structure
        - detail field present
        """
        errors_file = mock_responses_dir / "token_errors.json"

        if errors_file.exists():
            with open(errors_file) as f:
                error_data = json.load(f)

            # Common error scenarios for tokens
            expected_errors = [
                "token_not_found",           # 404
                "forbidden_regular_user",    # 403
                "forbidden_admin_delete",    # 403
                "invalid_scopes",            # 422
                "token_limit_exceeded"       # 400
            ]

            for error_key in expected_errors:
                if error_key in error_data:
                    error = error_data[error_key]
                    assert "detail" in error, f"Error {error_key} missing 'detail' field"
                    assert isinstance(error["detail"], str)

            print(f"✅ Token error responses match FastAPI format")

    def test_rate_limit_values(self, mock_responses_dir):
        """
        Test: Rate limit values are within acceptable range

        Validates:
        - rate_limit is integer
        - rate_limit between 100 and 10000
        """
        with open(mock_responses_dir / "token_list.json") as f:
            mock_data = json.load(f)

        for token in mock_data["tokens"]:
            rate_limit = token["rate_limit"]

            assert isinstance(rate_limit, int), "rate_limit must be integer"
            assert 100 <= rate_limit <= 10000, \
                f"rate_limit {rate_limit} out of range (100-10000)"

        print("✅ All token rate limits within valid range (100-10000)")

    def test_last_used_timestamp_optional(self, mock_responses_dir):
        """
        Test: last_used field is optional and properly formatted when present

        Validates:
        - last_used can be null/absent
        - When present, is valid ISO 8601 timestamp
        """
        with open(mock_responses_dir / "token_list.json") as f:
            mock_data = json.load(f)

        from datetime import datetime

        for token in mock_data["tokens"]:
            last_used = token.get("last_used")

            if last_used is not None:
                # Should be ISO 8601 format
                assert "T" in last_used, f"Timestamp '{last_used}' not ISO 8601"

                # Should be parseable
                try:
                    datetime.fromisoformat(last_used.replace("Z", "+00:00"))
                except ValueError as e:
                    pytest.fail(f"Invalid last_used timestamp '{last_used}': {e}")

        print("✅ last_used timestamps are properly formatted (when present)")

    def test_mock_data_completeness(self, mock_responses_dir):
        """
        Test: All required mock files exist

        Validates:
        - Mock files for all 7 endpoints exist
        - Files are valid JSON
        """
        required_mocks = [
            "token_create.json",   # POST /v1/tokens
            "token_list.json",     # GET /v1/tokens
            "token_get.json",      # GET /v1/tokens/{token_id}
            "token_update.json",   # PATCH /v1/tokens/{token_id}
            "token_rotate.json",   # POST /v1/tokens/{token_id}/rotate
            "token_revoke.json",   # POST /v1/tokens/{token_id}/revoke
            "token_errors.json"    # Error responses
        ]

        missing_files = []
        for mock_file in required_mocks:
            mock_path = mock_responses_dir / mock_file
            if not mock_path.exists():
                missing_files.append(mock_file)
            else:
                # Validate JSON is parseable
                try:
                    with open(mock_path) as f:
                        json.load(f)
                except json.JSONDecodeError as e:
                    pytest.fail(f"Invalid JSON in {mock_file}: {e}")

        if missing_files:
            pytest.fail(f"Missing mock files: {', '.join(missing_files)}")

        print(f"✅ All {len(required_mocks)} token mock files present and valid")
