"""
Ecosyste.ms ingestion agent.

Fetches package ecosystem data from ecosyste.ms APIs.
Ecosyste.ms provides health metrics, dependencies, and metadata for packages.

Data source: https://packages.ecosyste.ms/api/v1/
Collections populated:
- package_health (document collection - health scores and metrics)
- components (updates existing components with health data)
"""

from typing import Generator
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_http_client
from ..utils.keys import normalize_purl

logger = structlog.get_logger()


class EcosystemsAgent(BaseIngestionAgent):
    """
    Agent for ingesting Ecosyste.ms package health and metadata.

    Ecosyste.ms provides health scores, maintenance metrics, and ecosystem data.
    """

    ECOSYSTEMS_API_BASE = "https://packages.ecosyste.ms/api/v1"
    # Supported registries
    REGISTRIES = ["npmjs.org", "rubygems.org", "pypi.org", "crates.io", "maven.org"]

    def __init__(self, db):
        """Initialize Ecosyste.ms agent."""
        super().__init__(db)
        self.client = create_http_client(
            service_name="ecosystems",
            calls_per_period=30,
            period_seconds=60,
            circuit_breaker=False,
            timeout=30.0,
        )

    def fetch_data(self, packages: list[dict] = None) -> list[dict]:
        """
        Fetch package health data from ecosyste.ms API.

        Args:
            packages: List of packages to fetch (format: [{"registry": "npmjs.org", "name": "lodash"}, ...])
                      If None, returns empty list (designed for on-demand queries)

        Returns:
            list[dict]: Package health metadata from ecosyste.ms

        Note:
            Like deps.dev, ecosyste.ms is designed for on-demand queries.
            For v1.0, this provides the framework for future integration.
        """
        if not packages:
            self.logger.info("No packages specified for ecosyste.ms fetch (on-demand agent)")
            return []

        self.logger.info("Fetching package health from ecosyste.ms", package_count=len(packages))

        all_health_data = []

        for pkg in packages:
            registry = pkg.get('registry', '')
            name = pkg.get('name', '')

            if not registry or not name:
                continue

            try:
                # Fetch package info
                response = self.client.get(
                    f"{self.ECOSYSTEMS_API_BASE}/registries/{registry}/packages/{name}",
                )

                health_data = response.json()
                all_health_data.append(health_data)

                self.logger.debug(
                    "Fetched package health from ecosyste.ms",
                    registry=registry,
                    name=name,
                )

            except Exception as e:
                self.logger.warning(
                    "Failed to fetch package from ecosyste.ms",
                    registry=registry,
                    name=name,
                    error=str(e),
                )

        self.logger.info(
            "Fetched all package health from ecosyste.ms",
            total=len(all_health_data),
        )

        return all_health_data

    def transform_data(self, raw_data: list[dict]) -> Generator[dict, None, None]:
        """
        Transform ecosyste.ms health data to graph nodes.

        Args:
            raw_data: List of package health metadata from fetch_data()

        Yields:
            dict: Package health documents
        """
        for health in raw_data:
            # Extract package identifier
            registry = health.get('registry', {}).get('name', '')
            name = health.get('name', '')

            if not registry or not name:
                continue

            # Map registry to ecosystem
            ecosystem_map = {
                'npmjs.org': 'npm',
                'rubygems.org': 'gem',
                'pypi.org': 'pypi',
                'crates.io': 'cargo',
                'maven.org': 'maven',
            }

            ecosystem = ecosystem_map.get(registry, registry)

            # Build PURL
            purl = f"pkg:{ecosystem}/{name}"
            _key = normalize_purl(purl)

            # Extract health metrics
            scorecard = health.get('scorecard', {})
            health_score = scorecard.get('overall_score')
            scorecard_date = scorecard.get('date')

            # Extract repository info
            repository = health.get('repository', {})
            repo_url = repository.get('url', '')
            repo_stars = repository.get('stargazers_count', 0)
            repo_forks = repository.get('forks_count', 0)
            repo_open_issues = repository.get('open_issues_count', 0)

            # Extract maintenance metrics
            latest_release_published_at = health.get('latest_release_published_at')
            latest_release_number = health.get('latest_release_number', '')
            downloads = health.get('downloads', 0)

            # Yield package health document
            yield {
                '_key': _key,
                'purl': purl,
                'ecosystem': ecosystem,
                'name': name,
                'health_score': health_score,
                'scorecard_date': scorecard_date,
                'repository_url': repo_url,
                'stars': repo_stars,
                'forks': repo_forks,
                'open_issues': repo_open_issues,
                'latest_release': latest_release_number,
                'latest_release_date': latest_release_published_at,
                'downloads': downloads,
                'source': 'ecosystems',
            }

    def load_data(self, records: Generator[dict, None, None], collection_name: str = None, on_duplicate: str = "update") -> dict:
        """
        Load ecosyste.ms health data into database.

        Args:
            records: Generator from transform_data()
            collection_name: Ignored (always uses 'package_health')
            on_duplicate: Action on duplicate _key

        Returns:
            dict: Import statistics
        """
        # Convert generator to list
        documents = list(records)

        if not documents:
            self.logger.info("No package health data to load (placeholder implementation)")
            return {
                'created': 0,
                'updated': 0,
                'errors': 0,
                'total': 0,
            }

        self.logger.info("Loading package health data", count=len(documents))

        stats = super().load_data(
            iter(documents),
            collection_name='package_health',
            on_duplicate=on_duplicate,
        )

        return stats

    def _get_primary_collection(self) -> str:
        """Get primary collection name."""
        return 'package_health'
