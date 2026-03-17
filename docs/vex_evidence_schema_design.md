# Regulatory-Grade VEX Evidence Schema Design

**Version:** 1.0
**Date:** 2026-03-06
**Status:** Design Specification
**Compliance Targets:** FDA 524B, EU CRA, IEC 62304

## Executive Summary

This document specifies a complete, production-ready evidence-grounding system for VEX (Vulnerability Exploitability eXchange) generation that meets regulatory requirements by enforcing structured evidence collection from the knowledge graph before any LLM assessment.

### Key Design Principles

1. **Evidence First**: Collect all evidence from graph before LLM involvement
2. **Structured Output**: Pydantic schemas enforce compliance - no free-form JSON
3. **Auditable Chain**: Full graph traversal provenance (CVE→CWE→CAPEC→ATT&CK→NIST)
4. **Multi-Format**: Support both CycloneDX VEX and CSAF 2.0
5. **Regulatory Grade**: Meets FDA/CRA evidence requirements

## Architecture Overview

```
┌────────────────────────────────────────────────────────────────┐
│                  VEX Generation Pipeline                       │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  1. Evidence Collection Service                                │
│     ├─ CVE Metadata (CVSS, description)                        │
│     ├─ Graph Traversals (CVE→CWE→CAPEC→ATT&CK→NIST)           │
│     ├─ KEV Status Check                                        │
│     ├─ EPSS Score Retrieval                                    │
│     ├─ Component Presence Validation                           │
│     └─ Regulatory Violations                                   │
│                                                                │
│  2. Evidence Validation Layer                                  │
│     ├─ Tier 1 Completeness (Critical evidence present)         │
│     ├─ Graph Reference Integrity (documents exist)             │
│     ├─ Evidence Consistency (no contradictions)                │
│     └─ Regulatory Requirements (FDA/CRA)                       │
│                                                                │
│  3. VEX Synthesizer V2 (LLM with Evidence)                     │
│     ├─ Receives structured evidence (not free-form)            │
│     ├─ Generates assessment with evidence citations            │
│     ├─ Enforces Pydantic output schema                         │
│     └─ Validates completeness before return                    │
│                                                                │
│  4. Multi-Format Output                                        │
│     ├─ CycloneDX VEX 1.5 Formatter                             │
│     └─ CSAF 2.0 Formatter                                      │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

## Evidence Tier Classification

### Tier 1 - Critical (Always Required)

These evidence types are **mandatory** for regulatory compliance:

| Evidence Type | Description | Graph Query | Validation Rule |
|--------------|-------------|-------------|-----------------|
| **CVE Metadata** | CVSS score, severity, description | Direct lookup in `vulnerabilities` | Must have CVSS v3.x score |
| **CWE Mapping** | Weakness classification | `vulnerabilities→has_weakness→cwes` | At least 1 CWE required |
| **KEV Status** | CISA Known Exploited Vulnerabilities | `vulnerabilities→exploited_in_wild→kev_entries` | Boolean (in KEV or not) |
| **Component Presence** | Vulnerable component in SBOM | Match PURL in customer `components` | Must validate against SBOM |
| **Exploitability** | EPSS score, exploit availability | `vulnerabilities→has_epss→epss_scores` | EPSS score (0-1) required |

### Tier 2 - Important (Regulatory Preference)

These evidence types strengthen regulatory compliance:

| Evidence Type | Description | Graph Query | Validation Rule |
|--------------|-------------|-------------|-----------------|
| **Attack Techniques** | ATT&CK techniques that exploit this weakness | `CVE→CWE→CAPEC→ATT&CK` | List of technique IDs |
| **Mitigation Controls** | NIST 800-53 controls that mitigate | `ATT&CK→technique_mitigated_by_control→oscal_controls` | List of control IDs |
| **Remediation Path** | Patches, upgrades, workarounds | Check `fix_versions`, advisories | Available/Not Available |
| **Impact Analysis** | Regulatory requirements violated | `vulnerabilities→violates_requirement→requirements` | List of violated requirements |

### Tier 3 - Advanced (Future Enhancement)

Not yet implemented in v1.0:

- Reachability analysis (call graph paths)
- Binary analysis (function presence checks)
- Runtime configuration analysis

## File Specifications

### 1. Evidence Schema Models

**File:** `/Users/venkatapydialli/Documents/cybersecurity-compliance-app/src/complira_graph/models/vex_evidence.py`

Complete Pydantic models for evidence collection:

```python
"""
VEX Evidence Models (Regulatory-Grade).

Provides structured evidence collection for VEX generation.
Enforces FDA 524B, EU CRA, and IEC 62304 compliance requirements.

Key Features:
- Tiered evidence classification (Tier 1/2/3)
- Full graph traversal provenance
- Multi-format support (CycloneDX + CSAF)
- Auditability and validation

Usage:
    from complira_graph.models.vex_evidence import (
        VEXAssessment,
        VulnerabilityEvidence,
        GraphEvidence,
    )

    # Collect evidence
    evidence = VulnerabilityEvidence(
        cve_metadata=CVEMetadata(...),
        cwe_evidence=CWEEvidence(...),
        kev_evidence=KEVEvidence(...),
    )

    # Generate VEX assessment
    assessment = VEXAssessment(
        vulnerability_id="CVE-2021-44228",
        component_purl="pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
        evidence=evidence,
        status="affected",
    )
"""

from typing import List, Dict, Optional, Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field, validator
from enum import Enum


