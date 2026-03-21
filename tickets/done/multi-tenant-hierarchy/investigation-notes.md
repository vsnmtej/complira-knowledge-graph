# Investigation Notes
**Ticket**: `multi-tenant-hierarchy`
**Date**: 2026-03-12
**Last Updated**: 2026-03-12

## Investigation Sources

### Local File Paths
- `/src/api/v1/endpoints/account.py` - Reference for CRUD pattern
- `/src/api/v1/endpoints/scan.py` - Scan ingestion/listing endpoints to update
- `/src/api/v1/endpoints/vex.py` - Another CRUD example
- `/src/api/models/requests/account.py` - Request model pattern
- `/src/api/models/responses/account.py` - Response model pattern
- `/src/api/models/requests/scan.py` - Scan request models
- `/src/api/models/responses/scan.py` - Scan response models
- `/src/api/core/security.py` - Authentication dependency
- `/src/api/core/database.py` - Database access patterns
- `/src/api/core/config.py` - Settings/configuration
- `/src/api/v1/router.py` - Router registration
- `/docs/API_DOCUMENTATION.md` - API documentation structure
- `/docs/MULTI_TENANT_HIERARCHY.md` - Design document (created during bootstrap)

### Web Links
- None (internal codebase investigation only)

### Open-Source References
- FastAPI documentation patterns (already applied in codebase)
- Pydantic model validation patterns (already applied)
- ArangoDB document/collection patterns (already applied)

## Key Findings

### 1. Existing Architecture Patterns

**API Layer** (`src/api/v1/endpoints/`):
- **FastAPI routers** with `APIRouter()` instances
- **Dependency injection** via `Depends(get_current_customer)` for authentication
- **Pydantic request models** for input validation
- **Pydantic response models** wrapped in `APIResponse[T]` envelope
- **Structured logging** via `structlog.get_logger()`
- **Execution time tracking** for metadata
- **Error handling** with appropriate HTTP status codes (400, 401, 404, 500)

**Example Pattern (from `account.py:51-162`)**:
```python
@router.post("/api-keys", response_model=APIResponse[CreateAPIKeyResponse])
async def create_api_key(
    request: CreateAPIKeyRequest,
    customer: Customer = Depends(get_current_customer),
):
    import time
    start_time = time.time()

    try:
        db = get_database()
        # ... business logic ...

        execution_time_ms = (time.time() - start_time) * 1000

        return APIResponse(
            success=True,
            data=CreateAPIKeyResponse(...),
            metadata=ResponseMetadata(
                cache_hit=False,
                execution_time_ms=execution_time_ms,
            ),
        )
    except Exception as e:
        logger.error(...)
        raise HTTPException(status_code=500, detail="...")
```

**Data Models** (`src/api/models/`):
- **Request models**: `/requests/*.py` with Pydantic `BaseModel` + validation
- **Response models**: `/responses/*.py` with Pydantic `BaseModel` + examples
- **Naming convention**: `{Entity}{Action}Request/Response` (e.g., `CreateAPIKeyRequest`)
- **Field validation**: `Field(...)` with constraints, descriptions, examples

**Database Layer** (`src/api/core/database.py`):
- **Two-database architecture**:
  - `get_reference_db()` → Shared reference database (complira_reference)
  - `get_customer_db(customer_id)` → Customer-isolated database (customer_{id})
- **ArangoDB collections**: Document collections + Edge collections
- **Customer scoping**: All queries filtered by `customer_id`
- **Collection creation**: `db.has_collection()` + `db.create_collection()` pattern
- **Indexes**: Created via `collection.add_persistent_index(fields=[...])`

**Authentication** (`src/api/core/security.py:176-225`):
- **API key validation**: Bcrypt-hashed keys checked against database
- **Customer extraction**: Returns `CustomerProfile` object via dependency
- **Multi-key support**: Checks `customer_api_keys` collection + legacy `customer_profiles`
- **Scoping enforcement**: Customer ID embedded in dependency

### 2. Current Scan Session Model

**Scan Ingestion Flow** (`scan.py:32-106`):
1. Parse scan payload (SARIF, CycloneDX, etc.)
2. Create scan session document
3. Store findings and components
4. Create graph edges (finding → CVE, component → finding)

