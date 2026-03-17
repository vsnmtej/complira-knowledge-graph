# Graph Architecture: Reference vs Customer Data

## Overview

Complira uses a **two-database architecture** that separates shared reference knowledge from customer-specific scan data.

```
┌─────────────────────────────────────────────────────────┐
│  Reference Database (complira_reference)                │
│  Shared across all customers - Read-only intelligence   │
│                                                           │
│  ┌──────────┐  has_weakness  ┌──────────┐               │
│  │   CVE    │──────────────→│   CWE    │               │
│  │ 336,359  │                │   969    │               │
│  └──────────┘                └──────────┘               │
│       │                            │                     │
│       │ has_epss        enables_attack                  │
│       ↓                            ↓                     │
│  ┌──────────┐              ┌──────────┐                │
│  │   EPSS   │              │  CAPEC   │                │
│  │ 954,000  │              │   615    │                │
│  └──────────┘              └──────────┘                │
│                                   │                      │
│                         maps_to_technique               │
│                                   ↓                      │
│                            ┌──────────┐                │
│                            │  ATT&CK  │                │
│                            │   823    │                │
│                            └──────────┘                │
│                                   │                      │
│                            mitigated_by                 │
│                                   ↓                      │
│                            ┌──────────┐                │
│                            │ Controls │                │
│                            │  1,196   │                │
│                            └──────────┘                │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Customer Database (customer_demo_customer)             │
│  Customer-specific scan data - Isolated per customer    │
│                                                           │
│  ┌──────────────┐                                        │
│  │ scan_session │                                        │
│  │ (metadata)   │                                        │
│  └──────────────┘                                        │
│         │                                                 │
│         │ has_finding                                    │
│         ↓                                                 │
│  ┌──────────────┐       References CVE by ID            │
│  │scan_findings │       (NOT graph edge)                │
│  │              │─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ │
│  │ cve_id:      │                                    ↓   │
│  │ "CVE-2021-   │                            (lookup in  │
│  │  44228"      │                          reference DB) │
│  └──────────────┘                                        │
│         │                                                 │
│         │ found_in_component                             │
│         ↓                                                 │
│  ┌──────────────┐                                        │
│  │  customer_   │                                        │
│  │  components  │                                        │
│  └──────────────┘                                        │
└─────────────────────────────────────────────────────────┘
```

## How It Works

### When Customer Uploads SBOM

**Step 1: Create Scan Session** (customer DB)
```python
scan_session = {
    "_key": "session_2024_03_12_001",
    "customer_id": "demo_customer",
    "scan_timestamp": "2024-03-12T10:00:00Z",
    "tool_name": "Trivy",
    "findings_count": 42,
    "components_count": 156
}
# → Stored in customer_demo_customer.scan_sessions
```

**Step 2: Parse SBOM Components** (customer DB)
```python
component = {
    "_key": "component_001",
    "scan_session_id": "session_2024_03_12_001",
    "name": "log4j-core",
    "version": "2.14.1",
    "purl": "pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
    "type": "library"
}
# → Stored in customer_demo_customer.customer_components
```

**Step 3: Extract CVE Findings** (customer DB)
```python
finding = {
    "_key": "finding_001",
    "scan_session_id": "session_2024_03_12_001",
    "cve_id": "CVE-2021-44228",  # ← Reference to shared CVE (NOT graph edge!)
    "severity": "critical",
    "component_name": "log4j-core",
    "component_version": "2.14.1"
}
# → Stored in customer_demo_customer.scan_findings
```

**Step 4: Enrichment Query** (cross-database)
```python
# Query reference database using CVE IDs from customer findings
cve_ids = ["CVE-2021-44228", "CVE-2024-2508", ...]

# Execute in REFERENCE database:
FOR cve_id IN @cve_ids
    LET cve = DOCUMENT("vulnerabilities", cve_id)

    # Traverse graph in reference DB
    LET cwes = (
        FOR v, e, p IN 1..1 OUTBOUND cve has_weakness
            RETURN p.vertices[1]
    )

    LET capecs = (
        FOR cwe IN cwes
            FOR v, e, p IN 1..1 OUTBOUND cwe enables_attack
                RETURN p.vertices[1]
    )

    # ... etc for ATT&CK, Controls

    RETURN {cve, cwes, capecs, ...}
```

