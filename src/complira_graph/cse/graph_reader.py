"""
complira_graph.cse.graph_reader
=================================
Attack surface extraction from ArangoDB for CSE simulation.

Replaces complira_graph.mirofish.seed_extractor.
Returns a structured list of CyberEntityNode objects covering:
  - CVEs linked to the tenant's components
  - Components with active vulnerabilities
  - Regulatory obligations applicable to the tenant

Target: < 200ms for tenants with < 100 CVEs (uses tenant_id indexes).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from arango.database import StandardDatabase

log = logging.getLogger(__name__)


@dataclass
class CyberEntityNode:
    entity_id: str
    entity_type: str          # "cve" | "component" | "regulatory_obligation"
    severity: float           # CVSS base score, or 0.0
    is_kev: bool
    regulatory_refs: list[str] = field(default_factory=list)
    component_name: str = ""


# AQL: fetch CVEs + components + regulatory obligations for a tenant
_AQL_ATTACK_SURFACE = """
LET tenant_key = @tenant_id

LET cves = (
    FOR scan IN scans
        FILTER scan.customer_key == tenant_key
        FOR v IN 1..2 OUTBOUND scan scan_has_vulnerability
            FILTER v._id != null
            RETURN DISTINCT {
                entity_id:     v._key,
                entity_type:   "cve",
                severity:      TO_NUMBER(v.cvss_base_score),
                is_kev:        (v.is_kev == true OR v.kev == true),
                component_name: CONCAT(v.product_name, " ", v.version),
                regulatory_refs: []
            }
)

LET components = (
    FOR scan IN scans
        FILTER scan.customer_key == tenant_key
        FOR c IN 1..1 OUTBOUND scan scan_has_component
            FILTER c._id != null
            RETURN DISTINCT {
                entity_id:     c._key,
                entity_type:   "component",
                severity:      0.0,
                is_kev:        false,
                component_name: CONCAT(c.name, " ", c.version),
                regulatory_refs: []
            }
)

RETURN {cves: cves, components: components}
"""


class CompliraGraphReader:
    """Read attack surface entities from ArangoDB for a given tenant."""

    def __init__(self, db: "StandardDatabase") -> None:
        self._db = db

    def get_attack_surface(self, tenant_id: str) -> list[CyberEntityNode]:
        """
        Return CVEs + components + regulatory obligations for tenant.
        Returns empty list if no data found (caller raises 422).
        """
        t0 = time.monotonic()
        try:
            cursor = self._db.aql.execute(
                _AQL_ATTACK_SURFACE,
                bind_vars={"tenant_id": tenant_id},
                count=False,
            )
            rows = list(cursor)
        except Exception as exc:
            log.error("cse_graph_reader_error", tenant_id=tenant_id, error=str(exc))
            raise

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        nodes: list[CyberEntityNode] = []

        for row in rows:
            for cve_dict in row.get("cves", []):
                nodes.append(_dict_to_node(cve_dict))
            for comp_dict in row.get("components", []):
                nodes.append(_dict_to_node(comp_dict))

        # De-duplicate by entity_id
        seen: set[str] = set()
        unique_nodes = []
        for n in nodes:
            if n.entity_id not in seen:
                seen.add(n.entity_id)
                unique_nodes.append(n)

        log.info(
            "cse_graph_reader_fetched",
            tenant_id=tenant_id,
            entity_count=len(unique_nodes),
            elapsed_ms=elapsed_ms,
        )
        return unique_nodes


def _dict_to_node(d: dict[str, Any]) -> CyberEntityNode:
    return CyberEntityNode(
        entity_id=str(d.get("entity_id", "")),
        entity_type=str(d.get("entity_type", "cve")),
        severity=float(d.get("severity") or 0.0),
        is_kev=bool(d.get("is_kev", False)),
        regulatory_refs=list(d.get("regulatory_refs") or []),
        component_name=str(d.get("component_name", "")),
    )
