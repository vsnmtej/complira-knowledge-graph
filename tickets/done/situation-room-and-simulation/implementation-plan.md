# Implementation Plan — Situation Room + MiroFish Simulation

## Basis

- Design Version: `v2`
- Call Stack Version: `v2`
- Stage 5 Gate: `Go Confirmed` (Rounds 2+3 clean)

---

## Phase 1 — Static Prototype (Demo-Ready)

### Tasks (ordered by dependency)

| Task | Change ID | File | Status |
| --- | --- | --- | --- |
| T-001 | C-010 | `frontend/package.json` — add `@xyflow/react`, `@dagrejs/dagre` | Pending |
| T-002 | — | `frontend/lib/types/situation.ts` — TypeScript types | Pending |
| T-003 | C-002 | `frontend/lib/stores/situation-store.ts` — Zustand persona store | Pending |
| T-004 | C-008 | `frontend/src/fixtures/aquadrive_tenant.json` — mock data | Pending |
| T-005 | C-004 | `frontend/components/situation/MetricStrip.tsx` | Pending |
| T-006 | C-007 | `frontend/components/situation/AttackChainGraph.tsx` | Pending |
| T-007 | C-006 | `frontend/components/situation/AlertCard.tsx` | Pending |
| T-008 | C-005 | `frontend/components/situation/AlertFeed.tsx` | Pending |
| T-009 | C-003 | `frontend/components/situation/PersonaSwitcher.tsx` | Pending |
| T-010 | C-001 | `frontend/app/dashboard/situation/page.tsx` | Pending |
| T-011 | C-009 | `frontend/app/dashboard/layout.tsx` — add nav entry | Pending |
| T-012 | C-011 | `frontend/app/dashboard/chat/page.tsx` — auto-submit on `?prompt=` | Pending |

### Fixture Shape (AC-010)

All four keys must match AQL tool return shapes exactly:
- `attack_chains[]` — matches `get_attack_chain()` return: `{ cve_id, cvss3, epss, description, weaknesses[], attack_techniques[], live_detections[], affected_devices[], attack_chain_complete, spine_to_reality_hops }`
- `threat_detections[]` — matches `get_active_threat_detections()`: `{ detection_id, hostname, cve_id, technique_id, technique_name, tactic, severity, detected_at, cvss3, epss, in_kev, ... }`
- `regulatory_deadlines[]` — matches `get_regulatory_deadline_summary()`: `{ incident_id, title, cve_id, regulatory_labels, sla_deadline, hours_remaining, overdue, urgency_tier, ... }`
- `patch_priority[]` — matches `get_patch_priority()`: `{ rank, cve_id, composite_score, cvss3, epss, in_kev, active_exploits_in_env, affected_devices[], patch_urgency, ... }`

Fixture also includes `situation_metadata` for per-persona metric cards (not from AQL tools — computed at fixture-build time).

---

## Phase 2 — Live AQL Wiring (CISO view only)

| Task | Change ID | File | Status |
| --- | --- | --- | --- |
| T-013 | C-012 | Replace fixture import with real AQL calls in CISO view | Pending |

---

## Phase 3 — Simulation Schema + Write-back + Tools

| Task | Change ID | File | Status |
| --- | --- | --- | --- |
| T-014 | C-013 | `scripts/init_simulation_schema.py` | Pending |
| T-015 | C-014 | `src/complira_graph/simulation/__init__.py` | Pending |
| T-016 | C-015 | `src/complira_graph/simulation/writeback_service.py` | Pending |
| T-017 | C-016 | `src/complira_graph/queries/simulation_queries.py` | Pending |
| T-018 | C-017 | `src/api/v1/endpoints/chat.py` — 4 thin wrapper entries | Pending |

---

## Phase 4 — Simulation Visualization

| Task | Change ID | File | Status |
| --- | --- | --- | --- |
| T-019 | C-018 | `frontend/components/situation/SimulationLivePanel.tsx` | Pending |
| T-020 | C-019 | `frontend/components/situation/SimulationResultCard.tsx` | Pending |
| T-021 | C-020 | `src/api/v1/routers/simulation.py` | Pending |
| T-022 | C-021 | Register simulation router in main app | Pending |
