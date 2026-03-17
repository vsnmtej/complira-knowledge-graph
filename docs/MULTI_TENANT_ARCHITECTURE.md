# Multi-Tenant Architecture: Centralized vs Customer Data

## Overview

Complira uses a **database-per-customer** architecture with one **shared reference database** and multiple **isolated customer databases**.

```
┌─────────────────────────────────────────────────────────────┐
│                    ArangoDB Cluster                          │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  complira_reference (SHARED - READ-ONLY)           │    │
│  │  ─────────────────────────────────────────────     │    │
│  │  • 699,824 documents                               │    │
│  │  • CVE data (NVD, GHSA, OSV)                       │    │
│  │  • CWE hierarchy (969 entries)                     │    │
│  │  • MITRE ATT&CK (835 techniques)                   │    │
│  │  • NIST 800-53 controls (1,196 controls)           │    │
│  │  • Regulatory requirements (52 requirements)       │    │
│  │  • EPSS scores (953K historical)                   │    │
│  │  • KEV catalog (1,529 entries)                     │    │
│  │  • Exploit intelligence (46K exploits)             │    │
│  │  • D3FEND defenses (493 techniques)                │    │
│  │  • Threat groups (187 groups)                      │    │
│  │  • Package health data (7,593 packages)            │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  complira_customer_acme_corp (ISOLATED)            │    │
│  │  ───────────────────────────────────────────       │    │
│  │  • Scan sessions (customer's scans only)           │    │
│  │  • Scan findings (customer's vulnerabilities)      │    │
│  │  • Customer components (customer's SBOM)           │    │
│  │  • Edges: finding → CVE (references shared data)   │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  complira_customer_startup_xyz (ISOLATED)          │    │
│  │  ───────────────────────────────────────────       │    │
│  │  • Scan sessions (different customer's scans)      │    │
│  │  • Scan findings                                   │    │
│  │  • Customer components                             │    │
│  │  • Edges: finding → CVE                            │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  complira_customer_enterprise_co (ISOLATED)        │    │
│  │  ───────────────────────────────────────────       │    │
│  │  • Scan sessions                                   │    │
│  │  • Scan findings                                   │    │
│  │  • Customer components                             │    │
│  │  • Edges: finding → CVE                            │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Centralized Data (Shared Reference Database)

**Database:** `complira_reference`

**Purpose:** Public cybersecurity intelligence shared across ALL customers (read-only)

**Collections:**

| Collection | Count | Description | Update Frequency |
|------------|-------|-------------|-----------------|
| **vulnerabilities** | 3,238 | CVE data from NVD, GHSA, OSV | Daily |
| **weaknesses** | 969 | CWE hierarchy | Weekly |
| **attack_techniques** | 835 | MITRE ATT&CK techniques | Weekly |
| **oscal_controls** | 1,196 | NIST 800-53 controls | Monthly |
| **regulatory_requirements** | 52 | FDA 524B, EU CRA, IEC 62304 | As needed |
| **kev_entries** | 1,529 | CISA Known Exploited Vulnerabilities | Daily |
| **epss_history** | 635,744 | EPSS scores (historical) | Daily |
| **exploit_modules** | 46,491 | Metasploit, Exploit-DB | Weekly |
| **d3fend_techniques** | 493 | D3FEND defensive countermeasures | Monthly |
| **threat_groups** | 187 | APT groups and campaigns | Monthly |
| **attack_patterns** | 615 | CAPEC attack patterns | Monthly |
| **atlas_techniques** | 155 | MITRE ATLAS (ML threats) | Monthly |
| **package_health** | 7,593 | Package metadata, health scores | Weekly |
| **licenses** | 727 | SPDX license data | Quarterly |

**Why Centralized?**
- **Efficiency:** Single copy instead of duplicating 699K docs per customer
- **Consistency:** All customers see same CVE data, avoiding version conflicts
- **Performance:** Central updates (1 update vs. updating 1000 customer DBs)
- **Cost:** ~2GB reference data × 1 = 2GB vs. ~2GB × 1000 customers = 2TB

**Access Pattern:**
- **Read-only** for all customers
- Updated by backend agents (NVDAgent, KEVAgent, EPSSAgent, etc.)
- Never contains customer-specific data

---

## Customer-Specific Data (Isolated Databases)

**Database Pattern:** `complira_customer_<customer_id>`

**Examples:**
- `complira_customer_acme_corp`
- `complira_customer_startup_xyz`
- `complira_customer_enterprise_co`

**Purpose:** Private scan data, findings, and SBOMs unique to each customer

**Collections:**

| Collection | Description | Example Data |
|------------|-------------|--------------|
| **scan_sessions** | Scan metadata | Tool: Semgrep, Branch: main, Timestamp: 2026-03-05 |
| **scan_findings** | Individual vulnerabilities found | CVE-2024-1234 in app.py:42, Severity: HIGH |
| **customer_components** | Software inventory (SBOM) | lodash@4.17.20, express@4.18.0 |
| **finding_to_cve** (edge) | Links finding → CVE in reference DB | finding_001 → vulnerabilities/CVE-2024-1234 |
| **component_to_finding** (edge) | Links component → finding | lodash@4.17.20 → finding_042 |

**Why Isolated?**
- **Security:** Customer A cannot see Customer B's scan results
- **Compliance:** SOC 2, GDPR, HIPAA require data isolation
- **Performance:** Each customer's queries only search their own data
- **Deletion:** Can delete customer database without affecting others

**Access Pattern:**
- **Read/Write** by customer only (enforced by API key)
- Auto-created on first API request
- Can be deleted when customer churns

---

## How It Works: Query Example

### Scenario: Customer scans their app and finds CVE-2024-1234

**Step 1: Scan Ingestion**
```
POST /v1/scan/ingest
X-API-Key: customer_acme_api_key

