# Proposed Design — cse-demo-realtime-simulation (v1)

**Status:** Design-ready
**Version:** v2
**Scope:** Large
**Date:** 2026-04-15
**Changes from v1:** C-02 apply_action signature clarified (two params, not three); C-03 adds `compliance_gaps.json` write at subprocess exit; C-04 updated: report_agent reads from file, not from in-memory surface_server (subprocess vs parent process boundary fix)

---

## 1. Current State (As-Is)

### Simulation Engine
- Two agent coroutines: `run_attacker_loop` + `run_defender_loop` + IPC poller via `asyncio.gather()`
- `CyberActionLogger` writes all events to `cyber_actions.jsonl` in a per-run `sim_dir` (subprocess filesystem)
- `AttackSurfaceServer` is the shared in-process state object (mutable, no locks, safe under GIL+asyncio yield)
- After all rounds complete, `simulation_manager.py` calls `report_agent.generate()` then `SimulationWritebackService.run_all(payload)` — bulk ArangoDB write at the end
- Writeback payload `compliance_gaps` is hardcoded to `[]` — no compliance gap data flows through today

### API Layer
- `POST /v1/cse/simulations/create` — starts a simulation as a FastAPI background task
- `GET /v1/cse/simulations/{sim_id}/status` — AQL snapshot of run state + recent high-significance events
- `GET /v1/situation/ciso` + `GET /v1/situation/board` — live Situation Room data
- No SSE endpoint; no Engineering or RegAffairs situation endpoints

### Frontend
- `SimulationLivePanel.tsx` polls status endpoint every 3 seconds via `setInterval`
- `situation/page.tsx`: CISO + Board use live API; **Engineering + RegAffairs use static fixture data**
- `AGENT_TYPE_COLOR` already has `Regulator: "bg-orange-400"` — Regulator persona is pre-wired in UI but no data flows to it

---

## 2. Architecture Direction

### Layer Map (Target)

```
Subprocess (sim_dir)
  run_parallel_cyber_simulation.py
    ├── run_attacker_loop()      ← unchanged
    ├── run_defender_loop()      ← unchanged
    ├── run_regulator_loop()     ← NEW
    └── ipc_handler.poll_commands()

  AttackSurfaceServer             ← Modify: add 5 Regulator actions + compliance_gaps list
  CyberActionLogger               ← unchanged (JSONL file write per action)

Parent process (FastAPI)
  CyberSimulationManager
    ├── prepare() / run()         ← unchanged
    ├── complete()                ← Modify: pass compliance_gaps from surface server to payload
    └── SimulationRegistry        ← NEW: process-level sim_id → sim_dir mapping

  API Endpoints
    ├── POST /v1/cse/simulations/create   ← Modify: register sim_dir in SimulationRegistry
    ├── GET  /v1/cse/simulations/{id}/status    ← unchanged
    ├── GET  /v1/cse/simulations/{id}/stream    ← NEW: SSE, tails cyber_actions.jsonl
    ├── GET  /v1/situation/ciso             ← unchanged
    ├── GET  /v1/situation/board            ← unchanged
    ├── GET  /v1/situation/engineering      ← NEW
    └── GET  /v1/situation/reg_affairs      ← NEW

  SituationAbstractionLayer        ← Modify: add compute_engineering() + compute_reg_affairs()

Frontend
  SimulationLivePanel.tsx          ← Modify: SSE EventSource replaces setInterval polling
  situation/page.tsx               ← Modify: Engineering + RegAffairs call live API
```

### Key Architecture Decisions

**AD-1: SSE uses JSONL file tailing, not ArangoDB polling or in-memory Queue**

- `cyber_actions.jsonl` is written per-action in real time by `CyberActionLogger` (already exists)
- The parent process knows `sim_dir` via `CyberSimulationRunner.sim_dir`
- SSE endpoint reads this file with a byte-offset cursor, sleeping 0.5s between polls
- No subprocess-to-parent IPC change needed; no additional ArangoDB writes per round
- For completed runs (no live file), SSE reads from ArangoDB `agent_action_logs` (populated by writeback)
- Rationale: simplest approach; no cross-process queue; leverages existing infrastructure

**AD-2: SimulationRegistry — process-level dict for sim_dir lookup**

- The SSE endpoint needs `sim_dir` for a given `sim_id`
- The runner object lives inside the background task closure; SSE is a separate request
- Solution: `SimulationRegistry` is a module-level `dict[str, Path]` in `endpoints/cse.py`
- Populated when `POST /create` launches the background task; cleaned up after 1 hour TTL
- Rationale: simplest stateful glue; no Redis/DB needed; acceptable for single-process deployment

