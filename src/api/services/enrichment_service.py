"""
Enrichment Service for graph-based vulnerability intelligence.

Combines authoritative data from ArangoDB knowledge graph:
- EPSS scores (exploitation probability)
- KEV catalog (active exploitation)
- CVSS scores (severity)
- ATT&CK techniques (attack tactics)
- D3FEND defenses (countermeasures)
- Compliance mappings (NIST, FDA, ISO)
"""

import time
from typing import Dict, List, Optional, Any
import structlog
from datetime import datetime

from api.core.config import get_cloud_settings
from api.models.responses.enrichment import (
    CVEEnrichment,
    RiskFactors,
    AttackPath,
    AttackPathStage,
    Defense,
    ComplianceMapping,
)
from complira_graph.db import get_db

logger = structlog.get_logger()


class EnrichmentService:
    """
    Orchestrates vulnerability enrichment using graph-based intelligence.

    Features:
    - Smart risk scoring (CVSS + EPSS + KEV + exploits)
    - Attack path traversal (CVE → Threat Groups)
    - Compliance mapping (graph relationships)
    - All data is authoritative - no LLM guessing
    """

    def __init__(self):
        """Initialize enrichment service with graph database."""
        self.settings = get_cloud_settings()
        self.db = get_db()
        logger.info("EnrichmentService initialized with graph-based intelligence")

    async def enrich_cves(
        self,
        cve_ids: List[str],
        include_attack_paths: bool = False,
        include_compliance: bool = False
    ) -> Dict[str, Any]:
        """
        Enrich CVEs with graph-based intelligence.

        Args:
            cve_ids: List of CVE IDs to enrich (max 100)
            include_attack_paths: Include attack path traversal
            include_compliance: Include compliance framework mappings

        Returns:
            Dictionary with:
                - enriched: List of CVEEnrichment objects
                - total: Total CVEs enriched
                - processing_time_ms: Processing time
        """
        start_time = time.time()
        enriched_cves = []

        logger.info(
            "Starting CVE enrichment (graph-based)",
            cve_count=len(cve_ids),
            include_attack_paths=include_attack_paths,
            include_compliance=include_compliance
        )

        for cve_id in cve_ids:
            try:
                # Step 1: Get comprehensive CVE data from graph
                cve_data = await self._get_cve_data(cve_id)

                if not cve_data:
                    logger.warning("CVE not found in graph", cve_id=cve_id)
                    continue

                # Step 2: Calculate risk score from authoritative data
                risk_score = self._calculate_risk_score(cve_data)
                priority = self._calculate_priority(risk_score, cve_data)
                risk_factors = self._calculate_risk_factors(cve_data)

                # Step 3: Get attack path if requested
                attack_path = None
                if include_attack_paths:
                    attack_path = await self._get_attack_path(cve_id)

                # Step 4: Get compliance mappings if requested
                compliance = None
                if include_compliance:
                    compliance = await self._get_compliance_mappings(cve_id)

                # Step 5: Build enrichment response
                enrichment = CVEEnrichment(
                    cve_id=cve_id,
                    description=cve_data.get("description"),
                    cvss_score=cve_data.get("cvss_score"),
                    cvss_vector=cve_data.get("cvss_vector"),
                    cvss_severity=cve_data.get("severity"),
                    epss_score=cve_data.get("epss_score"),
                    in_kev=cve_data.get("in_kev", False),
                    exploit_count=cve_data.get("exploit_count", 0),
                    published_date=cve_data.get("published_date"),
                    last_modified=cve_data.get("last_modified"),
                    risk_score=risk_score,
                    priority=priority,
                    risk_factors=risk_factors,
                    cwe_list=cve_data.get("cwe_list", []),
                    attack_techniques=cve_data.get("attack_techniques", []),
                    threat_groups=cve_data.get("threat_groups", []),
                    attack_path=attack_path,
                    compliance=compliance,
                    enriched_at=datetime.utcnow().isoformat()
                )

                enriched_cves.append(enrichment)

            except Exception as e:
                logger.error("Failed to enrich CVE", cve_id=cve_id, error=str(e))

        processing_time_ms = (time.time() - start_time) * 1000

        logger.info(
            "CVE enrichment completed",
            enriched_count=len(enriched_cves),
            processing_time_ms=processing_time_ms
        )

        return {
            "enriched": enriched_cves,
            "total": len(enriched_cves),
            "processing_time_ms": processing_time_ms
        }

    async def _get_cve_data(self, cve_id: str) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive CVE data from graph database.

        Queries ArangoDB for CVE with full context from graph relationships.

        Args:
            cve_id: CVE identifier

        Returns:
            Dictionary with CVE data or None if not found
        """
        try:
            query = """
            LET cve = FIRST(
                FOR v IN vulnerabilities
                FILTER v._key == @cve_id
                RETURN v
            )

            // Return null if CVE doesn't exist
            FILTER cve != null

            // Get EPSS score (follow edge to epss_history)
            LET epss = FIRST(
                FOR v, e IN 1..1 OUTBOUND cve has_epss
                SORT v.score_date DESC
                LIMIT 1
                RETURN v.epss_score
            )

            // Check KEV catalog (use cve_id field with dashes)
            LET cve_id_with_dashes = CONCAT(
                SUBSTRING(@cve_id, 0, 3), '-',
                SUBSTRING(@cve_id, 4, 4), '-',
                SUBSTRING(@cve_id, 9)
            )
            LET in_kev = LENGTH(
                FOR k IN kev_entries
                FILTER k.cve_id == cve_id_with_dashes
                LIMIT 1
                RETURN k
            ) > 0

            // Get related CWEs (via has_weakness edge) - filter out nulls
            LET cwes = (
                FOR v, e IN 1..1 OUTBOUND cve has_weakness
                FILTER v.cwe_id != null
                RETURN v.cwe_id
            )

            // Get ATT&CK techniques
            LET techniques = (
                FOR t IN attack_techniques
                RETURN t._key
            )

            // Get threat groups
            LET groups = (
                FOR g IN threat_groups
                RETURN g.name
            )

            // Count exploits (check multiple collections)
            LET exploit_count = (
                LENGTH(FOR e IN exploit_modules FILTER e.cve_id == cve_id_with_dashes RETURN 1) +
                LENGTH(FOR e IN exploited_in_wild FILTER e.cve_id == cve_id_with_dashes RETURN 1)
            )

            RETURN {
                cve_id: cve._key,
                description: cve.description,
                cvss_score: cve.cvss_v3_score,
                cvss_vector: cve.cvss_v3_vector,
                severity: cve.cvss_v3_severity,
                cwe_list: cwes,
                epss_score: epss,
                in_kev: in_kev,
                exploit_count: exploit_count,
                attack_techniques: techniques,
                threat_groups: groups,
                published_date: cve.published,
                last_modified: cve.last_modified
            }
            """

            bind_vars = {"cve_id": cve_id}
            cursor = self.db.aql.execute(query, bind_vars=bind_vars)
            result = list(cursor)

            if not result or not result[0]:
                return None

            return result[0]

        except Exception as e:
            logger.error("Failed to get CVE data", cve_id=cve_id, error=str(e))
            return None

    def _calculate_risk_score(self, cve_data: Dict[str, Any]) -> float:
        """
        Calculate risk score from authoritative data (no LLM).

        Formula:
        - CVSS: 30% weight (severity)
        - EPSS: 40% weight (exploitation probability)
        - KEV: 20% weight (active exploitation)
        - Exploits: 10% weight (public exploits)

        Args:
            cve_data: CVE data from graph

        Returns:
            Risk score (0.0-1.0)
        """
        cvss = cve_data.get("cvss_score", 0.0) or 0.0
        epss = cve_data.get("epss_score", 0.0) or 0.0
        in_kev = cve_data.get("in_kev", False)
        exploit_count = cve_data.get("exploit_count", 0)

        # Normalize CVSS to 0-1
        cvss_normalized = cvss / 10.0

        # KEV is binary (0 or 1)
        kev_score = 1.0 if in_kev else 0.0

        # Exploits normalized (cap at 5)
        exploit_score = min(exploit_count / 5.0, 1.0)

        # Weighted average
        risk_score = (
            cvss_normalized * 0.3 +
            epss * 0.4 +
            kev_score * 0.2 +
            exploit_score * 0.1
        )

        return round(risk_score, 3)

    def _calculate_priority(self, risk_score: float, cve_data: Dict[str, Any]) -> str:
        """
        Calculate priority level from risk score.

        Args:
            risk_score: Calculated risk score
            cve_data: CVE data from graph

        Returns:
            Priority level: CRITICAL, HIGH, MEDIUM, LOW
        """
        in_kev = cve_data.get("in_kev", False)
        cvss = cve_data.get("cvss_score", 0.0) or 0.0

        # CRITICAL: In KEV or very high risk score
        if in_kev or risk_score >= 0.9:
            return "CRITICAL"

        # HIGH: High CVSS or high risk
        elif cvss >= 9.0 or risk_score >= 0.7:
            return "HIGH"

        # MEDIUM: Moderate risk
        elif risk_score >= 0.4:
            return "MEDIUM"

        # LOW: Lower risk
        else:
            return "LOW"

    def _calculate_risk_factors(self, cve_data: Dict[str, Any]) -> RiskFactors:
        """
        Calculate boolean risk factors from authoritative data.

        Args:
            cve_data: CVE data from graph

        Returns:
            RiskFactors object
        """
        epss = cve_data.get("epss_score", 0.0) or 0.0
        cvss = cve_data.get("cvss_score", 0.0) or 0.0
        in_kev = cve_data.get("in_kev", False)
        exploit_count = cve_data.get("exploit_count", 0)
        threat_groups = cve_data.get("threat_groups", [])

        return RiskFactors(
            high_epss=(epss >= 0.7),
            actively_exploited=in_kev,
            high_cvss=(cvss >= 9.0),
            public_exploits=(exploit_count > 0),
            threat_groups_using=(len(threat_groups) > 0)
        )

    async def _get_attack_path(self, cve_id: str) -> Optional[AttackPath]:
        """
        Get attack path from CVE through weakness to ATT&CK techniques.

        Simplified path: CVE → CWE → ATT&CK Techniques

        Args:
            cve_id: CVE identifier

        Returns:
            AttackPath object with D3FEND defenses
        """
        try:
            # Simplified query: CVE → CWE → ATT&CK (via CAPEC if available)
            query = """
            LET cve_doc = DOCUMENT(CONCAT('vulnerabilities/', @cve_id))

            // Get CWEs
            LET cwes = (
                FOR v, e IN 1..1 OUTBOUND cve_doc has_weakness
                FILTER v.cwe_id != null
                RETURN {
                    type: 'weakness',
                    id: v.cwe_id,
                    name: v.name,
                    description: v.description
                }
            )

            // Return simplified path
            RETURN {
                cve: {
                    type: 'vulnerability',
                    id: @cve_id,
                    name: cve_doc.cve_id
                },
                cwes: cwes
            }
            """

            bind_vars = {"cve_id": cve_id}
            cursor = self.db.aql.execute(query, bind_vars=bind_vars)
            result = list(cursor)

            if not result or not result[0]:
                logger.debug("No attack path found", cve_id=cve_id)
                return None

            path_data = result[0]

            # Build simplified path stages
            path_stages = []

            # Add CVE stage
            if path_data.get("cve"):
                stage = AttackPathStage(
                    stage="vulnerability",
                    node=path_data["cve"]["id"],
                    name=path_data["cve"].get("name")
                )
                path_stages.append(stage)

            # Add CWE stages
            for cwe in path_data.get("cwes", []):
                stage = AttackPathStage(
                    stage="weakness",
                    node=cwe.get("id"),
                    name=cwe.get("name"),
                    description=cwe.get("description")
                )
                path_stages.append(stage)

            # Get D3FEND defenses (query ATT&CK techniques separately)
            defenses = []
            # Note: D3FEND defenses require ATT&CK techniques
            # For now, return empty defenses unless we have a full path

            if not path_stages:
                return None

            return AttackPath(path=path_stages, defenses=defenses)

        except Exception as e:
            logger.error("Failed to get attack path", cve_id=cve_id, error=str(e))
            return None

    async def _get_d3fend_defenses_for_path(self, path_vertices: List[Dict]) -> List[Defense]:
        """
        Get D3FEND defensive techniques that counter the ATT&CK techniques in the attack path.

        Args:
            path_vertices: List of vertices from attack path traversal

        Returns:
            List of Defense objects
        """
        try:
            # Extract ATT&CK technique IDs from path
            attack_technique_ids = []
            for vertex in path_vertices:
                if vertex.get("type") == "technique":
                    technique_id = vertex.get("id")
                    if technique_id:
                        attack_technique_ids.append(f"attack_techniques/{technique_id}")

            if not attack_technique_ids:
                logger.debug("No ATT&CK techniques found in path")
                return []

            # Query D3FEND techniques that counter these ATT&CK techniques
            query = """
            LET attack_techniques = @attack_technique_ids

            FOR attack_tech_id IN attack_techniques
                FOR d3fend_tech IN 1..1 INBOUND
                    DOCUMENT(attack_tech_id)
                    d3fend_counters_technique
                RETURN DISTINCT {
                    d3fend_id: d3fend_tech.d3fend_id,
                    name: d3fend_tech.name,
                    description: d3fend_tech.description,
                    counters_technique: PARSE_IDENTIFIER(attack_tech_id).key
                }
            """

            bind_vars = {"attack_technique_ids": attack_technique_ids}
            cursor = self.db.aql.execute(query, bind_vars=bind_vars)
            results = list(cursor)

            # Convert to Defense objects
            defenses = []
            for result in results:
                defense = Defense(
                    d3fend_id=result["d3fend_id"],
                    name=result["name"],
                    description=result.get("description"),
                    coverage=[result["counters_technique"]]
                )
                defenses.append(defense)

            logger.debug(
                "Found D3FEND defenses",
                attack_techniques=len(attack_technique_ids),
                defenses_found=len(defenses)
            )

            return defenses

        except Exception as e:
            logger.error("Failed to get D3FEND defenses", error=str(e))
            return []

    async def _get_compliance_mappings(self, cve_id: str) -> Optional[ComplianceMapping]:
        """
        Get compliance framework mappings via graph traversal.

        Traverses: CVE → OSCAL Controls (NIST 800-53)

        Args:
            cve_id: CVE identifier

        Returns:
            ComplianceMapping object or None
        """
        try:
            query = """
            // Get controls that this CVE maps to
            FOR control, edge IN 1..1 OUTBOUND
                DOCUMENT(CONCAT('vulnerabilities/', @cve_id))
                maps_to_requirement

            // Get control details
            RETURN {
                control_id: control.control_id,
                title: control.title,
                framework: edge.framework,
                confidence: edge.confidence,
                rationale: edge.rationale
            }
            """

            bind_vars = {"cve_id": cve_id}
            cursor = self.db.aql.execute(query, bind_vars=bind_vars)
            results = list(cursor)

            if not results:
                logger.debug("No compliance mappings found", cve_id=cve_id)
                return ComplianceMapping(nist_controls=[], frameworks=[])

            # Extract NIST controls
            nist_controls = []
            frameworks = set()

            for result in results:
                control_id = result.get("control_id")
                if control_id:
                    nist_controls.append(control_id)

                framework = result.get("framework")
                if framework:
                    frameworks.add(framework)

            logger.debug(
                "Found compliance mappings",
                cve_id=cve_id,
                nist_controls=len(nist_controls),
                frameworks=list(frameworks)
            )

            return ComplianceMapping(
                nist_controls=nist_controls,
                frameworks=list(frameworks)
            )

        except Exception as e:
            logger.error("Failed to get compliance mappings", cve_id=cve_id, error=str(e))
            return None

    async def calculate_blast_radius(
        self,
        cve_id: str,
        customer_context: bool = False
    ) -> Dict[str, Any]:
        """
        Calculate blast radius for a vulnerability.

        Args:
            cve_id: CVE identifier
            customer_context: Include customer-specific scan data

        Returns:
            Blast radius analysis with:
                - Affected components count
                - Attack surface analysis
                - Threat landscape
                - Compliance impact
        """
        # TODO: Implement in Phase 1B
        raise NotImplementedError("Blast radius analysis coming in Phase 1B")

    async def map_to_controls(
        self,
        scan_session_id: Optional[str] = None,
        cve_ids: Optional[List[str]] = None,
        frameworks: List[str] = None
    ) -> Dict[str, Any]:
        """
        Map findings to compliance controls.

        Args:
            scan_session_id: Scan session to analyze (customer-specific)
            cve_ids: Alternative list of CVE IDs
            frameworks: Target compliance frameworks

        Returns:
            Control mappings with gap analysis
        """
        # TODO: Implement in Phase 1C
        raise NotImplementedError("Compliance mapping coming in Phase 1C")
