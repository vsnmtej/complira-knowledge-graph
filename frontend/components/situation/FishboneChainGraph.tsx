"use client";

import type { ChainNode, ChainEdge } from "@/lib/types/situation";

// ---------------------------------------------------------------------------
// Layout constants
// ---------------------------------------------------------------------------
const SPINE_Y      = 120;   // vertical center of spine
const BRANCH_DY    = 82;    // how far branch nodes sit above/below spine
const BRANCH_DX    = 52;    // how far branch nodes are pushed right of attachment
const NODE_R       = 30;    // node circle radius
const NODE_SPACING = 145;   // horizontal spacing between spine attachment points
const SPINE_PAD    = 85;    // left/right padding before first/after last spine point
const CANVAS_H     = 290;   // total SVG height

// ---------------------------------------------------------------------------
// Node colours by type
// ---------------------------------------------------------------------------
const STYLE: Record<string, { fill: string; stroke: string; text: string; tag: string }> = {
  CVE:       { fill: "#1a0505", stroke: "#ef4444", text: "#fca5a5", tag: "CVE"       },
  CWE:       { fill: "#1a0d04", stroke: "#f97316", text: "#fdba74", tag: "CWE"       },
  Technique: { fill: "#0d0519", stroke: "#8b5cf6", text: "#c4b5fd", tag: "TECHNIQUE" },
  IAMRole:   { fill: "#050d1a", stroke: "#3b82f6", text: "#93c5fd", tag: "IAM"       },
  Detection: { fill: "#051a0c", stroke: "#22c55e", text: "#86efac", tag: "DETECTION" },
  Outcome:   { fill: "#1a1002", stroke: "#f59e0b", text: "#fde68a", tag: "OUTCOME"   },
};

// ---------------------------------------------------------------------------
// Topological sort (Kahn's algorithm)
// ---------------------------------------------------------------------------
function topSort(nodes: ChainNode[], edges: ChainEdge[]): ChainNode[] {
  const inDeg = new Map(nodes.map(n => [n.id, 0]));
  const adj   = new Map(nodes.map(n => [n.id, [] as string[]]));
  for (const e of edges) {
    adj.get(e.source)?.push(e.target);
    inDeg.set(e.target, (inDeg.get(e.target) ?? 0) + 1);
  }
  const queue  = nodes.filter(n => !inDeg.get(n.id));
  const out: ChainNode[] = [];
  const map    = new Map(nodes.map(n => [n.id, n]));
  while (queue.length) {
    const n = queue.shift()!;
    out.push(n);
    for (const nid of (adj.get(n.id) ?? [])) {
      const d = (inDeg.get(nid) ?? 1) - 1;
      inDeg.set(nid, d);
      if (d === 0) { const nn = map.get(nid); if (nn) queue.push(nn); }
    }
  }
  return out.length === nodes.length ? out : nodes;
}

// ---------------------------------------------------------------------------
// Layout: first & last node on spine; intermediate nodes alternate above/below
// ---------------------------------------------------------------------------
interface LayoutNode {
  node:    ChainNode;
  x:       number;   // actual node centre x
  y:       number;   // actual node centre y
  attachX: number;   // x where bone meets the spine
  onSpine: boolean;
  above:   boolean;
}

function buildLayout(sorted: ChainNode[]): LayoutNode[] {
  const n = sorted.length;
  return sorted.map((node, i) => {
    const attachX = SPINE_PAD + i * NODE_SPACING;
    const onSpine = i === 0 || i === n - 1;
    const above   = i % 2 === 1;
    if (onSpine) {
      return { node, x: attachX, y: SPINE_Y, attachX, onSpine: true, above: false };
    }
    return {
      node,
      x: attachX + BRANCH_DX,
      y: above ? SPINE_Y - BRANCH_DY : SPINE_Y + BRANCH_DY,
      attachX,
      onSpine: false,
      above,
    };
  });
}

