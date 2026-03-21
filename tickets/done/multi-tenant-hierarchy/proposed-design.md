# Proposed Design Document

## Design Version

- Current Version: `v1`

## Revision History

| Version | Trigger | Summary Of Changes | Related Review Round |
| --- | --- | --- | --- |
| v1 | Initial draft | Initial design for multi-tenant hierarchy feature | N/A (pre-review) |

## Artifact Basis

- Investigation Notes: `tickets/in-progress/multi-tenant-hierarchy/investigation-notes.md`
- Requirements: `tickets/in-progress/multi-tenant-hierarchy/requirements.md`
- Requirements Status: `Design-ready`

## Summary

Implement hierarchical multi-tenant architecture enabling customers to organize vulnerability scans into Projects (logical groups) and Repositories (individual codebases). Provide CRUD APIs for project/repository management, extend scan submission to accept hierarchy metadata, add filtering capabilities, and create aggregation endpoints for insights at each hierarchy level (customer, project, repository).

## Goals

1. Enable customers to organize scans hierarchically (Customer → Project → Repository → Scan)
2. Provide project and repository management APIs (CRUD operations)
3. Support optional hierarchy in scan submission (backward compatible)
4. Enable filtering scans by project and/or repository
5. Provide aggregated insights at project, repository, and customer levels
6. Maintain backward compatibility with existing scans (no breaking changes)
7. Enforce customer scoping (no cross-customer data access)

## Legacy Removal Policy (Mandatory)

- Policy: `No backward compatibility; remove legacy code paths.`
- **Exception for this feature**: This is an additive feature with optional hierarchy fields. Existing scans without project/repository IDs must continue to work.
- Required action: No legacy code removal in this scope (additive-only feature).

## Requirements And Use Cases

| Requirement ID | Description | Acceptance Criteria ID(s) | Acceptance Criteria Summary | Use Case IDs |
| --- | --- | --- | --- | --- |
| R-001 | Project data model | AC-001, AC-002, AC-003, AC-004 | Validation, scoping, uniqueness, soft delete | UC-001, UC-002, UC-003, UC-004, UC-005 |
| R-002 | Repository data model | AC-005, AC-006, AC-007, AC-008, AC-009 | Validation, scoping, uniqueness, nullable project, soft delete | UC-006, UC-007, UC-008, UC-009, UC-010 |
| R-003 | Scan session hierarchy | AC-010, AC-011, AC-012, AC-013 | Optional fields, backward compat, validation, scoping | UC-011, UC-012, UC-013, UC-014 |
| R-004 | Project management API | AC-014 to AC-020 | CRUD endpoints with auth and error handling | UC-001, UC-002, UC-003, UC-004, UC-005 |
| R-005 | Repository management API | AC-021 to AC-027 | CRUD endpoints with auth and error handling | UC-006, UC-007, UC-008, UC-009, UC-010 |
| R-006 | Scan filtering | AC-028 to AC-032 | Filter by project/repo with scoping | UC-012, UC-013, UC-014 |
| R-007 | Project-level aggregation | AC-033 to AC-037 | Aggregate findings across repositories in project | UC-015 |
| R-008 | Repository-level aggregation | AC-038 to AC-042 | Aggregate findings over time for repository | UC-016 |
| R-009 | Customer-level aggregation | AC-043 to AC-045 | Enhanced customer summary with hierarchy breakdown | UC-017 |
| R-010 | Database indexes | AC-046, AC-047 | Indexes for performance | UC-018 |

## Codebase Understanding Snapshot (Pre-Design Mandatory)

| Area | Findings | Evidence (files/functions) | Open Unknowns |
| --- | --- | --- | --- |
| Entrypoints / Boundaries | FastAPI routers with APIRouter(), authenticated via Depends(get_current_customer) | `src/api/v1/endpoints/account.py`, `src/api/v1/endpoints/scan.py`, `src/api/v1/endpoints/vex.py` | None - pattern is clear |
| Current Naming Conventions | Endpoints: `{entity}.py`, Models: `{Entity}{Action}Request/Response`, Collections: `{entities}` (plural snake_case) | `src/api/models/requests/account.py`, `src/api/models/responses/account.py` | None - consistent across codebase |
| Impacted Modules / Responsibilities | API endpoints (HTTP handling), Models (validation), Database (ArangoDB queries), Router (registration) | `src/api/v1/router.py`, `src/api/core/database.py` | None - clear separation of concerns |
| Data / Persistence / External IO | ArangoDB customer databases (`customer_{id}`), Collections created on-demand, Indexes via add_persistent_index() | `src/api/core/database.py:50-150`, `src/api/v1/endpoints/account.py:120-121` | None - pattern established |

