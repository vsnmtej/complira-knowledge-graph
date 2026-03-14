# Multi-Tenant Hierarchical Architecture

**Version**: 1.0
**Date**: 2026-03-12
**Status**: Design Document

## Overview

This document describes the hierarchical multi-tenant architecture that enables customers to organize their vulnerability scans across multiple projects and repositories, with aggregated insights at each level.

## Hierarchy Levels

```
Customer (Organization)
├── Project A (e.g., "Backend Services")
│   ├── Repository 1 (e.g., "api-gateway")
│   │   ├── Scan Session 1 (2024-03-01)
│   │   ├── Scan Session 2 (2024-03-08)
│   │   └── Scan Session 3 (2024-03-12)
│   ├── Repository 2 (e.g., "user-service")
│   └── Repository 3 (e.g., "payment-processor")
├── Project B (e.g., "Mobile Apps")
│   ├── Repository 1 (e.g., "ios-app")
│   └── Repository 2 (e.g., "android-app")
└── Project C (e.g., "Infrastructure")
    ├── Repository 1 (e.g., "terraform-configs")
    └── Repository 2 (e.g., "kubernetes-manifests")
```

### Level 1: Customer/Organization
- **Scope**: Entire organization's security posture
- **Use Cases**:
  - Executive dashboards
  - Company-wide compliance reporting
  - Cross-project risk aggregation
- **Examples**: "Acme Corp", "TechStart Inc"

### Level 2: Project
- **Scope**: Logical grouping of related repositories
- **Use Cases**:
  - Team-level dashboards (backend team, mobile team)
  - Product-level compliance (e.g., "Payment Platform")
  - Service group security posture
- **Examples**: "Backend Services", "Mobile Apps", "Data Platform"

### Level 3: Repository
- **Scope**: Individual codebase/application
- **Use Cases**:
  - Repository-specific vulnerability tracking
  - Developer-focused security insights
  - CI/CD integration
- **Examples**: "api-gateway", "user-service", "ios-app"

### Level 4: Scan Session
- **Scope**: Point-in-time SBOM snapshot
- **Use Cases**:
  - Temporal analysis (drift, churn)
  - Version-to-version comparison
  - Compliance audit trail
- **Examples**: Scan on 2024-03-12 10:00 UTC

## Data Model

### Projects Collection

**Collection**: `projects` (in customer database)

```json
{
  "_key": "proj_a1b2c3d4e5f6",
  "project_id": "proj_a1b2c3d4e5f6",
  "customer_id": "demo_customer",
  "name": "Backend Services",
  "description": "Microservices powering the API platform",
  "tags": ["backend", "api", "production"],
  "created_at": "2024-01-15T10:00:00Z",
  "updated_at": "2024-03-12T14:30:00Z",
  "repository_count": 5,
  "active": true
}
```

**Fields**:
- `project_id`: Unique identifier (e.g., `proj_abc123`)
- `customer_id`: Foreign key to customer profile
- `name`: Human-readable project name
- `description`: Optional project description
- `tags`: Array of labels for filtering/categorization
- `repository_count`: Cached count of repositories in this project
- `active`: Boolean flag for soft deletion

### Repositories Collection

**Collection**: `repositories` (in customer database)

```json
{
  "_key": "repo_x1y2z3a4b5c6",
  "repository_id": "repo_x1y2z3a4b5c6",
  "customer_id": "demo_customer",
  "project_id": "proj_a1b2c3d4e5f6",
  "name": "api-gateway",
  "description": "Kong-based API gateway with authentication",
  "repository_url": "https://github.com/acme/api-gateway",
  "default_branch": "main",
  "tags": ["gateway", "auth", "critical"],
  "created_at": "2024-01-15T10:00:00Z",
  "updated_at": "2024-03-12T14:30:00Z",
  "last_scan_at": "2024-03-12T10:00:00Z",
  "scan_count": 42,
  "active": true
}
```

