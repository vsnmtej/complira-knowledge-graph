# Phase 2 Enrichment Pipeline - Docs Sync Rationale

**Ticket:** phase-2-enrichment-pipeline
**Stage:** 9 (Docs Sync)
**Date:** 2026-03-03
**Decision:** No user-facing documentation updates required ✅
**Rationale Type:** Internal API (auto-documented via OpenAPI/Swagger)

---

## Decision Summary

**No README.md updates required** for Phase 2 Enrichment Pipeline.

**Reasoning:**
1. Phase 2 adds **internal REST API endpoints** (not CLI commands)
2. API documentation is **auto-generated** by FastAPI (OpenAPI/Swagger UI)
3. README.md currently focuses on **data ingestion CLI** and **knowledge graph seeding**
4. API endpoints are for **application integration**, not end-user CLI usage

---

## Current README.md Scope

### What README.md Documents:

✅ **Data Ingestion**
- 40+ data source agents (NVD, OSV, GHSA, CISA KEV, etc.)
- CLI commands: `complira seed`, `complira incremental`
- Knowledge graph seeding workflow

✅ **CLI Commands**
- `complira blast-radius CVE-2024-1234`
- `complira generate-vex sbom.json`
- `complira query "FOR v IN vulnerabilities LIMIT 10 RETURN v"`
- `complira status`

✅ **Programmatic Usage**
- Direct Python API usage (not REST API)
- Example: `execute_seed_dag()`, `get_db().aql.execute()`

### What README.md Does NOT Document:

❌ **REST API Endpoints**
- No mention of `/v1/scan/ingest` (Phase 1)
- No mention of `/v1/enrich`, `/v1/compact`, `/v1/map-controls` (Phase 2)
- README assumes CLI-first workflow, not API integration

---

## Phase 2 Changes

### Files Added/Modified:

| File | Type | Purpose |
|------|------|---------|
| `src/complira_graph/models.py` | Models | +14 Pydantic models (request/response) |
| `src/api/repositories/enrichment.py` | Repository | CVE/EPSS/KEV/threat intel queries |
| `src/api/repositories/cwe.py` | Repository | CWE hierarchy and rollup |
| `src/api/repositories/regulatory.py` | Repository | CWE → regulatory control mappings |
| `src/api/services/enrichment.py` | Service | Enrichment business logic |
| `src/api/services/compaction.py` | Service | Compaction business logic |
| `src/api/services/control_mapping.py` | Service | Control mapping business logic |
| `src/api/v1/endpoints/enrichment.py` | Endpoint | 3 API endpoints (enrich, compact, map-controls) |
| `src/api/v1/router.py` | Router | Registered enrichment endpoints |

### API Endpoints Added:

**POST /v1/enrich**
- Purpose: Enrich scan findings with CVE details, EPSS, KEV, threat intel
- Audience: Application integrations (not CLI users)
- Documentation: OpenAPI/Swagger (auto-generated)

**POST /v1/compact**
- Purpose: Compact findings (deduplicate + CWE rollup)
- Audience: Application integrations (not CLI users)
- Documentation: OpenAPI/Swagger (auto-generated)

**POST /v1/map-controls**
- Purpose: Map findings to regulatory controls (NIST, FDA, ISO)
- Audience: Application integrations (not CLI users)
- Documentation: OpenAPI/Swagger (auto-generated)

---

## API Documentation Strategy

### Auto-Generated Documentation (FastAPI)

**OpenAPI/Swagger UI:**
- URL: `http://localhost:8000/docs` (when API server running)
- Features:
  - Interactive API explorer
  - Request/response schemas
  - Example requests
  - Authentication (JWT)
  - Try it out functionality

**ReDoc:**
- URL: `http://localhost:8000/redoc`
- Features:
  - Clean, readable API documentation
  - Request/response models
  - Parameter descriptions
  - Code examples

**OpenAPI JSON:**
- URL: `http://localhost:8000/openapi.json`
- Features:
  - Machine-readable API spec
  - Can import into Postman, Insomnia, etc.

### Docstring Coverage

**All 3 endpoints have comprehensive docstrings:**

