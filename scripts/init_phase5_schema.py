#!/usr/bin/env python3
"""
Database Schema Initialization for Phase 5 Web UI

Creates new collections and edges for user authentication and organization management
while maintaining backward compatibility with existing customer_profiles.

Run: python scripts/init_phase5_schema.py
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from complira_graph.db import get_db
from arango.exceptions import CollectionCreateError, IndexCreateError
import structlog

logger = structlog.get_logger()


def init_phase5_schema():
    """Initialize Phase 5 database schema (users, organizations, api_tokens)."""

    db = get_db()
    logger.info("Initializing Phase 5 schema", database=db.name)

    # ========== NEW COLLECTIONS ==========

    # 1. Organizations collection
    try:
        organizations = db.create_collection("organizations")
        logger.info("Created collection: organizations")

        # Indexes
        organizations.add_hash_index(fields=["slug"], unique=True, name="idx_org_slug")
        organizations.add_hash_index(fields=["domain"], unique=False, name="idx_org_domain")
        logger.info("Created indexes on organizations")
    except CollectionCreateError:
        logger.info("Collection 'organizations' already exists, skipping")
        organizations = db.collection("organizations")

    # 2. Users collection
    try:
        users = db.create_collection("users")
        logger.info("Created collection: users")

        # Indexes
        users.add_hash_index(fields=["email"], unique=True, name="idx_user_email")
        users.add_hash_index(fields=["email_verification_token"], unique=False, sparse=True, name="idx_user_verification_token")
        users.add_hash_index(fields=["password_reset_token"], unique=False, sparse=True, name="idx_user_reset_token")
        logger.info("Created indexes on users")
    except CollectionCreateError:
        logger.info("Collection 'users' already exists, skipping")
        users = db.collection("users")

    # 3. API Tokens collection
    try:
        api_tokens = db.create_collection("api_tokens")
        logger.info("Created collection: api_tokens")

        # Indexes
        api_tokens.add_hash_index(fields=["token_hash"], unique=True, name="idx_token_hash")
        api_tokens.add_hash_index(fields=["organization_id"], unique=False, name="idx_token_org")
        api_tokens.add_skiplist_index(fields=["expires_at"], unique=False, name="idx_token_expiry")
        logger.info("Created indexes on api_tokens")
    except CollectionCreateError:
        logger.info("Collection 'api_tokens' already exists, skipping")
        api_tokens = db.collection("api_tokens")

    # 4. Audit Log collection
    try:
        audit_log = db.create_collection("audit_log")
        logger.info("Created collection: audit_log")

        # Indexes
        audit_log.add_hash_index(fields=["organization_id", "timestamp"], unique=False, name="idx_audit_org_time")
        audit_log.add_hash_index(fields=["actor_id", "timestamp"], unique=False, name="idx_audit_actor_time")
        audit_log.add_hash_index(fields=["event_type"], unique=False, name="idx_audit_event_type")
        logger.info("Created indexes on audit_log")
    except CollectionCreateError:
        logger.info("Collection 'audit_log' already exists, skipping")
        audit_log = db.collection("audit_log")

    # ========== EDGE COLLECTIONS ==========

    # 5. user_belongs_to_org edge
    try:
        user_belongs_to_org = db.create_collection("user_belongs_to_org", edge=True)
        logger.info("Created edge collection: user_belongs_to_org")

        # Indexes for efficient traversals
        user_belongs_to_org.add_hash_index(fields=["_from"], unique=False, name="idx_user_org_from")
        user_belongs_to_org.add_hash_index(fields=["_to"], unique=False, name="idx_user_org_to")
        logger.info("Created indexes on user_belongs_to_org")
    except CollectionCreateError:
        logger.info("Edge collection 'user_belongs_to_org' already exists, skipping")
        user_belongs_to_org = db.collection("user_belongs_to_org")

    # 6. org_owns_token edge
    try:
        org_owns_token = db.create_collection("org_owns_token", edge=True)
        logger.info("Created edge collection: org_owns_token")

        # Indexes
        org_owns_token.add_hash_index(fields=["_from"], unique=False, name="idx_org_token_from")
        org_owns_token.add_hash_index(fields=["_to"], unique=False, name="idx_org_token_to")
        logger.info("Created indexes on org_owns_token")
    except CollectionCreateError:
        logger.info("Edge collection 'org_owns_token' already exists, skipping")
        org_owns_token = db.collection("org_owns_token")

    # 7. user_created_token edge
    try:
        user_created_token = db.create_collection("user_created_token", edge=True)
        logger.info("Created edge collection: user_created_token")

        # Indexes
        user_created_token.add_hash_index(fields=["_from"], unique=False, name="idx_user_token_from")
        user_created_token.add_hash_index(fields=["_to"], unique=False, name="idx_user_token_to")
        logger.info("Created indexes on user_created_token")
    except CollectionCreateError:
        logger.info("Edge collection 'user_created_token' already exists, skipping")
        user_created_token = db.collection("user_created_token")

    # ========== VERIFY BACKWARD COMPATIBILITY ==========

    # Check that customer_profiles still exists (should not be modified)
    if db.has_collection("customer_profiles"):
        logger.info("✅ Verified: customer_profiles collection exists (backward compatible)")
    else:
        logger.warning("⚠️  customer_profiles collection not found - may need to run Phase 0-4 initialization first")

    # ========== SUMMARY ==========

    collections_created = [
        "organizations",
        "users",
        "api_tokens",
        "audit_log",
        "user_belongs_to_org (edge)",
        "org_owns_token (edge)",
        "user_created_token (edge)"
    ]

    logger.info(
        "Phase 5 schema initialization complete",
        collections=collections_created,
        total=len(collections_created)
    )

    print("\n✅ Phase 5 Schema Initialized Successfully")
    print("\nCollections created:")
    for coll in collections_created:
        print(f"  • {coll}")
    print("\n⚠️  Note: customer_profiles collection remains unchanged (backward compatible)")
    print("\nNext steps:")
    print("  1. Install backend dependencies: uv sync")
    print("  2. Run authentication endpoints: uvicorn src.api.main:app --reload")
    print("  3. Test with frontend: cd frontend && npm run dev\n")


if __name__ == "__main__":
    try:
        init_phase5_schema()
    except Exception as e:
        logger.error("Schema initialization failed", error=str(e), exc_info=True)
        sys.exit(1)
