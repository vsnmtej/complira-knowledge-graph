#!/usr/bin/env python3
"""
Test script for the 4 newly added agents.

Tests:
- GHSAAgent (GitHub Security Advisories)
- CRAAgent (EU Cyber Resilience Act)
- YAMLRegulatoryAgent with FDA_524B
- YAMLRegulatoryAgent with IEC_62304

This is a quick validation before running the full seed script.
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from complira_graph.db import get_db
from complira_graph.agents import ghsa, cra
from complira_graph.agents.yaml_regulatory import YAMLRegulatoryAgent


def test_agent(name, agent_instance, expected_min_docs=1):
    """Test a single agent."""
    print(f"\n{'=' * 60}")
    print(f"Testing: {name}")
    print('=' * 60)

    start = time.time()
    try:
        result = agent_instance.run()
        elapsed = time.time() - start

        # Handle different result formats
        docs_created = result.get("documents_created", result.get("created", 0))

        print(f"✅ Success!")
        print(f"   Documents created: {docs_created:,}")
        print(f"   Time: {elapsed:.2f}s")

        if docs_created < expected_min_docs:
            print(f"⚠️  Warning: Expected at least {expected_min_docs} documents, got {docs_created}")
            return False

        return True

    except Exception as e:
        elapsed = time.time() - start
        print(f"❌ Failed: {e}")
        print(f"   Time: {elapsed:.2f}s")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Test all 4 new agents."""
    print("=" * 60)
    print("🧪 Testing New Agents for Seed Script")
    print("=" * 60)
    print()
    print("This will test the 4 newly added agents:")
    print("  1. GHSAAgent (GitHub Security Advisories)")
    print("  2. CRAAgent (EU Cyber Resilience Act)")
    print("  3. YAMLRegulatoryAgent (FDA 524B)")
    print("  4. YAMLRegulatoryAgent (IEC 62304)")
    print()

    response = input("Continue with testing? (y/n): ")
    if response.lower() != 'y':
        print("❌ Testing cancelled.")
        return 1

    db = get_db()
    results = []

    # Test 1: GHSAAgent
    print("\n" + "=" * 60)
    print("Note: GHSA may take 2-3 minutes if fetching from GitHub API")
    print("=" * 60)
    agent = ghsa.GHSAAgent(db=db)
    success = test_agent("GitHub Security Advisories", agent, expected_min_docs=1)
    results.append(("GHSA", success))

    # Test 2: CRAAgent
    agent = cra.CRAAgent(db=db)
    success = test_agent("EU Cyber Resilience Act", agent, expected_min_docs=50)
    results.append(("CRA", success))

    # Test 3: FDA 524B
    agent = YAMLRegulatoryAgent(db, framework_key="FDA_524B")
    success = test_agent("FDA 524B Medical Devices", agent, expected_min_docs=30)
    results.append(("FDA_524B", success))

    # Test 4: IEC 62304
    agent = YAMLRegulatoryAgent(db, framework_key="IEC_62304")
    success = test_agent("IEC 62304 Medical Software", agent, expected_min_docs=50)
    results.append(("IEC_62304", success))

    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Summary")
    print("=" * 60)

    passed = sum(1 for _, s in results if s)
    failed = sum(1 for _, s in results if not s)

    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {name}")

    print()
    print(f"Passed: {passed}/4")
    print(f"Failed: {failed}/4")
    print()

    if failed == 0:
        print("✅ All agents working! Ready to update seed script.")
        return 0
    else:
        print("⚠️  Some agents failed. Check errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
