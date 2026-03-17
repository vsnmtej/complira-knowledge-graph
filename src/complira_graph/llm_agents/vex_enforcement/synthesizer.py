"""
Grounded VEX Synthesizer Module.

Provides evidence-grounded VEX synthesis with pre-LLM validation and
post-LLM hallucination detection. Uses Anthropic function calling to
prevent LLM from generating content outside of structured tool calls.

Key Features:
- Pre-LLM evidence sufficiency validation
- Function calling enforcement (prevents prose escape hatch)
- Post-generation hallucination detection
- Evidence grounding (only real node IDs injected into prompt)

Compliance:
- FDA 524B: Evidence-backed justifications only
- EU CRA: Full evidence traceability

Author: Complira Development Team
Version: 1.0
Ticket: vex-justification-enforcement
"""

from typing import List, Dict, Optional, Any, Literal
from datetime import datetime
import json
import structlog

from anthropic import Anthropic
import instructor
from pydantic import BaseModel, Field

from .grounding import (
    VEXEvidenceBundle,
    EvidenceNode,
    JustificationCode,
    REQUIRED_EVIDENCE_FOR_JUSTIFICATION,
)
from .validator import (
    VEXJustificationValidator,
    ValidationFailure,
    VEXStatement as ValidatorVEXStatement,
    EvidenceReference,
)

logger = structlog.get_logger()


# ========== VEX Document Models ==========


class VEXStatement(BaseModel):
    """
    VEX statement for one CVE-component pair.

    Extends the validator's minimal VEXStatement with additional fields
    needed for complete VEX generation.
    """
    cve_id: str = Field(
        description="CVE identifier (e.g., CVE-2021-44228)"
    )
    component_purl: str = Field(
        description="Component Package URL"
    )
    status: Literal["not_affected", "affected", "fixed", "under_investigation"] = Field(
        description="Vulnerability status"
    )
    justification: Optional[JustificationCode] = Field(
        None,
        description="Justification code (required for not_affected status)"
    )
    evidence_refs: List[EvidenceReference] = Field(
        default_factory=list,
        description="Evidence references supporting this assessment (min 2 for not_affected)"
    )
    detail: str = Field(
        description="Detailed justification narrative (must mention at least one node_id inline)",
        min_length=50
    )
    impact_summary: str = Field(
        description="Summary of vulnerability impact on component",
        min_length=20
    )
    regulatory_context: List[str] = Field(
        default_factory=list,
        description="Applicable regulatory contexts (e.g., FDA_524B, EU_CRA)"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="Assessment timestamp"
    )


class VEXDocument(BaseModel):
    """
    Complete VEX document with multiple statements.

    Represents a VEX document containing assessments for one or more
    CVE-component pairs from a scan session.
    """
    bom_format: Literal["CycloneDX"] = Field(
        default="CycloneDX",
        description="BOM format identifier"
    )
    spec_version: Literal["1.5"] = Field(
        default="1.5",
        description="VEX specification version"
    )
    scan_session_id: str = Field(
        description="Scan session identifier"
    )
    statements: List[VEXStatement] = Field(
        default_factory=list,
        description="VEX statements in this document"
    )
    evidence_coverage: Dict[str, int] = Field(
        default_factory=dict,
        description="Evidence type coverage statistics"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="Document generation timestamp"
    )


# ========== Grounded VEX Synthesizer ==========


