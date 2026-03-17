# VEX Evidence Schema Design - Part 3

## 5. CycloneDX VEX Formatter

**File:** `/Users/venkatapydialli/Documents/cybersecurity-compliance-app/src/complira_graph/formatters/cyclonedx.py`

```python
"""
CycloneDX VEX 1.5 Formatter.

Converts VEXAssessment to CycloneDX VEX format (industry standard).

CycloneDX is an OWASP standard for Software Bill of Materials (SBOM) and
VEX documents. Version 1.5 introduced native VEX support.

Specification: https://cyclonedx.org/docs/1.5/json/

Key Features:
- CycloneDX 1.5 compliance
- Evidence package inclusion (Complira extension)
- SBOM-native VEX format
- Tool integration friendly

Usage:
    from complira_graph.formatters.cyclonedx import CycloneDXFormatter

    formatter = CycloneDXFormatter()
    cyclonedx_vex = formatter.format(vex_assessment)
"""

from typing import Dict, Any, List
from datetime import datetime
from uuid import uuid4

from complira_graph.models.vex_evidence import (
    VEXAssessment,
    VEXStatus,
    VEXJustification,
    VEXResponse,
)
import structlog

logger = structlog.get_logger()


class CycloneDXFormatter:
    """
    CycloneDX 1.5 VEX formatter.

    Converts VEXAssessment (internal model) to CycloneDX 1.5 JSON.
    """

    SPEC_VERSION = "1.5"
    BOM_FORMAT = "CycloneDX"

    def format(self, assessment: VEXAssessment) -> Dict[str, Any]:
        """
        Convert VEXAssessment to CycloneDX 1.5 VEX document.

        Args:
            assessment: VEX assessment with evidence

        Returns:
            dict: CycloneDX 1.5 VEX document
        """
        logger.debug(
            "Formatting VEX assessment to CycloneDX",
            cve_id=assessment.vulnerability_id,
        )

        # Build CycloneDX document
        cyclonedx_doc = {
            "bomFormat": self.BOM_FORMAT,
            "specVersion": self.SPEC_VERSION,
            "serialNumber": f"urn:uuid:{uuid4()}",
            "version": 1,
            "metadata": self._build_metadata(assessment),
            "vulnerabilities": [self._build_vulnerability(assessment)],
        }

        # Add Complira extension for complete evidence
        cyclonedx_doc["properties"] = self._build_evidence_properties(assessment)

        logger.debug(
            "CycloneDX document formatted",
            cve_id=assessment.vulnerability_id,
        )

        return cyclonedx_doc

    def _build_metadata(self, assessment: VEXAssessment) -> Dict[str, Any]:
        """
        Build CycloneDX metadata section.

        Args:
            assessment: VEX assessment

        Returns:
            dict: Metadata section
        """
        return {
            "timestamp": assessment.assessment_timestamp.isoformat() + "Z",
            "tools": [
                {
                    "vendor": "Complira",
                    "name": "Complira VEX Synthesizer",
                    "version": assessment.assessment_version,
                }
            ],
            "component": self._build_component_ref(assessment.component_purl),
        }

    def _build_component_ref(self, purl: str) -> Dict[str, Any]:
        """
        Build component reference from PURL.

        Args:
            purl: Package URL

        Returns:
            dict: Component reference
        """
        purl_parts = self._parse_purl(purl)

        return {
            "type": "library",
            "name": purl_parts["name"],
            "version": purl_parts["version"],
            "purl": purl,
        }

    def _build_vulnerability(self, assessment: VEXAssessment) -> Dict[str, Any]:
        """
        Build CycloneDX vulnerability object.

        Args:
            assessment: VEX assessment

        Returns:
            dict: Vulnerability object
        """
        cve_meta = assessment.evidence.cve_metadata

        vuln = {
            "id": assessment.vulnerability_id,
            "source": {
                "name": "NVD",
                "url": f"https://nvd.nist.gov/vuln/detail/{assessment.vulnerability_id}",
            },
            "ratings": self._build_ratings(assessment),
            "cwes": self._build_cwes(assessment),
            "description": cve_meta.description,
            "published": cve_meta.published_date.isoformat() + "Z"
            if cve_meta.published_date
            else None,
            "updated": cve_meta.last_modified_date.isoformat() + "Z"
            if cve_meta.last_modified_date
            else None,
            "analysis": self._build_analysis(assessment),
            "affects": [
                {
                    "ref": assessment.component_purl,
                }
            ],
        }

        # Add advisories if available
        if assessment.evidence.graph_evidence.remediation:
            vuln["advisories"] = self._build_advisories(assessment)

        return vuln

    def _build_ratings(self, assessment: VEXAssessment) -> List[Dict[str, Any]]:
        """
        Build CVSS ratings.

        Args:
            assessment: VEX assessment

        Returns:
            list: CVSS ratings
        """
        cve_meta = assessment.evidence.cve_metadata
        ratings = []

        if cve_meta.cvss_v3_score:
            ratings.append(
                {
                    "source": {"name": "NVD"},
                    "score": cve_meta.cvss_v3_score,
                    "severity": cve_meta.cvss_v3_severity.lower()
                    if cve_meta.cvss_v3_severity
                    else "unknown",
                    "method": "CVSSv31",
                    "vector": cve_meta.cvss_v3_vector,
                }
            )

        # Add EPSS as supplemental rating
        epss = assessment.evidence.graph_evidence.exploitability
        if epss.epss_score:
            ratings.append(
                {
                    "source": {"name": "FIRST EPSS"},
                    "score": epss.epss_score * 10,  # Convert 0-1 to 0-10 scale
                    "severity": self._epss_to_severity(epss.epss_score),
                    "method": "other",
                    "vector": f"EPSS:{epss.epss_score:.6f}",
                }
            )

        return ratings

    def _build_cwes(self, assessment: VEXAssessment) -> List[int]:
        """
        Build CWE list.

        Args:
            assessment: VEX assessment

        Returns:
            list: CWE IDs (integers)
        """
        cwes = assessment.evidence.graph_evidence.cwe_mappings

        return [int(cwe.cwe_id.replace("CWE-", "")) for cwe in cwes if "CWE-" in cwe.cwe_id]

    def _build_analysis(self, assessment: VEXAssessment) -> Dict[str, Any]:
        """
        Build CycloneDX analysis section (VEX data).

        This is the core VEX assessment.

        Args:
            assessment: VEX assessment

        Returns:
            dict: Analysis section
        """
        analysis = {
            "state": self._map_vex_status(assessment.status),
            "detail": assessment.impact_summary,
        }

        # Add justification if not_affected
        if assessment.justification:
            analysis["justification"] = self._map_justification(assessment.justification)

        # Add response actions
        if assessment.response:
            analysis["response"] = [self._map_response(r) for r in assessment.response]

        return analysis

    def _build_advisories(self, assessment: VEXAssessment) -> List[Dict[str, Any]]:
        """
        Build advisories section.

        Args:
            assessment: VEX assessment

        Returns:
            list: Advisories
        """
        remediation = assessment.evidence.graph_evidence.remediation
        advisories = []

        if remediation.vendor_advisory_url:
            advisories.append(
                {
                    "title": "Vendor Security Advisory",
                    "url": remediation.vendor_advisory_url,
                }
            )

        return advisories

    def _build_evidence_properties(self, assessment: VEXAssessment) -> List[Dict[str, str]]:
        """
        Build Complira evidence properties (extension).

        CycloneDX allows custom properties for tool-specific data.
        We use this to embed complete evidence for auditability.

        Args:
            assessment: VEX assessment

        Returns:
            list: Property objects
        """
        properties = []

        # Evidence completeness
        properties.append(
            {
                "name": "complira:evidence:tier_1_complete",
                "value": str(assessment.evidence.tier_1_complete),
            }
        )
        properties.append(
            {
                "name": "complira:evidence:tier_2_complete",
                "value": str(assessment.evidence.tier_2_complete),
            }
        )
        properties.append(
            {
                "name": "complira:evidence:completeness",
                "value": assessment.evidence.graph_evidence.evidence_completeness,
            }
        )

        # KEV status
        kev = assessment.evidence.graph_evidence.kev_evidence
        properties.append(
            {
                "name": "complira:evidence:kev:in_catalog",
                "value": str(kev.in_kev),
            }
        )
        if kev.in_kev:
            properties.append(
                {
                    "name": "complira:evidence:kev:due_date",
                    "value": kev.kev_due_date.isoformat() if kev.kev_due_date else "",
                }
            )

        # ATT&CK techniques
        if assessment.evidence.graph_evidence.attack_techniques:
            techniques = ",".join(
                [t.technique_id for t in assessment.evidence.graph_evidence.attack_techniques]
            )
            properties.append(
                {
                    "name": "complira:evidence:attack_techniques",
                    "value": techniques,
                }
            )

        # Mitigation controls
        if assessment.evidence.graph_evidence.mitigation_controls:
            controls = ",".join(
                [c.control_id for c in assessment.evidence.graph_evidence.mitigation_controls]
            )
            properties.append(
                {
                    "name": "complira:evidence:mitigation_controls",
                    "value": controls,
                }
            )

        # Evidence citations
        if assessment.evidence_citations:
            properties.append(
                {
                    "name": "complira:evidence:citations",
                    "value": ",".join(assessment.evidence_citations),
                }
            )

        # LLM provenance
        if assessment.llm_model:
            properties.append(
                {
                    "name": "complira:llm:model",
                    "value": assessment.llm_model,
                }
            )

        return properties

    # ========== Mapping Helpers ==========

    def _map_vex_status(self, status: VEXStatus) -> str:
        """
        Map VEXStatus enum to CycloneDX state.

        Args:
            status: VEX status

        Returns:
            str: CycloneDX state
        """
        mapping = {
            VEXStatus.AFFECTED: "exploitable",
            VEXStatus.NOT_AFFECTED: "not_affected",
            VEXStatus.UNDER_INVESTIGATION: "in_triage",
            VEXStatus.FIXED: "resolved",
        }
        return mapping.get(status, "in_triage")

    def _map_justification(self, justification: VEXJustification) -> str:
        """
        Map VEXJustification enum to CycloneDX justification.

        Args:
            justification: VEX justification

        Returns:
            str: CycloneDX justification
        """
        # CycloneDX uses snake_case
        return justification.value

    def _map_response(self, response: VEXResponse) -> str:
        """
        Map VEXResponse enum to CycloneDX response.

        Args:
            response: VEX response

        Returns:
            str: CycloneDX response
        """
        # CycloneDX uses snake_case
        return response.value

    def _epss_to_severity(self, epss_score: float) -> str:
        """
        Convert EPSS score to severity label.

        Args:
            epss_score: EPSS score (0-1)

        Returns:
            str: Severity label
        """
        if epss_score >= 0.5:
            return "critical"
        elif epss_score >= 0.2:
            return "high"
        elif epss_score >= 0.05:
            return "medium"
        else:
            return "low"

    def _parse_purl(self, purl: str) -> Dict[str, str]:
        """
        Parse PURL to extract name and version.

        Args:
            purl: Package URL

        Returns:
            dict: {name, version, type}
        """
        # Simple parsing - production should use packageurl-python
        parts = purl.split("/")
        name_version = parts[-1] if parts else purl

        if "@" in name_version:
            name, version = name_version.split("@", 1)
        else:
            name = name_version
            version = "unknown"

        purl_type = purl.split(":")[1].split("/")[0] if ":" in purl else "generic"

        return {"name": name, "version": version, "type": purl_type}


# ========== Export ==========

__all__ = ["CycloneDXFormatter"]
```

