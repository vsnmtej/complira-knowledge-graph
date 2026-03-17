# Phase 3A-B: RegulatoryTriggerService - Proposed Design

**Date:** 2026-03-05
**Stage:** 3 (Design Basis)
**Status:** v1 Design Specification

---

## Design Overview

Phase 3A-B implements **RegulatoryTriggerService** to automatically generate `vuln_triggers_requirement` edges based on VulnCheck exploit intelligence, plus a **POST /v1/enrich** API endpoint to merge Phase 2 (NVD) and Phase 3A (VulnCheck) enrichment data.

**Core Components:**
1. **RegulatoryTriggerService** - Service to generate regulatory trigger edges
2. **TriggerRuleEngine** - 4 hardcoded trigger rules (KEV, CVSS, ransomware, exploit chain)
3. **POST /v1/enrich API** - CVE enrichment endpoint with regulatory triggers
4. **Placeholder Requirements Setup** - 5 placeholder regulatory requirements for testing

**Design Principles:**
- **Idempotent** - Multiple runs do not create duplicate edges
- **Incremental** - Process only new/updated CVEs using checkpoints
- **Performance** - Batch processing with AQL queries (< 10s per 1,000 CVEs)
- **Scalable** - Support 100,000+ CVEs
- **Auditable** - Full provenance in edge metadata

---

## 1. System Architecture

### 1.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                   RegulatoryTriggerService                  │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │              TriggerRuleEngine                        │ │
│  │                                                       │ │
│  │  • Rule 1: KEV Entry → 24h urgency                   │ │
│  │  • Rule 2: CVSS 9.0+ → high urgency                  │ │
│  │  • Rule 3: Ransomware → critical urgency             │ │
│  │  • Rule 4: Exploit Chain → critical urgency          │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │          EdgeGenerationService                        │ │
│  │                                                       │ │
│  │  • Check existing edges (idempotency)                │ │
│  │  • Generate edge metadata                            │ │
│  │  • Batch insert with AQL                             │ │
│  │  • Checkpoint tracking                               │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────────────┐
        │          ArangoDB Collections               │
        │                                             │
        │  • vulnerabilities (Phase 2)                │
        │  • vulncheck_kev_entries (Phase 3A)         │
        │  • exploit_intelligence (Phase 3A)          │
        │  • ransomware_families (Phase 3A)           │
        │  • exploit_chains (Phase 3A)                │
        │  • regulatory_requirements (placeholder)    │
        │  • vuln_triggers_requirement (edges)        │
        │  • agent_checkpoints (progress tracking)    │
        └─────────────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────────────┐
        │         POST /v1/enrich Endpoint            │
        │                                             │
        │  1. Query vulnerabilities (Phase 2 NVD)     │
        │  2. Query vulncheck_kev_entries (Phase 3A)  │
        │  3. Query exploit_intelligence (Phase 3A)   │
        │  4. Query vuln_triggers_requirement edges   │
        │  5. Merge + return unified response         │
        └─────────────────────────────────────────────┘
```

---

## 2. RegulatoryTriggerService Design

### 2.1 Service Interface

**File:** `src/complira_graph/services/regulatory_trigger_service.py`

**Class:** `RegulatoryTriggerService`

**Methods:**

```python
class RegulatoryTriggerService:
    """
    Auto-generate vuln_triggers_requirement edges based on exploit intelligence.

    Features:
    - 4 trigger rules (KEV, CVSS, ransomware, exploit chain)
    - Idempotent edge creation (no duplicates)
    - Incremental processing with checkpoints
    - Batch processing for performance
    """

    def __init__(self, db: StandardDatabase):
        """Initialize service with database connection."""
        self.db = db
        self.logger = structlog.get_logger()
        self.checkpoint_service = CheckpointService(db)

    def run(self, force_full_scan: bool = False) -> Dict[str, Any]:
        """
        Run all trigger rules and generate edges.

        Args:
            force_full_scan: If True, ignore checkpoints and process all CVEs

        Returns:
            {
                "edges_created": int,
                "edges_skipped": int,  # Already exist
                "rules_executed": List[str],
                "execution_time_seconds": float,
                "checkpoint_updated": bool
            }
        """

    def run_rule(self, rule_name: str) -> int:
        """
        Run a single trigger rule.

        Args:
            rule_name: One of ["kev_entry", "cvss_critical", "ransomware", "exploit_chain"]

        Returns:
            Number of edges created
        """