**AD-3: Regulator compliance gaps flow through AttackSurfaceServer**

- `ISSUE_COMPLIANCE_FINDING` handler appends to `AttackSurfaceServer.compliance_gaps: list[dict]`
- `report_agent.generate()` has access to `surface_server` and includes `compliance_gaps` in report
- `simulation_manager._build_writeback_payload()` reads `report["compliance_gaps"]` and passes to writeback
- Rationale: avoids adding a separate file/table; Regulator output flows through existing writeback path cleanly

**AD-4: Regulator is a dedicated third coroutine, not embedded in Defender**

- Distinct agent loop `run_regulator_loop()` in `regulator_simulation.py`
- Distinct `agent_type = "Regulator"` in all action logs
- `asyncio.gather()` in `run_parallel_cyber_simulation.py` gets three agent coroutines
- Rationale: demo clarity — viewers see three distinct personas in the live panel

**AD-5: Engineering and RegAffairs endpoints compute on-request from ArangoDB**

- `compute_engineering()`: AQL query on `attack_chain_findings` + `vulnerabilities` (CVSS, EPSS, KEV)
- `compute_reg_affairs()`: AQL query on `compliance_gap_findings` for latest run
- No pre-computation; acceptable latency for demo
- Rationale: avoids new persistent derived collections; leverages existing writeback data

---

## 3. Change Inventory

| # | File | Change Type | Summary |
|---|---|---|---|
| C-01 | `src/complira_graph/cse/regulator_simulation.py` | Add | Regulator agent loop; 5 LLM-driven actions |
| C-02 | `src/complira_graph/cse/attack_surface_server.py` | Modify | Add 5 Regulator action constants + handlers; add `compliance_gaps` list |
| C-03 | `src/complira_graph/cse/run_parallel_cyber_simulation.py` | Modify | Wire `run_regulator_loop` as 3rd coroutine |
| C-04 | `src/complira_graph/cse/report_agent.py` | Modify | Pass `surface_server.compliance_gaps` in report output |
| C-05 | `src/complira_graph/simulation/writeback_service.py` | Modify | Read `compliance_gaps` from report in `_build_writeback_payload` |
| C-06 | `src/api/v1/endpoints/cse.py` | Modify | Add `SimulationRegistry`; add `GET /stream` SSE endpoint |
| C-07 | `src/complira_graph/situation/abstraction_layer.py` | Modify | Add `compute_engineering()` + `compute_reg_affairs()` |
| C-08 | `src/api/v1/endpoints/situation.py` | Modify | Add `/situation/engineering` + `/situation/reg_affairs` routes |
| C-09 | `frontend/components/situation/SimulationLivePanel.tsx` | Modify | Replace `setInterval` with `EventSource` SSE |
| C-10 | `frontend/app/dashboard/situation/page.tsx` | Modify | Wire Engineering + RegAffairs to live API |
| C-11 | `tests/unit/cse/test_regulator_simulation.py` | Add | Unit tests for Regulator agent |
| C-12 | `tests/unit/cse/test_cse_api.py` | Modify | Add SSE streaming test scenario |

---

## 4. Module Specifications

### C-01: `regulator_simulation.py` (Add)

```
Layer: Agent domain (subprocess side)
Responsibility: Regulator agent coroutine — LLM-driven compliance auditor
Inputs: config dict, surface_server, logger, memory, ipc_handler
Outputs: compliance gap entries via surface_server.compliance_gaps
Key API: run_regulator_loop(config, surface_server, logger, memory, ipc_handler) -> None
```

Action set:
- `AUDIT_VULNERABILITY` — checks if exploited CVEs have compliance implications
- `ISSUE_COMPLIANCE_FINDING` — appends to `surface_server.compliance_gaps`
- `FILE_INCIDENT_REPORT` — marks incident report filed
- `NOTIFY_REGULATOR` — marks external regulatory body notified
- `APPROVE_EXCEPTION` — marks a risk exception granted

LLM prompt pattern: mirrors attacker/defender (Haiku model, JSON response, fallback heuristic).

### C-02: `attack_surface_server.py` (Modify)

New state field:
```python
self.compliance_gaps: list[dict] = []   # Regulator audit findings
self.incident_report_filed: bool = False
self.regulator_notified: bool = False
self.exceptions_approved: list[str] = []   # cve_ids with exception
```

New action constants:
```python
AUDIT_VULNERABILITY     = "AUDIT_VULNERABILITY"
ISSUE_COMPLIANCE_FINDING = "ISSUE_COMPLIANCE_FINDING"
FILE_INCIDENT_REPORT    = "FILE_INCIDENT_REPORT"
NOTIFY_REGULATOR        = "NOTIFY_REGULATOR"
APPROVE_EXCEPTION       = "APPROVE_EXCEPTION"
```

