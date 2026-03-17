"""
VEX Evidence Collection Queries (Production-Ready AQL).

This module provides a complete library of AQL queries for extracting evidence
from the knowledge graph to support regulatory-grade VEX (Vulnerability
Exploitability eXchange) generation.

Design Principles:
- Evidence First: Collect all evidence before LLM involvement
- Graph Provenance: Return _id, _key, _from, _to for auditability
- Parameterized Queries: Use bind_vars for SQL injection prevention
- Performance Optimized: Proper indexes, minimal traversals
- Regulatory Compliance: FDA 524B, EU CRA, IEC 62304

Query Organization:
- Tier 1 Queries: Critical evidence (CVE, CWE, KEV, EPSS, Component)
- Tier 2 Queries: Important evidence (ATT&CK, Controls, Remediation)
- Optimized Queries: Multi-hop traversals, parallel collection

Usage:
    from complira_graph.queries.vex_evidence_queries import (
        get_cve_metadata,
        get_full_evidence_chain,
        get_all_tier1_evidence
    )

    # Single query
    cve_data = get_cve_metadata(db, 'CVE-2021-44228')

    # Full evidence chain
    chain = get_full_evidence_chain(db, 'CVE-2021-44228')

    # Parallel Tier 1 collection
    tier1 = get_all_tier1_evidence(
        db,
        'CVE-2021-44228',
        'pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1',
        'customer_123'
    )

Performance Notes:
- All queries use indexed lookups where possible
- Graph traversals are depth-limited (1..1, 1..2, 1..3)
- DISTINCT used to prevent duplicate results
- LIMIT clauses for safety
- Bind variables prevent query injection

Author: Complira Graph Team
Version: 1.0
Date: 2026-03-06
"""

from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime
from arango.database import StandardDatabase
import structlog

logger = structlog.get_logger()


# ============================================================================
# QUERY PERFORMANCE CONSTANTS
# ============================================================================

# Expected query performance (in milliseconds)
PERFORMANCE_TARGETS = {
    "tier1_simple": 50,      # Simple document lookups (CVE metadata, KEV check)
    "tier1_edge": 100,       # Single-hop edge traversals (CWE mappings)
    "tier2_multihop": 500,   # Multi-hop traversals (CVE→CWE→CAPEC→ATT&CK)
    "full_chain": 1000,      # Complete evidence chain (all tiers)
}

# Index requirements (for reference)
REQUIRED_INDEXES = {
    "vulnerabilities": ["cve_id", "_key"],
    "weaknesses": ["cwe_id", "_key"],
    "kev_catalog": ["cve_id"],
    "epss_scores": ["cve_id", "date"],
    "attack_techniques": ["technique_id"],
    "oscal_controls": ["control_id"],
}


# ============================================================================
# TIER 1 EVIDENCE QUERIES (CRITICAL)
# ============================================================================

def get_cve_metadata(db: StandardDatabase, cve_key: str) -> Optional[Dict[str, Any]]:
    """
    Get CVE metadata from vulnerabilities collection.

    This is Tier 1 critical evidence required for all VEX assessments.
    Provides CVSS scoring and severity classification per FDA 524B requirements.

    Args:
        db: ArangoDB database instance
        cve_key: CVE key (e.g., 'CVE-2021-44228')

    Returns:
        CVE document with metadata or None if not found

    Example:
        >>> result = get_cve_metadata(db, 'CVE-2021-44228')
        >>> result['cvss_v3_score']
        10.0
        >>> result['cvss_v3_severity']
        'CRITICAL'

    Performance: ~20-50ms (indexed lookup on cve_id)

    Graph Query:
        Direct lookup in vulnerabilities collection
    """
    query = """
    FOR vuln IN vulnerabilities
        FILTER vuln.cve_id == @cve_id
        LIMIT 1
        RETURN {
            _id: vuln._id,
            _key: vuln._key,
            cve_id: vuln.cve_id,
            description: vuln.description,
            cvss_v3_score: vuln.cvss_v3_score,
            cvss_v3_vector: vuln.cvss_v3_vector,
            cvss_v3_severity: vuln.cvss_v3_severity,
            cvss_v2_score: vuln.cvss_v2_score,
            published_date: vuln.published_date,
            last_modified_date: vuln.last_modified_date,
            references: vuln.references
        }
    """

    try:
        cursor = db.aql.execute(query, bind_vars={'cve_id': cve_key.upper()})
        results = list(cursor)

        if results:
            logger.debug("CVE metadata retrieved", cve_id=cve_key)
            return results[0]
        else:
            logger.warning("CVE not found in database", cve_id=cve_key)
            return None

    except Exception as e:
        logger.error("Error retrieving CVE metadata", cve_id=cve_key, error=str(e))
        raise


