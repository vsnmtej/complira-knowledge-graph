# Future-State Runtime Call Stack

**Ticket:** phase-2-enrichment-pipeline
**Stage:** 4 (Runtime Modeling)
**Purpose:** Detailed runtime call stacks for Phase 2 Enrichment Pipeline (3 endpoints)
**Status:** Round 1 - Initial modeling

---

## Call Stack 1: POST /v1/enrich - Full Enrichment Flow

**Endpoint:** `POST /v1/enrich`
**Use Case:** Enrich scan findings with CVE details, EPSS, KEV status, and threat intelligence
**Expected Performance:** ~2-3 seconds for 100 findings (with batch queries)

### Request Flow

```
REQUEST:
POST /v1/enrich
Headers: Authorization: Bearer <customer_jwt>
Body: {
  "scan_session_id": "scan_sess_123",
  "include_threat_intel": true,
  "include_kev": true,
  "include_epss": true
}
```

### Runtime Call Stack

```
1. API Layer: src/api/v1/endpoints/enrichment.py
   ├─> enrich_scan_findings(request: EnrichRequest, customer: CustomerProfile)
   │   ├─> Validate request (FastAPI auto-validation)
   │   ├─> Extract customer_id from JWT: "cust_456"
   │   └─> Call service layer
   │
   └─> EnrichmentService.enrich_scan_session()

2. Service Layer: src/api/services/enrichment.py
   ├─> EnrichmentService.enrich_scan_session(
   │       customer_id="cust_456",
   │       scan_session_id="scan_sess_123",
   │       include_threat_intel=True,
   │       include_kev=True,
   │       include_epss=True
   │   )
   │
   ├─> Step 1: Get scan findings from customer DB
   │   ├─> ScanFindingRepository.get_findings_by_session(scan_session_id)
   │   │   ├─> Switch to customer DB: "complira_customer_cust_456"
   │   │   ├─> AQL Query 1 (Customer DB):
   │   │   │   FOR finding IN scan_findings
   │   │   │       FILTER finding.scan_session_id == "scan_sess_123"
   │   │   │       RETURN finding
   │   │   └─> Returns: List[dict] (100 findings)
   │   │
   │   └─> Convert dicts → List[ScanFinding] models (100 findings)
   │       └─> Findings breakdown:
   │           - 80 findings with CVE IDs (e.g., "CVE-2023-1234")
   │           - 20 findings without CVE (SAST secrets: CWE-798, CWE-259)
   │
   ├─> Step 2: Group findings by CVE ID and CWE ID
   │   ├─> CVE findings: {
   │   │       "CVE-2023-1234": [finding1, finding2, ...],
   │   │       "CVE-2023-5678": [finding3, finding4, ...],
   │   │       ... (50 unique CVEs)
   │   │   }
   │   └─> Non-CVE findings: {
   │           "CWE-798": [finding81, finding82, ...],
   │           "CWE-259": [finding83, finding84, ...],
   │           ... (5 unique CWEs)
   │       }
   │
   ├─> Step 3: Batch query reference DB for CVE enrichment
   │   ├─> EnrichmentRepository.batch_get_cve_details(cve_ids=[50 unique CVEs])
   │   │   ├─> Switch to reference DB: "complira_graph_reference"
   │   │   ├─> AQL Query 2 (Reference DB - CVE Details):
   │   │   │   FOR cve_id IN ["CVE-2023-1234", "CVE-2023-5678", ...]
   │   │   │       LET vuln = FIRST(
   │   │   │           FOR v IN vulnerabilities
   │   │   │               FILTER v.cve_id == cve_id
   │   │   │               RETURN v
   │   │   │       )
   │   │   │       FILTER vuln != null
   │   │   │       RETURN vuln
   │   │   └─> Returns: List[dict] (50 CVE records)
   │   │
   │   └─> Convert dicts → List[Vulnerability] models (50 CVEs)
   │       └─> Each Vulnerability contains: {
   │               cve_id, description, cvss_v3_score, severity,
   │               published_date, last_modified, weaknesses: [CWE IDs]
   │           }
   │
   ├─> Step 4: Batch query EPSS scores
   │   ├─> EnrichmentRepository.batch_get_latest_epss(cve_ids=[50 unique CVEs])
   │   │   ├─> Switch to reference DB: "complira_graph_reference"
   │   │   ├─> AQL Query 3 (Reference DB - EPSS Scores):
   │   │   │   FOR cve_id IN ["CVE-2023-1234", "CVE-2023-5678", ...]
   │   │   │       LET latest_epss = FIRST(
   │   │   │           FOR epss IN epss_history
   │   │   │               FILTER epss.cve_id == cve_id
   │   │   │               SORT epss.score_date DESC
   │   │   │               LIMIT 1
   │   │   │               RETURN epss
   │   │   │       )
   │   │   │       FILTER latest_epss != null
   │   │   │       RETURN latest_epss
   │   │   └─> Returns: List[dict] (50 EPSS records)
   │   │
   │   └─> Convert dicts → List[EPSSHistory] models (50 EPSS scores)
   │       └─> Each EPSSHistory contains: {
   │               cve_id, epss_score, epss_percentile, score_date
   │           }
   │
   ├─> Step 5: Batch query KEV status
   │   ├─> EnrichmentRepository.batch_check_kev_status(cve_ids=[50 unique CVEs])
   │   │   ├─> Switch to reference DB: "complira_graph_reference"
   │   │   ├─> AQL Query 4 (Reference DB - KEV Status):
   │   │   │   FOR cve_id IN ["CVE-2023-1234", "CVE-2023-5678", ...]
   │   │   │       LET vuln = FIRST(
   │   │   │           FOR v IN vulnerabilities
   │   │   │               FILTER v.cve_id == cve_id
   │   │   │               RETURN v
   │   │   │       )
   │   │   │       FILTER vuln != null
   │   │   │       LET kev = FIRST(
   │   │   │           FOR k IN 1..1 OUTBOUND vuln._id exploited_in_wild
   │   │   │               RETURN k
   │   │   │       )
   │   │   │       FILTER kev != null
   │   │   │       RETURN {cve_id: cve_id, kev: kev}
   │   │   └─> Returns: List[dict] (10 KEV records - only CVEs in KEV)
   │   │
   │   └─> Convert dicts → List[KEVEntry] models (10 KEV entries)
   │       └─> Each KEVEntry contains: {
   │               cve_id, known_ransomware_campaign_use, date_added,
   │               required_action, due_date
   │           }
   │
   ├─> Step 6: Batch query threat intelligence (CWE → CAPEC → ATT&CK)
   │   ├─> Collect all CWE IDs from CVE findings + non-CVE findings
   │   │   └─> CWE IDs: ["CWE-79", "CWE-89", "CWE-798", "CWE-259", ...]
   │   │       (60 unique CWEs from 50 CVEs + 5 from non-CVE findings)
   │   │
   │   ├─> EnrichmentRepository.batch_get_threat_intelligence_chain(cwe_ids=[60 unique CWEs])
   │   │   ├─> Switch to reference DB: "complira_graph_reference"
   │   │   ├─> AQL Query 5 (Reference DB - Threat Intelligence Chain):
   │   │   │   FOR cwe_id IN ["CWE-79", "CWE-89", "CWE-798", ...]
   │   │   │       LET cwe = FIRST(
   │   │   │           FOR w IN weaknesses
   │   │   │               FILTER w.cwe_id == cwe_id
   │   │   │               RETURN w
   │   │   │       )
   │   │   │       FILTER cwe != null
   │   │   │
   │   │   │       // Get CAPECs
   │   │   │       LET capecs = (
   │   │   │           FOR c IN 1..1 INBOUND cwe._id capec_relates_to_cwe
   │   │   │               RETURN {
   │   │   │                   capec_id: c.capec_id,
   │   │   │                   name: c.name,
   │   │   │                   description: c.description
   │   │   │               }
   │   │   │       )
   │   │   │
   │   │   │       // Get ATT&CK techniques
   │   │   │       LET attacks = (
   │   │   │           FOR capec IN FLATTEN(
   │   │   │               FOR c IN 1..1 INBOUND cwe._id capec_relates_to_cwe
   │   │   │                   RETURN c
   │   │   │           )
   │   │   │               FOR a IN 1..1 OUTBOUND capec._id capec_maps_to_attack
   │   │   │                   RETURN {
   │   │   │                       technique_id: a.technique_id,
   │   │   │                       name: a.name,
   │   │   │                       tactic: a.tactic
   │   │   │                   }
   │   │   │       )
   │   │   │
   │   │   │       RETURN {
   │   │   │           cwe_id: cwe_id,
   │   │   │           cwe: cwe,
   │   │   │           capecs: capecs,
   │   │   │           attacks: attacks
   │   │   │       }
   │   │   └─> Returns: List[dict] (60 threat intel records)
   │   │       └─> Each record: {
   │   │               cwe_id: "CWE-79",
   │   │               cwe: {cwe_id, name, description},
   │   │               capecs: [{capec_id, name, description}, ...],
   │   │               attacks: [{technique_id, name, tactic}, ...]
   │   │           }
   │   │
   │   └─> Convert dicts → Dict[str, ThreatIntelligence] models (60 CWEs)
   │       └─> ThreatIntelligence model: {
   │               cwe: Weakness,
   │               capecs: List[AttackPattern],
   │               attack_techniques: List[ATTACKTechnique]
   │           }
   │
   ├─> Step 7: Build enriched findings
   │   ├─> For each finding (100 findings):
   │   │   ├─> If finding has CVE ID:
   │   │   │   └─> Create EnrichedFinding {
   │   │   │           finding: ScanFinding (original),
   │   │   │           cve_details: Vulnerability (from Step 3),
   │   │   │           epss_score: EPSSHistory (from Step 4),
   │   │   │           kev_entry: KEVEntry (from Step 5, if exists),
   │   │   │           threat_intelligence: ThreatIntelligence (from Step 6)
   │   │   │       }
   │   │   │
   │   │   └─> If finding has no CVE ID (non-CVE):
   │   │       └─> Create EnrichedFinding {
   │   │               finding: ScanFinding (original),
   │   │               cve_details: None,
   │   │               epss_score: None,
   │   │               kev_entry: None,
   │   │               threat_intelligence: ThreatIntelligence (from Step 6 via CWE)
   │   │           }
   │   │
   │   └─> Returns: List[EnrichedFinding] (100 enriched findings)
   │
   ├─> Step 8: Build response
   │   └─> Create EnrichResponse {
   │           scan_session_id: "scan_sess_123",
   │           total_findings: 100,
   │           enriched_findings: List[EnrichedFinding] (100),
   │           enrichment_metadata: {
   │               cve_enrichment_coverage: 80 / 80 = 100%,
   │               epss_coverage: 50 / 80 = 62.5%,
   │               kev_coverage: 10 / 80 = 12.5%,
   │               threat_intel_coverage: 60 / 60 = 100%
   │           }
   │       }
   │
   └─> Return EnrichResponse to API layer

3. API Layer Response: src/api/v1/endpoints/enrichment.py
   ├─> FastAPI auto-serializes EnrichResponse → JSON
   └─> Return HTTP 200 with JSON body

RESPONSE:
{
  "scan_session_id": "scan_sess_123",
  "total_findings": 100,
  "enriched_findings": [
    {
      "finding": {
        "finding_id": "finding_001",
        "vulnerability_id": "CVE-2023-1234",
        "severity": "HIGH",
        ...
      },
      "cve_details": {
        "cve_id": "CVE-2023-1234",
        "description": "Remote code execution in...",
        "cvss_v3_score": 9.8,
        ...
      },
      "epss_score": {
        "epss_score": 0.95,
        "epss_percentile": 0.99,
        "score_date": "2024-01-15"
      },
      "kev_entry": {
        "known_ransomware_campaign_use": true,
        "date_added": "2023-12-01",
        ...
      },
      "threat_intelligence": {
        "cwe": {"cwe_id": "CWE-79", "name": "XSS", ...},
        "capecs": [{"capec_id": "CAPEC-86", ...}],
        "attack_techniques": [{"technique_id": "T1059", ...}]
      }
    },
    ...
  ],
  "enrichment_metadata": {
    "cve_enrichment_coverage": 100.0,
    "epss_coverage": 62.5,
    "kev_coverage": 12.5,
    "threat_intel_coverage": 100.0
  }
}
```

