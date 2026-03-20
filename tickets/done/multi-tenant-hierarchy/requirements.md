# Requirements Document
**Ticket**: `multi-tenant-hierarchy`
**Status**: `Design-ready`
**Date**: 2026-03-12
**Last Updated**: 2026-03-12

## Problem Statement

Users with multiple repositories and projects currently have no way to organize their vulnerability scans hierarchically. All scans are flat at the customer level, making it difficult to:

1. Get project-level insights (e.g., "Backend Services" team with 5 microservices)
2. Get repository-level trends (e.g., individual "api-gateway" vulnerability history)
3. Aggregate findings across related repositories
4. Filter scan data by project or repository
5. Track compliance at different organizational levels

**User Request**:
> "what if users have multiple repos and projects. can we provide repo level, project level with multiple repos all the insights from APIs?"

## Goal

Implement a hierarchical multi-tenant architecture that allows customers to organize scans into:
- **Projects** (logical groups like "Backend Services", "Mobile Apps")
- **Repositories** (individual codebases like "api-gateway", "ios-app")
- **Scan Sessions** (time-stamped SBOM snapshots)

Enable API endpoints to provide insights at each level (customer, project, repository).

## Scope

### In-Scope

1. **Data Model**: Project and Repository entities with proper relationships
2. **Project Management**: CRUD APIs for projects
3. **Repository Management**: CRUD APIs for repositories
4. **Scan Hierarchy**: Update scan submission/listing to support project_id and repository_id
5. **Filtering**: Filter scans by project, repository, or both
6. **Aggregation**: Project-level and repository-level summary endpoints
7. **Migration**: Backward compatibility with existing scans (no project/repo assigned)
8. **API Documentation**: Update docs with hierarchy examples
9. **Testing**: E2E test script demonstrating multi-repo workflow

### Out-of-Scope

- UI/dashboard implementation (API-first)
- Automatic project/repository detection from Git URLs
- Cross-customer project sharing
- Repository access control/permissions (all repos visible to customer)
- Historical scan reassignment to projects/repos (future enhancement)

## Requirements

### R-001: Project Data Model
**Priority**: High
**Description**: Define Project entity with necessary fields and relationships

**Details**:
- `project_id`: Unique identifier (e.g., `proj_abc123`)
- `customer_id`: Link to customer (scoping)
- `name`: Human-readable name (e.g., "Backend Services")
- `description`: Optional description
- `tags`: Array of labels for categorization
- `created_at`, `updated_at`: Timestamps
- `repository_count`: Cached count
- `active`: Soft delete flag

