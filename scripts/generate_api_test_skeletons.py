#!/usr/bin/env python3
"""
Generate API test skeletons for untested endpoints.

This script analyzes API endpoints and generates:
1. Integration test stubs
2. Contract test stubs
3. Mock response templates

Based on the successful pattern from scan ingestion tests.
"""

import ast
import json
from pathlib import Path
from typing import Dict, List, Tuple
import re


class EndpointAnalyzer:
    """Analyzes API endpoint files to extract endpoint definitions."""

    def __init__(self, endpoints_dir: Path):
        self.endpoints_dir = endpoints_dir
        self.endpoints: Dict[str, List[Dict]] = {}

    def analyze_all(self):
        """Analyze all endpoint files."""
        for file_path in self.endpoints_dir.glob("*.py"):
            if file_path.name == "__init__.py":
                continue
            self.analyze_file(file_path)

    def analyze_file(self, file_path: Path):
        """Extract endpoints from a single file."""
        module_name = file_path.stem
        self.endpoints[module_name] = []

        with open(file_path) as f:
            content = f.read()

        # Extract router decorators and function signatures
        # Pattern: @router.METHOD("path", ...)
        pattern = r'@router\.(get|post|put|patch|delete)\((.*?)\)\s*(?:async\s+)?def\s+(\w+)\((.*?)\):'

        for match in re.finditer(pattern, content, re.DOTALL):
            method = match.group(1).upper()
            decorator_args = match.group(2)
            func_name = match.group(3)
            func_args = match.group(4)

            # Extract path from decorator args
            path_match = re.search(r'"([^"]+)"', decorator_args)
            if not path_match:
                path_match = re.search(r"'([^']+)'", decorator_args)

            if path_match:
                path = path_match.group(1)

                # Extract response model
                response_model = None
                response_match = re.search(r'response_model=(\w+(?:\[[\w\[\]]+\])?)', decorator_args)
                if response_match:
                    response_model = response_match.group(1)

                self.endpoints[module_name].append({
                    "method": method,
                    "path": path,
                    "function": func_name,
                    "response_model": response_model,
                    "module": module_name,
                })

        return self.endpoints[module_name]


