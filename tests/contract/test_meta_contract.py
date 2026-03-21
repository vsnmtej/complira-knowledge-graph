"""
API Contract Tests for Meta/System Endpoints.

These tests ensure:
1. Backend API responses match the documented contract
2. Frontend mock data matches real API responses
3. No breaking changes to API structure
4. Response models validate correctly
"""

import json
import pytest
from pathlib import Path


class TestMetaCoverageContract:
    """Contract tests for GET /v1/meta/coverage - Get reference data coverage stats."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses."""
        return Path("tests/fixtures/api_responses")

    def test_coverage_response_contract(self, mock_responses_dir):
        """
        Test: GET /v1/meta/coverage response matches contract.

        Validates:
        - Response structure matches expected schema
        - All required sections present (vertices, edges, enrichment_funnel, data_limitations)
        - Field types correct
        - Vertex and edge counts are integers
        """
        with open(mock_responses_dir / "meta_coverage.json") as f:
            mock_data = json.load(f)

        # Validate outer APIResponse wrapper
        assert "success" in mock_data
        assert "data" in mock_data
        assert "metadata" in mock_data

        # Validate coverage data structure
        data = mock_data["data"]
        required_sections = ["vertices", "edges", "enrichment_funnel", "data_limitations", "total_edges", "recommendations"]
        for section in required_sections:
            assert section in data, f"Missing required section: {section}"

        # Validate vertices section
        vertices = data["vertices"]
        required_vertex_collections = [
            "vulnerabilities", "weaknesses", "attack_patterns",
            "attack_techniques", "oscal_controls", "regulatory_requirements"
        ]
        for collection in required_vertex_collections:
            assert collection in vertices, f"Missing vertex collection: {collection}"
            assert isinstance(vertices[collection], int), f"{collection} should be integer"
            assert vertices[collection] > 0, f"{collection} should have positive count"

        # Validate edges section
        edges = data["edges"]
        required_edge_collections = [
            "has_weakness", "capec_relates_to_cwe", "capec_maps_to_attack",
            "technique_mitigated_by_control", "violates_requirement"
        ]
        for collection in required_edge_collections:
            assert collection in edges, f"Missing edge collection: {collection}"
            assert isinstance(edges[collection], int), f"{collection} should be integer"
            assert edges[collection] > 0, f"{collection} should have positive count"

        # Validate total_edges
        assert isinstance(data["total_edges"], int)
        assert data["total_edges"] == sum(edges.values()), "total_edges should equal sum of edge counts"

    def test_coverage_enrichment_funnel_structure(self, mock_responses_dir):
        """
        Test: GET /v1/meta/coverage enrichment funnel has correct structure.

        Validates:
        - sample_size is integer
        - sample_year is integer
        - Percentage fields are present and numeric
        - estimated_coverage has expected structure
        """
        with open(mock_responses_dir / "meta_coverage.json") as f:
            mock_data = json.load(f)

        funnel = mock_data["data"]["enrichment_funnel"]

        # Validate sample info
        assert "sample_size" in funnel
        assert isinstance(funnel["sample_size"], int)
        assert funnel["sample_size"] == 100, "Sample size should be 100"

        assert "sample_year" in funnel
        assert isinstance(funnel["sample_year"], int)
        assert funnel["sample_year"] >= 2024, "Sample year should be current or recent"

        # Validate percentages
        assert "cve_to_cwe_percent" in funnel
        assert "cve_to_capec_percent" in funnel
        assert "cve_to_attack_percent" in funnel
        assert isinstance(funnel["cve_to_cwe_percent"], int)
        assert isinstance(funnel["cve_to_capec_percent"], int)
        assert isinstance(funnel["cve_to_attack_percent"], int)

        # Validate percentages are in valid range
        assert 0 <= funnel["cve_to_cwe_percent"] <= 100
        assert 0 <= funnel["cve_to_capec_percent"] <= 100
        assert 0 <= funnel["cve_to_attack_percent"] <= 100

        # Validate funnel decreases (CVE->CWE >= CVE->CAPEC >= CVE->ATT&CK)
        assert funnel["cve_to_cwe_percent"] >= funnel["cve_to_capec_percent"]
        assert funnel["cve_to_capec_percent"] >= funnel["cve_to_attack_percent"]

        # Validate estimated_coverage
        assert "estimated_coverage" in funnel
        coverage = funnel["estimated_coverage"]
        assert "cwe_weaknesses" in coverage
        assert "capec_patterns" in coverage
        assert "attack_techniques" in coverage
        assert "nist_controls" in coverage
        for key, value in coverage.items():
            assert isinstance(value, str), f"Coverage estimate {key} should be string"
            assert "%" in value or "CVE" in value, f"Coverage estimate should mention percentage"

    def test_coverage_data_limitations_structure(self, mock_responses_dir):
        """
        Test: GET /v1/meta/coverage data limitations has correct structure.

        Validates:
        - capec_attack_mappings limitation present
        - control_to_regulatory limitation present
        - Each limitation has required fields
        """
        with open(mock_responses_dir / "meta_coverage.json") as f:
            mock_data = json.load(f)

        limitations = mock_data["data"]["data_limitations"]

        # Validate capec_attack_mappings limitation
        assert "capec_attack_mappings" in limitations
        capec_limit = limitations["capec_attack_mappings"]
        assert "total_capecs" in capec_limit
        assert "capecs_with_attack_mappings" in capec_limit
        assert "coverage_percent" in capec_limit
        assert "source" in capec_limit
        assert "limitation" in capec_limit

        assert isinstance(capec_limit["total_capecs"], int)
        assert isinstance(capec_limit["capecs_with_attack_mappings"], int)
        assert isinstance(capec_limit["coverage_percent"], (int, float))
        assert isinstance(capec_limit["source"], str)
        assert isinstance(capec_limit["limitation"], str)

        # Validate coverage_percent is reasonable (~29% according to MITRE)
        assert 0 < capec_limit["coverage_percent"] < 100
        assert 20 <= capec_limit["coverage_percent"] <= 40, "CAPEC-ATT&CK coverage should be ~29%"

        # Validate control_to_regulatory limitation
        assert "control_to_regulatory" in limitations
        control_limit = limitations["control_to_regulatory"]
        assert "status" in control_limit
        assert "reason" in control_limit
        assert "workaround" in control_limit

        assert control_limit["status"] == "not_implemented"
        assert isinstance(control_limit["reason"], str)
        assert isinstance(control_limit["workaround"], str)

    def test_coverage_recommendations_structure(self, mock_responses_dir):
        """
        Test: GET /v1/meta/coverage recommendations are actionable.

        Validates:
        - recommendations is a list
        - Contains at least 4 recommendations
        - Each recommendation is a non-empty string
        - Recommendations mention specific percentages or use cases
        """
        with open(mock_responses_dir / "meta_coverage.json") as f:
            mock_data = json.load(f)

        recommendations = mock_data["data"]["recommendations"]

        assert isinstance(recommendations, list)
        assert len(recommendations) >= 4, "Should have at least 4 recommendations"

        for rec in recommendations:
            assert isinstance(rec, str)
            assert len(rec) > 20, "Recommendations should be meaningful text"
            # Should mention percentages or specific use cases
            assert any(keyword in rec for keyword in ["%", "CVE", "use", "threat", "attack", "control", "regulatory"])

    def test_coverage_metadata_structure(self, mock_responses_dir):
        """
        Test: GET /v1/meta/coverage metadata includes standard fields.

        Validates:
        - metadata includes cache_hit and api_version
        - cache_hit is false (live query)
        """
        with open(mock_responses_dir / "meta_coverage.json") as f:
            mock_data = json.load(f)

        assert "metadata" in mock_data
        metadata = mock_data["metadata"]

        assert "cache_hit" in metadata
        assert "api_version" in metadata

        assert isinstance(metadata["cache_hit"], bool)
        assert metadata["cache_hit"] is False, "Coverage queries should not be cached"
        assert metadata["api_version"] == "v1"

    def test_coverage_realistic_data_values(self, mock_responses_dir):
        """
        Test: GET /v1/meta/coverage contains realistic data values.

        Validates:
        - CVE count is 200K+ (realistic for NVD database)
        - KEV count is 1000+ (realistic for CISA KEV)
        - Enrichment percentages are realistic (85%+ for CWE)
        """
        with open(mock_responses_dir / "meta_coverage.json") as f:
            mock_data = json.load(f)

        data = mock_data["data"]

        # Validate realistic CVE count
        cve_count = data["vertices"]["vulnerabilities"]
        assert cve_count >= 200000, "CVE count should be 200K+ for realistic dataset"

        # Validate realistic CWE count
        cwe_count = data["vertices"]["weaknesses"]
        assert 900 <= cwe_count <= 1000, "CWE count should be ~900-1000"

        # Validate realistic CAPEC count
        capec_count = data["vertices"]["attack_patterns"]
        assert 500 <= capec_count <= 600, "CAPEC count should be ~500-600"

        # Validate realistic ATT&CK technique count
        attack_count = data["vertices"]["attack_techniques"]
        assert 600 <= attack_count <= 800, "ATT&CK technique count should be ~600-800"

        # Validate enrichment percentages are realistic
        funnel = data["enrichment_funnel"]
        assert funnel["cve_to_cwe_percent"] >= 85, "CWE enrichment should be 85%+ (high coverage)"
        assert funnel["cve_to_capec_percent"] >= 60, "CAPEC enrichment should be 60%+ (good coverage)"
        assert funnel["cve_to_attack_percent"] >= 40, "ATT&CK enrichment should be 40%+ (decent coverage)"


