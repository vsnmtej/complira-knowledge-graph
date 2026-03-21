"""
ScanEnrichmentRepository — bulk reads and writes for the three-stage post-ingestion pipeline.

Responsibilities:
- Paginated fetch of scan_findings for a scan run
- Bulk AQL traversal for CVE enrichment (EPSS, KEV, CWE chain, D3FEND, req keys)
- CWE parent-map resolution for compaction grouping
- Bulk UPDATE of scan_findings with enrichment / compaction fields
- Upsert of detected_controls and all pipeline-generated edge collections
- scan_run status transitions

Design contract:
- All AQL is contained here; pipeline classes hold zero AQL.
- All reads include FILTER tenant_id == @tenant_id where the collection has tenant_id.
- All writes use import_bulk(on_duplicate="update") for idempotency.
- bulk_update_findings() chunks internally at 500 items per AQL call.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterator, Optional

from arango.database import StandardDatabase

log = logging.getLogger(__name__)

_CHUNK_SIZE = 500


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class ScanEnrichmentRepository:
    """
    Data-access layer for all pipeline-stage reads and writes.

    Injected into EnrichmentPipeline, CompactionPipeline, ControlMappingPipeline
    and PipelineCoordinator via constructor.
    """

    def __init__(self, db: StandardDatabase) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Paginated reads
    # ------------------------------------------------------------------

    def fetch_findings_for_run(
        self,
        scan_run_id: str,
        tenant_id: str,
        batch_size: int = 500,
    ) -> Iterator[list[dict]]:
        """
        Yield batches of scan_findings for the given scan run.

        AQL: FOR f IN scan_findings
               FILTER f.scan_run_id == @run_id AND f.tenant_id == @tenant_id
               LIMIT @offset, @batch_size
               RETURN f

        Yields one list[dict] per batch until the collection is exhausted.
        """
        offset = 0
        while True:
            cursor = self._db.aql.execute(
                """
                FOR f IN scan_findings
                    FILTER f.scan_run_id == @run_id AND f.tenant_id == @tenant_id
                    LIMIT @offset, @batch_size
                    RETURN f
                """,
                bind_vars={
                    "run_id": scan_run_id,
                    "tenant_id": tenant_id,
                    "offset": offset,
                    "batch_size": batch_size,
                },
            )
            batch = list(cursor)
            if not batch:
                break
            log.debug(
                "scan_enrichment_repo.fetch_findings_batch",
                extra={
                    "scan_run_id": scan_run_id,
                    "offset": offset,
                    "count": len(batch),
                },
            )
            yield batch
            if len(batch) < batch_size:
                break
            offset += batch_size

    def fetch_enriched_findings_for_run(
        self,
        scan_run_id: str,
        tenant_id: str,
        batch_size: int = 500,
    ) -> Iterator[list[dict]]:
        """
        Yield batches of scan_findings that have enriched_at set (used by CompactionPipeline).

        AQL: FOR f IN scan_findings
               FILTER f.scan_run_id == @run_id AND f.tenant_id == @tenant_id
                 AND f.enriched_at != null
               LIMIT @offset, @batch_size
               RETURN f
        """
        offset = 0
        while True:
            cursor = self._db.aql.execute(
                """
                FOR f IN scan_findings
                    FILTER f.scan_run_id == @run_id
                      AND f.tenant_id == @tenant_id
                      AND f.enriched_at != null
                    LIMIT @offset, @batch_size
                    RETURN f
                """,
                bind_vars={
                    "run_id": scan_run_id,
                    "tenant_id": tenant_id,
                    "offset": offset,
                    "batch_size": batch_size,
                },
            )
            batch = list(cursor)
            if not batch:
                break
            yield batch
            if len(batch) < batch_size:
                break
            offset += batch_size

    def fetch_detected_controls_for_run(
        self,
        scan_run_id: str,
        tenant_id: str,
    ) -> list[dict]:
        """
        Return all detected_controls for the run in one query.

        AQL: FOR c IN detected_controls
               FILTER c.scan_run_id == @run_id AND c.tenant_id == @tenant_id
               RETURN c
        """
        cursor = self._db.aql.execute(
            """
            FOR c IN detected_controls
                FILTER c.scan_run_id == @run_id AND c.tenant_id == @tenant_id
                RETURN c
            """,
            bind_vars={"run_id": scan_run_id, "tenant_id": tenant_id},
        )
        return list(cursor)

    # ------------------------------------------------------------------
    # Bulk CVE enrichment traversal
    # ------------------------------------------------------------------

    def aql_enrich_batch(
        self,
        cve_ids: list[str],
        db: Optional[StandardDatabase] = None,
    ) -> dict[str, dict]:
        """
        Single AQL traversal over a batch of CVE keys (underscore format).

        Returns dict keyed by cve_key:
          {epss_score, epss_percentile, in_kev, cwe_chain, d3fend_techniques, req_keys}

        The `db` parameter is accepted for interface compatibility but ignored;
        the instance DB handle is always used.
        """
        if not cve_ids:
            return {}
        _db = db or self._db
        try:
            cursor = _db.aql.execute(
                """
                FOR cve_key IN @cve_keys
                    LET cve_doc = DOCUMENT(CONCAT("vulnerabilities/", cve_key))
                    FILTER cve_doc != null
                    LET epss = FIRST(
                        FOR e IN 1..1 OUTBOUND cve_doc has_epss
                            SORT e.score_date DESC
                            LIMIT 1
                            RETURN e
                    )
                    LET in_kev = (
                        LENGTH(
                            FOR k IN kev_entries
                                FILTER k.cve_id == REGEX_REPLACE(cve_key, "_", "-")
                                LIMIT 1
                                RETURN 1
                        ) > 0
                    )
                    LET cwes = (
                        FOR w IN 1..1 OUTBOUND cve_doc has_weakness
                            RETURN w.cwe_id
                    )
                    LET req_keys = (
                        FOR req IN 1..2 OUTBOUND cve_doc
                            violates_requirement, maps_to_requirement
                            RETURN DISTINCT req._key
                    )
                    LET attack_techs = (
                        FOR w IN 1..1 OUTBOUND cve_doc has_weakness
                            FOR t IN 1..1 INBOUND w technique_exploits_weakness
                                RETURN DISTINCT t._key
                    )
                    LET d3fend = (
                        FOR tech IN attack_techs
                            FOR d IN 1..1 INBOUND DOCUMENT(CONCAT("attack_techniques/", tech))
                                d3fend_counters_technique
                                RETURN DISTINCT d.d3fend_id
                    )
                    RETURN {
                        cve_key:          cve_key,
                        epss_score:       epss.epss_score,
                        epss_percentile:  epss.percentile,
                        in_kev:           in_kev,
                        cwe_chain:        cwes,
                        d3fend_techniques: d3fend,
                        req_keys:         req_keys
                    }
                """,
                bind_vars={"cve_keys": cve_ids},
            )
        except Exception:
            log.exception(
                "scan_enrichment_repo.aql_enrich_batch_failed",
                extra={"cve_count": len(cve_ids)},
            )
            return {}

        result: dict[str, dict] = {}
        for row in cursor:
            cve_key = row.get("cve_key")
            if cve_key:
                result[cve_key] = row
        log.debug(
            "scan_enrichment_repo.aql_enrich_batch_complete",
            extra={"queried": len(cve_ids), "found": len(result)},
        )
        return result

    # ------------------------------------------------------------------
    # CWE parent-map for compaction grouping
    # ------------------------------------------------------------------

    def aql_get_cwe_parent_map(self, cwe_ids: list[str]) -> dict[str, str]:
        """
        For each CWE key, resolve to nearest ancestor that has a maps_to_requirement edge.

        Returns dict: {cwe_key -> resolved_cwe_key}
        If a CWE has no ancestor with a requirement mapping, resolves to itself.
        """
        if not cwe_ids:
            return {}
        try:
            cursor = self._db.aql.execute(
                """
                FOR cwe_key IN @cwe_keys
                    LET has_req = (
                        LENGTH(
                            FOR req IN 1..1 OUTBOUND DOCUMENT(CONCAT("weaknesses/", cwe_key))
                                maps_to_requirement
                                RETURN 1
                        ) > 0
                    )
                    LET parent = (
                        FOR p IN 1..5 OUTBOUND DOCUMENT(CONCAT("weaknesses/", cwe_key))
                            child_of
                            FILTER LENGTH(
                                FOR r IN 1..1 OUTBOUND p maps_to_requirement RETURN 1
                            ) > 0
                            LIMIT 1
                            RETURN p._key
                    )
                    RETURN {
                        cwe_key:  cwe_key,
                        resolved: has_req ? cwe_key : FIRST(parent)
                    }
                """,
                bind_vars={"cwe_keys": cwe_ids},
            )
        except Exception:
            log.exception(
                "scan_enrichment_repo.aql_get_cwe_parent_map_failed",
                extra={"cwe_count": len(cwe_ids)},
            )
            return {k: k for k in cwe_ids}

        result: dict[str, str] = {}
        for row in cursor:
            cwe_key = row.get("cwe_key")
            resolved = row.get("resolved")
            if cwe_key:
                result[cwe_key] = resolved if resolved else cwe_key
        return result

    def aql_get_alias_groups(
        self,
        scan_run_id: str,
        tenant_id: str,
    ) -> dict[str, list[str]]:
        """
        Group finding fingerprints by shared primary CWE (first element of cwe_chain).

        Returns dict: {cwe_key -> [fingerprint, ...]}
        """
        cursor = self._db.aql.execute(
            """
            FOR f IN scan_findings
                FILTER f.scan_run_id == @run_id AND f.tenant_id == @tenant_id
                  AND f.cwe_chain != null AND LENGTH(f.cwe_chain) > 0
                COLLECT cwe_key = FIRST(f.cwe_chain) INTO fps
                RETURN {cwe_key: cwe_key, fingerprints: fps[*].f._key}
            """,
            bind_vars={"run_id": scan_run_id, "tenant_id": tenant_id},
        )
        return {row["cwe_key"]: row["fingerprints"] for row in cursor}

    # ------------------------------------------------------------------
    # Control framework resolution
    # ------------------------------------------------------------------

    def aql_resolve_control_framework(
        self,
        detected_control_ids: list[str],
    ) -> list[dict]:
        """
        Resolve each detected_control to its framework via oscal_controls/scf_controls/
        regulatory_requirements.

        Returns list[{control_key, framework}].
        """
        if not detected_control_ids:
            return []
        try:
            cursor = self._db.aql.execute(
                """
                FOR ctrl_key IN @control_keys
                    LET oscal = FIRST(
                        FOR o IN oscal_controls
                            FILTER o._key == ctrl_key
                            RETURN o.framework
                    )
                    LET scf = FIRST(
                        FOR s IN scf_controls
                            FILTER s._key == ctrl_key
                            RETURN s.framework
                    )
                    LET reg = FIRST(
                        FOR r IN regulatory_requirements
                            FILTER r._key == ctrl_key
                            RETURN r.framework
                    )
                    RETURN {
                        control_key: ctrl_key,
                        framework: oscal != null ? oscal : (scf != null ? scf : reg)
                    }
                """,
                bind_vars={"control_keys": detected_control_ids},
            )
        except Exception:
            log.exception(
                "scan_enrichment_repo.aql_resolve_control_framework_failed",
                extra={"count": len(detected_control_ids)},
            )
            return []
        return list(cursor)

    def aql_resolve_evidence_chains(
        self,
        scan_run_id: str,
        tenant_id: str,
    ) -> list[dict]:
        """
        Per detected_control: resolve evidence chain [finding_id, cwe_id, req_id, control_id].

        Returns list[{control_key, chain: [finding_id, cwe_id, req_id, control_id]}].
        """
        try:
            cursor = self._db.aql.execute(
                """
                FOR ctrl IN detected_controls
                    FILTER ctrl.scan_run_id == @run_id AND ctrl.tenant_id == @tenant_id
                    LET req_id = ctrl.req_id
                    LET finding_id = FIRST(
                        FOR edge IN finding_triggers_req
                            FILTER edge._to == CONCAT("regulatory_requirements/", req_id)
                              AND edge.tenant_id == @tenant_id
                            LIMIT 1
                            RETURN PARSE_IDENTIFIER(edge._from).key
                    )
                    LET cwe_id = (
                        finding_id != null
                            ? FIRST(DOCUMENT(CONCAT("scan_findings/", finding_id)).cwe_chain)
                            : null
                    )
                    RETURN {
                        control_key: ctrl._key,
                        chain: [
                            finding_id != null ? finding_id : "",
                            cwe_id != null ? cwe_id : "",
                            req_id != null ? req_id : "",
                            ctrl._key
                        ]
                    }
                """,
                bind_vars={"run_id": scan_run_id, "tenant_id": tenant_id},
            )
        except Exception:
            log.exception(
                "scan_enrichment_repo.aql_resolve_evidence_chains_failed",
                extra={"scan_run_id": scan_run_id},
            )
            return []
        return list(cursor)

    def aql_get_total_reqs_by_framework(self) -> dict[str, int]:
        """
        Count total applicable requirements per framework in the reference DB.

        Returns dict: {framework_name -> count}
        """
        try:
            cursor = self._db.aql.execute(
                """
                FOR req IN regulatory_requirements
                    FILTER req.framework != null
                    COLLECT framework = req.framework WITH COUNT INTO cnt
                    RETURN {framework: framework, count: cnt}
                """
            )
        except Exception:
            log.exception("scan_enrichment_repo.aql_get_total_reqs_by_framework_failed")
            return {}
        return {row["framework"]: row["count"] for row in cursor}

    # ------------------------------------------------------------------
    # Bulk writes
    # ------------------------------------------------------------------

    def bulk_update_findings(self, updates: list[dict]) -> None:
        """
        Bulk-update scan_findings documents by _key.

        Each dict in updates must have '_key' plus the fields to update.
        Chunks internally at 500 items per AQL call to respect transaction limits.
        """
        if not updates:
            return
        total = 0
        for i in range(0, len(updates), _CHUNK_SIZE):
            chunk = updates[i : i + _CHUNK_SIZE]
            self._db.aql.execute(
                """
                FOR u IN @updates
                    UPDATE u._key WITH u IN scan_findings
                    OPTIONS {keepNull: false}
                """,
                bind_vars={"updates": chunk},
            )
            total += len(chunk)
        log.info(
            "scan_enrichment_repo.bulk_update_findings",
            extra={"total": total, "chunks": len(range(0, len(updates), _CHUNK_SIZE))},
        )

    def upsert_detected_controls(self, docs: list[dict]) -> None:
        """
        Upsert detected_controls documents.
        Delegates to import_bulk(on_duplicate="update").
        """
        if not docs:
            return
        self._db.collection("detected_controls").import_bulk(
            docs, on_duplicate="update"
        )
        log.info(
            "scan_enrichment_repo.upsert_detected_controls",
            extra={"count": len(docs)},
        )

    # Alias used by call-stack design doc
    bulk_upsert_detected_controls = upsert_detected_controls

    def upsert_finding_triggers_req_edges(self, edges: list[dict]) -> None:
        """
        Upsert finding_triggers_req edges.
        Uses import_bulk(on_duplicate="update").
        """
        if not edges:
            return
        self._db.collection("finding_triggers_req").import_bulk(
            edges, on_duplicate="update"
        )
        log.info(
            "scan_enrichment_repo.upsert_finding_triggers_req_edges",
            extra={"count": len(edges)},
        )

    def upsert_detected_control_maps_to_edges(self, edges: list[dict]) -> None:
        """
        Upsert detected_control_maps_to edges.
        Uses import_bulk(on_duplicate="update").
        """
        if not edges:
            return
        self._db.collection("detected_control_maps_to").import_bulk(
            edges, on_duplicate="update"
        )
        log.info(
            "scan_enrichment_repo.upsert_detected_control_maps_to_edges",
            extra={"count": len(edges)},
        )

    def update_scan_run(self, scan_run_id: str, updates: dict) -> None:
        """
        Update scan_runs document fields.

        Merges updates dict into the document, always setting updated_at.
        """
        payload = {"_key": scan_run_id, "updated_at": _utcnow(), **updates}
        self._db.collection("scan_runs").update(payload)
        log.info(
            "scan_enrichment_repo.update_scan_run",
            extra={"scan_run_id": scan_run_id, "fields": list(updates.keys())},
        )

    def update_scan_run_status(
        self,
        scan_run_key: str,
        status: str,
        extra_fields: Optional[dict] = None,
    ) -> None:
        """
        Convenience wrapper: update scan_runs status + optional extra fields.
        """
        updates: dict = {"status": status}
        if extra_fields:
            updates.update(extra_fields)
        self.update_scan_run(scan_run_key, updates)
        log.info(
            "scan_enrichment_repo.update_scan_run_status",
            extra={"scan_run_id": scan_run_key, "status": status},
        )

    def update_scan_run_coverage(
        self,
        scan_run_key: str,
        coverage_by_framework: dict,
    ) -> None:
        """Write coverage_by_framework to scan_runs document."""
        self.update_scan_run(
            scan_run_key,
            {"coverage_by_framework": coverage_by_framework},
        )
