#!/usr/bin/env python3
"""
Seed reference database with authoritative threat intelligence data.

Runs all essential agents to populate the knowledge graph with:
- CVE data (NVD)
- EPSS scores (FIRST.org)
- KEV catalog (CISA)
- CWE weaknesses (MITRE)
- CAPEC attack patterns (MITRE)
- ATT&CK techniques (MITRE)
- Exploit intelligence (VulnCheck)
- D3FEND defenses (MITRE)
- NIST 800-53 controls
- GitHub Security Advisories (GHSA)
- Regulatory frameworks (CRA, FDA, IEC)

This is a ONE-TIME operation to populate your local knowledge graph.
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from complira_graph.db import get_db, init_schema
from complira_graph.agents import (
    nvd,
    epss,
    kev,
    cwe,
    capec,
    attack,
    d3fend,
    oscal,
    ghsa,
    cra,
)
from complira_graph.agents.vulncheck_exploits_agent import VulnCheckExploitsAgent
from complira_graph.agents.yaml_regulatory import YAMLRegulatoryAgent
from complira_graph.agents.derived_edges import DerivedEdgesAgent

# Order matters! Some agents depend on others
AGENTS = [
    # 1. Core vulnerability data (auto-detects initial seed vs incremental)
    ("NVD CVE Data", nvd.NVDAgent, "Recent CVEs from NIST NVD (120-day window on first run)", "2-5 min"),

    # 2. Threat intelligence scores
    ("EPSS Scores", epss.EPSSAgent, "Exploit probability scores from FIRST.org", "2-5 min"),
    ("CISA KEV Catalog", kev.KEVAgent, "Known Exploited Vulnerabilities", "30 sec"),

    # 3. Weakness & attack pattern taxonomies
    ("CWE Weaknesses", cwe.CWEAgent, "~900 weakness types from MITRE", "1-2 min"),
    ("CAPEC Attack Patterns", capec.CAPECAgent, "~600 attack patterns from MITRE", "1-2 min"),

    # 4. Threat actor intelligence
    ("ATT&CK Techniques", attack.ATTACKAgent, "~800 techniques from MITRE", "2-3 min"),

    # 5. Exploit intelligence
    ("VulnCheck Exploits", VulnCheckExploitsAgent, "Public exploit data", "5-10 min"),

    # 6. Defensive techniques
    ("D3FEND Defenses", d3fend.D3FENDAgent, "Evidence-based defenses from MITRE", "1-2 min"),

    # 7. Compliance frameworks
    ("NIST 800-53 Controls", oscal.OSCALAgent, "Federal security controls", "1-2 min"),

    # 8. Additional vulnerability sources
    ("GitHub Security Advisories", ghsa.GHSAAgent, "~700K OSS vulnerability advisories", "30-45 min"),

    # 9. Regulatory frameworks
    ("EU Cyber Resilience Act", cra.CRAAgent, "CRA compliance requirements", "30 sec"),
    ("FDA 524B Medical Devices", lambda db: YAMLRegulatoryAgent(db, "FDA_524B"), "FDA cybersecurity requirements", "30 sec"),
    ("IEC 62304 Medical Software", lambda db: YAMLRegulatoryAgent(db, "IEC_62304"), "Medical device software lifecycle", "30 sec"),

    # 10. Derived edges (MUST run last - depends on all base data)
    ("Derived Graph Edges", DerivedEdgesAgent, "ATT&CK→CWE and ATT&CK→NIST mappings", "1-2 sec"),
]


def main():
    """Run all seeding agents."""
    print("=" * 80)
    print("🌱 Seeding Reference Database with Authoritative Threat Intelligence")
    print("=" * 80)
    print()
    print(f"This will populate your local ArangoDB with {len(AGENTS)} data sources:")
    print()

    for i, (name, agent_class, desc, eta) in enumerate(AGENTS, 1):
        print(f"  {i}. {name:25s} - {desc} (ETA: {eta})")

    print()
    print("⏱️  Total estimated time: 30-60 minutes")
    print("💾 Total estimated size: ~2-3 GB")
    print()

    response = input("Continue with seeding? (y/n): ")
    if response.lower() != 'y':
        print("❌ Seeding cancelled.")
        return 1

    print()
    print("=" * 80)
    print()

    db = get_db()

    print("📋 Initializing database schema...")
    init_schema(db)
    print("✅ Schema initialized\n")

    total_start = time.time()
    results = []

    for i, (name, agent_class, desc, eta) in enumerate(AGENTS, 1):
        print(f"[{i}/{len(AGENTS)}] Running {name}...")
        print(f"    Description: {desc}")
        print(f"    ETA: {eta}")

        start = time.time()
        try:
            # Handle both class constructors and lambda functions
            if callable(agent_class) and not isinstance(agent_class, type):
                # It's a lambda function, call it with db parameter
                agent = agent_class(db)
            else:
                # It's a class, instantiate with db parameter
                agent = agent_class(db=db)

            result = agent.run()
            elapsed = time.time() - start

            # Handle different result formats (some agents return 'created' instead of 'documents_created')
            docs_created = result.get("documents_created", result.get("created", 0))

            print(f"    ✅ Complete! Created {docs_created:,} documents in {elapsed:.1f}s")
            results.append({
                "name": name,
                "status": "success",
                "docs": docs_created,
                "time": elapsed
            })

        except Exception as e:
            elapsed = time.time() - start
            print(f"    ❌ Failed: {e}")
            results.append({
                "name": name,
                "status": "failed",
                "error": str(e),
                "time": elapsed
            })

        print()

    total_elapsed = time.time() - total_start

    # Summary
    print("=" * 80)
    print("📊 Seeding Summary")
    print("=" * 80)
    print()

    total_docs = 0
    successes = 0
    failures = 0

    for r in results:
        status_icon = "✅" if r["status"] == "success" else "❌"
        docs = r.get("docs", 0)
        total_docs += docs

        if r["status"] == "success":
            successes += 1
            print(f"{status_icon} {r['name']:30s} {docs:>10,} docs  {r['time']:>6.1f}s")
        else:
            failures += 1
            print(f"{status_icon} {r['name']:30s} FAILED: {r.get('error', 'Unknown')}")

    print()
    print(f"Total documents created: {total_docs:,}")
    print(f"Total time: {total_elapsed/60:.1f} minutes")
    print(f"Successes: {successes}/{len(AGENTS)}")
    print(f"Failures: {failures}/{len(AGENTS)}")
    print()

    if failures == 0:
        print("✅ Reference database seeding complete!")
        print("🚀 Your Phase 1 enrichment API is now ready to use!")
        return 0
    else:
        print("⚠️  Some agents failed. Check errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