### Performance Analysis

**Query Count:** 5 batch queries (vs 100+ queries without batching)
- Query 1: Get all findings from customer DB (1 query)
- Query 2: Batch get CVE details for 50 unique CVEs (1 query)
- Query 3: Batch get EPSS scores for 50 unique CVEs (1 query)
- Query 4: Batch check KEV status for 50 unique CVEs (1 query)
- Query 5: Batch get threat intelligence for 60 unique CWEs (1 query)

**Expected Performance:**
- Without batching: 100 findings × 4 queries each = 400 queries (~20-30 seconds)
- With batching: 5 queries total (~2-3 seconds) ✅

**Database Switches:** 2 (Customer DB → Reference DB)

---

## Call Stack 2: POST /v1/compact - Compaction Flow

**Endpoint:** `POST /v1/compact`
**Use Case:** Deduplicate findings by CVE and roll up CWEs to higher abstraction levels
**Expected Performance:** ~1-2 seconds for 100 findings

### Request Flow

```
REQUEST:
POST /v1/compact
Headers: Authorization: Bearer <customer_jwt>
Body: {
  "scan_session_id": "scan_sess_123",
  "deduplication_strategy": "by_cve",
  "cwe_rollup_level": "Class"
}
```

### Runtime Call Stack

```
1. API Layer: src/api/v1/endpoints/enrichment.py
   ├─> compact_scan_findings(request: CompactRequest, customer: CustomerProfile)
   │   ├─> Validate request (FastAPI auto-validation)
   │   ├─> Extract customer_id from JWT: "cust_456"
   │   └─> Call service layer
   │
   └─> CompactionService.compact_findings()

2. Service Layer: src/api/services/compaction.py
   ├─> CompactionService.compact_findings(
   │       customer_id="cust_456",
   │       scan_session_id="scan_sess_123",
   │       deduplication_strategy="by_cve",
   │       cwe_rollup_level="Class"
   │   )
   │
   ├─> Step 1: Get scan findings from customer DB
   │   ├─> ScanFindingRepository.get_findings_by_session(scan_session_id)
   │   │   ├─> Switch to customer DB: "complira_customer_cust_456"
   │   │   ├─> AQL Query 1 (Customer DB):
   │   │   │   FOR finding IN scan_findings
   │   │   │       FILTER finding.scan_session_id == "scan_sess_123"
   │   │   │       RETURN finding
   │   │   └─> Returns: List[dict] (100 findings)
   │   │
   │   └─> Convert dicts → List[ScanFinding] models (100 findings)
   │       └─> Example findings:
   │           - finding_001: CVE-2023-1234, CWE-79, file: app.js:42
   │           - finding_002: CVE-2023-1234, CWE-79, file: index.js:15
   │           - finding_003: CVE-2023-5678, CWE-89, file: db.js:89
   │           - finding_004: No CVE, CWE-798, file: config.py:12
   │           ...
   │
   ├─> Step 2: Deduplicate by CVE ID
   │   ├─> Group findings by CVE ID
   │   │   └─> CVE groups: {
   │   │           "CVE-2023-1234": [finding_001, finding_002, finding_010, ...] (15 findings),
   │   │           "CVE-2023-5678": [finding_003, finding_011, ...] (8 findings),
   │   │           "CVE-2023-9999": [finding_005, finding_012, ...] (10 findings),
   │   │           ... (50 unique CVEs)
   │   │       }
   │   │   └─> Non-CVE findings: [finding_004, finding_020, ...] (20 findings)
   │   │
   │   ├─> For each CVE group, create CompactedFinding:
   │   │   └─> CompactedFinding {
   │   │           vulnerability_id: "CVE-2023-1234",
   │   │           severity: "HIGH" (from first finding),
   │   │           occurrences: 15,
   │   │           affected_locations: [
   │   │               {file: "app.js", line: 42},
   │   │               {file: "index.js", line: 15},
   │   │               ...
   │   │           ],
   │   │           cwe_ids: ["CWE-79"] (unique CWEs from all findings in group)
   │   │       }
   │   │
   │   └─> Result after deduplication:
   │       - 50 compacted CVE findings (was 80 individual findings)
   │       - 20 non-CVE findings (no deduplication for non-CVE)
   │       - Total: 70 compacted findings (was 100 individual findings)
   │
   ├─> Step 3: Roll up CWEs to target abstraction level
   │   ├─> Collect all unique CWE IDs from compacted findings
   │   │   └─> CWE IDs: ["CWE-79", "CWE-89", "CWE-798", "CWE-259", ...] (60 unique)
   │   │
   │   ├─> CWERepository.batch_rollup_to_abstraction_level(
   │   │       cwe_ids=[60 unique CWEs],
   │   │       target_level="Class"
   │   │   )
   │   │   ├─> Switch to reference DB: "complira_graph_reference"
   │   │   ├─> AQL Query 2 (Reference DB - CWE Rollup):
   │   │   │   FOR cwe_id IN ["CWE-79", "CWE-89", "CWE-798", ...]
   │   │   │       LET cwe = FIRST(
   │   │   │           FOR w IN weaknesses
   │   │   │               FILTER w.cwe_id == cwe_id
   │   │   │               RETURN w
   │   │   │       )
   │   │   │       FILTER cwe != null
   │   │   │
   │   │   │       // Traverse up parent hierarchy to find Class-level CWE
   │   │   │       LET parent_chain = (
   │   │   │           FOR v, e, p IN 0..10 OUTBOUND cwe._id child_of
   │   │   │               FILTER v.abstraction == "Class" OR v.abstraction == "Pillar"
   │   │   │               LIMIT 1
   │   │   │               RETURN v
   │   │   │       )
   │   │   │
   │   │   │       LET rolled_up = LENGTH(parent_chain) > 0 ? parent_chain[0] : cwe
   │   │   │
   │   │   │       RETURN {
   │   │   │           original_cwe_id: cwe_id,
   │   │   │           rolled_up_cwe: rolled_up
   │   │   │       }
   │   │   └─> Returns: List[dict] (60 rollup mappings)
   │   │       └─> Example mappings:
   │   │           - CWE-79 (Variant: XSS) → CWE-74 (Class: Injection)
   │   │           - CWE-89 (Variant: SQL Injection) → CWE-74 (Class: Injection)
   │   │           - CWE-798 (Variant: Hard-coded Creds) → CWE-657 (Class: Credential Management)
   │   │
   │   └─> Convert dicts → Dict[str, Weakness] (60 CWE rollup mappings)
   │       └─> Mapping: {"CWE-79": CWE-74, "CWE-89": CWE-74, ...}
   │
   ├─> Step 4: Apply CWE rollup to compacted findings
   │   ├─> For each compacted finding (70 findings):
   │   │   ├─> Replace original CWE IDs with rolled-up CWE IDs
   │   │   │   └─> Before: cwe_ids = ["CWE-79"]
   │   │   │       After:  cwe_ids = ["CWE-74"] (rolled up to Class)
   │   │   │
   │   │   └─> Update CompactedFinding with rolled_up_cwe_ids
   │   │
   │   └─> Result after rollup:
   │       - 70 compacted findings with CWEs rolled up to Class level
   │       - CWE diversity reduced: 60 unique CWEs → 15 unique Class-level CWEs
   │
   ├─> Step 5: Build response
   │   └─> Create CompactResponse {
   │           scan_session_id: "scan_sess_123",
   │           original_finding_count: 100,
   │           compacted_finding_count: 70,
   │           reduction_percentage: 30.0,
   │           compacted_findings: List[CompactedFinding] (70),
   │           compaction_metadata: {
   │               deduplication_strategy: "by_cve",
   │               cwe_rollup_level: "Class",
   │               original_cwe_count: 60,
   │               rolled_up_cwe_count: 15,
   │               cwe_reduction_percentage: 75.0
   │           }
   │       }
   │
   └─> Return CompactResponse to API layer

3. API Layer Response: src/api/v1/endpoints/enrichment.py
   ├─> FastAPI auto-serializes CompactResponse → JSON
   └─> Return HTTP 200 with JSON body

RESPONSE:
{
  "scan_session_id": "scan_sess_123",
  "original_finding_count": 100,
  "compacted_finding_count": 70,
  "reduction_percentage": 30.0,
  "compacted_findings": [
    {
      "vulnerability_id": "CVE-2023-1234",
      "severity": "HIGH",
      "occurrences": 15,
      "affected_locations": [
        {"file": "app.js", "line": 42},
        {"file": "index.js", "line": 15},
        ...
      ],
      "cwe_ids": ["CWE-74"],
      "original_cwe_ids": ["CWE-79"]
    },
    ...
  ],
  "compaction_metadata": {
    "deduplication_strategy": "by_cve",
    "cwe_rollup_level": "Class",
    "original_cwe_count": 60,
    "rolled_up_cwe_count": 15,
    "cwe_reduction_percentage": 75.0
  }
}
```

