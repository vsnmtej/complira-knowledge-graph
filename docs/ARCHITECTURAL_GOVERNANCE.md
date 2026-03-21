# Architectural Governance Guide

> **Purpose**: Ensure architectural consistency, prevent ad-hoc implementations, and maintain code quality as the codebase grows.

## Table of Contents

1. [Introduction](#introduction)
2. [Core Principles](#core-principles)
3. [Code Organization](#code-organization)
4. [Required Patterns](#required-patterns)
5. [Enforcement Mechanisms](#enforcement-mechanisms)
6. [Common Tasks](#common-tasks)
7. [Anti-Patterns](#anti-patterns)
8. [Onboarding Checklist](#onboarding-checklist)

---

## Introduction

### Why This Matters

As our codebase grows, maintaining architectural consistency becomes critical. Without clear patterns and enforcement:

- **Duplication proliferates** - Developers create new parsers/repositories instead of using existing ones
- **Technical debt accumulates** - Ad-hoc implementations bypass established patterns
- **Maintenance costs explode** - Inconsistent code is harder to understand, debug, and extend
- **Quality degrades** - Testing becomes fragmented, bugs slip through

This guide establishes **clear rules** for where code lives, **enforced patterns** for how code is structured, and **validation mechanisms** to catch violations early.

### Our Architecture at a Glance

```
Multi-Tenant SaaS Application
├── Reference Database (shared, read-only)
│   └── CVE, CWE, ATT&CK, NIST controls, etc.
├── Customer Databases (isolated per customer)
│   └── Scans, findings, components, custom mappings
└── API Layer
    ├── Parsers (SARIF, CycloneDX, etc.)
    ├── Repositories (database access)
    ├── Services (business logic)
    └── Endpoints (thin controllers)
```

**Key Constraint**: All customer data MUST be isolated in customer-specific databases. Never mix customer data in the reference database.

---

## Core Principles

### 1. Separation of Concerns (SRP)

Each layer has ONE responsibility:

- **Parsers**: Convert external formats to internal models
- **Repositories**: Handle ALL database access
- **Services**: Orchestrate business logic
- **Endpoints**: Handle HTTP concerns (auth, validation, serialization)

**Rule**: If a class has multiple reasons to change, it violates SRP.

### 2. Dependency Inversion (DIP)

Depend on abstractions, not concrete implementations:

- Services depend on `IRepository` protocol, not `ComponentRepository`
- Services depend on `IDatabase` protocol, not `ArangoClient`
- Services depend on `IScanParser` protocol, not `SARIFParser`

**Rule**: Never import concrete implementations in service constructors. Use protocols/abstractions.

### 3. Open/Closed Principle (OCP)

Code should be open for extension, closed for modification:

- Add new parsers by implementing `BaseScanParser` - no changes to `ScanIngestionService`
- Add new repositories by extending `BaseRepository` - no changes to services
- Add new services by extending `BaseGraphService` - no changes to endpoints

**Rule**: Adding new functionality should NOT require modifying existing classes (except registration/wiring).

### 4. Don't Repeat Yourself (DRY)

Shared logic lives in base classes:

- `BaseScanParser`: Common parsing patterns (validation, error handling)
- `BaseRepository`: Common CRUD operations
- `BaseGraphService`: Common graph traversals (shortest path, coverage, risk aggregation)

**Rule**: If you copy-paste code, refactor it into a base class or utility.

### 5. Multi-Tenant Database Isolation

Customer data MUST be isolated:

- **Reference DB**: Shared, read-only data (CVEs, CWE, ATT&CK)
- **Customer DBs**: Isolated per customer (scans, findings, components)

**Rule**: NEVER call `db.collection()` directly. ALWAYS use `get_customer_db(customer_id)` or `get_reference_db()`.

---

## Code Organization

### Directory Structure

```
src/
├── api/                          # Customer-facing API
│   ├── core/                     # Core infrastructure
│   │   ├── config.py            # Settings (env vars, secrets)
│   │   ├── database.py          # Multi-tenant DB routing ⚠️
│   │   ├── cache.py             # Redis cache abstraction
│   │   └── security.py          # Authentication/authorization
│   │
│   ├── models/                   # Pydantic models
│   │   ├── domain/              # Domain entities (ScanSession, Finding)
│   │   ├── requests/            # API request models
│   │   └── responses/           # API response models
│   │
│   ├── parsers/                  # Scan format parsers ⚠️
│   │   ├── base.py              # BaseScanParser, IScanParser
│   │   ├── factory.py           # ParserFactory (OCP)
│   │   ├── sarif.py             # SARIF parser
│   │   ├── cyclonedx.py         # CycloneDX parser
│   │   └── ...                  # New parsers here
│   │
│   ├── repositories/             # Database access layer ⚠️
│   │   ├── base.py              # BaseRepository, IRepository
│   │   ├── scan.py              # ScanSessionRepository, ScanFindingRepository
│   │   ├── component.py         # ComponentRepository
│   │   ├── vulnerability.py     # VulnerabilityRepository
│   │   └── ...                  # New repositories here
│   │
│   ├── services/                 # Business logic layer ⚠️
│   │   ├── base.py              # BaseGraphService (DRY)
│   │   ├── scan.py              # ScanIngestionService
│   │   ├── enrichment.py        # EnrichmentService
│   │   ├── control_mapping.py   # ControlMappingService
│   │   └── ...                  # New services here
│   │
│   └── v1/                       # API version 1
│       └── endpoints/            # HTTP endpoints ⚠️
│           ├── scan.py          # POST /v1/scan/ingest
│           ├── enrichment.py    # GET /v1/enrich/{cve_id}
│           └── ...              # New endpoints here
│
└── complira_graph/               # Background agents & orchestration
    ├── agents/                   # Data ingestion agents
    ├── services/                 # Background services
    └── orchestrator/             # Agent scheduling
```

**⚠️ = Critical paths - follow patterns strictly**

### What Goes Where

| Code Type | Location | Example |
|-----------|----------|---------|
| Database access | `api/repositories/` | Never in endpoints/services |
| Business logic | `api/services/` | Never in endpoints/parsers |
| HTTP handling | `api/v1/endpoints/` | Never in services/repositories |
| External format parsing | `api/parsers/` | Never in endpoints/services |
| Request/response models | `api/models/` | Never inline in endpoints |
| Configuration | `api/core/config.py` | Never hardcoded elsewhere |
| Multi-tenant DB routing | `api/core/database.py` | Never bypass this |

---

## Required Patterns

### Pattern 1: Repository Pattern

**What**: All database access goes through repositories.

**Why**: Centralize DB logic, enable testing with mocks, enforce multi-tenancy.

**Implementation**:

```python
# ✅ CORRECT: Repository encapsulates DB access
class ScanFindingRepository(BaseRepository):
    """Repository for scan_findings collection."""

    def __init__(self, db: IDatabase):
        super().__init__(db, "scan_findings")

    def list_session_findings(
        self,
        customer_id: str,
        scan_session_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict]:
        """List findings for a scan session."""
        query = """
        FOR doc IN scan_findings
            FILTER doc.customer_id == @customer_id
            FILTER doc.scan_session_id == @session_id
            SORT doc.created_at DESC
            LIMIT @offset, @limit
            RETURN doc
        """

        cursor = self.db.aql_execute(
            query,
            bind_vars={
                "customer_id": customer_id,
                "session_id": scan_session_id,
                "offset": offset,
                "limit": limit,
            }
        )

        return list(cursor)
```

**Usage in Service**:

```python
# ✅ CORRECT: Service uses repository
class ScanIngestionService(BaseGraphService):
    async def ingest_scan(self, customer_id: str, scan_request: ScanIngestRequest):
        # Get customer database
        customer_db = get_customer_db(customer_id)

        # Initialize repositories
        finding_repo = ScanFindingRepository(customer_db)

        # Use repository methods
        findings = await finding_repo.list_session_findings(
            customer_id=customer_id,
            scan_session_id=scan_session_id,
        )
```

**Anti-Pattern**:

```python
# ❌ WRONG: Direct DB access in service
class ScanIngestionService:
    async def ingest_scan(self, customer_id: str, scan_request: ScanIngestRequest):
        customer_db = get_customer_db(customer_id)

        # ❌ Direct collection access bypasses repository
        findings = customer_db.collection("scan_findings").all()
```

**Rules**:

1. ALL database access MUST go through repositories
2. Repositories extend `BaseRepository` and implement `IRepository`
3. Services receive repository instances (constructor injection)
4. NEVER call `db.collection()` in services or endpoints

---

### Pattern 2: Service Layer Pattern

**What**: All business logic lives in services.

**Why**: Keep endpoints thin, enable reusability, simplify testing.

**Implementation**:

```python
# ✅ CORRECT: Service contains business logic
class ScanIngestionService(BaseGraphService):
    """
    Scan ingestion service.

    Orchestrates:
    - Parser selection (via factory)
    - Scan session creation
    - Finding normalization
    - Component extraction
    - Edge creation
    """

    async def ingest_scan(
        self,
        customer_id: str,
        scan_request: ScanIngestRequest,
    ):
        # Step 1: Get parser (OCP)
        parser = ParserFactory.get_parser(scan_request.format)

        # Step 2: Parse payload
        parsed_data = parser.parse(scan_request.payload)

        # Step 3: Create scan session
        customer_db = get_customer_db(customer_id)
        session_repo = ScanSessionRepository(customer_db)
        scan_session = session_repo.create_session(...)

        # Step 4: Store findings
        finding_repo = ScanFindingRepository(customer_db)
        findings = await self._store_findings(...)

        # Step 5: Create edges
        await self._create_edges(...)

        return scan_session
```

**Usage in Endpoint**:

```python
# ✅ CORRECT: Endpoint delegates to service
@router.post("/ingest")
async def ingest_scan_endpoint(
    request: ScanIngestRequest,
    customer: Customer = Depends(get_current_customer),
):
    """POST /v1/scan/ingest - Ingest scan results."""

    # Instantiate service
    service = ScanIngestionService(
        db=get_reference_db(),
        cache=RedisCacheService(),
    )

    # Delegate to service
    result = await service.ingest_scan(
        customer_id=customer.id,
        scan_request=request,
    )

    # Return response
    return APIResponse(
        success=True,
        data=result,
    )
```

**Anti-Pattern**:

```python
# ❌ WRONG: Business logic in endpoint
@router.post("/ingest")
async def ingest_scan_endpoint(
    request: ScanIngestRequest,
    customer: Customer = Depends(get_current_customer),
):
    # ❌ Parsing logic in endpoint
    if request.format == "sarif":
        parser = SARIFParser()
    elif request.format == "cyclonedx":
        parser = CycloneDXParser()

    # ❌ Database access in endpoint
    customer_db = get_customer_db(customer.id)
    findings = customer_db.collection("scan_findings").insert(...)

    # ❌ Business logic in endpoint
    for finding in findings:
        if finding["severity"] == "CRITICAL":
            # Send alert...
            pass
```

**Rules**:

1. Endpoints ONLY handle HTTP concerns (auth, validation, serialization)
2. ALL business logic goes in services
3. Services extend `BaseGraphService` for graph operations
4. Services receive dependencies via constructor (db, cache)
5. Endpoints instantiate services and call methods

---

### Pattern 3: Parser Factory Pattern

**What**: Use factory to get appropriate parser based on scan format.

**Why**: Open/Closed Principle - add new parsers without changing existing code.

**Implementation**:

```python
# ✅ CORRECT: Factory provides parser
class ParserFactory:
    """Factory for scan format parsers (OCP)."""

    _parsers = {
        "sarif": SARIFParser,
        "cyclonedx": CycloneDXParser,
    }

    @classmethod
    def get_parser(cls, format: str) -> IScanParser:
        """Get parser for specified format."""
        parser_class = cls._parsers.get(format.lower())

        if not parser_class:
            raise ValueError(f"Unsupported format: {format}")

        return parser_class()

    @classmethod
    def register_parser(cls, format: str, parser_class: type):
        """Register custom parser (extensibility)."""
        cls._parsers[format.lower()] = parser_class
```

**Adding New Parser**:

```python
# Step 1: Implement parser
class OSVParser(BaseScanParser):
    """Parser for OSV (Open Source Vulnerabilities) format."""

    def parse(self, payload: Dict[str, Any]) -> ParsedScanData:
        """Parse OSV payload."""
        # Implementation...
        pass

    def _extract_findings(self, payload: Dict) -> List[ParsedFinding]:
        """Extract findings from OSV format."""
        # Implementation...
        pass

    def _extract_metadata(self, payload: Dict) -> Dict[str, Any]:
        """Extract metadata from OSV format."""
        # Implementation...
        pass

# Step 2: Register parser
ParserFactory.register_parser("osv", OSVParser)

# Step 3: Use parser (no changes to service!)
parser = ParserFactory.get_parser("osv")
parsed_data = parser.parse(payload)
```

**Anti-Pattern**:

```python
# ❌ WRONG: Manual parser selection in service
class ScanIngestionService:
    async def ingest_scan(self, customer_id: str, scan_request: ScanIngestRequest):
        # ❌ Hard-coded parser selection
        if scan_request.format == "sarif":
            parser = SARIFParser()
        elif scan_request.format == "cyclonedx":
            parser = CycloneDXParser()
        elif scan_request.format == "osv":
            parser = OSVParser()
        else:
            raise ValueError("Unsupported format")

        # Every new parser requires modifying this code!
```

**Rules**:

1. NEVER instantiate parsers directly (`SARIFParser()`)
2. ALWAYS use factory (`ParserFactory.get_parser()`)
3. Register new parsers in `factory.py` or at runtime
4. All parsers MUST extend `BaseScanParser` and implement `IScanParser`

---

### Pattern 4: Multi-Tenant Database Pattern

**What**: All customer data uses customer-specific databases.

**Why**: Data isolation, security, compliance (GDPR, SOC2).

**Implementation**:

```python
# ✅ CORRECT: Use database abstraction
from api.core.database import get_customer_db, get_reference_db

# Customer-specific data (scans, findings)
customer_db = get_customer_db(customer_id)
finding_repo = ScanFindingRepository(customer_db)

# Reference data (CVEs, CWE, ATT&CK)
reference_db = get_reference_db()
vuln_repo = VulnerabilityRepository(reference_db)
```

**Database Routing Rules**:

| Data Type | Database | Example Collections |
|-----------|----------|---------------------|
| Reference data (shared, read-only) | `get_reference_db()` | `vulnerabilities`, `cwe`, `attack_techniques`, `oscal_controls` |
| Customer data (isolated) | `get_customer_db(customer_id)` | `scan_sessions`, `scan_findings`, `customer_components` |

**Anti-Pattern**:

```python
# ❌ WRONG: Direct database connection
from arango import ArangoClient

client = ArangoClient(hosts="http://localhost:8529")
db = client.db("complira_reference", username="root", password="password")

# ❌ Hard-coded database name
findings = db.collection("scan_findings").all()

# ❌ Mixing customer data in reference database
db.collection("scan_findings").insert({
    "customer_id": customer_id,  # ❌ Customer data in shared DB!
    "cve_id": "CVE-2021-44228",
})
```

**Rules**:

1. NEVER instantiate `ArangoClient` outside `api/core/database.py`
2. NEVER hard-code database names
3. Customer data MUST use `get_customer_db(customer_id)`
4. Reference data MUST use `get_reference_db()`
5. Cross-database queries are allowed (finding → CVE edge)

**Cross-Database Edge Example**:

```python
# ✅ CORRECT: Edge from customer DB to reference DB
customer_db = get_customer_db(customer_id)
edge_collection = customer_db.collection("finding_to_cve")

edge = {
    "_from": "scan_findings/finding_123",          # Customer DB
    "_to": "vulnerabilities/cve_2021_44228",       # Reference DB
    "created_at": datetime.now(timezone.utc),
}

edge_collection.insert(edge)
```

---

## Enforcement Mechanisms

### A. Pre-Commit Hooks

Create `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: check-direct-db-access
        name: Check for direct database access
        entry: python scripts/check_direct_db_access.py
        language: python
        types: [python]

      - id: check-import-patterns
        name: Validate import patterns
        entry: python scripts/check_import_patterns.py
        language: python
        types: [python]

      - id: check-repository-usage
        name: Ensure repositories are used
        entry: python scripts/check_repository_usage.py
        language: python
        files: ^src/api/(services|v1/endpoints)/.*\.py$
```

**Script: `scripts/check_direct_db_access.py`**

```python
#!/usr/bin/env python3
"""Check for direct database access bypassing repositories."""

import sys
import re
from pathlib import Path

# Patterns that indicate direct DB access
VIOLATION_PATTERNS = [
    r'db\.collection\(',           # Direct collection access
    r'ArangoClient\(',             # Direct client instantiation
    r'client\.db\(',               # Direct database connection
]

# Allowed files (infrastructure only)
ALLOWED_FILES = [
    'src/api/core/database.py',
    'src/api/repositories/base.py',
]

def check_file(filepath):
    """Check file for direct database access."""

    # Skip allowed files
    if any(allowed in str(filepath) for allowed in ALLOWED_FILES):
        return []

    violations = []

    with open(filepath, 'r') as f:
        for line_num, line in enumerate(f, 1):
            for pattern in VIOLATION_PATTERNS:
                if re.search(pattern, line):
                    violations.append({
                        'file': str(filepath),
                        'line': line_num,
                        'content': line.strip(),
                        'pattern': pattern,
                    })

    return violations

def main():
    """Check all Python files."""
    violations = []

    for filepath in Path('src').rglob('*.py'):
        violations.extend(check_file(filepath))

    if violations:
        print("❌ Direct database access detected:")
        for v in violations:
            print(f"\n  {v['file']}:{v['line']}")
            print(f"  Pattern: {v['pattern']}")
            print(f"  Code: {v['content']}")

        print("\n💡 Use repositories instead:")
        print("  ✅ finding_repo = ScanFindingRepository(customer_db)")
        print("  ✅ findings = finding_repo.list(...)")

        sys.exit(1)

    print("✅ No direct database access violations")
    sys.exit(0)

if __name__ == '__main__':
    main()
```

**Script: `scripts/check_import_patterns.py`**

```python
#!/usr/bin/env python3
"""Validate import patterns - ensure proper separation of concerns."""

import sys
import re
from pathlib import Path

# Import restrictions
RESTRICTIONS = {
    # Endpoints should NOT import repositories directly
    'src/api/v1/endpoints/': [
        (r'from api\.repositories import', 'Endpoints should use services, not repositories'),
        (r'from arango import', 'Endpoints should not access database directly'),
    ],

    # Services should NOT import endpoints
    'src/api/services/': [
        (r'from api\.v1\.endpoints import', 'Services should not import endpoints'),
        (r'from fastapi import.*APIRouter', 'Services should not define routes'),
    ],

    # Parsers should NOT import services/repositories
    'src/api/parsers/': [
        (r'from api\.services import', 'Parsers should not import services'),
        (r'from api\.repositories import', 'Parsers should not import repositories'),
    ],
}

def check_file(filepath):
    """Check file for import violations."""
    violations = []

    # Find applicable restrictions
    applicable_restrictions = []
    for path_prefix, restrictions in RESTRICTIONS.items():
        if path_prefix in str(filepath):
            applicable_restrictions = restrictions
            break

    if not applicable_restrictions:
        return []

    with open(filepath, 'r') as f:
        for line_num, line in enumerate(f, 1):
            for pattern, message in applicable_restrictions:
                if re.search(pattern, line):
                    violations.append({
                        'file': str(filepath),
                        'line': line_num,
                        'content': line.strip(),
                        'message': message,
                    })

    return violations

def main():
    """Check all Python files."""
    violations = []

    for filepath in Path('src/api').rglob('*.py'):
        violations.extend(check_file(filepath))

    if violations:
        print("❌ Import pattern violations detected:")
        for v in violations:
            print(f"\n  {v['file']}:{v['line']}")
            print(f"  {v['message']}")
            print(f"  Code: {v['content']}")

        sys.exit(1)

    print("✅ No import pattern violations")
    sys.exit(0)

if __name__ == '__main__':
    main()
```

### B. Code Review Checklist

Copy this checklist to your PR template:

```markdown
## Architectural Review Checklist

### General
- [ ] Code is in the correct directory (parsers/repositories/services/endpoints)
- [ ] No duplicate logic (DRY principle)
- [ ] Follows existing patterns (no ad-hoc implementations)

### Repository Pattern
- [ ] All database access uses repositories
- [ ] No `db.collection()` calls in services/endpoints
- [ ] Repository extends `BaseRepository`
- [ ] Repository methods are tested

### Service Layer
- [ ] Business logic is in services, not endpoints
- [ ] Service extends `BaseGraphService` (if graph operations)
- [ ] Service receives dependencies via constructor
- [ ] Service methods are unit tested

### Multi-Tenant Database
- [ ] Customer data uses `get_customer_db(customer_id)`
- [ ] Reference data uses `get_reference_db()`
- [ ] No hard-coded database names
- [ ] No mixing customer data in reference DB

### Parser Pattern
- [ ] New parsers registered in `ParserFactory`
- [ ] Parser extends `BaseScanParser`
- [ ] Parser returns `ParsedScanData`
- [ ] No direct parser instantiation in services

### Testing
- [ ] Unit tests for new repositories
- [ ] Unit tests for new services
- [ ] Integration tests for new endpoints
- [ ] Tests use mocks (no real database)

### Documentation
- [ ] Docstrings for public methods
- [ ] README updated (if new feature)
- [ ] API docs updated (if new endpoint)
```

### C. Architecture Tests

Create `tests/architecture/test_patterns.py`:

```python
"""
Architecture tests - validate patterns are followed.

These tests fail if code violates architectural patterns.
"""

import pytest
from pathlib import Path
import ast
import re


class TestRepositoryPattern:
    """Test repository pattern compliance."""

    def test_endpoints_do_not_import_repositories(self):
        """Endpoints should use services, not repositories."""
        violations = []

        for filepath in Path('src/api/v1/endpoints').rglob('*.py'):
            with open(filepath) as f:
                content = f.read()
                if 'from api.repositories import' in content:
                    violations.append(str(filepath))

        assert not violations, f"Endpoints importing repositories: {violations}"

    def test_no_direct_db_collection_calls_in_services(self):
        """Services should use repositories, not db.collection()."""
        violations = []

        for filepath in Path('src/api/services').rglob('*.py'):
            with open(filepath) as f:
                for line_num, line in enumerate(f, 1):
                    if re.search(r'db\.collection\(', line):
                        violations.append(f"{filepath}:{line_num}")

        assert not violations, f"Direct db.collection() calls: {violations}"


class TestServiceLayerPattern:
    """Test service layer pattern compliance."""

    def test_endpoints_instantiate_services(self):
        """Endpoints should instantiate and use services."""
        violations = []

        for filepath in Path('src/api/v1/endpoints').rglob('*.py'):
            if filepath.name == '__init__.py':
                continue

            with open(filepath) as f:
                content = f.read()

                # Check if file defines routes but doesn't use services
                if '@router.' in content and 'Service(' not in content:
                    violations.append(str(filepath))

        assert not violations, f"Endpoints not using services: {violations}"


class TestParserFactoryPattern:
    """Test parser factory pattern compliance."""

    def test_no_direct_parser_instantiation_in_services(self):
        """Services should use ParserFactory, not direct instantiation."""
        violations = []

        for filepath in Path('src/api/services').rglob('*.py'):
            with open(filepath) as f:
                content = f.read()

                # Check for direct parser instantiation
                if re.search(r'(SARIF|CycloneDX|OSV)Parser\(\)', content):
                    violations.append(str(filepath))

        assert not violations, f"Direct parser instantiation: {violations}"


class TestMultiTenantPattern:
    """Test multi-tenant database pattern compliance."""

    def test_no_direct_arango_client_outside_core(self):
        """Only core/database.py should instantiate ArangoClient."""
        violations = []

        for filepath in Path('src/api').rglob('*.py'):
            # Skip allowed file
            if 'core/database.py' in str(filepath):
                continue

            with open(filepath) as f:
                content = f.read()
                if 'ArangoClient(' in content:
                    violations.append(str(filepath))

        assert not violations, f"Direct ArangoClient usage: {violations}"

    def test_customer_db_usage_in_endpoints(self):
        """Endpoints handling customer data should use get_customer_db()."""
        violations = []

        for filepath in Path('src/api/v1/endpoints').rglob('*.py'):
            if filepath.name == '__init__.py':
                continue

            with open(filepath) as f:
                content = f.read()

                # If endpoint uses repository but doesn't get customer_db
                if 'Repository(' in content and 'get_customer_db' not in content:
                    violations.append(str(filepath))

        # This is a warning, not a hard failure (some endpoints use only reference DB)
        if violations:
            print(f"⚠️  Endpoints not using get_customer_db: {violations}")
```

**Run Architecture Tests**:

```bash
# Run on every commit
pytest tests/architecture/ -v

# Expected output:
# tests/architecture/test_patterns.py::TestRepositoryPattern::test_endpoints_do_not_import_repositories PASSED
# tests/architecture/test_patterns.py::TestServiceLayerPattern::test_endpoints_instantiate_services PASSED
# tests/architecture/test_patterns.py::TestParserFactoryPattern::test_no_direct_parser_instantiation_in_services PASSED
```

### D. Linting Rules

Add to `pyproject.toml`:

```toml
[tool.ruff]
# Enable additional rules
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "N",   # pep8-naming
    "UP",  # pyupgrade
    "B",   # flake8-bugbear
    "SIM", # flake8-simplify
]

[tool.ruff.per-file-ignores]
# Allow certain imports only in specific files
"src/api/core/database.py" = ["E402"]  # Allow late imports
"src/api/v1/endpoints/*.py" = ["B008"]  # Allow function calls in defaults (FastAPI Depends)

[tool.pylint.master]
# Custom checks
load-plugins = "scripts.pylint_custom_rules"

[tool.pylint.messages_control]
# Enforce patterns
enable = [
    "direct-db-access",        # Custom: detect db.collection() outside repositories
    "missing-repository-usage", # Custom: detect services not using repositories
]
```

**Custom Pylint Plugin**: `scripts/pylint_custom_rules.py`

```python
"""Custom pylint rules for architectural patterns."""

from pylint.checkers import BaseChecker
from pylint.interfaces import IAstroidChecker


class DirectDatabaseAccessChecker(BaseChecker):
    """Check for direct database access bypassing repositories."""

    __implements__ = IAstroidChecker

    name = 'direct-db-access'
    priority = -1
    msgs = {
        'W9001': (
            'Direct database access detected: %s',
            'direct-db-access',
            'Use repositories instead of db.collection()',
        ),
    }

    def visit_call(self, node):
        """Check function calls for db.collection()."""
        if hasattr(node.func, 'attrname') and node.func.attrname == 'collection':
            # Check if this is a db.collection() call
            if hasattr(node.func.expr, 'name') and node.func.expr.name == 'db':
                # Skip if in allowed files
                if 'repositories/' not in node.root().file:
                    self.add_message('direct-db-access', node=node, args=('db.collection()',))


def register(linter):
    """Register custom checkers."""
    linter.register_checker(DirectDatabaseAccessChecker(linter))
```

---

## Common Tasks

### Task 1: Add a New SBOM Parser

**Scenario**: Support new SBOM format (e.g., SPDX).

**Steps**:

1. **Create parser file**: `src/api/parsers/spdx.py`

```python
from api.parsers.base import BaseScanParser, ParsedScanData, ParsedFinding
from typing import Dict, Any, List

class SPDXParser(BaseScanParser):
    """Parser for SPDX (Software Package Data Exchange) format."""

    def parse(self, payload: Dict[str, Any]) -> ParsedScanData:
        """Parse SPDX payload."""
        if not self.validate(payload):
            raise ValueError(f"Invalid SPDX payload: {self.errors}")

        return ParsedScanData(
            tool_name="spdx",
            tool_version=payload.get("spdxVersion", "unknown"),
            scan_timestamp=payload.get("creationInfo", {}).get("created", ""),
            findings=self._extract_findings(payload),
            components=self._extract_components(payload),
            metadata=self._extract_metadata(payload),
        )

    def _extract_findings(self, payload: Dict) -> List[ParsedFinding]:
        """Extract vulnerabilities from SPDX packages."""
        findings = []

        for package in payload.get("packages", []):
            for external_ref in package.get("externalRefs", []):
                if external_ref.get("referenceCategory") == "SECURITY":
                    cve_id = external_ref.get("referenceLocator", "")

                    findings.append(ParsedFinding(
                        cve_id=cve_id,
                        severity="UNKNOWN",  # SPDX doesn't include severity
                        description=f"Vulnerability in {package.get('name')}",
                        location=f"{package.get('name')}@{package.get('versionInfo')}",
                        tool_name="spdx",
                        scan_type="spdx",
                        raw_data=package,
                    ))

        return findings

    def _extract_components(self, payload: Dict) -> List[Dict]:
        """Extract components from SPDX packages."""
        components = []

        for package in payload.get("packages", []):
            components.append({
                "name": package.get("name"),
                "version": package.get("versionInfo"),
                "purl": self._build_purl(package),
                "license": package.get("licenseConcluded"),
                "supplier": package.get("supplier"),
            })

        return components

    def _extract_metadata(self, payload: Dict) -> Dict[str, Any]:
        """Extract metadata from SPDX document."""
        return {
            "spdx_version": payload.get("spdxVersion"),
            "document_name": payload.get("name"),
            "document_namespace": payload.get("documentNamespace"),
            "creation_info": payload.get("creationInfo", {}),
        }

    def _build_purl(self, package: Dict) -> str:
        """Build Package URL from SPDX package."""
        # Find package URL in external refs
        for ref in package.get("externalRefs", []):
            if ref.get("referenceType") == "purl":
                return ref.get("referenceLocator", "")

        # Fallback: construct basic purl
        name = package.get("name", "unknown")
        version = package.get("versionInfo", "")
        return f"pkg:generic/{name}@{version}"
```

2. **Register parser**: Add to `src/api/parsers/factory.py`

```python
from api.parsers.spdx import SPDXParser

class ParserFactory:
    _parsers = {
        "sarif": SARIFParser,
        "cyclonedx": CycloneDXParser,
        "spdx": SPDXParser,  # ← Add new parser
    }
```

3. **Add tests**: `tests/unit/parsers/test_spdx_parser.py`

```python
import pytest
from api.parsers.spdx import SPDXParser

def test_spdx_parser_valid_payload():
    """Test SPDX parser with valid payload."""
    parser = SPDXParser()

    payload = {
        "spdxVersion": "SPDX-2.3",
        "name": "test-sbom",
        "creationInfo": {"created": "2024-01-01T00:00:00Z"},
        "packages": [
            {
                "name": "lodash",
                "versionInfo": "4.17.21",
                "externalRefs": [
                    {
                        "referenceCategory": "SECURITY",
                        "referenceType": "cve",
                        "referenceLocator": "CVE-2021-23337",
                    }
                ],
            }
        ],
    }

    result = parser.parse(payload)

    assert result.tool_name == "spdx"
    assert len(result.findings) == 1
    assert result.findings[0].cve_id == "CVE-2021-23337"
    assert len(result.components) == 1
    assert result.components[0]["name"] == "lodash"
```

4. **Update docs**: Document new format in API docs

```markdown
## Supported Scan Formats

- **SARIF** 2.1.0 (SAST/DAST tools)
- **CycloneDX** 1.4/1.5 (SBOM/SCA tools)
- **SPDX** 2.3 (SBOM format) ← NEW
```

5. **Test end-to-end**:

```bash
# Upload SPDX SBOM
curl -X POST https://api.complira.dev/v1/scan/ingest \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "format": "spdx",
    "scan_type": "sbom",
    "payload": {...}
  }'
```

**Result**: New parser added with ZERO changes to `ScanIngestionService` (OCP)!

---

### Task 2: Add a New API Endpoint

**Scenario**: Add endpoint to export scan findings as CSV.

**Steps**:

1. **Create service method**: `src/api/services/scan.py`

```python
class ScanIngestionService(BaseGraphService):
    # ... existing methods ...

    async def export_findings_csv(
        self,
        customer_id: str,
        scan_session_id: str,
    ) -> str:
        """
        Export scan findings as CSV.

        Args:
            customer_id: Customer identifier
            scan_session_id: Scan session ID

        Returns:
            str: CSV content
        """
        customer_db = get_customer_db(customer_id)
        finding_repo = ScanFindingRepository(customer_db)

        # Get findings
        findings = finding_repo.list_session_findings(
            customer_id=customer_id,
            scan_session_id=scan_session_id,
            limit=10000,  # Max export limit
        )

        # Build CSV
        import csv
        from io import StringIO

        output = StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=["cve_id", "severity", "description", "location", "created_at"]
        )

        writer.writeheader()
        for finding in findings:
            writer.writerow({
                "cve_id": finding.get("cve_id", ""),
                "severity": finding.get("severity", ""),
                "description": finding.get("description", ""),
                "location": finding.get("location", ""),
                "created_at": finding.get("created_at", ""),
            })

        return output.getvalue()
```

2. **Create endpoint**: `src/api/v1/endpoints/scan.py`

```python
from fastapi.responses import Response

@router.get("/{session_id}/export/csv")
async def export_findings_csv_endpoint(
    session_id: str,
    customer: Customer = Depends(get_current_customer),
):
    """
    GET /v1/scan/{session_id}/export/csv

    Export scan findings as CSV file.

    Returns:
    - CSV file with findings (Content-Type: text/csv)
    """
    try:
        # Instantiate service
        service = ScanIngestionService(
            db=get_reference_db(),
            cache=RedisCacheService(),
        )

        # Export CSV
        csv_content = await service.export_findings_csv(
            customer_id=customer.id,
            scan_session_id=session_id,
        )

        # Return CSV response
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=findings_{session_id}.csv"
            },
        )

    except Exception as e:
        logger.error(
            "Failed to export findings",
            session_id=session_id,
            customer_id=customer.id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Export failed")
```

3. **Add tests**: `tests/integration/test_scan_endpoints.py`

```python
def test_export_findings_csv(client, auth_headers):
    """Test CSV export endpoint."""
    # Create test scan
    response = client.post(
        "/v1/scan/ingest",
        headers=auth_headers,
        json={
            "format": "sarif",
            "scan_type": "sast",
            "payload": {...},
        }
    )

    session_id = response.json()["data"]["scan_session_id"]

    # Export CSV
    response = client.get(
        f"/v1/scan/{session_id}/export/csv",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv"
    assert "cve_id,severity,description" in response.text
```

4. **Update API docs**: FastAPI auto-generates OpenAPI docs

**Result**: New endpoint with proper separation of concerns (service logic → endpoint wrapper).

---

### Task 3: Add a New Database Collection

**Scenario**: Add `scan_exceptions` collection to track suppressed findings.

**Steps**:

1. **Define collection**: `src/complira_graph/db.py`

```python
# Add to DOCUMENT_COLLECTIONS
DOCUMENT_COLLECTIONS = [
    # ... existing collections ...
    "scan_exceptions",  # ← NEW: Suppressed findings
]

# Add to INDEXES
INDEXES = {
    # ... existing indexes ...
    "scan_exceptions": [
        {"fields": ["customer_id"], "unique": False},
        {"fields": ["customer_id", "cve_id"], "unique": True},  # One exception per CVE
    ],
}
```

2. **Create domain model**: `src/api/models/domain/scan.py`

```python
class ScanException(BaseModel):
    """
    Scan exception model.

    Represents a suppressed/ignored finding.
    """
    _key: str
    customer_id: str
    cve_id: str
    reason: str  # "false_positive" | "accepted_risk" | "mitigated"
    justification: str
    created_by: str  # User who created exception
    created_at: datetime
    expires_at: Optional[datetime] = None  # Auto-reinstate after expiry
```

3. **Create repository**: `src/api/repositories/scan_exception.py`

```python
from api.repositories.base import BaseRepository
from api.models.domain.scan import ScanException
from typing import List, Optional
from datetime import datetime, timezone

class ScanExceptionRepository(BaseRepository):
    """Repository for scan_exceptions collection."""

    def __init__(self, db):
        super().__init__(db, "scan_exceptions")

    def create_exception(
        self,
        customer_id: str,
        cve_id: str,
        reason: str,
        justification: str,
        created_by: str,
        expires_at: Optional[datetime] = None,
    ) -> ScanException:
        """Create new scan exception."""
        exception_dict = {
            "customer_id": customer_id,
            "cve_id": cve_id,
            "reason": reason,
            "justification": justification,
            "created_by": created_by,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": expires_at.isoformat() if expires_at else None,
        }

        result = self.create(exception_dict)
        return ScanException(**result)

    def list_active_exceptions(
        self,
        customer_id: str,
    ) -> List[ScanException]:
        """List active (non-expired) exceptions."""
        query = """
        FOR doc IN scan_exceptions
            FILTER doc.customer_id == @customer_id
            FILTER doc.expires_at == null OR doc.expires_at > @now
            RETURN doc
        """

        cursor = self.db.aql_execute(
            query,
            bind_vars={
                "customer_id": customer_id,
                "now": datetime.now(timezone.utc).isoformat(),
            }
        )

        return [ScanException(**doc) for doc in cursor]
```

4. **Update database initialization**: `src/api/core/database.py`

```python
def _create_customer_collections(db: StandardDatabase) -> None:
    """Create customer-specific collections."""
    customer_collections = {
        "scan_sessions": False,
        "scan_findings": False,
        "customer_components": False,
        "scan_exceptions": False,  # ← NEW
        "finding_to_cve": True,
        "component_to_finding": True,
    }

    # ... rest of initialization ...
```

5. **Create migration script**: `scripts/migrate_add_scan_exceptions.py`

```python
"""Migration: Add scan_exceptions collection to existing customer databases."""

from api.core.database import get_arango_client, get_cloud_settings
import structlog

logger = structlog.get_logger()

def migrate():
    """Add scan_exceptions collection to all customer databases."""
    settings = get_cloud_settings()
    client = get_arango_client()

    sys_db = client.db("_system", username=settings.ARANGO_USERNAME, password=settings.ARANGO_PASSWORD)

    # Get all customer databases
    db_names = [db for db in sys_db.databases() if db.startswith(settings.ARANGO_CUSTOMER_DATABASE_PREFIX)]

    for db_name in db_names:
        logger.info("Migrating database", database=db_name)

        customer_db = client.db(db_name, username=settings.ARANGO_USERNAME, password=settings.ARANGO_PASSWORD)

        # Create collection
        if not customer_db.has_collection("scan_exceptions"):
            customer_db.create_collection("scan_exceptions", edge=False)
            logger.info("Created collection", database=db_name, collection="scan_exceptions")

        # Create indexes
        collection = customer_db.collection("scan_exceptions")
        collection.add_persistent_index(fields=["customer_id"], unique=False)
        collection.add_persistent_index(fields=["customer_id", "cve_id"], unique=True)

        logger.info("Migration complete", database=db_name)

if __name__ == "__main__":
    migrate()
```

6. **Run migration**:

```bash
python scripts/migrate_add_scan_exceptions.py
```

**Result**: New collection added with proper schema, repository, and migration.

---

## Anti-Patterns

### Anti-Pattern 1: Direct Database Access in Endpoints

**Problem**: Bypasses repository layer, violates SRP.

```python
# ❌ WRONG
@router.get("/scans")
async def list_scans(customer: Customer = Depends(get_current_customer)):
    # Direct database access
    customer_db = get_customer_db(customer.id)
    scans = customer_db.collection("scan_sessions").all()

    return {"scans": list(scans)}
```

**Solution**: Use service → repository pattern.

```python
# ✅ CORRECT
@router.get("/scans")
async def list_scans(customer: Customer = Depends(get_current_customer)):
    # Delegate to service
    service = ScanIngestionService(db=get_reference_db(), cache=RedisCacheService())
    scans = await service.list_customer_scans(customer_id=customer.id)

    return APIResponse(success=True, data=scans)

# In service
class ScanIngestionService:
    async def list_customer_scans(self, customer_id: str):
        customer_db = get_customer_db(customer_id)
        session_repo = ScanSessionRepository(customer_db)
        return session_repo.list_customer_sessions(customer_id)
```

---

### Anti-Pattern 2: Business Logic in Endpoints

**Problem**: Makes endpoints fat, logic not reusable, hard to test.

```python
# ❌ WRONG
@router.post("/ingest")
async def ingest_scan(request: ScanIngestRequest, customer: Customer = Depends(get_current_customer)):
    # Parsing logic
    if request.format == "sarif":
        findings = extract_sarif_findings(request.payload)
    elif request.format == "cyclonedx":
        findings = extract_cyclonedx_findings(request.payload)

    # Database logic
    customer_db = get_customer_db(customer.id)
    for finding in findings:
        customer_db.collection("scan_findings").insert(finding)

    # Business logic
    critical_findings = [f for f in findings if f["severity"] == "CRITICAL"]
    if critical_findings:
        send_alert_email(customer.email, critical_findings)

    return {"status": "success"}
```

**Solution**: Move ALL logic to service.

```python
# ✅ CORRECT
@router.post("/ingest")
async def ingest_scan(request: ScanIngestRequest, customer: Customer = Depends(get_current_customer)):
    service = ScanIngestionService(db=get_reference_db(), cache=RedisCacheService())
    result = await service.ingest_scan(customer_id=customer.id, scan_request=request)
    return APIResponse(success=True, data=result)

# In service
class ScanIngestionService:
    async def ingest_scan(self, customer_id: str, scan_request: ScanIngestRequest):
        # Parsing (via factory)
        parser = ParserFactory.get_parser(scan_request.format)
        parsed_data = parser.parse(scan_request.payload)

        # Storage (via repository)
        customer_db = get_customer_db(customer_id)
        finding_repo = ScanFindingRepository(customer_db)
        findings = await self._store_findings(finding_repo, parsed_data.findings)

        # Alerting (separate service)
        if self._has_critical_findings(findings):
            alert_service = AlertService()
            await alert_service.send_critical_findings_alert(customer_id, findings)

        return {"findings_count": len(findings)}
```

---

### Anti-Pattern 3: Copy-Paste Code Duplication

**Problem**: Violates DRY, creates maintenance burden.

```python
# ❌ WRONG: Duplicated graph traversal in multiple services
class BlastRadiusService:
    def get_blast_radius(self, cve_id: str):
        query = """
        FOR v, e, p IN 1..4 OUTBOUND @start_doc
            has_weakness, capec_relates_to_cwe, capec_maps_to_attack
            OPTIONS {uniqueVertices: "global", bfs: true}
            RETURN {vertex: v, edge: e}
        """
        # ... execute query ...

class DefenseCoverageService:
    def get_defense_coverage(self, cve_id: str):
        query = """
        FOR v, e, p IN 1..4 OUTBOUND @start_doc
            has_weakness, technique_exploits_weakness, mitigates
            OPTIONS {uniqueVertices: "global", bfs: true}
            RETURN {vertex: v, edge: e}
        """
        # ... execute query ... (same logic!)
```

**Solution**: Extract to base class (DRY).

```python
# ✅ CORRECT: Shared traversal in BaseGraphService
class BaseGraphService:
    def traverse(self, start_collection: str, start_key: str, edge_definitions: List[str], max_depth: int = 4):
        """Generic graph traversal (DRY)."""
        query = f"""
        FOR v, e, p IN 1..@max_depth OUTBOUND @start_doc {', '.join(edge_definitions)}
            OPTIONS {{uniqueVertices: "global", bfs: true}}
            RETURN {{vertex: v, edge: e}}
        """
        return self.db.aql_execute(query, bind_vars={"start_doc": f"{start_collection}/{start_key}", "max_depth": max_depth})

# Services use base class method
class BlastRadiusService(BaseGraphService):
    def get_blast_radius(self, cve_id: str):
        return self.traverse(
            start_collection="vulnerabilities",
            start_key=cve_id,
            edge_definitions=["has_weakness", "capec_relates_to_cwe", "capec_maps_to_attack"],
        )

class DefenseCoverageService(BaseGraphService):
    def get_defense_coverage(self, cve_id: str):
        return self.traverse(
            start_collection="vulnerabilities",
            start_key=cve_id,
            edge_definitions=["has_weakness", "technique_exploits_weakness", "mitigates"],
        )
```

---

### Anti-Pattern 4: Hard-Coded Database Names

**Problem**: Breaks multi-tenancy, security risk.

```python
# ❌ WRONG
from arango import ArangoClient

client = ArangoClient(hosts="http://localhost:8529")
db = client.db("complira_customer_acme", username="root", password="password")

findings = db.collection("scan_findings").all()
```

**Solution**: Use database abstraction.

```python
# ✅ CORRECT
from api.core.database import get_customer_db

customer_db = get_customer_db(customer_id="acme")
finding_repo = ScanFindingRepository(customer_db)
findings = finding_repo.list(...)
```

---

### Anti-Pattern 5: Manual Parser Selection

**Problem**: Violates OCP, requires modifying existing code for new parsers.

```python
# ❌ WRONG
def parse_scan(format: str, payload: dict):
    if format == "sarif":
        parser = SARIFParser()
    elif format == "cyclonedx":
        parser = CycloneDXParser()
    elif format == "osv":
        parser = OSVParser()
    # Every new parser requires modifying this function!

    return parser.parse(payload)
```

**Solution**: Use factory pattern.

```python
# ✅ CORRECT
from api.parsers.factory import ParserFactory

def parse_scan(format: str, payload: dict):
    parser = ParserFactory.get_parser(format)
    return parser.parse(payload)

# Adding new parser: just register it
ParserFactory.register_parser("osv", OSVParser)
# No changes to parse_scan() function!
```

---

## Onboarding Checklist

### For New Developers

Welcome! Before you start contributing, complete this checklist:

- [ ] **Read this guide** - Understand the 5 core principles
- [ ] **Review code organization** - Know where code lives
- [ ] **Study the 4 required patterns**:
  - [ ] Repository pattern (database access)
  - [ ] Service layer pattern (business logic)
  - [ ] Parser factory pattern (format parsing)
  - [ ] Multi-tenant database pattern (data isolation)
- [ ] **Set up pre-commit hooks**:
  ```bash
  pip install pre-commit
  pre-commit install
  ```
- [ ] **Run architecture tests**:
  ```bash
  pytest tests/architecture/ -v
  ```
- [ ] **Review existing code examples**:
  - [ ] Read `src/api/parsers/cyclonedx.py` (parser example)
  - [ ] Read `src/api/repositories/scan.py` (repository example)
  - [ ] Read `src/api/services/scan.py` (service example)
  - [ ] Read `src/api/v1/endpoints/scan.py` (endpoint example)
- [ ] **Know where to find documentation**:
  - [ ] This guide (`docs/ARCHITECTURAL_GOVERNANCE.md`)
  - [ ] Contributing guide (`CONTRIBUTING.md`)
  - [ ] API docs (`docs/API.md`)
- [ ] **Understand code review process**:
  - [ ] Use PR template with architectural checklist
  - [ ] Address reviewer feedback on patterns
  - [ ] Ensure tests pass before requesting review

### For Code Reviewers

When reviewing PRs, check:

- [ ] **Directory placement**: Is code in the correct directory?
- [ ] **Pattern compliance**: Does code follow established patterns?
- [ ] **DRY principle**: Is there any code duplication?
- [ ] **Abstraction usage**: Are abstractions (protocols) used correctly?
- [ ] **Multi-tenancy**: Is customer data properly isolated?
- [ ] **Testing**: Are there unit/integration tests?
- [ ] **Documentation**: Are docstrings present for public methods?

---

## Summary

### The Golden Rules

1. **Repository Pattern**: All database access MUST go through repositories
2. **Service Layer**: All business logic MUST be in services
3. **Parser Factory**: All parsers MUST be registered in factory
4. **Multi-Tenant Database**: Customer data MUST use `get_customer_db(customer_id)`
5. **DRY Principle**: Shared logic MUST be in base classes

### Quick Reference

| I need to... | I should... |
|--------------|-------------|
| Access database | Use repository (`ScanFindingRepository`) |
| Add business logic | Add method to service (`ScanIngestionService`) |
| Create endpoint | Create thin wrapper in `v1/endpoints/` that calls service |
| Parse new format | Create parser extending `BaseScanParser`, register in factory |
| Add new collection | Define in `db.py`, create repository, write migration |
| Store customer data | Use `get_customer_db(customer_id)` |
| Access reference data | Use `get_reference_db()` |

### Common Violations

| ❌ DON'T | ✅ DO |
|---------|-------|
| `db.collection("scan_findings").all()` | `finding_repo.list(...)` |
| Business logic in endpoint | Business logic in service |
| `SARIFParser()` in service | `ParserFactory.get_parser("sarif")` |
| Hard-coded database name | `get_customer_db(customer_id)` |
| Copy-paste traversal code | Extend `BaseGraphService` |

---

## Questions?

- **Architecture questions**: Review this guide or ask in #architecture Slack channel
- **Pattern questions**: Check existing code examples in `src/api/`
- **Implementation questions**: Pair with senior developer

**Remember**: Consistency is key. When in doubt, follow existing patterns!
