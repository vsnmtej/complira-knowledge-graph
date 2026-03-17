# DerivedEdgesAgent Quick Reference

**Implementation Guide for Option 3: Quick Wins - Missing Edges**

---

## At a Glance

**What:** Create `DerivedEdgesAgent` to populate missing edge collections
**Where:** `/src/complira_graph/agents/derived_edges.py`
**Why:** Add ~13,562 edges (ATT&CK → CWE, ATT&CK → NIST 800-53)
**When:** Runs after base data agents (CWE, CAPEC, ATT&CK, OSCAL)
**Time:** 1.5-2 days implementation

---

## Files to Create/Modify

### New Files (1)
```
src/complira_graph/agents/derived_edges.py (350 lines)
```

### Modified Files (3)
```
src/complira_graph/agents/__init__.py (+1 import)
src/complira_graph/utils/keys.py (+1 function)
scripts/seed_reference_database.py (+1 agent)
```

### Test Files (2)
```
tests/unit/agents/test_derived_edges.py
tests/integration/test_derived_edges_agent.py
```

---

## Implementation Checklist

### Step 1: Add Control ID Normalization (30 min)

**File:** `/src/complira_graph/utils/keys.py`

**Add this function:**
```python
def normalize_control_id(control_id: str) -> str:
    """
    Normalize NIST 800-53 control ID to ArangoDB _key format.

    Examples:
        >>> normalize_control_id("AC-2")
        'ac_2'
        >>> normalize_control_id("ac-2.1")
        'ac_2_1'
        >>> normalize_control_id("AC-2(1)")
        'ac_2_1'
    """
    key = control_id.lower()
    key = key.replace('.', '_').replace('-', '_')
    key = key.replace('(', '_').replace(')', '')
    while '__' in key:
        key = key.replace('__', '_')
    return key.strip('_')
```

**Test:**
```python
assert normalize_control_id("AC-2") == "ac_2"
assert normalize_control_id("ac-2.1") == "ac_2_1"
assert normalize_control_id("AC-2(1)") == "ac_2_1"
```

---

### Step 2: Create DerivedEdgesAgent (4-5 hours)

**File:** `/src/complira_graph/agents/derived_edges.py`

**Template Structure:**
```python
"""
Derived Edges Agent - Computes edges from existing graph data.

Collections populated:
- technique_exploits_weakness (ATT&CK → CWE via CAPEC)
- technique_mitigated_by_control (ATT&CK → NIST 800-53 via external mapping)
"""

from typing import Generator, Any
import json
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_http_client
from ..utils.keys import normalize_attack_id, normalize_control_id

logger = structlog.get_logger()


class DerivedEdgesAgent(BaseIngestionAgent):
    """Agent for creating derived edges from existing graph data."""

    ATTACK_CONTROL_MAPPING_URL = (
        "https://raw.githubusercontent.com/center-for-threat-informed-defense/"
        "attack-control-framework-mappings/main/frameworks/attack_10_1/"
        "nist800_53_r5/stix/nist800-53-r5-mappings.json"
    )

    def __init__(self, db):
        super().__init__(db)
        self.client = create_http_client(
            service_name="attack_control_mappings",
            calls_per_period=10,
            period_seconds=60,
            circuit_breaker=False,
            timeout=30.0,
        )

    def fetch_data(self) -> dict:
        """Fetch external ATT&CK → NIST mapping."""
        # TODO: Implement
        pass

    def transform_data(self, raw_data: dict) -> Generator[dict, None, None]:
        """Transform to derived edges."""
        # TODO: Call both derivation methods
        pass

    def _derive_technique_exploits_weakness(self) -> Generator[dict, None, None]:
        """Derive ATT&CK → CWE via graph traversal."""
        # TODO: Implement AQL query
        pass

    def _create_technique_control_mappings(self, stix_data: dict) -> Generator[dict, None, None]:
        """Create ATT&CK → NIST from external mapping."""
        # TODO: Parse STIX data
        pass

    def load_data(self, records, collection_name=None, on_duplicate="update") -> dict:
        """Load edges into both collections."""
        # TODO: Separate edges by collection
        pass

    def _get_primary_collection(self) -> str:
        return 'technique_exploits_weakness'
```

**Key Implementation Points:**

1. **fetch_data():**
   - Fetch STIX JSON from GitHub
   - Return dict with 'attack_control_mapping' key

2. **_derive_technique_exploits_weakness():**
   - AQL query: `FOR technique IN attack_techniques FOR capec IN 1..1 INBOUND technique capec_maps_to_attack FOR cwe IN 1..1 OUTBOUND capec capec_relates_to_cwe RETURN DISTINCT {...}`
   - Yield edges with `_collection='technique_exploits_weakness'`

