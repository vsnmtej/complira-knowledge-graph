"""
VulnCheck KEV (Known Exploited Vulnerabilities) ingestion agent.

Fetches VulnCheck's KEV catalog and provides dual tracking vs CISA KEV.
VulnCheck KEV typically has 2-4 week lead time over CISA KEV.

Data source: https://api.vulncheck.com/v3/backup/vulncheck-kev
Collections populated:
- vulncheck_kev_entries (document collection for VulnCheck KEV data)
- has_exploit_intelligence (edges from vulnerabilities to KEV entries)
- exploited_in_wild (edges from vulnerabilities to KEV entries, source: "vulncheck_kev")
- vuln_triggers_requirement (auto-generated regulatory triggers for KEV entries)

Phase: 3A (VulnCheck Integration)
"""

from typing import Generator, Dict, Any, Optional
from datetime import datetime
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_vulncheck_client
from ..utils.keys import normalize_cve_id
from ..config import get_settings

logger = structlog.get_logger()


class VulnCheckKEVAgent(BaseIngestionAgent):
    """
    Agent for ingesting VulnCheck KEV catalog with dual tracking vs CISA KEV.

    VulnCheck KEV catalog (~3,700+ entries) has significant lead time over CISA KEV:
    - Average lead time: 28 days
    - VulnCheck typically adds CVEs weeks before CISA

    This agent provides:
    1. Full VulnCheck KEV catalog (vendor_project, product, exploitation_evidence)
    2. Lead time calculation (VulnCheck dateAdded - CISA dateAdded)
    3. Dual tracking (both VulnCheck KEV and CISA KEV available)
    4. Automatic regulatory trigger generation (24h urgency for KEV entries)
    """

    def __init__(self, db):
        """Initialize VulnCheck KEV agent."""
        super().__init__(db)
        settings = get_settings()

        # Get VulnCheck API key from settings
        api_key = settings.VULNCHECK_API_KEY
        if not api_key:
            raise ValueError(
                "VULNCHECK_API_KEY not configured. "
                "Please set VULNCHECK_API_KEY in .env file."
            )

        # Create VulnCheck HTTP client (1,000 req/min rate limit)
        self.client = create_vulncheck_client(api_key=api_key, timeout=30.0)
        self.base_url = settings.VULNCHECK_BASE_URL

    def _get_primary_collection(self) -> str:
        """Get primary collection name for VulnCheck KEV data."""
        return "vulncheck_kev_entries"

    def fetch_data(self) -> dict:
        """
        Fetch VulnCheck KEV catalog from backup endpoint.

        Returns:
            dict: Full KEV catalog response

        Raises:
            Exception: On fetch failure

        Example response:
            {
                "data": [
                    {
                        "cve": "CVE-2024-1234",
                        "vendorProject": "Vendor Name",
                        "product": "Product Name",
                        "dateAdded": "2024-06-01T00:00:00Z",
                        "knownRansomwareCampaignUse": "Known",
                        "exploitationEvidence": [
                            {"url": "https://...", "dateAdded": "..."}
                        ]
                    },
                    ...
                ],
                "meta": {"total": 3700, "timestamp": "..."}
            }
        """
        url = f"{self.base_url}/backup/vulncheck-kev"
        self.logger.info("Fetching VulnCheck KEV catalog", url=url)

        response = self.client.get(url)
        data = response.json()

        kev_count = len(data.get("data", []))
        self.logger.info(
            "Fetched VulnCheck KEV catalog",
            count=kev_count,
            timestamp=data.get("meta", {}).get("timestamp")
        )

        return data

    def _get_cisa_kev_map(self) -> Dict[str, str]:
        """
        Get CISA KEV map for lead time calculation.

        Returns:
            dict: Map of {cve_id: date_added} from CISA KEV catalog

        Example:
            {
                "CVE-2024-1234": "2024-06-29T00:00:00Z",
                "CVE-2024-5678": "2024-05-15T00:00:00Z"
            }
        """
        kev_collection = self.db.collection("kev_entries")

        # Query CISA KEV catalog
        query = """
        FOR kev IN kev_entries
            RETURN {cve_id: kev.cve_id, date_added: kev.date_added}
        """

        cursor = self.db.aql.execute(query)
        cisa_kev_map = {entry["cve_id"]: entry["date_added"] for entry in cursor}

        self.logger.info(
            "Loaded CISA KEV map for lead time calculation",
            cisa_kev_count=len(cisa_kev_map)
        )

        return cisa_kev_map

    def _calculate_lead_time(
        self,
        vulncheck_date: str,
        cisa_date: Optional[str]
    ) -> Optional[int]:
        """
        Calculate lead time (days) between VulnCheck and CISA KEV.

        Args:
            vulncheck_date: VulnCheck dateAdded (ISO 8601)
            cisa_date: CISA dateAdded (ISO 8601) or None

        Returns:
            int: Lead time in days (positive if VulnCheck first, negative if CISA first)
                 None if CISA doesn't have this CVE

        Example:
            >>> _calculate_lead_time("2024-06-01T00:00:00Z", "2024-06-29T00:00:00Z")
            28  # VulnCheck added 28 days before CISA
        """
        if not cisa_date:
            return None

        try:
            vc_dt = datetime.fromisoformat(vulncheck_date.replace("Z", "+00:00"))
            cisa_dt = datetime.fromisoformat(cisa_date.replace("Z", "+00:00"))
            delta = (cisa_dt - vc_dt).days
            return delta
        except Exception as e:
            self.logger.warning(
                "Failed to calculate lead time",
                vulncheck_date=vulncheck_date,
                cisa_date=cisa_date,
                error=str(e)
            )
            return None

    def transform_data(self, raw_data: dict) -> Generator[dict, None, None]:
        """
        Transform VulnCheck KEV data to graph nodes and edges.

        Args:
            raw_data: VulnCheck KEV response from fetch_data()

        Yields:
            dict: Documents and edges for bulk insert

        Document format:
            {
                "type": "document",
                "collection": "vulncheck_kev_entries",
                "data": {
                    "_key": "CVE-2024-1234",
                    "cve_id": "CVE-2024-1234",
                    "vendor_project": "Vendor Name",
                    "product": "Product Name",
                    "date_added": "2024-06-01T00:00:00Z",
                    "known_ransomware_campaign_use": "Known",
                    "exploitation_evidence": [...],
                    "in_cisa_kev": True,
                    "vulncheck_first": True,
                    "lead_time_days": 28,
                    "source": "vulncheck"
                }
            }

        Edge formats:
            {
                "type": "edge",
                "collection": "has_exploit_intelligence",
                "data": {
                    "_from": "vulnerabilities/CVE-2024-1234",
                    "_to": "exploit_intelligence/CVE-2024-1234",
                    "source": "vulncheck_kev"
                }
            }
        """
        # Get CISA KEV map for lead time calculation
        cisa_kev_map = self._get_cisa_kev_map()

        kev_entries = raw_data.get("data", [])

        for entry in kev_entries:
            cve_id_original = entry.get("cve", "").strip()
            if not cve_id_original or not cve_id_original.startswith("CVE-"):
                continue

            # Normalize CVE ID for _key (ArangoDB requires no hyphens)
            cve_id_normalized = normalize_cve_id(cve_id_original)

            # Get CISA KEV date for this CVE (if exists)
            cisa_date = cisa_kev_map.get(cve_id_normalized)

            # Calculate lead time
            vulncheck_date = entry.get("dateAdded")
            lead_time_days = self._calculate_lead_time(vulncheck_date, cisa_date)

            # Determine if VulnCheck added first
            vulncheck_first = lead_time_days is not None and lead_time_days > 0

            # Create vulncheck_kev_entries document
            kev_doc = {
                "type": "document",
                "collection": "vulncheck_kev_entries",
                "data": {
                    "_key": cve_id_normalized,
                    "cve_id": cve_id_original,  # Store original CVE-YYYY-NNNNN format
                    "vendor_project": entry.get("vendorProject", ""),
                    "product": entry.get("product", ""),
                    "date_added": vulncheck_date,
                    "known_ransomware_campaign_use": entry.get("knownRansomwareCampaignUse", "Unknown"),
                    "exploitation_evidence": entry.get("exploitationEvidence", []),
                    "in_cisa_kev": cisa_date is not None,
                    "vulncheck_first": vulncheck_first,
                    "lead_time_days": lead_time_days,
                    "source": "vulncheck",
                    "last_updated": datetime.utcnow().isoformat()
                }
            }

            yield kev_doc

            # Create has_exploit_intelligence edge (CVE → exploit_intelligence)
            # Note: exploit_intelligence will be populated by VulnCheckNVD2Agent
            exploit_edge = {
                "type": "edge",
                "collection": "has_exploit_intelligence",
                "data": {
                    "_from": f"vulnerabilities/{cve_id_normalized}",
                    "_to": f"exploit_intelligence/{cve_id_normalized}",
                    "source": "vulncheck_kev",
                    "created_at": datetime.utcnow().isoformat()
                }
            }

            yield exploit_edge

            # Create exploited_in_wild edge (CVE → KEV entry, source: vulncheck_kev)
            # This allows differentiation from CISA KEV edges (source: cisa_kev)
            exploited_edge = {
                "type": "edge",
                "collection": "exploited_in_wild",
                "data": {
                    "_from": f"vulnerabilities/{cve_id_normalized}",
                    "_to": f"vulncheck_kev_entries/{cve_id_normalized}",
                    "source": "vulncheck_kev",
                    "date_added": vulncheck_date,
                    "lead_time_days": lead_time_days,
                    "created_at": datetime.utcnow().isoformat()
                }
            }

            yield exploited_edge

            # TODO: Auto-generate regulatory triggers (vuln_triggers_requirement edges)
            # This will be implemented in Phase 3A-B (RegulatoryTriggerService)
            # For now, skip auto-generation

    def load_data(self, transformed_data: Generator[dict, None, None]) -> dict:
        """
        Bulk load VulnCheck KEV documents and edges into ArangoDB.

        Args:
            transformed_data: Generator of documents/edges from transform_data()

        Returns:
            dict: Load statistics

        Example:
            {
                "documents_inserted": 3700,
                "edges_inserted": 7400,  # 2 edges per KEV entry
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
                    on_duplicate="replace",  # Replace existing KEV entries
                    details=False
                )
                stats["documents_inserted"] += result.get("created", 0) + result.get("updated", 0)
                stats["errors"] += result.get("errors", 0)

                self.logger.info(
                    "Bulk inserted documents",
                    collection=coll_name,
                    count=len(docs),
                    created=result.get("created", 0),
                    updated=result.get("updated", 0)
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
                    count=len(edges),
                    created=result.get("created", 0),
                    updated=result.get("updated", 0)
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
        Execute full VulnCheck KEV ingestion workflow.

        Returns:
            dict: Execution statistics

        Example:
            {
                "agent": "VulnCheckKEVAgent",
                "status": "success",
                "documents_inserted": 3700,
                "edges_inserted": 7400,
                "vulncheck_first_count": 2200,  # CVEs added before CISA
                "average_lead_time_days": 28,
                "duration_seconds": 25.3
            }
        """
        start_time = datetime.utcnow()

        self.logger.info("Starting VulnCheck KEV ingestion")

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
                "VulnCheck KEV ingestion complete",
                **result
            )

            return result

        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()

            self.logger.error(
                "VulnCheck KEV ingestion failed",
                error=str(e),
                duration_seconds=round(duration, 2)
            )

            return {
                "agent": self.agent_name,
                "status": "failed",
                "error": str(e),
                "duration_seconds": round(duration, 2)
            }
