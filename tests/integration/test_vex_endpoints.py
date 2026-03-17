"""
Integration tests for VEX (Vulnerability Exploitability eXchange) endpoints.

Tests full API flow for all 6 VEX endpoints:
- POST /v1/vex - Create VEX document
- GET /v1/vex - List VEX documents
- GET /v1/vex/{vex_id} - Get VEX document (enriched)
- PUT /v1/vex/{vex_id} - Update entire VEX document
- PATCH /v1/vex/{vex_id}/vulnerability/{cve_id} - Update single vulnerability assessment
- DELETE /v1/vex/{vex_id} - Delete VEX document

Uses FastAPI dependency_overrides via conftest fixtures for get_current_customer.
"""

import pytest
from unittest.mock import MagicMock, Mock, patch, AsyncMock


@pytest.fixture
def mock_customer_db():
    """Mock customer database for VEX operations."""
    db = MagicMock()
    db.collection = Mock(return_value=MagicMock())
    db.aql = MagicMock()

    collection = db.collection.return_value
    collection.insert = Mock(return_value={
        "_key": "vex_abc123",
        "_id": "vex_documents/vex_abc123",
        "_rev": "_rev123",
    })
    collection.update = Mock(return_value={
        "_key": "vex_abc123",
        "_id": "vex_documents/vex_abc123",
        "_rev": "_rev456",
    })
    collection.delete = Mock(return_value=True)

    return db


@pytest.fixture
def mock_reference_db():
    """Mock reference database for knowledge graph enrichment."""
    db = MagicMock()
    db.collection = Mock(return_value=MagicMock())
    db.aql = MagicMock()

    db.aql.execute = Mock(return_value=[{
        "_key": "CVE-2021-44228",
        "cve_id": "CVE-2021-44228",
        "in_kev": True,
        "kev_date_added": "2021-12-10T00:00:00Z",
        "kev_due_date": "2021-12-24T00:00:00Z",
        "epss_score": 0.97542,
        "epss_percentile": 0.99876,
        "cvss_score": 10.0,
        "cvss_severity": "CRITICAL",
    }])

    return db


@pytest.fixture
def valid_vex_request():
    """Valid VEX document request payload."""
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "vulnerabilities": [
            {
                "id": "CVE-2021-44228",
                "analysis": {
                    "state": "not_affected",
                    "justification": "code_not_reachable",
                    "detail": "Log4j is included but logging is disabled in production configuration"
                }
            },
            {
                "id": "CVE-2024-2508",
                "analysis": {
                    "state": "exploitable",
                    "response": ["update"],
                    "detail": "Vulnerability confirmed exploitable, patch available"
                }
            }
        ],
        "metadata": {
            "component": {
                "type": "application",
                "name": "my-app",
                "version": "1.0.0"
            },
            "timestamp": "2026-03-10T10:00:00Z"
        }
    }