### Performance Analysis

**Query Count:** 2 queries
- Query 1: Get all findings from customer DB (1 query)
- Query 2: Batch rollup CWEs to Class level (1 query)

**Expected Performance:**
- ~1-2 seconds for 100 findings ✅

**Database Switches:** 2 (Customer DB → Reference DB)

**Reduction Efficiency:**
- Findings: 100 → 70 (30% reduction)
- CWEs: 60 → 15 (75% reduction)

---

## Call Stack 3: POST /v1/map-controls - Control Mapping Flow

**Endpoint:** `POST /v1/map-controls`
**Use Case:** Map scan findings to regulatory controls (NIST 800-53, FDA 524B, ISO 27001)
**Expected Performance:** ~2-3 seconds for 100 findings

### Request Flow

```
REQUEST:
POST /v1/map-controls
Headers: Authorization: Bearer <customer_jwt>
Body: {
  "scan_session_id": "scan_sess_123",
  "frameworks": ["NIST 800-53", "FDA 524B", "ISO 27001"],
  "use_compacted_view": true
}
```

### Runtime Call Stack

```
1. API Layer: src/api/v1/endpoints/enrichment.py
   ├─> map_findings_to_controls(request: MapControlsRequest, customer: CustomerProfile)
   │   ├─> Validate request (FastAPI auto-validation)
   │   ├─> Extract customer_id from JWT: "cust_456"
   │   └─> Call service layer
   │
   └─> ControlMappingService.map_controls()

2. Service Layer: src/api/services/control_mapping.py
   ├─> ControlMappingService.map_controls(
   │       customer_id="cust_456",
   │       scan_session_id="scan_sess_123",
   │       frameworks=["NIST 800-53", "FDA 524B", "ISO 27001"],
   │       use_compacted_view=True
   │   )
   │
   ├─> Step 1: Get findings (compacted if requested)
   │   ├─> If use_compacted_view = True:
   │   │   ├─> CompactionService.compact_findings(
   │   │   │       customer_id="cust_456",
   │   │   │       scan_session_id="scan_sess_123",
   │   │   │       deduplication_strategy="by_cve",
   │   │   │       cwe_rollup_level="Class"
   │   │   │   )
   │   │   └─> Returns: CompactResponse (70 compacted findings)
   │   │       └─> Findings have rolled-up CWE IDs: ["CWE-74", "CWE-657", ...]
   │   │
   │   └─> If use_compacted_view = False:
   │       └─> ScanFindingRepository.get_findings_by_session(scan_session_id)
   │           └─> Returns: List[ScanFinding] (100 findings)
   │
   ├─> Step 2: Collect all unique CWE IDs
   │   ├─> Extract CWE IDs from compacted findings
   │   │   └─> CWE IDs: ["CWE-74", "CWE-657", "CWE-119", ...] (15 unique Class-level CWEs)
   │   │
   │   └─> If use_compacted_view = False, would have 60 unique CWEs
   │
   ├─> Step 3: Query regulatory mappings for CWEs
   │   ├─> RegulatoryRepository.batch_get_requirements_for_cwes(
   │   │       cwe_ids=[15 unique CWEs],
   │   │       frameworks=["NIST 800-53", "FDA 524B", "ISO 27001"]
   │   │   )
   │   │   ├─> Switch to reference DB: "complira_graph_reference"
   │   │   ├─> AQL Query 1 (Reference DB - CWE → Regulatory Requirements):
   │   │   │   FOR cwe_id IN ["CWE-74", "CWE-657", "CWE-119", ...]
   │   │   │       LET cwe = FIRST(
   │   │   │           FOR w IN weaknesses
   │   │   │               FILTER w.cwe_id == cwe_id
   │   │   │               RETURN w
   │   │   │       )
   │   │   │       FILTER cwe != null
   │   │   │
   │   │   │       // Get regulatory requirements
   │   │   │       LET requirements = (
   │   │   │           FOR req IN 1..1 OUTBOUND cwe._id maps_to_requirement
   │   │   │               FILTER req.framework IN ["NIST 800-53", "FDA 524B", "ISO 27001"]
   │   │   │               RETURN req
   │   │   │       )
   │   │   │
   │   │   │       RETURN {
   │   │   │           cwe_id: cwe_id,
   │   │   │           requirements: requirements
   │   │   │       }
   │   │   └─> Returns: List[dict] (15 CWE → requirement mappings)
   │   │       └─> Example mapping for CWE-74 (Injection):
   │   │           {
   │   │               cwe_id: "CWE-74",
   │   │               requirements: [
   │   │                   {requirement_id: "NIST-800-53-SI-10", framework: "NIST 800-53", ...},
   │   │                   {requirement_id: "FDA-524B-5.1", framework: "FDA 524B", ...},
   │   │                   {requirement_id: "ISO-27001-A.14.2", framework: "ISO 27001", ...}
   │   │               ]
   │   │           }
   │   │
   │   └─> Convert dicts → Dict[str, List[RegulatoryRequirement]]
   │       └─> Mapping: {
   │               "CWE-74": [NIST-800-53-SI-10, FDA-524B-5.1, ISO-27001-A.14.2],
   │               "CWE-657": [NIST-800-53-IA-5, FDA-524B-3.2, ISO-27001-A.9.4],
   │               ...
   │           }
   │
   ├─> Step 4: Query NIST 800-53 controls
   │   ├─> Extract NIST requirement IDs from Step 3 mappings
   │   │   └─> NIST IDs: ["NIST-800-53-SI-10", "NIST-800-53-IA-5", ...] (30 unique)
   │   │
   │   ├─> RegulatoryRepository.batch_get_nist_controls(
   │   │       requirement_ids=[30 NIST IDs]
   │   │   )
   │   │   ├─> Switch to reference DB: "complira_graph_reference"
   │   │   ├─> AQL Query 2 (Reference DB - NIST Controls):
   │   │   │   FOR req_id IN ["NIST-800-53-SI-10", "NIST-800-53-IA-5", ...]
   │   │   │       LET req = FIRST(
   │   │   │           FOR r IN regulatory_requirements
   │   │   │               FILTER r.requirement_id == req_id
   │   │   │               RETURN r
   │   │   │       )
   │   │   │       FILTER req != null
   │   │   │
   │   │   │       // Get OSCAL control details
   │   │   │       LET control = FIRST(
   │   │   │           FOR c IN 1..1 OUTBOUND req._id implements_control
   │   │   │               RETURN c
   │   │   │       )
   │   │   │
   │   │   │       RETURN {
   │   │   │           requirement_id: req_id,
   │   │   │           control: control
   │   │   │       }
   │   │   └─> Returns: List[dict] (30 NIST controls)
   │   │       └─> Example control for NIST-800-53-SI-10:
   │   │           {
   │   │               requirement_id: "NIST-800-53-SI-10",
   │   │               control: {
   │   │                   control_id: "SI-10",
   │   │                   title: "Information Input Validation",
   │   │                   description: "Check the validity of information inputs",
   │   │                   baseline: ["moderate", "high"]
   │   │               }
   │   │           }
   │   │
   │   └─> Convert dicts → Dict[str, OSCALControl]
   │       └─> Mapping: {
   │               "NIST-800-53-SI-10": OSCALControl(control_id="SI-10", ...),
   │               "NIST-800-53-IA-5": OSCALControl(control_id="IA-5", ...),
   │               ...
   │           }
   │
   ├─> Step 5: Build control mappings per finding
   │   ├─> For each compacted finding (70 findings):
   │   │   ├─> Get CWE IDs: ["CWE-74"]
   │   │   │
   │   │   ├─> Lookup requirements for CWE-74 (from Step 3):
   │   │   │   └─> Requirements: [NIST-800-53-SI-10, FDA-524B-5.1, ISO-27001-A.14.2]
   │   │   │
   │   │   ├─> Lookup NIST controls (from Step 4):
   │   │   │   └─> Controls: [OSCALControl(SI-10), ...]
   │   │   │
   │   │   └─> Create ControlMapping {
   │   │           finding_id: "CVE-2023-1234",
   │   │           cwe_ids: ["CWE-74"],
   │   │           nist_controls: [OSCALControl(SI-10), ...],
   │   │           fda_requirements: [RegulatoryRequirement(FDA-524B-5.1), ...],
   │   │           iso_requirements: [RegulatoryRequirement(ISO-27001-A.14.2), ...]
   │   │       }
   │   │
   │   └─> Returns: List[ControlMapping] (70 mappings)
   │
   ├─> Step 6: Aggregate control statistics
   │   ├─> Count unique controls per framework:
   │   │   └─> NIST 800-53: 30 unique controls
   │   │       FDA 524B: 25 unique requirements
   │   │       ISO 27001: 20 unique requirements
   │   │
   │   └─> Create ControlStatistics {
   │           total_findings_mapped: 70,
   │           total_nist_controls: 30,
   │           total_fda_requirements: 25,
   │           total_iso_requirements: 20,
   │           coverage_percentage: {
   │               "NIST 800-53": 100.0,  // All 70 findings mapped to NIST controls
   │               "FDA 524B": 85.7,       // 60/70 findings mapped to FDA
   │               "ISO 27001": 92.9       // 65/70 findings mapped to ISO
   │           }
   │       }
   │
   ├─> Step 7: Build response
   │   └─> Create ControlMappingsResponse {
   │           scan_session_id: "scan_sess_123",
   │           frameworks: ["NIST 800-53", "FDA 524B", "ISO 27001"],
   │           control_mappings: List[ControlMapping] (70),
   │           control_statistics: ControlStatistics,
   │           used_compacted_view: true
   │       }
   │
   └─> Return ControlMappingsResponse to API layer

3. API Layer Response: src/api/v1/endpoints/enrichment.py
   ├─> FastAPI auto-serializes ControlMappingsResponse → JSON
   └─> Return HTTP 200 with JSON body

RESPONSE:
{
  "scan_session_id": "scan_sess_123",
  "frameworks": ["NIST 800-53", "FDA 524B", "ISO 27001"],
  "control_mappings": [
    {
      "finding_id": "CVE-2023-1234",
      "cwe_ids": ["CWE-74"],
      "nist_controls": [
        {
          "control_id": "SI-10",
          "title": "Information Input Validation",
          "description": "Check the validity of information inputs",
          "baseline": ["moderate", "high"]
        }
      ],
      "fda_requirements": [
        {
          "requirement_id": "FDA-524B-5.1",
          "title": "Input Validation",
          ...
        }
      ],
      "iso_requirements": [
        {
          "requirement_id": "ISO-27001-A.14.2",
          "title": "Security in Development",
          ...
        }
      ]
    },
    ...
  ],
  "control_statistics": {
    "total_findings_mapped": 70,
    "total_nist_controls": 30,
    "total_fda_requirements": 25,
    "total_iso_requirements": 20,
    "coverage_percentage": {
      "NIST 800-53": 100.0,
      "FDA 524B": 85.7,
      "ISO 27001": 92.9
    }
  },
  "used_compacted_view": true
}
```

