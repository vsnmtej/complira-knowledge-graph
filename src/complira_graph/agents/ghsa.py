"""
GHSA (GitHub Security Advisories) ingestion agent.

Fetches vulnerability data from GitHub Security Advisories.
GHSA provides curated security advisories for GitHub repositories and packages.

Data source: GitHub Advisory Database (https://github.com/github/advisory-database)
Alternative: GitHub GraphQL API (requires authentication)

Collections populated:
- vulnerabilities (document collection)
- has_weakness (edges to CWE weaknesses)
- affects (edges to components via PURL)
"""

from typing import Generator
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_http_client
from ..utils.keys import normalize_cve_id, normalize_cwe_id
from ..utils.transforms import safe_date_parse

logger = structlog.get_logger()


class GHSAAgent(BaseIngestionAgent):
    """
    Agent for ingesting GHSA (GitHub Security Advisories) data.

    GHSA provides curated vulnerability advisories from GitHub's security team.
    """

    # Enable checkpoint/resume support for long-running fetches
    supports_checkpointing = True
    checkpoint_interval = 100  # Save every 100 pages

    # Batch processing configuration (to avoid OOM)
    BATCH_SIZE = 50  # Process 50 pages at a time (5,000 advisories per batch)

    # GitHub Advisory Database API endpoint
    # Note: For production, consider cloning the advisory-database repo and parsing JSON files
    GHSA_API_BASE = "https://api.github.com"

    def __init__(self, db, github_token: str = None):
        """
        Initialize GHSA agent.

        Args:
            db: ArangoDB database instance
            github_token: GitHub personal access token (optional, increases rate limits)
        """
        super().__init__(db)
        self.github_token = github_token or getattr(self.settings, 'GITHUB_TOKEN', None)

        # GitHub rate limits: 60 req/hr unauthenticated, 5000 req/hr authenticated
        rate_limit = 80 if self.github_token else 10
        period = 60

        self.client = create_http_client(
            service_name="github_api",
            calls_per_period=rate_limit,
            period_seconds=period,
            circuit_breaker=False,
            timeout=30.0,
        )

        self.logger.info(
            "GHSA agent initialized",
            has_token=bool(self.github_token),
            rate_limit=f"{rate_limit} req/{period}s",
        )

    def run(self) -> dict:
        """
        Override run() to process GHSA data in batches (to avoid OOM).

        Fetches, transforms, and loads advisories in batches of BATCH_SIZE pages
        instead of loading all 1.39M advisories into memory at once.

        Returns:
            dict: Combined statistics from all batches
        """
        # Get last update timestamp for incremental updates
        last_updated = self._get_last_update_timestamp()

        # Check for checkpoint to resume from
        start_page = 1
        checkpoint = self._load_checkpoint()
        if checkpoint:
            start_page = checkpoint.get("page", 1)
            self.logger.info(
                "Resuming from checkpoint",
                start_page=start_page,
                total_processed=checkpoint.get("total_processed", 0),
            )

        if last_updated:
            self.logger.info(
                "Running GHSA agent (incremental update)",
                updated_since=last_updated.isoformat(),
            )
        else:
            self.logger.info("Running GHSA agent (full initial sync)")

        # Initialize cumulative statistics
        total_stats = {
            "documents_created": 0,
            "documents_updated": 0,
            "edges_created": 0,
            "edges_updated": 0,
            "total_processed": 0,
            "errors": 0,
        }

        page = start_page
        batch_count = 0

        while True:
            batch_count += 1
            self.logger.info(
                "Processing batch",
                batch=batch_count,
                starting_page=page,
                batch_size=self.BATCH_SIZE,
            )

            # Fetch batch of pages
            batch_advisories = self._fetch_batch(page, last_updated)

            if not batch_advisories:
                self.logger.info("No more advisories to fetch")
                break

            # Transform batch
            transformed = self.transform_data(batch_advisories)

            # Load batch
            batch_stats = self._load_batch(transformed)

            # Update cumulative statistics
            total_stats["documents_created"] += batch_stats.get("vulnerabilities", {}).get("created", 0)
            total_stats["documents_updated"] += batch_stats.get("vulnerabilities", {}).get("updated", 0)
            total_stats["edges_created"] += batch_stats.get("edges", {}).get("created", 0)
            total_stats["edges_updated"] += batch_stats.get("edges", {}).get("updated", 0)
            total_stats["total_processed"] += len(batch_advisories)
            total_stats["errors"] += batch_stats.get("vulnerabilities", {}).get("errors", 0) + batch_stats.get("edges", {}).get("errors", 0)

            self.logger.info(
                "Batch processed",
                batch=batch_count,
                advisories_in_batch=len(batch_advisories),
                total_processed=total_stats["total_processed"],
                docs_created=total_stats["documents_created"],
            )

            # Save checkpoint
            self._save_checkpoint({
                "page": page + len(batch_advisories) // 100,  # Approximate next page
                "total_processed": total_stats["total_processed"],
            })

            # Check if we got a partial batch (end of data)
            if len(batch_advisories) < (self.BATCH_SIZE * 100):
                break

            page += self.BATCH_SIZE

        self.logger.info(
            "GHSA agent complete",
            total_processed=total_stats["total_processed"],
            documents_created=total_stats["documents_created"],
            edges_created=total_stats["edges_created"],
        )

        # Clear checkpoint on successful completion
        self._clear_checkpoint()

        return total_stats

    def _fetch_batch(self, start_page: int, last_updated=None) -> list[dict]:
        """
        Fetch a batch of GHSA advisories (BATCH_SIZE pages).

        Args:
            start_page: Starting page number
            last_updated: Timestamp for incremental updates (optional)

        Returns:
            list[dict]: Advisories from this batch (max BATCH_SIZE * 100 advisories)
        """
        batch_advisories = []
        page = start_page
        per_page = 100

        for _ in range(self.BATCH_SIZE):
            headers = {
                "Accept": "application/vnd.github+json",
            }
            if self.github_token:
                headers["Authorization"] = f"Bearer {self.github_token}"

            params = {
                "per_page": per_page,
                "page": page,
            }

            if last_updated:
                params["updated"] = f">{last_updated.isoformat()}"

            try:
                response = self.client.get(
                    f"{self.GHSA_API_BASE}/advisories",
                    headers=headers,
                    params=params,
                )

                advisories = response.json()

                if not advisories:
                    break

                batch_advisories.extend(advisories)

                # Check if this is the last page
                if len(advisories) < per_page:
                    break

                page += 1

            except Exception as e:
                self.logger.error(
                    "Failed to fetch GHSA page",
                    page=page,
                    error=str(e),
                )
                break

        return batch_advisories

    def _load_batch(self, records: Generator[dict, None, None]) -> dict:
        """
        Load a batch of transformed records into database.

        Args:
            records: Generator from transform_data()

        Returns:
            dict: Batch statistics
        """
        # Separate documents from edges
        documents = []
        edges_by_collection = {
            "has_weakness": [],
            "aliases": [],
        }

        for record in records:
            if "_collection" in record:
                collection = record.pop("_collection")
                if collection in edges_by_collection:
                    edges_by_collection[collection].append(record)
            else:
                documents.append(record)

        # Load documents
        doc_stats = {"created": 0, "updated": 0, "errors": 0, "total": 0}
        if documents:
            doc_stats = super(GHSAAgent, self).load_data(
                iter(documents),
                collection_name="vulnerabilities",
                on_duplicate="update",
            )

        # Load edges
        total_edge_stats = {"created": 0, "updated": 0, "errors": 0, "total": 0}
        for collection, edges in edges_by_collection.items():
            if not edges:
                continue

            edge_stats = super(GHSAAgent, self).load_data(
                iter(edges),
                collection_name=collection,
                on_duplicate="update",
            )

            total_edge_stats["created"] += edge_stats["created"]
            total_edge_stats["updated"] += edge_stats["updated"]
            total_edge_stats["errors"] += edge_stats["errors"]
            total_edge_stats["total"] += edge_stats["total"]

        return {
            "vulnerabilities": doc_stats,
            "edges": total_edge_stats,
        }

    def fetch_data(self) -> list[dict]:
        """
        Fetch security advisories from GitHub API with incremental updates.

        Returns:
            list[dict]: GHSA advisory records (only new/updated since last run)

        Note:
            Uses updated_since parameter to fetch only new advisories.
            Supports resume from last checkpoint (page number) within a single run.
        """
        # Get last update timestamp from database for incremental updates
        last_updated = self._get_last_update_timestamp()

        # Check for checkpoint to resume from (crash recovery)
        start_page = 1
        if self._checkpoint:
            start_page = self._checkpoint.get("page", 1) + 1  # Resume from next page
            self.logger.info(
                "Resuming from checkpoint",
                start_page=start_page,
                total_fetched=self._checkpoint.get("total", 0),
            )

        if last_updated:
            self.logger.info(
                "Fetching GHSA advisories (incremental update)",
                updated_since=last_updated.isoformat(),
            )
        else:
            self.logger.info("Fetching GHSA advisories (full initial sync)")

        all_advisories = []
        page = start_page
        per_page = 100

        while True:
            # Build headers
            headers = {
                "Accept": "application/vnd.github+json",
            }
            if self.github_token:
                headers["Authorization"] = f"Bearer {self.github_token}"

            params = {
                "per_page": per_page,
                "page": page,
            }

            # Add incremental update filter (only fetch advisories updated after last run)
            if last_updated:
                params["updated"] = f">{last_updated.isoformat()}"

            self.logger.debug(
                "Fetching GHSA page",
                page=page,
                per_page=per_page,
                incremental=bool(last_updated),
            )

            try:
                response = self.client.get(
                    f"{self.GHSA_API_BASE}/advisories",
                    headers=headers,
                    params=params,
                )

                advisories = response.json()

                if not advisories:
                    break

                all_advisories.extend(advisories)

                self.logger.debug(
                    "Fetched GHSA page",
                    page=page,
                    count=len(advisories),
                    total=len(all_advisories),
                )

                # Save checkpoint periodically (every checkpoint_interval pages)
                if page % self.checkpoint_interval == 0:
                    self._save_checkpoint({
                        "page": page,
                        "total": len(all_advisories),
                    })

                # Check if more pages exist
                if len(advisories) < per_page:
                    break

                page += 1

            except Exception as e:
                self.logger.error(
                    "Failed to fetch GHSA page",
                    page=page,
                    error=str(e),
                )
                break

        self.logger.info(
            "Fetched all GHSA advisories",
            total=len(all_advisories),
        )

        return all_advisories

    def transform_data(self, raw_data: list[dict]) -> Generator[dict, None, None]:
        """
        Transform GHSA data to graph nodes and edges.

        Args:
            raw_data: List of GHSA advisory records from fetch_data()

        Yields:
            dict: Vulnerability documents and relationship edges
        """
        for advisory in raw_data:
            # Extract GHSA ID
            ghsa_id = advisory.get("ghsa_id", "")
            if not ghsa_id:
                continue

            # Use GHSA ID as _key (e.g., "GHSA_xxxx_yyyy_zzzz")
            _key = ghsa_id.replace("-", "_")

            # Extract CVE ID if available
            cve_id = advisory.get("cve_id")

            # Extract basic fields
            summary = advisory.get("summary", "")
            description = advisory.get("description", "")
            severity = advisory.get("severity", "")  # low, moderate, high, critical

            # Extract dates
            published = safe_date_parse(advisory.get("published_at"))
            updated = safe_date_parse(advisory.get("updated_at"))
            withdrawn = safe_date_parse(advisory.get("withdrawn_at"))

            # Extract CVSS score
            cvss = advisory.get("cvss", {})
            cvss_score = cvss.get("score")
            cvss_vector = cvss.get("vector_string")

            # Extract CWE IDs
            cwes = advisory.get("cwes", [])
            cwe_ids = []
            for cwe in cwes:
                cwe_id = cwe.get("cwe_id", "")
                if cwe_id:
                    cwe_ids.append(cwe_id)

            # Extract affected packages/ecosystems
            vulnerabilities = advisory.get("vulnerabilities", [])
            affected_packages = []

            for vuln in vulnerabilities:
                package = vuln.get("package", {})
                ecosystem = package.get("ecosystem", "")
                name = package.get("name", "")

                vulnerable_version_range = vuln.get("vulnerable_version_range", "")
                patched_versions = vuln.get("patched_versions", "")
                vulnerable_functions = vuln.get("vulnerable_functions", [])

                affected_packages.append({
                    "ecosystem": ecosystem,
                    "name": name,
                    "vulnerable_version_range": vulnerable_version_range,
                    "patched_versions": patched_versions,
                    "vulnerable_functions": vulnerable_functions,
                })

            # Extract references
            references = advisory.get("references", [])
            reference_list = []
            for ref in references:
                reference_list.append({
                    "url": ref if isinstance(ref, str) else ref.get("url", ""),
                })

            # Map GHSA severity to CVSS v3 severity (schema expects uppercase)
            severity_mapping = {
                "low": "LOW",
                "moderate": "MEDIUM",
                "high": "HIGH",
                "critical": "CRITICAL",
            }
            cvss_v3_severity = severity_mapping.get(severity.lower(), severity.upper()) if severity else None

            # Yield vulnerability document
            yield {
                "_key": _key,
                "vulnerability_id": ghsa_id,  # REQUIRED field in schema
                "cve_id": cve_id,
                "summary": summary,
                "description": description,
                "published": published.isoformat() if published else None,
                "modified": updated.isoformat() if updated else None,
                "last_modified": updated.isoformat() if updated else None,
                "withdrawn": withdrawn.isoformat() if withdrawn else None,
                "cvss_v3_score": cvss_score,  # Schema expects cvss_v3_score, not cvss_score
                "cvss_v3_vector": cvss_vector,
                "cvss_v3_severity": cvss_v3_severity,
                "cwe_ids": cwe_ids,
                "affected_packages": affected_packages,
                "references": reference_list,
                "source": "ghsa",
            }

            # Yield edges to CWE weaknesses
            for cwe_id in cwe_ids:
                cwe_key = normalize_cwe_id(cwe_id)
                yield {
                    "_collection": "has_weakness",
                    "_from": f"vulnerabilities/{_key}",
                    "_to": f"weaknesses/{cwe_key}",
                    "source": "ghsa",
                }

            # Yield alias edge to CVE (if GHSA maps to CVE)
            if cve_id:
                cve_key = normalize_cve_id(cve_id)
                yield {
                    "_collection": "aliases",
                    "_from": f"vulnerabilities/{_key}",
                    "_to": f"vulnerabilities/{cve_key}",
                    "source": "ghsa",
                }

    def load_data(self, records: Generator[dict, None, None], collection_name: str = None, on_duplicate: str = "update") -> dict:
        """
        Load GHSA data into database.

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
            "has_weakness": [],
            "aliases": [],
        }

        for record in records:
            if "_collection" in record:
                # It's an edge
                collection = record.pop("_collection")
                if collection in edges_by_collection:
                    edges_by_collection[collection].append(record)
            else:
                # It's a document
                documents.append(record)

        # Load documents
        self.logger.info("Loading GHSA advisories", count=len(documents))
        doc_stats = super().load_data(
            iter(documents),
            collection_name="vulnerabilities",
            on_duplicate=on_duplicate,
        )

        # Load edges
        total_edge_stats = {"created": 0, "updated": 0, "errors": 0, "total": 0}

        for collection, edges in edges_by_collection.items():
            if not edges:
                continue

            self.logger.info(f"Loading {collection} edges", count=len(edges))
            edge_stats = super().load_data(
                iter(edges),
                collection_name=collection,
                on_duplicate=on_duplicate,
            )

            total_edge_stats["created"] += edge_stats["created"]
            total_edge_stats["updated"] += edge_stats["updated"]
            total_edge_stats["errors"] += edge_stats["errors"]
            total_edge_stats["total"] += edge_stats["total"]

        # Combine statistics
        combined_stats = {
            "vulnerabilities": doc_stats,
            "edges": total_edge_stats,
            "total_created": doc_stats["created"] + total_edge_stats["created"],
            "total_updated": doc_stats["updated"] + total_edge_stats["updated"],
            "total_errors": doc_stats["errors"] + total_edge_stats["errors"],
        }

        return combined_stats

    def _get_primary_collection(self) -> str:
        """Get primary collection name."""
        return "vulnerabilities"

    def _get_last_update_timestamp(self):
        """
        Get the most recent update timestamp from GHSA advisories in the database.

        Returns:
            datetime: Most recent updated_at timestamp, or None if no data exists

        Note:
            Used for incremental updates - only fetch advisories newer than this timestamp.
        """
        try:
            query = """
            FOR vuln IN vulnerabilities
                FILTER vuln.source == "ghsa"
                FILTER vuln.updated != null
                SORT vuln.updated DESC
                LIMIT 1
                RETURN vuln.updated
            """

            cursor = self.db.aql.execute(query)
            result = list(cursor)

            if result and result[0]:
                from dateutil import parser
                last_updated = parser.isoparse(result[0])

                self.logger.info(
                    "Found last GHSA update timestamp",
                    last_updated=last_updated.isoformat(),
                )

                return last_updated

            self.logger.info("No existing GHSA data found, performing full sync")
            return None

        except Exception as e:
            self.logger.warning(
                "Failed to get last update timestamp, performing full sync",
                error=str(e),
            )
            return None
