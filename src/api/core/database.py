"""
Multi-tenant database routing.

Provides:
- IDatabase protocol (DIP)
- Reference database access (shared, read-only)
- Customer database access (isolated per customer)
- Automatic database provisioning
- Cross-database query support
"""

from typing import Protocol, Optional
from arango import ArangoClient
from arango.database import StandardDatabase
from arango.exceptions import DatabaseCreateError, CollectionCreateError
import structlog
import redis
import time

from api.core.config import get_cloud_settings
from complira_graph.db import (
    DOCUMENT_COLLECTIONS,
    EDGE_COLLECTIONS,
    INDEXES,
)

logger = structlog.get_logger()


class IDatabase(Protocol):
    """
    Database abstraction (DIP).

    Allows services to depend on database interface, not concrete implementation.
    """

    def aql_execute(self, query: str, bind_vars: dict = None):
        """Execute AQL query."""
        ...

    def has_collection(self, name: str) -> bool:
        """Check if collection exists."""
        ...

    def collection(self, name: str):
        """Get collection."""
        ...


# Global database connections (cached)
_reference_db: Optional[StandardDatabase] = None
_customer_db_cache: dict = {}  # customer_id -> StandardDatabase
_arango_client: Optional[ArangoClient] = None


def get_arango_client() -> ArangoClient:
    """
    Get or create ArangoDB client.

    Returns:
        ArangoClient: Shared client instance with connection pooling
    """
    global _arango_client

    if _arango_client is not None:
        return _arango_client

    settings = get_cloud_settings()

    _arango_client = ArangoClient(hosts=settings.ARANGO_URL)

    logger.info("ArangoDB client initialized", url=settings.ARANGO_URL)

    return _arango_client


def get_reference_db() -> StandardDatabase:
    """
    Get reference database connection (shared, read-only).

    Reference database contains:
    - CVE data (NVD, OSV, GHSA)
    - CWE hierarchy
    - MITRE ATT&CK
    - NIST 800-53 controls
    - Other reference data sources

    Returns:
        StandardDatabase: Reference database instance

    Raises:
        ConnectionError: If unable to connect
    """
    global _reference_db

    if _reference_db is not None:
        return _reference_db

    settings = get_cloud_settings()
    client = get_arango_client()

    try:
        # Connect to system database to check if reference DB exists
        sys_db = client.db(
            "_system",
            username=settings.ARANGO_USERNAME,
            password=settings.ARANGO_PASSWORD,
        )

        # Create reference database if it doesn't exist
        if not sys_db.has_database(settings.ARANGO_REFERENCE_DATABASE):
            logger.info(
                "Creating reference database",
                database=settings.ARANGO_REFERENCE_DATABASE,
            )
            sys_db.create_database(settings.ARANGO_REFERENCE_DATABASE)

            # Initialize schema
            ref_db = client.db(
                settings.ARANGO_REFERENCE_DATABASE,
                username=settings.ARANGO_USERNAME,
                password=settings.ARANGO_PASSWORD,
            )
            _init_database_schema(ref_db)

        # Connect to reference database
        _reference_db = client.db(
            settings.ARANGO_REFERENCE_DATABASE,
            username=settings.ARANGO_USERNAME,
            password=settings.ARANGO_PASSWORD,
        )

        logger.info(
            "Connected to reference database",
            database=settings.ARANGO_REFERENCE_DATABASE,
        )

        return _reference_db

    except Exception as e:
        logger.error(
            "Failed to connect to reference database",
            database=settings.ARANGO_REFERENCE_DATABASE,
            error=str(e),
        )
        raise ConnectionError(f"Failed to connect to reference database: {e}")


