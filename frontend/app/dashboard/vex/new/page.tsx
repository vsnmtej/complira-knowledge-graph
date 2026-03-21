"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Plus, Trash2, Shield, AlertCircle, CheckCircle2 } from "lucide-react";
import { createVEX, type CreateVEXRequest } from "@/lib/api/vex";

interface VulnEntry {
  id: string;
  state: "not_affected" | "exploitable" | "in_triage" | "resolved" | "false_positive";
  justification?: string;
  detail: string;
}

const VEX_STATES = [
  { value: "not_affected", label: "Not Affected", color: "text-green-500" },
  { value: "exploitable", label: "Exploitable", color: "text-red-500" },
  { value: "in_triage", label: "In Triage", color: "text-yellow-500" },
  { value: "resolved", label: "Resolved", color: "text-blue-500" },
  { value: "false_positive", label: "False Positive", color: "text-slate-500" },
];

const JUSTIFICATIONS = [
  "code_not_present",
  "code_not_reachable",
  "requires_configuration",
  "requires_dependency",
  "requires_environment",
  "protected_by_compiler",
  "protected_at_runtime",
  "protected_at_perimeter",
  "protected_by_mitigating_control",
];

export default function CreateVEXPage() {
  const router = useRouter();

  const [vulnerabilities, setVulnerabilities] = useState<VulnEntry[]>([
    { id: "", state: "in_triage", detail: "" },
  ]);
  const [metadata, setMetadata] = useState({
    componentName: "",
    componentVersion: "",
  });

  const createMutation = useMutation({
    mutationFn: (request: CreateVEXRequest) => createVEX(request),
    onSuccess: (data) => {
      router.push(`/dashboard/vex/${data.data.vex_id}`);
    },
  });

  const addVulnerability = () => {
    setVulnerabilities([...vulnerabilities, { id: "", state: "in_triage", detail: "" }]);
  };

  const removeVulnerability = (index: number) => {
    if (vulnerabilities.length <= 1) return;
    setVulnerabilities(vulnerabilities.filter((_, i) => i !== index));
  };

  const updateVulnerability = (index: number, updates: Partial<VulnEntry>) => {
    setVulnerabilities(
      vulnerabilities.map((v, i) => (i === index ? { ...v, ...updates } : v))
    );
  };

  const handleSubmit = () => {
    const valid = vulnerabilities.every((v) => v.id.match(/^CVE-\d{4}-\d{4,}$/));
    if (!valid) return;

    const request: CreateVEXRequest = {
      bomFormat: "CycloneDX",
      specVersion: "1.5",
      vulnerabilities: vulnerabilities.map((v) => ({
        id: v.id,
        analysis: {
          state: v.state,
          justification: v.state === "not_affected" ? v.justification : undefined,
          detail: v.detail || undefined,
        },
      })),
      metadata:
        metadata.componentName
          ? {
              component: {
                type: "application",
                name: metadata.componentName,
                version: metadata.componentVersion || undefined,
              },
            }
          : undefined,
    };

    createMutation.mutate(request);
  };

  const isValid = vulnerabilities.every(
    (v) => v.id.match(/^CVE-\d{4}-\d{4,}$/) && v.state
  );

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link
          href="/dashboard/vex"
          className="p-2 hover:bg-accent rounded-lg transition-colors"
        >
          <ArrowLeft className="h-5 w-5" />
        </Link>
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Create VEX Document</h1>
          <p className="text-muted-foreground mt-1">
            Assess vulnerability exploitability with knowledge graph enrichment
          </p>
        </div>
      </div>

      {/* Metadata */}
      <div className="rounded-lg border border-border bg-card shadow-sm p-6">
        <h2 className="text-lg font-semibold mb-4">Component Information (Optional)</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">
              Component Name
            </label>
            <input
              type="text"
              value={metadata.componentName}
              onChange={(e) => setMetadata({ ...metadata, componentName: e.target.value })}
              placeholder="e.g., my-application"
              className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">
              Version
            </label>
            <input
              type="text"
              value={metadata.componentVersion}
              onChange={(e) => setMetadata({ ...metadata, componentVersion: e.target.value })}
              placeholder="e.g., 1.0.0"
              className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
            />
          </div>
        </div>
      </div>

      {/* Vulnerabilities */}
      <div className="rounded-lg border border-border bg-card shadow-sm">
        <div className="p-6 border-b border-border flex items-center justify-between">
          <h2 className="text-lg font-semibold">Vulnerability Assessments</h2>
          <button
            onClick={addVulnerability}
            className="inline-flex items-center gap-2 px-3 py-1.5 text-sm bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
          >
            <Plus className="h-4 w-4" />
            Add CVE
          </button>
        </div>

        <div className="divide-y divide-border">
          {vulnerabilities.map((vuln, index) => (
            <div key={index} className="p-6 space-y-4">
              <div className="flex items-start gap-4">
                <div className="flex-1 grid grid-cols-2 gap-4">
                  {/* CVE ID */}
                  <div>
                    <label className="block text-sm font-medium text-muted-foreground mb-1">
                      CVE ID *
                    </label>
                    <input
                      type="text"
                      value={vuln.id}
                      onChange={(e) => updateVulnerability(index, { id: e.target.value.toUpperCase() })}
                      placeholder="CVE-2024-1234"
                      className={`w-full px-3 py-2 bg-background border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm font-mono ${
                        vuln.id && !vuln.id.match(/^CVE-\d{4}-\d{4,}$/)
                          ? "border-destructive"
                          : "border-border"
                      }`}
                    />
                    {vuln.id && !vuln.id.match(/^CVE-\d{4}-\d{4,}$/) && (
                      <p className="text-destructive text-xs mt-1">Format: CVE-YYYY-NNNN</p>
                    )}
                  </div>

                  {/* State */}
                  <div>
                    <label className="block text-sm font-medium text-muted-foreground mb-1">
                      State *
                    </label>
                    <select
                      value={vuln.state}
                      onChange={(e) => updateVulnerability(index, { state: e.target.value as VulnEntry["state"] })}
                      className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                    >
                      {VEX_STATES.map((s) => (
                        <option key={s.value} value={s.value}>{s.label}</option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* Remove button */}
                {vulnerabilities.length > 1 && (
                  <button
                    onClick={() => removeVulnerability(index)}
                    className="p-2 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-lg transition-colors mt-6"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                )}
              </div>

              {/* Justification (only for not_affected) */}
              {vuln.state === "not_affected" && (
                <div>
                  <label className="block text-sm font-medium text-muted-foreground mb-1">
                    Justification
                  </label>
                  <select
                    value={vuln.justification || ""}
                    onChange={(e) => updateVulnerability(index, { justification: e.target.value })}
                    className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                  >
                    <option value="">Select justification...</option>
                    {JUSTIFICATIONS.map((j) => (
                      <option key={j} value={j}>
                        {j.replace(/_/g, " ")}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {/* Detail */}
              <div>
                <label className="block text-sm font-medium text-muted-foreground mb-1">
                  Detail / Notes
                </label>
                <textarea
                  value={vuln.detail}
                  onChange={(e) => updateVulnerability(index, { detail: e.target.value })}
                  placeholder="Explain why this CVE has the selected state..."
                  rows={2}
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm resize-none"
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Error */}
      {createMutation.isError && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4">
          <div className="flex items-center gap-2 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <p className="font-medium">Failed to create VEX document</p>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            {createMutation.error instanceof Error ? createMutation.error.message : "Unknown error"}
          </p>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {vulnerabilities.length} vulnerability{vulnerabilities.length !== 1 ? "ies" : "y"} — each will be enriched with KEV, EPSS, CVSS, CWE, ATT&CK data
        </p>
        <div className="flex items-center gap-3">
          <Link
            href="/dashboard/vex"
            className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg transition-colors"
          >
            Cancel
          </Link>
          <button
            onClick={handleSubmit}
            disabled={!isValid || createMutation.isPending}
            className="inline-flex items-center gap-2 px-6 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {createMutation.isPending ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-primary-foreground" />
                Creating...
              </>
            ) : (
              <>
                <Shield className="h-4 w-4" />
                Create VEX Document
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
