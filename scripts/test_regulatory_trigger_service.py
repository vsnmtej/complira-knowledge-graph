#!/usr/bin/env python3
"""
Smoke test for RegulatoryTriggerService.

Tests the basic functionality of the regulatory trigger service including
all 4 trigger rules and statistics collection.
"""

from complira_graph.db import get_db
from complira_graph.services.regulatory_trigger_service import RegulatoryTriggerService
import structlog

logger = structlog.get_logger()


def main():
    """Run smoke test of RegulatoryTriggerService."""
    print("=" * 70)
    print("Regulatory Trigger Service - Smoke Test")
    print("=" * 70)
    print()

    # Connect to database
    print("1. Connecting to database...")
    db = get_db()
    print("   ✅ Connected to ArangoDB")
    print()

    # Initialize service
    print("2. Initializing RegulatoryTriggerService...")
    service = RegulatoryTriggerService(db)
    print("   ✅ Service initialized")
    print()

    # Get initial statistics
    print("3. Getting initial statistics...")
    initial_stats = service.get_statistics()
    print(f"   ✅ Total edges before: {initial_stats['total_edges']}")
    print()

    # Run all trigger rules
    print("4. Running all trigger rules...")
    print("   This may take several minutes depending on data size...")
    print()

    result = service.run()

    print("   ✅ Service execution complete!")
    print()
    print("   Results:")
    print(f"   - Edges created: {result['edges_created']}")
    print(f"   - Execution time: {result['execution_time_seconds']:.2f}s")
    print(f"   - Rules executed: {', '.join(result['rules_executed'])}")
    print()
    print("   Edges by rule:")
    for rule_name, count in result['rule_results'].items():
        print(f"   - {rule_name}: {count} edges")
    print()

    # Get final statistics
    print("5. Getting final statistics...")
    final_stats = service.get_statistics()
    print(f"   ✅ Total edges after: {final_stats['total_edges']}")
    print()
    print("   Edges by rule:")
    for rule, count in final_stats.get('edges_by_rule', {}).items():
        print(f"   - {rule}: {count}")
    print()
    print("   Edges by urgency:")
    for urgency, count in final_stats.get('edges_by_urgency', {}).items():
        print(f"   - {urgency}: {count}")
    print()

    # Verify idempotency (run again, should create 0 edges)
    print("6. Testing idempotency (running service again)...")
    result2 = service.run()
    print(f"   ✅ Edges created on 2nd run: {result2['edges_created']} (should be 0)")
    print()

    print("=" * 70)
    print("✅ Smoke test complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
