"""
POST /v1/enrich - CVE enrichment endpoint (Phase 3A-B).

Merges Phase 2 (NVD/GHSA) + Phase 3A (VulnCheck) + Phase 3A-B (regulatory triggers) data
into a unified enrichment response.

Performance Target: < 500ms per request
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from arango.database import StandardDatabase
import structlog

from complira_graph.db import get_db

logger = structlog.get_logger()

router = APIRouter()


class EnrichRequest(BaseModel):
    """Request schema for POST /v1/enrich."""
    cve_id: str = Field(..., description="CVE ID to enrich (e.g., CVE-2021-44228)", example="CVE-2021-44228")


class EnrichResponse(BaseModel):
    """Response schema for POST /v1/enrich."""
    cve_id: str = Field(..., description="CVE ID")
    nvd_data: Optional[Dict[str, Any]] = Field(None, description="Phase 2: NVD/GHSA vulnerability data")
    exploit_intelligence: Optional[Dict[str, Any]] = Field(None, description="Phase 3A: VulnCheck exploit intelligence")
    regulatory_triggers: List[Dict[str, Any]] = Field([], description="Phase 3A-B: Triggered regulatory requirements")


@router.post("/enrich/regulatory", response_model=EnrichResponse, summary="Enrich CVE with multi-phase data including regulatory triggers")
async def enrich_cve(request: EnrichRequest, db: StandardDatabase = Depends(get_db)) -> EnrichResponse:
    """
    Enrich CVE with Phase 2 (NVD) + Phase 3A (VulnCheck) + Phase 3A-B (regulatory triggers).

    **Request:**
    ```json
    {
      "cve_id": "CVE-2021-44228"
    }
    ```

    **Response:**
    ```json
    {
      "cve_id": "CVE-2021-44228",
      "nvd_data": {
        "published": "2021-12-10T10:15:00.000Z",
        "cvss_v31": {"baseScore": 10.0, ...},
        "description": "Apache Log4j2 RCE...",
        "references": [...]
      },
      "exploit_intelligence": {
        "in_kev": true,
        "kev_date_added": "2021-12-10",
        "exploit_maturity": "weaponized",
        "ransomware_families": [...],
        "exploit_chains": [...],
        "botnet_campaigns": []
      },
      "regulatory_triggers": [
        {
          "framework": "FDA 524B",
          "requirement_id": "KEV_RESPONSE",
          "requirement_title": "Known Exploited Vulnerability Response",
          "urgency": "24h",
          "trigger_rule": "kev_entry",
          "confidence": 1.0,
          "evidence": {...},
          "trigger_timestamp": "2026-03-05T12:00:00Z"
        }
      ]
    }
    ```

    **Performance:** < 500ms target

    **Error Responses:**
    - 404: CVE not found in database
    - 500: Internal server error
    """
    cve_id = request.cve_id

    logger.info("Enriching CVE", cve_id=cve_id)

    try:
        # Query 1: Get NVD data (Phase 2)
        nvd_query = """
        FOR vuln IN vulnerabilities
            FILTER vuln.cve_id == @cve_id
            RETURN {
                published: vuln.published,
                last_modified: vuln.last_modified,
                cvss_v31: vuln.cvss_v31,
                cvss_v3: vuln.cvss_v3,
                cvss_v2: vuln.cvss_v2,
                description: vuln.description,
                references: vuln.references,
                cpe_configs: vuln.cpe_configs
            }
        """

        nvd_cursor = db.aql.execute(nvd_query, bind_vars={"cve_id": cve_id})
        nvd_results = list(nvd_cursor)

        if not nvd_results:
            logger.warning("CVE not found", cve_id=cve_id)
            raise HTTPException(
                status_code=404,
                detail=f"{cve_id} not found in database"
            )

        nvd_data = nvd_results[0]

        # Query 2: Get VulnCheck exploit intelligence (Phase 3A)
        exploit_query = """
        LET vuln_key = CONCAT('vulnerabilities/', @cve_id)

        // KEV status
        LET in_kev = LENGTH(
            FOR kev IN vulncheck_kev_entries
                FILTER kev.cve_id == @cve_id
                RETURN kev
        ) > 0

        LET kev_entry = FIRST(
            FOR kev IN vulncheck_kev_entries
                FILTER kev.cve_id == @cve_id
                RETURN kev
        )

        // Exploit intelligence
        LET exploit_intel = FIRST(
            FOR intel IN exploit_intelligence
                FILTER intel.cve_id == @cve_id
                RETURN intel
        )

        // Ransomware families
        LET ransomware_families = (
            FOR edge IN exploited_by_ransomware
                FILTER edge._from == vuln_key
                LIMIT 100
                LET ransomware = DOCUMENT(edge._to)
                RETURN {
                    name: ransomware.name,
                    first_seen: ransomware.first_seen,
                    description: ransomware.description
                }
        )

        // Exploit chains
        LET exploit_chains = (
            FOR edge IN chain_includes_vuln
                FILTER edge._to == vuln_key
                LIMIT 100
                LET chain = DOCUMENT(edge._from)
                RETURN {
                    name: chain.name,
                    position: edge.position,
                    description: chain.description
                }
        )

        // Botnet campaigns
        LET botnets = (
            FOR edge IN exploited_by_botnet
                FILTER edge._from == vuln_key
                LIMIT 100
                LET botnet = DOCUMENT(edge._to)
                RETURN {
                    name: botnet.name,
                    first_seen: botnet.first_seen,
                    description: botnet.description
                }
        )

        RETURN {
            in_kev: in_kev,
            kev_date_added: kev_entry ? kev_entry.date_added : null,
            exploit_maturity: exploit_intel ? exploit_intel.exploit_maturity : null,
            ransomware_families: ransomware_families,
            exploit_chains: exploit_chains,
            botnet_campaigns: botnets
        }
        """

        exploit_cursor = db.aql.execute(exploit_query, bind_vars={"cve_id": cve_id})
        exploit_data = list(exploit_cursor)[0]

        # Query 3: Get regulatory triggers (Phase 3A-B)
        triggers_query = """
        LET vuln_key = CONCAT('vulnerabilities/', @cve_id)

        FOR edge IN vuln_triggers_requirement
            FILTER edge._from == vuln_key
            LET requirement = DOCUMENT(edge._to)
            RETURN {
                framework: requirement.framework,
                requirement_id: requirement.requirement_id,
                requirement_title: requirement.title,
                urgency: edge.urgency,
                trigger_rule: edge.trigger_rule,
                confidence: edge.confidence,
                evidence: edge.evidence,
                trigger_timestamp: edge.trigger_timestamp
            }
        """

        triggers_cursor = db.aql.execute(triggers_query, bind_vars={"cve_id": cve_id})
        regulatory_triggers = list(triggers_cursor)

        logger.info(
            "CVE enriched successfully",
            cve_id=cve_id,
            triggers_count=len(regulatory_triggers)
        )

        return EnrichResponse(
            cve_id=cve_id,
            nvd_data=nvd_data,
            exploit_intelligence=exploit_data,
            regulatory_triggers=regulatory_triggers
        )

    except HTTPException:
        # Re-raise HTTP exceptions (e.g., 404)
        raise

    except Exception as e:
        logger.error(
            "Failed to enrich CVE",
            cve_id=cve_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to enrich {cve_id}: {str(e)}"
        )