```

---

### 2.2 Trigger Rules Implementation

**File:** `src/complira_graph/services/trigger_rules.py`

**Module:** Collection of 4 trigger rule implementations

#### Rule 1: KEV Entry (24h urgency)

```python
def trigger_rule_kev_entry(db: StandardDatabase, checkpoint_date: Optional[str] = None) -> int:
    """
    Trigger Rule 1: KEV Entry → 24h urgency (FDA 524B, CRA)

    For each CVE in vulncheck_kev_entries:
        Create edge: vulnerabilities/{cve_id} → regulatory_requirements/FDA_524B_KEV_RESPONSE

    Args:
        db: ArangoDB database connection
        checkpoint_date: Process only entries added after this date (ISO 8601)

    Returns:
        Number of edges created
    """
    query = """
    FOR kev IN vulncheck_kev_entries
        // Checkpoint filter (incremental processing)
        FILTER @checkpoint_date == null OR kev.date_added > @checkpoint_date

        // Check if vulnerability exists
        LET vuln_key = CONCAT('vulnerabilities/', kev.cve_id)
        LET vuln_exists = DOCUMENT(vuln_key) != null
        FILTER vuln_exists

        // Check if requirement exists
        LET req_key = 'regulatory_requirements/FDA_524B_KEV_RESPONSE'
        LET req_exists = DOCUMENT(req_key) != null
        FILTER req_exists

        // Check if edge already exists (idempotency)
        LET edge_exists = LENGTH(
            FOR edge IN vuln_triggers_requirement
                FILTER edge._from == vuln_key AND edge._to == req_key
                LIMIT 1
                RETURN edge
        ) > 0
        FILTER !edge_exists

        // Insert edge with metadata
        INSERT {
            _from: vuln_key,
            _to: req_key,
            trigger_rule: 'kev_entry',
            urgency: '24h',
            confidence: 1.0,
            evidence: {
                source: 'vulncheck_kev',
                date_added: kev.date_added,
                vulncheck_first: kev.vulncheck_first,
                description: kev.short_description
            },
            trigger_timestamp: DATE_ISO8601(DATE_NOW()),
            trigger_source: 'regulatory_trigger_service_v1'
        } INTO vuln_triggers_requirement

        RETURN NEW
    """

    bind_vars = {"checkpoint_date": checkpoint_date}
    cursor = db.aql.execute(query, bind_vars=bind_vars)
    results = list(cursor)

    return len(results)
```

**Expected Edges:** 4,609 (one per KEV entry)

---

#### Rule 2: CVSS 9.0+ (high urgency)

```python
def trigger_rule_cvss_critical(db: StandardDatabase) -> int:
    """
    Trigger Rule 2: CVSS 9.0+ → high urgency

    For each CVE with cvss_v3_score >= 9.0:
        Create edge: vulnerabilities/{cve_id} → regulatory_requirements/FDA_524B_CVSS_HIGH

    Returns:
        Number of edges created
    """
    query = """
    FOR vuln IN vulnerabilities
        // CVSS filter (9.0+)
        LET cvss_score = vuln.cvss_v31.baseScore OR vuln.cvss_v3.baseScore
        FILTER cvss_score >= 9.0

        // Check if requirement exists
        LET req_key = 'regulatory_requirements/FDA_524B_CVSS_HIGH'
        LET req_exists = DOCUMENT(req_key) != null
        FILTER req_exists

        // Check if edge already exists (idempotency)
        LET edge_exists = LENGTH(
            FOR edge IN vuln_triggers_requirement
                FILTER edge._from == vuln._id AND edge._to == req_key
                LIMIT 1
                RETURN edge
        ) > 0
        FILTER !edge_exists

        // Insert edge with metadata
        INSERT {
            _from: vuln._id,
            _to: req_key,
            trigger_rule: 'cvss_critical',
            urgency: 'high',
            confidence: 0.95,
            evidence: {
                cvss_v3_score: cvss_score,
                cvss_vector: vuln.cvss_v31.vectorString OR vuln.cvss_v3.vectorString
            },
            trigger_timestamp: DATE_ISO8601(DATE_NOW()),
            trigger_source: 'regulatory_trigger_service_v1'
        } INTO vuln_triggers_requirement

        RETURN NEW
    """

    cursor = db.aql.execute(query)
    results = list(cursor)

    return len(results)