### Performance Analysis

**Query Count:** 2 queries (when use_compacted_view=True)
- Query 1: Get CWE → Regulatory mappings (1 query for 15 CWEs)
- Query 2: Get NIST control details (1 query for 30 controls)

**Expected Performance:**
- ~2-3 seconds for 70 compacted findings ✅
- Would be ~5-7 seconds for 100 individual findings (without compaction)

**Database Switches:** 2 (Customer DB → Reference DB)

**Efficiency Gains from Compaction:**
- CWE mappings: 15 unique CWEs vs 60 unique CWEs (75% reduction)
- Faster query response due to fewer CWE lookups

---

## Call Stack 4: Batch Query Optimization Patterns

**Purpose:** Document reusable batch query patterns for performance optimization

### Pattern 1: Batch Lookup with FOR...IN

**Use Case:** Get multiple CVE records in a single query

```aql
// Input: List of CVE IDs
["CVE-2023-1234", "CVE-2023-5678", "CVE-2024-0001", ...]

// Query
FOR cve_id IN @cve_ids
    LET vuln = FIRST(
        FOR v IN vulnerabilities
            FILTER v.cve_id == cve_id
            RETURN v
    )
    FILTER vuln != null
    RETURN vuln

// Output: List of Vulnerability documents
[
    {_key: "...", cve_id: "CVE-2023-1234", description: "...", cvss_v3_score: 9.8, ...},
    {_key: "...", cve_id: "CVE-2023-5678", description: "...", cvss_v3_score: 7.5, ...},
    ...
]
```