def get_cwe_mappings(db: StandardDatabase, cve_key: str) -> List[Dict[str, Any]]:
    """
    Get CWE weakness mappings for a CVE via has_weakness edges.

    This is Tier 1 critical evidence. CWE classification is required by
    EU CRA for risk assessment and weakness categorization.

    Graph Path:
        vulnerabilities → has_weakness → weaknesses

    Args:
        db: ArangoDB database instance
        cve_key: CVE key (e.g., 'CVE-2021-44228')

    Returns:
        List of CWE documents with edge provenance

    Example:
        >>> results = get_cwe_mappings(db, 'CVE-2021-44228')
        >>> results[0]['cwe_id']
        'CWE-502'
        >>> results[0]['name']
        'Deserialization of Untrusted Data'

    Performance: ~50-100ms (single-hop edge traversal)

    Validation:
        At least 1 CWE mapping is required for Tier 1 completeness
    """
    query = """
    FOR vuln IN vulnerabilities
        FILTER vuln.cve_id == @cve_id
        FOR cwe, edge IN 1..1 OUTBOUND vuln has_weakness
            RETURN {
                _id: cwe._id,
                _key: cwe._key,
                edge_id: edge._id,
                cwe_id: cwe.cwe_id,
                name: cwe.name,
                description: cwe.description,
                weakness_type: cwe.weakness_type,
                likelihood_of_exploit: cwe.likelihood_of_exploit,
                abstraction_level: cwe.abstraction_level
            }
    """

    try:
        cursor = db.aql.execute(query, bind_vars={'cve_id': cve_key.upper()})
        results = list(cursor)

        logger.debug("CWE mappings retrieved", cve_id=cve_key, count=len(results))
        return results

    except Exception as e:
        logger.error("Error retrieving CWE mappings", cve_id=cve_key, error=str(e))
        raise


def get_kev_status(db: StandardDatabase, cve_key: str) -> Dict[str, Any]:
    """
    Check if CVE is in CISA Known Exploited Vulnerabilities (KEV) catalog.

    This is Tier 1 critical evidence. FDA 524B prioritizes KEV vulnerabilities
    for immediate remediation with mandatory deadlines.

    Graph Path:
        vulnerabilities → in_kev_catalog → kev_catalog (if exists)

    Args:
        db: ArangoDB database instance
        cve_key: CVE key (e.g., 'CVE-2021-44228')

    Returns:
        KEV status with optional KEV metadata

    Example:
        >>> result = get_kev_status(db, 'CVE-2021-44228')
        >>> result['in_kev']
        True
        >>> result['kev_due_date']
        '2022-01-04T00:00:00Z'

    Performance: ~30-50ms (indexed lookup + optional edge traversal)

    Validation:
        Always returns a result (in_kev: true/false)
    """
    query = """
    FOR vuln IN vulnerabilities
        FILTER vuln.cve_id == @cve_id
        LIMIT 1
        LET kev = FIRST(
            FOR k IN 1..1 OUTBOUND vuln in_kev_catalog
                RETURN k
        )
        RETURN {
            in_kev: kev != null,
            kev_id: kev ? kev._id : null,
            kev_date_added: kev ? kev.date_added : null,
            kev_due_date: kev ? kev.due_date : null,
            kev_required_action: kev ? kev.required_action : null,
            kev_known_ransomware: kev ? kev.known_ransomware_campaign_use : null,
            kev_notes: kev ? kev.notes : null
        }
    """

    try:
        cursor = db.aql.execute(query, bind_vars={'cve_id': cve_key.upper()})
        results = list(cursor)

        if results:
            result = results[0]
            logger.debug("KEV status retrieved", cve_id=cve_key, in_kev=result['in_kev'])
            return result
        else:
            # CVE not found, return default
            logger.warning("CVE not found for KEV check", cve_id=cve_key)
            return {'in_kev': False, 'kev_id': None}

    except Exception as e:
        logger.error("Error retrieving KEV status", cve_id=cve_key, error=str(e))
        raise


def get_exploitability_data(db: StandardDatabase, cve_key: str) -> Dict[str, Any]:
    """
    Get exploitability evidence including EPSS scores and exploit intelligence.

    This is Tier 1 critical evidence. FDA/CRA require exploit probability
    assessment for risk prioritization.

    Graph Path:
        vulnerabilities → has_epss_score → epss_scores (latest)
        vulnerabilities.exploit_metadata (direct fields)

    Args:
        db: ArangoDB database instance
        cve_key: CVE key (e.g., 'CVE-2021-44228')

    Returns:
        Exploitability data with EPSS scores and exploit metadata

    Example:
        >>> result = get_exploitability_data(db, 'CVE-2021-44228')
        >>> result['epss_score']
        0.97542
        >>> result['epss_percentile']
        0.99876
        >>> result['exploit_available']
        True

    Performance: ~50-100ms (edge traversal + sort for latest EPSS)

    Validation:
        EPSS score is preferred but not required (some CVEs lack EPSS)
    """
    query = """
    FOR vuln IN vulnerabilities
        FILTER vuln.cve_id == @cve_id
        LIMIT 1

        // Get latest EPSS score (sorted by date DESC)
        LET epss = FIRST(
            FOR e IN 1..1 OUTBOUND vuln has_epss_score
                SORT e.date DESC
                LIMIT 1
                RETURN e
        )

        RETURN {
            // EPSS data
            epss_score: epss ? epss.epss : null,
            epss_percentile: epss ? epss.percentile : null,
            epss_date: epss ? epss.date : null,
            epss_id: epss ? epss._id : null,

            // Exploit metadata from CVE document
            exploit_available: vuln.exploit_available,
            exploit_maturity: vuln.exploit_maturity,
            exploit_details: vuln.exploit_details,

            // Metadata
            cve_id: vuln._id
        }
    """

    try:
        cursor = db.aql.execute(query, bind_vars={'cve_id': cve_key.upper()})
        results = list(cursor)

        if results:
            result = results[0]
            logger.debug(
                "Exploitability data retrieved",
                cve_id=cve_key,
                has_epss=result['epss_score'] is not None
            )
            return result
        else:
            logger.warning("CVE not found for exploitability check", cve_id=cve_key)
            return {'epss_score': None, 'exploit_available': None}

    except Exception as e:
        logger.error("Error retrieving exploitability data", cve_id=cve_key, error=str(e))
        raise


