# Implementation Plan — org-data-kg-integration

**Status:** Finalized (Stage 5 Go Confirmed)
**Scope:** Large
**Last Updated:** 2026-03-31

---

## Traceability Map

| UC / AC | Design Section | Call Stack | Change Items |
| --- | --- | --- | --- |
| UC-001 / AC-001, AC-002, AC-010 | §OrgConnector pattern, §Connector registry | CS-001, CS-002 | C-001, C-002, C-003, C-004, C-005, C-014 |
| UC-002 / AC-003, AC-004 | §threat_detections schema, §exploited_by edge | CS-003 | C-001, C-004, C-013 |
| UC-003 / AC-005 | §network_exposure edge | CS-004 | C-001, C-004 |
| UC-004 / AC-006 | §access_events schema, §user_lacks_control edge | CS-005 | C-001, C-003, C-007 |
| UC-005 / AC-007 | §incidents schema | CS-006 | C-001, C-008, C-009 |
| UC-006 / AC-008 | §cross-layer AQL proof query | CS-007 | C-013, C-015 |
| UC-007 / AC-009 | §TTL cleanup flow | CS-008 | C-012, C-014 |

---

## Change Inventory (Execution Order)

| Change ID | Type | File | Responsibility | Depends On |
| --- | --- | --- | --- | --- |
| C-001 | Add | `src/complira_graph/schema/complira_kg_schema_v2_3.py` | Schema migration — 4 new vertex + 5 new edge collections | — |
| C-002 | Add | `src/complira_graph/connectors/__init__.py` | Package init; export `OrgConnector` + connector registry | C-001 |
| C-003 | Add | `src/complira_graph/connectors/base.py` | `OrgConnector` ABC: `fetch()`, `extract()`, `upsert_kg()`, `run()` | C-001 |
| C-004 | Add | `src/complira_graph/connectors/crowdstrike.py` | CrowdStrikeConnector — devices + network_exposure + threat_detections | C-003 |
| C-005 | Add | `src/complira_graph/connectors/tenable.py` | TenableConnector — aws_instance_id bridge + device_has_vulnerability | C-003 |
| C-006 | Add | `src/complira_graph/connectors/qualys.py` | QualysConnector — host→CVE edges via QID→CVE mapping | C-003 |
| C-007 | Add | `src/complira_graph/connectors/okta.py` | OktaConnector — MFA enrollment gaps → access_events | C-003 |
| C-008 | Add | `src/complira_graph/connectors/jira.py` | JiraConnector — PSEC tickets → incidents nodes | C-003 |
| C-009 | Add | `src/complira_graph/connectors/pagerduty.py` | PagerDutyConnector — P1 incidents → incidents nodes + cross-link | C-003, C-008 |
| C-010 | Add | `src/complira_graph/connectors/sentinelone.py` | SentinelOneConnector — threat detections + quarantine status | C-003 |
| C-011 | Add | `src/complira_graph/connectors/aws_ec2.py` | AWSEC2Connector — compliance-tagged EC2 → device nodes | C-003 |
| C-012 | Add | `src/complira_graph/orchestrator/ttl_cleanup.py` | Prefect flow — expire stale deployment edges + flag VEX docs | C-001 |
| C-013 | Add | `src/complira_graph/queries/deployment_reality_queries.py` | AQL — cross-layer proof query (CRA Art.14 evidence) | C-001 |
| C-014 | Modify | `src/complira_graph/orchestrator/dag.py` | Add Batch 6: org connector flows + nightly TTL cleanup | C-002–C-012 |
| C-015 | Modify | `src/complira_graph/queries/vex_evidence_queries.py` | Add `get_exploitation_evidence()` with exploited_by traversal | C-001, C-013 |

---

## Implementation Order (Bottom-Up)

### Phase 1 — Schema (must be first, gates everything)
1. **C-001**: `complira_kg_schema_v2_3.py` — creates all new collections in ArangoDB

