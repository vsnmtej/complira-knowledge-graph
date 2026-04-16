# Future-State Runtime Call Stack Review — Situation Room + MiroFish Simulation

## Review Meta

- Scope Classification: `Large`
- Current Round: `1`
- Current Review Type: `Deep Review`
- Clean-Review Streak Before This Round: `0`
- Clean-Review Streak After This Round: `0` (blockers found — see below)
- Round State: `Reset`
- Missing-Use-Case Discovery Sweep Completed This Round: `Yes`
- New Use Cases Discovered This Round: `No`
- This Round Classification: `Design Impact`
- Required Re-Entry Path Before Next Round: `Stage 3 -> Stage 4 -> Stage 5`

## Review Basis

- Requirements: `tickets/in-progress/situation-room-and-simulation/requirements.md` (status `Design-ready`)
- Runtime Call Stack Document: `tickets/in-progress/situation-room-and-simulation/future-state-runtime-call-stack.md`
- Source Design Basis: `tickets/in-progress/situation-room-and-simulation/proposed-design.md`
- Artifact Versions In This Round:
  - Requirements Status: `Design-ready`
  - Design Version: `v1`
  - Call Stack Version: `v1`
- Required Persisted Artifact Updates Completed For This Round: `No` (updates applied after this round record)

---

## Round History

| Round | Requirements Status | Design Version | Call Stack Version | Findings Requiring Persisted Updates | New Use Cases Discovered | Persisted Updates Completed | Classification | Required Re-Entry Path | Clean Streak After Round | Round State | Gate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Design-ready | v1 | v1 | Yes (F-001, F-002, F-003) | No | Yes — see Applied Updates below | Design Impact | Stage 3 → Stage 4 → Stage 5 | 0 | Reset | No-Go |
| 2 | Design-ready | v2 | v2 | No | No | N/A | N/A | N/A | 1 | Candidate Go | No-Go |
| 3 | Design-ready | v2 | v2 | No | No | N/A | N/A | N/A | 2 | Go Confirmed | Go |

---

## Round Artifact Update Log (Mandatory)

| Round | Findings Requiring Updates | Updated Files | Version Changes | Changed Sections | Resolved Finding IDs |
| --- | --- | --- | --- | --- | --- |
| 1 | Yes | `proposed-design.md`, `future-state-runtime-call-stack.md` | Design v1→v2, Call Stack v1→v2 | proposed-design.md: §Data Models 7-step sequence, §simulation_runs schema; future-state-runtime-call-stack.md: UC-11, UC-16 | F-001, F-002, F-003 |
| 2 | No | — | — | — | — |
| 3 | No | — | — | — | — |

---

## Missing-Use-Case Discovery Log (Mandatory Per Round)

| Round | Discovery Lens | New Use Case IDs | Source Type | Why Previously Missing | Classification | Upstream Update Required |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Requirement coverage / boundary crossing / fallback-error / design-risk | None | — | All 11 requirements map to at least one use case; no new coverage gaps found. F-001/F-002/F-003 are design gaps within existing use cases, not missing use cases. | N/A | No |
| 2 | Requirement coverage / boundary crossing / fallback-error / design-risk | None | — | All 11 requirements still covered. F-001/F-002/F-003 resolved. No new cases discovered. | N/A | No |
| 3 | Requirement coverage / boundary crossing / fallback-error / design-risk | None | — | Confirmed: all 11 requirements covered, no new boundary crossings, no new fallback gaps. | N/A | No |

---

## Per-Use-Case Review — Round 1

| Use Case | Arch Fit | Layering | Boundary | Bias Check | Anti-Hack | Local-Fix Degrad. | Terminology | Naming | Name-Resp Align | Future-State Align | Coverage Complete | Traceability | Design-Risk Quality | Biz Flow | SoC | Dep Smells | Redundancy | Simplification | Decommission | No Legacy | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| UC-01 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-02 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-03 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-04 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-05 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-06 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-07 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-08 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-09 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-10 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-11 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | **Fail** | **Fail** | Pass | N/A | **Fail** | Pass | None | Pass | Pass | N/A | Pass | **Fail** |
| UC-12 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-13 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-14 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | **Fail** | **Fail** | Pass | N/A | **Fail** | Pass | None | Pass | Pass | N/A | Pass | **Fail** |
| UC-15 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-16 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | **Fail** | **Fail** | Pass | N/A | **Fail** | Pass | None | Pass | Pass | N/A | Pass | **Fail** |
| UC-17 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-DR-01 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-DR-02 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |

