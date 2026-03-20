# Future-State Runtime Call Stacks (Debug-Trace Style)

Use this document as a future-state (`to-be`) execution model derived from the design basis.
Prefer exact `file:function` frames, explicit branching, and clear state/persistence boundaries.
Do not treat this document as an as-is trace of current code behavior.

## Conventions

- Frame format: `path/to/file.py:function_name(args?)`
- Boundary tags:
  - `[ENTRY]` external entrypoint (API/CLI/event)
  - `[ASYNC]` async boundary (`await`, queue handoff, callback)
  - `[STATE]` in-memory mutation
  - `[IO]` file/network/database/cache IO
  - `[FALLBACK]` non-primary branch
  - `[ERROR]` error path
- Comments: use brief inline comments with `# ...`.
- Do not include legacy/backward-compatibility branches.

## Design Basis

- **Scope Classification:** `Large`
- **Call Stack Version:** `v1`
- **Requirements:** `tickets/in-progress/cloud-saas-architecture/requirements.md` (status `Design-ready`)
- **Source Artifact:** `tickets/in-progress/cloud-saas-architecture/proposed-design.md`
- **Source Design Version:** `v1`
- **Referenced Sections:**
  - Architecture Overview (Target State)
  - File And Module Breakdown
  - BaseGraphService Design (DRY patterns)
  - SOLID Principles Application

## Future-State Modeling Rule (Mandatory)

- Model target design behavior even when current code diverges.
- If migration from as-is to to-be requires transition logic, describe that logic in `Transition Notes`; do not replace the to-be call stack with current flow.

## Use Case Index (Stable IDs)

| use_case_id | Source Type | Requirement ID(s) | Design-Risk Objective | Use Case Name | Coverage Target (Primary/Fallback/Error) |
| --- | --- | --- | --- | --- | --- |
| **UC-001** | Requirement | REQ-001 | N/A | Multi-Tenant Database Setup | Yes/Yes/Yes |
| **UC-002** | Requirement | REQ-002 | N/A | API Authentication & Customer Scoping | Yes/Yes/Yes |
| **UC-003** | Requirement | REQ-003 | N/A | Redis Caching Layer | Yes/Yes/Yes |
| **UC-004** | Requirement | REQ-004 | N/A | Scan Ingestion API | Yes/Yes/Yes |
| **UC-005** | Stage 5 Review | REQ-001 | Zero data loss migration | Database Migration from Local to Cloud | Yes/Yes/Yes |
| **UC-006** | Stage 5 Review | REQ-001 | Concurrent provisioning safety | Customer Database On-Demand Provisioning | Yes/Yes/Yes |

**Coverage Verification:**
- REQ-001 (Multi-tenant database) → UC-001, UC-005, UC-006 ✅
- REQ-002 (API authentication) → UC-002 ✅
- REQ-003 (Caching layer) → UC-003 ✅
- REQ-004 (Scan ingestion) → UC-004 ✅

---

## Transition Notes

### Migration from Local to Cloud

**Temporary Logic (Phase 0):**
1. Local database (`complira_graph`) remains operational during cloud deployment
2. Reference data export → cloud import process runs once (not part of application runtime)
3. Local application and cloud API coexist (no forced migration)

**Cloud Database Initialization:**
```python
# One-time setup script (not application runtime)
# scripts/init_cloud_databases.py

1. Create complira_reference database
2. Import local data via arangorestore
3. Verify document counts match
4. Create first test customer database: complira_customer_test
5. Create indexes for customer-scoped queries
```

**Retirement Plan:**
- Local database kept as read-only backup for 30 days post-migration
- After validation period, local DB can be decommissioned
- No runtime temporary logic in application code

---

## Use Case: UC-001 Multi-Tenant Database Setup

### Goal

Initialize cloud ArangoDB cluster with separated reference and customer databases, enabling multi-tenant SaaS architecture with automatic customer scoping in all database queries.

### Preconditions

- Cloud ArangoDB cluster deployed (AWS/GCP/Azure)
- Network connectivity established
- Admin credentials available in environment variables

### Expected Outcome

**AC-001:** `complira_reference` database created with existing 335K+ docs migrated
**AC-002:** Customer database template created (`complira_customer_<id>`)
**AC-003:** Cross-database AQL queries work (customer → reference joins)

### Primary Runtime Call Stack

**Scenario:** Application startup - database connection initialization

```text
[ENTRY] src/api/main.py:create_app()
├── src/api/core/config.py:CloudSettings.from_env() [IO env vars]
│   ├── ARANGO_HOST, ARANGO_USER, ARANGO_PASSWORD
│   ├── REDIS_URL
│   └── API_KEY_SECRET
│
├── src/api/core/database.py:init_databases(settings) [IO database]
│   ├── src/api/core/database.py:connect_to_arango(settings.arango_host)
│   │   └── arango.ArangoClient(hosts=settings.arango_host) [IO network]
│   │
│   ├── src/api/core/database.py:ensure_reference_db(client) [IO database]
│   │   ├── client.db('complira_reference', verify=True) [IO verify]
│   │   ├── # Verify collections exist (27 collections)
│   │   ├── db.collection('vulnerabilities').count() [IO query]
│   │   └── # Expected: 335K+ documents
│   │
│   ├── src/api/core/database.py:create_customer_db_router() [STATE]
│   │   └── # Returns function: customer_id → Database
│   │
│   └── src/api/core/database.py:ensure_indexes() [IO database]
│       ├── # Create indexes for customer-scoped queries
│       ├── db.collection('components').add_persistent_index(['customer_id', 'cpe'])
│       └── db.collection('scan_findings').add_persistent_index(['customer_id', 'scan_session_id'])
│
└── src/api/main.py:app.state.db_router = db_router [STATE]
    # Store database router in FastAPI app state
```

### Branching / Fallback Paths

#### Fallback Path 1: Reference Database Not Found

```text
[FALLBACK] if complira_reference does not exist
src/api/core/database.py:ensure_reference_db(client)
├── [ERROR] raise DatabaseNotFoundError("complira_reference database not initialized")
│   # Application startup fails - deployment error
│   # Expected: Admin runs migration script first
│
└── src/api/main.py:handle_startup_error(exc) [ERROR]
    ├── logger.critical("Database initialization failed", error=str(exc))
    └── sys.exit(1)
```

#### Fallback Path 2: Customer Database Creation (On-Demand)

```text
[FALLBACK] if complira_customer_<id> does not exist
src/api/core/database.py:get_customer_db(customer_id) [IO database]
├── # Called during first API request from new customer
├── src/api/core/database.py:_create_customer_db(customer_id)
│   ├── client.create_database(f'complira_customer_{customer_id}')
│   ├── src/api/core/database.py:_create_customer_collections(db)
│   │   ├── db.create_collection('components', edge=False)
│   │   ├── db.create_collection('scan_sessions', edge=False)
│   │   ├── db.create_collection('scan_findings', edge=False)
│   │   ├── db.create_collection('component_has_finding', edge=True)
│   │   └── db.create_collection('found_in_scan', edge=True)
│   │
│   └── src/api/core/database.py:_create_customer_indexes(db)
│       ├── db.collection('components').add_persistent_index(['customer_id', 'cpe'])
│       └── db.collection('scan_findings').add_persistent_index(['customer_id', 'scan_session_id'])
│
└── # Return newly created database
```

#### Error Path 1: Database Connection Failure

```text
[ERROR] if ArangoDB connection fails
src/api/core/database.py:connect_to_arango(host)
├── # Network timeout, wrong credentials, cluster down
├── ConnectionError raised by arango.ArangoClient
│
└── src/api/main.py:handle_startup_error(exc) [ERROR]
    ├── logger.critical("Cannot connect to ArangoDB", host=host, error=str(exc))
    ├── # Retry logic (3 attempts with exponential backoff)
    └── sys.exit(1) if all retries fail
```

### State And Data Transformations

**Environment Variables → CloudSettings:**
```python
# Input:
ARANGO_HOST="http://arango-cluster:8529"
ARANGO_USER="root"
ARANGO_PASSWORD="<secret>"
REDIS_URL="redis://redis:6379"

# Output:
CloudSettings(
    arango_host="http://arango-cluster:8529",
    arango_user="root",
    arango_password="<secret>",  # Hashed in memory, never logged
    redis_url="redis://redis:6379"
)
```

**Customer ID → Database Name:**
```python
# Input:
customer_id = "cust_001"

# Transformation:
database_name = f"complira_customer_{customer_id}"
# Output: "complira_customer_cust_001"
```

