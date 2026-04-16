# Proposed Design — Situation Room + MiroFish Simulation Layer

## Design Version

- Current Version: `v3`

## Revision History

| Version | Trigger | Summary Of Changes | Related Review Round |
| --- | --- | --- | --- |
| v1 | Initial draft from `investigation-notes.md` + `requirements.md` `Design-ready` | Full 4-phase design: Phase 1 static UI, Phase 2 live AQL wiring, Phase 3 simulation schema + writeback, Phase 4 simulation visualization | Round 1 |
| v2 | Stage 5 Round 1 `Design Impact` findings F-001, F-002, F-003 | (1) 7-step write-back sequence expanded to cover all 8 edge collections — bundled writes for sim_ran_on, sim_triggered_by, chain_involves_component, playbook_addresses_finding, gap_violates_requirement; chain_informs_vex added to step 6. (2) simulation_runs schema updated with summary fields (chain_count, soc_blind_spot_count, top_playbook_action) written by post-completion summary UPSERT. | Round 2 |
| v3 | Stage 8 Design Impact re-entry: CISO/Board views exposed CVE IDs. New scope: SituationAbstractionLayer, CISOSituation/BoardSituation Pydantic models, threat_category_rollups + business_impact_findings + posture_snapshots collections, SimulationWritebackService step 8, MiroFish integration (trigger client, seed extractor, CFO/Board agent personas, monthly_posture_sim), CISO+Board frontend views rebuilt with business metrics | Re-entry Round 1 |

## Artifact Basis

- Investigation Notes: `tickets/in-progress/situation-room-and-simulation/investigation-notes.md`
- Requirements: `tickets/in-progress/situation-room-and-simulation/requirements.md`
- Requirements Status: `Refined`

---

## Summary

The Situation Room is a multi-persona proactive dashboard (CISO, Board/CFO, Engineering, Regulatory Affairs) that surfaces the top actionable items for each stakeholder without requiring search or query. It is built on the existing Complira Next.js 14 App Router frontend.

The MiroFish Simulation Layer extends the ArangoDB `complira_graph` with 13 new collections (5 document + 8 edge), a Python `SimulationWritebackService`, 4 new AQL chat tools, and a Phase 4 visualization panel. This ticket delivers the schema, write-back contract, and UI; MiroFish itself (the simulation engine) is out of scope.

Phases 1–4 are implemented and tested. v3 adds the `SituationAbstractionLayer` to enforce zero CVE ID leakage in CISO and Board/CFO views, introduces `CISOSituation` and `BoardSituation` Pydantic models, adds three new ArangoDB collections (`threat_category_rollups`, `business_impact_findings`, `posture_snapshots`), extends `SimulationWritebackService` with step 8 (threat category rollup), and integrates MiroFish trigger client and seed extractor for the new `monthly_posture_sim` trigger type with CFO and Board member agent personas.

Delivery is split into phases with independent shippability gates per phase.

---

## Goals

1. Expose `/dashboard/situation` — a 4-persona situation room, not a BI dashboard.
2. Inline attack-chain graph visualization with SOC blind-spot annotation.
3. "Ask Complira" deep-link from every alert card to pre-populated chat.
4. ArangoDB simulation schema and idempotent migration script.
5. Prefect-retry-safe write-back service (7-step, all UPSERT).
6. 4 new simulation chat tools registered in `_TOOL_REGISTRY`.
7. Phase 4 live simulation panel (polling, 3-second interval).
8. SituationAbstractionLayer: translate raw simulation graph → business-level CISOSituation/BoardSituation (zero CVE IDs in CISO/Board views).
9. Historical posture snapshots: time-series posture_score, attck_coverage_pct per tenant for monthly/quarterly trend arrows.
10. MiroFish integration: trigger client (POST /v1/mirofish/trigger), seed extractor AQL, CFO/Board agent persona config, monthly_posture_sim trigger type.
11. business_impact_findings: store CFO/board agent financial + governance outputs; feed BoardSituation.

---

## Legacy Removal Policy (Mandatory)

- Policy: `No backward compatibility; remove legacy code paths.`
- Required action: No legacy paths are being replaced by this ticket — all additions are net-new. The existing `/dashboard` utility overview page is not removed or modified; it serves a different purpose.

---

## Requirements And Use Cases

| Requirement ID | Description | Acceptance Criteria ID(s) | Acceptance Criteria Summary | Use Case IDs |
| --- | --- | --- | --- | --- |
| R-001 | `/dashboard/situation` route | AC-001, AC-002 | Route loads 200; sidebar nav entry visible | UC-01, UC-02, UC-03, UC-04 |
| R-002 | 4-persona views with Zustand state | AC-003, AC-004 | All 4 tabs render; switching updates content | UC-01 – UC-04, UC-07 |
| R-003 | Alert card inline drill-down | AC-005 | Toggle open/close, no page navigation | UC-05 |
| R-004 | Ask Complira integration | AC-006, AC-007 | Nav with encoded prompt; chat auto-submits | UC-06 |
| R-005 | AttackChainGraph component | AC-008, AC-009 | ≥3 nodes, SOC blind-spot edge in red | UC-05, UC-15 |
| R-006 | Phase 1 mock data fixture | AC-010 | Fixture shape matches AQL tool output | UC-01 – UC-07 |
| R-007 | Phase 2 live graph wiring (CISO) | AC-011, AC-012 | Real AQL data; empty state renders | UC-08, UC-09 |
| R-008 | Simulation ArangoDB schema | AC-013, AC-014 | Idempotent init; all 13 collections created | UC-10, UC-11 |
| R-009 | SimulationWritebackService | AC-015 – AC-018 | Idempotent run_all(); steps 6+7 after step 2 | UC-10 – UC-14 |
| R-010 | Simulation chat tools (4 new) | AC-019, AC-020 | Tools callable via Ask Complira | UC-10, UC-15, UC-17 |
| R-011 | Simulation visualization (Phase 4) | AC-021, AC-022 | SimulationResultCard and LivePanel render | UC-15 – UC-17 |
| R-012 | SituationAbstractionLayer | AC-023, AC-024 | CISO + Board API zero CVE IDs | UC-18, UC-19 |
| R-013 | CISO persona business-level view | AC-025, AC-026, AC-027 | Posture score, threat categories by tactic, MTTD | UC-18, UC-20 |
| R-014 | Board/CFO persona business-level view | AC-024 | Breach probability, financial exposure, no CVE IDs | UC-19, UC-21 |
| R-015 | Historical posture snapshots | AC-028, AC-029 | posture_delta computed from last 2 snapshots | UC-22 |
| R-016 | SimulationWritebackService step 8 | AC-030, AC-031 | rollup_threat_categories() after steps 1–7 | UC-23 |
| R-017 | MiroFish integration | AC-032, AC-033, AC-034 | Trigger + status endpoints; monthly_posture_sim | UC-24, UC-25 |
| R-018 | business_impact_findings collection | AC-035 | CFO/board agent outputs stored per run | UC-23, UC-26 |

---

## Codebase Understanding Snapshot (Pre-Design Mandatory)

| Area | Findings | Evidence (files/functions) | Open Unknowns |
| --- | --- | --- | --- |
| Entrypoints / Boundaries | `/dashboard/situation` is a new Next.js App Router route; backend API has `/v1/chat` SSE endpoint and existing AQL tool functions | `frontend/app/dashboard/layout.tsx`, `src/api/v1/endpoints/chat.py` | None |
| Current Naming Conventions | Frontend: `camelCase` components, `kebab-case` route dirs; Backend: `snake_case` Python modules | All existing `dashboard/` subdirs, `src/complira_graph/queries/` | None |
| Impacted Modules / Responsibilities | Frontend layout nav array (1 entry add); `chat.py` `_TOOL_REGISTRY` + `COMPLIRA_TOOLS` (4 new thin wrappers); new Python module `simulation_queries.py`; new service `writeback_service.py` | `dashboard/layout.tsx` lines 20-50, `chat.py` lines 2047–2110 | None |
| Data / Persistence / External IO | ArangoDB `complira_graph`; new collections only append-only per schema §6.5; no existing collection mutations | `simulation_schema_design_v1.1.docx`, `scripts/init_phase5_schema.py` | React Flow v12 dagre compatibility (OQ-02) |

---

## Current State (As-Is)

- **Frontend:** `/dashboard` = utility overview (API tokens, scans, KG nodes, recent scans). No `/dashboard/situation` route. No Zustand. No React Flow. `@radix-ui/react-tabs` is installed.
- **Backend:** `chat.py` has 4 fully implemented Phase 2 AQL tools (`get_attack_chain_analysis`, `get_active_threat_detections`, `get_regulatory_deadline_summary`, `get_patch_priority_list`). No simulation collections exist. No simulation query module. `chat.py` is 3,523 lines (exceeds 700-line code review threshold).
- **Database:** `complira_graph` has existing collections for scans, findings, CVEs, VEX, FAIR, IAM, controls. Zero simulation collections.
- **Scripts:** `scripts/init_phase5_schema.py` exists as canonical idempotent schema init pattern.

---

## Target State (To-Be)