**Fields**:
- `repository_id`: Unique identifier (e.g., `repo_abc123`)
- `customer_id`: Foreign key to customer profile
- `project_id`: Foreign key to project (nullable for unassigned repos)
- `name`: Human-readable repository name
- `repository_url`: Git repository URL (optional)
- `default_branch`: Default branch name (e.g., "main", "master")
- `tags`: Array of labels for filtering/categorization
- `last_scan_at`: Timestamp of most recent scan
- `scan_count`: Cached count of scan sessions
- `active`: Boolean flag for soft deletion

### Updated Scan Sessions

**Collection**: `scan_sessions` (existing, with new fields)

```json
{
  "_key": "session_2024_03_12_001",
  "customer_id": "demo_customer",
  "project_id": "proj_a1b2c3d4e5f6",       // NEW
  "repository_id": "repo_x1y2z3a4b5c6",    // NEW
  "scan_timestamp": "2024-03-12T10:00:00Z",
  "sbom_format": "cyclonedx",
  "sbom_version": "1.5",
  "scanner_tool": "trivy",
  "scanner_version": "0.49.0",
  "findings_count": 42,
  "critical_count": 5,
  "high_count": 12,
  "medium_count": 18,
  "low_count": 7
}
```

**New Fields**:
- `project_id`: Link to project (nullable)
- `repository_id`: Link to repository (nullable)

## API Endpoints

### Project Management

#### Create Project
```http
POST /v1/projects
X-API-Key: your_api_key
Content-Type: application/json

{
  "name": "Backend Services",
  "description": "Microservices powering the API platform",
  "tags": ["backend", "api", "production"]
}
```

**Response**:
```json
{
  "success": true,
  "data": {
    "project_id": "proj_a1b2c3d4e5f6",
    "name": "Backend Services",
    "description": "Microservices powering the API platform",
    "tags": ["backend", "api", "production"],
    "created_at": "2024-03-12T14:30:00Z",
    "repository_count": 0
  },
  "metadata": {
    "execution_time_ms": 12.5
  }
}
```

#### List Projects
```http
GET /v1/projects
X-API-Key: your_api_key
```

**Response**:
```json
{
  "success": true,
  "data": {
    "projects": [
      {
        "project_id": "proj_a1b2c3d4e5f6",
        "name": "Backend Services",
        "repository_count": 5,
        "last_scan_at": "2024-03-12T10:00:00Z",
        "created_at": "2024-01-15T10:00:00Z"
      }
    ],
    "total": 3
  }
}
```

#### Get Project Details
```http
GET /v1/projects/{project_id}
X-API-Key: your_api_key
```

**Response**:
```json
{
  "success": true,
  "data": {
    "project_id": "proj_a1b2c3d4e5f6",
    "name": "Backend Services",
    "description": "Microservices powering the API platform",
    "tags": ["backend", "api", "production"],
    "repository_count": 5,
    "repositories": [
      {
        "repository_id": "repo_x1y2z3a4b5c6",
        "name": "api-gateway",
        "last_scan_at": "2024-03-12T10:00:00Z",
        "findings_count": 42
      }
    ],
    "created_at": "2024-01-15T10:00:00Z"
  }
}
```

#### Update Project
```http
PUT /v1/projects/{project_id}
X-API-Key: your_api_key
Content-Type: application/json

{
  "description": "Updated description",
  "tags": ["backend", "critical"]
}
```

#### Delete Project
```http
DELETE /v1/projects/{project_id}
X-API-Key: your_api_key
```

### Repository Management

#### Create Repository
```http
POST /v1/repositories
X-API-Key: your_api_key
Content-Type: application/json

{
  "name": "api-gateway",
  "project_id": "proj_a1b2c3d4e5f6",
  "description": "Kong-based API gateway",
  "repository_url": "https://github.com/acme/api-gateway",
  "default_branch": "main",
  "tags": ["gateway", "auth", "critical"]
}
```

**Response**:
```json
{
  "success": true,
  "data": {
    "repository_id": "repo_x1y2z3a4b5c6",
    "name": "api-gateway",
    "project_id": "proj_a1b2c3d4e5f6",
    "created_at": "2024-03-12T14:30:00Z",
    "scan_count": 0
  }
}
```

