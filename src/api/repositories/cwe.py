"""
CWE repository.

Handles database access for CWE hierarchy queries:
- Get parent CWE
- Get full CWE hierarchy
- Roll up CWE to target abstraction level (Class, Pillar)
"""

from typing import List, Dict, Any, Optional
from api.repositories.base import BaseRepository
from complira_graph.models import Weakness
import structlog

logger = structlog.get_logger()


class CWERepository(BaseRepository):
    """
    Repository for CWE hierarchy queries against reference database.

    All methods query the reference database (complira_graph_reference)
    for CWE weakness data and hierarchy traversals.
    """

    def __init__(self, db):
        """
        Initialize CWE repository.

        Args:
            db: Reference database instance (complira_graph_reference)
        """
        super().__init__(db, "weaknesses")

    def get_parent_cwe(self, cwe_id: str) -> Optional[Weakness]:
        """
        Get parent CWE via child_of edge.

        Args:
            cwe_id: CWE identifier (e.g., "CWE-79")

        Returns:
            Weakness model or None if no parent found
        """
        query = """
        FOR cwe IN weaknesses
            FILTER cwe.cwe_id == @cwe_id
            LIMIT 1
            LET parent = FIRST(
                FOR p IN 1..1 OUTBOUND cwe._id child_of
                    RETURN p
            )
            FILTER parent != null
            RETURN parent
        """

        cursor = self.db.aql_execute(query, bind_vars={"cwe_id": cwe_id})
        results = list(cursor)

        if not results:
            logger.debug("No parent CWE found", cwe_id=cwe_id)
            return None

        return Weakness(**results[0])

    def get_cwe_hierarchy(self, cwe_id: str, max_depth: int = 10) -> List[Weakness]:
        """
        Get full CWE hierarchy from child to root.

        Args:
            cwe_id: CWE identifier
            max_depth: Maximum traversal depth

        Returns:
            List of Weakness models from child → parent → ... → root
        """
        query = """
        FOR cwe IN weaknesses
            FILTER cwe.cwe_id == @cwe_id
            LIMIT 1
            LET hierarchy = (
                FOR v, e, p IN 0..@max_depth OUTBOUND cwe._id child_of
                    RETURN v
            )
            RETURN hierarchy
        """

        cursor = self.db.aql_execute(
            query,
            bind_vars={"cwe_id": cwe_id, "max_depth": max_depth}
        )
        results = list(cursor)

        if not results or not results[0]:
            logger.debug("CWE hierarchy not found", cwe_id=cwe_id)
            return []

        return [Weakness(**cwe_dict) for cwe_dict in results[0]]

    def rollup_to_abstraction_level(
        self, cwe_id: str, target_level: str = "Class"
    ) -> Optional[Weakness]:
        """
        Roll up CWE to target abstraction level.

        Traverses parent hierarchy until finding CWE at target abstraction level.
        If no parent at target level found, returns original CWE.

        Args:
            cwe_id: CWE identifier
            target_level: Target abstraction level ("Class" or "Pillar")

        Returns:
            Weakness model at target level or original CWE if no parent found
        """
        query = """
        FOR cwe IN weaknesses
            FILTER cwe.cwe_id == @cwe_id
            LIMIT 1

            // Traverse up parent hierarchy to find target abstraction level
            LET parent_chain = (
                FOR v, e, p IN 0..10 OUTBOUND cwe._id child_of
                    FILTER v.abstraction == @target_level OR v.abstraction == "Pillar"
                    LIMIT 1
                    RETURN v
            )

            // Use parent if found, otherwise keep original CWE
            LET rolled_up = LENGTH(parent_chain) > 0 ? parent_chain[0] : cwe

            RETURN rolled_up
        """

        cursor = self.db.aql_execute(
            query,
            bind_vars={"cwe_id": cwe_id, "target_level": target_level}
        )
        results = list(cursor)

        if not results:
            logger.debug("CWE not found for rollup", cwe_id=cwe_id)
            return None

        return Weakness(**results[0])

    def batch_rollup_to_abstraction_level(
        self, cwe_ids: List[str], target_level: str = "Class"
    ) -> Dict[str, Weakness]:
        """
        Batch roll up multiple CWEs to target abstraction level.

        Args:
            cwe_ids: List of CWE identifiers
            target_level: Target abstraction level ("Class" or "Pillar")

        Returns:
            Dict mapping original CWE ID → rolled-up Weakness model
        """
        if not cwe_ids:
            return {}

        query = """
        FOR cwe_id IN @cwe_ids
            LET cwe = FIRST(
                FOR w IN weaknesses
                    FILTER w.cwe_id == cwe_id
                    RETURN w
            )
            FILTER cwe != null

            // Traverse up parent hierarchy to find target abstraction level
            LET parent_chain = (
                FOR v, e, p IN 0..10 OUTBOUND cwe._id child_of
                    FILTER v.abstraction == @target_level OR v.abstraction == "Pillar"
                    LIMIT 1
                    RETURN v
            )

            // Use parent if found, otherwise keep original CWE
            LET rolled_up = LENGTH(parent_chain) > 0 ? parent_chain[0] : cwe

            RETURN {
                original_cwe_id: cwe_id,
                rolled_up_cwe: rolled_up
            }
        """

        cursor = self.db.aql_execute(
            query,
            bind_vars={"cwe_ids": cwe_ids, "target_level": target_level}
        )
        results = list(cursor)

        logger.debug(
            "Batch rolled up CWEs",
            requested=len(cwe_ids),
            found=len(results),
            target_level=target_level
        )

        return {
            result['original_cwe_id']: Weakness(**result['rolled_up_cwe'])
            for result in results
        }
