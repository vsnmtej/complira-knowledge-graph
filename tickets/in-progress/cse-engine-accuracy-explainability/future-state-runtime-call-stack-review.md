# Runtime Call Stack Review — cse-engine-accuracy-explainability

**Review Round:** 1  
**Reviewer:** Claude Sonnet 4.6  
**Date:** 2026-04-16  
**Artifact Reviewed:** `future-state-runtime-call-stack.md` v1  
**Against:** `proposed-design.md` v1, actual source files  

---

## Review Method

Each UC reviewed against:
1. Current source code (actual function signatures, class fields, interfaces)
2. Internal consistency with other UCs in this ticket
3. Downstream consumers (writeback, situation room, frontend)
4. Concurrency model (subprocess vs. main process boundary)

---

## Findings

---

### F-001 — Design Impact (Medium)
**UC:** UC-01, UC-06  
**Issue:** `TechniqueResolver` is called during `prepare()` with a `db` reference, then technique data is stored in `simulation_config.json`. In UC-06, `_flush_all_agent_logs_to_arango()` reads `technique_id` and `technique_source` from JSONL entries. But the subprocess (which writes JSONL) only has `entity_techniques` from the config — it doesn't have the resolver. The call stack shows the attacker subprocess reading `config["entity_techniques"]` to pick a technique, but UC-01 doesn't show this subprocess read path.

**Required correction:** UC-01 call stack must explicitly show the subprocess read path:
```
[SUBPROCESS] run_attacker_loop()
└── entity_techniques = config.get("entity_techniques", {})
└── technique = random.choice(entity_techniques.get(cve_id, ["T1190"]))
└── payload["technique"] = technique
└── payload["technique_source"] = "graph" if graph_resolved else "fallback"
```
This must be added to `_parse_action_response()` in `attacker_simulation.py` (C-01).

**Classification:** Design Impact — UC-01 call stack update needed  
**Action:** Update UC-01 to show subprocess consume path; update C-01 change item scope.

---

### F-002 — Design Impact (High)
**UC:** UC-03  
**Issue:** `_compute_exploit_probability()` references `self.controls_deployed` as a flat list, but the current `AttackSurfaceServer` has `controls_deployed: list[str]` containing control *descriptions* (e.g. "deployed EDR on pump-api-prod-01"), not CVE-specific controls. The modifier `-0.30 if controls_deployed` applies the same penalty regardless of whether any control is relevant to the specific CVE being exploited.

**Required correction:** Either:
- (a) Add `controls_per_cve: dict[str, list[str]]` to track which controls apply to which CVE, OR
- (b) Keep the flat list but change the modifier logic to: "any control deployed → -0.10 general deterrent; CVE-specific control → additional -0.20"

Option (b) is simpler and doesn't require a schema change. Proposed-design.md AD-02 says "pure Python, no DB calls" — option (b) is consistent.

**Classification:** Design Impact — probability modifier logic needs clarification  
**Action:** Update UC-03 and proposed-design.md to use option (b) modifier logic.

---

### F-003 — Logic Error (High)
**UC:** UC-04  
**Issue:** The state machine shows `SCAN_SURFACE success → phase = EXPLOITATION`. But `_action_scan_surface()` in `attack_surface_server.py` always succeeds (no failure path). This means the attacker moves out of RECON after exactly 1 round. With `total_rounds=720`, the attacker is in EXPLOITATION phase from round 2 onward, spending 718 rounds purely exploiting. This doesn't achieve the intended diversity.

**Required correction:** Gate RECON→EXPLOITATION transition on `round_no >= 2` AND the scan having returned at least 1 exploitable CVE, not just on action success. This ensures at least 2 rounds of reconnaissance regardless.

Also: the call stack shows `run_attacker_loop()` calling `surface_server.get_available_attacker_actions()` but the current `run_attacker_loop` signature is:
```python
async def run_attacker_loop(config, surface_server, logger, memory)
```
The call stack adds `scheduled_events` as a parameter (UC-07) — this needs to be reflected in the C-04 and C-10 change items.

