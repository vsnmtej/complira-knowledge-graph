# Future-State Runtime Call Stacks — cse-simulation-engine

## Design Basis

- Scope Classification: `Large`
- Call Stack Version: `v2`
- Requirements: `tickets/in-progress/cse-simulation-engine/requirements.md` (status `Design-ready`)
- Source Artifact: `tickets/in-progress/cse-simulation-engine/proposed-design.md`
- Source Design Version: `v1`
- Referenced Sections: File And Module Breakdown, Target Architecture Shape And Boundaries, Change Inventory

## Future-State Modeling Rule (Mandatory)

All call stacks model the **to-be** behavior derived from `proposed-design.md v1`. Current `mirofish/` code is not represented in any path. Subprocess isolation boundary is explicit in every execution path that crosses from API process into simulation child process.

---

## Use Case Index (Stable IDs)

| use_case_id | Source Type | Requirement ID(s) | Design-Risk Objective | Use Case Name | Coverage Target |
| --- | --- | --- | --- | --- | --- |
| UC-CSE-01 | Requirement | R-CSE-01 | N/A | Simulation lifecycle state machine | Primary/Fallback/Error |
| UC-CSE-02 | Requirement | R-CSE-02 | N/A | IPC command dispatch | Primary/Fallback/Error |
| UC-CSE-03 | Requirement | R-CSE-03 | N/A | Attack surface extraction | Primary/N/A/Error |
| UC-CSE-04 | Requirement | R-CSE-04 | N/A | Parallel agent profile generation | Primary/Fallback/Error |
| UC-CSE-05 | Requirement | R-CSE-05 | N/A | Simulation config synthesis | Primary/N/A/N/A |
| UC-CSE-06 | Requirement | R-CSE-06 | N/A | Preparation pipeline (CREATED → READY) | Primary/N/A/Error |
| UC-CSE-07 | Requirement | R-CSE-07 | N/A | Parallel simulation execution (subprocess) | Primary/N/A/Error |
| UC-CSE-08 | Requirement | R-CSE-08 | N/A | 15-action cybersecurity action space | Primary/N/A/N/A |
| UC-CSE-09 | Requirement | R-CSE-09 | N/A | JSONL action logging | Primary/N/A/N/A |
| UC-CSE-10 | Requirement | R-CSE-10 | N/A | SQLite working memory + ArangoDB flush | Primary/Fallback/Error |
| UC-CSE-11 | Requirement | R-CSE-11 | N/A | Post-simulation ReACT report generation | Primary/N/A/Error |
| UC-CSE-12 | Requirement | R-CSE-12 | N/A | Write-back integration | Primary/N/A/Error |
| UC-CSE-13 | Requirement | R-CSE-13 | N/A | CSE API endpoints (create + status) | Primary/N/A/Error |
| UC-CSE-14 | Requirement | R-CSE-14 | N/A | mirofish module removal (no dead imports) | Primary/N/A/N/A |
| UC-CSE-15 | Requirement | R-CSE-15 | N/A | Concurrent tenant isolation | Primary/N/A/N/A |
| UC-CSE-16 | Requirement | R-CSE-13 | N/A | CSE frontend wizard — trigger → monitor → results | Primary/N/A/Error |
| UC-CSE-DR-01 | Design-Risk | R-CSE-07, R-CSE-02 | Subprocess crash leaves run in RUNNING state; run_state.json must reflect FAILED | Subprocess crash recovery via run_state.json | Primary/N/A/Error |
| UC-CSE-DR-02 | Design-Risk | R-CSE-04 | asyncio.gather with 5 LLM calls — rate limit causes all profiles to fail | Profile gen partial failure with Semaphore(3) | Primary/Fallback/Error |

---

## Transition Notes

- `src/complira_graph/mirofish/` is deleted in the same deploy as CSE. All mirofish imports cleaned from `router.py` and tests before the new endpoint is deployed.
- `data/simulations/` is created on first `CyberSimulationRunner.start_simulation()` call via `Path.mkdir(parents=True, exist_ok=True)`. No pre-provisioning required.
- `scripts/init_simulation_schema.py` run once (idempotent) to add `agent_action_logs` collection before first simulation.

---

## Use Case: UC-CSE-01 — Simulation lifecycle state machine

### Goal
`CyberSimulationRunner` transitions through all 8 states (IDLE → STARTING → RUNNING → PAUSED → STOPPING → STOPPED → COMPLETED → FAILED). Every transition writes `run_state.json`.

### Preconditions
- `simulation_config.json` exists in `data/simulations/{tenant_id}/{sim_id}/`
- `CyberSimulationRunner` initialized with `sim_id`, `tenant_id`, `sim_dir`

### Expected Outcome
`run_state.json` reflects current status on every transition. `start_simulation()` transitions IDLE→STARTING→RUNNING and spawns subprocess. `stop_simulation()` sends CLOSE_ENV IPC then transitions STOPPING→STOPPED.

### Primary Runtime Call Stack

```text
[ENTRY] src/complira_graph/cse/runner.py:CyberSimulationRunner.start_simulation()
├── runner.py:_transition(IDLE → STARTING)
│   └── runner.py:_write_run_state() [IO] # writes run_state.json
├── runner.py:_launch_subprocess()
│   └── subprocess.Popen(
│         [sys.executable, "-m", "complira_graph.cse.run_parallel_cyber_simulation",
│          "--sim-dir", sim_dir, "--config", config_path],
│         cwd=project_root
│       )  # [IO] spawns child process
├── runner.py:_transition(STARTING → RUNNING)
│   └── runner.py:_write_run_state() [IO]
└── runner.py:_monitor_subprocess() [ASYNC]  # background thread polls proc.poll()
    ├── on proc exit 0 → _transition(RUNNING → COMPLETED) + _write_run_state() [IO]
    └── on proc exit != 0 → _transition(RUNNING → FAILED) + _write_run_state() [IO]
```

### Branching / Fallback Paths

```text
[FALLBACK] stop_simulation() called during RUNNING
src/complira_graph/cse/runner.py:stop_simulation()
├── runner.py:_transition(RUNNING → STOPPING) + _write_run_state() [IO]
├── ipc.py:CyberIPCClient.send_command("CLOSE_ENV", {}) [IO]  # writes command file
├── runner.py:_wait_for_subprocess(timeout=10)  # waits for clean exit
└── runner.py:_transition(STOPPING → STOPPED) + _write_run_state() [IO]
```