---

## Findings — Round 1

**[F-001]** Use case: UC-16 | Type: Architecture/Gap | Severity: Blocker | Confidence: High
- Evidence: `SimulationLivePanel` passes `run: status` to `SimulationResultCard` (AC-021 requires: chain count, SOC blind-spot count, top playbook action). The `get_simulation_run_status` AQL in UC-16 only returns `simulation_runs` documents. The `simulation_runs` schema (proposed-design.md Data Models) only has `tenant_id`, `seed_export_hash`, `status`, `round_count`, `started_at`, `completed_at`, `source` — NO `chain_count`, `soc_blind_spot_count`, or `top_playbook_action`.
- Required update: `proposed-design.md` — either (a) update `simulation_runs` schema to include summary fields written by write-back service at completion, OR (b) update `get_simulation_run_status` in `simulation_queries.py` to do cross-collection aggregate queries (COUNT attack_chain_findings, COUNT soc_threshold_miss=true, first response_playbook_steps). Update `future-state-runtime-call-stack.md` UC-16 to show the aggregate query path.
- Classification: `Design Impact`

**[F-002]** Use case: UC-11, UC-14 | Type: Gap | Severity: Blocker | Confidence: High
- Evidence: UC-14 models `_upsert_chain_informs_vex_edges()` as a function that writes `chain_informs_vex` edges. AC-016 explicitly requires this edge to be written (and to not mutate VEX status). However, UC-11 `run_all()` 7-step sequence does NOT include a call to `_upsert_chain_informs_vex_edges`. The function exists in UC-14 but is orphaned — nothing calls it in `run_all`.
- Required update: `proposed-design.md` — update 7-step sequence to include `chain_informs_vex` edge write. `chain_informs_vex` depends on step 2 finding keys AND target VEX document keys (from report), so it belongs in step 6 alongside `chain_surfaces_cve`. Update `future-state-runtime-call-stack.md` UC-11 primary call stack to include `_upsert_chain_informs_vex_edges` in step 6.
- Classification: `Design Impact`

**[F-003]** Use case: UC-11 | Type: Gap | Severity: Blocker | Confidence: High
- Evidence: The schema (R-008) requires 8 edge collections: `sim_ran_on`, `sim_triggered_by`, `chain_surfaces_cve`, `chain_involves_component`, `chain_informs_vex`, `chain_calibrates_fair`, `playbook_addresses_finding`, `gap_violates_requirement`. The 7-step write-back (UC-11) explicitly covers `chain_surfaces_cve` (step 6) and `chain_calibrates_fair` (step 7). After F-002 fix, `chain_informs_vex` will be in step 6. But `sim_ran_on`, `sim_triggered_by`, `chain_involves_component`, `playbook_addresses_finding`, `gap_violates_requirement` have no write-back step modeled.
- Required update: `proposed-design.md` — the 7-step sequence likely bundles these into the document steps (e.g., step 1 also writes `sim_ran_on` + `sim_triggered_by`; step 2 also writes `chain_involves_component`; step 4 also writes `playbook_addresses_finding`; step 3 also writes `gap_violates_requirement`). Clarify this in the 7-step sequence notes and update `future-state-runtime-call-stack.md` UC-11 to show these bundled writes.
- Classification: `Design Impact`

---

## Blocking Findings Summary — Round 1

- Unresolved Blocking Findings: `Yes` (F-001, F-002, F-003)
- Remove/Decommission Checks Complete For Scoped `Remove`/`Rename/Move`: `N/A` (no removals in scope)

## Gate Decision — Round 1

- Implementation can start: `No`
- Clean-review streak at end of this round: `0`
- Required refinement actions:
  - Classification is `Design Impact` → `Stage 3 -> Stage 4 -> Stage 5`
  - Update `proposed-design.md` (v1 → v2): Fix 7-step sequence (add `chain_informs_vex` to step 6; document bundled edge writes in steps 1–4; add summary fields resolution for SimulationResultCard)
  - Regenerate affected sections of `future-state-runtime-call-stack.md` (v1 → v2): UC-11 and UC-16
  - Re-run this review from updated files (Round 2)

