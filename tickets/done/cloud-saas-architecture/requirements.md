# Requirements: Cloud SaaS Architecture Implementation

**Status:** Design-ready
**Date:** 2026-03-02
**Updated:** 2026-03-02 (Stage 2 refinement)
**Ticket:** cloud-saas-architecture

---

## Goal

Transform Complira Knowledge Graph from a local/on-premise reference data store into a cloud-hosted multi-tenant SaaS platform with 13 API endpoints implementing 10 killer security intelligence features.

---

## Problem Statement

Current architecture limitations:
- **Local-only:** Cannot serve multiple customers/organizations
- **No multi-tenancy:** All data in single database
- **No API layer:** Direct database access only
- **No enrichment services:** Graph traversal logic scattered across CLI commands
- **No caching:** Every query hits database
- **No authentication:** No customer isolation or API keys

Target capabilities needed:
- **Cloud-native SaaS:** Multi-tenant platform serving multiple customers via API
- **Customer isolation:** Separate databases per customer (SOC 2 compliance)
- **API-first:** 13 REST endpoints for scan ingestion, enrichment, analysis
- **Advanced features:** Blast radius, EPSS velocity, defense coverage, regulatory delta, etc.
- **Performance:** Redis caching, optimized graph traversals
- **Security:** API key auth, rate limiting, per-customer data isolation

---

## In-Scope Use Cases

### Phase 0 (Foundation) - Weeks 1-2

**UC-001: Multi-Tenant Database Setup**
- **Source:** Requirement
- **Description:** Deploy cloud ArangoDB with reference DB + per-customer DBs
- **Acceptance Criteria:**
  - AC-001: `complira_reference` database created with existing 335K+ docs migrated
  - AC-002: Customer database template created (`complira_customer_<id>`)
  - AC-003: Cross-database AQL queries work (customer → reference joins)

**UC-002: API Authentication & Customer Scoping**
- **Source:** Requirement
- **Description:** Implement API key authentication with automatic customer scoping
- **Acceptance Criteria:**
  - AC-004: API key validates and maps to customer_id
  - AC-005: All database queries auto-inject customer_id filter
  - AC-006: Customers cannot access other customers' data

**UC-003: Redis Caching Layer**
- **Source:** Requirement
- **Description:** Deploy Redis with caching strategies per endpoint type
- **Acceptance Criteria:**
  - AC-007: Reference data cached (CVE enrichment, 6-hour TTL)
  - AC-008: Customer-specific data cached (1-hour TTL)
  - AC-009: Cache invalidation on reference data updates

**UC-004: Scan Ingestion API**
- **Source:** Requirement
- **Description:** POST /v1/scan/ingest - Accept SARIF/CycloneDX scanner outputs
- **Acceptance Criteria:**
  - AC-010: Parse SARIF format correctly
  - AC-011: Parse CycloneDX SBOM format correctly
  - AC-012: Create scan_session document
  - AC-013: Create scan_findings documents (normalized schema)
  - AC-014: Extract components from SBOM
  - AC-015: Create component_has_finding edges
  - AC-016: Return scan_session_id

**UC-005: Database Migration from Local to Cloud**
- **Source:** Stage 5 Review (Missing Use Case Discovery)
- **Description:** One-time migration of reference database from local ArangoDB to cloud
- **Acceptance Criteria:**
  - AC-017: Export all 335K+ documents from local database
  - AC-018: Export all 1.97M edges from local database
  - AC-019: Verify export integrity (document count, edge count, checksums)
  - AC-020: Import documents into cloud `complira_reference` database
  - AC-021: Import edges into cloud `complira_reference` database
  - AC-022: Verify import integrity (counts match, spot-check sample documents)
  - AC-023: Keep local database as read-only backup for 30 days
  - AC-024: Zero data loss tolerance (all counts must match exactly)

**UC-006: Customer Database On-Demand Provisioning**
- **Source:** Stage 5 Review (Missing Use Case Discovery)
- **Description:** Automatic creation of customer-specific database on first API request
- **Acceptance Criteria:**
  - AC-025: Database creation triggered on first authenticated request from new customer
  - AC-026: Database naming follows pattern `complira_customer_<customer_id>`
  - AC-027: Database created with customer-specific collections (scan_sessions, scan_findings, components, edges)
  - AC-028: Indexes created automatically (customer_id indexes, CVE lookup indexes)
  - AC-029: Creation is idempotent (concurrent requests handled safely)
  - AC-030: Database creation completes within 5 seconds
  - AC-031: Failure rolls back (no partial database state)

### Phase 1 (Core Pipeline) - Weeks 3-5

