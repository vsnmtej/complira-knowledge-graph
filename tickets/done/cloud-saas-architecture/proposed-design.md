# Proposed Design Document: Cloud SaaS Architecture

## Design Version

- Current Version: `v1`
- Date: 2026-03-02
- Scope: Phase 0 (Foundation) + Architecture for Phases 1-4

## Revision History

| Version | Trigger | Summary Of Changes | Related Review Round |
| --- | --- | --- | --- |
| v1 | Initial draft | Complete cloud architecture with DRY/SOLID patterns | 1 |

## Artifact Basis

- Investigation Notes: `tickets/in-progress/cloud-saas-architecture/investigation-notes.md`
- Requirements: `tickets/in-progress/cloud-saas-architecture/requirements.md`
- Requirements Status: `Design-ready`

---

## Summary

Transform Complira Knowledge Graph from a local Python CLI application into a cloud-hosted multi-tenant SaaS platform with 13 REST API endpoints implementing 10 advanced security intelligence features. The design strictly follows DRY (Don't Repeat Yourself) and SOLID principles to eliminate code duplication and create a maintainable, extensible architecture.

**Key Design Principles:**
1. **DRY:** Single `BaseGraphService` eliminates graph traversal duplication across 10 features
2. **SRP:** Clear separation - Endpoints (HTTP), Services (business logic), Repositories (DB), Cache (performance)
3. **OCP:** Base classes extensible without modification
4. **LSP:** All services implement protocol interfaces
5. **ISP:** Specific interfaces (ITraversalService, not generic IService)
6. **DIP:** Depend on abstractions (IDatabase, ICacheService) not concretions

**Architecture Decisions Applied:**
- AD-001: Database-per-customer (reference DB + customer DBs)
- AD-002: API and Workers decoupled (separate processes from Day 1)
- AD-003: BaseGraphService for reusable graph patterns
- AD-004: Automatic customer scoping via dependency injection
- AD-005: Redis caching with per-endpoint TTL strategy
- AD-006: API key authentication with FastAPI middleware
- AD-007: Strict SOLID enforcement

---

## Goals

### Primary Goals
1. **Multi-Tenant SaaS Platform:** Support multiple customers with isolated data
2. **API-First Architecture:** 13 REST endpoints for scan ingestion, enrichment, analysis
3. **Zero Code Duplication:** Eliminate repeated graph traversal logic across features
4. **Independent Scaling:** API and workers scale independently
5. **Performance:** < 30s graph traversals, > 70% cache hit ratio
6. **Maintainability:** SOLID principles enable easy feature addition

### Non-Goals (Explicitly Out of Scope)
- GitHub Action client (deferred)
- Multi-cloud support (single cloud provider initially)
- Real-time streaming (batch processing sufficient)
- GraphQL API (REST only)

---

## Legacy Removal Policy (Mandatory)

- **Policy:** No backward compatibility; this is a new cloud architecture alongside existing local app
- **Existing Local App:** Remains unchanged; cloud is net-new parallel system
- **Migration Path:** Local app can gradually adopt cloud services, but no forced migration
- **Required Action:** None - no legacy code to remove (clean slate for `src/api/`)

---

## Requirements And Use Cases

### Phase 0 (Foundation) - Weeks 1-2

| Requirement ID | Description | Acceptance Criteria ID(s) | Acceptance Criteria Summary | Use Case IDs |
| --- | --- | --- | --- | --- |
| REQ-001 | Multi-tenant database | AC-001, AC-002, AC-003 | Reference DB + customer DBs + cross-DB queries | UC-001 |
| REQ-002 | API authentication | AC-004, AC-005, AC-006 | API key validation, customer scoping, data isolation | UC-002 |
| REQ-003 | Caching layer | AC-007, AC-008, AC-009 | Redis cache, TTL strategy, invalidation | UC-003 |
| REQ-004 | Scan ingestion | AC-010 through AC-016 | Parse SARIF/CycloneDX, create findings, return session_id | UC-004 |

### Phase 1 (Core Pipeline) - Weeks 3-5

| Requirement ID | Description | Acceptance Criteria ID(s) | Acceptance Criteria Summary | Use Case IDs |
| --- | --- | --- | --- | --- |
| REQ-005 | Enrichment | AC-017 through AC-022 | CVE → CWE → ATT&CK traversal, EPSS, KEV, caching | UC-005 |
| REQ-006 | Compaction | AC-023 through AC-026 | Dedupe via aliases, CWE rollup, risk scoring | UC-006 |
| REQ-007 | Control mapping | AC-027 through AC-031 | Map to NIST/ISO/FDA, evidence chains, coverage % | UC-007 |

### Phase 2 (Killer Features Wave 1) - Weeks 6-9

| Requirement ID | Description | Acceptance Criteria ID(s) | Acceptance Criteria Summary | Use Case IDs |
| --- | --- | --- | --- | --- |
| REQ-008 | Blast radius | AC-032 through AC-038 | Graph traversal, hop distance, kill chains, visualization | UC-008 |
| REQ-009 | EPSS velocity | AC-039 through AC-043 | 30-day trends, acceleration detection, KEV prediction | UC-009 |
| REQ-010 | Portfolio risk | AC-044 through AC-048 | Aggregate EPSS, trend analysis, inflection points | UC-010 |
| REQ-011 | Defense coverage | AC-049 through AC-053 | ATT&CK heatmap, control mapping, D3FEND recommendations | UC-011 |
| REQ-012 | Regulatory delta | AC-054 through AC-058 | Framework diff, impact analysis, doc regeneration triggers | UC-012 |

---

## Codebase Understanding Snapshot (Pre-Design Mandatory)

| Area | Findings | Evidence (files/functions) | Open Unknowns |
| --- | --- | --- | --- |
| **Entrypoints / Boundaries** | Local CLI application with ingestion agents and LLM enrichment agents | `src/complira_graph/agents/` (24 agents), `src/complira_graph/llm_agents/` (5 agents) | None - well understood |
| **Current Naming Conventions** | snake_case for functions/files, PascalCase for classes, kebab-case for collections | Consistent across codebase | None |
| **Impacted Modules / Responsibilities** | `src/api/` directory exists but empty (clean slate); agents and LLM agents are isolated and reusable | `src/complira_graph/agents/base.py`, `src/complira_graph/llm_agents/` | None |
| **Data / Persistence / External IO** | ArangoDB (335K docs, 1.97M edges), Anthropic Claude API (LLM), HTTP clients for external APIs | `src/complira_graph/db.py`, `src/complira_graph/utils/http_client.py` | Cloud database performance (will benchmark) |

---

## Current State (As-Is)

### Architecture
```
Local CLI Application
├── CLI Commands (entry points)
├── Ingestion Agents (24 agents)
│   └── BaseIngestionAgent (fetch → transform → load)
├── LLM Agents (5 agents)
│   └── BaseLLMAgent (find_gaps → enrich → validate → persist)
├── Database Layer (ArangoDB)
│   └── Single database: complira_graph
├── Orchestration (Prefect)
│   └── seed_workflow.py
└── Utilities (HTTP, transforms, keys)
```

### Strengths
- ✅ Well-structured base classes (BaseIngestionAgent, BaseLLMAgent)
- ✅ Reusable utilities (HTTP client, normalization functions)
- ✅ Comprehensive database schema (27 collections, 44 edges)
- ✅ Gap-based enrichment pattern (efficient)
- ✅ Prefect orchestration for reliable workflows

### Limitations for Cloud SaaS
- ❌ No multi-tenancy (single database)
- ❌ No API layer (direct database access only)
- ❌ No customer isolation
- ❌ No caching (every query hits database)
- ❌ Graph traversal logic scattered across use cases
- ❌ No authentication/authorization
- ❌ Agents tightly coupled to local execution

---

## Target State (To-Be)

### Architecture
```
┌─────────────────────────────────────────────────────────────────┐
│  API LAYER (Horizontally Scalable)                             │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  FastAPI Application (src/api/)                          │  │
│  │                                                            │  │
│  │  ├── Endpoints (src/api/v1/endpoints/)                   │  │
│  │  │   Thin HTTP handlers, FastAPI dependencies            │  │
│  │  │   - scan.py: POST /v1/scan/ingest                     │  │
│  │  │   - enrich.py: POST /v1/enrich                        │  │
│  │  │   - compact.py: POST /v1/compact                      │  │
│  │  │   - mapping.py: POST /v1/map-controls                 │  │
│  │  │   - blast_radius.py: POST /v1/blast-radius            │  │
│  │  │   - ... (9 more endpoints for features)               │  │
│  │  │                                                         │  │
│  │  ├── Services (src/api/services/)                        │  │
│  │  │   Business logic, extend BaseGraphService             │  │
│  │  │   - base.py: BaseGraphService (DRY traversals)        │  │
│  │  │   - enrichment.py: EnrichmentService                  │  │
│  │  │   - compaction.py: CompactionService                  │  │
│  │  │   - blast_radius.py: BlastRadiusService               │  │
│  │  │   - epss_velocity.py: EPSSVelocityService             │  │
│  │  │   - ... (8 more feature services)                     │  │
│  │  │                                                         │  │
│  │  ├── Repositories (src/api/repositories/)                │  │
│  │  │   Database access abstraction (DIP)                   │  │
│  │  │   - base.py: IRepository[T] protocol                  │  │
│  │  │   - vulnerability.py: VulnerabilityRepository         │  │
│  │  │   - component.py: ComponentRepository                 │  │
│  │  │   - ... (repositories per entity type)                │  │
│  │  │                                                         │  │
│  │  ├── Core (src/api/core/)                                │  │
│  │  │   Cross-cutting concerns                              │  │
│  │  │   - config.py: Settings (extends complira_graph)      │  │
│  │  │   - security.py: API key auth, customer scoping       │  │
│  │  │   - cache.py: Redis abstraction, decorators           │  │
│  │  │   - database.py: Multi-tenant DB routing              │  │
│  │  │   - dependencies.py: FastAPI dependency injection     │  │
│  │  │                                                         │  │
│  │  └── Models (src/api/models/)                            │  │
│  │      Pydantic request/response models                     │  │
│  │      - requests/: ScanIngestRequest, EnrichRequest, etc. │  │
│  │      - responses/: APIResponse[T], EnrichmentResponse    │  │
│  │      - domain/: Shared domain models                      │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  Redis Cache    │
                    │  (ICacheService)│
                    └─────────────────┘
                              │
                              ▼
        ┌──────────────────────────────────────────────┐
        │  ArangoDB Cluster (IDatabase)               │
        │  ┌──────────────────┐  ┌─────────────────┐  │
        │  │ complira_        │  │ complira_       │  │
        │  │ reference        │  │ customer_<id>   │  │
        │  │ (shared,         │  │ (isolated per   │  │
        │  │  read-only)      │  │  customer)      │  │
        │  └──────────────────┘  └─────────────────┘  │
        └──────────────────────────────────────────────┘
                              ▲
                              │ (scheduled updates)
                              │
┌─────────────────────────────────────────────────────────────────┐
│  WORKER LAYER (Workload-Based Scaling)                         │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Workers (src/workers/)                                   │  │
│  │                                                            │  │
│  │  ├── Flows (src/workers/flows/)                          │  │
│  │  │   Prefect workflows (reuse agents)                     │  │
│  │  │   - reference_sync.py: NVD, MITRE, EPSS updates       │  │
│  │  │   - epss_velocity.py: Daily velocity computation      │  │
│  │  │   - benchmark_agg.py: Weekly benchmark aggregation    │  │
│  │  │                                                         │  │
│  │  └── Tasks (src/workers/tasks/)                          │  │
│  │      Reusable task definitions                            │  │
│  │      - ingest_nvd.py, ingest_mitre.py, etc.              │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Strengths of Target Design
- ✅ **DRY:** `BaseGraphService` eliminates duplication across 10+ features
- ✅ **SRP:** Clear responsibility per layer (endpoints/services/repos/cache)
- ✅ **OCP:** New features extend base classes without modifying existing code
- ✅ **LSP:** Services substitutable via protocol interfaces
- ✅ **ISP:** Specific interfaces (ITraversalService, not bloated IService)
- ✅ **DIP:** Depend on abstractions (IDatabase, ICacheService)
- ✅ **Multi-Tenant:** Database-per-customer with automatic scoping
- ✅ **Scalable:** API and workers scale independently
- ✅ **Performant:** Redis caching with 70% hit ratio target
- ✅ **Testable:** Dependency injection enables easy mocking

---

## Architecture Direction Decision (Mandatory)

### Chosen Direction
**Add new layered architecture** for cloud SaaS platform while preserving existing local application.

### Rationale
- **Complexity:** Moderate - net-new parallel system, no migration of existing code
- **Testability:** High - dependency injection, mockable interfaces, clear boundaries
- **Operability:** High - independent scaling, fault isolation, declarative caching
- **Evolution Cost:** Low - SOLID principles enable easy feature addition without modifying existing code

### Layering Fitness Assessment
**Current Layering:** Coherent for local CLI application (CLI → Agents → DB → Utils)

**Target Layering:** Net-new architecture required for cloud SaaS
```
API Gateway (rate limiting, auth)
    ↓
REST Endpoints (thin, FastAPI)
    ↓
Services (business logic, extend BaseGraphService)
    ↓
Repositories (database abstraction, IRepository[T])
    ↓
Cache Layer (Redis, ICacheService)
    ↓
Multi-Tenant Database (reference + customer DBs)
```

**Assessment:** Target layering is **necessary** for cloud requirements. Cannot adapt existing layering due to fundamental architectural differences (multi-tenancy, API-first, caching, independent scaling).

### Outcome
**Add** - Create new `src/api/` and `src/workers/` with layered architecture

**Note:** Existing `src/complira_graph/` remains unchanged. Cloud reuses:
- ✅ `db.py` (database connection logic, extended for multi-tenancy)
- ✅ `config.py` (settings pattern, extended for cloud config)
- ✅ `utils/` (HTTP client, transforms, keys - all reusable)
- ✅ `agents/` (adapted for background workers)
- ✅ `llm_agents/` (adapted for enrichment services)

---

## Change Inventory (Delta)

### Phase 0 Changes (Weeks 1-2)

| Change ID | Change Type | Current Path | Target Path | Rationale | Impacted Areas | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| **C-001** | Add | N/A | `src/api/main.py` | FastAPI application entry point | New API layer | Phase 0 |
| **C-002** | Add | N/A | `src/api/__init__.py` | API package init | API layer | Phase 0 |
| **C-003** | Add | N/A | `src/api/core/config.py` | Cloud settings (extends complira_graph.config) | Configuration | Phase 0 |
| **C-004** | Add | N/A | `src/api/core/security.py` | API key auth, customer scoping | Authentication | Phase 0 |
| **C-005** | Add | N/A | `src/api/core/cache.py` | Redis cache service, decorators | Caching | Phase 0 |
| **C-006** | Add | N/A | `src/api/core/database.py` | Multi-tenant DB routing | Database | Phase 0 |
| **C-007** | Add | N/A | `src/api/core/dependencies.py` | FastAPI dependency injection | Cross-cutting | Phase 0 |
| **C-008** | Add | N/A | `src/api/services/base.py` | BaseGraphService (DRY traversals) | Services | Phase 0 |
| **C-009** | Add | N/A | `src/api/repositories/base.py` | IRepository[T] protocol | Repositories | Phase 0 |
| **C-010** | Add | N/A | `src/api/models/requests/__init__.py` | Request models package | Models | Phase 0 |
| **C-011** | Add | N/A | `src/api/models/responses/__init__.py` | Response models package | Models | Phase 0 |
| **C-012** | Add | N/A | `src/api/models/domain/__init__.py` | Domain models package | Models | Phase 0 |
| **C-013** | Add | N/A | `src/api/v1/__init__.py` | API v1 package | Endpoints | Phase 0 |
| **C-014** | Add | N/A | `src/api/v1/router.py` | Main API router | Endpoints | Phase 0 |
| **C-015** | Add | N/A | `src/api/v1/endpoints/scan.py` | POST /v1/scan/ingest | Scan ingestion | Phase 0 |
| **C-016** | Add | N/A | `src/api/models/requests/scan.py` | ScanIngestRequest | Scan models | Phase 0 |
| **C-017** | Add | N/A | `src/api/models/responses/scan.py` | ScanIngestResponse | Scan models | Phase 0 |
| **C-018** | Add | N/A | `src/api/services/scan.py` | ScanIngestionService | Scan logic | Phase 0 |
| **C-019** | Add | N/A | `src/api/repositories/scan.py` | ScanRepository | Scan DB access | Phase 0 |
| **C-020** | Modify | `src/complira_graph/db.py` | `src/complira_graph/db.py` | Add multi-tenant routing | Database | Phase 0 |
| **C-021** | Modify | `src/complira_graph/config.py` | `src/complira_graph/config.py` | Add Redis, API auth settings | Configuration | Phase 0 |
| **C-022** | Add | N/A | `src/workers/main.py` | Worker application entry point | Workers | Phase 0 |
| **C-023** | Add | N/A | `src/workers/flows/reference_sync.py` | Reference data update workflow | Workers | Phase 0 |

### Phase 1 Changes (Weeks 3-5)

| Change ID | Change Type | Current Path | Target Path | Rationale | Impacted Areas | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| **C-024** | Add | N/A | `src/api/v1/endpoints/enrich.py` | POST /v1/enrich | Enrichment | Phase 1 |
| **C-025** | Add | N/A | `src/api/services/enrichment.py` | EnrichmentService (extends BaseGraphService) | Enrichment logic | Phase 1 |
| **C-026** | Add | N/A | `src/api/v1/endpoints/compact.py` | POST /v1/compact | Compaction | Phase 1 |
| **C-027** | Add | N/A | `src/api/services/compaction.py` | CompactionService (extends BaseGraphService) | Compaction logic | Phase 1 |
| **C-028** | Add | N/A | `src/api/v1/endpoints/mapping.py` | POST /v1/map-controls | Control mapping | Phase 1 |
| **C-029** | Add | N/A | `src/api/services/mapping.py` | ControlMappingService (extends BaseGraphService) | Mapping logic | Phase 1 |
| **C-030** | Add | N/A | `src/api/repositories/vulnerability.py` | VulnerabilityRepository | Vulnerability DB | Phase 1 |
| **C-031** | Add | N/A | `src/api/repositories/component.py` | ComponentRepository | Component DB | Phase 1 |

### Phase 2 Changes (Weeks 6-9) - Summary

| Change ID | Change Type | Target Path | Rationale | Notes |
| --- | --- | --- | --- | --- |
| **C-032 to C-039** | Add | Feature endpoints + services for blast radius, EPSS velocity, portfolio risk, defense coverage, regulatory delta | 8 new files | Phase 2 |

**Total New Files:** 50+ files across Phases 0-2

---

## Target Architecture Shape And Boundaries (Mandatory)

| Layer/Boundary | Purpose | Owns | Must Not Own | Notes |
| --- | --- | --- | --- | --- |
| **API Gateway** | Rate limiting, API key validation, request routing | HTTP concerns, auth, rate limits | Business logic, database access | Optional Kong/Traefik in Phase 2 |
| **Endpoints Layer** | HTTP request/response handling, input validation | FastAPI routes, Pydantic validation, HTTP status codes | Business logic, database queries, caching logic | Thin wrappers around services |
| **Services Layer** | Business logic, graph traversal, risk scoring | Domain logic, orchestration, service composition | HTTP concerns, SQL/AQL queries, cache keys | All extend BaseGraphService |
| **Repositories Layer** | Database access abstraction | AQL queries, DB connection management, entity mapping | Business logic, HTTP concerns, caching | Implement IRepository[T] |
| **Cache Layer** | Performance optimization via Redis | Cache keys, TTL management, Redis client | Business logic, database schema knowledge | Implement ICacheService |
| **Database Layer** | Data persistence, multi-tenant routing | ArangoDB connection, cross-DB queries, customer scoping | Business logic, cache logic, HTTP concerns | Extended from complira_graph.db |
| **Models Layer** | Data contracts and validation | Request/response schemas, domain models | Business logic, database access, HTTP routing | Pydantic models |
| **Workers Layer** | Background jobs, scheduled updates | Prefect workflows, reference data sync | HTTP concerns, customer-specific logic | Reuses agents from complira_graph |

**Boundary Enforcement:**
- ✅ Endpoints call Services only (not Repositories directly)
- ✅ Services call Repositories via interfaces (IRepository[T])
- ✅ Services call Cache via interface (ICacheService)
- ✅ Repositories call Database via interface (IDatabase)
- ✅ Workers access Database directly (no API calls)

---

## File And Module Breakdown

### Core Infrastructure (Phase 0)

| File/Module | Change Type | Layer / Boundary | Concern / Responsibility | Public APIs | Inputs/Outputs | Dependencies |
| --- | --- | --- | --- | --- | --- | --- |
| `src/api/main.py` | Add | Application | FastAPI app initialization, CORS, middleware | `app: FastAPI` | HTTP requests/responses | FastAPI, api.core.config, api.v1.router |
| `src/api/core/config.py` | Add | Configuration | Cloud settings (Redis, API auth, multi-tenant DB) | `CloudSettings` (extends Settings) | Environment variables | complira_graph.config, pydantic |
| `src/api/core/security.py` | Add | Authentication | API key validation, customer ID extraction | `get_current_customer()`, `validate_api_key()` | API key → Customer | FastAPI, database |
| `src/api/core/cache.py` | Add | Caching | Redis abstraction, cache decorators | `ICacheService`, `@cache()` decorator | Key → Value | redis-py, typing.Protocol |
| `src/api/core/database.py` | Add | Database | Multi-tenant DB routing, cross-DB query builder | `get_customer_db()`, `get_reference_db()` | customer_id → Database | arango, complira_graph.db |
| `src/api/core/dependencies.py` | Add | Cross-cutting | FastAPI dependency injection functions | `get_db()`, `get_cache()`, `get_customer()` | Dependency injection | FastAPI.Depends, core.* |

### Service Layer (DRY Foundation - Phase 0)

| File/Module | Change Type | Layer / Boundary | Concern / Responsibility | Public APIs | Inputs/Outputs | Dependencies |
| --- | --- | --- | --- | --- | --- | --- |
| **`src/api/services/base.py`** | Add | Services | **BaseGraphService - Reusable graph traversal patterns (DRY)** | `traverse()`, `shortest_path()`, `compute_coverage()`, `aggregate_risk()` | Graph queries → Results | database, cache, typing.Protocol |

**BaseGraphService Details (Critical DRY Component):**
```python
# src/api/services/base.py
from typing import Protocol, Any, List, Dict
from abc import ABC, abstractmethod

class IDatabase(Protocol):
    """Database abstraction (DIP)"""
    def aql_execute(self, query: str, bind_vars: dict) -> Any: ...

class ICacheService(Protocol):
    """Cache abstraction (DIP)"""
    def get(self, key: str) -> Any: ...
    def set(self, key: str, value: Any, ttl: int): ...

class BaseGraphService(ABC):
    """
    Reusable graph traversal patterns (DRY).
    All feature services extend this base class.

    SOLID Principles Applied:
    - SRP: Only graph traversal logic, no HTTP or cache concerns
    - OCP: Extensible via inheritance, closed for modification
    - LSP: All subclasses are substitutable
    - DIP: Depends on IDatabase and ICacheService abstractions
    """

    def __init__(self, db: IDatabase, cache: ICacheService):
        self.db = db  # DIP: depend on abstraction
        self.cache = cache  # DIP: depend on abstraction

    def traverse(
        self,
        start_collection: str,
        start_key: str,
        edge_definitions: List[str],
        max_depth: int = 4,
        customer_id: str = None
    ) -> Dict[str, Any]:
        """
        Generic graph traversal (DRY).

        Used by:
        - BlastRadiusService (CVE → CWE → CAPEC → ATT&CK → Threat Groups)
        - DefenseCoverageService (Findings → CVE → CWE → ATT&CK → Controls)
        - DependencyRiskService (Component → depends_on → CVE)
        - RemediationPlaybookService (CVE → CWE → CAPEC → ATT&CK → Controls → Reqs)
        """
        # Build AQL traversal query
        query = f"""
        FOR v, e, p IN 1..@max_depth OUTBOUND @start_doc {', '.join(edge_definitions)}
            OPTIONS {{uniqueVertices: "global"}}
            RETURN {{vertex: v, edge: e, path: p}}
        """

        # Auto-inject customer scoping if needed
        if customer_id:
            query = self._inject_customer_scope(query, customer_id)

        # Execute and return
        return self.db.aql_execute(query, {
            'start_doc': f'{start_collection}/{start_key}',
            'max_depth': max_depth
        })

    def shortest_path(
        self,
        from_collection: str,
        from_key: str,
        to_collection: str,
        to_key: str,
        via_edges: List[str]
    ) -> Dict[str, Any]:
        """Shortest path between two nodes (DRY)."""
        query = f"""
        FOR v, e IN OUTBOUND SHORTEST_PATH
            @from_doc TO @to_doc
            {', '.join(via_edges)}
            RETURN {{vertex: v, edge: e}}
        """
        return self.db.aql_execute(query, {
            'from_doc': f'{from_collection}/{from_key}',
            'to_doc': f'{to_collection}/{to_key}'
        })

    def compute_coverage(
        self,
        items: List[str],
        target_collection: str,
        mapping_edge: str
    ) -> float:
        """
        Compute coverage percentage (DRY).

        Used by:
        - ControlMappingService (coverage % per framework)
        - DefenseCoverageService (ATT&CK technique coverage)
        - RegulatoryDeltaService (framework migration impact)
        """
        query = f"""
        LET total = LENGTH(@items)
        LET covered = LENGTH(
            FOR item IN @items
                FOR v IN 1..1 OUTBOUND item {mapping_edge}
                    FILTER v._id LIKE CONCAT(@target_collection, "/%")
                    RETURN 1
        )
        RETURN (covered / total) * 100
        """
        result = self.db.aql_execute(query, {
            'items': items,
            'target_collection': target_collection
        })
        return result[0] if result else 0.0

    def aggregate_risk(
        self,
        findings: List[Dict],
        risk_weights: Dict[str, float]
    ) -> List[Dict]:
        """
        Aggregate risk scores across findings (DRY).

        Used by:
        - CompactionService (composite risk scoring)
        - PortfolioRiskService (aggregate EPSS trends)
        - DependencyRiskService (transitive risk propagation)
        """
        # Composite risk = weighted sum of KEV, EPSS, attack_paths, control_gaps
        for finding in findings:
            finding['risk_score'] = (
                (risk_weights.get('kev_multiplier', 3.0) if finding.get('kev_listed') else 0) +
                (risk_weights.get('epss_weight', 0.4) * finding.get('epss_current', 0)) +
                (risk_weights.get('attack_path_weight', 0.3) * finding.get('attack_path_count', 0)) +
                (risk_weights.get('control_gap_weight', 0.3) * finding.get('control_gap_count', 0))
            )

        # Sort by risk descending
        return sorted(findings, key=lambda x: x.get('risk_score', 0), reverse=True)

    def _inject_customer_scope(self, query: str, customer_id: str) -> str:
        """Auto-inject customer_id filter (DRY)."""
        # Insert FILTER customer_id clause after FOR statement
        return query.replace(
            'RETURN',
            f'FILTER v.customer_id == "{customer_id}" RETURN'
        )
```

### Feature Services (Phase 0-2) - All Extend BaseGraphService

| File/Module | Change Type | Layer / Boundary | Concern / Responsibility | Public APIs | Extends | Phase |
| --- | --- | --- | --- | --- | --- | --- |
| `src/api/services/scan.py` | Add | Services | Scan ingestion logic, SBOM parsing | `ingest_scan()` | BaseGraphService | P0 |
| `src/api/services/enrichment.py` | Add | Services | CVE enrichment via graph traversal | `enrich_cves()` | BaseGraphService | P1 |
| `src/api/services/compaction.py` | Add | Services | Dedupe, cluster, risk score | `compact_findings()` | BaseGraphService | P1 |
| `src/api/services/mapping.py` | Add | Services | Map findings to compliance frameworks | `map_to_controls()` | BaseGraphService | P1 |
| `src/api/services/blast_radius.py` | Add | Services | Blast radius computation | `compute_blast_radius()` | BaseGraphService | P2 |
| `src/api/services/epss_velocity.py` | Add | Services | EPSS acceleration detection | `detect_velocity()` | BaseGraphService | P2 |
| `src/api/services/portfolio_risk.py` | Add | Services | Aggregate EPSS trends | `compute_portfolio_curve()` | BaseGraphService | P2 |
| `src/api/services/defense_coverage.py` | Add | Services | ATT&CK heatmap generation | `compute_coverage_heatmap()` | BaseGraphService | P2 |
| `src/api/services/regulatory_delta.py` | Add | Services | Framework version diff | `compute_delta()` | BaseGraphService | P2 |

**DRY Benefit:** Each service is ~200 lines (not 500+) because `BaseGraphService` provides reusable traversal, coverage, and risk aggregation methods. **Estimated savings: 3000+ lines of duplicated code eliminated.**

### Scan Parser Architecture (Phase 0)

**Issue Addressed:** Stage 5 Round 1 identified that `ScanIngestionService` should not contain format-specific parsing logic (SARIF, CycloneDX). Parser logic must be extracted to dedicated classes following **SRP** (Single Responsibility Principle) and **OCP** (Open/Closed Principle).

**Design Decision:** Implement **Strategy Pattern** with parser abstraction and factory.

#### Parser Interface (DIP)

```python
# src/api/parsers/base.py
from typing import Protocol, List, Dict, Any
from abc import ABC, abstractmethod
from pydantic import BaseModel

class ParsedFinding(BaseModel):
    """Normalized finding schema (output of all parsers)."""
    cve_id: str
    severity: str
    description: str
    location: str
    tool_name: str
    scan_type: str  # "sarif" | "cyclonedx"
    raw_data: Dict[str, Any]  # Original finding for traceability

class ParsedScanData(BaseModel):
    """Parser output model."""
    tool_name: str
    tool_version: str
    scan_timestamp: str
    findings: List[ParsedFinding]
    components: List[Dict[str, Any]]  # SBOMs only
    metadata: Dict[str, Any]

class IScanParser(Protocol):
    """
    Scan parser abstraction (DIP).

    All parsers must implement this interface.
    Allows ScanIngestionService to depend on abstraction, not concrete parsers.
    """

    def parse(self, payload: Dict[str, Any]) -> ParsedScanData:
        """Parse scan payload and return normalized data."""
        ...

    def validate(self, payload: Dict[str, Any]) -> bool:
        """Validate payload conforms to expected schema."""
        ...
```

#### Base Parser (DRY)

```python
# src/api/parsers/base.py (continued)
class BaseScanParser(ABC):
    """
    Base parser with shared logic (DRY).

    SOLID Principles:
    - SRP: Only parsing logic, no business logic or DB access
    - OCP: Extensible via inheritance, closed for modification
    - Template Method Pattern: Common validation/error handling
    """

    def __init__(self):
        self.errors: List[str] = []

    @abstractmethod
    def parse(self, payload: Dict[str, Any]) -> ParsedScanData:
        """Implemented by subclasses (SARIF, CycloneDX, etc.)."""
        pass

    @abstractmethod
    def _extract_findings(self, payload: Dict[str, Any]) -> List[ParsedFinding]:
        """Extract findings from format-specific structure."""
        pass

    @abstractmethod
    def _extract_metadata(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Extract tool metadata."""
        pass

    def validate(self, payload: Dict[str, Any]) -> bool:
        """
        Common validation logic (DRY).

        Subclasses can override for format-specific validation.
        """
        if not payload:
            self.errors.append("Payload is empty")
            return False

        if not isinstance(payload, dict):
            self.errors.append("Payload must be dict/JSON object")
            return False

        return True

    def _handle_parse_error(self, error: Exception, context: str) -> None:
        """Centralized error handling (DRY)."""
        error_msg = f"{context}: {type(error).__name__} - {str(error)}"
        self.errors.append(error_msg)
        # Log to observability platform
        # logger.error(error_msg, exc_info=error)
```

#### Concrete Parsers (OCP)

```python
# src/api/parsers/sarif.py
from api.parsers.base import BaseScanParser, ParsedScanData, ParsedFinding
from typing import Dict, Any, List

class SARIFParser(BaseScanParser):
    """
    SARIF format parser (Static Analysis Results Interchange Format).

    Spec: https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html
    """

    def parse(self, payload: Dict[str, Any]) -> ParsedScanData:
        """Parse SARIF 2.1.0 payload."""
        if not self.validate(payload):
            raise ValueError(f"SARIF validation failed: {', '.join(self.errors)}")

        try:
            runs = payload.get("runs", [])
            if not runs:
                raise ValueError("SARIF payload has no runs")

            run = runs[0]  # Most tools produce single run
            tool_name = run.get("tool", {}).get("driver", {}).get("name", "Unknown")
            tool_version = run.get("tool", {}).get("driver", {}).get("version", "Unknown")

            findings = self._extract_findings(payload)
            metadata = self._extract_metadata(payload)

            return ParsedScanData(
                tool_name=tool_name,
                tool_version=tool_version,
                scan_timestamp=metadata.get("timestamp", ""),
                findings=findings,
                components=[],  # SARIF doesn't have SBOM data
                metadata=metadata
            )
        except Exception as e:
            self._handle_parse_error(e, "SARIF parsing")
            raise

    def _extract_findings(self, payload: Dict[str, Any]) -> List[ParsedFinding]:
        """Extract findings from SARIF results."""
        findings = []
        for run in payload.get("runs", []):
            for result in run.get("results", []):
                # SARIF uses ruleId (e.g., CVE-2021-44228)
                rule_id = result.get("ruleId", "")

                finding = ParsedFinding(
                    cve_id=rule_id if rule_id.startswith("CVE-") else "",
                    severity=result.get("level", "warning").upper(),
                    description=result.get("message", {}).get("text", ""),
                    location=self._extract_location(result),
                    tool_name=run.get("tool", {}).get("driver", {}).get("name", ""),
                    scan_type="sarif",
                    raw_data=result
                )
                findings.append(finding)

        return findings

    def _extract_location(self, result: Dict[str, Any]) -> str:
        """Extract file location from SARIF result."""
        locations = result.get("locations", [])
        if locations:
            physical = locations[0].get("physicalLocation", {})
            artifact = physical.get("artifactLocation", {})
            uri = artifact.get("uri", "")
            region = physical.get("region", {})
            line = region.get("startLine", 0)
            return f"{uri}:{line}" if line else uri
        return ""

    def _extract_metadata(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Extract SARIF metadata."""
        runs = payload.get("runs", [])
        if runs:
            run = runs[0]
            return {
                "timestamp": run.get("invocations", [{}])[0].get("startTimeUtc", ""),
                "tool_driver": run.get("tool", {}).get("driver", {}),
                "sarif_version": payload.get("version", "2.1.0")
            }
        return {}


# src/api/parsers/cyclonedx.py
from api.parsers.base import BaseScanParser, ParsedScanData, ParsedFinding
from typing import Dict, Any, List

class CycloneDXParser(BaseScanParser):
    """
    CycloneDX SBOM parser (Software Bill of Materials).

    Spec: https://cyclonedx.org/docs/
    """

    def parse(self, payload: Dict[str, Any]) -> ParsedScanData:
        """Parse CycloneDX 1.4/1.5 payload."""
        if not self.validate(payload):
            raise ValueError(f"CycloneDX validation failed: {', '.join(self.errors)}")

        try:
            metadata = payload.get("metadata", {})
            tool_data = metadata.get("tools", [{}])[0] if metadata.get("tools") else {}

            findings = self._extract_findings(payload)
            components = self._extract_components(payload)

            return ParsedScanData(
                tool_name=tool_data.get("name", "Unknown"),
                tool_version=tool_data.get("version", "Unknown"),
                scan_timestamp=metadata.get("timestamp", ""),
                findings=findings,
                components=components,
                metadata=self._extract_metadata(payload)
            )
        except Exception as e:
            self._handle_parse_error(e, "CycloneDX parsing")
            raise

    def _extract_findings(self, payload: Dict[str, Any]) -> List[ParsedFinding]:
        """Extract vulnerabilities from CycloneDX components."""
        findings = []
        for component in payload.get("components", []):
            for vuln in component.get("vulnerabilities", []):
                finding = ParsedFinding(
                    cve_id=vuln.get("id", ""),  # e.g., CVE-2021-44228
                    severity=self._map_severity(vuln.get("ratings", [{}])[0].get("severity", "")),
                    description=vuln.get("description", ""),
                    location=f"{component.get('name', '')}@{component.get('version', '')}",
                    tool_name=payload.get("metadata", {}).get("tools", [{}])[0].get("name", ""),
                    scan_type="cyclonedx",
                    raw_data=vuln
                )
                findings.append(finding)

        return findings

    def _extract_components(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract SBOM components."""
        return payload.get("components", [])

    def _extract_metadata(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Extract CycloneDX metadata."""
        return {
            "bom_format": payload.get("bomFormat", "CycloneDX"),
            "spec_version": payload.get("specVersion", "1.4"),
            "serial_number": payload.get("serialNumber", ""),
            "metadata": payload.get("metadata", {})
        }

    def _map_severity(self, cyclonedx_severity: str) -> str:
        """Map CycloneDX severity to normalized severity."""
        mapping = {
            "critical": "CRITICAL",
            "high": "HIGH",
            "medium": "MEDIUM",
            "low": "LOW",
            "info": "INFO",
            "none": "NONE"
        }
        return mapping.get(cyclonedx_severity.lower(), "UNKNOWN")
```

#### Parser Factory (OCP)

```python
# src/api/parsers/factory.py
from typing import Dict, Any
from api.parsers.base import IScanParser
from api.parsers.sarif import SARIFParser
from api.parsers.cyclonedx import CycloneDXParser

class ParserFactory:
    """
    Factory for creating appropriate parser based on scan format (OCP).

    To add new parser (e.g., OSV, VEX):
    1. Implement new parser class extending BaseScanParser
    2. Register in _parsers dict
    3. No changes needed in ScanIngestionService (OCP)
    """

    _parsers: Dict[str, type] = {
        "sarif": SARIFParser,
        "cyclonedx": CycloneDXParser,
        # Future: "osv": OSVParser, "vex": VEXParser
    }

    @classmethod
    def get_parser(cls, format: str) -> IScanParser:
        """Get parser for specified format."""
        parser_class = cls._parsers.get(format.lower())
        if not parser_class:
            raise ValueError(f"Unsupported scan format: {format}. Supported: {list(cls._parsers.keys())}")

        return parser_class()

    @classmethod
    def register_parser(cls, format: str, parser_class: type):
        """Register custom parser (extensibility)."""
        cls._parsers[format.lower()] = parser_class
```

#### Updated ScanIngestionService (Using Parsers)

```python
# src/api/services/scan.py (revised)
from api.services.base import BaseGraphService
from api.parsers.factory import ParserFactory
from api.models.requests.scan import ScanIngestRequest
from typing import Dict, Any

class ScanIngestionService(BaseGraphService):
    """
    Scan ingestion service (SRP: business logic only, no parsing).

    Delegates parsing to parser classes (DIP: depends on IScanParser abstraction).
    """

    async def ingest_scan(
        self,
        customer_id: str,
        scan_request: ScanIngestRequest
    ) -> Dict[str, Any]:
        """
        Ingest scan results.

        Flow:
        1. Get appropriate parser via factory
        2. Parse payload (delegation to parser)
        3. Create scan_session document
        4. Normalize and store findings
        5. Extract and store components (SBOM)
        6. Create edges
        """
        # Step 1: Get parser (OCP - factory handles format selection)
        parser = ParserFactory.get_parser(scan_request.format)

        # Step 2: Parse payload (SRP - parser handles format-specific logic)
        parsed_data = parser.parse(scan_request.payload)

        # Step 3-6: Business logic (create session, findings, edges)
        scan_session_id = await self._create_scan_session(
            customer_id=customer_id,
            tool_name=parsed_data.tool_name,
            tool_version=parsed_data.tool_version,
            scan_timestamp=parsed_data.scan_timestamp
        )

        findings_created = await self._store_findings(
            customer_id=customer_id,
            scan_session_id=scan_session_id,
            findings=parsed_data.findings
        )

        if parsed_data.components:
            await self._store_components(
                customer_id=customer_id,
                scan_session_id=scan_session_id,
                components=parsed_data.components
            )

        await self._create_edges(
            customer_id=customer_id,
            scan_session_id=scan_session_id,
            findings=parsed_data.findings
        )

        return {
            "scan_session_id": scan_session_id,
            "findings_count": len(findings_created),
            "components_count": len(parsed_data.components)
        }
```

#### Change Inventory Updates

| Change ID | Type | Path | Description | Phase |
|---|---|---|---|
| **C-018a** | Add | `src/api/parsers/__init__.py` | Parser package | P0 |
| **C-018b** | Add | `src/api/parsers/base.py` | IScanParser, BaseScanParser, ParsedScanData models | P0 |
| **C-018c** | Add | `src/api/parsers/sarif.py` | SARIFParser implementation | P0 |
| **C-018d** | Add | `src/api/parsers/cyclonedx.py` | CycloneDXParser implementation | P0 |
| **C-018e** | Add | `src/api/parsers/factory.py` | ParserFactory | P0 |
| **C-018** | Modify | `src/api/services/scan.py` | ScanIngestionService uses ParserFactory (no inline parsing) | P0 |

#### SOLID Compliance

| Principle | How Applied |
|---|---|
| **SRP** | Each parser handles one format only; service handles business logic only |
| **OCP** | Add new parsers by extending BaseScanParser, no changes to service/factory |
| **LSP** | All parsers substitutable via IScanParser interface |
| **ISP** | IScanParser interface is minimal (parse, validate only) |
| **DIP** | ScanIngestionService depends on IScanParser abstraction, not concrete parsers |

#### DRY Benefit

- Common validation, error handling, metadata extraction in `BaseScanParser`
- Estimated 400+ lines of duplicated code eliminated between SARIF/CycloneDX parsers
- Future parsers (OSV, VEX) inherit all shared logic

### Repository Layer (Phase 0-1)

| File/Module | Change Type | Layer / Boundary | Concern / Responsibility | Public APIs | Implements | Dependencies |
| --- | --- | --- | --- | --- | --- | --- |
| `src/api/repositories/base.py` | Add | Repositories | IRepository[T] protocol | `get()`, `list()`, `create()`, `update()`, `delete()` | Protocol | typing.Protocol |
| `src/api/repositories/scan.py` | Add | Repositories | Scan session DB access | CRUD for scan_sessions, scan_findings | IRepository[ScanSession] | database, base |
| `src/api/repositories/vulnerability.py` | Add | Repositories | Vulnerability DB access | CRUD for vulnerabilities (read-only mostly) | IRepository[Vulnerability] | database, base |
| `src/api/repositories/component.py` | Add | Repositories | Component DB access | CRUD for customer components | IRepository[Component] | database, base |

### Endpoints Layer (Phase 0-2)

| File/Module | Change Type | Layer / Boundary | Concern / Responsibility | Public APIs | Dependencies | Phase |
| --- | --- | --- | --- | --- | --- | --- |
| `src/api/v1/endpoints/scan.py` | Add | Endpoints | POST /v1/scan/ingest HTTP handler | `ingest_scan_endpoint()` | services.scan, models, dependencies | P0 |
| `src/api/v1/endpoints/enrich.py` | Add | Endpoints | POST /v1/enrich HTTP handler | `enrich_endpoint()` | services.enrichment, models, dependencies | P1 |
| `src/api/v1/endpoints/compact.py` | Add | Endpoints | POST /v1/compact HTTP handler | `compact_endpoint()` | services.compaction, models, dependencies | P1 |
| `src/api/v1/endpoints/mapping.py` | Add | Endpoints | POST /v1/map-controls HTTP handler | `map_controls_endpoint()` | services.mapping, models, dependencies | P1 |
| `src/api/v1/endpoints/blast_radius.py` | Add | Endpoints | POST /v1/blast-radius HTTP handler | `blast_radius_endpoint()` | services.blast_radius, models, dependencies | P2 |

**Endpoint Pattern (DRY via FastAPI Dependencies):**
```python
# src/api/v1/endpoints/scan.py
from fastapi import APIRouter, Depends, HTTPException
from api.models.requests.scan import ScanIngestRequest
from api.models.responses.scan import ScanIngestResponse
from api.services.scan import ScanIngestionService
from api.core.dependencies import get_current_customer, get_scan_service

router = APIRouter(prefix="/scan", tags=["scan"])

@router.post("/ingest", response_model=ScanIngestResponse)
async def ingest_scan_endpoint(
    request: ScanIngestRequest,
    customer: Customer = Depends(get_current_customer),  # Auto customer scoping (AD-004)
    service: ScanIngestionService = Depends(get_scan_service)  # Dependency injection (DIP)
):
    """
    POST /v1/scan/ingest

    Thin endpoint (SRP): Only HTTP concerns.
    Business logic delegated to ScanIngestionService.
    """
    try:
        result = await service.ingest_scan(
            customer_id=customer.id,
            scan_data=request
        )
        return ScanIngestResponse(
            success=True,
            data=result,
            metadata={'cache_hit': False}
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
```

**DRY Benefits:**
1. Customer scoping automatic via `Depends(get_current_customer)` - no manual checks
2. Service injection via `Depends(get_scan_service)` - easy mocking for tests
3. Standard error handling pattern reused across all endpoints
4. Response model `APIResponse[T]` reused (generic type)

### Workers Layer (Phase 0-1)

| File/Module | Change Type | Layer / Boundary | Concern / Responsibility | Public APIs | Dependencies | Phase |
| --- | --- | --- | --- | --- | --- | --- |
| `src/workers/main.py` | Add | Workers | Worker application entry point | `start_worker()` | Prefect, flows | P0 |
| `src/workers/flows/reference_sync.py` | Add | Workers | Scheduled reference data updates | `sync_reference_data()` (Prefect flow) | complira_graph.agents | P0 |
| `src/workers/flows/epss_velocity.py` | Add | Workers | Daily EPSS velocity computation | `compute_epss_velocity()` (Prefect flow) | database, epss_history | P2 |
| `src/workers/flows/benchmark_agg.py` | Add | Workers | Weekly benchmark aggregation | `aggregate_benchmarks()` (Prefect flow) | database, scan_findings | P4 |

---

## Layer-Appropriate Separation Of Concerns Check

✅ **Non-UI Scope (Backend/Service/Worker):** Responsibility is clear at **file/module/service boundaries**

### Separation Verification

| Layer | File/Module | Responsibility | Passes SRP? | Notes |
| --- | --- | --- | --- | --- |
| **Endpoints** | `src/api/v1/endpoints/scan.py` | HTTP request/response handling only | ✅ Yes | No business logic, delegates to service |
| **Endpoints** | `src/api/v1/endpoints/enrich.py` | HTTP request/response handling only | ✅ Yes | No database access, delegates to service |
| **Services** | `src/api/services/base.py` | Graph traversal patterns only | ✅ Yes | No HTTP concerns, no cache keys |
| **Services** | `src/api/services/enrichment.py` | Enrichment business logic only | ✅ Yes | No HTTP, no SQL, uses BaseGraphService |
| **Services** | `src/api/services/scan.py` | Scan ingestion logic only | ✅ Yes | No HTTP, no DB access, uses Repository |
| **Repositories** | `src/api/repositories/scan.py` | Scan DB access only | ✅ Yes | No business logic, pure CRUD |
| **Repositories** | `src/api/repositories/vulnerability.py` | Vulnerability DB access only | ✅ Yes | No HTTP, no caching, pure queries |
| **Cache** | `src/api/core/cache.py` | Redis caching only | ✅ Yes | No business logic, no DB schema knowledge |
| **Database** | `src/api/core/database.py` | Multi-tenant DB routing only | ✅ Yes | No business logic, no HTTP concerns |
| **Config** | `src/api/core/config.py` | Settings management only | ✅ Yes | No business logic, pure configuration |

**Conclusion:** ✅ All layers have clear, single responsibilities. No violations detected.

---

## Naming Decisions (Natural And Implementation-Friendly)

| Item Type | Current Name | Proposed Name | Reason | Notes |
| --- | --- | --- | --- | --- |
| **Service** | N/A (new) | `BaseGraphService` | Clear, indicates base class for graph operations | Natural, not `GraphServiceBase` |
| **Service** | N/A (new) | `EnrichmentService` | Clear domain concept (enrichment) | Not `CVEEnricher` (less clear) |
| **Service** | N/A (new) | `BlastRadiusService` | Matches feature name from requirements | Clear purpose |
| **Endpoint** | N/A (new) | `/v1/scan/ingest` | RESTful, clear action (ingest) | Not `/v1/scans/create` (less specific) |
| **Endpoint** | N/A (new) | `/v1/enrich` | Simple, clear (enrich vulnerabilities) | Not `/v1/vulnerabilities/enrich` (too verbose) |
| **Endpoint** | N/A (new) | `/v1/blast-radius` | Matches feature name | Kebab-case for URLs |
| **Model** | N/A (new) | `ScanIngestRequest` | Clear request model for scan ingestion | Pattern: `{Feature}{Action}Request` |
| **Model** | N/A (new) | `EnrichmentResponse` | Clear response model | Pattern: `{Feature}Response` |
| **Model** | N/A (new) | `APIResponse[T]` | Generic response wrapper | Type parameter T for flexibility |
| **Repository** | N/A (new) | `VulnerabilityRepository` | Clear entity type | Not `VulnRepo` (abbreviations hurt clarity) |
| **Repository** | N/A (new) | `ComponentRepository` | Clear entity type | Consistent with VulnerabilityRepository |
| **Interface** | N/A (new) | `IRepository[T]` | Generic repository interface | `I` prefix for interfaces (Python convention) |
| **Interface** | N/A (new) | `ICacheService` | Cache service interface | `I` prefix for interfaces |
| **Interface** | N/A (new) | `IDatabase` | Database interface | `I` prefix for interfaces |
| **Decorator** | N/A (new) | `@cache(ttl=3600)` | Clear caching decorator | Simple, declarative |
| **Dependency** | N/A (new) | `get_current_customer()` | Returns Customer from API key | Clear intent |
| **Dependency** | N/A (new) | `get_db()` | Returns database connection | Short, common pattern |
| **Dependency** | N/A (new) | `get_cache()` | Returns cache service | Consistent with `get_db()` |

**Naming Principles Applied:**
1. **Natural:** "EnrichmentService" not "CVEEnricher"
2. **Unsurprising:** "BaseGraphService" for base class (not "GraphServiceBase")
3. **Consistent:** All services end with "Service", all repositories end with "Repository"
4. **No abbreviations:** "VulnerabilityRepository" not "VulnRepo"
5. **Clear purpose:** "BlastRadiusService" immediately conveys feature

---

## Naming Drift Check (Mandatory)

**N/A** - All new code, no existing names to drift from.

For future: As scope expands, check if "EnrichmentService" still matches its responsibility. If it starts handling compaction too, rename to "EnrichmentAndCompactionService" or split into separate services (SRP).

---

## Existing-Structure Bias Check (Mandatory)

| Candidate Area | Current-File-Layout Bias Risk | Architecture-First Alternative | Decision | Why |
| --- | --- | --- | --- | --- |
| **API Structure** | Low - `src/api/` is empty | Design layers first (endpoints/services/repos) | Change (Add) | No existing structure to bias |
| **Service Organization** | Low | Organize by feature (enrichment.py, blast_radius.py) not by layer depth | Keep | Feature-based organization is clearest |
| **Repository Naming** | Low | Name by entity (VulnerabilityRepository) not by database (ArangoVulnerabilityRepository) | Keep | Entity-based is more abstract (DIP) |
| **Worker Structure** | Low | Separate from API (`src/workers/` not `src/api/workers/`) | Change (Add) | Independent scaling requires separate structure |

**Conclusion:** ✅ No existing-structure bias detected. Architecture designed from target requirements, not adapted from current file layout.

---

## Anti-Hack Check (Mandatory)

| Candidate Change | Shortcut/Hack Risk | Proper Structural Fix | Decision | Notes |
| --- | --- | --- | --- | --- |
| **Customer Scoping** | High - Manual `if customer_id == ...` in every endpoint | FastAPI dependency injection (`Depends(get_current_customer)`) | Use Proper Fix | Eliminates duplication (DRY) |
| **Caching** | High - Manual Redis get/set in every service | Caching decorator (`@cache(ttl=3600)`) | Use Proper Fix | Declarative, reusable (DRY) |
| **Graph Traversals** | High - Copy-paste AQL queries across services | `BaseGraphService.traverse()` method | Use Proper Fix | Eliminates 3000+ lines of duplication |
| **Error Handling** | Medium - Try-catch in every endpoint | FastAPI exception handlers + standard response model | Use Proper Fix | Centralized error handling |
| **Database Access** | High - Direct ArangoDB calls in services | Repository pattern (`IRepository[T]`) | Use Proper Fix | Testability, abstraction (DIP) |

**Rule Applied:** A functionally working local fix is invalid if it degrades layering or responsibility boundaries.

**Example Violation (Avoided):**
```python
# BAD (Hack):
@router.post("/enrich")
async def enrich(request: EnrichRequest):
    # Direct DB access in endpoint
    db = get_arango_client()
    query = "FOR cve IN vulnerabilities..."
    result = db.aql.execute(query)

    # Manual caching
    redis = get_redis()
    redis.set(f"enrich:{request.cve_id}", result, ex=3600)

    return result

# GOOD (Proper Structure):
@router.post("/enrich")
async def enrich(
    request: EnrichRequest,
    customer: Customer = Depends(get_current_customer),  # DRY: Auto customer scope
    service: EnrichmentService = Depends(get_enrichment_service)  # DIP: Depend on abstraction
):
    # Delegate to service (SRP)
    return await service.enrich_cves(request.cve_ids, customer.id)
```

**Conclusion:** ✅ No hacks/shortcuts. All cross-cutting concerns handled via proper abstractions (DIP, DRY).

---

## Dependency Flow And Cross-Reference Risk

### Allowed Dependency Direction (Mandatory)

**Strict Layered Architecture:**
```
Endpoints → Services → Repositories → Database
            ↓           ↓
          Cache ←───────┘
```

**Rules:**
1. Endpoints MAY call Services, MUST NOT call Repositories directly
2. Services MAY call Repositories and Cache, MUST NOT call Endpoints
3. Repositories MAY call Database, MUST NOT call Services or Cache
4. Cache MAY call Database (for cache-aside pattern), MUST NOT call Services
5. Workers MAY call Database directly (no API calls), MAY reuse Agents

**Temporary Boundary Violations:** None allowed. Architecture is clean-slate.

**Cleanup Deadline:** N/A - no violations expected in initial implementation.

### Dependency Matrix

| Module | Upstream Dependencies | Downstream Dependents | Cross-Reference Risk | Mitigation |
| --- | --- | --- | --- | --- |
| `api.v1.endpoints.scan` | services.scan, models, dependencies | None (leaf) | Low | Endpoints are leaves, never imported by other layers |
| `api.services.scan` | repositories.scan, base.BaseGraphService | endpoints.scan | Low | Services depend on abstractions (IRepository) |
| `api.services.base` | database (IDatabase), cache (ICacheService) | All feature services | Low | Base depends on protocols, not concretions |
| `api.repositories.scan` | database, base.IRepository | services.scan | Low | Repositories are isolated, no cross-references |
| `api.core.cache` | redis, typing.Protocol | All services | Low | Cache is interface, swappable implementation |
| `api.core.database` | arango, complira_graph.db | All repositories | Low | Database abstraction, no business logic |

**Conclusion:** ✅ No circular dependencies. All dependencies flow downward (Endpoints → Services → Repositories → Database). No cross-reference risk detected.

---

## Decommission / Cleanup Plan

**N/A** - No legacy code to remove. This is net-new architecture alongside existing local application.

**Future Cleanup (Post-Migration):**
- If/when customers migrate from local to cloud, local CLI commands can be deprecated
- Timeline: Not in scope for initial implementation
- Strategy: Gradual deprecation with warnings, not immediate removal

---

## Data Models (If Needed)

### Request Models (Pydantic)

```python
# src/api/models/requests/scan.py
from pydantic import BaseModel, Field
from typing import Literal

class ScanIngestRequest(BaseModel):
    """Request model for POST /v1/scan/ingest"""
    format: Literal["sarif", "cyclonedx", "csv", "json"] = Field(
        ..., description="Scanner output format"
    )
    scan_type: Literal["sast", "dast", "sca", "container", "sbom"] = Field(
        ..., description="Type of scan"
    )
    payload: str = Field(..., description="Scanner output (JSON/XML string)")
    metadata: dict = Field(
        default_factory=dict,
        description="Scan metadata (repo, commit_sha, branch, etc.)"
    )
```

### Response Models (Pydantic)

```python
# src/api/models/responses/common.py
from pydantic import BaseModel, Generic, TypeVar
from typing import Optional

T = TypeVar('T')

class ResponseMetadata(BaseModel):
    """Standard response metadata"""
    cache_hit: bool = False
    execution_time_ms: Optional[float] = None
    api_version: str = "v1"

class APIResponse(BaseModel, Generic[T]):
    """
    Generic response wrapper (DRY).
    Used by all endpoints for consistent response format.
    """
    success: bool
    data: Optional[T] = None
    error: Optional[str] = None
    metadata: ResponseMetadata = ResponseMetadata()
```

### Domain Models

```python
# src/api/models/domain/customer.py
from pydantic import BaseModel

class Customer(BaseModel):
    """Customer domain model"""
    id: str
    name: str
    api_key_hash: str
    database_name: str  # e.g., "complira_customer_001"
    tier: str = "free"  # free, pro, enterprise
```

---

## Error Handling And Edge Cases

### Centralized Error Handling (DRY)

```python
# src/api/main.py
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI()

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Centralized HTTP exception handler"""
    return JSONResponse(
        status_code=exc.status_code,
        content=APIResponse(
            success=False,
            error=exc.detail,
            metadata=ResponseMetadata()
        ).dict()
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Catch-all for unexpected errors"""
    logger.error("Unhandled exception", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content=APIResponse(
            success=False,
            error="Internal server error",
            metadata=ResponseMetadata()
        ).dict()
    )
```

### Edge Cases

| Edge Case | Handling Strategy | Implementation |
| --- | --- | --- |
| **Customer Not Found** | Return 401 Unauthorized | `get_current_customer()` raises HTTPException(401) |
| **Database Connection Failure** | Return 503 Service Unavailable | Database client retry logic + circuit breaker |
| **Cache Miss** | Fall through to database | Cache-aside pattern in services |
| **Invalid API Key** | Return 401 Unauthorized | `validate_api_key()` raises HTTPException(401) |
| **Rate Limit Exceeded** | Return 429 Too Many Requests | API gateway middleware (Phase 2) or FastAPI middleware (Phase 0) |
| **Malformed Request** | Return 400 Bad Request | Pydantic validation raises HTTPException(400) automatically |
| **Empty Graph Traversal** | Return empty result (not error) | Services return `{'nodes': [], 'edges': []}` |
| **Cross-DB Query Failure** | Return 500 Internal Server Error | Log error, return generic error to client |

---

## Use-Case Coverage Matrix (Design Gate)

### Phase 0 Coverage

| use_case_id | Requirement | Use Case | Primary Path Covered | Fallback Path Covered | Error Path Covered | Runtime Call Stack Section |
| --- | --- | --- | --- | --- | --- | --- |
| **UC-001** | REQ-001 | Multi-tenant database setup | Yes | N/A | Yes (connection failure) | Section 1: Database Setup |
| **UC-002** | REQ-002 | API authentication & customer scoping | Yes | N/A | Yes (invalid API key) | Section 2: Authentication |
| **UC-003** | REQ-003 | Redis caching layer | Yes | Yes (cache miss fallback) | Yes (Redis connection failure) | Section 3: Caching |
| **UC-004** | REQ-004 | Scan ingestion API | Yes | Yes (format detection fallback) | Yes (malformed SARIF) | Section 4: Scan Ingestion |

### Phase 1 Coverage

| use_case_id | Requirement | Use Case | Primary Path Covered | Fallback Path Covered | Error Path Covered | Runtime Call Stack Section |
| --- | --- | --- | --- | --- | --- | --- |
| **UC-005** | REQ-005 | Vulnerability enrichment | Yes | Yes (cache hit path) | Yes (CVE not found) | Section 5: Enrichment |
| **UC-006** | REQ-006 | Finding compaction | Yes | Yes (no aliases found) | Yes (empty findings list) | Section 6: Compaction |
| **UC-007** | REQ-007 | Control mapping | Yes | Yes (framework not supported) | Yes (CVE has no CWE) | Section 7: Control Mapping |

### Phase 2 Coverage

| use_case_id | Requirement | Use Case | Primary Path Covered | Fallback Path Covered | Error Path Covered | Runtime Call Stack Section |
| --- | --- | --- | --- | --- | --- | --- |
| **UC-008** | REQ-008 | Blast radius simulation | Yes | Yes (max depth reached) | Yes (start CVE not found) | Section 8: Blast Radius |
| **UC-009** | REQ-009 | EPSS velocity detection | Yes | Yes (insufficient history) | Yes (EPSS data missing) | Section 9: EPSS Velocity |
| **UC-010** | REQ-010 | Portfolio risk curves | Yes | Yes (single data point) | Yes (no customer components) | Section 10: Portfolio Risk |
| **UC-011** | REQ-011 | Defense coverage heatmap | Yes | Yes (no techniques found) | Yes (ATT&CK data missing) | Section 11: Defense Coverage |
| **UC-012** | REQ-012 | Regulatory delta analysis | Yes | Yes (no changes detected) | Yes (framework version not found) | Section 12: Regulatory Delta |

**Coverage Assessment:** ✅ All 12 use cases have primary, fallback, and error paths defined.

---

## Performance / Security Considerations

### Performance Optimizations

1. **Caching Strategy (AD-005):**
   - Reference data: 6-hour TTL (CVE details, NIST controls, etc.)
   - Customer data: 1-hour TTL (scan sessions, findings)
   - Target: > 70% cache hit ratio
   - Measurement: Prometheus metrics on cache hits/misses

2. **Database Indexing:**
   ```python
   # Phase 0: Create indexes for customer-scoped queries
   db.collection('components').add_persistent_index(['customer_id', 'cpe'], unique=False)
   db.collection('scan_findings').add_persistent_index(['customer_id', 'scan_session_id'], unique=False)
   db.collection('scan_findings').add_persistent_index(['customer_id', 'cve_id'], unique=False)
   ```

3. **Named Graphs (Phase 1):**
   ```python
   # Optimize traversals with named graph
   db._graphs.save({
       'name': 'blast_radius_graph',
       'edgeDefinitions': [
           {'collection': 'has_weakness', 'from': ['vulnerabilities'], 'to': ['weaknesses']},
           {'collection': 'capec_relates_to_cwe', 'from': ['attack_patterns'], 'to': ['weaknesses']},
           # ... more edges
       ]
   })
   ```

4. **Parallel Processing (Phase 2):**
   - Enrich 100 CVEs in parallel (asyncio)
   - Batch database queries (bulk inserts)

### Security Considerations

1. **API Key Authentication (AD-006):**
   - API keys hashed with bcrypt
   - Stored in `customer_profiles` collection
   - Rate limiting per API key (100 req/min initially)

2. **Customer Data Isolation (AD-001):**
   - Database-per-customer architecture
   - Automatic customer_id injection in all queries
   - Cross-customer data access impossible (separate DBs)

3. **Input Validation:**
   - Pydantic models validate all request inputs
   - Sanitize user-provided strings before AQL queries
   - Max payload size limits (10MB for SBOM, 50MB for SARIF)

4. **Secrets Management:**
   - Environment variables for API keys, DB credentials
   - Never log secrets (structlog filtering)
   - Rotate API keys on demand

---

## Migration / Rollout (If Needed)

### Phase 0 Rollout (Weeks 1-2)

**Week 1: Infrastructure Setup**
1. Deploy ArangoDB cloud cluster
2. Create `complira_reference` database
3. Export local database: `arangodump --output-directory ./backup`
4. Import to cloud: `arangorestore --input-directory ./backup --server.endpoint <cloud-url>`
5. Verify document counts match local
6. Create test customer database: `complira_customer_test`
7. Deploy Redis cluster

**Week 2: API Deployment**
1. Deploy FastAPI application (Docker + ECS/EKS)
2. Deploy Workers (separate Docker container)
3. Configure API gateway (or FastAPI middleware)
4. Create test customer account with API key
5. Integration test: POST /v1/scan/ingest with test SARIF
6. Verify scan appears in test customer database
7. Keep local database as backup (30 days)

### Rollback Plan

If cloud deployment fails:
1. Keep local application running (unchanged)
2. Cloud is parallel system, no impact on existing workflows
3. Debug cloud issues without downtime
4. Retry deployment after fixes

---

## Change Traceability To Implementation Plan

| Change ID | Implementation Plan Task(s) | Verification (Unit/Integration/API/E2E) | Status |
| --- | --- | --- | --- |
| **C-001 to C-007** | Core infrastructure setup | Unit: Config loading, Auth validation | Planned (P0) |
| **C-008** | Implement BaseGraphService | Unit: traverse(), shortest_path(), compute_coverage() | Planned (P0) |
| **C-009** | Implement IRepository[T] | Unit: Protocol compliance | Planned (P0) |
| **C-010 to C-012** | Implement request/response models | Unit: Pydantic validation | Planned (P0) |
| **C-013 to C-019** | Implement scan ingestion endpoint + service | API/E2E: POST /v1/scan/ingest with SARIF | Planned (P0) |
| **C-020 to C-021** | Extend db.py and config.py | Integration: Multi-tenant DB access | Planned (P0) |
| **C-022 to C-023** | Implement workers | Integration: Prefect flow execution | Planned (P0) |
| **C-024 to C-031** | Implement enrichment, compaction, mapping | API/E2E: Full pipeline test | Planned (P1) |

---

## Design Feedback Loop Notes (From Review/Implementation)

| Date | Trigger | Classification | Design Smell | Requirements Updated? | Design Update Applied | Status |
| --- | --- | --- | --- | --- | --- | --- |
| TBD | Stage 5 Review Round 1 | N/A | TBD | No | N/A | Pending |

---

## Open Questions

1. **Q:** Cloud provider decision (AWS / GCP / Azure)?
   - **Recommendation:** AWS (mature managed services: ElastiCache, S3, ECS/EKS)
   - **Decision needed:** Phase 0 Week 1

2. **Q:** ArangoDB deployment model (self-managed / Oasis)?
   - **Recommendation:** Self-managed on EC2/EKS (cost control, can scale customer DBs independently)
   - **Decision needed:** Phase 0 Week 1

3. **Q:** Initial customer onboarding process?
   - **Recommendation:** Manual for Phase 0 (admin script to create customer DB + API key)
   - **Decision:** Automated onboarding deferred to Phase 3

4. **Q:** Monitoring and observability stack?
   - **Recommendation:** Prometheus + Grafana (metrics), Structlog (logging)
   - **Decision:** Phase 0 uses structlog only; Prometheus added in Phase 1

---

## Summary

This proposed design implements a cloud-native multi-tenant SaaS platform following strict DRY and SOLID principles:

**DRY Achievements:**
- ✅ `BaseGraphService` eliminates 3000+ lines of duplicated graph traversal logic
- ✅ `@cache()` decorator eliminates manual Redis get/set across services
- ✅ `Depends(get_current_customer)` eliminates manual customer scoping checks
- ✅ `APIResponse[T]` generic model eliminates response duplication
- ✅ `IRepository[T]` protocol eliminates repository boilerplate

**SOLID Achievements:**
- ✅ **SRP:** Clear layer separation (Endpoints/Services/Repositories/Cache/Database)
- ✅ **OCP:** `BaseGraphService` extensible without modification
- ✅ **LSP:** All services substitutable via protocol interfaces
- ✅ **ISP:** Specific interfaces (ITraversalService, ICacheService, not generic IService)
- ✅ **DIP:** Services depend on abstractions (IDatabase, ICacheService) not concretions

**Architecture Decisions Applied:**
- ✅ AD-001: Database-per-customer (reference + customer DBs)
- ✅ AD-002: API and Workers decoupled (separate processes)
- ✅ AD-003: BaseGraphService for reusable patterns
- ✅ AD-004: Automatic customer scoping
- ✅ AD-005: Redis caching strategy
- ✅ AD-006: API key authentication
- ✅ AD-007: Strict SOLID enforcement

**Next Steps:** Stage 4 (Future-State Runtime Call Stacks) → Stage 5 (Review Gate) → Stage 6 (Implementation)
