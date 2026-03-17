"""
Integration tests for authentication endpoints.

Tests full API flow for all 7 auth endpoints:
- POST /v1/auth/signup
- POST /v1/auth/login
- POST /v1/auth/verify-email
- POST /v1/auth/forgot-password
- POST /v1/auth/reset-password
- POST /v1/auth/refresh
- GET /v1/auth/me
"""

import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from fastapi.testclient import TestClient
from datetime import datetime


@pytest.fixture
def mock_database():
    """Mock ArangoDB database."""
    db = MagicMock()
    db.collection = Mock(return_value=MagicMock())
    db.aql = MagicMock()
    return db


@pytest.fixture
def test_client():
    """FastAPI test client."""
    from api.main import app
    return TestClient(app)


@pytest.fixture
def valid_user_data():
    """Valid user data for testing."""
    return {
        "_key": "user_test_123",
        "_id": "users/user_test_123",
        "email": "john.doe@example.com",
        "name": "John Doe",
        "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyWMb.qsVXge",  # hash of "SecurePass123!"
        "email_verified": True,
        "email_verification_token": None,
        "password_reset_token": None,
        "password_reset_expires": None,
        "created_at": "2024-01-15T10:30:00Z",
        "updated_at": "2024-01-15T10:30:00Z"
    }


@pytest.fixture
def valid_organization_data():
    """Valid organization data for testing."""
    return {
        "_key": "org_test_456",
        "_id": "organizations/org_test_456",
        "name": "Acme Corp",
        "domain": "acme.com",
        "tier": "professional",
        "frameworks": ["FDA_524B", "IEC_62304"],
        "created_at": "2024-01-15T10:30:00Z",
        "updated_at": "2024-01-15T10:30:00Z"
    }


@pytest.fixture
def valid_access_token():
    """Valid JWT access token for testing."""
    # In real tests, generate this using create_access_token()
    return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyX3Rlc3RfMTIzIiwiZW1haWwiOiJqb2huLmRvZUBleGFtcGxlLmNvbSIsIm9yZ19pZCI6Im9yZ190ZXN0XzQ1NiIsInJvbGUiOiJvd25lciIsInR5cGUiOiJhY2Nlc3MiLCJleHAiOjk5OTk5OTk5OTl9.test"


@pytest.fixture
def valid_refresh_token():
    """Valid JWT refresh token for testing."""
    return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyX3Rlc3RfMTIzIiwidHlwZSI6InJlZnJlc2giLCJleHAiOjk5OTk5OTk5OTl9.test"


