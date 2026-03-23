"""
ArangoDB connection management and schema initialization.

This module handles:
- Database connection pooling
- Schema creation (42 document collections, 49 edge collections)
- Index management
- Health checks

v1.0 + Phase 3A Scope:
- Core Vulnerability Intelligence (8 doc, 6 edge)
- Phase 3A: VulnCheck Intelligence (5 doc, 9 edge)
- Threat & Attack Frameworks (5 doc, 7 edge)
- Compliance & Regulatory (5 doc, 5 edge)
- Software Identity & Supply Chain (5 doc, 5 edge)
- System Collections (1 doc, 0 edge)

Phase 5: Web UI & Multi-Tenant:
- Organizations, Users, API Tokens, Audit Log (4 doc, 3 edge)
- Multi-Tenant Hierarchy: Projects, Repositories (2 doc, 0 edge)

Other:
- LLM Enrichments (1 doc, 0 edge)
- Customer API Keys (1 doc, 0 edge)
- EPSS History linkage (0 doc, 1 edge)

Phase 3A VulnCheck Integration:
- exploit_intelligence, ransomware_families, botnets, exploit_chains, eol_products
- has_exploit_intelligence, exploited_by_ransomware, exploited_by_botnet, exploited_by_threat_actor
- chain_includes_vuln, component_eol_status, ransomware_uses_technique
- botnet_uses_technique, vuln_triggers_requirement
- Note: canary_observations removed (402 Payment Required - requires Exploit & Vulnerability Intelligence subscription)

v2.2 Scanner Evidence Layer:
- scan_runs, scan_findings, detected_controls, evidence_packages (4 doc)
- component_has_vuln, finding_maps_to_weakness, finding_triggers_req,
  detected_control_maps_to, control_in_component, finding_in_component,
  evidence_links_finding, evidence_for_project, project_uses_component (9 edge)
- Architecture: components are global (purl-keyed), projects link via
  project_uses_component edge. tenant_id required on all evidence collections.

Deferred to v3.0:
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

# ========== Document Collections (42 total) ==========
DOCUMENT_COLLECTIONS = [
    # Core Vulnerability Intelligence (8 collections)
    "vulnerabilities",           # CVE records (NVD, OSV, GHSA)
    "weaknesses",                # CWE records with hierarchy
    "kev_entries",               # CISA Known Exploited Vulnerabilities
    "vulncheck_kev_entries",     # VulnCheck extended KEV data
    "exploit_modules",           # Metasploit, ExploitDB exploits
    "nuclei_templates",          # Nuclei vulnerability detection templates
    "poc_repositories",          # PoC-in-GitHub proof-of-concept repositories
    "epss_history",              # Time-series EPSS scores

    # Phase 3A: VulnCheck Intelligence (5 collections)
    "exploit_intelligence",      # VulnCheck per-CVE exploit maturity data (NVD2)
    "ransomware_families",       # Ransomware groups with CVE attribution
    "botnets",                   # Botnet campaigns with CVE attribution
    "exploit_chains",            # Multi-CVE attack sequences for threat modeling
    "eol_products",              # End-of-life products for FDA compliance tracking

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
    "llm_enrichments",           # LLM-generated enrichment data (CWE↔CVE mappings, etc.)

    # Multi-Tenant SaaS (Phase 0)
    "customer_profiles",         # Customer metadata and authentication
    "customer_api_keys",         # Per-customer API keys for programmatic access

    # Phase 5: Web UI & Multi-Tenant (4 collections)
    "organizations",             # Organization profiles (slug-keyed)
    "users",                     # User accounts with org membership
    "api_tokens",                # API tokens for programmatic access (org-scoped)
    "audit_log",                 # Audit trail for compliance and security

    # Multi-Tenant Hierarchy (2 collections)
    "projects",                  # Customer projects grouping repositories
    "repositories",              # Source code repositories linked to projects

    # v2.2 Scanner Evidence Layer (4 collections — tenant_id required)
    "scan_runs",                 # Pipeline execution metadata (replaces scan_sessions in reference DB)
    "scan_findings",             # Universal scanner findings (SAST/secrets/DAST/SCA/firmware)
    "detected_controls",         # Positive security control detections from scanner output
    "evidence_packages",         # Regulatory evidence bundles (SBOM + MCP + scan run)
]

# ========== Edge Collections (49 total) ==========
EDGE_COLLECTIONS = [
    # Core Vulnerability Intelligence (6 edges)
    "has_weakness",              # Vulnerability → CWE
    "exploited_in_wild",         # Vulnerability → KEV entry
    "has_exploit",               # Vulnerability → exploit module/PoC
    "aliases",                   # Vulnerability ↔ Vulnerability (CVE/GHSA/OSV equivalence)
    "affects",                   # Vulnerability → component/CPE (with version ranges)
    "has_epss",                  # Vulnerability → EPSS history entry (time-series in epss_history collection)
    "has_epss_history",          # Vulnerability → EPSS history (alternate linkage)

    # Phase 3A: VulnCheck Intelligence (9 edges)
    "has_exploit_intelligence",      # Vulnerability → exploit_intelligence
    "exploited_by_ransomware",       # Vulnerability → ransomware_families
    "exploited_by_botnet",           # Vulnerability → botnets
    "exploited_by_threat_actor",     # Vulnerability → threat_groups
    "chain_includes_vuln",           # exploit_chains → Vulnerability
    "component_eol_status",          # Component → eol_products
    "ransomware_uses_technique",     # ransomware_families → attack_techniques
    "botnet_uses_technique",         # botnets → attack_techniques
    "vuln_triggers_requirement",     # Vulnerability → regulatory_requirements (auto-generated)

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

    # Compliance & Regulatory (5 edges)
    "maps_to_requirement",       # CWE → regulatory requirement
    "requirement_hierarchy",     # Requirement → parent requirement (Annex → Section → Paragraph)
    "cross_framework_mapping",   # Framework ↔ framework equivalence
    "opencre_links",             # OpenCRE → standards/requirements
    "violates_requirement",      # Vulnerability → regulatory requirement (CVE-to-regulation mapping)

    # Software Identity & Supply Chain (5 edges)
    "depends_on",                # Component → component (dependency DAG)
    "matched_by_cpe",            # Component (PURL) → CPE
    "same_as",                   # Component ↔ component (identity equivalence)
    "scored_by",                 # Component → Scorecard result
    "licensed_under",            # Component → license

    # Phase 5: Web UI & Multi-Tenant (3 edges)
    "user_belongs_to_org",       # User → Organization (membership)
    "org_owns_token",            # Organization → API Token (ownership)
    "user_created_token",        # User → API Token (creator tracking)

    # v2.2 Scanner Evidence Layer (9 edges)
    "component_has_vuln",            # Component → Vulnerability (CPE match / scanner direct)
    "finding_maps_to_weakness",      # ScanFinding → CWE (enables ATT&CK traversal)
    "finding_triggers_req",          # ScanFinding → Regulatory Requirement
    "detected_control_maps_to",      # DetectedControl → OSCAL/SCF control
    "control_in_component",          # DetectedControl → Component (scoping)
    "finding_in_component",          # ScanFinding → Component (scoping)
    "evidence_links_finding",        # EvidencePackage → ScanFinding (traceability)
    "evidence_for_project",          # EvidencePackage → Project (ownership)
    "project_uses_component",        # Project → Component (global component usage, Fix 1)

    # Compliance Violation Layer
    "finding_violates_control",      # ScanFinding → NIST 800-53 control (deterministic CVE→CWE→CAPEC→ATT&CK→Control chain)
]

# ========== Index Definitions ==========
# Indexes optimized for query performance with cacheEnabled
INDEXES = {
    "vulnerabilities": [
        {"type": "persistent", "fields": ["cve_id"], "unique": True, "sparse": True},
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
        {"type": "persistent", "fields": ["edb_id"], "unique": True},
        {"type": "persistent", "fields": ["source"]},
        {"type": "persistent", "fields": ["cve_ids[*]"]},
    ],
    "nuclei_templates": [
        {"type": "persistent", "fields": ["template_id"], "unique": True},
        {"type": "persistent", "fields": ["cve_ids[*]"]},
    ],
    "poc_repositories": [
        {"type": "persistent", "fields": ["repository_url"], "unique": True},
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
        {"type": "persistent", "fields": ["cpe"]},
        {"type": "persistent", "fields": ["package_manager"]},
        {"type": "persistent", "fields": ["firmware_layer"]},
    ],
    "cpe_entries": [
        {"type": "persistent", "fields": ["cpe_name"], "unique": True},
    ],

    # Phase 3A: VulnCheck Intelligence indexes
    "exploit_intelligence": [
        {"type": "persistent", "fields": ["cve_id"], "unique": True},
        {"type": "persistent", "fields": ["reported_exploited"]},
        {"type": "persistent", "fields": ["exploit_maturity"]},
    ],
    "ransomware_families": [
        {"type": "persistent", "fields": ["name"], "unique": True},
        {"type": "persistent", "fields": ["first_seen"]},
    ],
    "botnets": [
        {"type": "persistent", "fields": ["name"], "unique": True},
        {"type": "persistent", "fields": ["first_seen"]},
    ],
    "exploit_chains": [
        {"type": "persistent", "fields": ["name"], "unique": True},
        {"type": "persistent", "fields": ["cve_sequence[*]"]},
    ],
    "eol_products": [
        {"type": "persistent", "fields": ["product", "version"], "unique": True},
        {"type": "persistent", "fields": ["cpe"]},
        {"type": "persistent", "fields": ["support_status"]},
    ],
    "vulncheck_kev_entries": [
        {"type": "persistent", "fields": ["primary_cve_id"], "unique": True},
        {"type": "persistent", "fields": ["date_added"]},
        {"type": "persistent", "fields": ["vulncheck_reported_exploitation"]},
    ],

    # Compliance & Regulatory
    "regulatory_frameworks": [
        {"type": "persistent", "fields": ["short_name"], "unique": True},
    ],
    "regulatory_requirements": [
        {"type": "persistent", "fields": ["requirement_id"], "unique": True},
        {"type": "persistent", "fields": ["framework_id"]},
    ],
    "scf_controls": [
        {"type": "persistent", "fields": ["scf_id"], "unique": True},
    ],
    "oscal_controls": [
        {"type": "persistent", "fields": ["control_id"], "unique": True},
    ],

    # LLM Enrichments
    "llm_enrichments": [
        {"type": "persistent", "fields": ["entity_type"]},
        {"type": "persistent", "fields": ["cve_id"]},
        {"type": "persistent", "fields": ["cwe_id"]},
    ],

    # Customer API Keys
    "customer_api_keys": [
        {"type": "persistent", "fields": ["customer_id"]},
        {"type": "persistent", "fields": ["api_key_hash"], "unique": True},
    ],

    # Phase 5: Web UI & Multi-Tenant
    "organizations": [
        {"type": "persistent", "fields": ["slug"], "unique": True},
        {"type": "persistent", "fields": ["domain"]},
    ],
    "users": [
        {"type": "persistent", "fields": ["email"], "unique": True},
    ],
    "api_tokens": [
        {"type": "persistent", "fields": ["token_hash"], "unique": True},
        {"type": "persistent", "fields": ["organization_id"]},
        {"type": "persistent", "fields": ["expires_at"]},
    ],
    "audit_log": [
        {"type": "persistent", "fields": ["organization_id", "timestamp"]},
        {"type": "persistent", "fields": ["actor_id", "timestamp"]},
        {"type": "persistent", "fields": ["event_type"]},
    ],

    # Multi-Tenant Hierarchy
    "projects": [
        {"type": "persistent", "fields": ["customer_id"]},
        {"type": "persistent", "fields": ["project_id"], "unique": True},
        {"type": "persistent", "fields": ["customer_id", "active"]},
    ],
    "repositories": [
        {"type": "persistent", "fields": ["customer_id"]},
        {"type": "persistent", "fields": ["repository_id"], "unique": True},
        {"type": "persistent", "fields": ["customer_id", "project_id"]},
        {"type": "persistent", "fields": ["customer_id", "active"]},
    ],

    # Violates Requirement edge indexes
    "violates_requirement": [
        {"type": "persistent", "fields": ["framework"]},
        {"type": "persistent", "fields": ["severity"]},
    ],

    # ── v2.2 Scanner Evidence Layer ──────────────────────────────────────

    # Document collection indexes
    "scan_runs": [
        {"type": "persistent", "fields": ["scan_run_id"], "unique": True},
        {"type": "persistent", "fields": ["tenant_id", "project_id"]},
        {"type": "persistent", "fields": ["tenant_id", "started_at"]},
        {"type": "persistent", "fields": ["commit_sha"]},
        {"type": "persistent", "fields": ["status"]},
    ],
    "scan_findings": [
        {"type": "persistent", "fields": ["fingerprint"], "unique": True},
        {"type": "persistent", "fields": ["tenant_id", "project_id"]},
        {"type": "persistent", "fields": ["tenant_id", "scan_run_id"]},
        {"type": "persistent", "fields": ["tool"]},
        {"type": "persistent", "fields": ["finding_type"]},
        {"type": "persistent", "fields": ["severity_normalised"]},
        {"type": "persistent", "fields": ["triage_status"]},
        {"type": "persistent", "fields": ["cwe_ids[*]"]},
        {"type": "persistent", "fields": ["secret_type"]},
        {"type": "persistent", "fields": ["tenant_id", "project_id", "triage_status", "severity_normalised"]},
    ],
    "detected_controls": [
        {"type": "persistent", "fields": ["fingerprint"], "unique": True},
        {"type": "persistent", "fields": ["tenant_id", "project_id"]},
        {"type": "persistent", "fields": ["tenant_id", "scan_run_id"]},
        {"type": "persistent", "fields": ["control_type"]},
        {"type": "persistent", "fields": ["control_category"]},
        {"type": "persistent", "fields": ["oscal_control_id"]},
        {"type": "persistent", "fields": ["scf_control_id"]},
    ],
    "evidence_packages": [
        {"type": "persistent", "fields": ["package_id"], "unique": True},
        {"type": "persistent", "fields": ["tenant_id", "project_id"]},
        {"type": "persistent", "fields": ["tenant_id", "scan_run_id"]},
        {"type": "persistent", "fields": ["submission_ready"]},
        {"type": "persistent", "fields": ["retention_until"]},
        {"type": "persistent", "fields": ["target_regulation[*]"]},
    ],

    # Edge collection indexes
    "component_has_vuln": [
        {"type": "persistent", "fields": ["source"]},
        {"type": "persistent", "fields": ["vex_status"]},
        {"type": "persistent", "fields": ["is_kev_at_detection"]},
    ],
    "finding_maps_to_weakness": [
        {"type": "persistent", "fields": ["source"]},
    ],
    "finding_triggers_req": [
        {"type": "persistent", "fields": ["source"]},
    ],
    "detected_control_maps_to": [
        {"type": "persistent", "fields": ["confidence"]},
        {"type": "persistent", "fields": ["target_collection"]},
    ],
    "project_uses_component": [
        {"type": "persistent", "fields": ["tenant_id"]},
        {"type": "persistent", "fields": ["tenant_id", "project_id"]},
    ],
    "finding_violates_control": [
        {"type": "persistent", "fields": ["tenant_id", "scan_run_id"]},
        {"type": "persistent", "fields": ["framework"]},
        {"type": "persistent", "fields": ["control_id"]},
    ],
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

    Creates all 42 document collections and 49 edge collections.
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
                    sparse=index_def.get("sparse", False),
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
                sparse=index_def.get("sparse", False),
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