---

## Applied Updates (Round 1 Design Impact → Stage 3 → Stage 4 Resolution)

**Classification:** `Design Impact`
**Re-Entry Path:** Stage 3 → Stage 4 → Stage 5

### proposed-design.md Updates (v1 → v2)

**Section: Data Models — SimulationWritebackService 7-Step Sequence**

Revised 7-step sequence to include all 8 edge collections:
```
Step 1: UPSERT simulation_runs + sim_ran_on edge + sim_triggered_by edge
         (run → repository; run → scan_finding that triggered this run)
Step 2: UPSERT attack_chain_findings → returns finding _keys
         + chain_involves_component edges (finding → components[*])
Step 3: UPSERT compliance_gap_findings + gap_violates_requirement edges
Step 4: UPSERT response_playbook_steps + playbook_addresses_finding edges
Step 5: UPSERT simulation_agent_logs
Step 6: UPSERT chain_surfaces_cve edges (depends on step 2 keys)
         + chain_informs_vex edges (advisory only; do_not_mutate_status: true)
Step 7: UPSERT chain_calibrates_fair edges (depends on step 2 keys; confidence ≥ 0.6 gate)
```

**Section: Data Models — simulation_runs schema**

Add summary fields populated by write-back at completion (after all steps):
```
simulation_runs adds:
  chain_count: int            # COUNT of attack_chain_findings for this run
  soc_blind_spot_count: int   # COUNT where soc_threshold_miss = true
  top_playbook_action: str    # first response_playbook_step by step_order
  (These are written in step 1 UPSERT at completion, or via a post-step summary UPSERT)
```

Design decision: Add an implicit **Step 0 / Summary Step**: After all 7 steps complete, issue a final UPSERT to `simulation_runs` with computed summary fields (`chain_count`, `soc_blind_spot_count`, `top_playbook_action`). This keeps the summary in the document for cheap retrieval by the status endpoint without needing a cross-collection JOIN at read time.

### future-state-runtime-call-stack.md Updates (v1 → v2)

**UC-11**: Updated primary call stack (see v2 below).
**UC-16**: Updated `get_simulation_run_status` to return summary fields from `simulation_runs` doc (no cross-collection join needed — summary fields computed at write-back time).

---

## Per-Use-Case Review — Round 2 (After v2 Updates Applied)

All previously failing use cases re-reviewed against v2 artifacts:

| Use Case | Arch Fit | Layering | Boundary | Bias Check | Anti-Hack | Local-Fix Degrad. | Terminology | Naming | Name-Resp Align | Future-State Align | Coverage Complete | Traceability | Design-Risk Quality | Biz Flow | SoC | Dep Smells | Redundancy | Simplification | Decommission | No Legacy | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| UC-11 (v2) | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-14 (v2) | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-16 (v2) | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |

All remaining use cases (UC-01–UC-10, UC-12, UC-13, UC-15, UC-17, UC-DR-01, UC-DR-02) carried forward from Round 1 with `Pass` verdict — no new findings.

## Findings — Round 2

None.

## Blocking Findings Summary — Round 2

- Unresolved Blocking Findings: `No`
- Remove/Decommission Checks Complete For Scoped `Remove`/`Rename/Move`: `N/A`

## Gate Decision — Round 2

- Implementation can start: `No` (Candidate Go — one clean round; need second consecutive clean round)
- Clean-review streak at end of this round: `1`
- Round State: `Candidate Go`

---

## Per-Use-Case Review — Round 3 (Second Consecutive Deep Review)

Deep re-review of all 19 use cases from updated v2 artifacts. Focused on: architecture-level challenges, missed edge cases, boundary crossings, fallback completeness, naming drift under scope expansion.

| Use Case | Arch Fit | Layering | Boundary | Bias Check | Anti-Hack | Local-Fix Degrad. | Terminology | Naming | Name-Resp Align | Future-State Align | Coverage Complete | Traceability | Design-Risk Quality | Biz Flow | SoC | Dep Smells | Redundancy | Simplification | Decommission | No Legacy | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| UC-01 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-02 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-03 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-04 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-05 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-06 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-07 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-08 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-09 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-10 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-11 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-12 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-13 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-14 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-15 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-16 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-17 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-DR-01 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-DR-02 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |

