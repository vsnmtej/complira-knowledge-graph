# Complira Knowledge Graph - Cloud Architecture

**Status:** Phase 0 Implementation
**Version:** 1.0.0
**Last Updated:** 2026-03-02
**Architecture Pattern:** Multi-tenant SaaS with Graph Database

---

## Executive Summary

This document describes the cloud-native architecture for **Complira Knowledge Graph**, a multi-tenant SaaS platform that transforms the existing local cybersecurity compliance knowledge graph into a scalable cloud service.

**Key Transformations:**
- **From:** Local Python application with direct database access
- **To:** Cloud-hosted API with thin CI/CD clients (GitHub Actions)
- **Pattern:** Backend API (FastAPI) + Client SDK (GitHub Action) + Background Workers
- **Multi-tenancy:** Database separation (reference DB + customer DBs)
- **Deployment:** Single-region with horizontal scaling capability

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         CLOUD PLATFORM (VPS)                          │
│                                                                        │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    FastAPI Backend                           │    │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐            │    │
│  │  │ API        │  │ Services   │  │ Workers    │            │    │
│  │  │ Endpoints  │→ │ (Business  │→ │ (Background│            │    │
│  │  │ (13 total) │  │  Logic)    │  │  Jobs)     │            │    │
│  │  └────────────┘  └────────────┘  └────────────┘            │    │
│  │         ↓                ↓                ↓                 │    │
│  │  ┌──────────────────────────────────────────────┐          │    │
│  │  │           Core Infrastructure                │          │    │
│  │  │  • Redis (Caching)                          │          │    │
│  │  │  • API Key Auth                             │          │    │
│  │  │  • Rate Limiting                            │          │    │
│  │  └──────────────────────────────────────────────┘          │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                              ↓                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                  ArangoDB Cluster                            │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │    │
│  │  │ Reference DB │  │ Customer DB  │  │ Customer DB  │      │    │
│  │  │ (Shared)     │  │ (tenant_1)   │  │ (tenant_2)   │      │    │
│  │  └──────────────┘  └──────────────┘  └──────────────┘      │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
                              ↑
                              │ HTTPS/API
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│                      CLIENT LAYER                                     │
│                                                                        │
│  ┌─────────────────┐     ┌─────────────────┐     ┌────────────────┐ │
│  │ GitHub Action   │     │ CLI Client      │     │ Web Dashboard  │ │
│  │ (CI/CD)         │     │ (Local/Server)  │     │ (Future)       │ │
│  └─────────────────┘     └─────────────────┘     └────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Design Principles Applied

### 1. DRY (Don't Repeat Yourself)

**Problem:** 13 API endpoints could lead to massive code duplication for:
- Graph traversal logic
- Customer scoping
- Caching patterns
- Error handling
- Response formatting

**Solution:** Hierarchical abstraction layers

```python
# Base Service (DRY Layer 1)
class BaseGraphService:
    """Reusable graph traversal patterns"""
    - traverse()
    - shortest_path()
    - compute_coverage()
    - get_customer_scoped_collection()

# Feature Services (DRY Layer 2)
class BlastRadiusService(BaseGraphService):
    """Inherits traversal logic, adds blast radius specifics"""

class DefenseCoverageService(BaseGraphService):
    """Inherits traversal logic, adds coverage specifics"""

# API Endpoints (DRY Layer 3)
@router.post("/v1/blast-radius")
async def blast_radius(service: BlastRadiusService = Depends()):
    """Thin wrapper - no business logic duplication"""
    return await service.execute()
```

**Duplication Eliminated:**
- Graph traversal: 13 endpoints × 150 lines = **1,950 lines saved**
- Customer scoping: 13 endpoints × 50 lines = **650 lines saved**
- Caching logic: 13 endpoints × 75 lines = **975 lines saved**
- **Total reduction: ~3,600 lines of code**

---

### 2. SOLID Principles

#### Single Responsibility Principle (SRP)
Each component has one reason to change:

| Component | Responsibility | Changes When |
|-----------|---------------|--------------|
| `BlastRadiusService` | Calculate regulatory blast radius | Business logic for blast radius changes |
| `CacheManager` | Cache operations | Caching strategy changes |
| `CustomerAuthMiddleware` | API key validation | Auth requirements change |
| `GraphTraversalEngine` | Build AQL queries | Query patterns change |

#### Open/Closed Principle (OCP)
**Extensible without modification:**

