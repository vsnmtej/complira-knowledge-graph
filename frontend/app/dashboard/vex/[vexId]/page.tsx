"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { format } from "date-fns";
import {
  ArrowLeft,
  Shield,
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Edit,
  Download,
  FileText,
  TrendingUp,
  Bug,
  Target,
  BookOpen,
} from "lucide-react";
import { getVEX, patchVulnerability, type VEXDocument, type VEXVulnerability } from "@/lib/api/vex";

export default function VEXDetailsPage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const vexId = params.vexId as string;

  const [editingVuln, setEditingVuln] = useState<string | null>(null);
  const [editState, setEditState] = useState("");
  const [editDetail, setEditDetail] = useState("");

  // Fetch VEX document
  const {
    data: vexData,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["vex", vexId],
    queryFn: () => getVEX(vexId),
    enabled: !!vexId,
  });

  const vex = vexData?.data;

  // Update vulnerability mutation
  const updateMutation = useMutation({
    mutationFn: ({ cveId, state, detail }: { cveId: string; state: string; detail: string }) =>
      patchVulnerability(vexId, cveId, {
        analysis: { state, detail },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vex", vexId] });
      setEditingVuln(null);
    },
  });

  const handleSaveEdit = (cveId: string) => {
    updateMutation.mutate({
      cveId,
      state: editState,
      detail: editDetail,
    });
  };

  const getStateColor = (state: string) => {
    switch (state?.toLowerCase()) {
      case "exploitable":
        return "text-red-600 bg-red-100 border-red-200";
      case "not_affected":
        return "text-green-600 bg-green-100 border-green-200";
      case "resolved":
        return "text-blue-600 bg-blue-100 border-blue-200";
      case "in_triage":
        return "text-yellow-600 bg-yellow-100 border-yellow-200";
      case "false_positive":
        return "text-gray-600 bg-gray-100 border-gray-200";
      default:
        return "text-gray-600 bg-gray-100 border-gray-200";
    }
  };

  const getStateIcon = (state: string) => {
    switch (state?.toLowerCase()) {
      case "exploitable":
        return <AlertCircle className="h-4 w-4" />;
      case "not_affected":
        return <CheckCircle2 className="h-4 w-4" />;
      case "resolved":
        return <CheckCircle2 className="h-4 w-4" />;
      case "in_triage":
        return <AlertTriangle className="h-4 w-4" />;
      case "false_positive":
        return <XCircle className="h-4 w-4" />;
      default:
        return <Shield className="h-4 w-4" />;
    }
  };

  const downloadVEX = () => {
    if (!vex) return;
    const json = JSON.stringify(vex, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${vex.vex_id}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    );
  }

  if (error || !vex) {
    return (
      <div className="space-y-6">
        <Link
          href="/dashboard/vex"
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to VEX
        </Link>

        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4">
          <div className="flex items-center gap-2 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <p className="font-medium">Failed to load VEX document</p>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            {(error as Error)?.message || "VEX document not found"}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <Link
          href="/dashboard/vex"
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-4"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to VEX
        </Link>

        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">VEX Document</h1>
            <p className="text-muted-foreground mt-1">
              ID: <span className="font-mono">{vex.vex_id}</span>
            </p>
          </div>

          <button
            onClick={downloadVEX}
            className="inline-flex items-center gap-2 px-4 py-2 border border-border rounded-lg hover:bg-accent transition-colors text-sm font-medium"
          >
            <Download className="h-4 w-4" />
            Download JSON
          </button>
        </div>
      </div>

      {/* Metadata */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-2">
            <FileText className="h-4 w-4" />
            <span className="text-sm font-medium">Format</span>
          </div>
          <p className="font-semibold">{vex.bomFormat}</p>
          <p className="text-xs text-muted-foreground">v{vex.specVersion}</p>
        </div>

        <div className="rounded-lg border border-border bg-card p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-2">
            <Shield className="h-4 w-4" />
            <span className="text-sm font-medium">Vulnerabilities</span>
          </div>
          <p className="text-2xl font-bold">{vex.vulnerabilities.length}</p>
        </div>

        <div className="rounded-lg border border-border bg-card p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-2">
            <FileText className="h-4 w-4" />
            <span className="text-sm font-medium">Version</span>
          </div>
          <p className="text-2xl font-bold">{vex.version}</p>
        </div>
      </div>

      {/* Vulnerabilities */}
      <div className="space-y-4">
        <h2 className="text-xl font-semibold">Vulnerability Assessments</h2>

        {vex.vulnerabilities.map((vuln) => (
          <div
            key={vuln.cve_id}
            className="rounded-lg border border-border bg-card p-6 space-y-4"
          >
            {/* CVE Header */}
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-3 mb-2">
                  <h3 className="text-lg font-semibold font-mono">{vuln.cve_id}</h3>
                  <div
                    className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border ${getStateColor(
                      vuln.state
                    )}`}
                  >
                    {getStateIcon(vuln.state)}
                    {vuln.state.replace("_", " ").toUpperCase()}
                  </div>
                  {vuln.enrichment.in_kev && (
                    <span className="px-2 py-0.5 rounded bg-red-600 text-white text-xs font-semibold">
                      KEV
                    </span>
                  )}
                </div>

                {vuln.detail && (
                  <p className="text-sm text-muted-foreground">{vuln.detail}</p>
                )}
              </div>

              <button
                onClick={() => {
                  setEditingVuln(vuln.cve_id);
                  setEditState(vuln.state);
                  setEditDetail(vuln.detail || "");
                }}
                className="p-2 hover:bg-accent rounded transition-colors"
              >
                <Edit className="h-4 w-4" />
              </button>
            </div>

            {/* Enrichment Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* CVSS */}
              {vuln.enrichment.cvss_score !== undefined && (
                <div className="p-3 rounded-lg bg-muted/50">
                  <div className="flex items-center gap-2 mb-1">
                    <TrendingUp className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="text-xs font-medium text-muted-foreground">CVSS Score</span>
                  </div>
                  <p className="text-xl font-bold">{vuln.enrichment.cvss_score}</p>
                  <p className="text-xs text-muted-foreground">{vuln.enrichment.cvss_severity}</p>
                </div>
              )}

              {/* EPSS */}
              {vuln.enrichment.epss_score !== undefined && (
                <div className="p-3 rounded-lg bg-muted/50">
                  <div className="flex items-center gap-2 mb-1">
                    <Target className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="text-xs font-medium text-muted-foreground">EPSS Score</span>
                  </div>
                  <p className="text-xl font-bold">
                    {(vuln.enrichment.epss_score * 100).toFixed(1)}%
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {(vuln.enrichment.epss_percentile! * 100).toFixed(1)}th percentile
                  </p>
                </div>
              )}

              {/* KEV */}
              {vuln.enrichment.in_kev && (
                <div className="p-3 rounded-lg bg-red-50 border border-red-200">
                  <div className="flex items-center gap-2 mb-1">
                    <AlertCircle className="h-3.5 w-3.5 text-red-600" />
                    <span className="text-xs font-medium text-red-600">KEV Catalog</span>
                  </div>
                  <p className="text-sm font-semibold text-red-600">Actively Exploited</p>
                  {vuln.enrichment.kev_due_date && (
                    <p className="text-xs text-red-600">
                      Due: {format(new Date(vuln.enrichment.kev_due_date), "PP")}
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* CWE Weaknesses */}
            {vuln.enrichment.weaknesses.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <Bug className="h-4 w-4 text-muted-foreground" />
                  <h4 className="text-sm font-semibold">CWE Weaknesses</h4>
                </div>
                <div className="flex flex-wrap gap-2">
                  {vuln.enrichment.weaknesses.map((weakness, idx) => (
                    <div
                      key={idx}
                      className="px-3 py-1.5 rounded-lg bg-orange-100 border border-orange-200 text-orange-700 text-xs"
                    >
                      <span className="font-semibold">{weakness.cwe_id}</span> - {weakness.name}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ATT&CK Techniques */}
            {vuln.enrichment.attack_techniques.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <Target className="h-4 w-4 text-muted-foreground" />
                  <h4 className="text-sm font-semibold">MITRE ATT&CK Techniques</h4>
                </div>
                <div className="flex flex-wrap gap-2">
                  {vuln.enrichment.attack_techniques.map((tech, idx) => (
                    <div
                      key={idx}
                      className="px-3 py-1.5 rounded-lg bg-red-100 border border-red-200 text-red-700 text-xs"
                    >
                      <span className="font-semibold">{tech.technique_id}</span> - {tech.name}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* NIST Controls */}
            {vuln.enrichment.nist_controls.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <BookOpen className="h-4 w-4 text-muted-foreground" />
                  <h4 className="text-sm font-semibold">NIST 800-53 Controls</h4>
                </div>
                <div className="flex flex-wrap gap-2">
                  {vuln.enrichment.nist_controls.map((control, idx) => (
                    <div
                      key={idx}
                      className="px-3 py-1.5 rounded-lg bg-blue-100 border border-blue-200 text-blue-700 text-xs"
                    >
                      <span className="font-semibold">{control.control_id}</span> - {control.title}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Regulatory Violations */}
            {vuln.enrichment.regulatory_violations.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <AlertTriangle className="h-4 w-4 text-muted-foreground" />
                  <h4 className="text-sm font-semibold">Regulatory Violations</h4>
                </div>
                <div className="flex flex-wrap gap-2">
                  {vuln.enrichment.regulatory_violations.map((violation, idx) => (
                    <div
                      key={idx}
                      className="px-3 py-1.5 rounded-lg bg-purple-100 border border-purple-200 text-purple-700 text-xs"
                    >
                      <span className="font-semibold">{violation.framework}</span> -{" "}
                      {violation.requirement_id}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Edit Modal */}
      {editingVuln && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-card border border-border rounded-lg max-w-2xl w-full p-6">
            <h2 className="text-2xl font-bold mb-4">Update Assessment</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">State</label>
                <select
                  value={editState}
                  onChange={(e) => setEditState(e.target.value)}
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg"
                >
                  <option value="exploitable">Exploitable</option>
                  <option value="not_affected">Not Affected</option>
                  <option value="in_triage">In Triage</option>
                  <option value="resolved">Resolved</option>
                  <option value="false_positive">False Positive</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Detail</label>
                <textarea
                  value={editDetail}
                  onChange={(e) => setEditDetail(e.target.value)}
                  rows={4}
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg"
                  placeholder="Explanation or justification..."
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 mt-6">
              <button
                onClick={() => setEditingVuln(null)}
                className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg"
                disabled={updateMutation.isPending}
              >
                Cancel
              </button>
              <button
                onClick={() => handleSaveEdit(editingVuln)}
                disabled={updateMutation.isPending}
                className="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 text-sm font-medium disabled:opacity-50"
              >
                {updateMutation.isPending ? "Saving..." : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