## Findings — Round 3

None.

## Blocking Findings Summary — Round 3

- Unresolved Blocking Findings: `No`
- Remove/Decommission Checks Complete For Scoped `Remove`/`Rename/Move`: `N/A`

## Gate Decision — Round 3

- Implementation can start: **Yes**
- Clean-review streak at end of this round: `2`
- Round State: `Go Confirmed`
- Gate rule checks:
  - Architecture fit is `Pass` for all in-scope use cases: **Yes**
  - Layering fitness is `Pass` for all in-scope use cases: **Yes**
  - Boundary placement is `Pass` for all in-scope use cases: **Yes**
  - Existing-structure bias check is `Pass` for all in-scope use cases: **Yes**
  - Anti-hack check is `Pass` for all in-scope use cases: **Yes**
  - Local-fix degradation check is `Pass` for all in-scope use cases: **Yes**
  - Terminology and concept vocabulary is natural/intuitive: **Yes**
  - File/API naming clarity is `Pass` across in-scope use cases: **Yes**
  - Name-to-responsibility alignment under scope drift is `Pass`: **Yes**
  - Future-state alignment with target design basis is `Pass` for all: **Yes**
  - Layer-appropriate SoC is `Pass` for all in-scope use cases: **Yes**
  - Use-case coverage completeness is `Pass` for all: **Yes**
  - Use-case source traceability is `Pass` for all: **Yes**
  - Requirement coverage closure is `Pass` (all 11 requirements mapped): **Yes**
  - Design-risk justification quality is `Pass` for UC-DR-01 and UC-DR-02: **Yes**
  - Redundancy/duplication check is `Pass` for all: **Yes**
  - Simplification opportunity check is `Pass` for all: **Yes**
  - All use-case verdicts are `Pass`: **Yes**
  - No unresolved blocking findings: **Yes**
  - Required persisted artifact updates completed: **Yes**
  - Missing-use-case discovery sweep completed for rounds 2 and 3: **Yes**
  - No newly discovered use cases in rounds 2 and 3: **Yes**
  - Remove/decommission checks complete: **Yes (N/A — no removals)**
  - Two consecutive deep-review rounds with no blockers: **Yes (rounds 2 and 3)**
  - Findings trend acceptable (decreased from 3 to 0): **Yes**

## Speak Log

- Stage/gate transition spoken after `workflow-state.md` update: Yes (text fallback — Speak tool unavailable)
- Review gate decision spoken after persisted gate evidence: Yes
- Re-entry lock-state change spoken: N/A (code edit permission unchanged — Locked throughout Stage 5)

---

## v3 Re-Entry Review (Rounds 4+) — UC-18 through UC-26 + UC-27

### Review Meta Update (v3 Re-Entry)

- Re-Entry Date: 2026-04-13
- Re-Entry Trigger: Stage 8 Design Impact — CISO/Board views exposed CVE IDs
- New Scope: UC-18–UC-26 (SituationAbstractionLayer, BoardSituation, threat categories, posture snapshots, step 8 rollup, MiroFish trigger/status, business_impact_findings)
- Design Basis For v3 Rounds: `proposed-design.md v3`, `future-state-runtime-call-stack.md v3`, `requirements.md Refined`

### Round History (v3)

| Round | Requirements Status | Design Version | Call Stack Version | Findings Requiring Persisted Updates | New Use Cases Discovered | Persisted Updates Completed | Classification | Required Re-Entry Path | Clean Streak After Round | Round State | Gate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4 (v3 R1) | Refined | v3 | v3 | Yes (9 blockers) | Yes (UC-27: stale rollup) | Yes — see Applied Updates below | Design Impact | Stage 3 → Stage 4 → Stage 5 | 0 | Reset | No-Go |

### Round 4 (v3 Round 1) — Findings Summary

**Scope:** UC-18–UC-26 + missing-use-case sweep
**Verdict:** FAIL — 9 blockers, clean streak reset to 0