## 6. VEX Validator

**File:** `/Users/venkatapydialli/Documents/cybersecurity-compliance-app/src/complira_graph/validators/vex_validator.py`

```python
"""
VEX Evidence Validator.

Validates evidence completeness and regulatory compliance.

Validation Layers:
1. Tier 1 Evidence Completeness (Critical)
2. Tier 2 Evidence Completeness (Important)
3. Graph Reference Integrity
4. Evidence Consistency
5. Regulatory Compliance (FDA/CRA/IEC)

Usage:
    from complira_graph.validators.vex_validator import VEXValidator

    validator = VEXValidator()
    result = validator.validate_evidence(evidence)

    if not result.valid:
        print(f"Missing evidence: {result.missing_evidence}")
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import structlog

from complira_graph.models.vex_evidence import (
    VulnerabilityEvidence,
    EvidenceValidationResult,
    GraphEvidence,
    CVEMetadata,
)

logger = structlog.get_logger()


class VEXValidator:
    """
    Validator for VEX evidence packages.

    Ensures evidence meets regulatory requirements.
    """

    def __init__(self):
        """Initialize validator."""
        self.logger = structlog.get_logger()

    def validate_evidence(self, evidence: VulnerabilityEvidence) -> EvidenceValidationResult:
        """
        Validate complete evidence package.

        Args:
            evidence: Vulnerability evidence package

        Returns:
            EvidenceValidationResult: Validation result
        """
        self.logger.debug("Validating evidence package")

        # Tier 1 validation
        tier_1_valid, tier_1_missing = self._validate_tier_1(evidence)

        # Tier 2 validation
        tier_2_valid, tier_2_missing = self._validate_tier_2(evidence)

        # Graph reference validation
        invalid_refs = self._validate_graph_references(evidence)

        # Consistency validation
        inconsistencies = self._validate_consistency(evidence)

        # Regulatory compliance
        regulatory_compliance = self._validate_regulatory_compliance(evidence)

        # Overall validation
        valid = tier_1_valid and not invalid_refs and not inconsistencies

        result = EvidenceValidationResult(
            valid=valid,
            tier_1_valid=tier_1_valid,
            tier_2_valid=tier_2_valid,
            missing_evidence=tier_1_missing + tier_2_missing,
            invalid_references=invalid_refs,
            inconsistencies=inconsistencies,
            regulatory_compliance=regulatory_compliance,
        )

        self.logger.info(
            "Evidence validation complete",
            valid=valid,
            tier_1_valid=tier_1_valid,
            tier_2_valid=tier_2_valid,
        )

        return result

    # ========== Tier 1 Validation (Critical) ==========

    def _validate_tier_1(
        self, evidence: VulnerabilityEvidence
    ) -> tuple[bool, List[str]]:
        """
        Validate Tier 1 evidence completeness.

        Tier 1 Requirements (Critical):
        - CVE metadata with CVSS score
        - At least one CWE mapping
        - KEV evidence (even if not in KEV)
        - Component presence validation
        - Exploitability evidence

        Args:
            evidence: Evidence package

        Returns:
            tuple: (is_valid, missing_evidence_list)
        """
        missing = []

        # Check CVE metadata
        cve_meta = evidence.cve_metadata
        if not cve_meta.cvss_v3_score and not cve_meta.cvss_v2_score:
            missing.append("cve_metadata.cvss_score")

        # Check CWE mappings
        if not evidence.graph_evidence.cwe_mappings:
            missing.append("graph_evidence.cwe_mappings")

        # KEV evidence always present (boolean field)
        # Component presence always present (boolean field)

        # Exploitability - EPSS is preferred but not required
        # (Some CVEs don't have EPSS yet)

        is_valid = len(missing) == 0

        return is_valid, missing

    # ========== Tier 2 Validation (Important) ==========

    def _validate_tier_2(
        self, evidence: VulnerabilityEvidence
    ) -> tuple[bool, List[str]]:
        """
        Validate Tier 2 evidence completeness.

        Tier 2 Requirements (Important):
        - Attack techniques (if graph path exists)
        - Mitigation controls (if attack techniques exist)
        - Remediation evidence (optional)
        - Compliance violations (optional)

        Args:
            evidence: Evidence package

        Returns:
            tuple: (is_valid, missing_evidence_list)
        """
        missing = []

        # Tier 2 is "best effort" - not all CVEs have complete chains
        # We only flag missing if CWE exists but no attack chain
        if evidence.graph_evidence.cwe_mappings:
            if not evidence.graph_evidence.attack_techniques:
                missing.append("graph_evidence.attack_techniques")

            # If we have attack techniques but no controls, flag it
            if (
                evidence.graph_evidence.attack_techniques
                and not evidence.graph_evidence.mitigation_controls
            ):
                missing.append("graph_evidence.mitigation_controls")

        # Remediation is optional (not all CVEs have fixes)
        # Compliance violations are optional (not all CVEs violate requirements)

        # Tier 2 is valid if we have at least some evidence
        is_valid = bool(
            evidence.graph_evidence.attack_techniques
            or evidence.graph_evidence.mitigation_controls
            or evidence.graph_evidence.compliance_violations
        )

        return is_valid, missing

    # ========== Graph Reference Validation ==========

    def _validate_graph_references(
        self, evidence: VulnerabilityEvidence
    ) -> List[str]:
        """
        Validate graph document references.

        Checks that all graph_id fields reference valid documents.

        Args:
            evidence: Evidence package

        Returns:
            list: Invalid reference IDs
        """
        invalid = []

        # CVE metadata graph_id
        if not self._is_valid_graph_id(evidence.cve_metadata.graph_id):
            invalid.append(f"cve_metadata.graph_id: {evidence.cve_metadata.graph_id}")

        # CWE mappings
        for i, cwe in enumerate(evidence.graph_evidence.cwe_mappings):
            if not self._is_valid_graph_id(cwe.graph_id):
                invalid.append(f"cwe_mappings[{i}].graph_id: {cwe.graph_id}")
            if not self._is_valid_graph_id(cwe.edge_id):
                invalid.append(f"cwe_mappings[{i}].edge_id: {cwe.edge_id}")

        # KEV evidence
        if evidence.graph_evidence.kev_evidence.kev_graph_id:
            if not self._is_valid_graph_id(
                evidence.graph_evidence.kev_evidence.kev_graph_id
            ):
                invalid.append(
                    f"kev_evidence.kev_graph_id: {evidence.graph_evidence.kev_evidence.kev_graph_id}"
                )

        # EPSS evidence
        if evidence.graph_evidence.exploitability.epss_graph_id:
            if not self._is_valid_graph_id(
                evidence.graph_evidence.exploitability.epss_graph_id
            ):
                invalid.append(
                    f"exploitability.epss_graph_id: {evidence.graph_evidence.exploitability.epss_graph_id}"
                )

        # Attack techniques
        for i, attack in enumerate(evidence.graph_evidence.attack_techniques):
            if not self._is_valid_graph_id(attack.technique_graph_id):
                invalid.append(
                    f"attack_techniques[{i}].technique_graph_id: {attack.technique_graph_id}"
                )

        # Mitigation controls
        for i, control in enumerate(evidence.graph_evidence.mitigation_controls):
            if not self._is_valid_graph_id(control.control_graph_id):
                invalid.append(
                    f"mitigation_controls[{i}].control_graph_id: {control.control_graph_id}"
                )

        # Compliance violations
        for i, violation in enumerate(evidence.graph_evidence.compliance_violations):
            if not self._is_valid_graph_id(violation.requirement_graph_id):
                invalid.append(
                    f"compliance_violations[{i}].requirement_graph_id: {violation.requirement_graph_id}"
                )

        return invalid

    def _is_valid_graph_id(self, graph_id: str) -> bool:
        """
        Check if graph ID is valid ArangoDB document ID.

        Valid format: collection_name/document_key

        Args:
            graph_id: Graph document ID

        Returns:
            bool: True if valid
        """
        if not graph_id:
            return False

        parts = graph_id.split("/")
        if len(parts) != 2:
            return False

        collection, key = parts
        if not collection or not key:
            return False

        return True

    # ========== Consistency Validation ==========

    def _validate_consistency(self, evidence: VulnerabilityEvidence) -> List[str]:
        """
        Validate evidence consistency.

        Checks for logical contradictions in evidence.

        Args:
            evidence: Evidence package

        Returns:
            list: Inconsistency descriptions
        """
        inconsistencies = []

        # Check: High CVSS + Low EPSS (unusual but not invalid)
        cvss = evidence.cve_metadata.cvss_v3_score or evidence.cve_metadata.cvss_v2_score
        epss = evidence.graph_evidence.exploitability.epss_score

        if cvss and epss:
            if cvss >= 9.0 and epss < 0.01:
                inconsistencies.append(
                    f"High CVSS ({cvss}) but very low EPSS ({epss}) - unusual pattern"
                )

        # Check: In KEV but not exploitable (contradiction)
        if evidence.graph_evidence.kev_evidence.in_kev:
            if evidence.graph_evidence.exploitability.exploit_available is False:
                inconsistencies.append(
                    "In KEV catalog but exploit_available=False - contradictory"
                )

        # Check: Attack techniques without CWE (should not happen)
        if evidence.graph_evidence.attack_techniques and not evidence.graph_evidence.cwe_mappings:
            inconsistencies.append(
                "Attack techniques present but no CWE mappings - invalid graph path"
            )

        # Check: Mitigation controls without attack techniques (should not happen)
        if (
            evidence.graph_evidence.mitigation_controls
            and not evidence.graph_evidence.attack_techniques
        ):
            inconsistencies.append(
                "Mitigation controls present but no attack techniques - invalid graph path"
            )

        return inconsistencies

    # ========== Regulatory Compliance Validation ==========

    def _validate_regulatory_compliance(
        self, evidence: VulnerabilityEvidence
    ) -> Dict[str, bool]:
        """
        Validate regulatory compliance.

        Checks evidence against FDA 524B, EU CRA, and IEC 62304 requirements.

        Args:
            evidence: Evidence package

        Returns:
            dict: Compliance status per framework
        """
        compliance = {}

        # FDA 524B Requirements
        compliance["FDA_524B"] = self._validate_fda_524b(evidence)

        # EU CRA Requirements
        compliance["CRA"] = self._validate_cra(evidence)

        # IEC 62304 Requirements
        compliance["IEC_62304"] = self._validate_iec_62304(evidence)

        return compliance

    def _validate_fda_524b(self, evidence: VulnerabilityEvidence) -> bool:
        """
        Validate FDA 524B requirements.

        FDA Requirements:
        - CVSS scoring present
        - KEV status checked
        - Exploitability assessment (EPSS)
        - Remediation plan (if applicable)

        Args:
            evidence: Evidence package

        Returns:
            bool: True if FDA compliant
        """
        # CVSS required
        if not evidence.cve_metadata.cvss_v3_score and not evidence.cve_metadata.cvss_v2_score:
            return False

        # KEV status checked (always present)
        # EPSS preferred but not required

        # If in KEV, remediation plan required
        if evidence.graph_evidence.kev_evidence.in_kev:
            if not evidence.graph_evidence.remediation:
                return False

        return True

    def _validate_cra(self, evidence: VulnerabilityEvidence) -> bool:
        """
        Validate EU CRA requirements.

        CRA Requirements:
        - Weakness classification (CWE)
        - Attack technique correlation (ATT&CK)
        - Risk assessment (CVSS + EPSS)
        - Compliance violation tracking

        Args:
            evidence: Evidence package

        Returns:
            bool: True if CRA compliant
        """
        # CWE required
        if not evidence.graph_evidence.cwe_mappings:
            return False

        # CVSS required
        if not evidence.cve_metadata.cvss_v3_score and not evidence.cve_metadata.cvss_v2_score:
            return False

        # ATT&CK techniques preferred (not required)
        # Compliance violations optional

        return True

    def _validate_iec_62304(self, evidence: VulnerabilityEvidence) -> bool:
        """
        Validate IEC 62304 requirements.

        IEC 62304 Requirements:
        - Risk assessment (CVSS)
        - Weakness classification (CWE)
        - Impact analysis
        - Mitigation controls

        Args:
            evidence: Evidence package

        Returns:
            bool: True if IEC 62304 compliant
        """
        # CVSS required
        if not evidence.cve_metadata.cvss_v3_score and not evidence.cve_metadata.cvss_v2_score:
            return False

        # CWE required
        if not evidence.graph_evidence.cwe_mappings:
            return False

        # Mitigation controls preferred (not required)

        return True


# ========== Export ==========

__all__ = ["VEXValidator"]
```

