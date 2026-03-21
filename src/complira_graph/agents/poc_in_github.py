"""
PoC-in-GitHub ingestion agent.

Tracks proof-of-concept exploits published on GitHub.
Searches GitHub for repositories containing CVE exploit PoCs.

Data source: GitHub Code Search API / nomi-sec/PoC-in-GitHub repo
Collections populated:
- exploit_modules (document collection)
- has_exploit (edges from vulnerabilities to GitHub PoCs)
"""

from typing import Generator
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_http_client
from ..utils.keys import normalize_cve_id
from ..utils.transforms import safe_date_parse

logger = structlog.get_logger()


class PoCInGitHubAgent(BaseIngestionAgent):
    """
    Agent for ingesting PoC-in-GitHub exploit data.

    Tracks public proof-of-concept exploits shared on GitHub.
    """

    # nomi-sec/PoC-in-GitHub maintains a curated list
    POC_IN_GITHUB_API = "https://raw.githubusercontent.com/nomi-sec/PoC-in-GitHub/master/2024/PoC-in-GitHub-2024.json"

    def __init__(self, db, github_token: str = None):
        """
        Initialize PoC-in-GitHub agent.

        Args:
            db: ArangoDB database instance
            github_token: GitHub token for API access (optional)
        """
        super().__init__(db)
        self.github_token = github_token or getattr(self.settings, 'GITHUB_TOKEN', None)

        rate_limit = 80 if self.github_token else 10
        period = 60

        self.client = create_http_client(
            service_name="poc_in_github",
            calls_per_period=rate_limit,
            period_seconds=period,
            circuit_breaker=False,
            timeout=60.0,
        )

        self.logger.info(
            "PoC-in-GitHub agent initialized",
            has_token=bool(self.github_token),
        )

    def fetch_data(self) -> dict:
        """
        Fetch PoC-in-GitHub data.

        Returns:
            dict: PoC repository metadata

        Note:
            For complete coverage, fetch multiple years:
            - PoC-in-GitHub-2024.json
            - PoC-in-GitHub-2023.json
            - etc.
        """
        self.logger.info("Fetching PoC-in-GitHub data", url=self.POC_IN_GITHUB_API)

        try:
            response = self.client.get(self.POC_IN_GITHUB_API)
            data = response.json()

            self.logger.info(
                "Fetched PoC-in-GitHub data",
                pocs_count=len(data),
            )

            return data

        except Exception as e:
            self.logger.error(
                "Failed to fetch PoC-in-GitHub data",
                error=str(e),
            )
            return {}

    def transform_data(self, raw_data: dict) -> Generator[dict, None, None]:
        """
        Transform PoC-in-GitHub data to graph nodes and edges.

        Args:
            raw_data: PoC metadata dict from fetch_data()

        Yields:
            dict: Exploit module documents and edges

        Data structure:
            {
                "CVE-2024-1234": [
                    {
                        "html_url": "https://github.com/user/repo",
                        "created_at": "2024-01-15T10:00:00Z",
                        "pushed_at": "2024-01-20T12:00:00Z",
                        "stargazers_count": 42,
                        "watchers_count": 10
                    }
                ]
            }
        """
        for cve_id, repos in raw_data.items():
            # Validate CVE ID
            if not cve_id.startswith('CVE-'):
                continue

            cve_key = normalize_cve_id(cve_id)

            # Process each PoC repository for this CVE
            for repo in repos:
                if not isinstance(repo, dict):
                    continue

                # Extract repository metadata
                repo_url = repo.get('html_url', '')
                if not repo_url:
                    continue

                # Create unique key from repo URL
                # Extract owner/repo from URL (e.g., github.com/user/repo)
                repo_path = repo_url.replace('https://github.com/', '').replace('/', '_')
                _key = f"POC_{repo_path}"

                created_at = safe_date_parse(repo.get('created_at'))
                pushed_at = safe_date_parse(repo.get('pushed_at'))
                stars = repo.get('stargazers_count', 0)
                watchers = repo.get('watchers_count', 0)

                # Yield exploit module document
                yield {
                    '_key': _key,
                    'cve_id': cve_id,
                    'repository_url': repo_url,
                    'created_at': created_at.isoformat() if created_at else None,
                    'pushed_at': pushed_at.isoformat() if pushed_at else None,
                    'stars': stars,
                    'watchers': watchers,
                    'source': 'poc_in_github',
                    'exploit_type': 'github_poc',
                }

                # Yield edge to CVE
                yield {
                    '_collection': 'has_exploit',
                    '_from': f'vulnerabilities/{cve_key}',
                    '_to': f'exploit_modules/{_key}',
                    'exploit_type': 'github_poc',
                    'stars': stars,
                    'source': 'poc_in_github',
                }

    def load_data(self, records: Generator[dict, None, None], collection_name: str = None, on_duplicate: str = "update") -> dict:
        """
        Load PoC-in-GitHub data into database.

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
        self.logger.info("Loading PoC-in-GitHub exploits", count=len(documents))
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
