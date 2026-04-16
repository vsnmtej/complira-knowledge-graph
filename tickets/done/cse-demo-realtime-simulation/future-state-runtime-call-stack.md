# Future-State Runtime Call Stacks — cse-demo-realtime-simulation

## Design Basis

- Scope Classification: `Large`
- Call Stack Version: `v2`
- Changes from v1: F-001 fix — UC-01 subprocess exit writes compliance_gaps.json; UC-02 exit step updated; UC-08 writeback chain updated. F-002 fix — UC-01 and UC-07 apply_action() call corrected to two-parameter signature.
- Requirements: `tickets/in-progress/cse-demo-realtime-simulation/requirements.md` (status `Design-ready`)
- Source Artifact: `tickets/in-progress/cse-demo-realtime-simulation/proposed-design.md`
- Source Design Version: `v1`
- Referenced Sections: §2 Architecture Direction, §3 Change Inventory, §4 Module Specifications, §9 Data Models

---

## Future-State Modeling Rule

All call stacks model the **target (to-be)** design behavior, not current code. Where current code diverges, target behavior is shown and migration notes are in the Transition Notes section.

---

## Use Case Index

| use_case_id | Source Type | Requirement ID(s) | Design-Risk Objective | Use Case Name | Coverage Target |
|---|---|---|---|---|---|
| UC-01 | Requirement | UC-01, UC-07 | N/A | Regulator agent runs in simulation | Primary/N/A/Yes |
| UC-02 | Requirement | UC-02 | N/A | Three concurrent coroutines orchestrated | Primary/N/A/Yes |
| UC-03 | Requirement | UC-03, UC-09 | N/A | SSE streaming endpoint emits round events | Primary/Yes/Yes |
| UC-04 | Requirement | UC-04 | N/A | Frontend SSE consumption and rendering | Primary/Yes/Yes |
| UC-05 | Requirement | UC-05 | N/A | Engineering live patch-priority endpoint | Primary/N/A/Yes |
| UC-06 | Requirement | UC-06 | N/A | RegAffairs live regulatory deadlines endpoint | Primary/N/A/Yes |
| UC-07 | Requirement | UC-07 | N/A | Regulator action handlers in AttackSurfaceServer | Primary/N/A/N/A |
| UC-08 | Requirement | UC-08 | N/A | Full demo end-to-end: trigger → stream → Situation Room | Primary/N/A/N/A |
| UC-09 | Design-Risk | UC-09 | SSE stream must close cleanly when run status = COMPLETED/FAILED | SSE terminal event and clean shutdown | Primary/N/A/Yes |
| UC-10 | Design-Risk | UC-10 | Three concurrent coroutines share AttackSurfaceServer mutable state without locking | Regulator concurrency safety under asyncio | Primary/N/A/N/A |
| UC-11 | Design-Risk | UC-11 | Engineering/RegAffairs endpoints called before any simulation has run | Empty-state graceful response | Primary/N/A/N/A |
| UC-12 | Design-Risk | UC-12 | Slow SSE client should not block agent coroutine loop in subprocess | SSE backpressure isolation | Primary/N/A/N/A |

---

## Transition Notes

- `run_parallel_cyber_simulation.py` currently has 2 agent coroutines (`asyncio.gather` with attacker + defender + ipc). Target adds `run_regulator_loop()` as a third coroutine — minimal diff, no other callers change.
- `CyberActionLogger` currently writes only to `cyber_actions.jsonl`. No subprocess-side changes needed for SSE — the parent process tails the file.
- `SimulationRegistry` does not exist yet. It is a new module-level dict in `endpoints/cse.py`. The `POST /create` handler must register `sim_dir` into it at task launch.
- `_build_writeback_payload()` in `simulation_manager.py` currently sets `"compliance_gaps": []`. Target replaces that with `_build_compliance_gaps(report, sim_id, tenant_id)`.
- `SituationAbstractionLayer` currently has `compute_ciso()` and `compute_board()`. Target adds `compute_engineering()` and `compute_reg_affairs()`.
- `situation/page.tsx` currently hard-codes fixture data for Engineering and RegAffairs. Target replaces with live API calls with fixture fallback.
- `SimulationLivePanel.tsx` currently polls every 3 seconds via `setInterval`. Target replaces with `EventSource` (SSE).

---

## Use Case: UC-01 — Regulator Agent Runs In Simulation

### Goal

A dedicated Regulator coroutine runs during the simulation, performing LLM-driven compliance audit actions and writing gap findings to the shared `AttackSurfaceServer.compliance_gaps` list.

### Preconditions

- `AttackSurfaceServer` initialized with `compliance_gaps = []` (C-02)
- `CyberActionLogger` and `CyberMemoryUpdater` instances are initialized
- `config` dict contains Anthropic API key and game config (rounds, tenant, etc.)

### Expected Outcome

- `run_regulator_loop()` executes for `config["num_rounds"]` rounds without error
- At least one of `AUDIT_VULNERABILITY`, `ISSUE_COMPLIANCE_FINDING`, `FILE_INCIDENT_REPORT`, `NOTIFY_REGULATOR`, `APPROVE_EXCEPTION` is called per round
- `cyber_actions.jsonl` has entries with `agent_type = "Regulator"` for each round
- `surface_server.compliance_gaps` contains at least one entry if `ISSUE_COMPLIANCE_FINDING` was called

### Primary Runtime Call Stack

