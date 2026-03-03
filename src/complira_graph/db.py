"""
ArangoDB connection management and schema initialization.

This module handles:
- Database connection pooling
- Schema creation (22 document collections, 27 edge collections for v1.0)
- Index management
- Health checks

v1.0 Scope: Open data sources only
- Core Vulnerability Intelligence (6 doc, 7 edge)
- Threat & Attack Frameworks (5 doc, 7 edge)
- Compliance & Regulatory (5 doc, 4 edge)
- Software Identity & Supply Chain (5 doc, 5 edge)
- System Collections (1 doc, 4 edge)

Deferred to v2.0:
- Scanner Evidence Layers 0-4 (8 doc, 10 edge)
- Process Evidence Layer 5 (4 doc, 6 edge)
- Document Provenance Layer 6 (3 doc, 3 edge)
"""

from typing import Optional
from arango import ArangoClient
from arango.database import StandardDatabase
from arango.exceptions import DatabaseCreateError, CollectionCreateError
import structlog

from .config import get_settings

logger = structlog.get_logger()

# ========== Document Collections (22 total - v1.0 scope + system) ==========
DOCUMENT_COLLECTIONS = [
    # Core Vulnerability Intelligence (6 collections)
    "vulnerabilities",           # CVE records (NVD, OSV, GHSA)
    "weaknesses",                # CWE records with hierarchy
    "kev_entries",               # CISA Known Exploited Vulnerabilities
    "vulncheck_kev_entries",     # VulnCheck extended KEV data
    "exploit_modules",           # Metasploit, ExploitDB, Nuclei, PoC-in-GitHub
    "epss_history",              # Time-series EPSS scores

    # Threat & Attack Frameworks (5 collections)
    "attack_techniques",         # MITRE ATT&CK techniques
    "attack_patterns",           # CAPEC attack patterns
    "atlas_techniques",          # MITRE ATLAS AI/ML techniques
    "d3fend_techniques",         # MITRE D3FEND defensive techniques
    "threat_groups",             # ATT&CK threat actor groups

    # Compliance & Regulatory (5 collections)
    "regulatory_frameworks",     # Framework metadata (CRA, FDA 524B, IEC 62304, etc.)
    "regulatory_requirements",   # Individual requirements from frameworks
    "oscal_controls",            # NIST SP 800-53 Rev 5 controls
    "scf_controls",              # Secure Controls Framework 2025.4
    "opencre_nodes",             # OWASP OpenCRE nodes

    # Software Identity & Supply Chain (5 collections)
    "components",                # Software packages keyed by PURL
    "cpe_entries",               # NVD CPE dictionary
    "scorecard_results",         # OpenSSF Scorecard results
    "licenses",                  # SPDX license definitions
    "package_health",            # Package ecosystem health (deps.dev, Ecosyste.ms)

    # System Collections
    "agent_checkpoints",         # Agent execution checkpoints for resume support

    # Multi-Tenant SaaS (1 collection - Phase 0)
    "customer_profiles",         # Customer metadata and authentication
]

# ========== Edge Collections (26 total - v1.0 scope) ==========
EDGE_COLLECTIONS = [
    # Core Vulnerability Intelligence (6 edges)
    "has_weakness",              # Vulnerability → CWE
    "exploited_in_wild",         # Vulnerability → KEV entry
    "has_exploit",               # Vulnerability → exploit module/PoC
    "aliases",                   # Vulnerability ↔ Vulnerability (CVE/GHSA/OSV equivalence)
    "affects",                   # Vulnerability → component/CPE (with version ranges)
    "has_epss",                  # Vulnerability → EPSS history entry (time-series in epss_history collection)

    # Threat & Attack Frameworks (7 edges)
    "technique_exploits_weakness",   # ATT&CK technique → CWE
    "capec_relates_to_cwe",          # CAPEC → CWE
    "capec_child_of",                # CAPEC → parent CAPEC (hierarchy)
    "capec_maps_to_attack",          # CAPEC → ATT&CK
    "technique_mitigated_by_control", # ATT&CK → NIST 800-53 control
    "atlas_maps_to_attack",          # ATLAS → ATT&CK
    "d3fend_counters_technique",     # D3FEND → ATT&CK

    # CWE Hierarchy (4 edges)
    "child_of",                  # CWE → parent CWE
    "peer_of",                   # CWE ↔ peer CWE
    "can_precede",               # CWE → CWE (temporal relationship)
    "requires",                  # CWE → CWE (dependency)

    # Compliance & Regulatory (4 edges)
    "maps_to_requirement",       # CWE → regulatory requirement
    "requirement_hierarchy",     # Requirement → parent requirement (Annex → Section → Paragraph)
    "cross_framework_mapping",   # Framework ↔ framework equivalence
    "opencre_links",             # OpenCRE → standards/requirements

    # Software Identity & Supply Chain (5 edges)
    "depends_on",                # Component → component (dependency DAG)
    "matched_by_cpe",            # Component (PURL) → CPE
    "same_as",                   # Component ↔ component (identity equivalence)
    "scored_by",                 # Component → Scorecard result
    "licensed_under",            # Component → license
]

