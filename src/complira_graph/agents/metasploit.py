"""
Metasploit Framework ingestion agent.

Fetches exploit module metadata from Metasploit Framework.
Metasploit is the most widely used penetration testing framework.

Data source: https://github.com/rapid7/metasploit-framework (modules/exploits/)
Collections populated:
- exploit_modules (document collection)
- has_exploit (edges from vulnerabilities to exploit modules)
"""

from typing import Generator
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_http_client
from ..utils.keys import normalize_cve_id

logger = structlog.get_logger()


class MetasploitAgent(BaseIngestionAgent):
    """
    Agent for ingesting Metasploit Framework exploit modules.

    Metasploit provides a comprehensive database of exploits for known vulnerabilities.
    """

    # Metasploit module database from Rapid7
    # Note: This is a simplified approach. For production, consider:
    # 1. Cloning metasploit-framework repo and parsing module files
    # 2. Using Metasploit's msfrpc API
    # 3. Using Rapid7's Vulndb API (commercial)
    METASPLOIT_MODULES_API = "https://raw.githubusercontent.com/rapid7/metasploit-framework/master/db/modules_metadata_base.json"

    def __init__(self, db, github_token: str = None):
        """
        Initialize Metasploit agent.

        Args:
            db: ArangoDB database instance
            github_token: GitHub token for higher rate limits (optional)
        """
        super().__init__(db)
        self.github_token = github_token or getattr(self.settings, 'GITHUB_TOKEN', None)

        rate_limit = 80 if self.github_token else 10
        period = 60

        self.client = create_http_client(
            service_name="metasploit_github",
            calls_per_period=rate_limit,
            period_seconds=period,
            circuit_breaker=False,
            timeout=120.0,
        )

        self.logger.info(
            "Metasploit agent initialized",
            has_token=bool(self.github_token),
        )

    def fetch_data(self) -> dict:
        """
        Fetch Metasploit module metadata.

        Returns:
            dict: Metasploit modules metadata

        Note:
            For production, consider parsing module Ruby files directly from
            metasploit-framework repo for more complete metadata.
        """
        self.logger.info("Fetching Metasploit modules metadata", url=self.METASPLOIT_MODULES_API)

        try:
            headers = {}
            if self.github_token:
                headers["Authorization"] = f"Bearer {self.github_token}"

            response = self.client.get(
                self.METASPLOIT_MODULES_API,
                headers=headers,
            )

            data = response.json()

            self.logger.info(
                "Fetched Metasploit modules",
                modules_count=len(data),
            )

            return data

        except Exception as e:
            self.logger.error(
                "Failed to fetch Metasploit modules metadata",
                error=str(e),
            )
            return {}

    def transform_data(self, raw_data: dict) -> Generator[dict, None, None]:
        """
        Transform Metasploit module data to graph nodes and edges.

        Args:
            raw_data: Metasploit modules metadata from fetch_data()

        Yields:
            dict: Exploit module documents and edges
        """
        for module_path, module_data in raw_data.items():
            # Only process exploit modules
            if not module_path.startswith('exploit/'):
                continue

            # Extract module metadata
            name = module_data.get('name', '')
            description = module_data.get('description', '')
            author = module_data.get('author', [])
            if isinstance(author, str):
                author = [author]

            # Extract CVE references
            references = module_data.get('references', [])
            cve_ids = []
            urls = []

            for ref in references:
                if isinstance(ref, str):
                    if ref.startswith('CVE-'):
                        cve_ids.append(ref)
                    elif ref.startswith('http'):
                        urls.append(ref)
                elif isinstance(ref, list) and len(ref) >= 2:
                    ref_type, ref_value = ref[0], ref[1]
                    if ref_type == 'CVE':
                        cve_ids.append(f"CVE-{ref_value}")
                    elif ref_type == 'URL':
                        urls.append(ref_value)

            # Extract platform and targets
            platform = module_data.get('platform', [])
            if isinstance(platform, str):
                platform = [platform]

            targets = module_data.get('targets', [])
            arch = module_data.get('arch', [])
            if isinstance(arch, str):
                arch = [arch]

            # Extract disclosure date
            disclosure_date = module_data.get('disclosure_date', '')

            # Extract rank (exploit reliability)
            rank = module_data.get('rank', '')

            # Create unique key from module path
            _key = module_path.replace('/', '_').replace('.', '_')

            # Yield exploit module document
            yield {
                '_key': _key,
                'module_path': module_path,
                'name': name,
                'description': description,
                'author': author,
                'platform': platform,
                'arch': arch,
                'targets': targets,
                'disclosure_date': disclosure_date,
                'rank': rank,
                'cve_ids': cve_ids,
                'references': urls,
                'source': 'metasploit',
                'exploit_type': 'metasploit_module',
            }

            # Yield edges to CVEs
            for cve_id in cve_ids:
                cve_key = normalize_cve_id(cve_id)
                yield {
                    '_collection': 'has_exploit',
                    '_from': f'vulnerabilities/{cve_key}',
                    '_to': f'exploit_modules/{_key}',
                    'exploit_type': 'metasploit',
                    'rank': rank,
                    'source': 'metasploit',
                }

    def load_data(self, records: Generator[dict, None, None], collection_name: str = None, on_duplicate: str = "update") -> dict:
        """
        Load Metasploit data into database.

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
        self.logger.info("Loading Metasploit exploit modules", count=len(documents))
        doc_stats = super().load_data(
            iter(documents),
            collection_name='exploit_modules',
            on_duplicate=on_duplicate,
        )

        # Load edges
        edge_stats = {'created': 0, 'updated': 0, 'errors': 0, 'total': 0}

        if edges:
            self.logger.info("Loading has_exploit edges", count=len(edges))
            edge_stats = super().load_data(
                iter(edges),
                collection_name='has_exploit',
                on_duplicate=on_duplicate,
            )

        # Combine statistics
        combined_stats = {
            'exploit_modules': doc_stats,
            'edges': edge_stats,
            'total_created': doc_stats['created'] + edge_stats['created'],
            'total_updated': doc_stats['updated'] + edge_stats['updated'],
            'total_errors': doc_stats['errors'] + edge_stats['errors'],
        }

        return combined_stats

    def _get_primary_collection(self) -> str:
        """Get primary collection name."""
        return 'exploit_modules'
