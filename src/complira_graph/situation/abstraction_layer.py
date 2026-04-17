"""
complira_graph.situation.abstraction_layer
==========================================
SituationAbstractionLayer — translates simulation graph data into
business-level metrics for CISO and Board/CFO personas.

Pull model: this layer is invoked on request (not push-triggered).
No CVE IDs are present in any output from this layer.

Public API:
  SituationAbstractionLayer(db).compute_ciso(tenant_id) -> CISOSituation
  SituationAbstractionLayer(db).compute_board(tenant_id) -> BoardSituation
"""

from __future__ import annotations

import math
import structlog
from datetime import datetime, timezone
from typing import Any

from complira_graph.situation.models import (
    ActionPriority,
    BoardSituation,
    CISOSituation,
    ControlFailure,
    ExposureDerivation,
    ThreatCategory,
    ThreatCategoryExplanation,
)
from complira_graph.queries.situation_abstraction_queries import (
    get_attack_chain_findings_for_run,
    get_attck_coverage,
    get_business_impact_findings,
    get_chain_narratives_for_bucket,
    get_compliance_failures_by_framework,
    get_counterfactuals_for_tenant,
    get_latest_run_id,
    get_posture_snapshot_history,
    get_simulated_mttd,
    get_threat_category_rollup,
)

log = structlog.get_logger(__name__)

_POSTURE_SNAPSHOT_AQL = """
UPSERT { _key: @key }
INSERT @doc
UPDATE @doc
IN posture_snapshots
"""


