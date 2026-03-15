# Phase 4 - Regulatory Framework Integration: Proposed Design

**Date:** 2026-03-05
**Stage:** 3 (Design Basis)
**Status:** v1
**Scope:** SMALL (1-2 days, 2-4 files, 600-800 LOC)

---

## Executive Summary

Phase 4 is a **simple data ingestion task** leveraging existing infrastructure. No new agents, services, or database schema changes required.

**What Exists:**
- ✅ YAMLRegulatoryAgent (production-ready, framework-agnostic)
- ✅ FDA 524B YAML (12 requirements, data/regulations/fda_524b.yaml)
- ✅ CRA YAML (8 requirements, data/regulations/cra.yaml)
- ✅ Database schema (regulatory_requirements collection)

**What We'll Build:**
- 1 ingestion script (scripts/ingest_regulatory_frameworks.py, ~150-200 LOC)
- 1 test file (tests/test_regulatory_ingestion.py, ~150-200 LOC)
- 1-2 documentation files (docs/PHASE_4_REGULATORY_FRAMEWORK_INTEGRATION.md, ~300-400 LOC)

**Estimated Effort:** 8-10 hours (1-2 days)

---

## Architecture Overview

### High-Level Flow

```
[Operator]
    ↓ runs
[scripts/ingest_regulatory_frameworks.py]
    ↓ invokes
[YAMLRegulatoryAgent] (already exists)
    ↓ reads
[data/regulations/*.yaml] (already exists)
    ↓ validates schema
[YAML Schema Validator] (already exists in agent)
    ↓ generates keys
[RegulatoryKeyGenerator] (already exists)
    ↓ inserts/updates
[regulatory_requirements collection] (already exists)
    ↓ returns
[Ingestion Statistics]
```

**Key Insight:** We're orchestrating existing components, not building new infrastructure.

---

## Component Design

### Component 1: Ingestion Script

**File:** `scripts/ingest_regulatory_frameworks.py`
**LOC:** ~150-200 lines
**Purpose:** Simple CLI script to run YAMLRegulatoryAgent for FDA 524B and CRA

**Architecture:**
```python
#!/usr/bin/env python3
"""
Ingest FDA 524B and EU CRA regulatory requirements.

Usage:
    python scripts/ingest_regulatory_frameworks.py [--frameworks FDA_524B,CRA] [--dry-run]

Examples:
    # Ingest both FDA and CRA
    python scripts/ingest_regulatory_frameworks.py

    # Ingest only FDA 524B
    python scripts/ingest_regulatory_frameworks.py --frameworks FDA_524B

    # Dry run (validation only)
    python scripts/ingest_regulatory_frameworks.py --dry-run
"""

import argparse
import time
from complira_graph.db import get_db
from complira_graph.agents.yaml_regulatory import YAMLRegulatoryAgent

def ingest_framework(framework_key: str, dry_run: bool = False):
    """Ingest a single regulatory framework"""
    # 1. Initialize database connection
    # 2. Create YAMLRegulatoryAgent instance
    # 3. Run agent (or validate only if dry_run)
    # 4. Return statistics
    pass

def main():
    # 1. Parse CLI arguments
    # 2. For each framework: FDA_524B, CRA
    # 3. Call ingest_framework()
    # 4. Print summary statistics
    # 5. Exit with appropriate code
    pass
```

**Key Features:**
- ✅ CLI argument parsing (--frameworks, --dry-run)
- ✅ Progress reporting (per-framework statistics)
- ✅ Error handling (catch exceptions, report failures)
- ✅ Dry-run mode (validation without insertion)
- ✅ Exit codes (0 = success, 1 = failure)

**Dependencies:**
- argparse (stdlib)
- complira_graph.db.get_db (already exists)
- complira_graph.agents.yaml_regulatory.YAMLRegulatoryAgent (already exists)

---

### Component 2: YAMLRegulatoryAgent (Already Exists)

**File:** `src/complira_graph/agents/yaml_regulatory.py`
**LOC:** ~500 lines (already implemented)
**Purpose:** Generic YAML-based regulatory framework ingestion