**Cross-Database Query Pattern:**
```python
# Query customer components with reference CVE data
query = """
FOR comp IN complira_customer_001.components
    FILTER comp.customer_id == @customer_id
    FOR vuln IN complira_reference.vulnerabilities
        FILTER vuln.cve_id == comp.cve_id
        RETURN {component: comp, vulnerability: vuln}
"""
# Joins customer DB with reference DB seamlessly
```

### Observability And Debug Points

**Logs emitted at:**
- Database connection attempt: `INFO "Connecting to ArangoDB" host=<host>`
- Reference DB verification: `INFO "Reference database verified" doc_count=335398`
- Customer DB creation: `INFO "Created customer database" customer_id=<id> db_name=<name>`
- Index creation: `INFO "Created indexes" collection=<name> fields=<fields>`
- Connection failure: `CRITICAL "Database connection failed" error=<err>`

**Metrics/counters updated at:**
- `db_connections_total{type="reference"}` - Total reference DB connections
- `db_connections_total{type="customer"}` - Total customer DB connections
- `db_customer_databases_total` - Number of customer databases created
- `db_connection_errors_total` - Connection failures

**Tracing spans:**
- `database.init` - Full database initialization
- `database.create_customer_db` - Customer DB creation

### Design Smells / Gaps

- **Any legacy/backward-compatibility branch present?** No - clean slate architecture
- **Any naming-to-responsibility drift detected?** No - all names match responsibilities

### Open Questions

- Q: How to handle database schema migrations (reference DB schema changes)?
  - A: Use Alembic-style migrations, separate from customer DBs
- Q: Maximum number of customer databases (cost/scaling)?
  - A: Monitor in Phase 1; consider shared-DB multi-tenancy if cost prohibitive

### Coverage Status

- **Primary Path:** `Covered` (application startup, database initialization)
- **Fallback Path:** `Covered` (on-demand customer DB creation, retry logic)
- **Error Path:** `Covered` (connection failure, missing reference DB)

---

## Use Case: UC-002 API Authentication & Customer Scoping

### Goal

Authenticate API requests using API keys, automatically extract customer ID, and inject customer context into all endpoints via FastAPI dependency injection (AD-004).

### Preconditions

- Database initialized (UC-001 complete)
- Customer record exists in `customer_profiles` collection
- API key generated and provided to customer

### Expected Outcome

**AC-004:** API key validates and maps to customer_id
**AC-005:** All database queries auto-inject customer_id filter
**AC-006:** Customers cannot access other customers' data

### Primary Runtime Call Stack

**Scenario:** Authenticated API request to enrichment endpoint

```text
[ENTRY] HTTP POST /v1/enrich
├── src/api/main.py:app (FastAPI instance)
│
├── src/api/v1/router.py:api_router
│   # Routes to v1/endpoints/enrich.py
│
├── src/api/v1/endpoints/enrich.py:enrich_endpoint(request, customer, service)
│   ├── [DEPENDENCY INJECTION] customer: Customer = Depends(get_current_customer)
│   │   # FastAPI automatically calls get_current_customer before endpoint
│   │
│   └── src/api/core/dependencies.py:get_current_customer(api_key: str)
│       ├── [ASYNC] await src/api/core/security.py:validate_api_key(api_key) [IO cache + DB]
│       │   ├── src/api/core/cache.py:cache.get(f"api_key:{api_key}") [IO Redis]
│       │   │   └── [FALLBACK if cache miss] → database lookup
│       │   │
│       │   ├── [CACHE MISS] src/api/core/database.py:get_reference_db()
│       │   │   └── db.collection('customer_profiles').find_one({'api_key_hash': hash(api_key)}) [IO query]
│       │   │
│       │   ├── src/api/core/security.py:verify_api_key_hash(api_key, stored_hash)
│       │   │   └── bcrypt.checkpw(api_key.encode(), stored_hash.encode()) [CPU intensive]
│       │   │
│       │   ├── [STATE] customer_profile = {...}
│       │   │
│       │   └── src/api/core/cache.py:cache.set(f"api_key:{api_key}", customer_profile, ttl=3600)
│       │       # Cache customer profile for 1 hour
│       │
│       ├── src/api/core/dependencies.py:_build_customer_object(profile)
│       │   └── Customer(id=profile['id'], name=profile['name'], ...)
│       │
│       └── # Return Customer object to endpoint
│
├── # Endpoint receives customer: Customer automatically injected
├── src/api/v1/endpoints/enrich.py:service.enrich_cves(request.cve_ids, customer.id)
│   # customer.id automatically passed to service layer
│
└── src/api/v1/endpoints/enrich.py:return APIResponse(success=True, data=result)
```

### Branching / Fallback Paths

#### Fallback Path 1: Cache Hit (Fast Path)

```text
[FALLBACK] if API key found in Redis cache
src/api/core/security.py:validate_api_key(api_key)
├── src/api/core/cache.py:cache.get(f"api_key:{api_key}") [IO Redis]
│   └── # Cache hit! Return cached customer profile
│
└── src/api/core/dependencies.py:_build_customer_object(cached_profile)
    # Skip database query - 10x faster
```

#### Error Path 1: Invalid API Key

```text
[ERROR] if API key not found or invalid
src/api/core/security.py:validate_api_key(api_key)
├── db.collection('customer_profiles').find_one({'api_key_hash': hash(api_key)})
│   └── # Returns None - API key not found
│
├── [ERROR] raise HTTPException(status_code=401, detail="Invalid API key")
│
└── src/api/main.py:http_exception_handler(request, exc)
    ├── logger.warning("Authentication failed", api_key_prefix=api_key[:8])
    └── return JSONResponse(status_code=401, content={"success": False, "error": "Unauthorized"})
```

#### Error Path 2: Customer Database Not Found

```text
[ERROR] if customer database does not exist
src/api/core/database.py:get_customer_db(customer.id)
├── # Customer authenticated, but database missing (data corruption?)
├── client.db(f'complira_customer_{customer.id}', verify=True)
│   └── # Raises DatabaseNotFoundError
│
├── [FALLBACK] src/api/core/database.py:_create_customer_db(customer.id)
│   # Auto-create database on first access (idempotent)
│
└── # Return newly created database
```

#### Error Path 3: Concurrent Request Race Condition

```text
[ERROR] if two requests from same customer arrive simultaneously (both cache miss)
src/api/core/security.py:validate_api_key(api_key)
├── Request A: cache miss → database query [IO]
├── Request B: cache miss → database query [IO] (parallel)
│   # Both queries execute in parallel (acceptable)
│
├── Request A: cache.set(...) [IO Redis]
├── Request B: cache.set(...) [IO Redis] (overwrites A)
│   # Last-write-wins - acceptable (idempotent data)
│
└── # No functional issue - both requests succeed
```

### State And Data Transformations

**HTTP Header → API Key:**
```python
# Input:
Authorization: Bearer sk-complira-cust001-abc123xyz

# Extraction:
api_key = request.headers.get("Authorization").replace("Bearer ", "")
# Output: "sk-complira-cust001-abc123xyz"
```

**API Key → Customer Profile:**
```python
# Input:
api_key = "sk-complira-cust001-abc123xyz"
api_key_hash = hash(api_key)  # bcrypt hash

# Database query:
customer_profile = {
    "_key": "cust_001",
    "id": "cust_001",
    "name": "Acme Corp",
    "api_key_hash": "$2b$12$...",  # bcrypt hash
    "database_name": "complira_customer_cust_001",
    "tier": "pro"
}

# Output (cached):
Customer(
    id="cust_001",
    name="Acme Corp",
    database_name="complira_customer_cust_001",
    tier="pro"
)
```

**Customer ID → Database Context (Automatic Injection):**
```python
# Service layer receives customer_id automatically
async def enrich_cves(self, cve_ids: List[str], customer_id: str):
    # All database queries auto-scoped to customer_id
    query = """
    FOR finding IN scan_findings
        FILTER finding.customer_id == @customer_id
        FILTER finding.cve_id IN @cve_ids
        RETURN finding
    """
    # customer_id automatically injected - no manual checks!
```

### Observability And Debug Points

**Logs emitted at:**
- Authentication attempt: `INFO "API key validation" api_key_prefix=<first 8 chars>`
- Cache hit: `DEBUG "API key cache hit" customer_id=<id>`
- Cache miss: `DEBUG "API key cache miss, querying database" api_key_prefix=<prefix>`
- Authentication success: `INFO "Customer authenticated" customer_id=<id> customer_name=<name>`
- Authentication failure: `WARNING "Invalid API key" api_key_prefix=<prefix> source_ip=<ip>`

