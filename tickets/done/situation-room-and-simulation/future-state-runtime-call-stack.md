# Future-State Runtime Call Stacks — Situation Room + MiroFish Simulation

## Conventions

- Frame format: `path/to/file.ts:functionName(...)` or `path/to/file.py:functionName(...)`
- `[ENTRY]` external entrypoint (route/API/CLI)
- `[ASYNC]` async boundary (`await`, queue handoff)
- `[STATE]` in-memory / Zustand state mutation
- `[IO]` database / network / file IO
- `[FALLBACK]` non-primary branch
- `[ERROR]` error path

---

## Design Basis

- Scope Classification: `Large`
- Call Stack Version: `v3`
- Requirements: `tickets/in-progress/situation-room-and-simulation/requirements.md` (status `Design-ready`)
- Source Artifact: `tickets/in-progress/situation-room-and-simulation/proposed-design.md`
- Source Design Version: `v3`
- Referenced Sections: Change Inventory C-001–C-021, Use-Case Coverage Matrix UC-01–UC-17; Change Inventory C-022–C-043, Use-Case Coverage Matrix UC-18–UC-26

---

## Future-State Modeling Rule (Mandatory)

Model target design behavior. Phase 1 uses static fixture import; Phase 2 replaces that with real AQL calls in the same component entry point — the call stack shape is identical; only the data source changes.

---

## Use Case Index (Stable IDs)

| use_case_id | Source Type | Requirement ID(s) | Design-Risk Objective | Use Case Name | Coverage Target |
| --- | --- | --- | --- | --- | --- |
| UC-01 | Requirement | R-001, R-002 | N/A | Navigate to Situation Room — CISO persona default | Primary/Fallback/Error |
| UC-02 | Requirement | R-002 | N/A | Switch to Board/CFO persona | Primary/N/A/N/A |
| UC-03 | Requirement | R-002 | N/A | Switch to Engineering persona | Primary/N/A/N/A |
| UC-04 | Requirement | R-002 | N/A | Switch to Regulatory Affairs persona | Primary/N/A/N/A |
| UC-05 | Requirement | R-003, R-005 | N/A | Expand alert card — attack chain drill-down with graph | Primary/Fallback/N/A |
| UC-06 | Requirement | R-004 | N/A | Click Ask Complira on card — navigate with encoded prompt | Primary/N/A/N/A |
| UC-07 | Requirement | R-004 | N/A | Chat page auto-submit on `?prompt=` mount | Primary/Fallback/N/A |
| UC-08 | Requirement | R-007 | N/A | CISO view — Phase 2 live AQL data fetch | Primary/N/A/Error |
| UC-09 | Requirement | R-007 | N/A | CISO view — empty state when AQL returns zero results | Primary/N/A/N/A |
| UC-10 | Requirement | R-008 | N/A | Run `init_simulation_schema.py` — 13 collections created | Primary/Fallback/N/A |
| UC-11 | Requirement | R-009 | N/A | `SimulationWritebackService.run_all()` full 7-step write-back | Primary/Fallback/Error |
| UC-12 | Requirement | R-009 | N/A | Steps 6+7 gated on step 2 finding keys | Primary/N/A/N/A |
| UC-13 | Requirement | R-009 | N/A | `chain_calibrates_fair` confidence gate (< 0.6 → skip) | Primary/Fallback/N/A |
| UC-14 | Requirement | R-009 | N/A | `chain_informs_vex` edge — VEX status NOT mutated | Primary/N/A/N/A |
| UC-15 | Requirement | R-010, R-011 | N/A | `get_simulation_runs` tool via Ask Complira | Primary/Fallback/N/A |
| UC-16 | Requirement | R-011 | N/A | `SimulationLivePanel` polls status every 3 seconds | Primary/Fallback/N/A |
| UC-17 | Requirement | R-010, R-011 | N/A | `get_attack_chains_for_cve` tool | Primary/Fallback/N/A |
| UC-DR-01 | Design-Risk | R-005 | React Flow v12 + dagre layout compatibility risk | AttackChainGraph renders with dagre layout | Primary/Fallback/N/A |
| UC-DR-02 | Design-Risk | R-009 | UPSERT idempotency under Prefect retry — step 1 duplicate seed | SimulationWritebackService idempotency on re-run | Primary/N/A/N/A |
| UC-18 | Requirement | R-012, R-013 | N/A | CISO view fetches CISOSituation via SituationAbstractionLayer — zero CVE IDs | Primary/Fallback/Error |
| UC-19 | Requirement | R-012, R-014 | N/A | Board view fetches BoardSituation via SituationAbstractionLayer — zero CVE IDs | Primary/Fallback/Error |
| UC-20 | Requirement | R-013 | N/A | Threat categories grouped by ATT&CK tactic bucket — not by CVE | Primary/Fallback/N/A |
| UC-21 | Requirement | R-014 | N/A | Board priorities use governance language — no CVE IDs | Primary/N/A/N/A |
| UC-22 | Requirement | R-015 | N/A | posture_snapshot written after compute_ciso(); delta computed from last 2 | Primary/Fallback/N/A |
| UC-23 | Requirement | R-016, R-018 | N/A | SimulationWritebackService step 8 — rollup_threat_categories() + business_impact_findings | Primary/Fallback/N/A |
| UC-24 | Requirement | R-017 | N/A | POST /v1/mirofish/trigger monthly_posture_sim — seed extractor + trigger client | Primary/N/A/Error |
| UC-25 | Requirement | R-017 | N/A | GET /v1/mirofish/status/{run_id} — poll MiroFish run state | Primary/N/A/Error |
| UC-26 | Requirement | R-018 | N/A | BoardSituation.financial_exposure derived from business_impact_findings | Primary/Fallback/N/A |
| UC-27 | Requirement | R-012, R-013 | N/A | compute_ciso() detects stale threat_category_rollups — surfaces data_staleness_warning | Primary/Fallback/N/A |

---

## Transition Notes

- **Phase 1 → Phase 2 data source swap:** In `situation/page.tsx` (and/or CISO-view data hook), replace `import fixture from "fixtures/aquadrive_tenant.json"` with `fetch("/api/v1/chat")` AQL tool call. Component shape is unchanged; only data source changes (R-006).
- **Retirement of fixture import:** Fixture JSON remains as test reference data after Phase 2; the production import is removed from `situation/page.tsx`.

---

## Use Case: UC-01 — Navigate to Situation Room, CISO persona default

### Goal
User navigates to `/dashboard/situation`. Page loads with CISO persona active by default, displaying metric strip and alert feed from Phase 1 fixture data.

### Preconditions
- User authenticated; dashboard layout rendered.
- Phase 1: `aquadrive_tenant.json` fixture exists at `frontend/src/fixtures/`.
- `@xyflow/react`, `@dagrejs/dagre`, `zustand` installed.

### Expected Outcome
Page renders 200. Persona switcher shows 4 tabs with CISO active. MetricStrip renders 4 CISO metric cards. AlertFeed renders alert cards from fixture `attack_chains`.

### Primary Runtime Call Stack

```text
[ENTRY] frontend/app/dashboard/situation/page.tsx:SituationRoomPage()
├── frontend/lib/stores/situation-store.ts:usePersonaStore()          # [STATE] read activePersona (default: "CISO")
├── frontend/app/dashboard/situation/page.tsx:loadFixtureData()       # [IO] Phase 1: import aquadrive_tenant.json
│   └── frontend/src/fixtures/aquadrive_tenant.json                   # static JSON import
├── frontend/components/situation/PersonaSwitcher.tsx:PersonaSwitcher({ activePersona, onSwitch })
├── frontend/components/situation/MetricStrip.tsx:MetricStrip({ metrics: cisoMetrics })
│   └── renders 4 MetricCard divs (Tailwind)
└── frontend/components/situation/AlertFeed.tsx:AlertFeed({ alerts: cisoAlerts })
    └── frontend/components/situation/AlertCard.tsx:AlertCard({ item }) × N
        # each card: collapsed state, expand button, Ask Complira button
```

### Branching / Fallback Paths