class SituationAbstractionLayer:
    """
    Translates raw simulation graph data into persona-appropriate business views.

    Design rules (enforced here and in situation_abstraction_queries.py):
      - CISO view: posture score, threat categories (tactic buckets, no CVE IDs),
        compliance failures, MTTD, action priorities.
      - Board view: breach probability, financial exposure, regulatory fine risk
        (using f.framework structured field), reputational risk, governance priorities.
      - posture_snapshots are written ONLY by compute_ciso() (not compute_board()).
    """

    def __init__(self, db: Any) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # CISO view
    # ------------------------------------------------------------------

    def compute_ciso(self, tenant_id: str) -> CISOSituation:
        """
        Computes and returns the CISOSituation for the given tenant.
        Writes a posture_snapshot document after computation (time-series).
        """
        db = self._db

        # Stale rollup detection (UC-27)
        latest_run_id = get_latest_run_id(db, tenant_id)
        rollups = get_threat_category_rollup(db, tenant_id)
        data_staleness_warning = self._check_staleness(rollups, latest_run_id)

        # Core data queries
        chain_findings = get_attack_chain_findings_for_run(
            db, tenant_id, run_id=latest_run_id
        )
        attck_coverage_pct = get_attck_coverage(db, tenant_id)
        gaps = get_compliance_failures_by_framework(db, tenant_id)
        mttd_hours = get_simulated_mttd(db, tenant_id)
        snapshots = get_posture_snapshot_history(db, tenant_id, limit=4)

        # Posture score computation
        posture_score = _compute_posture_score(chain_findings, gaps, attck_coverage_pct)

        # Delta from snapshots (monthly delta: index 0 vs 1)
        posture_delta: int | None = None
        if len(snapshots) >= 2:
            posture_delta = snapshots[0]["posture_score"] - snapshots[1]["posture_score"]

        # Build structured outputs
        threat_categories = [
            ThreatCategory(
                bucket_name=r["bucket_name"],
                display_name=r.get("display_name", r["bucket_name"]),
                breach_probability=r.get("max_chain_probability", 0.0),
                critical_asset_count=r.get("critical_asset_count", 0),
            )
            for r in rollups
        ]

        control_failures = [
            ControlFailure(
                framework=g["framework"],
                failure_count=g["failure_count"],
                coverage_pct=g.get("coverage_pct", 0.0),
            )
            for g in gaps
        ]

        action_priorities = _derive_action_priorities(gaps, rollups)

        # C-19: threat category explanations from stored chain narratives
        threat_category_explanations = _build_threat_category_explanations(
            db, tenant_id, rollups
        )

        snapshot_ts = datetime.now(timezone.utc).isoformat()

        situation = CISOSituation(
            posture_score=posture_score,
            posture_delta=posture_delta,
            attck_coverage_pct=attck_coverage_pct,
            remediation_sla_pct=None,       # enrichment-ready
            control_failure_count=len(gaps),
            threat_categories=threat_categories,
            control_failures=control_failures,
            mttd_hours=mttd_hours,
            mttd_target_hours=24.0,
            mttr_days=None,                 # enrichment-ready
            mttr_target_days=7.0,
            action_priorities=action_priorities,
            snapshot_timestamp=snapshot_ts,
            data_staleness_warning=data_staleness_warning,
            threat_category_explanations=threat_category_explanations,
        )

        # Write posture snapshot (must be AFTER delta computation)
        self._write_posture_snapshot(tenant_id, situation, latest_run_id)

        log.info(
            "compute_ciso_complete",
            tenant_id=tenant_id,
            posture_score=posture_score,
            threat_categories=len(threat_categories),
            stale=data_staleness_warning is not None,
        )
        return situation

    # ------------------------------------------------------------------
    # Board view
    # ------------------------------------------------------------------

    def compute_board(self, tenant_id: str) -> BoardSituation:
        """
        Computes and returns the BoardSituation for the given tenant.
        Does NOT write posture_snapshots (compute_ciso owns that time series).
        """
        db = self._db

        findings = get_business_impact_findings(db, tenant_id)
        rollups = get_threat_category_rollup(db, tenant_id)
        gaps = get_compliance_failures_by_framework(db, tenant_id)

        # Breach probability from max chain probability across tactic buckets
        breach_probability_pct = 0.0
        if rollups:
            breach_probability_pct = max(
                r.get("max_chain_probability", 0.0) for r in rollups
            ) * 100.0

        # Financial exposure from CFO agent findings
        financial_findings = [
            f for f in findings if f.get("impact_type") == "financial_exposure"
        ]
        regulatory_findings = [
            f for f in findings if f.get("impact_type") == "regulatory_fine_risk"
        ]

        if not rollups:
            # New tenant — no simulation data yet
            financial_exposure_low = None
            financial_exposure_high = None
        elif financial_findings:
            financial_exposure_low = int(
                min(f.get("estimated_value", 0) for f in financial_findings)
            )
            financial_exposure_high = int(
                max(f.get("estimated_value", 0) for f in financial_findings)
            )
        else:
            # Rollup data exists but no CFO agent findings
            bp = breach_probability_pct / 100.0
            financial_exposure_low = round(bp * 500_000)
            financial_exposure_high = round(bp * 5_000_000)

        # Reputational risk score
        rep_findings = [
            f for f in findings if f.get("impact_type") == "reputational_risk"
        ]
        reputational_risk_score = min(
            1.0,
            sum(f.get("estimated_value", 0) for f in rep_findings) / 10_000_000,
        ) if rep_findings else 0.0

        regulatory_fine_risk = _group_fine_risk_by_framework(regulatory_findings)
        board_priorities = _derive_board_priorities(findings, gaps)

        # C-20: financial exposure derivation from stored counterfactuals
        run_data = get_counterfactuals_for_tenant(db, tenant_id)
        exposure_derivation = _build_exposure_derivation(
            run_data, breach_probability_pct,
            financial_exposure_low, financial_exposure_high,
        ) if run_data else None

        snapshot_ts = datetime.now(timezone.utc).isoformat()

        situation = BoardSituation(
            breach_probability_pct=breach_probability_pct,
            breach_probability_delta=None,   # enrichment-ready
            financial_exposure_usd_low=financial_exposure_low,
            financial_exposure_usd_high=financial_exposure_high,
            regulatory_fine_risk=regulatory_fine_risk,
            reputational_risk_score=reputational_risk_score,
            board_priorities=board_priorities,
            snapshot_timestamp=snapshot_ts,
            exposure_derivation=exposure_derivation,
        )

        log.info(
            "compute_board_complete",
            tenant_id=tenant_id,
            breach_probability_pct=breach_probability_pct,
            financial_findings=len(financial_findings),
        )
        return situation

    # ------------------------------------------------------------------
    # Engineering persona view
    # ------------------------------------------------------------------

    def compute_engineering(self, tenant_id: str) -> dict[str, Any]:
        """
        Returns patch priority list derived from latest simulation run.

        Queries attack_chain_findings joined with vulnerability CVSS/EPSS/KEV data.
        Returns {"patch_priority": [...], "data_staleness_warning": str|None}.
        """
        db = self._db
        latest_run_id = get_latest_run_id(db, tenant_id)
        if latest_run_id is None:
            return {"patch_priority": [], "data_staleness_warning": "no simulation run found"}

        _AQL = """
        FOR chain IN attack_chain_findings
          FILTER chain.tenant_id == @tenant_id
          FILTER chain.run_id == @run_id
          FOR vuln IN vulnerabilities
            FILTER vuln._key == SUBSTITUTE(SUBSTITUTE(chain.cve_id, 'CVE-', 'CVE_'), '-', '_', 1)
            LET epss = FIRST(
              FOR e IN has_epss
                FILTER e._from == CONCAT("vulnerabilities/", vuln._key)
                RETURN e.epss
            )
            LET in_kev = LENGTH(
              FOR e IN exploited_in_wild
                FILTER e._from == CONCAT("vulnerabilities/", vuln._key)
                RETURN 1
            ) > 0
            RETURN {
              cve_id:     chain.cve_id,
              cvss3:      vuln.cvss_v3_score,
              epss:       epss,
              in_kev:     in_kev,
              confidence: chain.confidence
            }
        """
        try:
            cursor = db.aql.execute(_AQL, bind_vars={"tenant_id": tenant_id, "run_id": latest_run_id})
            rows = list(cursor)
        except Exception as exc:
            log.error("compute_engineering_aql_error", tenant_id=tenant_id, error=str(exc))
            return {"patch_priority": [], "data_staleness_warning": "query error"}

        patch_priority = []
        for rank, row in enumerate(
            sorted(rows, key=lambda r: _composite_score(r), reverse=True), start=1
        ):
            score = _composite_score(row)
            patch_priority.append({
                "rank":                    rank,
                "cve_id":                  row.get("cve_id", ""),
                "composite_score":         round(score, 1),
                "patch_urgency":           _patch_urgency(score),
                "cvss3":                   row.get("cvss3"),
                "epss":                    row.get("epss"),
                "in_kev":                  row.get("in_kev", False),
                "active_exploits_in_env":  1 if row.get("confidence", 0) > 0.7 else 0,
                "internet_facing_devices": 0,
                "affected_devices":        [],
                "regulatory_frameworks":   [],
                "score_breakdown": {
                    "epss_pts":    round((row.get("epss") or 0) * 40, 1),
                    "kev_pts":     30 if row.get("in_kev") else 0,
                    "exploit_pts": round((row.get("confidence") or 0) * 12, 1),
                    "exposure_pts": 8,
                },
            })

        return {"patch_priority": patch_priority, "data_staleness_warning": None}

    # ------------------------------------------------------------------
    # RegAffairs persona view
    # ------------------------------------------------------------------

    def compute_reg_affairs(self, tenant_id: str) -> dict[str, Any]:
        """
        Returns regulatory deadline list derived from latest simulation compliance gap findings.

        Queries compliance_gap_findings written by the Regulator agent.
        Returns {"regulatory_deadlines": [...]}.
        """
        db = self._db
        latest_run_id = get_latest_run_id(db, tenant_id)
        if latest_run_id is None:
            return {"regulatory_deadlines": []}

        _AQL = """
        FOR gap IN compliance_gap_findings
          FILTER gap.tenant_id == @tenant_id
          FILTER gap.run_id == @run_id
          RETURN {
            gap_key:         gap._key,
            framework:       gap.framework,
            description:     gap.description,
            severity:        gap.severity,
            requirement_key: gap.requirement_key,
            created_at:      gap.created_at
          }
        """
        try:
            cursor = db.aql.execute(_AQL, bind_vars={"tenant_id": tenant_id, "run_id": latest_run_id})
            rows = list(cursor)
        except Exception as exc:
            log.error("compute_reg_affairs_aql_error", tenant_id=tenant_id, error=str(exc))
            return {"regulatory_deadlines": []}

        now = datetime.now(timezone.utc)
        deadlines = []
        for i, gap in enumerate(rows):
            framework = gap.get("framework", "CRA")
            sla_hours = _FRAMEWORK_SLA_HOURS.get(framework, 72)
            created_at_str = gap.get("created_at")
            hours_remaining = sla_hours
            try:
                if created_at_str:
                    from datetime import timezone as tz
                    import datetime as dt
                    created = dt.datetime.fromisoformat(created_at_str)
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=tz.utc)
                    elapsed = (now - created).total_seconds() / 3600
                    hours_remaining = round(sla_hours - elapsed, 1)
            except Exception:
                pass

            overdue = hours_remaining <= 0
            urgency = "OVERDUE" if overdue else ("HIGH" if hours_remaining <= 24 else ("MEDIUM" if hours_remaining <= 72 else "LOW"))
            deadlines.append({
                "incident_id":       f"gap_{gap.get('gap_key', i)}",
                "native_id":         latest_run_id,
                "title":             f"{framework} {gap.get('requirement_key', '')} — {gap.get('description', 'Compliance Gap')[:60]}",
                "regulatory_labels": [framework],
                "sla_deadline":      None,
                "hours_remaining":   hours_remaining,
                "overdue":           overdue,
                "urgency_tier":      urgency,
                "linked_jira_key":   None,
            })

        return {"regulatory_deadlines": deadlines}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _write_posture_snapshot(
        self,
        tenant_id: str,
        situation: CISOSituation,
        run_id: str | None,
    ) -> None:
        iso_now = datetime.now(timezone.utc).isoformat()
        # maxsplit=1: tenant_id may contain underscores
        snapshot_key = f"{tenant_id}_{iso_now}"
        doc = {
            "_key": snapshot_key,
            "tenant_id": tenant_id,
            "posture_score": situation.posture_score,
            "attck_coverage_pct": situation.attck_coverage_pct,
            "mttd_hours": situation.mttd_hours,
            "computed_at": iso_now,
            "run_id": run_id,
        }
        self._db.aql.execute(
            _POSTURE_SNAPSHOT_AQL,
            bind_vars={"key": snapshot_key, "doc": doc},
        )

    @staticmethod
    def _check_staleness(
        rollups: list[dict],
        latest_run_id: str | None,
    ) -> str | None:
        if not rollups or latest_run_id is None:
            return None
        rollup_run_id = rollups[0].get("run_id")
        if rollup_run_id and rollup_run_id != latest_run_id:
            age_label = rollups[0].get("computed_at", "an earlier simulation")
            return (
                f"Threat data is from a prior simulation "
                f"(last updated: {age_label}). "
                "Trigger a new monthly simulation for current data."
            )
        return None