```text
[ENTRY] src/complira_graph/cse/run_parallel_cyber_simulation.py:main()
└── asyncio.gather(
      run_attacker_loop(...),
      run_defender_loop(...),
      run_regulator_loop(config, surface_server, logger, memory, ipc_handler),  # new
      ipc_handler.poll_commands()
    ) [ASYNC]

  src/complira_graph/cse/regulator_simulation.py:run_regulator_loop(config, surface_server, logger, memory, ipc_handler)
  ├── for round_no in range(config["num_rounds"]):
  │   ├── src/complira_graph/cse/regulator_simulation.py:_build_regulator_prompt(config, surface_server, round_no)
  │   │   └── returns prompt str incorporating surface_server.chain_steps, patched_cves, cra_notified
  │   │
  │   ├── [ASYNC] anthropic.AsyncAnthropic().messages.create(model="claude-haiku-...", ...)
  │   │   # LLM chooses action from: AUDIT_VULNERABILITY, ISSUE_COMPLIANCE_FINDING,
  │   │   # FILE_INCIDENT_REPORT, NOTIFY_REGULATOR, APPROVE_EXCEPTION
  │   │
  │   ├── src/complira_graph/cse/regulator_simulation.py:_parse_regulator_response(content)
  │   │   # extracts action_type, target_cve_id, description, framework, severity
  │   │   # fallback heuristic: returns AUDIT_VULNERABILITY if JSON parse fails
  │   │
  │   ├── src/complira_graph/cse/attack_surface_server.py:apply_action(action_type, params)
  │   │   # two-param signature: same as Attacker/Defender callers
  │   │   # dispatches to _ACTION_HANDLERS[action_type]
  │   │   └── [STATE] handler mutates surface_server fields (see UC-07 for handler details)
  │   │
  │   ├── src/complira_graph/cse/action_logger.py:CyberActionLogger.log_action(
  │   │     round_no, "Regulator", action_type, outcome, significance
  │   │   ) [IO]
  │   │   └── appends JSON line to cyber_actions.jsonl in sim_dir
  │   │
  │   ├── src/complira_graph/cse/memory_updater.py:CyberMemoryUpdater.record_episode(
  │   │     round_no, "Regulator", action_type, outcome
  │   │   ) [IO]
  │   │   └── writes to SQLite episodic memory in sim_dir
  │   │
  │   └── asyncio.sleep(0)   # yield to event loop; allows Attacker/Defender to run [ASYNC]
  │
  └── return  # coroutine completes after all rounds
      # NOTE: compliance_gaps.json is written by run_parallel_cyber_simulation.py
      # AFTER asyncio.gather() returns — not inside this coroutine (see UC-02)
```

### Branching / Fallback Paths

```text
[FALLBACK] LLM JSON parse failure in _parse_regulator_response()
src/complira_graph/cse/regulator_simulation.py:_parse_regulator_response(content)
├── json.loads(content) raises ValueError
└── returns {"action_type": "AUDIT_VULNERABILITY", "description": "fallback", ...}
    # same fallback pattern as attacker/defender
```

### State And Data Transformations

- LLM response str → parsed dict (action_type, framework, cve_id, description, severity)
- `apply_action()` → `AttackSurfaceServer` field mutation (varies by handler)
- `log_action()` → JSONL line appended to `cyber_actions.jsonl`

### Observability And Debug Points

- Each round: JSONL entry written with `agent_type="Regulator"`, `round_no`, `action_type`, `outcome`
- Fallback heuristic: logged at WARNING level if triggered

### Design Smells / Gaps

- Any legacy/backward-compatibility branch present? No
- Any naming-to-responsibility drift detected? No — `regulator_simulation.py` / `run_regulator_loop()` exactly mirrors attacker/defender naming

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `Covered` (LLM fallback heuristic)

---

## Use Case: UC-02 — Three Concurrent Coroutines Orchestrated

### Goal

`run_parallel_cyber_simulation.py` runs Attacker, Defender, and Regulator as three concurrent asyncio coroutines plus the IPC poller, ensuring all complete normally for the configured number of rounds.

### Preconditions

- All agent modules importable (`attacker_simulation`, `defender_simulation`, `regulator_simulation`)
- `AttackSurfaceServer`, `CyberActionLogger`, `CyberMemoryUpdater`, `IPCHandler` initialized
- `config["num_rounds"]` is a positive integer

### Expected Outcome

- `asyncio.gather()` completes without raising
- `run_state.json` written to `sim_dir` with `status = "completed"`
- `cyber_actions.jsonl` contains entries from all three agents

### Primary Runtime Call Stack

```text
[ENTRY] src/complira_graph/cse/run_parallel_cyber_simulation.py:main()
├── parse_args() → args (sim_id, config_path, sim_dir, ...)
├── load config from config_path [IO]
├── init AttackSurfaceServer(config) [STATE]
├── init CyberActionLogger(sim_dir) [IO]
├── init CyberMemoryUpdater(sim_dir) [IO]
├── init IPCHandler(ipc_socket_path)
│
├── logger.log_action("simulation_start", ...) [IO]
│
├── [ASYNC] asyncio.gather(
│     run_attacker_loop(config, surface_server, logger, memory, ipc_handler),
│     run_defender_loop(config, surface_server, logger, memory, ipc_handler),
│     run_regulator_loop(config, surface_server, logger, memory, ipc_handler),  # NEW
│     ipc_handler.poll_commands(),
│   )
│   # All 3 coroutines yield via asyncio.sleep(0) each round
│   # GIL + single event loop ensures only one runs at a time → no locking needed
│
├── [IO] write compliance_gaps.json to sim_dir
│   │   # serialize surface_server.compliance_gaps (list of dicts from ISSUE_COMPLIANCE_FINDING calls)
│   │   # parent process reads this file; subprocess has no shared memory with parent
│   └── json.dump(surface_server.compliance_gaps, open(sim_dir/"compliance_gaps.json", "w"))
└── write run_state.json {"status": "completed", "rounds": N} to sim_dir [IO]
```

