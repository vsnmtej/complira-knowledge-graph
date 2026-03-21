# Proposed Design Document: Complira Knowledge Graph Engine

## Design Version

- Current Version: `v1`
- Date: 2026-02-28
- Ticket: `complira-knowledge-graph`

## Revision History

| Version | Trigger | Summary Of Changes | Related Review Round |
| --- | --- | --- | --- |
| v1 | Initial draft from Stage 3 | Greenfield architecture for LARGE scope project | Pending Stage 4/5 |

## Artifact Basis

- Investigation Notes: `tickets/in-progress/complira-knowledge-graph/investigation-notes.md`
- Requirements: `tickets/in-progress/complira-knowledge-graph/requirements.md`
- Requirements Status: `Design-ready`
- Reference Documents:
  - `references/Data_sources.rtf` (40+ data source specifications)
  - `references/Implementation_stack.rtf` (technology stack)
  - `references/Unified_Schema.rtf` (ArangoDB schema: 36 collections, 41 edges)
  - `references/LLM_Enhancement.rtf` (9 LLM agent specifications)

---

## Summary

Build a production-grade cybersecurity compliance knowledge graph platform that ingests 40+ open data sources into ArangoDB, enriches the graph with 9 LLM agents, and enables regulatory compliance queries. The system will support incremental updates, full provenance tracking, and cost-efficient LLM usage (<$100/month).

**Key Architecture Components:**
1. **Database Layer:** ArangoDB 3.12 with 36 document collections, 41 edge collections, and 7 named graphs
2. **Deterministic Ingestion Layer:** 23+ agents for open data sources (NVD, ATT&CK, CWE, etc.)
3. **LLM Enrichment Layer:** 9 agents for gap-filling (CWE classification, PURL→CPE, VEX generation)
4. **Orchestration Layer:** DAG-based scheduling with dependency ordering
5. **API/CLI Layer:** Click CLI for seed/update/status commands
6. **Monitoring Layer:** Prometheus metrics + Grafana dashboards

---

## Goals

1. **Correctness:** Accurate data ingestion with full provenance tracking
2. **Performance:** Initial seed <6 hours, incremental updates <2 hours
3. **Cost Efficiency:** Infrastructure <€100/month, LLM <$100/month
4. **Auditability:** Complete evidence chain for regulatory compliance
5. **Maintainability:** Plugin-based agent architecture, clear separation of concerns
6. **Evolution:** Support adding new data sources without core refactoring

---

## Legacy Removal Policy

**Policy:** N/A (greenfield project)

No legacy code to remove. This is a from-scratch implementation.

---

## Requirements And Use Cases

| Requirement ID | Description | Acceptance Criteria ID(s) | Acceptance Criteria Summary | Use Case IDs |
| --- | --- | --- | --- | --- |
| FR-1 | Data Ingestion | FR-1.1-1.4 | 40+ agents with rate limiting, incremental updates, retry logic | UC-1, UC-2 |
| FR-2 | Database Schema | FR-2.1-2.4 | 36 collections, 41 edges, indexes, deterministic keys | UC-1, UC-2, UC-5 |
| FR-3 | LLM Enrichment | FR-3.1-3.4 | 9 agents with provenance, confidence thresholds, cost tracking | UC-3, UC-4 |
| FR-4 | Query Performance | FR-4.1-4.3 | Regulatory blast radius <5s, VEX gen <30s, 3-hop <10s | UC-4, UC-5 |
| NFR-1 | Scalability | NFR-1.1-1.3 | 10M+ nodes, 28M+ edges, concurrent ingestion | UC-1, UC-2 |
| NFR-2 | Reliability | NFR-2.1-2.3 | Retry logic, graceful shutdown, health checks | UC-1, UC-2 |
| NFR-3 | Observability | NFR-3.1-3.3 | Prometheus metrics, structured logs, Grafana dashboards | All |
| NFR-4 | Security | NFR-4.1-4.3 | Env-based secrets, no secrets in git, read-only queries | All |
| NFR-5 | Cost Efficiency | NFR-5.1-5.3 | <€100/month infra, <$100/month LLM, LZ4 compression | All |

---

## Codebase Understanding Snapshot (Pre-Design)

| Area | Findings | Evidence | Open Unknowns |
| --- | --- | --- | --- |
| Entrypoints / Boundaries | CLI entry via Click, Prefect flows for orchestration | `src/complira_graph/cli.py`, `src/complira_graph/orchestrator/` | None (greenfield) |
| Current Naming Conventions | N/A (greenfield) - will use snake_case for Python, PascalCase for classes | Investigation notes | None |
| Impacted Modules | 40+ new Python modules across 6 packages | Investigation file/module breakdown | None |
| Data / Persistence | ArangoDB 3.12, bulk import optimization critical | `references/Unified_Schema.rtf` | Schema migration strategy (defer to v2) |
| External IO | 40+ REST APIs, 4 git repos, CSV/JSON/XML parsing | Investigation rate limiting section | None |