# ---------------------------------------------------------------------------
# Standalone computation helpers (no DB access)
# ---------------------------------------------------------------------------

def _compute_posture_score(
    chain_findings: list[dict],
    gaps: list[dict],
    attck_coverage_pct: float,
) -> int:
    """
    Posture score formula:
      100
      − round(mean(chain_probability) × 40)   [chain risk penalty]
      − (gap_count × 3)                        [compliance gap penalty]
      − round(soc_miss_rate × 20)              [detection gap penalty]
      + round(attck_coverage_pct × 0.1)        [coverage bonus]
    Clamped to [0, 100].
    """
    n = len(chain_findings)
    if n > 0:
        mean_prob = sum(f.get("chain_probability", 0.0) for f in chain_findings) / n
        miss_count = sum(
            1 for f in chain_findings if f.get("soc_threshold_miss", False)
        )
        soc_miss_rate = miss_count / n
    else:
        mean_prob = 0.0
        soc_miss_rate = 0.0

    gap_count = len(gaps)
    score = (
        100
        - round(mean_prob * 40)
        - (gap_count * 3)
        - round(soc_miss_rate * 20)
        + round(attck_coverage_pct * 0.1)
    )
    return max(0, min(100, score))


def _derive_action_priorities(
    gaps: list[dict],
    rollups: list[dict],
) -> list[ActionPriority]:
    """
    Generates action priorities for the CISO view using business language.
    No CVE IDs in any output field.
    """
    priorities: list[ActionPriority] = []
    rank = 1

    # Top threat category → immediate remediation action
    for rollup in rollups[:2]:
        display = rollup.get("display_name", rollup.get("bucket_name", "Unknown threat"))
        prob = rollup.get("max_chain_probability", 0.0)
        urgency = "critical" if prob > 0.7 else "high" if prob > 0.4 else "medium"
        priorities.append(ActionPriority(
            rank=rank,
            description=(
                f"Remediate {display} attack vectors "
                f"({prob * 100:.0f}% breach probability)"
            ),
            owner="Security Engineering",
            due_label="14 days" if urgency == "critical" else "30 days",
            urgency=urgency,
        ))
        rank += 1

    # Top compliance gaps → governance action
    for gap in gaps[:2]:
        framework = gap.get("framework", "compliance")
        count = gap.get("failure_count", 0)
        priorities.append(ActionPriority(
            rank=rank,
            description=(
                f"Resolve {framework} compliance gaps "
                f"({count} control failure{'s' if count != 1 else ''})"
            ),
            owner="GRC Team",
            due_label="30 days",
            urgency="medium",
        ))
        rank += 1

    return priorities[:4]


