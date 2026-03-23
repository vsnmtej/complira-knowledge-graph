"""
EvidenceEdgeService — creates all 9 v2.2 scanner evidence edge collections.

Edge collections managed:
  component_has_vuln          components → vulnerabilities  (SCA CVE hits)
  finding_maps_to_weakness    scan_findings → weaknesses    (CWE links)
  finding_triggers_req        scan_findings → regulatory_requirements (rule_engine / checkov_native / llm_reg_mapper)
  finding_in_component        scan_findings → components    (purl context)
  project_uses_component      projects → components         (SBOM)
  evidence_links_finding      evidence_packages → scan_findings
  evidence_for_project        evidence_packages → projects
  detected_control_maps_to    detected_controls → oscal_controls  (stub)
  control_in_component        detected_controls → components      (stub)

Design:
  - All edges use generate_edge_key() for deterministic _key → idempotent import_bulk(on_duplicate="update")
  - AQL resolution (CWE→req, bc_check_id→req) gracefully skips when mapping not found
  - llm_reg_mapper edges are logged and deferred (no synchronous write)
  - Stub methods for detected_controls edges (UC-010/UC-011) return early until a scanner emits them
"""

from __future__ import annotations

import logging
from typing import Optional

from arango.database import StandardDatabase

from complira_graph.utils.keys import (
    generate_edge_key,
    normalize_cwe_id,
    normalize_cve_id,
    normalize_purl,
)
from complira_graph.ingestion.checkov_control_map import (
    CHECKOV_NIST_MAP,
    _normalize_oscal_key,
)

log = logging.getLogger(__name__)


