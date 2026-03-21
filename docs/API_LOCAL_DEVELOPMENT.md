# API Local Development Guide

Complete guide for running and testing the Complira API locally.

---

## Prerequisites

- Python 3.12+
- Docker (for ArangoDB and Redis)
- uv package manager

---

## Quick Start

### Option A: Using Helper Scripts (Recommended)

**Start API Server:**
```bash
# All-in-one script: checks dependencies, starts infrastructure, runs API
./scripts/run_api_dev.sh

# Custom port
./scripts/run_api_dev.sh --port 8080

# Disable auto-reload
./scripts/run_api_dev.sh --no-reload
```

**Test API:**
```bash
# Run all API tests
python scripts/test_api_local.py

# Test with custom URL
python scripts/test_api_local.py --base-url http://localhost:8080

# Test with API key (for authenticated endpoints)
export COMPLIRA_API_KEY="your_key_here"
python scripts/test_api_local.py --api-key $COMPLIRA_API_KEY
```

### Option B: Manual Setup

### 1. Install Dependencies

```bash
# Install uv package manager
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install project dependencies
uv sync
```

### 2. Start Infrastructure

```bash
# Start ArangoDB and Redis
docker compose up -d arangodb redis

# Verify services are running
docker compose ps

# Check ArangoDB: http://localhost:8529 (root/rootpassword)
# Check Redis: redis-cli ping
```

### 3. Seed Reference Database

```bash
# Activate virtual environment
source .venv/bin/activate

# Seed knowledge graph (this will take some time on first run)
# Skip LLM agents to avoid API costs during development
complira seed --skip-llm

# Verify data loaded
complira query "RETURN LENGTH(vulnerabilities)"
# Should return: 3238 (or current CVE count)
```

### 4. Create Test API Key

```bash
# Create a test customer API key
python -c "
from api.core.security import hash_api_key
import secrets

# Generate test API key
api_key = 'complira_test_' + secrets.token_urlsafe(32)
print(f'API Key: {api_key}')

# Hash it (you'll need to insert this into a customer DB)
hashed = hash_api_key(api_key)
print(f'Hashed: {hashed}')
"

# Save the API key for testing
export COMPLIRA_API_KEY="complira_test_..."
```

**Note:** For full multi-tenant setup, you'll need to create a customer record in the database. For now, you can test reference endpoints (no auth required).

### 5. Run API Server

```bash
# Method 1: Using uvicorn directly
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Method 2: Using the CLI (if implemented)
# complira api serve --reload
```

**Server will start at:**
- API: http://localhost:8000
- Interactive docs (Swagger): http://localhost:8000/docs
- Alternative docs (ReDoc): http://localhost:8000/redoc
- Health check: http://localhost:8000/health

---

## Testing the API

### Method 1: Interactive Swagger UI (Recommended)

1. Open http://localhost:8000/docs
2. Explore all available endpoints
3. Click "Try it out" on any endpoint
4. Enter parameters and click "Execute"
5. See request/response in real-time

**Example: Test Reference API**
1. Navigate to http://localhost:8000/docs
2. Find `GET /v1/reference/cve/{cve_id}`
3. Click "Try it out"
4. Enter `CVE-2024-21413` (or any CVE from your database)
5. Click "Execute"
6. See full enrichment response

### Method 2: cURL Commands

**Health Check:**
```bash
curl http://localhost:8000/health
```

**Reference API (No Authentication):**
```bash
# Get single CVE with enrichment
curl http://localhost:8000/v1/reference/cve/CVE-2024-21413 | jq

# Batch enrich multiple CVEs
curl "http://localhost:8000/v1/reference/enrich?cve_ids=CVE-2024-21413,CVE-2023-44487" | jq

# Get CWE details
curl http://localhost:8000/v1/reference/cwe/CWE-89 | jq

# Get NIST controls for CVE
curl http://localhost:8000/v1/reference/controls/CVE-2024-21413 | jq
```

**Scan Ingestion API (Requires Authentication):**
```bash
# Upload SARIF scan
curl -X POST http://localhost:8000/v1/scan/ingest \
  -H "X-API-Key: $COMPLIRA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "format": "sarif",
    "scan_type": "sast",
    "payload": {
      "version": "2.1.0",
      "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
      "runs": [{
        "tool": {
          "driver": {
            "name": "Semgrep",
            "version": "1.0.0"
          }
        },
        "results": []
      }]
    },
    "metadata": {
      "repository": "test-repo",
      "branch": "main"
    }
  }' | jq

# List scans
curl http://localhost:8000/v1/scans \
  -H "X-API-Key: $COMPLIRA_API_KEY" | jq
```

### Method 3: Python Requests