def _derive_board_priorities(
    findings: list[dict],
    gaps: list[dict],
) -> list[ActionPriority]:
    """
    Generates governance-language action priorities for the Board view.
    Uses board_member_agent narratives when available; falls back to
    compliance gap governance templates.
    """
    priorities: list[ActionPriority] = []
    rank = 1

    board_findings = sorted(
        [f for f in findings if f.get("agent_type") == "board_member_agent"],
        key=lambda x: x.get("confidence", 0.0),
        reverse=True,
    )

    for f in board_findings[:2]:
        narrative = f.get("narrative", "")
        if not narrative:
            continue
        confidence = f.get("confidence", 0.5)
        priorities.append(ActionPriority(
            rank=rank,
            description=narrative,
            owner=_map_impact_type_to_owner(f.get("impact_type", "")),
            due_label="Immediate" if confidence > 0.8 else "Next quarter",
            urgency="critical" if confidence > 0.8 else "high" if confidence > 0.6 else "medium",
        ))
        rank += 1

    # Fall back to governance templates from compliance gaps
    if not priorities:
        for gap in gaps[:2]:
            framework = gap.get("framework", "compliance framework")
            priorities.append(ActionPriority(
                rank=rank,
                description=(
                    f"Strengthen {framework} compliance posture "
                    "to reduce regulatory exposure"
                ),
                owner="Board Governance Committee",
                due_label="Next board meeting",
                urgency="medium",
            ))
            rank += 1

    return priorities[:3]