```

**Expected Edges:** ~10,000-20,000 (depends on Phase 2 vulnerability data)

---

#### Rule 3: Ransomware Exploitation (critical urgency)

```python
def trigger_rule_ransomware_exploitation(db: StandardDatabase) -> int:
    """
    Trigger Rule 3: Ransomware Exploitation → critical urgency

    For each CVE exploited by ransomware:
        Create edge: vulnerabilities/{cve_id} → regulatory_requirements/CRA_RANSOMWARE_EXPLOITATION

    Returns:
        Number of edges created
    """
    query = """
    FOR edge IN exploited_by_ransomware
        // Get ransomware family details
        LET ransomware = DOCUMENT(edge._to)

        // Check if requirement exists
        LET req_key = 'regulatory_requirements/CRA_RANSOMWARE_EXPLOITATION'
        LET req_exists = DOCUMENT(req_key) != null
        FILTER req_exists

        // Check if trigger edge already exists (idempotency)
        LET trigger_edge_exists = LENGTH(
            FOR trigger_edge IN vuln_triggers_requirement
                FILTER trigger_edge._from == edge._from AND trigger_edge._to == req_key
                LIMIT 1
                RETURN trigger_edge
        ) > 0
        FILTER !trigger_edge_exists

        // Insert edge with metadata
        INSERT {
            _from: edge._from,
            _to: req_key,
            trigger_rule: 'ransomware_exploitation',
            urgency: 'critical',
            confidence: 0.98,
            evidence: {
                ransomware_family: ransomware.name,
                ransomware_first_seen: ransomware.first_seen,
                source: 'vulncheck'
            },
            trigger_timestamp: DATE_ISO8601(DATE_NOW()),
            trigger_source: 'regulatory_trigger_service_v1'
        } INTO vuln_triggers_requirement

        RETURN NEW
    """

    cursor = db.aql.execute(query)
    results = list(cursor)

    return len(results)
```

**Expected Edges:** 0 (requires paid VulnCheck tier)

---

#### Rule 4: Exploit Chain (critical urgency)

```python
def trigger_rule_exploit_chain(db: StandardDatabase) -> int:
    """
    Trigger Rule 4: Exploit Chain → critical urgency

    For each CVE in exploit chains:
        Create edge: vulnerabilities/{cve_id} → regulatory_requirements/CRA_EXPLOIT_CHAIN

    Returns:
        Number of edges created
    """
    query = """
    FOR edge IN chain_includes_vuln
        // Get exploit chain details
        LET chain = DOCUMENT(edge._from)

        // Check if requirement exists
        LET req_key = 'regulatory_requirements/CRA_EXPLOIT_CHAIN'
        LET req_exists = DOCUMENT(req_key) != null
        FILTER req_exists

        // Check if trigger edge already exists (idempotency)
        LET trigger_edge_exists = LENGTH(
            FOR trigger_edge IN vuln_triggers_requirement
                FILTER trigger_edge._from == edge._to AND trigger_edge._to == req_key
                LIMIT 1
                RETURN trigger_edge
        ) > 0
        FILTER !trigger_edge_exists

        // Insert edge with metadata
        INSERT {
            _from: edge._to,  // Vulnerability
            _to: req_key,
            trigger_rule: 'exploit_chain',
            urgency: 'critical',
            confidence: 0.95,
            evidence: {
                chain_name: chain.name,
                chain_description: chain.description,
                chain_position: edge.position
            },
            trigger_timestamp: DATE_ISO8601(DATE_NOW()),
            trigger_source: 'regulatory_trigger_service_v1'
        } INTO vuln_triggers_requirement

        RETURN NEW
    """

    cursor = db.aql.execute(query)
    results = list(cursor)

    return len(results)
```

**Expected Edges:** 0 (requires paid VulnCheck tier)

---

### 2.3 Checkpoint Service

**File:** `src/complira_graph/services/checkpoint_service.py`

**Purpose:** Track last processed timestamp for incremental processing

```python
class CheckpointService:
    """
    Manage checkpoints for incremental trigger rule execution.

    Checkpoints stored in agent_checkpoints collection:
    {
        "_key": "regulatory_trigger_service_kev_entry",
        "agent_name": "regulatory_trigger_service",
        "rule_name": "kev_entry",
        "last_processed_timestamp": "2026-03-05T12:00:00Z",
        "last_processed_count": 4609,
        "updated_at": "2026-03-05T12:05:00Z"
    }
    """

    def get_checkpoint(self, rule_name: str) -> Optional[str]:
        """Get last processed timestamp for a rule."""

    def update_checkpoint(self, rule_name: str, timestamp: str, count: int) -> None:
        """Update checkpoint after successful rule execution."""