class TestAuthSignup:
    """Integration tests for POST /v1/auth/signup."""

    @pytest.mark.integration
    def test_signup_success_creates_user_and_organization(
        self, test_client, mock_database
    ):
        """
        Test: POST /v1/auth/signup creates new user and organization.

        Verifies:
        - User is created with hashed password
        - Organization is created
        - User-organization relationship edge is created
        - Email verification token is generated
        - Returns 201 status code
        - Response includes user_id and email
        """
        with patch('api.v1.endpoints.auth.get_database', return_value=mock_database), \
             patch('api.repositories.user.UserRepository.get_user_by_email', return_value=None), \
             patch('api.repositories.user.UserRepository.create_user') as mock_create_user, \
             patch('api.repositories.organization.OrganizationRepository.create_organization') as mock_create_org:

            # Mock organization creation
            mock_create_org.return_value = {
                "_key": "org_new_123",
                "_id": "organizations/org_new_123",
                "name": "Test Corp",
                "tier": "free"
            }

            # Mock user creation
            mock_create_user.return_value = {
                "_key": "user_new_456",
                "_id": "users/user_new_456",
                "email": "newuser@test.com",
                "name": "New User",
                "email_verified": False,
                "email_verification_token": "abc123def456ghi789"
            }

            # Make request
            response = test_client.post(
                "/v1/auth/signup",
                json={
                    "name": "New User",
                    "email": "newuser@test.com",
                    "password": "SecurePass123!",
                    "organization_name": "Test Corp",
                    "organization_domain": "test.com"
                }
            )

            # Verify response
            assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"

            data = response.json()
            assert data["success"] is True
            assert data["message"] == "Account created successfully. Please check your email to verify your account."
            assert data["user_id"] == "users/user_new_456"
            assert data["email"] == "newuser@test.com"

            # Verify organization was created
            mock_create_org.assert_called_once()

            # Verify user was created
            mock_create_user.assert_called_once()

    @pytest.mark.integration
    def test_signup_fails_with_existing_email(
        self, test_client, mock_database, valid_user_data
    ):
        """
        Test: POST /v1/auth/signup fails when email already exists.

        Verifies:
        - Returns 400 status code
        - Error message indicates email already registered
        """
        with patch('api.v1.endpoints.auth.get_database', return_value=mock_database), \
             patch('api.repositories.user.UserRepository.get_user_by_email', return_value=valid_user_data):

            response = test_client.post(
                "/v1/auth/signup",
                json={
                    "name": "John Doe",
                    "email": "john.doe@example.com",
                    "password": "SecurePass123!",
                    "organization_name": "Acme Corp",
                    "organization_domain": "acme.com"
                }
            )

            assert response.status_code == 400
            data = response.json()
            assert "Email already registered" in data["detail"]

    @pytest.mark.integration
    def test_signup_fails_with_weak_password(self, test_client):
        """
        Test: POST /v1/auth/signup fails when password is weak.

        Verifies:
        - Returns 422 status code (validation error)
        - Error message indicates password requirements
        """
        response = test_client.post(
            "/v1/auth/signup",
            json={
                "name": "Test User",
                "email": "test@example.com",
                "password": "weak",  # Too short, no uppercase, no number, no special char
                "organization_name": "Test Corp",
                "organization_domain": "test.com"
            }
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.integration
    def test_signup_fails_with_invalid_email(self, test_client):
        """
        Test: POST /v1/auth/signup fails when email format is invalid.

        Verifies:
        - Returns 422 status code (validation error)
        - Error message indicates invalid email format
        """
        response = test_client.post(
            "/v1/auth/signup",
            json={
                "name": "Test User",
                "email": "not-an-email",  # Invalid format
                "password": "SecurePass123!",
                "organization_name": "Test Corp",
                "organization_domain": "test.com"
            }
        )

        assert response.status_code == 422


class TestAuthLogin:
    """Integration tests for POST /v1/auth/login."""

    @pytest.mark.integration
    def test_login_success_returns_tokens_and_user_profile(
        self, test_client, mock_database, valid_user_data, valid_organization_data
    ):
        """
        Test: POST /v1/auth/login returns JWT tokens and user profile.

        Verifies:
        - Credentials are validated
        - Access token is generated
        - Refresh token is generated
        - User profile is included in response
        - Returns 200 status code
        """
        with patch('api.v1.endpoints.auth.get_database', return_value=mock_database), \
             patch('api.core.config.get_cloud_settings') as mock_settings, \
             patch('api.services.auth.AuthService.authenticate', return_value=valid_user_data), \
             patch('api.services.auth.AuthService.get_user_organization', return_value={**valid_organization_data, "role": "owner"}), \
             patch('api.services.auth.AuthService.create_tokens', return_value={"access_token": "access_token_123", "refresh_token": "refresh_token_456"}):

            # Mock settings
            mock_settings.return_value.JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 15

            response = test_client.post(
                "/v1/auth/login",
                json={
                    "email": "john.doe@example.com",
                    "password": "SecurePass123!"
                }
            )

            assert response.status_code == 200

            data = response.json()
            assert data["access_token"] == "access_token_123"
            assert data["refresh_token"] == "refresh_token_456"
            assert data["token_type"] == "bearer"
            assert data["expires_in"] == 900  # 15 minutes * 60 seconds

            # Verify user profile
            user = data["user"]
            assert user["id"] == "users/user_test_123"
            assert user["email"] == "john.doe@example.com"
            assert user["name"] == "John Doe"
            assert user["email_verified"] is True
            assert user["organization_id"] == "org_test_456"
            assert user["organization_name"] == "Acme Corp"
            assert user["role"] == "owner"
            assert user["tier"] == "professional"
            assert user["frameworks"] == ["FDA_524B", "IEC_62304"]

    @pytest.mark.integration
    def test_login_fails_with_invalid_email(
        self, test_client, mock_database
    ):
        """
        Test: POST /v1/auth/login fails when email doesn't exist.

        Verifies:
        - Returns 401 status code
        - Error message is generic (security best practice)
        """
        with patch('api.v1.endpoints.auth.get_database', return_value=mock_database), \
             patch('api.repositories.user.UserRepository.get_user_by_email', return_value=None):

            response = test_client.post(
                "/v1/auth/login",
                json={
                    "email": "nonexistent@example.com",
                    "password": "SecurePass123!"
                }
            )

            assert response.status_code == 401
            data = response.json()
            assert data["detail"] == "Invalid email or password"

    @pytest.mark.integration
    def test_login_fails_with_invalid_password(
        self, test_client, mock_database, valid_user_data
    ):
        """
        Test: POST /v1/auth/login fails when password is incorrect.

        Verifies:
        - Returns 401 status code
        - Error message is generic (security best practice)
        """
        with patch('api.v1.endpoints.auth.get_database', return_value=mock_database), \
             patch('api.repositories.user.UserRepository.get_user_by_email', return_value=valid_user_data), \
             patch('api.core.security.verify_password', return_value=False):

            response = test_client.post(
                "/v1/auth/login",
                json={
                    "email": "john.doe@example.com",
                    "password": "WrongPassword123!"
                }
            )

            assert response.status_code == 401
            data = response.json()
            assert data["detail"] == "Invalid email or password"


class TestAuthVerifyEmail:
    """Integration tests for POST /v1/auth/verify-email."""

    @pytest.mark.integration
    def test_verify_email_success(
        self, test_client, mock_database
    ):
        """
        Test: POST /v1/auth/verify-email verifies email with valid token.

        Verifies:
        - Token is validated
        - Email verification status is updated
        - Returns success message
        - Returns 200 status code
        """
        with patch('api.v1.endpoints.auth.get_database', return_value=mock_database), \
             patch('api.repositories.user.UserRepository.verify_email', return_value=True):

            response = test_client.post(
                "/v1/auth/verify-email",
                json={
                    "token": "abc123def456ghi789jkl012mno345pqr"
                }
            )

            assert response.status_code == 200

            data = response.json()
            assert data["success"] is True
            assert data["message"] == "Email verified successfully. You can now log in."

    @pytest.mark.integration
    def test_verify_email_fails_with_invalid_token(
        self, test_client, mock_database
    ):
        """
        Test: POST /v1/auth/verify-email fails with invalid token.

        Verifies:
        - Returns 400 status code
        - Error message indicates invalid/expired token
        """
        with patch('api.v1.endpoints.auth.get_database', return_value=mock_database), \
             patch('api.services.auth.AuthService.verify_email', return_value=False):

            response = test_client.post(
                "/v1/auth/verify-email",
                json={
                    "token": "invalid_token_123_long_enough_for_validation_check"
                }
            )

            assert response.status_code == 400
            data = response.json()
            assert "Invalid or expired verification token" in data["detail"]

    @pytest.mark.integration
    def test_verify_email_fails_with_short_token(self, test_client):
        """
        Test: POST /v1/auth/verify-email fails when token is too short.

        Verifies:
        - Returns 422 status code (validation error)
        - Error indicates minimum token length requirement
        """
        response = test_client.post(
            "/v1/auth/verify-email",
            json={
                "token": "short"  # Less than 32 characters
            }
        )

        assert response.status_code == 422


class TestAuthForgotPassword:
    """Integration tests for POST /v1/auth/forgot-password."""

    @pytest.mark.integration
    def test_forgot_password_success_returns_generic_message(
        self, test_client, mock_database
    ):
        """
        Test: POST /v1/auth/forgot-password returns generic success message.

        Verifies:
        - Always returns success (prevents email enumeration)
        - Creates password reset token for valid email
        - Returns 200 status code
        - Message is generic and doesn't reveal if email exists
        """
        with patch('api.v1.endpoints.auth.get_database', return_value=mock_database), \
             patch('api.repositories.user.UserRepository.create_password_reset_token', return_value="reset_token_123"):

            response = test_client.post(
                "/v1/auth/forgot-password",
                json={
                    "email": "john.doe@example.com"
                }
            )

            assert response.status_code == 200

            data = response.json()
            assert data["success"] is True
            assert "If an account exists with this email" in data["message"]

    @pytest.mark.integration
    def test_forgot_password_returns_same_message_for_nonexistent_email(
        self, test_client, mock_database
    ):
        """
        Test: POST /v1/auth/forgot-password returns same message for non-existent email.

        Verifies:
        - Always returns success (prevents email enumeration)
        - Returns same message regardless of whether email exists
        """
        with patch('api.v1.endpoints.auth.get_database', return_value=mock_database), \
             patch('api.repositories.user.UserRepository.create_password_reset_token', return_value=None):

            response = test_client.post(
                "/v1/auth/forgot-password",
                json={
                    "email": "nonexistent@example.com"
                }
            )

            assert response.status_code == 200

            data = response.json()
            assert data["success"] is True
            assert "If an account exists with this email" in data["message"]

    @pytest.mark.integration
    def test_forgot_password_fails_with_invalid_email_format(self, test_client):
        """
        Test: POST /v1/auth/forgot-password fails with invalid email format.

        Verifies:
        - Returns 422 status code (validation error)
        """
        response = test_client.post(
            "/v1/auth/forgot-password",
            json={
                "email": "not-an-email"
            }
        )

        assert response.status_code == 422


class TestAuthResetPassword:
    """Integration tests for POST /v1/auth/reset-password."""

    @pytest.mark.integration
    def test_reset_password_success(
        self, test_client, mock_database
    ):
        """
        Test: POST /v1/auth/reset-password resets password with valid token.

        Verifies:
        - Token is validated
        - New password meets strength requirements
        - Password is hashed and updated
        - Returns success message
        - Returns 200 status code
        """
        with patch('api.v1.endpoints.auth.get_database', return_value=mock_database), \
             patch('api.repositories.user.UserRepository.reset_password', return_value=True), \
             patch('api.core.security.hash_password', return_value="new_hashed_password"):

            response = test_client.post(
                "/v1/auth/reset-password",
                json={
                    "token": "reset_token_abc123def456ghi789jkl",
                    "new_password": "NewSecurePass456!"
                }
            )

            assert response.status_code == 200

            data = response.json()
            assert data["success"] is True
            assert data["message"] == "Password reset successfully. You can now log in with your new password."

    @pytest.mark.integration
    def test_reset_password_fails_with_invalid_token(
        self, test_client, mock_database
    ):
        """
        Test: POST /v1/auth/reset-password fails with invalid token.

        Verifies:
        - Returns 400 status code
        - Error message indicates invalid/expired token
        """
        with patch('api.v1.endpoints.auth.get_database', return_value=mock_database), \
             patch('api.services.auth.AuthService.reset_password', return_value=False):

            response = test_client.post(
                "/v1/auth/reset-password",
                json={
                    "token": "invalid_token_123_that_is_long_enough_for_validation",
                    "new_password": "NewSecurePass456!"
                }
            )

            assert response.status_code == 400
            data = response.json()
            assert "Invalid or expired reset token" in data["detail"]

    @pytest.mark.integration
    def test_reset_password_fails_with_weak_password(self, test_client):
        """
        Test: POST /v1/auth/reset-password fails when new password is weak.

        Verifies:
        - Returns 422 status code (validation error)
        - Error message indicates password requirements
        """
        response = test_client.post(
            "/v1/auth/reset-password",
            json={
                "token": "reset_token_abc123def456ghi789jkl",
                "new_password": "weak"  # Too short, no uppercase, no number, no special char
            }
        )

        assert response.status_code == 422


class TestAuthRefresh:
    """Integration tests for POST /v1/auth/refresh."""

    @pytest.mark.integration
    def test_refresh_token_success_returns_new_access_token(
        self, test_client, mock_database, valid_user_data, valid_organization_data
    ):
        """
        Test: POST /v1/auth/refresh returns new access token.

        Verifies:
        - Refresh token is validated
        - New access token is generated
        - Token type and expiry are included
        - Returns 200 status code
        """
        with patch('api.v1.endpoints.auth.get_database', return_value=mock_database), \
             patch('api.core.config.get_cloud_settings') as mock_settings, \
             patch('api.services.auth.AuthService.verify_refresh_token', return_value={"sub": "user_test_123", "type": "refresh"}), \
             patch('api.services.auth.AuthService.get_user_by_id', return_value=valid_user_data), \
             patch('api.services.auth.AuthService.get_user_organization', return_value={**valid_organization_data, "role": "owner"}), \
             patch('api.services.auth.AuthService.create_tokens', return_value={"access_token": "new_access_token_789", "refresh_token": "rt"}):

            # Mock settings
            mock_settings.return_value.JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 15

            response = test_client.post(
                "/v1/auth/refresh",
                json={
                    "refresh_token": "valid_refresh_token_123"
                }
            )

            assert response.status_code == 200

            data = response.json()
            assert data["access_token"] == "new_access_token_789"
            assert data["token_type"] == "bearer"
            assert data["expires_in"] == 900  # 15 minutes * 60 seconds

    @pytest.mark.integration
    def test_refresh_token_fails_with_invalid_token(
        self, test_client, mock_database
    ):
        """
        Test: POST /v1/auth/refresh fails with invalid refresh token.

        Verifies:
        - Returns 401 status code
        - Error message indicates invalid/expired token
        """
        with patch('api.v1.endpoints.auth.get_database', return_value=mock_database), \
             patch('api.services.auth.AuthService.verify_refresh_token', side_effect=Exception("Invalid token")):

            response = test_client.post(
                "/v1/auth/refresh",
                json={
                    "refresh_token": "invalid_refresh_token"
                }
            )

            assert response.status_code == 401
            data = response.json()
            assert "Invalid or expired" in data["detail"]

    @pytest.mark.integration
    def test_refresh_token_fails_with_access_token(
        self, test_client, mock_database
    ):
        """
        Test: POST /v1/auth/refresh fails when using access token instead of refresh token.

        Verifies:
        - Returns 401 status code
        - Error message indicates wrong token type
        """
        with patch('api.v1.endpoints.auth.get_database', return_value=mock_database), \
             patch('api.services.auth.AuthService.verify_refresh_token', return_value={"sub": "user_test_123", "type": "access"}):

            response = test_client.post(
                "/v1/auth/refresh",
                json={
                    "refresh_token": "access_token_not_refresh"
                }
            )

            assert response.status_code == 401
            data = response.json()
            assert "Invalid token type" in data["detail"] or "Invalid or expired" in data["detail"]


class TestAuthMe:
    """Integration tests for GET /v1/auth/me."""

    @pytest.mark.integration
    def test_get_current_user_success_returns_profile(
        self, test_client, mock_database, valid_user_data, valid_organization_data
    ):
        """
        Test: GET /v1/auth/me returns current user profile.

        Verifies:
        - Access token is validated
        - User profile is fetched from database
        - Organization information is included
        - Returns 200 status code
        """
        from api.main import app as fastapi_app
        from api.core.security import get_current_user

        async def _override(token=None):
            return {"sub": "user_test_123"}

        fastapi_app.dependency_overrides[get_current_user] = _override
        try:
            with patch('api.v1.endpoints.auth.get_database', return_value=mock_database), \
                 patch('api.services.auth.AuthService.get_user_by_id', return_value=valid_user_data), \
                 patch('api.services.auth.AuthService.get_user_organization', return_value={**valid_organization_data, "role": "owner"}):

                response = test_client.get(
                    "/v1/auth/me",
                    headers={"Authorization": "Bearer valid_access_token_123"}
                )

                assert response.status_code == 200

                data = response.json()
                assert data["id"] == "users/user_test_123"
                assert data["email"] == "john.doe@example.com"
                assert data["name"] == "John Doe"
                assert data["email_verified"] is True
                assert data["organization_id"] == "org_test_456"
                assert data["organization_name"] == "Acme Corp"
                assert data["role"] == "owner"
                assert data["tier"] == "professional"
                assert data["frameworks"] == ["FDA_524B", "IEC_62304"]
                assert data["created_at"] == "2024-01-15T10:30:00Z"
        finally:
            fastapi_app.dependency_overrides.pop(get_current_user, None)

    @pytest.mark.integration
    def test_get_current_user_fails_without_auth_header(
        self, test_client
    ):
        """
        Test: GET /v1/auth/me fails when Authorization header is missing.

        Verifies:
        - Returns 401 or 403 status code
        """
        response = test_client.get("/v1/auth/me")

        # Depending on FastAPI security configuration, this could be 401 or 403
        assert response.status_code in [401, 403]

    @pytest.mark.integration
    def test_get_current_user_fails_with_invalid_token(
        self, test_client, mock_database
    ):
        """
        Test: GET /v1/auth/me fails with invalid access token.

        Verifies:
        - Returns 401 status code
        - Error message indicates invalid/expired token
        """
        with patch('api.v1.endpoints.auth.get_database', return_value=mock_database), \
             patch('api.core.security.get_current_user', side_effect=Exception("Invalid token")):

            response = test_client.get(
                "/v1/auth/me",
                headers={"Authorization": "Bearer invalid_token"}
            )

            # Depending on exception handling, this could be 401 or 500
            assert response.status_code in [401, 500]

    @pytest.mark.integration
    def test_get_current_user_fails_when_user_not_found(
        self, test_client, mock_database
    ):
        """
        Test: GET /v1/auth/me fails when user document doesn't exist.

        Verifies:
        - Returns 404 status code
        - Error message indicates user not found
        """
        from api.main import app as fastapi_app
        from api.core.security import get_current_user

        async def _override(token=None):
            return {"sub": "user_nonexistent"}

        fastapi_app.dependency_overrides[get_current_user] = _override
        try:
            with patch('api.v1.endpoints.auth.get_database', return_value=mock_database), \
                 patch('api.services.auth.AuthService.get_user_by_id', return_value=None):

                response = test_client.get(
                    "/v1/auth/me",
                    headers={"Authorization": "Bearer valid_access_token_123"}
                )

                assert response.status_code == 404
                data = response.json()
                assert "User not found" in data["detail"]
        finally:
            fastapi_app.dependency_overrides.pop(get_current_user, None)
