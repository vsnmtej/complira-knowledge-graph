# Proposed Design: Phase 2 Enrichment Pipeline

**Ticket:** phase-2-enrichment-pipeline
**Stage:** 3 (Design Basis)
**Date:** 2026-03-03
**Version:** v1

---

## Design Overview

Phase 2 implements three enrichment endpoints that transform raw scan findings into actionable security intelligence by querying the reference database and traversing the knowledge graph.

**Architecture Pattern:** Follows Phase 1 patterns (Model-First Service, Model-Dict Adapter Repository)

**Key Design Principles:**
1. **On-demand computation** - No caching, always fresh data
2. **Read-only operations** - Never modify scan_findings
3. **Graceful degradation** - Handle missing data elegantly
4. **Performance-first** - Batch queries, <5s for 100 findings

---

## 1. Architecture Patterns

### 1.1 Layered Architecture (Consistent with Phase 1)

```
┌─────────────────────────────────────────────────────────────┐
│  API Layer (FastAPI)                                         │
│  - /v1/enrich, /v1/compact, /v1/map-controls                 │
│  - Request/Response models (Pydantic)                        │
│  - Authentication (X-API-Key → CustomerProfile)              │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│  Service Layer (Business Logic)                              │
│  - EnrichmentService                                         │
│  - CompactionService                                         │
│  - ControlMappingService                                     │
│  - Model-First Pattern (works with Pydantic models)          │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│  Repository Layer (Data Access)                              │
│  - EnrichmentRepository (CVE, EPSS, KEV, CWE chain)          │
│  - CWERepository (CWE hierarchy, rollup)                     │
│  - RegulatoryRepository (CWE → Controls)                     │
│  - Model-Dict Adapter Pattern                                │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│  Database Layer (ArangoDB)                                   │
│  - Reference DB (read-only): vulnerabilities, epss_history,  │
│    kev_entries, weaknesses, attack_techniques, etc.          │
│  - Customer DB: scan_sessions, scan_findings                 │
│  - Graph traversal via AQL                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Repository Design

### 2.1 EnrichmentRepository

**Purpose:** Query reference database for enrichment data (CVE details, EPSS, KEV, threat chain)

**File:** `src/api/repositories/enrichment.py`

**Class Definition:**
```python
from typing import Optional, List, Dict
from api.repositories.base import BaseRepository
from complira_graph.models import Vulnerability, EPSSHistory, KEVEntry, Weakness, AttackPattern, ATTACKTechnique

