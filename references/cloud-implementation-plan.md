# Complira Knowledge Graph — Implementation Plan

**Version:** 1.0
**Date:** March 2, 2026
**Scope:** 10 killer features, schema evolution, cloud/client architecture redesign

---

## Executive Summary

This plan transforms the Complira Knowledge Graph from a reference data store (335K docs, 1.97M edges) into a full security intelligence platform with cloud-hosted graph services and a thin CI/CD client. Implementation is organized into 5 phases over ~16 weeks, with each phase delivering usable features.

---

## Database Impact Analysis

**IMPORTANT: Your existing data will NOT be lost, but will be reorganized:**

### Current State
- Local ArangoDB database: `complira_graph`
- 335,398 documents, 1,971,746 edges
- Mix of reference data (CVEs, NIST, ATT&CK) and minimal customer data

### Target State (Cloud Architecture)
The plan calls for **database separation**:

1. **Reference Database** (`complira_reference`) - **Your existing data goes here**
   - All 335K+ documents stay intact
   - Vulnerabilities, attack_techniques, weaknesses, NIST controls, etc.
   - Read-only access for customers via API
   - Updated by background workers only

2. **Customer Databases** (`complira_customer_<id>`) - **New per-tenant databases**
   - Components from customer SBOMs
   - Scan sessions and findings
   - Customer-specific enrichments
   - Links to reference database via cross-database AQL queries

### Migration Strategy
```
Phase 0 (Weeks 1-2):
- Deploy cloud ArangoDB cluster
- Create complira_reference database
- Export existing local data
- Import into complira_reference (preserving all documents and edges)
- Verify: complira_reference.doc_count == local.doc_count
- Keep local database as backup during transition
```

### What Happens to Your Data
✅ **SAFE:** All reference data (CVEs, NIST, ATT&CK, etc.) migrates to cloud reference DB
✅ **SAFE:** All edges and relationships are preserved
✅ **SAFE:** Local database remains untouched until cloud migration is verified
❌ **NO DATA LOSS:** This is a reorganization, not a deletion

### Why This Architecture
- **Multi-tenancy:** Each customer gets isolated database (SOC 2 compliance)
- **Performance:** Reference data is read-heavy, customer data is write-heavy
- **Security:** Your IP (reference graph) never exposed to customers
- **Offline mode:** Can export reference subsets without customer data

---

## Part 1 — Schema Evolution

### 1.1 New Document Collections

| Collection | Purpose | Phase |
|---|---|---|
| `customer_profiles` | Multi-tenant customer metadata, tech stack declarations, framework targets | P0 |
| `scan_sessions` | Individual CI scan run metadata (timestamp, scanner type, commit SHA, repo) | P0 |
| `scan_findings` | Normalized scanner findings (SARIF/CycloneDX/custom mapped to canonical schema) | P0 |
| `remediation_playbooks` | Auto-generated remediation steps per finding cluster | P3 |
| `benchmark_aggregates` | Anonymized cross-customer stats (patching velocity, control coverage by industry) | P4 |
| `nl_query_log` | Natural language query history for improving text-to-AQL accuracy | P4 |
| `epss_velocity_alerts` | Pre-computed EPSS acceleration signals per CVE | P2 |
| `snapshot_manifests` | Tracks which reference data subsets are exported for offline clients | P3 |

### 1.2 Modified Existing Collections

**`components`** (currently 0 docs — becomes central)
```json
{
  "_key": "comp_<customer_id>_<hash>",
  "customer_id": "cust_001",
  "name": "log4j-core",
  "version": "2.14.1",
  "type": "library|framework|os|firmware|container",
  "source": "sbom|sca_scanner|manual",
  "cpe": "cpe:2.3:a:apache:log4j:2.14.1:*:*:*:*:*:*:*",
  "purl": "pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
  "first_seen": "2026-01-15T10:00:00Z",
  "last_seen": "2026-03-01T10:00:00Z",
  "sbom_depth": 0,
  "license_spdx": "Apache-2.0",
  "scan_session_id": "scan_abc123"
}
```

**`cpe_entries`** (currently 0 — populated from NVD CPE dictionary)
```json
{
  "_key": "cpe_<hash>",
  "cpe23": "cpe:2.3:a:apache:log4j:2.14.1:*:*:*:*:*:*:*",
  "vendor": "apache",
  "product": "log4j",
  "version": "2.14.1",
  "version_range_start": "2.0.0",
  "version_range_end": "2.17.0",
  "part": "a"
}
```

