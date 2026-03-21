# Architectural Governance - Complete Index

> Your complete guide to maintaining architectural consistency in the codebase

## Start Here

**New to the project?** Follow this path:

1. Read **[CONTRIBUTING.md](CONTRIBUTING.md)** (10 minutes) - Essential patterns
2. Skim **[Quick Reference](docs/QUICK_REFERENCE.md)** (5 minutes) - Cheat sheet
3. Setup tools: `./scripts/setup_governance.sh` (5 minutes)
4. Review code examples in `src/api/` (20 minutes)

**Need details?** Read **[Architectural Governance Guide](docs/ARCHITECTURAL_GOVERNANCE.md)** (1 hour)

---

## Complete File Listing

### Documentation (6 files)

| File | Purpose | Read Time |
|------|---------|-----------|
| **[CONTRIBUTING.md](CONTRIBUTING.md)** | Quick start guide | 10 min |
| **[docs/ARCHITECTURAL_GOVERNANCE.md](docs/ARCHITECTURAL_GOVERNANCE.md)** | Complete governance guide | 1 hour |
| **[docs/QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md)** | One-page cheat sheet | 5 min |
| **[docs/IMPLEMENTATION_GUIDE.md](docs/IMPLEMENTATION_GUIDE.md)** | Setup and usage guide | 20 min |
| **[docs/GOVERNANCE_SUMMARY.md](docs/GOVERNANCE_SUMMARY.md)** | Executive summary | 10 min |
| **[docs/README.md](docs/README.md)** | Documentation index | 5 min |

### Enforcement Scripts (4 files)

| File | Purpose | Runs |
|------|---------|------|
| **[scripts/check_direct_db_access.py](scripts/check_direct_db_access.py)** | Detect database access violations | Pre-commit + Manual |
| **[scripts/check_import_patterns.py](scripts/check_import_patterns.py)** | Validate separation of concerns | Pre-commit + Manual |
| **[scripts/check_repository_usage.py](scripts/check_repository_usage.py)** | Check repository pattern compliance | Pre-commit + Manual |
| **[scripts/setup_governance.sh](scripts/setup_governance.sh)** | One-command setup | Manual |

### Testing (1 file)

| File | Purpose | Runs |
|------|---------|------|
| **[tests/architecture/test_patterns.py](tests/architecture/test_patterns.py)** | Architecture tests (pytest) | CI/CD + Manual |

### Configuration (2 files)

| File | Purpose |
|------|---------|
| **[.pre-commit-config.yaml](.pre-commit-config.yaml)** | Pre-commit hook configuration |
| **[.github/pull_request_template.md](.github/pull_request_template.md)** | PR review checklist |

---

## The 5 Core Patterns (Quick Reference)

### 1. Repository Pattern
```python
# ✅ DO: Use repositories for database access
customer_db = get_customer_db(customer_id)
finding_repo = ScanFindingRepository(customer_db)
findings = finding_repo.list(...)

# ❌ DON'T: Direct database access
db.collection("scan_findings").all()
```

### 2. Service Layer Pattern
```python
# ✅ DO: Business logic in services
@router.post("/ingest")
async def ingest_scan(...):
    service = ScanIngestionService(...)
    return await service.ingest_scan(...)

# ❌ DON'T: Business logic in endpoints
@router.post("/ingest")
async def ingest_scan(...):
    # Complex parsing logic here...
```

### 3. Parser Factory Pattern
```python
# ✅ DO: Use factory
parser = ParserFactory.get_parser("sarif")

# ❌ DON'T: Direct instantiation
parser = SARIFParser()
```

### 4. Multi-Tenant Database Pattern
```python
# ✅ DO: Use database abstraction
customer_db = get_customer_db(customer_id)
reference_db = get_reference_db()

# ❌ DON'T: Hard-code database names
client.db("complira_customer_acme")
```

### 5. DRY Principle
```python
# ✅ DO: Use base class methods
class MyService(BaseGraphService):
    def get_data(self):
        return self.traverse(...)

# ❌ DON'T: Copy-paste code
query = """FOR v, e IN..."""  # Duplicated!
```

---

## Quick Commands

### Setup
```bash
# One-command setup (installs hooks, runs checks)
./scripts/setup_governance.sh

# Install pre-commit hooks only
pre-commit install

# Verify setup
pre-commit run --all-files
```

