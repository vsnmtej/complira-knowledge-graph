# Requirements: Complira Knowledge Graph Engine

**Status:** `Design-ready`
**Last Updated:** 2026-02-28 (Refined from Draft)
**Ticket:** complira-knowledge-graph
**Scope:** LARGE

---

## Goal / Problem Statement

Build a production-grade cybersecurity compliance knowledge graph platform that:

1. **Ingests 40+ open data sources** (NVD, ATT&CK, CWE, CISA KEV, compliance frameworks, exploit databases)
2. **Stores data in ArangoDB** as a unified graph (~10M nodes, ~28M edges)
3. **Provides LLM enrichment** to fill gaps (CWE classification, PURL→CPE resolution, VEX justification)
4. **Maps vulnerabilities to regulatory requirements** (CRA, FDA 524B, IEC 62304, NIST 800-53)
5. **Enables compliance queries** across the entire knowledge graph

**Business Value:**
- Automates regulatory compliance assessment for cybersecurity products
- Reduces manual VEX justification time from 15-30 minutes to <1 minute per CVE
- Provides defensible audit trail for regulatory submissions

---

## In-Scope Use Cases

### UC-1: Initial Knowledge Graph Seeding
**Actor:** Platform Operator
**Flow:**
1. Operator runs `complira seed` command
2. System executes all 40+ ingestion agents in dependency order (DAG)
3. System populates ArangoDB with ~10M nodes and ~28M edges
4. System reports completion status and metrics

**Success Criteria:**
- All collections created (36 document, 41 edge)
- Data successfully loaded from all sources
- Dependency ordering respected (e.g., CWE loads before NVD CVEs)

### UC-2: Incremental Updates
**Actor:** Scheduled Job / Platform Operator
**Flow:**
1. System runs scheduled update jobs (hourly/daily/weekly/quarterly)
2. Each agent checks for updates using source-specific detection (lastModStartDate, git diff, version comparison)
3. System fetches only delta records
4. System upserts into ArangoDB using deterministic `_key` values

**Success Criteria:**
- Only changed records are processed
- No duplicate nodes/edges created
- Update completes within reasonable time (<2 hours for NVD delta)

### UC-3: LLM Gap Filling - CWE Classification
**Actor:** LLM Enrichment Agent
**Flow:**
1. Agent queries for CVEs without CWE classification
2. Agent sends CVE descriptions to Claude Haiku 4.5
3. LLM returns CWE classification with confidence score
4. If confidence >= 0.85, agent creates `has_weakness` edge
5. Agent stores provenance in `llm_enrichments` collection

**Success Criteria:**
- ~25,000 unclassified CVEs are processed
- Confidence scores recorded
- Full provenance tracked (model, input hash, token counts)

### UC-4: VEX Justification Generation
**Actor:** Compliance Analyst / API Consumer
**Flow:**
1. User uploads SBOM or selects component+CVE pair
2. System queries graph for all evidence (CWE, EPSS, KEV status, exploits, hardening, SAST/DAST findings)
3. LLM (Claude Sonnet 4.5) generates VEX justification with specific evidence citations
4. System returns VEX document with status (affected/not_affected/fixed/under_investigation)

**Success Criteria:**
- VEX status determined with high confidence
- All claims cite specific evidence sources
- Generated in <30 seconds per CVE

### UC-5: Regulatory Blast Radius Query
**Actor:** Compliance Analyst
**Flow:**
1. Analyst provides CVE ID
2. System traverses: CVE → CWE → Regulatory Requirements → Frameworks
3. System returns all affected regulations (CRA, FDA 524B, NIST 800-53, etc.)
4. System provides evidence chain for each mapping

**Success Criteria:**
- All regulatory impacts identified
- Evidence chain is complete and auditable
- Query completes in <5 seconds

---

## Acceptance Criteria

### Functional Requirements

**FR-1: Data Ingestion**
- [ ] All 40+ data sources have functional agents
- [ ] Agents handle rate limiting correctly (NVD: 50 req/30s, GitHub: 5000/hr)
- [ ] Incremental updates work for all sources
- [ ] Failed ingestions are logged with retry logic

**FR-2: Database Schema**
- [ ] All 36 document collections created with correct schema
- [ ] All 41 edge collections created with `_from`/`_to` validation
- [ ] Indexes created for performance (persistent + cacheEnabled)
- [ ] Deterministic `_key` generation works for all entity types

**FR-3: LLM Enrichment**
- [ ] 9 LLM agents implemented (CWE classifier, PURL→CPE, VEX, etc.)
- [ ] Provenance tracking for all LLM outputs
- [ ] Confidence thresholds enforced
- [ ] Token usage and costs tracked

**FR-4: Query Performance**
- [ ] Regulatory blast radius query: <5 seconds
- [ ] VEX generation: <30 seconds per CVE
- [ ] Graph traversal for 3-hop queries: <10 seconds

### Non-Functional Requirements

**NFR-1: Scalability**
- [ ] Handle 10M+ nodes and 28M+ edges
- [ ] Support concurrent ingestion (3-4 agents in parallel)
- [ ] Single server deployment sufficient (32GB RAM, NVMe SSD)

