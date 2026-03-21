"""
EnrichmentPipeline — UC-007 Vulnerability Enrichment.

Reads all scan_findings for a scan run in batches, identifies findings with
cve_id, executes bulk AQL traversal against the reference knowledge graph,
writes enrichment fields back to scan_findings, upserts new detected_controls,
and creates finding_triggers_req and detected_control_maps_to edges.

Status transition: completed → enriched
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from arango.database import StandardDatabase

from complira_graph.ingestion.scan_enrichment_repository import ScanEnrichmentRepository
from complira_graph.utils.keys import generate_edge_key

log = logging.getLogger(__name__)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class EnrichmentPipeline:
    """
    UC-007 Vulnerability Enrichment pipeline stage.

    Reads findings in batches, enriches via AQL graph traversal, writes back
    to scan_findings and creates edges. Zero AQL in this class.
    """

    def __init__(self, db: StandardDatabase, repo: ScanEnrichmentRepository) -> None:
        self._db = db
        self._repo = repo

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self, scan_run_id: str, tenant_id: str) -> None:
        """
        Entry point for UC-007.

        Full call sequence per batch:
          1. Fetch findings (paginated, batch_size=500)
          2. Extract distinct CVE IDs → normalize to ArangoDB key format
          3. aql_enrich_batch(cve_keys) → enrichment_map
          4. _build_finding_updates → repo.bulk_update_findings
          5. _build_req_edges → repo.upsert_finding_triggers_req_edges
          6. _build_detected_controls → repo.upsert_detected_controls
          7. _build_detected_control_maps_to_edges → repo.upsert_detected_control_maps_to_edges
        Finally: update scan_run status to "enriched".
        """
        log.info(
            "enrichment_pipeline.start",
            extra={"scan_run_id": scan_run_id, "tenant_id": tenant_id},
        )

        batch_count = 0
        for batch in self._repo.fetch_findings_for_run(scan_run_id, tenant_id):
            batch_count += 1
            log.debug(
                "enrichment_pipeline.batch",
                extra={
                    "scan_run_id": scan_run_id,
                    "batch": batch_count,
                    "size": len(batch),
                },
            )

            # Collect distinct CVE keys from findings that have a cve_id
            cve_key_set: dict[str, str] = {}  # normalized_key → original cve_id
            for finding in batch:
                cve_id = finding.get("cve_id")
                if cve_id:
                    normalized = self._normalize_cve_key(cve_id)
                    cve_key_set[normalized] = cve_id

            enrichment_map: dict[str, dict] = {}
            if cve_key_set:
                enrichment_map = self._repo.aql_enrich_batch(list(cve_key_set.keys()))

            updates = self._build_finding_updates(batch, enrichment_map)
            self._repo.bulk_update_findings(updates)

            req_edges = self._build_req_edges(batch, enrichment_map, tenant_id)
            self._repo.upsert_finding_triggers_req_edges(req_edges)

            control_docs = self._build_detected_controls(
                scan_run_id, batch, enrichment_map, tenant_id
            )
            self._repo.upsert_detected_controls(control_docs)

            ctrl_edges = self._build_detected_control_maps_to_edges(
                control_docs, tenant_id
            )
            self._repo.upsert_detected_control_maps_to_edges(ctrl_edges)

        self._repo.update_scan_run_status(
            scan_run_id,
            "enriched",
            extra_fields={"enriched_at": _utcnow()},
        )
        log.info(
            "enrichment_pipeline.complete",
            extra={"scan_run_id": scan_run_id, "batches": batch_count},
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _normalize_cve_key(self, cve_id: str) -> str:
        """
        Convert CVE ID to ArangoDB _key format.

        CVE-2024-1234 → CVE_2024_1234 (hyphens replaced with underscores, uppercased).
        """
        return cve_id.replace("-", "_").upper()

    def _build_finding_updates(
        self,
        findings: list[dict],
        enrichment_map: dict[str, dict],
    ) -> list[dict]:
        """
        Build update dicts for scan_findings enrichment write-back.

        For each finding with cve_id present in enrichment_map:
          - Write: epss_score, epss_percentile, in_kev, cwe_chain, d3fend_techniques
        All findings (including no-CVE findings): write enriched_at.

        Returns list[{_key, ...fields}].
        """
        enriched_at = _utcnow()
        updates: list[dict] = []
        for finding in findings:
            fingerprint = finding.get("_key") or finding.get("fingerprint", "")
            update: dict = {"_key": fingerprint, "enriched_at": enriched_at}

            cve_id = finding.get("cve_id")
            if cve_id:
                cve_key = self._normalize_cve_key(cve_id)
                enrichment = enrichment_map.get(cve_key)
                if enrichment:
                    if enrichment.get("epss_score") is not None:
                        update["epss_score"] = enrichment["epss_score"]
                    if enrichment.get("epss_percentile") is not None:
                        update["epss_percentile"] = enrichment["epss_percentile"]
                    update["in_kev"] = bool(enrichment.get("in_kev", False))
                    cwe_chain = enrichment.get("cwe_chain") or []
                    if cwe_chain:
                        update["cwe_chain"] = cwe_chain
                    d3fend = enrichment.get("d3fend_techniques") or []
                    if d3fend:
                        update["d3fend_techniques"] = d3fend

            updates.append(update)
        return updates

    def _build_req_edges(
        self,
        findings: list[dict],
        enrichment_map: dict[str, dict],
        tenant_id: str,
    ) -> list[dict]:
        """
        Build finding_triggers_req edge dicts from CVE → violates_requirement traversal.

        _from: scan_findings/<fingerprint>
        _to:   regulatory_requirements/<req_key>
        source: "cve_violates_req"

        Deduplicates by edge _key.
        """
        edges: dict[str, dict] = {}
        for finding in findings:
            cve_id = finding.get("cve_id")
            if not cve_id:
                continue
            cve_key = self._normalize_cve_key(cve_id)
            enrichment = enrichment_map.get(cve_key)
            if not enrichment:
                continue
            req_keys = enrichment.get("req_keys") or []
            fingerprint = finding.get("_key") or finding.get("fingerprint", "")
            for req_key in req_keys:
                edge_key = generate_edge_key(fingerprint, req_key, "triggers_req")
                if edge_key not in edges:
                    edges[edge_key] = {
                        "_key": edge_key,
                        "_from": f"scan_findings/{fingerprint}",
                        "_to": f"regulatory_requirements/{req_key}",
                        "tenant_id": tenant_id,
                        "source": "cve_violates_req",
                    }
        return list(edges.values())

    def _build_detected_controls(
        self,
        scan_run_id: str,
        findings: list[dict],
        enrichment_map: dict[str, dict],
        tenant_id: str,
    ) -> list[dict]:
        """
        Build detected_controls documents from CVE → violates_requirement traversal.

        For each (finding, req_key) pair reachable via enrichment_map:
          _key: generate_edge_key(scan_run_id, req_key, "ctrl")
          scan_run_id, tenant_id, req_id, check_id, check_name, triage_status="compliant"

        Deduplicates by _key.
        """
        seen: dict[str, dict] = {}
        for finding in findings:
            cve_id = finding.get("cve_id")
            if not cve_id:
                continue
            cve_key = self._normalize_cve_key(cve_id)
            enrichment = enrichment_map.get(cve_key)
            if not enrichment:
                continue
            req_keys = enrichment.get("req_keys") or []
            for req_key in req_keys:
                ctrl_key = generate_edge_key(scan_run_id, req_key, "ctrl")
                if ctrl_key not in seen:
                    seen[ctrl_key] = {
                        "_key": ctrl_key,
                        "scan_run_id": scan_run_id,
                        "tenant_id": tenant_id,
                        "req_id": req_key,
                        "check_id": finding.get("check_id") or finding.get("rule_id", ""),
                        "check_name": finding.get("check_name") or finding.get("message", ""),
                        "triage_status": "compliant",
                        "source": "enrichment_pipeline",
                    }
        return list(seen.values())

    def _build_detected_control_maps_to_edges(
        self,
        control_docs: list[dict],
        tenant_id: str,
    ) -> list[dict]:
        """
        Build detected_control_maps_to edge dicts.

        _from: detected_controls/<control_key>
        _to:   regulatory_requirements/<req_key>
        source: "enrichment_pipeline"
        """
        edges: dict[str, dict] = {}
        for ctrl in control_docs:
            ctrl_key = ctrl.get("_key", "")
            req_key = ctrl.get("req_id", "")
            if not ctrl_key or not req_key:
                continue
            edge_key = generate_edge_key(ctrl_key, req_key, "maps_to")
            if edge_key not in edges:
                edges[edge_key] = {
                    "_key": edge_key,
                    "_from": f"detected_controls/{ctrl_key}",
                    "_to": f"regulatory_requirements/{req_key}",
                    "tenant_id": tenant_id,
                    "source": "enrichment_pipeline",
                }
        return list(edges.values())
