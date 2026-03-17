# Complira API Quick Reference

**TL;DR**: Run `./scripts/run_api_dev.sh` to start the API, then visit http://localhost:8000/docs

---

## Start API Locally

```bash
# One command - checks everything and starts API
./scripts/run_api_dev.sh
```

**What it does:**
1. ✅ Checks Python, venv, ArangoDB, Redis
2. 🚀 Starts missing services
3. 🔍 Verifies database has data
4. 🌐 Starts API at http://localhost:8000

---

## Test API

```bash
# Run all tests
python scripts/test_api_local.py

# See results in color-coded table
```

**Tests:**
- ✅ Health check
- ✅ Reference CVE API
- ✅ Batch enrichment
- ✅ Reference CWE API
- ✅ Scan ingestion (if API key provided)

---

## API Endpoints

### Reference API (No Auth Required)

```bash
# Get CVE with full enrichment
curl http://localhost:8000/v1/reference/cve/CVE-2024-21413 | jq

# Batch enrich multiple CVEs
curl "http://localhost:8000/v1/reference/enrich?cve_ids=CVE-2024-21413,CVE-2023-44487" | jq

# Get CWE details
curl http://localhost:8000/v1/reference/cwe/CWE-89 | jq

# Get NIST controls for CVE
curl http://localhost:8000/v1/reference/controls/CVE-2024-21413 | jq
```

### Scan API (Requires `X-API-Key` Header)

```bash
export COMPLIRA_API_KEY="your_key_here"

# Upload SARIF scan
curl -X POST http://localhost:8000/v1/scan/ingest \
  -H "X-API-Key: $COMPLIRA_API_KEY" \
  -H "Content-Type: application/json" \
  -d @scan_payload.json | jq

# List scans
curl http://localhost:8000/v1/scans \
  -H "X-API-Key: $COMPLIRA_API_KEY" | jq

# Get scan details
curl http://localhost:8000/v1/scan/{session_id} \
  -H "X-API-Key: $COMPLIRA_API_KEY" | jq

# List findings
curl http://localhost:8000/v1/scan/{session_id}/findings \
  -H "X-API-Key: $COMPLIRA_API_KEY" | jq
```

---

## Interactive Docs

Once API is running:

- **Swagger UI**: http://localhost:8000/docs (try endpoints in browser!)
- **ReDoc**: http://localhost:8000/redoc (alternative UI)
- **Health**: http://localhost:8000/health

---

## Common Commands

```bash
# Seed database (first time)
complira seed --skip-llm

# Check database
complira query "RETURN LENGTH(vulnerabilities)"

# Check ArangoDB
docker compose ps arangodb
# Web UI: http://localhost:8529 (root/rootpassword)

# Check Redis
redis-cli ping

# Restart services
docker compose restart arangodb redis

# View logs
docker compose logs -f api
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Connection refused | `docker compose up -d arangodb redis` |
| CVE not found | `complira seed --skip-llm` |
| 401 Unauthorized | Check API key or use reference endpoints (no auth) |
| Empty results | Verify database: `complira query "RETURN LENGTH(vulnerabilities)"` |

---

## File Locations

| Purpose | File |
|---------|------|
| API entry point | `src/api/main.py` |
| Reference endpoints | `src/api/v1/endpoints/reference.py` |
| Scan endpoints | `src/api/v1/endpoints/scan.py` |
| Database utilities | `src/api/core/database.py` |
| Authentication | `src/api/core/security.py` |
| Cache layer | `src/api/core/cache.py` |
| Dev server script | `scripts/run_api_dev.sh` |
| Test script | `scripts/test_api_local.py` |

---

## Full Documentation

- **[API Documentation](API_DOCUMENTATION.md)** - Complete API reference with examples
- **[Local Development Guide](API_LOCAL_DEVELOPMENT.md)** - Detailed setup, testing, debugging
- **[Multi-Tenant Architecture](MULTI_TENANT_ARCHITECTURE.md)** - Database isolation design
- **[GitHub Action Example](examples/github-action-local-scan.yml)** - CI/CD integration

---

## Quick Test

```bash
# 1. Start API
./scripts/run_api_dev.sh

# 2. In another terminal, test it
curl http://localhost:8000/health

# 3. Try reference API (no auth needed!)
curl http://localhost:8000/v1/reference/cve/CVE-2024-21413 | jq .data.epss

# 4. Open interactive docs
open http://localhost:8000/docs  # macOS
xdg-open http://localhost:8000/docs  # Linux
```

---

## Support

**Check logs first:**
```bash
# API logs
tail -f logs/api.log

# Docker logs
docker compose logs -f api

# Database connection
complira query "RETURN 1"
```

**Still stuck?**
- GitHub Issues: https://github.com/complira/complira-graph/issues
- Read full docs: [API_LOCAL_DEVELOPMENT.md](API_LOCAL_DEVELOPMENT.md)
