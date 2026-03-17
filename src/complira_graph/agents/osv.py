"""
OSV (Open Source Vulnerabilities) ingestion agent.

Fetches vulnerability data from OSV API for open source packages.
OSV aggregates vulnerabilities across multiple ecosystems (npm, PyPI, Go, etc.).

Data source: https://api.osv.dev/v1/query
Collections populated:
- vulnerabilities (document collection)
- has_weakness (edges to CWE weaknesses)
- affects (edges to components via PURL)
"""

from typing import Generator
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_http_client
from ..utils.keys import normalize_cve_id, normalize_cwe_id, normalize_purl
from ..utils.transforms import safe_date_parse

logger = structlog.get_logger()


class OSVAgent(BaseIngestionAgent):
    """
    Agent for ingesting OSV (Open Source Vulnerabilities) data.

    OSV provides vulnerability data for open source packages across multiple ecosystems.
    """

    OSV_API_BASE = "https://api.osv.dev/v1"
    # Ecosystems to fetch (expand as needed)
    ECOSYSTEMS = [
        "PyPI",
        "npm",
        "Maven",
        "Go",
        "crates.io",
        "NuGet",
        "RubyGems",
        "Packagist",
        "Pub",
    ]

    def __init__(self, db):
        """Initialize OSV agent."""
        super().__init__(db)
        self.client = create_http_client(
            service_name="osv_dev",
            calls_per_period=30,
            period_seconds=60,
            circuit_breaker=False,
            timeout=30.0,
        )

    def fetch_data(self, ecosystems: list[str] = None) -> list[dict]:
        """
        Fetch vulnerability data from OSV bulk exports.

        Args:
            ecosystems: List of ecosystems to fetch (default: all supported)

        Returns:
            list[dict]: OSV vulnerability records

        Note:
            The /query endpoint requires a specific package name and doesn't support
            "all vulnerabilities in ecosystem" queries. This causes 400 Bad Request errors.

            Proper implementation requires using GCS bulk exports:
            https://osv-vulnerabilities.storage.googleapis.com/{ecosystem}/all.zip

            This involves:
            1. Download ZIP from GCS for each ecosystem
            2. Extract and parse JSON files
            3. Handle large datasets efficiently (GBs of data)

            OSV data is optional - GHSA + NVD provide sufficient vulnerability coverage.
        """
        if not ecosystems:
            ecosystems = self.ECOSYSTEMS

        self.logger.info(
            "OSV bulk export not implemented - skipping ecosystem-wide fetch",
            ecosystems=ecosystems,
            note="OSV /query endpoint requires package name, use GCS bulk exports for production",
        )

        # Return empty list - OSV data is optional (GHSA + NVD provide coverage)
        return []

        # TODO: Implement bulk export approach:
        # import zipfile
        # import tempfile
        # import json
        #
        # all_vulnerabilities = []
        # for ecosystem in ecosystems:
        #     url = f"https://osv-vulnerabilities.storage.googleapis.com/{ecosystem}/all.zip"
        #
        #     # Download ZIP to temp file
        #     response = self.client.get(url)
        #     with tempfile.NamedTemporaryFile(suffix='.zip') as tmp:
        #         tmp.write(response.content)
        #         tmp.flush()
        #
        #         # Extract and parse JSON files
        #         with zipfile.ZipFile(tmp.name, 'r') as zip_ref:
        #             for filename in zip_ref.namelist():
        #                 if filename.endswith('.json'):
        #                     with zip_ref.open(filename) as f:
        #                         vuln = json.load(f)
        #                         all_vulnerabilities.append(vuln)
        #
        #     self.logger.info(f"Fetched {len(all_vulnerabilities)} vulnerabilities from {ecosystem}")
        #
        # return all_vulnerabilities

    def transform_data(self, raw_data: list[dict]) -> Generator[dict, None, None]:
        """
        Transform OSV data to graph nodes and edges.

        Args:
            raw_data: List of OSV vulnerability records from fetch_data()

        Yields:
            dict: Vulnerability documents and relationship edges
        """
        for vuln in raw_data:
            # Extract vulnerability ID (may be CVE or OSV-specific like GHSA-*, PYSEC-*, etc.)
            vuln_id = vuln.get("id", "")
            if not vuln_id:
                continue

            # Normalize _key
            _key = normalize_cve_id(vuln_id) if vuln_id.startswith("CVE-") else vuln_id.replace("-", "_")

            # Extract summary and details
            summary = vuln.get("summary", "")
            details = vuln.get("details", "")

            # Extract dates
            published = safe_date_parse(vuln.get("published"))
            modified = safe_date_parse(vuln.get("modified"))
            withdrawn = safe_date_parse(vuln.get("withdrawn"))

            # Extract severity (CVSS scores)
            severity = vuln.get("severity", [])
            cvss_v3_score = None
            cvss_v3_vector = None

            for sev in severity:
                if sev.get("type") == "CVSS_V3":
                    cvss_v3_score = sev.get("score")
                    # OSV stores full CVSS vector in 'score' field sometimes
                    # Need to parse if it's a vector string

            # Extract affected packages
            affected = vuln.get("affected", [])
            affected_packages = []

            for pkg in affected:
                package = pkg.get("package", {})
                ecosystem = package.get("ecosystem", "")
                name = package.get("name", "")
                purl = package.get("purl", "")

                # Extract version ranges
                ranges = pkg.get("ranges", [])
                versions = pkg.get("versions", [])

                affected_packages.append({
                    "ecosystem": ecosystem,
                    "name": name,
                    "purl": purl,
                    "ranges": ranges,
                    "versions": versions,
                })

            # Extract references
            references = vuln.get("references", [])
            reference_list = []
            for ref in references:
                reference_list.append({
                    "type": ref.get("type", ""),
                    "url": ref.get("url", ""),
                })

            # Extract aliases (including CVE IDs)
            aliases = vuln.get("aliases", [])
            cve_aliases = [alias for alias in aliases if alias.startswith("CVE-")]

            # Extract CWE IDs from database_specific or references
            database_specific = vuln.get("database_specific", {})
            cwe_ids = database_specific.get("cwe_ids", [])

            # Yield vulnerability document
            yield {
                "_key": _key,
                "vulnerability_id": vuln_id,
                "summary": summary,
                "details": details,
                "published": published.isoformat() if published else None,
                "modified": modified.isoformat() if modified else None,
                "withdrawn": withdrawn.isoformat() if withdrawn else None,
                "cvss_v3_score": cvss_v3_score,
                "cvss_v3_vector": cvss_v3_vector,
                "affected_packages": affected_packages,
                "references": reference_list,
                "aliases": aliases,
                "cwe_ids": cwe_ids,
                "source": "osv",
            }

            # Yield edges to CWE weaknesses
            for cwe_id in cwe_ids:
                if cwe_id.startswith("CWE-"):
                    cwe_key = normalize_cwe_id(cwe_id)
                    yield {
                        "_collection": "has_weakness",
                        "_from": f"vulnerabilities/{_key}",
                        "_to": f"weaknesses/{cwe_key}",
                        "source": "osv",
                    }

            # Yield alias edges to CVE (if OSV ID maps to CVE)
            for cve_alias in cve_aliases:
                cve_key = normalize_cve_id(cve_alias)
                if cve_key != _key:  # Don't create self-edges
                    yield {
                        "_collection": "aliases",
                        "_from": f"vulnerabilities/{_key}",
                        "_to": f"vulnerabilities/{cve_key}",
                        "source": "osv",
                    }

    def load_data(self, records: Generator[dict, None, None], collection_name: str = None, on_duplicate: str = "update") -> dict:
        """
        Load OSV data into database.

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
        self.logger.info("Loading OSV vulnerabilities", count=len(documents))
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