**Usage:**
```python
from complira_graph.agents.yaml_regulatory import YAMLRegulatoryAgent
from complira_graph.db import get_db

db = get_db()

# Ingest FDA 524B
fda_agent = YAMLRegulatoryAgent(db, framework_key="FDA_524B")
fda_result = fda_agent.run()
print(f"FDA 524B: {fda_result['documents_created']} requirements ingested")

# Ingest CRA
cra_agent = YAMLRegulatoryAgent(db, framework_key="CRA")
cra_result = cra_agent.run()
print(f"CRA: {cra_result['documents_created']} requirements ingested")
```

**Features (already implemented):**
- ✅ Framework-agnostic (supports any YAML file)
- ✅ Schema validation with helpful error messages
- ✅ Deterministic key generation (via RegulatoryKeyGenerator)
- ✅ Upsert logic (handles duplicates)
- ✅ Checkpoint support (for large frameworks)
- ✅ Structured logging (with structlog)

**No changes needed to this component.**

---

### Component 3: YAML Data Files (Already Exist)

**File 1:** `data/regulations/fda_524b.yaml`
- **LOC:** 272 lines
- **Requirements:** 12 FDA 524B requirements
- **Format:** Manually curated YAML with framework metadata + requirements list
- **Sample:**
```yaml
framework:
  key: FDA_524B
  name: "FDA Section 524B - Cybersecurity in Medical Devices"
  version: "Draft Guidance 2023"

requirements:
  - key: FDA_524B_V_A_1
    requirement_id: "V.A.1"
    title: "Software Bill of Materials (SBOM)"
    obligation_level: shall
    # ... more fields
```

**File 2:** `data/regulations/cra.yaml`
- **LOC:** 409 lines
- **Requirements:** 8 CRA Annex I essential requirements
- **Format:** Manually curated YAML with framework metadata + annex_i_requirements list
- **Sample:**
```yaml
framework:
  key: CRA
  name: "Cyber Resilience Act"
  version: "Regulation (EU) 2024/2847"

annex_i_requirements:
  - annex: "I"
    section: 1
    title: "Security by design and by default"
    obligation_level: shall
    # ... more fields
```

**No changes needed to these files.**

---

### Component 4: Database Schema (Already Exists)

**Collection:** `regulatory_requirements`
**Current State:** 32 requirements (27 IEC 62304, 3 CRA, 2 FDA 524B)
**After Phase 4:** 52 requirements (27 IEC + 14 FDA + 11 CRA)

**Schema:**
```json
{
  "_key": "FDA_524B_V_A_1",
  "_id": "regulatory_requirements/FDA_524B_V_A_1",
  "framework": "FDA_524B",
  "requirement_id": "V.A.1",
  "title": "Software Bill of Materials (SBOM)",
  "text": "Manufacturers shall maintain a current SBOM...",
  "requirement_type": "procedural",
  "obligation_level": "shall",
  "applies_to": ["manufacturer"],
  "evidence_types": [...],
  "deadline": "2025-09-01",
  "created_at": "2026-03-05T...",
  "source": "FDA Section 524B"
}
```

**No schema changes needed.** YAMLRegulatoryAgent handles all field mapping.

---

## Testing Strategy

### Unit Tests

**File:** `tests/test_regulatory_ingestion.py`
**LOC:** ~150-200 lines
**Coverage:** Ingestion script + validation

**Test Cases:**
```python
class TestRegulatoryIngestion:
    """Test regulatory framework ingestion"""

    def test_fda_524b_ingestion(self):
        """Test FDA 524B requirements ingestion"""
        # 1. Run YAMLRegulatoryAgent for FDA_524B
        # 2. Assert 12 requirements inserted
        # 3. Verify requirement metadata completeness
        # 4. Check no errors

    def test_cra_ingestion(self):
        """Test CRA requirements ingestion"""
        # 1. Run YAMLRegulatoryAgent for CRA
        # 2. Assert 8 requirements inserted
        # 3. Verify requirement metadata completeness
        # 4. Check no errors

    def test_dry_run_mode(self):
        """Test dry-run mode (validation only)"""
        # 1. Run ingestion script with --dry-run
        # 2. Assert no database changes
        # 3. Verify validation passes

    def test_duplicate_handling(self):
        """Test duplicate requirement handling"""
        # 1. Ingest FDA 524B twice
        # 2. Assert still only 12 requirements
        # 3. Verify upsert logic works

    def test_invalid_framework_key(self):
        """Test error handling for invalid framework"""
        # 1. Try to ingest non-existent framework
        # 2. Assert appropriate error

    def test_yaml_validation_error(self):
        """Test YAML schema validation error handling"""
        # 1. Mock invalid YAML
        # 2. Assert validation error caught
        # 3. Verify helpful error message
```

