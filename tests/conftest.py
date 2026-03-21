"""
Pytest configuration and fixtures for Complira Knowledge Graph tests.
"""

# Suppress urllib3 SSL warning BEFORE any imports that trigger it.
# On macOS system Python 3.9 with LibreSSL, urllib3 v2 fires a NotOpenSSLWarning
# at import time. This must be suppressed here (before pytest filterwarnings="error"
# processes it) so the existing test suite continues to function.
import warnings
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

import pytest
from unittest.mock import Mock, MagicMock
from pathlib import Path
import os
import sys

# Add project root to sys.path for scripts imports
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Add src to path
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Set test environment
os.environ['ENVIRONMENT'] = 'test'

# Enable integration tests with real database
# Set to 'true' to use local database, 'false' to use mocks
USE_REAL_DB = os.environ.get('USE_REAL_DB', 'true').lower() == 'true'


@pytest.fixture(scope='session')
def test_data_dir():
    """Path to test data directory."""
    return Path(__file__).parent / 'data'


@pytest.fixture
def mock_db():
    """Mock ArangoDB database."""
    db = MagicMock()

    # Mock collections
    db.has_collection = Mock(return_value=True)
    db.collection = Mock(return_value=MagicMock())
    db.create_collection = Mock(return_value=MagicMock())

    # Mock AQL
    db.aql = MagicMock()
    db.aql.execute = Mock(return_value=[])

    return db


@pytest.fixture
def real_db():
    """Real ArangoDB connection for integration tests."""
    if not USE_REAL_DB:
        pytest.skip("Real database tests disabled. Set USE_REAL_DB=true to enable.")

    try:
        from complira_graph.db import get_db
        db = get_db()
        yield db
    except Exception as e:
        pytest.skip(f"Could not connect to real database: {e}")


@pytest.fixture
def test_client():
    """FastAPI TestClient for API integration tests."""
    if not USE_REAL_DB:
        pytest.skip("Real database tests disabled. Set USE_REAL_DB=true to enable.")

    try:
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)
        yield client
    except Exception as e:
        pytest.skip(f"Could not create test client: {e}")


@pytest.fixture(scope='session')
def test_customer_profile(real_db):
    """
    Create test customer profile with API key in database.

    This fixture creates a real test customer in the database that can be used
    for integration tests. The customer is cleaned up after all tests complete.
    """
    if not USE_REAL_DB:
        pytest.skip("Real database tests disabled. Set USE_REAL_DB=true to enable.")

    import secrets
    from api.core.security import hash_api_key

    # Generate test API key
    test_api_key = f"test_api_key_{secrets.token_hex(16)}"
    api_key_hash = hash_api_key(test_api_key)

    # Create test customer profile
    test_customer = {
        "_key": "test_customer_001",
        "name": "Test Customer Organization",
        "tier": "professional",
        "frameworks": ["FDA_524B", "IEC_62304"],
        "database_name": "complira_tenant_test_customer_001",
        "api_key_hash": api_key_hash,
        "created_at": "2024-01-01T00:00:00Z",
    }

    try:
        # Create customer_profiles collection if it doesn't exist
        if not real_db.has_collection("customer_profiles"):
            real_db.create_collection("customer_profiles")

        # Insert or update test customer
        collection = real_db.collection("customer_profiles")
        try:
            collection.insert(test_customer, overwrite=True)
        except Exception:
            # If document exists, update it
            collection.update(test_customer)

        yield {
            "customer_key": test_customer["_key"],
            "api_key": test_api_key,
            "customer_data": test_customer,
        }

        # Cleanup after all tests
        try:
            collection.delete(test_customer["_key"])
        except Exception:
            pass  # Ignore cleanup errors

    except Exception as e:
        pytest.skip(f"Could not create test customer: {e}")


@pytest.fixture
def valid_api_key(test_customer_profile):
    """Valid API key for testing authenticated endpoints."""
    return test_customer_profile["api_key"]


@pytest.fixture
def customer_token():
    """Valid customer JWT token for testing."""
    # TODO: Implement real JWT token generation
    # For now, tests will use API key authentication
    return "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.test"


@pytest.fixture
def mock_settings():
    """Mock application settings."""
    from unittest.mock import patch

    settings = Mock()
    settings.ARANGO_URL = 'http://localhost:8529'
    settings.ARANGO_DATABASE = 'test_complira'
    settings.ARANGO_PASSWORD = 'test_password'
    settings.ANTHROPIC_API_KEY = 'test_api_key'
    settings.NVD_API_KEY = None

    with patch('complira_graph.config.get_settings', return_value=settings):
        yield settings


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic API client."""
    client = MagicMock()

    # Mock response
    response = MagicMock()
    response.content = [MagicMock(text='{"result": "test"}')]
    response.usage = MagicMock(input_tokens=100, output_tokens=50)

    client.messages.create = Mock(return_value=response)

    return client


@pytest.fixture
def mock_http_client():
    """Mock HTTP client."""
    import httpx

    client = MagicMock(spec=httpx.Client)

    # Mock response
    response = MagicMock(spec=httpx.Response)
    response.status_code = 200
    response.text = '{"data": []}'
    response.json = Mock(return_value={'data': []})
    response.content = b'{"data": []}'

    client.get = Mock(return_value=response)
    client.post = Mock(return_value=response)

    return client


@pytest.fixture
def sample_cve_data():
    """Sample CVE data for testing."""
    return {
        'cve_id': 'CVE-2024-1234',
        'description': 'Test vulnerability in example software',
        'cvss_v3_score': 9.8,
        'cvss_v3_vector': 'CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H',
        'published': '2024-01-15T00:00:00Z',
        'cwe_ids': ['CWE-79'],
    }


@pytest.fixture
def sample_cwe_data():
    """Sample CWE data for testing."""
    return {
        'cwe_id': 'CWE-79',
        'name': 'Cross-site Scripting (XSS)',
        'abstraction': 'Base',
        'description': 'Improper neutralization of input during web page generation',
    }


@pytest.fixture
def sample_attack_technique():
    """Sample ATT&CK technique for testing."""
    return {
        'technique_id': 'T1190',
        'name': 'Exploit Public-Facing Application',
        'tactic': 'initial-access',
        'description': 'Adversaries may exploit software vulnerabilities',
    }


@pytest.fixture(autouse=True)
def reset_logging():
    """Reset logging configuration between tests."""
    import structlog

    # Reset structlog configuration
    structlog.reset_defaults()

    yield

    # Cleanup
    structlog.reset_defaults()


@pytest.fixture(scope='function')
def temp_env_vars(monkeypatch):
    """Fixture for temporarily setting environment variables."""
    def _set_env(**kwargs):
        for key, value in kwargs.items():
            monkeypatch.setenv(key, str(value))

    return _set_env


# Mark configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "unit: Unit tests that don't require external dependencies"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests that require database/API"
    )
    config.addinivalue_line(
        "markers", "performance: Performance and load tests"
    )
    config.addinivalue_line(
        "markers", "slow: Tests that take >5 seconds to run"
    )
    config.addinivalue_line(
        "markers", "requires_db: Tests that require ArangoDB connection"
    )
    config.addinivalue_line(
        "markers", "requires_llm: Tests that require LLM API (costs money)"
    )


def pytest_collection_modifyitems(config, items):
    """Auto-mark tests based on path."""
    for item in items:
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "performance" in str(item.fspath):
            item.add_marker(pytest.mark.performance)
            item.add_marker(pytest.mark.slow)