```text
[FALLBACK] pause/resume cycle
runner.py:pause_simulation()
├── ipc.py:CyberIPCClient.send_command("PAUSE_AND_SNAPSHOT", {}) [IO]
└── runner.py:_transition(RUNNING → PAUSED) + _write_run_state() [IO]

runner.py:resume_simulation()
├── ipc.py:CyberIPCClient.send_command("INJECT_VARIABLE", {"resume": True}) [IO]
└── runner.py:_transition(PAUSED → RUNNING) + _write_run_state() [IO]
```

```text
[ERROR] subprocess crashes (non-zero exit)
runner.py:_monitor_subprocess()
└── runner.py:_transition(RUNNING → FAILED) + _write_run_state() [IO]
    # status: "failed" written to run_state.json
    # write-back NOT called (manager checks status before calling report agent)
```

### State And Data Transformations

- `CyberRunnerStatus` enum value → `run_state.json` `status` field string
- `sim_dir/run_state.json` format: `{sim_id, tenant_id, status, trigger_type, total_rounds, current_round, started_at, updated_at}`

### Observability And Debug Points

- Logs: `runner.py:_transition()` logs `cse_runner_transition` at INFO level with `from_status`, `to_status`, `sim_id`
- `run_state.json` is the durable state record — survives API restart

### Design Smells / Gaps

- Any legacy/backward-compatibility branch present? No
- Any naming-to-responsibility drift detected? No

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `Covered` (stop + pause)
- Error Path: `Covered` (subprocess crash)

---

## Use Case: UC-CSE-02 — IPC command dispatch

### Goal
`CyberIPCHandler` (in subprocess) polls `ipc_commands/` directory, dispatches commands (INJECT_VARIABLE, PAUSE_AND_SNAPSHOT, CLOSE_ENV, DEBRIEF_AGENT), and writes response files. `CyberIPCClient` (in main process) writes command files and reads responses.

### Preconditions
- Subprocess is RUNNING
- `ipc_commands/` and `ipc_responses/` directories created by `CyberSimulationRunner` at start

### Expected Outcome
INJECT_VARIABLE dispatched and response received within 5 seconds. Unknown command returns `{error: "unknown_command"}`. Simulation does not crash on unknown command.

### Primary Runtime Call Stack

```text
[ENTRY — main process] src/complira_graph/cse/ipc.py:CyberIPCClient.send_command(cmd, payload)
├── ipc.py:_write_command_file(cmd, payload)  [IO]
│   # writes: ipc_commands/{uuid}.json = {command: cmd, payload: payload, sent_at: ISO}
└── ipc.py:_wait_for_response(cmd_id, timeout=5) [ASYNC]
    ├── poll ipc_responses/{cmd_id}.json every 0.1s [IO]
    └── on file found → return parsed response dict
```

```text
[SUBPROCESS SIDE] src/complira_graph/cse/ipc.py:CyberIPCHandler.poll_commands()
# called from run_parallel_cyber_simulation.py within asyncio.gather loop
├── ipc.py:_scan_command_files() [IO]  # list ipc_commands/*.json
├── for each command file:
│   ├── ipc.py:dispatch(command_name, payload) [STATE]
│   │   ├── "INJECT_VARIABLE" → attacker/defender simulation state update [STATE]
│   │   ├── "PAUSE_AND_SNAPSHOT" → set pause_flag=True; write snapshot [STATE] [IO]
│   │   ├── "CLOSE_ENV" → set stop_flag=True [STATE]
│   │   ├── "DEBRIEF_AGENT" → enable debrief mode [STATE]
│   │   └── unknown → write {error: "unknown_command"} to response [IO]
│   ├── ipc.py:_write_response_file(cmd_id, result) [IO]
│   └── ipc.py:_delete_command_file(cmd_id) [IO]
└── asyncio.sleep(0.1)  # yield to other coroutines
```

### Branching / Fallback Paths

```text
[ERROR] unknown command received
ipc.py:dispatch(unknown_cmd, payload)
├── log warning "ipc_unknown_command", cmd=unknown_cmd
└── write {error: "unknown_command", cmd: unknown_cmd} to ipc_responses/{cmd_id}.json [IO]
# simulation loop continues uninterrupted
```

```text
[ERROR] response timeout > 5s
ipc.py:CyberIPCClient._wait_for_response(timeout=5)
└── raise IPCTimeoutError("Command {cmd} timed out after 5s")
    # caller (runner.py) logs and handles; simulation continues in subprocess
```

### State And Data Transformations

- Command file: `{command: str, payload: dict, sent_at: ISO, cmd_id: uuid}` → dispatched action + response file
- Response file: `{cmd_id: str, result: dict, responded_at: ISO}`

### Observability And Debug Points

- Logs: `ipc_command_dispatched`, `ipc_command_timeout`, `ipc_unknown_command`

### Design Smells / Gaps

- Any legacy/backward-compatibility branch present? No
- Any naming-to-responsibility drift detected? No

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `Covered` (unknown command; timeout)

---

## Use Case: UC-CSE-03 — Attack surface extraction

### Goal
`CompliraGraphReader.get_attack_surface()` queries ArangoDB for `CyberEntityNode` list (CVEs + components + regulatory obligations) for a tenant in < 200ms.

### Preconditions
- ArangoDB available; tenant has at least one CVE or component in graph

### Expected Outcome
Returns `list[CyberEntityNode]` with ≥ 1 entity for demo tenant. Empty list if no entities → triggers 422 in API.

### Primary Runtime Call Stack

```text
[ENTRY] src/complira_graph/cse/graph_reader.py:CompliraGraphReader.get_attack_surface(db, tenant_id)
├── graph_reader.py:_build_aql_query()  # AQL: CVEs + components + reg obligations for tenant
├── db.aql.execute(aql, bind_vars={"tenant_id": tenant_id}) [IO]
│   # ArangoDB query — filtered by tenant_id index (< 200ms for < 100 CVEs)
├── for each row → graph_reader.py:_row_to_entity_node(row) → CyberEntityNode
└── return list[CyberEntityNode]
```

### Branching / Fallback Paths

```text
[ERROR] empty result (no CVEs/components)
graph_reader.py:get_attack_surface(db, tenant_id)
└── return []  # empty list — caller (simulation_manager.py) raises ValueError → API returns 422
```

```text
[ERROR] ArangoDB unavailable
graph_reader.py:get_attack_surface(db, tenant_id)
└── db.aql.execute() raises ArangoError [IO]
    └── propagated to simulation_manager.py → logged + run_state.json = FAILED
```

### State And Data Transformations

- ArangoDB rows → `CyberEntityNode(entity_id, entity_type, severity, is_kev, regulatory_refs, component_name)`

### Observability And Debug Points

- Logs: `cse_graph_reader_fetched` with `entity_count`, `tenant_id`, `elapsed_ms`

### Design Smells / Gaps

