"""
Evidence ingestion pipeline package.

Public API:
- EvidenceIngestionService: main pipeline orchestrator
- BackfillAdapter: legacy customer DB migration
- ADAPTER_REGISTRY, register_adapter: tool adapter configuration
- PipelineCoordinator: three-stage post-ingestion pipeline orchestrator
- EnrichmentPipeline: UC-007 CVE enrichment stage
- CompactionPipeline: UC-008 risk scoring and compaction stage
- ControlMappingPipeline: UC-009 compliance coverage stage
- ScanEnrichmentRepository: bulk read/write data-access layer for pipeline stages
"""

from complira_graph.ingestion.service import EvidenceIngestionService
from complira_graph.ingestion.backfill import BackfillAdapter
from complira_graph.ingestion.adapter_registry import ADAPTER_REGISTRY, register_adapter
from complira_graph.ingestion.scan_enrichment_repository import ScanEnrichmentRepository
from complira_graph.ingestion.enrichment_pipeline import EnrichmentPipeline
from complira_graph.ingestion.compaction_pipeline import CompactionPipeline
from complira_graph.ingestion.control_mapping_pipeline import ControlMappingPipeline
from complira_graph.ingestion.pipeline_coordinator import PipelineCoordinator

__all__ = [
    "EvidenceIngestionService",
    "BackfillAdapter",
    "ADAPTER_REGISTRY",
    "register_adapter",
    "ScanEnrichmentRepository",
    "EnrichmentPipeline",
    "CompactionPipeline",
    "ControlMappingPipeline",
    "PipelineCoordinator",
]