**Performance:**
- Without batching: N queries (N = number of CVE IDs)
- With batching: 1 query
- Speedup: ~N× faster

### Pattern 2: Batch Lookup with Subquery and SORT

**Use Case:** Get latest EPSS score for multiple CVEs

```aql
// Input: List of CVE IDs
["CVE-2023-1234", "CVE-2023-5678", ...]

// Query
FOR cve_id IN @cve_ids
    LET latest_epss = FIRST(
        FOR epss IN epss_history
            FILTER epss.cve_id == cve_id
            SORT epss.score_date DESC
            LIMIT 1
            RETURN epss
    )
    FILTER latest_epss != null
    RETURN latest_epss

// Output: List of latest EPSS records
[
    {cve_id: "CVE-2023-1234", epss_score: 0.95, epss_percentile: 0.99, score_date: "2024-01-15"},
    {cve_id: "CVE-2023-5678", epss_score: 0.12, epss_percentile: 0.45, score_date: "2024-01-15"},
    ...
]
```

**Performance:**
- Without batching: N queries with SORT each
- With batching: 1 query with N subqueries (server-side optimization)
- Speedup: ~N× faster

### Pattern 3: Batch Graph Traversal (Multi-hop)

**Use Case:** Get CWE → CAPEC → ATT&CK chain for multiple CWEs

