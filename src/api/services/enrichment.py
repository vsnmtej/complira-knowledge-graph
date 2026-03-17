"""
Enrichment service.

Handles vulnerability enrichment logic:
- Enrich scan findings with CVE details, EPSS, KEV, threat intelligence
- No caching (MVP decision D1)
- On-demand computation
"""

from typing import List, Dict, Any, Optional
from collections import defaultdict
import structlog

from api.services.base import BaseGraphService
from api.repositories.scan import ScanFindingRepository
from api.repositories.enrichment import EnrichmentRepository
from complira_graph.models import (
    ScanFinding,
    EnrichedFinding,
    EnrichResponse,
    EnrichmentMetadata,
    ThreatIntelligence,
    Vulnerability,
    Weakness,
    AttackPattern,
    ATTACKTechnique,
)

logger = structlog.get_logger()


class EnrichmentService(BaseGraphService):
    """
    Service for enriching scan findings with vulnerability intelligence.

    MVP Design (D1: No caching):
    - Compute enrichment on-demand for every request
    - No caching layer (future enhancement)
    - Batch queries for performance optimization
    """

    async def enrich_scan_session(
        self,
        customer_id: str,
        scan_session_id: str,
        include_threat_intel: bool = True,
        include_kev: bool = True,
        include_epss: bool = True,
    ) -> EnrichResponse:
        """
        Enrich all findings in a scan session.

        Flow:
        1. Get scan findings from customer DB
        2. Group findings by CVE ID (for batch queries)
        3. Batch query reference DB (CVE, EPSS, KEV, threat chain)
        4. Build enriched findings
        5. Return enriched response

        Args:
            customer_id: Customer identifier
            scan_session_id: Scan session _key
            include_threat_intel: Include CWE → CAPEC → ATT&CK chain
            include_kev: Include CISA KEV status
            include_epss: Include EPSS scores

        Returns:
            EnrichResponse with enriched findings and metadata
        """
        self.logger.info(
            "Starting scan enrichment",
            customer_id=customer_id,
            scan_session_id=scan_session_id,
        )

        # Step 1: Get scan findings from customer DB
        from api.core.database import get_customer_db
        customer_db = get_customer_db(customer_id)
        finding_repo = ScanFindingRepository(customer_db)

        findings = finding_repo.list_session_findings(
            customer_id=customer_id,
            scan_session_id=scan_session_id,
            limit=10000,  # MVP: No pagination
        )

        if not findings:
            self.logger.info("No findings to enrich", scan_session_id=scan_session_id)
            return EnrichResponse(
                scan_session_id=scan_session_id,
                total_findings=0,
                enriched_findings=[],
                enrichment_metadata=EnrichmentMetadata(),
            )

        self.logger.debug(
            "Fetched findings from customer DB",
            findings_count=len(findings)
        )

        # Step 2: Group findings by CVE ID and CWE ID
        cve_findings = defaultdict(list)  # CVE ID → list of findings
        non_cve_findings = []  # Findings without CVE ID
        all_cwe_ids = set()

        for finding in findings:
            if finding.cve_id:
                cve_findings[finding.cve_id].append(finding)
                # Extract CWE IDs from raw_data if available
                if 'cwe_ids' in finding.raw_data:
                    all_cwe_ids.update(finding.raw_data['cwe_ids'])
            else:
                non_cve_findings.append(finding)
                # Extract CWE IDs from raw_data for non-CVE findings
                if 'cwe_ids' in finding.raw_data:
                    all_cwe_ids.update(finding.raw_data['cwe_ids'])

        unique_cve_ids = list(cve_findings.keys())

        self.logger.debug(
            "Grouped findings",
            unique_cve_count=len(unique_cve_ids),
            non_cve_count=len(non_cve_findings),
            unique_cwe_count=len(all_cwe_ids)
        )

        # Step 3: Batch query reference DB for CVE enrichment
        from api.core.database import get_reference_db
        reference_db = get_reference_db()
        enrich_repo = EnrichmentRepository(reference_db)

        # Batch get CVE details
        cve_details_map = enrich_repo.batch_get_cve_details(unique_cve_ids)

        # Collect CWE IDs from CVE details
        for vuln in cve_details_map.values():
            all_cwe_ids.update(vuln.cwe_ids)

        # Step 4: Batch query EPSS scores (if requested)
        epss_map = {}
        if include_epss and unique_cve_ids:
            epss_map = enrich_repo.batch_get_latest_epss(unique_cve_ids)

        # Step 5: Batch query KEV status (if requested)
        kev_map = {}
        if include_kev and unique_cve_ids:
            kev_map = enrich_repo.batch_check_kev_status(unique_cve_ids)

        # Step 6: Batch query threat intelligence (if requested)
        threat_intel_map = {}
        if include_threat_intel and all_cwe_ids:
            raw_threat_map = enrich_repo.batch_get_threat_intelligence_chain(
                list(all_cwe_ids)
            )

            # Convert to ThreatIntelligence models
            for cwe_id, threat_data in raw_threat_map.items():
                threat_intel_map[cwe_id] = ThreatIntelligence(
                    cwe=Weakness(**threat_data['cwe']),
                    capecs=[
                        AttackPattern(**capec_dict)
                        for capec_dict in threat_data['capecs']
                    ],
                    attack_techniques=[
                        ATTACKTechnique(**attack_dict)
                        for attack_dict in threat_data['attacks']
                    ]
                )

        # Step 7: Build enriched findings
        enriched_findings = []

        for finding in findings:
            if finding.cve_id:
                # Enrich CVE finding
                cve_details = cve_details_map.get(finding.cve_id)
                epss_score = epss_map.get(finding.cve_id)
                kev_entry = kev_map.get(finding.cve_id)

                # Get threat intel for first CWE
                threat_intel = None
                if cve_details and cve_details.cwe_ids:
                    first_cwe = cve_details.cwe_ids[0]
                    threat_intel = threat_intel_map.get(first_cwe)

                enriched_findings.append(
                    EnrichedFinding(
                        finding=finding,
                        cve_details=cve_details,
                        epss_score=epss_score,
                        kev_entry=kev_entry,
                        threat_intelligence=threat_intel,
                    )
                )
            else:
                # Enrich non-CVE finding (via CWE only)
                threat_intel = None
                if 'cwe_ids' in finding.raw_data and finding.raw_data['cwe_ids']:
                    first_cwe = finding.raw_data['cwe_ids'][0]
                    threat_intel = threat_intel_map.get(first_cwe)

                enriched_findings.append(
                    EnrichedFinding(
                        finding=finding,
                        cve_details=None,
                        epss_score=None,
                        kev_entry=None,
                        threat_intelligence=threat_intel,
                    )
                )

        # Step 8: Build enrichment metadata
        cve_finding_count = len(unique_cve_ids)
        cve_enriched_count = len(cve_details_map)
        epss_count = len(epss_map)
        kev_count = len(kev_map)
        threat_intel_count = len(threat_intel_map)

        metadata = EnrichmentMetadata(
            cve_enrichment_coverage=(
                (cve_enriched_count / cve_finding_count * 100)
                if cve_finding_count > 0 else 0.0
            ),
            epss_coverage=(
                (epss_count / cve_finding_count * 100)
                if cve_finding_count > 0 else 0.0
            ),
            kev_coverage=(
                (kev_count / cve_finding_count * 100)
                if cve_finding_count > 0 else 0.0
            ),
            threat_intel_coverage=(
                (threat_intel_count / len(all_cwe_ids) * 100)
                if len(all_cwe_ids) > 0 else 0.0
            ),
        )

        self.logger.info(
            "Scan enrichment complete",
            total_findings=len(findings),
            cve_enriched=cve_enriched_count,
            epss_found=epss_count,
            kev_found=kev_count,
            threat_intel_found=threat_intel_count,
        )

        return EnrichResponse(
            scan_session_id=scan_session_id,
            total_findings=len(findings),
            enriched_findings=enriched_findings,
            enrichment_metadata=metadata,
        )
