"""
CompactionPipeline — UC-008 Finding Compaction and Risk Scoring.

Reads all enriched findings for a scan run, groups by CWE (with parent roll-up
for CWEs that lack regulatory mappings), computes composite risk scores, assigns
compaction_group_id, marks canonical findings, and assigns cluster_rank per group.

Status transition: enriched → compacted

Risk score formula:
  risk_score = (cvss_base/10)*0.4 + epss_score*0.3 + (1.0 if in_kev else 0)*0.2
               + (0.1 if d3fend_techniques else 0.0)*0.1
"""

from __future__ import annotations

import logging

from arango.database import StandardDatabase

from complira_graph.ingestion.scan_enrichment_repository import ScanEnrichmentRepository
from complira_graph.utils.keys import normalize_cwe_id

log = logging.getLogger(__name__)


class CompactionPipeline:
    """
    UC-008 Finding Compaction pipeline stage.

    Requires the full set of findings in memory (needs global view for cluster ranking).
    Accumulates all batches before computing groups and ranks.
    """

    def __init__(self, db: StandardDatabase, repo: ScanEnrichmentRepository) -> None:
        self._db = db
        self._repo = repo

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self, scan_run_id: str, tenant_id: str) -> None:
        """
        Entry point for UC-008.

        Full call sequence:
          1. Accumulate all enriched findings into memory
          2. Collect distinct CWE keys from cwe_chain fields
          3. aql_get_cwe_parent_map(cwe_keys) → cwe_parent_map
          4. _assign_compaction_groups(all_findings, cwe_parent_map) → group_map
          5. _compute_risk_scores(all_findings) → risk_score_map
          6. _compute_cluster_ranks(all_findings, group_map, risk_score_map) → rank_map
          7. _build_compaction_updates → repo.bulk_update_findings
          8. update scan_run status to "compacted"
        """
        log.info(
            "compaction_pipeline.start",
            extra={"scan_run_id": scan_run_id, "tenant_id": tenant_id},
        )

        # Accumulate all findings (needs global view for ranking)
        all_findings: list[dict] = []
        for batch in self._repo.fetch_findings_for_run(scan_run_id, tenant_id):
            all_findings.extend(batch)

        if not all_findings:
            log.info(
                "compaction_pipeline.no_findings",
                extra={"scan_run_id": scan_run_id},
            )
            self._repo.update_scan_run_status(scan_run_id, "compacted")
            return

        # Collect unique CWE keys from cwe_chain fields
        cwe_key_set: set[str] = set()
        for finding in all_findings:
            for cwe_id in finding.get("cwe_chain") or []:
                if cwe_id:
                    cwe_key_set.add(normalize_cwe_id(cwe_id))

        cwe_parent_map: dict[str, str] = {}
        if cwe_key_set:
            cwe_parent_map = self._repo.aql_get_cwe_parent_map(list(cwe_key_set))

        group_map = self._assign_compaction_groups(all_findings, cwe_parent_map)
        risk_score_map = self._compute_risk_scores(all_findings)
        rank_map = self._compute_cluster_ranks(all_findings, group_map, risk_score_map)
        canonical_map = self._canonical_map(all_findings, group_map)

        updates = self._build_compaction_updates(
            all_findings, group_map, risk_score_map, rank_map, canonical_map
        )
        self._repo.bulk_update_findings(updates)

        self._repo.update_scan_run_status(scan_run_id, "compacted")
        log.info(
            "compaction_pipeline.complete",
            extra={
                "scan_run_id": scan_run_id,
                "findings": len(all_findings),
                "groups": len(set(group_map.values())),
            },
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_risk_score(self, finding: dict) -> float:
        """
        Compute composite risk score for a single finding.

        Formula:
          risk_score = (cvss_base/10)*0.4 + epss_score*0.3
                       + (1.0 if in_kev else 0.0)*0.2
                       + (0.1 if d3fend_techniques else 0.0)*0.1

        Findings without cve_id return 0.0.
        """
        if not finding.get("cve_id"):
            return 0.0

        cvss_base = float(finding.get("cvss_base") or 0.0)
        epss_score = float(finding.get("epss_score") or 0.0)
        in_kev = 1.0 if finding.get("in_kev") else 0.0
        d3fend = finding.get("d3fend_techniques")
        exploit_bonus = 0.1 if d3fend else 0.0

        cvss_normalized = cvss_base / 10.0
        risk = (
            cvss_normalized * 0.4
            + epss_score * 0.3
            + in_kev * 0.2
            + exploit_bonus * 0.1
        )
        # Clamp to [0.0, 1.0]
        return max(0.0, min(1.0, risk))

    def _compute_risk_scores(self, findings: list[dict]) -> dict[str, float]:
        """Return {fingerprint -> risk_score} for all findings."""
        return {
            (f.get("_key") or f.get("fingerprint", "")): self._compute_risk_score(f)
            for f in findings
        }

    def _assign_compaction_groups(
        self,
        findings: list[dict],
        cwe_parent_map: dict[str, str],
    ) -> dict[str, str]:
        """
        Assign compaction_group_id to each finding.

        Logic:
          - If cwe_chain non-empty:
              primary_cwe = normalize_cwe_id(cwe_chain[0])
              group_id = cwe_parent_map.get(primary_cwe, primary_cwe)
          - If cwe_chain empty:
              group_id = "no_cwe_<fingerprint>"

        Returns {fingerprint -> group_id}.
        """
        group_map: dict[str, str] = {}
        for finding in findings:
            fingerprint = finding.get("_key") or finding.get("fingerprint", "")
            cwe_chain = finding.get("cwe_chain") or []
            if cwe_chain:
                primary = normalize_cwe_id(cwe_chain[0])
                group_id = cwe_parent_map.get(primary, primary)
            else:
                group_id = f"no_cwe_{fingerprint}"
            group_map[fingerprint] = group_id
        return group_map

    def _canonical_map(
        self,
        findings: list[dict],
        group_map: dict[str, str],
    ) -> dict[str, str]:
        """
        For each group, select the canonical finding (lowest fingerprint alphabetically).

        Returns {fingerprint -> canonical_fingerprint_for_group}.
        """
        groups: dict[str, list[str]] = {}
        for finding in findings:
            fp = finding.get("_key") or finding.get("fingerprint", "")
            group_id = group_map.get(fp, fp)
            groups.setdefault(group_id, []).append(fp)

        canonical: dict[str, str] = {}
        for group_id, fps in groups.items():
            fps_sorted = sorted(fps)
            canon = fps_sorted[0]
            for fp in fps:
                canonical[fp] = canon
        return canonical

    def _compute_cluster_ranks(
        self,
        findings: list[dict],
        group_map: dict[str, str],
        risk_score_map: dict[str, float],
    ) -> dict[str, int]:
        """
        Assign cluster_rank per group (rank 1 = highest risk group).

        Ranking:
          - Per group: max_risk = max(risk_scores for findings in group)
          - Sort groups by max_risk descending; ties broken by group_id alphabetically
          - Assign rank 1..N
          - All findings in a group share the group's rank

        Returns {fingerprint -> cluster_rank}.
        """
        # Build group → fingerprints
        group_fps: dict[str, list[str]] = {}
        for finding in findings:
            fp = finding.get("_key") or finding.get("fingerprint", "")
            group_id = group_map.get(fp, fp)
            group_fps.setdefault(group_id, []).append(fp)

        # Per-group max risk
        group_max_risk: dict[str, float] = {}
        for group_id, fps in group_fps.items():
            group_max_risk[group_id] = max(
                risk_score_map.get(fp, 0.0) for fp in fps
            )

        # Sort groups: desc by max_risk, then asc by group_id for tiebreak
        sorted_groups = sorted(
            group_fps.keys(),
            key=lambda g: (-group_max_risk[g], g),
        )

        rank_map: dict[str, int] = {}
        for rank, group_id in enumerate(sorted_groups, start=1):
            for fp in group_fps[group_id]:
                rank_map[fp] = rank
        return rank_map

    def _build_compaction_updates(
        self,
        findings: list[dict],
        group_map: dict[str, str],
        risk_score_map: dict[str, float],
        rank_map: dict[str, int],
        canonical_map: dict[str, str],
    ) -> list[dict]:
        """
        Build update dicts for scan_findings compaction write-back.

        Fields written: risk_score, compaction_group_id, cluster_rank, compacted.
        compacted=False for the canonical finding in each group; True for the rest.
        """
        updates: list[dict] = []
        for finding in findings:
            fp = finding.get("_key") or finding.get("fingerprint", "")
            is_canonical = canonical_map.get(fp) == fp
            updates.append(
                {
                    "_key": fp,
                    "risk_score": risk_score_map.get(fp, 0.0),
                    "compaction_group_id": group_map.get(fp, fp),
                    "cluster_rank": rank_map.get(fp, 1),
                    "compacted": not is_canonical,
                }
            )
        return updates

    # Keep singular form as alias for test compatibility
    _cluster_and_rank = _compute_cluster_ranks