```text
[FALLBACK] fixture not found (import error during build)
frontend/app/dashboard/situation/page.tsx:SituationRoomPage()
└── renders empty-state UI: "No situation data available" message
```

```text
[ERROR] Phase 2: AQL call fails or ArangoDB unreachable
frontend/app/dashboard/situation/page.tsx:fetchCISOData()
└── catches error → [STATE] sets `dataError = true`
    └── frontend/components/situation/AlertFeed.tsx:AlertFeed({ alerts: [] })
        └── empty-state message: "Unable to load threat intelligence. Try again." (AC-012)
```

### State And Data Transformations

- Fixture JSON → typed `SituationRoomData` object via import
- `SituationRoomData.attack_chains[]` → `AlertItem[]` (CISO alert feed)
- `SituationRoomData.attack_chains[0]` → `MetricCard[]` for CISO strip (chain count, SOC miss count, top CVSS, mean probability)

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `Covered`
- Error Path: `Covered`

---

## Use Case: UC-02 — Switch to Board/CFO persona

### Goal
User clicks "Board/CFO" tab. Persona store updates. MetricStrip shows ALE/VaR95 metrics. AlertFeed shows financial exposure cards.

### Preconditions
- Situation room page loaded (UC-01 complete).
- `aquadrive_tenant.json` loaded in memory.

### Expected Outcome
MetricStrip updates to Board metrics (ALE, VaR95, highest-exposure CVE, compliance fines). AlertFeed updates to Board alert cards. No page reload.

### Primary Runtime Call Stack

```text
[ENTRY] frontend/components/situation/PersonaSwitcher.tsx:handleTabChange("Board")
├── frontend/lib/stores/situation-store.ts:setActivePersona("Board")  # [STATE] Zustand update
└── frontend/app/dashboard/situation/page.tsx:SituationRoomPage()     # re-renders on store change
    ├── frontend/components/situation/PersonaSwitcher.tsx             # "Board/CFO" tab highlighted
    ├── frontend/components/situation/MetricStrip.tsx:MetricStrip({ metrics: boardMetrics })
    │   └── ALE ($), VaR95 ($), highest-exposure CVE, compliance fine exposure
    └── frontend/components/situation/AlertFeed.tsx:AlertFeed({ alerts: boardAlerts })
        └── frontend/components/situation/AlertCard.tsx × N           # board alert cards
```

### State And Data Transformations

- `setActivePersona("Board")` → Zustand `activePersona = "Board"`
- Component re-render reads `activePersona` from store → selects `boardMetrics` + `boardAlerts` from loaded fixture

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `N/A`

**Phase 5 Board View Transition Note:** The Phase 1 fixture-based Board view (`boardMetrics` containing `highest-exposure CVE`) is replaced by Phase 5 `GET /v1/situation/board` returning `BoardSituation` (zero CVE IDs). After C-036 is implemented, the UC-02 Board/CFO call stack follows the UC-19 path instead of the fixture path. The legacy `boardMetrics.highest-exposure CVE` field must NOT appear in any Phase 5 Board view component.

---

## Use Case: UC-03 — Switch to Engineering persona

### Goal
User clicks "Engineering" tab. MetricStrip shows patch sprint metrics. AlertFeed shows patch priority list.

### Expected Outcome
MetricStrip updates: critical patches due this sprint, mean EPSS top-10, patch coverage %. AlertFeed: patch priority cards ordered by EPSS × impact.

### Primary Runtime Call Stack

```text
[ENTRY] frontend/components/situation/PersonaSwitcher.tsx:handleTabChange("Engineering")
├── frontend/lib/stores/situation-store.ts:setActivePersona("Engineering")  # [STATE]
└── frontend/app/dashboard/situation/page.tsx:SituationRoomPage()
    ├── frontend/components/situation/MetricStrip.tsx:MetricStrip({ metrics: engineeringMetrics })
    │   └── critical patch count, EPSS mean, sprint coverage %, blockers
    └── frontend/components/situation/AlertFeed.tsx:AlertFeed({ alerts: patchAlerts })
        └── frontend/components/situation/AlertCard.tsx × N           # patch priority cards
            # drill-down: CVE ID, EPSS, affected components, recommended action
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `N/A`

---

## Use Case: UC-04 — Switch to Regulatory Affairs persona

### Goal
User clicks "Regulatory Affairs" tab. MetricStrip shows compliance deadline metrics. AlertFeed shows upcoming requirement deadlines.

### Expected Outcome
MetricStrip: days to nearest deadline, open compliance gaps, frameworks at risk, frameworks compliant. AlertFeed: regulatory deadline cards ordered by nearest due date.

### Primary Runtime Call Stack

```text
[ENTRY] frontend/components/situation/PersonaSwitcher.tsx:handleTabChange("RegAffairs")
├── frontend/lib/stores/situation-store.ts:setActivePersona("RegAffairs")  # [STATE]
└── frontend/app/dashboard/situation/page.tsx:SituationRoomPage()
    ├── frontend/components/situation/MetricStrip.tsx:MetricStrip({ metrics: regMetrics })
    │   └── days to deadline, open gaps, frameworks at risk, frameworks compliant
    └── frontend/components/situation/AlertFeed.tsx:AlertFeed({ alerts: regAlerts })
        └── frontend/components/situation/AlertCard.tsx × N
            # drill-down: framework, requirement ID, deadline, gap description
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `N/A`

---

## Use Case: UC-05 — Expand alert card — attack chain drill-down with graph

### Goal
User clicks a closed attack chain alert card. Card expands inline showing `AttackChainGraph` with CVE→CWE→Technique→IAM→Outcome nodes and SOC blind-spot edge. Clicking again collapses it.

### Preconditions
- Alert card with `card_type = "attack_chain"` rendered.
- Chain data present in card's `chain` field.

### Expected Outcome
Card expands with `AttackChainGraph` showing ≥3 nodes left-to-right. SOC blind-spot edge renders red with "SOC blind spot" annotation. Clicking again collapses.

### Primary Runtime Call Stack

```text
[ENTRY] frontend/components/situation/AlertCard.tsx:handleToggle()
├── [STATE] setExpanded(!expanded)                                    # local React state
└── if expanded && item.card_type === "attack_chain":
    └── frontend/components/situation/AttackChainGraph.tsx:AttackChainGraph({ chain })
        ├── AttackChainGraph:buildGraphElements(chain)
        │   ├── maps chain.nodes[] → ReactFlow Node[] with position via dagre layout
        │   │   └── @dagrejs/dagre:graphlib.Graph():setNode/setEdge/layout()  # dagre left-to-right
        │   └── maps chain.edges[] → ReactFlow Edge[]
        │       └── for edge with soc_threshold_miss=true:
        │           └── edge.style = { stroke: "red" }, edge.label = "SOC blind spot"
        └── @xyflow/react:ReactFlow({ nodes, edges, fitView: true })  # renders graph
```

### Branching / Fallback Paths

```text
[FALLBACK] item.card_type !== "attack_chain" (e.g., compliance, patch)
frontend/components/situation/AlertCard.tsx:handleToggle()
└── if expanded:
    └── renders detail_rows[] as key-value pairs (no graph)
```

### State And Data Transformations

- `ChainData` → dagre `graphlib.Graph` (node positions computed)
- dagre layout output → `ReactFlow Node[]` with `{x, y}` positions
- `ChainEdge.soc_threshold_miss === true` → `ReactFlow Edge` style override (red stroke + label)

### Design Smells / Gaps

- Legacy/backward-compatibility branch present? `No`
- Naming-to-responsibility drift? `No`

### Open Questions

- OQ-02: Confirm `@dagrejs/dagre` + `@xyflow/react` v12 works; fallback to `reactflow` v11 if not.

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `Covered`
- Error Path: `N/A`

---

## Use Case: UC-06 — Click Ask Complira on card — navigate with encoded prompt

### Goal
User clicks "Ask Complira" button on any alert card. Browser navigates to `/dashboard/chat?prompt=<encoded>` with card's `ask_prompt` text URL-encoded.

### Preconditions
- Alert card rendered with non-null `ask_prompt`.