function clamp(s: string, max: number) {
  return s.length > max ? s.slice(0, max - 1) + "…" : s;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
interface Props {
  chainNodes: ChainNode[];
  chainEdges: ChainEdge[];
  height?: number;
}

export function FishboneChainGraph({ chainNodes, chainEdges, height = CANVAS_H }: Props) {
  if (!chainNodes?.length) return null;

  const sorted  = topSort(chainNodes, chainEdges);
  const layouts = buildLayout(sorted);
  const n       = sorted.length;

  const svgW  = SPINE_PAD + (n - 1) * NODE_SPACING + BRANCH_DX + NODE_R + 30;
  const spineX1 = SPINE_PAD - 36;
  const spineX2 = SPINE_PAD + (n - 1) * NODE_SPACING + BRANCH_DX + 12;

  // Edge lookup: source-target → edge
  const edgeMap = new Map(chainEdges.map(e => [`${e.source}-${e.target}`, e]));
  // Incoming edge for a node
  const inEdge  = (id: string) => chainEdges.find(e => e.target === id);

  return (
    <div className="w-full overflow-x-auto rounded-md bg-[#080808] border border-border">
      <svg
        width={svgW}
        height={height}
        viewBox={`0 0 ${svgW} ${height}`}
        style={{ minWidth: "100%", display: "block" }}
      >
        <defs>
          {/* Arrow markers */}
          <marker id="arr" markerWidth="7" markerHeight="5" refX="7" refY="2.5" orient="auto">
            <polygon points="0 0,7 2.5,0 5" fill="#4b5563" />
          </marker>
          <marker id="arr-red" markerWidth="7" markerHeight="5" refX="7" refY="2.5" orient="auto">
            <polygon points="0 0,7 2.5,0 5" fill="#ef4444" />
          </marker>
          {/* Amber glow for Outcome head */}
          <radialGradient id="amber-glow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#f59e0b" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#f59e0b" stopOpacity="0"  />
          </radialGradient>
          {/* Blind-spot dash animation */}
          <style>{`
            @keyframes fb-dash { to { stroke-dashoffset: -24; } }
            .fb-blind { animation: fb-dash 1.1s linear infinite; }
          `}</style>
        </defs>

        {/* ── Fish tail ── */}
        <path
          d={`M${spineX1+6},${SPINE_Y} L${spineX1-16},${SPINE_Y-17} L${spineX1-4},${SPINE_Y} L${spineX1-16},${SPINE_Y+17} Z`}
          fill="#1c2533" stroke="#374151" strokeWidth="1"
        />

        {/* ── Spine ── */}
        <line
          x1={spineX1} y1={SPINE_Y} x2={spineX2} y2={SPINE_Y}
          stroke="#2d3748" strokeWidth="2.5"
          markerEnd="url(#arr)"
        />

        {/* ── Outcome glow (fish head) ── */}
        {(() => {
          const last = layouts[n - 1];
          return (
            <>
              <circle cx={last.x} cy={last.y} r={NODE_R + 20}
                fill="url(#amber-glow)" />
              {/* Double-chevron mouth */}
              <g transform={`translate(${last.x + NODE_R + 4},${last.y})`}>
                <polygon points="0,-11 16,0 0,11"  fill="#f59e0b" fillOpacity="0.55" />
                <polygon points="14,-8 26,0 14,8" fill="#f59e0b" fillOpacity="0.30" />
              </g>
            </>
          );
        })()}

        {/* ── Bones: branch nodes → spine attachment ── */}
        {layouts.filter(l => !l.onSpine).map(l => {
          const edge   = inEdge(l.node.id);
          const isBlind = edge?.soc_threshold_miss === true;
          const prob    = edge?.probability;
          const midX    = (l.x + l.attachX) / 2;
          const midY    = (l.y + SPINE_Y) / 2;

          return (
            <g key={`bone-${l.node.id}`}>
              <line
                x1={l.x}       y1={l.y}
                x2={l.attachX} y2={SPINE_Y}
                stroke={isBlind ? "#ef4444" : "#374151"}
                strokeWidth={isBlind ? 1.5 : 1.2}
                strokeDasharray={isBlind ? "5 4" : undefined}
                className={isBlind ? "fb-blind" : undefined}
                markerEnd={isBlind ? "url(#arr-red)" : "url(#arr)"}
              />

              {/* probability label alongside bone */}
              {prob != null && (
                <text
                  x={midX + (l.above ? -6 : 6)}
                  y={midY}
                  fill={isBlind ? "#ef4444" : "#4b5563"}
                  fontSize="9" textAnchor="middle" fontFamily="monospace"
                >
                  {`p=${prob.toFixed(2)}`}
                </text>
              )}

              {/* BLIND SPOT badge */}
              {isBlind && (
                <text
                  x={l.x + (l.above ? 0 : 0)}
                  y={l.above ? l.y - NODE_R - 7 : l.y + NODE_R + 13}
                  fill="#ef4444" fontSize="8" textAnchor="middle"
                  fontWeight="700" letterSpacing="0.5"
                >
                  BLIND SPOT
                </text>
              )}
            </g>
          );
        })}

        {/* ── Spine-to-spine edge labels ── */}
        {layouts
          .filter(l => l.onSpine && l !== layouts[0])
          .map(l => {
            // find edge from previous spine node
            const prevSpine = layouts.filter(ll => ll.onSpine && ll.x < l.x).at(-1);
            if (!prevSpine) return null;
            const edge = edgeMap.get(`${prevSpine.node.id}-${l.node.id}`);
            if (!edge?.probability) return null;
            return (
              <text key={`sl-${l.node.id}`}
                x={(prevSpine.x + l.x) / 2} y={SPINE_Y - 9}
                fill="#4b5563" fontSize="9" textAnchor="middle" fontFamily="monospace"
              >
                {`p=${edge.probability.toFixed(2)}`}
              </text>
            );
          })}

        {/* ── Nodes ── */}
        {layouts.map(({ node, x, y }) => {
          const s     = STYLE[node.node_type] ?? STYLE.Outcome;
          const lines = node.label.split("\n");

          return (
            <g key={node.id}>
              {/* Critical severity outer ring */}
              {node.severity === "critical" && (
                <circle cx={x} cy={y} r={NODE_R + 7}
                  fill="none" stroke={s.stroke} strokeWidth="1" strokeOpacity="0.3" />
              )}
              {/* Node body */}
              <circle cx={x} cy={y} r={NODE_R}
                fill={s.fill} stroke={s.stroke} strokeWidth="1.6" />
              {/* Type tag */}
              <text x={x} y={y - 10} fontSize="7.5" fontWeight="700"
                fill={s.text} textAnchor="middle" fontFamily="monospace" letterSpacing="0.4">
                {s.tag}
              </text>
              {/* Main label */}
              <text x={x} y={y + 2} fontSize="9.5" fontWeight="600"
                fill="#ffffff" textAnchor="middle" fontFamily="system-ui">
                {clamp(lines[0], 10)}
              </text>
              {/* Sub label */}
              {lines[1] && (
                <text x={x} y={y + 14} fontSize="8"
                  fill={s.text} textAnchor="middle" fontFamily="system-ui" opacity="0.85">
                  {clamp(lines[1], 13)}
                </text>
              )}
            </g>
          );
        })}

        {/* ── Legend ── */}
        <g transform={`translate(8,${height - 20})`}>
          {[
            { c: "#ef4444", l: "CVE"       },
            { c: "#f97316", l: "CWE"       },
            { c: "#8b5cf6", l: "Technique" },
            { c: "#22c55e", l: "Detection" },
            { c: "#f59e0b", l: "Outcome"   },
          ].map(({ c, l }, i) => (
            <g key={l} transform={`translate(${i * 88},0)`}>
              <circle cx="5" cy="5" r="4" fill="#080808" stroke={c} strokeWidth="1.5" />
              <text x="13" y="9" fill="#4b5563" fontSize="8" fontFamily="system-ui">{l}</text>
            </g>
          ))}
          <g transform="translate(440,0)">
            <line x1="0" y1="5" x2="20" y2="5"
              stroke="#ef4444" strokeWidth="1.5" strokeDasharray="4 3" />
            <text x="24" y="9" fill="#4b5563" fontSize="8" fontFamily="system-ui">
              SOC blind spot
            </text>
          </g>
        </g>
      </svg>
    </div>
  );
}
