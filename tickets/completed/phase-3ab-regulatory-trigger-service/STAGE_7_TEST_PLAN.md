# Phase 3A-B: Stage 7 API/E2E Test Plan

**Date:** 2026-03-05
**Stage:** 7 (API/E2E Testing)
**Status:** 🚧 In Progress

---

## Stage 7 Gate Requirement

**Exit Condition:** API/E2E test implementation complete + AC scenario gate complete

**Acceptance Criteria to Validate:**
- AC7: Unit Tests (deferred from Stage 6)
- AC8: Integration Tests (deferred from Stage 6)

**Testing Scope:**
1. Smoke tests (already passing in Stage 6)
2. API/E2E tests with real Phase 2 + Phase 3A data
3. Performance validation
4. Idempotency validation
5. Edge creation verification

---

## Test Plan Overview

### Pre-Test Setup
1. ✅ Verify ArangoDB is running
2. Check Phase 2 vulnerability data availability (vulnerabilities collection)
3. Check Phase 3A KEV data availability (vulncheck_kev_entries collection)
4. Run placeholder requirements insertion script
5. Verify 5 placeholder requirements exist in regulatory_requirements collection

### Test Execution
1. **Service Execution Test**
   - Run RegulatoryTriggerService.run()
   - Verify all 4 trigger rules execute
   - Measure execution time

2. **Edge Creation Test**
   - Verify vuln_triggers_requirement edges created
   - Verify edge metadata (trigger_rule, urgency, confidence, evidence)
   - Count edges by rule (kev_entry, cvss_critical, ransomware_exploitation, exploit_chain)

3. **Idempotency Test**
   - Run RegulatoryTriggerService.run() a 2nd time
   - Verify 0 new edges created
   - Verify edge count remains stable

4. **API Endpoint Test**
   - Test POST /v1/enrich with test CVE IDs
   - Verify response includes nvd_data, exploit_intelligence, regulatory_triggers
   - Verify HTTP 404 for non-existent CVEs
   - Measure API response time

5. **Performance Validation**
   - Rule 1 (KEV): < 10s per 1K CVEs target
   - Rule 2 (CVSS): < 10s per 1K CVEs target
   - POST /v1/enrich: < 500ms target

6. **Statistics Validation**
   - Verify RegulatoryTriggerService.get_statistics() returns correct counts
   - Verify edges_by_rule matches expected distribution
   - Verify edges_by_urgency matches trigger rule urgency mappings

---

## Test Cases

### TC1: Placeholder Requirements Exist
**Precondition:** Database connected
**Steps:**
1. Run `python scripts/insert_placeholder_requirements.py`
2. Query regulatory_requirements collection
**Expected Result:** 5 placeholder requirements exist (FDA_524B_KEV_RESPONSE, CRA_CRITICAL_VULNERABILITY, FDA_524B_CVSS_HIGH, CRA_RANSOMWARE_EXPLOITATION, CRA_EXPLOIT_CHAIN)

### TC2: Phase 2 Vulnerability Data Available
**Precondition:** Database connected
**Steps:**
1. Query vulnerabilities collection for count
**Expected Result:** > 0 vulnerabilities (Phase 2 data populated)

### TC3: Phase 3A KEV Data Available
**Precondition:** Database connected
**Steps:**
1. Query vulncheck_kev_entries collection for count
**Expected Result:** ~4,609 KEV entries (Phase 3A data populated)

### TC4: RegulatoryTriggerService Execution
**Precondition:** TC1, TC2, TC3 pass
**Steps:**
1. Run `python scripts/test_regulatory_trigger_service.py`
**Expected Result:**
- All 4 rules execute successfully
- edges_created > 0 (depends on data availability)
- execution_time < 300s (5 minutes for full dataset)

### TC5: Edge Creation Verification
**Precondition:** TC4 pass
**Steps:**
1. Query vuln_triggers_requirement collection
2. Count edges by trigger_rule
**Expected Result:**
- kev_entry: ~4,609 edges (if Phase 3A KEV data exists)
- cvss_critical: ~15,000-20,000 edges (if Phase 2 CVSS data exists)
- ransomware_exploitation: 0 edges (Community tier, paid tier required)
- exploit_chain: 0 edges (Community tier, paid tier required)

### TC6: Idempotency Validation
**Precondition:** TC4 pass
**Steps:**
1. Run RegulatoryTriggerService.run() a 2nd time
2. Compare edges_created with 1st run
**Expected Result:** edges_created = 0 on 2nd run

