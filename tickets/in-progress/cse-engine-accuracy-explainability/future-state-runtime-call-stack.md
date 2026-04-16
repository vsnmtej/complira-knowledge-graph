# Future-State Runtime Call Stacks — cse-engine-accuracy-explainability

## Design Basis

- Scope Classification: `Large`
- Call Stack Version: `v1`
- Requirements: `tickets/in-progress/cse-engine-accuracy-explainability/requirements.md` (status `Design-ready`)
- Source Artifact: `tickets/in-progress/cse-engine-accuracy-explainability/proposed-design.md` v1
- Referenced Sections: §1 Architecture Decisions, §2 Component Design, §3 Data Flow, §4 Test Plan

---

## Future-State Modeling Rule

All call stacks model the **target (to-be)** design. Where current code diverges, the target behaviour is shown. Migration notes appear in the Transition Notes section.

---

## Use Case Index

| UC | Name | Type | Change Items |
|----|------|------|-------------|
| UC-01 | Technique resolver — graph path | Requirement | C-01 |
| UC-02 | Technique resolver — severity fallback | Requirement | C-01 |
| UC-03 | Probabilistic exploit model | Requirement | C-02, C-03 |
| UC-04 | Action state machine phase transitions | Requirement | C-04 |
| UC-05 | LLM retry + structured fallback | Requirement | C-05, C-06, C-07 |
| UC-06 | ArangoDB flush via main-process JSONL parse | Requirement | C-08, C-09 |
| UC-07 | Scheduled events auto-fire | Requirement | C-10 |
| UC-08 | Detection events fed to attacker | Requirement | C-11 |
| UC-09 | Compliance gap payload validation | Requirement | C-12 |
| UC-10 | Decision trace logging per agent action | Requirement | C-16 |
| UC-11 | Report agent — chain narratives | Requirement | C-13 |
| UC-12 | Report agent — counterfactuals | Requirement | C-14 |
| UC-13 | Report agent — audit trail | Requirement | C-15 |
| UC-14 | Writeback — explanation + counterfactuals | Requirement | C-17, C-18 |
| UC-15 | CISO view — threat category explanations | Requirement | C-19 |
| UC-16 | Board view — exposure derivation | Requirement | C-20 |

---

## Transition Notes

- `attacker_simulation.py` line 131+137: `"T1190"` replaced by `TechniqueResolver.resolve()`. No change to caller signature.
- `attack_surface_server.py` `_action_exploit_cve()`: currently returns `exploit_success` unconditionally. Target inserts probability check before success return; all existing callers receive `ActionResult` — interface unchanged.
- `AttackSurfaceServer.__init__()`: adds `attacker_phase: AttackerPhase`, `exploit_attempts: dict[str,int]`, `entity_techniques: dict[str,list[str]]`. All existing fields preserved.
- `run_parallel_cyber_simulation.py`: `flush_remaining(db=None)` call removed. No new DB connection in subprocess.
- `simulation_manager.complete()`: new step added after subprocess exits — parse JSONL, batch-upsert to `agent_action_logs`. Existing steps shift down by 1.
- `CyberActionLogger`: adds `decision_source`, `decision_reasoning`, `game_state_snapshot` to JSONL entries. Backwards-compatible (new optional fields).
- `report_agent.py`: output dict gains `chain_narratives`, `counterfactuals`, `audit_trail`, `technique_coverage`, `defender_effectiveness_score`. Existing fields preserved.
- `simulation_manager._build_agent_outputs()` and `_build_writeback_payload()`: pass through new report fields to writeback payload.
- `situation/models.py`: new optional fields added to `CISOSituation` and `BoardSituation`. No breaking changes.

---

## UC-01: Technique Resolver — Graph Path

### Goal
For a CVE with a known CWE in the graph, resolve the correct ATT&CK technique(s) via
`has_weakness → capec_relates_to_cwe → capec_maps_to_attack`.

### Preconditions
- CVE has `has_weakness` edge(s) to at least one CWE
- CWE has `capec_relates_to_cwe` edge(s) to CAPEC entries
- CAPEC has `capec_maps_to_attack` edge(s) to ATT&CK techniques
- ArangoDB accessible from main process (prepare phase)

