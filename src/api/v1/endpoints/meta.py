"""
Metadata and data quality endpoints.

GET /v1/meta/coverage - Data coverage and quality metrics
GET /v1/meta/stats - Database statistics
"""

from fastapi import APIRouter
from typing import Dict, Any
import structlog

from api.core.database import get_reference_db
from api.models.responses import APIResponse, ResponseMetadata

logger = structlog.get_logger()

router = APIRouter()


@router.get("/coverage")
async def get_data_coverage():
    """
    GET /v1/meta/coverage

    Returns data quality and coverage metrics for the knowledge graph.

    Metrics include:
    - CVE enrichment funnel (CVE → CWE → CAPEC → ATT&CK → Controls)
    - Edge collection counts
    - Vertex collection counts
    - Data source limitations

    This endpoint helps users understand realistic expectations for enrichment.
    """
    try:
        db = get_reference_db()

        # Vertex counts
        vertices = {
            "vulnerabilities": db.collection("vulnerabilities").count(),
            "weaknesses": db.collection("weaknesses").count(),
            "attack_patterns": db.collection("attack_patterns").count(),
            "attack_techniques": db.collection("attack_techniques").count(),
            "oscal_controls": db.collection("oscal_controls").count(),
            "regulatory_requirements": db.collection("regulatory_requirements").count(),
        }

        # Edge counts
        edges = {
            "has_weakness": db.collection("has_weakness").count(),
            "capec_relates_to_cwe": db.collection("capec_relates_to_cwe").count(),
            "capec_maps_to_attack": db.collection("capec_maps_to_attack").count(),
            "technique_mitigated_by_control": db.collection("technique_mitigated_by_control").count(),
            "violates_requirement": db.collection("violates_requirement").count(),
        }

        # Sample-based enrichment coverage (100 CVEs from 2024)
        sample_query = '''
        FOR v IN vulnerabilities
            FILTER STARTS_WITH(v._key, "CVE_2024_")
            LIMIT 100
            LET has_cwe = LENGTH(FOR cwe IN 1..1 OUTBOUND v has_weakness RETURN 1) > 0
            LET has_capec = LENGTH(FOR cwe IN 1..1 OUTBOUND v has_weakness FOR capec IN 1..1 INBOUND cwe capec_relates_to_cwe LIMIT 1 RETURN 1) > 0
            LET has_attack = LENGTH(FOR cwe IN 1..1 OUTBOUND v has_weakness FOR capec IN 1..1 INBOUND cwe capec_relates_to_cwe FOR tech IN 1..1 OUTBOUND capec capec_maps_to_attack LIMIT 1 RETURN 1) > 0
            RETURN {has_cwe: has_cwe, has_capec: has_capec, has_attack: has_attack}
        '''
        samples = list(db.aql.execute(sample_query))

        with_cwe = sum(1 for s in samples if s['has_cwe'])
        with_capec = sum(1 for s in samples if s['has_capec'])
        with_attack = sum(1 for s in samples if s['has_attack'])

        enrichment_funnel = {
            "sample_size": len(samples),
            "sample_year": 2024,
            "cve_to_cwe_percent": with_cwe,
            "cve_to_capec_percent": with_capec,
            "cve_to_attack_percent": with_attack,
            "estimated_coverage": {
                "cwe_weaknesses": f"~{with_cwe}% of CVEs",
                "capec_patterns": f"~{with_capec}% of CVEs",
                "attack_techniques": f"~{with_attack}% of CVEs",
                "nist_controls": f"~{with_attack}% of CVEs (estimated)",
            }
        }

        # Data source limitations
        capec_with_attack_query = '''
        LET total_capecs = LENGTH(attack_patterns)
        LET capecs_with_attack = LENGTH(
            FOR capec IN attack_patterns
                LET has_attack = LENGTH(FOR t IN 1..1 OUTBOUND capec capec_maps_to_attack RETURN 1) > 0
                FILTER has_attack
                RETURN 1
        )
        RETURN {total: total_capecs, with_attack: capecs_with_attack}
        '''
        capec_stats = list(db.aql.execute(capec_with_attack_query))[0]

        data_limitations = {
            "capec_attack_mappings": {
                "total_capecs": capec_stats['total'],
                "capecs_with_attack_mappings": capec_stats['with_attack'],
                "coverage_percent": round(capec_stats['with_attack'] / capec_stats['total'] * 100, 1),
                "source": "MITRE CAPEC XML",
                "limitation": "MITRE only provides ATT&CK mappings for ~29% of CAPEC patterns",
            },
            "control_to_regulatory": {
                "status": "not_implemented",
                "reason": "Manual mapping required - not in public data sources",
                "workaround": "Use CVE → Regulatory violates_requirement edges (5.27M edges)",
            }
        }

        return APIResponse(
            success=True,
            data={
                "vertices": vertices,
                "edges": edges,
                "enrichment_funnel": enrichment_funnel,
                "data_limitations": data_limitations,
                "total_edges": sum(edges.values()),
                "recommendations": [
                    "45% of CVEs reach ATT&CK techniques - use these for threat modeling",
                    "72% of CVEs have CAPEC attack patterns - useful for understanding attack methods",
                    "97% of CVEs have CWE weaknesses - excellent for root cause analysis",
                    "Use violates_requirement edges for direct CVE → Regulatory mapping (bypasses control layer)",
                ]
            },
            metadata=ResponseMetadata(
                cache_hit=False,
                api_version="v1"
            )
        )

    except Exception as e:
        logger.error("Failed to get coverage metrics", error=str(e))
        raise


@router.get("/stats")
async def get_database_stats():
    """
    GET /v1/meta/stats

    Returns basic database statistics.
    """
    try:
        db = get_reference_db()

        collections = {}
        for coll_name in db.collections():
            if not coll_name['name'].startswith('_'):
                collections[coll_name['name']] = db.collection(coll_name['name']).count()

        return APIResponse(
            success=True,
            data={
                "database": "complira_graph",
                "collections": collections,
                "total_documents": sum(v for k, v in collections.items() if not k.endswith('_') or '_to_' not in k),
                "total_edges": sum(v for k, v in collections.items() if '_to_' in k or k.startswith('has_') or k.startswith('capec_') or k.startswith('technique_') or k.startswith('violates_')),
            },
            metadata=ResponseMetadata(
                cache_hit=False,
                api_version="v1"
            )
        )

    except Exception as e:
        logger.error("Failed to get database stats", error=str(e))
        raise