---

## Current State (As-Is)

**N/A - Greenfield Project**

Starting from empty repository with only:
- `.gitignore`
- `README.md`
- Reference documentation (`references/*.rtf`)
- Workflow skill templates (`.claude/skills/`)

No existing code to migrate or refactor.

---

## Target State (To-Be)

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      CLI Entry (complira)                       │
│  Commands: seed, update, status, validate                      │
└──────────────────────┬──────────────────────────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         │                           │
         ▼                           ▼
┌─────────────────┐          ┌──────────────────┐
│  Orchestrator   │          │  Monitoring      │
│  - DAG Builder  │◄────────►│  - Prometheus    │
│  - Prefect/Cron │          │  - Grafana       │
│  - Semaphore    │          │  - structlog     │
└────────┬────────┘          └──────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│    Agent Executor (Parallel)        │
│  Max 3-4 concurrent writers         │
└────────┬────────────────────────────┘
         │
    ┌────┴────┬──────────┬────────────┐
    ▼         ▼          ▼            ▼
┌────────┐ ┌──────┐  ┌──────┐   ┌─────────┐
│ NVD    │ │ OSV  │  │ CWE  │...│ LLM     │
│ Agent  │ │ Agent│  │ Agent│   │ Agents  │
└───┬────┘ └───┬──┘  └───┬──┘   └────┬────┘
    │          │          │           │
    └──────────┴──────────┴───────────┘
                     │
                     ▼
           ┌──────────────────┐
           │   ArangoDB 3.12  │
           │   - 36 docs      │
           │   - 41 edges     │
           │   - 7 graphs     │
           └──────────────────┘