#### List Repositories
```http
GET /v1/repositories?project_id=proj_a1b2c3d4e5f6
X-API-Key: your_api_key
```

**Response**:
```json
{
  "success": true,
  "data": {
    "repositories": [
      {
        "repository_id": "repo_x1y2z3a4b5c6",
        "name": "api-gateway",
        "project_id": "proj_a1b2c3d4e5f6",
        "project_name": "Backend Services",
        "last_scan_at": "2024-03-12T10:00:00Z",
        "scan_count": 42,
        "findings_count": 156
      }
    ],
    "total": 5
  }
}
```

#### Get Repository Details
```http
GET /v1/repositories/{repository_id}
X-API-Key: your_api_key
```

#### Update Repository
```http
PUT /v1/repositories/{repository_id}
X-API-Key: your_api_key
Content-Type: application/json

{
  "project_id": "proj_b2c3d4e5f6g7",
  "description": "Updated description"
}
```

#### Delete Repository
```http
DELETE /v1/repositories/{repository_id}
X-API-Key: your_api_key
```

### Updated Scan Endpoints

#### Submit Scan (with hierarchy)
```http
POST /v1/scan/submit
X-API-Key: your_api_key
Content-Type: application/json

{
  "project_id": "proj_a1b2c3d4e5f6",
  "repository_id": "repo_x1y2z3a4b5c6",
  "sbom": { ... },
  "scanner_tool": "trivy",
  "scanner_version": "0.49.0"
}
```

#### List Scans (with filtering)
```http
GET /v1/scan/list?project_id=proj_a1b2c3d4e5f6
GET /v1/scan/list?repository_id=repo_x1y2z3a4b5c6
GET /v1/scan/list?project_id=proj_a1b2c3d4e5f6&repository_id=repo_x1y2z3a4b5c6
X-API-Key: your_api_key
```

### Aggregation Endpoints

#### Project-Level Summary
```http
GET /v1/projects/{project_id}/summary
X-API-Key: your_api_key
```

**Response**:
```json
{
  "success": true,
  "data": {
    "project_id": "proj_a1b2c3d4e5f6",
    "project_name": "Backend Services",
    "repository_count": 5,
    "total_scans": 210,
    "findings": {
      "total": 487,
      "critical": 23,
      "high": 87,
      "medium": 245,
      "low": 132,
      "by_repository": [
        {
          "repository_id": "repo_x1y2z3a4b5c6",
          "repository_name": "api-gateway",
          "findings_count": 156,
          "critical_count": 8
        }
      ]
    },
    "top_vulnerabilities": [
      {
        "cve_id": "CVE-2021-44228",
        "severity": "CRITICAL",
        "affected_repositories": 3,
        "first_seen": "2024-01-15T10:00:00Z"
      }
    ],
    "compliance_status": {
      "compliant_repositories": 3,
      "non_compliant_repositories": 2
    }
  }
}
```

#### Repository-Level Summary
```http
GET /v1/repositories/{repository_id}/summary
X-API-Key: your_api_key
```

**Response**:
```json
{
  "success": true,
  "data": {
    "repository_id": "repo_x1y2z3a4b5c6",
    "repository_name": "api-gateway",
    "project_id": "proj_a1b2c3d4e5f6",
    "project_name": "Backend Services",
    "scan_count": 42,
    "first_scan": "2024-01-15T10:00:00Z",
    "last_scan": "2024-03-12T10:00:00Z",
    "current_findings": {
      "total": 156,
      "critical": 8,
      "high": 34,
      "medium": 78,
      "low": 36
    },
    "trends": {
      "new_vulnerabilities_30d": 12,
      "resolved_vulnerabilities_30d": 8,
      "severity_trend": "improving"
    },
    "top_vulnerabilities": [
      {
        "cve_id": "CVE-2021-44228",
        "severity": "CRITICAL",
        "first_seen": "2024-02-01T10:00:00Z",
        "status": "open"
      }
    ]
  }
}
```

#### Customer-Level Summary (Organization)
```http
GET /v1/summary
X-API-Key: your_api_key
```

