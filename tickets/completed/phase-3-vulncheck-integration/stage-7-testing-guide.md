# Stage 7: API/E2E Testing Guide

**Ticket:** phase-3-vulncheck-integration
**Stage:** 7 (API/E2E Testing)
**Created:** 2026-03-05
**Status:** In Progress

---

## Overview

Stage 7 validates Phase 3A VulnCheck Integration through comprehensive testing:
- Unit tests (all 9 agents)
- Canary endpoint tier verification
- Database schema initialization
- Integration tests (agent workflows, database state, edge relationships)
- API endpoint tests (POST /v1/enrich with Phase 2 + Phase 3 merge)

**Exit Condition:** API/E2E gate closes all executable mapped acceptance criteria (`Passed` or explicit user `Waived`)

---

## Prerequisites

### 1. Environment Setup

The project uses `uv` for dependency management. Install dependencies:

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync dependencies (installs all dev dependencies including pytest)
uv sync --all-extras

# Activate virtual environment
source .venv/bin/activate
```

**Alternative (if uv not available):** Install pytest manually:
```bash
# Using system Python
python3 -m pip install pytest pytest-mock pytest-cov responses

# Or create new venv with pip
python3 -m venv .venv-test
source .venv-test/bin/activate
pip install -e ".[dev]"
```

### 2. Configuration

Ensure `.env` file contains required credentials:

```bash
# VulnCheck API (Community tier - 1,000 req/min)
VULNCHECK_API_KEY=your_vulncheck_api_key_here
VULNCHECK_BASE_URL=https://api.vulncheck.com/v3

# ArangoDB (for integration tests)
ARANGO_HOST=http://localhost:8529
ARANGO_USERNAME=root
ARANGO_PASSWORD=your_password
ARANGO_DATABASE=complira_graph_test
```

### 3. ArangoDB Setup (for integration tests)

```bash
# Start ArangoDB container
docker run -d \
  --name arangodb-test \
  -p 8529:8529 \
  -e ARANGO_ROOT_PASSWORD=testpassword \
  arangodb/arangodb:3.11

# Wait for startup
sleep 10

# Initialize test database
python -m complira_graph.db init_schema
```

---

## Test Execution Checklist

### ✅ Task 1: Unit Tests

**Description:** Validate all 9 VulnCheck agents with mocked HTTP client.

**Command:**
```bash
pytest tests/unit/test_vulncheck_agents.py -v --tb=short
```

**Expected Results:**
- 25 test cases pass
- Coverage > 80% for all agent modules
- No import errors
- No test failures

**Test Coverage:**
- `test_vulncheck_kev_agent_initialization` - Agent setup with API key
- `test_vulncheck_kev_agent_transform_data` - Data transformation (1 doc + 2 edges)
- `test_vulncheck_kev_agent_run` - Full workflow (fetch → transform → load)
- `test_vulncheck_nvd2_agent_streaming` - Streaming parser with ijson
- `test_vulncheck_exploits_agent_enrich_cve` - On-demand enrichment
- `test_vulncheck_ransomware_agent_edges` - Ransomware → CVE + TTP edges
- `test_vulncheck_botnets_agent_batch_insert` - Batch processing (500/batch)
- `test_vulncheck_threat_actors_agent_fuzzy_match` - Name deduplication
- `test_vulncheck_exploit_chains_agent_multi_cve` - Multi-CVE chains
- `test_vulncheck_eol_agent_fda_compliance` - EOL → Component edges
- `test_vulncheck_canaries_agent_tier_verification` - 403 graceful handling
- ... (25 total)

**Acceptance Criteria Mapping:**
- AC1: All 9 agents pass unit tests ✅

---

### ✅ Task 2: Canary Endpoint Tier Verification

**Description:** Test if `/v3/index/canaries` is available in Community tier.

**Command:**
```bash
python test_canary_endpoint.py
```

**Expected Results (Option A - Success):**
```
✅ SUCCESS: Canary endpoint available in Community tier!
DECISION: INCLUDE canary intelligence in Phase 3A implementation
Implementation scope: 6 collections, 10 edges, 9 agents
```

**Expected Results (Option B - Tier Restriction):**
```
❌ FORBIDDEN: Canary endpoint requires Professional tier
DECISION: REMOVE canary components from Phase 3A implementation
Updated scope: 5 collections, 9 edges, 8 agents

