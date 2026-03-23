"""
ingest_fair.py — FAIR Risk Quantification schema extensions
============================================================
Run AFTER ingest_demo.py and ingest_iam.py.

    PYTHONPATH=src python scripts/ingest_fair.py
    PYTHONPATH=src python scripts/ingest_fair.py --reset   # wipe and reseed

New document collections:
    financial_profiles     tenant financial profile (revenue, insurance, asset valuations)
    fair_scenarios         pre-built FAIR risk scenario templates (asset × threat × effect)
    fair_analyses          completed FAIR analysis runs with Monte Carlo results
    loss_benchmarks        calibrated industry loss data (NetDiligence, IBM, Advisen)
    threat_profiles        sector threat actor profiles with TEF calibration data
    control_assessments    FAIR-CAM control effectiveness scores per control × project
    penalty_structures     regulatory penalty structures with loss magnitude parameters
    asset_valuations       asset-level financial value (records, devices, hourly revenue)

New edge collections:
    has_financial_profile  tenant → financial_profile
    scoped_to_scenario     fair_analysis → fair_scenario
    uses_benchmark         fair_analysis → loss_benchmark
    assessed_against       finding → control_assessment    (FAIR-CAM bridge)
    quantified_by          finding → fair_analysis         (finding → its FAIR outputs)
    incurs_penalty         finding → penalty_structure     (financial loss overlay)
    values_asset           project → asset_valuation       (project → financial value)

Key design decisions:
  - TEF is expressed as annualised event frequency (not probability)
  - EPSS → TEF annualisation: tef = 1 - (1 - epss)^12
  - KEV status forces tef_floor = 12.0 (at least monthly attempt)
  - CVSS Access Vector N/A/L maps to contact_freq_tier HIGH/MED/LOW
  - Susceptibility = 1 - resistance_strength; both stored as [0,1]
  - Monte Carlo uses beta-PERT distribution: (min, most_likely, max, lambda=4)
  - All dollar values in USD, stored as float
"""

import os
import json
import math
import logging
import argparse
from pathlib import Path

from arango import ArangoClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

ARANGO_URL  = os.getenv("ARANGO_URL",  "http://localhost:8529")
ARANGO_DB   = os.getenv("ARANGO_DB",   "complira_graph")
ARANGO_USER = os.getenv("ARANGO_USER", "root")
ARANGO_PASS = os.getenv("ARANGO_PASS", "your_arango_password_here")
TENANT_ID   = "19349158"

# Actual MedCore project keys from complira_graph
PROJECT_PUMP_API   = "proj_08b7668d7af14fc2e9e847ff"
PROJECT_FIRMWARE   = "proj_b673c6b1ba51fc921bec8ad1"
PROJECT_INFRA      = "proj_8b66bc5412437dd21263695e"


# ---------------------------------------------------------------------------
# Industry benchmark seed data (sourced from research)
# NetDiligence 2025, IBM 2024, Coalition 2025, At-Bay 2025
# ---------------------------------------------------------------------------