### Phase 2 — Connector foundation
2. **C-003**: `connectors/base.py` — OrgConnector ABC
3. **C-002**: `connectors/__init__.py` — package + registry

### Phase 3 — Connectors (can parallelize within phase, sequential here for clarity)
4. **C-011**: `aws_ec2.py` — device nodes (prerequisite data for all other connectors)
5. **C-004**: `crowdstrike.py` — device enrichment, network_exposure, threat_detections
6. **C-005**: `tenable.py` — device_has_vulnerability via aws_instance_id bridge
7. **C-006**: `qualys.py` — device_has_vulnerability via QID→CVE
8. **C-010**: `sentinelone.py` — threat_detections + exploited_by
9. **C-007**: `okta.py` — access_events + user_lacks_control
10. **C-008**: `jira.py` — incidents nodes
11. **C-009**: `pagerduty.py` — incidents cross-link

### Phase 4 — TTL + Queries
12. **C-012**: `ttl_cleanup.py` — Prefect nightly flow
13. **C-013**: `deployment_reality_queries.py` — cross-layer AQL

### Phase 5 — Wiring + existing file modifications
14. **C-014**: `dag.py` — add Batch 6
15. **C-015**: `vex_evidence_queries.py` — add exploited_by traversal

---

## Key Design Decisions (from proposed-design.md)

- **Connector pattern**: `OrgConnector` ABC in `connectors/base.py`; tools inject mock data path or real API client via constructor — no flag branching inside `fetch()`
- **KG upsert**: `db.collection(name).import_bulk(docs, overwrite=True)` — idempotent for all vertex and edge writes
- **TTL field**: all deployment-layer edges carry `ttl_expires` (ISO 8601); default 48h for exploit status, 7d for device inventory
- **No CVE metadata duplication**: connectors only write the CVE ID as a reference (`vulnerabilities/<cve_id>`) — never CVSS, CWE, or CVE descriptions
- **tenant_id required**: every vertex and edge in the deployment reality layer carries `tenant_id`
- **Spine CVE existence check**: before writing `exploited_by` or `device_has_vulnerability`, connector checks `vulnerabilities/<cve_id>` exists; skips gracefully if not
- **Schema additive**: existing 5 collections + 13 edges in v2.2.1 must not be modified

---

## Acceptance Criteria Mapping to Stage 7 Scenarios

| AC ID | Stage 7 Scenario ID | Test Type |
| --- | --- | --- |
| AC-001 | S7-001 | Integration — devices collection field verification |
| AC-002 | S7-002 | Integration — AQL traversal device→CVE |
| AC-003 | S7-003 | Integration — threat_detections field verification |
| AC-004 | S7-004 | Integration — exploited_by edge TTL verification |
| AC-005 | S7-005 | Integration — network_exposure edge field verification |
| AC-006 | S7-006 | Integration — access_events MFA gap for Hoffmann |
| AC-007 | S7-007 | Integration — incidents Jira/PD cross-link with CVE |
| AC-008 | S7-008 | Integration — cross-layer CRA Art.14 proof AQL |
| AC-009 | S7-009 | Integration — TTL cleanup zeroes stale edges |
| AC-010 | S7-010 | Integration — no CVSS/CWE fields in connector output |

---

## Unit/Integration Test Scope (Stage 6)

- Unit: `OrgConnector` ABC contract enforcement (extract + upsert called)
- Unit: each connector's `extract()` output shape against mock data fixtures
- Integration: schema migration `run_migration()` idempotency (run twice, second run is all-skip)
- Integration: `crowdstrike.run()` against mock JSON — verify ArangoDB documents exist with expected fields
- Integration: cross-layer AQL `cra_article14_evidence()` returns expected row for CVE-2023-38408
- Integration: TTL cleanup removes synthetic stale edges and sets `requires_refresh=true` on affected VEX docs
