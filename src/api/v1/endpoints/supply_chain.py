"""
Supply chain intelligence endpoints (authentication required).

GET /v1/supply-chain/component?purl=...          - Component detail with dep graph + vuln associations
GET /v1/supply-chain/affected-projects?cve_id=... - Projects transitively using a CVE-affected component
GET /v1/supply-chain/dependency-path?from_purl=...&to_purl=... - Shortest dependency path between two components
GET /v1/supply-chain/risk-summary?project_id=... - Supply chain risk summary for a project
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List
import structlog

from api.core.database import get_reference_db
from api.core.security import Customer, get_current_customer
from api.models.responses import APIResponse, ResponseMetadata
from api.models.responses.supply_chain import (
    ComponentDetailResponse,
    AffectedProjectItem,
    AffectedProjectsResponse,
    DependencyPathResponse,
    TopComponent,
    RiskSummaryResponse,
)
from complira_graph.utils.keys import normalize_purl, normalize_cve_id

logger = structlog.get_logger()

router = APIRouter()


_COMPONENT_DETAIL_QUERY = """
LET comp = DOCUMENT("components", @comp_key)
LET tenant_projects = (
    FOR e IN project_uses_component
        FILTER e._to == comp._id AND e.tenant_id == @tenant_id
        RETURN PARSE_IDENTIFIER(e._from).key
)
LET deps = (
    FOR v IN 1..1 OUTBOUND comp depends_on RETURN v.purl
)
LET dependents = (
    FOR v IN 1..1 INBOUND comp depends_on RETURN v.purl
)
LET vuln_ids = (
    FOR v IN 1..1 OUTBOUND comp component_has_vuln RETURN v.cve_id
)
RETURN {
    purl: comp.purl,
    name: comp.name,
    version: comp.version,
    type: comp.type,
    projects: tenant_projects,
    dependencies: deps,
    dependents: dependents,
    vulnerabilities: vuln_ids
}
"""

_AFFECTED_PROJECTS_QUERY = """
LET vuln = DOCUMENT("vulnerabilities", @cve_key)
LET affected = (
    FOR comp IN 1..1 INBOUND vuln component_has_vuln
        LET projects = (
            FOR e IN project_uses_component
                FILTER e._to == comp._id AND e.tenant_id == @tenant_id
                RETURN PARSE_IDENTIFIER(e._from).key
        )
        FILTER LENGTH(projects) > 0
        FOR proj_id IN projects
            RETURN {
                project_id: proj_id,
                component_purl: comp.purl,
                cve_id: @cve_id
            }
)
RETURN affected
"""

_DEPENDENCY_PATH_QUERY = """
LET from_access = FIRST(
    FOR e IN project_uses_component
        FILTER e._to == @from_id AND e.tenant_id == @tenant_id
        LIMIT 1
        RETURN 1
)
LET to_access = FIRST(
    FOR e IN project_uses_component
        FILTER e._to == @to_id AND e.tenant_id == @tenant_id
        LIMIT 1
        RETURN 1
)
LET path_result = (
    from_access != null AND to_access != null
    ? (
        FOR path IN OUTBOUND SHORTEST_PATH @from_id TO @to_id depends_on
            RETURN path.vertices[*].purl
      )
    : []
)
RETURN path_result
"""

_RISK_SUMMARY_QUERY = """
LET project_doc = FIRST(
    FOR p IN projects
        FILTER p._key == @project_id AND p.tenant_id == @tenant_id
        RETURN p
)
LET project_components = (
    FOR e IN project_uses_component
        FILTER e._from == CONCAT("projects/", @project_id) AND e.tenant_id == @tenant_id
        RETURN DOCUMENT(e._to)
)
LET vuln_components = (
    FOR comp IN project_components
        LET vuln_count = LENGTH(
            FOR e IN 1..1 OUTBOUND comp component_has_vuln RETURN 1
        )
        FILTER vuln_count > 0
        RETURN comp
)
LET crit_count = LENGTH(
    FOR comp IN vuln_components
        FOR vuln IN 1..1 OUTBOUND comp component_has_vuln
            FILTER UPPER(vuln.severity) == "CRITICAL"
            RETURN 1
)
LET high_count = LENGTH(
    FOR comp IN vuln_components
        FOR vuln IN 1..1 OUTBOUND comp component_has_vuln
            FILTER UPPER(vuln.severity) == "HIGH"
            RETURN 1
)
LET top_depended = (
    FOR comp IN project_components
        LET dep_count = LENGTH(
            FOR e IN 1..1 INBOUND comp depends_on RETURN 1
        )
        SORT dep_count DESC
        LIMIT 5
        RETURN { purl: comp.purl, dependent_count: dep_count }
)
RETURN {
    project_exists: project_doc != null,
    project_id: @project_id,
    total_components: LENGTH(project_components),
    vulnerable_components: LENGTH(vuln_components),
    critical_count: crit_count,
    high_count: high_count,
    top_depended_on: top_depended
}
"""


@router.get("/component")
async def get_component_detail(
    purl: str = Query(..., description="Package URL (PURL) of the component"),
    customer: Customer = Depends(get_current_customer),
):
    """
    GET /v1/supply-chain/component?purl=...

    Returns component metadata plus projects using it, direct dependencies,
    direct dependents, and CVE associations. All results are tenant-scoped.

    Returns 404 if the component does not exist or the tenant has no project using it.
    """
    try:
        db = get_reference_db()
        comp_key = normalize_purl(purl)

        cursor = db.aql.execute(
            _COMPONENT_DETAIL_QUERY,
            bind_vars={"comp_key": comp_key, "tenant_id": customer.id},
        )
        result = list(cursor)

        if not result or result[0] is None or result[0].get("purl") is None:
            raise HTTPException(status_code=404, detail=f"Component not found: {purl}")

        row = result[0]
        # 404 if tenant has no project using this component
        if not row.get("projects"):
            raise HTTPException(status_code=404, detail=f"Component not found: {purl}")

        return APIResponse(
            success=True,
            data=ComponentDetailResponse(**row),
            metadata=ResponseMetadata(api_version="v1"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("supply_chain.component_detail.error", purl=purl, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/affected-projects")
async def get_affected_projects(
    cve_id: str = Query(..., description="CVE identifier (e.g. CVE-2021-44228)"),
    customer: Customer = Depends(get_current_customer),
):
    """
    GET /v1/supply-chain/affected-projects?cve_id=...

    Returns all projects (for the current tenant) that use a component
    associated with the given CVE. Returns an empty list if no components
    are affected or no tenant projects use affected components.
    """
    try:
        db = get_reference_db()
        cve_key = normalize_cve_id(cve_id)

        cursor = db.aql.execute(
            _AFFECTED_PROJECTS_QUERY,
            bind_vars={"cve_key": cve_key, "cve_id": cve_id, "tenant_id": customer.id},
        )
        result = list(cursor)
        items_raw = result[0] if result else []

        items = [AffectedProjectItem(**r) for r in items_raw]
        return APIResponse(
            success=True,
            data=AffectedProjectsResponse(items=items, total=len(items)),
            metadata=ResponseMetadata(api_version="v1"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("supply_chain.affected_projects.error", cve_id=cve_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/dependency-path")
async def get_dependency_path(
    from_purl: str = Query(..., description="Source component PURL"),
    to_purl: str = Query(..., description="Target component PURL"),
    customer: Customer = Depends(get_current_customer),
):
    """
    GET /v1/supply-chain/dependency-path?from_purl=...&to_purl=...

    Finds the shortest dependency path between two components on depends_on edges.
    Returns found=false with an empty path if no path exists or either component
    is not accessible to the tenant.
    """
    try:
        db = get_reference_db()
        from_key = normalize_purl(from_purl)
        to_key = normalize_purl(to_purl)

        cursor = db.aql.execute(
            _DEPENDENCY_PATH_QUERY,
            bind_vars={
                "from_id": f"components/{from_key}",
                "to_id": f"components/{to_key}",
                "tenant_id": customer.id,
            },
        )
        result = list(cursor)

        # path_result is a list of lists: [[purl1, purl2, ...]] or [[]] or []
        path_vertices: List[str] = []
        if result and result[0]:
            inner = result[0]
            if inner and inner[0]:
                path_vertices = inner[0]

        found = len(path_vertices) > 0
        return APIResponse(
            success=True,
            data=DependencyPathResponse(
                found=found,
                path=path_vertices,
                path_length=len(path_vertices),
            ),
            metadata=ResponseMetadata(api_version="v1"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "supply_chain.dependency_path.error",
            from_purl=from_purl,
            to_purl=to_purl,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/risk-summary")
async def get_risk_summary(
    project_id: str = Query(..., description="Project identifier"),
    customer: Customer = Depends(get_current_customer),
):
    """
    GET /v1/supply-chain/risk-summary?project_id=...

    Returns supply chain risk summary for a project: component counts,
    vulnerability severity counts, and top most-depended-on components.
    Returns 404 if the project does not belong to the tenant.
    """
    try:
        db = get_reference_db()

        cursor = db.aql.execute(
            _RISK_SUMMARY_QUERY,
            bind_vars={"project_id": project_id, "tenant_id": customer.id},
        )
        result = list(cursor)

        if not result or result[0] is None:
            raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

        row = result[0]
        if not row.get("project_exists"):
            raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

        response_data = {k: v for k, v in row.items() if k != "project_exists"}
        top_depended_on = [TopComponent(**t) for t in response_data.pop("top_depended_on", [])]

        return APIResponse(
            success=True,
            data=RiskSummaryResponse(**response_data, top_depended_on=top_depended_on),
            metadata=ResponseMetadata(api_version="v1"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("supply_chain.risk_summary.error", project_id=project_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")
