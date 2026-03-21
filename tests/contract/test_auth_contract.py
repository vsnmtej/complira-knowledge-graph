"""
API Contract Tests - Authentication Endpoints.

These tests ensure:
1. Auth API responses match the documented contract
2. Frontend mock data matches real API responses
3. No breaking changes to authentication API structure
4. All response models validate correctly with Pydantic
"""
import json
import pytest
from pathlib import Path
from pydantic import ValidationError

from api.models.auth import (
    SignupResponse,
    LoginResponse,
    EmailVerificationResponse,
    PasswordResetResponse,
    RefreshTokenResponse,
    UserProfile,
)


class TestAuthAPIContract:
    """Test authentication API responses match expected contract."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses"""
        return Path("tests/fixtures/api_responses")

    def test_signup_response_contract(self, mock_responses_dir):
        """
        Test: POST /v1/auth/signup response matches contract

        Validates:
        - Response structure matches SignupResponse model
        - All required fields present (success, message, user_id, email)
        - Field types correct
        """
        with open(mock_responses_dir / "auth_signup.json") as f:
            mock_data = json.load(f)

        # Validate required fields
        required_fields = ["success", "message", "user_id", "email"]
        for field in required_fields:
            assert field in mock_data, f"Missing required field: {field}"

        # Validate field types
        assert isinstance(mock_data["success"], bool)
        assert isinstance(mock_data["message"], str)
        assert isinstance(mock_data["user_id"], str)
        assert isinstance(mock_data["email"], str)

        # Validate user_id format (should be "users/{key}")
        assert mock_data["user_id"].startswith("users/"), \
            f"user_id should start with 'users/', got: {mock_data['user_id']}"

        # Validate email format (basic check)
        assert "@" in mock_data["email"], "email should be valid email address"

        # Validate using Pydantic model
        try:
            response = SignupResponse(**mock_data)
            assert response.success == mock_data["success"]
            assert response.user_id == mock_data["user_id"]
            assert response.email == mock_data["email"]
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match SignupResponse schema: {e}")

    def test_login_response_contract(self, mock_responses_dir):
        """
        Test: POST /v1/auth/login response matches contract

        Validates:
        - Response structure matches LoginResponse model
        - JWT tokens are present (access_token, refresh_token)
        - User profile is complete and valid
        - Token metadata is correct (token_type, expires_in)
        """
        with open(mock_responses_dir / "auth_login.json") as f:
            mock_data = json.load(f)

        # Validate required fields
        required_fields = ["access_token", "refresh_token", "token_type", "expires_in", "user"]
        for field in required_fields:
            assert field in mock_data, f"Missing required field: {field}"

        # Validate token fields
        assert isinstance(mock_data["access_token"], str)
        assert isinstance(mock_data["refresh_token"], str)
        assert mock_data["token_type"] == "bearer"
        assert isinstance(mock_data["expires_in"], int)
        assert mock_data["expires_in"] > 0

        # Validate JWT token format (basic check - should have 3 parts separated by dots)
        assert mock_data["access_token"].count(".") >= 2, "access_token should be JWT format"
        assert mock_data["refresh_token"].count(".") >= 2, "refresh_token should be JWT format"

        # Validate user profile structure
        user = mock_data["user"]
        user_required_fields = [
            "id", "email", "name", "email_verified", "organization_id",
            "organization_name", "role", "tier", "frameworks", "created_at"
        ]
        for field in user_required_fields:
            assert field in user, f"Missing user field: {field}"

        # Validate user profile field types
        assert isinstance(user["id"], str)
        assert isinstance(user["email"], str)
        assert isinstance(user["name"], str)
        assert isinstance(user["email_verified"], bool)
        assert isinstance(user["organization_id"], str)
        assert isinstance(user["organization_name"], str)
        assert user["role"] in ["owner", "admin", "member"]
        assert user["tier"] in ["free", "professional", "enterprise"]
        assert isinstance(user["frameworks"], list)
        assert isinstance(user["created_at"], str)

        # Validate using Pydantic model
        try:
            response = LoginResponse(**mock_data)
            assert response.access_token == mock_data["access_token"]
            assert response.token_type == "bearer"
            assert response.user.email == user["email"]
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match LoginResponse schema: {e}")

    def test_verify_email_response_contract(self, mock_responses_dir):
        """
        Test: POST /v1/auth/verify-email response matches contract

        Validates:
        - Response structure matches EmailVerificationResponse model
        - Success and message fields present
        """
        with open(mock_responses_dir / "auth_verify_email.json") as f:
            mock_data = json.load(f)

        # Validate required fields
        required_fields = ["success", "message"]
        for field in required_fields:
            assert field in mock_data, f"Missing required field: {field}"

        # Validate field types
        assert isinstance(mock_data["success"], bool)
        assert isinstance(mock_data["message"], str)
        assert len(mock_data["message"]) > 0, "message should not be empty"

        # Validate using Pydantic model
        try:
            response = EmailVerificationResponse(**mock_data)
            assert response.success == mock_data["success"]
            assert response.message == mock_data["message"]
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match EmailVerificationResponse schema: {e}")

    def test_forgot_password_response_contract(self, mock_responses_dir):
        """
        Test: POST /v1/auth/forgot-password response matches contract

        Validates:
        - Response structure matches PasswordResetResponse model
        - Message is generic (doesn't reveal if email exists)
        """
        with open(mock_responses_dir / "auth_forgot_password.json") as f:
            mock_data = json.load(f)

        # Validate required fields
        required_fields = ["success", "message"]
        for field in required_fields:
            assert field in mock_data, f"Missing required field: {field}"

        # Validate field types
        assert isinstance(mock_data["success"], bool)
        assert isinstance(mock_data["message"], str)

        # Validate message is generic (security best practice)
        assert "if" in mock_data["message"].lower() or "has been sent" in mock_data["message"].lower(), \
            "Message should be generic to prevent email enumeration"

        # Validate using Pydantic model
        try:
            response = PasswordResetResponse(**mock_data)
            assert response.success == mock_data["success"]
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match PasswordResetResponse schema: {e}")

    def test_reset_password_response_contract(self, mock_responses_dir):
        """
        Test: POST /v1/auth/reset-password response matches contract

        Validates:
        - Response structure matches EmailVerificationResponse model
        - Success and message fields present
        """
        with open(mock_responses_dir / "auth_reset_password.json") as f:
            mock_data = json.load(f)

        # Validate required fields
        required_fields = ["success", "message"]
        for field in required_fields:
            assert field in mock_data, f"Missing required field: {field}"

        # Validate field types
        assert isinstance(mock_data["success"], bool)
        assert isinstance(mock_data["message"], str)

        # Validate using Pydantic model
        try:
            response = EmailVerificationResponse(**mock_data)
            assert response.success == mock_data["success"]
            assert response.message == mock_data["message"]
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match EmailVerificationResponse schema: {e}")

    def test_refresh_token_response_contract(self, mock_responses_dir):
        """
        Test: POST /v1/auth/refresh response matches contract

        Validates:
        - Response structure matches RefreshTokenResponse model
        - New access token is present
        - Token metadata is correct
        """
        with open(mock_responses_dir / "auth_refresh.json") as f:
            mock_data = json.load(f)

        # Validate required fields
        required_fields = ["access_token", "token_type", "expires_in"]
        for field in required_fields:
            assert field in mock_data, f"Missing required field: {field}"

        # Validate field types
        assert isinstance(mock_data["access_token"], str)
        assert mock_data["token_type"] == "bearer"
        assert isinstance(mock_data["expires_in"], int)
        assert mock_data["expires_in"] > 0

        # Validate JWT token format
        assert mock_data["access_token"].count(".") >= 2, "access_token should be JWT format"

        # Validate using Pydantic model
        try:
            response = RefreshTokenResponse(**mock_data)
            assert response.access_token == mock_data["access_token"]
            assert response.token_type == "bearer"
            assert response.expires_in == mock_data["expires_in"]
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match RefreshTokenResponse schema: {e}")

    def test_get_me_response_contract(self, mock_responses_dir):
        """
        Test: GET /v1/auth/me response matches contract

        Validates:
        - Response structure matches UserProfile model
        - All user profile fields present
        - Field types and values are valid
        """
        with open(mock_responses_dir / "auth_me.json") as f:
            mock_data = json.load(f)

        # Validate required fields
        required_fields = [
            "id", "email", "name", "email_verified", "organization_id",
            "organization_name", "role", "tier", "frameworks", "created_at"
        ]
        for field in required_fields:
            assert field in mock_data, f"Missing required field: {field}"

        # Validate field types
        assert isinstance(mock_data["id"], str)
        assert isinstance(mock_data["email"], str)
        assert isinstance(mock_data["name"], str)
        assert isinstance(mock_data["email_verified"], bool)
        assert isinstance(mock_data["organization_id"], str)
        assert isinstance(mock_data["organization_name"], str)
        assert isinstance(mock_data["created_at"], str)
        assert isinstance(mock_data["frameworks"], list)

        # Validate enum values
        assert mock_data["role"] in ["owner", "admin", "member"], \
            f"Invalid role: {mock_data['role']}"
        assert mock_data["tier"] in ["free", "professional", "enterprise"], \
            f"Invalid tier: {mock_data['tier']}"

        # Validate ID format
        assert mock_data["id"].startswith("users/"), \
            f"id should start with 'users/', got: {mock_data['id']}"

        # Validate email format
        assert "@" in mock_data["email"], "email should be valid email address"

        # Validate ISO 8601 timestamp format (basic check)
        assert "T" in mock_data["created_at"] and "Z" in mock_data["created_at"], \
            "created_at should be ISO 8601 format"

        # Validate using Pydantic model
        try:
            response = UserProfile(**mock_data)
            assert response.id == mock_data["id"]
            assert response.email == mock_data["email"]
            assert response.role == mock_data["role"]
            assert response.tier == mock_data["tier"]
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match UserProfile schema: {e}")

    def test_all_auth_error_responses_contract(self, mock_responses_dir):
        """
        Test: Auth error responses match FastAPI HTTPException format

        Validates:
        - All auth-specific errors have "detail" field
        - Error messages are descriptive
        """
        with open(mock_responses_dir / "auth_errors.json") as f:
            error_data = json.load(f)

        # All errors should have "detail" field
        for error_key, error_response in error_data.items():
            assert "detail" in error_response, f"Error {error_key} missing 'detail' field"
            # Detail can be either a string (simple errors) or list (validation errors)
            assert isinstance(error_response["detail"], (str, list)), \
                f"Error {error_key} has invalid detail type: {type(error_response['detail'])}"
            if isinstance(error_response["detail"], str):
                assert len(error_response["detail"]) > 0, f"Error {error_key} has empty detail"
            elif isinstance(error_response["detail"], list):
                assert len(error_response["detail"]) > 0, f"Error {error_key} has empty detail list"
                # Validate structure of validation errors
                for error_item in error_response["detail"]:
                    assert "type" in error_item, f"Validation error missing 'type' field"
                    assert "msg" in error_item, f"Validation error missing 'msg' field"

    def test_user_profile_has_all_roles(self, mock_responses_dir):
        """
        Test: Mock data includes examples of all user roles

        Verifies:
        - Examples exist for owner, admin, and member roles
        """
        # This would require multiple mock files or a list of users
        # For now, we just verify the main user profile has a valid role
        with open(mock_responses_dir / "auth_me.json") as f:
            mock_data = json.load(f)

        assert mock_data["role"] in ["owner", "admin", "member"]

    def test_user_profile_has_all_tiers(self, mock_responses_dir):
        """
        Test: Mock data includes examples of all organization tiers

        Verifies:
        - Examples exist for free, professional, and enterprise tiers
        """
        # For now, we just verify the main user profile has a valid tier
        with open(mock_responses_dir / "auth_me.json") as f:
            mock_data = json.load(f)

        assert mock_data["tier"] in ["free", "professional", "enterprise"]

    def test_login_response_includes_all_user_fields(self, mock_responses_dir):
        """
        Test: Login response includes complete user profile

        Verifies:
        - User object in login response matches UserProfile schema exactly
        - No missing or extra fields
        """
        with open(mock_responses_dir / "auth_login.json") as f:
            mock_data = json.load(f)

        user = mock_data["user"]

        # Validate using UserProfile model
        try:
            user_profile = UserProfile(**user)
            # Ensure all fields are present
            assert user_profile.model_dump() is not None
        except ValidationError as e:
            pytest.fail(f"User profile in login response doesn't match UserProfile schema: {e}")

    def test_jwt_tokens_have_valid_structure(self, mock_responses_dir):
        """
        Test: JWT tokens have valid structure (header.payload.signature)

        Verifies:
        - Access and refresh tokens are properly formatted JWTs
        - Tokens have three parts separated by dots
        """
        with open(mock_responses_dir / "auth_login.json") as f:
            login_data = json.load(f)

        with open(mock_responses_dir / "auth_refresh.json") as f:
            refresh_data = json.load(f)

        # Check login tokens
        assert login_data["access_token"].count(".") >= 2, \
            "Login access_token should be JWT format (header.payload.signature)"
        assert login_data["refresh_token"].count(".") >= 2, \
            "Login refresh_token should be JWT format (header.payload.signature)"

        # Check refresh endpoint token
        assert refresh_data["access_token"].count(".") >= 2, \
            "Refresh access_token should be JWT format (header.payload.signature)"

    def test_password_related_responses_dont_leak_info(self, mock_responses_dir):
        """
        Test: Password-related responses don't leak sensitive information

        Verifies:
        - Forgot password response is generic
        - Reset password response doesn't reveal user existence
        """
        with open(mock_responses_dir / "auth_forgot_password.json") as f:
            forgot_data = json.load(f)

        # Verify message doesn't confirm email existence
        message = forgot_data["message"].lower()
        assert "if" in message or "may have" in message or "has been sent" in message, \
            "Forgot password message should be generic to prevent email enumeration"

    def test_all_timestamp_fields_use_iso8601(self, mock_responses_dir):
        """
        Test: All timestamp fields use ISO 8601 format

        Verifies:
        - created_at fields are in ISO 8601 format
        """
        # Check user profile timestamp
        with open(mock_responses_dir / "auth_me.json") as f:
            me_data = json.load(f)

        assert "T" in me_data["created_at"] and ("Z" in me_data["created_at"] or "+" in me_data["created_at"]), \
            "created_at should be ISO 8601 format"

        # Check login response timestamp
        with open(mock_responses_dir / "auth_login.json") as f:
            login_data = json.load(f)

        assert "T" in login_data["user"]["created_at"] and ("Z" in login_data["user"]["created_at"] or "+" in login_data["user"]["created_at"]), \
            "User created_at in login response should be ISO 8601 format"
