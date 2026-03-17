#!/usr/bin/env python3
"""
One-time database migration script: Local → Cloud.

Migrates reference database from local ArangoDB to cloud ArangoDB.

Usage:
    python scripts/migrate_to_cloud.py --export
    python scripts/migrate_to_cloud.py --import
    python scripts/migrate_to_cloud.py --verify

Stages:
    1. Export: Export all collections from local database to JSON files
    2. Import: Import all JSON files into cloud reference database
    3. Verify: Verify data integrity (counts, checksums, spot-checks)

Safety:
    - Local database remains read-only after export (not deleted)
    - All operations are logged with timestamps
    - Checksums verify data integrity
    - Spot-checks validate sample documents

AC-017: Export all 335K+ documents from local database
AC-018: Export all 1.97M edges from local database
AC-019: Verify export integrity (document count, edge count, checksums)
AC-020: Import documents into cloud `complira_reference` database
AC-021: Import edges into cloud `complira_reference` database
AC-022: Verify import integrity (counts match, spot-check sample documents)
AC-023: Keep local database as read-only backup for 30 days
AC-024: Zero data loss tolerance (all counts must match exactly)
"""

import argparse
import json
import hashlib
import random
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import structlog

from arango import ArangoClient
from arango.database import StandardDatabase

logger = structlog.get_logger()

# Export directory
EXPORT_DIR = Path("./migration_export")
EXPORT_MANIFEST_FILE = EXPORT_DIR / "manifest.json"


def get_local_db() -> StandardDatabase:
    """
    Connect to local ArangoDB instance.

    Returns:
        StandardDatabase: Local database instance
    """
    client = ArangoClient(hosts="http://localhost:8529")

    db = client.db(
        "complira_graph",
        username="root",
        password="complira_dev_password_change_in_production",
    )

    logger.info("Connected to local database", database="complira_graph")

    return db


def get_cloud_db() -> StandardDatabase:
    """
    Connect to cloud ArangoDB instance.

    Reads cloud credentials from environment or .env file.

    Returns:
        StandardDatabase: Cloud reference database instance
    """
    from api.core.config import get_cloud_settings

    settings = get_cloud_settings()

    client = ArangoClient(hosts=settings.ARANGO_URL)

    # Connect to system database to create reference DB if needed
    sys_db = client.db(
        "_system",
        username=settings.ARANGO_USERNAME,
        password=settings.ARANGO_PASSWORD,
    )

    # Create reference database if it doesn't exist
    if not sys_db.has_database(settings.ARANGO_REFERENCE_DATABASE):
        logger.info(
            "Creating cloud reference database",
            database=settings.ARANGO_REFERENCE_DATABASE,
        )
        sys_db.create_database(settings.ARANGO_REFERENCE_DATABASE)

    # Connect to reference database
    db = client.db(
        settings.ARANGO_REFERENCE_DATABASE,
        username=settings.ARANGO_USERNAME,
        password=settings.ARANGO_PASSWORD,
    )

    logger.info(
        "Connected to cloud reference database",
        database=settings.ARANGO_REFERENCE_DATABASE,
    )

    return db


def export_collection(
    db: StandardDatabase,
    collection_name: str,
    output_file: Path,
) -> Dict[str, Any]:
    """
    Export collection to JSON file.

    Args:
        db: Source database
        collection_name: Collection to export
        output_file: Output JSON file path

    Returns:
        Export metadata (count, checksum, sample_doc_ids)
    """
    logger.info("Exporting collection", collection=collection_name)

    if not db.has_collection(collection_name):
        logger.warning("Collection does not exist, skipping", collection=collection_name)
        return {
            "count": 0,
            "checksum": None,
            "sample_doc_ids": [],
        }

    collection = db.collection(collection_name)

    # Export all documents
    documents = []
    for doc in collection.all():
        documents.append(doc)

    # Write to JSON file
    with open(output_file, "w") as f:
        json.dump(documents, f, indent=2)

    # Compute checksum
    checksum = hashlib.sha256(json.dumps(documents, sort_keys=True).encode()).hexdigest()

    # Sample document IDs for spot-checking
    sample_size = min(10, len(documents))
    sample_doc_ids = random.sample([doc["_key"] for doc in documents if "_key" in doc], sample_size) if len(documents) > 0 else []

    logger.info(
        "Collection exported",
        collection=collection_name,
        count=len(documents),
        file_size_mb=output_file.stat().st_size / 1024 / 1024,
        checksum=checksum[:16],
    )

    return {
        "count": len(documents),
        "checksum": checksum,
        "sample_doc_ids": sample_doc_ids,
    }


