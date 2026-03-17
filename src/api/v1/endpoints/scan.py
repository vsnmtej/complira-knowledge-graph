"""
Scan ingestion endpoints.

POST /v1/scan/ingest - Ingest scan results
GET /v1/scan/{session_id} - Get scan session details
GET /v1/scan/{session_id}/findings - List scan findings
GET /v1/scans - List all scans for customer
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List
import structlog

from api.core.security import Customer, get_current_customer
from api.core.database import get_customer_db
from api.services.scan import ScanIngestionService
from api.models.requests.scan import ScanIngestRequest
from api.models.responses.scan import (
    ScanIngestResponse,
    ScanSessionResponse,
    ScanFindingResponse,
    VEXGenerationResponse,
    CPEMatchingResponse,
)
from api.models.responses import APIResponse, ResponseMetadata

logger = structlog.get_logger()

router = APIRouter()


@router.post("/ingest", response_model=APIResponse[ScanIngestResponse])
async def ingest_scan_endpoint(
    request: ScanIngestRequest,
    customer: Customer = Depends(get_current_customer),
):
    """
    POST /v1/scan/ingest

    Ingest scan results from SAST, DAST, SCA, or SBOM tools.

    Supported formats:
    - **SARIF** 2.1.0 (GitHub Code Scanning, Semgrep, Snyk, CodeQL, etc.)
    - **CycloneDX** 1.4/1.5 (Dependency-Check, Syft, Grype, Trivy, etc.)

    Flow:
    1. Parse scan payload using appropriate parser
    2. Create scan session
    3. Store findings and components
    4. Create graph edges (finding → CVE, component → finding)

    Returns:
    - **scan_session_id**: Unique identifier for this scan (use to query status/findings)
    - **findings_count**: Number of vulnerabilities detected
    - **components_count**: Number of SBOM components (SCA/SBOM scans only)
    - **status**: Processing status (completed, processing, failed)

    Example:
    ```bash
    curl -X POST https://api.complira.dev/v1/scan/ingest \\
      -H "X-API-Key: your_api_key" \\
      -H "Content-Type: application/json" \\
      -d '{
        "format": "sarif",
        "scan_type": "sast",
        "payload": { ... sarif json ... },
        "metadata": {
          "repository": "https://github.com/org/repo",
          "branch": "main"
        }
      }'
    ```
    """
    import time
    start_time = time.time()

    try:
        # Get service dependencies
        from api.core.cache import RedisCacheService
        from api.core.database import get_reference_db

        service = ScanIngestionService(
            db=get_reference_db(),
            cache=RedisCacheService(),
        )

        # Ingest scan
        result = await service.ingest_scan(
            customer_id=customer.id,
            scan_request=request,
        )

        # Build response (result is ScanSession Pydantic model)
        scan_response = ScanIngestResponse(
            scan_session_id=result.session_id,  # Use model attribute
            findings_count=result.findings_count,
            components_count=result.components_count,
            status=result.status,
        )

        execution_time_ms = (time.time() - start_time) * 1000

        return APIResponse(
            success=True,
            data=scan_response,
            metadata=ResponseMetadata(
                cache_hit=False,
                execution_time_ms=execution_time_ms,
            ),
        )

    except ValueError as e:
        # Validation or parsing error (400 Bad Request)
        logger.warning(
            "Scan ingestion validation error",
            customer_id=customer.id,
            error=str(e),
        )
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        # Internal error (500)
        logger.error(
            "Scan ingestion failed",
            customer_id=customer.id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error during scan ingestion"
        )


@router.get("/{session_id}", response_model=APIResponse[ScanSessionResponse])
async def get_scan_session(
    session_id: str,
    customer: Customer = Depends(get_current_customer),
):
    """
    GET /v1/scan/{session_id}

    Get scan session details.

    Args:
    - **session_id**: Scan session identifier (from /v1/scan/ingest response)

    Returns:
    - Full scan session details including status, findings count, metadata

    Example:
    ```bash
    curl https://api.complira.dev/v1/scan/scan_abc123 \\
      -H "X-API-Key: your_api_key"
    ```
    """
    try:
        from api.core.cache import RedisCacheService

        customer_db = get_customer_db(customer.id)
        service = ScanIngestionService(
            db=customer_db,
            cache=RedisCacheService(),
        )

        # Get session
        session = await service.get_session(session_id, customer.id)

        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Scan session not found: {session_id}"
            )

        # Build response
        response = ScanSessionResponse(
            session_id=session["_key"],
            tool_name=session["tool_name"],
            tool_version=session["tool_version"],
            scan_type=session.get("scan_type", "unknown"),
            scan_timestamp=session["scan_timestamp"],
            status=session["status"],
            findings_count=session["findings_count"],
            components_count=session.get("components_count", 0),
            created_at=session["created_at"],
            updated_at=session["updated_at"],
            metadata=session.get("metadata", {}),
            project_id=session.get("project_id"),
            repository_id=session.get("repository_id"),
        )

        return APIResponse(
            success=True,
            data=response,
            metadata=ResponseMetadata(cache_hit=False),
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            "Failed to get scan session",
            session_id=session_id,
            customer_id=customer.id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{session_id}/findings", response_model=APIResponse[List[ScanFindingResponse]])
async def list_scan_findings(
    session_id: str,
    customer: Customer = Depends(get_current_customer),
    limit: int = Query(100, ge=1, le=1000, description="Maximum findings to return"),
    offset: int = Query(0, ge=0, description="Number of findings to skip"),
):
    """
    GET /v1/scan/{session_id}/findings

    List findings for a scan session.

    Args:
    - **session_id**: Scan session identifier
    - **limit**: Maximum findings to return (1-1000, default 100)
    - **offset**: Number of findings to skip (for pagination)

    Returns:
    - List of findings sorted by severity (CRITICAL → HIGH → MEDIUM → LOW)

    Example:
    ```bash
    curl 'https://api.complira.dev/v1/scan/scan_abc123/findings?limit=50' \\
      -H "X-API-Key: your_api_key"
    ```
    """
    try:
        from api.core.cache import RedisCacheService

        customer_db = get_customer_db(customer.id)
        service = ScanIngestionService(
            db=customer_db,
            cache=RedisCacheService(),
        )

        # Get findings (service verifies session exists and customer owns it)
        findings = await service.list_session_findings(
            session_id=session_id,
            customer_id=customer.id,
            limit=limit,
            offset=offset,
        )

        if not findings and limit > 0:
            # Check if session exists
            session = await service.get_session(session_id, customer.id)
            if not session:
                raise HTTPException(status_code=404, detail="Scan session not found")

        # Build response
        findings_response = [
            ScanFindingResponse(
                finding_id=f["_key"],
                cve_id=f["cve_id"],
                severity=f["severity"],
                description=f["description"],
                location=f["location"],
                tool_name=f["tool_name"],
                created_at=f["created_at"],
            )
            for f in findings
        ]

        return APIResponse(
            success=True,
            data=findings_response,
            metadata=ResponseMetadata(cache_hit=False),
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            "Failed to list scan findings",
            session_id=session_id,
            customer_id=customer.id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("s", response_model=APIResponse[List[ScanSessionResponse]])
async def list_scans(
    customer: Customer = Depends(get_current_customer),
    limit: int = Query(100, ge=1, le=1000, description="Maximum scans to return"),
    offset: int = Query(0, ge=0, description="Number of scans to skip"),
    project_id: str = Query(None, description="Filter by project ID"),
    repository_id: str = Query(None, description="Filter by repository ID"),
):
    """
    GET /v1/scans

    List all scan sessions for current customer.

    Args:
    - **limit**: Maximum scans to return (1-1000, default 100)
    - **offset**: Number of scans to skip (for pagination)
    - **project_id**: Filter scans by project ID (optional)
    - **repository_id**: Filter scans by repository ID (optional)

    Returns:
    - List of scan sessions sorted by created_at DESC (newest first)

    Example:
    ```bash
    curl 'https://api.complira.dev/v1/scans?limit=20&repository_id=repo_abc123' \\
      -H "X-API-Key: your_api_key"
    ```
    """
    try:
        from api.core.cache import RedisCacheService

        customer_db = get_customer_db(customer.id)
        service = ScanIngestionService(
            db=customer_db,
            cache=RedisCacheService(),
        )

        # Get sessions (filtering will be implemented in service layer)
        sessions = await service.list_customer_sessions(
            customer_id=customer.id,
            limit=limit,
            offset=offset,
            project_id=project_id,
            repository_id=repository_id,
        )

        # Build response (sessions are ScanSession Pydantic models)
        sessions_response = [
            ScanSessionResponse(
                session_id=s.session_id,
                tool_name=s.tool_name,
                tool_version=s.tool_version,
                scan_type=s.scan_type,
                scan_timestamp=s.scan_timestamp,
                status=s.status,
                findings_count=s.findings_count,
                components_count=s.components_count,
                created_at=s.created_at,
                updated_at=s.updated_at,
                metadata=s.metadata,
                project_id=s.project_id,
                repository_id=s.repository_id,
            )
            for s in sessions
        ]

        return APIResponse(
            success=True,
            data=sessions_response,
            metadata=ResponseMetadata(cache_hit=False),
        )

    except Exception as e:
        logger.error(
            "Failed to list scans",
            customer_id=customer.id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{session_id}/vex", response_model=APIResponse[VEXGenerationResponse])
async def generate_vex_endpoint(
    session_id: str,
    customer: Customer = Depends(get_current_customer),
):
    """
    POST /v1/scan/{session_id}/vex

    Generate VEX (Vulnerability Exploitability eXchange) document for a scan session.

    VEX documents provide machine-readable assessments of vulnerability impact
    in the context of specific products/components.

    Args:
    - **session_id**: Scan session identifier (from /v1/scan/ingest response)

    Returns:
    - **vex_document**: CycloneDX VEX document (JSON format)
    - **vulnerabilities_assessed**: Number of vulnerabilities analyzed
    - **generated_at**: Timestamp of VEX generation

    Example:
    ```bash
    curl -X POST https://api.complira.dev/v1/scan/{session_id}/vex \\
      -H "X-API-Key: your_api_key"
    ```

    Caching:
    - VEX documents are cached for 24 hours (identical SBOM = cached VEX)
    """
    import time
    start_time = time.time()

    try:
        # Get service dependencies
        from api.core.cache import RedisCacheService
        from api.core.database import get_reference_db

        service = ScanIngestionService(
            db=get_reference_db(),
            cache=RedisCacheService(),
        )

        # Generate VEX
        result = await service.generate_vex(
            customer_id=customer.id,
            scan_session_id=session_id,
        )

        # Build response
        vex_response = VEXGenerationResponse(
            scan_session_id=result["scan_session_id"],
            vex_document=result["vex_document"],
            vulnerabilities_assessed=result["vulnerabilities_assessed"],
            generated_at=result["generated_at"],
        )

        execution_time_ms = (time.time() - start_time) * 1000

        return APIResponse(
            success=True,
            data=vex_response,
            metadata=ResponseMetadata(
                cache_hit=False,
                execution_time_ms=execution_time_ms,
            ),
        )

    except ValueError as e:
        # Validation error (404 Not Found or 400 Bad Request)
        logger.warning(
            "VEX generation validation error",
            customer_id=customer.id,
            session_id=session_id,
            error=str(e),
        )
        status_code = 404 if "not found" in str(e).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        # Internal error (500)
        logger.error(
            "VEX generation failed",
            customer_id=customer.id,
            session_id=session_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error during VEX generation"
        )


@router.post("/{session_id}/cpe-match", response_model=APIResponse[CPEMatchingResponse])
async def match_cpes_endpoint(
    session_id: str,
    customer: Customer = Depends(get_current_customer),
):
    """
    POST /v1/scan/{session_id}/cpe-match

    Generate CPE (Common Platform Enumeration) mappings for SBOM components.

    CPE mappings enable vulnerability matching by linking Package URLs (PURLs)
    to CPE identifiers used in CVE records.

    Args:
    - **session_id**: Scan session identifier (from /v1/scan/ingest response)

    Returns:
    - **components_processed**: Number of components analyzed
    - **cpe_mappings_created**: Number of matched_by_cpe edges created
    - **completed_at**: Timestamp of completion

    Example:
    ```bash
    curl -X POST https://api.complira.dev/v1/scan/{session_id}/cpe-match \\
      -H "X-API-Key: your_api_key"
    ```

    Note:
    - Uses Claude Sonnet 4.5 for intelligent PURL→CPE mapping
    - Only processes components without existing CPE mappings
    - May take several minutes for large SBOMs (150+ components)
    """
    import time
    start_time = time.time()

    try:
        # Get service dependencies
        from api.core.cache import RedisCacheService
        from api.core.database import get_reference_db

        service = ScanIngestionService(
            db=get_reference_db(),
            cache=RedisCacheService(),
        )

        # Match CPEs
        result = await service.match_cpes(
            customer_id=customer.id,
            scan_session_id=session_id,
        )

        # Build response
        cpe_response = CPEMatchingResponse(
            scan_session_id=result["scan_session_id"],
            components_processed=result["components_processed"],
            cpe_mappings_created=result["cpe_mappings_created"],
            completed_at=result["completed_at"],
        )

        execution_time_ms = (time.time() - start_time) * 1000

        return APIResponse(
            success=True,
            data=cpe_response,
            metadata=ResponseMetadata(
                cache_hit=False,
                execution_time_ms=execution_time_ms,
            ),
        )

    except ValueError as e:
        # Validation error (404 Not Found or 400 Bad Request)
        logger.warning(
            "CPE matching validation error",
            customer_id=customer.id,
            session_id=session_id,
            error=str(e),
        )
        status_code = 404 if "not found" in str(e).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        # Internal error (500)
        logger.error(
            "CPE matching failed",
            customer_id=customer.id,
            session_id=session_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error during CPE matching"
        )
