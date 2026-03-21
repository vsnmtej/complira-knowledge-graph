"""
LLM enrichment agents for knowledge graph enhancement.

These agents use Claude models to fill gaps and generate insights that are
not available from deterministic data sources.

Agents:
- CWEClassifierAgent: Classify CVEs to CWE weakness types
- PURLtoCPEAgent: Map package URLs to CPE identifiers
- VEXSynthesizerAgent: Generate VEX documents for vulnerabilities
- RegulatoryMapperAgent: Map vulnerabilities to compliance requirements
- CVEEntityExtractorAgent: Extract structured data from CVE descriptions
"""

from .cwe_classifier import CWEClassifierAgent

__all__ = [
    'CWEClassifierAgent',
]
