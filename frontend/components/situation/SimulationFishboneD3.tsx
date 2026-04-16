"use client";

import { useEffect, useRef } from "react";
import * as d3 from "d3";
import type { CSEActionEvent } from "@/lib/types/situation";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const H             = 340;
const SPINE_Y       = 160;
const BONE_LEN      = 90;
const BONE_DX       = 48;   // horizontal offset from spine attachment to node
const NODE_R        = 18;
const SPINE_PAD     = 80;
const MIN_W         = 600;
const EVENTS_SHOWN  = 40;   // max bones rendered (keep readable)
const SIG_THRESHOLD = 0.55; // only bones for significant events

// ---------------------------------------------------------------------------
// Agent → visual config
// ---------------------------------------------------------------------------
const AGENT_CONFIG: Record<string, { color: string; side: 1 | -1; label: string }> = {
  Attacker:   { color: "#ef4444", side: -1, label: "ATK" },  // above spine
  SOCAnalyst: { color: "#3b82f6", side:  1, label: "SOC" },  // below
  Defender:   { color: "#3b82f6", side:  1, label: "DEF" },
  DevSecOps:  { color: "#22c55e", side:  1, label: "DEV" },
  CISO:       { color: "#8b5cf6", side: -1, label: "CISO" },
  Regulator:  { color: "#f97316", side:  1, label: "REG" },
};

function cfg(agentType: string) {
  return AGENT_CONFIG[agentType] ?? { color: "#6b7280", side: 1 as const, label: "???" };
}