## Current State (As-Is)

**Database Architecture**:
- Two-database system: Reference DB (shared CVE data) + Customer DBs (isolated scan data)
- Customer DB collections: `scan_sessions`, `findings`, `components`, `customer_api_keys`, `vex_documents`
- No hierarchy: Scans are flat at customer level

**API Endpoints**:
- Scan ingestion: `POST /v1/scan/ingest` (no project/repo params)
- Scan listing: `GET /v1/scan/list` (no filtering by project/repo)
- Account management: API key CRUD (established pattern to follow)

**Data Models**:
- Scan session: `{customer_id, scan_type, format, findings_count, ...}` (no project_id/repository_id)
- Pydantic validation for all requests/responses

**Authentication**:
- X-API-Key header via `get_current_customer` dependency
- Customer scoping enforced in all queries

## Target State (To-Be)

**Database Architecture** (enhanced):
- Add collections: `projects`, `repositories`
- Update collection: `scan_sessions` (add `project_id`, `repository_id` fields)
- Add indexes for query performance

**API Endpoints** (new + modified):
- **New**: Project CRUD (`/v1/projects`, `/v1/projects/{id}`)
- **New**: Repository CRUD (`/v1/repositories`, `/v1/repositories/{id}`)
- **New**: Aggregation (`/v1/projects/{id}/summary`, `/v1/repositories/{id}/summary`, `/v1/summary` enhanced)
- **Modified**: Scan ingestion accepts optional `project_id`, `repository_id`
- **Modified**: Scan listing supports filtering by `project_id`, `repository_id`

**Data Models** (new):
- `CreateProjectRequest`, `UpdateProjectRequest`, `ProjectResponse`, `ProjectSummaryResponse`
- `CreateRepositoryRequest`, `UpdateRepositoryRequest`, `RepositoryResponse`, `RepositorySummaryResponse`
- `ScanIngestRequest` updated with optional `project_id`, `repository_id`

**Hierarchy**:
- Customer → Projects → Repositories → Scans (optional, backward compatible)

## Architecture Direction Decision (Mandatory)

- **Chosen direction**: `Add` new collections and endpoints; `Modify` existing scan endpoints
- **Rationale**:
  - **Complexity**: Low - follows established CRUD patterns from `account.py`
  - **Testability**: High - clear API boundaries, easy to test in isolation
  - **Operability**: High - backward compatible, no data migration required
  - **Evolution cost**: Low - additive feature, no breaking changes
- **Layering fitness assessment**: Current layering (API → Core → Database) is coherent and appropriate
  - API layer handles HTTP, validation, auth
  - Core layer provides database access, authentication
  - No service layer needed for simple CRUD
- **Outcome**: `Add` (new endpoint files, new model files, new database collections)

## Change Inventory (Delta)

| Change ID | Change Type | Current Path | Target Path | Rationale | Impacted Areas | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| C-001 | Add | N/A | `src/api/v1/endpoints/projects.py` | New project management endpoints | API layer | Follow account.py pattern |
| C-002 | Add | N/A | `src/api/v1/endpoints/repositories.py` | New repository management endpoints | API layer | Follow account.py pattern |
| C-003 | Add | N/A | `src/api/models/requests/repositories.py` | Repository request models | Model layer | Already created projects.py |
| C-004 | Add | N/A | `src/api/models/responses/projects.py` | Project response models | Model layer | Pydantic models |
| C-005 | Add | N/A | `src/api/models/responses/repositories.py` | Repository response models | Model layer | Pydantic models |
| C-006 | Add | N/A | `scripts/test_multi_tenant_hierarchy.py` | E2E test script | Testing | Demonstrates multi-repo workflow |
| C-007 | Modify | `src/api/v1/router.py` | `src/api/v1/router.py` | Register new routers | API layer | Add 2 router registrations |
| C-008 | Modify | `src/api/v1/endpoints/scan.py` | `src/api/v1/endpoints/scan.py` | Add hierarchy params, filtering | API layer | Update ingest + list endpoints |
| C-009 | Modify | `src/api/models/requests/scan.py` | `src/api/models/requests/scan.py` | Add optional project_id, repository_id | Model layer | Backward compatible fields |
| C-010 | Modify | `docs/API_DOCUMENTATION.md` | `docs/API_DOCUMENTATION.md` | Document new endpoints | Documentation | Add hierarchy examples |
| C-011 | Add (data) | N/A | Database: `projects` collection | Store project entities | Database | Customer DB |
| C-012 | Add (data) | N/A | Database: `repositories` collection | Store repository entities | Database | Customer DB |
| C-013 | Modify (data) | Database: `scan_sessions` | Database: `scan_sessions` | Add project_id, repository_id fields | Database | Nullable fields |