ACTION REQUIRED:
1. Remove VulnCheckCanariesAgent from src/complira_graph/agents/vulncheck_canaries_agent.py
2. Remove from __init__.py exports
3. Remove canary_observations collection from db.py
4. Remove observed_by_canary edge from db.py
5. Update test_vulncheck_agents.py (remove canary tests)
6. Update requirements.md (scope reduction)
7. Update PHASE_3A_IMPLEMENTATION_SUMMARY.md
```

**Acceptance Criteria Mapping:**
- AC9: Canary endpoint tier verified ✅ or ⚠️ (conditional)

**Next Steps:**
- If 403 Forbidden → Trigger classified re-entry (Local Fix: Stage 6 → 7)
- If 200 OK → Continue with full implementation

---

### ✅ Task 3: Database Schema Initialization

**Description:** Initialize ArangoDB with 6 Phase 3A collections + 10 edges.

**Command:**
```bash
python -m complira_graph.db init_schema
```

**Expected Results:**
```
✅ Created document collections:
   - exploit_intelligence
   - ransomware_families
   - botnets
   - exploit_chains
   - eol_products
   - canary_observations (if tier verified)

✅ Created edge collections:
   - has_exploit_intelligence
   - exploited_by_ransomware
   - exploited_by_botnet
   - exploited_by_threat_actor
   - observed_by_canary (if tier verified)
   - chain_includes_vuln
   - component_eol_status
   - ransomware_uses_technique
   - botnet_uses_technique
   - vuln_triggers_requirement

✅ Created indexes (7 total):
   - exploit_intelligence: cve_id (unique), reported_exploited, exploit_maturity
   - ransomware_families: name (unique), first_seen
   - botnets: name (unique), first_seen
   - exploit_chains: name (unique), attack_complexity
   - eol_products: cpe (unique), eol_date
   - canary_observations: cve_id (unique), first_seen (if tier verified)
   - vulncheck_kev_entries: cve_id (unique), date_added
```

**Verification:**
```bash
# Query collection counts
python -c "from complira_graph.db import get_db; db = get_db(); \
  print('exploit_intelligence:', db.collection('exploit_intelligence').count()); \
  print('ransomware_families:', db.collection('ransomware_families').count()); \
  print('botnets:', db.collection('botnets').count());"
```

**Acceptance Criteria Mapping:**
- AC5: Database schema initialized with 6 collections ✅
- AC6: 10 edge collections created ✅
- AC7: 7 performance indexes created ✅

---

### ✅ Task 4: Integration Tests - Agent Workflows

**Description:** Test end-to-end agent execution (fetch → transform → load).

**Test File:** `tests/integration/test_vulncheck_integration.py`

**Command:**
```bash
pytest tests/integration/test_vulncheck_integration.py -v --tb=short -m "not slow"
```

**Test Cases:**

#### 4.1 VulnCheck KEV Agent - Full Workflow
```python
def test_vulncheck_kev_agent_full_workflow(db, vulncheck_api_key):
    """Test VulnCheckKEVAgent end-to-end with real API."""
    agent = VulnCheckKEVAgent(db)
    stats = agent.run()

    # Assertions
    assert stats["documents_created"] > 3000  # ~3,700 KEV entries
    assert stats["edges_created"] > 6000  # 2 edges per KEV entry

    # Verify database state
    kev_count = db.collection("vulncheck_kev_entries").count()
    assert kev_count == stats["documents_created"]

    # Verify edge relationships
    query = "FOR v IN vulncheck_kev_entries LIMIT 1 RETURN v"
    sample = list(db.aql.execute(query))[0]
    assert "cve_id" in sample
    assert "date_added" in sample