def _group_fine_risk_by_framework(
    regulatory_findings: list[dict],
) -> list[dict]:
    """
    Groups regulatory_fine_risk findings by the structured framework field.
    Uses f.framework (NOT narrative string matching — UC-26, B-04 fix).

    Returns dicts with keys:
      framework, estimated_fine_usd, probability
    matching the BoardSituation frontend contract.
    """
    groups: dict[str, dict] = {}
    for f in regulatory_findings:
        framework = f.get("framework")
        if not framework:
            continue
        existing = groups.get(framework, {"estimated_fine_usd": 0, "probability": 0.0})
        existing["estimated_fine_usd"] = max(
            existing["estimated_fine_usd"], int(f.get("estimated_value", 0))
        )
        existing["probability"] = max(
            existing["probability"], float(f.get("confidence", 0.0))
        )
        groups[framework] = existing
    return [
        {
            "framework": fw,
            "estimated_fine_usd": data["estimated_fine_usd"],
            "probability": data["probability"],
        }
        for fw, data in sorted(
            groups.items(), key=lambda x: x[1]["estimated_fine_usd"], reverse=True
        )
    ]


def _map_impact_type_to_owner(impact_type: str) -> str:
    return {
        "financial_exposure":   "CFO",
        "regulatory_fine_risk": "General Counsel",
        "reputational_risk":    "CEO",
    }.get(impact_type, "Board Governance Committee")