class TestVEXCreation:
    """Integration tests for POST /v1/vex - Create VEX document."""

    @pytest.mark.integration
    def test_create_vex_success(
        self, api_client, override_customer_auth,
        mock_customer_db, mock_reference_db, valid_vex_request
    ):
        """
        Test: POST /v1/vex successfully creates VEX document with enrichment.
        """
        with patch('api.v1.endpoints.vex.get_customer_db', return_value=mock_customer_db), \
             patch('api.v1.endpoints.vex.get_reference_db', return_value=mock_reference_db), \
             patch('api.services.vex.VEXService.create_vex') as mock_create:

            mock_create.return_value = {
                "vex_id": "vex_abc123",
                "vulnerabilities_count": 2,
                "enriched_count": 2,
                "created_at": "2026-03-17T10:00:00Z"
            }

            response = api_client.post(
                "/v1/vex",
                json=valid_vex_request,
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

            data = response.json()
            assert data["success"] is True
            assert "data" in data

            vex_data = data["data"]
            assert vex_data["vex_id"] == "vex_abc123"
            assert vex_data["vulnerabilities_count"] == 2
            assert vex_data["enriched_count"] == 2
            assert "created_at" in vex_data

            assert "metadata" in data
            assert "execution_time_ms" in data["metadata"]
            assert data["metadata"]["cache_hit"] is False

    @pytest.mark.integration
    def test_create_vex_with_various_states(
        self, api_client, override_customer_auth,
        mock_customer_db, mock_reference_db
    ):
        """
        Test: POST /v1/vex accepts all VEX states.
        """
        vex_request = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.5",
            "vulnerabilities": [
                {"id": "CVE-2024-0001", "analysis": {"state": "not_affected", "justification": "code_not_present", "detail": "Component not included in this build"}},
                {"id": "CVE-2024-0002", "analysis": {"state": "exploitable", "response": ["update", "workaround_available"], "detail": "Patch scheduled for next release"}},
                {"id": "CVE-2024-0003", "analysis": {"state": "resolved", "response": ["update"], "detail": "Fixed in version 1.2.3"}},
                {"id": "CVE-2024-0004", "analysis": {"state": "in_triage", "detail": "Security team investigating"}},
                {"id": "CVE-2024-0005", "analysis": {"state": "false_positive", "detail": "Not applicable to our use case"}}
            ]
        }

        with patch('api.v1.endpoints.vex.get_customer_db', return_value=mock_customer_db), \
             patch('api.v1.endpoints.vex.get_reference_db', return_value=mock_reference_db), \
             patch('api.services.vex.VEXService.create_vex') as mock_create:

            mock_create.return_value = {
                "vex_id": "vex_def456",
                "vulnerabilities_count": 5,
                "enriched_count": 5,
                "created_at": "2026-03-17T10:00:00Z"
            }

            response = api_client.post("/v1/vex", json=vex_request, headers={"X-API-Key": "test_key"})

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["data"]["vulnerabilities_count"] == 5

    @pytest.mark.integration
    def test_create_vex_with_all_justifications(
        self, api_client, override_customer_auth,
        mock_customer_db, mock_reference_db
    ):
        """
        Test: POST /v1/vex accepts all VEX justification types.
        """
        vex_request = {
            "vulnerabilities": [
                {"id": "CVE-2024-1001", "analysis": {"state": "not_affected", "justification": "code_not_present"}},
                {"id": "CVE-2024-1002", "analysis": {"state": "not_affected", "justification": "code_not_reachable"}},
                {"id": "CVE-2024-1003", "analysis": {"state": "not_affected", "justification": "requires_configuration"}},
                {"id": "CVE-2024-1004", "analysis": {"state": "not_affected", "justification": "protected_by_mitigating_control"}}
            ]
        }

        with patch('api.v1.endpoints.vex.get_customer_db', return_value=mock_customer_db), \
             patch('api.v1.endpoints.vex.get_reference_db', return_value=mock_reference_db), \
             patch('api.services.vex.VEXService.create_vex') as mock_create:

            mock_create.return_value = {
                "vex_id": "vex_ghi789",
                "vulnerabilities_count": 4,
                "enriched_count": 4,
                "created_at": "2026-03-17T10:00:00Z"
            }

            response = api_client.post("/v1/vex", json=vex_request, headers={"X-API-Key": "test_key"})
            assert response.status_code == 200

    @pytest.mark.integration
    def test_create_vex_fails_with_invalid_cve_format(
        self, api_client, override_customer_auth,
        mock_customer_db, mock_reference_db
    ):
        """
        Test: POST /v1/vex rejects invalid CVE ID format.
        """
        invalid_vex_request = {
            "vulnerabilities": [
                {"id": "INVALID-2024-1234", "analysis": {"state": "not_affected", "justification": "code_not_present"}}
            ]
        }

        with patch('api.v1.endpoints.vex.get_customer_db', return_value=mock_customer_db), \
             patch('api.v1.endpoints.vex.get_reference_db', return_value=mock_reference_db):

            response = api_client.post("/v1/vex", json=invalid_vex_request, headers={"X-API-Key": "test_key"})
            assert response.status_code == 422

    @pytest.mark.integration
    def test_create_vex_fails_with_empty_vulnerabilities(
        self, api_client, override_customer_auth,
        mock_customer_db, mock_reference_db
    ):
        """
        Test: POST /v1/vex rejects empty vulnerabilities list.
        """
        invalid_vex_request = {"vulnerabilities": []}

        with patch('api.v1.endpoints.vex.get_customer_db', return_value=mock_customer_db), \
             patch('api.v1.endpoints.vex.get_reference_db', return_value=mock_reference_db):

            response = api_client.post("/v1/vex", json=invalid_vex_request, headers={"X-API-Key": "test_key"})
            assert response.status_code == 422

    @pytest.mark.integration
    def test_create_vex_fails_without_authentication(self, api_client, valid_vex_request):
        """
        Test: POST /v1/vex requires authentication.
        """
        response = api_client.post("/v1/vex", json=valid_vex_request)
        assert response.status_code in [401, 403]