```

#### 4.2 VulnCheck NVD2 Agent - Streaming Parser
```python
def test_vulncheck_nvd2_agent_streaming(db, vulncheck_api_key):
    """Test VulnCheckNVD2Agent with streaming JSON parser (ijson)."""
    agent = VulnCheckNVD2Agent(db)

    # Stream first 1000 CVEs only (full dataset is 244K CVEs)
    stats = agent.run(limit=1000)

    # Assertions
    assert stats["documents_created"] == 1000
    assert stats["memory_usage_mb"] < 100  # Constant memory (ijson)

    # Verify checkpointing
    checkpoint = agent.load_checkpoint()
    assert checkpoint["records_processed"] == 1000
```

#### 4.3 VulnCheck Exploits Agent - On-Demand Enrichment
```python
def test_vulncheck_exploits_agent_enrich(db, vulncheck_api_key):
    """Test on-demand CVE enrichment."""
    agent = VulnCheckExploitsAgent(db)

    # Enrich CVE-2023-12345
    exploit_doc = agent.enrich_cve("CVE-2023-12345")

    # Assertions
    assert exploit_doc is not None
    assert exploit_doc["cve_id"] == "CVE-2023-12345"
    assert "exploit_maturity" in exploit_doc
    assert exploit_doc["exploit_maturity"] in ["High", "Functional", "Proof of Concept", "Unproven"]

    # Verify < 600ms performance
    import time
    start = time.time()
    agent.enrich_cve("CVE-2024-56789")
    elapsed = time.time() - start
    assert elapsed < 0.6  # < 600ms
```

#### 4.4 VulnCheck Ransomware Agent - Edge Creation
```python
def test_vulncheck_ransomware_agent_edges(db, vulncheck_api_key):
    """Test ransomware → CVE + TTP edge creation."""
    agent = VulnCheckRansomwareAgent(db)
    stats = agent.run()

    # Assertions
    assert stats["documents_created"] > 200  # ~300 families
    assert stats["edges_created"] > 600  # Multiple edges per family

    # Verify edge relationships
    query = """
        FOR r IN ransomware_families
            FILTER r.name == "LockBit"
            LET cves = (FOR v, e IN 1..1 OUTBOUND r exploited_by_ransomware RETURN v.cve_id)
            LET ttps = (FOR t, e IN 1..1 OUTBOUND r ransomware_uses_technique RETURN t.technique_id)
            RETURN {name: r.name, cve_count: LENGTH(cves), ttp_count: LENGTH(ttps)}
    """
    result = list(db.aql.execute(query))[0]
    assert result["cve_count"] > 0
    assert result["ttp_count"] > 0
```

#### 4.5 VulnCheck Threat Actors Agent - Fuzzy Merge
```python
def test_vulncheck_threat_actors_fuzzy_merge(db, vulncheck_api_key):
    """Test fuzzy name matching prevents duplicates."""
    agent = VulnCheckThreatActorsAgent(db)

    # Pre-insert existing threat group
    db.collection("threat_groups").insert({
        "_key": "apt29",
        "name": "APT29",
        "aliases": ["Cozy Bear", "The Dukes"],
        "source": "mitre_attack"
    })

    stats = agent.run()

    # Verify no duplicate APT29 created
    query = 'FOR g IN threat_groups FILTER g.name LIKE "APT%29%" RETURN g'
    duplicates = list(db.aql.execute(query))
    assert len(duplicates) == 1  # Only original, no duplicate
```

#### 4.6 VulnCheck Canaries Agent - Graceful 403 Handling
```python
def test_vulncheck_canaries_agent_tier_verification(db, vulncheck_api_key):
    """Test canary agent gracefully handles 403 Forbidden."""
    agent = VulnCheckCanariesAgent(db)

    stats = agent.run()

    # If 403: stats should be empty but no exception raised
    # If 200: stats should have documents
    if stats.get("tier_unavailable"):
        assert stats["documents_created"] == 0
        assert stats["edges_created"] == 0
    else:
        assert stats["documents_created"] > 0