class EvidenceEdgeService:
    """
    Creates and bulk-upserts all scanner evidence edge collections.

    Accepts a StandardDatabase instance (reference DB). The create_all_edges()
    orchestrator is the primary entry point called by EvidenceIngestionService.
    """

    def __init__(self, db: StandardDatabase) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Orchestrator — called by EvidenceIngestionService after all docs written
    # ------------------------------------------------------------------

    def create_all_edges(
        self,
        finding_docs: list[dict],
        component_docs: list[dict],
        sca_vuln_docs: list[dict],
        detected_control_docs: list[dict],
        edge_plans: list[dict],
        tenant_id: str,
        project_id: Optional[str] = None,
        evidence_pkg_key: Optional[str] = None,
    ) -> None:
        """
        Run all edge creation passes after documents are written.

        Args:
            finding_docs:          scan_findings documents (IngestionBundle.document where collection=scan_findings)
            component_docs:        components documents (from SBOM ingestion)
            sca_vuln_docs:         SCA finding docs routed to component_has_vuln (grype output)
            detected_control_docs: detected_controls documents (Checkov PASSED)
            edge_plans:            planned edge dicts from IngestionBundle.edges
            tenant_id:             tenant scope
            project_id:            optional project context
            evidence_pkg_key:      optional evidence_packages _key for linking findings
        """
        if sca_vuln_docs:
            self.create_component_has_vuln_edges(sca_vuln_docs, tenant_id)

        if finding_docs:
            self.create_finding_weakness_edges(finding_docs, tenant_id)
            self.create_finding_in_component_edges(finding_docs, tenant_id)
            self.create_finding_req_edges(finding_docs, edge_plans, tenant_id)

        if component_docs and project_id:
            self.create_project_uses_component_edges(component_docs, project_id, tenant_id)

        if detected_control_docs:
            self.create_detected_control_edges(detected_control_docs, tenant_id)

        if evidence_pkg_key and finding_docs:
            self.create_evidence_finding_edges(evidence_pkg_key, finding_docs, tenant_id)

        if evidence_pkg_key and project_id:
            self.create_evidence_project_edge(evidence_pkg_key, project_id, tenant_id)

    # ------------------------------------------------------------------
    # UC-003 / UC-006: component_has_vuln edges (SCA)
    # ------------------------------------------------------------------

    def create_component_has_vuln_edges(
        self, sca_docs: list[dict], tenant_id: str
    ) -> None:
        """
        Create component_has_vuln edges from SCA finding dicts.

        _from: components/<normalize_purl(purl)>
        _to:   vulnerabilities/<normalize_cve_id(cve_id)>

        CVE not in reference DB is allowed — dangling edges are tolerated by ArangoDB;
        Tier 1 AQL traversals skip non-existent vertices automatically.
        """
        edges: list[dict] = []
        for doc in sca_docs:
            purl = doc.get("purl")
            cve_id = doc.get("cve_id")
            if not purl or not cve_id:
                log.debug(
                    "component_has_vuln.skip_missing_fields",
                    extra={"purl": purl, "cve_id": cve_id},
                )
                continue
            comp_key = normalize_purl(purl)
            cve_key = normalize_cve_id(cve_id)
            edge_key = generate_edge_key(comp_key, cve_key)
            edges.append(
                {
                    "_key": edge_key,
                    "_from": f"components/{comp_key}",
                    "_to": f"vulnerabilities/{cve_key}",
                    "tenant_id": tenant_id,
                    "vex_status": "unknown",
                    "source": doc.get("tool", "unknown"),
                }
            )
        if edges:
            self._db.collection("component_has_vuln").import_bulk(
                edges, on_duplicate="update"
            )
            log.info("component_has_vuln.created", extra={"count": len(edges)})

    # ------------------------------------------------------------------
    # UC-007: finding_maps_to_weakness edges (CWE)
    # ------------------------------------------------------------------

    def create_finding_weakness_edges(
        self, findings: list[dict], tenant_id: str
    ) -> None:
        """
        Create finding_maps_to_weakness edges for findings that have cwe_ids.

        _from: scan_findings/<fingerprint>
        _to:   weaknesses/<normalize_cwe_id(cwe_id)>

        Dangling _to references are allowed (CWE may not be in reference DB).
        """
        edges: list[dict] = []
        for f in findings:
            fingerprint = f.get("fingerprint", "")
            for cwe_id in f.get("cwe_ids") or []:
                cwe_key = normalize_cwe_id(cwe_id)
                edge_key = generate_edge_key(fingerprint, cwe_key, "maps_to_weakness")
                edges.append(
                    {
                        "_key": edge_key,
                        "_from": f"scan_findings/{fingerprint}",
                        "_to": f"weaknesses/{cwe_key}",
                        "tenant_id": tenant_id,
                        "cwe_source": f.get("cwe_source", "unknown"),
                        "source": "rule_engine",
                    }
                )
        if edges:
            self._db.collection("finding_maps_to_weakness").import_bulk(
                edges, on_duplicate="update"
            )
            log.info("finding_maps_to_weakness.created", extra={"count": len(edges)})

    # ------------------------------------------------------------------
    # UC-008 + UC-018: finding_triggers_req edges
    # ------------------------------------------------------------------

    def create_finding_req_edges(
        self,
        findings: list[dict],
        edge_plans: list[dict],
        tenant_id: str,
    ) -> None:
        """
        Resolve and create finding_triggers_req edges.

        Routes by source declared in edge_plans:
          rule_engine    → CWE traversal AQL (UC-008)
          checkov_native → bc_check_id AQL lookup (UC-018)
          llm_reg_mapper → log and defer (no synchronous write)
        """
        req_plans = [p for p in edge_plans if p.get("collection") == "finding_triggers_req"]
        if not req_plans:
            return

        rule_plans = [p for p in req_plans if p.get("source") == "rule_engine"]
        checkov_plans = [p for p in req_plans if p.get("source") == "checkov_native"]
        llm_plans = [p for p in req_plans if p.get("source") == "llm_reg_mapper"]

        if rule_plans:
            fp_map = {f.get("fingerprint", ""): f for f in findings}
            self._create_rule_engine_req_edges(rule_plans, fp_map, tenant_id)

        for plan in checkov_plans:
            self._resolve_checkov_req_edge(plan, tenant_id)

        if llm_plans:
            log.info(
                "finding_triggers_req.deferred_llm_mapper",
                extra={"count": len(llm_plans)},
            )

    def _create_rule_engine_req_edges(
        self,
        plans: list[dict],
        fp_map: dict[str, dict],
        tenant_id: str,
    ) -> None:
        """
        CWE-based finding_triggers_req via AQL traversal (UC-008).

        Collects unique CWE keys from relevant findings, queries the
        weakness → requirement graph path in a single AQL call, then
        creates edges for each (finding, req_key) pair found.
        """
        cwe_keys: list[str] = list(
            {
                normalize_cwe_id(cwe)
                for plan in plans
                for cwe in fp_map.get(plan["_from"].split("/")[-1], {}).get("cwe_ids") or []
            }
        )
        if not cwe_keys:
            return

        try:
            cursor = self._db.aql.execute(
                """
                FOR cwe_key IN @cwe_keys
                    FOR req IN 1..2 OUTBOUND CONCAT("weaknesses/", cwe_key)
                        weakness_to_requirement, cwe_to_regulation
                        RETURN DISTINCT {cwe_key: cwe_key, req_key: req._key}
                """,
                bind_vars={"cwe_keys": cwe_keys},
            )
        except Exception:
            log.exception("finding_triggers_req.aql_failed")
            return

        cwe_to_req: dict[str, list[str]] = {}
        for row in cursor:
            cwe_to_req.setdefault(row["cwe_key"], []).append(row["req_key"])

        if not cwe_to_req:
            log.info(
                "finding_triggers_req.no_cwe_req_mappings",
                extra={"cwe_keys": cwe_keys},
            )
            return

        edges: list[dict] = []
        for plan in plans:
            fingerprint = plan["_from"].split("/")[-1]
            finding = fp_map.get(fingerprint, {})
            for cwe in finding.get("cwe_ids") or []:
                cwe_key = normalize_cwe_id(cwe)
                for req_key in cwe_to_req.get(cwe_key) or []:
                    edge_key = generate_edge_key(fingerprint, req_key, "triggers_req")
                    edges.append(
                        {
                            "_key": edge_key,
                            "_from": f"scan_findings/{fingerprint}",
                            "_to": f"regulatory_requirements/{req_key}",
                            "tenant_id": tenant_id,
                            "source": "rule_engine",
                        }
                    )

        if edges:
            self._db.collection("finding_triggers_req").import_bulk(
                edges, on_duplicate="update"
            )
            log.info("finding_triggers_req.rule_engine_created", extra={"count": len(edges)})

    def _resolve_checkov_req_edge(self, plan: dict, tenant_id: str) -> None:
        """
        Resolve finding_triggers_req for checkov_native source (UC-018).

        Looks up bc_check_id in regulatory_requirements collection to find
        the target requirement. Skips gracefully if not found.
        """
        bc_check_id = plan.get("bc_check_id")
        if not bc_check_id:
            log.debug("checkov_req.skip_no_bc_check_id")
            return

        try:
            cursor = self._db.aql.execute(
                """
                FOR r IN regulatory_requirements
                    FILTER r.bc_check_id == @bc_check_id
                    RETURN r._key
                    LIMIT 1
                """,
                bind_vars={"bc_check_id": bc_check_id},
            )
        except Exception:
            log.exception(
                "checkov_req.aql_failed", extra={"bc_check_id": bc_check_id}
            )
            return

        req_key = next(iter(cursor), None)
        if not req_key:
            log.warning(
                "checkov_req.bc_check_id_not_found",
                extra={"bc_check_id": bc_check_id},
            )
            return

        fingerprint = plan["_from"].split("/")[-1]
        edge_key = generate_edge_key(fingerprint, req_key, "triggers_req")
        try:
            self._db.collection("finding_triggers_req").insert(
                {
                    "_key": edge_key,
                    "_from": plan["_from"],
                    "_to": f"regulatory_requirements/{req_key}",
                    "tenant_id": tenant_id,
                    "source": "checkov_native",
                    "bc_check_id": bc_check_id,
                },
                overwrite=True,
            )
            log.info(
                "finding_triggers_req.checkov_native_created",
                extra={"fingerprint": fingerprint, "req_key": req_key},
            )
        except Exception:
            log.exception(
                "checkov_req.insert_failed", extra={"fingerprint": fingerprint}
            )

    # ------------------------------------------------------------------
    # UC-009: finding_in_component edges
    # ------------------------------------------------------------------

    def create_finding_in_component_edges(
        self, findings: list[dict], tenant_id: str
    ) -> None:
        """
        Create finding_in_component edges for findings that have a purl.

        _from: scan_findings/<fingerprint>
        _to:   components/<normalize_purl(purl)>
        """
        edges: list[dict] = []
        for f in findings:
            purl = f.get("purl")
            if not purl:
                continue
            fingerprint = f.get("fingerprint", "")
            comp_key = normalize_purl(purl)
            edge_key = generate_edge_key(fingerprint, comp_key, "in_component")
            edges.append(
                {
                    "_key": edge_key,
                    "_from": f"scan_findings/{fingerprint}",
                    "_to": f"components/{comp_key}",
                    "tenant_id": tenant_id,
                }
            )
        if edges:
            self._db.collection("finding_in_component").import_bulk(
                edges, on_duplicate="update"
            )
            log.info("finding_in_component.created", extra={"count": len(edges)})

    # ------------------------------------------------------------------
    # UC-005: project_uses_component edges (SBOM)
    # ------------------------------------------------------------------

    def create_project_uses_component_edges(
        self,
        component_docs: list[dict],
        project_id: str,
        tenant_id: str,
    ) -> None:
        """
        Create project_uses_component edges from project to each SBOM component.

        _from: projects/<project_id>
        _to:   components/<normalize_purl(purl)>

        No-op if project_id is None.
        """
        if not project_id:
            log.info("project_uses_component.skip_no_project_id")
            return

        edges: list[dict] = []
        for comp in component_docs:
            purl = comp.get("purl")
            if not purl:
                continue
            comp_key = comp.get("_key") or normalize_purl(purl)
            edge_key = generate_edge_key(project_id, comp_key, "uses")
            edges.append(
                {
                    "_key": edge_key,
                    "_from": f"projects/{project_id}",
                    "_to": f"components/{comp_key}",
                    "tenant_id": tenant_id,
                    "sbom_format": comp.get("sbom_format"),
                    "source": "sbom",
                }
            )
        if edges:
            self._db.collection("project_uses_component").import_bulk(
                edges, on_duplicate="update"
            )
            log.info("project_uses_component.created", extra={"count": len(edges)})

    # ------------------------------------------------------------------
    # UC-012: evidence_links_finding + evidence_for_project edges
    # ------------------------------------------------------------------

    def create_evidence_finding_edges(
        self,
        pkg_key: str,
        findings: list[dict],
        tenant_id: str,
    ) -> None:
        """
        Create evidence_links_finding edges from evidence_packages to scan_findings.

        _from: evidence_packages/<pkg_key>
        _to:   scan_findings/<fingerprint>
        """
        edges: list[dict] = []
        for f in findings:
            fingerprint = f.get("fingerprint", "")
            edge_key = generate_edge_key(pkg_key, fingerprint, "links_finding")
            edges.append(
                {
                    "_key": edge_key,
                    "_from": f"evidence_packages/{pkg_key}",
                    "_to": f"scan_findings/{fingerprint}",
                    "tenant_id": tenant_id,
                }
            )
        if edges:
            self._db.collection("evidence_links_finding").import_bulk(
                edges, on_duplicate="update"
            )
            log.info("evidence_links_finding.created", extra={"count": len(edges)})

    def create_evidence_project_edge(
        self,
        pkg_key: str,
        project_id: Optional[str],
        tenant_id: str,
    ) -> None:
        """
        Create evidence_for_project edge from evidence_packages to projects.

        No-op if project_id is None.
        """
        if not project_id:
            log.info("evidence_for_project.skip_no_project_id")
            return

        edge_key = generate_edge_key(pkg_key, project_id, "for_project")
        self._db.collection("evidence_for_project").import_bulk(
            [
                {
                    "_key": edge_key,
                    "_from": f"evidence_packages/{pkg_key}",
                    "_to": f"projects/{project_id}",
                    "tenant_id": tenant_id,
                }
            ],
            on_duplicate="update",
        )
        log.info(
            "evidence_for_project.created",
            extra={"pkg_key": pkg_key, "project_id": project_id},
        )

    # ------------------------------------------------------------------
    # UC-SBOM-002: depends_on edges (component dependency graph)
    # ------------------------------------------------------------------

    def create_depends_on_edges(
        self,
        dependencies_raw: list[dict],
        scan_run_key: str,
        tenant_id: str,
    ) -> None:
        """
        Create depends_on edges from CycloneDX dependencies[] array.

        _from: components/<normalize_purl(ref)>
        _to:   components/<normalize_purl(dependsOn[i])>

        Dangling _to references are tolerated (component may not be in DB yet;
        ArangoDB allows dangling edges, matching component_has_vuln pattern).
        """
        edges: list[dict] = []
        for dep in dependencies_raw:
            from_purl = dep.get("ref")
            if not from_purl:
                log.debug("depends_on.skip_missing_ref", extra={"dep": dep})
                continue
            from_key = normalize_purl(from_purl)
            for to_purl in dep.get("dependsOn") or []:
                to_key = normalize_purl(to_purl)
                edge_key = generate_edge_key(from_key, to_key, "depends_on")
                edges.append(
                    {
                        "_key": edge_key,
                        "_from": f"components/{from_key}",
                        "_to": f"components/{to_key}",
                        "tenant_id": tenant_id,
                        "scan_run_id": scan_run_key,
                    }
                )
        if edges:
            self._db.collection("depends_on").import_bulk(edges, on_duplicate="update")
            log.info("depends_on.created", extra={"count": len(edges)})

    # ------------------------------------------------------------------
    # UC-011: detected_control_maps_to + control_in_component stubs
    # ------------------------------------------------------------------

    def create_detected_control_edges(
        self, detected_controls: list[dict], tenant_id: str
    ) -> None:
        """
        Create detected_control_maps_to and control_in_component edges.

        detected_control_maps_to: detected_controls/<fp> → oscal_controls/<key>
          - check_id looked up in CHECKOV_NIST_MAP (static curated mapping)
          - source: "rule_engine", confidence: 1.0
          - additionalProperties: False — no tenant_id/scan_run_id on edge docs

        control_in_component: detected_controls/<fp> → components/<purl_key>
          - only created when doc has a purl field (IaC Checkov output never has one;
            reserved for future scanners that emit purl alongside control evidence)
        """
        if not detected_controls:
            return

        maps_to_edges: list[dict] = []
        in_comp_edges: list[dict] = []

        for doc in detected_controls:
            fp = doc.get("fingerprint") or doc.get("_key", "")
            if not fp:
                continue

            check_id = doc.get("check_id", "")
            for ctrl_id in CHECKOV_NIST_MAP.get(check_id, []):
                ctrl_key = _normalize_oscal_key(ctrl_id)
                edge_key = generate_edge_key(fp, ctrl_key, "maps_to")
                maps_to_edges.append(
                    {
                        "_key": edge_key,
                        "_from": f"detected_controls/{fp}",
                        "_to": f"oscal_controls/{ctrl_key}",
                        "source": "rule_engine",
                        "confidence": 1.0,
                        "target_collection": "oscal_controls",
                    }
                )

            purl = doc.get("purl")
            if purl:
                purl_key = normalize_purl(purl)
                edge_key = generate_edge_key(fp, purl_key, "control_in_comp")
                in_comp_edges.append(
                    {
                        "_key": edge_key,
                        "_from": f"detected_controls/{fp}",
                        "_to": f"components/{purl_key}",
                        "source": "scanner",
                        "file_path": doc.get("file_path") or None,
                    }
                )

        if maps_to_edges:
            self._db.collection("detected_control_maps_to").import_bulk(
                maps_to_edges, on_duplicate="update"
            )
            log.info(
                "detected_control_maps_to.created",
                extra={"count": len(maps_to_edges)},
            )

        if in_comp_edges:
            self._db.collection("control_in_component").import_bulk(
                in_comp_edges, on_duplicate="update"
            )
            log.info(
                "control_in_component.created",
                extra={"count": len(in_comp_edges)},
            )