- **Frontend:** New `/dashboard/situation` route with `SituationRoomPage`, `PersonaSwitcher` (Zustand), `MetricStrip`, `AlertFeed`, `AlertCard` (inline drill-down), `AttackChainGraph` (React Flow + dagre). Phase 4 adds `SimulationLivePanel` and `SimulationResultCard`. Phase 5 rebuilds CISO and Board/CFO views with business-level abstractions: posture score, threat categories by tactic bucket, MTTD/MTTR vs. target, compliance failures by framework, action priorities, breach probability, financial exposure, regulatory fine risk, historical trend arrows. New deps: `@xyflow/react`, `@dagrejs/dagre`, `zustand`.
- **Backend:** 4 new simulation chat tools as thin wrappers in `chat.py` backed by `simulation_queries.py`. New `GET /v1/simulation/{run_id}/status` endpoint in `src/api/v1/routers/simulation.py` (Phase 4). New `SituationAbstractionLayer` service and `CISOSituation`/`BoardSituation` Pydantic models. New `GET /v1/situation/ciso` and `GET /v1/situation/board` endpoints returning zero CVE IDs. New `POST /v1/mirofish/trigger` and `GET /v1/mirofish/status/{run_id}` endpoints.
- **Database:** 13 new simulation collections created by `scripts/init_simulation_schema.py`. Phase 5 adds 3 new collections: `threat_category_rollups`, `business_impact_findings`, `posture_snapshots`.
- **Service:** `src/complira_graph/simulation/writeback_service.py` — `SimulationWritebackService` class implementing 7-step UPSERT write-back sequence, extended in Phase 5 with step 8 `rollup_threat_categories()`.

### v3 Target State Additions

- New Python service: `src/complira_graph/situation/abstraction_layer.py` — `SituationAbstractionLayer` class with `compute_ciso(tenant_id)` and `compute_board(tenant_id)`
- New Pydantic models: `src/api/v1/models/situation_models.py` — `CISOSituation`, `BoardSituation`, `ThreatCategory`, `ControlFailure`, `ActionPriority`
- New AQL module: `src/complira_graph/queries/situation_abstraction_queries.py` — 8 AQL functions: `get_threat_category_rollup`, `get_compliance_failures_by_framework`, `get_simulated_mttd`, `get_posture_snapshot_history`, `get_business_impact_findings`, `get_attack_chain_findings_for_run`, `get_attck_coverage`, `get_latest_run_id`
- New DB collections (3): `threat_category_rollups`, `business_impact_findings`, `posture_snapshots`
- Modified: `SimulationWritebackService.run_all()` — adds step 8 `rollup_threat_categories()`
- Modified: `GET /v1/situation/ciso` — rebuilt to use `SituationAbstractionLayer`, returns `CISOSituation`
- New endpoint: `GET /v1/situation/board` — returns `BoardSituation`
- New module: `src/complira_graph/mirofish/` — trigger client + seed extractor
- New endpoints: `POST /v1/mirofish/trigger`, `GET /v1/mirofish/status/{run_id}`
- Modified: CISO frontend view — posture score, threat categories, MTTD/MTTR, compliance failures, action priorities, historical trend arrows
- Modified: Board/CFO frontend view — breach probability, financial exposure, regulatory fine risk, governance priorities
- Engineering + RegAffairs views: UNCHANGED

---

## Architecture Direction Decision (Mandatory)

- **Chosen direction:** Additive layering — new route, new component tree, new Python service module, new query module. All net-new; zero modification of existing collection schemas.
- **Rationale:**
  - *Complexity:* Adding alongside existing code is lower risk than modifying shared modules.
  - *Testability:* `simulation_queries.py` module is independently testable. Frontend components are independently testable with fixture data.
  - *Operability:* Idempotent init script can be run safely in any environment order.
  - *Evolution cost:* Phase 2 fixture-to-live-data swap requires only data source change in CISO view — component logic is unchanged (R-006).
- **Layering fitness assessment:** `Yes` — existing layering is coherent; no structural changes needed.
- **Outcome:** `Add` (new route, new module, new service directory, new script) + `Modify` (nav entry, `chat.py` thin wrappers, `package.json` deps).

### Alternatives

| Option | Summary | Pros | Cons | Decision | Rationale |
| --- | --- | --- | --- | --- | --- |
| A (Chosen) | New `/dashboard/situation` route alongside existing `/dashboard` | Zero risk to existing pages; independent deployable | Two dashboard routes in sidebar | Chosen | Requirements explicitly require new route (R-001, F-02) |
| B | Replace existing `/dashboard` with situation room | Simpler nav | Breaks existing utility page used by other personas | Rejected | Existing dashboard serves different purpose |
| C | SSE for SimulationLivePanel | Reuses existing SSE infrastructure | Requires new SSE route; overkill for Phase 4 demo | Rejected | 3-second polling on dedicated status endpoint is simpler (OQ-03 resolved) |

---

## SituationAbstractionLayer Architecture

The `SituationAbstractionLayer` sits between `complira_graph` and the `/v1/situation/` API endpoints. It is the single point that translates simulation node data to business language. The simulation never knows it feeds a business view — it just runs and writes to the graph. The abstraction layer decides what surfaces to whom.

```
complira_graph (ArangoDB)
    attack_chain_findings
    compliance_gap_findings
    threat_category_rollups      ← written by SimulationWritebackService step 8
    business_impact_findings     ← written by MiroFish monthly_posture_sim write-back
    posture_snapshots            ← written by SituationAbstractionLayer on each compute
         ↓
SituationAbstractionLayer
    compute_ciso(tenant_id) → CISOSituation
    compute_board(tenant_id) → BoardSituation
         ↓
/v1/situation/ciso    (zero CVE IDs)
/v1/situation/board   (zero CVE IDs)
```

**Pull model (intentional):** `SituationAbstractionLayer` is pull-only. `posture_snapshots` are written on each `GET /v1/situation/ciso` API request, not triggered by `SimulationWritebackService.run_all()` completion. This is intentional: push-triggering would create a circular dependency between `writeback_service.py` and `abstraction_layer.py`, violating the allowed dependency direction. The trade-off is that CISO/Board views show data from the previous posture computation until the next page load after a new simulation completes.

**Posture score formula:**

```python
posture = 100
posture -= round(mean(c.chain_probability for c in chains) * 40)  # breach signal
posture -= len(gaps) * 3                                           # compliance gaps
posture -= round(soc_miss_rate(chains) * 20)                       # detection gaps
posture += round(attck_coverage * 0.1)                             # coverage credit
posture = max(0, min(100, posture))
```

**Threat category tactic buckets:**

```python
TACTIC_BUCKETS = {
    "remote_code_execution":   ["T1190", "T1059", "T1203", "T1210"],
    "credential_exposure":     ["T1552", "T1078", "T1539", "T1111"],
    "cloud_misconfiguration":  ["T1580", "T1098", "T1530"],
    "patch_gaps":              ["T1190"],  # firmware-specific via EMBA flag
}
```

---

## Pydantic Data Models (CISOSituation, BoardSituation)

```python
class ThreatCategory(BaseModel):
    bucket_name: str          # "remote_code_execution"
    display_name: str         # "Remote code execution"
    breach_probability: float # max chain_probability in bucket
    critical_asset_count: int
    trend: str | None         # "up" | "down" | "stable"

class ControlFailure(BaseModel):
    framework: str            # "CRA Article 13"
    failure_count: int
    coverage_pct: float | None

class ActionPriority(BaseModel):
    rank: int
    description: str
    owner: str
    due_label: str            # "18h" | "this sprint" | "47 days"
    urgency: str              # "overdue" | "in_progress" | "upcoming"

class CISOSituation(BaseModel):
    posture_score: int                    # 0–100
    posture_delta: int | None             # vs last snapshot
    attck_coverage_pct: float
    attck_coverage_delta: float | None
    remediation_sla_pct: float | None  # enrichment-ready: None until SLA deadline tracking added to response_playbook_steps
    control_failure_count: int
    threat_categories: list[ThreatCategory]
    control_failures: list[ControlFailure]
    mttd_hours: float
    mttd_target_hours: float
    mttr_days: float | None       # enrichment-ready: None until playbook step timing data available
    mttr_target_days: float
    action_priorities: list[ActionPriority]
    snapshot_timestamp: str

class BoardSituation(BaseModel):
    breach_probability_pct: float
    breach_probability_delta: float | None
    financial_exposure_usd_low: int
    financial_exposure_usd_high: int
    regulatory_fine_risk: list[dict]      # [{"framework": "NIS2", "max_fine_usd": ...}] — Uses business_impact_findings.framework structured field (NOT narrative string matching). Framework value set at write-back time.
    reputational_risk_score: float        # 0–1
    board_priorities: list[ActionPriority]
    snapshot_timestamp: str
```

---

## MiroFish Integration Architecture

```
Complira-side only. MiroFish engine is external.

POST /v1/mirofish/trigger
    body: {trigger_type, tenant_id, cve_id?}
    → MiroFishTriggerClient.trigger(trigger_type, seed)
    → returns {run_id, status: "queued"}

GET /v1/mirofish/status/{run_id}
    → MiroFishTriggerClient.get_status(run_id)
    → returns {run_id, status, started_at, completed_at}
```

**Trigger types:**

- `kev_triggered`: existing path — 40 rounds, attacker+defender+regulator agents, seeds from KEV CVE subgraph
- `monthly_posture_sim`: new — 50 rounds, adds cfo_agent + board_member_agent to agent_config, seeds from full product surface AQL export, writes to business_impact_findings + threat_category_rollups

**CFO + Board member agent personas (added to `monthly_posture_sim` agent_config only):**

