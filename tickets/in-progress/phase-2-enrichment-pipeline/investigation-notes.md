# Investigation Notes: Phase 2 Enrichment Pipeline

**Ticket:** phase-2-enrichment-pipeline
**Stage:** 1 (Investigation + Triage)
**Date:** 2026-03-03
**Investigator:** Automated Investigation

---

## Investigation Summary

Investigated existing reference database schema, Phase 1 code structure, and available data sources to understand what's needed for the enrichment pipeline. All required models and edge collections exist in the reference database.

---

## 1. Reference Database Investigation

### 1.1 Available Models (from `src/complira_graph/models.py`)

**✅ All enrichment models exist:**

#### Vulnerability Intelligence Models
- `Vulnerability` (CVE records)
  - Fields: `cve_id`, `description`, `cvss_v2_score`, `cvss_v3_score`, `cvss_v3_vector`, `published`, `modified`, `cwe_ids`, `references`
  - Source: NVD, OSV, GHSA
  - _key generation: `normalize_cve_id(cve_id)` → `cve_2024_1234`

- `Weakness` (CWE records)
  - Fields: `cwe_id`, `name`, `abstraction`, `description`, `common_consequences`, `mitigations`
  - Source: MITRE CWE
  - _key generation: `normalize_cwe_id(cwe_id)` → `cwe_79`

- `KEVEntry` (CISA KEV)
  - Fields: `cve_id`, `vendor_project`, `product`, `short_description`, `date_added`, `due_date`, `known_ransomware_campaign_use`
  - Source: CISA KEV catalog
  - _key generation: `normalize_cve_id(cve_id)` → `cve_2024_1234`

- `EPSSHistory` (Exploit Prediction Scores)
  - Fields: `cve_id`, `epss_score` (0.0-1.0), `percentile`, `score_date`
  - Source: EPSS daily feed
  - _key generation: `{cve_key}_{date}` → `cve_2024_1234_2026_03_01`

#### Threat Framework Models
- `ATTACKTechnique` (MITRE ATT&CK)
  - Fields: `technique_id`, `name`, `description`, `tactic_names`, `platforms`, `detection`
  - Source: MITRE ATT&CK STIX
  - _key generation: `normalize_attack_id(technique_id)` → `t1059_001`

- `AttackPattern` (CAPEC)
  - Fields: `capec_id`, `name`, `description`, `abstraction`, `prerequisites`, `mitigations`
  - Source: MITRE CAPEC XML
  - _key generation: `capec_{id}` → `capec_66`

- `D3FENDTechnique` (MITRE D3FEND)
  - Fields: `d3fend_id`, `name`, `description`
  - Source: MITRE D3FEND ontology

#### Regulatory Compliance Models
- `RegulatoryRequirement`
  - Fields: `requirement_id`, `framework_id`, `title`, `description`, `category`
  - Source: NIST, FDA, ISO, IEC, etc.

- `OSCALControl` (NIST 800-53)
  - Fields: `control_id`, `title`, `description`, `family`
  - Source: NIST OSCAL JSON

- `SCFControl` (Secure Controls Framework)
  - Fields: `control_id`, `title`, `description`
  - Source: SCF YAML

---

### 1.2 Available Edge Collections (from `src/complira_graph/db.py`)

**✅ All required edges exist:**

#### For Enrichment (Phase 2a - /v1/enrich)
- `has_weakness` - Vulnerability → CWE
- `has_epss` - Vulnerability → EPSS history entry
- `exploited_in_wild` - Vulnerability → KEV entry
- `capec_relates_to_cwe` - CAPEC → CWE
- `capec_maps_to_attack` - CAPEC → ATT&CK
- `technique_exploits_weakness` - ATT&CK → CWE

#### For Compacting (Phase 2b - /v1/compact)
- `child_of` - CWE → parent CWE (hierarchy for rollup)
- `peer_of` - CWE ↔ peer CWE

#### For Control Mapping (Phase 2c - /v1/map-controls)
- `maps_to_requirement` - CWE → regulatory requirements
- `requirement_hierarchy` - Requirement → parent requirement
- `cross_framework_mapping` - Framework ↔ framework equivalence
- `technique_mitigated_by_control` - ATT&CK → NIST 800-53 control

---

### 1.3 Data Availability Assessment

**Query Pattern for Enrichment:**