# ========== Evidence Tier Classification ==========

class EvidenceTier(str, Enum):
    """Evidence tier classification."""
    TIER_1_CRITICAL = "tier_1_critical"  # Mandatory for compliance
    TIER_2_IMPORTANT = "tier_2_important"  # Regulatory preference
    TIER_3_ADVANCED = "tier_3_advanced"  # Future enhancement


# ========== Tier 1 Evidence Models (Critical) ==========

class CVEMetadata(BaseModel):
    """
    CVE metadata evidence (Tier 1 - Critical).

    Regulatory Requirement: FDA 524B requires CVSS scoring and severity classification.
    """
    cve_id: str = Field(description="CVE identifier (e.g., CVE-2021-44228)")
    description: str = Field(description="CVE description from NVD")
    cvss_v3_score: Optional[float] = Field(None, ge=0.0, le=10.0, description="CVSS v3.x base score")
    cvss_v3_vector: Optional[str] = Field(None, description="CVSS v3.x vector string")
    cvss_v3_severity: Optional[str] = Field(None, description="CRITICAL | HIGH | MEDIUM | LOW")
    cvss_v2_score: Optional[float] = Field(None, ge=0.0, le=10.0, description="CVSS v2 score (fallback)")
    published_date: Optional[datetime] = Field(None, description="CVE publication date")
    last_modified_date: Optional[datetime] = Field(None, description="CVE last modified date")

    # Graph provenance
    graph_id: str = Field(description="ArangoDB document _id (e.g., vulnerabilities/cve-2021-44228)")

    @validator('cvss_v3_score', 'cvss_v2_score')
    def validate_cvss_present(cls, v, values):
        """At least one CVSS score must be present."""
        if 'cvss_v3_score' in values and values['cvss_v3_score'] is None and v is None:
            raise ValueError("At least one CVSS score (v3 or v2) is required")
        return v


class CWEEvidence(BaseModel):
    """
    CWE weakness mapping evidence (Tier 1 - Critical).

    Regulatory Requirement: CRA requires weakness classification for risk assessment.
    """
    cwe_id: str = Field(description="CWE identifier (e.g., CWE-502)")
    name: str = Field(description="CWE name (e.g., 'Deserialization of Untrusted Data')")
    description: str = Field(description="CWE description")
    weakness_type: Optional[str] = Field(None, description="Class | Base | Variant | Compound")
    likelihood: Optional[str] = Field(None, description="HIGH | MEDIUM | LOW")

    # Graph provenance
    graph_id: str = Field(description="ArangoDB document _id (e.g., cwes/CWE-502)")
    edge_id: str = Field(description="Edge _id linking CVE to CWE (has_weakness edge)")


class KEVEvidence(BaseModel):
    """
    CISA Known Exploited Vulnerabilities evidence (Tier 1 - Critical).

    Regulatory Requirement: FDA 524B prioritizes KEV vulnerabilities for remediation.
    """
    in_kev: bool = Field(description="Is this CVE in CISA KEV catalog?")
    kev_date_added: Optional[datetime] = Field(None, description="Date added to KEV")
    kev_due_date: Optional[datetime] = Field(None, description="KEV remediation deadline")
    kev_required_action: Optional[str] = Field(None, description="Required action from CISA")
    kev_known_ransomware: Optional[bool] = Field(None, description="Known ransomware campaign use")

    # Graph provenance (if in KEV)
    kev_graph_id: Optional[str] = Field(None, description="KEV document _id if present")


class ComponentPresenceEvidence(BaseModel):
    """
    Component presence validation (Tier 1 - Critical).

    Regulatory Requirement: VEX must confirm vulnerable component is actually in SBOM.
    """
    component_purl: str = Field(description="Package URL of component")
    component_name: str = Field(description="Component name")
    component_version: str = Field(description="Component version")
    in_sbom: bool = Field(description="Is component present in SBOM?")

    # SBOM reference
    sbom_component_id: Optional[str] = Field(None, description="Component _id in customer database")

    # Deployment context
    deployment_scope: Optional[str] = Field(None, description="production | staging | development")
    deployment_criticality: Optional[str] = Field(None, description="critical | high | medium | low")


class ExploitabilityEvidence(BaseModel):
    """
    Exploitability evidence (Tier 1 - Critical).

    Regulatory Requirement: FDA/CRA require exploit probability assessment.
    """
    epss_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="EPSS probability score (0-1)")
    epss_percentile: Optional[float] = Field(None, ge=0.0, le=1.0, description="EPSS percentile (0-1)")
    epss_date: Optional[datetime] = Field(None, description="EPSS score date")

    exploit_available: Optional[bool] = Field(None, description="Public exploit code available?")
    exploit_maturity: Optional[str] = Field(None, description="unproven | poc | functional | high")

    # Graph provenance
    epss_graph_id: Optional[str] = Field(None, description="EPSS document _id")


# ========== Tier 2 Evidence Models (Important) ==========