class TestVEXListing:
    """Integration tests for GET /v1/vex - List VEX documents."""

    @pytest.mark.integration
    def test_list_vex_success(
        self, api_client, override_customer_auth,
        mock_customer_db, mock_reference_db
    ):
        """
        Test: GET /v1/vex returns paginated list of VEX documents.
        """
        with patch('api.v1.endpoints.vex.get_customer_db', return_value=mock_customer_db), \
             patch('api.v1.endpoints.vex.get_reference_db', return_value=mock_reference_db), \
             patch('api.services.vex.VEXService.list_vex_documents') as mock_list:

            mock_list.return_value = [
                {
                    "vex_id": "vex_abc123",
                    "vulnerabilities_count": 5,
                    "created_at": "2026-03-17T10:00:00Z",
                    "updated_at": "2026-03-17T10:00:00Z",
                    "metadata": {"component": {"name": "app-v1"}}
                },
                {
                    "vex_id": "vex_def456",
                    "vulnerabilities_count": 3,
                    "created_at": "2026-03-16T10:00:00Z",
                    "updated_at": "2026-03-16T10:00:00Z",
                    "metadata": {"component": {"name": "app-v2"}}
                }
            ]

            response = api_client.get("/v1/vex", headers={"X-API-Key": "test_key"})

            assert response.status_code == 200
            data = response.json()

            assert data["success"] is True
            assert "data" in data
            assert isinstance(data["data"], list)
            assert len(data["data"]) == 2

            vex = data["data"][0]
            assert vex["vex_id"] == "vex_abc123"
            assert vex["vulnerabilities_count"] == 5
            assert "created_at" in vex
            assert "updated_at" in vex
            assert "metadata" in vex

    @pytest.mark.integration
    def test_list_vex_with_pagination(
        self, api_client, override_customer_auth,
        mock_customer_db, mock_reference_db
    ):
        """
        Test: GET /v1/vex?limit=10&offset=20 - Pagination works.
        """
        with patch('api.v1.endpoints.vex.get_customer_db', return_value=mock_customer_db), \
             patch('api.v1.endpoints.vex.get_reference_db', return_value=mock_reference_db), \
             patch('api.services.vex.VEXService.list_vex_documents') as mock_list:

            mock_list.return_value = []

            response = api_client.get("/v1/vex?limit=10&offset=20", headers={"X-API-Key": "test_key"})

            assert response.status_code == 200
            mock_list.assert_called_once()
            call_kwargs = mock_list.call_args[1]
            assert call_kwargs["limit"] == 10
            assert call_kwargs["offset"] == 20

    @pytest.mark.integration
    def test_list_vex_empty_result(
        self, api_client, override_customer_auth,
        mock_customer_db, mock_reference_db
    ):
        """
        Test: GET /v1/vex returns empty list when no VEX documents exist.
        """
        with patch('api.v1.endpoints.vex.get_customer_db', return_value=mock_customer_db), \
             patch('api.v1.endpoints.vex.get_reference_db', return_value=mock_reference_db), \
             patch('api.services.vex.VEXService.list_vex_documents') as mock_list:

            mock_list.return_value = []

            response = api_client.get("/v1/vex", headers={"X-API-Key": "test_key"})

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["data"] == []


