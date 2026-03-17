"""
VEX Justification Validator Module.

Provides post-generation validation for VEX statements to detect hallucination,
evidence gaps, and regulatory compliance issues. Implements blocking vs warning
severity levels for submission readiness guidance.

Key Validation Checks:
1. Node ID existence (hallucination detection)
2. Justification code supported by deterministic evidence
3. Deterministic/probabilistic evidence ratio
4. Regulatory bar enforcement (FDA 524B, EU CRA)

Compliance:
- FDA 524B: Binary analysis required for "not_affected" claims
- EU CRA: Detailed vulnerability handling documentation

Author: Complira Development Team
Version: 1.0
Ticket: vex-justification-enforcement
"""

from typing import List, Dict, Literal, Optional
from pydantic import BaseModel, Field

from .grounding import VEXEvidenceBundle, JustificationCode


# ========== Validation Failure Model ==========


class ValidationFailure(BaseModel):
    """
    Single validation failure with severity.

    Represents one validation check failure for a VEX statement. Severity
    determines whether the failure blocks submission or is a warning.

    Severity Levels:
        - block: Statement cannot be submitted (critical failure)
        - warn: Statement can be submitted but review recommended

    Fields:
        - cve_id: CVE identifier for the failed statement
        - component_purl: Component Package URL
        - reason: Human-readable explanation of failure
        - severity: "block" (cannot submit) or "warn" (review recommended)
        - validation_type: Type of validation that failed

    Example:
        >>> failure = ValidationFailure(
        ...     cve_id="CVE-2021-44228",
        ...     component_purl="pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
        ...     reason="Hallucinated evidence reference: 'fake/node123' does not exist in KG",
        ...     severity="block",
        ...     validation_type="node_id_existence"
        ... )
    """
    cve_id: str = Field(
        description="CVE identifier"
    )
    component_purl: str = Field(
        description="Component Package URL"
    )
    reason: str = Field(
        description="Human-readable failure explanation",
        min_length=1
    )
    severity: Literal["block", "warn"] = Field(
        description="Failure severity: 'block' prevents submission, 'warn' allows with review"
    )
    validation_type: str = Field(
        description="Type of validation check that failed",
        examples=["node_id_existence", "justification_support", "determinism_ratio", "regulatory_bar"]
    )

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "cve_id": "CVE-2021-44228",
                "component_purl": "pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
                "reason": "Hallucinated evidence reference: 'fake/node123' does not exist in knowledge graph",
                "severity": "block",
                "validation_type": "node_id_existence"
            }]
        }
    }


# ========== VEX Statement Models (Minimal for Validation) ==========


class EvidenceReference(BaseModel):
    """Evidence reference in VEX statement."""
    node_id: str = Field(description="ArangoDB _id from evidence bundle")
    relevance_explanation: str = Field(description="Why this evidence is relevant")


class VEXStatement(BaseModel):
    """
    VEX statement for validation (minimal fields needed by validator).

    This is a simplified version of the full VEXStatement model used only
    for validation purposes. Full model definition is in synthesizer.py.
    """
    cve_id: str
    component_purl: str
    status: Literal["not_affected", "affected", "fixed", "under_investigation"]
    justification: Optional[JustificationCode] = None
    evidence_refs: List[EvidenceReference] = Field(default_factory=list)
    detail: str
    regulatory_context: List[str] = Field(default_factory=list)


class VEXDocument(BaseModel):
    """
    VEX document for validation (minimal fields needed by validator).

    This is a simplified version used only for validation. Full model
    definition is in synthesizer.py.
    """
    statements: List[VEXStatement]


# ========== Validator ==========


