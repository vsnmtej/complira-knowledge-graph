"""
complira_graph.cse.technique_resolver
=======================================
Resolves CVE → ATT&CK technique(s) via graph path or CVSS severity fallback.

Called once during simulation prepare() in the main process.
Stores resolved techniques in simulation_config.json["entity_techniques"].
The subprocess reads them at runtime — no DB calls in the hot path.

Graph path:  CVE → has_weakness → CWE → capec_relates_to_cwe → CAPEC
             → capec_maps_to_attack → ATT&CK technique
Fallback:    CVSS severity bucket (constants.TECHNIQUE_BUCKETS)
"""

from __future__ import annotations

import structlog
from typing import TYPE_CHECKING, Any

from complira_graph.cse.constants import TECHNIQUE_BUCKETS

if TYPE_CHECKING:
    from arango.database import StandardDatabase
    from complira_graph.cse.graph_reader import CyberEntityNode

log = structlog.get_logger(__name__)

_AQL_TECHNIQUE_FROM_CVE = """
FOR v IN vulnerabilities
    FILTER v._key == @cve_key
    FOR cwe IN 1..1 OUTBOUND v has_weakness
        FOR capec IN 1..1 INBOUND cwe capec_relates_to_cwe
            FOR tech IN 1..1 OUTBOUND capec capec_maps_to_attack
                FILTER tech.technique_id != null
                RETURN DISTINCT tech.technique_id
"""


class TechniqueResolver:
    """
    Resolves CVE entity_id → list[technique_id] with resolution source tag.

    Usage:
        resolver = TechniqueResolver(db)
        entity_techniques = resolver.resolve_all(entities)
        # {"CVE_2021_44228": ["T1190", "T1059"], ...}
    """

    def __init__(self, db: "StandardDatabase") -> None:
        self._db = db

    def resolve(self, cve_key: str, cvss: float) -> tuple[list[str], str]:
        """
        Returns (technique_ids, source) where source is "graph" or "fallback".
        Always returns at least one technique.
        """
        try:
            cursor = self._db.aql.execute(
                _AQL_TECHNIQUE_FROM_CVE,
                bind_vars={"cve_key": cve_key},
            )
            results: list[str] = [r for r in cursor if r]
            if results:
                log.debug(
                    "technique_resolver_graph",
                    cve=cve_key,
                    techniques=results[:3],
                )
                return results, "graph"
        except Exception as exc:
            log.warning("technique_resolver_graph_error", cve=cve_key, error=str(exc))

        # Fallback: severity bucket
        bucket = _severity_bucket(cvss)
        techniques = TECHNIQUE_BUCKETS[bucket]
        log.debug(
            "technique_resolver_fallback",
            cve=cve_key,
            cvss=cvss,
            bucket=bucket,
            techniques=techniques,
        )
        return techniques, "fallback"

    def resolve_all(self, entities: "list[CyberEntityNode]") -> dict[str, list[str]]:
        """
        Resolve all CVE entities in the attack surface.
        Returns dict mapping entity_id → list[technique_id].
        """
        entity_techniques: dict[str, list[str]] = {}
        for e in entities:
            if e.entity_type != "cve":
                continue
            techniques, source = self.resolve(e.entity_id, e.severity)
            entity_techniques[e.entity_id] = techniques
        log.info(
            "technique_resolver_complete",
            total=len(entity_techniques),
            graph_resolved=sum(
                1 for eid in entity_techniques
                if self._is_graph_resolved(eid, entity_techniques[eid])
            ),
        )
        return entity_techniques

    def _is_graph_resolved(self, cve_key: str, techniques: list[str]) -> bool:
        """Heuristic: if technique list differs from all fallback buckets it's graph-resolved."""
        for bucket_techs in TECHNIQUE_BUCKETS.values():
            if set(techniques) == set(bucket_techs):
                return False
        return True


def _severity_bucket(cvss: float) -> str:
    if cvss >= 9.0:
        return "critical"
    if cvss >= 7.0:
        return "high"
    if cvss >= 4.0:
        return "medium"
    return "low"
