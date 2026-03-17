#!/usr/bin/env python3
"""
Insert placeholder regulatory requirements for Phase 3A-B testing.

This script inserts 5 placeholder FDA 524B and CRA regulatory requirements
into the regulatory_requirements collection. These placeholders enable
Phase 3A-B development and testing before Phase 4 (Regulatory Framework Integration).

Phase 4 will replace these placeholders with real FDA 524B and CRA requirements.

Usage:
    python scripts/insert_placeholder_requirements.py
"""

from complira_graph.db import get_db
import structlog

logger = structlog.get_logger()


PLACEHOLDER_REQUIREMENTS = [
    {
        "_key": "FDA_524B_KEV_RESPONSE",
        "framework": "FDA_524B",
        "requirement_id": "KEV_RESPONSE",
        "title": "Known Exploited Vulnerability Response",
        "description": (
            "Medical device manufacturers must respond to CISA KEV-listed "
            "vulnerabilities within 24 hours per FDA cybersecurity guidance"
        ),
        "urgency": "24h",
        "source": "FDA Cybersecurity in Medical Devices (524B)",
        "placeholder": True,
        "created_at": "2026-03-05T13:00:00Z",
        "notes": "Placeholder for Phase 3A-B testing. Replace with real FDA 524B requirement in Phase 4."
    },
    {
        "_key": "CRA_CRITICAL_VULNERABILITY",
        "framework": "CRA",
        "requirement_id": "CRITICAL_VULN_NOTIFICATION",
        "title": "Critical Vulnerability Notification",
        "description": (
            "Automotive manufacturers must notify authorities of actively exploited "
            "critical vulnerabilities within 24 hours per EU Cyber Resilience Act"
        ),
        "urgency": "24h",
        "source": "EU Cyber Resilience Act (CRA)",
        "placeholder": True,
        "created_at": "2026-03-05T13:00:00Z",
        "notes": "Placeholder for Phase 3A-B testing. Replace with real CRA requirement in Phase 4."
    },
    {
        "_key": "FDA_524B_CVSS_HIGH",
        "framework": "FDA_524B",
        "requirement_id": "CVSS_HIGH_SEVERITY",
        "title": "CVSS 9.0+ High Severity Vulnerability",
        "description": (
            "Medical device manufacturers must assess high severity vulnerabilities "
            "(CVSS 9.0+) for patient impact and implement mitigations"
        ),
        "urgency": "high",
        "source": "FDA Cybersecurity in Medical Devices (524B)",
        "placeholder": True,
        "created_at": "2026-03-05T13:00:00Z",
        "notes": "Placeholder for Phase 3A-B testing. Replace with real FDA 524B requirement in Phase 4."
    },
    {
        "_key": "CRA_RANSOMWARE_EXPLOITATION",
        "framework": "CRA",
        "requirement_id": "RANSOMWARE_EXPLOITATION",
        "title": "Ransomware Exploitation Detection",
        "description": (
            "Automotive manufacturers must report vulnerabilities actively exploited "
            "by ransomware and implement emergency patches"
        ),
        "urgency": "critical",
        "source": "EU Cyber Resilience Act (CRA)",
        "placeholder": True,
        "created_at": "2026-03-05T13:00:00Z",
        "notes": "Placeholder for Phase 3A-B testing. Replace with real CRA requirement in Phase 4."
    },
    {
        "_key": "CRA_EXPLOIT_CHAIN",
        "framework": "CRA",
        "requirement_id": "EXPLOIT_CHAIN_DETECTION",
        "title": "Multi-CVE Exploit Chain Detection",
        "description": (
            "Automotive manufacturers must identify vulnerabilities used in "
            "multi-CVE attack chains and assess combined impact"
        ),
        "urgency": "critical",
        "source": "EU Cyber Resilience Act (CRA)",
        "placeholder": True,
        "created_at": "2026-03-05T13:00:00Z",
        "notes": "Placeholder for Phase 3A-B testing. Replace with real CRA requirement in Phase 4."
    }
]


def insert_placeholder_requirements() -> int:
    """
    Insert placeholder requirements into regulatory_requirements collection.

    Returns:
        Number of requirements inserted

    Example:
        >>> inserted = insert_placeholder_requirements()
        >>> print(f"Inserted {inserted} placeholder requirements")
    """
    logger.info(
        "Inserting placeholder regulatory requirements",
        count=len(PLACEHOLDER_REQUIREMENTS)
    )

    db = get_db()
    collection = db.collection("regulatory_requirements")

    inserted_count = 0

    for req in PLACEHOLDER_REQUIREMENTS:
        try:
            # Check if requirement already exists
            if collection.has(req["_key"]):
                logger.info(
                    "Placeholder requirement already exists, skipping",
                    key=req["_key"],
                    title=req["title"]
                )
                continue

            # Insert requirement
            collection.insert(req)
            inserted_count += 1

            logger.info(
                "Inserted placeholder requirement",
                key=req["_key"],
                title=req["title"],
                framework=req["framework"],
                urgency=req["urgency"]
            )

        except Exception as e:
            logger.error(
                "Failed to insert placeholder requirement",
                key=req["_key"],
                error=str(e)
            )

    logger.info(
        "Placeholder requirements insertion complete",
        inserted_count=inserted_count,
        total=len(PLACEHOLDER_REQUIREMENTS)
    )

    return inserted_count


def remove_placeholder_requirements() -> int:
    """
    Remove all placeholder requirements.

    Useful for cleanup before Phase 4 real requirement ingestion.

    Returns:
        Number of requirements removed

    Example:
        >>> removed = remove_placeholder_requirements()
        >>> print(f"Removed {removed} placeholder requirements")
    """
    logger.warning("Removing all placeholder regulatory requirements")

    db = get_db()
    collection = db.collection("regulatory_requirements")

    removed_count = 0

    for req in PLACEHOLDER_REQUIREMENTS:
        try:
            if collection.has(req["_key"]):
                collection.delete(req["_key"])
                removed_count += 1

                logger.info(
                    "Removed placeholder requirement",
                    key=req["_key"],
                    title=req["title"]
                )

        except Exception as e:
            logger.error(
                "Failed to remove placeholder requirement",
                key=req["_key"],
                error=str(e)
            )

    logger.info(
        "Placeholder requirements removal complete",
        removed_count=removed_count
    )

    return removed_count


def main():
    """Main entry point for script execution."""
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--remove":
        # Remove placeholders
        removed = remove_placeholder_requirements()
        print(f"✅ Removed {removed} placeholder requirements")
    else:
        # Insert placeholders
        inserted = insert_placeholder_requirements()
        print(f"✅ Inserted {inserted} placeholder requirements")

        if inserted > 0:
            print("\n📝 Next steps:")
            print("   1. Run RegulatoryTriggerService to generate edges")
            print("   2. Test POST /v1/enrich endpoint with CVEs")
            print("   3. Verify regulatory triggers are created")


if __name__ == "__main__":
    main()