**UC-007: Vulnerability Enrichment**
- **Source:** Requirement
- **Description:** POST /v1/enrich - Hydrate CVEs with full graph context
- **Acceptance Criteria:**
  - AC-032: Traverse CVE → CWE → CAPEC → ATT&CK → Threat Groups
  - AC-033: Add EPSS current score and velocity
  - AC-034: Add KEV status
  - AC-035: Add mapped D3FEND defenses
  - AC-036: Add mapped OSCAL controls
  - AC-037: Results cached in Redis

**UC-008: Finding Compaction & Risk Scoring**
- **Source:** Requirement
- **Description:** POST /v1/compact - Deduplicate, cluster, risk-score findings
- **Acceptance Criteria:**
  - AC-038: Deduplicate via aliases edges (634K)
  - AC-039: Roll up to parent CWE via child_of edges (1.77K)
  - AC-040: Composite risk score = weighted(KEV, EPSS, attack_paths, control_gaps)
  - AC-041: Return clusters sorted by risk descending

**UC-009: Control Mapping**
- **Source:** Requirement
- **Description:** POST /v1/map-controls - Map findings to compliance frameworks
- **Acceptance Criteria:**
  - AC-042: Map to NIST 800-53 controls
  - AC-043: Map to ISO 27001 controls
  - AC-044: Map to FDA 510(k) requirements
  - AC-045: Return evidence chains (CVE → CWE → CAPEC → ATT&CK → Control → Requirement)
  - AC-046: Calculate coverage % per framework

### Phase 2 (Killer Features Wave 1) - Weeks 6-9

**UC-010: Blast Radius Simulation**
- **Source:** Requirement
- **Description:** POST /v1/blast-radius - Compute full impact graph from CVE
- **Acceptance Criteria:**
  - AC-047: Traverse up to configurable max depth (default 4)
  - AC-048: Include threat groups reachable from CVE
  - AC-049: Include kill chain via can_precede edges (286 edges)
  - AC-050: Compute hop distance to each APT group
  - AC-051: Return visualization data (nodes + edges)
  - AC-052: Return executive summary ("N hops from APT group X")
  - AC-053: Export formats: PDF slide, JSON graph, Mermaid

**UC-011: EPSS Velocity Detection**
- **Source:** Requirement
- **Description:** GET /v1/epss-velocity - Identify CVEs with accelerating exploit probability
- **Acceptance Criteria:**
  - AC-054: Query epss_history (317K records) for 30-day trends
  - AC-055: Calculate daily_acceleration per CVE
  - AC-056: Flag "accelerating" if daily_acceleration > threshold
  - AC-057: Predict KEV probability based on EPSS + CWE type + threat group activity
  - AC-058: Return sorted by acceleration descending

**UC-012: Portfolio Risk Curves**
- **Source:** Requirement
- **Description:** GET /v1/portfolio-risk-curve - Aggregate EPSS trends across customer SBOM
- **Acceptance Criteria:**
  - AC-059: Aggregate EPSS for all CVEs affecting customer components
  - AC-060: Calculate portfolio_risk_score over time (daily/weekly)
  - AC-061: Identify trend (improving/stable/deteriorating)
  - AC-062: Identify inflection points (sudden risk increases)
  - AC-063: Breakdown by severity/CWE/component

**UC-013: Defense Coverage Heatmap**
- **Source:** Requirement
- **Description:** POST /v1/defense-coverage - ATT&CK heatmap showing covered vs uncovered techniques
- **Acceptance Criteria:**
  - AC-064: Find techniques reachable from customer vulnerabilities
  - AC-065: Check if technique has controls (technique_mitigated_by_control edges)
  - AC-066: Check if technique has defenses (d3fend_counters_technique edges)
  - AC-067: Return full ATT&CK matrix with coverage status per technique
  - AC-068: Include D3FEND recommendations for uncovered techniques

**UC-014: Regulatory Delta Analysis**
- **Source:** Requirement
- **Description:** POST /v1/regulatory-delta - Diff framework versions and compute impact
- **Acceptance Criteria:**
  - AC-069: Diff oscal_controls between versions (e.g., ISO 27001:2013 → 2022)
  - AC-070: Identify controls_added, controls_removed, controls_modified
  - AC-071: Compute customer impact (newly_non_compliant count)
  - AC-072: Identify doc sections needing regeneration
  - AC-073: Return continuous monitoring alerts

---

## Out of Scope

**Explicitly NOT in Phase 0-1:**
- GitHub Action client (deferred)
- Remediation playbooks (Phase 3)
- What-if modeling (Phase 3)
- License conflict detection (Phase 3)
- Benchmarking (Phase 4)
- Natural language query (Phase 4)
- Offline snapshots (Phase 4)
- Document generation enhancements (Phase 4)