```python
{"type": "cfo_agent", "persona": "CFO of a mid-market medical device manufacturer. Focused on financial exposure from regulatory non-compliance and breach recovery costs. Reacts to regulator agent actions with financial impact estimates.", "memory_config": {"financial_threshold": 1000000, "currency": "USD"}},
{"type": "board_member_agent", "persona": "Non-executive board member with fiduciary duty. Focused on disclosure obligations, reputational risk, and regulatory fine exposure. Reacts to compliance gap findings with governance concerns.", "memory_config": {"reporting_frameworks": ["SEC", "NIS2", "CRA"]}}
```

**Authentication:** `MiroFishTriggerClient` sends `Authorization: Bearer {MIROFISH_API_KEY}` header on all requests. Key read from `MIROFISH_API_KEY` environment variable at startup. Missing or empty key raises `ConfigurationError` on application startup. Key is never logged or included in error responses.

**Seed extractor AQL (`extract_monthly_posture_seed`):** exports full product surface subgraph — all components, CVEs, CWEs, compliance requirements for tenant. Output: JSON matching MiroFish seed schema.

---

## New ArangoDB Collections (v3 additions — 3 new)

**`threat_category_rollups`** (document):
- `_key`: `{run_id}_{bucket_name}`
- `run_id`, `tenant_id`, `bucket_name`, `display_name`, `max_chain_probability`, `critical_asset_count`, `technique_ids[]`, `source: "mirofish_simulation"`

**`business_impact_findings`** (document):
- `_key`: `{run_id}_{agent_type}_{impact_type}`
- `run_id`, `tenant_id`, `agent_type` (cfo_agent|board_member_agent), `impact_type` (financial_exposure|regulatory_fine_risk|reputational_risk|disclosure_obligation), `framework` (str | None): structured framework identifier (e.g., "NIS2", "SEC", "CRA") — present when `impact_type = "regulatory_fine_risk"`; eliminates narrative string matching in `compute_board()`, `estimated_value`, `currency`, `narrative`, `confidence`, `source: "mirofish_simulation"`

**`posture_snapshots`** (document):
- `_key`: `{tenant_id}_{iso_timestamp}`
- `tenant_id`, `posture_score`, `attck_coverage_pct`, `remediation_sla_pct`, `control_failure_count`, `mttd_hours`, `breach_probability_pct`, `computed_at` (ISO timestamp), `run_id` (latest run used)

---

## Architecture Boundary for SituationAbstractionLayer

| Layer | Owns | Must Not Own |
|---|---|---|
| `situation/abstraction_layer.py` | posture_score computation, threat category mapping, business metric derivation, posture_snapshot write (compute_ciso only — compute_board MUST NOT write posture_snapshots) | AQL (delegates to situation_abstraction_queries), API schema (delegates to situation_models) |
| `queries/situation_abstraction_queries.py` | AQL read queries for abstraction layer | Write operations (except snapshot write, which is owned by abstraction_layer) |
| `api/v1/models/situation_models.py` | Pydantic models: CISOSituation, BoardSituation, sub-models | Business logic |
| `mirofish/trigger_client.py` | HTTP client calls to MiroFish engine | Seed extraction (delegates to seed_extractor), simulation write-back (delegates to writeback_service) |
| `mirofish/seed_extractor.py` | AQL export of product surface subgraph | MiroFish API calls |

---

## Engineering + RegAffairs Views: Unchanged

Engineering persona: unchanged. Full CVE detail, patch priority list, affected packages, CVSS scores remain. No modifications to Engineering view.

Regulatory Affairs persona: unchanged. Compliance deadline calendar, control-to-violation mapping remain. No modifications.

---

## Change Inventory (Delta)

| Change ID | Change Type | Current Path | Target Path | Rationale | Impacted Areas | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| C-001 | Add | — | `frontend/app/dashboard/situation/page.tsx` | New route (R-001) | Frontend route | Phase 1 |
| C-002 | Add | — | `frontend/lib/stores/situation-store.ts` | Zustand persona state (R-002) | Frontend state | Phase 1 |
| C-003 | Add | — | `frontend/components/situation/PersonaSwitcher.tsx` | Persona tab switcher (R-002) | Frontend component | Phase 1 |
| C-004 | Add | — | `frontend/components/situation/MetricStrip.tsx` | 4-card metric row per persona (R-002) | Frontend component | Phase 1 |
| C-005 | Add | — | `frontend/components/situation/AlertFeed.tsx` | Alert card list (R-003) | Frontend component | Phase 1 |
| C-006 | Add | — | `frontend/components/situation/AlertCard.tsx` | Collapsible alert card with drill-down + Ask button (R-003, R-004) | Frontend component | Phase 1 |
| C-007 | Add | — | `frontend/components/situation/AttackChainGraph.tsx` | React Flow attack chain graph, dagre layout (R-005) | Frontend component | Phase 1 |
| C-008 | Add | — | `frontend/src/fixtures/aquadrive_tenant.json` | Phase 1 mock data fixture (R-006) | Frontend fixture | Phase 1 |
| C-009 | Modify | `frontend/app/dashboard/layout.tsx` | same | Add "Situation Room" nav entry (R-001) | Frontend nav | Phase 1 |
| C-010 | Modify | `frontend/package.json` | same | Add `@xyflow/react`, `@dagrejs/dagre`, `zustand` (F-01) | Frontend deps | Phase 1 |
| C-011 | Modify | `frontend/app/dashboard/chat/page.tsx` | same | Auto-submit on `?prompt=` mount (R-004, AC-007) | Frontend chat | Phase 1 |
| C-012 | Modify | `frontend/app/dashboard/situation/page.tsx` | same | Phase 2: replace fixture with real AQL tool calls (R-007) | Frontend CISO view | Phase 2 |
| C-013 | Add | — | `scripts/init_simulation_schema.py` | Idempotent schema migration — 13 new collections (R-008) | Database | Phase 3 |
| C-014 | Add | — | `src/complira_graph/simulation/__init__.py` | New module package | Backend module | Phase 3 |
| C-015 | Add | — | `src/complira_graph/simulation/writeback_service.py` | `SimulationWritebackService` 7-step UPSERT (R-009) | Backend service | Phase 3 |
| C-016 | Add | — | `src/complira_graph/queries/simulation_queries.py` | AQL query functions for 4 new tools (R-010) | Backend queries | Phase 3 |
| C-017 | Modify | `src/api/v1/endpoints/chat.py` | same | 4 new thin wrapper entries in `_TOOL_REGISTRY` + `COMPLIRA_TOOLS` (R-010) | Backend chat endpoint | Phase 3 |
| C-018 | Add | — | `frontend/components/situation/SimulationLivePanel.tsx` | Live round counter + event feed (R-011) | Frontend component | Phase 4 |
| C-019 | Add | — | `frontend/components/situation/SimulationResultCard.tsx` | Completed run summary card (R-011) | Frontend component | Phase 4 |
| C-020 | Add | — | `src/api/v1/routers/simulation.py` | `GET /v1/simulation/{run_id}/status` polling endpoint (R-011) | Backend API | Phase 4 |
| C-021 | Modify | `src/api/v1/main.py` (or router registry) | same | Register simulation router (Phase 4) | Backend routing | Phase 4 |
| C-022 | Add | — | `src/complira_graph/situation/__init__.py` | New situation module package | Backend module | Phase 5 |
| C-023 | Add | — | `src/complira_graph/situation/abstraction_layer.py` | SituationAbstractionLayer service | Backend service | Phase 5 |
| C-024 | Add | — | `src/api/v1/models/situation_models.py` | CISOSituation + BoardSituation Pydantic models | Backend models | Phase 5 |
| C-025 | Add | — | `src/complira_graph/queries/situation_abstraction_queries.py` | 5 AQL functions for abstraction layer | Backend queries | Phase 5 |
| C-026 | Modify | `src/api/v1/endpoints/situation.py` | same | Rebuild GET /v1/situation/ciso to use SituationAbstractionLayer | Backend API | Phase 5 |
| C-027 | Add | — | `src/api/v1/endpoints/situation.py` | Add GET /v1/situation/board endpoint | Backend API | Phase 5 |
| C-028 | Modify | `scripts/init_simulation_schema.py` | same | Add 3 new collections: threat_category_rollups, business_impact_findings, posture_snapshots | Database | Phase 5 |
| C-029 | Modify | `src/complira_graph/simulation/writeback_service.py` | same | Add step 8: rollup_threat_categories() | Backend service | Phase 5 |
| C-030 | Add | — | `src/complira_graph/mirofish/__init__.py` | MiroFish integration module package | Backend module | Phase 6 |
| C-031 | Add | — | `src/complira_graph/mirofish/trigger_client.py` | MiroFishTriggerClient: trigger + status polling | Backend service | Phase 6 |
| C-032 | Add | — | `src/complira_graph/mirofish/seed_extractor.py` | extract_monthly_posture_seed() AQL seed export | Backend queries | Phase 6 |
| C-033 | Add | — | `src/api/v1/endpoints/mirofish.py` | POST /v1/mirofish/trigger + GET /v1/mirofish/status/{run_id} | Backend API | Phase 6 |
| C-034 | Modify | `src/api/v1/router.py` | same | Register mirofish router | Backend routing | Phase 6 |
| C-035 | Modify | `frontend/app/dashboard/situation/page.tsx` | same | Rebuild CISO view: posture score, threat categories, MTTD/MTTR, compliance failures, action priorities, trend arrows | Frontend route | Phase 5 |
| C-036 | Modify | `frontend/app/dashboard/situation/page.tsx` | same | Rebuild Board/CFO view: breach probability, financial exposure, regulatory fine risk, board priorities | Frontend route | Phase 5 |
| C-037 | Add | — | `frontend/components/situation/PostureScoreCard.tsx` | CISO posture score with trend arrow | Frontend component | Phase 5 |
| C-038 | Add | — | `frontend/components/situation/ThreatCategoryList.tsx` | CISO threat categories with breach probability bars | Frontend component | Phase 5 |
| C-039 | Add | — | `frontend/components/situation/ComplianceFailurePanel.tsx` | Framework-grouped compliance failures | Frontend component | Phase 5 |
| C-040 | Add | — | `frontend/components/situation/SimulatedMetricCard.tsx` | MTTD/MTTR actual vs target with trend | Frontend component | Phase 5 |
| C-041 | Add | — | `frontend/components/situation/ActionPriorityList.tsx` | Top 3 action priorities with owner + urgency badge | Frontend component | Phase 5 |
| C-042 | Add | — | `frontend/components/situation/BoardMetricPanel.tsx` | Board breach probability + financial exposure | Frontend component | Phase 5 |
| C-043 | Add | — | `frontend/lib/types/situation.ts` additions | CISOSituation, BoardSituation, ThreatCategory TypeScript interfaces | Frontend types | Phase 5 |

