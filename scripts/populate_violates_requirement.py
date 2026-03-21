#!/usr/bin/env python3
"""
Populate violates_requirement edge collection.

This implements the "Path B" of the dual-path compliance architecture:
- Path A: maps_to_requirement (what evidence is needed) - already exists
- Path B: violates_requirement (what is actively breached) - THIS SCRIPT

Mapping Logic (Phase 1B - Minimal Implementation):
==================================================

Since we don't yet have:
- Supply chain layer (components with safety classifications)
- Rich requirement metadata (cvss_threshold, product_scope, deadlines)

We implement a SIMPLE but FUNCTIONAL mapping:

1. HIGH/CRITICAL CVEs (CVSS >= 7.0) violate security-related requirements
2. Map to frameworks that care about vulnerabilities (CRA, FDA, IEC)
3. Use deterministic rules (not AI/heuristics)

Future enhancements (Phase 1C+ with supply chain layer):
- Map based on component safety classification
- Filter by product category (medical, automotive, industrial)
- Use requirement-specific CVSS thresholds
- Include KEV status for criticality

Example Edge Created:
---------------------
{
  "_from": "vulnerabilities/CVE_2024_12345",
  "_to": "regulatory_requirements/CRA_I_1",
  "source": "deterministic",
  "confidence": 1.0,
  "framework": "CRA",
  "severity": "CRITICAL",
  "rationale": "High-severity vulnerability in software component",
  "cvss_score": 9.8,
  "in_kev": false,
  "created_at": "2026-03-06T10:45:00Z"
}

Expected Output:
---------------
~50K edges (122K HIGH/CRITICAL CVEs × ~40% applicable reqs)
"""

import sys
import time
from pathlib import Path
from datetime import datetime, timezone

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from complira_graph.db import get_db


# Mapping rules: Which requirements care about which CVEs
FRAMEWORK_RULES = {
    "CRA": {
        "cvss_threshold": 7.0,
        "applicable_requirement_types": ["essential", "procedural"],
        "rationale_template": "High-severity vulnerability violates CRA essential cybersecurity requirements",
    },
    "FDA_524B": {
        "cvss_threshold": 7.0,
        "applicable_requirement_types": ["essential", "procedural"],
        "rationale_template": "High-severity vulnerability in medical device software",
    },
    "IEC_62304": {
        "cvss_threshold": 7.0,
        "applicable_requirement_types": ["procedural"],  # Skip classifications
        "rationale_template": "Software vulnerability affecting medical device safety",
    },
}


def create_edge_collection(db):
    """Create violates_requirement edge collection if it doesn't exist."""
    from arango import exceptions

    try:
        # Check if collection exists
        if db.has_collection("violates_requirement"):
            print("✅ violates_requirement collection already exists")
            return db.collection("violates_requirement")

        # Create edge collection
        collection = db.create_collection("violates_requirement", edge=True)

        # Add indexes for performance
        collection.add_hash_index(fields=["_from"], unique=False)
        collection.add_hash_index(fields=["_to"], unique=False)
        collection.add_hash_index(fields=["framework"], unique=False)
        collection.add_hash_index(fields=["severity"], unique=False)

        print("✅ Created violates_requirement edge collection with indexes")
        return collection

    except exceptions.CollectionCreateError as e:
        print(f"❌ Failed to create collection: {e}")
        raise


def get_applicable_requirements(db, framework: str, requirement_types: list) -> list:
    """Get requirements from a framework that should be checked for violations."""
    query = """
    FOR r IN regulatory_requirements
      FILTER r.framework == @framework
      FILTER r.requirement_type IN @requirement_types
      RETURN {
        _id: r._id,
        _key: r._key,
        requirement_id: r.requirement_id,
        title: r.title,
        requirement_type: r.requirement_type,
        obligation_level: r.obligation_level,
        deadline: r.deadline
      }
    """

    cursor = db.aql.execute(
        query,
        bind_vars={
            "framework": framework,
            "requirement_types": requirement_types
        }
    )

    return list(cursor)


def get_high_critical_cves(db, cvss_threshold: float, limit: int = None) -> list:
    """Get HIGH/CRITICAL CVEs above threshold."""
    query = """
    FOR v IN vulnerabilities
      FILTER v.cvss_v3_score >= @threshold
      SORT v.cvss_v3_score DESC
      {limit_clause}

      // Check KEV status
      LET cve_id_with_dashes = CONCAT(
        SUBSTRING(v._key, 0, 3), '-',
        SUBSTRING(v._key, 3, 4), '-',
        SUBSTRING(v._key, 7)
      )

      LET in_kev = LENGTH(
        FOR k IN kev_entries
        FILTER k.cve_id == cve_id_with_dashes
        LIMIT 1
        RETURN k
      ) > 0

      RETURN {
        _id: v._id,
        _key: v._key,
        cve_id: v._key,
        cvss_score: v.cvss_v3_score,
        cvss_severity: v.cvss_v3_severity,
        in_kev: in_kev,
        published: v.published_date
      }
    """

    limit_clause = f"LIMIT {limit}" if limit else ""
    query = query.replace("{limit_clause}", limit_clause)

    cursor = db.aql.execute(
        query,
        bind_vars={"threshold": cvss_threshold}
    )

    return list(cursor)


