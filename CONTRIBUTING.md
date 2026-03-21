# Contributing Guide

Thank you for contributing to Complira! This guide provides quick reference for maintaining architectural consistency.

## Quick Start

1. **Read the full governance guide**: [`docs/ARCHITECTURAL_GOVERNANCE.md`](/Users/venkatapydialli/Documents/cybersecurity-compliance-app/docs/ARCHITECTURAL_GOVERNANCE.md)
2. **Set up pre-commit hooks**: `pre-commit install`
3. **Run tests before committing**: `pytest tests/ -v`
4. **Follow the patterns below**

## The 5 Golden Rules

### 1. Repository Pattern
**All database access MUST go through repositories**

```python
# ✅ CORRECT
customer_db = get_customer_db(customer_id)
finding_repo = ScanFindingRepository(customer_db)
findings = finding_repo.list_session_findings(customer_id, scan_session_id)

# ❌ WRONG
customer_db = get_customer_db(customer_id)
findings = customer_db.collection("scan_findings").all()
```

### 2. Service Layer Pattern
**All business logic MUST be in services**

```python
# ✅ CORRECT - Endpoint delegates to service
@router.post("/ingest")
async def ingest_scan(request: ScanIngestRequest, customer: Customer = Depends(get_current_customer)):
    service = ScanIngestionService(db=get_reference_db(), cache=RedisCacheService())
    result = await service.ingest_scan(customer_id=customer.id, scan_request=request)
    return APIResponse(success=True, data=result)

# ❌ WRONG - Business logic in endpoint
@router.post("/ingest")
async def ingest_scan(request: ScanIngestRequest, customer: Customer = Depends(get_current_customer)):
    parser = SARIFParser()
    parsed_data = parser.parse(request.payload)
    customer_db = get_customer_db(customer.id)
    # ... complex logic here ...
```

### 3. Parser Factory Pattern
**All parsers MUST be registered in factory**

```python
# ✅ CORRECT
parser = ParserFactory.get_parser("sarif")
parsed_data = parser.parse(payload)

# ❌ WRONG
parser = SARIFParser()
parsed_data = parser.parse(payload)
```

### 4. Multi-Tenant Database Pattern
**Customer data MUST use customer-specific databases**

```python
# ✅ CORRECT
customer_db = get_customer_db(customer_id)        # Customer data
reference_db = get_reference_db()                  # Reference data

# ❌ WRONG
from arango import ArangoClient
client = ArangoClient(hosts="http://localhost:8529")
db = client.db("complira_customer_acme", ...)     # Hard-coded!
```

### 5. DRY Principle
**Shared logic MUST be in base classes**

```python
# ✅ CORRECT - Use base class method
class BlastRadiusService(BaseGraphService):
    def get_blast_radius(self, cve_id: str):
        return self.traverse(
            start_collection="vulnerabilities",
            start_key=cve_id,
            edge_definitions=["has_weakness", "capec_relates_to_cwe"],
        )

# ❌ WRONG - Duplicated traversal code
class BlastRadiusService:
    def get_blast_radius(self, cve_id: str):
        query = """FOR v, e IN 1..4 OUTBOUND..."""  # Copy-pasted!
        # ... same logic as 10 other services ...
```

## Code Organization

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

### What Goes Where

| Code Type | Location | Example |
|-----------|----------|---------|
| Database access | `api/repositories/` | `ScanFindingRepository` |
| Business logic | `api/services/` | `ScanIngestionService` |
| HTTP handling | `api/v1/endpoints/` | `@router.post("/ingest")` |
| External format parsing | `api/parsers/` | `SARIFParser`, `CycloneDXParser` |
| Request/response models | `api/models/` | `ScanIngestRequest` |
| Configuration | `api/core/config.py` | `get_cloud_settings()` |
| Database routing | `api/core/database.py` | `get_customer_db()` |

## Common Tasks

### Add a New Parser

1. Create parser: `src/api/parsers/my_parser.py`
   ```python
   class MyParser(BaseScanParser):
       def parse(self, payload: Dict) -> ParsedScanData:
           # Implementation...
   ```

2. Register in factory: `src/api/parsers/factory.py`
   ```python
   _parsers = {
       "sarif": SARIFParser,
       "cyclonedx": CycloneDXParser,
       "myformat": MyParser,  # Add here
   }
   ```

3. Add tests: `tests/unit/parsers/test_my_parser.py`

### Add a New Repository

1. Create repository: `src/api/repositories/my_repo.py`
   ```python
   class MyRepository(BaseRepository):
       def __init__(self, db):
           super().__init__(db, "my_collection")

       def custom_query(self, customer_id: str):
           # Implementation...
   ```

