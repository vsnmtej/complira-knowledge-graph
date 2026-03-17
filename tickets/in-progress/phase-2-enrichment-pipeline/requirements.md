# Requirements: Phase 2 Enrichment Pipeline

**Status:** `Design-ready`
**Ticket:** phase-2-enrichment-pipeline
**Created:** 2026-03-03
**Last Updated:** 2026-03-03
**Version:** v2 (Design-ready - refined after Stage 1 investigation)

---

## Goal / Problem Statement

**Goal:** Build enrichment pipeline to add vulnerability intelligence, risk context, and regulatory mappings to scan findings, transforming raw scanner output into actionable security intelligence.

**Problem:**
- Phase 1 ingests scan findings but provides no context (CVE details, risk scores, exploitation status)
- Security teams need to manually research each CVE for severity, EPSS, KEV status
- No mapping from vulnerabilities to regulatory requirements (NIST 800-53, FDA 524B)
- Duplicate findings across scans create noise
- No rollup of related CWEs into actionable patterns

**Expected Outcome:**
- `/v1/enrich` endpoint enriches findings with CVE details, EPSS scores, KEV status, CWE/CAPEC/ATT&CK mappings
- `/v1/compact` endpoint deduplicates findings and rolls up CWE hierarchies
- `/v1/map-controls` endpoint maps findings to NIST 800-53, FDA 524B, ISO 27001 controls
- Enriched scan results enable prioritized remediation

---

## In-Scope Use Cases

### UC-001: Enrich Scan Findings with Vulnerability Intelligence
- **Description:** Add CVE details, EPSS scores, KEV status, and threat mappings to scan findings
- **Input:** `scan_session_id` from Phase 1 scan ingestion
- **Primary Path:**
  1. Retrieve scan findings for session
  2. For each finding with CVE ID:
     - Fetch CVE details from reference DB (description, CVSS scores, published date)
     - Fetch EPSS score from reference DB (exploit prediction)
     - Check KEV status from reference DB (active exploitation)
     - Map CVE → CWE → CAPEC → ATT&CK tactics
  3. Return enriched findings with full context
- **Expected Outcome:** API returns findings with risk context, enabling prioritization

### UC-002: Compact Scan Findings (Deduplicate + Rollup)
- **Description:** Deduplicate findings and roll up CWE hierarchies to reduce noise
- **Input:** `scan_session_id` or list of `finding_ids`
- **Primary Path:**
  1. Group findings by CVE ID (deduplicate)
  2. Roll up CWE children to parent categories (e.g., CWE-79 XSS variants → CWE-79)
  3. Aggregate locations (list all affected files/components)
  4. Return compacted findings with aggregated metadata
- **Expected Outcome:** Reduced finding count, clearer patterns

### UC-003: Map Findings to Regulatory Controls
- **Description:** Map findings to applicable regulatory requirements (NIST 800-53, FDA 524B, ISO 27001)
- **Input:** `scan_session_id` or list of `cve_ids`
- **Primary Path:**
  1. For each finding, map CVE → CWE
  2. Query reference DB for regulatory requirements mapped to CWE
  3. Return applicable controls grouped by framework
  4. Include control descriptions and implementation guidance
- **Expected Outcome:** Compliance teams can see which controls are affected by vulnerabilities

---

## Out-of-Scope

**Excluded from Phase 2:**
- VulnCheck API integration (deferred to Phase 3)
- Dependency tree analysis (Phase 3)
- Blast radius simulation (Phase 3)
- EPSS velocity alerts (Phase 3)
- Remediation playbooks (Phase 3)
- Natural language queries (Phase 4)
- Defense coverage heatmaps (Phase 3)

**Data Sources (MVP):**
- ✅ Reference DB (vulnerabilities, cwe, capec, attack_techniques, regulatory_requirements)
- ✅ NVD API (CVE details - fallback if not in reference DB)
- ✅ CISA KEV from reference DB
- ✅ EPSS from reference DB
- ❌ VulnCheck API (Phase 3)

---

## Acceptance Criteria

### AC-001: /v1/enrich Endpoint Returns Enriched Findings
- **ID:** AC-001
- **Endpoint:** `POST /v1/enrich`
- **Request:**
  ```json
  {
    "scan_session_id": "session_123"
  }
  ```