New handlers follow same pattern as existing handlers.

**apply_action signature (unchanged)**: `apply_action(action_type: str, params: dict) -> dict`. The `agent_type` ("Regulator") is **not** a parameter of `apply_action` — it is passed only to `CyberActionLogger.log_action()` as a separate call. Regulator calls `apply_action(action_type, params)` exactly like Attacker and Defender.

### C-03: `run_parallel_cyber_simulation.py` (Modify)

```python
await asyncio.gather(
    run_attacker_loop(config, surface_server, logger, memory, ipc_handler),
    run_defender_loop(config, surface_server, logger, memory, ipc_handler),
    run_regulator_loop(config, surface_server, logger, memory, ipc_handler),  # NEW
    ipc_handler.poll_commands(),
)

# After gather completes — serialize compliance_gaps to file for parent process
import json
compliance_gaps_path = sim_dir / "compliance_gaps.json"
with open(compliance_gaps_path, "w") as f:
    json.dump(surface_server.compliance_gaps, f)
```

**Rationale for file-based transfer**: `surface_server` is an in-process object in the subprocess. The parent process (`simulation_manager.py`) calls `report_agent.generate(sim_dir)` after the subprocess exits. The parent has no access to subprocess memory. Writing `compliance_gaps.json` to `sim_dir` is the correct subprocess → parent handoff pattern (consistent with how `run_state.json` is used).

### C-04: `report_agent.py` (Modify)

Add `compliance_gaps` field to report output dict by reading from `compliance_gaps.json` written by the subprocess (C-03):
```python
# In report_agent.generate(sim_dir):
compliance_gaps_path = sim_dir / "compliance_gaps.json"
if compliance_gaps_path.exists():
    with open(compliance_gaps_path) as f:
        report["compliance_gaps"] = json.load(f)
else:
    report["compliance_gaps"] = []
```

**Note**: `report_agent.generate()` already receives `sim_dir` to read other subprocess-side output files (SQLite episodic memory, JSONL logs). No signature change beyond ensuring `sim_dir` is passed. `surface_server` is NOT passed — it is subprocess-only.

### C-05: `simulation_manager.py` (Modify)

In `_build_writeback_payload()`, replace `"compliance_gaps": []` with:
```python
"compliance_gaps": _build_compliance_gaps(report, sim_id, tenant_id),
```

Where `_build_compliance_gaps()` maps `report["compliance_gaps"]` to writeback format:
```python
{
    "gap_key": f"{sim_id}_gap_{i}",
    "requirement_key": gap.get("requirement_key", "unknown"),
    "framework": gap.get("framework", "CRA"),
    "description": gap.get("description", ""),
    "severity": gap.get("severity", "medium"),
}
```

### C-06: `endpoints/cse.py` (Modify)

**SimulationRegistry** (module-level):
```python
_SIM_REGISTRY: dict[str, Path] = {}   # sim_id → sim_dir
```
Populated in the `POST /create` background task wrapper. TTL cleanup via `asyncio.create_task` after 3600s.

**SSE endpoint**:
```
GET /v1/cse/simulations/{sim_id}/stream
Content-Type: text/event-stream

Events emitted:
  data: {"round_no": 3, "agent_type": "Attacker", "action_type": "EXPLOIT_CVE", "outcome": "...", "significance": 0.8}
  data: {"round_no": 3, "agent_type": "Defender", ...}
  data: {"round_no": 3, "agent_type": "Regulator", ...}
  event: done\ndata: {}  (on COMPLETED/FAILED status)
```

SSE polling logic:
1. Look up `sim_dir` from `_SIM_REGISTRY` — if absent, fall back to ArangoDB query for completed run
2. Open `cyber_actions.jsonl`, seek to byte offset (start at 0)
3. Read new lines (JSONL format), emit `data:` events for `type == "action"` entries
4. Sleep 0.5s; repeat until run state file shows `completed` or `failed`
5. Emit `event: done\ndata: {}\n\n`

### C-07: `abstraction_layer.py` (Modify)