```aql
// Input: List of CWE IDs
["CWE-79", "CWE-89", "CWE-798", ...]

// Query
FOR cwe_id IN @cwe_ids
    LET cwe = FIRST(
        FOR w IN weaknesses
            FILTER w.cwe_id == cwe_id
            RETURN w
    )
    FILTER cwe != null

    // Get CAPECs (1-hop traversal via INBOUND edge)
    LET capecs = (
        FOR c IN 1..1 INBOUND cwe._id capec_relates_to_cwe
            RETURN {
                capec_id: c.capec_id,
                name: c.name,
                description: c.description
            }
    )

    // Get ATT&CK techniques (2-hop traversal: CWE → CAPEC → ATT&CK)
    LET attacks = (
        FOR capec IN FLATTEN(
            FOR c IN 1..1 INBOUND cwe._id capec_relates_to_cwe
                RETURN c
        )
            FOR a IN 1..1 OUTBOUND capec._id capec_maps_to_attack
                RETURN {
                    technique_id: a.technique_id,
                    name: a.name,
                    tactic: a.tactic
                }
    )

    RETURN {
        cwe_id: cwe_id,
        cwe: cwe,
        capecs: capecs,
        attacks: attacks
    }

// Output: List of threat intelligence chains
[
    {
        cwe_id: "CWE-79",
        cwe: {cwe_id: "CWE-79", name: "Cross-site Scripting", ...},
        capecs: [
            {capec_id: "CAPEC-86", name: "XSS Through HTTP Query Strings", ...},
            {capec_id: "CAPEC-18", name: "XSS Targeting Non-Script Elements", ...}
        ],
        attacks: [
            {technique_id: "T1059", name: "Command and Scripting Interpreter", tactic: "Execution"},
            {technique_id: "T1566", name: "Phishing", tactic: "Initial Access"}
        ]
    },
    ...
]
```

