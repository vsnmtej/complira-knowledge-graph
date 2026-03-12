"""
Reference data endpoints (no authentication required, no customer data stored).

GET /v1/reference/cve/{cve_id} - Get CVE details with enrichment
GET /v1/reference/enrich - Batch enrich multiple CVEs
GET /v1/reference/cwe/{cwe_id} - Get CWE weakness details
GET /v1/reference/controls/{cve_id} - Get mapped NIST 800-53 controls
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any
import structlog

from api.core.database import get_reference_db
from api.core.cache import cache
from api.models.responses import APIResponse, ResponseMetadata
from complira_graph.utils.keys import normalize_cve_id, normalize_cwe_id

logger = structlog.get_logger()

router = APIRouter()


@router.get("/cve/{cve_id}")
@cache(ttl=21600)  # 6 hour cache for reference data
async def get_cve_details(cve_id: str):
    """
    GET /v1/reference/cve/{cve_id}

    Get CVE details with threat intelligence enrichment.

    **No authentication required** - public reference data only.

    Returns:
    - CVE details (description, CVSS score, severity)
    - EPSS exploit probability score
    - KEV catalog status (CISA Known Exploited Vulnerabilities)
    - CWE weaknesses
    - CAPEC attack patterns
    - MITRE ATT&CK techniques
    - NIST 800-53 controls
    - FDA/EU CRA regulatory requirements
    - D3FEND defensive countermeasures
    - Threat groups exploiting this CVE
    - Available exploit modules

    Example:
    ```bash
    # No API key needed!
    curl https://api.complira.dev/v1/reference/cve/CVE-2024-1234
    ```

    Use case: GitHub Action finds CVE-2024-1234 locally, queries this endpoint
    for enrichment data, generates report - scan results never leave your CI/CD.
    """
    try:
        db = get_reference_db()

        # Query CVE with full enrichment
        query = """
        LET cve = DOCUMENT("vulnerabilities", @cve_id)

        // Get EPSS score
        LET epss = FIRST(
            FOR e IN epss_history
                FILTER e.cve_id == @cve_id
                SORT e.date DESC
                LIMIT 1
                RETURN {
                    score: e.epss_score,
                    percentile: e.epss_percentile,
                    date: e.date
                }
        )

        // Check KEV status
        LET kev = FIRST(
            FOR k IN kev_entries
                FILTER k.cve_id == @cve_id
                RETURN {
                    in_kev: true,
                    known_ransomware: k.known_ransomware_use,
                    due_date: k.due_date,
                    notes: k.notes
                }
        )

        // Get CWE weaknesses
        LET cwes = (
            FOR v, e, p IN 1..1 OUTBOUND cve has_weakness
                RETURN {
                    cwe_id: v.cwe_id,
                    name: v.name,
                    description: v.description
                }
        )

        // Get CAPEC attack patterns
        LET capecs = (
            FOR v1, e1, p1 IN 1..1 OUTBOUND cve has_weakness
                FOR v, e, p IN 1..1 INBOUND v1 capec_relates_to_cwe
                    RETURN DISTINCT {
                        capec_id: v.capec_id,
                        name: v.name,
                        description: v.description
                    }
        )

        // Get ATT&CK techniques
        LET attack_techniques = (
            FOR v1, e1, p1 IN 1..1 OUTBOUND cve has_weakness
                FOR v2, e2, p2 IN 1..1 INBOUND v1 capec_relates_to_cwe
                    FOR v, e, p IN 1..1 OUTBOUND v2 capec_maps_to_attack
                        RETURN DISTINCT {
                            technique_id: v.technique_id,
                            name: v.name,
                            description: v.description,
                            tactics: v.tactics
                        }
        )

        // Get NIST 800-53 controls
        LET nist_controls = (
            FOR v1, e1, p1 IN 1..1 OUTBOUND cve has_weakness
                FOR v2, e2, p2 IN 1..1 INBOUND v1 capec_relates_to_cwe
                    FOR v3, e3, p3 IN 1..1 OUTBOUND v2 capec_maps_to_attack
                        FOR v, e, p IN 1..1 OUTBOUND v3 technique_mitigated_by_control
                            RETURN DISTINCT {
                                control_id: v.control_id,
                                title: v.title,
                                family: v.family
                            }
        )

        // Get regulatory requirements (TODO: implement control_to_regulatory edge)
        LET regulatory_reqs = []

        // Get D3FEND defenses
        LET d3fend_defenses = (
            FOR v1, e1, p1 IN 1..1 OUTBOUND cve has_weakness
                FOR v2, e2, p2 IN 1..1 INBOUND v1 capec_relates_to_cwe
                    FOR v3, e3, p3 IN 1..1 OUTBOUND v2 capec_maps_to_attack
                        FOR v, e, p IN 1..1 INBOUND v3 d3fend_counters_technique
                            RETURN DISTINCT {
                                technique_id: v.d3fend_id,
                                name: v.name,
                                description: v.description
                            }
        )

        // Get threat groups (TODO: implement threat group traversal via VulnCheck intelligence)
        LET threat_groups = []

        // Get exploit modules
        LET exploits = (
            FOR e IN exploit_modules
                FILTER e.cve_id == @cve_id
                RETURN {
                    exploit_id: e.exploit_id,
                    name: e.name,
                    type: e.type,
                    platform: e.platform
                }
        )

        RETURN {
            cve_id: cve.cve_id,
            description: cve.description,
            cvss_score: cve.cvss_v3_score,
            cvss_vector: cve.cvss_v3_vector,
            severity: cve.severity,
            published_date: cve.published_date,
            last_modified_date: cve.last_modified_date,

            epss: epss,
            kev: kev || {in_kev: false},

            weaknesses: cwes,
            attack_patterns: capecs,
            attack_techniques: attack_techniques,
            nist_controls: nist_controls,
            regulatory_requirements: regulatory_reqs,
            d3fend_defenses: d3fend_defenses,
            threat_groups: threat_groups,
            exploits: exploits,

            references: cve.references
        }
        """

        # Normalize CVE ID to _key format (CVE-2024-1234 → CVE_2024_1234)
        normalized_cve_id = normalize_cve_id(cve_id)

        cursor = db.aql.execute(query, bind_vars={"cve_id": normalized_cve_id})
        result = list(cursor)

        if not result or result[0] is None:
            raise HTTPException(
                status_code=404,
                detail=f"CVE not found: {cve_id}"
            )

        return APIResponse(
            success=True,
            data=result[0],
            metadata=ResponseMetadata(
                cache_hit=False,  # Will be set by cache decorator
                api_version="v1"
            )
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to get CVE details",
            cve_id=cve_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/enrich")
@cache(ttl=21600)
async def batch_enrich_cves(
    cve_ids: str = Query(..., description="Comma-separated CVE IDs (e.g., CVE-2024-1234,CVE-2024-5678)")
):
    """
    GET /v1/reference/enrich?cve_ids=CVE-2024-1234,CVE-2024-5678

    Batch enrich multiple CVEs with threat intelligence.

    **No authentication required** - public reference data only.

    Returns:
    - Array of enriched CVE data (same as /v1/reference/cve/{cve_id})

    Example:
    ```bash
    # Enrich multiple CVEs found in your local scan
    curl "https://api.complira.dev/v1/reference/enrich?cve_ids=CVE-2024-1234,CVE-2024-5678"
    ```

    Use case: GitHub Action finds 50 CVEs, sends them all in one request,
    gets back enrichment data for local report generation.
    """
    try:
        # Parse CVE IDs
        cve_list = [cve.strip() for cve in cve_ids.split(",")]

        if len(cve_list) > 100:
            raise HTTPException(
                status_code=400,
                detail="Maximum 100 CVEs per request"
            )

        # Query each CVE
        results = []
        for cve_id in cve_list:
            try:
                response = await get_cve_details(cve_id)
                results.append(response.data)
            except HTTPException as e:
                if e.status_code == 404:
                    results.append({
                        "cve_id": cve_id,
                        "error": "CVE not found"
                    })
                else:
                    raise

        return APIResponse(
            success=True,
            data=results,
            metadata=ResponseMetadata(
                cache_hit=False,
                api_version="v1"
            )
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to batch enrich CVEs",
            cve_ids=cve_ids,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/cwe/{cwe_id}")
@cache(ttl=21600)
async def get_cwe_details(cwe_id: str):
    """
    GET /v1/reference/cwe/{cwe_id}

    Get CWE weakness details.

    **No authentication required** - public reference data only.

    Returns:
    - CWE details (name, description, extended_description)
    - Parent/child relationships in CWE hierarchy
    - Related CAPEC attack patterns

    Example:
    ```bash
    curl https://api.complira.dev/v1/reference/cwe/CWE-89
    ```
    """
    try:
        db = get_reference_db()

        query = """
        LET cwe = DOCUMENT("weaknesses", @cwe_id)

        // Get parent CWEs
        LET parents = (
            FOR v, e, p IN 1..1 INBOUND cwe child_of
                RETURN {
                    cwe_id: v.cwe_id,
                    name: v.name
                }
        )

        // Get child CWEs
        LET children = (
            FOR v, e, p IN 1..1 OUTBOUND cwe child_of
                RETURN {
                    cwe_id: v.cwe_id,
                    name: v.name
                }
        )

        // Get CAPEC attack patterns
        LET capecs = (
            FOR v, e, p IN 1..1 INBOUND cwe capec_relates_to_cwe
                RETURN {
                    capec_id: v.capec_id,
                    name: v.name,
                    description: v.description
                }
        )

        RETURN {
            cwe_id: cwe.cwe_id,
            name: cwe.name,
            description: cwe.description,
            extended_description: cwe.extended_description,
            parents: parents,
            children: children,
            attack_patterns: capecs
        }
        """

        # Normalize CWE ID to _key format (CWE-79 → CWE_79)
        normalized_cwe_id = normalize_cwe_id(cwe_id)

        cursor = db.aql.execute(query, bind_vars={"cwe_id": normalized_cwe_id})
        result = list(cursor)

        if not result or result[0] is None:
            raise HTTPException(
                status_code=404,
                detail=f"CWE not found: {cwe_id}"
            )

        return APIResponse(
            success=True,
            data=result[0],
            metadata=ResponseMetadata(cache_hit=False, api_version="v1")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get CWE details", cwe_id=cwe_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/controls/{cve_id}")
@cache(ttl=21600)
async def get_mapped_controls(cve_id: str):
    """
    GET /v1/reference/controls/{cve_id}

    Get NIST 800-53 controls and regulatory requirements mapped to a CVE.

    **No authentication required** - public reference data only.

    Returns:
    - NIST 800-53 controls (via CVE → CWE → CAPEC → ATT&CK → Control path)
    - FDA 524B requirements
    - EU Cyber Resilience Act requirements
    - IEC 62304 requirements

    Example:
    ```bash
    curl https://api.complira.dev/v1/reference/controls/CVE-2024-1234
    ```

    Use case: Generate compliance report showing which controls address
    vulnerabilities found in your local scan.
    """
    try:
        db = get_reference_db()

        query = """
        LET cve = DOCUMENT("vulnerabilities", @cve_id)

        // Traverse: CVE → CWE → CAPEC → ATT&CK → Controls
        LET controls = (
            FOR v1, e1, p1 IN 1..1 OUTBOUND cve has_weakness
                FOR v2, e2, p2 IN 1..1 INBOUND v1 capec_relates_to_cwe
                    FOR v3, e3, p3 IN 1..1 OUTBOUND v2 capec_maps_to_attack
                        FOR v4, e4, p4 IN 1..1 OUTBOUND v3 technique_mitigated_by_control
                            RETURN DISTINCT {
                                control_id: v4.control_id,
                                title: v4.title,
                                family: v4.family,
                                description: v4.description
                            }
        )

        // Get regulatory requirements (TODO: implement control_to_regulatory edge)
        LET regulatory = []

        RETURN {
            cve_id: @cve_id,
            nist_controls: controls,
            regulatory_requirements: regulatory
        }
        """

        # Normalize CVE ID to _key format
        normalized_cve_id = normalize_cve_id(cve_id)

        cursor = db.aql.execute(query, bind_vars={"cve_id": normalized_cve_id})
        result = list(cursor)

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"CVE not found: {cve_id}"
            )

        return APIResponse(
            success=True,
            data=result[0],
            metadata=ResponseMetadata(cache_hit=False, api_version="v1")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get controls", cve_id=cve_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")
