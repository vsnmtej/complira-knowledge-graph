# Investigation Notes: Cloud SaaS Architecture

**Ticket:** cloud-saas-architecture
**Date:** 2026-03-02
**Status:** In Progress

---

## Executive Summary

**Current Architecture:** Local Python CLI application with ArangoDB graph database (335K docs, 1.97M edges). Ingestion agents fetch reference data (NVD, MITRE, NIST), LLM agents enrich vulnerabilities, and CLI commands expose graph queries.

**Target Architecture:** Cloud-hosted multi-tenant SaaS platform with FastAPI REST API, separated reference and customer databases, Redis caching, and 13 endpoints implementing advanced security intelligence features.

**Key Finding:** Existing codebase has well-structured base classes (`BaseIngestionAgent`, `BaseLLMAgent`) and utilities that can be adapted for cloud services. The `src/api/` directory structure exists but is empty - clean slate for implementation.

---

## Sources Consulted

### Local Files Examined
1. `src/complira_graph/db.py` - Database schema and collections
2. `src/complira_graph/config.py` - Pydantic settings configuration
3. `src/complira_graph/agents/base.py` - Base ingestion agent pattern
4. `src/complira_graph/llm_agents/` - LLM enrichment agents (5 agents)
5. `src/complira_graph/utils/` - Shared utilities (HTTP client, keys, transforms)
6. `src/complira_graph/models.py` - Pydantic models
7. `src/complira_graph/queries/compliance.py` - Query abstractions
8. `src/complira_graph/orchestrator/` - Prefect workflow orchestration
9. `references/cloud-implementation-plan.md` - Implementation plan document