**Performance:**
- Without batching: N queries × (1 CWE lookup + 1 CAPEC traversal + 1 ATT&CK traversal) = 3N queries
- With batching: 1 query with N subtraversals
- Speedup: ~3N× faster

### Pattern 4: Batch Hierarchy Traversal with Depth Limit

**Use Case:** Roll up multiple CWEs to parent abstraction level

```aql
// Input: List of CWE IDs + target abstraction level
cwe_ids: ["CWE-79", "CWE-89", "CWE-798", ...]
target_level: "Class"

// Query
FOR cwe_id IN @cwe_ids
    LET cwe = FIRST(
        FOR w IN weaknesses
            FILTER w.cwe_id == cwe_id
            RETURN w
    )
    FILTER cwe != null

    // Traverse up parent hierarchy (max 10 hops)
    LET parent_chain = (
        FOR v, e, p IN 0..10 OUTBOUND cwe._id child_of
            FILTER v.abstraction == @target_level OR v.abstraction == "Pillar"
            LIMIT 1
            RETURN v
    )

    // Use parent if found, otherwise keep original CWE
    LET rolled_up = LENGTH(parent_chain) > 0 ? parent_chain[0] : cwe

    RETURN {
        original_cwe_id: cwe_id,
        original_abstraction: cwe.abstraction,
        rolled_up_cwe: rolled_up,
        rolled_up_abstraction: rolled_up.abstraction
    }

// Output: List of rollup mappings
[
    {
        original_cwe_id: "CWE-79",
        original_abstraction: "Variant",
        rolled_up_cwe: {cwe_id: "CWE-74", name: "Improper Neutralization", ...},
        rolled_up_abstraction: "Class"
    },
    {
        original_cwe_id: "CWE-89",
        original_abstraction: "Variant",
        rolled_up_cwe: {cwe_id: "CWE-74", name: "Improper Neutralization", ...},
        rolled_up_abstraction: "Class"
    },
    ...
]
```

**Performance:**
- Without batching: N queries × (1 CWE lookup + 1 hierarchy traversal) = 2N queries
- With batching: 1 query with N subtraversals
- Speedup: ~2N× faster

### Pattern 5: Batch Filtered Edge Traversal

**Use Case:** Get regulatory requirements for multiple CWEs filtered by framework

```aql
// Input: List of CWE IDs + frameworks
cwe_ids: ["CWE-74", "CWE-657", ...]
frameworks: ["NIST 800-53", "FDA 524B", "ISO 27001"]

// Query
FOR cwe_id IN @cwe_ids
    LET cwe = FIRST(
        FOR w IN weaknesses
            FILTER w.cwe_id == cwe_id
            RETURN w
    )
    FILTER cwe != null

    // Get regulatory requirements filtered by framework
    LET requirements = (
        FOR req IN 1..1 OUTBOUND cwe._id maps_to_requirement
            FILTER req.framework IN @frameworks
            RETURN req
    )

    RETURN {
        cwe_id: cwe_id,
        requirements: requirements
    }

// Output: List of CWE → requirement mappings
[
    {
        cwe_id: "CWE-74",
        requirements: [
            {requirement_id: "NIST-800-53-SI-10", framework: "NIST 800-53", ...},
            {requirement_id: "FDA-524B-5.1", framework: "FDA 524B", ...},
            {requirement_id: "ISO-27001-A.14.2", framework: "ISO 27001", ...}
        ]
    },
    ...
]
```

**Performance:**
- Without batching: N queries × (1 CWE lookup + 1 requirement traversal) = 2N queries
- With batching: 1 query with N filtered traversals
- Speedup: ~2N× faster

---

## Round 1 Review Summary

**Call Stacks Modeled:** 4
1. ✅ POST /v1/enrich - Full enrichment flow (8 steps, 5 AQL queries)
2. ✅ POST /v1/compact - Compaction flow (5 steps, 2 AQL queries)
3. ✅ POST /v1/map-controls - Control mapping flow (7 steps, 2 AQL queries)
4. ✅ Batch query optimization patterns (5 reusable patterns)

**Performance Targets:**
- /v1/enrich: ~2-3 seconds for 100 findings ✅
- /v1/compact: ~1-2 seconds for 100 findings ✅
- /v1/map-controls: ~2-3 seconds for 70 compacted findings ✅

**Key Optimizations:**
- Batch queries: 5 queries for /v1/enrich (vs 100+ without batching)
- CWE rollup: 60 CWEs → 15 Class-level CWEs (75% reduction)
- Compaction: 100 findings → 70 findings (30% reduction)

**Database Switches:** 2 per endpoint (Customer DB → Reference DB)

**Graceful Degradation:**
- FILTER vuln != null / FILTER latest_epss != null - Skip missing data
- Service layer handles missing enrichment data without failing

**Next:** Round 2 review for runtime validation and edge case handling

---

## Round 2 Review

**Review Questions:**

### Q1: Error Handling
**Question:** How do we handle AQL query failures or database connection errors?

