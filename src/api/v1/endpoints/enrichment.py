"""
Enrichment API endpoints for Phase 1.

Provides graph-based vulnerability intelligence with:
- Smart risk scoring (CVSS + EPSS + KEV + exploits)
- Attack path discovery (graph traversal)
- Compliance mapping (graph relationships)

All data is authoritative - no LLM guessing.
"""

from typing import List
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
import structlog

from api.models.responses.enrichment import (
    EnrichmentRequest,
    EnrichmentResponse,
    CVEEnrichment,
)
from api.services.enrichment_service import EnrichmentService
from api.core.cache import cache

logger = structlog.get_logger()

# Create router
router = APIRouter()


@router.post(
    "/enrich",
    response_model=EnrichmentResponse,
    summary="Enrich CVEs with graph-based intelligence",
    description="""
    Deep enrichment of CVEs with authoritative graph database intelligence.

    **Features:**
    - **Smart risk scoring**: CVSS + EPSS + KEV + public exploits
    - **Attack path discovery**: CVE → CWE → CAPEC → ATT&CK → Threat Groups
    - **Compliance mapping**: NIST, FDA, ISO frameworks
    - **All authoritative data**: No LLM guessing

    **Authentication:** None required (uses reference database)

    **Rate Limits:** 60 requests/minute

    **Example Request:**
    ```json
    {
      "cve_ids": ["CVE-2024-21413", "CVE-2023-44487"],
      "include_attack_paths": true,
      "include_compliance": false
    }
    ```

    **Example Response:**
    ```json
    {
      "enriched": [
        {
          "cve_id": "CVE-2024-21413",
          "cvss_score": 9.8,
          "epss_score": 0.85,
          "in_kev": true,
          "exploit_count": 3,
          "risk_score": 0.92,
          "priority": "CRITICAL",
          "risk_factors": {
            "high_epss": true,
            "actively_exploited": true,
            "high_cvss": true,
            "public_exploits": true,
            "threat_groups_using": true
          },
          "cwe_list": ["CWE-89"],
          "attack_techniques": ["T1190"],
          "threat_groups": ["APT28", "APT29"],
          "attack_path": {
            "path": [...],
            "defenses": [...]
          }
        }
      ],
      "total": 1,
      "processing_time_ms": 250.5
    }
    ```

    **Data Sources:**
    - CVSS scores: NVD authoritative
    - EPSS scores: FIRST.org exploitation probability
    - KEV catalog: CISA confirmed active exploitation
    - ATT&CK: MITRE authoritative techniques
    - D3FEND: Evidence-based defenses
    """,
    tags=["enrichment"],
)
async def enrich_cves(request: EnrichmentRequest) -> EnrichmentResponse:
    """
    Enrich CVEs with graph-based intelligence.

    Args:
        request: Enrichment request with CVE IDs and options

    Returns:
        Enriched CVE data with authoritative intelligence

    Raises:
        HTTPException: If validation fails or processing errors occur
    """
    try:
        # Validate request
        if not request.cve_ids:
            raise HTTPException(
                status_code=400,
                detail="cve_ids list cannot be empty"
            )

        if len(request.cve_ids) > 100:
            raise HTTPException(
                status_code=400,
                detail="Maximum 100 CVEs per request"
            )

        logger.info(
            "Enrichment request received (graph-based)",
            cve_count=len(request.cve_ids),
            include_attack_paths=request.include_attack_paths,
            include_compliance=request.include_compliance
        )

        # Initialize enrichment service
        enrichment_service = EnrichmentService()

        # Perform enrichment
        result = await enrichment_service.enrich_cves(
            cve_ids=request.cve_ids,
            include_attack_paths=request.include_attack_paths,
            include_compliance=request.include_compliance
        )

        # Convert to response model
        response = EnrichmentResponse(
            enriched=result["enriched"],
            total=result["total"],
            processing_time_ms=result["processing_time_ms"]
        )

        logger.info(
            "Enrichment request completed",
            enriched_count=response.total,
            processing_time_ms=response.processing_time_ms
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Enrichment request failed",
            error=str(e),
            error_type=type(e).__name__
        )
        raise HTTPException(
            status_code=500,
            detail=f"Enrichment failed: {str(e)}"
        )


@router.get(
    "/enrich/{cve_id}",
    response_model=CVEEnrichment,
    summary="Enrich single CVE",
    description="""
    Convenience endpoint for enriching a single CVE.

    Equivalent to POST /enrich with a single CVE ID.

    **Query Parameters:**
    - `include_attack_path` (bool): Include attack path traversal (default: false)
    - `include_compliance` (bool): Include compliance mappings (default: false)

    **Example:**
    ```
    GET /v1/enrich/CVE-2024-21413?include_attack_path=true&include_compliance=false
    ```
    """,
    tags=["enrichment"],
)
async def enrich_single_cve(
    cve_id: str,
    include_attack_path: bool = Query(False, description="Include attack path traversal"),
    include_compliance: bool = Query(False, description="Include compliance mappings")
) -> CVEEnrichment:
    """
    Enrich a single CVE.

    Args:
        cve_id: CVE identifier
        include_attack_path: Include attack path analysis
        include_compliance: Include compliance mappings

    Returns:
        Enriched CVE data

    Raises:
        HTTPException: If CVE not found or processing fails
    """
    try:
        logger.info(
            "Single CVE enrichment requested",
            cve_id=cve_id,
            include_attack_path=include_attack_path,
            include_compliance=include_compliance
        )

        # Initialize enrichment service
        enrichment_service = EnrichmentService()

        # Perform enrichment
        result = await enrichment_service.enrich_cves(
            cve_ids=[cve_id],
            include_attack_paths=include_attack_path,
            include_compliance=include_compliance
        )

        if not result["enriched"]:
            raise HTTPException(
                status_code=404,
                detail=f"CVE {cve_id} not found in knowledge graph"
            )

        enriched_cve = result["enriched"][0]

        logger.info(
            "Single CVE enrichment completed",
            cve_id=cve_id,
            processing_time_ms=result["processing_time_ms"]
        )

        return enriched_cve

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Single CVE enrichment failed",
            cve_id=cve_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Enrichment failed: {str(e)}"
        )
