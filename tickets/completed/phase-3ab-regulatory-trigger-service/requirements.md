# Phase 3A-B: RegulatoryTriggerService - Requirements

**Ticket:** phase-3ab-regulatory-trigger-service
**Status:** Design-ready v2
**Date:** 2026-03-05 (Updated after Stage 1 investigation)
**Parent Ticket:** phase-3-vulncheck-integration (completed)
**Scope:** SMALL (3-5 days, ~8-10 files)
**Target Audience:** Medical device manufacturers (FDA 524B), automotive (CRA), ICS/OT

---

## Business Context

### Problem Statement

**Phase 3A delivered VulnCheck exploit intelligence** (KEV, NVD2, ransomware attribution, exploit chains) but left **AC10 deferred**: automatic regulatory trigger generation.

**Current State:**
- ✅ VulnCheck KEV data ingested (4,609 entries)
- ✅ Exploit intelligence schema ready (exploit_intelligence, ransomware_families, exploit_chains)
- ✅ `vuln_triggers_requirement` edge collection exists
- ❌ **No automatic edge creation** - Graph cannot answer "Which regulations require this CVE?"
- ❌ **Manual regulatory mapping** - Compliance analysts must manually research each CVE
- ❌ **No POST /v1/enrich merge logic** - Phase 2 (NVD) + Phase 3A (VulnCheck) data not merged

**Gap:**
Without automatic regulatory trigger generation, the knowledge graph cannot:
1. Answer "Which FDA/CRA requirements are triggered by CVE-2024-1234?"
2. Calculate regulatory blast radius for a given CVE
3. Provide defensible audit trail for regulatory submissions
4. Prioritize CVEs by regulatory urgency (24h KEV response vs 90-day standard)

---

### Business Value

**For Medical Device Manufacturers (FDA 524B):**
- **Automatic KEV urgency detection** - FDA requires 24h response to KEV-listed CVEs
- **Exploit intelligence prioritization** - Focus on weaponized/actively exploited CVEs first
- **Audit trail** - Defensible evidence chain (CVE → Exploit Intelligence → Regulatory Requirement)

**For Automotive Manufacturers (CRA - Cyber Resilience Act):**
- **Critical vulnerability response** - CRA requires 24h notification for actively exploited vulnerabilities
- **Exploit chain detection** - Multi-CVE attack sequences require special attention
- **Ransomware attribution** - Ransomware-exploited CVEs have elevated regulatory urgency

**For All Customers:**
- **Reduced manual effort** - Automated regulatory mapping vs manual research (15-30 min/CVE → <1 second)
- **Consistent policy application** - Algorithmic rules vs human judgment
- **Scalability** - Handle 1,000+ CVEs per SBOM automatically

---

## Goal

**Build RegulatoryTriggerService** to automatically generate `vuln_triggers_requirement` edges based on VulnCheck exploit intelligence.

**Inputs:**
- VulnCheck KEV entries (vulncheck_kev_entries collection)
- Exploit intelligence (exploit_intelligence collection)
- Ransomware families (ransomware_families collection)
- Exploit chains (exploit_chains collection)
- CVSS scores (from vulnerabilities collection)
- Regulatory requirements (regulatory_requirements collection)

**Outputs:**
- `vuln_triggers_requirement` edges connecting CVEs to regulatory requirements
- Trigger metadata (trigger_rule, urgency, confidence, evidence)
- Audit trail (trigger_timestamp, trigger_source)

---

## In-Scope Use Cases

### UC-1: KEV Entry Triggers Regulatory Requirement

**Actor:** RegulatoryTriggerService (automated)

**Flow:**
1. Service detects new KEV entry in `vulncheck_kev_entries`
2. Service queries for FDA 524B KEV requirement (if exists)
3. Service creates `vuln_triggers_requirement` edge:
   - `_from`: vulnerabilities/CVE_2024_1234
   - `_to`: regulatory_requirements/FDA_524B_KEV_RESPONSE
   - `trigger_rule`: "kev_entry"
   - `urgency`: "24h"
   - `confidence`: 1.0
   - `evidence`: {"source": "vulncheck_kev", "date_added": "2024-03-05"}