class AttackTechniqueEvidence(BaseModel):
    """
    ATT&CK technique evidence (Tier 2 - Important).

    Regulatory Requirement: CRA recommends attack technique correlation.
    """
    technique_id: str = Field(description="ATT&CK technique ID (e.g., T1190)")
    technique_name: str = Field(description="Technique name (e.g., 'Exploit Public-Facing Application')")
    tactic: str = Field(description="ATT&CK tactic (e.g., 'Initial Access')")
    description: str = Field(description="Technique description")

    # Graph provenance (full chain)
    technique_graph_id: str = Field(description="ATT&CK technique _id")
    capec_id: Optional[str] = Field(None, description="Intermediate CAPEC pattern (e.g., CAPEC-248)")
    capec_graph_id: Optional[str] = Field(None, description="CAPEC document _id")

    # Traversal path
    graph_path: List[str] = Field(
        description="Full graph path: [CVE_id, CWE_id, CAPEC_id, ATTACK_id]",
        example=["vulnerabilities/cve-2021-44228", "cwes/CWE-502", "capecs/CAPEC-248", "attack_techniques/T1190"]
    )


class MitigationControlEvidence(BaseModel):
    """
    Mitigation control evidence (Tier 2 - Important).

    Regulatory Requirement: FDA 524B requires documented mitigations.
    """
    control_id: str = Field(description="Control identifier (e.g., AC-3, SI-10)")
    control_title: str = Field(description="Control title")
    framework: str = Field(description="Control framework (NIST_800_53 | ISO_27001 | IEC_62443)")
    control_family: Optional[str] = Field(None, description="Control family (e.g., Access Control)")

    mitigation_effectiveness: Optional[str] = Field(
        None,
        description="complete | partial | minimal"
    )

    # Graph provenance
    control_graph_id: str = Field(description="Control document _id")

    # Traversal path
    graph_path: List[str] = Field(
        description="Full graph path: [CVE_id, ..., ATTACK_id, CONTROL_id]"
    )


class RemediationEvidence(BaseModel):
    """
    Remediation path evidence (Tier 2 - Important).

    Regulatory Requirement: FDA 524B requires remediation plan.
    """
    fix_available: bool = Field(description="Is fix/patch available?")
    fix_version: Optional[str] = Field(None, description="Fixed version (if available)")
    upgrade_path: Optional[str] = Field(None, description="Recommended upgrade path")
    workaround_available: bool = Field(default=False, description="Is workaround available?")
    workaround_description: Optional[str] = Field(None, description="Workaround description")

    vendor_advisory_url: Optional[str] = Field(None, description="Vendor security advisory URL")
    patch_complexity: Optional[str] = Field(None, description="low | medium | high")


class ComplianceViolationEvidence(BaseModel):
    """
    Regulatory requirement violation evidence (Tier 2 - Important).

    Regulatory Requirement: CRA requires mapping to compliance obligations.
    """
    requirement_id: str = Field(description="Requirement identifier (e.g., CRA_I_1_a)")
    requirement_title: str = Field(description="Requirement title")
    framework: str = Field(description="Regulatory framework (CRA | FDA_524B | IEC_62304)")
    obligation_level: str = Field(description="shall | should | may")

    deadline: Optional[datetime] = Field(None, description="Compliance deadline")
    violation_severity: Optional[str] = Field(None, description="critical | high | medium | low")

    # Graph provenance
    requirement_graph_id: str = Field(description="Requirement document _id")
    violation_edge_id: str = Field(description="violates_requirement edge _id")


# ========== Composite Evidence Container ==========

class GraphEvidence(BaseModel):
    """
    Graph traversal evidence container.

    Contains all evidence derived from knowledge graph traversals.
    """
    # Tier 1 (Critical)
    cwe_mappings: List[CWEEvidence] = Field(default_factory=list, description="CWE weaknesses")
    kev_evidence: KEVEvidence = Field(description="KEV status")
    component_presence: ComponentPresenceEvidence = Field(description="Component presence validation")
    exploitability: ExploitabilityEvidence = Field(description="Exploitability metrics")

    # Tier 2 (Important)
    attack_techniques: List[AttackTechniqueEvidence] = Field(default_factory=list, description="ATT&CK techniques")
    mitigation_controls: List[MitigationControlEvidence] = Field(default_factory=list, description="Mitigations")
    remediation: Optional[RemediationEvidence] = None
    compliance_violations: List[ComplianceViolationEvidence] = Field(default_factory=list, description="Violations")

    # Collection metadata
    collection_timestamp: datetime = Field(default_factory=datetime.utcnow, description="When evidence was collected")
    evidence_completeness: str = Field(description="complete | partial | incomplete")


class VulnerabilityEvidence(BaseModel):
    """
    Complete vulnerability evidence package.

    Aggregates all evidence for a single CVE affecting a component.
    """
    # Tier 1 (Critical)
    cve_metadata: CVEMetadata = Field(description="CVE metadata")
    graph_evidence: GraphEvidence = Field(description="Graph-derived evidence")

    # Evidence validation
    tier_1_complete: bool = Field(description="All Tier 1 evidence collected?")
    tier_2_complete: bool = Field(description="All Tier 2 evidence collected?")

    # Provenance
    evidence_version: str = Field(default="1.0", description="Evidence schema version")
    collection_method: str = Field(default="graph_traversal", description="How evidence was collected")


# ========== VEX Status Enums ==========

class VEXStatus(str, Enum):
    """
    VEX vulnerability status (CycloneDX + CSAF compatible).
    """
    AFFECTED = "affected"
    NOT_AFFECTED = "not_affected"
    UNDER_INVESTIGATION = "under_investigation"
    FIXED = "fixed"