### Testing
```bash
# Run all tests
pytest tests/ -v

# Run architecture tests (enforce patterns)
pytest tests/architecture/ -v

# Run with coverage
pytest tests/ --cov=src/api --cov-report=html
```

### Manual Checks
```bash
# Check for direct database access
python scripts/check_direct_db_access.py

# Check import patterns
python scripts/check_import_patterns.py

# Check repository usage
python scripts/check_repository_usage.py
```

### Development Workflow
```bash
# Make changes
vim src/api/services/my_service.py

# Run tests
pytest tests/ -v

# Commit (pre-commit hooks run automatically)
git add .
git commit -m "Add feature"

# Architecture tests pass? Push!
git push
```

---

## Documentation by Audience

### For New Developers

**Essential Reading** (30 minutes):
1. [CONTRIBUTING.md](CONTRIBUTING.md) - The 5 golden rules
2. [Quick Reference](docs/QUICK_REFERENCE.md) - Cheat sheet
3. Run setup: `./scripts/setup_governance.sh`

**Deep Dive** (2 hours):
1. [Architectural Governance Guide](docs/ARCHITECTURAL_GOVERNANCE.md) - Complete reference
2. Review code examples: `src/api/parsers/`, `src/api/repositories/`, etc.
3. [Implementation Guide](docs/IMPLEMENTATION_GUIDE.md) - Detailed usage

### For Code Reviewers

