"""
CPE (Common Platform Enumeration) Dictionary ingestion agent.

Fetches CPE entries from NVD CPE Dictionary API.
CPE is a standardized method for naming software, hardware, and OS platforms.

Data source: https://services.nvd.nist.gov/rest/json/cpes/2.0
API Documentation: https://nvd.nist.gov/developers/products

Collections populated:
- cpe_entries (document collection) - CPE Dictionary entries
- affects (edges from vulnerabilities to CPE entries)
"""

from typing import Generator
from datetime import datetime, timedelta
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_http_client
from ..utils.keys import normalize_cpe

logger = structlog.get_logger()


class CPEAgent(BaseIngestionAgent):
    """
    Agent for ingesting CPE (Common Platform Enumeration) Dictionary from NVD.

    CPE provides standardized naming for software products, operating systems, and hardware devices.
    ~1M+ CPE entries in the NVD CPE Dictionary.
    """

    NVD_CPE_API_URL = "https://services.nvd.nist.gov/rest/json/cpes/2.0"

    def __init__(self, db, api_key: str = None, start_date: datetime = None, end_date: datetime = None):
        """
        Initialize CPE agent.

        Args:
            db: ArangoDB database instance
            api_key: NVD API key (optional, increases rate limit from 5 to 50 req/30s)
            start_date: Fetch CPEs modified after this date (default: last 30 days)
            end_date: Fetch CPEs modified before this date (default: now)
        """
        super().__init__(db)

        self.api_key = api_key

        # Default to last 30 days if no dates specified
        if end_date is None:
            end_date = datetime.utcnow()
        if start_date is None:
            start_date = end_date - timedelta(days=30)

        self.start_date = start_date
        self.end_date = end_date

        # Create HTTP client with appropriate rate limiting
        # NVD API: 5 requests per 30 seconds (public) or 50 requests per 30 seconds (with API key)
        rate_limit = 50 if api_key else 5

        self.client = create_http_client(
            service_name="nvd_cpe",
            calls_per_period=rate_limit,
            period_seconds=30,
            circuit_breaker=True,
            timeout=60.0,
        )

        self.logger.info(
            "CPE agent initialized",
            rate_limit=f"{rate_limit} req/30s",
            has_api_key=bool(api_key),
            date_range=f"{start_date.date()} to {end_date.date()}",
        )

    def fetch_data(self) -> Generator[dict, None, None]:
        """
        Fetch CPE entries from NVD CPE Dictionary API.

        Yields:
            dict: Raw CPE product data from NVD API

        Note:
            NVD CPE API returns paginated results (max 10,000 results per request).
            Uses lastModStartDate/lastModEndDate filters for incremental updates.
        """
        self.logger.info(
            "Fetching CPE entries from NVD",
            start_date=self.start_date.date(),
            end_date=self.end_date.date(),
        )

        start_index = 0
        results_per_page = 2000  # Max allowed by NVD API
        total_results = None
        fetched_count = 0

        while True:
            # Build query parameters
            params = {
                "resultsPerPage": results_per_page,
                "startIndex": start_index,
                "lastModStartDate": self.start_date.strftime("%Y-%m-%dT%H:%M:%S.000"),
                "lastModEndDate": self.end_date.strftime("%Y-%m-%dT%H:%M:%S.000"),
            }

            # Add API key if provided
            headers = {}
            if self.api_key:
                headers["apiKey"] = self.api_key

            try:
                self.logger.debug(
                    "Fetching CPE page",
                    start_index=start_index,
                    results_per_page=results_per_page,
                )

                response = self.client.get(
                    self.NVD_CPE_API_URL,
                    params=params,
                    headers=headers,
                )

                if response.status_code != 200:
                    self.logger.error(
                        "NVD CPE API returned non-200 status",
                        status_code=response.status_code,
                        reason=response.reason,
                    )
                    break

                data = response.json()

                # Get total results count on first page
                if total_results is None:
                    total_results = data.get("totalResults", 0)
                    self.logger.info(
                        "NVD CPE API total results",
                        total_results=total_results,
                    )

                # Extract CPE products from response
                products = data.get("products", [])

                if not products:
                    self.logger.info("No more CPE products to fetch")
                    break

                # Yield each product
                for product in products:
                    fetched_count += 1
                    yield product

                self.logger.debug(
                    "Fetched CPE page",
                    page_size=len(products),
                    total_fetched=fetched_count,
                    total_results=total_results,
                )

                # Check if we've fetched all results
                if fetched_count >= total_results:
                    break

                # Move to next page
                start_index += results_per_page

            except Exception as e:
                self.logger.error(
                    "Failed to fetch CPE data from NVD",
                    start_index=start_index,
                    error=str(e),
                )
                break

        self.logger.info(
            "CPE fetch complete",
            total_fetched=fetched_count,
            total_results=total_results,
        )

    def transform_data(self, raw_data: Generator[dict, None, None]) -> Generator[dict, None, None]:
        """
        Transform NVD CPE products to graph documents.

        Args:
            raw_data: Generator of raw CPE product data from fetch_data()

        Yields:
            dict: Transformed CPE entry documents for cpe_entries collection
        """
        self.logger.info("Transforming CPE data")

        cpe_count = 0

        for product in raw_data:
            try:
                cpe = product.get("cpe", {})

                # Extract CPE URI (e.g., "cpe:2.3:a:vendor:product:version:...")
                cpe_name = cpe.get("cpeName", "")

                if not cpe_name or not cpe_name.startswith("cpe:"):
                    continue

                # Generate _key from CPE name
                _key = normalize_cpe(cpe_name)

                # Extract metadata
                cpe_name_id = cpe.get("cpeNameId")  # UUID for this CPE
                deprecated = cpe.get("deprecated", False)

                # Extract titles (multilingual)
                titles = {}
                title_list = cpe.get("titles", [])
                for title_obj in title_list:
                    lang = title_obj.get("lang", "en")
                    title = title_obj.get("title", "")
                    if title:
                        titles[lang] = title

                # Extract references
                refs = []
                ref_list = cpe.get("refs", [])
                for ref in ref_list:
                    ref_url = ref.get("ref", "")
                    ref_type = ref.get("type", "")
                    if ref_url:
                        refs.append({
                            "url": ref_url,
                            "type": ref_type,
                        })

                # Extract deprecation info
                deprecation_date = None
                deprecated_by = []
                if deprecated:
                    deprecation_date = cpe.get("deprecationDate")
                    deprecated_by_list = cpe.get("deprecatedBy", [])
                    for dep_cpe in deprecated_by_list:
                        dep_cpe_name = dep_cpe.get("cpeName", "")
                        if dep_cpe_name:
                            deprecated_by.append(dep_cpe_name)

                # Parse CPE name components
                # CPE 2.3 format: cpe:2.3:part:vendor:product:version:update:edition:language:sw_edition:target_sw:target_hw:other
                cpe_parts = cpe_name.split(":")
                part = cpe_parts[2] if len(cpe_parts) > 2 else None  # a=application, o=os, h=hardware
                vendor = cpe_parts[3] if len(cpe_parts) > 3 else None
                product_name = cpe_parts[4] if len(cpe_parts) > 4 else None
                version = cpe_parts[5] if len(cpe_parts) > 5 else None

                # Last modified date
                last_modified = cpe.get("lastModified")
                if last_modified:
                    last_modified = datetime.fromisoformat(last_modified.replace("Z", "+00:00")).isoformat()

                # Yield CPE entry document
                yield {
                    "_key": _key,
                    "cpe_name": cpe_name,
                    "cpe_name_id": cpe_name_id,
                    "part": part,
                    "vendor": vendor,
                    "product": product_name,
                    "version": version,
                    "deprecated": deprecated,
                    "deprecation_date": deprecation_date,
                    "deprecated_by": deprecated_by if deprecated_by else None,
                    "titles": titles if titles else None,
                    "references": refs if refs else None,
                    "last_modified": last_modified,
                    "source": "nvd",
                }

                cpe_count += 1

            except Exception as e:
                self.logger.warning(
                    "Failed to transform CPE product",
                    error=str(e),
                )
                continue

        self.logger.info("CPE transformation complete", total_cpes=cpe_count)

    def _get_primary_collection(self) -> str:
        """Get primary collection name."""
        return "cpe_entries"
