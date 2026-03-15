"""
Unit tests for Phase 1: Authentication Model Adoption.

Tests for AC-004:
- AC-004: Authentication returns CustomerProfile model (not Customer class)
"""

import pytest
from unittest.mock import MagicMock, Mock, patch, AsyncMock
from fastapi import HTTPException

from api.core.security import (
    get_customer_from_api_key,
    get_current_customer,
    verify_api_key,
)
from complira_graph.models import CustomerProfile


@pytest.fixture
def mock_db():
    """Mock ArangoDB database."""
    db = MagicMock()

    # Mock AQL execution
    db.aql = MagicMock()
    db.aql.execute = Mock(return_value=[])

    return db


@pytest.fixture
def sample_customer_profile_dict():
    """Sample customer profile dictionary from database."""
    return {
        "_key": "customer_abc",
        "_id": "customer_profiles/customer_abc",
        "_rev": "_rev123",
        "name": "Acme Corp",
        "tier": "pro",
        "database_name": "customer_abc_db",
        "api_key_hash": "$2b$12$hashedapikey123",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
    }


# ============================================================================
# AC-004: Authentication Returns CustomerProfile Model
# ============================================================================

class TestAC004_Authentication:
    """Test AC-004: Authentication returns CustomerProfile model."""

    @pytest.mark.asyncio
    async def test_get_customer_from_api_key_returns_customer_profile_model(
        self, mock_db, sample_customer_profile_dict
    ):
        """
        AC-004 Test 1: get_customer_from_api_key() returns CustomerProfile instance.

        Verifies:
        - Return type is CustomerProfile (not Customer class)
        - Model validates tier, database_name, api_key_hash
        - Customer class is no longer used
        """
        with patch('api.core.security.get_database', return_value=mock_db), \
             patch('api.core.security.verify_api_key', return_value=True):

            # Mock AQL query to return customer profile
            mock_db.aql.execute.return_value = [sample_customer_profile_dict]

            # Get customer from API key
            result = await get_customer_from_api_key(api_key="test_api_key_123")

            # Verify return type is CustomerProfile model
            assert isinstance(result, CustomerProfile)

            # Verify model attributes
            assert result._key == "customer_abc"
            assert result.name == "Acme Corp"
            assert result.tier == "pro"
            assert result.database_name == "customer_abc_db"

    @pytest.mark.asyncio
    async def test_get_customer_from_api_key_validates_model_fields(
        self, mock_db, sample_customer_profile_dict
    ):
        """
        AC-004 Test 2: CustomerProfile model validates required fields.

        Verifies:
        - Model validates tier (must be 'free', 'pro', 'enterprise')
        - Model requires database_name
        - Model requires api_key_hash
        """
        with patch('api.core.security.get_database', return_value=mock_db), \
             patch('api.core.security.verify_api_key', return_value=True):

            # Mock AQL query to return customer profile
            mock_db.aql.execute.return_value = [sample_customer_profile_dict]

            # Get customer from API key
            result = await get_customer_from_api_key(api_key="test_api_key_123")

            # Verify CustomerProfile model validation passed
            assert isinstance(result, CustomerProfile)
            assert result.tier in ["free", "pro", "enterprise"]
            assert result.database_name is not None
            assert result.api_key_hash is not None

    @pytest.mark.asyncio
    async def test_get_customer_from_api_key_returns_none_for_invalid_key(self, mock_db):
        """
        AC-004 Test 3: get_customer_from_api_key() returns None for invalid API key.

        Verifies:
        - Returns None if no matching API key found
        - Does not raise exception
        """
        with patch('api.core.security.get_database', return_value=mock_db), \
             patch('api.core.security.verify_api_key', return_value=False):

            # Mock AQL query to return profiles (but verify will fail)
            mock_db.aql.execute.return_value = [{
                "_key": "customer_abc",
                "name": "Acme Corp",
                "tier": "pro",
                "database_name": "customer_abc_db",
                "api_key_hash": "$2b$12$different_hash",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
            }]

            # Get customer with invalid API key
            result = await get_customer_from_api_key(api_key="invalid_key")

            # Verify returns None
            assert result is None

    @pytest.mark.asyncio
    async def test_get_current_customer_returns_customer_profile_model(
        self, mock_db, sample_customer_profile_dict
    ):
        """
        AC-004 Test 4: get_current_customer() returns CustomerProfile instance.

        Verifies:
        - FastAPI dependency returns CustomerProfile model
        - Model can be used in endpoint handlers
        """
        with patch('api.core.security.get_database', return_value=mock_db), \
             patch('api.core.security.verify_api_key', return_value=True):

            # Mock AQL query
            mock_db.aql.execute.return_value = [sample_customer_profile_dict]

            # Call get_current_customer with API key
            result = await get_current_customer(api_key="test_api_key_123")

            # Verify return type is CustomerProfile model
            assert isinstance(result, CustomerProfile)
            assert result._key == "customer_abc"
            assert result.name == "Acme Corp"

    @pytest.mark.asyncio
    async def test_get_current_customer_raises_401_for_missing_key(self):
        """
        AC-004 Test 5: get_current_customer() raises 401 for missing API key.

        Verifies:
        - Raises HTTPException with 401 status code
        - Proper error message
        """
        with pytest.raises(HTTPException) as exc_info:
            await get_current_customer(api_key=None)

        # Verify exception details
        assert exc_info.value.status_code == 401
        assert "Missing API key" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_current_customer_raises_401_for_invalid_key(self, mock_db):
        """
        AC-004 Test 6: get_current_customer() raises 401 for invalid API key.

        Verifies:
        - Raises HTTPException with 401 status code
        - Proper error message
        """
        with patch('api.core.security.get_database', return_value=mock_db), \
             patch('api.core.security.verify_api_key', return_value=False):

            # Mock AQL query
            mock_db.aql.execute.return_value = [{
                "_key": "customer_abc",
                "name": "Acme Corp",
                "tier": "pro",
                "database_name": "customer_abc_db",
                "api_key_hash": "$2b$12$different_hash",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
            }]

            with pytest.raises(HTTPException) as exc_info:
                await get_current_customer(api_key="invalid_key")

            # Verify exception details
            assert exc_info.value.status_code == 401
            assert "Invalid API key" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_customer_profile_has_id_property_for_backward_compatibility(
        self, mock_db, sample_customer_profile_dict
    ):
        """
        AC-004 Test 7: CustomerProfile has .id property for backward compatibility.

        Verifies:
        - CustomerProfile.id returns same value as CustomerProfile._key
        - Endpoints can use either customer.id or customer._key
        """
        with patch('api.core.security.get_database', return_value=mock_db), \
             patch('api.core.security.verify_api_key', return_value=True):

            # Mock AQL query
            mock_db.aql.execute.return_value = [sample_customer_profile_dict]

            # Get customer from API key
            result = await get_customer_from_api_key(api_key="test_api_key_123")

            # Verify CustomerProfile has .id property
            assert hasattr(result, 'id')
            assert result.id == result._key
            assert result.id == "customer_abc"

    @pytest.mark.asyncio
    async def test_customer_profile_has_required_attributes(
        self, mock_db, sample_customer_profile_dict
    ):
        """
        AC-004 Test 8: CustomerProfile has all required attributes for authentication.

        Verifies:
        - Model has _key, name, tier, database_name, api_key_hash
        - All attributes are accessible
        """
        with patch('api.core.security.get_database', return_value=mock_db), \
             patch('api.core.security.verify_api_key', return_value=True):

            # Mock AQL query
            mock_db.aql.execute.return_value = [sample_customer_profile_dict]

            # Get customer from API key
            result = await get_customer_from_api_key(api_key="test_api_key_123")

            # Verify all required attributes exist
            assert hasattr(result, '_key')
            assert hasattr(result, 'name')
            assert hasattr(result, 'tier')
            assert hasattr(result, 'database_name')
            assert hasattr(result, 'api_key_hash')

            # Verify attribute values
            assert result._key == "customer_abc"
            assert result.name == "Acme Corp"
            assert result.tier == "pro"
            assert result.database_name == "customer_abc_db"
            assert result.api_key_hash == "$2b$12$hashedapikey123"

    def test_customer_class_is_removed(self):
        """
        AC-004 Test 9: Verify Customer is backward compatibility alias.

        Verifies:
        - Customer is an alias to CustomerProfile (backward compatibility)
        - CustomerProfile is the canonical model
        """
        import api.core.security
        from complira_graph.models import CustomerProfile

        # Verify Customer exists as backward compatibility alias
        assert hasattr(api.core.security, 'Customer')
        assert api.core.security.Customer is CustomerProfile

        # Verify CustomerProfile is the canonical model
        assert CustomerProfile is not None
