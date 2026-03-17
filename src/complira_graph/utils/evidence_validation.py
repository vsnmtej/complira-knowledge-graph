"""
Evidence validation query builder (DRY + Secure).

Builds AQL queries from structured specifications to check if required evidence exists.
Prevents SQL injection by using bind parameters instead of string concatenation.

Usage:
    from complira_graph.utils.evidence_validation import EvidenceValidator

    spec = {
        "collection": "sast_findings",
        "filters": {"tenant_id": "@tenant", "tool_name": ["semgrep", "bandit"]},
        "aggregation": "exists"
    }

    validator = EvidenceValidator()
    exists = validator.check_evidence_exists(db, requirement, "acme_corp")
"""

from typing import Dict, List, Any, Tuple, Optional
from arango.database import StandardDatabase
import structlog

logger = structlog.get_logger()


class EvidenceValidator:
    """
    Centralized evidence validation query builder (DRY + Secure).

    Responsibilities:
    - Build AQL queries from structured specs (no raw AQL injection)
    - Validate evidence exists for requirements
    - Calculate coverage metrics (e.g., CWE coverage %)
    - Check evidence freshness (scan_date < 90 days)
    """

    @staticmethod
    def build_query(spec: Dict[str, Any], bind_vars: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """
        Build secure AQL query from structured evidence specification.

        Prevents AQL injection by using bind parameters for all user inputs.

        Args:
            spec: Evidence specification
                {
                    "collection": str,  # Collection name (sanitized)
                    "filters": dict,    # Field filters with bind params
                    "aggregation": str, # exists | count | coverage_percentage
                    "cwe_coverage": list[str],  # For coverage_percentage
                    "freshness_days": int  # Optional: max age in days
                }
            bind_vars: Initial bind variables (will be extended)

        Returns:
            (query_string, bind_vars) tuple

        Example:
            >>> spec = {
            ...     "collection": "sast_findings",
            ...     "filters": {"tenant_id": "@tenant", "severity": ["high", "critical"]},
            ...     "aggregation": "count"
            ... }
            >>> query, binds = EvidenceValidator.build_query(spec, {"tenant": "acme"})
            >>> print(query)
            FOR doc IN sast_findings
                FILTER doc.tenant_id == @tenant
                FILTER doc.severity IN @severity
                COLLECT WITH COUNT INTO total RETURN total
        """
        collection = spec.get("collection", "")
        if not collection:
            raise ValueError("Evidence spec must include 'collection'")

        # Sanitize collection name (prevent injection)
        if not collection.replace("_", "").isalnum():
            raise ValueError(f"Invalid collection name: {collection}")

        filters = spec.get("filters", {})
        aggregation = spec.get("aggregation", "exists")

        # Build filter clauses with bind parameters
        filter_clauses = []

        for field, value in filters.items():
            # Sanitize field name (prevent injection)
            if not field.replace(".", "_").replace("[", "").replace("]", "").replace("*", "").isalnum():
                raise ValueError(f"Invalid field name: {field}")

            # Create bind parameter name (replace dots for valid param names)
            param_name = field.replace(".", "_").replace("[*]", "_array")

            if isinstance(value, list):
                filter_clauses.append(f"FILTER doc.{field} IN @{param_name}")
                bind_vars[param_name] = value
            elif isinstance(value, str) and value.startswith("@"):
                # Already a bind parameter reference
                param = value[1:]  # Remove @ prefix
                filter_clauses.append(f"FILTER doc.{field} == @{param}")
                # Don't add to bind_vars - caller should provide it
            else:
                filter_clauses.append(f"FILTER doc.{field} == @{param_name}")
                bind_vars[param_name] = value

        # Add freshness filter if specified
        freshness_days = spec.get("freshness_days")
        if freshness_days:
            filter_clauses.append(
                f"FILTER doc.scan_date >= DATE_SUBTRACT(DATE_NOW(), {int(freshness_days)}, 'day')"
            )

        # Build aggregation clause
        if aggregation == "exists":
            return_clause = "LIMIT 1 RETURN TRUE"

        elif aggregation == "count":
            return_clause = "COLLECT WITH COUNT INTO total RETURN total"

        elif aggregation == "coverage_percentage":
            # For CWE coverage: count(found_cwes) / count(required_cwes)
            required_cwes = spec.get("cwe_coverage", [])
            if not required_cwes:
                raise ValueError("coverage_percentage aggregation requires 'cwe_coverage' list")

            bind_vars["required_cwes"] = required_cwes

            return_clause = """
                LET found_cwes = UNIQUE(FLATTEN(doc[*].cwe_ids))
                LET covered = LENGTH(INTERSECTION(found_cwes, @required_cwes))
                LET total_required = LENGTH(@required_cwes)
                RETURN covered / total_required
            """

        elif aggregation == "list":
            return_clause = "RETURN doc"

        else:
            raise ValueError(f"Unknown aggregation type: {aggregation}")

        # Build final query
        query = f"""
        FOR doc IN {collection}
            {" ".join(filter_clauses)}
            {return_clause}
        """.strip()

        return (query, bind_vars)

    @classmethod
    def check_evidence_exists(
        cls,
        db: StandardDatabase,
        requirement: Dict[str, Any],
        tenant_id: str
    ) -> Dict[str, Any]:
        """
        Check if required evidence exists for a requirement.

        Args:
            db: ArangoDB database instance
            requirement: Requirement document with evidence_types array
            tenant_id: Tenant identifier

        Returns:
            {
                "compliant": bool,
                "evidence_checks": [
                    {
                        "type": "SAST",
                        "required": True,
                        "exists": True,
                        "description": "Static analysis covering CWE-787, CWE-89"
                    },
                    {
                        "type": "SBOM",
                        "required": True,
                        "exists": False,
                        "description": "Software bill of materials"
                    }
                ],
                "missing_required": ["SBOM"],
                "optional_present": ["DAST"]
            }

        Example:
            >>> requirement = {
            ...     "_key": "CRA_I_1_a",
            ...     "evidence_types": [
            ...         {
            ...             "type": "SAST",
            ...             "required": True,
            ...             "validation_spec": {
            ...                 "collection": "sast_findings",
            ...                 "filters": {"tenant_id": "@tenant"},
            ...                 "aggregation": "exists"
            ...             }
            ...         }
            ...     ]
            ... }
            >>> result = EvidenceValidator.check_evidence_exists(db, requirement, "acme")
            >>> print(result["compliant"])
            True
        """
        evidence_types = requirement.get("evidence_types", [])

        if not evidence_types:
            # No evidence required - compliant by default
            return {
                "compliant": True,
                "evidence_checks": [],
                "missing_required": [],
                "optional_present": []
            }

        evidence_checks = []
        missing_required = []
        optional_present = []

        for evidence_req in evidence_types:
            evidence_type = evidence_req.get("type", "unknown")
            is_required = evidence_req.get("required", False)
            description = evidence_req.get("description", "")

            # Check if this is a manual attestation (no automated check)
            if evidence_req.get("manual_attestation", False):
                evidence_checks.append({
                    "type": evidence_type,
                    "required": is_required,
                    "exists": None,  # Manual - can't auto-check
                    "description": description,
                    "manual_attestation": True
                })
                continue

            # Get validation spec
            validation_spec = evidence_req.get("validation_spec")

            if not validation_spec:
                logger.warning(
                    "Evidence type missing validation_spec",
                    requirement_key=requirement.get("_key"),
                    evidence_type=evidence_type
                )
                evidence_checks.append({
                    "type": evidence_type,
                    "required": is_required,
                    "exists": None,
                    "description": description,
                    "error": "No validation_spec defined"
                })
                continue

            # Add tenant filter if not already present
            if "filters" not in validation_spec:
                validation_spec["filters"] = {}

            # Ensure tenant_id is filtered
            if "tenant_id" not in validation_spec["filters"]:
                validation_spec["filters"]["tenant_id"] = "@tenant"

            # Build and execute query
            try:
                query, bind_vars = cls.build_query(validation_spec, {"tenant": tenant_id})

                result = list(db.aql.execute(query, bind_vars=bind_vars))

                # Interpret result based on aggregation type
                aggregation = validation_spec.get("aggregation", "exists")

                if aggregation == "exists":
                    exists = len(result) > 0 and result[0] is True
                elif aggregation == "count":
                    exists = len(result) > 0 and result[0] > 0
                elif aggregation == "coverage_percentage":
                    coverage = result[0] if result else 0.0
                    exists = coverage >= evidence_req.get("coverage_threshold", 0.8)
                else:
                    exists = len(result) > 0

                evidence_checks.append({
                    "type": evidence_type,
                    "required": is_required,
                    "exists": exists,
                    "description": description
                })

                if is_required and not exists:
                    missing_required.append(evidence_type)
                elif not is_required and exists:
                    optional_present.append(evidence_type)

            except Exception as e:
                logger.error(
                    "Evidence validation query failed",
                    requirement_key=requirement.get("_key"),
                    evidence_type=evidence_type,
                    error=str(e)
                )

                evidence_checks.append({
                    "type": evidence_type,
                    "required": is_required,
                    "exists": False,
                    "description": description,
                    "error": str(e)
                })

                if is_required:
                    missing_required.append(evidence_type)

        return {
            "compliant": len(missing_required) == 0,
            "evidence_checks": evidence_checks,
            "missing_required": missing_required,
            "optional_present": optional_present,
            "requirement_key": requirement.get("_key"),
            "requirement_id": requirement.get("requirement_id")
        }

    @classmethod
    def check_all_requirements(
        cls,
        db: StandardDatabase,
        tenant_id: str,
        framework_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Check evidence compliance for all requirements.

        Args:
            db: ArangoDB database instance
            tenant_id: Tenant identifier
            framework_key: Filter by framework (optional)

        Returns:
            {
                "compliant_requirements": int,
                "non_compliant_requirements": int,
                "total_requirements": int,
                "compliance_score": float,
                "results": [...]
            }
        """
        # Get all requirements for this framework
        query = """
        FOR req IN regulatory_requirements
            FILTER @framework == null OR req.framework == @framework
            FILTER LENGTH(req.evidence_types) > 0  // Only check requirements with evidence
            RETURN req
        """

        requirements = list(db.aql.execute(query, bind_vars={"framework": framework_key}))

        results = []
        compliant_count = 0
        non_compliant_count = 0

        for req in requirements:
            evidence_check = cls.check_evidence_exists(db, req, tenant_id)
            results.append(evidence_check)

            if evidence_check["compliant"]:
                compliant_count += 1
            else:
                non_compliant_count += 1

        total = len(requirements)
        compliance_score = compliant_count / total if total > 0 else 1.0

        return {
            "compliant_requirements": compliant_count,
            "non_compliant_requirements": non_compliant_count,
            "total_requirements": total,
            "compliance_score": compliance_score,
            "compliance_percentage": f"{compliance_score * 100:.1f}%",
            "framework": framework_key,
            "results": results
        }

    @staticmethod
    def get_evidence_gaps(
        db: StandardDatabase,
        tenant_id: str,
        framework_key: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get list of evidence gaps (missing required evidence).

        Args:
            db: ArangoDB database instance
            tenant_id: Tenant identifier
            framework_key: Filter by framework

        Returns:
            List of evidence gaps sorted by requirement priority

        Example:
            >>> gaps = EvidenceValidator.get_evidence_gaps(db, "acme", "CRA")
            >>> for gap in gaps:
            ...     print(f"{gap['requirement_id']}: Missing {gap['missing_evidence']}")
            CRA_I_1_a: Missing ['SBOM', 'SAST']
            CRA_I_2_b: Missing ['threat_model']
        """
        query = """
        FOR req IN regulatory_requirements
            FILTER @framework == null OR req.framework == @framework
            FILTER LENGTH(req.evidence_types) > 0
            SORT req.requirement_type == "essential" DESC, req.obligation_level == "shall" DESC
            RETURN req
        """

        requirements = list(db.aql.execute(query, bind_vars={"framework": framework_key}))

        gaps = []

        for req in requirements:
            result = EvidenceValidator.check_evidence_exists(db, req, tenant_id)

            if not result["compliant"] and result["missing_required"]:
                gaps.append({
                    "requirement_key": req["_key"],
                    "requirement_id": req["requirement_id"],
                    "framework": req["framework"],
                    "title": req.get("title", ""),
                    "requirement_type": req.get("requirement_type"),
                    "obligation_level": req.get("obligation_level"),
                    "missing_evidence": result["missing_required"],
                    "evidence_checks": result["evidence_checks"]
                })

        return gaps
