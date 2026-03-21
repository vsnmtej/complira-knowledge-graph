"""
Performance tests for regulatory blast radius queries.

Validates that blast radius queries complete in <5 seconds.
Run with: pytest -m performance
"""

import pytest
import time
from complira_graph.db import get_db, init_schema


def _connect_db():
    """Attempt DB connection, skip test if unavailable."""
    try:
        db = get_db()
        # Verify connection is actually live
        db.version()
        return db
    except Exception as e:
        pytest.skip(f"ArangoDB not available: {e}")


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.requires_db
class TestBlastRadiusPerformance:
    """Performance tests for blast radius queries."""

    @pytest.fixture(scope='class', autouse=True)
    def setup_test_data(self):
        """Setup test data for performance testing."""
        db = _connect_db()
        init_schema(db)

        # Insert test CVE
        cve = {
            '_key': 'cve_perf_test',
            'cve_id': 'CVE-PERF-TEST',
            'description': 'Performance test vulnerability',
            'cvss_v3_score': 9.8,
            'cvss_v3_vector': 'CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H',
            'published': '2024-01-01T00:00:00Z',
        }

        cwe = {
            '_key': 'cwe_perf_test',
            'cwe_id': 'CWE-PERF-TEST',  # Use unique test ID to avoid conflicts
            'name': 'Cross-site Scripting',
            'abstraction': 'Base',
        }

        edge = {
            '_from': 'vulnerabilities/cve_perf_test',
            '_to': 'weaknesses/cwe_perf_test',
        }

        db.collection('vulnerabilities').insert(cve, overwrite=True)
        db.collection('weaknesses').insert(cwe, overwrite=True)
        db.collection('has_weakness').insert(edge, overwrite=True)

        yield db

        # Cleanup
        db.collection('vulnerabilities').delete('cve_perf_test', ignore_missing=True)
        db.collection('weaknesses').delete('cwe_perf_test', ignore_missing=True)

    def test_blast_radius_query_performance(self, setup_test_data):
        """Test that blast radius query completes in <5 seconds."""
        db = setup_test_data

        # Blast radius query (simplified version)
        query = """
        LET cve = DOCUMENT('vulnerabilities', @cve_key)

        // Get CWE weaknesses
        LET cwes = (
            FOR v, e IN 1..1 OUTBOUND cve has_weakness
                RETURN {
                    cwe_id: v.cwe_id,
                    name: v.name,
                    abstraction: v.abstraction
                }
        )

        // Get regulatory controls
        LET controls = (
            FOR v, e IN 1..1 OUTBOUND cve maps_to_requirement
                RETURN {
                    control_id: v.control_id,
                    name: v.name,
                    framework: e.framework
                }
        )

        // Get exploits
        LET exploits = (
            FOR v, e IN 1..1 OUTBOUND cve has_exploit
                RETURN {
                    exploit_id: v.exploit_id,
                    name: v.name
                }
        )

        RETURN {
            cve: {
                cve_id: cve.cve_id,
                description: cve.description,
                cvss_v3_score: cve.cvss_v3_score
            },
            cwes: cwes,
            controls: controls,
            exploits: exploits,
            summary: {
                total_cwes: LENGTH(cwes),
                total_controls: LENGTH(controls),
                total_exploits: LENGTH(exploits)
            }
        }
        """

        # Measure execution time
        start_time = time.time()

        cursor = db.aql.execute(query, bind_vars={'cve_key': 'cve_perf_test'})
        result = next(cursor, None)

        execution_time = time.time() - start_time

        # Assertions
        assert result is not None, "Query should return results"
        assert result['cve']['cve_id'] == 'CVE-PERF-TEST'
        assert execution_time < 5.0, \
            f"Blast radius query took {execution_time:.2f}s (should be <5s)"

        print(f"\n✓ Blast radius query completed in {execution_time:.3f} seconds")

    def test_multi_hop_traversal_performance(self, setup_test_data):
        """Test multi-hop graph traversal performance."""
        db = setup_test_data

        # 3-hop traversal query (traverse all edge collections)
        query = """
        FOR v, e, p IN 1..3 OUTBOUND 'vulnerabilities/cve_perf_test'
            has_weakness, has_exploit, exploited_in_wild, affects, has_epss
            LIMIT 100
            RETURN {path_length: LENGTH(p.edges)}
        """

        start_time = time.time()

        cursor = db.aql.execute(query)
        results = list(cursor)

        execution_time = time.time() - start_time

        assert execution_time < 10.0, \
            f"3-hop traversal took {execution_time:.2f}s (should be <10s)"

        print(f"\n✓ 3-hop traversal completed in {execution_time:.3f} seconds")
        print(f"  Found {len(results)} paths")


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.requires_db
class TestAggregationPerformance:
    """Performance tests for aggregation queries."""

    def test_collection_count_performance(self):
        """Test that collection counts can be retrieved quickly."""
        db = _connect_db()

        start_time = time.time()

        collections = [
            'vulnerabilities', 'weaknesses', 'attack_techniques',
            'attack_patterns', 'components', 'oscal_controls'
        ]

        counts = {}
        for coll_name in collections:
            if db.has_collection(coll_name):
                counts[coll_name] = db.collection(coll_name).count()

        execution_time = time.time() - start_time

        assert execution_time < 2.0, \
            f"Collection counts took {execution_time:.2f}s (should be <2s)"

        print(f"\n✓ Retrieved counts for {len(counts)} collections in {execution_time:.3f} seconds")

    def test_cvss_aggregation_performance(self):
        """Test CVSS score aggregation performance."""
        db = _connect_db()

        query = """
        FOR v IN vulnerabilities
            FILTER v.cvss_v3_score != null
            COLLECT severity = (
                v.cvss_v3_score >= 9.0 ? 'critical' :
                v.cvss_v3_score >= 7.0 ? 'high' :
                v.cvss_v3_score >= 4.0 ? 'medium' : 'low'
            )
            WITH COUNT INTO count
            RETURN {severity: severity, count: count}
        """

        start_time = time.time()

        cursor = db.aql.execute(query)
        results = list(cursor)

        execution_time = time.time() - start_time

        assert execution_time < 5.0, \
            f"CVSS aggregation took {execution_time:.2f}s (should be <5s)"

        print(f"\n✓ CVSS aggregation completed in {execution_time:.3f} seconds")
        print(f"  Results: {results}")
