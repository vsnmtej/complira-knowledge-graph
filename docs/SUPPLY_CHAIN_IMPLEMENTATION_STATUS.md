# Supply Chain Layer Implementation Status

**Generated:** 2026-03-06
**Project:** Complira Cybersecurity Compliance Platform
**Scope:** SBOM Ingestion & VEX Generation (Supply Chain Layer)

---

## Executive Summary

The Supply Chain Layer API infrastructure is **80% complete**. The foundation for SBOM ingestion exists through the scan ingestion system, but dedicated SBOM/VEX endpoints and services need to be created.

**Key Finding:** The existing `/v1/scan/ingest` endpoint already supports CycloneDX SBOM ingestion, component extraction, and vulnerability mapping. We need to build specialized SBOM management endpoints and integrate the VEX synthesizer for full supply chain functionality.

**Status by Component:**
- Core Infrastructure: ✅ **100% Complete**
- SBOM Parsers: ✅ **95% Complete** (CycloneDX ready, SPDX needed)
- Database Schema: ✅ **100% Complete** (collections exist)
- Scan Endpoints: ✅ **100% Complete** (supports SBOM upload)
- SBOM Endpoints: 🚧 **0% Complete** (need to create)
- VEX Integration: 🚧 **50% Complete** (agent exists, no API endpoint)
- Repositories: ✅ **100% Complete** (ComponentRepository ready)
- Services: 🚧 **70% Complete** (scan service works, need SBOM service)

---

## Table of Contents