---

## Target Architecture Shape And Boundaries (Mandatory)

| Layer/Boundary | Purpose | Owns | Must Not Own | Notes |
| --- | --- | --- | --- | --- |
| `frontend/app/dashboard/situation/` | Route + page container | Route layout, data fetch orchestration (Phase 2+), fixture import (Phase 1) | Business logic, graph query detail | Next.js App Router server/client boundary |
| `frontend/lib/stores/situation-store.ts` | Client-side persona state | Active persona enum, session-scoped state | Server data, API calls | Zustand store; no persistence across page load |
| `frontend/components/situation/` | Presentational + interactive UI | Rendering, expand/collapse, Ask button navigation | State management (delegates to store), API calls | Each component owns one clear concern |
| `src/complira_graph/situation/` | Abstraction layer service | Business metric computation, posture score formula, tactic bucket mapping, snapshot persistence | AQL (delegates to situation_abstraction_queries), API schema (delegates to situation_models) | New module directory; v3 addition |
| `src/complira_graph/simulation/` | Simulation write-back service | 7-step UPSERT orchestration + step 8 rollup, data transformation to ArangoDB documents | Query logic (delegates to simulation_queries), API routing | New module directory |
| `src/complira_graph/queries/simulation_queries.py` | AQL read queries for simulation collections | AQL query functions (get_simulation_runs, get_attack_chains_for_cve, get_playbook_for_run, get_compliance_gaps_for_run) | Write operations, API schema | Follows existing `multihop_queries.py` pattern |
| `src/complira_graph/queries/situation_abstraction_queries.py` | AQL read queries for abstraction layer | 8 AQL functions: get_threat_category_rollup, get_compliance_failures_by_framework, get_simulated_mttd, get_posture_snapshot_history, get_business_impact_findings, get_attack_chain_findings_for_run, get_attck_coverage, get_latest_run_id | Write operations, business logic | v3 addition |
| `src/complira_graph/mirofish/` | MiroFish trigger client + seed extractor | HTTP trigger client, status polling, product surface seed AQL export | Simulation write-back (delegates to writeback_service) | v3 Phase 6 addition |
| `src/api/v1/endpoints/chat.py` | Chat tool registry + SSE streaming | Thin tool wrappers, tool routing, SSE emit | Full AQL implementation (delegates to query modules) | Only 4 thin wrapper entries added; full AQL stays in `simulation_queries.py` |
| `src/api/v1/routers/simulation.py` | Phase 4 status polling | `GET /v1/simulation/{run_id}/status` response | Simulation logic | Reads `simulation_runs` collection |
| `src/api/v1/endpoints/situation.py` | CISO + Board API endpoints | GET /v1/situation/ciso (returns CISOSituation), GET /v1/situation/board (returns BoardSituation) | Business logic computation (delegates to SituationAbstractionLayer) | v3 modification. RBAC: soft-open — any authenticated tenant user may call any persona endpoint. Persona-level role gating is deferred (add role check to Depends() chain when required). |
| `src/api/v1/endpoints/mirofish.py` | MiroFish API endpoints | POST /v1/mirofish/trigger, GET /v1/mirofish/status/{run_id} | Trigger logic (delegates to trigger_client), seed extraction (delegates to seed_extractor) | v3 Phase 6 addition |
| `src/api/v1/models/situation_models.py` | Pydantic response models | CISOSituation, BoardSituation, ThreatCategory, ControlFailure, ActionPriority | Business logic | v3 addition |
| `scripts/init_simulation_schema.py` | One-time idempotent schema migration | Collection + index creation (16 total: 13 original + 3 v3) | Application business logic | Follows `init_phase5_schema.py` pattern exactly |

---

## File And Module Breakdown

| File/Module | Change Type | Layer / Boundary | Concern / Responsibility | Public APIs | Inputs/Outputs | Dependencies |
| --- | --- | --- | --- | --- | --- | --- |
| `situation/page.tsx` | Add | Route container | Orchestrates persona view rendering, fixture/API data | React Server Component + `"use client"` sub-tree | Fixture JSON (Phase 1) → page props | `situation-store`, all situation components |
| `situation-store.ts` | Add | Client state | Active persona enum (CISO/Board/Engineering/RegAffairs) | `usePersona()`, `setPersona()` | `PersonaType` enum | `zustand` |
| `PersonaSwitcher.tsx` | Add | UI component | Renders 4 persona tabs, highlights active, calls `setPersona` | `<PersonaSwitcher />` | `PersonaType` in/out | `situation-store`, `@radix-ui/react-tabs` |
| `MetricStrip.tsx` | Add | UI component | Renders 4 metric cards for active persona | `<MetricStrip metrics={[]} />` | `MetricCard[]` array | Tailwind |
| `AlertFeed.tsx` | Add | UI component | Maps alert list to `AlertCard` items | `<AlertFeed alerts={[]} />` | `AlertItem[]` array | `AlertCard` |
| `AlertCard.tsx` | Add | UI component | Expandable card: title, severity, drill-down content, Ask Complira button | `<AlertCard item={} />` | `AlertItem` with `ask_prompt` | `@xyflow/react` (for chain type), `next/navigation` |
| `AttackChainGraph.tsx` | Add | UI component | React Flow graph: CVE→CWE→Technique→IAM→Outcome nodes, dagre layout, SOC blind-spot edge annotation | `<AttackChainGraph chain={} />` | `ChainNode[]`, `ChainEdge[]` | `@xyflow/react`, `@dagrejs/dagre` |
| `aquadrive_tenant.json` | Add | Fixture | Static mock data matching AQL tool output shapes exactly | JSON import | Fixture data → situation page | None |
| `dashboard/layout.tsx` | Modify | Nav layout | Add Situation Room nav entry | Nav array | — | `lucide-react` (LayoutGrid icon) |
| `chat/page.tsx` | Modify | Chat UI | Auto-submit on `?prompt=` query param on mount | `useEffect` on mount | URL `?prompt=` param → `sendMessage()` | Already-existing `sendMessage` fn |
| `init_simulation_schema.py` | Add/Modify | DB migration | Create 5 doc + 8 edge collections + indexes + 3 v3 collections, idempotent | `python init_simulation_schema.py` | ArangoDB connection env vars | `python-arango`, `CollectionCreateError` |
| `simulation/__init__.py` | Add | Module | Package marker | — | — | — |
| `writeback_service.py` | Add/Modify | Write-back service | `SimulationWritebackService.run_all(report, run_key)` — 7-step UPSERT + step 8 rollup | `run_all(report, run_key)` | MiroFish report dict → ArangoDB documents | `simulation_queries`, `python-arango` |
| `simulation_queries.py` | Add | Query module | 4 AQL read functions for simulation collections | `get_simulation_runs()`, `get_attack_chains_for_cve()`, `get_playbook_for_run()`, `get_compliance_gaps_for_run()` | `tenant_id`, optional filters → list of dicts | `python-arango` |
| `chat.py` | Modify | Chat endpoint | 4 thin wrapper entries in `_TOOL_REGISTRY` + `COMPLIRA_TOOLS` | New `_tool_get_simulation_*` wrappers | Delegates to `simulation_queries` | `simulation_queries` module |
| `routers/simulation.py` | Add | API router | Phase 4 status endpoint | `GET /v1/simulation/{run_id}/status` | `run_id` path param → `SimulationStatusResponse` | `simulation_queries` |
| `SimulationLivePanel.tsx` | Add | UI component | Phase 4: active run panel, 3s poll, round counter, event feed (significance ≥ 0.6) | `<SimulationLivePanel runId={} />` | `run_id` → polled status | `GET /v1/simulation/{run_id}/status` |
| `SimulationResultCard.tsx` | Add | UI component | Phase 4: completed run summary (chain count, SOC blind spots, top action, Ask button) | `<SimulationResultCard run={} />` | `SimulationRun` | `AlertCard` (Ask Complira pattern) |
| `situation/__init__.py` | Add | Module | New situation module package marker | — | — | — |
| `abstraction_layer.py` | Add | Abstraction service | `SituationAbstractionLayer.compute_ciso(tenant_id)` → `CISOSituation`; `compute_board(tenant_id)` → `BoardSituation`; persists posture_snapshot | `compute_ciso(tenant_id)`, `compute_board(tenant_id)` | tenant_id → CISOSituation or BoardSituation | `situation_abstraction_queries`, `situation_models`, `python-arango` |
| `situation_models.py` | Add | API models | `CISOSituation`, `BoardSituation`, `ThreatCategory`, `ControlFailure`, `ActionPriority` Pydantic models | Model classes | — | `pydantic` |
| `situation_abstraction_queries.py` | Add | Query module | 8 AQL read functions for abstraction layer | `get_threat_category_rollup()`, `get_compliance_failures_by_framework()`, `get_simulated_mttd()`, `get_posture_snapshot_history()`, `get_business_impact_findings()`, `get_attack_chain_findings_for_run(db, tenant_id, run_id=None)` — returns individual chain_probability values for the posture score formula; `run_id=None` means latest completed run. Returns projected fields only: `{chain_probability, soc_threshold_miss}` — NEVER returns full document including `chain_steps[]` to prevent CVE data entering the abstraction compute path., `get_attck_coverage(db, tenant_id)` — returns float (0–100): distinct technique_ids across tenant's threat_category_rollups / configured ATT&CK universe size × 100, `get_latest_run_id(db, tenant_id)` — returns latest completed simulation_runs._key for tenant (used for staleness check in UC-27) | tenant_id, optional run_id → dicts | `python-arango` |
| `endpoints/situation.py` | Modify | API endpoint | Rebuild GET /v1/situation/ciso; add GET /v1/situation/board | Both endpoints | tenant_id query param → CISOSituation or BoardSituation JSON | `SituationAbstractionLayer` |
| `mirofish/__init__.py` | Add | Module | MiroFish integration package marker | — | — | — |
| `trigger_client.py` | Add | MiroFish client | `MiroFishTriggerClient.trigger(trigger_type, seed)` and `get_status(run_id)` | `trigger(trigger_type, seed)`, `get_status(run_id)` | trigger config + seed → run_id; run_id → status dict | `httpx` or `requests`, MiroFish external API |
| `seed_extractor.py` | Add | Seed query module | `extract_monthly_posture_seed(tenant_id)` — AQL full product surface subgraph export | `extract_monthly_posture_seed(tenant_id)` | tenant_id → seed JSON dict | `python-arango` |
| `endpoints/mirofish.py` | Add | API endpoint | POST /v1/mirofish/trigger; GET /v1/mirofish/status/{run_id} | Both endpoints | trigger body → run_id; run_id path param → status | `MiroFishTriggerClient`, `seed_extractor` |
| `PostureScoreCard.tsx` | Add | UI component | CISO posture score (0–100) with trend arrow and delta | `<PostureScoreCard score={} delta={} />` | posture_score, posture_delta | Tailwind |
| `ThreatCategoryList.tsx` | Add | UI component | CISO threat categories with breach probability bars; no CVE IDs | `<ThreatCategoryList categories={[]} />` | `ThreatCategory[]` | Tailwind |
| `ComplianceFailurePanel.tsx` | Add | UI component | Framework-grouped compliance failures (CRA, IEC 62304, NIS2, NIST CSF) | `<ComplianceFailurePanel failures={[]} />` | `ControlFailure[]` | Tailwind |
| `SimulatedMetricCard.tsx` | Add | UI component | MTTD/MTTR actual vs target with trend indicator | `<SimulatedMetricCard actual={} target={} label={} />` | actual, target floats + label | Tailwind |
| `ActionPriorityList.tsx` | Add | UI component | Top 3 action priorities with owner, due label, urgency badge | `<ActionPriorityList priorities={[]} />` | `ActionPriority[]` | Tailwind |
| `BoardMetricPanel.tsx` | Add | UI component | Board breach probability + financial exposure range + regulatory fine risk | `<BoardMetricPanel situation={} />` | `BoardSituation` | Tailwind |

