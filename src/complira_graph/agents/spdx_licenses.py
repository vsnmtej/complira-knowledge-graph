"""
SPDX License List ingestion agent.

Fetches SPDX license data and populates the licenses collection.
SPDX provides standardized identifiers for open source licenses.

Data source: https://raw.githubusercontent.com/spdx/license-list-data/main/json/licenses.json
Collections populated:
- licenses (document collection)
"""

from typing import Generator
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_http_client

logger = structlog.get_logger()


class SPDXLicensesAgent(BaseIngestionAgent):
    """
    Agent for ingesting SPDX (Software Package Data Exchange) license list.

    SPDX provides a standardized list of open source license identifiers.
    """

    SPDX_LICENSES_URL = "https://raw.githubusercontent.com/spdx/license-list-data/main/json/licenses.json"

    def __init__(self, db):
        """Initialize SPDX Licenses agent."""
        super().__init__(db)
        self.client = create_http_client(
            service_name="spdx_github",
            calls_per_period=10,
            period_seconds=60,
            circuit_breaker=False,
            timeout=30.0,
        )

    def fetch_data(self) -> dict:
        """
        Fetch SPDX license list from GitHub.

        Returns:
            dict: SPDX licenses JSON

        Raises:
            Exception: On fetch failure
        """
        self.logger.info("Fetching SPDX license list from GitHub", url=self.SPDX_LICENSES_URL)

        response = self.client.get(self.SPDX_LICENSES_URL)
        data = response.json()

        self.logger.info(
            "Fetched SPDX licenses",
            licenses_count=len(data.get('licenses', [])),
            version=data.get('licenseListVersion', 'unknown'),
        )

        return data

    def transform_data(self, raw_data: dict) -> Generator[dict, None, None]:
        """
        Transform SPDX license data to graph nodes.

        Args:
            raw_data: JSON data from fetch_data()

        Yields:
            dict: License documents
        """
        licenses = raw_data.get('licenses', [])

        for license_data in licenses:
            # Extract license ID (e.g., "Apache-2.0", "MIT")
            license_id = license_data.get('licenseId', '')
            if not license_id:
                continue

            # Use license_id as _key (may need normalization for special characters)
            # SPDX IDs are already URL-safe, but replace . and - with _
            _key = license_id.replace('.', '_').replace('-', '_').replace('+', '_plus')

            # Extract fields
            name = license_data.get('name', '')
            reference = license_data.get('reference', '')
            reference_number = license_data.get('referenceNumber', 0)
            details_url = license_data.get('detailsUrl', '')
            see_also = license_data.get('seeAlso', [])

            # License properties
            is_osi_approved = license_data.get('isOsiApproved', False)
            is_fsf_libre = license_data.get('isFsfLibre', False)
            is_deprecated = license_data.get('isDeprecatedLicenseId', False)

            # Yield license document
            yield {
                '_key': _key,
                'license_id': license_id,
                'name': name,
                'reference': reference,
                'reference_number': reference_number,
                'details_url': details_url,
                'see_also': see_also,
                'is_osi_approved': is_osi_approved,
                'is_fsf_libre': is_fsf_libre,
                'is_deprecated': is_deprecated,
            }

    def load_data(self, records: Generator[dict, None, None], collection_name: str = None, on_duplicate: str = "update") -> dict:
        """
        Load SPDX license data into database.

        Args:
            records: Generator from transform_data()
            collection_name: Ignored (always uses 'licenses')
            on_duplicate: Action on duplicate _key

        Returns:
            dict: Import statistics
        """
        # Convert generator to list for counting
        documents = list(records)

        self.logger.info("Loading SPDX licenses", count=len(documents))

        stats = super().load_data(
            iter(documents),
            collection_name='licenses',
            on_duplicate=on_duplicate,
        )

        return stats

    def _get_primary_collection(self) -> str:
        """Get primary collection name."""
        return 'licenses'
