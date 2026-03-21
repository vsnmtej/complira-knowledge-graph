"""
VulnCheck Botnets ingestion agent.

Fetches botnet CVE attribution data from VulnCheck.
Enriches graph with botnet-to-CVE relationships and ATT&CK technique mappings.

Data source: https://api.vulncheck.com/v3/backup/botnets
Collections populated:
- botnets (document collection for botnet campaigns)
- exploited_by_botnet (edges from vulnerabilities to botnets)
- botnet_uses_technique (edges from botnets to ATT&CK techniques)

Phase: 3A (VulnCheck Integration)
"""

from typing import Generator, Dict, Any
from datetime import datetime
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_vulncheck_client
from ..utils.keys import normalize_cve_id
from ..config import get_settings

logger = structlog.get_logger()


class VulnCheckBotnetsAgent(BaseIngestionAgent):
    """
    Agent for ingesting VulnCheck botnet CVE attribution data.

    VulnCheck botnet data (~100+ botnets) includes:
    - Botnet campaign metadata (name, aliases, first_seen)
    - CVE attribution (which CVEs are exploited by each botnet)
    - ATT&CK technique mappings (TTPs used by each botnet)
    """

    def __init__(self, db):
        """Initialize VulnCheck Botnets agent."""
        super().__init__(db)
        settings = get_settings()

        api_key = settings.VULNCHECK_API_KEY
        if not api_key:
            raise ValueError(
                "VULNCHECK_API_KEY not configured. "
                "Please set VULNCHECK_API_KEY in .env file."
            )

        self.client = create_vulncheck_client(api_key=api_key, timeout=30.0)
        self.base_url = settings.VULNCHECK_BASE_URL

    def _get_primary_collection(self) -> str:
        """Get primary collection name for botnet data."""
        return "botnets"

    def fetch_data(self) -> dict:
        """Fetch botnet data from VulnCheck backup endpoint."""
        url = f"{self.base_url}/backup/botnets"
        self.logger.info("Fetching VulnCheck botnets catalog", url=url)

        response = self.client.get(url)
        data = response.json()

        botnet_count = len(data.get("data", []))
        self.logger.info("Fetched VulnCheck botnets catalog", botnet_count=botnet_count)

        return data

    def _get_attack_technique_map(self) -> Dict[str, str]:
        """Get ATT&CK technique map for TTP validation."""
        query = """
        FOR tech IN attack_techniques
            FILTER tech.source == "mitre_attack"
            RETURN {technique_id: tech.technique_id, doc_id: tech._id}
        """

        cursor = self.db.aql.execute(query)
        return {entry["technique_id"]: entry["doc_id"] for entry in cursor}

    def transform_data(self, raw_data: dict) -> Generator[dict, None, None]:
        """Transform botnet data to graph nodes and edges."""
        technique_map = self._get_attack_technique_map()
        botnets = raw_data.get("data", [])

        for botnet in botnets:
            botnet_name = botnet.get("name", "").strip()
            if not botnet_name:
                continue

            botnet_key = botnet_name.lower().replace(" ", "_").replace(".", "")

            cves = botnet.get("cves", [])
            ttps = botnet.get("ttps", [])

            # Create botnets document
            botnet_doc = {
                "type": "document",
                "collection": "botnets",
                "data": {
                    "_key": botnet_key,
                    "name": botnet_name,
                    "aliases": botnet.get("aliases", []),
                    "first_seen": botnet.get("firstSeen"),
                    "cve_count": len(cves),
                    "ttp_count": len(ttps),
                    "source": "vulncheck",
                    "last_updated": datetime.utcnow().isoformat()
                }
            }

            yield botnet_doc

            # Create exploited_by_botnet edges
            for cve_id in cves:
                cve_id = normalize_cve_id(cve_id)

                edge = {
                    "type": "edge",
                    "collection": "exploited_by_botnet",
                    "data": {
                        "_from": f"vulnerabilities/{cve_id}",
                        "_to": f"botnets/{botnet_key}",
                        "botnet_name": botnet_name,
                        "first_seen": botnet.get("firstSeen"),
                        "created_at": datetime.utcnow().isoformat()
                    }
                }

                yield edge

            # Create botnet_uses_technique edges
            for ttp in ttps:
                if ttp not in technique_map:
                    continue

                edge = {
                    "type": "edge",
                    "collection": "botnet_uses_technique",
                    "data": {
                        "_from": f"botnets/{botnet_key}",
                        "_to": technique_map[ttp],
                        "technique_id": ttp,
                        "botnet_name": botnet_name,
                        "created_at": datetime.utcnow().isoformat()
                    }
                }

                yield edge

    def load_data(self, transformed_data: Generator[dict, None, None]) -> dict:
        """Bulk load botnet documents and edges into ArangoDB."""
        documents_by_collection = {}
        edges_by_collection = {}
        stats = {"documents_inserted": 0, "edges_inserted": 0, "errors": 0}

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

        for coll_name, docs in documents_by_collection.items():
            try:
                collection = self.db.collection(coll_name)
                result = collection.import_bulk(docs, on_duplicate="replace", details=False)
                stats["documents_inserted"] += result.get("created", 0) + result.get("updated", 0)
                stats["errors"] += result.get("errors", 0)
            except Exception as e:
                self.logger.error("Failed to insert documents", collection=coll_name, error=str(e))
                stats["errors"] += len(docs)

        for coll_name, edges in edges_by_collection.items():
            try:
                collection = self.db.collection(coll_name)
                result = collection.import_bulk(edges, on_duplicate="replace", details=False)
                stats["edges_inserted"] += result.get("created", 0) + result.get("updated", 0)
                stats["errors"] += result.get("errors", 0)
            except Exception as e:
                self.logger.error("Failed to insert edges", collection=coll_name, error=str(e))
                stats["errors"] += len(edges)

        return stats

    def run(self) -> dict:
        """Execute full VulnCheck botnets ingestion workflow."""
        start_time = datetime.utcnow()
        self.logger.info("Starting VulnCheck botnets ingestion")

        try:
            raw_data = self.fetch_data()
            transformed_data = self.transform_data(raw_data)
            stats = self.load_data(transformed_data)
            duration = (datetime.utcnow() - start_time).total_seconds()

            result = {
                "agent": self.agent_name,
                "status": "success",
                **stats,
                "duration_seconds": round(duration, 2)
            }

            self.logger.info("VulnCheck botnets ingestion complete", **result)
            return result

        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()
            self.logger.error("VulnCheck botnets ingestion failed", error=str(e))

            return {
                "agent": self.agent_name,
                "status": "failed",
                "error": str(e),
                "duration_seconds": round(duration, 2)
            }