def create_violates_edges(db, cves: list, requirements: list, framework: str, rules: dict) -> int:
    """Create violates_requirement edges in batches."""
    edges = []
    rationale_template = rules["rationale_template"]
    BATCH_SIZE = 10000  # Process 10K edges at a time to avoid connection timeouts
    total_created = 0
    collection = db.collection("violates_requirement")

    for cve in cves:
        cvss_score = cve["cvss_score"]
        in_kev = cve["in_kev"]

        # Determine severity for edge metadata
        if in_kev:
            severity = "CRITICAL"
        elif cvss_score >= 9.0:
            severity = "CRITICAL"
        elif cvss_score >= 7.0:
            severity = "HIGH"
        else:
            severity = "MEDIUM"

        # Map to all applicable requirements in this framework
        for req in requirements:
            edge = {
                "_from": cve["_id"],
                "_to": req["_id"],
                "source": "deterministic",
                "confidence": 1.0,
                "framework": framework,
                "severity": severity,
                "cvss_score": cvss_score,
                "in_kev": in_kev,
                "rationale": rationale_template,
                "requirement_id": req["requirement_id"],
                "requirement_title": req.get("title", ""),
                "created_at": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
            }

            # Add deadline if requirement has one
            if req.get("deadline"):
                edge["remediation_deadline"] = req["deadline"]

            edges.append(edge)

            # Bulk insert when batch is full
            if len(edges) >= BATCH_SIZE:
                result = collection.import_bulk(edges, on_duplicate="ignore")
                total_created += result["created"]
                edges = []  # Clear for next batch

    # Insert remaining edges
    if edges:
        result = collection.import_bulk(edges, on_duplicate="ignore")
        total_created += result["created"]

    return total_created


def main():
    """Main execution flow."""
    print("=" * 80)
    print("🔗 Populate violates_requirement Edge Collection")
    print("=" * 80)
    print()
    print("This implements Path B of the dual-path compliance architecture.")
    print("It maps HIGH/CRITICAL CVEs to regulatory requirements they violate.")
    print()

    # Parse arguments
    import argparse
    parser = argparse.ArgumentParser(description='Populate violates_requirement edges')
    parser.add_argument('--limit', type=int, help='Limit CVEs per framework (for testing)')
    parser.add_argument('--framework', help='Process only specific framework (CRA, FDA_524B, IEC_62304)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be created without creating')
    args = parser.parse_args()

    db = get_db()

    # Step 1: Create edge collection
    print("[1/4] Creating edge collection...")
    create_edge_collection(db)
    print()

    # Step 2: Process each framework
    print("[2/4] Processing frameworks...")
    print()

    frameworks_to_process = [args.framework] if args.framework else list(FRAMEWORK_RULES.keys())

    total_edges_created = 0

    for framework, rules in FRAMEWORK_RULES.items():
        if framework not in frameworks_to_process:
            continue

        print(f"Framework: {framework}")
        print(f"  CVSS threshold: >= {rules['cvss_threshold']}")

        # Get applicable requirements
        requirements = get_applicable_requirements(
            db,
            framework,
            rules["applicable_requirement_types"]
        )

        print(f"  Applicable requirements: {len(requirements)}")

        if len(requirements) == 0:
            print(f"  ⚠️  No applicable requirements found, skipping")
            print()
            continue

        # Get HIGH/CRITICAL CVEs
        cves = get_high_critical_cves(
            db,
            rules["cvss_threshold"],
            limit=args.limit
        )

        print(f"  CVEs to map: {len(cves):,}")

        expected_edges = len(cves) * len(requirements)
        print(f"  Expected edges: ~{expected_edges:,}")

        if args.dry_run:
            print(f"  [DRY RUN] Would create {expected_edges:,} edges")
            print()
            continue

        # Create edges
        print(f"  Creating edges...")
        start_time = time.time()

        edges_created = create_violates_edges(db, cves, requirements, framework, rules)

        elapsed = time.time() - start_time
        print(f"  ✅ Created {edges_created:,} edges in {elapsed:.1f}s")
        print()

        total_edges_created += edges_created

    # Step 3: Summary
    print("[3/4] Summary")
    print("=" * 80)
    print(f"Total edges created: {total_edges_created:,}")

    # Verify edge count
    if not args.dry_run:
        query = "FOR e IN violates_requirement COLLECT WITH COUNT INTO count RETURN count"
        cursor = db.aql.execute(query)
        actual_count = list(cursor)[0]

        print(f"Total edges in collection: {actual_count:,}")

    print()

    # Step 4: Sample query
    print("[4/4] Sample Query")
    print("=" * 80)
    print()
    print("Test the Compliance Passport feature with this query:")
    print()
    print("```aql")
    print("// Find all requirements violated by CVE-2024-21413")
    print("FOR e IN violates_requirement")
    print("  FILTER e._from == 'vulnerabilities/CVE_2024_21413'")
    print("  LET req = DOCUMENT(e._to)")
    print("  RETURN {")
    print("    cve: e._from,")
    print("    requirement: req.requirement_id,")
    print("    framework: e.framework,")
    print("    severity: e.severity,")
    print("    deadline: e.remediation_deadline")
    print("  }")
    print("```")
    print()

    if not args.dry_run:
        print("✅ violates_requirement edge collection populated!")
        print("🎉 Compliance Passport feature is now functional!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
