# Requirements — cse-engine-accuracy-explainability

**Status:** Design-ready  
**Scope:** Large  
**Branch:** codex/cse-engine-accuracy-explainability  

---

## Goal / Problem Statement

The CSE engine produces simulations that run end-to-end but are not accurate enough to be trusted as risk evidence. Three specific problems:

1. **Simulation is deterministic and unrealistic** — the attacker always uses technique T1190, always succeeds when a CVE is exploitable, and never adapts to defender actions. Breach probability is consistently 85–100% regardless of the organisation's actual posture.

2. **Defender actions have no effect** — detections, patches, and deployed controls do not influence attacker success probability. The simulation is not adversarial — it is a one-sided replay.

3. **No explainability** — simulation outputs (attack chains, posture scores, compliance gaps) arrive without reasoning. A CISO cannot understand *why* a specific CVE was exploited, *why* a particular technique was chosen, *what the defender did that failed*, or *what would have changed the outcome*. Compliance assessors require audit-ready explanations, not just numeric outputs.

The goal is to fix all 4 critical issues, the 5 high-severity realism gaps, and add a full explainability layer across the simulation engine and Situation Room personas.

---

## Explainability Requirements

Explainability means every simulation output can be traced to a specific decision, with reasoning that a non-technical stakeholder can understand.

### EX-01: Per-Chain Narrative
Every attack chain finding must include a human-readable narrative explaining:
- Which CVE was the entry point and why the attacker chose it
- Which technique was used and why it succeeded
- What the defender did in response and whether it was effective
- What the SOC blind spot was (if any) and what detection would have caught it
- What a single countermeasure would have broken the chain

### EX-02: Per-Round Decision Trace
Every agent action must be traceable to the game state that caused it:
- Attacker: "Chose EXPLOIT_CVE(CVE-2021-44228) because it has CVSS 10.0, is in KEV, and patch has not been deployed after 12 rounds"
- Defender: "Chose PATCH(CVE-2021-44228) because it was exploited in chain step 3 and CISO alert was active"
- Regulator: "Issued CRA compliance gap because CVE-2021-44228 was exploited and CRA Article 14 notification deadline (round 24) was missed"

### EX-03: Counterfactual Analysis
For every completed simulation, generate a counterfactual explaining:
- "If the defender had patched CVE-2021-44228 by round 8 (instead of round 15), the attack chain would not have formed"
- "If monitoring had been active before round 5, the SOC blind spot at round 6 would have been detected"
- "If FDA 524B notification had been filed by round 30, the regulatory fine risk would have been zero"

### EX-04: CISO Explainability View
The CISO Situation Room persona must include per-threat-category explanations:
- Which specific simulation events drove the breach probability
- Which rounds were the turning points
- Which defender actions were effective vs. ineffective

### EX-05: Board Explainability View
The Board Situation Room persona must include:
- Plain-English explanation of how the financial exposure figure was derived
- Which attack chains contributed to the TEF estimate
- What investment in which control would reduce the exposure by what amount

### EX-06: Audit Trail Document
After each simulation, generate an audit-ready JSON document containing:
- Full decision trace for every agent action with game state snapshot
- Chain of custody from CVE → exploit → technique → detection → outcome
- Regulatory obligation timeline showing which deadlines were met/missed
- Confidence intervals for all probability outputs

---

## Accuracy Fix Requirements

### AC-01: Technique Diversity (Critical C-1)
**File:** `attacker_simulation.py` lines 131, 137

Replace hardcoded `"T1190"` with a dynamic technique resolver that:
- Looks up the CVE's CWE in the graph (`has_weakness` edges)
- Traverses CWE → CAPEC → ATT&CK via `capec_relates_to_cwe` + `capec_maps_to_attack` edges
- Falls back to a severity-bucketed technique distribution if no graph path exists:
  - CVSS 9–10: T1190, T1133, T1078 (external exposure)
  - CVSS 7–8.9: T1059, T1047, T1055 (execution/injection)
  - CVSS < 7: T1203, T1189, T1566 (user-assisted)
- Logs the resolution path (graph vs. fallback) for explainability

### AC-02: Probabilistic Exploit Outcome (Critical C-2)
**File:** `attack_surface_server.py` `_action_exploit_cve()`

Replace guaranteed success with a probabilistic model:

```
base_success_probability = 0.85 if is_kev else 0.60

modifiers:
  - monitoring_active:        -0.15 (harder to exploit undetected)
  - detection_event_exists:   -0.20 (SOC has seen this CVE)
  - control_deployed_for_cve: -0.30 (active countermeasure)
  - privilege_level == 0:     -0.10 (no foothold yet)
  - attacker tried this CVE before: -0.10 per prior attempt (capped at -0.30)

final_probability = clamp(base + sum(modifiers), 0.05, 0.95)
```