```

---

## 3. POST /v1/enrich API Design

### 3.1 Endpoint Specification

**File:** `src/complira_graph/api/enrich.py`

**Endpoint:** `POST /v1/enrich`

**Request:**
```json
{
  "cve_id": "CVE-2024-1234"
}
```

**Response (200 OK):**
```json
{
  "cve_id": "CVE-2024-1234",
  "nvd_data": {
    "published": "2024-03-05T14:15:00.000Z",
    "last_modified": "2024-03-05T14:15:00.000Z",
    "cvss_v31": {
      "baseScore": 9.8,
      "baseSeverity": "CRITICAL",
      "vectorString": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
    },
    "description": "Remote code execution vulnerability...",
    "references": ["https://..."]
  },
  "exploit_intelligence": {
    "in_kev": true,
    "kev_date_added": "2024-03-05",
    "exploit_maturity": "weaponized",
    "ransomware_families": [
      {
        "name": "LockBit",
        "first_seen": "2023-01-15"
      }
    ],
    "exploit_chains": [
      {
        "name": "ProxyShell",
        "position": 1,
        "description": "Exchange Server exploit chain"
      }
    ],
    "botnet_campaigns": []
  },
  "regulatory_triggers": [
    {
      "framework": "FDA 524B",
      "requirement_id": "KEV_RESPONSE",
      "requirement_title": "Known Exploited Vulnerability Response",
      "urgency": "24h",
      "trigger_rule": "kev_entry",
      "confidence": 1.0,
      "evidence": {
        "source": "vulncheck_kev",
        "date_added": "2024-03-05"
      },
      "trigger_timestamp": "2026-03-05T12:00:00Z"
    },
    {
      "framework": "FDA 524B",
      "requirement_id": "CVSS_HIGH_SEVERITY",
      "requirement_title": "CVSS 9.0+ High Severity Vulnerability",
      "urgency": "high",
      "trigger_rule": "cvss_critical",
      "confidence": 0.95,
      "evidence": {
        "cvss_v3_score": 9.8
      },
      "trigger_timestamp": "2026-03-05T12:00:00Z"
    },
    {
      "framework": "CRA",
      "requirement_id": "RANSOMWARE_EXPLOITATION",
      "requirement_title": "Ransomware Exploitation Detection",
      "urgency": "critical",
      "trigger_rule": "ransomware_exploitation",
      "confidence": 0.98,
      "evidence": {
        "ransomware_family": "LockBit"
      },
      "trigger_timestamp": "2026-03-05T12:00:00Z"
    }
  ]
}
```

**Response (404 Not Found):**
```json
{
  "detail": "CVE-2024-1234 not found in database"
}
```

---

### 3.2 Implementation

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from arango.database import StandardDatabase
from typing import Optional, List, Dict, Any

router = APIRouter(prefix="/v1", tags=["enrichment"])


class EnrichRequest(BaseModel):
    cve_id: str


class EnrichResponse(BaseModel):
    cve_id: str
    nvd_data: Optional[Dict[str, Any]]
    exploit_intelligence: Optional[Dict[str, Any]]
    regulatory_triggers: List[Dict[str, Any]]


@router.post("/enrich", response_model=EnrichResponse)
async def enrich_cve(request: EnrichRequest, db: StandardDatabase) -> EnrichResponse:
    """
    Enrich CVE with Phase 2 (NVD) + Phase 3A (VulnCheck) + Phase 3A-B (regulatory triggers).

    Response time target: < 500ms
    """
    cve_id = request.cve_id

    # Query 1: Get NVD data (Phase 2)
    nvd_query = """
    FOR vuln IN vulnerabilities
        FILTER vuln.cve_id == @cve_id
        RETURN {
            published: vuln.published,
            last_modified: vuln.last_modified,
            cvss_v31: vuln.cvss_v31,
            cvss_v3: vuln.cvss_v3,
            description: vuln.description,
            references: vuln.references
        }
    """
    nvd_cursor = db.aql.execute(nvd_query, bind_vars={"cve_id": cve_id})
    nvd_results = list(nvd_cursor)

    if not nvd_results:
        raise HTTPException(status_code=404, detail=f"{cve_id} not found in database")

    nvd_data = nvd_results[0]

    # Query 2: Get VulnCheck exploit intelligence (Phase 3A)
    exploit_query = """
    LET vuln_key = CONCAT('vulnerabilities/', @cve_id)

    // KEV status
    LET in_kev = LENGTH(
        FOR kev IN vulncheck_kev_entries
            FILTER kev.cve_id == @cve_id
            RETURN kev
    ) > 0
    LET kev_entry = FIRST(
        FOR kev IN vulncheck_kev_entries
            FILTER kev.cve_id == @cve_id
            RETURN kev
    )

    // Exploit intelligence
    LET exploit_intel = FIRST(
        FOR intel IN exploit_intelligence
            FILTER intel.cve_id == @cve_id
            RETURN intel
    )

    // Ransomware families
    LET ransomware_families = (
        FOR edge IN exploited_by_ransomware
            FILTER edge._from == vuln_key
            LET ransomware = DOCUMENT(edge._to)
            RETURN {
                name: ransomware.name,
                first_seen: ransomware.first_seen
            }
    )

    // Exploit chains
    LET exploit_chains = (
        FOR edge IN chain_includes_vuln
            FILTER edge._to == vuln_key
            LET chain = DOCUMENT(edge._from)
            RETURN {
                name: chain.name,
                position: edge.position,
                description: chain.description
            }
    )

    // Botnet campaigns
    LET botnets = (
        FOR edge IN exploited_by_botnet
            FILTER edge._from == vuln_key
            LET botnet = DOCUMENT(edge._to)
            RETURN {
                name: botnet.name,
                first_seen: botnet.first_seen
            }
    )

    RETURN {
        in_kev: in_kev,
        kev_date_added: kev_entry ? kev_entry.date_added : null,
        exploit_maturity: exploit_intel ? exploit_intel.exploit_maturity : null,
        ransomware_families: ransomware_families,
        exploit_chains: exploit_chains,
        botnet_campaigns: botnets
    }
    """
    exploit_cursor = db.aql.execute(exploit_query, bind_vars={"cve_id": cve_id})
    exploit_data = list(exploit_cursor)[0]

    # Query 3: Get regulatory triggers (Phase 3A-B)
    triggers_query = """
    LET vuln_key = CONCAT('vulnerabilities/', @cve_id)

    FOR edge IN vuln_triggers_requirement
        FILTER edge._from == vuln_key
        LET requirement = DOCUMENT(edge._to)
        RETURN {
            framework: requirement.framework,
            requirement_id: requirement.requirement_id,
            requirement_title: requirement.title,
            urgency: edge.urgency,
            trigger_rule: edge.trigger_rule,
            confidence: edge.confidence,
            evidence: edge.evidence,
            trigger_timestamp: edge.trigger_timestamp
        }
    """
    triggers_cursor = db.aql.execute(triggers_query, bind_vars={"cve_id": cve_id})
    regulatory_triggers = list(triggers_cursor)

    return EnrichResponse(
        cve_id=cve_id,
        nvd_data=nvd_data,
        exploit_intelligence=exploit_data,
        regulatory_triggers=regulatory_triggers
    )
```

