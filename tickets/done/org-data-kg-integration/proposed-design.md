# Proposed Design — org-data-kg-integration

## Design Version

- Current Version: `v1`

## Revision History

| Version | Trigger | Summary Of Changes | Related Review Round |
| --- | --- | --- | --- |
| v1 | Initial draft | Full design for deployment-reality layer + 8 org connectors | 1 |

## Artifact Basis

- Investigation Notes: `tickets/in-progress/org-data-kg-integration/investigation-notes.md`
- Requirements: `tickets/in-progress/org-data-kg-integration/requirements.md`
- Requirements Status: `Design-ready`

---

## Summary

Add a **deployment reality layer** to the Complira KG that records which CVEs are live on which devices in what runtime state, capturing signals from 8 org tools (CrowdStrike, Tenable, Qualys, SentinelOne, Okta, AWS EC2, Jira, PagerDuty). The layer is purely additive — it adds 4 new vertex collections, 5 new edge collections, and 8 connector modules without modifying any existing collection. Edges carry TTL fields; a nightly Prefect flow expires stale data and flags VEX documents for refresh. Both KG layers (abstract spine + deployment reality) are traversable in a single AQL query that produces defensible CRA Art.14 / FDA 524B evidence.

---

## Goals

1. Make `CVE on exploited internet-facing device with open regulatory deadline` queryable in < 50ms AQL
2. Surface IAM/MFA control gaps per user per framework requirement
3. Link CVE → Jira/PagerDuty incident lifecycle with SLA deadline tracking
4. Ensure all deployment-layer evidence expires after 48h (exploit status) or 7d (device inventory) unless refreshed
5. Keep the spine tenant-agnostic; deployment layer carries `tenant_id` on every node/edge

---

## Legacy Removal Policy (Mandatory)

- Policy: `No backward compatibility; remove legacy code paths.`
- No legacy paths exist for org connectors (entirely new). No existing code is modified.

---

## Requirements And Use Cases

| Requirement ID | Description | Acceptance Criteria ID(s) | Use Case IDs |
| --- | --- | --- | --- |
| UC-001 | Device inventory — CVE findings on hosts | AC-001, AC-002, AC-010 | UC-001 |
| UC-002 | Active exploitation evidence | AC-003, AC-004 | UC-002 |
| UC-003 | Network exposure | AC-005 | UC-003 |
| UC-004 | IAM/MFA control gaps | AC-006 | UC-004 |
| UC-005 | Incident/ticket lifecycle | AC-007 | UC-005 |
| UC-006 | Cross-layer AQL proof query | AC-008 | UC-006 |
| UC-007 | TTL enforcement | AC-009 | UC-007 |

---

## Codebase Understanding Snapshot

| Area | Findings | Evidence | Open Unknowns |
| --- | --- | --- | --- |
| Ingestion entrypoint | `IngestionEngine.process()` → `IngestionBundle` list; OCP enforced via `ADAPTER_REGISTRY` | `src/complira_graph/ingestion/ingestion_engine.py:1-50` | — |
| Orchestrator | Prefect + Kahn's DAG; agents in batches by dependency | `src/complira_graph/orchestrator/dag.py` | Prefect v2 vs v3 syntax |
| KG schema | 5 doc collections, 13 edge collections, all in reference DB | `src/complira_graph/schema/complira_kg_schema_v2_2.py` | — |
| Connector pattern | No org connectors exist yet; ToolAdapter pattern is the right seam | `ingestion/adapter_registry.py` | — |
| VEX evidence service | Traverses spine; needs `exploited_by` edges to include exploitation evidence | `src/api/services/vex_evidence.py` | — |

---

## Current State (As-Is)

- **KG spine only**: CVE→CWE→ATT&CK→regulatory requirement. Universal. ~45% of FDA 524B / EU CRA evidence chain.
- **No device nodes**: cannot track which CVE is on which host.
- **No threat detection nodes**: cannot prove active exploitation.
- **No user/IAM nodes**: cannot detect MFA gaps per framework requirement.
- **No incident nodes**: cannot track CRA Art.14 response deadlines.
- **No org connectors**: no Prefect flows for CrowdStrike, Tenable, Qualys, SentinelOne, Okta, AWS, Jira, PagerDuty.

