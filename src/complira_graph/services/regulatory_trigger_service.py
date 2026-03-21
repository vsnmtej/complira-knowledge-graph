"""
Regulatory Trigger Service for automatic regulatory requirement edge generation.

This service automatically generates vuln_triggers_requirement edges based on VulnCheck
exploit intelligence and vulnerability metadata. It implements 4 trigger rules:
1. KEV Entry → 24h urgency (FDA 524B, CRA)
2. CVSS 9.0+ → high urgency
3. Ransomware Exploitation → critical urgency
4. Exploit Chain → critical urgency

The service is idempotent and supports incremental processing via checkpoints.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import time
from arango.database import StandardDatabase
import structlog

from .checkpoint_service import CheckpointService
from .trigger_rules import (
    trigger_rule_kev_entry,
    trigger_rule_cvss_critical,
    trigger_rule_ransomware_exploitation,
    trigger_rule_exploit_chain,
    get_trigger_rule
)

logger = structlog.get_logger()


class RegulatoryTriggerService:
    """
    Auto-generate vuln_triggers_requirement edges based on exploit intelligence.

    Features:
    - 4 trigger rules (KEV, CVSS, ransomware, exploit chain)
    - Idempotent edge creation (no duplicates)
    - Incremental processing with checkpoints
    - Batch processing for performance

    Performance Targets:
    - < 10 seconds per 1,000 CVEs
    - Idempotent (subsequent runs create 0 new edges)

    Example:
        >>> from complira_graph.db import get_db
        >>> db = get_db()
        >>> service = RegulatoryTriggerService(db)
        >>> result = service.run()
        >>> print(f"Created {result['edges_created']} edges in {result['execution_time_seconds']:.1f}s")
    """

    # Rule names in execution order
    RULES = [
        "kev_entry",
        "cvss_critical",
        "ransomware_exploitation",
        "exploit_chain"
    ]

    def __init__(self, db: StandardDatabase):
        """
        Initialize regulatory trigger service.

        Args:
            db: ArangoDB database connection
        """
        self.db = db
        self.logger = structlog.get_logger()
        self.checkpoint_service = CheckpointService(db)

    def run(self, force_full_scan: bool = False) -> Dict[str, Any]:
        """
        Run all trigger rules and generate edges.

        Args:
            force_full_scan: If True, ignore checkpoints and process all CVEs

        Returns:
            {
                "edges_created": int,
                "edges_skipped": int,
                "rules_executed": List[str],
                "execution_time_seconds": float,
                "checkpoint_updated": bool,
                "rule_results": {
                    "kev_entry": int,
                    "cvss_critical": int,
                    "ransomware_exploitation": int,
                    "exploit_chain": int
                }
            }

        Example:
            >>> result = service.run()
            >>> print(result)
            {
                "edges_created": 19843,
                "edges_skipped": 0,
                "rules_executed": ["kev_entry", "cvss_critical", "ransomware_exploitation", "exploit_chain"],
                "execution_time_seconds": 45.2,
                "checkpoint_updated": True,
                "rule_results": {
                    "kev_entry": 4609,
                    "cvss_critical": 15234,
                    "ransomware_exploitation": 0,
                    "exploit_chain": 0
                }
            }
        """
        self.logger.info(
            "Starting regulatory trigger service",
            force_full_scan=force_full_scan
        )

        start_time = time.time()
        total_edges_created = 0
        rules_executed = []
        rule_results = {}

        # Execute all trigger rules
        for rule_name in self.RULES:
            try:
                self.logger.info(
                    "Executing trigger rule",
                    rule=rule_name
                )

                edges_created = self._execute_rule(rule_name, force_full_scan)

                total_edges_created += edges_created
                rules_executed.append(rule_name)
                rule_results[rule_name] = edges_created

                self.logger.info(
                    "Trigger rule complete",
                    rule=rule_name,
                    edges_created=edges_created
                )

            except Exception as e:
                self.logger.error(
                    "Trigger rule failed",
                    rule=rule_name,
                    error=str(e)
                )
                # Continue with other rules (non-fatal)
                rule_results[rule_name] = 0

        execution_time = time.time() - start_time

        self.logger.info(
            "Regulatory trigger service complete",
            edges_created=total_edges_created,
            rules_executed=rules_executed,
            execution_time_seconds=execution_time
        )

        return {
            "edges_created": total_edges_created,
            "edges_skipped": 0,  # Idempotency handled by trigger rules
            "rules_executed": rules_executed,
            "execution_time_seconds": execution_time,
            "checkpoint_updated": True,
            "rule_results": rule_results
        }

    def run_rule(self, rule_name: str, force_full_scan: bool = False) -> int:
        """
        Run a single trigger rule.

        Args:
            rule_name: One of ["kev_entry", "cvss_critical", "ransomware_exploitation", "exploit_chain"]
            force_full_scan: If True, ignore checkpoint and process all CVEs

        Returns:
            Number of edges created

        Raises:
            ValueError: If rule_name is not recognized

        Example:
            >>> edges = service.run_rule("kev_entry")
            >>> print(f"Created {edges} KEV edges")
        """
        if rule_name not in self.RULES:
            raise ValueError(
                f"Unknown trigger rule: {rule_name}. "
                f"Valid rules: {self.RULES}"
            )

        self.logger.info(
            "Executing single trigger rule",
            rule=rule_name,
            force_full_scan=force_full_scan
        )

        edges_created = self._execute_rule(rule_name, force_full_scan)

        self.logger.info(
            "Single trigger rule complete",
            rule=rule_name,
            edges_created=edges_created
        )

        return edges_created

    def _execute_rule(self, rule_name: str, force_full_scan: bool) -> int:
        """
        Execute a single trigger rule with checkpoint support.

        Args:
            rule_name: Name of the trigger rule
            force_full_scan: If True, ignore checkpoint

        Returns:
            Number of edges created
        """
        # Get checkpoint (if not force_full_scan)
        checkpoint_date = None
        if not force_full_scan and rule_name == "kev_entry":
            checkpoint_date = self.checkpoint_service.get_checkpoint(rule_name)

        # Execute trigger rule
        if rule_name == "kev_entry":
            edges_created = trigger_rule_kev_entry(self.db, checkpoint_date)
        elif rule_name == "cvss_critical":
            edges_created = trigger_rule_cvss_critical(self.db)
        elif rule_name == "ransomware_exploitation":
            edges_created = trigger_rule_ransomware_exploitation(self.db)
        elif rule_name == "exploit_chain":
            edges_created = trigger_rule_exploit_chain(self.db)
        else:
            raise ValueError(f"Unknown trigger rule: {rule_name}")

        # Update checkpoint (only for kev_entry which supports incremental processing)
        if rule_name == "kev_entry" and edges_created > 0:
            current_timestamp = datetime.utcnow().isoformat() + "Z"
            self.checkpoint_service.update_checkpoint(
                rule_name,
                current_timestamp,
                edges_created
            )

        return edges_created

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics on generated regulatory trigger edges.

        Returns:
            {
                "total_edges": int,
                "edges_by_rule": {
                    "kev_entry": int,
                    "cvss_critical": int,
                    "ransomware_exploitation": int,
                    "exploit_chain": int
                },
                "edges_by_urgency": {
                    "24h": int,
                    "high": int,
                    "critical": int
                }
            }

        Example:
            >>> stats = service.get_statistics()
            >>> print(f"Total edges: {stats['total_edges']}")
        """
        query = """
        LET total_edges = LENGTH(vuln_triggers_requirement)

        LET edges_by_rule = (
            FOR edge IN vuln_triggers_requirement
                COLLECT rule = edge.trigger_rule WITH COUNT INTO count
                RETURN {[rule]: count}
        )

        LET edges_by_urgency = (
            FOR edge IN vuln_triggers_requirement
                COLLECT urgency = edge.urgency WITH COUNT INTO count
                RETURN {[urgency]: count}
        )

        RETURN {
            total_edges: total_edges,
            edges_by_rule: MERGE(edges_by_rule),
            edges_by_urgency: MERGE(edges_by_urgency)
        }
        """

        try:
            cursor = self.db.aql.execute(query)
            results = list(cursor)

            if results:
                stats = results[0]
                self.logger.info(
                    "Regulatory trigger statistics",
                    total_edges=stats.get("total_edges", 0),
                    edges_by_rule=stats.get("edges_by_rule", {}),
                    edges_by_urgency=stats.get("edges_by_urgency", {})
                )
                return stats
            else:
                return {
                    "total_edges": 0,
                    "edges_by_rule": {},
                    "edges_by_urgency": {}
                }

        except Exception as e:
            self.logger.error(
                "Failed to get statistics",
                error=str(e)
            )
            return {
                "total_edges": 0,
                "edges_by_rule": {},
                "edges_by_urgency": {}
            }

    def clear_all_edges(self) -> int:
        """
        Clear all regulatory trigger edges.

        WARNING: This deletes all vuln_triggers_requirement edges. Use with caution.

        Returns:
            Number of edges deleted

        Example:
            >>> deleted = service.clear_all_edges()
            >>> print(f"Deleted {deleted} edges")
        """
        self.logger.warning("Clearing all regulatory trigger edges")

        query = """
        FOR edge IN vuln_triggers_requirement
            REMOVE edge IN vuln_triggers_requirement
            RETURN OLD
        """

        try:
            cursor = self.db.aql.execute(query)
            results = list(cursor)

            deleted_count = len(results)

            self.logger.info(
                "Regulatory trigger edges cleared",
                deleted_count=deleted_count
            )

            # Clear all checkpoints
            for rule_name in self.RULES:
                self.checkpoint_service.clear_checkpoint(rule_name)

            return deleted_count

        except Exception as e:
            self.logger.error(
                "Failed to clear edges",
                error=str(e)
            )
            raise