# ========== Index Definitions ==========
# Indexes optimized for query performance with cacheEnabled
INDEXES = {
    "vulnerabilities": [
        {"type": "persistent", "fields": ["cve_id"], "unique": True},
        {"type": "persistent", "fields": ["published"]},
        {"type": "persistent", "fields": ["cvss_v31.baseScore"]},
        {"type": "persistent", "fields": ["source"]},
    ],
    "weaknesses": [
        {"type": "persistent", "fields": ["cwe_id"], "unique": True},
        {"type": "persistent", "fields": ["abstraction"]},
    ],
    "kev_entries": [
        {"type": "persistent", "fields": ["cve_id"], "unique": True},
        {"type": "persistent", "fields": ["date_added"]},
    ],
    "exploit_modules": [
        {"type": "persistent", "fields": ["module_id"], "unique": True},
        {"type": "persistent", "fields": ["source"]},
        {"type": "persistent", "fields": ["cve_ids[*]"]},
    ],
    "epss_history": [
        {"type": "persistent", "fields": ["cve_id", "date"], "unique": True},
        {"type": "persistent", "fields": ["date"]},
    ],
    "attack_techniques": [
        {"type": "persistent", "fields": ["technique_id"], "unique": True},
        {"type": "persistent", "fields": ["is_subtechnique"]},
    ],
    "components": [
        {"type": "persistent", "fields": ["purl"], "unique": True},
        {"type": "persistent", "fields": ["name", "version"]},
    ],
    "cpe_entries": [
        {"type": "persistent", "fields": ["cpe23"], "unique": True},
    ],
    # Additional indexes for other collections can be added as needed
}


# Global database connection
_db: Optional[StandardDatabase] = None


def get_db() -> StandardDatabase:
    """
    Get or create ArangoDB database connection.

    Uses connection pooling for performance.
    Connection is cached globally and reused.

    Returns:
        StandardDatabase: ArangoDB database instance

    Raises:
        ConnectionError: If unable to connect to ArangoDB
    """
    global _db

    if _db is not None:
        return _db

    settings = get_settings()

    try:
        # Create ArangoDB client with connection pooling
        client = ArangoClient(
            hosts=settings.ARANGO_URL,
        )

        # Connect to system database first to create app database if needed
        sys_db = client.db(
            "_system",
            username=settings.ARANGO_USERNAME,
            password=settings.ARANGO_PASSWORD,
        )

        # Create application database if it doesn't exist
        if not sys_db.has_database(settings.ARANGO_DATABASE):
            logger.info(
                "Creating database",
                database=settings.ARANGO_DATABASE,
            )
            sys_db.create_database(settings.ARANGO_DATABASE)

        # Connect to application database
        _db = client.db(
            settings.ARANGO_DATABASE,
            username=settings.ARANGO_USERNAME,
            password=settings.ARANGO_PASSWORD,
        )

        logger.info(
            "Connected to ArangoDB",
            database=settings.ARANGO_DATABASE,
            url=settings.ARANGO_URL,
        )

        return _db

    except Exception as e:
        logger.error(
            "Failed to connect to ArangoDB",
            error=str(e),
            url=settings.ARANGO_URL,
        )
        raise ConnectionError(f"Failed to connect to ArangoDB: {e}")