```python
# ✅ Adding new feature: Extend base, don't modify it
class NewFeatureService(BaseGraphService):
    def execute(self):
        # Uses inherited traverse(), shortest_path(), etc.
        # No changes to BaseGraphService needed
        pass
```

#### Liskov Substitution Principle (LSP)
**All services are substitutable:**

```python
# Any service can be injected via dependency injection
def execute_service(service: BaseGraphService):
    return service.execute()  # Works with any subclass

# ✅ Works
execute_service(BlastRadiusService())
execute_service(DefenseCoverageService())
execute_service(EPSSVelocityService())
```

#### Interface Segregation Principle (ISP)
**Many specific interfaces over one fat interface:**

```python
# ❌ Fat interface
class FatService:
    def traverse()
    def cache()
    def auth()
    def enrich()
    def compact()
    # Too many responsibilities!

# ✅ Segregated interfaces
class ITraversalService(Protocol):
    def traverse() -> Iterator[dict]

class ICacheableService(Protocol):
    def get_cache_key() -> str

class IEnrichableService(Protocol):
    def enrich(data: dict) -> dict
```

#### Dependency Inversion Principle (DIP)
**Depend on abstractions, not concretions:**

```python
# ✅ Service depends on abstract database interface
class BlastRadiusService:
    def __init__(self, db: IGraphDatabase, cache: ICache):
        self.db = db  # Abstraction, not ArangoDB directly
        self.cache = cache  # Abstraction, not Redis directly

    # Can swap implementations without changing service code
    # - ArangoDB → Neo4j: Just change IGraphDatabase impl
    # - Redis → Memcached: Just change ICache impl
```

---

## Multi-Tenancy Architecture

### Database Separation Strategy

**Reference Database (Shared):**
- Contains: CVE, CWE, ATT&CK, CAPEC, D3FEND, regulatory frameworks
- Updated by: Background workers (hourly/daily)
- Access: Read-only from all customers
- Size: ~10M nodes, ~28M edges

**Customer Databases (Isolated):**
- Contains: SBOM components, scan results, VEX documents, policy overrides
- Updated by: Customer API calls (scan ingestion)
- Access: Scoped by API key
- Size: ~1K-100K nodes per customer

**Benefits:**
1. **Cost Efficiency:** Shared reference data (no duplication)
2. **Performance:** Smaller customer DBs = faster queries
3. **Security:** Customer data physically separated
4. **Compliance:** GDPR/SOC2 isolation requirements met

### Customer Scoping Pattern

```python
# Automatic customer scoping in all services
class BaseGraphService:
    def __init__(self, customer_id: str):
        self.customer_id = customer_id
        self.reference_db = get_reference_db()
        self.customer_db = get_customer_db(customer_id)

    def query_with_scoping(self, aql_query: str):
        """Auto-inject customer_id filter"""
        # Reference DB: No scoping needed (shared)
        # Customer DB: All queries scoped to customer_id
        return self.customer_db.aql.execute(
            aql_query,
            bind_vars={"customer_id": self.customer_id}
        )
```

---

## API Endpoint Design (13 Endpoints)

### Phase 0 (Foundation) - 2 Endpoints
1. `POST /v1/scan/ingest` - Ingest SARIF/CycloneDX scans
2. `GET /v1/health` - Health check

### Phase 1 (Core Features) - 5 Endpoints
3. `POST /v1/blast-radius` - Regulatory blast radius
4. `POST /v1/vex/generate` - VEX document generation
5. `GET /v1/enrichment/status` - Enrichment job status
6. `POST /v1/query/graph` - Custom AQL queries
7. `GET /v1/components/{purl}` - Component details

### Phase 2 (Advanced Features) - 3 Endpoints
8. `POST /v1/defense-coverage` - Defense coverage analysis
9. `POST /v1/epss-velocity` - EPSS trend analysis
10. `POST /v1/exploit-likelihood` - Exploit probability

### Phase 3 (Intelligence) - 3 Endpoints
11. `POST /v1/threat-context` - Threat actor context
12. `POST /v1/dependency-risk` - Dependency risk scoring
13. `POST /v1/compliance/gaps` - Compliance gap analysis

---

## Caching Strategy (Per Endpoint)

| Endpoint | Cache TTL | Cache Key | Invalidation |
|----------|-----------|-----------|--------------|
| `/blast-radius` | 1 hour | `blast:{customer_id}:{cve_id}` | On reference DB update |
| `/vex/generate` | 30 min | `vex:{customer_id}:{component}:{cve}` | On scan ingestion |
| `/defense-coverage` | 2 hours | `defense:{customer_id}:{technique}` | On D3FEND update |
| `/epss-velocity` | 6 hours | `epss:{cve_id}:{days}` | On EPSS daily update |
| `/components/{purl}` | 24 hours | `component:{purl}` | On deps.dev update |

