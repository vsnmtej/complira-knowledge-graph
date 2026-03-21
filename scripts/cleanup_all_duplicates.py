"""
Clean up duplicate edges across all edge collections.

Issues found:
- has_weakness: 1,914,991 duplicate edges (87%)
- violates_requirement: 1,227,100 duplicate edges (23%)
- d3fend_counters_technique: 64,761 duplicate edges (95%)
- capec_relates_to_cwe: 12,142 duplicate edges (91%)
- child_of: 8,060 duplicate edges (87%)

Total: ~3.2 million duplicate edges to remove
"""

from complira_graph.db import get_db
import structlog

logger = structlog.get_logger()


def cleanup_edge_collection(db, collection_name: str):
    """Remove duplicate edges from a collection, keeping only one of each (_from, _to) pair."""
    logger.info(f"Cleaning up {collection_name}...", collection=collection_name)

    # Count before
    before_count = db.collection(collection_name).count()

    # Delete all duplicate edges, keeping only the one with minimum _key
    delete_duplicates_query = f'''
    FOR edge IN {collection_name}
        COLLECT from = edge._from, to = edge._to INTO edges
        LET keep_id = MIN(edges[*].edge._key)
        FOR e IN edges
            FILTER e.edge._key != keep_id
            REMOVE e.edge IN {collection_name}
            COLLECT WITH COUNT INTO removed
            RETURN removed
    '''

    results = list(db.aql.execute(delete_duplicates_query))
    removed = sum(results) if results else 0

    # Count after
    after_count = db.collection(collection_name).count()

    logger.info(
        f"✅ {collection_name} cleanup complete",
        before=before_count,
        after=after_count,
        removed=removed
    )

    # Verify no more duplicates
    dup_check = list(db.aql.execute(f'''
        FOR edge IN {collection_name}
            COLLECT from = edge._from, to = edge._to WITH COUNT INTO count
            FILTER count > 1
            RETURN count
    '''))

    if len(dup_check) == 0:
        logger.info(f"✅ No duplicates remaining in {collection_name}")
    else:
        logger.warning(f"⚠️  Still have {len(dup_check)} duplicate pairs in {collection_name}")

    return removed


def main():
    db = get_db()

    logger.info("=" * 70)
    logger.info("Database Edge Deduplication")
    logger.info("=" * 70)

    # Edge collections with duplicates
    edge_collections = [
        'has_weakness',
        'capec_relates_to_cwe',
        'd3fend_counters_technique',
        'child_of',
        'violates_requirement',
    ]

    total_removed = 0

    for collection_name in edge_collections:
        try:
            if not db.has_collection(collection_name):
                logger.warning(f"Collection {collection_name} does not exist, skipping...")
                continue

            removed = cleanup_edge_collection(db, collection_name)
            total_removed += removed

        except Exception as e:
            logger.error(f"Failed to clean up {collection_name}", error=str(e))

    logger.info("=" * 70)
    logger.info(f"Total duplicate edges removed: {total_removed:,}")
    logger.info("=" * 70)


if __name__ == '__main__':
    main()