```python
# Enrich a finding with CVE-2024-1234
finding = ScanFinding(cve_id="CVE-2024-1234", ...)

# 1. Get CVE details
vuln = Vulnerability.query(cve_id="CVE-2024-1234")  # From reference DB

# 2. Get EPSS score (latest)
epss = EPSSHistory.query(cve_id="CVE-2024-1234").sort_by_date().latest()

# 3. Check KEV status
kev = KEVEntry.query(cve_id="CVE-2024-1234")

# 4. Get CWE → CAPEC → ATT&CK chain
cwe_ids = vuln.cwe_ids  # e.g., ["CWE-79"]
capecs = CAPEC.query(cwe_id IN cwe_ids)  # Via capec_relates_to_cwe edge
attack_techniques = ATTACKTechnique.query(capec_id IN capecs)  # Via capec_maps_to_attack edge

# 5. Get regulatory requirements
requirements = RegulatoryRequirement.query(cwe_id IN cwe_ids)  # Via maps_to_requirement edge
```

**Data Availability:**
- ✅ Vulnerabilities: Available (populated by NVD/OSV/GHSA agents)
- ✅ EPSS: Available (populated by EPSS agent)
- ✅ KEV: Available (populated by CISA KEV agent)
- ✅ CWE: Available (populated by CWE agent)
- ✅ CAPEC: Available (populated by CAPEC agent)
- ✅ ATT&CK: Available (populated by ATT&CK agent)
- ✅ Regulatory Requirements: Available (populated by regulatory agents)
- ✅ NIST 800-53: Available (populated by NIST OSCAL agent)

**Assumption:** Reference database is already populated with data from Phase 0 agents.

---

## 2. Phase 1 Code Structure Investigation

### 2.1 Existing Repositories

**Location:** `src/api/repositories/`

**Files:**
1. `base.py` - BaseRepository (CRUD operations)
2. `scan.py` - ScanSessionRepository, ScanFindingRepository (Phase 1)
3. `component.py` - ComponentRepository (Phase 1)
4. `vulnerability.py` - VulnerabilityRepository (placeholder, needs implementation)

**Repository Pattern:**
- Model-Dict Adapter Pattern (models ↔ dicts at DB boundary)
- Methods return Pydantic models (not dicts)
- Uses ArangoDB Python driver for queries

**Code Quality:** ✅ Clean, follows SOLID principles

---

### 2.2 Existing Services

**Location:** `src/api/services/`

**Files:**
1. `base.py` - BaseGraphService (base class)
2. `scan.py` - ScanIngestionService (Phase 1)

**Service Pattern:**
- Model-First Service Pattern (no dict manipulation)
- Services work entirely with models
- Clean separation: Service → Repository → Database

**Code Quality:** ✅ Clean, well-documented

---

### 2.3 Existing API Structure

**Location:** `src/api/`

**Directories:**
- `core/` - Database, security, config
- `models/` - Request/response models
- `parsers/` - SARIF, CycloneDX parsers
- `repositories/` - Data access layer
- `services/` - Business logic layer
- `v1/` - API endpoints

**API Endpoint Pattern (from Phase 1):**
```python
# src/api/v1/endpoints/scan.py
@router.post("/ingest")
async def ingest_scan(
    scan_request: ScanIngestRequest,
    customer: CustomerProfile = Depends(get_current_customer),
):
    service = ScanIngestionService()
    result = await service.ingest_scan(customer._key, scan_request)
    return result  # FastAPI auto-serializes model to JSON
```

**Code Quality:** ✅ Clean FastAPI structure, ready for new endpoints

---

## 3. Scope Triage

### 3.1 What Needs to Be Built

#### Phase 2a: /v1/enrich Endpoint

**New Files:**
1. `src/api/services/enrichment.py` - EnrichmentService
2. `src/api/repositories/enrichment.py` - EnrichmentRepository (query reference DB)
3. `src/api/v1/endpoints/enrichment.py` - Enrichment endpoints
4. `src/api/models/requests/enrichment.py` - EnrichRequest
5. `src/api/models/responses/enrichment.py` - EnrichResponse

**Implementation Tasks:**
- Create EnrichmentRepository with methods:
  - `get_cve_details(cve_id)` → Vulnerability model
  - `get_latest_epss(cve_id)` → EPSSHistory model
  - `check_kev_status(cve_id)` → Optional[KEVEntry]
  - `get_cwe_chain(cwe_ids)` → List[CWE, CAPEC, ATTACKTechnique]
- Create EnrichmentService with method:
  - `enrich_scan_session(scan_session_id)` → EnrichedFindings
- Create FastAPI endpoint:
  - `POST /v1/enrich` → EnrichedFindings