**Estimated Effort:** 2-3 hours

---

### Integration Tests

**Approach:** Manual testing (no automated integration tests for SMALL scope)

**Test Plan:**
1. **Pre-Test State Verification:**
   - Query database: 32 requirements (27 IEC, 3 CRA, 2 FDA)

2. **FDA 524B Ingestion Test:**
   - Run: `python scripts/ingest_regulatory_frameworks.py --frameworks FDA_524B`
   - Verify: 44 requirements (32 + 12 FDA)
   - Spot-check: V.A.1 SBOM requirement exists

3. **CRA Ingestion Test:**
   - Run: `python scripts/ingest_regulatory_frameworks.py --frameworks CRA`
   - Verify: 52 requirements (44 + 8 CRA)
   - Spot-check: Annex I.1 Security by design requirement exists

4. **Idempotency Test:**
   - Run: `python scripts/ingest_regulatory_frameworks.py` (both frameworks)
   - Verify: Still 52 requirements (no duplicates)

5. **Database Verification:**
   - Query: `FOR req IN regulatory_requirements COLLECT framework = req.framework WITH COUNT INTO count RETURN {framework, count}`
   - Expected: IEC_62304: 27, FDA_524B: 14, CRA: 11

**Estimated Effort:** 1 hour

---

### Performance Testing

**Target:** Ingestion time < 10 seconds for FDA + CRA (20 requirements)

**Test:**
```bash
time python scripts/ingest_regulatory_frameworks.py
```

**Expected Result:**
```
FDA_524B: 12 requirements ingested in 0.5s
CRA: 8 requirements ingested in 0.4s
Total: 20 requirements ingested in 0.9s
```

**Estimated Effort:** 15 minutes

---

## Implementation Plan

### Phase 4A: Ingestion Script (2 hours)

**File:** `scripts/ingest_regulatory_frameworks.py`

**Tasks:**
1. Create file with CLI argument parsing
2. Implement `ingest_framework()` function
3. Add progress reporting (per-framework)
4. Add error handling
5. Add dry-run mode
6. Test manually with FDA 524B

**Deliverable:** Functional ingestion script (~150-200 LOC)

---

### Phase 4B: Testing (2-3 hours)

**File:** `tests/test_regulatory_ingestion.py`

**Tasks:**
1. Create test file with pytest setup
2. Implement 6 unit test cases (listed above)
3. Run tests: `pytest tests/test_regulatory_ingestion.py -v`
4. Fix any failures
5. Verify 100% test pass rate

**Deliverable:** Comprehensive unit tests (~150-200 LOC)

---

### Phase 4C: Integration Testing (1 hour)

**Manual Tests:**

**Tasks:**
1. Run manual integration tests (listed above)
2. Verify database state after each test
3. Measure performance (time ingestion)
4. Document test results

**Deliverable:** Manual test results documented

---

### Phase 4D: Documentation (2-3 hours)

**File 1:** `docs/PHASE_4_REGULATORY_FRAMEWORK_INTEGRATION.md`
**LOC:** ~300-400 lines

**Content:**
- Executive summary
- What was implemented (ingestion script)
- What was ingested (FDA 524B + CRA requirements)
- How to use (CLI examples)
- Database state (52 requirements)
- Testing results
- Known limitations (placeholder migration deferred)

**File 2:** `README.md` (update)
**LOC:** ~10-20 lines

**Content:**
- Add Phase 4 to completed phases list
- Update regulatory framework coverage (FDA 524B, CRA, IEC 62304)

**Deliverable:** Comprehensive documentation