**Metrics/counters updated at:**
- `auth_requests_total{result="success"}` - Successful authentications
- `auth_requests_total{result="failure"}` - Failed authentications
- `auth_cache_hits_total` - API key cache hits
- `auth_cache_misses_total` - API key cache misses
- `auth_duration_seconds` - Authentication latency histogram

**Tracing spans:**
- `auth.validate_api_key` - Full authentication process
- `auth.cache_lookup` - Redis cache lookup
- `auth.database_query` - Database customer profile query

### Design Smells / Gaps

- **Any legacy/backward-compatibility branch present?** No
- **Any naming-to-responsibility drift detected?** No
- **Security concern:** API keys in logs?
  - Mitigation: Only log first 8 characters (`api_key[:8]`)

### Open Questions

- Q: API key rotation strategy?
  - A: Phase 0 supports manual rotation (admin updates customer_profiles)
  - A: Phase 2 adds automated rotation API
- Q: Rate limiting per API key?
  - A: Phase 0 uses global rate limit (100 req/min)
  - A: Phase 2 adds per-customer tier-based limits

### Coverage Status

- **Primary Path:** `Covered` (successful authentication with cache miss + cache hit)
- **Fallback Path:** `Covered` (cache hit fast path, on-demand DB creation)
- **Error Path:** `Covered` (invalid API key, database not found, concurrent requests)

---

## Use Case: UC-003 Redis Caching Layer

### Goal

Implement Redis caching with declarative `@cache()` decorator (AD-005) to achieve > 70% cache hit ratio for reference data queries, reducing database load and improving API response times.

### Preconditions

- Redis cluster deployed and accessible
- Database initialized (UC-001 complete)
- API authentication working (UC-002 complete)

### Expected Outcome

**AC-007:** Reference data cached (CVE enrichment, 6-hour TTL)
**AC-008:** Customer-specific data cached (1-hour TTL)
**AC-009:** Cache invalidation on reference data updates

### Primary Runtime Call Stack

**Scenario:** CVE enrichment request with cache miss → cache population

```text
[ENTRY] HTTP POST /v1/enrich {"cve_ids": ["CVE-2021-44228"]}
├── src/api/v1/endpoints/enrich.py:enrich_endpoint(request, customer, service)
│   ├── [ASYNC] await service.enrich_cves(request.cve_ids, customer.id)
│   │
│   └── src/api/services/enrichment.py:enrich_cves(cve_ids, customer_id)
│       ├── # Decorated with @cache
│       ├── src/api/core/cache.py:cache_decorator_wrapper()
│       │   ├── src/api/core/cache.py:_build_cache_key(func_name, args)
│       │   │   └── cache_key = f"enrich:CVE-2021-44228"
│       │   │
│       │   ├── [ASYNC] await self.cache_service.get(cache_key) [IO Redis]
│       │   │   └── redis_client.get(cache_key) [IO network]
│       │   │       # Returns None - cache miss
│       │   │
│       │   ├── [CACHE MISS] logger.debug("Cache miss", key=cache_key)
│       │   │
│       │   ├── # Execute actual function (database query)
│       │   ├── [ASYNC] result = await original_function(cve_ids, customer_id)
│       │   │   └── src/api/services/enrichment.py:_enrich_cves_impl(cve_ids, customer_id)
│       │   │       ├── src/api/services/base.py:traverse(start, edges, max_depth) [IO database]
│       │   │       │   # Traverse: CVE → CWE → CAPEC → ATT&CK → Threat Groups
│       │   │       │   └── db.aql.execute(traversal_query) [IO query]
│       │   │       │
│       │   │       └── # Return enriched CVE data
│       │   │
│       │   ├── [ASYNC] await self.cache_service.set(cache_key, result, ttl=21600)
│       │   │   # TTL = 6 hours (reference data changes slowly)
│       │   │   └── redis_client.setex(cache_key, 21600, json.dumps(result)) [IO Redis]
│       │   │
│       │   └── # Return result to caller
│       │
│       └── # Enrichment complete (with cache population)
│
└── src/api/v1/endpoints/enrich.py:return APIResponse(
        success=True,
        data=result,
        metadata={'cache_hit': False, 'execution_time_ms': 450}
    )
```

### Branching / Fallback Paths

#### Fallback Path 1: Cache Hit (Fast Path - 70% of requests)

```text
[FALLBACK] if enrichment data found in cache
src/api/core/cache.py:cache_decorator_wrapper()
├── [ASYNC] await self.cache_service.get(cache_key) [IO Redis]
│   └── redis_client.get("enrich:CVE-2021-44228")
│       # Returns cached JSON data
│
├── logger.debug("Cache hit", key=cache_key)
│
├── # Deserialize cached data
├── result = json.loads(cached_data)
│
└── # Return immediately - NO database query!
    # Response time: ~10ms (vs ~450ms cache miss)
```

#### Fallback Path 2: Redis Connection Failure (Graceful Degradation)

```text
[ERROR] if Redis is unavailable
src/api/core/cache.py:cache_decorator_wrapper()
├── [ASYNC] await self.cache_service.get(cache_key)
│   ├── redis_client.get(cache_key) [IO Redis]
│   │   └── [ERROR] redis.exceptions.ConnectionError raised
│   │
│   └── src/api/core/cache.py:_handle_redis_error(exc)
│       ├── logger.warning("Redis unavailable, falling through to database", error=str(exc))
│       └── # Return None - treat as cache miss
│
├── # Execute function normally (database query)
├── result = await original_function(cve_ids, customer_id)
│
└── # Try to cache result (will fail, but don't raise exception)
    └── await self.cache_service.set(cache_key, result, ttl=21600)
        # Fails silently - logs warning but doesn't break request
```

#### Error Path 1: Cache Serialization Failure

```text
[ERROR] if enrichment result cannot be serialized to JSON
src/api/core/cache.py:cache_decorator_wrapper()
├── result = await original_function(cve_ids, customer_id)
│   # Function returns data with non-serializable objects
│
├── [ASYNC] await self.cache_service.set(cache_key, result, ttl=21600)
│   ├── json.dumps(result) [STATE]
│   │   └── [ERROR] TypeError: Object of type 'datetime' is not JSON serializable
│   │
│   └── src/api/core/cache.py:_handle_serialization_error(exc)
│       ├── logger.error("Cache serialization failed", key=cache_key, error=str(exc))
│       └── # Don't cache - return result anyway
│
└── # Return result to caller (even though caching failed)
```

#### Fallback Path 3: Cache Invalidation (Reference Data Update)

```text
[FALLBACK] when reference data updated by worker
src/workers/flows/reference_sync.py:sync_nvd_data()
├── # Worker updates vulnerabilities collection in reference DB
├── src/workers/tasks/invalidate_cache.py:invalidate_pattern("enrich:*")
│   ├── redis_client.keys("enrich:*") [IO Redis]
│   │   # Find all enrichment cache keys
│   │
│   └── redis_client.delete(*keys) [IO Redis]
│       # Bulk delete all enrichment cache entries
│
└── logger.info("Cache invalidated", pattern="enrich:*", keys_deleted=count)
    # Next enrichment request will be cache miss - repopulates with fresh data
```

### State And Data Transformations

**Function Arguments → Cache Key:**
```python
# Input:
func_name = "enrich_cves"
cve_ids = ["CVE-2021-44228", "CVE-2023-0286"]
customer_id = "cust_001"  # Not included in key for reference data!

# Cache key generation:
cache_key = f"{func_name}:{':'.join(sorted(cve_ids))}"
# Output: "enrich_cves:CVE-2021-44228:CVE-2023-0286"
# Note: Reference data cached globally (not per-customer)
```

**Enrichment Result → Cached JSON:**
```python
# Input (Python objects):
result = {
    "cve_id": "CVE-2021-44228",
    "cvss_v3_score": 10.0,
    "weaknesses": [{"cwe_id": "CWE-502", "name": "Deserialization"}],
    "attack_techniques": [{"technique_id": "T1190", "name": "Exploit Public-Facing"}],
    "threat_groups": ["APT41", "APT29"]
}

# Serialization:
cached_value = json.dumps(result)
# Output (stored in Redis): '{"cve_id":"CVE-2021-44228","cvss_v3_score":10.0,...}'

# Redis storage:
redis.setex(key="enrich_cves:CVE-2021-44228", time=21600, value=cached_value)
# TTL: 21600 seconds = 6 hours
```

**Cache Hit Ratio Calculation:**
```python
# Metrics collection:
cache_hits = 700  # Requests served from cache
cache_misses = 300  # Requests queried database
total_requests = 1000

# Calculation:
cache_hit_ratio = (cache_hits / total_requests) * 100
# Output: 70% (meets target!)
```