class GroundedVEXSynthesizer:
    """
    VEX synthesizer with evidence grounding and function calling enforcement.

    Generates VEX assessments with pre-LLM validation to ensure evidence
    sufficiency and post-LLM validation to detect hallucination.

    Key Differences from V2:
    - Pre-LLM evidence sufficiency checks
    - Function calling enforcement (no prose escape hatch)
    - Post-generation hallucination detection
    - Evidence grounding (only real node IDs in prompt)

    Usage:
        >>> from anthropic import Anthropic
        >>> client = Anthropic(api_key="...")
        >>> synthesizer = GroundedVEXSynthesizer(client)
        >>>
        >>> doc = await synthesizer.generate(
        ...     scan_session_id="scan_123",
        ...     customer_id="customer_456",
        ...     regulatory_context=["FDA_524B"]
        ... )
        >>>
        >>> # Check validation failures
        >>> if synthesizer.last_validation_failures:
        ...     for failure in synthesizer.last_validation_failures:
        ...         print(f"{failure.severity}: {failure.reason}")
    """

    # Model configuration (aligned with V2)
    MODEL = "claude-sonnet-4-20250514"  # Claude Sonnet 4.5
    MAX_TOKENS = 4096
    TEMPERATURE = 0.3  # Low for consistency

    def __init__(self, anthropic_client: Anthropic):
        """
        Initialize grounded VEX synthesizer.

        Args:
            anthropic_client: Configured Anthropic API client
        """
        self.client = anthropic_client
        # Wrap client with instructor for Pydantic schema enforcement
        self.instructor_client = instructor.from_anthropic(self.client)

        # Track last validation failures for observability
        self.last_validation_failures: List[ValidationFailure] = []

        logger.info(
            "Initialized Grounded VEX Synthesizer",
            model=self.MODEL,
            max_tokens=self.MAX_TOKENS,
            temperature=self.TEMPERATURE,
        )

    async def generate(
        self,
        bundles: List[VEXEvidenceBundle],
        scan_session_id: str,
        regulatory_context: Optional[List[str]] = None
    ) -> VEXDocument:
        """
        Generate VEX document with evidence grounding.

        Flow:
        1. Pre-LLM validation: Check evidence sufficiency for each CVE
        2. Build grounded prompt: Inject only real node IDs from bundles
        3. Call Claude: Use instructor for Pydantic schema enforcement
        4. Post-LLM validation: Detect hallucination, evidence gaps, regulatory issues
        5. Filter blocking failures: Remove statements that cannot be submitted
        6. Return VEXDocument with validation metadata

        Args:
            bundles: Evidence bundles for CVEs in this scan session
            scan_session_id: Scan session identifier
            regulatory_context: Optional regulatory contexts (e.g., ["FDA_524B", "EU_CRA"])

        Returns:
            VEXDocument with validated statements

        Raises:
            ValueError: If no valid statements remain after validation

        Example:
            >>> bundles = [bundle1, bundle2, bundle3]
            >>> doc = await synthesizer.generate(
            ...     bundles=bundles,
            ...     scan_session_id="scan_123",
            ...     regulatory_context=["FDA_524B"]
            ... )
            >>> print(f"Generated {len(doc.statements)} VEX statements")
        """
        regulatory_context = regulatory_context or []

        logger.info(
            "Starting grounded VEX synthesis",
            scan_session_id=scan_session_id,
            cve_count=len(bundles),
            regulatory_context=regulatory_context,
        )

        # Step 1: Pre-LLM evidence sufficiency validation
        valid_bundles = self._filter_sufficient_evidence(bundles)

        if not valid_bundles:
            logger.warning(
                "No bundles with sufficient evidence",
                scan_session_id=scan_session_id,
            )
            # Return document with under_investigation statements
            return self._create_under_investigation_doc(bundles, scan_session_id)

        # Step 2: Build grounded prompt
        prompt = self._build_grounded_prompt(valid_bundles, regulatory_context)

        # Step 3: Call Claude with Pydantic enforcement
        try:
            logger.debug(
                "Calling Claude API with structured output",
                model=self.MODEL,
                bundle_count=len(valid_bundles),
            )

            # Use instructor for Pydantic schema enforcement
            doc = self.instructor_client.messages.create(
                model=self.MODEL,
                max_tokens=self.MAX_TOKENS,
                temperature=self.TEMPERATURE,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                response_model=VEXDocument,
            )

            # Set scan_session_id (instructor doesn't include in response)
            doc.scan_session_id = scan_session_id

        except Exception as e:
            logger.error(
                "LLM API call failed",
                error=str(e),
                scan_session_id=scan_session_id,
            )
            raise

        # Step 4: Post-LLM validation
        bundles_by_cve = {bundle.cve_id: bundle for bundle in bundles}
        validator = VEXJustificationValidator(bundles_by_cve)

        # Convert to validator's VEXDocument format for validation
        validator_doc = self._convert_to_validator_doc(doc)
        self.last_validation_failures = validator.validate(validator_doc)

        logger.info(
            "Post-validation complete",
            total_failures=len(self.last_validation_failures),
            blocking_failures=len([f for f in self.last_validation_failures if f.severity == "block"]),
            warnings=len([f for f in self.last_validation_failures if f.severity == "warn"]),
        )

        # Step 5: Filter blocking failures
        doc = self._filter_blocked_statements(doc, self.last_validation_failures)

        # Step 6: Add evidence coverage statistics
        doc.evidence_coverage = self._calculate_evidence_coverage(bundles)

        return doc

    def _filter_sufficient_evidence(
        self,
        bundles: List[VEXEvidenceBundle]
    ) -> List[VEXEvidenceBundle]:
        """
        Filter bundles to those with sufficient evidence for synthesis.

        Pre-LLM validation to avoid wasting LLM calls on insufficient evidence.

        Args:
            bundles: Evidence bundles to validate

        Returns:
            List of bundles with sufficient evidence

        UC-001 Implementation: Evidence sufficiency check
        """
        valid_bundles = []

        for bundle in bundles:
            # Check if bundle has at least 2 deterministic evidence nodes
            deterministic_nodes = bundle.deterministic_nodes()

            if len(deterministic_nodes) >= 2:
                valid_bundles.append(bundle)
                logger.debug(
                    "Bundle has sufficient evidence",
                    cve_id=bundle.cve_id,
                    deterministic_count=len(deterministic_nodes),
                )
            else:
                logger.warning(
                    "Bundle has insufficient evidence, skipping synthesis",
                    cve_id=bundle.cve_id,
                    deterministic_count=len(deterministic_nodes),
                    required_minimum=2,
                )

        return valid_bundles

    def _build_grounded_prompt(
        self,
        bundles: List[VEXEvidenceBundle],
        regulatory_context: List[str]
    ) -> str:
        """
        Build grounded prompt with real node IDs injected.

        Injects only node IDs that exist in bundles to prevent hallucination.
        LLM can only cite evidence that actually exists in knowledge graph.

        Args:
            bundles: Evidence bundles with real node IDs
            regulatory_context: Regulatory contexts for this assessment

        Returns:
            Prompt string with grounded evidence
        """
        # Build evidence context with real node IDs
        evidence_sections = []
        for bundle in bundles:
            evidence_section = f"""
## CVE: {bundle.cve_id}
**Component**: {bundle.component_purl}

### Available Evidence Nodes:
"""
            for node in bundle.nodes:
                deterministic_marker = "✓ DETERMINISTIC" if node.deterministic else "⚠ PROBABILISTIC"
                evidence_section += f"""
- **Node ID**: `{node.node_id}` ({deterministic_marker})
  - **Type**: {node.evidence_type}
  - **Source**: {node.source}
  - **Summary**: {node.summary}
"""
                if node.confidence is not None:
                    evidence_section += f"  - **Confidence**: {node.confidence:.2f}\n"

            evidence_sections.append(evidence_section)

        # Build full prompt
        regulatory_note = ""
        if regulatory_context:
            regulatory_note = f"""
**REGULATORY CONTEXT**: {', '.join(regulatory_context)}
- FDA 524B: Requires binary-level analysis for "not_affected" claims
- EU CRA: Requires detailed vulnerability handling documentation
"""

        prompt = f"""You are a regulatory-grade VEX (Vulnerability Exploitability eXchange) assessment generator.

{regulatory_note}

## Task
Generate VEX statements for the following CVEs based ONLY on the evidence nodes provided.

## Critical Requirements
1. **Evidence Grounding**: You MUST cite ONLY node IDs that exist in the "Available Evidence Nodes" sections above
   - NEVER fabricate or guess node IDs
   - Each evidence_refs entry MUST use a real node_id from the evidence
2. **Deterministic Evidence**: Prefer DETERMINISTIC evidence (✓) over PROBABILISTIC (⚠)
3. **Minimum Evidence**: Include at least 2 evidence references for "not_affected" status
4. **Detail Narratives**: Provide detailed justification (≥100 characters) mentioning specific node IDs

## Evidence Data

{chr(10).join(evidence_sections)}

## Output Format
Generate a VEXDocument containing VEXStatement objects for each CVE.

## Justification Codes (MVP Scope)
- `vulnerable_code_cannot_be_controlled_by_adversary`: Use when KEV evidence shows not in CISA catalog + CWE evidence available
- `inline_mitigations_already_exist`: Use when KEV absent + EPSS score is low

**IMPORTANT**: Only use node IDs that appear in the evidence sections above. Fabricating node IDs will result in validation failure.
"""

        return prompt

    def _convert_to_validator_doc(self, doc: VEXDocument) -> Any:
        """
        Convert VEXDocument to validator's document format.

        Args:
            doc: VEXDocument from LLM

        Returns:
            Validator-compatible document
        """
        # Import validator's VEXStatement and VEXDocument from validator module
        from .validator import VEXStatement as ValidatorStatement, VEXDocument as ValidatorDoc

        validator_statements = []
        for stmt in doc.statements:
            validator_statements.append(ValidatorStatement(
                cve_id=stmt.cve_id,
                component_purl=stmt.component_purl,
                status=stmt.status,
                justification=stmt.justification,
                evidence_refs=stmt.evidence_refs,
                detail=stmt.detail,
                regulatory_context=stmt.regulatory_context,
            ))

        return ValidatorDoc(statements=validator_statements)

    def _filter_blocked_statements(
        self,
        doc: VEXDocument,
        failures: List[ValidationFailure]
    ) -> VEXDocument:
        """
        Remove statements with blocking validation failures.

        Filters out statements that have severity="block" failures.
        Warnings are allowed to pass through.

        Args:
            doc: VEX document from LLM
            failures: Validation failures

        Returns:
            Document with blocked statements removed
        """
        # Build set of blocked CVE-component pairs
        blocked_pairs = {
            (f.cve_id, f.component_purl)
            for f in failures
            if f.severity == "block"
        }

        # Filter statements
        valid_statements = [
            stmt for stmt in doc.statements
            if (stmt.cve_id, stmt.component_purl) not in blocked_pairs
        ]

        if len(valid_statements) < len(doc.statements):
            logger.warning(
                "Filtered blocked statements",
                original_count=len(doc.statements),
                filtered_count=len(valid_statements),
                blocked_count=len(blocked_pairs),
            )

        doc.statements = valid_statements
        return doc

    def _create_under_investigation_doc(
        self,
        bundles: List[VEXEvidenceBundle],
        scan_session_id: str
    ) -> VEXDocument:
        """
        Create VEX document with under_investigation status for insufficient evidence.

        UC-001 Error Path: Insufficient evidence → under_investigation

        Args:
            bundles: Evidence bundles with insufficient evidence
            scan_session_id: Scan session identifier

        Returns:
            VEXDocument with under_investigation statements
        """
        statements = []
        for bundle in bundles:
            statements.append(VEXStatement(
                cve_id=bundle.cve_id,
                component_purl=bundle.component_purl,
                status="under_investigation",
                justification=None,
                evidence_refs=[],
                detail=f"Insufficient deterministic evidence available for {bundle.cve_id}. Further analysis required.",
                impact_summary="Status under investigation due to insufficient evidence.",
                regulatory_context=[],
            ))

        return VEXDocument(
            scan_session_id=scan_session_id,
            statements=statements,
            evidence_coverage={},
        )

    def _calculate_evidence_coverage(
        self,
        bundles: List[VEXEvidenceBundle]
    ) -> Dict[str, int]:
        """
        Calculate evidence type coverage statistics.

        Args:
            bundles: Evidence bundles

        Returns:
            Dict mapping evidence types to counts
        """
        coverage: Dict[str, int] = {}
        for bundle in bundles:
            for evidence_type in bundle.available_evidence_types():
                coverage[evidence_type] = coverage.get(evidence_type, 0) + 1
        return coverage