LOSS_BENCHMARKS = [
    {
        "_key": "bench_hc_ransomware_sme",
        "source": "NetDiligence_2025",
        "sector": "healthcare",
        "scenario_type": "ransomware",
        "company_size": "SME",
        "currency": "USD",
        "incident_cost_min": 50_000,
        "incident_cost_most_likely": 173_000,
        "incident_cost_max": 800_000,
        "per_record_cost": None,
        "source_url": "https://netdiligence.com/cyber-insurance-claims-study/",
        "year": 2025,
    },
    {
        "_key": "bench_hc_breach_ibm2024",
        "source": "IBM_Cost_of_Data_Breach_2024",
        "sector": "healthcare",
        "scenario_type": "data_breach",
        "company_size": "all",
        "currency": "USD",
        "incident_cost_min": 3_200_000,
        "incident_cost_most_likely": 9_770_000,
        "incident_cost_max": 28_000_000,
        "per_record_cost": 150,
        "source_url": "https://newsroom.ibm.com/2024-07-30-ibm-report",
        "year": 2024,
    },
    {
        "_key": "bench_hc_ransomware_large",
        "source": "At_Bay_InsurSec_2025",
        "sector": "healthcare",
        "scenario_type": "ransomware",
        "company_size": "large",
        "currency": "USD",
        "incident_cost_min": 100_000,
        "incident_cost_most_likely": 468_000,
        "incident_cost_max": 4_000_000,
        "ransom_demand_avg": 957_000,
        "ransom_payment_avg": 317_000,
        "per_record_cost": None,
        "source_url": "https://www.at-bay.com/articles/2025-insursec-report/",
        "year": 2025,
    },
    {
        "_key": "bench_meddev_recall_major",
        "source": "McKinsey_MedDevice_Quality_2024",
        "sector": "medical_devices",
        "scenario_type": "product_recall",
        "company_size": "large",
        "currency": "USD",
        "incident_cost_min": 5_000_000,
        "incident_cost_most_likely": 100_000_000,
        "incident_cost_max": 600_000_000,
        "daily_cost": 5_000_000,
        "source_url": "https://www.mckinsey.com/industries/medical-products",
        "year": 2024,
    },
    {
        "_key": "bench_meddev_consent_decree",
        "source": "FDA_Consent_Decree_Precedent",
        "sector": "medical_devices",
        "scenario_type": "consent_decree",
        "company_size": "large",
        "currency": "USD",
        "incident_cost_min": 10_000_000,
        "incident_cost_most_likely": 50_000_000,
        "incident_cost_max": 175_000_000,
        "source_url": "https://www.medtechdive.com/news/bd-settle-sec-order-alaris-pumps",
        "year": 2024,
    },
    {
        "_key": "bench_hipaa_ocr_penalty",
        "source": "HHS_OCR_Enforcement_2024",
        "sector": "healthcare",
        "scenario_type": "regulatory_penalty_hipaa",
        "company_size": "all",
        "currency": "USD",
        "incident_cost_min": 10_000,
        "incident_cost_most_likely": 321_000,
        "incident_cost_max": 4_750_000,
        "annual_cap_tier4": 2_190_294,
        "per_record_cost_ocr": 15,
        "source_url": "https://www.legalhie.com/a-look-back-at-2024-hipaa-enforcement",
        "year": 2024,
    },
    {
        "_key": "bench_hipaa_class_action",
        "source": "Healthcare_Class_Action_2024_2025",
        "sector": "healthcare",
        "scenario_type": "class_action_breach",
        "company_size": "all",
        "currency": "USD",
        "incident_cost_min": 625_000,
        "incident_cost_most_likely": 5_000_000,
        "incident_cost_max": 11_000_000,
        "per_record_cost_min": 0.98,
        "per_record_cost_max": 35.67,
        "source_url": "https://www.hipaajournal.com/class-action-data-breach-settlements",
        "year": 2025,
    },
    {
        "_key": "bench_cra_art14_penalty",
        "source": "EU_CRA_Regulation_2024_2847",
        "sector": "all",
        "scenario_type": "regulatory_penalty_cra",
        "company_size": "all",
        "currency": "EUR",
        "tier1_fixed_max": 15_000_000,
        "tier1_revenue_pct_max": 0.025,
        "tier2_fixed_max": 10_000_000,
        "tier2_revenue_pct_max": 0.02,
        "tier3_fixed_max": 5_000_000,
        "tier3_revenue_pct_max": 0.01,
        "art14_24h_reporting_applies": True,
        "source_url": "https://digital-strategy.ec.europa.eu/en/policies/cyber-resilience-act",
        "year": 2024,
    },
]


# ---------------------------------------------------------------------------
# Threat profiles by sector (TEF calibration data)
# ---------------------------------------------------------------------------