```python
import requests

BASE_URL = "http://localhost:8000"

# Test health endpoint
response = requests.get(f"{BASE_URL}/health")
print(response.json())

# Test reference API (no auth)
response = requests.get(f"{BASE_URL}/v1/reference/cve/CVE-2024-21413")
data = response.json()

if data['success']:
    cve = data['data']
    print(f"CVE: {cve['cve_id']}")
    print(f"CVSS: {cve['cvss_score']}")
    print(f"EPSS: {cve['epss']['score']}")
    print(f"In KEV: {cve['kev']['in_kev']}")
    print(f"ATT&CK Techniques: {len(cve['attack_techniques'])}")
    print(f"NIST Controls: {len(cve['nist_controls'])}")
else:
    print(f"Error: {data.get('error')}")
```

### Method 4: HTTPie (Pretty CLI)

```bash
# Install httpie
pip install httpie

# Test reference API
http GET http://localhost:8000/v1/reference/cve/CVE-2024-21413

# Test with authentication
http POST http://localhost:8000/v1/scan/ingest \
  X-API-Key:$COMPLIRA_API_KEY \
  format=sarif \
  scan_type=sast \
  payload:='{"version": "2.1.0", ...}'
```

---

## Testing with Real Scan Data

### Generate Test Scan Results

**SARIF (Semgrep):**
```bash
# Install Semgrep
pip install semgrep

# Scan your project
cd /path/to/your/project
semgrep --config auto --sarif > test_scan.sarif

# Upload to local API
curl -X POST http://localhost:8000/v1/scan/ingest \
  -H "X-API-Key: $COMPLIRA_API_KEY" \
  -H "Content-Type: application/json" \
  -d @- <<EOF
{
  "format": "sarif",
  "scan_type": "sast",
  "payload": $(cat test_scan.sarif),
  "metadata": {
    "repository": "test-project",
    "branch": "main",
    "commit": "$(git rev-parse HEAD)"
  }
}
EOF
```

**CycloneDX (Syft):**
```bash
# Install Syft
curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh -s -- -b /usr/local/bin

# Generate SBOM
syft packages -o cyclonedx-json > test_sbom.json

# Upload to local API
curl -X POST http://localhost:8000/v1/scan/ingest \
  -H "X-API-Key: $COMPLIRA_API_KEY" \
  -H "Content-Type: application/json" \
  -d @- <<EOF
{
  "format": "cyclonedx",
  "scan_type": "sca",
  "payload": $(cat test_sbom.json),
  "metadata": {
    "repository": "test-project",
    "environment": "production"
  }
}
EOF
```

---

## Development Workflow

### 1. Watch Mode (Auto-Reload)

```bash
# API server will restart on file changes
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Check Logs

```bash
# Structured logs with color coding
tail -f logs/api.log

# Or view in real-time (if using systemd/docker)
docker compose logs -f api
```

### 3. Monitor Redis Cache

```bash
# Connect to Redis CLI
redis-cli

# Check cache keys
KEYS complira:*

# Get cache entry
GET complira:reference:cve:CVE-2024-21413

# Clear cache
FLUSHDB

# Monitor cache hits/misses
MONITOR
```

### 4. Query ArangoDB

```bash
# Using CLI
complira query "FOR v IN vulnerabilities FILTER v.cve_id == 'CVE-2024-21413' RETURN v"

# Using ArangoDB Web UI
# http://localhost:8529
# Login: root / rootpassword
# Database: complira_reference
```

---

## Testing Customer Isolation

### Create Test Customers

```python
# scripts/create_test_customer.py
from api.core.database import get_reference_db
from api.core.security import hash_api_key
import secrets

def create_test_customer(customer_id: str, name: str):
    """Create a test customer with API key."""
    # Generate API key
    api_key = f"complira_test_{customer_id}_" + secrets.token_urlsafe(32)
    hashed_key = hash_api_key(api_key)

    print(f"Customer: {name}")
    print(f"Customer ID: {customer_id}")
    print(f"API Key: {api_key}")
    print(f"Hashed: {hashed_key}")
    print()

    # TODO: Insert into customers collection
    # (requires customer management implementation)

if __name__ == "__main__":
    create_test_customer("acme_corp", "Acme Corporation")
    create_test_customer("startup_xyz", "Startup XYZ")
```

### Test Multi-Tenant Isolation

```bash
# Upload scan as Customer A
curl -X POST http://localhost:8000/v1/scan/ingest \
  -H "X-API-Key: $CUSTOMER_A_API_KEY" \
  -d @scan_a.json

# Try to access Customer A's scans as Customer B (should fail with 403)
SCAN_ID="scan_abc123"
curl http://localhost:8000/v1/scan/$SCAN_ID \
  -H "X-API-Key: $CUSTOMER_B_API_KEY"
# Expected: 403 Forbidden

# Verify database isolation
complira query "RETURN DATABASE_LIST()"
# Should show: complira_reference, complira_customer_acme_corp, complira_customer_startup_xyz
```

---

## Performance Testing

### Load Test with Apache Bench

```bash
# Install Apache Bench
sudo apt-get install apache2-utils  # Ubuntu/Debian
brew install httpd  # macOS