---

## Target State (To-Be)

- **KG deployment layer added** (4 new vertex collections + 5 new edge collections): devices, threat_detections, access_events, incidents
- **8 org connectors** (one module per tool, under `src/complira_graph/connectors/`)
- **Schema v2.3 migration script**: `src/complira_graph/schema/complira_kg_schema_v2_3.py`
- **Nightly Prefect TTL cleanup flow**: `src/complira_graph/orchestrator/ttl_cleanup.py`
- **Cross-layer AQL query template**: `src/complira_graph/queries/deployment_reality_queries.py`
- **VEX evidence integration**: `VEXEvidenceService` updated to include `exploited_by` evidence in Tier 1

---

## Architecture Direction Decision (Mandatory)

- **Chosen direction**: Additive new module layer — `src/complira_graph/connectors/` — isolated from existing ingestion engine. Each connector is a standalone class with `fetch()`, `extract()`, `upsert_kg()` methods.
- **Rationale**:
  - `complexity`: connector concerns (live API auth, rate limiting, field filtering) are orthogonal to the existing ingestion pipeline (SBOM/scan tool parsing). Merging them would pollute the adapter registry with live-API concerns.
  - `testability`: standalone connectors can be tested with mock JSON files without touching the ingestion engine.
  - `operability`: each connector can be run independently (for backfill, debugging, or per-tenant refreshes).
  - `evolution cost`: adding a 9th tool = add one connector file; no engine changes.
- **Layering fitness**: current `ingestion/` + `orchestrator/` layering is coherent. Adding `connectors/` at the same level is the right placement.
- **Outcome**: `Add` — new `connectors/` module with base class + 8 tool connectors.

---

## Architecture: Two-Layer KG Model

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  LAYER 1: Abstract Vulnerability Spine (Universal, Tenant-Agnostic)          │
│  vulnerabilities → weaknesses → attack_techniques → regulatory_requirements │
│  components → component_has_vuln → vulnerabilities                          │
│  (populated by NVD/GHSA/CWE/ATT&CK/EPSS/KEV agents)                        │
└──────────────────────────────────────────────────────────────────────────────┘
                           ↕ traversed in single AQL query
┌──────────────────────────────────────────────────────────────────────────────┐
│  LAYER 2: Deployment Reality (Per-Tenant, Time-Bounded)                      │
│  devices ──device_has_vulnerability──► vulnerabilities (Layer 1)            │
│  vulnerabilities ──exploited_by──► threat_detections                        │
│  devices ──network_exposure──► (internet_facing, public_ports)              │
│  access_events ──user_lacks_control──► regulatory_requirements (Layer 1)   │
│  devices ──device_triggers_incident──► incidents                            │
│  (populated by org connectors; TTL on all edges)                            │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Change Inventory (Delta)

| Change ID | Type | Current Path | Target Path | Rationale |
| --- | --- | --- | --- | --- |
| C-001 | Add | — | `src/complira_graph/schema/complira_kg_schema_v2_3.py` | Schema migration: 4 new vertex + 5 new edge collections |
| C-002 | Add | — | `src/complira_graph/connectors/__init__.py` | New connectors package |
| C-003 | Add | — | `src/complira_graph/connectors/base.py` | `OrgConnector` abstract base class |
| C-004 | Add | — | `src/complira_graph/connectors/crowdstrike.py` | CrowdStrike connector |
| C-005 | Add | — | `src/complira_graph/connectors/tenable.py` | Tenable.io connector |
| C-006 | Add | — | `src/complira_graph/connectors/qualys.py` | Qualys VM connector |
| C-007 | Add | — | `src/complira_graph/connectors/sentinelone.py` | SentinelOne connector |
| C-008 | Add | — | `src/complira_graph/connectors/okta.py` | Okta connector |
| C-009 | Add | — | `src/complira_graph/connectors/aws_ec2.py` | AWS EC2 connector |
| C-010 | Add | — | `src/complira_graph/connectors/jira.py` | Jira connector |
| C-011 | Add | — | `src/complira_graph/connectors/pagerduty.py` | PagerDuty connector |
| C-012 | Add | — | `src/complira_graph/orchestrator/ttl_cleanup.py` | Nightly TTL cleanup Prefect flow |
| C-013 | Add | — | `src/complira_graph/queries/deployment_reality_queries.py` | Cross-layer AQL templates |
| C-014 | Modify | `src/complira_graph/orchestrator/dag.py` | same | Add Batch 6: OrgConnectors after NVD spine |
| C-015 | Modify | `src/complira_graph/queries/vex_evidence_queries.py` | same | Add `exploited_by` traversal to Tier 1 evidence collection |

