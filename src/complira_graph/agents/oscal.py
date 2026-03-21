"""
OSCAL (Open Security Controls Assessment Language) ingestion agent.

Fetches NIST 800-53 controls in OSCAL format and populates controls collection.
OSCAL provides machine-readable security and privacy control catalogs.

Data source: https://raw.githubusercontent.com/usnistgov/oscal-content/main/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json
Collections populated:
- oscal_controls (document collection)
"""

from typing import Generator
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_http_client

logger = structlog.get_logger()


class OSCALAgent(BaseIngestionAgent):
    """
    Agent for ingesting OSCAL (NIST 800-53) security controls.

    OSCAL provides a standardized format for security and privacy controls.
    """

    OSCAL_NIST_800_53_URL = "https://raw.githubusercontent.com/usnistgov/oscal-content/main/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json"

    def __init__(self, db):
        """Initialize OSCAL agent."""
        super().__init__(db)
        self.client = create_http_client(
            service_name="oscal_nist",
            calls_per_period=10,
            period_seconds=60,
            circuit_breaker=False,
            timeout=120.0,  # Large JSON file
        )

    def fetch_data(self) -> dict:
        """
        Fetch NIST 800-53 catalog in OSCAL format from GitHub.

        Returns:
            dict: OSCAL catalog JSON

        Raises:
            Exception: On fetch failure
        """
        self.logger.info("Fetching NIST 800-53 OSCAL catalog from GitHub", url=self.OSCAL_NIST_800_53_URL)

        response = self.client.get(self.OSCAL_NIST_800_53_URL)
        data = response.json()

        # Extract control count
        catalog = data.get('catalog', {})
        groups = catalog.get('groups', [])
        control_count = sum(len(group.get('controls', [])) for group in groups)

        self.logger.info(
            "Fetched OSCAL catalog",
            groups_count=len(groups),
            controls_count=control_count,
        )

        return data

    def transform_data(self, raw_data: dict) -> Generator[dict, None, None]:
        """
        Transform OSCAL catalog to graph nodes.

        Args:
            raw_data: OSCAL JSON catalog from fetch_data()

        Yields:
            dict: Control documents
        """
        catalog = raw_data.get('catalog', {})
        groups = catalog.get('groups', [])

        # Iterate through control families (groups)
        for group in groups:
            family_id = group.get('id', '')
            family_title = group.get('title', '')

            controls = group.get('controls', [])

            # Process each control
            for control in controls:
                yield from self._process_control(control, family_id, family_title)

    def _process_control(self, control: dict, family_id: str, family_title: str, parent_id: str = None) -> Generator[dict, None, None]:
        """
        Process a single control and its sub-controls recursively.

        Args:
            control: OSCAL control object
            family_id: Control family ID
            family_title: Control family title
            parent_id: Parent control ID (for enhancements)

        Yields:
            dict: Control document
        """
        control_id = control.get('id', '')
        if not control_id:
            return

        # Use control_id as _key (e.g., "ac-1", "ac-2.1")
        _key = control_id.replace('.', '_')

        # Extract title
        title = control.get('title', '')

        # Extract parameters
        params = control.get('params', [])
        parameters = []
        for param in params:
            parameters.append({
                'id': param.get('id', ''),
                'label': param.get('label', ''),
                'select': param.get('select', {}),
            })

        # Extract parts (statement, guidance, etc.)
        parts = control.get('parts', [])
        statement = ''
        guidance = ''
        related_controls = []

        for part in parts:
            part_name = part.get('name', '')
            part_prose = part.get('prose', '')

            if part_name == 'statement':
                statement = part_prose
            elif part_name == 'guidance':
                guidance = part_prose

        # Extract properties
        props = control.get('props', [])
        priority = None
        baseline_impact = []

        for prop in props:
            prop_name = prop.get('name', '')
            prop_value = prop.get('value', '')

            if prop_name == 'priority':
                priority = prop_value
            elif prop_name == 'baseline-impact':
                baseline_impact.append(prop_value)

        # Extract links (related controls)
        links = control.get('links', [])
        for link in links:
            rel = link.get('rel', '')
            href = link.get('href', '')

            if rel == 'related':
                # Extract control ID from href (e.g., "#ac-2" -> "ac-2")
                related_id = href.lstrip('#')
                related_controls.append(related_id)

        # Yield control document
        yield {
            '_key': _key,
            'control_id': control_id,
            'title': title,
            'family_id': family_id,
            'family_title': family_title,
            'parent_control_id': parent_id,
            'statement': statement,
            'guidance': guidance,
            'parameters': parameters,
            'priority': priority,
            'baseline_impact': baseline_impact,
            'related_controls': related_controls,
        }

        # Process control enhancements (sub-controls) recursively
        enhancements = control.get('controls', [])
        for enhancement in enhancements:
            yield from self._process_control(enhancement, family_id, family_title, parent_id=control_id)

    def load_data(self, records: Generator[dict, None, None], collection_name: str = None, on_duplicate: str = "update") -> dict:
        """
        Load OSCAL controls into database.

        Args:
            records: Generator from transform_data()
            collection_name: Ignored (always uses 'oscal_controls')
            on_duplicate: Action on duplicate _key

        Returns:
            dict: Import statistics
        """
        # Convert generator to list for counting
        documents = list(records)

        self.logger.info("Loading OSCAL controls", count=len(documents))

        stats = super().load_data(
            iter(documents),
            collection_name='oscal_controls',
            on_duplicate=on_duplicate,
        )

        return stats

    def _get_primary_collection(self) -> str:
        """Get primary collection name."""
        return 'oscal_controls'
