"""
OpenCRE (Open Common Requirement Enumeration) ingestion agent.

Fetches OpenCRE data from OWASP and populates security requirement mappings.
OpenCRE provides mappings between security standards (OWASP, NIST, ISO, CIS, etc.).

Data source: https://www.opencre.org/rest/v1/cre_catalog

⚠️ WARNING (2026-03): The public OpenCRE API endpoint has been deprecated.
   The CSV export functionality now requires running a local OpenCRE Docker instance.
   This agent will return 0 records until an alternative data source is configured.
   See: https://github.com/OWASP/OpenCRE/blob/main/docs/my-opencre-user-guide.md

Collections populated:
- opencre_nodes (document collection)
- opencre_links (edges between CRE nodes and external standards)
"""

from typing import Generator
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_http_client

logger = structlog.get_logger()


class OpenCREAgent(BaseIngestionAgent):
    """
    Agent for ingesting OpenCRE (Open Common Requirement Enumeration) data.

    OpenCRE provides mappings between security standards and requirements from OWASP, NIST, ISO, etc.
    """

    OPENCRE_API_URL = "https://www.opencre.org/rest/v1/cre_catalog"

    def __init__(self, db):
        """Initialize OpenCRE agent."""
        super().__init__(db)
        self.client = create_http_client(
            service_name="opencre_owasp",
            calls_per_period=10,
            period_seconds=60,
            circuit_breaker=False,
            timeout=120.0,
        )

    def fetch_data(self) -> dict:
        """
        Fetch OpenCRE catalog from OWASP API.

        Returns:
            dict: OpenCRE catalog JSON

        Raises:
            Exception: On fetch failure
        """
        self.logger.info("Fetching OpenCRE catalog from OWASP API", url=self.OPENCRE_API_URL)

        try:
            response = self.client.get(self.OPENCRE_API_URL)

            # Check response status
            if response.status_code != 200:
                self.logger.warning(
                    "OpenCRE API returned non-200 status",
                    status_code=response.status_code,
                    reason=response.reason,
                )
                return {'data': []}

            # Check if response is empty
            if not response.text or len(response.text.strip()) == 0:
                self.logger.warning("OpenCRE API returned empty response")
                return {'data': []}

            # Try to parse JSON
            try:
                data = response.json()
            except ValueError as json_err:
                self.logger.error(
                    "OpenCRE API returned invalid JSON (API likely deprecated)",
                    error=str(json_err),
                    content_preview=response.text[:200] if response.text else "None",
                    content_type=response.headers.get('content-type', 'unknown'),
                    recommendation="The public OpenCRE API has been deprecated. Consider running a local instance or using an alternative data source.",
                )
                return {'data': []}

            self.logger.info(
                "Fetched OpenCRE catalog",
                cre_count=len(data.get('data', [])),
            )

            return data

        except Exception as e:
            self.logger.error(
                "Failed to fetch OpenCRE data",
                error=str(e),
                error_type=type(e).__name__,
            )

            # Return empty structure
            return {'data': []}

    def transform_data(self, raw_data: dict) -> Generator[dict, None, None]:
        """
        Transform OpenCRE catalog to graph nodes and edges.

        Args:
            raw_data: OpenCRE catalog JSON from fetch_data()

        Yields:
            dict: OpenCRE node documents and link edges

        Note:
            OpenCRE structure (example):
            {
                "id": "123-456",
                "name": "Authentication",
                "description": "...",
                "links": [
                    {
                        "document": "ASVS",
                        "section": "2.1.1",
                        "ltype": "Same"
                    }
                ]
            }
        """
        cre_nodes = raw_data.get('data', [])

        for node in cre_nodes:
            # Extract CRE ID
            cre_id = node.get('id', '')
            if not cre_id:
                continue

            # Use cre_id as _key (normalize)
            _key = str(cre_id).replace('-', '_')

            # Extract basic fields
            name = node.get('name', '')
            description = node.get('description', '')
            cre_type = node.get('type', 'CRE')  # CRE, Standard, etc.

            # Extract external links
            links = node.get('links', [])

            # Group links by document type
            linked_standards = {}
            for link in links:
                doc_name = link.get('document', '')
                section = link.get('section', '')
                link_type = link.get('ltype', 'Same')  # Same, Contains, Related, etc.

                if doc_name not in linked_standards:
                    linked_standards[doc_name] = []

                linked_standards[doc_name].append({
                    'section': section,
                    'link_type': link_type,
                })

            # Yield OpenCRE node document
            yield {
                '_key': _key,
                'cre_id': cre_id,
                'name': name,
                'description': description,
                'cre_type': cre_type,
                'linked_standards': linked_standards,
            }

            # Yield edges to external standards
            # Note: This creates edges to other opencre_nodes or could link to specific standards
            # For now, we'll store the links in the document itself
            # In a more complete implementation, we'd create edges to NIST, ISO, etc. collections

            # If there are parent/child CRE relationships, create edges
            # (This would require parsing the 'links' for CRE-to-CRE relationships)
            for link in links:
                doc_name = link.get('document', '')
                link_type = link.get('ltype', '')

                # Only create edges for CRE-to-CRE links
                if doc_name == 'CRE' or cre_type == 'CRE':
                    linked_cre_id = link.get('id', '')
                    if linked_cre_id:
                        linked_key = str(linked_cre_id).replace('-', '_')

                        yield {
                            '_collection': 'opencre_links',
                            '_from': f'opencre_nodes/{_key}',
                            '_to': f'opencre_nodes/{linked_key}',
                            'link_type': link_type,
                            'source': 'opencre',
                        }

    def load_data(self, records: Generator[dict, None, None], collection_name: str = None, on_duplicate: str = "update") -> dict:
        """
        Load OpenCRE data into database.

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
        self.logger.info("Loading OpenCRE nodes", count=len(documents))
        doc_stats = super().load_data(
            iter(documents),
            collection_name='opencre_nodes',
            on_duplicate=on_duplicate,
        )

        # Load edges
        edge_stats = {'created': 0, 'updated': 0, 'errors': 0, 'total': 0}

        if edges:
            self.logger.info("Loading opencre_links edges", count=len(edges))
            edge_stats = super().load_data(
                iter(edges),
                collection_name='opencre_links',
                on_duplicate=on_duplicate,
            )

        # Combine statistics
        combined_stats = {
            'opencre_nodes': doc_stats,
            'edges': edge_stats,
            'total_created': doc_stats['created'] + edge_stats['created'],
            'total_updated': doc_stats['updated'] + edge_stats['updated'],
            'total_errors': doc_stats['errors'] + edge_stats['errors'],
        }

        return combined_stats

    def _get_primary_collection(self) -> str:
        """Get primary collection name."""
        return 'opencre_nodes'
