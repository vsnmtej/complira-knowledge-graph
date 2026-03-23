"""
Compliance violation query endpoints (authentication required).

GET /v1/compliance/violations?scan_run_id=...  - List all finding→control violations for a scan run
GET /v1/compliance/coverage?scan_run_id=...    - Per-framework coverage summary for a scan run
"""

from fastapi import APIRouter, HTTPException, Query, Depends
import structlog

from api.core.database import get_reference_db
from api.core.security import Customer, get_current_customer
from api.models.responses import APIResponse, ResponseMetadata
from api.models.responses.compliance import (
    ViolationItem,
    ViolationsResponse,
    FrameworkCoverage,
    CoverageResponse,
)

logger = structlog.get_logger()

router = APIRouter()


_VIOLATIONS_QUERY = """
LET run_exists = LENGTH(
    FOR r IN scan_runs
        FILTER r._key == @scan_run_id AND r.tenant_id == @tenant_id
        LIMIT 1
        RETURN 1
) > 0
LET items = (
    FOR e IN finding_violates_control
        FILTER e.scan_run_id == @scan_run_id AND e.tenant_id == @tenant_id
        RETURN {
            finding_id: PARSE_IDENTIFIER(e._from).key,
            cve_id: e.cve_id,
            control_id: e.control_id,
            framework: e.framework,
            confidence: e.confidence,
            evidence_path: e.evidence_path
        }
)
RETURN {run_exists: run_exists, items: items}
"""

_COVERAGE_QUERY = """
LET run_exists = LENGTH(
    FOR r IN scan_runs
        FILTER r._key == @scan_run_id AND r.tenant_id == @tenant_id
        LIMIT 1
        RETURN 1
) > 0
LET total_findings = LENGTH(
    FOR f IN scan_findings
        FILTER f.scan_run_id == @scan_run_id AND f.tenant_id == @tenant_id
        RETURN 1
)
LET findings_with_violations = LENGTH(
    FOR e IN finding_violates_control
        FILTER e.scan_run_id == @scan_run_id AND e.tenant_id == @tenant_id
        COLLECT finding = PARSE_IDENTIFIER(e._from).key
        RETURN finding
)
LET by_framework = (
    FOR e IN finding_violates_control
        FILTER e.scan_run_id == @scan_run_id AND e.tenant_id == @tenant_id
        COLLECT framework = e.framework INTO grouped
        RETURN {
            framework: framework,
            violated_control_count: LENGTH(UNIQUE(grouped[*].e.control_id)),
            control_ids: UNIQUE(grouped[*].e.control_id)
        }
)
RETURN {
    run_exists: run_exists,
    scan_run_id: @scan_run_id,
    total_findings: total_findings,
    findings_with_violations: findings_with_violations,
    by_framework: by_framework
}
"""


@router.get("/violations")
async def get_violations(
    scan_run_id: str = Query(..., description="Scan run identifier"),
    customer: Customer = Depends(get_current_customer),
):
    """
    GET /v1/compliance/violations?scan_run_id=...

    Returns all finding_violates_control edges for a scan run, scoped to the caller's tenant.
    Each item represents a scan finding that triggered a NIST 800-53 control via the
    CVE → CWE → CAPEC → ATT&CK → Control deterministic traversal chain.

    Returns 404 if the scan run does not exist or does not belong to the caller's tenant.
    """
    try:
        db = get_reference_db()

        cursor = db.aql.execute(
            _VIOLATIONS_QUERY,
            bind_vars={"scan_run_id": scan_run_id, "tenant_id": customer.id},
        )
        result = list(cursor)

        if not result or not result[0].get("run_exists"):
            raise HTTPException(status_code=404, detail=f"Scan run not found: {scan_run_id}")

        row = result[0]
        items = [ViolationItem(**r) for r in row.get("items", [])]
        return APIResponse(
            success=True,
            data=ViolationsResponse(items=items, total=len(items)),
            metadata=ResponseMetadata(api_version="v1"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("compliance.violations.error", scan_run_id=scan_run_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/coverage")
async def get_coverage(
    scan_run_id: str = Query(..., description="Scan run identifier"),
    customer: Customer = Depends(get_current_customer),
):
    """
    GET /v1/compliance/coverage?scan_run_id=...

    Returns a per-framework compliance coverage summary for a scan run.
    Includes total findings, count of findings with at least one control violation,
    and per-framework breakdown with violated control IDs.

    Returns 404 if the scan run does not exist or does not belong to the caller's tenant.
    """
    try:
        db = get_reference_db()

        cursor = db.aql.execute(
            _COVERAGE_QUERY,
            bind_vars={"scan_run_id": scan_run_id, "tenant_id": customer.id},
        )
        result = list(cursor)

        if not result or not result[0].get("run_exists"):
            raise HTTPException(status_code=404, detail=f"Scan run not found: {scan_run_id}")

        row = result[0]
        by_framework = [FrameworkCoverage(**fw) for fw in row.get("by_framework", [])]
        return APIResponse(
            success=True,
            data=CoverageResponse(
                scan_run_id=row["scan_run_id"],
                total_findings=row["total_findings"],
                findings_with_violations=row["findings_with_violations"],
                by_framework=by_framework,
            ),
            metadata=ResponseMetadata(api_version="v1"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("compliance.coverage.error", scan_run_id=scan_run_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")