**`vulnerabilities`** — add fields:
```json
{
  "...existing fields...": "",
  "epss_current": 0.0342,
  "epss_30d_delta": 0.0215,
  "epss_velocity": "accelerating|stable|decelerating",
  "kev_listed": true,
  "blast_radius_score": 8.7,
  "reachable_threat_groups": ["APT29", "APT41"],
  "attack_path_count": 4
}
```

### 1.3 New Edge Collections

| Edge | From → To | Purpose | Phase |
|---|---|---|---|
| `belongs_to_customer` | components → customer_profiles | Multi-tenant component ownership | P0 |
| `found_in_scan` | scan_findings → scan_sessions | Links findings to CI runs | P0 |
| `finding_matches_vuln` | scan_findings → vulnerabilities | Scanner finding → CVE resolution | P0 |
| `component_has_finding` | components → scan_findings | Which component triggered which finding | P0 |
| `mitigated_by_playbook` | scan_findings → remediation_playbooks | Finding → remediation mapping | P3 |
| `framework_delta` | oscal_controls → oscal_controls | Tracks control changes between framework versions | P2 |
| `benchmark_contributes` | scan_findings → benchmark_aggregates | Anonymized aggregation link | P4 |

### 1.4 Edge Collections to Populate (Currently 0)

These exist in schema but need data pipelines:

| Edge | Data Source | Priority | Phase |
|---|---|---|---|
| `affects` | NVD CPE match feed + scan correlation | **P0** | P1 |
| `matched_by_cpe` | NVD CPE dictionary matching | **P0** | P1 |
| `depends_on` | SBOM dependency tree parsing (CycloneDX/SPDX) | **P0** | P1 |
| `technique_mitigated_by_control` | NIST SP 800-53 → ATT&CK mapping + D3FEND | **P0** | P1 |
| `maps_to_requirement` | SCF → regulatory framework manual + automated mapping | **P1** | P2 |
| `cross_framework_mapping` | OpenCRE data + NIST Crosswalk | **P1** | P2 |
| `d3fend_counters_technique` | D3FEND ontology ingest | **P1** | P2 |
| `capec_maps_to_attack` | CAPEC XML ATT&CK references | **P1** | P1 |
| `licensed_under` | Component → license resolution from SBOM/scanners | **P2** | P1 |
| `same_as` | Cross-database dedup (NVD ↔ VulnCheck ↔ OSV) | **P2** | P2 |

---

## Part 2 — Cloud/Client Architecture

### 2.1 Cloud Infrastructure