- Any legacy/backward-compatibility branch present? No
- Any naming-to-responsibility drift detected? No

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `Covered` (empty list; ArangoDB error)

---

## Use Case: UC-CSE-04 — Parallel agent profile generation

### Goal
`CyberAgentProfileGenerator.generate_all()` generates 5 agent profiles (Attacker, SOCAnalyst, DevSecOps, CISO, Regulator) in parallel via `asyncio.gather`. All profiles are valid JSON matching the `cyber_simulation_config.json` schema.

### Preconditions
- `list[CyberEntityNode]` from `CompliraGraphReader`
- `ANTHROPIC_API_KEY` set in config

### Expected Outcome
Returns `list[dict]` with 5 profile dicts. Each profile includes `agent_type`, `role`, `tactics`, `constraints`, `goals` keys.

### Primary Runtime Call Stack

```text
[ENTRY] src/complira_graph/cse/profile_generator.py:CyberAgentProfileGenerator.generate_all(entities)
├── profile_generator.py:_build_profile_tasks(entities)
│   # builds 5 coroutine tasks, one per agent type
├── asyncio.gather(
│     _generate_profile("Attacker", entities, semaphore),
│     _generate_profile("SOCAnalyst", entities, semaphore),
│     _generate_profile("DevSecOps", entities, semaphore),
│     _generate_profile("CISO", entities, semaphore),
│     _generate_profile("Regulator", entities, semaphore)
│   ) [ASYNC]
│   # Semaphore(3) limits concurrency to 3 simultaneous Claude calls
│
└── for each result → profile_generator.py:_validate_profile_schema(result)
    └── return list[dict]  # 5 validated profiles
```

```text
[DETAIL] profile_generator.py:_generate_profile(agent_type, entities, semaphore)
async with semaphore:
    ├── profile_generator.py:_build_prompt(agent_type, entities)  # structured prompt
    ├── anthropic.messages.create(model=ANTHROPIC_MODEL_SONNET, ...) [ASYNC] [IO]
    └── profile_generator.py:_parse_response(raw_text) → dict
```

### Branching / Fallback Paths

```text
[FALLBACK] Semaphore(3) — 4th+ concurrent call waits for semaphore slot
asyncio.Semaphore(3) — 4th task yields until one of 3 active tasks completes
# no failure, just sequential fallback for rate-limited burst
```

```text
[ERROR] Claude 429 rate limit
anthropic.messages.create() → anthropic.RateLimitError
├── profile_generator.py:_generate_profile() catches RateLimitError
├── asyncio.sleep(exponential_backoff) [ASYNC]
└── retry up to 3 times, then raise
    └── asyncio.gather raises ProfileGenerationError
        └── simulation_manager.py catches → run_state = FAILED
```

### State And Data Transformations

- `list[CyberEntityNode]` + agent_type → LLM prompt → JSON response → profile dict
- Profile schema: `{agent_type, role, tactics: list[str], constraints: list[str], goals: list[str], llm_context: str}`

### Observability And Debug Points

- Logs: `cse_profile_generated` per profile with `agent_type`, `elapsed_ms`
- Logs: `cse_profile_rate_limited` on retry

### Design Smells / Gaps

- Any legacy/backward-compatibility branch present? No
- Any naming-to-responsibility drift detected? No

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `Covered` (Semaphore(3))
- Error Path: `Covered` (rate limit)

---

## Use Case: UC-CSE-05 — Simulation config synthesis

### Goal
`CyberSimConfigGenerator.generate()` produces `simulation_config.json` with `total_rounds`, `hours_per_round=1`, `cra_deadline_round=24`, `agent_profiles[]`, `scheduled_events[]`, `narrative_provider`.

### Preconditions
- 5 profiles from `CyberAgentProfileGenerator.generate_all()`
- `list[CyberEntityNode]` available
- `trigger_type` known ("kev_triggered" → 48 rounds; "monthly_posture_sim" → 720 rounds)

### Expected Outcome
`simulation_config.json` written to `data/simulations/{tenant}/{sim_id}/simulation_config.json`.

### Primary Runtime Call Stack

```text
[ENTRY] src/complira_graph/cse/config_generator.py:CyberSimConfigGenerator.generate(trigger_type, profiles, entities, sim_dir)
├── config_generator.py:_compute_total_rounds(trigger_type)
│   ├── "kev_triggered" → 48
│   └── "monthly_posture_sim" → 720
├── config_generator.py:_build_scheduled_events(entities)
│   # map KEV CVEs → early-round scheduled exploit events
├── config_generator.py:_assemble_config(
│     sim_id, tenant_id, trigger_type,
│     total_rounds, hours_per_round=1, cra_deadline_round=24,
│     agent_profiles=profiles, scheduled_events=events,
│     narrative_provider="claude"
│   ) → dict
├── json.dumps(config) [IO]
└── Path(sim_dir / "simulation_config.json").write_text(json_str) [IO]
    # returns config dict
```

### State And Data Transformations

- trigger_type + profiles + entities → `simulation_config.json` dict with all required fields

### Observability And Debug Points

- Logs: `cse_config_generated` with `sim_id`, `total_rounds`, `trigger_type`

### Design Smells / Gaps

- Any legacy/backward-compatibility branch present? No
- Any naming-to-responsibility drift detected? No

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `N/A`

---

## Use Case: UC-CSE-06 — Preparation pipeline (CREATED → READY)

### Goal
`CyberSimulationManager.prepare()` orchestrates the full preparation pipeline: graph read → profile gen → config gen → CREATED state → READY state. Both `run_state.json` and `simulation_config.json` are written before subprocess launch.

### Preconditions
- ArangoDB available with tenant data
- Valid `trigger_type`

### Expected Outcome
Returns `sim_id`. `data/simulations/{tenant}/{sim_id}/` directory contains `run_state.json` (status=ready) and `simulation_config.json`.

### Primary Runtime Call Stack

```text
[ENTRY] src/complira_graph/cse/simulation_manager.py:CyberSimulationManager.prepare(db, tenant_id, trigger_type)
├── simulation_manager.py:_generate_sim_id()  # uuid4
├── simulation_manager.py:_create_sim_directories(tenant_id, sim_id)  [IO]
│   # mkdir: data/simulations/{tenant_id}/{sim_id}/ipc_commands/
│   # mkdir: data/simulations/{tenant_id}/{sim_id}/ipc_responses/
├── runner.py:CyberSimulationRunner(sim_id, tenant_id, sim_dir)
├── runner.py:_transition(→ CREATED) + _write_run_state() [IO]
│
├── graph_reader.py:CompliraGraphReader.get_attack_surface(db, tenant_id) [IO]
│   └── returns list[CyberEntityNode]
│   └── [ERROR] if empty → raise ValueError("insufficient_attack_surface")
│
├── profile_generator.py:CyberAgentProfileGenerator.generate_all(entities) [ASYNC]
│   └── returns list[dict] (5 profiles)
│
├── config_generator.py:CyberSimConfigGenerator.generate(trigger_type, profiles, entities, sim_dir) [IO]
│   └── writes simulation_config.json
│
├── runner.py:_transition(CREATED → READY) + _write_run_state() [IO]
│
├── simulation_manager.py:_upsert_simulation_runs(db, sim_id, tenant_id, "ready") [IO]
│   # INSERT simulation_runs document in ArangoDB
│
└── return sim_id
```