**Classification:** Logic Error — phase gate condition needs correction; function signature delta  
**Action:** Update UC-04 with corrected gate condition; add `run_attacker_loop` signature change to change items.

---

### F-004 — Logic Error (Medium)
**UC:** UC-06  
**Issue:** The JSONL batch upsert uses `_key: f"{sim_id}_{round_no}_{agent_id}"`. But `agent_id` in the current JSONL is `"attacker_0"`, `"defender_0"`, `"regulator_0"` — all fixed strings. Multiple actions in the same round by the same agent (e.g., if the regulator acts twice in a round) will produce duplicate `_key` values, causing the second UPSERT to silently overwrite the first.

**Required correction:** Use `f"{sim_id}_{round_no}_{agent_id}_{action_type}"` as the key, or better: use a monotonic counter suffix from the JSONL line number to guarantee uniqueness.

Recommended: `_key = f"{sim_id}_{i:06d}"` where `i` is the line index in the JSONL file.

**Classification:** Logic Error — duplicate key collision on multi-action rounds  
**Action:** Update UC-06 key formula to use line index.

---

### F-005 — Interface Gap (Medium)
**UC:** UC-11, UC-12, UC-13  
**Issue:** All three report agent UCs call `anthropic_client.messages.create()` with `model="claude-sonnet-4-6"`. But `report_agent.py` currently uses `get_settings().ANTHROPIC_MODEL_HAIKU` for cost efficiency. Switching to Sonnet for all 3 calls adds significant cost per simulation completion.

Also: the three LLM calls happen sequentially in `report_agent.generate()`. With Sonnet, each call is ~3–5 seconds. Total report generation time becomes 10–15 seconds per simulation, which blocks the writeback pipeline.

**Required correction:** 
- Run the three calls with `asyncio.gather()` for parallelism, cutting wall time to ~5 seconds
- Make model configurable: `ANTHROPIC_MODEL_REPORT` setting (default: sonnet, can set to haiku for cost savings)
- Add to proposed-design.md as AD-06

**Classification:** Interface Gap — cost and latency not addressed in design  
**Action:** Update UC-11/12/13 to show parallel gather; add AD-06 to proposed-design.md.

---

### F-006 — Missing Edge Case (Low)
**UC:** UC-09  
**Issue:** `_validate_compliance_payload()` raises `ValueError` for empty `cve_id`. The call stack shows the regulator loop catching this and continuing. But the current `regulator_simulation.py` calls `surface_server.apply_action()` which calls the validator inside `AttackSurfaceServer`. If the validator raises inside `apply_action`, the exception propagates back to `run_regulator_loop()`. The call stack correctly shows the try/except in the regulator loop. However, the `_VALID_FRAMEWORKS` list used for framework validation is defined in `regulator_simulation.py`, not in `attack_surface_server.py`. The validator in `attack_surface_server.py` cannot import from `regulator_simulation.py` without a circular import.

**Required correction:** Move `_VALID_FRAMEWORKS` constant to `attack_surface_server.py` or a shared `cse/constants.py` module. The validator in `attack_surface_server.py` references it from there.

**Classification:** Missing edge case — circular import risk  
**Action:** Add `cse/constants.py` to change items (C-12 scope extension); update UC-09 to show constant location.

---

### F-007 — Concurrency Issue (High)
**UC:** UC-10  
**Issue:** `get_state_snapshot()` reads from `self.chain_steps`, `self.patched_cves`, `self.detection_events` etc. These are mutated by `apply_action()` which runs concurrently across attacker, defender, and regulator coroutines. The current code has no locks because `asyncio` is cooperative (only one coroutine runs at a time). However, `get_state_snapshot()` is called *after* the action decision and *before* `apply_action()` returns — this is safe.

BUT: the call stack shows `game_state = surface_server.get_state_snapshot()` called *inside* the attacker loop *after* `apply_action()` returns. This means the snapshot reflects state AFTER the action, not the state that CAUSED the decision. This is backwards for explainability — the reasoning should reflect the state the agent *saw* when deciding.

