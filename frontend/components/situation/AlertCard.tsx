"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronDown, ChevronRight, MessageSquare, AlertTriangle, Info, Cpu, Shield } from "lucide-react";
import type { AlertItem } from "@/lib/types/situation";
import { FishboneChainGraph } from "./FishboneChainGraph";

const SEVERITY_BADGE: Record<string, string> = {
  critical: "bg-red-500/15 text-red-400 border border-red-500/30",
  high:     "bg-orange-500/15 text-orange-400 border border-orange-500/30",
  medium:   "bg-yellow-500/15 text-yellow-400 border border-yellow-500/30",
  low:      "bg-green-500/15 text-green-400 border border-green-500/30",
};

const CARD_TYPE_ICON: Record<string, React.ReactNode> = {
  attack_chain:      <AlertTriangle className="h-4 w-4 text-red-400" />,
  threat_detection:  <Cpu className="h-4 w-4 text-orange-400" />,
  compliance:        <Shield className="h-4 w-4 text-yellow-400" />,
  patch:             <Info className="h-4 w-4 text-blue-400" />,
};

const CARD_BORDER: Record<string, string> = {
  attack_chain:      "border-red-500/25 hover:border-red-500/50",
  threat_detection:  "border-orange-500/25 hover:border-orange-500/50",
  compliance:        "border-yellow-500/25 hover:border-yellow-500/50",
  patch:             "border-blue-500/25 hover:border-blue-500/50",
};

interface AlertCardProps {
  item: AlertItem;
}

export function AlertCard({ item }: AlertCardProps) {
  const [expanded, setExpanded] = useState(false);
  const router = useRouter();

  const handleAsk = (e: React.MouseEvent) => {
    e.stopPropagation();
    router.push(`/dashboard/chat?prompt=${encodeURIComponent(item.ask_prompt)}`);
  };

  const hasChain = item.card_type === "attack_chain" && item.chain && item.chain.nodes.length > 0;

  return (
    <div
      className={`rounded-lg border bg-card transition-all cursor-pointer ${CARD_BORDER[item.card_type] ?? "border-border hover:border-muted-foreground"}`}
      onClick={() => setExpanded(!expanded)}
    >
      {/* Header row */}
      <div className="flex items-center gap-3 p-4">
        <div className="flex-shrink-0">{CARD_TYPE_ICON[item.card_type]}</div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-foreground truncate">{item.title}</span>
            <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium uppercase tracking-wide ${SEVERITY_BADGE[item.severity] ?? SEVERITY_BADGE.medium}`}>
              {item.severity}
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{item.summary}</p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            onClick={handleAsk}
            className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-md bg-primary/10 text-primary border border-primary/20 hover:bg-primary/20 transition-colors font-medium"
          >
            <MessageSquare className="h-3 w-3" />
            Ask
          </button>
          <div className="text-muted-foreground">
            {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </div>
        </div>
      </div>

      {/* Expanded drill-down */}
      {expanded && (
        <div className="border-t border-border px-4 pb-4 pt-3" onClick={(e) => e.stopPropagation()}>
          {hasChain ? (
            <div>
              <div className="text-xs text-muted-foreground mb-2 font-medium uppercase tracking-wide">Attack Chain</div>
              <FishboneChainGraph
                chainNodes={item.chain!.nodes}
                chainEdges={item.chain!.edges}
              />
            </div>
          ) : (
            <div className="space-y-1.5">
              {(item.detail_rows ?? []).map((row) => (
                <div key={row.key} className="flex items-start gap-3 text-xs">
                  <span className="text-muted-foreground font-medium min-w-[120px] flex-shrink-0">{row.key}</span>
                  <span className="text-foreground break-all">{row.value}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
