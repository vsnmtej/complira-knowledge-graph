"""
KEV (Known Exploited Vulnerabilities) ingestion agent.

Fetches CISA KEV catalog - authoritative list of CVEs exploited in the wild.
KEV is critical for vulnerability prioritization.

Data source: https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json
Collections populated:
- kev_entries (document collection)
- exploited_in_wild (edges from vulnerabilities to KEV entries)
"""

from typing import Generator
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_http_client
from ..utils.keys import normalize_cve_id
from ..utils.transforms import safe_date_parse

logger = structlog.get_logger()


class KEVAgent(BaseIngestionAgent):
    """
    Agent for ingesting CISA KEV (Known Exploited Vulnerabilities) catalog.

    KEV provides authoritative list of CVEs actively exploited in the wild.
    """

    KEV_JSON_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"

    def __init__(self, db):
        """Initialize KEV agent."""
        super().__init__(db)
        self.client = create_http_client(
            service_name="cisa_kev",
            calls_per_period=10,
            period_seconds=60,
            circuit_breaker=False,
            timeout=30.0,
        )

    def fetch_data(self) -> dict:
        """
        Fetch KEV catalog from CISA.

        Returns:
            dict: KEV catalog JSON

        Raises:
            Exception: On fetch failure
        """
        self.logger.info("Fetching CISA KEV catalog", url=self.KEV_JSON_URL)

        response = self.client.get(self.KEV_JSON_URL)
        data = response.json()

        self.logger.info(
            "Fetched CISA KEV catalog",
            title=data.get('title', ''),
            catalog_version=data.get('catalogVersion', ''),
            count=data.get('count', 0),
        )

        return data

    def transform_data(self, raw_data: dict) -> Generator[dict, None, None]:
        """
        Transform KEV catalog to graph nodes and edges.

        Args:
            raw_data: KEV catalog JSON from fetch_data()

        Yields:
            dict: KEV entry documents and edges to vulnerabilities
        """
        vulnerabilities = raw_data.get('vulnerabilities', [])

        for vuln in vulnerabilities:
            # Extract CVE ID
            cve_id = vuln.get('cveID', '')
            if not cve_id:
                continue

            cve_key = normalize_cve_id(cve_id)

            # Use CVE key as _key for KEV entries (1:1 mapping)
            _key = cve_key

            # Extract KEV-specific fields
            vendor_project = vuln.get('vendorProject', '')
            product = vuln.get('product', '')
            vulnerability_name = vuln.get('vulnerabilityName', '')
            date_added = vuln.get('dateAdded', '')
            short_description = vuln.get('shortDescription', '')
            required_action = vuln.get('requiredAction', '')
            due_date = vuln.get('dueDate', '')
            known_ransomware_campaign_use = vuln.get('knownRansomwareCampaignUse', 'Unknown')
            notes = vuln.get('notes', '')

            # Parse dates
            date_added_dt = safe_date_parse(date_added)
            due_date_dt = safe_date_parse(due_date)

            # Yield KEV entry document
            yield {
                '_key': _key,
                'cve_id': cve_id,
                'vendor_project': vendor_project,
                'product': product,
                'vulnerability_name': vulnerability_name,
                'short_description': short_description,
                'required_action': required_action,
                'date_added': date_added_dt.isoformat() if date_added_dt else None,
                'due_date': due_date_dt.isoformat() if due_date_dt else None,
                'known_ransomware_campaign_use': known_ransomware_campaign_use,
                'notes': notes,
                'source': 'cisa_kev',
            }

            # Yield edge from vulnerability to KEV entry
            yield {
                '_collection': 'exploited_in_wild',
                '_from': f'vulnerabilities/{cve_key}',
                '_to': f'kev_entries/{_key}',
                'date_added': date_added_dt.isoformat() if date_added_dt else None,
                'source': 'cisa_kev',
            }

    def load_data(self, records: Generator[dict, None, None], collection_name: str = None, on_duplicate: str = "update") -> dict:
        """
        Load KEV data into database.

        Overrides base class to handle multiple collections.

        Args:
            records: Generator from transform_data()
            collection_name: Ignored
            on_duplicate: Action on duplicate _key

        Returns:
            dict: Combined statistics
        """
        # Separate documents from edges
        documents = []
        edges = []

        for record in records:
            if '_collection' in record:
                # It's an edge
                record.pop('_collection')
                edges.append(record)
            else:
                # It's a document
                documents.append(record)

        # Load documents
        self.logger.info("Loading CISA KEV entries", count=len(documents))
        doc_stats = super().load_data(
            iter(documents),
            collection_name='kev_entries',
            on_duplicate=on_duplicate,
        )

        # Load edges
        edge_stats = {'created': 0, 'updated': 0, 'errors': 0, 'total': 0}

        if edges:
            self.logger.info("Loading exploited_in_wild edges", count=len(edges))
            edge_stats = super().load_data(
                iter(edges),
                collection_name='exploited_in_wild',
                on_duplicate=on_duplicate,
            )

        # Combine statistics
        combined_stats = {
            'kev_entries': doc_stats,
            'edges': edge_stats,
            'total_created': doc_stats['created'] + edge_stats['created'],
            'total_updated': doc_stats['updated'] + edge_stats['updated'],
            'total_errors': doc_stats['errors'] + edge_stats['errors'],
        }

        return combined_stats

    def _get_primary_collection(self) -> str:
        """Get primary collection name."""
        return 'kev_entries'
