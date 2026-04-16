# Future-State Runtime Call Stack Review — cse-demo-realtime-simulation

## Review Meta

- Scope Classification: `Large`
- Current Round: `1`
- Current Review Type: `Deep Review`
- Clean-Review Streak Before This Round: `0`
- Clean-Review Streak After This Round: `0` (blocker found — Design Impact)
- Round State: `Reset`
- Missing-Use-Case Discovery Sweep Completed This Round: `Yes`
- New Use Cases Discovered This Round: `No`
- This Round Classification: `Design Impact`
- Required Re-Entry Path Before Next Round: `Stage 3 → Stage 4 → Stage 5`

---

## Review Basis

- Requirements: `tickets/in-progress/cse-demo-realtime-simulation/requirements.md` (status `Design-ready`)
- Runtime Call Stack Document: `tickets/in-progress/cse-demo-realtime-simulation/future-state-runtime-call-stack.md`
- Source Design Basis: `tickets/in-progress/cse-demo-realtime-simulation/proposed-design.md`
- Artifact Versions In This Round:
  - Requirements Status: `Design-ready`
  - Design Version: `v1`
  - Call Stack Version: `v1`
- Required Persisted Artifact Updates Completed For This Round: `No` (blocking finding requires Stage 3 update first)

---

## Review Intent

- Primary check: future-state call stacks are coherent, implementable, and correctly model subprocess → parent process boundary behavior.
- Design-Impact finding F-001 blocks this round. Required re-entry: update `proposed-design.md` (Stage 3), regenerate affected call stack sections (Stage 4), then return to Stage 5.

---

## Round History

| Round | Requirements Status | Design Version | Call Stack Version | Findings Requiring Persisted Updates | New Use Cases Discovered | Persisted Updates Completed | Classification | Required Re-Entry Path | Clean Streak After Round | Round State | Gate |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Design-ready | v1 | v1 | Yes | No | No | Design Impact | Stage 3 → Stage 4 → Stage 5 | 0 | Reset | No-Go |
| 2 | Design-ready | v2 | v2 | No | No | Yes | N/A | N/A | 1 | Candidate Go | Go |
| 3 | Design-ready | v2 | v2 | No | No | N/A | N/A | N/A | 2 | Go Confirmed | Go |

---

## Round Artifact Update Log

| Round | Findings Requiring Updates | Updated Files | Version Changes | Changed Sections | Resolved Finding IDs |
|---|---|---|---|---|---|
| 1 | Yes | proposed-design.md, future-state-runtime-call-stack.md | proposed-design v1→v2; call-stack v1→v2 | C-03 (compliance_gaps.json write), C-04 (report_agent reads file), UC-01, UC-02, UC-08 call stacks; apply_action signature corrections in UC-01, UC-07 | F-001, F-002 |
| 2 | No | — | — | — | — |
| 3 | No | — | — | — | — |

---

## Missing-Use-Case Discovery Log

| Round | Discovery Lens | New Use Case IDs | Source Type | Why Previously Missing | Classification | Upstream Update Required |
|---|---|---|---|---|---|---|
| 1 | Requirement coverage / boundary crossing / fallback-error / design-risk | None | — | All 12 use cases cover requirement and design-risk scenarios. No gap in requirement-to-use-case coverage. Subprocess-to-parent boundary issue is an internal design gap, not a missing use case. | N/A | No |
| 2 | Requirement coverage / boundary crossing / fallback-error / design-risk | None | — | — | N/A | No |
| 3 | Requirement coverage / boundary crossing / fallback-error / design-risk | None | — | — | N/A | No |

---

## Per-Use-Case Review — Round 1

| Use Case | Arch Fit | Layering Fitness | Boundary Placement | Existing-Structure Bias | Anti-Hack | Local-Fix Degradation | Terminology | File/API Naming | Name-to-Responsibility | Future-State Alignment | Coverage Completeness | Source Traceability | Design-Risk Justification | Business Flow | Layer SoC | Dependency Flow Smells | Redundancy | Simplification | Remove/Decommission | No Legacy | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| UC-01 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Fail (F-001, F-002) | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | Fail |
| UC-02 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Fail (F-001) | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | Fail |
| UC-03 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | Pass |
| UC-04 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | Pass |
| UC-05 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | Pass |
| UC-06 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | Pass |
| UC-07 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Fail (F-002) | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | Fail |
| UC-08 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Fail (F-001) | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | Fail |
| UC-09 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | None | Pass | Pass | N/A | Pass | Pass |
| UC-10 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | None | Pass | Pass | N/A | Pass | Pass |
| UC-11 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | None | Pass | Pass | N/A | Pass | Pass |
| UC-12 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | None | Pass | Pass | N/A | Pass | Pass |

