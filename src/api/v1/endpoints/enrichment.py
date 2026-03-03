"""
Enrichment endpoints (Phase 2).

POST /v1/enrich - Enrich scan findings with vulnerability intelligence
POST /v1/compact - Compact findings (deduplicate + CWE rollup)
POST /v1/map-controls - Map findings to regulatory controls
"""

from fastapi import APIRouter, Depends, HTTPException
import structlog
import time

from api.core.security import Customer, get_current_customer
from api.core.database import get_reference_db
from api.core.cache import RedisCacheService
from api.services.enrichment import EnrichmentService
from api.services.compaction import CompactionService
from api.services.control_mapping import ControlMappingService
from complira_graph.models import (
    EnrichRequest,
    EnrichResponse,
    CompactRequest,
    CompactResponse,
    MapControlsRequest,
    ControlMappingsResponse,
)

logger = structlog.get_logger()

router = APIRouter()


@router.post("/enrich", response_model=EnrichResponse)
async def enrich_scan_findings(
    request: EnrichRequest,
    customer: Customer = Depends(get_current_customer),
):
    """
    POST /v1/enrich

    Enrich scan findings with vulnerability intelligence.

    Enriches findings with:
    - **CVE Details**: Description, CVSS scores, published date
    - **EPSS Score**: Exploit prediction probability (0-1)
    - **KEV Status**: CISA Known Exploited Vulnerabilities catalog
    - **Threat Intelligence**: CWE → CAPEC → ATT&CK technique chain

    Args:
    - **scan_session_id**: Scan session identifier (from /v1/scan/ingest)
    - **include_threat_intel**: Include CWE → CAPEC → ATT&CK chain (default: true)
    - **include_kev**: Include CISA KEV status (default: true)
    - **include_epss**: Include EPSS scores (default: true)

    Returns:
    - **total_findings**: Number of findings enriched
    - **enriched_findings**: List of findings with enrichment data
    - **enrichment_metadata**: Coverage statistics (CVE enrichment %, EPSS %, KEV %, threat intel %)

    Example:
    ```bash
    curl -X POST https://api.complira.dev/v1/enrich \\
      -H "X-API-Key: your_api_key" \\
      -H "Content-Type: application/json" \\
      -d '{
        "scan_session_id": "scan_sess_123",
        "include_threat_intel": true,
        "include_kev": true,
        "include_epss": true
      }'
    ```

    Performance:
    - Expected: ~2-3 seconds for 100 findings (with batch queries)
    """
    start_time = time.time()

    try:
        # Initialize service
        service = EnrichmentService(
            db=get_reference_db(),
            cache=RedisCacheService(),
        )

        # Enrich scan
        result = await service.enrich_scan_session(
            customer_id=customer.id,
            scan_session_id=request.scan_session_id,
            include_threat_intel=request.include_threat_intel,
            include_kev=request.include_kev,
            include_epss=request.include_epss,
        )

        execution_time_ms = (time.time() - start_time) * 1000

        logger.info(
            "Enrichment request complete",
            customer_id=customer.id,
            scan_session_id=request.scan_session_id,
            total_findings=result.total_findings,
            execution_time_ms=execution_time_ms,
        )

        return result

    except ValueError as e:
        logger.warning(
            "Enrichment validation error",
            customer_id=customer.id,
            error=str(e),
        )
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.error(
            "Enrichment failed",
            customer_id=customer.id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error during enrichment"
        )