### Expected Outcome
`TechniqueResolver.resolve("CVE_2021_44228", 10.0, db)` returns `("T1190", "graph")`
(or another valid technique mapped from CWE-20/CWE-502).

### Call Stack

```
[ENTRY] simulation_manager.prepare(db, tenant_id, trigger_type)
└── CompliraGraphReader(db).get_attack_surface(tenant_id)
    → returns entities: list[CyberEntityNode]
└── TechniqueResolver(db).resolve_all(entities)              # new
    ├── for each entity in entities:
    │   └── TechniqueResolver.resolve(entity.entity_id, entity.severity, db)
    │       ├── db.aql.execute(_AQL_TECHNIQUE_FROM_CVE, {"cve_key": entity.entity_id})
    │       │   # AQL:
    │       │   # FOR v IN vulnerabilities FILTER v._key == @cve_key
    │       │   #   FOR cwe IN 1..1 OUTBOUND v has_weakness
    │       │   #     FOR capec IN 1..1 INBOUND cwe capec_relates_to_cwe
    │       │   #       FOR tech IN 1..1 OUTBOUND capec capec_maps_to_attack
    │       │   #         RETURN DISTINCT tech.technique_id
    │       ├── [if results]: return (results[0], "graph")
    │       └── [if no results]: fall through to UC-02 fallback
    └── returns entity_techniques: dict[str, list[str]]
        # e.g. {"CVE_2021_44228": ["T1190", "T1059"], "CVE_2022_22965": ["T1190"]}
└── CyberSimConfigGenerator.generate(
        sim_id, tenant_id, trigger_type, profiles, entities, sim_dir,
        entity_techniques=entity_techniques               # new parameter
    )
    └── writes simulation_config.json["entity_techniques"] = entity_techniques
```

---

## UC-02: Technique Resolver — Severity Fallback

### Goal
For a CVE with no CWE→ATT&CK graph path, return a plausible technique from the
severity-bucketed fallback distribution.

### Preconditions
- CVE has no `has_weakness` edges OR CWE has no CAPEC/ATT&CK mappings
- `entity.severity` (cvss_v3_score) is available

### Expected Outcome
`TechniqueResolver.resolve("CVE_2024_99999", 9.5, db)` returns one of
`["T1190", "T1133", "T1078"]` with source `"fallback"`.

### Call Stack

```
TechniqueResolver.resolve(cve_key, cvss, db)
├── db.aql.execute(_AQL_TECHNIQUE_FROM_CVE, ...) → empty result
└── _severity_bucket(cvss)
    ├── cvss >= 9.0 → bucket = "critical" → ["T1190", "T1133", "T1078"]
    ├── cvss >= 7.0 → bucket = "high"     → ["T1059", "T1047", "T1055"]
    ├── cvss >= 4.0 → bucket = "medium"   → ["T1203", "T1189", "T1566"]
    └── else        → bucket = "low"      → ["T1189", "T1204", "T1598"]
└── random.choice(bucket_techniques)
└── return (technique_id, "fallback")
    # logged: "technique_resolver: fallback used for {cve_key} (no graph path)"
```

---

## UC-03: Probabilistic Exploit Model

### Goal
Replace guaranteed exploit success with a probability model that makes defender
actions meaningful.

### Preconditions
- `AttackSurfaceServer` has `exploit_attempts: dict[str,int]` tracking prior attempts
- `monitoring_active`, `detection_events`, `controls_deployed` populated from prior rounds

### Expected Outcome
- Undefended KEV CVE: ~85% success
- Monitored + detected CVE: ~50% success
- Controlled CVE: ~35% success
- Same CVE attempted 3× with monitoring: ~25% success

### Call Stack

