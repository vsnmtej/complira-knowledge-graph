# API / E2E Testing — org-data-kg-integration

**Stage:** 7
**Date:** 2026-04-14

---

## Acceptance Criteria Matrix

| AC ID | Description | Scenario IDs | Execution Status |
| --- | --- | --- | --- |
| AC-001 | Device nodes written with only compliance-relevant fields | S-001, S-002 | Passed |
| AC-002 | device_has_vulnerability edge links device to CVE | S-003, S-010, S-011 | Passed |
| AC-003 | threat_detections node has cve_id, technique_id, ttl_expires | S-004 | Passed |
| AC-004 | exploited_by edge has ttl_expires ≤ NOW+48h | S-005, S-006 | Passed |
| AC-005 | network_exposure edge for pump-api-prod-01, internet_facing=true, provider=crowdstrike | S-007 | Passed |
| AC-006 | access_event for Sarah Hoffmann, control_type=mfa_enrollment, FDA_524B_4_2 | S-008, S-009 | Passed |
| AC-007 | Jira+PD incidents cross-linked with CVE-2023-38408, regulatory_labels | S-012, S-013, S-014 | Passed |
| AC-008 | Cross-layer AQL traversal returns CRA Art.14 evidence row | S-015 | **Blocked (Infeasible)** |
| AC-009 | TTL enforcement — stale edges expired, VEX refresh flagged | S-016 | **Blocked (Infeasible)** |
| AC-010 | No CVE metadata duplication in any connector output | S-002, S-004, S-010, S-011, S-012 | Passed |

---

## Scenario Results

### S-001 — Device compliance fields (AC-001)
- **Requirement:** UC-001 / AC-001
- **Source:** Requirement
- **Level:** Unit
- **Expected:** devices collection has hostname, instance_id, internet_facing, public_ports, containment_status, tenant_id; no cvss3_base_score/cwe_ids/descriptions
- **Command:** `pytest tests/unit/connectors/test_crowdstrike_connector.py::TestDeviceNodes`
- **Result:** Passed

### S-002 — No prohibited fields in device/detection nodes (AC-010)
- **Requirement:** UC-001 / AC-010
- **Source:** Requirement
- **Level:** Unit
- **Expected:** No cvss3_base_score, cwe_ids, description, cvss_vector in any connector output
- **Command:** `pytest tests/unit/connectors/ -k "prohibited"`
- **Result:** Passed

### S-003 — CrowdStrike device_has_vulnerability edge (AC-002)
- **Requirement:** UC-001 / AC-002
- **Source:** Requirement
- **Level:** Unit
- **Expected:** Edge _from=devices/pump_api_prod_01, _to=vulnerabilities/CVE-2023-38408
- **Command:** `pytest tests/unit/connectors/test_crowdstrike_connector.py::TestDeviceHasVulnerability`
- **Result:** Passed

### S-004 — threat_detections node fields (AC-003)
- **Requirement:** UC-002 / AC-003
- **Source:** Requirement
- **Level:** Unit
- **Expected:** cve_id=CVE-2023-38408, technique_id=T1203, ttl_expires present
- **Command:** `pytest tests/unit/connectors/test_crowdstrike_connector.py::TestThreatDetections`
- **Result:** Passed

### S-005 — exploited_by edge TTL (AC-004)
- **Requirement:** UC-002 / AC-004
- **Source:** Requirement
- **Level:** Unit
- **Expected:** ttl_expires ≤ NOW+48h
- **Command:** `pytest tests/unit/connectors/test_crowdstrike_connector.py::TestExploitedBy`
- **Result:** Passed

### S-006 — Base TTL helpers (AC-004)
- **Requirement:** UC-002 / AC-004
- **Source:** Design-Risk
- **Level:** Unit
- **Expected:** exploit_ttl() returns valid ISO timestamp ≤ NOW+48h; device_ttl() is future
- **Command:** `pytest tests/unit/connectors/test_connector_base.py::TestTTLHelpers`
- **Result:** Passed

### S-007 — network_exposure edge for internet-facing host (AC-005)
- **Requirement:** UC-003 / AC-005
- **Source:** Requirement
- **Level:** Unit
- **Expected:** One network_exposure edge for pump-api-prod-01 with internet_facing=true, provider=crowdstrike
- **Command:** `pytest tests/unit/connectors/test_crowdstrike_connector.py::TestNetworkExposure`
- **Result:** Passed

### S-008 — Okta MFA gap access_event (AC-006)
- **Requirement:** UC-004 / AC-006
- **Source:** Requirement
- **Level:** Unit
- **Expected:** access_events entry with control_type=mfa_enrollment, control_status=not_enrolled, framework_requirement_id=FDA_524B_4_2
- **Command:** `pytest tests/unit/connectors/test_okta_connector.py::TestMFAGapRecording`
- **Result:** Passed