### Expected Outcome
Router navigates to `/dashboard/chat?prompt=<URL-encoded ask_prompt>`. Chat page receives the param.

### Primary Runtime Call Stack

```text
[ENTRY] frontend/components/situation/AlertCard.tsx:handleAskComplira()
├── encodeURIComponent(item.ask_prompt)                               # encode prompt text
└── next/navigation:useRouter():push(`/dashboard/chat?prompt=${encoded}`)  # [IO] navigate
    └── [ENTRY] frontend/app/dashboard/chat/page.tsx:AskCompliraPage()
        └── (UC-07 handles auto-submit)
```

### State And Data Transformations

- `item.ask_prompt` (plain text) → `encodeURIComponent()` → URL-safe query param string

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `N/A`

---

## Use Case: UC-07 — Chat page auto-submit on `?prompt=` mount

### Goal
Chat page mounts with `?prompt=<encoded>` query param. Page auto-submits the decoded prompt as if the user typed and pressed Enter.

### Preconditions
- User navigated from situation room card with `?prompt=` param.
- Chat page `sendMessage` function available.

### Expected Outcome
On mount, chat page decodes `?prompt=`, calls `sendMessage(decodedPrompt)`, and normal SSE response stream begins. No user interaction needed.

### Primary Runtime Call Stack

```text
[ENTRY] frontend/app/dashboard/chat/page.tsx:AskCompliraPage()
├── next/navigation:useSearchParams():get("prompt")                   # read ?prompt= param
├── [ASYNC] useEffect([prompt], () => {
│   if (prompt) {
│       const decoded = decodeURIComponent(prompt)
│       sendMessage(decoded)                                          # [STATE] message added
│   }
│ })
└── sendMessage(decoded):
    ├── [STATE] setMessages([...messages, { role: "user", content: decoded }])
    └── [ASYNC] fetch("/api/v1/chat", { method: "POST", body: { message: decoded } })
        └── SSE stream begins → onmessage handlers update [STATE] assistantMessage
```

### Branching / Fallback Paths

```text
[FALLBACK] ?prompt= absent or empty
frontend/app/dashboard/chat/page.tsx:AskCompliraPage()
└── useEffect does nothing → normal chat UI rendered, empty input, no auto-submit
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `Covered`
- Error Path: `N/A`

---

## Use Case: UC-08 — CISO view — Phase 2 live AQL data fetch

### Goal
Phase 2: CISO view fetches real data from ArangoDB via existing AQL tool functions instead of the Phase 1 fixture.

### Preconditions
- Phase 2 deployed. ArangoDB `complira_graph` accessible.
- `get_attack_chain_analysis`, `get_active_threat_detections`, `get_regulatory_deadline_summary`, `get_patch_priority_list` registered in `_TOOL_REGISTRY`.

### Expected Outcome
CISO persona view displays real chain data, threat detections, deadlines, and patch list from ArangoDB.

### Primary Runtime Call Stack

```text
[ENTRY] frontend/app/dashboard/situation/page.tsx:SituationRoomPage()
├── [ASYNC] fetchCISOData():
│   ├── POST /api/v1/chat (tool: get_attack_chain_analysis)           # [IO] SSE/JSON
│   │   └── src/api/v1/endpoints/chat.py:_tool_get_attack_chain_analysis(db, tenant_id, inp)
│   │       └── src/complira_graph/queries/multihop_queries.py:get_attack_chain(db, tenant_id)  [IO]
│   ├── POST /api/v1/chat (tool: get_active_threat_detections)        # [IO]
│   │   └── multihop_queries.py:get_active_threat_detections(db, tenant_id)  [IO]
│   ├── POST /api/v1/chat (tool: get_regulatory_deadline_summary)     # [IO]
│   │   └── multihop_queries.py:get_regulatory_deadline_summary(db, tenant_id)  [IO]
│   └── POST /api/v1/chat (tool: get_patch_priority_list)             # [IO]
│       └── multihop_queries.py:get_patch_priority(db, tenant_id)     [IO]
├── [STATE] setSituationData({ attack_chains, threat_detections, regulatory_deadlines, patch_priority })
└── renders MetricStrip + AlertFeed from live data (same components as Phase 1)
```

### Branching / Fallback Paths

```text
[ERROR] ArangoDB unreachable or tool returns error
src/api/v1/endpoints/chat.py:_stream_response()
└── emits SSE error event → frontend catches → [STATE] setDataError(true)
    └── AlertFeed renders empty state: "Unable to load threat intelligence."  (AC-012)
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `Covered`

---

## Use Case: UC-09 — CISO view empty state when AQL returns zero results

### Goal
When all AQL tool functions return empty arrays (no findings yet for tenant), CISO view renders an informative empty state, not a broken layout.

### Expected Outcome
MetricStrip shows all zeros. AlertFeed shows "No active alerts for this tenant." message.

### Primary Runtime Call Stack

```text
[ENTRY] frontend/app/dashboard/situation/page.tsx:SituationRoomPage()
├── [ASYNC] fetchCISOData() returns { attack_chains: [], threat_detections: [], ... }
├── [STATE] setSituationData(emptyResult)
└── frontend/components/situation/AlertFeed.tsx:AlertFeed({ alerts: [] })
    └── renders <EmptyState message="No active alerts for this tenant." />
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `N/A`

---

## Use Case: UC-10 — Run `init_simulation_schema.py` — 13 collections created

### Goal
Operator runs `python scripts/init_simulation_schema.py`. Script creates 5 document + 8 edge simulation collections in ArangoDB with required indexes. Re-running is safe.

### Preconditions
- ArangoDB `complira_graph` accessible.
- `ARANGO_URL`, `ARANGO_DB`, `ARANGO_USER`, `ARANGO_PASSWORD` env vars set.

### Expected Outcome
All 13 collections exist after first run. Running again produces no error (idempotent). All required indexes present.

### Primary Runtime Call Stack

```text
[ENTRY] scripts/init_simulation_schema.py:main()
├── python-arango:ArangoClient():db("complira_graph")                 # [IO] DB connection
├── for each of 5 document collections:
│   ├── try: db.create_collection(name)                               # [IO]
│   └── except CollectionCreateError: db.collection(name)             # [FALLBACK] already exists
│       └── (no-op; idempotent)
├── for each of 8 edge collections:
│   ├── try: db.create_collection(name, edge=True)                    # [IO]
│   └── except CollectionCreateError: db.collection(name)             # [FALLBACK] already exists
├── for simulation_runs: create persistent index on [tenant_id, seed_export_hash]
├── for attack_chain_findings: create persistent index on [run_id]
└── for simulation_agent_logs: create persistent index on [run_id, significance]
```

### Branching / Fallback Paths

```text
[FALLBACK] collection already exists (re-run / idempotent)
scripts/init_simulation_schema.py:main()
└── CollectionCreateError caught → db.collection(name) → continues to next collection
    # No error raised; no duplicate collection created (AC-013)
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `Covered`
- Error Path: `N/A`

---

## Use Case: UC-11 — `SimulationWritebackService.run_all()` full 7-step write-back

### Goal
`SimulationWritebackService.run_all(report, run_key)` executes all 7 write-back steps, inserting simulation output into ArangoDB. All writes use UPSERT for Prefect-retry safety.

### Preconditions
- `init_simulation_schema.py` has been run (13 collections exist).
- `report` dict contains all required MiroFish simulation output fields.
- `run_key` contains `seed_export_hash` + `tenant_id`.

### Expected Outcome
All 13 steps complete (5 doc + 8 edge types). `simulation_runs` has exactly 1 document for the run. `attack_chain_findings` has N finding documents.

### Primary Runtime Call Stack (v2 — includes all 8 edge collections)