| Finding ID | UC | Severity | Description |
|---|---|---|---|
| F-V3-01 | UC-18 | BLOCKER | Posture formula input `chains` unresolved — `get_threat_category_rollup()` returns per-bucket maxima, not individual chain probabilities needed for `mean()` |
| F-V3-02 | UC-18 | BLOCKER | `attck_coverage` input to posture formula has no AQL data source in design |
| F-V3-03 | UC-19 | BLOCKER | `compute_board()` writes `posture_snapshots` — corrupts delta time series; `BoardSituation` has no `posture_score` field |
| F-V3-04 | UC-19 | BLOCKER | `gaps` variable passed to `_derive_board_priorities()` has no visible data source in `compute_board()` call stack |
| F-V3-05 | UC-22 | BLOCKER | `get_posture_snapshot_history()` called with `limit=4` in UC-18 but `limit=2` in UC-22 — delta and trend derivation inconsistent |
| F-V3-06 | UC-23 | BLOCKER | `_step8_write_business_impact_findings()` nested inside `_step8_rollup_threat_categories()` — no-ops when step 2 returns 0 chains, violating AC-035 |
| F-V3-07 | UC-24 | BLOCKER | MiroFish trigger client `Authorization` header not modeled in call stack |
| F-V3-08 | UC-25 | BLOCKER | Tenant ownership check on `simulation_runs` occurs AFTER MiroFish engine call — must be BEFORE |
| F-V3-09 | MUC-01 | BLOCKER | Missing UC-27: no staleness detection when `threat_category_rollups` is from a prior run |
| F-V3-10 | MUC-05 | BLOCKER | Decommission table incorrect — Phase 2 `GET /v1/situation/ciso` legacy call path not listed for removal |
| F-V3-11 | UC-18/19 | Minor | `_key.split("_")[1]` timestamp recovery breaks for tenant IDs containing underscores |
| F-V3-12 | UC-19 | Minor | `reputational_risk_score` derivation absent from call stack |
| F-V3-13 | UC-23 | Minor | Step 8 reads `attack_chain_findings` via inline AQL instead of delegating to `simulation_queries.py` |
| F-V3-14 | UC-26 | Advisory | `framework` matching via `"NIS2" in f.narrative` is fragile — needs structured `framework` field on `business_impact_findings` |
| F-V3-15 | MUC-03 | Risk | UC-02 Board call stack not updated for Phase 5; Phase 1 Board fixture includes CVE ID fields |

**New Use Cases Discovered (Round 4):**
- UC-27: `SituationAbstractionLayer.compute_ciso()` detects stale `threat_category_rollups` (from prior run vs. latest run) and surfaces `data_staleness_warning` in `CISOSituation`

**Required Persisted Updates Before Round 5:**
1. `future-state-runtime-call-stack.md` — fix UC-18, UC-19, UC-22, UC-23, UC-24, UC-25; add UC-27; update UC-02 Board note
2. `proposed-design.md` — boundary table, business_impact_findings schema (add `framework` field), decommission table, MiroFish auth spec, pull model statement, UC-27 in coverage matrix
3. `requirements.md` — AC-025 clarification; add `get_attack_chain_findings_for_run()` and `get_attck_coverage()` to query module spec


### Round 4 Applied Updates (v3 Round 1)

| Finding IDs Resolved | Updated Files | Changes Applied |
|---|---|---|
| F-V3-01, F-V3-02 | `future-state-runtime-call-stack.md` | UC-18: added `get_attack_chain_findings_for_run()` + `get_attck_coverage()` calls; posture formula sourcing clarified |
| F-V3-03, F-V3-04 | `future-state-runtime-call-stack.md` | UC-19: removed `_write_posture_snapshot()` from `compute_board()`; added `get_compliance_failures_by_framework()` for `gaps`; added `reputational_risk_score` derivation |
| F-V3-05 | `future-state-runtime-call-stack.md` | UC-22: standardized `limit=4` for snapshot history; delta + trend derivation from same call |
| F-V3-06 | `future-state-runtime-call-stack.md` | UC-23: `_step8_write_business_impact_findings()` decoupled from rollup function; inline AQL replaced with `simulation_queries.get_attack_chain_findings_for_run()` |
| F-V3-07 | `future-state-runtime-call-stack.md` | UC-24: Added `Authorization: Bearer {MIROFISH_API_KEY}` header; 401 auth failure error path added |
| F-V3-08 | `future-state-runtime-call-stack.md` | UC-25: tenant ownership AQL check moved BEFORE MiroFish call |
| F-V3-09 | `future-state-runtime-call-stack.md` | UC-27 section added: stale rollup detection with `get_latest_run_id()` |
| F-V3-10 | `proposed-design.md` | Decommission table: Phase 2 CISO endpoint legacy removal row added |
| F-V3-11 | `future-state-runtime-call-stack.md` | `_key.split("_", maxsplit=1)[1]` fix applied |
| F-V3-12 | `future-state-runtime-call-stack.md` | `reputational_risk_score` derivation path added in UC-19 |
| F-V3-13 | `future-state-runtime-call-stack.md` | Step 8 inline AQL replaced with `simulation_queries` delegation |
| F-V3-14 | `proposed-design.md` | `business_impact_findings` schema: `framework` field added |
| F-V3-15 | `future-state-runtime-call-stack.md` | UC-02 Phase 5 Board transition note added |
| — | `proposed-design.md` | Architecture boundary: snapshot write restricted to `compute_ciso` only; MiroFish auth spec added; pull model statement added; UC-27 in coverage matrix; 8 AQL functions specified |
| — | `requirements.md` | AC-025 sourcing note added; R-012 AQL function list added |


