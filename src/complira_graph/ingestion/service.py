"""
EvidenceIngestionService — orchestrates the full scan ingestion pipeline.

Entry point: EvidenceIngestionService.ingest_scan(tenant_id, tool_name, raw_payload, ...)
Returns:     ScanIngestResult

Pipeline sequence (UC-001 through UC-019):
  1. Create scan_runs doc (status=running)
  2. Run IngestionEngine → List[IngestionBundle]
  3. Route bundles: findings / detected_controls / component_has_vuln / audit_log
  4. Persist findings + detected_controls via repositories
  5. Ingest SBOM components (CycloneDX path, separate from engine)
  6. Append audit_log entries to scan_run
  7. Create all edges via EvidenceEdgeService
  8. Assemble evidence_packages doc + traceability edges
  9. Complete scan_runs doc with final counts
  10. Return ScanIngestResult

Fail-safe: any unhandled exception between create_run and complete_run calls
fail_run() to mark the scan record with status=failed.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from arango.database import StandardDatabase

from complira_graph.ingestion.ingestion_engine import IngestionEngine, IngestionBundle
from complira_graph.ingestion.repositories import (
    EvidenceRunRepository,
    EvidenceFindingRepository,
    EvidenceComponentRepository,
    EvidenceDetectedControlRepository,
)
from complira_graph.ingestion.edge_service import EvidenceEdgeService
from complira_graph.models.evidence import V22Component
from complira_graph.utils.keys import normalize_purl

log = logging.getLogger(__name__)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Result dataclass (returned to endpoint layer)
# ---------------------------------------------------------------------------

@dataclass
class ScanIngestResult:
    scan_run_id: str
    findings_count: int
    components_count: int
    status: str  # "completed" | "failed"


# ---------------------------------------------------------------------------
# EvidenceIngestionService
# ---------------------------------------------------------------------------

class EvidenceIngestionService:
    """
    Orchestrates scan evidence ingestion into the v2.2 reference DB.

    All repositories and the edge service receive the same StandardDatabase
    instance (reference DB) injected at construction time.
    """

    def __init__(self, db: StandardDatabase) -> None:
        self._db = db
        self._engine = IngestionEngine()
        self._run_repo = EvidenceRunRepository(db)
        self._finding_repo = EvidenceFindingRepository(db)
        self._component_repo = EvidenceComponentRepository(db)
        self._control_repo = EvidenceDetectedControlRepository(db)
        self._edge_svc = EvidenceEdgeService(db)

    # ------------------------------------------------------------------
    # Primary entry point
    # ------------------------------------------------------------------

    async def ingest_scan(
        self,
        tenant_id: str,
        tool_name: str,
        raw_payload: bytes,
        project_id: Optional[str] = None,
        repository_id: Optional[str] = None,
    ) -> ScanIngestResult:
        """
        Run the full ingestion pipeline for one scanner output.

        Args:
            tenant_id:      Tenant scope (= customer_id from auth context)
            tool_name:      Key in ADAPTER_REGISTRY (e.g. "semgrep", "checkov")
            raw_payload:    Raw scanner output as JSON bytes
            project_id:     Optional project context for edge creation
            repository_id:  Optional repository context stored on scan_run

        Returns:
            ScanIngestResult with scan_run_id, counts, and status

        Raises:
            ValueError:   Unsupported tool_name or malformed payload
            Exception:    Other errors (scan_run marked failed before re-raise)
        """
        # Step 1: Create scan run (status=running)
        scan_run = self._run_repo.create_run(
            tenant_id=tenant_id,
            project_id=project_id,
            repository_id=repository_id,
            tools_invoked=[tool_name],
        )
        scan_run_key: str = scan_run["_key"]

        try:
            result = await self._run_pipeline(
                scan_run_key=scan_run_key,
                tenant_id=tenant_id,
                tool_name=tool_name,
                raw_payload=raw_payload,
                project_id=project_id,
            )
            return result

        except Exception as e:
            log.exception(
                "evidence_ingestion.pipeline_failed",
                extra={"scan_run_id": scan_run_key, "tool": tool_name, "tenant_id": tenant_id},
            )
            self._run_repo.fail_run(scan_run_key, str(e))
            raise

    async def _run_pipeline(
        self,
        scan_run_key: str,
        tenant_id: str,
        tool_name: str,
        raw_payload: bytes,
        project_id: Optional[str],
    ) -> ScanIngestResult:
        """Pipeline body — all steps between create_run and complete_run."""

        # Step 2: Run IngestionEngine
        bundles = self._engine.process(
            tool_name=tool_name,
            raw_file=raw_payload,
            scan_run_id=scan_run_key,
            tenant_id=tenant_id,
            project_id=project_id,
        )

        # Step 3: Classify bundles by target collection
        finding_docs: list[dict] = []
        detected_control_docs: list[dict] = []
        sca_vuln_docs: list[dict] = []
        audit_entries: list[dict] = []
        all_edge_plans: list[dict] = []

        for bundle in bundles:
            col = bundle.collection
            if col == "scan_findings":
                finding_docs.append(bundle.document)
                all_edge_plans.extend(bundle.edges)
            elif col == "detected_controls":
                detected_control_docs.append(bundle.document)
            elif col == "component_has_vuln":
                sca_vuln_docs.append(bundle.document)
            elif col == "audit_log":
                audit_entries.append(bundle.document)

        # Step 4: Persist findings and detected controls
        if finding_docs:
            self._finding_repo.upsert_batch(finding_docs)

        if detected_control_docs:
            self._control_repo.upsert_batch(detected_control_docs)

        # Step 5: Append audit_log entries to scan_run (Checkov SKIPPED)
        if audit_entries:
            self._run_repo.append_audit_log(scan_run_key, audit_entries)

        # Step 6: Create all edges
        self._edge_svc.create_all_edges(
            finding_docs=finding_docs,
            component_docs=[],          # SBOM components handled via ingest_sbom()
            sca_vuln_docs=sca_vuln_docs,
            detected_control_docs=detected_control_docs,
            edge_plans=all_edge_plans,
            tenant_id=tenant_id,
            project_id=project_id,
        )

        # Step 7: Assemble evidence package
        if finding_docs:
            pkg_key = self._assemble_evidence_package(
                scan_run_key=scan_run_key,
                finding_docs=finding_docs,
                tenant_id=tenant_id,
                project_id=project_id,
            )
            self._edge_svc.create_evidence_finding_edges(pkg_key, finding_docs, tenant_id)
            if project_id:
                self._edge_svc.create_evidence_project_edge(pkg_key, project_id, tenant_id)

        # Step 8: Complete scan run
        finding_counts = self._count_by_severity(finding_docs)
        self._run_repo.complete_run(
            scan_run_key=scan_run_key,
            finding_counts=finding_counts,
            status="completed",
        )

        log.info(
            "evidence_ingestion.completed",
            extra={
                "scan_run_id": scan_run_key,
                "tool": tool_name,
                "tenant_id": tenant_id,
                "findings": len(finding_docs),
                "controls": len(detected_control_docs),
                "audit": len(audit_entries),
            },
        )
        return ScanIngestResult(
            scan_run_id=scan_run_key,
            findings_count=len(finding_docs),
            components_count=0,
            status="completed",
        )

    # ------------------------------------------------------------------
    # SBOM component ingestion (separate from finding engine path)
    # ------------------------------------------------------------------

    async def ingest_sbom(
        self,
        tenant_id: str,
        components_raw: list[dict[str, Any]],
        sbom_format: Optional[str] = None,
        dependencies_raw: Optional[list[dict[str, Any]]] = None,
        project_id: Optional[str] = None,
        repository_id: Optional[str] = None,
        scan_run_key: Optional[str] = None,
    ) -> ScanIngestResult:
        """
        Ingest SBOM components (CycloneDX / SPDX) into the components collection.

        Does not go through IngestionEngine — components are not findings.
        Creates project_uses_component edges if project_id is available.

        Args:
            tenant_id:        Tenant scope
            components_raw:   List of raw component dicts from the SBOM parser
            sbom_format:      "cyclonedx" | "spdx" (stored on component doc)
            dependencies_raw: CycloneDX dependencies[] array (ref → dependsOn[]); None treated as empty
            project_id:       Optional project for project_uses_component edges
            repository_id:    Optional repository context for scan_run
            scan_run_key:     If provided, update existing run; otherwise create new one

        Returns:
            ScanIngestResult with components_count
        """
        create_new_run = scan_run_key is None
        if create_new_run:
            scan_run = self._run_repo.create_run(
                tenant_id=tenant_id,
                project_id=project_id,
                repository_id=repository_id,
                tools_invoked=["sbom"],
            )
            scan_run_key = scan_run["_key"]

        try:
            component_docs = self._build_component_docs(components_raw, sbom_format)

            if component_docs:
                self._component_repo.upsert_batch(component_docs)

            if component_docs and project_id:
                self._edge_svc.create_project_uses_component_edges(
                    component_docs, project_id, tenant_id
                )

            if dependencies_raw:
                self._edge_svc.create_depends_on_edges(
                    dependencies_raw=dependencies_raw,
                    scan_run_key=scan_run_key,
                    tenant_id=tenant_id,
                )

            if create_new_run:
                self._run_repo.complete_run(
                    scan_run_key=scan_run_key,
                    finding_counts={"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0},
                    status="completed",
                    components_count=len(component_docs),
                )

            return ScanIngestResult(
                scan_run_id=scan_run_key,
                findings_count=0,
                components_count=len(component_docs),
                status="completed",
            )

        except Exception as e:
            if create_new_run:
                self._run_repo.fail_run(scan_run_key, str(e))
            raise

    def _build_component_docs(
        self, raw_components: list[dict], sbom_format: Optional[str]
    ) -> list[dict]:
        """
        Convert raw parser component dicts to V22Component model dicts.

        Generates fallback purl for components without a purl field.
        Skips components with no purl and no name.
        """
        docs: list[dict] = []
        for raw in raw_components:
            purl = raw.get("purl") or raw.get("packageUrl")
            name = raw.get("name", "").strip()
            version = raw.get("version", "")

            if not purl:
                if name:
                    purl = f"pkg:generic/{name}@{version}" if version else f"pkg:generic/{name}"
                    log.info(
                        "sbom.generated_fallback_purl",
                        extra={"name": name, "purl": purl},
                    )
                else:
                    log.warning(
                        "sbom.skip_component_no_purl_no_name",
                        extra={"raw_keys": list(raw.keys())},
                    )
                    continue

            # supplier
            supplier_raw = raw.get("supplier")
            supplier = (
                supplier_raw.get("name")
                if isinstance(supplier_raw, dict)
                else None
            )

            # licenses — full list of expression strings
            licenses_raw = raw.get("licenses") or []
            licenses: list[str] = [
                entry
                for lic in licenses_raw
                if isinstance(lic, dict)
                for entry in [
                    (lic.get("license") or {}).get("id")
                    or (lic.get("license") or {}).get("name")
                ]
                if entry
            ]

            # hashes — list of {alg, content} dicts
            hashes_raw = raw.get("hashes") or []
            hashes: list[dict] = [
                {"alg": h.get("alg"), "content": h.get("content")}
                for h in hashes_raw
                if isinstance(h, dict) and h.get("alg") and h.get("content")
            ]

            # legacy single-license field (first entry, preserved for backward compat)
            legacy_license = licenses[0] if licenses else (
                raw.get("license") or None
            )

            comp = V22Component(
                key=normalize_purl(purl),
                purl=purl,
                name=name or purl,
                version=version or None,
                type=raw.get("type"),
                purl_source="sbom",
                sbom_format=sbom_format,
                cpe=raw.get("cpe"),
                license=legacy_license,
                supplier=supplier or None,
                licenses=licenses or None,
                hashes=hashes or None,
            )
            docs.append(comp.model_dump(by_alias=True, exclude_none=True))
        return docs

    # ------------------------------------------------------------------
    # Evidence package assembly (UC-012 / UC-013)
    # ------------------------------------------------------------------

    def _assemble_evidence_package(
        self,
        scan_run_key: str,
        finding_docs: list[dict],
        tenant_id: str,
        project_id: Optional[str],
    ) -> str:
        """
        Insert evidence_packages document and return its _key.

        The evidence_links_finding and evidence_for_project edges are created
        by EvidenceEdgeService after this call.
        """
        pkg_key = uuid.uuid4().hex
        pkg_doc = {
            "_key": pkg_key,
            "package_id": pkg_key,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "scan_run_id": scan_run_key,
            "finding_count": len(finding_docs),
            "component_count": 0,
            "package_type": "scan_evidence",
            "assembled_at": _utcnow(),
        }
        self._db.collection("evidence_packages").insert(pkg_doc)
        log.info(
            "evidence_package.created",
            extra={"pkg_key": pkg_key, "scan_run_id": scan_run_key},
        )
        return pkg_key

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _count_by_severity(findings: list[dict]) -> dict:
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        for f in findings:
            sev = (f.get("severity") or "").lower()
            if sev in counts:
                counts[sev] += 1
        return counts