@router.post("/compact", response_model=CompactResponse)
async def compact_scan_findings(
    request: CompactRequest,
    customer: Customer = Depends(get_current_customer),
):
    """
    POST /v1/compact

    Compact scan findings (deduplicate + CWE rollup).

    Compaction strategies:
    - **Deduplication**: Group findings by CVE ID, aggregate affected locations
    - **CWE Rollup**: Roll up CWEs to higher abstraction levels (Class, Pillar)

    Args:
    - **scan_session_id**: Scan session identifier
    - **deduplication_strategy**: Deduplication strategy ("by_cve") - default: "by_cve"
    - **cwe_rollup_level**: CWE abstraction level ("Class" or "Pillar") - default: "Class"

    Returns:
    - **original_finding_count**: Number of findings before compaction
    - **compacted_finding_count**: Number of findings after compaction
    - **reduction_percentage**: Percentage reduction (0-100)
    - **compacted_findings**: List of compacted findings
    - **compaction_metadata**: CWE rollup statistics

    Example:
    ```bash
    curl -X POST https://api.complira.dev/v1/compact \\
      -H "X-API-Key: your_api_key" \\
      -H "Content-Type: application/json" \\
      -d '{
        "scan_session_id": "scan_sess_123",
        "deduplication_strategy": "by_cve",
        "cwe_rollup_level": "Class"
      }'
    ```

    Performance:
    - Expected: ~1-2 seconds for 100 findings
    - Read-only (MVP decision D2 - does not modify scan_findings)
    """
    start_time = time.time()

    try:
        # Initialize service
        service = CompactionService(
            db=get_reference_db(),
            cache=RedisCacheService(),
        )

        # Compact findings
        result = await service.compact_findings(
            customer_id=customer.id,
            scan_session_id=request.scan_session_id,
            deduplication_strategy=request.deduplication_strategy,
            cwe_rollup_level=request.cwe_rollup_level,
        )

        execution_time_ms = (time.time() - start_time) * 1000

        logger.info(
            "Compaction request complete",
            customer_id=customer.id,
            scan_session_id=request.scan_session_id,
            original_count=result.original_finding_count,
            compacted_count=result.compacted_finding_count,
            execution_time_ms=execution_time_ms,
        )

        return result

    except ValueError as e:
        logger.warning(
            "Compaction validation error",
            customer_id=customer.id,
            error=str(e),
        )
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.error(
            "Compaction failed",
            customer_id=customer.id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error during compaction"
        )


@router.post("/map-controls", response_model=ControlMappingsResponse)
async def map_findings_to_controls(
    request: MapControlsRequest,
    customer: Customer = Depends(get_current_customer),
):
    """
    POST /v1/map-controls

    Map scan findings to regulatory controls.

    Supported frameworks:
    - **NIST 800-53**: Federal Information Security Management Act (FISMA) controls
    - **FDA 524B**: FDA Software Validation Guidance
    - **ISO 27001**: Information Security Management System (ISMS) controls

    Args:
    - **scan_session_id**: Scan session identifier
    - **frameworks**: List of frameworks to map to (default: ["NIST 800-53", "FDA 524B", "ISO 27001"])
    - **use_compacted_view**: Use compacted findings for efficiency (default: true)

    Returns:
    - **control_mappings**: List of findings mapped to controls
    - **control_statistics**: Aggregate statistics (total controls, coverage %)
    - **used_compacted_view**: Whether compacted view was used

    Example:
    ```bash
    curl -X POST https://api.complira.dev/v1/map-controls \\
      -H "X-API-Key: your_api_key" \\
      -H "Content-Type: application/json" \\
      -d '{
        "scan_session_id": "scan_sess_123",
        "frameworks": ["NIST 800-53", "FDA 524B", "ISO 27001"],
        "use_compacted_view": true
      }'
    ```

    Performance:
    - Expected: ~2-3 seconds for 70 compacted findings
    - Batch queries for CWE → control mappings
    """
    start_time = time.time()

    try:
        # Initialize service
        service = ControlMappingService(
            db=get_reference_db(),
            cache=RedisCacheService(),
        )

        # Map controls
        result = await service.map_controls(
            customer_id=customer.id,
            scan_session_id=request.scan_session_id,
            frameworks=request.frameworks,
            use_compacted_view=request.use_compacted_view,
        )

        execution_time_ms = (time.time() - start_time) * 1000

        logger.info(
            "Control mapping request complete",
            customer_id=customer.id,
            scan_session_id=request.scan_session_id,
            total_mappings=result.control_statistics.total_findings_mapped,
            execution_time_ms=execution_time_ms,
        )

        return result

    except ValueError as e:
        logger.warning(
            "Control mapping validation error",
            customer_id=customer.id,
            error=str(e),
        )
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.error(
            "Control mapping failed",
            customer_id=customer.id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error during control mapping"
        )
