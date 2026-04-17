# Investigation Notes — cse-engine-accuracy-explainability

## Audit Findings (2026-04-16)

Full 25-issue audit performed against all CSE files. Key findings per layer:

---

## Layer 1: Attacker Agent (`attacker_simulation.py`)

### T1190 Hardcode (C-1 CRITICAL)
Lines 131 + 137: `technique: "T1190"` hardcoded in both success and fallback paths.

**Root cause:** Technique resolver was deferred during initial build. The graph already has the
data to resolve it: `has_weakness` → CWE → `capec_relates_to_cwe` → CAPEC →
`capec_maps_to_attack` → ATT&CK technique. 567 `technique_exploits_weakness` edges exist.

**Graph path test (confirmed working):**
```aql
FOR v IN vulnerabilities FILTER v._key == "CVE_2021_44228"
  FOR cwe IN 1..1 OUTBOUND v has_weakness
    FOR capec IN 1..1 INBOUND cwe capec_relates_to_cwe
      FOR tech IN 1..1 OUTBOUND capec capec_maps_to_attack
        RETURN tech.technique_id
-- Returns: T1059, T1190, T1203
```

### Action State Machine Missing (H-1 HIGH)
No gates between SCAN → EXPLOIT → LATERAL → ESCALATE → PIVOT.
LLM prompt lists all 5 actions as equally available every round.
Observed in 720-round simulation: attacker performed EXPLOIT_CVE ~680 times, SCAN_SURFACE ~40 times,
LATERAL_MOVE 0 times, ESCALATE_PRIVILEGES 0 times.

**Fix approach:** Track `phase: "recon" | "exploitation" | "lateral" | "escalation"` in
AttackSurfaceServer. Gate available actions per phase. Pass current phase + available actions
to LLM prompt.

---

## Layer 2: Attack Surface Server (`attack_surface_server.py`)

### Guaranteed Exploit Success (C-2 CRITICAL)
`_action_exploit_cve()` lines 180–193: only failure case is `cve_id not in exploitable_cves`.
If CVE is in the list, success is 100%. Defender actions (patch, deploy_control, monitor, detect)
write to their own lists but none of them read by `_action_exploit_cve()`.

**Evidence from 720-round sim:** Every CVE in attack surface was eventually exploited.
`soc_blind_spots` populated for every CVE = no detection ever stopped an exploit.

**Probability model designed:**
```python
base = 0.85 if is_kev else 0.60
modifiers = {
    "monitoring_active":       -0.15,
    "detection_event_exists":  -0.20,
    "control_deployed":        -0.30,
    "no_foothold":             -0.10,   # privilege_level == 0
    "repeated_attempt":        -0.10,   # per prior attempt, cap -0.30
}
```
This gives: un-monitored KEV = 85% → monitored + detected = 50% → control deployed = 35%.

### Detection Events Unused (H-3 HIGH)
`detection_events` list exists (line 236–239) but never read by attacker or exploit logic.
Attacker prompt does not include detected CVEs. SOC detections are cosmetic.

---

## Layer 3: Defender Agent (`defender_simulation.py`)

### Heuristic Fallback Misaligned (H-4 HIGH)
Lines 147–154: fallback PATCH picks `random.choice(surface_server.exploitable_cves)`.
`exploitable_cves` returns all CVEs not in `patched_cves`. This means defender can "patch"
a CVE that was never exploited, wasting the action. Should prioritise CVEs in `chain_steps`.

**Fix:** Fallback should check `chain_steps` first → patch the most recently exploited CVE.

---

## Layer 4: Regulator Agent (`regulator_simulation.py`)

### Empty CVE in Gap Findings (H-5 HIGH)
Line 166: `cve_id = data.get("cve_id", "") or random.choice(exploitable_cves) or ""`
If `exploitable_cves` is empty (all patched), cve_id = "". Compliance gap with no CVE is invalid.

### Hardcoded Frameworks
Lines 42–47: `_FRAMEWORKS = ["CRA", "FDA_524B", "HIPAA", "NIST_800_53"]`
Should be loaded from simulation config → tenant's regulatory obligations from graph.

---

## Layer 5: Memory Updater / Subprocess (`memory_updater.py`, `run_parallel_cyber_simulation.py`)

### ArangoDB Flush No-op (C-4 CRITICAL)
`flush_remaining(db=None)` at line 81 of `run_parallel_cyber_simulation.py`.
`memory_updater.py` line 100: `if self._pending_for_arango and db is not None:` → skipped.