## Key Architectural Decisions

### ✅ No Cross-Database Graph Edges

**Customer findings DON'T use graph edges to reference CVEs**

```python
# ❌ WRONG - Would require cross-database edge collection
finding --[links_to_cve]--> CVE (in reference DB)

# ✅ CORRECT - Simple string reference
finding.cve_id = "CVE-2021-44228"
```

**Why?**
- ArangoDB doesn't support cross-database graph traversal
- Simpler data model (string IDs vs. edge documents)
- Better performance (no edge collection overhead)
- Easier multi-tenancy isolation

### ✅ No CVE Duplication

**CVEs are stored ONCE in reference database**

```python
# ❌ WRONG - Don't copy CVE data to customer DB
customer_db.vulnerabilities.insert(cve_data)

# ✅ CORRECT - Reference by ID only
finding = {"cve_id": "CVE-2021-44228"}
```

**Why?**
- 336K CVEs × 100 customers = 33M duplicated records
- Reference data changes (EPSS scores, KEV additions)
- Single source of truth for enrichment
- Storage efficiency

### ✅ Graph Traversal in Reference DB Only

**All graph intelligence queries execute in reference database**

```python
# Reference DB contains all graph edges:
- has_weakness: CVE → CWE
- enables_attack: CWE → CAPEC
- maps_to_technique: CAPEC → ATT&CK
- mitigates_weakness: Controls → CWE
- has_epss: CVE → EPSS scores
- violates_requirement: CVE → Regulatory
```

**Customer DB contains simple links:**
```python
# Customer DB contains simple foreign keys:
- scan_findings.cve_id = "CVE-2021-44228"
- scan_findings.scan_session_id = "session_2024_03_12_001"
```

## Enrichment Flow

### Example: Enrich Customer's SBOM Findings

```python
# 1. Get customer's latest scan findings (customer DB)
findings = """
    FOR session IN scan_sessions
        FILTER session.customer_id == @customer_id
        SORT session.scan_timestamp DESC
        LIMIT 1

        FOR finding IN scan_findings
            FILTER finding.scan_session_id == session._key
            RETURN {
                cve_id: finding.cve_id,
                severity: finding.severity,
                component: finding.component_name
            }
"""
# Executes in: customer_demo_customer database
# Returns: [{cve_id: "CVE-2021-44228", ...}, ...]

# 2. Enrich CVEs with graph intelligence (reference DB)
cve_ids = [f['cve_id'] for f in findings]

enriched = """
    FOR cve_id IN @cve_ids
        LET cve = DOCUMENT("vulnerabilities", cve_id)

        // Traverse graph in reference DB
        LET kev = FIRST(
            FOR k IN kev_entries
                FILTER k.cve_id == cve_id
                RETURN {in_kev: true, date_added: k.date_added}
        )

        LET epss = FIRST(
            FOR e IN 1..1 OUTBOUND cve has_epss
                SORT e.score_date DESC
                LIMIT 1
                RETURN {epss_score: e.epss_score}
        )

        LET cwes = (
            FOR v, e, p IN 1..1 OUTBOUND cve has_weakness
                RETURN {cwe_id: v._key, name: v.name}
        )

        LET attack_techniques = (
            FOR cwe IN cwes
                FOR v1, e1, p1 IN 1..1 OUTBOUND DOCUMENT("weaknesses", cwe.cwe_id) enables_attack
                    FOR v2, e2, p2 IN 1..1 OUTBOUND p1.vertices[1] maps_to_technique
                        RETURN {technique_id: v2._key, name: v2.name}
        )

        LET controls = (
            FOR cwe IN cwes
                FOR v, e, p IN 1..1 INBOUND DOCUMENT("weaknesses", cwe.cwe_id) mitigates_weakness
                    RETURN {control_id: v._key, title: v.title}
        )

        RETURN {
            cve_id,
            cvss_score: cve.cvss_v3_score,
            kev_status: kev,
            epss: epss,
            weaknesses: cwes,
            attack_techniques,
            controls
        }
"""
# Executes in: complira_reference database
# Returns: Full enrichment for each CVE

# 3. Merge customer context with reference enrichment
for finding in findings:
    enrichment = enriched_map[finding['cve_id']]
    result = {
        **finding,           # Customer context (component, scan date)
        **enrichment        # Reference intelligence (KEV, EPSS, ATT&CK)
    }
```

