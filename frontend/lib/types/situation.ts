export type PersonaType = "CISO" | "Board" | "Engineering" | "RegAffairs";

// -------------------------------------------------------------------------
// v3 abstraction-layer types (no CVE IDs — persona-safe)
// -------------------------------------------------------------------------

export interface ThreatCategory {
  bucket_name: string;
  display_name: string;
  breach_probability: number;
  critical_asset_count: number;
  trend: string | null;
}

export interface ControlFailure {
  framework: string;
  failure_count: number;
  coverage_pct: number;
}

export interface ActionPriority {
  rank: number;
  description: string;
  owner: string;
  due_label: string;
  urgency: string;
}

export interface ThreatCategoryExplanation {
  bucket_name: string;
  driving_events: string[];
  turning_point_round: number | null;
  effective_defender_actions: string[];
  what_would_have_helped: string;
}

export interface ExposureDerivation {
  narrative: string;
  contributing_chains: number;
  highest_confidence_chain: string;
  investment_recommendation: string;
}

export interface CISOSituation {
  posture_score: number;
  posture_delta: number | null;
  attck_coverage_pct: number;
  attck_coverage_delta: number | null;
  remediation_sla_pct: number | null;
  control_failure_count: number;
  threat_categories: ThreatCategory[];
  control_failures: ControlFailure[];
  mttd_hours: number | null;
  mttd_target_hours: number;
  mttr_days: number | null;
  mttr_target_days: number;
  action_priorities: ActionPriority[];
  snapshot_timestamp: string;
  data_staleness_warning: string | null;
  threat_category_explanations?: ThreatCategoryExplanation[];
}

export interface BoardSituation {
  breach_probability_pct: number;
  breach_probability_delta: number | null;
  financial_exposure_usd_low: number | null;
  financial_exposure_usd_high: number | null;
  regulatory_fine_risk: { framework: string; estimated_fine_usd: number; probability: number }[];
  reputational_risk_score: number;
  board_priorities: ActionPriority[];
  snapshot_timestamp: string;
  exposure_derivation?: ExposureDerivation | null;
}

export interface MetricCard {
  id: string;
  label: string;
  value: string | number;
  delta?: string;
  severity?: "critical" | "high" | "medium" | "low" | "neutral";
  unit?: string;
}

export interface ChainNode {
  id: string;
  node_type: "CVE" | "CWE" | "Technique" | "IAMRole" | "Outcome" | "Detection";
  label: string;
  severity?: string;
}

export interface ChainEdge {
  id: string;
  source: string;
  target: string;
  probability?: number;
  soc_threshold_miss?: boolean;
}

export interface ChainData {
  nodes: ChainNode[];
  edges: ChainEdge[];
}

export interface AlertItem {
  id: string;
  title: string;
  severity: "critical" | "high" | "medium" | "low";
  card_type: "attack_chain" | "threat_detection" | "compliance" | "patch";
  summary: string;
  ask_prompt: string;
  chain?: ChainData;
  detail_rows?: { key: string; value: string }[];
}

// AQL tool return shapes — fixture keys must match these exactly
export interface AttackChainResult {
  cve_id: string;
  cvss3: number | null;
  epss: number | null;
  description: string;
  weaknesses: { cwe_id: string; name: string; abstraction: string }[];
  attack_techniques: { technique_id: string; name: string; tactic: string; description: string }[];
  live_detections: {
    detection_id: string;
    hostname: string;
    technique_id: string;
    tactic: string;
    severity: string;
    ioc_type: string;
    ioc_value: string;
    detected_at: string;
    source_tool: string;
    attack_technique_matched: boolean;
    technique_name: string | null;
    soc_threshold_miss?: boolean;
  }[];
  affected_devices: {
    hostname: string;
    internet_facing: boolean;
    containment_status: string;
    compliance_tags: string[];
  }[];
  attack_chain_complete: boolean;
  spine_to_reality_hops: number;
  // Fixture extension for Phase 1 graph visualization
  chain_nodes?: ChainNode[];
  chain_edges?: ChainEdge[];
}

export interface ThreatDetection {
  detection_id: string;
  hostname: string;
  cve_id: string;
  technique_id: string;
  technique_name: string;
  tactic: string;
  severity: string;
  ioc_type: string;
  ioc_value: string;
  quarantined: boolean;
  source_tool: string;
  detected_at: string;
  ttl_expires: string | null;
  cvss3: number | null;
  epss: number | null;
  in_kev: boolean;
}

export interface RegulatoryDeadline {
  incident_id: string;
  native_id: string;
  title: string;
  cve_id: string;
  source_tool: string;
  regulatory_labels: string[];
  sla_deadline: string;
  hours_remaining: number;
  overdue: boolean;
  urgency_tier: "OVERDUE" | "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  linked_jira_key: string | null;
  linked_pd_incident_id: string | null;
}

export interface PatchPriorityItem {
  rank: number;
  cve_id: string;
  composite_score: number;
  score_breakdown: {
    epss_pts: number;
    cvss_pts: number;
    kev_pts: number;
    exploit_pts: number;
    exposure_pts: number;
  };
  cvss3: number | null;
  epss: number | null;
  in_kev: boolean;
  active_exploits_in_env: number;
  affected_devices: {
    hostname: string;
    internet_facing: boolean;
    containment_status: string;
  }[];
  internet_facing_devices: number;
  open_incidents: number;
  regulatory_frameworks: string[];
  patch_urgency: "IMMEDIATE" | "HIGH" | "MEDIUM" | "LOW";
}

export interface SituationMetrics {
  ciso: MetricCard[];
  board: MetricCard[];
  engineering: MetricCard[];
  reg_affairs: MetricCard[];
}

// CSE simulation types

export interface CSEActionEvent {
  round_no: number;
  agent_type: string;
  action_type: string;
  outcome: string;
  significance?: number;
  timestamp?: string;
}

export interface CSERunStatus {
  sim_id: string;
  tenant_id: string;
  status: "idle" | "running" | "completed" | "failed" | "stopped";
  trigger_type: string | null;
  started_at: string | null;
  current_round: number | null;
  total_rounds: number | null;
  agent_count: number | null;
  chain_count: number | null;
  chain_probability: number | null;
  board_narrative: string | null;
  top_3_actions: string[];
  recent_events: CSEActionEvent[];
}

// Legacy simulation types (kept for existing simulation.py endpoint)

export interface SimulationAgentEvent {
  log_key: string;
  agent_id: string;
  round: number;
  event_type: string;
  significance: number;
  payload: Record<string, unknown>;
  timestamp: string;
}

export interface SimulationRunStatus {
  run_id: string;
  cve_id: string;
  status: "running" | "completed" | "failed" | "partial";
  started_at: string;
  completed_at: string | null;
  agent_count: number;
  round_count: number;
  chain_count: number | null;
  soc_blind_spot_count: number | null;
  top_playbook_action: string | null;
  recent_events: SimulationAgentEvent[];
}

export interface SituationRoomData {
  attack_chains: AttackChainResult[];
  threat_detections: ThreatDetection[];
  regulatory_deadlines: RegulatoryDeadline[];
  patch_priority: PatchPriorityItem[];
  situation_metadata: SituationMetrics;
  ciso_situation?: CISOSituation;
  board_situation?: BoardSituation;
}
