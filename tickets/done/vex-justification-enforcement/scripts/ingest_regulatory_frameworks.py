#!/usr/bin/env python3
"""
Ingest FDA 524B and EU CRA regulatory requirements.

This script ingests regulatory frameworks from YAML files using the
YAMLRegulatoryAgent. It supports both FDA Section 524B (Medical Device
Cybersecurity) and EU Cyber Resilience Act (CRA) requirements.

Usage:
    # Ingest both FDA and CRA (default)
    python scripts/ingest_regulatory_frameworks.py

    # Ingest only FDA 524B
    python scripts/ingest_regulatory_frameworks.py --frameworks FDA_524B

    # Ingest only CRA
    python scripts/ingest_regulatory_frameworks.py --frameworks CRA

    # Ingest multiple frameworks
    python scripts/ingest_regulatory_frameworks.py --frameworks FDA_524B,CRA

    # Dry run (validation only, no database changes)
    python scripts/ingest_regulatory_frameworks.py --dry-run

Exit Codes:
    0: Success (all frameworks ingested without errors)
    1: Failure (errors during ingestion or validation)

Examples:
    # Full ingestion
    python scripts/ingest_regulatory_frameworks.py

    # Validate YAMLs without ingesting
    python scripts/ingest_regulatory_frameworks.py --dry-run

    # Ingest FDA only
    python scripts/ingest_regulatory_frameworks.py --frameworks FDA_524B
"""

import argparse
import sys
import time
from datetime import datetime
from typing import List, Dict, Any

from complira_graph.db import get_db
from complira_graph.agents.yaml_regulatory import YAMLRegulatoryAgent


# Default frameworks to ingest
DEFAULT_FRAMEWORKS = ["FDA_524B", "CRA"]


def ingest_framework(framework_key: str, db, dry_run: bool = False) -> Dict[str, Any]:
    """
    Ingest a single regulatory framework.

    Args:
        framework_key: Framework identifier (e.g., "FDA_524B", "CRA")
        db: ArangoDB database connection
        dry_run: If True, validate only without database changes

    Returns:
        dict: Ingestion statistics
            {
                "framework": str,
                "status": "success" | "failed",
                "created": int,
                "updated": int,
                "errors": int,
                "execution_time_seconds": float,
                "error": str (if failed)
            }

    Raises:
        Exception: If ingestion fails (dry_run=False)
    """
    start_time = datetime.now()

    try:
        # Create agent instance
        agent = YAMLRegulatoryAgent(db, framework_key=framework_key)

        if dry_run:
            # Dry-run mode: validate only (fetch + transform, skip load)
            print(f"[DRY-RUN] Validating {framework_key}...")

            # Fetch and validate YAML
            raw_data = agent.fetch_data()

            if not raw_data:
                print(f"[DRY-RUN] ⚠️  No data found for {framework_key}")
                return {
                    "framework": framework_key,
                    "status": "success",
                    "would_create": 0,
                    "validation": "passed_empty",
                    "execution_time_seconds": (datetime.now() - start_time).total_seconds(),
                }

            # Transform data (validate models can be created)
            documents = agent.transform_data(raw_data)

            # Count documents by collection
            framework_count = sum(1 for doc in documents if doc.get("_collection") == "regulatory_frameworks")
            requirement_count = sum(1 for doc in documents if doc.get("_collection") == "regulatory_requirements")

            execution_time = (datetime.now() - start_time).total_seconds()

            print(f"[DRY-RUN] ✅ {framework_key} validation passed")
            print(f"[DRY-RUN]   Would create {framework_count} framework(s) and {requirement_count} requirement(s)")
            print(f"[DRY-RUN]   Validation time: {execution_time:.2f}s")

            return {
                "framework": framework_key,
                "status": "dry_run_success",
                "would_create": len(documents),
                "would_create_frameworks": framework_count,
                "would_create_requirements": requirement_count,
                "validation": "passed",
                "execution_time_seconds": execution_time,
            }

        else:
            # Full ingestion mode
            print(f"Ingesting {framework_key}...")

            # Run agent (fetch + transform + load)
            result = agent.run()

            execution_time = (datetime.now() - start_time).total_seconds()

            # Add framework key to result
            result["framework"] = framework_key
            result["execution_time_seconds"] = execution_time

            if result.get("status") == "success":
                created = result.get("created", 0)
                updated = result.get("updated", 0)
                print(f"✅ {framework_key}: {created} created, {updated} updated ({execution_time:.2f}s)")
            else:
                print(f"❌ {framework_key} failed: {result.get('error', 'Unknown error')}")

            return result

    except Exception as e:
        execution_time = (datetime.now() - start_time).total_seconds()

        error_msg = f"Error ingesting {framework_key}: {str(e)}"
        print(f"❌ {error_msg}")

        return {
            "framework": framework_key,
            "status": "failed",
            "error": str(e),
            "created": 0,
            "updated": 0,
            "errors": 1,
            "execution_time_seconds": execution_time,
        }


