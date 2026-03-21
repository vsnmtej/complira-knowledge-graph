"""
Architecture tests - validate patterns are followed.

These tests fail if code violates architectural patterns.
Run with: pytest tests/architecture/ -v
"""

import pytest
from pathlib import Path
import re


class TestRepositoryPattern:
    """Test repository pattern compliance."""

    def test_endpoints_do_not_import_repositories(self):
        """Endpoints should use services, not repositories directly."""
        violations = []

        endpoints_path = Path('src/api/v1/endpoints')
        if not endpoints_path.exists():
            pytest.skip("Endpoints directory not found")

        for filepath in endpoints_path.rglob('*.py'):
            if filepath.name == '__init__.py':
                continue

            with open(filepath) as f:
                content = f.read()
                # Check for direct repository imports
                if re.search(r'from api\.repositories(?:\.[\w]+)? import', content):
                    violations.append(str(filepath))

        assert not violations, (
            f"Endpoints importing repositories directly: {violations}\n"
            "Endpoints should use services, not repositories."
        )

    def test_no_direct_db_collection_calls_in_services(self):
        """Services should use repositories, not db.collection()."""
        violations = []

        services_path = Path('src/api/services')
        if not services_path.exists():
            pytest.skip("Services directory not found")

        for filepath in services_path.rglob('*.py'):
            if filepath.name in ['__init__.py', 'base.py']:
                continue

            with open(filepath) as f:
                for line_num, line in enumerate(f, 1):
                    # Skip comments
                    if line.strip().startswith('#'):
                        continue

                    if re.search(r'db\.collection\(', line):
                        violations.append(f"{filepath}:{line_num}")

        assert not violations, (
            f"Direct db.collection() calls in services: {violations}\n"
            "Services should use repositories for database access."
        )

    def test_repositories_extend_base_repository(self):
        """All repositories should extend BaseRepository."""
        violations = []

        repos_path = Path('src/api/repositories')
        if not repos_path.exists():
            pytest.skip("Repositories directory not found")

        for filepath in repos_path.rglob('*.py'):
            if filepath.name in ['__init__.py', 'base.py']:
                continue

            with open(filepath) as f:
                content = f.read()

                # Check if file defines a repository class
                if re.search(r'class \w+Repository\(', content):
                    # Check if it extends BaseRepository
                    if not re.search(r'class \w+Repository\(BaseRepository', content):
                        violations.append(str(filepath))

        assert not violations, (
            f"Repositories not extending BaseRepository: {violations}\n"
            "All repositories must extend BaseRepository."
        )


class TestServiceLayerPattern:
    """Test service layer pattern compliance."""

    def test_endpoints_instantiate_services(self):
        """Endpoints should instantiate and use services."""
        violations = []

        endpoints_path = Path('src/api/v1/endpoints')
        if not endpoints_path.exists():
            pytest.skip("Endpoints directory not found")

        for filepath in endpoints_path.rglob('*.py'):
            if filepath.name == '__init__.py':
                continue

            with open(filepath) as f:
                content = f.read()

                # Check if file defines routes
                if '@router.' in content:
                    # Check if it uses services
                    has_service_usage = (
                        'Service(' in content or
                        'service = ' in content.lower()
                    )

                    if not has_service_usage:
                        violations.append(str(filepath))

        # This is informational - some endpoints may not need services
        if violations:
            print(f"\n⚠️  Endpoints potentially not using services: {violations}")

    def test_services_extend_base_graph_service(self):
        """Services performing graph operations should extend BaseGraphService."""
        violations = []

        services_path = Path('src/api/services')
        if not services_path.exists():
            pytest.skip("Services directory not found")

        for filepath in services_path.rglob('*.py'):
            if filepath.name in ['__init__.py', 'base.py']:
                continue

            with open(filepath) as f:
                content = f.read()

                # Check if file defines a service class
                if re.search(r'class \w+Service\(', content):
                    # Check if it performs graph operations
                    has_graph_ops = any(keyword in content for keyword in [
                        'traverse',
                        'shortest_path',
                        'aql_execute',
                        'OUTBOUND',
                        'INBOUND',
                    ])

                    if has_graph_ops:
                        # Check if it extends BaseGraphService
                        if not re.search(r'class \w+Service\(BaseGraphService', content):
                            violations.append(str(filepath))

        # This is informational - not all services need graph operations
        if violations:
            print(f"\n⚠️  Services with graph operations not extending BaseGraphService: {violations}")


class TestParserFactoryPattern:
    """Test parser factory pattern compliance."""

    def test_no_direct_parser_instantiation_in_services(self):
        """Services should use ParserFactory, not direct instantiation."""
        violations = []

        services_path = Path('src/api/services')
        if not services_path.exists():
            pytest.skip("Services directory not found")

        for filepath in services_path.rglob('*.py'):
            if filepath.name == '__init__.py':
                continue

            with open(filepath) as f:
                content = f.read()

                # Check for direct parser instantiation
                parser_patterns = [
                    r'SARIFParser\(\)',
                    r'CycloneDXParser\(\)',
                    r'OSVParser\(\)',
                    r'SPDXParser\(\)',
                ]

                for pattern in parser_patterns:
                    if re.search(pattern, content):
                        violations.append(str(filepath))
                        break

        assert not violations, (
            f"Direct parser instantiation in services: {violations}\n"
            "Services should use ParserFactory.get_parser() instead."
        )

    def test_parsers_extend_base_scan_parser(self):
        """All parsers should extend BaseScanParser."""
        violations = []

        parsers_path = Path('src/api/parsers')
        if not parsers_path.exists():
            pytest.skip("Parsers directory not found")

        for filepath in parsers_path.rglob('*.py'):
            if filepath.name in ['__init__.py', 'base.py', 'factory.py']:
                continue

            with open(filepath) as f:
                content = f.read()

                # Check if file defines a parser class
                if re.search(r'class \w+Parser\(', content):
                    # Check if it extends BaseScanParser
                    if not re.search(r'class \w+Parser\(BaseScanParser', content):
                        violations.append(str(filepath))

        assert not violations, (
            f"Parsers not extending BaseScanParser: {violations}\n"
            "All parsers must extend BaseScanParser."
        )