**Use These**:
1. [PR Template](.github/pull_request_template.md) - Review checklist
2. [Quick Reference](docs/QUICK_REFERENCE.md) - Pattern validation
3. [Anti-Patterns](docs/ARCHITECTURAL_GOVERNANCE.md#anti-patterns) - Red flags

**Questions to Ask**:
- Is code in the correct directory?
- Does it follow established patterns?
- Is there code duplication?
- Are tests included?

### For Team Leads

**Management**:
1. [Governance Summary](docs/GOVERNANCE_SUMMARY.md) - Executive overview
2. [Implementation Guide](docs/IMPLEMENTATION_GUIDE.md) - Setup and CI/CD
3. [Architecture Tests](tests/architecture/test_patterns.py) - Enforcement

**Metrics**:
- Architecture test pass rate
- Pre-commit hook compliance
- Code review violations
- Time to onboard new developers

### For Architects

**Deep Technical**:
1. [Architectural Governance Guide](docs/ARCHITECTURAL_GOVERNANCE.md) - Complete patterns
2. [Architecture Tests](tests/architecture/test_patterns.py) - Validation rules
3. [Enforcement Scripts](scripts/) - Custom checks

**Customization**:
- Add new patterns to governance guide
- Add new tests to `test_patterns.py`
- Add new checks to `scripts/`

---

## Common Tasks

### I want to add a new parser
1. Read: [Task 1: Add a New SBOM Parser](docs/ARCHITECTURAL_GOVERNANCE.md#task-1-add-a-new-sbom-parser)
2. Create: `src/api/parsers/my_parser.py` extending `BaseScanParser`
3. Register: `ParserFactory._parsers["myformat"] = MyParser`
4. Test: `tests/unit/parsers/test_my_parser.py`

### I want to add a new endpoint
1. Read: [Task 2: Add a New API Endpoint](docs/ARCHITECTURAL_GOVERNANCE.md#task-2-add-a-new-api-endpoint)
2. Create service: `src/api/services/my_service.py`
3. Create endpoint: `src/api/v1/endpoints/my_endpoint.py` (thin wrapper)
4. Test: `tests/integration/test_my_endpoint.py`

### I want to add a new collection
1. Read: [Task 3: Add a New Database Collection](docs/ARCHITECTURAL_GOVERNANCE.md#task-3-add-a-new-database-collection)
2. Define: `src/complira_graph/db.py` (add to DOCUMENT_COLLECTIONS)
3. Create repository: `src/api/repositories/my_repo.py`
4. Migrate: `scripts/migrate_add_my_collection.py`

### I got a pre-commit violation
1. Read error message
2. Fix code following pattern in [Quick Reference](docs/QUICK_REFERENCE.md)
3. Re-commit
4. If stuck: Check [Troubleshooting](docs/IMPLEMENTATION_GUIDE.md#troubleshooting)

### I need to understand a pattern
1. Check [Quick Reference](docs/QUICK_REFERENCE.md) for examples
2. Read pattern section in [Governance Guide](docs/ARCHITECTURAL_GOVERNANCE.md#required-patterns)
3. Review existing code: `src/api/parsers/`, `src/api/repositories/`, etc.
4. Ask in #architecture Slack channel

---

## Directory Structure

```
project-root/
├── CONTRIBUTING.md                   # Quick start guide (essential)
├── GOVERNANCE_INDEX.md              # This file (navigation)
│
├── docs/                            # Documentation
│   ├── README.md                    # Documentation index
│   ├── ARCHITECTURAL_GOVERNANCE.md  # Complete guide (main reference)
│   ├── QUICK_REFERENCE.md           # One-page cheat sheet
│   ├── IMPLEMENTATION_GUIDE.md      # Setup and usage
│   └── GOVERNANCE_SUMMARY.md        # Executive summary
│
├── scripts/                         # Enforcement scripts
│   ├── check_direct_db_access.py   # Detect database violations
│   ├── check_import_patterns.py    # Validate separation of concerns
│   ├── check_repository_usage.py   # Check repository pattern
│   └── setup_governance.sh         # One-command setup
│
├── tests/architecture/              # Architecture tests
│   └── test_patterns.py            # Pattern validation (pytest)
│
├── .github/                         # GitHub templates
│   └── pull_request_template.md    # PR review checklist
│
└── .pre-commit-config.yaml         # Pre-commit configuration
```

---

## Success Metrics

### Enforcement Coverage
- ✅ **5 automated checks** (pre-commit hooks)
- ✅ **8 architecture test classes** (pytest)
- ✅ **3 manual check scripts** (development)
- ✅ **1 PR review checklist** (code review)

### Documentation Coverage
- ✅ **70+ pages** across 6 documents
- ✅ **50+ code examples** (good vs bad)
- ✅ **3 common task guides** (step-by-step)
- ✅ **7 anti-patterns documented** (what to avoid)

### Developer Experience
- ✅ **< 5 minutes** setup time (one command)
- ✅ **< 1 second** violation detection (pre-commit)
- ✅ **< 30 minutes** to understand patterns (docs)
- ✅ **< 1 hour** to master all patterns (with examples)

---

## Getting Help

### Documentation
- **Quick answers**: [Quick Reference](docs/QUICK_REFERENCE.md)
- **Complete details**: [Architectural Governance Guide](docs/ARCHITECTURAL_GOVERNANCE.md)
- **Setup issues**: [Implementation Guide](docs/IMPLEMENTATION_GUIDE.md)
- **Examples**: Code in `src/api/`

### Support Channels
- **Architecture questions**: #architecture Slack channel
- **Pattern questions**: Review existing code examples
- **Implementation questions**: Pair with senior developer
- **Tool issues**: Create GitHub issue

### Quick Links
- [SOLID Principles](https://en.wikipedia.org/wiki/SOLID)
- [Repository Pattern](https://martinfowler.com/eaaCatalog/repository.html)
- [Service Layer Pattern](https://martinfowler.com/eaaCatalog/serviceLayer.html)
- [Factory Pattern](https://refactoring.guru/design-patterns/factory-method)

---

## Maintenance

### Monthly Tasks
- [ ] Review new patterns added
- [ ] Identify recurring violations
- [ ] Update enforcement tools
- [ ] Update documentation
- [ ] Hold architecture review meeting

### Continuous Improvement
- Add new architecture tests for new patterns
- Enhance pre-commit hooks based on violations
- Update documentation based on feedback
- Share learnings with team

---

## Version History

- **v1.0** (2026-03-06): Initial governance system
  - 5 core patterns documented
  - 4 enforcement scripts created
  - 1 architecture test suite
  - 6 documentation files
  - Pre-commit hooks configured
  - PR template created

---

## Summary

This governance system ensures developers **always use existing infrastructure** through:

1. **Clear Documentation** - 70+ pages with examples
2. **Automated Enforcement** - Pre-commit hooks + architecture tests
3. **Code Review** - Checklist and guidelines
4. **Easy Setup** - One-command installation
5. **Developer Support** - Multiple documentation levels

**Result**: Consistent, maintainable codebase that scales without accumulating technical debt.

---

**Questions?** Start with [CONTRIBUTING.md](CONTRIBUTING.md) or ask in #architecture!
