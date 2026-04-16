# Requirements — org-data-kg-integration

**Status:** `Design-ready`
**Scope Triage:** `Large`
**Last Updated:** 2026-03-31

---

## Goal / Problem Statement

The Complira knowledge graph (KG) currently models **abstract vulnerability knowledge** (CVE→CWE→ATT&CK→regulatory requirement) that is tenant-agnostic and permanent. It is missing the **deployment reality layer** — which specific CVEs are live on which hosts, in what runtime state, with what surrounding organizational context.

Without the deployment layer, Complira cannot produce a defensible regulatory evidence chain for FDA 524B or EU CRA Article 14. The gap is ~55%: no device inventory, no threat detection evidence, no user/IAM control gap tracking, no incident lifecycle.

The goal is to add org-tool connectors that extract **only compliance-relevant signals** from 8 tools (CrowdStrike, Tenable, Qualys, SentinelOne, Okta, AWS EC2, Jira, PagerDuty), write them as time-bounded KG nodes and edges alongside the existing spine, and expose the combined graph through AQL queries that produce auditable regulatory evidence.

---

## In-Scope Use Cases

| UC ID | Use Case | Source Tools | Regulatory Tie |
| --- | --- | --- | --- |
| UC-001 | Ingest device inventory — map CVE findings to physical/virtual hosts | AWS EC2, CrowdStrike, Tenable, Qualys, SentinelOne | FDA 524B device inventory |
| UC-002 | Record active exploitation evidence — confirmed threats/detections with ATT&CK mapping | CrowdStrike, SentinelOne | CRA Art.14 early warning trigger |
| UC-003 | Record network exposure — internet_facing + public_ports per device | AWS EC2, CrowdStrike | CRA Art.14 risk surface |
| UC-004 | Record IAM/MFA control gaps — users without required MFA enrollment | Okta | FDA 524B §4.2, IEC 62443-4-2 |
| UC-005 | Record incident/ticket lifecycle — CVE → Jira ticket → PagerDuty incident → SLA clock | Jira, PagerDuty | CRA Art.14 response deadline, postmarket reporting |
| UC-006 | Cross-layer AQL traversal — CVE on exploited internet-facing host with open regulatory deadline | All KG layers combined | Unified regulatory evidence chain |
| UC-007 | TTL enforcement — expire stale deployment-layer edges, mark VEX docs requiring refresh | Prefect orchestration | Evidence freshness for audit |

---

## Acceptance Criteria

| AC ID | Requirement ID | Description | Measurable Expected Outcome |
| --- | --- | --- | --- |
| AC-001 | UC-001 | Device nodes written to KG with only compliance-relevant fields | `devices` collection contains `hostname`, `instance_id`, `internet_facing`, `public_ports`, `containment_status`, `tenant_id`; NO full EC2 schema |
| AC-002 | UC-001 | `device_has_vulnerability` edge links device to CVE in KG | AQL traversal from `devices/pump-api-prod-01` via `device_has_vulnerability` returns CVE-2023-38408 |
| AC-003 | UC-002 | `threat_detections` node written with CVE + ATT&CK tactic + IOC value | `threat_detections` collection contains `cve_id`, `technique_id`, `ioc_value`, `ttl_expires` |
| AC-004 | UC-002 | `exploited_by` edge links CVE to detection with TTL | Edge `exploited_by` from vulnerability to threat_detection has `ttl_expires` ≤ NOW + 48h |
| AC-005 | UC-003 | `network_exposure` edge written with `internet_facing=true` for pump-api-prod-01 | AQL query on `network_exposure` edges for pump-api-prod-01 returns `internet_facing=true`, `provider=crowdstrike` |
| AC-006 | UC-004 | MFA gap written as `access_event` node for users with zero enrolled factors | `access_events` collection contains entry for Sarah Hoffmann with `control_type=mfa_enrollment`, `control_status=not_enrolled`, `framework_requirement_id=FDA_524B_4_2` |
| AC-007 | UC-005 | Jira issue and PagerDuty incident cross-linked with CVE in `incidents` collection | `incidents` collection entry for PSEC-41 / PD incident links to CVE-2023-38408 with `regulatory_labels=[cra-article-14, fda-524b]` |
| AC-008 | UC-006 | Proof AQL traversal query executes against live KG and returns defensible CRA Art.14 evidence row | Query returns `{cve_id, host, blast_radius_score, cra_deadline, regulatory_action, evidence_sources}` for CVE-2023-38408 |
| AC-009 | UC-007 | Nightly Prefect flow expires edges past `ttl_expires` and flags VEX docs | After synthetic TTL expiry, AQL count of stale `exploited_by` edges is 0; affected VEX docs have `requires_refresh=true` |
| AC-010 | UC-001 | Each connector extracts only the compliance-relevant fields — no CVE metadata duplication | No `cvss3_base_score`, `cwe_ids`, or CVE descriptions written from tool connectors into KG nodes |

---

## Constraints / Dependencies

- **No CVE metadata duplication**: tools' CVSS scores, CWE IDs, and CVE descriptions are already in the NVD/GHSA spine. Importing again creates competing values.
- **No full user profiles**: only `admin_users`, `mfa_enrolled`, `role`, `mfa_policy_enforced` from Okta.
- **No CMDB**: do not import all EC2 instances — only those tagged with compliance frameworks (FDA-524B, EU_CRA, etc.).
- **TTL required on all deployment-layer edges**: exploit status is live data; stale evidence is a regulatory liability.
- **Tenant isolation**: all deployment-layer nodes/edges must carry `tenant_id`.
- **KG schema additive**: existing 5 collections + 13 edges must not be modified; new collections are additive.
- **Prefect orchestration**: connectors run as Prefect flows; nightly cleanup is a separate scheduled flow.
- **ArangoDB**: all writes use python-arango; upsert pattern (overwrite=True) for idempotency.

---

## Assumptions

- Mock data in `/Users/venkatapydialli/Downloads/mock_data_v2` is representative of real API responses.
- The `complira_graph` reference DB is accessible; per-tenant DBs follow the `complira_customer_{id}` pattern.
- CrowdStrike device IDs are stable enough to use as correlation keys across tools.
- Tenable `aws_instance_id` field provides the AWS↔Tenable bridge.
- Jira `customfield_10100` = CVE ID is a project-level convention in MedPulse's Jira setup.
- PagerDuty incident body contains structured CVE cross-reference (consistent with mock data).

---

## Open Questions / Risks

| ID | Question | Risk if Unresolved | Owner |
| --- | --- | --- | --- |
| OQ-001 | Do real CrowdStrike API responses always include `behaviors[].cve_id`? Mock data shows it — production may differ. | Detection→CVE edge breaks without this field | Dev |
| OQ-002 | What is the real Qualys QID→CVE mapping source? Mock data uses RESULTS text pattern matching — is there a cleaner API field? | Qualys connector fragile | Dev |
| OQ-003 | Should Redis (ElastiCache) be destroyed alongside the TTL cleanup flow, or does TTL live purely in ArangoDB edge fields? | Two TTL systems = consistency risk | Arch |
| OQ-004 | Is PagerDuty incident body always structured JSON with CVE ref, or sometimes free text? | Incident connector NLP dependency | Dev |
| OQ-005 | How does `blast_radius_score` get computed — from existing KG traversal or from tool risk scores (Tenable ACR=10, Qualys=95)? | Proof AQL query (UC-006) relies on this field | Arch |
