"""
VEX Statement Generator.

Generates VEX (Vulnerability Exploitability eXchange) statements for individual
vulnerabilities, with scanner-assisted status short-circuiting.

Architecture:
- Status Assessment: Scanner VEX hint → immediate status; None → evidence heuristics
- Action Generation: LLM service (if provided) → template fallback
- SOLID: SRP (status logic separate from action logic), DIP (llm_service optional)

Scanner VEX Status Flow:
    Grype fix.state="fixed"      → VEXStatus.FIXED     (skip LLM)
    Grype fix.state="wont-fix"   → VEXStatus.AFFECTED  (skip LLM)
    Grype fix.state="not-fixed"  → VEXStatus.AFFECTED  (skip LLM)
    Grype fix.state=None/unknown → evidence heuristics → optional LLM

Usage:
    from api.services.vex_statement_generator import VEXStatementGenerator

    # With LLM (full capability)
    generator = VEXStatementGenerator(llm_service=synthesizer)

    # Without LLM (template-based only)
    generator = VEXStatementGenerator()

    status = generator._assess_vulnerability_status(finding_dict, evidence)
    action = generator._create_action_statement(finding_dict, evidence, status)
"""

import asyncio
from typing import Dict, Any, Optional
import structlog

from complira_graph.models.vex_evidence import (
    VulnerabilityEvidence,
    VEXStatus,
)

logger = structlog.get_logger()


# Scanner fix.state → VEXStatus short-circuit map
_SCANNER_STATUS_MAP: Dict[str, VEXStatus] = {
    "fixed": VEXStatus.FIXED,
    "affected": VEXStatus.AFFECTED,
    "wont-fix": VEXStatus.AFFECTED,
    "not-fixed": VEXStatus.AFFECTED,
    # "unknown" / None → fall through to heuristics
}


