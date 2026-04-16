# Requirements — situation-room-and-simulation

**Status:** `Refined`
**Triage:** `Large`
**Branch:** `codex/situation-room-and-simulation`
**Last Updated:** 2026-04-13

---

## Goal / Problem Statement

Complira has a complete intelligence layer (Ask Complira chat, FAIR risk, VEX, scan ingestion, graph traversal) but no proactive surface. Every insight requires a question first.

The Situation Room closes this gap. It is a multi-persona dashboard that surfaces the top items each stakeholder role needs to act on — without search, without configuration, without asking. It is a situation room, not a BI dashboard.

The MiroFish simulation layer provides simulation-derived attack chains with real chain probabilities and SOC blind-spot detection. This ticket builds the schema and write-back service for simulation outputs, and the UI to visualize them.

---

## Requirements

### R-001 — Situation Room route
The application must expose a `/dashboard/situation` route with a 4-persona stakeholder dashboard. The sidebar nav must include a "Situation Room" entry linking to this route.
**Expected outcome:** User navigates to `/dashboard/situation` and sees a loaded page with a persona tab switcher and at least one metric strip and one alert card for the active persona.

### R-002 — Persona views
The dashboard must render four distinct persona views: CISO, Board/CFO, Engineering, Regulatory Affairs. Switching persona transforms the displayed metrics, alert cards, and drill-down content. State must persist within a session (Zustand store).
**Expected outcome:** Clicking each persona tab updates all cards and metrics without page reload. Active persona highlights in the tab bar.

### R-003 — Alert card with inline drill-down
Each alert card must expand inline on click to show a chain path (for attack chain cards) or key-value detail rows (for other card types), without navigating to a new page.
**Expected outcome:** Clicking an alert card reveals drill-down content in the same card. Clicking again collapses it.

### R-004 — Ask Complira integration
Every alert card must include an "Ask Complira" button. Clicking it navigates to `/dashboard/chat?prompt=<encoded>` with the card's `ask_prompt` text pre-filled. The chat page must auto-submit the prompt on mount when a `?prompt` param is present.
**Expected outcome:** Clicking "Ask Complira" on a card opens the chat page with the prompt pre-filled and the query submitted automatically.

### R-005 — AttackChainGraph component
A graph component must render an ordered node chain (CVE → CWE → Technique → IAM role → Outcome) with a left-to-right dagre layout. Each node shows its ID and severity label. Edges show chain probability. Edges where `soc_threshold_miss = true` render in red with a visible SOC blind-spot annotation.
**Expected outcome:** Graph renders all chain nodes connected in order. SOC blind-spot edges are visually distinct (red, annotated).

### R-006 — Phase 1 mock data fixture
All Phase 1 data must be served from a static JSON fixture at `frontend/src/fixtures/aquadrive_tenant.json`. The fixture's data shapes must exactly match the return shapes of the Phase 2 AQL tool functions so that Phase 2 swap requires zero component changes.
**Expected outcome:** Replacing fixture import with real tool API call requires only the data source change, not component logic changes.

### R-007 — Phase 2 live graph wiring (CISO view)
The CISO persona view must fetch real data from ArangoDB using the existing tools (`get_attack_chain_analysis`, `get_active_threat_detections`, `get_regulatory_deadline_summary`, `get_patch_priority_list`). No mock fixture used in Phase 2 for the CISO view.
**Expected outcome:** CISO view shows real attack chain data. Page renders correctly when tools return empty results.

### R-008 — Simulation ArangoDB schema
The database must have 5 new document collections (`simulation_runs`, `attack_chain_findings`, `response_playbook_steps`, `compliance_gap_findings`, `simulation_agent_logs`) and 8 new edge collections as specified in `simulation_schema_design_v1.1.docx`. Schema must be created by `scripts/init_simulation_schema.py` (idempotent, matches existing init pattern).
**Expected outcome:** Running `init_simulation_schema.py` creates all 13 collections and their indexes. Re-running is safe (no error, no duplicate).

