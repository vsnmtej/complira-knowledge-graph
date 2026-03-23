"""
ScanViolationRepository — AQL for compliance violation mapping.

Responsibilities:
- Traverse the reference graph chain (CVE → CWE → CAPEC → ATT&CK → NIST 800-53 control)
  for a batch of CVE keys and return matched controls with evidence paths.
- Bulk upsert finding_violates_control edges.

Design contract:
- All AQL is contained here; ViolationMappingPipeline holds zero AQL.
- import_bulk(on_duplicate="update") ensures idempotency via deterministic _key.
"""

from __future__ import annotations

import logging

from arango.database import StandardDatabase

log = logging.getLogger(__name__)

_CHUNK_SIZE = 500

_TRAVERSE_CONTROLS_QUERY = """
FOR cve_key IN @cve_keys
    LET cve_doc = DOCUMENT(CONCAT("vulnerabilities/", cve_key))
    FILTER cve_doc != null
    LET controls = (
        FOR w IN 1..1 OUTBOUND cve_doc has_weakness
            FOR ca IN 1..1 INBOUND w capec_relates_to_cwe
                FOR at IN 1..1 OUTBOUND ca capec_maps_to_attack
                    FOR ctrl IN 1..1 OUTBOUND at technique_mitigated_by_control
                        RETURN DISTINCT {
                            control_key: ctrl._key,
                            control_id: ctrl.control_id,
                            framework: ctrl.framework,
                            evidence_path: [cve_key, w._key, ca._key, at._key, ctrl._key]
                        }
    )
    FILTER LENGTH(controls) > 0
    RETURN {cve_key: cve_key, controls: controls}
"""


class ScanViolationRepository:
    """
    Data-access layer for the compliance violation pipeline stage.

    Injected into ViolationMappingPipeline via constructor.
    """

    def __init__(self, db: StandardDatabase) -> None:
        self._db = db

    def aql_traverse_controls_for_cves(
        self,
        cve_keys: list[str],
    ) -> dict[str, list[dict]]:
        """
        Traverse CVE → CWE → CAPEC → ATT&CK → NIST 800-53 control for each CVE.

        Returns dict[cve_key → list[{control_key, control_id, framework, evidence_path}]].
        CVEs with no chain mapping are absent from the result (not an error).
        CVEs not found in vulnerabilities collection are silently excluded.
        """
        if not cve_keys:
            return {}
        try:
            cursor = self._db.aql.execute(
                _TRAVERSE_CONTROLS_QUERY,
                bind_vars={"cve_keys": cve_keys},
            )
        except Exception:
            log.exception(
                "scan_violation_repo.aql_traverse_controls_failed",
                extra={"cve_count": len(cve_keys)},
            )
            return {}

        result: dict[str, list[dict]] = {}
        for row in cursor:
            cve_key = row.get("cve_key")
            controls = row.get("controls") or []
            if cve_key and controls:
                result[cve_key] = controls
        log.debug(
            "scan_violation_repo.aql_traverse_controls_complete",
            extra={"queried": len(cve_keys), "with_controls": len(result)},
        )
        return result

    def aql_lookup_controls_by_ids(
        self,
        control_ids: list[str],
    ) -> dict[str, str]:
        """
        Look up oscal_controls _key for each control_id string.

        Returns dict[control_id → control_key].
        Control IDs not found in oscal_controls are absent from the result.
        """
        if not control_ids:
            return {}
        query = """
FOR ctrl IN oscal_controls
    FILTER ctrl.control_id IN @control_ids
    RETURN {control_id: ctrl.control_id, control_key: ctrl._key}
"""
        try:
            cursor = self._db.aql.execute(query, bind_vars={"control_ids": control_ids})
        except Exception:
            log.exception(
                "scan_violation_repo.aql_lookup_controls_failed",
                extra={"control_count": len(control_ids)},
            )
            return {}
        result: dict[str, str] = {}
        for row in cursor:
            cid = row.get("control_id")
            ckey = row.get("control_key")
            if cid and ckey:
                result[cid] = ckey
        log.debug(
            "scan_violation_repo.aql_lookup_controls_complete",
            extra={"queried": len(control_ids), "found": len(result)},
        )
        return result

    def upsert_finding_violates_control_edges(self, edges: list[dict]) -> None:
        """
        Bulk upsert finding_violates_control edges.

        Uses import_bulk(on_duplicate="update") for idempotency.
        Each edge must have _key, _from, _to, plus metadata fields.
        """
        if not edges:
            return
        for i in range(0, len(edges), _CHUNK_SIZE):
            chunk = edges[i : i + _CHUNK_SIZE]
            self._db.collection("finding_violates_control").import_bulk(
                chunk, on_duplicate="update"
            )
        log.info(
            "scan_violation_repo.upsert_finding_violates_control_edges",
            extra={"count": len(edges)},
        )