---

## Findings — Round 1

**[F-001] Use case: UC-01, UC-02, UC-08 | Type: Architecture/Boundary | Severity: Blocker | Confidence: High**

Evidence: The proposed design (C-04) specifies `report["compliance_gaps"] = surface_server.compliance_gaps` in `report_agent.py`. However, `report_agent.generate()` is called from the **parent process** (`CyberSimulationManager.complete()` in the FastAPI background task), while `surface_server` is a Python object that only exists in the **subprocess** (`run_parallel_cyber_simulation.py`). The parent and subprocess are separate OS processes; the parent has no access to the subprocess's in-memory `surface_server.compliance_gaps` list after the subprocess exits.

Required update: Update `proposed-design.md` C-03 and C-04 to specify that:
- In `run_parallel_cyber_simulation.py` (C-03), after `asyncio.gather()` completes, serialize `surface_server.compliance_gaps` to `sim_dir / "compliance_gaps.json"`
- In `report_agent.py` (C-04), `generate(sim_dir)` reads `compliance_gaps.json` and includes it in the report dict (no `surface_server` parameter needed)
- Update call stacks for UC-01 (subprocess section), UC-02 (subprocess exit), UC-08 (Step 6 writeback chain) to reflect file-based transfer

Classification: `Design Impact`

---

**[F-002] Use case: UC-01, UC-07 | Type: Naming/Signature | Severity: Minor | Confidence: High**

Evidence: UC-01 call stack shows `attack_surface_server.py:apply_action("Regulator", action_type, params)` and UC-07 shows the same three-parameter call. The existing `apply_action()` function almost certainly takes `(action_type: str, params: dict)` — the `agent_type` is not a parameter of `apply_action()`; it is passed only to `CyberActionLogger.log_action()`. Adding `agent_type` as the first arg to `apply_action()` would change the existing signature and require updating all Attacker and Defender call sites.

Required update: Correct UC-01 and UC-07 call stacks to use `apply_action(action_type, params)` (two parameters, same as existing callers). `agent_type` is passed to `logger.log_action()` separately, as already shown in the call stack.

Classification: `Design Impact` (minor signature correction needed in C-02 spec and call stacks)

---

## Blocking Findings Summary — Round 1

- Unresolved Blocking Findings: `Yes` (F-001)
- Remove/Decommission Checks Complete: `N/A`

## Gate Decision — Round 1

- Implementation can start: `No`
- Required re-entry: `Stage 3 → Stage 4 → Stage 5` (Design Impact classification)
- Re-entry actions:
  - Update `proposed-design.md` v1 → v2: fix C-03 (add `compliance_gaps.json` write) and C-04 (report_agent reads file, no surface_server param) and C-02 spec (apply_action signature)
  - Update `future-state-runtime-call-stack.md` v1 → v2: fix UC-01, UC-02, UC-07, UC-08 call stacks
  - Return to Stage 5 Round 2

---

---

# Round 2 — After Applied Updates (v2 artifacts)

## Review Meta

- Current Round: `2`
- Current Review Type: `Deep Review`
- Clean-Review Streak Before This Round: `0`
- Clean-Review Streak After This Round: `1`
- Round State: `Candidate Go`
- Missing-Use-Case Discovery Sweep Completed This Round: `Yes`
- New Use Cases Discovered This Round: `No`
- This Round Classification: `N/A`
- Required Re-Entry Path Before Next Round: `N/A`

## Review Basis — Round 2

- Requirements: `Design-ready` (unchanged)
- Design Version: `v2` (updated: C-03 compliance_gaps.json, C-04 report reads file, C-02 apply_action signature fixed)
- Call Stack Version: `v2` (updated: UC-01, UC-02, UC-07, UC-08 corrected)
- Required Persisted Artifact Updates Completed For This Round: `Yes`

## Per-Use-Case Review — Round 2

