"""
VEX Synthesizer V2 - Evidence-Grounded VEX Generation.

Enhanced VEX synthesizer that generates regulatory-grade VEX assessments using
structured evidence from the knowledge graph. Replaces v1 with evidence-first approach.

Key Improvements Over V1:
- Evidence-first approach (not LLM-first)
- Structured input/output via Pydantic schemas
- Graph provenance citations in all justifications
- Full regulatory compliance (FDA 524B, EU CRA, IEC 62304)
- Multi-format output (CycloneDX + CSAF)

Architecture:
1. Evidence Collection → VulnerabilityEvidence package
2. Evidence-Based Synthesis → Claude Sonnet 4.5
3. Structured Output → VEXAssessment (Pydantic enforced)
4. Validation → Regulatory compliance checks
5. Multi-Format Export → CycloneDX + CSAF

Model: Claude Sonnet 4.5 (claude-sonnet-4-20250514)
Output: VEXAssessment with complete evidence chain

Author: Complira Development Team
Version: 2.0
Compliance: FDA 524B, EU CRA, IEC 62304
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
import json
import structlog

from anthropic import Anthropic
import instructor

from complira_graph.models.vex_evidence import (
    VulnerabilityEvidence,
    VEXAssessment,
    VEXStatus,
    VEXJustification,
    VEXResponse,
    CVEMetadata,
    GraphEvidence,
    CycloneDXVEX,
    CSAFVEX,
)

logger = structlog.get_logger()


class VEXSynthesizerV2:
    """
    Enhanced VEX synthesizer with evidence grounding.

    Uses Claude Sonnet 4.5 to generate VEX assessments from structured
    evidence collected from the knowledge graph.

    Key improvements over V1:
    - Evidence-first approach (not LLM-first)
    - Structured output via Pydantic schemas
    - Graph provenance citations
    - Regulatory compliance (FDA/CRA/IEC)
    - Multi-format output (CycloneDX + CSAF)

    Example:
        >>> from anthropic import Anthropic
        >>> client = Anthropic(api_key="...")
        >>> synthesizer = VEXSynthesizerV2(client)
        >>>
        >>> # Evidence collected from graph traversal
        >>> evidence = VulnerabilityEvidence(...)
        >>>
        >>> # Generate VEX assessment
        >>> assessment = await synthesizer.synthesize_vex(
        ...     evidence=evidence,
        ...     component_purl="pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1"
        ... )
        >>>
        >>> # Assessment includes graph-backed justifications
        >>> print(assessment.impact_summary)
        >>> print(assessment.evidence_citations)

    Attributes:
        MODEL: Claude Sonnet 4.5 model ID
        MAX_TOKENS: Maximum response tokens (4096)
        TEMPERATURE: Low temperature for consistency (0.3)
        client: Anthropic API client
        instructor_client: Instructor-wrapped client for structured outputs
    """

    # Model configuration
    MODEL = "claude-sonnet-4-20250514"  # Claude Sonnet 4.5
    MAX_TOKENS = 4096
    TEMPERATURE = 0.3  # Low for consistency

    def __init__(self, anthropic_client: Anthropic):
        """
        Initialize VEX synthesizer with Anthropic client.

        Args:
            anthropic_client: Configured Anthropic API client

        Example:
            >>> from anthropic import Anthropic
            >>> client = Anthropic(api_key="sk-...")
            >>> synthesizer = VEXSynthesizerV2(client)
        """
        self.client = anthropic_client
        # Wrap client with instructor for structured outputs
        self.instructor_client = instructor.from_anthropic(self.client)

        logger.info(
            "Initialized VEX Synthesizer V2",
            model=self.MODEL,
            max_tokens=self.MAX_TOKENS,
            temperature=self.TEMPERATURE,
        )

    async def synthesize_vex(
        self,
        evidence: VulnerabilityEvidence,
        component_purl: str
    ) -> VEXAssessment:
        """
        Generate VEX assessment from structured evidence.

        This is the main entry point for VEX generation. It takes a complete
        evidence package (collected from graph traversal) and generates a
        regulatory-grade VEX assessment with graph-backed justifications.

        Flow:
        1. Format evidence into structured prompt
        2. Call Claude with Pydantic schema enforcement
        3. LLM generates assessment with evidence citations
        4. Validate assessment completeness
        5. Return structured VEXAssessment

        Args:
            evidence: Complete vulnerability evidence package from graph
            component_purl: Component Package URL (e.g., pkg:maven/...)

        Returns:
            VEXAssessment: Complete assessment with graph-backed justifications

        Raises:
            ValueError: If evidence validation fails
            Exception: If LLM API call fails

        Example:
            >>> evidence = VulnerabilityEvidence(
            ...     cve_metadata=CVEMetadata(...),
            ...     graph_evidence=GraphEvidence(...),
            ...     tier_1_complete=True,
            ...     tier_2_complete=True
            ... )
            >>>
            >>> assessment = await synthesizer.synthesize_vex(
            ...     evidence=evidence,
            ...     component_purl="pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1"
            ... )
            >>>
            >>> # Assessment includes all required fields
            >>> assert assessment.status in [VEXStatus.AFFECTED, VEXStatus.NOT_AFFECTED]
            >>> assert len(assessment.evidence_citations) > 0
        """
        logger.info(
            "Synthesizing VEX assessment",
            cve=evidence.cve_metadata.cve_id,
            component=component_purl,
            tier_1_complete=evidence.tier_1_complete,
            tier_2_complete=evidence.tier_2_complete,
        )

        # Validate evidence completeness
        if not evidence.tier_1_complete:
            logger.warning(
                "Tier 1 evidence incomplete",
                cve=evidence.cve_metadata.cve_id,
            )
            raise ValueError(
                "Tier 1 (Critical) evidence must be complete for regulatory compliance"
            )

        # Build structured prompt with evidence
        system_prompt = self._build_system_prompt()
        evidence_prompt = self._build_evidence_prompt(evidence, component_purl)

        # Call Claude with Pydantic schema enforcement
        try:
            logger.debug(
                "Calling Claude API with structured output",
                model=self.MODEL,
                cve=evidence.cve_metadata.cve_id,
            )

            # Use instructor for Pydantic schema enforcement
            response = self.instructor_client.messages.create(
                model=self.MODEL,
                max_tokens=self.MAX_TOKENS,
                temperature=self.TEMPERATURE,
                system=system_prompt,
                messages=[{
                    "role": "user",
                    "content": evidence_prompt
                }],
                response_model=VEXAssessment  # Pydantic schema enforcement!
            )

            # Response is already a validated VEXAssessment instance
            assessment = response

            # Validate assessment for regulatory compliance
            self._validate_assessment(assessment, evidence)

            logger.info(
                "VEX assessment generated successfully",
                cve=evidence.cve_metadata.cve_id,
                status=assessment.status,
                citations=len(assessment.evidence_citations),
            )

            return assessment

        except Exception as e:
            logger.error(
                "VEX synthesis failed",
                cve=evidence.cve_metadata.cve_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    def _build_system_prompt(self) -> str:
        """
        Build system prompt for VEX synthesis.

        The system prompt defines the role, task, and critical rules for
        VEX generation. It emphasizes evidence-based analysis and regulatory
        compliance.

        Key instructions:
        - You are a cybersecurity expert
        - Analyze provided evidence (NOT speculation)
        - Cite graph IDs for all claims
        - Follow VEX status definitions
        - Provide actionable recommendations
        - Meet regulatory requirements (FDA/CRA/IEC)

        Returns:
            str: System prompt text
        """
        return """You are a cybersecurity analyst generating VEX (Vulnerability Exploitability eXchange) assessments for regulatory compliance.