### Branching / Fallback Paths

```text
[ERROR] asyncio.gather() raises (one coroutine throws unhandled exception)
src/complira_graph/cse/run_parallel_cyber_simulation.py:main()
└── except Exception as e:
    ├── write compliance_gaps.json (partial — whatever was collected before error) [IO]
    └── write run_state.json {"status": "failed", "error": str(e)} to sim_dir [IO]
```

### State And Data Transformations

- `AttackSurfaceServer` starts empty; mutated by all 3 coroutines over N rounds
- `cyber_actions.jsonl`: sequential appends from all 3 agents (interleaved by asyncio schedule)
- Final `run_state.json` records terminal status

### Observability And Debug Points

- `simulation_start` log entry in JSONL
- `round_start` log entry per round (written by whichever coroutine logs it first)
- `run_state.json` terminal state on completion or failure

### Design Smells / Gaps

- Any legacy/backward-compatibility branch present? No
- Any naming-to-responsibility drift detected? No

### Open Questions

- `ipc_handler.poll_commands()` must not block; it already uses asyncio-safe socket reads. No change needed.

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `Covered` (exception → `failed` status)

---

## Use Case: UC-03 — SSE Streaming Endpoint Emits Round Events

### Goal

`GET /v1/cse/simulations/{sim_id}/stream` returns a `text/event-stream` response that tails `cyber_actions.jsonl` and emits each agent action in real time as a JSON SSE event while the simulation is running.

### Preconditions

- Simulation started via `POST /v1/cse/simulations/create`
- `sim_id` registered in `_SIM_REGISTRY` with its `sim_dir`
- `cyber_actions.jsonl` exists and is being written by the subprocess

### Expected Outcome

- Response has `Content-Type: text/event-stream`
- Client receives `data:` events for each action with `round_no`, `agent_type`, `action_type`, `outcome`, `significance`
- After simulation completes, client receives `event: done\ndata: {}\n\n`

### Primary Runtime Call Stack

```text
[ENTRY] src/api/v1/endpoints/cse.py:stream_simulation(sim_id, request, db)
├── sim_dir = _SIM_REGISTRY.get(sim_id)   # O(1) dict lookup
│
├── [if sim_dir found (live run)]
│   └── return StreamingResponse(
│           _stream_from_jsonl(sim_id, sim_dir),
│           media_type="text/event-stream"
│         )
│
└── [if sim_dir not found (completed/not-started run)] → [FALLBACK]

  src/api/v1/endpoints/cse.py:_stream_from_jsonl(sim_id, sim_dir) [async generator]
  ├── jsonl_path = sim_dir / "cyber_actions.jsonl"
  ├── byte_offset = 0
  ├── while True:
  │   ├── [IO] open(jsonl_path, "rb"), seek(byte_offset)
  │   ├── read new bytes since last poll
  │   ├── for each complete newline-terminated JSON line:
  │   │   ├── parsed = json.loads(line)
  │   │   ├── [if parsed["type"] == "action"]
  │   │   │   └── yield f'data: {json.dumps(event_payload)}\n\n'
  │   │   │       # event_payload = {round_no, agent_type, action_type, outcome, significance, timestamp}
  │   │   └── byte_offset += len(line_bytes)
  │   │
  │   ├── [IO] run_state = read_run_state_json(sim_dir)
  │   ├── [if run_state["status"] in ("completed", "failed")]
  │   │   ├── yield 'event: done\ndata: {}\n\n'
  │   │   └── return  # generator exits; StreamingResponse closes
  │   │
  │   └── [ASYNC] await asyncio.sleep(0.5)   # poll interval
```

### Branching / Fallback Paths

```text
[FALLBACK] sim_dir not in _SIM_REGISTRY (run already completed before client connected)
src/api/v1/endpoints/cse.py:stream_simulation(sim_id, ...)
├── [IO] AQL: FOR e IN agent_action_logs FILTER e.sim_id == @sim_id
│         SORT e._key ASC RETURN e
│         # reads all stored events from writeback collection
├── for each event: yield f'data: {json.dumps(event_payload)}\n\n'
└── yield 'event: done\ndata: {}\n\n'
    # All events delivered synchronously then stream closes
```

```text
[ERROR] sim_id not in registry AND no ArangoDB records found
src/api/v1/endpoints/cse.py:stream_simulation(sim_id, ...)
└── raise HTTPException(status_code=404, detail="Simulation not found")
```

### State And Data Transformations

- `cyber_actions.jsonl` line → filtered by `type == "action"` → SSE `data:` event JSON
- `run_state.json` status → terminal `event: done` trigger

### Observability And Debug Points

- Each emitted SSE event is derived from a JSONL line; no additional logging needed
- 404 on missing sim_id is logged at WARNING

### Design Smells / Gaps

- Any legacy/backward-compatibility branch present? No
- Any naming-to-responsibility drift detected? No

### Open Questions