3. **_create_technique_control_mappings():**
   - Parse STIX objects for type='relationship', relationship_type='mitigates'
   - Extract technique ID from target_ref
   - Extract control ID from source_ref
   - Yield edges with `_collection='technique_mitigated_by_control'`

4. **load_data():**
   - Separate edges into two lists by `_collection` key
   - Call `super().load_data()` twice (once per collection)
   - Return combined stats

**Reference Implementation:** See `/docs/QUICK_WINS_MISSING_EDGES_ARCHITECTURE.md` Section 3.2

---

### Step 3: Update Agent Registry (15 min)

**File:** `/src/complira_graph/agents/__init__.py`

**Add import:**
```python
from complira_graph.agents.derived_edges import DerivedEdgesAgent

__all__ = [
    ...,
    "DerivedEdgesAgent",
]
```

---

### Step 4: Integrate into Seed Script (30 min)

**File:** `/scripts/seed_reference_database.py`

**Add import:**
```python
from complira_graph.agents import (
    ...,
    DerivedEdgesAgent,  # Add this
)
```

**Add to AGENTS list (at the END):**
```python
AGENTS = [
    ...,
    # After all base data is loaded
    ("Derived Edges (ATT&CK→CWE, ATT&CK→Controls)",
     DerivedEdgesAgent,
     "Compute derived edges from existing graph",
     "1-2 min"),
]
```

**IMPORTANT:** Must run AFTER CWEAgent, CAPECAgent, ATTACKAgent, OSCALAgent

---

### Step 5: Write Unit Tests (2-3 hours)

**File:** `/tests/unit/agents/test_derived_edges.py`

**Test Coverage:**
```python
def test_fetch_data_success():
    """Test external mapping fetch."""
    # Mock HTTP client
    # Assert: Returns dict with 'attack_control_mapping'

def test_derive_technique_exploits_weakness():
    """Test graph traversal."""
    # Mock db.aql.execute()
    # Assert: Yields correct edge format

def test_create_technique_control_mappings():
    """Test STIX parsing."""
    # Mock STIX data
    # Assert: Extracts technique and control IDs

def test_load_data_separates_collections():
    """Test edge separation."""
    # Mock super().load_data()
    # Assert: Calls load_data twice
```

---

### Step 6: Write Integration Tests (1-2 hours)

**File:** `/tests/integration/test_derived_edges_agent.py`

**Test Coverage:**
```python
def test_agent_run_e2e(db):
    """Test full agent execution."""
    agent = DerivedEdgesAgent(db)
    result = agent.run()
    assert result['status'] == 'success'
    assert result['total_created'] > 0

def test_edge_counts_match_expected(db):
    """Test edge counts."""
    agent = DerivedEdgesAgent(db)
    agent.run()

    coll = db.collection('technique_exploits_weakness')
    assert 5000 <= coll.count() <= 6000  # ~5,562 expected

    coll = db.collection('technique_mitigated_by_control')
    assert 7000 <= coll.count() <= 9000  # ~8,000 expected

def test_idempotency(db):
    """Test no duplicates on re-run."""
    agent = DerivedEdgesAgent(db)

    agent.run()
    count1 = db.collection('technique_exploits_weakness').count()

    agent.run()
    count2 = db.collection('technique_exploits_weakness').count()

    assert count1 == count2  # No duplicates
```

---

## Verification Queries

### Check Edge Counts

```bash
complira query "RETURN {
    technique_exploits_weakness: LENGTH(technique_exploits_weakness),
    technique_mitigated_by_control: LENGTH(technique_mitigated_by_control)
}"

# Expected output:
# {
#   "technique_exploits_weakness": 5562,
#   "technique_mitigated_by_control": 8000
# }
```

### Sample Derived Edges

```bash
complira query "
FOR edge IN technique_exploits_weakness
    LIMIT 5
    LET technique = DOCUMENT(edge._from)
    LET cwe = DOCUMENT(edge._to)
    RETURN {
        technique: technique.technique_id,
        weakness: cwe.cwe_id,
        via_capec: edge.capec_intermediary
    }
"

# Expected output:
# [
#   {
#     "technique": "T1059.001",
#     "weakness": "CWE-78",
#     "via_capec": "CAPEC-88"
#   },
#   ...
# ]
```

### Verify No Orphaned Edges

```bash
complira query "
FOR edge IN technique_exploits_weakness
    LET from_exists = DOCUMENT(edge._from) != null
    LET to_exists = DOCUMENT(edge._to) != null
    FILTER !from_exists OR !to_exists
    RETURN edge
"

# Expected output: [] (empty - no orphans)
```

