#!/usr/bin/env python3
"""
Test NVD API key connectivity.

Run this after setting NVD_API_KEY in .env to verify it works.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from complira_graph.db import get_db
from complira_graph.agents.nvd import NVDAgent


def main():
    print("=" * 60)
    print("🔑 Testing NVD API Key")
    print("=" * 60)
    print()

    try:
        # Initialize agent
        db = get_db()
        agent = NVDAgent(db=db)

        if not agent.api_key:
            print("❌ NVD_API_KEY not found in environment")
            print()
            print("Please add to .env file:")
            print("  NVD_API_KEY=your-key-here")
            return 1

        print(f"✅ NVD_API_KEY found: {agent.api_key[:8]}...{agent.api_key[-4:]}")
        print(f"   Rate limit: 50 requests/30s (with API key)")
        print()

        # Test a simple API call
        print("🧪 Testing API connection...")

        # Make a small test request
        url = f"{agent.NVD_API_BASE}?resultsPerPage=1"
        headers = {"apiKey": agent.api_key} if agent.api_key else {}

        response = agent.client.get(url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            total_results = data.get("totalResults", 0)
            print(f"✅ API connection successful!")
            print(f"   Total CVEs available: {total_results:,}")
            print()
            print("🎉 Your NVD API key is working correctly!")
            print()
            print("Next step: Run the enhancement script:")
            print("  .venv/bin/python scripts/enhance_cve_dataset.py")
            return 0
        else:
            print(f"❌ API request failed: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return 1

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