```

### Layered Architecture

**Layer 1: Database (Foundation)**
- ArangoDB collections and indexes
- Bulk import utilities
- Connection management
- Schema initialization

**Layer 2: Data Models (Contracts)**
- Pydantic v2 models for all document types
- Edge models with `_from`/`_to` validation
- Transform utilities (STIX→ArangoDB, PURL normalization, key generation)

**Layer 3: Ingestion Agents (Data Acquisition)**
- `BaseIngestionAgent` abstract class
- 23+ concrete agents (NVD, CWE, ATT&CK, etc.)
- Rate limiting and retry logic
- Incremental update detection

**Layer 4: LLM Enrichment Agents (Intelligence)**
- `BaseLLMAgent` abstract class
- 9 specialized agents (CWE classifier, VEX synthesizer, etc.)
- Provenance tracking
- Cost monitoring

**Layer 5: Orchestration (Coordination)**
- DAG dependency graph
- Parallel execution with semaphore
- Prefect flows and schedules
- Error handling and retry

**Layer 6: API/CLI (User Interface)**
- Click CLI commands
- Health check endpoints
- Status reporting

**Layer 7: Monitoring (Observability)**
- Prometheus metrics
- Structured logging
- Grafana dashboards

---

## Architecture Direction Decision

### Primary Decision: Prefect vs APScheduler for Orchestration

**Chosen Direction:** **Prefect 3.x**

**Rationale:**
1. **Complexity:** LARGE scope with 32 agents (23 deterministic + 9 LLM) justifies richer orchestration
2. **Testability:** Prefect's Python-native flows easier to unit test than cron jobs
3. **Operability:** Built-in UI for monitoring, logs, retries, and scheduling
4. **Evolution Cost:** Adding new agents is simpler (register new flow vs editing crontab)

**Layering Fitness Assessment:** Yes (Prefect stays in orchestration layer, doesn't leak into agents)

**Outcome:** `Add` Prefect 3.x as orchestration framework

### Alternative Analysis

| Option | Summary | Pros | Cons | Decision | Rationale |
| --- | --- | --- | --- | --- | --- |
| A: Prefect 3.x | Full orchestration framework with UI, scheduling, retries | Rich monitoring, Python-native, free tier, excellent docs | Adds PostgreSQL dependency, ~2 GB RAM overhead, learning curve | **Chosen** | Scale (32 agents) + observability needs justify complexity |
| B: APScheduler 3.x | Lightweight Python scheduler with SQLite backend | Minimal deps, simpler, <100 MB RAM, no external services | No UI, manual retry logic, harder to monitor 32 agents | Rejected | Monitoring gap too large for LARGE scope |
| C: Plain Cron + systemd | OS-level scheduling | Zero Python deps, ubiquitous, simple | No dependency tracking, no retry logic, hard to monitor | Rejected | DAG dependencies are critical (CWE must load before NVD CVEs) |

**Deferred Decisions (Stage 5 Review May Reveal Need to Revisit):**
- Circuit breaker pattern for unreliable sources (NVD 503 errors)
- Dead letter queue for failed LLM enrichments
- Index drop strategy for incremental updates

---

## Change Inventory (Delta)

**Note:** All changes are `Add` since this is greenfield.

| Change ID | Change Type | Current Path | Target Path | Rationale | Impacted Areas | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| C-001 | Add | N/A | `src/complira_graph/db.py` | ArangoDB connection, bulk import, schema init | Database layer | Core foundation |
| C-002 | Add | N/A | `src/complira_graph/config.py` | Pydantic settings from `.env` | All layers | Centralized config |
| C-003 | Add | N/A | `src/complira_graph/models/*.py` | 8 model files (vulnerability, weakness, component, etc.) | Data model layer | Contract definitions |
| C-004 | Add | N/A | `src/complira_graph/agents/*.py` | 23+ ingestion agents | Ingestion layer | Data acquisition |
| C-005 | Add | N/A | `src/complira_graph/llm_agents/*.py` | 9 LLM enrichment agents | LLM layer | Intelligence |
| C-006 | Add | N/A | `src/complira_graph/orchestrator/*.py` | DAG builder, Prefect flows | Orchestration layer | Coordination |
| C-007 | Add | N/A | `src/complira_graph/cli.py` | Click CLI commands | API layer | User interface |
| C-008 | Add | N/A | `src/complira_graph/monitoring/*.py` | Prometheus metrics, health checks | Monitoring layer | Observability |
| C-009 | Add | N/A | `src/complira_graph/transforms/*.py` | Key generation, STIX parser, normalization | Utility layer | Cross-cutting |
| C-010 | Add | N/A | `docker-compose.yml` | ArangoDB, Prefect, Prometheus, Grafana | Infrastructure | Deployment |
| C-011 | Add | N/A | `monitoring/prometheus.yml` | Prometheus config | Infrastructure | Monitoring setup |
| C-012 | Add | N/A | `monitoring/grafana/dashboards/*.json` | Grafana dashboards | Infrastructure | Visualization |
| C-013 | Add | N/A | `pyproject.toml` | Python dependencies via uv | Build system | Package management |
| C-014 | Add | N/A | `.env.example` | Environment variable template | Config | Security (no secrets in git) |

---

## Target Architecture Shape And Boundaries

| Layer/Boundary | Purpose | Owns | Must Not Own | Notes |
| --- | --- | --- | --- | --- |
| **Database** | Persistence and graph queries | ArangoDB schema, collections, indexes, connection pooling | Business logic, API schemas, external API calls | Foundation layer |
| **Data Models** | Type contracts and validation | Pydantic models, edge definitions, transform utilities | Database operations, HTTP requests, orchestration | Contract layer |
| **Ingestion Agents** | Fetch and load external data | API clients, rate limiting, incremental update logic, bulk loading | LLM calls, orchestration, CLI | Data acquisition |
| **LLM Agents** | AI-powered gap filling | LLM prompts, confidence filtering, provenance tracking | Direct database access (goes through `db.py`), orchestration | Intelligence layer |
| **Orchestration** | Scheduling and coordination | DAG definitions, Prefect flows, semaphore for concurrency | Agent implementation details, database schema | Coordination layer |
| **API/CLI** | User interaction | Click commands, input validation, output formatting | Agent execution logic, database queries | Interface layer |
| **Monitoring** | Observability | Prometheus metrics, structured logs, health checks | Business logic, orchestration decisions | Cross-cutting concern |
| **Transforms** | Utilities | Key normalization, STIX parsing, PURL/CPE utils | Agent-specific logic, database operations | Shared utilities |

---

## File And Module Breakdown

### Core Infrastructure (3 modules)

| File/Module | Change Type | Layer | Concern / Responsibility | Public APIs | Inputs/Outputs | Dependencies |
| --- | --- | --- | --- | --- | --- | --- |
| `src/complira_graph/__init__.py` | Add | - | Package initialization | `__version__` | - | - |
| `src/complira_graph/config.py` | Add | Config | Pydantic settings from `.env` | `Settings` class | `.env` → Settings object | `pydantic-settings` |
| `src/complira_graph/db.py` | Add | Database | ArangoDB connection, collection setup, bulk ops | `get_db()`, `init_schema()`, `bulk_upsert()` | ArangoDB connection params | `python-arango` |

### Data Models (8 modules)

| File/Module | Change Type | Layer | Concern / Responsibility | Public APIs | Inputs/Outputs | Dependencies |
| --- | --- | --- | --- | --- | --- | --- |
| `models/__init__.py` | Add | - | Package exports | All model classes | - | - |
| `models/vulnerability.py` | Add | Model | Vulnerability, KEV, EPSS models | `Vulnerability`, `KEVEntry`, `EPSSScore` | JSON → Pydantic | `pydantic` |
| `models/weakness.py` | Add | Model | CWE weakness models | `Weakness` | XML → Pydantic | `pydantic` |
| `models/component.py` | Add | Model | Software component, CPE, license | `Component`, `CPEEntry`, `License` | JSON → Pydantic | `pydantic` |
| `models/threat.py` | Add | Model | ATT&CK, CAPEC, D3FEND, ATLAS | `ATTACKTechnique`, `CAPEC`, `D3FENDTechnique` | STIX/XML/YAML → Pydantic | `pydantic` |
| `models/compliance.py` | Add | Model | Regulatory requirements, OSCAL | `RegulatoryRequirement`, `OSCALControl` | JSON → Pydantic | `pydantic` |
| `models/exploit.py` | Add | Model | Exploit modules (MSF, EDB, Nuclei) | `ExploitModule` | JSON/CSV/YAML → Pydantic | `pydantic` |
| `models/edges.py` | Add | Model | All edge types with validation | `HasWeakness`, `ExploitedInWild`, etc. | - | `pydantic` |

### Ingestion Agents (23+ modules)

| File/Module | Change Type | Layer | Concern / Responsibility | Public APIs | Inputs/Outputs | Dependencies |
| --- | --- | --- | --- | --- | --- | --- |
| `agents/__init__.py` | Add | - | Package exports | All agent classes | - | - |
| `agents/base.py` | Add | Agent | Abstract base agent interface | `BaseIngestionAgent` (ABC) | - | `abc` |
| `agents/nvd.py` | Add | Agent | NVD API 2.0 ingestion | `NVDAgent` | NVD API → `vulnerabilities` | `httpx`, `tenacity` |
| `agents/osv.py` | Add | Agent | OSV.dev GCS + API | `OSVAgent` | GCS bucket → `vulnerabilities` | `httpx`, `google-cloud-storage` |
| `agents/cisa_kev.py` | Add | Agent | CISA KEV JSON feed | `CISAKEVAgent` | JSON URL → `kev_entries` | `httpx` |
| `agents/epss.py` | Add | Agent | FIRST.org EPSS daily CSV | `EPSSAgent` | CSV download → `epss_history` | `httpx`, `csv` |
| `agents/cwe.py` | Add | Agent | CWE XML parser | `CWEAgent` | XML download → `weaknesses` | `lxml` |
| `agents/attack.py` | Add | Agent | ATT&CK STIX 2.1 parser | `ATTACKAgent` | GitHub STIX bundles → `attack_techniques` | `stix2` |
| `agents/capec.py` | Add | Agent | CAPEC XML parser | `CAPECAgent` | XML download → `attack_patterns` | `lxml` |
| `agents/d3fend.py` | Add | Agent | D3FEND REST API | `D3FENDAgent` | REST API → `d3fend_techniques` | `httpx` |
| `agents/oscal.py` | Add | Agent | NIST OSCAL SP 800-53 JSON | `OSCALAgent` | JSON download → `oscal_controls` | `httpx` |
| ... (13+ more agents) | Add | Agent | Various data sources | Agent classes | API/Git/CSV → Collections | Various |

### LLM Enrichment Agents (9 modules)

| File/Module | Change Type | Layer | Concern / Responsibility | Public APIs | Inputs/Outputs | Dependencies |
| --- | --- | --- | --- | --- | --- | --- |
| `llm_agents/__init__.py` | Add | - | Package exports | All LLM agent classes | - | - |
| `llm_agents/base_llm.py` | Add | LLM Agent | Abstract LLM agent interface | `BaseLLMAgent` (ABC) | - | `abc`, `anthropic` |
| `llm_agents/cwe_classifier.py` | Add | LLM Agent | L1: CWE Gap Filler (Haiku 4.5) | `CWEClassifierAgent` | Unclassified CVEs → `has_weakness` edges | `anthropic` |
| `llm_agents/purl_cpe_resolver.py` | Add | LLM Agent | L2: PURL→CPE (Sonnet 4.5) | `PURLCPEResolverAgent` | Unmatched PURLs → `matched_by_cpe` edges | `anthropic` |
| `llm_agents/vex_synthesizer.py` | Add | LLM Agent | L3: VEX Justification (Sonnet 4.5) | `VEXSynthesizerAgent` | CVE+Component → VEX document | `anthropic` |
| `llm_agents/regulatory_mapper.py` | Add | LLM Agent | L4: Regulatory Mapping (Opus 4) | `RegulatoryMapperAgent` | CWE+Requirements → `maps_to_requirement` edges | `anthropic` |
| ... (5+ more LLM agents) | Add | LLM Agent | Various enrichment tasks | Agent classes | Graph gaps → Enriched edges/nodes | `anthropic` |

### Orchestration (3 modules)

| File/Module | Change Type | Layer | Concern / Responsibility | Public APIs | Inputs/Outputs | Dependencies |
| --- | --- | --- | --- | --- | --- | --- |
| `orchestrator/__init__.py` | Add | - | Package exports | Orchestrator classes | - | - |
| `orchestrator/dag.py` | Add | Orchestrator | DAG dependency graph builder | `build_dag()`, `execute_dag()` | Agent list → Topological order | `graphlib` |
| `orchestrator/seed.py` | Add | Orchestrator | Full initial seed Prefect flow | `seed_flow()` | - | `prefect`, `asyncio` |
| `orchestrator/schedules.py` | Add | Orchestrator | Prefect deployment definitions | `create_schedules()` | - | `prefect` |

### Transforms & Utilities (4 modules)

| File/Module | Change Type | Layer | Concern / Responsibility | Public APIs | Inputs/Outputs | Dependencies |
| --- | --- | --- | --- | --- | --- | --- |
| `transforms/__init__.py` | Add | - | Package exports | Transform functions | - | - |
| `transforms/keys.py` | Add | Transform | Deterministic `_key` generation | `cve_key()`, `cwe_key()`, `purl_key()` | ID strings → Normalized keys | - |
| `transforms/stix.py` | Add | Transform | STIX 2.1 → ArangoDB converter | `stix_to_doc()` | STIX objects → Pydantic models | `stix2` |
| `transforms/normalize.py` | Add | Transform | PURL/CPE/CVE normalization | `normalize_purl()`, `normalize_cpe()` | Raw identifiers → Canonical form | `packageurl` |

### Monitoring (2 modules)

| File/Module | Change Type | Layer | Concern / Responsibility | Public APIs | Inputs/Outputs | Dependencies |
| --- | --- | --- | --- | --- | --- | --- |
| `monitoring/__init__.py` | Add | - | Package exports | Metrics, health check | - | - |
| `monitoring/metrics.py` | Add | Monitoring | Prometheus metrics definitions | `record_ingestion()`, `record_llm_tokens()` | Events → Prometheus | `prometheus-client` |
| `monitoring/health.py` | Add | Monitoring | Health check endpoints | `check_health()` | - → Health status | `python-arango` |

### CLI (1 module)

| File/Module | Change Type | Layer | Concern / Responsibility | Public APIs | Inputs/Outputs | Dependencies |
| --- | --- | --- | --- | --- | --- | --- |
| `cli.py` | Add | CLI | Click command interface | `seed()`, `update()`, `status()`, `validate()` | User commands → Orchestrator | `click`, `rich` |

---

## Layer-Appropriate Separation Of Concerns Check

✅ **Database Layer:**
- Owns: Collection creation, indexing, bulk import, connection pooling
- Does not own: Business logic, API schemas, external calls
- Boundary: `db.py` module exposes clean API (`get_db()`, `bulk_upsert()`)

✅ **Data Model Layer:**
- Owns: Pydantic schemas, validation, type contracts
- Does not own: Database operations, HTTP requests, LLM calls
- Boundary: Models are pure data structures with validation only

✅ **Ingestion Agent Layer:**
- Owns: API clients, rate limiting, incremental detection, transformation to Pydantic
- Does not own: Database schema definition, orchestration, LLM logic
- Boundary: `BaseIngestionAgent` enforces consistent interface

✅ **LLM Agent Layer:**
- Owns: Prompt engineering, LLM API calls, confidence filtering, provenance tracking
- Does not own: Direct database access (uses `db.py`), orchestration
- Boundary: `BaseLLMAgent` enforces gap detection → enrich → persist pattern

✅ **Orchestration Layer:**
- Owns: DAG dependencies, parallel execution, scheduling, retries
- Does not own: Agent implementation details, database schema, LLM prompts
- Boundary: Prefect flows call agent methods, agents don't know about Prefect

✅ **CLI Layer:**
- Owns: User input parsing, output formatting, command routing
- Does not own: Agent execution, database queries, business logic
- Boundary: CLI calls orchestrator, orchestrator calls agents

✅ **Monitoring Layer:**
- Cross-cutting: Metrics recording, logging, health checks
- Does not own: Business decisions, orchestration logic
- Boundary: Decorator pattern for agent instrumentation

---

## Naming Decisions (Natural And Implementation-Friendly)

| Item Type | Current Name | Proposed Name | Reason | Notes |
| --- | --- | --- | --- | --- |
| File | N/A (greenfield) | `base.py`, `nvd.py`, `cwe.py` | Descriptive, lowercase, snake_case (PEP 8) | Standard Python convention |
| Module | N/A | `complira_graph` | Product name, underscores for multi-word | Top-level package |
| Class | N/A | `BaseIngestionAgent`, `NVDAgent` | PascalCase, noun-based, clear inheritance | Standard Python convention |
| Function | N/A | `check_for_updates()`, `load_data()` | snake_case, verb-based, action-oriented | Standard Python convention |
| Collection | N/A | `vulnerabilities`, `weaknesses`, `attack_techniques` | Plural nouns, snake_case | ArangoDB convention |
| Edge | N/A | `has_weakness`, `exploited_in_wild`, `depends_on` | Verb phrases, snake_case | Graph relationship clarity |
| Key | N/A | `CVE_2024_1234`, `CWE_79`, `T1190` | Normalized, uppercase with underscores | Deterministic, readable |
| CLI Command | N/A | `complira seed`, `complira update` | Verb-based, lowercase | User-friendly |
| Env Var | N/A | `ARANGO_HOST`, `NVD_API_KEY` | Uppercase, snake_case | Standard env var convention |

---

## Naming Drift Check

**N/A - Greenfield Project**

No existing names to check for drift. All naming decisions are fresh and follow established conventions.

---

## Existing-Structure Bias Check

**N/A - Greenfield Project**

No existing file layout to create bias. Architecture-first approach is already enforced by starting from a clean slate.

---

## Data Flow Diagrams

### Initial Seed Flow (UC-1)

```
User runs: complira seed
         │
         ▼
    CLI (seed command)
         │
         ▼
  Orchestrator builds DAG
  (TopologicalSorter + agent deps)
         │
         ├──────────┬──────────┬──────────┐
         ▼          ▼          ▼          ▼
     CWE Agent  ATT&CK Ag  OSCAL Ag   ... (parallel, max 3-4 concurrent)
         │          │          │
         │ check_for_updates() → False (first run)
         │ fetch_data() → List[dict]
         │ transform_data() → List[Pydantic]
         │ load_data() → db.bulk_upsert()
         │          │          │
         ▼          ▼          ▼
    ┌─────────────────────────────┐
    │   ArangoDB Collections      │
    │   - weaknesses              │
    │   - attack_techniques       │
    │   - oscal_controls          │
    └─────────────────────────────┘
                 │
    Wait for dependencies to complete
                 │
         ▼          ▼          ▼
     NVD Agent  CAPEC Ag   Deps.dev Ag
         │          │          │
         │ (requires CWE loaded first)
         │ (requires ATT&CK loaded first)
         │          │          │
         ▼          ▼          ▼
    ArangoDB (vulnerabilities, etc.)
                 │
    All deterministic agents complete
                 │
         ▼
    LLM Enrichment Agents
    (Sequential after deterministic pipeline)
         │
         ├──────────┬──────────┐
         ▼          ▼          ▼
    L1: CWE     L2: PURL→CPE  L3: VEX
    Classifier   Resolver     Synth
         │          │          │
         │ find_gaps() → AQL query
         │ enrich() → Claude API call
         │ validate() → confidence filter
         │ persist() → db.bulk_upsert()
         │          │          │
         ▼          ▼          ▼
    ArangoDB (edges + llm_enrichments)
                 │
         ▼
    Prometheus metrics recorded
    Structured logs written
         │
         ▼
    Report completion to CLI
    (duration, record counts, costs)
```

### Incremental Update Flow (UC-2)

```
Prefect cron trigger (hourly/daily/weekly)
         │
         ▼
  Orchestrator executes update DAG
  (only agents with updates)
         │
         ▼
    Agent.check_for_updates() → bool
         │
     True? ────► fetch_data(delta_only=True)
         │       │
         │       ▼ transform_data()
         │       │
         │       ▼ db.bulk_upsert(on_duplicate="update")
         │       │
         │       ▼ Prometheus metrics
         │
    False? ────► Skip (log "no updates")
         │
         ▼
    LLM agents run on new gaps only
    (query for unclassified CVEs, unmatched PURLs)
         │
         ▼
    Report delta metrics to monitoring
```

### VEX Generation Flow (UC-4)

```
User uploads SBOM (CycloneDX JSON)
         │
         ▼
    CLI parses SBOM → List[Component]
         │
         ▼
    For each component:
        Query graph for vulnerabilities
        (affects edges)
         │
         ▼
    For each CVE+Component pair:
         │
         ├─► Query evidence from graph:
         │   - CWE (has_weakness edges)
         │   - EPSS (epss_score)
         │   - KEV (kev_entries)
         │   - Exploits (has_exploit edges)
         │   - Hardening (binary_hardening_profiles)
         │   - SAST/DAST (scanner findings)
         │
         ▼
    L3: VEX Synthesizer Agent
         │
         ├─► Claude Sonnet 4.5 API call
         │   Prompt: Evidence + VEX template
         │   Response: VEX justification JSON
         │
         ▼
    Validate confidence threshold
         │
         ▼
    Persist VEX document to graph
    + llm_enrichments provenance
         │
         ▼
    Return VEX document to user
    (affected/not_affected/fixed/under_investigation)
```

---

## Error Handling Strategy

### Retry Logic (All Agents)

- **Library:** `tenacity` with exponential backoff + jitter
- **Retry Conditions:**
  - HTTP 5xx errors → Retry up to 3 times, backoff 2^n seconds
  - HTTP 429 (rate limit) → Retry up to 5 times, backoff with jitter
  - Network timeouts → Retry up to 2 times
  - HTTP 4xx (except 429) → No retry (client error)
- **Max Retry Time:** 5 minutes total per operation

### Circuit Breaker (NVD API - Known Unreliable)

**Problem:** NVD has frequent 503 errors during enrichment pauses (known issue since 2023)

**Solution:** Implement circuit breaker pattern
- **Threshold:** 5 consecutive failures → OPEN circuit for 30 minutes
- **Half-Open:** After 30 minutes, allow 1 test request
- **Closed:** If test succeeds, resume normal operation
- **Monitoring:** Prometheus metric `nvd_circuit_breaker_state` (closed/open/half_open)

**Implementation:** Custom decorator on `NVDAgent.fetch_data()`

### Dead Letter Queue (LLM Enrichments)

**Problem:** LLM API failures (rate limits, quota exceeded, API outage) should not block deterministic pipeline

**Solution:** SQLite-based dead letter queue
- Failed enrichments written to `llm_dlq.db` with:
  - Agent ID
  - Input payload (hashed for deduplication)
  - Failure reason
  - Retry count
  - Next retry time
- **Retry Schedule:** Exponential backoff, max 7 days
- **Manual Intervention:** CLI command `complira retry-dlq` to force retry

### Graceful Shutdown

- **SIGTERM Handler:** Agents check `shutdown_requested` flag before each batch
- **In-Flight Completion:** Allow current batch to finish (max 30 seconds)
- **State Persistence:** Write checkpoint to ArangoDB `_checkpoint` collection
- **Resume:** Next run starts from checkpoint if exists

---

## Concurrency And Parallelism

### Parallel Agent Execution

**Constraint:** ArangoDB can handle many readers but limited concurrent bulk writers (recommended 3-4)

**Solution:** Semaphore with max 4 concurrent bulk writers
```python
async def execute_agents_parallel(agents: List[BaseIngestionAgent]):
    semaphore = asyncio.Semaphore(4)  # Max 4 concurrent
    async with semaphore:
        await agent.run()
```

**DAG Execution:**
1. Build topological order from dependency graph
2. For each layer in DAG (e.g., all agents with no dependencies):
   - Execute in parallel up to semaphore limit
   - Wait for all in layer to complete
3. Move to next layer

### LLM Agent Parallelism

**Decision:** Sequential execution after deterministic pipeline

**Rationale:**
- LLM agents have API rate limits (Claude: 50K req/min)
- Each agent processes batches internally (e.g., 1,000 CVEs per batch)
- Parallel LLM agents would hit rate limit quickly
- Sequential is simpler and avoids coordination complexity

**Future Optimization (v2.0):** Concurrent with shared rate limiter

---

## Security Considerations

### Secrets Management

- **Environment Variables:** All API keys in `.env` file (not committed to git)
- **`.gitignore`:** Enforces exclusion of `.env`, `*.key`, `*.pem`
- **Pre-Commit Hook:** Scan commits for secrets (detect base64-encoded keys)
- **ArangoDB:** Default password changed in Docker Compose, stored in env

### ArangoDB Access Control

- **Read-Only User:** Create `complira_reader` user for query-only operations
- **Write User:** `complira_writer` for ingestion agents (no drop/truncate permissions)
- **Admin User:** `root` for schema initialization only

### LLM Input Sanitization

- **Prevent Prompt Injection:** Escape user-provided input (SBOM data)
- **Max Token Limit:** Enforce hard limit (100K tokens per request)
- **Cost Monitoring:** Alert if daily LLM cost exceeds $20 (prevents runaway costs)

---

## Testing Strategy

### Unit Tests

- **Coverage Target:** 80%+ for core modules (`db.py`, `base.py`, transforms)
- **Framework:** `pytest` with `pytest-asyncio`
- **Mocking:** `httpx` responses for API agents, in-memory ArangoDB for `db.py`
- **Fixtures:** Sample data from reference docs (NVD CVE JSON, CWE XML snippets)

### Integration Tests

- **Scope:** End-to-end agent execution against test ArangoDB instance
- **Data:** Small subset (100 CVEs, 50 CWEs, 10 ATT&CK techniques)
- **Validation:** Assert document counts, edge counts, key uniqueness

### E2E Tests (Stage 7)

- **Scenario 1:** Full seed with 1,000 records per source → Validate graph structure
- **Scenario 2:** Incremental update simulation → Assert only deltas processed
- **Scenario 3:** VEX generation → Assert evidence chain completeness
- **Scenario 4:** Regulatory blast radius query → Assert CRA/FDA mappings

### Performance Tests

- **Bulk Import:** 100K documents in <10 seconds
- **Incremental Update:** NVD delta (1K CVEs) in <2 minutes
- **VEX Generation:** 50 CVE+Component pairs in <20 minutes
- **Graph Query:** 3-hop traversal on 10M nodes in <10 seconds

---

## Deployment Architecture

### Single-Server Deployment (v1.0)

**Target Infrastructure:** Hetzner/OVH VPS (€70-90/month)

**Specs:**
- 32 GB RAM (24 GB for ArangoDB, 4 GB for Prefect, 4 GB for apps)
- 500 GB NVMe SSD (LZ4 compression → 15-25 GB used for 10M nodes)
- 8 vCPUs (Intel/AMD)
- Ubuntu 24.04 LTS

**Docker Compose Stack:**
- ArangoDB 3.12 (port 8529)
- Prefect Server (port 4200)
- Prometheus (port 9090)
- Grafana (port 3000)
- PostgreSQL 16 (Prefect backend, port 5432)

**Backup Strategy:**
- Daily `arangodump --all-databases` → Backblaze B2
- Retention: 30 daily, 12 monthly
- Restore tested monthly via CI

**Monitoring:**
- Grafana dashboards: Agent execution, LLM costs, query performance
- Prometheus alerts: Disk usage >80%, ArangoDB down, LLM cost >$5/day
- Uptime monitoring: UptimeRobot for API health check

---

## Open Design Questions (Defer to Stage 5 Review)

1. **Index Drop Strategy for Incremental Updates:**
   - Keep indexes during incremental updates? (slower upserts, queries available)
   - Drop-and-rebuild? (faster upserts, query downtime)
   - **Decision Point:** Stage 5 review, depends on update frequency vs query load

2. **LLM Agent Concurrent Execution:**
   - Sequential after deterministic pipeline? (simpler, avoids rate limit complexity)
   - Concurrent with shared rate limiter? (faster, more complex)
   - **Decision Point:** Stage 5 review, measure sequential runtime first

3. **Schema Migration Strategy (Deferred to v2.0):**
   - How to add new collections/edges without downtime?
   - **Decision Point:** Not blocking for v1.0, address in v2.0 design

---

## Success Metrics (Acceptance Criteria Mapping)

| Acceptance Criterion | Metric | Target | Measurement |
| --- | --- | --- | --- |
| FR-1: All 40+ agents functional | Agent execution success rate | >95% | Prometheus `agent_success_total / agent_runs_total` |
| FR-2: Schema created | Collection count | 36 docs + 41 edges | ArangoDB `_api/collection` query |
| FR-3: LLM provenance tracked | Enrichment provenance rate | 100% | `llm_enrichments` count == LLM-generated edge count |
| FR-4.1: Regulatory query <5s | Query latency P95 | <5 seconds | Prometheus histogram `graph_query_duration_seconds` |
| FR-4.2: VEX gen <30s | VEX generation latency P95 | <30 seconds | Prometheus histogram `vex_generation_duration_seconds` |
| NFR-1: Scale to 10M nodes | Node count | >10M | ArangoDB system collection query |
| NFR-2: Retry logic | Retry success rate | >80% | Prometheus `retries_succeeded / retries_total` |
| NFR-3: Prometheus metrics | Metric cardinality | <1,000 unique series | Prometheus TSDB stats |
| NFR-5: LLM cost <$100/month | Monthly LLM cost | <$100 | Prometheus counter `llm_cost_usd_total` |

---

## Design Complete - Ready for Stage 4

**Status:** ✅ **Design Basis Complete**
**Next Stage:** Runtime Modeling (Stage 4) - Create `future-state-runtime-call-stack.md` for each use case
**Approval:** Pending Stage 5 Review Gate

---

## Appendix: Technology Stack Summary

| Category | Technology | Version | Rationale |
| --- | --- | --- | --- |
| **Language** | Python | 3.12+ | Ecosystem fit, LLM SDKs, async support |
| **Package Manager** | uv | Latest | 10-100× faster than pip |
| **Database** | ArangoDB | 3.12 | Multi-model, native graph, open source |
| **DB Driver** | python-arango | 8.3+ | Official driver, excellent bulk API |
| **Validation** | Pydantic | 2.0+ | v2 performance, strict mode |
| **HTTP Client** | httpx | 0.28+ | Async support, modern API |
| **Retry Logic** | tenacity | 9.0+ | Declarative retry decorators |
| **Rate Limiting** | pyrate-limiter | 4.0+ | Multi-source rate limits |
| **Orchestration** | Prefect | 3.0+ | Python-native, free UI, scheduling |
| **XML Parsing** | lxml | 5.0+ | 2-10× faster than stdlib |
| **Git Operations** | GitPython | 3.1+ | Clone, pull, diff for git-based sources |
| **Excel Parsing** | openpyxl | 3.1+ | SCF Excel parsing |
| **Monitoring** | Prometheus + Grafana | Latest | Industry standard, rich ecosystem |
| **Logging** | structlog | 24.0+ | Structured JSON logs |
| **CLI** | Click | 8.1+ | Declarative, excellent UX |
| **LLM** | Anthropic Claude | API v1 | Haiku 4.5 / Sonnet 4.5 / Opus 4 |
| **Testing** | pytest | 8.0+ | Industry standard, rich plugins |