- **Response:**
  ```json
  {
    "scan_session_id": "session_123",
    "enriched_findings": [
      {
        "finding_id": "finding_456",
        "cve_id": "CVE-2024-1234",
        "severity": "HIGH",
        "description": "SQL Injection vulnerability",
        "location": "src/app.py:42",
        "enrichment": {
          "cve_details": {
            "description": "Full CVE description...",
            "cvss_v3_score": 9.8,
            "cvss_v3_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
            "published_date": "2024-01-15",
            "references": ["https://nvd.nist.gov/..."]
          },
          "epss": {
            "score": 0.92,
            "percentile": 98.5,
            "date": "2024-03-01"
          },
          "kev_status": {
            "in_kev": true,
            "date_added": "2024-02-01",
            "due_date": "2024-03-01",
            "known_ransomware": false
          },
          "threat_intel": {
            "cwe_id": "CWE-89",
            "cwe_name": "SQL Injection",
            "capec_patterns": ["CAPEC-66"],
            "attack_tactics": ["TA0001 Initial Access", "TA0002 Execution"]
          }
        }
      }
    ],
    "summary": {
      "total_findings": 25,
      "enriched_count": 20,
      "kev_count": 3,
      "high_epss_count": 5
    }
  }
  ```
- **Expected Outcome:** Findings enriched with CVE details, EPSS, KEV, CWE/CAPEC/ATT&CK
- **Testable:**
  - Unit test: Enrichment service adds CVE details from reference DB
  - Unit test: EPSS scores fetched correctly
  - Unit test: KEV status checked
  - Integration test: POST /v1/enrich returns enriched findings
- **Status:** Not Started

### AC-002: /v1/compact Endpoint Deduplicates Findings
- **ID:** AC-002
- **Endpoint:** `POST /v1/compact`
- **Request:**
  ```json
  {
    "scan_session_id": "session_123",
    "options": {
      "deduplicate_by": "cve_id",
      "rollup_cwe": true
    }
  }
  ```
- **Response:**
  ```json
  {
    "scan_session_id": "session_123",
    "compacted_findings": [
      {
        "cve_id": "CVE-2024-1234",
        "severity": "HIGH",
        "occurrence_count": 5,
        "locations": [
          "src/app.py:42",
          "src/api.py:100",
          "src/utils.py:25"
        ],
        "cwe_rollup": {
          "parent_cwe": "CWE-89",
          "child_cwes": ["CWE-89.1", "CWE-89.2"]
        }
      }
    ],
    "summary": {
      "original_count": 25,
      "compacted_count": 8,
      "reduction_percentage": 68
    }
  }
  ```
- **Expected Outcome:** Findings deduplicated by CVE ID, CWEs rolled up to parent categories
- **Testable:**
  - Unit test: Deduplication logic groups by CVE ID
  - Unit test: CWE rollup follows CWE hierarchy
  - Integration test: POST /v1/compact returns compacted findings
- **Status:** Not Started

### AC-003: /v1/map-controls Endpoint Maps to Regulatory Requirements
- **ID:** AC-003
- **Endpoint:** `POST /v1/map-controls`
- **Request:**
  ```json
  {
    "scan_session_id": "session_123",
    "frameworks": ["nist_800_53", "fda_524b", "iso_27001"]
  }
  ```
- **Response:**
  ```json
  {
    "scan_session_id": "session_123",
    "control_mappings": [
      {
        "cve_id": "CVE-2024-1234",
        "cwe_id": "CWE-89",
        "frameworks": {
          "nist_800_53": [
            {
              "control_id": "SI-10",
              "control_name": "Information Input Validation",
              "description": "Check the validity of information inputs."
            }
          ],
          "fda_524b": [
            {
              "control_id": "SEC-002",
              "control_name": "Secure Coding Practices",
              "description": "Implement input validation to prevent injection attacks."
            }
          ]
        }
      }
    ],
    "summary": {
      "total_findings": 25,
      "findings_with_mappings": 20,
      "unique_controls_affected": {
        "nist_800_53": 12,
        "fda_524b": 8,
        "iso_27001": 10
      }
    }
  }
  ```
- **Expected Outcome:** Findings mapped to regulatory controls via CVE → CWE → Controls
- **Testable:**
  - Unit test: CVE → CWE mapping works
  - Unit test: CWE → Controls query returns correct controls
  - Integration test: POST /v1/map-controls returns control mappings
- **Status:** Not Started