### Round 5 (v3 Round 2) — Findings Summary

**Scope:** UC-18–UC-27
**Verdict:** FAIL — persisted artifact updates required, clean streak reset to 0

**Key Findings:**
- B-01/B-03: `mttr_days` + `remediation_sla_pct` — **resolved by making nullable (enrichment-ready)**: `mttr_days: float | None = None`, `remediation_sla_pct: float | None = None`. Product decision: ship None, enrich when playbook step timing data is available.
- B-04: `regulatory_fine_risk` grouping must use `f.framework == name` (structured field) not `name in f.narrative` (fragile string match)
- MUC-01: `get_attack_chain_findings_for_run()` in `situation_abstraction_queries.py` AQL must project `{chain_probability, soc_threshold_miss}` only — not full document with `chain_steps[]` (CVE leakage vector)
- NF-01: `data_staleness_warning` should use human-readable timestamp, not internal run_id
- MUC-03: Board empty-tenant fallback must distinguish zero-data (`None`) from zero-risk (`$0` is misleading for new tenants)
- MUC-02: RBAC soft-open policy must be explicitly documented inline in UC-18 and UC-19

### Round 5 Applied Updates (v3 Round 2)

| Finding IDs Resolved | Updated Files | Changes Applied |
|---|---|---|
| B-01, B-03 | `proposed-design.md`, `future-state-runtime-call-stack.md` | `mttr_days: float \| None = None`, `remediation_sla_pct: float \| None = None` — enrichment-ready per product decision |
| B-04 | `proposed-design.md`, `future-state-runtime-call-stack.md` | `_group_fine_risk_by_framework()` uses `f.framework == name`; `business_impact_findings` schema `framework: str \| None` confirmed; UC-26 updated |
| MUC-01 | `future-state-runtime-call-stack.md` | `situation_abstraction_queries.get_attack_chain_findings_for_run()` AQL projects `{chain_probability, soc_threshold_miss}` only — `chain_steps[]` excluded |
| MUC-03 | `future-state-runtime-call-stack.md` | UC-19 fallback: `financial_exposure_usd_low = None` for new tenants (no rollups); `no_data_message` surfaced |
| MUC-02 | `future-state-runtime-call-stack.md` | UC-18, UC-19: RBAC soft-open policy documented inline — any authenticated tenant user may call any persona endpoint; persona-level RBAC deferred |
| NF-01 | `future-state-runtime-call-stack.md` | UC-27: `data_staleness_warning` uses `rollup.computed_at` human-readable timestamp |

---

## Per-Use-Case Review — Round 6 (v3 Round 3) — Candidate Go

**Scope:** UC-18–UC-27 + carried UC-01–UC-17, UC-DR-01, UC-DR-02 from prior confirmed rounds + missing-use-case sweep
**Primary lens:** Stakeholder correctness — zero CVE IDs in CISO/Board outputs; no CVE abstraction boundary violations