**Scan Session Fields** (inferred from `scan.py:88-99`):
```python
{
    "scan_session_id": "scan_abc123",
    "customer_id": "demo_customer",
    "scan_type": "sca",
    "format": "cyclonedx",
    "scan_timestamp": "2024-03-12T10:00:00Z",
    "findings_count": 42,
    "components_count": 150,
    "status": "completed",
    "metadata": {...}
}
```

**Missing Fields** (to add):
- `project_id` (nullable)
- `repository_id` (nullable)

### 3. Entrypoints and Execution Boundaries

**API Entrypoints**:
- `POST /v1/scan/ingest` - Scan ingestion (needs project_id/repository_id params)
- `GET /v1/scan/list` - List scans (needs filtering by project/repo)
- `GET /v1/scan/{session_id}` - Get scan session (no changes)
- `GET /v1/scan/{session_id}/findings` - Get findings (no changes)

**New Entrypoints** (to create):
- `POST /v1/projects` - Create project
- `GET /v1/projects` - List projects
- `GET /v1/projects/{project_id}` - Get project details
- `PUT /v1/projects/{project_id}` - Update project
- `DELETE /v1/projects/{project_id}` - Soft delete project
- `POST /v1/repositories` - Create repository
- `GET /v1/repositories` - List repositories (with optional project filter)
- `GET /v1/repositories/{repository_id}` - Get repository details
- `PUT /v1/repositories/{repository_id}` - Update repository
- `DELETE /v1/repositories/{repository_id}` - Soft delete repository
- `GET /v1/projects/{project_id}/summary` - Project-level aggregation
- `GET /v1/repositories/{repository_id}/summary` - Repository-level aggregation
- `GET /v1/summary` - Customer-level aggregation (enhanced)

**Execution Boundaries**:
- **API → Database**: Direct AQL queries (no service layer for simple CRUD)
- **API → Service → Database**: Complex operations (e.g., scan ingestion uses `ScanIngestionService`)
- **Customer Scoping**: Enforced at API layer via `get_current_customer` dependency

### 4. Touched Modules and Owning Concerns

**Files to Create** (new):
1. `src/api/v1/endpoints/projects.py` - Project management endpoints
2. `src/api/v1/endpoints/repositories.py` - Repository management endpoints
3. `src/api/models/requests/projects.py` - Project request models (**already created**)
4. `src/api/models/requests/repositories.py` - Repository request models
5. `src/api/models/responses/projects.py` - Project response models
6. `src/api/models/responses/repositories.py` - Repository response models
7. `scripts/test_multi_tenant_hierarchy.py` - E2E test script

**Files to Modify** (existing):
1. `src/api/v1/router.py` - Register new routers (projects, repositories)
2. `src/api/v1/endpoints/scan.py` - Add project_id/repository_id to ingest, add filtering to list
3. `src/api/models/requests/scan.py` - Add optional project_id/repository_id fields
4. `docs/API_DOCUMENTATION.md` - Add hierarchy endpoints and examples

**Database Collections** (customer database):
1. **projects** (new):
   - Fields: `_key`, `project_id`, `customer_id`, `name`, `description`, `tags`, `created_at`, `updated_at`, `repository_count`, `active`
   - Index: `customer_id`
2. **repositories** (new):
   - Fields: `_key`, `repository_id`, `customer_id`, `project_id` (nullable), `name`, `repository_url`, `default_branch`, `tags`, `created_at`, `updated_at`, `last_scan_at`, `scan_count`, `active`
   - Indexes: `customer_id`, `project_id`
3. **scan_sessions** (modify):
   - Add fields: `project_id` (nullable), `repository_id` (nullable)
   - Add indexes: `customer_id + project_id`, `customer_id + repository_id`

### 5. Current Naming Conventions

**File Naming**:
- Endpoints: `{entity}.py` (e.g., `account.py`, `scan.py`, `vex.py`)
- Request models: `{entity}.py` under `/requests/` (e.g., `account.py`, `scan.py`)
- Response models: `{entity}.py` under `/responses/` (e.g., `account.py`, `scan.py`)