Your task is to analyze STRUCTURED EVIDENCE from a knowledge graph and determine:
1. VEX Status (affected, not_affected, under_investigation, fixed)
2. Justification (if not_affected, explain WHY using evidence)
3. Impact Analysis (severity, exploitability, blast radius)
4. Mitigation Recommendations (cite specific controls from evidence)

CRITICAL RULES:
- ONLY use provided evidence (no speculation)
- CITE graph IDs for all claims (e.g., "per CWE-79 [weaknesses/CWE_79]")
- Use EPSS/KEV for exploitability assessment
- Reference ATT&CK techniques and NIST controls when available
- Follow regulatory requirements (FDA 524B, EU CRA, IEC 62304)
- Provide actionable, specific recommendations

EVIDENCE STRUCTURE:
- CVE Metadata: CVSS score, severity, description
- CWE Mappings: Weakness classifications with graph IDs
- KEV Status: Known exploitation (CISA catalog)
- EPSS Scores: Exploit probability
- Component Presence: Is vulnerable component in SBOM?
- ATT&CK Techniques: Attack methods (from CWE→CAPEC→ATT&CK chain)
- Mitigation Controls: NIST 800-53 controls (from ATT&CK→Controls)
- Compliance Violations: Regulatory requirements violated

VEX STATUS DEFINITIONS:
- affected: Component is vulnerable and exploitable
- not_affected: Component contains vulnerability but is NOT exploitable
- under_investigation: Assessment in progress (use sparingly)
- fixed: Vulnerability has been remediated

