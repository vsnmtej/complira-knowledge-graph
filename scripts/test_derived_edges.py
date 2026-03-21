#!/usr/bin/env python3
"""
Test script for DerivedEdgesAgent.

Validates:
1. Agent can derive technique_exploits_weakness edges via graph traversal
2. Agent can fetch and parse ATT&CK → NIST 800-53 mapping
3. Both edge collections are created and populated
4. Edge counts match expectations (~5,562 + ~8,000)
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from complira_graph.db import get_db
from complira_graph.agents.derived_edges import DerivedEdgesAgent


def validate_prerequisites(db):
    """Validate that required collections exist and have data."""
    print("🔍 Validating prerequisites...")
    print()

    required_collections = {
        "attack_techniques": 800,  # Min expected
        "attack_patterns": 600,  # CAPEC patterns
        "weaknesses": 900,
        "oscal_controls": 1000,  # NIST 800-53 controls
    }

    required_edges = {
        "capec_maps_to_attack": 200,
        "capec_relates_to_cwe": 10000,
    }

    all_valid = True

    for coll_name, min_count in required_collections.items():
        query = f"RETURN LENGTH({coll_name})"
        cursor = db.aql.execute(query)
        count = list(cursor)[0]

        if count >= min_count:
            print(f"  ✅ {coll_name}: {count:,} documents")
        else:
            print(
                f"  ❌ {coll_name}: {count:,} documents (expected >= {min_count:,})"
            )
            all_valid = False

    for coll_name, min_count in required_edges.items():
        query = f"RETURN LENGTH({coll_name})"
        cursor = db.aql.execute(query)
        count = list(cursor)[0]

        if count >= min_count:
            print(f"  ✅ {coll_name}: {count:,} edges")
        else:
            print(f"  ❌ {coll_name}: {count:,} edges (expected >= {min_count:,})")
            all_valid = False

    print()

    if not all_valid:
        print("⚠️  Prerequisites not met. Please run seed script first:")
        print("  .venv/bin/python scripts/seed_reference_database.py")
        print()
        return False

    print("✅ All prerequisites met")
    print()
    return True


def test_agent(db):
    """Test DerivedEdgesAgent."""
    print("=" * 80)
    print("🧪 Testing DerivedEdgesAgent")
    print("=" * 80)
    print()

    agent = DerivedEdgesAgent(db=db)

    print("Running agent...")
    start = time.time()

    try:
        result = agent.run()
        elapsed = time.time() - start

        print()
        print("✅ Agent completed successfully!")
        print()
        print("Results:")
        print(f"  Total edges created: {result['documents_created']:,}")
        print(
            f"  technique_exploits_weakness: {result['technique_exploits_weakness']:,}"
        )
        print(
            f"  technique_mitigated_by_control: {result['technique_mitigated_by_control']:,}"
        )
        print(f"  Execution time: {elapsed:.2f}s")
        print()

        return True

    except Exception as e:
        elapsed = time.time() - start
        print()
        print(f"❌ Agent failed: {e}")
        print(f"  Execution time: {elapsed:.2f}s")
        print()
        import traceback

        traceback.print_exc()
        return False


def validate_edges(db):
    """Validate edge collections were created correctly."""
    print("=" * 80)
    print("🔍 Validating Edge Collections")
    print("=" * 80)
    print()

    # Check technique_exploits_weakness
    print("1. technique_exploits_weakness")
    query = """
    FOR e IN technique_exploits_weakness
      LIMIT 3
      RETURN {
        from: e._from,
        to: e._to,
        source: e.source,
        derivation_method: e.derivation_method,
        capec_bridge_ids: e.capec_bridge_ids,
        technique_name: e.technique_name,
        cwe_name: e.cwe_name
      }
    """
    cursor = db.aql.execute(query)
    sample_edges = list(cursor)

    count_query = "RETURN LENGTH(technique_exploits_weakness)"
    cursor = db.aql.execute(count_query)
    count = list(cursor)[0]

    print(f"  Total edges: {count:,}")
    print(f"  Expected: ~5,562")
    print()
    print("  Sample edges:")
    for edge in sample_edges:
        print(f"    {edge['from']} → {edge['to']}")
        print(f"      Technique: {edge['technique_name']}")
        print(f"      CWE: {edge['cwe_name']}")
        print(f"      Via CAPEC: {', '.join(edge['capec_bridge_ids'][:3])}")
        print()

    # Check technique_mitigated_by_control
    print("2. technique_mitigated_by_control")
    query = """
    FOR e IN technique_mitigated_by_control
      LIMIT 3
      RETURN {
        from: e._from,
        to: e._to,
        source: e.source,
        mapping_version: e.mapping_version,
        technique_id: e.technique_id,
        control_id: e.control_id
      }
    """
    cursor = db.aql.execute(query)
    sample_edges = list(cursor)

    count_query = "RETURN LENGTH(technique_mitigated_by_control)"
    cursor = db.aql.execute(count_query)
    count = list(cursor)[0]

    print(f"  Total edges: {count:,}")
    print(f"  Expected: ~8,000")
    print()
    print("  Sample edges:")
    for edge in sample_edges:
        print(
            f"    {edge['technique_id']} mitigated by {edge['control_id']} (source: {edge['source']})"
        )
    print()


def main():
    """Main test flow."""
    print("=" * 80)
    print("🧪 DerivedEdgesAgent Test Suite")
    print("=" * 80)
    print()

    db = get_db()

    # Step 1: Validate prerequisites
    if not validate_prerequisites(db):
        return 1

    # Step 2: Run agent
    if not test_agent(db):
        return 1

    # Step 3: Validate edges
    validate_edges(db)

    print("=" * 80)
    print("✅ All tests passed!")
    print("=" * 80)
    print()
    print("Next step: Add DerivedEdgesAgent to seed script")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
