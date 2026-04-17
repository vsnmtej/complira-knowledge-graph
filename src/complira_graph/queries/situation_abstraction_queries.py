"""
complira_graph.queries.situation_abstraction_queries
=====================================================
AQL read queries for the SituationAbstractionLayer.

CVE abstraction boundary (mandatory):
  Every AQL in this module returns business-level projections ONLY.
  chain_steps[], cve_id, cvss, epss, and package-level vulnerability fields
  are NEVER returned by any function in this module.  This module is the
  sole data-access layer for /v1/situation/ciso and /v1/situation/board.

  Contrast with simulation_queries.py (full data — writeback + chat tools).
  Both modules have a get_attack_chain_findings_for_run() function.
  This module's version returns a restricted projection; simulation_queries.py
  returns the full document including chain_nodes/chain_edges.

Eight public functions:
  get_threat_category_rollup()           — ATT&CK tactic buckets for tenant
  get_attack_chain_findings_for_run()    — restricted: {chain_probability, soc_threshold_miss}
  get_attck_coverage()                   — float: % known ATT&CK techniques observed
  get_compliance_failures_by_framework() — list of {framework, failure_count, coverage_pct}
  get_simulated_mttd()                   — float | None: mean time to detect (hours)
  get_posture_snapshot_history()         — list of prior posture snapshots (desc order)
  get_business_impact_findings()         — CFO/board agent outputs from business_impact_findings
  get_latest_run_id()                    — str | None: _key of most recent completed run
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# 1. Threat category rollups
# ---------------------------------------------------------------------------

_AQL_THREAT_CATEGORY_ROLLUP = """
FOR r IN threat_category_rollups
  FILTER r.tenant_id == @tenant_id
  SORT r.max_chain_probability DESC
  RETURN r
"""


def get_threat_category_rollup(
    db: Any,
    tenant_id: str,
) -> list[dict[str, Any]]:
    """
    Returns ATT&CK tactic-bucket rollup rows for the tenant, sorted by
    breach probability descending.  No CVE IDs are present in these documents.
    """
    cursor = db.aql.execute(
        _AQL_THREAT_CATEGORY_ROLLUP,
        bind_vars={"tenant_id": tenant_id},
    )
    return list(cursor)


# ---------------------------------------------------------------------------
# 2. Attack chain findings — RESTRICTED projection (CVE abstraction boundary)
# ---------------------------------------------------------------------------

_AQL_CHAIN_FINDINGS_SUMMARY = """
LET target_run = @run_id != null ? @run_id : (
  FOR r IN simulation_runs
    FILTER r.tenant_id == @tenant_id
    FILTER r.status == "completed"
    SORT r.completed_at DESC
    LIMIT 1
    RETURN r._key
)[0]
FOR f IN attack_chain_findings
  FILTER f.tenant_id == @tenant_id
  FILTER f.run_id == target_run
  RETURN {
    chain_probability:  NOT_NULL(f.chain_probability, f.confidence, 0.0),
    soc_threshold_miss: f.soc_threshold_miss != null
                          ? f.soc_threshold_miss
                          : (LENGTH(f.soc_blind_spots) > 0)
  }
"""


def get_attack_chain_findings_for_run(
    db: Any,
    tenant_id: str,
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Returns per-finding summary rows for the given run (or latest completed run
    when run_id is None).

    RESTRICTED PROJECTION — chain_steps[], cve_id and all CVE-related fields
    are intentionally excluded.  This function is for the SituationAbstractionLayer
    only.  Use simulation_queries.get_attack_chain_findings_for_run() for full data.

    Returns: [{chain_probability: float, soc_threshold_miss: bool}, ...]
    """
    cursor = db.aql.execute(
        _AQL_CHAIN_FINDINGS_SUMMARY,
        bind_vars={"tenant_id": tenant_id, "run_id": run_id},
    )
    return list(cursor)


# ---------------------------------------------------------------------------
# 3. ATT&CK technique coverage
# ---------------------------------------------------------------------------

# Approximate count of distinct ATT&CK Enterprise techniques (v15).
# Used as the denominator for coverage percentage.
_ATTCK_TECHNIQUE_UNIVERSE = 250