---

## Target Architecture Shape And Boundaries

| Layer/Boundary | Purpose | Owns | Must Not Own |
| --- | --- | --- | --- |
| `connectors/base.py` | Contract for all org connectors | `OrgConnector` ABC, `ComplianceSignal` dataclass, `UpsertResult` | API client auth details, ArangoDB write logic |
| `connectors/{tool}.py` | Single-tool extraction + KG write | `fetch()`, `extract()`, `upsert_kg()` for one tool | Multi-tool logic, CVE metadata, full user profiles |
| `schema/complira_kg_schema_v2_3.py` | Schema migration | New collection definitions + index creation | Data loading, connector logic |
| `orchestrator/ttl_cleanup.py` | Scheduled stale-edge removal | TTL query + VEX flag update | Live ingestion, connector invocation |
| `queries/deployment_reality_queries.py` | Cross-layer AQL templates | `device_cve_exposure_query()`, `cra_article14_evidence_query()`, `mfa_gap_query()` | Data writing, connector logic |
| `orchestrator/dag.py` | DAG dependency map | Agent execution order | Connector implementation |

---

## File And Module Breakdown

| File/Module | Change | Layer | Responsibility | Public APIs | Key Inputs/Outputs |
| --- | --- | --- | --- | --- | --- |
| `schema/complira_kg_schema_v2_3.py` | Add | Infra/Schema | Create 4 vertex + 5 edge collections + TTL indexes | `run_migration(db)` | db handle → creates collections |
| `connectors/base.py` | Add | Domain | Abstract connector contract | `OrgConnector`, `ComplianceSignal`, `UpsertResult` | — |
| `connectors/crowdstrike.py` | Add | Integration | Extract internet_exposure, containment_status, detection CVEs, ATT&CK tactics | `CrowdStrikeConnector(data_path, db, tenant_id)` | raw JSON → devices + threat_detections + exploited_by edges |
| `connectors/tenable.py` | Add | Integration | Extract ACR score, exploit_available, patch_date, aws_instance_id bridge | `TenableConnector` | raw JSON → device_has_vulnerability edges |
| `connectors/qualys.py` | Add | Integration | Extract risk_score, CVE findings, first/last seen | `QualysConnector` | raw JSON → device_has_vulnerability edges |
| `connectors/sentinelone.py` | Add | Integration | Extract isInfected, mitigationStatus, cveId on threats | `SentinelOneConnector` | raw JSON → devices + threat_detections + exploited_by edges |
| `connectors/okta.py` | Add | Integration | Extract users with zero MFA factors vs. policy requirement | `OktaConnector` | raw JSON → access_events + user_lacks_control edges |
| `connectors/aws_ec2.py` | Add | Integration | Extract compliance-tagged EC2s: internet_facing, public_ports | `AWSEC2Connector` | raw JSON → devices nodes only |
| `connectors/jira.py` | Add | Integration | Extract CVE label, regulatory labels, status, hostname | `JiraConnector` | raw JSON → incidents nodes |
| `connectors/pagerduty.py` | Add | Integration | Extract CVE ref in title/body, urgency, SLA clock | `PagerDutyConnector` | raw JSON → incidents nodes + device_triggers_incident edges |
| `orchestrator/ttl_cleanup.py` | Add | Orchestration | Nightly: delete edges with `ttl_expires < DATE_NOW()`, set `requires_refresh=true` on VEX docs | `run_ttl_cleanup(db)` Prefect flow | db handle → deleted edge count + flagged VEX doc count |
| `queries/deployment_reality_queries.py` | Add | Query | Named AQL query functions for cross-layer traversal | `cra_article14_evidence(db, cve_id, tenant_id)`, `mfa_gap_report(db, tenant_id)`, `device_cve_exposure(db, tenant_id)` | → list of evidence dicts |
| `orchestrator/dag.py` | Modify | Orchestration | Add Batch 6: OrgConnector entries | — | New dependency rows |
| `queries/vex_evidence_queries.py` | Modify | Query | Add `exploited_by` traversal as Tier 1 signal | — | `exploited_by` edges included in Tier 1 evidence |