**Total**: 7 new files, 4 modified files, 2 new collections, 1 schema update

## Target Architecture Shape And Boundaries (Mandatory)

| Layer/Boundary | Purpose | Owns | Must Not Own | Notes |
| --- | --- | --- | --- | --- |
| API Layer (`/api/v1/endpoints/`) | HTTP request handling, validation, authentication, response formatting | FastAPI routers, endpoint functions, HTTP error handling | Business logic orchestration (simple CRUD is acceptable), direct database queries for complex operations | Direct AQL queries acceptable for simple CRUD (established pattern) |
| Model Layer (`/api/models/`) | Data validation, serialization, deserialization | Pydantic request/response models, field validation rules | HTTP handling, database access | Models are pure data structures |
| Core Layer (`/api/core/`) | Infrastructure services | Database connections, authentication dependencies, configuration, caching | Business logic, HTTP handling | Provides reusable infrastructure |
| Database Layer (ArangoDB) | Data persistence | Collections, documents, indexes, AQL queries | Application logic | Customer-isolated databases |

## File And Module Breakdown

| File/Module | Change Type | Layer / Boundary | Concern / Responsibility | Public APIs | Inputs/Outputs | Dependencies |
| --- | --- | --- | --- | --- | --- | --- |
| `src/api/v1/endpoints/projects.py` | Add | API Layer | Project CRUD HTTP endpoints | `POST /`, `GET /`, `GET /{id}`, `PUT /{id}`, `DELETE /{id}`, `GET /{id}/summary` | ScanIngestRequest → APIResponse | get_current_customer, get_customer_db, Pydantic models |
| `src/api/v1/endpoints/repositories.py` | Add | API Layer | Repository CRUD HTTP endpoints | `POST /`, `GET /`, `GET /{id}`, `PUT /{id}`, `DELETE /{id}`, `GET /{id}/summary` | RepositoryRequest → APIResponse | get_current_customer, get_customer_db, Pydantic models |
| `src/api/models/requests/repositories.py` | Add | Model Layer | Repository request validation | CreateRepositoryRequest, UpdateRepositoryRequest | None (data classes) | Pydantic |
| `src/api/models/responses/projects.py` | Add | Model Layer | Project response serialization | ProjectResponse, ProjectSummaryResponse, ListProjectsResponse | None (data classes) | Pydantic |
| `src/api/models/responses/repositories.py` | Add | Model Layer | Repository response serialization | RepositoryResponse, RepositorySummaryResponse, ListRepositoriesResponse | None (data classes) | Pydantic |
| `src/api/v1/endpoints/scan.py` | Modify | API Layer | Scan ingestion + listing with hierarchy | Existing + filtering params | Modified: ScanIngestRequest, query params | get_current_customer, ScanIngestionService |
| `src/api/models/requests/scan.py` | Modify | Model Layer | Scan request validation with hierarchy | ScanIngestRequest (add fields) | None | Pydantic |
| `src/api/v1/router.py` | Modify | API Layer | Router registration | api_router (aggregate) | None | FastAPI, endpoint modules |
| `scripts/test_multi_tenant_hierarchy.py` | Add | Testing | E2E test for multi-repo workflow | main() | None (script) | requests library |

## Layer-Appropriate Separation Of Concerns Check