**Acceptance Criteria**:
- **AC-001**: Project document validates with all required fields
- **AC-002**: Project is scoped to customer (cannot access other customer's projects)
- **AC-003**: Project name is unique within customer
- **AC-004**: Soft delete preserves data integrity (sets active=false)

### R-002: Repository Data Model
**Priority**: High
**Description**: Define Repository entity with necessary fields and relationships

**Details**:
- `repository_id`: Unique identifier (e.g., `repo_xyz789`)
- `customer_id`: Link to customer
- `project_id`: Link to project (nullable - unassigned repos allowed)
- `name`: Human-readable name (e.g., "api-gateway")
- `repository_url`: Optional Git URL
- `default_branch`: Branch name (e.g., "main")
- `tags`: Array of labels
- `created_at`, `updated_at`, `last_scan_at`: Timestamps
- `scan_count`: Cached count
- `active`: Soft delete flag

**Acceptance Criteria**:
- **AC-005**: Repository document validates with all required fields
- **AC-006**: Repository is scoped to customer
- **AC-007**: Repository name is unique within customer
- **AC-008**: Repository can exist without project_id (null allowed)
- **AC-009**: Soft delete preserves data integrity

### R-003: Scan Session Hierarchy
**Priority**: High
**Description**: Update scan sessions to link to project and repository

**Details**:
- Add `project_id` field (nullable)
- Add `repository_id` field (nullable)
- Maintain backward compatibility (existing scans without hierarchy)

**Acceptance Criteria**:
- **AC-010**: Scan submission accepts optional project_id and repository_id
- **AC-011**: Existing scans without project/repo IDs continue to work
- **AC-012**: Invalid project/repo IDs are rejected with clear error message
- **AC-013**: Scan is linked to customer's project/repo only (no cross-customer)

### R-004: Project Management API
**Priority**: High
**Description**: CRUD endpoints for project management

**Endpoints**:
- `POST /v1/projects` - Create project
- `GET /v1/projects` - List projects
- `GET /v1/projects/{project_id}` - Get project details
- `PUT /v1/projects/{project_id}` - Update project
- `DELETE /v1/projects/{project_id}` - Soft delete project

**Acceptance Criteria**:
- **AC-014**: Create project returns project_id and stores in database
- **AC-015**: List projects returns all active projects for authenticated customer
- **AC-016**: Get project details includes repository_count and last_scan_at
- **AC-017**: Update project allows changing name, description, tags
- **AC-018**: Delete project soft deletes (active=false) and prevents deletion if repositories exist
- **AC-019**: All endpoints require authentication (X-API-Key header)
- **AC-020**: Endpoints return proper error codes (400, 401, 404, 500)

### R-005: Repository Management API
**Priority**: High
**Description**: CRUD endpoints for repository management

**Endpoints**:
- `POST /v1/repositories` - Create repository
- `GET /v1/repositories?project_id={id}` - List repositories (with optional project filter)
- `GET /v1/repositories/{repository_id}` - Get repository details
- `PUT /v1/repositories/{repository_id}` - Update repository
- `DELETE /v1/repositories/{repository_id}` - Soft delete repository

**Acceptance Criteria**:
- **AC-021**: Create repository returns repository_id and stores in database
- **AC-022**: List repositories supports optional project_id filter
- **AC-023**: Get repository details includes scan_count and last_scan_at
- **AC-024**: Update repository allows changing project_id (reassign to different project)
- **AC-025**: Delete repository soft deletes and prevents deletion if scans exist
- **AC-026**: All endpoints require authentication
- **AC-027**: Endpoints return proper error codes

### R-006: Scan Filtering
**Priority**: High
**Description**: Filter scans by project and/or repository

**Endpoints**:
- `GET /v1/scan/list?project_id={id}`
- `GET /v1/scan/list?repository_id={id}`
- `GET /v1/scan/list?project_id={id}&repository_id={id}`

**Acceptance Criteria**:
- **AC-028**: Filter by project_id returns only scans in that project
- **AC-029**: Filter by repository_id returns only scans in that repository
- **AC-030**: Filter by both returns scans matching both criteria
- **AC-031**: Invalid IDs return empty list (not error)
- **AC-032**: Filtering respects customer scoping (no cross-customer access)

### R-007: Project-Level Aggregation
**Priority**: Medium
**Description**: Aggregate vulnerability insights across all repositories in a project

**Endpoint**:
- `GET /v1/projects/{project_id}/summary`

**Response Includes**:
- Project metadata
- Repository count
- Total scan count
- Aggregated findings (total, by severity)
- Findings breakdown by repository
- Top vulnerabilities across project
- Compliance status

**Acceptance Criteria**:
- **AC-033**: Project summary includes all repositories in project
- **AC-034**: Findings are aggregated from latest scan per repository
- **AC-035**: Top vulnerabilities sorted by severity and affected repository count
- **AC-036**: Empty project (no repositories) returns valid response with zero counts
- **AC-037**: Summary respects customer scoping

### R-008: Repository-Level Aggregation
**Priority**: Medium
**Description**: Aggregate vulnerability insights and trends for a single repository over time

**Endpoint**:
- `GET /v1/repositories/{repository_id}/summary`

**Response Includes**:
- Repository metadata
- Scan history (count, first, last)
- Current findings (from latest scan)
- Trends (new vs resolved vulnerabilities over last 30 days)
- Top vulnerabilities
- Severity trend (improving/degrading)

**Acceptance Criteria**:
- **AC-038**: Repository summary includes all scan sessions for that repository
- **AC-039**: Current findings are from most recent scan
- **AC-040**: Trends compare latest scan to scan from 30 days ago
- **AC-041**: Empty repository (no scans) returns valid response with zero counts
- **AC-042**: Summary respects customer scoping

### R-009: Customer-Level Aggregation (Updated)
**Priority**: Medium
**Description**: Extend existing customer summary to include hierarchy breakdown

**Endpoint**:
- `GET /v1/summary` (existing, enhanced)

**Enhanced Response Includes**:
- Project count
- Repository count
- Findings breakdown by project
- Compliance status by project

**Acceptance Criteria**:
- **AC-043**: Customer summary includes project_count and repository_count
- **AC-044**: Findings breakdown shows aggregation by project
- **AC-045**: Backward compatible (works for customers without projects/repos)

### R-010: Database Indexes
**Priority**: High
**Description**: Create indexes for query performance

**Indexes**:
- `projects` collection: index on `customer_id`
- `repositories` collection: index on `customer_id`, index on `project_id`
- `scan_sessions` collection: index on `customer_id + project_id`, index on `customer_id + repository_id`

**Acceptance Criteria**:
- **AC-046**: Indexes are created at API startup (or via migration script)
- **AC-047**: Query performance is acceptable (<500ms for list operations)

### R-011: API Documentation
**Priority**: Medium
**Description**: Update API documentation with hierarchy examples

**Acceptance Criteria**:
- **AC-048**: Documentation includes project management endpoints
- **AC-049**: Documentation includes repository management endpoints
- **AC-050**: Documentation includes hierarchy examples (multi-repo setup)
- **AC-051**: Documentation includes use case examples (backend team, mobile team)

### R-012: End-to-End Test Script
**Priority**: Medium
**Description**: Create test script demonstrating multi-repo workflow

**Test Flow**:
1. Create project "Backend Services"
2. Create 3 repositories under project
3. Submit scans for each repository
4. Query project-level summary
5. Query repository-level summary
6. Filter scans by project and repository

**Acceptance Criteria**:
- **AC-052**: Test script completes successfully
- **AC-053**: Test script validates all aggregation endpoints
- **AC-054**: Test script demonstrates filtering capabilities

## Constraints

1. **Backward Compatibility**: Existing scans without project/repo IDs must continue to work
2. **Customer Scoping**: All entities strictly scoped to authenticated customer
3. **No Cross-Customer Access**: Projects/repos/scans isolated per customer
4. **Soft Delete**: Deletion sets `active=false` (preserves audit trail)
5. **API-First**: No UI implementation in this scope
6. **Database**: ArangoDB collections in customer-specific databases

## Assumptions

1. Customers manually create projects and repositories (no auto-detection)
2. Repository names are unique within customer (not globally)
3. A repository can only belong to one project at a time
4. A scan session can only belong to one repository
5. Unassigned repositories and scans are allowed (hierarchy is optional)
6. Project/repository deletion is prevented if dependent entities exist

## Dependencies

- Existing authentication system (X-API-Key)
- Existing customer database architecture
- Existing scan submission/listing endpoints
- Existing API response models (APIResponse wrapper)

## Open Questions

1. **Q**: Should we allow moving repositories between projects?
   **A**: Yes - PUT /v1/repositories/{id} allows updating project_id

2. **Q**: Should we allow deleting projects with repositories?
   **A**: No - return error 400 "Cannot delete project with existing repositories"

3. **Q**: Should we automatically detect project/repo from Git URL?
   **A**: Out of scope - manual assignment only in v1

4. **Q**: Should we support nested projects (project hierarchy)?
   **A**: Out of scope - flat project structure in v1

## Risks

1. **Performance**: Aggregation queries across many repositories could be slow
   - **Mitigation**: Add database indexes, cache aggregated counts

2. **Migration**: Existing customers may have many unorganized scans
   - **Mitigation**: Provide backward compatibility, optional hierarchy

3. **Complexity**: Additional entities increase API surface area
   - **Mitigation**: Clear documentation, comprehensive test coverage

## Success Metrics

1. API endpoints return correct data with <500ms latency
2. E2E test script passes all scenarios
3. API documentation is complete and clear
4. Zero breaking changes to existing scan workflows
5. Customer can organize 50+ repositories across 10+ projects efficiently

## Non-Functional Requirements

### NFR-001: Performance
- List operations: <500ms
- Get operations: <200ms
- Aggregation operations: <2s

### NFR-002: Reliability
- Input validation on all endpoints
- Graceful error handling with meaningful messages
- Transaction safety for multi-step operations

### NFR-003: Maintainability
- Code follows existing patterns (Pydantic models, FastAPI dependencies)
- Comprehensive inline documentation
- Reusable query functions

### NFR-004: Security
- All endpoints require authentication
- Customer scoping enforced at database query level
- No sensitive data in error messages

## Requirement Coverage Map

This map ensures all requirements are covered by at least one use case in the runtime call stack document.

| Requirement ID | Requirement Summary | Mapped Use Case IDs | Coverage Status |
| --- | --- | --- | --- |
| R-001 | Project data model | UC-001 (Create project), UC-002 (List projects), UC-003 (Get project), UC-004 (Update project), UC-005 (Delete project) | Complete |
| R-002 | Repository data model | UC-006 (Create repository), UC-007 (List repositories), UC-008 (Get repository), UC-009 (Update repository), UC-010 (Delete repository) | Complete |
| R-003 | Scan session hierarchy | UC-011 (Submit scan with hierarchy), UC-012 (List scans with filtering) | Complete |
| R-004 | Project management API | UC-001, UC-002, UC-003, UC-004, UC-005 | Complete |
| R-005 | Repository management API | UC-006, UC-007, UC-008, UC-009, UC-010 | Complete |
| R-006 | Scan filtering | UC-012 (Filter by project), UC-013 (Filter by repository), UC-014 (Filter by both) | Complete |
| R-007 | Project-level aggregation | UC-015 (Project summary) | Complete |
| R-008 | Repository-level aggregation | UC-016 (Repository summary) | Complete |
| R-009 | Customer-level aggregation | UC-017 (Customer summary with hierarchy) | Complete |
| R-010 | Database indexes | UC-018 (Index creation at startup) | Complete |
| R-011 | API documentation | N/A (documentation requirement) | N/A |
| R-012 | E2E test script | N/A (testing requirement) | N/A |

## Acceptance Criteria Coverage Map to Stage 7 Scenarios

This map ensures all acceptance criteria are mapped to API/E2E test scenarios.

| AC ID | Requirement | Expected Outcome | Stage 7 Scenario IDs | Test Level | Coverage |
| --- | --- | --- | --- | --- | --- |
| AC-001 | R-001 | Project validates with all required fields | AV-001 | API | Complete |
| AC-002 | R-001 | Project scoped to customer (no cross-customer access) | AV-002 | API | Complete |
| AC-003 | R-001 | Project name unique within customer | AV-003 | API | Complete |
| AC-004 | R-001 | Soft delete preserves data (active=false) | AV-004 | API | Complete |
| AC-005 | R-002 | Repository validates with all required fields | AV-005 | API | Complete |
| AC-006 | R-002 | Repository scoped to customer | AV-006 | API | Complete |
| AC-007 | R-002 | Repository name unique within customer | AV-007 | API | Complete |
| AC-008 | R-002 | Repository can exist without project_id | AV-008 | API | Complete |
| AC-009 | R-002 | Soft delete preserves data | AV-009 | API | Complete |
| AC-010 | R-003 | Scan accepts optional project_id/repository_id | AV-010 | API | Complete |
| AC-011 | R-003 | Existing scans without hierarchy work | AV-011 | API | Complete |
| AC-012 | R-003 | Invalid project/repo IDs rejected with error | AV-012 | API | Complete |
| AC-013 | R-003 | Scan linked to customer's project/repo only | AV-013 | API | Complete |
| AC-014 | R-004 | Create project returns project_id | AV-014 | API | Complete |
| AC-015 | R-004 | List projects returns active projects | AV-015 | API | Complete |
| AC-016 | R-004 | Get project includes repository_count | AV-016 | API | Complete |
| AC-017 | R-004 | Update project allows changing fields | AV-017 | API | Complete |
| AC-018 | R-004 | Delete project soft deletes, prevents if repos exist | AV-018 | API | Complete |
| AC-019 | R-004 | All endpoints require authentication | AV-019 | API | Complete |
| AC-020 | R-004 | Endpoints return proper error codes | AV-020 | API | Complete |
| AC-021 | R-005 | Create repository returns repository_id | AV-021 | API | Complete |
| AC-022 | R-005 | List repositories supports project_id filter | AV-022 | API | Complete |
| AC-023 | R-005 | Get repository includes scan_count | AV-023 | API | Complete |
| AC-024 | R-005 | Update repository allows changing project_id | AV-024 | API | Complete |
| AC-025 | R-005 | Delete repository soft deletes, prevents if scans exist | AV-025 | API | Complete |
| AC-026 | R-005 | All endpoints require authentication | AV-026 | API | Complete |
| AC-027 | R-005 | Endpoints return proper error codes | AV-027 | API | Complete |
| AC-028 | R-006 | Filter by project_id returns only project scans | AV-028 | API | Complete |
| AC-029 | R-006 | Filter by repository_id returns only repo scans | AV-029 | API | Complete |
| AC-030 | R-006 | Filter by both returns matching scans | AV-030 | API | Complete |
| AC-031 | R-006 | Invalid IDs return empty list | AV-031 | API | Complete |
| AC-032 | R-006 | Filtering respects customer scoping | AV-032 | API | Complete |
| AC-033 | R-007 | Project summary includes all repositories | AV-033 | API | Complete |
| AC-034 | R-007 | Findings aggregated from latest scan per repo | AV-034 | API | Complete |
| AC-035 | R-007 | Top vulns sorted by severity and repo count | AV-035 | API | Complete |
| AC-036 | R-007 | Empty project returns valid response | AV-036 | API | Complete |
| AC-037 | R-007 | Summary respects customer scoping | AV-037 | API | Complete |
| AC-038 | R-008 | Repository summary includes all scan sessions | AV-038 | API | Complete |
| AC-039 | R-008 | Current findings from most recent scan | AV-039 | API | Complete |
| AC-040 | R-008 | Trends compare latest to 30 days ago | AV-040 | API | Complete |
| AC-041 | R-008 | Empty repository returns valid response | AV-041 | API | Complete |
| AC-042 | R-008 | Summary respects customer scoping | AV-042 | API | Complete |
| AC-043 | R-009 | Customer summary includes project/repo counts | AV-043 | API | Complete |
| AC-044 | R-009 | Findings breakdown by project | AV-044 | API | Complete |
| AC-045 | R-009 | Backward compatible for customers without hierarchy | AV-045 | API | Complete |
| AC-046 | R-010 | Indexes created at API startup | AV-046 | E2E | Complete |
| AC-047 | R-010 | Query performance <500ms for list operations | AV-047 | E2E | Complete |
| AC-048 | R-011 | Documentation includes project endpoints | N/A | Manual | N/A |
| AC-049 | R-011 | Documentation includes repository endpoints | N/A | Manual | N/A |
| AC-050 | R-011 | Documentation includes hierarchy examples | N/A | Manual | N/A |
| AC-051 | R-011 | Documentation includes use case examples | N/A | Manual | N/A |
| AC-052 | R-012 | Test script completes successfully | AV-048 | E2E | Complete |
| AC-053 | R-012 | Test script validates aggregation endpoints | AV-049 | E2E | Complete |
| AC-054 | R-012 | Test script demonstrates filtering | AV-050 | E2E | Complete |

**Note**: AC-048 through AC-051 are documentation requirements and will be verified during Stage 9 (Docs Sync), not Stage 7 (API/E2E Testing).

## Use Case List

Preliminary use case list for runtime call stack modeling (Stage 4):

**Project Management** (UC-001 to UC-005):
- UC-001: Create project (primary + error paths)
- UC-002: List projects for customer (primary + empty result)
- UC-003: Get project details (primary + not found)
- UC-004: Update project (primary + validation errors)
- UC-005: Delete project (primary + soft delete + prevent if repos exist)

**Repository Management** (UC-006 to UC-010):
- UC-006: Create repository (primary + with/without project_id)
- UC-007: List repositories (primary + filter by project + empty result)
- UC-008: Get repository details (primary + not found)
- UC-009: Update repository (primary + reassign project)
- UC-010: Delete repository (primary + soft delete + prevent if scans exist)

**Scan Hierarchy** (UC-011 to UC-014):
- UC-011: Submit scan with project_id and repository_id (primary + validation)
- UC-012: List scans filtered by project (primary + empty)
- UC-013: List scans filtered by repository (primary + empty)
- UC-014: List scans filtered by both (primary + empty)

**Aggregation** (UC-015 to UC-017):
- UC-015: Get project summary (primary + empty project + aggregation logic)
- UC-016: Get repository summary (primary + empty repo + trend calculation)
- UC-017: Get customer summary with hierarchy (primary + no hierarchy fallback)

**Infrastructure** (UC-018):
- UC-018: Index creation at API startup (background operation)

**Total**: 18 use cases covering all requirements

## Revision History

| Version | Date | Changes | Author |
| --- | --- | --- | --- |
| Draft | 2026-03-12 | Initial requirements capture | Claude |
| Design-ready | 2026-03-12 | Added requirement coverage map, AC coverage map, use case list | Claude |