---

## New Collection Schemas

### Vertex: `devices`
```python
{
  "_key":             "{tenant_id}_{hostname}",   # stable, dedup key
  "hostname":         str,                         # e.g. "pump-api-prod-01"
  "instance_id":      str | None,                  # AWS EC2 instance ID
  "internet_facing":  bool,                        # from CrowdStrike or AWS
  "public_ports":     list[int],                   # e.g. [22, 443, 8883]
  "containment_status": str | None,               # "containment_pending" | "contained" | None
  "os_name":          str | None,
  "agent_version":    str | None,
  "compliance_tags":  list[str],                  # ["FDA-524B", "EU_CRA"]
  "source_tools":     list[str],                  # ["crowdstrike", "tenable", "aws"]
  "tenant_id":        str,
  "ttl_expires":      str,                        # ISO8601; 7d from collected_at
  "collected_at":     str,                        # ISO8601
}
```

### Vertex: `threat_detections`
```python
{
  "_key":         "{tenant_id}_{detection_id}",
  "detection_id": str,                            # CrowdStrike ldt:* or SentinelOne threat ID
  "cve_id":       str | None,                     # "CVE-2023-38408"
  "technique_id": str | None,                     # "T1190"
  "tactic":       str | None,                     # "TA0001"
  "ioc_value":    str | None,                     # "185.220.101.47"
  "ioc_type":     str | None,                     # "ip_address" | "hash" | "domain"
  "severity":     str,                            # "critical" | "high" | "medium"
  "status":       str,                            # "new" | "in_progress" | "resolved"
  "provider":     str,                            # "crowdstrike" | "sentinelone"
  "tenant_id":    str,
  "ttl_expires":  str,                            # 48h from collected_at
  "collected_at": str,
}
```

### Vertex: `access_events`
```python
{
  "_key":                    "{tenant_id}_{user_id}_{control_type}",
  "user_id":                 str,
  "user_email":              str,
  "control_type":            str,                 # "mfa_enrollment" | "role_assignment"
  "control_status":          str,                 # "active" | "not_enrolled" | "inactive"
  "framework_requirement_id": str,                # "FDA_524B_4_2" | "IEC_62443_4_2"
  "policy_name":             str | None,          # Okta policy name
  "tenant_id":               str,
  "collected_at":            str,
}
```

### Vertex: `incidents`
```python
{
  "_key":              "{tenant_id}_{source}_{incident_id}",
  "source":            str,                       # "jira" | "pagerduty"
  "incident_id":       str,                       # "PSEC-41" | PD incident ID
  "cve_id":            str | None,
  "hostname":          str | None,
  "regulatory_labels": list[str],                 # ["cra-article-14", "fda-524b"]
  "priority":          str,                       # "P1" | "high"
  "status":            str,                       # "in_progress" | "acknowledged"
  "sla_deadline":      str | None,                # ISO8601 computed from CRA 24h rule
  "tenant_id":         str,
  "collected_at":      str,
}
```

### Edge: `device_has_vulnerability`
```python
{
  "_from":        "devices/{key}",
  "_to":          "vulnerabilities/{cve_id}",
  "source_tools": list[str],
  "first_seen":   str,
  "last_seen":    str,
  "risk_score":   float | None,                   # Tenable ACR or Qualys risk score
  "tenant_id":    str,
  "ttl_expires":  str,                            # 7d
  "collected_at": str,
}
```

