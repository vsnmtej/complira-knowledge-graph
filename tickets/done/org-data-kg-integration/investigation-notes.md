# Investigation Notes — org-data-kg-integration

**Status:** Complete
**Scope Triage:** `Large`
**Last Updated:** 2026-03-31

---

## Sources Consulted

| Source | Type | Path / Reference |
| --- | --- | --- |
| Mock data (19 files) | Local files | `/Users/venkatapydialli/Downloads/mock_data_v2/` |
| KG schema v2.2.1 | Local source | `src/complira_graph/schema/complira_kg_schema_v2_2.py` |
| Ingestion engine | Local source | `src/complira_graph/ingestion/ingestion_engine.py` |
| Ingestion adapter registry | Local source | `src/complira_graph/ingestion/adapter_registry.py` |
| KG orchestrator DAG | Local source | `src/complira_graph/orchestrator/dag.py` |
| VEX evidence service | Local source | `src/api/services/vex_evidence.py` |
| User's architectural framing | User message | (provided inline with ticket) |

---

## Key Findings

### 1. Mock Data — Compliance-Relevant Signal Inventory

**8 tools, 19 files. Critical signals only (per user's framing):**

| Tool | Files | Critical Compliance Signals | Noise to Discard |
| --- | --- | --- | --- |
| **AWS EC2** | aws_01_ec2_instances.json | Compliance tags (`FDA-524B`, `EU_CRA`), VPC/subnet isolation, monitoring state | InstanceType, BIOS, ReservationId, key names |
| **CrowdStrike** | device_entities, detection_entities | `internet_exposure` (yes/no), `filesystem_containment_status`, `behaviors[].cve_id`, `behaviors[].tactic/technique`, `network_accesses[].port`, IOC values | MAC, config IDs, bios_manufacturer, groups |
| **Jira** | issues | `customfield_10100` = CVE ID, `customfield_101` = hostname, `labels` = [cra-article-14, fda-524b, kev-confirmed], `status`, `priority` | Reporter, timestamps, category URLs |
| **Okta** | users, roles, factors, mfa_policy | `admin_users`, `mfa_enrolled` (per-user factor list), `role.type`, `mfa_policy.settings.factors` enforcement state | Name, phone, dept, title, created dates |
| **PagerDuty** | incidents | Incident title (contains CVE ref + regulatory label), `urgency`, `priority.name`, `status`, `body.details` | Assignment timestamps, html_url |
| **Qualys** | hosts, vulnerabilities | `ASSET_RISK_SCORE`, `TAGS` (compliance), QID→CVE (via RESULTS text), `FIRST_FOUND_DATETIME`, `LAST_FOUND_DATETIME` | HOST_ID, NETBIOS, XML structure |
| **SentinelOne** | agents, threats | `isInfected`, `threatCount`, `mitigationMode`, `mitigationStatus`, `cveId` on threat, `classification`, `indicators.category` | networkInterfaces, licenseKey, locations |
| **Tenable** | assets, vulnerabilities | `acr_score`, `aes_score`, `aws_instance_id` (cross-tool bridge), `plugin.attributes.exploit_available`, `vpr_score`, `patch_publication_date`, `state=OPEN` | family_id, family_name, raw CWE refs (redundant with spine) |

**Critical cross-tool correlation confirmed in mock data:**
- CVE-2023-38408 appears in: CrowdStrike detection (actively exploited, tactic=TA0001), Tenable (CVSS 9.8, exploit_available=true, VPR 9.4), Qualys (severity=5, OPEN), Jira PSEC-41 (cra-article-14, actively-exploited labels), PagerDuty P1 ("CRA Art.14 Early Warning"), SentinelOne agent infection + threat.
- pump-api-prod-01 is tagged `FDA-524B` in AWS, has `internet_exposure=yes` in CrowdStrike, has `filesystem_containment_status=containment_pending`, `acr_score=10` in Tenable.
- Sarah Hoffmann (s.hoffmann@medpulse.io): zero MFA factors enrolled, Okta MFA policy requires TOTP+Push for ALL users → violation of `FDA_524B_4_2`.

### 2. Existing KG Structure — What's Present

**Reference DB (`complira_graph`) — document collections:**
- `vulnerabilities`, `weaknesses` (CWE), `attack_techniques` (ATT&CK), `regulatory_requirements` — all populated by NVD/GHSA/CWE/ATT&CK agents
- `scan_runs`, `scan_findings`, `detected_controls`, `evidence_packages`, `components` — populated by ingestion engine (v2.2.1)

**Reference DB — edge collections (13):**
- `component_has_vuln` (vex_status, is_kev_at_detection, epss_score_at_detection)
- `finding_maps_to_weakness`, `finding_triggers_req`, `detected_control_maps_to`
- `control_in_component`, `finding_in_component`, `evidence_links_finding`, `evidence_for_project`
- `project_uses_component`, `matched_by_cpe`, `depends_on`, `licensed_under`, `component_eol_status`

**What the KG can already answer:** "What does CVE-X mean for framework Y?" (universal, tenant-agnostic)
**What it cannot answer:** "Is CVE-X actively exploited on device Z in tenant T right now?"

### 3. Ingestion Architecture — How the Existing Pipeline Works

- `IngestionEngine.process(tool_name, raw_file, scan_run_id, tenant_id)` → `List[IngestionBundle]`
- Each bundle routes to a collection via `collection` field on the bundle
- Per-tool variation is entirely in `ADAPTER_REGISTRY` (no engine changes needed for new tools)
- `ToolAdapter` config: `tool_name`, `finding_type`, `normalizer_fn`, `edge_producers`
- **Key architectural signal**: OCP is already enforced — adding a new tool = add one registry entry

### 4. Orchestrator DAG Structure

- `AGENT_DEPENDENCIES` dict drives Kahn's topological sort
- Existing agents: CWE, ATT&CK, NVD, OSV, GHSA, EPSS, KEV, Metasploit, ExploitDB, etc.
- Org connectors need to run **after** NVD spine (they reference `vulnerabilities` collection nodes)
- New batch in DAG: `Batch 6: Org Connectors (Depend on NVD Spine)`

### 5. Critical Architecture Constraints Identified

**Constraint 1 — No cross-DB edges in ArangoDB:**
All new collections must live in `reference` DB alongside the spine. Per-tenant data isolation achieved via `tenant_id` field + composite index (as established in v2.2.1 Fix 2). NOT via separate databases.

**Constraint 2 — Deployment-layer edges require TTL:**
CrowdStrike exploit status changes within hours. An `exploited_by` edge that's 3 days old is a regulatory liability in a CRA Art.14 submission. TTL field on every deployment-layer edge; nightly Prefect cleanup.

**Constraint 3 — Idempotent upserts only:**
All connectors must use `overwrite=True` in python-arango insert. Same device_id + tenant_id → update, not duplicate.

**Constraint 4 — CVE metadata is NOT loaded from tool connectors:**
CVSS, CWE IDs, CVE descriptions already exist in `vulnerabilities` collection from NVD/GHSA. Importing again from Tenable/Qualys creates competing values. Connectors write `_from`/`_to` edges pointing to existing `vulnerabilities/{cve_id}` nodes only.

**Constraint 5 — Selective EC2 import:**
Only import EC2 instances tagged with compliance framework values (`FDA-524B`, `EU_CRA`, `HIPAA`, etc.). Importing all EC2s is a CMDB anti-pattern.

### 6. New Collections Required

Three new vertex collections are needed (none exist today):

| Collection | Key Design Decision |
| --- | --- |
| `devices` | Keyed by `{tenant_id}_{hostname}` or `{tenant_id}_{instance_id}`; fields: hostname, instance_id, internet_facing (bool), public_ports (list), containment_status, os_name, agent_version, compliance_tags, tenant_id, ttl_expires, collected_at |
| `threat_detections` | Keyed by `{tenant_id}_{detection_id}`; fields: detection_id, cve_id, technique_id (ATT&CK), tactic, ioc_value, ioc_type, severity, status, provider, tenant_id, ttl_expires, collected_at |
| `access_events` | Keyed by `{tenant_id}_{user_id}_{control_type}`; fields: user_id, user_email, control_type (mfa_enrollment/role_assignment), control_status (active/not_enrolled), framework_requirement_id, policy_name, tenant_id, collected_at |
| `incidents` | Keyed by `{tenant_id}_{source}_{incident_id}`; fields: source (jira/pagerduty), incident_id, cve_id, hostname, regulatory_labels, priority, status, sla_deadline, tenant_id, collected_at |

### 7. New Edge Collections Required

| Edge | From → To | Critical Fields |
| --- | --- | --- |
| `device_has_vulnerability` | devices → vulnerabilities | source_tools (list), first_seen, last_seen, risk_score (Tenable ACR / Qualys score), tenant_id, ttl_expires |
| `exploited_by` | vulnerabilities → threat_detections | is_exploited (bool), is_isolated (bool), alert_count, provider, source_type (deterministic), tenant_id, ttl_expires |
| `network_exposure` | devices → (self-reference or separate exposure node) | internet_facing (bool), public_ports (list), provider, tenant_id, ttl_expires |
| `user_lacks_control` | access_events → regulatory_requirements | gap_type (mfa_not_enrolled/role_missing), framework, article, tenant_id, collected_at |
| `device_triggers_incident` | devices → incidents | tenant_id, collected_at |

### 8. Connector Architecture Pattern

Each tool connector follows this interface:
```
OrgConnector
  .fetch(config) -> raw_response
  .extract(raw_response) -> List[ComplianceSignal]
  .upsert_kg(signals, db, tenant_id) -> UpsertResult
```

Connectors that do NOT need to call live APIs (mock data mode): all 8 in this phase. Live API auth happens in a later phase.

### 9. Proof AQL Query Shape

The query that proves both KG layers work together (from user's framing):
```aql
FOR vi IN vulnerabilities
    FILTER vi.cve_id == "CVE-2023-38408"
    FILTER vi.tenant_id == @tenant_id  // or just use edge filter

    FOR eb IN exploited_by
        FILTER eb._from == vi._id
        FILTER eb.is_exploited == true
        FILTER eb.ttl_expires > DATE_NOW()

    FOR ne IN network_exposure
        FILTER ne._from == PARSE_IDENTIFIER(eb._to).collection + "/" + ...

    FOR reg IN OUTBOUND vi maps_to_requirement
        FILTER reg.framework == "EU_CRA"

    RETURN { cve_id, host, cra_deadline, regulatory_action, evidence_sources }
```

This traversal requires: existing `vulnerabilities` + `maps_to_requirement` (spine) + new `exploited_by` + `network_exposure` (deployment layer).

---

## Scope Triage Decision: `Large`

**Signals:**
- 8 new connector modules
- 4 new ArangoDB collections (schema migration)
- 5 new edge collections (schema migration)
- 1 new Prefect orchestration flow (nightly TTL cleanup)
- Cross-layer AQL template (new query file)
- Touches: schema, ingestion, orchestrator DAG, new connectors module, new queries module

**Workflow depth:** `Large` → `proposed-design.md` required before runtime call stacks.

---

## Open Unknowns

| ID | Unknown | Impact |
| --- | --- | --- |
| OQ-001 | CrowdStrike `behaviors[].cve_id` — always present in production API? | Detection→CVE edge reliability |
| OQ-002 | Qualys QID→CVE mapping — RESULTS text pattern or dedicated API field? | Qualys connector fragility |
| OQ-003 | `blast_radius_score` source — existing KG traversal or tool risk scores? | Proof query field availability |
| OQ-004 | PagerDuty body structure consistency | Incident connector regex dependency |
| OQ-005 | Prefect version in use — v2 (flows/tasks) or v3? | Orchestration syntax |

---

## Implications for Requirements / Design

1. **Schema migration is a hard dependency**: schema v2.3 must be created and applied before any connector writes.
2. **Connector isolation principle**: each connector must be independently runnable; no shared state between connectors except the ArangoDB client.
3. **TTL cleanup must be a separate Prefect flow** (not inline in connectors) to avoid coupling live ingestion to cleanup logic.
4. **`devices` collection is the hub**: all deployment-layer edges route through `devices`, making it the most critical new collection.
5. **Mock-data-first**: connectors should accept file path as input (mock data mode) with live API client as optional injection — DIP, enables testing without live credentials.