**API Route Naming**:
- Collection resource: `GET /v1/{entities}` (e.g., `GET /v1/projects`)
- Single resource: `GET /v1/{entities}/{id}` (e.g., `GET /v1/projects/{project_id}`)
- Create: `POST /v1/{entities}`
- Update: `PUT /v1/{entities}/{id}`
- Delete: `DELETE /v1/{entities}/{id}`
- Sub-resource: `GET /v1/{entities}/{id}/{sub-resource}` (e.g., `GET /v1/projects/{id}/summary`)

**Model Naming**:
- Request: `{Action}{Entity}Request` (e.g., `CreateProjectRequest`, `UpdateProjectRequest`)
- Response: `{Entity}Response` or `{Action}{Entity}Response` (e.g., `ProjectResponse`, `ProjectSummaryResponse`)

**Database Naming**:
- Collection: Plural snake_case (e.g., `customer_api_keys`, `scan_sessions`, `projects`, `repositories`)
- Field: Snake_case with entity prefix for IDs (e.g., `project_id`, `repository_id`, `customer_id`)

### 6. Data Persistence and External IO

**Database**: ArangoDB (customer-isolated databases)
- **Customer DB**: `customer_{customer_id}` (e.g., `customer_demo_customer`)
- **Reference DB**: `complira_reference` (shared, read-only for CVE data)

**Cache**: Redis (for caching enriched CVE data)
- Not needed for project/repository CRUD (low churn, small dataset)

**External IO**: None for this feature (purely internal database operations)

### 7. Current Separation of Concerns

**Layer Structure** (backend/service):
- **API Layer** (`/api/v1/endpoints/`) - HTTP request handling, validation, error mapping
- **Model Layer** (`/api/models/`) - Data validation, serialization/deserialization
- **Core Layer** (`/api/core/`) - Authentication, database access, configuration, caching
- **Service Layer** (`/api/services/`) - Complex business logic (e.g., scan ingestion, enrichment)

**Responsibility Boundaries**:
- **Endpoints**: Accept requests, validate via Pydantic, call database/service, return APIResponse
- **Models**: Define data structures, validation rules, examples
- **Core**: Provide infrastructure (DB connections, auth, config)
- **Services**: Orchestrate multi-step operations (scan parsing, enrichment, aggregation)

**Design Decision for This Feature**:
- **Simple CRUD** (projects, repositories): Implement directly in endpoints (follow `account.py` pattern)
- **Aggregation** (summaries): Implement directly in endpoints with AQL queries (simple aggregation, no complex orchestration)
- **Scan filtering**: Modify existing endpoint with query parameters

### 8. Implications for Requirements and Design

**Backward Compatibility**:
- Existing scans without `project_id`/`repository_id` must continue to work
- Make fields nullable in scan session updates
- Filter queries must handle null values gracefully

**Performance**:
- Add database indexes for `customer_id`, `project_id`, `repository_id`
- Aggregation queries may be slow for customers with 100+ repositories
- **Mitigation**: Use cached counts (`repository_count`, `scan_count`) + indexes

**Data Integrity**:
- Prevent deletion of projects with repositories
- Prevent deletion of repositories with scans
- **Mitigation**: Check for dependent entities before soft delete

**Customer Scoping**:
- All queries must filter by `customer_id`
- Prevent cross-customer access to projects/repositories
- **Enforcement**: Use `customer.id` from authentication dependency in all queries

## Open Unknowns and Questions

### 1. **Should we create collections at API startup or via migration script?**
- **Current Pattern**: Collections created on-demand in endpoint (e.g., `account.py:120-121`)
- **Decision**: Follow existing pattern - create collections on first use with `if not db.has_collection()`
- **Risk**: None (ArangoDB create is idempotent)

### 2. **Should aggregation endpoints use cached counts or real-time queries?**
- **Tradeoff**: Cached counts (fast, stale) vs Real-time (slow, accurate)
- **Decision**: Use real-time AQL aggregation queries for v1 (accurate, acceptable <2s latency)
- **Future Enhancement**: Add Redis caching for summaries if performance degrades