```text
[ENTRY] src/complira_graph/simulation/writeback_service.py:SimulationWritebackService.run_all(report, run_key)
│
├── # Step 1: UPSERT simulation_runs + sim_ran_on + sim_triggered_by
│   └── _upsert_simulation_run(report, run_key)                       # [IO]
│       ├── AQL UPSERT simulation_runs (_key = seed_export_hash + "_" + tenant_id)
│       ├── AQL UPSERT sim_ran_on edge (simulation_runs → repositories)
│       └── AQL UPSERT sim_triggered_by edge (simulation_runs → scan_findings[trigger])
│
├── # Step 2: UPSERT attack_chain_findings → collect finding _keys
│   │       + chain_involves_component edges (finding → components per chain step)
│   └── finding_keys = _upsert_attack_chain_findings(report)          # [IO]
│       ├── AQL UPSERT attack_chain_findings (_key = run_id + "_" + chain_hash)
│       │   └── returns list of upserted _key values
│       └── AQL UPSERT chain_involves_component edges (finding → component, per chain_steps[*])
│
├── # Step 3: UPSERT compliance_gap_findings + gap_violates_requirement edges
│   └── _upsert_compliance_gaps(report)                               # [IO]
│       ├── AQL UPSERT compliance_gap_findings
│       └── AQL UPSERT gap_violates_requirement edges (gap → compliance_requirements)
│
├── # Step 4: UPSERT response_playbook_steps + playbook_addresses_finding edges
│   └── _upsert_playbook_steps(report)                                # [IO]
│       ├── AQL UPSERT response_playbook_steps
│       └── AQL UPSERT playbook_addresses_finding edges (step → attack_chain_finding)
│
├── # Step 5: UPSERT simulation_agent_logs
│   └── _upsert_agent_logs(report)                                    # [IO]
│
├── # Steps 6+7 gated on step 2 finding_keys being non-empty (UC-12)
│   if not finding_keys:
│   └── [FALLBACK] skip steps 6+7 and summary UPSERT, log warning
│
├── # Step 6: UPSERT chain_surfaces_cve + chain_informs_vex (gated on step 2)
│   └── _upsert_finding_cve_edges(finding_keys, report)               # [IO]
│       ├── AQL UPSERT chain_surfaces_cve edges (finding → scan_findings, with chain_probability)
│       └── AQL UPSERT chain_informs_vex edges (finding → vex_statements)
│           └── { do_not_mutate_status: true, advisory_note: ..., source: "mirofish_simulation" }
│           # VEX document status field is NEVER touched (UC-14, AC-016)
│
├── # Step 7: UPSERT chain_calibrates_fair edges (confidence gate ≥ 0.6, gated on step 2)
│   └── _upsert_chain_calibrates_fair_edges(finding_keys, report)     # [IO]
│       └── for each finding with confidence >= 0.6: UPSERT edge (UC-13)
│
└── # Summary UPSERT: update simulation_runs with computed summary fields
    └── _update_simulation_run_summary(run_key, finding_keys, report) # [IO]
        └── AQL UPSERT simulation_runs with:
            { chain_count: COUNT(finding_keys),
              soc_blind_spot_count: COUNT(f where soc_threshold_miss=true),
              top_playbook_action: first step by step_order }
```

### Branching / Fallback Paths

```text
[FALLBACK] run_all() called twice with same seed (idempotency — UC-DR-02)
Step 1 UPSERT: _key = seed_export_hash + "_" + tenant_id already exists → REPLACE with same data
→ produces exactly 1 simulation_runs document (not 2) (AC-015)
```

```text
[ERROR] ArangoDB write failure during any step
writeback_service.py:run_all()
└── exception propagates to Prefect task caller
    └── Prefect retries entire run_all() call
        → all UPSERT steps are idempotent → safe to retry
```

### State And Data Transformations

- `report` dict → typed `SimulationReport` dataclass (internal validation)
- `seed_export_hash + "_" + tenant_id` → document `_key` for `simulation_runs`
- `run_id + "_" + chain_hash` → document `_key` for `attack_chain_findings`
- All documents include `source: "mirofish_simulation"` field (F-14)

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `Covered`
- Error Path: `Covered`

---

## Use Case: UC-12 — Steps 6+7 gated on step 2 finding keys

### Goal
Verify that steps 6 and 7 of the write-back sequence only execute after step 2 returns finding `_key` values. If step 2 returns empty (no findings), steps 6+7 are skipped entirely.

### Preconditions
- `run_all()` called with a valid report.

### Expected Outcome
When step 2 returns `[]`, steps 6+7 are skipped. When step 2 returns `["findings/abc123", ...]`, steps 6+7 execute with those keys. (AC-018)

### Primary Runtime Call Stack

```text
src/complira_graph/simulation/writeback_service.py:run_all()
├── finding_keys = _upsert_attack_chain_findings(report)   # Step 2
│   └── returns [] or ["findings/key1", ...]
│
└── if finding_keys:                                        # gate check
    ├── _upsert_chain_surfaces_cve_edges(finding_keys, report)  # Step 6
    └── _upsert_chain_calibrates_fair_edges(finding_keys, report)  # Step 7
    # Steps 6+7 receive finding_keys as explicit parameter — no implicit dependency
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `N/A`

---

## Use Case: UC-13 — `chain_calibrates_fair` confidence gate (< 0.6 → skip)

### Goal
During step 7, findings with `confidence < 0.6` must not produce `chain_calibrates_fair` edges. Only high-confidence chains calibrate FAIR TEF. (AC-017)

### Primary Runtime Call Stack

```text
src/complira_graph/simulation/writeback_service.py:_upsert_chain_calibrates_fair_edges(finding_keys, report)
└── for finding in report.attack_chain_findings:
    ├── if finding.confidence < 0.6:
    │   └── continue  # [FALLBACK] skip this finding — no edge written
    └── else:
        └── AQL UPSERT chain_calibrates_fair edge  # [IO]
            └── { _from: finding_key, _to: fair_scenario_key,
                  tef_input: finding.chain_probability, confidence: finding.confidence,
                  source: "mirofish_simulation" }
```

### Branching / Fallback Paths

```text
[FALLBACK] all findings have confidence < 0.6
_upsert_chain_calibrates_fair_edges()
└── no edges written; function returns normally
    # No error; no chain_calibrates_fair edges in collection
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `Covered`
- Error Path: `N/A`

---

## Use Case: UC-14 — `chain_informs_vex` edge — VEX status NOT mutated

### Goal
`chain_informs_vex` edges are advisory only. The write-back service writes the edge linking an `attack_chain_finding` to a `vex_statement`, but never modifies the `vex_statements.status` field. (AC-016, schema §6.5)

### Primary Runtime Call Stack

```text
src/complira_graph/simulation/writeback_service.py:_upsert_chain_informs_vex_edges(finding_keys, report)
└── for each finding_key, vex_key pair:
    └── AQL UPSERT chain_informs_vex edge:                 # [IO]
        INSERT { _from: finding_key, _to: vex_key,
                 advisory_note: "simulation chain overlaps with this VEX statement",
                 do_not_mutate_status: true,
                 source: "mirofish_simulation" }
        # NOTE: no UPDATE to vex_statements collection — edge only
        # vex_statements.status is NEVER touched by this function
```

### State And Data Transformations

- Edge carries `do_not_mutate_status: true` as explicit marker
- No AQL `UPDATE vex_statements` issued — write is edge-only

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `N/A`

---

## Use Case: UC-15 — `get_simulation_runs` tool via Ask Complira

### Goal
User asks Ask Complira "show me recent simulation runs". The `get_simulation_runs` chat tool executes, returns a list of simulation runs for the tenant, and the response renders in the chat UI.

### Preconditions
- Phase 3 deployed. `simulation_runs` collection populated by at least one write-back run.
- `get_simulation_runs` registered in `_TOOL_REGISTRY` + `COMPLIRA_TOOLS`.

### Expected Outcome
Chat responds with a list of simulation runs including run ID, status, round count, timestamp. (AC-019)

### Primary Runtime Call Stack

```text
[ENTRY] frontend/app/dashboard/chat/page.tsx:sendMessage("show me recent simulation runs")
└── [ASYNC] POST /api/v1/chat  # [IO]
    └── [ENTRY] src/api/v1/endpoints/chat.py:_stream_response(message, tenant_id, db)
        ├── Claude API tool selection → selects get_simulation_runs  # [ASYNC]
        ├── _TOOL_REGISTRY["get_simulation_runs"](db, tenant_id, inp)
        │   └── _tool_get_simulation_runs(db, tenant_id, inp)        # thin wrapper
        │       └── src/complira_graph/queries/simulation_queries.py:get_simulation_runs(db, tenant_id)  [IO]
        │           └── AQL: FOR r IN simulation_runs FILTER r.tenant_id == @tenant_id
        │                     SORT r.started_at DESC LIMIT 20 RETURN r
        └── tool result → Claude API → SSE text response → frontend renders
```

