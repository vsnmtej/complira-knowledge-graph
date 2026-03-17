"""
Nuclei Templates ingestion agent.

Fetches vulnerability detection templates from ProjectDiscovery's Nuclei.
Nuclei is a fast vulnerability scanner based on simple YAML templates.

Data source: https://github.com/projectdiscovery/nuclei-templates
Collections populated:
- exploit_modules (document collection)
- has_exploit (edges from vulnerabilities to templates)
"""

from typing import Generator
import yaml
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_http_client
from ..utils.keys import normalize_cve_id

logger = structlog.get_logger()


class NucleiAgent(BaseIngestionAgent):
    """
    Agent for ingesting Nuclei vulnerability templates.

    Nuclei provides YAML-based vulnerability detection templates.
    """

    # GitHub API for nuclei-templates repo
    NUCLEI_TEMPLATES_API = "https://api.github.com/repos/projectdiscovery/nuclei-templates"

    def __init__(self, db, github_token: str = None):
        """
        Initialize Nuclei agent.

        Args:
            db: ArangoDB database instance
            github_token: GitHub token for higher rate limits (optional)
        """
        super().__init__(db)
        self.github_token = github_token or getattr(self.settings, 'GITHUB_TOKEN', None)

        rate_limit = 80 if self.github_token else 10
        period = 60

        self.client = create_http_client(
            service_name="nuclei_github",
            calls_per_period=rate_limit,
            period_seconds=period,
            circuit_breaker=False,
            timeout=30.0,
        )

        self.logger.info(
            "Nuclei agent initialized",
            has_token=bool(self.github_token),
        )

    def fetch_data(self) -> list[dict]:
        """
        Fetch Nuclei templates metadata.

        Returns:
            list[dict]: Nuclei template metadata

        Note:
            This is a placeholder. For production:
            1. Clone nuclei-templates repo
            2. Parse YAML template files from cves/ directory
            3. Extract metadata from each template
        """
        self.logger.warning(
            "Nuclei agent uses placeholder implementation. "
            "For production, clone projectdiscovery/nuclei-templates repo and parse YAML files."
        )

        # Placeholder: Return empty list
        # In production, this would:
        # 1. Clone/pull nuclei-templates repo
        # 2. Scan cves/ directory for YAML files
        # 3. Parse each YAML template
        # 4. Extract id, info.name, info.description, info.severity, info.reference (CVE IDs)

        self.logger.info("Nuclei fetch placeholder - returning empty data")

        return []

    def transform_data(self, raw_data: list[dict]) -> Generator[dict, None, None]:
        """
        Transform Nuclei template data to graph nodes and edges.

        Args:
            raw_data: List of Nuclei template metadata from fetch_data()

        Yields:
            dict: Exploit module documents and edges

        Example Nuclei template structure:
            id: CVE-2021-1234
            info:
              name: Vulnerability Name
              description: Description
              severity: high
              reference:
                - https://nvd.nist.gov/vuln/detail/CVE-2021-1234
              tags: cve,cve2021
        """
        for template in raw_data:
            # Extract template ID
            template_id = template.get('id', '')
            if not template_id:
                continue

            # Create unique key
            _key = template_id.replace('-', '_').replace('.', '_')

            # Extract info section
            info = template.get('info', {})
            name = info.get('name', '')
            description = info.get('description', '')
            severity = info.get('severity', '')
            author = info.get('author', '')
            tags = info.get('tags', [])
            if isinstance(tags, str):
                tags = tags.split(',')

            # Extract CVE references
            references = info.get('reference', [])
            if isinstance(references, str):
                references = [references]

            cve_ids = []
            # Extract CVE IDs from references or ID
            if template_id.startswith('CVE-'):
                cve_ids.append(template_id)

            import re
            for ref in references:
                cve_matches = re.findall(r'CVE-\d{4}-\d{4,7}', ref)
                cve_ids.extend(cve_matches)

            # Remove duplicates
            cve_ids = list(set(cve_ids))

            # Yield exploit module document
            yield {
                '_key': _key,
                'template_id': template_id,
                'name': name,
                'description': description,
                'severity': severity,
                'author': author,
                'tags': tags,
                'references': references,
                'cve_ids': cve_ids,
                'source': 'nuclei',
                'exploit_type': 'nuclei_template',
            }

            # Yield edges to CVEs
            for cve_id in cve_ids:
                cve_key = normalize_cve_id(cve_id)
                yield {
                    '_collection': 'has_exploit',
                    '_from': f'vulnerabilities/{cve_key}',
                    '_to': f'exploit_modules/{_key}',
                    'exploit_type': 'nuclei',
                    'severity': severity,
                    'source': 'nuclei',
                }

    def load_data(self, records: Generator[dict, None, None], collection_name: str = None, on_duplicate: str = "update") -> dict:
        """
        Load Nuclei data into database.

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

        if not documents:
            self.logger.info("No Nuclei templates to load (placeholder implementation)")
            return {
                'created': 0,
                'updated': 0,
                'errors': 0,
                'total': 0,
            }

        # Load documents
        self.logger.info("Loading Nuclei templates", count=len(documents))
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