- `read_run_state_json()` is a small helper that reads `run_state.json` in `sim_dir`. It should be a private function in `cse.py`, not a separate module.

### Coverage Status

- Primary Path: `Covered` (live JSONL tailing)
- Fallback Path: `Covered` (ArangoDB fallback for completed runs)
- Error Path: `Covered` (404 for unknown sim_id)

---

## Use Case: UC-04 — Frontend SSE Consumption And Rendering

### Goal

`SimulationLivePanel.tsx` connects to the SSE stream endpoint via `EventSource`, receives action events round-by-round, and renders them grouped by agent persona (Attacker/Defender/Regulator) with correct color coding.

### Preconditions

- Simulation started; `sim_id` known to frontend
- SSE endpoint is live at `/v1/cse/simulations/{sim_id}/stream`
- Auth token available in frontend session

### Expected Outcome

- Events appear in the panel as they are emitted (no page reload)
- Attacker events shown in red, Defender in blue, Regulator in orange (per existing `AGENT_TYPE_COLOR`)
- On `event: done`, panel transitions to "Completed" state and fetches final status snapshot

### Primary Runtime Call Stack

```text
[ENTRY] frontend/components/situation/SimulationLivePanel.tsx:SimulationLivePanel({simId})
│
├── [STATE] useState: events = [], status = "running"
│
├── useEffect([simId]):
│   ├── const streamUrl = `${API_URL}/v1/cse/simulations/${simId}/stream?token=${token}`
│   │   # token as query param (acceptable for demo; TODO: upgrade to fetch-event-source)
│   │
│   ├── [ASYNC] const es = new EventSource(streamUrl)
│   │
│   ├── es.onmessage = (e) => {
│   │   ├── const event = JSON.parse(e.data) as CSEActionEvent
│   │   └── [STATE] setEvents(prev => [event, ...prev].slice(0, 50))
│   │       # newest events at top; cap at 50 for UI performance
│   │   }
│   │
│   ├── es.addEventListener("done", () => {
│   │   ├── es.close()
│   │   └── [ASYNC] fetchFinalStatus(simId)
│   │       └── GET /v1/cse/simulations/{simId}/status
│   │           └── [STATE] setStatus("completed"); onComplete(simId)
│   │   })
│   │
│   └── return () => es.close()  # cleanup on unmount
│
└── render:
    ├── for each event in events:
    │   ├── agentColor = AGENT_TYPE_COLOR[event.agent_type]   # Attacker/Defender/Regulator
    │   └── <EventRow color={agentColor} event={event} />
    └── [if status == "completed"] <CompletedBanner />
```

### Branching / Fallback Paths

```text
[FALLBACK] EventSource connection error (network, auth failure)
es.onerror = (err) => {
  es.close()
  [STATE] setStatus("error")
  renderErrorToast("Stream connection failed — simulation may still be running")
}
```

### State And Data Transformations

- SSE `data:` JSON string → `CSEActionEvent` typed object → prepended to `events` array
- `event: done` → `fetchFinalStatus()` → status set to `"completed"`

### Design Smells / Gaps

- Any legacy/backward-compatibility branch present? No (`setInterval` removed entirely)
- Any naming-to-responsibility drift detected? No

### Open Questions

- `EventSource` doesn't support custom `Authorization` headers. Query param token is acceptable for demo. For production, `@microsoft/fetch-event-source` or session cookies would replace this.

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `Covered` (error toast)
- Error Path: `Covered` (connection error handler)

---

## Use Case: UC-05 — Engineering Live Patch-Priority Endpoint

### Goal

`GET /v1/situation/engineering` returns a ranked list of CVE patch priorities derived from the latest simulation's `attack_chain_findings` joined with vulnerability CVSS/EPSS/KEV data from ArangoDB.

### Preconditions

- At least one simulation has completed and been written back by `SimulationWritebackService`
- `attack_chain_findings` collection populated with `tenant_id`, `run_id`, `cve_id`, `confidence`
- `vulnerabilities`, `has_epss`, `exploited_in_wild` collections available in reference graph

### Expected Outcome

- Response: `{"patch_priority": [...]}`  where each entry has `cve_id`, `composite_score`, `patch_urgency`
- Items ordered by `composite_score` descending (rank 1 = most urgent)
- 200 with empty `patch_priority: []` if no simulation has run (no 404/500)

### Primary Runtime Call Stack

```text
[ENTRY] src/api/v1/endpoints/situation.py:get_engineering(request, db)
├── tenant_id = extract_tenant_id(request)   # from JWT / API key
│
├── src/complira_graph/situation/abstraction_layer.py:SituationAbstractionLayer(db).compute_engineering(tenant_id)
│   │
│   ├── [IO] AQL: FOR run IN simulation_runs
│   │         FILTER run.tenant_id == @tenant_id
│   │         SORT run.created_at DESC LIMIT 1
│   │         RETURN run._key
│   │         → latest_run_id (or None)
│   │
│   ├── [if no run found] → return {"patch_priority": []}  # UC-11 empty-state path
│   │
│   ├── [IO] AQL: FOR chain IN attack_chain_findings
│   │         FILTER chain.tenant_id == @tenant_id
│   │         FILTER chain.run_id == @latest_run_id
│   │         FOR vuln IN vulnerabilities
│   │           FILTER vuln._key == SUBSTITUTE(chain.cve_id, '-', '_', 2)
│   │           LET epss = FIRST(FOR e IN has_epss
│   │                         FILTER e._from == CONCAT("vulnerabilities/", vuln._key)
│   │                         RETURN e.epss)
│   │           LET in_kev = LENGTH(FOR e IN exploited_in_wild
│   │                           FILTER e._from == CONCAT("vulnerabilities/", vuln._key)
│   │                           RETURN 1) > 0
│   │           RETURN {cve_id: chain.cve_id, cvss3: vuln.cvss_v3_score,
│   │                   epss: epss, in_kev: in_kev, confidence: chain.confidence}
│   │
│   ├── for each row: compute composite_score = (epss * 40) + (kev ? 30 : 0) + (cvss3 * 3) + (confidence * 27)
│   │   [STATE] classify patch_urgency: score >= 80 → "IMMEDIATE", >= 60 → "HIGH", >= 40 → "MEDIUM", else "LOW"
│   │
│   ├── sort by composite_score DESC, assign rank
│   └── return {"patch_priority": [PatchPriorityItem, ...]}
│
└── return JSONResponse({"patch_priority": [...]})
```