### Branching / Fallback Paths

```text
[ERROR] empty attack surface
graph_reader.py:get_attack_surface() returns []
└── simulation_manager.py raises ValueError("insufficient_attack_surface")
    └── api/v1/endpoints/cse.py:create_simulation() catches ValueError
        └── raise HTTPException(status_code=422, detail="insufficient_attack_surface")
```

```text
[ERROR] ArangoDB unavailable during prepare
simulation_manager.py:_upsert_simulation_runs() raises ArangoError
└── simulation_manager.py logs + runner._transition(→ FAILED) + _write_run_state() [IO]
    └── API returns 503
```

### State And Data Transformations

- `trigger_type` + tenant ArangoDB data → `sim_id` + `run_state.json` (status=ready) + `simulation_config.json`

### Observability And Debug Points

- Logs: `cse_prepare_started`, `cse_prepare_complete` with `sim_id`, `tenant_id`, `elapsed_ms`
- ArangoDB: `simulation_runs` document upserted with `status=ready`

### Design Smells / Gaps

- Any legacy/backward-compatibility branch present? No
- Any naming-to-responsibility drift detected? No

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `Covered` (empty surface; ArangoDB error)

---

## Use Case: UC-CSE-07 — Parallel simulation execution (subprocess)

### Goal
`run_parallel_cyber_simulation.py` runs attacker loop + defender loop + IPC polling concurrently via `asyncio.gather` for `total_rounds` rounds. Completes with `run_state.json` showing `status: completed`.

### Preconditions
- Launched as subprocess: `sys.executable -m complira_graph.cse.run_parallel_cyber_simulation --sim-dir ... --config ...`
- `simulation_config.json` exists in sim_dir

### Expected Outcome
48 rounds complete. `run_state.json` shows `status: completed`. `cyber_actions.jsonl` has entries for all rounds.

### Primary Runtime Call Stack

```text
[ENTRY — subprocess] src/complira_graph/cse/run_parallel_cyber_simulation.py:main()
├── run_parallel_cyber_simulation.py:_load_config(config_path)  [IO]
├── run_parallel_cyber_simulation.py:_init_components(sim_dir, config)
│   ├── attack_surface_server.py:AttackSurfaceServer(entities=config["entities"]) [STATE]
│   ├── action_logger.py:CyberActionLogger(sim_dir) [IO]  # opens cyber_actions.jsonl
│   ├── memory_updater.py:CyberMemoryUpdater(sim_dir) [IO]  # opens SQLite, starts bg thread
│   └── ipc.py:CyberIPCHandler(sim_dir)
│
├── action_logger.py:log_simulation_start(config) [IO]
│
├── asyncio.gather(
│     attacker_simulation.py:run_attacker_loop(config, surface_server, logger, memory),
│     defender_simulation.py:run_defender_loop(config, surface_server, logger, memory),
│     ipc.py:CyberIPCHandler.poll_commands()
│   ) [ASYNC]  # all three run concurrently for total_rounds
│
├── memory_updater.py:CyberMemoryUpdater.flush_remaining() [IO]  # final SQLite flush
├── run_parallel_cyber_simulation.py:_write_completion_state(sim_dir) [IO]
│   # updates run_state.json: status=completed, current_round=total_rounds
│
│   # ── DEBRIEF PHASE ─────────────────────────────────────────────────────────
│   # Subprocess stays alive to handle DEBRIEF_AGENT queries from main process
│   # Main process (simulation_manager.complete()) detects completed via run_state.json
│   # and runs CyberReportAgent (direct AQL — no IPC), then sends CLOSE_ENV
│
├── run_parallel_cyber_simulation.py:_debrief_loop(ipc_handler)
│   while not stop_flag:
│   ├── ipc_handler.poll_commands() [IO]  # handles DEBRIEF_AGENT queries
│   └── asyncio.sleep(0.2)
│   # loop exits when CLOSE_ENV sets stop_flag=True
│
└── sys.exit(0)  # clean exit after CLOSE_ENV received
```

```text
[DETAIL] attacker_simulation.py:run_attacker_loop(config, surface_server, logger, memory)
for round_no in range(total_rounds):
    ├── action_logger.py:log_round_start(round_no) [IO]
    ├── attacker_simulation.py:_decide_action(surface_server, config, round_no) [ASYNC]
    │   # LLM call to determine attacker action
    │   └── anthropic.messages.create(...) [ASYNC] [IO]
    ├── attack_surface_server.py:apply_action(action_type, payload) [STATE]
    ├── action_logger.py:log_action(action_type, payload, outcome) [IO]
    ├── memory_updater.py:record(CyberAgentActivity(...)) [STATE]  # enqueues
    └── asyncio.sleep(0)  # yield to defender loop + IPC poller
```

### Branching / Fallback Paths

```text
[ERROR] subprocess crashes mid-run (unhandled exception)
run_parallel_cyber_simulation.py:main() → unhandled exception
└── Python default handler → sys.exit(1)
    └── runner.py:_monitor_subprocess() detects exit code 1
        └── runner.py:_transition(RUNNING → FAILED) + _write_run_state() [IO]
        # note: partial cyber_actions.jsonl and SQLite data remain (useful for debug)
```

### State And Data Transformations

- `simulation_config.json` → `AttackSurfaceServer` initial state (CVEs, exploitability map)
- Each round: attacker/defender action → `AttackSurfaceServer` state mutation + `cyber_actions.jsonl` append + SQLite enqueue
- Final: `run_state.json` status=completed

### Observability And Debug Points

- Logs: `cse_round_start`, `cse_attacker_action`, `cse_defender_action` per round (in subprocess stdout/stderr)
- `cyber_actions.jsonl` — primary debug artifact for simulation replay

### Design Smells / Gaps

- Any legacy/backward-compatibility branch present? No
- Any naming-to-responsibility drift detected? No

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `Covered` (subprocess crash)

---

## Use Case: UC-CSE-08 — 15-action cybersecurity action space

