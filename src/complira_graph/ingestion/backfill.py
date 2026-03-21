"""
BackfillAdapter — migrates legacy customer DB scan data to v2.2 reference DB.

Migration scope (UC-015):
  scan_sessions       → scan_runs        (customer DB → reference DB)
  customer_components → components       (customer DB → reference DB, global)

Field transformations (FIELD_MAP):
  customer_id  → tenant_id

Component documents have tenant_id removed: components are global in v2.2
(tenant_id lives on the project_uses_component edge, not the component doc).

Usage:
    from api.core.database import get_reference_db, get_customer_db
    adapter = BackfillAdapter(ref_db=get_reference_db())
    adapter.run(["customer_abc", "customer_xyz"])
"""

from __future__ import annotations

import logging
from typing import Optional

from arango.database import StandardDatabase

from complira_graph.schema.complira_kg_schema_v2_2 import LEGACY_COLLECTION_MAP, FIELD_MAP
from complira_graph.utils.keys import normalize_purl

log = logging.getLogger(__name__)


class BackfillAdapter:
    """
    One-shot backfill from legacy customer DBs into the v2.2 reference DB.

    Idempotent: import_bulk(on_duplicate="update") means re-running the backfill
    for the same customer_ids will update existing docs rather than duplicate them.
    """

    def __init__(self, ref_db: StandardDatabase) -> None:
        self._ref_db = ref_db

    def run(
        self,
        customer_ids: list[str],
        get_customer_db_fn=None,
    ) -> dict:
        """
        Migrate all specified customers from legacy customer DBs to reference DB.

        Args:
            customer_ids:      List of customer IDs to migrate
            get_customer_db_fn: Callable(customer_id) → StandardDatabase.
                                Defaults to api.core.database.get_customer_db.

        Returns:
            Summary dict with per-customer migration counts.
        """
        if get_customer_db_fn is None:
            from api.core.database import get_customer_db as get_customer_db_fn  # type: ignore[assignment]

        totals = {"scan_runs_migrated": 0, "components_migrated": 0, "errors": 0}
        per_customer: dict = {}

        for customer_id in customer_ids:
            try:
                cust_db = get_customer_db_fn(customer_id)
            except Exception:
                log.error(
                    "backfill.customer_db_unreachable",
                    extra={"customer_id": customer_id},
                    exc_info=True,
                )
                totals["errors"] += 1
                per_customer[customer_id] = {"error": "db_unreachable"}
                continue

            runs = self._migrate_scan_sessions(customer_id, cust_db)
            comps = self._migrate_components(customer_id, cust_db)
            per_customer[customer_id] = {
                "scan_runs_migrated": runs,
                "components_migrated": comps,
            }
            totals["scan_runs_migrated"] += runs
            totals["components_migrated"] += comps

        totals["per_customer"] = per_customer
        log.info(
            "backfill.complete",
            extra={
                "customer_ids": customer_ids,
                "scan_runs_migrated": totals["scan_runs_migrated"],
                "components_migrated": totals["components_migrated"],
                "errors": totals["errors"],
            },
        )
        return totals

    # ------------------------------------------------------------------
    # scan_sessions → scan_runs
    # ------------------------------------------------------------------

    def _migrate_scan_sessions(
        self, customer_id: str, cust_db: StandardDatabase
    ) -> int:
        """
        Copy scan_sessions from customer DB to scan_runs in reference DB.

        Transformations:
          customer_id  → tenant_id                       (FIELD_MAP)
          tool_name    → tools_invoked=[tool_name]        (v2.2 schema)
          findings_count → finding_counts.total           (v2.2 schema)
        """
        legacy_col = LEGACY_COLLECTION_MAP["scan_sessions"]   # "scan_runs"

        if not cust_db.has_collection("scan_sessions"):
            log.debug(
                "backfill.scan_sessions.missing",
                extra={"customer_id": customer_id},
            )
            return 0

        docs = list(cust_db.collection("scan_sessions").all())
        if not docs:
            return 0

        new_docs = []
        for doc in docs:
            new_doc = dict(doc)
            # customer_id → tenant_id
            if "customer_id" in new_doc:
                new_doc["tenant_id"] = new_doc.pop("customer_id")
            # tool_name → tools_invoked list
            tool_name = new_doc.pop("tool_name", None)
            if tool_name and "tools_invoked" not in new_doc:
                new_doc["tools_invoked"] = [tool_name]
            # findings_count → finding_counts.total
            fc = new_doc.pop("findings_count", None)
            if fc is not None and "finding_counts" not in new_doc:
                new_doc["finding_counts"] = {"total": fc}
            new_docs.append(new_doc)

        result = self._ref_db.collection(legacy_col).import_bulk(
            new_docs, on_duplicate="update"
        )
        count = result.get("created", 0) + result.get("updated", 0)
        log.info(
            "backfill.scan_sessions.migrated",
            extra={"customer_id": customer_id, "count": count},
        )
        return count

    # ------------------------------------------------------------------
    # customer_components → components (global)
    # ------------------------------------------------------------------

    def _migrate_components(
        self, customer_id: str, cust_db: StandardDatabase
    ) -> int:
        """
        Copy customer_components from customer DB to components in reference DB.

        Components become global in v2.2 — no tenant_id on document.
        _key is re-keyed by normalize_purl(purl).
        """
        legacy_col = LEGACY_COLLECTION_MAP["customer_components"]   # "components"

        if not cust_db.has_collection("customer_components"):
            log.debug(
                "backfill.customer_components.missing",
                extra={"customer_id": customer_id},
            )
            return 0

        docs = list(cust_db.collection("customer_components").all())
        if not docs:
            return 0

        new_docs = []
        for doc in docs:
            new_doc = dict(doc)
            purl = new_doc.get("purl")
            if not purl:
                log.warning(
                    "backfill.component.skip_no_purl",
                    extra={"customer_id": customer_id, "doc_key": doc.get("_key")},
                )
                continue
            # Re-key by purl (global dedup)
            new_doc["_key"] = normalize_purl(purl)
            # Remove tenant-scoped fields — components are global
            new_doc.pop("customer_id", None)
            new_doc.pop("tenant_id", None)
            # Remove ArangoDB internal fields other than _key
            new_doc.pop("_id", None)
            new_doc.pop("_rev", None)
            new_docs.append(new_doc)

        if not new_docs:
            return 0

        result = self._ref_db.collection(legacy_col).import_bulk(
            new_docs, on_duplicate="update"
        )
        count = result.get("created", 0) + result.get("updated", 0)
        log.info(
            "backfill.components.migrated",
            extra={"customer_id": customer_id, "count": count},
        )
        return count

    # ------------------------------------------------------------------
    # Optional: apply arbitrary FIELD_MAP transformation
    # ------------------------------------------------------------------

    @staticmethod
    def apply_field_map(doc: dict, field_map: Optional[dict] = None) -> dict:
        """
        Apply FIELD_MAP renames to a document dict.

        Uses the schema-level FIELD_MAP by default ({"customer_id": "tenant_id"}).
        """
        if field_map is None:
            field_map = FIELD_MAP
        result = dict(doc)
        for old_key, new_key in field_map.items():
            if old_key in result:
                result[new_key] = result.pop(old_key)
        return result
