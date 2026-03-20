"""
Evidence ingestion pipeline package.

Public API:
- EvidenceIngestionService: main pipeline orchestrator
- BackfillAdapter: legacy customer DB migration
- ADAPTER_REGISTRY, register_adapter: tool adapter configuration
"""

from complira_graph.ingestion.service import EvidenceIngestionService
from complira_graph.ingestion.backfill import BackfillAdapter
from complira_graph.ingestion.adapter_registry import ADAPTER_REGISTRY, register_adapter

__all__ = [
    "EvidenceIngestionService",
    "BackfillAdapter",
    "ADAPTER_REGISTRY",
    "register_adapter",
]