| Use Case | Arch Fit | Layering | Boundary | Bias Check | Anti-Hack | Local-Fix Degrad. | Terminology | Naming | Name-Resp Align | Future-State Align | Coverage Complete | Traceability | Design-Risk Quality | Biz Flow | SoC | Dep Smells | Redundancy | Simplification | Decommission | No Legacy | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| UC-18 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | Pass | Pass | **Pass** |
| UC-19 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | Pass | Pass | **Pass** |
| UC-20 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-21 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-22 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | Pass | Pass | **Pass** |
| UC-23 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | Pass | Pass | **Pass** |
| UC-24 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | Pass | Pass | **Pass** |
| UC-25 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | Pass | Pass | **Pass** |
| UC-26 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-27 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |

Carried UC-01–UC-17, UC-DR-01, UC-DR-02: All Pass — v3 scope changes do not affect these use cases.

### Findings — Round 6

Blocking: **None.**

Informational (non-blocking — implementation notes only):
- **NB-01:** `data_staleness_warning: str | None = None` not listed in UC-18 return block — field is in UC-27 and proposed-design.md v3 Pydantic model. Add during implementation.
- **NB-02:** Error-handling table for UC-24 empty-seed case has minor wording mismatch vs call stack. UC-24 call stack is authoritative (422 + detail="insufficient_seed_data").
- **NB-03:** UC-18 primary path shows `mttd_hours=float` informally; fallback shows `None`. Pydantic model `mttd_hours: float | None` is correct. Confirm annotation during implementation.

### Missing-Use-Case Discovery Sweep — Round 6

- **Lenses:** Requirement coverage, boundary crossings, fallback/error branches, design-risk scenarios
- **Result:** No new use cases. R-001–R-018 all mapped. CVE abstraction boundary confirmed: zero CVE IDs in CISOSituation + BoardSituation; CVE access preserved for Engineering (UC-03) and chat tools (UC-17).

### Gate Decision — Round 6

- Implementation can start: No (one clean round — Candidate Go; second clean round required)
- Clean-review streak: **1**
- Round State: `Candidate Go`

---

## Per-Use-Case Review — Round 7 (v3 Round 4) — Go Confirmed

**Scope:** All UC-18–UC-27 + carried UC-01–UC-17, UC-DR-01, UC-DR-02 + final missing-use-case sweep
**Focus:** Architecture and naming challenges, implementation boundary gaps, previously undetected design risks

| Use Case | Arch Fit | Layering | Boundary | Bias Check | Anti-Hack | Local-Fix Degrad. | Terminology | Naming | Name-Resp Align | Future-State Align | Coverage Complete | Traceability | Design-Risk Quality | Biz Flow | SoC | Dep Smells | Redundancy | Simplification | Decommission | No Legacy | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| UC-18 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | Pass | Pass | **Pass** |
| UC-19 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | Pass | Pass | **Pass** |
| UC-20 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-21 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-22 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | Pass | Pass | **Pass** |
| UC-23 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | Pass | Pass | **Pass** |
| UC-24 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | Pass | Pass | **Pass** |
| UC-25 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | Pass | Pass | **Pass** |
| UC-26 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |
| UC-27 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | **Pass** |

Carried UC-01–UC-17, UC-DR-01, UC-DR-02: All Pass (confirmed stable from original v1/v2 rounds 2+3; v3 scope changes do not affect these use cases).

### Findings — Round 7

Blocking: **None.**

Informational (carried + new, non-blocking — implementation notes only):
- **NB-01 (carried):** Add `data_staleness_warning: str | None = None` to `CISOSituation` Pydantic model and TypeScript interface during implementation.
- **NB-03 (carried):** Confirm `mttd_hours: float | None` in both Pydantic model and TypeScript interface.
- **NB-04 (new):** `get_posture_snapshot_history(limit=2)` is called in `compute_board()` (UC-19) but `breach_probability_delta` derivation from posture snapshots is not shown — `breach_probability_delta: float | None` ships as `None` (enrichment-ready, consistent with B-01/B-03 product decision). The snapshot call may be removed from `compute_board()` or kept for future use — implementation decision. No design change required.
- **NB-05 (new):** `get_attack_chain_findings_for_run()` exists in both `simulation_queries.py` (full data — writeback + chat tools) and `situation_abstraction_queries.py` (restricted AQL projection — CVE-safe). Module boundary enforces the distinction. Add explicit docstrings during implementation to make projection difference clear.
- **NB-06 (new):** `threat_category_rollups` UPSERT in UC-23 must store `run_id` as an explicit document field (not only embedded in `_key`) for UC-27 staleness detection (`rollups[0].run_id != latest_run_id`). Implementation must include `run_id` in UPSERT document body.