**Effort:** 3-4 days (Medium complexity)

---

#### Phase 2b: /v1/compact Endpoint

**New Files:**
1. `src/api/services/compaction.py` - CompactionService
2. `src/api/repositories/cwe.py` - CWERepository (CWE hierarchy queries)
3. `src/api/v1/endpoints/compaction.py` - Compaction endpoint (or add to enrichment.py)
4. `src/api/models/requests/compaction.py` - CompactRequest
5. `src/api/models/responses/compaction.py` - CompactResponse

**Implementation Tasks:**
- Create CWERepository with methods:
  - `get_parent_cwe(cwe_id)` → Optional[CWE]
  - `get_cwe_hierarchy(cwe_id)` → List[CWE] (parents up to root)
- Create CompactionService with methods:
  - `deduplicate_findings(findings)` → CompactedFindings
  - `rollup_cwe_hierarchy(findings)` → CompactedFindings with parent CWEs
- Create FastAPI endpoint:
  - `POST /v1/compact` → CompactedFindings

**Effort:** 2-3 days (Medium complexity)

---

#### Phase 2c: /v1/map-controls Endpoint

**New Files:**
1. `src/api/services/control_mapping.py` - ControlMappingService
2. `src/api/repositories/regulatory.py` - RegulatoryRepository (query regulatory requirements)
3. `src/api/v1/endpoints/controls.py` - Control mapping endpoint
4. `src/api/models/requests/controls.py` - MapControlsRequest
5. `src/api/models/responses/controls.py` - ControlMappingsResponse

**Implementation Tasks:**
- Create RegulatoryRepository with methods:
  - `get_requirements_for_cwe(cwe_id, frameworks)` → List[RegulatoryRequirement]
  - `get_controls_for_cwe(cwe_id, frameworks)` → List[OSCALControl | SCFControl]
- Create ControlMappingService with method:
  - `map_findings_to_controls(scan_session_id, frameworks)` → ControlMappings
- Create FastAPI endpoint:
  - `POST /v1/map-controls` → ControlMappings

**Effort:** 2-3 days (Medium complexity)

---

### 3.2 Testing Requirements

**Unit Tests (per endpoint):**
- Repository unit tests (mock DB queries)
- Service unit tests (mock repository)
- FastAPI endpoint unit tests (mock service)

**Integration Tests:**
- End-to-end tests with real database queries
- Performance tests (AC-005: <5s for 100 findings)

**Estimated Test Effort:** 2-3 days

---

### 3.3 Total Effort Estimate

| Component | Files | Complexity | Effort |
|-----------|-------|------------|--------|
| Phase 2a: /v1/enrich | 5 files | Medium | 3-4 days |
| Phase 2b: /v1/compact | 5 files | Medium | 2-3 days |
| Phase 2c: /v1/map-controls | 5 files | Medium | 2-3 days |
| Testing (unit + integration) | 15 test files | Medium | 2-3 days |
| **Total** | **30 files** | **Medium-Large** | **9-13 days** |

**Scope Classification:** **Large** (9-13 days)

---

## 4. Identified Risks & Mitigation

### Risk 1: Reference Database Not Populated

**Likelihood:** Medium
**Impact:** High (enrichment will return empty/null data)

**Investigation:**
- Assumption: Reference DB populated by Phase 0 data ingestion agents
- Need to verify: `vulnerabilities`, `epss_history`, `kev_entries`, `weaknesses` have data

**Mitigation:**
- Stage 2: Add data availability check to requirements
- Stage 6: Add graceful fallback if data missing (AC-004)
- Document dependency on Phase 0 data agents

---

### Risk 2: Performance Issues with Large Scans

**Likelihood:** Medium
**Impact:** Medium (slow enrichment for 1000+ findings)

**Mitigation:**
- AC-005 validates performance (<5s for 100 findings)
- Use batch queries to reference DB (not 1 query per finding)
- Add caching layer (Redis) if needed
- Stage 3: Design with performance in mind

---

### Risk 3: NVD API Rate Limits (Fallback Scenario)

**Likelihood:** Low (using reference DB as primary)
**Impact:** Low (only affects CVEs not in reference DB)

**Mitigation:**
- Use reference DB as primary source (no API calls)
- NVD API as fallback only for missing CVEs
- Consider NVD API key for faster rate limit (50 requests/30s)

---

## 5. Design Decisions

### Decision 1: Enrichment Storage Strategy

**Options:**
1. Store enrichment results in database (persistent)
2. Compute enrichment on-demand (transient)