### Branching / Fallback Paths

```text
[FALLBACK] no simulation runs exist yet
simulation_queries.py:get_simulation_runs()
└── AQL returns []
    └── tool result: { runs: [] }
        → chat response: "No simulation runs found for this tenant."
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `Covered`
- Error Path: `N/A`

---

## Use Case: UC-16 — `SimulationLivePanel` polls status every 3 seconds

### Goal
While a simulation run is active (status = "running"), `SimulationLivePanel` polls `GET /v1/simulation/{run_id}/status` every 3 seconds, updating the round counter and event feed. When status becomes "completed", panel hides and `SimulationResultCard` mounts.

### Preconditions
- Phase 4 deployed. `routers/simulation.py` registered. Active simulation run in `simulation_runs`.

### Expected Outcome
Panel shows round counter ticking up. Event feed shows significance ≥ 0.6 events. On completion, panel unmounts and result card renders. (AC-022)

### Primary Runtime Call Stack

```text
[ENTRY] frontend/components/situation/SimulationLivePanel.tsx:SimulationLivePanel({ runId })
└── [ASYNC] useEffect([runId], () => {
        const interval = setInterval(pollStatus, 3000)                # 3-second interval
        return () => clearInterval(interval)                          # cleanup on unmount
    })
└── pollStatus():
    ├── [ASYNC] fetch(`/api/v1/simulation/${runId}/status`)           # [IO]
    │   └── [ENTRY] src/api/v1/routers/simulation.py:get_simulation_status(run_id, tenant_id, db)
    │       └── src/complira_graph/queries/simulation_queries.py:get_simulation_run_status(db, run_id)  [IO]
    │           └── AQL: FOR r IN simulation_runs FILTER r._key == @run_id RETURN r
    │               # returns doc with: status, round_count, chain_count,
    │               # soc_blind_spot_count, top_playbook_action (from writeback summary step)
    ├── [STATE] setRoundCount(status.round_count)
    ├── [STATE] setEvents(status.recent_events.filter(e => e.significance >= 0.6))
    └── if status.status === "completed":
        ├── [STATE] setRunComplete(true)
        └── clearInterval(interval)
            └── parent mounts SimulationResultCard({ run: status })
```

### Branching / Fallback Paths

```text
[FALLBACK] run transitions to "completed" during poll
SimulationLivePanel.tsx:pollStatus()
└── status.status === "completed"
    └── clearInterval → panel unmounts
        └── frontend/app/dashboard/situation/page.tsx renders SimulationResultCard
```

### State And Data Transformations

- `GET /v1/simulation/{run_id}/status` → `SimulationStatusResponse { run_id, status, round_count, recent_events[] }`
- `recent_events.filter(e => e.significance >= 0.6)` → displayed events

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `Covered`
- Error Path: `N/A`

---

## Use Case: UC-17 — `get_attack_chains_for_cve` tool

### Goal
User asks "what attack chains involve CVE-2021-44228". The tool queries `attack_chain_findings` for chains containing that CVE in `chain_steps`, returns chain docs with probability and SOC flag.

### Preconditions
- Phase 3 deployed. `attack_chain_findings` collection populated.

### Expected Outcome
Chat responds with chain documents linking CVE-2021-44228 to downstream exploit path, including `chain_probability` and `soc_threshold_miss`. (AC-020)

### Primary Runtime Call Stack

```text
[ENTRY] frontend/.../chat sendMessage("attack chains for CVE-2021-44228")
└── [ASYNC] POST /api/v1/chat
    └── src/api/v1/endpoints/chat.py:_stream_response()
        ├── Claude selects get_attack_chains_for_cve({ cve_id: "CVE-2021-44228" })
        └── _tool_get_attack_chains_for_cve(db, tenant_id, inp)      # thin wrapper
            └── simulation_queries.py:get_attack_chains_for_cve(db, tenant_id, cve_id)  [IO]
                └── AQL: FOR f IN attack_chain_findings
                           FILTER f.tenant_id == @tenant_id
                           FILTER @cve_id IN f.chain_steps[*].cve_id
                           RETURN f
                    → list of chain dicts with probability, soc_threshold_miss, chain_steps
```

### Branching / Fallback Paths

```text
[FALLBACK] no chains found for CVE
simulation_queries.py:get_attack_chains_for_cve()
└── AQL returns []
    → chat response: "No attack chains found involving CVE-2021-44228."
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `Covered`
- Error Path: `N/A`

---

## Use Case: UC-DR-01 — AttackChainGraph dagre layout compatibility

### Goal
Validate that `@xyflow/react` v12 + `@dagrejs/dagre` produces a valid left-to-right layout during Phase 1 implementation. If incompatible, confirm fallback to `reactflow` v11.

### Technical Risk Objective
OQ-02: React Flow v12 uses `@xyflow/react` package. `@dagrejs/dagre` is the standard dagre package. Compatibility is not yet confirmed for v12.

### Expected Observable Outcome
Phase 1 `AttackChainGraph` renders the mock `CVE-2021-44228` chain with ≥3 nodes in a left-to-right layout with no layout errors in the console. If `@xyflow/react` + `@dagrejs/dagre` is confirmed working, OQ-02 is closed. If not, switch to `reactflow` (v11) and re-run.

### Primary Runtime Call Stack

```text
frontend/components/situation/AttackChainGraph.tsx:buildGraphElements(chain)
├── const g = new dagre.graphlib.Graph()                              # @dagrejs/dagre
├── g.setDefaultEdgeLabel(() => ({}))
├── g.setGraph({ rankdir: "LR", nodesep: 50, ranksep: 80 })
├── for each node: g.setNode(node.id, { width: 120, height: 40 })
├── for each edge: g.setEdge(edge.source, edge.target)
├── dagre.layout(g)                                                   # compute positions
└── return { nodes: g.nodes().map(id => ({
               ...reactFlowNode,
               position: g.node(id)
           })),
             edges: reactFlowEdges }
```

### Branching / Fallback Paths

```text
[FALLBACK] @xyflow/react v12 + dagre incompatibility
package.json: replace "@xyflow/react" with "reactflow" (v11)
AttackChainGraph.tsx: replace import from "@xyflow/react" with "reactflow"
# dagre layout call is identical for v11
# OQ-02 resolution: use reactflow v11 if v12 dagre integration fails
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `Covered`
- Error Path: `N/A`

---

## Use Case: UC-DR-02 — SimulationWritebackService idempotency under Prefect retry

### Goal
Validate that calling `run_all()` twice with the same `seed_export_hash + tenant_id` produces exactly 1 `simulation_runs` document (not 2). UPSERT must be truly idempotent.

### Technical Risk Objective
Prefect tasks may retry on transient failures. If UPSERT is not correct, each retry creates a duplicate document, corrupting simulation history.

### Expected Observable Outcome
After 2 calls with the same `run_key`, `db.collection("simulation_runs").count()` increases by 1, not 2. (AC-015)

### Primary Runtime Call Stack

```text
# Call 1:
writeback_service.py:_upsert_simulation_run(report, run_key)
└── AQL UPSERT { _key: "hash123_tenant_abc" }
    INSERT { _key: "hash123_tenant_abc", ... }
    REPLACE { ... }
    IN simulation_runs
    → 1 document written

# Call 2 (same seed):
writeback_service.py:_upsert_simulation_run(report, run_key)
└── AQL UPSERT { _key: "hash123_tenant_abc" }
    INSERT ...
    REPLACE { ... }              # replaces existing doc — no new doc created
    IN simulation_runs
    → still 1 document in collection (AC-015)
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `N/A`

---

## §UC-18 — CISO View: SituationAbstractionLayer compute_ciso()

**Source:** Requirement (R-012, R-013)
**Coverage:** Primary ✓ | Fallback ✓ | Error ✓