### S-009 — Okta: enrolled users produce no events
- **Requirement:** UC-004 / AC-006
- **Source:** Design-Risk
- **Level:** Unit
- **Expected:** Users with enrolled MFA produce no access_events
- **Command:** `pytest tests/unit/connectors/test_okta_connector.py::TestMFAGapRecording::test_no_event_for_enrolled_user`
- **Result:** Passed

### S-010 — Tenable device_has_vulnerability edge (AC-002, AC-010)
- **Requirement:** UC-001 / AC-002, AC-010
- **Source:** Requirement
- **Level:** Unit
- **Expected:** Edge _to=vulnerabilities/CVE-2023-38408; no prohibited fields
- **Command:** `pytest tests/unit/connectors/test_tenable_qualys_connectors.py::TestTenableConnector`
- **Result:** Passed

### S-011 — Qualys device_has_vulnerability edge (AC-002, AC-010)
- **Requirement:** UC-001 / AC-002, AC-010
- **Source:** Requirement
- **Level:** Unit
- **Expected:** Edge _to=vulnerabilities/CVE-2023-38408 via QID→CVE map; no prohibited fields
- **Command:** `pytest tests/unit/connectors/test_tenable_qualys_connectors.py::TestQualysConnector`
- **Result:** Passed

### S-012 — Jira incident cross-linked with CVE (AC-007, AC-010)
- **Requirement:** UC-005 / AC-007, AC-010
- **Source:** Requirement
- **Level:** Unit
- **Expected:** incident cve_id=CVE-2023-38408; regulatory_labels includes cra-article-14, fda-524b
- **Command:** `pytest tests/unit/connectors/test_jira_pagerduty_connector.py::TestJiraConnector`
- **Result:** Passed

### S-013 — PagerDuty incident cross-linked with CVE (AC-007)
- **Requirement:** UC-005 / AC-007
- **Source:** Requirement
- **Level:** Unit
- **Expected:** PD incident cve_id=CVE-2023-38408, hostname=pump-api-prod-01
- **Command:** `pytest tests/unit/connectors/test_jira_pagerduty_connector.py::TestPagerDutyConnector`
- **Result:** Passed

### S-014 — Connector registry completeness
- **Requirement:** UC-001 / AC-001
- **Source:** Design-Risk
- **Level:** Unit
- **Expected:** CONNECTOR_REGISTRY has all 8 source tools
- **Command:** `pytest tests/unit/connectors/test_connector_base.py::TestConnectorRegistry`
- **Result:** Passed

### S-015 — Cross-layer AQL traversal (AC-008)
- **Requirement:** UC-006 / AC-008
- **Source:** Requirement
- **Level:** API (Integration)
- **Expected:** AQL query returns cve_id, host, blast_radius_score, cra_deadline, evidence_sources
- **Infeasibility:** Requires live ArangoDB with all 9 new collections populated. Not executable in unit test environment.
- **Compensating evidence:** AQL query in deployment_reality_queries.py reviewed; correct cross-collection traversal with FILTER tenant_id==@tenant_id and regulatory constraint joins verified by code inspection + import test.
- **Result:** **Blocked (Infeasible)**

### S-016 — TTL enforcement nightly flow (AC-009)
- **Requirement:** UC-007 / AC-009
- **Source:** Requirement
- **Level:** Integration
- **Expected:** Stale exploited_by edges removed; affected VEX docs flagged requires_refresh=true
- **Infeasibility:** Requires live ArangoDB + Prefect infrastructure. Not executable in unit test environment.
- **Compensating evidence:** ttl_cleanup.py reviewed; AQL DELETE statement for expired edges verified; VEX requires_refresh upsert verified by code inspection + import test.
- **Result:** **Blocked (Infeasible)**

---

## Infeasibility Summary

| AC ID | Reason | Compensating Automated Evidence |
| --- | --- | --- |
| AC-008 | Requires live ArangoDB with full deployment layer populated | AQL query structure + import test passed; connector unit tests verified all input data |
| AC-009 | Requires live ArangoDB + Prefect scheduler | ttl_cleanup.py import test passed; AQL reviewed by code inspection |

**User Waiver Required:** AC-008, AC-009 — both require live ArangoDB integration.

---

## Test Execution Summary

- **Total scenarios:** 16
- **Passed:** 14
- **Blocked (infeasible):** 2 (AC-008, AC-009)
- **Failed:** 0
- **Test command:** `pytest tests/unit/connectors/ -q --no-header --no-cov`
- **Result:** 44 passed, 0 failed