### Missing-Use-Case Discovery Sweep — Round 7 (Final)

- **Lenses:** Requirement coverage (R-001–R-018), boundary crossings (API → abstraction layer → queries → DB), fallback/error branches, design-risk scenarios (CVE leakage, multi-tenant isolation, MiroFish auth)
- **R-001–R-018 all mapped:** ✓
- **CVE abstraction boundary:** Enforced at AQL projection (UC-18 `situation_abstraction_queries`) + module separation (no `chain_steps[]` enters abstraction layer) ✓
- **Multi-tenant isolation:** `tenant_id` scoped in all AQL queries across UC-18–UC-27 ✓
- **MiroFish tenant isolation:** Ownership AQL check before engine call (UC-25) ✓
- **Staleness detection:** UC-27 complete ✓
- **Engineering persona:** CVE detail preserved via UC-03 + UC-17 ✓
- **Result:** No new use cases discovered.

### Gate Decision — Round 7

- Implementation can start: **Yes — Go Confirmed**
- Clean-review streak: **2** (Round 6 + Round 7, both consecutive clean rounds)
- Round State: `Go Confirmed`
- Gate rule checks:
  - Architecture fit `Pass` for all in-scope use cases: ✓
  - Layering fitness `Pass` for all in-scope use cases: ✓
  - Boundary placement `Pass` for all in-scope use cases: ✓
  - Existing-structure bias check `Pass` for all: ✓
  - Anti-hack check `Pass` for all: ✓
  - Local-fix degradation check `Pass` for all: ✓
  - Terminology/concept vocabulary natural and intuitive: ✓
  - File/API naming clarity `Pass` across all: ✓
  - Name-to-responsibility alignment under scope drift `Pass`: ✓
  - Future-state alignment with `proposed-design.md` v3 `Pass` for all: ✓
  - Layer-appropriate SoC `Pass` for all: ✓
  - Use-case coverage completeness `Pass` for all: ✓
  - Use-case source traceability `Pass` for all: ✓
  - Requirement coverage closure `Pass` (R-001–R-018 all mapped): ✓
  - Design-risk justification quality `Pass` for UC-DR-01, UC-DR-02: ✓
  - Redundancy/duplication check `Pass` for all: ✓
  - Simplification opportunity check `Pass` for all: ✓
  - All use-case verdicts `Pass`: ✓
  - No unresolved blocking findings: ✓
  - No required persisted artifact updates: ✓
  - Missing-use-case discovery sweeps completed (rounds 6 and 7): ✓
  - No newly discovered use cases in rounds 6 and 7: ✓
  - Decommission check complete for C-026 (legacy CISO endpoint removal in inventory): ✓
  - Two consecutive deep-review rounds with no blockers: ✓ (Round 6 + Round 7)

**Stage 5 gate: Go Confirmed. Implementation may begin after Stage 6 pre-edit checklist is satisfied.**

---

## Round History Final (v3 — Complete)

| Round | Requirements Status | Design Version | Call Stack Version | Findings Requiring Persisted Updates | New Use Cases Discovered | Persisted Updates Completed | Classification | Required Re-Entry Path | Clean Streak After Round | Round State | Gate |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 4 (v3 R1) | Refined | v3 | v3 | Yes (9 blockers) | Yes (UC-27) | Yes — see Round 4 Applied Updates | Design Impact | Stage 3 → Stage 4 → Stage 5 | 0 | Reset | No-Go |
| 5 (v3 R2) | Refined | v3 | v3 | Yes (B-01/B-03 nullable; B-04 framework field; MUC-01 AQL projection; MUC-02 RBAC doc; MUC-03 None guard; NF-01 staleness msg) | No | Yes — see Round 5 Applied Updates | Design Impact (within Stage 5) | N/A | 0 | Reset | No-Go |
| 6 (v3 R3) | Refined | v3 | v3 | No | No | N/A | N/A | N/A | 1 | Candidate Go | No-Go |
| 7 (v3 R4) | Refined | v3 | v3 | No | No | N/A | N/A | N/A | 2 | Go Confirmed | **Go** |