---

## Constraints

**Technical Constraints:**
- Must use existing ArangoDB database with 335K docs, 1.97M edges
- Must preserve all existing reference data during migration
- Must support cross-database AQL queries (customer DB → reference DB)
- Must use Python 3.11+ (existing codebase)
- Must use FastAPI for REST API
- Must use Redis for caching
- Must use existing ingestion agents (`src/complira_graph/agents/`) as basis

**Business Constraints:**
- Phase 0 must complete in 2 weeks (foundation for all other features)
- Customer data isolation is mandatory (SOC 2 compliance requirement)
- Reference data is IP - never exposed directly to customers
- API must be production-ready (error handling, logging, observability)

**Performance Constraints:**
- Graph traversals must complete in < 30 seconds
- Enrichment API must handle 100 CVEs in < 10 seconds
- Cache hit ratio target: > 70% for reference data queries
- Database separation must NOT degrade query performance

---

## Assumptions

1. **ArangoDB Cluster:** We will deploy ArangoDB on cloud infrastructure (AWS/GCP/Azure)
2. **Redis:** We will use managed Redis service (ElastiCache / MemoryStore)
3. **Existing Agents:** Current ingestion agents can be adapted (not rewritten from scratch)
4. **API Gateway:** We will use Kong or Traefik for rate limiting (not building custom)
5. **Customer Onboarding:** Initial customers will be manually onboarded (automated onboarding in later phase)

---

## Architecture Decisions (From Investigation)

### AD-001: Database Separation Strategy
**Decision:** Database-per-customer architecture
- **Reference DB:** `complira_reference` (shared, read-only for customers)
- **Customer DBs:** `complira_customer_<id>` (isolated per tenant)
- **Rationale:** SOC 2 compliance requires customer data isolation
- **Impact:** All customer queries use cross-database AQL syntax

### AD-002: API and Workers Decoupling
**Decision:** Separate processes from Day 1
- **API:** FastAPI application (scales horizontally based on traffic)
- **Workers:** Prefect workers (scales based on workload)
- **Rationale:** Independent scaling profiles and fault isolation
- **Impact:** Different deployment, scaling, and resource allocation

### AD-003: Base Service Pattern (DRY)
**Decision:** Create `BaseGraphService` for reusable traversal patterns
- **Methods:** `traverse()`, `shortest_path()`, `compute_coverage()`, `aggregate_risk()`
- **Rationale:** Eliminate duplication across 10 features requiring graph traversal
- **Impact:** All services extend `BaseGraphService`

### AD-004: Customer Scoping (Automatic)
**Decision:** FastAPI dependency injection for automatic customer_id
- **Pattern:** `async def get_current_customer(api_key: str) -> Customer`
- **Rationale:** Eliminate manual customer_id checks in every endpoint
- **Impact:** All endpoints use `Depends(get_current_customer)`

### AD-005: Caching Strategy
**Decision:** Redis with per-endpoint TTL strategy
- **Reference data:** 6-hour TTL (changes slowly)
- **Customer data:** 1-hour TTL (changes frequently)
- **Target:** > 70% cache hit ratio
- **Rationale:** Performance optimization for expensive graph traversals

### AD-006: Authentication (Phase 0)
**Decision:** API key authentication (no separate gateway initially)
- **Implementation:** FastAPI middleware
- **Upgrade path:** Add Kong/Traefik in Phase 2
- **Rationale:** Faster Phase 0 delivery, simpler initial setup

### AD-007: SOLID Principles Application
**Decision:** Strict SOLID enforcement
- **SRP:** Endpoints (HTTP only), Services (business logic only), Repositories (DB only)
- **OCP:** Base classes for extension (BaseGraphService, BaseAPIEndpoint)
- **LSP:** All services implement interfaces (IGraphService, ICacheService)
- **ISP:** Specific interfaces (ITraversalService, not generic IService)
- **DIP:** Depend on abstractions (IDatabase, not ArangoDB directly)

## Open Questions

1. **Q:** Which cloud provider? (AWS / GCP / Azure)
   - **A:** [TBD - Recommendation: AWS for mature managed services]

2. **Q:** ArangoDB deployment model? (Self-managed cluster / ArangoDB Oasis managed service)
   - **A:** [TBD - Recommendation: Self-managed for cost control]

3. **Q:** API Gateway in Phase 0 or Phase 2?
   - **A:** DECIDED - Phase 2 (use FastAPI middleware initially)