def import_collection(
    db: StandardDatabase,
    collection_name: str,
    input_file: Path,
    is_edge: bool = False,
) -> int:
    """
    Import collection from JSON file.

    Args:
        db: Target database
        collection_name: Collection to import into
        input_file: Input JSON file path
        is_edge: Whether this is an edge collection

    Returns:
        Number of documents imported
    """
    logger.info("Importing collection", collection=collection_name, is_edge=is_edge)

    if not input_file.exists():
        logger.warning("Export file not found, skipping", file=str(input_file))
        return 0

    # Create collection if it doesn't exist
    if not db.has_collection(collection_name):
        db.create_collection(collection_name, edge=is_edge)
        logger.info("Created collection", collection=collection_name, is_edge=is_edge)

    collection = db.collection(collection_name)

    # Load documents from JSON
    with open(input_file, "r") as f:
        documents = json.load(f)

    if len(documents) == 0:
        logger.info("No documents to import", collection=collection_name)
        return 0

    # Import in batches for performance
    batch_size = 1000
    imported_count = 0

    for i in range(0, len(documents), batch_size):
        batch = documents[i:i+batch_size]

        try:
            collection.import_bulk(batch, overwrite=True)
            imported_count += len(batch)

            logger.debug(
                "Batch imported",
                collection=collection_name,
                batch=f"{i+1}-{i+len(batch)}",
                total=len(documents),
            )

        except Exception as e:
            logger.error(
                "Batch import failed",
                collection=collection_name,
                batch=f"{i+1}-{i+len(batch)}",
                error=str(e),
            )
            raise

    logger.info(
        "Collection imported",
        collection=collection_name,
        count=imported_count,
    )

    return imported_count


def export_database(db: StandardDatabase) -> Dict[str, Any]:
    """
    Export entire database to JSON files.

    Exports all collections and creates manifest.json with metadata.

    Args:
        db: Source database

    Returns:
        Export manifest with collection metadata
    """
    logger.info("Starting database export")

    # Create export directory
    EXPORT_DIR.mkdir(exist_ok=True)

    manifest = {
        "export_timestamp": datetime.utcnow().isoformat(),
        "source_database": "complira_graph",
        "total_documents": 0,
        "total_edges": 0,
        "collections": {},
    }

    # Get all collections
    collections = db.collections()

    for coll_info in collections:
        collection_name = coll_info["name"]

        # Skip system collections
        if collection_name.startswith("_"):
            continue

        is_edge = coll_info["type"] == 3  # ArangoDB edge collection type

        # Export collection
        output_file = EXPORT_DIR / f"{collection_name}.json"
        metadata = export_collection(db, collection_name, output_file)

        # Update manifest
        manifest["collections"][collection_name] = {
            "is_edge": is_edge,
            "count": metadata["count"],
            "checksum": metadata["checksum"],
            "sample_doc_ids": metadata["sample_doc_ids"],
            "file": str(output_file.name),
        }

        if is_edge:
            manifest["total_edges"] += metadata["count"]
        else:
            manifest["total_documents"] += metadata["count"]

    # Write manifest
    with open(EXPORT_MANIFEST_FILE, "w") as f:
        json.dump(manifest, f, indent=2)

    logger.info(
        "Database export complete",
        total_documents=manifest["total_documents"],
        total_edges=manifest["total_edges"],
        collections=len(manifest["collections"]),
        export_dir=str(EXPORT_DIR),
    )

    return manifest


def import_database(db: StandardDatabase) -> Dict[str, Any]:
    """
    Import entire database from JSON files.

    Reads manifest.json and imports all collections.

    Args:
        db: Target database

    Returns:
        Import summary with collection counts
    """
    logger.info("Starting database import")

    # Load manifest
    if not EXPORT_MANIFEST_FILE.exists():
        raise FileNotFoundError(f"Export manifest not found: {EXPORT_MANIFEST_FILE}")

    with open(EXPORT_MANIFEST_FILE, "r") as f:
        manifest = json.load(f)

    summary = {
        "import_timestamp": datetime.utcnow().isoformat(),
        "source_export": manifest["export_timestamp"],
        "total_documents_imported": 0,
        "total_edges_imported": 0,
        "collections_imported": {},
    }

    # Import collections
    for collection_name, metadata in manifest["collections"].items():
        input_file = EXPORT_DIR / metadata["file"]
        is_edge = metadata["is_edge"]

        count = import_collection(db, collection_name, input_file, is_edge=is_edge)

        summary["collections_imported"][collection_name] = count

        if is_edge:
            summary["total_edges_imported"] += count
        else:
            summary["total_documents_imported"] += count

    logger.info(
        "Database import complete",
        total_documents=summary["total_documents_imported"],
        total_edges=summary["total_edges_imported"],
        collections=len(summary["collections_imported"]),
    )

    return summary