```

**Acceptance Criteria Mapping:**
- AC2: KEV agent workflow passes ✅
- AC3: NVD2 streaming parser works (< 100MB memory) ✅
- AC4: Exploits agent enriches CVE < 600ms ✅
- AC8: Edge relationships validated ✅

---

### ✅ Task 5: API Endpoint Tests

**Description:** Test POST /v1/enrich endpoint with Phase 2 + Phase 3 data merge.

**Test File:** `tests/integration/test_api_vulncheck.py`

**Command:**
```bash
pytest tests/integration/test_api_vulncheck.py -v --tb=short
```

**Test Case - Full Enrichment:**
```python
def test_enrich_cve_with_vulncheck(api_client):
    """Test CVE enrichment merges Phase 2 (NVD/GHSA) + Phase 3 (VulnCheck)."""
    response = api_client.post("/v1/enrich", json={"cve_id": "CVE-2023-12345"})

    assert response.status_code == 200
    data = response.json()

    # Phase 2 data (NVD + GHSA)
    assert "nvd_data" in data
    assert "ghsa_data" in data
    assert data["nvd_data"]["cvss_v3_score"] > 0

    # Phase 3 data (VulnCheck)
    assert "exploit_intelligence" in data
    assert "kev_status" in data
    assert "ransomware_families" in data

    # Exploit maturity
    assert data["exploit_intelligence"]["exploit_maturity"] in [
        "High", "Functional", "Proof of Concept", "Unproven"
    ]

    # KEV status
    if data["kev_status"]["in_vulncheck_kev"]:
        assert "date_added" in data["kev_status"]
        assert "lead_time_days" in data["kev_status"]

    # Ransomware attribution
    if len(data["ransomware_families"]) > 0:
        assert "name" in data["ransomware_families"][0]
        assert "first_seen" in data["ransomware_families"][0]