### External References
1. FastAPI documentation (https://fastapi.tiangolo.com/) - For REST API patterns
2. ArangoDB multi-tenancy docs - For database separation strategy
3. Redis caching patterns - For performance optimization
4. OAuth2/API key authentication patterns

---

## Current Architecture Analysis

### Directory Structure
```
src/
├── api/                         # EXISTS but EMPTY - target for cloud API
│   ├── core/                    # Config, security, cache
│   ├── models/                  # Request/response models
│   ├── services/                # Business logic services
│   ├── v1/                      # API endpoints
│   └── workers/                 # Background workers
└── complira_graph/              # EXISTING - local application
    ├── agents/                  # 24 ingestion agents
    ├── llm_agents/              # 5 LLM enrichment agents
    ├── utils/                   # Shared utilities
    ├── models.py                # Pydantic models
    ├── db.py                    # Database schema
    ├── config.py                # Settings
    ├── queries/                 # Query abstractions
    ├── orchestrator/            # Prefect workflows
    └── monitoring/              # Logging/metrics
```

### Database Schema (Current State)

**Document Collections (27 total):**
- **Reference Data (populated):**
  - `vulnerabilities` (335K docs) - CVEs from NVD/GHSA
  - `attack_techniques` (900+ docs) - MITRE ATT&CK
  - `weaknesses` (937 docs) - CWE
  - `attack_patterns` (559 docs) - CAPEC
  - `oscal_controls` (1.2K docs) - NIST 800-53
  - `threat_groups` (150+ docs) - APT groups
  - `epss_history` (317K docs) - EPSS scores
  - `kev_entries` (1.2K docs) - CISA KEV
  - `d3fend_techniques` (418 docs) - D3FEND defenses
  - `licenses` (727 docs) - SPDX licenses
  - `regulatory_requirements` (populated) - Compliance reqs

- **Customer Data (empty):**
  - `components` (0 docs) - Will hold customer SBOMs
  - `cpe_entries` (0 docs) - Will hold CPE matches
  - `scan_sessions` (doesn't exist yet)
  - `scan_findings` (doesn't exist yet)
  - `customer_profiles` (doesn't exist yet)

**Edge Collections (44 total):**
- **Populated:**
  - `aliases` (634K edges) - CVE cross-references
  - `child_of` (1.77K edges) - CWE hierarchy
  - `has_weakness` (populated) - CVE → CWE
  - `can_precede` (286 edges) - ATT&CK technique sequencing
  - `exploited_in_wild` (populated) - CVE → KEV

- **Empty (need population):**
  - `affects` (0 edges) - CVE → Component
  - `matched_by_cpe` (0 edges) - Component → CPE
  - `depends_on` (0 edges) - Component dependency tree
  - `technique_mitigated_by_control` (0 edges) - ATT&CK → NIST
  - `capec_maps_to_attack` (0 edges) - CAPEC → ATT&CK
  - `d3fend_counters_technique` (0 edges) - D3FEND → ATT&CK

### Configuration System

**Current (`src/complira_graph/config.py`):**
- Uses Pydantic Settings with `.env` file
- Database connection settings (ArangoDB URL, credentials)
- Anthropic API keys for LLM agents
- HTTP client configuration

**Needs for Cloud:**
- ✅ Can reuse existing Pydantic Settings pattern
- ➕ Add Redis configuration
- ➕ Add API authentication settings (API key secrets)
- ➕ Add per-customer database routing
- ➕ Add rate limiting configuration
- ➕ Add cloud storage configuration (S3/GCS)

### Agent Architecture

**Ingestion Agents (`src/complira_graph/agents/`):**
- 24 agents (NVD, GHSA, MITRE ATT&CK, CAPEC, NIST, etc.)
- All extend `BaseIngestionAgent`
- Pattern: `fetch_data()` → `transform_data()` → `load_data()`
- Use shared `HttpClient` with rate limiting
- Use shared utilities (`normalize_cve_id`, `safe_date_parse`, etc.)

**LLM Agents (`src/complira_graph/llm_agents/`):**
- 5 agents (CWE classifier, PURL→CPE, VEX, entity extractor, regulatory mapper)
- All extend `BaseLLMAgent`
- Pattern: `find_gaps()` → `enrich()` → `validate()` → `persist()`
- Use Anthropic Claude (Haiku 4.5 / Sonnet 4.5 / Opus 4.6)
- Gap-based enrichment (only process records missing enrichments)

**Key Insight:** 🎯 **The agent patterns are well-designed for adaptation to cloud services**
- `BaseIngestionAgent` → becomes background workers
- `BaseLLMAgent` → becomes enrichment services
- `find_gaps()` pattern → perfect for API-driven enrichment

### Utilities (`src/complira_graph/utils/`)

**Existing utilities that can be reused:**
- `http_client.py` - Rate-limited HTTP client with circuit breaker
- `keys.py` - Normalization functions (`normalize_cve_id`, `normalize_cwe_id`, etc.)
- `transforms.py` - Data transformation utilities (`safe_date_parse`, `batch_iterator`, etc.)

**Need to create:**
- Graph traversal utilities (reusable AQL query patterns)
- Caching decorators
- Customer scoping utilities
- API response formatting utilities

### Orchestration (`src/complira_graph/orchestrator/`)

**Current:**
- Uses Prefect 3.x for workflow orchestration
- `seed_workflow.py` - Orchestrates all ingestion agents
- DAG-based execution with checkpointing

**For Cloud:**
- ✅ Keep Prefect for background workers (reference data updates)
- ➕ Add scheduled jobs (EPSS velocity computation, benchmark aggregation)
- ➕ API-triggered workflows (on-demand snapshot generation)

---

## Layering and Boundaries Assessment

### Current Layering (Local App)
```
CLI Commands (thin)
    ↓
Agents (fetch + transform + load)
    ↓
Database (direct ArangoDB access)
    ↓
Utils (HTTP, transforms, keys)
```

**Assessment:** ✅ **Layering is coherent** for a local application
- CLI is thin (good)
- Agents own their domain (CVE ingestion, MITRE ingestion, etc.)
- Database layer is centralized (`db.py`)
- Utils are properly separated

### Target Layering (Cloud SaaS)
```
API Gateway (rate limiting, auth)
    ↓
REST API Endpoints (thin, FastAPI)
    ↓
Services (business logic, graph traversal)
    ↓
Database Layer (multi-tenant, cross-DB queries)
    ↓
Cache Layer (Redis)
    ↓
Background Workers (Prefect-orchestrated)
```

**New Layers Needed:**
1. **API Gateway Layer** - Kong/Traefik (rate limiting, API key validation)
2. **REST API Layer** - FastAPI (thin endpoints, dependency injection)
3. **Service Layer** - Business logic (enrichment, compaction, traversal)
4. **Cache Layer** - Redis (reference data caching)
5. **Multi-Tenant DB Layer** - Reference DB + Customer DBs

**Separation of Concerns:**
- **Endpoints:** Thin, handle HTTP concerns only (validation, responses)
- **Services:** Business logic, graph traversal, risk scoring
- **Database:** Multi-tenant data access, cross-DB queries
- **Cache:** Performance optimization, declarative
- **Workers:** Background jobs, decoupled from API

---

## DRY Opportunities Identified

### Code Duplication to Eliminate

**1. Graph Traversal Patterns**

Many features require similar graph traversals:
- Blast radius: CVE → CWE → CAPEC → ATT&CK → Threat Groups
- Defense coverage: Findings → CVE → CWE → CAPEC → ATT&CK → Controls
- Dependency risk: Component → depends_on (recursive) → CVE → CWE
- Remediation playbooks: CVE → CWE → CAPEC → ATT&CK → Controls → Requirements

**DRY Solution:** Create `BaseGraphService` with reusable traversal methods
```python
class BaseGraphService:
    def traverse(self, start_collection, start_key, edge_definitions, max_depth)
    def shortest_path(self, from_doc, to_collection, via_edges)
    def compute_coverage(self, items, target_collection, mapping_edge)
    def aggregate_risk(self, findings, risk_weights)
```

**2. Customer Scoping**

Every endpoint needs to:
- Extract customer_id from API key
- Inject `customer_id` filter into queries
- Return only customer's data

**DRY Solution:** FastAPI dependency injection
```python
async def get_current_customer(api_key: str = Depends(oauth2_scheme)) -> Customer:
    # Validate API key, return customer

# Every endpoint:
@router.post("/scan/ingest")
async def ingest_scan(customer: Customer = Depends(get_current_customer)):
    # customer_id automatically available
```

**3. Caching Logic**

Multiple endpoints need caching:
- Enrichment (reference data, 6-hour TTL)
- EPSS velocity (pre-computed, 24-hour TTL)
- Blast radius (reference, 6-hour TTL)
- Defense coverage (per-customer, 1-hour TTL)

**DRY Solution:** Caching decorator
```python
@cache(ttl=3600, key_prefix="enrich")
async def enrich_cve(cve_id: str) -> EnrichmentResult:
    # Cache handles Redis get/set transparently
```

**4. API Response Formatting**

All endpoints return similar structure:
- Success/error status
- Data payload
- Metadata (timing, cache hit, etc.)

**DRY Solution:** Standard response models
```python
class APIResponse[T]:
    success: bool
    data: T
    metadata: ResponseMetadata
```

**5. AQL Query Building**

Many services build AQL queries with similar patterns:
- Customer scoping (`FILTER doc.customer_id == @customer_id`)
- Graph traversals (`FOR v, e, p IN 1..N OUTBOUND start_doc edge_collection`)
- Caching (`LET cached = ...`)

**DRY Solution:** AQL Query Builder
```python
class GraphQueryBuilder:
    def __init__(self, db: Database):
        self.db = db

    def traverse(self, start, edges, max_depth):
        # Build traversal AQL

    def with_customer_scope(self, customer_id):
        # Auto-inject customer filter

    def execute(self, bind_vars):
        # Execute and return results
```

---

## SOLID Principles Application

### Single Responsibility Principle (SRP)

**Current:** Agents mix fetching, transformation, and loading
- ✅ Acceptable for local app (simplicity)
- ❌ Not ideal for cloud (services need to be composable)

**Target:**
- **Endpoints:** HTTP handling only
- **Services:** One concern each (`EnrichmentService`, `CompactionService`, etc.)
- **Repository Layer:** Database access only
- **Cache Layer:** Caching only

**Example:**
```python
# BEFORE (in agent):
class GHSAAgent:
    def fetch_data(self): ...
    def transform_data(self): ...
    def load_data(self): ...

# AFTER (in cloud):
class EnrichmentService:  # SRP: Enrichment logic only
    def enrich_cves(self, cve_ids: list[str]) -> list[Enrichment]:
        ...

class VulnerabilityRepository:  # SRP: DB access only
    def get_vulnerabilities(self, cve_ids: list[str]) -> list[CVE]:
        ...

class CacheService:  # SRP: Caching only
    def get_cached(self, key: str) -> Any:
        ...
```

### Open/Closed Principle (OCP)

**Goal:** Can add new features without modifying existing services

**Strategy:**
- **Base classes:** `BaseGraphService`, `BaseAPIEndpoint`
- **Interfaces:** `ICacheService`, `IGraphRepository`
- **Extension:** New features extend base, don't modify

**Example:**
```python
class BaseGraphService:  # Open for extension
    def traverse(self, ...): ...
    def compute_risk(self, ...): ...

class BlastRadiusService(BaseGraphService):  # Extends without modifying base
    def compute_blast_radius(self, cve_id: str):
        # Uses self.traverse() from base
        return self.traverse(...)
```

### Liskov Substitution Principle (LSP)

**Goal:** Subtypes must be substitutable for base types

**Application:**
- All graph services must implement `IGraphService` interface
- All cache implementations must implement `ICacheService`
- All repository implementations must implement `IRepository[T]`

**Example:**
```python
class IGraphService(Protocol):
    def traverse(self, ...) -> TraversalResult: ...

class EnrichmentService(BaseGraphService):  # Implements IGraphService
    # Can be used anywhere IGraphService is expected
    ...

class BlastRadiusService(BaseGraphService):  # Also implements IGraphService
    # Can be used anywhere IGraphService is expected
    ...
```

### Interface Segregation Principle (ISP)

**Goal:** Many specific interfaces > one general interface

**Application:**
- Don't create `IService` with 20 methods
- Create specific interfaces: `ITraversalService`, `ICacheService`, `IEnrichmentService`

**Example:**
```python
# BAD:
class IService:
    def traverse(...): ...
    def enrich(...): ...
    def cache(...): ...
    def compute_risk(...): ...
    # Too many responsibilities

# GOOD:
class ITraversalService(Protocol):
    def traverse(...): ...

class IEnrichmentService(Protocol):
    def enrich(...): ...

class ICacheService(Protocol):
    def get(...): ...
    def set(...): ...
```

### Dependency Inversion Principle (DIP)

**Goal:** Depend on abstractions, not concretions

**Application:**
- Services depend on `IDatabase`, not `ArangoDB` directly
- Services depend on `ICacheService`, not `Redis` directly
- Endpoints depend on `IEnrichmentService`, not `EnrichmentService` directly

**Example:**
```python
# BAD:
class EnrichmentService:
    def __init__(self):
        self.db = ArangoDB(...)  # Depends on concrete class
        self.cache = RedisCache(...)  # Depends on concrete class

# GOOD:
class EnrichmentService:
    def __init__(self, db: IDatabase, cache: ICacheService):
        self.db = db  # Depends on abstraction
        self.cache = cache  # Depends on abstraction
```

---

## Naming Conventions Assessment

### Current Naming
- **Agents:** `{source}_agent` (e.g., `ghsa_agent`, `kev_agent`) ✅ Good
- **Collections:** lowercase_snake_case ✅ Good
- **Functions:** snake_case ✅ Good
- **Classes:** PascalCase ✅ Good

### Target Naming (Cloud)
- **Services:** `{Domain}Service` (e.g., `EnrichmentService`, `BlastRadiusService`)
- **Endpoints:** `/v1/{resource}/{action}` (e.g., `/v1/scan/ingest`, `/v1/enrich`)
- **Models:** `{Purpose}{Type}` (e.g., `ScanIngestRequest`, `EnrichmentResponse`)
- **Workers:** `{Task}Worker` (e.g., `EPSSVelocityWorker`, `ReferenceUpdaterWorker`)

**No naming drift concerns** - clean slate for API layer.

---

## Constraints Identified

### Technical Constraints

**1. ArangoDB Multi-Tenancy**
- Must support cross-database AQL queries
- Constraint: ArangoDB requires `@<db_name>.<collection>` syntax for cross-DB
- Example: `FOR cve IN complira_reference.vulnerabilities`
- Implication: All customer queries must use cross-DB syntax

**2. Performance**
- Graph traversals can be expensive (4-hop blast radius on 335K CVEs)
- Constraint: Must complete in < 30 seconds
- Mitigation: Aggressive caching, indexed traversals, named graphs

**3. Existing Data Preservation**
- Must not lose any of 335K docs, 1.97M edges during migration
- Constraint: Export-verify-import-verify process mandatory
- Mitigation: Keep local DB as backup for 30 days

**4. Python 3.11+ (Existing Codebase)**
- All existing agents use Python 3.11 features
- Constraint: Cannot downgrade to older Python
- Implication: Ensure cloud infrastructure supports Python 3.11+

### Business Constraints

**1. SOC 2 Compliance**
- Customer data isolation is mandatory
- Constraint: Database-per-customer architecture required
- Implication: Cannot use shared database with row-level security

**2. Reference Data as IP**
- Reference graph is competitive advantage
- Constraint: Never expose reference DB directly to customers
- Implication: All access via API only, subset exports only

**3. Phase 0 Timeline (2 weeks)**
- Foundation must be production-ready quickly
- Constraint: Cannot gold-plate, must deliver MVP
- Mitigation: Focus on Phase 0 scope only, defer advanced features

### Performance Constraints

**1. Cache Hit Ratio Target: > 70%**
- Reference data queries must hit cache frequently
- Constraint: TTL tuning required
- Strategy: 6-hour TTL for reference data, 1-hour for customer data

**2. Enrichment Latency: < 10s for 100 CVEs**
- Must be usable in CI pipelines
- Constraint: Batch processing required
- Strategy: Parallel enrichment, Redis caching

**3. Database Query Optimization**
- Must add indexes for customer-scoped queries
- Constraint: Index on `customer_id` field in all customer collections
- Mitigation: Create indexes during Phase 0 setup

---

## Dependency Analysis

### External Dependencies (New)

**Must Add:**
1. **FastAPI** - REST API framework
2. **Redis** - Caching layer (python package: `redis`)
3. **uvicorn** - ASGI server for FastAPI
4. **python-jose** - JWT/API key handling
5. **passlib** - Password hashing (for future OAuth2)

**Optional (Phase 0):**
1. **Kong/Traefik** - API gateway (can use FastAPI middleware initially)
2. **Prometheus** - Metrics (can use structlog initially)

### Internal Dependencies (Reuse)

**Can Reuse:**
1. `src/complira_graph/db.py` - Database connection logic
2. `src/complira_graph/config.py` - Settings pattern
3. `src/complira_graph/utils/` - All utilities
4. `src/complira_graph/agents/base.py` - Adapt for background workers
5. `src/complira_graph/llm_agents/` - Adapt for enrichment services

**Must Extend:**
1. `db.py` - Add multi-tenant database routing
2. `config.py` - Add Redis, API auth settings
3. Create new `BaseGraphService` for traversals

---

## Open Questions and Unknowns

### Infrastructure Questions

**Q1:** Which cloud provider? (AWS / GCP / Azure)
- **Impact:** Affects managed services (Redis, object storage)
- **Decision needed:** Phase 0 Week 1
- **Recommendation:** AWS (ElastiCache, S3, ECS/EKS mature)

**Q2:** ArangoDB deployment model?
- **Option A:** Self-managed cluster on EC2/GKE (more control, more ops)
- **Option B:** ArangoDB Oasis managed service (less control, less ops)
- **Impact:** Operational complexity vs cost
- **Decision needed:** Phase 0 Week 1
- **Recommendation:** Self-managed for cost control (customer DBs can scale independently)

**Q3:** API Gateway choice?
- **Option A:** Kong (feature-rich, complex setup)
- **Option B:** Traefik (simpler, good for Kubernetes)
- **Option C:** FastAPI middleware (no separate gateway, simpler initially)
- **Decision needed:** Phase 0 Week 1
- **Recommendation:** Start with FastAPI middleware (Phase 0), add Kong later (Phase 2)

### Architecture Questions

**Q4:** How to handle local DB during transition?
- **Answer:** Keep local DB as read-only backup for 30 days post-migration
- **Verification:** Daily data consistency checks (doc counts, sample queries)

**Q5:** Rate limiting strategy?
- **Phase 0:** Simple global rate limit (100 req/min per API key)
- **Phase 2:** Per-customer tiers (free: 100/min, pro: 1000/min, enterprise: custom)

**Q6:** Background worker architecture?
- **Option A:** Prefect Cloud (managed)
- **Option B:** Self-hosted Prefect server
- **Decision:** Self-hosted Prefect on same infrastructure as API

---

## Risks and Mitigations

### Risk 1: Database Migration Data Loss
- **Likelihood:** Low
- **Impact:** Critical
- **Mitigation:**
  1. Export-verify-import-verify process (automated checks)
  2. Keep local DB as backup for 30 days
  3. Dry-run migration to test environment first
  4. Checksums and document counts at each step

### Risk 2: Cross-Database Query Performance
- **Likelihood:** Medium
- **Impact:** High
- **Mitigation:**
  1. Benchmark early (Week 1 of Phase 0)
  2. Add indexes on customer_id in all collections
  3. Use ArangoDB named graphs for optimized traversals
  4. Aggressive Redis caching (70% hit ratio target)

### Risk 3: Multi-Tenant Complexity
- **Likelihood:** Medium
- **Impact:** High
- **Mitigation:**
  1. Database-per-customer (simplest isolation)
  2. Centralized database routing in `db.py`
  3. Automatic customer_id injection via FastAPI dependencies
  4. Add shared-DB option only if cost becomes prohibitive

### Risk 4: Existing Code Not Cloud-Ready
- **Likelihood:** Medium
- **Impact:** Medium
- **Mitigation:**
  1. Refactor incrementally (reuse base classes)
  2. Extract reusable patterns into `BaseGraphService`
  3. Apply SOLID principles (DIP: depend on abstractions)
  4. Keep existing agents unchanged (adapt, don't rewrite)

### Risk 5: Phase 0 Timeline (2 weeks)
- **Likelihood:** Medium
- **Impact:** Medium
- **Mitigation:**
  1. Focus ruthlessly on Phase 0 scope only
  2. Defer advanced features to later phases
  3. Use FastAPI middleware for auth initially (no separate gateway)
  4. Minimal viable endpoints (just `/scan/ingest` for Phase 0)

---

## Scope Triage Decision

**Scope Classification:** **Large**

**Rationale:**
1. **Files Touched:** 50+ new files (API layer, services, workers, models)
2. **New Public APIs:** 13 REST endpoints across 4 phases
3. **Multi-Layer Impact:** API + services + database + cache + workers
4. **Architectural Impact:** Database separation, multi-tenancy, new layering
5. **Cross-Cutting Concerns:** Authentication, caching, error handling, logging
6. **Performance Requirements:** < 30s graph traversals, > 70% cache hit ratio
7. **Zero-Downtime Migration:** Must preserve 335K docs, 1.97M edges

**Workflow Depth:** Full workflow required
- ✅ Proposed design document (architecture + separation of concerns)
- ✅ Future-state runtime call stacks per use case
- ✅ Iterative deep-review rounds until stability gate
- ✅ Implementation plan + real-time progress tracking
- ✅ API/E2E testing with acceptance criteria closure
- ✅ Code review gate
- ✅ Documentation synchronization

---

## Next Steps

1. **Transition to Stage 2:** Refine requirements to Design-ready status
2. **Stage 3:** Create proposed design document (architecture-first)
3. **Stage 4:** Build future-state runtime call stacks for Phase 0 use cases
4. **Stage 5:** Iterative deep-review rounds until Go Confirmed
5. **Stage 6:** Implement Phase 0 (foundation)

---

## Investigation Complete

**Status:** ✅ Complete
**Transition:** Ready for Stage 2 (Requirements Refinement)
**Evidence:** `investigation-notes.md` current, scope triage recorded (Large)