### R-009 — SimulationWritebackService
A Python class `SimulationWritebackService` must implement the 7-step write-back sequence. All writes use UPSERT (Prefect-retry safe). Steps 6 and 7 must only execute after step 2 completes. `simulation_runs` UPSERT must be idempotent on `(seed_export_hash, tenant_id)`.
**Expected outcome:** Calling `service.run_all(report, run_key)` writes all simulation output to ArangoDB. Calling it twice with the same seed produces one `simulation_runs` document (not two).

### R-010 — Simulation chat tools
Four new tools must be registered in `_TOOL_REGISTRY` and `COMPLIRA_TOOLS`: `get_simulation_runs`, `get_attack_chains_for_cve`, `get_playbook_for_run`, `get_compliance_gaps_for_run`. Query logic lives in `src/complira_graph/queries/simulation_queries.py`.
**Expected outcome:** Ask Complira can answer "show me simulation runs" and "what attack chains involve CVE-2021-44228" using real simulation data.

### R-011 — Simulation visualization (Phase 4)
The Situation Room must include a `SimulationLivePanel` (shows round counter and high-significance event feed while simulation runs) and a `SimulationResultCard` (shows completed run summary). Both components must include an "Ask Complira" button. The AttackChainGraph must render real `chain_surfaces_cve` edge data when simulation data is available.
**Expected outcome:** After a simulation run completes, the CISO view shows a `SimulationResultCard` with chain count, SOC blind-spot count, and top playbook action.

### R-012 — SituationAbstractionLayer
A Python service `SituationAbstractionLayer` must translate raw simulation graph data into business-level metrics. CISO and Board/CFO API responses must contain zero CVE IDs, zero CVSS scores, zero package names. The layer reads `attack_chain_findings`, `compliance_gap_findings`, and `threat_category_rollups` and computes `CISOSituation` and `BoardSituation` Pydantic models.
**Expected outcome:** `GET /v1/situation/ciso` and `GET /v1/situation/board` return only business-level fields. Asserting `"CVE-"` not in json_response confirms zero CVE leakage.
**Required AQL functions in `situation_abstraction_queries.py`:** `get_threat_category_rollup`, `get_compliance_failures_by_framework`, `get_simulated_mttd`, `get_posture_snapshot_history`, `get_attack_chain_findings_for_run` (individual chain probabilities for posture formula), `get_attck_coverage` (MITRE ATT&CK coverage %), `get_business_impact_findings`, `get_latest_run_id` (staleness check).

### R-013 — CISO persona business-level view
The CISO persona view must display: posture score (0–100, derived from simulation signals), threat categories (grouped by ATT&CK tactic bucket — not by CVE), MTTD/MTTR (simulated, in hours/days vs. target), compliance control failures by framework (CRA, IEC 62304, NIS2, NIST CSF), and top 3 action priorities with owner and due date. Historical trend delta (↑↓ with delta value vs. last month) must be shown for posture score and ATT&CK coverage.
**Expected outcome:** CISO view shows posture score, ≥1 threat category, MTTD vs target, compliance failure count by framework, and 3 action priorities. No CVE IDs visible.

### R-014 — Board/CFO persona business-level view
The Board/CFO persona view must display: breach probability % (derived from max chain_probability across tenant runs), financial exposure estimate ($, derived from breach probability × asset value model), regulatory fine risk by framework, reputational risk score, and top 2 board-level priorities (governance language only — disclosure obligations, fiduciary exposure). No CVE IDs, CVSS scores, or technical identifiers in Board view.
**Expected outcome:** Board view shows breach probability, financial exposure range, and regulatory fine risk. Asserting no CVE IDs in rendered output.

### R-015 — Historical posture snapshots
After each `SituationAbstractionLayer.compute_ciso()` call, the computed metrics must be persisted to a `posture_snapshots` ArangoDB collection (one document per tenant per computation). Historical delta (↓ 8 pts from last month, ↑ 4% this quarter) is computed by comparing the latest 2 snapshots for monthly delta and latest 4 for quarterly trend.
**Expected outcome:** After 2 `compute_ciso()` calls for same tenant, `posture_snapshots` contains 2 documents. Monthly delta = snapshot[n].posture_score − snapshot[n-1].posture_score.