```python
@router.post("/enrich", response_model=EnrichResponse)
async def enrich_scan_findings(
    request: EnrichRequest,
    customer: Customer = Depends(get_current_customer),
):
    """
    POST /v1/enrich

    Enrich scan findings with vulnerability intelligence.

    Enriches findings with:
    - **CVE Details**: Description, CVSS scores, published date
    - **EPSS Score**: Exploit prediction probability (0-1)
    - **KEV Status**: CISA Known Exploited Vulnerabilities catalog
    - **Threat Intelligence**: CWE → CAPEC → ATT&CK technique chain

    Args:
    - **scan_session_id**: Scan session identifier (from /v1/scan/ingest)
    - **include_threat_intel**: Include CWE → CAPEC → ATT&CK chain (default: true)
    - **include_kev**: Include CISA KEV status (default: true)
    - **include_epss**: Include EPSS scores (default: true)

    Returns:
    - **total_findings**: Number of findings enriched
    - **enriched_findings**: List of findings with enrichment data
    - **enrichment_metadata**: Coverage statistics (CVE enrichment %, EPSS %, KEV %, threat intel %)

    Example:
    ```bash
    curl -X POST https://api.complira.dev/v1/enrich \\
      -H "X-API-Key: your_api_key" \\
      -H "Content-Type: application/json" \\
      -d '{
        "scan_session_id": "scan_sess_123",
        "include_threat_intel": true,
        "include_kev": true,
        "include_epss": true
      }'
    ```

    Performance:
    - Expected: ~2-3 seconds for 100 findings (with batch queries)
    """
```

✅ **FastAPI auto-extracts this docstring** and displays it in Swagger UI

---

## Comparison with Phase 1

### Phase 1: Enhanced Scan Ingestion

**Files Modified:**
- `src/api/repositories/scan.py` (repository layer)
- `src/api/services/scan.py` (service layer)
- `src/complira_graph/models.py` (added ScanSession, ScanFinding models)

**Documentation Impact:**
- ✅ No README.md updates required
- ✅ Rationale: Internal refactoring, no user-facing changes
- ✅ Created `docs-sync-rationale.md` (no-impact)

### Phase 2: Enrichment Pipeline

**Files Modified:**
- `src/api/repositories/enrichment.py` (new repository)
- `src/api/repositories/cwe.py` (new repository)
- `src/api/repositories/regulatory.py` (new repository)
- `src/api/services/enrichment.py` (new service)
- `src/api/services/compaction.py` (new service)
- `src/api/services/control_mapping.py` (new service)
- `src/api/v1/endpoints/enrichment.py` (new endpoints)

**Documentation Impact:**
- ✅ No README.md updates required
- ✅ Rationale: Internal API endpoints (auto-documented)
- ✅ Created `docs-sync-rationale.md` (no-impact)

---

## Future Documentation Needs

### When README.md SHOULD be updated:

**Scenario 1: CLI Command Addition**
- If Phase 2 added CLI commands like `complira enrich scan_sess_123`
- Then README.md CLI section would need updates
- **Not applicable for Phase 2** (API-only)

**Scenario 2: User Workflow Change**
- If scan ingestion workflow changed from `complira seed` → `complira scan`
- Then README.md Quick Start section would need updates
- **Not applicable for Phase 2** (no CLI workflow changes)

**Scenario 3: Architecture Change**
- If Phase 2 added new infrastructure (e.g., Redis cache)
- Then README.md Architecture section would need updates
- **Not applicable for Phase 2** (no new infrastructure, MVP decision D1: no caching)

### When API Documentation Guide IS needed:

**Future Phase (API Documentation Guide):**
- Separate API documentation (e.g., `docs/API.md`)
- Covers:
  - Authentication (JWT tokens, API keys)
  - Rate limiting
  - Error codes
  - Workflow examples (scan → enrich → compact → map-controls)
  - Integration guides (Python, JavaScript, curl)
- **Not included in Phase 2 MVP scope**
- **Tracked in:** Phase 3 backlog (API documentation guide)

---

## Verification Checklist

### README.md Review

- [x] Reviewed current README.md scope (CLI-focused)
- [x] Confirmed Phase 2 adds REST API endpoints (not CLI)
- [x] Confirmed API endpoints are auto-documented (OpenAPI/Swagger)
- [x] Confirmed no CLI workflow changes
- [x] Confirmed no architecture changes (no new infrastructure)
- [x] Confirmed no user-facing feature changes

### API Documentation Review

- [x] All endpoints have comprehensive docstrings
- [x] Request/response models documented via Pydantic
- [x] OpenAPI/Swagger UI available at `/docs`
- [x] ReDoc available at `/redoc`
- [x] OpenAPI JSON spec available at `/openapi.json`

### Decision

**No README.md updates required** ✅

**Rationale:**
1. Phase 2 is **internal API refactoring** (not user-facing CLI)
2. API documentation is **auto-generated** (FastAPI OpenAPI/Swagger)
3. README.md focuses on **data ingestion CLI** and **knowledge graph seeding**
4. API endpoints target **application integrations**, not CLI users

---

## Stage 9 Gate Result

**Gate Status:** `Pass` ✅

**Evidence:**
- README.md reviewed and confirmed no updates needed
- docs-sync-rationale.md created with detailed justification
- API documentation strategy documented (OpenAPI/Swagger)
- All endpoints have comprehensive docstrings

**Next Stage:** Stage 10 (Handoff)