---

## Layer-Appropriate Separation Of Concerns Check

- **UI/frontend scope:** Each component owns exactly one concern. `situation-store.ts` owns persona state only. `AttackChainGraph.tsx` owns graph rendering only. `AlertCard.tsx` owns expand/collapse + Ask Complira navigation only. The page container owns data orchestration only. Phase 5 business-metric components each own one display concern: `PostureScoreCard` owns score + trend, `ThreatCategoryList` owns tactic-bucket display, `BoardMetricPanel` owns Board-level metrics only.
- **Non-UI scope (backend):** `simulation_queries.py` owns AQL read logic only. `writeback_service.py` owns write-back orchestration only. `chat.py` thin wrappers own tool routing only (no AQL inline). `routers/simulation.py` owns Phase 4 status API only. `abstraction_layer.py` owns business metric computation only — delegates AQL to `situation_abstraction_queries.py`. `trigger_client.py` owns HTTP calls to MiroFish only. `seed_extractor.py` owns AQL seed export only.
- **Integration/infra scope:** `init_simulation_schema.py` owns schema migration only. It does not contain application logic.

---

## Naming Decisions (Natural And Implementation-Friendly)

| Item Type | Current Name | Proposed Name | Reason | Notes |
| --- | --- | --- | --- | --- |
| File | — | `situation/page.tsx` | Matches route path `/dashboard/situation`; consistent with App Router convention | |
| File | — | `situation-store.ts` | Standard Zustand store naming in this project | |
| File | — | `AttackChainGraph.tsx` | "AttackChain" = domain term; "Graph" = visual type | Consistent with React Flow component naming |
| File | — | `SimulationLivePanel.tsx` | "Live" = active run state; "Panel" = UI container type | |
| File | — | `SimulationResultCard.tsx` | "Result" = completed run; "Card" = card UI component type | |
| Module | — | `simulation_queries.py` | Parallel naming to `multihop_queries.py`, `deployment_reality_queries.py` | |
| Module | — | `writeback_service.py` | "Writeback" = domain operation; "Service" = orchestration class | |
| API | — | `GET /v1/simulation/{run_id}/status` | RESTful sub-resource; `status` is the sub-resource read | |
| Class | — | `SimulationWritebackService` | PascalCase Python class; domain + operation + type | |
| Class | — | `SituationAbstractionLayer` | "Situation" = domain; "Abstraction" = transformation role; "Layer" = architectural position | v3 |
| Module | — | `situation_abstraction_queries.py` | Parallel naming to `simulation_queries.py`; "abstraction" distinguishes from raw simulation queries | v3 |
| Module | — | `trigger_client.py` | "Trigger" = operation; "Client" = external HTTP dependency pattern | v3 |
| Module | — | `seed_extractor.py` | "Seed" = MiroFish domain term; "Extractor" = data export operation | v3 |

---

## Naming Drift Check (Mandatory)

| Item | Current Responsibility | Does Name Still Match? | Corrective Action | Mapped Change ID |
| --- | --- | --- | --- | --- |
| `aquadrive_tenant.json` | Mock fixture data for "Aquadrive" demo tenant | Yes — fixture name = demo tenant name | N/A | C-008 |
| `simulation_queries.py` | AQL read queries for simulation collections | Yes | N/A | C-016 |
| `writeback_service.py` | 7-step UPSERT write-back + step 8 rollup | Yes — step 8 is still write-back orchestration | N/A | C-015, C-029 |
| `chat.py` | Chat endpoint; now also registers 4 simulation tools | Yes — still primarily the chat endpoint | N/A; new tools are thin wrappers only | C-017 |
| `situation_abstraction_queries.py` | AQL read queries for the abstraction layer (not raw simulation) | Yes — "abstraction" qualifier prevents confusion with `simulation_queries.py` | N/A | C-025 |

---

## Existing-Structure Bias Check (Mandatory)

| Candidate Area | Current-File-Layout Bias Risk | Architecture-First Alternative | Decision | Why |
| --- | --- | --- | --- | --- |
| Simulation AQL queries | Medium — could put AQL inline in `chat.py` (existing pattern) | Separate `simulation_queries.py` module | Change | `chat.py` is 3,523 lines, over 700-line threshold; inline would compound the problem (F-09) |
| Simulation write-back | Low — no existing pattern to bias toward | New `simulation/` directory | Change (Add) | Write-back is not a query; owns a distinct orchestration concern |
| Frontend components | Low — could put all in `dashboard/` root | Dedicated `components/situation/` directory | Change (Add) | 8+ components need a home; directory-level grouping by feature is correct for App Router |
| Phase 4 status endpoint | Medium — could add to `chat.py` or existing endpoints | New `routers/simulation.py` | Change (Add) | Simulation runtime is a distinct domain from chat streaming |
| SituationAbstractionLayer placement | Medium — could inline in `situation.py` endpoint | Dedicated `situation/` module directory | Change (Add) | Abstraction logic is complex enough for its own service; endpoint stays thin |
| MiroFish trigger client | Low — could inline in endpoint | Dedicated `mirofish/` module directory | Change (Add) | External HTTP client + seed AQL are two distinct concerns; module boundary enforces it |

---

## Anti-Hack Check (Mandatory)