2. Add tests: `tests/unit/repositories/test_my_repo.py`

### Add a New Service

1. Create service: `src/api/services/my_service.py`
   ```python
   class MyService(BaseGraphService):
       def __init__(self, db, cache):
           super().__init__(db, cache)

       async def my_business_logic(self, customer_id: str):
           # Use repositories
           customer_db = get_customer_db(customer_id)
           my_repo = MyRepository(customer_db)
           # Implementation...
   ```

2. Add tests: `tests/unit/services/test_my_service.py`

### Add a New Endpoint

1. Create endpoint: `src/api/v1/endpoints/my_endpoint.py`
   ```python
   @router.post("/my-action")
   async def my_action_endpoint(
       request: MyRequest,
       customer: Customer = Depends(get_current_customer),
   ):
       # Instantiate service
       service = MyService(db=get_reference_db(), cache=RedisCacheService())

       # Delegate to service
       result = await service.my_business_logic(customer_id=customer.id)

       # Return response
       return APIResponse(success=True, data=result)
   ```

2. Register router: `src/api/v1/__init__.py`
   ```python
   from api.v1.endpoints import my_endpoint
   api_router.include_router(my_endpoint.router, prefix="/my", tags=["my"])
   ```

3. Add tests: `tests/integration/test_my_endpoint.py`

### Add a New Collection

1. Define collection: `src/complira_graph/db.py`
   ```python
   DOCUMENT_COLLECTIONS = [
       # ... existing ...
       "my_collection",
   ]

   INDEXES = {
       "my_collection": [
           {"fields": ["customer_id"], "unique": False},
       ],
   }
   ```

2. Create repository: `src/api/repositories/my_collection.py`

3. Update customer collections: `src/api/core/database.py` (if customer-specific)

4. Write migration: `scripts/migrate_add_my_collection.py`

## Testing Requirements

### Required Tests

- **Unit tests** for repositories (`tests/unit/repositories/`)
- **Unit tests** for services (`tests/unit/services/`)
- **Integration tests** for endpoints (`tests/integration/`)
- **Architecture tests** run automatically (`tests/architecture/`)

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/unit/parsers/test_sarif_parser.py -v

# Run with coverage
pytest tests/ --cov=src/api --cov-report=html

# Run architecture tests (enforce patterns)
pytest tests/architecture/ -v
```

## Pre-Commit Checks

Before committing, these checks run automatically:

1. **Direct database access check** - Ensures no `db.collection()` outside repositories
2. **Import pattern check** - Validates separation of concerns
3. **Code formatting** - Runs `ruff` and `black`
4. **Type checking** - Runs `mypy`

**To skip checks** (not recommended):
```bash
git commit --no-verify
```

## Code Review Checklist

When submitting a PR, ensure:

- [ ] Code is in the correct directory
- [ ] Follows established patterns (repository/service/parser/database)
- [ ] No code duplication (DRY principle)
- [ ] Uses abstractions (protocols) correctly
- [ ] Customer data properly isolated (multi-tenancy)
- [ ] Tests added for new code
- [ ] Docstrings added for public methods
- [ ] No `db.collection()` calls outside repositories
- [ ] No business logic in endpoints
- [ ] No direct parser instantiation (use factory)

## Common Violations

| ❌ DON'T | ✅ DO |
|---------|-------|
| `db.collection("scan_findings").all()` in service | `finding_repo.list(...)` |
| Business logic in endpoint | Business logic in service |
| `SARIFParser()` in service | `ParserFactory.get_parser("sarif")` |
| Hard-coded `"complira_customer_acme"` | `get_customer_db(customer_id)` |
| Copy-paste traversal code | Extend `BaseGraphService` |
| `from arango import ArangoClient` in service | Use `get_customer_db()` abstraction |
| Import repository in endpoint | Import and use service |

## Questions?

- **Full architectural guide**: [`docs/ARCHITECTURAL_GOVERNANCE.md`](/Users/venkatapydialli/Documents/cybersecurity-compliance-app/docs/ARCHITECTURAL_GOVERNANCE.md)
- **Pattern questions**: Check existing code examples in `src/api/`
- **Implementation questions**: Ask in #engineering Slack channel

## Development Workflow

1. **Create feature branch**: `git checkout -b feature/my-feature`
2. **Make changes** following patterns above
3. **Run tests**: `pytest tests/ -v`
4. **Run architecture tests**: `pytest tests/architecture/ -v`
5. **Commit** (pre-commit hooks run automatically)
6. **Push** and create PR
7. **Address review feedback**
8. **Merge** after approval

---

**Remember**: Consistency is more important than cleverness. Follow existing patterns!