**Success Criteria:**
- All 4,609 KEV entries trigger FDA/CRA regulatory requirements
- Edges created within 5 seconds per CVE
- No duplicate edges

---

### UC-2: CVSS 9.0+ Triggers High Urgency Requirement

**Actor:** RegulatoryTriggerService (automated)

**Flow:**
1. Service queries for CVEs with `cvss_v3_score >= 9.0`
2. Service queries for CRA/FDA critical vulnerability requirements
3. Service creates `vuln_triggers_requirement` edge:
   - `trigger_rule`: "cvss_critical"
   - `urgency`: "high"
   - `confidence`: 0.95
   - `evidence`: {"cvss_v3_score": 9.8}

**Success Criteria:**
- All CVSS 9.0+ CVEs trigger high urgency requirements
- Edge metadata includes CVSS score

---

### UC-3: Ransomware Exploitation Triggers Critical Urgency

**Actor:** RegulatoryTriggerService (automated)

**Flow:**
1. Service queries for CVEs in `exploited_by_ransomware` edges
2. Service queries for CRA ransomware response requirements
3. Service creates `vuln_triggers_requirement` edge:
   - `trigger_rule`: "ransomware_exploitation"
   - `urgency`: "critical"
   - `confidence`: 0.98
   - `evidence`: {"ransomware_family": "LockBit", "source": "vulncheck"}

**Success Criteria:**
- All ransomware-exploited CVEs trigger critical urgency requirements
- Edge metadata includes ransomware family name

---

### UC-4: Exploit Chain Triggers Critical Urgency

**Actor:** RegulatoryTriggerService (automated)

**Flow:**
1. Service queries for CVEs in exploit chains
2. Service queries for CRA exploit chain requirements
3. Service creates `vuln_triggers_requirement` edge:
   - `trigger_rule`: "exploit_chain"
   - `urgency`: "critical"
   - `confidence`: 0.95
   - `evidence`: {"chain_name": "ProxyShell", "chain_position": 1}

**Success Criteria:**
- All exploit chain CVEs trigger critical urgency requirements
- Edge metadata includes chain name and position

---

### UC-5: POST /v1/enrich Merges Phase 2 + Phase 3A Data

**Actor:** API Consumer (compliance analyst)

**Flow:**
1. User sends POST /v1/enrich with `{"cve_id": "CVE-2024-1234"}`
2. Service queries:
   - Phase 2: NVD/GHSA vulnerability data
   - Phase 3A: VulnCheck exploit intelligence
   - Phase 3A-B: Triggered regulatory requirements
3. Service returns merged response:
   ```json
   {
     "cve_id": "CVE-2024-1234",
     "nvd_data": {...},
     "exploit_intelligence": {
       "in_kev": true,
       "exploit_maturity": "weaponized",
       "ransomware_families": ["LockBit"],
       "exploit_chains": ["ProxyShell"]
     },
     "regulatory_triggers": [
       {
         "framework": "FDA 524B",
         "requirement": "KEV Response",
         "urgency": "24h",
         "trigger_rule": "kev_entry",
         "evidence": {...}
       }
     ]
   }
   ```

**Success Criteria:**
- Response includes all Phase 2 + Phase 3A data
- Response includes triggered regulatory requirements
- Response time < 500ms

---

## Acceptance Criteria

### Functional Requirements

**AC1: RegulatoryTriggerService Implementation**
- ✅ Service scans for CVEs matching trigger rules
- ✅ Service creates `vuln_triggers_requirement` edges
- ✅ Service includes trigger metadata (rule, urgency, confidence, evidence)
- ✅ Service is idempotent (no duplicate edges)

**AC2: Trigger Rule 1 - KEV Entry**
- ✅ All KEV entries trigger FDA/CRA KEV response requirements
- ✅ Urgency: 24h
- ✅ Confidence: 1.0
- ✅ Evidence: VulnCheck KEV metadata

**AC3: Trigger Rule 2 - CVSS 9.0+**
- ✅ All CVSS 9.0+ CVEs trigger high urgency requirements
- ✅ Urgency: high
- ✅ Confidence: 0.95
- ✅ Evidence: CVSS score