class EnrichmentRepository(BaseRepository):
    """
    Repository for enrichment data queries.

    Queries reference database for:
    - CVE details (Vulnerability model)
    - EPSS scores (EPSSHistory model)
    - KEV status (KEVEntry model)
    - Threat intelligence chain (CWE → CAPEC → ATT&CK)
    """

    def __init__(self, reference_db):
        """
        Initialize with reference database (not customer database).

        Args:
            reference_db: ArangoDB reference database instance
        """
        super().__init__(reference_db, None)  # No primary collection
        self.reference_db = reference_db

    def get_cve_details(self, cve_id: str) -> Optional[Vulnerability]:
        """
        Get CVE details from reference database.

        Args:
            cve_id: CVE ID (e.g., "CVE-2024-1234")

        Returns:
            Vulnerability model or None if not found

        AQL Query:
            FOR vuln IN vulnerabilities
                FILTER vuln.cve_id == @cve_id
                RETURN vuln
        """
        pass

    def get_latest_epss(self, cve_id: str) -> Optional[EPSSHistory]:
        """
        Get latest EPSS score for CVE.

        Args:
            cve_id: CVE ID

        Returns:
            EPSSHistory model (latest by score_date) or None

        AQL Query:
            FOR epss IN epss_history
                FILTER epss.cve_id == @cve_id
                SORT epss.score_date DESC
                LIMIT 1
                RETURN epss
        """
        pass

    def check_kev_status(self, cve_id: str) -> Optional[KEVEntry]:
        """
        Check if CVE is in CISA KEV catalog.

        Args:
            cve_id: CVE ID

        Returns:
            KEVEntry model or None if not in KEV

        AQL Query:
            FOR kev IN kev_entries
                FILTER kev.cve_id == @cve_id
                RETURN kev
        """
        pass

    def get_threat_intelligence_chain(self, cwe_ids: List[str]) -> Dict[str, List]:
        """
        Get CWE → CAPEC → ATT&CK chain for threat intelligence.

        Args:
            cwe_ids: List of CWE IDs (e.g., ["CWE-79", "CWE-89"])

        Returns:
            {
                "cwe": [Weakness models],
                "capec": [AttackPattern models],
                "attack": [ATTACKTechnique models]
            }

        AQL Query (Graph Traversal):
            FOR cwe_id IN @cwe_ids
                LET cwe = FIRST(FOR c IN weaknesses FILTER c.cwe_id == cwe_id RETURN c)

                LET capecs = (
                    FOR v, e, p IN 1..1 OUTBOUND cwe._id capec_relates_to_cwe
                        RETURN v
                )

                LET attacks = (
                    FOR capec IN capecs
                        FOR v, e, p IN 1..1 OUTBOUND capec._id capec_maps_to_attack
                            RETURN v
                )

                RETURN {
                    cwe: cwe,
                    capecs: capecs,
                    attacks: attacks
                }
        """
        pass

    def batch_get_cve_details(self, cve_ids: List[str]) -> List[Vulnerability]:
        """
        Batch query for multiple CVE details (performance optimization).

        Args:
            cve_ids: List of CVE IDs

        Returns:
            List of Vulnerability models

        AQL Query:
            FOR vuln IN vulnerabilities
                FILTER vuln.cve_id IN @cve_ids
                RETURN vuln
        """
        pass

    def batch_get_epss(self, cve_ids: List[str]) -> List[EPSSHistory]:
        """
        Batch query for multiple EPSS scores (latest for each CVE).

        Args:
            cve_ids: List of CVE IDs

        Returns:
            List of EPSSHistory models

        AQL Query:
            FOR cve_id IN @cve_ids
                LET latest_epss = FIRST(
                    FOR epss IN epss_history
                        FILTER epss.cve_id == cve_id
                        SORT epss.score_date DESC
                        LIMIT 1
                        RETURN epss
                )
                FILTER latest_epss != null
                RETURN latest_epss
        """
        pass

    def batch_check_kev(self, cve_ids: List[str]) -> List[KEVEntry]:
        """
        Batch query to check KEV status for multiple CVEs.

        Args:
            cve_ids: List of CVE IDs

        Returns:
            List of KEVEntry models (only for CVEs in KEV)

        AQL Query:
            FOR kev IN kev_entries
                FILTER kev.cve_id IN @cve_ids
                RETURN kev
        """
        pass
```

---

### 2.2 CWERepository

**Purpose:** Query CWE hierarchy for compaction (rollup to parent CWEs)

**File:** `src/api/repositories/cwe.py`

**Class Definition:**
```python
from typing import Optional, List
from api.repositories.base import BaseRepository
from complira_graph.models import Weakness

class CWERepository(BaseRepository):
    """
    Repository for CWE hierarchy queries.

    Used for:
    - CWE rollup (child → parent)
    - CWE hierarchy traversal
    """

    def __init__(self, reference_db):
        super().__init__(reference_db, "weaknesses")
        self.reference_db = reference_db

    def get_cwe(self, cwe_id: str) -> Optional[Weakness]:
        """
        Get CWE by ID.

        Args:
            cwe_id: CWE ID (e.g., "CWE-79")

        Returns:
            Weakness model or None
        """
        pass

    def get_parent_cwe(self, cwe_id: str) -> Optional[Weakness]:
        """
        Get parent CWE via child_of edge.

        Args:
            cwe_id: Child CWE ID

        Returns:
            Parent Weakness model or None

        AQL Query (Graph Traversal):
            FOR cwe IN weaknesses
                FILTER cwe.cwe_id == @cwe_id
                FOR parent IN 1..1 OUTBOUND cwe._id child_of
                    RETURN parent
        """
        pass

    def get_cwe_hierarchy(self, cwe_id: str, max_depth: int = 10) -> List[Weakness]:
        """
        Get CWE hierarchy from child to root (all ancestors).

        Args:
            cwe_id: Starting CWE ID
            max_depth: Maximum traversal depth

        Returns:
            List of Weakness models (child → parent → ... → root)

        AQL Query (Graph Traversal):
            FOR cwe IN weaknesses
                FILTER cwe.cwe_id == @cwe_id
                FOR v, e, p IN 1..@max_depth OUTBOUND cwe._id child_of
                    RETURN v
        """
        pass

    def rollup_to_abstraction_level(self, cwe_id: str, target_level: str = "Class") -> Optional[Weakness]:
        """
        Roll up CWE to specific abstraction level (Base → Class → Pillar).

        Args:
            cwe_id: Starting CWE ID
            target_level: Target abstraction ("Class", "Pillar")

        Returns:
            Weakness model at target abstraction level

        AQL Query:
            FOR cwe IN weaknesses
                FILTER cwe.cwe_id == @cwe_id
                FOR v IN 1..10 OUTBOUND cwe._id child_of
                    FILTER v.abstraction == @target_level
                    LIMIT 1
                    RETURN v
        """
        pass
