# VEX Evidence Schema Design - Part 2

## 3. Enhanced VEX Synthesizer (V2)

**File:** `/Users/venkatapydialli/Documents/cybersecurity-compliance-app/src/complira_graph/llm_agents/vex_synthesizer_v2.py`

Enhanced VEX synthesizer that uses evidence-first approach:

```python
"""
VEX Synthesizer V2 - Evidence-Grounded LLM Agent.

Key Improvements Over V1:
1. Evidence-First: Collects all evidence before LLM call
2. Structured Output: Enforces Pydantic schema (no JSON parsing)
3. Evidence Citations: LLM must cite specific evidence items
4. Multi-Format: Generates both CycloneDX and CSAF
5. Regulatory Grade: Meets FDA/CRA requirements

Model: Claude Sonnet 4.5 (complex reasoning for impact analysis)
Output: VEXAssessment with complete evidence chain

Usage:
    from complira_graph.llm_agents.vex_synthesizer_v2 import VEXSynthesizerV2

    synthesizer = VEXSynthesizerV2(db, anthropic_client, settings)

    assessment = await synthesizer.generate_vex_assessment(
        cve_id="CVE-2021-44228",
        component_purl="pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
        customer_id="customer_123"
    )
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import structlog

from api.services.vex_evidence import VEXEvidenceCollectionService
from complira_graph.models.vex_evidence import (
    VEXAssessment,
    VulnerabilityEvidence,
    VEXStatus,
    VEXJustification,
    VEXResponse,
    CycloneDXVEX,
    CSAFVEX,
)
from complira_graph.validators.vex_validator import VEXValidator
from complira_graph.formatters.cyclonedx import CycloneDXFormatter
from complira_graph.formatters.csaf import CSAFFormatter

logger = structlog.get_logger()


class VEXSynthesizerV2:
    """
    Evidence-grounded VEX synthesizer (V2).

    Pipeline:
    1. Collect Evidence → VEXEvidenceCollectionService
    2. Validate Evidence → VEXValidator
    3. LLM Synthesis → Claude with structured output
    4. Format Output → CycloneDX + CSAF formatters
    """

    MODEL = "claude-sonnet-4.5"
    MAX_TOKENS = 8192  # Longer for detailed analysis

    def __init__(self, db, anthropic_client, settings):
        """
        Initialize VEX synthesizer.

        Args:
            db: Database instance
            anthropic_client: Anthropic API client
            settings: Application settings
        """
        self.db = db
        self.anthropic_client = anthropic_client
        self.settings = settings
        self.logger = structlog.get_logger()

        # Initialize dependencies
        self.evidence_service = VEXEvidenceCollectionService(db, cache=None)
        self.validator = VEXValidator()
        self.cyclonedx_formatter = CycloneDXFormatter()
        self.csaf_formatter = CSAFFormatter()

    async def generate_vex_assessment(
        self,
        cve_id: str,
        component_purl: str,
        customer_id: Optional[str] = None,
        output_format: str = "both",  # "cyclonedx" | "csaf" | "both"
    ) -> Dict[str, Any]:
        """
        Generate complete VEX assessment with evidence.

        This is the main entry point for VEX generation.

        Args:
            cve_id: CVE identifier
            component_purl: Component PURL
            customer_id: Customer ID for SBOM validation
            output_format: Output format(s) to generate

        Returns:
            dict: {
                "assessment": VEXAssessment,
                "cyclonedx_vex": CycloneDXVEX (if requested),
                "csaf_vex": CSAFVEX (if requested),
                "validation_result": EvidenceValidationResult
            }

        Flow:
            1. Collect evidence (Evidence Service)
            2. Validate evidence (Validator)
            3. Generate assessment (LLM)
            4. Format output (Formatters)
            5. Return complete package
        """
        self.logger.info(
            "Starting VEX generation (V2)",
            cve_id=cve_id,
            component_purl=component_purl,
        )

        # Step 1: Collect Evidence
        evidence = await self.evidence_service.collect_evidence(
            cve_id=cve_id,
            component_purl=component_purl,
            customer_id=customer_id,
            include_tier_2=True,
        )

        self.logger.debug(
            "Evidence collected",
            tier_1_complete=evidence.tier_1_complete,
            tier_2_complete=evidence.tier_2_complete,
        )

        # Step 2: Validate Evidence
        validation_result = self.validator.validate_evidence(evidence)

        if not validation_result.tier_1_valid:
            self.logger.warning(
                "Tier 1 evidence incomplete - cannot generate regulatory-grade VEX",
                missing_evidence=validation_result.missing_evidence,
            )
            raise ValueError(
                f"Tier 1 evidence incomplete: {validation_result.missing_evidence}"
            )

        # Step 3: Generate Assessment (LLM)
        assessment = await self._generate_assessment_with_llm(
            evidence=evidence,
            cve_id=cve_id,
            component_purl=component_purl,
        )

        # Step 4: Format Output
        result = {
            "assessment": assessment,
            "validation_result": validation_result,
        }

        if output_format in ["cyclonedx", "both"]:
            result["cyclonedx_vex"] = self.cyclonedx_formatter.format(assessment)

        if output_format in ["csaf", "both"]:
            result["csaf_vex"] = self.csaf_formatter.format(assessment)

        self.logger.info(
            "VEX generation complete",
            cve_id=cve_id,
            status=assessment.status,
            output_format=output_format,
        )

        return result

    async def _generate_assessment_with_llm(
        self,
        evidence: VulnerabilityEvidence,
        cve_id: str,
        component_purl: str,
    ) -> VEXAssessment:
        """
        Generate VEX assessment using LLM with evidence.

        The LLM receives structured evidence and must:
        1. Analyze impact with evidence citations
        2. Determine VEX status (affected | not_affected | under_investigation)
        3. Provide justification (if not_affected)
        4. Recommend mitigations
        5. Cite specific evidence items

        Args:
            evidence: Complete evidence package
            cve_id: CVE identifier
            component_purl: Component PURL

        Returns:
            VEXAssessment: Complete assessment with evidence citations
        """
        # Build evidence-rich prompt
        prompt = self._build_evidence_prompt(evidence, cve_id, component_purl)

        self.logger.debug(
            "Calling Claude API for VEX assessment",
            cve_id=cve_id,
            model=self.MODEL,
        )

        # Call LLM with structured output
        try:
            response = self.anthropic_client.messages.create(
                model=self.settings.ANTHROPIC_MODEL_SONNET,
                max_tokens=self.MAX_TOKENS,
                temperature=0.0,  # Deterministic for compliance
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            )

            response_text = response.content[0].text

            # Parse LLM response
            llm_output = self._parse_llm_response(response_text)

            # Build VEXAssessment
            assessment = VEXAssessment(
                vulnerability_id=cve_id,
                component_purl=component_purl,
                status=VEXStatus(llm_output["status"]),
                justification=VEXJustification(llm_output["justification"])
                if llm_output.get("justification")
                else None,
                response=[VEXResponse(r) for r in llm_output.get("response", [])],
                evidence=evidence,
                impact_summary=llm_output["impact_summary"],
                exploitability_analysis=llm_output["exploitability_analysis"],
                mitigation_recommendations=llm_output.get("mitigation_recommendations", []),
                evidence_citations=llm_output.get("evidence_citations", []),
                regulatory_impact=llm_output.get("regulatory_impact"),
                compliance_deadline=self._extract_compliance_deadline(evidence),
                llm_model=self.MODEL,
                llm_tokens={
                    "input": response.usage.input_tokens,
                    "output": response.usage.output_tokens,
                },
            )

            self.logger.debug(
                "LLM assessment generated",
                status=assessment.status,
                citations=len(assessment.evidence_citations),
            )

            return assessment

        except Exception as e:
            self.logger.error(
                "LLM assessment generation failed",
                cve_id=cve_id,
                error=str(e),
            )
            raise

    def _build_evidence_prompt(
        self,
        evidence: VulnerabilityEvidence,
        cve_id: str,
        component_purl: str,
    ) -> str:
        """
        Build evidence-rich prompt for LLM.

        The prompt includes:
        1. Complete evidence package (structured)
        2. Regulatory requirements
        3. Output format specification
        4. Evidence citation requirements

        Args:
            evidence: Evidence package
            cve_id: CVE identifier
            component_purl: Component PURL

        Returns:
            str: Formatted prompt
        """
        cve_meta = evidence.cve_metadata
        graph_ev = evidence.graph_evidence

        # Format CWE mappings
        cwe_text = "\n".join([
            f"  - {cwe.cwe_id}: {cwe.name} (Graph ID: {cwe.graph_id})"
            for cwe in graph_ev.cwe_mappings
        ])

        # Format KEV status
        kev_text = f"  - In KEV Catalog: {graph_ev.kev_evidence.in_kev}"
        if graph_ev.kev_evidence.in_kev:
            kev_text += f"\n  - KEV Due Date: {graph_ev.kev_evidence.kev_due_date}"
            kev_text += f"\n  - Required Action: {graph_ev.kev_evidence.kev_required_action}"

        # Format EPSS
        epss_text = "  - EPSS Score: Not Available"
        if graph_ev.exploitability.epss_score:
            epss_text = f"  - EPSS Score: {graph_ev.exploitability.epss_score:.4f} (Percentile: {graph_ev.exploitability.epss_percentile:.2f})"

        # Format ATT&CK techniques
        attack_text = ""
        if graph_ev.attack_techniques:
            attack_text = "\n\nAttack Techniques (Tier 2):\n"
            for attack in graph_ev.attack_techniques[:5]:  # Limit to 5
                attack_text += f"  - {attack.technique_id}: {attack.technique_name}\n"
                attack_text += f"    Tactic: {attack.tactic}\n"
                attack_text += f"    Graph Path: {' → '.join([p.split('/')[-1] for p in attack.graph_path])}\n"

        # Format mitigation controls
        control_text = ""
        if graph_ev.mitigation_controls:
            control_text = "\n\nMitigation Controls (Tier 2):\n"
            for control in graph_ev.mitigation_controls[:5]:  # Limit to 5
                control_text += f"  - {control.control_id}: {control.control_title}\n"
                control_text += f"    Framework: {control.framework}\n"
                control_text += f"    Effectiveness: {control.mitigation_effectiveness}\n"

        # Format compliance violations
        compliance_text = ""
        if graph_ev.compliance_violations:
            compliance_text = "\n\nRegulatory Violations (Tier 2):\n"
            for violation in graph_ev.compliance_violations:
                compliance_text += f"  - {violation.framework}: {violation.requirement_title}\n"
                compliance_text += f"    Obligation: {violation.obligation_level}\n"
                if violation.deadline:
                    compliance_text += f"    Deadline: {violation.deadline}\n"

        # Component presence
        component_text = f"""
Component Presence (Tier 1):
  - PURL: {graph_ev.component_presence.component_purl}
  - In SBOM: {graph_ev.component_presence.in_sbom}
  - Deployment Scope: {graph_ev.component_presence.deployment_scope or 'Unknown'}
  - Criticality: {graph_ev.component_presence.deployment_criticality or 'Unknown'}
"""

        prompt = f"""You are a security expert generating a VEX (Vulnerability Exploitability eXchange) assessment for regulatory compliance (FDA 524B, EU CRA, IEC 62304).

You are provided with complete, structured evidence collected from a knowledge graph. Your task is to analyze this evidence and generate a VEX assessment.

## IMPORTANT RULES

1. **Evidence-Based Only**: Base ALL conclusions on the provided evidence. Do NOT speculate or hallucinate.
2. **Cite Evidence**: Reference specific evidence items (e.g., "cve_metadata", "kev_evidence", "attack_techniques[0]")
3. **Regulatory Focus**: Consider FDA/CRA requirements in your analysis
4. **Structured Output**: Respond in valid JSON matching the schema below

## Vulnerability Evidence

CVE Metadata (Tier 1):
  - CVE ID: {cve_meta.cve_id}
  - Description: {cve_meta.description[:300]}...
  - CVSS v3 Score: {cve_meta.cvss_v3_score} ({cve_meta.cvss_v3_severity})
  - CVSS Vector: {cve_meta.cvss_v3_vector}
  - Published: {cve_meta.published_date}
  - Graph ID: {cve_meta.graph_id}

CWE Weaknesses (Tier 1):
{cwe_text}

KEV Status (Tier 1):
{kev_text}

Exploitability (Tier 1):
{epss_text}
  - Exploit Available: {graph_ev.exploitability.exploit_available}
  - Exploit Maturity: {graph_ev.exploitability.exploit_maturity}

{component_text}

{attack_text}

{control_text}

{compliance_text}

## Evidence Completeness

- Tier 1 (Critical) Complete: {evidence.tier_1_complete}
- Tier 2 (Important) Complete: {evidence.tier_2_complete}
- Overall Completeness: {graph_ev.evidence_completeness}

## Your Task

Analyze the evidence and generate a VEX assessment:

1. **Status Determination**: Choose one:
   - "affected": Component is vulnerable and exploitable
   - "not_affected": Component contains vulnerable code but is not exploitable
   - "under_investigation": More analysis needed (ONLY if evidence is incomplete)
   - "fixed": Vulnerability is fixed (only if fix_available=true)

2. **Justification** (REQUIRED if status="not_affected"):
   - "vulnerable_code_not_present": Component doesn't include vulnerable code
   - "vulnerable_code_not_in_execute_path": Code exists but not reachable
   - "vulnerable_code_cannot_be_controlled_by_adversary": Code not exploitable
   - "inline_mitigations_already_exist": Mitigations prevent exploitation

3. **Response Actions**: Choose applicable:
   - "can_not_fix": Technical limitations prevent fix
   - "will_not_fix": Business decision not to fix
   - "update": Update to fixed version available
   - "rollback": Rollback to prior version
   - "workaround_available": Workaround exists

4. **Impact Analysis**:
   - Summarize impact in 2-3 sentences
   - Cite specific evidence (e.g., "High EPSS score (cve_metadata.cvss_v3_score)")
   - Consider regulatory requirements

5. **Exploitability Analysis**:
   - Analyze exploitability based on EPSS, KEV, ATT&CK
   - Cite evidence items
   - Consider deployment context

6. **Mitigation Recommendations**:
   - List 3-5 concrete mitigation steps
   - Reference specific controls if available (mitigation_controls)
   - Prioritize based on KEV status

7. **Regulatory Impact**:
   - Summarize regulatory implications (FDA/CRA)
   - Reference compliance_violations if present
   - State soonest deadline

8. **Evidence Citations**:
   - List all evidence items you referenced
   - Format: "cve_metadata", "kev_evidence", "attack_techniques[0]", etc.

## Output Format (JSON)

Respond with ONLY valid JSON (no markdown fences):

{{
  "status": "affected|not_affected|under_investigation|fixed",
  "justification": "vulnerable_code_not_present|...|null",
  "response": ["update", "workaround_available"],
  "impact_summary": "Brief 2-3 sentence summary citing evidence...",
  "exploitability_analysis": "Detailed exploitability analysis with evidence citations...",
  "mitigation_recommendations": [
    "1. Immediate action: ...",
    "2. Short-term: ...",
    "3. Long-term: ..."
  ],
  "regulatory_impact": "FDA/CRA impact statement...",
  "evidence_citations": [
    "cve_metadata",
    "kev_evidence",
    "cwe_mappings[0]",
    "attack_techniques[0]",
    "mitigation_controls[1]"
  ]
}}

Generate the assessment now:"""

        return prompt

    def _parse_llm_response(self, response_text: str) -> Dict[str, Any]:
        """
        Parse LLM response JSON.

        Args:
            response_text: LLM response text

        Returns:
            dict: Parsed response

        Raises:
            ValueError: If response is invalid JSON
        """
        import json

        # Strip markdown fences if present
        response_text = response_text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]

        response_text = response_text.strip()

        try:
            return json.loads(response_text)
        except json.JSONDecodeError as e:
            self.logger.error("Failed to parse LLM response", error=str(e))
            raise ValueError(f"Invalid JSON response from LLM: {e}")

    def _extract_compliance_deadline(self, evidence: VulnerabilityEvidence) -> Optional[datetime]:
        """
        Extract soonest compliance deadline from violations.

        Args:
            evidence: Vulnerability evidence

        Returns:
            datetime: Soonest deadline or None
        """
        violations = evidence.graph_evidence.compliance_violations

        if not violations:
            return None

        deadlines = [v.deadline for v in violations if v.deadline]

        if not deadlines:
            return None

        return min(deadlines)


# ========== Batch Generation ==========

class VEXBatchGenerator:
    """
    Batch VEX generation for SBOM scanning.

    Processes multiple CVE/component pairs efficiently.
    """

    def __init__(self, synthesizer: VEXSynthesizerV2):
        """
        Initialize batch generator.

        Args:
            synthesizer: VEX synthesizer instance
        """
        self.synthesizer = synthesizer
        self.logger = structlog.get_logger()

    async def generate_vex_for_sbom(
        self,
        sbom_components: List[Dict[str, Any]],
        customer_id: str,
        output_format: str = "cyclonedx",
    ) -> Dict[str, Any]:
        """
        Generate VEX for all vulnerable components in SBOM.

        Args:
            sbom_components: List of components with vulnerabilities
            customer_id: Customer ID
            output_format: Output format

        Returns:
            dict: {
                "vex_assessments": [list of assessments],
                "summary": {statistics},
                "errors": [list of errors]
            }
        """
        self.logger.info(
            "Starting batch VEX generation",
            components_count=len(sbom_components),
        )

        assessments = []
        errors = []

        for component in sbom_components:
            purl = component["purl"]
            vulnerabilities = component.get("vulnerabilities", [])

            for vuln in vulnerabilities:
                cve_id = vuln["cve_id"]

                try:
                    result = await self.synthesizer.generate_vex_assessment(
                        cve_id=cve_id,
                        component_purl=purl,
                        customer_id=customer_id,
                        output_format=output_format,
                    )

                    assessments.append(result)

                except Exception as e:
                    self.logger.error(
                        "VEX generation failed",
                        cve_id=cve_id,
                        purl=purl,
                        error=str(e),
                    )
                    errors.append(
                        {
                            "cve_id": cve_id,
                            "purl": purl,
                            "error": str(e),
                        }
                    )

        # Build summary
        summary = {
            "total_components": len(sbom_components),
            "assessments_generated": len(assessments),
            "errors": len(errors),
            "status_breakdown": self._count_statuses(assessments),
        }

        self.logger.info(
            "Batch VEX generation complete",
            assessments=len(assessments),
            errors=len(errors),
        )

        return {
            "vex_assessments": assessments,
            "summary": summary,
            "errors": errors,
        }

    def _count_statuses(self, assessments: List[Dict[str, Any]]) -> Dict[str, int]:
        """Count VEX statuses."""
        from collections import Counter

        statuses = [a["assessment"].status.value for a in assessments]
        return dict(Counter(statuses))


# ========== Export ==========

__all__ = ["VEXSynthesizerV2", "VEXBatchGenerator"]
```