---

## File Structure

```
cybersecurity-compliance-app/
├── scripts/
│   └── ingest_regulatory_frameworks.py   ← NEW (150-200 LOC)
├── tests/
│   └── test_regulatory_ingestion.py      ← NEW (150-200 LOC)
├── docs/
│   ├── PHASE_4_REGULATORY_FRAMEWORK_INTEGRATION.md  ← NEW (300-400 LOC)
│   └── README.md                          ← UPDATED (10-20 LOC)
├── data/regulations/
│   ├── fda_524b.yaml                      ← EXISTS (272 LOC)
│   └── cra.yaml                           ← EXISTS (409 LOC)
└── src/complira_graph/agents/
    └── yaml_regulatory.py                 ← EXISTS (~500 LOC)

TOTAL NEW LOC: 610-820 lines
TOTAL NEW FILES: 2 files (script + test)
TOTAL UPDATED FILES: 1 file (README)
TOTAL DOCUMENTATION: 1 file (Phase 4 docs)
```

---

## Risk Mitigation

### Risk 1: YAML Schema Compatibility (LOW)

**Mitigation:**
- YAMLRegulatoryAgent has built-in schema validation
- Validation errors caught immediately with helpful messages
- Dry-run mode allows validation without database changes

**Test:**
```bash
python scripts/ingest_regulatory_frameworks.py --dry-run
```

---

### Risk 2: Duplicate Requirements (LOW)

**Mitigation:**
- YAMLRegulatoryAgent uses deterministic key generation
- Agent uses upsert logic (INSERT OR REPLACE)
- Database enforces unique _key constraint

**Test:**
Run ingestion twice, verify database still has 52 requirements (not 104)

---

### Risk 3: Database Connection Failures (LOW)

**Mitigation:**
- get_db() function handles connection errors
- Ingestion script catches and reports database exceptions
- Structured logging provides detailed error context

**Test:**
Stop ArangoDB, run script, verify graceful error message

---

## Success Criteria

### Functional Criteria

1. ✅ Ingestion script successfully ingests FDA 524B (12 requirements)
2. ✅ Ingestion script successfully ingests CRA (8 requirements)
3. ✅ Database contains 52 total requirements after ingestion
4. ✅ All unit tests pass (6/6 test cases)
5. ✅ Dry-run mode validates without inserting
6. ✅ Idempotency verified (run twice, same result)

### Non-Functional Criteria

7. ✅ Ingestion time < 10 seconds for FDA + CRA
8. ✅ Error messages are helpful and actionable
9. ✅ Code follows project conventions (structlog, type hints, docstrings)
10. ✅ Documentation complete and comprehensive

---

## Dependencies

### Already Satisfied ✅
- ✅ YAMLRegulatoryAgent exists (src/complira_graph/agents/yaml_regulatory.py)
- ✅ FDA 524B YAML exists (data/regulations/fda_524b.yaml, 12 requirements)
- ✅ CRA YAML exists (data/regulations/cra.yaml, 8 requirements)
- ✅ Database schema compatible (regulatory_requirements collection)
- ✅ RegulatoryKeyGenerator exists (src/complira_graph/utils/regulatory_keys.py)

### External Dependencies
- None (all dependencies already in project)

---

## Future Enhancements (Out of Scope for Phase 4)

### Phase 5: CWE Mapping
- LLM-based agent to infer CWE → requirement relationships
- New edge collection: cwe_triggers_requirement
- Hybrid approach: LLM proposes, analyst reviews

### Phase 5: Placeholder Migration
- Update Phase 3A-B trigger rules to use comprehensive FDA/CRA requirements
- Migrate 43 vuln_triggers_requirement edges from placeholders to new requirements

### Phase 6+: Additional Frameworks
- ISO/IEC 27001, PCI DSS, HIPAA Security Rule, ISO 21434, DORA, NIS2

---

## Document Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| v1 | 2026-03-05 | Claude Code | Initial design for Phase 4 (SMALL scope) |

---

**Status:** v1 - Ready for Stage 3 → Stage 4 transition
**Next Step:** Stage 4 (Runtime Modeling) to document execution flows