### Goal
`AttackSurfaceServer.apply_action()` handles all 15 action types and produces correct state changes. PATCH removes CVE from exploitable list. EXPLOIT_CVE adds chain step.

### Preconditions
- `AttackSurfaceServer` initialized with entity list from `simulation_config.json`

### Expected Outcome
All 15 actions produce defined state changes. PATCH(cve_id) → `exploitable_cves` no longer contains `cve_id`. EXPLOIT_CVE(cve_id) → `chain_steps` contains new step.

### Primary Runtime Call Stack

```text
[ENTRY] src/complira_graph/cse/attack_surface_server.py:AttackSurfaceServer.apply_action(action_type, payload)
├── "SCAN_SURFACE" → _action_scan_surface(payload) [STATE]  # returns visible CVEs snapshot
├── "EXPLOIT_CVE" → _action_exploit_cve(payload) [STATE]
│   ├── validate cve_id in exploitable_cves
│   └── append ChainStep(cve_id, technique, timestamp) to chain_steps [STATE]
├── "LATERAL_MOVE" → _action_lateral_move(payload) [STATE]  # expand reached_components
├── "ESCALATE_PRIVILEGES" → _action_escalate(payload) [STATE]  # set privilege_level
├── "PIVOT_TARGET" → _action_pivot(payload) [STATE]  # update current_target
├── "MONITOR" → _action_monitor(payload) [STATE]  # set monitoring_active=True
├── "DETECT" → _action_detect(payload) [STATE]  # record detection event
├── "INVESTIGATE" → _action_investigate(payload) [STATE]  # mark CVE under investigation
├── "ESCALATE_TO_CISO" → _action_escalate_to_ciso(payload) [STATE]  # set ciso_alerted=True
├── "PATCH" → _action_patch(payload) [STATE]
│   ├── remove cve_id from exploitable_cves
│   └── add cve_id to patched_cves
├── "DEPLOY_CONTROL" → _action_deploy_control(payload) [STATE]  # add control to controls_deployed
├── "ROTATE_CREDENTIAL" → _action_rotate_credential(payload) [STATE]  # invalidate lateral movement
├── "FILE_CRA_NOTIFICATION" → _action_file_cra(payload) [STATE]  # set cra_notified=True, cra_round=round_no
├── "NOTIFY_BOARD" → _action_notify_board(payload) [STATE]  # set board_notified=True
├── "ACKNOWLEDGE" → _action_acknowledge(payload) [STATE]  # set acknowledged_cves.add(cve_id)
└── return ActionResult(action_type, outcome_description, state_delta)
```

### State And Data Transformations

- `exploitable_cves: set[str]` — modified by EXPLOIT_CVE, PATCH
- `chain_steps: list[ChainStep]` — appended by EXPLOIT_CVE, LATERAL_MOVE
- `patched_cves: set[str]` — appended by PATCH
- `controls_deployed: list[str]` — appended by DEPLOY_CONTROL
- `ciso_alerted: bool`, `board_notified: bool`, `cra_notified: bool` — set by their respective actions

### Design Smells / Gaps

- Any legacy/backward-compatibility branch present? No
- Any naming-to-responsibility drift detected? No

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `N/A`

---

## Use Case: UC-CSE-09 — JSONL action logging

### Goal
`CyberActionLogger` writes valid JSONL to `cyber_actions.jsonl` for all 15 action types, plus `simulation_start` and `round_start` entries.

### Preconditions
- `CyberActionLogger` initialized with `sim_dir`
- `cyber_actions.jsonl` opened for append

### Expected Outcome
After 100 rounds, JSONL file contains all 15 action type strings. Every line is valid JSON.

### Primary Runtime Call Stack

```text
[ENTRY] src/complira_graph/cse/action_logger.py:CyberActionLogger(sim_dir)
└── _open_log_file(sim_dir / "cyber_actions.jsonl", mode="a") [IO]

action_logger.py:log_simulation_start(config)
└── _write_line({type: "simulation_start", sim_id, tenant_id, total_rounds, timestamp}) [IO]

action_logger.py:log_round_start(round_no)
└── _write_line({type: "round_start", round_no, timestamp}) [IO]

action_logger.py:log_action(action_type, agent_type, payload, outcome, round_no)
└── _write_line({type: "action", action_type, agent_type, payload, outcome, round_no, timestamp}) [IO]
    # one line per action per round; append-only
```

### State And Data Transformations

- Each call → one JSON line appended to `cyber_actions.jsonl`
- Line format: `{type, action_type, agent_type, payload, outcome, round_no, sim_id, timestamp}`

### Design Smells / Gaps

- Any legacy/backward-compatibility branch present? No
- Any naming-to-responsibility drift detected? No

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `N/A`

---

## Use Case: UC-CSE-10 — SQLite working memory + ArangoDB flush

### Goal
`CyberMemoryUpdater` writes agent activities to per-run `cyber_agent_memory.db` via Queue + background thread (batch_size=5). Batch of 5 activities flushed to ArangoDB `agent_action_logs` collection with `episode_text` readable.

### Preconditions
- `CyberMemoryUpdater` initialized; SQLite connection open with `check_same_thread=False`; background thread started

### Expected Outcome
Batch of 5 `CyberAgentActivity` objects written to SQLite, then flushed to ArangoDB `agent_action_logs`. Each document has `episode_text` set.

### Primary Runtime Call Stack

```text
[ENTRY — simulation loop] src/complira_graph/cse/memory_updater.py:CyberMemoryUpdater.record(activity: CyberAgentActivity)
└── memory_updater.py:_queue.put(activity) [STATE]  # enqueue; non-blocking

[BACKGROUND THREAD] memory_updater.py:_batch_write_worker()
loop:
├── collect up to batch_size=5 activities from queue
├── memory_updater.py:_write_batch_to_sqlite(activities) [IO]
│   # INSERT INTO cyber_agent_activities(sim_id, agent_id, agent_type, round_no,
│   #   action_type, target, outcome, episode_text, timestamp) VALUES ...
└── if len(activities) == batch_size:
    └── memory_updater.py:_flush_batch_to_arango(db, activities) [IO]
        # INSERT INTO agent_action_logs collection (ArangoDB)
        # document: {sim_id, agent_id, agent_type, round_no, action_type, episode_text, ...}
```

```text
[AT SIMULATION END] memory_updater.py:flush_remaining(db)
├── drain remaining queue items
├── _write_batch_to_sqlite(remaining) [IO]
└── _flush_batch_to_arango(db, remaining) [IO]
    # flush any partial batch to ArangoDB
```

### Branching / Fallback Paths

