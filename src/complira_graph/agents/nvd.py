"""
NVD (National Vulnerability Database) ingestion agent.

Fetches CVE data from NVD API 2.0 and populates vulnerabilities collection.
NVD is the primary authoritative source for CVE vulnerability data.

Data source: https://services.nvd.nist.gov/rest/json/cves/2.0
Collections populated:
- vulnerabilities (document collection)
- has_weakness (edges to CWE weaknesses)
- affects (edges to CPE entries)

Special requirements:
- Circuit breaker (NVD API known for 503 errors)
- Rate limiting: 50 requests/30s with API key, 5 requests/30s without
- Incremental updates with checkpoint support
"""

from typing import Generator
from datetime import datetime, timedelta
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_http_client
from ..utils.keys import normalize_cve_id, normalize_cwe_id
from ..utils.transforms import safe_date_parse

logger = structlog.get_logger()


class NVDAgent(BaseIngestionAgent):
    """
    Agent for ingesting NVD (National Vulnerability Database) CVE data.

    NVD provides comprehensive vulnerability data with CVSS scores, CWE mappings, and CPE matches.
    """

    # Enable checkpoint/resume support for long-running fetches
    supports_checkpointing = True
    checkpoint_interval = 50  # Save every 50 pages (50 * 2000 = 100k CVEs)

    NVD_API_BASE = "https://services.nvd.nist.gov/rest/json/cves/2.0"

    def __init__(self, db, api_key: str = None):
        """
        Initialize NVD agent.

        Args:
            db: ArangoDB database instance
            api_key: NVD API key (optional but recommended for higher rate limits)
        """
        super().__init__(db)
        self.api_key = api_key or self.settings.NVD_API_KEY

        # Rate limit depends on API key presence
        rate_limit = 50 if self.api_key else 5
        period = 30

        self.client = create_http_client(
            service_name="nvd_nist",
            calls_per_period=rate_limit,
            period_seconds=period,
            circuit_breaker=True,  # CRITICAL: NVD is unreliable
            timeout=30.0,
        )

        self.logger.info(
            "NVD agent initialized",
            has_api_key=bool(self.api_key),
            rate_limit=f"{rate_limit} req/{period}s",
        )

    def fetch_data(self, start_date: datetime = None, end_date: datetime = None) -> list[dict]:
        """
        Fetch CVE data from NVD API 2.0.

        Args:
            start_date: Start date for incremental updates (lastModStartDate)
            end_date: End date for incremental updates (lastModEndDate)

        Returns:
            list[dict]: CVE records from NVD

        Raises:
            Exception: On fetch failure (after retries and circuit breaker)
        """
        # Auto-detect initial seed vs incremental update
        if not start_date:
            # Check if vulnerabilities collection is empty (initial seed)
            vuln_count = self.db.collection("vulnerabilities").count()
            if vuln_count == 0:
                # Initial seed: fetch all historical data from 120 days ago (NVD API limit)
                # Note: NVD API v2.0 has a 120-day lookback limit per request
                # For full historical data, we'll need to make multiple requests
                start_date = datetime.utcnow() - timedelta(days=120)
                self.logger.info("Empty database detected, fetching full historical dataset (120-day window)")
            else:
                # Incremental update: fetch last 7 days
                start_date = datetime.utcnow() - timedelta(days=7)
                self.logger.info("Existing data found, performing incremental update (last 7 days)")

        if not end_date:
            end_date = datetime.utcnow()

        # Check for checkpoint to resume from
        start_index = 0
        checkpoint = self._load_checkpoint()
        if checkpoint:
            start_index = checkpoint.get("start_index", 0)
            self.logger.info(
                "Resuming from checkpoint",
                start_index=start_index,
                total_fetched=checkpoint.get("total", 0),
            )

        self.logger.info(
            "Fetching CVE data from NVD",
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )

        all_vulnerabilities = []
        results_per_page = 2000  # Max allowed by NVD API
        page_count = 0

        while True:
            # Build query parameters
            params = {
                "resultsPerPage": results_per_page,
                "startIndex": start_index,
                "lastModStartDate": start_date.strftime("%Y-%m-%dT%H:%M:%S.000"),
                "lastModEndDate": end_date.strftime("%Y-%m-%dT%H:%M:%S.000"),
            }

            # Add API key if available
            headers = {}
            if self.api_key:
                headers["apiKey"] = self.api_key

            self.logger.debug(
                "Fetching NVD page",
                start_index=start_index,
                results_per_page=results_per_page,
            )

            # Fetch page (circuit breaker + rate limiting applied automatically)
            response = self.client.get(
                self.NVD_API_BASE,
                params=params,
                headers=headers,
            )

            data = response.json()

            # Extract vulnerabilities
            vulnerabilities = data.get("vulnerabilities", [])
            all_vulnerabilities.extend(vulnerabilities)

            # Check if more pages exist
            total_results = data.get("totalResults", 0)
            page_count += 1

            self.logger.debug(
                "Fetched NVD page",
                page_size=len(vulnerabilities),
                total_fetched=len(all_vulnerabilities),
                total_available=total_results,
            )

            # Save checkpoint periodically
            if page_count % self.checkpoint_interval == 0:
                self._save_checkpoint({
                    "start_index": start_index + results_per_page,  # Next start_index
                    "total": len(all_vulnerabilities),
                    "total_results": total_results,
                })

            if len(all_vulnerabilities) >= total_results:
                break

            start_index += results_per_page

        self.logger.info(
            "Fetched all CVE data from NVD",
            total_vulnerabilities=len(all_vulnerabilities),
        )

        return all_vulnerabilities

    def transform_data(self, raw_data: list[dict]) -> Generator[dict, None, None]:
        """
        Transform NVD CVE data to graph nodes and edges.

        Args:
            raw_data: List of CVE records from fetch_data()

        Yields:
            dict: CVE documents and relationship edges
        """
        for vuln_wrapper in raw_data:
            cve = vuln_wrapper.get("cve", {})

            # Extract CVE ID
            cve_id = cve.get("id", "")
            if not cve_id:
                continue

            _key = normalize_cve_id(cve_id)

            # Extract descriptions
            descriptions = cve.get("descriptions", [])
            description = ""
            for desc in descriptions:
                if desc.get("lang") == "en":
                    description = desc.get("value", "")
                    break

            # Extract published/modified dates
            published = safe_date_parse(cve.get("published"))
            last_modified = safe_date_parse(cve.get("lastModified"))

            # Extract CVSS scores (v2, v3.x)
            metrics = cve.get("metrics", {})

            cvss_v2_score = None
            cvss_v2_vector = None
            cvss_v2_severity = None
            cvss_v2_data = metrics.get("cvssMetricV2", [])
            if cvss_v2_data:
                cvss_v2 = cvss_v2_data[0].get("cvssData", {})
                cvss_v2_score = cvss_v2.get("baseScore")
                cvss_v2_vector = cvss_v2.get("vectorString")
                cvss_v2_severity = cvss_v2_data[0].get("baseSeverity")

            cvss_v3_score = None
            cvss_v3_vector = None
            cvss_v3_severity = None
            # Try v3.1 first, then v3.0
            for version in ["cvssMetricV31", "cvssMetricV30"]:
                cvss_v3_data = metrics.get(version, [])
                if cvss_v3_data:
                    cvss_v3 = cvss_v3_data[0].get("cvssData", {})
                    cvss_v3_score = cvss_v3.get("baseScore")
                    cvss_v3_vector = cvss_v3.get("vectorString")
                    cvss_v3_severity = cvss_v3.get("baseSeverity")
                    break

            # Extract CWE IDs
            weaknesses = cve.get("weaknesses", [])
            cwe_ids = []
            for weakness in weaknesses:
                descriptions = weakness.get("description", [])
                for desc in descriptions:
                    value = desc.get("value", "")
                    if value.startswith("CWE-"):
                        cwe_ids.append(value)

            # Extract references
            references = cve.get("references", [])
            reference_list = []
            for ref in references:
                reference_list.append({
                    "url": ref.get("url", ""),
                    "source": ref.get("source", ""),
                    "tags": ref.get("tags", []),
                })

            # Extract CPE matches (vulnerable configurations)
            configurations = cve.get("configurations", [])
            cpe_matches = []
            for config in configurations:
                nodes = config.get("nodes", [])
                for node in nodes:
                    cpe_match = node.get("cpeMatch", [])
                    for match in cpe_match:
                        if match.get("vulnerable", False):
                            cpe_matches.append({
                                "criteria": match.get("criteria", ""),
                                "match_criteria_id": match.get("matchCriteriaId", ""),
                                "version_start_including": match.get("versionStartIncluding"),
                                "version_end_including": match.get("versionEndIncluding"),
                                "version_start_excluding": match.get("versionStartExcluding"),
                                "version_end_excluding": match.get("versionEndExcluding"),
                            })

            # Yield CVE document
            yield {
                "_key": _key,
                "vulnerability_id": cve_id,  # REQUIRED field in schema
                "cve_id": cve_id,
                "description": description,
                "published": published.isoformat() if published else None,
                "last_modified": last_modified.isoformat() if last_modified else None,
                "cvss_v2_score": cvss_v2_score,
                "cvss_v2_vector": cvss_v2_vector,
                "cvss_v2_severity": cvss_v2_severity,
                "cvss_v3_score": cvss_v3_score,
                "cvss_v3_vector": cvss_v3_vector,
                "cvss_v3_severity": cvss_v3_severity,
                "cwe_ids": cwe_ids,
                "references": reference_list,
                "cpe_matches": cpe_matches,
                "source": "nvd",
            }

            # Yield edges to CWE weaknesses
            for cwe_id in cwe_ids:
                cwe_key = normalize_cwe_id(cwe_id)
                yield {
                    "_collection": "has_weakness",
                    "_from": f"vulnerabilities/{_key}",
                    "_to": f"weaknesses/{cwe_key}",
                    "source": "nvd",
                }

    def load_data(self, records: Generator[dict, None, None], collection_name: str = None, on_duplicate: str = "update") -> dict:
        """
        Load NVD data into database.

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
            if "_collection" in record:
                # It's an edge
                record.pop("_collection")
                edges.append(record)
            else:
                # It's a document
                documents.append(record)

        # Load documents
        self.logger.info("Loading NVD vulnerabilities", count=len(documents))
        doc_stats = super().load_data(
            iter(documents),
            collection_name="vulnerabilities",
            on_duplicate=on_duplicate,
        )

        # Load edges
        edge_stats = {"created": 0, "updated": 0, "errors": 0, "total": 0}

        if edges:
            self.logger.info("Loading has_weakness edges", count=len(edges))
            edge_stats = super().load_data(
                iter(edges),
                collection_name="has_weakness",
                on_duplicate=on_duplicate,
            )

        # Combine statistics
        combined_stats = {
            "vulnerabilities": doc_stats,
            "edges": edge_stats,
            "total_created": doc_stats["created"] + edge_stats["created"],
            "total_updated": doc_stats["updated"] + edge_stats["updated"],
            "total_errors": doc_stats["errors"] + edge_stats["errors"],
        }

        return combined_stats

    def _get_primary_collection(self) -> str:
        """Get primary collection name."""
        return "vulnerabilities"
