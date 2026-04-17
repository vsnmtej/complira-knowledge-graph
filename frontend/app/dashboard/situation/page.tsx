"use client";

import { useCallback, useEffect, useState } from "react";
import { getSession } from "next-auth/react";
import { useSituationStore } from "@/lib/stores/situation-store";
import { PersonaSwitcher } from "@/components/situation/PersonaSwitcher";
import { MetricStrip } from "@/components/situation/MetricStrip";
import { AlertFeed } from "@/components/situation/AlertFeed";
import { SimulationLivePanel } from "@/components/situation/SimulationLivePanel";
import type {
  AlertItem,
  ChainData,
  CSERunStatus,
  MetricCard,
  PatchPriorityItem,
  RegulatoryDeadline,
  SituationRoomData,
  CISOSituation,
  BoardSituation,
} from "@/lib/types/situation";
import fixture from "@/src/fixtures/aquadrive_tenant.json";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ---------------------------------------------------------------------------
// Map v3 CISOSituation → MetricCard[] + AlertItem[]
// ---------------------------------------------------------------------------

function cisoMetrics(s: CISOSituation): MetricCard[] {
  return [
    {
      id: "posture",
      label: "Posture Score",
      value: s.posture_score,
      delta: s.posture_delta != null ? `${s.posture_delta > 0 ? "+" : ""}${s.posture_delta}` : undefined,
      severity: s.posture_score >= 70 ? "low" : s.posture_score >= 50 ? "medium" : s.posture_score >= 30 ? "high" : "critical",
      unit: "/ 100",
    },
    {
      id: "attck",
      label: "ATT&CK Coverage",
      value: `${s.attck_coverage_pct.toFixed(0)}%`,
      delta: s.attck_coverage_delta != null ? `${s.attck_coverage_delta > 0 ? "+" : ""}${s.attck_coverage_delta.toFixed(0)}%` : undefined,
      severity: s.attck_coverage_pct >= 60 ? "low" : s.attck_coverage_pct >= 40 ? "medium" : "high",
    },
    {
      id: "mttd",
      label: "Simulated MTTD",
      value: s.mttd_hours != null ? `${s.mttd_hours.toFixed(0)}h` : "—",
      severity: s.mttd_hours != null && s.mttd_hours <= s.mttd_target_hours ? "low" : "high",
      unit: `target ${s.mttd_target_hours}h`,
    },
    {
      id: "ctrl",
      label: "Control Failures",
      value: s.control_failure_count,
      severity: s.control_failure_count === 0 ? "low" : s.control_failure_count <= 3 ? "medium" : "critical",
    },
  ];
}

function cisoAlerts(s: CISOSituation): AlertItem[] {
  const items: AlertItem[] = s.threat_categories.map((tc, i) => {
    // C-09: find matching explanation for this bucket
    const explanation = s.threat_category_explanations?.find(
      e => e.bucket_name === tc.bucket_name
    );
    return {
      id: `ciso-tc-${i}`,
      title: tc.display_name,
      severity:
        tc.breach_probability >= 0.7 ? "critical"
        : tc.breach_probability >= 0.5 ? "high"
        : tc.breach_probability >= 0.3 ? "medium"
        : "low",
      card_type: "attack_chain",
      summary: `Breach probability ${(tc.breach_probability * 100).toFixed(0)}% · ${tc.critical_asset_count} critical asset(s)${tc.trend ? ` · Trend: ${tc.trend}` : ""}`,
      ask_prompt: `What is driving the ${tc.display_name} risk category? Summarise top techniques, affected assets, and recommended controls.`,
      detail_rows: [
        { key: "Bucket", value: tc.bucket_name },
        { key: "Breach Probability", value: `${(tc.breach_probability * 100).toFixed(0)}%` },
        { key: "Critical Assets", value: String(tc.critical_asset_count) },
        ...(tc.trend ? [{ key: "Trend", value: tc.trend }] : []),
        ...(explanation?.what_would_have_helped
          ? [{ key: "What would help", value: explanation.what_would_have_helped }]
          : []),
      ],
    };
  });

  s.action_priorities.slice(0, 3).forEach((ap, i) => {
    items.push({
      id: `ciso-ap-${i}`,
      title: `Priority #${ap.rank}: ${ap.description}`,
      severity: ap.urgency === "critical" ? "critical" : ap.urgency === "high" ? "high" : "medium",
      card_type: "compliance",
      summary: `Owner: ${ap.owner} · Due: ${ap.due_label}`,
      ask_prompt: `Walk me through how to execute: "${ap.description}". What are the steps, owners, and expected risk reduction?`,
      detail_rows: [
        { key: "Owner", value: ap.owner },
        { key: "Due", value: ap.due_label },
        { key: "Urgency", value: ap.urgency },
      ],
    });
  });

  return items;
}

