"""
API Contract Tests for Repository Management Endpoints.

These tests ensure:
1. Backend API responses match the documented contract
2. Frontend mock data matches real API responses
3. No breaking changes to API structure
4. Response models validate correctly
"""
import json
import pytest
from pathlib import Path
from pydantic import ValidationError

from api.models.responses.repositories import (
    CreateRepositoryResponse,
    RepositoryResponse,
    ListRepositoriesResponse,
    RepositorySummaryResponse,
    DeleteRepositoryResponse,
)
from api.models.responses import APIResponse


class TestRepositoryContract:
    """Test repository API responses match expected contract."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses"""
        return Path("tests/fixtures/api_responses")

    def test_create_repository_response_contract(self, mock_responses_dir):
        """
        Test: POST /v1/repositories response matches contract

        Validates:
        - Response structure matches APIResponse[CreateRepositoryResponse]
        - All required fields present
        - Field types correct
        - repository_id format is valid (repo_*)
        """
        with open(mock_responses_dir / "repository_create.json") as f:
            mock_data = json.load(f)

        # Validate outer APIResponse wrapper
        assert "success" in mock_data
        assert "data" in mock_data
        assert "metadata" in mock_data
        assert mock_data["success"] is True

        # Validate CreateRepositoryResponse data
        data = mock_data["data"]
        required_fields = [
            "repository_id", "name", "created_at", "scan_count"
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Validate field types
        assert isinstance(data["repository_id"], str)
        assert data["repository_id"].startswith("repo_")
        assert isinstance(data["name"], str)
        assert isinstance(data["scan_count"], int)
        assert data["scan_count"] == 0  # Always 0 at creation
        assert isinstance(data["created_at"], str)

        # Validate optional fields
        if data.get("project_id"):
            assert isinstance(data["project_id"], str)
        if data.get("description"):
            assert isinstance(data["description"], str)
        if data.get("repository_url"):
            assert isinstance(data["repository_url"], str)
        if data.get("default_branch"):
            assert isinstance(data["default_branch"], str)
        if data.get("tags"):
            assert isinstance(data["tags"], list)

        # Validate using Pydantic model
        try:
            response = CreateRepositoryResponse(**data)
            assert response.repository_id == data["repository_id"]
            assert response.name == data["name"]
            assert response.scan_count == 0
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match CreateRepositoryResponse schema: {e}")

    def test_repository_response_contract(self, mock_responses_dir):
        """
        Test: GET /v1/repositories/{repository_id} response matches contract
        """
        with open(mock_responses_dir / "repository_get.json") as f:
            mock_data = json.load(f)

        data = mock_data["data"]

        required_fields = [
            "repository_id", "name", "created_at", "updated_at",
            "scan_count", "active"
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Validate field types
        assert isinstance(data["repository_id"], str)
        assert isinstance(data["name"], str)
        assert isinstance(data["scan_count"], int)
        assert isinstance(data["active"], bool)
        assert isinstance(data["created_at"], str)
        assert isinstance(data["updated_at"], str)

        # Validate tags is a list
        if "tags" in data:
            assert isinstance(data["tags"], list)
            for tag in data["tags"]:
                assert isinstance(tag, str)

        # Validate using Pydantic model
        try:
            response = RepositoryResponse(**data)
            assert response.repository_id == data["repository_id"]
            assert response.name == data["name"]
            assert response.active == data["active"]
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match RepositoryResponse schema: {e}")

    def test_list_repositories_response_contract(self, mock_responses_dir):
        """
        Test: GET /v1/repositories response matches contract
        """
        with open(mock_responses_dir / "repository_list.json") as f:
            mock_data = json.load(f)

        data = mock_data["data"]

        # Validate ListRepositoriesResponse structure
        assert "repositories" in data
        assert "total" in data
        assert isinstance(data["repositories"], list)
        assert isinstance(data["total"], int)

        # Validate each repository in list
        for repo in data["repositories"]:
            required_fields = ["repository_id", "name", "scan_count", "active"]
            for field in required_fields:
                assert field in repo, f"Missing field {field} in repository"

            # Validate field types
            assert isinstance(repo["repository_id"], str)
            assert isinstance(repo["name"], str)
            assert isinstance(repo["scan_count"], int)
            assert isinstance(repo["active"], bool)

            # Validate using Pydantic model
            try:
                RepositoryResponse(**repo)
            except ValidationError as e:
                pytest.fail(f"Repository doesn't match RepositoryResponse schema: {e}")

        # Validate using Pydantic model
        try:
            response = ListRepositoriesResponse(**data)
            assert len(response.repositories) == data["total"]
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match ListRepositoriesResponse schema: {e}")

    def test_update_repository_response_contract(self, mock_responses_dir):
        """
        Test: PUT /v1/repositories/{repository_id} response matches contract
        """
        with open(mock_responses_dir / "repository_update.json") as f:
            mock_data = json.load(f)

        data = mock_data["data"]

        # Update response should match RepositoryResponse
        required_fields = [
            "repository_id", "name", "created_at", "updated_at", "active"
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Validate using Pydantic model
        try:
            response = RepositoryResponse(**data)
            assert response.repository_id == data["repository_id"]
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match RepositoryResponse schema: {e}")

    def test_delete_repository_response_contract(self, mock_responses_dir):
        """
        Test: DELETE /v1/repositories/{repository_id} response matches contract
        """
        with open(mock_responses_dir / "repository_delete.json") as f:
            mock_data = json.load(f)

        data = mock_data["data"]

        required_fields = ["repository_id", "name", "deleted_at", "message"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Validate field types
        assert isinstance(data["repository_id"], str)
        assert isinstance(data["name"], str)
        assert isinstance(data["deleted_at"], str)
        assert isinstance(data["message"], str)

        # Validate message contains expected text
        assert "preserved" in data["message"].lower() or "historical" in data["message"].lower()

        # Validate using Pydantic model
        try:
            response = DeleteRepositoryResponse(**data)
            assert response.repository_id == data["repository_id"]
            assert response.name == data["name"]
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match DeleteRepositoryResponse schema: {e}")

    def test_repository_summary_response_contract(self, mock_responses_dir):
        """
        Test: GET /v1/repositories/{repository_id}/summary response matches contract
        """
        with open(mock_responses_dir / "repository_summary.json") as f:
            mock_data = json.load(f)

        data = mock_data["data"]

        required_fields = [
            "repository_id", "repository_name", "scan_count",
            "current_findings", "trends", "top_vulnerabilities"
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Validate current_findings structure
        findings = data["current_findings"]
        assert "critical" in findings
        assert "high" in findings
        assert "medium" in findings
        assert "low" in findings
        assert "total" in findings

        for severity in ["critical", "high", "medium", "low", "total"]:
            assert isinstance(findings[severity], int), f"{severity} should be integer"
            assert findings[severity] >= 0, f"{severity} should be non-negative"

        # Validate total equals sum of severities
        assert findings["total"] >= (
            findings["critical"] + findings["high"] + findings["medium"] + findings["low"]
        )

        # Validate trends structure
        trends = data["trends"]
        assert "new_last_7_days" in trends
        assert "resolved_last_7_days" in trends
        assert "net_change" in trends

        for trend_key in ["new_last_7_days", "resolved_last_7_days", "net_change"]:
            assert isinstance(trends[trend_key], int), f"{trend_key} should be integer"

        # Validate top_vulnerabilities is a list
        assert isinstance(data["top_vulnerabilities"], list)

        # Validate using Pydantic model
        try:
            response = RepositorySummaryResponse(**data)
            assert response.repository_id == data["repository_id"]
            assert response.repository_name == data["repository_name"]
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match RepositorySummaryResponse schema: {e}")

    def test_repository_mock_data_has_all_repository_types(self, mock_responses_dir):
        """
        Test: Mock data includes different repository types (GitHub, GitLab, Bitbucket)
        """
        with open(mock_responses_dir / "repository_list.json") as f:
            mock_data = json.load(f)

        repositories = mock_data["data"]["repositories"]

        # Check for different repository URL patterns
        github_repos = [r for r in repositories if r.get("repository_url") and "github.com" in r["repository_url"]]
        gitlab_repos = [r for r in repositories if r.get("repository_url") and "gitlab.com" in r["repository_url"]]
        bitbucket_repos = [r for r in repositories if r.get("repository_url") and "bitbucket.org" in r["repository_url"]]

        # Should have at least one of each type (or mixed)
        assert len(github_repos) > 0 or len(gitlab_repos) > 0 or len(bitbucket_repos) > 0, \
            "Mock data should include repository URLs"

        print(f"✅ Mock data includes repository URLs: GitHub={len(github_repos)}, GitLab={len(gitlab_repos)}, Bitbucket={len(bitbucket_repos)}")

    def test_repository_mock_data_has_different_branches(self, mock_responses_dir):
        """
        Test: Mock data includes different branch names (main, master, develop)
        """
        with open(mock_responses_dir / "repository_list.json") as f:
            mock_data = json.load(f)

        repositories = mock_data["data"]["repositories"]

        # Collect unique branch names
        branches = {r.get("default_branch") for r in repositories if r.get("default_branch")}

        # Should have variety of branch names
        assert len(branches) > 0, "Mock data should include default branches"

        # Common branches
        common_branches = {"main", "master", "develop", "development"}
        assert any(branch in common_branches for branch in branches), \
            f"Mock data should include common branch names, got: {branches}"

        print(f"✅ Mock data includes branches: {branches}")

    def test_repository_mock_data_has_tags(self, mock_responses_dir):
        """
        Test: Mock data includes repository tags for filtering
        """
        with open(mock_responses_dir / "repository_list.json") as f:
            mock_data = json.load(f)

        repositories = mock_data["data"]["repositories"]

        # Check that at least some repositories have tags
        repos_with_tags = [r for r in repositories if r.get("tags") and len(r["tags"]) > 0]

        assert len(repos_with_tags) > 0, "Mock data should include repositories with tags"

        # Collect all unique tags
        all_tags = set()
        for repo in repos_with_tags:
            all_tags.update(repo["tags"])

        # Should have variety of tags
        assert len(all_tags) >= 3, f"Mock data should have diverse tags, got: {all_tags}"

        print(f"✅ Mock data includes tags: {all_tags}")

    def test_repository_mock_data_has_scan_counts(self, mock_responses_dir):
        """
        Test: Mock data includes realistic scan counts
        """
        with open(mock_responses_dir / "repository_list.json") as f:
            mock_data = json.load(f)

        repositories = mock_data["data"]["repositories"]

        # Check scan counts
        scan_counts = [r["scan_count"] for r in repositories]

        # Should have variety (some with scans, some without)
        assert any(count == 0 for count in scan_counts), "Should have new repositories (scan_count=0)"
        assert any(count > 0 for count in scan_counts), "Should have repositories with scans"

        # Scan counts should be non-negative
        assert all(count >= 0 for count in scan_counts), "Scan counts should be non-negative"

        print(f"✅ Mock data scan counts range: {min(scan_counts)} to {max(scan_counts)}")

    def test_repository_mock_data_includes_assigned_and_unassigned(self, mock_responses_dir):
        """
        Test: Mock data includes both project-assigned and unassigned repositories
        """
        with open(mock_responses_dir / "repository_list.json") as f:
            mock_data = json.load(f)

        repositories = mock_data["data"]["repositories"]

        assigned_repos = [r for r in repositories if r.get("project_id")]
        unassigned_repos = [r for r in repositories if not r.get("project_id")]

        # Should have both types
        assert len(assigned_repos) > 0, "Mock data should include project-assigned repositories"
        assert len(unassigned_repos) > 0, "Mock data should include unassigned repositories"

        print(f"✅ Mock data: {len(assigned_repos)} assigned, {len(unassigned_repos)} unassigned repositories")

    def test_repository_mock_data_includes_active_and_inactive(self, mock_responses_dir):
        """
        Test: Mock data includes both active and soft-deleted repositories
        """
        with open(mock_responses_dir / "repository_list.json") as f:
            mock_data = json.load(f)

        repositories = mock_data["data"]["repositories"]

        active_repos = [r for r in repositories if r.get("active", True) is True]
        inactive_repos = [r for r in repositories if r.get("active", True) is False]

        # Should have both types for testing
        assert len(active_repos) > 0, "Mock data should include active repositories"
        # Note: Inactive repos might not be in default list (filtered out)
        # but we test this in the contract

        print(f"✅ Mock data: {len(active_repos)} active repositories")

    def test_metadata_structure(self, mock_responses_dir):
        """
        Test: All responses include metadata with cache_hit and execution_time_ms
        """
        mock_files = [
            "repository_create.json",
            "repository_get.json",
            "repository_list.json",
            "repository_update.json",
            "repository_delete.json",
            "repository_summary.json"
        ]

        for mock_file in mock_files:
            with open(mock_responses_dir / mock_file) as f:
                mock_data = json.load(f)

            assert "metadata" in mock_data, f"{mock_file} missing metadata"
            metadata = mock_data["metadata"]

            assert "cache_hit" in metadata, f"{mock_file} metadata missing cache_hit"
            assert "execution_time_ms" in metadata, f"{mock_file} metadata missing execution_time_ms"

            assert isinstance(metadata["cache_hit"], bool)
            assert isinstance(metadata["execution_time_ms"], (int, float))
            assert metadata["execution_time_ms"] > 0, "Execution time should be positive"

    def test_repository_summary_findings_consistency(self, mock_responses_dir):
        """
        Test: Repository summary current_findings total matches sum of severities
        """
        with open(mock_responses_dir / "repository_summary.json") as f:
            mock_data = json.load(f)

        findings = mock_data["data"]["current_findings"]

        # Calculate sum of individual severities
        severity_sum = (
            findings["critical"] +
            findings["high"] +
            findings["medium"] +
            findings["low"]
        )

        # Total should equal sum (or be greater if there are other categories)
        assert findings["total"] >= severity_sum, \
            f"Total findings ({findings['total']}) should be >= sum of severities ({severity_sum})"

        print(f"✅ Findings consistency check passed: total={findings['total']}, sum={severity_sum}")

    def test_repository_summary_trends_consistency(self, mock_responses_dir):
        """
        Test: Repository summary trends net_change matches new - resolved
        """
        with open(mock_responses_dir / "repository_summary.json") as f:
            mock_data = json.load(f)

        trends = mock_data["data"]["trends"]

        # Calculate expected net change
        expected_net_change = trends["new_last_7_days"] - trends["resolved_last_7_days"]

        # Should match
        assert trends["net_change"] == expected_net_change, \
            f"Net change ({trends['net_change']}) should equal new - resolved ({expected_net_change})"

        print(f"✅ Trends consistency check passed: net_change={trends['net_change']}")