### Primary Path

```
[ENTRY] Browser GET /dashboard/situation (CISO persona active)
  frontend/app/dashboard/situation/page.tsx:SituationRoomPage()
    useEffect() on mount
      [ASYNC] fetch("GET /v1/situation/ciso", {Authorization: Bearer <token>})
        src/api/v1/endpoints/situation.py:get_ciso_situation()
          Depends(get_current_customer) → resolves tenant_id
          # RBAC policy: situation endpoints are soft-open — any authenticated tenant user may call any persona endpoint.
          # Board-persona users CAN call /v1/situation/ciso. Data scope is always tenant-scoped only (no cross-tenant risk).
          # Persona-level RBAC gating is deferred — add role check to Depends() chain if stricter access control required.
          [IO] SituationAbstractionLayer(db).compute_ciso(tenant_id)
            src/complira_graph/situation/abstraction_layer.py:compute_ciso()
              [IO] situation_abstraction_queries.get_threat_category_rollup(db, tenant_id)
                → returns List[ThreatCategory] grouped by tactic bucket (no CVE IDs)
              [IO] situation_abstraction_queries.get_attack_chain_findings_for_run(db, tenant_id, latest_run_id=None)
                AQL RETURN projection: RETURN {chain_probability: f.chain_probability, soc_threshold_miss: f.soc_threshold_miss}
                → returns List[{chain_probability: float, soc_threshold_miss: bool}] ONLY — chain_steps[] NOT returned
                → prevents CVE/CWE data in chain_steps from entering the abstraction layer compute path
              [IO] situation_abstraction_queries.get_attck_coverage(db, tenant_id)
                → returns float (0–100): distinct technique_ids across threat_category_rollups / known ATT&CK technique universe × 100
              [IO] situation_abstraction_queries.get_compliance_failures_by_framework(db, tenant_id)
                → returns List[ControlFailure] by framework name
              [IO] situation_abstraction_queries.get_simulated_mttd(db, tenant_id)
                → returns mttd_hours (float) derived from soc_threshold_miss rate
              [IO] situation_abstraction_queries.get_posture_snapshot_history(db, tenant_id, limit=4)
                → returns List[PostureSnapshot] sorted by computed_at desc (limit=4 covers monthly delta + quarterly trend)
                → posture_delta   = snapshots[0].posture_score − snapshots[1].posture_score if len >= 2 else None
                → quarterly_trend = "up" if snapshots[0].posture_score > snapshots[3].posture_score else "down" if len >= 4 else None
              posture_score = _compute_posture_score(chain_findings, gaps, attck_coverage_pct)
                # chain_findings: from get_attack_chain_findings_for_run() — individual chain_probability values
                # gaps: from get_compliance_failures_by_framework() — used as gap_count
                # attck_coverage_pct: from get_attck_coverage()
                # formula: 100 − round(mean(chain_probability) × 40) − (gap_count × 3) − round(soc_miss_rate × 20) + round(attck_coverage_pct × 0.1)
                # clamped to [0, 100]
              posture_delta = snapshots[0].posture_score − snapshots[1].posture_score if len(snapshots) >= 2 else None
              action_priorities = _derive_action_priorities(gaps, threat_categories)
              [IO] _write_posture_snapshot(db, tenant_id, ciso_situation)
                → UPSERT posture_snapshots {_key: f"{tenant_id}_{iso_now}"}
              return CISOSituation(
                posture_score=int,         # no CVE IDs
                posture_delta=int|None,
                attck_coverage_pct=float,
                threat_categories=[ThreatCategory(bucket_name, display_name, breach_probability, critical_asset_count)],
                control_failures=[ControlFailure(framework, failure_count, coverage_pct)],
                mttd_hours=float,
                mttd_target_hours=24.0,
                mttr_days=None,           # enrichment-ready: derive from response_playbook_steps timing when available
                mttr_target_days=7.0,
                remediation_sla_pct=None, # enrichment-ready: % findings remediated within SLA — requires playbook step deadline tracking
                action_priorities=[ActionPriority(rank, description, owner, due_label, urgency)],
                snapshot_timestamp=str
              )
          return JSONResponse(ciso_situation.model_dump())   # zero CVE IDs in output
      setState(cisoData)
    render PostureScoreCard(posture_score, posture_delta)
    render ThreatCategoryList(threat_categories)
    render ComplianceFailurePanel(control_failures)
    render SimulatedMetricCard(mttd_hours, mttd_target_hours)
    render ActionPriorityList(action_priorities)
```

### Fallback Path

```
[FALLBACK] No simulation data for tenant (no completed runs)
  abstraction_layer.py:compute_ciso()
    get_threat_category_rollup() → []
    get_compliance_failures_by_framework() → []
    get_simulated_mttd() → None
    _compute_posture_score(chains=[], gaps=[], coverage=0) → 100 (no penalty)
    return CISOSituation(
      posture_score=100,
      threat_categories=[],
      control_failures=[],
      mttd_hours=None,
      action_priorities=[]
    )
  Frontend renders empty state: "No simulation data yet — trigger a monthly posture sim"
```

### Error Path

```
[ERROR] ArangoDB unavailable
  situation.py:get_ciso_situation()
    SituationAbstractionLayer(db).compute_ciso() raises ArangoError
    → HTTPException(status_code=503, detail="graph_unavailable")
  Frontend catches non-ok response → shows error banner
```

---

## §UC-19 — Board View: SituationAbstractionLayer compute_board()

**Source:** Requirement (R-012, R-014)
**Coverage:** Primary ✓ | Fallback ✓ | Error ✓

### Primary Path

```
[ENTRY] Browser GET /dashboard/situation (Board/CFO persona active)
  frontend/app/dashboard/situation/page.tsx:SituationRoomPage()
    useEffect() on Board persona mount
      [ASYNC] fetch("GET /v1/situation/board", {Authorization: Bearer <token>})
        src/api/v1/endpoints/situation.py:get_board_situation()
          Depends(get_current_customer) → resolves tenant_id
          # RBAC policy: situation endpoints are soft-open — any authenticated tenant user may call any persona endpoint.
          # Board-persona users CAN call /v1/situation/ciso. Data scope is always tenant-scoped only (no cross-tenant risk).
          # Persona-level RBAC gating is deferred — add role check to Depends() chain if stricter access control required.
          [IO] SituationAbstractionLayer(db).compute_board(tenant_id)
            src/complira_graph/situation/abstraction_layer.py:compute_board()
              [IO] situation_abstraction_queries.get_business_impact_findings(db, tenant_id)
                → returns List[BusinessImpactFinding] (agent_type=cfo_agent|board_member_agent)
              [IO] situation_abstraction_queries.get_threat_category_rollup(db, tenant_id)
                → used to derive breach_probability_pct = max(c.max_chain_probability for c in rollups)
              [IO] situation_abstraction_queries.get_posture_snapshot_history(db, tenant_id, limit=2)
              [IO] situation_abstraction_queries.get_compliance_failures_by_framework(db, tenant_id)
                → returns List[ControlFailure] — used as `gaps` for _derive_board_priorities()
              reputational_risk_score = sum(f.estimated_value for f in findings if f.impact_type == "reputational_risk") / 10_000_000
                → normalized to [0.0, 1.0]; default 0.0 if no reputational_risk findings
              financial_findings = [f for f in findings if f.impact_type == "financial_exposure"]
              financial_exposure_low = min(f.estimated_value for f in financial_findings) if financial_findings else breach_prob × 500_000
              financial_exposure_high = max(f.estimated_value for f in financial_findings) if financial_findings else breach_prob × 5_000_000
              regulatory_fine_risk = _group_fine_risk_by_framework(findings)
              board_priorities = _derive_board_priorities(findings, gaps)
              return BoardSituation(
                breach_probability_pct=float,      # no CVE IDs
                financial_exposure_usd_low=int,
                financial_exposure_usd_high=int,
                regulatory_fine_risk=[{"framework": str, "max_fine_usd": int}],
                reputational_risk_score=float,
                board_priorities=[ActionPriority(governance language only)],
                snapshot_timestamp=str
              )
          return JSONResponse(board_situation.model_dump())   # zero CVE IDs
      setState(boardData)
    render BoardMetricPanel(breach_probability_pct, financial_exposure_usd_low, financial_exposure_usd_high)
    render ActionPriorityList(board_priorities, governance_mode=True)
```