### Branching / Fallback Paths

No fallback required. Empty-state path returns `{"patch_priority": []}` with `data_staleness_warning: "no simulation run found"` (see UC-11).

### State And Data Transformations

- ArangoDB rows (attack_chain_findings + vulnerabilities + has_epss + exploited_in_wild)
  → computed composite_score + urgency tier
  → sorted ranked `PatchPriorityItem[]`

### Observability And Debug Points

- AQL query logged at DEBUG with `tenant_id`, `run_id`
- Total items returned logged at INFO

### Design Smells / Gaps

- Any legacy/backward-compatibility branch present? No
- Any naming-to-responsibility drift detected? No — `compute_engineering()` mirrors `compute_ciso()` naming

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `Covered` (empty-state return in UC-11)

---

## Use Case: UC-06 — RegAffairs Live Regulatory Deadlines Endpoint

### Goal

`GET /v1/situation/reg_affairs` returns a list of regulatory deadline items derived from `compliance_gap_findings` written by the Regulator agent during the latest simulation run.

### Preconditions

- Regulator agent has run and `ISSUE_COMPLIANCE_FINDING` was called at least once
- `SimulationWritebackService` has completed and written `compliance_gap_findings` records
- `compliance_gap_findings` collection populated with `tenant_id`, `run_id`, `framework`, `description`, `severity`

### Expected Outcome

- Response: `{"regulatory_deadlines": [...]}`
- Each item has `title`, `regulatory_labels`, `hours_remaining`, `urgency_tier`
- Empty list if no gaps were issued

### Primary Runtime Call Stack

```text
[ENTRY] src/api/v1/endpoints/situation.py:get_reg_affairs(request, db)
├── tenant_id = extract_tenant_id(request)
│
├── src/complira_graph/situation/abstraction_layer.py:SituationAbstractionLayer(db).compute_reg_affairs(tenant_id)
│   │
│   ├── [IO] AQL: RETURN latest_run_id for tenant_id (same query as compute_engineering)
│   │
│   ├── [if no run] → return {"regulatory_deadlines": []}
│   │
│   ├── [IO] AQL: FOR gap IN compliance_gap_findings
│   │         FILTER gap.tenant_id == @tenant_id
│   │         FILTER gap.run_id == @latest_run_id
│   │         RETURN {framework: gap.framework, description: gap.description,
│   │                  severity: gap.severity, created_at: gap.created_at}
│   │
│   ├── for each gap:
│   │   ├── sla_hours = SLA_MAP[gap["framework"]]   # CRA=72, FDA_524B=120, HIPAA=1440, NIST_800_53=168
│   │   ├── hours_remaining = sla_hours - elapsed_hours_since(gap["created_at"])
│   │   ├── urgency_tier = "OVERDUE" if hours_remaining <= 0
│   │   │                  else "HIGH" if hours_remaining <= 24
│   │   │                  else "MEDIUM" if hours_remaining <= 72
│   │   │                  else "LOW"
│   │   └── build RegulatoryDeadlineItem {...}
│   │
│   └── return {"regulatory_deadlines": [RegulatoryDeadlineItem, ...]}
│
└── return JSONResponse({"regulatory_deadlines": [...]})
```

### Branching / Fallback Paths

Empty-state path covered in UC-11.

### State And Data Transformations

- `compliance_gap_findings` AQL rows → framework SLA mapping → `hours_remaining` + `urgency_tier`
- Output schema matches fixture schema exactly (for frontend compatibility)

### Design Smells / Gaps

- Any legacy/backward-compatibility branch present? No
- Any naming-to-responsibility drift detected? No

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `Covered` (empty-state in UC-11)

---

## Use Case: UC-07 — Regulator Action Handlers In AttackSurfaceServer

### Goal

`AttackSurfaceServer.apply_action()` correctly handles all 5 Regulator action types by dispatching to dedicated handler functions that mutate appropriate state fields.

### Preconditions

- `AttackSurfaceServer` initialized with new fields: `compliance_gaps = []`, `incident_report_filed = False`, `regulator_notified = False`, `exceptions_approved = []`
- Action constants defined: `AUDIT_VULNERABILITY`, `ISSUE_COMPLIANCE_FINDING`, `FILE_INCIDENT_REPORT`, `NOTIFY_REGULATOR`, `APPROVE_EXCEPTION`

### Expected Outcome

