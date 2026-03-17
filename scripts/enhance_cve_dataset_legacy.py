#!/usr/bin/env python3
"""
OPTIONAL: Enhance CVE dataset with high-severity legacy CVEs (2015-2022).

This is Priority 3 in the tiered approach - run ONLY if you need deeper historical coverage.
Most users should run enhance_cve_dataset.py instead (Priority 1: last 3 years).

This script fetches CVEs from 2015-2022 but ONLY loads those with CVSS >= 9.0.
This gives you critical legacy vulnerabilities without the full historical dataset.

Prerequisites:
1. Run enhance_cve_dataset.py first (Priority 1)
2. Ensure NVD_API_KEY is set in .env
3. Run: .venv/bin/python scripts/enhance_cve_dataset_legacy.py

This will take approximately 60-90 minutes with an API key.
Expected result: ~15,000 additional high-severity CVEs.
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from complira_graph.db import get_db
from complira_graph.agents.nvd import NVDAgent
from datetime import datetime


def filter_high_cvss_records(records, min_cvss: float = 9.0):
    """Filter records to only include high CVSS scores."""
    for record in records:
        # Check if it's a vulnerability document (not an edge)
        if "_collection" not in record:
            cvss_v3 = record.get("cvss_v3_score")
            cvss_v2 = record.get("cvss_v2_score")

            # Only include if CVSS >= min_cvss
            if (cvss_v3 and cvss_v3 >= min_cvss) or (cvss_v2 and cvss_v2 >= min_cvss):
                yield record
        else:
            # Always yield edges (will be filtered by parent documents)
            yield record


def main():
    """Run NVD agent for legacy high-severity CVEs."""
    print("=" * 80)
    print("🚀 CVE Dataset Enhancement - Legacy High-Severity CVEs (OPTIONAL)")
    print("=" * 80)
    print()

    # Connect to database
    db = get_db()

    # Check current CVE count
    current_count = db.collection("vulnerabilities").count()
    print(f"📊 Current CVE count: {current_count:,}")
    print()

    # Legacy fetch explanation
    print("📋 Priority 3: Legacy High-Severity CVEs")
    print("   Date range: 2015-2022")
    print("   Filter: CVSS >= 9.0 only")
    print("   Expected: ~15,000 additional CVEs")
    print()
    print("⚠️  Note: This is OPTIONAL and only recommended if:")
    print("   - You need coverage for legacy systems (pre-2023)")
    print("   - You've already run enhance_cve_dataset.py (Priority 1)")
    print("   - You need historical critical vulnerabilities")
    print()

    # Initialize NVD agent
    agent = NVDAgent(db=db)

    # Set date range for legacy period
    start_date = datetime(2015, 1, 1)
    end_date = datetime(2022, 12, 31)

    print(f"📅 Date range: {start_date.date()} to {end_date.date()}")
    print(f"   Fetching CVEs with CVSS >= 9.0 only")
    print()

    # Check if API key is set
    if not agent.api_key:
        print("❌ NVD_API_KEY not found!")
        print()
        print("⚠️  Without an API key, this will be extremely slow")
        print("   Please set NVD_API_KEY before running this script")
        print()
        return 1
    else:
        print("✅ NVD API key detected")
        print("⏱️  Estimated time: 60-90 minutes")
        print()

    # Confirm before starting
    print("This script will:")
    print("  1. Fetch CVEs from 2015-2022 from NVD API")
    print("  2. Filter to only CVSS >= 9.0")
    print("  3. Add ~15K critical legacy CVEs to your database")
    print()

    response = input("Start legacy CVE enhancement? (y/n): ")
    if response.lower() != 'y':
        print("❌ Cancelled.")
        return 1

    print()
    print("=" * 80)
    print("🔄 Starting NVD ingestion (legacy high-severity)...")
    print("=" * 80)
    print()

    # Run agent with custom date range and filtering
    start_time = time.time()
    try:
        # Fetch data with custom date range
        print("📥 Fetching CVE data from NVD API (2015-2022)...")
        print("   This will fetch ALL CVEs from this period...")
        raw_data = agent.fetch_data(start_date=start_date, end_date=end_date)

        print(f"✅ Fetched {len(raw_data):,} CVE records")
        print()

        # Transform data
        print("🔄 Transforming CVE data...")
        records = agent.transform_data(raw_data)

        # Filter to high CVSS only
        print("🔍 Filtering to CVSS >= 9.0...")
        filtered_records = list(filter_high_cvss_records(records, min_cvss=9.0))

        # Count documents (not edges)
        doc_count = sum(1 for r in filtered_records if "_collection" not in r)
        print(f"✅ Filtered to {doc_count:,} high-severity CVEs")
        print()

        # Load data
        print("💾 Loading high-severity CVEs into database...")
        result = agent.load_data(iter(filtered_records))

        elapsed = time.time() - start_time
        new_count = db.collection("vulnerabilities").count()

        print()
        print("=" * 80)
        print("✅ Legacy CVE Enhancement Complete!")
        print("=" * 80)
        print()
        print(f"📊 Results:")
        print(f"   Previous CVE count: {current_count:,}")
        print(f"   New CVE count: {new_count:,}")
        print(f"   CVEs added: {new_count - current_count:,}")
        print(f"   Documents created: {result.get('total_created', 0):,}")
        print(f"   Documents updated: {result.get('total_updated', 0):,}")
        print(f"   Time elapsed: {elapsed/60:.1f} minutes ({elapsed/3600:.2f} hours)")
        print()
        print("🎉 Your enrichment API now has legacy high-severity CVEs!")
        print()
        return 0

    except KeyboardInterrupt:
        elapsed = time.time() - start_time
        print()
        print("⚠️  Interrupted by user")
        print(f"   Partial execution time: {elapsed/60:.1f} minutes")
        print()
        print("💾 Progress saved via checkpoint!")
        print("   Run this script again to resume from where you left off.")
        print()
        return 1

    except Exception as e:
        print()
        print(f"❌ Error: {e}")
        print()
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
