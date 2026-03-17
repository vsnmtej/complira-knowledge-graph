"""
Base classes for all ingestion and LLM enrichment agents.

Implements SOLID principles:
- Single Responsibility: Each agent handles ONE data source
- Open/Closed: Extensible via inheritance, closed for modification
- Liskov Substitution: All agents interchangeable via base interface
- Interface Segregation: Separate interfaces for deterministic vs LLM agents
- Dependency Inversion: Depends on StandardDatabase abstraction

This module provides:
- BaseIngestionAgent: For deterministic data source ingestion (NVD, CWE, ATT&CK, etc.)
- BaseLLMAgent: For LLM-based enrichment (CWE classification, VEX generation, etc.)
"""

from abc import ABC, abstractmethod
from typing import Any, Generator, Optional
from datetime import datetime
from arango.database import StandardDatabase
import structlog

from ..config import get_settings
from ..utils.transforms import batch_iterator

logger = structlog.get_logger()


class BaseIngestionAgent(ABC):
    """
    Abstract base class for deterministic data ingestion agents.

    All ingestion agents (NVD, CWE, ATT&CK, CAPEC, etc.) inherit from this class.

    Lifecycle:
    1. fetch_data() - Retrieve data from external source
    2. transform_data() - Transform to graph nodes/edges
    3. load_data() - Bulk insert into ArangoDB
    4. run() - Orchestrate the full workflow

    Example:
        class NVDAgent(BaseIngestionAgent):
            def fetch_data(self):
                # Fetch from NVD API
                ...

            def transform_data(self, raw_data):
                # Transform to CVE nodes + edges
                ...
    """

    # ========== Checkpoint Configuration (Override in subclass) ==========
    supports_checkpointing = False  # Set to True in agents that need resume support
    checkpoint_interval = 100       # Save checkpoint every N iterations

    def __init__(self, db: StandardDatabase):
        """
        Initialize base ingestion agent.

        Args:
            db: ArangoDB database instance
        """
        self.db = db
        self.agent_name = self.__class__.__name__
        self.settings = get_settings()
        self.logger = logger.bind(agent=self.agent_name)

        self.logger.info("Agent initialized")

    # ========== Checkpoint Methods (Auto-Resume Support) ==========

    def _save_checkpoint(self, checkpoint_data: dict) -> None:
        """
        Internal: Save agent execution checkpoint to database.

        Args:
            checkpoint_data: Checkpoint state (e.g., {"page": 1000, "total": 100000})
        """
        if not self.supports_checkpointing:
            return

        try:
            checkpoints_collection = self.db.collection("agent_checkpoints")

            checkpoint_doc = {
                "_key": self.agent_name,
                "agent_name": self.agent_name,
                "checkpoint_data": checkpoint_data,
                "last_updated": datetime.utcnow().isoformat(),
                "status": "in_progress",
            }

            checkpoints_collection.insert(
                checkpoint_doc,
                overwrite=True,
            )

            self.logger.debug("Checkpoint saved", **checkpoint_data)

        except Exception as e:
            self.logger.warning("Failed to save checkpoint", error=str(e))

    def _load_checkpoint(self) -> Optional[dict]:
        """
        Internal: Load agent execution checkpoint from database.

        Returns:
            dict | None: Checkpoint data if exists, None otherwise
        """
        if not self.supports_checkpointing:
            return None

        try:
            checkpoints_collection = self.db.collection("agent_checkpoints")

            if checkpoints_collection.has(self.agent_name):
                checkpoint_doc = checkpoints_collection.get(self.agent_name)
                checkpoint_data = checkpoint_doc.get("checkpoint_data", {})

                self.logger.info(
                    "Checkpoint found - resuming from last state",
                    **checkpoint_data,
                )

                return checkpoint_data

        except Exception as e:
            self.logger.warning("Failed to load checkpoint", error=str(e))

        return None

    def _clear_checkpoint(self) -> None:
        """
        Internal: Clear agent execution checkpoint after successful completion.
        """
        if not self.supports_checkpointing:
            return

        try:
            checkpoints_collection = self.db.collection("agent_checkpoints")

            if checkpoints_collection.has(self.agent_name):
                checkpoints_collection.delete(self.agent_name)
                self.logger.info("Checkpoint cleared")

        except Exception as e:
            self.logger.warning("Failed to clear checkpoint", error=str(e))

    @abstractmethod
    def fetch_data(self) -> Any:
        """
        Fetch data from external source.

        This method should:
        - Handle API authentication
        - Implement rate limiting
        - Handle pagination
        - Return raw data (JSON, XML, etc.)

        Returns:
            Any: Raw data from source (format depends on source)

        Raises:
            Exception: On fetch failure (should be caught by orchestrator)
        """
        pass

    @abstractmethod
    def transform_data(self, raw_data: Any) -> Generator[dict, None, None]:
        """
        Transform raw data to graph nodes and edges.

        This method should:
        - Parse raw data format
        - Extract relevant fields
        - Normalize IDs to _key format
        - Yield documents and edges separately

        Args:
            raw_data: Raw data from fetch_data()

        Yields:
            dict: ArangoDB documents or edges with _key, _from, _to fields

        Example:
            def transform_data(self, raw_data):
                for cve in raw_data["vulnerabilities"]:
                    # Yield CVE document
                    yield {
                        "_key": normalize_key(cve["id"], "cve"),
                        "cve_id": cve["id"],
                        "description": cve["description"],
                        ...
                    }

                    # Yield has_weakness edges
                    for cwe_id in cve["cwes"]:
                        yield {
                            "_from": f"vulnerabilities/{normalize_key(cve['id'], 'cve')}",
                            "_to": f"weaknesses/{normalize_key(cwe_id, 'cwe')}",
                            "source": "nvd",
                        }
        """
        pass

    def load_data(
        self,
        records: Generator[dict, None, None],
        collection_name: str,
        on_duplicate: str = "update"
    ) -> dict:
        """
        Bulk load data into ArangoDB collection.

        Uses import_bulk() for performance (200× faster than UPSERT).
        Batches records to avoid memory issues.

        Args:
            records: Generator of documents/edges
            collection_name: Target collection name
            on_duplicate: Action on duplicate _key ("update", "replace", "ignore")

        Returns:
            dict: Import statistics (created, updated, errors)

        Example:
            records = self.transform_data(raw_data)
            stats = self.load_data(records, "vulnerabilities", on_duplicate="update")
        """
        if not self.db.has_collection(collection_name):
            self.logger.error(
                "Collection does not exist",
                collection=collection_name,
            )
            raise ValueError(f"Collection {collection_name} does not exist")

        collection = self.db.collection(collection_name)
        total_created = 0
        total_updated = 0
        total_errors = 0

        # Process in batches for performance
        for batch in batch_iterator(records, batch_size=self.settings.BULK_IMPORT_BATCH_SIZE):
            try:
                result = collection.import_bulk(
                    batch,
                    on_duplicate=on_duplicate,
                    details=True,
                )

                total_created += result.get("created", 0)
                total_updated += result.get("updated", 0)
                total_errors += result.get("errors", 0)

                self.logger.debug(
                    "Batch imported",
                    collection=collection_name,
                    batch_size=len(batch),
                    created=result.get("created", 0),
                    updated=result.get("updated", 0),
                    errors=result.get("errors", 0),
                )

            except Exception as e:
                self.logger.error(
                    "Batch import failed",
                    collection=collection_name,
                    error=str(e),
                )
                total_errors += len(batch)

        stats = {
            "created": total_created,
            "updated": total_updated,
            "errors": total_errors,
            "total": total_created + total_updated + total_errors,
        }

        self.logger.info(
            "Data load complete",
            collection=collection_name,
            **stats,
        )

        return stats

    def run(self) -> dict:
        """
        Execute full ingestion workflow with auto-checkpoint support.

        Orchestrates:
        1. Load checkpoint (if supports_checkpointing=True)
        2. Fetch data from source (agent can access self._checkpoint)
        3. Transform to graph format
        4. Load into database
        5. Clear checkpoint on success

        Returns:
            dict: Execution statistics

        Raises:
            Exception: On workflow failure
        """
        start_time = datetime.now()

        self.logger.info("Agent execution started")

        try:
            # Step 0: Load checkpoint (for resume support)
            self._checkpoint = self._load_checkpoint()

            # Step 1: Fetch
            self.logger.info("Fetching data")
            raw_data = self.fetch_data()

            # Step 2: Transform
            self.logger.info("Transforming data")
            records = self.transform_data(raw_data)

            # Step 3: Load
            # Note: Subclasses should override this if they need to load into multiple collections
            self.logger.info("Loading data")
            stats = self.load_data(records, self._get_primary_collection())

            execution_time = (datetime.now() - start_time).total_seconds()

            # Step 4: Clear checkpoint on success
            self._clear_checkpoint()

            result = {
                "agent": self.agent_name,
                "status": "success",
                "execution_time_seconds": execution_time,
                **stats,
            }

            self.logger.info(
                "Agent execution completed",
                **result,
            )

            return result

        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()

            self.logger.error(
                "Agent execution failed",
                error=str(e),
                execution_time_seconds=execution_time,
            )

            return {
                "agent": self.agent_name,
                "status": "failed",
                "error": str(e),
                "execution_time_seconds": execution_time,
            }

    @abstractmethod
    def _get_primary_collection(self) -> str:
        """
        Get primary collection name for this agent.

        Returns:
            str: Collection name

        Example:
            def _get_primary_collection(self):
                return "vulnerabilities"
        """
        pass