```text
[FALLBACK] partial batch < 5 at simulation end
memory_updater.py:flush_remaining()
└── flush partial batch even if len < 5 [IO]
```

```text
[ERROR] SQLite thread safety
sqlite3.connect(db_path, check_same_thread=False)
# explicit flag — background thread writes safely to same connection
```

### State And Data Transformations

- `CyberAgentActivity` dataclass → SQLite row → ArangoDB `agent_action_logs` document
- `episode_text` field must be non-empty (LLM narrative from agent action decision)

### Observability And Debug Points

- Logs: `cse_memory_batch_flushed` with `batch_size`, `agent_id`, `sim_id`

### Design Smells / Gaps

- Any legacy/backward-compatibility branch present? No
- Any naming-to-responsibility drift detected? No

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `Covered` (partial batch flush)
- Error Path: `Covered` (SQLite check_same_thread)

---

## Use Case: UC-CSE-11 — Post-simulation ReACT report generation

### Goal
`CyberReportAgent.run()` executes ReACT loop with 3 AQL tools (deep_chain_analysis, timeline_reconstruction, agent_state_query). Produces report with `chain_probability`, `soc_miss_probability`, `tef_estimate`, `board_narrative`, `top_3_actions` in < 30 seconds.

### Preconditions
- Simulation completed (subprocess exit 0)
- `agent_action_logs` and `simulation_runs` populated in ArangoDB
- `ANTHROPIC_API_KEY` available

### Expected Outcome
Returns dict with all required report fields. `chain_probability` and `board_narrative` are non-null.

### Primary Runtime Call Stack

```text
[ENTRY] src/complira_graph/cse/report_agent.py:CyberReportAgent.run(db, sim_id, tenant_id)
├── report_agent.py:_build_initial_prompt(sim_id, tenant_id)
├── [ReACT LOOP — up to 5 iterations]
│   ├── anthropic.messages.create(
│         model=ANTHROPIC_MODEL_SONNET,
│         tools=REPORT_TOOLS,  # 3 tool definitions
│         messages=[...],
│         timeout=ANTHROPIC_TIMEOUT
│       ) [ASYNC] [IO]
│   │
│   ├── on tool_use block → dispatch tool:
│   │   ├── "deep_chain_analysis" → db.aql.execute(AQL_DEEP_CHAIN, {sim_id}) [IO]
│   │   ├── "timeline_reconstruction" → db.aql.execute(AQL_TIMELINE, {sim_id}) [IO]
│   │   └── "agent_state_query" → db.aql.execute(AQL_AGENT_STATE, {sim_id, agent_id}) [IO]
│   │   └── append tool result to messages list
│   │
│   └── on stop_reason="end_turn" → break loop
│
├── report_agent.py:_extract_report_fields(final_response)
│   # parse: chain_probability, soc_miss_probability, tef_estimate,
│   #        board_narrative, top_3_actions
└── return report_dict
```

### Branching / Fallback Paths

```text
[ERROR] Claude timeout (> ANTHROPIC_TIMEOUT seconds)
anthropic.messages.create() → anthropic.APITimeoutError
├── report_agent.py catches timeout
├── return partial_report_dict with available fields (chain_probability=None if loop never ran)
└── log cse_report_timeout, sim_id=sim_id
    # simulation_manager.py still calls write-back with partial report
```

### State And Data Transformations

- AQL query results → LLM context messages → final report dict
- `board_narrative` must not contain raw CVE IDs (uses ATT&CK tactic names)

### Observability And Debug Points

- Logs: `cse_report_react_iteration` per loop with `iteration_no`, `tool_called`
- Logs: `cse_report_complete` with `elapsed_ms`, `chain_probability`

### Design Smells / Gaps

- Any legacy/backward-compatibility branch present? No
- Any naming-to-responsibility drift detected? No

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `Covered` (timeout → partial report)

---

## Use Case: UC-CSE-12 — Write-back integration

### Goal
After `CyberReportAgent` completes, `SimulationWritebackService.run_all()` is called with report payload. ArangoDB collections populated. `SituationAbstractionLayer` returns updated CISO/Board views. No CVE IDs in CISO/Board output.

### Preconditions
- `CyberReportAgent.run()` returned report dict
- `SimulationWritebackService` built and available

### Expected Outcome
ArangoDB `attack_chain_findings`, `threat_category_rollups`, `business_impact_findings` populated. `GET /v1/situation/ciso` returns updated `posture_score`. No CVE IDs in response.

### Primary Runtime Call Stack

```text
[ENTRY] src/complira_graph/cse/simulation_manager.py:CyberSimulationManager.complete(db, sim_id)
├── simulation_manager.py:_wait_for_subprocess_complete(runner)
│   # polls run_state.json until status=completed or timeout
├── report_agent.py:CyberReportAgent(db, settings).run(db, sim_id, tenant_id) [ASYNC]
│   └── returns report_dict
│
├── simulation_manager.py:_build_writeback_payload(sim_id, tenant_id, report_dict, run_state)
│   # maps report fields to SimulationWritebackService payload schema
│
├── simulation.writeback_service.py:SimulationWritebackService(db).run_all(payload) [IO]
│   # 8-step UPSERT pipeline to ArangoDB
│   # Steps 1-8: simulation_runs, attack_chain_findings, response_playbook_steps,
│   #            compliance_gap_findings, simulation_agent_logs, chain_calibrates_fair,
│   #            summary upsert, threat_category_rollups + business_impact_findings
│
├── ipc.py:CyberIPCClient.send_command("CLOSE_ENV", {}) [IO]
│   # terminates subprocess debrief loop → subprocess exits with sys.exit(0)
│
└── log.info("cse_complete", sim_id=sim_id)
```

### Branching / Fallback Paths

```text
[ERROR] subprocess exited with FAILED status
simulation_manager.py:complete()
├── check run_state.json: status=failed
├── log cse_sim_failed, sim_id=sim_id
└── return without calling report_agent or write-back
    # No partial write-back on failed run
```

### State And Data Transformations

- report_dict → write-back payload conforming to `SimulationWritebackService` contract
- `board_narrative` field maps to `business_impact_findings` documents (no CVE IDs)
- `top_3_actions` maps to `response_playbook_steps` documents

### Observability And Debug Points

- Logs: `cse_writeback_started`, `cse_writeback_complete` with `sim_id`, `elapsed_ms`

### Design Smells / Gaps

- Any legacy/backward-compatibility branch present? No
- Any naming-to-responsibility drift detected? No

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `Covered` (failed run → no write-back)

---

## Use Case: UC-CSE-13 — CSE API endpoints (create + status)