def init_schema(db: Optional[StandardDatabase] = None) -> None:
    """
    Initialize database schema.

    Creates all 20 document collections and 21 edge collections for v1.0.
    Creates indexes for performance optimization.

    Args:
        db: ArangoDB database instance (uses get_db() if not provided)

    Raises:
        CollectionCreateError: If unable to create collections
    """
    if db is None:
        db = get_db()

    logger.info("Initializing schema", collections=len(DOCUMENT_COLLECTIONS) + len(EDGE_COLLECTIONS))

    # Create document collections
    for collection_name in DOCUMENT_COLLECTIONS:
        if not db.has_collection(collection_name):
            try:
                db.create_collection(collection_name, edge=False)
                logger.info("Created document collection", collection=collection_name)
            except CollectionCreateError as e:
                logger.warning(
                    "Collection already exists or creation failed",
                    collection=collection_name,
                    error=str(e),
                )
        else:
            logger.debug("Collection already exists", collection=collection_name)

    # Create edge collections
    for edge_name in EDGE_COLLECTIONS:
        if not db.has_collection(edge_name):
            try:
                db.create_collection(edge_name, edge=True)
                logger.info("Created edge collection", edge=edge_name)
            except CollectionCreateError as e:
                logger.warning(
                    "Edge collection already exists or creation failed",
                    edge=edge_name,
                    error=str(e),
                )
        else:
            logger.debug("Edge collection already exists", edge=edge_name)

    logger.info(
        "Schema initialization complete",
        document_collections=len(DOCUMENT_COLLECTIONS),
        edge_collections=len(EDGE_COLLECTIONS),
    )


def create_indexes(db: Optional[StandardDatabase] = None) -> None:
    """
    Create performance indexes on collections.

    Indexes are created with:
    - type: persistent (cached in memory)
    - cacheEnabled: true (for performance)

    Args:
        db: ArangoDB database instance (uses get_db() if not provided)
    """
    if db is None:
        db = get_db()

    logger.info("Creating indexes")

    for collection_name, indexes in INDEXES.items():
        if not db.has_collection(collection_name):
            logger.warning("Collection does not exist, skipping indexes", collection=collection_name)
            continue

        collection = db.collection(collection_name)

        for index_def in indexes:
            try:
                collection.add_persistent_index(
                    fields=index_def["fields"],
                    unique=index_def.get("unique", False),
                    sparse=False,
                    name=None,  # Auto-generate index name
                )
                logger.info(
                    "Created index",
                    collection=collection_name,
                    fields=index_def["fields"],
                    unique=index_def.get("unique", False),
                )
            except Exception as e:
                logger.warning(
                    "Index creation failed or already exists",
                    collection=collection_name,
                    fields=index_def["fields"],
                    error=str(e),
                )

    logger.info("Index creation complete")


def drop_indexes(collection_name: str, db: Optional[StandardDatabase] = None) -> None:
    """
    Drop all non-primary indexes from a collection.

    Used before bulk import to improve performance.
    Indexes should be rebuilt with rebuild_indexes() after bulk import.

    Args:
        collection_name: Name of the collection
        db: ArangoDB database instance (uses get_db() if not provided)
    """
    if db is None:
        db = get_db()

    if not db.has_collection(collection_name):
        logger.warning("Collection does not exist", collection=collection_name)
        return

    collection = db.collection(collection_name)

    # Get all indexes except primary
    indexes = collection.indexes()
    dropped_count = 0

    for index in indexes:
        # Never drop the primary index
        if index["type"] == "primary":
            continue

        try:
            collection.delete_index(index["id"])
            dropped_count += 1
            logger.debug("Dropped index", collection=collection_name, index=index["id"])
        except Exception as e:
            logger.warning(
                "Failed to drop index",
                collection=collection_name,
                index=index["id"],
                error=str(e),
            )

    logger.info("Dropped indexes", collection=collection_name, count=dropped_count)


def rebuild_indexes(collection_name: str, db: Optional[StandardDatabase] = None) -> None:
    """
    Rebuild indexes for a collection after bulk import.

    Args:
        collection_name: Name of the collection
        db: ArangoDB database instance (uses get_db() if not provided)
    """
    if db is None:
        db = get_db()

    if collection_name not in INDEXES:
        logger.debug("No indexes defined for collection", collection=collection_name)
        return

    if not db.has_collection(collection_name):
        logger.warning("Collection does not exist", collection=collection_name)
        return

    collection = db.collection(collection_name)
    index_defs = INDEXES[collection_name]

    for index_def in index_defs:
        try:
            collection.add_persistent_index(
                fields=index_def["fields"],
                unique=index_def.get("unique", False),
                sparse=False,
            )
            logger.debug(
                "Rebuilt index",
                collection=collection_name,
                fields=index_def["fields"],
            )
        except Exception as e:
            logger.warning(
                "Failed to rebuild index",
                collection=collection_name,
                fields=index_def["fields"],
                error=str(e),
            )

    logger.info("Rebuilt indexes", collection=collection_name)


def health_check() -> tuple[bool, str]:
    """
    Check if ArangoDB is accessible and healthy.

    Returns:
        tuple[bool, str]: (is_healthy, message)
    """
    try:
        db = get_db()
        # Simple query to verify connection
        db.aql.execute("RETURN 1")
        logger.info("Database health check passed")
        return (True, "Database connection OK")
    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        return (False, str(e))