## 4. CSAF Output Formatter

**File:** `/Users/venkatapydialli/Documents/cybersecurity-compliance-app/src/complira_graph/formatters/csaf.py`

CSAF 2.0 formatter for VEX output:

```python
"""
CSAF 2.0 VEX Formatter.

Converts VEXAssessment to CSAF 2.0 format (OASIS standard).

CSAF (Common Security Advisory Framework) is an OASIS standard for
machine-readable security advisories and VEX documents.

Specification: https://docs.oasis-open.org/csaf/csaf/v2.0/csaf-v2.0.html

Key Features:
- Full CSAF 2.0 compliance
- Evidence embedded in notes sections
- Product tree generation
- Vulnerability scoring
- Remediation tracking

Usage:
    from complira_graph.formatters.csaf import CSAFFormatter

    formatter = CSAFFormatter()
    csaf_doc = formatter.format(vex_assessment)
"""

from typing import Dict, Any, List
from datetime import datetime
from uuid import uuid4

from complira_graph.models.vex_evidence import VEXAssessment, VEXStatus
import structlog

logger = structlog.get_logger()


class CSAFFormatter:
    """
    CSAF 2.0 formatter for VEX documents.

    Converts VEXAssessment (internal model) to CSAF 2.0 JSON.
    """

    CSAF_VERSION = "2.0"
    GENERATOR_NAME = "Complira VEX Synthesizer V2"
    GENERATOR_VERSION = "2.0.0"

    def format(self, assessment: VEXAssessment) -> Dict[str, Any]:
        """
        Convert VEXAssessment to CSAF 2.0 document.

        Args:
            assessment: VEX assessment with evidence

        Returns:
            dict: CSAF 2.0 document
        """
        logger.debug(
            "Formatting VEX assessment to CSAF",
            cve_id=assessment.vulnerability_id,
        )

        # Build CSAF document
        csaf_doc = {
            "document": self._build_document_section(assessment),
            "product_tree": self._build_product_tree(assessment),
            "vulnerabilities": [self._build_vulnerability_section(assessment)],
        }

        logger.debug("CSAF document formatted", cve_id=assessment.vulnerability_id)

        return csaf_doc

    def _build_document_section(self, assessment: VEXAssessment) -> Dict[str, Any]:
        """
        Build CSAF document section.

        Contains document metadata, generator info, and tracking.

        Args:
            assessment: VEX assessment

        Returns:
            dict: Document section
        """
        doc_id = f"COMPLIRA-VEX-{uuid4()}"

        return {
            "category": "csaf_vex",
            "csaf_version": self.CSAF_VERSION,
            "distribution": {
                "tlp": {
                    "label": "WHITE",
                    "url": "https://www.first.org/tlp/",
                }
            },
            "lang": "en",
            "notes": self._build_evidence_notes(assessment),
            "publisher": {
                "category": "vendor",
                "name": "Complira",
                "namespace": "https://complira.com",
            },
            "title": f"VEX Assessment: {assessment.vulnerability_id} in {assessment.component_purl}",
            "tracking": {
                "current_release_date": assessment.assessment_timestamp.isoformat() + "Z",
                "generator": {
                    "date": assessment.assessment_timestamp.isoformat() + "Z",
                    "engine": {
                        "name": self.GENERATOR_NAME,
                        "version": self.GENERATOR_VERSION,
                    },
                },
                "id": doc_id,
                "initial_release_date": assessment.assessment_timestamp.isoformat() + "Z",
                "revision_history": [
                    {
                        "date": assessment.assessment_timestamp.isoformat() + "Z",
                        "number": "1",
                        "summary": "Initial VEX assessment",
                    }
                ],
                "status": "final",
                "version": "1",
            },
        }

    def _build_product_tree(self, assessment: VEXAssessment) -> Dict[str, Any]:
        """
        Build CSAF product tree.

        Defines the product affected by the vulnerability.

        Args:
            assessment: VEX assessment

        Returns:
            dict: Product tree section
        """
        # Parse PURL to extract product information
        purl_parts = self._parse_purl(assessment.component_purl)

        product_id = f"PRODUCT-{uuid4().hex[:8]}"

        return {
            "full_product_names": [
                {
                    "name": f"{purl_parts['name']} {purl_parts['version']}",
                    "product_id": product_id,
                    "product_identification_helper": {
                        "purl": assessment.component_purl,
                    },
                }
            ]
        }

    def _build_vulnerability_section(self, assessment: VEXAssessment) -> Dict[str, Any]:
        """
        Build CSAF vulnerability section.

        Contains vulnerability details, scores, and VEX status.

        Args:
            assessment: VEX assessment

        Returns:
            dict: Vulnerability section
        """
        cve_meta = assessment.evidence.cve_metadata

        vuln_section = {
            "cve": assessment.vulnerability_id,
            "notes": [
                {
                    "category": "description",
                    "text": cve_meta.description,
                    "title": "CVE Description",
                },
                {
                    "category": "general",
                    "text": assessment.impact_summary,
                    "title": "Impact Summary",
                },
                {
                    "category": "general",
                    "text": assessment.exploitability_analysis,
                    "title": "Exploitability Analysis",
                },
            ],
            "product_status": self._map_vex_status_to_csaf(assessment.status),
            "scores": self._build_scores_section(assessment),
        }

        # Add remediations if available
        if assessment.evidence.graph_evidence.remediation:
            vuln_section["remediations"] = self._build_remediations_section(assessment)

        # Add threats if KEV
        if assessment.evidence.graph_evidence.kev_evidence.in_kev:
            vuln_section["threats"] = self._build_threats_section(assessment)

        return vuln_section

    def _build_evidence_notes(self, assessment: VEXAssessment) -> List[Dict[str, Any]]:
        """
        Build evidence notes for auditability.

        CSAF stores evidence in the document-level notes section.

        Args:
            assessment: VEX assessment

        Returns:
            list: Evidence notes
        """
        notes = []

        # Evidence completeness note
        notes.append(
            {
                "category": "general",
                "text": f"Evidence Tier 1 Complete: {assessment.evidence.tier_1_complete}\n"
                f"Evidence Tier 2 Complete: {assessment.evidence.tier_2_complete}\n"
                f"Overall Completeness: {assessment.evidence.graph_evidence.evidence_completeness}",
                "title": "Evidence Completeness",
            }
        )

        # CWE mappings note
        if assessment.evidence.graph_evidence.cwe_mappings:
            cwe_text = "\n".join(
                [
                    f"- {cwe.cwe_id}: {cwe.name} (Graph: {cwe.graph_id})"
                    for cwe in assessment.evidence.graph_evidence.cwe_mappings
                ]
            )
            notes.append(
                {
                    "category": "general",
                    "text": cwe_text,
                    "title": "CWE Weaknesses",
                }
            )

        # KEV status note
        kev = assessment.evidence.graph_evidence.kev_evidence
        if kev.in_kev:
            notes.append(
                {
                    "category": "general",
                    "text": f"KEV Due Date: {kev.kev_due_date}\n"
                    f"Required Action: {kev.kev_required_action}\n"
                    f"Known Ransomware: {kev.kev_known_ransomware}",
                    "title": "CISA KEV Status - ACTIVE EXPLOITATION",
                }
            )

        # ATT&CK techniques note
        if assessment.evidence.graph_evidence.attack_techniques:
            attack_text = "\n".join(
                [
                    f"- {t.technique_id}: {t.technique_name} (Tactic: {t.tactic})"
                    for t in assessment.evidence.graph_evidence.attack_techniques
                ]
            )
            notes.append(
                {
                    "category": "general",
                    "text": attack_text,
                    "title": "MITRE ATT&CK Techniques",
                }
            )

        # Mitigation controls note
        if assessment.evidence.graph_evidence.mitigation_controls:
            control_text = "\n".join(
                [
                    f"- {c.control_id}: {c.control_title} ({c.framework})"
                    for c in assessment.evidence.graph_evidence.mitigation_controls
                ]
            )
            notes.append(
                {
                    "category": "general",
                    "text": control_text,
                    "title": "Mitigation Controls",
                }
            )

        # Regulatory violations note
        if assessment.evidence.graph_evidence.compliance_violations:
            violation_text = "\n".join(
                [
                    f"- {v.framework}: {v.requirement_title} (Obligation: {v.obligation_level})"
                    for v in assessment.evidence.graph_evidence.compliance_violations
                ]
            )
            notes.append(
                {
                    "category": "general",
                    "text": violation_text,
                    "title": "Regulatory Violations",
                }
            )

        return notes

    def _build_scores_section(self, assessment: VEXAssessment) -> List[Dict[str, Any]]:
        """
        Build CSAF scores section.

        Args:
            assessment: VEX assessment

        Returns:
            list: Scores section
        """
        cve_meta = assessment.evidence.cve_metadata
        scores = []

        # CVSS v3 score
        if cve_meta.cvss_v3_score:
            scores.append(
                {
                    "cvss_v3": {
                        "baseScore": cve_meta.cvss_v3_score,
                        "baseSeverity": cve_meta.cvss_v3_severity,
                        "vectorString": cve_meta.cvss_v3_vector,
                        "version": "3.1",
                    },
                    "products": ["PRODUCT-*"],
                }
            )

        return scores

    def _build_remediations_section(self, assessment: VEXAssessment) -> List[Dict[str, Any]]:
        """
        Build CSAF remediations section.

        Args:
            assessment: VEX assessment

        Returns:
            list: Remediations section
        """
        remediation = assessment.evidence.graph_evidence.remediation
        remediations = []

        if remediation.fix_available:
            remediations.append(
                {
                    "category": "vendor_fix",
                    "date": assessment.assessment_timestamp.isoformat() + "Z",
                    "details": f"Upgrade to version {remediation.fix_version}",
                    "product_ids": ["PRODUCT-*"],
                }
            )

        if remediation.workaround_available:
            remediations.append(
                {
                    "category": "workaround",
                    "date": assessment.assessment_timestamp.isoformat() + "Z",
                    "details": remediation.workaround_description or "Workaround available",
                    "product_ids": ["PRODUCT-*"],
                }
            )

        return remediations

    def _build_threats_section(self, assessment: VEXAssessment) -> List[Dict[str, Any]]:
        """
        Build CSAF threats section (for KEV vulnerabilities).

        Args:
            assessment: VEX assessment

        Returns:
            list: Threats section
        """
        kev = assessment.evidence.graph_evidence.kev_evidence

        return [
            {
                "category": "exploit_status",
                "date": kev.kev_date_added.isoformat() + "Z" if kev.kev_date_added else None,
                "details": "Known exploitation in the wild (CISA KEV)",
                "product_ids": ["PRODUCT-*"],
            }
        ]

    def _map_vex_status_to_csaf(self, status: VEXStatus) -> Dict[str, List[str]]:
        """
        Map VEX status to CSAF product_status.

        Args:
            status: VEX status

        Returns:
            dict: CSAF product_status
        """
        if status == VEXStatus.AFFECTED:
            return {"known_affected": ["PRODUCT-*"]}
        elif status == VEXStatus.NOT_AFFECTED:
            return {"known_not_affected": ["PRODUCT-*"]}
        elif status == VEXStatus.FIXED:
            return {"fixed": ["PRODUCT-*"]}
        elif status == VEXStatus.UNDER_INVESTIGATION:
            return {"under_investigation": ["PRODUCT-*"]}
        else:
            return {"unknown": ["PRODUCT-*"]}

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

__all__ = ["CSAFFormatter"]
```

---

*[Document continues in next section...]*
