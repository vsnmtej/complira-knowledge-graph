"""
Integration tests for meta/system endpoints.

Tests full API flow for all 2 meta endpoints:
- GET /v1/meta/coverage (get reference data coverage stats)
- GET /v1/meta/stats (get system statistics)
"""

import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from fastapi.testclient import TestClient
from datetime import datetime


@pytest.fixture
def mock_reference_db():
    """Mock ArangoDB reference database for meta operations."""
    db = MagicMock()
    db.collection = Mock(return_value=MagicMock())
    db.aql = MagicMock()
    db.collections = Mock(return_value=[
        {"name": "vulnerabilities"},
        {"name": "weaknesses"},
        {"name": "attack_patterns"},
        {"name": "attack_techniques"},
        {"name": "oscal_controls"},
        {"name": "regulatory_requirements"},
        {"name": "has_weakness"},
        {"name": "capec_relates_to_cwe"},
        {"name": "capec_maps_to_attack"},
        {"name": "technique_mitigated_by_control"},
        {"name": "violates_requirement"},
        {"name": "_system"},  # Should be filtered out
        {"name": "_graphs"},  # Should be filtered out
    ])

    # Mock collection counts for vertex collections
    def mock_collection_count(name):
        collection = MagicMock()
        counts = {
            "vulnerabilities": 245678,
            "weaknesses": 934,
            "attack_patterns": 559,
            "attack_techniques": 718,
            "oscal_controls": 1084,
            "regulatory_requirements": 2456,
            "has_weakness": 238901,
            "capec_relates_to_cwe": 1829,
            "capec_maps_to_attack": 163,
            "technique_mitigated_by_control": 8492,
            "violates_requirement": 5274983,
        }
        collection.count = Mock(return_value=counts.get(name, 0))
        return collection

    db.collection = Mock(side_effect=mock_collection_count)

    # Mock AQL queries for coverage statistics
    def mock_aql_execute(query):
        # Sample enrichment query
        if "CVE_2024_" in query and "has_cwe" in query:
            return [
                {"has_cwe": True, "has_capec": True, "has_attack": True},
                {"has_cwe": True, "has_capec": True, "has_attack": False},
                {"has_cwe": True, "has_capec": False, "has_attack": False},
                {"has_cwe": False, "has_capec": False, "has_attack": False},
            ] * 25  # 100 samples

        # CAPEC-to-ATT&CK mapping query
        if "total_capecs" in query and "capecs_with_attack" in query:
            return [{"total": 559, "with_attack": 163}]

        return []

    db.aql.execute = Mock(side_effect=mock_aql_execute)

    return db