### Edge: `exploited_by`
```python
{
  "_from":        "vulnerabilities/{cve_id}",
  "_to":          "threat_detections/{key}",
  "is_exploited": bool,
  "is_isolated":  bool,
  "alert_count":  int,
  "provider":     str,
  "source_type":  "deterministic",
  "tenant_id":    str,
  "ttl_expires":  str,                            # 48h
  "collected_at": str,
}
```

### Edge: `network_exposure`
```python
{
  "_from":          "devices/{key}",
  "_to":            "devices/{key}",              # self-edge (device exposes itself)
  "internet_facing": bool,
  "public_ports":   list[int],
  "provider":       str,
  "tenant_id":      str,
  "ttl_expires":    str,
  "collected_at":   str,
}
```

### Edge: `user_lacks_control`
```python
{
  "_from":     "access_events/{key}",
  "_to":       "regulatory_requirements/{req_id}",
  "gap_type":  str,                               # "mfa_not_enrolled" | "role_missing"
  "framework": str,                               # "FDA_524B" | "EU_CRA"
  "article":   str | None,
  "tenant_id": str,
  "collected_at": str,
}
```

### Edge: `device_triggers_incident`
```python
{
  "_from":     "devices/{key}",
  "_to":       "incidents/{key}",
  "tenant_id": str,
  "collected_at": str,
}
```

---

## Connector Base Contract

```python
# src/complira_graph/connectors/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

@dataclass
class ComplianceSignal:
    collection: str          # target vertex collection
    document:   dict         # fields to upsert
    edges:      list[dict] = field(default_factory=list)

@dataclass
class UpsertResult:
    collection:   str
    written:      int
    edges_written: int
    errors:       list[str] = field(default_factory=list)

class OrgConnector(ABC):
    def __init__(self, db, tenant_id: str, data_path: str | None = None):
        self.db = db
        self.tenant_id = tenant_id
        self.data_path = data_path  # None = live API mode

    @abstractmethod
    def fetch(self) -> Any:
        """Return raw response (file content or live API call)."""

    @abstractmethod
    def extract(self, raw: Any) -> list[ComplianceSignal]:
        """Return compliance-relevant signals only. No CVE metadata."""

    def upsert_kg(self, signals: list[ComplianceSignal]) -> list[UpsertResult]:
        """Write signals to ArangoDB. Idempotent (overwrite=True)."""
        ...

    def run(self) -> list[UpsertResult]:
        """Convenience: fetch → extract → upsert_kg."""
        return self.upsert_kg(self.extract(self.fetch()))
```

---

## Cross-Layer Proof AQL Query

```aql
// deployment_reality_queries.py: cra_article14_evidence(db, cve_id, tenant_id)

FOR vuln IN vulnerabilities
    FILTER vuln.cve_id == @cve_id

    FOR eb IN exploited_by
        FILTER eb._from == vuln._id
        FILTER eb.is_exploited == true
        FILTER eb.tenant_id == @tenant_id
        FILTER eb.ttl_expires > DATE_NOW()

        LET det = DOCUMENT(eb._to)
        LET dev_key = SPLIT(det._key, "_", 2)[0] + "_" + SPLIT(det._key, "_", 2)[1]

        FOR ne IN network_exposure
            FILTER ne._from == CONCAT("devices/", dev_key)
            FILTER ne.internet_facing == true
            FILTER ne.tenant_id == @tenant_id

        FOR reg IN OUTBOUND vuln maps_to_requirement
            FILTER reg.framework == "EU_CRA"

        LET inc = (
            FOR i IN incidents
                FILTER i.cve_id == @cve_id
                FILTER i.tenant_id == @tenant_id
                FILTER "cra-article-14" IN i.regulatory_labels
                LIMIT 1
                RETURN i
        )[0]

        RETURN {
            cve_id:             vuln.cve_id,
            host:               det.hostname,
            internet_facing:    ne.internet_facing,
            technique_id:       det.technique_id,
            ioc_value:          det.ioc_value,
            blast_radius_score: vuln.blast_radius_score,
            cra_deadline:       inc.sla_deadline,
            regulatory_action:  reg.required_action,
            evidence_sources:   [eb.provider, ne.provider, inc.source]
        }
```

---

## Layer-Appropriate Separation Of Concerns Check