```

---

### 2.3 RegulatoryRepository

**Purpose:** Query CWE → Regulatory Control mappings

**File:** `src/api/repositories/regulatory.py`

**Class Definition:**
```python
from typing import List, Dict
from api.repositories.base import BaseRepository
from complira_graph.models import RegulatoryRequirement, OSCALControl, SCFControl

class RegulatoryRepository(BaseRepository):
    """
    Repository for regulatory control mappings.

    Queries CWE → Regulatory Requirements via maps_to_requirement edge.
    """

    def __init__(self, reference_db):
        super().__init__(reference_db, None)
        self.reference_db = reference_db

    def get_requirements_for_cwe(
        self,
        cwe_id: str,
        frameworks: List[str]
    ) -> List[RegulatoryRequirement]:
        """
        Get regulatory requirements mapped to CWE.

        Args:
            cwe_id: CWE ID
            frameworks: List of framework IDs (e.g., ["nist_800_53", "fda_524b"])

        Returns:
            List of RegulatoryRequirement models

        AQL Query:
            FOR cwe IN weaknesses
                FILTER cwe.cwe_id == @cwe_id
                FOR req IN 1..1 OUTBOUND cwe._id maps_to_requirement
                    FILTER req.framework_id IN @frameworks
                    RETURN req
        """
        pass

    def get_nist_controls_for_cwe(self, cwe_id: str) -> List[OSCALControl]:
        """
        Get NIST 800-53 controls for CWE.

        Args:
            cwe_id: CWE ID

        Returns:
            List of OSCALControl models

        AQL Query:
            FOR cwe IN weaknesses
                FILTER cwe.cwe_id == @cwe_id
                FOR control IN 1..2 OUTBOUND cwe._id maps_to_requirement, technique_mitigated_by_control
                    FILTER control._id LIKE 'oscal_controls/%'
                    RETURN control
        """
        pass

    def get_scf_controls_for_cwe(self, cwe_id: str) -> List[SCFControl]:
        """
        Get SCF controls for CWE.

        Args:
            cwe_id: CWE ID

        Returns:
            List of SCFControl models
        """
        pass

    def batch_get_controls(
        self,
        cwe_ids: List[str],
        frameworks: List[str]
    ) -> Dict[str, List]:
        """
        Batch query: Get controls for multiple CWEs.

        Args:
            cwe_ids: List of CWE IDs
            frameworks: List of framework IDs

        Returns:
            {
                "CWE-79": [controls],
                "CWE-89": [controls],
                ...
            }
        """
        pass
```

---

## 3. Service Design

### 3.1 EnrichmentService

**Purpose:** Orchestrate enrichment logic, coordinate between repositories

**File:** `src/api/services/enrichment.py`

**Class Definition:**
```python
from typing import List, Dict, Optional
from api.services.base import BaseGraphService
from api.repositories.enrichment import EnrichmentRepository
from api.repositories.scan import ScanSessionRepository, ScanFindingRepository
from complira_graph.models import ScanFinding