Outcome logging:
- `exploit_success`: probability check passed
- `exploit_blocked_by_detection`: detection modifier caused failure
- `exploit_blocked_by_control`: control modifier caused failure
- `exploit_failed_probabilistic`: random failure with no specific cause

### AC-03: Defender Effectiveness (Critical C-2 companion)
When a control is deployed or a CVE patched, it must immediately affect the shared game state such that:
- `patched_cves` removes the CVE from `get_exploitable_cves()`
- `controls_deployed` list is checked by `_action_exploit_cve()` for probability modifiers
- `detection_events` list is checked to determine if a specific CVE has been seen

### AC-04: LLM Failure Handling (Critical C-3)
**Files:** `attacker_simulation.py`, `defender_simulation.py`, `regulator_simulation.py`

Replace silent fallbacks with:
- Retry logic: 2 retries with 500ms backoff before fallback
- Structured fallback: heuristic decisions based on current game state, not fixed passive defaults
- Error telemetry: increment `llm_failure_count` in game state; if > 20% of rounds fail, mark simulation as `degraded` status
- Round-level decision trace: record whether decision came from LLM or heuristic fallback

### AC-05: ArangoDB Flush in Subprocess (Critical C-4)
**File:** `run_parallel_cyber_simulation.py`, `memory_updater.py`

The subprocess has no DB connection. Fix by:
- Writing all agent activity to the `cyber_actions.jsonl` (already done)
- In `simulation_manager.complete()`, after subprocess exits, read the full JSONL and upsert all Defender + Regulator agent activity to `agent_action_logs` in ArangoDB
- Remove the `flush_remaining(db=None)` call from subprocess — document it as a no-op in subprocess context

### AC-06: Attacker Action Diversity (High H-1)
**File:** `attacker_simulation.py`

Add state machine gates for attacker actions:
- `SCAN_SURFACE` required before first `EXPLOIT_CVE` (reconnaissance phase, rounds 1–3)
- `EXPLOIT_CVE` unlocks `LATERAL_MOVE` after first successful exploit
- `LATERAL_MOVE` unlocks `ESCALATE_PRIVILEGES` after reaching second component
- `ESCALATE_PRIVILEGES` unlocks `PIVOT_TARGET` after privilege_level ≥ 2
- LLM prompt updated to reflect which actions are currently available given state

### AC-07: Scheduled Events Execution (High H-2)
**File:** `config_generator.py`, `run_parallel_cyber_simulation.py`

Execute scheduled events at the designated round:
- In the main simulation loop, before each round's agent actions, check `scheduled_events` for round == current_round
- For KEV CVE scheduled events, automatically apply `EXPLOIT_CVE` with significance 0.9 regardless of attacker LLM decision
- Log scheduled events as a distinct event type in `cyber_actions.jsonl`

### AC-08: Detection Affects Attacker (High H-3)
**File:** `attack_surface_server.py`, `attacker_simulation.py`

Pass detection event list to attacker decision:
- Attacker prompt includes: "The following CVEs have been detected by SOC: [list]"
- Attacker should de-prioritise detected CVEs and attempt undetected ones
- If all exploitable CVEs are detected, attacker should switch to LATERAL_MOVE

### AC-09: Compliance Gap Validation (High H-5)
**File:** `regulator_simulation.py`

Add payload validation:
- Reject `ISSUE_COMPLIANCE_FINDING` payloads with empty cve_id
- Validate framework against known list before writing
- Only assign severity field for finding-type actions

---

## Acceptance Criteria

| ID | Criterion | Verifiable Outcome |
|----|-----------|-------------------|
| AC-E01 | Per-chain narrative generated for every completed simulation | `attack_chain_findings` documents have non-empty `explanation` field after writeback |
| AC-E02 | Per-round decision trace stored with every agent action | `agent_action_logs` documents have `decision_source` (llm/heuristic) and `game_state_snapshot` fields |
| AC-E03 | Counterfactual analysis generated by report agent | `simulation_runs` has `counterfactuals` array after completion |
| AC-E04 | CISO situation view includes per-category explanation | `/v1/situation/ciso` response includes `threat_category_explanations` array |
| AC-E05 | Board situation view includes financial derivation | `/v1/situation/board` response includes `exposure_derivation` narrative |
| AC-E06 | Audit trail document generated and stored | `simulation_runs.audit_trail_url` or embedded `audit_trail` field populated |
| AC-A01 | Technique resolver uses graph CWE→ATT&CK path | Unit test: CVE with known CWE resolves to correct technique |
| AC-A02 | Exploit success is probabilistic | Unit test: same CVE with monitoring_active=True fails > 15% of the time |
| AC-A03 | Control deployment reduces exploit success rate | Integration test: defender patches CVE → attacker cannot exploit it |
| AC-A04 | LLM failure retries before fallback | Unit test: mock LLM failing 2× then succeeding → action taken from LLM |
| AC-A05 | Defender/Regulator actions present in ArangoDB after simulation | DB query after run → `agent_action_logs` has Defender and Regulator entries |
| AC-A06 | Attacker uses LATERAL_MOVE and ESCALATE_PRIVILEGES | Unit test: simulation of 50 rounds includes all 5 action types |
| AC-A07 | Scheduled events fire at correct round | Unit test: round 1 triggers KEV CVE exploit automatically |
| AC-A08 | Detected CVEs deprioritised by attacker | Unit test: attacker with detected CVE-A and undetected CVE-B exploits CVE-B |
| AC-A09 | Compliance gap rejects empty cve_id | Unit test: `_build_payload` raises ValueError for ISSUE_COMPLIANCE_FINDING with no CVE |

