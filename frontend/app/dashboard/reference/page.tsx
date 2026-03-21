"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BookOpen,
  Search,
  AlertCircle,
  Shield,
  ShieldAlert,
  Bug,
  Swords,
  Lock,
  Plus,
  X,
  Loader2,
} from "lucide-react";
import {
  getCVEDetails,
  getCWEDetails,
  batchEnrichCVEs,
  type CVEDetail,
  type CWEDetail,
} from "@/lib/api/reference";
import Link from "next/link";

export default function ReferencePage() {
  const [searchInput, setSearchInput] = useState("");
  const [searchId, setSearchId] = useState("");
  const [searchType, setSearchType] = useState<"cve" | "cwe" | null>(null);

  const [batchInput, setBatchInput] = useState("");
  const [batchIds, setBatchIds] = useState<string[]>([]);
  const [showBatch, setShowBatch] = useState(false);

  // Single CVE lookup
  const {
    data: cveData,
    isLoading: cveLoading,
    error: cveError,
  } = useQuery({
    queryKey: ["cve-detail", searchId],
    queryFn: () => getCVEDetails(searchId),
    enabled: searchType === "cve" && !!searchId,
  });

  // Single CWE lookup
  const {
    data: cweData,
    isLoading: cweLoading,
    error: cweError,
  } = useQuery({
    queryKey: ["cwe-detail", searchId],
    queryFn: () => getCWEDetails(searchId),
    enabled: searchType === "cwe" && !!searchId,
  });

  // Batch enrich
  const {
    data: batchData,
    isLoading: batchLoading,
    error: batchError,
  } = useQuery({
    queryKey: ["batch-enrich", batchIds],
    queryFn: () => batchEnrichCVEs(batchIds),
    enabled: batchIds.length > 0,
  });

  const cve = cveData?.data;
  const cwe = cweData?.data;
  const batchResults = batchData?.data || [];

  const handleSearch = () => {
    const input = searchInput.trim().toUpperCase();
    if (!input) return;

    if (input.startsWith("CVE-")) {
      setSearchType("cve");
      setSearchId(input);
    } else if (input.startsWith("CWE-")) {
      setSearchType("cwe");
      setSearchId(input);
    } else if (/^\d+$/.test(input)) {
      // If just a number, assume CWE
      setSearchType("cwe");
      setSearchId(`CWE-${input}`);
    } else {
      // Default to CVE
      setSearchType("cve");
      setSearchId(input);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSearch();
  };

  const handleBatchEnrich = () => {
    const ids = batchInput
      .split(/[,\n]/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (ids.length > 0) {
      setBatchIds(ids);
    }
  };

  const isLoading = cveLoading || cweLoading;
  const error = cveError || cweError;

  const getSeverityColor = (severity: string | null) => {
    switch (severity?.toUpperCase()) {
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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            Reference Lookup
          </h1>
          <p className="text-muted-foreground mt-1">
            Query CVE and CWE details with threat intelligence enrichment
          </p>
        </div>
        <button
          onClick={() => setShowBatch(!showBatch)}
          className="inline-flex items-center gap-2 px-4 py-2 text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg transition-colors font-medium"
        >
          {showBatch ? (
            <X className="h-4 w-4" />
          ) : (
            <Plus className="h-4 w-4" />
          )}
          {showBatch ? "Close Batch" : "Batch Enrich"}
        </button>
      </div>

      {/* Search Bar */}
      <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Enter CVE-YYYY-NNNN or CWE-NNN..."
              className="w-full pl-10 pr-4 py-3 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
            />
          </div>
          <button
            onClick={handleSearch}
            disabled={!searchInput.trim()}
            className="inline-flex items-center gap-2 px-6 py-3 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Search className="h-4 w-4" />
            Search
          </button>
        </div>
        <p className="text-xs text-muted-foreground mt-2">
          Examples: CVE-2024-1234, CWE-89, CWE-79
        </p>
      </div>

      {/* Batch Enrich Section */}
      {showBatch && (
        <div className="rounded-lg border border-border bg-card p-6 shadow-sm space-y-4">
          <div>
            <h3 className="text-lg font-semibold mb-1">Batch CVE Enrichment</h3>
            <p className="text-sm text-muted-foreground">
              Enter multiple CVE IDs (comma or newline separated, max 100)
            </p>
          </div>
          <textarea
            value={batchInput}
            onChange={(e) => setBatchInput(e.target.value)}
            placeholder="CVE-2024-1234, CVE-2024-5678&#10;CVE-2023-9999"
            rows={4}
            className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm font-mono resize-none"
          />
          <div className="flex items-center gap-3">
            <button
              onClick={handleBatchEnrich}
              disabled={!batchInput.trim() || batchLoading}
              className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {batchLoading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Enriching...
                </>
              ) : (
                "Enrich CVEs"
              )}
            </button>
            <span className="text-xs text-muted-foreground">
              {batchInput
                .split(/[,\n]/)
                .map((s) => s.trim())
                .filter(Boolean).length}{" "}
              CVEs
            </span>
          </div>

          {batchError && (
            <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4">
              <div className="flex items-center gap-2 text-destructive">
                <AlertCircle className="h-5 w-5" />
                <p className="font-medium">Batch enrichment failed</p>
              </div>
              <p className="text-sm text-muted-foreground mt-1">
                {(batchError as Error).message}
              </p>
            </div>
          )}

          {batchResults.length > 0 && (
            <div className="space-y-3">
              <h4 className="text-sm font-medium">
                Results ({batchResults.length} CVEs)
              </h4>
              <div className="rounded-lg border border-border bg-card overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="bg-muted/50 border-b border-border">
                      <tr>
                        <th className="px-4 py-2 text-left text-xs font-medium">
                          CVE ID
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium">
                          Severity
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium">
                          CVSS
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium">
                          EPSS
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium">
                          KEV
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium">
                          CWEs
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium">
                          Controls
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {batchResults.map((item: CVEDetail, idx: number) => (
                        <tr
                          key={idx}
                          className="hover:bg-muted/30 transition-colors"
                        >
                          <td className="px-4 py-2">
                            {item.error ? (
                              <span className="text-sm text-muted-foreground">
                                {item.cve_id}
                              </span>
                            ) : (
                              <button
                                onClick={() => {
                                  setSearchInput(item.cve_id);
                                  setSearchType("cve");
                                  setSearchId(item.cve_id);
                                }}
                                className="text-sm text-primary hover:underline font-mono"
                              >
                                {item.cve_id}
                              </button>
                            )}
                          </td>
                          <td className="px-4 py-2">
                            {item.error ? (
                              <span className="text-xs text-destructive">
                                Not found
                              </span>
                            ) : (
                              <span
                                className={`text-xs px-2 py-0.5 rounded ${getSeverityColor(item.severity)}`}
                              >
                                {item.severity || "N/A"}
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-2 text-sm">
                            {item.cvss_score ?? "--"}
                          </td>
                          <td className="px-4 py-2 text-sm">
                            {item.epss
                              ? `${(item.epss.score * 100).toFixed(2)}%`
                              : "--"}
                          </td>
                          <td className="px-4 py-2">
                            {item.kev?.in_kev ? (
                              <span className="text-xs px-2 py-0.5 rounded bg-red-500/10 text-red-500">
                                Yes
                              </span>
                            ) : (
                              <span className="text-xs text-muted-foreground">
                                No
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-2 text-sm">
                            {item.weaknesses?.length ?? 0}
                          </td>
                          <td className="px-4 py-2 text-sm">
                            {item.nist_controls?.length ?? 0}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Loading State */}
      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4">
          <div className="flex items-center gap-2 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <p className="font-medium">Lookup failed</p>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            {(error as Error).message}
          </p>
        </div>
      )}

      {/* CVE Detail Result */}
      {!isLoading && !error && cve && searchType === "cve" && (
        <div className="space-y-4">
          {/* CVE Header Card */}
          <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
            <div className="flex items-start justify-between">
              <div>
                <h2 className="text-2xl font-bold font-mono">{cve.cve_id}</h2>
                <p className="text-muted-foreground mt-2 max-w-3xl">
                  {cve.description}
                </p>
              </div>
              <div className="flex items-center gap-3">
                {cve.severity && (
                  <span
                    className={`text-sm px-3 py-1.5 rounded font-medium ${getSeverityColor(cve.severity)}`}
                  >
                    {cve.severity}
                  </span>
                )}
                {cve.kev?.in_kev && (
                  <span className="text-xs px-2 py-1 rounded bg-red-500/10 text-red-500 font-medium">
                    CISA KEV
                  </span>
                )}
              </div>
            </div>

            {/* Score Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
              <div className="p-4 rounded-lg bg-muted/50">
                <p className="text-xs text-muted-foreground mb-1">CVSS Score</p>
                <p className="text-xl font-bold">
                  {cve.cvss_score ?? "N/A"}
                </p>
              </div>
              <div className="p-4 rounded-lg bg-muted/50">
                <p className="text-xs text-muted-foreground mb-1">
                  EPSS Probability
                </p>
                <p className="text-xl font-bold">
                  {cve.epss
                    ? `${(cve.epss.score * 100).toFixed(2)}%`
                    : "N/A"}
                </p>
              </div>
              <div className="p-4 rounded-lg bg-muted/50">
                <p className="text-xs text-muted-foreground mb-1">
                  EPSS Percentile
                </p>
                <p className="text-xl font-bold">
                  {cve.epss
                    ? `${(cve.epss.percentile * 100).toFixed(1)}%`
                    : "N/A"}
                </p>
              </div>
              <div className="p-4 rounded-lg bg-muted/50">
                <p className="text-xs text-muted-foreground mb-1">KEV Status</p>
                <p className="text-xl font-bold">
                  {cve.kev?.in_kev ? "In Catalog" : "Not in KEV"}
                </p>
              </div>
            </div>
          </div>

          {/* CWE Weaknesses */}
          {cve.weaknesses.length > 0 && (
            <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
              <div className="flex items-center gap-2 mb-4">
                <Bug className="h-5 w-5 text-orange-500" />
                <h3 className="text-lg font-semibold">
                  CWE Weaknesses ({cve.weaknesses.length})
                </h3>
              </div>
              <div className="space-y-2">
                {cve.weaknesses.map((w) => (
                  <div
                    key={w.cwe_id}
                    className="p-3 rounded-lg bg-muted/30 border border-border"
                  >
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => {
                          setSearchInput(w.cwe_id);
                          setSearchType("cwe");
                          setSearchId(w.cwe_id);
                        }}
                        className="font-mono text-sm text-primary hover:underline font-medium"
                      >
                        {w.cwe_id}
                      </button>
                      <span className="text-sm font-medium">{w.name}</span>
                    </div>
                    {w.description && (
                      <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                        {w.description}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ATT&CK Techniques */}
          {cve.attack_techniques.length > 0 && (
            <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
              <div className="flex items-center gap-2 mb-4">
                <Swords className="h-5 w-5 text-red-500" />
                <h3 className="text-lg font-semibold">
                  MITRE ATT&CK Techniques ({cve.attack_techniques.length})
                </h3>
              </div>
              <div className="space-y-2">
                {cve.attack_techniques.map((t) => (
                  <div
                    key={t.technique_id}
                    className="p-3 rounded-lg bg-muted/30 border border-border"
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm text-primary font-medium">
                        {t.technique_id}
                      </span>
                      <span className="text-sm font-medium">{t.name}</span>
                    </div>
                    {t.tactics && t.tactics.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1">
                        {t.tactics.map((tactic) => (
                          <span
                            key={tactic}
                            className="text-xs px-2 py-0.5 rounded bg-red-500/10 text-red-500"
                          >
                            {tactic}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* NIST Controls */}
          {cve.nist_controls.length > 0 && (
            <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
              <div className="flex items-center gap-2 mb-4">
                <Lock className="h-5 w-5 text-blue-500" />
                <h3 className="text-lg font-semibold">
                  NIST 800-53 Controls ({cve.nist_controls.length})
                </h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-muted/50 border-b border-border">
                    <tr>
                      <th className="px-4 py-2 text-left text-xs font-medium">
                        Control ID
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium">
                        Title
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium">
                        Family
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {cve.nist_controls.map((c) => (
                      <tr key={c.control_id}>
                        <td className="px-4 py-2 font-mono text-sm text-primary">
                          {c.control_id}
                        </td>
                        <td className="px-4 py-2 text-sm">{c.title}</td>
                        <td className="px-4 py-2 text-sm text-muted-foreground">
                          {c.family}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* D3FEND Defenses */}
          {cve.d3fend_defenses.length > 0 && (
            <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
              <div className="flex items-center gap-2 mb-4">
                <Shield className="h-5 w-5 text-green-500" />
                <h3 className="text-lg font-semibold">
                  D3FEND Countermeasures ({cve.d3fend_defenses.length})
                </h3>
              </div>
              <div className="space-y-2">
                {cve.d3fend_defenses.map((d) => (
                  <div
                    key={d.technique_id}
                    className="p-3 rounded-lg bg-muted/30 border border-border"
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm text-green-600 font-medium">
                        {d.technique_id}
                      </span>
                      <span className="text-sm font-medium">{d.name}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Exploits */}
          {cve.exploits.length > 0 && (
            <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
              <div className="flex items-center gap-2 mb-4">
                <ShieldAlert className="h-5 w-5 text-red-500" />
                <h3 className="text-lg font-semibold">
                  Known Exploits ({cve.exploits.length})
                </h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-muted/50 border-b border-border">
                    <tr>
                      <th className="px-4 py-2 text-left text-xs font-medium">
                        ID
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium">
                        Name
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium">
                        Type
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium">
                        Platform
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {cve.exploits.map((ex) => (
                      <tr key={ex.exploit_id}>
                        <td className="px-4 py-2 font-mono text-sm">
                          {ex.exploit_id}
                        </td>
                        <td className="px-4 py-2 text-sm">{ex.name}</td>
                        <td className="px-4 py-2 text-sm text-muted-foreground">
                          {ex.type}
                        </td>
                        <td className="px-4 py-2 text-sm text-muted-foreground">
                          {ex.platform}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Empty Enrichment Summary */}
          {cve.weaknesses.length === 0 &&
            cve.attack_techniques.length === 0 &&
            cve.nist_controls.length === 0 && (
              <div className="rounded-lg border border-border bg-card p-8 text-center">
                <BookOpen className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
                <h3 className="text-lg font-semibold mb-1">
                  No enrichment data available
                </h3>
                <p className="text-muted-foreground">
                  This CVE does not have mapped CWE weaknesses, ATT&CK
                  techniques, or NIST controls in the knowledge graph.
                </p>
              </div>
            )}
        </div>
      )}

      {/* CWE Detail Result */}
      {!isLoading && !error && cwe && searchType === "cwe" && (
        <div className="space-y-4">
          <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
            <h2 className="text-2xl font-bold">
              <span className="font-mono text-primary">{cwe.cwe_id}</span>{" "}
              {cwe.name}
            </h2>
            <p className="text-muted-foreground mt-2">{cwe.description}</p>
            {cwe.extended_description && (
              <p className="text-sm text-muted-foreground mt-2">
                {cwe.extended_description}
              </p>
            )}
          </div>

          {/* Hierarchy */}
          {(cwe.parents.length > 0 || cwe.children.length > 0) && (
            <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
              <h3 className="text-lg font-semibold mb-4">CWE Hierarchy</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {cwe.parents.length > 0 && (
                  <div>
                    <p className="text-sm font-medium text-muted-foreground mb-2">
                      Parent Weaknesses
                    </p>
                    <div className="space-y-1">
                      {cwe.parents.map((p) => (
                        <button
                          key={p.cwe_id}
                          onClick={() => {
                            setSearchInput(p.cwe_id);
                            setSearchType("cwe");
                            setSearchId(p.cwe_id);
                          }}
                          className="block text-sm text-primary hover:underline"
                        >
                          {p.cwe_id}: {p.name}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {cwe.children.length > 0 && (
                  <div>
                    <p className="text-sm font-medium text-muted-foreground mb-2">
                      Child Weaknesses
                    </p>
                    <div className="space-y-1">
                      {cwe.children.map((c) => (
                        <button
                          key={c.cwe_id}
                          onClick={() => {
                            setSearchInput(c.cwe_id);
                            setSearchType("cwe");
                            setSearchId(c.cwe_id);
                          }}
                          className="block text-sm text-primary hover:underline"
                        >
                          {c.cwe_id}: {c.name}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Attack Patterns */}
          {cwe.attack_patterns.length > 0 && (
            <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
              <div className="flex items-center gap-2 mb-4">
                <Swords className="h-5 w-5 text-red-500" />
                <h3 className="text-lg font-semibold">
                  CAPEC Attack Patterns ({cwe.attack_patterns.length})
                </h3>
              </div>
              <div className="space-y-2">
                {cwe.attack_patterns.map((ap) => (
                  <div
                    key={ap.capec_id}
                    className="p-3 rounded-lg bg-muted/30 border border-border"
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm text-primary font-medium">
                        {ap.capec_id}
                      </span>
                      <span className="text-sm font-medium">{ap.name}</span>
                    </div>
                    {ap.description && (
                      <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                        {ap.description}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Initial Empty State */}
      {!isLoading && !error && !cve && !cwe && searchType === null && (
        <div className="rounded-lg border border-border bg-card p-12 text-center">
          <BookOpen className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <h3 className="text-lg font-semibold mb-2">
            Search the Knowledge Graph
          </h3>
          <p className="text-muted-foreground mb-2 max-w-md mx-auto">
            Look up any CVE or CWE to see enrichment data including CVSS, EPSS
            scores, KEV status, ATT&CK techniques, and NIST controls.
          </p>
        </div>
      )}
    </div>
  );
}
