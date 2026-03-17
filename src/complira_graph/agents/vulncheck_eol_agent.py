"""
VulnCheck EOL (End-of-Life) ingestion agent.

Fetches end-of-life product data from VulnCheck for FDA unsupported software documentation.
Critical for regulatory compliance (FDA 524B requires tracking unsupported software).

Data source: https://api.vulncheck.com/v3/backup/eol
Collections populated:
- eol_products (document collection for EOL products)
- component_eol_status (edges from components to EOL products)

Phase: 3A (VulnCheck Integration)
"""

from typing import Generator, Dict, Any
from datetime import datetime
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_vulncheck_client
from ..config import get_settings

logger = structlog.get_logger()


class VulnCheckEOLAgent(BaseIngestionAgent):
    """
    Agent for ingesting VulnCheck EOL product data.

    EOL data (~500+ products) includes:
    - Product/version metadata (name, version, CPE)
    - EOL dates (end-of-life, end-of-support)
    - Support status (supported, unsupported)
    - FDA compliance context (unsupported software tracking)
    """

    def __init__(self, db):
        """Initialize VulnCheck EOL agent."""
        super().__init__(db)
        settings = get_settings()

        api_key = settings.VULNCHECK_API_KEY
        if not api_key:
            raise ValueError("VULNCHECK_API_KEY not configured.")

        self.client = create_vulncheck_client(api_key=api_key, timeout=30.0)
        self.base_url = settings.VULNCHECK_BASE_URL

    def _get_primary_collection(self) -> str:
        """Get primary collection name for EOL product data."""
        return "eol_products"

    def fetch_data(self) -> dict:
        """Fetch EOL product data from VulnCheck backup endpoint."""
        url = f"{self.base_url}/backup/eol"
        self.logger.info("Fetching VulnCheck EOL catalog", url=url)

        response = self.client.get(url)
        data = response.json()

        eol_count = len(data.get("data", []))
        self.logger.info("Fetched VulnCheck EOL catalog", eol_count=eol_count)

        return data

    def _get_components_with_cpe(self) -> Dict[str, str]:
        """
        Get all components with CPE for EOL matching.

        Returns:
            dict: Map of {component_cpe: component_id}
        """
        query = """
        FOR comp IN components
            FILTER comp.cpe != null
            RETURN {cpe: comp.cpe, doc_id: comp._id}
        """

        cursor = self.db.aql.execute(query)
        cpe_map = {entry["cpe"]: entry["doc_id"] for entry in cursor}

        self.logger.info("Loaded components with CPE", count=len(cpe_map))
        return cpe_map

    def transform_data(self, raw_data: dict) -> Generator[dict, None, None]:
        """
        Transform EOL product data to graph nodes and edges.

        Args:
            raw_data: VulnCheck EOL response

        Yields:
            dict: Documents and edges for bulk insert
        """
        # Get component CPE map for matching
        component_cpe_map = self._get_components_with_cpe()

        eol_products = raw_data.get("data", [])

        for product in eol_products:
            product_name = product.get("product", "").strip()
            if not product_name:
                continue

            version = product.get("version", "").strip()
            product_key = f"{product_name}_{version}".lower().replace(" ", "_").replace(".", "_")

            cpe = product.get("cpe", "")

            # Create eol_products document
            eol_doc = {
                "type": "document",
                "collection": "eol_products",
                "data": {
                    "_key": product_key,
                    "product": product_name,
                    "version": version,
                    "cpe": cpe,
                    "eol_date": product.get("eolDate"),
                    "support_status": product.get("supportStatus", "unknown"),
                    "lts": product.get("lts", False),
                    "source": "vulncheck",
                    "last_updated": datetime.utcnow().isoformat()
                }
            }

            yield eol_doc

            # Create component_eol_status edges (component → EOL product)
            # Match components by CPE prefix
            if cpe:
                for comp_cpe, comp_id in component_cpe_map.items():
                    # Simple prefix match (can be enhanced with CPE parsing library)
                    if comp_cpe.startswith(cpe):
                        edge = {
                            "type": "edge",
                            "collection": "component_eol_status",
                            "data": {
                                "_from": comp_id,
                                "_to": f"eol_products/{product_key}",
                                "eol_date": product.get("eolDate"),
                                "support_status": product.get("supportStatus", "unknown"),
                                "created_at": datetime.utcnow().isoformat()
                            }
                        }

                        yield edge

    def load_data(self, transformed_data: Generator[dict, None, None]) -> dict:
        """Bulk load EOL product documents and edges."""
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
        """Execute full VulnCheck EOL ingestion workflow."""
        start_time = datetime.utcnow()
        self.logger.info("Starting VulnCheck EOL ingestion")

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

            self.logger.info("VulnCheck EOL ingestion complete", **result)
            return result

        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()
            self.logger.error("VulnCheck EOL ingestion failed", error=str(e))

            return {
                "agent": self.agent_name,
                "status": "failed",
                "error": str(e),
                "duration_seconds": round(duration, 2)
            }