THREAT_PROFILES = [
    {
        "_key": "threat_meddev_apt_healthcare",
        "sector": "medical_devices",
        "threat_community": "Nation-state APT (healthcare focus)",
        "examples": ["VOLT-TYPHOON", "APT41", "Lazarus Group"],
        "tef_min": 2.0,
        "tef_most_likely": 8.0,
        "tef_max": 52.0,
        "skill_level": "HIGH",
        "resources": "HIGH",
        "motivation": "HIGH",
        "kev_tef_multiplier": 4.0,
        "notes": "Healthcare sector is #3 targeted by nation-state actors per CISA 2024",
    },
    {
        "_key": "threat_meddev_ransomware",
        "sector": "medical_devices",
        "threat_community": "Ransomware operators",
        "examples": ["LockBit", "ALPHV/BlackCat", "RansomHub"],
        # TEF = per-company targeted campaigns per year, NOT internet-wide contact frequency.
        # At-Bay 2025: ~12% of policy holders had a ransomware claim over the study period.
        # NetDiligence SME: median 1 incident per company per study period.
        # For MedCore ($85M, healthcare-adjacent, open KEV on internet-facing service):
        #   min=1  (low-activity: 1 credible campaign attempt/yr)
        #   ml=4   (typical: quarterly targeting given KEV + sector)
        #   max=12 (high-pressure period: monthly targeting during active ransomware wave)
        # EPSS 97.5% measures internet-wide exploitation probability — NOT per-company targeting rate.
        "tef_min": 1.0,
        "tef_most_likely": 4.0,
        "tef_max": 12.0,
        "skill_level": "MED",
        "resources": "MED",
        "motivation": "HIGH",
        "kev_tef_multiplier": 3.0,
        "tef_calibration_note": "Per-company targeting rate. EPSS 97.5% is internet-wide contact signal; ransomware operators select specific victims by revenue/sector and commit to ~quarterly ops against a mid-market target with an open KEV.",
        "notes": "93% of healthcare orgs have confirmed KEVs. Ransomware hit 67% of healthcare in 2024 — prevalence over 12 months, not per-company frequency.",
    },
    {
        "_key": "threat_meddev_commodity",
        "sector": "medical_devices",
        "threat_community": "Commodity/opportunistic scanners",
        "examples": ["Shodan bots", "exploit kits", "automated KEV scanners"],
        # High contact frequency is correct for bots — they DO hit Log4Shell endpoints hundreds/yr.
        # But susceptibility against commodity bots must be modelled VERY LOW (0.001-0.01):
        # most send the JNDI payload but never follow through to full exploitation.
        # Model commodity separately from ransomware operators — DO NOT combine.
        "tef_min": 52.0,
        "tef_most_likely": 200.0,
        "tef_max": 3650.0,
        "susceptibility_against_this_community": 0.005,
        "skill_level": "LOW",
        "resources": "LOW",
        "motivation": "LOW",
        "kev_tef_multiplier": 10.0,
        "tef_calibration_note": "High TEF is correct (bots contact constantly). Susceptibility 0.005 reflects that most automated scans produce noise, not full loss events. Combining commodity + ransomware TEF inflates ALE 10-50×.",
        "notes": "EPSS 97.5% reflects commodity community contact frequency — not ransomware operator targeting rate. Do not use EPSS to derive TEF for targeted threat communities.",
    },
]


# ---------------------------------------------------------------------------
# Financial profile for MedCore (demo values)
# ---------------------------------------------------------------------------

FINANCIAL_PROFILE = {
    "_key": f"fp_{TENANT_ID}",
    "tenant_id": TENANT_ID,
    "company_name": "MedCore Systems (Demo)",
    "sector": "medical_devices",
    "subsector": "infusion_systems",
    "annual_revenue_usd": 85_000_000,
    "gross_margin_pct": 0.62,
    "revenue_per_hour_usd": 9_703,
    "revenue_per_day_usd": 232_877,
    "employee_count": 340,
    "avg_fully_loaded_hr_cost_usd": 85,
    "cyber_policy_limit_usd": 5_000_000,
    "cyber_policy_deductible_usd": 100_000,
    "cyber_policy_sublimit_ransomware_usd": 2_000_000,
    "cyber_policy_sublimit_breach_response_usd": 1_000_000,
    "product_liability_limit_usd": 10_000_000,
    "phi_records_count": 2_100_000,
    "devices_in_field_count": 4_200,
    "eu_market_revenue_pct": 0.35,
    "annual_revenue_eu_usd": 29_750_000,
    "hipaa_covered_entity": True,
    "fda_cleared_devices": ["510(k) K210987 - MedCore PumpPro 3.0"],
    "recall_logistics_cost_per_unit_usd": 500,
    "recall_lost_revenue_per_day_usd": 500_000,
    "breach_notification_cost_per_record_usd": 2.50,
    "credit_monitoring_cost_per_record_usd_yr1": 15.00,
    "outside_counsel_day_rate_usd": 3_500,
    "ir_retainer_daily_rate_usd": 25_000,
}


# ---------------------------------------------------------------------------
# Asset valuations (financial anchors per asset)
# ---------------------------------------------------------------------------