class EnrichmentService(BaseGraphService):
    """
    Service for enriching scan findings with vulnerability intelligence.

    Orchestrates:
    - Fetch findings from customer DB
    - Query reference DB for enrichment data
    - Build enriched response
    """

    async def enrich_scan_session(
        self,
        customer_id: str,
        scan_session_id: str
    ) -> Dict:
        """
        Enrich all findings in a scan session.

        Flow:
        1. Get scan findings from customer DB
        2. Group findings by CVE ID (for batch queries)
        3. Batch query reference DB:
           - CVE details
           - EPSS scores
           - KEV status
           - CWE → CAPEC → ATT&CK chain
        4. Build enriched findings
        5. Return enriched response

        Args:
            customer_id: Customer identifier
            scan_session_id: Scan session ID

        Returns:
            {
                "scan_session_id": str,
                "enriched_findings": [EnrichedFinding],
                "summary": {
                    "total_findings": int,
                    "enriched_count": int,
                    "kev_count": int,
                    "high_epss_count": int
                }
            }
        """
        # 1. Get findings from customer DB
        customer_db = get_customer_db(customer_id)
        finding_repo = ScanFindingRepository(customer_db)
        findings = finding_repo.list_session_findings(customer_id, scan_session_id)

        # 2. Group by CVE ID for batch queries
        cve_findings = [f for f in findings if f.cve_id]
        non_cve_findings = [f for f in findings if not f.cve_id]

        cve_ids = list(set([f.cve_id for f in cve_findings]))
        cwe_ids = list(set([cwe for f in findings for cwe in (f.cwe_ids or [])]))

        # 3. Batch query reference DB
        reference_db = get_reference_db()
        enrichment_repo = EnrichmentRepository(reference_db)

        cve_details_map = self._build_cve_map(
            enrichment_repo.batch_get_cve_details(cve_ids)
        )
        epss_map = self._build_epss_map(
            enrichment_repo.batch_get_epss(cve_ids)
        )
        kev_map = self._build_kev_map(
            enrichment_repo.batch_check_kev(cve_ids)
        )
        threat_intel = enrichment_repo.get_threat_intelligence_chain(cwe_ids)

        # 4. Build enriched findings
        enriched_findings = []

        for finding in cve_findings:
            enriched = self._enrich_cve_finding(
                finding,
                cve_details_map,
                epss_map,
                kev_map,
                threat_intel
            )
            enriched_findings.append(enriched)

        for finding in non_cve_findings:
            enriched = self._enrich_non_cve_finding(finding, threat_intel)
            enriched_findings.append(enriched)

        # 5. Build summary
        summary = self._build_summary(enriched_findings)

        return {
            "scan_session_id": scan_session_id,
            "enriched_findings": enriched_findings,
            "summary": summary
        }

    def _enrich_cve_finding(
        self,
        finding: ScanFinding,
        cve_map,
        epss_map,
        kev_map,
        threat_intel
    ) -> Dict:
        """
        Enrich CVE finding (full enrichment).

        Returns enriched finding dict with:
        - cve_details
        - epss
        - kev_status
        - threat_intel
        """
        pass

    def _enrich_non_cve_finding(
        self,
        finding: ScanFinding,
        threat_intel
    ) -> Dict:
        """
        Enrich non-CVE finding (CWE-based enrichment only).

        Returns enriched finding dict with:
        - threat_intel (CWE → CAPEC → ATT&CK)
        - No CVE details, EPSS, or KEV (N/A)
        """
        pass
```

---

### 3.2 CompactionService

**Purpose:** Deduplicate findings and roll up CWE hierarchies

**File:** `src/api/services/compaction.py`

**Class Definition:**
```python
from typing import List, Dict
from api.services.base import BaseGraphService
from api.repositories.cwe import CWERepository
from api.repositories.scan import ScanFindingRepository
from complira_graph.models import ScanFinding

class CompactionService(BaseGraphService):
    """
    Service for compacting scan findings.

    Operations:
    - Deduplicate by CVE ID
    - Roll up CWE hierarchies
    - Aggregate locations
    """

    async def compact_findings(
        self,
        customer_id: str,
        scan_session_id: str,
        deduplicate_by: str = "cve_id",
        rollup_cwe: bool = True,
        cwe_rollup_level: str = "Class"
    ) -> Dict:
        """
        Compact findings from scan session.

        Flow:
        1. Get findings from customer DB
        2. Deduplicate by CVE ID (group findings)
        3. If rollup_cwe: Roll up CWEs to parent level
        4. Aggregate locations
        5. Return compacted findings

        Args:
            customer_id: Customer identifier
            scan_session_id: Scan session ID
            deduplicate_by: Deduplication key ("cve_id" or "cwe_id")
            rollup_cwe: Whether to roll up CWE hierarchy
            cwe_rollup_level: Target CWE abstraction level

        Returns:
            {
                "scan_session_id": str,
                "compacted_findings": [CompactedFinding],
                "summary": {
                    "original_count": int,
                    "compacted_count": int,
                    "reduction_percentage": int
                }
            }
        """
        pass

    def _deduplicate_by_cve(self, findings: List[ScanFinding]) -> Dict[str, List]:
        """
        Group findings by CVE ID.

        Returns:
            {
                "CVE-2024-1234": [finding1, finding2, ...],
                ...
            }
        """
        pass

    def _rollup_cwe(self, cwe_id: str, target_level: str, cwe_repo: CWERepository) -> str:
        """
        Roll up CWE to target abstraction level.

        Args:
            cwe_id: Original CWE ID
            target_level: Target level ("Class", "Pillar")
            cwe_repo: CWE repository

        Returns:
            Parent CWE ID at target level
        """
        pass
