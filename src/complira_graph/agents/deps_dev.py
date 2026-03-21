"""
deps.dev ingestion agent.

Fetches dependency metadata from Google's deps.dev API.
deps.dev provides insights on package dependencies, vulnerabilities, and licenses.

Data source: https://api.deps.dev/v3alpha/
Collections populated:
- components (document collection)
- depends_on (edges between components)
- licensed_under (edges to licenses)
"""

from typing import Generator
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_http_client
from ..utils.keys import normalize_purl

logger = structlog.get_logger()


class DepsDevAgent(BaseIngestionAgent):
    """
    Agent for ingesting deps.dev (Google) package dependency data.

    deps.dev provides comprehensive dependency metadata for open source packages.
    """

    DEPS_DEV_API_BASE = "https://api.deps.dev/v3alpha"

    def __init__(self, db):
        """Initialize deps.dev agent."""
        super().__init__(db)
        self.client = create_http_client(
            service_name="deps_dev",
            calls_per_period=30,
            period_seconds=60,
            circuit_breaker=False,
            timeout=30.0,
        )

    def fetch_data(self, packages: list[dict] = None) -> list[dict]:
        """
        Fetch package metadata from deps.dev API.

        Args:
            packages: List of packages to fetch (format: [{"system": "npm", "name": "lodash"}, ...])
                      If None, returns empty list (designed for on-demand queries)

        Returns:
            list[dict]: Package metadata from deps.dev

        Note:
            deps.dev is designed for on-demand queries, not bulk ingestion.
            For v1.0, this agent provides the framework for future integration.
        """
        if not packages:
            self.logger.info("No packages specified for deps.dev fetch (on-demand agent)")
            return []

        self.logger.info("Fetching package data from deps.dev", package_count=len(packages))

        all_package_data = []

        for pkg in packages:
            system = pkg.get('system', '')
            name = pkg.get('name', '')

            if not system or not name:
                continue

            try:
                # Fetch package version info
                response = self.client.get(
                    f"{self.DEPS_DEV_API_BASE}/systems/{system}/packages/{name}",
                )

                package_data = response.json()
                all_package_data.append(package_data)

                self.logger.debug(
                    "Fetched package from deps.dev",
                    system=system,
                    name=name,
                )

            except Exception as e:
                self.logger.warning(
                    "Failed to fetch package from deps.dev",
                    system=system,
                    name=name,
                    error=str(e),
                )

        self.logger.info(
            "Fetched all package data from deps.dev",
            total=len(all_package_data),
        )

        return all_package_data

    def transform_data(self, raw_data: list[dict]) -> Generator[dict, None, None]:
        """
        Transform deps.dev package data to graph nodes and edges.

        Args:
            raw_data: List of package metadata from fetch_data()

        Yields:
            dict: Component documents and relationship edges
        """
        for package in raw_data:
            # Extract package identifier
            package_key = package.get('packageKey', {})
            system = package_key.get('system', '')
            name = package_key.get('name', '')

            if not system or not name:
                continue

            # Build PURL (Package URL)
            purl = f"pkg:{system}/{name}"
            _key = normalize_purl(purl)

            # Extract versions
            versions = package.get('versions', [])
            latest_version = None
            if versions:
                # Get latest version (assuming sorted)
                latest_version = versions[-1].get('versionKey', {}).get('version')

            # Yield component document
            yield {
                '_key': _key,
                'purl': purl,
                'ecosystem': system,
                'name': name,
                'latest_version': latest_version,
                'versions_count': len(versions),
                'source': 'deps_dev',
            }

            # For each version, extract dependencies and licenses
            for version_data in versions:
                version_key = version_data.get('versionKey', {})
                version = version_key.get('version', '')

                if not version:
                    continue

                # Extract dependencies
                dependencies = version_data.get('dependencies', [])
                for dep in dependencies:
                    dep_key = dep.get('packageKey', {})
                    dep_system = dep_key.get('system', '')
                    dep_name = dep_key.get('name', '')

                    if not dep_system or not dep_name:
                        continue

                    dep_purl = f"pkg:{dep_system}/{dep_name}"
                    dep_key_normalized = normalize_purl(dep_purl)

                    # Yield dependency edge
                    yield {
                        '_collection': 'depends_on',
                        '_from': f'components/{_key}',
                        '_to': f'components/{dep_key_normalized}',
                        'version': version,
                        'source': 'deps_dev',
                    }

                # Extract licenses
                licenses = version_data.get('licenses', [])
                for license in licenses:
                    license_id = license.replace('.', '_').replace('-', '_').replace('+', '_plus')

                    # Yield license edge
                    yield {
                        '_collection': 'licensed_under',
                        '_from': f'components/{_key}',
                        '_to': f'licenses/{license_id}',
                        'version': version,
                        'source': 'deps_dev',
                    }

    def load_data(self, records: Generator[dict, None, None], collection_name: str = None, on_duplicate: str = "update") -> dict:
        """
        Load deps.dev data into database.

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
        edges_by_collection = {
            'depends_on': [],
            'licensed_under': [],
        }

        for record in records:
            if '_collection' in record:
                # It's an edge
                collection = record.pop('_collection')
                if collection in edges_by_collection:
                    edges_by_collection[collection].append(record)
            else:
                # It's a document
                documents.append(record)

        # Load documents
        self.logger.info("Loading deps.dev components", count=len(documents))
        doc_stats = super().load_data(
            iter(documents),
            collection_name='components',
            on_duplicate=on_duplicate,
        )

        # Load edges
        total_edge_stats = {'created': 0, 'updated': 0, 'errors': 0, 'total': 0}

        for collection, edges in edges_by_collection.items():
            if not edges:
                continue

            self.logger.info(f"Loading {collection} edges", count=len(edges))
            edge_stats = super().load_data(
                iter(edges),
                collection_name=collection,
                on_duplicate=on_duplicate,
            )

            total_edge_stats['created'] += edge_stats['created']
            total_edge_stats['updated'] += edge_stats['updated']
            total_edge_stats['errors'] += edge_stats['errors']
            total_edge_stats['total'] += edge_stats['total']

        # Combine statistics
        combined_stats = {
            'components': doc_stats,
            'edges': total_edge_stats,
            'total_created': doc_stats['created'] + total_edge_stats['created'],
            'total_updated': doc_stats['updated'] + total_edge_stats['updated'],
            'total_errors': doc_stats['errors'] + total_edge_stats['errors'],
        }

        return combined_stats

    def _get_primary_collection(self) -> str:
        """Get primary collection name."""
        return 'components'
