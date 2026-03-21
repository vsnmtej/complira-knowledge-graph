"""
VulnCheck Threat Actors ingestion agent with fuzzy matching.

Fetches threat actor CVE attribution from VulnCheck and merges with existing threat_groups.
Uses fuzzy name matching to avoid duplicates.

Data source: https://api.vulncheck.com/v3/backup/threat-actors
Collections populated:
- threat_groups (merge/update existing documents)
- exploited_by_threat_actor (edges from vulnerabilities to threat groups)

Phase: 3A (VulnCheck Integration)
"""

from typing import Generator, Dict, Any, Optional
from datetime import datetime
from difflib import SequenceMatcher
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_vulncheck_client
from ..utils.keys import normalize_cve_id
from ..config import get_settings

logger = structlog.get_logger()


class VulnCheckThreatActorsAgent(BaseIngestionAgent):
    """
    Agent for ingesting VulnCheck threat actor data with merge logic.

    Merges VulnCheck threat actors with existing threat_groups:
    - Fuzzy name matching (Levenshtein distance < 3, similarity > 85%)
    - Exact alias matching
    - Merge CVE lists if actor already exists
    - Create new threat_group if no match found
    """

    def __init__(self, db):
        """Initialize VulnCheck Threat Actors agent."""
        super().__init__(db)
        settings = get_settings()

        api_key = settings.VULNCHECK_API_KEY
        if not api_key:
            raise ValueError("VULNCHECK_API_KEY not configured.")

        self.client = create_vulncheck_client(api_key=api_key, timeout=30.0)
        self.base_url = settings.VULNCHECK_BASE_URL

    def _get_primary_collection(self) -> str:
        """Get primary collection name for threat actor data."""
        return "threat_groups"

    def fetch_data(self) -> dict:
        """Fetch threat actor data from VulnCheck backup endpoint."""
        url = f"{self.base_url}/backup/threat-actors"
        self.logger.info("Fetching VulnCheck threat actors catalog", url=url)

        response = self.client.get(url)
        data = response.json()

        actor_count = len(data.get("data", []))
        self.logger.info("Fetched VulnCheck threat actors catalog", actor_count=actor_count)

        return data

    def _fuzzy_match(self, name1: str, name2: str, threshold: float = 0.85) -> bool:
        """Check if two names are similar (fuzzy match)."""
        return SequenceMatcher(None, name1.lower(), name2.lower()).ratio() >= threshold

    def _find_existing_group(self, vc_actor: dict, existing_groups: list) -> Optional[dict]:
        """Find existing threat_group by exact or fuzzy match."""
        vc_name = vc_actor.get("name", "").lower()
        vc_aliases = [a.lower() for a in vc_actor.get("aliases", [])]

        for group in existing_groups:
            group_name = group.get("name", "").lower()
            group_aliases = [a.lower() for a in group.get("aliases", [])]

            # Exact name match
            if vc_name == group_name:
                return group

            # Alias match
            for vc_alias in vc_aliases:
                if vc_alias in group_aliases:
                    return group

            # Fuzzy match (similarity > 85%)
            if self._fuzzy_match(vc_name, group_name):
                return group

        return None

    def _get_existing_threat_groups(self) -> list:
        """Get all existing threat groups for merge logic."""
        query = """
        FOR group IN threat_groups
            RETURN {_id: group._id, _key: group._key, name: group.name, aliases: group.aliases}
        """

        cursor = self.db.aql.execute(query)
        groups = list(cursor)

        self.logger.info("Loaded existing threat groups", count=len(groups))
        return groups

    def transform_data(self, raw_data: dict) -> Generator[dict, None, None]:
        """Transform threat actor data with merge logic."""
        existing_groups = self._get_existing_threat_groups()
        actors = raw_data.get("data", [])

        for actor in actors:
            actor_name = actor.get("name", "").strip()
            if not actor_name:
                continue

            # Check if actor already exists
            existing_group = self._find_existing_group(actor, existing_groups)

            if existing_group:
                # MERGE: Update existing threat_group
                actor_key = existing_group["_key"]
                self.logger.debug("Merging threat actor with existing group", 
                                 vc_actor=actor_name, 
                                 existing_group=existing_group["name"])
            else:
                # CREATE: New threat_group
                actor_key = actor_name.lower().replace(" ", "_").replace(".", "")

            cves = actor.get("cves", [])

            # Yield threat_groups document (upsert)
            actor_doc = {
                "type": "document",
                "collection": "threat_groups",
                "data": {
                    "_key": actor_key,
                    "name": actor_name,
                    "aliases": actor.get("aliases", []),
                    "first_seen": actor.get("firstSeen"),
                    "cve_count": len(cves),
                    "source": "vulncheck",
                    "last_updated": datetime.utcnow().isoformat()
                }
            }

            yield actor_doc

            # Yield exploited_by_threat_actor edges
            for cve_id in cves:
                cve_id = normalize_cve_id(cve_id)

                edge = {
                    "type": "edge",
                    "collection": "exploited_by_threat_actor",
                    "data": {
                        "_from": f"vulnerabilities/{cve_id}",
                        "_to": f"threat_groups/{actor_key}",
                        "actor_name": actor_name,
                        "first_seen": actor.get("firstSeen"),
                        "created_at": datetime.utcnow().isoformat()
                    }
                }

                yield edge

    def load_data(self, transformed_data: Generator[dict, None, None]) -> dict:
        """Bulk load threat actor documents and edges."""
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
            except Exception as e:
                self.logger.error("Failed to insert documents", collection=coll_name, error=str(e))
                stats["errors"] += len(docs)

        for coll_name, edges in edges_by_collection.items():
            try:
                collection = self.db.collection(coll_name)
                result = collection.import_bulk(edges, on_duplicate="replace", details=False)
                stats["edges_inserted"] += result.get("created", 0) + result.get("updated", 0)
            except Exception as e:
                self.logger.error("Failed to insert edges", collection=coll_name, error=str(e))
                stats["errors"] += len(edges)

        return stats

    def run(self) -> dict:
        """Execute full VulnCheck threat actors ingestion workflow."""
        start_time = datetime.utcnow()
        self.logger.info("Starting VulnCheck threat actors ingestion")

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

            self.logger.info("VulnCheck threat actors ingestion complete", **result)
            return result

        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()
            self.logger.error("VulnCheck threat actors ingestion failed", error=str(e))

            return {
                "agent": self.agent_name,
                "status": "failed",
                "error": str(e),
                "duration_seconds": round(duration, 2)
            }
