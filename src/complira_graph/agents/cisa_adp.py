"""
CISA ADP (Authorized Data Publisher) enrichment agent.

Fetches CISA's enrichment of CVE records from CVE.org API.
CISA provides SSVC scores, KEV flags, enhanced CWE mappings, and CVSS scores.

Data source: https://cveawg.mitre.org/api/cve/{CVE-ID}
Collections populated:
- vulnerabilities (updates existing records with CISA enrichment)
- Adds SSVC decision points, KEV status, enhanced CWE mappings

Note: This agent enriches existing vulnerabilities from NVD/GHSA agents.
      Run this AFTER NVD agent has populated the vulnerabilities collection.
"""

from typing import Generator
import structlog
from datetime import datetime

from .base import BaseIngestionAgent
from ..utils.http_client import create_http_client
from ..utils.keys import normalize_cve_id

logger = structlog.get_logger()


class CISAADPAgent(BaseIngestionAgent):
    """
    Agent for ingesting CISA ADP enrichment data from CVE.org.

    CISA acts as a CVE Authorized Data Publisher (ADP) and enriches CVE records with:
    - SSVC (Stakeholder-Specific Vulnerability Categorization) decision points
    - KEV (Known Exploited Vulnerabilities) status
    - Enhanced CWE mappings
    - CISA CVSS scores
    """

    CVE_API_BASE = "https://cveawg.mitre.org/api/cve"

    def __init__(self, db, rate_limit: int = 30):
        """
        Initialize CISA ADP agent.

        Args:
            db: ArangoDB database instance
            rate_limit: API calls per period (default: 30/60s - conservative)
        """
        super().__init__(db)

        # CVE.org API rate limits (undocumented, being conservative)
        self.client = create_http_client(
            service_name="cve_org",
            calls_per_period=rate_limit,
            period_seconds=60,
            circuit_breaker=False,
            timeout=30.0,
        )

        self.logger.info(
            "CISA ADP agent initialized",
            rate_limit=f"{rate_limit} req/60s",
        )

    def fetch_data(self, cve_ids: list[str] = None) -> list[dict]:
        """
        Fetch CISA ADP data for CVEs from CVE.org API.

        Args:
            cve_ids: List of CVE IDs to fetch (e.g., ["CVE-2024-1234", ...])
                     If None, fetches CVEs from vulnerabilities collection

        Returns:
            list[dict]: CVE records with ADP containers

        Note:
            This makes 1 API call per CVE. For large datasets, this is slow.
            Consider running incrementally or filtering by recent CVEs.
        """
        if cve_ids is None:
            # Query vulnerabilities collection for CVE IDs
            self.logger.info("Fetching CVE IDs from vulnerabilities collection")
            cve_ids = self._get_cve_ids_from_db()

        if not cve_ids:
            self.logger.warning("No CVE IDs to fetch")
            return []

        self.logger.info(
            "Fetching CISA ADP data from CVE.org",
            total_cves=len(cve_ids),
            estimated_time_minutes=len(cve_ids) / 30,  # At 30 req/min
        )

        enriched_cves = []
        errors = 0

        for i, cve_id in enumerate(cve_ids, 1):
            if i % 100 == 0:
                self.logger.info(
                    "Fetch progress",
                    completed=i,
                    total=len(cve_ids),
                    errors=errors,
                )

            try:
                url = f"{self.CVE_API_BASE}/{cve_id}"
                response = self.client.get(url)

                if response.status_code == 200:
                    cve_record = response.json()

                    # Check if ADP container exists
                    containers = cve_record.get('containers', {})
                    if 'adp' in containers and containers['adp']:
                        enriched_cves.append(cve_record)
                    else:
                        self.logger.debug("No ADP container", cve_id=cve_id)

                elif response.status_code == 404:
                    self.logger.debug("CVE not found in CVE.org", cve_id=cve_id)

                else:
                    self.logger.warning(
                        "CVE API error",
                        cve_id=cve_id,
                        status=response.status_code,
                    )
                    errors += 1

            except Exception as e:
                self.logger.error(
                    "Failed to fetch CVE",
                    cve_id=cve_id,
                    error=str(e),
                )
                errors += 1

        self.logger.info(
            "Fetch complete",
            enriched=len(enriched_cves),
            total_queried=len(cve_ids),
            errors=errors,
        )

        return enriched_cves

    def _get_cve_ids_from_db(self, limit: int = 1000) -> list[str]:
        """
        Get CVE IDs from vulnerabilities collection.

        Args:
            limit: Maximum CVEs to fetch (default: 1000 for testing)

        Returns:
            list[str]: CVE IDs
        """
        # Query recent vulnerabilities (last 2 years)
        query = f"""
        FOR vuln IN vulnerabilities
            FILTER vuln.cve_id != null
            FILTER vuln.published >= DATE_SUBTRACT(DATE_NOW(), 2, 'years')
            FILTER vuln.cisa_enriched != true
            LIMIT {limit}
            RETURN vuln.cve_id
        """

        cursor = self.db.aql.execute(query)
        cve_ids = list(cursor)

        self.logger.info(
            "Retrieved CVE IDs from database",
            count=len(cve_ids),
            limit=limit,
        )

        return cve_ids

    def transform_data(self, raw_data: list[dict]) -> Generator[dict, None, None]:
        """
        Transform CVE.org records to CISA enrichment data.

        Args:
            raw_data: List of CVE records with ADP containers

        Yields:
            dict: Enrichment data for vulnerabilities
        """
        for cve_record in raw_data:
            # Extract CVE ID
            cve_metadata = cve_record.get('cveMetadata', {})
            cve_id = cve_metadata.get('cveId', '')

            if not cve_id:
                continue

            cve_key = normalize_cve_id(cve_id)

            # Extract ADP containers (CISA is typically first ADP)
            containers = cve_record.get('containers', {})
            adp_list = containers.get('adp', [])

            if not adp_list:
                continue

            # Process first CISA ADP container
            cisa_adp = adp_list[0]

            # Extract SSVC scores
            ssvc_data = None
            kev_data = None
            cisa_cwes = []
            cisa_cvss = None

            metrics = cisa_adp.get('metrics', [])
            for metric in metrics:
                # SSVC decision points
                if 'other' in metric and metric['other'].get('type') == 'ssvc':
                    ssvc_content = metric['other'].get('content', {})
                    ssvc_data = {
                        'exploitation': None,
                        'automatable': None,
                        'technical_impact': None,
                        'timestamp': ssvc_content.get('timestamp'),
                    }

                    for option in ssvc_content.get('options', []):
                        if 'Exploitation' in option:
                            ssvc_data['exploitation'] = option['Exploitation']
                        if 'Automatable' in option:
                            ssvc_data['automatable'] = option['Automatable']
                        if 'Technical Impact' in option:
                            ssvc_data['technical_impact'] = option['Technical Impact']

                # KEV flag
                elif 'other' in metric and metric['other'].get('type') == 'kev':
                    kev_content = metric['other'].get('content', {})
                    kev_data = {
                        'date_added': kev_content.get('dateAdded'),
                        'reference': kev_content.get('reference'),
                    }

                # CISA CVSS score
                elif 'cvssV3_1' in metric:
                    cvss = metric['cvssV3_1']
                    cisa_cvss = {
                        'vector': cvss.get('vectorString'),
                        'base_score': cvss.get('baseScore'),
                        'base_severity': cvss.get('baseSeverity'),
                    }

            # Extract enhanced CWE mappings
            problem_types = cisa_adp.get('problemTypes', [])
            for problem in problem_types:
                descriptions = problem.get('descriptions', [])
                for desc in descriptions:
                    cwe_id = desc.get('cweId', '')
                    if cwe_id:
                        cisa_cwes.append(cwe_id)

            # Yield enrichment data
            enrichment = {
                '_key': cve_key,
                'cve_id': cve_id,
                'cisa_enriched': True,
                'cisa_enrichment_date': datetime.utcnow().isoformat(),
            }

            if ssvc_data:
                enrichment['cisa_ssvc'] = ssvc_data

            if kev_data:
                enrichment['cisa_kev'] = kev_data
                enrichment['in_cisa_kev'] = True

            if cisa_cwes:
                enrichment['cisa_cwe_ids'] = cisa_cwes

            if cisa_cvss:
                enrichment['cisa_cvss'] = cisa_cvss

            yield enrichment

    def load_data(self, records: Generator[dict, None, None], collection_name: str = None, on_duplicate: str = "update") -> dict:
        """
        Load CISA enrichment data into vulnerabilities collection.

        Updates existing vulnerability documents with CISA ADP data.

        Args:
            records: Generator from transform_data()
            collection_name: Ignored (always uses 'vulnerabilities')
            on_duplicate: Action on duplicate _key (always 'update')

        Returns:
            dict: Import statistics
        """
        documents = list(records)

        if not documents:
            self.logger.info("No CISA enrichment data to load")
            return {
                'created': 0,
                'updated': 0,
                'errors': 0,
                'total': 0,
            }

        self.logger.info("Loading CISA ADP enrichments", count=len(documents))

        stats = super().load_data(
            iter(documents),
            collection_name='vulnerabilities',
            on_duplicate='update',  # Always update to enrich existing records
        )

        return stats

    def _get_primary_collection(self) -> str:
        """Get primary collection name."""
        return 'vulnerabilities'