- `apply_action("Regulator", "AUDIT_VULNERABILITY", {...})` returns outcome dict
- `apply_action("Regulator", "ISSUE_COMPLIANCE_FINDING", {...})` appends to `self.compliance_gaps`
- `apply_action("Regulator", "FILE_INCIDENT_REPORT", {...})` sets `self.incident_report_filed = True`
- `apply_action("Regulator", "NOTIFY_REGULATOR", {...})` sets `self.regulator_notified = True`
- `apply_action("Regulator", "APPROVE_EXCEPTION", {cve_id: ...})` appends to `self.exceptions_approved`

### Primary Runtime Call Stack

```text
src/complira_graph/cse/attack_surface_server.py:AttackSurfaceServer.apply_action(action_type, params)
# Two-parameter signature — unchanged from existing callers (Attacker/Defender use same)
# agent_type is logged by CyberActionLogger separately, not passed to apply_action
├── handler = self._ACTION_HANDLERS.get(action_type)
├── [if handler is None] → return {"outcome": "unknown_action", "significance": 0.0}
└── handler(self, params) → outcome dict

  # Handler: AUDIT_VULNERABILITY
  _handle_audit_vulnerability(self, params):
  ├── cve_id = params.get("cve_id")
  ├── is_exploited = cve_id in [step.get("cve_id") for step in self.chain_steps]
  └── return {"outcome": f"audit_complete: {cve_id} {'exploited' if is_exploited else 'clean'}", "significance": 0.6}

  # Handler: ISSUE_COMPLIANCE_FINDING
  _handle_issue_compliance_finding(self, params):
  ├── gap = {
  │     "requirement_key": params.get("requirement_key", "unknown"),
  │     "framework": params.get("framework", "CRA"),
  │     "description": params.get("description", ""),
  │     "severity": params.get("severity", "medium"),
  │     "round_no": params.get("round_no", 0),
  │     "cve_id": params.get("cve_id"),
  │   }
  ├── [STATE] self.compliance_gaps.append(gap)
  └── return {"outcome": f"gap_recorded: {gap['framework']} {gap['requirement_key']}", "significance": 0.8}

  # Handler: FILE_INCIDENT_REPORT
  _handle_file_incident_report(self, params):
  ├── [STATE] self.incident_report_filed = True
  └── return {"outcome": "incident_report_filed", "significance": 0.9}

  # Handler: NOTIFY_REGULATOR
  _handle_notify_regulator(self, params):
  ├── [STATE] self.regulator_notified = True
  └── return {"outcome": "regulator_notified", "significance": 0.9}

  # Handler: APPROVE_EXCEPTION
  _handle_approve_exception(self, params):
  ├── cve_id = params.get("cve_id", "")
  ├── [STATE] self.exceptions_approved.append(cve_id)
  └── return {"outcome": f"exception_approved: {cve_id}", "significance": 0.5}
```

### State And Data Transformations

- `params` dict from Regulator LLM response → handler-specific field mutations on `AttackSurfaceServer`
- `compliance_gaps` list grows with each `ISSUE_COMPLIANCE_FINDING` call
- All mutations are pure list appends or bool sets — safe under single asyncio thread

### Design Smells / Gaps

- Any legacy/backward-compatibility branch present? No
- Any naming-to-responsibility drift detected? No

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `N/A` (unknown action returns neutral outcome dict — consistent with existing pattern)

---

## Use Case: UC-08 — Full Demo End-To-End

### Goal

A user triggers a simulation run, watches all three agent personas stream actions in real time via the frontend, and then sees the Situation Room updated across all four personas (CISO, Board, Engineering, RegAffairs) from live simulation data.

### Preconditions

- Frontend is loaded and user is authenticated
- At least one scan has been ingested (provides CVE/finding data for `attack_chain_findings`)
- Backend is running; ArangoDB available

### Expected Outcome

- Simulation completes all rounds
- Situation Room shows non-empty data for all 4 personas from the completed run

### Primary Runtime Call Stack

