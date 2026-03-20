"""
Evidence ingestion repositories.

Responsibilities:
- EvidenceRunRepository       — scan_runs lifecycle (create / complete / fail / audit_log)
- EvidenceFindingRepository   — scan_findings bulk upsert (fingerprint _key idempotency)
- EvidenceComponentRepository — components bulk upsert (purl _key global dedup)
- EvidenceDetectedControlRepository — detected_controls bulk upsert

All repositories accept a StandardDatabase instance (dependency injection) so
the service layer can pass the reference DB and tests can pass a fake.

Idempotency contract: every upsert_batch call uses import_bulk(on_duplicate="update"),
producing identical _keys on re-ingestion and updating existing docs rather than
creating duplicates.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from arango.database import StandardDatabase

from complira_graph.models.evidence import ScanRun

log = logging.getLogger(__name__)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# EvidenceRunRepository
# ---------------------------------------------------------------------------

class EvidenceRunRepository:
    """
    scan_runs collection — one document per pipeline invocation.

    Each scan run is created with status=running, then updated to
    status=completed or status=failed when the pipeline finishes.
    SKIPPED Checkov entries are appended to the audit_log array via AQL.
    """

    def __init__(self, db: StandardDatabase) -> None:
        self._db = db
        self._col = db.collection("scan_runs")

    def create_run(
        self,
        tenant_id: str,
        project_id: Optional[str] = None,
        repository_id: Optional[str] = None,
        tools_invoked: Optional[list[str]] = None,
    ) -> dict:
        """
        Insert a new scan_runs document with status=running.

        Returns the inserted document (includes _key).
        """
        run = ScanRun(
            key=str(uuid.uuid4()),
            tenant_id=tenant_id,
            project_id=project_id,
            repository_id=repository_id,
            tools_invoked=tools_invoked or [],
        )
        doc = run.model_dump(by_alias=True, exclude_none=False)
        meta = self._col.insert(doc, return_new=True)
        log.info(
            "evidence_run.created",
            extra={"scan_run_id": meta["_key"], "tenant_id": tenant_id},
        )
        return meta["new"]

    def complete_run(
        self,
        scan_run_key: str,
        finding_counts: dict,
        status: str = "completed",
        compliance_score: Optional[float] = None,
        violated_requirements: Optional[list[str]] = None,
        components_count: int = 0,
    ) -> None:
        """Update scan_runs doc to completed/failed with final counts."""
        self._col.update(
            {
                "_key": scan_run_key,
                "status": status,
                "finding_counts": finding_counts,
                "compliance_score": compliance_score,
                "violated_requirements": violated_requirements or [],
                "components_count": components_count,
                "completed_at": _utcnow(),
            }
        )
        log.info(
            "evidence_run.completed",
            extra={"scan_run_id": scan_run_key, "status": status},
        )

    def fail_run(self, scan_run_key: str, error_message: str) -> None:
        """Mark scan_runs doc as failed with error message."""
        self._col.update(
            {
                "_key": scan_run_key,
                "status": "failed",
                "error_message": error_message,
                "completed_at": _utcnow(),
            }
        )
        log.error(
            "evidence_run.failed",
            extra={"scan_run_id": scan_run_key, "error": error_message},
        )

    def append_audit_log(self, scan_run_key: str, entries: list[dict]) -> None:
        """
        Append SKIPPED check entries to scan_run.audit_log (AQL APPEND).

        AQL APPEND preserves existing entries and adds new ones atomically.
        No-op if entries is empty.
        """
        if not entries:
            return
        self._db.aql.execute(
            """
            LET current = DOCUMENT("scan_runs", @key)
            UPDATE @key
            WITH { audit_log: APPEND(current.audit_log, @entries) }
            IN scan_runs
            """,
            bind_vars={"key": scan_run_key, "entries": entries},
        )
        log.debug(
            "evidence_run.audit_log_appended",
            extra={"scan_run_id": scan_run_key, "count": len(entries)},
        )


# ---------------------------------------------------------------------------
# EvidenceFindingRepository
# ---------------------------------------------------------------------------

class EvidenceFindingRepository:
    """
    scan_findings collection — normalised findings, fingerprint-keyed.

    Fingerprint _key enables on_duplicate=update idempotency: re-ingesting
    the same finding updates the existing document rather than duplicating.
    """

    def __init__(self, db: StandardDatabase) -> None:
        self._col = db.collection("scan_findings")

    def upsert_batch(self, documents: list[dict]) -> dict:
        """
        Bulk upsert scan_findings documents.

        Returns import_bulk result: {"created": N, "updated": N, ...}.
        """
        if not documents:
            return {"created": 0, "updated": 0, "ignored": 0, "errors": 0}
        result = self._col.import_bulk(documents, on_duplicate="update")
        log.info(
            "evidence_findings.upserted",
            extra={
                "created": result.get("created", 0),
                "updated": result.get("updated", 0),
                "errors": result.get("errors", 0),
            },
        )
        if result.get("errors", 0):
            log.error(
                "evidence_findings.upsert_errors",
                extra={"details": result.get("details", [])[:5]},
            )
        return result


# ---------------------------------------------------------------------------
# EvidenceComponentRepository
# ---------------------------------------------------------------------------

class EvidenceComponentRepository:
    """
    components collection — global, purl-keyed, no tenant_id on document.

    Components are shared across all tenants; the project_uses_component edge
    carries tenant_id. Re-ingesting the same purl updates the existing global
    component document.
    """

    def __init__(self, db: StandardDatabase) -> None:
        self._col = db.collection("components")

    def upsert_batch(self, documents: list[dict]) -> dict:
        """
        Bulk upsert components documents (purl _key — global dedup).

        Returns import_bulk result.
        """
        if not documents:
            return {"created": 0, "updated": 0, "ignored": 0, "errors": 0}
        result = self._col.import_bulk(documents, on_duplicate="update")
        log.info(
            "evidence_components.upserted",
            extra={
                "created": result.get("created", 0),
                "updated": result.get("updated", 0),
            },
        )
        return result


# ---------------------------------------------------------------------------
# EvidenceDetectedControlRepository
# ---------------------------------------------------------------------------

class EvidenceDetectedControlRepository:
    """
    detected_controls collection — positive IaC compliance evidence.

    Populated from Checkov PASSED checks and future Semgrep control-hit rules.
    _key is fingerprint-based (check_id + file_path + resource_address).
    """

    def __init__(self, db: StandardDatabase) -> None:
        self._col = db.collection("detected_controls")

    def upsert_batch(self, documents: list[dict]) -> dict:
        """
        Bulk upsert detected_controls documents.

        Returns import_bulk result.
        """
        if not documents:
            return {"created": 0, "updated": 0, "ignored": 0, "errors": 0}
        result = self._col.import_bulk(documents, on_duplicate="update")
        log.info(
            "evidence_detected_controls.upserted",
            extra={
                "created": result.get("created", 0),
                "updated": result.get("updated", 0),
            },
        )
        return result
