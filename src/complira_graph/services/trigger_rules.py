"""
Trigger rules for automatic regulatory requirement edge generation.

This module implements 4 hardcoded trigger rules for Phase 3A-B:
1. KEV Entry → 24h urgency (FDA 524B, CRA)
2. CVSS 9.0+ → high urgency
3. Ransomware Exploitation → critical urgency
4. Exploit Chain → critical urgency

Each rule generates vuln_triggers_requirement edges with full provenance metadata.
"""

from typing import Optional
from datetime import datetime
from arango.database import StandardDatabase
import structlog

logger = structlog.get_logger()


def trigger_rule_kev_entry(
    db: StandardDatabase,
    checkpoint_date: Optional[str] = None
) -> int:
    """
    Trigger Rule 1: KEV Entry → 24h urgency (FDA 524B, CRA).

    For each CVE in vulncheck_kev_entries:
        Create edge: vulnerabilities/{cve_id} → regulatory_requirements/FDA_524B_KEV_RESPONSE

    Args:
        db: ArangoDB database connection
        checkpoint_date: Process only entries added after this date (ISO 8601 format)

    Returns:
        Number of edges created

    Performance:
        - First run: ~45 seconds (4,609 KEV entries)
        - Incremental run: ~2 seconds (e.g., 150 new entries)

    Example:
        >>> edges = trigger_rule_kev_entry(db, checkpoint_date="2026-03-04T12:00:00Z")
        >>> print(f"Created {edges} KEV trigger edges")
    """
    logger.info(
        "Executing KEV entry trigger rule",
        checkpoint=checkpoint_date,
        rule="kev_entry"
    )

    query = """
    FOR kev IN vulncheck_kev_entries
        // Checkpoint filter (incremental processing)
        FILTER @checkpoint_date == null OR kev.date_added > @checkpoint_date

        // Find vulnerability by cve_id (not _key)
        LET vuln = FIRST(
            FOR v IN vulnerabilities
                FILTER v.cve_id == kev.primary_cve_id
                LIMIT 1
                RETURN v
        )
        FILTER vuln != null

        // Check if requirement exists
        LET req_key = 'regulatory_requirements/FDA_524B_KEV_RESPONSE'
        LET req_exists = DOCUMENT(req_key) != null
        FILTER req_exists

        // Check if edge already exists (idempotency)
        LET edge_exists = LENGTH(
            FOR edge IN vuln_triggers_requirement
                FILTER edge._from == vuln._id AND edge._to == req_key
                LIMIT 1
                RETURN edge
        ) > 0
        FILTER !edge_exists

        // Insert edge with metadata
        INSERT {
            _from: vuln._id,
            _to: req_key,
            trigger_rule: 'kev_entry',
            urgency: '24h',
            confidence: 1.0,
            evidence: {
                source: 'vulncheck_kev',
                date_added: kev.date_added,
                vulncheck_first: kev.vulncheck_first,
                description: kev.short_description
            },
            trigger_timestamp: DATE_ISO8601(DATE_NOW()),
            trigger_source: 'regulatory_trigger_service_v1'
        } INTO vuln_triggers_requirement

        RETURN NEW
    """

    bind_vars = {"checkpoint_date": checkpoint_date}

    try:
        cursor = db.aql.execute(query, bind_vars=bind_vars)
        results = list(cursor)

        logger.info(
            "KEV entry trigger rule complete",
            edges_created=len(results),
            rule="kev_entry"
        )

        return len(results)

    except Exception as e:
        logger.error(
            "KEV entry trigger rule failed",
            error=str(e),
            rule="kev_entry"
        )
        raise


