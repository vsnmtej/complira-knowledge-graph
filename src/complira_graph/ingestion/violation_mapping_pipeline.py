"""
ViolationMappingPipeline — Compliance Violation Mapping stage.

Two ingestion paths:

1. CVE path (SAST/SCA findings with cve_id):
   Traverses the reference graph chain:
     CVE → has_weakness → CWE → capec_relates_to_cwe ← CAPEC → capec_maps_to_attack
         → ATT&CK → technique_mitigated_by_control → NIST 800-53 control (oscal_controls)
   Deduplicates by CVE before issuing AQL traversals.

2. Direct-ref path (CSPM/IAC findings with nist_control_refs / hipaa_refs):
   Parses comma-separated control IDs directly from the finding (e.g. "AC-6, IA-2"),
   looks them up in oscal_controls by control_id, and writes edges without graph traversal.
   Frameworks: "NIST-800-53" for nist_control_refs, "HIPAA" for hipaa_refs.
   confidence = 1.0 (tool-provided mapping, not inferred).

Writes per-finding finding_violates_control edges carrying:
  tenant_id, scan_run_id, cve_id, control_id, framework,
  confidence (1.0), evidence_path, created_at

Status transition: mapped → violations_mapped
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from arango.database import StandardDatabase

from complira_graph.ingestion.scan_enrichment_repository import ScanEnrichmentRepository
from complira_graph.ingestion.scan_violation_repository import ScanViolationRepository
from complira_graph.utils.keys import generate_edge_key

log = logging.getLogger(__name__)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_cve_key(cve_id: str) -> str:
    """CVE-2024-1234 → CVE_2024_1234"""
    return cve_id.replace("-", "_").upper()


def _parse_control_refs(refs_field: str) -> list[str]:
    """
    Parse a comma-separated control ID string into a deduplicated list.

    "AC-6, IA-2, AC-6" → ["AC-6", "IA-2"]
    Empty string or None → []
    """
    if not refs_field:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for part in refs_field.split(","):
        ctrl_id = part.strip()
        if ctrl_id and ctrl_id not in seen:
            seen.add(ctrl_id)
            result.append(ctrl_id)
    return result


class ViolationMappingPipeline:
    """
    Compliance violation mapping pipeline stage.

    Reads findings via ScanEnrichmentRepository, traverses controls via
    ScanViolationRepository, writes finding_violates_control edges.
    Holds zero AQL directly.
    """

    def __init__(
        self,
        db: StandardDatabase,
        repo: ScanEnrichmentRepository,
        violation_repo: ScanViolationRepository,
    ) -> None:
        self._db = db
        self._repo = repo
        self._violation_repo = violation_repo

    def run(self, scan_run_id: str, tenant_id: str) -> None:
        """
        Map findings to NIST 800-53 controls for the given scan run.

        Trigger: scan_run.status == "mapped"
        Result:  scan_run.status = "violations_mapped" on success

        Processes two finding types in a single pass:
          - CVE-bearing findings: graph traversal CVE→CWE→CAPEC→ATT&CK→control
          - Direct-ref findings (nist_control_refs / hipaa_refs): direct oscal_controls lookup
        """
        log.info(
            "violation_mapping_pipeline.start",
            extra={"scan_run_id": scan_run_id, "tenant_id": tenant_id},
        )

        # Collect findings in a single pass
        cve_to_findings: dict[str, list[str]] = {}
        # direct_refs: list of (finding_key, control_id, framework)
        direct_refs: list[tuple[str, str, str]] = []

        for batch in self._repo.fetch_findings_for_run(scan_run_id, tenant_id):
            for finding in batch:
                finding_key = finding["_key"]

                # CVE path
                cve_id = finding.get("cve_id") or ""
                if cve_id:
                    cve_key = _normalize_cve_key(cve_id)
                    cve_to_findings.setdefault(cve_key, []).append(finding_key)

                # Direct NIST refs (comma-separated string, e.g. "AC-6, IA-2")
                nist_refs = finding.get("nist_control_refs") or ""
                for ctrl_id in _parse_control_refs(nist_refs):
                    direct_refs.append((finding_key, ctrl_id, "NIST-800-53"))

                # Direct HIPAA refs
                hipaa_refs = finding.get("hipaa_refs") or ""
                for ctrl_id in _parse_control_refs(hipaa_refs):
                    direct_refs.append((finding_key, ctrl_id, "HIPAA"))

        all_edges: list[dict] = []

        # --- CVE graph-traversal path ---
        if cve_to_findings:
            cve_keys = list(cve_to_findings.keys())
            control_map = self._violation_repo.aql_traverse_controls_for_cves(cve_keys)
            all_edges.extend(
                self._build_edges(cve_to_findings, control_map, tenant_id, scan_run_id)
            )

        # --- Direct-ref path ---
        if direct_refs:
            all_edges.extend(
                self._build_direct_ref_edges(direct_refs, tenant_id, scan_run_id)
            )

        if all_edges:
            self._violation_repo.upsert_finding_violates_control_edges(all_edges)

        self._repo.update_scan_run_status(scan_run_id, "violations_mapped")
        log.info(
            "violation_mapping_pipeline.complete",
            extra={
                "scan_run_id": scan_run_id,
                "unique_cves": len(cve_to_findings),
                "direct_ref_pairs": len(direct_refs),
                "edges_written": len(all_edges),
            },
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_edges(
        self,
        cve_to_findings: dict[str, list[str]],
        control_map: dict[str, list[dict]],
        tenant_id: str,
        scan_run_id: str,
    ) -> list[dict]:
        """
        Build finding_violates_control edge dicts.

        Deduplicates by edge _key = generate_edge_key(finding_key, control_key, "violates_ctrl").
        """
        now = _utcnow()
        seen: dict[str, dict] = {}

        for cve_key, finding_keys in cve_to_findings.items():
            controls = control_map.get(cve_key)
            if not controls:
                continue
            # Reconstruct original CVE ID format for the edge field
            cve_id = cve_key.replace("_", "-", 2)  # CVE_2024_1234 → CVE-2024-1234

            for finding_key in finding_keys:
                for ctrl in controls:
                    edge_key = generate_edge_key(finding_key, ctrl["control_key"], "violates_ctrl")
                    if edge_key not in seen:
                        seen[edge_key] = {
                            "_key": edge_key,
                            "_from": f"scan_findings/{finding_key}",
                            "_to": f"oscal_controls/{ctrl['control_key']}",
                            "tenant_id": tenant_id,
                            "scan_run_id": scan_run_id,
                            "cve_id": cve_id,
                            "control_id": ctrl.get("control_id") or ctrl["control_key"],
                            "framework": ctrl.get("framework") or "NIST_800_53",
                            "confidence": 1.0,
                            "evidence_path": ctrl.get("evidence_path") or [],
                            "created_at": now,
                        }

        return list(seen.values())

    def _build_direct_ref_edges(
        self,
        direct_refs: list[tuple[str, str, str]],
        tenant_id: str,
        scan_run_id: str,
    ) -> list[dict]:
        """
        Build finding_violates_control edges for findings with direct control refs.

        Looks up oscal_controls by control_id for all unique control IDs in one AQL call.
        Skips control IDs not found in oscal_controls (reference DB may not have all HIPAA IDs).

        Args:
            direct_refs: list of (finding_key, control_id, framework)
        """
        # Deduplicate control IDs for a single AQL lookup
        unique_control_ids = list({ctrl_id for _, ctrl_id, _ in direct_refs})
        control_id_to_key = self._violation_repo.aql_lookup_controls_by_ids(unique_control_ids)

        if not control_id_to_key:
            log.info(
                "violation_mapping_pipeline.direct_refs_no_controls_found",
                extra={
                    "scan_run_id": scan_run_id,
                    "unique_control_ids": len(unique_control_ids),
                },
            )
            return []

        now = _utcnow()
        seen: dict[str, dict] = {}

        for finding_key, ctrl_id, framework in direct_refs:
            control_key = control_id_to_key.get(ctrl_id)
            if not control_key:
                continue
            edge_key = generate_edge_key(finding_key, control_key, "violates_ctrl")
            if edge_key not in seen:
                seen[edge_key] = {
                    "_key": edge_key,
                    "_from": f"scan_findings/{finding_key}",
                    "_to": f"oscal_controls/{control_key}",
                    "tenant_id": tenant_id,
                    "scan_run_id": scan_run_id,
                    "control_id": ctrl_id,
                    "framework": framework,
                    "confidence": 1.0,
                    "evidence_path": [finding_key, control_key],
                    "created_at": now,
                }

        return list(seen.values())
