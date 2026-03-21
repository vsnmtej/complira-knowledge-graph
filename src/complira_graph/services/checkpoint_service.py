"""
Checkpoint service for tracking regulatory trigger rule execution progress.

This module provides checkpoint management for incremental processing of trigger rules,
allowing the RegulatoryTriggerService to resume from the last processed timestamp.
"""

from typing import Optional
from datetime import datetime
from arango.database import StandardDatabase
import structlog

logger = structlog.get_logger()


class CheckpointService:
    """
    Manage checkpoints for incremental trigger rule execution.

    Checkpoints are stored in the agent_checkpoints collection with the following schema:
    {
        "_key": "regulatory_trigger_service_{rule_name}",
        "agent_name": "regulatory_trigger_service",
        "rule_name": "{rule_name}",
        "last_processed_timestamp": "2026-03-05T12:00:00Z",
        "last_processed_count": 4609,
        "updated_at": "2026-03-05T12:05:00Z"
    }
    """

    def __init__(self, db: StandardDatabase):
        """
        Initialize checkpoint service.

        Args:
            db: ArangoDB database connection
        """
        self.db = db
        self.logger = structlog.get_logger()
        self.collection_name = "agent_checkpoints"

    def get_checkpoint(self, rule_name: str) -> Optional[str]:
        """
        Get last processed timestamp for a trigger rule.

        Args:
            rule_name: Name of the trigger rule (e.g., "kev_entry", "cvss_critical")

        Returns:
            Last processed timestamp (ISO 8601 format) or None if no checkpoint exists

        Example:
            >>> service = CheckpointService(db)
            >>> timestamp = service.get_checkpoint("kev_entry")
            >>> print(timestamp)  # "2026-03-05T12:00:00Z" or None
        """
        checkpoint_key = f"regulatory_trigger_service_{rule_name}"

        self.logger.debug(
            "Loading checkpoint",
            rule_name=rule_name,
            checkpoint_key=checkpoint_key
        )

        try:
            query = """
            FOR c IN agent_checkpoints
                FILTER c._key == @key
                RETURN c
            """

            cursor = self.db.aql.execute(query, bind_vars={"key": checkpoint_key})
            results = list(cursor)

            if not results:
                self.logger.info(
                    "No checkpoint found",
                    rule_name=rule_name,
                    checkpoint_key=checkpoint_key
                )
                return None

            checkpoint = results[0]
            timestamp = checkpoint.get("last_processed_timestamp")

            # Validate timestamp format (ISO 8601)
            if timestamp:
                try:
                    datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                except ValueError:
                    self.logger.warning(
                        "Invalid checkpoint timestamp format, ignoring checkpoint",
                        rule_name=rule_name,
                        timestamp=timestamp
                    )
                    return None

            self.logger.debug(
                "Checkpoint loaded",
                rule_name=rule_name,
                timestamp=timestamp,
                count=checkpoint.get("last_processed_count")
            )

            return timestamp

        except Exception as e:
            self.logger.error(
                "Failed to load checkpoint",
                rule_name=rule_name,
                error=str(e)
            )
            # Return None to fall back to full scan
            return None

    def update_checkpoint(
        self,
        rule_name: str,
        timestamp: str,
        count: int
    ) -> bool:
        """
        Update checkpoint after successful rule execution.

        Args:
            rule_name: Name of the trigger rule
            timestamp: Last processed timestamp (ISO 8601 format)
            count: Number of edges created in this run

        Returns:
            True if checkpoint updated successfully, False otherwise

        Example:
            >>> service = CheckpointService(db)
            >>> success = service.update_checkpoint("kev_entry", "2026-03-05T13:00:00Z", 150)
            >>> print(success)  # True
        """
        checkpoint_key = f"regulatory_trigger_service_{rule_name}"

        self.logger.debug(
            "Updating checkpoint",
            rule_name=rule_name,
            timestamp=timestamp,
            count=count
        )

        try:
            checkpoint_doc = {
                "_key": checkpoint_key,
                "agent_name": "regulatory_trigger_service",
                "rule_name": rule_name,
                "last_processed_timestamp": timestamp,
                "last_processed_count": count,
                "updated_at": datetime.utcnow().isoformat() + "Z"
            }

            collection = self.db.collection(self.collection_name)
            collection.insert(checkpoint_doc, overwrite=True)

            self.logger.info(
                "Checkpoint updated",
                rule_name=rule_name,
                timestamp=timestamp,
                count=count
            )

            return True

        except Exception as e:
            self.logger.error(
                "Failed to update checkpoint",
                rule_name=rule_name,
                error=str(e)
            )
            # Checkpoint failure is non-fatal (log and continue)
            return False

    def clear_checkpoint(self, rule_name: str) -> bool:
        """
        Clear checkpoint for a trigger rule.

        Useful for forcing a full scan on next execution.

        Args:
            rule_name: Name of the trigger rule

        Returns:
            True if checkpoint cleared successfully, False otherwise
        """
        checkpoint_key = f"regulatory_trigger_service_{rule_name}"

        self.logger.info(
            "Clearing checkpoint",
            rule_name=rule_name,
            checkpoint_key=checkpoint_key
        )

        try:
            collection = self.db.collection(self.collection_name)

            if collection.has(checkpoint_key):
                collection.delete(checkpoint_key)
                self.logger.info(
                    "Checkpoint cleared",
                    rule_name=rule_name
                )
            else:
                self.logger.debug(
                    "Checkpoint does not exist, nothing to clear",
                    rule_name=rule_name
                )

            return True

        except Exception as e:
            self.logger.error(
                "Failed to clear checkpoint",
                rule_name=rule_name,
                error=str(e)
            )
            return False