JUSTIFICATION (for not_affected):
- component_not_present: Vulnerable component is not included
- vulnerable_code_not_present: Vulnerable code paths do not exist
- vulnerable_code_not_in_execute_path: Code exists but never executes
- vulnerable_code_cannot_be_controlled_by_adversary: Code runs but not exploitable
- inline_mitigations_already_exist: Mitigations prevent exploitation

RESPONSE ACTIONS (for affected):
- update: Upgrade to fixed version
- workaround_available: Apply workaround mitigation
- rollback: Downgrade to non-vulnerable version
- can_not_fix: No fix available
- will_not_fix: Fix exists but won't be applied

OUTPUT FORMAT:
Return structured VEXAssessment with:
- status: VEX status enum
- justification: Justification enum (if not_affected)
- response: Response actions (if affected)
- impact_summary: 2-3 sentence impact analysis
- exploitability_analysis: EPSS/KEV-based exploitability
- mitigation_recommendations: Cite specific controls
- evidence_citations: List of graph IDs used

REGULATORY COMPLIANCE:
- FDA 524B: Requires CVSS scoring, KEV tracking, remediation plans
- EU CRA: Requires vulnerability handling, weakness classification
- IEC 62304: Requires risk assessment, safety impact analysis
"""

    def _build_evidence_prompt(
        self,
        evidence: VulnerabilityEvidence,
        component_purl: str
    ) -> str:
        """
        Build user prompt with formatted evidence.

        Formats the complete evidence package into a structured prompt that
        presents all available evidence to the LLM for analysis.

        Format:
        - CVE metadata (CVSS, severity, description)
        - Component presence (in SBOM?)
        - CWE mappings (with graph IDs)
        - KEV status (exploited in wild?)
        - EPSS score (probability)
        - ATT&CK techniques (attack methods)
        - NIST controls (mitigations)
        - Compliance violations (FDA/CRA/IEC)

        Args:
            evidence: Complete vulnerability evidence package
            component_purl: Component Package URL

        Returns:
            str: Formatted evidence prompt
        """
        cve = evidence.cve_metadata
        graph = evidence.graph_evidence

        # Start with core identification
        prompt = f"""Analyze this vulnerability and generate a VEX assessment:

## CVE Metadata
- CVE ID: {cve.cve_id}
- CVSS Score: {cve.cvss_v3_score or cve.cvss_v2_score or 'N/A'} ({cve.cvss_v3_severity or 'UNKNOWN'})
- CVSS Vector: {cve.cvss_v3_vector or 'N/A'}
- Description: {cve.description}
- Published: {cve.published_date or 'N/A'}
- Last Modified: {cve.last_modified_date or 'N/A'}
- Graph ID: {cve.graph_id}