## 7. AQL Query Library

**File:** `/Users/venkatapydialli/Documents/cybersecurity-compliance-app/src/complira_graph/queries/vex_evidence_queries.py`

Complete AQL query templates for evidence collection:

```python
"""
AQL Query Library for VEX Evidence Collection.

Provides reusable, parameterized AQL queries for collecting
evidence from the knowledge graph.

All queries use bind variables (@param) to prevent AQL injection.

Usage:
    from complira_graph.queries.vex_evidence_queries import VEXEvidenceQueries

    queries = VEXEvidenceQueries()

    # Execute CVE → CWE query
    cursor = db.aql.execute(
        queries.CVE_TO_CWE,
        bind_vars={"cve_key": "cve-2021-44228"}
    )
"""


class VEXEvidenceQueries:
    """
    AQL query templates for VEX evidence collection.
    """

    # ========== Tier 1 Queries (Critical Evidence) ==========

    CVE_METADATA = """
    FOR vuln IN vulnerabilities
        FILTER vuln._key == @cve_key
        LIMIT 1
        RETURN vuln
    """

    CVE_TO_CWE = """
    FOR vuln IN vulnerabilities
        FILTER vuln._key == @cve_key
        FOR cwe, edge IN 1..1 OUTBOUND vuln has_weakness
            RETURN {
                cwe: cwe,
                edge: edge
            }
    """

    KEV_STATUS = """
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

    COMPONENT_PRESENCE = """
    FOR component IN components
        FILTER component.purl == @purl
        LIMIT 1
        RETURN component
    """

    EPSS_SCORE = """
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

    # ========== Tier 2 Queries (Important Evidence) ==========

    CVE_TO_ATTACK_FULL_CHAIN = """
    FOR vuln IN vulnerabilities
        FILTER vuln._key == @cve_key
        FOR cwe IN 1..1 OUTBOUND vuln has_weakness
            FOR capec IN 1..1 INBOUND cwe capec_relates_to_cwe
                FOR attack IN 1..1 OUTBOUND capec capec_maps_to_attack
                    RETURN DISTINCT {
                        cve_id: vuln._id,
                        cwe_id: cwe._id,
                        cwe: cwe,
                        capec_id: capec._id,
                        capec: capec,
                        attack_id: attack._id,
                        attack: attack
                    }
    """

    ATTACK_TO_CONTROLS = """
    FOR technique_id IN @technique_ids
        FOR control IN 1..1 OUTBOUND technique_id technique_mitigated_by_control
            RETURN DISTINCT {
                technique_id: technique_id,
                control: control
            }
    """

    COMPLIANCE_VIOLATIONS = """
    FOR vuln IN vulnerabilities
        FILTER vuln._key == @cve_key
        FOR req, edge IN 1..1 OUTBOUND vuln violates_requirement
            RETURN {
                requirement: req,
                edge: edge
            }
    """

    # ========== Advanced Queries ==========

    # Full graph traversal (CVE → CWE → CAPEC → ATT&CK → Controls → Requirements)
    FULL_THREAT_CHAIN = """
    FOR vuln IN vulnerabilities
        FILTER vuln._key == @cve_key

        // Traverse to CWEs
        FOR cwe, has_weakness_edge IN 1..1 OUTBOUND vuln has_weakness

            // Traverse to CAPEC
            FOR capec, capec_cwe_edge IN 1..1 INBOUND cwe capec_relates_to_cwe

                // Traverse to ATT&CK
                FOR attack, capec_attack_edge IN 1..1 OUTBOUND capec capec_maps_to_attack

                    // Traverse to Controls
                    FOR control, mitigation_edge IN 1..1 OUTBOUND attack technique_mitigated_by_control

                        // Traverse to Requirements
                        FOR req, control_req_edge IN 1..1 OUTBOUND control maps_to_requirement

                            RETURN {
                                cve: vuln,
                                cwe: cwe,
                                capec: capec,
                                attack: attack,
                                control: control,
                                requirement: req,
                                edges: {
                                    has_weakness: has_weakness_edge,
                                    capec_cwe: capec_cwe_edge,
                                    capec_attack: capec_attack_edge,
                                    mitigation: mitigation_edge,
                                    control_req: control_req_edge
                                }
                            }
    """

    # Multi-hop shortest path (CVE → specific control)
    SHORTEST_PATH_TO_CONTROL = """
    FOR v, e IN OUTBOUND SHORTEST_PATH
        @start_doc TO @end_doc
        has_weakness, capec_relates_to_cwe, capec_maps_to_attack, technique_mitigated_by_control
        RETURN {vertex: v, edge: e}
    """

    # Batch CVE enrichment (multiple CVEs at once)
    BATCH_CVE_EVIDENCE = """
    FOR cve_key IN @cve_keys
        LET vuln = FIRST(
            FOR v IN vulnerabilities
                FILTER v._key == cve_key
                RETURN v
        )

        LET cwes = (
            FOR cwe IN 1..1 OUTBOUND vuln has_weakness
                RETURN cwe
        )

        LET kev = FIRST(
            FOR k IN 1..1 OUTBOUND vuln exploited_in_wild
                RETURN k
        )

        LET epss = FIRST(
            FOR e IN 1..1 OUTBOUND vuln has_epss
                SORT e.date DESC
                LIMIT 1
                RETURN e
        )

        RETURN {
            cve: vuln,
            cwes: cwes,
            kev: kev,
            epss: epss
        }
    """


# ========== Query Helpers ==========

def build_custom_traversal(
    start_collection: str,
    edge_collections: list[str],
    max_depth: int = 4,
    filters: dict = None,
) -> str:
    """
    Build custom AQL traversal query.

    Args:
        start_collection: Starting collection
        edge_collections: List of edge collections to traverse
        max_depth: Maximum depth
        filters: Optional filters

    Returns:
        str: AQL query
    """
    query = f"""
    FOR v, e, p IN 1..{max_depth} OUTBOUND @start_doc {', '.join(edge_collections)}
        OPTIONS {{uniqueVertices: "global", bfs: true}}
    """

    if filters:
        for field, value in filters.items():
            query += f"\n    FILTER v.{field} == @{field}"

    query += "\n    RETURN {vertex: v, edge: e, path: p}"

    return query


# ========== Export ==========

__all__ = ["VEXEvidenceQueries", "build_custom_traversal"]
```

---

*[Document continues with implementation examples and API specifications...]*