### Fallback Path

```
[FALLBACK] No business_impact_findings (monthly_posture_sim not yet run)
  compute_board()
    get_business_impact_findings() → []
    if not rollups:  # No simulation data at all — new tenant
      financial_exposure_usd_low  = None   # Not $0 — no data yet
      financial_exposure_usd_high = None
      no_data_message = "Run a monthly posture simulation to calculate financial exposure"
    else:  # Rollup data exists but no CFO agent findings
      financial_exposure_usd_low  = round(breach_prob * 500_000)    # Conservative estimate
      financial_exposure_usd_high = round(breach_prob * 5_000_000)  # Upper bound estimate
      no_data_message = None
    board_priorities → derived from gap data only (no CFO agent narratives)
  Frontend: renders estimated ranges with "Estimated — run monthly posture sim for precise values"
```

### Error Path

```
[ERROR] ArangoDB unavailable → 503, same as UC-18 error path
```

---

## §UC-20 — Threat Categories Grouped by ATT&CK Tactic Bucket

**Source:** Requirement (R-013)
**Coverage:** Primary ✓ | Fallback ✓ | Error N/A

### Primary Path

```
abstraction_layer.py:_build_threat_categories(db, tenant_id)
  [IO] queries/situation_abstraction_queries.py:get_threat_category_rollup(db, tenant_id)
    AQL: FOR r IN threat_category_rollups
           FILTER r.tenant_id == @tenant_id
           SORT r.max_chain_probability DESC
           RETURN r
    → List[{bucket_name, display_name, max_chain_probability, critical_asset_count, technique_ids}]
  for each rollup row:
    ThreatCategory(
      bucket_name=rollup.bucket_name,        # "remote_code_execution"
      display_name=rollup.display_name,      # "Remote code execution"
      breach_probability=rollup.max_chain_probability,
      critical_asset_count=rollup.critical_asset_count
      # NO cve_id field — tactic-level grouping only
    )
  return sorted list by breach_probability desc
```

### Fallback Path

```
[FALLBACK] threat_category_rollups empty (step 8 not yet run OR no chains in any bucket)
  get_threat_category_rollup() → []
  _build_threat_categories() → []
  CISOSituation.threat_categories = []
  [STATE mutation: posture_score penalty from chain_probability still applies even if rollup empty]
```

---

## §UC-21 — Board Priorities Use Governance Language

**Source:** Requirement (R-014)
**Coverage:** Primary ✓ | N/A | N/A

### Primary Path

```
abstraction_layer.py:_derive_board_priorities(findings, gaps)
  board_member_findings = [f for f in findings if f.agent_type == "board_member_agent"]
  for finding in board_member_findings (sorted by confidence desc):
    ActionPriority(
      rank=i+1,
      description=finding.narrative,   # governance language: "Disclosure obligation under SEC Rule 10b-5"
      owner=_map_impact_type_to_owner(finding.impact_type),
      due_label=_derive_due_label(finding),
      urgency=_derive_urgency(finding)
      # No CVE IDs, CVSS scores, or package names in description field
    )
  return top 2 board priorities
  [DECISION] if board_member_findings empty → derive from compliance_gap_findings using governance language templates
```

---

## §UC-22 — posture_snapshot Written After compute_ciso(); Delta Computed

**Source:** Requirement (R-015)
**Coverage:** Primary ✓ | Fallback ✓ | N/A

### Primary Path

```
abstraction_layer.py:compute_ciso(tenant_id)
  [IO] ... (all computations complete)
  [IO] _write_posture_snapshot(db, tenant_id, ciso_situation)
    src/complira_graph/situation/abstraction_layer.py:_write_posture_snapshot()
      _key = f"{tenant_id}_{datetime.utcnow().isoformat()}"
      [IO] db.aql.execute(
        "UPSERT {_key: @key} INSERT @doc UPDATE @doc IN posture_snapshots",
        bind_vars={
          "key": _key,
          "doc": {
            "tenant_id": tenant_id,
            "posture_score": ciso_situation.posture_score,
            "attck_coverage_pct": ciso_situation.attck_coverage_pct,
            "mttd_hours": ciso_situation.mttd_hours,
            "computed_at": _key.split("_", maxsplit=1)[1],   # maxsplit=1: tenant_id may contain underscores
            "run_id": latest_run_id
          }
        }
      )
  [STATE] ciso_situation.posture_delta computed before snapshot write:
    snapshots = get_posture_snapshot_history(db, tenant_id, limit=4)
    → limit=4 supports monthly delta (index 0 vs 1) and quarterly trend (index 0 vs 3)
    posture_delta = snapshots[0].posture_score − snapshots[1].posture_score if len(snapshots) >= 2 else None
    # Note: limit=4 fetched; only [0] and [1] used for monthly delta; [0] and [3] used for quarterly trend
    # Snapshot write happens AFTER this computation (correct ordering confirmed)
```

### Fallback Path

```
[FALLBACK] First compute for tenant — no prior snapshots
  get_posture_snapshot_history() → []
  posture_delta = None
  snapshot still written → becomes baseline for next compute
```

---

## §UC-23 — SimulationWritebackService Step 8: rollup_threat_categories()

**Source:** Requirement (R-016, R-018)
**Coverage:** Primary ✓ | Fallback ✓ | N/A

### Primary Path

```
src/complira_graph/simulation/writeback_service.py:run_all(payload)
  ... (steps 1–7 complete, finding_keys returned) ...
  _step8_rollup_threat_categories(payload, finding_keys)
    src/complira_graph/simulation/writeback_service.py:_step8_rollup_threat_categories()
      TACTIC_BUCKETS = {
        "remote_code_execution": ["T1190","T1059","T1203","T1210"],
        "credential_exposure":   ["T1552","T1078","T1539","T1111"],
        "cloud_misconfiguration":["T1580","T1098","T1530"],
        "patch_gaps":            ["T1190"],  # firmware-specific via EMBA flag
      }
      [IO] simulation_queries.get_attack_chain_findings_for_run(db, run_id)
                → chains  [delegates to query module per allowed dependency direction]
      for bucket_name, techniques in TACTIC_BUCKETS.items():
        chains_in_bucket = [c for c in chains if any(step["technique"] in techniques for step in c.chain_steps)]
        if not chains_in_bucket: continue
        max_prob = max(c.chain_probability for c in chains_in_bucket)
        critical_asset_count = _count_critical_assets(chains_in_bucket)
        [IO] db.aql.execute(
          "UPSERT {_key: @key} INSERT @doc UPDATE @doc IN threat_category_rollups",
          bind_vars={_key: f"{run_id}_{bucket_name}", ...}
        )
  _step8_write_business_impact_findings(payload)
    # Separate from rollup — gated ONLY on agent_outputs non-empty, NOT on finding_keys
    # Ensures CFO/board agent outputs are written even when step 2 found 0 attack chains
    for agent_output in payload.get("agent_outputs", []):
      if agent_output["agent_type"] not in ("cfo_agent", "board_member_agent"): continue
      [IO] UPSERT INTO business_impact_findings {_key: f"{run_id}_{agent_type}_{impact_type}"}
```

### Fallback Path

```
[FALLBACK] step 2 returned 0 finding_keys
  _step8_rollup_threat_categories() → no-op (all buckets empty, no UPSERTs executed)
  business_impact_findings → written only if agent_outputs present in payload
```

---

## §UC-24 — POST /v1/mirofish/trigger: monthly_posture_sim

**Source:** Requirement (R-017)
**Coverage:** Primary ✓ | N/A | Error ✓

### Primary Path