```

---

### 3.3 ControlMappingService

**Purpose:** Map findings to regulatory controls

**File:** `src/api/services/control_mapping.py`

**Class Definition:**
```python
from typing import List, Dict
from api.services.base import BaseGraphService
from api.repositories.regulatory import RegulatoryRepository
from api.repositories.scan import ScanFindingRepository

class ControlMappingService(BaseGraphService):
    """
    Service for mapping findings to regulatory controls.

    Maps CVE → CWE → Regulatory Requirements/Controls.
    """

    async def map_controls(
        self,
        customer_id: str,
        scan_session_id: str,
        frameworks: List[str]
    ) -> Dict:
        """
        Map findings to regulatory controls.

        Flow:
        1. Get findings from customer DB
        2. Extract unique CWE IDs
        3. Batch query reference DB for controls
        4. Build control mappings per finding
        5. Return control mappings

        Args:
            customer_id: Customer identifier
            scan_session_id: Scan session ID
            frameworks: List of frameworks (["nist_800_53", "fda_524b", "iso_27001"])

        Returns:
            {
                "scan_session_id": str,
                "control_mappings": [ControlMapping],
                "summary": {
                    "total_findings": int,
                    "findings_with_mappings": int,
                    "unique_controls_affected": {
                        "nist_800_53": int,
                        "fda_524b": int,
                        "iso_27001": int
                    }
                }
            }
        """
        pass
```

---

## 4. API Endpoint Design

### 4.1 POST /v1/enrich

**File:** `src/api/v1/endpoints/enrichment.py`

**Endpoint Definition:**
```python
from fastapi import APIRouter, Depends, HTTPException
from api.models.requests.enrichment import EnrichRequest
from api.models.responses.enrichment import EnrichResponse
from api.core.security import get_current_customer
from api.services.enrichment import EnrichmentService
from complira_graph.models import CustomerProfile

router = APIRouter()

@router.post("/enrich", response_model=EnrichResponse)
async def enrich_scan_findings(
    request: EnrichRequest,
    customer: CustomerProfile = Depends(get_current_customer),
):
    """
    Enrich scan findings with vulnerability intelligence.

    Adds CVE details, EPSS scores, KEV status, CWE/CAPEC/ATT&CK mappings.

    Request:
        {
            "scan_session_id": "session_123"
        }

    Response:
        {
            "scan_session_id": "session_123",
            "enriched_findings": [...],
            "summary": {...}
        }
    """
    service = EnrichmentService()
    result = await service.enrich_scan_session(
        customer._key,
        request.scan_session_id
    )
    return result
```

---

### 4.2 POST /v1/compact

**Endpoint Definition:**
```python
@router.post("/compact", response_model=CompactResponse)
async def compact_scan_findings(
    request: CompactRequest,
    customer: CustomerProfile = Depends(get_current_customer),
):
    """
    Compact scan findings (deduplicate + rollup CWEs).

    Request:
        {
            "scan_session_id": "session_123",
            "options": {
                "deduplicate_by": "cve_id",
                "rollup_cwe": true,
                "cwe_rollup_level": "Class"
            }
        }

    Response:
        {
            "scan_session_id": "session_123",
            "compacted_findings": [...],
            "summary": {...}
        }
    """
    service = CompactionService()
    result = await service.compact_findings(
        customer._key,
        request.scan_session_id,
        **request.options.dict()
    )
    return result
