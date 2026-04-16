"use client";

import { useEffect, useRef, useState } from "react";
import type { CSERunStatus, CSEActionEvent } from "@/lib/types/situation";
import { SimulationFishboneD3 } from "./SimulationFishboneD3";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const TERMINAL_STATUSES = new Set(["completed", "failed", "stopped"]);
const MAX_EVENTS = 50;

interface SimulationLivePanelProps {
  simId: string;
  /** Called when a terminal status is received with the final run state */
  onComplete?: (run: CSERunStatus) => void;
}

const ACTION_TYPE_LABEL: Record<string, string> = {
  SCAN_SURFACE:             "Attack surface scanned",
  EXPLOIT_CVE:              "CVE exploited",
  LATERAL_MOVE:             "Lateral movement",
  ESCALATE_PRIVILEGES:      "Privilege escalation",
  PIVOT_TARGET:             "Target pivot",
  MONITOR:                  "Monitoring",
  DETECT:                   "Threat detected",
  INVESTIGATE:              "Investigation",
  ESCALATE_TO_CISO:         "CISO alerted",
  PATCH:                    "Patch deployed",
  DEPLOY_CONTROL:           "Control deployed",
  ROTATE_CREDENTIAL:        "Credential rotated",
  FILE_CRA_NOTIFICATION:    "CRA notification filed",
  NOTIFY_BOARD:             "Board notified",
  ACKNOWLEDGE:              "Acknowledged",
  AUDIT_VULNERABILITY:      "Vulnerability audited",
  ISSUE_COMPLIANCE_FINDING: "Compliance gap recorded",
  FILE_INCIDENT_REPORT:     "Incident report filed",
  NOTIFY_REGULATOR:         "Regulator notified",
  APPROVE_EXCEPTION:        "Risk exception approved",
};

const AGENT_TYPE_COLOR: Record<string, string> = {
  Attacker:   "bg-red-500",
  SOCAnalyst: "bg-blue-500",
  Defender:   "bg-blue-500",
  DevSecOps:  "bg-green-500",
  CISO:       "bg-purple-500",
  Regulator:  "bg-orange-400",
};

function agentDot(agentType: string): string {
  return AGENT_TYPE_COLOR[agentType] ?? "bg-muted-foreground";
}

function EventRow({ event }: { event: CSEActionEvent }) {
  const label = ACTION_TYPE_LABEL[event.action_type] ?? event.action_type;
  const dot = agentDot(event.agent_type);

  return (
    <div className="flex items-start gap-2 py-1.5 border-b border-border/50 last:border-0">
      <div className={`mt-1.5 h-2 w-2 rounded-full shrink-0 ${dot}`} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-medium text-foreground truncate">{label}</span>
          <span className="text-[10px] text-muted-foreground shrink-0">Round {event.round_no}</span>
        </div>
        <div className="text-[11px] text-muted-foreground truncate">
          {event.agent_type} · {event.outcome}
        </div>
      </div>
    </div>
  );
}