## Component Presence
- PURL: {component_purl}
- Component Name: {graph.component_presence.component_name}
- Component Version: {graph.component_presence.component_version}
- In SBOM: {graph.component_presence.in_sbom}
- Deployment Scope: {graph.component_presence.deployment_scope or 'unknown'}
- Deployment Criticality: {graph.component_presence.deployment_criticality or 'unknown'}
"""

        # Add SBOM reference if available
        if graph.component_presence.sbom_component_id:
            prompt += f"- SBOM Component ID: {graph.component_presence.sbom_component_id}\n"

        # Add CWE mappings (Tier 1 - Critical)
        prompt += "\n## Weaknesses (CWE)\n"
        if graph.cwe_mappings:
            for cwe in graph.cwe_mappings:
                prompt += f"""- {cwe.cwe_id}: {cwe.name}
  Description: {cwe.description[:200]}...
  Weakness Type: {cwe.weakness_type or 'N/A'}
  Likelihood: {cwe.likelihood or 'N/A'}
  Graph ID: {cwe.graph_id}
  Edge ID: {cwe.edge_id}
"""
        else:
            prompt += "- No CWE mappings available\n"

        # Add KEV evidence (Tier 1 - Critical)
        prompt += "\n## Known Exploited Vulnerabilities (KEV)\n"
        if graph.kev_evidence.in_kev:
            prompt += f"""- **IN CISA KEV CATALOG** (Actively Exploited in Wild)
- Date Added: {graph.kev_evidence.kev_date_added}
- Remediation Deadline: {graph.kev_evidence.kev_due_date}
- Required Action: {graph.kev_evidence.kev_required_action}
- Ransomware Use: {graph.kev_evidence.kev_known_ransomware}
- Graph ID: {graph.kev_evidence.kev_graph_id}
"""
        else:
            prompt += "- Not in CISA KEV catalog (no known active exploitation)\n"

        # Add exploitability evidence (Tier 1 - Critical)
        prompt += "\n## Exploitability\n"
        if graph.exploitability.epss_score is not None:
            prompt += f"""- EPSS Score: {graph.exploitability.epss_score:.5f} ({graph.exploitability.epss_percentile:.2%} percentile)
- EPSS Date: {graph.exploitability.epss_date}
- Exploit Available: {graph.exploitability.exploit_available or 'Unknown'}
- Exploit Maturity: {graph.exploitability.exploit_maturity or 'Unknown'}
"""
            if graph.exploitability.epss_graph_id:
                prompt += f"- Graph ID: {graph.exploitability.epss_graph_id}\n"
        else:
            prompt += "- No EPSS data available\n"

        # Add Tier 2 evidence if available
        if evidence.tier_2_complete:

            # ATT&CK techniques
            if graph.attack_techniques:
                prompt += "\n## ATT&CK Techniques (Attack Methods)\n"
                for tech in graph.attack_techniques:
                    prompt += f"""- {tech.technique_id}: {tech.technique_name}
  Tactic: {tech.tactic}
  Description: {tech.description[:150]}...
  Graph ID: {tech.technique_graph_id}
  CAPEC: {tech.capec_id or 'N/A'}
  Graph Path: {' → '.join(tech.graph_path)}
"""

            # Mitigation controls
            if graph.mitigation_controls:
                prompt += "\n## Mitigation Controls (Security Measures)\n"
                for ctrl in graph.mitigation_controls:
                    prompt += f"""- {ctrl.control_id}: {ctrl.control_title}
  Framework: {ctrl.framework}
  Family: {ctrl.control_family or 'N/A'}
  Effectiveness: {ctrl.mitigation_effectiveness or 'N/A'}
  Graph ID: {ctrl.control_graph_id}
  Graph Path: {' → '.join(ctrl.graph_path)}
"""

            # Remediation information
            if graph.remediation:
                prompt += "\n## Remediation\n"
                rem = graph.remediation
                prompt += f"""- Fix Available: {rem.fix_available}