**Cache Hierarchy:**
1. **L1 (In-memory):** FastAPI `@lru_cache` for hot paths
2. **L2 (Redis):** Shared cache for all API instances
3. **L3 (Database):** Materialized views for complex aggregations

---

## Background Workers (Existing Agents → Cloud Services)

### Migration Pattern

**Before (Local):**
```python
# src/complira_graph/agents/nvd.py
class NVDAgent(BaseIngestionAgent):
    def run():
        # Runs locally, writes to local DB
        pass
```

**After (Cloud):**
```python
# src/api/workers/reference_updater.py
class ReferenceUpdaterWorker:
    def update_nvd():
        # Runs on cloud server, writes to reference DB
        # Uses existing NVDAgent internally
        agent = NVDAgent(get_reference_db())
        agent.run()
```

### Worker Schedule

| Worker | Frequency | Source | Target DB |
|--------|-----------|--------|-----------|
| `reference_updater.py` | Hourly | NVD, CISA KEV | Reference |
| `epss_velocity_compute.py` | Daily | EPSS history | Reference |
| `benchmark_aggregator.py` | Daily | Scorecard, deps.dev | Reference |
| `customer_enrichment.py` | On-demand | Claude API | Customer |

---

## Authentication & Authorization

### API Key Auth

```python
# src/api/core/security.py
class APIKeyAuth:
    """
    Simple API key authentication for v1.0

    Header: Authorization: Bearer <api_key>
    Rate Limit: 1000 requests/hour per key
    """

    @staticmethod
    async def verify_api_key(api_key: str) -> Customer:
        """Validate API key and return customer context"""
        # Lookup in Redis cache (fast path)
        customer = await redis.get(f"apikey:{api_key}")
        if customer:
            return customer

        # Lookup in database (slow path)
        customer = db.collection("api_keys").get(api_key)
        if not customer or customer.get("revoked"):
            raise HTTPException(401, "Invalid API key")

        # Cache for 5 minutes
        await redis.setex(f"apikey:{api_key}", 300, customer)
        return customer
```

### Rate Limiting

```python
# Per customer rate limits
RATE_LIMITS = {
    "free": 100,      # 100 requests/hour
    "starter": 1000,  # 1K requests/hour
    "pro": 10000,     # 10K requests/hour
    "enterprise": None  # Unlimited
}
```

---

## Data Flow Examples

### Example 1: Scan Ingestion → VEX Generation

```
1. Developer triggers GitHub Action
   ├─> Runs Trivy scan → SARIF output
   └─> Calls POST /v1/scan/ingest

2. API receives SARIF
   ├─> Authenticates API key → customer_id
   ├─> Parses SARIF → components + vulnerabilities
   ├─> Writes to customer DB
   └─> Returns ingestion_id

3. Developer requests VEX
   ├─> Calls POST /v1/vex/generate
   └─> Passes component + CVE

4. VEX Service executes
   ├─> Queries reference DB (CVE, CWE, EPSS, KEV)
   ├─> Queries customer DB (SBOM, scan findings)
   ├─> Calls LLM enrichment (Claude Sonnet 4.5)
   ├─> Generates VEX document
   ├─> Caches result (30 min TTL)
   └─> Returns VEX JSON

5. GitHub Action outputs VEX
   └─> Writes to repository artifacts
```

### Example 2: Blast Radius Query

```
1. Analyst queries blast radius
   └─> GET /v1/blast-radius?cve=CVE-2024-1234

2. Check cache
   ├─> Cache HIT: Return immediately
   └─> Cache MISS: Execute service

3. BlastRadiusService.execute()
   ├─> Query reference DB:
   │   CVE → CWE → Regulatory Requirements → Frameworks
   ├─> Build evidence chain
   ├─> Format response
   ├─> Cache result (1 hour TTL)
   └─> Return JSON

4. Response format:
   {
     "cve_id": "CVE-2024-1234",
     "affected_frameworks": [
       {
         "framework": "EU CRA",
         "requirements": ["Art. 20.1", "Annex I.2"],
         "evidence_chain": ["CVE-2024-1234", "CWE-79", "CRA-Art-20-1"]
       }
     ]
   }
```

---

## Project Structure