```

---

### 4.3 POST /v1/map-controls

**Endpoint Definition:**
```python
@router.post("/map-controls", response_model=ControlMappingsResponse)
async def map_findings_to_controls(
    request: MapControlsRequest,
    customer: CustomerProfile = Depends(get_current_customer),
):
    """
    Map scan findings to regulatory controls.

    Request:
        {
            "scan_session_id": "session_123",
            "frameworks": ["nist_800_53", "fda_524b", "iso_27001"]
        }

    Response:
        {
            "scan_session_id": "session_123",
            "control_mappings": [...],
            "summary": {...}
        }
    """
    service = ControlMappingService()
    result = await service.map_controls(
        customer._key,
        request.scan_session_id,
        request.frameworks
    )
    return result
```

---

## 5. Request/Response Models

### 5.1 Enrichment Models

**File:** `src/api/models/requests/enrichment.py`

```python
from pydantic import BaseModel

class EnrichRequest(BaseModel):
    scan_session_id: str
```

**File:** `src/api/models/responses/enrichment.py`

```python
from typing import List, Dict, Optional
from pydantic import BaseModel

class CVEDetails(BaseModel):
    description: str
    cvss_v3_score: Optional[float]
    cvss_v3_vector: Optional[str]
    published_date: Optional[str]
    references: List[str]

class EPSSData(BaseModel):
    score: float
    percentile: float
    date: str

class KEVStatus(BaseModel):
    in_kev: bool
    date_added: Optional[str] = None
    due_date: Optional[str] = None
    known_ransomware: bool = False

class ThreatIntel(BaseModel):
    cwe_id: Optional[str]
    cwe_name: Optional[str]
    capec_patterns: List[str]
    attack_tactics: List[str]

class Enrichment(BaseModel):
    cve_details: Optional[CVEDetails]
    epss: Optional[EPSSData]
    kev_status: Optional[KEVStatus]
    threat_intel: Optional[ThreatIntel]

class EnrichedFinding(BaseModel):
    finding_id: str
    cve_id: Optional[str]
    severity: str
    description: str
    location: str
    enrichment: Enrichment

class EnrichSummary(BaseModel):
    total_findings: int
    enriched_count: int
    kev_count: int
    high_epss_count: int

class EnrichResponse(BaseModel):
    scan_session_id: str
    enriched_findings: List[EnrichedFinding]
    summary: EnrichSummary
```

---

### 5.2 Compaction Models

**File:** `src/api/models/requests/compaction.py`

```python
from pydantic import BaseModel
from typing import Optional

class CompactionOptions(BaseModel):
    deduplicate_by: str = "cve_id"
    rollup_cwe: bool = True
    cwe_rollup_level: str = "Class"

class CompactRequest(BaseModel):
    scan_session_id: str
    options: CompactionOptions = CompactionOptions()
```

---

## 6. Database Access Patterns

### 6.1 Reference DB vs Customer DB

**Key Distinction:**
- **Customer DB:** Contains scan_sessions, scan_findings (Phase 1)
- **Reference DB:** Contains vulnerabilities, epss_history, kev_entries, weaknesses, etc.

**Access Pattern:**
```python
# Get customer DB
from api.core.database import get_customer_db
customer_db = get_customer_db(customer_id)

# Get reference DB
from api.core.database import get_reference_db
reference_db = get_reference_db()
```

---

### 6.2 AQL Query Patterns

**Pattern 1: Simple Lookup**
```python
# Get CVE details
query = """
FOR vuln IN vulnerabilities
    FILTER vuln.cve_id == @cve_id
    RETURN vuln
"""
```

**Pattern 2: Graph Traversal (1 hop)**
```python
# Get CWEs for CVE
query = """
FOR vuln IN vulnerabilities
    FILTER vuln.cve_id == @cve_id
    FOR cwe IN 1..1 OUTBOUND vuln._id has_weakness
        RETURN cwe
"""
```

**Pattern 3: Graph Traversal (Multi-hop CWE → CAPEC → ATT&CK)**
```python
# Get threat chain
query = """
FOR cwe IN weaknesses
    FILTER cwe.cwe_id == @cwe_id
    LET capecs = (
        FOR c IN 1..1 INBOUND cwe._id capec_relates_to_cwe
            RETURN c
    )
    LET attacks = (
        FOR capec IN capecs
            FOR a IN 1..1 OUTBOUND capec._id capec_maps_to_attack
                RETURN a
    )
    RETURN {
        cwe: cwe,
        capecs: capecs,
        attacks: attacks
    }
"""
```

**Pattern 4: Batch Query**
```python
# Batch get CVE details
query = """
FOR vuln IN vulnerabilities
    FILTER vuln.cve_id IN @cve_ids
    RETURN vuln
"""
```

**Pattern 5: Subquery with FIRST (Latest EPSS)**
```python
# Get latest EPSS for CVE
query = """
FOR cve_id IN @cve_ids
    LET latest_epss = FIRST(
        FOR epss IN epss_history
            FILTER epss.cve_id == cve_id
            SORT epss.score_date DESC
            LIMIT 1
            RETURN epss
    )
    FILTER latest_epss != null
    RETURN latest_epss
"""
```

---

## 7. Error Handling Strategy

### 7.1 Graceful Degradation

**Principle:** Never fail entire enrichment if partial data missing

**Implementation:**
```python
# Good: Return null for missing data
enrichment = {
    "cve_details": cve_details or None,  # None if not found
    "epss": epss_score or None,
    "kev_status": kev_status or {"in_kev": False},
    "threat_intel": threat_intel or None
}

