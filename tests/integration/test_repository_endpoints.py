"""
Integration tests for repository management endpoints.

Tests full API flow for all 6 repository endpoints:
- POST /v1/repositories (create)
- GET /v1/repositories (list)
- GET /v1/repositories/{repository_id} (get)
- PUT /v1/repositories/{repository_id} (update)
- DELETE /v1/repositories/{repository_id} (delete)
- GET /v1/repositories/{repository_id}/summary (get summary)
"""

import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from fastapi.testclient import TestClient
from datetime import datetime


@pytest.fixture
def mock_repository_db():
    """Mock ArangoDB database for repository operations."""
    db = MagicMock()
    db.collection = Mock(return_value=MagicMock())
    db.aql = MagicMock()
    db.has_collection = Mock(return_value=True)

    # Mock collection operations
    collection = db.collection.return_value
    collection.insert = Mock(return_value={
        "_key": "repo_abc123",
        "_id": "repositories/repo_abc123",
        "_rev": "_rev123",
    })
    collection.update = Mock(return_value={
        "_key": "repo_abc123",
        "_id": "repositories/repo_abc123",
        "_rev": "_rev456",
    })

    return db


@pytest.fixture
def sample_repository():
    """Sample repository data."""
    return {
        "_key": "repo_abc123",
        "repository_id": "repo_abc123",
        "customer_id": "customer_test",
        "project_id": "proj_xyz789",
        "name": "backend-api",
        "description": "Main backend API service",
        "repository_url": "https://github.com/myorg/backend-api",
        "default_branch": "main",
        "tags": ["backend", "api", "production"],
        "scan_count": 5,
        "created_at": "2024-01-15T10:00:00Z",
        "updated_at": "2024-01-15T10:00:00Z",
        "last_scan_at": "2024-01-20T14:30:00Z",
        "active": True,
    }


@pytest.fixture
def sample_project():
    """Sample project data."""
    return {
        "_key": "proj_xyz789",
        "project_id": "proj_xyz789",
        "customer_id": "customer_test",
        "name": "Backend Services",
        "active": True,
    }