class VEXJustificationValidator:
    """
    Post-generation validator for hallucination and evidence gaps.

    Validates VEX statements after LLM generation to ensure:
    - All cited evidence node IDs exist in knowledge graph
    - Justification codes are supported by deterministic evidence
    - Deterministic evidence ratio meets thresholds
    - Regulatory requirements are satisfied

    Usage:
        >>> bundles = {"CVE-2021-44228": bundle1, "CVE-2024-1234": bundle2}
        >>> validator = VEXJustificationValidator(bundles)
        >>> failures = validator.validate(vex_document)
        >>> blocking_failures = [f for f in failures if f.severity == "block"]
        >>> submission_ready = len(blocking_failures) == 0
    """

    def __init__(self, bundles: Dict[str, VEXEvidenceBundle]):
        """
        Initialize validator with evidence bundles.

        Args:
            bundles: Dict mapping CVE IDs to their evidence bundles
        """
        self.bundles = bundles

        # Build node ID index for fast lookup (O(1) hallucination detection)
        self._all_node_ids: Dict[str, set] = {}
        for cve_id, bundle in bundles.items():
            self._all_node_ids[cve_id] = bundle.node_id_index()

    def validate(self, doc: VEXDocument) -> List[ValidationFailure]:
        """
        Run all validation checks on VEX document.

        Validates all statements in the document and aggregates failures.

        Args:
            doc: VEX document to validate

        Returns:
            List of validation failures (empty if all checks pass)

        Example:
            >>> failures = validator.validate(vex_document)
            >>> for failure in failures:
            ...     print(f"{failure.severity.upper()}: {failure.reason}")
        """
        failures: List[ValidationFailure] = []

        for stmt in doc.statements:
            # Get bundle for this CVE
            bundle = self.bundles.get(stmt.cve_id)
            if not bundle:
                # Skip validation if bundle not available (graceful degradation)
                continue

            # Run all validation checks
            failures.extend(self._check_node_ids_exist(stmt, bundle))
            failures.extend(self._check_justification_supported(stmt, bundle))
            failures.extend(self._check_determinism_ratio(stmt, bundle))
            failures.extend(self._check_regulatory_bar(stmt, bundle))

        return failures

    def _check_node_ids_exist(self, stmt: VEXStatement, bundle: VEXEvidenceBundle) -> List[ValidationFailure]:
        """
        Check that all cited evidence node IDs exist in bundle (hallucination detection).

        This is a BLOCKING check. If LLM fabricates a node ID that doesn't exist
        in the pre-fetched evidence bundle, the statement is rejected.

        Args:
            stmt: VEX statement to validate
            bundle: Evidence bundle for this CVE

        Returns:
            List of validation failures (empty if all node IDs exist)

        UC-002 Implementation:
            - Primary path: All node IDs exist → Pass
            - Error path: Any node ID missing → Block statement
        """
        failures = []
        node_id_index = self._all_node_ids.get(stmt.cve_id, set())

        for ref in stmt.evidence_refs:
            if ref.node_id not in node_id_index:
                failures.append(ValidationFailure(
                    cve_id=stmt.cve_id,
                    component_purl=stmt.component_purl,
                    reason=f"Hallucinated evidence reference: '{ref.node_id}' does not exist in knowledge graph",
                    severity="block",  # ❌ Cannot submit with fabricated evidence
                    validation_type="node_id_existence"
                ))

        return failures

    def _check_justification_supported(self, stmt: VEXStatement, bundle: VEXEvidenceBundle) -> List[ValidationFailure]:
        """
        Check that justification code is supported by deterministic evidence.

        Validates that the VEX statement's justification code has the required
        deterministic evidence available in the bundle.

        Args:
            stmt: VEX statement to validate
            bundle: Evidence bundle for this CVE

        Returns:
            List of validation failures (empty if justification supported)

        UC-001 Implementation:
            - Primary path: Required evidence present → Pass
            - Error path: Evidence insufficient → Block statement
        """
        failures = []

        # Only validate justification for "not_affected" status
        if stmt.status != "not_affected" or not stmt.justification:
            return failures

        # Check if bundle has required evidence for this justification code
        if not bundle.can_support_justification(stmt.justification):
            from .grounding import REQUIRED_EVIDENCE_FOR_JUSTIFICATION
            required_types = REQUIRED_EVIDENCE_FOR_JUSTIFICATION.get(stmt.justification, [])

            failures.append(ValidationFailure(
                cve_id=stmt.cve_id,
                component_purl=stmt.component_purl,
                reason=(
                    f"Justification '{stmt.justification}' requires deterministic evidence types "
                    f"{required_types}, but bundle does not contain sufficient evidence"
                ),
                severity="block",  # ❌ Cannot submit without required evidence
                validation_type="justification_support"
            ))

        return failures

    def _check_determinism_ratio(self, stmt: VEXStatement, bundle: VEXEvidenceBundle) -> List[ValidationFailure]:
        """
        Check deterministic vs probabilistic evidence ratio.

        Warns if statement cites >50% probabilistic evidence. This is a WARNING
        level check - statement can still be submitted but should be reviewed.

        Args:
            stmt: VEX statement to validate
            bundle: Evidence bundle for this CVE

        Returns:
            List of validation failures (empty if ratio acceptable)

        UC-003 Implementation:
            - Primary path: >50% deterministic → Pass
            - Warning path: ≤50% deterministic → Warn
        """
        failures = []

        if not stmt.evidence_refs:
            return failures

        # Count deterministic vs probabilistic evidence among cited nodes
        node_id_index = bundle.node_id_index()
        cited_nodes = [
            node for node in bundle.nodes
            if node.node_id in [ref.node_id for ref in stmt.evidence_refs]
        ]

        if not cited_nodes:
            return failures

        deterministic_count = sum(1 for node in cited_nodes if node.deterministic)
        total_count = len(cited_nodes)
        deterministic_ratio = deterministic_count / total_count if total_count > 0 else 0.0

        # Warn if ≤50% deterministic evidence
        if deterministic_ratio <= 0.5:
            failures.append(ValidationFailure(
                cve_id=stmt.cve_id,
                component_purl=stmt.component_purl,
                reason=(
                    f"Low deterministic evidence ratio: {deterministic_count}/{total_count} "
                    f"({deterministic_ratio:.0%}). Statement relies heavily on probabilistic "
                    f"(ML/LLM-sourced) evidence. Review recommended for regulatory submissions."
                ),
                severity="warn",  # ⚠️ Can submit, but recommend review
                validation_type="determinism_ratio"
            ))

        return failures

    def _check_regulatory_bar(self, stmt: VEXStatement, bundle: VEXEvidenceBundle) -> List[ValidationFailure]:
        """
        Check regulatory-context-specific requirements.

        Validates regulatory requirements based on the statement's regulatory_context:
        - FDA 524B: Requires binary_analysis_result evidence for "not_affected" claims
        - EU CRA: Requires detailed justification narratives (>100 chars)

        Args:
            stmt: VEX statement to validate
            bundle: Evidence bundle for this CVE

        Returns:
            List of validation failures (empty if regulatory bar met)

        UC-004 Implementation:
            - Primary path: Regulatory evidence present → Pass
            - Warning path: Regulatory evidence missing → Warn
        """
        failures = []

        if not stmt.regulatory_context:
            return failures

        # FDA 524B: Binary analysis requirement for "not_affected"
        if "FDA_524B" in stmt.regulatory_context and stmt.status == "not_affected":
            # Check if bundle has binary analysis evidence
            # Note: MVP scope uses existing evidence types only
            # binary_analysis_result collection may not exist yet
            available_types = bundle.available_evidence_types()

            if "binary_analysis_result" not in available_types:
                failures.append(ValidationFailure(
                    cve_id=stmt.cve_id,
                    component_purl=stmt.component_purl,
                    reason=(
                        "FDA 524B regulatory context requires binary-level analysis evidence "
                        "for 'not_affected' status, but no binary analysis evidence found. "
                        "Consider running binary analysis or providing manual attestation."
                    ),
                    severity="warn",  # ⚠️ Can submit, but regulatory review may fail
                    validation_type="regulatory_bar"
                ))

        # EU CRA: Detailed justification narrative requirement
        if "EU_CRA" in stmt.regulatory_context:
            # Check detail field length (EU CRA requires detailed documentation)
            if len(stmt.detail) < 100:
                failures.append(ValidationFailure(
                    cve_id=stmt.cve_id,
                    component_purl=stmt.component_purl,
                    reason=(
                        f"EU CRA regulatory context requires detailed justification narrative "
                        f"(≥100 characters), but detail field is only {len(stmt.detail)} characters. "
                        f"Expand justification with technical details."
                    ),
                    severity="warn",  # ⚠️ Can submit, but may not meet CRA standards
                    validation_type="regulatory_bar"
                ))

        return failures

    def is_submission_ready(self, failures: List[ValidationFailure]) -> bool:
        """
        Check if VEX document is ready for submission.

        Document is submission-ready if there are no BLOCKING failures.
        Warnings can exist but should be reviewed before submission.

        Args:
            failures: List of validation failures from validate()

        Returns:
            True if no blocking failures, False otherwise

        Example:
            >>> failures = validator.validate(doc)
            >>> if validator.is_submission_ready(failures):
            ...     print("Ready to submit")
            ... else:
            ...     print("Cannot submit - blocking failures exist")
        """
        return all(f.severity != "block" for f in failures)

    def get_failures_by_severity(
        self,
        failures: List[ValidationFailure]
    ) -> Dict[Literal["block", "warn"], List[ValidationFailure]]:
        """
        Group validation failures by severity.

        Args:
            failures: List of validation failures

        Returns:
            Dict with "block" and "warn" keys containing respective failures

        Example:
            >>> failures_by_severity = validator.get_failures_by_severity(failures)
            >>> print(f"Blocking: {len(failures_by_severity['block'])}")
            >>> print(f"Warnings: {len(failures_by_severity['warn'])}")
        """
        return {
            "block": [f for f in failures if f.severity == "block"],
            "warn": [f for f in failures if f.severity == "warn"]
        }