class TestVEXRetrieval:
    """Integration tests for GET /v1/vex/{vex_id} - Get VEX document."""

    @pytest.mark.integration
    def test_get_vex_success_with_enrichment(
        self, api_client, override_customer_auth,
        mock_customer_db, mock_reference_db
    ):
        """
        Test: GET /v1/vex/{vex_id} returns enriched VEX document.
        """
        with patch('api.v1.endpoints.vex.get_customer_db', return_value=mock_customer_db), \
             patch('api.v1.endpoints.vex.get_reference_db', return_value=mock_reference_db), \
             patch('api.services.vex.VEXService.get_vex') as mock_get:

            mock_get.return_value = {
                "vex_id": "vex_abc123",
                "bomFormat": "CycloneDX",
                "specVersion": "1.5",
                "version": 1,
                "vulnerabilities": [
                    {
                        "cve_id": "CVE-2021-44228",
                        "state": "not_affected",
                        "justification": "code_not_reachable",
                        "detail": "Log4j included but logging disabled",
                        "enrichment": {
                            "in_kev": True,
                            "kev_date_added": "2021-12-10T00:00:00Z",
                            "kev_due_date": "2021-12-24T00:00:00Z",
                            "epss_score": 0.97542,
                            "epss_percentile": 0.99876,
                            "cvss_score": 10.0,
                            "cvss_severity": "CRITICAL",
                            "weaknesses": [{"cwe_id": "CWE-502", "name": "Deserialization of Untrusted Data"}],
                            "attack_techniques": [{"technique_id": "T1190", "name": "Exploit Public-Facing Application"}],
                            "nist_controls": [{"control_id": "SI-10", "title": "Information Input Validation"}],
                            "d3fend_defenses": [],
                            "regulatory_violations": [{"framework": "EU_CRA", "requirement_id": "ANNEX_I_1_a"}]
                        }
                    }
                ],
                "metadata": {"component": {"name": "my-app", "version": "1.0.0"}},
                "created_at": "2026-03-17T10:00:00Z",
                "updated_at": "2026-03-17T10:00:00Z",
                "customer_id": "customer_test"
            }

            response = api_client.get("/v1/vex/vex_abc123", headers={"X-API-Key": "test_key"})

            assert response.status_code == 200
            data = response.json()

            assert data["success"] is True
            vex = data["data"]

            assert vex["vex_id"] == "vex_abc123"
            assert vex["bomFormat"] == "CycloneDX"
            assert vex["specVersion"] == "1.5"
            assert len(vex["vulnerabilities"]) == 1

            vuln = vex["vulnerabilities"][0]
            assert vuln["cve_id"] == "CVE-2021-44228"
            assert vuln["state"] == "not_affected"
            assert "enrichment" in vuln

            enrichment = vuln["enrichment"]
            assert enrichment["in_kev"] is True
            assert enrichment["epss_score"] == 0.97542
            assert enrichment["cvss_score"] == 10.0
            assert len(enrichment["weaknesses"]) > 0
            assert len(enrichment["attack_techniques"]) > 0
            assert len(enrichment["nist_controls"]) > 0
            assert len(enrichment["regulatory_violations"]) > 0

    @pytest.mark.integration
    def test_get_vex_not_found(
        self, api_client, override_customer_auth,
        mock_customer_db, mock_reference_db
    ):
        """
        Test: GET /v1/vex/{vex_id} returns 404 when VEX doesn't exist.
        """
        with patch('api.v1.endpoints.vex.get_customer_db', return_value=mock_customer_db), \
             patch('api.v1.endpoints.vex.get_reference_db', return_value=mock_reference_db), \
             patch('api.services.vex.VEXService.get_vex') as mock_get:

            mock_get.return_value = None

            response = api_client.get("/v1/vex/nonexistent_vex", headers={"X-API-Key": "test_key"})

            assert response.status_code == 404
            data = response.json()
            assert "not found" in data["detail"].lower()


