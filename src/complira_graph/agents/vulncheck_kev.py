"""
VulnCheck KEV (Known Exploited Vulnerabilities) ingestion agent.

Fetches VulnCheck extended KEV catalog - broader coverage than CISA KEV with additional enrichment.
VulnCheck KEV includes exploit database references, ransomware tracking, and canary detections.

Data source: https://api.vulncheck.com/v3/backup/vulncheck-kev
Documentation: https://docs.vulncheck.com/community/vulncheck-kev

Collections populated:
- vulncheck_kev_entries (document collection)
- exploited_in_wild (edges from vulnerabilities to VulnCheck KEV entries)

Requires: VULNCHECK_API_KEY environment variable
"""

from typing import Generator, Optional
import json
import zipfile
import io
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_http_client
from ..utils.keys import normalize_cve_id
from ..utils.transforms import safe_date_parse
from ..config import get_settings

logger = structlog.get_logger()


class VulnCheckKEVAgent(BaseIngestionAgent):
    """
    Agent for ingesting VulnCheck KEV catalog.

    VulnCheck KEV provides extended vulnerability intelligence beyond CISA KEV,
    including exploit database cross-references and ransomware campaign tracking.
    """

    VULNCHECK_KEV_URL = "https://api.vulncheck.com/v3/backup/vulncheck-kev"

    def __init__(self, db, api_key: Optional[str] = None):
        """
        Initialize VulnCheck KEV agent.

        Args:
            db: ArangoDB connection
            api_key: VulnCheck API key (optional, defaults to settings.VULNCHECK_API_KEY)
        """
        super().__init__(db)

        # Get API key from parameter or settings
        settings = get_settings()
        self.api_key = api_key or settings.VULNCHECK_API_KEY

        if not self.api_key:
            raise ValueError(
                "VulnCheck API key required. Set VULNCHECK_API_KEY environment variable "
                "or pass api_key parameter. Get your free API key at: https://vulncheck.com/"
            )

        # Create HTTP client with Bearer token authentication
        self.client = create_http_client(
            service_name="vulncheck_kev",
            calls_per_period=1000,  # Community tier: 1000 req/min
            period_seconds=60,
            circuit_breaker=True,
            timeout=120.0,
        )

        self.logger.info(
            "VulnCheck KEV agent initialized",
            has_api_key=bool(self.api_key),
        )

    def fetch_data(self) -> dict:
        """
        Fetch VulnCheck KEV catalog via backup endpoint.

        The backup endpoint returns metadata with a pre-signed S3 URL to download
        a ZIP file containing the actual KEV data in JSON format.

        Returns:
            dict: VulnCheck KEV catalog JSON

        Raises:
            Exception: On fetch failure (API key invalid, network error, etc.)
        """
        self.logger.info("Fetching VulnCheck KEV backup metadata", url=self.VULNCHECK_KEV_URL)

        # Step 1: Get backup metadata (contains ZIP download URL)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

        response = self.client.get(self.VULNCHECK_KEV_URL, headers=headers)

        # Check for API errors
        if response.status_code == 401:
            raise ValueError("Invalid VulnCheck API key. Get your API key at: https://vulncheck.com/")
        elif response.status_code == 403:
            raise ValueError("VulnCheck API access denied. Check your subscription tier.")

        response.raise_for_status()
        metadata = response.json()

        # Extract backup metadata
        backup_data = metadata.get('data', [])
        if not backup_data:
            raise ValueError("No backup data available from VulnCheck")

        backup_info = backup_data[0]
        zip_url = backup_info.get('url')  # Pre-signed S3 URL
        filename = backup_info.get('filename', 'vulncheck-kev.zip')
        sha256 = backup_info.get('sha256', '')

        if not zip_url:
            raise ValueError("No download URL in VulnCheck backup metadata")

        self.logger.info(
            "Downloading VulnCheck KEV ZIP",
            filename=filename,
            sha256=sha256,
        )

        # Step 2: Download ZIP file from S3 (no auth needed - pre-signed URL)
        zip_response = self.client.get(zip_url)
        zip_response.raise_for_status()

        # Step 3: Extract JSON from ZIP
        zip_data = io.BytesIO(zip_response.content)
        kev_entries = []

        with zipfile.ZipFile(zip_data, 'r') as zip_file:
            # Get list of files in ZIP
            file_list = zip_file.namelist()
            self.logger.debug("ZIP contents", files=file_list)

            # Find JSON file (usually vulncheck-kev.json or similar)
            json_file = None
            for fname in file_list:
                if fname.endswith('.json'):
                    json_file = fname
                    break

            if not json_file:
                raise ValueError(f"No JSON file found in ZIP: {file_list}")

            self.logger.info("Extracting KEV data", json_file=json_file)

            # Read and parse JSON
            with zip_file.open(json_file) as f:
                json_content = f.read()
                kev_data = json.loads(json_content)

        self.logger.info(
            "Fetched VulnCheck KEV catalog",
            entry_count=len(kev_data) if isinstance(kev_data, list) else len(kev_data.get('data', [])),
        )

        # Return in consistent format (wrap in dict if it's a list)
        if isinstance(kev_data, list):
            return {'data': kev_data}
        else:
            return kev_data

    def transform_data(self, raw_data: dict) -> Generator[dict, None, None]:
        """
        Transform VulnCheck KEV catalog to graph nodes and edges.

        Args:
            raw_data: VulnCheck KEV catalog JSON from fetch_data()

        Yields:
            dict: VulnCheck KEV entry documents and edges to vulnerabilities
        """
        kev_entries = raw_data.get('data', [])

        for entry in kev_entries:
            # Extract CVE IDs (can be multiple)
            cve_ids = entry.get('cve', [])
            if not cve_ids:
                self.logger.warning("KEV entry missing CVE IDs", entry_id=entry.get('_id'))
                continue

            # Use first CVE as primary identifier for _key
            primary_cve = cve_ids[0] if isinstance(cve_ids, list) else cve_ids
            primary_cve_key = normalize_cve_id(primary_cve)

            # Generate unique _key for VulnCheck KEV entry
            # Use primary CVE + _vulncheck suffix to distinguish from CISA KEV
            _key = f"{primary_cve_key}_vulncheck"

            # Extract core fields
            vendor_project = entry.get('vendorProject', '')
            product = entry.get('product', '')
            vulnerability_name = entry.get('vulnerabilityName', '')
            short_description = entry.get('shortDescription', '')
            required_action = entry.get('required_action', '')
            known_ransomware_campaign_use = entry.get('knownRansomwareCampaignUse', 'Unknown')

            # Extract VulnCheck-specific enrichment
            vulncheck_xdb = entry.get('vulncheck_xdb', [])  # Exploit database references
            vulncheck_reported_exploitation = entry.get('vulncheck_reported_exploitation', [])
            reported_exploited_by_canaries = entry.get('reported_exploited_by_vulncheck_canaries', False)

            # Extract dates
            date_added = entry.get('date_added', '')
            due_date = entry.get('dueDate', '')
            cisa_date_added = entry.get('cisa_date_added', '')

            # Parse dates
            date_added_dt = safe_date_parse(date_added)
            due_date_dt = safe_date_parse(due_date)
            cisa_date_added_dt = safe_date_parse(cisa_date_added)

            # Yield VulnCheck KEV entry document
            yield {
                '_key': _key,
                'cve_ids': cve_ids,  # Array of CVE IDs
                'primary_cve_id': primary_cve,
                'vendor_project': vendor_project,
                'product': product,
                'vulnerability_name': vulnerability_name,
                'short_description': short_description,
                'required_action': required_action,
                'known_ransomware_campaign_use': known_ransomware_campaign_use,
                'date_added': date_added_dt.isoformat() if date_added_dt else None,
                'due_date': due_date_dt.isoformat() if due_date_dt else None,
                'cisa_date_added': cisa_date_added_dt.isoformat() if cisa_date_added_dt else None,
                # VulnCheck enrichment
                'vulncheck_xdb': vulncheck_xdb,  # Exploit database cross-references
                'vulncheck_reported_exploitation': vulncheck_reported_exploitation,
                'reported_exploited_by_canaries': reported_exploited_by_canaries,
                'source': 'vulncheck',
            }

            # Yield edges from each CVE to this VulnCheck KEV entry
            for cve_id in cve_ids:
                cve_key = normalize_cve_id(cve_id)
                yield {
                    '_collection': 'exploited_in_wild',
                    '_from': f'vulnerabilities/{cve_key}',
                    '_to': f'vulncheck_kev_entries/{_key}',
                    'date_added': date_added_dt.isoformat() if date_added_dt else None,
                    'source': 'vulncheck',
                    'has_exploit_db_reference': len(vulncheck_xdb) > 0,
                    'has_reported_exploitation': len(vulncheck_reported_exploitation) > 0,
                    'canary_detected': reported_exploited_by_canaries,
                }

    def load_data(self, records: Generator[dict, None, None], collection_name: str = None, on_duplicate: str = "update") -> dict:
        """
        Load VulnCheck KEV data into database.

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
        self.logger.info("Loading VulnCheck KEV entries", count=len(documents))
        doc_stats = super().load_data(
            iter(documents),
            collection_name='vulncheck_kev_entries',
            on_duplicate=on_duplicate,
        )

        # Load edges
        edge_stats = {'created': 0, 'updated': 0, 'errors': 0, 'total': 0}

        if edges:
            self.logger.info("Loading exploited_in_wild edges (VulnCheck)", count=len(edges))
            edge_stats = super().load_data(
                iter(edges),
                collection_name='exploited_in_wild',
                on_duplicate=on_duplicate,
            )

        # Combine statistics
        combined_stats = {
            'vulncheck_kev_entries': doc_stats,
            'edges': edge_stats,
            'total_created': doc_stats['created'] + edge_stats['created'],
            'total_updated': doc_stats['updated'] + edge_stats['updated'],
            'total_errors': doc_stats['errors'] + edge_stats['errors'],
        }

        return combined_stats

    def _get_primary_collection(self) -> str:
        """Get primary collection name."""
        return 'vulncheck_kev_entries'
