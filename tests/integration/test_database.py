"""
Integration tests for database operations.

These tests require a running ArangoDB instance.
Run with: pytest -m integration
"""

import pytest
from complira_graph.db import get_db, init_schema, health_check


@pytest.mark.integration
@pytest.mark.requires_db
class TestDatabaseConnection:
    """Test database connection and health."""

    def test_health_check(self):
        """Test database health check."""
        is_healthy, message = health_check()

        # Will fail if database is not running
        assert is_healthy is True, f"Health check failed: {message}"

    def test_get_db_returns_database(self):
        """Test get_db() returns valid database instance."""
        db = get_db()

        assert db is not None
        assert hasattr(db, 'collections')
        assert hasattr(db, 'aql')


@pytest.mark.integration
@pytest.mark.requires_db
class TestSchemaInitialization:
    """Test schema initialization."""

    def test_init_schema_creates_collections(self):
        """Test init_schema() creates all required collections."""
        db = get_db()

        # Initialize schema
        init_schema(db)

        # Check document collections
        doc_collections = [
            'vulnerabilities',
            'weaknesses',
            'attack_techniques',
            'attack_patterns',
            'threat_groups',
            'd3fend_techniques',
            'atlas_techniques',
            'kev_entries',
            'exploit_modules',
            'nuclei_templates',
            'poc_repositories',
            'components',
            'oscal_controls',
            'scf_controls',
            'opencre_nodes',
            'licenses',
            'package_health',
            'scorecard_results',
            'epss_history',
            'cpe_entries',
        ]

        for coll_name in doc_collections:
            assert db.has_collection(coll_name), \
                f"Document collection {coll_name} not created"

        # Check edge collections
        edge_collections = [
            'has_weakness',
            'has_exploit',
            'affects',  # Vulnerability → component/CPE
            'exploited_in_wild',
            'has_epss',  # Renamed from has_epss_score
            'capec_relates_to_cwe',
            'd3fend_counters_technique',
            'atlas_maps_to_attack',
        ]

        for edge_name in edge_collections:
            assert db.has_collection(edge_name), \
                f"Edge collection {edge_name} not created"
            # Verify it's an edge collection
            coll = db.collection(edge_name)
            assert coll.properties()['type'] == 3, \
                f"{edge_name} should be an edge collection (type=3)"

    def test_init_schema_idempotent(self):
        """Test init_schema() can be run multiple times safely."""
        db = get_db()

        # Run twice
        init_schema(db)
        init_schema(db)

        # Should not raise errors
        assert db.has_collection('vulnerabilities')


@pytest.mark.integration
@pytest.mark.requires_db
class TestBasicQueries:
    """Test basic AQL queries."""

    @pytest.fixture(autouse=True)
    def setup_db(self):
        """Ensure database is initialized."""
        db = get_db()
        init_schema(db)
        yield db

    def test_aql_query_execution(self, setup_db):
        """Test basic AQL query execution."""
        db = setup_db

        query = "RETURN 1 + 1"
        cursor = db.aql.execute(query)
        result = next(cursor)

        assert result == 2

    def test_insert_and_query_vulnerability(self, setup_db):
        """Test inserting and querying a vulnerability."""
        db = setup_db

        # Insert test document
        test_cve = {
            '_key': 'cve_test_1234',
            'cve_id': 'CVE-TEST-1234',
            'description': 'Test vulnerability',
            'cvss_v3_score': 9.8,
        }

        db.collection('vulnerabilities').insert(test_cve, overwrite=True)

        # Query it back
        query = """
        FOR v IN vulnerabilities
            FILTER v._key == @key
            RETURN v
        """

        cursor = db.aql.execute(query, bind_vars={'key': 'cve_test_1234'})
        result = next(cursor, None)

        assert result is not None
        assert result['cve_id'] == 'CVE-TEST-1234'
        assert result['cvss_v3_score'] == 9.8

        # Cleanup
        db.collection('vulnerabilities').delete('cve_test_1234')

    def test_graph_traversal(self, setup_db):
        """Test basic graph traversal query."""
        db = setup_db

        # Clean up any existing test data first
        db.collection('vulnerabilities').delete('cve_test_9999', ignore_missing=True)
        db.collection('weaknesses').delete('cwe_test_9999', ignore_missing=True)

        # Insert test data (use unique test IDs to avoid constraint violations)
        cve = {
            '_key': 'cve_test_9999',
            'cve_id': 'CVE-TEST-9999',
        }
        cwe = {
            '_key': 'cwe_test_9999',
            'cwe_id': 'CWE-TEST-9999',  # Use unique test ID to avoid conflicts
            'name': 'Test Weakness',
        }
        edge = {
            '_from': 'vulnerabilities/cve_test_9999',
            '_to': 'weaknesses/cwe_test_9999',
        }

        db.collection('vulnerabilities').insert(cve, overwrite=True)
        db.collection('weaknesses').insert(cwe, overwrite=True)
        db.collection('has_weakness').insert(edge, overwrite=True)

        # Traverse
        query = """
        FOR v, e IN 1..1 OUTBOUND 'vulnerabilities/cve_test_9999' has_weakness
            RETURN v.cwe_id
        """

        cursor = db.aql.execute(query)
        result = list(cursor)

        assert len(result) > 0
        assert 'CWE-TEST-9999' in result

        # Cleanup
        db.collection('vulnerabilities').delete('cve_test_9999')
        db.collection('weaknesses').delete('cwe_test_9999')