| Candidate Change | Shortcut/Hack Risk | Proper Structural Fix | Decision | Notes |
| --- | --- | --- | --- | --- |
| Add simulation AQL directly in `chat.py` wrappers | High — would bloat already-oversized file | `simulation_queries.py` module with thin wrappers in `chat.py` | Proper fix | `chat.py` already over 700-line threshold |
| Use React Flow v11 `reactflow` if v12 dagre has issues | Low — legitimate fallback | Try `@xyflow/react` v12 first; fall back to `reactflow` only if dagre incompatibility confirmed | Acceptable fallback | OQ-02: confirm dagre compatibility during Phase 1 |
| Inline simulation status in existing SSE endpoint | Medium — would conflate chat SSE with simulation polling | Dedicated `GET /v1/simulation/{run_id}/status` REST endpoint | Proper fix | REST polling is simpler and correct for this use case |
| Mutate `fair_scenarios` docs from write-back (tempting shortcut for FAIR calibration) | High — schema §6.5 says append-only | `chain_calibrates_fair` edge carries `tef_input`; FAIR tool reads the edge | Proper fix — edge only | AC-016 must never mutate VEX; AC-017 confidence gate enforced |
| Filter CVE IDs from existing CISO endpoint response (search-and-strip) | High — fragile, misses nested fields, not testable | Dedicate SituationAbstractionLayer that never reads CVE ID fields into its data models | Proper fix | AC-023/AC-024 assert zero leakage; structural prevention is the only safe guarantee |
| Reuse kev_triggered seed for monthly_posture_sim | Medium — KEV subgraph is a subset; board persona needs full product surface | Separate `extract_monthly_posture_seed()` AQL that exports full product surface | Proper fix | monthly_posture_sim needs all components, not just KEV-related nodes |

---

## Dependency Flow And Cross-Reference Risk

| Module/File | Upstream Dependencies | Downstream Dependents | Cross-Reference Risk | Mitigation / Boundary Strategy |
| --- | --- | --- | --- | --- |
| `simulation_queries.py` | `python-arango`, ArangoDB `complira_graph` | `writeback_service.py` (read step), `chat.py` (tool wrappers), `routers/simulation.py` (status) | Low | Pure query module; no write operations |
| `writeback_service.py` | `simulation_queries.py`, `python-arango` | Prefect task (out of scope) | Low | No circular deps; called by external orchestrator only |
| `chat.py` | `simulation_queries.py` (new), all other query modules (existing) | Frontend `/dashboard/chat` SSE | Low (adding 4 entries only) | Thin wrappers keep `chat.py` coupling to query modules only |
| `situation/page.tsx` | `situation-store`, all situation components, fixture (Phase 1) / API (Phase 2) | None | Low | Phase 2 swap is isolated to data source import change |
| `AttackChainGraph.tsx` | `@xyflow/react`, `@dagrejs/dagre` | `AlertCard`, `SimulationResultCard` | Medium (new external deps) | Confirmed peer dep compatibility; OQ-02 fallback plan exists |
| `abstraction_layer.py` | `situation_abstraction_queries.py`, `situation_models.py`, `python-arango` | `endpoints/situation.py` | Low | Single downstream consumer; no circular deps |
| `situation_abstraction_queries.py` | `python-arango`, ArangoDB `complira_graph` | `abstraction_layer.py` | Low | Pure query module; no write operations (snapshot write owned by abstraction_layer) |
| `trigger_client.py` | MiroFish external HTTP API | `endpoints/mirofish.py` | Medium (external API dependency) | External unavailability → 503 response; no retry logic in trigger_client (left to Prefect) |
| `seed_extractor.py` | `python-arango`, ArangoDB `complira_graph` | `endpoints/mirofish.py` (via trigger flow) | Low | Pure AQL export; no write operations |

---

## Allowed Dependency Direction (Mandatory)

- Frontend: `page.tsx` → `store` → `components` → external UI libs (`@xyflow/react`, `@radix-ui`). Components must not import page-level logic.
- Backend: `routers/` → `endpoints/` → `queries/` → `python-arango`. `writeback_service.py` → `simulation_queries.py`. `abstraction_layer.py` → `situation_abstraction_queries.py`. `trigger_client.py` → external MiroFish HTTP. `seed_extractor.py` → `python-arango`. No reverse deps.
- Temporary violations: None planned.

---

## Decommission / Cleanup Plan

| Item To Remove/Rename | Cleanup Actions | Legacy Removal Notes | Verification |
| --- | --- | --- | --- |
| Phase 1 fixture import in `situation/page.tsx` (Phase 2 swap) | Replace fixture import with real API/AQL calls in Phase 2 (C-012) | Fixture JSON remains for reference testing; import removed from production code | Phase 2 CISO view renders live data (AC-011) |
| Phase 2 CISO endpoint legacy code in `situation.py:get_ciso_situation()` | Remove calls to `get_attack_chain_analysis()`, `get_active_threat_detections()`, `get_regulatory_deadline_summary()`, `get_patch_priority_list()` from `get_ciso_situation()`. Replace entirely with `SituationAbstractionLayer(db).compute_ciso(tenant_id)` call. (C-026) | Phase 2 implementation (R-007) is superseded by Phase 5 abstraction layer | AC-023 verification confirms zero CVE IDs in response |
| No other legacy items | — | All changes are net-new additions | — |

---

## Data Models

### Frontend Types (`frontend/lib/types/situation.ts` — new file, C-022 Phase 1 + C-043 Phase 5 additions)

```typescript
type PersonaType = "CISO" | "Board" | "Engineering" | "RegAffairs";

interface MetricCard {
  id: string;
  label: string;
  value: string | number;
  delta?: string;
  severity?: "critical" | "high" | "medium" | "low";
}

interface AlertItem {
  id: string;
  title: string;
  severity: "critical" | "high" | "medium" | "low";
  card_type: "attack_chain" | "compliance" | "patch" | "finding";
  summary: string;
  ask_prompt: string;
  chain?: ChainData;        // present for attack_chain cards
  detail_rows?: { key: string; value: string }[];  // present for other cards
}

interface ChainNode {
  id: string;
  type: "CVE" | "CWE" | "Technique" | "IAMRole" | "Outcome";
  label: string;
  severity?: string;
}

interface ChainEdge {
  id: string;
  source: string;
  target: string;
  probability: number;
  soc_threshold_miss: boolean;
}

// v3 additions — Phase 5
interface ThreatCategory {
  bucket_name: string;        // "remote_code_execution"
  display_name: string;       // "Remote code execution"
  breach_probability: number; // max chain_probability in bucket
  critical_asset_count: number;
  trend: "up" | "down" | "stable" | null;
}

interface ControlFailure {
  framework: string;          // "CRA Article 13"
  failure_count: number;
  coverage_pct: number | null;
}

interface ActionPriority {
  rank: number;
  description: string;
  owner: string;
  due_label: string;          // "18h" | "this sprint" | "47 days"
  urgency: "overdue" | "in_progress" | "upcoming";
}

interface CISOSituation {
  posture_score: number;                    // 0–100
  posture_delta: number | null;             // vs last snapshot
  attck_coverage_pct: number;
  attck_coverage_delta: number | null;
  remediation_sla_pct: number;
  control_failure_count: number;
  threat_categories: ThreatCategory[];
  control_failures: ControlFailure[];
  mttd_hours: number;
  mttd_target_hours: number;
  mttr_days: number;
  mttr_target_days: number;
  action_priorities: ActionPriority[];
  snapshot_timestamp: string;
}

interface BoardSituation {
  breach_probability_pct: number;
  breach_probability_delta: number | null;
  financial_exposure_usd_low: number;
  financial_exposure_usd_high: number;
  regulatory_fine_risk: { framework: string; max_fine_usd: number }[];
  reputational_risk_score: number;          // 0–1
  board_priorities: ActionPriority[];
  snapshot_timestamp: string;
}
```

### Fixture Shape (`aquadrive_tenant.json`) — must match AQL tool output keys

```json
{
  "attack_chains": [/* get_attack_chain_analysis output */],
  "threat_detections": [/* get_active_threat_detections output */],
  "regulatory_deadlines": [/* get_regulatory_deadline_summary output */],
  "patch_priority": [/* get_patch_priority_list output */]
}
```

### Simulation Collections (ArangoDB document schemas)

**`simulation_runs`** (document):
- `_key`: `{seed_export_hash}_{tenant_id}`
- `tenant_id`, `seed_export_hash`, `status` (running|completed|failed), `round_count`, `started_at`, `completed_at`, `source: "mirofish_simulation"`
- `chain_count`: int — total attack_chain_findings for this run (written by summary UPSERT after step 7)
- `soc_blind_spot_count`: int — count of findings where soc_threshold_miss = true (written by summary UPSERT)
- `top_playbook_action`: str — action field from first response_playbook_step by step_order (written by summary UPSERT)

**`attack_chain_findings`** (document):
- `_key`: `{run_id}_{chain_hash}`
- `run_id`, `tenant_id`, `chain_probability`, `soc_threshold_miss` (bool), `confidence`, `chain_steps[]` (CVE/CWE/technique/iam/outcome), `source: "mirofish_simulation"`

**`response_playbook_steps`** (document):
- `_key`: `{run_id}_{step_index}`
- `run_id`, `finding_id`, `step_order`, `action`, `owner`, `priority`, `source: "mirofish_simulation"`

**`compliance_gap_findings`** (document):
- `_key`: `{run_id}_{gap_hash}`
- `run_id`, `tenant_id`, `framework`, `requirement_id`, `gap_description`, `confidence`, `source: "mirofish_simulation"`

**`simulation_agent_logs`** (document):
- `_key`: `{run_id}_{log_seq}`
- `run_id`, `round`, `agent_id`, `event_type`, `significance` (0–1 float), `payload`, `timestamp`, `source: "mirofish_simulation"`

### Edge Collections (all with `_from`, `_to`, `source: "mirofish_simulation"`)