```
[ENTRY] attack_surface_server.apply_action(EXPLOIT_CVE, payload, round_no)
└── _action_exploit_cve(cve_id, technique, attacker_id, round_no)
    ├── if cve_id not in get_exploitable_cves(): return "cve_not_exploitable" [unchanged]
    │
    ├── ctx = ExploitContext(                                # new
    │       cve_id=cve_id,
    │       is_kev=_entity_is_kev(cve_id),
    │       monitoring_active=self.monitoring_active,
    │       detection_events=self.detection_events,
    │       controls_deployed=self.controls_deployed,
    │       exploit_attempts=self.exploit_attempts,
    │       privilege_level=self.privilege_level
    │   )
    │
    ├── prob, reasons = _compute_exploit_probability(ctx)   # new
    │   ├── base = 0.85 if is_kev else 0.60
    │   ├── apply modifiers (monitoring, detection, control, foothold, repeats)
    │   └── return (clamped_prob, modifier_reasons_list)
    │
    ├── self.exploit_attempts[cve_id] = self.exploit_attempts.get(cve_id, 0) + 1
    │
    ├── roll = random.random()                              # new
    ├── if roll <= prob:                                    # SUCCESS PATH
    │   ├── [existing] chain_steps.append(ChainStep(...))
    │   ├── [existing] check soc_blind_spot
    │   └── return ActionResult(
    │           EXPLOIT_CVE,
    │           f"exploit_success: {cve_id} via {technique}",
    │           significance=0.90 if is_kev else 0.75,
    │           exploit_probability=prob,                  # new
    │           probability_reasons=reasons                # new
    │         )
    │
    └── else:                                              # FAILURE PATH (new)
        ├── failure_reason = _classify_failure(ctx, reasons)
        │   # "exploit_blocked_by_detection" | "exploit_blocked_by_control" | "exploit_failed_probabilistic"
        └── return ActionResult(
                EXPLOIT_CVE,
                f"{failure_reason}: {cve_id}",
                significance=0.20,
                exploit_probability=prob,
                probability_reasons=reasons
              )
```

---

## UC-04: Action State Machine Phase Transitions

### Goal
Attacker follows a realistic kill-chain progression — cannot LATERAL_MOVE before
first successful exploit, cannot ESCALATE without lateral movement.

### Preconditions
- `AttackSurfaceServer.attacker_phase` starts as `AttackerPhase.RECON`
- Phase transitions triggered by successful action outcomes

### Expected Outcome
- Rounds 1–2: only `SCAN_SURFACE` available
- After first successful scan: `EXPLOIT_CVE` unlocked
- After first successful exploit: `LATERAL_MOVE` unlocked
- After first lateral move: `ESCALATE_PRIVILEGES` unlocked
- After first privilege escalation: `PIVOT_TARGET` unlocked

### Call Stack

```
[ENTRY] run_attacker_loop() — each round
│
├── available = surface_server.get_available_attacker_actions()  # new method
│   └── returns subset of ATTACKER_ACTIONS based on attacker_phase
│
├── _decide_attacker_action(config, surface_server, round_no, available_actions)
│   ├── [LLM path] prompt includes:
│   │   "Available actions THIS round: {available_actions}"
│   │   "Current attacker phase: {attacker_phase}"
│   └── [fallback path] picks best action from available_actions given game state
│
├── action, payload = _parse_action_response(raw, exploitable, available_actions)
│   └── validates action is in available_actions; rejects if not
│
└── result = surface_server.apply_action(action, payload, round_no)
    └── [on success — phase transition check]
        ├── SCAN_SURFACE success + phase==RECON
        │   → self.attacker_phase = AttackerPhase.EXPLOITATION
        ├── EXPLOIT_CVE success + phase==EXPLOITATION
        │   → self.attacker_phase = AttackerPhase.LATERAL
        ├── LATERAL_MOVE success + phase==LATERAL
        │   → self.attacker_phase = AttackerPhase.ESCALATION
        └── ESCALATE_PRIVILEGES success + phase==ESCALATION
            → self.attacker_phase = AttackerPhase.PIVOT
```

---

## UC-05: LLM Retry + Structured Fallback

### Goal
LLM failures retry twice with backoff before falling back to heuristic. Fallback
decisions are game-state-aware, not passive defaults. All decisions tagged with source.

### Preconditions
- Anthropic client available
- `surface_server.get_state_snapshot()` returns current game state dict

### Expected Outcome
- 2 LLM failures then success → `decision_source = "llm"`
- 3 LLM failures → `decision_source = "heuristic"`, reasoning logged
- LLM failure rate tracked; simulation marked `degraded` if > 20% of rounds fail

### Call Stack (Attacker — same pattern for Defender/Regulator)