- **Integration layer** (`connectors/`): each connector owns exactly one tool's API contract and field-filtering logic. No shared state.
- **Domain layer** (`schema/`, `queries/`): schema migration and AQL templates are agnostic of which tool produced the data.
- **Orchestration layer** (`orchestrator/`): DAG and TTL cleanup own scheduling and coordination; do not own data extraction.

---

## Naming Decisions

| Item Type | Proposed Name | Reason |
| --- | --- | --- |
| Package | `connectors/` | Clear, one-word; distinguishes from `ingestion/` (SBOM/scan tools) |
| Base class | `OrgConnector` | "Org" signals "organizational tool" vs. "NVD/GHSA feed" |
| Signal type | `ComplianceSignal` | Emphasizes only compliance-relevant data is extracted |
| Edge | `exploited_by` | Active voice: vulnerability is exploited by detection event |
| Edge | `device_has_vulnerability` | Ownership direction: device → vulnerability |
| Edge | `user_lacks_control` | Negative gap framing: user lacks required control |
| Edge | `network_exposure` | Self-edge: device exposes itself to network |
| Collection | `access_events` | Generic enough for MFA + role gaps |
| Flow | `ttl_cleanup` | TTL is the mechanism; cleanup is the intent |

---

## Naming Drift Check

| Item | Current Responsibility | Name Match? | Corrective Action |
| --- | --- | --- | --- |
| `ingestion/` | Processes SBOM/scan file artifacts | Yes | N/A |
| `connectors/` (new) | Fetches from live org APIs | Yes | N/A |
| `orchestrator/dag.py` | Agent dependency ordering | Yes | N/A |
| `queries/vex_evidence_queries.py` | VEX evidence traversal | Yes — adding `exploited_by` extends it correctly | N/A |

---

## Existing-Structure Bias Check

| Area | Bias Risk | Architecture-First Alternative | Decision |
| --- | --- | --- | --- |
| Putting connectors in `ingestion/adapter_registry.py` | High — conflates live API fetch with SBOM/scan parsing | Separate `connectors/` package | Change |
| Adding new collections to `complira_kg_schema_v2_2.py` | Medium — version discipline broken | New `complira_kg_schema_v2_3.py` migration script | Change |
| Inline TTL cleanup in each connector | High — violates SRP; cleanup is a scheduled concern | Separate `orchestrator/ttl_cleanup.py` flow | Change |

---

## Anti-Hack Check

| Candidate Change | Hack Risk | Proper Fix | Decision |
| --- | --- | --- | --- |
| Store full EC2 schema to avoid field-selection code | High — CMDB anti-pattern | `AWSEC2Connector.extract()` filters to compliance-tagged + compliance-relevant fields only | Proper fix |
| Copy CVE metadata from Tenable to avoid spine traversal | High — creates competing data | Always resolve to existing `vulnerabilities/{cve_id}` node via `_to` edge reference | Proper fix |
| Use in-memory TTL check in connectors | Medium — stale data survives restart | TTL as ArangoDB field; nightly Prefect flow expires deterministically | Proper fix |

---

## Dependency Flow And Cross-Reference Risk

| Module | Upstream | Downstream | Risk | Mitigation |
| --- | --- | --- | --- | --- |
| `connectors/{tool}.py` | `connectors/base.py`, ArangoDB client | None (writes only) | Low | Connector = leaf node |
| `schema/v2_3.py` | None | `connectors/`, `queries/deployment_reality_queries.py` | Medium — must run before connectors | CI migration gate: v2_3 applied before connector tests |
| `orchestrator/ttl_cleanup.py` | ArangoDB client, `queries/` | None | Low | Independent Prefect flow |
| `queries/deployment_reality_queries.py` | Collections exist (post-v2_3) | VEX evidence service | Medium | Version gate on schema |
| `queries/vex_evidence_queries.py` (modified) | `exploited_by` collection (post-v2_3) | VEX generation API | Medium — must not break existing Tier 1 | `exploited_by` traversal is additive; fallback to empty list if no edges |

## Allowed Dependency Direction