### Goal
`POST /v1/cse/simulations/create` validates seed data, starts CSE run, returns `{sim_id, status: "queued"}`. `GET /v1/cse/simulations/{sim_id}/status` returns run state. Invalid tenant returns 422 on empty surface.

### Preconditions
- Authenticated tenant (JWT or API key)
- ArangoDB available

### Expected Outcome
POST returns 200 `{sim_id, status: "queued"}` for valid tenant. POST returns 422 for empty attack surface. GET returns current `run_state.json` status.

### Primary Runtime Call Stack

```text
[ENTRY — POST] src/api/v1/endpoints/cse.py:create_simulation(body, customer)
├── cse.py:_validate_request(body)  # trigger_type, optional params
├── simulation_manager.py:CyberSimulationManager(settings).prepare(db, tenant_id, trigger_type) [ASYNC]
│   └── (see UC-CSE-06 for full prepare flow)
│   └── returns sim_id
├── runner.py:CyberSimulationRunner.start_simulation() [ASYNC]
│   └── spawns subprocess
├── simulation_manager.py:_run_complete_async(db, sim_id) [ASYNC]
│   # background task: wait for subprocess → call report agent → write-back
│   # does not block HTTP response
└── return JSONResponse({sim_id: sim_id, status: "queued"})
```

```text
[ENTRY — GET] src/api/v1/endpoints/cse.py:get_simulation_status(sim_id, customer)
├── cse.py:_check_tenant_ownership(db, sim_id, tenant_id)  [IO]
│   # AQL: FOR r IN simulation_runs FILTER r._key == @sim_id AND r.tenant_id == @tenant_id
│   └── if not found → raise HTTPException(404, "run_not_found")
├── cse.py:_read_run_state(sim_dir, sim_id) [IO]
│   # read run_state.json; fall back to simulation_runs if file missing
└── return JSONResponse(CSERunStatus: {
      sim_id, tenant_id, status, trigger_type,
      current_round, total_rounds, agent_count,
      chain_count,         # null until write-back completes
      started_at, updated_at,
      recent_events: [     # last 20 entries from cyber_actions.jsonl
        {log_key, event_type, agent_id, agent_type, round_no, outcome, significance, timestamp}
      ]
    })
```

### Branching / Fallback Paths

```text
[ERROR] empty attack surface
simulation_manager.py:prepare() raises ValueError("insufficient_attack_surface")
└── cse.py:create_simulation() catches ValueError
    └── raise HTTPException(422, "insufficient_attack_surface")
```

```text
[ERROR] GET sim_id not found or wrong tenant
cse.py:_check_tenant_ownership() → empty AQL result
└── raise HTTPException(404, "run_not_found")
```

### State And Data Transformations

- HTTP request body → `trigger_type`, `tenant_id`
- `sim_id` → `{sim_id, status: "queued"}` HTTP response
- `run_state.json` → status response payload

### Observability And Debug Points

- Logs: `cse_create_simulation` with `tenant_id`, `trigger_type`, `sim_id`
- Logs: `cse_status_polled` with `sim_id`, `status`

### Design Smells / Gaps

- Any legacy/backward-compatibility branch present? No
- Any naming-to-responsibility drift detected? No

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `Covered` (422 empty surface; 404 not found)

---

## Use Case: UC-CSE-14 — mirofish module removal

### Goal
`src/complira_graph/mirofish/` module (3 files) and `src/api/v1/endpoints/mirofish.py` are deleted. No imports of `complira_graph.mirofish` remain. Router updated. Tests updated.

### Preconditions
- CSE package fully implemented and tested
- Tests that referenced mirofish updated for CSE endpoint

### Expected Outcome
`grep -r "complira_graph.mirofish"` returns zero results. `grep -r "from api.v1.endpoints import mirofish"` returns zero results. No `ImportError` at startup.

### Primary Runtime Call Stack

```text
[REMOVAL SEQUENCE — not a runtime flow]
1. Delete src/complira_graph/mirofish/trigger_client.py
2. Delete src/complira_graph/mirofish/seed_extractor.py
3. Delete src/complira_graph/mirofish/__init__.py
4. Delete src/api/v1/endpoints/mirofish.py
5. Edit src/api/v1/router.py:
   - Remove: from api.v1.endpoints import mirofish
   - Remove: api_router.include_router(mirofish.router, ...)
   + Add: from api.v1.endpoints import cse
   + Add: api_router.include_router(cse.router, prefix="", tags=["cse"])
6. Update tests/integration/test_situation_simulation_api.py:
   - Remove TestMiroFishTriggerAPI class
   - Add TestCSESimulationAPI class (scenarios mapped to AC-CSE-18, AC-CSE-19)
```

### Coverage Status

- Primary Path: `Covered` (deletion sequence defined)
- Fallback Path: `N/A`
- Error Path: `N/A`

---

## Use Case: UC-CSE-15 — Concurrent tenant isolation

### Goal
Two concurrent tenant simulations run without cross-contamination. Each run has isolated `data/simulations/{tenant}/{sim_id}/` directory, isolated SQLite, isolated IPC directories.

### Preconditions
- Two simultaneous `POST /v1/cse/simulations/create` from different tenants

### Expected Outcome
Tenant A's `cyber_actions.jsonl`, `cyber_agent_memory.db`, `ipc_commands/`, `ipc_responses/` are in `data/simulations/tenant_a/{sim_id_a}/`. Tenant B's are in `data/simulations/tenant_b/{sim_id_b}/`. No file path overlap.

### Primary Runtime Call Stack

```text
[ENTRY — Tenant A] cse.py:create_simulation() → simulation_manager.prepare(db, "tenant_a", ...)
├── sim_id_a = uuid4()
└── sim_dir_a = CSE_DATA_DIR / "tenant_a" / sim_id_a
    ├── sim_dir_a / "cyber_actions.jsonl"
    ├── sim_dir_a / "cyber_agent_memory.db"
    ├── sim_dir_a / "run_state.json"
    ├── sim_dir_a / "simulation_config.json"
    ├── sim_dir_a / "ipc_commands/"
    └── sim_dir_a / "ipc_responses/"

[ENTRY — Tenant B, concurrent] cse.py:create_simulation() → simulation_manager.prepare(db, "tenant_b", ...)
├── sim_id_b = uuid4()
└── sim_dir_b = CSE_DATA_DIR / "tenant_b" / sim_id_b
    # completely separate directory tree — no shared files
```

### State And Data Transformations

- `tenant_id` is a path component in all sim directories — structural isolation by construction
- ArangoDB queries always include `FILTER r.tenant_id == @tenant_id`

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `N/A`

---

## Use Case: UC-CSE-16 — CSE frontend wizard (trigger → monitor → results)

