# Documentation

Welcome to the Complira documentation. This directory contains guides for maintaining architectural consistency and code quality.

## Essential Reading

### For All Developers

1. **[CONTRIBUTING.md](../CONTRIBUTING.md)** - Start here! Quick guide to contributing
2. **[Quick Reference](QUICK_REFERENCE.md)** - One-page cheat sheet for patterns
3. **[Architectural Governance](ARCHITECTURAL_GOVERNANCE.md)** - Complete architectural guide

### For New Team Members

Follow this onboarding path:

1. Read **CONTRIBUTING.md** (10 minutes)
2. Skim **Quick Reference** (5 minutes)
3. Deep-dive **Architectural Governance** (30 minutes)
4. Review code examples in `src/api/` (20 minutes)
5. Run setup: `./scripts/setup_governance.sh`

## Documentation Index

### Architecture & Patterns

- **[Architectural Governance Guide](ARCHITECTURAL_GOVERNANCE.md)** - Complete guide to maintaining consistency
  - Core principles (SRP, DIP, OCP, DRY)
  - Required patterns (Repository, Service, Parser, Multi-Tenant)
  - Enforcement mechanisms (pre-commit, tests, reviews)
  - Common tasks (adding parsers, endpoints, collections)
  - Anti-patterns to avoid
  - Onboarding checklist

- **[Quick Reference](QUICK_REFERENCE.md)** - One-page cheat sheet
  - The 5 golden rules
  - Quick decision tree
  - Code examples
  - Common violations

### Contributing

- **[Contributing Guide](../CONTRIBUTING.md)** - Quick start for contributors
  - The 5 golden rules with examples
  - Code organization
  - Common tasks
  - Testing requirements

- **[Pull Request Template](../.github/pull_request_template.md)** - PR checklist
  - Architectural review checklist
  - Testing requirements
  - Code quality checks

## Architecture at a Glance

### The 5 Core Principles

1. **Repository Pattern** - All database access through repositories
2. **Service Layer Pattern** - All business logic in services
3. **Parser Factory Pattern** - Use factory for scan format parsers
4. **Multi-Tenant Database** - Customer data isolation
5. **DRY Principle** - Shared logic in base classes

### Directory Structure

```
src/api/
├── core/              # Infrastructure (database, cache, security)
├── models/            # Pydantic models (requests, responses, domain)
├── parsers/           # Scan format parsers (SARIF, CycloneDX, etc.)
├── repositories/      # Database access layer (CRUD operations)
├── services/          # Business logic layer (orchestration)
└── v1/endpoints/      # HTTP endpoints (thin controllers)
```

### Enforcement Tools

- **Pre-commit hooks** - Automatic checks on every commit
- **Architecture tests** - Validate patterns are followed
- **Code review checklist** - Template for reviewing PRs
- **Custom linting rules** - Detect violations

## Quick Links

### Setup

```bash
# Install governance tools
./scripts/setup_governance.sh

# Run architecture tests
pytest tests/architecture/ -v

# Check for violations
python scripts/check_direct_db_access.py
python scripts/check_import_patterns.py
```

### Common Tasks

- [Add a new SBOM parser](ARCHITECTURAL_GOVERNANCE.md#task-1-add-a-new-sbom-parser)
- [Add a new API endpoint](ARCHITECTURAL_GOVERNANCE.md#task-2-add-a-new-api-endpoint)
- [Add a new database collection](ARCHITECTURAL_GOVERNANCE.md#task-3-add-a-new-database-collection)

### Code Examples

- **Parser Example**: `src/api/parsers/cyclonedx.py`
- **Repository Example**: `src/api/repositories/scan.py`
- **Service Example**: `src/api/services/scan.py`
- **Endpoint Example**: `src/api/v1/endpoints/scan.py`

## Other Documentation

### Implementation Guides

- **[DRY/SOLID Migration Guide](../DRY_SOLID_MIGRATION_GUIDE.md)** - How we refactored to SOLID principles
- **[Implementation Summary](../IMPLEMENTATION_SUMMARY.md)** - Technical implementation details
- **[Regulatory Compliance Schema](../REGULATORY_COMPLIANCE_SCHEMA_ANALYSIS.md)** - Database schema analysis

### API Documentation

(Coming soon)

- REST API reference
- Authentication guide
- Rate limiting
- Error handling

## Questions?

- **Architecture questions**: Review this documentation or ask in #architecture
- **Pattern questions**: Check code examples in `src/api/`
- **Implementation questions**: Pair with senior developer
- **Bug reports**: Create GitHub issue with template

## Contributing to Documentation

When updating documentation:

1. Keep it practical and example-driven
2. Update all references when changing patterns
3. Add code examples for new patterns
4. Test all code examples
5. Update the Quick Reference if needed

---

**Remember**: Documentation is code. Keep it up to date, accurate, and helpful.