def get_customer_db(customer_id: str) -> StandardDatabase:
    """
    Get customer database connection (isolated per customer).

    Customer database contains:
    - Scan sessions
    - Scan findings
    - Customer components (SBOMs)
    - Customer-specific mappings

    If database doesn't exist and AUTO_CREATE_CUSTOMER_DB is True,
    creates database automatically with proper schema.

    Args:
        customer_id: Customer identifier

    Returns:
        StandardDatabase: Customer database instance

    Raises:
        ConnectionError: If unable to connect or create database
    """
    global _customer_db_cache

    # Check cache first
    if customer_id in _customer_db_cache:
        return _customer_db_cache[customer_id]

    settings = get_cloud_settings()
    client = get_arango_client()

    database_name = f"{settings.ARANGO_CUSTOMER_DATABASE_PREFIX}{customer_id}"

    try:
        # Connect to system database
        sys_db = client.db(
            "_system",
            username=settings.ARANGO_USERNAME,
            password=settings.ARANGO_PASSWORD,
        )

        # Create customer database if it doesn't exist
        if not sys_db.has_database(database_name):
            if not settings.AUTO_CREATE_CUSTOMER_DB:
                raise ConnectionError(
                    f"Customer database does not exist and auto-creation is disabled: {database_name}"
                )

            logger.info(
                "Creating customer database",
                customer_id=customer_id,
                database=database_name,
            )

            # Use Redis lock to prevent concurrent creation
            created = _create_customer_database_with_lock(
                sys_db=sys_db,
                customer_id=customer_id,
                database_name=database_name,
            )

            if not created:
                # Another process created it, continue
                logger.debug(
                    "Customer database created by another process",
                    customer_id=customer_id,
                )

        # Connect to customer database
        customer_db = client.db(
            database_name,
            username=settings.ARANGO_USERNAME,
            password=settings.ARANGO_PASSWORD,
        )

        # Cache connection
        _customer_db_cache[customer_id] = customer_db

        logger.info(
            "Connected to customer database",
            customer_id=customer_id,
            database=database_name,
        )

        return customer_db

    except Exception as e:
        logger.error(
            "Failed to get customer database",
            customer_id=customer_id,
            database=database_name,
            error=str(e),
        )
        raise ConnectionError(f"Failed to get customer database: {e}")


def _create_customer_database_with_lock(
    sys_db: StandardDatabase,
    customer_id: str,
    database_name: str,
) -> bool:
    """
    Create customer database with Redis distributed lock.

    Prevents concurrent creation by multiple API processes.

    Args:
        sys_db: System database instance
        customer_id: Customer identifier
        database_name: Database name to create

    Returns:
        bool: True if this process created the database, False if already exists
    """
    settings = get_cloud_settings()

    # Try to acquire Redis lock
    try:
        redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            db=settings.REDIS_DB,
        )

        lock_key = f"db_creation_lock:{customer_id}"
        lock_acquired = redis_client.set(
            lock_key,
            "locked",
            nx=True,  # Only set if not exists
            ex=10,  # 10-second TTL (longer than database creation)
        )

        if not lock_acquired:
            # Another process is creating the database, wait
            logger.debug(
                "Waiting for database creation lock",
                customer_id=customer_id,
            )

            for _ in range(10):  # Wait up to 10 seconds
                time.sleep(1)
                if sys_db.has_database(database_name):
                    logger.debug(
                        "Database created by another process",
                        customer_id=customer_id,
                    )
                    return False

            # Timeout - proceed anyway (lock may have expired)
            logger.warning(
                "Database creation lock timeout, proceeding",
                customer_id=customer_id,
            )

        # Double-check database doesn't exist (race condition protection)
        if sys_db.has_database(database_name):
            logger.debug(
                "Database already exists (created by another process)",
                customer_id=customer_id,
            )
            redis_client.delete(lock_key)
            return False

        # Create database
        try:
            sys_db.create_database(database_name)

            # Initialize schema
            client = get_arango_client()
            customer_db = client.db(
                database_name,
                username=settings.ARANGO_USERNAME,
                password=settings.ARANGO_PASSWORD,
            )
            _init_database_schema(customer_db)

            logger.info(
                "Customer database created successfully",
                customer_id=customer_id,
                database=database_name,
            )

            # Release lock
            redis_client.delete(lock_key)

            return True

        except DatabaseCreateError as e:
            logger.warning(
                "Database creation failed (may already exist)",
                customer_id=customer_id,
                error=str(e),
            )
            redis_client.delete(lock_key)
            return False

    except redis.RedisError as e:
        # Redis unavailable - proceed without lock (risk of duplicate creation)
        logger.warning(
            "Redis lock unavailable, creating database without lock",
            customer_id=customer_id,
            error=str(e),
        )

        if not sys_db.has_database(database_name):
            try:
                sys_db.create_database(database_name)

                # Initialize schema
                client = get_arango_client()
                customer_db = client.db(
                    database_name,
                    username=settings.ARANGO_USERNAME,
                    password=settings.ARANGO_PASSWORD,
                )
                _init_database_schema(customer_db)

                return True

            except DatabaseCreateError:
                return False

        return False