```
_decide_attacker_action(config, surface_server, round_no, available_actions)
├── attempts = 0
├── max_attempts = 3
│
├── while attempts < max_attempts:                        # retry loop (new)
│   ├── try:
│   │   response = anthropic_client.messages.create(...)
│   │   action, payload = _parse_action_response(response.content[0].text, ...)
│   │   log.info("attacker_decision_llm", round=round_no, action=action)
│   │   return action, payload, decision_source="llm"    # new return field
│   │
│   ├── except RateLimitError:
│   │   wait = 0.5 * (2 ** attempts)                     # exponential backoff
│   │   await asyncio.sleep(wait)
│   │   attempts += 1
│   │
│   └── except Exception as e:
│       log.warning("attacker_llm_failure", round=round_no, attempt=attempts, error=str(e))
│       attempts += 1
│
└── [heuristic fallback — new]
    ├── surface_server.llm_failure_count += 1            # track failures
    ├── if surface_server.llm_failure_count / round_no > 0.20:
    │   surface_server.simulation_degraded = True
    │   log.error("simulation_degraded_llm_failure_rate", rate=...)
    │
    ├── action, reasoning = _heuristic_attacker_decision(surface_server, available_actions)
    │   # Game-state-aware heuristic:
    │   # - phase==RECON → SCAN_SURFACE
    │   # - phase==EXPLOITATION + exploitable CVEs → EXPLOIT_CVE(highest CVSS KEV first)
    │   # - phase==LATERAL → LATERAL_MOVE
    │   # - chain_steps > 3 → ESCALATE_PRIVILEGES
    │
    └── return action, payload, decision_source="heuristic", reasoning=reasoning
```

---

## UC-06: ArangoDB Flush via Main-Process JSONL Parse

### Goal
Defender and Regulator agent actions, written to `cyber_actions.jsonl` in the subprocess,
are flushed to `agent_action_logs` in ArangoDB by the main process after the subprocess exits.

### Preconditions
- Subprocess has completed and written all events to `cyber_actions.jsonl`
- Main process has ArangoDB connection

### Expected Outcome
After `simulation_manager.complete()`, `agent_action_logs` in ArangoDB contains entries
for Attacker, Defender, AND Regulator agents.

### Call Stack

```
[ENTRY] simulation_manager.complete(db, runner)
├── [existing] _run_complete_background waits for subprocess exit
├── [existing] report_agent.generate(...)
│
├── [NEW STEP] _flush_all_agent_logs_to_arango(db, runner.sim_dir, sim_id, tenant_id)
│   ├── jsonl_path = sim_dir / "cyber_actions.jsonl"
│   ├── if not jsonl_path.exists(): log.warning; return
│   │
│   ├── entries = []
│   ├── for line in jsonl_path.read_text().splitlines():
│   │   ├── entry = json.loads(line)
│   │   ├── if entry.get("type") != "action": continue
│   │   └── entries.append({
│   │           "_key":        f"{sim_id}_{entry['round_no']}_{entry['agent_id']}",
│   │           "sim_id":      sim_id,
│   │           "tenant_id":   tenant_id,
│   │           "round_no":    entry["round_no"],
│   │           "agent_type":  entry["agent_type"],
│   │           "action_type": entry["action_type"],
│   │           "outcome":     entry["outcome"],
│   │           "significance": entry.get("significance", 0.5),
│   │           "decision_source": entry.get("decision_source", "llm"),
│   │           "decision_reasoning": entry.get("decision_reasoning", ""),
│   │           "game_state_snapshot": entry.get("game_state_snapshot", {}),
│   │           "technique_id": entry.get("technique_id"),
│   │           "timestamp":   entry.get("timestamp"),
│   │       })
│   │
│   ├── # Batch upsert in chunks of 500
│   ├── for chunk in _chunks(entries, 500):
│   │   └── db.aql.execute(_AQL_UPSERT_AGENT_LOGS, bind_vars={"docs": chunk})
│   │       # FOR doc IN @docs UPSERT {_key: doc._key} INSERT doc UPDATE doc IN agent_action_logs
│   │
│   └── log.info("agent_logs_flushed", count=len(entries), sim_id=sim_id)
│
└── [existing] writeback_service.run_all(payload)
```

---

## UC-07: Scheduled Events Auto-Fire

### Goal
KEV CVEs scheduled in `simulation_config["scheduled_events"]` automatically trigger an
exploit at their designated round, regardless of LLM attacker decision.

