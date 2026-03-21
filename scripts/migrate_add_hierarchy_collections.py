#!/usr/bin/env python3
"""
Migration script to add projects and repositories collections to existing customer databases.

This script adds the multi-tenant hierarchy collections and indexes to customer databases
that were created before this feature was implemented.
"""

from api.core.database import get_customer_db, get_arango_client
from api.core.config import get_cloud_settings
import structlog

logger = structlog.get_logger()


def migrate_customer_database(customer_id: str):
    """Add projects and repositories collections to a customer database."""
    try:
        db = get_customer_db(customer_id)

        print(f"\n{'='*60}")
        print(f"Migrating customer database: {customer_id}")
        print(f"{'='*60}\n")

        # Create projects collection
        if not db.has_collection('projects'):
            db.create_collection('projects', edge=False)
            print('✅ Created projects collection')
        else:
            print('ℹ️  projects collection already exists')

        # Create repositories collection
        if not db.has_collection('repositories'):
            db.create_collection('repositories', edge=False)
            print('✅ Created repositories collection')
        else:
            print('ℹ️  repositories collection already exists')

        # Create indexes for projects
        print('\nCreating indexes for projects...')
        projects = db.collection('projects')
        try:
            projects.add_persistent_index(fields=['customer_id'], unique=False)
            projects.add_persistent_index(fields=['customer_id', 'project_id'], unique=True)
            projects.add_persistent_index(fields=['customer_id', 'active'], unique=False)
            print('✅ Created indexes for projects')
        except Exception as e:
            print(f'⚠️  Index creation (may already exist): {e}')

        # Create indexes for repositories
        print('\nCreating indexes for repositories...')
        repositories = db.collection('repositories')
        try:
            repositories.add_persistent_index(fields=['customer_id'], unique=False)
            repositories.add_persistent_index(fields=['customer_id', 'repository_id'], unique=True)
            repositories.add_persistent_index(fields=['customer_id', 'project_id'], unique=False)
            repositories.add_persistent_index(fields=['customer_id', 'active'], unique=False)
            print('✅ Created indexes for repositories')
        except Exception as e:
            print(f'⚠️  Index creation (may already exist): {e}')

        # Add hierarchy indexes to scan_sessions
        if db.has_collection('scan_sessions'):
            print('\nCreating hierarchy indexes for scan_sessions...')
            scan_sessions = db.collection('scan_sessions')
            try:
                scan_sessions.add_persistent_index(fields=['customer_id', 'project_id'], unique=False)
                scan_sessions.add_persistent_index(fields=['customer_id', 'repository_id'], unique=False)
                print('✅ Created hierarchy indexes for scan_sessions')
            except Exception as e:
                print(f'⚠️  Index creation (may already exist): {e}')

        print(f'\n✅ Migration completed successfully for {customer_id}!')
        return True

    except Exception as e:
        logger.error(f"Migration failed for {customer_id}: {e}")
        print(f'\n❌ Migration failed: {e}')
        return False


def main():
    """Run migration for demo_customer."""
    print("Multi-Tenant Hierarchy Collections Migration")
    print("=" * 60)

    # Migrate demo_customer
    success = migrate_customer_database('demo_customer')

    if success:
        print("\n" + "="*60)
        print("✅ All migrations completed successfully!")
        print("="*60)
        return 0
    else:
        print("\n" + "="*60)
        print("❌ Migration failed!")
        print("="*60)
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