```
complira-graph/
├── src/
│   ├── api/                          # FastAPI Backend (NEW)
│   │   ├── __init__.py
│   │   ├── main.py                   # FastAPI app entry
│   │   ├── core/                     # Core infrastructure
│   │   │   ├── config.py             # Extended settings (cloud-specific)
│   │   │   ├── security.py           # API key auth
│   │   │   ├── cache.py              # Redis cache manager
│   │   │   └── dependencies.py       # FastAPI dependencies
│   │   ├── v1/                       # API v1
│   │   │   ├── router.py             # Main router
│   │   │   ├── dependencies.py       # Version-specific deps
│   │   │   └── endpoints/            # 13 API endpoints
│   │   │       ├── scan.py           # Scan ingestion
│   │   │       ├── blast_radius.py   # Blast radius
│   │   │       ├── vex.py            # VEX generation
│   │   │       ├── defense_coverage.py
│   │   │       ├── epss_velocity.py
│   │   │       └── ...
│   │   ├── services/                 # Business logic (DRY)
│   │   │   ├── base.py               # BaseGraphService
│   │   │   ├── graph_traversal.py    # GraphTraversalEngine
│   │   │   ├── blast_radius.py       # BlastRadiusService
│   │   │   ├── vex.py                # VEXGeneratorService
│   │   │   ├── enrichment.py         # EnrichmentService
│   │   │   └── ...
│   │   ├── models/                   # Pydantic models
│   │   │   ├── requests/             # API request models
│   │   │   ├── responses/            # API response models
│   │   │   └── domain/               # Domain models
│   │   └── workers/                  # Background workers
│   │       ├── reference_updater.py
│   │       ├── epss_velocity_compute.py
│   │       └── benchmark_aggregator.py
│   │
│   └── complira_graph/               # Existing codebase (KEEP)
│       ├── agents/                   # Ingestion agents (reused by workers)
│       ├── llm_agents/               # LLM agents (reused by services)
│       ├── db.py                     # Database utilities
│       ├── config.py                 # Existing config (extended)
│       └── ...
│
├── clients/                          # Client SDKs (NEW)
│   └── github-action/
│       ├── action.yml                # GitHub Action manifest
│       ├── Dockerfile                # Action container
│       ├── src/
│       │   ├── client.py             # API client with retry
│       │   ├── parsers/              # SARIF/CycloneDX parsers
│       │   └── reporters/            # Output formatters
│       └── tests/
│
├── docs/                             # Documentation
│   ├── cloud-architecture.md         # THIS FILE
│   ├── api/                          # API documentation
│   │   └── openapi.yml               # OpenAPI spec
│   └── adr/                          # Architecture Decision Records
│       ├── 001-fastapi-framework.md
│       ├── 002-database-separation.md
│       └── 003-caching-strategy.md
│
├── tests/                            # Tests
│   ├── unit/
│   ├── integration/
│   └── performance/
│
├── docker-compose.yml                # Local development
├── pyproject.toml                    # Dependencies
└── README.md
```

---

## Deployment Architecture

### Single-Server Deployment (Phase 0-1)

```yaml
# docker-compose.production.yml
services:
  api:
    image: complira/api:latest
    replicas: 2
    ports:
      - "8000:8000"
    environment:
      - ARANGO_URL=http://arangodb:8529
      - REDIS_URL=redis://redis:6379

  arangodb:
    image: arangodb:3.12
    volumes:
      - arangodb_data:/var/lib/arangodb3

  redis:
    image: redis:7-alpine

  worker:
    image: complira/api:latest
    command: python -m src.api.workers.reference_updater

  nginx:
    image: nginx:alpine
    ports:
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/ssl
```

### Horizontal Scaling (Phase 2+)

```
              ┌─────────────┐
              │ Load Balancer│
              │  (Nginx)     │
              └──────┬───────┘
                     │
         ┌───────────┼───────────┐
         ▼           ▼           ▼
    ┌────────┐  ┌────────┐  ┌────────┐
    │ API-1  │  │ API-2  │  │ API-3  │
    └────┬───┘  └────┬───┘  └────┬───┘
         │           │           │
         └───────────┼───────────┘
                     ▼
              ┌─────────────┐
              │   Redis     │
              │  (Shared)   │
              └─────────────┘
                     │
              ┌─────────────┐
              │  ArangoDB   │
              │  (Cluster)  │
              └─────────────┘
```

---

## Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| Blast radius query | < 5s | p95 |
| VEX generation | < 30s | p95 |
| Scan ingestion (1000 CVEs) | < 10s | p95 |
| API response time | < 200ms | p50 |
| Concurrent requests | 100 req/s | Sustained |
| Database size | 10M nodes | Single server |

