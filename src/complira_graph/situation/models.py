"""
complira_graph.situation.models
================================
Pydantic models for the SituationAbstractionLayer API responses.

Design boundary (mandatory): neither CISOSituation nor BoardSituation
contains CVE IDs, CVSS scores, EPSS scores, or any package-level
vulnerability detail.  All data is aggregated to business metrics
before entering these models.
"""

from __future__ import annotations

from pydantic import BaseModel


class ThreatCategoryExplanation(BaseModel):
    """Per-bucket explanation of what drove breach probability. No CVE IDs."""
    bucket_name: str
    driving_events: list[str]               # key events that drove probability
    turning_point_round: int | None = None  # enrichment-ready
    effective_defender_actions: list[str] = []
    what_would_have_helped: str = ""        # single_countermeasure from chain narrative


class ExposureDerivation(BaseModel):
    """Plain-English explanation of financial exposure calculation. No CVE IDs."""
    narrative: str
    contributing_chains: int = 0
    highest_confidence_chain: str = ""      # description only, no CVE IDs
    investment_recommendation: str = ""     # from counterfactuals[0]


class ThreatCategory(BaseModel):
    bucket_name: str           # "remote_code_execution"
    display_name: str          # "Remote code execution"
    breach_probability: float  # max chain probability in this tactic bucket
    critical_asset_count: int
    trend: str | None = None   # "up" | "down" | None (enrichment-ready)


class ControlFailure(BaseModel):
    framework: str
    failure_count: int
    coverage_pct: float        # enrichment-ready: 0.0 until playbook coverage tracking


class ActionPriority(BaseModel):
    rank: int
    description: str           # governance / business language only — no CVE IDs
    owner: str
    due_label: str
    urgency: str               # "critical" | "high" | "medium"


class CISOSituation(BaseModel):
    posture_score: int                         # 0–100
    posture_delta: int | None = None
    attck_coverage_pct: float
    attck_coverage_delta: float | None = None  # enrichment-ready
    remediation_sla_pct: float | None = None   # enrichment-ready
    control_failure_count: int
    threat_categories: list[ThreatCategory]
    control_failures: list[ControlFailure]
    mttd_hours: float | None = None
    mttd_target_hours: float
    mttr_days: float | None = None             # enrichment-ready
    mttr_target_days: float
    action_priorities: list[ActionPriority]
    snapshot_timestamp: str
    data_staleness_warning: str | None = None
    threat_category_explanations: list[ThreatCategoryExplanation] = []  # C-02


class BoardSituation(BaseModel):
    breach_probability_pct: float
    breach_probability_delta: float | None = None  # enrichment-ready
    financial_exposure_usd_low: int | None = None
    financial_exposure_usd_high: int | None = None
    regulatory_fine_risk: list[dict]
    reputational_risk_score: float
    board_priorities: list[ActionPriority]
    snapshot_timestamp: str
    exposure_derivation: ExposureDerivation | None = None  # C-03