// ---------------------------------------------------------------------------
// Map v3 BoardSituation → MetricCard[] + AlertItem[]
// ---------------------------------------------------------------------------

function boardMetrics(s: BoardSituation): MetricCard[] {
  const exposure =
    s.financial_exposure_usd_low != null && s.financial_exposure_usd_high != null
      ? `$${(s.financial_exposure_usd_low / 1_000_000).toFixed(1)}M – $${(s.financial_exposure_usd_high / 1_000_000).toFixed(1)}M`
      : "—";
  return [
    {
      id: "breach-prob",
      label: "Breach Probability",
      value: `${s.breach_probability_pct.toFixed(0)}%`,
      delta:
        s.breach_probability_delta != null
          ? `${s.breach_probability_delta > 0 ? "+" : ""}${s.breach_probability_delta.toFixed(0)}%`
          : undefined,
      severity:
        s.breach_probability_pct >= 70 ? "critical"
        : s.breach_probability_pct >= 50 ? "high"
        : s.breach_probability_pct >= 30 ? "medium"
        : "low",
    },
    {
      id: "fin-exposure",
      label: "Financial Exposure",
      value: exposure,
      severity: s.financial_exposure_usd_high != null && s.financial_exposure_usd_high >= 10_000_000 ? "critical" : "high",
    },
    {
      id: "rep-risk",
      label: "Reputational Risk",
      value: `${(s.reputational_risk_score * 100).toFixed(0)}%`,
      severity: s.reputational_risk_score >= 0.7 ? "critical" : s.reputational_risk_score >= 0.4 ? "high" : "medium",
    },
    {
      id: "reg-fines",
      label: "Regulatory Fine Risks",
      value: s.regulatory_fine_risk.length,
      severity: s.regulatory_fine_risk.length === 0 ? "low" : s.regulatory_fine_risk.length <= 2 ? "medium" : "critical",
      unit: "frameworks",
    },
  ];
}

function boardAlerts(s: BoardSituation): AlertItem[] {
  const items: AlertItem[] = [];

  // C-10: prepend exposure derivation card when available
  if (s.exposure_derivation) {
    const ed = s.exposure_derivation;
    items.push({
      id: "board-exposure-derivation",
      title: "Financial Exposure — How We Got Here",
      severity: "high" as const,
      card_type: "compliance" as const,
      summary: ed.narrative,
      ask_prompt: "Explain the financial exposure derivation in detail. What chains contributed and what would reduce it most?",
      detail_rows: [
        { key: "Contributing Chains", value: String(ed.contributing_chains) },
        ...(ed.highest_confidence_chain ? [{ key: "Top Chain", value: ed.highest_confidence_chain }] : []),
        ...(ed.investment_recommendation ? [{ key: "Recommended Investment", value: ed.investment_recommendation }] : []),
      ],
    });
  }

  s.regulatory_fine_risk.forEach((r, i) => {
    items.push({
      id: `board-reg-${i}`,
      title: `${r.framework} — Regulatory Fine Risk`,
      severity: (r.probability >= 0.7 ? "critical"
        : r.probability >= 0.5 ? "high"
        : r.probability >= 0.3 ? "medium"
        : "low") as AlertItem["severity"],
      card_type: "compliance" as const,
      summary: `Estimated fine up to $${(r.estimated_fine_usd / 1_000_000).toFixed(1)}M · Probability ${(r.probability * 100).toFixed(0)}%`,
      ask_prompt: `What is our regulatory exposure under ${r.framework}? Show the required notifications, fines, and remediation timeline.`,
      detail_rows: [
        { key: "Framework", value: r.framework },
        { key: "Estimated Fine", value: `$${(r.estimated_fine_usd / 1_000_000).toFixed(1)}M` },
        { key: "Probability", value: `${(r.probability * 100).toFixed(0)}%` },
      ],
    });
  });

  s.board_priorities.slice(0, 3).forEach((ap, i) => {
    items.push({
      id: `board-ap-${i}`,
      title: `Board Priority #${ap.rank}: ${ap.description}`,
      severity: (ap.urgency === "critical" ? "critical" : ap.urgency === "high" ? "high" : "medium") as AlertItem["severity"],
      card_type: "compliance" as const,
      summary: `Owner: ${ap.owner} · Due: ${ap.due_label}`,
      ask_prompt: `Give me the board-level summary for: "${ap.description}". Include financial impact, regulatory context, and recommended resolution.`,
      detail_rows: [
        { key: "Owner", value: ap.owner },
        { key: "Due", value: ap.due_label },
        { key: "Urgency", value: ap.urgency },
      ],
    });
  });

  return items;
}

