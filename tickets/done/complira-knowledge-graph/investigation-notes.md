# Investigation Notes: Complira Knowledge Graph Engine

**Ticket:** complira-knowledge-graph
**Investigation Date:** 2026-02-28
**Status:** Complete

---

## Sources Consulted

### Primary References (Project Local)
- `references/Data_sources.rtf` - Complete specifications for 40+ cybersecurity data sources
- `references/Implementation_stack.rtf` - Technology stack decisions (Python 3.12, ArangoDB 3.12, Prefect 3.x, uv)
- `references/Unified_Schema.rtf` - Full ArangoDB schema (36 document collections, 41 edge collections, 7 named graphs)
- `references/LLM_Enhancement.rtf` - LLM enrichment agent specifications (9 agents with prompt strategies)

### External References
- [ArangoDB 3.12 Documentation](https://www.arangodb.com/docs/stable/)
- [python-arango 8.3 API Docs](https://docs.python-arango.com/)
- [Prefect 3.x Documentation](https://docs.prefect.io/)
- [NVD API 2.0 Specification](https://nvd.nist.gov/developers/vulnerabilities)
- [MITRE ATT&CK STIX 2.1 Data](https://github.com/mitre-attack/attack-stix-data)
- [Anthropic Claude API](https://docs.anthropic.com/en/api)

---

## Key Findings

### 1. Architecture Overview

**Database Layer:**
- ArangoDB 3.12 (multi-model: document + graph + search)
- 36 document collections organized into 8 categories:
  - Core vulnerability intelligence (6 collections)
  - Threat & attack frameworks (5 collections)
  - Compliance & regulatory (4 collections)
  - Software identity & supply chain (5 collections)
  - Scanner evidence layers 0-4 (8 collections)
  - Process evidence layer 5 (4 collections)
  - Document provenance layer 6 (3 collections)
  - LLM enrichment infrastructure (1 collection)
- 41 edge collections for relationships
- Deterministic `_key` generation for upserts (e.g., `CVE_2024_1234`, `CWE_79`)

**Ingestion Layer:**
- 23+ deterministic ingestion agents for open data sources
- Plugin-based agent pattern with common interface:
  - `check_for_updates()` → bool
  - `fetch_data()` → list
  - `transform_data(raw)` → list
  - `load_data(transformed)` → IngestionResult
- DAG-based orchestration using Python's `graphlib.TopologicalSorter`
- Critical dependency chains:
  - CWE → NVD CVEs (CVEs reference CWE IDs)
  - ATT&CK → CAPEC (CAPEC maps to ATT&CK techniques)
  - ATT&CK → D3FEND (D3FEND counters ATT&CK)
  - NIST 800-53 → SCF/OLIR (mappings reference controls)

**LLM Enrichment Layer:**
- 9 specialized agents for gap-filling:
  1. **L1: CWE Gap Filler** - Classify ~25K CVEs without CWE (Claude Haiku 4.5)
  2. **L2: PURL→CPE Resolver** - Fuzzy match packages to NVD CPE dictionary (Claude Sonnet 4.5)
  3. **L3: VEX Justification Synthesizer** - Generate VEX documents with evidence (Claude Sonnet 4.5)
  4. **L4: Cross-Framework Regulatory Mapper** - Map CWE to CRA/FDA requirements (Claude Opus 4)
  5. **L5: CVE Description Entity Extractor** - Extract structured metadata (Claude Haiku 4.5)
  6. **L6: Component Identity Deduplicator** - Resolve package aliases (Claude Haiku 4.5)
  7. **L7-L9:** Reserved for future expansion
- All LLM outputs tracked with full provenance in `llm_enrichments` collection

### 2. Data Source Breakdown

**Vulnerability Intelligence (9 sources):**
- NVD API 2.0 (318K+ CVEs, rate limit: 50 req/30s with key)
- OSV.dev (GCS bucket + API, no rate limits)
- CISA KEV (1,507 entries, static JSON)
- EPSS (daily CSV, all scored CVEs)
- VulnCheck v3 (Community tier, 1K req/min)
- GitHub Advisory Database (REST/GraphQL, 5K req/hr)
- Red Hat Security Data API
- Debian Security Tracker (JSON dump)
- Ubuntu CVE data (OVAL format)

**Threat Frameworks (6 sources):**
- MITRE ATT&CK v18.1 (STIX 2.1: 216 techniques, 475 sub-techniques, 176 groups, 784 software)
- CAPEC 3.9 (559 attack patterns, XML)
- D3FEND 1.3.0 (267 defensive techniques, REST API)
- ATLAS 4.4.0 (40 AI/ML techniques, YAML)
- CTID Mappings (ATT&CK → NIST 800-53, STIX bundles)

**Compliance Frameworks (6 sources):**
- NIST OSCAL SP 800-53 Rev 5 (1,007 controls, JSON)
- SCF 2025.4 (100+ framework mappings, Excel)
- NIST OLIR (CSF 2.0 ↔ 800-53 mappings)
- OpenCRE (REST API, concept graph)
- CWE 4.19.1 (930+ weaknesses, XML)

**Exploit Intelligence (4 sources):**
- Metasploit (modules_metadata_base.json, 40-60 MB)
- ExploitDB (files_exploits.csv, 45K-50K exploits)
- Nuclei Templates (9K+ templates, YAML)
- PoC-in-GitHub (CVE → GitHub repos mapping)

**Software Supply Chain (8 sources):**
- deps.dev (Google, 7 ecosystems, PURL support)
- Ecosyste.ms (16+ microservices, 75 registries)
- endoflife.date (432+ products, lifecycle tracking)
- SPDX License List (JSON)
- OSADL compatibility matrix
- OpenSSF Scorecard (repository security scoring)

### 3. Critical Performance Constraints

**Bulk Loading Strategy:**
- Use `collection.import_bulk()` NOT AQL UPSERT
- Performance: 0.03s for 1,000 docs vs 6s with UPSERT (200× faster)
- Batch size: 50,000-100,000 documents per call
- Initial seed workflow:
  1. Drop non-primary indexes
  2. Bulk load via `import_bulk(on_duplicate="update")`
  3. Rebuild indexes
  4. Enable `on_duplicate="update"` for incremental updates

**Indexing:**
- All user-creatable indexes in ArangoDB 3.10+ are `persistent` (hash/skiplist are aliases)
- Enable `cacheEnabled: true` for equality lookups
- Use `storedValues` to cover projections
- Vertex-centric indexes critical for supernodes (composite on edge `_from` + timestamp)

**Capacity Planning:**
- Expected: 10M nodes + 28M edges = 15-25 GB on disk (LZ4 compression)
- Recommended: 32 GB RAM (4-8 GB RocksDB cache, 1.5 GB write buffers, 2-4 GB index caches)
- Single server sufficient (ArangoDB handles 100M+ documents)

### 4. Incremental Update Strategies

**Every source supports delta detection:**

| Source | Strategy | Frequency |
|--------|----------|-----------|
| NVD | `lastModStartDate/lastModEndDate` params (max 120-day range) | Every 2 hours |
| CISA KEV | Download JSON, compare `catalogVersion` | Hourly |
| EPSS | Daily CSV full replacement (hash check) | Daily |
| OSV | Stream `modified_id.csv` from GCS, stop at last timestamp | Daily |
| ATT&CK/Nuclei/ExploitDB | `git pull` + `git diff` to identify changed files | Weekly/Daily |
| CWE/CAPEC | Compare XML root `Version` attribute | Weekly (detect quarterly releases) |
| SCF | GitHub Releases API `tag_name` comparison | Weekly |
| D3FEND | `/api/version.json` endpoint | Weekly |

### 5. Rate Limiting Requirements

**Critical Limits:**
- NVD: 5 req/30s (no key) or 50 req/30s (with key) → Use `pyrate-limiter` with `Rate(50, Duration.SECOND * 30)`
- GitHub: 5,000 req/hr (REST with PAT) → `Rate(5000, Duration.HOUR)`
- EPSS: 1,000 req/min → `Rate(1000, Duration.MINUTE)`
- VulnCheck: 1,000 req/min → `Rate(1000, Duration.MINUTE)`
- OSV.dev: No rate limits currently
- D3FEND, OpenCRE: No authentication required

### 6. Technology Stack Decisions

**Core Runtime:**
- Python 3.12+ (ecosystem fit, LLM SDKs)
- `uv` package manager (10-100× faster than pip)
- Pydantic v2 for data validation
- `asyncio` + `httpx` for concurrent API fetching

**Database:**
- ArangoDB 3.12 Community (free, multi-model)
- `python-arango` 8.3+ (official driver, excellent bulk APIs)
- Docker deployment (matches production)

**Orchestration:**
- Prefect 3.x (Python-native, cron scheduling, free UI)
- Alternative: APScheduler 3.x + SQLite (simpler, <20 agents)
- `graphlib.TopologicalSorter` for DAG execution

**Utilities:**
- `tenacity` 9.1+ for retries (exponential backoff + jitter)
- `pyrate-limiter` 4.0+ for multi-source rate limiting
- `lxml` for XML parsing (2-10× faster than stdlib for large files)
- `GitPython` for git-based sources
- `openpyxl` for SCF Excel parsing

**Monitoring:**
- Prometheus + `prometheus-client` for metrics
- Grafana for dashboards
- `structlog` for structured JSON logging

**LLM:**
- Anthropic Claude API (`anthropic` Python SDK)
- Model selection:
  - Haiku 4.5: Fast classification tasks (CWE, entity extraction)
  - Sonnet 4.5: Complex reasoning (PURL→CPE, VEX generation)
  - Opus 4: Regulatory mapping (one-time, high-value)

---

## Entrypoints & Execution Boundaries

**CLI Entry (`complira` command):**
```
src/complira_graph/cli.py
└── Click CLI with commands:
    ├── seed      - Full initial graph seeding
    ├── update    - Incremental updates
    ├── status    - Health check and metrics
    └── validate  - Data validation queries
```

**Prefect Orchestrator:**
```
src/complira_graph/orchestrator/
├── dag.py           - TopologicalSorter wrapper
├── seed.py          - Full initial seed flow
└── schedules.py     - Prefect deployment definitions
```

**Agent Execution Flow:**
```
BaseIngestionAgent (abstract)
├── check_for_updates() → bool
├── fetch_data() → list[dict]
├── transform_data(raw) → list[Document]
└── load_data(transformed) → IngestionResult
    └── Calls db.import_bulk(on_duplicate="update")
```

**LLM Agent Flow:**
```
BaseLLMAgent (abstract)
├── find_gaps() → list[dict]        # AQL query for missing data
├── enrich(items) → list[Enrichment] # Call LLM API with prompt
├── validate(enrichments) → list     # Filter by confidence threshold
└── persist(valid) → IngestionResult # Write to graph + provenance
```

---

## Touched Modules/Files (Full Implementation)

### Core Infrastructure
```
src/complira_graph/
├── __init__.py
├── cli.py                      # Click CLI
├── config.py                   # Pydantic settings from .env
└── db.py                       # ArangoDB connection, collection setup, bulk ops
```

### Data Models (Pydantic)
```
src/complira_graph/models/
├── __init__.py
├── vulnerability.py            # Vulnerability, EPSSScore, KEVEntry, etc.
├── weakness.py                 # Weakness (CWE)
├── component.py                # Component, CPEEntry, License, PackageHealth
├── threat.py                   # ATTACKTechnique, CAPEC, ATLAS, D3FEND
├── compliance.py               # RegulatoryRequirement, OSCALControl, SCF
├── exploit.py                  # ExploitModule (MSF, EDB, Nuclei, PoC)
└── edges.py                    # All edge models with _from/_to validation
```

### Ingestion Agents (23+)
```
src/complira_graph/agents/
├── __init__.py
├── base.py                     # BaseIngestionAgent ABC
├── nvd.py                      # NVD API 2.0
├── osv.py                      # OSV.dev (GCS bulk + API)
├── cisa_kev.py                 # CISA KEV JSON feed
├── epss.py                     # FIRST.org EPSS daily CSV
├── vulncheck.py                # VulnCheck v3 API
├── ghsa.py                     # GitHub Advisory Database
├── cwe.py                      # CWE XML parser
├── capec.py                    # CAPEC XML parser
├── attack.py                   # ATT&CK STIX 2.1 parser
├── d3fend.py                   # D3FEND REST API
├── atlas.py                    # ATLAS YAML parser
├── ctid.py                     # CTID ATT&CK→800-53 STIX mappings
├── oscal.py                    # NIST OSCAL SP 800-53 JSON
├── scf.py                      # SCF Excel parser (openpyxl)
├── opencre.py                  # OpenCRE REST API
├── nuclei.py                   # Nuclei templates YAML (git-based)
├── exploitdb.py                # ExploitDB CSV (git-based)
├── metasploit.py               # Metasploit metadata JSON (git-based)
├── poc_github.py               # PoC-in-GitHub JSON (git-based)
├── eol.py                      # endoflife.date API
├── spdx_licenses.py            # SPDX License List JSON
├── osadl.py                    # OSADL compatibility matrix
├── deps_dev.py                 # deps.dev API
└── redhat.py                   # Red Hat Security Data API
```

### LLM Enrichment Agents (9)
```
src/complira_graph/llm_agents/
├── __init__.py
├── base_llm.py                 # BaseLLMAgent ABC
├── cwe_classifier.py           # L1: CWE Gap Filler
├── purl_cpe_resolver.py        # L2: Fuzzy PURL→CPE Resolver
├── vex_synthesizer.py          # L3: VEX Justification Generator
├── regulatory_mapper.py        # L4: Cross-Framework Regulatory Mapper
├── entity_extractor.py         # L5: CVE Description Entity Extractor
├── identity_deduplicator.py    # L6: Component Identity Deduplicator
└── [L7-L9 reserved]
```

### Orchestration
```
src/complira_graph/orchestrator/
├── __init__.py
├── dag.py                      # TopologicalSorter wrapper + dependency graph
├── seed.py                     # Full initial seed flow with DAG
└── schedules.py                # Prefect deployment definitions (cron)
```

### Transforms & Utilities
```
src/complira_graph/transforms/
├── __init__.py
├── keys.py                     # Deterministic _key generation (CVE→CVE_2024_1234)
├── stix.py                     # STIX 2.1 → ArangoDB document converter
├── xml_parser.py               # lxml iterparse helpers (memory-efficient)
└── normalize.py                # PURL/CPE/CVE normalization
```

### Monitoring
```
src/complira_graph/monitoring/
├── __init__.py
├── metrics.py                  # Prometheus metrics definitions
└── health.py                   # Health check endpoints
```

---

## Current Naming Conventions

**File/Module Style:**
- Snake_case for Python files: `cisa_kev.py`, `implementation_plan.py`
- Class names: PascalCase (`BaseIngestionAgent`, `VulnerabilityModel`)
- Functions: snake_case (`check_for_updates`, `load_data`)

**ArangoDB Collections:**
- Document collections: snake_case plural (`vulnerabilities`, `weaknesses`, `attack_techniques`)
- Edge collections: snake_case verb phrases (`has_weakness`, `exploited_in_wild`, `depends_on`)
- Keys: Normalized with underscores (`CVE_2024_1234`, `CWE_79`, `T1190`)

**Git:**
- Branch naming: `codex/<ticket-name>` (enforced by workflow)
- Commit messages: Conventional Commits style

---

## Unknowns / Open Questions

### 1. ❓ Prefect vs APScheduler Trade-off
**Question:** Given 23 deterministic agents + 9 LLM agents (32 total), is Prefect 3.x overhead worth it vs simpler APScheduler?

**Impact:** Infrastructure complexity, debugging experience, monitoring capabilities

**Decision Needed:** Stage 3 (Design Basis)

### 2. ❓ LLM Cost Estimation
**Question:** With ~25K CVEs for CWE classification + ~10K packages for PURL→CPE + VEX generation, what's realistic monthly LLM cost?

**Current Estimate:**
- L1 (CWE): ~10M tokens × $0.25/1M input = $2.50 one-time
- L2 (PURL→CPE): ~5M tokens × $3/1M (Sonnet) = $15 one-time
- L3 (VEX): ~$0.50-$5 per customer SBOM (recurring)
- L4 (Regulatory): ~$25 one-time (Opus)

**Total one-time seed:** ~$45, **recurring:** depends on VEX usage volume

**Impact:** Budget constraint (<$50/month target)

**Decision Needed:** Confirm acceptable in Stage 2

### 3. ❓ ArangoDB Schema Migration Strategy
**Question:** How to handle schema evolution without downtime? (e.g., adding new edge types, modifying collection indexes)

**Impact:** Production reliability, rollback capability

**Decision Needed:** Stage 3 (Design Basis)

### 4. ❓ Multi-Tenancy Approach
**Question:** Requirements doc says "handled at application layer" - what's the pattern?
- Tenant ID field in every document?
- Separate databases per tenant?
- Graph-based access control?

**Impact:** Query patterns, index design, data isolation

**Decision Needed:** Stage 2 (Requirements Refinement) or defer to v2.0

### 5. ❓ SBOM Ingestion Format
**Question:** VEX generation requires SBOM upload - which formats to support?
- CycloneDX JSON/XML?
- SPDX JSON/RDF?
- Both?

**Impact:** Parser complexity, PURL extraction logic

**Decision Needed:** Stage 2 (Requirements Refinement)

---

## Implications for Requirements/Design

### Requirements Implications

**R-1: Clarify Multi-Tenancy Approach**
- Current requirement says "out of scope at database level"
- Need to specify application-layer pattern in Stage 2
- Impacts: query filtering, audit logging, data isolation

**R-2: Define SBOM Support Matrix**
- VEX generation (UC-4) requires SBOM upload
- Must specify CycloneDX/SPDX support in acceptance criteria
- Impacts: parser selection, component extraction logic

**R-3: Quantify Acceptable LLM Costs**
- Budget constraint is "<$50/month"
- Need user confirmation that ~$45 one-time seed + VEX-driven recurring is acceptable
- Impacts: LLM agent activation schedule, model selection

### Design Implications

**D-1: Orchestration Layer Choice (Prefect vs APScheduler)**
- 32 total agents pushes toward Prefect's richer monitoring
- But adds PostgreSQL dependency + learning curve
- Alternative: Start with APScheduler, graduate to Prefect if needed
- **Decision Point:** Stage 3 (Design Basis)

**D-2: Agent Parallelism Limits**
- Reference doc recommends 3-4 concurrent ArangoDB writers
- Need to design semaphore/queue system in orchestrator
- Impacts: DAG executor implementation

**D-3: LLM Agent Execution Model**
- Run after deterministic pipeline completes? (sequential)
- Run in parallel with separate DAG? (concurrent)
- Hybrid: Some LLM agents require deterministic data first (e.g., L1 needs NVD CVEs)
- **Decision Point:** Stage 3 (Design Basis)

**D-4: Error Handling Strategy**
- NVD has known reliability issues (503 errors, enrichment pauses)
- Need circuit breaker pattern for unreliable sources
- Dead letter queue for failed enrichments?
- **Decision Point:** Stage 3 (Design Basis)

**D-5: Index Strategy**
- Drop-and-rebuild for initial seed is clear
- For incremental updates with `on_duplicate="update"`, keep indexes?
- Trade-off: update speed vs query availability
- **Decision Point:** Stage 3 (Design Basis)

---

## Scope Triage

### Scope Classification: **LARGE**

**Justification:**
1. **Estimated files touched:** 40+ Python modules across 5 packages
2. **New public APIs:** CLI with 4+ commands, potential REST API for VEX generation
3. **Schema changes:** 36 new collections + 41 edge types (greenfield database)
4. **Multi-layer impact:**
   - Data ingestion layer (23 agents)
   - LLM enrichment layer (9 agents)
   - Database layer (schema + indexes + bulk loading)
   - Orchestration layer (Prefect/APScheduler + DAG)
   - Monitoring layer (Prometheus + Grafana)
   - API layer (CLI + potential REST)
5. **Architectural impact:** Full system design required for large-scale data pipeline

### Workflow Depth Decision: **Large**

**Artifacts Required:**
- ✅ Stage 2: Refine `requirements.md` to `Design-ready` (address unknowns, clarify acceptance criteria)
- ✅ Stage 3: Create `proposed-design.md` (architecture direction + separation of concerns)
- ✅ Stage 4: Build `future-state-runtime-call-stack.md` per use case
- ✅ Stage 5: Run iterative deep-review rounds until `Go Confirmed` (two consecutive clean rounds)
- ✅ Stage 6: Create `implementation-plan.md` + `implementation-progress.md` + source code
- ✅ Stage 7: API/E2E testing
- ✅ Stage 8: Code review
- ✅ Stage 9: Docs sync
- ✅ Stage 10: Final handoff

---

## Next Steps (Immediate)

1. **Transition to Stage 2** (Requirements Refinement)
   - Address unknowns #1-#5 above
   - Refine multi-tenancy approach
   - Specify SBOM format support
   - Confirm LLM cost budget
   - Update `requirements.md` to `Design-ready` status

2. **Stage 3 Prep** (Design Basis)
   - Prepare architectural decision records for:
     - Orchestration layer (Prefect vs APScheduler)
     - LLM agent execution model (sequential vs concurrent)
     - Error handling patterns
     - Index strategy for incremental updates

---

## Investigation Complete

**Status:** ✅ **COMPLETE**
**Scope:** **LARGE**
**Next Stage:** Requirements Refinement (Stage 2)
**Blocker:** None
