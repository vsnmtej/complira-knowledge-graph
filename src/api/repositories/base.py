"""
Base repository protocol (DIP).

Defines generic repository interface that all repositories implement.
"""

from typing import Protocol, TypeVar, Generic, List, Optional, Dict, Any
from abc import ABC


T = TypeVar('T')


class IRepository(Protocol[T]):
    """
    Generic repository interface (DIP).

    All repositories implement this protocol for consistent CRUD operations.
    Services depend on this abstraction, not concrete implementations.

    Type parameter T represents the entity type (e.g., Vulnerability, Component).
    """

    def get(self, key: str) -> Optional[T]:
        """
        Get entity by key.

        Args:
            key: Entity _key

        Returns:
            Entity object or None if not found
        """
        ...

    def list(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[T]:
        """
        List entities with optional filtering.

        Args:
            filters: Optional filter dict (field: value)
            limit: Maximum number of entities to return
            offset: Number of entities to skip

        Returns:
            list: Entity objects
        """
        ...

    def create(self, entity: Dict[str, Any]) -> T:
        """
        Create new entity.

        Args:
            entity: Entity data

        Returns:
            Created entity object with _key and _id
        """
        ...

    def update(self, key: str, entity: Dict[str, Any]) -> T:
        """
        Update existing entity.

        Args:
            key: Entity _key
            entity: Updated entity data

        Returns:
            Updated entity object
        """
        ...

    def delete(self, key: str) -> bool:
        """
        Delete entity by key.

        Args:
            key: Entity _key

        Returns:
            True if deleted, False if not found
        """
        ...

    def exists(self, key: str) -> bool:
        """
        Check if entity exists.

        Args:
            key: Entity _key

        Returns:
            True if exists, False otherwise
        """
        ...


class BaseRepository(ABC, Generic[T]):
    """
    Base repository implementation (DRY).

    Provides common database access patterns.
    Concrete repositories can extend this for shared logic.
    """

    def __init__(self, db, collection_name: str):
        """
        Initialize repository.

        Args:
            db: Database instance
            collection_name: Collection name for this entity type
        """
        self.db = db
        self.collection_name = collection_name
        self.collection = db.collection(collection_name)

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get entity by key."""
        try:
            return self.collection.get(key)
        except Exception:
            return None

    def list(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List entities with optional filtering."""
        query = f"FOR doc IN {self.collection_name}"

        bind_vars = {}

        if filters:
            filter_clauses = []
            for i, (field, value) in enumerate(filters.items()):
                param_name = f"filter_{i}"
                filter_clauses.append(f"FILTER doc.{field} == @{param_name}")
                bind_vars[param_name] = value

            query += "\n  " + "\n  ".join(filter_clauses)

        query += f"\n  LIMIT @offset, @limit\n  RETURN doc"

        bind_vars["offset"] = offset
        bind_vars["limit"] = limit

        cursor = self.db.aql_execute(query, bind_vars=bind_vars)
        return list(cursor)

    def create(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """Create new entity."""
        result = self.collection.insert(entity, return_new=True)
        return result['new']

    def update(self, key: str, entity: Dict[str, Any]) -> Dict[str, Any]:
        """Update existing entity."""
        result = self.collection.update({'_key': key, **entity}, return_new=True)
        return result['new']

    def delete(self, key: str) -> bool:
        """Delete entity by key."""
        try:
            self.collection.delete(key)
            return True
        except Exception:
            return False

    def exists(self, key: str) -> bool:
        """Check if entity exists."""
        return self.collection.has(key)