ASSET_VALUATIONS = [
    {
        "_key": "av_pump_api",
        "tenant_id": TENANT_ID,
        "project_id": PROJECT_PUMP_API,
        "asset_name": "MedCore Cloud API",
        "asset_type": "cloud_service",
        "criticality": "CRITICAL",
        "data_classification": "PHI_ADJACENT",
        "phi_records_at_risk": 0,
        "revenue_contribution_daily_usd": 150_000,
        "downtime_cost_per_hour_usd": 6_250,
        "replacement_cost_usd": 2_500_000,
        "recovery_time_objective_hours": 4,
        "notes": "Cloud API relays dosing commands and telemetry. Compromise → device safety risk.",
    },
    {
        "_key": "av_pump_firmware",
        "tenant_id": TENANT_ID,
        "project_id": PROJECT_FIRMWARE,
        "asset_name": "Pump Firmware",
        "asset_type": "embedded_firmware",
        "criticality": "CRITICAL",
        "data_classification": "DEVICE_CONTROL",
        "devices_in_field": 4_200,
        "recall_cost_total_usd": 2_100_000,
        "patient_safety_liability_per_incident_min_usd": 250_000,
        "patient_safety_liability_per_incident_max_usd": 10_000_000,
        "recovery_time_objective_hours": 72,
        "notes": "OTA firmware. CVE-2022-0778 blocks patch delivery pipeline.",
    },
    {
        "_key": "av_patient_data_s3",
        "tenant_id": TENANT_ID,
        "project_id": PROJECT_INFRA,
        "asset_name": "medcore-patient-data S3",
        "asset_type": "cloud_data_store",
        "criticality": "CRITICAL",
        "data_classification": "PHI",
        "phi_records_count": 2_100_000,
        "hipaa_notification_cost_usd": 5_250_000,
        "credit_monitoring_cost_yr1_usd": 31_500_000,
        "ocr_penalty_min_usd": 21_000,
        "ocr_penalty_most_likely_usd": 321_000,
        "ocr_penalty_max_usd": 4_750_000,
        "class_action_min_usd": 2_058_000,
        "class_action_most_likely_usd": 8_000_000,
        "class_action_max_usd": 74_865_000,
        "is_public": True,
        "notes": "Public ACL active (CKV_AWS_57). No access logging (CKV_AWS_18).",
    },
]


# ---------------------------------------------------------------------------
# Penalty structures — maps regulatory framework to FAIR secondary loss inputs
# ---------------------------------------------------------------------------

PENALTY_STRUCTURES = [
    {
        "_key": "pen_hipaa_willful_uncorrected",
        "framework": "HIPAA",
        "tier": "Tier4_willful_uncorrected",
        "obligation": "breach_notification",
        "currency": "USD",
        "penalty_per_violation_min": 73_011,
        "penalty_per_violation_max": 2_190_294,
        "annual_cap": 2_190_294,
        "triggering_event": "PHI breach affecting ≥500 records in a state or ≥500 records total",
        "probability_of_action_given_breach": 0.12,
        "secondary_class_action_probability": 0.45,
        "effective_date": "2024-08-08",
        "source": "HHS_CMP_Inflation_Adjustment_2024",
    },
    {
        "_key": "pen_eu_cra_art13_tier1",
        "framework": "EU_CRA",
        "tier": "Tier1_essential_requirements",
        "obligation": "cybersecurity_essential_requirements",
        "currency": "EUR",
        "fixed_max": 15_000_000,
        "revenue_pct_max": 0.025,
        "use_higher_of": True,
        "triggering_event": "Product with actively exploited vulnerability placed on EU market",
        "notification_deadline_hours_early_warning": 24,
        "notification_deadline_hours_detailed": 72,
        "notification_deadline_days_final": 14,
        "probability_of_action": 0.05,
        "market_access_denial_risk": True,
        "effective_date": "2026-09-11",
        "source": "EU_Regulation_2024_2847_Article_64",
    },
    {
        "_key": "pen_fda_524b_rta",
        "framework": "FDA_524B",
        "tier": "Refuse_to_Accept",
        "obligation": "premarket_cybersecurity_submission",
        "currency": "USD",
        "enforcement_type": "market_exclusion",
        "revenue_at_risk_per_day_usd": 500_000,
        "expected_delay_months_min": 3,
        "expected_delay_months_most_likely": 6,
        "expected_delay_months_max": 18,
        "probability_of_rta_given_open_kev": 0.35,
        "triggering_event": "Premarket submission for cyber device with open KEV-listed CVE",
        "note": "FDA does not impose monetary fines under 524B. Financial impact is product delay.",
        "source": "FDA_Final_Guidance_June_2025",
    },
    {
        "_key": "pen_fda_consent_decree",
        "framework": "FDA_524B",
        "tier": "Consent_Decree",
        "obligation": "postmarket_cybersecurity",
        "currency": "USD",
        "cost_min": 10_000_000,
        "cost_most_likely": 50_000_000,
        "cost_max": 175_000_000,
        "probability_of_action_given_serious_breach": 0.08,
        "triggering_event": "Repeated/serious cybersecurity failures in marketed device",
        "source": "BD_Alaris_SEC_Precedent_2024_and_Abbott_Historical",
    },
]


# ---------------------------------------------------------------------------
# FAIR scenario templates
# ---------------------------------------------------------------------------

