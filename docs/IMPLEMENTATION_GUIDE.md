# Implementation Guide

> Step-by-step guide for implementing the architectural governance system

## Overview

This guide walks you through setting up and using the architectural governance tools to ensure consistency in your codebase.

## Quick Setup (5 minutes)

### 1. Run Setup Script

```bash
# From project root
./scripts/setup_governance.sh
```

This script will:
- Install pre-commit hooks
- Run initial checks
- Install test dependencies
- Run architecture tests

### 2. Verify Setup

```bash
# Test pre-commit hooks
git add .
git commit -m "Test commit"

# You should see:
# ✅ Check for direct database access........Passed
# ✅ Validate import patterns...............Passed
# ✅ Ensure repositories are used...........Passed
```

### 3. Run Tests

```bash
# Run all tests
pytest tests/ -v

# Run only architecture tests
pytest tests/architecture/ -v

# Expected output:
# tests/architecture/test_patterns.py::TestRepositoryPattern::test_endpoints_do_not_import_repositories PASSED
# tests/architecture/test_patterns.py::TestServiceLayerPattern::test_endpoints_instantiate_services PASSED
# ...
```

## Using the Governance Tools

### Pre-Commit Hooks (Automatic)

Pre-commit hooks run **automatically** when you commit:

```bash
git add src/api/services/my_service.py
git commit -m "Add new service"

# Hooks run automatically:
# - Check for direct database access
# - Validate import patterns
# - Check repository usage
# - Format code (black, ruff)
# - Type check (mypy)
```

**Bypassing hooks** (not recommended):
```bash
git commit --no-verify
```

### Manual Checks (Optional)

Run checks manually during development:

```bash
# Check for direct database access
python scripts/check_direct_db_access.py

# Check import patterns
python scripts/check_import_patterns.py

# Check repository usage
python scripts/check_repository_usage.py
```

### Architecture Tests (CI/CD)

Add to your CI/CD pipeline:

```yaml
# .github/workflows/test.yml
- name: Run architecture tests
  run: pytest tests/architecture/ -v --strict-markers
```

## Development Workflow

### Step 1: Create Feature Branch

```bash
git checkout -b feature/add-osv-parser
```

### Step 2: Make Changes Following Patterns

**Example: Add new parser**

```python
# src/api/parsers/osv.py
from api.parsers.base import BaseScanParser, ParsedScanData, ParsedFinding

class OSVParser(BaseScanParser):
    def parse(self, payload: Dict[str, Any]) -> ParsedScanData:
        # Implementation...
        pass
```

```python
# src/api/parsers/factory.py
from api.parsers.osv import OSVParser

class ParserFactory:
    _parsers = {
        "sarif": SARIFParser,
        "cyclonedx": CycloneDXParser,
        "osv": OSVParser,  # Register new parser
    }
```

### Step 3: Run Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test
pytest tests/unit/parsers/test_osv_parser.py -v

# Check coverage
pytest tests/ --cov=src/api --cov-report=html
```

### Step 4: Run Architecture Tests

```bash
pytest tests/architecture/ -v
```

### Step 5: Commit (Hooks Run Automatically)

```bash
git add .
git commit -m "Add OSV parser support"

# Pre-commit hooks run:
# ✅ Check for direct database access........Passed
# ✅ Validate import patterns...............Passed
# ✅ Ensure repositories are used...........Passed
# ✅ Format code............................Passed
```

### Step 6: Push and Create PR

```bash
git push origin feature/add-osv-parser
```

Use the PR template which includes architectural checklist.

### Step 7: Address Review Feedback

Reviewers will check:
- ✅ Code in correct directory
- ✅ Follows established patterns
- ✅ No code duplication
- ✅ Tests added
- ✅ Docstrings present

## Common Scenarios

### Scenario 1: Adding a New Service

```python
# 1. Create service file
# src/api/services/reporting_service.py
#
# v2.2 update: scan evidence now lives in the reference DB (scan_runs, scan_findings).
# Use EvidenceRunRepository / EvidenceFindingRepository from complira_graph.ingestion.
# The old ScanSessionRepository (api/repositories/scan.py) is deprecated.