**Performance Optimization:**
- Use AQL joins (faster than multiple queries)
- Indexes on `cve_id`, `_from`, `_to` fields
- Limit results (e.g., max 100 ransomware families)
- Optional: Add Redis caching for frequently requested CVEs (v2.0)

---

## 4. Placeholder Requirements Setup

### 4.1 Placeholder Requirements Script

**File:** `scripts/insert_placeholder_requirements.py`

**Purpose:** Insert 5 placeholder regulatory requirements for Phase 3A-B testing

```python
"""
Insert placeholder regulatory requirements for Phase 3A-B testing.

Phase 4 will replace these with real FDA 524B and CRA requirements.
"""

from complira_graph.db import get_db
import structlog

logger = structlog.get_logger()


PLACEHOLDER_REQUIREMENTS = [
    {
        "_key": "FDA_524B_KEV_RESPONSE",
        "framework": "FDA_524B",
        "requirement_id": "KEV_RESPONSE",
        "title": "Known Exploited Vulnerability Response",
        "description": "Medical device manufacturers must respond to CISA KEV-listed vulnerabilities within 24 hours",
        "urgency": "24h",
        "source": "FDA Cybersecurity in Medical Devices (524B)",
        "placeholder": True,
        "created_at": "2026-03-05T13:00:00Z"
    },
    {
        "_key": "CRA_CRITICAL_VULNERABILITY",
        "framework": "CRA",
        "requirement_id": "CRITICAL_VULN_NOTIFICATION",
        "title": "Critical Vulnerability Notification",
        "description": "Automotive manufacturers must notify authorities of actively exploited critical vulnerabilities within 24 hours",
        "urgency": "24h",
        "source": "EU Cyber Resilience Act (CRA)",
        "placeholder": True,
        "created_at": "2026-03-05T13:00:00Z"
    },
    {
        "_key": "FDA_524B_CVSS_HIGH",
        "framework": "FDA_524B",
        "requirement_id": "CVSS_HIGH_SEVERITY",
        "title": "CVSS 9.0+ High Severity Vulnerability",
        "description": "Medical device manufacturers must assess high severity vulnerabilities (CVSS 9.0+) for impact",
        "urgency": "high",
        "source": "FDA Cybersecurity in Medical Devices (524B)",
        "placeholder": True,
        "created_at": "2026-03-05T13:00:00Z"
    },
    {
        "_key": "CRA_RANSOMWARE_EXPLOITATION",
        "framework": "CRA",
        "requirement_id": "RANSOMWARE_EXPLOITATION",
        "title": "Ransomware Exploitation Detection",
        "description": "Automotive manufacturers must report vulnerabilities actively exploited by ransomware",
        "urgency": "critical",
        "source": "EU Cyber Resilience Act (CRA)",
        "placeholder": True,
        "created_at": "2026-03-05T13:00:00Z"
    },
    {
        "_key": "CRA_EXPLOIT_CHAIN",
        "framework": "CRA",
        "requirement_id": "EXPLOIT_CHAIN_DETECTION",
        "title": "Multi-CVE Exploit Chain Detection",
        "description": "Automotive manufacturers must identify vulnerabilities used in multi-CVE attack chains",
        "urgency": "critical",
        "source": "EU Cyber Resilience Act (CRA)",
        "placeholder": True,
        "created_at": "2026-03-05T13:00:00Z"
    }
]


def insert_placeholder_requirements():
    """Insert placeholder requirements into database."""
    db = get_db()
    collection = db.collection("regulatory_requirements")

    inserted_count = 0

    for req in PLACEHOLDER_REQUIREMENTS:
        try:
            # Check if requirement already exists
            if collection.has(req["_key"]):
                logger.info("Placeholder requirement already exists", key=req["_key"])
                continue

            # Insert requirement
            collection.insert(req)
            inserted_count += 1
            logger.info("Inserted placeholder requirement", key=req["_key"], title=req["title"])

        except Exception as e:
            logger.error("Failed to insert placeholder requirement", key=req["_key"], error=str(e))

    logger.info("Placeholder requirements inserted", count=inserted_count, total=len(PLACEHOLDER_REQUIREMENTS))

    return inserted_count


if __name__ == "__main__":
    insert_placeholder_requirements()
```