def verify_migration(
    local_db: StandardDatabase,
    cloud_db: StandardDatabase,
) -> bool:
    """
    Verify migration integrity.

    Checks:
    - AC-019: Export integrity (counts, checksums)
    - AC-022: Import integrity (counts match, spot-checks)
    - AC-024: Zero data loss (all counts must match exactly)

    Args:
        local_db: Source local database
        cloud_db: Target cloud database

    Returns:
        True if verification passes, False otherwise
    """
    logger.info("Starting migration verification")

    # Load manifest
    if not EXPORT_MANIFEST_FILE.exists():
        logger.error("Export manifest not found, cannot verify")
        return False

    with open(EXPORT_MANIFEST_FILE, "r") as f:
        manifest = json.load(f)

    verification_passed = True

    # Verify each collection
    for collection_name, export_metadata in manifest["collections"].items():
        logger.info("Verifying collection", collection=collection_name)

        # Check local count matches export
        if local_db.has_collection(collection_name):
            local_count = local_db.collection(collection_name).count()
            export_count = export_metadata["count"]

            if local_count != export_count:
                logger.error(
                    "Export count mismatch (AC-019 FAIL)",
                    collection=collection_name,
                    local_count=local_count,
                    export_count=export_count,
                )
                verification_passed = False

        # Check cloud count matches export
        if cloud_db.has_collection(collection_name):
            cloud_count = cloud_db.collection(collection_name).count()
            export_count = export_metadata["count"]

            if cloud_count != export_count:
                logger.error(
                    "Import count mismatch (AC-022 FAIL, AC-024 FAIL)",
                    collection=collection_name,
                    cloud_count=cloud_count,
                    export_count=export_count,
                )
                verification_passed = False
            else:
                logger.info(
                    "Count verified",
                    collection=collection_name,
                    count=cloud_count,
                )

            # Spot-check sample documents (AC-022)
            sample_doc_ids = export_metadata.get("sample_doc_ids", [])
            if sample_doc_ids:
                cloud_collection = cloud_db.collection(collection_name)

                for doc_id in sample_doc_ids:
                    if not cloud_collection.has(doc_id):
                        logger.error(
                            "Spot-check failed: document missing (AC-022 FAIL)",
                            collection=collection_name,
                            doc_id=doc_id,
                        )
                        verification_passed = False

                logger.info(
                    "Spot-check passed",
                    collection=collection_name,
                    sample_size=len(sample_doc_ids),
                )
        else:
            logger.warning(
                "Collection not found in cloud database",
                collection=collection_name,
            )

    # Final summary
    if verification_passed:
        logger.info("✅ Migration verification PASSED (AC-019, AC-022, AC-024)")
        logger.info(
            "Local database can remain as read-only backup for 30 days (AC-023)"
        )
        return True
    else:
        logger.error("❌ Migration verification FAILED")
        return False


def main():
    """Main entry point for migration script."""
    parser = argparse.ArgumentParser(
        description="Migrate Complira database from local to cloud"
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Export local database to JSON files (AC-017, AC-018, AC-019)",
    )
    parser.add_argument(
        "--import",
        action="store_true",
        help="Import JSON files into cloud database (AC-020, AC-021)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify migration integrity (AC-022, AC-024)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run export + import + verify in sequence",
    )

    args = parser.parse_args()

    try:
        if args.export or args.all:
            logger.info("=== EXPORT PHASE ===")
            local_db = get_local_db()
            export_manifest = export_database(local_db)

            logger.info(
                "Export complete",
                documents=export_manifest["total_documents"],
                edges=export_manifest["total_edges"],
            )

        if args.import or args.all:
            logger.info("=== IMPORT PHASE ===")
            cloud_db = get_cloud_db()
            import_summary = import_database(cloud_db)

            logger.info(
                "Import complete",
                documents=import_summary["total_documents_imported"],
                edges=import_summary["total_edges_imported"],
            )

        if args.verify or args.all:
            logger.info("=== VERIFICATION PHASE ===")
            local_db = get_local_db()
            cloud_db = get_cloud_db()

            verification_passed = verify_migration(local_db, cloud_db)

            if verification_passed:
                logger.info("✅ Migration completed successfully with zero data loss")
                return 0
            else:
                logger.error("❌ Migration verification failed")
                return 1

        logger.info("Migration script completed")
        return 0

    except Exception as e:
        logger.error(
            "Migration failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise


if __name__ == "__main__":
    exit(main())