### Preconditions
- `simulation_config["scheduled_events"]` populated by `config_generator._build_scheduled_events()`
- Subprocess reads `config["scheduled_events"]` at simulation start

### Expected Outcome
For a KEV CVE scheduled at round 1, `cyber_actions.jsonl` has an entry with
`round_no=1`, `agent_type="Attacker"`, `decision_source="scheduled"`.

### Call Stack

```
[ENTRY] run_parallel_cyber_simulation.main()
├── scheduled_events = config.get("scheduled_events", [])           # new
│   # e.g. [{"round": 1, "action": "EXPLOIT_CVE", "cve_id": "CVE_2021_44228", "is_kev": true}]
│
└── run_attacker_loop(config, surface_server, logger, memory, scheduled_events)
    └── for round_no in range(1, total_rounds + 1):
        │
        ├── [NEW] scheduled = [e for e in scheduled_events if e["round"] == round_no]
        ├── [NEW] for event in scheduled:
        │   ├── result = surface_server.apply_action(event["action"], event, round_no)
        │   └── logger.log(CyberAgentActivity(
        │           agent_type="Attacker",
        │           action_type=event["action"],
        │           outcome=result.outcome,
        │           significance=0.90,
        │           decision_source="scheduled",         # new
        │           decision_reasoning=f"Scheduled KEV event: {event['cve_id']}",
        │           ...
        │         ))
        │
        └── [existing] LLM decision for this round (in addition to scheduled)
```

---

## UC-08: Detection Events Fed to Attacker

### Goal
Defender detections are visible to attacker in subsequent rounds, causing attacker
to deprioritise detected CVEs.

### Preconditions
- `surface_server.detection_events` populated when defender runs `DETECT`
- `get_state_snapshot()` includes `detected_cves` list

### Expected Outcome
When CVE-A is in `detection_events` and CVE-B is not, attacker LLM prompt shows:
`"Detected by SOC (avoid): [CVE-A]"` and prefers CVE-B for exploitation.

### Call Stack

```
_decide_attacker_action(config, surface_server, round_no, available_actions)
│
└── state = surface_server.get_state_snapshot()                      # extended
    # now includes:
    # "detected_cves": [cve_id for cve_id in surface_server.detection_events]
    # "undetected_exploitable": [c for c in exploitable if c not in detection_events]
│
└── prompt = _build_attacker_prompt(config, state, round_no, available_actions)
    # new section in prompt:
    # "CVEs detected by SOC (higher risk to exploit): {state['detected_cves']}"
    # "Undetected CVEs (lower risk): {state['undetected_exploitable']}"
    # "Recommendation: prefer undetected CVEs to avoid detection"
```

---

## UC-09: Compliance Gap Payload Validation

### Goal
`ISSUE_COMPLIANCE_FINDING` actions with no CVE ID are rejected before writing to
`compliance_gaps`, preventing invalid gap findings.

### Preconditions
- Regulator agent attempts `ISSUE_COMPLIANCE_FINDING`
- `cve_id` field is empty string or None

### Expected Outcome
- `ValueError` raised with message `"ISSUE_COMPLIANCE_FINDING requires non-empty cve_id"`
- Action logged as failed, not as a compliance gap
- Regulator loop continues to next round

### Call Stack

```
[ENTRY] attack_surface_server.apply_action(ISSUE_COMPLIANCE_FINDING, payload, round_no)
└── _action_issue_compliance_finding(payload, round_no)
    ├── _validate_compliance_payload(payload)              # new
    │   ├── if not payload.get("cve_id"):
    │   │   raise ValueError("ISSUE_COMPLIANCE_FINDING requires non-empty cve_id")
    │   ├── if payload.get("framework") not in _VALID_FRAMEWORKS:
    │   │   raise ValueError(f"Unknown framework: {payload.get('framework')}")
    │   └── return True
    │
    ├── [existing] compliance_gaps.append(ComplianceGap(...))
    └── return ActionResult(...)

[CALLER] regulator_simulation._run_regulator_loop()
├── try:
│   result = surface_server.apply_action(action, payload, round_no)
├── except ValueError as e:
│   log.warning("compliance_gap_validation_failed", error=str(e), round=round_no)
│   result = ActionResult(action, f"validation_failed: {e}", {}, significance=0.1)
└── logger.log(...)
```

---

## UC-10: Decision Trace Logging Per Agent Action

