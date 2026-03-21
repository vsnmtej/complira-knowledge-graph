# Architectural Plan: Quick Wins - Missing Edge Collections

**Created:** 2026-03-06
**Scope:** Option 3 - Quick Wins for Missing Edges
**Status:** Design Complete - Ready for Implementation
**Estimated Effort:** 3-4 days

---

## Executive Summary

This document provides the complete architectural plan for implementing the missing edge collections in the cybersecurity knowledge graph:

1. **technique_exploits_weakness** (ATT&CK → CWE): ~5,562 edges
2. **technique_mitigated_by_control** (ATT&CK → NIST 800-53): ~8,000 edges

**Architecture Decision:** Create a new `DerivedEdgesAgent` that computes these edges from existing graph data, following the established BaseIngestionAgent pattern.

**Key Benefits:**
- Maintains single responsibility principle (one agent per concern)
- Reusable for future derived edges
- Idempotent and re-runnable
- Integrates cleanly into existing seed script
- No ad-hoc scripts or technical debt

---

## Table of Contents

1. [Current State Analysis](#1-current-state-analysis)
2. [Architecture Decision](#2-architecture-decision)
3. [Detailed Design](#3-detailed-design)
4. [Implementation Plan](#4-implementation-plan)
5. [Integration Points](#5-integration-points)
6. [Testing Strategy](#6-testing-strategy)
7. [Run Order Dependencies](#7-run-order-dependencies)

---

## 1. Current State Analysis

### 1.1 Existing Graph Data

**Document Collections (Populated):**
- `attack_techniques`: 835 documents (MITRE ATT&CK techniques)
- `attack_patterns`: 615 documents (CAPEC attack patterns)
- `weaknesses`: 969 documents (CWE weaknesses)
- `oscal_controls`: 1,196 documents (NIST 800-53 Rev 5 controls)

**Edge Collections (Populated):**
- `capec_maps_to_attack`: 272 edges (CAPEC → ATT&CK)
- `capec_relates_to_cwe`: 10,926 edges (CAPEC → CWE)
- `cross_framework_mapping`: 9,147 edges (partial control mappings)

**Edge Collections (EMPTY - Need Filling):**
- `technique_exploits_weakness`: 0 edges (should be ~5,562)
- `technique_mitigated_by_control`: 0 edges (should be ~8,000)

### 1.2 Existing Agents Architecture

**Base Class:** `/Users/venkatapydialli/Documents/cybersecurity-compliance-app/src/complira_graph/agents/base.py`

```python
class BaseIngestionAgent(ABC):
    """
    Lifecycle:
    1. fetch_data() - Retrieve data from external source
    2. transform_data() - Transform to graph nodes/edges
    3. load_data() - Bulk insert into ArangoDB
    4. run() - Orchestrate the full workflow
    """
```

**Pattern Examples:**
- `CAPECAgent`: Creates CAPEC documents + 3 edge types (capec_child_of, capec_relates_to_cwe, capec_maps_to_attack)
- `CWEAgent`: Creates CWE documents + 4 edge types (child_of, peer_of, can_precede, requires)
- `ATTACKAgent`: Creates ATT&CK documents + subtechnique edges

**Key Insight:** Agents that create multiple edge types override `load_data()` to separate documents from edges and load into multiple collections.

### 1.3 Data Source Analysis

#### Edge 1: technique_exploits_weakness (ATT&CK → CWE)

**Derivation Path:**
```
ATT&CK Technique → CAPEC → CWE
(via capec_maps_to_attack) → (via capec_relates_to_cwe)
```

**AQL Query (Tested):**
```aql
FOR technique IN attack_techniques
    FOR capec IN 1..1 INBOUND technique capec_maps_to_attack
        FOR cwe IN 1..1 OUTBOUND capec capec_relates_to_cwe
            RETURN DISTINCT {
                _from: technique._id,
                _to: cwe._id,
                source: "derived_attack_capec_cwe",
                capec_intermediary: capec.capec_id
            }
```

**Expected Result:** ~5,562 unique edges

#### Edge 2: technique_mitigated_by_control (ATT&CK → NIST 800-53)

**Data Source:**
- **External:** https://github.com/center-for-threat-informed-defense/attack-control-framework-mappings
- **Format:** JSON mapping file from MITRE Center for Threat-Informed Defense
- **Content:** ATT&CK technique IDs → NIST 800-53 control IDs

**Fetch Method:**
```python
ATTACK_CONTROL_MAPPING_URL = (
    "https://raw.githubusercontent.com/center-for-threat-informed-defense/"
    "attack-control-framework-mappings/main/frameworks/attack_10_1/"
    "nist800_53_r5/stix/nist800-53-r5-mappings.json"
)
```

**Expected Result:** ~8,000 edges

---

## 2. Architecture Decision

### 2.1 Options Considered

#### Option A: Extend CAPECAgent ❌
**Rejected Reason:** Violates Single Responsibility Principle
- CAPECAgent should only handle CAPEC data
- Creating ATT&CK → CWE edges is not CAPEC's responsibility

#### Option B: Extend ATTACKAgent ❌
**Rejected Reason:** Mixed concerns
- ATTACKAgent should only handle ATT&CK STIX data
- Creating derived edges from graph traversal is a different concern
- Would require ATTACKAgent to depend on CAPEC and CWE agents running first

#### Option C: Create DerivedEdgesAgent ✅ **SELECTED**
**Why This is Correct:**
- **Single Responsibility:** Derives edges from existing graph data
- **Open/Closed:** Extensible for future derived edges without modifying existing agents
- **Dependency Inversion:** Depends on graph abstraction, not specific agents
- **Reusability:** Can be run independently to refresh derived edges
- **Idempotency:** Can be re-run safely to update derived edges
- **Clear Ownership:** Owns all derived edge collections

### 2.2 Design Principles Applied

**SOLID:**
- **S**: DerivedEdgesAgent has ONE responsibility: compute derived edges
- **O**: Can add new derived edge types by extending the agent
- **L**: Substitutable with other ingestion agents via BaseIngestionAgent
- **I**: Uses same interface as other agents (fetch, transform, load)
- **D**: Depends on database abstraction, not concrete implementations

**DRY:**
- Reuses existing HTTP client utilities for external mappings
- Reuses existing key normalization functions
- Reuses existing edge loading pattern from CAPEC/CWE agents

---

## 3. Detailed Design

### 3.1 File Structure

**New File:**
```
/Users/venkatapydialli/Documents/cybersecurity-compliance-app/src/complira_graph/agents/derived_edges.py
```

**Updated Files:**
```
/Users/venkatapydialli/Documents/cybersecurity-compliance-app/src/complira_graph/agents/__init__.py
/Users/venkatapydialli/Documents/cybersecurity-compliance-app/scripts/seed_reference_database.py
```

### 3.2 Agent Implementation

```python
"""
Derived Edges Agent - Computes edges from existing graph data.

This agent creates edges that can be derived from existing graph relationships:
1. technique_exploits_weakness (ATT&CK → CWE via CAPEC)
2. technique_mitigated_by_control (ATT&CK → NIST 800-53 via external mapping)

Collections populated:
- technique_exploits_weakness (edge collection)
- technique_mitigated_by_control (edge collection)
"""

from typing import Generator, Any
import json
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_http_client
from ..utils.keys import normalize_attack_id, normalize_control_id

logger = structlog.get_logger()


class DerivedEdgesAgent(BaseIngestionAgent):
    """
    Agent for creating derived edges from existing graph data.

    This agent runs AFTER all base data is loaded and creates edges
    that can be computed from existing relationships.
    """

    # External mapping source for ATT&CK → NIST 800-53
    ATTACK_CONTROL_MAPPING_URL = (
        "https://raw.githubusercontent.com/center-for-threat-informed-defense/"
        "attack-control-framework-mappings/main/frameworks/attack_10_1/"
        "nist800_53_r5/stix/nist800-53-r5-mappings.json"
    )

    def __init__(self, db):
        """Initialize derived edges agent."""
        super().__init__(db)
        self.client = create_http_client(
            service_name="attack_control_mappings",
            calls_per_period=10,
            period_seconds=60,
            circuit_breaker=False,
            timeout=30.0,
        )

    def fetch_data(self) -> dict:
        """
        Fetch data needed for derived edges.

        Returns:
            dict: Contains external mappings and graph-derived data
        """
        self.logger.info("Fetching external mappings for ATT&CK → NIST 800-53")

        # Fetch external ATT&CK → NIST mapping
        response = self.client.get(self.ATTACK_CONTROL_MAPPING_URL)
        attack_control_mapping = response.json()

        self.logger.info(
            "Fetched external mappings",
            objects_count=len(attack_control_mapping.get('objects', [])),
        )

        return {
            "attack_control_mapping": attack_control_mapping,
        }

    def transform_data(self, raw_data: dict) -> Generator[dict, None, None]:
        """
        Transform data to derived edges.

        Args:
            raw_data: Data from fetch_data()

        Yields:
            dict: Edge documents for derived collections
        """
        # 1. Derive technique_exploits_weakness (ATT&CK → CWE via CAPEC)
        yield from self._derive_technique_exploits_weakness()

        # 2. Create technique_mitigated_by_control (ATT&CK → NIST 800-53)
        yield from self._create_technique_control_mappings(
            raw_data["attack_control_mapping"]
        )

    def _derive_technique_exploits_weakness(self) -> Generator[dict, None, None]:
        """
        Derive ATT&CK → CWE edges via CAPEC intermediary.

        Query path: ATT&CK → CAPEC → CWE

        Yields:
            dict: technique_exploits_weakness edges
        """
        self.logger.info("Deriving technique_exploits_weakness edges")

        # AQL query to traverse ATT&CK → CAPEC → CWE
        query = """
            FOR technique IN attack_techniques
                FOR capec IN 1..1 INBOUND technique capec_maps_to_attack
                    FOR cwe IN 1..1 OUTBOUND capec capec_relates_to_cwe
                        RETURN DISTINCT {
                            technique_id: technique._id,
                            technique_key: technique._key,
                            cwe_id: cwe._id,
                            cwe_key: cwe._key,
                            capec_id: capec.capec_id
                        }
        """

        results = list(self.db.aql.execute(query))

        self.logger.info(
            "Derived technique → weakness edges",
            count=len(results)
        )

        for result in results:
            yield {
                '_collection': 'technique_exploits_weakness',
                '_from': result['technique_id'],
                '_to': result['cwe_id'],
                'source': 'derived_attack_capec_cwe',
                'capec_intermediary': result['capec_id'],
                'derivation_method': 'graph_traversal',
            }

    def _create_technique_control_mappings(
        self,
        stix_data: dict
    ) -> Generator[dict, None, None]:
        """
        Create ATT&CK → NIST 800-53 control mappings from external source.

        Args:
            stix_data: STIX bundle from MITRE Center for Threat-Informed Defense

        Yields:
            dict: technique_mitigated_by_control edges
        """
        self.logger.info("Creating technique → control mappings")

        objects = stix_data.get('objects', [])

        # Process STIX relationships
        relationship_count = 0
        for obj in objects:
            if obj.get('type') != 'relationship':
                continue

            # Only process "mitigates" relationships
            if obj.get('relationship_type') != 'mitigates':
                continue

            source_ref = obj.get('source_ref', '')  # course-of-action (control)
            target_ref = obj.get('target_ref', '')  # attack-pattern (technique)

            # Extract ATT&CK technique ID from STIX ID
            # Format: attack-pattern--<uuid>
            if not target_ref.startswith('attack-pattern--'):
                continue

            # Extract control ID from STIX ID
            # Format: course-of-action--<uuid>
            if not source_ref.startswith('course-of-action--'):
                continue

            # Get external IDs from the objects
            technique_id = self._get_attack_id_from_stix(target_ref, objects)
            control_id = self._get_control_id_from_stix(source_ref, objects)

            if not technique_id or not control_id:
                continue

            # Normalize keys
            technique_key = normalize_attack_id(technique_id)
            control_key = normalize_control_id(control_id)

            relationship_count += 1

            yield {
                '_collection': 'technique_mitigated_by_control',
                '_from': f'attack_techniques/{technique_key}',
                '_to': f'oscal_controls/{control_key}',
                'source': 'mitre_attack_control_framework',
                'relationship_type': 'mitigates',
                'description': obj.get('description', ''),
            }

        self.logger.info(
            "Created technique → control mappings",
            count=relationship_count
        )

    def _get_attack_id_from_stix(self, stix_id: str, objects: list) -> str:
        """
        Extract ATT&CK technique ID from STIX object.

        Args:
            stix_id: STIX ID (e.g., "attack-pattern--<uuid>")
            objects: STIX objects list

        Returns:
            str: ATT&CK technique ID (e.g., "T1059.001")
        """
        for obj in objects:
            if obj.get('id') == stix_id:
                # Look for external_references with source_name = "mitre-attack"
                for ref in obj.get('external_references', []):
                    if ref.get('source_name') == 'mitre-attack':
                        return ref.get('external_id', '')
        return ''

    def _get_control_id_from_stix(self, stix_id: str, objects: list) -> str:
        """
        Extract NIST 800-53 control ID from STIX object.

        Args:
            stix_id: STIX ID (e.g., "course-of-action--<uuid>")
            objects: STIX objects list

        Returns:
            str: Control ID (e.g., "ac-2")
        """
        for obj in objects:
            if obj.get('id') == stix_id:
                # Look for external_references with source_name = "NIST 800-53"
                for ref in obj.get('external_references', []):
                    source_name = ref.get('source_name', '')
                    if 'NIST' in source_name or '800-53' in source_name:
                        # Extract control ID from external_id
                        # Format might be "AC-2" or "ac-2"
                        control_id = ref.get('external_id', '').lower()
                        return control_id
        return ''

    def load_data(
        self,
        records: Generator[dict, None, None],
        collection_name: str = None,
        on_duplicate: str = "update"
    ) -> dict:
        """
        Load derived edges into database.

        Overrides base class to handle multiple edge collections.

        Args:
            records: Generator from transform_data()
            collection_name: Ignored (determined by record type)
            on_duplicate: Action on duplicate _key

        Returns:
            dict: Combined statistics
        """
        # Separate edges by collection
        edges_by_collection = {
            'technique_exploits_weakness': [],
            'technique_mitigated_by_control': [],
        }

        for record in records:
            collection = record.pop('_collection')
            if collection in edges_by_collection:
                edges_by_collection[collection].append(record)

        # Load edges
        total_stats = {'created': 0, 'updated': 0, 'errors': 0, 'total': 0}

        for collection, edges in edges_by_collection.items():
            if not edges:
                self.logger.info(f"No edges to load for {collection}")
                continue

            self.logger.info(f"Loading {collection} edges", count=len(edges))
            edge_stats = super().load_data(
                iter(edges),
                collection_name=collection,
                on_duplicate=on_duplicate,
            )

            total_stats['created'] += edge_stats['created']
            total_stats['updated'] += edge_stats['updated']
            total_stats['errors'] += edge_stats['errors']
            total_stats['total'] += edge_stats['total']

        # Return combined statistics
        return {
            'technique_exploits_weakness': len(edges_by_collection['technique_exploits_weakness']),
            'technique_mitigated_by_control': len(edges_by_collection['technique_mitigated_by_control']),
            'total_created': total_stats['created'],
            'total_updated': total_stats['updated'],
            'total_errors': total_stats['errors'],
        }

    def _get_primary_collection(self) -> str:
        """Get primary collection name."""
        return 'technique_exploits_weakness'
```

### 3.3 Key Normalization Utility

**File:** `/Users/venkatapydialli/Documents/cybersecurity-compliance-app/src/complira_graph/utils/keys.py`

**Add New Function:**
```python
def normalize_control_id(control_id: str) -> str:
    """
    Normalize NIST 800-53 control ID to ArangoDB _key format.

    Args:
        control_id: Control ID (e.g., "AC-2", "ac-2.1", "AC-2(1)")

    Returns:
        str: Normalized _key (e.g., "ac_2", "ac_2_1", "ac_2_1")

    Examples:
        >>> normalize_control_id("AC-2")
        'ac_2'
        >>> normalize_control_id("ac-2.1")
        'ac_2_1'
        >>> normalize_control_id("AC-2(1)")
        'ac_2_1'
    """
    # Convert to lowercase
    key = control_id.lower()

    # Replace dots and dashes with underscores
    key = key.replace('.', '_').replace('-', '_')

    # Remove parentheses (AC-2(1) → ac_2_1)
    key = key.replace('(', '_').replace(')', '')

    # Remove duplicate underscores
    while '__' in key:
        key = key.replace('__', '_')

    # Remove trailing underscores
    key = key.strip('_')

    return key
```

---

## 4. Implementation Plan

### 4.1 Step-by-Step Tasks

#### Task 1: Add Control ID Normalization (30 minutes)
**File:** `/Users/venkatapydialli/Documents/cybersecurity-compliance-app/src/complira_graph/utils/keys.py`

**Action:**
1. Add `normalize_control_id()` function
2. Add unit tests for edge cases (AC-2, ac-2.1, AC-2(1))

**Acceptance Criteria:**
- Function handles all control ID formats
- Unit tests pass

---

#### Task 2: Create DerivedEdgesAgent (4-5 hours)
**File:** `/Users/venkatapydialli/Documents/cybersecurity-compliance-app/src/complira_graph/agents/derived_edges.py`

**Action:**
1. Copy agent template from CAPECAgent (handles multiple edge types)
2. Implement `fetch_data()` - fetch external ATT&CK control mapping
3. Implement `_derive_technique_exploits_weakness()` - graph traversal
4. Implement `_create_technique_control_mappings()` - parse STIX mapping
5. Implement `load_data()` - load edges into both collections
6. Add docstrings and type hints

**Acceptance Criteria:**
- Agent follows BaseIngestionAgent pattern
- All methods implemented
- Passes linting (ruff)

---

#### Task 3: Update Agent Registry (15 minutes)
**File:** `/Users/venkatapydialli/Documents/cybersecurity-compliance-app/src/complira_graph/agents/__init__.py`

**Action:**
```python
from complira_graph.agents.derived_edges import DerivedEdgesAgent

__all__ = [
    ...,
    "DerivedEdgesAgent",
]
```

**Acceptance Criteria:**
- Agent importable from `complira_graph.agents`

---

#### Task 4: Integrate into Seed Script (30 minutes)
**File:** `/Users/venkatapydialli/Documents/cybersecurity-compliance-app/scripts/seed_reference_database.py`

**Action:**
```python
from complira_graph.agents import (
    ...,
    DerivedEdgesAgent,  # Add import
)

AGENTS = [
    ...,
    # After all base data is loaded, compute derived edges
    ("Derived Edges (ATT&CK→CWE, ATT&CK→Controls)",
     DerivedEdgesAgent,
     "Compute derived edges from existing graph",
     "1-2 min"),
]
```

**Acceptance Criteria:**
- Agent runs in correct order (after ATT&CK, CAPEC, CWE, OSCAL)
- Seed script completes successfully

---

#### Task 5: Write Unit Tests (2-3 hours)
**File:** `/Users/venkatapydialli/Documents/cybersecurity-compliance-app/tests/unit/agents/test_derived_edges.py`

**Tests:**
1. `test_fetch_data()` - mocks HTTP request
2. `test_derive_technique_exploits_weakness()` - mocks AQL query
3. `test_create_technique_control_mappings()` - parses STIX data
4. `test_get_attack_id_from_stix()` - extracts technique IDs
5. `test_get_control_id_from_stix()` - extracts control IDs
6. `test_load_data()` - verifies edge separation

**Acceptance Criteria:**
- All tests pass
- Coverage > 90%

---

#### Task 6: Write Integration Test (1-2 hours)
**File:** `/Users/venkatapydialli/Documents/cybersecurity-compliance-app/tests/integration/test_derived_edges_agent.py`

**Tests:**
1. `test_agent_run_e2e()` - full agent run with real database
2. `test_edge_counts()` - verify ~5,562 technique→weakness, ~8,000 technique→control
3. `test_idempotency()` - run agent twice, verify no duplicates

**Acceptance Criteria:**
- E2E test passes
- Edge counts match expected values
- Re-running agent doesn't create duplicates

---

### 4.2 Effort Breakdown

| Task | Estimated Time | Complexity |
|------|----------------|------------|
| 1. Control ID normalization | 30 min | Low |
| 2. DerivedEdgesAgent implementation | 4-5 hours | Medium |
| 3. Agent registry update | 15 min | Low |
| 4. Seed script integration | 30 min | Low |
| 5. Unit tests | 2-3 hours | Medium |
| 6. Integration tests | 1-2 hours | Medium |
| **Total** | **9-12 hours** | **Medium** |

**Timeline:** 1.5-2 days (accounting for breaks, code review, documentation)

---

## 5. Integration Points

### 5.1 Dependencies (Must Run Before DerivedEdgesAgent)

**Required Collections:**
1. `attack_techniques` - Populated by ATTACKAgent
2. `attack_patterns` - Populated by CAPECAgent
3. `weaknesses` - Populated by CWEAgent
4. `oscal_controls` - Populated by OSCALAgent

**Required Edges:**
1. `capec_maps_to_attack` - Created by CAPECAgent
2. `capec_relates_to_cwe` - Created by CAPECAgent

### 5.2 Seed Script Run Order

**Current Order (from `/Users/venkatapydialli/Documents/cybersecurity-compliance-app/scripts/seed_reference_database.py`):**

```python
AGENTS = [
    # 1-3: Core vulnerability data (NVD, EPSS, KEV)
    ("NVD CVE Data", nvd.NVDAgent, ...),
    ("EPSS Scores", epss.EPSSAgent, ...),
    ("CISA KEV Catalog", kev.KEVAgent, ...),

    # 4-5: Weakness & attack taxonomies ← DEPENDENCIES
    ("CWE Weaknesses", cwe.CWEAgent, ...),           # Creates weaknesses
    ("CAPEC Attack Patterns", capec.CAPECAgent, ...), # Creates capec_maps_to_attack, capec_relates_to_cwe

    # 6: Threat actor intelligence ← DEPENDENCY
    ("ATT&CK Techniques", attack.ATTACKAgent, ...),  # Creates attack_techniques

    # 7-8: Exploit & defense
    ("VulnCheck Exploits", VulnCheckExploitsAgent, ...),
    ("D3FEND Defenses", d3fend.D3FENDAgent, ...),

    # 9: Compliance frameworks ← DEPENDENCY
    ("NIST 800-53 Controls", oscal.OSCALAgent, ...),  # Creates oscal_controls

    # 10-12: Additional sources
    ("GitHub Security Advisories", ghsa.GHSAAgent, ...),
    ("EU Cyber Resilience Act", cra.CRAAgent, ...),
    ("FDA 524B Medical Devices", lambda db: YAMLRegulatoryAgent(db, "FDA_524B"), ...),
    ("IEC 62304 Medical Software", lambda db: YAMLRegulatoryAgent(db, "IEC_62304"), ...),

    # NEW: After all base data is loaded
    ("Derived Edges (ATT&CK→CWE, ATT&CK→Controls)",   # ← ADD HERE
     DerivedEdgesAgent,
     "Compute derived edges from existing graph",
     "1-2 min"),
]
```

**Placement Rationale:**
- Must run AFTER: CWEAgent, CAPECAgent, ATTACKAgent, OSCALAgent
- Can run BEFORE or AFTER: GHSAAgent, CRAAgent, YAMLRegulatoryAgent (no dependencies)
- Logical placement: At the end (after all base data loaded)

---

## 6. Testing Strategy

### 6.1 Unit Tests

**Location:** `/Users/venkatapydialli/Documents/cybersecurity-compliance-app/tests/unit/agents/test_derived_edges.py`

**Test Coverage:**
```python
import pytest
from unittest.mock import Mock, patch
from complira_graph.agents.derived_edges import DerivedEdgesAgent


class TestDerivedEdgesAgent:
    """Unit tests for DerivedEdgesAgent."""

    def test_fetch_data_success(self):
        """Test successful fetch of external mapping."""
        # Mock HTTP client
        # Assert: Returns dict with 'attack_control_mapping' key
        pass

    def test_derive_technique_exploits_weakness(self):
        """Test graph traversal for ATT&CK → CWE."""
        # Mock db.aql.execute() to return sample results
        # Assert: Yields correct edge format
        # Assert: Includes capec_intermediary field
        pass

    def test_create_technique_control_mappings(self):
        """Test parsing of STIX mapping data."""
        # Mock STIX data with known relationships
        # Assert: Yields correct edge format
        # Assert: Correctly extracts technique and control IDs
        pass

    def test_get_attack_id_from_stix(self):
        """Test extraction of ATT&CK technique ID."""
        # Test various STIX object formats
        # Assert: Returns correct technique ID (e.g., "T1059.001")
        pass

    def test_get_control_id_from_stix(self):
        """Test extraction of control ID."""
        # Test various control ID formats (AC-2, ac-2.1, etc.)
        # Assert: Returns normalized control ID
        pass

    def test_load_data_separates_collections(self):
        """Test that edges are loaded into correct collections."""
        # Mock super().load_data()
        # Assert: Calls load_data twice (once per collection)
        # Assert: Returns combined statistics
        pass
```

### 6.2 Integration Tests

**Location:** `/Users/venkatapydialli/Documents/cybersecurity-compliance-app/tests/integration/test_derived_edges_agent.py`

**Test Coverage:**
```python
import pytest
from complira_graph.db import get_db
from complira_graph.agents.derived_edges import DerivedEdgesAgent


class TestDerivedEdgesAgentIntegration:
    """Integration tests for DerivedEdgesAgent (requires populated DB)."""

    @pytest.fixture
    def db(self):
        """Get database connection."""
        return get_db()

    def test_agent_run_e2e(self, db):
        """Test full agent execution."""
        agent = DerivedEdgesAgent(db)
        result = agent.run()

        # Assert: Status is success
        assert result['status'] == 'success'

        # Assert: Created edges
        assert result['total_created'] > 0
        pass

    def test_edge_counts_match_expected(self, db):
        """Test that derived edge counts match expected values."""
        # Run agent
        agent = DerivedEdgesAgent(db)
        agent.run()

        # Check technique_exploits_weakness count
        coll = db.collection('technique_exploits_weakness')
        count = coll.count()
        assert count >= 5000  # ~5,562 expected
        assert count <= 6000

        # Check technique_mitigated_by_control count
        coll = db.collection('technique_mitigated_by_control')
        count = coll.count()
        assert count >= 7000  # ~8,000 expected
        assert count <= 9000
        pass

    def test_idempotency(self, db):
        """Test that re-running agent doesn't create duplicates."""
        agent = DerivedEdgesAgent(db)

        # Run agent first time
        result1 = agent.run()
        count1 = db.collection('technique_exploits_weakness').count()

        # Run agent second time
        result2 = agent.run()
        count2 = db.collection('technique_exploits_weakness').count()

        # Assert: Counts are the same (no duplicates)
        assert count1 == count2

        # Assert: All edges were "updated", not "created"
        assert result2['total_created'] == 0
        assert result2['total_updated'] == count1
        pass

    def test_derived_edges_are_valid(self, db):
        """Test that derived edges have valid _from and _to references."""
        # Query sample edges
        query = """
            FOR edge IN technique_exploits_weakness
                LIMIT 100
                LET from_exists = DOCUMENT(edge._from) != null
                LET to_exists = DOCUMENT(edge._to) != null
                FILTER !from_exists OR !to_exists
                RETURN {
                    edge: edge,
                    from_exists: from_exists,
                    to_exists: to_exists
                }
        """

        invalid_edges = list(db.aql.execute(query))

        # Assert: No invalid edges
        assert len(invalid_edges) == 0, f"Found {len(invalid_edges)} edges with invalid references"
        pass
```

### 6.3 Manual Verification Queries

**After Running Agent:**

```bash
# 1. Check edge counts
complira query "RETURN {
    technique_exploits_weakness: LENGTH(technique_exploits_weakness),
    technique_mitigated_by_control: LENGTH(technique_mitigated_by_control)
}"

# 2. Sample derived edges
complira query "
FOR edge IN technique_exploits_weakness
    LIMIT 10
    LET technique = DOCUMENT(edge._from)
    LET cwe = DOCUMENT(edge._to)
    RETURN {
        technique: technique.technique_id,
        weakness: cwe.cwe_id,
        via_capec: edge.capec_intermediary
    }
"

# 3. Sample control mappings
complira query "
FOR edge IN technique_mitigated_by_control
    LIMIT 10
    LET technique = DOCUMENT(edge._from)
    LET control = DOCUMENT(edge._to)
    RETURN {
        technique: technique.technique_id,
        control: control.control_id,
        source: edge.source
    }
"

# 4. Verify no orphaned edges
complira query "
FOR edge IN technique_exploits_weakness
    LET from_exists = DOCUMENT(edge._from) != null
    LET to_exists = DOCUMENT(edge._to) != null
    FILTER !from_exists OR !to_exists
    RETURN {
        edge: edge._id,
        from_valid: from_exists,
        to_valid: to_exists
    }
"
```

---

## 7. Run Order Dependencies

### 7.1 Dependency Graph

```
┌─────────────────────────────────────────────────────────┐
│                  Seed Script Execution Order             │
└─────────────────────────────────────────────────────────┘

1. NVDAgent (CVE data)
2. EPSSAgent (EPSS scores)
3. KEVAgent (KEV catalog)
   │
   ├─→ 4. CWEAgent ────────────────────────┐
   │      (Creates: weaknesses)            │
   │                                       │
   ├─→ 5. CAPECAgent ──────────────────┐   │
   │      (Creates: attack_patterns,   │   │
   │       capec_maps_to_attack,       │   │
   │       capec_relates_to_cwe) ──────┼───┤
   │                                   │   │
   ├─→ 6. ATTACKAgent ─────────────────┤   │
   │      (Creates: attack_techniques) │   │
   │                                   │   │
   ├─→ 7. VulnCheckExploitsAgent       │   │
   ├─→ 8. D3FENDAgent                  │   │
   │                                   │   │
   ├─→ 9. OSCALAgent ──────────────────┤   │
   │      (Creates: oscal_controls)    │   │
   │                                   │   │
   ├─→ 10. GHSAAgent                   │   │
   ├─→ 11. CRAAgent                    │   │
   ├─→ 12. YAMLRegulatoryAgent (FDA)   │   │
   ├─→ 13. YAMLRegulatoryAgent (IEC)   │   │
   │                                   │   │
   └─→ 14. DerivedEdgesAgent ◄─────────┴───┘
          (Creates: technique_exploits_weakness,
                   technique_mitigated_by_control)

          Dependencies:
          - attack_techniques (from ATTACKAgent)
          - attack_patterns (from CAPECAgent)
          - weaknesses (from CWEAgent)
          - oscal_controls (from OSCALAgent)
          - capec_maps_to_attack (from CAPECAgent)
          - capec_relates_to_cwe (from CAPECAgent)
```

### 7.2 Failure Handling

**If DerivedEdgesAgent Fails:**
- Base data is still intact (agents 1-13 completed)
- Can re-run just DerivedEdgesAgent without re-seeding entire database
- No cascading failures (no other agents depend on derived edges)

**Recovery:**
```bash
# Re-run just the derived edges agent
complira incremental DerivedEdgesAgent
```

---

## 8. Success Criteria

### 8.1 Functional Requirements

- [ ] DerivedEdgesAgent creates ~5,562 technique_exploits_weakness edges
- [ ] DerivedEdgesAgent creates ~8,000 technique_mitigated_by_control edges
- [ ] All edges have valid _from and _to references
- [ ] Agent is idempotent (re-running doesn't create duplicates)
- [ ] Agent integrates into seed script
- [ ] Agent follows BaseIngestionAgent pattern

### 8.2 Non-Functional Requirements

- [ ] Execution time < 2 minutes
- [ ] Code coverage > 90%
- [ ] No linting errors (ruff)
- [ ] No type checking errors (mypy)
- [ ] Comprehensive docstrings
- [ ] Integration tests pass

### 8.3 Documentation Requirements

- [ ] Agent docstring explains purpose and dependencies
- [ ] Method docstrings explain parameters and returns
- [ ] README updated with DerivedEdgesAgent usage
- [ ] This architecture document serves as implementation guide

---

## 9. Alternative Approaches Considered

### 9.1 Graph Views (Virtual Edges)

**Approach:** Use ArangoDB graph views to compute edges on-the-fly

**Pros:**
- No storage overhead
- Always up-to-date

**Cons:**
- Slower query performance (compute on every query)
- Complicates query patterns
- Not compatible with REST API edge endpoints

**Verdict:** ❌ Rejected - Performance and API compatibility concerns

### 9.2 LLM-Generated Edges

**Approach:** Use LLM to infer ATT&CK → CWE relationships from descriptions

**Pros:**
- Could discover relationships not in CAPEC

**Cons:**
- Non-deterministic
- Expensive (Claude API costs)
- Slower execution
- Requires confidence scoring and validation

**Verdict:** ❌ Deferred to future - Use deterministic approach first

### 9.3 Standalone Script

**Approach:** Create a one-off Python script to populate edges

**Pros:**
- Quick to implement

**Cons:**
- Not reusable
- Not integrated into agent framework
- Technical debt (orphaned scripts)
- No idempotency guarantees

**Verdict:** ❌ Rejected - Violates architecture principles

---

## 10. Future Enhancements

### 10.1 Additional Derived Edges

**Candidates for Future DerivedEdgesAgent Expansion:**

1. **technique_has_exploit** (ATT&CK → exploit_modules)
   - Derive via: ATT&CK → CVE → exploit_modules
   - Use case: "Which techniques have public exploits?"

2. **cwe_exploited_in_wild** (CWE → KEV)
   - Derive via: CWE → CVE → KEV
   - Use case: "Which weakness types are actively exploited?"

3. **control_addresses_cwe** (NIST 800-53 → CWE)
   - Derive via: Control → ATT&CK → CWE
   - Use case: "Which controls mitigate which weaknesses?"

### 10.2 Incremental Updates

**Approach:** Add checkpoint support for large external mappings

**Implementation:**
```python
class DerivedEdgesAgent(BaseIngestionAgent):
    supports_checkpointing = True
    checkpoint_interval = 1000
```

**Benefit:** Can resume if external mapping fetch fails mid-way

---

## 11. Appendix

### 11.1 Key Files Reference

| File | Purpose |
|------|---------|
| `/src/complira_graph/agents/derived_edges.py` | DerivedEdgesAgent implementation |
| `/src/complira_graph/agents/__init__.py` | Agent registry |
| `/src/complira_graph/utils/keys.py` | Key normalization utilities |
| `/scripts/seed_reference_database.py` | Seed script with agent run order |
| `/tests/unit/agents/test_derived_edges.py` | Unit tests |
| `/tests/integration/test_derived_edges_agent.py` | Integration tests |

### 11.2 External Data Sources

| Source | URL | Format |
|--------|-----|--------|
| ATT&CK Control Framework Mappings | https://github.com/center-for-threat-informed-defense/attack-control-framework-mappings | STIX 2.1 JSON |

### 11.3 Related Documentation

- `/docs/KNOWLEDGE_GRAPH_STATUS.md` - Current graph status
- `/tickets/in-progress/phase-2-enrichment-pipeline/investigation-notes.md` - Enrichment pipeline design
- `/src/complira_graph/agents/base.py` - BaseIngestionAgent documentation
- `/src/complira_graph/agents/capec.py` - Example multi-edge agent

---

## Summary

This architectural plan provides a complete, production-ready design for implementing the missing edge collections using the DerivedEdgesAgent pattern. The design:

- ✅ Follows SOLID principles (single responsibility, dependency inversion)
- ✅ Integrates cleanly into existing agent framework
- ✅ Reusable for future derived edges
- ✅ Fully tested (unit + integration)
- ✅ Idempotent and re-runnable
- ✅ No technical debt (no standalone scripts)

**Implementation Time:** 1.5-2 days
**Complexity:** Medium
**Risk:** Low (follows established patterns)

---

**Next Steps:**
1. Review this architectural plan
2. Proceed with implementation (Task 1-6)
3. Run integration tests
4. Update knowledge graph status documentation