- Fixed Version: {rem.fix_version or 'N/A'}
- Upgrade Path: {rem.upgrade_path or 'N/A'}
- Workaround Available: {rem.workaround_available}
"""
                if rem.workaround_description:
                    prompt += f"- Workaround: {rem.workaround_description}\n"
                if rem.vendor_advisory_url:
                    prompt += f"- Vendor Advisory: {rem.vendor_advisory_url}\n"
                if rem.patch_complexity:
                    prompt += f"- Patch Complexity: {rem.patch_complexity}\n"

            # Compliance violations
            if graph.compliance_violations:
                prompt += "\n## Compliance Violations\n"
                for violation in graph.compliance_violations:
                    prompt += f"""- {violation.requirement_id}: {violation.requirement_title}
  Framework: {violation.framework}
  Obligation Level: {violation.obligation_level}
  Deadline: {violation.deadline or 'N/A'}
  Severity: {violation.violation_severity or 'N/A'}
  Graph ID: {violation.requirement_graph_id}
"""

        # Add evidence completeness summary
        prompt += f"""
## Evidence Completeness
- Tier 1 (Critical): {'Complete' if evidence.tier_1_complete else 'Incomplete'}
- Tier 2 (Important): {'Complete' if evidence.tier_2_complete else 'Incomplete'}
- Graph Evidence: {graph.evidence_completeness}
- Collection Time: {graph.collection_timestamp}

## Your Task
Based on the evidence above, generate a complete VEX assessment for:
- Vulnerability: {cve.cve_id}
- Component: {component_purl}