def trigger_rule_cvss_critical(db: StandardDatabase) -> int:
    """
    Trigger Rule 2: CVSS 9.0+ → high urgency.

    For each CVE with cvss_v3_score >= 9.0:
        Create edge: vulnerabilities/{cve_id} → regulatory_requirements/FDA_524B_CVSS_HIGH

    Args:
        db: ArangoDB database connection

    Returns:
        Number of edges created

    Performance:
        - First run: ~150 seconds (15,234 CVEs with CVSS 9.0+)
        - Subsequent run: ~1 second (idempotent, no new edges)

    Example:
        >>> edges = trigger_rule_cvss_critical(db)
        >>> print(f"Created {edges} CVSS critical trigger edges")
    """
    logger.info(
        "Executing CVSS critical trigger rule",
        rule="cvss_critical"
    )

    query = """
    FOR vuln IN vulnerabilities
        // CVSS filter (9.0+)
        LET cvss_score = vuln.cvss_v31.baseScore OR vuln.cvss_v3.baseScore
        FILTER cvss_score >= 9.0

        // Check if requirement exists
        LET req_key = 'regulatory_requirements/FDA_524B_CVSS_HIGH'
        LET req_exists = DOCUMENT(req_key) != null
        FILTER req_exists

        // Check if edge already exists (idempotency)
        LET edge_exists = LENGTH(
            FOR edge IN vuln_triggers_requirement
                FILTER edge._from == vuln._id AND edge._to == req_key
                LIMIT 1
                RETURN edge
        ) > 0
        FILTER !edge_exists

        // Insert edge with metadata
        INSERT {
            _from: vuln._id,
            _to: req_key,
            trigger_rule: 'cvss_critical',
            urgency: 'high',
            confidence: 0.95,
            evidence: {
                cvss_v3_score: cvss_score,
                cvss_vector: vuln.cvss_v31.vectorString OR vuln.cvss_v3.vectorString
            },
            trigger_timestamp: DATE_ISO8601(DATE_NOW()),
            trigger_source: 'regulatory_trigger_service_v1'
        } INTO vuln_triggers_requirement

        RETURN NEW
    """

    try:
        cursor = db.aql.execute(query)
        results = list(cursor)

        logger.info(
            "CVSS critical trigger rule complete",
            edges_created=len(results),
            rule="cvss_critical"
        )

        return len(results)

    except Exception as e:
        logger.error(
            "CVSS critical trigger rule failed",
            error=str(e),
            rule="cvss_critical"
        )
        raise


def trigger_rule_ransomware_exploitation(db: StandardDatabase) -> int:
    """
    Trigger Rule 3: Ransomware Exploitation → critical urgency.

    For each CVE exploited by ransomware:
        Create edge: vulnerabilities/{cve_id} → regulatory_requirements/CRA_RANSOMWARE_EXPLOITATION

    Args:
        db: ArangoDB database connection

    Returns:
        Number of edges created

    Performance:
        - Current (Community tier): ~0.5 seconds (0 ransomware edges)
        - With paid tier: ~5-10 seconds (estimated 500-1000 ransomware-exploited CVEs)

    Note:
        Requires VulnCheck paid tier (Exploit & Vulnerability Intelligence subscription).
        With Community tier, this rule returns 0 edges (no ransomware data available).

    Example:
        >>> edges = trigger_rule_ransomware_exploitation(db)
        >>> print(f"Created {edges} ransomware trigger edges")
    """
    logger.info(
        "Executing ransomware exploitation trigger rule",
        rule="ransomware_exploitation"
    )

    query = """
    FOR edge IN exploited_by_ransomware
        // Get ransomware family details
        LET ransomware = DOCUMENT(edge._to)

        // Check if requirement exists
        LET req_key = 'regulatory_requirements/CRA_RANSOMWARE_EXPLOITATION'
        LET req_exists = DOCUMENT(req_key) != null
        FILTER req_exists

        // Check if trigger edge already exists (idempotency)
        LET trigger_edge_exists = LENGTH(
            FOR trigger_edge IN vuln_triggers_requirement
                FILTER trigger_edge._from == edge._from AND trigger_edge._to == req_key
                LIMIT 1
                RETURN trigger_edge
        ) > 0
        FILTER !trigger_edge_exists

        // Insert edge with metadata
        INSERT {
            _from: edge._from,
            _to: req_key,
            trigger_rule: 'ransomware_exploitation',
            urgency: 'critical',
            confidence: 0.98,
            evidence: {
                ransomware_family: ransomware.name,
                ransomware_first_seen: ransomware.first_seen,
                source: 'vulncheck'
            },
            trigger_timestamp: DATE_ISO8601(DATE_NOW()),
            trigger_source: 'regulatory_trigger_service_v1'
        } INTO vuln_triggers_requirement

        RETURN NEW
    """

    try:
        cursor = db.aql.execute(query)
        results = list(cursor)

        logger.info(
            "Ransomware exploitation trigger rule complete",
            edges_created=len(results),
            rule="ransomware_exploitation"
        )

        return len(results)

    except Exception as e:
        logger.error(
            "Ransomware exploitation trigger rule failed",
            error=str(e),
            rule="ransomware_exploitation"
        )
        raise