---

## Common Pitfalls

### Pitfall 1: Wrong Run Order
**Problem:** DerivedEdgesAgent runs before base data agents
**Symptom:** Zero edges created, AQL query returns no results
**Fix:** Ensure AGENTS list has DerivedEdgesAgent at the END

### Pitfall 2: Missing Key Normalization
**Problem:** Control IDs not normalized (AC-2 vs ac_2)
**Symptom:** Edges have invalid _to references
**Fix:** Use `normalize_control_id()` when creating edges

### Pitfall 3: Duplicate Edges on Re-run
**Problem:** Using `on_duplicate="ignore"` instead of `"update"`
**Symptom:** Edge count doubles on second run
**Fix:** Use `on_duplicate="update"` in load_data()

### Pitfall 4: STIX Parsing Errors
**Problem:** External mapping format changed
**Symptom:** Zero technique_mitigated_by_control edges
**Fix:** Add version check in fetch_data(), validate STIX format

---

## Debugging Tips

### Enable Debug Logging

```python
# In derived_edges.py
logger.setLevel("DEBUG")
```

### Check Intermediate Results

```python
# In _derive_technique_exploits_weakness()
results = list(self.db.aql.execute(query))
self.logger.debug(f"Traversal returned {len(results)} results")
self.logger.debug(f"Sample: {results[:5]}")
```

### Verify External Mapping Fetch

```python
# In fetch_data()
data = response.json()
self.logger.debug(f"STIX objects: {len(data.get('objects', []))}")
self.logger.debug(f"Relationships: {sum(1 for obj in data.get('objects', []) if obj.get('type') == 'relationship')}")
```

---

## Success Criteria

### Before Declaring Complete

- [ ] `complira query "RETURN LENGTH(technique_exploits_weakness)"` returns ~5,562
- [ ] `complira query "RETURN LENGTH(technique_mitigated_by_control)"` returns ~8,000
- [ ] No orphaned edges (query above returns empty)
- [ ] Unit tests pass (coverage > 90%)
- [ ] Integration tests pass
- [ ] Agent runs in < 2 minutes
- [ ] No linting errors (`ruff check`)
- [ ] No type errors (`mypy`)

---

## Quick Commands

```bash
# Run full seed (includes DerivedEdgesAgent)
complira seed

# Run only DerivedEdgesAgent
complira incremental DerivedEdgesAgent

# Check edge counts
complira query "RETURN {
    technique_exploits_weakness: LENGTH(technique_exploits_weakness),
    technique_mitigated_by_control: LENGTH(technique_mitigated_by_control)
}"

# Sample edges
complira query "FOR edge IN technique_exploits_weakness LIMIT 10 RETURN edge"

# Verify no orphans
complira query "FOR edge IN technique_exploits_weakness LET from_exists = DOCUMENT(edge._from) != null LET to_exists = DOCUMENT(edge._to) != null FILTER !from_exists OR !to_exists RETURN edge"

# Run tests
pytest tests/unit/agents/test_derived_edges.py -v
pytest tests/integration/test_derived_edges_agent.py -v

# Code quality checks
ruff check src/complira_graph/agents/derived_edges.py
mypy src/complira_graph/agents/derived_edges.py
```

---

## Resources

- **Full Architecture Plan:** `/docs/QUICK_WINS_MISSING_EDGES_ARCHITECTURE.md`
- **Implementation Summary:** `/docs/DERIVED_EDGES_IMPLEMENTATION_SUMMARY.md`
- **Base Agent Pattern:** `/src/complira_graph/agents/base.py`
- **Example Multi-Edge Agent:** `/src/complira_graph/agents/capec.py`

---

## Time Breakdown

| Task | Estimated Time |
|------|----------------|
| 1. Add control ID normalization | 30 minutes |
| 2. Create DerivedEdgesAgent | 4-5 hours |
| 3. Update agent registry | 15 minutes |
| 4. Integrate into seed script | 30 minutes |
| 5. Write unit tests | 2-3 hours |
| 6. Write integration tests | 1-2 hours |
| **Total** | **9-12 hours** |

**Calendar Time:** 1.5-2 days (with code review, testing, breaks)

---

## Need Help?

**Architecture Questions:** See `/docs/QUICK_WINS_MISSING_EDGES_ARCHITECTURE.md` Section 2 (Architecture Decision)

**Implementation Questions:** See Section 3 (Detailed Design) with full code examples

**Testing Questions:** See Section 6 (Testing Strategy)

**Integration Questions:** See Section 7 (Run Order Dependencies)