| Edge Collection | From → To | Extra Fields |
| --- | --- | --- |
| `sim_ran_on` | `simulation_runs` → `repositories` | `scan_ref` |
| `sim_triggered_by` | `simulation_runs` → `scan_findings` | — |
| `chain_surfaces_cve` | `attack_chain_findings` → `scan_findings` | `chain_probability` |
| `chain_involves_component` | `attack_chain_findings` → `components` | `role` (CVE/CWE/tech/iam) |
| `chain_informs_vex` | `attack_chain_findings` → `vex_statements` | `advisory_note`, `do_not_mutate_status: true` |
| `chain_calibrates_fair` | `attack_chain_findings` → `fair_scenarios` | `tef_input`, `confidence` (≥0.6 gate) |
| `playbook_addresses_finding` | `response_playbook_steps` → `attack_chain_findings` | `priority` |
| `gap_violates_requirement` | `compliance_gap_findings` → `compliance_requirements` | `gap_score` |

### SimulationWritebackService — 8-Step Sequence (v3)

```
Step 1: UPSERT simulation_runs (_key = seed_export_hash + "_" + tenant_id)
          + UPSERT sim_ran_on edge (simulation_runs → repositories)
          + UPSERT sim_triggered_by edge (simulation_runs → scan_findings[trigger_cve_key])
Step 2: UPSERT attack_chain_findings[] → returns finding _keys
          + UPSERT chain_involves_component edges (finding → components[*], one per chain step)
Step 3: UPSERT compliance_gap_findings[]
          + UPSERT gap_violates_requirement edges (gap → compliance_requirements)
Step 4: UPSERT response_playbook_steps[]
          + UPSERT playbook_addresses_finding edges (playbook_step → attack_chain_finding)
Step 5: UPSERT simulation_agent_logs[]
Step 6: UPSERT chain_surfaces_cve edges (depends on step 2 keys)  [gated on step 2]
          + UPSERT chain_informs_vex edges (advisory; do_not_mutate_status: true)  [gated on step 2]
Step 7: UPSERT chain_calibrates_fair edges (depends on step 2 keys; confidence ≥ 0.6 gate)  [gated on step 2]
Summary UPSERT: update simulation_runs with:
          chain_count, soc_blind_spot_count, top_playbook_action (runs after steps 1–7 complete)
Step 8: rollup_threat_categories()
          Groups attack_chain_findings by ATT&CK tactic bucket
          UPSERT into threat_category_rollups (_key = run_id + "_" + bucket_name)
          Skipped if step 2 returns 0 findings
          Runs after Summary UPSERT completes
```

Steps 6 + 7 + Summary UPSERT are gated on step 2 returning finding keys (AC-018). Step 8 is gated on step 2 returning ≥1 finding (AC-030). All steps use ArangoDB UPSERT for Prefect-retry safety. `chain_informs_vex` and `chain_calibrates_fair` are advisory edges; no existing document status fields are mutated.

---

## Error Handling And Edge Cases

| Scenario | Handling |
| --- | --- |
| AQL tools return empty results (Phase 2) | CISO view renders empty state message (AC-012) |
| `?prompt=` absent on chat page mount | No auto-submit; normal chat UI rendered (AC-007) |
| `init_simulation_schema.py` run twice | `CollectionCreateError` caught + ignored; returns existing collection handle (AC-013) |
| `SimulationWritebackService.run_all()` called twice same seed | Step 1 UPSERT is idempotent on `(seed_export_hash, tenant_id)` — produces 1 doc (AC-015) |
| `chain_calibrates_fair` edge: confidence < 0.6 | Edge skipped entirely — not written (AC-017) |
| `chain_informs_vex` edge write-back | `do_not_mutate_status: true` field on edge; write-back does not touch `vex_statements.status` (AC-016) |
| React Flow v12 dagre incompatibility | Fallback to `reactflow` v11 package; OQ-02 to confirm during Phase 1 |
| `GET /v1/simulation/{run_id}/status` — run not found | Returns 404 with `{"error": "run_not_found"}` |
| `SimulationLivePanel` poll: run transitions to `completed` | Panel hides and `SimulationResultCard` mounts |
| `GET /v1/situation/ciso` — no simulation data for tenant | Returns default CISOSituation with posture_score=0 derived from gap penalty only, empty threat_categories list, posture_delta=None |
| `GET /v1/situation/board` — no business_impact_findings for tenant | Returns BoardSituation with financial_exposure estimated from chain_probability × default asset value model only |
| `POST /v1/mirofish/trigger` — MiroFish engine unreachable | Returns 503 with `{"error": "mirofish_unavailable"}` |
| `GET /v1/mirofish/status/{run_id}` — run_id not found | Returns 404 with `{"error": "run_not_found"}` |
| `extract_monthly_posture_seed(tenant_id)` — no component data | Returns empty dict `{}`; trigger client skips seed injection; MiroFish runs with empty seed |
| Step 8 `rollup_threat_categories()` — step 2 returned 0 findings | Step 8 no-ops entirely; `threat_category_rollups` not written for this run_id |
| `compute_ciso()` called for tenant with no prior snapshots | `posture_delta=None`; snapshot written as first entry; no delta computation attempted |

---

## Use-Case Coverage Matrix (Design Gate)

| use_case_id | Requirement | Use Case | Primary Path Covered | Fallback Path Covered | Error Path Covered | Runtime Call Stack Section |
| --- | --- | --- | --- | --- | --- | --- |
| UC-01 | R-001, R-002 | Navigate to `/dashboard/situation`, CISO persona loads by default | Yes | N/A | Yes (empty state) | §UC-01 |
| UC-02 | R-002 | Switch persona to Board/CFO — metrics update | Yes | N/A | N/A | §UC-02 |
| UC-03 | R-002 | Switch persona to Engineering — patch sprint list | Yes | N/A | N/A | §UC-03 |
| UC-04 | R-002 | Switch persona to Regulatory Affairs — deadline summary | Yes | N/A | N/A | §UC-04 |
| UC-05 | R-003, R-005 | Expand attack chain card → inline drill-down with AttackChainGraph | Yes | Yes (non-chain card → key-value rows) | N/A | §UC-05 |
| UC-06 | R-004 | Click Ask Complira on card → `/dashboard/chat?prompt=<encoded>` | Yes | N/A | N/A | §UC-06 |
| UC-07 | R-002, R-004 | Chat page auto-submits prompt on mount with `?prompt=` param | Yes | Yes (no prompt → normal UI) | N/A | §UC-07 |
| UC-08 | R-007 | CISO view fetches real AQL data (Phase 2) | Yes | N/A | Yes (ArangoDB unavailable) | §UC-08 |
| UC-09 | R-007 | CISO view empty state when tools return zero results | Yes | N/A | N/A | §UC-09 |
| UC-10 | R-008, R-009 | Run `init_simulation_schema.py` — 13 collections created | Yes | Yes (re-run idempotent) | N/A | §UC-10 |
| UC-11 | R-009 | `SimulationWritebackService.run_all()` writes all simulation output | Yes | Yes (duplicate seed = 1 doc) | Yes (ArangoDB error → exception) | §UC-11 |
| UC-12 | R-009 | Steps 6+7 execute only after step 2 returns finding keys | Yes | N/A | N/A | §UC-12 |
| UC-13 | R-009 | `chain_calibrates_fair` edge skipped when confidence < 0.6 | Yes | N/A | N/A | §UC-13 |
| UC-14 | R-009 | `chain_informs_vex` edge: VEX document status not mutated | Yes | N/A | N/A | §UC-14 |
| UC-15 | R-010, R-011 | `get_simulation_runs` tool returns tenant run list via Ask Complira | Yes | Yes (no runs → empty list) | N/A | §UC-15 |
| UC-16 | R-011 | `SimulationLivePanel` polls status every 3s, shows round counter + event feed | Yes | Yes (run completed → show ResultCard) | N/A | §UC-16 |
| UC-17 | R-010, R-011 | `get_attack_chains_for_cve("CVE-2021-44228")` returns chain docs | Yes | Yes (no chains → empty list) | N/A | §UC-17 |
| UC-18 | R-012, R-013 | CISO view fetches CISOSituation from abstraction layer; zero CVE IDs in response | Yes | Yes (no simulation data → default posture 0, empty categories) | Yes (ArangoDB error → 503) | §UC-18 |
| UC-19 | R-012, R-014 | Board view fetches BoardSituation; zero CVE IDs; financial exposure derived from business_impact_findings | Yes | Yes (no business_impact_findings → estimated from chain_probability only) | Yes | §UC-19 |
| UC-20 | R-013 | Threat categories grouped by tactic bucket; bucket with 0 findings omitted | Yes | Yes (0 chains → empty list, posture_score = 100 − gap penalty) | N/A | §UC-20 |
| UC-21 | R-014 | Board priorities use governance language; no technical identifiers | Yes | N/A | N/A | §UC-21 |
| UC-22 | R-015 | posture_snapshot written after compute_ciso(); delta computed from last 2 snapshots | Yes | Yes (first snapshot → delta=None) | N/A | §UC-22 |
| UC-23 | R-016, R-018 | SimulationWritebackService step 8 runs rollup_threat_categories() + writes business_impact_findings | Yes | Yes (0 findings → step 8 no-ops) | N/A | §UC-23 |
| UC-24 | R-017 | POST /v1/mirofish/trigger with monthly_posture_sim returns run_id; seed extractor builds product surface JSON | Yes | N/A | Yes (MiroFish unreachable → 503) | §UC-24 |
| UC-25 | R-017 | GET /v1/mirofish/status/{run_id} returns current run state | Yes | N/A | Yes (run_id not found → 404) | §UC-25 |
| UC-26 | R-018 | business_impact_findings documents written; BoardSituation.financial_exposure derived from cfo_agent outputs | Yes | Yes (no cfo_agent findings → estimate from chain_probability × default asset value) | N/A | §UC-26 |
| UC-27 | R-012, R-013 | Stale threat_category_rollups detection in compute_ciso() | Yes | Yes (no runs → no stale data) | N/A | §UC-27 |

