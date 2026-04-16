# Investigation Notes — situation-room-and-simulation

**Status:** Complete
**Triage:** `Large`
**Last Updated:** 2026-04-12

---

## Sources Consulted

- `frontend/app/dashboard/` — current route structure and naming conventions
- `frontend/app/dashboard/page.tsx` — current main dashboard (utility overview, not situation room)
- `frontend/app/dashboard/chat/page.tsx` — Ask Complira, SSE streaming, TOOL_LABELS
- `frontend/app/dashboard/layout.tsx` — sidebar nav, persona session
- `frontend/package.json` — dependency inventory
- `src/api/v1/endpoints/chat.py` — _TOOL_REGISTRY, COMPLIRA_TOOLS, all tool implementations
- `src/complira_graph/queries/multihop_queries.py` — Phase 2 tool backends
- `src/complira_graph/queries/deployment_reality_queries.py` — Phase 2 tool backends
- `scripts/init_phase5_schema.py` — canonical schema init pattern (CollectionCreateError try/except)
- `simulation_schema_design_v1.1.docx` — authoritative schema spec for Phase 3
- `dashboard_impl_plan.docx` — authoritative UX spec for Phase 1+2

---

## Key Findings

### Frontend

**F-01: No Zustand or React Flow in package.json**
Both must be added as new dependencies before Phase 1 implementation.
- `zustand` — persona state management (lightweight, no boilerplate)
- `reactflow` (or `@xyflow/react` — the new package name for React Flow v12+) — attack chain graph
- `@dagrejs/dagre` — layout algorithm for left-to-right chain layout

**F-02: Current `/dashboard` page is a utility overview, not a situation room**
`dashboard/page.tsx` shows: API token count, SBOM scan count, KG node count, recent scans list.
It is not the target. The situation room is a new route `/dashboard/situation` running alongside the existing page. The sidebar nav entry for "Ask Complira" and "Dashboard" currently exist; "Situation Room" needs to be added.
`dashboard/layout.tsx` navigation array is the single place to add the new nav entry.

**F-03: Radix Tabs already available**
`@radix-ui/react-tabs` is installed. The persona switcher can use this instead of a custom tab component, saving implementation time.

**F-04: Chat page `sendMessage` pattern is the Ask Complira integration hook**
`chat/page.tsx` exposes `sendMessage(text: string)` via its internal state. The "Ask Complira" button on situation room cards must navigate to `/dashboard/chat` with a `?prompt=<encoded>` query param, which the chat page reads on mount and fires automatically. This keeps the two pages decoupled.

**F-05: Mock data fixture must mirror AQL response shapes**
The Phase 2 swap requirement (zero component rewrites) means the fixture JSON keys must match exactly what the real tool functions return. The relevant tool return shapes are:
- `get_attack_chain_analysis` → `multihop_queries.get_attack_chain()` → list of chain objects
- `get_active_threat_detections` → `multihop_queries.get_active_threat_detections()` → list of detection objects
- `get_regulatory_deadline_summary` → `multihop_queries.get_regulatory_deadline_summary()` → list with deadline fields
- `get_patch_priority_list` → `multihop_queries.get_patch_priority()` → list of prioritized findings

**F-06: No `situation` route exists yet**
`frontend/app/dashboard/` has: chat, enrichment, profile, projects, reference, repositories, scans, settings, tokens, vex. No `situation` folder. Route must be created.

### Backend

**F-07: All Phase 2 tools are fully implemented in `_TOOL_REGISTRY`**
`get_attack_chain_analysis`, `get_active_threat_detections`, `get_regulatory_deadline_summary`, `get_patch_priority_list` — all wired via `multihop_queries` module at lines 2047–2110 of chat.py. No new backend code needed for Phase 2.

**F-08: New simulation chat tools (Phase 3) need new query functions + _TOOL_REGISTRY entries**
4 new tools needed: `get_simulation_runs`, `get_attack_chains_for_cve`, `get_playbook_for_run`, `get_compliance_gaps_for_run`. These read from the new simulation collections. Pattern matches existing tool implementations — add to chat.py `_TOOL_REGISTRY` and `COMPLIRA_TOOLS`.