# Test reference API (no auth, should be fast with cache)
ab -n 1000 -c 10 http://localhost:8000/v1/reference/cve/CVE-2024-21413

# Expected results:
# - First request: ~200-500ms (database query)
# - Cached requests: <10ms (Redis cache hit)

# Test with different CVEs (cache misses)
ab -n 100 -c 10 http://localhost:8000/v1/reference/cve/CVE-2023-44487
```

### Monitor Performance

```bash
# Watch request latency
tail -f logs/api.log | grep execution_time_ms

# Redis cache hit rate
redis-cli INFO stats | grep keyspace_hits
redis-cli INFO stats | grep keyspace_misses
```

---

## Debugging

### Enable Debug Logging

```python
# api/main.py
import logging

# Set log level to DEBUG
logging.basicConfig(level=logging.DEBUG)

# Or use structlog configuration
import structlog
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
)
```

### Common Issues

**Issue 1: Connection refused (ArangoDB)**
```bash
# Check if ArangoDB is running
docker compose ps arangodb

# Check logs
docker compose logs arangodb

# Restart
docker compose restart arangodb
```

**Issue 2: Redis connection error**
```bash
# Check if Redis is running
docker compose ps redis

# Test connection
redis-cli ping
# Expected: PONG

# Restart
docker compose restart redis
```

**Issue 3: 404 on /v1/reference endpoints**
```bash
# Verify router registration
grep -r "include_router" src/api/

# Check if reference router is imported
cat src/api/v1/router.py | grep reference
```

**Issue 4: Empty enrichment data**
```bash
# Verify reference database has data
complira query "RETURN LENGTH(vulnerabilities)"
# Should return > 0

# Check if CVE exists
complira query "RETURN DOCUMENT('vulnerabilities', 'CVE-2024-21413')"
```

---

## Automated Testing

### Run Integration Tests

```bash
# Run Phase 0 acceptance criteria tests
pytest tests/integration/test_phase0_acceptance_criteria.py -v

# Run with coverage
pytest tests/integration/test_phase0_acceptance_criteria.py --cov=api --cov-report=html

# Run specific test class
pytest tests/integration/test_phase0_acceptance_criteria.py::TestUC001_MultiTenantDatabase -v
```

### Test API Endpoints

```python
# tests/integration/test_reference_api.py
import pytest
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_reference_cve_endpoint():
    response = client.get("/v1/reference/cve/CVE-2024-21413")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["cve_id"] == "CVE-2024-21413"

def test_reference_enrich_endpoint():
    response = client.get("/v1/reference/enrich?cve_ids=CVE-2024-21413,CVE-2023-44487")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["data"]) == 2
```

---

## Docker Development

### Build and Run with Docker

```bash
# Build API image
docker build -t complira-api -f docker/Dockerfile.api .

# Run with docker compose
docker compose up -d

# Check logs
docker compose logs -f api

# Scale API instances
docker compose up -d --scale api=3
```

### Docker Compose Override (Development)

```yaml
# docker-compose.override.yml
version: '3.8'

services:
  api:
    build:
      context: .
      dockerfile: docker/Dockerfile.api
    volumes:
      - ./src:/app/src  # Hot reload
    environment:
      - LOG_LEVEL=DEBUG
      - RELOAD=true
    ports:
      - "8000:8000"
```

---

## API Versioning

Current version: `v1`

All endpoints are prefixed with `/v1/`:
- `/v1/reference/*` - Reference data
- `/v1/scan/*` - Scan management
- `/v1/enrich` - Enrichment (Phase 1)

When adding new features:
1. Add to `/v1/` routes first
2. Mark as `(Coming Soon)` in documentation
3. Implement and test
4. Update changelog

---

## Next Steps

1. **Implement customer management** - Create/delete customers, manage API keys
2. **Add rate limiting** - Redis-based rate limiting per API key
3. **Implement webhooks** - Notify on scan completion, new KEV entries
4. **Add GraphQL endpoint** - For complex graph queries
5. **Implement SSE streaming** - Real-time scan progress updates

---

## Resources

- **FastAPI Documentation**: https://fastapi.tiangolo.com
- **ArangoDB Python Driver**: https://docs.python-arango.com
- **Redis Python Client**: https://redis-py.readthedocs.io
- **Swagger/OpenAPI**: http://localhost:8000/docs (when API is running)
- **API Documentation**: [docs/API_DOCUMENTATION.md](API_DOCUMENTATION.md)
- **Multi-Tenant Architecture**: [docs/MULTI_TENANT_ARCHITECTURE.md](MULTI_TENANT_ARCHITECTURE.md)

---

## Support

For issues or questions:
1. Check logs: `tail -f logs/api.log`
2. Verify infrastructure: `docker compose ps`
3. Test database connection: `complira query "RETURN 1"`
4. Open GitHub issue with logs and steps to reproduce
