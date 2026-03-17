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
        graph_evidence=GraphEvidence(...),
        tier_1_complete=True,
        tier_2_complete=True,
    )

    # Generate VEX assessment
    assessment = VEXAssessment(
        vulnerability_id="CVE-2021-44228",
        component_purl="pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
        evidence=evidence,
        status="affected",
        impact_summary="Critical RCE vulnerability in Log4j",
        exploitability_analysis="EPSS 0.97, actively exploited in wild (KEV)",
    )

Author: Complira Development Team
Version: 1.0
Compliance: FDA 524B, EU CRA, IEC 62304
"""

from typing import List, Dict, Optional, Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, model_validator
from enum import Enum
import re


# ========== Evidence Tier Classification ==========


class EvidenceTier(str, Enum):
    """
    Evidence tier classification for VEX generation.

    Defines the importance and regulatory requirement level for evidence types.

    Tiers:
        - TIER_1_CRITICAL: Mandatory for regulatory compliance (FDA, CRA, IEC)
        - TIER_2_IMPORTANT: Strongly recommended, regulatory preference
        - TIER_3_ADVANCED: Future enhancement, not yet implemented
    """
    TIER_1_CRITICAL = "tier_1_critical"
    TIER_2_IMPORTANT = "tier_2_important"
    TIER_3_ADVANCED = "tier_3_advanced"


# ========== VEX Status Enums ==========


class VEXStatus(str, Enum):
    """
    VEX vulnerability status (CycloneDX + CSAF compatible).

    Defines the assessment status of a vulnerability affecting a component.

    Status Values:
        - affected: Component is vulnerable and affected
        - not_affected: Component contains vulnerability but is not affected
        - under_investigation: Status is being determined
        - fixed: Vulnerability has been remediated

    Standards Compliance:
        - CycloneDX VEX 1.5
        - CSAF 2.0
        - OpenVEX
    """
    AFFECTED = "affected"
    NOT_AFFECTED = "not_affected"
    UNDER_INVESTIGATION = "under_investigation"
    FIXED = "fixed"


class VEXJustification(str, Enum):
    """
    VEX justification for 'not_affected' status (CycloneDX).

    Provides specific reasoning when a component is not affected by a vulnerability.

    Justifications:
        - component_not_present: Vulnerable component is not included
        - vulnerable_code_not_present: Vulnerable code paths do not exist
        - vulnerable_code_not_in_execute_path: Code exists but never executes
        - vulnerable_code_cannot_be_controlled_by_adversary: Code runs but not exploitable
        - inline_mitigations_already_exist: Mitigations prevent exploitation

    Regulatory Significance:
        FDA 524B and EU CRA require documented justification for not_affected assessments.
    """
    COMPONENT_NOT_PRESENT = "component_not_present"
    VULNERABLE_CODE_NOT_PRESENT = "vulnerable_code_not_present"
    VULNERABLE_CODE_NOT_IN_EXECUTE_PATH = "vulnerable_code_not_in_execute_path"
    VULNERABLE_CODE_CANNOT_BE_CONTROLLED_BY_ADVERSARY = "vulnerable_code_cannot_be_controlled_by_adversary"
    INLINE_MITIGATIONS_ALREADY_EXIST = "inline_mitigations_already_exist"


class VEXResponse(str, Enum):
    """
    VEX response actions (CycloneDX).

    Defines the response strategy for an affected component.

    Response Actions:
        - can_not_fix: No fix is possible
        - will_not_fix: Fix exists but will not be applied
        - update: Upgrade to fixed version
        - rollback: Downgrade to non-vulnerable version
        - workaround_available: Apply workaround mitigation

    Regulatory Significance:
        FDA 524B requires documented response plan for affected vulnerabilities.
    """
    CAN_NOT_FIX = "can_not_fix"
    WILL_NOT_FIX = "will_not_fix"
    UPDATE = "update"
    ROLLBACK = "rollback"
    WORKAROUND_AVAILABLE = "workaround_available"


# ========== Tier 1 Evidence Models (Critical) ==========


class CVEMetadata(BaseModel):
    """
    CVE metadata evidence (Tier 1 - Critical).

    Contains core vulnerability metadata from NVD/NIST sources.

    Regulatory Requirement:
        - FDA 524B: CVSS scoring and severity classification required
        - EU CRA: Vulnerability identification and assessment
        - IEC 62304: Risk assessment foundation

    Fields:
        - cve_id: CVE identifier in standard format
        - description: Detailed vulnerability description
        - cvss_v3_score: CVSS v3.x base score (0.0-10.0)
        - cvss_v3_vector: CVSS v3.x vector string
        - cvss_v3_severity: Severity rating (CRITICAL/HIGH/MEDIUM/LOW)
        - cvss_v2_score: Legacy CVSS v2 score (fallback)
        - published_date: Initial CVE publication date
        - last_modified_date: Most recent CVE update date
        - graph_id: ArangoDB document ID for provenance

    Example:
        >>> cve = CVEMetadata(
        ...     cve_id="CVE-2021-44228",
        ...     description="Apache Log4j2 remote code execution vulnerability",
        ...     cvss_v3_score=10.0,
        ...     cvss_v3_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H",
        ...     cvss_v3_severity="CRITICAL",
        ...     graph_id="vulnerabilities/CVE_2021_44228"
        ... )
    """
    cve_id: str = Field(
        description="CVE identifier (e.g., CVE-2021-44228)",
        examples=["CVE-2021-44228", "CVE-2024-1234"]
    )
    description: str = Field(
        description="CVE description from NVD",
        min_length=1
    )
    cvss_v3_score: Optional[float] = Field(
        None,
        ge=0.0,
        le=10.0,
        description="CVSS v3.x base score (0.0-10.0)"
    )
    cvss_v3_vector: Optional[str] = Field(
        None,
        description="CVSS v3.x vector string (e.g., CVSS:3.1/AV:N/AC:L/...)"
    )
    cvss_v3_severity: Optional[str] = Field(
        None,
        description="CVSS v3 severity rating",
        pattern="^(CRITICAL|HIGH|MEDIUM|LOW|NONE)$"
    )
    cvss_v2_score: Optional[float] = Field(
        None,
        ge=0.0,
        le=10.0,
        description="CVSS v2 base score (fallback)"
    )
    published_date: Optional[datetime] = Field(
        None,
        description="CVE publication date"
    )
    last_modified_date: Optional[datetime] = Field(
        None,
        description="CVE last modified date"
    )

    # Graph provenance
    graph_id: str = Field(
        description="ArangoDB document _id (e.g., vulnerabilities/CVE_2021_44228)",
        pattern="^vulnerabilities/.+$"
    )

    @field_validator('cve_id')
    @classmethod
    def validate_cve_format(cls, v: str) -> str:
        """Validate CVE ID format: CVE-YYYY-NNNNN."""
        if not re.match(r'^CVE-\d{4}-\d{4,}$', v.upper()):
            raise ValueError(f"Invalid CVE ID format: {v}. Expected CVE-YYYY-NNNNN")
        return v.upper()

    @model_validator(mode='after')
    def validate_cvss_present(self) -> 'CVEMetadata':
        """Ensure at least one CVSS score is present."""
        if self.cvss_v3_score is None and self.cvss_v2_score is None:
            raise ValueError("At least one CVSS score (v3 or v2) is required for regulatory compliance")
        return self

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "cve_id": "CVE-2021-44228",
                "description": "Apache Log4j2 2.0-beta9 through 2.15.0 JNDI features used in configuration, log messages, and parameters do not protect against attacker controlled LDAP and other JNDI related endpoints. An attacker who can control log messages or log message parameters can execute arbitrary code loaded from LDAP servers when message lookup substitution is enabled.",
                "cvss_v3_score": 10.0,
                "cvss_v3_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H",
                "cvss_v3_severity": "CRITICAL",
                "published_date": "2021-12-10T10:15:09Z",
                "last_modified_date": "2021-12-14T02:23:04Z",
                "graph_id": "vulnerabilities/CVE_2021_44228"
            }]
        }
    }


class CWEEvidence(BaseModel):
    """
    CWE weakness mapping evidence (Tier 1 - Critical).

    Links CVE to underlying software weakness classifications.

    Regulatory Requirement:
        - EU CRA: Weakness classification for risk assessment
        - IEC 62304: Root cause analysis for safety assessment

    Fields:
        - cwe_id: CWE identifier (e.g., CWE-502)
        - name: Human-readable CWE name
        - description: Detailed weakness description
        - weakness_type: Classification (Class/Base/Variant/Compound)
        - likelihood: Exploitation likelihood (HIGH/MEDIUM/LOW)
        - graph_id: CWE document ID in graph
        - edge_id: has_weakness edge ID for provenance

    Example:
        >>> cwe = CWEEvidence(
        ...     cwe_id="CWE-502",
        ...     name="Deserialization of Untrusted Data",
        ...     description="The application deserializes untrusted data without verification",
        ...     weakness_type="Base",
        ...     graph_id="cwes/CWE_502",
        ...     edge_id="has_weakness/12345"
        ... )
    """
    cwe_id: str = Field(
        description="CWE identifier (e.g., CWE-502)",
        pattern="^CWE-\\d+$"
    )
    name: str = Field(
        description="CWE name (e.g., 'Deserialization of Untrusted Data')",
        min_length=1
    )
    description: str = Field(
        description="CWE description",
        min_length=1
    )
    weakness_type: Optional[str] = Field(
        None,
        description="CWE abstraction level",
        pattern="^(Class|Base|Variant|Compound|Category)$"
    )
    likelihood: Optional[str] = Field(
        None,
        description="Exploitation likelihood rating",
        pattern="^(HIGH|MEDIUM|LOW)$"
    )

    # Graph provenance
    graph_id: str = Field(
        description="ArangoDB document _id (e.g., cwes/CWE_502)",
        pattern="^cwes/.+$"
    )
    edge_id: str = Field(
        description="Edge _id linking CVE to CWE (has_weakness edge)",
        pattern="^has_weakness/.+$"
    )

    @field_validator('cwe_id')
    @classmethod
    def validate_cwe_format(cls, v: str) -> str:
        """Validate CWE ID format: CWE-NNN."""
        if not re.match(r'^CWE-\d+$', v.upper()):
            raise ValueError(f"Invalid CWE ID format: {v}. Expected CWE-NNN")
        return v.upper()

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "cwe_id": "CWE-502",
                "name": "Deserialization of Untrusted Data",
                "description": "The software deserializes untrusted data without sufficiently verifying that the resulting data will be valid.",
                "weakness_type": "Base",
                "likelihood": "HIGH",
                "graph_id": "cwes/CWE_502",
                "edge_id": "has_weakness/cve_2021_44228_to_cwe_502"
            }]
        }
    }


class KEVEvidence(BaseModel):
    """
    CISA Known Exploited Vulnerabilities evidence (Tier 1 - Critical).

    Indicates whether CVE appears in CISA KEV catalog.

    Regulatory Requirement:
        - FDA 524B: KEV vulnerabilities require prioritized remediation
        - EU CRA: Known exploitation increases risk severity

    Fields:
        - in_kev: Boolean flag for KEV catalog membership
        - kev_date_added: Date vulnerability added to KEV
        - kev_due_date: CISA remediation deadline
        - kev_required_action: CISA-mandated remediation action
        - kev_known_ransomware: Associated with ransomware campaigns
        - kev_graph_id: KEV document ID (if in catalog)

    Example:
        >>> kev = KEVEvidence(
        ...     in_kev=True,
        ...     kev_date_added=datetime(2021, 12, 10),
        ...     kev_due_date=datetime(2021, 12, 24),
        ...     kev_required_action="Apply updates per vendor instructions",
        ...     kev_known_ransomware=True,
        ...     kev_graph_id="kev_entries/CVE_2021_44228"
        ... )
    """
    in_kev: bool = Field(
        description="Is this CVE in CISA KEV catalog?"
    )
    kev_date_added: Optional[datetime] = Field(
        None,
        description="Date added to KEV catalog"
    )
    kev_due_date: Optional[datetime] = Field(
        None,
        description="KEV remediation deadline (critical for compliance)"
    )
    kev_required_action: Optional[str] = Field(
        None,
        description="Required action from CISA (e.g., 'Apply updates per vendor instructions')"
    )
    kev_known_ransomware: Optional[bool] = Field(
        None,
        description="Known ransomware campaign use (critical threat indicator)"
    )

    # Graph provenance (if in KEV)
    kev_graph_id: Optional[str] = Field(
        None,
        description="KEV document _id if present (e.g., kev_entries/CVE_2021_44228)"
    )

    @model_validator(mode='after')
    def validate_kev_fields(self) -> 'KEVEvidence':
        """If in_kev is True, validate KEV fields are present."""
        if self.in_kev:
            if not self.kev_date_added:
                raise ValueError("kev_date_added required when in_kev is True")
            if not self.kev_due_date:
                raise ValueError("kev_due_date required when in_kev is True")
            if not self.kev_required_action:
                raise ValueError("kev_required_action required when in_kev is True")
        return self

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "in_kev": True,
                "kev_date_added": "2021-12-10T00:00:00Z",
                "kev_due_date": "2021-12-24T00:00:00Z",
                "kev_required_action": "Apply updates per vendor instructions",
                "kev_known_ransomware": True,
                "kev_graph_id": "kev_entries/CVE_2021_44228"
            }]
        }
    }


class ComponentPresenceEvidence(BaseModel):
    """
    Component presence validation (Tier 1 - Critical).

    Verifies vulnerable component exists in SBOM.

    Regulatory Requirement:
        - All VEX Formats: Must confirm component is actually present
        - FDA 524B: SBOM validation required
        - EU CRA: Component inventory verification

    Fields:
        - component_purl: Package URL (PURL) identifier
        - component_name: Human-readable component name
        - component_version: Specific version string
        - in_sbom: Boolean flag for SBOM presence
        - sbom_component_id: Component document ID in customer DB
        - deployment_scope: Deployment environment (production/staging/dev)
        - deployment_criticality: Business criticality (critical/high/medium/low)

    Example:
        >>> component = ComponentPresenceEvidence(
        ...     component_purl="pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
        ...     component_name="log4j-core",
        ...     component_version="2.14.1",
        ...     in_sbom=True,
        ...     sbom_component_id="components/log4j_core_2_14_1",
        ...     deployment_scope="production",
        ...     deployment_criticality="critical"
        ... )
    """
    component_purl: str = Field(
        description="Package URL of component (e.g., pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1)",
        min_length=1
    )
    component_name: str = Field(
        description="Component name (e.g., 'log4j-core')",
        min_length=1
    )
    component_version: str = Field(
        description="Component version (e.g., '2.14.1')",
        min_length=1
    )
    in_sbom: bool = Field(
        description="Is component present in SBOM?"
    )

    # SBOM reference
    sbom_component_id: Optional[str] = Field(
        None,
        description="Component _id in customer database (if in_sbom is True)"
    )

    # Deployment context
    deployment_scope: Optional[str] = Field(
        None,
        description="Deployment environment",
        pattern="^(production|staging|development|test)$"
    )
    deployment_criticality: Optional[str] = Field(
        None,
        description="Business criticality rating",
        pattern="^(critical|high|medium|low)$"
    )

    @field_validator('component_purl')
    @classmethod
    def validate_purl_format(cls, v: str) -> str:
        """Validate basic PURL format: pkg:type/namespace/name@version."""
        if not v.startswith('pkg:'):
            raise ValueError(f"Invalid PURL format: {v}. Must start with 'pkg:'")
        if '@' not in v and '?' not in v:
            raise ValueError(f"Invalid PURL format: {v}. Version or qualifiers required")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "component_purl": "pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
                "component_name": "log4j-core",
                "component_version": "2.14.1",
                "in_sbom": True,
                "sbom_component_id": "components/log4j_core_2_14_1",
                "deployment_scope": "production",
                "deployment_criticality": "critical"
            }]
        }
    }


class ExploitabilityEvidence(BaseModel):
    """
    Exploitability evidence (Tier 1 - Critical).

    Contains EPSS scores and exploit availability information.

    Regulatory Requirement:
        - FDA 524B: Exploit probability assessment required
        - EU CRA: Exploitability analysis for risk scoring

    Fields:
        - epss_score: EPSS probability score (0.0-1.0)
        - epss_percentile: EPSS percentile rank (0.0-1.0)
        - epss_date: EPSS score calculation date
        - exploit_available: Public exploit code availability
        - exploit_maturity: Exploit code maturity level
        - epss_graph_id: EPSS document ID in graph

    Example:
        >>> exploit = ExploitabilityEvidence(
        ...     epss_score=0.97542,
        ...     epss_percentile=0.99876,
        ...     epss_date=datetime(2021, 12, 15),
        ...     exploit_available=True,
        ...     exploit_maturity="high",
        ...     epss_graph_id="epss_scores/CVE_2021_44228_20211215"
        ... )
    """
    epss_score: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="EPSS probability score (0.0-1.0, higher = more likely to be exploited)"
    )
    epss_percentile: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="EPSS percentile (0.0-1.0, higher = ranks above more vulnerabilities)"
    )
    epss_date: Optional[datetime] = Field(
        None,
        description="EPSS score date (scores updated daily)"
    )

    exploit_available: Optional[bool] = Field(
        None,
        description="Public exploit code available? (Metasploit, ExploitDB, GitHub)"
    )
    exploit_maturity: Optional[str] = Field(
        None,
        description="Exploit code maturity level",
        pattern="^(unproven|proof_of_concept|functional|high)$"
    )

    # Graph provenance
    epss_graph_id: Optional[str] = Field(
        None,
        description="EPSS document _id (e.g., epss_scores/CVE_2021_44228_20211215)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "epss_score": 0.97542,
                "epss_percentile": 0.99876,
                "epss_date": "2021-12-15T00:00:00Z",
                "exploit_available": True,
                "exploit_maturity": "high",
                "epss_graph_id": "epss_scores/CVE_2021_44228_20211215"
            }]
        }
    }


# ========== Tier 2 Evidence Models (Important) ==========


class AttackTechniqueEvidence(BaseModel):
    """
    ATT&CK technique evidence (Tier 2 - Important).

    Links vulnerability to MITRE ATT&CK techniques via graph traversal.

    Regulatory Requirement:
        - EU CRA: Attack technique correlation recommended
        - FDA 524B: Threat modeling for medical devices

    Fields:
        - technique_id: ATT&CK technique ID (e.g., T1190)
        - technique_name: Human-readable technique name
        - tactic: ATT&CK tactic category
        - description: Technique description
        - technique_graph_id: ATT&CK document ID
        - capec_id: Intermediate CAPEC pattern ID
        - capec_graph_id: CAPEC document ID
        - graph_path: Complete traversal path (CVE→CWE→CAPEC→ATT&CK)

    Traversal Path:
        CVE → has_weakness → CWE → capec_relates_to_cwe → CAPEC →
        capec_maps_to_attack → ATT&CK Technique

    Example:
        >>> attack = AttackTechniqueEvidence(
        ...     technique_id="T1190",
        ...     technique_name="Exploit Public-Facing Application",
        ...     tactic="Initial Access",
        ...     description="Adversaries may exploit weaknesses in Internet-facing applications",
        ...     technique_graph_id="attack_techniques/T1190",
        ...     capec_id="CAPEC-248",
        ...     capec_graph_id="capecs/CAPEC_248",
        ...     graph_path=["vulnerabilities/CVE_2021_44228", "cwes/CWE_502", "capecs/CAPEC_248", "attack_techniques/T1190"]
        ... )
    """
    technique_id: str = Field(
        description="ATT&CK technique ID (e.g., T1190)",
        pattern="^T\\d{4}(\\.\\d{3})?$"
    )
    technique_name: str = Field(
        description="Technique name (e.g., 'Exploit Public-Facing Application')",
        min_length=1
    )
    tactic: str = Field(
        description="ATT&CK tactic (e.g., 'Initial Access', 'Execution')",
        min_length=1
    )
    description: str = Field(
        description="Technique description from ATT&CK",
        min_length=1
    )

    # Graph provenance (full chain)
    technique_graph_id: str = Field(
        description="ATT&CK technique _id (e.g., attack_techniques/T1190)",
        pattern="^attack_techniques/.+$"
    )
    capec_id: Optional[str] = Field(
        None,
        description="Intermediate CAPEC pattern (e.g., CAPEC-248)",
        pattern="^CAPEC-\\d+$"
    )
    capec_graph_id: Optional[str] = Field(
        None,
        description="CAPEC document _id (e.g., capecs/CAPEC_248)"
    )

    # Traversal path
    graph_path: List[str] = Field(
        description="Full graph path: [CVE_id, CWE_id, CAPEC_id, ATTACK_id]",
        min_length=2
    )

    @field_validator('technique_id')
    @classmethod
    def validate_attack_id_format(cls, v: str) -> str:
        """Validate ATT&CK technique ID format: T#### or T####.###."""
        if not re.match(r'^T\d{4}(\.\d{3})?$', v.upper()):
            raise ValueError(f"Invalid ATT&CK technique ID format: {v}. Expected T#### or T####.###")
        return v.upper()

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "technique_id": "T1190",
                "technique_name": "Exploit Public-Facing Application",
                "tactic": "Initial Access",
                "description": "Adversaries may attempt to exploit weaknesses in Internet-facing computer applications and programs to gain initial access to a system.",
                "technique_graph_id": "attack_techniques/T1190",
                "capec_id": "CAPEC-248",
                "capec_graph_id": "capecs/CAPEC_248",
                "graph_path": [
                    "vulnerabilities/CVE_2021_44228",
                    "cwes/CWE_502",
                    "capecs/CAPEC_248",
                    "attack_techniques/T1190"
                ]
            }]
        }
    }


