"""
VulnCheck Ransomware ingestion agent.

Fetches ransomware family CVE attribution data from VulnCheck.
Enriches graph with ransomware-to-CVE relationships and ATT&CK technique mappings.

Data source: https://api.vulncheck.com/v3/backup/ransomware
Collections populated:
- ransomware_families (document collection for ransomware groups)
- exploited_by_ransomware (edges from vulnerabilities to ransomware families)
- ransomware_uses_technique (edges from ransomware families to ATT&CK techniques)

Phase: 3A (VulnCheck Integration)
"""

from typing import Generator, Dict, Any, List
from datetime import datetime
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_vulncheck_client
from ..utils.keys import normalize_cve_id
from ..config import get_settings

logger = structlog.get_logger()


class VulnCheckRansomwareAgent(BaseIngestionAgent):
    """
    Agent for ingesting VulnCheck ransomware family attribution data.

    VulnCheck ransomware data (~300+ families) includes:
    - Ransomware family metadata (name, aliases, first_seen)
    - CVE attribution (which CVEs are exploited by each family)
    - ATT&CK technique mappings (TTPs used by each family)

    This agent provides:
    1. Ransomware family documents
    2. CVE → ransomware edges (exploited_by_ransomware)
    3. Ransomware → ATT&CK technique edges (ransomware_uses_technique)
    4. Regulatory trigger candidates (ransomware exploitation = 24h urgency)
    """

    def __init__(self, db):
        """Initialize VulnCheck Ransomware agent."""
        super().__init__(db)
        settings = get_settings()

        # Get VulnCheck API key from settings
        api_key = settings.VULNCHECK_API_KEY
        if not api_key:
            raise ValueError(
                "VULNCHECK_API_KEY not configured. "
                "Please set VULNCHECK_API_KEY in .env file."
            )

        # Create VulnCheck HTTP client
        self.client = create_vulncheck_client(api_key=api_key, timeout=30.0)
        self.base_url = settings.VULNCHECK_BASE_URL

    def _get_primary_collection(self) -> str:
        """Get primary collection name for ransomware family data."""
        return "ransomware_families"

    def fetch_data(self) -> dict:
        """
        Fetch ransomware family data from VulnCheck backup endpoint.

        Returns:
            dict: Full ransomware catalog response

        Example response:
            {
                "data": [
                    {
                        "name": "LockBit",
                        "aliases": ["LockBit 2.0", "LockBit 3.0", "LockBit Black"],
                        "firstSeen": "2019-09-01",
                        "cves": ["CVE-2024-1234", "CVE-2023-5678"],
                        "ttps": ["T1486", "T1490", "T1003"]
                    },
                    ...
                ],
                "meta": {"total": 300}
            }
        """
        url = f"{self.base_url}/backup/ransomware"
        self.logger.info("Fetching VulnCheck ransomware catalog", url=url)

        response = self.client.get(url)
        data = response.json()

        family_count = len(data.get("data", []))
        self.logger.info(
            "Fetched VulnCheck ransomware catalog",
            family_count=family_count
        )

        return data

    def _get_attack_technique_map(self) -> Dict[str, str]:
        """
        Get ATT&CK technique map for TTP validation.

        Returns:
            dict: Map of {technique_id: document_id} from attack_techniques collection

        Example:
            {
                "T1486": "attack_techniques/T1486",
                "T1490": "attack_techniques/T1490"
            }
        """
        query = """
        FOR tech IN attack_techniques
            FILTER tech.source == "mitre_attack"
            RETURN {technique_id: tech.technique_id, doc_id: tech._id}
        """

        cursor = self.db.aql.execute(query)
        technique_map = {entry["technique_id"]: entry["doc_id"] for entry in cursor}

        self.logger.info(
            "Loaded ATT&CK technique map",
            technique_count=len(technique_map)
        )

        return technique_map

    def transform_data(self, raw_data: dict) -> Generator[dict, None, None]:
        """
        Transform ransomware data to graph nodes and edges.

        Args:
            raw_data: VulnCheck ransomware response from fetch_data()

        Yields:
            dict: Documents and edges for bulk insert

        Document format (ransomware_families):
            {
                "type": "document",
                "collection": "ransomware_families",
                "data": {
                    "_key": "lockbit",
                    "name": "LockBit",
                    "aliases": ["LockBit 2.0", "LockBit 3.0"],
                    "first_seen": "2019-09-01",
                    "cve_count": 12,
                    "ttp_count": 8,
                    "source": "vulncheck"
                }
            }

        Edge formats:
            - exploited_by_ransomware: vulnerabilities → ransomware_families
            - ransomware_uses_technique: ransomware_families → attack_techniques
        """
        # Get ATT&CK technique map for TTP validation
        technique_map = self._get_attack_technique_map()

        families = raw_data.get("data", [])

        for family in families:
            family_name = family.get("name", "").strip()
            if not family_name:
                continue

            # Generate key from family name (lowercase, no spaces)
            family_key = family_name.lower().replace(" ", "_").replace(".", "")

            # Get CVE list
            cves = family.get("cves", [])
            cve_count = len(cves)

            # Get TTP list (ATT&CK technique IDs)
            ttps = family.get("ttps", [])
            ttp_count = len(ttps)

            # Create ransomware_families document
            family_doc = {
                "type": "document",
                "collection": "ransomware_families",
                "data": {
                    "_key": family_key,
                    "name": family_name,
                    "aliases": family.get("aliases", []),
                    "first_seen": family.get("firstSeen"),
                    "cve_count": cve_count,
                    "ttp_count": ttp_count,
                    "source": "vulncheck",
                    "last_updated": datetime.utcnow().isoformat()
                }
            }

            yield family_doc

            # Create exploited_by_ransomware edges (CVE → ransomware family)
            for cve_id in cves:
                cve_id = normalize_cve_id(cve_id)

                edge = {
                    "type": "edge",
                    "collection": "exploited_by_ransomware",
                    "data": {
                        "_from": f"vulnerabilities/{cve_id}",
                        "_to": f"ransomware_families/{family_key}",
                        "ransomware_name": family_name,
                        "first_seen": family.get("firstSeen"),
                        "created_at": datetime.utcnow().isoformat()
                    }
                }

                yield edge

            # Create ransomware_uses_technique edges (ransomware → ATT&CK technique)
            for ttp in ttps:
                # Validate TTP exists in attack_techniques collection
                if ttp not in technique_map:
                    self.logger.warning(
                        "ATT&CK technique not found in graph",
                        ttp=ttp,
                        ransomware=family_name
                    )
                    continue

                edge = {
                    "type": "edge",
                    "collection": "ransomware_uses_technique",
                    "data": {
                        "_from": f"ransomware_families/{family_key}",
                        "_to": technique_map[ttp],
                        "technique_id": ttp,
                        "ransomware_name": family_name,
                        "created_at": datetime.utcnow().isoformat()
                    }
                }

                yield edge

    def load_data(self, transformed_data: Generator[dict, None, None]) -> dict:
        """
        Bulk load ransomware documents and edges into ArangoDB.

        Args:
            transformed_data: Generator of documents/edges from transform_data()

        Returns:
            dict: Load statistics

        Example:
            {
                "documents_inserted": 300,
                "edges_inserted": 4000,  # 3200 CVE edges + 800 TTP edges
                "errors": 0
            }
        """
        documents_by_collection = {}
        edges_by_collection = {}
        stats = {"documents_inserted": 0, "edges_inserted": 0, "errors": 0}

        # Group documents and edges by collection
        for item in transformed_data:
            if item["type"] == "document":
                coll = item["collection"]
                if coll not in documents_by_collection:
                    documents_by_collection[coll] = []
                documents_by_collection[coll].append(item["data"])

            elif item["type"] == "edge":
                coll = item["collection"]
                if coll not in edges_by_collection:
                    edges_by_collection[coll] = []
                edges_by_collection[coll].append(item["data"])

        # Bulk insert documents
        for coll_name, docs in documents_by_collection.items():
            try:
                collection = self.db.collection(coll_name)
                result = collection.import_bulk(
                    docs,
                    on_duplicate="replace",
                    details=False
                )
                stats["documents_inserted"] += result.get("created", 0) + result.get("updated", 0)
                stats["errors"] += result.get("errors", 0)

                self.logger.info(
                    "Bulk inserted documents",
                    collection=coll_name,
                    count=len(docs)
                )

            except Exception as e:
                self.logger.error(
                    "Failed to insert documents",
                    collection=coll_name,
                    error=str(e)
                )
                stats["errors"] += len(docs)

        # Bulk insert edges
        for coll_name, edges in edges_by_collection.items():
            try:
                collection = self.db.collection(coll_name)
                result = collection.import_bulk(
                    edges,
                    on_duplicate="replace",
                    details=False
                )
                stats["edges_inserted"] += result.get("created", 0) + result.get("updated", 0)
                stats["errors"] += result.get("errors", 0)

                self.logger.info(
                    "Bulk inserted edges",
                    collection=coll_name,
                    count=len(edges)
                )

            except Exception as e:
                self.logger.error(
                    "Failed to insert edges",
                    collection=coll_name,
                    error=str(e)
                )
                stats["errors"] += len(edges)

        return stats

    def run(self) -> dict:
        """
        Execute full VulnCheck ransomware ingestion workflow.

        Returns:
            dict: Execution statistics

        Example:
            {
                "agent": "VulnCheckRansomwareAgent",
                "status": "success",
                "documents_inserted": 300,
                "edges_inserted": 4000,
                "duration_seconds": 18.5
            }
        """
        start_time = datetime.utcnow()

        self.logger.info("Starting VulnCheck ransomware ingestion")

        try:
            # Fetch data
            raw_data = self.fetch_data()

            # Transform data
            transformed_data = self.transform_data(raw_data)

            # Load data
            stats = self.load_data(transformed_data)

            # Calculate duration
            duration = (datetime.utcnow() - start_time).total_seconds()

            result = {
                "agent": self.agent_name,
                "status": "success",
                **stats,
                "duration_seconds": round(duration, 2)
            }

            self.logger.info(
                "VulnCheck ransomware ingestion complete",
                **result
            )

            return result

        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()

            self.logger.error(
                "VulnCheck ransomware ingestion failed",
                error=str(e),
                duration_seconds=round(duration, 2)
            )

            return {
                "agent": self.agent_name,
                "status": "failed",
                "error": str(e),
                "duration_seconds": round(duration, 2)
            }