→ API authenticates → customer_id = "acme_corp"
→ Write to: complira_customer_acme_corp.scan_sessions
→ Write to: complira_customer_acme_corp.scan_findings
```

**Data Written (Customer DB):**
```json
// complira_customer_acme_corp.scan_findings
{
  "_key": "finding_001",
  "customer_id": "acme_corp",
  "scan_session_id": "scan_abc123",
  "cve_id": "CVE-2024-1234",
  "severity": "high",
  "location": {"file": "app.py", "line": 42},
  "created_at": "2026-03-05T12:00:00Z"
}
```

**Step 2: Enrichment Query**
```
POST /v1/enrich
{ "cve_ids": ["CVE-2024-1234"] }

→ Query customer DB: complira_customer_acme_corp.scan_findings
   (verify customer owns this CVE)
→ Query reference DB: complira_reference.vulnerabilities
   (get full CVE details)
→ Graph traversal: CVE → CWE → CAPEC → ATT&CK → Controls
```

**Query Path:**
```
Customer DB                    Reference DB
────────────                  ─────────────
scan_findings                 vulnerabilities
    ↓                              ↓
finding_001 ────────→ CVE-2024-1234 ────→ weaknesses/CWE-89
                                              ↓
                                         attack_patterns/CAPEC-66
                                              ↓
                                         attack_techniques/T1190
                                              ↓
                                         oscal_controls/SI-2
                                              ↓
                                         regulatory_requirements/FDA_524B_V_C_1
```

**Response (Enriched Data):**
```json
{
  "cve_id": "CVE-2024-1234",
  "cvss_score": 9.8,           // from reference DB
  "epss_score": 0.85,          // from reference DB
  "in_kev": true,              // from reference DB
  "cwe": ["CWE-89"],           // from reference DB
  "attack_techniques": ["T1190"],  // from reference DB
  "nist_controls": ["SI-2", "RA-5"],  // from reference DB
  "fda_requirements": ["V.C.1"],  // from reference DB

  // Customer-specific context
  "customer_findings": 3,      // from customer DB
  "affected_components": ["app.py", "api.py"],  // from customer DB
  "first_seen": "2026-01-15"   // from customer DB
}
```

---

## Data Flow Diagram

```
┌──────────────┐
│   Customer   │
│   (API Key)  │
└──────┬───────┘
       │
       │ POST /v1/scan/ingest
       ↓
┌──────────────────┐
│  FastAPI Server  │
│  ──────────────  │
│  1. Authenticate │
│  2. Get customer_id
│  3. Route to DBs │
└────┬─────────┬───┘
     │         │
     │         └─────────────────────────────┐
     │                                       │
     │ WRITE                                 │ READ
     ↓                                       ↓
┌─────────────────────┐            ┌──────────────────────┐
│  Customer Database  │            │  Reference Database  │
│  (Isolated)         │            │  (Shared)            │
│  ─────────────────  │            │  ──────────────────  │
│  • scan_sessions    │            │  • vulnerabilities   │
│  • scan_findings    │            │  • weaknesses        │
│  • components       │            │  • attack_techniques │
│                     │            │  • oscal_controls    │
│  Edges:             │            │  • regulatory_reqs   │
│  • finding → CVE ───┼───────────→│  • epss_history      │
│  • component → CVE ─┼───────────→│  • kev_entries       │
└─────────────────────┘            └──────────────────────┘
```

---

## Security Benefits

### 1. **Data Isolation**
- Customer A's scans in `complira_customer_a`
- Customer B's scans in `complira_customer_b`
- **Physical separation** prevents cross-customer data leaks

### 2. **Access Control**
```python
# API enforces customer scoping automatically
async def get_current_customer(api_key: str):
    customer = authenticate(api_key)

    # All queries auto-scoped to customer's database
    db = get_customer_db(customer.id)

    # Customer A can NEVER access customer B's data
    # because they're in different databases