```

**Acceptance Criteria Mapping:**
- AC10: POST /v1/enrich merges Phase 2 + Phase 3 data ✅

---

## Performance Benchmarks

### Expected Performance Targets

| Agent | Dataset Size | Expected Time | Memory Usage | Rate Limit Impact |
|-------|-------------|---------------|--------------|-------------------|
| **VulnCheck KEV** | 3,700 entries | 4 seconds | 10 MB | 1 request |
| **VulnCheck NVD2** | 244,866 CVEs | 120 seconds | 50 MB (streaming) | 1 request |
| **VulnCheck Exploits** | On-demand | < 600ms per CVE | 5 MB | 1 req/CVE |
| **VulnCheck Ransomware** | 300 families | 3 seconds | 8 MB | 1 request |
| **VulnCheck Botnets** | 150 campaigns | 2 seconds | 6 MB | 1 request |
| **VulnCheck Threat Actors** | 200 actors | 2 seconds | 6 MB | 1 request |
| **VulnCheck Exploit Chains** | 50 chains | 1 second | 4 MB | 1 request |
| **VulnCheck EOL** | 5,000 products | 5 seconds | 12 MB | 1 request |
| **VulnCheck Canaries** | 1,000 observations | 2 seconds | 8 MB | 1 request |

**Total Bulk Sync Time:** ~140 seconds (~2.3 minutes)
**Total Memory:** < 120 MB (streaming + batch processing)
**Rate Limit Usage:** 9 requests (well below 1,000 req/min Community tier limit)

---

## Acceptance Criteria Status

| ID | Acceptance Criteria | Status | Evidence |
|----|-------------------|--------|----------|
| AC1 | All 9 VulnCheck agents pass unit tests | ⏳ Pending | `pytest tests/unit/test_vulncheck_agents.py` |
| AC2 | KEV agent fetches 3,700+ entries in < 5s | ⏳ Pending | Integration test |
| AC3 | NVD2 streaming parser uses < 100MB memory | ⏳ Pending | Integration test |
| AC4 | Exploits agent enriches CVE in < 600ms | ⏳ Pending | Integration test |
| AC5 | Database schema includes 6 Phase 3A collections | ⏳ Pending | `init_schema` output |
| AC6 | 10 edge collections created | ⏳ Pending | `init_schema` output |
| AC7 | 7 performance indexes created | ⏳ Pending | `init_schema` output |
| AC8 | Edge relationships validated (ransomware → CVE + TTP) | ⏳ Pending | Integration test |
| AC9 | Canary endpoint tier verified (200 OK or 403 handled) | ⏳ Pending | `test_canary_endpoint.py` |
| AC10 | POST /v1/enrich merges Phase 2 + Phase 3 data | ⏳ Pending | API integration test |

**Gate Status:** 0/10 passed (requires test execution)

---

## Known Issues and Blockers

### 1. Environment Setup Required
- **Issue:** Virtual environment lacks pytest and dev dependencies
- **Root Cause:** Project uses `uv` for dependency management (uv.lock present)
- **Resolution:** Run `uv sync --all-extras` to install all dependencies
- **Alternative:** Manual pytest installation: `python3 -m pip install pytest pytest-mock`

### 2. Canary Endpoint Verification Pending
- **Issue:** Unknown if `/v3/index/canaries` is available in Community tier
- **Impact:** May need to remove canary components if 403 Forbidden
- **Resolution:** Run `python test_canary_endpoint.py` before integration tests
- **Fallback:** Scope reduction (5 collections, 9 edges, 8 agents)

### 3. ArangoDB Required for Integration Tests
- **Issue:** Integration tests require running ArangoDB instance
- **Resolution:** Start Docker container: `docker run -d -p 8529:8529 arangodb/arangodb:3.11`
- **Alternative:** Skip integration tests: `pytest -m "not requires_db"`

### 4. API Integration Tests Deferred
- **Issue:** POST /v1/enrich endpoint merge logic not yet implemented
- **Scope:** Deferred to Phase 3A-B (RegulatoryTriggerService implementation)
- **Workaround:** Test Phase 3 agents independently, defer API merge tests

---

## Stage 7 Exit Criteria

✅ **Pass Conditions:**
1. All unit tests pass (25/25)
2. Canary endpoint tier verified (200 OK or 403 gracefully handled)
3. Database schema initialized successfully
4. Integration tests pass (6/6 agents)
5. Performance benchmarks met (< 140s bulk sync, < 100MB memory, < 600ms enrichment)
6. All acceptance criteria closed (`Passed` or explicitly `Waived`)

❌ **Fail Conditions:**
1. Unit test failures (requires Local Fix: Stage 6 → 7)
2. Canary 403 without code removal (requires Local Fix: Stage 6 → 7)
3. Database schema errors (requires Local Fix: Stage 6 → 7)
4. Integration test failures (requires classified re-entry)
5. Performance degradation (requires Design Impact: Stage 3 → 4 → 5 → 6 → 7)

🔒 **Blocked Conditions:**
1. ArangoDB unavailable (infra blocker)
2. VulnCheck API key invalid (config blocker)
3. Rate limit exceeded (infra blocker)

---

## Next Steps After Stage 7

Once all acceptance criteria pass, transition to:

**Stage 8: Code Review**
- Review all 9 agent implementations
- Verify DRY/SOLID compliance
- Check error handling and logging
- Validate BaseIngestionAgent pattern adherence
- Security review (API key handling, input validation)

**Stage 9: Docs Sync**
- Update API documentation
- Update architecture diagrams
- Update PHASE_3A_IMPLEMENTATION_SUMMARY.md with test results
- Create user guide for VulnCheck integration

**Stage 10: Handoff / Ticket State**
- Final handoff to user
- Ticket state decision (merge to main, deploy, etc.)
- Update tickets/completed/ directory
- Archive workflow-state.md

---

## Test Execution Logs

### Unit Tests
```
# Run date: TBD
# Command: pytest tests/unit/test_vulncheck_agents.py -v
# Results: TBD
```

### Canary Verification
```
# Run date: TBD
# Command: python test_canary_endpoint.py
# Results: TBD
```

### Integration Tests
```
# Run date: TBD
# Command: pytest tests/integration/test_vulncheck_integration.py -v
# Results: TBD
```

---

**Document Version:** 1.0
**Last Updated:** 2026-03-05
**Next Review:** After test execution