```text
[ENTRY] frontend/app/dashboard/simulation/page.tsx:SimulationPage
├── Step 1: user selects scenario and clicks "Start Simulation"
│   └── [ASYNC] POST /v1/cse/simulations/create {tenant_id, config}
│       ├── src/api/v1/endpoints/cse.py:create_simulation(body, background_tasks, db)
│       ├── [STATE] sim_id = uuid4()
│       ├── [STATE] _SIM_REGISTRY[sim_id] = runner.sim_dir   # register for SSE
│       ├── background_tasks.add_task(_run_simulation_task, sim_id, runner, db)
│       └── return {"sim_id": sim_id}
│
├── Step 2: frontend starts SSE stream
│   └── frontend/components/situation/SimulationLivePanel.tsx
│       └── new EventSource(`/v1/cse/simulations/${simId}/stream?token=...`)
│           └── src/api/v1/endpoints/cse.py:stream_simulation(sim_id)
│               └── _stream_from_jsonl(sim_id, sim_dir)  # tails cyber_actions.jsonl
│
├── Step 3: subprocess runs 3 coroutines (UC-02 / UC-01)
│   └── src/complira_graph/cse/run_parallel_cyber_simulation.py:main()
│       ├── run_attacker_loop → writes to cyber_actions.jsonl
│       ├── run_defender_loop → writes to cyber_actions.jsonl
│       └── run_regulator_loop → writes to cyber_actions.jsonl + surface_server.compliance_gaps
│
├── Step 4: SSE emits events as JSONL is written (UC-03)
│   └── Frontend renders Attacker/Defender/Regulator events in SimulationLivePanel (UC-04)
│
├── Step 5: subprocess completes all rounds → writes run_state.json "completed"
│   └── SSE generator detects "completed" → emits "event: done" → frontend closes EventSource
│
├── Step 6: parent process completes _run_simulation_task
│   ├── src/complira_graph/cse/simulation_manager.py:CyberSimulationManager.complete()
│   │   ├── [IO] report_agent.generate(sim_dir) → reads compliance_gaps.json from sim_dir
│   │   │       → report dict includes compliance_gaps (C-04 file-based read)
│   │   ├── _build_writeback_payload(report) → payload with compliance_gaps populated (C-05)
│   │   └── SimulationWritebackService.run_all(payload) [IO]
│   │       # writes to: simulation_runs, attack_chain_findings, compliance_gap_findings,
│   │       # agent_action_logs, incidents, vulnerabilities edges, etc.
│   │
│   └── [STATE] del _SIM_REGISTRY[sim_id]  # TTL cleanup (or immediate cleanup after writeback)
│
└── Step 7: user navigates to Situation Room
    └── frontend/app/dashboard/situation/page.tsx:SituationRoomPage
        └── [ASYNC] Promise.all([
              GET /v1/situation/ciso       → live data ✓ (existing)
              GET /v1/situation/board      → live data ✓ (existing)
              GET /v1/situation/engineering → live data ✓ (NEW — UC-05)
              GET /v1/situation/reg_affairs → live data ✓ (NEW — UC-06)
            ])
```

### Design Smells / Gaps

- Any legacy/backward-compatibility branch present? No
- Any naming-to-responsibility drift detected? No

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `N/A` (individual error paths covered in UC-03, UC-04, UC-05, UC-06)

---

## Use Case: UC-09 — SSE Stream Closes Cleanly On COMPLETED Status (Design-Risk)

### Goal

The SSE generator emits `event: done` and exits cleanly when `run_state.json` shows `status = "completed"` or `"failed"`, ensuring the client receives a proper terminal signal and the server generator coroutine is garbage collected.

### Design-Risk Objective

If the generator does not terminate, the client will hang indefinitely waiting for more events. If the generator leaks, it will continue reading the now-static JSONL file in a tight loop.

### Preconditions

- Simulation has completed; `run_state.json` in `sim_dir` contains `{"status": "completed"}`
- SSE client is still connected

### Expected Outcome

- Client receives `event: done\ndata: {}\n\n`
- Generator coroutine returns (exits the `while True` loop)
- FastAPI `StreamingResponse` closes the HTTP connection

### Primary Runtime Call Stack

```text
src/api/v1/endpoints/cse.py:_stream_from_jsonl(sim_id, sim_dir)
│ [inside while True loop]
├── read remaining new JSONL lines (drain any final events)
├── emit remaining `data:` events
│
├── [IO] run_state = _read_run_state(sim_dir)   # read run_state.json
├── if run_state["status"] in ("completed", "failed"):
│   ├── yield 'event: done\ndata: {}\n\n'
│   └── return   # generator function returns → StopAsyncIteration raised
│                # FastAPI StreamingResponse catches and closes connection
│
└── [else] await asyncio.sleep(0.5)  # not done yet; continue polling
```

### Branching / Fallback Paths

```text
[ERROR] run_state.json missing or unreadable (subprocess crash without writing state)
_read_run_state(sim_dir):
├── [IO] try: open run_state.json
├── except FileNotFoundError:
│   └── return {"status": "running"}  # keep polling; don't terminate SSE prematurely
└── If file not present for > 300 seconds:
    └── yield 'event: done\ndata: {"status":"timeout"}\n\n'
    └── return   # safety timeout to prevent infinite generator
```

### Design Smells / Gaps

- Any legacy/backward-compatibility branch present? No
- Any naming-to-responsibility drift detected? No

### Open Questions

- The 300-second safety timeout should be configurable via the `config` dict or env var. Default 300s is reasonable for demo.

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `Covered` (missing `run_state.json` → keep polling + safety timeout)

---

## Use Case: UC-10 — Regulator Concurrency Safety (Design-Risk)

### Goal

With three concurrent asyncio coroutines (Attacker, Defender, Regulator) sharing `AttackSurfaceServer` mutable state, no race conditions, data corruption, or deadlocks occur.

### Design-Risk Objective

Python's GIL + asyncio single-threaded event loop guarantee that only one coroutine runs at a time. However, if a coroutine does not yield (no `asyncio.sleep(0)` or `await`), it can monopolize the event loop. Verify the Regulator coroutine yields correctly each round.

### Preconditions

- `run_parallel_cyber_simulation.py` uses `asyncio.gather()` (not `ThreadPoolExecutor`)
- All three coroutines call `asyncio.sleep(0)` or another `await` expression once per round
- `AttackSurfaceServer` uses no threading primitives (no `asyncio.Lock`)

### Expected Outcome

- No `AssertionError`, `AttributeError`, or corrupted list state in `compliance_gaps`
- All three coroutines complete their configured number of rounds
- Interleaving is coarse-grained (full round per coroutine before yielding)

### Primary Runtime Call Stack