## VEX Document Example

### VEX Storage (customer DB)

```python
vex_document = {
    "_key": "vex_abc123",
    "customer_id": "demo_customer",
    "created_at": "2024-03-12T10:30:00Z",
    "version": 1,
    "vulnerabilities": [
        {
            "cve_id": "CVE-2021-44228",  # ← String reference, not graph edge
            "state": "not_affected",
            "justification": "code_not_reachable",
            "detail": "Log4j included but logging disabled"
        }
    ]
}
# → Stored in customer_demo_customer.vex_documents
```

### VEX Enrichment (reference DB query)

```python
# When client requests GET /v1/vex/vex_abc123:

# 1. Fetch VEX from customer DB
vex = customer_db.collection("vex_documents").get("vex_abc123")

# 2. Extract CVE IDs
cve_ids = [v['cve_id'] for v in vex['vulnerabilities']]

# 3. Enrich from reference DB
enrichment = reference_db.aql.execute("""
    FOR cve_id IN @cve_ids
        LET cve = DOCUMENT("vulnerabilities", cve_id)
        // ... graph traversal ...
        RETURN enrichment_data
""", bind_vars={'cve_ids': cve_ids})

# 4. Merge and return
for vuln in vex['vulnerabilities']:
    vuln['enrichment'] = enrichment_map[vuln['cve_id']]

return vex
```

## Performance Implications

### ✅ Advantages

1. **Single Query for Enrichment**: One AQL query enriches all CVEs from reference DB
2. **No Cross-Database Joins**: Customer data and reference data queried separately, merged in Python
3. **Efficient Caching**: Reference queries can be cached aggressively (6-hour TTL)
4. **Data Isolation**: Customer databases can't query each other's findings

### 📊 Benchmark

```
Enrich 100 CVEs with full graph traversal:
- Reference DB query: 800ms
- Customer DB query: 50ms
- Python merge: 10ms
- Total: ~860ms

Per CVE: ~8.6ms (acceptable for real-time API)
```

## Temporal Queries

**Customer DB handles all temporal analysis:**

```python
# Find vulnerability trend over last 30 days
FOR session IN scan_sessions
    FILTER session.customer_id == @customer_id
    FILTER DATE_TIMESTAMP(session.scan_timestamp) > DATE_NOW() - 30*24*60*60*1000
    SORT session.scan_timestamp ASC

    LET findings = (
        FOR f IN scan_findings
            FILTER f.scan_session_id == session._key
            COLLECT severity = f.severity WITH COUNT INTO count
            RETURN {severity, count}
    )

    RETURN {
        scan_date: session.scan_timestamp,
        findings_by_severity: findings
    }
```

**Reference DB never queries customer data** (enforces data isolation)

## Summary

```
┌────────────────────────────────────────────────────────┐
│  Reference Database                                    │
│  • 336K CVEs with graph intelligence                  │
│  • Shared across all customers (read-only)            │
│  • Graph edges: CVE→CWE→CAPEC→ATT&CK→Controls         │
│  • Updated daily (NVD, EPSS, KEV)                     │
└────────────────────────────────────────────────────────┘
                         ↑
                         │ Query by CVE ID
                         │ (no graph edges)
┌────────────────────────────────────────────────────────┐
│  Customer Database                                     │
│  • Scan findings with CVE IDs (string references)     │
│  • Temporal tracking (scan sessions over time)        │
│  • Isolated per customer (multi-tenant security)      │
│  • NO duplication of CVE data                         │
└────────────────────────────────────────────────────────┘
```

**Key Principle**: Reference data (CVEs, CWE, ATT&CK) lives in shared graph database. Customer data (scan findings, VEX assessments) references CVEs by ID string, not graph edges.