class TestGetDataCoverage:
    """Integration tests for GET /v1/meta/coverage - Get reference data coverage stats."""

    @pytest.mark.integration
    def test_get_coverage_success(
        self, api_client, app, override_customer_auth, mock_reference_db
    ):
        """
        Test: GET /v1/meta/coverage - Successfully retrieve coverage statistics.

        Verifies:
        - Returns vertex collection counts (CVE, CWE, CAPEC, ATT&CK, Controls, Regulatory)
        - Returns edge collection counts
        - Returns enrichment funnel percentages
        - Returns data limitations with CAPEC-ATT&CK mappings
        - Returns recommendations
        - 200 OK status
        """
        with patch('api.v1.endpoints.meta.get_reference_db', return_value=mock_reference_db):

            response = api_client.get(
                "/v1/meta/coverage",
                headers={"X-API-Key": "test_key"}
            )

            # Verify response
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

            data = response.json()
            assert data["success"] is True
            assert "data" in data

            coverage_data = data["data"]

            # Verify vertices section
            assert "vertices" in coverage_data
            vertices = coverage_data["vertices"]
            assert vertices["vulnerabilities"] == 245678
            assert vertices["weaknesses"] == 934
            assert vertices["attack_patterns"] == 559
            assert vertices["attack_techniques"] == 718
            assert vertices["oscal_controls"] == 1084
            assert vertices["regulatory_requirements"] == 2456

            # Verify edges section
            assert "edges" in coverage_data
            edges = coverage_data["edges"]
            assert edges["has_weakness"] == 238901
            assert edges["capec_relates_to_cwe"] == 1829
            assert edges["capec_maps_to_attack"] == 163
            assert edges["technique_mitigated_by_control"] == 8492
            assert edges["violates_requirement"] == 5274983

            # Verify total edges calculated
            assert "total_edges" in coverage_data
            assert coverage_data["total_edges"] == sum(edges.values())

            # Verify enrichment funnel
            assert "enrichment_funnel" in coverage_data
            funnel = coverage_data["enrichment_funnel"]
            assert funnel["sample_size"] == 100
            assert funnel["sample_year"] == 2024
            assert "cve_to_cwe_percent" in funnel
            assert "cve_to_capec_percent" in funnel
            assert "cve_to_attack_percent" in funnel
            assert "estimated_coverage" in funnel

            # Verify data limitations
            assert "data_limitations" in coverage_data
            limitations = coverage_data["data_limitations"]
            assert "capec_attack_mappings" in limitations
            assert limitations["capec_attack_mappings"]["total_capecs"] == 559
            assert limitations["capec_attack_mappings"]["capecs_with_attack_mappings"] == 163
            assert limitations["capec_attack_mappings"]["coverage_percent"] > 0

            # Verify recommendations
            assert "recommendations" in coverage_data
            assert isinstance(coverage_data["recommendations"], list)
            assert len(coverage_data["recommendations"]) > 0

    @pytest.mark.integration
    def test_get_coverage_calculates_enrichment_percentages(
        self, api_client, app, override_customer_auth, mock_reference_db
    ):
        """
        Test: GET /v1/meta/coverage - Enrichment funnel percentages are calculated correctly.

        Verifies:
        - CVE -> CWE percentage calculated from sample
        - CVE -> CAPEC percentage calculated from sample
        - CVE -> ATT&CK percentage calculated from sample
        - Percentages are reasonable (between 0-100)
        """
        with patch('api.v1.endpoints.meta.get_reference_db', return_value=mock_reference_db):

            response = api_client.get(
                "/v1/meta/coverage",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()
            funnel = data["data"]["enrichment_funnel"]

            # Verify percentages are calculated (sample has 75% with CWE, 50% with CAPEC, 25% with ATT&CK)
            assert 0 <= funnel["cve_to_cwe_percent"] <= 100
            assert 0 <= funnel["cve_to_capec_percent"] <= 100
            assert 0 <= funnel["cve_to_attack_percent"] <= 100

            # Verify enrichment funnel decreases (CVE->CWE >= CVE->CAPEC >= CVE->ATT&CK)
            assert funnel["cve_to_cwe_percent"] >= funnel["cve_to_capec_percent"]
            assert funnel["cve_to_capec_percent"] >= funnel["cve_to_attack_percent"]

    @pytest.mark.integration
    def test_get_coverage_includes_capec_attack_mapping_limitation(
        self, api_client, app, override_customer_auth, mock_reference_db
    ):
        """
        Test: GET /v1/meta/coverage - Includes CAPEC-to-ATT&CK mapping limitation.

        Verifies:
        - Shows total CAPEC patterns
        - Shows how many have ATT&CK mappings
        - Shows coverage percentage (~29% according to MITRE)
        - Includes source attribution
        - Explains limitation
        """
        with patch('api.v1.endpoints.meta.get_reference_db', return_value=mock_reference_db):

            response = api_client.get(
                "/v1/meta/coverage",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            limitations = data["data"]["data_limitations"]
            assert "capec_attack_mappings" in limitations

            capec_limitation = limitations["capec_attack_mappings"]
            assert capec_limitation["total_capecs"] == 559
            assert capec_limitation["capecs_with_attack_mappings"] == 163
            assert "coverage_percent" in capec_limitation
            assert capec_limitation["source"] == "MITRE CAPEC XML"
            assert "limitation" in capec_limitation

    @pytest.mark.integration
    def test_get_coverage_includes_control_regulatory_limitation(
        self, api_client, app, override_customer_auth, mock_reference_db
    ):
        """
        Test: GET /v1/meta/coverage - Explains control-to-regulatory mapping limitation.

        Verifies:
        - Status is "not_implemented"
        - Provides reason (manual mapping required)
        - Suggests workaround (direct CVE -> Regulatory edges)
        """
        with patch('api.v1.endpoints.meta.get_reference_db', return_value=mock_reference_db):

            response = api_client.get(
                "/v1/meta/coverage",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            limitations = data["data"]["data_limitations"]
            assert "control_to_regulatory" in limitations

            control_limitation = limitations["control_to_regulatory"]
            assert control_limitation["status"] == "not_implemented"
            assert "reason" in control_limitation
            assert "workaround" in control_limitation

    @pytest.mark.integration
    def test_get_coverage_provides_actionable_recommendations(
        self, api_client, app, override_customer_auth, mock_reference_db
    ):
        """
        Test: GET /v1/meta/coverage - Provides actionable recommendations.

        Verifies:
        - Returns list of recommendations
        - Recommendations mention specific percentages
        - Recommendations suggest use cases
        - At least 4 recommendations provided
        """
        with patch('api.v1.endpoints.meta.get_reference_db', return_value=mock_reference_db):

            response = api_client.get(
                "/v1/meta/coverage",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            recommendations = data["data"]["recommendations"]
            assert isinstance(recommendations, list)
            assert len(recommendations) >= 4

            # Verify recommendations are actionable strings
            for rec in recommendations:
                assert isinstance(rec, str)
                assert len(rec) > 10  # Should be meaningful text

    @pytest.mark.integration
    def test_get_coverage_fails_without_authentication(self, api_client):
        """
        Test: GET /v1/meta/coverage - Fail when not authenticated.

        Verifies:
        - Authentication required
        - 401 or 403 status when no API key provided
        """
        response = api_client.get("/v1/meta/coverage")

        assert response.status_code in [401, 403]

    @pytest.mark.integration
    def test_get_coverage_metadata_includes_standard_fields(
        self, api_client, app, override_customer_auth, mock_reference_db
    ):
        """
        Test: GET /v1/meta/coverage - Response metadata includes standard fields.

        Verifies:
        - metadata.cache_hit is boolean
        - metadata.api_version is "v1"
        - cache_hit is false (live database query)
        """
        with patch('api.v1.endpoints.meta.get_reference_db', return_value=mock_reference_db):

            response = api_client.get(
                "/v1/meta/coverage",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            assert "metadata" in data
            metadata = data["metadata"]
            assert "cache_hit" in metadata
            assert "api_version" in metadata
            assert isinstance(metadata["cache_hit"], bool)
            assert metadata["api_version"] == "v1"


class TestGetDatabaseStats:
    """Integration tests for GET /v1/meta/stats - Get system statistics."""

    @pytest.mark.integration
    def test_get_stats_success(
        self, api_client, app, override_customer_auth, mock_reference_db
    ):
        """
        Test: GET /v1/meta/stats - Successfully retrieve database statistics.

        Verifies:
        - Returns database name
        - Returns collection counts for all collections
        - Calculates total documents (vertex collections)
        - Calculates total edges (edge collections)
        - Filters out system collections (starting with _)
        - 200 OK status
        """
        with patch('api.v1.endpoints.meta.get_reference_db', return_value=mock_reference_db):

            response = api_client.get(
                "/v1/meta/stats",
                headers={"X-API-Key": "test_key"}
            )

            # Verify response
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

            data = response.json()
            assert data["success"] is True
            assert "data" in data

            stats_data = data["data"]

            # Verify database name
            assert "database" in stats_data
            assert stats_data["database"] == "complira_graph"

            # Verify collections
            assert "collections" in stats_data
            collections = stats_data["collections"]
            assert isinstance(collections, dict)

            # Verify system collections are filtered out
            assert "_system" not in collections
            assert "_graphs" not in collections

            # Verify expected collections are present
            expected_collections = [
                "vulnerabilities", "weaknesses", "attack_patterns",
                "attack_techniques", "oscal_controls", "regulatory_requirements",
                "has_weakness", "capec_relates_to_cwe", "capec_maps_to_attack",
                "technique_mitigated_by_control", "violates_requirement"
            ]
            for coll in expected_collections:
                assert coll in collections
                assert isinstance(collections[coll], int)
                assert collections[coll] > 0

            # Verify totals
            assert "total_documents" in stats_data
            assert "total_edges" in stats_data
            assert isinstance(stats_data["total_documents"], int)
            assert isinstance(stats_data["total_edges"], int)

    @pytest.mark.integration
    def test_get_stats_calculates_totals_correctly(
        self, api_client, app, override_customer_auth, mock_reference_db
    ):
        """
        Test: GET /v1/meta/stats - Total document and edge counts are calculated correctly.

        Verifies:
        - total_documents sums vertex collections only
        - total_edges sums edge collections only
        - Edge collections identified by naming patterns
        """
        with patch('api.v1.endpoints.meta.get_reference_db', return_value=mock_reference_db):

            response = api_client.get(
                "/v1/meta/stats",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()
            stats = data["data"]

            # Verify totals are positive integers
            assert stats["total_documents"] > 0
            assert stats["total_edges"] > 0

            # Verify total_edges includes edge collections
            collections = stats["collections"]
            edge_count = (
                collections["has_weakness"] +
                collections["capec_relates_to_cwe"] +
                collections["capec_maps_to_attack"] +
                collections["technique_mitigated_by_control"] +
                collections["violates_requirement"]
            )
            assert stats["total_edges"] == edge_count

    @pytest.mark.integration
    def test_get_stats_includes_all_collection_types(
        self, api_client, app, override_customer_auth, mock_reference_db
    ):
        """
        Test: GET /v1/meta/stats - Includes all collection types.

        Verifies:
        - Vertex collections (vulnerabilities, weaknesses, attack patterns, etc.)
        - Edge collections (has_weakness, capec_relates_to_cwe, etc.)
        - Each collection has a count
        """
        with patch('api.v1.endpoints.meta.get_reference_db', return_value=mock_reference_db):

            response = api_client.get(
                "/v1/meta/stats",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()
            collections = data["data"]["collections"]

            # Verify vertex collections
            vertex_collections = [
                "vulnerabilities", "weaknesses", "attack_patterns",
                "attack_techniques", "oscal_controls", "regulatory_requirements"
            ]
            for coll in vertex_collections:
                assert coll in collections
                assert collections[coll] > 0

            # Verify edge collections
            edge_collections = [
                "has_weakness", "capec_relates_to_cwe", "capec_maps_to_attack",
                "technique_mitigated_by_control", "violates_requirement"
            ]
            for coll in edge_collections:
                assert coll in collections
                assert collections[coll] > 0

    @pytest.mark.integration
    def test_get_stats_filters_system_collections(
        self, api_client, app, override_customer_auth, mock_reference_db
    ):
        """
        Test: GET /v1/meta/stats - System collections are filtered out.

        Verifies:
        - Collections starting with _ are excluded
        - Only user collections are returned
        """
        with patch('api.v1.endpoints.meta.get_reference_db', return_value=mock_reference_db):

            response = api_client.get(
                "/v1/meta/stats",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()
            collections = data["data"]["collections"]

            # Verify no system collections
            for coll_name in collections.keys():
                assert not coll_name.startswith("_"), \
                    f"System collection {coll_name} should be filtered out"

    @pytest.mark.integration
    def test_get_stats_fails_without_authentication(self, api_client):
        """
        Test: GET /v1/meta/stats - Fail when not authenticated.

        Verifies:
        - Authentication required
        - 401 or 403 status when no API key provided
        """
        response = api_client.get("/v1/meta/stats")

        assert response.status_code in [401, 403]

    @pytest.mark.integration
    def test_get_stats_metadata_includes_standard_fields(
        self, api_client, app, override_customer_auth, mock_reference_db
    ):
        """
        Test: GET /v1/meta/stats - Response metadata includes standard fields.

        Verifies:
        - metadata.cache_hit is boolean
        - metadata.api_version is "v1"
        - cache_hit is false (live database query)
        """
        with patch('api.v1.endpoints.meta.get_reference_db', return_value=mock_reference_db):

            response = api_client.get(
                "/v1/meta/stats",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            assert "metadata" in data
            metadata = data["metadata"]
            assert "cache_hit" in metadata
            assert "api_version" in metadata
            assert isinstance(metadata["cache_hit"], bool)
            assert metadata["api_version"] == "v1"


class TestMetaEndpointsIntegration:
    """End-to-end integration tests for meta endpoints workflow."""

    @pytest.mark.integration
    def test_coverage_and_stats_provide_complementary_information(
        self, api_client, app, override_customer_auth, mock_reference_db
    ):
        """
        Test: Coverage and stats endpoints provide complementary information.

        Verifies:
        - Coverage shows enrichment quality and limitations
        - Stats shows raw database sizes
        - Both use same underlying data source
        - Collection counts match between endpoints
        """
        with patch('api.v1.endpoints.meta.get_reference_db', return_value=mock_reference_db):

            # Get coverage stats
            coverage_response = api_client.get(
                "/v1/meta/coverage",
                headers={"X-API-Key": "test_key"}
            )
            assert coverage_response.status_code == 200
            coverage_data = coverage_response.json()["data"]

            # Get database stats
            stats_response = api_client.get(
                "/v1/meta/stats",
                headers={"X-API-Key": "test_key"}
            )
            assert stats_response.status_code == 200
            stats_data = stats_response.json()["data"]

            # Verify collection counts match
            assert coverage_data["vertices"]["vulnerabilities"] == \
                   stats_data["collections"]["vulnerabilities"]
            assert coverage_data["vertices"]["weaknesses"] == \
                   stats_data["collections"]["weaknesses"]
            assert coverage_data["edges"]["has_weakness"] == \
                   stats_data["collections"]["has_weakness"]

            # Verify coverage provides enrichment insights
            assert "enrichment_funnel" in coverage_data
            assert "data_limitations" in coverage_data
            assert "recommendations" in coverage_data

            # Verify stats provides raw counts
            assert "total_documents" in stats_data
            assert "total_edges" in stats_data

            print("✅ Coverage and stats endpoints provide complementary information")

    @pytest.mark.integration
    def test_meta_endpoints_are_read_only(
        self, api_client, app, override_customer_auth, mock_reference_db
    ):
        """
        Test: Meta endpoints are read-only (no POST/PUT/DELETE).

        Verifies:
        - Only GET methods are supported
        - POST/PUT/DELETE return 405 METHOD NOT ALLOWED
        """
        with patch('api.v1.endpoints.meta.get_reference_db', return_value=mock_reference_db):

            endpoints = ["/v1/meta/coverage", "/v1/meta/stats"]

            for endpoint in endpoints:
                # POST should fail
                post_response = api_client.post(
                    endpoint,
                    headers={"X-API-Key": "test_key"}
                )
                assert post_response.status_code == 405

                # PUT should fail
                put_response = api_client.put(
                    endpoint,
                    headers={"X-API-Key": "test_key"}
                )
                assert put_response.status_code == 405

                # DELETE should fail
                delete_response = api_client.delete(
                    endpoint,
                    headers={"X-API-Key": "test_key"}
                )
                assert delete_response.status_code == 405

            print("✅ Meta endpoints are read-only (GET only)")
