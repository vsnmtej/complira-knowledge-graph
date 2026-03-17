"""
Vulnrichment (CISA CNA enriched CVE data) ingestion agent.

Fetches enriched CVE data from CISA's vulnrichment repository.
CISA acts as a CVE Numbering Authority (CNA) and provides additional context.

Data source: https://github.com/cisagov/vulnrichment
Collections populated:
- vulncheck_kev_entries (document collection - extended KEV data)
- Updates existing vulnerabilities with CISA enrichment
"""

from typing import Generator
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_http_client
from ..utils.keys import normalize_cve_id

logger = structlog.get_logger()


class VulnrichmentAgent(BaseIngestionAgent):
    """
    Agent for ingesting CISA Vulnrichment data.

    Vulnrichment provides CISA's enriched CVE data as a CNA (CVE Numbering Authority).
    """

    # GitHub API endpoint for vulnrichment repo
    VULNRICHMENT_API_BASE = "https://api.github.com/repos/cisagov/vulnrichment"

    def __init__(self, db, github_token: str = None):
        """
        Initialize Vulnrichment agent.

        Args:
            db: ArangoDB database instance
            github_token: GitHub personal access token (optional, increases rate limits)
        """
        super().__init__(db)
        self.github_token = github_token or getattr(self.settings, 'GITHUB_TOKEN', None)

        # GitHub rate limits
        rate_limit = 80 if self.github_token else 10
        period = 60

        self.client = create_http_client(
            service_name="vulnrichment_github",
            calls_per_period=rate_limit,
            period_seconds=period,
            circuit_breaker=False,
            timeout=30.0,
        )

        self.logger.info(
            "Vulnrichment agent initialized",
            has_token=bool(self.github_token),
            rate_limit=f"{rate_limit} req/{period}s",
        )

    def fetch_data(self) -> list[dict]:
        """
        Fetch vulnrichment data from CISA GitHub repository.

        Returns:
            list[dict]: Enriched CVE records

        Note:
            For production, consider cloning the repo and parsing JSON files locally.
            This implementation uses a placeholder approach.
        """
        self.logger.warning(
            "Vulnrichment agent uses simplified implementation. "
            "For production, clone cisagov/vulnrichment repo and parse JSON files."
        )

        # Placeholder: Return empty list
        # In production, this would:
        # 1. Clone/pull vulnrichment repo
        # 2. Parse CVE JSON files from cves/ directory
        # 3. Extract CISA enrichment data

        self.logger.info("Vulnrichment fetch placeholder - returning empty data")

        return []

    def transform_data(self, raw_data: list[dict]) -> Generator[dict, None, None]:
        """
        Transform vulnrichment data to graph nodes.

        Args:
            raw_data: List of enriched CVE records from fetch_data()

        Yields:
            dict: Enriched vulnerability documents

        Note:
            Vulnrichment data would be used to UPDATE existing vulnerability documents
            with additional CISA-provided context (better CWE mappings, SSVC scores, etc.)
        """
        for cve_record in raw_data:
            # Extract CVE ID from CVE 5.0 format
            cve_metadata = cve_record.get('cveMetadata', {})
            cve_id = cve_metadata.get('cveId', '')

            if not cve_id:
                continue

            cve_key = normalize_cve_id(cve_id)

            # Extract CISA enrichment
            containers = cve_record.get('containers', {})
            cna = containers.get('cna', {})

            # Enhanced CWE mappings from CISA
            problem_types = cna.get('problemTypes', [])
            cisa_cwe_ids = []
            for problem in problem_types:
                descriptions = problem.get('descriptions', [])
                for desc in descriptions:
                    cwe_id = desc.get('cweId', '')
                    if cwe_id:
                        cisa_cwe_ids.append(cwe_id)

            # SSVC (Stakeholder-Specific Vulnerability Categorization)
            ssvc = cna.get('metrics', [])

            # Yield enriched vulnerability update
            yield {
                '_key': cve_key,
                'cve_id': cve_id,
                'cisa_enriched': True,
                'cisa_cwe_ids': cisa_cwe_ids,
                'cisa_ssvc': ssvc,
                'source_enrichment': 'cisa_vulnrichment',
            }

    def load_data(self, records: Generator[dict, None, None], collection_name: str = None, on_duplicate: str = "update") -> dict:
        """
        Load vulnrichment data into database.

        Updates existing vulnerability documents with CISA enrichment.

        Args:
            records: Generator from transform_data()
            collection_name: Ignored (always uses 'vulnerabilities')
            on_duplicate: Action on duplicate _key (default 'update')

        Returns:
            dict: Import statistics
        """
        # Convert generator to list
        documents = list(records)

        if not documents:
            self.logger.info("No vulnrichment data to load (placeholder implementation)")
            return {
                'created': 0,
                'updated': 0,
                'errors': 0,
                'total': 0,
            }

        self.logger.info("Loading vulnrichment enrichments", count=len(documents))

        stats = super().load_data(
            iter(documents),
            collection_name='vulnerabilities',
            on_duplicate='update',  # Always update to enrich existing records
        )

        return stats

    def _get_primary_collection(self) -> str:
        """Get primary collection name."""
        return 'vulnerabilities'
