"""
Initialize Phase 5 database collections.

Creates collections required for Web UI:
- organizations
- users
- api_tokens
- audit_log

Usage:
    python scripts/init_phase5_collections.py
"""

import sys
sys.path.insert(0, "/Users/venkatapydialli/Documents/cybersecurity-compliance-app")

from complira_graph.db import get_db
import structlog

logger = structlog.get_logger()


def init_phase5_collections():
    """Create Phase 5 collections if they don't exist."""

    db = get_db()

    # Collection definitions
    collections = [
        {
            "name": "organizations",
            "description": "Organization profiles (multi-tenant)",
            "indices": [
                {"fields": ["slug"], "unique": True},
                {"fields": ["domain"], "unique": False},
            ]
        },
        {
            "name": "users",
            "description": "User accounts",
            "indices": [
                {"fields": ["email"], "unique": True},
                {"fields": ["organization_id"], "unique": False},
            ]
        },
        {
            "name": "api_tokens",
            "description": "API tokens for programmatic access",
            "indices": [
                {"fields": ["organization_id"], "unique": False},
                {"fields": ["token_prefix"], "unique": False},
                {"fields": ["revoked"], "unique": False},
                {"fields": ["expires_at"], "unique": False},
            ]
        },
        {
            "name": "audit_log",
            "description": "Audit log for all token operations",
            "indices": [
                {"fields": ["organization_id"], "unique": False},
                {"fields": ["action"], "unique": False},
                {"fields": ["timestamp"], "unique": False},
            ]
        },
    ]

    # Create collections
    for coll_def in collections:
        name = coll_def["name"]

        if db.has_collection(name):
            logger.info("collection_exists", collection=name)
        else:
            # Create collection
            collection = db.create_collection(name)
            logger.info("collection_created", collection=name)

            # Create indices
            for index_def in coll_def.get("indices", []):
                collection.add_hash_index(
                    fields=index_def["fields"],
                    unique=index_def["unique"]
                )
                logger.info(
                    "index_created",
                    collection=name,
                    fields=index_def["fields"],
                    unique=index_def["unique"]
                )

    logger.info("phase5_collections_initialized", collections=[c["name"] for c in collections])

    # Print summary
    print("\n" + "="*60)
    print("Phase 5 Collections Initialized")
    print("="*60)

    for coll_def in collections:
        name = coll_def["name"]
        count = db.collection(name).count()
        print(f"  {name:20} - {count:6} documents")

    print("="*60 + "\n")

    print("✅ Database ready for Phase 5 Web UI")
    print("\nNext steps:")
    print("  1. Start backend API: .venv/bin/uvicorn src.api.main:app --reload")
    print("  2. Start frontend: cd frontend && npm run dev")
    print("  3. Navigate to http://localhost:3001/signup")


if __name__ == "__main__":
    init_phase5_collections()