4. **Q:** How to handle local database during cloud transition?
   - **A:** DECIDED - Keep local DB as read-only backup for 30 days post-migration

5. **Q:** Rate limiting strategy per customer tier?
   - **A:** DECIDED - Phase 0: simple global (100 req/min); Phase 2: per-customer tiers

---

## Dependencies

**External Dependencies:**
- ArangoDB cloud cluster (or managed Oasis instance)
- Redis managed service
- API gateway (Kong/Traefik)
- Object storage (S3/GCS) for scan artifacts and generated docs

**Internal Dependencies:**
- Existing `src/complira_graph/agents/` ingestion agents
- Existing `src/complira_graph/llm_agents/` enrichment agents
- Existing `src/complira_graph/db.py` database schema
- Existing `src/complira_graph/config.py` settings

---

## Risks

**Risk 1: Database Migration Data Loss**
- **Likelihood:** Low
- **Impact:** Critical
- **Mitigation:** Export-verify-import-verify process; keep local DB as backup for 30 days

**Risk 2: Cross-Database Query Performance**
- **Likelihood:** Medium
- **Impact:** High
- **Mitigation:** Benchmark early; add indexes; use caching aggressively

**Risk 3: Multi-Tenant Complexity**
- **Likelihood:** Medium
- **Impact:** High
- **Mitigation:** Use database-per-customer (simplest isolation); add shared-DB multi-tenancy only if cost becomes prohibitive

**Risk 4: Existing Code Not Cloud-Ready**
- **Likelihood:** Medium
- **Impact:** Medium
- **Mitigation:** Refactor incrementally; extract reusable patterns into base classes (DRY); apply SOLID principles

---

## Success Criteria

**Phase 0 Success (End of Week 2):**
1. Cloud ArangoDB cluster operational with reference + customer DBs
2. All 335K+ reference docs migrated successfully (verified counts)
3. FastAPI application deployed with `/v1/scan/ingest` working
4. API key authentication working
5. Redis caching layer operational
6. Can ingest SARIF scan, get back scan_session_id
7. Zero data loss from local → cloud migration

**Phase 1 Success (End of Week 5):**
1. `/v1/enrich`, `/v1/compact`, `/v1/map-controls` APIs working
2. Full pipeline: scan ingest → enrich → compact → map → results
3. All critical edges populated (affects, matched_by_cpe, depends_on, technique_mitigated_by_control)
4. Cache hit ratio > 70% for reference queries
5. API response times: enrichment < 10s for 100 CVEs

---

## Scope Classification

**Scope:** Large

**Rationale:**
- 13 API endpoints to implement across 4 phases
- Multi-database architecture (reference + per-customer)
- Significant refactoring required (DRY/SOLID principles)
- Cross-cutting concerns (auth, caching, error handling)
- Database migration with zero data loss requirement
- Performance optimization required (caching, indexing)
- Production-ready (logging, monitoring, error handling)

**Workflow Depth:** Full workflow
- Proposed design document required
- Future-state runtime call stacks per use case
- Iterative deep-review rounds until stability gate
- Implementation plan + real-time progress tracking
- API/E2E testing with acceptance criteria closure
- Code review gate
- Documentation synchronization

---

## Requirement Coverage Map

| Requirement ID | Use Case ID(s) | Phase |
|---|---|---|
| REQ-001: Multi-tenant database | UC-001, UC-005, UC-006 | P0 |
| REQ-002: API authentication | UC-002 | P0 |
| REQ-003: Caching layer | UC-003 | P0 |
| REQ-004: Scan ingestion | UC-004 | P0 |
| REQ-005: Enrichment | UC-007 | P1 |
| REQ-006: Compaction | UC-008 | P1 |
| REQ-007: Control mapping | UC-009 | P1 |
| REQ-008: Blast radius | UC-010 | P2 |
| REQ-009: EPSS velocity | UC-011 | P2 |
| REQ-010: Portfolio risk | UC-012 | P2 |
| REQ-011: Defense coverage | UC-013 | P2 |
| REQ-012: Regulatory delta | UC-014 | P2 |

---

## Acceptance Criteria Coverage Map

Will be maintained during Stage 7 (API/E2E Testing).

Initial mapping: Each AC-XXX maps to at least one API test scenario.

---

## Notes

- This is a cloud-first rewrite, not incremental enhancement
- Focus on Phase 0 (foundation) - get it right, rest builds on it
- DRY/SOLID principles are mandatory (eliminate code duplication)
- All services must extend base classes for graph traversal
- API endpoints are thin wrappers around services (business logic in services)
- Customer scoping is automatic (injected by dependency, not manual in each endpoint)
