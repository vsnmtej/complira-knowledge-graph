"""
VEX document repository.

Handles direct database operations for VEX documents.
"""

from typing import Optional, Dict, Any
from api.repositories.base import BaseRepository


class VEXRepository(BaseRepository):
    """Repository for VEX document CRUD operations."""

    def __init__(self, db):
        super().__init__(db, "vex_documents")

    def insert_vex(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a new VEX document."""
        return self.collection.insert(document)

    def update_vex(self, vex_id: str, customer_id: str, update_data: Dict[str, Any]) -> None:
        """Update a VEX document by key and customer_id."""
        self.collection.update(
            {"_key": vex_id, "customer_id": customer_id},
            update_data,
        )

    def delete_vex(self, vex_id: str, customer_id: str) -> None:
        """Delete a VEX document by key and customer_id."""
        self.collection.delete({"_key": vex_id, "customer_id": customer_id})