class IntegrationTestGenerator:
    """Generates integration test stubs."""

    def generate(self, module_name: str, endpoints: List[Dict]) -> str:
        """Generate integration tests for a module."""
        test_class = f"Test{module_name.title().replace('_', '')}API"

        tests = []
        for endpoint in endpoints:
            test_name = f"test_{endpoint['function']}"
            method = endpoint['method'].lower()
            path = endpoint['path']

            # Generate test based on HTTP method
            if method == "post":
                test_body = self._generate_post_test(endpoint)
            elif method == "get":
                test_body = self._generate_get_test(endpoint)
            elif method in ["put", "patch"]:
                test_body = self._generate_update_test(endpoint)
            elif method == "delete":
                test_body = self._generate_delete_test(endpoint)
            else:
                test_body = f'        """Test {endpoint["function"]}"""\n        pass  # TODO: Implement'

            tests.append(f"    async def {test_name}(self, test_client, customer_token):\n{test_body}")

        return f'''"""
Integration tests for {module_name} API endpoints.

Tests API endpoints with actual database integration.
"""

import pytest
from fastapi.testclient import TestClient


class {test_class}:
    """Integration tests for {module_name} endpoints."""

    @pytest.fixture
    def test_client(self):
        """Create test client."""
        from src.api.main import app
        return TestClient(app)

    @pytest.fixture
    def customer_token(self):
        """Get valid customer authentication token."""
        # TODO: Implement token generation
        return "Bearer test_token_here"

{chr(10).join(tests)}
'''

    def _generate_post_test(self, endpoint: Dict) -> str:
        """Generate POST endpoint test."""
        path = endpoint['path']
        return f'''        """
        Test: {endpoint['method']} {path}

        Should successfully create resource and return 201/200.
        """
        # TODO: Create test payload
        payload = {{
            # Add required fields
        }}

        response = test_client.{endpoint['method'].lower()}(
            "/v1{path}",
            json=payload,
            headers={{"Authorization": customer_token}}
        )

        assert response.status_code in [200, 201]
        data = response.json()
        assert data["success"] is True
        # TODO: Add more assertions
'''

    def _generate_get_test(self, endpoint: Dict) -> str:
        """Generate GET endpoint test."""
        path = endpoint['path']
        has_params = "{" in path

        if has_params:
            # Extract param name from path like /v1/scan/{session_id}
            param_match = re.search(r'\{(\w+)\}', path)
            param_name = param_match.group(1) if param_match else "id"
            test_path = path.replace(f"{{{param_name}}}", "test_id_123")
            setup = f'        # TODO: Create test resource with {param_name}="test_id_123"\n'
        else:
            test_path = path
            setup = ""

        return f'''        """
        Test: {endpoint['method']} {path}

        Should successfully retrieve resource(s).
        """
{setup}
        response = test_client.get(
            "/v1{test_path}",
            headers={{"Authorization": customer_token}}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # TODO: Add more assertions
'''

    def _generate_update_test(self, endpoint: Dict) -> str:
        """Generate PUT/PATCH endpoint test."""
        path = endpoint['path']
        param_match = re.search(r'\{(\w+)\}', path)
        param_name = param_match.group(1) if param_match else "id"
        test_path = path.replace(f"{{{param_name}}}", "test_id_123")

        return f'''        """
        Test: {endpoint['method']} {path}

        Should successfully update resource.
        """
        # TODO: Create test resource with {param_name}="test_id_123"

        update_payload = {{
            # Add fields to update
        }}

        response = test_client.{endpoint['method'].lower()}(
            "/v1{test_path}",
            json=update_payload,
            headers={{"Authorization": customer_token}}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # TODO: Verify updates
'''

    def _generate_delete_test(self, endpoint: Dict) -> str:
        """Generate DELETE endpoint test."""
        path = endpoint['path']
        param_match = re.search(r'\{(\w+)\}', path)
        param_name = param_match.group(1) if param_match else "id"
        test_path = path.replace(f"{{{param_name}}}", "test_id_123")

        return f'''        """
        Test: {endpoint['method']} {path}

        Should successfully delete resource.
        """
        # TODO: Create test resource with {param_name}="test_id_123"

        response = test_client.delete(
            "/v1{test_path}",
            headers={{"Authorization": customer_token}}
        )

        assert response.status_code in [200, 204]

        # Verify resource deleted
        get_response = test_client.get(
            "/v1{test_path}",
            headers={{"Authorization": customer_token}}
        )
        assert get_response.status_code == 404
'''


class ContractTestGenerator:
    """Generates contract test stubs."""

    def generate(self, module_name: str, endpoints: List[Dict]) -> str:
        """Generate contract tests for a module."""
        test_class = f"Test{module_name.title().replace('_', '')}Contract"

        tests = []
        for endpoint in endpoints:
            test_name = f"test_{endpoint['function']}_contract"
            response_model = endpoint.get('response_model', 'dict')

            test_body = f'''        """
        Test: {endpoint['method']} {endpoint['path']} response matches contract

        Validates:
        - Response structure matches {response_model}
        - All required fields present
        - Field types correct
        """
        # TODO: Load mock response
        mock_file = mock_responses_dir / "{module_name}_{endpoint['function']}.json"

        if not mock_file.exists():
            pytest.skip(f"Mock file not found: {{mock_file}}")

        with open(mock_file) as f:
            mock_data = json.load(f)

        # Validate APIResponse wrapper
        assert "success" in mock_data
        assert "data" in mock_data
        assert "metadata" in mock_data

        # TODO: Validate response model fields
        # data = mock_data["data"]
        # assert "field_name" in data
'''

            tests.append(f"    def {test_name}(self, mock_responses_dir):\n{test_body}")

        return f'''"""
Contract tests for {module_name} API responses.

Validates that mock responses match expected schema.
"""

import json
import pytest
from pathlib import Path


class {test_class}:
    """Contract tests for {module_name} endpoints."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses"""
        return Path("tests/fixtures/api_responses")

{chr(10).join(tests)}
'''