### Goal
Every agent action written to `cyber_actions.jsonl` includes `decision_source`,
`decision_reasoning`, and `game_state_snapshot` for full explainability.

### Preconditions
- `CyberActionLogger` writes JSONL entries
- `CyberAgentActivity` dataclass has new fields

### Expected Outcome
Every line in `cyber_actions.jsonl` parses to a dict containing all 3 new fields.
`decision_source` is one of `"llm"`, `"heuristic"`, `"scheduled"`.

### Call Stack

```
[ENTRY] run_attacker_loop() — after decision made
│
├── game_state = surface_server.get_state_snapshot()               # new call
│
└── logger.log(CyberAgentActivity(
        sim_id=sim_id,
        round_no=round_no,
        agent_id="attacker_0",
        agent_type="Attacker",
        action_type=action,
        outcome=result.outcome,
        significance=result.significance,
        payload=payload,
        timestamp=datetime.utcnow().isoformat(),

        # New explainability fields
        decision_source=decision_source,       # "llm" | "heuristic" | "scheduled"
        decision_reasoning=decision_reasoning, # human-readable why
        game_state_snapshot={                  # compact snapshot
            "exploitable_count": len(game_state["exploitable_cves"]),
            "patched_count":     len(game_state["patched_cves"]),
            "chain_steps":       game_state["chain_step_count"],
            "monitoring":        game_state["monitoring_active"],
            "privilege_level":   game_state["privilege_level"],
            "attacker_phase":    game_state["attacker_phase"],
            "round_no":          round_no,
        },
        technique_id=payload.get("technique"),
        technique_source=payload.get("technique_source"),  # "graph" | "fallback"
    ))

action_logger.CyberActionLogger.log(activity)
└── line = json.dumps(asdict(activity))        # all new fields serialised
└── self._file.write(line + "\n")
└── self._file.flush()
```

---

## UC-11: Report Agent — Chain Narratives

### Goal
Report agent generates a per-chain narrative explaining entry point, technique,
defender response, and single countermeasure for each attack chain.

### Preconditions
- `chain_steps: list[ChainStep]` from completed simulation
- Full `cyber_actions.jsonl` available for defender action context
- Claude Sonnet available (higher quality than Haiku for narrative generation)

### Expected Outcome
`report["chain_narratives"]` contains one `ChainNarrative` per unique CVE in chain.
Each narrative has all 5 fields: `entry_point_reasoning`, `success_reasoning`,
`defender_response`, `soc_blind_spot_explanation`, `single_countermeasure`.

### Call Stack

```
[ENTRY] report_agent.generate(chain_steps, compliance_gaps, defender_actions, config)
│
├── [existing] _generate_board_report(chain_steps, compliance_gaps, config)
│   → board_narrative, tef_estimate, soc_miss_probability
│
├── [NEW] _generate_chain_narratives(chain_steps, defender_actions, config)
│   │
│   ├── defender_summary = _summarise_defender_actions(defender_actions)
│   │   # Group defender actions by round range near each chain step
│   │
│   ├── prompt = f"""
│   │   You are a cybersecurity analyst writing chain explanations for a CISO report.
│   │   
│   │   Attack chains observed:
│   │   {json.dumps(chain_steps_summary)}  # CVE, technique, round, success/fail
│   │   
│   │   Defender actions taken:
│   │   {json.dumps(defender_summary)}
│   │   
│   │   SOC blind spots (attacks missed by detection):
│   │   {json.dumps(soc_blind_spots)}
│   │   
│   │   For each attack chain, generate a JSON array of ChainNarrative objects with fields:
│   │   - chain_id, cve_id, technique_id
│   │   - entry_point_reasoning: why attacker chose this CVE (1–2 sentences)
│   │   - success_reasoning: why exploit succeeded given defender actions (1–2 sentences)
│   │   - defender_response: what defender did in response (1 sentence)
│   │   - soc_blind_spot_explanation: what detection would have caught this (1 sentence, null if detected)
│   │   - single_countermeasure: one specific action that would have stopped this chain (1 sentence)
│   │   
│   │   Return only the JSON array.
│   │   """
│   │
│   └── response = anthropic_client.messages.create(
│           model="claude-sonnet-4-6",
│           max_tokens=2048,
│           messages=[{"role": "user", "content": prompt}]
│         )
│       chain_narratives = json.loads(response.content[0].text)
│       return chain_narratives
│
└── report["chain_narratives"] = chain_narratives
```