def verify_component_presence(
    customer_db: StandardDatabase,
    component_purl: str,
    tenant_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Verify if vulnerable component is present in customer's SBOM.

    This is Tier 1 critical evidence. VEX must confirm that the vulnerable
    component is actually deployed in the customer's environment.

    Query Target:
        Customer database → components collection

    Args:
        customer_db: Customer ArangoDB database instance
        component_purl: Component Package URL (PURL)
        tenant_id: Optional tenant ID for multi-tenant environments

    Returns:
        Component presence validation with deployment context

    Example:
        >>> result = verify_component_presence(
        ...     customer_db,
        ...     'pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1'
        ... )
        >>> result['in_sbom']
        True
        >>> result['deployment_scope']
        'production'

    Performance: ~20-50ms (indexed lookup on purl)

    Validation:
        Returns in_sbom: true/false regardless of presence
    """
    query = """
    FOR component IN components
        FILTER component.purl == @purl
        FILTER @tenant_id == null OR component.tenant_id == @tenant_id
        LIMIT 1
        RETURN {
            _id: component._id,
            _key: component._key,
            in_sbom: true,
            purl: component.purl,
            name: component.name,
            version: component.version,
            type: component.type,

            // Deployment context
            deployment_scope: component.deployment_scope,
            deployment_criticality: component.deployment_criticality,
            deployment_locations: component.deployment_locations,

            // SBOM metadata
            scan_session_id: component.scan_session_id,
            last_scanned: component.last_scanned
        }
    """

    try:
        cursor = customer_db.aql.execute(
            query,
            bind_vars={
                'purl': component_purl,
                'tenant_id': tenant_id
            }
        )
        results = list(cursor)

        if results:
            logger.debug(
                "Component found in SBOM",
                purl=component_purl,
                tenant_id=tenant_id
            )
            return results[0]
        else:
            # Component not in SBOM
            logger.info("Component not found in SBOM", purl=component_purl)
            return {
                'in_sbom': False,
                'purl': component_purl,
                'name': None,
                'version': None
            }

    except Exception as e:
        logger.error(
            "Error verifying component presence",
            purl=component_purl,
            error=str(e)
        )
        raise


# ============================================================================
# TIER 2 EVIDENCE QUERIES (IMPORTANT)
# ============================================================================

def get_attack_techniques(db: StandardDatabase, cve_key: str) -> List[Dict[str, Any]]:
    """
    Get ATT&CK techniques that exploit this CVE via the CWE→CAPEC→ATT&CK chain.

    This is Tier 2 important evidence. EU CRA recommends attack technique
    correlation for threat modeling and risk assessment.

    Graph Path:
        vulnerabilities → has_weakness → weaknesses →
        ← capec_relates_to_cwe ← attack_patterns (CAPEC) →
        capec_maps_to_attack → attack_techniques (ATT&CK)

    Args:
        db: ArangoDB database instance
        cve_key: CVE key (e.g., 'CVE-2021-44228')

    Returns:
        List of ATT&CK techniques with full graph path provenance

    Example:
        >>> results = get_attack_techniques(db, 'CVE-2021-44228')
        >>> results[0]['technique_id']
        'T1190'
        >>> results[0]['technique_name']
        'Exploit Public-Facing Application'
        >>> results[0]['graph_path']
        ['vulnerabilities/cve-2021-44228', 'weaknesses/CWE-502',
         'attack_patterns/CAPEC-248', 'attack_techniques/T1190']

    Performance: ~200-500ms (3-hop traversal with DISTINCT)

    Validation:
        Not all CVEs have complete chains (acceptable to return empty list)
    """
    query = """
    FOR vuln IN vulnerabilities
        FILTER vuln.cve_id == @cve_id

        // Step 1: CVE → CWE
        FOR cwe IN 1..1 OUTBOUND vuln has_weakness

            // Step 2: CWE ← CAPEC (inbound from CAPEC to CWE)
            FOR capec IN 1..1 INBOUND cwe capec_relates_to_cwe

                // Step 3: CAPEC → ATT&CK
                FOR attack IN 1..1 OUTBOUND capec capec_maps_to_attack

                    RETURN DISTINCT {
                        // ATT&CK Technique
                        _id: attack._id,
                        _key: attack._key,
                        technique_id: attack.technique_id,
                        technique_name: attack.name,
                        tactic: attack.tactic,
                        description: attack.description,
                        platforms: attack.platforms,

                        // Intermediate CAPEC
                        capec_id: capec.capec_id,
                        capec_name: capec.name,
                        capec_graph_id: capec._id,

                        // Intermediate CWE
                        cwe_id: cwe.cwe_id,
                        cwe_graph_id: cwe._id,

                        // Full graph path for provenance
                        graph_path: [vuln._id, cwe._id, capec._id, attack._id]
                    }
    """

    try:
        cursor = db.aql.execute(query, bind_vars={'cve_id': cve_key.upper()})
        results = list(cursor)

        logger.debug(
            "ATT&CK techniques retrieved",
            cve_id=cve_key,
            count=len(results)
        )
        return results

    except Exception as e:
        logger.error("Error retrieving ATT&CK techniques", cve_id=cve_key, error=str(e))
        raise


def get_mitigation_controls(
    db: StandardDatabase,
    cve_key: str
) -> List[Dict[str, Any]]:
    """
    Get NIST 800-53 / OSCAL controls that mitigate this CVE.

    This is Tier 2 important evidence. FDA 524B requires documented
    mitigations for all identified vulnerabilities.

    Graph Path:
        vulnerabilities → ... → attack_techniques →
        technique_mitigated_by_control → oscal_controls

    Note: This builds on get_attack_techniques() results

    Args:
        db: ArangoDB database instance
        cve_key: CVE key (e.g., 'CVE-2021-44228')

    Returns:
        List of OSCAL controls with effectiveness ratings

    Example:
        >>> results = get_mitigation_controls(db, 'CVE-2021-44228')
        >>> results[0]['control_id']
        'SI-10'
        >>> results[0]['control_title']
        'Information Input Validation'
        >>> results[0]['mitigation_effectiveness']
        'complete'

    Performance: ~300-600ms (extends ATT&CK query by 1 hop)

    Validation:
        Controls are available only if ATT&CK techniques exist
    """
    query = """
    FOR vuln IN vulnerabilities
        FILTER vuln.cve_id == @cve_id

        // Traverse through CWE → CAPEC → ATT&CK
        FOR cwe IN 1..1 OUTBOUND vuln has_weakness
            FOR capec IN 1..1 INBOUND cwe capec_relates_to_cwe
                FOR attack IN 1..1 OUTBOUND capec capec_maps_to_attack

                    // Step 4: ATT&CK → Controls
                    FOR control, edge IN 1..1 OUTBOUND attack technique_mitigated_by_control

                        RETURN DISTINCT {
                            // Control
                            _id: control._id,
                            _key: control._key,
                            control_id: control.control_id,
                            control_title: control.title,
                            framework: control.framework,
                            control_family: control.family,

                            // Mitigation metadata from edge
                            mitigation_effectiveness: edge.effectiveness,
                            mitigation_edge_id: edge._id,

                            // Related ATT&CK technique
                            technique_id: attack.technique_id,
                            technique_graph_id: attack._id,

                            // Full graph path
                            graph_path: [vuln._id, cwe._id, capec._id, attack._id, control._id]
                        }
    """

    try:
        cursor = db.aql.execute(query, bind_vars={'cve_id': cve_key.upper()})
        results = list(cursor)

        logger.debug(
            "Mitigation controls retrieved",
            cve_id=cve_key,
            count=len(results)
        )
        return results

    except Exception as e:
        logger.error("Error retrieving mitigation controls", cve_id=cve_key, error=str(e))
        raise


def get_remediation_info(
    db: StandardDatabase,
    cve_key: str,
    component_purl: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get remediation information including patches, upgrades, and workarounds.

    This is Tier 2 important evidence. FDA 524B requires a remediation plan
    for all vulnerabilities with available fixes.

    Query Sources:
        1. CVE references (vendor advisories)
        2. Component fix_versions (from PURL ecosystem)
        3. Workaround documentation

    Args:
        db: ArangoDB database instance
        cve_key: CVE key (e.g., 'CVE-2021-44228')
        component_purl: Optional component PURL for fix version lookup

    Returns:
        Remediation information with fix availability and paths

    Example:
        >>> result = get_remediation_info(
        ...     db,
        ...     'CVE-2021-44228',
        ...     'pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1'
        ... )
        >>> result['fix_available']
        True
        >>> result['fix_version']
        '2.17.1'

    Performance: ~50-150ms (simple lookups)

    Note:
        This is a simplified implementation. Production systems should
        integrate with vulnerability databases for comprehensive fix data.
    """
    query = """
    FOR vuln IN vulnerabilities
        FILTER vuln.cve_id == @cve_id
        LIMIT 1
        RETURN {
            cve_id: vuln._id,

            // Vendor advisory references
            vendor_advisories: (
                FOR ref IN vuln.references
                    FILTER ref.type == 'Patch' OR ref.type == 'Vendor Advisory'
                    RETURN ref
            ),

            // Fix metadata
            fix_available: vuln.fix_available != null ? vuln.fix_available : false,
            fix_versions: vuln.fix_versions,

            // Workaround information
            workaround_available: vuln.workaround_available,
            workaround_description: vuln.workaround_description,

            // Patch complexity
            patch_complexity: vuln.patch_complexity
        }
    """

    try:
        cursor = db.aql.execute(query, bind_vars={'cve_id': cve_key.upper()})
        results = list(cursor)

        if results:
            logger.debug("Remediation info retrieved", cve_id=cve_key)
            return results[0]
        else:
            logger.warning("CVE not found for remediation check", cve_id=cve_key)
            return {
                'fix_available': False,
                'vendor_advisories': []
            }

    except Exception as e:
        logger.error("Error retrieving remediation info", cve_id=cve_key, error=str(e))
        raise


def get_compliance_violations(
    db: StandardDatabase,
    cve_key: str,
    framework: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get regulatory requirement violations caused by this CVE.

    This is Tier 2 important evidence. EU CRA requires mapping vulnerabilities
    to compliance obligations for regulatory reporting.

    Graph Path:
        vulnerabilities → violates_requirement → regulatory_requirements

    Args:
        db: ArangoDB database instance
        cve_key: CVE key (e.g., 'CVE-2021-44228')
        framework: Optional framework filter ('CRA', 'FDA_524B', 'IEC_62304')

    Returns:
        List of violated regulatory requirements

    Example:
        >>> results = get_compliance_violations(db, 'CVE-2021-44228', 'CRA')
        >>> results[0]['requirement_id']
        'CRA_I_1_a'
        >>> results[0]['framework']
        'CRA'
        >>> results[0]['obligation_level']
        'shall'

    Performance: ~50-100ms (single-hop edge traversal)

    Validation:
        Not all CVEs violate requirements (acceptable to return empty list)
    """
    query = """
    FOR vuln IN vulnerabilities
        FILTER vuln.cve_id == @cve_id

        FOR req, edge IN 1..1 OUTBOUND vuln violates_requirement
            FILTER @framework == null OR req.framework == @framework

            RETURN {
                // Requirement
                _id: req._id,
                _key: req._key,
                requirement_id: req.requirement_id,
                requirement_title: req.title,
                framework: req.framework,
                obligation_level: req.obligation_level,

                // Violation metadata
                violation_edge_id: edge._id,
                violation_severity: edge.severity,
                violation_deadline: edge.deadline,

                // Full requirement text
                requirement_text: req.requirement_text
            }
    """

    try:
        cursor = db.aql.execute(
            query,
            bind_vars={
                'cve_id': cve_key.upper(),
                'framework': framework
            }
        )
        results = list(cursor)

        logger.debug(
            "Compliance violations retrieved",
            cve_id=cve_key,
            framework=framework,
            count=len(results)
        )
        return results

    except Exception as e:
        logger.error(
            "Error retrieving compliance violations",
            cve_id=cve_key,
            error=str(e)
        )
        raise


# ============================================================================
# OPTIMIZED MULTI-HOP QUERIES
# ============================================================================

def get_full_evidence_chain(db: StandardDatabase, cve_key: str) -> List[Dict[str, Any]]:
    """
    Get complete evidence chain: CVE → CWE → CAPEC → ATT&CK → Controls.

    This is the MOST IMPORTANT QUERY for regulatory justification. It provides
    the complete graph provenance from vulnerability to mitigation controls
    in a single traversal.

    Graph Path:
        1. vulnerabilities → has_weakness → weaknesses (CWE)
        2. weaknesses ← capec_relates_to_cwe ← attack_patterns (CAPEC)
        3. attack_patterns → capec_maps_to_attack → attack_techniques (ATT&CK)
        4. attack_techniques → technique_mitigated_by_control → oscal_controls

    Args:
        db: ArangoDB database instance
        cve_key: CVE key (e.g., 'CVE-2021-44228')

    Returns:
        List of complete evidence chains with all nodes and edges

    Example:
        >>> chains = get_full_evidence_chain(db, 'CVE-2021-44228')
        >>> chain = chains[0]
        >>> chain['cve']['cve_id']
        'CVE-2021-44228'
        >>> chain['cwe']['cwe_id']
        'CWE-502'
        >>> chain['capec']['capec_id']
        'CAPEC-248'
        >>> chain['attack']['technique_id']
        'T1190'
        >>> chain['control']['control_id']
        'SI-10'

    Performance: ~500-1000ms (4-hop traversal with full provenance)

    Use Case:
        Generate regulatory report showing full attack path and mitigations
    """
    query = """
    FOR vuln IN vulnerabilities
        FILTER vuln.cve_id == @cve_id

        // Step 1: CVE → CWE
        FOR cwe, has_weakness_edge IN 1..1 OUTBOUND vuln has_weakness

            // Step 2: CWE ← CAPEC (inbound)
            FOR capec, capec_cwe_edge IN 1..1 INBOUND cwe capec_relates_to_cwe

                // Step 3: CAPEC → ATT&CK
                FOR attack, capec_attack_edge IN 1..1 OUTBOUND capec capec_maps_to_attack

                    // Step 4: ATT&CK → Controls
                    FOR control, mitigation_edge IN 1..1 OUTBOUND attack technique_mitigated_by_control

                        RETURN {
                            // CVE Node
                            cve: {
                                _id: vuln._id,
                                _key: vuln._key,
                                cve_id: vuln.cve_id,
                                description: vuln.description,
                                cvss_v3_score: vuln.cvss_v3_score,
                                cvss_v3_severity: vuln.cvss_v3_severity
                            },

                            // CWE Node
                            cwe: {
                                _id: cwe._id,
                                _key: cwe._key,
                                cwe_id: cwe.cwe_id,
                                name: cwe.name,
                                edge_id: has_weakness_edge._id
                            },

                            // CAPEC Node
                            capec: {
                                _id: capec._id,
                                _key: capec._key,
                                capec_id: capec.capec_id,
                                name: capec.name,
                                edge_id: capec_cwe_edge._id
                            },

                            // ATT&CK Node
                            attack: {
                                _id: attack._id,
                                _key: attack._key,
                                technique_id: attack.technique_id,
                                name: attack.name,
                                tactic: attack.tactic,
                                edge_id: capec_attack_edge._id
                            },

                            // Control Node
                            control: {
                                _id: control._id,
                                _key: control._key,
                                control_id: control.control_id,
                                title: control.title,
                                family: control.family,
                                effectiveness: mitigation_edge.effectiveness,
                                edge_id: mitigation_edge._id
                            },

                            // Full graph path (for citation)
                            graph_path: [
                                vuln._id,
                                cwe._id,
                                capec._id,
                                attack._id,
                                control._id
                            ],

                            // Edge provenance
                            edge_path: [
                                has_weakness_edge._id,
                                capec_cwe_edge._id,
                                capec_attack_edge._id,
                                mitigation_edge._id
                            ]
                        }
    """

    try:
        cursor = db.aql.execute(query, bind_vars={'cve_id': cve_key.upper()})
        results = list(cursor)

        logger.info(
            "Full evidence chain retrieved",
            cve_id=cve_key,
            chain_count=len(results)
        )
        return results

    except Exception as e:
        logger.error("Error retrieving full evidence chain", cve_id=cve_key, error=str(e))
        raise


def get_all_tier1_evidence(
    reference_db: StandardDatabase,
    customer_db: Optional[StandardDatabase],
    cve_key: str,
    component_purl: str,
    tenant_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Collect all Tier 1 evidence in parallel-optimized queries.

    This function orchestrates collection of all critical evidence required
    for VEX generation. It minimizes database round-trips by using
    efficient query patterns.

    Tier 1 Evidence Collected:
        1. CVE metadata (CVSS, severity, description)
        2. CWE mappings (weakness classification)
        3. KEV status (CISA catalog membership)
        4. Exploitability data (EPSS scores, exploit availability)
        5. Component presence (SBOM validation)

    Args:
        reference_db: Reference database (CVE/CWE/ATT&CK data)
        customer_db: Customer database (SBOM data), optional
        cve_key: CVE key (e.g., 'CVE-2021-44228')
        component_purl: Component Package URL
        tenant_id: Optional tenant ID for multi-tenant environments

    Returns:
        Dictionary containing all Tier 1 evidence

    Example:
        >>> evidence = get_all_tier1_evidence(
        ...     ref_db,
        ...     customer_db,
        ...     'CVE-2021-44228',
        ...     'pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1',
        ...     'tenant_123'
        ... )
        >>> evidence['cve_metadata']['cvss_v3_score']
        10.0
        >>> evidence['kev_status']['in_kev']
        True
        >>> evidence['component_presence']['in_sbom']
        True

    Performance: ~150-300ms (parallel collection via single query)

    Validation:
        Returns tier_1_complete: true if all required evidence is present
    """
    # Single optimized query for Tier 1 reference data
    tier1_query = """
    FOR vuln IN vulnerabilities
        FILTER vuln.cve_id == @cve_id
        LIMIT 1

        // CWE mappings
        LET cwe_mappings = (
            FOR cwe, edge IN 1..1 OUTBOUND vuln has_weakness
                RETURN {
                    _id: cwe._id,
                    _key: cwe._key,
                    edge_id: edge._id,
                    cwe_id: cwe.cwe_id,
                    name: cwe.name,
                    description: cwe.description,
                    weakness_type: cwe.weakness_type
                }
        )

        // KEV status
        LET kev = FIRST(
            FOR k IN 1..1 OUTBOUND vuln in_kev_catalog
                RETURN k
        )

        // EPSS score (latest)
        LET epss = FIRST(
            FOR e IN 1..1 OUTBOUND vuln has_epss_score
                SORT e.date DESC
                LIMIT 1
                RETURN e
        )

        RETURN {
            // CVE metadata
            cve_metadata: {
                _id: vuln._id,
                _key: vuln._key,
                cve_id: vuln.cve_id,
                description: vuln.description,
                cvss_v3_score: vuln.cvss_v3_score,
                cvss_v3_vector: vuln.cvss_v3_vector,
                cvss_v3_severity: vuln.cvss_v3_severity,
                published_date: vuln.published_date,
                last_modified_date: vuln.last_modified_date
            },

            // CWE mappings
            cwe_mappings: cwe_mappings,

            // KEV status
            kev_status: {
                in_kev: kev != null,
                kev_id: kev ? kev._id : null,
                kev_date_added: kev ? kev.date_added : null,
                kev_due_date: kev ? kev.due_date : null,
                kev_required_action: kev ? kev.required_action : null
            },

            // Exploitability
            exploitability: {
                epss_score: epss ? epss.epss : null,
                epss_percentile: epss ? epss.percentile : null,
                epss_date: epss ? epss.date : null,
                epss_id: epss ? epss._id : null,
                exploit_available: vuln.exploit_available,
                exploit_maturity: vuln.exploit_maturity
            }
        }
    """

    try:
        # Execute Tier 1 query on reference database
        cursor = reference_db.aql.execute(tier1_query, bind_vars={'cve_id': cve_key.upper()})
        results = list(cursor)

        if not results:
            raise ValueError(f"CVE not found: {cve_key}")

        tier1_evidence = results[0]

        # Component presence check (separate database)
        if customer_db:
            component_evidence = verify_component_presence(
                customer_db,
                component_purl,
                tenant_id
            )
        else:
            component_evidence = {
                'in_sbom': False,
                'purl': component_purl
            }

        tier1_evidence['component_presence'] = component_evidence

        # Validate completeness
        tier_1_complete = (
            tier1_evidence['cve_metadata']['cvss_v3_score'] is not None and
            len(tier1_evidence['cwe_mappings']) > 0
        )

        tier1_evidence['tier_1_complete'] = tier_1_complete
        tier1_evidence['collection_timestamp'] = datetime.utcnow().isoformat()

        logger.info(
            "Tier 1 evidence collection complete",
            cve_id=cve_key,
            complete=tier_1_complete,
            cwe_count=len(tier1_evidence['cwe_mappings'])
        )

        return tier1_evidence

    except Exception as e:
        logger.error("Error collecting Tier 1 evidence", cve_id=cve_key, error=str(e))
        raise


def get_all_tier2_evidence(
    db: StandardDatabase,
    cve_key: str
) -> Dict[str, Any]:
    """
    Collect all Tier 2 evidence in optimized queries.

    This function collects important but non-critical evidence for
    enhanced VEX assessments and regulatory reporting.

    Tier 2 Evidence Collected:
        1. ATT&CK techniques (attack paths)
        2. Mitigation controls (NIST 800-53, OSCAL)
        3. Remediation information (patches, workarounds)
        4. Compliance violations (regulatory requirements)

    Args:
        db: ArangoDB database instance
        cve_key: CVE key (e.g., 'CVE-2021-44228')

    Returns:
        Dictionary containing all Tier 2 evidence

    Example:
        >>> evidence = get_all_tier2_evidence(db, 'CVE-2021-44228')
        >>> len(evidence['attack_techniques'])
        3
        >>> len(evidence['mitigation_controls'])
        5

    Performance: ~400-800ms (multi-hop traversals)

    Validation:
        Returns tier_2_complete: true if at least some Tier 2 evidence exists
    """
    # Optimized query for Tier 2 evidence
    tier2_query = """
    FOR vuln IN vulnerabilities
        FILTER vuln.cve_id == @cve_id
        LIMIT 1

        // Attack techniques via CWE → CAPEC → ATT&CK
        LET attack_techniques = (
            FOR cwe IN 1..1 OUTBOUND vuln has_weakness
                FOR capec IN 1..1 INBOUND cwe capec_relates_to_cwe
                    FOR attack IN 1..1 OUTBOUND capec capec_maps_to_attack
                        RETURN DISTINCT {
                            _id: attack._id,
                            technique_id: attack.technique_id,
                            technique_name: attack.name,
                            tactic: attack.tactic,
                            capec_id: capec.capec_id,
                            cwe_id: cwe.cwe_id,
                            graph_path: [vuln._id, cwe._id, capec._id, attack._id]
                        }
        )

        // Mitigation controls (extend from attack techniques)
        LET mitigation_controls = (
            FOR cwe IN 1..1 OUTBOUND vuln has_weakness
                FOR capec IN 1..1 INBOUND cwe capec_relates_to_cwe
                    FOR attack IN 1..1 OUTBOUND capec capec_maps_to_attack
                        FOR control, edge IN 1..1 OUTBOUND attack technique_mitigated_by_control
                            RETURN DISTINCT {
                                _id: control._id,
                                control_id: control.control_id,
                                control_title: control.title,
                                framework: control.framework,
                                effectiveness: edge.effectiveness,
                                technique_id: attack.technique_id,
                                graph_path: [vuln._id, cwe._id, capec._id, attack._id, control._id]
                            }
        )

        // Compliance violations
        LET compliance_violations = (
            FOR req, edge IN 1..1 OUTBOUND vuln violates_requirement
                RETURN {
                    _id: req._id,
                    requirement_id: req.requirement_id,
                    framework: req.framework,
                    obligation_level: req.obligation_level,
                    violation_severity: edge.severity
                }
        )

        RETURN {
            attack_techniques: attack_techniques,
            mitigation_controls: mitigation_controls,
            compliance_violations: compliance_violations,

            // Remediation info from CVE document
            remediation: {
                fix_available: vuln.fix_available,
                fix_versions: vuln.fix_versions,
                workaround_available: vuln.workaround_available,
                vendor_advisories: (
                    FOR ref IN vuln.references
                        FILTER ref.type == 'Patch' OR ref.type == 'Vendor Advisory'
                        RETURN ref
                )
            }
        }
    """

    try:
        cursor = db.aql.execute(tier2_query, bind_vars={'cve_id': cve_key.upper()})
        results = list(cursor)

        if not results:
            raise ValueError(f"CVE not found: {cve_key}")

        tier2_evidence = results[0]

        # Validate completeness
        tier_2_complete = (
            len(tier2_evidence['attack_techniques']) > 0 or
            len(tier2_evidence['mitigation_controls']) > 0
        )

        tier2_evidence['tier_2_complete'] = tier_2_complete
        tier2_evidence['collection_timestamp'] = datetime.utcnow().isoformat()

        logger.info(
            "Tier 2 evidence collection complete",
            cve_id=cve_key,
            complete=tier_2_complete,
            attack_count=len(tier2_evidence['attack_techniques']),
            control_count=len(tier2_evidence['mitigation_controls'])
        )

        return tier2_evidence

    except Exception as e:
        logger.error("Error collecting Tier 2 evidence", cve_id=cve_key, error=str(e))
        raise


# ============================================================================
# HELPER UTILITIES
# ============================================================================

def normalize_cve_key(cve_input: str) -> str:
    """
    Normalize CVE input to standard format.

    Args:
        cve_input: CVE in any format ('CVE-2021-44228', 'cve-2021-44228', etc.)

    Returns:
        Normalized CVE key ('CVE-2021-44228')

    Example:
        >>> normalize_cve_key('cve-2021-44228')
        'CVE-2021-44228'
        >>> normalize_cve_key('CVE_2021_44228')
        'CVE-2021-44228'
    """
    cve_upper = cve_input.upper().replace('_', '-')
    if not cve_upper.startswith('CVE-'):
        cve_upper = 'CVE-' + cve_upper
    return cve_upper


def extract_purl_components(purl: str) -> Dict[str, str]:
    """
    Extract components from Package URL (PURL).

    Note: Production systems should use the `packageurl-python` library.
    This is a simplified implementation for demonstration.

    Args:
        purl: Package URL (e.g., 'pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1')

    Returns:
        Dictionary with type, namespace, name, version

    Example:
        >>> extract_purl_components('pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1')
        {
            'type': 'maven',
            'namespace': 'org.apache.logging.log4j',
            'name': 'log4j-core',
            'version': '2.14.1'
        }
    """
    # Remove 'pkg:' prefix
    if purl.startswith('pkg:'):
        purl = purl[4:]

    # Split type and rest
    parts = purl.split('/', 1)
    purl_type = parts[0]

    if len(parts) < 2:
        return {'type': purl_type, 'namespace': None, 'name': None, 'version': None}

    rest = parts[1]

    # Extract version
    if '@' in rest:
        path, version = rest.rsplit('@', 1)
    else:
        path = rest
        version = None

    # Extract namespace and name
    path_parts = path.split('/')
    if len(path_parts) > 1:
        namespace = '/'.join(path_parts[:-1])
        name = path_parts[-1]
    else:
        namespace = None
        name = path_parts[0]

    return {
        'type': purl_type,
        'namespace': namespace,
        'name': name,
        'version': version
    }


def validate_evidence_completeness(evidence: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate evidence completeness for regulatory compliance.

    Args:
        evidence: Evidence dictionary from get_all_tier1_evidence()

    Returns:
        Tuple of (is_complete, missing_items)

    Example:
        >>> is_complete, missing = validate_evidence_completeness(evidence)
        >>> if not is_complete:
        ...     print(f"Missing: {missing}")
        Missing: ['epss_score', 'component_presence']
    """
    missing = []

    # Check CVE metadata
    if not evidence.get('cve_metadata', {}).get('cvss_v3_score'):
        missing.append('cvss_v3_score')

    # Check CWE mappings
    if not evidence.get('cwe_mappings') or len(evidence['cwe_mappings']) == 0:
        missing.append('cwe_mappings')

    # Check KEV status (always present, just validate)
    if 'kev_status' not in evidence:
        missing.append('kev_status')

    # Check exploitability (EPSS preferred but not required)
    if not evidence.get('exploitability', {}).get('epss_score'):
        missing.append('epss_score (recommended)')

    # Check component presence
    if not evidence.get('component_presence'):
        missing.append('component_presence')

    is_complete = len([m for m in missing if 'recommended' not in m]) == 0

    return is_complete, missing


# ============================================================================
# MODULE EXPORTS
# ============================================================================

__all__ = [
    # Tier 1 Queries (Critical)
    'get_cve_metadata',
    'get_cwe_mappings',
    'get_kev_status',
    'get_exploitability_data',
    'verify_component_presence',

    # Tier 2 Queries (Important)
    'get_attack_techniques',
    'get_mitigation_controls',
    'get_remediation_info',
    'get_compliance_violations',

    # Optimized Queries
    'get_full_evidence_chain',
    'get_all_tier1_evidence',
    'get_all_tier2_evidence',

    # Helper Utilities
    'normalize_cve_key',
    'extract_purl_components',
    'validate_evidence_completeness',

    # Constants
    'PERFORMANCE_TARGETS',
    'REQUIRED_INDEXES',
]