class VEXStatementGenerator:
    """
    Generates VEX statements for individual vulnerability findings.

    Combines scanner-provided VEX hints (from Grype's fix.state) with
    evidence-based heuristics and optional LLM enrichment to produce
    VEX status and action statements.

    Status Assessment Priority:
        1. scanner_vex_status (from finding.raw_data) — deterministic, skip LLM
        2. Evidence heuristics (component presence, KEV, EPSS)
        3. Conservative fallback (under_investigation)

    Action Statement Priority:
        1. LLM service (if provided and status warrants it)
        2. Template-based fallback (deterministic, no API cost)

    Example:
        >>> generator = VEXStatementGenerator(llm_service=synthesizer)
        >>> status = generator._assess_vulnerability_status(finding, evidence)
        >>> action = generator._create_action_statement(finding, evidence, status)
    """

    def __init__(self, llm_service=None):
        """
        Initialize VEX statement generator.

        Args:
            llm_service: Optional LLM service for action statement generation.
                         Accepts VEXSynthesizerV2 or any service with a
                         `synthesize_vex(evidence, component_purl)` coroutine.
                         If None, uses template-based action statements.
        """
        self.llm_service = llm_service
        self.logger = structlog.get_logger(service="VEXStatementGenerator")

        self.logger.info(
            "VEXStatementGenerator initialized",
            llm_enabled=llm_service is not None,
        )

    # ========================================================================
    # STATUS ASSESSMENT
    # ========================================================================

    def _assess_vulnerability_status(
        self,
        vulnerability_dict: Dict[str, Any],
        evidence: VulnerabilityEvidence,
    ) -> VEXStatus:
        """
        Determine VEX status for a vulnerability, with scanner hint short-circuit.

        Priority:
            1. scanner_vex_status from vulnerability_dict (from Grype fix.state)
               - "fixed"      → VEXStatus.FIXED     (scanner knows it's patched)
               - "affected"   → VEXStatus.AFFECTED  (scanner confirms exploitable)
               - "wont-fix"   → VEXStatus.AFFECTED  (fix exists, won't be applied)
               - "not-fixed"  → VEXStatus.AFFECTED  (no fix yet)
            2. Evidence heuristics (component presence, KEV, EPSS, CVSS)
            3. Conservative fallback: UNDER_INVESTIGATION

        Args:
            vulnerability_dict: Finding dict with optional scanner_vex_status field.
                                 Typically finding.get("raw_data", {}) from the DB.
            evidence: Complete VulnerabilityEvidence package from graph traversal.

        Returns:
            VEXStatus: Assessed VEX status

        Example:
            >>> finding = {"cve_id": "CVE-2023-1234", "raw_data": {"scanner_vex_status": "fixed"}}
            >>> status = generator._assess_vulnerability_status(finding, evidence)
            >>> status
            VEXStatus.FIXED
        """
        # Step 1: Scanner VEX status short-circuit
        scanner_vex_status = vulnerability_dict.get("scanner_vex_status")
        if scanner_vex_status is None:
            # Also check inside raw_data (finding stored in DB has raw_data wrapper)
            raw_data = vulnerability_dict.get("raw_data", {})
            scanner_vex_status = raw_data.get("scanner_vex_status") if isinstance(raw_data, dict) else None

        if scanner_vex_status and scanner_vex_status in _SCANNER_STATUS_MAP:
            status = _SCANNER_STATUS_MAP[scanner_vex_status]
            self.logger.debug(
                "Scanner VEX status short-circuit",
                cve_id=vulnerability_dict.get("cve_id"),
                scanner_vex_status=scanner_vex_status,
                vex_status=status.value,
            )
            return status

        # Step 2: Evidence heuristics
        return self._heuristic_status(vulnerability_dict, evidence)

    def _heuristic_status(
        self,
        vulnerability_dict: Dict[str, Any],
        evidence: VulnerabilityEvidence,
    ) -> VEXStatus:
        """
        Determine VEX status from evidence heuristics when scanner hint is absent.

        Heuristics (in priority order):
            1. Component not in SBOM → NOT_AFFECTED (component_not_present)
            2. In CISA KEV catalog   → AFFECTED (actively exploited in wild)
            3. EPSS ≥ 0.5 (50%)     → AFFECTED (high exploitation probability)
            4. CVSS ≥ 9.0 (Critical) → AFFECTED (critical severity)
            5. CVSS ≥ 7.0 (High)    → AFFECTED (high severity)
            6. Default              → UNDER_INVESTIGATION

        Args:
            vulnerability_dict: Finding dict
            evidence: VulnerabilityEvidence package

        Returns:
            VEXStatus: Heuristic-based status
        """
        graph = evidence.graph_evidence

        # Heuristic 1: Component not present in SBOM
        if not graph.component_presence.in_sbom:
            self.logger.debug(
                "Heuristic: component not in SBOM → not_affected",
                cve_id=vulnerability_dict.get("cve_id"),
            )
            return VEXStatus.NOT_AFFECTED

        # Heuristic 2: In CISA KEV (actively exploited in wild)
        if graph.kev_evidence.in_kev:
            self.logger.debug(
                "Heuristic: in KEV catalog → affected",
                cve_id=vulnerability_dict.get("cve_id"),
            )
            return VEXStatus.AFFECTED

        # Heuristic 3: High EPSS score (≥50% exploit probability)
        epss_score = graph.exploitability.epss_score
        if epss_score is not None and epss_score >= 0.5:
            self.logger.debug(
                "Heuristic: high EPSS → affected",
                cve_id=vulnerability_dict.get("cve_id"),
                epss_score=epss_score,
            )
            return VEXStatus.AFFECTED

        # Heuristic 4: Critical CVSS score (≥9.0)
        cvss = evidence.cve_metadata.cvss_v3_score
        if cvss is not None and cvss >= 9.0:
            self.logger.debug(
                "Heuristic: critical CVSS → affected",
                cve_id=vulnerability_dict.get("cve_id"),
                cvss_v3_score=cvss,
            )
            return VEXStatus.AFFECTED

        # Heuristic 5: High CVSS score (≥7.0)
        if cvss is not None and cvss >= 7.0:
            self.logger.debug(
                "Heuristic: high CVSS → affected",
                cve_id=vulnerability_dict.get("cve_id"),
                cvss_v3_score=cvss,
            )
            return VEXStatus.AFFECTED

        # Default: under investigation (conservative)
        self.logger.debug(
            "Heuristic: insufficient evidence → under_investigation",
            cve_id=vulnerability_dict.get("cve_id"),
        )
        return VEXStatus.UNDER_INVESTIGATION

    # ========================================================================
    # ACTION STATEMENT
    # ========================================================================

    def _create_action_statement(
        self,
        vulnerability_dict: Dict[str, Any],
        evidence: VulnerabilityEvidence,
        status: VEXStatus,
    ) -> str:
        """
        Generate VEX action statement. Dispatches to LLM or template fallback.

        Dispatch logic:
            - LLM service available AND status is AFFECTED/UNDER_INVESTIGATION
              → `_generate_llm_action_statement` (richer, context-aware)
            - Otherwise
              → `_template_action_statement` (deterministic, no API cost)

        Args:
            vulnerability_dict: Finding dict (may include scanner_vex_status)
            evidence: VulnerabilityEvidence package
            status: Assessed VEX status

        Returns:
            str: Human-readable action statement for the VEX document
        """
        # Only use LLM for statuses that benefit from richer analysis
        use_llm = (
            self.llm_service is not None
            and status in (VEXStatus.AFFECTED, VEXStatus.UNDER_INVESTIGATION)
        )

        if use_llm:
            try:
                return self._run_async(
                    self._generate_llm_action_statement(vulnerability_dict, evidence, status)
                )
            except Exception as e:
                self.logger.warning(
                    "LLM action statement failed, falling back to template",
                    cve_id=vulnerability_dict.get("cve_id"),
                    error=str(e),
                )

        return self._template_action_statement(vulnerability_dict, evidence, status)

    async def _generate_llm_action_statement(
        self,
        vulnerability_dict: Dict[str, Any],
        evidence: VulnerabilityEvidence,
        status: VEXStatus,
    ) -> str:
        """
        Generate action statement using LLM service (async).

        Delegates to llm_service.synthesize_vex() and extracts the
        mitigation_recommendations as the action statement.

        Args:
            vulnerability_dict: Finding dict
            evidence: VulnerabilityEvidence package
            status: Assessed VEX status (for context)

        Returns:
            str: LLM-generated action statement

        Raises:
            Exception: If LLM call fails (caller falls back to template)
        """
        cve_id = vulnerability_dict.get("cve_id", "unknown")
        component_purl = vulnerability_dict.get("location") or vulnerability_dict.get("artifact_purl", "unknown")

        self.logger.debug(
            "Generating LLM action statement",
            cve_id=cve_id,
            vex_status=status.value,
        )

        assessment = await self.llm_service.synthesize_vex(
            evidence=evidence,
            component_purl=component_purl,
        )

        # Extract action statement from assessment
        if assessment.mitigation_recommendations:
            return "; ".join(assessment.mitigation_recommendations[:3])
        elif assessment.impact_summary:
            return assessment.impact_summary

        return self._template_action_statement(vulnerability_dict, evidence, status)

    def _template_action_statement(
        self,
        vulnerability_dict: Dict[str, Any],
        evidence: VulnerabilityEvidence,
        status: VEXStatus,
    ) -> str:
        """
        Generate deterministic template-based action statement.

        Produces actionable statements without LLM API calls, based on
        scanner VEX status, evidence data, and fix availability.

        Template logic:
            FIXED:
                - "Update to {fix_version}" if fix version known
                - "Upgrade to patched version" otherwise
            NOT_AFFECTED:
                - "Component not in SBOM" or "Vulnerable code not in execution path"
            AFFECTED + KEV:
                - Urgent remediation with CISA deadline if available
            AFFECTED + EPSS:
                - Risk-quantified remediation recommendation
            UNDER_INVESTIGATION:
                - Assessment in progress notice

        Args:
            vulnerability_dict: Finding dict (may include fix_versions)
            evidence: VulnerabilityEvidence package
            status: Assessed VEX status

        Returns:
            str: Template-generated action statement
        """
        cve_id = vulnerability_dict.get("cve_id", "unknown CVE")
        graph = evidence.graph_evidence
        raw_data = vulnerability_dict.get("raw_data", vulnerability_dict)
        fix_versions = raw_data.get("fix_versions", []) if isinstance(raw_data, dict) else []

        if status == VEXStatus.FIXED:
            if fix_versions:
                return (
                    f"Update affected component to fixed version "
                    f"{', '.join(fix_versions)} to remediate {cve_id}."
                )
            return f"Upgrade affected component to the latest patched version to remediate {cve_id}."

        if status == VEXStatus.NOT_AFFECTED:
            if not graph.component_presence.in_sbom:
                return (
                    f"Component is not present in the SBOM. "
                    f"{cve_id} does not affect this product."
                )
            return (
                f"Vulnerable code path is not reachable in this deployment. "
                f"{cve_id} does not affect this product."
            )

        if status == VEXStatus.AFFECTED:
            parts = []

            # KEV urgency
            if graph.kev_evidence.in_kev:
                due_date = graph.kev_evidence.kev_due_date
                required_action = graph.kev_evidence.kev_required_action
                if due_date:
                    parts.append(
                        f"CISA KEV: remediation required by {due_date.date()}."
                    )
                if required_action:
                    parts.append(required_action)
                else:
                    parts.append("Apply vendor patches immediately (actively exploited in wild).")

            # Fix version
            if fix_versions:
                parts.append(f"Update to {', '.join(fix_versions)}.")
            elif not parts:
                parts.append(f"Apply available patches or workarounds for {cve_id}.")

            # EPSS context
            epss = graph.exploitability.epss_score
            if epss is not None and epss >= 0.1:
                parts.append(
                    f"EPSS exploitation probability: {epss:.1%}. Prioritize remediation."
                )

            # NIST controls
            if graph.mitigation_controls:
                ctrl = graph.mitigation_controls[0]
                parts.append(
                    f"Apply {ctrl.framework} control {ctrl.control_id}: {ctrl.control_title}."
                )

            return " ".join(parts) if parts else f"Remediate {cve_id} per vendor guidance."

        # UNDER_INVESTIGATION
        return (
            f"Assessment for {cve_id} is under investigation. "
            f"Monitor vendor advisories and apply patches as available."
        )

    # ========================================================================
    # ASYNC HELPER
    # ========================================================================

    def _run_async(self, coro) -> Any:
        """
        Run an async coroutine from a synchronous context.

        Handles the case where an event loop is already running (e.g., inside
        FastAPI/uvicorn) by scheduling the coroutine on the existing loop.
        Falls back to creating a new loop if none is running.

        Args:
            coro: Coroutine to run

        Returns:
            Result of the coroutine

        Raises:
            Exception: If the coroutine raises
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're inside an async context (FastAPI/uvicorn).
                # Schedule the coroutine as a task and wait synchronously
                # using a concurrent.futures bridge.
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, coro)
                    return future.result()
            else:
                return loop.run_until_complete(coro)
        except RuntimeError:
            # No event loop exists — create one
            return asyncio.run(coro)


__all__ = [
    "VEXStatementGenerator",
]