class VEXJustification(str, Enum):
    """
    VEX justification for not_affected status (CycloneDX).
    """
    VULNERABLE_CODE_NOT_PRESENT = "vulnerable_code_not_present"
    VULNERABLE_CODE_NOT_IN_EXECUTE_PATH = "vulnerable_code_not_in_execute_path"
    VULNERABLE_CODE_CANNOT_BE_CONTROLLED_BY_ADVERSARY = "vulnerable_code_cannot_be_controlled_by_adversary"
    INLINE_MITIGATIONS_ALREADY_EXIST = "inline_mitigations_already_exist"


class VEXResponse(str, Enum):
    """
    VEX response actions (CycloneDX).
    """
    CAN_NOT_FIX = "can_not_fix"
    WILL_NOT_FIX = "will_not_fix"
    UPDATE = "update"
    ROLLBACK = "rollback"
    WORKAROUND_AVAILABLE = "workaround_available"


# ========== VEX Assessment Model ==========

class VEXAssessment(BaseModel):
    """
    Complete VEX assessment with evidence.

    This is the final output model that includes both the assessment
    and the complete evidence chain.
    """
    # Identification
    vulnerability_id: str = Field(description="CVE identifier")
    component_purl: str = Field(description="Component PURL")

    # Assessment
    status: VEXStatus = Field(description="Vulnerability status")
    justification: Optional[VEXJustification] = Field(None, description="Justification if not_affected")
    response: List[VEXResponse] = Field(default_factory=list, description="Response actions")

    # Evidence (Complete Chain)
    evidence: VulnerabilityEvidence = Field(description="Complete evidence package")

    # LLM-Generated Analysis (With Evidence Citations)
    impact_summary: str = Field(description="Human-readable impact summary")
    exploitability_analysis: str = Field(description="Exploitability analysis with evidence citations")
    mitigation_recommendations: List[str] = Field(default_factory=list, description="Recommended mitigations")

    # Evidence Citations (References to specific evidence items)
    evidence_citations: List[str] = Field(
        default_factory=list,
        description="Evidence item IDs cited in analysis",
        example=["cve_metadata", "kev_evidence", "attack_techniques[0]", "mitigation_controls[1]"]
    )

    # Regulatory Compliance
    regulatory_impact: Optional[str] = Field(None, description="Regulatory impact assessment")
    compliance_deadline: Optional[datetime] = Field(None, description="Soonest compliance deadline")

    # Metadata
    assessment_timestamp: datetime = Field(default_factory=datetime.utcnow)
    assessment_version: str = Field(default="2.0", description="VEX assessment version")
    generated_by: str = Field(default="complira_vex_v2", description="Generator identifier")

    # LLM Provenance
    llm_model: Optional[str] = Field(None, description="LLM model used for analysis")
    llm_tokens: Optional[Dict[str, int]] = Field(None, description="Token usage")


# ========== Multi-Format Output Models ==========

class CycloneDXVEX(BaseModel):
    """
    CycloneDX VEX 1.5 output format.
    """
    bomFormat: Literal["CycloneDX"] = "CycloneDX"
    specVersion: Literal["1.5"] = "1.5"
    version: int = Field(default=1, description="Document version")

    metadata: Dict[str, Any] = Field(description="Metadata including component info")
    vulnerabilities: List[Dict[str, Any]] = Field(description="Vulnerability assessments")

    # Complira extension
    evidence_package: Optional[VulnerabilityEvidence] = Field(
        None,
        description="Complete evidence package (Complira extension for auditability)"
    )


class CSAFVEX(BaseModel):
    """
    CSAF 2.0 VEX output format.
    """
    document: Dict[str, Any] = Field(description="CSAF document metadata")
    product_tree: Dict[str, Any] = Field(description="Product tree")
    vulnerabilities: List[Dict[str, Any]] = Field(description="Vulnerability assessments")

    # Evidence in notes section (CSAF pattern)
    notes: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Evidence notes for auditability"
    )


# ========== Validation Result Model ==========

class EvidenceValidationResult(BaseModel):
    """
    Evidence validation result.
    """
    valid: bool = Field(description="Overall validation status")
    tier_1_valid: bool = Field(description="Tier 1 evidence complete and valid")
    tier_2_valid: bool = Field(description="Tier 2 evidence complete and valid")

    missing_evidence: List[str] = Field(default_factory=list, description="Missing evidence types")
    invalid_references: List[str] = Field(default_factory=list, description="Invalid graph references")
    inconsistencies: List[str] = Field(default_factory=list, description="Evidence inconsistencies")

    regulatory_compliance: Dict[str, bool] = Field(
        default_factory=dict,
        description="Compliance status per framework",
        example={"FDA_524B": True, "CRA": True, "IEC_62304": False}
    )

    validation_timestamp: datetime = Field(default_factory=datetime.utcnow)


# ========== Export All Models ==========