def trigger_rule_exploit_chain(db: StandardDatabase) -> int:
    """
    Trigger Rule 4: Exploit Chain → critical urgency.

    For each CVE in exploit chains:
        Create edge: vulnerabilities/{cve_id} → regulatory_requirements/CRA_EXPLOIT_CHAIN

    Args:
        db: ArangoDB database connection

    Returns:
        Number of edges created

    Performance:
        - Current (Community tier): ~0.5 seconds (0 exploit chain edges)
        - With paid tier: ~3-5 seconds (estimated 200-500 exploit chain CVEs)

    Note:
        Requires VulnCheck paid tier (Exploit & Vulnerability Intelligence subscription).
        With Community tier, this rule returns 0 edges (no exploit chain data available).

    Example:
        >>> edges = trigger_rule_exploit_chain(db)
        >>> print(f"Created {edges} exploit chain trigger edges")
    """
    logger.info(
        "Executing exploit chain trigger rule",
        rule="exploit_chain"
    )

    query = """
    FOR edge IN chain_includes_vuln
        // Get exploit chain details
        LET chain = DOCUMENT(edge._from)

        // Check if requirement exists
        LET req_key = 'regulatory_requirements/CRA_EXPLOIT_CHAIN'
        LET req_exists = DOCUMENT(req_key) != null
        FILTER req_exists

        // Check if trigger edge already exists (idempotency)
        LET trigger_edge_exists = LENGTH(
            FOR trigger_edge IN vuln_triggers_requirement
                FILTER trigger_edge._from == edge._to AND trigger_edge._to == req_key
                LIMIT 1
                RETURN trigger_edge
        ) > 0
        FILTER !trigger_edge_exists

        // Insert edge with metadata
        INSERT {
            _from: edge._to,  // Vulnerability
            _to: req_key,
            trigger_rule: 'exploit_chain',
            urgency: 'critical',
            confidence: 0.95,
            evidence: {
                chain_name: chain.name,
                chain_description: chain.description,
                chain_position: edge.position
            },
            trigger_timestamp: DATE_ISO8601(DATE_NOW()),
            trigger_source: 'regulatory_trigger_service_v1'
        } INTO vuln_triggers_requirement

        RETURN NEW
    """

    try:
        cursor = db.aql.execute(query)
        results = list(cursor)

        logger.info(
            "Exploit chain trigger rule complete",
            edges_created=len(results),
            rule="exploit_chain"
        )

        return len(results)

    except Exception as e:
        logger.error(
            "Exploit chain trigger rule failed",
            error=str(e),
            rule="exploit_chain"
        )
        raise


# Registry of all trigger rules
TRIGGER_RULES = {
    "kev_entry": trigger_rule_kev_entry,
    "cvss_critical": trigger_rule_cvss_critical,
    "ransomware_exploitation": trigger_rule_ransomware_exploitation,
    "exploit_chain": trigger_rule_exploit_chain
}


def get_trigger_rule(rule_name: str):
    """
    Get trigger rule function by name.

    Args:
        rule_name: Name of the trigger rule

    Returns:
        Trigger rule function

    Raises:
        ValueError: If rule_name is not recognized

    Example:
        >>> rule_func = get_trigger_rule("kev_entry")
        >>> edges = rule_func(db, checkpoint_date="2026-03-04T12:00:00Z")
    """
    if rule_name not in TRIGGER_RULES:
        raise ValueError(
            f"Unknown trigger rule: {rule_name}. "
            f"Valid rules: {list(TRIGGER_RULES.keys())}"
        )

    return TRIGGER_RULES[rule_name]