### 3. **Should we support moving scans between repositories?**
- **User Story**: User uploads scan to wrong repository, wants to reassign
- **Decision**: Out of scope for v1 (scan metadata is immutable)
- **Rationale**: Scan metadata includes repository context; changing it breaks audit trail

### 4. **Should we validate repository_url format (Git URL)?**
- **Current Pattern**: No validation in `account.py` for similar fields
- **Decision**: No validation in v1 (accept any string, optional field)
- **Rationale**: Users may use non-Git URLs (Mercurial, SVN, internal systems)

### 5. **Should we auto-populate repository_count and scan_count?**
- **Tradeoff**: Cached counts (requires update logic) vs Computed counts (slower queries)
- **Decision**: Use cached counts with increment/decrement on create/delete
- **Rationale**: Consistent with existing patterns, better UX for list views

## Scope Triage

### Estimated Files Touched
- **New Files**: 7
  - 2 endpoint files (projects.py, repositories.py)
  - 4 model files (2 requests, 2 responses)
  - 1 test script
- **Modified Files**: 4
  - router.py (registration)
  - scan.py (add hierarchy params, filtering)
  - scan.py models (add optional fields)
  - API_DOCUMENTATION.md
- **Total**: 11 files

### New/Changed Public APIs
- **8 new CRUD endpoints** (4 per entity × 2 entities)
- **3 new aggregation endpoints** (customer, project, repository summaries)
- **2 modified endpoints** (scan ingest, scan list)
- **Total**: 13 endpoint changes

### Schema/Storage Changes
- **2 new collections** (projects, repositories)
- **3 new indexes** (projects: customer_id, repositories: customer_id + project_id, scan_sessions: customer_id + project_id/repository_id)
- **1 schema update** (scan_sessions: add project_id, repository_id)

### Multi-Layer Impact
- **API Layer**: New endpoints + modified endpoints
- **Model Layer**: New request/response models
- **Persistence Layer**: New collections + indexes

### Architectural Impact
- **No new patterns**: Following existing CRUD + aggregation patterns
- **No cross-cutting changes**: Isolated to project/repository management
- **Clear boundaries**: Customer scoping enforced via existing authentication

### Classification: **MEDIUM**

**Reasoning**:
- **Not Small** because:
  - 11 files touched (guideline: Small ≤ 3 files for non-cross-cutting changes)
  - Multiple new public APIs (13 endpoint changes)
  - Schema/storage changes (2 new collections)
  - Multi-layer impact (API + model + persistence)
- **Not Large** because:
  - No new architectural patterns (following existing CRUD patterns)
  - No cross-cutting behavior changes (isolated feature)
  - Clear bounded scope (project/repository management)
  - No complex orchestration (simple CRUD + aggregation)

**Workflow Depth** (per workflow skill):
- Medium → **Proposed Design Doc** → Future-State Runtime Call Stack → Runtime Call Stack Review (iterative deep rounds until `Go Confirmed`) → Implementation Plan → Implementation Progress → API/E2E Testing → Code Review → Docs Sync

## Constraints Discovered

1. **Backward Compatibility**: Must support existing scans without project/repository IDs
2. **Customer Scoping**: All entities strictly scoped to authenticated customer
3. **Soft Delete**: Deletion must preserve audit trail (active=false)
4. **ArangoDB**: Must use ArangoDB collections in customer databases (no cross-DB edges)
5. **Authentication**: All endpoints require X-API-Key header
6. **Performance**: Aggregation queries must complete in <2s

## Next Steps

1. **Stage 1 → Stage 2 Transition**: Refine requirements.md to Design-ready status
2. **Stage 2 → Stage 3 Transition**: Create proposed-design.md (required for Medium scope)
3. **Stage 3 → Stage 4 Transition**: Build future-state runtime call stacks
4. **Stage 4 → Stage 5 Transition**: Review runtime call stacks (iterative deep rounds)
5. **Stage 5 → Stage 6 Transition**: Only after review gate `Go Confirmed`

## Revision History

| Version | Date | Changes | Author |
| --- | --- | --- | --- |
| v1 | 2026-03-12 | Initial investigation and scope triage | Claude |