def _init_database_schema(db: StandardDatabase) -> None:
    """
    Initialize database schema (collections + indexes).

    Args:
        db: Database instance to initialize
    """
    logger.info("Initializing database schema")

    # Create document collections
    for collection_name in DOCUMENT_COLLECTIONS:
        if not db.has_collection(collection_name):
            try:
                db.create_collection(collection_name, edge=False)
                logger.debug("Created collection", collection=collection_name)
            except CollectionCreateError as e:
                logger.warning(
                    "Collection creation failed",
                    collection=collection_name,
                    error=str(e),
                )

    # Create edge collections
    for edge_name in EDGE_COLLECTIONS:
        if not db.has_collection(edge_name):
            try:
                db.create_collection(edge_name, edge=True)
                logger.debug("Created edge collection", edge=edge_name)
            except CollectionCreateError as e:
                logger.warning(
                    "Edge collection creation failed",
                    edge=edge_name,
                    error=str(e),
                )

    # Create indexes
    for collection_name, indexes in INDEXES.items():
        if not db.has_collection(collection_name):
            continue

        collection = db.collection(collection_name)

        for index_def in indexes:
            try:
                collection.add_persistent_index(
                    fields=index_def["fields"],
                    unique=index_def.get("unique", False),
                    sparse=False,
                )
                logger.debug(
                    "Created index",
                    collection=collection_name,
                    fields=index_def["fields"],
                )
            except Exception as e:
                logger.warning(
                    "Index creation failed",
                    collection=collection_name,
                    fields=index_def["fields"],
                    error=str(e),
                )

    # Create customer-specific collections
    _create_customer_collections(db)

    logger.info("Database schema initialized")


def _create_customer_collections(db: StandardDatabase) -> None:
    """
    Create customer-specific collections.

    These collections are unique to customer databases:
    - scan_sessions: Scan metadata
    - scan_findings: Individual findings from scans
    - customer_components: Customer's software inventory

    Args:
        db: Customer database instance
    """
    customer_collections = {
        "scan_sessions": False,  # Document collection
        "scan_findings": False,  # Document collection
        "customer_components": False,  # Document collection
        "finding_to_cve": True,  # Edge: finding → vulnerability
        "component_to_finding": True,  # Edge: component → finding
    }

    for collection_name, is_edge in customer_collections.items():
        if not db.has_collection(collection_name):
            try:
                db.create_collection(collection_name, edge=is_edge)
                logger.debug(
                    "Created customer collection",
                    collection=collection_name,
                    edge=is_edge,
                )
            except CollectionCreateError as e:
                logger.warning(
                    "Customer collection creation failed",
                    collection=collection_name,
                    error=str(e),
                )

    # Create customer-specific indexes
    customer_indexes = {
        "scan_sessions": [
            {"fields": ["customer_id"], "unique": False},
            {"fields": ["customer_id", "created_at"], "unique": False},
        ],
        "scan_findings": [
            {"fields": ["customer_id"], "unique": False},
            {"fields": ["customer_id", "scan_session_id"], "unique": False},
            {"fields": ["customer_id", "cve_id"], "unique": False},
        ],
        "customer_components": [
            {"fields": ["customer_id"], "unique": False},
            {"fields": ["customer_id", "purl"], "unique": True},
        ],
    }

    for collection_name, indexes in customer_indexes.items():
        if not db.has_collection(collection_name):
            continue

        collection = db.collection(collection_name)

        for index_def in indexes:
            try:
                collection.add_persistent_index(
                    fields=index_def["fields"],
                    unique=index_def.get("unique", False),
                    sparse=False,
                )
                logger.debug(
                    "Created customer index",
                    collection=collection_name,
                    fields=index_def["fields"],
                )
            except Exception as e:
                logger.warning(
                    "Customer index creation failed",
                    collection=collection_name,
                    fields=index_def["fields"],
                    error=str(e),
                )


def get_database() -> StandardDatabase:
    """
    Get default database (reference database).

    This is a convenience function for code that needs
    access to reference data without customer context.

    Returns:
        StandardDatabase: Reference database instance
    """
    return get_reference_db()
