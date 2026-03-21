"""
Clean up duplicate violates_requirement edges with batching.

The collection has 5.27M edges with 1.2M duplicates (23%).
Using batched approach to avoid connection timeouts.
"""

from complira_graph.db import get_db
import structlog

logger = structlog.get_logger()


def cleanup_violates_requirement_batched(db):
    """Remove duplicate edges using batched approach."""
    logger.info("Starting batched cleanup of violates_requirement...")

    # Count before
    before_count = db.collection('violates_requirement').count()
    logger.info(f"Edges before cleanup: {before_count:,}")

    # Use simpler approach: Find all duplicates and delete in single query
    # This is more efficient than batching for ArangoDB
    delete_query = '''
    FOR edge IN violates_requirement
        COLLECT from = edge._from, to = edge._to INTO edges
        LET keep_id = MIN(edges[*].edge._key)
        FOR e IN edges
            FILTER e.edge._key != keep_id
            REMOVE e.edge IN violates_requirement
            OPTIONS { ignoreErrors: false }
    '''

    logger.info("Executing deduplication query (may take 1-2 minutes)...")

    try:
        # Execute with longer timeout
        cursor = db.aql.execute(delete_query, ttl=600)
        # Consume cursor to ensure query completes
        list(cursor)

        # Count after
        after_count = db.collection('violates_requirement').count()
        removed = before_count - after_count

        logger.info(
            "✅ violates_requirement cleanup complete",
            before=before_count,
            after=after_count,
            removed=removed
        )

        # Verify no more duplicates
        dup_check = list(db.aql.execute('''
            FOR edge IN violates_requirement
                COLLECT from = edge._from, to = edge._to WITH COUNT INTO count
                FILTER count > 1
                LIMIT 1
                RETURN count
        '''))

        if len(dup_check) == 0:
            logger.info("✅ No duplicates remaining in violates_requirement")
        else:
            logger.warning("⚠️  Duplicates may still exist in violates_requirement")

        return removed

    except Exception as e:
        logger.error("Failed to cleanup violates_requirement", error=str(e))
        raise


def main():
    db = get_db()

    logger.info("=" * 70)
    logger.info("violates_requirement Deduplication")
    logger.info("=" * 70)

    try:
        removed = cleanup_violates_requirement_batched(db)
        logger.info("=" * 70)
        logger.info(f"✅ Removed {removed:,} duplicate edges")
        logger.info("=" * 70)
    except Exception as e:
        logger.error("Cleanup failed", error=str(e))
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
