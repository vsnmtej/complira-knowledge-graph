"""
OpenSSF Scorecard ingestion agent.

Fetches security scorecards from OpenSSF Scorecard project.
Scorecard evaluates OSS projects on security best practices.

Data source: https://api.securityscorecards.dev/
Collections populated:
- scorecard_results (document collection)
- scored_by (edges from components to scorecard results)
"""

from typing import Generator
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_http_client
from ..utils.keys import normalize_purl

logger = structlog.get_logger()


class ScorecardAgent(BaseIngestionAgent):
    """
    Agent for ingesting OpenSSF Scorecard security assessment data.

    Scorecard provides automated security analysis for open source projects.
    """

    SCORECARD_API_BASE = "https://api.securityscorecards.dev"

    def __init__(self, db):
        """Initialize OpenSSF Scorecard agent."""
        super().__init__(db)
        self.client = create_http_client(
            service_name="scorecard_openssf",
            calls_per_period=30,
            period_seconds=60,
            circuit_breaker=False,
            timeout=30.0,
        )

    def fetch_data(self, repositories: list[str] = None) -> list[dict]:
        """
        Fetch scorecard data for GitHub repositories.

        Args:
            repositories: List of GitHub repo URLs (e.g., ["github.com/owner/repo"])
                          If None, returns empty list (designed for on-demand queries)

        Returns:
            list[dict]: Scorecard results

        Note:
            OpenSSF Scorecard is designed for on-demand queries via GitHub repo URL.
            For v1.0, this provides the framework for future integration.
        """
        if not repositories:
            self.logger.info("No repositories specified for scorecard fetch (on-demand agent)")
            return []

        self.logger.info("Fetching scorecard results", repo_count=len(repositories))

        all_scorecard_results = []

        for repo_url in repositories:
            # Normalize repo URL format for API
            # API expects: platform/org/repo format
            if repo_url.startswith('https://github.com/'):
                repo_path = repo_url.replace('https://github.com/', '')
                platform = 'github.com'
            elif repo_url.startswith('github.com/'):
                repo_path = repo_url.replace('github.com/', '')
                platform = 'github.com'
            else:
                self.logger.warning("Unsupported repository platform", repo=repo_url)
                continue

            try:
                # Fetch scorecard for repository
                response = self.client.get(
                    f"{self.SCORECARD_API_BASE}/projects/{platform}/{repo_path}",
                )

                scorecard_data = response.json()
                all_scorecard_results.append(scorecard_data)

                self.logger.debug(
                    "Fetched scorecard result",
                    repo=repo_url,
                )

            except Exception as e:
                self.logger.warning(
                    "Failed to fetch scorecard",
                    repo=repo_url,
                    error=str(e),
                )

        self.logger.info(
            "Fetched all scorecard results",
            total=len(all_scorecard_results),
        )

        return all_scorecard_results

    def transform_data(self, raw_data: list[dict]) -> Generator[dict, None, None]:
        """
        Transform scorecard data to graph nodes and edges.

        Args:
            raw_data: List of scorecard results from fetch_data()

        Yields:
            dict: Scorecard result documents and edges
        """
        for scorecard in raw_data:
            # Extract repository info
            repo = scorecard.get('repo', {})
            repo_name = repo.get('name', '')
            repo_commit = repo.get('commit', '')

            if not repo_name:
                continue

            # Create unique key
            _key = f"{repo_name}_{repo_commit}".replace('/', '_').replace('.', '_')[:254]

            # Extract scorecard date and version
            scorecard_date = scorecard.get('date', '')
            scorecard_version = scorecard.get('scorecard', {}).get('version', '')

            # Extract overall score
            score = scorecard.get('score', 0.0)

            # Extract individual checks
            checks = scorecard.get('checks', [])
            check_results = []

            for check in checks:
                check_results.append({
                    'name': check.get('name', ''),
                    'score': check.get('score', 0),
                    'reason': check.get('reason', ''),
                    'documentation': check.get('documentation', {}).get('url', ''),
                })

            # Extract metadata
            metadata = scorecard.get('metadata', [])

            # Yield scorecard result document
            yield {
                '_key': _key,
                'repository': repo_name,
                'commit': repo_commit,
                'scorecard_date': scorecard_date,
                'scorecard_version': scorecard_version,
                'overall_score': score,
                'checks': check_results,
                'metadata': metadata,
                'source': 'openssf_scorecard',
            }

            # For edge to component, we'd need to resolve repo URL to PURL
            # This requires additional mapping logic
            # For now, store as standalone scorecard result

    def load_data(self, records: Generator[dict, None, None], collection_name: str = None, on_duplicate: str = "update") -> dict:
        """
        Load scorecard data into database.

        Args:
            records: Generator from transform_data()
            collection_name: Ignored (always uses 'scorecard_results')
            on_duplicate: Action on duplicate _key

        Returns:
            dict: Import statistics
        """
        # Convert generator to list
        documents = list(records)

        if not documents:
            self.logger.info("No scorecard results to load (placeholder implementation)")
            return {
                'created': 0,
                'updated': 0,
                'errors': 0,
                'total': 0,
            }

        self.logger.info("Loading scorecard results", count=len(documents))

        stats = super().load_data(
            iter(documents),
            collection_name='scorecard_results',
            on_duplicate=on_duplicate,
        )

        return stats

    def _get_primary_collection(self) -> str:
        """Get primary collection name."""
        return 'scorecard_results'