**Execution:**
```bash
.venv/bin/python scripts/insert_placeholder_requirements.py
```

**Output:**
```
2026-03-05 13:00:00 [info] Inserted placeholder requirement key=FDA_524B_KEV_RESPONSE
2026-03-05 13:00:00 [info] Inserted placeholder requirement key=CRA_CRITICAL_VULNERABILITY
2026-03-05 13:00:00 [info] Inserted placeholder requirement key=FDA_524B_CVSS_HIGH
2026-03-05 13:00:00 [info] Inserted placeholder requirement key=CRA_RANSOMWARE_EXPLOITATION
2026-03-05 13:00:00 [info] Inserted placeholder requirement key=CRA_EXPLOIT_CHAIN
2026-03-05 13:00:00 [info] Placeholder requirements inserted count=5 total=5
```

---

## 5. Database Schema

### 5.1 Edge Collection: vuln_triggers_requirement

**Collection:** `vuln_triggers_requirement` (already exists from Phase 3A)

**Edge Schema:**
```python
{
    "_key": "auto-generated",
    "_from": "vulnerabilities/CVE_2024_1234",
    "_to": "regulatory_requirements/FDA_524B_KEV_RESPONSE",
    "trigger_rule": "kev_entry",  # One of: kev_entry, cvss_critical, ransomware_exploitation, exploit_chain
    "urgency": "24h",  # One of: 24h, high, critical
    "confidence": 1.0,  # Float 0.0-1.0
    "evidence": {
        "source": "vulncheck_kev",
        "date_added": "2024-03-05",
        "vulncheck_first": true,
        "description": "..."
    },
    "trigger_timestamp": "2026-03-05T12:00:00Z",
    "trigger_source": "regulatory_trigger_service_v1"
}
```

**Indexes (no new indexes needed):**
- `_from` (automatic edge index)
- `_to` (automatic edge index)

---

### 5.2 Document Collection: agent_checkpoints

**Collection:** `agent_checkpoints` (already exists from Phase 2)

**Checkpoint Schema:**
```python
{
    "_key": "regulatory_trigger_service_kev_entry",
    "agent_name": "regulatory_trigger_service",
    "rule_name": "kev_entry",
    "last_processed_timestamp": "2026-03-05T12:00:00Z",
    "last_processed_count": 4609,
    "updated_at": "2026-03-05T12:05:00Z"
}
```

---

## 6. Testing Strategy

### 6.1 Unit Tests

**File:** `tests/agents/test_regulatory_trigger_service.py`

**Test Cases (20 tests):**

1. **Service Initialization:**
   - `test_service_initialization` - Service initializes with database
   - `test_service_without_database` - Raises error if no database

2. **Trigger Rule 1 (KEV Entry):**
   - `test_trigger_rule_kev_entry_creates_edges` - Creates 4,609 edges for KEV entries
   - `test_trigger_rule_kev_entry_idempotent` - No duplicate edges on re-run
   - `test_trigger_rule_kev_entry_checkpoint` - Incremental processing with checkpoint
   - `test_trigger_rule_kev_entry_metadata` - Edge metadata correct (urgency, confidence, evidence)
   - `test_trigger_rule_kev_entry_missing_requirement` - Graceful handling if requirement missing

3. **Trigger Rule 2 (CVSS 9.0+):**
   - `test_trigger_rule_cvss_critical_creates_edges` - Creates edges for CVSS 9.0+ CVEs
   - `test_trigger_rule_cvss_critical_idempotent` - No duplicate edges on re-run
   - `test_trigger_rule_cvss_critical_metadata` - Edge metadata includes CVSS score