from api.services.base import BaseGraphService
from complira_graph.ingestion.repositories import EvidenceRunRepository, EvidenceFindingRepository

class ReportingService(BaseGraphService):
    """Generate reports from scan data."""

    async def generate_report(self, tenant_id: str, scan_run_id: str):
        # Reference DB holds scan_runs and scan_findings in v2.2
        ref_db = get_reference_db()

        # Query scan run
        run = ref_db.collection("scan_runs").get(scan_run_id)

        # Query findings for this run
        cursor = ref_db.aql.execute(
            "FOR f IN scan_findings FILTER f.scan_run_id == @run_id AND f.tenant_id == @tid RETURN f",
            bind_vars={"run_id": scan_run_id, "tid": tenant_id},
        )
        findings = list(cursor)

        # Business logic...
        return report
```

```python
# 2. Add tests
# tests/unit/services/test_reporting_service.py

def test_reporting_service_generate_report(mock_db, mock_cache):
    service = ReportingService(db=mock_db, cache=mock_cache)
    report = await service.generate_report("customer1", "scan123")
    assert report is not None
```

```python
# 3. Use in endpoint
# src/api/v1/endpoints/reports.py

@router.get("/{session_id}/report")
async def generate_report(session_id: str, customer: Customer = Depends(get_current_customer)):
    service = ReportingService(db=get_reference_db(), cache=RedisCacheService())
    report = await service.generate_report(customer.id, session_id)
    return APIResponse(success=True, data=report)
```

### Scenario 2: Fixing a Violation

**Problem**: Architecture test fails

```bash
$ pytest tests/architecture/ -v

FAILED tests/architecture/test_patterns.py::TestRepositoryPattern::test_no_direct_db_collection_calls_in_services
Direct db.collection() calls in services: ['src/api/services/scan.py:145']
```

**Solution**: Refactor to use repository

```python
# ❌ Before (violation)
class ScanService:
    async def get_findings(self, customer_id: str):
        customer_db = get_customer_db(customer_id)
        findings = customer_db.collection("scan_findings").all()  # Direct access!
        return list(findings)

# ✅ After (fixed)
class ScanService:
    async def get_findings(self, customer_id: str):
        customer_db = get_customer_db(customer_id)
        finding_repo = ScanFindingRepository(customer_db)  # Use repository
        findings = finding_repo.list(customer_id=customer_id)
        return findings
```

### Scenario 3: Pre-Commit Hook Fails

**Problem**: Hook detects violation

```bash
$ git commit -m "Add feature"

Check for direct database access........Failed
- hook id: check-direct-db-access
- exit code: 1

