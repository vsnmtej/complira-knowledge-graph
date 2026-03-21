"""
endoflife.date ingestion agent.

Fetches end-of-life (EOL) data for products, frameworks, and libraries.
Tracks support lifecycle dates for prioritizing vulnerability remediation.

Data source: https://endoflife.date/api/
Collections populated:
- components (updates existing components with EOL data)
- Package health data with EOL status
"""

from typing import Generator
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_http_client
from ..utils.transforms import safe_date_parse

logger = structlog.get_logger()


class EndOfLifeAgent(BaseIngestionAgent):
    """
    Agent for ingesting endoflife.date EOL tracking data.

    endoflife.date provides end-of-support dates for software products.
    """

    EOL_API_BASE = "https://endoflife.date/api"

    def __init__(self, db):
        """Initialize endoflife.date agent."""
        super().__init__(db)
        self.client = create_http_client(
            service_name="endoflife_date",
            calls_per_period=30,
            period_seconds=60,
            circuit_breaker=False,
            timeout=30.0,
        )

    def fetch_data(self) -> dict:
        """
        Fetch EOL data for all tracked products.

        Returns:
            dict: EOL data for all products

        Workflow:
            1. Fetch list of all products from /api/all.json
            2. For each product, fetch version-specific EOL data
        """
        self.logger.info("Fetching product list from endoflife.date")

        # Fetch all products
        all_products = []

        try:
            response = self.client.get(f"{self.EOL_API_BASE}/all.json")
            products = response.json()

            self.logger.info("Fetched product list", product_count=len(products))

            # Fetch EOL data for each product
            for product_id in products:
                try:
                    product_response = self.client.get(f"{self.EOL_API_BASE}/{product_id}.json")
                    product_data = product_response.json()

                    all_products.append({
                        'product_id': product_id,
                        'cycles': product_data,
                    })

                    self.logger.debug(
                        "Fetched product EOL data",
                        product=product_id,
                        cycles=len(product_data),
                    )

                except Exception as e:
                    self.logger.warning(
                        "Failed to fetch product EOL data",
                        product=product_id,
                        error=str(e),
                    )

        except Exception as e:
            self.logger.error(
                "Failed to fetch product list from endoflife.date",
                error=str(e),
            )
            return {}

        self.logger.info(
            "Fetched all EOL data",
            total_products=len(all_products),
        )

        return {'products': all_products}

    def transform_data(self, raw_data: dict) -> Generator[dict, None, None]:
        """
        Transform endoflife.date data to graph nodes.

        Args:
            raw_data: EOL data from fetch_data()

        Yields:
            dict: EOL documents

        Cycle structure:
            {
                "cycle": "1.15",
                "releaseDate": "2020-08-11",
                "eol": "2021-08-15",
                "latest": "1.15.15",
                "latestReleaseDate": "2021-08-04",
                "lts": false,
                "support": "2021-02-15"
            }
        """
        products = raw_data.get('products', [])

        for product in products:
            product_id = product.get('product_id', '')
            cycles = product.get('cycles', [])

            if not product_id:
                continue

            for cycle in cycles:
                # Extract cycle identifier (version)
                cycle_version = cycle.get('cycle', '')
                if not cycle_version:
                    continue

                # Create unique key
                _key = f"{product_id}_{cycle_version}".replace('.', '_').replace('-', '_')

                # Extract dates
                release_date = safe_date_parse(cycle.get('releaseDate'))
                eol_date = safe_date_parse(cycle.get('eol'))
                support_end_date = safe_date_parse(cycle.get('support'))
                latest_release_date = safe_date_parse(cycle.get('latestReleaseDate'))

                # Extract metadata
                latest_version = cycle.get('latest', '')
                is_lts = cycle.get('lts', False)
                is_active = cycle.get('active', True)

                # Determine EOL status
                eol_status = 'active'
                if eol_date:
                    from datetime import datetime
                    if datetime.now() > eol_date:
                        eol_status = 'end_of_life'
                    elif support_end_date and datetime.now() > support_end_date:
                        eol_status = 'end_of_support'

                # Yield EOL document
                yield {
                    '_key': _key,
                    'product_id': product_id,
                    'cycle_version': cycle_version,
                    'latest_version': latest_version,
                    'release_date': release_date.isoformat() if release_date else None,
                    'eol_date': eol_date.isoformat() if eol_date else None,
                    'support_end_date': support_end_date.isoformat() if support_end_date else None,
                    'latest_release_date': latest_release_date.isoformat() if latest_release_date else None,
                    'is_lts': is_lts,
                    'is_active': is_active,
                    'eol_status': eol_status,
                    'source': 'endoflife_date',
                }

    def load_data(self, records: Generator[dict, None, None], collection_name: str = None, on_duplicate: str = "update") -> dict:
        """
        Load endoflife.date data into database.

        Args:
            records: Generator from transform_data()
            collection_name: Ignored (uses 'package_health' to enrich components)
            on_duplicate: Action on duplicate _key

        Returns:
            dict: Import statistics
        """
        # Convert generator to list
        documents = list(records)

        self.logger.info("Loading EOL data", count=len(documents))

        stats = super().load_data(
            iter(documents),
            collection_name='package_health',
            on_duplicate=on_duplicate,
        )

        return stats

    def _get_primary_collection(self) -> str:
        """Get primary collection name."""
        return 'package_health'