- **UI/frontend scope**: N/A (backend-only feature)
- **Non-UI scope**: ✅ Responsibility is clear at file/module/service boundaries
  - Each endpoint file owns one entity (projects, repositories, scans)
  - Each model file owns one entity's validation/serialization
  - Core files own infrastructure concerns (DB, auth, config)
- **Integration/infrastructure scope**: ✅ Database access abstracted via `get_customer_db()`, authentication via `get_current_customer()`

## Naming Decisions (Natural And Implementation-Friendly)

| Item Type | Current Name | Proposed Name | Reason | Notes |
| --- | --- | --- | --- | --- |
| File | N/A | `projects.py` | Matches established pattern (`account.py`, `scan.py`) | Plural noun for collection resource |
| File | N/A | `repositories.py` | Matches established pattern | Plural noun for collection resource |
| Model | N/A | `CreateProjectRequest` | Follows `{Action}{Entity}Request` pattern | Consistent with CreateAPIKeyRequest |
| Model | N/A | `ProjectResponse` | Follows `{Entity}Response` pattern | Consistent with APIKeyResponse |
| Model | N/A | `ProjectSummaryResponse` | Describes aggregation data | Clear intent for summary endpoint |
| API Route | N/A | `/v1/projects` | RESTful collection resource | Standard REST naming |
| API Route | N/A | `/v1/projects/{project_id}/summary` | Sub-resource for aggregation | Clear intent, follows REST conventions |
| Collection | N/A | `projects` | Plural snake_case | Matches `customer_api_keys`, `scan_sessions` |
| Collection | N/A | `repositories` | Plural snake_case | Matches established pattern |
| Field | N/A | `project_id` | Snake_case with entity prefix | Matches `customer_id`, `repository_id` |

## Naming Drift Check (Mandatory)

| Item | Current Responsibility | Does Name Still Match? | Corrective Action | Mapped Change ID |
| --- | --- | --- | --- | --- |
| N/A | N/A (all new entities) | Yes | N/A | N/A |

**Note**: No naming drift since all entities are new. Existing entities retain their current names.

## Existing-Structure Bias Check (Mandatory)

| Candidate Area | Current-File-Layout Bias Risk | Architecture-First Alternative | Decision | Why |
| --- | --- | --- | --- | --- |
| Project/Repository endpoints | Low | Create new endpoint files vs. add to existing scan.py | Create new files | Follows established pattern (one file per entity), clear separation of concerns |
| Aggregation logic | Low | Inline AQL queries vs. service layer | Inline AQL queries | Consistent with current approach (account.py), simple aggregation doesn't warrant service layer |
| Scan filtering | Low | Modify scan.py vs. create new filter endpoint | Modify scan.py | Natural extension of existing list endpoint, follows REST conventions |

## Anti-Hack Check (Mandatory)

| Candidate Change | Shortcut/Hack Risk | Proper Structural Fix | Decision | Notes |
| --- | --- | --- | --- | --- |
| Scan hierarchy fields | Low | Add nullable fields vs. separate hierarchy table | Add nullable fields | Acceptable - maintains data locality, backward compatible |
| Project deletion with repositories | Low | Allow deletion vs. prevent deletion | Prevent deletion | Proper data integrity - check for dependencies before soft delete |
| Aggregation caching | Low | Real-time queries vs. cached counts | Real-time queries (v1) | Acceptable - optimize later if needed, avoids premature optimization |

**Rule**: A functionally working local fix is still invalid here if it degrades layering or responsibility boundaries.
**Assessment**: No hacks detected - all changes follow established patterns and maintain clean boundaries.

## Dependency Flow And Cross-Reference Risk

| Module/File | Upstream Dependencies | Downstream Dependents | Cross-Reference Risk | Mitigation / Boundary Strategy |
| --- | --- | --- | --- | --- |
| `projects.py` | get_current_customer, get_customer_db, Pydantic models | router.py | Low | Clear dependency direction (API → Core), no circular deps |
| `repositories.py` | get_current_customer, get_customer_db, Pydantic models, projects collection (for validation) | router.py | Low | Validate project_id exists before creating repository |
| `scan.py` (modified) | get_current_customer, repositories collection (for validation) | router.py | Low | Validate repository_id exists before accepting scan |

