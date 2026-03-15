"""
Control mapping service.

Handles regulatory control mapping logic:
- Map scan findings to regulatory controls (NIST 800-53, FDA 524B, ISO 27001)
- Optionally use compacted view for efficiency
- Batch queries for performance
"""

from typing import List, Dict, Any, Optional
from collections import defaultdict
import structlog

from api.services.base import BaseGraphService
from api.services.compaction import CompactionService
from api.repositories.regulatory import RegulatoryRepository
from complira_graph.models import (
    ControlMapping,
    ControlMappingsResponse,
    ControlStatistics,
    RegulatoryRequirement,
    OSCALControl,
)

logger = structlog.get_logger()


class ControlMappingService(BaseGraphService):
    """
    Service for mapping findings to regulatory controls.

    MVP Design:
    - Support NIST 800-53, FDA 524B, ISO 27001 (D4: Built-in frameworks only)
    - Optionally use compacted view for efficiency
    - Batch queries for performance
    """

    async def map_controls(
        self,
        customer_id: str,
        scan_session_id: str,
        frameworks: List[str],
        use_compacted_view: bool = True,
    ) -> ControlMappingsResponse:
        """
        Map scan findings to regulatory controls.

        Flow:
        1. Get findings (compacted if requested)
        2. Collect unique CWE IDs
        3. Batch query CWE → regulatory requirements
        4. Batch query NIST control details
        5. Build control mappings per finding
        6. Aggregate statistics

        Args:
            customer_id: Customer identifier
            scan_session_id: Scan session _key
            frameworks: List of regulatory frameworks to map to
            use_compacted_view: Use compacted findings (deduplicate + CWE rollup)

        Returns:
            ControlMappingsResponse with control mappings and statistics
        """
        self.logger.info(
            "Starting control mapping",
            customer_id=customer_id,
            scan_session_id=scan_session_id,
            frameworks=frameworks,
            use_compacted_view=use_compacted_view,
        )

        # Step 1: Get findings (compacted if requested)
        if use_compacted_view:
            compaction_service = CompactionService(self.db, self.cache)
            compact_response = await compaction_service.compact_findings(
                customer_id=customer_id,
                scan_session_id=scan_session_id,
                deduplication_strategy="by_cve",
                cwe_rollup_level="Class",
            )
            compacted_findings = compact_response.compacted_findings

            self.logger.debug(
                "Using compacted findings",
                compacted_count=len(compacted_findings)
            )
        else:
            # Get raw findings
            from api.core.database import get_customer_db
            from api.repositories.scan import ScanFindingRepository

            customer_db = get_customer_db(customer_id)
            finding_repo = ScanFindingRepository(customer_db)

            findings = finding_repo.list_session_findings(
                customer_id=customer_id,
                scan_session_id=scan_session_id,
                limit=10000,
            )

            # Convert to compacted format for uniform processing
            compacted_findings = [
                self._convert_finding_to_compacted(f)
                for f in findings
            ]

            self.logger.debug(
                "Using raw findings",
                findings_count=len(compacted_findings)
            )

        if not compacted_findings:
            self.logger.info("No findings to map", scan_session_id=scan_session_id)
            return ControlMappingsResponse(
                scan_session_id=scan_session_id,
                frameworks=frameworks,
                control_mappings=[],
                control_statistics=ControlStatistics(
                    total_findings_mapped=0,
                    total_nist_controls=0,
                    total_fda_requirements=0,
                    total_iso_requirements=0,
                    coverage_percentage={},
                ),
                used_compacted_view=use_compacted_view,
            )

        # Step 2: Collect unique CWE IDs
        all_cwe_ids = set()
        for finding in compacted_findings:
            all_cwe_ids.update(finding.cwe_ids)

        self.logger.debug(
            "Collected CWE IDs",
            unique_cwe_count=len(all_cwe_ids)
        )

        # Step 3: Batch query CWE → regulatory requirements
        from api.core.database import get_reference_db
        reference_db = get_reference_db()
        regulatory_repo = RegulatoryRepository(reference_db)

        cwe_to_requirements = regulatory_repo.batch_get_requirements_for_cwes(
            cwe_ids=list(all_cwe_ids),
            frameworks=frameworks,
        )

        self.logger.debug(
            "Fetched CWE → requirements mappings",
            mapped_cwe_count=len(cwe_to_requirements)
        )

        # Step 4: Batch query NIST control details (if NIST in frameworks)
        nist_control_map = {}
        if "NIST 800-53" in frameworks:
            # Collect all NIST requirement IDs
            nist_req_ids = set()
            for requirements in cwe_to_requirements.values():
                for req in requirements:
                    if req.framework == "NIST 800-53":
                        nist_req_ids.add(req.requirement_id)

            if nist_req_ids:
                nist_control_map = regulatory_repo.batch_get_nist_controls(
                    requirement_ids=list(nist_req_ids)
                )

            self.logger.debug(
                "Fetched NIST controls",
                control_count=len(nist_control_map)
            )

        # Step 5: Build control mappings per finding
        control_mappings = []

        for finding in compacted_findings:
            finding_id = finding.vulnerability_id or f"non_cve_{hash(tuple(finding.affected_locations))}"

            # Aggregate requirements for all CWEs in this finding
            nist_controls = []
            fda_requirements = []
            iso_requirements = []

            for cwe_id in finding.cwe_ids:
                requirements = cwe_to_requirements.get(cwe_id, [])

                for req in requirements:
                    if req.framework == "NIST 800-53":
                        # Get control details
                        control = nist_control_map.get(req.requirement_id)
                        if control and control not in nist_controls:
                            nist_controls.append(control)
                    elif req.framework == "FDA 524B":
                        if req not in fda_requirements:
                            fda_requirements.append(req)
                    elif req.framework == "ISO 27001":
                        if req not in iso_requirements:
                            iso_requirements.append(req)

            control_mappings.append(
                ControlMapping(
                    finding_id=finding_id,
                    cwe_ids=finding.cwe_ids,
                    nist_controls=nist_controls,
                    fda_requirements=fda_requirements,
                    iso_requirements=iso_requirements,
                )
            )

        # Step 6: Aggregate statistics
        total_findings_mapped = len(control_mappings)

        unique_nist_controls = set()
        unique_fda_requirements = set()
        unique_iso_requirements = set()

        nist_mapped_count = 0
        fda_mapped_count = 0
        iso_mapped_count = 0

        for mapping in control_mappings:
            if mapping.nist_controls:
                nist_mapped_count += 1
                unique_nist_controls.update(c.control_id for c in mapping.nist_controls)

            if mapping.fda_requirements:
                fda_mapped_count += 1
                unique_fda_requirements.update(r.requirement_id for r in mapping.fda_requirements)

            if mapping.iso_requirements:
                iso_mapped_count += 1
                unique_iso_requirements.update(r.requirement_id for r in mapping.iso_requirements)

        coverage_percentage = {}
        if "NIST 800-53" in frameworks:
            coverage_percentage["NIST 800-53"] = (
                (nist_mapped_count / total_findings_mapped * 100)
                if total_findings_mapped > 0 else 0.0
            )
        if "FDA 524B" in frameworks:
            coverage_percentage["FDA 524B"] = (
                (fda_mapped_count / total_findings_mapped * 100)
                if total_findings_mapped > 0 else 0.0
            )
        if "ISO 27001" in frameworks:
            coverage_percentage["ISO 27001"] = (
                (iso_mapped_count / total_findings_mapped * 100)
                if total_findings_mapped > 0 else 0.0
            )

        self.logger.info(
            "Control mapping complete",
            total_findings=total_findings_mapped,
            nist_controls=len(unique_nist_controls),
            fda_requirements=len(unique_fda_requirements),
            iso_requirements=len(unique_iso_requirements),
        )

        return ControlMappingsResponse(
            scan_session_id=scan_session_id,
            frameworks=frameworks,
            control_mappings=control_mappings,
            control_statistics=ControlStatistics(
                total_findings_mapped=total_findings_mapped,
                total_nist_controls=len(unique_nist_controls),
                total_fda_requirements=len(unique_fda_requirements),
                total_iso_requirements=len(unique_iso_requirements),
                coverage_percentage=coverage_percentage,
            ),
            used_compacted_view=use_compacted_view,
        )

    def _convert_finding_to_compacted(self, finding) -> Any:
        """
        Convert raw ScanFinding to CompactedFinding format.

        Args:
            finding: ScanFinding model

        Returns:
            CompactedFinding-like object (for uniform processing)
        """
        from complira_graph.models import CompactedFinding

        # Extract CWE IDs from raw_data
        cwe_ids = finding.raw_data.get('cwe_ids', []) if finding.raw_data else []

        return CompactedFinding(
            vulnerability_id=finding.cve_id,
            severity=finding.severity,
            occurrences=1,
            affected_locations=[{"file": finding.location, "tool": finding.tool_name}],
            cwe_ids=cwe_ids,
            original_cwe_ids=cwe_ids,
        )
