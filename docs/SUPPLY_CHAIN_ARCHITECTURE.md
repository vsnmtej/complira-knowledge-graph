# Supply Chain Architecture: SBOM Ingestion & VEX Generation

## Executive Summary

This document defines the architecture for the Supply Chain Layer (Option 2) of the Complira cybersecurity compliance platform. It answers the critical question: **"How do clients submit and manage their SBOMs?"**

**Answer:** SBOMs are **uploaded by clients via API** and stored in **isolated customer databases**. They are NOT part of the reference database. The system enriches client SBOMs with reference vulnerability intelligence and generates VEX (Vulnerability Exploitability eXchange) documents for compliance reporting.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Data Model](#data-model)
3. [SBOM Upload Flow](#sbom-upload-flow)
4. [Multi-Tenancy Strategy](#multi-tenancy-strategy)
5. [API Endpoints](#api-endpoints)
6. [VEX Generation](#vex-generation)
7. [Implementation Roadmap](#implementation-roadmap)
8. [Security & Compliance](#security--compliance)

---

## 1. Architecture Overview

### 1.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         COMPLIRA SUPPLY CHAIN LAYER                 │
└─────────────────────────────────────────────────────────────────────┘

┌──────────────────┐
│  Client System   │
│  (CI/CD, SBOM    │
│   Generator)     │
└────────┬─────────┘
         │
         │ 1. Upload SBOM (CycloneDX/SPDX)
         │    POST /v1/sbom/upload
         │    X-API-Key: client_key
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         COMPLIRA API GATEWAY                         │
│  ─────────────────────────────────────────────────────────────────  │
│  1. Authenticate (API key → customer_id)                            │
│  2. Parse SBOM (CycloneDX/SPDX parser)                              │
│  3. Route to customer database                                      │
└────────┬────────────────────────────────────────────────────────────┘
         │
         │
    ┌────┴─────────────────────────────────────────┐
    │                                               │
    │ WRITE                                         │ READ
    ▼                                               ▼
┌─────────────────────────────┐        ┌──────────────────────────────┐
│  CUSTOMER DATABASE           │        │  REFERENCE DATABASE          │
│  (Isolated per Client)       │        │  (Shared, Read-Only)         │
│  ───────────────────────     │        │  ──────────────────────      │
│                              │        │                              │
│  Collections:                │        │  Collections:                │
│  • sbom_documents            │        │  • vulnerabilities (335K)    │
│  • customer_components       │        │  • weaknesses (CWE)          │
│  • scan_findings             │        │  • attack_techniques         │
│                              │        │  • oscal_controls            │
│  Edges:                      │        │  • regulatory_requirements   │
│  • component_has_vuln ──────►├───────►│  • epss_history              │
│  • component_depends_on      │        │  • kev_entries               │
│  • sbom_contains_component   │        │  • exploit_modules           │
│                              │        │                              │
└──────────────────────────────┘        └──────────────────────────────┘
         │
         │ 3. Enrich with reference data
         │    (CVE → CWE → ATT&CK → Controls)
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      VEX SYNTHESIZER (LLM)                           │
│  ─────────────────────────────────────────────────────────────────  │
│  • Claude Sonnet 4.5                                                │
│  • Analyzes component vulnerabilities                               │
│  • Generates impact assessments                                     │
│  • Produces VEX documents (CycloneDX/CSAF)                          │
└────────┬────────────────────────────────────────────────────────────┘
         │
         │ 4. Return VEX to client
         ▼
┌──────────────────┐
│  Client System   │
│  (VEX Document)  │
└──────────────────┘
```

### 1.2 Key Architectural Decisions

| Decision | Rationale |
|----------|-----------|
| **SBOMs in customer DB, NOT reference DB** | SBOMs are customer-specific, proprietary data requiring isolation |
| **API upload (not manual file upload)** | Enables CI/CD integration, automation, and audit trails |
| **Support CycloneDX + SPDX** | Industry standards; most SBOM tools support both formats |
| **VEX generation on-demand** | Expensive LLM operation; only run when client requests VEX |
| **Database-per-customer multi-tenancy** | Strong isolation for SOC 2, GDPR, HIPAA compliance |

---

## 2. Data Model

### 2.1 Customer Database Schema

Customer databases are created automatically on first API request. Each customer gets these collections:

#### Document Collections

##### `sbom_documents`
Stores complete SBOM metadata and metadata.

```json
{
  "_key": "sbom_20260306_abc123",
  "customer_id": "acme_corp",
  "sbom_format": "CycloneDX",
  "spec_version": "1.5",
  "serial_number": "urn:uuid:3e671687-395b-41f5-a30f-a58921a69b79",
  "metadata": {
    "timestamp": "2026-03-06T10:00:00Z",
    "component": {
      "name": "acme-web-app",
      "version": "2.1.0",
      "type": "application"
    },
    "tools": [
      {
        "name": "Syft",
        "version": "0.68.1"
      }
    ]
  },
  "component_count": 347,
  "vulnerability_count": 23,
  "created_at": "2026-03-06T10:05:00Z",
  "updated_at": "2026-03-06T10:05:00Z"
}
```

**Indexes:**
- `customer_id` (non-unique)
- `customer_id, created_at` (non-unique)
- `serial_number` (unique)

##### `customer_components`
Stores individual software components from SBOMs.

```json
{
  "_key": "pkg_npm_express_4_17_1",
  "customer_id": "acme_corp",
  "sbom_id": "sbom_20260306_abc123",
  "purl": "pkg:npm/express@4.17.1",
  "name": "express",
  "version": "4.17.1",
  "type": "library",
  "group": null,
  "licenses": [
    {
      "id": "MIT",
      "name": "MIT License"
    }
  ],
  "hashes": [
    {
      "alg": "SHA-256",
      "content": "abcd1234..."
    }
  ],
  "metadata": {
    "supplier": {
      "name": "TJ Holowaychuk",
      "url": "https://github.com/expressjs/express"
    }
  },
  "created_at": "2026-03-06T10:05:00Z",
  "updated_at": "2026-03-06T10:05:00Z"
}
```

**Indexes:**
- `customer_id` (non-unique)
- `customer_id, purl` (unique)
- `customer_id, sbom_id` (non-unique)

##### `scan_findings` (existing)
Vulnerabilities discovered in customer's components.

```json
{
  "_key": "finding_001",
  "customer_id": "acme_corp",
  "scan_session_id": "scan_abc123",
  "sbom_id": "sbom_20260306_abc123",
  "cve_id": "CVE-2024-1234",
  "severity": "HIGH",
  "description": "Prototype pollution vulnerability in lodash",
  "location": "pkg:npm/lodash@4.17.20",
  "tool_name": "Grype",
  "raw_data": { /* original finding */ },
  "created_at": "2026-03-06T10:05:00Z"
}
```

**Indexes:**
- `customer_id, scan_session_id` (existing)
- `customer_id, cve_id` (existing)
- `customer_id, sbom_id` (new)

#### Edge Collections

##### `sbom_contains_component`
Links SBOM documents to their components.

```json
{
  "_from": "sbom_documents/sbom_20260306_abc123",
  "_to": "customer_components/pkg_npm_express_4_17_1",
  "relationship": "contains",
  "scope": "required"  // required, optional, excluded
}
```

##### `component_has_vulnerability`
Links components to vulnerabilities in reference database.

```json
{
  "_from": "customer_components/pkg_npm_express_4_17_1",
  "_to": "vulnerabilities/CVE_2024_1234",  // Reference DB
  "customer_id": "acme_corp",
  "discovered_at": "2026-03-06T10:05:00Z",
  "scan_session_id": "scan_abc123"
}
```

##### `component_depends_on`
Dependency graph between components.

```json
{
  "_from": "customer_components/pkg_npm_myapp_1_0_0",
  "_to": "customer_components/pkg_npm_express_4_17_1",
  "dependency_type": "runtime",  // runtime, dev, optional
  "version_constraint": "^4.17.0"
}
```

##### `finding_to_cve` (existing)
Links scan findings to CVEs in reference database.

```json
{
  "_from": "scan_findings/finding_001",
  "_to": "vulnerabilities/CVE_2024_1234",  // Reference DB
  "customer_id": "acme_corp"
}
```

### 2.2 Reference Database (Read-Only for Clients)

The reference database contains public vulnerability intelligence shared across all customers:

- `vulnerabilities` (335K CVEs)
- `weaknesses` (969 CWEs)
- `attack_techniques` (MITRE ATT&CK)
- `oscal_controls` (NIST 800-53)
- `regulatory_requirements` (CRA, FDA, IEC)
- `epss_history` (EPSS scores)
- `kev_entries` (CISA KEV)
- `exploit_modules` (Metasploit, ExploitDB)

**Access Pattern:** Customer edges point to reference collections for enrichment.

---

## 3. SBOM Upload Flow

### 3.1 End-to-End Flow

```
┌────────────────────────────────────────────────────────────────────┐
│  STEP 1: CLIENT GENERATES SBOM                                     │
└────────────────────────────────────────────────────────────────────┘

CI/CD Pipeline (GitHub Actions):
  - Build application
  - Generate SBOM with Syft/CycloneDX
  - Output: sbom.json (CycloneDX format)

┌────────────────────────────────────────────────────────────────────┐
│  STEP 2: CLIENT UPLOADS SBOM TO COMPLIRA                           │
└────────────────────────────────────────────────────────────────────┘

POST /v1/sbom/upload
Headers:
  X-API-Key: acme_corp_api_key_12345
  Content-Type: application/json

Body:
{
  "format": "cyclonedx",
  "payload": { /* CycloneDX SBOM JSON */ },
  "metadata": {
    "repository": "https://github.com/acme/web-app",
    "commit_sha": "abc123",
    "branch": "main",
    "build_id": "build-456"
  }
}

┌────────────────────────────────────────────────────────────────────┐
│  STEP 3: API AUTHENTICATES & PARSES                                │
└────────────────────────────────────────────────────────────────────┘

1. Authenticate API key → customer_id = "acme_corp"
2. Get customer database: complira_customer_acme_corp
3. Parse SBOM using CycloneDXParser
   - Extract metadata (tool, timestamp, serial number)
   - Extract components (347 packages)
   - Extract vulnerabilities (23 CVEs)
   - Extract dependencies (425 edges)

┌────────────────────────────────────────────────────────────────────┐
│  STEP 4: STORE IN CUSTOMER DATABASE                                │
└────────────────────────────────────────────────────────────────────┘

Transaction:
1. Insert sbom_document
2. Bulk insert customer_components (347 components)
3. Create sbom_contains_component edges (347 edges)
4. Create component_depends_on edges (425 edges)
5. Insert scan_findings (23 vulnerabilities)
6. Create finding_to_cve edges (23 edges pointing to reference DB)

┌────────────────────────────────────────────────────────────────────┐
│  STEP 5: ENRICH WITH REFERENCE DATA                                │
└────────────────────────────────────────────────────────────────────┘

For each CVE in findings:
  - Query reference DB: vulnerabilities/CVE_2024_1234
  - Traverse graph: CVE → CWE → CAPEC → ATT&CK → Controls
  - Get EPSS score, KEV status, exploit availability
  - Map to regulatory requirements (CRA, FDA, IEC)

┌────────────────────────────────────────────────────────────────────┐
│  STEP 6: RETURN RESPONSE                                           │
└────────────────────────────────────────────────────────────────────┘

Response:
{
  "sbom_id": "sbom_20260306_abc123",
  "status": "completed",
  "component_count": 347,
  "vulnerability_count": 23,
  "critical_count": 2,
  "high_count": 8,
  "medium_count": 13,
  "created_at": "2026-03-06T10:05:00Z",
  "enrichment_summary": {
    "cve_enriched": 23,
    "epss_available": 23,
    "kev_flagged": 2,
    "regulatory_mappings": 15
  }
}
```

### 3.2 Supported SBOM Formats

| Format | Version | Parser | Status |
|--------|---------|--------|--------|
| **CycloneDX** | 1.4, 1.5 | `CycloneDXParser` | ✅ Implemented |
| **SPDX** | 2.2, 2.3 | `SPDXParser` | 🚧 Planned (Phase 2) |

**CycloneDX Example:**
```json
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.5",
  "version": 1,
  "metadata": {
    "timestamp": "2026-03-06T10:00:00Z",
    "component": {
      "name": "acme-web-app",
      "version": "2.1.0"
    }
  },
  "components": [
    {
      "type": "library",
      "name": "express",
      "version": "4.17.1",
      "purl": "pkg:npm/express@4.17.1",
      "licenses": [{"id": "MIT"}],
      "vulnerabilities": [
        {
          "id": "CVE-2024-1234",
          "ratings": [{"severity": "high"}]
        }
      ]
    }
  ],
  "dependencies": [
    {
      "ref": "pkg:npm/myapp@1.0.0",
      "dependsOn": ["pkg:npm/express@4.17.1"]
    }
  ]
}
```

### 3.3 Deduplication Strategy

**Problem:** Customer uploads same SBOM multiple times (e.g., every CI/CD run).

**Solution:** Idempotent inserts using PURL as key.

```python
# component.py repository logic
def create_component(self, customer_id, purl, name, version, ...):
    # Use PURL as _key (safe format: replace special chars)
    safe_key = purl.replace("/", "_").replace(":", "_").replace("@", "_")
    component["_key"] = safe_key

    try:
        self.create(component)  # Insert new
    except DuplicateKeyError:
        return self.get_by_purl(customer_id, purl)  # Return existing
```

**Result:** Uploading same SBOM 100 times creates 1 component document.

---

## 4. Multi-Tenancy Strategy

### 4.1 Database-per-Customer Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         ARANGODB CLUSTER                             │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  complira_reference (SHARED - READ-ONLY)                   │    │
│  │  ────────────────────────────────────────────────────────  │    │
│  │  • 699,824 documents                                       │    │
│  │  • CVE, CWE, ATT&CK, NIST, regulatory data                 │    │
│  │  • Updated by backend agents (NVDAgent, KEVAgent, etc.)    │    │
│  │  • All customers read from this database                   │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  complira_customer_acme_corp (ISOLATED)                    │    │
│  │  ────────────────────────────────────────────────────────  │    │
│  │  • sbom_documents (ACME's SBOMs only)                      │    │
│  │  • customer_components (ACME's components only)            │    │
│  │  • scan_findings (ACME's vulnerabilities only)             │    │
│  │  Edges:                                                    │    │
│  │  • component_has_vulnerability → vulnerabilities (ref DB)  │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  complira_customer_startup_xyz (ISOLATED)                  │    │
│  │  ────────────────────────────────────────────────────────  │    │
│  │  • sbom_documents (Startup XYZ's SBOMs only)               │    │
│  │  • customer_components (different components)              │    │
│  │  • scan_findings                                           │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.2 Why Database-per-Customer?

| Benefit | Description |
|---------|-------------|
| **Strong Isolation** | Customer A cannot access Customer B's SBOMs (physical separation) |
| **SOC 2 Compliance** | Data isolation requirement satisfied by design |
| **GDPR Compliance** | Easy customer deletion (drop database on churn) |
| **Performance** | Small customer DBs (MBs) vs. monolithic DB (GBs); faster queries |
| **Blast Radius** | Security breach in one customer DB ≠ affects others |
| **Scalability** | Linear scaling (add customer = add small DB) |

### 4.3 Cross-Database Queries

**Use Case:** Enrich customer finding with reference CVE data.

```aql
// Query customer database
FOR finding IN scan_findings
  FILTER finding.customer_id == "acme_corp"
  FILTER finding.cve_id == "CVE-2024-1234"

  // Cross-database edge to reference DB
  FOR v, e IN 1..1 OUTBOUND finding finding_to_cve
    // Now in reference database
    LET epss = FIRST(
      FOR h IN 1..1 OUTBOUND v has_epss
      SORT h.date DESC
      LIMIT 1
      RETURN h.epss
    )

    LET cwes = (
      FOR c IN 1..1 OUTBOUND v has_weakness
      RETURN c.cwe_id
    )

    RETURN {
      customer_finding: finding,
      cve_details: v,
      epss: epss,
      cwes: cwes
    }
```

**Note:** ArangoDB supports cross-database edges natively.

### 4.4 Automatic Database Provisioning

Customer databases are created automatically on first API request:

```python
# api/core/database.py

def get_customer_db(customer_id: str) -> StandardDatabase:
    """
    Get customer database (auto-created if not exists).
    """
    database_name = f"complira_customer_{customer_id}"

    # Check cache first
    if customer_id in _customer_db_cache:
        return _customer_db_cache[customer_id]

    # Create database if doesn't exist
    if not sys_db.has_database(database_name):
        # Use Redis lock to prevent concurrent creation
        with redis_lock(f"db_creation_lock:{customer_id}"):
            sys_db.create_database(database_name)

            # Initialize schema
            _create_customer_collections(customer_db)

    # Cache and return
    _customer_db_cache[customer_id] = customer_db
    return customer_db


def _create_customer_collections(db: StandardDatabase):
    """
    Create customer-specific collections.
    """
    collections = {
        "sbom_documents": False,  # Document collection
        "customer_components": False,
        "scan_findings": False,
        "scan_sessions": False,
        "sbom_contains_component": True,  # Edge
        "component_has_vulnerability": True,
        "component_depends_on": True,
        "finding_to_cve": True,
    }

    for name, is_edge in collections.items():
        db.create_collection(name, edge=is_edge)
```

---

## 5. API Endpoints

### 5.1 SBOM Upload Endpoint

**Endpoint:** `POST /v1/sbom/upload`

**Authentication:** Required (X-API-Key header)

**Request:**
```json
{
  "format": "cyclonedx",  // or "spdx"
  "payload": { /* SBOM JSON */ },
  "metadata": {
    "repository": "https://github.com/acme/web-app",
    "commit_sha": "abc123",
    "branch": "main",
    "build_id": "build-456",
    "tags": ["production", "web-app"]
  }
}
```

**Response:**
```json
{
  "sbom_id": "sbom_20260306_abc123",
  "status": "completed",
  "component_count": 347,
  "vulnerability_count": 23,
  "severity_distribution": {
    "critical": 2,
    "high": 8,
    "medium": 13,
    "low": 0
  },
  "created_at": "2026-03-06T10:05:00Z",
  "enrichment_summary": {
    "cve_enriched": 23,
    "epss_available": 23,
    "kev_flagged": 2,
    "regulatory_mappings": 15
  },
  "links": {
    "sbom": "/v1/sbom/sbom_20260306_abc123",
    "components": "/v1/sbom/sbom_20260306_abc123/components",
    "vulnerabilities": "/v1/sbom/sbom_20260306_abc123/vulnerabilities",
    "vex": "/v1/sbom/sbom_20260306_abc123/vex"
  }
}
```

### 5.2 SBOM Retrieval Endpoints

#### List Customer SBOMs
```
GET /v1/sbom?limit=100&offset=0

Response:
{
  "total": 42,
  "limit": 100,
  "offset": 0,
  "sboms": [
    {
      "sbom_id": "sbom_20260306_abc123",
      "component_count": 347,
      "vulnerability_count": 23,
      "created_at": "2026-03-06T10:05:00Z"
    },
    ...
  ]
}
```

#### Get SBOM Details
```
GET /v1/sbom/{sbom_id}

Response:
{
  "sbom_id": "sbom_20260306_abc123",
  "customer_id": "acme_corp",
  "format": "CycloneDX",
  "spec_version": "1.5",
  "serial_number": "urn:uuid:3e671687-395b-41f5-a30f-a58921a69b79",
  "metadata": { /* SBOM metadata */ },
  "component_count": 347,
  "vulnerability_count": 23,
  "created_at": "2026-03-06T10:05:00Z"
}
```

#### List SBOM Components
```
GET /v1/sbom/{sbom_id}/components?limit=100&offset=0

Response:
{
  "total": 347,
  "limit": 100,
  "offset": 0,
  "components": [
    {
      "purl": "pkg:npm/express@4.17.1",
      "name": "express",
      "version": "4.17.1",
      "type": "library",
      "licenses": [{"id": "MIT"}],
      "vulnerability_count": 1
    },
    ...
  ]
}
```

#### List SBOM Vulnerabilities
```
GET /v1/sbom/{sbom_id}/vulnerabilities?severity=high,critical

Response:
{
  "total": 10,
  "vulnerabilities": [
    {
      "cve_id": "CVE-2024-1234",
      "severity": "HIGH",
      "cvss_score": 8.2,
      "epss_score": 0.85,
      "in_kev": true,
      "affected_components": [
        "pkg:npm/lodash@4.17.20"
      ],
      "description": "Prototype pollution vulnerability",
      "cwes": ["CWE-1321"],
      "attack_techniques": ["T1059"],
      "nist_controls": ["SI-2", "RA-5"],
      "regulatory_requirements": ["CRA Annex I Part II 1"]
    },
    ...
  ]
}
```

### 5.3 VEX Generation Endpoint

**Endpoint:** `POST /v1/sbom/{sbom_id}/vex`

**Description:** Generates VEX document for SBOM using Claude Sonnet 4.5.

**Request:**
```json
{
  "format": "cyclonedx",  // or "csaf"
  "include_not_affected": true,
  "severity_filter": ["critical", "high"]
}
```

**Response:**
```json
{
  "vex_document": {
    "bomFormat": "CycloneDX",
    "specVersion": "1.5",
    "version": 1,
    "metadata": {
      "timestamp": "2026-03-06T10:30:00Z",
      "component": {
        "name": "acme-web-app",
        "version": "2.1.0"
      }
    },
    "vulnerabilities": [
      {
        "id": "CVE-2024-1234",
        "analysis": {
          "state": "not_affected",
          "justification": "vulnerable_code_not_in_execute_path",
          "response": ["will_not_fix"],
          "detail": "The vulnerable lodash function is imported but never called in application code. Static analysis confirms no execution path reaches the vulnerable code."
        }
      },
      {
        "id": "CVE-2024-5678",
        "analysis": {
          "state": "affected",
          "justification": null,
          "response": ["update"],
          "detail": "Component is vulnerable and exploitable. User input flows to vulnerable function. Recommend upgrading to express@5.0.0."
        }
      }
    ]
  },
  "assessments_summary": {
    "total": 23,
    "affected": 8,
    "not_affected": 12,
    "under_investigation": 3
  },
  "model": "claude-sonnet-4.5",
  "generated_at": "2026-03-06T10:30:00Z"
}
```

---

## 6. VEX Generation

### 6.1 VEX Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         VEX GENERATION FLOW                          │
└─────────────────────────────────────────────────────────────────────┘

1. Client Request
   POST /v1/sbom/{sbom_id}/vex

2. Fetch SBOM + Components + Vulnerabilities
   - Query customer DB: sbom_documents, customer_components, scan_findings
   - Query reference DB: vulnerabilities, weaknesses, attack_techniques

3. Enrich Each Vulnerability
   FOR each CVE in SBOM:
     - Get CVE details from reference DB
     - Get EPSS score, KEV status, exploit availability
     - Get CWE → CAPEC → ATT&CK chain
     - Get NIST controls, regulatory mappings

4. LLM Analysis (Claude Sonnet 4.5)
   Input: Component + Vulnerability + Enrichment

   Prompt:
   "Analyze if this component is exploitable:
    - Component: pkg:npm/express@4.17.1
    - CVE: CVE-2024-1234 (Prototype pollution, CVSS 8.2)
    - CWE: CWE-1321 (Prototype pollution)
    - ATT&CK: T1059 (Command execution)

    Determine:
    1. Is vulnerable code reachable in typical deployment?
    2. Can attacker control vulnerable inputs?
    3. Are there mitigations?

    Provide VEX status: affected | not_affected | under_investigation"

   Output:
   {
     "state": "not_affected",
     "justification": "vulnerable_code_not_in_execute_path",
     "detail": "Analysis shows..."
   }

5. Generate VEX Document
   - Format: CycloneDX VEX or CSAF VEX
   - Include all vulnerability assessments
   - Add metadata (timestamp, tool, model)

6. Store Metadata + Return VEX
   - Store VEX metadata in customer DB (vex_documents collection)
   - Store LLM provenance (llm_enrichments collection)
   - Return VEX JSON to client
```

### 6.2 VEX Justifications (CycloneDX Standard)

| Justification | Description | Example |
|---------------|-------------|---------|
| `vulnerable_code_not_present` | Vulnerable code doesn't exist in this component version | False positive from scanner |
| `vulnerable_code_not_in_execute_path` | Code exists but unreachable | Imported library function never called |
| `vulnerable_code_cannot_be_controlled_by_adversary` | Code runs but attacker can't control inputs | Internal function with no user input |
| `inline_mitigations_already_exist` | Vulnerability mitigated by other controls | WAF blocks exploit, input sanitized |

### 6.3 VEX Cost Estimation

**Model:** Claude Sonnet 4.5
- Input: ~1,000 tokens per CVE (component + CVE + enrichment)
- Output: ~500 tokens per CVE (analysis + justification)

**Pricing:**
- $3/M input tokens
- $15/M output tokens

**Cost per SBOM:**
- 347 components, 23 CVEs
- Input: 23 CVEs × 1,000 tokens = 23K tokens = $0.07
- Output: 23 CVEs × 500 tokens = 11.5K tokens = $0.17
- **Total: $0.24 per SBOM VEX generation**

**For 1,000 SBOMs/month:** $240/month in LLM costs.

---

## 7. Implementation Roadmap

### Phase 1: SBOM Upload (Week 1-2)

**Goal:** Support CycloneDX SBOM upload and storage.

**Tasks:**
1. ✅ Create customer database schema
   - `sbom_documents`, `customer_components` collections
   - `sbom_contains_component`, `component_depends_on` edges

2. ✅ Implement CycloneDX parser (already done)
   - `src/api/parsers/cyclonedx.py`

3. 🚧 Create SBOM upload endpoint
   - `POST /v1/sbom/upload`
   - Route to customer database
   - Parse SBOM, extract components
   - Create edges to reference DB

4. 🚧 Create SBOM retrieval endpoints
   - `GET /v1/sbom` (list)
   - `GET /v1/sbom/{id}` (details)
   - `GET /v1/sbom/{id}/components`
   - `GET /v1/sbom/{id}/vulnerabilities`

**Acceptance Criteria:**
- Client can upload CycloneDX SBOM via API
- Components stored in customer database
- Vulnerabilities enriched with reference data
- SBOM retrieval APIs return correct data

### Phase 2: VEX Generation (Week 3-4)

**Goal:** Generate VEX documents using LLM.

**Tasks:**
1. ✅ Implement VEX Synthesizer Agent (already done)
   - `src/complira_graph/llm_agents/vex_synthesizer.py`

2. 🚧 Create VEX generation endpoint
   - `POST /v1/sbom/{id}/vex`
   - Call VEX Synthesizer for each CVE
   - Format output (CycloneDX VEX)

3. 🚧 Implement VEX caching
   - Store VEX metadata in `vex_documents` collection
   - Cache VEX for 24 hours (avoid redundant LLM calls)

4. 🚧 Add VEX export formats
   - CycloneDX VEX (JSON)
   - CSAF VEX (JSON)
   - PDF report (future)

**Acceptance Criteria:**
- VEX endpoint generates vulnerability assessments
- LLM provides justifications for not_affected status
- VEX documents comply with CycloneDX 1.5 spec
- VEX metadata stored for audit trail

### Phase 3: SPDX Support (Week 5-6)

**Goal:** Support SPDX SBOM format.

**Tasks:**
1. 🚧 Implement SPDX parser
   - `src/api/parsers/spdx.py`
   - Support SPDX 2.2, 2.3

2. 🚧 Update SBOM upload endpoint
   - Auto-detect format (CycloneDX vs. SPDX)
   - Route to appropriate parser

3. 🚧 Test SPDX → VEX conversion
   - SPDX lacks vulnerability field (unlike CycloneDX)
   - Must cross-reference with NVD using CPE/PURL

**Acceptance Criteria:**
- Client can upload SPDX SBOM
- SPDX components normalized to PURL
- VEX generation works for SPDX SBOMs

### Phase 4: Advanced Features (Week 7-8)

**Goal:** Dependency graphs, vulnerability propagation, regulatory reports.

**Tasks:**
1. 🚧 Implement dependency graph visualization
   - `GET /v1/sbom/{id}/graph`
   - Return D3.js-compatible graph JSON

2. 🚧 Implement vulnerability propagation
   - If library A depends on library B with CVE-X
   - Flag library A as "transitive vulnerability"

3. 🚧 Implement regulatory compliance reports
   - `GET /v1/sbom/{id}/compliance?framework=cra`
   - Map SBOM vulnerabilities to CRA requirements
   - Generate compliance checklist

**Acceptance Criteria:**
- Dependency graph shows component relationships
- Transitive vulnerabilities identified
- Compliance report maps to regulatory requirements

---

## 8. Security & Compliance

### 8.1 Data Privacy

**Principle:** Customer SBOMs are proprietary and must be isolated.

**Implementation:**
- ✅ Database-per-customer (physical isolation)
- ✅ API key authentication (customer scoping)
- ✅ No cross-customer queries (enforced by DB routing)
- ✅ Customer data encrypted at rest (ArangoDB encryption)
- ✅ Customer data encrypted in transit (TLS 1.3)

### 8.2 Compliance Certifications

| Certification | Status | Requirements |
|---------------|--------|--------------|
| **SOC 2 Type II** | 🎯 Target | Data isolation ✅, Audit logs ✅, Access control ✅ |
| **GDPR** | 🎯 Target | Right to erasure (drop customer DB) ✅, Data portability ✅ |
| **HIPAA** | 🚧 Future | PHI isolation (customer DB) ✅, BAA required |
| **ISO 27001** | 🚧 Future | Security controls, risk management |

### 8.3 Audit Trail

All SBOM operations are logged:

```json
{
  "timestamp": "2026-03-06T10:05:00Z",
  "customer_id": "acme_corp",
  "action": "sbom.upload",
  "sbom_id": "sbom_20260306_abc123",
  "component_count": 347,
  "vulnerability_count": 23,
  "user_agent": "GitHub Actions",
  "ip_address": "192.168.1.1"
}
```

Stored in:
- Customer database: `audit_logs` collection
- Prometheus metrics: `sbom_upload_total{customer="acme_corp"}`

### 8.4 Rate Limiting

**Per-customer rate limits:**

| Tier | SBOM Uploads/Hour | VEX Generations/Hour | API Requests/Minute |
|------|-------------------|----------------------|---------------------|
| Free | 10 | 5 | 60 |
| Professional | 100 | 50 | 600 |
| Enterprise | Unlimited | Unlimited | Unlimited |

**Implementation:**
- Redis-based rate limiter
- Per-customer quotas stored in `customer_profiles.rate_limit`
- 429 Too Many Requests response when exceeded

---

## Summary

### Key Takeaways

1. **SBOMs are client-specific data** stored in isolated customer databases
2. **Upload via API** (POST /v1/sbom/upload) for CI/CD integration
3. **CycloneDX and SPDX** formats supported
4. **VEX generation** uses Claude Sonnet 4.5 for impact assessment
5. **Multi-tenancy** via database-per-customer architecture
6. **Reference database** provides shared vulnerability intelligence
7. **Cross-database edges** link customer components to reference CVEs

### Implementation Status

| Component | Status | Location |
|-----------|--------|----------|
| Customer database schema | ✅ Done | `src/api/core/database.py` |
| CycloneDX parser | ✅ Done | `src/api/parsers/cyclonedx.py` |
| Component repository | ✅ Done | `src/api/repositories/component.py` |
| VEX Synthesizer Agent | ✅ Done | `src/complira_graph/llm_agents/vex_synthesizer.py` |
| SBOM upload endpoint | 🚧 TODO | Phase 1 |
| SBOM retrieval endpoints | 🚧 TODO | Phase 1 |
| VEX generation endpoint | 🚧 TODO | Phase 2 |
| SPDX parser | 🚧 TODO | Phase 3 |
| Dependency graph | 🚧 TODO | Phase 4 |

### Next Steps

1. **Implement SBOM upload endpoint** (POST /v1/sbom/upload)
2. **Create SBOM service layer** (business logic for SBOM ingestion)
3. **Add SBOM retrieval endpoints** (GET /v1/sbom/*)
4. **Integrate VEX Synthesizer** (POST /v1/sbom/{id}/vex)
5. **Test end-to-end flow** (CI/CD → SBOM upload → VEX generation)

---

**Document Version:** 1.0
**Last Updated:** 2026-03-06
**Author:** Complira Engineering Team