```
[ENTRY] POST /v1/mirofish/trigger
  body: {trigger_type: "monthly_posture_sim", tenant_id: "aquadrive_001"}
  src/api/v1/endpoints/mirofish.py:trigger_mirofish_run()
    Depends(get_current_customer) → resolves tenant_id
    [IO] seed_extractor.extract_monthly_posture_seed(db, tenant_id)
      src/complira_graph/mirofish/seed_extractor.py:extract_monthly_posture_seed()
        [IO] AQL: export full product surface subgraph
          FOR c IN components FILTER c.tenant_id == @tenant_id
          LET cves = (FOR v IN 1..1 OUTBOUND c scan_findings_component_link RETURN v)
          LET cwes = (FOR w IN 1..1 OUTBOUND cves cve_maps_cwe RETURN w)
          RETURN {components: [...], cves: [...], cwes: [...], compliance_requirements: [...]}
        return seed_json (MiroFish seed format)
    agent_config = _build_agent_config("monthly_posture_sim")
      # includes cfo_agent + board_member_agent + existing attacker/defender/regulator personas
      # rounds: 50 (vs 40 for kev_triggered)
    [ASYNC] MiroFishTriggerClient.trigger(seed_json, agent_config)
      src/complira_graph/mirofish/trigger_client.py:trigger()
        [IO] POST MiroFish engine API /api/simulation
          headers: {Authorization: Bearer {MIROFISH_API_KEY}}   # key from env var; missing key → ConfigurationError on startup
          body: {seed: seed_json, agent_config: agent_config, tenant_id: tenant_id}
          → {run_id: "mf_run_abc123", status: "queued"}
    return JSONResponse({run_id: "mf_run_abc123", status: "queued"})
```

### Error Path

```
[ERROR] MiroFish engine unreachable
  trigger_client.trigger() → httpx.ConnectError
  → HTTPException(status_code=503, detail="mirofish_unavailable")

[ERROR] Seed extractor returns empty (tenant has no components/CVEs)
  extract_monthly_posture_seed() → {}
  → HTTPException(status_code=422, detail="insufficient_seed_data")

[ERROR] MiroFish returns 401 Unauthorized (API key expired or misconfigured)
  trigger_client.trigger() → httpx.HTTPStatusError(status_code=401)
  → HTTPException(status_code=502, detail="mirofish_auth_failure")

[ERROR] Empty seed (no components/CVEs for tenant)
  extract_monthly_posture_seed() → {}
  → HTTPException(status_code=422, detail="insufficient_seed_data")
  [Note: overrides error-handling table which said "proceed with empty seed" — 422 is authoritative; empty seed wastes 50 simulation rounds]
```

---

## §UC-25 — GET /v1/mirofish/status/{run_id}

**Source:** Requirement (R-017)
**Coverage:** Primary ✓ | N/A | Error ✓

### Primary Path

```
[ENTRY] GET /v1/mirofish/status/{run_id}
  src/api/v1/endpoints/mirofish.py:get_mirofish_status()
    Depends(get_current_customer) → resolves tenant_id
    [IO] AQL: FOR r IN simulation_runs FILTER r._key == @run_id AND r.tenant_id == @tenant_id RETURN r
      → ownership check BEFORE calling MiroFish (prevents tenant probing of other tenants' run IDs)
      if not rows: raise HTTPException(status_code=404, detail="run_not_found")
    local_run = rows[0]
    [ASYNC] MiroFishTriggerClient.get_status(run_id)
      src/complira_graph/mirofish/trigger_client.py:get_status()
        [IO] GET MiroFish engine API /api/simulation/{run_id}
          headers: {Authorization: Bearer {MIROFISH_API_KEY}}
          → {run_id, status, started_at, completed_at, round_count}
    writeback_status = local_run.get("status", "unknown")  # from simulation_runs collection
    return JSONResponse({
      run_id: run_id,
      mirofish_status: mirofish_response.status,
      writeback_status: writeback_status,   # "running"|"completed"|"failed" from simulation_runs.status
      started_at: mirofish_response.started_at,
      completed_at: mirofish_response.completed_at
    })
```

### Error Path

```
[ERROR] run_id not found in MiroFish
  trigger_client.get_status() → 404 from MiroFish engine
  → HTTPException(status_code=404, detail="run_not_found")

[ERROR] run belongs to different tenant
  simulation_runs AQL returns [] → HTTPException(status_code=404, detail="run_not_found")
```

---

## §UC-26 — BoardSituation.financial_exposure from business_impact_findings

**Source:** Requirement (R-018)
**Coverage:** Primary ✓ | Fallback ✓ | N/A

### Primary Path

```
abstraction_layer.py:compute_board(tenant_id)
  [IO] situation_abstraction_queries.get_business_impact_findings(db, tenant_id)
    AQL: FOR f IN business_impact_findings
           FILTER f.tenant_id == @tenant_id
           SORT f.confidence DESC
           RETURN f
    → [
        {agent_type: "cfo_agent", impact_type: "financial_exposure", estimated_value: 2400000, currency: "USD", narrative: "breach of this asset costs $2.4M in recovery + regulatory penalty"},
        {agent_type: "board_member_agent", impact_type: "regulatory_fine_risk", ...},
        ...
      ]
  financial_findings = [f for f in findings if f.impact_type == "financial_exposure"]
  regulatory_findings = [f for f in findings if f.impact_type == "regulatory_fine_risk"]
  financial_exposure_usd_low  = min(f.estimated_value for f in financial_findings)
  financial_exposure_usd_high = max(f.estimated_value for f in financial_findings)
  regulatory_fine_risk = _group_fine_risk_by_framework(regulatory_findings)
    # Uses f.framework structured field (NOT narrative string matching)
    # f.framework == "NIS2" | "SEC" | "CRA" etc. — set at write-back time by SimulationWritebackService
    # → [{"framework": "NIS2", "max_fine_usd": sum(f.estimated_value for f in findings where f.framework == "NIS2")}]
  [DECISION] all values are dollar amounts + governance text; NO CVE IDs, NO CVSS scores
```

### Fallback Path

```
[FALLBACK] monthly_posture_sim not yet run — business_impact_findings empty
  financial_findings = []
  breach_prob = max(c.max_chain_probability for c in rollups) if rollups else 0.0
  financial_exposure_usd_low  = round(breach_prob × 500_000)
  financial_exposure_usd_high = round(breach_prob × 5_000_000)
  regulatory_fine_risk = []
  BoardSituation.board_priorities includes note: "Run monthly posture simulation for CFO-agent financial analysis"
```

---

## §UC-27 — compute_ciso() Stale threat_category_rollups Detection

**Source:** Requirement (R-012, R-013)
**Coverage:** Primary ✓ | Fallback ✓ | N/A

### Primary Path (stale rollup detected)

```
abstraction_layer.py:compute_ciso(tenant_id)
  [IO] situation_abstraction_queries.get_latest_run_id(db, tenant_id)
    AQL: FOR r IN simulation_runs
           FILTER r.tenant_id == @tenant_id AND r.status == "completed"
           SORT r.completed_at DESC LIMIT 1 RETURN r._key
    → latest_run_id: str | None
  [IO] situation_abstraction_queries.get_threat_category_rollup(db, tenant_id)
    → rollups: List[{bucket_name, run_id, max_chain_probability, ...}]
  [DECISION] if rollups and rollups[0].run_id != latest_run_id:
    rollup_age = rollups[0].get("computed_at", "unknown date")
    data_staleness_warning = f"Threat data is from a prior simulation (last updated: {rollup_age}). Trigger a new monthly simulation for current data."
    # No internal run IDs exposed — CISO-readable message only
    # Stale rollups: step 8 may have failed for the latest run
    # Still return CISOSituation — do not block on staleness
  else:
    data_staleness_warning = None
  return CISOSituation(..., data_staleness_warning=data_staleness_warning)
  [STATE] CISOSituation.data_staleness_warning field:
    - None: rollup is current
    - str: rollup is from a prior run; frontend may show "Data may be outdated — last updated <timestamp>"
```

### Fallback Path (no completed runs yet)

```
[FALLBACK] get_latest_run_id() → None (no completed simulation runs for tenant)
  data_staleness_warning = None   # no runs → no stale data, just no data
  CISOSituation.threat_categories = []
  CISOSituation.posture_score = 100 − gap_count × 3  # chain and coverage terms drop to 0
```
