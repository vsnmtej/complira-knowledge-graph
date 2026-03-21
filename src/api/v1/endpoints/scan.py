"""
Scan ingestion endpoints (v2.2).

POST /v1/scan/ingest - Ingest scan results via EvidenceIngestionService
GET  /v1/scan/{run_id} - Get scan run details from scan_runs collection
GET  /v1/scans - List scan runs for current tenant
GET  /v1/scan/{run_id}/findings - List findings for a scan run
"""

import json
import time
from typing import List, Optional

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from api.core.security import Customer, get_current_customer
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


# ---------------------------------------------------------------------------
# Tool name derivation
# ---------------------------------------------------------------------------

_FORMAT_SCAN_TYPE_TO_TOOL = {
    ("json", "sast"): "semgrep",
    ("json", "iac"): "checkov",
    ("json", "sca"): "grype",
    ("json", "dast"): "zap",
    ("json", "container"): "grype",
    ("sarif", "sast"): "sarif",
    ("sarif", "dast"): "sarif",
    ("sarif", "sca"): "sarif",
    ("sarif", "iac"): "sarif",
    ("sarif", "container"): "sarif",
}


def _derive_tool_name(request: ScanIngestRequest) -> str:
    """
    Derive ADAPTER_REGISTRY tool key from the ingest request.

    Priority:
      1. request.metadata["tool_name"] — explicit caller override
      2. (format, scan_type) lookup table
      3. request.format — fallback (e.g. "sarif")
    """
    if request.metadata.get("tool_name"):
        return request.metadata["tool_name"]
    key = (request.format, request.scan_type)
    return _FORMAT_SCAN_TYPE_TO_TOOL.get(key, request.format)


# ---------------------------------------------------------------------------
# POST /v1/scan/ingest
# ---------------------------------------------------------------------------

