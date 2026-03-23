"""
EPSSVelocityPipeline — UC-012 EPSS Velocity Detection stage.

For each scan_findings document with a non-null cve_id, fetches the last 30 days
of EPSS score history and computes a linear regression slope to classify trend.

Classification thresholds:
  slope * 7 > 0.05  → "rising"
  slope * 7 < -0.05 → "falling"
  else              → "stable"

Writes per-finding:
  - epss_velocity           float (regression slope per day; 0.0 for <2 data points)
  - epss_trend              "rising" | "stable" | "falling"
  - epss_velocity_computed_at  ISO 8601 UTC timestamp

Findings with no cve_id receive epss_velocity=0.0 and epss_trend="stable".

Uses pure Python linear regression — no numpy/scipy dependency.
Uses ScanEnrichmentRepository for all reads and writes (no new repository needed).

Status transition: blast_radius_computed → velocity_computed
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from arango.database import StandardDatabase

from complira_graph.ingestion.scan_enrichment_repository import ScanEnrichmentRepository

log = logging.getLogger(__name__)

_RISING_THRESHOLD = 0.05    # weekly_delta > this → rising
_FALLING_THRESHOLD = -0.05  # weekly_delta < this → falling
_HISTORY_DAYS = 30


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_cve_key(cve_id: str) -> str:
    """Convert "CVE-2024-1234" to ArangoDB key format "CVE_2024_1234"."""
    return cve_id.replace("-", "_")


class EPSSVelocityPipeline:
    """
    UC-012: EPSS velocity detection stage.

    Uses only ScanEnrichmentRepository — reads via aql_get_epss_history_batch()
    and writes via bulk_update_findings() and update_scan_run_status().
    """

    def __init__(
        self,
        db: StandardDatabase,
        repo: ScanEnrichmentRepository,
    ) -> None:
        self._db = db
        self._repo = repo

    def run(self, scan_run_id: str, tenant_id: str) -> None:
        """
        Compute EPSS velocity for all findings in scan_run_id.

        Trigger: scan_run.status == "blast_radius_computed"
        Result:  scan_run.status = "velocity_computed" on success
        """
        log.info(
            "epss_velocity_pipeline.start",
            extra={"scan_run_id": scan_run_id, "tenant_id": tenant_id},
        )

        cve_key_to_fingerprints: dict[str, list[str]] = {}
        no_cve_fingerprints: list[str] = []

        for batch in self._repo.fetch_findings_for_run(scan_run_id, tenant_id):
            for finding in batch:
                cve_id = finding.get("cve_id") or ""
                if cve_id:
                    cve_key = _normalize_cve_key(cve_id)
                    cve_key_to_fingerprints.setdefault(cve_key, []).append(finding["_key"])
                else:
                    no_cve_fingerprints.append(finding["_key"])

        cutoff_date = (
            datetime.now(timezone.utc) - timedelta(days=_HISTORY_DAYS)
        ).strftime("%Y-%m-%d")

        history_map = self._repo.aql_get_epss_history_batch(
            list(cve_key_to_fingerprints.keys()),
            cutoff_date,
        )

        all_updates: list[dict] = []

        for cve_key, fingerprints in cve_key_to_fingerprints.items():
            history = history_map.get(cve_key, [])
            slope = self._compute_slope(history)
            trend = self._classify_trend(slope)
            all_updates.extend(self._build_velocity_updates(fingerprints, slope, trend))

        all_updates.extend(self._build_zero_velocity_updates(no_cve_fingerprints))

        self._repo.bulk_update_findings(all_updates)
        self._repo.update_scan_run_status(
            scan_run_id,
            "velocity_computed",
            extra_fields={"velocity_computed_at": _utcnow()},
        )
        log.info(
            "epss_velocity_pipeline.complete",
            extra={
                "scan_run_id": scan_run_id,
                "unique_cves": len(cve_key_to_fingerprints),
                "no_cve_count": len(no_cve_fingerprints),
                "total_updates": len(all_updates),
            },
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_slope(self, history: list[dict]) -> float:
        """
        Linear regression slope over EPSS history time series.

        history: list of {"score": float, "date": "YYYY-MM-DD"} sorted ascending.
        Returns 0.0 if fewer than 2 data points or degenerate input.
        Pure Python — no numpy.
        """
        n = len(history)
        if n < 2:
            return 0.0

        xs = list(range(n))
        ys = [h["score"] for h in history]
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        numerator = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
        denominator = sum((xs[i] - mean_x) ** 2 for i in range(n))

        if denominator == 0:
            return 0.0
        return numerator / denominator

    def _classify_trend(self, slope: float) -> str:
        weekly_delta = slope * 7
        if weekly_delta > _RISING_THRESHOLD:
            return "rising"
        if weekly_delta < _FALLING_THRESHOLD:
            return "falling"
        return "stable"

    def _build_velocity_updates(
        self,
        fingerprints: list[str],
        slope: float,
        trend: str,
    ) -> list[dict]:
        now = _utcnow()
        return [
            {
                "_key": fp,
                "epss_velocity": slope,
                "epss_trend": trend,
                "epss_velocity_computed_at": now,
            }
            for fp in fingerprints
        ]

    def _build_zero_velocity_updates(self, fingerprints: list[str]) -> list[dict]:
        now = _utcnow()
        return [
            {
                "_key": fp,
                "epss_velocity": 0.0,
                "epss_trend": "stable",
                "epss_velocity_computed_at": now,
            }
            for fp in fingerprints
        ]