---

## Cost Estimation

### Infrastructure (Monthly)

| Component | Provider | Spec | Cost |
|-----------|----------|------|------|
| VPS | Hetzner | 32GB RAM, 8 vCPU, 512GB NVMe | €40 |
| Backup | Backblaze B2 | 100GB | €0.50 |
| Domain + SSL | Cloudflare | Free tier | €0 |
| **Total Infrastructure** | | | **€40.50** |

### LLM API Costs (Monthly)

| Operation | Volume | Cost per 1K | Monthly Cost |
|-----------|--------|-------------|--------------|
| CWE Classification (one-time) | 25K CVEs | $0.80 | $20 (one-time) |
| VEX Generation | 1K/month | $3.00 | $3 |
| Regulatory Mapping | 100/month | $2.40 | $0.24 |
| **Total LLM** | | | **$23.24** |

**Total Monthly Cost: €40.50 + $23.24 ≈ €62** ✅ Well under €100 budget

---

## Security Considerations

### API Security
- ✅ API key authentication (Bearer token)
- ✅ Rate limiting per customer tier
- ✅ HTTPS only (TLS 1.3)
- ✅ Request validation (Pydantic)
- ✅ SQL injection prevention (parameterized AQL)

### Data Security
- ✅ Customer database isolation
- ✅ Encryption at rest (ArangoDB)
- ✅ Encryption in transit (TLS)
- ✅ API key rotation support
- ✅ Audit logging (structured logs)

### Compliance
- ✅ GDPR: Customer data isolation
- ✅ SOC2: Access logs, encryption
- ✅ ISO 27001: Security controls

---

## Monitoring & Observability

### Metrics (Prometheus)
```python
# Example metrics
api_requests_total = Counter("api_requests_total", ["endpoint", "customer"])
api_latency_seconds = Histogram("api_latency_seconds", ["endpoint"])
llm_tokens_used = Counter("llm_tokens_used", ["model", "customer"])
cache_hit_rate = Gauge("cache_hit_rate", ["endpoint"])
```

### Logs (Structured JSON)
```json
{
  "timestamp": "2026-03-02T10:15:30Z",
  "level": "INFO",
  "customer_id": "cust_123",
  "endpoint": "/v1/blast-radius",
  "cve_id": "CVE-2024-1234",
  "execution_time_ms": 1234,
  "cache_hit": true
}
```

### Dashboards (Grafana)
- API request rates and latencies
- Customer usage breakdown
- LLM cost tracking
- Cache hit rates
- Database query performance

---

## Migration Path (Existing → Cloud)

### Phase 0: Foundation (Weeks 1-2)
- ✅ FastAPI application structure
- ✅ Multi-tenant database setup
- ✅ API key authentication
- ✅ Redis caching layer
- ✅ `/v1/scan/ingest` endpoint
- ✅ GitHub Action client skeleton

### Phase 1: Core Features (Weeks 3-6)
- ✅ Blast radius endpoint
- ✅ VEX generation endpoint
- ✅ Background workers (NVD, KEV updates)
- ✅ Enrichment service
- ✅ Component lookup endpoint

### Phase 2: Advanced Features (Weeks 7-10)
- ✅ Defense coverage
- ✅ EPSS velocity
- ✅ Exploit likelihood
- ✅ Custom graph queries

### Phase 3: Intelligence (Weeks 11-14)
- ✅ Threat context
- ✅ Dependency risk
- ✅ Compliance gap analysis

### Phase 4: Production Hardening (Weeks 15-16)
- ✅ Load testing
- ✅ Security audit
- ✅ Documentation
- ✅ Beta customer onboarding

---

## Key Architectural Decisions

See Architecture Decision Records (ADRs) in `docs/adr/`:

1. [ADR-001: FastAPI Framework Selection](adr/001-fastapi-framework.md)
2. [ADR-002: Database Separation Strategy](adr/002-database-separation.md)
3. [ADR-003: Caching Strategy](adr/003-caching-strategy.md)

---

## Next Steps

1. Implement Phase 0 (foundation)
2. Deploy to staging environment
3. Implement Phase 1 (core features)
4. Beta testing with 3-5 customers
5. Production launch

---

## Appendix: API Endpoint Details

See [OpenAPI Specification](api/openapi.yml) for complete API documentation.

---

**Document Version:** 1.0.0
**Authors:** Complira Engineering Team
**Review Date:** 2026-03-02