// ---------------------------------------------------------------------------
// Fixture-based builders for Engineering + RegAffairs (Phase 1 only)
// ---------------------------------------------------------------------------

function buildEngineeringAlerts(patches: PatchPriorityItem[]): AlertItem[] {
  return patches.map((pp) => ({
    id: `eng-patch-${pp.rank}`,
    title: `${pp.cve_id.replace(/_/g, "-")} — ${pp.patch_urgency} [Score ${pp.composite_score}]`,
    severity:
      pp.patch_urgency === "IMMEDIATE" ? "critical"
      : pp.patch_urgency === "HIGH" ? "high"
      : pp.patch_urgency === "MEDIUM" ? "medium"
      : "low",
    card_type: "patch",
    summary: `CVSS ${pp.cvss3 ?? "N/A"} · EPSS ${pp.epss != null ? (pp.epss * 100).toFixed(0) + "%" : "N/A"} · ${pp.active_exploits_in_env} active exploit(s) · ${pp.internet_facing_devices} internet-facing`,
    ask_prompt: `Give me a detailed patch plan for ${pp.cve_id.replace(/_/g, "-")} — affected devices, remediation steps, and regulatory impact`,
    detail_rows: [
      { key: "Rank", value: `#${pp.rank}` },
      { key: "Composite Score", value: String(pp.composite_score) },
      { key: "EPSS pts / KEV pts", value: `${pp.score_breakdown.epss_pts} / ${pp.score_breakdown.kev_pts}` },
      { key: "Exploit pts / Exposure pts", value: `${pp.score_breakdown.exploit_pts} / ${pp.score_breakdown.exposure_pts}` },
      { key: "Active Exploits in Env", value: String(pp.active_exploits_in_env) },
      { key: "Affected Devices", value: pp.affected_devices.map((d) => `${d.hostname}${d.internet_facing ? " [internet]" : ""}`).join(", ") },
      { key: "Frameworks", value: pp.regulatory_frameworks.join(", ") || "None" },
    ],
  }));
}

