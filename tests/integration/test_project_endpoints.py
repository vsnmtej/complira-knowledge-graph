"""
Integration tests for project management endpoints.

Tests complete project lifecycle: create → list → get → update → get summary → delete.

Routes tested:
    POST   /v1/projects                    - Create new project
    GET    /v1/projects                    - List all projects
    GET    /v1/projects/{project_id}       - Get project details
    PUT    /v1/projects/{project_id}       - Update project
    DELETE /v1/projects/{project_id}       - Soft delete project
    GET    /v1/projects/{project_id}/summary - Get project summary
"""

import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from fastapi.testclient import TestClient
from datetime import datetime


@pytest.fixture
def mock_project_db():
    """Mock database for project operations."""
    db = MagicMock()
    db.collection = Mock(return_value=MagicMock())
    db.aql = MagicMock()
    db.has_collection = Mock(return_value=True)

    # Mock collection operations
    collection = db.collection.return_value
    collection.insert = Mock(return_value={
        "_key": "proj_abc123def456",
        "_id": "projects/proj_abc123def456",
        "_rev": "_rev123",
    })
    collection.update = Mock(return_value={
        "_key": "proj_abc123def456",
        "_id": "projects/proj_abc123def456",
        "_rev": "_rev456",
    })

    # Mock AQL queries for project listing
    db.aql.execute = Mock(return_value=[
        {
            "_key": "proj_abc123def456",
            "_id": "projects/proj_abc123def456",
            "project_id": "proj_abc123def456",
            "customer_id": "customer_test",
            "name": "Backend Services",
            "description": "All backend microservices and APIs",
            "tags": ["backend", "production", "critical"],
            "repository_count": 5,
            "created_at": "2024-01-15T10:00:00Z",
            "updated_at": "2024-01-15T10:00:00Z",
            "last_scan_at": "2024-01-15T14:28:00Z",
            "active": True,
        },
        {
            "_key": "proj_def456ghi789",
            "_id": "projects/proj_def456ghi789",
            "project_id": "proj_def456ghi789",
            "customer_id": "customer_test",
            "name": "Mobile Applications",
            "description": "iOS and Android mobile apps",
            "tags": ["mobile", "production"],
            "repository_count": 3,
            "created_at": "2024-01-10T10:00:00Z",
            "updated_at": "2024-01-12T15:30:00Z",
            "last_scan_at": "2024-01-14T09:15:00Z",
            "active": True,
        }
    ])

    return db