class TestRepositoryCreation:
    """Tests for POST /v1/repositories - Create new repository."""

    @pytest.mark.integration
    def test_create_repository_success(
        self, api_client, app, override_customer_auth, mock_repository_db, sample_project
    ):
        """
        Test: POST /v1/repositories - Successfully create new repository.

        Verifies:
        - Repository created with correct metadata
        - Returns repository_id
        - Response includes all required fields
        - 200 OK status
        """
        with patch('api.v1.endpoints.repositories.get_database', return_value=mock_repository_db):

            # Mock project verification query
            mock_repository_db.aql.execute = Mock(return_value=[sample_project])

            # Make request
            response = api_client.post(
                "/v1/repositories",
                json={
                    "name": "backend-api",
                    "project_id": "proj_xyz789",
                    "description": "Main backend API service",
                    "repository_url": "https://github.com/myorg/backend-api",
                    "default_branch": "main",
                    "tags": ["backend", "api", "production"]
                },
                headers={"X-API-Key": "test_key"}
            )

            # Verify response
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

            data = response.json()
            assert data["success"] is True
            assert "data" in data

            repo_data = data["data"]
            assert "repository_id" in repo_data
            assert repo_data["repository_id"].startswith("repo_")
            assert repo_data["name"] == "backend-api"
            assert repo_data["project_id"] == "proj_xyz789"
            assert repo_data["description"] == "Main backend API service"
            assert repo_data["repository_url"] == "https://github.com/myorg/backend-api"
            assert repo_data["default_branch"] == "main"
            assert repo_data["tags"] == ["backend", "api", "production"]
            assert repo_data["scan_count"] == 0

    @pytest.mark.integration
    def test_create_repository_without_project(
        self, api_client, app, override_customer_auth, mock_repository_db
    ):
        """
        Test: POST /v1/repositories - Create repository without project assignment.

        Verifies:
        - Repository can be created without project_id
        - project_id is null in response
        - Repository is unassigned
        """
        with patch('api.v1.endpoints.repositories.get_database', return_value=mock_repository_db):

            response = api_client.post(
                "/v1/repositories",
                json={
                    "name": "standalone-service",
                    "description": "Standalone microservice",
                    "repository_url": "https://github.com/myorg/standalone",
                    "default_branch": "develop"
                },
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            repo_data = data["data"]
            assert repo_data["project_id"] is None
            assert repo_data["name"] == "standalone-service"

    @pytest.mark.integration
    def test_create_repository_with_invalid_project(
        self, api_client, app, override_customer_auth, mock_repository_db
    ):
        """
        Test: POST /v1/repositories - Reject when project doesn't exist.

        Verifies:
        - Returns 404 when project_id is invalid
        - Error message indicates project not found
        """
        with patch('api.v1.endpoints.repositories.get_database', return_value=mock_repository_db):

            # Mock empty project query result
            mock_repository_db.aql.execute = Mock(return_value=[])

            response = api_client.post(
                "/v1/repositories",
                json={
                    "name": "test-repo",
                    "project_id": "proj_nonexistent",
                    "repository_url": "https://github.com/myorg/test"
                },
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 404
            data = response.json()
            assert "Project not found" in data["detail"]

    @pytest.mark.integration
    def test_create_repository_with_github_url(
        self, api_client, app, override_customer_auth, mock_repository_db
    ):
        """
        Test: POST /v1/repositories - Create with GitHub repository URL.

        Verifies:
        - GitHub URLs are accepted
        - URL format is preserved
        """
        with patch('api.v1.endpoints.repositories.get_database', return_value=mock_repository_db):

            response = api_client.post(
                "/v1/repositories",
                json={
                    "name": "github-repo",
                    "repository_url": "https://github.com/myorg/github-repo",
                    "default_branch": "main"
                },
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["repository_url"] == "https://github.com/myorg/github-repo"

    @pytest.mark.integration
    def test_create_repository_with_gitlab_url(
        self, api_client, app, override_customer_auth, mock_repository_db
    ):
        """
        Test: POST /v1/repositories - Create with GitLab repository URL.

        Verifies:
        - GitLab URLs are accepted
        - URL format is preserved
        """
        with patch('api.v1.endpoints.repositories.get_database', return_value=mock_repository_db):

            response = api_client.post(
                "/v1/repositories",
                json={
                    "name": "gitlab-repo",
                    "repository_url": "https://gitlab.com/myorg/gitlab-repo",
                    "default_branch": "main"
                },
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["repository_url"] == "https://gitlab.com/myorg/gitlab-repo"

    @pytest.mark.integration
    def test_create_repository_with_bitbucket_url(
        self, api_client, app, override_customer_auth, mock_repository_db
    ):
        """
        Test: POST /v1/repositories - Create with Bitbucket repository URL.

        Verifies:
        - Bitbucket URLs are accepted
        - URL format is preserved
        """
        with patch('api.v1.endpoints.repositories.get_database', return_value=mock_repository_db):

            response = api_client.post(
                "/v1/repositories",
                json={
                    "name": "bitbucket-repo",
                    "repository_url": "https://bitbucket.org/myorg/bitbucket-repo",
                    "default_branch": "master"
                },
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["repository_url"] == "https://bitbucket.org/myorg/bitbucket-repo"

    @pytest.mark.integration
    def test_create_repository_fails_with_invalid_name(
        self, api_client, app, override_customer_auth, mock_repository_db
    ):
        """
        Test: POST /v1/repositories - Reject when name is too short.

        Verifies:
        - Returns 422 validation error
        - Name must be at least 3 characters
        """
        with patch('api.v1.endpoints.repositories.get_database', return_value=mock_repository_db):

            response = api_client.post(
                "/v1/repositories",
                json={
                    "name": "ab",  # Too short (min 3 characters)
                    "repository_url": "https://github.com/myorg/test"
                },
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 422


class TestRepositoryListing:
    """Tests for GET /v1/repositories - List repositories."""

    @pytest.mark.integration
    def test_list_repositories_success(
        self, api_client, app, override_customer_auth, mock_repository_db, sample_repository, sample_project
    ):
        """
        Test: GET /v1/repositories - List all repositories.

        Verifies:
        - Returns list of repositories
        - Includes project names
        - Includes total count
        - Response structure matches ListRepositoriesResponse
        """
        with patch('api.v1.endpoints.repositories.get_database', return_value=mock_repository_db):

            # Mock AQL query result with project name
            mock_repository_db.aql.execute = Mock(return_value=[
                {**sample_repository, "project_name": "Backend Services"}
            ])

            response = api_client.get(
                "/v1/repositories",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200

            data = response.json()
            assert data["success"] is True
            assert "data" in data

            list_data = data["data"]
            assert "repositories" in list_data
            assert "total" in list_data
            assert list_data["total"] == 1

            # Verify repository details
            repo = list_data["repositories"][0]
            assert repo["repository_id"] == "repo_abc123"
            assert repo["name"] == "backend-api"
            assert repo["project_id"] == "proj_xyz789"
            assert repo["project_name"] == "Backend Services"
            assert repo["scan_count"] == 5
            assert repo["active"] is True

    @pytest.mark.integration
    def test_list_repositories_filter_by_project(
        self, api_client, app, override_customer_auth, mock_repository_db, sample_repository
    ):
        """
        Test: GET /v1/repositories?project_id=X - Filter by project.

        Verifies:
        - project_id query parameter works
        - Only repositories for specified project returned
        """
        with patch('api.v1.endpoints.repositories.get_database', return_value=mock_repository_db):

            mock_repository_db.aql.execute = Mock(return_value=[
                {**sample_repository, "project_name": "Backend Services"}
            ])

            response = api_client.get(
                "/v1/repositories?project_id=proj_xyz789",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            assert data["data"]["total"] == 1
            assert data["data"]["repositories"][0]["project_id"] == "proj_xyz789"

    @pytest.mark.integration
    def test_list_repositories_filter_by_active_status(
        self, api_client, app, override_customer_auth, mock_repository_db, sample_repository
    ):
        """
        Test: GET /v1/repositories?active=true - Filter by active status.

        Verifies:
        - active query parameter works
        - Only active repositories returned when active=true
        """
        with patch('api.v1.endpoints.repositories.get_database', return_value=mock_repository_db):

            mock_repository_db.aql.execute = Mock(return_value=[
                {**sample_repository, "project_name": "Backend Services"}
            ])

            response = api_client.get(
                "/v1/repositories?active=true",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            for repo in data["data"]["repositories"]:
                assert repo["active"] is True

    @pytest.mark.integration
    def test_list_repositories_filter_by_tags(
        self, api_client, app, override_customer_auth, mock_repository_db, sample_repository
    ):
        """
        Test: GET /v1/repositories?tags=backend,production - Filter by tags.

        Verifies:
        - tags query parameter works (comma-separated)
        - Returns repositories matching any of the specified tags
        """
        with patch('api.v1.endpoints.repositories.get_database', return_value=mock_repository_db):

            mock_repository_db.aql.execute = Mock(return_value=[
                {**sample_repository, "project_name": "Backend Services"}
            ])

            response = api_client.get(
                "/v1/repositories?tags=backend,production",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            assert data["data"]["total"] >= 0
            for repo in data["data"]["repositories"]:
                assert any(tag in repo["tags"] for tag in ["backend", "production"])

    @pytest.mark.integration
    def test_list_repositories_filter_unassigned(
        self, api_client, app, override_customer_auth, mock_repository_db
    ):
        """
        Test: GET /v1/repositories?project_id=null - List unassigned repositories.

        Verifies:
        - project_id=null filters for unassigned repositories
        - Returns only repositories without project assignment
        """
        with patch('api.v1.endpoints.repositories.get_database', return_value=mock_repository_db):

            unassigned_repo = {
                "repository_id": "repo_unassigned",
                "customer_id": "customer_test",
                "project_id": None,
                "name": "unassigned-service",
                "scan_count": 0,
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T10:00:00Z",
                "active": True,
                "project_name": None
            }

            mock_repository_db.aql.execute = Mock(return_value=[unassigned_repo])

            response = api_client.get(
                "/v1/repositories?project_id=null",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()

            for repo in data["data"]["repositories"]:
                assert repo["project_id"] is None


class TestRepositoryRetrieval:
    """Tests for GET /v1/repositories/{repository_id} - Get repository details."""

    @pytest.mark.integration
    def test_get_repository_success(
        self, api_client, app, override_customer_auth, mock_repository_db, sample_repository
    ):
        """
        Test: GET /v1/repositories/{repository_id} - Successfully retrieve repository.

        Verifies:
        - Repository details returned
        - Includes project name
        - All metadata present
        """
        with patch('api.v1.endpoints.repositories.get_database', return_value=mock_repository_db):

            mock_repository_db.aql.execute = Mock(return_value=[
                {**sample_repository, "project_name": "Backend Services"}
            ])

            response = api_client.get(
                "/v1/repositories/repo_abc123",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200

            data = response.json()
            assert data["success"] is True

            repo_data = data["data"]
            assert repo_data["repository_id"] == "repo_abc123"
            assert repo_data["name"] == "backend-api"
            assert repo_data["project_id"] == "proj_xyz789"
            assert repo_data["project_name"] == "Backend Services"
            assert repo_data["description"] == "Main backend API service"
            assert repo_data["repository_url"] == "https://github.com/myorg/backend-api"
            assert repo_data["default_branch"] == "main"
            assert repo_data["tags"] == ["backend", "api", "production"]
            assert repo_data["scan_count"] == 5
            assert repo_data["last_scan_at"] == "2024-01-20T14:30:00Z"

    @pytest.mark.integration
    def test_get_repository_not_found(
        self, api_client, app, override_customer_auth, mock_repository_db
    ):
        """
        Test: GET /v1/repositories/{repository_id} - 404 when repository doesn't exist.

        Verifies:
        - Returns 404 NOT FOUND
        - Error message indicates repository not found
        """
        with patch('api.v1.endpoints.repositories.get_database', return_value=mock_repository_db):

            # Mock empty query result
            mock_repository_db.aql.execute = Mock(return_value=[])

            response = api_client.get(
                "/v1/repositories/repo_nonexistent",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 404
            data = response.json()
            assert "Repository not found" in data["detail"]


class TestRepositoryUpdate:
    """Tests for PUT /v1/repositories/{repository_id} - Update repository."""

    @pytest.mark.integration
    def test_update_repository_success(
        self, api_client, app, override_customer_auth, mock_repository_db, sample_repository
    ):
        """
        Test: PUT /v1/repositories/{repository_id} - Successfully update repository.

        Verifies:
        - Repository fields can be updated
        - Returns updated repository
        - All fields reflect new values
        """
        with patch('api.v1.endpoints.repositories.get_database', return_value=mock_repository_db):

            # Mock repository exists query
            mock_repository_db.aql.execute = Mock(side_effect=[
                [sample_repository],  # First query: verify exists
                [],  # Second query: update project repo count
                [{**sample_repository,
                  "name": "backend-api-v2",
                  "description": "Updated backend API service",
                  "tags": ["backend", "production", "critical"],
                  "project_name": "Backend Services"}]  # Third query: fetch updated
            ])

            response = api_client.put(
                "/v1/repositories/repo_abc123",
                json={
                    "name": "backend-api-v2",
                    "description": "Updated backend API service",
                    "tags": ["backend", "production", "critical"]
                },
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200

            data = response.json()
            assert data["success"] is True

            repo_data = data["data"]
            assert repo_data["repository_id"] == "repo_abc123"
            assert repo_data["name"] == "backend-api-v2"
            assert repo_data["description"] == "Updated backend API service"
            assert repo_data["tags"] == ["backend", "production", "critical"]

    @pytest.mark.integration
    def test_update_repository_change_project(
        self, api_client, app, override_customer_auth, mock_repository_db, sample_repository, sample_project
    ):
        """
        Test: PUT /v1/repositories/{repository_id} - Reassign to different project.

        Verifies:
        - Can change project_id
        - New project is validated
        - Project counts are updated
        """
        with patch('api.v1.endpoints.repositories.get_database', return_value=mock_repository_db):

            new_project = {**sample_project, "project_id": "proj_new123", "name": "New Project"}

            # Mock queries: verify exists, verify new project, update old project count, update new project count, fetch updated
            mock_repository_db.aql.execute = Mock(side_effect=[
                [sample_repository],  # Repository exists
                [new_project],  # New project exists
                [],  # Update old project repo count
                [],  # Update new project repo count
                [{**sample_repository, "project_id": "proj_new123", "project_name": "New Project"}]  # Fetch updated
            ])

            response = api_client.put(
                "/v1/repositories/repo_abc123",
                json={"project_id": "proj_new123"},
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["project_id"] == "proj_new123"
            assert data["data"]["project_name"] == "New Project"

    @pytest.mark.integration
    def test_update_repository_unassign_project(
        self, api_client, app, override_customer_auth, mock_repository_db, sample_repository
    ):
        """
        Test: PUT /v1/repositories/{repository_id} - Unassign from project.

        Verifies:
        - Can set project_id to null
        - Repository becomes unassigned
        """
        with patch('api.v1.endpoints.repositories.get_database', return_value=mock_repository_db):

            mock_repository_db.aql.execute = Mock(side_effect=[
                [sample_repository],  # Repository exists
                [],  # Update old project repo count
                [{**sample_repository, "project_id": None, "project_name": None}]  # Fetch updated
            ])

            response = api_client.put(
                "/v1/repositories/repo_abc123",
                json={"project_id": None},
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["project_id"] is None
            assert data["data"]["project_name"] is None

    @pytest.mark.integration
    def test_update_repository_with_invalid_project(
        self, api_client, app, override_customer_auth, mock_repository_db, sample_repository
    ):
        """
        Test: PUT /v1/repositories/{repository_id} - Reject invalid project.

        Verifies:
        - Returns 404 when new project doesn't exist
        - Error message indicates project not found
        """
        with patch('api.v1.endpoints.repositories.get_database', return_value=mock_repository_db):

            mock_repository_db.aql.execute = Mock(side_effect=[
                [sample_repository],  # Repository exists
                []  # Project doesn't exist
            ])

            response = api_client.put(
                "/v1/repositories/repo_abc123",
                json={"project_id": "proj_nonexistent"},
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 404
            data = response.json()
            assert "Project not found" in data["detail"]

    @pytest.mark.integration
    def test_update_repository_not_found(
        self, api_client, app, override_customer_auth, mock_repository_db
    ):
        """
        Test: PUT /v1/repositories/{repository_id} - 404 when repository doesn't exist.
        """
        with patch('api.v1.endpoints.repositories.get_database', return_value=mock_repository_db):

            mock_repository_db.aql.execute = Mock(return_value=[])

            response = api_client.put(
                "/v1/repositories/repo_nonexistent",
                json={"name": "updated-name"},
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 404


class TestRepositoryDeletion:
    """Tests for DELETE /v1/repositories/{repository_id} - Delete repository."""

    @pytest.mark.integration
    def test_delete_repository_success(
        self, api_client, app, override_customer_auth, mock_repository_db, sample_repository
    ):
        """
        Test: DELETE /v1/repositories/{repository_id} - Successfully soft delete.

        Verifies:
        - Repository is soft deleted (active=false)
        - Historical scan data is preserved
        - Returns deletion confirmation
        - Response includes deleted_at timestamp
        """
        with patch('api.v1.endpoints.repositories.get_database', return_value=mock_repository_db):

            mock_repository_db.aql.execute = Mock(return_value=[sample_repository])

            response = api_client.delete(
                "/v1/repositories/repo_abc123",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200

            data = response.json()
            assert data["success"] is True

            delete_data = data["data"]
            assert delete_data["repository_id"] == "repo_abc123"
            assert delete_data["name"] == "backend-api"
            assert "deleted_at" in delete_data
            assert "Historical scan data is preserved" in delete_data["message"]

    @pytest.mark.integration
    def test_delete_repository_already_deleted(
        self, api_client, app, override_customer_auth, mock_repository_db, sample_repository
    ):
        """
        Test: DELETE /v1/repositories/{repository_id} - Reject already deleted.

        Verifies:
        - Returns 400 when repository already deleted
        - Error message indicates already deleted
        """
        with patch('api.v1.endpoints.repositories.get_database', return_value=mock_repository_db):

            deleted_repo = {**sample_repository, "active": False}
            mock_repository_db.aql.execute = Mock(return_value=[deleted_repo])

            response = api_client.delete(
                "/v1/repositories/repo_abc123",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 400
            data = response.json()
            assert "already deleted" in data["detail"]

    @pytest.mark.integration
    def test_delete_repository_not_found(
        self, api_client, app, override_customer_auth, mock_repository_db
    ):
        """
        Test: DELETE /v1/repositories/{repository_id} - 404 when repository doesn't exist.
        """
        with patch('api.v1.endpoints.repositories.get_database', return_value=mock_repository_db):

            mock_repository_db.aql.execute = Mock(return_value=[])

            response = api_client.delete(
                "/v1/repositories/repo_nonexistent",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 404


class TestRepositorySummary:
    """Tests for GET /v1/repositories/{repository_id}/summary - Get repository summary."""

    @pytest.mark.integration
    def test_get_repository_summary_success(
        self, api_client, app, override_customer_auth, mock_repository_db, sample_repository
    ):
        """
        Test: GET /v1/repositories/{repository_id}/summary - Successfully get summary.

        Verifies:
        - Returns aggregated repository insights
        - Includes scan count and timeline
        - Includes current findings by severity
        - Includes vulnerability trends
        - Response structure matches RepositorySummaryResponse
        """
        with patch('api.v1.endpoints.repositories.get_database', return_value=mock_repository_db):

            mock_repository_db.aql.execute = Mock(return_value=[
                {**sample_repository, "project_name": "Backend Services"}
            ])

            response = api_client.get(
                "/v1/repositories/repo_abc123/summary",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 200

            data = response.json()
            assert data["success"] is True

            summary_data = data["data"]
            assert summary_data["repository_id"] == "repo_abc123"
            assert summary_data["repository_name"] == "backend-api"
            assert summary_data["project_id"] == "proj_xyz789"
            assert summary_data["project_name"] == "Backend Services"
            assert summary_data["scan_count"] == 5

            # Verify current findings structure
            assert "current_findings" in summary_data
            findings = summary_data["current_findings"]
            assert "critical" in findings
            assert "high" in findings
            assert "medium" in findings
            assert "low" in findings
            assert "total" in findings

            # Verify trends structure
            assert "trends" in summary_data
            trends = summary_data["trends"]
            assert "new_last_7_days" in trends
            assert "resolved_last_7_days" in trends
            assert "net_change" in trends

            # Verify top vulnerabilities
            assert "top_vulnerabilities" in summary_data
            assert isinstance(summary_data["top_vulnerabilities"], list)

    @pytest.mark.integration
    def test_get_repository_summary_not_found(
        self, api_client, app, override_customer_auth, mock_repository_db
    ):
        """
        Test: GET /v1/repositories/{repository_id}/summary - 404 when repository doesn't exist.
        """
        with patch('api.v1.endpoints.repositories.get_database', return_value=mock_repository_db):

            mock_repository_db.aql.execute = Mock(return_value=[])

            response = api_client.get(
                "/v1/repositories/repo_nonexistent/summary",
                headers={"X-API-Key": "test_key"}
            )

            assert response.status_code == 404


class TestRepositoryLifecycle:
    """Integration tests for complete repository lifecycle."""

    @pytest.mark.integration
    def test_full_repository_lifecycle(
        self, api_client, app, override_customer_auth, mock_repository_db, sample_project
    ):
        """
        Test: Complete repository lifecycle - create -> update -> get summary -> delete.

        Verifies:
        - All operations work together
        - State transitions are valid
        - Data consistency maintained
        """
        with patch('api.v1.endpoints.repositories.get_database', return_value=mock_repository_db):

            # Step 1: Create repository
            mock_repository_db.aql.execute = Mock(return_value=[sample_project])

            create_response = api_client.post(
                "/v1/repositories",
                json={
                    "name": "lifecycle-test-repo",
                    "project_id": "proj_xyz789",
                    "description": "Lifecycle test repository",
                    "repository_url": "https://github.com/test/lifecycle",
                    "default_branch": "main",
                    "tags": ["test", "lifecycle"]
                },
                headers={"X-API-Key": "test_key"}
            )

            assert create_response.status_code == 200
            repository_id = create_response.json()["data"]["repository_id"]

            # Step 2: Update repository
            updated_repo = {
                "_key": repository_id.replace("repo_", ""),
                "repository_id": repository_id,
                "customer_id": "customer_test",
                "project_id": "proj_xyz789",
                "name": "lifecycle-test-repo-updated",
                "description": "Updated lifecycle test repository",
                "repository_url": "https://github.com/test/lifecycle",
                "default_branch": "develop",
                "tags": ["test", "lifecycle", "updated"],
                "scan_count": 0,
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T11:00:00Z",
                "last_scan_at": None,
                "active": True,
                "project_name": "Backend Services"
            }

            mock_repository_db.aql.execute = Mock(side_effect=[
                [updated_repo],  # Repository exists
                [],  # Update project repo count
                [updated_repo]  # Fetch updated repo
            ])

            update_response = api_client.put(
                f"/v1/repositories/{repository_id}",
                json={
                    "name": "lifecycle-test-repo-updated",
                    "description": "Updated lifecycle test repository",
                    "default_branch": "develop",
                    "tags": ["test", "lifecycle", "updated"]
                },
                headers={"X-API-Key": "test_key"}
            )

            assert update_response.status_code == 200
            assert update_response.json()["data"]["name"] == "lifecycle-test-repo-updated"

            # Step 3: Get repository summary
            mock_repository_db.aql.execute = Mock(return_value=[updated_repo])

            summary_response = api_client.get(
                f"/v1/repositories/{repository_id}/summary",
                headers={"X-API-Key": "test_key"}
            )

            assert summary_response.status_code == 200
            summary_data = summary_response.json()["data"]
            assert summary_data["repository_id"] == repository_id
            assert summary_data["repository_name"] == "lifecycle-test-repo-updated"

            # Step 4: Delete repository
            mock_repository_db.aql.execute = Mock(return_value=[updated_repo])

            delete_response = api_client.delete(
                f"/v1/repositories/{repository_id}",
                headers={"X-API-Key": "test_key"}
            )

            assert delete_response.status_code == 200
            delete_data = delete_response.json()["data"]
            assert delete_data["repository_id"] == repository_id
            assert "deleted_at" in delete_data

            print(f"✅ Full repository lifecycle test passed: create → update → get summary → delete")