function buildRegAffairsAlerts(deadlines: RegulatoryDeadline[]): AlertItem[] {
  return deadlines.map((dl) => ({
    id: `reg-dl-${dl.incident_id}`,
    title: dl.title,
    severity:
      dl.overdue ? "critical"
      : dl.urgency_tier === "CRITICAL" || dl.urgency_tier === "HIGH" ? "high"
      : "medium",
    card_type: "compliance",
    summary: `${dl.overdue ? "OVERDUE" : `${Math.abs(dl.hours_remaining).toFixed(0)}h remaining`} · ${dl.regulatory_labels.join(", ")}`,
    ask_prompt: `What are the exact regulatory obligations for ${dl.title}? List required actions, notification deadlines, and documentation needed.`,
    detail_rows: [
      { key: "Incident", value: dl.native_id },
      { key: "Frameworks", value: dl.regulatory_labels.join(", ") },
      { key: "SLA Deadline", value: new Date(dl.sla_deadline).toLocaleString() },
      { key: "Hours Remaining", value: dl.overdue ? `OVERDUE (${Math.abs(dl.hours_remaining).toFixed(0)}h past)` : `${dl.hours_remaining.toFixed(0)}h` },
      { key: "Urgency", value: dl.urgency_tier },
      ...(dl.linked_jira_key ? [{ key: "Jira", value: dl.linked_jira_key }] : []),
    ],
  }));
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PERSONA_SECTION_LABEL: Record<string, string> = {
  CISO:        "Threat Categories & Priorities",
  Board:       "Financial & Regulatory Exposure",
  Engineering: "Patch Priority — Ranked by Composite Score",
  RegAffairs:  "Regulatory Deadlines",
};

const PERSONA_EMPTY_MSG: Record<string, string> = {
  CISO:        "No simulation data yet. Trigger a simulation run to populate the CISO view.",
  Board:       "No board-level findings yet. Trigger a simulation run to populate this view.",
  Engineering: "No patches required — environment is clean.",
  RegAffairs:  "No open regulatory deadlines.",
};

const fixtureData = fixture as unknown as SituationRoomData;

// Pre-built fixture chain alerts — shown when live API is unavailable
const FIXTURE_CHAIN_ALERTS: AlertItem[] = (fixtureData.attack_chains ?? [])
  .filter(ac => ac.chain_nodes && ac.chain_nodes.length > 0)
  .map((ac, i) => {
    const cveId = ac.cve_id.replace(/_/g, "-");
    const blindCount = (ac.chain_edges ?? []).filter(e => e.soc_threshold_miss).length;
    return {
      id: `fixture-chain-${i}`,
      title: `Attack Chain — ${cveId}`,
      severity: (ac.cvss3 ?? 0) >= 9 ? "critical" : (ac.cvss3 ?? 0) >= 7 ? "high" : "medium",
      card_type: "attack_chain" as const,
      summary: `CVSS ${ac.cvss3 ?? "N/A"} · EPSS ${ac.epss != null ? (ac.epss * 100).toFixed(0) + "%" : "N/A"}${blindCount ? ` · ${blindCount} SOC blind spot(s)` : ""}`,
      ask_prompt: `Walk me through the full attack chain for ${cveId}. What are the exploit steps, which assets are at risk, and what controls would break the chain?`,
      chain: { nodes: ac.chain_nodes!, edges: ac.chain_edges ?? [] } as ChainData,
      detail_rows: [
        { key: "CVSS", value: String(ac.cvss3 ?? "N/A") },
        { key: "EPSS", value: ac.epss != null ? `${(ac.epss * 100).toFixed(1)}%` : "N/A" },
        ...(blindCount ? [{ key: "SOC Blind Spots", value: String(blindCount) }] : []),
      ],
    };
  });

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function SituationRoomPage() {
  const { activePersona, setActivePersona } = useSituationStore();

  const [cisoData, setCisoData] = useState<CISOSituation | null>(null);
  const [boardData, setBoardData] = useState<BoardSituation | null>(null);
  const [engineeringData, setEngineeringData] = useState<{ patch_priority: PatchPriorityItem[] } | null>(null);
  const [regAffairsData, setRegAffairsData] = useState<{ regulatory_deadlines: RegulatoryDeadline[] } | null>(null);
  const [chainAlerts, setChainAlerts] = useState<AlertItem[]>([]);
  const [dataSource, setDataSource] = useState<"fixture" | "live">("fixture");
  const [stalenessWarning, setStalenessWarning] = useState<string | null>(null);
  const [activeSim, setActiveSim] = useState<string | null>(null);
  const [triggerLoading, setTriggerLoading] = useState(false);
  const [triggerError, setTriggerError] = useState<string | null>(null);

  const fetchLive = useCallback(async () => {
    const session = await getSession();
    const token = session?.accessToken;
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;

    try {
      const [cisoRes, boardRes, engRes, regRes, chainsRes] = await Promise.all([
        fetch(`${API_URL}/v1/situation/ciso`, { headers }),
        fetch(`${API_URL}/v1/situation/board`, { headers }),
        fetch(`${API_URL}/v1/situation/engineering`, { headers }),
        fetch(`${API_URL}/v1/situation/reg_affairs`, { headers }),
        fetch(`${API_URL}/v1/cse/simulations/chains`, { headers }),
      ]);

      if (cisoRes.ok) {
        const json: CISOSituation = await cisoRes.json();
        setCisoData(json);
        setStalenessWarning(json.data_staleness_warning ?? null);
        setDataSource("live");
      }
      if (boardRes.ok) {
        const json: BoardSituation = await boardRes.json();
        setBoardData(json);
      }
      if (engRes.ok) {
        const json = await engRes.json();
        setEngineeringData(json);
      }
      if (regRes.ok) {
        const json = await regRes.json();
        setRegAffairsData(json);
      }
      if (chainsRes.ok) {
        const json: { run_id: string | null; chains: { cve_id: string; confidence: number; chain_nodes?: unknown[]; chain_edges?: unknown[]; soc_blind_spots?: string[] }[] } = await chainsRes.json();
        const items: AlertItem[] = json.chains
          .filter((c) => c.chain_nodes && c.chain_nodes.length > 0)
          .map((c, i) => ({
            id: `chain-${i}`,
            title: `Attack Chain — ${c.cve_id}`,
            severity: c.confidence >= 0.8 ? "critical" : c.confidence >= 0.6 ? "high" : "medium",
            card_type: "attack_chain" as const,
            summary: `Chain probability ${(c.confidence * 100).toFixed(0)}%${c.soc_blind_spots?.length ? ` · ${c.soc_blind_spots.length} SOC blind spot(s)` : ""}`,
            ask_prompt: `Walk me through the full attack chain for ${c.cve_id}. What are the exploit steps, which assets are at risk, and what controls would break the chain?`,
            chain: {
              nodes: c.chain_nodes,
              edges: c.chain_edges ?? [],
            } as ChainData,
            detail_rows: [
              { key: "Chain Probability", value: `${(c.confidence * 100).toFixed(0)}%` },
              ...(c.soc_blind_spots?.length ? [{ key: "SOC Blind Spots", value: c.soc_blind_spots.join(", ") }] : []),
            ],
          }));
        setChainAlerts(items);
      }
    } catch {
      // Network error — stay on fixture
    }
  }, []);

  useEffect(() => {
    fetchLive();
  }, [fetchLive]);

  async function triggerSimulation() {
    setTriggerLoading(true);
    setTriggerError(null);
    try {
      const session = await getSession();
      const token = session?.accessToken;
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const res = await fetch(`${API_URL}/v1/cse/simulations/create`, {
        method: "POST",
        headers,
        body: JSON.stringify({ trigger_type: "monthly_posture_sim" }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setTriggerError(err.detail ?? "Failed to start simulation.");
        return;
      }
      const { sim_id } = await res.json();
      setActiveSim(sim_id);
    } catch {
      setTriggerError("Network error — could not reach the server.");
    } finally {
      setTriggerLoading(false);
    }
  }

  function handleSimComplete(_run: CSERunStatus) {
    setActiveSim(null);
    // Refresh all situation data after simulation completes
    fetchLive();
  }

  // Build persona-specific metrics + alerts
  let metrics: MetricCard[] = [];
  let alerts: AlertItem[] = [];

  const effectiveChains = chainAlerts.length > 0 ? chainAlerts : FIXTURE_CHAIN_ALERTS;

  if (activePersona === "CISO") {
    const ciso = cisoData ?? fixtureData.ciso_situation ?? null;
    if (ciso) {
      metrics = cisoMetrics(ciso);
      alerts  = [...cisoAlerts(ciso), ...effectiveChains];
    } else {
      metrics = fixtureData.situation_metadata.ciso;
      alerts  = effectiveChains;
    }
  } else if (activePersona === "Board") {
    const board = boardData ?? fixtureData.board_situation ?? null;
    if (board) {
      metrics = boardMetrics(board);
      alerts  = boardAlerts(board);
    } else {
      metrics = fixtureData.situation_metadata.board;
      alerts  = [];
    }
  } else if (activePersona === "Engineering") {
    metrics = fixtureData.situation_metadata.engineering;
    const patches = engineeringData?.patch_priority ?? fixtureData.patch_priority;
    alerts  = buildEngineeringAlerts(patches);
  } else {
    metrics = fixtureData.situation_metadata.reg_affairs;
    const deadlines = regAffairsData?.regulatory_deadlines ?? fixtureData.regulatory_deadlines;
    alerts  = buildRegAffairsAlerts(deadlines);
  }

  return (
    <div className="max-w-5xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-foreground">Situation Room</h1>
            <p className="text-sm text-muted-foreground mt-1">
              Live threat intelligence — Aquadrive Medical Devices
            </p>
          </div>
          <div className="flex items-center gap-2">
            {dataSource === "live" && (
              <span className="text-xs px-2 py-1 rounded bg-green-500/10 text-green-600 dark:text-green-400 font-medium">
                Live data
              </span>
            )}
            <button
              onClick={triggerSimulation}
              disabled={triggerLoading || activeSim !== null}
              className="text-xs px-3 py-1.5 rounded font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {triggerLoading ? "Starting…" : activeSim ? "Simulation running…" : "Run Simulation"}
            </button>
          </div>
        </div>
        {triggerError && (
          <div className="mt-2 text-xs px-3 py-1.5 rounded bg-destructive/10 text-destructive border border-destructive/20">
            {triggerError}
          </div>
        )}
        {stalenessWarning && !triggerError && (
          <div className="mt-2 text-xs px-3 py-1.5 rounded bg-yellow-500/10 text-yellow-700 dark:text-yellow-400 border border-yellow-500/20">
            {stalenessWarning}
          </div>
        )}
      </div>

      {/* Live simulation panel */}
      {activeSim && (
        <div className="mb-6">
          <SimulationLivePanel simId={activeSim} onComplete={handleSimComplete} />
        </div>
      )}

      {/* Persona switcher */}
      <PersonaSwitcher activePersona={activePersona} onSwitch={setActivePersona} />

      {/* Metric strip */}
      <MetricStrip metrics={metrics} />

      {/* Alert feed */}
      <div className="mb-2">
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">
          {PERSONA_SECTION_LABEL[activePersona]}
        </h2>
        <AlertFeed alerts={alerts} emptyMessage={PERSONA_EMPTY_MSG[activePersona]} />
      </div>
    </div>
  );
}
