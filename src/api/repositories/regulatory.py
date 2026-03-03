"""
Regulatory repository.

Handles database access for regulatory control mappings:
- CWE → Regulatory Requirements
- CWE → NIST 800-53 Controls
- CWE → FDA 524B Requirements
- CWE → ISO 27001 Requirements
"""

from typing import List, Dict, Any, Optional
from api.repositories.base import BaseRepository
from complira_graph.models import RegulatoryRequirement, OSCALControl
import structlog

logger = structlog.get_logger()


class RegulatoryRepository(BaseRepository):
    """
    Repository for regulatory control mapping queries against reference database.

    All methods query the reference database (complira_graph_reference)
    for CWE → regulatory requirement/control mappings.
    """

    def __init__(self, db):
        """
        Initialize regulatory repository.

        Args:
            db: Reference database instance (complira_graph_reference)
        """
        super().__init__(db, "regulatory_requirements")

    def get_requirements_for_cwe(
        self, cwe_id: str, frameworks: Optional[List[str]] = None
    ) -> List[RegulatoryRequirement]:
        """
        Get regulatory requirements mapped to a CWE.

        Args:
            cwe_id: CWE identifier (e.g., "CWE-79")
            frameworks: Optional list of frameworks to filter by

        Returns:
            List of RegulatoryRequirement models
        """
        if frameworks:
            query = """
            FOR cwe IN weaknesses
                FILTER cwe.cwe_id == @cwe_id
                LIMIT 1
                LET requirements = (
                    FOR req IN 1..1 OUTBOUND cwe._id maps_to_requirement
                        FILTER req.framework IN @frameworks
                        RETURN req
                )
                RETURN requirements
            """
            bind_vars = {"cwe_id": cwe_id, "frameworks": frameworks}
        else:
            query = """
            FOR cwe IN weaknesses
                FILTER cwe.cwe_id == @cwe_id
                LIMIT 1
                LET requirements = (
                    FOR req IN 1..1 OUTBOUND cwe._id maps_to_requirement
                        RETURN req
                )
                RETURN requirements
            """
            bind_vars = {"cwe_id": cwe_id}

        cursor = self.db.aql_execute(query, bind_vars=bind_vars)
        results = list(cursor)

        if not results or not results[0]:
            logger.debug("No requirements found for CWE", cwe_id=cwe_id)
            return []

        return [RegulatoryRequirement(**req_dict) for req_dict in results[0]]

    def batch_get_requirements_for_cwes(
        self, cwe_ids: List[str], frameworks: Optional[List[str]] = None
    ) -> Dict[str, List[RegulatoryRequirement]]:
        """
        Batch get regulatory requirements for multiple CWEs.

        Args:
            cwe_ids: List of CWE identifiers
            frameworks: Optional list of frameworks to filter by

        Returns:
            Dict mapping CWE ID → list of RegulatoryRequirement models
        """
        if not cwe_ids:
            return {}

        if frameworks:
            query = """
            FOR cwe_id IN @cwe_ids
                LET cwe = FIRST(
                    FOR w IN weaknesses
                        FILTER w.cwe_id == cwe_id
                        RETURN w
                )
                FILTER cwe != null

                // Get regulatory requirements filtered by framework
                LET requirements = (
                    FOR req IN 1..1 OUTBOUND cwe._id maps_to_requirement
                        FILTER req.framework IN @frameworks
                        RETURN req
                )

                RETURN {
                    cwe_id: cwe_id,
                    requirements: requirements
                }
            """
            bind_vars = {"cwe_ids": cwe_ids, "frameworks": frameworks}
        else:
            query = """
            FOR cwe_id IN @cwe_ids
                LET cwe = FIRST(
                    FOR w IN weaknesses
                        FILTER w.cwe_id == cwe_id
                        RETURN w
                )
                FILTER cwe != null

                // Get all regulatory requirements
                LET requirements = (
                    FOR req IN 1..1 OUTBOUND cwe._id maps_to_requirement
                        RETURN req
                )

                RETURN {
                    cwe_id: cwe_id,
                    requirements: requirements
                }
            """
            bind_vars = {"cwe_ids": cwe_ids}

        cursor = self.db.aql_execute(query, bind_vars=bind_vars)
        results = list(cursor)

        logger.debug(
            "Batch fetched CWE → requirements",
            requested=len(cwe_ids),
            found=len(results),
            frameworks=frameworks
        )

        return {
            result['cwe_id']: [
                RegulatoryRequirement(**req_dict)
                for req_dict in result['requirements']
            ]
            for result in results
        }

    def get_nist_controls_for_cwe(self, cwe_id: str) -> List[OSCALControl]:
        """
        Get NIST 800-53 controls mapped to a CWE.

        Args:
            cwe_id: CWE identifier

        Returns:
            List of OSCALControl models
        """
        query = """
        FOR cwe IN weaknesses
            FILTER cwe.cwe_id == @cwe_id
            LIMIT 1
            LET requirements = (
                FOR req IN 1..1 OUTBOUND cwe._id maps_to_requirement
                    FILTER req.framework == "NIST 800-53"
                    RETURN req
            )
            LET controls = (
                FOR req IN requirements
                    FOR ctrl IN 1..1 OUTBOUND req._id implements_control
                        RETURN ctrl
            )
            RETURN controls
        """

        cursor = self.db.aql_execute(query, bind_vars={"cwe_id": cwe_id})
        results = list(cursor)

        if not results or not results[0]:
            logger.debug("No NIST controls found for CWE", cwe_id=cwe_id)
            return []

        return [OSCALControl(**ctrl_dict) for ctrl_dict in results[0]]

    def batch_get_nist_controls(
        self, requirement_ids: List[str]
    ) -> Dict[str, OSCALControl]:
        """
        Batch get NIST 800-53 controls for multiple requirement IDs.

        Args:
            requirement_ids: List of requirement IDs (e.g., ["NIST-800-53-SI-10", ...])

        Returns:
            Dict mapping requirement ID → OSCALControl model
        """
        if not requirement_ids:
            return {}

        query = """
        FOR req_id IN @requirement_ids
            LET req = FIRST(
                FOR r IN regulatory_requirements
                    FILTER r.requirement_id == req_id
                    RETURN r
            )
            FILTER req != null

            // Get OSCAL control details
            LET control = FIRST(
                FOR c IN 1..1 OUTBOUND req._id implements_control
                    RETURN c
            )

            FILTER control != null

            RETURN {
                requirement_id: req_id,
                control: control
            }
        """

        cursor = self.db.aql_execute(query, bind_vars={"requirement_ids": requirement_ids})
        results = list(cursor)

        logger.debug(
            "Batch fetched NIST controls",
            requested=len(requirement_ids),
            found=len(results)
        )

        return {
            result['requirement_id']: OSCALControl(**result['control'])
            for result in results
        }