_AQL_ATTCK_COVERAGE = """
LET technique_sets = (
  FOR r IN threat_category_rollups
    FILTER r.tenant_id == @tenant_id
    RETURN r.technique_ids
)
LET flat = UNIQUE(FLATTEN(technique_sets))
LET raw = LENGTH(flat) > 0 ? (LENGTH(flat) / @universe * 100.0) : 0.0
RETURN raw > 100.0 ? 100.0 : raw
"""


def get_attck_coverage(
    db: Any,
    tenant_id: str,
) -> float:
    """
    Returns the percentage of known ATT&CK Enterprise techniques observed
    across all threat_category_rollups for the tenant.

    Range: 0.0 – 100.0.  Returns 0.0 when no rollups exist.
    """
    cursor = db.aql.execute(
        _AQL_ATTCK_COVERAGE,
        bind_vars={"tenant_id": tenant_id, "universe": _ATTCK_TECHNIQUE_UNIVERSE},
    )
    result = list(cursor)
    return float(result[0]) if result and result[0] is not None else 0.0


# ---------------------------------------------------------------------------
# 4. Compliance failures by framework
# ---------------------------------------------------------------------------

_AQL_COMPLIANCE_FAILURES = """
FOR gap IN compliance_gap_findings
  FILTER gap.tenant_id == @tenant_id
  COLLECT framework = gap.framework WITH COUNT INTO failure_count
  SORT failure_count DESC
  RETURN {
    framework:     framework,
    failure_count: failure_count,
    coverage_pct:  0.0
  }
"""


def get_compliance_failures_by_framework(
    db: Any,
    tenant_id: str,
) -> list[dict[str, Any]]:
    """
    Returns compliance failure counts grouped by regulatory framework.
    coverage_pct is enrichment-ready (0.0 until playbook-step coverage tracking).
    """
    cursor = db.aql.execute(
        _AQL_COMPLIANCE_FAILURES,
        bind_vars={"tenant_id": tenant_id},
    )
    return list(cursor)


# ---------------------------------------------------------------------------
# 5. Simulated mean time to detect
# ---------------------------------------------------------------------------

_AQL_SIMULATED_MTTD = """
LET total = COUNT(
  FOR f IN attack_chain_findings
    FILTER f.tenant_id == @tenant_id
    RETURN 1
)
LET misses = total > 0 ? COUNT(
  FOR f IN attack_chain_findings
    FILTER f.tenant_id == @tenant_id
    FILTER (f.soc_threshold_miss == true) OR (LENGTH(f.soc_blind_spots) > 0)
    RETURN 1
) : 0
RETURN total > 0 ? (4.0 + (misses / total) * 200.0) : null
"""


def get_simulated_mttd(
    db: Any,
    tenant_id: str,
) -> float | None:
    """
    Returns mean time to detect in hours derived from the SOC miss rate.

    Formula: 4.0h baseline + soc_miss_rate × 200h.
    Returns None when no attack chain findings exist for the tenant.
    """
    cursor = db.aql.execute(
        _AQL_SIMULATED_MTTD,
        bind_vars={"tenant_id": tenant_id},
    )
    result = list(cursor)
    val = result[0] if result else None
    return float(val) if val is not None else None


# ---------------------------------------------------------------------------
# 6. Posture snapshot history
# ---------------------------------------------------------------------------

_AQL_POSTURE_SNAPSHOT_HISTORY = """
FOR s IN posture_snapshots
  FILTER s.tenant_id == @tenant_id
  SORT s.computed_at DESC
  LIMIT @limit
  RETURN {
    posture_score:      s.posture_score,
    attck_coverage_pct: s.attck_coverage_pct,
    mttd_hours:         s.mttd_hours,
    computed_at:        s.computed_at,
    run_id:             s.run_id
  }
"""


def get_posture_snapshot_history(
    db: Any,
    tenant_id: str,
    limit: int = 4,
) -> list[dict[str, Any]]:
    """
    Returns the most recent posture snapshots for a tenant (most recent first).

    limit=4 supports monthly delta (index 0 vs 1) and quarterly trend (index 0 vs 3)
    from a single call.
    """
    cursor = db.aql.execute(
        _AQL_POSTURE_SNAPSHOT_HISTORY,
        bind_vars={"tenant_id": tenant_id, "limit": limit},
    )
    return list(cursor)


# ---------------------------------------------------------------------------
# 7. Business impact findings (CFO/board agent outputs)
# ---------------------------------------------------------------------------