@router.post("/ingest", response_model=APIResponse[ScanIngestResponse])
async def ingest_scan_endpoint(
    request: ScanIngestRequest,
    background_tasks: BackgroundTasks,
    customer: Customer = Depends(get_current_customer),
):
    """
    POST /v1/scan/ingest

    Ingest scan results from SAST, DAST, SCA, IaC, or SBOM tools into the
    v2.2 scanner evidence layer.

    Supported formats:
    - **SARIF** 2.1.0 (Semgrep, CodeQL, Snyk, etc.)
    - **JSON** native tool format (Checkov, Grype, Gitleaks, etc.)
    - **CycloneDX** 1.4/1.5 (SBOM path via ingest_sbom)

    Returns:
    - **scan_run_id**: Unique identifier for this scan run
    - **findings_count**: Number of findings ingested
    - **components_count**: Number of SBOM components (SBOM scans only)
    - **status**: completed | failed
    """
    start_time = time.time()

    try:
        from api.core.database import get_reference_db
        from complira_graph.ingestion.service import EvidenceIngestionService

        ref_db = get_reference_db()
        svc = EvidenceIngestionService(ref_db)

        tool_name = _derive_tool_name(request)
        raw_payload = json.dumps(request.payload).encode()

        if request.format == "cyclonedx" or request.scan_type == "sbom":
            # SBOM component path
            components_raw = request.payload.get("components", [])
            result = await svc.ingest_sbom(
                tenant_id=customer.id,
                components_raw=components_raw,
                sbom_format="cyclonedx",
                project_id=request.project_id,
                repository_id=request.repository_id,
            )
        else:
            result = await svc.ingest_scan(
                tenant_id=customer.id,
                tool_name=tool_name,
                raw_payload=raw_payload,
                project_id=request.project_id,
                repository_id=request.repository_id,
            )

        # Auto-trigger post-ingestion pipeline (enrichment → compaction → control mapping)
        # Runs asynchronously after the HTTP response is returned.
        try:
            from complira_graph.ingestion.pipeline_coordinator import PipelineCoordinator

            coordinator = PipelineCoordinator(ref_db)
            background_tasks.add_task(
                coordinator.run_post_ingest_pipeline,
                scan_run_id=result.scan_run_id,
                tenant_id=customer.id,
            )
            logger.debug(
                "Scan ingest: pipeline background task queued",
                scan_run_id=result.scan_run_id,
                customer_id=customer.id,
            )
        except Exception as pipeline_exc:
            # Never fail the ingest response because of pipeline wiring failure
            logger.warning(
                "Scan ingest: failed to queue pipeline background task",
                scan_run_id=result.scan_run_id,
                customer_id=customer.id,
                error=str(pipeline_exc),
            )

        scan_response = ScanIngestResponse(
            scan_run_id=result.scan_run_id,
            findings_count=result.findings_count,
            components_count=result.components_count,
            status=result.status,
        )

        return APIResponse(
            success=True,
            data=scan_response,
            metadata=ResponseMetadata(
                cache_hit=False,
                execution_time_ms=(time.time() - start_time) * 1000,
            ),
        )

    except ValueError as e:
        logger.warning(
            "Scan ingestion validation error",
            customer_id=customer.id,
            error=str(e),
        )
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.error(
            "Scan ingestion failed",
            customer_id=customer.id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(status_code=500, detail="Internal server error during scan ingestion")


# ---------------------------------------------------------------------------
# GET /v1/scan/{run_id}
# ---------------------------------------------------------------------------

@router.get("/{run_id}", response_model=APIResponse[ScanSessionResponse])
async def get_scan_run(
    run_id: str,
    customer: Customer = Depends(get_current_customer),
):
    """
    GET /v1/scan/{run_id}

    Get scan run details from the scan_runs collection.
    """
    try:
        from api.core.database import get_reference_db

        ref_db = get_reference_db()
        doc = ref_db.collection("scan_runs").get(run_id)

        if not doc or doc.get("tenant_id") != customer.id:
            raise HTTPException(status_code=404, detail=f"Scan run not found: {run_id}")

        tools = doc.get("tools_invoked") or []
        response = ScanSessionResponse(
            session_id=doc["_key"],
            tool_name=tools[0] if tools else "unknown",
            tool_version=doc.get("tool_version", "unknown"),
            scan_type=doc.get("scan_type", "unknown"),
            scan_timestamp=doc.get("created_at", ""),
            status=doc.get("status", "unknown"),
            findings_count=doc.get("finding_counts", {}).get("total", 0),
            components_count=doc.get("components_count", 0),
            created_at=doc.get("created_at", ""),
            updated_at=doc.get("completed_at") or doc.get("created_at", ""),
            metadata=doc.get("metadata", {}),
            project_id=doc.get("project_id"),
            repository_id=doc.get("repository_id"),
        )

        return APIResponse(
            success=True,
            data=response,
            metadata=ResponseMetadata(cache_hit=False),
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Failed to get scan run", run_id=run_id, customer_id=customer.id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# GET /v1/scan/{run_id}/findings
# ---------------------------------------------------------------------------

@router.get("/{run_id}/findings", response_model=APIResponse[List[ScanFindingResponse]])
async def list_scan_findings(
    run_id: str,
    customer: Customer = Depends(get_current_customer),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """
    GET /v1/scan/{run_id}/findings

    List findings for a scan run from the scan_findings collection.
    """
    try:
        from api.core.database import get_reference_db

        ref_db = get_reference_db()

        # Verify ownership
        run_doc = ref_db.collection("scan_runs").get(run_id)
        if not run_doc or run_doc.get("tenant_id") != customer.id:
            raise HTTPException(status_code=404, detail=f"Scan run not found: {run_id}")

        cursor = ref_db.aql.execute(
            """
            FOR f IN scan_findings
                FILTER f.scan_run_id == @run_id AND f.tenant_id == @tenant_id
                SORT f.severity ASC
                LIMIT @offset, @limit
                RETURN f
            """,
            bind_vars={
                "run_id": run_id,
                "tenant_id": customer.id,
                "offset": offset,
                "limit": limit,
            },
        )
        findings = list(cursor)

        findings_response = [
            ScanFindingResponse(
                finding_id=f["_key"],
                cve_id=f.get("cve_id") or f.get("rule_id") or "N/A",
                severity=f.get("severity") or "unknown",
                description=f.get("message") or f.get("description") or "",
                location=f.get("file_path") or f.get("location") or "",
                tool_name=f.get("tool", "unknown"),
                created_at=f.get("ingested_at") or "",
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
        logger.error("Failed to list findings", run_id=run_id, customer_id=customer.id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# GET /v1/scans
# ---------------------------------------------------------------------------

@router.get("s", response_model=APIResponse[List[ScanSessionResponse]])
async def list_scans(
    customer: Customer = Depends(get_current_customer),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    project_id: Optional[str] = Query(None),
    repository_id: Optional[str] = Query(None),
):
    """
    GET /v1/scans

    List scan runs for the current tenant, newest first.
    """
    try:
        from api.core.database import get_reference_db

        ref_db = get_reference_db()

        filters = "FILTER r.tenant_id == @tenant_id"
        bind_vars: dict = {"tenant_id": customer.id, "offset": offset, "limit": limit}
        if project_id:
            filters += " AND r.project_id == @project_id"
            bind_vars["project_id"] = project_id
        if repository_id:
            filters += " AND r.repository_id == @repository_id"
            bind_vars["repository_id"] = repository_id

        cursor = ref_db.aql.execute(
            f"""
            FOR r IN scan_runs
                {filters}
                SORT r.created_at DESC
                LIMIT @offset, @limit
                RETURN r
            """,
            bind_vars=bind_vars,
        )
        runs = list(cursor)

        response = [
            ScanSessionResponse(
                session_id=r["_key"],
                tool_name=(r.get("tools_invoked") or ["unknown"])[0],
                tool_version=r.get("tool_version", "unknown"),
                scan_type=r.get("scan_type", "unknown"),
                scan_timestamp=r.get("created_at", ""),
                status=r.get("status", "unknown"),
                findings_count=r.get("finding_counts", {}).get("total", 0),
                components_count=r.get("components_count", 0),
                created_at=r.get("created_at", ""),
                updated_at=r.get("completed_at") or r.get("created_at", ""),
                metadata=r.get("metadata", {}),
                project_id=r.get("project_id"),
                repository_id=r.get("repository_id"),
            )
            for r in runs
        ]

        return APIResponse(
            success=True,
            data=response,
            metadata=ResponseMetadata(cache_hit=False),
        )

    except Exception as e:
        logger.error("Failed to list scans", customer_id=customer.id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# POST /v1/scan/{run_id}/vex  (not yet implemented in v2.2)
# POST /v1/scan/{run_id}/cpe-match  (not yet implemented in v2.2)
# ---------------------------------------------------------------------------

@router.post("/{run_id}/vex", response_model=APIResponse[VEXGenerationResponse])
async def generate_vex_endpoint(
    run_id: str,
    customer: Customer = Depends(get_current_customer),
):
    """
    POST /v1/scan/{run_id}/vex

    VEX generation is not yet available in the v2.2 evidence pipeline.
    """
    raise HTTPException(status_code=501, detail="VEX generation not yet implemented in v2.2")


@router.post("/{run_id}/cpe-match", response_model=APIResponse[CPEMatchingResponse])
async def match_cpes_endpoint(
    run_id: str,
    customer: Customer = Depends(get_current_customer),
):
    """
    POST /v1/scan/{run_id}/cpe-match

    CPE matching is not yet available in the v2.2 evidence pipeline.
    """
    raise HTTPException(status_code=501, detail="CPE matching not yet implemented in v2.2")
