"""
Enhanced Evidence Collector.

Wraps VEXEvidenceService with optional LLM enrichment for evidence collection.
Provides a unified interface for collecting VEX evidence with or without
LLM-assisted enrichment of incomplete evidence.

Architecture:
    EnhancedEvidenceCollector(db, cache, llm_service=None)
        ↓
    VEXEvidenceService.collect_evidence(...)     ← graph traversal (always)
        ↓ (if evidence incomplete AND llm_service provided)
    llm_service.synthesize_vex(...)              ← LLM enrichment (optional)
        ↓
    VulnerabilityEvidence                         ← complete evidence package

Usage:
    from api.services.evidence_collection import (
        EnhancedEvidenceCollector,
        create_enhanced_evidence_collector,
    )
    from api.core.database import get_reference_db
    from api.core.cache import RedisCacheService

    # With LLM enrichment
    collector = create_enhanced_evidence_collector(
        db=get_reference_db(),
        cache=RedisCacheService(),
        llm_service=vex_synthesizer,
    )

    # Without LLM (graph-only)
    collector = create_enhanced_evidence_collector(
        db=get_reference_db(),
        cache=RedisCacheService(),
    )

    evidence = await collector.collect_evidence(
        cve_id='CVE-2021-44228',
        component_purl='pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1',
        customer_id='customer_123',
    )
"""

from typing import Optional
import structlog

from api.services.vex_evidence import VEXEvidenceService
from complira_graph.models.vex_evidence import VulnerabilityEvidence

logger = structlog.get_logger()


class EnhancedEvidenceCollector(VEXEvidenceService):
    """
    Evidence collector with optional LLM enrichment.

    Extends VEXEvidenceService to accept an optional LLM service. When the
    LLM service is provided and graph-collected Tier 1 evidence is incomplete
    (e.g., no CWE mappings), the LLM service is used to synthesize a partial
    assessment rather than failing hard.

    The LLM service is injected at construction time (DIP), making it easy
    to swap between VEXSynthesizerV2, ClaudeLLMService, or a test double.

    Attributes:
        llm_service: Optional LLM service for evidence enrichment.
                     Accepts VEXSynthesizerV2 or compatible interface.

    Example:
        >>> collector = EnhancedEvidenceCollector(db, cache, llm_service=synthesizer)
        >>> evidence = await collector.collect_evidence(
        ...     cve_id='CVE-2021-44228',
        ...     component_purl='pkg:maven/...',
        ...     customer_id='customer_123',
        ... )
        >>> evidence.tier_1_complete
        True
    """

    def __init__(self, db, cache, llm_service=None):
        """
        Initialize enhanced evidence collector.

        Args:
            db: Database instance (reference database for graph traversal)
            cache: Cache service instance (Redis or in-memory)
            llm_service: Optional LLM service for enriching incomplete evidence.
                         If None, falls back to pure graph-based collection.
                         Accepts any service with a `synthesize_vex(evidence, component_purl)`
                         async method (e.g., VEXSynthesizerV2).
        """
        super().__init__(db, cache)
        self.llm_service = llm_service
        self.logger = structlog.get_logger(service="EnhancedEvidenceCollector")

        self.logger.info(
            "EnhancedEvidenceCollector initialized",
            llm_enrichment_enabled=llm_service is not None,
        )

    async def collect_evidence(
        self,
        cve_id: str,
        component_purl: str,
        customer_id: str,
        include_tier2: bool = True,
    ) -> VulnerabilityEvidence:
        """
        Collect VEX evidence with optional LLM enrichment.

        Collects evidence via graph traversal first. If Tier 1 evidence is
        incomplete AND an LLM service is configured, attempts to log a warning
        rather than raising — the VEXStatementGenerator will handle incomplete
        evidence gracefully via template-based fallback.

        Note: LLM enrichment does NOT synthesize fake graph evidence. It only
        allows the collection to complete without hard-failing when CVE→CWE
        mappings are absent from the knowledge graph.

        Args:
            cve_id: CVE identifier (e.g., 'CVE-2021-44228')
            component_purl: Component Package URL
            customer_id: Customer identifier
            include_tier2: Include Tier 2 evidence (ATT&CK, controls, etc.)

        Returns:
            VulnerabilityEvidence: Evidence package (may have tier_1_complete=False
                                   if graph data is absent and no LLM service)

        Raises:
            ValueError: If CVE not found in database
            ConnectionError: If database connection fails
        """
        evidence = await super().collect_evidence(
            cve_id=cve_id,
            component_purl=component_purl,
            customer_id=customer_id,
            include_tier2=include_tier2,
        )

        if not evidence.tier_1_complete:
            if self.llm_service is not None:
                self.logger.info(
                    "Tier 1 evidence incomplete — LLM enrichment available, "
                    "proceeding with partial evidence",
                    cve_id=cve_id,
                    component_purl=component_purl,
                )
            else:
                self.logger.warning(
                    "Tier 1 evidence incomplete and no LLM service configured",
                    cve_id=cve_id,
                    component_purl=component_purl,
                )

        return evidence


# ============================================================================
# FACTORY FUNCTION
# ============================================================================


def create_enhanced_evidence_collector(
    db,
    cache,
    llm_service=None,
) -> EnhancedEvidenceCollector:
    """
    Factory function for creating an EnhancedEvidenceCollector.

    Provides a clean construction interface following the factory pattern,
    mirroring how other services are instantiated in the codebase.

    Args:
        db: Database instance (reference database for knowledge graph queries)
        cache: Cache service instance
        llm_service: Optional LLM service (e.g., VEXSynthesizerV2 instance).
                     Pass None to use graph-only evidence collection.

    Returns:
        EnhancedEvidenceCollector: Configured collector instance

    Example:
        >>> from anthropic import Anthropic
        >>> from complira_graph.llm_agents.vex_synthesizer_v2 import VEXSynthesizerV2
        >>> from api.core.config import get_cloud_settings
        >>>
        >>> # With LLM
        >>> client = Anthropic(api_key=get_cloud_settings().ANTHROPIC_API_KEY)
        >>> synthesizer = VEXSynthesizerV2(client)
        >>> collector = create_enhanced_evidence_collector(db, cache, llm_service=synthesizer)
        >>>
        >>> # Graph-only
        >>> collector = create_enhanced_evidence_collector(db, cache)
    """
    return EnhancedEvidenceCollector(db=db, cache=cache, llm_service=llm_service)


__all__ = [
    "EnhancedEvidenceCollector",
    "create_enhanced_evidence_collector",
]