---

## UC-12: Report Agent — Counterfactuals

### Goal
For each attack chain, generate a counterfactual explaining what specific intervention
would have broken the chain, with the round window available to act.

### Expected Outcome
`report["counterfactuals"]` has one entry per chain with `intervention_type`,
`intervention_description`, `current_state`, `impact_if_applied`, `rounds_available`.

### Call Stack

```
[ENTRY] report_agent._generate_counterfactuals(chain_steps, action_log, config)
│
├── # Build timeline: when each CVE was first exploited vs when it was patched (if at all)
├── patch_timeline = {
│       step.cve_id: _find_patch_round(step.cve_id, action_log)
│       for step in chain_steps
│   }
│
├── prompt = f"""
│   Attack chains: {chain_steps_summary}
│   Patch timeline (CVE → round patched, None if never): {patch_timeline}
│   Monitoring activated at round: {monitoring_activation_round}
│   Controls deployed: {controls_deployed_timeline}
│   CRA deadline round: {cra_deadline_round}
│   CRA notification filed at round: {cra_notification_round or "never"}
│   
│   For each chain, generate a Counterfactual JSON object:
│   - chain_id
│   - intervention_type: "patch" | "monitoring" | "control" | "notification"
│   - intervention_description: specific action in plain English
│   - current_state: what actually happened (with round numbers)
│   - impact_if_applied: what outcome would change and by how much
│   - rounds_available: how many rounds elapsed between when action was possible and when it was needed
│   
│   Return only the JSON array.
│   """
│
└── counterfactuals = json.loads(response.content[0].text)
└── report["counterfactuals"] = counterfactuals
```

---

## UC-13: Report Agent — Audit Trail

### Goal
Generate an ordered regulatory timeline showing which obligations were met or missed.

### Expected Outcome
`report["audit_trail"]` is a chronological list of significant events tagged with
regulatory obligations, outcome (`"met"` | `"missed"`), and round number.

### Call Stack

```
[ENTRY] report_agent._generate_audit_trail(chain_steps, compliance_gaps, action_log, config)
│
├── # Build event sequence from action_log + chain_steps
├── significant_events = _extract_significant_events(action_log, chain_steps)
│   # Includes: first exploit, detections, patches, CISO alerts, regulatory filings
│
├── prompt = f"""
│   Simulation events (round, type, description):
│   {json.dumps(significant_events)}
│   
│   Regulatory obligations:
│   - CRA Article 14: notify within round {cra_deadline_round} of significant incident
│   - FDA 524B: notify within round {fda_deadline_round}
│   - HIPAA: notify within round {hipaa_deadline_round}
│   
│   CRA notification filed: round {cra_filed_round or "never"}
│   FDA notification filed: round {fda_filed_round or "never"}
│   
│   Generate a chronological AuditTrail JSON array. Each entry:
│   - round_no
│   - event_type: "exploit" | "detection" | "patch" | "deadline" | "notification" | "escalation"
│   - description: plain English (no raw CVE IDs in board-safe entries)
│   - regulatory_obligation: framework + article or null
│   - outcome: "met" | "missed" | "not_applicable"
│   
│   Return only the JSON array.
│   """
│
└── audit_trail = json.loads(response.content[0].text)
└── report["audit_trail"] = audit_trail
```

---

## UC-14: Writeback — Explanation + Counterfactuals

### Goal
New report fields (`chain_narratives`, `counterfactuals`, `audit_trail`) are written
to ArangoDB collections after simulation completes.

### Call Stack