class TestMultiTenantPattern:
    """Test multi-tenant database pattern compliance."""

    def test_no_direct_arango_client_outside_core(self):
        """Only core/database.py should instantiate ArangoClient."""
        violations = []

        src_api = Path('src/api')
        if not src_api.exists():
            pytest.skip("API directory not found")

        for filepath in src_api.rglob('*.py'):
            # Skip allowed files
            if 'core/database.py' in str(filepath) or 'test_' in filepath.name:
                continue

            with open(filepath) as f:
                content = f.read()

                if 'ArangoClient(' in content:
                    violations.append(str(filepath))

        assert not violations, (
            f"Direct ArangoClient usage outside core: {violations}\n"
            "Use get_customer_db() or get_reference_db() instead."
        )

    def test_no_hardcoded_database_names(self):
        """Database names should not be hardcoded."""
        violations = []

        src_api = Path('src/api')
        if not src_api.exists():
            pytest.skip("API directory not found")

        for filepath in src_api.rglob('*.py'):
            # Skip allowed files
            if 'core/database.py' in str(filepath) or 'core/config.py' in str(filepath):
                continue

            if 'test_' in filepath.name:
                continue

            with open(filepath) as f:
                for line_num, line in enumerate(f, 1):
                    # Skip comments
                    if line.strip().startswith('#'):
                        continue

                    # Check for hardcoded database names
                    if re.search(r'client\.db\(["\']complira_', line):
                        violations.append(f"{filepath}:{line_num}")

        assert not violations, (
            f"Hardcoded database names found: {violations}\n"
            "Use get_customer_db(customer_id) or get_reference_db() instead."
        )


class TestDRYPrinciple:
    """Test DRY (Don't Repeat Yourself) principle compliance."""

    def test_services_use_base_graph_service_methods(self):
        """Services should use BaseGraphService methods, not duplicate traversal logic."""
        violations = []

        services_path = Path('src/api/services')
        if not services_path.exists():
            pytest.skip("Services directory not found")

        for filepath in services_path.rglob('*.py'):
            if filepath.name in ['__init__.py', 'base.py']:
                continue

            with open(filepath) as f:
                content = f.read()

                # Check for duplicated traversal patterns
                # (services should call self.traverse() instead)
                has_raw_traversal = re.search(
                    r'FOR v, e, p IN \d+\.\.\d+ (OUTBOUND|INBOUND|ANY)',
                    content
                )

                extends_base = 'BaseGraphService' in content
                uses_base_method = (
                    'self.traverse(' in content or
                    'self.shortest_path(' in content or
                    'self.get_neighbors(' in content
                )

                if has_raw_traversal and extends_base and not uses_base_method:
                    violations.append(str(filepath))

        # This is informational
        if violations:
            print(f"\n⚠️  Services with duplicated traversal logic: {violations}")
            print("    Consider using BaseGraphService.traverse() method")


class TestCodeOrganization:
    """Test code organization rules."""

    def test_models_in_models_directory(self):
        """Pydantic models should be in api/models/."""
        violations = []

        src_api = Path('src/api')
        if not src_api.exists():
            pytest.skip("API directory not found")

        # Check for Pydantic models outside models directory
        for filepath in src_api.rglob('*.py'):
            # Skip allowed locations
            if 'models/' in str(filepath) or 'test_' in filepath.name:
                continue

            with open(filepath) as f:
                content = f.read()

                # Check for Pydantic model definitions
                if re.search(r'class \w+\(BaseModel\):', content):
                    # Allow in repositories/services for internal models
                    if 'repositories/' not in str(filepath) and 'services/' not in str(filepath):
                        violations.append(str(filepath))

        # This is informational - some internal models are acceptable
        if violations:
            print(f"\n⚠️  Pydantic models defined outside models/ directory: {violations}")

    def test_no_business_logic_in_endpoints(self):
        """Endpoints should not contain complex business logic."""
        violations = []

        endpoints_path = Path('src/api/v1/endpoints')
        if not endpoints_path.exists():
            pytest.skip("Endpoints directory not found")

        for filepath in endpoints_path.rglob('*.py'):
            if filepath.name == '__init__.py':
                continue

            with open(filepath) as f:
                content = f.read()
                lines = content.split('\n')

                # Check for signs of business logic in endpoint functions
                in_endpoint_function = False
                endpoint_lines = []

                for line in lines:
                    if '@router.' in line:
                        in_endpoint_function = True
                        endpoint_lines = []

                    if in_endpoint_function:
                        endpoint_lines.append(line)

                        # End of function
                        if line and not line[0].isspace() and 'def ' not in line:
                            in_endpoint_function = False

                            # Check endpoint lines for business logic indicators
                            endpoint_content = '\n'.join(endpoint_lines)

                            # Complex logic indicators
                            has_complex_logic = any([
                                len([l for l in endpoint_lines if l.strip().startswith('for ')]) > 1,
                                len([l for l in endpoint_lines if l.strip().startswith('if ')]) > 3,
                                'db.collection(' in endpoint_content,
                                '.insert(' in endpoint_content and 'Service(' not in endpoint_content,
                            ])

                            if has_complex_logic:
                                violations.append(str(filepath))
                                break

        # This is informational
        if violations:
            print(f"\n⚠️  Endpoints with potential business logic: {violations}")
            print("    Consider moving logic to services")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