4. **Trigger Rule 3 (Ransomware):**
   - `test_trigger_rule_ransomware_creates_edges` - Creates edges for ransomware-exploited CVEs
   - `test_trigger_rule_ransomware_idempotent` - No duplicate edges on re-run
   - `test_trigger_rule_ransomware_metadata` - Edge metadata includes ransomware family

5. **Trigger Rule 4 (Exploit Chain):**
   - `test_trigger_rule_exploit_chain_creates_edges` - Creates edges for exploit chain CVEs
   - `test_trigger_rule_exploit_chain_idempotent` - No duplicate edges on re-run
   - `test_trigger_rule_exploit_chain_metadata` - Edge metadata includes chain name

6. **Service Integration:**
   - `test_service_run_all_rules` - Runs all 4 rules in sequence
   - `test_service_run_single_rule` - Runs single rule
   - `test_service_checkpoint_tracking` - Checkpoint updated after execution
   - `test_service_force_full_scan` - Ignores checkpoint when force_full_scan=True

**Mocking Strategy:**
- Mock ArangoDB connection for unit tests
- Use in-memory data structures for collections
- Mock VulnCheck paid tier data (ransomware, exploit chains)

---

### 6.2 Integration Tests

**File:** `tests/integration/test_enrich_endpoint.py`

**Test Cases (10 tests):**

1. **API Endpoint Tests:**
   - `test_enrich_endpoint_success` - Returns 200 OK with full data
   - `test_enrich_endpoint_not_found` - Returns 404 for unknown CVE
   - `test_enrich_endpoint_performance` - Response time < 500ms
   - `test_enrich_endpoint_invalid_cve_id` - Returns 400 for malformed CVE ID

2. **Data Merge Tests:**
   - `test_enrich_endpoint_nvd_data` - Includes Phase 2 NVD data
   - `test_enrich_endpoint_exploit_intelligence` - Includes Phase 3A VulnCheck data
   - `test_enrich_endpoint_regulatory_triggers` - Includes Phase 3A-B trigger edges

3. **Trigger Rule Tests:**
   - `test_enrich_endpoint_kev_trigger` - KEV entry triggers 24h urgency
   - `test_enrich_endpoint_cvss_trigger` - CVSS 9.0+ triggers high urgency
   - `test_enrich_endpoint_multiple_triggers` - CVE with multiple triggers (KEV + CVSS)

**Test Data:**
- Use real CVE-2021-44228 (Log4Shell) as test case (in KEV, CVSS 10.0)
- Verify 2+ regulatory triggers (KEV + CVSS)

---

### 6.3 Manual Integration Tests

**Test Cases:**

1. **Insert placeholder requirements:**
   ```bash
   .venv/bin/python scripts/insert_placeholder_requirements.py
   ```
   **Expected:** 5 requirements inserted

2. **Run RegulatoryTriggerService:**
   ```bash
   .venv/bin/python scripts/run_regulatory_trigger_service.py
   ```
   **Expected:** 4,609+ edges created (Rule 1 + Rule 2)

3. **Test POST /v1/enrich:**
   ```bash
   curl -X POST http://localhost:8000/v1/enrich \
     -H "Content-Type: application/json" \
     -d '{"cve_id": "CVE-2021-44228"}'
   ```
   **Expected:** Response includes KEV + CVSS triggers

4. **Verify idempotency:**
   ```bash
   .venv/bin/python scripts/run_regulatory_trigger_service.py
   ```
   **Expected:** 0 new edges created (all already exist)

---

## 7. Performance Targets

### 7.1 RegulatoryTriggerService Performance

**Target:** < 10 seconds per 1,000 CVEs

**Expected Performance:**
- Rule 1 (KEV Entry): 4,609 CVEs → ~45 seconds (first run), < 1 second (incremental)
- Rule 2 (CVSS 9.0+): ~20,000 CVEs → ~200 seconds (first run), < 1 second (incremental)
- Rule 3 (Ransomware): 0 CVEs (paid tier) → < 1 second
- Rule 4 (Exploit Chain): 0 CVEs (paid tier) → < 1 second

**Optimization Strategies:**
- Batch processing with AQL (avoid N+1 queries)
- Checkpoint-based incremental processing
- Indexes on `cve_id`, `_from`, `_to` fields

---

### 7.2 POST /v1/enrich Performance

**Target:** < 500ms per request

**Expected Performance:**
- Query 1 (NVD data): ~50ms
- Query 2 (Exploit intelligence): ~100ms
- Query 3 (Regulatory triggers): ~50ms
- Response serialization: ~50ms
- **Total:** ~250ms (well within target)