### R-016 — SimulationWritebackService step 8: threat category rollup
`SimulationWritebackService.run_all()` must execute a step 8 after steps 1–7 complete: `rollup_threat_categories()`. This function groups `attack_chain_findings` by ATT&CK tactic bucket (remote_code_execution: T1190/T1059/T1203/T1210; credential_exposure: T1552/T1078/T1539/T1111; cloud_misconfiguration: T1580/T1098/T1530; patch_gaps: T1190 firmware) and writes aggregated results to `threat_category_rollups` collection using UPSERT.
**Expected outcome:** After `run_all()`, `threat_category_rollups` contains one document per non-empty tactic bucket per run. Each document has `bucket_name`, `max_chain_probability`, `critical_asset_count`, `tenant_id`, `run_id`.

### R-017 — MiroFish integration
The system must support triggering MiroFish simulation runs via `POST /v1/mirofish/trigger` and polling status via `GET /v1/mirofish/status/{run_id}`. Two simulation trigger types must be supported: `kev_triggered` (existing — for Engineering/RegAffairs feeds) and `monthly_posture_sim` (new — runs with CFO + Board member agent personas, 50 rounds, full product surface seed, feeds CISO posture score and Board breach probability). A seed extractor AQL must export the full product surface subgraph for `monthly_posture_sim` runs. MiroFish engine itself is external — this ticket builds the Complira-side trigger client, seed exporter, and response parser only.
**Expected outcome:** `POST /v1/mirofish/trigger` with `{"trigger_type": "monthly_posture_sim", "tenant_id": "..."}` returns `{"run_id": "...", "status": "queued"}`. `GET /v1/mirofish/status/{run_id}` returns current run state.

### R-018 — business_impact_findings collection
CFO and Board member agent outputs from MiroFish `monthly_posture_sim` runs must be stored in `business_impact_findings` collection. Each document captures: `run_id`, `tenant_id`, `agent_type` (cfo_agent | board_member_agent), `impact_type` (financial_exposure | regulatory_fine_risk | reputational_risk | disclosure_obligation), `estimated_value`, `currency`, `narrative`, `confidence`, `source: "mirofish_simulation"`.
**Expected outcome:** After `monthly_posture_sim` run write-back, `business_impact_findings` contains ≥1 document per agent type. `BoardSituation` financial exposure is derived from these documents.

---

## Acceptance Criteria