_AQL_BUSINESS_IMPACT_FINDINGS = """
FOR f IN business_impact_findings
  FILTER f.tenant_id == @tenant_id
  SORT f.confidence DESC
  RETURN f
"""


def get_business_impact_findings(
    db: Any,
    tenant_id: str,
) -> list[dict[str, Any]]:
    """
    Returns all business impact findings for the tenant, sorted by confidence.
    Includes cfo_agent (financial_exposure) and board_member_agent (regulatory_fine_risk,
    reputational_risk) findings written by SimulationWritebackService step 8.
    """
    cursor = db.aql.execute(
        _AQL_BUSINESS_IMPACT_FINDINGS,
        bind_vars={"tenant_id": tenant_id},
    )
    return list(cursor)


# ---------------------------------------------------------------------------
# 8. Latest completed run ID
# ---------------------------------------------------------------------------

_AQL_LATEST_RUN_ID = """
FOR r IN simulation_runs
  FILTER r.tenant_id == @tenant_id
  FILTER r.status == "completed"
  SORT r.completed_at DESC
  LIMIT 1
  RETURN r._key
"""


def get_latest_run_id(
    db: Any,
    tenant_id: str,
) -> str | None:
    """
    Returns the _key of the most recently completed simulation run for a tenant,
    or None if no completed runs exist.
    """
    cursor = db.aql.execute(
        _AQL_LATEST_RUN_ID,
        bind_vars={"tenant_id": tenant_id},
    )
    result = list(cursor)
    return result[0] if result else None


# ---------------------------------------------------------------------------
# 9. Chain narratives for a tactic bucket (C-19 explainability)
# ---------------------------------------------------------------------------

_AQL_CHAIN_NARRATIVES_FOR_BUCKET = """
FOR r IN threat_category_rollups
  FILTER r.tenant_id == @tenant_id
  FILTER r.bucket_name == @bucket_name
  SORT r.computed_at DESC
  LIMIT 1
  FOR f IN attack_chain_findings
    FILTER f.run_id == r.run_id
    FILTER f.explanation != null
    SORT f.confidence DESC
    LIMIT 3
    RETURN {
      technique_id:          f.explanation.technique_id,
      entry_point_reasoning: f.explanation.entry_point_reasoning,
      success_reasoning:     f.explanation.success_reasoning,
      defender_response:     f.explanation.defender_response,
      soc_blind_spot:        f.explanation.soc_blind_spot_explanation,
      single_countermeasure: f.explanation.single_countermeasure,
      confidence:            f.confidence
    }
"""


def get_chain_narratives_for_bucket(
    db: Any,
    tenant_id: str,
    bucket_name: str,
) -> list[dict[str, Any]]:
    """
    Returns up to 3 chain narrative objects for the given ATT&CK tactic bucket.
    Uses the most recent rollup's run_id (SORT computed_at DESC — F-001 fix).
    Returns [] when no explanation data exists.

    No CVE IDs — explanation fields are generated by report_agent._gen_chain_narratives()
    which enforces the CVE abstraction boundary.
    """
    cursor = db.aql.execute(
        _AQL_CHAIN_NARRATIVES_FOR_BUCKET,
        bind_vars={"tenant_id": tenant_id, "bucket_name": bucket_name},
    )
    return list(cursor)


# ---------------------------------------------------------------------------
# 10. Counterfactuals from latest completed run (C-20 explainability)
# ---------------------------------------------------------------------------

_AQL_COUNTERFACTUALS_FOR_RUN = """
FOR r IN simulation_runs
  FILTER r.tenant_id == @tenant_id
  FILTER r.status == "completed"
  SORT r.completed_at DESC
  LIMIT 1
  RETURN {
    run_id:          r._key,
    counterfactuals: r.counterfactuals,
    chain_count:     r.chain_count,
    audit_trail:     r.audit_trail
  }
"""


def get_counterfactuals_for_tenant(
    db: Any,
    tenant_id: str,
) -> dict[str, Any] | None:
    """
    Returns counterfactuals + chain_count from the most recently completed
    simulation run for the tenant, or None if no completed run exists.

    counterfactuals is a list of objects written by report_agent._gen_counterfactuals().
    No CVE IDs are present in counterfactual descriptions.
    """
    cursor = db.aql.execute(
        _AQL_COUNTERFACTUALS_FOR_RUN,
        bind_vars={"tenant_id": tenant_id},
    )
    result = list(cursor)
    return result[0] if result else None
