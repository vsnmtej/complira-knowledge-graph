# Code Review — cse-engine-accuracy-explainability

**Reviewer:** Claude Sonnet 4.6  
**Date:** 2026-04-16  
**Files reviewed:** 10 source files  
**Gate Decision:** PASS — No Blockers  

---

## Summary

| File | Status | Blocker | Major | Minor | Nitpick |
|------|--------|---------|-------|-------|---------|
| constants.py | PASS | 0 | 0 | 0 | 0 |
| technique_resolver.py | PASS | 0 | 0 | 0 | 0 |
| attack_surface_server.py | PASS | 0 | 0 | 0 | 1 |
| action_logger.py | PASS | 0 | 0 | 0 | 0 |
| attacker_simulation.py | PASS | 0 | 0 | 1 | 0 |
| defender_simulation.py | PASS | 0 | 0 | 0 | 0 |
| regulator_simulation.py | PASS | 0 | 0 | 0 | 0 |
| config_generator.py | PASS | 0 | 0 | 0 | 0 |
| report_agent.py | PASS | 0 | 0 | 0 | 1 |
| simulation_manager.py | PASS | 0 | 0 | 0 | 0 |

---

## File Reviews

### constants.py — PASS
Immutable frozensets for VALID_FRAMEWORKS and VALID_SEVERITIES. TECHNIQUE_BUCKETS covers all 4 severity tiers with 3 plausible techniques each. REQUIREMENT_KEYS correctly centralised. No issues.

### technique_resolver.py — PASS
Graph AQL path correct (CVE→has_weakness→CWE→capec_relates_to_cwe→CAPEC→capec_maps_to_attack→ATT&CK). Exception handling falls through to severity bucket without crashing. `resolve_all()` skips non-CVE entities correctly. `_is_graph_resolved()` heuristic correctly distinguishes graph vs fallback by set comparison.

### attack_surface_server.py — PASS
- Probability model: base rates (0.85 KEV / 0.60 non-KEV), modifier stack, `max(0.05, min(0.95, ...))` bounds all correct.
- Phase machine: all 5 transitions (RECON→EXPLOITATION gate on round≥2 + CVEs, EXPLOITATION→LATERAL on exploit success, LATERAL→ESCALATION, ESCALATION→PIVOT) correctly placed in respective action handlers.
- `exploit_attempts` tracking caps repeated-attempt penalty at -0.30.
- Compliance gap validation raises `ValueError` for empty `cve_id` and unknown framework.
- **Nitpick fixed:** SOC blind spot comment clarified (line 305).

### action_logger.py — PASS
New fields (decision_source, decision_reasoning, game_state_snapshot, technique_id, technique_source) appended to JSONL record. Compact game state snapshot prevents bloat. Backwards-compatible (existing readers ignore new fields).

### attacker_simulation.py — PASS
Retry loop: 3 attempts, 0.5×2^n backoff, degradation flag at >20% failure rate. Heuristic fallback is game-state-aware (undetected CVEs preferred, KEV prioritised, phase-gated). Scheduled events fire before LLM decision. `entity_techniques` read from config.
- **Minor:** `technique_source` in payload set as `"graph" if cve_id in entity_techniques else "fallback"` — technically all CVEs in entity_techniques have sources (graph or fallback), so this mis-tags fallback-resolved techniques as "graph". Logging-only issue, no downstream effect on simulation outcomes.

### defender_simulation.py — PASS
Retry + aligned heuristic: escalate CISO before random patching, chain CVEs patched first, CRA deadline respected. CVE selection from chain_steps in parse path fixes H-4. Snapshot taken before decision (F-007). No issues.

### regulator_simulation.py — PASS
Uses constants.py (no circular import). Payload validation delegated to attack_surface_server._action_issue_compliance_finding (single source of truth). ValueError caught at call site and logged. Framework/severity coercion in `_build_payload` handles malformed LLM output.

### config_generator.py — PASS
`entity_techniques` embedded under its own key. Scheduled events now carry `"action": "EXPLOIT_CVE"` field (C-10 fix). Round count mapping unchanged. Config written with `ensure_ascii=False`.

### report_agent.py — PASS
`asyncio.run()` called from synchronous main-process context — correct for the completion phase. Three explainability calls run in `asyncio.gather()` with `return_exceptions=True` so one failure doesn't block others. Action log filtered to significance ≥ 0.6 for context compression. Each LLM call has separate error handling.
- **Nitpick fixed:** Regex changed from `r'\{.*\}'` to `r'\{.*?\}'` (non-greedy) for robustness.

### simulation_manager.py — PASS
`TechniqueResolver` called once in `prepare()` — correct placement. JSONL flush uses line-index key `f"{sim_id}_{i:06d}"` (F-004 fix). All 5 explainability fields written per entry. Status endpoint synthesis only when sim_dir found on disk.

---

## Cross-Cutting Checks

**Subprocess boundary:** Technique resolution, report generation, and writeback all in main process. Subprocess limited to agent loops + JSONL writes. ✓

**Concurrency:** All shared state mutations in AttackSurfaceServer happen within subprocess's single asyncio event loop. `await asyncio.sleep(0)` yield points in all 3 agent loops. ✓

**No CVE ID leakage:** Report agent prompts include explicit instruction to use ATT&CK tactic names, not CVE IDs, in board-safe output. ✓

**Backwards compatibility:** JSONL format extended with new optional fields — existing parsers skip unknowns. Config JSON extended with `entity_techniques` — old subprocess code (fallback) defaults to empty dict. ✓

---

## Gate: PASS