**`compute_engineering(tenant_id)`** — returns Engineering persona data:
```
AQL: FOR chain IN attack_chain_findings
       FILTER chain.tenant_id == @tenant_id
       FILTER chain.run_id == @latest_run_id
       FOR cve IN vulnerabilities
         FILTER cve._key == SUBSTITUTE(chain.cve_id, '-', '_')
         LET epss_score = FIRST(FOR e IN has_epss FILTER e._from == CONCAT("vulnerabilities/", cve._key) RETURN e.epss)
         LET in_kev = LENGTH(FOR e IN exploited_in_wild FILTER e._from == CONCAT("vulnerabilities/", cve._key) RETURN 1) > 0
         RETURN {
           cve_id: chain.cve_id,
           cvss3: cve.cvss_v3_score,
           epss: epss_score,
           in_kev: in_kev,
           confidence: chain.confidence
         }
```
Computes composite patch score: `(epss * 40) + (kev ? 30 : 0) + (cvss3 * 3) + (confidence * 27)`.
Returns `PatchPriorityItem[]` matching the fixture schema.

**`compute_reg_affairs(tenant_id)`** — returns RegAffairs persona data:
```
AQL: FOR gap IN compliance_gap_findings
       FILTER gap.tenant_id == @tenant_id
       FILTER gap.run_id == @latest_run_id
       RETURN { framework: gap.framework, description: gap.description, severity: gap.severity }
```
Maps to `RegulatoryDeadline[]` with computed `hours_remaining` (based on framework SLA: CRA=72h, FDA=5days, HIPAA=60days).

### C-08: `endpoints/situation.py` (Modify)

Add two routes:
```
GET /v1/situation/engineering
GET /v1/situation/reg_affairs
```
Both: auth required (JWT/API key); calls `SituationAbstractionLayer(db).compute_engineering(tenant_id)` / `compute_reg_affairs(tenant_id)`.

### C-09: `SimulationLivePanel.tsx` (Modify)

Replace `setInterval` polling with `EventSource`:
```typescript
const es = new EventSource(`${API_URL}/v1/cse/simulations/${simId}/stream`, {
  headers: { Authorization: `Bearer ${token}` }  // via fetch wrapper fallback
});
es.onmessage = (e) => {
  const event = JSON.parse(e.data) as CSEActionEvent;
  setEvents(prev => [event, ...prev].slice(0, 50));
};
es.addEventListener("done", () => {
  es.close();
  // poll status once for final run state
  fetchFinalStatus();
});
```

Note: `EventSource` doesn't support custom headers natively in browser. Workaround: use `@microsoft/fetch-event-source` library (already common in Next.js projects) or add token as a query param `?token=...` (acceptable for demo).

### C-10: `situation/page.tsx` (Modify)

In `useEffect` `fetchLive()`:
```typescript
const [engRes, regRes] = await Promise.all([
  fetch(`${API_URL}/v1/situation/engineering`, { headers }),
  fetch(`${API_URL}/v1/situation/reg_affairs`, { headers }),
]);
if (engRes.ok) setEngineeringData(await engRes.json());
if (regRes.ok) setRegAffairsData(await regRes.json());
```

Engineering + RegAffairs sections use live data when available, fall back to fixture on error.

---

## 5. Naming Decisions

| Name | Rationale |
|---|---|
| `regulator_simulation.py` | Mirrors `attacker_simulation.py` / `defender_simulation.py` naming pattern |
| `run_regulator_loop()` | Mirrors `run_attacker_loop()` / `run_defender_loop()` |
| `SimulationRegistry` | Clear: process-level sim_id → path registry |
| `compute_engineering()` | Mirrors `compute_ciso()` / `compute_board()` naming |
| `compute_reg_affairs()` | Mirrors same pattern; `reg_affairs` matches frontend persona name |
| `AUDIT_VULNERABILITY` | Natural audit verb; consistent ALL_CAPS pattern |
| `ISSUE_COMPLIANCE_FINDING` | Explicit — issues a finding (compliance term) |
| `FILE_INCIDENT_REPORT` | Filing a report is the regulatory act |
| `NOTIFY_REGULATOR` | Direct; mirrors `NOTIFY_BOARD` |
| `APPROVE_EXCEPTION` | Standard risk management term |

### Naming Drift Check

| File | Current Name | Drift? | Action |
|---|---|---|---|
| `run_parallel_cyber_simulation.py` | — | No drift | Keep (adds 3rd coroutine only) |
| `simulation_manager.py` | `_build_writeback_payload` | No drift | Keep |
| `abstraction_layer.py` | `SituationAbstractionLayer` | No drift; adding methods | Keep |
| `endpoints/cse.py` | `cse.py` | No drift | Keep; SSE added inline |

---

## 6. Dependency Flow