❌ Direct database access detected:
  src/api/v1/endpoints/scan.py:42
  Pattern: db.collection(
  Code: findings = db.collection("scan_findings").all()
```

**Solution**: Fix violation and re-commit

```python
# Fix the code
findings = finding_repo.list(customer_id=customer_id)

# Re-commit
git add src/api/v1/endpoints/scan.py
git commit -m "Add feature"
# ✅ Hooks pass
```

## CI/CD Integration

### GitHub Actions Example

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -e .
          pip install pytest pytest-cov pre-commit

      - name: Run pre-commit checks
        run: pre-commit run --all-files

      - name: Run architecture tests
        run: pytest tests/architecture/ -v --strict-markers

      - name: Run unit tests
        run: pytest tests/unit/ -v --cov=src/api --cov-report=xml

      - name: Run integration tests
        run: pytest tests/integration/ -v

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

### GitLab CI Example

```yaml
# .gitlab-ci.yml
stages:
  - test
  - lint

test:
  stage: test
  image: python:3.11
  script:
    - pip install -e .
    - pip install pytest pytest-cov
    - pytest tests/architecture/ -v
    - pytest tests/ -v --cov=src/api
  coverage: '/TOTAL.*\s+(\d+%)$/'

lint:
  stage: lint
  image: python:3.11
  script:
    - pip install pre-commit
    - pre-commit run --all-files
```

## Troubleshooting

### Problem: Pre-commit hooks not running

**Solution**:
```bash
# Reinstall hooks
pre-commit uninstall
pre-commit install

# Verify
pre-commit run --all-files
```

### Problem: Architecture tests failing

**Solution**:
```bash
# Run with verbose output
pytest tests/architecture/ -vv

# Run specific test
pytest tests/architecture/test_patterns.py::TestRepositoryPattern -v

# Fix violations based on output
```

### Problem: False positives in checks

**Solution**: Update allowed files in scripts

```python
# scripts/check_direct_db_access.py
ALLOWED_FILES = [
    'src/api/core/database.py',
    'src/api/repositories/base.py',
    'src/api/my_special_case.py',  # Add exception
]
```

### Problem: Import errors in tests

**Solution**: Install package in development mode

```bash
pip install -e .
```

## Customization

### Adding Custom Architecture Tests

```python
# tests/architecture/test_custom.py
def test_custom_pattern():
    """Custom architecture test."""
    violations = []

    for filepath in Path('src/api/services').rglob('*.py'):
        # Custom check logic
        pass

    assert not violations, f"Violations: {violations}"
```

### Adding Custom Pre-Commit Hook

```yaml
# .pre-commit-config.yaml
- repo: local
  hooks:
    - id: check-custom-pattern
      name: Check custom pattern
      entry: python scripts/check_custom.py
      language: python
      types: [python]
```

### Customizing Enforcement Level

**Strict mode** (fail on any violation):
```yaml
# .pre-commit-config.yaml
- id: check-repository-usage
  entry: python scripts/check_repository_usage.py --strict
```

**Relaxed mode** (warnings only):
```yaml
# .pre-commit-config.yaml
- id: check-repository-usage
  entry: python scripts/check_repository_usage.py --warn
```

## Best Practices

### 1. Run Checks Frequently

```bash
# Before committing
pytest tests/architecture/ -v
python scripts/check_direct_db_access.py

# During development
pytest tests/unit/ -v -k "my_feature"
```

### 2. Fix Violations Immediately

Don't accumulate technical debt. Fix violations as soon as they're detected.

### 3. Update Documentation

When adding new patterns, update:
- `docs/ARCHITECTURAL_GOVERNANCE.md`
- `docs/QUICK_REFERENCE.md`
- `CONTRIBUTING.md`

### 4. Review Regularly

Hold monthly architecture reviews to:
- Review new patterns
- Identify recurring violations
- Update enforcement tools

### 5. Educate Team

- Onboard new developers with governance guide
- Pair programming sessions to demonstrate patterns
- Code review discussions focused on architecture

## Metrics & Monitoring

### Track Compliance

```bash
# Count violations over time
git log --oneline --grep="fix.*violation" | wc -l

# Architecture test pass rate
pytest tests/architecture/ --quiet | grep "passed"
```

### Pre-Commit Hook Statistics

```bash
# View hook runs
git log --oneline --grep="pre-commit"

# Most common failures
grep "Failed" .git/hooks/pre-commit.log | sort | uniq -c
```

## Resources

- **[Architectural Governance Guide](ARCHITECTURAL_GOVERNANCE.md)** - Complete reference
- **[Quick Reference](QUICK_REFERENCE.md)** - Cheat sheet
- **[Contributing Guide](../CONTRIBUTING.md)** - Quick start

## Questions?

- Architecture questions: Review documentation or ask in #architecture
- Tool issues: Create GitHub issue
- Pattern clarifications: Pair with senior developer

---

**Remember**: The tools are here to help, not hinder. They catch mistakes early and keep the codebase consistent.
