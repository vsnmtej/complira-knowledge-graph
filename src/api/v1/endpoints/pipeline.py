"""
Pipeline trigger endpoint.

POST /v1/scans/{scan_run_id}/enrich  — manual trigger for the three-stage
post-ingestion intelligence pipeline. Returns 202 Accepted immediately;
pipeline runs as a FastAPI BackgroundTask.

Retriable statuses (allow re-triggering):
  completed, enriched, compacted, pipeline_failed, enrichment_pending
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from api.core.security import Customer, get_current_customer

logger = structlog.get_logger()

router = APIRouter()

_RETRIABLE_STATUSES = frozenset(
    {
        "completed",
        "enriched",
        "compacted",
        "pipeline_failed",
        "enrichment_pending",
    }
)


@router.post("/scans/{scan_run_id}/enrich", status_code=202)
async def enrich_scan_endpoint(
    scan_run_id: str,
    background_tasks: BackgroundTasks,
    customer: Customer = Depends(get_current_customer),
) -> dict:
    """
    POST /v1/scans/{scan_run_id}/enrich

    Manually trigger the three-stage post-ingestion pipeline for a scan run.

    - Validates scan_run ownership (tenant_id check).
    - Validates that current status permits re-enrichment.
    - Queues PipelineCoordinator.run_post_ingest_pipeline as a BackgroundTask.
    - Returns 202 immediately; pipeline executes asynchronously.

    Retriable statuses: completed, enriched, compacted, pipeline_failed, enrichment_pending
    """
    from api.core.database import get_reference_db
    from complira_graph.ingestion.pipeline_coordinator import PipelineCoordinator

    try:
        ref_db = get_reference_db()
    except Exception as exc:
        logger.error(
            "enrich_scan_endpoint.db_unavailable",
            scan_run_id=scan_run_id,
            customer_id=customer.id,
            error=str(exc),
        )
        raise HTTPException(
            status_code=503,
            detail="Reference database unavailable",
        )

    # Ownership + status check
    try:
        run_doc = ref_db.collection("scan_runs").get(scan_run_id)
    except Exception as exc:
        logger.error(
            "enrich_scan_endpoint.fetch_run_failed",
            scan_run_id=scan_run_id,
            customer_id=customer.id,
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail="Internal server error")

    if not run_doc or run_doc.get("tenant_id") != customer.id:
        raise HTTPException(
            status_code=404,
            detail=f"Scan run not found: {scan_run_id}",
        )

    current_status = run_doc.get("status", "unknown")
    if current_status not in _RETRIABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Scan run {scan_run_id} has status '{current_status}' which does not "
                f"allow re-enrichment. Retriable statuses: {sorted(_RETRIABLE_STATUSES)}"
            ),
        )

    coordinator = PipelineCoordinator(ref_db)
    background_tasks.add_task(
        coordinator.run_post_ingest_pipeline,
        scan_run_id=scan_run_id,
        tenant_id=customer.id,
    )

    logger.info(
        "enrich_scan_endpoint.queued",
        scan_run_id=scan_run_id,
        customer_id=customer.id,
        current_status=current_status,
    )

    return {
        "scan_run_id": scan_run_id,
        "message": "enrichment queued",
        "status": 202,
    }