## Allowed Dependency Direction (Mandatory)

- **Allowed direction rules**: `API → Core → Database`, `API → Models`, `Models → (no dependencies)`
- **Temporary boundary violations and cleanup deadline**: None - all dependencies follow established direction
- **Cross-layer validation**: Repository creation validates `project_id` against `projects` collection (acceptable - same layer, data integrity check)

## Decommission / Cleanup Plan

| Item To Remove/Rename | Cleanup Actions | Legacy Removal Notes | Verification |
| --- | --- | --- | --- |
| N/A | None (additive feature) | No legacy code to remove | N/A |

## Data Models (If Needed)

### Project Document (ArangoDB)

```json
{
  "_key": "proj_abc123",
  "project_id": "proj_abc123",
  "customer_id": "demo_customer",
  "name": "Backend Services",
  "description": "Microservices powering the API platform",
  "tags": ["backend", "api", "production"],
  "created_at": "2024-03-12T10:00:00Z",
  "updated_at": "2024-03-12T10:00:00Z",
  "repository_count": 5,
  "active": true
}
```

### Repository Document (ArangoDB)

```json
{
  "_key": "repo_xyz789",
  "repository_id": "repo_xyz789",
  "customer_id": "demo_customer",
  "project_id": "proj_abc123",
  "name": "api-gateway",
  "description": "Kong-based API gateway",
  "repository_url": "https://github.com/acme/api-gateway",
  "default_branch": "main",
  "tags": ["gateway", "auth", "critical"],
  "created_at": "2024-03-12T10:00:00Z",
  "updated_at": "2024-03-12T10:00:00Z",
  "last_scan_at": "2024-03-12T10:00:00Z",
  "scan_count": 42,
  "active": true
}
```

### Scan Session Document (Updated)

```json
{
  "_key": "scan_abc123",
  "scan_session_id": "scan_abc123",
  "customer_id": "demo_customer",
  "project_id": "proj_abc123",        // NEW (nullable)
  "repository_id": "repo_xyz789",     // NEW (nullable)
  "scan_type": "sca",
  "format": "cyclonedx",
  "findings_count": 42,
  "status": "completed"
}
```

## Error Handling And Edge Cases

**Project Deletion**:
- Check if repositories exist → Return 400 "Cannot delete project with existing repositories"
- Soft delete only (active=false)

**Repository Deletion**:
- Check if scans exist → Return 400 "Cannot delete repository with existing scans"
- Soft delete only (active=false)

**Scan Submission**:
- Validate `project_id` exists and belongs to customer → Return 400 if invalid
- Validate `repository_id` exists and belongs to customer → Return 400 if invalid
- Allow null values (backward compatibility)

**Aggregation**:
- Empty project (no repositories) → Return valid response with zero counts
- Empty repository (no scans) → Return valid response with zero counts
- Invalid IDs → Return 404 Not Found

## Use-Case Coverage Matrix (Design Gate)

| use_case_id | Requirement | Use Case | Primary Path Covered | Fallback Path Covered | Error Path Covered | Runtime Call Stack Section |
| --- | --- | --- | --- | --- | --- | --- |
| UC-001 | R-001, R-004 | Create project | Yes | N/A | Yes (validation errors) | Section 1.1 |
| UC-002 | R-001, R-004 | List projects | Yes | Yes (empty list) | N/A | Section 1.2 |
| UC-003 | R-001, R-004 | Get project details | Yes | N/A | Yes (not found) | Section 1.3 |
| UC-004 | R-001, R-004 | Update project | Yes | N/A | Yes (validation errors) | Section 1.4 |
| UC-005 | R-001, R-004 | Delete project | Yes | Yes (soft delete) | Yes (has repositories) | Section 1.5 |
| UC-006 | R-002, R-005 | Create repository | Yes | Yes (with/without project_id) | Yes (validation errors) | Section 2.1 |
| UC-007 | R-002, R-005 | List repositories | Yes | Yes (filter by project + empty) | N/A | Section 2.2 |
| UC-008 | R-002, R-005 | Get repository details | Yes | N/A | Yes (not found) | Section 2.3 |
| UC-009 | R-002, R-005 | Update repository | Yes | Yes (reassign project) | Yes (validation errors) | Section 2.4 |
| UC-010 | R-002, R-005 | Delete repository | Yes | Yes (soft delete) | Yes (has scans) | Section 2.5 |
| UC-011 | R-003 | Submit scan with hierarchy | Yes | N/A | Yes (invalid IDs) | Section 3.1 |
| UC-012 | R-006 | Filter scans by project | Yes | Yes (empty list) | N/A | Section 3.2 |
| UC-013 | R-006 | Filter scans by repository | Yes | Yes (empty list) | N/A | Section 3.3 |
| UC-014 | R-006 | Filter scans by both | Yes | Yes (empty list) | N/A | Section 3.4 |
| UC-015 | R-007 | Project summary | Yes | Yes (empty project) | Yes (not found) | Section 4.1 |
| UC-016 | R-008 | Repository summary | Yes | Yes (empty repo) | Yes (not found) | Section 4.2 |
| UC-017 | R-009 | Customer summary with hierarchy | Yes | Yes (no hierarchy fallback) | N/A | Section 4.3 |
| UC-018 | R-010 | Index creation at startup | Yes | N/A | Yes (already exists) | Section 5.1 |

