"""
VEX (Vulnerability Exploitability eXchange) endpoints.

POST /v1/vex - Create VEX document
GET /v1/vex - List all VEX documents
GET /v1/vex/{vex_id} - Get specific VEX document (enriched)
PUT /v1/vex/{vex_id} - Update entire VEX document
PATCH /v1/vex/{vex_id}/vulnerability/{cve_id} - Update single vulnerability assessment
DELETE /v1/vex/{vex_id} - Delete VEX document
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List
import structlog

from api.core.security import Customer, get_current_customer
from api.core.database import get_customer_db, get_reference_db
from api.core.cache import RedisCacheService
from api.services.vex import VEXService
from api.models.requests.vex import (
    VEXDocumentRequest,
    VEXUpdateRequest,
    VEXVulnerabilityPatchRequest,
)
from api.models.responses.vex import (
    VEXCreateResponse,
    VEXDocumentResponse,
    VEXUpdateResponse,
    VEXListResponse,
)
from api.models.responses import APIResponse, ResponseMetadata

logger = structlog.get_logger()

router = APIRouter()


@router.post("", response_model=APIResponse[VEXCreateResponse])
async def create_vex_endpoint(
    request: VEXDocumentRequest,
    customer: Customer = Depends(get_current_customer),
):
    """
    POST /v1/vex

    Create new VEX document from client application.

    Your client app generates VEX documents with reachability analysis,
    and this API stores them and enriches them with knowledge graph data.

    **Enrichment includes:**
    - KEV status (CISA catalog - actively exploited vulnerabilities)
    - EPSS scores (exploit prediction)
    - CVSS scores (severity)
    - CWE weaknesses
    - MITRE ATT&CK techniques
    - NIST 800-53 controls
    - D3FEND defensive techniques
    - Regulatory violations (EU CRA, FDA 524B, etc.)

    **Args:**
    - **vulnerabilities**: List of vulnerability assessments from your analysis
    - **metadata**: Optional component information, timestamps, etc.

    **Returns:**
    - **vex_id**: Unique identifier for this VEX document
    - **vulnerabilities_count**: Total vulnerabilities assessed
    - **enriched_count**: Number successfully enriched with knowledge graph
    - **created_at**: Timestamp (ISO 8601)

    **Example:**
    ```bash
    curl -X POST https://api.complira.dev/v1/vex \\
      -H "X-API-Key: your_api_key" \\
      -H "Content-Type: application/json" \\
      -d '{
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "vulnerabilities": [
          {
            "id": "CVE-2021-44228",
            "analysis": {
              "state": "not_affected",
              "justification": "code_not_reachable",
              "detail": "Log4j included but logging disabled"
            }
          }
        ]
      }'
    ```
    """
    import time
    start_time = time.time()

    try:
        service = VEXService(
            customer_db=get_customer_db(customer.id),
            reference_db=get_reference_db(),
            cache=RedisCacheService(),
        )

        result = await service.create_vex(
            vex_request=request,
            customer_id=customer.id,
        )

        execution_time_ms = (time.time() - start_time) * 1000

        return APIResponse(
            success=True,
            data=result,
            metadata=ResponseMetadata(
                cache_hit=False,
                execution_time_ms=execution_time_ms,
            ),
        )

    except ValueError as e:
        logger.warning(
            "VEX creation validation error",
            customer_id=customer.id,
            error=str(e),
        )
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.error(
            "VEX creation failed",
            customer_id=customer.id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error during VEX creation"
        )


@router.get("", response_model=APIResponse[List[VEXListResponse]])
async def list_vex_endpoint(
    customer: Customer = Depends(get_current_customer),
    limit: int = Query(100, ge=1, le=1000, description="Maximum VEX documents to return"),
    offset: int = Query(0, ge=0, description="Number of VEX documents to skip"),
):
    """
    GET /v1/vex

    List all VEX documents for current customer.

    **Args:**
    - **limit**: Maximum documents to return (1-1000, default 100)
    - **offset**: Number of documents to skip (for pagination)

    **Returns:**
    - List of VEX documents sorted by created_at DESC (newest first)

    **Example:**
    ```bash
    curl 'https://api.complira.dev/v1/vex?limit=20' \\
      -H "X-API-Key: your_api_key"
    ```
    """
    import time
    start_time = time.time()

    try:
        service = VEXService(
            customer_db=get_customer_db(customer.id),
            reference_db=get_reference_db(),
            cache=RedisCacheService(),
        )

        result = await service.list_vex_documents(
            customer_id=customer.id,
            limit=limit,
            offset=offset,
        )

        execution_time_ms = (time.time() - start_time) * 1000

        return APIResponse(
            success=True,
            data=result,
            metadata=ResponseMetadata(
                cache_hit=False,
                execution_time_ms=execution_time_ms,
            ),
        )

    except Exception as e:
        logger.error(
            "VEX list failed",
            customer_id=customer.id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{vex_id}", response_model=APIResponse[VEXDocumentResponse])
async def get_vex_endpoint(
    vex_id: str,
    customer: Customer = Depends(get_current_customer),
):
    """
    GET /v1/vex/{vex_id}

    Get VEX document with full knowledge graph enrichment.

    Returns your client-submitted VEX assessments enriched with:
    - KEV status, EPSS scores, CVSS scores
    - CWE weaknesses, ATT&CK techniques
    - NIST controls, D3FEND defenses
    - Regulatory violations

    **Args:**
    - **vex_id**: VEX document identifier (from POST /v1/vex response)

    **Returns:**
    - Complete VEX document with enriched vulnerability data

    **Example:**
    ```bash
    curl https://api.complira.dev/v1/vex/vex_abc123 \\
      -H "X-API-Key: your_api_key"
    ```
    """
    import time
    start_time = time.time()

    try:
        service = VEXService(
            customer_db=get_customer_db(customer.id),
            reference_db=get_reference_db(),
            cache=RedisCacheService(),
        )

        result = await service.get_vex(
            vex_id=vex_id,
            customer_id=customer.id,
        )

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"VEX document not found: {vex_id}"
            )

        execution_time_ms = (time.time() - start_time) * 1000

        return APIResponse(
            success=True,
            data=result,
            metadata=ResponseMetadata(
                cache_hit=False,
                execution_time_ms=execution_time_ms,
            ),
        )

    except HTTPException:
        raise

    except ValueError as e:
        status_code = 404 if "not found" in str(e).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        logger.error(
            "VEX retrieval failed",
            vex_id=vex_id,
            customer_id=customer.id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{vex_id}", response_model=APIResponse[VEXUpdateResponse])
async def update_vex_endpoint(
    vex_id: str,
    request: VEXUpdateRequest,
    customer: Customer = Depends(get_current_customer),
):
    """
    PUT /v1/vex/{vex_id}

    Update entire VEX document (replaces all vulnerabilities).

    Use this when you want to replace the full VEX document with updated
    assessments. All vulnerabilities will be re-enriched with latest
    knowledge graph data.

    **Args:**
    - **vex_id**: VEX document identifier
    - **vulnerabilities**: Updated list of vulnerability assessments
    - **metadata**: Updated metadata

    **Returns:**
    - Update confirmation with timestamp

    **Example:**
    ```bash
    curl -X PUT https://api.complira.dev/v1/vex/vex_abc123 \\
      -H "X-API-Key: your_api_key" \\
      -H "Content-Type: application/json" \\
      -d '{
        "vulnerabilities": [...],
        "metadata": {...}
      }'
    ```
    """
    import time
    start_time = time.time()

    try:
        service = VEXService(
            customer_db=get_customer_db(customer.id),
            reference_db=get_reference_db(),
            cache=RedisCacheService(),
        )

        result = await service.update_vex(
            vex_id=vex_id,
            update_request=request,
            customer_id=customer.id,
        )

        execution_time_ms = (time.time() - start_time) * 1000

        return APIResponse(
            success=True,
            data=result,
            metadata=ResponseMetadata(
                cache_hit=False,
                execution_time_ms=execution_time_ms,
            ),
        )

    except ValueError as e:
        status_code = 404 if "not found" in str(e).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        logger.error(
            "VEX update failed",
            vex_id=vex_id,
            customer_id=customer.id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error during VEX update"
        )


@router.patch("/{vex_id}/vulnerability/{cve_id}", response_model=APIResponse[VEXUpdateResponse])
async def patch_vulnerability_endpoint(
    vex_id: str,
    cve_id: str,
    request: VEXVulnerabilityPatchRequest,
    customer: Customer = Depends(get_current_customer),
):
    """
    PATCH /v1/vex/{vex_id}/vulnerability/{cve_id}

    Update single vulnerability assessment in VEX document.

    Use this when you want to update just one CVE's assessment without
    replacing the entire VEX document. The CVE will be re-enriched with
    latest knowledge graph data.

    **Args:**
    - **vex_id**: VEX document identifier
    - **cve_id**: CVE identifier to update (e.g., CVE-2021-44228)
    - **analysis**: Updated VEX analysis for this CVE

    **Returns:**
    - Update confirmation with timestamp

    **Example:**
    ```bash
    curl -X PATCH https://api.complira.dev/v1/vex/vex_abc123/vulnerability/CVE-2021-44228 \\
      -H "X-API-Key: your_api_key" \\
      -H "Content-Type: application/json" \\
      -d '{
        "analysis": {
          "state": "resolved",
          "response": ["update"],
          "detail": "Updated to patched version 2.17.1"
        }
      }'
    ```
    """
    import time
    start_time = time.time()

    try:
        service = VEXService(
            customer_db=get_customer_db(customer.id),
            reference_db=get_reference_db(),
            cache=RedisCacheService(),
        )

        result = await service.patch_vulnerability(
            vex_id=vex_id,
            cve_id=cve_id,
            patch_request=request,
            customer_id=customer.id,
        )

        execution_time_ms = (time.time() - start_time) * 1000

        return APIResponse(
            success=True,
            data=result,
            metadata=ResponseMetadata(
                cache_hit=False,
                execution_time_ms=execution_time_ms,
            ),
        )

    except ValueError as e:
        status_code = 404 if "not found" in str(e).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        logger.error(
            "Vulnerability patch failed",
            vex_id=vex_id,
            cve_id=cve_id,
            customer_id=customer.id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error during vulnerability patch"
        )


@router.delete("/{vex_id}", response_model=APIResponse[dict])
async def delete_vex_endpoint(
    vex_id: str,
    customer: Customer = Depends(get_current_customer),
):
    """
    DELETE /v1/vex/{vex_id}

    Delete VEX document.

    **Args:**
    - **vex_id**: VEX document identifier

    **Returns:**
    - Deletion confirmation

    **Example:**
    ```bash
    curl -X DELETE https://api.complira.dev/v1/vex/vex_abc123 \\
      -H "X-API-Key: your_api_key"
    ```
    """
    import time
    start_time = time.time()

    try:
        service = VEXService(
            customer_db=get_customer_db(customer.id),
            reference_db=get_reference_db(),
            cache=RedisCacheService(),
        )

        await service.delete_vex(
            vex_id=vex_id,
            customer_id=customer.id,
        )

        execution_time_ms = (time.time() - start_time) * 1000

        return APIResponse(
            success=True,
            data={"deleted": True, "vex_id": vex_id},
            metadata=ResponseMetadata(
                cache_hit=False,
                execution_time_ms=execution_time_ms,
            ),
        )

    except ValueError as e:
        status_code = 404 if "not found" in str(e).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        logger.error(
            "VEX deletion failed",
            vex_id=vex_id,
            customer_id=customer.id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error during VEX deletion"
        )