**F-09: chat.py is already 3,523 lines**
The Stage 8 code review size policy flags files >700 non-empty lines for Design Impact review. chat.py is deeply over this threshold. New simulation tools should go into a dedicated module `src/complira_graph/queries/simulation_queries.py` (same pattern as `multihop_queries.py`) and be thin wrappers in chat.py. This is the correct architectural pattern already in use.

**F-10: Schema init pattern is `CollectionCreateError` try/except**
`init_phase5_schema.py` uses `try: db.create_collection(...) except CollectionCreateError: db.collection(...)` for idempotency. `init_simulation_schema.py` must follow identical pattern.

### Simulation Schema

**F-11: 5 document + 8 edge collections, all new**
Per `simulation_schema_design_v1.1.docx`. None exist yet. Named graph membership defined:
- `scanner_evidence_graph`: simulation_runs, attack_chain_findings, sim_ran_on, sim_triggered_by, chain_surfaces_cve, chain_involves_component, playbook_addresses_finding
- `compliance_graph`: compliance_gap_findings, gap_violates_requirement, chain_informs_vex
- `risk_quantification_graph`: chain_calibrates_fair

**F-12: SimulationWritebackService is a Python class, 7-step write-back sequence**
Steps 1–5 are independent; steps 6 and 7 depend on step 2 (`attack_chain_findings` keys). All steps use UPSERT. Class should live at `src/complira_graph/simulation/writeback_service.py`. Prefect task will call it.

**F-13: chain_calibrates_fair is edge-only — does NOT update fair_scenarios documents**
Schema doc §6.5 explicitly states write-back is append-only. `chain_calibrates_fair` edges carry `tef_input` but do not patch `fair_scenarios.tef_most_likely`. FAIR analysis tool reads the edge for calibrated TEF. This resolves OQ-04.

**F-14: Simulation write-back produces `source: "mirofish_simulation"` on all new nodes/edges**
GraphRAG tier routing requires this field. All writes must include it.

### Open Questions Resolved

- **OQ-01 (situation route vs replace dashboard):** `/dashboard/situation` is a new route alongside the existing `/dashboard`. Existing dashboard stays — it's a different purpose (utility overview vs situation room).
- **OQ-04 (chain_calibrates_fair):** Edge-only. No `fair_scenarios` document mutation.
- **OQ-05 (init script idempotency):** Use `CollectionCreateError` try/except, matching existing pattern.

### Open Questions Still Open

- **OQ-02:** React Flow v12 uses `@xyflow/react` package name. Need to confirm dagre plugin works with v12. Risk: may need to use React Flow v11 (`reactflow` package) if v12 dagre support is incomplete.
- **OQ-03:** SimulationLivePanel real-time updates — SSE vs polling. Decision: SSE reuse is cleaner but requires a new backend endpoint. For Phase 4, use 3-second polling against a `GET /api/v1/simulation/{run_id}/status` endpoint. Simpler and avoids adding another streaming route.

---

## Scope Triage: `Large`

**Signals:**
- New frontend route + 10+ new components
- New ArangoDB schema (5 doc collections + 8 edge collections + index set)
- New Python service (`SimulationWritebackService`, ~400 lines)
- New query module (`simulation_queries.py`)
- 4 new chat tools in `_TOOL_REGISTRY`
- New backend API endpoint (`GET /simulation/{run_id}/status` for Phase 4 polling)
- Cross-layer: frontend → API → ArangoDB + chat tools → graph queries
- 4 phased delivery increments with clear exit criteria per phase

**Conclusion:** `Large` — full workflow applies: proposed-design.md required before implementation plan.

---

## Implications for Requirements / Design

- Phase 1 fixture must be in `frontend/src/fixtures/` (create this directory — doesn't exist)
- `@xyflow/react` v12 is the correct React Flow package; `@dagrejs/dagre` is the layout dep
- Persona switcher state (Zustand store) should be at `frontend/lib/stores/situation-store.ts`
- `SimulationWritebackService` goes in `src/complira_graph/simulation/` (new module directory)
- `simulation_queries.py` goes in `src/complira_graph/queries/` (matches existing pattern)
- New nav entry in `dashboard/layout.tsx` navigation array: `{ name: "Situation Room", href: "/dashboard/situation", icon: LayoutGrid }`
- Phase 4 polling endpoint: `GET /v1/simulation/{run_id}/status` → new FastAPI router in `src/api/v1/routers/simulation.py`