**NFR-2: Reliability**
- [ ] Retry logic with exponential backoff for API failures
- [ ] Graceful shutdown for in-progress agents
- [ ] Health checks for ArangoDB, Prefect

**NFR-3: Observability**
- [ ] Prometheus metrics for all agents
- [ ] Structured logging with tenant/product isolation
- [ ] Grafana dashboards for monitoring

**NFR-4: Security**
- [ ] API keys stored in environment variables (`.env` file, not committed)
- [ ] No secrets in git repository (enforce with `.gitignore` and pre-commit hook)
- [ ] Read-only access for query endpoints (ArangoDB user permissions)

**NFR-5: Cost Efficiency**
- [ ] Total infrastructure cost: <€100/month (VPS + storage + LLM)
- [ ] LLM API costs: <$100/month (tracked via Prometheus)
- [ ] Storage optimization: LZ4 compression enabled in ArangoDB

---

## Out of Scope (v1.0)

- **Multi-tenancy:** Database-level isolation (separate ArangoDB instances per tenant). Application-layer approach: Add `tenant_id: string` field to all collections, filter queries with `FILTER doc.tenant_id == @tenant`. Deferred to v2.0.
- **High Availability / Clustering:** Single-server deployment acceptable for v1.0
- **Real-time streaming ingestion:** Scheduled batch updates sufficient
- **Custom web UI:** Focus on API/CLI only
- **Support for non-open data sources:** Commercial threat intel feeds (e.g., Recorded Future, Mandiant)

---

## Constraints

- **Budget:** Minimize LLM API costs (target <$50/month for enrichment)
- **Infrastructure:** Single VPS deployment (Hetzner/OVH ~€70-90/month)
- **Timeline:** MVP with core ingestion agents in 4-6 weeks
- **Dependencies:** Must use open/free data sources only
- **Compliance:** Output must be audit-ready for FDA/CRA submissions

---

## Resolved Decisions

### 1. Multi-Tenancy Approach (Resolved)
**Decision:** Application-layer filtering with `tenant_id` field
**Rationale:** Simpler for v1.0, deferred to v2.0 for advanced isolation
**Implementation:** All queries include `FILTER doc.tenant_id == @tenant` predicate

### 2. SBOM Format Support (Resolved)
**Decision:** Support CycloneDX JSON (primary) and SPDX JSON (secondary)
**Rationale:** CycloneDX has better PURL support, SPDX for compatibility
**Acceptance Criteria:**
- [ ] Parser for CycloneDX JSON v1.5+
- [ ] Parser for SPDX JSON v2.3+
- [ ] Extract PURLs, CPEs, licenses from both formats
- [ ] Map components to graph `components` collection

### 3. LLM Cost Budget (Resolved)
**Decision:** Acceptable budget is **$100/month** for v1.0
**Breakdown:**
- One-time seed: ~$45 (CWE classification, PURL→CPE, regulatory mapping)
- Recurring VEX generation: ~$0.50-$5 per customer SBOM
- Target: 10-20 customer SBOMs/month = ~$10-$100/month
**Acceptance Criteria:**
- [ ] Track LLM token usage in Prometheus metrics
- [ ] Alert if monthly cost exceeds $100
- [ ] Monthly cost report in Grafana dashboard

### 4. Update Frequency (Resolved)
**Decision:** Tiered update schedule by source volatility
**Schedule:**
- **Hourly:** CISA KEV (critical alerts)
- **Every 2 hours:** NVD (active CVE updates)
- **Daily:** EPSS, OSV, GitHub Advisories, CISA Vulnrichment
- **Weekly:** ATT&CK, CAPEC, D3FEND, ATLAS, CWE, SCF, endoflife.date
- **Quarterly:** Regulatory frameworks (CRA, FDA, IEC standards - manual updates)

### 5. Backup Strategy (Resolved)
**Decision:** Daily `arangodump` to S3-compatible storage (Backblaze B2)
**Rationale:** Sufficient for v1.0, upgrade to streaming replication in v2.0
**Acceptance Criteria:**
- [ ] Daily cron job for `arangodump --all-databases`
- [ ] Retention: 30 daily backups, 12 monthly backups
- [ ] Restore tested monthly

## Open Questions (Stage 3 Design Decisions)

These will be addressed in Stage 3 (Proposed Design):

1. **Orchestration Layer:** Prefect 3.x vs APScheduler? (Design decision)
2. **LLM Execution Model:** Sequential after deterministic pipeline or concurrent DAG? (Design decision)
3. **Error Handling Pattern:** Circuit breaker, dead letter queue, or retry-only? (Design decision)
4. **Index Strategy:** Drop-and-rebuild for incremental updates or keep indexes? (Design decision)

---

## References

- `references/Data_sources.rtf` - All 40+ data source specifications
- `references/Implementation_stack.rtf` - Technology stack details
- `references/Unified_Schema.rtf` - Complete ArangoDB schema
- `references/LLM_Enhancement.rtf` - LLM agent specifications