### Observability And Debug Points

**Logs emitted at:**
- Cache hit: `DEBUG "Cache hit" key=<key> ttl_remaining=<seconds>`
- Cache miss: `DEBUG "Cache miss, executing function" key=<key>`
- Cache write: `DEBUG "Cache write" key=<key> ttl=<seconds> size_bytes=<size>`
- Redis error: `WARNING "Redis unavailable, falling through" error=<err>`
- Serialization error: `ERROR "Cache serialization failed" key=<key> error=<err>`
- Cache invalidation: `INFO "Cache invalidated" pattern=<pattern> keys_deleted=<count>`

**Metrics/counters updated at:**
- `cache_requests_total{result="hit"}` - Cache hits
- `cache_requests_total{result="miss"}` - Cache misses
- `cache_writes_total{status="success"}` - Successful cache writes
- `cache_writes_total{status="failure"}` - Failed cache writes (Redis down, serialization error)
- `cache_hit_ratio` - Gauge: (hits / total) * 100
- `cache_invalidations_total` - Cache invalidation events

**Tracing spans:**
- `cache.get` - Cache lookup
- `cache.set` - Cache write
- `cache.invalidate` - Cache invalidation

### Design Smells / Gaps

- **Any legacy/backward-compatibility branch present?** No
- **Any naming-to-responsibility drift detected?** No
- **Performance consideration:** Cache stampede on popular CVEs?
  - Mitigation: Use Redis SET NX (set-if-not-exists) to prevent concurrent cache writes
  - Future: Add request coalescing (multiple concurrent requests for same CVE coalesce into one DB query)

### Open Questions

- Q: How to handle cache warming (pre-populate common CVEs)?
  - A: Phase 0 uses lazy caching (populate on first request)
  - A: Phase 2 adds cache warming worker (pre-populate top 1000 CVEs)
- Q: Redis memory limits (eviction policy)?
  - A: Use `allkeys-lru` eviction policy (evict least-recently-used keys when memory full)
  - A: Monitor Redis memory usage in Phase 1

### Coverage Status

- **Primary Path:** `Covered` (cache miss → database query → cache population)
- **Fallback Path:** `Covered` (cache hit fast path, Redis unavailable graceful degradation, cache invalidation)
- **Error Path:** `Covered` (Redis connection failure, serialization error)

---

## Use Case: UC-004 Scan Ingestion API

### Goal

Accept scanner output (SARIF/CycloneDX) via POST /v1/scan/ingest, normalize findings into canonical schema, extract components from SBOM, create scan session, and return session ID for subsequent enrichment requests.

### Preconditions

- Database initialized (UC-001 complete)
- Customer authenticated (UC-002 complete)
- Caching layer operational (UC-003 complete)

### Expected Outcome

**AC-010:** Parse SARIF format correctly
**AC-011:** Parse CycloneDX SBOM format correctly
**AC-012:** Create scan_session document
**AC-013:** Create scan_findings documents (normalized schema)
**AC-014:** Extract components from SBOM
**AC-015:** Create component_has_finding edges
**AC-016:** Return scan_session_id

### Primary Runtime Call Stack

**Scenario:** Customer uploads SARIF scan results via API

```text
[ENTRY] HTTP POST /v1/scan/ingest
Headers: Authorization: Bearer sk-complira-cust001-xyz
Body: {
    "format": "sarif",
    "scan_type": "sast",
    "payload": "<SARIF JSON string>",
    "metadata": {"repo": "acme/webapp", "commit_sha": "abc123", "branch": "main"}
}

├── src/api/v1/router.py:api_router
│   # Routes to /scan/ingest endpoint
│
├── src/api/v1/endpoints/scan.py:ingest_scan_endpoint(request, customer, service)
│   ├── [DEPENDENCY INJECTION] customer: Customer = Depends(get_current_customer)
│   │   # Customer authentication (UC-002)
│   │
│   ├── [DEPENDENCY INJECTION] service: ScanIngestionService = Depends(get_scan_service)
│   │
│   ├── src/api/models/requests/scan.py:ScanIngestRequest.parse_obj(body)
│   │   # Pydantic validation
│   │   ├── format in ["sarif", "cyclonedx", "csv", "json"] ✓
│   │   ├── scan_type in ["sast", "dast", "sca", "container", "sbom"] ✓
│   │   └── payload is valid JSON string ✓
│   │
│   ├── [ASYNC] await service.ingest_scan(customer_id=customer.id, scan_data=request)
│   │   └── src/api/services/scan.py:ingest_scan(customer_id, scan_data)
│   │       ├── src/api/services/scan.py:_create_scan_session(customer_id, scan_data.metadata)
│   │       │   ├── scan_session_id = uuid.uuid4().hex
│   │       │   ├── scan_session = {
│   │       │   │     "_key": scan_session_id,
│   │       │   │     "customer_id": customer_id,
│   │       │   │     "scan_type": scan_data.scan_type,
│   │       │   │     "timestamp": datetime.utcnow().isoformat(),
│   │       │   │     "metadata": scan_data.metadata
│   │       │   │   }
│   │       │   └── [IO] db.collection('scan_sessions').insert(scan_session)
│   │       │
│   │       ├── src/api/parsers/factory.py:ParserFactory.get_parser(scan_data.format)
│   │       │   # Factory pattern (OCP) - returns appropriate parser
│   │       │   └── if format == "sarif":
│   │       │       └── return SARIFParser()  # Parser instantiation
│   │       │   └── elif format == "cyclonedx":
│   │       │       └── return CycloneDXParser()
│   │       │   └── else:
│   │       │       └── raise ValueError(f"Unsupported format: {format}")
│   │       │
│   │       ├── [DELEGATION] parser.parse(scan_data.payload) → ParsedScanData
│   │       │   # Parser handles format-specific logic (SRP)
│   │       │   # Service delegates, doesn't know format details (DIP)
│   │       │   │
│   │       │   └── [DISPATCH to format-specific parser]
│   │       │       ├── if parser is SARIFParser:
│   │       │       │   └── src/api/parsers/sarif.py:SARIFParser.parse(payload)
│   │       │       │       ├── [VALIDATION] parser.validate(payload) → True
│   │       │       │       ├── sarif_json = json.loads(payload)
│   │       │       │       ├── [EXTRACTION] parser._extract_findings(sarif_json)
│   │       │       │       │   └── for run in sarif_json['runs']:
│   │       │       │       │       for result in run['results']:
│   │       │       │       │           ├── ParsedFinding(
│   │       │       │       │           │     cve_id=result['ruleId'],
│   │       │       │       │           │     severity=result['level'].upper(),
│   │       │       │       │           │     description=result['message']['text'],
│   │       │       │       │           │     location=parser._extract_location(result),
│   │       │       │       │           │     scan_type="sarif",
│   │       │       │       │           │     raw_data=result
│   │       │       │       │           │   )
│   │       │       │       │
│   │       │       │       ├── [EXTRACTION] parser._extract_metadata(sarif_json)
│   │       │       │       │
│   │       │       │       └── return ParsedScanData(
│   │       │       │             tool_name=run['tool']['driver']['name'],
│   │       │       │             tool_version=run['tool']['driver']['version'],
│   │       │       │             scan_timestamp=metadata['timestamp'],
│   │       │       │             findings=[...],
│   │       │       │             components=[],  # SARIF has no SBOM data
│   │       │       │             metadata={...}
│   │       │       │           )
│   │       │       │
│   │       │       └── elif parser is CycloneDXParser:
│   │       │           └── src/api/parsers/cyclonedx.py:CycloneDXParser.parse(payload)
│   │       │               ├── [VALIDATION] parser.validate(payload) → True
│   │       │               ├── sbom_json = json.loads(payload)
│   │       │               ├── [EXTRACTION] parser._extract_findings(sbom_json)
│   │       │               │   └── for component in sbom_json['components']:
│   │       │               │       for vuln in component['vulnerabilities']:
│   │       │               │           ├── ParsedFinding(
│   │       │               │           │     cve_id=vuln['id'],
│   │       │               │           │     severity=parser._map_severity(vuln['ratings'][0]['severity']),
│   │       │               │           │     description=vuln['description'],
│   │       │               │           │     location=f"{component['name']}@{component['version']}",
│   │       │               │           │     scan_type="cyclonedx",
│   │       │               │           │     raw_data=vuln
│   │       │               │           │   )
│   │       │               │
│   │       │               ├── [EXTRACTION] parser._extract_components(sbom_json)
│   │       │               │
│   │       │               └── return ParsedScanData(
│   │       │                     tool_name=metadata['tools'][0]['name'],
│   │       │                     tool_version=metadata['tools'][0]['version'],
│   │       │                     scan_timestamp=metadata['timestamp'],
│   │       │                     findings=[...],
│   │       │                     components=[...],  # CycloneDX has SBOM
│   │       │                     metadata={...}
│   │       │                   )
│   │       │
│   │       ├── [STATE] parsed_data: ParsedScanData
│   │       │   # Normalized output from parser (all formats return same schema)
│   │       │
│   │       ├── [NOTE] Parser abstraction benefits (Stage 5 Round 1 fix):
│   │       │   # - SRP: Service doesn't contain format-specific logic
│   │       │   # - OCP: Add new parsers (OSV, VEX) without modifying service
│   │       │   # - DIP: Service depends on IScanParser abstraction
│   │       │   # - DRY: BaseScanParser provides shared validation/error handling
│   │       │
│   │       ├── src/api/services/scan.py:_store_findings(customer_id, scan_session_id, parsed_data.findings)
│   │       │   # Parser already normalized findings, just add DB keys
│   │       │   └── for parsed_finding in parsed_data.findings:
│   │       │       ├── finding_doc = {
│   │       │       │     "_key": uuid.uuid4().hex,
│   │       │       │     "customer_id": customer_id,
│   │       │       │     "scan_session_id": scan_session_id,
│   │       │       │     "cve_id": parsed_finding.cve_id,  # Already normalized by parser
│   │       │       │     "severity": parsed_finding.severity,
│   │       │       │     "description": parsed_finding.description,
│   │       │       │     "location": parsed_finding.location,
│   │       │       │     "scan_type": parsed_finding.scan_type,
│   │       │       │     "tool_name": parsed_finding.tool_name,
│   │       │       │     "raw_data": parsed_finding.raw_data  # Original finding for traceability
│   │       │       │   }
│   │       │
│   │       ├── [IO BULK] db.collection('scan_findings').import_bulk(finding_docs)
│   │       │   # Bulk insert for performance (all findings in one transaction)
│   │       │   # Returns: {"created": 47, "errors": 0}
│   │       │
│   │       ├── src/api/services/scan.py:_store_components(customer_id, scan_session_id, parsed_data.components)
│   │       │   # Only if components exist (CycloneDX has them, SARIF doesn't)
│   │       │   └── if parsed_data.components:
│   │       │       └── for component in parsed_data.components:
│   │       │       ├── component_key = hashlib.sha256(f"{component['name']}:{component['version']}".encode()).hexdigest()
│   │       │       ├── component_doc = {
│   │       │       │     "_key": component_key,
│   │       │       │     "customer_id": customer_id,
│   │       │       │     "name": component['name'],
│   │       │       │     "version": component['version'],
│   │       │       │     "purl": component.get('purl'),
│   │       │       │     "cpe": component.get('cpe'),
│   │       │       │     "first_seen": datetime.utcnow().isoformat(),
│   │       │       │     "last_seen": datetime.utcnow().isoformat(),
│   │       │       │     "scan_session_id": scan_session_id
│   │       │       │   }
│   │       │       └── [IO] db.collection('components').insert(component_doc, overwrite_mode='update')
│   │       │           # Upsert: insert if new, update last_seen if exists
│   │       │
│   │       ├── src/api/services/scan.py:_create_edges(normalized_findings, parsed_components, customer_id)
│   │       │   ├── # Create component_has_finding edges
│   │       │   ├── for finding in normalized_findings:
│   │       │   │   ├── matching_component = self._match_finding_to_component(finding, parsed_components)
│   │       │   │   └── if matching_component:
│   │       │   │       └── edge = {
│   │       │   │             "_from": f"components/{matching_component['_key']}",
│   │       │   │             "_to": f"scan_findings/{finding['_key']}",
│   │       │   │             "customer_id": customer_id
│   │       │   │           }
│   │       │   │
│   │       │   ├── [IO BULK] db.collection('component_has_finding').import_bulk(edges)
│   │       │   │
│   │       │   └── # Create found_in_scan edges (findings → scan_session)
│   │       │       └── [IO BULK] db.collection('found_in_scan').import_bulk(scan_edges)
│   │       │
│   │       └── # Return statistics
│   │           └── [STATE] return {
│   │                 "scan_session_id": scan_session_id,
│   │                 "findings_count": len(normalized_findings),
│   │                 "components_count": len(parsed_components),
│   │                 "new_components": new_component_count
│   │               }
│   │
│   └── src/api/v1/endpoints/scan.py:return APIResponse(
│           success=True,
│           data=result,
│           metadata={'execution_time_ms': 1200}
│       )
│
└── HTTP 200 OK
    Body: {
        "success": true,
        "data": {
            "scan_session_id": "abc123xyz",
            "findings_count": 47,
            "components_count": 312,
            "new_components": 8
        },
        "metadata": {"execution_time_ms": 1200}
    }
```