class MitigationControlEvidence(BaseModel):
    """
    Mitigation control evidence (Tier 2 - Important).

    Links ATT&CK techniques to security controls that mitigate them.

    Regulatory Requirement:
        - FDA 524B: Documented mitigations required
        - EU CRA: Security measures for vulnerability management
        - IEC 62304: Risk mitigation documentation

    Fields:
        - control_id: Control identifier (e.g., AC-3, SI-10)
        - control_title: Human-readable control title
        - framework: Control framework origin
        - control_family: Control family/category
        - mitigation_effectiveness: Effectiveness rating
        - control_graph_id: Control document ID
        - graph_path: Complete traversal path

    Frameworks Supported:
        - NIST 800-53 (Federal/Medical)
        - ISO 27001 (International)
        - IEC 62443 (Industrial)

    Example:
        >>> control = MitigationControlEvidence(
        ...     control_id="SI-10",
        ...     control_title="Information Input Validation",
        ...     framework="NIST_800_53",
        ...     control_family="System and Information Integrity",
        ...     mitigation_effectiveness="complete",
        ...     control_graph_id="oscal_controls/NIST_800_53_SI_10",
        ...     graph_path=["vulnerabilities/CVE_2021_44228", "cwes/CWE_502", "capecs/CAPEC_248", "attack_techniques/T1190", "oscal_controls/NIST_800_53_SI_10"]
        ... )
    """
    control_id: str = Field(
        description="Control identifier (e.g., AC-3, SI-10, ISO-27001-A.12.6.1)",
        min_length=1
    )
    control_title: str = Field(
        description="Control title (e.g., 'Information Input Validation')",
        min_length=1
    )
    framework: str = Field(
        description="Control framework origin",
        pattern="^(NIST_800_53|ISO_27001|IEC_62443|PCI_DSS)$"
    )
    control_family: Optional[str] = Field(
        None,
        description="Control family (e.g., 'Access Control', 'System Integrity')"
    )

    mitigation_effectiveness: Optional[str] = Field(
        None,
        description="Mitigation effectiveness rating",
        pattern="^(complete|partial|minimal)$"
    )

    # Graph provenance
    control_graph_id: str = Field(
        description="Control document _id (e.g., oscal_controls/NIST_800_53_SI_10)",
        pattern="^oscal_controls/.+$"
    )

    # Traversal path
    graph_path: List[str] = Field(
        description="Full graph path: [CVE_id, ..., ATTACK_id, CONTROL_id]",
        min_length=2
    )

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "control_id": "SI-10",
                "control_title": "Information Input Validation",
                "framework": "NIST_800_53",
                "control_family": "System and Information Integrity",
                "mitigation_effectiveness": "complete",
                "control_graph_id": "oscal_controls/NIST_800_53_SI_10",
                "graph_path": [
                    "vulnerabilities/CVE_2021_44228",
                    "cwes/CWE_502",
                    "capecs/CAPEC_248",
                    "attack_techniques/T1190",
                    "oscal_controls/NIST_800_53_SI_10"
                ]
            }]
        }
    }