class TestVEXUpdate:
    """Integration tests for PUT /v1/vex/{vex_id} - Update VEX document."""

    @pytest.mark.integration
    def test_update_vex_success(
        self, api_client, override_customer_auth,
        mock_customer_db, mock_reference_db
    ):
        """
        Test: PUT /v1/vex/{vex_id} successfully replaces VEX document.
        """
        update_request = {
            "vulnerabilities": [
                {"id": "CVE-2024-9999", "analysis": {"state": "resolved", "response": ["update"], "detail": "Updated to patched version"}}
            ],
            "metadata": {"component": {"name": "updated-app", "version": "2.0.0"}}
        }

        with patch('api.v1.endpoints.vex.get_customer_db', return_value=mock_customer_db), \
             patch('api.v1.endpoints.vex.get_reference_db', return_value=mock_reference_db), \
             patch('api.services.vex.VEXService.update_vex') as mock_update:

            mock_update.return_value = {
                "vex_id": "vex_abc123",
                "updated_at": "2026-03-17T11:00:00Z",
                "vulnerabilities_count": 1
            }

            response = api_client.put("/v1/vex/vex_abc123", json=update_request, headers={"X-API-Key": "test_key"})

            assert response.status_code == 200
            data = response.json()

            assert data["success"] is True
            assert data["data"]["vex_id"] == "vex_abc123"
            assert data["data"]["vulnerabilities_count"] == 1
            assert "updated_at" in data["data"]

    @pytest.mark.integration
    def test_update_vex_not_found(
        self, api_client, override_customer_auth,
        mock_customer_db, mock_reference_db
    ):
        """
        Test: PUT /v1/vex/{vex_id} returns 404 when VEX doesn't exist.
        """
        update_request = {
            "vulnerabilities": [
                {"id": "CVE-2024-1234", "analysis": {"state": "not_affected", "justification": "code_not_present"}}
            ]
        }

        with patch('api.v1.endpoints.vex.get_customer_db', return_value=mock_customer_db), \
             patch('api.v1.endpoints.vex.get_reference_db', return_value=mock_reference_db), \
             patch('api.services.vex.VEXService.update_vex') as mock_update:

            mock_update.side_effect = ValueError("VEX document not found")

            response = api_client.put("/v1/vex/nonexistent", json=update_request, headers={"X-API-Key": "test_key"})

            assert response.status_code == 404