| Use Case | Arch Fit | Layering | Boundary | Existing-Bias | Anti-Hack | Local-Fix Degrade | Terminology | Naming | Name-Responsibility | Future-State | Coverage | Traceability | Design-Risk | Business Flow | SoC | Dependency Smells | Redundancy | Simplification | Remove/Decommission | No Legacy | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| UC-01 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | Pass |
| UC-02 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | Pass |
| UC-03 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | Pass |
| UC-04 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | Pass |
| UC-05 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | Pass |
| UC-06 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | Pass |
| UC-07 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | Pass |
| UC-08 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | N/A | Pass | Pass | None | Pass | Pass | N/A | Pass | Pass |
| UC-09 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | None | Pass | Pass | N/A | Pass | Pass |
| UC-10 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | None | Pass | Pass | N/A | Pass | Pass |
| UC-11 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | None | Pass | Pass | N/A | Pass | Pass |
| UC-12 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass | None | Pass | Pass | N/A | Pass | Pass |

## Missing-Use-Case Discovery — Round 2

All 12 use cases present. No new requirement-coverage gaps, boundary-crossing gaps, fallback/error gaps, or design-risk gaps discovered. Requirement-to-use-case coverage closure: all 12 UCs in `requirements.md` have at least one mapped call stack. AC → Stage 7 scenario map remains intact. No new cases.

## Findings — Round 2

None.

## Blocking Findings Summary — Round 2

- Unresolved Blocking Findings: `No`
- Remove/Decommission Checks Complete: `N/A`

## Gate Decision — Round 2

- Implementation can start: No (need one more clean round to reach `Go Confirmed`)
- Clean-review streak: `1` (Candidate Go)

---

---

# Round 3 — Second Consecutive Clean Deep Review

## Review Meta

- Current Round: `3`
- Current Review Type: `Deep Review`
- Clean-Review Streak Before This Round: `1`
- Clean-Review Streak After This Round: `2`
- Round State: `Go Confirmed`
- Missing-Use-Case Discovery Sweep Completed This Round: `Yes`
- New Use Cases Discovered This Round: `No`
- This Round Classification: `N/A`
- Required Re-Entry Path Before Next Round: `N/A`

## Review Basis — Round 3

- Requirements: `Design-ready` (unchanged)
- Design Version: `v2` (unchanged)
- Call Stack Version: `v2` (unchanged)
- Required Persisted Artifact Updates Completed For This Round: `N/A`

## Full Gate-Criteria Checklist — Round 3

- Architecture fit is `Pass` for all 12 in-scope use cases: **Yes**
- Layering fitness is `Pass` for all 12 in-scope use cases: **Yes**
- Boundary placement is `Pass` for all 12 in-scope use cases: **Yes**
- Existing-structure bias check is `Pass` for all 12 in-scope use cases: **Yes**
- Anti-hack check is `Pass` for all 12 in-scope use cases: **Yes**
- Local-fix degradation check is `Pass` for all 12 in-scope use cases: **Yes**
- Terminology and concept vocabulary is natural/intuitive: **Yes**
- File/API naming clarity is `Pass` across all 12 use cases: **Yes**
- Name-to-responsibility alignment under scope drift is `Pass`: **Yes**
- Future-state alignment with target design basis (v2) is `Pass` for all 12 use cases: **Yes**
- Layer-appropriate SoC is `Pass` for all 12 use cases: **Yes**
- Use-case coverage completeness is `Pass` for all 12 use cases: **Yes**
- Use-case source traceability is `Pass` for all 12 use cases: **Yes**
- Requirement coverage closure is `Pass` (all requirements map to ≥ 1 use case): **Yes**
- Design-risk justification quality is `Pass` for all 4 design-risk use cases (UC-09, UC-10, UC-11, UC-12): **Yes**
- Redundancy/duplication check is `Pass`: **Yes**
- Simplification opportunity check is `Pass`: **Yes**
- All 12 use-case verdicts are `Pass`: **Yes**
- No unresolved blocking findings: **Yes**
- Required persisted artifact updates completed (Round 1 findings resolved in v2 artifacts): **Yes**
- Missing-use-case discovery sweep completed this round: **Yes**
- No newly discovered use cases this round: **Yes**
- Remove/decommission checks complete for scoped changes: `N/A` (no Remove items)
- Two consecutive clean deep-review rounds (Rounds 2 and 3): **Yes**
- Findings trend: declining (1 blocker Round 1 → 0 Round 2 → 0 Round 3): **Yes**

## Gate Decision — Round 3

- Implementation can start: **Yes**
- Clean-review streak: `2`
- Round State: **Go Confirmed**

---

## Speak Log

- Stage 5 entry spoken after workflow-state.md update: Speak tool unavailable — text fallback provided
- Gate decision (Go Confirmed) spoken after persisted gate evidence: Speak tool unavailable — text fallback: "Stage 5 complete — Go Confirmed after 3 rounds. Advancing to Stage 6. Code Edit Permission will be Unlocked."