**AC4: Trigger Rule 3 - Ransomware Exploitation**
- ✅ All ransomware-exploited CVEs trigger critical urgency requirements
- ✅ Urgency: critical
- ✅ Confidence: 0.98
- ✅ Evidence: Ransomware family name

**AC5: Trigger Rule 4 - Exploit Chain**
- ✅ All exploit chain CVEs trigger critical urgency requirements
- ✅ Urgency: critical
- ✅ Confidence: 0.95
- ✅ Evidence: Chain name + position

**AC6: POST /v1/enrich Endpoint**
- ✅ Endpoint merges Phase 2 (NVD) + Phase 3A (VulnCheck) data
- ✅ Endpoint includes triggered regulatory requirements
- ✅ Response time < 500ms
- ✅ Handles missing CVE gracefully (404 Not Found)

**AC7: Unit Tests**
- ✅ All trigger rules tested
- ✅ Edge creation logic tested
- ✅ Idempotency tested (no duplicate edges)
- ✅ Evidence metadata validated

**AC8: Integration Tests**
- ✅ Full service execution (scan + generate edges)
- ✅ POST /v1/enrich endpoint tested
- ✅ Edge count validated (e.g., 4,609 KEV edges created)

---

### Non-Functional Requirements

**Performance:**
- Trigger generation: < 10 seconds per 1,000 CVEs
- POST /v1/enrich: < 500ms response time
- Batch processing: Support 100,000+ CVEs

**Scalability:**
- Idempotent (can run multiple times without duplicates)
- Incremental (only process new CVEs)
- Supports checkpointing (resume on failure)

**Reliability:**
- Graceful degradation (if regulatory requirements missing, log warning but continue)
- Retry logic for database operations
- Structured logging for audit trail

**Maintainability:**
- Trigger rules configurable (add new rules without code changes)
- Clear documentation of rule logic
- Unit tests for all rules

---

## Out-of-Scope

**Not Included in Phase 3A-B:**
- ❌ **Regulatory framework ingestion** (FDA 524B, CRA) - Deferred to Phase 4
  - **Workaround:** Create placeholder requirements for testing
  - **Example:** `regulatory_requirements/FDA_524B_KEV_RESPONSE`

- ❌ **Custom trigger rules** (user-defined rules) - Deferred to future enhancement
  - **Workaround:** Hardcode 4 rules in v1.0

- ❌ **Trigger rule priorities** (conflict resolution) - Deferred to future enhancement
  - **Workaround:** Allow multiple edges (one per trigger rule)

- ❌ **Historical trigger tracking** (when was edge created/updated) - Deferred to future enhancement
  - **Workaround:** Include `trigger_timestamp` in edge metadata

---

## Dependencies

### Phase 3A (Completed) ✅
- ✅ VulnCheck KEV data ingested
- ✅ Exploit intelligence schema ready
- ✅ `vuln_triggers_requirement` edge collection created

### Phase 4 (Not Started) ⏸️
- ⏸️ Regulatory framework ingestion (FDA 524B, CRA)
- **Workaround:** Create placeholder requirements for testing

### Infrastructure (Existing) ✅
- ✅ ArangoDB connection
- ✅ Database schema (5 Phase 3A collections)
- ✅ HTTP client utilities

---

## Open Questions

**Q1: Should trigger rules be configurable (YAML/JSON) or hardcoded?**
- **Status:** `Resolved`
- **Decision:** Hardcode 4 rules in v1.0, defer configurability to v2.0
- **Rationale:** Simpler implementation, sufficient for Phase 3A-B scope

**Q2: How to handle missing regulatory requirements (Phase 4 not complete)?**
- **Status:** `Resolved`
- **Decision:** Create placeholder requirements for testing
- **Example:** `regulatory_requirements/FDA_524B_KEV_RESPONSE` (manually inserted for testing)

**Q3: Should POST /v1/enrich be a new endpoint or extend existing?**
- **Status:** `Resolved`
- **Decision:** New endpoint (POST /v1/enrich)
- **Rationale:** Keeps Phase 2 APIs unchanged, cleaner separation