---

## Performance / Security Considerations

- **Fixture import (Phase 1):** Static JSON; no network call. Zero performance concern.
- **Phase 2 AQL calls:** Existing tools use indexed collections. No new indexes needed for Phase 2 CISO view.
- **Simulation schema indexes:** `simulation_runs` needs persistent index on `(tenant_id, seed_export_hash)` for UPSERT idempotency lookup. `attack_chain_findings` needs index on `(run_id)`. `simulation_agent_logs` needs index on `(run_id, significance)` for live panel event feed filter (significance ≥ 0.6).
- **v3 schema indexes:** `threat_category_rollups` needs index on `(tenant_id, run_id)`. `posture_snapshots` needs index on `(tenant_id, computed_at)` for efficient snapshot history retrieval. `business_impact_findings` needs index on `(tenant_id, agent_type)`.
- **`chain_calibrates_fair` confidence gate:** Enforced in `writeback_service.py` before AQL UPSERT — not in AQL. Prevents low-confidence noise edges from polluting FAIR analysis.
- **SimulationLivePanel polling:** 3-second interval, component-level `useEffect` cleanup on unmount. No global polling state.
- **Ask Complira prompt injection:** `ask_prompt` content originates from the fixture/AQL — not from user input. URL-encoded via `encodeURIComponent()`. No XSS surface.
- **CVE ID leakage prevention:** `SituationAbstractionLayer` never reads `cve_id` fields into `CISOSituation` or `BoardSituation` model fields. Structural model enforcement (not runtime filtering) is the primary control. AC-023/AC-024 assert zero leakage in test suite.
- **MiroFish trigger authentication:** `MiroFishTriggerClient` must send API key via Authorization header. Key stored in environment variable, never in code or logs.

---

## Migration / Rollout

- Phase 1: Frontend-only. Deploy anytime. No backend changes.
- Phase 2: Requires ArangoDB `complira_graph` accessible. Deploy after Phase 1 demo.
- Phase 3: Run `scripts/init_simulation_schema.py` once before deploying backend with simulation tools. Script is idempotent — safe to re-run.
- Phase 4: Requires Phase 3 schema + new `routers/simulation.py` deployed. Frontend polling depends on `GET /v1/simulation/{run_id}/status` being live.
- Phase 5: Run updated `scripts/init_simulation_schema.py` to add 3 new collections (`threat_category_rollups`, `business_impact_findings`, `posture_snapshots`). Script is idempotent — existing 13 collections unaffected. Deploy `SituationAbstractionLayer`, updated `situation.py` endpoints, new situation model + query modules. Frontend CISO and Board views rebuilt — Engineering and RegAffairs views untouched.
- Phase 6: Deploy `mirofish/` module and `endpoints/mirofish.py`. Requires MiroFish engine API credentials in environment. `POST /v1/mirofish/trigger` with `monthly_posture_sim` trigger type becomes live. Seed extractor AQL requires Phase 5 collections to exist.

---

## Change Traceability To Implementation Plan

| Change ID | Implementation Plan Task(s) | Verification (Unit/Integration/API/E2E) | Status |
| --- | --- | --- | --- |
| C-001 | Phase 1: Create `situation/page.tsx` | E2E: AC-001 route loads 200 | Implemented |
| C-002 | Phase 1: Create `situation-store.ts` | Unit: persona switch updates store state | Implemented |
| C-003 | Phase 1: Create `PersonaSwitcher.tsx` | Unit: 4 tabs render; active tab highlights | Implemented |
| C-004 | Phase 1: Create `MetricStrip.tsx` | Unit: renders 4 metric cards | Implemented |
| C-005 | Phase 1: Create `AlertFeed.tsx` | Unit: renders AlertCard list | Implemented |
| C-006 | Phase 1: Create `AlertCard.tsx` | Unit: expand/collapse toggle; Ask button navigates | Implemented |
| C-007 | Phase 1: Create `AttackChainGraph.tsx` | Unit: ≥3 nodes rendered; SOC edge red | Implemented |
| C-008 | Phase 1: Create `aquadrive_tenant.json` | Integration: keys match AQL tool output shapes (AC-010) | Implemented |
| C-009 | Phase 1: Modify `layout.tsx` nav | E2E: Situation Room link visible in sidebar | Implemented |
| C-010 | Phase 1: Modify `package.json` deps | Build: `npm install` succeeds | Implemented |
| C-011 | Phase 1: Modify `chat/page.tsx` auto-submit | E2E: AC-007 auto-submit on `?prompt=` mount | Implemented |
| C-012 | Phase 2: Replace fixture with AQL calls | E2E: AC-011 live data; AC-012 empty state | Implemented |
| C-013 | Phase 3: `init_simulation_schema.py` | Integration: AC-013 idempotent; AC-014 13 collections | Implemented |
| C-014–C-015 | Phase 3: `writeback_service.py` | Integration: AC-015 idempotency; AC-016, AC-017, AC-018 | Implemented |
| C-016 | Phase 3: `simulation_queries.py` | Unit: each query function returns correct shape | Implemented |
| C-017 | Phase 3: `chat.py` wrappers | API: AC-019, AC-020 tools callable via chat endpoint | Implemented |
| C-018–C-019 | Phase 4: `SimulationLivePanel`, `SimulationResultCard` | E2E: AC-021, AC-022 | Implemented |
| C-020–C-021 | Phase 4: `routers/simulation.py` + registration | API: status endpoint returns correct schema | Implemented |
| C-022 | Phase 5: Create `situation/__init__.py` | Build: module importable | Planned |
| C-023 | Phase 5: Create `abstraction_layer.py` | Unit: compute_ciso() returns CISOSituation; AC-023 zero CVE leakage | Planned |
| C-024 | Phase 5: Create `situation_models.py` | Unit: Pydantic model validates correctly | Planned |
| C-025 | Phase 5: Create `situation_abstraction_queries.py` | Unit: each AQL function returns correct shape | Planned |
| C-026 | Phase 5: Modify `endpoints/situation.py` — rebuild CISO endpoint | API: AC-023 zero CVE IDs in GET /v1/situation/ciso | Planned |
| C-027 | Phase 5: Add board endpoint to `endpoints/situation.py` | API: AC-024 zero CVE IDs in GET /v1/situation/board | Planned |
| C-028 | Phase 5: Update `init_simulation_schema.py` add 3 collections | Integration: AC-031 threat_category_rollups present; posture_snapshots present | Planned |
| C-029 | Phase 5: Modify `writeback_service.py` add step 8 | Integration: AC-030 rollup_threat_categories() called after steps 1–7 | Planned |
| C-030 | Phase 6: Create `mirofish/__init__.py` | Build: module importable | Planned |
| C-031 | Phase 6: Create `trigger_client.py` | Unit: trigger() returns run_id; get_status() returns status dict | Planned |
| C-032 | Phase 6: Create `seed_extractor.py` | Unit: AC-033 AQL returns ≥1 component node + ≥1 CVE node (or empty dict) | Planned |
| C-033 | Phase 6: Create `endpoints/mirofish.py` | API: AC-032 POST returns run_id; AC-034 monthly_posture_sim agent config correct | Planned |
| C-034 | Phase 6: Modify `router.py` register mirofish | Build: mirofish routes accessible | Planned |
| C-035 | Phase 5: Rebuild CISO view in `situation/page.tsx` | E2E: AC-025 posture score; AC-026 threat categories; AC-027 MTTD present | Planned |
| C-036 | Phase 5: Rebuild Board/CFO view in `situation/page.tsx` | E2E: AC-024 no CVE IDs in Board view | Planned |
| C-037–C-042 | Phase 5: Create 6 new situation components | Unit: each component renders correct fields from typed props | Planned |
| C-043 | Phase 5: Extend `frontend/lib/types/situation.ts` | Build: TypeScript types compile without errors | Planned |

---

## Design Feedback Loop Notes (From Review/Implementation)

| Date | Trigger | Classification | Design Smell | Requirements Updated? | Design Update Applied | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-04-13 | Stage 8 re-entry: CISO and Board/CFO views exposing CVE-level data to executive personas | Design Impact | CISO/Board views passed raw simulation node data directly to API responses; no abstraction boundary enforced between simulation graph and executive persona views | Yes (R-012 through R-018 added; AC-023 through AC-035 added) | SituationAbstractionLayer introduced; CISOSituation/BoardSituation Pydantic models prevent CVE field leakage structurally; MiroFish monthly_posture_sim trigger type added for CFO/Board persona simulation | Open — Phase 5+6 planned |

---

## Open Questions

| ID | Question | Status | Resolution |
| --- | --- | --- | --- |
| OQ-02 | React Flow v12 `@xyflow/react` dagre compatibility | Open | Confirm during Phase 1 `AttackChainGraph` implementation; fallback to `reactflow` v11 if dagre broken |
| OQ-03 | SimulationLivePanel real-time strategy | Resolved | 3-second polling on `GET /v1/simulation/{run_id}/status` |
| OQ-04 | MiroFish engine API contract for monthly_posture_sim | Open | MiroFish team to confirm agent_config schema accepts cfo_agent and board_member_agent type fields before Phase 6 implementation begins |
| OQ-05 | Asset value model for financial exposure estimation | Open | Default asset value (USD) for breach probability × asset value computation when no business_impact_findings exist — confirm with CFO persona stakeholder before Phase 5 Board view implementation |