FAIR_SCENARIOS = [
    {
        "_key": "scenario_log4shell_phi_exfil",
        "tenant_id": TENANT_ID,
        "name": "Log4Shell exploitation → PHI exfiltration",
        "cve_ids": ["CVE-2021-44228", "CVE-2021-45046"],
        "asset_key": "av_patient_data_s3",
        "threat_profile_key": "threat_meddev_ransomware",
        "attack_method": "JNDI_injection_RCE",
        "primary_effect": "data_exfiltration_phi",
        # TEF: ransomware operators targeting this specific $85M company (see threat profile).
        # NOT derived from EPSS (internet-wide prevalence). NOT commodity scanner contact rate.
        "tef_min": 1.0,
        "tef_most_likely": 4.0,
        "tef_max": 12.0,
        # Susceptibility 0.85: near-zero resistance but some attempts hit scan-only bots
        # or mis-configured payloads that never reach full RCE.
        "resistance_strength": 0.05,
        "susceptibility": 0.85,
        "control_gaps": ["no_patch", "no_jndi_disable", "no_waf_rule", "no_egress_policy"],
        # Loss magnitudes calibrated to MedCore's 2.1M PHI records + IBM/NetDiligence benchmarks.
        "primary_loss_min": 420_000,
        "primary_loss_most_likely": 5_250_000,
        "primary_loss_max": 31_500_000,
        "secondary_loss_min": 2_058_000,
        "secondary_loss_most_likely": 8_321_000,
        "secondary_loss_max": 79_615_000,
        "monte_carlo_iterations": 10_000,
        "pert_lambda": 4,
        "computed": False,
        "ale_usd": None,
        "var_95_usd": None,
        "var_99_usd": None,
        "max_blast_radius": "FULL_ACCOUNT_COMPROMISE",
        # Defensibility annotations
        "scenario_scope": "single_event",
        "tef_calibration_basis": "targeted_threat_community_per_company",
        "annual_revenue_context_usd": 85_000_000,
        "max_plausible_annual_loss_usd": 170_000_000,
        "created_at": "2026-03-20T00:00:00Z",
    },
    {
        "_key": "scenario_openssl_ota_block",
        "tenant_id": TENANT_ID,
        "name": "OpenSSL CVE-2022-0778 → OTA pipeline DoS → patch delivery blocked",
        "cve_ids": ["CVE-2022-0778"],
        "asset_key": "av_pump_firmware",
        "threat_profile_key": "threat_meddev_apt_healthcare",
        "attack_method": "infinite_loop_tls_cert",
        "primary_effect": "ota_denial_of_service",
        "tef_min": 4.0,
        "tef_most_likely": 12.0,
        "tef_max": 52.0,
        "resistance_strength": 0.20,
        "susceptibility": 0.80,
        "control_gaps": ["openssl_unpatched", "no_tls_cert_validation_bypass"],
        "primary_loss_min": 100_000,
        "primary_loss_most_likely": 500_000,
        "primary_loss_max": 2_100_000,
        "secondary_loss_min": 500_000,
        "secondary_loss_most_likely": 5_000_000,
        "secondary_loss_max": 30_000_000,
        "monte_carlo_iterations": 10_000,
        "pert_lambda": 4,
        "computed": False,
        "ale_usd": None,
        "var_95_usd": None,
        "var_99_usd": None,
        "max_blast_radius": "PHI_BREACH",
        "created_at": "2026-03-20T00:00:00Z",
    },
    {
        "_key": "scenario_iam_privesc_account_takeover",
        "tenant_id": TENANT_ID,
        "name": "Log4Shell → IRSA creds → 2-hop IAM escalation → full AWS admin",
        "cve_ids": ["CVE-2021-44228"],
        "iam_chain": ["medcore-pump-api-irsa", "medcore-lambda-exec", "medcore-admin"],
        "asset_key": "av_pump_api",
        "threat_profile_key": "threat_meddev_apt_healthcare",
        "attack_method": "passrole_lambda_updatefunctioncode_createpolicyversion",
        "primary_effect": "full_account_compromise",
        # TEF: APT targeting this specific company. APT campaigns are deliberate operations —
        # not automated sweeps. Healthcare APT (VOLT TYPHOON, APT41) may reconnoitre many targets
        # but commit to full exploitation chains against a specific mid-market company rarely.
        #   min=0.25 (once every 4 yrs: low-profile company)
        #   ml=1.5   (typical: 1-2 ops/yr given active healthcare APT activity + open KEV)
        #   max=4    (high-tension period: quarterly ops during geopolitical escalation)
        "tef_min": 0.25,
        "tef_most_likely": 1.5,
        "tef_max": 4.0,
        "resistance_strength": 0.02,
        "susceptibility": 0.98,
        "control_gaps": ["overpermissioned_irsa", "passrole_lambda_chain", "no_mfa_admin"],
        "primary_loss_min": 2_000_000,
        "primary_loss_most_likely": 15_000_000,
        "primary_loss_max": 50_000_000,
        "secondary_loss_min": 5_000_000,
        "secondary_loss_most_likely": 20_000_000,
        "secondary_loss_max": 95_000_000,
        "monte_carlo_iterations": 10_000,
        "pert_lambda": 4,
        "computed": False,
        "ale_usd": None,
        "var_95_usd": None,
        "var_99_usd": None,
        "max_blast_radius": "FULL_ACCOUNT_COMPROMISE",
        "created_at": "2026-03-20T00:00:00Z",
    },
]


