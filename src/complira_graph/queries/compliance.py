"""
Compliance query layer - centralized graph traversals (DRY principle).

Eliminates duplication of compliance queries across API, CLI, and report generators.
Implements both Path A (CWE mapping) and Path B (direct scanner findings).

Usage:
    from complira_graph.queries.compliance import ComplianceQueries
    from complira_graph.db import get_db

    db = get_db()
    report = ComplianceQueries.get_framework_compliance(db, "acme_corp")
"""

from typing import List, Dict, Optional, Any
from arango.database import StandardDatabase
import structlog

logger = structlog.get_logger()


class ComplianceQueries:
    """
    Centralized compliance traversal queries (DRY + Secure).

    All compliance-related queries go through this class:
    - Eliminates duplication across API/CLI/Reports
    - Single source of truth for compliance logic
    - Easy to optimize (change once, benefits everywhere)
    - Easy to test (one class to mock)
    """

    @staticmethod
    def get_violations_via_cwe_mapping(
        db: StandardDatabase,
        tenant_id: str,
        framework_key: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Path A: Find regulatory violations via CWE → requirement mapping.

        Traversal:
            component → affects → vulnerability → has_weakness → CWE →
            maps_to_requirement → regulatory_requirement

        Args:
            db: ArangoDB database instance
            tenant_id: Tenant identifier for multi-tenancy
            framework_key: Filter by specific framework (e.g., "CRA"), or None for all

        Returns:
            List of violation records with CWE context

        Example:
            >>> violations = ComplianceQueries.get_violations_via_cwe_mapping(
            ...     db, "acme_corp", "CRA"
            ... )
            >>> print(violations[0])
            {
                "requirement_key": "CRA_I_1_a",
                "framework": "CRA",
                "violation_source": "cwe_mapping",
                "cve_id": "CVE-2024-1234",
                "cwe_id": "CWE-787",
                "cvss_score": 9.8,
                "component_purl": "pkg:npm/lodash@4.17.20"
            }
        """
        query = """
        FOR comp IN components
            FILTER comp.tenant_id == @tenant

            // Traverse to vulnerabilities affecting this component
            FOR vuln IN 1..1 INBOUND comp affects
                // Traverse to CWE weaknesses
                FOR cwe IN 1..1 OUTBOUND vuln has_weakness
                    // Traverse to regulatory requirements mapped from CWE
                    FOR req IN 1..1 OUTBOUND cwe maps_to_requirement
                        // Filter by framework if specified
                        FILTER @framework == null OR req.framework == @framework

                        RETURN DISTINCT {
                            requirement_key: req._key,
                            requirement_id: req.requirement_id,
                            framework: req.framework,
                            violation_source: "cwe_mapping",
                            cve_id: vuln.cve_id,
                            cwe_id: cwe.cwe_id,
                            cwe_name: cwe.name,
                            cvss_v3_score: vuln.cvss_v3_score,
                            cvss_v2_score: vuln.cvss_v2_score,
                            component_key: comp._key,
                            component_purl: comp.purl,
                            component_name: comp.name
                        }
        """

        try:
            result = list(db.aql.execute(query, bind_vars={
                "tenant": tenant_id,
                "framework": framework_key
            }))

            logger.debug(
                "Path A violations retrieved",
                tenant=tenant_id,
                framework=framework_key,
                count=len(result)
            )

            return result

        except Exception as e:
            logger.error(
                "Path A query failed",
                tenant=tenant_id,
                framework=framework_key,
                error=str(e)
            )
            return []

    @staticmethod
    def get_violations_via_scanner_findings(
        db: StandardDatabase,
        tenant_id: str,
        framework_key: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Path B: Find regulatory violations via direct scanner findings.

        Traversal:
            component → source_artifact → scanned_by → scan_session →
            produced_findings → finding (SAST/DAST/etc.) →
            violates_requirement → regulatory_requirement

        Args:
            db: ArangoDB database instance
            tenant_id: Tenant identifier
            framework_key: Filter by specific framework, or None for all

        Returns:
            List of violation records with finding details

        Example:
            >>> violations = ComplianceQueries.get_violations_via_scanner_findings(
            ...     db, "acme_corp", "CRA"
            ... )
            >>> print(violations[0])
            {
                "requirement_key": "CRA_I_1_a",
                "framework": "CRA",
                "violation_source": "scanner_finding",
                "finding_id": "semgrep_20240301_finding_42",
                "finding_type": "sast_findings",
                "severity": "high",
                "cwe_id": "CWE-89",
                "file_path": "src/api/users.py",
                "line_number": 145
            }
        """
        query = """
        FOR comp IN components
            FILTER comp.tenant_id == @tenant

            // Traverse to source artifacts (code, binaries, containers)
            FOR artifact IN 1..1 OUTBOUND comp source_artifact
                // Traverse to scan sessions
                FOR session IN 1..1 OUTBOUND artifact scanned_by
                    // Traverse to findings produced by this scan
                    FOR finding IN 1..1 OUTBOUND session produced_findings
                        // Traverse to requirements violated by this finding
                        FOR req IN 1..1 OUTBOUND finding violates_requirement
                            // Filter by framework if specified
                            FILTER @framework == null OR req.framework == @framework

                            RETURN DISTINCT {
                                requirement_key: req._key,
                                requirement_id: req.requirement_id,
                                framework: req.framework,
                                violation_source: "scanner_finding",
                                finding_id: finding._key,
                                finding_type: PARSE_IDENTIFIER(finding).collection,
                                severity: finding.severity,
                                cwe_id: finding.cwe_id,
                                file_path: finding.file_path,
                                line_number: finding.line_number,
                                tool_name: session.tool_name,
                                scan_date: session.scan_date,
                                component_key: comp._key,
                                component_purl: comp.purl
                            }
        """

        try:
            result = list(db.aql.execute(query, bind_vars={
                "tenant": tenant_id,
                "framework": framework_key
            }))

            logger.debug(
                "Path B violations retrieved",
                tenant=tenant_id,
                framework=framework_key,
                count=len(result)
            )

            return result

        except Exception as e:
            logger.error(
                "Path B query failed",
                tenant=tenant_id,
                framework=framework_key,
                error=str(e)
            )
            return []

    @classmethod
    def get_all_violations(
        cls,
        db: StandardDatabase,
        tenant_id: str,
        framework_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Combined: Get violations from both Path A and Path B.

        Returns deduplicated violations with breakdown by source.

        Args:
            db: ArangoDB database instance
            tenant_id: Tenant identifier
            framework_key: Filter by framework, or None for all

        Returns:
            Dict with violation breakdown:
            {
                "cwe_violations": [...],
                "direct_violations": [...],
                "all_violations": [...],  # Deduplicated by requirement_key
                "violated_requirements": [...],  # Unique requirement keys
                "summary": {
                    "cwe_count": int,
                    "direct_count": int,
                    "total_violations": int,
                    "unique_requirements": int
                }
            }
        """
        # Path A: CWE-based violations
        cwe_violations = cls.get_violations_via_cwe_mapping(db, tenant_id, framework_key)

        # Path B: Direct scanner finding violations
        direct_violations = cls.get_violations_via_scanner_findings(db, tenant_id, framework_key)

        # Combine and deduplicate
        all_violations = cwe_violations + direct_violations

        # Get unique requirement keys
        violated_req_keys = list(set(v["requirement_key"] for v in all_violations))

        return {
            "cwe_violations": cwe_violations,
            "direct_violations": direct_violations,
            "all_violations": all_violations,
            "violated_requirements": violated_req_keys,
            "summary": {
                "cwe_count": len(cwe_violations),
                "direct_count": len(direct_violations),
                "total_violations": len(all_violations),
                "unique_requirements": len(violated_req_keys)
            }
        }

    @classmethod
    def get_framework_compliance(
        cls,
        db: StandardDatabase,
        tenant_id: str,
        include_violations: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Calculate compliance score for all in-force regulatory frameworks.

        Returns framework-by-framework compliance summary.

        Args:
            db: ArangoDB database instance
            tenant_id: Tenant identifier
            include_violations: Whether to include detailed violation list (default: True)

        Returns:
            List of framework compliance summaries

        Example:
            >>> compliance = ComplianceQueries.get_framework_compliance(db, "acme_corp")
            >>> for fw in compliance:
            ...     print(f"{fw['framework_name']}: {fw['compliance_score']:.1%}")
            EU Cyber Resilience Act: 87.5%
            FDA Section 524B: 92.3%
        """
        # Get all in-force frameworks
        frameworks_query = """
        FOR fw IN regulatory_frameworks
            FILTER fw.status == "in_force"
            SORT fw.enforcement_date ASC
            RETURN {
                key: fw._key,
                name: fw.name,
                short_name: fw.short_name,
                enforcement_date: fw.enforcement_date,
                jurisdiction: fw.jurisdiction
            }
        """

        frameworks = list(db.aql.execute(frameworks_query))

        results = []

        for fw in frameworks:
            # Get total requirements for this framework
            requirements_query = """
            FOR req IN regulatory_requirements
                FILTER req.framework == @framework
                RETURN req._key
            """

            requirements = list(db.aql.execute(
                requirements_query,
                bind_vars={"framework": fw["key"]}
            ))

            # Get violations for this framework
            violations = cls.get_all_violations(db, tenant_id, fw["key"])

            total_reqs = len(requirements)
            violated_reqs = len(violations["violated_requirements"])

            # Calculate compliance score
            compliance_score = 1.0 - (violated_reqs / total_reqs) if total_reqs > 0 else 1.0

            framework_result = {
                "framework": fw["key"],
                "framework_name": fw["name"],
                "framework_short_name": fw["short_name"],
                "enforcement_date": fw["enforcement_date"],
                "jurisdiction": fw["jurisdiction"],
                "total_requirements": total_reqs,
                "violated_requirements": violated_reqs,
                "compliant_requirements": total_reqs - violated_reqs,
                "compliance_score": compliance_score,
                "compliance_percentage": f"{compliance_score * 100:.1f}%",
                "status": cls._get_compliance_status(compliance_score),
                "violation_summary": violations["summary"]
            }

            # Optionally include detailed violations
            if include_violations:
                framework_result["violations"] = violations

            results.append(framework_result)

        logger.info(
            "Framework compliance calculated",
            tenant=tenant_id,
            frameworks_count=len(results)
        )

        return results

    @staticmethod
    def _get_compliance_status(score: float) -> str:
        """
        Get human-readable compliance status.

        Args:
            score: Compliance score (0.0 to 1.0)

        Returns:
            Status string (compliant | mostly_compliant | partial | non_compliant)
        """
        if score >= 0.95:
            return "compliant"
        elif score >= 0.80:
            return "mostly_compliant"
        elif score >= 0.50:
            return "partial"
        else:
            return "non_compliant"

    @staticmethod
    def get_requirement_blast_radius(
        db: StandardDatabase,
        tenant_id: str,
        requirement_key: str
    ) -> Dict[str, Any]:
        """
        Get blast radius for a specific requirement.

        Shows all components, vulnerabilities, and findings that violate this requirement.

        Args:
            db: ArangoDB database instance
            tenant_id: Tenant identifier
            requirement_key: Requirement key (e.g., "CRA_I_1_a")

        Returns:
            Blast radius breakdown

        Example:
            >>> blast = ComplianceQueries.get_requirement_blast_radius(
            ...     db, "acme_corp", "CRA_I_1_a"
            ... )
            >>> print(f"Affects {blast['affected_components_count']} components")
        """
        query = """
        LET req = DOCUMENT(CONCAT("regulatory_requirements/", @req_key))

        // Path A: Via CWE mapping
        LET cwe_components = (
            FOR comp IN components
                FILTER comp.tenant_id == @tenant
                FOR vuln IN 1..1 INBOUND comp affects
                    FOR cwe IN 1..1 OUTBOUND vuln has_weakness
                        FOR r IN 1..1 OUTBOUND cwe maps_to_requirement
                            FILTER r._key == @req_key
                            RETURN DISTINCT {
                                component: comp,
                                vulnerability: vuln,
                                cwe: cwe,
                                source: "cwe_mapping"
                            }
        )

        // Path B: Via direct findings
        LET finding_components = (
            FOR comp IN components
                FILTER comp.tenant_id == @tenant
                FOR artifact IN 1..1 OUTBOUND comp source_artifact
                    FOR session IN 1..1 OUTBOUND artifact scanned_by
                        FOR finding IN 1..1 OUTBOUND session produced_findings
                            FOR r IN 1..1 OUTBOUND finding violates_requirement
                                FILTER r._key == @req_key
                                RETURN DISTINCT {
                                    component: comp,
                                    finding: finding,
                                    scan_session: session,
                                    source: "scanner_finding"
                                }
        )

        RETURN {
            requirement: req,
            cwe_violations: cwe_components,
            direct_violations: finding_components,
            affected_components_count: LENGTH(UNIQUE(
                APPEND(
                    cwe_components[* RETURN CURRENT.component._key],
                    finding_components[* RETURN CURRENT.component._key]
                )
            )),
            total_violations: LENGTH(cwe_components) + LENGTH(finding_components)
        }
        """

        result = db.aql.execute(query, bind_vars={
            "tenant": tenant_id,
            "req_key": requirement_key
        })

        blast_radius = next(result, None)

        if not blast_radius:
            return {
                "requirement_key": requirement_key,
                "found": False,
                "error": "Requirement not found"
            }

        return {
            "requirement_key": requirement_key,
            "requirement_id": blast_radius["requirement"]["requirement_id"],
            "framework": blast_radius["requirement"]["framework"],
            "found": True,
            "affected_components_count": blast_radius["affected_components_count"],
            "total_violations": blast_radius["total_violations"],
            "cwe_violations_count": len(blast_radius["cwe_violations"]),
            "direct_violations_count": len(blast_radius["direct_violations"]),
            "cwe_violations": blast_radius["cwe_violations"],
            "direct_violations": blast_radius["direct_violations"]
        }