class MockResponseGenerator:
    """Generates mock response templates."""

    def generate(self, module_name: str, endpoints: List[Dict]) -> Dict[str, Dict]:
        """Generate mock responses for all endpoints in a module."""
        mocks = {}

        for endpoint in endpoints:
            mock_key = f"{module_name}_{endpoint['function']}"

            # Generate appropriate mock based on method
            if endpoint['method'] in ['GET', 'POST', 'PUT', 'PATCH']:
                mock_data = {
                    "success": True,
                    "data": {
                        "id": "mock_id_123",
                        "message": f"Mock response for {endpoint['function']}"
                        # TODO: Add actual response fields
                    },
                    "metadata": {
                        "cache_hit": False,
                        "execution_time_ms": 12.34
                    }
                }
            elif endpoint['method'] == 'DELETE':
                mock_data = {
                    "success": True,
                    "data": {
                        "deleted": True,
                        "message": "Resource deleted successfully"
                    },
                    "metadata": {
                        "cache_hit": False,
                        "execution_time_ms": 5.67
                    }
                }
            else:
                mock_data = {
                    "success": True,
                    "data": {},
                    "metadata": {}
                }

            mocks[mock_key] = mock_data

        return mocks


def main():
    """Generate test skeletons for all untested endpoints."""
    print("=" * 60)
    print("API Test Skeleton Generator")
    print("=" * 60)
    print()

    # Initialize
    project_root = Path(__file__).parent.parent
    endpoints_dir = project_root / "src" / "api" / "v1" / "endpoints"
    tests_dir = project_root / "tests"
    fixtures_dir = tests_dir / "fixtures" / "api_responses"

    # Create directories if they don't exist
    (tests_dir / "integration").mkdir(parents=True, exist_ok=True)
    (tests_dir / "contract").mkdir(parents=True, exist_ok=True)
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    # Analyze endpoints
    print("📊 Analyzing API endpoints...")
    analyzer = EndpointAnalyzer(endpoints_dir)
    analyzer.analyze_all()

    # Modules to skip (already have tests)
    skip_modules = {"scan"}  # Already has comprehensive tests

    # Generate tests for each module
    integration_gen = IntegrationTestGenerator()
    contract_gen = ContractTestGenerator()
    mock_gen = MockResponseGenerator()

    generated_count = 0

    for module_name, endpoints in analyzer.endpoints.items():
        if module_name in skip_modules:
            print(f"⏭️  Skipping {module_name} (already has tests)")
            continue

        if not endpoints:
            continue

        print(f"\n📝 Generating tests for {module_name} ({len(endpoints)} endpoints)...")

        # Generate integration tests
        integration_test_file = tests_dir / "integration" / f"test_{module_name}_api.py"
        if not integration_test_file.exists():
            integration_tests = integration_gen.generate(module_name, endpoints)
            with open(integration_test_file, "w") as f:
                f.write(integration_tests)
            print(f"   ✅ Created {integration_test_file.relative_to(project_root)}")
            generated_count += 1
        else:
            print(f"   ⏭️  Integration test already exists")

        # Generate contract tests
        contract_test_file = tests_dir / "contract" / f"test_{module_name}_contract.py"
        if not contract_test_file.exists():
            contract_tests = contract_gen.generate(module_name, endpoints)
            with open(contract_test_file, "w") as f:
                f.write(contract_tests)
            print(f"   ✅ Created {contract_test_file.relative_to(project_root)}")
            generated_count += 1
        else:
            print(f"   ⏭️  Contract test already exists")

        # Generate mock responses
        mocks = mock_gen.generate(module_name, endpoints)
        for mock_key, mock_data in mocks.items():
            mock_file = fixtures_dir / f"{mock_key}.json"
            if not mock_file.exists():
                with open(mock_file, "w") as f:
                    json.dump(mock_data, f, indent=2)
                print(f"   ✅ Created mock: {mock_file.name}")
                generated_count += 1

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Generated {generated_count} new test files/mocks")
    print()
    print("Next steps:")
    print("1. Review generated test files in tests/integration/ and tests/contract/")
    print("2. Fill in TODO sections with actual test logic")
    print("3. Update mock responses in tests/fixtures/api_responses/")
    print("4. Run tests: pytest tests/integration/ -v")
    print("5. Run contract tests: pytest tests/contract/ -v")
    print()


if __name__ == "__main__":
    main()