__all__ = [
    "EvidenceTier",
    "CVEMetadata",
    "CWEEvidence",
    "KEVEvidence",
    "ComponentPresenceEvidence",
    "ExploitabilityEvidence",
    "AttackTechniqueEvidence",
    "MitigationControlEvidence",
    "RemediationEvidence",
    "ComplianceViolationEvidence",
    "GraphEvidence",
    "VulnerabilityEvidence",
    "VEXStatus",
    "VEXJustification",
    "VEXResponse",
    "VEXAssessment",
    "CycloneDXVEX",
    "CSAFVEX",
    "EvidenceValidationResult",
]
```

### 2. Evidence Collection Service

**File:** `/Users/venkatapydialli/Documents/cybersecurity-compliance-app/src/api/services/vex_evidence.py`

Service for collecting evidence from the knowledge graph:

```python
"""
VEX Evidence Collection Service.

Queries the knowledge graph to collect structured evidence for VEX generation.
Implements the "Evidence First" pattern - all evidence is collected before
LLM involvement.

SOLID Principles:
- SRP: Only evidence collection, no VEX formatting or LLM synthesis
- OCP: Extensible for new evidence types
- DIP: Depends on BaseGraphService abstraction

Usage:
    from api.services.vex_evidence import VEXEvidenceCollectionService

    service = VEXEvidenceCollectionService(db, cache)

    evidence = await service.collect_evidence(
        cve_id="CVE-2021-44228",
        component_purl="pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
        customer_id="customer_123"
    )
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import structlog

from api.services.base import BaseGraphService
from complira_graph.models.vex_evidence import (
    VulnerabilityEvidence,
    GraphEvidence,
    CVEMetadata,
    CWEEvidence,
    KEVEvidence,
    ComponentPresenceEvidence,
    ExploitabilityEvidence,
    AttackTechniqueEvidence,
    MitigationControlEvidence,
    RemediationEvidence,
    ComplianceViolationEvidence,
)

logger = structlog.get_logger()


class VEXEvidenceCollectionService(BaseGraphService):
    """
    Service for collecting VEX evidence from knowledge graph.

    Extends BaseGraphService to inherit graph traversal patterns.
    """

    async def collect_evidence(
        self,
        cve_id: str,
        component_purl: str,
        customer_id: Optional[str] = None,
        include_tier_2: bool = True,
    ) -> VulnerabilityEvidence:
        """
        Collect complete evidence package for a CVE affecting a component.

        This is the main entry point for evidence collection.

        Args:
            cve_id: CVE identifier (e.g., "CVE-2021-44228")
            component_purl: Component PURL
            customer_id: Customer ID for SBOM validation
            include_tier_2: Include Tier 2 evidence (default: True)

        Returns:
            VulnerabilityEvidence: Complete evidence package

        Flow:
            1. Collect CVE metadata (Tier 1)
            2. Collect graph evidence (Tier 1 + Tier 2)
            3. Validate evidence completeness
            4. Return evidence package
        """
        self.logger.info(
            "Collecting VEX evidence",
            cve_id=cve_id,
            component_purl=component_purl,
        )

        # Step 1: Collect CVE metadata
        cve_metadata = await self._collect_cve_metadata(cve_id)

        # Step 2: Collect graph evidence
        graph_evidence = await self._collect_graph_evidence(
            cve_id=cve_id,
            component_purl=component_purl,
            customer_id=customer_id,
            include_tier_2=include_tier_2,
        )

        # Step 3: Validate completeness
        tier_1_complete = self._validate_tier_1_completeness(cve_metadata, graph_evidence)
        tier_2_complete = self._validate_tier_2_completeness(graph_evidence) if include_tier_2 else False

        # Step 4: Build evidence package
        evidence = VulnerabilityEvidence(
            cve_metadata=cve_metadata,
            graph_evidence=graph_evidence,
            tier_1_complete=tier_1_complete,
            tier_2_complete=tier_2_complete,
        )

        self.logger.info(
            "Evidence collection complete",
            cve_id=cve_id,
            tier_1_complete=tier_1_complete,
            tier_2_complete=tier_2_complete,
        )

        return evidence

    # ========== Tier 1 Evidence Collection (Critical) ==========

    async def _collect_cve_metadata(self, cve_id: str) -> CVEMetadata:
        """
        Collect CVE metadata from vulnerabilities collection.

        Args:
            cve_id: CVE identifier

        Returns:
            CVEMetadata: CVE metadata evidence
        """
        query = """
        FOR vuln IN vulnerabilities
            FILTER vuln.cve_id == @cve_id
            LIMIT 1
            RETURN vuln
        """

        cursor = self.db.aql_execute(query, bind_vars={"cve_id": cve_id.upper()})
        results = list(cursor)

        if not results:
            raise ValueError(f"CVE not found: {cve_id}")

        vuln = results[0]

        return CVEMetadata(
            cve_id=vuln["cve_id"],
            description=vuln.get("description", ""),
            cvss_v3_score=vuln.get("cvss_v3_score"),
            cvss_v3_vector=vuln.get("cvss_v3_vector"),
            cvss_v3_severity=vuln.get("cvss_v3_severity"),
            cvss_v2_score=vuln.get("cvss_v2_score"),
            published_date=vuln.get("published_date"),
            last_modified_date=vuln.get("last_modified_date"),
            graph_id=vuln["_id"],
        )

    async def _collect_graph_evidence(
        self,
        cve_id: str,
        component_purl: str,
        customer_id: Optional[str],
        include_tier_2: bool,
    ) -> GraphEvidence:
        """
        Collect all graph-derived evidence.

        Orchestrates parallel collection of:
        - CWE mappings
        - KEV status
        - Component presence
        - Exploitability
        - Attack techniques (if Tier 2)
        - Mitigation controls (if Tier 2)
        - Remediation (if Tier 2)
        - Compliance violations (if Tier 2)

        Args:
            cve_id: CVE identifier
            component_purl: Component PURL
            customer_id: Customer ID
            include_tier_2: Include Tier 2 evidence

        Returns:
            GraphEvidence: Complete graph evidence
        """
        # Normalize CVE key
        cve_key = cve_id.lower().replace("cve-", "cve-")

        # Tier 1 collection (parallel)
        cwe_mappings = await self._collect_cwe_mappings(cve_key)
        kev_evidence = await self._collect_kev_evidence(cve_key)
        component_presence = await self._collect_component_presence(component_purl, customer_id)
        exploitability = await self._collect_exploitability_evidence(cve_key)

        # Tier 2 collection (if requested)
        attack_techniques = []
        mitigation_controls = []
        remediation = None
        compliance_violations = []

        if include_tier_2:
            attack_techniques = await self._collect_attack_techniques(cve_key)
            mitigation_controls = await self._collect_mitigation_controls(attack_techniques)
            remediation = await self._collect_remediation_evidence(component_purl)
            compliance_violations = await self._collect_compliance_violations(cve_key)

        # Determine completeness
        completeness = self._determine_evidence_completeness(
            cwe_mappings=cwe_mappings,
            kev_evidence=kev_evidence,
            exploitability=exploitability,
            include_tier_2=include_tier_2,
            attack_techniques=attack_techniques,
        )

        return GraphEvidence(
            cwe_mappings=cwe_mappings,
            kev_evidence=kev_evidence,
            component_presence=component_presence,
            exploitability=exploitability,
            attack_techniques=attack_techniques,
            mitigation_controls=mitigation_controls,
            remediation=remediation,
            compliance_violations=compliance_violations,
            evidence_completeness=completeness,
        )

    async def _collect_cwe_mappings(self, cve_key: str) -> List[CWEEvidence]:
        """
        Collect CWE mappings via has_weakness edges.

        AQL Query Pattern:
            CVE → has_weakness → CWE

        Args:
            cve_key: CVE document _key

        Returns:
            list[CWEEvidence]: CWE evidence items
        """
        query = """
        FOR vuln IN vulnerabilities
            FILTER vuln._key == @cve_key
            FOR cwe, edge IN 1..1 OUTBOUND vuln has_weakness
                RETURN {
                    cwe: cwe,
                    edge: edge
                }
        """

        cursor = self.db.aql_execute(query, bind_vars={"cve_key": cve_key})
        results = list(cursor)

        cwe_evidence = []
        for result in results:
            cwe = result["cwe"]
            edge = result["edge"]

            cwe_evidence.append(
                CWEEvidence(
                    cwe_id=cwe["cwe_id"],
                    name=cwe.get("name", ""),
                    description=cwe.get("description", ""),
                    weakness_type=cwe.get("weakness_type"),
                    likelihood=cwe.get("likelihood"),
                    graph_id=cwe["_id"],
                    edge_id=edge["_id"],
                )
            )

        self.logger.debug("Collected CWE mappings", cve_key=cve_key, count=len(cwe_evidence))

        return cwe_evidence

    async def _collect_kev_evidence(self, cve_key: str) -> KEVEvidence:
        """
        Check KEV catalog membership.

        AQL Query Pattern:
            CVE → exploited_in_wild → KEV (if exists)

        Args:
            cve_key: CVE document _key

        Returns:
            KEVEvidence: KEV status evidence
        """
        query = """
        FOR vuln IN vulnerabilities
            FILTER vuln._key == @cve_key
            LET kev = FIRST(
                FOR k IN 1..1 OUTBOUND vuln exploited_in_wild
                    RETURN k
            )
            RETURN {
                in_kev: kev != null,
                kev: kev
            }
        """

        cursor = self.db.aql_execute(query, bind_vars={"cve_key": cve_key})
        results = list(cursor)

        if not results:
            return KEVEvidence(in_kev=False)

        result = results[0]
        kev = result.get("kev")

        if not kev:
            return KEVEvidence(in_kev=False)

        return KEVEvidence(
            in_kev=True,
            kev_date_added=kev.get("date_added"),
            kev_due_date=kev.get("due_date"),
            kev_required_action=kev.get("required_action"),
            kev_known_ransomware=kev.get("known_ransomware_campaign_use"),
            kev_graph_id=kev["_id"],
        )

    async def _collect_component_presence(
        self,
        component_purl: str,
        customer_id: Optional[str],
    ) -> ComponentPresenceEvidence:
        """
        Validate component presence in SBOM.

        Queries customer database to verify component exists.

        Args:
            component_purl: Component PURL
            customer_id: Customer ID

        Returns:
            ComponentPresenceEvidence: Component presence validation
        """
        if not customer_id:
            # No customer context - cannot validate SBOM presence
            return ComponentPresenceEvidence(
                component_purl=component_purl,
                component_name=self._extract_name_from_purl(component_purl),
                component_version=self._extract_version_from_purl(component_purl),
                in_sbom=False,
            )

        # Query customer database
        from api.core.database import get_customer_db

        customer_db = get_customer_db(customer_id)

        query = """
        FOR component IN components
            FILTER component.purl == @purl
            LIMIT 1
            RETURN component
        """

        cursor = customer_db.aql_execute(query, bind_vars={"purl": component_purl})
        results = list(cursor)

        if not results:
            return ComponentPresenceEvidence(
                component_purl=component_purl,
                component_name=self._extract_name_from_purl(component_purl),
                component_version=self._extract_version_from_purl(component_purl),
                in_sbom=False,
            )

        component = results[0]

        return ComponentPresenceEvidence(
            component_purl=component_purl,
            component_name=component.get("name", ""),
            component_version=component.get("version", ""),
            in_sbom=True,
            sbom_component_id=component["_id"],
            deployment_scope=component.get("deployment_scope"),
            deployment_criticality=component.get("deployment_criticality"),
        )

    async def _collect_exploitability_evidence(self, cve_key: str) -> ExploitabilityEvidence:
        """
        Collect EPSS scores and exploit metadata.

        AQL Query Pattern:
            CVE → has_epss → EPSS

        Args:
            cve_key: CVE document _key

        Returns:
            ExploitabilityEvidence: Exploitability evidence
        """
        query = """
        FOR vuln IN vulnerabilities
            FILTER vuln._key == @cve_key
            LET epss = FIRST(
                FOR e IN 1..1 OUTBOUND vuln has_epss
                    SORT e.date DESC
                    LIMIT 1
                    RETURN e
            )
            RETURN {
                epss: epss,
                exploit_available: vuln.exploit_available,
                exploit_maturity: vuln.exploit_maturity
            }
        """

        cursor = self.db.aql_execute(query, bind_vars={"cve_key": cve_key})
        results = list(cursor)

        if not results:
            return ExploitabilityEvidence()

        result = results[0]
        epss = result.get("epss")

        if not epss:
            return ExploitabilityEvidence(
                exploit_available=result.get("exploit_available"),
                exploit_maturity=result.get("exploit_maturity"),
            )

        return ExploitabilityEvidence(
            epss_score=epss.get("epss"),
            epss_percentile=epss.get("percentile"),
            epss_date=epss.get("date"),
            exploit_available=result.get("exploit_available"),
            exploit_maturity=result.get("exploit_maturity"),
            epss_graph_id=epss["_id"],
        )

    # ========== Tier 2 Evidence Collection (Important) ==========

    async def _collect_attack_techniques(self, cve_key: str) -> List[AttackTechniqueEvidence]:
        """
        Collect ATT&CK techniques via graph traversal.

        AQL Query Pattern:
            CVE → has_weakness → CWE → capec_relates_to_cwe → CAPEC →
            capec_maps_to_attack → ATT&CK

        Args:
            cve_key: CVE document _key

        Returns:
            list[AttackTechniqueEvidence]: ATT&CK technique evidence
        """
        query = """
        FOR vuln IN vulnerabilities
            FILTER vuln._key == @cve_key
            FOR cwe IN 1..1 OUTBOUND vuln has_weakness
                FOR capec IN 1..1 INBOUND cwe capec_relates_to_cwe
                    FOR attack IN 1..1 OUTBOUND capec capec_maps_to_attack
                        RETURN DISTINCT {
                            cve_id: vuln._id,
                            cwe_id: cwe._id,
                            capec_id: capec._id,
                            capec_key: capec.capec_id,
                            attack_id: attack._id,
                            attack: attack
                        }
        """

        cursor = self.db.aql_execute(query, bind_vars={"cve_key": cve_key})
        results = list(cursor)

        attack_evidence = []
        for result in results:
            attack = result["attack"]

            attack_evidence.append(
                AttackTechniqueEvidence(
                    technique_id=attack.get("technique_id", ""),
                    technique_name=attack.get("name", ""),
                    tactic=attack.get("tactic", ""),
                    description=attack.get("description", ""),
                    technique_graph_id=result["attack_id"],
                    capec_id=result.get("capec_key"),
                    capec_graph_id=result.get("capec_id"),
                    graph_path=[
                        result["cve_id"],
                        result["cwe_id"],
                        result["capec_id"],
                        result["attack_id"],
                    ],
                )
            )

        self.logger.debug(
            "Collected ATT&CK techniques",
            cve_key=cve_key,
            count=len(attack_evidence),
        )

        return attack_evidence

    async def _collect_mitigation_controls(
        self,
        attack_techniques: List[AttackTechniqueEvidence],
    ) -> List[MitigationControlEvidence]:
        """
        Collect mitigation controls for ATT&CK techniques.

        AQL Query Pattern:
            ATT&CK → technique_mitigated_by_control → Control

        Args:
            attack_techniques: ATT&CK technique evidence

        Returns:
            list[MitigationControlEvidence]: Mitigation control evidence
        """
        if not attack_techniques:
            return []

        # Extract ATT&CK technique IDs
        technique_ids = [t.technique_graph_id for t in attack_techniques]

        query = """
        FOR technique_id IN @technique_ids
            FOR control IN 1..1 OUTBOUND technique_id technique_mitigated_by_control
                RETURN DISTINCT {
                    technique_id: technique_id,
                    control: control
                }
        """

        cursor = self.db.aql_execute(query, bind_vars={"technique_ids": technique_ids})
        results = list(cursor)

        control_evidence = []
        for result in results:
            control = result["control"]

            # Find the full path from attack technique evidence
            graph_path = []
            for tech in attack_techniques:
                if tech.technique_graph_id == result["technique_id"]:
                    graph_path = tech.graph_path + [control["_id"]]
                    break

            control_evidence.append(
                MitigationControlEvidence(
                    control_id=control.get("control_id", ""),
                    control_title=control.get("title", ""),
                    framework=control.get("framework", ""),
                    control_family=control.get("family"),
                    mitigation_effectiveness=control.get("mitigation_effectiveness"),
                    control_graph_id=control["_id"],
                    graph_path=graph_path,
                )
            )

        self.logger.debug("Collected mitigation controls", count=len(control_evidence))

        return control_evidence

    async def _collect_remediation_evidence(
        self,
        component_purl: str,
    ) -> Optional[RemediationEvidence]:
        """
        Collect remediation information for component.

        Checks for:
        - Fixed versions
        - Vendor advisories
        - Workarounds

        Args:
            component_purl: Component PURL

        Returns:
            RemediationEvidence: Remediation evidence or None
        """
        # TODO: Implement remediation collection
        # This requires:
        # 1. Vendor advisory parsing
        # 2. Fixed version tracking
        # 3. Workaround documentation

        # Placeholder for now
        return RemediationEvidence(
            fix_available=False,
            workaround_available=False,
        )

    async def _collect_compliance_violations(
        self,
        cve_key: str,
    ) -> List[ComplianceViolationEvidence]:
        """
        Collect regulatory requirement violations.

        AQL Query Pattern:
            CVE → violates_requirement → Requirement

        Args:
            cve_key: CVE document _key

        Returns:
            list[ComplianceViolationEvidence]: Compliance violation evidence
        """
        query = """
        FOR vuln IN vulnerabilities
            FILTER vuln._key == @cve_key
            FOR req, edge IN 1..1 OUTBOUND vuln violates_requirement
                RETURN {
                    requirement: req,
                    edge: edge
                }
        """

        cursor = self.db.aql_execute(query, bind_vars={"cve_key": cve_key})
        results = list(cursor)

        violation_evidence = []
        for result in results:
            req = result["requirement"]
            edge = result["edge"]

            violation_evidence.append(
                ComplianceViolationEvidence(
                    requirement_id=req.get("requirement_id", ""),
                    requirement_title=req.get("title", ""),
                    framework=req.get("framework", ""),
                    obligation_level=req.get("obligation_level", ""),
                    deadline=req.get("deadline"),
                    violation_severity=edge.get("severity"),
                    requirement_graph_id=req["_id"],
                    violation_edge_id=edge["_id"],
                )
            )

        self.logger.debug(
            "Collected compliance violations",
            cve_key=cve_key,
            count=len(violation_evidence),
        )

        return violation_evidence

    # ========== Helper Methods ==========

    def _validate_tier_1_completeness(
        self,
        cve_metadata: CVEMetadata,
        graph_evidence: GraphEvidence,
    ) -> bool:
        """
        Validate Tier 1 evidence completeness.

        Tier 1 Requirements:
        - CVE metadata with CVSS score
        - At least one CWE mapping
        - KEV evidence (even if not in KEV)
        - Component presence check
        - Exploitability evidence (EPSS preferred)

        Args:
            cve_metadata: CVE metadata
            graph_evidence: Graph evidence

        Returns:
            bool: True if Tier 1 complete
        """
        # Check CVE metadata
        if not cve_metadata.cvss_v3_score and not cve_metadata.cvss_v2_score:
            return False

        # Check CWE mappings
        if not graph_evidence.cwe_mappings:
            return False

        # KEV evidence always present (boolean)
        # Component presence always present (boolean)

        # Exploitability - prefer EPSS but not required
        # (Some CVEs don't have EPSS scores yet)

        return True

    def _validate_tier_2_completeness(self, graph_evidence: GraphEvidence) -> bool:
        """
        Validate Tier 2 evidence completeness.

        Tier 2 Requirements:
        - Attack techniques (if CWE → CAPEC → ATT&CK path exists)
        - Mitigation controls (if attack techniques exist)
        - Remediation evidence (optional)
        - Compliance violations (optional)

        Args:
            graph_evidence: Graph evidence

        Returns:
            bool: True if Tier 2 complete
        """
        # Tier 2 is "best effort" - not all CVEs have full chains
        # Return True if we have at least some Tier 2 evidence
        return bool(
            graph_evidence.attack_techniques
            or graph_evidence.mitigation_controls
            or graph_evidence.compliance_violations
        )

    def _determine_evidence_completeness(
        self,
        cwe_mappings: List[CWEEvidence],
        kev_evidence: KEVEvidence,
        exploitability: ExploitabilityEvidence,
        include_tier_2: bool,
        attack_techniques: List[AttackTechniqueEvidence],
    ) -> str:
        """
        Determine overall evidence completeness.

        Args:
            cwe_mappings: CWE evidence
            kev_evidence: KEV evidence
            exploitability: Exploitability evidence
            include_tier_2: Was Tier 2 requested?
            attack_techniques: Attack technique evidence

        Returns:
            str: "complete" | "partial" | "incomplete"
        """
        # Tier 1 check
        tier_1_complete = bool(cwe_mappings and kev_evidence)

        if not tier_1_complete:
            return "incomplete"

        if not include_tier_2:
            return "complete"

        # Tier 2 check
        tier_2_present = bool(attack_techniques)

        if tier_2_present:
            return "complete"
        else:
            return "partial"

    def _extract_name_from_purl(self, purl: str) -> str:
        """Extract component name from PURL."""
        # Simple extraction - production should use packageurl-python
        parts = purl.split("/")
        if len(parts) >= 2:
            name_version = parts[-1]
            return name_version.split("@")[0]
        return ""

    def _extract_version_from_purl(self, purl: str) -> str:
        """Extract version from PURL."""
        if "@" in purl:
            return purl.split("@")[-1]
        return ""


# ========== Export ==========

__all__ = ["VEXEvidenceCollectionService"]
```

---

*[Document continues in next section due to length...]*