**Optimization Strategies:**
- Use single AQL query with UNION (reduce round trips)
- Add Redis caching for frequently requested CVEs (v2.0)
- Limit result sizes (e.g., max 100 ransomware families)

---

## 8. File Structure

```
src/complira_graph/
├── services/
│   ├── regulatory_trigger_service.py      # Main service (300-400 lines)
│   ├── trigger_rules.py                    # 4 trigger rule implementations (150-200 lines)
│   └── checkpoint_service.py               # Checkpoint management (100-150 lines)
│
├── api/
│   └── enrich.py                           # POST /v1/enrich endpoint (150-200 lines)
│
└── db.py                                   # No changes needed (vuln_triggers_requirement exists)

tests/
├── agents/
│   └── test_regulatory_trigger_service.py  # Unit tests (300-400 lines)
│
└── integration/
    └── test_enrich_endpoint.py             # Integration tests (150-200 lines)

scripts/
├── insert_placeholder_requirements.py      # Insert 5 placeholder requirements (50-100 lines)
└── run_regulatory_trigger_service.py       # Manual testing script (50-100 lines)
```

**Total Estimated LOC:** ~1,200-1,700 lines (within SMALL scope: ~1,100-1,500 lines)

---

## 9. Acceptance Criteria Mapping

| AC | Description | Design Component | Test Strategy |
|----|-------------|------------------|---------------|
| AC1 | RegulatoryTriggerService Implementation | `regulatory_trigger_service.py` | Unit tests (20 tests) |
| AC2 | Trigger Rule 1 - KEV Entry | `trigger_rules.py::trigger_rule_kev_entry` | Unit test + manual test (4,609 edges) |
| AC3 | Trigger Rule 2 - CVSS 9.0+ | `trigger_rules.py::trigger_rule_cvss_critical` | Unit test + manual test (~20K edges) |
| AC4 | Trigger Rule 3 - Ransomware | `trigger_rules.py::trigger_rule_ransomware_exploitation` | Unit test (mocked), integration test deferred |
| AC5 | Trigger Rule 4 - Exploit Chain | `trigger_rules.py::trigger_rule_exploit_chain` | Unit test (mocked), integration test deferred |
| AC6 | POST /v1/enrich Endpoint | `api/enrich.py` | Integration tests (10 tests) |
| AC7 | Unit Tests | `test_regulatory_trigger_service.py` | 20 unit tests (100% rule coverage) |
| AC8 | Integration Tests | `test_enrich_endpoint.py` | 10 integration tests (API + data merge) |

---

## 10. Risk Mitigation

### Risk 1: Edge Count Explosion

**Mitigation:**
- ArangoDB tested with millions of edges (Phase 2)
- Batch processing with checkpoints (scalability)
- Indexes on `_from`, `_to` (performance)

---

### Risk 2: POST /v1/enrich Performance

**Mitigation:**
- Use efficient AQL queries with joins
- Limit result sizes (e.g., max 100 ransomware families)
- Load test during Stage 7 (API/E2E testing)
- Optional: Add Redis caching (v2.0)

---

### Risk 3: Idempotency Edge Cases

**Mitigation:**
- Check for existing edges before insert (AQL `FILTER !edge_exists`)
- Unit tests for idempotency
- Manual test with multiple runs (verify 0 duplicate edges)

---

## 11. Future Enhancements (v2.0)

1. **Configurable Trigger Rules** - YAML/JSON configuration instead of hardcoded
2. **Custom Trigger Rules** - User-defined rules via API
3. **Trigger Rule Priorities** - Conflict resolution when multiple rules apply
4. **Historical Trigger Tracking** - Log when edges were created/updated/deleted
5. **Real-time Trigger Notifications** - Webhook/email notifications when new triggers generated
6. **Trigger Rule Performance Dashboard** - Metrics on execution time, edge counts, etc.

---

## Summary

**Design Completeness:**
- ✅ RegulatoryTriggerService architecture defined
- ✅ 4 trigger rule implementations specified (AQL queries)
- ✅ POST /v1/enrich endpoint designed (request/response schema)
- ✅ Placeholder requirements setup planned (5 requirements)
- ✅ Testing strategy defined (20 unit tests, 10 integration tests)
- ✅ Performance targets specified (< 10s per 1K CVEs, < 500ms API response)
- ✅ File structure planned (8-10 files, ~1,200-1,700 lines)
- ✅ Acceptance criteria mapped to components

**Stage 3 Gate:** ✅ **READY FOR STAGE 4** (Runtime Modeling)

---

**Document Version:** 1.0
**Created:** 2026-03-05
**Author:** Claude Code (Anthropic)
**Status:** ✅ Stage 3 Design Basis Complete - Ready for Stage 4 (Runtime Modeling)