**Evidence:** After simulation, ArangoDB `agent_action_logs` has 0 Defender or Regulator entries.
Only Attacker entries (written by a separate path through writeback_service) present.

**Fix:** Don't attempt ArangoDB flush from subprocess. In `simulation_manager.complete()`,
after subprocess exits, parse full `cyber_actions.jsonl` and batch-upsert all entries to
`agent_action_logs`. This is already partly done in writeback Step 5 but only for a subset.

### Scheduled Events Not Executed (H-2 HIGH)
`config_generator.py` line 45: `scheduled_events = _build_scheduled_events(entities, total_rounds)`
Lines 65–76: builds KEV CVE events at rounds 1, 4, 7, 10, 13.
`run_parallel_cyber_simulation.py`: no code reads `config["scheduled_events"]`.
Events are built, written to config, and ignored.

---

## Layer 6: Report Agent (`report_agent.py`)

### No Explainability Output
Report agent generates `board_narrative`, `tef_estimate`, `soc_miss_probability`.
No per-chain explanation, no counterfactual, no audit trail.

**LLM capability confirmed:** Claude can generate structured counterfactuals and causal
explanations given the chain data. Additional prompt sections needed:

```
Given attack_chains: [...]
Given defender_actions: [...]
Given missed_deadline_rounds: [...]

Generate:
1. per_chain_narrative: one paragraph per chain explaining entry point, technique, and why it succeeded
2. counterfactuals: list of specific changes that would have broken each chain
3. audit_trail: ordered timeline of significant events with regulatory obligations
```

---

## Explainability Design

### Decision Trace
Every `cyber_actions.jsonl` entry should be extended from:
```json
{"type": "action", "agent_type": "Attacker", "action_type": "EXPLOIT_CVE", "outcome": "...", "round_no": 5}
```
to:
```json
{
  "type": "action",
  "agent_type": "Attacker",
  "action_type": "EXPLOIT_CVE",
  "outcome": "...",
  "round_no": 5,
  "decision_source": "llm",
  "decision_reasoning": "CVE-2021-44228 selected: CVSS 10.0, KEV, unpatched after 5 rounds",
  "game_state_snapshot": {
    "exploitable_count": 12,
    "patched_count": 3,
    "chain_steps": 2,
    "monitoring_active": false,
    "privilege_level": 1
  }
}
```

### Counterfactual Format
```json
{
  "chain_id": "chain_0",
  "counterfactuals": [
    {
      "intervention": "Patch CVE-2021-44228 by round 8",
      "current_round_patched": 15,
      "impact": "Attack chain would not have formed — entry point removed 7 rounds before exploitation"
    },
    {
      "intervention": "Enable monitoring before round 5",
      "current_state": "monitoring activated at round 18",
      "impact": "SOC blind spot at round 6 would have been detected, reducing chain probability from 0.91 to 0.42"
    }
  ]
}
```

### CISO Explainability View Addition
New field in `/v1/situation/ciso` response:
```json
{
  "threat_category_explanations": [
    {
      "bucket_name": "remote_code_execution",
      "driving_events": ["CVE-2021-44228 exploited at round 6 via T1190", "Lateral movement to 2 components at round 18"],
      "turning_point_round": 6,
      "what_would_have_helped": "Patching CVE-2021-44228 before round 6 would have prevented chain formation"
    }
  ]
}
```

---

## Effort Estimates

| Area | Files Changed | Complexity | Estimated Rounds |
|------|--------------|------------|------------------|
| Technique resolver | attacker_simulation.py | Medium | 2–3 |
| Probabilistic exploit model | attack_surface_server.py | High | 3–4 |
| Action state machine | attacker_simulation.py, attack_surface_server.py | High | 3–4 |
| LLM retry + fallback | all 3 agent files | Low | 1–2 |
| JSONL→ArangoDB flush | simulation_manager.py | Medium | 2 |
| Scheduled events | run_parallel_cyber_simulation.py | Low | 1 |
| Decision trace logging | action_logger.py | Medium | 2 |
| Report agent explainability | report_agent.py | High | 4–5 |
| Situation Room explainability | abstraction_layer.py, models.py | Medium | 3 |
| Writeback explainability fields | writeback_service.py | Medium | 2 |
| Tests | tests/unit/cse/ | Medium | 3 |

**Total scope: Large (10 files core, 3 files situation layer, 2 files writeback, tests)**