1. [What's Already Implemented](#1-whats-already-implemented)
2. [What's Missing](#2-whats-missing)
3. [Implementation Plan](#3-implementation-plan)
4. [Quick Start Guide](#4-quick-start-guide)
5. [Architecture Overview](#5-architecture-overview)
6. [Testing Strategy](#6-testing-strategy)

---

## 1. What's Already Implemented

### 1.1 Core Infrastructure (✅ 100%)

#### Multi-Tenant Database System
**File:** `/src/api/core/database.py`

**Features:**
- ✅ Database-per-customer architecture implemented
- ✅ Automatic customer database provisioning
- ✅ Redis-based distributed locking for concurrent creation
- ✅ Customer database caching
- ✅ Cross-database query support (customer DB → reference DB)

**Collections Created:**
```python
# Customer Database Collections (Auto-created)
- scan_sessions          # Scan metadata
- scan_findings          # Individual vulnerability findings
- customer_components    # SBOM components (PURL-keyed)

# Edge Collections
- finding_to_cve                # Finding → Vulnerability (ref DB)
- component_to_finding          # Component → Finding
```

**Status:** Production-ready. Tested with automatic provisioning.

---

#### API Gateway & Authentication
**File:** `/src/api/main.py`

**Features:**
- ✅ FastAPI application with CORS middleware
- ✅ Global exception handling
- ✅ Health check endpoint (`/health`)
- ✅ API versioning (`/v1` router)
- ✅ Structured logging (structlog)

**File:** `/src/api/core/security.py`

**Features:**
- ✅ Customer authentication via API key
- ✅ `get_current_customer()` dependency injection
- ✅ Customer model with ID and metadata

**Status:** Production-ready.

---

### 1.2 SBOM Parsers (✅ 95%)

#### CycloneDX Parser
**File:** `/src/api/parsers/cyclonedx.py`

**Capabilities:**
- ✅ Parses CycloneDX 1.4 and 1.5 formats
- ✅ Extracts metadata (tool, version, timestamp)
- ✅ Extracts components (name, version, PURL, licenses, hashes)
- ✅ Extracts vulnerabilities from components
- ✅ Maps CycloneDX severity to normalized levels
- ✅ Validates SBOM structure (bomFormat, specVersion)
- ✅ Handles both old and new tools format

**Example Usage:**
```python
from api.parsers.factory import ParserFactory

parser = ParserFactory.get_parser("cyclonedx")
parsed_data = parser.parse(cyclonedx_payload)

# Returns ParsedScanData with:
# - tool_name, tool_version, scan_timestamp
# - findings: List[ParsedFinding]
# - components: List[Dict]
# - metadata: Dict
```

**Supported Tools:**
- Syft
- Grype
- Trivy
- Snyk
- OWASP Dependency-Check
- GitHub Dependency Graph

**Status:** Production-ready. Tested with multiple tools.

---

#### Parser Factory
**File:** `/src/api/parsers/factory.py`

**Features:**
- ✅ Factory pattern for parser selection (OCP compliant)
- ✅ Supports `sarif` and `cyclonedx` formats
- ✅ Extensible registration system
- ✅ Format validation

**Registered Parsers:**
```python
{
    "sarif": SARIFParser,        # SAST/DAST tools
    "cyclonedx": CycloneDXParser, # SBOM/SCA tools
    # Future: "spdx", "osv", "vex", "csaf"
}
```

**Status:** Production-ready.

---

#### Missing: SPDX Parser
**Status:** 🚧 Not implemented (planned for Phase 2)

**Required for:**
- SPDX 2.2/2.3 SBOM support
- Full compliance with EU CRA (accepts SPDX or CycloneDX)

---

### 1.3 Database Repositories (✅ 100%)

#### ComponentRepository
**File:** `/src/api/repositories/component.py`

**Methods:**
- ✅ `create_component()` - Create single component with deduplication
- ✅ `bulk_create_components()` - Bulk insert with overwrite_mode="ignore"
- ✅ `get_by_purl()` - Query by Package URL
- ✅ `list_customer_components()` - Paginated list
- ✅ `get_components_with_vulnerabilities()` - Find vulnerable components
- ✅ `count_customer_components()` - Count total
- ✅ `delete_customer_components()` - Cleanup

**Key Features:**
- PURL-based deduplication (idempotent inserts)
- Safe key generation (`pkg:npm/express@4.17.1` → `pkg_npm_express_4_17_1`)
- Customer isolation (all queries filter by customer_id)

**Schema:**
```json
{
  "_key": "pkg_npm_express_4_17_1",
  "customer_id": "acme_corp",
  "purl": "pkg:npm/express@4.17.1",
  "name": "express",
  "version": "4.17.1",
  "type": "library",
  "metadata": {},
  "created_at": "2026-03-06T10:00:00Z",
  "updated_at": "2026-03-06T10:00:00Z"
}
```

**Status:** Production-ready.

---

#### ScanSessionRepository
**File:** `/src/api/repositories/scan.py`

**Methods:**
- ✅ `create_session()` - Create scan session with validation
- ✅ `update_session_status()` - Update status and counts
- ✅ `get()` - Get session by ID
- ✅ `list_customer_sessions()` - Paginated list

**Uses Domain Model:**
```python
from complira_graph.models import ScanSession

session = ScanSession(
    customer_id="acme_corp",
    tool_name="Grype",
    tool_version="0.65.1",
    scan_type="sbom",
    status="processing",
    findings_count=0,
    components_count=0,
    ...
)
```

**Status:** Production-ready.

---

#### ScanFindingRepository
**File:** `/src/api/repositories/scan.py`

**Methods:**
- ✅ `create_finding()` - Create vulnerability finding
- ✅ `list_session_findings()` - Get findings for scan
- ✅ `get_by_cve()` - Query by CVE ID

**Status:** Production-ready.

---

### 1.4 Services (✅ 70%)

#### ScanIngestionService
**File:** `/src/api/services/scan.py`

**Key Method:** `ingest_scan(customer_id, scan_request)`

**Flow:**
1. ✅ Get parser from factory (supports CycloneDX)
2. ✅ Parse SBOM payload
3. ✅ Create scan session
4. ✅ Store findings (vulnerabilities)
5. ✅ Store components (bulk insert)
6. ✅ Create graph edges:
   - `finding_to_cve` (customer DB → reference DB)
   - `component_to_finding` (links components to vulnerabilities)
7. ✅ Update session status

**SBOM Support:**
- ✅ Accepts `scan_type="sbom"` or `scan_type="sca"`
- ✅ Extracts components from CycloneDX
- ✅ Creates customer_components collection entries
- ✅ Links components to findings via location/PURL matching

**Example:**
```python
service = ScanIngestionService(db=get_reference_db(), cache=cache)

result = await service.ingest_scan(
    customer_id="acme_corp",
    scan_request=ScanIngestRequest(
        format="cyclonedx",
        scan_type="sbom",
        payload={...},  # CycloneDX JSON
        metadata={
            "repository": "https://github.com/acme/app",
            "commit_sha": "abc123"
        }
    )
)

# Returns:
# {
#   "scan_session_id": "scan_abc123",
#   "findings_count": 23,
#   "components_count": 347,
#   "status": "completed"
# }
```

**Status:** Production-ready for SBOM ingestion.

---

### 1.5 API Endpoints (✅ 100% for scan, 0% for SBOM)

#### Scan Endpoints (Doubles as SBOM Upload)
**File:** `/src/api/v1/endpoints/scan.py`

**Endpoints Implemented:**

##### 1. POST /v1/scan/ingest
**Purpose:** Ingest scan results (including SBOMs)

**Request:**
```json
{
  "format": "cyclonedx",
  "scan_type": "sbom",
  "payload": { /* CycloneDX SBOM */ },
  "metadata": {
    "repository": "https://github.com/org/repo",
    "branch": "main"
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "scan_session_id": "scan_abc123",
    "findings_count": 23,
    "components_count": 347,
    "status": "completed"
  },
  "metadata": {
    "cache_hit": false,
    "execution_time_ms": 1234.5
  }
}
```

**Status:** ✅ Works for SBOM upload (tested)

---

##### 2. GET /v1/scan/{session_id}
**Purpose:** Get scan session details

**Response:**
```json
{
  "success": true,
  "data": {
    "session_id": "scan_abc123",
    "tool_name": "Grype",
    "tool_version": "0.65.1",
    "scan_type": "sbom",
    "scan_timestamp": "2026-03-06T10:00:00Z",
    "status": "completed",
    "findings_count": 23,
    "components_count": 347,
    "created_at": "2026-03-06T10:05:00Z",
    "metadata": {}
  }
}
```

**Status:** ✅ Production-ready

---

##### 3. GET /v1/scan/{session_id}/findings
**Purpose:** List findings for a scan (paginated)

**Query Parameters:**
- `limit`: Max findings (1-1000, default 100)
- `offset`: Pagination offset

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "finding_id": "finding_001",
      "cve_id": "CVE-2024-1234",
      "severity": "HIGH",
      "description": "Prototype pollution in lodash",
      "location": "pkg:npm/lodash@4.17.20",
      "tool_name": "Grype",
      "created_at": "2026-03-06T10:05:00Z"
    }
  ]
}
```

**Status:** ✅ Production-ready

---

##### 4. GET /v1/scans
**Purpose:** List all scans for customer (paginated)

**Status:** ✅ Production-ready

---

### 1.6 VEX Synthesizer (✅ 50%)

#### VEXSynthesizerAgent
**File:** `/src/complira_graph/llm_agents/vex_synthesizer.py`

**Capabilities:**
- ✅ Uses Claude Sonnet 4.5 for VEX generation
- ✅ `find_gaps()` - Find components needing VEX assessment
- ✅ `enrich()` - Generate VEX document with impact analysis
- ✅ `validate()` - Validate VEX document quality
- ✅ `persist()` - Store VEX metadata in database

**Generated Output:**
```json
{
  "format": "cyclonedx",
  "vex_document": {
    "bomFormat": "CycloneDX",
    "specVersion": "1.5",
    "vulnerabilities": [
      {
        "id": "CVE-2024-1234",
        "analysis": {
          "state": "affected|not_affected|under_investigation",
          "justification": "vulnerable_code_not_in_execute_path",
          "detail": "Impact analysis..."
        }
      }
    ]
  },
  "assessments": [...]
}
```

**Status:** ✅ LLM agent implemented, 🚧 Not exposed via API endpoint

---

### 1.7 Domain Models (✅ 100%)

#### Models Defined
**File:** `/src/complira_graph/models.py`

**Available Models:**
- ✅ `Vulnerability` (CVE records)
- ✅ `Weakness` (CWE records)
- ✅ `KEVEntry` (CISA KEV)
- ✅ `Component` (Software packages)
- ✅ `ScanSession` (Scan metadata)
- ✅ `ScanFinding` (Vulnerability findings)

**Features:**
- Pydantic validation
- Deterministic _key generation
- Timestamp management
- JSON serialization

**Status:** Production-ready.

---

## 2. What's Missing

### 2.1 SBOM-Specific API Endpoints (🚧 0%)

We need dedicated SBOM management endpoints beyond the generic scan endpoints:

#### Missing Endpoints:

##### 1. POST /v1/sbom/upload
**Purpose:** Dedicated SBOM upload (alternative to `/v1/scan/ingest`)

**Why Needed:**
- Clearer API semantics for SBOM-specific uploads
- SBOM-specific response format with enrichment data
- SBOM metadata (serial number, BOM format, etc.)

**Required:**
- New endpoint in `/src/api/v1/endpoints/sbom.py`
- Reuse ScanIngestionService internally
- Return SBOM-specific response model

**Effort:** 4 hours

---

##### 2. GET /v1/sbom
**Purpose:** List all SBOMs for customer

**Response:**
```json
{
  "total": 42,
  "limit": 100,
  "offset": 0,
  "sboms": [
    {
      "sbom_id": "sbom_20260306_abc123",
      "format": "CycloneDX",
      "spec_version": "1.5",
      "component_count": 347,
      "vulnerability_count": 23,
      "created_at": "2026-03-06T10:05:00Z"
    }
  ]
}
```

**Required:**
- New endpoint
- Query scan_sessions where scan_type="sbom"
- SBOM-specific response model

**Effort:** 3 hours

---

##### 3. GET /v1/sbom/{sbom_id}
**Purpose:** Get SBOM details

**Response:**
```json
{
  "sbom_id": "sbom_20260306_abc123",
  "customer_id": "acme_corp",
  "format": "CycloneDX",
  "spec_version": "1.5",
  "serial_number": "urn:uuid:...",
  "metadata": {},
  "component_count": 347,
  "vulnerability_count": 23,
  "severity_distribution": {
    "critical": 2,
    "high": 8,
    "medium": 13
  },
  "created_at": "2026-03-06T10:05:00Z"
}
```

**Effort:** 2 hours

---

##### 4. GET /v1/sbom/{sbom_id}/components
**Purpose:** List components in SBOM (paginated)

**Effort:** 3 hours

---

##### 5. GET /v1/sbom/{sbom_id}/vulnerabilities
**Purpose:** List vulnerabilities in SBOM (filterable by severity)

**Effort:** 3 hours

---

##### 6. POST /v1/sbom/{sbom_id}/vex
**Purpose:** Generate VEX document for SBOM

**Request:**
```json
{
  "format": "cyclonedx",  // or "csaf"
  "components": ["pkg:npm/express@4.17.1"]  // optional filter
}
```

**Response:**
```json
{
  "vex_document": { /* CycloneDX VEX */ },
  "generated_at": "2026-03-06T10:00:00Z",
  "assessments_count": 23
}
```

**Required:**
- Integrate VEXSynthesizerAgent
- Call agent.find_gaps() with SBOM components
- Call agent.enrich() for each component
- Return generated VEX document

**Effort:** 8 hours

---

##### 7. GET /v1/sbom/{sbom_id}/vex (Optional)
**Purpose:** Retrieve previously generated VEX

**Effort:** 2 hours

---

##### 8. DELETE /v1/sbom/{sbom_id}
**Purpose:** Delete SBOM and associated data

**Effort:** 2 hours

---

### 2.2 SBOM Service Layer (🚧 30%)

#### Missing: SBOMService
**File:** `/src/api/services/sbom.py` (DOES NOT EXIST)

**Required Methods:**
```python
class SBOMService:
    async def list_sboms(customer_id, limit, offset) -> List[SBOM]
    async def get_sbom(customer_id, sbom_id) -> SBOM
    async def get_sbom_components(customer_id, sbom_id, limit, offset)
    async def get_sbom_vulnerabilities(customer_id, sbom_id, severity_filter)
    async def generate_vex(customer_id, sbom_id, format, component_filter) -> VEX
    async def delete_sbom(customer_id, sbom_id)
```

**Rationale:**
- Separation of concerns (SBOM logic separate from scan logic)
- SBOM-specific business logic (VEX generation, enrichment)
- Easier to test and maintain

**Dependencies:**
- ScanSessionRepository (read scan_sessions)
- ComponentRepository (read customer_components)
- ScanFindingRepository (read scan_findings)
- VEXSynthesizerAgent (generate VEX)

**Effort:** 12 hours

---

### 2.3 SBOM Request/Response Models (🚧 0%)

#### Missing Models:
**File:** `/src/api/models/requests/sbom.py` (DOES NOT EXIST)

**Required:**
```python
class SBOMUploadRequest(BaseModel):
    format: Literal["cyclonedx", "spdx"]
    payload: Dict[str, Any]
    metadata: Dict[str, Any] = {}

class VEXGenerateRequest(BaseModel):
    format: Literal["cyclonedx", "csaf"]
    component_filter: Optional[List[str]] = None
```

**File:** `/src/api/models/responses/sbom.py` (DOES NOT EXIST)

**Required:**
```python
class SBOMUploadResponse(BaseModel):
    sbom_id: str
    status: str
    component_count: int
    vulnerability_count: int
    severity_distribution: Dict[str, int]
    enrichment_summary: Dict[str, Any]
    links: Dict[str, str]

class SBOMResponse(BaseModel):
    sbom_id: str
    customer_id: str
    format: str
    spec_version: str
    serial_number: str
    component_count: int
    vulnerability_count: int
    severity_distribution: Dict[str, int]
    created_at: str

class SBOMListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    sboms: List[SBOMResponse]

class VEXGenerateResponse(BaseModel):
    vex_document: Dict[str, Any]
    format: str
    generated_at: str
    assessments_count: int
    model: str
    input_tokens: int
    output_tokens: int
```

**Effort:** 4 hours

---

### 2.4 SBOM Repository (Optional - 🚧 0%)

Current approach: Reuse ScanSessionRepository for SBOM metadata.

**Alternative:** Create dedicated `SBOMRepository` for clearer separation.

**File:** `/src/api/repositories/sbom.py` (DOES NOT EXIST)

**Benefit:**
- Clearer semantics (`sbom_repo.get()` vs `scan_session_repo.get()`)
- SBOM-specific queries (filter by serial_number, BOM format)

**Effort:** 4 hours (optional)

---

### 2.5 SBOM Database Collections (✅ 90%)

#### Current Schema:
We're reusing `scan_sessions` for SBOM metadata. This works but could be clearer.

#### Option 1: Add sbom_documents collection (Recommended)
**Collection:** `sbom_documents`

**Schema:**
```json
{
  "_key": "sbom_20260306_abc123",
  "customer_id": "acme_corp",
  "scan_session_id": "scan_abc123",  // Link to scan_sessions
  "sbom_format": "CycloneDX",
  "spec_version": "1.5",
  "serial_number": "urn:uuid:...",
  "metadata": {},
  "component_count": 347,
  "vulnerability_count": 23,
  "created_at": "2026-03-06T10:05:00Z"
}
```

**Rationale:**
- Clearer data model (SBOM is not a "scan")
- Store SBOM-specific metadata (serial_number, BOM format)
- Separate SBOM lifecycle from scan lifecycle

**Migration Path:**
- Create `sbom_documents` collection
- Populate from existing `scan_sessions` where `scan_type="sbom"`
- Add `sbom_id` field to `customer_components`

**Effort:** 6 hours

**Decision:** Optional (current approach works, but this is cleaner)

---

#### Missing Edge: sbom_contains_component
**Edge:** `sbom_documents` → `customer_components`

**Current:** Components link to scan_session via metadata
**Better:** Explicit edge for graph traversal

**Schema:**
```json
{
  "_from": "sbom_documents/sbom_20260306_abc123",
  "_to": "customer_components/pkg_npm_express_4_17_1",
  "relationship": "contains",
  "scope": "required"  // required, optional, excluded
}
```

**Benefit:** Fast SBOM → components queries

**Effort:** 2 hours (create edge on SBOM upload)

---

### 2.6 SPDX Parser (🚧 0%)

**File:** `/src/api/parsers/spdx.py` (DOES NOT EXIST)

**Required for:**
- EU CRA compliance (SPDX is accepted format)
- Full SBOM ecosystem support

**Capabilities Needed:**
- Parse SPDX 2.2/2.3 JSON format
- Extract packages (SPDX equivalent of components)
- Extract relationships (dependencies)
- Map to ParsedScanData format

**Example SPDX:**
```json
{
  "spdxVersion": "SPDX-2.3",
  "dataLicense": "CC0-1.0",
  "SPDXID": "SPDXRef-DOCUMENT",
  "name": "acme-web-app",
  "packages": [
    {
      "SPDXID": "SPDXRef-Package-express",
      "name": "express",
      "versionInfo": "4.17.1",
      "externalRefs": [
        {
          "referenceType": "purl",
          "referenceLocator": "pkg:npm/express@4.17.1"
        }
      ]
    }
  ],
  "relationships": [
    {
      "spdxElementId": "SPDXRef-DOCUMENT",
      "relationshipType": "DESCRIBES",
      "relatedSpdxElement": "SPDXRef-Package-express"
    }
  ]
}
```

**Implementation:**
```python
class SPDXParser(BaseScanParser):
    def parse(self, payload: Dict[str, Any]) -> ParsedScanData:
        # Extract packages
        # Map SPDXID to PURL via externalRefs
        # Extract relationships
        # Return ParsedScanData
        pass
```

**Effort:** 16 hours (complex format, needs testing)

**Priority:** Medium (Phase 2)

---

### 2.7 VEX Export Formats (🚧 50%)

#### Current: CycloneDX VEX
- ✅ VEXSynthesizerAgent generates CycloneDX 1.5 VEX

#### Missing: CSAF VEX
**Format:** OASIS Common Security Advisory Framework

**Use Case:** Government/enterprise compliance (NIST, CISA)

**Example:**
```json
{
  "document": {
    "category": "csaf_vex",
    "csaf_version": "2.0",
    "publisher": {
      "category": "vendor",
      "name": "ACME Corp"
    },
    "title": "VEX for acme-web-app",
    "tracking": {
      "id": "ACME-VEX-2026-001",
      "status": "final",
      "version": "1"
    }
  },
  "product_tree": {},
  "vulnerabilities": [
    {
      "cve": "CVE-2024-1234",
      "product_status": {
        "known_affected": [],
        "known_not_affected": ["pkg:npm/express@4.17.1"]
      },
      "threats": []
    }
  ]
}
```

**Effort:** 12 hours

**Priority:** Low (Phase 3)

---

### 2.8 Missing Indexes (🚧 10%)

#### Current Indexes:
```python
# customer_components
- customer_id (non-unique)
- customer_id, purl (unique)
```

#### Recommended Additional Indexes:
```python
# scan_sessions
- customer_id, scan_type (for filtering SBOMs)
- serial_number (unique, for SBOM deduplication)

# scan_findings
- customer_id, scan_session_id (exists)
- customer_id, severity (for severity filtering)
```

**Effort:** 2 hours

**Priority:** High (performance optimization)

---

## 3. Implementation Plan

### Overview

**Total Estimated Effort:** 5-6 days (40-48 hours)

**Approach:**
- Phase 1 (Days 1-2): SBOM API endpoints (critical path)
- Phase 2 (Days 3-4): VEX integration and SBOM service
- Phase 3 (Days 5-6): Polish, testing, documentation

---

### Phase 1: SBOM API Endpoints (Days 1-2)

**Goal:** Create dedicated SBOM management endpoints that clients expect.

**Priority:** CRITICAL (blocking client integration)

---

#### Task 1.1: Create SBOM Request/Response Models
**File:** `/src/api/models/requests/sbom.py`, `/src/api/models/responses/sbom.py`

**What to Create:**
```python
# requests/sbom.py
class SBOMUploadRequest(BaseModel):
    format: Literal["cyclonedx"]
    payload: Dict[str, Any]
    metadata: Dict[str, Any] = Field(default_factory=dict)

class VEXGenerateRequest(BaseModel):
    format: Literal["cyclonedx", "csaf"] = "cyclonedx"
    component_filter: Optional[List[str]] = None

# responses/sbom.py
class SBOMUploadResponse(BaseModel):
    sbom_id: str
    status: str
    component_count: int
    vulnerability_count: int
    severity_distribution: Dict[str, int]
    enrichment_summary: Dict[str, Any]
    links: Dict[str, str]

class SBOMResponse(BaseModel):
    sbom_id: str
    customer_id: str
    format: str
    spec_version: str
    serial_number: Optional[str]
    component_count: int
    vulnerability_count: int
    severity_distribution: Dict[str, int]
    created_at: str
    updated_at: str
    metadata: Dict[str, Any]

class SBOMListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    sboms: List[SBOMResponse]

class ComponentResponse(BaseModel):
    purl: str
    name: str
    version: str
    type: str
    licenses: List[Dict[str, Any]]
    vulnerability_count: int

class VEXGenerateResponse(BaseModel):
    vex_document: Dict[str, Any]
    format: str
    generated_at: str
    assessments_count: int
```

**Testing:**
```bash
# Validate models with test data
pytest tests/api/models/test_sbom_models.py
```

**Estimated Time:** 4 hours

**Dependencies:** None

**Deliverable:** Model files with Pydantic validation

---

#### Task 1.2: Create SBOM Endpoints File
**File:** `/src/api/v1/endpoints/sbom.py`

**What to Create:**
```python
from fastapi import APIRouter, Depends, HTTPException, Query
from api.core.security import Customer, get_current_customer
from api.models.requests.sbom import SBOMUploadRequest
from api.models.responses.sbom import SBOMUploadResponse, SBOMListResponse
from api.services.scan import ScanIngestionService

router = APIRouter()

@router.post("/upload", response_model=APIResponse[SBOMUploadResponse])
async def upload_sbom(
    request: SBOMUploadRequest,
    customer: Customer = Depends(get_current_customer),
):
    """
    POST /v1/sbom/upload

    Upload SBOM (CycloneDX or SPDX format).

    Returns SBOM ID and enrichment summary.
    """
    # Implementation details below
    pass

@router.get("", response_model=APIResponse[SBOMListResponse])
async def list_sboms(
    customer: Customer = Depends(get_current_customer),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """
    GET /v1/sbom

    List all SBOMs for customer.
    """
    pass

@router.get("/{sbom_id}", response_model=APIResponse[SBOMResponse])
async def get_sbom(
    sbom_id: str,
    customer: Customer = Depends(get_current_customer),
):
    """
    GET /v1/sbom/{sbom_id}

    Get SBOM details.
    """
    pass

@router.get("/{sbom_id}/components")
async def list_sbom_components(
    sbom_id: str,
    customer: Customer = Depends(get_current_customer),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """
    GET /v1/sbom/{sbom_id}/components

    List components in SBOM.
    """
    pass

@router.get("/{sbom_id}/vulnerabilities")
async def list_sbom_vulnerabilities(
    sbom_id: str,
    customer: Customer = Depends(get_current_customer),
    severity: Optional[str] = Query(None, description="Filter by severity (critical,high,medium,low)"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """
    GET /v1/sbom/{sbom_id}/vulnerabilities

    List vulnerabilities in SBOM (filterable by severity).
    """
    pass
```

**Implementation Strategy:**
- Reuse existing ScanIngestionService for upload
- Query scan_sessions with scan_type="sbom" filter
- Use ComponentRepository and ScanFindingRepository
- Return SBOM-specific response models

**Testing:**
```bash
# Manual testing with curl
curl -X POST http://localhost:8000/v1/sbom/upload \
  -H "X-API-Key: test_key" \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/cyclonedx_sbom.json

# Unit tests
pytest tests/api/endpoints/test_sbom.py
```

**Estimated Time:** 8 hours

**Dependencies:** Task 1.1 (models)

**Deliverable:** Working SBOM endpoints (no VEX yet)

---

#### Task 1.3: Register SBOM Router
**File:** `/src/api/v1/router.py`

**Changes:**
```python
from api.v1.endpoints import scan, reference, enrichment, sbom

# Add SBOM router
api_router.include_router(sbom.router, prefix="/sbom", tags=["sbom"])
```

**Testing:**
```bash
# Check API docs
open http://localhost:8000/docs
# Verify /v1/sbom endpoints appear
```

**Estimated Time:** 15 minutes

**Dependencies:** Task 1.2

**Deliverable:** SBOM endpoints visible in API docs

---

#### Task 1.4: Test SBOM Upload End-to-End
**Goal:** Verify full SBOM upload flow

**Test Case:**
```python
# tests/integration/test_sbom_upload.py

async def test_sbom_upload_cyclonedx():
    """Test CycloneDX SBOM upload."""

    # Load fixture
    with open("tests/fixtures/cyclonedx_sbom.json") as f:
        sbom_payload = json.load(f)

    # Upload SBOM
    response = client.post(
        "/v1/sbom/upload",
        headers={"X-API-Key": "test_key"},
        json={
            "format": "cyclonedx",
            "payload": sbom_payload,
            "metadata": {
                "repository": "https://github.com/test/repo",
                "branch": "main"
            }
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "sbom_id" in data["data"]
    assert data["data"]["component_count"] > 0

    sbom_id = data["data"]["sbom_id"]

    # Verify SBOM was created
    response = client.get(
        f"/v1/sbom/{sbom_id}",
        headers={"X-API-Key": "test_key"}
    )

    assert response.status_code == 200
    assert response.json()["data"]["format"] == "CycloneDX"
```

**Estimated Time:** 2 hours

**Dependencies:** Task 1.1, 1.2, 1.3

**Deliverable:** Passing integration test

---

### Phase 2: VEX Integration (Days 3-4)

**Goal:** Expose VEX generation via API endpoint.

---

#### Task 2.1: Create VEX Generation Endpoint
**File:** `/src/api/v1/endpoints/sbom.py` (add to existing)

**Implementation:**
```python
from complira_graph.llm_agents.vex_synthesizer import VEXSynthesizerAgent
from api.models.responses.sbom import VEXGenerateResponse

@router.post("/{sbom_id}/vex", response_model=APIResponse[VEXGenerateResponse])
async def generate_vex(
    sbom_id: str,
    request: VEXGenerateRequest,
    customer: Customer = Depends(get_current_customer),
):
    """
    POST /v1/sbom/{sbom_id}/vex

    Generate VEX (Vulnerability Exploitability eXchange) document.

    Uses Claude Sonnet 4.5 to analyze vulnerabilities and generate
    impact assessments.
    """
    import time
    start_time = time.time()

    # Validate SBOM exists
    customer_db = get_customer_db(customer.id)
    session_repo = ScanSessionRepository(customer_db)

    session = session_repo.get(sbom_id)
    if not session or session.get("scan_type") != "sbom":
        raise HTTPException(status_code=404, detail="SBOM not found")

    # Get components for SBOM
    component_repo = ComponentRepository(customer_db)

    # Filter components if requested
    if request.component_filter:
        components = [
            component_repo.get_by_purl(customer.id, purl)
            for purl in request.component_filter
        ]
        components = [c for c in components if c]  # Filter None
    else:
        # Get all components for this SBOM
        query = """
        FOR component IN customer_components
            FILTER component.customer_id == @customer_id
            FILTER component.metadata.scan_session_id == @sbom_id
            RETURN component
        """
        cursor = customer_db.aql_execute(
            query,
            bind_vars={"customer_id": customer.id, "sbom_id": sbom_id}
        )
        components = list(cursor)

    # Get PURLs for VEX agent
    purls = [c.get("purl") for c in components if c.get("purl")]

    # Initialize VEX agent
    from api.core.database import get_reference_db
    vex_agent = VEXSynthesizerAgent(db=get_reference_db())

    # Find components with vulnerabilities
    gaps = vex_agent.find_gaps(sbom_components=purls)

    if not gaps:
        return APIResponse(
            success=True,
            data=VEXGenerateResponse(
                vex_document={
                    "bomFormat": "CycloneDX",
                    "specVersion": "1.5",
                    "vulnerabilities": []
                },
                format=request.format,
                generated_at=datetime.utcnow().isoformat(),
                assessments_count=0
            )
        )

    # Generate VEX for each component with vulnerabilities
    assessments = []
    vex_vulnerabilities = []

    for gap in gaps:
        enrichment = vex_agent.enrich(gap)

        if vex_agent.validate(enrichment):
            assessments.extend(enrichment["assessments"])

            # Add to VEX document
            for assessment in enrichment["assessments"]:
                vex_vulnerabilities.append({
                    "id": assessment["vulnerability_id"],
                    "analysis": {
                        "state": assessment["status"],
                        "justification": assessment.get("justification"),
                        "detail": assessment["impact_analysis"]["details"]
                    }
                })

    # Build VEX document
    vex_document = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "component": session.get("metadata", {}).get("component", {})
        },
        "vulnerabilities": vex_vulnerabilities
    }

    execution_time_ms = (time.time() - start_time) * 1000

    return APIResponse(
        success=True,
        data=VEXGenerateResponse(
            vex_document=vex_document,
            format=request.format,
            generated_at=datetime.utcnow().isoformat(),
            assessments_count=len(assessments)
        ),
        metadata=ResponseMetadata(
            cache_hit=False,
            execution_time_ms=execution_time_ms
        )
    )
```

**Testing:**
```bash
# Test VEX generation
curl -X POST http://localhost:8000/v1/sbom/{sbom_id}/vex \
  -H "X-API-Key: test_key" \
  -H "Content-Type: application/json" \
  -d '{"format": "cyclonedx"}'

# Should return CycloneDX VEX document
```

**Estimated Time:** 8 hours

**Dependencies:** Phase 1 complete

**Deliverable:** Working VEX generation endpoint

---

#### Task 2.2: Add VEX Caching (Optional)
**Goal:** Cache VEX documents to avoid re-running expensive LLM calls

**Implementation:**
```python
# Check Redis cache first
cache_key = f"vex:{customer.id}:{sbom_id}"
cached_vex = await cache.get(cache_key)

if cached_vex:
    return APIResponse(
        success=True,
        data=VEXGenerateResponse(**json.loads(cached_vex)),
        metadata=ResponseMetadata(cache_hit=True)
    )

# Generate VEX (as above)
# ...

# Cache result (24 hour TTL)
await cache.set(cache_key, json.dumps(vex_response), ttl=86400)
```

**Estimated Time:** 2 hours

**Priority:** Medium (performance optimization)

---

#### Task 2.3: Create VEX Tests
**File:** `tests/integration/test_vex_generation.py`

**Test Cases:**
```python
async def test_vex_generation_cyclonedx():
    """Test VEX generation for CycloneDX format."""
    # Upload SBOM with vulnerabilities
    # Generate VEX
    # Verify VEX structure
    pass

async def test_vex_generation_no_vulnerabilities():
    """Test VEX generation for SBOM with no vulns."""
    # Should return empty VEX document
    pass

async def test_vex_generation_component_filter():
    """Test VEX generation with component filter."""
    # Generate VEX for specific components only
    pass
```

**Estimated Time:** 3 hours

**Dependencies:** Task 2.1

**Deliverable:** Passing VEX tests

---

#### Task 2.4: Update API Documentation
**File:** `/docs/API_DOCUMENTATION.md`

**Add:**
- SBOM upload endpoint documentation
- SBOM retrieval endpoint documentation
- VEX generation endpoint documentation
- Example requests/responses
- Error handling

**Estimated Time:** 2 hours

**Dependencies:** Phase 1 and 2 complete

**Deliverable:** Updated API docs

---

### Phase 3: Polish & Testing (Days 5-6)

**Goal:** Production-readiness, testing, performance optimization.

---

#### Task 3.1: Add Performance Indexes
**File:** `/src/api/core/database.py`

**Changes:**
```python
customer_indexes = {
    "scan_sessions": [
        {"fields": ["customer_id"], "unique": False},
        {"fields": ["customer_id", "created_at"], "unique": False},
        {"fields": ["customer_id", "scan_type"], "unique": False},  # NEW
    ],
    "scan_findings": [
        {"fields": ["customer_id"], "unique": False},
        {"fields": ["customer_id", "scan_session_id"], "unique": False},
        {"fields": ["customer_id", "cve_id"], "unique": False},
        {"fields": ["customer_id", "severity"], "unique": False},  # NEW
    ],
}
```

**Testing:**
```bash
# Verify indexes created
python -c "from api.core.database import get_customer_db; db = get_customer_db('test'); print(db.collection('scan_sessions').indexes())"
```

**Estimated Time:** 1 hour

**Priority:** High (performance)

---

#### Task 3.2: Add Error Handling
**Goal:** Graceful error handling for common failure cases

**Scenarios:**
- Invalid SBOM format
- Malformed JSON payload
- Missing required fields
- SBOM too large (>10MB)
- Rate limiting (VEX generation)
- LLM API failures

**Implementation:**
```python
# In sbom.py endpoints

@router.post("/upload")
async def upload_sbom(...):
    try:
        # Validate payload size
        if len(json.dumps(request.payload)) > 10_000_000:  # 10MB
            raise HTTPException(
                status_code=413,
                detail="SBOM payload too large (max 10MB)"
            )

        # Existing upload logic
        ...

    except ValueError as e:
        # Parser validation error
        raise HTTPException(status_code=400, detail=f"Invalid SBOM format: {str(e)}")

    except Exception as e:
        logger.error("SBOM upload failed", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")
```

**Estimated Time:** 3 hours

**Priority:** High (production-readiness)

---

#### Task 3.3: Load Testing
**Goal:** Verify API can handle expected load

**Test Scenarios:**
- 100 concurrent SBOM uploads
- SBOM with 10,000 components
- VEX generation for large SBOM
- Multiple customers uploading simultaneously

**Tools:**
- Locust or k6 for load testing
- Monitor ArangoDB performance
- Monitor Redis cache hit rate

**Success Criteria:**
- p95 latency < 5 seconds for SBOM upload
- p95 latency < 30 seconds for VEX generation
- No database deadlocks
- No memory leaks

**Estimated Time:** 4 hours

**Priority:** Medium (pre-production)

---

#### Task 3.4: Create Integration Test Suite
**File:** `tests/integration/test_sbom_complete_flow.py`

**Test Flow:**
```python
async def test_complete_sbom_flow():
    """Test complete SBOM workflow from upload to VEX generation."""

    # 1. Upload SBOM
    sbom_id = upload_sbom_fixture()

    # 2. Verify SBOM exists
    sbom = get_sbom(sbom_id)
    assert sbom["component_count"] > 0

    # 3. List components
    components = list_sbom_components(sbom_id)
    assert len(components) == sbom["component_count"]

    # 4. List vulnerabilities
    vulns = list_sbom_vulnerabilities(sbom_id, severity="high,critical")
    assert len(vulns) > 0

    # 5. Generate VEX
    vex = generate_vex(sbom_id)
    assert vex["assessments_count"] > 0
    assert "vex_document" in vex

    # 6. Verify VEX structure
    assert vex["vex_document"]["bomFormat"] == "CycloneDX"
    assert vex["vex_document"]["specVersion"] == "1.5"

    # 7. Delete SBOM (cleanup)
    delete_sbom(sbom_id)
```

**Estimated Time:** 3 hours

**Priority:** High (quality assurance)

---

#### Task 3.5: Create API Usage Examples
**File:** `/docs/examples/sbom_upload_example.py`

**Example:**
```python
"""
Example: Upload SBOM and generate VEX using Complira API.

Requirements:
- pip install requests
- API key from Complira dashboard
"""

import requests
import json

# Configuration
API_BASE_URL = "https://api.complira.dev"
API_KEY = "your_api_key_here"

def upload_sbom(sbom_path):
    """Upload SBOM to Complira."""

    # Load SBOM
    with open(sbom_path) as f:
        sbom_payload = json.load(f)

    # Upload
    response = requests.post(
        f"{API_BASE_URL}/v1/sbom/upload",
        headers={
            "X-API-Key": API_KEY,
            "Content-Type": "application/json"
        },
        json={
            "format": "cyclonedx",
            "payload": sbom_payload,
            "metadata": {
                "repository": "https://github.com/your-org/your-repo",
                "branch": "main"
            }
        }
    )

    response.raise_for_status()
    data = response.json()["data"]

    print(f"SBOM uploaded successfully!")
    print(f"SBOM ID: {data['sbom_id']}")
    print(f"Components: {data['component_count']}")
    print(f"Vulnerabilities: {data['vulnerability_count']}")

    return data["sbom_id"]

def generate_vex(sbom_id):
    """Generate VEX document for SBOM."""

    response = requests.post(
        f"{API_BASE_URL}/v1/sbom/{sbom_id}/vex",
        headers={
            "X-API-Key": API_KEY,
            "Content-Type": "application/json"
        },
        json={
            "format": "cyclonedx"
        }
    )

    response.raise_for_status()
    data = response.json()["data"]

    print(f"VEX generated successfully!")
    print(f"Assessments: {data['assessments_count']}")

    # Save VEX document
    with open("vex_document.json", "w") as f:
        json.dump(data["vex_document"], f, indent=2)

    print("VEX document saved to vex_document.json")

    return data

if __name__ == "__main__":
    # Upload SBOM
    sbom_id = upload_sbom("sbom.json")

    # Generate VEX
    vex = generate_vex(sbom_id)
```

**Estimated Time:** 2 hours

**Priority:** Medium (developer experience)

---

#### Task 3.6: Create CLI Tool (Optional)
**Goal:** Command-line tool for SBOM/VEX operations

**Example:**
```bash
# Upload SBOM
complira sbom upload sbom.json --repository https://github.com/org/repo

# List SBOMs
complira sbom list

# Generate VEX
complira vex generate sbom_abc123 --format cyclonedx --output vex.json
```

**Estimated Time:** 6 hours

**Priority:** Low (nice-to-have)

---

## 4. Quick Start Guide

### First 3 Tasks to Tackle

#### Task 1: Create SBOM Models (4 hours)
**Why First:** Models are dependency for endpoints and services.

**Steps:**
1. Create `/src/api/models/requests/sbom.py`
2. Create `/src/api/models/responses/sbom.py`
3. Define request/response models with Pydantic
4. Add validation rules
5. Test models with sample data

**Expected Outcome:**
- Models importable: `from api.models.requests.sbom import SBOMUploadRequest`
- Models validate correctly
- Models serialize to JSON

**Test:**
```python
# Test model validation
request = SBOMUploadRequest(
    format="cyclonedx",
    payload={"bomFormat": "CycloneDX", ...},
    metadata={"repository": "..."}
)
assert request.format == "cyclonedx"
```

---

#### Task 2: Create Basic SBOM Endpoints (8 hours)
**Why Second:** Core functionality clients need.

**Steps:**
1. Create `/src/api/v1/endpoints/sbom.py`
2. Implement `POST /v1/sbom/upload` (reuse ScanIngestionService)
3. Implement `GET /v1/sbom` (list SBOMs)
4. Implement `GET /v1/sbom/{sbom_id}` (get SBOM details)
5. Register router in `/src/api/v1/router.py`
6. Test with curl/httpie

**Expected Outcome:**
- Upload SBOM via API
- List SBOMs for customer
- Get SBOM details by ID

**Test:**
```bash
# Upload SBOM
curl -X POST http://localhost:8000/v1/sbom/upload \
  -H "X-API-Key: test" \
  -H "Content-Type: application/json" \
  -d '{"format": "cyclonedx", "payload": {...}}'

# Should return:
# {"success": true, "data": {"sbom_id": "...", "component_count": 347}}

# List SBOMs
curl http://localhost:8000/v1/sbom -H "X-API-Key: test"

# Get SBOM
curl http://localhost:8000/v1/sbom/{sbom_id} -H "X-API-Key: test"
```

---

#### Task 3: Add VEX Generation Endpoint (8 hours)
**Why Third:** High-value feature for compliance.

**Steps:**
1. Add `POST /v1/sbom/{sbom_id}/vex` endpoint
2. Import `VEXSynthesizerAgent`
3. Call `agent.find_gaps()` with SBOM components
4. Call `agent.enrich()` for each component with vulns
5. Build CycloneDX VEX document
6. Return VEX in response

**Expected Outcome:**
- Generate VEX for SBOM
- VEX contains impact assessments
- VEX follows CycloneDX 1.5 spec

**Test:**
```bash
# Generate VEX
curl -X POST http://localhost:8000/v1/sbom/{sbom_id}/vex \
  -H "X-API-Key: test" \
  -H "Content-Type: application/json" \
  -d '{"format": "cyclonedx"}'

# Should return:
# {
#   "success": true,
#   "data": {
#     "vex_document": {
#       "bomFormat": "CycloneDX",
#       "vulnerabilities": [...]
#     },
#     "assessments_count": 23
#   }
# }
```

---

## 5. Architecture Overview

### Current State

```
┌─────────────────────────────────────────────────────────────┐
│                      IMPLEMENTED (80%)                       │
└─────────────────────────────────────────────────────────────┘

┌──────────────┐
│   Client     │
│   (CI/CD)    │
└──────┬───────┘
       │
       │ POST /v1/scan/ingest
       │ (format=cyclonedx, scan_type=sbom)
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│  API GATEWAY (✅ Complete)                                   │
│  ─────────────────────────────────────────────────────────  │
│  • Authentication (X-API-Key → customer_id)                 │
│  • Exception handling                                       │
│  • Logging (structlog)                                      │
└────────┬────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  SCAN INGESTION SERVICE (✅ Complete)                        │
│  ─────────────────────────────────────────────────────────  │
│  1. Parse SBOM (CycloneDXParser) ✅                          │
│  2. Create scan session ✅                                   │
│  3. Store components (ComponentRepository) ✅                │
│  4. Store findings (ScanFindingRepository) ✅                │
│  5. Create edges (component → finding → CVE) ✅              │
└────────┬────────────────────────────────────────────────────┘
         │
    ┌────┴─────────────────────────┐
    │                              │
    ▼                              ▼
┌─────────────────┐        ┌──────────────────┐
│  CUSTOMER DB    │        │  REFERENCE DB    │
│  (✅ Complete)  │        │  (✅ Complete)   │
│  ─────────────  │        │  ──────────────  │
│  • scan_sessions│        │  • vulnerabilities
│  • scan_findings│        │  • weaknesses    │
│  • customer_    │───────►│  • kev_entries   │
│    components   │ edges  │  • epss_history  │
└─────────────────┘        └──────────────────┘
```

---

### Target State

```
┌─────────────────────────────────────────────────────────────┐
│                      TARGET (100%)                           │
└─────────────────────────────────────────────────────────────┘

┌──────────────┐
│   Client     │
│   (CI/CD)    │
└──────┬───────┘
       │
       │ POST /v1/sbom/upload (NEW)
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│  SBOM ENDPOINTS (🚧 To Build)                                │
│  ─────────────────────────────────────────────────────────  │
│  • POST /v1/sbom/upload                                     │
│  • GET  /v1/sbom                                            │
│  • GET  /v1/sbom/{id}                                       │
│  • GET  /v1/sbom/{id}/components                            │
│  • GET  /v1/sbom/{id}/vulnerabilities                       │
│  • POST /v1/sbom/{id}/vex (VEX generation)                  │
└────────┬────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  SBOM SERVICE (🚧 To Build)                                  │
│  ─────────────────────────────────────────────────────────  │
│  • list_sboms()                                             │
│  • get_sbom()                                               │
│  • get_sbom_components()                                    │
│  • get_sbom_vulnerabilities()                               │
│  • generate_vex() ← Integrates VEXSynthesizerAgent          │
└────────┬────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  VEX SYNTHESIZER AGENT (✅ 50% Complete)                     │
│  ─────────────────────────────────────────────────────────  │
│  • find_gaps() ✅                                            │
│  • enrich() (Claude Sonnet 4.5) ✅                           │
│  • validate() ✅                                             │
│  • persist() ✅                                              │
│  • API endpoint integration (🚧 TO DO)                       │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Testing Strategy

### Unit Tests
**Coverage Target:** 80%+

**Test Files:**
```
tests/api/models/test_sbom_models.py
tests/api/endpoints/test_sbom_endpoints.py
tests/api/services/test_sbom_service.py
tests/api/parsers/test_cyclonedx_parser.py
```

**Key Test Cases:**
- Model validation (valid/invalid payloads)
- Parser validation (CycloneDX format errors)
- Repository CRUD operations
- Service business logic
- Endpoint error handling

**Run:**
```bash
pytest tests/api --cov=api --cov-report=html
```

---

### Integration Tests
**Purpose:** Test full API workflows

**Test Files:**
```
tests/integration/test_sbom_upload.py
tests/integration/test_vex_generation.py
tests/integration/test_sbom_complete_flow.py
```

**Key Scenarios:**
- Upload SBOM → verify components stored
- List SBOMs → verify pagination
- Generate VEX → verify LLM integration
- Multi-tenant isolation (customer A can't see customer B's SBOMs)

**Run:**
```bash
pytest tests/integration --maxfail=1
```

---

### Load Tests
**Purpose:** Verify performance at scale

**Tool:** Locust or k6

**Scenarios:**
- 100 concurrent SBOM uploads (small SBOMs, 50 components)
- 10 concurrent SBOM uploads (large SBOMs, 5000 components)
- 50 concurrent VEX generation requests
- Mixed workload (uploads + queries + VEX)

**Success Criteria:**
- p95 latency < 5s for SBOM upload
- p95 latency < 30s for VEX generation
- No database deadlocks
- No 500 errors under load

**Run:**
```bash
locust -f tests/load/locustfile.py --host http://localhost:8000
```

---

### Manual Testing
**Purpose:** Verify user experience

**Test Plan:**
1. Upload real SBOM from Syft/Grype/Trivy
2. Verify components appear correctly
3. Verify vulnerabilities mapped correctly
4. Generate VEX document
5. Validate VEX with CycloneDX schema validator
6. Test error cases (invalid SBOM, missing fields, etc.)

**Tools:**
- curl / httpie for API testing
- Postman collection (to be created)
- CycloneDX CLI for validation

---

## Summary

### Implementation Checklist

**Phase 1: SBOM API Endpoints (Days 1-2)**
- [ ] Task 1.1: Create SBOM models (4h)
- [ ] Task 1.2: Create SBOM endpoints (8h)
- [ ] Task 1.3: Register router (0.25h)
- [ ] Task 1.4: Test upload end-to-end (2h)

**Phase 2: VEX Integration (Days 3-4)**
- [ ] Task 2.1: Create VEX endpoint (8h)
- [ ] Task 2.2: Add VEX caching (2h)
- [ ] Task 2.3: Create VEX tests (3h)
- [ ] Task 2.4: Update API docs (2h)

**Phase 3: Polish & Testing (Days 5-6)**
- [ ] Task 3.1: Add performance indexes (1h)
- [ ] Task 3.2: Add error handling (3h)
- [ ] Task 3.3: Load testing (4h)
- [ ] Task 3.4: Integration test suite (3h)
- [ ] Task 3.5: API usage examples (2h)
- [ ] Task 3.6: CLI tool (optional, 6h)

**Total:** 48 hours (6 days)

---

### Key Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **VEX generation too slow** | Poor UX | Add caching, async processing |
| **LLM costs too high** | Business viability | Rate limiting, tiered pricing |
| **SBOM parsing failures** | Upload failures | Extensive parser testing, validation |
| **Multi-tenant data leak** | Security breach | Thorough isolation testing |
| **Database performance** | Slow queries | Add indexes, query optimization |

---

### Success Metrics

**API Functionality:**
- ✅ Upload SBOM via API (CycloneDX)
- ✅ List SBOMs for customer
- ✅ Retrieve SBOM details
- ✅ List components in SBOM
- ✅ List vulnerabilities in SBOM
- ✅ Generate VEX document

**Performance:**
- SBOM upload p95 < 5 seconds
- VEX generation p95 < 30 seconds
- Supports 100 concurrent uploads

**Quality:**
- 80%+ test coverage
- Zero critical bugs
- Comprehensive API documentation

---

### Next Steps

1. **Review this plan** with team
2. **Create GitHub issues** for each task
3. **Set up project board** (Kanban or Sprint)
4. **Start Phase 1** (SBOM models + endpoints)
5. **Daily standups** to track progress
6. **Code review** for each PR
7. **Deploy to staging** after Phase 2
8. **Load test** in staging
9. **Deploy to production** after Phase 3

---

## Appendix

### Related Documentation

- `/docs/SUPPLY_CHAIN_ARCHITECTURE.md` - Full architecture design
- `/docs/API_DOCUMENTATION.md` - API reference (to be updated)
- `/docs/MULTI_TENANT_ARCHITECTURE.md` - Multi-tenancy design
- `/src/api/parsers/cyclonedx.py` - CycloneDX parser implementation
- `/src/complira_graph/llm_agents/vex_synthesizer.py` - VEX agent

### External References

- [CycloneDX Specification](https://cyclonedx.org/docs/)
- [SPDX Specification](https://spdx.dev/specifications/)
- [VEX Use Cases](https://www.cisa.gov/sites/default/files/publications/VEX_Use_Cases_Document_508c.pdf)
- [EU Cyber Resilience Act](https://digital-strategy.ec.europa.eu/en/policies/cyber-resilience-act)

---

**Report Generated:** 2026-03-06
**Author:** Claude Code (Audit & Analysis)
**Version:** 1.0