function truncate(s: string, max = 16) {
  return s && s.length > max ? s.slice(0, max - 1) + "…" : (s ?? "");
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
interface Props {
  events: CSEActionEvent[];
  totalRounds?: number;
  isRunning?: boolean;
}

export function SimulationFishboneD3({ events, totalRounds = 720, isRunning = false }: Props) {
  const svgRef  = useRef<SVGSVGElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const simId   = useRef(`fb-${Math.random().toString(36).slice(2)}`);

  function showTooltip(d: CSEActionEvent, mouseX: number, mouseY: number) {
    const tip = document.getElementById(`fb-tooltip-${simId.current}`);
    if (!tip || !wrapRef.current) return;
    const rect = wrapRef.current.getBoundingClientRect();
    const c = cfg(d.agent_type);
    tip.innerHTML = [
      `<span style="color:${c.color};font-weight:700">${d.agent_type}</span>`,
      `<span style="color:#9ca3af"> · round ${d.round_no}</span>`,
      `<br/><span style="color:#6b7280">${d.action_type}</span>`,
      `<br/>${d.outcome ?? ""}`,
    ].join("");
    const tx = mouseX - rect.left + 12;
    const ty = mouseY - rect.top - 10;
    tip.style.left = `${Math.min(tx, rect.width - 250)}px`;
    tip.style.top  = `${ty}px`;
    tip.style.display = "block";
  }

  function hideTooltip() {
    const tip = document.getElementById(`fb-tooltip-${simId.current}`);
    if (tip) tip.style.display = "none";
  }

  useEffect(() => {
    const svg = svgRef.current;
    const wrap = wrapRef.current;
    if (!svg || !wrap) return;

    const W = Math.max(MIN_W, wrap.clientWidth || MIN_W);
    const spineLen = W - SPINE_PAD * 2;

    // Filter to significant events, deduplicate by round+agent, limit count
    const filtered = events
      .filter(e => (e.significance ?? 0) >= SIG_THRESHOLD)
      .reduce<CSEActionEvent[]>((acc, e) => {
        const key = `${e.round_no}-${e.agent_type}`;
        if (!acc.find(x => `${x.round_no}-${x.agent_type}` === key)) acc.push(e);
        return acc;
      }, [])
      .slice(-EVENTS_SHOWN);

    const maxRound = Math.max(totalRounds, ...events.map(e => e.round_no ?? 0), 1);
    const xScale = d3.scaleLinear().domain([0, maxRound]).range([SPINE_PAD, SPINE_PAD + spineLen]);

    const sel = d3.select(svg);
    sel.attr("width", W).attr("height", H).attr("viewBox", `0 0 ${W} ${H}`);

    // One-time setup of defs + static elements
    if (sel.select("defs").empty()) {
      const defs = sel.append("defs");

      // Arrow markers
      ["grey", "red", "blue", "green", "purple", "orange"].forEach(name => {
        const colors: Record<string, string> = {
          grey: "#4b5563", red: "#ef4444", blue: "#3b82f6",
          green: "#22c55e", purple: "#8b5cf6", orange: "#f97316",
        };
        defs.append("marker")
          .attr("id", `arr-${name}`)
          .attr("markerWidth", 6).attr("markerHeight", 5)
          .attr("refX", 6).attr("refY", 2.5).attr("orient", "auto")
          .append("polygon")
          .attr("points", "0 0,6 2.5,0 5")
          .attr("fill", colors[name]);
      });

      // Amber glow for head
      const glow = defs.append("radialGradient").attr("id", "head-glow")
        .attr("cx", "50%").attr("cy", "50%").attr("r", "50%");
      glow.append("stop").attr("offset", "0%").attr("stop-color", "#f59e0b").attr("stop-opacity", 0.3);
      glow.append("stop").attr("offset", "100%").attr("stop-color", "#f59e0b").attr("stop-opacity", 0);

      // Animation style
      sel.append("style").text(`
        @keyframes fb-pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
        .running-dot { animation: fb-pulse 1.2s ease-in-out infinite; }
        .bone-enter { opacity: 0; }
        .bone-enter-done { opacity: 1; transition: opacity 0.4s ease; }
      `);

      // ── Static: fish tail ──
      sel.append("g").attr("class", "fish-tail")
        .append("path")
        .attr("d", `M${SPINE_PAD-2},${SPINE_Y} L${SPINE_PAD-24},${SPINE_Y-18} L${SPINE_PAD-12},${SPINE_Y} L${SPINE_PAD-24},${SPINE_Y+18} Z`)
        .attr("fill", "#1c2533").attr("stroke", "#374151").attr("stroke-width", 1);

      // ── Static: spine ──
      sel.append("line").attr("class", "spine")
        .attr("stroke", "#2d3748").attr("stroke-width", 2.5).attr("marker-end", "url(#arr-grey)");

      // ── Static: fish head glow ──
      sel.append("circle").attr("class", "head-glow").attr("fill", "url(#head-glow)");

      // ── Static: fish head chevrons ──
      sel.append("g").attr("class", "head-chevrons");

      // ── Static: round axis ticks ──
      sel.append("g").attr("class", "round-ticks");

      // ── Dynamic: bones group ──
      sel.append("g").attr("class", "bones");

      // ── Dynamic: running indicator ──
      sel.append("circle").attr("class", "running-dot")
        .attr("r", 6).attr("fill", "#22c55e").style("display", "none");
    }

    // ── Update spine length ──
    sel.select<SVGLineElement>("line.spine")
      .attr("x1", SPINE_PAD - 8).attr("y1", SPINE_Y)
      .attr("x2", SPINE_PAD + spineLen + 16).attr("y2", SPINE_Y);

    // ── Update head ──
    const headX = SPINE_PAD + spineLen + 20;
    sel.select("circle.head-glow")
      .attr("cx", headX).attr("cy", SPINE_Y).attr("r", NODE_R + 22);

    sel.select("g.head-chevrons")
      .attr("transform", `translate(${headX + NODE_R + 2},${SPINE_Y})`)
      .selectAll("polygon")
      .data([
        { pts: "0,-13 18,0 0,13",  op: 0.6 },
        { pts: "16,-10 30,0 16,10", op: 0.3 },
      ])
      .join("polygon")
      .attr("points", d => d.pts)
      .attr("fill", "#f59e0b")
      .attr("fill-opacity", d => d.op);

    // ── Zone labels (Attack above, Defence below) ──
    if (sel.select("text.zone-attack").empty()) {
      sel.append("text").attr("class", "zone-attack")
        .attr("x", SPINE_PAD).attr("y", SPINE_Y - BONE_LEN - 10)
        .attr("fill", "#ef444466").attr("font-size", 10).attr("font-weight", 700)
        .attr("font-family", "monospace").attr("letter-spacing", 1)
        .text("▲ ATTACK");
      sel.append("text").attr("class", "zone-defence")
        .attr("x", SPINE_PAD).attr("y", SPINE_Y + BONE_LEN + 20)
        .attr("fill", "#3b82f666").attr("font-size", 10).attr("font-weight", 700)
        .attr("font-family", "monospace").attr("letter-spacing", 1)
        .text("▼ DEFENCE");
    }

    // ── Round axis ticks — labelled as % progress ──
    const tickData = d3.range(0, 11).map(i => ({
      round: Math.round(maxRound * i / 10),
      pct: i * 10,
      x: xScale(Math.round(maxRound * i / 10)),
    }));
    sel.select<SVGGElement>("g.round-ticks")
      .selectAll<SVGGElement, typeof tickData[0]>("g.tick")
      .data(tickData, d => d.round)
      .join(enter => {
        const g = enter.append("g").attr("class", "tick");
        g.append("line").attr("stroke", "#1f2937").attr("stroke-width", 1)
          .attr("y1", SPINE_Y - 4).attr("y2", SPINE_Y + 4);
        // Percentage label
        g.append("text").attr("class", "pct-label")
          .attr("fill", "#4b5563").attr("font-size", 8)
          .attr("text-anchor", "middle").attr("y", SPINE_Y + 14).attr("font-family", "monospace");
        // Round number below
        g.append("text").attr("class", "round-label")
          .attr("fill", "#1f2937").attr("font-size", 7)
          .attr("text-anchor", "middle").attr("y", SPINE_Y + 23).attr("font-family", "monospace");
        return g;
      })
      .each(function(d) {
        d3.select(this).select("line").attr("x1", d.x).attr("x2", d.x);
        d3.select(this).select("text.pct-label").attr("x", d.x)
          .text(d.pct === 0 ? "start" : d.pct === 100 ? "end" : `${d.pct}%`);
        d3.select(this).select("text.round-label").attr("x", d.x)
          .text(d.pct > 0 && d.pct < 100 ? `r${d.round}` : "");
      });

    // ── Running dot ──
    const lastRound = events.length ? events[events.length - 1].round_no ?? 0 : 0;
    const dotX = xScale(lastRound);
    sel.select<SVGCircleElement>("circle.running-dot")
      .attr("cx", dotX).attr("cy", SPINE_Y)
      .style("display", isRunning ? "" : "none");

    // ── Bones (key = round_no + agent_type) ──
    const bones = sel.select<SVGGElement>("g.bones")
      .selectAll<SVGGElement, CSEActionEvent>("g.bone")
      .data(filtered, d => `${d.round_no}-${d.agent_type}`)
      .join(
        enter => {
          const g = enter.append("g").attr("class", "bone").style("opacity", 0);
          g.append("line").attr("class", "bone-line");
          g.append("circle").attr("class", "bone-node").attr("r", NODE_R);
          g.append("text").attr("class", "bone-tag");
          g.append("text").attr("class", "bone-label");
          // Fade in
          g.transition().duration(400).style("opacity", 1);
          return g;
        },
        update => update,
        exit => exit.transition().duration(200).style("opacity", 0).remove(),
      );

    // Update positions
    bones.each(function(d) {
      const g     = d3.select(this);
      const c     = cfg(d.agent_type);
      const ax    = xScale(d.round_no ?? 0);               // spine attachment x
      const nx    = ax + BONE_DX;                          // node x
      const ny    = SPINE_Y + c.side * BONE_LEN;           // node y

      // Determine arrow marker colour
      const markerMap: Record<string, string> = {
        "#ef4444": "red", "#3b82f6": "blue",
        "#22c55e": "green", "#8b5cf6": "purple", "#f97316": "orange",
      };
      const markerName = markerMap[c.color] ?? "grey";

      g.select<SVGLineElement>("line.bone-line")
        .attr("x1", nx).attr("y1", ny)
        .attr("x2", ax).attr("y2", SPINE_Y)
        .attr("stroke", c.color).attr("stroke-width", 1.2)
        .attr("marker-end", `url(#arr-${markerName})`);

      g.select<SVGCircleElement>("circle.bone-node")
        .attr("cx", nx).attr("cy", ny)
        .attr("fill", "#0a0a0a").attr("stroke", c.color).attr("stroke-width", 1.5)
        .style("cursor", "pointer")
        .on("mouseenter", (event: MouseEvent) => showTooltip(d, event.clientX, event.clientY))
        .on("mousemove",  (event: MouseEvent) => showTooltip(d, event.clientX, event.clientY))
        .on("mouseleave", () => hideTooltip());

      // Type tag
      g.select<SVGTextElement>("text.bone-tag")
        .attr("x", nx).attr("y", ny - 6)
        .attr("text-anchor", "middle")
        .attr("font-size", 7).attr("font-weight", 700)
        .attr("font-family", "monospace").attr("fill", c.color)
        .text(c.label);

      // Outcome label
      const outcome = truncate((d.outcome ?? "").replace(/^[^:]+:\s*/, ""), 14);
      g.select<SVGTextElement>("text.bone-label")
        .attr("x", nx).attr("y", ny + 5)
        .attr("text-anchor", "middle")
        .attr("font-size", 8).attr("font-family", "system-ui").attr("fill", "#e5e7eb")
        .text(outcome);
    });

    // ── Legend ──
    if (sel.select("g.legend").empty()) {
      const lg = sel.append("g").attr("class", "legend")
        .attr("transform", `translate(${SPINE_PAD}, ${H - 22})`);

      Object.entries(AGENT_CONFIG).forEach(([name, ac], i) => {
        const gx = i * 95;
        const g = lg.append("g").attr("transform", `translate(${gx},0)`);
        g.append("circle").attr("cx", 5).attr("cy", 5).attr("r", 5)
          .attr("fill", "#0a0a0a").attr("stroke", ac.color).attr("stroke-width", 1.5);
        g.append("text").attr("x", 14).attr("y", 9)
          .attr("fill", "#4b5563").attr("font-size", 8).attr("font-family", "system-ui")
          .text(name);
      });
    }

  }, [events, totalRounds, isRunning]);

  return (
    <div ref={wrapRef} className="w-full overflow-x-auto rounded-md bg-[#080808] border border-border relative">
      <svg ref={svgRef} style={{ display: "block", minWidth: "100%" }} />
      {/* Tooltip rendered in React so it can overflow the SVG */}
      <div id={`fb-tooltip-${simId.current}`}
        style={{ position: "absolute", pointerEvents: "none", display: "none",
          background: "#1f2937", border: "1px solid #374151", borderRadius: 6,
          padding: "6px 10px", fontSize: 11, color: "#e5e7eb", maxWidth: 240,
          lineHeight: 1.5, zIndex: 50 }}
      />
    </div>
  );
}