**Response**:
```json
{
  "success": true,
  "data": {
    "customer_id": "demo_customer",
    "customer_name": "Acme Corp",
    "project_count": 3,
    "repository_count": 15,
    "total_scans": 630,
    "findings": {
      "total": 1247,
      "critical": 67,
      "high": 234,
      "medium": 678,
      "low": 268,
      "by_project": [
        {
          "project_id": "proj_a1b2c3d4e5f6",
          "project_name": "Backend Services",
          "findings_count": 487,
          "critical_count": 23
        }
      ]
    },
    "compliance_status": {
      "compliant_projects": 2,
      "non_compliant_projects": 1
    }
  }
}
```

## Use Cases

### Use Case 1: Multi-Repository Backend Team

**Scenario**: Backend engineering team manages 5 microservices

**Setup**:
1. Create project: "Backend Services"
2. Create repositories: "api-gateway", "user-service", "payment-processor", "notification-service", "analytics-service"

**Workflow**:
1. Each CI/CD pipeline submits scans with `project_id` and `repository_id`
2. Team lead reviews project-level dashboard
3. Developers drill down to specific repository vulnerabilities
4. Security team monitors customer-level compliance

### Use Case 2: Mobile App Development

**Scenario**: Mobile team maintains iOS and Android apps

**Setup**:
1. Create project: "Mobile Apps"
2. Create repositories: "ios-app", "android-app"

**Workflow**:
1. CI/CD submits scans for each platform
2. Product manager reviews project-level summary
3. Platform-specific developers review repository-level findings

### Use Case 3: Multi-Team Organization

**Scenario**: Company with backend, mobile, and infrastructure teams

**Setup**:
1. Create projects: "Backend Services", "Mobile Apps", "Infrastructure"
2. Create repositories under each project

**Workflow**:
1. CTO reviews customer-level executive dashboard
2. Team leads review project-level summaries
3. Developers review repository-level findings

## Migration Strategy

### Phase 1: Add Optional Fields
- Add `project_id` and `repository_id` to scan submissions (optional)
- Existing scans without hierarchy still work
- No breaking changes

### Phase 2: Encourage Adoption
- Update documentation with hierarchy examples
- Provide migration tools to assign existing scans to projects/repos

### Phase 3: Full Adoption
- Make `repository_id` required for new scans
- `project_id` remains optional (for ungrouped repos)

## Database Indexes

```python
# Projects collection
db.collection("projects").add_persistent_index(
    fields=["customer_id"],
    unique=False
)

# Repositories collection
db.collection("repositories").add_persistent_index(
    fields=["customer_id"],
    unique=False
)
db.collection("repositories").add_persistent_index(
    fields=["project_id"],
    unique=False
)

# Scan sessions collection
db.collection("scan_sessions").add_persistent_index(
    fields=["customer_id", "project_id"],
    unique=False
)
db.collection("scan_sessions").add_persistent_index(
    fields=["customer_id", "repository_id"],
    unique=False
)
```

## Security Considerations

### Access Control
- All endpoints require authentication via X-API-Key
- Projects/repositories scoped to customer via `customer_id`
- No cross-customer data access

### Validation
- Project IDs validated against customer's projects
- Repository IDs validated against customer's repositories
- Prevent orphaned scans (repository must exist)

### Data Isolation
- Each customer has isolated database
- No shared projects/repositories across customers

## Performance Considerations

### Caching
- Cache project/repository metadata (low churn)
- Cache aggregated summaries (recompute on new scan)

### Query Optimization
- Use indexes on `customer_id`, `project_id`, `repository_id`
- Pre-aggregate counts (`repository_count`, `scan_count`)
- Lazy-load detailed repository lists in project details

### Scalability
- Project/repository collections are small (<1000 records typically)
- Scan sessions grow over time (archive old scans)
- Aggregation queries benefit from indexes

## Next Steps

1. ✅ Design document (this file)
2. Implement data models
3. Implement API endpoints
4. Update scan submission/listing
5. Implement aggregation endpoints
6. Update API documentation
7. Create test scripts
8. Migration guide for existing customers