class BaseLLMAgent(ABC):
    """
    Abstract base class for LLM enrichment agents.

    All LLM agents (CWE classifier, PURL→CPE, VEX synthesizer, etc.) inherit from this class.

    Lifecycle:
    1. find_gaps() - Identify records needing enrichment
    2. enrich() - Call LLM to generate enrichment
    3. validate() - Validate enrichment quality
    4. persist() - Save enrichment + provenance

    Example:
        class CWEClassifierAgent(BaseLLMAgent):
            def find_gaps(self):
                # Find CVEs without CWE
                ...

            def enrich(self, record):
                # Call Claude to classify CWE
                ...
    """

    def __init__(self, db: StandardDatabase, anthropic_client):
        """
        Initialize base LLM agent.

        Args:
            db: ArangoDB database instance
            anthropic_client: Anthropic API client
        """
        self.db = db
        self.anthropic_client = anthropic_client
        self.agent_name = self.__class__.__name__
        self.settings = get_settings()
        self.logger = logger.bind(agent=self.agent_name)

        self.logger.info("LLM agent initialized")

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        """
        Strip markdown code fences from LLM response.

        Claude 4 models often wrap JSON in ```json ... ``` even when
        instructed to return only JSON. This helper removes those fences.

        Args:
            text: Response text from LLM

        Returns:
            str: Cleaned text without markdown fences
        """
        text = text.strip()
        if text.startswith('```'):
            # Remove opening fence (```json or ```)
            lines = text.split('\n')
            lines = lines[1:]  # Skip first line
            # Remove closing fence
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            text = '\n'.join(lines)
        return text

    @abstractmethod
    def find_gaps(self) -> list[dict]:
        """
        Find records that need LLM enrichment.

        This method should:
        - Query database for incomplete records
        - Return list of records to enrich
        - Limit batch size to control costs

        Returns:
            list[dict]: Records needing enrichment

        Example:
            def find_gaps(self):
                query = '''
                    FOR cve IN vulnerabilities
                        FILTER LENGTH(
                            FOR v, e IN 1..1 OUTBOUND cve has_weakness
                                RETURN 1
                        ) == 0
                        LIMIT 1000
                        RETURN {cve_id: cve.cve_id, description: cve.description}
                '''
                return list(self.db.aql.execute(query))
        """
        pass

    @abstractmethod
    def enrich(self, record: dict) -> dict:
        """
        Generate enrichment for a single record using LLM.

        This method should:
        - Construct prompt with record data
        - Call Anthropic API
        - Parse LLM response
        - Return enrichment with provenance

        Args:
            record: Record to enrich

        Returns:
            dict: Enrichment data with provenance metadata

        Example:
            def enrich(self, record):
                response = self.anthropic_client.messages.create(
                    model="claude-haiku-4.5",
                    max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}]
                )
                result = json.loads(response.content[0].text)
                return {
                    "cve_id": record["cve_id"],
                    "cwe_id": result["cwe_id"],
                    "confidence": result["confidence"],
                    "model": "claude-haiku-4.5",
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                }
        """
        pass

    @abstractmethod
    def validate(self, enrichment: dict) -> bool:
        """
        Validate enrichment quality.

        This method should:
        - Check confidence thresholds
        - Validate output format
        - Verify logical consistency

        Args:
            enrichment: Enrichment data from enrich()

        Returns:
            bool: True if enrichment is valid

        Example:
            def validate(self, enrichment):
                return enrichment.get("confidence", 0.0) >= 0.85
        """
        pass

    @abstractmethod
    def persist(self, enrichment: dict) -> None:
        """
        Save enrichment and provenance to database.

        This method should:
        - Create edges/documents with enrichment
        - Store provenance in llm_enrichments collection
        - Track token usage for cost monitoring

        Args:
            enrichment: Validated enrichment data

        Example:
            def persist(self, enrichment):
                # Create edge
                edge = {
                    "_from": f"vulnerabilities/{enrichment['cve_key']}",
                    "_to": f"weaknesses/{enrichment['cwe_key']}",
                    "confidence": enrichment["confidence"],
                    "source": "llm",
                }
                self.db.collection("has_weakness").insert(edge)

                # Store provenance
                provenance = {
                    "entity_type": "has_weakness",
                    "model": enrichment["model"],
                    "input_tokens": enrichment["input_tokens"],
                    "output_tokens": enrichment["output_tokens"],
                    "timestamp": datetime.utcnow().isoformat(),
                }
                self.db.collection("llm_enrichments").insert(provenance)
        """
        pass

    def run(self) -> dict:
        """
        Execute full LLM enrichment workflow.

        Orchestrates:
        1. Find gaps needing enrichment
        2. Enrich each record with LLM
        3. Validate enrichments
        4. Persist valid enrichments

        Returns:
            dict: Execution statistics
        """
        start_time = datetime.now()

        self.logger.info("LLM agent execution started")

        try:
            # Step 1: Find gaps
            self.logger.info("Finding gaps")
            gaps = self.find_gaps()

            self.logger.info("Gaps found", count=len(gaps))

            enriched_count = 0
            failed_count = 0
            skipped_count = 0

            # Step 2-4: Enrich, validate, persist
            for record in gaps:
                try:
                    # Enrich
                    enrichment = self.enrich(record)

                    # Validate
                    if self.validate(enrichment):
                        # Persist
                        self.persist(enrichment)
                        enriched_count += 1
                    else:
                        self.logger.debug("Enrichment validation failed", record=record)
                        skipped_count += 1

                except Exception as e:
                    self.logger.warning(
                        "Enrichment failed for record",
                        record=record,
                        error=str(e),
                    )
                    failed_count += 1

            execution_time = (datetime.now() - start_time).total_seconds()

            result = {
                "agent": self.agent_name,
                "status": "success",
                "execution_time_seconds": execution_time,
                "gaps_found": len(gaps),
                "enriched": enriched_count,
                "skipped": skipped_count,
                "failed": failed_count,
            }

            self.logger.info(
                "LLM agent execution completed",
                **result,
            )

            return result

        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()

            self.logger.error(
                "LLM agent execution failed",
                error=str(e),
                execution_time_seconds=execution_time,
            )

            return {
                "agent": self.agent_name,
                "status": "failed",
                "error": str(e),
                "execution_time_seconds": execution_time,
            }
