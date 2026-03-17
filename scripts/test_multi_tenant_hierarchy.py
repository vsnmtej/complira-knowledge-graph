#!/usr/bin/env python3
"""
E2E test script for multi-tenant hierarchy feature.

Tests:
- Project CRUD operations
- Repository CRUD operations
- Project-Repository associations
- Summary/aggregation endpoints
- Scan session hierarchy integration

Usage:
    python scripts/test_multi_tenant_hierarchy.py

Requirements:
    - API server running on http://localhost:8000
    - Valid API key (set in API_KEY variable or environment)
"""

import requests
import json
import sys
import os
from typing import Dict, Any, Optional

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/v1")
API_KEY = os.getenv("API_KEY", "your_api_key_here")

# Test state
test_state = {
    "project_ids": [],
    "repository_ids": [],
    "scan_session_ids": [],
}


class Colors:
    """ANSI color codes for terminal output."""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_test(name: str):
    """Print test name."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}TEST: {name}{Colors.ENDC}")


def print_success(message: str):
    """Print success message."""
    print(f"{Colors.OKGREEN}✓ {message}{Colors.ENDC}")


def print_error(message: str):
    """Print error message."""
    print(f"{Colors.FAIL}✗ {message}{Colors.ENDC}")


def print_info(message: str):
    """Print info message."""
    print(f"{Colors.OKCYAN}  {message}{Colors.ENDC}")


def make_request(
    method: str,
    endpoint: str,
    data: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> requests.Response:
    """Make HTTP request to API."""
    url = f"{API_BASE_URL}{endpoint}"
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json",
    }

    if method.upper() == "GET":
        response = requests.get(url, headers=headers, params=params)
    elif method.upper() == "POST":
        response = requests.post(url, headers=headers, json=data)
    elif method.upper() == "PUT":
        response = requests.put(url, headers=headers, json=data)
    elif method.upper() == "DELETE":
        response = requests.delete(url, headers=headers, json=data)
    else:
        raise ValueError(f"Unsupported HTTP method: {method}")

    return response


def test_create_project():
    """Test: Create a new project."""
    print_test("Create Project")

    payload = {
        "name": "Backend Services",
        "description": "All backend microservices",
        "tags": ["backend", "production"],
    }

    response = make_request("POST", "/projects", data=payload)

    if response.status_code == 200:
        result = response.json()
        project_id = result["data"]["project_id"]
        test_state["project_ids"].append(project_id)
        print_success(f"Created project: {project_id}")
        print_info(f"Name: {result['data']['name']}")
        print_info(f"Tags: {result['data']['tags']}")
        return True
    else:
        print_error(f"Failed with status {response.status_code}: {response.text}")
        return False


def test_list_projects():
    """Test: List all projects."""
    print_test("List Projects")

    response = make_request("GET", "/projects")

    if response.status_code == 200:
        result = response.json()
        total = result["data"]["total"]
        print_success(f"Listed {total} projects")
        for project in result["data"]["projects"]:
            print_info(f"- {project['name']} ({project['project_id']})")
        return True
    else:
        print_error(f"Failed with status {response.status_code}: {response.text}")
        return False


def test_get_project():
    """Test: Get project details."""
    print_test("Get Project Details")

    if not test_state["project_ids"]:
        print_error("No project ID available")
        return False

    project_id = test_state["project_ids"][0]
    response = make_request("GET", f"/projects/{project_id}")

    if response.status_code == 200:
        result = response.json()
        print_success(f"Retrieved project: {result['data']['name']}")
        print_info(f"Repository count: {result['data']['repository_count']}")
        print_info(f"Created: {result['data']['created_at']}")
        return True
    else:
        print_error(f"Failed with status {response.status_code}: {response.text}")
        return False


def test_create_repository_assigned():
    """Test: Create repository assigned to project."""
    print_test("Create Repository (Assigned to Project)")

    if not test_state["project_ids"]:
        print_error("No project ID available")
        return False

    project_id = test_state["project_ids"][0]

    payload = {
        "name": "backend-api",
        "project_id": project_id,
        "description": "Main backend API service",
        "repository_url": "https://github.com/myorg/backend-api",
        "default_branch": "main",
        "tags": ["backend", "api", "production"],
    }

    response = make_request("POST", "/repositories", data=payload)

    if response.status_code == 200:
        result = response.json()
        repository_id = result["data"]["repository_id"]
        test_state["repository_ids"].append(repository_id)
        print_success(f"Created repository: {repository_id}")
        print_info(f"Name: {result['data']['name']}")
        print_info(f"Project ID: {result['data']['project_id']}")
        return True
    else:
        print_error(f"Failed with status {response.status_code}: {response.text}")
        return False


def test_create_repository_unassigned():
    """Test: Create repository without project assignment."""
    print_test("Create Repository (Unassigned)")

    payload = {
        "name": "mobile-app",
        "description": "Mobile application",
        "repository_url": "https://github.com/myorg/mobile-app",
        "default_branch": "develop",
        "tags": ["mobile", "ios", "android"],
    }

    response = make_request("POST", "/repositories", data=payload)

    if response.status_code == 200:
        result = response.json()
        repository_id = result["data"]["repository_id"]
        test_state["repository_ids"].append(repository_id)
        print_success(f"Created unassigned repository: {repository_id}")
        print_info(f"Name: {result['data']['name']}")
        print_info(f"Project ID: {result['data']['project_id']}")  # Should be null
        return True
    else:
        print_error(f"Failed with status {response.status_code}: {response.text}")
        return False


def test_list_repositories():
    """Test: List all repositories."""
    print_test("List All Repositories")

    response = make_request("GET", "/repositories")

    if response.status_code == 200:
        result = response.json()
        total = result["data"]["total"]
        print_success(f"Listed {total} repositories")
        for repo in result["data"]["repositories"]:
            project_info = f"Project: {repo['project_name']}" if repo['project_name'] else "Unassigned"
            print_info(f"- {repo['name']} ({repo['repository_id']}) | {project_info}")
        return True
    else:
        print_error(f"Failed with status {response.status_code}: {response.text}")
        return False


def test_list_repositories_by_project():
    """Test: List repositories filtered by project."""
    print_test("List Repositories by Project")

    if not test_state["project_ids"]:
        print_error("No project ID available")
        return False

    project_id = test_state["project_ids"][0]
    response = make_request("GET", "/repositories", params={"project_id": project_id})

    if response.status_code == 200:
        result = response.json()
        total = result["data"]["total"]
        print_success(f"Listed {total} repositories for project {project_id}")
        for repo in result["data"]["repositories"]:
            print_info(f"- {repo['name']} ({repo['repository_id']})")
        return True
    else:
        print_error(f"Failed with status {response.status_code}: {response.text}")
        return False


def test_list_unassigned_repositories():
    """Test: List unassigned repositories."""
    print_test("List Unassigned Repositories")

    response = make_request("GET", "/repositories", params={"project_id": "null"})

    if response.status_code == 200:
        result = response.json()
        total = result["data"]["total"]
        print_success(f"Listed {total} unassigned repositories")
        for repo in result["data"]["repositories"]:
            print_info(f"- {repo['name']} ({repo['repository_id']})")
        return True
    else:
        print_error(f"Failed with status {response.status_code}: {response.text}")
        return False


def test_update_repository():
    """Test: Update repository (reassign to different project)."""
    print_test("Update Repository")

    if len(test_state["repository_ids"]) < 2:
        print_error("Need at least 2 repositories")
        return False

    # Create a second project
    payload = {
        "name": "Frontend Services",
        "description": "All frontend applications",
        "tags": ["frontend", "production"],
    }
    response = make_request("POST", "/projects", data=payload)
    if response.status_code != 200:
        print_error("Failed to create second project")
        return False

    project_id_2 = response.json()["data"]["project_id"]
    test_state["project_ids"].append(project_id_2)

    # Reassign unassigned repository to second project
    repository_id = test_state["repository_ids"][1]
    update_payload = {
        "project_id": project_id_2,
        "tags": ["mobile", "production"],
    }

    response = make_request("PUT", f"/repositories/{repository_id}", data=update_payload)

    if response.status_code == 200:
        result = response.json()
        print_success(f"Updated repository: {repository_id}")
        print_info(f"New project ID: {result['data']['project_id']}")
        print_info(f"New tags: {result['data']['tags']}")
        return True
    else:
        print_error(f"Failed with status {response.status_code}: {response.text}")
        return False


def test_get_repository_summary():
    """Test: Get repository summary."""
    print_test("Get Repository Summary")

    if not test_state["repository_ids"]:
        print_error("No repository ID available")
        return False

    repository_id = test_state["repository_ids"][0]
    response = make_request("GET", f"/repositories/{repository_id}/summary")

    if response.status_code == 200:
        result = response.json()
        print_success(f"Retrieved summary for repository: {result['data']['repository_name']}")
        print_info(f"Scan count: {result['data']['scan_count']}")
        print_info(f"Project: {result['data']['project_name'] or 'Unassigned'}")
        return True
    else:
        print_error(f"Failed with status {response.status_code}: {response.text}")
        return False


def test_get_project_summary():
    """Test: Get project summary."""
    print_test("Get Project Summary")

    if not test_state["project_ids"]:
        print_error("No project ID available")
        return False

    project_id = test_state["project_ids"][0]
    response = make_request("GET", f"/projects/{project_id}/summary")

    if response.status_code == 200:
        result = response.json()
        print_success(f"Retrieved summary for project: {result['data']['project_name']}")
        print_info(f"Repository count: {result['data']['repository_count']}")
        print_info(f"Total scans: {result['data']['total_scans']}")
        return True
    else:
        print_error(f"Failed with status {response.status_code}: {response.text}")
        return False


def test_delete_repository():
    """Test: Delete (soft delete) a repository."""
    print_test("Delete Repository")

    if not test_state["repository_ids"]:
        print_error("No repository ID available")
        return False

    repository_id = test_state["repository_ids"][0]
    response = make_request("DELETE", f"/repositories/{repository_id}")

    if response.status_code == 200:
        result = response.json()
        print_success(f"Deleted repository: {result['data']['name']}")
        print_info(f"Message: {result['data']['message']}")
        return True
    else:
        print_error(f"Failed with status {response.status_code}: {response.text}")
        return False


def test_delete_project():
    """Test: Delete (soft delete) a project."""
    print_test("Delete Project")

    if not test_state["project_ids"]:
        print_error("No project ID available")
        return False

    project_id = test_state["project_ids"][0]
    response = make_request("DELETE", f"/projects/{project_id}")

    if response.status_code == 200:
        result = response.json()
        print_success(f"Deleted project: {result['data']['name']}")
        print_info(f"Message: {result['data']['message']}")
        return True
    else:
        print_error(f"Failed with status {response.status_code}: {response.text}")
        return False


def main():
    """Run all tests."""
    print(f"{Colors.BOLD}{Colors.HEADER}{'=' * 60}")
    print("Multi-Tenant Hierarchy E2E Test Suite")
    print(f"{'=' * 60}{Colors.ENDC}\n")
    print_info(f"API Base URL: {API_BASE_URL}")
    print_info(f"Using API Key: {API_KEY[:10]}...")

    tests = [
        test_create_project,
        test_list_projects,
        test_get_project,
        test_create_repository_assigned,
        test_create_repository_unassigned,
        test_list_repositories,
        test_list_repositories_by_project,
        test_list_unassigned_repositories,
        test_update_repository,
        test_get_repository_summary,
        test_get_project_summary,
        test_delete_repository,
        test_delete_project,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print_error(f"Test crashed: {e}")
            failed += 1

    # Print summary
    print(f"\n{Colors.BOLD}{Colors.HEADER}{'=' * 60}")
    print("Test Summary")
    print(f"{'=' * 60}{Colors.ENDC}")
    print(f"{Colors.OKGREEN}Passed: {passed}{Colors.ENDC}")
    print(f"{Colors.FAIL}Failed: {failed}{Colors.ENDC}")
    print(f"Total: {passed + failed}")

    # Exit with appropriate code
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
