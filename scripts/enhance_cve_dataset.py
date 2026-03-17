#!/usr/bin/env python3
"""
Enhance CVE dataset using tiered approach (last 3 years + KEV catalog).

Tiered Strategy:
- Priority 1: Last 3 years (2023-present) - ~75K CVEs covering 95% of real-world findings
- Priority 2: CISA KEV catalog CVEs - already in database from KEV agent
- Priority 3: High CVSS CVEs from 2015-2022 - optional, run separately if needed

Prerequisites:
1. Get free NVD API key: https://nvd.nist.gov/developers/request-an-api-key
2. Add to .env file: NVD_API_KEY=your-key-here
3. Run: .venv/bin/python scripts/enhance_cve_dataset.py

This will take approximately 45-60 minutes with an API key.
The script supports checkpointing so you can stop/resume anytime.
"""

import sys
import time
from pathlib import Path
import argparse

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from complira_graph.db import get_db
from complira_graph.agents.nvd import NVDAgent


def main():
    """Run NVD agent with tiered fetch strategy."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Enhance CVE dataset with Priority 1 (last 3 years)')
    parser.add_argument('--yes', '-y', action='store_true', help='Skip confirmation prompts')
    args = parser.parse_args()

    print("=" * 80)
    print("🚀 CVE Dataset Enhancement - Tiered Approach")
    print("=" * 80)
    print()

    # Connect to database
    db = get_db()

    # Check current CVE count
    current_count = db.collection("vulnerabilities").count()
    print(f"📊 Current CVE count: {current_count:,}")
    print()

    # Tiered approach explanation
    print("📋 Tiered Fetch Strategy:")
    print("   Priority 1: Last 3 years (2023-present)")
    print("               ~75K CVEs covering 95% of real-world findings")
    print("   Priority 2: CISA KEV catalog (~1,500 CVEs)")
    print("               Already in database - actively exploited CVEs")
    print("   Priority 3: High CVSS from 2015-2022")
    print("               Optional - run separately if needed")
    print()
    print(f"🎯 Target CVE count: ~75,000 (Priority 1)")
    print(f"📥 CVEs to fetch: ~{75000 - current_count:,}")
    print()

    # Initialize NVD agent
    agent = NVDAgent(db=db)

    # Set date range for last 3 years
    from datetime import datetime, timedelta, timezone
    start_date = datetime(2023, 1, 1)  # Last 3 years
    end_date = datetime.now(timezone.utc).replace(tzinfo=None)  # UTC without timezone info

    print(f"📅 Date range: {start_date.date()} to {end_date.date()}")
    print(f"   Fetching CVEs from last 3 years")
    print()

    # Check if API key is set
    if not agent.api_key:
        print("❌ NVD_API_KEY not found!")
        print()
        print("⚠️  Without an API key, this will be extremely slow (5 req/30s)")
        print("   Estimated time: ~10 hours for 75K CVEs")
        print()
        print("📝 Get a free API key:")
        print("   1. Visit: https://nvd.nist.gov/developers/request-an-api-key")
        print("   2. Fill out the form (instant approval)")
        print("   3. Add to .env: NVD_API_KEY=your-key-here")
        print()
        if not args.yes:
            response = input("Continue without API key? (y/n): ")
            if response.lower() != 'y':
                print("❌ Exiting. Please set NVD_API_KEY and try again.")
                return 1
        else:
            print("⚠️  Proceeding without API key (--yes flag used)")
    else:
        print("✅ NVD API key detected")
        print("⏱️  Estimated time: 45-60 minutes")
        print()

    # Confirm before starting
    print("This script will:")
    print("  1. Fetch CVEs from 2023-present from NVD API")
    print("  2. Populate 'vulnerabilities' collection")
    print("  3. Create 'has_weakness' edges to CWE")
    print("  4. Support checkpoint/resume (safe to stop anytime)")
    print()

    if not args.yes:
        response = input("Start CVE enhancement? (y/n): ")
        if response.lower() != 'y':
            print("❌ Cancelled.")
            return 1
    else:
        print("✅ Starting automatically (--yes flag used)")
        print()

    print()
    print("=" * 80)
    print("🔄 Starting NVD ingestion (last 3 years)...")
    print("=" * 80)
    print()

    # Run agent with custom date range
    start_time = time.time()
    try:
        # Initialize checkpoint support (required by fetch_data)
        agent._checkpoint = agent._load_checkpoint()

        # NVD API has 120-day maximum date range limit
        # Chunk the date range into 120-day windows
        print("📥 Fetching CVE data from NVD API in 120-day chunks...")
        print()

        all_raw_data = []
        chunk_size_days = 119  # Use 119 to be safe
        current_start = start_date
        chunk_num = 0

        while current_start < end_date:
            chunk_num += 1
            current_end = min(current_start + timedelta(days=chunk_size_days), end_date)

            print(f"   Chunk {chunk_num}: {current_start.date()} to {current_end.date()}")

            chunk_data = agent.fetch_data(start_date=current_start, end_date=current_end)
            all_raw_data.extend(chunk_data)

            print(f"   ✅ Fetched {len(chunk_data):,} CVEs (total: {len(all_raw_data):,})")
            print()

            current_start = current_end + timedelta(days=1)

        print(f"✅ Fetched {len(all_raw_data):,} CVE records total")
        print()

        # Transform data
        print("🔄 Transforming CVE data...")
        records = agent.transform_data(all_raw_data)

        # Load data
        print("💾 Loading CVE data into database...")
        result = agent.load_data(records)

        elapsed = time.time() - start_time
        new_count = db.collection("vulnerabilities").count()

        # Clear checkpoint on success
        agent._clear_checkpoint()

        print()
        print("=" * 80)
        print("✅ CVE Enhancement Complete!")
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
        print("🎉 Your enrichment API now has CVEs from the last 3 years!")
        print()
        print("💡 Note: CISA KEV catalog CVEs are already in your database")
        print("   from the KEV agent (covers actively exploited CVEs)")
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
