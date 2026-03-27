"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useSession } from "next-auth/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type MessageRole = "user" | "assistant";

interface ToolActivity {
  name: string;
  args: Record<string, unknown>;
  status: "running" | "done";
  preview?: string;
  sourceLabels?: string[];
  startedAt?: number;
  completedAt?: number;
}

interface ChatMessage {
  role: MessageRole;
  content: string;
  toolCalls?: ToolActivity[];
}

interface SSEEvent {
  type: "text" | "tool_call" | "tool_result" | "done" | "error" | "artifact";
  content?: string;
  name?: string;
  args?: Record<string, unknown>;
  preview?: string;
  source_labels?: string[];
  message?: string;
  // artifact fields
  subtype?: "dashboard" | "fair_report" | "heatmap" | "slides";
  title?: string;
  html?: string;
}

interface Artifact {
  id: string;
  subtype: "dashboard" | "fair_report" | "heatmap" | "slides";
  title: string;
  html: string;
  createdAt: Date;
}

// ---------------------------------------------------------------------------
// Demo starter questions
// ---------------------------------------------------------------------------

const STARTER_QUESTIONS = [
  { icon: "⚡", text: "Give me an executive summary of our vulnerability posture" },
  { icon: "🎯", text: "Show me the regulatory blast radius for CVE-2021-44228" },
  { icon: "⚖️", text: "How does FDA 524B differ from EU CRA for our most critical CVE?" },
  { icon: "📦", text: "Which components carry the highest supply chain risk?" },
  { icon: "🔥", text: "What should my team fix first this week?" },
  { icon: "📈", text: "Is our security posture getting better or worse over time?" },
];

// ---------------------------------------------------------------------------
// Tool labels
// ---------------------------------------------------------------------------

const TOOL_LABELS: Record<string, string> = {
  get_vulnerability_summary: "Querying vulnerability summary",
  get_critical_findings: "Fetching critical findings",
  get_top_affected_components: "Analyzing affected components",
  get_compliance_posture: "Checking compliance posture",
  get_kev_exposure: "Scanning CISA KEV exposure",
  get_regulatory_blast_radius: "Mapping regulatory blast radius",
  get_scan_trend: "Loading scan history",
  get_project_risk_breakdown: "Aggregating project risk",
  get_nist_control_coverage: "Checking NIST control coverage",
  get_epss_rising_findings: "Fetching rising EPSS findings",
  emit_artifact: "Building visual artifact",
};

// ---------------------------------------------------------------------------
// Markdown components (react-markdown v9 — no `inline` prop on code)
// ---------------------------------------------------------------------------

const mdComponents: Components = {
  pre({ children }) {
    return (
      <pre className="bg-[#0d1117] border border-zinc-700/60 rounded-xl p-4 overflow-x-auto my-3 text-xs">
        {children}
      </pre>
    );
  },
  code({ className, children, ...rest }) {
    const isBlock = /language-/.test(className ?? "");
    if (isBlock) {
      return (
        <code className={`text-emerald-400 font-mono ${className ?? ""}`} {...rest}>
          {children}
        </code>
      );
    }
    return (
      <code className="bg-zinc-800 text-emerald-400 px-1.5 py-0.5 rounded text-[0.8em] font-mono" {...rest}>
        {children}
      </code>
    );
  },
  table({ children }) {
    return (
      <div className="overflow-x-auto my-4 rounded-xl border border-zinc-700/60">
        <table className="min-w-full text-sm">{children}</table>
      </div>
    );
  },
  thead({ children }) {
    return <thead className="bg-zinc-800/80 text-zinc-300">{children}</thead>;
  },
  tbody({ children }) {
    return <tbody className="divide-y divide-zinc-800">{children}</tbody>;
  },
  tr({ children }) {
    return <tr className="hover:bg-zinc-800/40 transition-colors">{children}</tr>;
  },
  th({ children }) {
    return (
      <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-400">
        {children}
      </th>
    );
  },
  td({ children }) {
    return <td className="px-4 py-2.5 text-zinc-200">{children}</td>;
  },
  strong({ children }) {
    return <strong className="text-white font-semibold">{children}</strong>;
  },
  ul({ children }) {
    return <ul className="list-disc list-inside space-y-1 my-2 text-zinc-200">{children}</ul>;
  },
  ol({ children }) {
    return <ol className="list-decimal list-inside space-y-1 my-2 text-zinc-200">{children}</ol>;
  },
  li({ children }) {
    return <li className="text-zinc-200">{children}</li>;
  },
  h1({ children }) {
    return <h1 className="text-xl font-bold text-white mt-5 mb-2">{children}</h1>;
  },
  h2({ children }) {
    return (
      <h2 className="text-base font-semibold text-white mt-4 mb-2 border-b border-zinc-700/60 pb-1">
        {children}
      </h2>
    );
  },
  h3({ children }) {
    return <h3 className="text-sm font-semibold text-zinc-100 mt-3 mb-1">{children}</h3>;
  },
  p({ children }) {
    return <p className="text-zinc-200 leading-relaxed mb-2 last:mb-0">{children}</p>;
  },
  blockquote({ children }) {
    return (
      <blockquote className="border-l-2 border-emerald-500/60 pl-4 my-3 text-zinc-400 italic">
        {children}
      </blockquote>
    );
  },
};