# Bad: Raise exception if EPSS missing
if not epss_score:
    raise ValueError("EPSS data not found")  # ❌ Don't do this
```

---

### 7.2 Error Categories

| Error Category | Handling Strategy | HTTP Status |
|----------------|-------------------|-------------|
| Scan session not found | Return 404 with error message | 404 |
| Customer unauthorized | Return 401 (handled by auth middleware) | 401 |
| Reference DB connection error | Return 503 with retry message | 503 |
| Partial enrichment data missing | Log warning, return partial enrichment | 200 |
| Invalid request (bad scan_session_id format) | Return 400 with validation error | 400 |

---

## 8. Performance Optimization

### 8.1 Batch Queries

**Problem:** Enriching 100 findings = 100 * 4 queries = 400 queries (slow)

**Solution:** Batch queries
```python
# Bad: N queries (1 per finding)
for finding in findings:
    cve_details = repo.get_cve_details(finding.cve_id)  # N queries

# Good: 1 batch query
cve_ids = [f.cve_id for f in findings]
cve_details_map = repo.batch_get_cve_details(cve_ids)  # 1 query
```

**Expected Performance:**
- 100 findings with batch queries: ~2-3 seconds ✅
- 100 findings without batch queries: ~20-30 seconds ❌

---

### 8.2 Query Optimization

**Use AQL best practices:**
1. **Filter early** - FILTER before joins
2. **Limit results** - Use LIMIT for top-N queries
3. **Use indexes** - Ensure cve_id, cwe_id indexed
4. **Avoid nested loops** - Use LET subqueries

---

## 9. Implementation Order

**Phase 2a: /v1/enrich** (Days 1-4)
1. Day 1-2: EnrichmentRepository + AQL queries
2. Day 3: EnrichmentService
3. Day 4: API endpoint + request/response models

**Phase 2b: /v1/compact** (Days 5-7)
4. Day 5-6: CWERepository + CompactionService
5. Day 7: API endpoint

**Phase 2c: /v1/map-controls** (Days 8-10)
6. Day 8-9: RegulatoryRepository + ControlMappingService
7. Day 10: API endpoint

**Testing** (Days 11-13)
8. Day 11-12: Unit tests (repositories, services)
9. Day 13: Integration + performance tests

---

## 10. Backward Compatibility

**No breaking changes:**
- Phase 1 endpoints unchanged
- New endpoints added (/v1/enrich, /v1/compact, /v1/map-controls)
- scan_findings collection not modified (read-only)

---

## 11. Testing Strategy

### 11.1 Unit Tests

**Repository Tests:**
- Mock ArangoDB queries
- Test AQL query construction
- Test model conversion (dict → Pydantic)

**Service Tests:**
- Mock repositories
- Test business logic
- Test error handling (missing data)

### 11.2 Integration Tests

**End-to-end tests:**
- Real database queries (test reference DB)
- Test full enrichment pipeline
- Test performance (AC-005: <5s for 100 findings)

---

## 12. Open Design Questions

(None - all resolved in requirements)

---

## Design Sign-Off

**Design Complete:** Ready for Stage 4 (Runtime Modeling)

**Next Step:** Create `future-state-runtime-call-stack.md` with detailed call stacks for:
1. /v1/enrich flow
2. /v1/compact flow
3. /v1/map-controls flow
4. Batch query optimization patterns