**Answer:**
- Service layer wraps repository calls in try/except blocks
- Repository layer raises specific exceptions: `DatabaseConnectionError`, `QueryExecutionError`
- API layer catches exceptions and returns appropriate HTTP status codes:
  - 500 Internal Server Error for database failures
  - 503 Service Unavailable for connection issues
- Partial enrichment: If EPSS query fails, return enrichment without EPSS data (graceful degradation)

### Q2: Authentication & Authorization
**Question:** How do we ensure customers can only access their own scan sessions?

**Answer:**
- JWT authentication extracts `customer_id` from token
- Service layer validates: `scan_session.customer_id == customer_id`
- If mismatch: Raise `UnauthorizedError` → API returns 403 Forbidden
- Database switch: Always use `complira_customer_{customer_id}` database

### Q3: Empty/Missing Data Handling
**Question:** What happens if a scan session has no findings?

**Answer:**
- ScanFindingRepository.get_findings_by_session() returns empty list `[]`
- Service layer detects empty list and returns early:
  ```python
  if not findings:
      return EnrichResponse(
          scan_session_id=scan_session_id,
          total_findings=0,
          enriched_findings=[],
          enrichment_metadata={...}
      )
  ```
- No reference DB queries executed (performance optimization)

### Q4: Non-CVE Finding Enrichment
**Question:** How do we handle findings with no CVE ID (e.g., SAST secrets)?

**Answer:**
- Detect missing CVE: `if not finding.vulnerability_id or not finding.vulnerability_id.startswith("CVE-")`
- Extract CWE IDs from finding metadata (e.g., `finding.cwe_ids = ["CWE-798"]`)
- Query threat intelligence via CWE only: CWE → CAPEC → ATT&CK
- Return partial enrichment:
  ```python
  EnrichedFinding(
      finding=finding,
      cve_details=None,
      epss_score=None,
      kev_entry=None,
      threat_intelligence=ThreatIntelligence(...)  # Via CWE
  )
  ```

### Q5: CWE Rollup Edge Cases
**Question:** What if a CWE has no parent at the target abstraction level?

**Answer:**
- AQL query uses fallback: `LET rolled_up = LENGTH(parent_chain) > 0 ? parent_chain[0] : cwe`
- If no parent found, keep original CWE unchanged
- Example: CWE-1000 (Research Concept) has no Class parent → stays CWE-1000

### Q6: Control Mapping Coverage
**Question:** What if a CWE has no regulatory mappings?

**Answer:**
- AQL query returns empty `requirements: []` for that CWE
- Service layer creates ControlMapping with empty lists:
  ```python
  ControlMapping(
      finding_id=finding.vulnerability_id,
      cwe_ids=finding.cwe_ids,
      nist_controls=[],  # Empty if no mappings found
      fda_requirements=[],
      iso_requirements=[]
  )
  ```
- Control statistics tracks coverage percentage: `coverage_percentage = mapped_findings / total_findings`

### Q7: Large Scan Sessions
**Question:** What if a scan session has 10,000 findings?

**Answer:**
- Current design: No pagination, load all findings in memory
- Risk: Memory exhaustion for very large scans
- Mitigation for MVP: Document limitation in API docs (max 1,000 findings recommended)
- Future enhancement: Add pagination support:
  ```python
  EnrichRequest(
      scan_session_id="...",
      offset=0,
      limit=100
  )
  ```

### Q8: Duplicate CVE Handling
**Question:** How does compaction handle duplicate CVEs across different locations?

**Answer:**
- Compaction groups by CVE ID: `group_by_cve = defaultdict(list)`
- For each group: `compacted = CompactedFinding(occurrences=len(group), affected_locations=[...])`
- All locations preserved in `affected_locations` list
- Example:
  ```python
  # Before compaction:
  - finding_001: CVE-2023-1234, file: app.js:42
  - finding_002: CVE-2023-1234, file: index.js:15

  # After compaction:
  CompactedFinding(
      vulnerability_id="CVE-2023-1234",
      occurrences=2,
      affected_locations=[
          {file: "app.js", line: 42},
          {file: "index.js", line: 15}
      ]
  )
  ```

### Q9: Framework Filtering
**Question:** What if user requests only NIST 800-53 controls (not FDA or ISO)?

**Answer:**
- MapControlsRequest accepts: `frameworks: List[str]`
- AQL query filters: `FILTER req.framework IN @frameworks`
- Only requested frameworks returned in response
- Example:
  ```python
  # Request
  MapControlsRequest(
      frameworks=["NIST 800-53"]  # Only NIST
  )

  # Response
  ControlMapping(
      nist_controls=[...],  # Populated
      fda_requirements=[],  # Empty (not requested)
      iso_requirements=[]   # Empty (not requested)
  )
  ```

### Q10: Performance Monitoring
**Question:** How do we track actual performance vs expected performance?

**Answer:**
- Add timing instrumentation in service layer:
  ```python
  start_time = time.time()
  enriched_findings = await enrich_scan_session(...)
  elapsed_time = time.time() - start_time
  logger.info(f"Enrichment completed in {elapsed_time:.2f}s for {len(findings)} findings")
  ```
- Include performance metadata in response:
  ```python
  EnrichResponse(
      ...,
      enrichment_metadata={
          ...,
          "query_time_seconds": 2.34,
          "finding_count": 100
      }
  )
  ```
- Future: Add Prometheus metrics for monitoring

---

## Round 2 Review Result

**Blockers:** None ✅

**Required Artifact Updates:** None ✅

**Newly Discovered Use Cases:** None ✅

**Runtime Model Status:** Complete ✅

**Next Stage:** Stage 5 (Review Gate)

---

## Stage 5 Review Gate Checklist

- [x] Round 1 complete - All 4 call stacks modeled
- [x] Round 2 complete - All 10 review questions answered
- [x] No blockers identified
- [x] No required artifact updates
- [x] No newly discovered use cases
- [x] Performance targets defined and achievable
- [x] Error handling patterns documented
- [x] Edge cases addressed

**Gate Status:** `Go Confirmed` ✅

**Next Step:** Transition to Stage 6 (Implementation) with Code Edit Permission UNLOCKED