### Branching / Fallback Paths

#### Fallback Path 1: Duplicate Scan (Idempotency)

```text
[FALLBACK] if scan with same commit_sha already exists
src/api/services/scan.py:ingest_scan(customer_id, scan_data)
├── src/api/services/scan.py:_check_duplicate_scan(customer_id, scan_data.metadata)
│   ├── [IO] db.aql.execute("""
│   │   FOR session IN scan_sessions
│   │       FILTER session.customer_id == @customer_id
│   │       FILTER session.metadata.commit_sha == @commit_sha
│   │       RETURN session
│   │   """)
│   └── # Returns existing scan session
│
├── logger.info("Duplicate scan detected", commit_sha=scan_data.metadata['commit_sha'])
│
└── # Return existing scan_session_id (don't re-process)
    # Idempotent: same input → same output
```

#### Fallback Path 2: Unsupported SARIF Version

```text
[FALLBACK] if SARIF version is newer than supported
src/api/services/parsers/sarif.py:parse_sarif(payload)
├── sarif_json = json.loads(payload)
├── version = sarif_json.get('version', '2.1.0')
│
├── if version not in SUPPORTED_VERSIONS:
│   ├── logger.warning("Unsupported SARIF version", version=version, supported=SUPPORTED_VERSIONS)
│   └── # Try to parse anyway (best-effort)
│       # If schema changed significantly, parsing may fail
│
└── # Continue parsing (graceful degradation)
```

#### Error Path 1: Malformed SARIF JSON

```text
[ERROR] if SARIF payload cannot be parsed
src/api/services/parsers/sarif.py:parse_sarif(payload)
├── sarif_json = json.loads(payload)
│   └── [ERROR] json.JSONDecodeError: Expecting value: line 42 column 15
│
├── [ERROR] raise ValueError("Invalid SARIF format: malformed JSON")
│
└── src/api/v1/endpoints/scan.py:handle_value_error(exc)
    ├── logger.error("SARIF parsing failed", error=str(exc))
    └── raise HTTPException(status_code=400, detail=f"Invalid SARIF: {str(exc)}")
```

#### Error Path 2: Missing Required Fields

```text
[ERROR] if SARIF missing required fields (runs[].results)
src/api/services/parsers/sarif.py:parse_sarif(payload)
├── sarif_json = json.loads(payload)
├── runs = sarif_json.get('runs', [])
│   # Empty list - no scan results
│
├── if not runs:
│   └── [ERROR] raise ValueError("SARIF contains no runs")
│
└── src/api/v1/endpoints/scan.py:handle_value_error(exc)
    └── raise HTTPException(status_code=400, detail="SARIF contains no scan results")
```

#### Error Path 3: Database Insert Failure (Duplicate Key)

```text
[ERROR] if scan_session_id collision (extremely unlikely with UUID)
src/api/services/scan.py:_create_scan_session(customer_id, metadata)
├── scan_session_id = uuid.uuid4().hex
├── [IO] db.collection('scan_sessions').insert(scan_session)
│   └── [ERROR] arango.exceptions.DocumentInsertError: unique constraint violated
│
├── [RETRY] Regenerate scan_session_id and retry (max 3 attempts)
│   └── scan_session_id = uuid.uuid4().hex  # Try new UUID
│
└── if all retries fail:
    └── [ERROR] raise HTTPException(status_code=500, detail="Failed to create scan session")
```

### State And Data Transformations