```
┌─────────────────────────────────────────────────────────────────┐
│  CLOUD INFRASTRUCTURE                                           │
│                                                                 │
│  ┌────────────────────┐    ┌─────────────────────────────────┐  │
│  │  API Gateway        │    │  Background Workers              │  │
│  │  (Kong / Traefik)   │    │                                  │  │
│  │  - Rate limiting     │    │  ┌──────────────────────────┐   │  │
│  │  - API key auth      │    │  │ EPSS Velocity Compute    │   │  │
│  │  - Per-customer      │    │  │ (daily cron)             │   │  │
│  │    quotas            │    │  └──────────────────────────┘   │  │
│  │  - Request logging   │    │  ┌──────────────────────────┐   │  │
│  └────────┬───────────┘    │  │ Reference Data Updater   │   │  │
│           │                 │  │ (NVD, KEV, EPSS, CAPEC   │   │  │
│           ▼                 │  │  D3FEND, ATT&CK weekly)  │   │  │
│  ┌────────────────────┐    │  └──────────────────────────┘   │  │
│  │  Complira API       │    │  ┌──────────────────────────┐   │  │
│  │  (FastAPI)          │    │  │ Benchmark Aggregator     │   │  │
│  │                      │    │  │ (weekly anonymized)      │   │  │
│  │  /v1/enrich          │    │  └──────────────────────────┘   │  │
│  │  /v1/compact         │    │  ┌──────────────────────────┐   │  │
│  │  /v1/blast-radius    │    │  │ Snapshot Builder         │   │  │
│  │  /v1/map-controls    │    │  │ (on-demand per customer) │   │  │
│  │  /v1/generate-doc    │    │  └──────────────────────────┘   │  │
│  │  /v1/epss-velocity   │    └─────────────────────────────────┘  │
│  │  /v1/defense-coverage│                                        │
│  │  /v1/what-if         │    ┌─────────────────────────────────┐  │
│  │  /v1/license-check   │    │  ArangoDB Cluster               │  │
│  │  /v1/benchmark       │    │  ┌───────────┐ ┌─────────────┐  │  │
│  │  /v1/nl-query        │    │  │ Reference │ │ Customer    │  │  │
│  │  /v1/snapshot/export │    │  │ Database  │ │ Database    │  │  │
│  └────────┬───────────┘    │  │ (shared)  │ │ (per-tenant)│  │  │
│           │                 │  └───────────┘ └─────────────┘  │  │
│           │                 └─────────────────────────────────┘  │
│           │                                                      │
│  ┌────────┴───────────┐    ┌─────────────────────────────────┐  │
│  │  Redis Cache        │    │  Object Storage (S3)            │  │
│  │  - Enrichment cache  │    │  - Generated docs               │  │
│  │  - EPSS snapshots    │    │  - Offline snapshots             │  │
│  │  - Session state     │    │  - Scan artifacts                │  │
│  └────────────────────┘    └─────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Database Separation Strategy

**Reference Database** (`complira_reference`) — shared, read-heavy:
- `attack_techniques`, `attack_patterns`, `atlas_techniques`
- `weaknesses`, `d3fend_techniques`, `oscal_controls`
- `kev_entries`, `epss_history`, `threat_groups`
- `regulatory_requirements`, `licenses`
- `vulnerabilities` (base CVE data without customer context)
- All cross-reference edges between the above
- Updated by background workers only, customers get read access via API

**Customer Database** (`complira_customer_<id>`) — per-tenant, write-heavy:
- `components`, `cpe_entries`, `scan_sessions`, `scan_findings`
- `customer_profiles`, `scorecard_results`, `package_health`
- `remediation_playbooks`
- Customer-specific edges: `affects`, `depends_on`, `component_has_finding`, `found_in_scan`
- Cross-database AQL queries link customer findings to reference data

**Why separate:**
- Reference data is your IP — never exposed, never shipped
- Customer data isolation for SOC 2 compliance (you're selling to compliance-conscious buyers)
- Independent scaling (reference DB is read-heavy, customer DBs are write-heavy during CI runs)
- Clean backup/restore per customer
- Enables the offline snapshot feature — you export a *subset* of reference, never customer data

---

## Part 3 — Implementation Phases

### Phase 0: Foundation (Weeks 1–2)

**Goal:** Multi-tenant cloud infrastructure, client SDK skeleton, scan ingestion pipeline

**Cloud tasks:**
1. Deploy ArangoDB cluster with separate reference and customer databases
2. Set up FastAPI service with API key authentication and per-customer scoping
3. Implement `/v1/scan/ingest` endpoint with SARIF and CycloneDX parsers
4. Create `customer_profiles`, `scan_sessions`, `scan_findings` collections
5. Deploy Redis cache layer
6. Set up API gateway with rate limiting (Kong or Traefik)
7. CI/CD pipeline for the API service itself (Docker + Kubernetes or ECS)

**Client tasks:**
1. Create `complira-action` GitHub Action skeleton
2. Implement scanner output detection and parsing (SARIF, CycloneDX, CSV)
3. Implement SBOM parsing (CycloneDX, SPDX)
4. Client SDK with API key auth, retry logic, error handling
5. Basic output formatting (SARIF enriched output, PR comments)

**Schema changes:**
- Create all new document collections from Section 1.1
- Create new edge collections from Section 1.3
- Add customer_id index on components, scan_findings

**Deliverable:** Client can run a scan in GitHub Actions, upload findings to cloud, get back a scan_session_id

---

### Phase 1: Core Pipeline + Data Enrichment (Weeks 3–5)

**Goal:** Complete enrich → compact → map pipeline, populate critical edges

**Cloud tasks:**
1. Implement `/v1/enrich` endpoint with full graph traversal
2. Implement `/v1/compact` endpoint with alias dedup + CWE rollup
3. Implement `/v1/map-controls` endpoint for FDA, SOC 2, ISO 27001
4. Build reference data updater workers:
   - NVD CVE/CPE feed → `vulnerabilities`, `cpe_entries`, `matched_by_cpe`
   - KEV feed → `kev_entries`, `exploited_in_wild` edges
   - EPSS feed → `epss_history`, `has_epss` edges
   - MITRE ATT&CK STIX → `attack_techniques`, cross-reference edges
   - CAPEC XML → `capec_maps_to_attack` edges (currently 0)
   - D3FEND ontology → `d3fend_counters_technique` edges (currently 0)
5. Build dependency tree builder from SBOM → `depends_on` edges
6. Build CPE matcher → `matched_by_cpe`, `affects` edges
7. Build control-technique mapper → `technique_mitigated_by_control` edges
8. Build component-license resolver → `licensed_under` edges

**Deliverable:** Full scan → enrich → compact → map pipeline working end-to-end

---

### Phase 2: Killer Features — Wave 1 (Weeks 6–9)

**Features: Blast Radius, EPSS Velocity, Defense Coverage, Regulatory Delta**

**2a. Blast Radius Simulation (Week 6–7)**
- Implement graph traversal engine with configurable depth
- Build kill chain reconstruction from `can_precede` edges
- Create visualization data model (nodes + edges)
- Build hop-distance computation
- Build executive summary generator
- Build export formats: PDF, JSON, Mermaid
- Implement `/v1/blast-radius` endpoint

**2b. EPSS Velocity, Portfolio Risk Curves & Predictive KEV (Week 7–8)**
- Build daily cron job: compute EPSS velocity for all CVEs
- Create `epss_velocity_alerts` collection
- Implement `/v1/epss-velocity` endpoint
- Build portfolio risk curve aggregation engine
- Build predictive KEV model
- Implement `/v1/predictive-kev` endpoint

**2c. Defense Coverage Heatmap (Week 8–9)**
- Build ATT&CK matrix coverage computation per customer
- Implement `/v1/defense-coverage` endpoint
- Include D3FEND recommendations

**2d. Regulatory Delta Analysis (Week 9)**
- Build framework version tracking
- Implement `framework_delta` edge creation
- Build customer impact computation
- Implement `/v1/regulatory-delta` endpoint

---

### Phase 3: Killer Features — Wave 2 (Weeks 10–13)

**Features: Transitive Dependency Risk, Remediation Playbooks, What-If Modeling, License Conflicts**

**3a. Transitive Dependency Risk (Week 10–11)**
- Build recursive traversal with risk propagation
- Implement `/v1/dependency-risk` endpoint

**3b. Remediation Playbooks (Week 11–12)**
- Build playbook generator
- Build dual-audience output (engineer + auditor)
- Implement `/v1/remediation-playbook` endpoint

**3c. What-If Impact Modeling (Week 12–13)**
- Build snapshot-and-modify engine
- Implement `/v1/what-if` endpoint

**3d. License Conflict Detection (Week 13)**
- Build license compatibility matrix
- Implement `/v1/license-check` endpoint

---

### Phase 4: Killer Features — Wave 3 (Weeks 14–16)

**Features: Benchmarking, NL Query, Offline Snapshots, Doc Generation**

**4a. Cross-Customer Benchmarking (Week 14)**
- Build weekly aggregation job
- Implement `/v1/benchmark` endpoint

**4b. Natural Language Query Interface (Week 14–15)**
- Build text-to-AQL translation layer
- Implement `/v1/nl-query` endpoint

**4c. Offline Snapshot Mode (Week 15–16)**
- Build snapshot builder
- Implement `/v1/snapshot/export` endpoint

**4d. Document Generation Enhancement (Week 16)**
- Integrate all feature outputs
- Implement `/v1/generate-doc` enhancements

---

## Timeline Summary

```
Week  1-2   [P0] Foundation ─────────────────── Cloud infra + client SDK + scan ingest
Week  3-5   [P1] Core Pipeline ──────────────── Enrich + compact + map + edge population
Week  6-7   [P2] Blast Radius ───────────────── Kill chain traversal + visualization
Week  7-8   [P2] EPSS Velocity ──────────────── Velocity + portfolio curves + predictive KEV
Week  8-9   [P2] Defense Coverage ───────────── ATT&CK heatmap + D3FEND recommendations
Week  9     [P2] Regulatory Delta ───────────── Framework version diffing
Week 10-11  [P3] Dependency Risk ────────────── Transitive risk propagation
Week 11-12  [P3] Remediation Playbooks ──────── Auto-generated fix plans
Week 12-13  [P3] What-If Modeling ───────────── Scenario simulation engine
Week 13     [P3] License Conflicts ──────────── Compatibility matrix
Week 14     [P4] Benchmarking ───────────────── Anonymized cross-customer metrics
Week 14-15  [P4] NL Query ──────────────────── Text-to-AQL interface
Week 15-16  [P4] Offline + Doc Gen ──────────── Snapshots + enriched templates
```
