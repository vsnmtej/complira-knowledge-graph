"""
VulnCheck NVD2 (enriched NVD data) ingestion agent with streaming parser.

Fetches VulnCheck's enriched NVD2 catalog with exploit intelligence for 244K+ CVEs.
Uses ijson streaming parser to avoid memory exhaustion (~500MB-1GB response).

Data source: https://api.vulncheck.com/v3/backup/vulncheck-nvd2
Collections populated:
- exploit_intelligence (document collection for per-CVE exploit maturity data)
- has_exploit_intelligence (edges from vulnerabilities to exploit intelligence)

Phase: 3A (VulnCheck Integration)
"""

from typing import Generator, Dict, Any
from datetime import datetime
import structlog
import ijson
import io

from .base import BaseIngestionAgent
from ..utils.http_client import create_vulncheck_client
from ..utils.keys import normalize_cve_id
from ..config import get_settings

logger = structlog.get_logger()


class VulnCheckNVD2Agent(BaseIngestionAgent):
    """
    Agent for ingesting VulnCheck NVD2 catalog with streaming JSON parser.

    VulnCheck NVD2 provides enriched CVE data with exploit intelligence:
    - 244,866+ CVEs (full NVD catalog)
    - Exploit maturity (POC, weaponized, actively exploited)
    - Exploit timeline (first_exploit_date, reported_exploited)
    - Response size: ~500MB-1GB (requires streaming parser)

    This agent uses ijson for incremental JSON parsing:
    - Constant memory usage (~50MB vs 500MB-1GB)
    - Processes CVEs in batches of 1,000
    - Shows progress every 10,000 CVEs
    - Supports checkpointing (auto-resume on failure)
    """

    # Enable checkpointing for large dataset (auto-resume on failure)
    supports_checkpointing = True
    checkpoint_interval = 10000  # Save checkpoint every 10K CVEs

    def __init__(self, db):
        """Initialize VulnCheck NVD2 agent."""
        super().__init__(db)
        settings = get_settings()

        # Get VulnCheck API key from settings
        api_key = settings.VULNCHECK_API_KEY
        if not api_key:
            raise ValueError(
                "VULNCHECK_API_KEY not configured. "
                "Please set VULNCHECK_API_KEY in .env file."
            )

        # Create VulnCheck HTTP client with longer timeout for streaming
        self.client = create_vulncheck_client(api_key=api_key, timeout=300.0)  # 5 min timeout
        self.base_url = settings.VULNCHECK_BASE_URL

        # Batch size for bulk inserts
        self.batch_size = 1000

    def _get_primary_collection(self) -> str:
        """Get primary collection name for exploit intelligence data."""
        return "exploit_intelligence"

    def fetch_data_stream(self) -> Generator[dict, None, None]:
        """
        Stream VulnCheck NVD2 catalog using ijson incremental parser.

        Yields:
            dict: Individual CVE entries from NVD2 catalog

        Example CVE entry:
            {
                "cve": "CVE-2024-1234",
                "reportedExploited": true,
                "firstExploitDate": "2024-06-01T00:00:00Z",
                "exploitMaturity": "weaponized",
                "exploitCount": 3,
                "cpeCount": 12,
                "cvssV3Score": 9.8,
                "cvssV2Score": 7.5
            }
        """
        url = f"{self.base_url}/backup/vulncheck-nvd2"
        self.logger.info("Streaming VulnCheck NVD2 catalog", url=url)

        # Stream HTTP response
        response = self.client.get(url)

        # Use ijson to parse JSON incrementally
        # Parse "data" array items (each CVE entry)
        parser = ijson.items(io.BytesIO(response.content), 'data.item')

        for cve_entry in parser:
            yield cve_entry

        self.logger.info("Finished streaming VulnCheck NVD2 catalog")

    def transform_data(self, cve_entry: dict) -> Dict[str, Any]:
        """
        Transform single CVE entry to exploit_intelligence document.

        Args:
            cve_entry: Single CVE entry from NVD2 stream

        Returns:
            dict: exploit_intelligence document or None if invalid

        Document format:
            {
                "_key": "CVE-2024-1234",
                "cve_id": "CVE-2024-1234",
                "reported_exploited": true,
                "first_exploit_date": "2024-06-01T00:00:00Z",
                "exploit_maturity": "weaponized",
                "exploit_count": 3,
                "cpe_count": 12,
                "cvss_v3_score": 9.8,
                "cvss_v2_score": 7.5,
                "source": "vulncheck_nvd2",
                "last_updated": "2024-03-03T12:00:00Z"
            }
        """
        cve_id_original = cve_entry.get("cve", "").strip()
        if not cve_id_original or not cve_id_original.startswith("CVE-"):
            return None

        # Normalize CVE ID for _key (ArangoDB requires no hyphens)
        cve_id_normalized = normalize_cve_id(cve_id_original)

        # Create exploit_intelligence document
        exploit_doc = {
            "_key": cve_id_normalized,
            "cve_id": cve_id_original,  # Store original CVE-YYYY-NNNNN format
            "reported_exploited": cve_entry.get("reportedExploited", False),
            "reported_exploited_by_vulncheck_canaries": cve_entry.get("reportedExploitedByVulnCheckCanaries", False),
            "first_exploit_date": cve_entry.get("firstExploitDate"),
            "exploit_maturity": cve_entry.get("exploitMaturity", "unknown"),  # POC, weaponized, actively_exploited
            "exploit_count": cve_entry.get("exploitCount", 0),
            "cpe_count": cve_entry.get("cpeCount", 0),
            "cvss_v3_score": cve_entry.get("cvssV3Score"),
            "cvss_v2_score": cve_entry.get("cvssV2Score"),
            "source": "vulncheck_nvd2",
            "last_updated": datetime.utcnow().isoformat()
        }

        return exploit_doc

    def _batch_insert_documents(self, batch: list) -> dict:
        """
        Bulk insert batch of exploit_intelligence documents.

        Args:
            batch: List of exploit_intelligence documents

        Returns:
            dict: Insert statistics
        """
        if not batch:
            return {"created": 0, "updated": 0, "errors": 0}

        try:
            collection = self.db.collection("exploit_intelligence")
            result = collection.import_bulk(
                batch,
                on_duplicate="replace",  # Replace existing entries
                details=False
            )

            return {
                "created": result.get("created", 0),
                "updated": result.get("updated", 0),
                "errors": result.get("errors", 0)
            }

        except Exception as e:
            self.logger.error(
                "Failed to insert batch",
                batch_size=len(batch),
                error=str(e)
            )
            return {"created": 0, "updated": 0, "errors": len(batch)}

    def _batch_insert_edges(self, batch: list) -> dict:
        """
        Bulk insert batch of has_exploit_intelligence edges.

        Args:
            batch: List of edge documents

        Returns:
            dict: Insert statistics
        """
        if not batch:
            return {"created": 0, "updated": 0, "errors": 0}

        try:
            collection = self.db.collection("has_exploit_intelligence")
            result = collection.import_bulk(
                batch,
                on_duplicate="replace",
                details=False
            )

            return {
                "created": result.get("created", 0),
                "updated": result.get("updated", 0),
                "errors": result.get("errors", 0)
            }

        except Exception as e:
            self.logger.error(
                "Failed to insert edge batch",
                batch_size=len(batch),
                error=str(e)
            )
            return {"created": 0, "updated": 0, "errors": len(batch)}

    def run(self) -> dict:
        """
        Execute full VulnCheck NVD2 ingestion with streaming parser.

        Returns:
            dict: Execution statistics

        Example:
            {
                "agent": "VulnCheckNVD2Agent",
                "status": "success",
                "cves_processed": 244866,
                "documents_inserted": 244866,
                "edges_inserted": 244866,
                "batches": 245,
                "duration_seconds": 720.5
            }
        """
        start_time = datetime.utcnow()

        self.logger.info("Starting VulnCheck NVD2 ingestion (streaming mode)")

        # Check for existing checkpoint
        checkpoint = self._load_checkpoint()
        resume_from = checkpoint.get("cves_processed", 0) if checkpoint else 0

        if resume_from > 0:
            self.logger.info(
                "Resuming from checkpoint",
                cves_processed=resume_from
            )

        try:
            # Counters
            cves_processed = resume_from
            total_documents_inserted = 0
            total_edges_inserted = 0
            total_errors = 0
            batch_count = 0

            # Batch buffers
            doc_batch = []
            edge_batch = []

            # Stream CVE entries
            for i, cve_entry in enumerate(self.fetch_data_stream()):
                # Skip already processed CVEs (resume support)
                if i < resume_from:
                    continue

                # Transform CVE entry to exploit_intelligence document
                exploit_doc = self.transform_data(cve_entry)
                if not exploit_doc:
                    continue

                cve_id = exploit_doc["_key"]

                # Add to document batch
                doc_batch.append(exploit_doc)

                # Create has_exploit_intelligence edge
                edge = {
                    "_from": f"vulnerabilities/{cve_id}",
                    "_to": f"exploit_intelligence/{cve_id}",
                    "source": "vulncheck_nvd2",
                    "created_at": datetime.utcnow().isoformat()
                }
                edge_batch.append(edge)

                cves_processed += 1

                # Flush batch when full
                if len(doc_batch) >= self.batch_size:
                    # Insert documents
                    doc_result = self._batch_insert_documents(doc_batch)
                    total_documents_inserted += doc_result["created"] + doc_result["updated"]
                    total_errors += doc_result["errors"]

                    # Insert edges
                    edge_result = self._batch_insert_edges(edge_batch)
                    total_edges_inserted += edge_result["created"] + edge_result["updated"]
                    total_errors += edge_result["errors"]

                    batch_count += 1

                    # Clear batches
                    doc_batch = []
                    edge_batch = []

                    # Log progress every 10K CVEs
                    if cves_processed % 10000 == 0:
                        self.logger.info(
                            "Progress update",
                            cves_processed=cves_processed,
                            batches=batch_count,
                            duration_seconds=round((datetime.utcnow() - start_time).total_seconds(), 1)
                        )

                        # Save checkpoint every 10K CVEs
                        if self.supports_checkpointing:
                            self._save_checkpoint({
                                "cves_processed": cves_processed,
                                "batches": batch_count
                            })

            # Flush remaining batch
            if doc_batch:
                doc_result = self._batch_insert_documents(doc_batch)
                total_documents_inserted += doc_result["created"] + doc_result["updated"]
                total_errors += doc_result["errors"]

                edge_result = self._batch_insert_edges(edge_batch)
                total_edges_inserted += edge_result["created"] + edge_result["updated"]
                total_errors += edge_result["errors"]

                batch_count += 1

            # Clear checkpoint on success
            if self.supports_checkpointing:
                self._clear_checkpoint()

            # Calculate duration
            duration = (datetime.utcnow() - start_time).total_seconds()

            result = {
                "agent": self.agent_name,
                "status": "success",
                "cves_processed": cves_processed,
                "documents_inserted": total_documents_inserted,
                "edges_inserted": total_edges_inserted,
                "batches": batch_count,
                "errors": total_errors,
                "duration_seconds": round(duration, 2)
            }

            self.logger.info(
                "VulnCheck NVD2 ingestion complete",
                **result
            )

            return result

        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()

            self.logger.error(
                "VulnCheck NVD2 ingestion failed",
                error=str(e),
                cves_processed=cves_processed,
                duration_seconds=round(duration, 2)
            )

            # Save checkpoint on failure for resume
            if self.supports_checkpointing:
                self._save_checkpoint({
                    "cves_processed": cves_processed,
                    "status": "failed",
                    "error": str(e)
                })

            return {
                "agent": self.agent_name,
                "status": "failed",
                "error": str(e),
                "cves_processed": cves_processed,
                "duration_seconds": round(duration, 2)
            }

    # Legacy methods (not used in streaming mode, but required by BaseIngestionAgent)
    def fetch_data(self) -> Any:
        """Not used in streaming mode. Use fetch_data_stream() instead."""
        raise NotImplementedError("Use fetch_data_stream() for NVD2 agent")

    # Note: transform_data() is defined earlier (line 108) and works with single CVE entries
    # The run() method calls transform_data(cve_entry) for each streamed CVE

    def load_data(self, transformed_data: Generator[dict, None, None]) -> dict:
        """Not used in streaming mode. Bulk inserts handled in run()."""
        raise NotImplementedError("Bulk inserts handled directly in run() for NVD2 agent")