- `connectors/` → `schema/` (read collection names) ✓
- `connectors/` → `db.py` (ArangoDB client) ✓
- `orchestrator/` → `connectors/` (call `connector.run()`) ✓
- `queries/` → collections (read-only AQL) ✓
- `connectors/` → `queries/` — **NOT ALLOWED** (connectors write; queries read; keep separate)

---

## Data Models (Summary)

See "New Collection Schemas" section above for full field specs. Key invariants:
- Every deployment-layer node: `tenant_id` (required) + `collected_at` (ISO8601)
- Every deployment-layer edge: `ttl_expires` (ISO8601) + `tenant_id`
- Device key: `{tenant_id}_{hostname}` — stable across tool sources
- Vulnerability reference: always `vulnerabilities/{cve_id}` — no CVE metadata duplication

---

## Error Handling And Edge Cases

| Scenario | Handling |
| --- | --- |
| CVE in tool data not found in `vulnerabilities` collection | Log warning; skip edge write; do NOT create orphan CVE node |
| Device hostname missing (tool API gap) | Use `instance_id` as fallback key; log warning |
| CrowdStrike `behaviors[].cve_id` absent | Skip `exploited_by` edge; device node + network_exposure edge still written |
| Qualys QID→CVE pattern match fails | Skip finding; log; do not write partial data |
| PagerDuty body not structured | Regex extraction fails gracefully; incident node written without `cve_id` |
| `ttl_expires` < NOW on read | AQL WHERE filter in all queries; stale edges never returned |
| Concurrent connector runs | `overwrite=True` makes upserts idempotent; last-write-wins acceptable for TTL refresh |

---

## Use-Case Coverage Matrix

| use_case_id | Primary Path | Fallback Path | Error Path | Runtime Call Stack Section |
| --- | --- | --- | --- | --- |
| UC-001 | Yes | Yes (missing hostname → instance_id key) | Yes (CVE not in spine → skip) | CS-001, CS-002 |
| UC-002 | Yes | N/A | Yes (no cve_id in behavior → skip edge) | CS-003 |
| UC-003 | Yes | N/A | N/A | CS-004 |
| UC-004 | Yes | N/A | Yes (factor API empty → mark not_enrolled) | CS-005 |
| UC-005 | Yes | N/A | Yes (no CVE in body → incident written without CVE) | CS-006 |
| UC-006 | Yes (proof query) | N/A | Yes (no exploited_by edge → empty result) | CS-007 |
| UC-007 | Yes | N/A | Yes (AQL delete fails → retry + alert) | CS-008 |

---

## Performance / Security Considerations

- **No secrets in connector code**: API credentials injected via env vars or Prefect SecretBlock; mock-data mode uses file path.
- **AQL TTL queries**: `ttl_expires` indexed with persistent index on each deployment collection; cleanup query `FOR e IN exploited_by FILTER e.ttl_expires < DATE_NOW() REMOVE e` is O(index_size).
- **Batch upserts**: connectors collect all signals then `import_bulk()` in one call; not per-document inserts.
- **Rate limiting**: live API mode (future) should use exponential backoff; not needed for mock-data-first phase.

---

## Migration / Rollout

1. Apply schema v2.3 migration (creates empty collections + indexes)
2. Load mock data via each connector's `run()` with `data_path` pointing to `/Downloads/mock_data_v2/`
3. Validate proof AQL query returns evidence row for CVE-2023-38408 / tenant MedPulse
4. Run TTL cleanup flow (no-op on fresh data; verifies flow executes)
5. Update VEX evidence service (additive `exploited_by` traversal)

---

## Open Questions

| ID | Question | Blocking? |
| --- | --- | --- |
| OQ-001 | CrowdStrike `behaviors[].cve_id` always present? | No — handled with skip |
| OQ-002 | Qualys QID→CVE via RESULTS text or structured field? | No — connector uses text pattern with graceful skip |
| OQ-003 | `blast_radius_score` field: exists on `vulnerabilities` node already? | Yes — must verify before proof query |
| OQ-004 | Prefect v2 vs v3 syntax for ttl_cleanup flow | Low — syntax difference only |
| OQ-005 | `network_exposure` as self-edge vs. separate `exposures` collection? | Decided: self-edge (simpler; device is both subject and context) |
