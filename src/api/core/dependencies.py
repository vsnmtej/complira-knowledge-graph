"""
FastAPI dependency injection functions.

Provides reusable dependencies for:
- Database connections (reference and customer)
- Cache service
- Current customer authentication
- Service instances

All dependencies follow FastAPI Depends pattern for:
- Automatic injection
- Easy testing (mocking)
- Clear dependency graphs
"""

from typing import Optional
from fastapi import Depends
from arango.database import StandardDatabase
import structlog

from api.core.config import get_cloud_settings, CloudSettings
from api.core.cache import ICacheService, RedisCacheService
from api.core.database import get_reference_db, get_customer_db
from api.core.security import get_current_customer, Customer

logger = structlog.get_logger()


# ========== Configuration Dependencies ==========


def get_settings() -> CloudSettings:
    """
    Get cloud settings.

    Returns:
        CloudSettings: Application settings

    Usage:
        @app.get("/config")
        def get_config(settings: CloudSettings = Depends(get_settings)):
            return {"debug": settings.API_DEBUG}
    """
    return get_cloud_settings()


# ========== Database Dependencies ==========


def get_reference_database() -> StandardDatabase:
    """
    Get reference database connection.

    Reference database contains shared read-only data:
    - CVE/CWE/CAPEC/ATT&CK
    - NIST 800-53 controls
    - Customer profiles

    Returns:
        StandardDatabase: Reference database instance

    Usage:
        @app.get("/v1/cve/{cve_id}")
        def get_cve(
            cve_id: str,
            db: StandardDatabase = Depends(get_reference_database)
        ):
            # Query reference database
            ...
    """
    return get_reference_db()


def get_customer_database(
    customer: Customer = Depends(get_current_customer),
) -> StandardDatabase:
    """
    Get customer database connection.

    Customer database contains isolated customer data:
    - Scan sessions
    - Scan findings
    - Customer components

    Args:
        customer: Authenticated customer (injected by FastAPI)

    Returns:
        StandardDatabase: Customer database instance

    Usage:
        @app.get("/v1/scans")
        def list_scans(
            db: StandardDatabase = Depends(get_customer_database)
        ):
            # Query customer database (automatically scoped)
            ...
    """
    return get_customer_db(customer.id)


# ========== Cache Dependencies ==========


def get_cache_service() -> ICacheService:
    """
    Get cache service instance.

    Returns:
        ICacheService: Redis cache service

    Usage:
        @app.get("/v1/cve/{cve_id}")
        def get_cve(
            cve_id: str,
            cache: ICacheService = Depends(get_cache_service)
        ):
            # Check cache first
            cached = cache.get(f"cve:{cve_id}")
            if cached:
                return cached
            ...
    """
    return RedisCacheService()


# ========== Authentication Dependencies ==========


def get_customer(
    customer: Customer = Depends(get_current_customer),
) -> Customer:
    """
    Get authenticated customer.

    This is an alias for get_current_customer for consistency
    with other dependency naming.

    Args:
        customer: Authenticated customer (injected by FastAPI)

    Returns:
        Customer: Customer object

    Usage:
        @app.get("/v1/profile")
        def get_profile(customer: Customer = Depends(get_customer)):
            return {
                "id": customer.id,
                "name": customer.name,
                "tier": customer.tier
            }
    """
    return customer


# ========== Service Dependencies ==========
# These will be implemented as services are created


def get_scan_service():
    """
    Get evidence ingestion service (v2.2).

    Returns:
        EvidenceIngestionService: Service instance with reference DB injected.
    """
    from complira_graph.ingestion.service import EvidenceIngestionService

    return EvidenceIngestionService(db=get_reference_db())


def get_blast_radius_service():
    """
    Get blast radius service.

    Returns:
        BlastRadiusService: Service instance with injected dependencies
    """
    # Import here to avoid circular dependency
    from api.services.blast_radius import BlastRadiusService

    return BlastRadiusService(
        db=get_reference_db(),
        cache=RedisCacheService(),
    )


# ========== Common Dependencies ==========


def get_db_and_cache() -> tuple[StandardDatabase, ICacheService]:
    """
    Get both database and cache.

    Convenience dependency for services that need both.

    Returns:
        tuple: (database, cache_service)

    Usage:
        @app.get("/v1/data")
        def get_data(
            deps: tuple = Depends(get_db_and_cache)
        ):
            db, cache = deps
            ...
    """
    return (get_reference_db(), RedisCacheService())


def get_customer_db_and_cache(
    customer: Customer = Depends(get_current_customer),
) -> tuple[StandardDatabase, ICacheService, Customer]:
    """
    Get customer database, cache, and customer object.

    Convenience dependency for customer-scoped endpoints.

    Args:
        customer: Authenticated customer (injected by FastAPI)

    Returns:
        tuple: (customer_database, cache_service, customer)

    Usage:
        @app.get("/v1/scans")
        def list_scans(
            deps: tuple = Depends(get_customer_db_and_cache)
        ):
            db, cache, customer = deps
            # All customer-scoped dependencies ready
            ...
    """
    return (
        get_customer_db(customer.id),
        RedisCacheService(),
        customer,
    )