Determine the VEX status, provide evidence-backed justification, and recommend specific mitigations.
Remember to cite graph IDs in your analysis to maintain regulatory auditability.
"""

        return prompt

    def _validate_assessment(
        self,
        assessment: VEXAssessment,
        evidence: VulnerabilityEvidence
    ) -> None:
        """
        Validate VEX assessment for regulatory compliance.

        Performs additional validation beyond Pydantic schema validation
        to ensure regulatory requirements are met.

        Checks:
        - Status consistency (if in_sbom=False, must be not_affected)
        - Justification required (if status=not_affected)
        - Response required (if status=affected)
        - Evidence citations present
        - Impact summary not generic
        - Exploitability analysis not empty

        Args:
            assessment: Generated VEX assessment
            evidence: Original evidence package

        Raises:
            ValueError: If validation fails
        """
        logger.debug(
            "Validating VEX assessment",
            cve=assessment.vulnerability_id,
            status=assessment.status,
        )

        # Check status consistency with SBOM presence
        if not evidence.graph_evidence.component_presence.in_sbom:
            if assessment.status != VEXStatus.NOT_AFFECTED:
                raise ValueError(
                    f"Component not in SBOM but status is '{assessment.status}'. "
                    f"Must be 'not_affected' with justification 'component_not_present'"
                )
            if assessment.justification != VEXJustification.COMPONENT_NOT_PRESENT:
                raise ValueError(
                    f"Component not in SBOM but justification is '{assessment.justification}'. "
                    f"Must be 'component_not_present'"
                )

        # Check justification requirement
        if assessment.status == VEXStatus.NOT_AFFECTED:
            if not assessment.justification:
                raise ValueError(
                    "Justification required when status is 'not_affected' (VEX spec requirement)"
                )

        # Check response requirement
        if assessment.status == VEXStatus.AFFECTED:
            if not assessment.response or len(assessment.response) == 0:
                raise ValueError(
                    "At least one response action required when status is 'affected' "
                    "(FDA 524B requirement)"
                )

        # Check evidence citations
        if not assessment.evidence_citations or len(assessment.evidence_citations) == 0:
            raise ValueError(
                "Evidence citations required for regulatory compliance and auditability"
            )

        # Check impact summary quality
        if len(assessment.impact_summary) < 20:
            raise ValueError(
                f"Impact summary too short: {len(assessment.impact_summary)} chars. "
                f"Must be substantive (>20 chars)"
            )

        # Check exploitability analysis quality
        if len(assessment.exploitability_analysis) < 20:
            raise ValueError(
                f"Exploitability analysis too short: {len(assessment.exploitability_analysis)} chars. "
                f"Must be substantive (>20 chars)"
            )

        # Check KEV consistency
        if evidence.graph_evidence.kev_evidence.in_kev:
            # If in KEV, must be affected (unless there's a very strong justification)
            if assessment.status == VEXStatus.NOT_AFFECTED:
                logger.warning(
                    "KEV vulnerability marked as not_affected",
                    cve=assessment.vulnerability_id,
                    justification=assessment.justification,
                )

        # Validation passed
        logger.debug(
            "VEX assessment validation passed",
            cve=assessment.vulnerability_id,
        )

    def export_cyclonedx(
        self,
        assessment: VEXAssessment,
        document_version: int = 1
    ) -> CycloneDXVEX:
        """
        Export VEX assessment to CycloneDX 1.5 format.

        Converts the VEXAssessment to CycloneDX standard format for
        tool interoperability and SBOM/VEX ecosystem integration.

        Args:
            assessment: VEX assessment to export
            document_version: Document version number (increments on updates)

        Returns:
            CycloneDXVEX: CycloneDX-formatted VEX document

        Example:
            >>> cyclonedx_vex = synthesizer.export_cyclonedx(assessment)
            >>> print(cyclonedx_vex.bomFormat)  # "CycloneDX"
            >>> print(cyclonedx_vex.specVersion)  # "1.5"
        """
        logger.info(
            "Exporting VEX to CycloneDX format",
            cve=assessment.vulnerability_id,
        )

        # Build metadata
        metadata = {
            "timestamp": assessment.assessment_timestamp.isoformat() + "Z",
            "component": {
                "type": "library",
                "purl": assessment.component_purl,
                "name": assessment.evidence.graph_evidence.component_presence.component_name,
                "version": assessment.evidence.graph_evidence.component_presence.component_version,
            },
            "supplier": {
                "name": "Complira",
                "url": ["https://complira.ai"]
            }
        }

        # Build vulnerability assessment
        vulnerability = {
            "id": assessment.vulnerability_id,
            "source": {
                "name": "NVD",
                "url": f"https://nvd.nist.gov/vuln/detail/{assessment.vulnerability_id}"
            },
            "ratings": [],
            "cwes": [],
            "description": assessment.evidence.cve_metadata.description,
            "analysis": {
                "state": assessment.status.value,
                "detail": assessment.impact_summary,
            }
        }

        # Add CVSS rating
        if assessment.evidence.cve_metadata.cvss_v3_score:
            vulnerability["ratings"].append({
                "score": assessment.evidence.cve_metadata.cvss_v3_score,
                "severity": assessment.evidence.cve_metadata.cvss_v3_severity,
                "method": "CVSSv3",
                "vector": assessment.evidence.cve_metadata.cvss_v3_vector,
            })

        # Add CWE IDs
        for cwe in assessment.evidence.graph_evidence.cwe_mappings:
            vulnerability["cwes"].append(int(cwe.cwe_id.split("-")[1]))

        # Add justification if not_affected
        if assessment.justification:
            vulnerability["analysis"]["justification"] = assessment.justification.value

        # Add response if affected
        if assessment.response:
            vulnerability["analysis"]["response"] = [r.value for r in assessment.response]

        # Build CycloneDX document
        cyclonedx = CycloneDXVEX(
            version=document_version,
            metadata=metadata,
            vulnerabilities=[vulnerability],
            evidence_package=assessment.evidence,  # Complira extension
        )

        logger.info(
            "CycloneDX export complete",
            cve=assessment.vulnerability_id,
        )

        return cyclonedx

    def export_csaf(
        self,
        assessment: VEXAssessment,
        publisher_name: str = "Complira",
        publisher_category: str = "vendor"
    ) -> CSAFVEX:
        """
        Export VEX assessment to CSAF 2.0 format.

        Converts the VEXAssessment to CSAF standard format for
        government/enterprise environments preferring CSAF.

        Args:
            assessment: VEX assessment to export
            publisher_name: Publisher name for CSAF document
            publisher_category: Publisher category (vendor/coordinator/user)

        Returns:
            CSAFVEX: CSAF-formatted VEX document

        Example:
            >>> csaf_vex = synthesizer.export_csaf(assessment)
            >>> print(csaf_vex.document["category"])  # "csaf_vex"
        """
        logger.info(
            "Exporting VEX to CSAF format",
            cve=assessment.vulnerability_id,
        )

        # Build CSAF document metadata
        document = {
            "category": "csaf_vex",
            "title": f"VEX for {assessment.vulnerability_id} in {assessment.component_purl}",
            "publisher": {
                "category": publisher_category,
                "name": publisher_name,
            },
            "tracking": {
                "id": f"{assessment.vulnerability_id}-{assessment.evidence.graph_evidence.component_presence.component_name}",
                "status": "final",
                "version": assessment.assessment_version,
                "revision_history": [{
                    "number": assessment.assessment_version,
                    "date": assessment.assessment_timestamp.isoformat() + "Z",
                    "summary": "Initial VEX assessment"
                }],
                "initial_release_date": assessment.assessment_timestamp.isoformat() + "Z",
                "current_release_date": assessment.assessment_timestamp.isoformat() + "Z",
            }
        }

        # Build product tree
        product_tree = {
            "branches": [{
                "category": "product_name",
                "name": assessment.evidence.graph_evidence.component_presence.component_name,
                "product": {
                    "name": f"{assessment.evidence.graph_evidence.component_presence.component_name} {assessment.evidence.graph_evidence.component_presence.component_version}",
                    "product_id": assessment.component_purl,
                    "product_identification_helper": {
                        "purl": assessment.component_purl
                    }
                }
            }]
        }

        # Build vulnerability assessment
        vulnerability = {
            "cve": assessment.vulnerability_id,
            "notes": [{
                "category": "description",
                "text": assessment.evidence.cve_metadata.description
            }, {
                "category": "summary",
                "text": assessment.impact_summary
            }, {
                "category": "details",
                "text": assessment.exploitability_analysis
            }],
        }

        # Add product status
        if assessment.status == VEXStatus.AFFECTED:
            vulnerability["product_status"] = {
                "known_affected": [assessment.component_purl]
            }
        elif assessment.status == VEXStatus.NOT_AFFECTED:
            vulnerability["product_status"] = {
                "known_not_affected": [assessment.component_purl]
            }
        elif assessment.status == VEXStatus.FIXED:
            vulnerability["product_status"] = {
                "fixed": [assessment.component_purl]
            }
        elif assessment.status == VEXStatus.UNDER_INVESTIGATION:
            vulnerability["product_status"] = {
                "under_investigation": [assessment.component_purl]
            }

        # Add remediation if available
        if assessment.mitigation_recommendations:
            vulnerability["remediations"] = [{
                "category": "mitigation",
                "details": "\n".join(assessment.mitigation_recommendations),
                "product_ids": [assessment.component_purl]
            }]

        # Build evidence notes
        notes = [{
            "category": "general",
            "title": "Evidence Citations",
            "text": f"Evidence IDs: {', '.join(assessment.evidence_citations)}"
        }]

        if assessment.regulatory_impact:
            notes.append({
                "category": "legal_disclaimer",
                "title": "Regulatory Impact",
                "text": assessment.regulatory_impact
            })

        # Build CSAF document
        csaf = CSAFVEX(
            document=document,
            product_tree=product_tree,
            vulnerabilities=[vulnerability],
            notes=notes,
        )

        logger.info(
            "CSAF export complete",
            cve=assessment.vulnerability_id,
        )

        return csaf


# Convenience function for standalone usage
async def synthesize_vex_from_evidence(
    evidence: VulnerabilityEvidence,
    component_purl: str,
    anthropic_api_key: str,
    export_format: Optional[str] = None
) -> Dict[str, Any]:
    """
    Convenience function for synthesizing VEX from evidence.

    This is a standalone function that handles client initialization
    and format export in one call.

    Args:
        evidence: Complete vulnerability evidence package
        component_purl: Component Package URL
        anthropic_api_key: Anthropic API key
        export_format: Optional format ('cyclonedx', 'csaf', or None)

    Returns:
        dict: VEX assessment and optional format export

    Example:
        >>> result = await synthesize_vex_from_evidence(
        ...     evidence=evidence,
        ...     component_purl="pkg:maven/...",
        ...     anthropic_api_key="sk-...",
        ...     export_format="cyclonedx"
        ... )
        >>> print(result["assessment"].status)
        >>> print(result["cyclonedx_vex"])
    """
    # Initialize client and synthesizer
    client = Anthropic(api_key=anthropic_api_key)
    synthesizer = VEXSynthesizerV2(client)

    # Generate assessment
    assessment = await synthesizer.synthesize_vex(
        evidence=evidence,
        component_purl=component_purl
    )

    result: Dict[str, Any] = {"assessment": assessment}

    # Export to requested format
    if export_format == "cyclonedx":
        result["cyclonedx_vex"] = synthesizer.export_cyclonedx(assessment)
    elif export_format == "csaf":
        result["csaf_vex"] = synthesizer.export_csaf(assessment)
    elif export_format == "both":
        result["cyclonedx_vex"] = synthesizer.export_cyclonedx(assessment)
        result["csaf_vex"] = synthesizer.export_csaf(assessment)

    return result


def export_cyclonedx_multi(
    synthesizer: "VEXSynthesizerV2",
    assessments: List[VEXAssessment],
    scan_session_id: str,
    document_version: int = 1
) -> Dict[str, Any]:
    """
    Export multiple VEX assessments to a single CycloneDX VEX 1.5 document.

    Aggregates multiple vulnerability assessments into one VEX document,
    suitable for scan session results with multiple findings.

    Args:
        synthesizer: VEXSynthesizerV2 instance
        assessments: List of VEX assessments to export
        scan_session_id: Scan session identifier
        document_version: Document version number

    Returns:
        dict: CycloneDX VEX document (JSON format)
    """
    from datetime import datetime

    if not assessments:
        raise ValueError("At least one assessment required for VEX export")

    logger.info(
        "Exporting multiple VEX assessments to CycloneDX format",
        assessments_count=len(assessments),
    )

    # Build metadata from first assessment
    first_assessment = assessments[0]
    metadata = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "component": {
            "bom-ref": scan_session_id,
            "type": "application",
        },
        "supplier": {
            "name": "Complira",
            "url": ["https://complira.ai"]
        },
        "tools": [{
            "vendor": "Complira",
            "name": "VEX Synthesizer V2",
            "version": "2.0.0"
        }]
    }

    # Build vulnerability array
    vulnerabilities = []
    for assessment in assessments:
        vulnerability = {
            "id": assessment.vulnerability_id,
            "source": {
                "name": "NVD",
                "url": f"https://nvd.nist.gov/vuln/detail/{assessment.vulnerability_id}"
            },
            "ratings": [],
            "cwes": [],
            "description": assessment.evidence.cve_metadata.description,
            "analysis": {
                "state": assessment.status.value,
                "detail": assessment.impact_summary,
            },
            "affects": [{
                "ref": assessment.component_purl,
            }]
        }

        # Add CVSS rating
        if assessment.evidence.cve_metadata.cvss_v3_score:
            vulnerability["ratings"].append({
                "score": assessment.evidence.cve_metadata.cvss_v3_score,
                "severity": assessment.evidence.cve_metadata.cvss_v3_severity,
                "method": "CVSSv3",
                "vector": assessment.evidence.cve_metadata.cvss_v3_vector,
            })

        # Add CWE IDs
        for cwe in assessment.evidence.graph_evidence.cwe_mappings:
            try:
                cwe_num = int(cwe.cwe_id.split("-")[1])
                vulnerability["cwes"].append(cwe_num)
            except (IndexError, ValueError):
                pass

        # Add justification if not_affected
        if assessment.justification:
            vulnerability["analysis"]["justification"] = assessment.justification.value

        # Add response if affected
        if assessment.response:
            vulnerability["analysis"]["response"] = [r.value for r in assessment.response]

        vulnerabilities.append(vulnerability)

    # Build CycloneDX document
    cyclonedx_doc = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": document_version,
        "metadata": metadata,
        "vulnerabilities": vulnerabilities
    }

    logger.info(
        "CycloneDX multi-assessment export complete",
        assessments_count=len(assessments),
    )

    return cyclonedx_doc


__all__ = [
    "VEXSynthesizerV2",
    "synthesize_vex_from_evidence",
    "export_cyclonedx_multi",
]