### AC-004: Enrichment Service Handles Missing Data and Non-CVE Findings Gracefully
- **ID:** AC-004
- **Expected Outcome:** Service handles cases where CVE details, EPSS, or KEV data is missing, and enriches non-CVE findings based on CWE
- **Test Cases:**
  - **TC-004a:** Enrichment continues if EPSS data missing (returns null in epss field)
  - **TC-004b:** Enrichment continues if KEV status missing (returns in_kev: false)
  - **TC-004c:** Enrichment continues if CVE not in reference DB (returns null for cve_details, continues with CWE-based enrichment)
  - **TC-004d:** Non-CVE finding (SAST secret detection) enriched based on CWE only
    - Input: Finding with CWE-798 (hardcoded credentials), no CVE ID
    - Output: Enrichment with threat_intel (CWE → CAPEC → ATT&CK) but no CVE details/EPSS/KEV
  - **TC-004e:** Finding with invalid CWE ID (enrichment returns partial data)
- **Testable:**
  - Unit test: Enrichment with missing EPSS data
  - Unit test: Enrichment with missing KEV data
  - Unit test: Enrichment with CVE not in reference DB
  - Unit test: Non-CVE finding enriched via CWE only (TC-004d)
  - Integration test: End-to-end enrichment with mixed CVE/non-CVE findings
- **Status:** Not Started

### AC-005: Performance - Enrichment Completes Within SLA
- **ID:** AC-005
- **Expected Outcome:** Enrichment of 100 findings completes within 5 seconds
- **Testable:**
  - Performance test: Enrich 100 findings < 5 seconds
  - Performance test: Enrich 1000 findings < 30 seconds
- **Status:** Not Started

---

## Constraints / Dependencies

### Technical Constraints
- Must work with existing Phase 1 scan ingestion (scan_sessions, scan_findings)
- Must query reference database (vulnerabilities, cwe, capec, attack_techniques, regulatory_requirements)
- Must handle missing data gracefully (not all CVEs have EPSS, KEV data)
- Must not modify scan_findings collection (enrichment is additive, not in-place)

### Dependencies
- Phase 1 scan ingestion complete (scan_sessions, scan_findings) ✅
- Reference database populated with:
  - Vulnerabilities (CVE data)
  - EPSS history
  - KEV entries
  - CWE catalog
  - CAPEC patterns
  - ATT&CK techniques
  - Regulatory requirements (NIST 800-53, FDA 524B, etc.)
- NVD API (fallback for CVE details not in reference DB)

---

## Assumptions (Validated in Stage 1)

1. **Reference database is populated:** ✅ Vulnerabilities, CWE, CAPEC, ATT&CK, regulatory requirements exist (confirmed in investigation)
2. **Phase 1 scan ingestion works:** ✅ Can retrieve findings via scan_session_id (ScanSessionRepository, ScanFindingRepository exist)
3. **No caching for MVP:** ✅ Compute enrichment on-demand (Decision D1)
4. **Enrichment is read-only:** ✅ Does not modify scan_findings, returns enriched data in response (Decision D2)
5. **Single customer testing:** ✅ Can test with one customer profile
6. **All required edge collections exist:** ✅ Confirmed 26 edge collections available (has_weakness, has_epss, exploited_in_wild, capec_relates_to_cwe, capec_maps_to_attack, maps_to_requirement, etc.)

---

## Decisions (Resolved in Stage 1-2)

### D1: Enrichment Caching Strategy
- **Decision:** No caching for Phase 2 MVP ✅
- **Rationale:**
  - Keep implementation simple for MVP
  - EPSS scores update daily, caching may serve stale data
  - Can add Redis caching in Phase 3 if performance testing shows need
- **Implementation:** Compute enrichment on-demand for every request