class TestVEXVulnerabilityPatch:
    """Integration tests for PATCH /v1/vex/{vex_id}/vulnerability/{cve_id}."""

    @pytest.mark.integration
    def test_patch_vulnerability_success(
        self, api_client, override_customer_auth,
        mock_customer_db, mock_reference_db
    ):
        """
        Test: PATCH /v1/vex/{vex_id}/vulnerability/{cve_id} updates single CVE.
        """
        patch_request = {
            "analysis": {
                "state": "resolved",
                "response": ["update"],
                "detail": "Updated to patched version 2.17.1"
            }
        }

        with patch('api.v1.endpoints.vex.get_customer_db', return_value=mock_customer_db), \
             patch('api.v1.endpoints.vex.get_reference_db', return_value=mock_reference_db), \
             patch('api.services.vex.VEXService.patch_vulnerability') as mock_patch:

            mock_patch.return_value = {
                "vex_id": "vex_abc123",
                "updated_at": "2026-03-17T11:30:00Z",
                "vulnerabilities_count": 2
            }

            response = api_client.patch(
                "/v1/vex/vex_abc123/vulnerability/CVE-2021-44228",
                json=patch_request,
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            assert data["success"] is True
            assert data["data"]["vex_id"] == "vex_abc123"
            assert "updated_at" in data["data"]

    @pytest.mark.integration
    def test_patch_vulnerability_state_transitions(
        self, api_client, override_customer_auth,
        mock_customer_db, mock_reference_db
    ):
        """
        Test: PATCH supports common VEX state transitions.
        """
        transitions = [
            {"state": "exploitable", "response": ["update"], "detail": "Confirmed exploitable after investigation"},
            {"state": "resolved", "response": ["update"], "detail": "Patched successfully"}
        ]

        with patch('api.v1.endpoints.vex.get_customer_db', return_value=mock_customer_db), \
             patch('api.v1.endpoints.vex.get_reference_db', return_value=mock_reference_db), \
             patch('api.services.vex.VEXService.patch_vulnerability') as mock_patch:

            for analysis in transitions:
                mock_patch.return_value = {
                    "vex_id": "vex_abc123",
                    "updated_at": "2026-03-17T12:00:00Z",
                    "vulnerabilities_count": 1
                }

                response = api_client.patch(
                    "/v1/vex/vex_abc123/vulnerability/CVE-2024-1234",
                    json={"analysis": analysis},
                    headers={"X-API-Key": "test_key"}
                )

                assert response.status_code == 200

    @pytest.mark.integration
    def test_patch_vulnerability_not_found(
        self, api_client, override_customer_auth,
        mock_customer_db, mock_reference_db
    ):
        """
        Test: PATCH returns 404 when VEX or CVE doesn't exist.
        """
        patch_request = {"analysis": {"state": "resolved", "response": ["update"]}}

        with patch('api.v1.endpoints.vex.get_customer_db', return_value=mock_customer_db), \
             patch('api.v1.endpoints.vex.get_reference_db', return_value=mock_reference_db), \
             patch('api.services.vex.VEXService.patch_vulnerability') as mock_patch:

            mock_patch.side_effect = ValueError("CVE not found in VEX document")

            response = api_client.patch(
                "/v1/vex/vex_abc123/vulnerability/CVE-9999-9999",
                json=patch_request,
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 404


class TestVEXDeletion:
    """Integration tests for DELETE /v1/vex/{vex_id} - Delete VEX document."""

    @pytest.mark.integration
    def test_delete_vex_success(
        self, api_client, override_customer_auth,
        mock_customer_db, mock_reference_db
    ):
        """
        Test: DELETE /v1/vex/{vex_id} permanently deletes VEX document.
        """
        with patch('api.v1.endpoints.vex.get_customer_db', return_value=mock_customer_db), \
             patch('api.v1.endpoints.vex.get_reference_db', return_value=mock_reference_db), \
             patch('api.services.vex.VEXService.delete_vex') as mock_delete:

            mock_delete.return_value = None

            response = api_client.delete("/v1/vex/vex_abc123", headers={"X-API-Key": "test_key"})

            assert response.status_code == 200
            data = response.json()

            assert data["success"] is True
            assert data["data"]["deleted"] is True
            assert data["data"]["vex_id"] == "vex_abc123"

    @pytest.mark.integration
    def test_delete_vex_not_found(
        self, api_client, override_customer_auth,
        mock_customer_db, mock_reference_db
    ):
        """
        Test: DELETE /v1/vex/{vex_id} returns 404 when VEX doesn't exist.
        """
        with patch('api.v1.endpoints.vex.get_customer_db', return_value=mock_customer_db), \
             patch('api.v1.endpoints.vex.get_reference_db', return_value=mock_reference_db), \
             patch('api.services.vex.VEXService.delete_vex') as mock_delete:

            mock_delete.side_effect = ValueError("VEX document not found")

            response = api_client.delete("/v1/vex/nonexistent", headers={"X-API-Key": "test_key"})

            assert response.status_code == 404


class TestVEXLifecycle:
    """Integration tests for complete VEX lifecycle."""

    @pytest.mark.integration
    def test_full_vex_lifecycle(
        self, api_client, override_customer_auth,
        mock_customer_db, mock_reference_db, valid_vex_request
    ):
        """
        Test: Complete VEX lifecycle - create -> get -> patch -> update -> delete.
        """
        with patch('api.v1.endpoints.vex.get_customer_db', return_value=mock_customer_db), \
             patch('api.v1.endpoints.vex.get_reference_db', return_value=mock_reference_db), \
             patch('api.v1.endpoints.vex.VEXService') as MockService:

            mock_service = MockService.return_value
            mock_service.create_vex = AsyncMock()
            mock_service.get_vex = AsyncMock()
            mock_service.patch_vulnerability = AsyncMock()
            mock_service.update_vex = AsyncMock()
            mock_service.delete_vex = AsyncMock()

            # Step 1: Create VEX
            mock_service.create_vex.return_value = {
                "vex_id": "vex_lifecycle",
                "vulnerabilities_count": 2,
                "enriched_count": 2,
                "created_at": "2026-03-17T10:00:00Z"
            }

            create_response = api_client.post("/v1/vex", json=valid_vex_request, headers={"X-API-Key": "test_key"})
            assert create_response.status_code == 200
            vex_id = create_response.json()["data"]["vex_id"]

            # Step 2: Get VEX
            mock_service.get_vex.return_value = {
                "vex_id": vex_id,
                "bomFormat": "CycloneDX",
                "specVersion": "1.5",
                "version": 1,
                "vulnerabilities": [
                    {"cve_id": "CVE-2021-44228", "state": "not_affected", "enrichment": {"in_kev": True, "epss_score": 0.97542}}
                ],
                "metadata": {},
                "created_at": "2026-03-17T10:00:00Z",
                "updated_at": "2026-03-17T10:00:00Z",
                "customer_id": "customer_test"
            }

            get_response = api_client.get(f"/v1/vex/{vex_id}", headers={"X-API-Key": "test_key"})
            assert get_response.status_code == 200
            vex_data = get_response.json()["data"]
            assert len(vex_data["vulnerabilities"]) > 0

            # Step 3: Patch single vulnerability
            mock_service.patch_vulnerability.return_value = {
                "vex_id": vex_id,
                "updated_at": "2026-03-17T11:00:00Z",
                "vulnerabilities_count": 2
            }

            patch_response = api_client.patch(
                f"/v1/vex/{vex_id}/vulnerability/CVE-2021-44228",
                json={"analysis": {"state": "resolved", "response": ["update"], "detail": "Patched"}},
                headers={"X-API-Key": "test_key"}
            )
            assert patch_response.status_code == 200

            # Step 4: Update entire VEX
            mock_service.update_vex.return_value = {
                "vex_id": vex_id,
                "updated_at": "2026-03-17T12:00:00Z",
                "vulnerabilities_count": 1
            }

            update_response = api_client.put(
                f"/v1/vex/{vex_id}",
                json={"vulnerabilities": [{"id": "CVE-2024-9999", "analysis": {"state": "not_affected", "justification": "code_not_present"}}]},
                headers={"X-API-Key": "test_key"}
            )
            assert update_response.status_code == 200

            # Step 5: Delete VEX
            mock_service.delete_vex.return_value = None

            delete_response = api_client.delete(f"/v1/vex/{vex_id}", headers={"X-API-Key": "test_key"})
            assert delete_response.status_code == 200
            assert delete_response.json()["data"]["deleted"] is True