| AC ID | Requirement | Description | Measurable Expected Outcome |
|-------|-------------|-------------|----------------------------|
| AC-001 | R-001 | Situation Room route loads | `GET /dashboard/situation` returns 200; page renders without console errors |
| AC-002 | R-001 | Sidebar nav entry | "Situation Room" link visible in sidebar; active state highlights when on `/dashboard/situation` |
| AC-003 | R-002 | Persona switcher renders all 4 tabs | CISO, Board/CFO, Engineering, Regulatory Affairs tabs all visible |
| AC-004 | R-002 | Persona switch updates content | Clicking Board/CFO shows ALE metric; clicking Engineering shows patch sprint list |
| AC-005 | R-003 | Alert card drill-down toggles | Clicking closed card opens drill-down; clicking again closes it; no page navigation |
| AC-006 | R-004 | Ask Complira navigates with prompt | Clicking button opens `/dashboard/chat` with `?prompt=` query param encoded |
| AC-007 | R-004 | Chat page auto-submits on `?prompt` | On mount with `?prompt` param, chat submits prompt without user pressing enter |
| AC-008 | R-005 | AttackChainGraph renders chain | Graph shows ≥ 3 nodes connected left-to-right for mock CVE-2021-44228 chain |
| AC-009 | R-005 | SOC blind-spot edge annotation | Edge with `soc_threshold_miss=true` renders red with "SOC blind spot" annotation |
| AC-010 | R-006 | Fixture shape matches tool output | `aquadrive_tenant.json` keys match the return keys of `get_attack_chain_analysis` output |
| AC-011 | R-007 | CISO view live data | CISO view shows real chain data when ArangoDB is connected; no hardcoded values |
| AC-012 | R-007 | Empty state renders | CISO view shows empty state message when tools return zero results |
| AC-013 | R-008 | Schema init idempotent | Running `init_simulation_schema.py` twice produces no error and no duplicate collections |
| AC-014 | R-008 | All 13 collections created | `db.collections()` after init includes all 5 document + 8 edge simulation collections |
| AC-015 | R-009 | Write-back idempotency | Calling `run_all()` twice with same `seed_export_hash` produces 1 `simulation_runs` doc |
| AC-016 | R-009 | chain_informs_vex is advisory | Running write-back does not change any existing VEX document's status field |
| AC-017 | R-009 | chain_calibrates_fair confidence gate | No `chain_calibrates_fair` edge created when finding confidence < 0.6 |
| AC-018 | R-009 | Step order enforced | Steps 6+7 only run after step 2 returns finding keys |
| AC-019 | R-010 | Simulation tools in registry | `get_simulation_runs` callable via Ask Complira; returns list of simulation runs for tenant |
| AC-020 | R-010 | Attack chains by CVE | `get_attack_chains_for_cve("CVE-2021-44228")` returns chain documents from ArangoDB |
| AC-021 | R-011 | SimulationResultCard renders | After completed run, CISO view shows chain count, SOC blind-spot count, top action |
| AC-022 | R-011 | SimulationLivePanel polls status | During active run, panel updates round counter every 3 seconds |
| AC-023 | R-012 | CISO API zero CVE IDs | `GET /v1/situation/ciso` JSON response: asserting `"CVE-"` not in `json.dumps(response)` passes |
| AC-024 | R-012 | Board API zero CVE IDs | `GET /v1/situation/board` JSON response: asserting `"CVE-"` not in `json.dumps(response)` passes |
| AC-025 | R-013 | Posture score formula | `posture_score` = 100 − round(mean(chain_probability) × 40) − (gap_count × 3) − round(soc_miss_rate × 20) + round(attck_coverage × 0.1); value is 0–100 integer. Note: `chain_probability` values sourced from `attack_chain_findings` documents for tenant's latest completed run via `get_attack_chain_findings_for_run()`; NOT from aggregated `threat_category_rollups` which contains per-bucket maxima only. `attck_coverage` sourced from `get_attck_coverage()`. `soc_miss_rate` = count(chain_findings where soc_threshold_miss=True) / total chain_findings. |
| AC-026 | R-013 | Threat categories by tactic | Response `threat_categories` contains items with `bucket_name` field; no `cve_id` field present |
| AC-027 | R-013 | MTTD derived from simulation | `mttd_hours` field present; value derived from `soc_threshold_miss` rate across tenant chain findings |
| AC-028 | R-015 | Posture trend delta | Response includes `posture_delta` field; when 2+ snapshots exist, value = latest − previous snapshot posture_score |
| AC-029 | R-015 | Snapshot persisted on compute | After `compute_ciso()` call, `posture_snapshots` collection has 1 additional document for tenant |
| AC-030 | R-016 | Step 8 executes after steps 1–7 | `rollup_threat_categories()` AQL execute called after all 7 write-back steps complete; skipped if step 2 returns 0 findings |
| AC-031 | R-016 | threat_category_rollups collection | `db.collections()` after schema init includes `threat_category_rollups`; each doc has `bucket_name`, `max_chain_probability`, `critical_asset_count` |
| AC-032 | R-017 | MiroFish trigger API accepts monthly_posture_sim | `POST /v1/mirofish/trigger` with `trigger_type=monthly_posture_sim` returns 200 with `run_id` |
| AC-033 | R-017 | Seed extractor exports product surface | `extract_monthly_posture_seed(tenant_id)` AQL returns graph with ≥1 component node and ≥1 CVE node (or empty dict when no data) |
| AC-034 | R-017 | monthly_posture_sim agent config includes CFO + board personas | Agent config for `monthly_posture_sim` trigger type includes `cfo_agent` and `board_member_agent` entries |
| AC-035 | R-018 | business_impact_findings written after monthly_posture_sim | After write-back with CFO agent outputs, `business_impact_findings` collection contains doc with `agent_type=cfo_agent` and `impact_type=financial_exposure` |

