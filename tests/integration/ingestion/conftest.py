"""
Fixtures for EvidenceIngestionService integration tests.

These tests require a live ArangoDB instance. All tests that use ref_db are
automatically skipped if the database is not reachable.
"""

import pytest
from unittest.mock import MagicMock, Mock


def _try_get_ref_db():
    """Attempt to connect to the reference ArangoDB database.

    Returns the database handle on success, None on failure.
    """
    try:
        from api.core.database import get_reference_db
        db = get_reference_db()
        # Probe the connection — raises if not reachable
        db.collections()
        return db
    except Exception:
        return None


@pytest.fixture(scope="session")
def ref_db():
    """Live reference DB connection.

    Skips the entire session if ArangoDB is not reachable.
    """
    db = _try_get_ref_db()
    if db is None:
        pytest.skip("ArangoDB reference DB not reachable — skipping live integration tests")
    return db


@pytest.fixture
def tenant_id():
    """Deterministic tenant ID for integration test isolation."""
    return "integration_test_tenant"


@pytest.fixture
def mock_customer_db():
    """Mock customer DB with one legacy scan_session document."""
    db = MagicMock()
    sessions_col = MagicMock()
    sessions_col.__iter__ = Mock(return_value=iter([
        {
            "_key": "sess_001",
            "customer_id": "integration_test_tenant",
            "tool_name": "semgrep",
            "status": "completed",
            "findings_count": 1,
            "created_at": "2024-01-01T00:00:00Z",
        }
    ]))
    components_col = MagicMock()
    components_col.__iter__ = Mock(return_value=iter([]))

    def _collection(name):
        if name == "scan_sessions":
            return sessions_col
        return components_col

    db.collection = Mock(side_effect=_collection)
    db.aql = MagicMock()
    db.aql.execute = Mock(return_value=iter([]))
    return db


@pytest.fixture
def mock_customer_db_with_components():
    """Mock customer DB with one legacy component document (has purl)."""
    db = MagicMock()
    sessions_col = MagicMock()
    sessions_col.__iter__ = Mock(return_value=iter([]))
    components_col = MagicMock()
    components_col.__iter__ = Mock(return_value=iter([
        {
            "_key": "comp_001",
            "purl": "pkg:npm/react@18.0.0",
            "name": "react",
            "version": "18.0.0",
            "customer_id": "integration_test_tenant",
            "tenant_id": "integration_test_tenant",
        }
    ]))

    def _collection(name):
        if name == "scan_sessions":
            return sessions_col
        return components_col

    db.collection = Mock(side_effect=_collection)
    db.aql = MagicMock()
    db.aql.execute = Mock(return_value=iter([]))
    return db