```text
asyncio event loop:
│
├── [round 1 of N] event loop schedules Attacker coroutine
│   ├── run_attacker_loop: round 1 logic (LLM call = await → yields to event loop)
│   └── asyncio.sleep(0) at end of round → yields
│
├── [round 1 of N] event loop schedules Defender coroutine
│   ├── run_defender_loop: round 1 logic (LLM call = await → yields)
│   └── asyncio.sleep(0) → yields
│
├── [round 1 of N] event loop schedules Regulator coroutine
│   ├── run_regulator_loop: round 1 logic (LLM call = await → yields)
│   ├── attack_surface_server.apply_action() → synchronous, no await
│   │   # safe: no other coroutine running during this synchronous call
│   └── asyncio.sleep(0) → yields
│
└── [rounds 2..N repeat the pattern above]

AttackSurfaceServer.compliance_gaps (list):
├── Only appended to by _handle_issue_compliance_finding()
├── Called synchronously (no await) inside apply_action()
├── Because asyncio is single-threaded, no concurrent append is possible
└── No lock needed
```

### Design Smells / Gaps

- Any legacy/backward-compatibility branch present? No
- Any naming-to-responsibility drift detected? No

### Open Questions

- LLM `await anthropic.messages.create(...)` in each coroutine is the primary yield point each round, not just `asyncio.sleep(0)`. This is fine — the await naturally yields the event loop to other coroutines.

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `N/A`

---

## Use Case: UC-11 — Empty-State Graceful Response (Design-Risk)

### Goal

`GET /v1/situation/engineering` and `GET /v1/situation/reg_affairs` return valid empty responses (not 404 or 500) when no simulation has run for the tenant.

### Design-Risk Objective

If the AQL query for `latest_run_id` returns nothing, the subsequent `attack_chain_findings` or `compliance_gap_findings` queries must not throw. The response must match the expected schema with empty arrays.

### Preconditions

- Tenant exists but has never run a simulation
- `simulation_runs`, `attack_chain_findings`, `compliance_gap_findings` collections exist but have no records for this tenant

### Expected Outcome

- `GET /v1/situation/engineering` → `{"patch_priority": [], "data_staleness_warning": "no simulation run found"}` with HTTP 200
- `GET /v1/situation/reg_affairs` → `{"regulatory_deadlines": []}` with HTTP 200

### Primary Runtime Call Stack

```text
src/complira_graph/situation/abstraction_layer.py:SituationAbstractionLayer.compute_engineering(tenant_id)
├── [IO] AQL: latest_run_id query → returns None (no records)
├── if latest_run_id is None:
│   └── return {"patch_priority": [], "data_staleness_warning": "no simulation run found"}
└── [normal path skipped]

src/complira_graph/situation/abstraction_layer.py:SituationAbstractionLayer.compute_reg_affairs(tenant_id)
├── [IO] AQL: latest_run_id query → returns None
├── if latest_run_id is None:
│   └── return {"regulatory_deadlines": []}
└── [normal path skipped]
```

### Design Smells / Gaps

- Any legacy/backward-compatibility branch present? No
- Any naming-to-responsibility drift detected? No

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `N/A` (empty state IS the success path here)

---

## Use Case: UC-12 — SSE Backpressure (Design-Risk)

### Goal

A slow SSE client (e.g., high latency or paused browser tab) does not block the JSONL file writer (agent subprocess) or cause the agent coroutine loop to stall.

### Design-Risk Objective

The JSONL file writer (`CyberActionLogger.log_action()`) is synchronous file I/O in the subprocess. The SSE endpoint (`_stream_from_jsonl`) is in the parent process and only reads the file. They share no synchronization primitive. The SSE generator uses `await asyncio.sleep(0.5)` between polls — a slow HTTP client delays yields of the generator coroutine but does NOT block the file writer in any way (different processes).

### Preconditions

- Subprocess running `run_parallel_cyber_simulation.py`
- Parent process SSE generator tailing `cyber_actions.jsonl`
- SSE client is slow (e.g., simulated with small TCP window)

### Expected Outcome

- Agent subprocess continues writing JSONL at full speed regardless of client read rate
- SSE generator accumulates unread lines between polls; when client resumes, it drains them
- No deadlock, no stall, no data loss

### Primary Runtime Call Stack

```text
[subprocess process — independent of parent]
src/complira_graph/cse/action_logger.py:CyberActionLogger.log_action(...)
├── [IO] open(cyber_actions.jsonl, "a")  # O_APPEND; no lock contention
├── write JSON line
└── flush/close
    # subprocess has no connection to parent SSE generator; writes always succeed

[parent process — FastAPI event loop]
src/api/v1/endpoints/cse.py:_stream_from_jsonl(sim_id, sim_dir)
├── while True:
│   ├── open file, seek to byte_offset, read new bytes
│   │   # reads as many bytes as have been written since last poll (no block)
│   ├── emit all buffered lines as SSE data events
│   │   # FastAPI yields bytes to HTTP write buffer
│   │   # If client is slow, HTTP write buffer fills; StreamingResponse awaits drain [ASYNC]
│   │   # This only slows the SSE generator coroutine; other API requests still run
│   └── await asyncio.sleep(0.5)
```

### Design Smells / Gaps

- Any legacy/backward-compatibility branch present? No
- Backpressure effect: if the client is very slow, unacknowledged `data:` events pile up in the OS TCP send buffer. This is bounded by OS buffer size (~128KB typical). If client disconnects entirely, `StreamingResponse` raises `BrokenPipeError` which FastAPI handles by cancelling the generator coroutine.

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `N/A` (`BrokenPipeError` on client disconnect is handled by FastAPI runtime, not application code)