// ---------------------------------------------------------------------------
// Tool indicator row
// ---------------------------------------------------------------------------

function ToolIndicator({ activity }: { activity: ToolActivity }) {
  const label = TOOL_LABELS[activity.name] ?? activity.name.replace(/_/g, " ");
  const isDone = activity.status === "done";
  const elapsed =
    activity.completedAt && activity.startedAt
      ? ((activity.completedAt - activity.startedAt) / 1000).toFixed(1)
      : null;

  return (
    <div
      className={`text-xs py-1.5 px-3 rounded-lg my-0.5 border transition-all duration-300 ${
        isDone
          ? "bg-emerald-950/20 border-emerald-800/20"
          : "bg-zinc-800/60 border-zinc-700/60"
      }`}
    >
      {/* Row 1 — icon + label + elapsed */}
      <div className="flex items-center gap-2">
        {isDone ? (
          <svg className="w-3 h-3 text-emerald-500 shrink-0" fill="none" viewBox="0 0 12 12">
            <path stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" d="M2.5 6l2.5 2.5 4.5-5" />
          </svg>
        ) : (
          <svg className="w-3 h-3 text-emerald-400 shrink-0 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
            <path className="opacity-80" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        )}
        <span className={`flex-1 ${isDone ? "text-zinc-500" : "text-zinc-300"}`}>{label}</span>
        {activity.args?.cve_id != null && (
          <span className="font-mono text-emerald-500/70 text-[10px]">{String(activity.args.cve_id)}</span>
        )}
        {elapsed && <span className="text-zinc-600 text-[10px] ml-1">{elapsed}s</span>}
      </div>

      {/* Row 2 — result preview (done only) */}
      {isDone && activity.preview && (
        <p className="mt-0.5 ml-5 text-[11px] text-zinc-400 leading-snug">{activity.preview}</p>
      )}

      {/* Row 3 — source labels */}
      {isDone && activity.sourceLabels && activity.sourceLabels.length > 0 && (
        <div className="mt-1 ml-5 flex flex-wrap gap-1">
          {activity.sourceLabels.map((s) => (
            <span key={s} className="px-1.5 py-px rounded text-[10px] bg-zinc-800 text-zinc-500 border border-zinc-700/50">
              {s}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Artifact panel — split-pane right side with tabs + download + sandboxed iframe
// ---------------------------------------------------------------------------

const SUBTYPE_ICONS: Record<string, string> = {
  dashboard: "▦",
  fair_report: "⊞",
  heatmap: "◫",
  slides: "▷",
};

function ArtifactPanel({
  artifacts,
  activeId,
  onSelectTab,
  onClose,
}: {
  artifacts: Artifact[];
  activeId: string;
  onSelectTab: (id: string) => void;
  onClose: () => void;
}) {
  const active = artifacts.find((a) => a.id === activeId) ?? artifacts[artifacts.length - 1];
  if (!active) return null;

  const handleDownload = () => {
    const blob = new Blob([active.html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${active.title.replace(/\s+/g, "_")}.html`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex flex-col h-full bg-zinc-950 border-l border-zinc-800">
      {/* Panel header */}
      <div className="shrink-0 flex items-center justify-between px-3 py-2.5 border-b border-zinc-800 bg-zinc-900/60">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-emerald-400 text-xs font-mono shrink-0">
            {SUBTYPE_ICONS[active.subtype] ?? "▦"}
          </span>
          <span className="text-xs font-medium text-zinc-200 truncate">{active.title}</span>
        </div>
        <div className="flex items-center gap-1.5 shrink-0 ml-2">
          <button
            onClick={handleDownload}
            className="flex items-center gap-1 px-2 py-1 rounded-md text-[11px] text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
            title="Download HTML"
          >
            <svg className="w-3 h-3" fill="none" viewBox="0 0 16 16" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M8 2v8m0 0l-3-3m3 3l3-3M3 13h10" />
            </svg>
            Download
          </button>
          <button
            onClick={onClose}
            className="w-6 h-6 flex items-center justify-center rounded-md text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 transition-colors text-xs"
            title="Close panel"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Tabs — only when multiple artifacts */}
      {artifacts.length > 1 && (
        <div className="shrink-0 flex gap-0 border-b border-zinc-800 overflow-x-auto bg-zinc-900/40 px-2 pt-1.5">
          {artifacts.map((a) => (
            <button
              key={a.id}
              onClick={() => onSelectTab(a.id)}
              className={`shrink-0 px-3 py-1.5 text-[11px] rounded-t-md border border-b-0 transition-colors mr-1 ${
                a.id === activeId
                  ? "bg-zinc-950 border-zinc-700 text-zinc-200"
                  : "bg-transparent border-transparent text-zinc-500 hover:text-zinc-300"
              }`}
            >
              <span className="mr-1">{SUBTYPE_ICONS[a.subtype] ?? "▦"}</span>
              {a.title.length > 20 ? a.title.slice(0, 18) + "…" : a.title}
            </button>
          ))}
        </div>
      )}

      {/* Sandboxed iframe */}
      <div className="flex-1 relative">
        <iframe
          key={active.id}
          srcDoc={active.html}
          className="w-full h-full border-0"
          sandbox="allow-scripts"
          title={active.title}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Message bubble
// ---------------------------------------------------------------------------

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const hasContent = message.content.length > 0;
  const hasTools = (message.toolCalls?.length ?? 0) > 0;

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : "flex-row"} items-start`}>
      <div
        className={`shrink-0 w-7 h-7 rounded-lg flex items-center justify-center mt-0.5 ${
          isUser ? "bg-emerald-700 text-white" : "bg-zinc-800 text-zinc-400 border border-zinc-700"
        }`}
      >
        {isUser ? (
          <span className="text-[10px] font-bold">You</span>
        ) : (
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
        )}
      </div>

      <div
        className={`max-w-[84%] rounded-2xl px-4 py-3 text-sm ${
          isUser
            ? "bg-zinc-800 border border-zinc-700 text-zinc-100 rounded-tr-sm"
            : "bg-zinc-900 border border-zinc-800 text-zinc-100 rounded-tl-sm"
        }`}
      >
        {hasTools && (
          <div className={hasContent ? "mb-3" : ""}>
            {message.toolCalls!.map((tc, i) => (
              <ToolIndicator key={i} activity={tc} />
            ))}
          </div>
        )}

        {isUser ? (
          <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
        ) : hasContent ? (
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
            {message.content}
          </ReactMarkdown>
        ) : null}

        {!isUser && !hasContent && !hasTools && (
          <div className="flex gap-1 items-center h-5">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="w-1.5 h-1.5 bg-zinc-600 rounded-full animate-bounce"
                style={{ animationDelay: `${i * 0.12}s` }}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function AskCompliraPage() {
  const { data: session } = useSession();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [isGeneratingArtifact, setIsGeneratingArtifact] = useState(false);
  const [streamingStatus, setStreamingStatus] = useState<string | null>(null);
  const [activeTools, setActiveTools] = useState<string[]>([]);
  const [completedTools, setCompletedTools] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [activeArtifactId, setActiveArtifactId] = useState<string | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
  };

  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim() || isStreaming) return;

      setError(null);
      const trimmed = text.trim();
      const historySnapshot = messages;

      setMessages((prev) => [
        ...prev,
        { role: "user", content: trimmed },
        { role: "assistant", content: "", toolCalls: [] },
      ]);
      setInput("");
      if (inputRef.current) inputRef.current.style.height = "auto";
      setIsStreaming(true);
      setActiveTools([]);
      setCompletedTools([]);
      setIsGeneratingArtifact(true); // show right panel immediately

      abortRef.current = new AbortController();

      try {
        const response = await fetch(`${API_URL}/v1/chat/stream`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(session?.accessToken
              ? { Authorization: `Bearer ${session.accessToken}` }
              : {}),
          },
          body: JSON.stringify({
            messages: [
              ...historySnapshot.map((m) => ({ role: m.role, content: m.content })),
              { role: "user", content: trimmed },
            ],
          }),
          signal: abortRef.current.signal,
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const reader = response.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let streamDone = false;

        while (!streamDone) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const raw = line.slice(6).trim();
            if (!raw) continue;

            let event: SSEEvent;
            try {
              event = JSON.parse(raw);
            } catch {
              continue;
            }

            if (event.type === "text") {
              setStreamingStatus(null);
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last?.role === "assistant") {
                  updated[updated.length - 1] = {
                    ...last,
                    content: last.content + (event.content ?? ""),
                  };
                }
                return updated;
              });
            } else if (event.type === "tool_call") {
              const toolName = event.name ?? "";
              const label = TOOL_LABELS[toolName] ?? toolName.replace(/_/g, " ");
              setStreamingStatus(label);
              setActiveTools((prev) => prev.includes(toolName) ? prev : [...prev, toolName]);
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (!last || last.role !== "assistant") return prev;
                const existing = last.toolCalls ?? [];
                if (existing.some((tc) => tc.name === toolName && tc.status === "running")) {
                  return prev;
                }
                updated[updated.length - 1] = {
                  ...last,
                  toolCalls: [
                    ...existing,
                    {
                      name: toolName,
                      args: event.args ?? {},
                      status: "running" as const,
                      sourceLabels: event.source_labels ?? [],
                      startedAt: Date.now(),
                    },
                  ],
                };
                return updated;
              });
            } else if (event.type === "tool_result") {
              const toolName = event.name ?? "";
              const preview = event.preview;
              setActiveTools((prev) => prev.filter((t) => t !== toolName));
              setCompletedTools((prev) => prev.includes(toolName) ? prev : [...prev, toolName]);
              setStreamingStatus(null);
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (!last || last.role !== "assistant" || !last.toolCalls) return prev;
                const toolCalls = [...last.toolCalls];
                for (let i = toolCalls.length - 1; i >= 0; i--) {
                  if (toolCalls[i].name === toolName && toolCalls[i].status === "running") {
                    toolCalls[i] = {
                      ...toolCalls[i],
                      status: "done",
                      preview,
                      completedAt: Date.now(),
                    };
                    break;
                  }
                }
                updated[updated.length - 1] = { ...last, toolCalls };
                return updated;
              });
            } else if (event.type === "artifact") {
              if (event.html && event.title) {
                const newArtifact: Artifact = {
                  id: `artifact-${Date.now()}`,
                  subtype: event.subtype ?? "dashboard",
                  title: event.title,
                  html: event.html,
                  createdAt: new Date(),
                };
                setArtifacts((prev) => [...prev, newArtifact]);
                setActiveArtifactId(newArtifact.id);
              }
            } else if (event.type === "error") {
              const raw = event.content ?? event.message ?? "Unknown error";
              const friendly = raw.includes("usage limits")
                ? "API usage limit reached. Access will be restored on 2026-04-01. Please try again then."
                : raw.includes("Claude API error:")
                ? (raw.match(/'message':\s*'([^']+)'/) ?? [])[1]?.trim() ?? raw
                : raw;
              setError(friendly);
              setIsGeneratingArtifact(false);
              setStreamingStatus(null);
              streamDone = true;
              break;
            } else if (event.type === "done") {
              setIsGeneratingArtifact(false);
              setStreamingStatus(null);
              streamDone = true;
              break;
            }
          }
        }
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          setError((err as Error).message);
        }
      } finally {
        setIsStreaming(false);
        setIsGeneratingArtifact(false);
        setStreamingStatus(null);
        setActiveTools([]);
        abortRef.current = null;
        inputRef.current?.focus();
      }
    },
    [messages, isStreaming, session]
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  const stopStreaming = () => {
    abortRef.current?.abort();
    setIsStreaming(false);
  };

  const isEmpty = messages.length === 0;
  const showArtifactPanel = activeArtifactId !== null && artifacts.length > 0;
  const showLoadingPanel = isGeneratingArtifact && !showArtifactPanel;

  return (
    <div className="flex h-screen bg-zinc-950 text-zinc-100 antialiased">

      {/* ── Chat pane ── */}
      <div className={`flex flex-col ${showArtifactPanel || showLoadingPanel ? "w-[42%]" : "w-full"} transition-all duration-300 min-w-0`}>

        {/* Header */}
        <header className="shrink-0 flex items-center justify-between px-5 py-3.5 border-b border-zinc-800/80 bg-zinc-950/90 backdrop-blur-sm z-10">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 rounded-lg bg-emerald-600 flex items-center justify-center shadow-lg shadow-emerald-950/60">
              <svg className="w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <div className="leading-tight">
              <span className="text-sm font-semibold text-white">Complira</span>
              <span className="text-xs text-zinc-500 ml-2">Security Intelligence</span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {artifacts.length > 0 && (
              <button
                onClick={() => setActiveArtifactId(artifacts[artifacts.length - 1].id)}
                className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-emerald-950/60 border border-emerald-800/40 text-[11px] text-emerald-400 hover:bg-emerald-900/40 transition-colors"
              >
                <span className="font-mono">▦</span>
                {artifacts.length} artifact{artifacts.length !== 1 ? "s" : ""}
              </button>
            )}
            <div className="flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-[11px] text-zinc-500">Knowledge Graph · Live</span>
            </div>
          </div>
        </header>

        {/* Messages */}
        <main className="flex-1 overflow-y-auto">
          {isEmpty ? (
            <div className="flex flex-col items-center justify-center min-h-full gap-10 px-4 py-12">
              <div className="text-center space-y-3 max-w-md">
                <div className="w-12 h-12 mx-auto rounded-2xl bg-emerald-600/15 border border-emerald-600/20 flex items-center justify-center">
                  <svg className="w-6 h-6 text-emerald-400/80" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                  </svg>
                </div>
                <h2 className="text-lg font-semibold text-white tracking-tight">What do you need to know?</h2>
                <p className="text-sm text-zinc-500 leading-relaxed">
                  Ask about your vulnerability posture, a specific CVE&apos;s regulatory impact,
                  compliance gaps, or remediation priorities. Ask to &ldquo;build a dashboard&rdquo; to get a visual.
                </p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-2xl">
                {STARTER_QUESTIONS.map(({ icon, text }) => (
                  <button
                    key={text}
                    onClick={() => sendMessage(text)}
                    className="text-left text-sm px-4 py-3 rounded-xl bg-zinc-900 border border-zinc-800 hover:border-zinc-600 hover:bg-zinc-800/80 transition-all duration-150 text-zinc-400 hover:text-zinc-200 flex items-start gap-3"
                  >
                    <span className="text-base shrink-0 mt-px">{icon}</span>
                    <span>{text}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto px-4 py-6 space-y-5">
              {messages.map((msg, i) => (
                <MessageBubble key={i} message={msg} />
              ))}
              {error && (
                <div className="rounded-xl bg-red-950/50 border border-red-800/60 px-4 py-3 text-sm text-red-300 flex items-center gap-2">
                  <svg className="w-4 h-4 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M18 10A8 8 0 112 10a8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                  </svg>
                  <span className="flex-1">{error}</span>
                  <button onClick={() => setError(null)} className="text-red-400 hover:text-red-200 transition-colors">✕</button>
                </div>
              )}
            </div>
          )}
          <div ref={bottomRef} />
        </main>

        {/* Input */}
        <footer className="shrink-0 border-t border-zinc-800/80 bg-zinc-950/90 backdrop-blur-sm px-4 py-3">
          <div className="mx-auto max-w-3xl">
            <div className="flex items-end gap-3 bg-zinc-900 border border-zinc-800 rounded-2xl px-4 py-3 focus-within:border-zinc-600 transition-colors duration-150">
              <textarea
                ref={inputRef}
                value={input}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                placeholder="Ask about a CVE, compliance posture, or say 'build me a risk dashboard'…"
                rows={1}
                disabled={isStreaming}
                className="flex-1 bg-transparent text-sm text-zinc-100 placeholder-zinc-600 resize-none outline-none min-h-[22px] max-h-[160px] leading-[1.6] disabled:opacity-50"
              />
              {isStreaming ? (
                <button
                  onClick={stopStreaming}
                  className="shrink-0 w-7 h-7 rounded-lg bg-zinc-700 hover:bg-zinc-600 flex items-center justify-center text-zinc-300 transition-colors"
                  title="Stop"
                >
                  <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 12 12">
                    <rect x="2" y="2" width="8" height="8" rx="1" />
                  </svg>
                </button>
              ) : (
                <button
                  onClick={() => sendMessage(input)}
                  disabled={!input.trim()}
                  className="shrink-0 w-7 h-7 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-25 disabled:cursor-not-allowed flex items-center justify-center text-white transition-colors"
                  title="Send (Enter)"
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 10.5L12 3m0 0l7.5 7.5M12 3v18" />
                  </svg>
                </button>
              )}
            </div>
            {/* Global streaming status */}
            {streamingStatus && (
              <div className="mt-2 flex items-center justify-center gap-2 text-[11px] text-zinc-500">
                <svg className="w-3 h-3 text-emerald-500 animate-spin shrink-0" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                  <path className="opacity-80" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                <span>{streamingStatus}…</span>
              </div>
            )}
            {!streamingStatus && <p className="text-[11px] text-zinc-700 text-center mt-2">↵ to send · ⇧↵ new line</p>}
          </div>
        </footer>
      </div>

      {/* ── Live activity + artifact loading pane ── */}
      {showLoadingPanel && (
        <div className="flex-1 min-w-0 flex flex-col bg-zinc-950 border-l border-zinc-800">
          {/* Header */}
          <div className="shrink-0 flex items-center gap-2 px-4 py-2.5 border-b border-zinc-800 bg-zinc-900/60">
            <svg className="w-3 h-3 text-emerald-400 animate-spin shrink-0" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
              <path className="opacity-80" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <span className="text-xs text-zinc-400 font-medium">
              {completedTools.includes("emit_artifact")
                ? "Rendering artifact…"
                : activeTools.includes("emit_artifact")
                ? "Generating visual report…"
                : activeTools.length > 0
                ? "Querying knowledge graph…"
                : "Analyzing…"}
            </span>
          </div>

          <div className="flex-1 flex flex-col px-6 py-8 gap-6 overflow-y-auto">
            {/* Step counter */}
            {(activeTools.length > 0 || completedTools.length > 0) && (
              <p className="text-[11px] text-zinc-600">
                Step {completedTools.length} of ~{completedTools.length + activeTools.length + (activeTools.length > 0 ? 1 : 0)}
              </p>
            )}

            {/* Tool activity feed */}
            <div className="space-y-1">
              <p className="text-[11px] font-semibold uppercase tracking-widest text-zinc-600 mb-3">
                Intelligence gathering
              </p>

              {/* Completed tools — with preview + source labels */}
              {messages[messages.length - 1]?.toolCalls
                ?.filter(tc => tc.status === "done" && tc.name !== "emit_artifact")
                .map((tc) => (
                  <div key={tc.name} className="rounded-lg border border-emerald-900/30 bg-emerald-950/10 px-3 py-2">
                    <div className="flex items-center gap-2">
                      <div className="w-3.5 h-3.5 rounded-full bg-emerald-900/60 border border-emerald-700/40 flex items-center justify-center shrink-0">
                        <svg className="w-2 h-2 text-emerald-500" fill="none" viewBox="0 0 10 10">
                          <path stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" d="M2 5l2 2 4-4" />
                        </svg>
                      </div>
                      <span className="text-xs text-zinc-500 flex-1">{TOOL_LABELS[tc.name] ?? tc.name.replace(/_/g, " ")}</span>
                      {tc.completedAt && tc.startedAt && (
                        <span className="text-[10px] text-zinc-700">{((tc.completedAt - tc.startedAt) / 1000).toFixed(1)}s</span>
                      )}
                    </div>
                    {tc.preview && (
                      <p className="mt-1 ml-5.5 text-[11px] text-zinc-400 leading-snug">{tc.preview}</p>
                    )}
                    {tc.sourceLabels && tc.sourceLabels.length > 0 && (
                      <div className="mt-1.5 ml-5 flex flex-wrap gap-1">
                        {tc.sourceLabels.map((s) => (
                          <span key={s} className="px-1.5 py-px rounded text-[10px] bg-zinc-800/80 text-zinc-500 border border-zinc-700/40">
                            {s}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}

              {/* Active tools */}
              {activeTools.filter(t => t !== "emit_artifact").map((t) => (
                <div key={t} className="flex items-center gap-2.5 rounded-lg border border-zinc-700/40 bg-zinc-800/30 px-3 py-2 text-xs text-zinc-300">
                  <svg className="w-3.5 h-3.5 text-emerald-400 animate-spin shrink-0" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                    <path className="opacity-80" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  <span className="flex-1">{TOOL_LABELS[t] ?? t.replace(/_/g, " ")}</span>
                  <span className="text-zinc-600 text-[10px]">querying…</span>
                </div>
              ))}

              {/* Skeleton when nothing fired yet */}
              {activeTools.length === 0 && completedTools.length === 0 && (
                <div className="space-y-2 animate-pulse">
                  {[48, 64, 56, 40].map((w, i) => (
                    <div key={i} className="flex items-center gap-3">
                      <div className="w-3.5 h-3.5 rounded-full bg-zinc-800 shrink-0" />
                      <div className="h-2.5 bg-zinc-800 rounded" style={{ width: `${w}%` }} />
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Artifact generation phase */}
            {(activeTools.includes("emit_artifact") || completedTools.includes("emit_artifact")) && (
              <div className="space-y-3">
                <p className="text-[11px] font-semibold uppercase tracking-widest text-zinc-600 mb-3">
                  Building visual report
                </p>
                <div className="space-y-2.5 animate-pulse">
                  <div className="h-5 bg-zinc-800/70 rounded-lg w-2/3" />
                  <div className="h-32 bg-zinc-800/50 rounded-xl" />
                  <div className="grid grid-cols-3 gap-2">
                    {[0,1,2].map(i => <div key={i} className="h-12 bg-zinc-800/50 rounded-lg" />)}
                  </div>
                  <div className="h-16 bg-zinc-800/40 rounded-xl" />
                </div>
              </div>
            )}

            {/* Data sources consulted */}
            {completedTools.length > 0 && (
              <div className="mt-auto pt-4 border-t border-zinc-800/60">
                <p className="text-[10px] font-semibold uppercase tracking-widest text-zinc-700 mb-2">
                  Data sources consulted
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {Array.from(new Set(
                    (messages[messages.length - 1]?.toolCalls ?? [])
                      .flatMap(tc => tc.sourceLabels ?? [])
                  )).map((src) => (
                    <span key={src} className="px-2 py-0.5 rounded-full text-[10px] bg-zinc-800/60 text-zinc-500 border border-zinc-700/40">
                      {src}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Status hint */}
            {completedTools.length === 0 && activeTools.length === 0 && (
              <p className="text-[11px] text-zinc-700 mt-auto">Connecting to the knowledge graph…</p>
            )}
          </div>
        </div>
      )}

      {/* ── Artifact pane ── */}
      {showArtifactPanel && (
        <div className="flex-1 min-w-0">
          <ArtifactPanel
            artifacts={artifacts}
            activeId={activeArtifactId!}
            onSelectTab={setActiveArtifactId}
            onClose={() => setActiveArtifactId(null)}
          />
        </div>
      )}
    </div>
  );
}