# ---------------------------------------------------------------------------
# FAIR-CAM control assessments for pump-api project
# ---------------------------------------------------------------------------

CONTROL_ASSESSMENTS = [
    {
        "_key": "ca_pump_api_resistance",
        "tenant_id": TENANT_ID,
        "project_id": PROJECT_PUMP_API,
        "fair_cam_function": "Resistance",
        "fair_cam_description": "Degrades attacker ability to exploit vulnerabilities",
        "control_name": "Patch and Vulnerability Management",
        "framework_mapping": "NIST_CSF_ID.RA-1 / FAIR-CAM LC-R-01",
        "capability_score": 0.05,
        "coverage_score": 0.10,
        "reliability_score": 0.10,
        "composite_effectiveness": 0.05,
        "evidence": "log4j-core 2.14.1 unpatched (Dec 2021 - present), spring-webmvc 5.3.17 unpatched",
        "scanner_findings": ["CVE-2021-44228", "CVE-2021-45046", "CVE-2022-22965"],
        "resistance_strength_contribution": 0.05,
        "notes": "Near-zero resistance for Log4Shell class. No compensating controls confirmed.",
    },
    {
        "_key": "ca_pump_api_detection",
        "tenant_id": TENANT_ID,
        "project_id": PROJECT_PUMP_API,
        "fair_cam_function": "Detection",
        "fair_cam_description": "Identifies loss events in progress",
        "control_name": "Security Monitoring and SIEM",
        "framework_mapping": "NIST_CSF_DE.CM-1 / FAIR-CAM LC-D-01",
        "capability_score": 0.20,
        "coverage_score": 0.40,
        "reliability_score": 0.30,
        "composite_effectiveness": 0.20,
        "evidence": "CKV_AWS_18: S3 access logging disabled. No WAF logs confirmed.",
        "scanner_findings": ["CKV_AWS_18"],
        "notes": "Limited detection. S3 access not logged — exfiltration would be undetected.",
    },
    {
        "_key": "ca_pump_api_egress",
        "tenant_id": TENANT_ID,
        "project_id": PROJECT_PUMP_API,
        "fair_cam_function": "Avoidance",
        "fair_cam_description": "Reduces contact frequency by limiting attacker reach",
        "control_name": "Network Egress Controls",
        "framework_mapping": "NIST_800-53_SC-7 / FAIR-CAM LC-A-01",
        "capability_score": 0.10,
        "coverage_score": 0.50,
        "reliability_score": 0.20,
        "composite_effectiveness": 0.10,
        "evidence": "No JNDI/LDAP egress blocking. Outbound JNDI callbacks succeed. S3 accessed over public internet (no VPC endpoint).",
        "scanner_findings": ["CVE-2021-44228"],
        "notes": "Egress controls absent — the Log4Shell callback mechanism is completely unimpeded.",
    },
]


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_db():
    client = ArangoClient(hosts=ARANGO_URL)
    return client.db(ARANGO_DB, username=ARANGO_USER, password=ARANGO_PASS)


def ensure_collection(db, name: str, edge: bool = False):
    if not db.has_collection(name):
        db.create_collection(name, edge=edge)
        log.info(f"  Created {'edge ' if edge else ''}collection: {name}")
    return db.collection(name)


def upsert(col, doc: dict):
    col.insert(doc, overwrite=True, silent=True)


def upsert_edge(col, from_id: str, to_id: str, attrs: dict = None):
    doc = {"_from": from_id, "_to": to_id, **(attrs or {})}
    key = f"{from_id.replace('/','_').replace(':','_')}___{to_id.replace('/','_').replace(':','_')}"
    doc["_key"] = key[:240]
    col.insert(doc, overwrite=True, silent=True)


# ---------------------------------------------------------------------------
# Monte Carlo PERT simulation (pure Python, no scipy dependency)
# ---------------------------------------------------------------------------

def pert_sample(low: float, mode: float, high: float, lam: int = 4) -> float:
    """
    Beta-PERT sample using FAIR Institute parameterization.
    lam=4 is FAIR default weight on mode.
    """
    import random
    mean = (low + lam * mode + high) / (lam + 2)
    if abs(high - low) < 1e-10:
        return low
    alpha = (mean - low) / (high - low)
    alpha = max(1e-10, min(1 - 1e-10, alpha))
    beta_a = alpha * (lam + 2)
    beta_b = (lam + 2) * (1 - alpha)
    # Johnk's method — pure Python Beta sample
    while True:
        u = random.random() ** (1 / beta_a)
        v = random.random() ** (1 / beta_b)
        if u + v <= 1.0:
            return low + (u / (u + v)) * (high - low)