### D2: Compaction Strategy
- **Decision:** Read-only compaction (return compacted view, don't modify scan_findings) ✅
- **Rationale:**
  - Preserves original scan data
  - Allows different compaction strategies per request
  - Consistent with on-demand enrichment approach
- **Implementation:** /v1/compact returns compacted findings, does not update database

### D3: Non-CVE Finding Enrichment
- **Decision:** Enrich based on CWE only (for non-CVE findings) ✅
- **Rationale:**
  - SAST findings (secrets, hardcoded credentials) have CWE but no CVE
  - Can still provide threat intel (CWE → CAPEC → ATT&CK) and control mappings
  - CVE-specific enrichment (EPSS, KEV) not applicable
- **Implementation:**
  - If finding has CVE ID: Full enrichment (CVE details + EPSS + KEV + threat intel)
  - If finding has no CVE ID: Partial enrichment (threat intel via CWE only)

### D4: Custom Framework Support
- **Decision:** Built-in frameworks only for Phase 2 ✅
- **Scope:** NIST 800-53, FDA 524B, ISO 27001 supported
- **Custom frameworks:** Deferred to Phase 3+
- **Rationale:** MVP focuses on most common compliance frameworks

## Open Questions / Risks

### Remaining Open Questions
(None - all questions resolved in Stage 1-2)

### Risks
1. **Risk-001:** Reference database missing data (EPSS, KEV, regulatory mappings)
   - **Likelihood:** Medium
   - **Impact:** High (enrichment incomplete)
   - **Mitigation:**
     - Stage 1: Investigate reference DB coverage
     - Ensure Phase 0 data workers populated reference DB
     - Add data quality checks

2. **Risk-002:** NVD API rate limits (10 requests/minute without API key)
   - **Likelihood:** High if using NVD API heavily
   - **Impact:** Medium (slow enrichment)
   - **Mitigation:**
     - Use reference DB as primary source
     - NVD API as fallback only
     - Consider NVD API key (faster rate limit)

3. **Risk-003:** Performance issues with large scans (1000+ findings)
   - **Likelihood:** Medium
   - **Impact:** Medium (slow enrichment)
   - **Mitigation:**
     - Batch DB queries
     - Add caching layer (Redis)
     - AC-005 validates performance

---

## Triage Result (Confirmed in Stage 1)

**Scope:** `Large` ✅

**Effort Estimate:** 9-13 days (30 files)

**Breakdown:**
| Component | Files | Complexity | Effort |
|-----------|-------|------------|--------|
| Phase 2a: /v1/enrich | 5 files | Medium | 3-4 days |
| Phase 2b: /v1/compact | 5 files | Medium | 2-3 days |
| Phase 2c: /v1/map-controls | 5 files | Medium | 2-3 days |
| Testing (unit + integration + performance) | 15 test files | Medium | 2-3 days |
| **Total** | **30 files** | **Medium-Large** | **9-13 days** |

**Rationale for Large:**
- 3 new API endpoints with complex business logic
- 30 new files (repositories, services, endpoints, tests)
- Graph traversal queries (CVE → CWE → CAPEC → ATT&CK → Controls)
- Performance optimization required (AC-005: <5s for 100 findings)
- Comprehensive testing (unit + integration + performance)

**Investigation Findings:**
- ✅ All required data models exist (Vulnerability, CWE, EPSS, KEV, ATT&CK, CAPEC, Regulatory)
- ✅ All required edge collections exist (has_weakness, has_epss, exploited_in_wild, etc.)
- ✅ Phase 1 API structure ready for extension
- ✅ No blockers identified

---

## Data Sources (Phase 2 MVP)

### Primary: Reference Database
- `vulnerabilities` - CVE details, CVSS scores, published dates
- `epss_history` - EPSS scores (exploit prediction)
- `kev_entries` - CISA KEV (known exploited vulnerabilities)
- `weaknesses` - CWE catalog with hierarchy
- `attack_patterns` - CAPEC patterns
- `attack_techniques` - MITRE ATT&CK tactics/techniques
- `regulatory_requirements` - NIST 800-53, FDA 524B, ISO 27001, etc.

### Edges Required
- `cve_to_cwe` - CVE → CWE mapping
- `cwe_to_capec` - CWE → CAPEC mapping
- `capec_to_attack` - CAPEC → ATT&CK mapping
- `cwe_to_controls` - CWE → Regulatory requirements mapping
- `has_epss` - Vulnerability → EPSS score
- `in_kev` - Vulnerability → KEV entry

### Fallback: NVD API
- Used only if CVE not found in reference DB
- Rate-limited (10 requests/min without API key)

---

## Change History

| Date | Version | Changes | Status |
|------|---------|---------|--------|
| 2026-03-03 | v1 | Initial draft for Phase 2 Enrichment Pipeline | Draft |
| 2026-03-03 | v2 | Refined after Stage 1 investigation - scope confirmed Large (9-13 days, 30 files), all open questions resolved (D1-D4), AC-004 updated for non-CVE findings, assumptions validated | Design-ready |
