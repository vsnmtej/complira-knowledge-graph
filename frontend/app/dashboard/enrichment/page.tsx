"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  Zap,
  AlertCircle,
  Search,
  Loader2,
  ShieldCheck,
  ShieldAlert,
  FileWarning,
  Clock,
} from "lucide-react";
import {
  batchEnrich,
  enrichRegulatory,
  type CVEEnrichment,
  type BatchEnrichResponse,
  type RegulatoryEnrichResponse,
} from "@/lib/api/enrichment";

export default function EnrichmentPage() {
  const [activeTab, setActiveTab] = useState<"batch" | "regulatory">("batch");

  // Batch state
  const [batchInput, setBatchInput] = useState("");
  const [includeAttackPaths, setIncludeAttackPaths] = useState(false);
  const [includeCompliance, setIncludeCompliance] = useState(false);
  const [batchResult, setBatchResult] = useState<BatchEnrichResponse | null>(
    null
  );

  // Regulatory state
  const [regulatoryCveId, setRegulatoryCveId] = useState("");
  const [regulatoryResult, setRegulatoryResult] =
    useState<RegulatoryEnrichResponse | null>(null);

  // Batch mutation
  const batchMutation = useMutation({
    mutationFn: () => {
      const cveIds = batchInput
        .split(/[,\n]/)
        .map((s) => s.trim().toUpperCase())
        .filter(Boolean);
      return batchEnrich({
        cve_ids: cveIds,
        include_attack_paths: includeAttackPaths,
        include_compliance: includeCompliance,
      });
    },
    onSuccess: (data) => {
      setBatchResult(data);
    },
  });

  // Regulatory mutation
  const regulatoryMutation = useMutation({
    mutationFn: () => enrichRegulatory(regulatoryCveId.trim().toUpperCase()),
    onSuccess: (data) => {
      setRegulatoryResult(data);
    },
  });

  const cveCount = batchInput
    .split(/[,\n]/)
    .map((s) => s.trim())
    .filter(Boolean).length;

  const getPriorityColor = (priority: string) => {
    switch (priority?.toUpperCase()) {
      case "CRITICAL":
        return "bg-red-500/10 text-red-500";
      case "HIGH":
        return "bg-orange-500/10 text-orange-500";
      case "MEDIUM":
        return "bg-yellow-500/10 text-yellow-500";
      case "LOW":
        return "bg-blue-500/10 text-blue-500";
      default:
        return "bg-gray-500/10 text-gray-500";
    }
  };

  const getUrgencyColor = (urgency: string) => {
    switch (urgency?.toLowerCase()) {
      case "24h":
      case "immediate":
        return "bg-red-500/10 text-red-500";
      case "48h":
      case "72h":
        return "bg-orange-500/10 text-orange-500";
      case "7d":
      case "14d":
        return "bg-yellow-500/10 text-yellow-500";
      default:
        return "bg-blue-500/10 text-blue-500";
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">
          Vulnerability Enrichment
        </h1>
        <p className="text-muted-foreground mt-1">
          Enrich CVEs with risk scoring, attack intelligence, and regulatory
          trigger analysis
        </p>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-border">
        <button
          onClick={() => setActiveTab("batch")}
          className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            activeTab === "batch"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          Batch Enrich
        </button>
        <button
          onClick={() => setActiveTab("regulatory")}
          className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            activeTab === "regulatory"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          Regulatory Triggers
        </button>
      </div>

      {/* Tab 1: Batch Enrich */}
      {activeTab === "batch" && (
        <div className="space-y-6">
          {/* Input Card */}
          <div className="rounded-lg border border-border bg-card p-6 shadow-sm space-y-4">
            <div>
              <h3 className="text-lg font-semibold mb-1">
                Batch CVE Enrichment
              </h3>
              <p className="text-sm text-muted-foreground">
                Enter multiple CVE IDs to enrich with risk scoring and graph
                intelligence (max 100)
              </p>
            </div>

            <textarea
              value={batchInput}
              onChange={(e) => setBatchInput(e.target.value)}
              placeholder={"CVE-2024-21413, CVE-2023-44487\nCVE-2021-44228"}
              rows={5}
              className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm font-mono resize-none"
            />

            <div className="flex items-center gap-6">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={includeAttackPaths}
                  onChange={(e) => setIncludeAttackPaths(e.target.checked)}
                  className="rounded border-border"
                />
                <span className="text-muted-foreground">
                  Include attack paths
                </span>
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={includeCompliance}
                  onChange={(e) => setIncludeCompliance(e.target.checked)}
                  className="rounded border-border"
                />
                <span className="text-muted-foreground">
                  Include compliance mapping
                </span>
              </label>
            </div>

            <div className="flex items-center gap-3">
              <button
                onClick={() => batchMutation.mutate()}
                disabled={cveCount === 0 || batchMutation.isPending}
                className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {batchMutation.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Enriching...
                  </>
                ) : (
                  <>
                    <Zap className="h-4 w-4" />
                    Enrich
                  </>
                )}
              </button>
              <span className="text-xs text-muted-foreground">
                {cveCount} CVE{cveCount !== 1 ? "s" : ""}
              </span>
            </div>
          </div>

          {/* Batch Error */}
          {batchMutation.isError && (
            <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4">
              <div className="flex items-center gap-2 text-destructive">
                <AlertCircle className="h-5 w-5" />
                <p className="font-medium">Enrichment failed</p>
              </div>
              <p className="text-sm text-muted-foreground mt-1">
                {(batchMutation.error as Error).message}
              </p>
            </div>
          )}

          {/* Batch Results */}
          {batchResult && batchResult.enriched.length > 0 && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold">
                  Results ({batchResult.total} CVEs)
                </h3>
                <div className="flex items-center gap-1 text-sm text-muted-foreground">
                  <Clock className="h-4 w-4" />
                  {batchResult.processing_time_ms.toFixed(0)}ms
                </div>
              </div>

              <div className="rounded-lg border border-border bg-card overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="bg-muted/50 border-b border-border">
                      <tr>
                        <th className="px-4 py-3 text-left text-sm font-medium">
                          CVE
                        </th>
                        <th className="px-4 py-3 text-left text-sm font-medium">
                          CVSS
                        </th>
                        <th className="px-4 py-3 text-left text-sm font-medium">
                          EPSS
                        </th>
                        <th className="px-4 py-3 text-left text-sm font-medium">
                          KEV
                        </th>
                        <th className="px-4 py-3 text-left text-sm font-medium">
                          Risk Score
                        </th>
                        <th className="px-4 py-3 text-left text-sm font-medium">
                          Priority
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {batchResult.enriched.map((item: CVEEnrichment) => (
                        <tr
                          key={item.cve_id}
                          className="hover:bg-muted/30 transition-colors"
                        >
                          <td className="px-4 py-3">
                            <span className="text-sm font-mono font-medium text-primary">
                              {item.cve_id}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-sm">
                            {item.cvss_score != null
                              ? item.cvss_score.toFixed(1)
                              : "--"}
                          </td>
                          <td className="px-4 py-3 text-sm">
                            {item.epss_score != null
                              ? `${(item.epss_score * 100).toFixed(2)}%`
                              : "--"}
                          </td>
                          <td className="px-4 py-3">
                            {item.in_kev ? (
                              <span className="text-xs px-2 py-0.5 rounded bg-red-500/10 text-red-500 font-medium">
                                Yes
                              </span>
                            ) : (
                              <span className="text-xs text-muted-foreground">
                                No
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              <div className="w-16 h-2 rounded-full bg-muted overflow-hidden">
                                <div
                                  className={`h-full rounded-full ${
                                    item.risk_score >= 0.8
                                      ? "bg-red-500"
                                      : item.risk_score >= 0.6
                                        ? "bg-orange-500"
                                        : item.risk_score >= 0.4
                                          ? "bg-yellow-500"
                                          : "bg-blue-500"
                                  }`}
                                  style={{
                                    width: `${item.risk_score * 100}%`,
                                  }}
                                />
                              </div>
                              <span className="text-sm">
                                {(item.risk_score * 100).toFixed(0)}
                              </span>
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            <span
                              className={`text-xs px-2 py-0.5 rounded font-medium ${getPriorityColor(item.priority)}`}
                            >
                              {item.priority}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* Batch Empty Result */}
          {batchResult && batchResult.enriched.length === 0 && (
            <div className="rounded-lg border border-border bg-card p-12 text-center">
              <Search className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-semibold mb-2">
                No results found
              </h3>
              <p className="text-muted-foreground">
                The provided CVE IDs were not found in the knowledge graph.
              </p>
            </div>
          )}

          {/* Initial Empty State */}
          {!batchResult && !batchMutation.isPending && !batchMutation.isError && (
            <div className="rounded-lg border border-border bg-card p-12 text-center">
              <Zap className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-semibold mb-2">
                Enrich Vulnerabilities
              </h3>
              <p className="text-muted-foreground max-w-md mx-auto">
                Enter CVE IDs above to get risk scores, EPSS probabilities, KEV
                status, and priority ratings powered by the knowledge graph.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Tab 2: Regulatory Triggers */}
      {activeTab === "regulatory" && (
        <div className="space-y-6">
          {/* Input Card */}
          <div className="rounded-lg border border-border bg-card p-6 shadow-sm space-y-4">
            <div>
              <h3 className="text-lg font-semibold mb-1">
                Regulatory Trigger Analysis
              </h3>
              <p className="text-sm text-muted-foreground">
                Analyze a CVE for regulatory compliance triggers across
                frameworks (FDA 524B, ISO 27001, EU CRA)
              </p>
            </div>

            <div className="flex items-center gap-3">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
                <input
                  type="text"
                  value={regulatoryCveId}
                  onChange={(e) => setRegulatoryCveId(e.target.value)}
                  onKeyDown={(e) => {
                    if (
                      e.key === "Enter" &&
                      regulatoryCveId.trim() &&
                      !regulatoryMutation.isPending
                    ) {
                      regulatoryMutation.mutate();
                    }
                  }}
                  placeholder="Enter CVE ID (e.g., CVE-2021-44228)"
                  className="w-full pl-10 pr-4 py-3 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                />
              </div>
              <button
                onClick={() => regulatoryMutation.mutate()}
                disabled={
                  !regulatoryCveId.trim() || regulatoryMutation.isPending
                }
                className="inline-flex items-center gap-2 px-6 py-3 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {regulatoryMutation.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Analyzing...
                  </>
                ) : (
                  <>
                    <FileWarning className="h-4 w-4" />
                    Analyze
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Regulatory Error */}
          {regulatoryMutation.isError && (
            <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4">
              <div className="flex items-center gap-2 text-destructive">
                <AlertCircle className="h-5 w-5" />
                <p className="font-medium">Regulatory analysis failed</p>
              </div>
              <p className="text-sm text-muted-foreground mt-1">
                {(regulatoryMutation.error as Error).message}
              </p>
            </div>
          )}

          {/* Regulatory Results */}
          {regulatoryResult && (
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">
                Results for{" "}
                <span className="font-mono text-primary">
                  {regulatoryResult.cve_id}
                </span>
              </h3>

              {/* NVD Data Card */}
              {regulatoryResult.nvd_data && (
                <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
                  <div className="flex items-center gap-2 mb-4">
                    <ShieldCheck className="h-5 w-5 text-blue-500" />
                    <h4 className="text-lg font-semibold">NVD Data</h4>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="p-4 rounded-lg bg-muted/50">
                      <p className="text-xs text-muted-foreground mb-1">
                        Published
                      </p>
                      <p className="text-sm font-medium">
                        {regulatoryResult.nvd_data.published
                          ? String(regulatoryResult.nvd_data.published)
                          : "N/A"}
                      </p>
                    </div>
                    <div className="p-4 rounded-lg bg-muted/50">
                      <p className="text-xs text-muted-foreground mb-1">
                        CVSS v3.1
                      </p>
                      <p className="text-xl font-bold">
                        {(regulatoryResult.nvd_data.cvss_v31 as any)
                          ?.baseScore ?? "N/A"}
                      </p>
                    </div>
                    <div className="p-4 rounded-lg bg-muted/50">
                      <p className="text-xs text-muted-foreground mb-1">
                        Last Modified
                      </p>
                      <p className="text-sm font-medium">
                        {regulatoryResult.nvd_data.last_modified
                          ? String(regulatoryResult.nvd_data.last_modified)
                          : "N/A"}
                      </p>
                    </div>
                  </div>
                  {regulatoryResult.nvd_data.description != null && (
                    <p className="text-sm text-muted-foreground mt-4">
                      {String(regulatoryResult.nvd_data.description)}
                    </p>
                  )}
                </div>
              )}

              {/* Exploit Intelligence Card */}
              {regulatoryResult.exploit_intelligence && (
                <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
                  <div className="flex items-center gap-2 mb-4">
                    <ShieldAlert className="h-5 w-5 text-red-500" />
                    <h4 className="text-lg font-semibold">
                      Exploit Intelligence
                    </h4>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="p-4 rounded-lg bg-muted/50">
                      <p className="text-xs text-muted-foreground mb-1">
                        KEV Status
                      </p>
                      <p className="text-sm font-bold">
                        {regulatoryResult.exploit_intelligence.in_kev ? (
                          <span className="text-red-500">In Catalog</span>
                        ) : (
                          "Not in KEV"
                        )}
                      </p>
                    </div>
                    <div className="p-4 rounded-lg bg-muted/50">
                      <p className="text-xs text-muted-foreground mb-1">
                        Exploit Maturity
                      </p>
                      <p className="text-sm font-bold">
                        {String(
                          regulatoryResult.exploit_intelligence
                            .exploit_maturity ?? "Unknown"
                        )}
                      </p>
                    </div>
                    <div className="p-4 rounded-lg bg-muted/50">
                      <p className="text-xs text-muted-foreground mb-1">
                        Ransomware
                      </p>
                      <p className="text-sm font-bold">
                        {(
                          regulatoryResult.exploit_intelligence
                            .ransomware_families as any[]
                        )?.length ?? 0}{" "}
                        families
                      </p>
                    </div>
                    <div className="p-4 rounded-lg bg-muted/50">
                      <p className="text-xs text-muted-foreground mb-1">
                        Exploit Chains
                      </p>
                      <p className="text-sm font-bold">
                        {(
                          regulatoryResult.exploit_intelligence
                            .exploit_chains as any[]
                        )?.length ?? 0}{" "}
                        chains
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Regulatory Triggers Card */}
              <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
                <div className="flex items-center gap-2 mb-4">
                  <FileWarning className="h-5 w-5 text-yellow-500" />
                  <h4 className="text-lg font-semibold">
                    Regulatory Triggers (
                    {regulatoryResult.regulatory_triggers.length})
                  </h4>
                </div>

                {regulatoryResult.regulatory_triggers.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No regulatory triggers found for this CVE.
                  </p>
                ) : (
                  <div className="space-y-3">
                    {regulatoryResult.regulatory_triggers.map(
                      (trigger, idx) => (
                        <div
                          key={idx}
                          className="p-4 rounded-lg bg-muted/30 border border-border"
                        >
                          <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-semibold">
                                {trigger.framework}
                              </span>
                              <span className="text-xs px-2 py-0.5 rounded bg-primary/10 text-primary font-mono">
                                {trigger.requirement_id}
                              </span>
                            </div>
                            <span
                              className={`text-xs px-2 py-0.5 rounded font-medium ${getUrgencyColor(trigger.urgency)}`}
                            >
                              {trigger.urgency}
                            </span>
                          </div>
                          <p className="text-sm font-medium">
                            {trigger.requirement_title}
                          </p>
                          <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                            <span>Rule: {trigger.trigger_rule}</span>
                            <span>
                              Confidence:{" "}
                              {(trigger.confidence * 100).toFixed(0)}%
                            </span>
                          </div>
                        </div>
                      )
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Regulatory Initial Empty State */}
          {!regulatoryResult &&
            !regulatoryMutation.isPending &&
            !regulatoryMutation.isError && (
              <div className="rounded-lg border border-border bg-card p-12 text-center">
                <FileWarning className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                <h3 className="text-lg font-semibold mb-2">
                  Regulatory Trigger Analysis
                </h3>
                <p className="text-muted-foreground max-w-md mx-auto">
                  Enter a CVE ID to analyze which regulatory frameworks and
                  requirements are triggered, including urgency levels and
                  compliance evidence.
                </p>
              </div>
            )}
        </div>
      )}
    </div>
  );
}
