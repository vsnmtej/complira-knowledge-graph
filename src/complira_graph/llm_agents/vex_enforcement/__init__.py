"""
VEX Enforcement Layer Package.

Provides evidence-grounded VEX synthesis with justification enforcement,
hallucination detection, and regulatory compliance validation.

Public APIs:
    - EnforcedVEXSynthesizer: Drop-in replacement for VEXSynthesizerV2 with enforcement
    - GroundedVEXSynthesizer: Grounded synthesis with validation
    - VEXJustificationValidator: Post-generation validator
    - VEXEvidenceBundle: Evidence bundle model
    - JustificationCode: VEX justification code enum
    - ValidationFailure: Validation failure model

Usage:
    >>> from complira_graph.llm_agents.vex_enforcement import (
    ...     EnforcedVEXSynthesizer,
    ...     VEXEvidenceBundle,
    ... )
    >>>
    >>> from anthropic import Anthropic
    >>> client = Anthropic(api_key="...")
    >>> synthesizer = EnforcedVEXSynthesizer(client)
    >>>
    >>> result = await synthesizer.synthesize(
    ...     bundles=[bundle1, bundle2],
    ...     scan_session_id="scan_123",
    ...     regulatory_context=["FDA_524B"]
    ... )

Author: Complira Development Team
Version: 1.0
Ticket: vex-justification-enforcement
"""

from .wrapper import EnforcedVEXSynthesizer
from .synthesizer import GroundedVEXSynthesizer, VEXDocument, VEXStatement
from .validator import VEXJustificationValidator, ValidationFailure
from .grounding import (
    VEXEvidenceBundle,
    EvidenceNode,
    JustificationCode,
    REQUIRED_EVIDENCE_FOR_JUSTIFICATION,
)

__all__ = [
    # Primary public API (wrapper)
    "EnforcedVEXSynthesizer",

    # Grounded synthesizer (advanced usage)
    "GroundedVEXSynthesizer",
    "VEXDocument",
    "VEXStatement",

    # Validator (advanced usage)
    "VEXJustificationValidator",
    "ValidationFailure",

    # Evidence grounding (advanced usage)
    "VEXEvidenceBundle",
    "EvidenceNode",
    "JustificationCode",
    "REQUIRED_EVIDENCE_FOR_JUSTIFICATION",
]

__version__ = "1.0.0"
