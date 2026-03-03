"""
Component repository.

Handles database access for customer_components collection (customer database).

Components represent customer's software inventory from SBOMs.
"""

from typing import List, Dict, Any, Optional
from api.repositories.base import BaseRepository
import structlog

logger = structlog.get_logger()


class ComponentRepository(BaseRepository):
    """
    Repository for customer_components collection (customer database).

    Components collection stores customer's software inventory:
    - customer_id
    - purl (Package URL - primary key)
    - name, version, group
    - type (library, application, framework, etc.)
    - licenses
    - vulnerabilities (via edges)
    """

    def __init__(self, db):
        """
        Initialize component repository.

        Args:
            db: Database instance (customer database)
        """
        super().__init__(db, "customer_components")

    def create_component(
        self,
        customer_id: str,
        purl: str,
        name: str,
        version: str,
        component_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create new component.

        Args:
            customer_id: Customer identifier
            purl: Package URL (e.g., "pkg:npm/express@4.17.1")
            name: Component name
            version: Component version
            component_type: Component type (library, application, etc.)
            metadata: Optional additional metadata

        Returns:
            dict: Created component with _key
        """
        from datetime import datetime

        component = {
            "customer_id": customer_id,
            "purl": purl,
            "name": name,
            "version": version,
            "type": component_type,
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        # Use PURL as _key for idempotency
        # Convert PURL to safe key format (replace special chars)
        safe_key = purl.replace("/", "_").replace(":", "_").replace("@", "_")
        component["_key"] = safe_key

        try:
            result = self.create(component)
            logger.info(
                "Component created",
                component_key=result.get("_key"),
                purl=purl,
            )
            return result

        except Exception as e:
            # Component may already exist (duplicate PURL)
            logger.debug(
                "Component creation failed (may already exist)",
                purl=purl,
                error=str(e),
            )
            # Return existing component
            return self.get_by_purl(customer_id, purl)

    def bulk_create_components(
        self,
        components: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Bulk create components.

        Args:
            components: List of component dictionaries

        Returns:
            list: Created components with _key
        """
        from datetime import datetime

        # Add timestamps and safe keys
        for component in components:
            if "created_at" not in component:
                component["created_at"] = datetime.utcnow().isoformat()
            if "updated_at" not in component:
                component["updated_at"] = datetime.utcnow().isoformat()

            # Generate safe key from PURL
            if "purl" in component and "_key" not in component:
                purl = component["purl"]
                safe_key = purl.replace("/", "_").replace(":", "_").replace("@", "_")
                component["_key"] = safe_key

        # Use bulk insert with overwrite mode
        try:
            results = self.collection.insert_many(
                components,
                overwrite_mode="ignore",  # Ignore duplicates
                return_new=True,
            )

            created_count = len([r for r in results if 'new' in r])

            logger.info(
                "Bulk created components",
                total=len(components),
                created=created_count,
                skipped=len(components) - created_count,
            )

            return [r.get('new', {}) for r in results if 'new' in r]

        except Exception as e:
            logger.error(
                "Bulk component creation failed",
                error=str(e),
            )
            raise

    def get_by_purl(
        self,
        customer_id: str,
        purl: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get component by PURL.

        Args:
            customer_id: Customer identifier
            purl: Package URL

        Returns:
            dict: Component document or None if not found
        """
        query = """
        FOR component IN customer_components
            FILTER component.customer_id == @customer_id
            FILTER component.purl == @purl
            LIMIT 1
            RETURN component
        """

        cursor = self.db.aql_execute(
            query,
            bind_vars={
                "customer_id": customer_id,
                "purl": purl,
            }
        )

        result = list(cursor)
        return result[0] if result else None

    def list_customer_components(
        self,
        customer_id: str,
        limit: int = 1000,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        List all components for a customer.

        Args:
            customer_id: Customer identifier
            limit: Maximum number of components
            offset: Number of components to skip

        Returns:
            list: Component documents sorted by name
        """
        query = """
        FOR component IN customer_components
            FILTER component.customer_id == @customer_id
            SORT component.name ASC
            LIMIT @offset, @limit
            RETURN component
        """

        cursor = self.db.aql_execute(
            query,
            bind_vars={
                "customer_id": customer_id,
                "limit": limit,
                "offset": offset,
            }
        )

        return list(cursor)

    def get_components_with_vulnerabilities(
        self,
        customer_id: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get components that have known vulnerabilities.

        Args:
            customer_id: Customer identifier
            limit: Maximum number of components

        Returns:
            list: Components with vulnerability counts
        """
        query = """
        FOR component IN customer_components
            FILTER component.customer_id == @customer_id
            LET vuln_count = LENGTH(
                FOR finding IN 1..1 OUTBOUND component component_to_finding
                    RETURN 1
            )
            FILTER vuln_count > 0
            SORT vuln_count DESC
            LIMIT @limit
            RETURN {
                component: component,
                vulnerability_count: vuln_count
            }
        """

        cursor = self.db.aql_execute(
            query,
            bind_vars={
                "customer_id": customer_id,
                "limit": limit,
            }
        )

        return list(cursor)

    def count_customer_components(self, customer_id: str) -> int:
        """
        Count total components for a customer.

        Args:
            customer_id: Customer identifier

        Returns:
            int: Number of components
        """
        query = """
        FOR component IN customer_components
            FILTER component.customer_id == @customer_id
            COLLECT WITH COUNT INTO count
            RETURN count
        """

        cursor = self.db.aql_execute(
            query,
            bind_vars={"customer_id": customer_id}
        )

        result = list(cursor)
        return result[0] if result else 0

    def delete_customer_components(self, customer_id: str) -> int:
        """
        Delete all components for a customer.

        Args:
            customer_id: Customer identifier

        Returns:
            int: Number of components deleted
        """
        query = """
        FOR component IN customer_components
            FILTER component.customer_id == @customer_id
            REMOVE component IN customer_components
            RETURN 1
        """

        cursor = self.db.aql_execute(
            query,
            bind_vars={"customer_id": customer_id}
        )

        deleted = len(list(cursor))

        logger.info(
            "Deleted customer components",
            customer_id=customer_id,
            deleted_count=deleted,
        )

        return deleted
