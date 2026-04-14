"use client";

import { useEffect, useRef, useState } from "react";
import { getSession } from "next-auth/react";
import type { CSERunStatus, CSEActionEvent } from "@/lib/types/situation";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const POLL_INTERVAL_MS = 3000;
const TERMINAL_STATUSES = new Set(["completed", "failed", "stopped"]);

interface SimulationLivePanelProps {
  simId: string;
  /** Called when a terminal status is received with the final run state */
  onComplete?: (run: CSERunStatus) => void;
}

const ACTION_TYPE_LABEL: Record<string, string> = {
  SCAN_SURFACE:          "Attack surface scanned",
  EXPLOIT_CVE:           "CVE exploited",
  LATERAL_MOVE:          "Lateral movement",
  ESCALATE_PRIVILEGES:   "Privilege escalation",
  PIVOT_TARGET:          "Target pivot",
  MONITOR:               "Monitoring",
  DETECT:                "Threat detected",
  INVESTIGATE:           "Investigation",
  ESCALATE_TO_CISO:      "CISO alerted",
  PATCH:                 "Patch deployed",
  DEPLOY_CONTROL:        "Control deployed",
  ROTATE_CREDENTIAL:     "Credential rotated",
  FILE_CRA_NOTIFICATION: "CRA notification filed",
  NOTIFY_BOARD:          "Board notified",
  ACKNOWLEDGE:           "Acknowledged",
};

const AGENT_TYPE_COLOR: Record<string, string> = {
  Attacker:   "bg-red-500",
  SOCAnalyst: "bg-blue-500",
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
  const [error, setError] = useState<string | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const completedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      if (completedRef.current || cancelled) return;

      try {
        const session = await getSession();
        if (!session?.accessToken) return;

        const res = await fetch(`${API_URL}/v1/cse/simulations/${simId}/status`, {
          headers: { Authorization: `Bearer ${session.accessToken}` },
        });

        if (!res.ok) {
          setError(`Failed to fetch status: ${res.status}`);
          return;
        }

        const data: CSERunStatus = await res.json();
        if (cancelled) return;

        setRun(data);
        setError(null);

        if (TERMINAL_STATUSES.has(data.status)) {
          completedRef.current = true;
          if (pollingRef.current) clearInterval(pollingRef.current);
          onComplete?.(data);
        }
      } catch (err) {
        if (!cancelled) setError(String(err));
      }
    }

    poll();
    pollingRef.current = setInterval(poll, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [simId, onComplete]);

  if (error) {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
        {error}
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
  const roundDisplay = run.total_rounds
    ? `${run.current_round ?? 0} / ${run.total_rounds}`
    : String(run.current_round ?? 0);

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

      {/* Live event feed */}
      <div className="px-4 pt-3 pb-1">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">
            Agent actions
          </span>
          <span className="text-[10px] text-muted-foreground">most recent first</span>
        </div>
        <div className="max-h-52 overflow-y-auto">
          {run.recent_events.length === 0 ? (
            <p className="text-xs text-muted-foreground py-2">No agent events yet.</p>
          ) : (
            run.recent_events.map((ev, i) => <EventRow key={`${ev.round_no}-${ev.agent_type}-${i}`} event={ev} />)
          )}
        </div>
      </div>
    </div>
  );
}
