"""
Clean up duplicate and broken CAPEC → ATT&CK edges.

Issues to fix:
1. 271 duplicate edges (agent ran 3 times)
2. 3 broken edges pointing to non-existent ATT&CK techniques
"""

from complira_graph.db import get_db
import structlog

logger = structlog.get_logger()

def cleanup_duplicate_edges(db):
    """Remove duplicate capec_maps_to_attack edges, keeping only one of each."""
    logger.info("Cleaning up duplicate edges...")

    # Delete all duplicate edges, keeping only the one with minimum _key
    delete_duplicates_query = '''
    FOR edge IN capec_maps_to_attack
        COLLECT from = edge._from, to = edge._to INTO edges
        LET keep_id = MIN(edges[*].edge._key)
        FOR e IN edges
            FILTER e.edge._key != keep_id
            REMOVE e.edge IN capec_maps_to_attack
            COLLECT WITH COUNT INTO removed
            RETURN removed
    '''

    results = list(db.aql.execute(delete_duplicates_query))
    removed = sum(results) if results else 0

    logger.info(f"✅ Removed {removed} duplicate edges")
    return removed


def cleanup_broken_edges(db):
    """Remove edges pointing to non-existent ATT&CK techniques."""
    logger.info("Cleaning up broken edges...")

    # Find broken edges
    broken_query = '''
    FOR edge IN capec_maps_to_attack
        LET technique_exists = DOCUMENT(edge._to) != null
        FILTER !technique_exists
        RETURN edge._key
    '''

    broken_keys = list(db.aql.execute(broken_query))
    logger.info(f"Found {len(broken_keys)} broken edges")

    # Remove broken edges
    for key in broken_keys:
        db.collection('capec_maps_to_attack').delete(key)

    logger.info(f"✅ Removed {len(broken_keys)} broken edges")
    return len(broken_keys)


def main():
    db = get_db()

    logger.info("=" * 60)
    logger.info("CAPEC → ATT&CK Edge Cleanup")
    logger.info("=" * 60)

    # Count before
    before_count = db.collection('capec_maps_to_attack').count()
    logger.info(f"Edges before cleanup: {before_count}")

    # Clean up duplicates
    removed_duplicates = cleanup_duplicate_edges(db)

    # Clean up broken edges
    removed_broken = cleanup_broken_edges(db)

    # Count after
    after_count = db.collection('capec_maps_to_attack').count()
    logger.info(f"\nEdges after cleanup: {after_count}")
    logger.info(f"Total removed: {before_count - after_count}")
    logger.info(f"  Duplicates: {removed_duplicates}")
    logger.info(f"  Broken: {removed_broken}")

    # Verify no more duplicates
    dup_check = list(db.aql.execute('''
        FOR edge IN capec_maps_to_attack
            COLLECT from = edge._from, to = edge._to WITH COUNT INTO count
            FILTER count > 1
            RETURN count
    '''))

    if len(dup_check) == 0:
        logger.info("✅ No duplicates remaining")
    else:
        logger.warning(f"⚠️  Still have {len(dup_check)} duplicate pairs")


if __name__ == '__main__':
    main()
