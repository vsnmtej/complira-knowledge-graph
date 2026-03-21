# Future-State Runtime Call Stacks (Debug-Trace Style)

This document models the **future-state (`to-be`)** execution behavior of the Complira Knowledge Graph Engine based on the proposed design. These are not traces of current code (which doesn't exist yet) but execution models for implementation.

## Conventions

- **Frame format:** `path/to/file.py:function_name(args?)`
- **Boundary tags:**
  - `[ENTRY]` - External entrypoint (CLI/API/scheduled trigger)
  - `[ASYNC]` - Async boundary (`await`, concurrent execution)
  - `[STATE]` - In-memory state mutation
  - `[IO]` - File/network/database/cache IO
  - `[FALLBACK]` - Non-primary branch (error handling, cache miss)
  - `[ERROR]` - Error path
- **Comments:** Inline comments with `# ...`
- **No legacy branches:** Greenfield project, all code is new

---

## Design Basis

- **Scope Classification:** `LARGE`
- **Call Stack Version:** `v1`
- **Requirements:** `tickets/in-progress/complira-knowledge-graph/requirements.md` (status: `Design-ready`)
- **Source Artifact:** `tickets/in-progress/complira-knowledge-graph/proposed-design.md` (v1)
- **Referenced Sections:**
  - Target Architecture Shape And Boundaries
  - File And Module Breakdown
  - Data Flow Diagrams
  - Error Handling Strategy

---

## Future-State Modeling Rule

✅ **This document models target design behavior** (to-be), not current code (which doesn't exist yet).

Since this is a greenfield project, all call stacks represent the intended implementation from proposed-design.md v1.

---

## Use Case Index (Stable IDs)

| use_case_id | Source Type | Requirement ID(s) | Design-Risk Objective | Use Case Name | Coverage |
| --- | --- | --- | --- | --- | --- |
| UC-001 | Requirement | FR-1, FR-2, NFR-1 | N/A | Initial Knowledge Graph Seeding | Primary/Fallback/Error |
| UC-002 | Requirement | FR-1, FR-4, NFR-2 | N/A | Incremental Updates | Primary/Fallback/Error |
| UC-003 | Requirement | FR-3 | N/A | LLM Gap Filling - CWE Classification | Primary/Error |
| UC-004 | Requirement | FR-3, FR-4 | N/A | VEX Justification Generation | Primary/Fallback/Error |
| UC-005 | Requirement | FR-4 | N/A | Regulatory Blast Radius Query | Primary/Error |
| UC-DRA | Design-Risk | NFR-2 | NVD API circuit breaker during 503 storm | NVD Circuit Breaker Activation | Primary/Fallback |
| UC-DRB | Design-Risk | NFR-2 | LLM API failure handling with DLQ | LLM Dead Letter Queue Retry | Primary/Fallback/Error |

**Coverage Rule:** All 5 functional requirements (FR-1 to FR-4, NFR-2) mapped to use cases ✅

---

## Transition Notes

**N/A - Greenfield Project**

No migration from existing system. All code will be implemented according to these call stacks.

---

## Use Case: UC-001 - Initial Knowledge Graph Seeding

### Goal

Execute full initial seeding of all 40+ data sources into ArangoDB in dependency order, creating ~10M nodes and ~28M edges.

### Preconditions

- ArangoDB 3.12 running and accessible
- `.env` file configured with API keys (NVD, GitHub, VulnCheck, Anthropic)
- Database `complira` exists but collections are empty
- User has network access to all data sources

### Expected Outcome

- All 36 document collections created with data
- All 41 edge collections created with relationships
- Prometheus metrics recorded (duration, record counts, error rates)
- CLI reports completion with summary statistics

### Primary Runtime Call Stack

```text
[ENTRY] src/complira_graph/cli.py:seed()
├── click.echo("Starting initial seed...") # User feedback
├── src/complira_graph/config.py:load_settings() [IO]
│   └── pydantic_settings.BaseSettings.from_dotenv() # Load .env
├── src/complira_graph/db.py:get_db() [IO]
│   ├── arango.ArangoClient(hosts=...) # Connect to ArangoDB
│   └── client.db("complira", username=..., password=...) # Auth
├── src/complira_graph/db.py:init_schema(db) [IO] # First-time schema creation
│   ├── db.create_collection("vulnerabilities", ...) # Create 36 doc collections
│   ├── db.create_collection("has_weakness", edge=True, ...) # Create 41 edge collections
│   └── db.create_index("vulnerabilities", fields=["cve_id"], unique=True) # Create indexes
├── src/complira_graph/orchestrator/dag.py:build_dag() [STATE]
│   ├── # Define agent dependencies: CWE → NVD, ATT&CK → CAPEC, etc.
│   ├── graphlib.TopologicalSorter(dependencies) # Build dependency graph
│   └── toposort.static_order() # Return ordered layers
├── src/complira_graph/orchestrator/seed.py:execute_seed_dag(agents, db) [ASYNC]
│   ├── # Layer 1: No dependencies (CWE, ATT&CK, OSCAL, etc.)
│   ├── asyncio.Semaphore(4) # Limit to 4 concurrent bulk writers
│   ├── [ASYNC] asyncio.gather([agent.run() for agent in layer1], semaphore=sem)
│   │   ├── src/complira_graph/agents/cwe.py:CWEAgent.run()
│   │   │   ├── self.check_for_updates() → False # First run, no checkpoint
│   │   │   ├── self.fetch_data() [IO]
│   │   │   │   ├── httpx.get("https://cwe.mitre.org/data/xml/cwec_latest.xml.zip")
│   │   │   │   ├── zipfile.ZipFile(...).extractall()
│   │   │   │   └── return {"xml_path": "/tmp/cwec_latest.xml"}
│   │   │   ├── self.transform_data(raw) [STATE]
│   │   │   │   ├── lxml.etree.iterparse(xml_path, tag="Weakness")
│   │   │   │   ├── for elem in weaknesses:
│   │   │   │   │   ├── weakness_model = models.Weakness(
│   │   │   │   │   │   _key=transforms.cwe_key(elem.get("ID")), # CWE_79
│   │   │   │   │   │   cwe_id=elem.get("ID"),
│   │   │   │   │   │   name=elem.find("Name").text,
│   │   │   │   │   │   ...
│   │   │   │   │   │   )
│   │   │   │   │   └── weaknesses_list.append(weakness_model.model_dump())
│   │   │   │   └── return weaknesses_list # ~930 CWEs
│   │   │   ├── self.load_data(transformed) [IO]
│   │   │   │   ├── db.collection("weaknesses").import_bulk(
│   │   │   │   │   transformed,
│   │   │   │   │   on_duplicate="update", # Idempotent
│   │   │   │   │   batch_size=50000
│   │   │   │   │   ) # Bulk import (0.03s for 1,000 docs vs 6s with UPSERT)
│   │   │   │   └── return IngestionResult(success=True, records=930, duration=1.2)
│   │   │   ├── monitoring.metrics.record_ingestion("cwe", result) [IO]
│   │   │   └── structlog.info("CWE agent complete", records=930, duration=1.2)
│   │   ├── src/complira_graph/agents/attack.py:ATTACKAgent.run()
│   │   │   ├── # Similar flow: fetch STIX bundles from GitHub → transform → bulk load
│   │   │   └── return IngestionResult(success=True, records=691, duration=3.5)
│   │   ├── src/complira_graph/agents/oscal.py:OSCALAgent.run()
│   │   │   ├── # Fetch NIST 800-53 Rev 5 JSON → transform → bulk load
│   │   │   └── return IngestionResult(success=True, records=1007, duration=2.1)
│   │   └── [3 more agents in parallel, max 4 concurrent via semaphore]
│   ├── # Wait for Layer 1 to complete before Layer 2
│   ├── # Layer 2: Depends on Layer 1 (NVD → CWE, CAPEC → ATT&CK, etc.)
│   ├── [ASYNC] asyncio.gather([agent.run() for agent in layer2], semaphore=sem)
│   │   ├── src/complira_graph/agents/nvd.py:NVDAgent.run()
│   │   │   ├── self.check_for_updates() → False # First run
│   │   │   ├── self.fetch_data() [IO]
│   │   │   │   ├── # NVD API 2.0: /vulnerabilities
│   │   │   │   ├── rate_limiter.acquire("nvd", Rate(50, Duration.SECOND * 30))
│   │   │   │   ├── @tenacity.retry(stop=stop_after_attempt(3), wait=wait_exponential())
│   │   │   │   ├── httpx.get("https://services.nvd.nist.gov/rest/json/cves/2.0",
│   │   │   │   │   params={"resultsPerPage": 2000, "startIndex": 0},
│   │   │   │   │   headers={"apiKey": settings.NVD_API_KEY}
│   │   │   │   │   )
│   │   │   │   ├── # Paginate through all ~318,000 CVEs (150+ pages)
│   │   │   │   └── return {"cves": [...]} # All CVE records
│   │   │   ├── self.transform_data(raw) [STATE]
│   │   │   │   ├── for cve in raw["cves"]:
│   │   │   │   │   ├── vuln_model = models.Vulnerability(
│   │   │   │   │   │   _key=transforms.cve_key(cve["id"]), # CVE_2024_1234
│   │   │   │   │   │   cve_id=cve["id"],
│   │   │   │   │   │   description=cve["descriptions"][0]["value"],
│   │   │   │   │   │   cvss_v31=cve["metrics"]["cvssMetricV31"][0] if present,
│   │   │   │   │   │   ...
│   │   │   │   │   │   )
│   │   │   │   │   ├── vulnerabilities_list.append(vuln_model.model_dump())
│   │   │   │   │   ├── # Extract CWE relationships
│   │   │   │   │   ├── for weakness in cve.get("weaknesses", []):
│   │   │   │   │   │   ├── edge_model = models.HasWeakness(
│   │   │   │   │   │   │   _from=f"vulnerabilities/{vuln._key}",
│   │   │   │   │   │   │   _to=f"weaknesses/{transforms.cwe_key(weakness['cweId'])}",
│   │   │   │   │   │   │   source="nvd",
│   │   │   │   │   │   │   type="Primary" if weakness['type'] == "Primary" else "Secondary"
│   │   │   │   │   │   │   )
│   │   │   │   │   │   └── edges_list.append(edge_model.model_dump())
│   │   │   │   └── return {"vulnerabilities": vulnerabilities_list, "edges": edges_list}
│   │   │   ├── self.load_data(transformed) [IO]
│   │   │   │   ├── db.collection("vulnerabilities").import_bulk(
│   │   │   │   │   transformed["vulnerabilities"],
│   │   │   │   │   on_duplicate="update",
│   │   │   │   │   batch_size=50000
│   │   │   │   │   ) # Load ~318K CVEs
│   │   │   │   ├── db.collection("has_weakness").import_bulk(
│   │   │   │   │   transformed["edges"],
│   │   │   │   │   on_duplicate="update",
│   │   │   │   │   batch_size=100000
│   │   │   │   │   ) # Load CWE edges
│   │   │   │   └── return IngestionResult(success=True, records=318000, duration=1200)
│   │   │   ├── monitoring.metrics.record_ingestion("nvd", result) [IO]
│   │   │   └── structlog.info("NVD agent complete", records=318000, duration=1200)
│   │   ├── src/complira_graph/agents/capec.py:CAPECAgent.run()
│   │   │   ├── # Fetch CAPEC XML → parse → create attack_patterns + capec_maps_to_attack edges
│   │   │   └── return IngestionResult(success=True, records=559, duration=4.2)
│   │   └── [5+ more agents depending on Layer 1]
│   ├── # Layers 3-5: Continue DAG execution
│   ├── [ASYNC] asyncio.gather([agent.run() for agent in layer3], semaphore=sem)
│   ├── [ASYNC] asyncio.gather([agent.run() for agent in layer4], semaphore=sem)
│   ├── [ASYNC] asyncio.gather([agent.run() for agent in layer5], semaphore=sem)
│   └── structlog.info("All deterministic agents complete", total_records=10000000, duration=18000)
├── # LLM Enrichment Layer (Sequential after deterministic pipeline)
├── src/complira_graph/llm_agents/cwe_classifier.py:CWEClassifierAgent.run()
│   ├── self.find_gaps() [IO] # AQL query for CVEs without CWE
│   │   ├── db.aql.execute("""
│   │   │   FOR v IN vulnerabilities
│   │   │   LET has_cwe = LENGTH(FOR e IN has_weakness FILTER e._from == CONCAT("vulnerabilities/", v._key) RETURN 1) > 0
│   │   │   FILTER !has_cwe AND v.description != null
│   │   │   RETURN {_key: v._key, cve_id: v.cve_id, description: v.description}
│   │   │   """)
│   │   └── return unclassified_cves # ~25,000 CVEs
│   ├── self.enrich(unclassified_cves) [IO] [ASYNC]
│   │   ├── # Batch processing: 1,000 CVEs per batch
│   │   ├── for batch in chunks(unclassified_cves, 1000):
│   │   │   ├── # Load top 200 CWEs for reference
│   │   │   ├── cwe_reference_list = db.collection("weaknesses").all(limit=200)
│   │   │   ├── for cve in batch:
│   │   │   │   ├── prompt = build_prompt(cve, cwe_reference_list) # From LLM_Enhancement.rtf
│   │   │   │   ├── anthropic.messages.create(
│   │   │   │   │   model="claude-haiku-4.5",
│   │   │   │   │   max_tokens=500,
│   │   │   │   │   messages=[{"role": "user", "content": prompt}],
│   │   │   │   │   system=SYSTEM_PROMPT # CWE classifier system prompt
│   │   │   │   │   ) [IO] [ASYNC]
│   │   │   │   ├── response = {"classifications": [{"cwe_id": "CWE-79", "confidence": 0.92, "reasoning": "..."}]}
│   │   │   │   ├── monitoring.metrics.record_llm_tokens("claude-haiku-4.5", usage.input_tokens, usage.output_tokens)
│   │   │   │   └── enrichments_list.append({"cve_key": cve._key, "classifications": response})
│   │   ├── return enrichments_list # ~25,000 enrichments
│   ├── self.validate(enrichments) [STATE]
│   │   ├── # Filter by confidence threshold
│   │   ├── valid_enrichments = [e for e in enrichments if e["confidence"] >= 0.85] # Auto-apply
│   │   ├── review_queue = [e for e in enrichments if 0.5 <= e["confidence"] < 0.85] # Human review
│   │   └── return {"valid": valid_enrichments, "review": review_queue}
│   ├── self.persist(valid_enrichments) [IO]
│   │   ├── # Create has_weakness edges
│   │   ├── edges = [models.HasWeakness(
│   │   │   _from=f"vulnerabilities/{e['cve_key']}",
│   │   │   _to=f"weaknesses/{transforms.cwe_key(e['cwe_id'])}",
│   │   │   source="llm_cwe_classifier",
│   │   │   confidence=e["confidence"]
│   │   │   ) for e in valid_enrichments]
│   │   ├── db.collection("has_weakness").import_bulk(edges, on_duplicate="update")
│   │   ├── # Create llm_enrichments provenance records
│   │   ├── provenance = [models.LLMEnrichment(
│   │   │   _key=f"cwe_classifier_{e['cve_key']}", # Deterministic key
│   │   │   agent_type="cwe_classifier",
│   │   │   model="claude-haiku-4.5",
│   │   │   input_hash=hashlib.sha256(e["input"]).hexdigest(),
│   │   │   output=e["output"],
│   │   │   confidence=e["confidence"],
│   │   │   tokens_input=e["tokens_in"],
│   │   │   tokens_output=e["tokens_out"],
│   │   │   cost_usd=e["cost"],
│   │   │   timestamp=datetime.now()
│   │   │   ) for e in valid_enrichments]
│   │   ├── db.collection("llm_enrichments").import_bulk(provenance, on_duplicate="update")
│   │   └── return IngestionResult(success=True, records=len(valid_enrichments), cost=2.50)
│   ├── monitoring.metrics.record_llm_enrichment("cwe_classifier", result) [IO]
│   └── structlog.info("CWE classifier complete", records=20000, cost_usd=2.50)
├── # More LLM agents (L2-L9) run sequentially...
├── src/complira_graph/llm_agents/purl_cpe_resolver.py:PURLCPEResolverAgent.run()
├── src/complira_graph/llm_agents/regulatory_mapper.py:RegulatoryMapperAgent.run()
├── # All enrichment complete
├── src/complira_graph/monitoring/metrics.py:export_prometheus_metrics() [IO]
└── cli.py:seed() → click.echo(f"Seed complete: {total_records} records in {duration}s, LLM cost: ${llm_cost}")
```

### Branching / Fallback Paths

#### [FALLBACK] Schema Already Exists

```text
src/complira_graph/db.py:init_schema(db) [IO]
├── try:
│   └── db.create_collection("vulnerabilities", ...)
├── except arango.exceptions.CollectionCreateError as e:
│   ├── if e.error_code == 1207: # Collection already exists
│   │   ├── structlog.warn("Collection exists, skipping creation", collection="vulnerabilities")
│   │   └── continue # Skip to next collection
│   └── else:
│       └── raise # Re-raise unexpected errors
```

#### [FALLBACK] NVD API Rate Limit Hit (429)

```text
src/complira_graph/agents/nvd.py:NVDAgent.fetch_data() [IO]
├── @tenacity.retry(
│   stop=stop_after_attempt(5),
│   wait=wait_exponential(multiplier=1, min=4, max=60),
│   retry=retry_if_exception_type(httpx.HTTPStatusError) and status_code == 429
│   )
├── rate_limiter.acquire("nvd", Rate(50, Duration.SECOND * 30)) # Blocks if rate exceeded
├── httpx.get(...) → raises httpx.HTTPStatusError(429)
├── # tenacity catches, waits (exponential backoff), retries
└── # Max 5 attempts, then raises if all fail
```

### Error Paths

#### [ERROR] Agent Fetch Failure After Retries

```text
src/complira_graph/orchestrator/seed.py:execute_seed_dag()
├── try:
│   └── [ASYNC] agent.run() → raises httpx.HTTPError after 3 retries
├── except Exception as e:
│   ├── structlog.error("Agent failed", agent=agent.name, error=str(e), exc_info=True)
│   ├── monitoring.metrics.record_agent_failure(agent.name, error=str(e))
│   ├── # Store failure in dead letter queue
│   ├── dlq.add_failure(agent_id=agent.name, error=str(e), retry_in="1h")
│   └── # Continue with other agents (don't block entire seed)
└── # At end of seed, report failed agents to user
    └── click.echo(f"Seed completed with {len(failed_agents)} failures: {failed_agents}", fg="yellow")
```

#### [ERROR] Database Connection Failure

```text
src/complira_graph/db.py:get_db() [IO]
├── try:
│   └── arango.ArangoClient(hosts=settings.ARANGO_HOST).db(...)
├── except arango.exceptions.ServerConnectionError as e:
│   ├── structlog.error("Failed to connect to ArangoDB", error=str(e))
│   ├── click.echo(f"ERROR: Cannot connect to ArangoDB at {settings.ARANGO_HOST}", fg="red")
│   └── sys.exit(1) # Fatal error, abort seed
```

---

## Use Case: UC-002 - Incremental Updates

### Goal

Update graph with only changed/new records from data sources, triggered hourly/daily/weekly by Prefect scheduler.

### Preconditions

- Initial seed completed (UC-001)
- Prefect server running with deployed schedules
- Checkpoint metadata exists in `_checkpoint` collection

### Expected Outcome

- Only delta records fetched and upserted
- Checkpoint metadata updated with latest timestamps
- Prometheus metrics show incremental record counts (not full dataset)

### Primary Runtime Call Stack

```text
[ENTRY] Prefect scheduled trigger (cron: "0 */2 * * *") # Every 2 hours
├── prefect.deployments.run("nvd-update-flow")
├── src/complira_graph/orchestrator/schedules.py:nvd_update_flow() [ASYNC]
│   ├── db = get_db() [IO]
│   ├── agent = NVDAgent(db=db)
│   ├── has_updates = agent.check_for_updates() [IO]
│   │   ├── # Load checkpoint from ArangoDB
│   │   ├── checkpoint = db.collection("_checkpoint").get("nvd") [IO]
│   │   ├── last_modified = checkpoint["last_modified"] if checkpoint else "1999-01-01T00:00:00"
│   │   ├── # NVD API: Check if any CVEs modified since last_modified
│   │   ├── httpx.get("https://services.nvd.nist.gov/rest/json/cves/2.0",
│   │   │   params={"lastModStartDate": last_modified, "lastModEndDate": datetime.now(), "resultsPerPage": 1}
│   │   │   ) [IO]
│   │   ├── response.json()["totalResults"] > 0 → True # Updates available
│   │   └── return True
│   ├── if has_updates:
│   │   ├── result = agent.run(incremental=True) [ASYNC]
│   │   │   ├── self.fetch_data(delta_only=True) [IO]
│   │   │   │   ├── # Fetch only CVEs modified since checkpoint.last_modified
│   │   │   │   ├── httpx.get("https://services.nvd.nist.gov/rest/json/cves/2.0",
│   │   │   │   │   params={"lastModStartDate": checkpoint["last_modified"], "resultsPerPage": 2000}
│   │   │   │   │   )
│   │   │   │   └── return {"cves": [...]} # Only ~1,000 modified CVEs (not all 318K)
│   │   │   ├── self.transform_data(raw) # Same as full seed
│   │   │   ├── self.load_data(transformed) [IO]
│   │   │   │   ├── db.collection("vulnerabilities").import_bulk(
│   │   │   │   │   transformed["vulnerabilities"],
│   │   │   │   │   on_duplicate="update", # Upsert: update existing, insert new
│   │   │   │   │   batch_size=50000
│   │   │   │   │   ) # Only 1,000 records, not 318K
│   │   │   │   └── return IngestionResult(success=True, records=1000, duration=30)
│   │   │   ├── # Update checkpoint
│   │   │   ├── db.collection("_checkpoint").update(
│   │   │   │   "_key": "nvd",
│   │   │   │   "last_modified": datetime.now().isoformat(),
│   │   │   │   "last_run": datetime.now().isoformat()
│   │   │   │   ) [IO]
│   │   │   └── return result
│   │   ├── monitoring.metrics.record_incremental_update("nvd", result) [IO]
│   │   └── structlog.info("NVD incremental update complete", records=1000, duration=30)
│   └── else:
│       ├── structlog.info("No NVD updates available, skipping")
│       └── monitoring.metrics.record_no_update("nvd")
└── prefect.deployments.complete()
```

### Branching / Fallback Paths

#### [FALLBACK] No Checkpoint Exists (First Incremental Run)

```text
agent.check_for_updates() [IO]
├── checkpoint = db.collection("_checkpoint").get("nvd") [IO]
├── if checkpoint is None:
│   ├── structlog.warn("No checkpoint found, treating as initial run", agent="nvd")
│   ├── last_modified = "1999-01-01T00:00:00" # Default to earliest date
│   └── # Will fetch all records (essentially a full seed)
```

#### [FALLBACK] Incremental Fetch Exceeds Max Range (120 days for NVD)

```text
agent.fetch_data(delta_only=True) [IO]
├── days_since_last_run = (datetime.now() - checkpoint["last_modified"]).days
├── if days_since_last_run > 120: # NVD max range
│   ├── structlog.warn("Time range exceeds NVD max, splitting into chunks", days=days_since_last_run)
│   ├── for chunk in split_date_range(checkpoint["last_modified"], datetime.now(), chunk_size=120):
│   │   ├── httpx.get(..., params={"lastModStartDate": chunk.start, "lastModEndDate": chunk.end})
│   │   └── results.extend(response.json()["vulnerabilities"])
│   └── return {"cves": results} # Combined from multiple chunks
```

### Error Paths

#### [ERROR] Prefect Flow Failure

```text
src/complira_graph/orchestrator/schedules.py:nvd_update_flow() [ASYNC]
├── try:
│   └── agent.run(incremental=True) → raises Exception
├── except Exception as e:
│   ├── structlog.error("Incremental update failed", agent="nvd", error=str(e), exc_info=True)
│   ├── monitoring.metrics.record_agent_failure("nvd", error=str(e))
│   ├── # Prefect automatically handles retries (configured in deployment)
│   └── raise # Prefect marks flow as failed, will retry per schedule
```

---

## Use Case: UC-003 - LLM Gap Filling - CWE Classification

### Goal

Classify ~25,000 NVD CVEs without CWE classification using Claude Haiku 4.5, creating `has_weakness` edges with provenance.

### Preconditions

- Deterministic ingestion complete (NVD CVEs loaded)
- `weaknesses` collection populated with CWEs
- Anthropic API key configured in `.env`

### Expected Outcome

- ~20,000 high-confidence CWE classifications created (confidence >= 0.85)
- ~5,000 low-confidence classifications flagged for human review
- All enrichments tracked in `llm_enrichments` collection with provenance
- LLM cost recorded in Prometheus (~$2.50 for 25K CVEs)

### Primary Runtime Call Stack

(Already detailed in UC-001 LLM Enrichment section, extracted here for clarity)

```text
[ENTRY] src/complira_graph/llm_agents/cwe_classifier.py:CWEClassifierAgent.run()
├── self.find_gaps() [IO] # Query for unclassified CVEs (already detailed above)
├── self.enrich(unclassified_cves) [IO] [ASYNC] # Claude API calls (already detailed above)
├── self.validate(enrichments) [STATE] # Confidence filtering (already detailed above)
├── self.persist(valid_enrichments) [IO] # Create edges + provenance (already detailed above)
└── return IngestionResult(success=True, records=20000, cost=2.50)
```

### Error Paths

#### [ERROR] Anthropic API Rate Limit (529)

```text
self.enrich(unclassified_cves) [IO] [ASYNC]
├── for cve in batch:
│   ├── @tenacity.retry(
│   │   stop=stop_after_attempt(5),
│   │   wait=wait_exponential(multiplier=2, min=4, max=60),
│   │   retry=retry_if_exception_type(anthropic.RateLimitError)
│   │   )
│   ├── anthropic.messages.create(...) → raises anthropic.RateLimitError
│   ├── # tenacity waits 4s, 8s, 16s, 32s, 60s (exponential backoff)
│   └── # After 5 failed attempts:
│       ├── structlog.error("LLM API rate limit exceeded after retries", cve_id=cve.cve_id)
│       ├── # Add to dead letter queue
│       ├── dlq.add_llm_failure(
│       │   agent="cwe_classifier",
│       │   input_payload={"cve_id": cve.cve_id, "description": cve.description},
│       │   error="RateLimitError after 5 retries",
│       │   retry_at=datetime.now() + timedelta(hours=1)
│       │   ) [IO]
│       └── continue # Skip this CVE, process next
```

#### [ERROR] Anthropic API Authentication Failure (401)

```text
self.enrich(unclassified_cves) [IO] [ASYNC]
├── anthropic.messages.create(...) → raises anthropic.AuthenticationError(401)
├── # No retry for auth errors (will never succeed)
├── structlog.error("Anthropic API key invalid or missing", error=str(e))
├── click.echo("ERROR: Invalid Anthropic API key. Check ANTHROPIC_API_KEY in .env", fg="red")
└── sys.exit(1) # Fatal error, abort entire LLM enrichment
```

---

## Use Case: UC-004 - VEX Justification Generation

### Goal

Generate VEX (Vulnerability Exploitability eXchange) document for a given CVE+Component pair by querying graph for all evidence and synthesizing justification with Claude Sonnet 4.5.

### Preconditions

- Graph fully populated (deterministic + LLM enrichment)
- SBOM uploaded and parsed into `components` collection
- Vulnerabilities affecting components identified via `affects` edges

### Expected Outcome

- VEX document with status (affected/not_affected/fixed/under_investigation)
- Justification with specific evidence citations
- Full provenance tracked in `llm_enrichments`
- Generated in <30 seconds

### Primary Runtime Call Stack

```text
[ENTRY] src/complira_graph/cli.py:generate_vex(sbom_path, output_path)
├── click.echo("Parsing SBOM...")
├── src/complira_graph/transforms/sbom_parser.py:parse_cyclonedx(sbom_path) [IO]
│   ├── with open(sbom_path) as f:
│   │   └── sbom_data = json.load(f)
│   ├── for component in sbom_data["components"]:
│   │   ├── purl = component["purl"] # pkg:pypi/requests@2.31.0
│   │   ├── purl_key = transforms.purl_key(purl) # pkg_pypi_requests_2_31_0
│   │   └── components_list.append({"purl": purl, "_key": purl_key})
│   └── return components_list # ~200 components in typical SBOM
├── db = get_db() [IO]
├── vex_agent = src/complira_graph/llm_agents/vex_synthesizer.py:VEXSynthesizerAgent(db=db)
├── vex_documents = []
├── for component in components_list:
│   ├── # Query graph for vulnerabilities affecting this component
│   ├── vulnerabilities = db.aql.execute("""
│   │   FOR v IN vulnerabilities
│   │       FOR e IN affects
│   │           FILTER e._to == @component_id
│   │           AND e._from == CONCAT("vulnerabilities/", v._key)
│   │       RETURN {cve_id: v.cve_id, _key: v._key}
│   │   """, bind_vars={"component_id": f"components/{component['_key']}"}) [IO]
│   ├── # For each CVE affecting this component:
│   ├── for vuln in vulnerabilities: # ~10-50 CVEs per component
│   │   ├── # Collect all evidence from graph (CWE, EPSS, KEV, exploits, hardening, SAST/DAST)
│   │   ├── evidence = vex_agent.collect_evidence(vuln["_key"], component["_key"]) [IO]
│   │   │   ├── # AQL query to collect evidence (from proposed-design.md)
│   │   │   ├── db.aql.execute("""
│   │   │   │   LET vuln = DOCUMENT("vulnerabilities/@vuln_key")
│   │   │   │   LET comp = DOCUMENT("components/@comp_key")
│   │   │   │   LET cwe_data = (FOR cwe IN 1..1 OUTBOUND vuln has_weakness RETURN {cwe_id: cwe.cwe_id, name: cwe.name})
│   │   │   │   LET epss = {score: vuln.epss_score, percentile: vuln.epss_percentile}
│   │   │   │   LET is_kev = LENGTH(FOR k IN kev_entries FILTER k._key == vuln._key RETURN 1) > 0
│   │   │   │   LET exploits = (FOR exp IN 1..1 OUTBOUND vuln has_exploit RETURN {source: exp.source, type: exp.type})
│   │   │   │   LET hardening = (FOR h IN 1..1 OUTBOUND comp has_hardening_profile RETURN {pie: h.pie, nx: h.nx, aslr: h.aslr})
│   │   │   │   LET sast = (FOR f IN sast_findings FILTER f.tenant_id == @tenant FOR e IN found_in_component FILTER e._from == f._id AND e._to == comp._id RETURN {rule: f.rule_id, severity: f.severity})
│   │   │   │   RETURN {vulnerability: {...}, weakness: cwe_data, exploits: exploits, component: {...}, hardening: hardening, sast_findings: sast, ...}
│   │   │   │   """, bind_vars={"vuln_key": vuln["_key"], "comp_key": component["_key"], "tenant": "default"})
│   │   │   └── return evidence_dict # Comprehensive evidence bundle
│   │   ├── # Call LLM to synthesize VEX justification
│   │   ├── vex_doc = vex_agent.synthesize_vex(evidence) [IO] [ASYNC]
│   │   │   ├── # Build prompt with evidence (from LLM_Enhancement.rtf)
│   │   │   ├── prompt = build_vex_prompt(evidence) # Detailed prompt with all evidence
│   │   │   ├── anthropic.messages.create(
│   │   │   │   model="claude-sonnet-4.5",
│   │   │   │   max_tokens=2000,
│   │   │   │   messages=[{"role": "user", "content": prompt}],
│   │   │   │   system=VEX_SYSTEM_PROMPT # From LLM_Enhancement.rtf
│   │   │   │   ) [IO] [ASYNC]
│   │   │   ├── response = anthropic.Message(content=...)
│   │   │   ├── vex_json = json.loads(response.content[0].text) # Parse structured output
│   │   │   ├── # Validate VEX schema
│   │   │   ├── vex_model = models.VEXJustification(
│   │   │   │   status=vex_json["status"], # affected | not_affected | fixed | under_investigation
│   │   │   │   justification=vex_json.get("justification"), # VEX justification category
│   │   │   │   impact_statement=vex_json["impact_statement"],
│   │   │   │   detail=vex_json["detail"], # Full reasoning with evidence references
│   │   │   │   evidence_citations=vex_json["evidence_citations"],
│   │   │   │   confidence=vex_json["confidence"],
│   │   │   │   recommended_action=vex_json["recommended_action"]
│   │   │   │   )
│   │   │   ├── monitoring.metrics.record_llm_tokens("claude-sonnet-4.5", response.usage.input_tokens, response.usage.output_tokens)
│   │   │   └── return vex_model
│   │   ├── # Persist VEX + provenance
│   │   ├── vex_agent.persist_vex(vex_doc, vuln["_key"], component["_key"]) [IO]
│   │   │   ├── # Store VEX document in vex_documents collection
│   │   │   ├── db.collection("vex_documents").insert({
│   │   │   │   "_key": f"vex_{vuln['_key']}_{component['_key']}",
│   │   │   │   "cve_id": vuln["cve_id"],
│   │   │   │   "component_purl": component["purl"],
│   │   │   │   "status": vex_doc.status,
│   │   │   │   "justification": vex_doc.justification,
│   │   │   │   "impact_statement": vex_doc.impact_statement,
│   │   │   │   "detail": vex_doc.detail,
│   │   │   │   "evidence_citations": vex_doc.evidence_citations,
│   │   │   │   "confidence": vex_doc.confidence,
│   │   │   │   "recommended_action": vex_doc.recommended_action,
│   │   │   │   "generated_at": datetime.now()
│   │   │   │   })
│   │   │   ├── # Store provenance
│   │   │   ├── db.collection("llm_enrichments").insert({
│   │   │   │   "_key": f"vex_synth_{vuln['_key']}_{component['_key']}",
│   │   │   │   "agent_type": "vex_synthesizer",
│   │   │   │   "model": "claude-sonnet-4.5",
│   │   │   │   "input_hash": hashlib.sha256(json.dumps(evidence).encode()).hexdigest(),
│   │   │   │   "output": vex_doc.model_dump(),
│   │   │   │   "confidence": vex_doc.confidence,
│   │   │   │   "tokens_input": response.usage.input_tokens,
│   │   │   │   "tokens_output": response.usage.output_tokens,
│   │   │   │   "cost_usd": calculate_cost(response.usage), # Sonnet pricing
│   │   │   │   "timestamp": datetime.now()
│   │   │   │   })
│   │   │   └── return vex_doc
│   │   └── vex_documents.append(vex_doc)
├── # Export VEX to CycloneDX VEX format
├── src/complira_graph/transforms/vex_exporter.py:export_to_cyclonedx_vex(vex_documents, output_path) [IO]
│   ├── cyclonedx_vex = {"bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1, "vulnerabilities": [...]}
│   ├── for vex in vex_documents:
│   │   └── cyclonedx_vex["vulnerabilities"].append({
│   │       "bom-ref": f"{vex.cve_id}-{vex.component_purl}",
│   │       "id": vex.cve_id,
│   │       "source": {"name": "Complira Knowledge Graph"},
│   │       "ratings": [...],
│   │       "analysis": {
│   │           "state": vex.status, # affected | not_affected | fixed | under_investigation
│   │           "justification": vex.justification, # component_not_present | vulnerable_code_not_reachable | ...
│   │           "response": [vex.recommended_action],
│   │           "detail": vex.detail # Full reasoning with evidence citations
│   │       }
│   │       })
│   ├── with open(output_path, "w") as f:
│   │   └── json.dump(cyclonedx_vex, f, indent=2)
│   └── return output_path
├── monitoring.metrics.record_vex_generation(len(vex_documents), duration=25.3, cost=4.50)
└── click.echo(f"VEX document generated: {output_path} ({len(vex_documents)} vulnerabilities)")
```

### Branching / Fallback Paths

#### [FALLBACK] No Evidence Found for CVE+Component

```text
vex_agent.collect_evidence(vuln_key, comp_key) [IO]
├── evidence = db.aql.execute(...) # Query returns empty CWE, no exploits, etc.
├── if evidence is empty or minimal:
│   ├── structlog.warn("Insufficient evidence for VEX generation", cve_id=vuln.cve_id, component=comp.purl)
│   ├── # Generate conservative VEX with "under_investigation" status
│   ├── vex_doc = models.VEXJustification(
│   │   status="under_investigation",
│   │   justification=None,
│   │   impact_statement="Insufficient evidence to determine exploitability",
│   │   detail="No CWE classification, SAST/DAST findings, or exploit intelligence available. Manual investigation required.",
│   │   evidence_citations=[],
│   │   confidence=0.0,
│   │   recommended_action="Conduct manual security assessment"
│   │   )
│   └── return vex_doc # Without calling LLM (saves cost)
```

### Error Paths

#### [ERROR] LLM Returns Invalid JSON

```text
vex_agent.synthesize_vex(evidence) [IO] [ASYNC]
├── response = anthropic.messages.create(...)
├── try:
│   └── vex_json = json.loads(response.content[0].text)
├── except json.JSONDecodeError as e:
│   ├── structlog.error("LLM returned invalid JSON", response=response.content[0].text, error=str(e))
│   ├── # Retry with explicit JSON schema in prompt (second attempt)
│   ├── prompt_with_schema = f"{prompt}\n\nYou MUST return valid JSON matching this schema: {VEX_SCHEMA}"
│   ├── response_retry = anthropic.messages.create(..., messages=[{"role": "user", "content": prompt_with_schema}])
│   ├── try:
│   │   └── vex_json = json.loads(response_retry.content[0].text)
│   └── except json.JSONDecodeError:
│       ├── # Both attempts failed, fallback to conservative VEX
│       ├── structlog.error("LLM JSON parsing failed after retry, using fallback VEX")
│       └── return models.VEXJustification(status="under_investigation", detail="LLM generation failed", confidence=0.0)
```

---

## Use Case: UC-005 - Regulatory Blast Radius Query

### Goal

Given a CVE ID, traverse the graph to find all affected regulatory requirements (CRA, FDA 524B, NIST 800-53, etc.) with full evidence chain.

### Preconditions

- Graph fully populated including CWE→requirement mappings
- LLM regulatory mapper (L4) has created `maps_to_requirement` edges

### Expected Outcome

- List of all regulatory requirements affected by the CVE
- Evidence chain: CVE → CWE → Requirement → Framework
- Query completes in <5 seconds

### Primary Runtime Call Stack

```text
[ENTRY] src/complira_graph/cli.py:regulatory_blast_radius(cve_id)
├── click.echo(f"Querying regulatory impact for {cve_id}...")
├── db = get_db() [IO]
├── # AQL traversal query (3-hop: CVE → CWE → Requirement → Framework)
├── results = db.aql.execute("""
│   FOR v IN vulnerabilities
│       FILTER v.cve_id == @cve_id
│       # Hop 1: CVE → CWEs
│       FOR cwe IN 1..1 OUTBOUND v has_weakness
│           # Hop 2: CWE → Regulatory Requirements
│           FOR req IN 1..1 OUTBOUND cwe maps_to_requirement
│               # Hop 3: Requirement → Framework metadata
│               RETURN {
│                   cve_id: v.cve_id,
│                   cvss_score: v.cvss_v31.baseScore,
│                   cwe_id: cwe.cwe_id,
│                   cwe_name: cwe.name,
│                   requirement_id: req.requirement_id,
│                   requirement_title: req.title,
│                   framework: req.framework, # CRA | FDA_524B | IEC_62304 | NIST_SSDF
│                   evidence_types: req.evidence_types, # [SAST, SCA, DAST, SBOM]
│                   deadline: req.deadline, # Compliance deadline (e.g., CRA Sept 2026)
│                   mapping_source: req.source # curated | llm_reg_mapper
│               }
│   """, bind_vars={"cve_id": cve_id}) [IO]
├── # Format results by framework
├── blast_radius = defaultdict(list)
├── for result in results:
│   └── blast_radius[result["framework"]].append(result)
├── # Display results
├── click.echo(f"\nRegulatory Blast Radius for {cve_id}:\n")
├── for framework, requirements in blast_radius.items():
│   ├── click.echo(f"  {framework}: {len(requirements)} requirements affected", fg="yellow")
│   └── for req in requirements:
│       └── click.echo(f"    - {req['requirement_id']}: {req['requirement_title']}")
│       └── click.echo(f"      CWE: {req['cwe_id']} ({req['cwe_name']})")
│       └── click.echo(f"      Evidence: {', '.join(req['evidence_types'])}")
│       └── click.echo(f"      Deadline: {req['deadline']}")
│       └── click.echo(f"      Source: {req['mapping_source']}")
├── monitoring.metrics.record_query_latency("regulatory_blast_radius", duration=3.2)
└── return blast_radius
```

### Branching / Fallback Paths

#### [FALLBACK] CVE Not Found in Database

```text
src/complira_graph/cli.py:regulatory_blast_radius(cve_id)
├── results = db.aql.execute(...)
├── if len(results) == 0:
│   ├── # Check if CVE exists at all
│   ├── cve_exists = db.collection("vulnerabilities").find({"cve_id": cve_id}).count() > 0
│   ├── if not cve_exists:
│   │   ├── click.echo(f"ERROR: CVE {cve_id} not found in database. Run 'complira update' to fetch latest CVEs.", fg="red")
│   │   └── sys.exit(1)
│   └── else:
│       ├── # CVE exists but has no CWE mappings (and thus no regulatory mappings)
│       ├── click.echo(f"WARNING: {cve_id} has no CWE classification. No regulatory impact can be determined.", fg="yellow")
│       ├── click.echo("Recommendation: Wait for LLM CWE classifier to process this CVE, or manually classify.")
│       └── return {} # Empty blast radius
```

### Error Paths

#### [ERROR] Query Timeout (>10 seconds)

```text
db.aql.execute(query, bind_vars=...) [IO]
├── # ArangoDB query timeout (configured in db.py connection)
├── try:
│   └── db.aql.execute(..., ttl=10) # 10-second timeout
├── except arango.exceptions.AQLQueryExecuteError as e:
│   ├── if "query timed out" in str(e).lower():
│   │   ├── structlog.error("Regulatory blast radius query timed out", cve_id=cve_id, error=str(e))
│   │   ├── click.echo(f"ERROR: Query timed out. This may indicate missing indexes or large result set.", fg="red")
│   │   └── click.echo("Recommendation: Check ArangoDB query profile and indexes on has_weakness/maps_to_requirement edges.")
│   └── raise # Re-raise for other AQL errors
```

---

## Use Case: UC-DRA - NVD Circuit Breaker Activation (Design Risk)

### Goal

**Design-Risk Objective:** Prevent NVD agent from hammering API during known 503 error storms (NVD enrichment pauses). Circuit breaker opens after 5 consecutive failures, waits 30 minutes before retry.

### Preconditions

- NVD API experiencing 503 errors (known issue during enrichment pauses)
- Circuit breaker initialized in `closed` state

### Expected Outcome

- After 5 consecutive 503 errors, circuit opens
- No further NVD API calls for 30 minutes (half-open state)
- After 30 minutes, test request sent (half-open → closed if success, or back to open)
- Prometheus metric `nvd_circuit_breaker_state` tracks state transitions

### Primary Runtime Call Stack

```text
[ENTRY] src/complira_graph/agents/nvd.py:NVDAgent.fetch_data() [IO]
├── # Circuit breaker decorator (custom implementation)
├── @circuit_breaker(
│   failure_threshold=5,
│   recovery_timeout=1800, # 30 minutes
│   expected_exception=httpx.HTTPStatusError
│   )
├── # Circuit breaker state check
├── if circuit_breaker.state == "open":
│   ├── if time.time() - circuit_breaker.opened_at < circuit_breaker.recovery_timeout:
│   │   ├── structlog.warn("NVD circuit breaker OPEN, skipping fetch", time_until_retry=circuit_breaker.recovery_timeout - (time.time() - circuit_breaker.opened_at))
│   │   ├── monitoring.metrics.set_gauge("nvd_circuit_breaker_state", 1) # 1 = open
│   │   └── raise CircuitBreakerOpen("NVD API circuit breaker is OPEN, retry in 30 minutes")
│   └── else:
│       ├── # Recovery timeout elapsed, transition to half-open
│       ├── circuit_breaker.state = "half_open"
│       ├── structlog.info("NVD circuit breaker transitioning to HALF_OPEN, sending test request")
│       ├── monitoring.metrics.set_gauge("nvd_circuit_breaker_state", 0.5) # 0.5 = half-open
│       └── # Continue to API call below (test request)
├── # Attempt API call
├── try:
│   ├── rate_limiter.acquire("nvd", Rate(50, Duration.SECOND * 30))
│   ├── response = httpx.get("https://services.nvd.nist.gov/rest/json/cves/2.0", ...) [IO]
│   ├── response.raise_for_status() # Raises HTTPStatusError if 4xx/5xx
│   ├── # Success path
│   ├── if circuit_breaker.state == "half_open":
│   │   ├── # Test request succeeded, close circuit
│   │   ├── circuit_breaker.state = "closed"
│   │   ├── circuit_breaker.failure_count = 0
│   │   ├── structlog.info("NVD circuit breaker CLOSED after successful test request")
│   │   └── monitoring.metrics.set_gauge("nvd_circuit_breaker_state", 0) # 0 = closed
│   └── return response.json()
├── except httpx.HTTPStatusError as e:
│   ├── if e.response.status_code == 503: # NVD enrichment pause
│   │   ├── circuit_breaker.failure_count += 1
│   │   ├── structlog.warn("NVD API 503 error", failure_count=circuit_breaker.failure_count, threshold=5)
│   │   ├── if circuit_breaker.failure_count >= 5:
│   │   │   ├── # Open circuit
│   │   │   ├── circuit_breaker.state = "open"
│   │   │   ├── circuit_breaker.opened_at = time.time()
│   │   │   ├── structlog.error("NVD circuit breaker OPEN after 5 consecutive 503 errors, will retry in 30 minutes")
│   │   │   ├── monitoring.metrics.set_gauge("nvd_circuit_breaker_state", 1) # 1 = open
│   │   │   └── raise CircuitBreakerOpen("NVD API circuit breaker opened due to 503 storm")
│   │   └── else:
│   │       ├── # Retry with exponential backoff (tenacity handles this)
│   │       └── raise # tenacity will retry
│   └── else:
│       ├── # Other HTTP errors (not 503) don't count toward circuit breaker
│       └── raise # tenacity handles retry for 429, raises for others
```

### Branching / Fallback Paths

#### [FALLBACK] Circuit Breaker Half-Open Test Fails

```text
circuit_breaker.state == "half_open"
├── try:
│   └── response = httpx.get(...) → raises httpx.HTTPStatusError(503)
├── except httpx.HTTPStatusError as e:
│   ├── # Test request failed, reopen circuit
│   ├── circuit_breaker.state = "open"
│   ├── circuit_breaker.opened_at = time.time() # Reset recovery timer
│   ├── structlog.warn("NVD circuit breaker test request failed, reopening circuit for another 30 minutes")
│   ├── monitoring.metrics.set_gauge("nvd_circuit_breaker_state", 1) # 1 = open
│   └── raise CircuitBreakerOpen("NVD API still unavailable, circuit breaker reopened")
```

---

## Use Case: UC-DRB - LLM Dead Letter Queue Retry (Design Risk)

### Goal

**Design-Risk Objective:** Handle LLM API failures (rate limits, quota exceeded, temporary outages) without blocking deterministic ingestion. Failed enrichments stored in DLQ for retry with exponential backoff.

### Preconditions

- LLM enrichment agent encounters API failure (e.g., Anthropic rate limit 529)
- SQLite DLQ database initialized at `data/llm_dlq.db`

### Expected Outcome

- Failed enrichment written to DLQ with retry schedule
- Automatic retry with exponential backoff (1h, 2h, 4h, 8h, 16h, 32h, 7 days max)
- CLI command `complira retry-dlq` to manually trigger retry
- Successful retry removes entry from DLQ

### Primary Runtime Call Stack

```text
[ENTRY] src/complira_graph/llm_agents/cwe_classifier.py:CWEClassifierAgent.enrich(unclassified_cves) [ASYNC]
├── for cve in batch:
│   ├── try:
│   │   └── anthropic.messages.create(...) [IO] [ASYNC]
│   ├── except anthropic.RateLimitError as e:
│   │   ├── # After tenacity exhausts retries (5 attempts)
│   │   ├── structlog.error("LLM API rate limit exhausted, adding to DLQ", cve_id=cve.cve_id)
│   │   ├── src/complira_graph/monitoring/dlq.py:add_llm_failure(
│   │   │   agent="cwe_classifier",
│   │   │   input_payload={"cve_id": cve.cve_id, "description": cve.description},
│   │   │   input_hash=hashlib.sha256(json.dumps({"cve_id": cve.cve_id, "description": cve.description}).encode()).hexdigest(),
│   │   │   error=str(e),
│   │   │   retry_count=0,
│   │   │   retry_at=datetime.now() + timedelta(hours=1) # First retry in 1 hour
│   │   │   ) [IO]
│   │   │   ├── # Insert into SQLite DLQ
│   │   │   ├── conn = sqlite3.connect("data/llm_dlq.db")
│   │   │   ├── conn.execute("""
│   │   │   │   INSERT INTO llm_dlq (agent, input_payload, input_hash, error, retry_count, retry_at, created_at)
│   │   │   │   VALUES (?, ?, ?, ?, ?, ?, ?)
│   │   │   │   ON CONFLICT(input_hash) DO UPDATE SET retry_count = retry_count + 1, retry_at = excluded.retry_at
│   │   │   │   """, (agent, json.dumps(input_payload), input_hash, error, 0, retry_at, datetime.now()))
│   │   │   ├── conn.commit()
│   │   │   └── structlog.info("LLM failure added to DLQ", agent=agent, retry_at=retry_at)
│   │   └── continue # Skip this CVE, process next (don't block entire batch)
│   └── # Continue with successful enrichments
├── # Background DLQ processor (scheduled by Prefect)
├── [ENTRY] prefect.deployments.run("llm-dlq-retry-flow") # Runs hourly
├── src/complira_graph/monitoring/dlq.py:retry_dlq_failures() [ASYNC]
│   ├── conn = sqlite3.connect("data/llm_dlq.db")
│   ├── # Query for failures ready to retry
│   ├── failures = conn.execute("""
│   │   SELECT id, agent, input_payload, input_hash, retry_count
│   │   FROM llm_dlq
│   │   WHERE retry_at <= ? AND retry_count < 7
│   │   ORDER BY retry_at ASC
│   │   LIMIT 100
│   │   """, (datetime.now(),)).fetchall()
│   ├── for failure in failures:
│   │   ├── agent_class = get_agent_class(failure["agent"]) # CWEClassifierAgent
│   │   ├── agent = agent_class(db=db)
│   │   ├── try:
│   │   │   ├── # Retry enrichment
│   │   │   ├── result = agent.enrich([failure["input_payload"]]) [IO] [ASYNC]
│   │   │   ├── # Success, persist result
│   │   │   ├── agent.persist([result])
│   │   │   ├── # Remove from DLQ
│   │   │   ├── conn.execute("DELETE FROM llm_dlq WHERE id = ?", (failure["id"],))
│   │   │   ├── conn.commit()
│   │   │   └── structlog.info("DLQ retry succeeded", agent=failure["agent"], input_hash=failure["input_hash"])
│   │   ├── except Exception as e:
│   │   │   ├── # Retry failed, update DLQ with exponential backoff
│   │   │   ├── new_retry_count = failure["retry_count"] + 1
│   │   │   ├── backoff_hours = 2 ** new_retry_count # 1h, 2h, 4h, 8h, 16h, 32h, 64h...
│   │   │   ├── if backoff_hours > 168: # Max 7 days
│   │   │   │   └── backoff_hours = 168
│   │   │   ├── new_retry_at = datetime.now() + timedelta(hours=backoff_hours)
│   │   │   ├── conn.execute("""
│   │   │   │   UPDATE llm_dlq
│   │   │   │   SET retry_count = ?, retry_at = ?, last_error = ?
│   │   │   │   WHERE id = ?
│   │   │   │   """, (new_retry_count, new_retry_at, str(e), failure["id"]))
│   │   │   ├── conn.commit()
│   │   │   └── structlog.warn("DLQ retry failed, scheduled for next attempt", agent=failure["agent"], retry_at=new_retry_at, retry_count=new_retry_count)
│   └── structlog.info("DLQ retry batch complete", processed=len(failures))
```

### Branching / Fallback Paths

#### [FALLBACK] Manual DLQ Retry (CLI Command)

```text
[ENTRY] src/complira_graph/cli.py:retry_dlq(force=False)
├── click.echo("Retrying all DLQ failures...")
├── db = get_db() [IO]
├── if force:
│   ├── # Force retry all failures regardless of retry_at timestamp
│   ├── failures = conn.execute("SELECT * FROM llm_dlq WHERE retry_count < 7").fetchall()
│   └── click.echo(f"Force retrying {len(failures)} DLQ failures...")
├── else:
│   ├── # Only retry failures ready per schedule
│   ├── failures = conn.execute("SELECT * FROM llm_dlq WHERE retry_at <= ?", (datetime.now(),)).fetchall()
│   └── click.echo(f"Retrying {len(failures)} DLQ failures...")
├── src/complira_graph/monitoring/dlq.py:retry_dlq_failures(failures) # Same as automated retry above
└── click.echo(f"DLQ retry complete: {success_count} succeeded, {fail_count} failed")
```

### Error Paths

#### [ERROR] DLQ Max Retries Exceeded (7 attempts)

```text
src/complira_graph/monitoring/dlq.py:retry_dlq_failures() [ASYNC]
├── failures = conn.execute("SELECT * FROM llm_dlq WHERE retry_at <= ? AND retry_count < 7", ...) # Excludes failures with retry_count >= 7
├── # Separate query for max-retry failures (manual intervention required)
├── max_retry_failures = conn.execute("SELECT * FROM llm_dlq WHERE retry_count >= 7").fetchall()
├── if len(max_retry_failures) > 0:
│   ├── structlog.error("DLQ has failures exceeding max retries, manual intervention required", count=len(max_retry_failures))
│   ├── monitoring.metrics.set_gauge("llm_dlq_max_retry_count", len(max_retry_failures))
│   └── # Alert via Prometheus (configured threshold: llm_dlq_max_retry_count > 10)
```

---

## Runtime Call Stack Completeness Check

### Requirements Coverage

| Requirement ID | Covered Use Cases | Call Stack Depth | Evidence Boundaries |
| --- | --- | --- | --- |
| FR-1 (Data Ingestion) | UC-001, UC-002, UC-DRA | Full stack (CLI → agent → DB) | [ENTRY], [IO], [ASYNC] |
| FR-2 (Database Schema) | UC-001 | Schema init in UC-001 | [IO] |
| FR-3 (LLM Enrichment) | UC-001, UC-003, UC-004, UC-DRB | Full stack (agent → LLM API → DB) | [ASYNC], [IO], [STATE] |
| FR-4 (Query Performance) | UC-004, UC-005 | Full stack (CLI → AQL → result) | [ENTRY], [IO] |
| NFR-2 (Reliability) | UC-002, UC-DRA, UC-DRB | Error paths + retry logic | [ERROR], [FALLBACK] |

✅ All functional requirements mapped to detailed call stacks

### Boundary Tag Coverage

- `[ENTRY]`: ✅ All use cases have CLI/scheduled trigger entry points
- `[ASYNC]`: ✅ Async boundaries documented (Prefect flows, LLM API calls, parallel agent execution)
- `[STATE]`: ✅ In-memory mutations documented (data transformation, circuit breaker state)
- `[IO]`: ✅ All database, API, file operations tagged
- `[FALLBACK]`: ✅ Cache miss, circuit breaker, DLQ retry paths documented
- `[ERROR]`: ✅ API failures, timeouts, invalid data paths documented

### Missing Use Case Discovery

**No new use cases discovered during runtime modeling.**

All functional flows are covered by UC-001 through UC-005. Design-risk use cases (UC-DRA, UC-DRB) cover error handling patterns.

---

## Stage 4 Complete - Ready for Stage 5 Review

**Status:** ✅ **Runtime Modeling Complete**
**Call Stack Version:** v1
**Next Stage:** Review Gate (Stage 5) - Iterative deep-review rounds until `Go Confirmed`
**Approval:** Pending Stage 5 Review (requires two consecutive clean rounds with no blockers)

---

## Appendix: Call Stack Notation Guide

### Frame Format
```
path/to/file.py:function_name(args?)
```

### Boundary Tags
- `[ENTRY]` - External entrypoint (user action, scheduled trigger, API call)
- `[ASYNC]` - Async boundary (await, concurrent execution, queue handoff)
- `[STATE]` - In-memory state mutation (variables, data structures)
- `[IO]` - External IO (database, file, network, cache)
- `[FALLBACK]` - Non-primary branch (error handling, cache miss, degraded mode)
- `[ERROR]` - Error path (exception handling, validation failure)

### Example
```text
[ENTRY] src/app/cli.py:command()
├── src/app/service.py:process() [STATE]
│   ├── src/app/db.py:query() [IO]
│   └── src/app/cache.py:get() [FALLBACK] if cache miss
└── [ERROR] if ValidationError
```