export function SimulationLivePanel({ simId, onComplete }: SimulationLivePanelProps) {
  const [run, setRun] = useState<CSERunStatus | null>(null);
  const [events, setEvents] = useState<CSEActionEvent[]>([]);
  const [liveRound, setLiveRound] = useState<number>(0);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"graph" | "feed">("graph");
  const completedRef = useRef(false);
  const esRef = useRef<EventSource | null>(null);

  // Fetch run metadata (status, agent_count, total_rounds, etc.)
  async function fetchStatus(): Promise<CSERunStatus | null> {
    try {
      const res = await fetch(`${API_URL}/v1/cse/simulations/${simId}/status`);
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  }

  useEffect(() => {
    let cancelled = false;

    async function startStream() {
      // Fetch initial metadata (only available once sim is in DB — may be null for new runs)
      const initialRun = await fetchStatus();
      if (cancelled) return;

      if (initialRun) {
        setRun(initialRun);
        // Already finished before we connected — show final state and exit
        if (TERMINAL_STATUSES.has(initialRun.status)) {
          completedRef.current = true;
          onComplete?.(initialRun);
          return;
        }
      } else {
        // Sim not in DB yet (in-progress) — synthesize a running state so the panel renders
        setRun({
          sim_id: simId,
          tenant_id: "",
          status: "running",
          trigger_type: "monthly_posture_sim",
          started_at: new Date().toISOString(),
          current_round: null,
          total_rounds: null,
          agent_count: null,
          chain_count: null,
          chain_probability: null,
          board_narrative: null,
          top_3_actions: [],
          recent_events: [],
        });
      }

      // Stream endpoint is auth-free (sim_id UUID is the capability token)
      const streamUrl = `${API_URL}/v1/cse/simulations/${simId}/stream`;
      const es = new EventSource(streamUrl);
      esRef.current = es;

      es.onmessage = (e: MessageEvent) => {
        if (cancelled) return;
        try {
          const event = JSON.parse(e.data) as CSEActionEvent;
          setEvents((prev) => [event, ...prev].slice(0, MAX_EVENTS));
          if (event.round_no) setLiveRound((prev) => Math.max(prev, event.round_no));
        } catch {
          // malformed event — ignore
        }
      };

      es.addEventListener("done", async () => {
        if (cancelled) return;
        es.close();
        completedRef.current = true;
        // Poll for final status — writeback may take a few seconds after stream closes
        let finalRun: CSERunStatus | null = null;
        for (let i = 0; i < 6; i++) {
          await new Promise((r) => setTimeout(r, 2000));
          finalRun = await fetchStatus();
          if (finalRun) break;
        }
        if (cancelled) return;
        if (finalRun) {
          setRun(finalRun);
          onComplete?.(finalRun);
        } else {
          // Writeback still pending — mark completed with what we know from the stream
          setRun((prev) => prev ? { ...prev, status: "completed" } : null);
          onComplete?.({ sim_id: simId } as CSERunStatus);
        }
      });

      es.onerror = () => {
        if (cancelled) return;
        es.close();
        if (!completedRef.current) {
          setStreamError("Stream connection lost — simulation may still be running.");
        }
      };
    }

    startStream();

    return () => {
      cancelled = true;
      esRef.current?.close();
      esRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [simId]);

  if (streamError && !run) {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
        {streamError}
      </div>
    );
  }

  if (!run) {
    return (
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <div className="h-3 w-3 rounded-full bg-muted animate-pulse" />
          Connecting to simulation {simId}…
        </div>
      </div>
    );
  }

  const isRunning = !TERMINAL_STATUSES.has(run.status);
  const currentRound = liveRound || run.current_round || 0;
  const roundDisplay = run.total_rounds
    ? `${currentRound} / ${run.total_rounds}`
    : liveRound > 0 ? String(liveRound) : "—";

  // Merge SSE events with any recent_events from the status snapshot
  const displayEvents = events.length > 0 ? events : (run.recent_events ?? []);

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isRunning ? (
            <div className="h-2.5 w-2.5 rounded-full bg-green-500 animate-pulse" />
          ) : (
            <div className={`h-2.5 w-2.5 rounded-full ${run.status === "completed" ? "bg-green-500" : "bg-red-500"}`} />
          )}
          <span className="text-sm font-semibold text-foreground">
            {isRunning ? "Simulation running" : `Simulation ${run.status}`}
          </span>
          {run.trigger_type && (
            <span className="text-xs text-muted-foreground">· {run.trigger_type.replace(/_/g, " ")}</span>
          )}
        </div>
        <span className="text-xs text-muted-foreground font-mono">{run.sim_id.slice(0, 8)}…</span>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 divide-x divide-border border-b border-border">
        <div className="px-4 py-3 text-center">
          <div className="text-2xl font-bold text-foreground tabular-nums">{roundDisplay}</div>
          <div className="text-[11px] text-muted-foreground uppercase tracking-wide mt-0.5">Rounds</div>
        </div>
        <div className="px-4 py-3 text-center">
          <div className="text-2xl font-bold text-foreground tabular-nums">{run.agent_count ?? "—"}</div>
          <div className="text-[11px] text-muted-foreground uppercase tracking-wide mt-0.5">Agents</div>
        </div>
        <div className="px-4 py-3 text-center">
          <div className="text-2xl font-bold text-foreground tabular-nums">
            {run.chain_probability != null ? `${(run.chain_probability * 100).toFixed(0)}%` : "—"}
          </div>
          <div className="text-[11px] text-muted-foreground uppercase tracking-wide mt-0.5">Chain prob.</div>
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex border-b border-border">
        {(["graph", "feed"] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-xs font-semibold uppercase tracking-wide transition-colors ${
              activeTab === tab
                ? "text-foreground border-b-2 border-primary -mb-px"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {tab === "graph" ? "Fish Graph" : "Agent Feed"}
          </button>
        ))}
        {isRunning && (
          <span className="ml-auto px-4 py-2 text-[10px] text-green-500 font-medium">● live</span>
        )}
      </div>

      {/* Fish graph */}
      {activeTab === "graph" && (
        <div className="p-2">
          {streamError && <p className="text-[11px] text-amber-500 mb-1 px-2">{streamError}</p>}
          {displayEvents.length === 0 ? (
            <p className="text-xs text-muted-foreground py-4 text-center">Waiting for simulation events…</p>
          ) : (
            <SimulationFishboneD3
              events={[...displayEvents].reverse()}
              totalRounds={run.total_rounds ?? 720}
              isRunning={isRunning}
            />
          )}
        </div>
      )}

      {/* Agent feed */}
      {activeTab === "feed" && (
      <div className="px-4 pt-3 pb-1">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">
            Agent actions
          </span>
          <span className="text-[10px] text-muted-foreground">
            {isRunning ? "live" : "most recent first"}
          </span>
        </div>
        {streamError && (
          <p className="text-[11px] text-amber-500 mb-1">{streamError}</p>
        )}
        <div className="max-h-52 overflow-y-auto">
          {displayEvents.length === 0 ? (
            <p className="text-xs text-muted-foreground py-2">No agent events yet.</p>
          ) : (
            displayEvents.map((ev, i) => (
              <EventRow key={`${ev.round_no}-${ev.agent_type}-${i}`} event={ev} />
            ))
          )}
        </div>
      </div>
      )}
    </div>
  );
}