**SARIF Payload → Normalized Findings:**
```python
# Input (SARIF JSON):
{
    "version": "2.1.0",
    "runs": [{
        "results": [{
            "ruleId": "CVE-2021-44228",
            "message": {"text": "Log4j vulnerability detected"},
            "level": "error",
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": "pom.xml"},
                    "region": {"startLine": 45}
                }
            }]
        }]
    }]
}

# Normalization:
normalized_finding = {
    "_key": "finding_abc123",
    "customer_id": "cust_001",
    "scan_session_id": "scan_xyz789",
    "cve_id": "CVE-2021-44228",  # Extracted from ruleId
    "cwe_id": None,  # Not present in SARIF
    "severity": "critical",  # Mapped from level="error"
    "description": "Log4j vulnerability detected",
    "location": {"file": "pom.xml", "line": 45},
    "source": "sast"
}
```

**CycloneDX Component → Component Document:**
```python
# Input (CycloneDX SBOM):
{
    "bomFormat": "CycloneDX",
    "specVersion": "1.4",
    "components": [{
        "type": "library",
        "name": "log4j-core",
        "version": "2.14.1",
        "purl": "pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
        "hashes": [{"alg": "SHA-256", "content": "abc..."}]
    }]
}

# Transformation:
component_doc = {
    "_key": hashlib.sha256(b"log4j-core:2.14.1").hexdigest(),
    "customer_id": "cust_001",
    "name": "log4j-core",
    "version": "2.14.1",
    "type": "library",
    "purl": "pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
    "cpe": None,  # Will be resolved later via PURL→CPE mapper
    "first_seen": "2026-03-02T10:00:00Z",
    "last_seen": "2026-03-02T10:00:00Z",
    "scan_session_id": "scan_xyz789"
}
```

**Finding + Component → Edge:**
```python
# Inputs:
finding = {"_key": "finding_abc123", "cve_id": "CVE-2021-44228", ...}
component = {"_key": "comp_def456", "name": "log4j-core", "version": "2.14.1"}

# Edge creation:
edge = {
    "_from": "components/comp_def456",
    "_to": "scan_findings/finding_abc123",
    "customer_id": "cust_001"
}
# Stored in: component_has_finding edge collection
```

### Observability And Debug Points

**Logs emitted at:**
- Scan ingestion start: `INFO "Scan ingestion started" customer_id=<id> format=<format> scan_type=<type>`
- Scan session created: `INFO "Scan session created" session_id=<id> customer_id=<id>`
- SARIF parsing: `DEBUG "Parsing SARIF" runs_count=<n> results_count=<n>`
- Findings normalized: `INFO "Findings normalized" count=<n> session_id=<id>`
- Components extracted: `INFO "Components extracted" count=<n> new_components=<n>`
- Edges created: `INFO "Edges created" component_has_finding=<n> found_in_scan=<n>`
- Duplicate scan: `INFO "Duplicate scan detected" commit_sha=<sha>`
- Parsing error: `ERROR "SARIF parsing failed" error=<err>`

**Metrics/counters updated at:**
- `scan_ingestions_total{format="sarif",scan_type="sast"}` - Total scan ingestions
- `scan_findings_total` - Total findings created
- `scan_components_total` - Total components extracted
- `scan_errors_total{error_type="malformed_sarif"}` - Parsing errors
- `scan_duration_seconds` - Ingestion latency histogram

**Tracing spans:**
- `scan.ingest` - Full ingestion process
- `scan.parse_sarif` - SARIF parsing
- `scan.normalize_findings` - Finding normalization
- `scan.extract_components` - Component extraction
- `scan.create_edges` - Edge creation

### Design Smells / Gaps

- **Any legacy/backward-compatibility branch present?** No
- **Any naming-to-responsibility drift detected?** No
- **Performance consideration:** Bulk inserts used for findings/edges (not one-by-one)
  - ✅ Good: `import_bulk()` is 10x faster than individual inserts

### Open Questions

- Q: How to handle very large scans (10K+ findings)?
  - A: Phase 0 uses bulk inserts (acceptable for 10K)
  - A: Phase 2 adds chunked processing if needed (100K+ findings)
- Q: Should we deduplicate findings within same scan session?
  - A: Phase 0 keeps duplicates (scanner output as-is)
  - A: Phase 1 deduplicates via `/v1/compact` endpoint

### Coverage Status

- **Primary Path:** `Covered` (successful SARIF ingestion with findings + components + edges)
- **Fallback Path:** `Covered` (duplicate scan idempotency, unsupported SARIF version)
- **Error Path:** `Covered` (malformed JSON, missing fields, database insert failure)

---

## Use Case: UC-005 Database Migration from Local to Cloud

### Goal

One-time migration of reference database from local ArangoDB to cloud with zero data loss. Export all 335K+ documents and 1.97M edges from local database, import into cloud `complira_reference` database, verify integrity, and keep local database as read-only backup for 30 days.

### Preconditions

- Local ArangoDB instance operational with existing data
- Cloud ArangoDB cluster deployed and accessible
- Sufficient network bandwidth for data transfer
- Cloud database credentials configured

### Expected Outcome

**AC-017:** Export all 335K+ documents from local database
**AC-018:** Export all 1.97M edges from local database
**AC-019:** Verify export integrity (document count, edge count, checksums)
**AC-020:** Import documents into cloud `complira_reference` database
**AC-021:** Import edges into cloud `complira_reference` database
**AC-022:** Verify import integrity (counts match, spot-check sample documents)
**AC-023:** Keep local database as read-only backup for 30 days
**AC-024:** Zero data loss tolerance (all counts must match exactly)

### Primary Runtime Call Stack

**Scenario:** DevOps runs migration script from local machine to cloud