## Performance / Security Considerations

**Performance**:
- Add database indexes: `projects(customer_id)`, `repositories(customer_id, project_id)`, `scan_sessions(customer_id, project_id, repository_id)`
- Aggregation queries: Limit to <2s execution time
- Cached counts: `repository_count`, `scan_count` for faster list views

**Security**:
- All endpoints require X-API-Key authentication
- Customer scoping enforced in all queries (FILTER customer_id == @customer_id)
- No cross-customer data access
- Input validation via Pydantic (max lengths, allowed characters)
- Soft delete prevents accidental data loss

## Migration / Rollout (If Needed)

**Phase 1**: Deploy additive changes (no migration needed)
- New collections created on first use
- Existing scans work without hierarchy fields

**Phase 2**: Encourage adoption
- Update documentation with hierarchy examples
- Provide guidance for organizing existing scans

**Phase 3**: Future enhancement (out of scope)
- Bulk reassignment tool for historical scans
- Auto-detection of project/repo from Git URLs

## Change Traceability To Implementation Plan

| Change ID | Implementation Plan Task(s) | Verification (Unit/Integration/API/E2E) | Status |
| --- | --- | --- | --- |
| C-001 | Implement projects.py endpoints | API tests (AV-001 to AV-020) | Planned |
| C-002 | Implement repositories.py endpoints | API tests (AV-021 to AV-027) | Planned |
| C-003 | Create repository request models | Unit tests (model validation) | Planned |
| C-004 | Create project response models | Unit tests (model serialization) | Planned |
| C-005 | Create repository response models | Unit tests (model serialization) | Planned |
| C-006 | Create E2E test script | E2E execution (AV-048 to AV-050) | Planned |
| C-007 | Update router.py | Integration test (router registration) | Planned |
| C-008 | Update scan.py | API tests (AV-010 to AV-032) | Planned |
| C-009 | Update scan request models | Unit tests (model validation) | Planned |
| C-010 | Update API documentation | Manual review (AC-048 to AC-051) | Planned |
| C-011 | Create projects collection + indexes | E2E test (AV-046, AV-047) | Planned |
| C-012 | Create repositories collection + indexes | E2E test (AV-046, AV-047) | Planned |
| C-013 | Add scan_sessions fields | API test (AV-011) | Planned |

## Design Feedback Loop Notes (From Review/Implementation)

| Date | Trigger (Review/File/Test/Blocker) | Classification | Design Smell | Requirements Updated? | Design Update Applied | Status |
| --- | --- | --- | --- | --- | --- | --- |
| N/A | Pre-review | N/A | No issues detected | No | N/A | Clean |

## Open Questions

1. **Q**: Should we support nested projects (project hierarchy)?
   **A**: No - flat project structure in v1 (out of scope)

2. **Q**: Should we allow bulk reassignment of historical scans?
   **A**: No - future enhancement (out of scope)

3. **Q**: Should we auto-detect project/repo from Git URLs?
   **A**: No - manual assignment only in v1 (out of scope)

All open questions from requirements document are resolved or marked out of scope.