### Goal
User navigates 5-step CSE wizard at `/dashboard/simulation`. Selects trigger type → previews attack surface count → launches simulation → watches `SimulationLivePanel` poll live status → sees `SimulationResultCard` when completed.

### Preconditions
- Authenticated session (next-auth JWT)
- API reachable at `NEXT_PUBLIC_API_URL`

### Expected Outcome
`sim_id` returned from POST create. `SimulationLivePanel` polls `/v1/cse/simulations/{sim_id}/status` every 3s and updates. On `status: completed`, `SimulationResultCard` renders `chain_probability`, `board_narrative`, `top_3_actions`.

### Primary Runtime Call Stack

```text
[ENTRY — browser] frontend/app/dashboard/simulation/page.tsx
│
│  ── Step 1: Configure ──────────────────────────────────────────────────────
├── page.tsx:_setTriggerType(trigger_type)  [STATE]
│
│  ── Step 2: Preview attack surface ─────────────────────────────────────────
├── page.tsx:_fetchAttackSurfacePreview()  [ASYNC]
│   └── fetch(`${API_URL}/v1/cse/simulations/preview`, {method: "GET", headers})  [IO]
│       # lightweight: returns {entity_count, trigger_type} without creating a run
│
│  ── Step 3: Launch ──────────────────────────────────────────────────────────
├── page.tsx:_launchSimulation()  [ASYNC]
│   ├── fetch(`${API_URL}/v1/cse/simulations/create`, {method: "POST", body: {trigger_type}})  [IO]
│   │   └── returns {sim_id, status: "queued"}
│   ├── page.tsx:_setSimId(sim_id)  [STATE]
│   └── page.tsx:_setStep("monitor")  [STATE]
│
│  ── Step 4: Monitor ─────────────────────────────────────────────────────────
├── frontend/components/situation/SimulationLivePanel.tsx:SimulationLivePanel({simId})
│   ├── useEffect: setInterval(poll, 3000)
│   │   ├── getSession() → accessToken
│   │   ├── fetch(`${API_URL}/v1/cse/simulations/${simId}/status`, {headers})  [IO]
│   │   │   └── returns CSERunStatus
│   │   ├── setRun(CSERunStatus)  [STATE]
│   │   └── on TERMINAL_STATUSES.has(status) → clearInterval + onComplete(run)
│   └── renders: progress bar (current_round/total_rounds), agent_count, recent_events feed
│
│  ── Step 5: Results ─────────────────────────────────────────────────────────
└── frontend/components/situation/SimulationResultCard.tsx:SimulationResultCard({run: CSERunStatus})
    # rendered when onComplete fires
    ├── renders: chain_count, chain_probability, top_3_actions[0..2]
    ├── renders: board_narrative excerpt
    └── "Ask Complira" button → router.push(`/dashboard/chat?prompt=...`)
```

### Branching / Fallback Paths

```text
[ERROR] POST /create returns 422 (empty attack surface)
page.tsx:_launchSimulation()
└── setError("No attack surface data found for this tenant") [STATE]
    # step stays at "launch"; user sees error message
```

```text
[ERROR] poll returns status: "failed"
SimulationLivePanel.tsx: status in TERMINAL_STATUSES
└── onComplete(run) called with status="failed"
    └── page.tsx renders failure message with sim_id for support reference
```

### State And Data Transformations

- Step selection: `step: "configure" | "preview" | "launch" | "monitor" | "results"` — React state
- `CSERunStatus` → `SimulationLivePanel` display (progress + event feed)
- `CSERunStatus` (completed) → `SimulationResultCard` display (chain_probability, top_3_actions, board_narrative)

### Observability And Debug Points

- Browser: step state visible in React devtools
- Network: poll requests to `/v1/cse/simulations/{sim_id}/status` visible in browser devtools

### Design Smells / Gaps

- Any legacy/backward-compatibility branch present? No
- Any naming-to-responsibility drift detected? No

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `Covered` (422 empty surface; failed status)

---

## Use Case: UC-CSE-DR-01 — Subprocess crash recovery via run_state.json

### Goal (Design-Risk)
When the simulation subprocess crashes (non-zero exit), `run_state.json` is updated to `status: failed` by `CyberSimulationRunner._monitor_subprocess()`. `GET /v1/cse/simulations/{sim_id}/status` reflects FAILED. No zombie RUNNING state persists across API restart.

### Preconditions
- Simulation is RUNNING; subprocess crashes with exit code 1

### Expected Outcome
`run_state.json` shows `status: failed`. GET status endpoint returns `status: failed`. Write-back is NOT called.

### Primary Runtime Call Stack

```text
[SUBPROCESS CRASH]
run_parallel_cyber_simulation.py:main() → unhandled exception → sys.exit(1)

[MONITOR THREAD — runner.py]
runner.py:_monitor_subprocess()
├── proc.poll() returns 1 (non-zero)
├── runner.py:_transition(RUNNING → FAILED) [STATE]
└── runner.py:_write_run_state() [IO]
    # run_state.json: {status: "failed", updated_at: ISO}

[ON GET STATUS]
cse.py:get_simulation_status(sim_id)
└── _read_run_state() → {status: "failed"} [IO]
    └── return JSONResponse({status: "failed", ...})
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `Covered`

---

## Use Case: UC-CSE-DR-02 — Profile gen partial failure with Semaphore(3)

### Goal (Design-Risk)
With `asyncio.Semaphore(3)`, the 4th and 5th profile generation tasks queue behind the first 3. A 429 rate limit on one task causes exponential backoff retry without failing all 5 profiles.

### Preconditions
- Claude API under rate pressure; 5 concurrent profile gen calls attempted

### Expected Outcome
All 5 profiles eventually generated. No 429 error propagated to caller if retry succeeds within 3 attempts.

### Primary Runtime Call Stack

```text
profile_generator.py:generate_all(entities)
├── asyncio.gather(5 tasks with Semaphore(3))
│   Tasks 1, 2, 3: acquire semaphore immediately → call Claude
│   Tasks 4, 5: wait for semaphore slot
│
│   Task 2: Claude returns 429
│   ├── asyncio.sleep(2^retry_count * 1.0) [ASYNC]
│   └── retry: anthropic.messages.create() [ASYNC] [IO] → success
│
│   Task 4: acquires slot from task 2 after semaphore release
│   └── Claude call succeeds
│
└── all 5 profiles returned successfully
```

```text
[ERROR] all 3 retries exhausted for one profile
_generate_profile() raises ProfileGenerationError
└── asyncio.gather() propagates first exception
    └── simulation_manager.py → run_state = FAILED
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `Covered` (Semaphore queue)
- Error Path: `Covered` (max retries exhausted)