class TestMetaStatsContract:
    """Contract tests for GET /v1/meta/stats - Get system statistics."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses."""
        return Path("tests/fixtures/api_responses")

    def test_stats_response_contract(self, mock_responses_dir):
        """
        Test: GET /v1/meta/stats response matches contract.

        Validates:
        - Response structure matches expected schema
        - All required fields present (database, collections, totals)
        - Field types correct
        """
        with open(mock_responses_dir / "meta_stats.json") as f:
            mock_data = json.load(f)

        # Validate outer APIResponse wrapper
        assert "success" in mock_data
        assert "data" in mock_data
        assert "metadata" in mock_data

        # Validate stats data structure
        data = mock_data["data"]
        required_fields = ["database", "collections", "total_documents", "total_edges"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Validate database name
        assert isinstance(data["database"], str)
        assert data["database"] == "complira_graph"

        # Validate collections
        assert isinstance(data["collections"], dict)
        assert len(data["collections"]) > 0, "Should have at least one collection"

        # Validate totals
        assert isinstance(data["total_documents"], int)
        assert isinstance(data["total_edges"], int)
        assert data["total_documents"] > 0
        assert data["total_edges"] > 0

    def test_stats_collections_structure(self, mock_responses_dir):
        """
        Test: GET /v1/meta/stats collections have correct structure.

        Validates:
        - All expected collections present
        - No system collections (starting with _)
        - All counts are positive integers
        """
        with open(mock_responses_dir / "meta_stats.json") as f:
            mock_data = json.load(f)

        collections = mock_data["data"]["collections"]

        # Validate expected collections present
        expected_collections = [
            "vulnerabilities", "weaknesses", "attack_patterns",
            "attack_techniques", "oscal_controls", "regulatory_requirements",
            "has_weakness", "capec_relates_to_cwe", "capec_maps_to_attack",
            "technique_mitigated_by_control", "violates_requirement"
        ]
        for coll in expected_collections:
            assert coll in collections, f"Missing collection: {coll}"
            assert isinstance(collections[coll], int)
            assert collections[coll] > 0

        # Validate no system collections
        for coll_name in collections.keys():
            assert not coll_name.startswith("_"), \
                f"System collection {coll_name} should be filtered out"

    def test_stats_totals_calculated_correctly(self, mock_responses_dir):
        """
        Test: GET /v1/meta/stats totals are calculated correctly.

        Validates:
        - total_documents sums vertex collections
        - total_edges sums edge collections
        - Calculations match expected values
        """
        with open(mock_responses_dir / "meta_stats.json") as f:
            mock_data = json.load(f)

        data = mock_data["data"]
        collections = data["collections"]

        # Calculate expected total_edges
        edge_collections = [
            "has_weakness", "capec_relates_to_cwe", "capec_maps_to_attack",
            "technique_mitigated_by_control", "violates_requirement"
        ]
        expected_edges = sum(collections[coll] for coll in edge_collections if coll in collections)

        assert data["total_edges"] == expected_edges, \
            "total_edges should equal sum of edge collection counts"

        # Verify total_documents is sum of vertex collections
        vertex_collections = [
            "vulnerabilities", "weaknesses", "attack_patterns",
            "attack_techniques", "oscal_controls", "regulatory_requirements"
        ]
        expected_docs = sum(collections[coll] for coll in vertex_collections if coll in collections)

        assert data["total_documents"] == expected_docs, \
            "total_documents should equal sum of vertex collection counts"

    def test_stats_metadata_structure(self, mock_responses_dir):
        """
        Test: GET /v1/meta/stats metadata includes standard fields.

        Validates:
        - metadata includes cache_hit and api_version
        - cache_hit is false (live query)
        """
        with open(mock_responses_dir / "meta_stats.json") as f:
            mock_data = json.load(f)

        assert "metadata" in mock_data
        metadata = mock_data["metadata"]

        assert "cache_hit" in metadata
        assert "api_version" in metadata

        assert isinstance(metadata["cache_hit"], bool)
        assert metadata["cache_hit"] is False, "Stats queries should not be cached"
        assert metadata["api_version"] == "v1"

    def test_stats_realistic_data_values(self, mock_responses_dir):
        """
        Test: GET /v1/meta/stats contains realistic data values.

        Validates:
        - Collection sizes are realistic for production dataset
        - Edge counts exceed vertex counts (graph should be well-connected)
        - Total documents is reasonable
        """
        with open(mock_responses_dir / "meta_stats.json") as f:
            mock_data = json.load(f)

        data = mock_data["data"]
        collections = data["collections"]

        # Validate realistic collection sizes
        assert collections["vulnerabilities"] >= 200000, "Should have 200K+ CVEs"
        assert collections["weaknesses"] >= 900, "Should have 900+ CWEs"
        assert collections["attack_patterns"] >= 500, "Should have 500+ CAPEC patterns"

        # Validate edge counts are substantial
        assert collections["has_weakness"] >= 200000, "Most CVEs should have CWE mappings"
        assert collections["violates_requirement"] >= 5000000, "Should have millions of CVE-regulatory edges"

        # Validate total_edges exceeds total_documents (well-connected graph)
        assert data["total_edges"] > data["total_documents"], \
            "Graph should be well-connected (more edges than documents)"


class TestMetaContractBackwardCompatibility:
    """Tests to ensure no breaking changes to meta endpoint contracts."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses."""
        return Path("tests/fixtures/api_responses")

    def test_coverage_required_fields_not_removed(self, mock_responses_dir):
        """
        Test: Coverage response required fields are never removed.

        Prevents breaking changes to coverage endpoint contract.
        """
        with open(mock_responses_dir / "meta_coverage.json") as f:
            mock_data = json.load(f)

        data = mock_data["data"]

        # These fields MUST always be present
        mandatory_sections = ["vertices", "edges", "enrichment_funnel", "data_limitations", "total_edges", "recommendations"]

        for section in mandatory_sections:
            assert section in data, \
                f"Breaking change detected: Required section '{section}' missing from coverage response"

        # Validate critical vertex collections
        mandatory_vertices = ["vulnerabilities", "weaknesses", "attack_patterns", "attack_techniques"]
        for vertex in mandatory_vertices:
            assert vertex in data["vertices"], \
                f"Breaking change detected: Required vertex collection '{vertex}' missing"

        # Validate critical edge collections
        mandatory_edges = ["has_weakness", "capec_relates_to_cwe", "violates_requirement"]
        for edge in mandatory_edges:
            assert edge in data["edges"], \
                f"Breaking change detected: Required edge collection '{edge}' missing"

    def test_stats_required_fields_not_removed(self, mock_responses_dir):
        """
        Test: Stats response required fields are never removed.

        Prevents breaking changes to stats endpoint contract.
        """
        with open(mock_responses_dir / "meta_stats.json") as f:
            mock_data = json.load(f)

        data = mock_data["data"]

        # These fields MUST always be present
        mandatory_fields = ["database", "collections", "total_documents", "total_edges"]

        for field in mandatory_fields:
            assert field in data, \
                f"Breaking change detected: Required field '{field}' missing from stats response"

        # Validate database name hasn't changed
        assert data["database"] == "complira_graph", \
            "Breaking change detected: Database name changed"


class TestMetaContractConsistency:
    """Tests to ensure consistency between coverage and stats endpoints."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses."""
        return Path("tests/fixtures/api_responses")

    def test_coverage_and_stats_collection_counts_match(self, mock_responses_dir):
        """
        Test: Coverage and stats endpoints return consistent collection counts.

        Validates:
        - Vertex counts match between coverage.vertices and stats.collections
        - Edge counts match between coverage.edges and stats.collections
        """
        with open(mock_responses_dir / "meta_coverage.json") as f:
            coverage_data = json.load(f)["data"]

        with open(mock_responses_dir / "meta_stats.json") as f:
            stats_data = json.load(f)["data"]

        # Validate vertex counts match
        for vertex_name, count in coverage_data["vertices"].items():
            assert vertex_name in stats_data["collections"], \
                f"Inconsistency: {vertex_name} in coverage but not in stats"
            assert stats_data["collections"][vertex_name] == count, \
                f"Inconsistency: {vertex_name} count differs between coverage ({count}) and stats ({stats_data['collections'][vertex_name]})"

        # Validate edge counts match
        for edge_name, count in coverage_data["edges"].items():
            assert edge_name in stats_data["collections"], \
                f"Inconsistency: {edge_name} in coverage but not in stats"
            assert stats_data["collections"][edge_name] == count, \
                f"Inconsistency: {edge_name} count differs between coverage ({count}) and stats ({stats_data['collections'][edge_name]})"

    def test_coverage_and_stats_use_same_database(self, mock_responses_dir):
        """
        Test: Coverage and stats endpoints reference the same database.

        Validates:
        - Both endpoints query complira_graph database
        """
        with open(mock_responses_dir / "meta_coverage.json") as f:
            coverage_data = json.load(f)

        with open(mock_responses_dir / "meta_stats.json") as f:
            stats_data = json.load(f)["data"]

        # Stats explicitly includes database name
        assert stats_data["database"] == "complira_graph"

        # Coverage should reference same data (implicit validation via matching counts)
        # Both should have same vertices and edges counts
        assert len(coverage_data["data"]["vertices"]) > 0
        assert len(coverage_data["data"]["edges"]) > 0


class TestMetaContractTimestampFormats:
    """Tests for consistent response structure across meta endpoints."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses."""
        return Path("tests/fixtures/api_responses")

    def test_all_responses_have_standard_wrapper(self, mock_responses_dir):
        """
        Test: All meta endpoints use standard APIResponse wrapper.

        Validates:
        - success field is boolean
        - data field contains response data
        - metadata field contains cache_hit and api_version
        """
        mock_files = ["meta_coverage.json", "meta_stats.json"]

        for mock_file in mock_files:
            with open(mock_responses_dir / mock_file) as f:
                mock_data = json.load(f)

            # Validate wrapper structure
            assert "success" in mock_data, f"{mock_file} missing 'success' field"
            assert "data" in mock_data, f"{mock_file} missing 'data' field"
            assert "metadata" in mock_data, f"{mock_file} missing 'metadata' field"

            assert isinstance(mock_data["success"], bool)
            assert mock_data["success"] is True

            # Validate metadata
            metadata = mock_data["metadata"]
            assert "cache_hit" in metadata
            assert "api_version" in metadata
            assert isinstance(metadata["cache_hit"], bool)
            assert metadata["api_version"] == "v1"