---

## Requirement Coverage Map → Use Cases

| Requirement | Covered By Use Case(s) |
|-------------|----------------------|
| R-001 | UC-01, UC-02, UC-03, UC-04 |
| R-002 | UC-01, UC-02, UC-03, UC-04, UC-07 |
| R-003 | UC-05 |
| R-004 | UC-06 |
| R-005 | UC-05, UC-15 |
| R-006 | UC-01 through UC-07 |
| R-007 | UC-08, UC-09 |
| R-008 | UC-10, UC-11 |
| R-009 | UC-10, UC-11, UC-12, UC-13, UC-14 |
| R-010 | UC-10, UC-15, UC-17 |
| R-011 | UC-15, UC-16, UC-17 |
| R-012 | UC-18, UC-19, UC-27 |
| R-013 | UC-18, UC-20, UC-27 |
| R-014 | UC-19, UC-21 |
| R-015 | UC-22 |
| R-016 | UC-23 |
| R-017 | UC-24, UC-25 |
| R-018 | UC-23, UC-26 |

---

## Acceptance Criteria Coverage Map → Stage 7 Scenarios

| AC ID | Stage 7 Scenario ID(s) |
|-------|----------------------|
| AC-001 | S-001 |
| AC-002 | S-001 |
| AC-003 | S-002 |
| AC-004 | S-002 |
| AC-005 | S-003 |
| AC-006 | S-004 |
| AC-007 | S-004 |
| AC-008 | S-005 |
| AC-009 | S-005 |
| AC-010 | S-006 |
| AC-011 | S-007 |
| AC-012 | S-007 |
| AC-013 | S-008 |
| AC-014 | S-008 |
| AC-015 | S-009 |
| AC-016 | S-010 |
| AC-017 | S-010 |
| AC-018 | S-009 |
| AC-019 | S-011 |
| AC-020 | S-011 |
| AC-021 | S-012 |
| AC-022 | S-012 |
| AC-023 | S-013 |
| AC-024 | S-013 |
| AC-025 | S-014 |
| AC-026 | S-014 |
| AC-027 | S-014 |
| AC-028 | S-015 |
| AC-029 | S-015 |
| AC-030 | S-016 |
| AC-031 | S-016 |
| AC-032 | S-017 |
| AC-033 | S-017 |
| AC-034 | S-017 |
| AC-035 | S-018 |

---

## Constraints / Dependencies

- Next.js 14 App Router, Tailwind CSS
- New deps required: `@xyflow/react` (React Flow v12), `@dagrejs/dagre`, `zustand`
- All Phase 2 backend tools exist — no new FastAPI endpoints for Phase 2
- Phase 4 requires new `GET /v1/simulation/{run_id}/status` endpoint
- MiroFish itself is out of scope — write-back service is built to contract but not called by real MiroFish in this increment
- Write-back is append-only per schema doc §6.5 — no existing collection mutations

## Assumptions

- ArangoDB `complira_graph` is accessible for Phase 2+
- React Flow v12 (`@xyflow/react`) dagre layout works; fallback to v11 (`reactflow`) if not
- Zustand is stateless per page load (no persistence) — active persona resets on refresh
- `init_simulation_schema.py` runs once manually before write-back service is used

## Open Questions

- OQ-02 (partially resolved): React Flow v12 — confirm `@dagrejs/dagre` compatibility during Phase 1 implementation
- OQ-03 (resolved): SimulationLivePanel uses 3-second polling against `GET /v1/simulation/{run_id}/status`