```

### 3. **Compliance**
- **SOC 2 Type II:** Data isolation requirement satisfied
- **GDPR:** Easy customer data deletion (drop database)
- **HIPAA:** PHI in separate database per covered entity

### 4. **Blast Radius Containment**
- Security breach in Customer A's database ≠ affects Customer B
- Reference database breach = public data only (no customer secrets)

---

## Performance Benefits

### 1. **Query Isolation**
- Customer A's heavy query load doesn't slow Customer B
- Each customer DB is small (MBs) vs. reference DB (GBs)

### 2. **Indexing**
```sql
-- Customer database indexes (fast - small dataset)
CREATE INDEX ON scan_findings (customer_id, scan_session_id)
CREATE INDEX ON scan_findings (customer_id, cve_id)

-- Reference database indexes (shared by all)
CREATE INDEX ON vulnerabilities (cve_id)
CREATE INDEX ON weaknesses (cwe_id)
```

### 3. **Caching Strategy**
- **Reference data:** 6-hour TTL (rarely changes, shared across customers)
- **Customer data:** 1-hour TTL (changes frequently, customer-specific)

---

## Cost Optimization

### Without Multi-Tenancy (Single DB)
```
Single database with 1000 customers:
- 699K reference docs × 1 = 699K docs
- 10K customer scans × 1000 customers = 10M docs
- Total: 10.7M docs in one database
- Cost: High (large database, complex queries)
- Risk: High (all eggs in one basket)
```

### With Multi-Tenancy (Database-per-Customer)
```
Reference database (shared):
- 699K reference docs × 1 = 699K docs
- Cost: Medium (shared infrastructure)

Customer databases (1000 customers):
- 10K customer scans × 1 customer = 10K docs per DB
- 10K docs × 1000 customers = 10M docs total
- Cost: Lower (distributed, smaller queries)
- Risk: Low (isolated failure domains)
```

**Savings:**
- **Storage:** ~30% (no duplication of reference data)
- **Query speed:** ~10x faster (smaller datasets)
- **Scalability:** Linear (add customer = add small DB)

---

## Migration Strategy

### Local → Cloud Migration (UC-005)

**Before Migration (Local):**
```
localhost:8529/complira_graph (everything mixed together)
├── vulnerabilities (3,238)
├── scan_sessions (your local scans)
├── scan_findings (your local findings)
└── ... (all 699K docs)
```

**After Migration (Cloud):**
```
cloud.arangodb.com/complira_reference (centralized)
├── vulnerabilities (3,238)
├── weaknesses (969)
├── attack_techniques (835)
└── ... (699K reference docs only)

cloud.arangodb.com/complira_customer_you (isolated)
├── scan_sessions (your scans only)
├── scan_findings (your findings only)
└── customer_components (your SBOM only)
```

**Migration Script:**
```bash
# 1. Export local database
python scripts/migrate_to_cloud.py --export

# 2. Import reference data to cloud reference DB
python scripts/migrate_to_cloud.py --import

# 3. Your personal scans go to your customer DB
# (requires API key provisioning)
```

---

## Summary Table

| Aspect | Reference Database | Customer Database |
|--------|-------------------|-------------------|
| **Name** | `complira_reference` | `complira_customer_<id>` |
| **Shared?** | ✅ Shared across all customers | ❌ Isolated per customer |
| **Size** | ~2GB (699K docs) | ~10MB (10K docs typical) |
| **Data Type** | Public CVE/threat intelligence | Private scans, findings, SBOM |
| **Write Access** | Backend agents only | Customer via API only |
| **Read Access** | All customers (read-only) | Customer only (via API key) |
| **Updates** | Daily/Weekly (agents) | Real-time (API requests) |
| **Compliance** | N/A (public data) | SOC 2, GDPR, HIPAA compliant |
| **Cost** | Fixed (1 database) | Linear (N customers = N DBs) |
| **Deletion** | Never | On customer churn |

---

## Key Takeaway

**Reference Database = Shared Knowledge**
- CVEs, CWEs, ATT&CK, NIST controls
- Updated by backend agents
- Read by all customers

**Customer Database = Private Results**
- Your scans, your findings, your SBOM
- Updated by your API requests
- Read only by you

**Together = Powerful Compliance Platform**
- Reference data provides context
- Customer data provides specifics
- Graph edges connect the two