**Recommendation:** **On-demand computation** (Option 2)

**Rationale:**
- Enrichment data changes frequently (new EPSS scores daily)
- Storing enriched findings creates data duplication
- On-demand ensures freshness
- Can add caching layer later for performance

**Action:** Document in Stage 2 Requirements

---

### Decision 2: CWE Rollup Strategy

**Options:**
1. Roll up to direct parent only
2. Roll up to abstraction level (e.g., Base → Class → Pillar)
3. Configurable rollup depth

**Recommendation:** **Configurable rollup depth** (Option 3)

**Rationale:**
- Different users need different rollup levels
- Security analysts may want Base-level CWEs
- Executives may want Pillar-level summary
- Make it configurable via request parameter

**Action:** Document in Stage 2 Requirements

---

### Decision 3: Control Mapping Framework Support

**Options:**
1. Support all frameworks in reference DB
2. Support subset (NIST 800-53, FDA 524B, ISO 27001)
3. Support custom frameworks via API

**Recommendation:** **Support subset** (Option 2) for Phase 2

**Rationale:**
- Phase 2 MVP should support most common frameworks
- NIST 800-53: Most widely used
- FDA 524B: Medical devices
- ISO 27001: International standard
- Custom frameworks: Defer to Phase 3+

**Action:** Document in Stage 2 Requirements

---

## 6. Open Questions (To Be Resolved in Stage 2)

### Q1: Should enrichment be cached?

**Context:** EPSS scores update daily, KEV catalog updates frequently

**Options:**
- Cache enrichment for 24 hours (Redis)
- No caching (always fresh)
- Cache with configurable TTL

**Action:** Discuss in Stage 2, default to no caching for Phase 2 MVP

---

### Q2: How to handle findings with no CVE ID?

**Context:** SAST findings (secrets, hardcoded credentials) may not have CVE IDs

**Options:**
- Enrich based on CWE only (no CVE details, EPSS, KEV)
- Skip enrichment for non-CVE findings
- Return partial enrichment

**Recommendation:** Enrich based on CWE only (threat intel + controls, no CVE-specific data)

**Action:** Document in Stage 2 Requirements

---

### Q3: Should /v1/compact modify scan_findings collection?

**Context:** Compaction could be stored or computed on-demand

**Options:**
- Modify scan_findings (in-place compaction)
- Return compacted view (read-only)

**Recommendation:** Return compacted view (read-only) - don't modify original findings

**Rationale:**
- Preserves original scan data
- Allows different compaction strategies
- Consistent with on-demand enrichment approach

**Action:** Confirm in Stage 2 Requirements

---

## 7. Investigation Conclusion

### Summary

**All required infrastructure exists:**
- ✅ Reference database models (Vulnerability, CWE, EPSS, KEV, ATT&CK, CAPEC, regulatory)
- ✅ Edge collections for graph traversal
- ✅ Phase 1 API structure (services, repositories, endpoints)
- ✅ Clean architecture ready for extension

**No blockers identified.**

### Scope Triage

**Classification:** **Large** (9-13 days)

**Breakdown:**
- Phase 2a: /v1/enrich (3-4 days)
- Phase 2b: /v1/compact (2-3 days)
- Phase 2c: /v1/map-controls (2-3 days)
- Testing (2-3 days)

**Justification for Large:**
- 3 new API endpoints with complex business logic
- 30 new files (5 repositories, 5 services, 5 endpoints, 15 tests)
- Graph traversal queries (CVE → CWE → CAPEC → ATT&CK → Controls)
- Performance optimization required (AC-005)
- Comprehensive testing needed

### Next Steps

1. ✅ Stage 1 Investigation complete
2. ➡️ Move to Stage 2: Refine requirements to Design-ready
   - Resolve open questions (Q1-Q3)
   - Add data availability checks
   - Specify caching strategy
   - Define exact API contracts (request/response schemas)
   - Update acceptance criteria with specific test cases

---

## 8. Files to Investigate Further (Stage 2+)

**For detailed design (Stage 3):**
- `src/api/repositories/vulnerability.py` - Check if VulnerabilityRepository exists and needs extension
- `src/api/core/database.py` - Check customer DB vs reference DB access patterns
- `src/complira_graph/queries/` - Check if reusable AQL queries exist

**For implementation (Stage 6):**
- Phase 1 test files - Use as templates for Phase 2 tests
- `src/api/services/base.py` - Understand BaseGraphService pattern

---

**Investigation Complete:** 2026-03-03
**Next Stage:** Stage 2 (Requirements Refinement)