### TC7: POST /v1/enrich API Test
**Precondition:** FastAPI app running, TC4 pass
**Steps:**
1. Start FastAPI app: `uvicorn src.main:app --reload`
2. POST /v1/enrich with CVE-2021-44228 (Log4Shell)
3. Verify response structure
**Expected Result:**
- HTTP 200 OK
- Response includes nvd_data, exploit_intelligence, regulatory_triggers
- regulatory_triggers contains >= 1 trigger (KEV + CVSS expected)
- Response time < 500ms

### TC8: POST /v1/enrich 404 Test
**Precondition:** FastAPI app running
**Steps:**
1. POST /v1/enrich with CVE-9999-99999 (non-existent)
**Expected Result:**
- HTTP 404 Not Found
- Error message: "CVE-9999-99999 not found"

### TC9: Performance Validation
**Precondition:** TC4 pass
**Steps:**
1. Measure Rule 1 execution time
2. Calculate time per 1K CVEs (execution_time / (edges_created / 1000))
**Expected Result:**
- Rule 1 (KEV): < 10s per 1K CVEs
- Rule 2 (CVSS): < 10s per 1K CVEs
- POST /v1/enrich: < 500ms

### TC10: Statistics Validation
**Precondition:** TC4 pass
**Steps:**
1. Call RegulatoryTriggerService.get_statistics()
2. Verify total_edges matches sum of edges_by_rule
**Expected Result:**
- total_edges = sum(edges_by_rule.values())
- edges_by_urgency includes 24h, high, critical
- Statistics match expected distribution

---

## Test Environment

**Database:** ArangoDB (localhost:8529)
**Collections Required:**
- vulnerabilities (Phase 2)
- vulncheck_kev_entries (Phase 3A)
- regulatory_requirements (placeholder data)
- vuln_triggers_requirement (edge collection)
- agent_checkpoints (checkpoint storage)

**Data Dependencies:**
- Phase 2: NVD vulnerability data (required for Rule 2)
- Phase 3A: KEV entries (required for Rule 1)
- Placeholder requirements (required for all rules)

---

## Expected Test Results

### Scenario A: No Phase 2 Data (Current State)
- Rule 1 (KEV): 0 edges (no vulnerabilities collection data)
- Rule 2 (CVSS): 0 edges (no CVSS scores)
- Rule 3 (Ransomware): 0 edges (paid tier required)
- Rule 4 (Exploit Chain): 0 edges (paid tier required)
- **Result:** Smoke test only (service executes successfully, 0 edges created)

### Scenario B: Phase 2 + Phase 3A Data Populated
- Rule 1 (KEV): ~4,609 edges
- Rule 2 (CVSS): ~15,000-20,000 edges
- Rule 3 (Ransomware): 0 edges (paid tier required)
- Rule 4 (Exploit Chain): 0 edges (paid tier required)
- **Result:** Full integration test (service creates production-scale edges)

### Scenario C: FastAPI Integration Test
- POST /v1/enrich returns merged data from Phase 2 + Phase 3A + Phase 3A-B
- Regulatory triggers include KEV + CVSS triggers
- API response time < 500ms

---

## Test Execution Log

### Test Run 1: 2026-03-05 (Smoke Test - Stage 6)
- **Result:** ✅ PASS
- **Edges Created:** 0 (no Phase 2 data)
- **Execution Time:** 0.05s
- **Idempotency:** ✅ Verified (0 edges on 2nd run)

### Test Run 2: 2026-03-05 (Stage 7 - TBD)
- **Status:** Pending
- **Expected:** Full integration test with Phase 2 + Phase 3A data

---

## Test Deliverables

1. **Test Execution Report:** STAGE_7_TEST_RESULTS.md
2. **Performance Metrics:** Execution times, edge counts, API response times
3. **Edge Statistics:** Breakdown by rule, urgency, framework
4. **API Test Results:** Sample requests/responses, error handling validation
5. **Idempotency Proof:** Before/after edge counts

---

## Stage 7 Gate Decision Criteria

**PASS:**
- All test cases execute successfully (TC1-TC10)
- Service runs without errors
- Idempotency verified
- API endpoint functional (or waived if FastAPI app setup required)
- Performance within acceptable range (or explained if data-dependent)

**FAIL (Local Fix):**
- Test failures due to code bugs → Re-enter Stage 6

**FAIL (Design Impact):**
- Design flaws discovered → Re-enter Stage 3

**BLOCKED:**
- Missing Phase 2 data prevents meaningful testing
- Requires user decision: waive API tests or populate Phase 2 data first

---

**Document Version:** 1.0
**Created:** 2026-03-05
**Author:** Claude Code (Anthropic)
**Status:** 🚧 Test execution in progress