---

## Use Cases

| ID | Use Case |
|----|----------|
| UC-01 | Attacker resolves CVE→CWE→ATT&CK technique from graph, falls back to severity bucket |
| UC-02 | Exploit outcome is probabilistic; monitoring/controls/detections reduce success chance |
| UC-03 | Defender patches a CVE → attacker cannot exploit it in subsequent rounds |
| UC-04 | LLM failure retries twice → heuristic fallback with game-state reasoning logged |
| UC-05 | Subprocess JSONL flushed to ArangoDB in main process after simulation exits |
| UC-06 | Attacker follows state machine: SCAN → EXPLOIT → LATERAL → ESCALATE → PIVOT |
| UC-07 | Scheduled KEV events auto-fire at designated round, independent of LLM |
| UC-08 | Report agent generates per-chain narrative, counterfactuals, and audit trail |
| UC-09 | Situation Room CISO view includes threat category explanations |
| UC-10 | Situation Room Board view includes financial exposure derivation narrative |
| UC-11 | Audit trail document stored with every completed simulation run |

---

## Change Items

| ID | File | Change |
|----|------|--------|
| C-01 | `attacker_simulation.py` | Replace T1190 hardcode with `_resolve_technique(cve_id, db)` |
| C-02 | `attack_surface_server.py` | Add probabilistic exploit outcome model with modifier stack |
| C-03 | `attack_surface_server.py` | Add `exploit_attempts: dict[str, int]` to track per-CVE retry penalty |
| C-04 | `attacker_simulation.py` | Add action state machine (SCAN→EXPLOIT→LATERAL→ESCALATE→PIVOT gates) |
| C-05 | `attacker_simulation.py` | Add retry logic + structured heuristic fallback with logging |
| C-06 | `defender_simulation.py` | Add retry logic + aligned heuristic fallback based on game state |
| C-07 | `regulator_simulation.py` | Add retry logic + payload validation |
| C-08 | `run_parallel_cyber_simulation.py` | Remove `flush_remaining(db=None)`; document subprocess DB-free design |
| C-09 | `simulation_manager.py` | In `complete()`, flush JSONL to ArangoDB after subprocess exits |
| C-10 | `run_parallel_cyber_simulation.py` | Execute scheduled events before agent actions each round |
| C-11 | `attack_surface_server.py` | Pass detection events to attacker state snapshot |
| C-12 | `regulator_simulation.py` | Add `_validate_payload()` with required field checks |
| C-13 | `report_agent.py` | Add per-chain narrative generation to report output |
| C-14 | `report_agent.py` | Add counterfactual analysis generation |
| C-15 | `report_agent.py` | Add audit trail document generation |
| C-16 | `action_logger.py` | Add `decision_source` + `game_state_snapshot` fields to logged events |
| C-17 | `writeback_service.py` | Write `explanation` field to `attack_chain_findings` |
| C-18 | `writeback_service.py` | Write `counterfactuals` array to `simulation_runs` |
| C-19 | `situation/abstraction_layer.py` | Add `threat_category_explanations` to `compute_ciso()` |
| C-20 | `situation/abstraction_layer.py` | Add `exposure_derivation` narrative to `compute_board()` |

---

## Constraints

- Must not break existing 91 CSE + situation unit tests
- Technique resolver must handle CVEs with no CWE mapping gracefully
- Probabilistic model must be deterministic given the same random seed (reproducible simulations)
- Explainability narratives generated by LLM must be cached to avoid latency on repeat requests
- Audit trail document must not contain raw CVE IDs in CISO or Board views (persona boundary rule)
- All new fields must be backwards-compatible (optional, not required)