```
regulator_simulation.py
  → attack_surface_server.py (reads/writes state)
  → action_logger.py (writes JSONL)
  → memory_updater.py (records episodes)
  → complira_graph.config (Anthropic API key)

run_parallel_cyber_simulation.py
  → run_attacker_loop, run_defender_loop, run_regulator_loop

endpoints/cse.py (SSE)
  → _SIM_REGISTRY (module-level)
  → JSONL file tail (cyber_actions.jsonl in sim_dir)
  → agent_action_logs AQL (fallback for completed runs)

abstraction_layer.py
  → situation_abstraction_queries.py (existing)
  → new inline AQL for engineering + reg_affairs

situation.py (new routes)
  → SituationAbstractionLayer
```

No circular dependencies introduced. All new imports are one-way.

---

## 7. Use Case Coverage Matrix

| use_case_id | Description | Primary | Fallback | Error | Call Stack Section |
|---|---|---|---|---|---|
| UC-01 | Regulator agent runs in simulation | Yes | N/A | Yes | regulator_simulation.run_regulator_loop |
| UC-02 | Three concurrent coroutines | Yes | N/A | Yes | run_parallel_cyber_simulation.main |
| UC-03 | SSE streaming endpoint | Yes | Yes (ArangoDB) | Yes | endpoints/cse.stream |
| UC-04 | Frontend SSE consumption | Yes | Yes (error toast) | Yes | SimulationLivePanel |
| UC-05 | Engineering live endpoint | Yes | N/A | Yes | abstraction_layer.compute_engineering |
| UC-06 | RegAffairs live endpoint | Yes | N/A | Yes | abstraction_layer.compute_reg_affairs |
| UC-07 | Regulator action set | Yes | N/A | N/A | attack_surface_server._ACTION_HANDLERS |
| UC-08 | Full demo end-to-end | Yes | N/A | N/A | All layers |
| UC-09 | SSE closes on COMPLETED | Yes | N/A | N/A | endpoints/cse.stream |
| UC-10 | Regulator concurrency safety | Yes | N/A | N/A | run_parallel_cyber_simulation |
| UC-11 | Empty state graceful return | Yes | N/A | N/A | abstraction_layer |
| UC-12 | SSE backpressure | Yes | N/A | N/A | endpoints/cse.stream |

---

## 8. Error Handling

| Scenario | Handling |
|---|---|
| Regulator LLM call fails | Fallback to `AUDIT_VULNERABILITY` (same pattern as Attacker/Defender) |
| `ISSUE_COMPLIANCE_FINDING` on empty cve_id | Handler appends generic gap with `framework="UNKNOWN"` and logs warning |
| SSE: sim_dir not in registry, run already completed | Fall back to ArangoDB `agent_action_logs` query; emit all, then `event: done` |
| SSE: sim_dir not found, no ArangoDB data | Return 404 |
| Engineering AQL: no simulation run | Return empty `patch_priority: []` with `data_staleness_warning` |
| RegAffairs AQL: no compliance gaps | Return empty `regulatory_deadlines: []` |
| Frontend EventSource auth: token in query param | Accepted for demo; note in code as TODO for production |

---

## 9. Data Models

### Regulator compliance gap (in-memory, surface server)
```python
{
    "requirement_key": str,   # e.g. "CRA_art_24"
    "framework": str,         # "CRA" | "FDA_524B" | "HIPAA" | "NIST_800_53"
    "description": str,
    "severity": str,          # "critical" | "high" | "medium" | "low"
    "round_no": int,
    "cve_id": str | None,
}
```

### SSE event wire format
```
data: {"round_no": 4, "agent_type": "Regulator", "action_type": "ISSUE_COMPLIANCE_FINDING", "outcome": "gap_recorded: CRA Article 24", "significance": 0.8, "timestamp": "2026-04-15T..."}\n\n
```

### Engineering endpoint response
```json
{
  "patch_priority": [
    {
      "rank": 1, "cve_id": "CVE-2024-1234",
      "composite_score": 87.4, "patch_urgency": "IMMEDIATE",
      "cvss3": 9.8, "epss": 0.94, "in_kev": true,
      "active_exploits_in_env": 1, "internet_facing_devices": 2,
      "affected_devices": [], "regulatory_frameworks": ["CRA", "NIST_800_53"],
      "score_breakdown": {"epss_pts": 37, "kev_pts": 30, "exploit_pts": 12, "exposure_pts": 8}
    }
  ]
}
```

### RegAffairs endpoint response
```json
{
  "regulatory_deadlines": [
    {
      "incident_id": "gap_sim123_0",
      "native_id": "sim123",
      "title": "CRA Article 24 — Vulnerability Handling Compliance Gap",
      "regulatory_labels": ["CRA"],
      "sla_deadline": "2026-04-18T...",
      "hours_remaining": 72.0,
      "overdue": false,
      "urgency_tier": "HIGH",
      "linked_jira_key": null
    }
  ]
}
```
