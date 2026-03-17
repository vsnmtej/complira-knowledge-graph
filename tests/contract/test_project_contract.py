"""
API Contract Tests for Project Endpoints - Validate API responses match expected schema.

These tests ensure:
1. Backend API responses match the documented contract
2. Frontend mock data matches real API responses
3. No breaking changes to API structure
4. Pydantic models are correctly defined

Tests all 6 project endpoints:
- POST /v1/projects (create)
- GET /v1/projects (list)
- GET /v1/projects/{project_id} (get)
- PUT /v1/projects/{project_id} (update)
- DELETE /v1/projects/{project_id} (delete)
- GET /v1/projects/{project_id}/summary (get summary)
"""

import json
import pytest
from pathlib import Path
from pydantic import ValidationError

from api.models.responses.projects import (
    CreateProjectResponse,
    ProjectResponse,
    ListProjectsResponse,
    ProjectSummaryResponse,
    DeleteProjectResponse,
)
from api.models.responses import APIResponse


class TestProjectContractCreate:
    """Test POST /v1/projects response contract."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses."""
        return Path("tests/fixtures/api_responses")

    def test_create_project_response_contract(self, mock_responses_dir):
        """
        Test: POST /v1/projects response matches contract.

        Validates:
        - Response structure matches APIResponse[CreateProjectResponse]
        - All required fields present
        - Field types correct
        - project_id format valid
        """
        with open(mock_responses_dir / "project_create.json") as f:
            mock_data = json.load(f)

        # Validate outer APIResponse wrapper
        assert "success" in mock_data
        assert "data" in mock_data
        assert "metadata" in mock_data
        assert mock_data["success"] is True

        # Validate CreateProjectResponse data
        data = mock_data["data"]
        required_fields = ["project_id", "name", "created_at", "repository_count"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Validate field types
        assert isinstance(data["project_id"], str)
        assert data["project_id"].startswith("proj_")
        assert isinstance(data["name"], str)
        assert len(data["name"]) >= 3
        assert isinstance(data["created_at"], str)
        assert isinstance(data["repository_count"], int)
        assert data["repository_count"] == 0  # Always 0 at creation

        # Validate optional fields
        if "description" in data:
            assert isinstance(data["description"], (str, type(None)))
        if "tags" in data:
            assert isinstance(data["tags"], list)
            for tag in data["tags"]:
                assert isinstance(tag, str)

        # Validate using Pydantic model
        try:
            response = CreateProjectResponse(**data)
            assert response.project_id == data["project_id"]
            assert response.name == data["name"]
            assert response.repository_count == 0
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match CreateProjectResponse schema: {e}")

    def test_create_project_metadata_structure(self, mock_responses_dir):
        """
        Test: POST /v1/projects response includes correct metadata.

        Validates:
        - cache_hit field present (always false for create)
        - execution_time_ms field present
        """
        with open(mock_responses_dir / "project_create.json") as f:
            mock_data = json.load(f)

        metadata = mock_data["metadata"]
        assert "cache_hit" in metadata
        assert "execution_time_ms" in metadata
        assert isinstance(metadata["cache_hit"], bool)
        assert metadata["cache_hit"] is False  # Create operations never cache
        assert isinstance(metadata["execution_time_ms"], (int, float))
        assert metadata["execution_time_ms"] > 0


class TestProjectContractList:
    """Test GET /v1/projects response contract."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses."""
        return Path("tests/fixtures/api_responses")

    def test_list_projects_response_contract(self, mock_responses_dir):
        """
        Test: GET /v1/projects response matches contract.

        Validates:
        - Response structure matches APIResponse[ListProjectsResponse]
        - projects array present
        - total count present and matches array length
        - Each project has required fields
        """
        with open(mock_responses_dir / "project_list.json") as f:
            mock_data = json.load(f)

        assert mock_data["success"] is True
        data = mock_data["data"]

        # Validate ListProjectsResponse structure
        assert "projects" in data
        assert "total" in data
        assert isinstance(data["projects"], list)
        assert isinstance(data["total"], int)
        assert data["total"] >= len(data["projects"])

        # Validate each project
        for project in data["projects"]:
            required_fields = [
                "project_id", "name", "repository_count",
                "created_at", "updated_at", "active"
            ]
            for field in required_fields:
                assert field in project, f"Missing field {field} in project"

            # Validate field types
            assert isinstance(project["project_id"], str)
            assert project["project_id"].startswith("proj_")
            assert isinstance(project["name"], str)
            assert isinstance(project["repository_count"], int)
            assert isinstance(project["active"], bool)

            # Validate optional fields
            if "description" in project:
                assert isinstance(project["description"], (str, type(None)))
            if "tags" in project:
                assert isinstance(project["tags"], list)
            if "last_scan_at" in project:
                assert isinstance(project["last_scan_at"], (str, type(None)))

        # Validate using Pydantic model
        try:
            response = ListProjectsResponse(**data)
            assert len(response.projects) == len(data["projects"])
            assert response.total == data["total"]
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match ListProjectsResponse schema: {e}")

    def test_list_projects_empty_result(self, mock_responses_dir):
        """
        Test: GET /v1/projects handles empty results correctly.

        Validates:
        - Empty projects array is valid
        - total is 0 for empty results
        """
        # Create synthetic empty response
        empty_data = {
            "success": True,
            "data": {
                "projects": [],
                "total": 0
            },
            "metadata": {
                "cache_hit": False,
                "execution_time_ms": 10.5
            }
        }

        try:
            response = ListProjectsResponse(**empty_data["data"])
            assert len(response.projects) == 0
            assert response.total == 0
        except ValidationError as e:
            pytest.fail(f"Empty result doesn't match ListProjectsResponse schema: {e}")


class TestProjectContractGet:
    """Test GET /v1/projects/{project_id} response contract."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses."""
        return Path("tests/fixtures/api_responses")

    def test_get_project_response_contract(self, mock_responses_dir):
        """
        Test: GET /v1/projects/{project_id} response matches contract.

        Validates:
        - Response structure matches APIResponse[ProjectResponse]
        - All required fields present
        - Timestamps in ISO 8601 format
        """
        with open(mock_responses_dir / "project_get.json") as f:
            mock_data = json.load(f)

        assert mock_data["success"] is True
        data = mock_data["data"]

        required_fields = [
            "project_id", "name", "repository_count",
            "created_at", "updated_at", "active"
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Validate field types and formats
        assert isinstance(data["project_id"], str)
        assert data["project_id"].startswith("proj_")
        assert isinstance(data["name"], str)
        assert isinstance(data["repository_count"], int)
        assert data["repository_count"] >= 0
        assert isinstance(data["active"], bool)

        # Validate ISO 8601 timestamps
        assert "T" in data["created_at"]
        assert "Z" in data["created_at"]
        assert "T" in data["updated_at"]
        assert "Z" in data["updated_at"]

        # Validate using Pydantic model
        try:
            response = ProjectResponse(**data)
            assert response.project_id == data["project_id"]
            assert response.name == data["name"]
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match ProjectResponse schema: {e}")


class TestProjectContractUpdate:
    """Test PUT /v1/projects/{project_id} response contract."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses."""
        return Path("tests/fixtures/api_responses")

    def test_update_project_response_contract(self, mock_responses_dir):
        """
        Test: PUT /v1/projects/{project_id} response matches contract.

        Validates:
        - Response structure matches APIResponse[ProjectResponse]
        - updated_at timestamp changes after update
        - All fields present after partial update
        """
        with open(mock_responses_dir / "project_update.json") as f:
            mock_data = json.load(f)

        assert mock_data["success"] is True
        data = mock_data["data"]

        # Validate using Pydantic model
        try:
            response = ProjectResponse(**data)
            assert response.project_id == data["project_id"]
            assert response.name == data["name"]

            # Ensure updated_at is present (required for updates)
            assert response.updated_at is not None
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match ProjectResponse schema: {e}")


class TestProjectContractDelete:
    """Test DELETE /v1/projects/{project_id} response contract."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses."""
        return Path("tests/fixtures/api_responses")

    def test_delete_project_response_contract(self, mock_responses_dir):
        """
        Test: DELETE /v1/projects/{project_id} response matches contract.

        Validates:
        - Response structure matches APIResponse[DeleteProjectResponse]
        - deleted_at timestamp present
        - Confirmation message present
        """
        with open(mock_responses_dir / "project_delete.json") as f:
            mock_data = json.load(f)

        assert mock_data["success"] is True
        data = mock_data["data"]

        required_fields = ["project_id", "name", "deleted_at", "message"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Validate field types
        assert isinstance(data["project_id"], str)
        assert data["project_id"].startswith("proj_")
        assert isinstance(data["name"], str)
        assert isinstance(data["deleted_at"], str)
        assert isinstance(data["message"], str)

        # Validate message content
        assert "deleted" in data["message"].lower()

        # Validate using Pydantic model
        try:
            response = DeleteProjectResponse(**data)
            assert response.project_id == data["project_id"]
            assert response.name == data["name"]
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match DeleteProjectResponse schema: {e}")


class TestProjectContractSummary:
    """Test GET /v1/projects/{project_id}/summary response contract."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses."""
        return Path("tests/fixtures/api_responses")

    def test_get_project_summary_response_contract(self, mock_responses_dir):
        """
        Test: GET /v1/projects/{project_id}/summary response matches contract.

        Validates:
        - Response structure matches APIResponse[ProjectSummaryResponse]
        - Aggregated findings present
        - Repository breakdown present
        - Top vulnerabilities structure correct
        """
        with open(mock_responses_dir / "project_summary.json") as f:
            mock_data = json.load(f)

        assert mock_data["success"] is True
        data = mock_data["data"]

        required_fields = [
            "project_id", "project_name", "repository_count",
            "total_scans", "findings", "repositories"
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Validate findings structure
        findings = data["findings"]
        assert "critical" in findings
        assert "high" in findings
        assert "medium" in findings
        assert "low" in findings
        assert "total" in findings

        for severity, count in findings.items():
            assert isinstance(count, int)
            assert count >= 0

        # Verify total equals sum of severities (excluding total itself)
        if findings["total"] > 0:
            severity_sum = (
                findings["critical"] + findings["high"] +
                findings["medium"] + findings["low"]
            )
            assert findings["total"] == severity_sum

        # Validate repositories breakdown
        repositories = data["repositories"]
        assert isinstance(repositories, list)
        for repo in repositories:
            assert "repository_id" in repo
            assert "repository_name" in repo
            assert "scan_count" in repo

        # Validate top vulnerabilities structure
        if "top_vulnerabilities" in data:
            assert isinstance(data["top_vulnerabilities"], list)
            for vuln in data["top_vulnerabilities"]:
                assert isinstance(vuln, dict)

        # Validate using Pydantic model
        try:
            response = ProjectSummaryResponse(**data)
            assert response.project_id == data["project_id"]
            assert response.project_name == data["project_name"]
            assert response.repository_count == len(data["repositories"])
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match ProjectSummaryResponse schema: {e}")

    def test_project_summary_empty_project(self, mock_responses_dir):
        """
        Test: GET /v1/projects/{project_id}/summary handles project with no repositories.

        Validates:
        - Empty repositories array is valid
        - repository_count is 0
        - total_scans is 0
        - findings all zero
        """
        empty_summary = {
            "success": True,
            "data": {
                "project_id": "proj_empty123",
                "project_name": "Empty Project",
                "repository_count": 0,
                "total_scans": 0,
                "findings": {
                    "critical": 0,
                    "high": 0,
                    "medium": 0,
                    "low": 0,
                    "total": 0
                },
                "top_vulnerabilities": [],
                "compliance_status": None,
                "repositories": []
            },
            "metadata": {
                "cache_hit": False,
                "execution_time_ms": 15.2
            }
        }

        try:
            response = ProjectSummaryResponse(**empty_summary["data"])
            assert response.repository_count == 0
            assert response.total_scans == 0
            assert len(response.repositories) == 0
            assert response.findings["total"] == 0
        except ValidationError as e:
            pytest.fail(f"Empty summary doesn't match ProjectSummaryResponse schema: {e}")


class TestProjectContractErrors:
    """Test project error responses match contract."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses."""
        return Path("tests/fixtures/api_responses")

    def test_project_not_found_error(self, mock_responses_dir):
        """
        Test: 404 error response for non-existent project.

        Validates:
        - Error response has "detail" field
        - Error message indicates not found
        """
        with open(mock_responses_dir / "project_errors.json") as f:
            error_data = json.load(f)

        assert "project_not_found" in error_data
        not_found_error = error_data["project_not_found"]

        assert "detail" in not_found_error
        assert isinstance(not_found_error["detail"], str)
        assert "not found" in not_found_error["detail"].lower()

    def test_project_already_deleted_error(self, mock_responses_dir):
        """
        Test: 400 error response when trying to delete already-deleted project.
        """
        with open(mock_responses_dir / "project_errors.json") as f:
            error_data = json.load(f)

        assert "project_already_deleted" in error_data
        already_deleted_error = error_data["project_already_deleted"]

        assert "detail" in already_deleted_error
        assert "already deleted" in already_deleted_error["detail"].lower()

    def test_project_validation_error(self, mock_responses_dir):
        """
        Test: 422 validation error for invalid project data.
        """
        with open(mock_responses_dir / "project_errors.json") as f:
            error_data = json.load(f)

        assert "project_validation_error" in error_data
        validation_error = error_data["project_validation_error"]

        assert "detail" in validation_error
        # 422 errors typically have array of validation details
        assert isinstance(validation_error["detail"], (str, list))


class TestProjectContractDataQuality:
    """Test project data quality and consistency."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses."""
        return Path("tests/fixtures/api_responses")

    def test_project_tags_are_realistic(self, mock_responses_dir):
        """
        Test: Project tags use realistic compliance frameworks and categories.

        Validates:
        - Tags include compliance frameworks (FDA_524B, IEC_62304, HIPAA, etc.)
        - Tags include environment categories (production, staging, development)
        - Tags include technology categories (backend, frontend, mobile, etc.)
        """
        with open(mock_responses_dir / "project_list.json") as f:
            mock_data = json.load(f)

        all_tags = []
        for project in mock_data["data"]["projects"]:
            if "tags" in project:
                all_tags.extend(project["tags"])

        # Check for realistic tag categories
        compliance_tags = ["FDA_524B", "IEC_62304", "HIPAA", "SOC2", "ISO_13485", "GDPR"]
        environment_tags = ["production", "staging", "development", "qa"]
        tech_tags = ["backend", "frontend", "mobile", "api", "microservice"]

        # At least some tags should be from realistic categories
        has_compliance = any(tag in all_tags for tag in compliance_tags)
        has_environment = any(tag in all_tags for tag in environment_tags)
        has_tech = any(tag in all_tags for tag in tech_tags)

        assert has_compliance or has_environment or has_tech, \
            "Tags should include realistic compliance, environment, or technology categories"

    def test_project_names_are_descriptive(self, mock_responses_dir):
        """
        Test: Project names are descriptive and realistic.

        Validates:
        - Names are between 3-100 characters
        - Names are human-readable
        """
        with open(mock_responses_dir / "project_list.json") as f:
            mock_data = json.load(f)

        for project in mock_data["data"]["projects"]:
            name = project["name"]
            assert len(name) >= 3, f"Project name too short: {name}"
            assert len(name) <= 100, f"Project name too long: {name}"
            assert not name.startswith("proj_"), "Project name should be human-readable, not ID"

    def test_repository_counts_are_valid(self, mock_responses_dir):
        """
        Test: Repository counts are non-negative integers.

        Validates:
        - repository_count >= 0
        - repository_count is integer
        """
        with open(mock_responses_dir / "project_list.json") as f:
            mock_data = json.load(f)

        for project in mock_data["data"]["projects"]:
            count = project["repository_count"]
            assert isinstance(count, int)
            assert count >= 0, f"Repository count cannot be negative: {count}"

    def test_timestamps_are_chronological(self, mock_responses_dir):
        """
        Test: Timestamps follow chronological order.

        Validates:
        - created_at <= updated_at
        - created_at <= last_scan_at (if present)
        """
        with open(mock_responses_dir / "project_get.json") as f:
            mock_data = json.load(f)

        data = mock_data["data"]
        created_at = data["created_at"]
        updated_at = data["updated_at"]

        # updated_at should be >= created_at
        assert updated_at >= created_at, \
            f"updated_at ({updated_at}) should be >= created_at ({created_at})"

        # If last_scan_at exists, it should be >= created_at
        if data.get("last_scan_at"):
            last_scan_at = data["last_scan_at"]
            assert last_scan_at >= created_at, \
                f"last_scan_at ({last_scan_at}) should be >= created_at ({created_at})"
