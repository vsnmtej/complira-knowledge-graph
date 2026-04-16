# Implementation Progress — cse-engine-accuracy-explainability

## Delivery Summary

**Branch:** `codex/cse-engine-accuracy-explainability`  
**Commits:** 7 (Stage 3 → Stage 9)  
**Tests:** 146 passed, 0 failed (45 new + 101 pre-existing)  

---

## What Was Built

### Accuracy Fixes (9 critical/high issues resolved)

| Issue | Fix | File(s) |
|-------|-----|---------|
| T1190 hardcoded — zero ATT&CK diversity | `TechniqueResolver` queries CVE→CWE→CAPEC→ATT&CK graph path; severity-bucket fallback | `technique_resolver.py` (new), `config_generator.py`, `attacker_simulation.py` |
| Attacker always wins — exploit always succeeds | Probabilistic model: base 0.85/0.60 ± modifier stack (monitoring, detection, controls, foothold, repeats) | `attack_surface_server.py` |
| Defender actions have no effect | Patched CVEs removed from exploitable set; control deployment adds probability penalty | `attack_surface_server.py` |
| LLM failure → passive fallback | 3-attempt retry with exponential backoff; structured heuristic fallback (game-state-aware, not passive default) | `attacker_simulation.py`, `defender_simulation.py`, `regulator_simulation.py` |
| ArangoDB flush no-op in subprocess | JSONL parsed in main process post-subprocess; batch-upsert with line-index keys to ArangoDB | `simulation_manager.py` |
| No action diversity — 720 rounds of EXPLOIT_CVE | Kill-chain phase machine: RECON→EXPLOITATION→LATERAL→ESCALATION→PIVOT with guards | `attack_surface_server.py`, `attacker_simulation.py` |
| Scheduled events ignored | Auto-fire before LLM decision each round; `action` field added to event schema | `attacker_simulation.py`, `config_generator.py` |
| Detections don't affect attacker | `detected_cves` + `undetected_exploitable` in state snapshot; attacker prompt prefers undetected | `attack_surface_server.py`, `attacker_simulation.py` |
| Compliance gap allows empty cve_id | `_validate_compliance_payload()` raises `ValueError`; caught at call site | `attack_surface_server.py`, `regulator_simulation.py` |

### Explainability (6 new features)

| Feature | What it produces | Where stored |
|---------|-----------------|--------------|
| Per-chain narrative | Entry point reasoning, technique used, defender response, SOC blind spot explanation, single countermeasure | `attack_chain_findings.explanation` |
| Decision trace | `decision_source` (llm/heuristic/scheduled), `decision_reasoning`, `game_state_snapshot` per action | `agent_action_logs` + JSONL |
| Counterfactuals | What specific intervention (patch/monitoring/control/notification) would have broken each chain, with rounds available | `simulation_runs.counterfactuals` |
| CISO explanations | Per-category: driving events, turning point round, effective defender actions, what would have helped | `/v1/situation/ciso` (pending C-19) |
| Board derivation | Plain-English explanation of financial exposure calculation, contributing chains, investment recommendation | `/v1/situation/board` (pending C-20) |
| Audit trail | Chronological regulatory timeline: event type, regulatory obligation, outcome (met/missed) | `simulation_runs.audit_trail` |

### New Files
- `src/complira_graph/cse/constants.py` — shared constants, no circular imports
- `src/complira_graph/cse/technique_resolver.py` — graph-path + fallback technique resolution
- `tests/unit/cse/test_cse_accuracy_explainability.py` — 45 AC tests

### Modified Files (10)
`attack_surface_server.py`, `action_logger.py`, `attacker_simulation.py`, `defender_simulation.py`, `regulator_simulation.py`, `config_generator.py`, `report_agent.py`, `simulation_manager.py`, `src/api/v1/endpoints/cse.py`, `docs/API_DOCUMENTATION.md`

---

## Deferred Items (in-scope but not blocking)

| ID | Item | Reason |
|----|------|--------|
| C-19 | `threat_category_explanations` in CISO situation view | Requires `ThreatCategoryExplanation` model addition to `situation/models.py` + new AQL; low-risk deferral |
| C-20 | `exposure_derivation` in Board situation view | Same model extension; pairs naturally with C-19 |

Both C-19 and C-20 are non-breaking additions (optional response fields). The explainability data they read (`chain_narratives`, `counterfactuals`) is now being written to ArangoDB, so they can be wired in as a small follow-on ticket.

---

## Stage Gate Results

| Stage | Result |
|-------|--------|
| 0–2 | Pass — 25-issue audit, requirements Design-ready |
| 3 | Pass — proposed-design.md v1: 5 ADs, component designs |
| 4 | Pass — 16 use cases covering all 20 change items |
| 5 | **Go Confirmed** after 3 rounds (7 findings caught pre-code) |
| 6 | Pass — 13 files changed, 2 new modules, 146 tests |
| 7 | Pass — 45 new AC tests, 146 total, 0 failed |
| 8 | Pass — 0 Blockers, 0 Majors, 2 nitpicks fixed |
| 9 | Pass — API docs updated for all changed endpoints |
| 10 | In Progress |
