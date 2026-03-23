"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { format } from "date-fns";
import {
  ArrowLeft,
  FileSearch,
  AlertCircle,
  CheckCircle2,
  Clock,
  XCircle,
  Download,
  Shield,
  Package,
} from "lucide-react";
import {
  getScanSession,
  getScanFindings,
  generateVEX,
  matchCPEs,
  type ScanSession,
  type ScanFinding,
} from "@/lib/api/scans";

export default function ScanDetailsPage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const sessionId = params.sessionId as string;

  const [severityFilter, setSeverityFilter] = useState<string>("all");

  // Fetch scan session details
  const {
    data: sessionData,
    isLoading: sessionLoading,
    error: sessionError,
  } = useQuery({
    queryKey: ["scan", sessionId],
    queryFn: () => getScanSession(sessionId),
    enabled: !!sessionId,
  });

  const session = sessionData?.data;

  // Fetch findings
  const {
    data: findingsData,
    isLoading: findingsLoading,
    error: findingsError,
  } = useQuery({
    queryKey: ["scan-findings", sessionId, severityFilter],
    queryFn: () =>
      getScanFindings({
        sessionId,
        severity: severityFilter !== "all" ? severityFilter : undefined,
      }),
    enabled: !!sessionId,
  });

  const findings = findingsData?.data || [];

  // Generate VEX mutation
  const [vexError, setVexError] = useState<string | null>(null);
  const vexMutation = useMutation({
    mutationFn: () => generateVEX(sessionId),
    onSuccess: (data) => {
      setVexError(null);
      // Download VEX document
      const vexJson = JSON.stringify(data.data.vex_document, null, 2);
      const blob = new Blob([vexJson], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `vex-${sessionId}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    },
    onError: (error: any) => {
      const msg = error?.data?.detail || error?.message || "VEX generation failed";
      if (msg.includes("not found") || msg.includes("customer") || msg.includes("Anthropic")) {
        setVexError("VEX auto-generation requires a provisioned tenant database and LLM API key. Use manual VEX creation instead.");
      } else {
        setVexError(msg);
      }
    },
  });

  // CPE Match mutation
  const cpeMutation = useMutation({
    mutationFn: () => matchCPEs(sessionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scan", sessionId] });
    },
  });

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "completed":
        return <CheckCircle2 className="h-5 w-5 text-green-500" />;
      case "processing":
        return <Clock className="h-5 w-5 text-blue-500" />;
      case "failed":
        return <XCircle className="h-5 w-5 text-red-500" />;
      default:
        return <Clock className="h-5 w-5 text-gray-500" />;
    }
  };

  const getSeverityColor = (severity: string) => {
    switch (severity?.toUpperCase()) {
      case "CRITICAL":
        return "text-red-600 bg-red-100 border-red-200";
      case "HIGH":
        return "text-orange-600 bg-orange-100 border-orange-200";
      case "MEDIUM":
        return "text-yellow-600 bg-yellow-100 border-yellow-200";
      case "LOW":
        return "text-blue-600 bg-blue-100 border-blue-200";
      case "INFO":
        return "text-gray-600 bg-gray-100 border-gray-200";
      default:
        return "text-gray-600 bg-gray-100 border-gray-200";
    }
  };

  const getSeverityStats = () => {
    const stats = {
      CRITICAL: 0,
      HIGH: 0,
      MEDIUM: 0,
      LOW: 0,
      INFO: 0,
    };

    findings.forEach((finding) => {
      const severity = finding.severity?.toUpperCase();
      if (severity && severity in stats) {
        stats[severity as keyof typeof stats]++;
      }
    });

    return stats;
  };

  if (sessionLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    );
  }

  if (sessionError || !session) {
    return (
      <div className="space-y-6">
        <Link
          href="/dashboard/scans"
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Scans
        </Link>

        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4">
          <div className="flex items-center gap-2 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <p className="font-medium">Failed to load scan</p>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            {(sessionError as Error)?.message || "Scan not found"}
          </p>
        </div>
      </div>
    );
  }

  const severityStats = getSeverityStats();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <Link
          href="/dashboard/scans"
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-4"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Scans
        </Link>

        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-3xl font-bold tracking-tight">Scan Details</h1>
              <div className="flex items-center gap-2">
                {getStatusIcon(session.status)}
                <span className="text-sm capitalize">{session.status}</span>
              </div>
            </div>
            <p className="text-muted-foreground">
              Session ID: <span className="font-mono">{session.session_id}</span>
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => cpeMutation.mutate()}
              disabled={cpeMutation.isPending}
              className="inline-flex items-center gap-2 px-4 py-2 border border-border rounded-lg hover:bg-accent transition-colors text-sm font-medium disabled:opacity-50"
            >
              {cpeMutation.isPending ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-primary"></div>
                  Matching CPEs...
                </>
              ) : (
                <>
                  <Package className="h-4 w-4" />
                  Match CPEs
                </>
              )}
            </button>

            <button
              onClick={() => vexMutation.mutate()}
              disabled={vexMutation.isPending}
              className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors text-sm font-medium disabled:opacity-50"
            >
              {vexMutation.isPending ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-primary-foreground"></div>
                  Generating...
                </>
              ) : (
                <>
                  <Download className="h-4 w-4" />
                  Generate VEX
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* VEX/CPE Error Messages */}
      {vexError && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-destructive">
              <AlertCircle className="h-5 w-5" />
              <p className="font-medium text-sm">{vexError}</p>
            </div>
            <Link
              href="/dashboard/vex/new"
              className="inline-flex items-center gap-1 px-3 py-1.5 text-xs bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
            >
              <Shield className="h-3 w-3" />
              Create VEX Manually
            </Link>
          </div>
        </div>
      )}

      {cpeMutation.isError && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4">
          <div className="flex items-center gap-2 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <p className="font-medium text-sm">
              CPE matching failed: {(cpeMutation.error as any)?.message || "Unknown error"}
            </p>
          </div>
        </div>
      )}

      {/* Scan Info Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-2">
            <FileSearch className="h-4 w-4" />
            <span className="text-sm font-medium">Tool</span>
          </div>
          <div>
            <p className="text-lg font-semibold">{session.tool_name}</p>
            <p className="text-xs text-muted-foreground">v{session.tool_version}</p>
          </div>
        </div>

        <div className="rounded-lg border border-border bg-card p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-2">
            <Shield className="h-4 w-4" />
            <span className="text-sm font-medium">Scan Type</span>
          </div>
          <p className="text-lg font-semibold uppercase">{session.scan_type}</p>
        </div>

        <div className="rounded-lg border border-border bg-card p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-2">
            <AlertCircle className="h-4 w-4" />
            <span className="text-sm font-medium">Findings</span>
          </div>
          <p className="text-lg font-semibold">{session.findings_count}</p>
        </div>

        <div className="rounded-lg border border-border bg-card p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-2">
            <Package className="h-4 w-4" />
            <span className="text-sm font-medium">Components</span>
          </div>
          <p className="text-lg font-semibold">{session.components_count}</p>
        </div>
      </div>

      {/* Severity Distribution */}
      <div className="rounded-lg border border-border bg-card p-6">
        <h2 className="text-lg font-semibold mb-4">Severity Distribution</h2>
        <div className="grid grid-cols-5 gap-4">
          {(Object.entries(severityStats) as [keyof typeof severityStats, number][]).map(
            ([severity, count]) => (
              <div
                key={severity}
                className={`rounded-lg border p-4 text-center ${getSeverityColor(severity)}`}
              >
                <p className="text-2xl font-bold">{count}</p>
                <p className="text-sm font-medium mt-1">{severity}</p>
              </div>
            )
          )}
        </div>
      </div>

      {/* Findings Table */}
      <div className="rounded-lg border border-border bg-card">
        <div className="p-4 border-b border-border">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Findings</h2>

            <div className="flex items-center gap-2">
              <label className="text-sm text-muted-foreground">Filter:</label>
              <select
                value={severityFilter}
                onChange={(e) => setSeverityFilter(e.target.value)}
                className="px-3 py-1.5 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="all">All Severities</option>
                <option value="CRITICAL">Critical</option>
                <option value="HIGH">High</option>
                <option value="MEDIUM">Medium</option>
                <option value="LOW">Low</option>
                <option value="INFO">Info</option>
              </select>
            </div>
          </div>
        </div>

        {findingsLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
          </div>
        ) : findingsError ? (
          <div className="p-4">
            <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4">
              <div className="flex items-center gap-2 text-destructive">
                <AlertCircle className="h-5 w-5" />
                <p className="font-medium">Failed to load findings</p>
              </div>
            </div>
          </div>
        ) : findings.length === 0 ? (
          <div className="p-12 text-center">
            <FileSearch className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <p className="text-muted-foreground">No findings for selected filter</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-muted/50 border-b border-border">
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-medium">Severity</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">CVE ID</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Description</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Location</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Tool</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {findings.map((finding) => (
                  <tr key={finding.finding_id} className="hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3">
                      <span
                        className={`inline-block px-2 py-1 rounded text-xs font-semibold ${getSeverityColor(
                          finding.severity
                        )}`}
                      >
                        {finding.severity}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="font-mono text-sm">{finding.cve_id}</span>
                    </td>
                    <td className="px-4 py-3">
                      <p className="text-sm line-clamp-2">{finding.description}</p>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-sm text-muted-foreground font-mono">
                        {finding.location}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-sm">{finding.tool_name}</span>
                    </td>
                    <td className="px-4 py-3 text-sm text-muted-foreground">
                      {finding.created_at ? format(new Date(finding.created_at), "PP") : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {findings.length > 0 && (
          <div className="px-4 py-3 border-t border-border bg-muted/20">
            <p className="text-sm text-muted-foreground">
              Showing {findings.length} finding{findings.length !== 1 ? "s" : ""}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