class RemediationEvidence(BaseModel):
    """
    Remediation path evidence (Tier 2 - Important).

    Documents available fixes, patches, and workarounds.

    Regulatory Requirement:
        - FDA 524B: Remediation plan required for affected vulnerabilities
        - EU CRA: Vulnerability management obligations

    Fields:
        - fix_available: Boolean flag for fix availability
        - fix_version: Specific version that fixes vulnerability
        - upgrade_path: Recommended upgrade strategy
        - workaround_available: Temporary mitigation availability
        - workaround_description: Detailed workaround steps
        - vendor_advisory_url: Official security advisory URL
        - patch_complexity: Implementation difficulty

    Example:
        >>> remediation = RemediationEvidence(
        ...     fix_available=True,
        ...     fix_version="2.17.1",
        ...     upgrade_path="Upgrade to log4j-core 2.17.1 or later",
        ...     workaround_available=True,
        ...     workaround_description="Set log4j2.formatMsgNoLookups=true",
        ...     vendor_advisory_url="https://logging.apache.org/log4j/2.x/security.html",
        ...     patch_complexity="low"
        ... )
    """
    fix_available: bool = Field(
        description="Is fix/patch available from vendor?"
    )
    fix_version: Optional[str] = Field(
        None,
        description="Fixed version (e.g., '2.17.1', '>=2.17.0')"
    )
    upgrade_path: Optional[str] = Field(
        None,
        description="Recommended upgrade path (e.g., '2.14.1 → 2.17.1')"
    )
    workaround_available: bool = Field(
        default=False,
        description="Is temporary workaround available?"
    )
    workaround_description: Optional[str] = Field(
        None,
        description="Detailed workaround steps"
    )

    vendor_advisory_url: Optional[str] = Field(
        None,
        description="Vendor security advisory URL",
        pattern="^https?://.+"
    )
    patch_complexity: Optional[str] = Field(
        None,
        description="Implementation difficulty",
        pattern="^(low|medium|high)$"
    )

    @field_validator('vendor_advisory_url')
    @classmethod
    def validate_url_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate URL format."""
        if v and not (v.startswith('http://') or v.startswith('https://')):
            raise ValueError(f"Invalid URL format: {v}. Must start with http:// or https://")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "fix_available": True,
                "fix_version": "2.17.1",
                "upgrade_path": "Upgrade to log4j-core 2.17.1 or later",
                "workaround_available": True,
                "workaround_description": "Set system property log4j2.formatMsgNoLookups=true or environment variable LOG4J_FORMAT_MSG_NO_LOOKUPS=true",
                "vendor_advisory_url": "https://logging.apache.org/log4j/2.x/security.html",
                "patch_complexity": "low"
            }]
        }
    }


class ComplianceViolationEvidence(BaseModel):
    """
    Regulatory requirement violation evidence (Tier 2 - Important).

    Links vulnerability to specific regulatory obligations.

    Regulatory Requirement:
        - EU CRA: Mapping to compliance obligations mandatory
        - FDA 524B: Regulatory impact assessment

    Fields:
        - requirement_id: Requirement identifier (e.g., CRA_I_1_a)
        - requirement_title: Human-readable requirement title
        - framework: Regulatory framework (CRA, FDA, IEC)
        - obligation_level: RFC 2119 level (shall/should/may)
        - deadline: Compliance deadline (if applicable)
        - violation_severity: Impact severity rating
        - requirement_graph_id: Requirement document ID
        - violation_edge_id: violates_requirement edge ID

    Example:
        >>> violation = ComplianceViolationEvidence(
        ...     requirement_id="CRA_I_1_a",
        ...     requirement_title="Vulnerability Handling Process",
        ...     framework="EU_CRA",
        ...     obligation_level="shall",
        ...     deadline=datetime(2024, 12, 31),
        ...     violation_severity="high",
        ...     requirement_graph_id="requirements/CRA_I_1_a",
        ...     violation_edge_id="violates_requirement/cve_2021_44228_to_cra_i_1_a"
        ... )
    """
    requirement_id: str = Field(
        description="Requirement identifier (e.g., CRA_I_1_a, FDA_524B_3_2_1)",
        min_length=1
    )
    requirement_title: str = Field(
        description="Requirement title (e.g., 'Vulnerability Handling Process')",
        min_length=1
    )
    framework: str = Field(
        description="Regulatory framework origin",
        pattern="^(EU_CRA|FDA_524B|IEC_62304|ISO_13485|HIPAA)$"
    )
    obligation_level: str = Field(
        description="RFC 2119 obligation level",
        pattern="^(shall|should|may)$"
    )

    deadline: Optional[datetime] = Field(
        None,
        description="Compliance deadline (critical for planning)"
    )
    violation_severity: Optional[str] = Field(
        None,
        description="Violation impact severity",
        pattern="^(critical|high|medium|low)$"
    )

    # Graph provenance
    requirement_graph_id: str = Field(
        description="Requirement document _id (e.g., requirements/CRA_I_1_a)",
        pattern="^requirements/.+$"
    )
    violation_edge_id: str = Field(
        description="violates_requirement edge _id",
        pattern="^violates_requirement/.+$"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "requirement_id": "CRA_I_1_a",
                "requirement_title": "Vulnerability Handling Process - Active Monitoring",
                "framework": "EU_CRA",
                "obligation_level": "shall",
                "deadline": "2024-12-31T23:59:59Z",
                "violation_severity": "high",
                "requirement_graph_id": "requirements/CRA_I_1_a",
                "violation_edge_id": "violates_requirement/cve_2021_44228_to_cra_i_1_a"
            }]
        }
    }


# ========== Composite Evidence Container ==========


class GraphEvidence(BaseModel):
    """
    Graph traversal evidence container.

    Aggregates all evidence derived from knowledge graph traversals.

    Contains:
        - Tier 1 (Critical): CWE, KEV, Component, Exploitability
        - Tier 2 (Important): ATT&CK, Controls, Remediation, Violations

    Fields:
        - cwe_mappings: List of CWE weakness classifications
        - kev_evidence: KEV catalog status
        - component_presence: SBOM validation
        - exploitability: EPSS and exploit data
        - attack_techniques: ATT&CK technique mappings
        - mitigation_controls: Security control mappings
        - remediation: Fix and workaround information
        - compliance_violations: Regulatory violations
        - collection_timestamp: When evidence was collected
        - evidence_completeness: Completeness assessment

    Example:
        >>> evidence = GraphEvidence(
        ...     cwe_mappings=[cwe_502],
        ...     kev_evidence=kev_evidence,
        ...     component_presence=component_presence,
        ...     exploitability=exploitability,
        ...     attack_techniques=[t1190],
        ...     mitigation_controls=[si_10],
        ...     evidence_completeness="complete"
        ... )
    """
    # Tier 1 (Critical)
    cwe_mappings: List[CWEEvidence] = Field(
        default_factory=list,
        description="CWE weakness classifications (Tier 1 - Critical)"
    )
    kev_evidence: KEVEvidence = Field(
        description="KEV status evidence (Tier 1 - Critical)"
    )
    component_presence: ComponentPresenceEvidence = Field(
        description="Component presence validation (Tier 1 - Critical)"
    )
    exploitability: ExploitabilityEvidence = Field(
        description="Exploitability metrics (Tier 1 - Critical)"
    )

    # Tier 2 (Important)
    attack_techniques: List[AttackTechniqueEvidence] = Field(
        default_factory=list,
        description="ATT&CK techniques (Tier 2 - Important)"
    )
    mitigation_controls: List[MitigationControlEvidence] = Field(
        default_factory=list,
        description="Mitigation controls (Tier 2 - Important)"
    )
    remediation: Optional[RemediationEvidence] = Field(
        None,
        description="Remediation information (Tier 2 - Important)"
    )
    compliance_violations: List[ComplianceViolationEvidence] = Field(
        default_factory=list,
        description="Compliance violations (Tier 2 - Important)"
    )

    # Collection metadata
    collection_timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when evidence was collected"
    )
    evidence_completeness: str = Field(
        description="Evidence completeness assessment",
        pattern="^(complete|partial|incomplete)$"
    )

    @field_validator('cwe_mappings')
    @classmethod
    def validate_cwe_mappings(cls, v: List[CWEEvidence]) -> List[CWEEvidence]:
        """Validate at least one CWE mapping (Tier 1 requirement)."""
        if not v:
            raise ValueError("At least one CWE mapping required (Tier 1 - Critical)")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "cwe_mappings": [
                    {
                        "cwe_id": "CWE-502",
                        "name": "Deserialization of Untrusted Data",
                        "description": "Software deserializes untrusted data without verification",
                        "weakness_type": "Base",
                        "graph_id": "cwes/CWE_502",
                        "edge_id": "has_weakness/12345"
                    }
                ],
                "kev_evidence": {
                    "in_kev": True,
                    "kev_date_added": "2021-12-10T00:00:00Z",
                    "kev_due_date": "2021-12-24T00:00:00Z",
                    "kev_required_action": "Apply updates per vendor instructions",
                    "kev_graph_id": "kev_entries/CVE_2021_44228"
                },
                "component_presence": {
                    "component_purl": "pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
                    "component_name": "log4j-core",
                    "component_version": "2.14.1",
                    "in_sbom": True
                },
                "exploitability": {
                    "epss_score": 0.97542,
                    "epss_percentile": 0.99876,
                    "exploit_available": True,
                    "exploit_maturity": "high"
                },
                "evidence_completeness": "complete"
            }]
        }
    }


class VulnerabilityEvidence(BaseModel):
    """
    Complete vulnerability evidence package.

    Aggregates all evidence for a single CVE affecting a component.

    Structure:
        - CVE Metadata (Tier 1)
        - Graph Evidence (Tier 1 + Tier 2)
        - Completeness Flags
        - Provenance Metadata

    Fields:
        - cve_metadata: Core CVE information
        - graph_evidence: All graph-derived evidence
        - tier_1_complete: Tier 1 evidence completeness flag
        - tier_2_complete: Tier 2 evidence completeness flag
        - evidence_version: Schema version
        - collection_method: Collection methodology

    Example:
        >>> evidence = VulnerabilityEvidence(
        ...     cve_metadata=cve_metadata,
        ...     graph_evidence=graph_evidence,
        ...     tier_1_complete=True,
        ...     tier_2_complete=True
        ... )
    """
    # Tier 1 (Critical)
    cve_metadata: CVEMetadata = Field(
        description="CVE metadata evidence (Tier 1 - Critical)"
    )
    graph_evidence: GraphEvidence = Field(
        description="Graph-derived evidence (Tier 1 + Tier 2)"
    )

    # Evidence validation
    tier_1_complete: bool = Field(
        description="All Tier 1 (Critical) evidence collected and valid?"
    )
    tier_2_complete: bool = Field(
        description="All Tier 2 (Important) evidence collected and valid?"
    )

    # Provenance
    evidence_version: str = Field(
        default="1.0",
        description="Evidence schema version"
    )
    collection_method: str = Field(
        default="graph_traversal",
        description="Evidence collection methodology"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "cve_metadata": {
                    "cve_id": "CVE-2021-44228",
                    "description": "Apache Log4j2 RCE vulnerability",
                    "cvss_v3_score": 10.0,
                    "cvss_v3_severity": "CRITICAL",
                    "graph_id": "vulnerabilities/CVE_2021_44228"
                },
                "graph_evidence": {
                    "cwe_mappings": [],
                    "kev_evidence": {"in_kev": True},
                    "component_presence": {"in_sbom": True},
                    "exploitability": {"epss_score": 0.97},
                    "evidence_completeness": "complete"
                },
                "tier_1_complete": True,
                "tier_2_complete": True,
                "evidence_version": "1.0",
                "collection_method": "graph_traversal"
            }]
        }
    }


# ========== VEX Assessment Model ==========


class VEXAssessment(BaseModel):
    """
    Complete VEX assessment with evidence.

    Final output model combining assessment decision and evidence chain.

    Components:
        1. Identification (CVE + Component)
        2. Assessment Decision (Status + Justification)
        3. Complete Evidence Package
        4. LLM-Generated Analysis
        5. Regulatory Compliance
        6. Provenance Metadata

    Fields:
        - vulnerability_id: CVE identifier
        - component_purl: Component PURL
        - status: VEX assessment status
        - justification: Justification (if not_affected)
        - response: Response actions
        - evidence: Complete evidence package
        - impact_summary: Human-readable impact
        - exploitability_analysis: Exploitability assessment
        - mitigation_recommendations: Recommended mitigations
        - evidence_citations: Evidence references
        - regulatory_impact: Regulatory significance
        - compliance_deadline: Soonest deadline
        - assessment_timestamp: When assessment was made
        - generated_by: Generator identifier
        - llm_model: LLM model used

    Example:
        >>> assessment = VEXAssessment(
        ...     vulnerability_id="CVE-2021-44228",
        ...     component_purl="pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
        ...     status=VEXStatus.AFFECTED,
        ...     response=[VEXResponse.UPDATE],
        ...     evidence=vulnerability_evidence,
        ...     impact_summary="Critical RCE vulnerability in Log4j",
        ...     exploitability_analysis="EPSS 0.97, actively exploited (KEV)",
        ...     mitigation_recommendations=["Upgrade to 2.17.1 immediately"]
        ... )
    """
    # Identification
    vulnerability_id: str = Field(
        description="CVE identifier (e.g., CVE-2021-44228)",
        pattern="^CVE-\\d{4}-\\d{4,}$"
    )
    component_purl: str = Field(
        description="Component PURL (e.g., pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1)"
    )

    # Assessment
    status: VEXStatus = Field(
        description="Vulnerability assessment status"
    )
    justification: Optional[VEXJustification] = Field(
        None,
        description="Justification (required if status is not_affected)"
    )
    response: List[VEXResponse] = Field(
        default_factory=list,
        description="Response actions (for affected status)"
    )

    # Evidence (Complete Chain)
    evidence: VulnerabilityEvidence = Field(
        description="Complete evidence package with graph provenance"
    )

    # LLM-Generated Analysis (With Evidence Citations)
    impact_summary: str = Field(
        description="Human-readable impact summary",
        min_length=10
    )
    exploitability_analysis: str = Field(
        description="Exploitability analysis with evidence citations",
        min_length=10
    )
    mitigation_recommendations: List[str] = Field(
        default_factory=list,
        description="Prioritized mitigation recommendations"
    )

    # Evidence Citations (References to specific evidence items)
    evidence_citations: List[str] = Field(
        default_factory=list,
        description="Evidence item IDs cited in analysis (e.g., ['cve_metadata', 'kev_evidence'])"
    )

    # Regulatory Compliance
    regulatory_impact: Optional[str] = Field(
        None,
        description="Regulatory impact assessment (FDA, CRA, IEC)"
    )
    compliance_deadline: Optional[datetime] = Field(
        None,
        description="Soonest compliance deadline (from KEV or violations)"
    )

    # Metadata
    assessment_timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When assessment was generated"
    )
    assessment_version: str = Field(
        default="2.0",
        description="VEX assessment schema version"
    )
    generated_by: str = Field(
        default="complira_vex_v2",
        description="Generator identifier"
    )

    # LLM Provenance
    llm_model: Optional[str] = Field(
        None,
        description="LLM model used for analysis (e.g., 'gpt-4', 'claude-3')"
    )
    llm_tokens: Optional[Dict[str, int]] = Field(
        None,
        description="Token usage statistics (e.g., {'input': 1200, 'output': 450})"
    )

    @model_validator(mode='after')
    def validate_justification_required(self) -> 'VEXAssessment':
        """If status is not_affected, justification is required."""
        if self.status == VEXStatus.NOT_AFFECTED and not self.justification:
            raise ValueError("justification required when status is 'not_affected'")
        return self

    @model_validator(mode='after')
    def validate_response_for_affected(self) -> 'VEXAssessment':
        """If status is affected, at least one response is recommended."""
        if self.status == VEXStatus.AFFECTED and not self.response:
            raise ValueError("At least one response action recommended when status is 'affected'")
        return self

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "vulnerability_id": "CVE-2021-44228",
                "component_purl": "pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
                "status": "affected",
                "response": ["update"],
                "evidence": {
                    "cve_metadata": {"cve_id": "CVE-2021-44228", "cvss_v3_score": 10.0},
                    "graph_evidence": {"evidence_completeness": "complete"},
                    "tier_1_complete": True,
                    "tier_2_complete": True
                },
                "impact_summary": "Critical remote code execution vulnerability in Apache Log4j2 allows unauthenticated remote attackers to execute arbitrary code",
                "exploitability_analysis": "EPSS score 0.97542 (99.8th percentile). Actively exploited in wild (CISA KEV). Public exploits widely available (high maturity).",
                "mitigation_recommendations": [
                    "Upgrade to log4j-core 2.17.1 immediately",
                    "Apply workaround: set log4j2.formatMsgNoLookups=true",
                    "Implement SI-10 input validation controls"
                ],
                "evidence_citations": ["cve_metadata", "kev_evidence", "exploitability", "attack_techniques[0]"],
                "regulatory_impact": "FDA 524B: Critical vulnerability requires immediate remediation. EU CRA: Violates vulnerability handling obligations.",
                "compliance_deadline": "2021-12-24T00:00:00Z",
                "assessment_timestamp": "2024-03-06T12:00:00Z"
            }]
        }
    }


# ========== Multi-Format Output Models ==========


class CycloneDXVEX(BaseModel):
    """
    CycloneDX VEX 1.5 output format.

    Produces VEX in CycloneDX standard format for tool interoperability.

    Fields:
        - bomFormat: Always "CycloneDX"
        - specVersion: Always "1.5"
        - version: Document version (increments on updates)
        - metadata: Document metadata and component info
        - vulnerabilities: List of vulnerability assessments
        - evidence_package: Complira extension for auditability

    Standards Compliance:
        - CycloneDX 1.5 Specification
        - VEX 1.0 Specification
        - SBOM/VEX Industry Standard
    """
    bomFormat: Literal["CycloneDX"] = "CycloneDX"
    specVersion: Literal["1.5"] = "1.5"
    version: int = Field(
        default=1,
        ge=1,
        description="Document version (increments on updates)"
    )

    metadata: Dict[str, Any] = Field(
        description="Metadata including timestamp, component info, supplier"
    )
    vulnerabilities: List[Dict[str, Any]] = Field(
        description="Vulnerability assessments in CycloneDX format"
    )

    # Complira extension
    evidence_package: Optional[VulnerabilityEvidence] = Field(
        None,
        description="Complete evidence package (Complira extension for auditability)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "bomFormat": "CycloneDX",
                "specVersion": "1.5",
                "version": 1,
                "metadata": {
                    "timestamp": "2024-03-06T12:00:00Z",
                    "component": {
                        "type": "library",
                        "name": "log4j-core",
                        "version": "2.14.1"
                    }
                },
                "vulnerabilities": [
                    {
                        "id": "CVE-2021-44228",
                        "analysis": {
                            "state": "affected",
                            "response": ["update"]
                        }
                    }
                ]
            }]
        }
    }


class CSAFVEX(BaseModel):
    """
    CSAF 2.0 VEX output format.

    Produces VEX in CSAF standard format (preferred by some industries).

    Fields:
        - document: CSAF document metadata
        - product_tree: Product identification tree
        - vulnerabilities: List of vulnerability assessments
        - notes: Evidence notes for auditability

    Standards Compliance:
        - CSAF 2.0 Specification
        - OASIS Standard
        - Government/Enterprise Preferred
    """
    document: Dict[str, Any] = Field(
        description="CSAF document metadata (category, title, publisher)"
    )
    product_tree: Dict[str, Any] = Field(
        description="Product tree defining affected products"
    )
    vulnerabilities: List[Dict[str, Any]] = Field(
        description="Vulnerability assessments in CSAF format"
    )

    # Evidence in notes section (CSAF pattern)
    notes: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Evidence notes for auditability (CSAF pattern)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "document": {
                    "category": "csaf_vex",
                    "title": "VEX for CVE-2021-44228 in log4j-core",
                    "publisher": {
                        "category": "vendor",
                        "name": "Complira"
                    }
                },
                "product_tree": {
                    "branches": [
                        {
                            "name": "log4j-core",
                            "product": {
                                "name": "log4j-core 2.14.1",
                                "product_id": "log4j-core-2.14.1"
                            }
                        }
                    ]
                },
                "vulnerabilities": [
                    {
                        "cve": "CVE-2021-44228",
                        "product_status": {
                            "known_affected": ["log4j-core-2.14.1"]
                        }
                    }
                ]
            }]
        }
    }


# ========== Validation Result Model ==========


class EvidenceValidationResult(BaseModel):
    """
    Evidence validation result.

    Reports on evidence completeness and regulatory compliance.

    Fields:
        - valid: Overall validation status
        - tier_1_valid: Tier 1 evidence validation
        - tier_2_valid: Tier 2 evidence validation
        - missing_evidence: List of missing evidence types
        - invalid_references: Graph references that don't exist
        - inconsistencies: Evidence contradictions
        - regulatory_compliance: Per-framework compliance
        - validation_timestamp: When validation occurred

    Usage:
        >>> result = EvidenceValidationResult(
        ...     valid=True,
        ...     tier_1_valid=True,
        ...     tier_2_valid=True,
        ...     regulatory_compliance={"FDA_524B": True, "CRA": True}
        ... )
    """
    valid: bool = Field(
        description="Overall validation status (True if Tier 1 complete)"
    )
    tier_1_valid: bool = Field(
        description="Tier 1 (Critical) evidence complete and valid?"
    )
    tier_2_valid: bool = Field(
        description="Tier 2 (Important) evidence complete and valid?"
    )

    missing_evidence: List[str] = Field(
        default_factory=list,
        description="Missing evidence types (e.g., ['cwe_mappings', 'epss_score'])"
    )
    invalid_references: List[str] = Field(
        default_factory=list,
        description="Invalid graph references (documents don't exist)"
    )
    inconsistencies: List[str] = Field(
        default_factory=list,
        description="Evidence inconsistencies (e.g., 'CVSS severity mismatch')"
    )

    regulatory_compliance: Dict[str, bool] = Field(
        default_factory=dict,
        description="Compliance status per framework"
    )

    validation_timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When validation was performed"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "valid": True,
                "tier_1_valid": True,
                "tier_2_valid": True,
                "missing_evidence": [],
                "invalid_references": [],
                "inconsistencies": [],
                "regulatory_compliance": {
                    "FDA_524B": True,
                    "EU_CRA": True,
                    "IEC_62304": True
                },
                "validation_timestamp": "2024-03-06T12:00:00Z"
            }]
        }
    }


class VEXGenerationResult(BaseModel):
    """
    Complete VEX generation result.

    Top-level result container for VEX generation workflow.

    Fields:
        - assessment: VEX assessment with evidence
        - validation: Evidence validation result
        - cyclonedx_vex: CycloneDX format output
        - csaf_vex: CSAF format output
        - generation_timestamp: When result was generated
        - generation_duration_ms: Processing time
        - errors: Any errors encountered
        - warnings: Any warnings generated

    Usage:
        >>> result = VEXGenerationResult(
        ...     assessment=vex_assessment,
        ...     validation=validation_result,
        ...     cyclonedx_vex=cyclonedx_output
        ... )
    """
    assessment: VEXAssessment = Field(
        description="Complete VEX assessment with evidence"
    )
    validation: EvidenceValidationResult = Field(
        description="Evidence validation result"
    )

    # Multi-format outputs
    cyclonedx_vex: Optional[CycloneDXVEX] = Field(
        None,
        description="CycloneDX VEX 1.5 format output"
    )
    csaf_vex: Optional[CSAFVEX] = Field(
        None,
        description="CSAF 2.0 VEX format output"
    )

    # Generation metadata
    generation_timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When result was generated"
    )
    generation_duration_ms: Optional[int] = Field(
        None,
        ge=0,
        description="Processing time in milliseconds"
    )

    # Errors and warnings
    errors: List[str] = Field(
        default_factory=list,
        description="Errors encountered during generation"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Warnings generated during processing"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "assessment": {
                    "vulnerability_id": "CVE-2021-44228",
                    "status": "affected",
                    "impact_summary": "Critical RCE vulnerability"
                },
                "validation": {
                    "valid": True,
                    "tier_1_valid": True,
                    "tier_2_valid": True
                },
                "generation_timestamp": "2024-03-06T12:00:00Z",
                "generation_duration_ms": 1250,
                "errors": [],
                "warnings": []
            }]
        }
    }


# ========== Export All Models ==========

__all__ = [
    # Enums
    "EvidenceTier",
    "VEXStatus",
    "VEXJustification",
    "VEXResponse",
    # Tier 1 Evidence Models
    "CVEMetadata",
    "CWEEvidence",
    "KEVEvidence",
    "ComponentPresenceEvidence",
    "ExploitabilityEvidence",
    # Tier 2 Evidence Models
    "AttackTechniqueEvidence",
    "MitigationControlEvidence",
    "RemediationEvidence",
    "ComplianceViolationEvidence",
    # Container Models
    "GraphEvidence",
    "VulnerabilityEvidence",
    # Assessment Models
    "VEXAssessment",
    # Output Format Models
    "CycloneDXVEX",
    "CSAFVEX",
    # Validation Models
    "EvidenceValidationResult",
    "VEXGenerationResult",
]
