"use client";

import { useRouter } from "next/navigation";
import type { CSERunStatus } from "@/lib/types/situation";

interface SimulationResultCardProps {
  run: CSERunStatus;
}

export function SimulationResultCard({ run }: SimulationResultCardProps) {
  const router = useRouter();

  const chainProb     = run.chain_probability != null ? (run.chain_probability * 100).toFixed(0) + "%" : "—";
  const narrative     = run.board_narrative ?? "No board narrative generated.";
  const topActions    = run.top_3_actions ?? [];
  const topAction     = topActions[0] ?? "No recommended actions generated.";

  const askPrompt = [
    `Summarise the CSE simulation results for run ${run.sim_id}.`,
    run.chain_probability != null ? `Attack chain probability: ${chainProb}.` : "",
    `Top recommended action: ${topAction}.`,
    "What should the security team prioritise first?",
  ]
    .filter(Boolean)
    .join(" ");

  function handleAsk() {
    router.push(`/dashboard/chat?prompt=${encodeURIComponent(askPrompt)}`);
  }

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className={`h-2.5 w-2.5 rounded-full ${run.status === "completed" ? "bg-green-500" : "bg-orange-400"}`} />
          <span className="text-sm font-semibold text-foreground">Simulation result</span>
          {run.trigger_type && (
            <span className="text-xs text-muted-foreground">· {run.trigger_type.replace(/_/g, " ")}</span>
          )}
        </div>
        <span className="text-xs text-muted-foreground font-mono">{run.sim_id.slice(0, 8)}…</span>
      </div>

      {/* Metric grid */}
      <div className="grid grid-cols-3 divide-x divide-border border-b border-border">
        {/* Chain probability */}
        <div className="px-4 py-4 text-center">
          <div className={`text-3xl font-bold tabular-nums ${
            run.chain_probability != null && run.chain_probability >= 0.5 ? "text-red-500" : "text-foreground"
          }`}>
            {chainProb}
          </div>
          <div className="text-[11px] text-muted-foreground uppercase tracking-wide mt-1">Chain prob.</div>
        </div>

        {/* Agent count */}
        <div className="px-4 py-4 text-center">
          <div className="text-3xl font-bold tabular-nums text-foreground">
            {run.agent_count ?? "—"}
          </div>
          <div className="text-[11px] text-muted-foreground uppercase tracking-wide mt-1">Agents</div>
        </div>

        {/* Rounds run */}
        <div className="px-4 py-4 text-center">
          <div className="text-3xl font-bold tabular-nums text-foreground">
            {run.total_rounds ?? run.current_round ?? "—"}
          </div>
          <div className="text-[11px] text-muted-foreground uppercase tracking-wide mt-1">Rounds run</div>
        </div>
      </div>

      {/* Board narrative */}
      <div className="px-4 py-3 border-b border-border">
        <div className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">
          Board narrative
        </div>
        <p className="text-sm text-foreground leading-relaxed">{narrative}</p>
      </div>

      {/* Top 3 actions */}
      {topActions.length > 0 && (
        <div className="px-4 py-3 border-b border-border">
          <div className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide mb-2">
            Recommended actions
          </div>
          <ol className="space-y-1">
            {topActions.map((action, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-foreground">
                <span className="text-[11px] font-semibold text-muted-foreground shrink-0 mt-0.5">
                  {i + 1}.
                </span>
                <span>{action}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* Ask Complira */}
      <div className="px-4 py-3 flex justify-end">
        <button
          onClick={handleAsk}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          Ask Complira
        </button>
      </div>
    </div>
  );
}