# ---------------------------------------------------------------------------
# C-19: Threat category explanation builder
# ---------------------------------------------------------------------------

def _build_threat_category_explanations(
    db: Any,
    tenant_id: str,
    rollups: list[dict],
) -> list[ThreatCategoryExplanation]:
    """
    Builds per-bucket explanations from stored chain narrative data.
    Skips buckets with no explanation data — returns empty list when no
    simulation has run or report agent returned no narratives.
    No CVE IDs — explanation fields enforced by report_agent.
    """
    explanations: list[ThreatCategoryExplanation] = []
    for rollup in rollups:
        try:
            narratives = get_chain_narratives_for_bucket(
                db, tenant_id, rollup["bucket_name"]
            )
        except Exception as exc:
            log.warning(
                "threat_category_explanation_error",
                bucket=rollup["bucket_name"],
                error=str(exc),
            )
            continue
        if not narratives:
            continue
        explanations.append(
            ThreatCategoryExplanation(
                bucket_name=rollup["bucket_name"],
                driving_events=[
                    n["entry_point_reasoning"]
                    for n in narratives[:2]
                    if n.get("entry_point_reasoning")
                ],
                effective_defender_actions=[
                    n["defender_response"]
                    for n in narratives
                    if n.get("defender_response")
                ],
                what_would_have_helped=narratives[0].get("single_countermeasure", ""),
            )
        )
    return explanations


# ---------------------------------------------------------------------------
# C-20: Board exposure derivation builder
# ---------------------------------------------------------------------------

def _build_exposure_derivation(
    run_data: dict[str, Any],
    breach_probability_pct: float,
    financial_exposure_low: int | None,
    financial_exposure_high: int | None,
) -> ExposureDerivation:
    """
    Assembles a plain-English exposure derivation from counterfactual data.
    No CVE IDs — counterfactual descriptions generated by report_agent
    with CVE abstraction boundary enforced.
    F-002: guards trailing space when counterfactuals list is empty.
    """
    counterfactuals = run_data.get("counterfactuals") or []
    chain_count     = run_data.get("chain_count") or 0
    top_cf          = counterfactuals[0] if counterfactuals else {}

    impact = (top_cf.get("impact_if_applied") or "").strip()

    # Build exposure range — omit range when no financial data yet
    if financial_exposure_low is not None and financial_exposure_high is not None:
        low_m  = financial_exposure_low  / 1_000_000
        high_m = financial_exposure_high / 1_000_000
        range_str = f"${low_m:.1f}M\u2013${high_m:.1f}M "
    else:
        range_str = "financial exposure "

    narrative = (
        f"Estimated {range_str}derived from "
        f"{chain_count} confirmed attack chain"
        f"{'s' if chain_count != 1 else ''} "
        f"({breach_probability_pct:.0f}% breach probability)."
        + (f" {impact}" if impact else "")
    )

    return ExposureDerivation(
        narrative=narrative,
        contributing_chains=chain_count,
        highest_confidence_chain=top_cf.get("current_state", ""),
        investment_recommendation=top_cf.get("intervention_description", ""),
    )


# ---------------------------------------------------------------------------
# Engineering + RegAffairs helpers
# ---------------------------------------------------------------------------

_FRAMEWORK_SLA_HOURS: dict[str, float] = {
    "CRA":         72.0,
    "FDA_524B":    120.0,
    "HIPAA":       1440.0,
    "NIST_800_53": 168.0,
}


def _composite_score(row: dict[str, Any]) -> float:
    epss = row.get("epss") or 0.0
    kev = 30.0 if row.get("in_kev") else 0.0
    cvss3 = row.get("cvss3") or 0.0
    confidence = row.get("confidence") or 0.0
    return (epss * 40) + kev + (cvss3 * 3) + (confidence * 27)


def _patch_urgency(score: float) -> str:
    if score >= 80:
        return "IMMEDIATE"
    if score >= 60:
        return "HIGH"
    if score >= 40:
        return "MEDIUM"
    return "LOW"