**Required correction:** Call `get_state_snapshot()` BEFORE the LLM/heuristic decision, not after. Pass the snapshot to the logger. This is the "state that caused the decision."

The call stack in UC-10 must be reordered:
```
1. game_state = surface_server.get_state_snapshot()   # BEFORE decision
2. action, payload, source, reasoning = _decide_attacker_action(..., game_state)
3. result = surface_server.apply_action(action, payload, round_no)
4. logger.log(..., game_state_snapshot=game_state)    # snapshot from step 1
```

**Classification:** Concurrency/Logic Issue — snapshot timing is wrong for explainability  
**Action:** Update UC-10 call stack ordering; update C-16 to note pre-decision snapshot.

---

## Summary

| Finding | Severity | Classification | Blocks Stage 5? |
|---------|----------|---------------|-----------------|
| F-001 | Medium | Design Impact | Yes — UC-01 missing subprocess path |
| F-002 | High | Design Impact | Yes — probability modifier logic ambiguous |
| F-003 | High | Logic Error | Yes — phase gate exits RECON after 1 round |
| F-004 | Medium | Logic Error | Yes — JSONL key collision |
| F-005 | Medium | Interface Gap | Yes — report agent cost/latency unaddressed |
| F-006 | Low | Missing Edge Case | No — circular import is fixable, doesn't block |
| F-007 | High | Logic/Concurrency | Yes — snapshot timing wrong |

**Round 1 Gate Decision: BLOCKED — 7 findings, 5 blocking**  

---

## Review Round 2 (2026-04-16)

All 7 findings addressed in call-stack v2 and proposed-design.md update:

| Finding | Fix Applied | Location |
|---------|-------------|----------|
| F-001 | UC-01 now shows subprocess entity_techniques read path | call-stack v2 UC-01 |
| F-002 | Modifier split: general -0.10 + CVE-specific -0.20 | call-stack v2 UC-03, proposed-design.md §2 |
| F-003 | RECON gate: round_no >= 2 AND exploitable > 0 | call-stack v2 UC-04 |
| F-004 | Key = f"{sim_id}_{i:06d}" (line index) | call-stack v2 UC-06 |
| F-005 | asyncio.gather() for 3 report calls; AD-06 added | call-stack v2 UC-11 |
| F-006 | VALID_FRAMEWORKS from cse/constants.py | call-stack v2 UC-09 |
| F-007 | get_state_snapshot() called BEFORE decision | call-stack v2 UC-04, UC-10 |

**No new findings in Round 2 scan.**

**Round 2 Gate Decision: Candidate Go**

---

## Review Round 3 (2026-04-16)

Re-scan of v2 call stacks for any regressions from Round 2 fixes.

Checked:
- F-001 fix: subprocess path consistent with config_generator writing entity_techniques — confirmed
- F-002 fix: modifier split is additive; worst case (general + CVE-specific) = -0.30 matches prior intent — confirmed
- F-003 fix: round_no >= 2 means minimum 2 SCAN rounds before exploitation — correct; does not break phase for short sims (total_rounds=48 still has round_no=1,2 before exploitation)
- F-004 fix: line index key is stable across retries (same JSONL line = same _key) — confirmed
- F-005 fix: asyncio.gather() requires report_agent.generate() to be async — need to verify current signature
- F-006 fix: cse/constants.py is a new file (C-12 scope extended) — no circular import — confirmed
- F-007 fix: snapshot before decision and passed to logger — consistent across UC-04 and UC-10 — confirmed

One observation on F-005: `report_agent.generate()` in current code is a synchronous function. Making it async requires changing `simulation_manager.complete()` call site. This is a minor scope extension (C-13/14/15 change items) but not a blocker — the change is straightforward.

**Round 3 Gate Decision: Go Confirmed**  
**Stage 5 Result: PASS**  
**Advance to Stage 6 — Source Implementation**
