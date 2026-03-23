"""
Evidence ingestion pipeline package.

Phase 1 public API:
- EvidenceIngestionService: main pipeline orchestrator
- BackfillAdapter: legacy customer DB migration
- ADAPTER_REGISTRY, register_adapter: tool adapter configuration
- PipelineCoordinator: six-stage post-ingestion pipeline orchestrator
- EnrichmentPipeline: UC-007 CVE enrichment stage
- CompactionPipeline: UC-008 risk scoring and compaction stage
- ControlMappingPipeline: UC-009 compliance coverage stage
- ScanEnrichmentRepository: bulk read/write data-access layer for pipeline stages

Phase 2 additions:
- PipelineLLMClient: sync Anthropic Claude wrapper for pipeline layer
- ScanLLMEnrichmentRepository: write LLM fields to scan_findings
- ScanBlastRadiusRepository: blast radius AQL traversal and writes
- LLMEnrichmentPipeline: UC-010 LLM enrichment stage
- BlastRadiusPipeline: UC-011 blast radius simulation stage
- EPSSVelocityPipeline: UC-012 EPSS velocity detection stage
"""

from complira_graph.ingestion.service import EvidenceIngestionService
from complira_graph.ingestion.backfill import BackfillAdapter
from complira_graph.ingestion.adapter_registry import ADAPTER_REGISTRY, register_adapter
from complira_graph.ingestion.scan_enrichment_repository import ScanEnrichmentRepository
from complira_graph.ingestion.enrichment_pipeline import EnrichmentPipeline
from complira_graph.ingestion.compaction_pipeline import CompactionPipeline
from complira_graph.ingestion.control_mapping_pipeline import ControlMappingPipeline
from complira_graph.ingestion.pipeline_coordinator import PipelineCoordinator
from complira_graph.ingestion.pipeline_llm_client import PipelineLLMClient
from complira_graph.ingestion.scan_llm_enrichment_repository import ScanLLMEnrichmentRepository
from complira_graph.ingestion.scan_blast_radius_repository import ScanBlastRadiusRepository
from complira_graph.ingestion.llm_enrichment_pipeline import LLMEnrichmentPipeline
from complira_graph.ingestion.blast_radius_pipeline import BlastRadiusPipeline
from complira_graph.ingestion.epss_velocity_pipeline import EPSSVelocityPipeline

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
    "PipelineLLMClient",
    "ScanLLMEnrichmentRepository",
    "ScanBlastRadiusRepository",
    "LLMEnrichmentPipeline",
    "BlastRadiusPipeline",
    "EPSSVelocityPipeline",
]