```text
[ENTRY] python scripts/migrate_to_cloud.py --source local --target cloud --verify

├── scripts/migrate_to_cloud.py:main()
│   ├── src/api/core/config.py:CloudSettings.from_env()
│   │   # Load cloud ArangoDB connection settings
│   │
│   ├── scripts/migrate_to_cloud.py:MigrationOrchestrator.init(local_config, cloud_config)
│   │
│   ├── [PHASE 1] MigrationOrchestrator.export_local_data()
│   │   ├── _connect_to_local_db() [IO database]
│   │   │   └── ArangoClient(hosts=localhost:8529).db('complira_knowledge_graph')
│   │   │
│   │   ├── _export_document_collections() [IO database + file]
│   │   │   └── for collection in ['cves', 'cwes', 'capecs', 'attack_techniques', ...]:
│   │   │       ├── [IO] docs = db.collection(collection).all()
│   │   │       ├── [IO] write_to_file(f'export/{collection}.jsonl', docs)
│   │   │       ├── doc_count = len(docs)
│   │   │       ├── checksum = hashlib.sha256(json.dumps(docs).encode()).hexdigest()
│   │   │       └── manifest['collections'][collection] = {'count': doc_count, 'checksum': checksum}
│   │   │
│   │   ├── _export_edge_collections() [IO database + file]
│   │   │   └── for edge_collection in ['affects', 'aliases', 'matched_by_cpe', ...]:
│   │   │       ├── [IO] edges = db.collection(edge_collection).all()
│   │   │       ├── [IO] write_to_file(f'export/{edge_collection}.jsonl', edges)
│   │   │       ├── edge_count = len(edges)
│   │   │       ├── checksum = hashlib.sha256(json.dumps(edges).encode()).hexdigest()
│   │   │       └── manifest['edges'][edge_collection] = {'count': edge_count, 'checksum': checksum}
│   │   │
│   │   ├── [IO] write_manifest('export/manifest.json', manifest) [FILE]
│   │   │
│   │   └── [LOG] Export complete: 335K+ docs, 1.97M edges, manifest written
│   │
│   ├── [PHASE 2] MigrationOrchestrator.verify_export_integrity()
│   │   ├── [IO] manifest = read_manifest('export/manifest.json')
│   │   ├── total_doc_count = sum(manifest['collections'].values(), key='count')
│   │   ├── total_edge_count = sum(manifest['edges'].values(), key='count')
│   │   ├── [ASSERT] total_doc_count >= 335000 ✓
│   │   ├── [ASSERT] total_edge_count >= 1970000 ✓
│   │   └── [LOG] Export integrity verified: counts match expected values
│   │
│   ├── [PHASE 3] MigrationOrchestrator.import_to_cloud()
│   │   ├── _connect_to_cloud_db() [IO database]
│   │   │   └── ArangoClient(hosts=cloud_host:8529).db('complira_reference', username='admin', password='***')
│   │   │
│   │   ├── _create_collections_if_not_exist() [IO database]
│   │   │   └── for collection_name in manifest['collections'].keys():
│   │   │       ├── [IO] if not db.has_collection(collection_name):
│   │   │       │   └── db.create_collection(collection_name, edge=(collection_name in manifest['edges']))
│   │   │       └── [LOG] Collection ensured: {collection_name}
│   │   │
│   │   ├── _import_document_collections() [IO database]
│   │   │   └── for collection_name, metadata in manifest['collections'].items():
│   │   │       ├── [IO] docs = read_from_file(f'export/{collection_name}.jsonl')
│   │   │       ├── [IO BULK] db.collection(collection_name).import_bulk(docs, on_duplicate='ignore')
│   │   │       │   # Bulk import (batches of 10K documents)
│   │   │       ├── imported_count = len(docs)
│   │   │       └── [LOG] Imported {imported_count} docs to {collection_name}
│   │   │
│   │   ├── _import_edge_collections() [IO database]
│   │   │   └── for edge_collection, metadata in manifest['edges'].items():
│   │   │       ├── [IO] edges = read_from_file(f'export/{edge_collection}.jsonl')
│   │   │       ├── [IO BULK] db.collection(edge_collection).import_bulk(edges, on_duplicate='ignore')
│   │   │       ├── imported_count = len(edges)
│   │   │       └── [LOG] Imported {imported_count} edges to {edge_collection}
│   │   │
│   │   └── [LOG] Import complete: all collections and edges imported
│   │
│   ├── [PHASE 4] MigrationOrchestrator.verify_import_integrity()
│   │   ├── _verify_document_counts() [IO database]
│   │   │   └── for collection_name, expected_metadata in manifest['collections'].items():
│   │   │       ├── [IO] actual_count = db.collection(collection_name).count()
│   │   │       ├── expected_count = expected_metadata['count']
│   │   │       ├── [ASSERT] actual_count == expected_count ✓
│   │   │       └── [LOG] ✓ {collection_name}: {actual_count} docs (matches expected)
│   │   │
│   │   ├── _verify_edge_counts() [IO database]
│   │   │   └── for edge_collection, expected_metadata in manifest['edges'].items():
│   │   │       ├── [IO] actual_count = db.collection(edge_collection).count()
│   │   │       ├── expected_count = expected_metadata['count']
│   │   │       ├── [ASSERT] actual_count == expected_count ✓
│   │   │       └── [LOG] ✓ {edge_collection}: {actual_count} edges (matches expected)
│   │   │
│   │   ├── _spot_check_sample_documents() [IO database]
│   │   │   └── for collection_name in random.sample(manifest['collections'].keys(), k=10):
│   │   │       ├── [IO] local_sample = local_db.collection(collection_name).random(limit=100)
│   │   │       ├── [IO] cloud_sample = cloud_db.collection(collection_name).get(local_sample._keys)
│   │   │       ├── for local_doc, cloud_doc in zip(local_sample, cloud_sample):
│   │   │       │   └── [ASSERT] local_doc == cloud_doc ✓
│   │   │       └── [LOG] ✓ Spot-check passed for {collection_name}
│   │   │
│   │   └── [LOG] Import integrity verified: zero data loss
│   │
│   ├── [PHASE 5] MigrationOrchestrator.set_local_db_readonly()
│   │   ├── [IO] local_db.update_user('root', passwd='***', extra={'read_only': True})
│   │   ├── [LOG] Local database set to read-only mode
│   │   ├── [IO] write_backup_note('local_backup_expires_on: 2026-04-01')
│   │   └── [LOG] Local database will be kept as backup until 2026-04-01 (30 days)
│   │
│   └── [LOG] Migration complete: cloud database operational, local backup retained
│
└── [EXIT] Migration successful
```

**Transformations:**
- **Input:** Local database (335K+ docs, 1.97M edges)
- **Output:** Cloud database with identical data + manifest with verification checksums

**Observability:**
- Log migration progress per collection (exported count, imported count, verification status)
- Metric: `migration.collections_exported` (gauge)
- Metric: `migration.collections_imported` (gauge)
- Metric: `migration.data_loss` (gauge, expected: 0)
- Trace span: `migration.export_phase`, `migration.import_phase`, `migration.verify_phase`

### Fallback Path: Partial Import Recovery

**Scenario:** Import fails mid-way through edge collections

```text
[ERROR] Import failed at edge collection 'technique_mitigated_by_control'

├── MigrationOrchestrator._handle_import_failure(failed_collection='technique_mitigated_by_control')
│   ├── [LOG] Import failure detected, rolling back partial import
│   │
│   ├── [IO] for collection_name in imported_collections:
│   │   └── db.collection(collection_name).truncate()  # Clear partial data
│   │
│   ├── [LOG] Rolled back partial import, restarting from Phase 3
│   │
│   └── [RETRY] MigrationOrchestrator.import_to_cloud()
│       # Retry import from beginning with smaller batch sizes
│
└── [FALLBACK] If retry fails after 3 attempts, abort and alert DevOps
```

### Error Path: Count Mismatch Detection

**Scenario:** Import completes but counts don't match

```text
[ERROR] Verification failed: cves collection count mismatch

├── MigrationOrchestrator.verify_import_integrity()
│   ├── expected_count = 235000 (from manifest)
│   ├── actual_count = 234998 (from cloud DB)
│   ├── [ASSERT FAIL] actual_count == expected_count ❌
│   │
│   ├── [LOG ERROR] Count mismatch detected: cves collection
│   ├── [LOG ERROR] Expected: 235000, Actual: 234998, Missing: 2 docs
│   │
│   ├── _identify_missing_documents() [IO database]
│   │   ├── [IO] local_keys = set(local_db.collection('cves').keys())
│   │   ├── [IO] cloud_keys = set(cloud_db.collection('cves').keys())
│   │   ├── missing_keys = local_keys - cloud_keys
│   │   └── [LOG ERROR] Missing doc keys: {missing_keys}
│   │
│   ├── _reimport_missing_documents() [IO database]
│   │   └── for missing_key in missing_keys:
│   │       ├── [IO] doc = local_db.collection('cves').get(missing_key)
│   │       └── [IO] cloud_db.collection('cves').insert(doc)
│   │
│   └── [RETRY] verify_import_integrity()
│       # Re-run verification after fixing missing docs
│
└── [EXIT] Migration complete after fixing count mismatch
```

### Coverage Summary

- **Primary Path:** `Covered` (successful migration with zero data loss)
- **Fallback Path:** `Covered` (partial import recovery with rollback)
- **Error Path:** `Covered` (count mismatch detection and fix)

---

## Use Case: UC-006 Customer Database On-Demand Provisioning

### Goal

Automatically create customer-specific database on first authenticated API request from new customer. Database must follow naming pattern `complira_customer_<customer_id>`, include all required collections and indexes, handle concurrent requests safely (idempotent), and complete within 5 seconds.

### Preconditions

- Cloud ArangoDB cluster operational (UC-001 complete)
- Customer authenticated and customer_id available (UC-002 complete)
- Customer database does not yet exist (first-time customer)

### Expected Outcome

**AC-025:** Database creation triggered on first authenticated request from new customer
**AC-026:** Database naming follows pattern `complira_customer_<customer_id>`
**AC-027:** Database created with customer-specific collections (scan_sessions, scan_findings, components, edges)
**AC-028:** Indexes created automatically (customer_id indexes, CVE lookup indexes)
**AC-029:** Creation is idempotent (concurrent requests handled safely)
**AC-030:** Database creation completes within 5 seconds
**AC-031:** Failure rolls back (no partial database state)

### Primary Runtime Call Stack

**Scenario:** First API request from new customer (customer_id=cust_abc123) triggers database provisioning

