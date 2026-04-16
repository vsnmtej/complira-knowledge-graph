"""
Compaction service.

Handles finding compaction logic:
- Deduplicate findings by CVE
- Roll up CWEs to higher abstraction levels (Class, Pillar)
- Read-only (MVP decision D2 - does not modify scan_findings)
"""

from typing import List, Dict, Any
from collections import defaultdict
import structlog

from api.services.base import BaseGraphService
from api.repositories.scan import ScanFindingRepository
from api.repositories.cwe import CWERepository
from complira_graph.models import (
    ScanFinding,
    CompactedFinding,
    CompactResponse,
    CompactionMetadata,
)

logger = structlog.get_logger()


class CompactionService(BaseGraphService):
    """
    Service for compacting scan findings.

    MVP Design (D2: Read-only compaction):
    - Return compacted view without modifying database
    - Deduplicate by CVE ID
    - Roll up CWEs to target abstraction level
    """

    async def compact_findings(
        self,
        customer_id: str,
        scan_session_id: str,
        deduplication_strategy: str = "by_cve",
        cwe_rollup_level: str = "Class",
    ) -> CompactResponse:
        """
        Compact scan findings (deduplicate + CWE rollup).

        Flow:
        1. Get scan findings from customer DB
        2. Deduplicate by CVE ID (group by CVE, aggregate locations)
        3. Roll up CWEs to target abstraction level
        4. Return compacted view (does not modify database)

        Args:
            customer_id: Customer identifier
            scan_session_id: Scan session _key
            deduplication_strategy: Deduplication strategy ("by_cve")
            cwe_rollup_level: CWE abstraction level ("Class" or "Pillar")

        Returns:
            CompactResponse with compacted findings and metadata
        """
        self.logger.info(
            "Starting finding compaction",
            customer_id=customer_id,
            scan_session_id=scan_session_id,
            strategy=deduplication_strategy,
            rollup_level=cwe_rollup_level,
        )

        # Step 1: Get scan findings from customer DB
        from api.core.database import get_customer_db
        customer_db = get_customer_db(customer_id)
        finding_repo = ScanFindingRepository(customer_db)

        findings = finding_repo.list_session_findings(
            customer_id=customer_id,
            scan_session_id=scan_session_id,
            limit=10000,  # MVP: No pagination
        )

        if not findings:
            self.logger.info("No findings to compact", scan_session_id=scan_session_id)
            return CompactResponse(
                scan_session_id=scan_session_id,
                original_finding_count=0,
                compacted_finding_count=0,
                reduction_percentage=0.0,
                compacted_findings=[],
                compaction_metadata=CompactionMetadata(
                    deduplication_strategy=deduplication_strategy,
                    cwe_rollup_level=cwe_rollup_level,
                    original_cwe_count=0,
                    rolled_up_cwe_count=0,
                    cwe_reduction_percentage=0.0,
                ),
            )

        original_finding_count = len(findings)

        self.logger.debug(
            "Fetched findings from customer DB",
            findings_count=original_finding_count
        )

        # Step 2: Deduplicate by CVE ID
        if deduplication_strategy == "by_cve":
            compacted_findings = self._deduplicate_by_cve(findings)
        else:
            # Future: Support other strategies
            raise ValueError(f"Unsupported deduplication strategy: {deduplication_strategy}")

        # Collect all unique CWE IDs from compacted findings
        all_cwe_ids = set()
        for compacted in compacted_findings:
            all_cwe_ids.update(compacted.cwe_ids)

        original_cwe_count = len(all_cwe_ids)

        self.logger.debug(
            "Deduplication complete",
            original_count=original_finding_count,
            compacted_count=len(compacted_findings),
            unique_cwe_count=original_cwe_count
        )

        # Step 3: Roll up CWEs to target abstraction level
        if all_cwe_ids:
            from api.core.database import get_reference_db
            reference_db = get_reference_db()
            cwe_repo = CWERepository(reference_db)

            cwe_rollup_map = cwe_repo.batch_rollup_to_abstraction_level(
                cwe_ids=list(all_cwe_ids),
                target_level=cwe_rollup_level,
            )

            # Apply rollup to compacted findings
            for compacted in compacted_findings:
                original_cwes = compacted.cwe_ids.copy()
                rolled_up_cwes = set()

                for cwe_id in original_cwes:
                    rolled_up_cwe = cwe_rollup_map.get(cwe_id)
                    if rolled_up_cwe:
                        rolled_up_cwes.add(rolled_up_cwe.cwe_id)
                    else:
                        # Keep original if rollup not found
                        rolled_up_cwes.add(cwe_id)

                compacted.original_cwe_ids = original_cwes
                compacted.cwe_ids = list(rolled_up_cwes)

            # Count unique rolled-up CWEs
            rolled_up_cwe_count = len(set(
                cwe_id
                for compacted in compacted_findings
                for cwe_id in compacted.cwe_ids
            ))
        else:
            rolled_up_cwe_count = 0

        self.logger.debug(
            "CWE rollup complete",
            original_cwe_count=original_cwe_count,
            rolled_up_cwe_count=rolled_up_cwe_count
        )

        # Step 4: Build response
        compacted_finding_count = len(compacted_findings)
        reduction_percentage = (
            ((original_finding_count - compacted_finding_count) / original_finding_count * 100)
            if original_finding_count > 0 else 0.0
        )

        cwe_reduction_percentage = (
            ((original_cwe_count - rolled_up_cwe_count) / original_cwe_count * 100)
            if original_cwe_count > 0 else 0.0
        )

        self.logger.info(
            "Finding compaction complete",
            original_count=original_finding_count,
            compacted_count=compacted_finding_count,
            reduction_pct=f"{reduction_percentage:.1f}%",
            cwe_reduction_pct=f"{cwe_reduction_percentage:.1f}%",
        )

        return CompactResponse(
            scan_session_id=scan_session_id,
            original_finding_count=original_finding_count,
            compacted_finding_count=compacted_finding_count,
            reduction_percentage=reduction_percentage,
            compacted_findings=compacted_findings,
            compaction_metadata=CompactionMetadata(
                deduplication_strategy=deduplication_strategy,
                cwe_rollup_level=cwe_rollup_level,
                original_cwe_count=original_cwe_count,
                rolled_up_cwe_count=rolled_up_cwe_count,
                cwe_reduction_percentage=cwe_reduction_percentage,
            ),
        )

    def _deduplicate_by_cve(self, findings: List[ScanFinding]) -> List[CompactedFinding]:
        """
        Deduplicate findings by CVE ID.

        Groups findings by CVE ID and aggregates locations.

        Args:
            findings: List of scan findings

        Returns:
            List of compacted findings
        """
        cve_groups = defaultdict(list)

        for finding in findings:
            if finding.cve_id:
                cve_groups[finding.cve_id].append(finding)
            else:
                # Non-CVE findings are not deduplicated (keep as-is)
                cve_groups[f"_non_cve_{finding._key}"].append(finding)

        compacted_findings = []

        for group_key, group_findings in cve_groups.items():
            # Use first finding as representative
            first_finding = group_findings[0]

            # Extract locations from all findings in group
            affected_locations = []
            for finding in group_findings:
                affected_locations.append({
                    "file": finding.location,
                    "tool": finding.tool_name,
                })

            # Extract CWE IDs from raw_data
            cwe_ids = set()
            for finding in group_findings:
                if 'cwe_ids' in finding.raw_data:
                    cwe_ids.update(finding.raw_data['cwe_ids'])

            compacted_findings.append(
                CompactedFinding(
                    vulnerability_id=first_finding.cve_id,
                    severity=first_finding.severity,
                    occurrences=len(group_findings),
                    affected_locations=affected_locations,
                    cwe_ids=list(cwe_ids),
                    original_cwe_ids=list(cwe_ids),  # Will be updated by rollup
                )
            )

        return compacted_findings