```
[ENTRY] writeback_service.run_all(payload)
│
├── [existing Steps 1–8b unchanged]
│
├── [NEW Step 9] _step9_write_chain_explanations(payload)
│   ├── for narrative in payload.get("chain_narratives", []):
│   │   └── db.aql.execute(_AQL_UPSERT_CHAIN_EXPLANATION, {
│   │           "finding_key": narrative["chain_id"],
│   │           "explanation": narrative,              # full ChainNarrative dict
│   │         })
│   │       # UPSERT {_key: @finding_key}
│   │       # UPDATE {explanation: @explanation}
│   │       # IN attack_chain_findings
│   └── log.debug("step9_chain_explanations_done", count=len(chain_narratives))
│
└── [NEW Step 10] _step10_write_simulation_explainability(payload)
    ├── db.aql.execute(_AQL_UPDATE_SIMULATION_RUN, {
    │       "sim_id": payload["run_id"],
    │       "counterfactuals": payload.get("counterfactuals", []),
    │       "audit_trail":     payload.get("audit_trail", []),
    │       "technique_coverage": payload.get("technique_coverage", []),
    │       "defender_effectiveness_score": payload.get("defender_effectiveness_score"),
    │     })
    └── log.debug("step10_explainability_done", sim_id=payload["run_id"])
```

---

## UC-15: CISO View — Threat Category Explanations

### Goal
`/v1/situation/ciso` includes per-category explanations alongside existing metrics.

### Call Stack

```
[ENTRY] SituationAbstractionLayer.compute_ciso(tenant_id)
│
├── [existing] rollups = get_threat_category_rollup(db, tenant_id)
├── [existing] threat_categories = [ThreatCategory(...) for r in rollups]
│
├── [NEW] threat_category_explanations = _build_category_explanations(rollups, db, tenant_id)
│   └── for rollup in rollups:
│       ├── # Fetch latest chain narratives for this tactic bucket
│       ├── narratives = db.aql.execute(_AQL_NARRATIVES_FOR_BUCKET, {
│       │       "bucket": rollup["bucket_name"],
│       │       "tenant_id": tenant_id,
│       │     })
│       └── ThreatCategoryExplanation(
│               bucket_name=rollup["bucket_name"],
│               driving_events=_extract_driving_events(narratives),
│               turning_point_round=_find_turning_point(narratives),
│               effective_defender_actions=_find_effective_defences(narratives),
│               what_would_have_helped=narratives[0].get("single_countermeasure", "") if narratives else "",
│             )
│
└── situation = CISOSituation(
        ...,                                # all existing fields
        threat_category_explanations=threat_category_explanations,  # new optional field
    )
```

---

## UC-16: Board View — Exposure Derivation

### Goal
`/v1/situation/board` includes a plain-English explanation of how the financial
exposure figure was calculated.

### Call Stack

```
[ENTRY] SituationAbstractionLayer.compute_board(tenant_id)
│
├── [existing] findings = get_business_impact_findings(db, tenant_id)
├── [existing] breach_probability_pct, financial_exposure range computed
│
├── [NEW] exposure_derivation = _build_exposure_derivation(
│       findings, breach_probability_pct, financial_exposure_low, financial_exposure_high, db, tenant_id
│     )
│   ├── latest_sim = get_latest_run_id(db, tenant_id)
│   ├── counterfactuals = _fetch_counterfactuals(db, latest_sim)
│   └── ExposureDerivation(
│           narrative=_build_derivation_narrative(
│               breach_probability_pct, financial_exposure_low, financial_exposure_high,
│               len(chain_count), counterfactuals
│           ),
│           contributing_chains=chain_count,
│           highest_confidence_chain=_describe_top_chain_safely(findings),
│           investment_recommendation=counterfactuals[0]["intervention_description"] if counterfactuals else "",
│         )
│
└── situation = BoardSituation(
        ...,                             # all existing fields
        exposure_derivation=exposure_derivation,  # new optional field
    )
```

---

## Cross-Cutting: `get_state_snapshot()` — New Method

Used by UC-05, UC-08, UC-10. Returns a compact dict of current game state:

```python
def get_state_snapshot(self) -> dict:
    return {
        "exploitable_cves":    list(self.get_exploitable_cves()),
        "patched_cves":        list(self.patched_cves),
        "detected_cves":       list(self.detection_events),
        "controls_deployed":   list(self.controls_deployed),
        "chain_step_count":    len(self.chain_steps),
        "soc_blind_spots":     list(self.soc_blind_spots),
        "privilege_level":     self.privilege_level,
        "monitoring_active":   self.monitoring_active,
        "ciso_alerted":        self.ciso_alerted,
        "cra_notified":        self.cra_notified,
        "attacker_phase":      self.attacker_phase.value,
        "llm_failure_count":   self.llm_failure_count,
        "simulation_degraded": self.simulation_degraded,
    }
```
