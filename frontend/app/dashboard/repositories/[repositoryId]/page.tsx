"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  GitBranch,
  AlertCircle,
  Pencil,
  Trash2,
  ArrowLeft,
  FileSearch,
  ShieldAlert,
  TrendingUp,
  TrendingDown,
  X,
  Check,
  ExternalLink,
} from "lucide-react";
import {
  getRepository,
  getRepositorySummary,
  updateRepository,
  deleteRepository,
  type UpdateRepositoryRequest,
} from "@/lib/api/repositories";
import { listScans, type ScanSession } from "@/lib/api/scans";
import { format } from "date-fns";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

export default function RepositoryDetailPage() {
  const params = useParams();
  const router = useRouter();
  const repositoryId = params.repositoryId as string;
  const queryClient = useQueryClient();

  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editUrl, setEditUrl] = useState("");
  const [editBranch, setEditBranch] = useState("");
  const [editTags, setEditTags] = useState("");
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const {
    data: repoData,
    isLoading: repoLoading,
    error: repoError,
  } = useQuery({
    queryKey: ["repository", repositoryId],
    queryFn: () => getRepository(repositoryId),
  });

  const { data: summaryData, isLoading: summaryLoading } = useQuery({
    queryKey: ["repository-summary", repositoryId],
    queryFn: () => getRepositorySummary(repositoryId),
    enabled: !!repoData,
  });

  const { data: scansData, isLoading: scansLoading } = useQuery({
    queryKey: ["scans", { repository_id: repositoryId }],
    queryFn: () => listScans({ limit: 10 }),
    enabled: !!repoData,
  });

  const repo = repoData?.data;
  const summary = summaryData?.data;
  const scans = scansData?.data || [];

  const updateMutation = useMutation({
    mutationFn: (data: UpdateRepositoryRequest) =>
      updateRepository(repositoryId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["repository", repositoryId],
      });
      queryClient.invalidateQueries({ queryKey: ["repositories"] });
      setIsEditing(false);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteRepository(repositoryId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["repositories"] });
      router.push("/dashboard/repositories");
    },
  });

  const startEdit = () => {
    if (!repo) return;
    setEditName(repo.name);
    setEditDescription(repo.description || "");
    setEditUrl(repo.repository_url || "");
    setEditBranch(repo.default_branch || "");
    setEditTags(repo.tags.join(", "));
    setIsEditing(true);
  };

  const handleSave = () => {
    const tags = editTags
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    updateMutation.mutate({
      name: editName.trim(),
      description: editDescription.trim() || undefined,
      repository_url: editUrl.trim() || undefined,
      default_branch: editBranch.trim() || undefined,
      tags,
    });
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "completed":
        return (
          <span className="text-xs px-2 py-1 rounded bg-green-500/10 text-green-500">
            Completed
          </span>
        );
      case "processing":
        return (
          <span className="text-xs px-2 py-1 rounded bg-blue-500/10 text-blue-500">
            Processing
          </span>
        );
      case "failed":
        return (
          <span className="text-xs px-2 py-1 rounded bg-red-500/10 text-red-500">
            Failed
          </span>
        );
      default:
        return (
          <span className="text-xs px-2 py-1 rounded bg-gray-500/10 text-gray-500">
            {status}
          </span>
        );
    }
  };

  if (repoLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    );
  }

  if (repoError) {
    return (
      <div className="space-y-6">
        <Link
          href="/dashboard/repositories"
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Repositories
        </Link>
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4">
          <div className="flex items-center gap-2 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <p className="font-medium">Failed to load repository</p>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            {(repoError as Error).message}
          </p>
        </div>
      </div>
    );
  }

  if (!repo) return null;

  return (
    <div className="space-y-6">
      {/* Back link */}
      <Link
        href="/dashboard/repositories"
        className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Repositories
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex-1">
          {isEditing ? (
            <div className="space-y-3 max-w-lg">
              <div>
                <label className="block text-sm font-medium mb-1">Name</label>
                <input
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">
                  Description
                </label>
                <textarea
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  rows={2}
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm resize-none"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">
                  Repository URL
                </label>
                <input
                  type="text"
                  value={editUrl}
                  onChange={(e) => setEditUrl(e.target.value)}
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">
                  Default Branch
                </label>
                <input
                  type="text"
                  value={editBranch}
                  onChange={(e) => setEditBranch(e.target.value)}
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">
                  Tags (comma-separated)
                </label>
                <input
                  type="text"
                  value={editTags}
                  onChange={(e) => setEditTags(e.target.value)}
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                />
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleSave}
                  disabled={updateMutation.isPending || !editName.trim()}
                  className="inline-flex items-center gap-1 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors text-sm font-medium disabled:opacity-50"
                >
                  <Check className="h-3.5 w-3.5" />
                  {updateMutation.isPending ? "Saving..." : "Save"}
                </button>
                <button
                  onClick={() => setIsEditing(false)}
                  className="inline-flex items-center gap-1 px-3 py-1.5 text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg transition-colors text-sm"
                >
                  <X className="h-3.5 w-3.5" />
                  Cancel
                </button>
              </div>
              {updateMutation.isError && (
                <p className="text-sm text-destructive">
                  {updateMutation.error instanceof Error
                    ? updateMutation.error.message
                    : "Update failed"}
                </p>
              )}
            </div>
          ) : (
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-3xl font-bold tracking-tight">
                  {repo.name}
                </h1>
                {repo.active ? (
                  <span className="text-xs px-2 py-1 rounded bg-green-500/10 text-green-500">
                    Active
                  </span>
                ) : (
                  <span className="text-xs px-2 py-1 rounded bg-gray-500/10 text-gray-500">
                    Archived
                  </span>
                )}
              </div>
              {repo.description && (
                <p className="text-muted-foreground mt-1">
                  {repo.description}
                </p>
              )}
              <div className="flex items-center gap-4 mt-2 text-sm text-muted-foreground">
                {repo.project_id && (
                  <Link
                    href={`/dashboard/projects/${repo.project_id}`}
                    className="hover:text-foreground hover:underline"
                  >
                    Project: {repo.project_name || repo.project_id}
                  </Link>
                )}
                {repo.repository_url && (
                  <a
                    href={repo.repository_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 hover:text-foreground"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                    {repo.repository_url}
                  </a>
                )}
                {repo.default_branch && (
                  <span className="text-xs px-2 py-0.5 rounded bg-purple-500/10 text-purple-500 font-mono">
                    {repo.default_branch}
                  </span>
                )}
              </div>
              {repo.tags.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {repo.tags.map((tag) => (
                    <span
                      key={tag}
                      className="text-xs px-2 py-0.5 rounded bg-blue-500/10 text-blue-500"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {!isEditing && (
          <div className="flex items-center gap-2">
            <button
              onClick={startEdit}
              className="inline-flex items-center gap-2 px-3 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg transition-colors"
            >
              <Pencil className="h-4 w-4" />
              Edit
            </button>
            <button
              onClick={() => setShowDeleteConfirm(true)}
              className="inline-flex items-center gap-2 px-3 py-2 text-sm text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-lg transition-colors"
            >
              <Trash2 className="h-4 w-4" />
              Archive
            </button>
          </div>
        )}
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-purple-500/10">
              <FileSearch className="h-5 w-5 text-purple-500" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Total Scans</p>
              <p className="text-2xl font-bold">
                {summaryLoading ? "--" : summary?.scan_count ?? 0}
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-red-500/10">
              <ShieldAlert className="h-5 w-5 text-red-500" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Critical / High</p>
              <p className="text-2xl font-bold">
                {summaryLoading
                  ? "--"
                  : `${summary?.current_findings.critical ?? 0} / ${summary?.current_findings.high ?? 0}`}
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-orange-500/10">
              <AlertCircle className="h-5 w-5 text-orange-500" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Total Findings</p>
              <p className="text-2xl font-bold">
                {summaryLoading
                  ? "--"
                  : summary?.current_findings.total ?? 0}
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-green-500/10">
              {(summary?.trends.net_change ?? 0) <= 0 ? (
                <TrendingDown className="h-5 w-5 text-green-500" />
              ) : (
                <TrendingUp className="h-5 w-5 text-red-500" />
              )}
            </div>
            <div>
              <p className="text-sm text-muted-foreground">7-Day Trend</p>
              <p className="text-2xl font-bold">
                {summaryLoading
                  ? "--"
                  : summary?.trends.net_change ?? 0}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Recent Scans Section */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold">Recent Scans</h2>
          <Link
            href="/dashboard/scans"
            className="text-sm text-primary hover:underline"
          >
            View all scans
          </Link>
        </div>

        {scansLoading && (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
          </div>
        )}

        {!scansLoading && scans.length === 0 && (
          <div className="rounded-lg border border-border bg-card p-8 text-center">
            <FileSearch className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
            <h3 className="text-lg font-semibold mb-1">No scans yet</h3>
            <p className="text-muted-foreground mb-4">
              Upload an SBOM or SARIF file to scan this repository
            </p>
            <Link
              href="/dashboard/scans"
              className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium text-sm"
            >
              Upload Scan
            </Link>
          </div>
        )}

        {!scansLoading && scans.length > 0 && (
          <div className="rounded-lg border border-border bg-card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-muted/50 border-b border-border">
                  <tr>
                    <th className="px-4 py-3 text-left text-sm font-medium">
                      Scan ID
                    </th>
                    <th className="px-4 py-3 text-left text-sm font-medium">
                      Tool
                    </th>
                    <th className="px-4 py-3 text-left text-sm font-medium">
                      Type
                    </th>
                    <th className="px-4 py-3 text-left text-sm font-medium">
                      Findings
                    </th>
                    <th className="px-4 py-3 text-left text-sm font-medium">
                      Status
                    </th>
                    <th className="px-4 py-3 text-left text-sm font-medium">
                      Date
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {scans.map((scan: ScanSession) => (
                    <tr
                      key={scan.session_id}
                      className="hover:bg-muted/30 transition-colors"
                    >
                      <td className="px-4 py-3">
                        <Link
                          href={`/dashboard/scans/${scan.session_id}`}
                          className="font-mono text-sm text-primary hover:underline"
                        >
                          {scan.session_id}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-sm">
                        {scan.tool_name}
                      </td>
                      <td className="px-4 py-3">
                        <span className="text-xs px-2 py-1 rounded bg-blue-500/10 text-blue-500 uppercase">
                          {scan.scan_type}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-semibold">
                        {scan.findings_count}
                      </td>
                      <td className="px-4 py-3">
                        {getStatusIcon(scan.status)}
                      </td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">
                        {scan.scan_timestamp ? format(new Date(scan.scan_timestamp), "PP") : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-card border border-border rounded-lg max-w-md w-full p-6">
            <h2 className="text-xl font-bold mb-2">Archive Repository</h2>
            <p className="text-muted-foreground mb-6">
              Are you sure you want to archive &quot;{repo.name}&quot;?
              Historical scan data will be preserved.
            </p>
            <div className="flex items-center justify-end gap-3">
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg transition-colors"
                disabled={deleteMutation.isPending}
              >
                Cancel
              </button>
              <button
                onClick={() => deleteMutation.mutate()}
                disabled={deleteMutation.isPending}
                className="px-4 py-2 bg-destructive text-destructive-foreground rounded-lg hover:bg-destructive/90 transition-colors text-sm font-medium disabled:opacity-50"
              >
                {deleteMutation.isPending
                  ? "Archiving..."
                  : "Archive Repository"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