def print_summary(results: List[Dict[str, Any]], dry_run: bool = False):
    """
    Print summary statistics for all frameworks.

    Args:
        results: List of ingestion results (one per framework)
        dry_run: If True, print dry-run summary
    """
    print("\n" + "=" * 60)

    if dry_run:
        print("DRY-RUN SUMMARY")
    else:
        print("INGESTION SUMMARY")

    print("=" * 60)

    # Calculate totals
    total_created = sum(r.get("created", 0) for r in results)
    total_updated = sum(r.get("updated", 0) for r in results)
    total_errors = sum(r.get("errors", 0) for r in results)
    total_time = sum(r.get("execution_time_seconds", 0) for r in results)

    successful = sum(1 for r in results if r.get("status") in ["success", "dry_run_success"])
    failed = len(results) - successful

    # Print per-framework results
    for result in results:
        framework = result.get("framework", "Unknown")
        status = result.get("status", "unknown")

        if dry_run:
            would_create = result.get("would_create", 0)
            validation = result.get("validation", "unknown")
            print(f"  {framework}: {validation} (would create {would_create} documents)")
        else:
            created = result.get("created", 0)
            updated = result.get("updated", 0)
            errors = result.get("errors", 0)

            if status == "success":
                print(f"  {framework}: ✅ {created} created, {updated} updated")
            else:
                print(f"  {framework}: ❌ {errors} errors - {result.get('error', 'Unknown error')}")

    # Print totals
    print("-" * 60)

    if dry_run:
        total_would_create = sum(r.get("would_create", 0) for r in results)
        print(f"Total: {len(results)} frameworks validated")
        print(f"Would create: {total_would_create} documents")
        print(f"Validation time: {total_time:.2f}s")
        print(f"All validations passed: {'✅ YES' if failed == 0 else '❌ NO'}")
    else:
        print(f"Total: {len(results)} frameworks")
        print(f"  Created: {total_created} documents")
        print(f"  Updated: {total_updated} documents")
        print(f"  Errors: {total_errors}")
        print(f"  Execution time: {total_time:.2f}s")
        print(f"  Success rate: {successful}/{len(results)} frameworks")

    print("=" * 60)


def main():
    """
    Main entry point for regulatory framework ingestion.

    Parses CLI arguments and runs ingestion for specified frameworks.
    """
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Ingest FDA 524B and EU CRA regulatory requirements from YAML files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Ingest both FDA and CRA (default)
  %(prog)s

  # Ingest only FDA 524B
  %(prog)s --frameworks FDA_524B

  # Dry run (validation only)
  %(prog)s --dry-run

  # Ingest specific frameworks
  %(prog)s --frameworks FDA_524B,CRA
        """
    )

    parser.add_argument(
        "--frameworks",
        type=str,
        default=",".join(DEFAULT_FRAMEWORKS),
        help=f"Comma-separated list of frameworks to ingest (default: {','.join(DEFAULT_FRAMEWORKS)})"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate YAML files without making database changes"
    )

    args = parser.parse_args()

    # Parse frameworks list
    frameworks = [f.strip() for f in args.frameworks.split(",") if f.strip()]

    if not frameworks:
        print("❌ Error: No frameworks specified")
        sys.exit(1)

    # Initialize database connection
    try:
        db = get_db()
        print(f"✅ Connected to database: {db.name}")
    except Exception as e:
        print(f"❌ Error: Failed to connect to database: {e}")
        print("   Is ArangoDB running? (http://localhost:8529)")
        sys.exit(1)

    # Print header
    print("\n" + "=" * 60)
    if args.dry_run:
        print("REGULATORY FRAMEWORK VALIDATION (DRY-RUN)")
    else:
        print("REGULATORY FRAMEWORK INGESTION")
    print("=" * 60)
    print(f"Frameworks: {', '.join(frameworks)}")
    print(f"Mode: {'Dry-run (validation only)' if args.dry_run else 'Full ingestion'}")
    print("=" * 60 + "\n")

    # Ingest each framework
    results = []
    for framework_key in frameworks:
        result = ingest_framework(framework_key, db, dry_run=args.dry_run)
        results.append(result)

    # Print summary
    print_summary(results, dry_run=args.dry_run)

    # Exit with appropriate code
    failed_count = sum(1 for r in results if r.get("status") not in ["success", "dry_run_success"])

    if failed_count > 0:
        print(f"\n❌ Ingestion completed with {failed_count} failure(s)")
        sys.exit(1)
    else:
        if args.dry_run:
            print("\n✅ All validations passed")
        else:
            print("\n✅ Ingestion completed successfully")
        sys.exit(0)


if __name__ == "__main__":
    main()