class TestProjectCreation:
    """Tests for POST /v1/projects - Create new project."""

    @pytest.mark.integration
    def test_create_project_success(
        self, api_client, app, override_customer_auth, mock_project_db
    ):
        """
        Test: POST /v1/projects - Successfully create new project.

        Verifies:
        - Project created with correct metadata
        - Response includes project_id, name, description, tags
        - repository_count is 0 at creation
        - Returns 200 status code
        - Metadata includes execution time
        """
        with patch('api.v1.endpoints.projects.get_database', return_value=mock_project_db):

            # Make request
            response = api_client.post(
                "/v1/projects",
                json={
                    "name": "Backend Services",
                    "description": "All backend microservices and APIs",
                    "tags": ["backend", "production", "critical"]
                },
                headers={"X-API-Key": "test_key"}
            )

            # Verify response
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

            data = response.json()
            assert data["success"] is True
            assert "data" in data

            project_data = data["data"]
            assert "project_id" in project_data
            assert project_data["project_id"].startswith("proj_")
            assert project_data["name"] == "Backend Services"
            assert project_data["description"] == "All backend microservices and APIs"
            assert project_data["tags"] == ["backend", "production", "critical"]
            assert project_data["repository_count"] == 0
            assert "created_at" in project_data

            # Verify metadata
            assert "metadata" in data
            assert "execution_time_ms" in data["metadata"]
            assert data["metadata"]["cache_hit"] is False

    @pytest.mark.integration
    def test_create_project_minimal_fields(
        self, api_client, app, override_customer_auth, mock_project_db
    ):
        """
        Test: POST /v1/projects - Create project with only required fields.

        Verifies:
        - Only name is required
        - description defaults to None
        - tags defaults to empty list
        """
        with patch('api.v1.endpoints.projects.get_database', return_value=mock_project_db):

            response = api_client.post(
                "/v1/projects",
                json={"name": "Minimal Project"},
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()
            project_data = data["data"]

            assert project_data["name"] == "Minimal Project"
            assert project_data["description"] is None
            assert project_data["tags"] == []
            assert project_data["repository_count"] == 0

    @pytest.mark.integration
    def test_create_project_fails_with_short_name(self, api_client, app, override_customer_auth):
        """
        Test: POST /v1/projects - Reject name shorter than 3 characters.

        Verifies:
        - Returns 422 UNPROCESSABLE_ENTITY status
        - Error indicates minimum length requirement
        """
        response = api_client.post(
            "/v1/projects",
            json={"name": "AB"},  # Less than 3 characters
            headers={"X-API-Key": "test_key"}
        )

        assert response.status_code == 422

    @pytest.mark.integration
    def test_create_project_fails_with_long_name(self, api_client, app, override_customer_auth):
        """
        Test: POST /v1/projects - Reject name longer than 100 characters.

        Verifies:
        - Returns 422 UNPROCESSABLE_ENTITY status
        - Error indicates maximum length requirement
        """
        response = api_client.post(
            "/v1/projects",
            json={"name": "A" * 101},  # More than 100 characters
            headers={"X-API-Key": "test_key"}
        )

        assert response.status_code == 422

    @pytest.mark.integration
    def test_create_project_fails_without_auth(self, api_client):
        """
        Test: POST /v1/projects - Reject request without authentication.

        Verifies:
        - Returns 401 or 403 status code
        - Authentication is required
        """
        response = api_client.post(
            "/v1/projects",
            json={"name": "Test Project"}
        )

        assert response.status_code in [401, 403]


class TestProjectListing:
    """Tests for GET /v1/projects - List all projects."""

    @pytest.mark.integration
    def test_list_projects_success(
        self, api_client, app, override_customer_auth, mock_project_db
    ):
        """
        Test: GET /v1/projects - List all active projects.

        Verifies:
        - Returns list of projects
        - Includes project metadata
        - Includes total count
        - Projects sorted by created_at DESC
        """
        with patch('api.v1.endpoints.projects.get_database', return_value=mock_project_db):

            response = api_client.get(
                "/v1/projects",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            assert data["success"] is True
            assert "data" in data

            list_data = data["data"]
            assert "projects" in list_data
            assert "total" in list_data
            assert len(list_data["projects"]) == 2
            assert list_data["total"] == 2

            # Verify first project details
            project = list_data["projects"][0]
            assert project["project_id"] == "proj_abc123def456"
            assert project["name"] == "Backend Services"
            assert project["description"] == "All backend microservices and APIs"
            assert project["tags"] == ["backend", "production", "critical"]
            assert project["repository_count"] == 5
            assert project["active"] is True
            assert "created_at" in project
            assert "updated_at" in project

    @pytest.mark.integration
    def test_list_projects_filter_by_active(
        self, api_client, app, override_customer_auth, mock_project_db
    ):
        """
        Test: GET /v1/projects?active=true - Filter by active status.

        Verifies:
        - active query parameter works
        - Returns only active/inactive projects
        """
        with patch('api.v1.endpoints.projects.get_database', return_value=mock_project_db):

            response = api_client.get(
                "/v1/projects?active=true",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            # All returned projects should be active
            for project in data["data"]["projects"]:
                assert project["active"] is True

    @pytest.mark.integration
    def test_list_projects_filter_by_tags(
        self, api_client, app, override_customer_auth, mock_project_db
    ):
        """
        Test: GET /v1/projects?tags=backend,production - Filter by tags.

        Verifies:
        - tags query parameter works (comma-separated)
        - Returns projects with matching tags
        """
        # Mock filtered results
        mock_project_db.aql.execute = Mock(return_value=[
            {
                "_key": "proj_abc123def456",
                "project_id": "proj_abc123def456",
                "customer_id": "customer_test",
                "name": "Backend Services",
                "description": "All backend microservices and APIs",
                "tags": ["backend", "production", "critical"],
                "repository_count": 5,
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T10:00:00Z",
                "last_scan_at": "2024-01-15T14:28:00Z",
                "active": True,
            }
        ])

        with patch('api.v1.endpoints.projects.get_database', return_value=mock_project_db):

            response = api_client.get(
                "/v1/projects?tags=backend,production",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            assert len(data["data"]["projects"]) == 1
            assert "backend" in data["data"]["projects"][0]["tags"]
            assert "production" in data["data"]["projects"][0]["tags"]

    @pytest.mark.integration
    def test_list_projects_empty_result(
        self, api_client, app, override_customer_auth, mock_project_db
    ):
        """
        Test: GET /v1/projects - Empty result when no projects exist.

        Verifies:
        - Returns empty list
        - total is 0
        - No errors occur
        """
        mock_project_db.aql.execute = Mock(return_value=[])

        with patch('api.v1.endpoints.projects.get_database', return_value=mock_project_db):

            response = api_client.get(
                "/v1/projects",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            assert data["data"]["projects"] == []
            assert data["data"]["total"] == 0


class TestProjectRetrieval:
    """Tests for GET /v1/projects/{project_id} - Get project details."""

    @pytest.mark.integration
    def test_get_project_success(
        self, api_client, app, override_customer_auth, mock_project_db
    ):
        """
        Test: GET /v1/projects/{project_id} - Successfully retrieve project.

        Verifies:
        - Project details returned
        - All fields present
        - Customer isolation enforced
        """
        mock_project_db.aql.execute = Mock(return_value=[
            {
                "_key": "proj_abc123def456",
                "project_id": "proj_abc123def456",
                "customer_id": "customer_test",
                "name": "Backend Services",
                "description": "All backend microservices and APIs",
                "tags": ["backend", "production", "critical"],
                "repository_count": 5,
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T10:00:00Z",
                "last_scan_at": "2024-01-15T14:28:00Z",
                "active": True,
            }
        ])

        with patch('api.v1.endpoints.projects.get_database', return_value=mock_project_db):

            response = api_client.get(
                "/v1/projects/proj_abc123def456",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            assert data["success"] is True
            project_data = data["data"]

            assert project_data["project_id"] == "proj_abc123def456"
            assert project_data["name"] == "Backend Services"
            assert project_data["description"] == "All backend microservices and APIs"
            assert project_data["tags"] == ["backend", "production", "critical"]
            assert project_data["repository_count"] == 5
            assert project_data["active"] is True
            assert project_data["created_at"] == "2024-01-15T10:00:00Z"
            assert project_data["updated_at"] == "2024-01-15T10:00:00Z"
            assert project_data["last_scan_at"] == "2024-01-15T14:28:00Z"

    @pytest.mark.integration
    def test_get_project_not_found(
        self, api_client, app, override_customer_auth, mock_project_db
    ):
        """
        Test: GET /v1/projects/{project_id} - 404 when project doesn't exist.

        Verifies:
        - 404 NOT FOUND for non-existent project
        - Error message indicates project not found
        """
        mock_project_db.aql.execute = Mock(return_value=[])

        with patch('api.v1.endpoints.projects.get_database', return_value=mock_project_db):

            response = api_client.get(
                "/v1/projects/proj_nonexistent",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 404
            assert "not found" in response.text.lower()

    @pytest.mark.integration
    def test_get_project_cross_customer_isolation(
        self, api_client, app, mock_project_db
    ):
        """
        Test: GET /v1/projects/{project_id} - Cannot access other customer's projects.

        Verifies:
        - Customer isolation enforced
        - Returns 404 (not 403) to avoid revealing project existence
        """
        from api.core.security import get_current_customer

        # Mock different customer
        different_customer = Mock()
        different_customer._key = "customer_other"
        different_customer.id = "customer_other"
        different_customer.name = "Other Customer"
        different_customer.tier = "pro"
        different_customer.database_name = "complira_tenant_customer_other"
        different_customer.frameworks = ["FDA_524B"]

        async def _override(api_key=None, token=None):
            return different_customer

        app.dependency_overrides[get_current_customer] = _override

        # Project belongs to customer_test, but request is from customer_other
        mock_project_db.aql.execute = Mock(return_value=[])

        with patch('api.v1.endpoints.projects.get_database', return_value=mock_project_db):

            response = api_client.get(
                "/v1/projects/proj_abc123def456",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 404


class TestProjectUpdate:
    """Tests for PUT /v1/projects/{project_id} - Update project."""

    @pytest.mark.integration
    def test_update_project_success(
        self, api_client, app, override_customer_auth, mock_project_db
    ):
        """
        Test: PUT /v1/projects/{project_id} - Successfully update project.

        Verifies:
        - Name, description, tags can be updated
        - Updated project returned
        - updated_at timestamp changes
        """
        # Mock get project (before update)
        mock_project_db.aql.execute = Mock(side_effect=[
            # First call: verify project exists
            [{
                "_key": "proj_abc123def456",
                "project_id": "proj_abc123def456",
                "customer_id": "customer_test",
                "name": "Backend Services",
                "description": "All backend microservices and APIs",
                "tags": ["backend", "production"],
                "repository_count": 5,
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T10:00:00Z",
                "active": True,
            }],
            # Second call: return updated project
            [{
                "_key": "proj_abc123def456",
                "project_id": "proj_abc123def456",
                "customer_id": "customer_test",
                "name": "Backend Services (Updated)",
                "description": "All backend microservices and APIs - now with GraphQL",
                "tags": ["backend", "production", "graphql"],
                "repository_count": 5,
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T15:30:00Z",
                "active": True,
            }]
        ])

        with patch('api.v1.endpoints.projects.get_database', return_value=mock_project_db):

            response = api_client.put(
                "/v1/projects/proj_abc123def456",
                json={
                    "name": "Backend Services (Updated)",
                    "description": "All backend microservices and APIs - now with GraphQL",
                    "tags": ["backend", "production", "graphql"]
                },
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            project_data = data["data"]
            assert project_data["name"] == "Backend Services (Updated)"
            assert project_data["description"] == "All backend microservices and APIs - now with GraphQL"
            assert project_data["tags"] == ["backend", "production", "graphql"]
            assert project_data["updated_at"] == "2024-01-15T15:30:00Z"

    @pytest.mark.integration
    def test_update_project_partial_fields(
        self, api_client, app, override_customer_auth, mock_project_db
    ):
        """
        Test: PUT /v1/projects/{project_id} - Partial update (only some fields).

        Verifies:
        - Can update only name without description/tags
        - Other fields remain unchanged
        """
        mock_project_db.aql.execute = Mock(side_effect=[
            [{
                "_key": "proj_abc123def456",
                "project_id": "proj_abc123def456",
                "customer_id": "customer_test",
                "name": "Backend Services",
                "description": "Original description",
                "tags": ["backend"],
                "repository_count": 5,
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T10:00:00Z",
                "active": True,
            }],
            [{
                "_key": "proj_abc123def456",
                "project_id": "proj_abc123def456",
                "customer_id": "customer_test",
                "name": "New Project Name",
                "description": "Original description",  # Unchanged
                "tags": ["backend"],  # Unchanged
                "repository_count": 5,
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T15:30:00Z",
                "active": True,
            }]
        ])

        with patch('api.v1.endpoints.projects.get_database', return_value=mock_project_db):

            response = api_client.put(
                "/v1/projects/proj_abc123def456",
                json={"name": "New Project Name"},
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            project_data = data["data"]
            assert project_data["name"] == "New Project Name"
            assert project_data["description"] == "Original description"
            assert project_data["tags"] == ["backend"]

    @pytest.mark.integration
    def test_update_project_soft_delete_via_active_flag(
        self, api_client, app, override_customer_auth, mock_project_db
    ):
        """
        Test: PUT /v1/projects/{project_id} - Soft delete via active=false.

        Verifies:
        - Can set active=false to soft delete
        - Alternative to DELETE endpoint
        """
        mock_project_db.aql.execute = Mock(side_effect=[
            [{
                "_key": "proj_abc123def456",
                "project_id": "proj_abc123def456",
                "customer_id": "customer_test",
                "name": "Backend Services",
                "description": "Description",
                "tags": ["backend"],
                "repository_count": 5,
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T10:00:00Z",
                "active": True,
            }],
            [{
                "_key": "proj_abc123def456",
                "project_id": "proj_abc123def456",
                "customer_id": "customer_test",
                "name": "Backend Services",
                "description": "Description",
                "tags": ["backend"],
                "repository_count": 5,
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T15:30:00Z",
                "active": False,  # Soft deleted
            }]
        ])

        with patch('api.v1.endpoints.projects.get_database', return_value=mock_project_db):

            response = api_client.put(
                "/v1/projects/proj_abc123def456",
                json={"active": False},
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["active"] is False

    @pytest.mark.integration
    def test_update_project_not_found(
        self, api_client, app, override_customer_auth, mock_project_db
    ):
        """
        Test: PUT /v1/projects/{project_id} - 404 when project doesn't exist.
        """
        mock_project_db.aql.execute = Mock(return_value=[])

        with patch('api.v1.endpoints.projects.get_database', return_value=mock_project_db):

            response = api_client.put(
                "/v1/projects/proj_nonexistent",
                json={"name": "New Name"},
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 404


class TestProjectDeletion:
    """Tests for DELETE /v1/projects/{project_id} - Soft delete project."""

    @pytest.mark.integration
    def test_delete_project_success(
        self, api_client, app, override_customer_auth, mock_project_db
    ):
        """
        Test: DELETE /v1/projects/{project_id} - Successfully soft delete project.

        Verifies:
        - Project marked as inactive (active=false)
        - Repositories unassigned from project
        - Response includes deletion confirmation
        - Returns 200 status code
        """
        mock_project_db.aql.execute = Mock(return_value=[
            {
                "_key": "proj_abc123def456",
                "project_id": "proj_abc123def456",
                "customer_id": "customer_test",
                "name": "Backend Services",
                "description": "Description",
                "tags": ["backend"],
                "repository_count": 5,
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T10:00:00Z",
                "active": True,
            }
        ])

        with patch('api.v1.endpoints.projects.get_database', return_value=mock_project_db):

            response = api_client.delete(
                "/v1/projects/proj_abc123def456",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            assert data["success"] is True
            delete_data = data["data"]

            assert delete_data["project_id"] == "proj_abc123def456"
            assert delete_data["name"] == "Backend Services"
            assert "deleted_at" in delete_data
            assert "message" in delete_data
            assert "deleted" in delete_data["message"].lower()

    @pytest.mark.integration
    def test_delete_project_already_deleted(
        self, api_client, app, override_customer_auth, mock_project_db
    ):
        """
        Test: DELETE /v1/projects/{project_id} - Reject if already deleted.

        Verifies:
        - Returns 400 BAD REQUEST
        - Error indicates project already deleted
        """
        mock_project_db.aql.execute = Mock(return_value=[
            {
                "_key": "proj_abc123def456",
                "project_id": "proj_abc123def456",
                "customer_id": "customer_test",
                "name": "Backend Services",
                "active": False,  # Already deleted
            }
        ])

        with patch('api.v1.endpoints.projects.get_database', return_value=mock_project_db):

            response = api_client.delete(
                "/v1/projects/proj_abc123def456",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 400
            assert "already deleted" in response.text.lower()

    @pytest.mark.integration
    def test_delete_project_not_found(
        self, api_client, app, override_customer_auth, mock_project_db
    ):
        """
        Test: DELETE /v1/projects/{project_id} - 404 when project doesn't exist.
        """
        mock_project_db.aql.execute = Mock(return_value=[])

        with patch('api.v1.endpoints.projects.get_database', return_value=mock_project_db):

            response = api_client.delete(
                "/v1/projects/proj_nonexistent",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 404


class TestProjectSummary:
    """Tests for GET /v1/projects/{project_id}/summary - Get project summary."""

    @pytest.mark.integration
    def test_get_project_summary_success(
        self, api_client, app, override_customer_auth, mock_project_db
    ):
        """
        Test: GET /v1/projects/{project_id}/summary - Get aggregated project insights.

        Verifies:
        - Returns project summary with aggregations
        - Includes repository count and breakdown
        - Includes findings aggregation
        - Includes top vulnerabilities
        - Includes compliance status
        """
        # Mock project exists
        mock_project_db.aql.execute = Mock(side_effect=[
            # First call: get project
            [{
                "_key": "proj_abc123def456",
                "project_id": "proj_abc123def456",
                "customer_id": "customer_test",
                "name": "Backend Services",
            }],
            # Second call: get repositories
            [
                {
                    "repository_id": "repo_123",
                    "name": "auth-service",
                    "scan_count": 12,
                    "last_scan_at": "2024-01-15T14:28:00Z",
                },
                {
                    "repository_id": "repo_456",
                    "name": "payment-service",
                    "scan_count": 8,
                    "last_scan_at": "2024-01-14T10:15:00Z",
                },
                {
                    "repository_id": "repo_789",
                    "name": "notification-service",
                    "scan_count": 5,
                    "last_scan_at": "2024-01-13T09:00:00Z",
                }
            ]
        ])

        with patch('api.v1.endpoints.projects.get_database', return_value=mock_project_db):

            response = api_client.get(
                "/v1/projects/proj_abc123def456/summary",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            assert data["success"] is True
            summary_data = data["data"]

            assert summary_data["project_id"] == "proj_abc123def456"
            assert summary_data["project_name"] == "Backend Services"
            assert summary_data["repository_count"] == 3
            assert summary_data["total_scans"] == 25  # 12 + 8 + 5

            # Verify findings structure
            assert "findings" in summary_data
            findings = summary_data["findings"]
            assert "critical" in findings
            assert "high" in findings
            assert "medium" in findings
            assert "low" in findings
            assert "total" in findings

            # Verify repositories breakdown
            assert "repositories" in summary_data
            assert len(summary_data["repositories"]) == 3
            repo = summary_data["repositories"][0]
            assert "repository_id" in repo
            assert "repository_name" in repo
            assert "scan_count" in repo
            assert "last_scan_at" in repo

    @pytest.mark.integration
    def test_get_project_summary_no_repositories(
        self, api_client, app, override_customer_auth, mock_project_db
    ):
        """
        Test: GET /v1/projects/{project_id}/summary - Project with no repositories.

        Verifies:
        - Returns empty summary
        - repository_count is 0
        - total_scans is 0
        - No errors occur
        """
        mock_project_db.aql.execute = Mock(side_effect=[
            [{
                "_key": "proj_abc123def456",
                "project_id": "proj_abc123def456",
                "customer_id": "customer_test",
                "name": "Empty Project",
            }],
            []  # No repositories
        ])

        with patch('api.v1.endpoints.projects.get_database', return_value=mock_project_db):

            response = api_client.get(
                "/v1/projects/proj_abc123def456/summary",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            summary_data = data["data"]
            assert summary_data["repository_count"] == 0
            assert summary_data["total_scans"] == 0
            assert summary_data["repositories"] == []

    @pytest.mark.integration
    def test_get_project_summary_not_found(
        self, api_client, app, override_customer_auth, mock_project_db
    ):
        """
        Test: GET /v1/projects/{project_id}/summary - 404 when project doesn't exist.
        """
        mock_project_db.aql.execute = Mock(return_value=[])

        with patch('api.v1.endpoints.projects.get_database', return_value=mock_project_db):

            response = api_client.get(
                "/v1/projects/proj_nonexistent/summary",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 404


class TestProjectLifecycle:
    """Integration tests for complete project lifecycle."""

    @pytest.mark.integration
    def test_full_project_lifecycle(
        self, api_client, app, override_customer_auth, mock_project_db
    ):
        """
        Test: Complete project lifecycle - create -> list -> get -> update -> get summary -> delete.

        Verifies:
        - All operations work together
        - State transitions are valid
        - Data consistency throughout lifecycle
        """
        project_id = "proj_lifecycle_test"

        with patch('api.v1.endpoints.projects.get_database', return_value=mock_project_db):

            # Step 1: Create project
            mock_project_db.collection.return_value.insert = Mock(return_value={
                "_key": project_id,
                "_id": f"projects/{project_id}",
            })

            create_response = api_client.post(
                "/v1/projects",
                json={
                    "name": "Lifecycle Test Project",
                    "description": "Testing full lifecycle",
                    "tags": ["test", "lifecycle"]
                },
                headers={"X-API-Key": "test_key"}
            )

            assert create_response.status_code == 200
            created_project_id = create_response.json()["data"]["project_id"]

            # Step 2: List projects (should include new project)
            mock_project_db.aql.execute = Mock(return_value=[
                {
                    "_key": created_project_id,
                    "project_id": created_project_id,
                    "customer_id": "customer_test",
                    "name": "Lifecycle Test Project",
                    "description": "Testing full lifecycle",
                    "tags": ["test", "lifecycle"],
                    "repository_count": 0,
                    "created_at": "2024-01-15T10:00:00Z",
                    "updated_at": "2024-01-15T10:00:00Z",
                    "active": True,
                }
            ])

            list_response = api_client.get(
                "/v1/projects",
                headers={"X-API-Key": "test_key"}
            )

            assert list_response.status_code == 200
            assert len(list_response.json()["data"]["projects"]) > 0

            # Step 3: Get project details
            mock_project_db.aql.execute = Mock(return_value=[
                {
                    "_key": created_project_id,
                    "project_id": created_project_id,
                    "customer_id": "customer_test",
                    "name": "Lifecycle Test Project",
                    "description": "Testing full lifecycle",
                    "tags": ["test", "lifecycle"],
                    "repository_count": 0,
                    "created_at": "2024-01-15T10:00:00Z",
                    "updated_at": "2024-01-15T10:00:00Z",
                    "active": True,
                }
            ])

            get_response = api_client.get(
                f"/v1/projects/{created_project_id}",
                headers={"X-API-Key": "test_key"}
            )

            assert get_response.status_code == 200
            assert get_response.json()["data"]["name"] == "Lifecycle Test Project"

            # Step 4: Update project
            mock_project_db.aql.execute = Mock(side_effect=[
                [{
                    "_key": created_project_id,
                    "project_id": created_project_id,
                    "customer_id": "customer_test",
                    "name": "Lifecycle Test Project",
                    "description": "Testing full lifecycle",
                    "tags": ["test", "lifecycle"],
                    "repository_count": 0,
                    "created_at": "2024-01-15T10:00:00Z",
                    "updated_at": "2024-01-15T10:00:00Z",
                    "active": True,
                }],
                [{
                    "_key": created_project_id,
                    "project_id": created_project_id,
                    "customer_id": "customer_test",
                    "name": "Lifecycle Test Project (Updated)",
                    "description": "Testing full lifecycle - updated",
                    "tags": ["test", "lifecycle", "updated"],
                    "repository_count": 0,
                    "created_at": "2024-01-15T10:00:00Z",
                    "updated_at": "2024-01-15T15:30:00Z",
                    "active": True,
                }]
            ])

            update_response = api_client.put(
                f"/v1/projects/{created_project_id}",
                json={
                    "name": "Lifecycle Test Project (Updated)",
                    "description": "Testing full lifecycle - updated",
                    "tags": ["test", "lifecycle", "updated"]
                },
                headers={"X-API-Key": "test_key"}
            )

            assert update_response.status_code == 200
            assert update_response.json()["data"]["name"] == "Lifecycle Test Project (Updated)"

            # Step 5: Get summary
            mock_project_db.aql.execute = Mock(side_effect=[
                [{
                    "_key": created_project_id,
                    "project_id": created_project_id,
                    "customer_id": "customer_test",
                    "name": "Lifecycle Test Project (Updated)",
                }],
                []  # No repositories yet
            ])

            summary_response = api_client.get(
                f"/v1/projects/{created_project_id}/summary",
                headers={"X-API-Key": "test_key"}
            )

            assert summary_response.status_code == 200
            assert summary_response.json()["data"]["repository_count"] == 0

            # Step 6: Delete project
            mock_project_db.aql.execute = Mock(return_value=[
                {
                    "_key": created_project_id,
                    "project_id": created_project_id,
                    "customer_id": "customer_test",
                    "name": "Lifecycle Test Project (Updated)",
                    "active": True,
                }
            ])

            delete_response = api_client.delete(
                f"/v1/projects/{created_project_id}",
                headers={"X-API-Key": "test_key"}
            )

            assert delete_response.status_code == 200
            assert "deleted" in delete_response.json()["data"]["message"].lower()

            print("✅ Full project lifecycle test passed: create → list → get → update → get summary → delete")
