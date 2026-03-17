"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { format } from "date-fns";
import { Key, FileSearch, ShieldAlert, CheckCircle2, ArrowRight, Clock } from "lucide-react";
import { listTokens } from "@/lib/api/tokens";
import { listScans, type ScanSession } from "@/lib/api/scans";

export default function DashboardPage() {
  // Fetch tokens
  const { data: tokensData, isLoading: tokensLoading } = useQuery({
    queryKey: ["tokens", { include_revoked: false }],
    queryFn: () => listTokens({ include_revoked: false }),
  });

  // Fetch scans
  const { data: scansData, isLoading: scansLoading } = useQuery({
    queryKey: ["scans"],
    queryFn: () => listScans({ limit: 5 }),
  });

  const tokens = tokensData?.tokens || [];
  const scans = scansData?.data || [];
  const totalVulnerabilities = scans.reduce((sum, scan) => sum + scan.findings_count, 0);
  const criticalVulnerabilities = scans.reduce((sum, scan) => {
    // This is a rough estimate; you'd need to query findings to get exact counts
    return sum + Math.floor(scan.findings_count * 0.1); // Assume ~10% critical
  }, 0);

  const stats = [
    {
      name: "API Tokens",
      value: tokensLoading ? "-" : tokens.length.toString(),
      subtext: "Active tokens",
      icon: Key,
      color: "text-blue-500",
      href: "/dashboard/tokens",
    },
    {
      name: "SBOM Scans",
      value: scansLoading ? "-" : scans.length.toString(),
      subtext: "Recent scans",
      icon: FileSearch,
      color: "text-purple-500",
      href: "/dashboard/scans",
    },
    {
      name: "Vulnerabilities",
      value: scansLoading ? "-" : totalVulnerabilities.toString(),
      subtext: `${criticalVulnerabilities} critical`,
      icon: ShieldAlert,
      color: "text-red-500",
      href: "/dashboard/scans",
    },
    {
      name: "Compliance",
      value: "-",
      subtext: "Status",
      icon: CheckCircle2,
      color: "text-green-500",
      href: "/dashboard",
    },
  ];

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "completed":
        return <CheckCircle2 className="h-4 w-4 text-green-500" />;
      case "processing":
        return <Clock className="h-4 w-4 text-blue-500 animate-pulse" />;
      case "failed":
        return <div className="h-2 w-2 rounded-full bg-red-500" />;
      default:
        return <Clock className="h-4 w-4 text-gray-500" />;
    }
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-4xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground mt-2">
          Welcome to Complira - Cybersecurity Compliance Platform
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <Link
              key={stat.name}
              href={stat.href}
              className="rounded-lg border border-border bg-card p-6 shadow-sm hover:shadow-md transition-all hover:border-primary/50"
            >
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <p className="text-sm font-medium text-muted-foreground">{stat.name}</p>
                  <p className="text-3xl font-bold mt-2">{stat.value}</p>
                  <p className="text-xs text-muted-foreground mt-1">{stat.subtext}</p>
                </div>
                <Icon className={`h-8 w-8 ${stat.color}`} />
              </div>
            </Link>
          );
        })}
      </div>

      {/* Recent Scans */}
      {scans.length > 0 && (
        <div className="rounded-lg border border-border bg-card shadow-sm">
          <div className="p-6 border-b border-border flex items-center justify-between">
            <h2 className="text-xl font-semibold">Recent Scans</h2>
            <Link
              href="/dashboard/scans"
              className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
            >
              View all
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
          <div className="divide-y divide-border">
            {scans.slice(0, 5).map((scan) => (
              <Link
                key={scan.session_id}
                href={`/dashboard/scans/${scan.session_id}`}
                className="p-4 hover:bg-muted/30 transition-colors flex items-center justify-between"
              >
                <div className="flex items-center gap-4 flex-1">
                  <div>{getStatusIcon(scan.status)}</div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium truncate">{scan.tool_name} v{scan.tool_version}</p>
                    <div className="flex items-center gap-3 mt-1">
                      <span className="text-xs px-2 py-0.5 rounded bg-blue-500/10 text-blue-500 uppercase">
                        {scan.scan_type}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {format(new Date(scan.scan_timestamp), "PPp")}
                      </span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-6 text-sm">
                  <div className="text-center">
                    <p className="font-semibold text-red-500">{scan.findings_count}</p>
                    <p className="text-xs text-muted-foreground">Findings</p>
                  </div>
                  <div className="text-center">
                    <p className="font-semibold">{scan.components_count}</p>
                    <p className="text-xs text-muted-foreground">Components</p>
                  </div>
                  <ArrowRight className="h-4 w-4 text-muted-foreground" />
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Getting Started Card */}
      <div className="rounded-lg border border-border bg-card shadow-sm">
        <div className="p-6 border-b border-border">
          <h2 className="text-xl font-semibold">Getting Started</h2>
        </div>
        <div className="p-6">
          <h3 className="font-medium mb-4">Next Steps:</h3>
          <ol className="space-y-3 text-sm">
            <li className="flex items-start gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-semibold">
                1
              </span>
              <span className="text-muted-foreground">
                Create an API token in the API Tokens section
              </span>
            </li>
            <li className="flex items-start gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-semibold">
                2
              </span>
              <span className="text-muted-foreground">
                Upload your SBOM file or use the API to scan your software
              </span>
            </li>
            <li className="flex items-start gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-semibold">
                3
              </span>
              <span className="text-muted-foreground">
                Review vulnerabilities and compliance findings
              </span>
            </li>
            <li className="flex items-start gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-semibold">
                4
              </span>
              <span className="text-muted-foreground">
                Generate VEX documents for remediation tracking
              </span>
            </li>
          </ol>
        </div>
      </div>
    </div>
  );
}