```text
[ENTRY] HTTP POST /v1/scan/ingest (first request from cust_abc123)

├── src/api/v1/endpoints/scan.py:ingest_scan_endpoint(request, customer, service)
│   ├── [DEPENDENCY] customer: Customer = Depends(get_current_customer)
│   │   # customer.id = "cust_abc123", customer.db_provisioned = False
│   │
│   ├── [DEPENDENCY] service: ScanIngestionService = Depends(get_scan_service)
│   │
│   ├── src/api/core/database.py:ensure_customer_database(customer_id=customer.id)
│   │   ├── db_name = f"complira_customer_{customer.id}"  # "complira_customer_cust_abc123"
│   │   │
│   │   ├── [IO DATABASE] if arango_client.has_database(db_name):
│   │   │   └── return existing_db  # Database already exists (idempotency)
│   │   │
│   │   ├── [LOCK] acquire_provisioning_lock(customer.id) [IO REDIS]
│   │   │   # Prevent concurrent provisioning of same customer DB
│   │   │   ├── lock_key = f"db_provision_lock:{customer.id}"
│   │   │   ├── [IO] redis.set(lock_key, value='locked', nx=True, ex=10)  # 10-second lock
│   │   │   └── if lock acquired ✓
│   │   │
│   │   ├── [CHECK AGAIN] if arango_client.has_database(db_name):
│   │   │   # Double-check after acquiring lock (concurrent request may have created DB)
│   │   │   ├── release_provisioning_lock(customer.id)
│   │   │   └── return existing_db  # Idempotent return
│   │   │
│   │   ├── [IO DATABASE] new_db = arango_client.create_database(
│   │   │       name=db_name,
│   │   │       users=[{'username': 'api_user', 'password': '***', 'active': True}]
│   │   │   )
│   │   │   # Database created (empty, no collections yet)
│   │   │
│   │   ├── src/api/core/database.py:_create_customer_collections(new_db)
│   │   │   ├── [IO DATABASE] new_db.create_collection('scan_sessions', edge=False)
│   │   │   ├── [IO DATABASE] new_db.create_collection('scan_findings', edge=False)
│   │   │   ├── [IO DATABASE] new_db.create_collection('components', edge=False)
│   │   │   ├── [IO DATABASE] new_db.create_collection('component_has_finding', edge=True)
│   │   │   └── [LOG] Collections created: scan_sessions, scan_findings, components, component_has_finding
│   │   │
│   │   ├── src/api/core/database.py:_create_customer_indexes(new_db)
│   │   │   ├── [IO DATABASE] new_db.collection('scan_findings').add_hash_index(fields=['cve_id'], unique=False)
│   │   │   ├── [IO DATABASE] new_db.collection('scan_findings').add_hash_index(fields=['scan_session_id'], unique=False)
│   │   │   ├── [IO DATABASE] new_db.collection('components').add_hash_index(fields=['purl'], unique=True)
│   │   │   └── [LOG] Indexes created: cve_id, scan_session_id, purl
│   │   │
│   │   ├── [IO DATABASE] update_customer_profile(customer.id, {'db_provisioned': True, 'db_name': db_name})
│   │   │   # Mark customer as provisioned in customers collection (complira_reference DB)
│   │   │
│   │   ├── [UNLOCK] release_provisioning_lock(customer.id) [IO REDIS]
│   │   │   └── redis.delete(lock_key)
│   │   │
│   │   ├── [LOG] Customer database provisioned: {db_name} (took 3.2 seconds)
│   │   └── return new_db
│   │
│   └── [ASYNC] service.ingest_scan(customer_id=customer.id, scan_data=request)
│       # Proceed with scan ingestion (database now exists)
│
└── [EXIT] HTTP 200 OK {"scan_session_id": "...", "findings_count": 47}
```

**Transformations:**
- **Input:** customer_id="cust_abc123", db_provisioned=False
- **Output:** New database "complira_customer_cust_abc123" with 4 collections, 3 indexes, db_provisioned=True

**Observability:**
- Log: "Customer database provisioned: complira_customer_{customer_id} (took {duration_ms}ms)"
- Metric: `customer_db.provision_duration_ms` (histogram)
- Metric: `customer_db.provision_attempts` (counter)
- Metric: `customer_db.provision_failures` (counter)
- Trace span: `database.provision_customer_db`

### Fallback Path: Concurrent Provisioning Attempt

**Scenario:** Two API requests from same customer arrive simultaneously (both trigger provisioning)

```text
[CONCURRENT] Request A and Request B both call ensure_customer_database(customer_id="cust_xyz")

Request A:
├── acquire_provisioning_lock("cust_xyz") [IO REDIS]
│   └── redis.set("db_provision_lock:cust_xyz", nx=True) → True ✓ (lock acquired)
│
├── create_database("complira_customer_cust_xyz") [IO DATABASE]
│   # Database creation in progress...
│
└── # Continues with collection creation...

Request B (concurrent):
├── acquire_provisioning_lock("cust_xyz") [IO REDIS]
│   └── redis.set("db_provision_lock:cust_xyz", nx=True) → False ❌ (lock already held)
│
├── [WAIT] sleep(500ms) and retry lock acquisition
│   └── for attempt in range(5):  # Retry up to 5 times (5 seconds max)
│       ├── redis.set("db_provision_lock:cust_xyz", nx=True) → False (still locked)
│       └── sleep(1000ms)
│
├── [FALLBACK after 5 retries] Check if database exists
│   ├── [IO DATABASE] if arango_client.has_database("complira_customer_cust_xyz"):
│   │   └── return existing_db ✓ (Request A completed provisioning)
│   │
│   └── [LOG] Database provisioned by concurrent request, proceeding
│
└── [CONTINUE] Use existing database for scan ingestion
```

### Error Path: Database Creation Fails

**Scenario:** ArangoDB database creation fails due to insufficient permissions

```text
[ERROR] Database creation failure

├── src/api/core/database.py:ensure_customer_database(customer_id)
│   ├── [IO DATABASE] arango_client.create_database(db_name)
│   │   └── [EXCEPTION] ArangoServerError: insufficient permissions (403)
│   │
│   ├── [CATCH] except ArangoServerError as e:
│   │   ├── [LOG ERROR] Failed to create customer database: {e}
│   │   ├── [UNLOCK] release_provisioning_lock(customer.id)  # Release lock on failure
│   │   ├── [METRIC] increment('customer_db.provision_failures')
│   │   └── raise HTTPException(status_code=500, detail="Database provisioning failed")
│   │
│   └── [ROLLBACK] No rollback needed (database creation is atomic)
│
└── [EXIT ERROR] HTTP 500 Internal Server Error {"detail": "Database provisioning failed"}
```

### Error Path: Partial Collection Creation

**Scenario:** Collections created successfully but index creation fails

```text
[ERROR] Index creation failure after collections created

├── src/api/core/database.py:_create_customer_indexes(new_db)
│   ├── [IO DATABASE] new_db.collection('scan_findings').add_hash_index(fields=['cve_id'])
│   │   └── [EXCEPTION] ArangoServerError: index creation failed
│   │
│   ├── [CATCH] except ArangoServerError as e:
│   │   ├── [LOG ERROR] Index creation failed, rolling back database
│   │   │
│   │   ├── [ROLLBACK] arango_client.delete_database(db_name)
│   │   │   # Delete entire database (removes partial state)
│   │   │   └── [IO DATABASE] Database deleted: {db_name}
│   │   │
│   │   ├── [UNLOCK] release_provisioning_lock(customer.id)
│   │   ├── [LOG ERROR] Rolled back database due to index creation failure
│   │   └── raise HTTPException(status_code=500, detail="Database provisioning failed during indexing")
│   │
│   └── [EXIT ERROR] HTTP 500 Internal Server Error
```

### Coverage Summary

- **Primary Path:** `Covered` (successful first-time database provisioning)
- **Fallback Path:** `Covered` (concurrent provisioning with lock handling)
- **Error Path 1:** `Covered` (database creation failure with lock release)
- **Error Path 2:** `Covered` (partial collection creation with full rollback)

---

## Summary

**Future-State Runtime Call Stacks Complete for Phase 0:**
- ✅ UC-001: Multi-Tenant Database Setup (3 paths)
- ✅ UC-002: API Authentication & Customer Scoping (4 paths)
- ✅ UC-003: Redis Caching Layer (4 paths)
- ✅ UC-004: Scan Ingestion API (5 paths) - **Revised to show parser delegation**
- ✅ UC-005: Database Migration from Local to Cloud (3 paths) - **Added in Stage 5 Round 1 review**
- ✅ UC-006: Customer Database On-Demand Provisioning (4 paths) - **Added in Stage 5 Round 1 review**

**Total Paths Modeled:** 23 runtime paths (primary + fallback + error)

**Key Design Validations:**
1. **DRY Applied:** `BaseGraphService` used in enrichment service, `BaseScanParser` eliminates parser duplication
2. **SOLID Applied:** Dependency injection used in all endpoints, parser abstraction follows SRP/OCP/DIP
3. **Separation of Concerns:** Clear boundaries (endpoints/services/parsers/repositories/cache/database)
4. **Zero Data Loss:** UC-005 migration with export-verify-import-verify pattern
5. **Concurrent Safety:** UC-006 provisioning with Redis locking for idempotency

**Stage 5 Round 1 Review Issues Addressed:**
- ✅ Parser abstraction extracted (UC-004 revised)
- ✅ Database migration use case added (UC-005)
- ✅ Customer provisioning use case added (UC-006)

**Next Stage:** Stage 5 Round 2 (Review Gate) - Review updated runtime call stacks