**Q4: Should we support incremental trigger generation (only new CVEs)?**
- **Status:** `Resolved`
- **Decision:** Yes, use checkpoint file to track last processed CVE
- **Rationale:** Scalability - avoid reprocessing 100K+ CVEs on every run

**Q5: What confidence threshold should trigger edge creation?**
- **Status:** `Resolved`
- **Decision:** No threshold - create edges for all matching CVEs
- **Rationale:** Confidence scores are informational, not filtering criteria

---

## Design Decisions

**D1: Trigger Rule Architecture**
- **Decision:** Hardcode 4 rules in RegulatoryTriggerService
- **Alternative:** YAML configuration file
- **Rationale:** Simpler for v1.0, can refactor to config in v2.0

**D2: Edge Metadata Schema**
- **Decision:** Include trigger metadata in edge attributes
  ```python
  {
      "_from": "vulnerabilities/CVE_2024_1234",
      "_to": "regulatory_requirements/FDA_524B_KEV_RESPONSE",
      "trigger_rule": "kev_entry",
      "urgency": "24h",
      "confidence": 1.0,
      "evidence": {...},
      "trigger_timestamp": "2026-03-05T12:00:00Z",
      "trigger_source": "regulatory_trigger_service_v1"
  }
  ```
- **Rationale:** Full provenance, supports audit trail

**D3: POST /v1/enrich Implementation**
- **Decision:** New FastAPI endpoint in `src/complira_graph/api/enrich.py`
- **Alternative:** Extend existing Phase 2 APIs
- **Rationale:** Cleaner separation, avoids breaking Phase 2 APIs

---

## Risks & Mitigation

**Risk 1: Phase 4 regulatory requirements not available**
- **Impact:** HIGH - Cannot test trigger rules without actual requirements
- **Mitigation:** Create placeholder requirements for testing
- **Contingency:** Mock requirements in unit tests

**Risk 2: VulnCheck paid tier required for full testing**
- **Impact:** MEDIUM - 8 of 9 agents disabled (Community tier)
- **Mitigation:** Trigger rules tested with KEV data only (1/9 agents functional)
- **Contingency:** Unit tests with mocked data

**Risk 3: POST /v1/enrich performance**
- **Impact:** LOW - Response time may exceed 500ms for complex queries
- **Mitigation:** Optimize AQL queries, add caching
- **Contingency:** Increase timeout to 1 second

---

## Success Metrics

**Completion Criteria:**
- ✅ All 8 acceptance criteria passed
- ✅ RegulatoryTriggerService implemented and tested
- ✅ POST /v1/enrich endpoint functional
- ✅ Unit tests passing (100%)
- ✅ Integration tests passing (100%)
- ✅ Documentation complete

**Business Metrics:**
- Regulatory trigger generation time: < 10s per 1,000 CVEs
- POST /v1/enrich response time: < 500ms
- Edge accuracy: 100% (all KEV entries have regulatory edges)

---

## Next Steps (After Requirements Approval)

1. **Stage 1:** Investigation + Triage
   - Review Phase 3A implementation
   - Validate database schema (vuln_triggers_requirement edges)
   - Create placeholder regulatory requirements for testing

2. **Stage 2:** Requirements Refinement
   - Resolve open questions
   - Validate trigger rules with stakeholders
   - Refine POST /v1/enrich API contract

3. **Stage 3-4:** Design + Runtime Modeling
   - Design RegulatoryTriggerService architecture
   - Model runtime call stacks for trigger generation
   - Design POST /v1/enrich endpoint

4. **Stage 5:** Review Gate
   - Two-round review
   - Go/No-Go decision

5. **Stage 6-10:** Implementation → Testing → Review → Docs → Handoff

---

**Document Version:** 2.0 Design-ready
**Created:** 2026-03-05
**Updated:** 2026-03-05 (Stage 1 investigation complete)
**Status:** Design-ready - Validated by Stage 1 investigation, all dependencies confirmed, scope triaged to SMALL (3-5 days, ~1,100-1,500 lines), ready for Stage 3 (Design Basis)
