"""
Integration test fixtures with proper FastAPI dependency overrides.

FastAPI's Depends() system requires app.dependency_overrides for mocking,
not unittest.mock.patch() which only patches module namespaces.
"""

import pytest
from unittest.mock import Mock, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    """FastAPI application instance."""
    from api.main import app
    yield app
    # Always clean up overrides after tests
    app.dependency_overrides.clear()


@pytest.fixture
def mock_customer():
    """Mock authenticated customer (for API key auth endpoints)."""
    customer = Mock()
    customer._key = "customer_test"
    customer.id = "customer_test"
    customer.name = "Test Customer"
    customer.tier = "pro"
    customer.database_name = "complira_tenant_customer_test"
    customer.frameworks = ["FDA_524B"]
    return customer


@pytest.fixture
def mock_auth_user():
    """Mock authenticated user (for JWT auth endpoints)."""
    return {
        "sub": "user_test_123",
        "email": "test@example.com",
        "org_id": "org_test_123",
        "role": "owner",
    }


@pytest.fixture
def override_customer_auth(app, mock_customer):
    """Override get_current_customer dependency with mock."""
    from api.core.security import get_current_customer

    async def _override(api_key=None, token=None):
        return mock_customer

    app.dependency_overrides[get_current_customer] = _override
    yield mock_customer
    app.dependency_overrides.pop(get_current_customer, None)


@pytest.fixture
def override_user_auth(app, mock_auth_user):
    """Override get_current_user dependency with mock."""
    from api.core.security import get_current_user

    async def _override(token=None):
        return mock_auth_user

    app.dependency_overrides[get_current_user] = _override
    yield mock_auth_user
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def override_database(app):
    """Override get_database dependency with mock."""
    from api.core.database import get_database

    mock_db = MagicMock()
    mock_db.has_collection = Mock(return_value=True)
    mock_db.collection = Mock(return_value=MagicMock())
    mock_db.aql = MagicMock()
    mock_db.aql.execute = Mock(return_value=[])

    app.dependency_overrides[get_database] = lambda: mock_db
    yield mock_db
    app.dependency_overrides.pop(get_database, None)


@pytest.fixture
def api_client(app):
    """FastAPI TestClient."""
    return TestClient(app)