def run_monte_carlo(scenario: dict, n: int = 10_000) -> dict:
    """Run Monte Carlo simulation for a FAIR scenario."""
    import random
    lam = scenario.get("pert_lambda", 4)

    losses = []
    for _ in range(n):
        tef = pert_sample(scenario["tef_min"], scenario["tef_most_likely"], scenario["tef_max"], lam)
        lef = tef * scenario["susceptibility"]
        primary_loss   = pert_sample(scenario["primary_loss_min"], scenario["primary_loss_most_likely"], scenario["primary_loss_max"], lam)
        secondary_loss = pert_sample(scenario["secondary_loss_min"], scenario["secondary_loss_most_likely"], scenario["secondary_loss_max"], lam)
        losses.append(lef * (primary_loss + secondary_loss))

    losses.sort()
    n_float = float(n)
    ale   = sum(losses) / n_float
    var90 = losses[int(0.90 * n)]
    var95 = losses[int(0.95 * n)]
    var99 = losses[int(0.99 * n)]

    return {
        "ale_usd":         round(ale, 2),
        "var_90_usd":      round(var90, 2),
        "var_95_usd":      round(var95, 2),
        "var_99_usd":      round(var99, 2),
        "min_loss_usd":    round(min(losses), 2),
        "max_loss_usd":    round(max(losses), 2),
        "median_loss_usd": round(losses[n // 2], 2),
        "iterations": n,
    }


# ---------------------------------------------------------------------------
# Main ingest
# ---------------------------------------------------------------------------

def ingest(db, reset: bool = False):
    log.info("=== FAIR Schema Extensions Ingestion ===")

    # -- Collections --
    log.info("\n[1/6] Ensuring FAIR collections...")
    doc_cols = [
        "financial_profiles", "fair_scenarios", "fair_analyses",
        "loss_benchmarks", "threat_profiles", "control_assessments",
        "penalty_structures", "asset_valuations",
    ]
    edge_cols = [
        "has_financial_profile", "scoped_to_scenario", "uses_benchmark",
        "assessed_against", "quantified_by", "incurs_penalty", "values_asset",
    ]
    cols = {}
    for name in doc_cols:
        cols[name] = ensure_collection(db, name, edge=False)
    for name in edge_cols:
        cols[name] = ensure_collection(db, name, edge=True)

    if reset:
        log.info("  Resetting FAIR collections...")
        for name in doc_cols + edge_cols:
            col = db.collection(name)
            col.truncate()

    # -- Seed global reference data --
    log.info("\n[2/6] Seeding benchmark and threat data...")
    for b in LOSS_BENCHMARKS:
        upsert(cols["loss_benchmarks"], b)
    log.info(f"  {len(LOSS_BENCHMARKS)} loss benchmarks")

    for t in THREAT_PROFILES:
        upsert(cols["threat_profiles"], t)
    log.info(f"  {len(THREAT_PROFILES)} threat profiles")

    for p in PENALTY_STRUCTURES:
        upsert(cols["penalty_structures"], p)
    log.info(f"  {len(PENALTY_STRUCTURES)} penalty structures")

    # -- Tenant-specific data --
    log.info("\n[3/6] Inserting financial profile and asset valuations...")
    upsert(cols["financial_profiles"], FINANCIAL_PROFILE)
    upsert_edge(
        cols["has_financial_profile"],
        f"projects/{PROJECT_PUMP_API}",
        f"financial_profiles/{FINANCIAL_PROFILE['_key']}",
        {"tenant_id": TENANT_ID},
    )

    for av in ASSET_VALUATIONS:
        upsert(cols["asset_valuations"], av)
        if "project_id" in av:
            upsert_edge(
                cols["values_asset"],
                f"projects/{av['project_id']}",
                f"asset_valuations/{av['_key']}",
                {"tenant_id": TENANT_ID},
            )
    log.info(f"  {len(ASSET_VALUATIONS)} asset valuations")

    # -- FAIR-CAM control assessments --
    log.info("\n[4/6] Inserting control assessments (FAIR-CAM)...")
    for ca in CONTROL_ASSESSMENTS:
        upsert(cols["control_assessments"], ca)
        # Link each scanner finding to its control assessment
        for cve_id in ca.get("scanner_findings", []):
            cursor = db.aql.execute(
                "FOR f IN scan_findings FILTER f.tenant_id == @tid AND f.cve_id == @cve RETURN f._key",
                bind_vars={"tid": TENANT_ID, "cve": cve_id},
            )
            for fk in cursor:
                upsert_edge(
                    cols["assessed_against"],
                    f"scan_findings/{fk}",
                    f"control_assessments/{ca['_key']}",
                    {
                        "fair_cam_function": ca["fair_cam_function"],
                        "composite_effectiveness": ca["composite_effectiveness"],
                    },
                )
    log.info(f"  {len(CONTROL_ASSESSMENTS)} control assessments")

    # -- FAIR scenarios + Monte Carlo --
    log.info("\n[5/6] Running Monte Carlo simulations for FAIR scenarios...")
    for scenario in FAIR_SCENARIOS:
        mc_results = run_monte_carlo(scenario, n=10_000)
        scenario.update(mc_results)
        scenario["computed"] = True
        upsert(cols["fair_scenarios"], scenario)

        # Link findings → scenario via quantified_by edge
        for cve_id in scenario.get("cve_ids", []):
            cursor = db.aql.execute(
                "FOR f IN scan_findings FILTER f.tenant_id == @tid AND f.cve_id == @cve RETURN f._key",
                bind_vars={"tid": TENANT_ID, "cve": cve_id},
            )
            for fk in cursor:
                upsert_edge(
                    cols["quantified_by"],
                    f"scan_findings/{fk}",
                    f"fair_scenarios/{scenario['_key']}",
                    {"ale_usd": mc_results["ale_usd"]},
                )

        # Link scenario → penalty structures based on framework from finding_violates_control edges
        # Collect frameworks already wired via ViolationMappingPipeline
        for cve_id in scenario.get("cve_ids", []):
            try:
                fw_cursor = db.aql.execute(
                    """
                    FOR f IN scan_findings
                        FILTER f.tenant_id == @tid AND f.cve_id == @cve
                        FOR e IN finding_violates_control
                            FILTER e._from == CONCAT('scan_findings/', f._key)
                            RETURN DISTINCT e.framework
                    """,
                    bind_vars={"tid": TENANT_ID, "cve": cve_id},
                )
                for fw in fw_cursor:
                    if not fw:
                        continue
                    # Normalize framework name to match penalty structure keys
                    fw_map = {
                        "NIST-800-53": None,   # no NIST penalty structure
                        "HIPAA": "pen_hipaa_willful_uncorrected",
                    }
                    pen_key = fw_map.get(fw)
                    if pen_key:
                        upsert_edge(
                            cols["incurs_penalty"],
                            f"fair_scenarios/{scenario['_key']}",
                            f"penalty_structures/{pen_key}",
                            {"framework": fw},
                        )
            except Exception as e:
                log.warning(f"  Penalty link skip for {cve_id}: {e}")

        log.info(f"  {scenario['name'][:60]}")
        log.info(f"    ALE: ${mc_results['ale_usd']:,.0f}  |  VaR95: ${mc_results['var_95_usd']:,.0f}  |  VaR99: ${mc_results['var_99_usd']:,.0f}")

    # Also link KEV scenarios to EU CRA and FDA penalties
    for scenario in FAIR_SCENARIOS:
        if scenario.get("max_blast_radius") in ("FULL_ACCOUNT_COMPROMISE", "PHI_BREACH"):
            for pen_key in ("pen_eu_cra_art13_tier1", "pen_fda_524b_rta"):
                upsert_edge(
                    cols["incurs_penalty"],
                    f"fair_scenarios/{scenario['_key']}",
                    f"penalty_structures/{pen_key}",
                    {"framework": "regulatory"},
                )

    log.info("\n[6/6] Ingestion complete.")
    log.info(f"  Loss benchmarks:       {len(LOSS_BENCHMARKS)}")
    log.info(f"  Threat profiles:       {len(THREAT_PROFILES)}")
    log.info(f"  Penalty structures:    {len(PENALTY_STRUCTURES)}")
    log.info(f"  Asset valuations:      {len(ASSET_VALUATIONS)}")
    log.info(f"  Control assessments:   {len(CONTROL_ASSESSMENTS)}")
    log.info(f"  FAIR scenarios:        {len(FAIR_SCENARIOS)} (Monte Carlo complete)")
    log.info("")
    log.info("Add these tools to chat.py:")
    log.info("  get_fair_analysis(cve_id)            — ALE, VaR, scenario breakdown")
    log.info("  get_control_effectiveness(project_id) — FAIR-CAM scores per project")
    log.info("  get_penalty_exposure()               — regulatory secondary loss summary")
    log.info("  get_remediation_roi(cve_id)          — risk reduction value of patching")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Truncate FAIR collections before seeding")
    args = parser.parse_args()
    db = get_db()
    ingest(db, reset=args.reset)
