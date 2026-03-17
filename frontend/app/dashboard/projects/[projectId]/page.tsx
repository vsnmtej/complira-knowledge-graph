"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  FolderKanban,
  AlertCircle,
  Plus,
  Pencil,
  Trash2,
  ArrowLeft,
  GitBranch,
  FileSearch,
  ShieldAlert,
  X,
  Check,
} from "lucide-react";
import {
  getProject,
  getProjectSummary,
  updateProject,
  deleteProject,
  type UpdateProjectRequest,
} from "@/lib/api/projects";
import { listRepositories, type Repository } from "@/lib/api/repositories";
import { format } from "date-fns";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

export default function ProjectDetailPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = params.projectId as string;
  const queryClient = useQueryClient();

  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editTags, setEditTags] = useState("");
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const {
    data: projectData,
    isLoading: projectLoading,
    error: projectError,
  } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId),
  });

  const { data: summaryData, isLoading: summaryLoading } = useQuery({
    queryKey: ["project-summary", projectId],
    queryFn: () => getProjectSummary(projectId),
    enabled: !!projectData,
  });

  const { data: reposData, isLoading: reposLoading } = useQuery({
    queryKey: ["repositories", { project_id: projectId }],
    queryFn: () => listRepositories({ project_id: projectId }),
    enabled: !!projectData,
  });

  const project = projectData?.data;
  const summary = summaryData?.data;
  const repositories = reposData?.data?.repositories || [];

  const updateMutation = useMutation({
    mutationFn: (data: UpdateProjectRequest) => updateProject(projectId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setIsEditing(false);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteProject(projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      router.push("/dashboard/projects");
    },
  });

  const startEdit = () => {
    if (!project) return;
    setEditName(project.name);
    setEditDescription(project.description || "");
    setEditTags(project.tags.join(", "));
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
      tags,
    });
  };

  if (projectLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    );
  }

  if (projectError) {
    return (
      <div className="space-y-6">
        <Link
          href="/dashboard/projects"
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Projects
        </Link>
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4">
          <div className="flex items-center gap-2 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <p className="font-medium">Failed to load project</p>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            {(projectError as Error).message}
          </p>
        </div>
      </div>
    );
  }

  if (!project) return null;

  return (
    <div className="space-y-6">
      {/* Back link */}
      <Link
        href="/dashboard/projects"
        className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Projects
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
                  {project.name}
                </h1>
                {project.active ? (
                  <span className="text-xs px-2 py-1 rounded bg-green-500/10 text-green-500">
                    Active
                  </span>
                ) : (
                  <span className="text-xs px-2 py-1 rounded bg-gray-500/10 text-gray-500">
                    Archived
                  </span>
                )}
              </div>
              {project.description && (
                <p className="text-muted-foreground mt-1">
                  {project.description}
                </p>
              )}
              {project.tags.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {project.tags.map((tag) => (
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
            <div className="p-2 rounded-lg bg-blue-500/10">
              <GitBranch className="h-5 w-5 text-blue-500" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Repositories</p>
              <p className="text-2xl font-bold">
                {summaryLoading ? "--" : summary?.repository_count ?? 0}
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-purple-500/10">
              <FileSearch className="h-5 w-5 text-purple-500" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Total Scans</p>
              <p className="text-2xl font-bold">
                {summaryLoading ? "--" : summary?.total_scans ?? 0}
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
                  : `${summary?.findings.critical ?? 0} / ${summary?.findings.high ?? 0}`}
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
                {summaryLoading ? "--" : summary?.findings.total ?? 0}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Repositories Section */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold">Repositories</h2>
          <Link
            href={`/dashboard/repositories?project=${projectId}`}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium text-sm"
          >
            <Plus className="h-4 w-4" />
            Add Repository
          </Link>
        </div>

        {reposLoading && (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
          </div>
        )}

        {!reposLoading && repositories.length === 0 && (
          <div className="rounded-lg border border-border bg-card p-8 text-center">
            <GitBranch className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
            <h3 className="text-lg font-semibold mb-1">
              No repositories in this project
            </h3>
            <p className="text-muted-foreground mb-4">
              Add a repository to start scanning
            </p>
            <Link
              href={`/dashboard/repositories?project=${projectId}`}
              className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium text-sm"
            >
              <Plus className="h-4 w-4" />
              Add Repository
            </Link>
          </div>
        )}

        {!reposLoading && repositories.length > 0 && (
          <div className="rounded-lg border border-border bg-card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-muted/50 border-b border-border">
                  <tr>
                    <th className="px-4 py-3 text-left text-sm font-medium">
                      Name
                    </th>
                    <th className="px-4 py-3 text-left text-sm font-medium">
                      URL
                    </th>
                    <th className="px-4 py-3 text-left text-sm font-medium">
                      Branch
                    </th>
                    <th className="px-4 py-3 text-left text-sm font-medium">
                      Scans
                    </th>
                    <th className="px-4 py-3 text-left text-sm font-medium">
                      Last Scan
                    </th>
                    <th className="px-4 py-3 text-right text-sm font-medium">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {repositories.map((repo: Repository) => (
                    <tr
                      key={repo.repository_id}
                      className="hover:bg-muted/30 transition-colors"
                    >
                      <td className="px-4 py-3">
                        <Link
                          href={`/dashboard/repositories/${repo.repository_id}`}
                          className="font-medium text-primary hover:underline"
                        >
                          {repo.name}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-sm text-muted-foreground truncate max-w-xs">
                        {repo.repository_url || "--"}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        {repo.default_branch && (
                          <span className="text-xs px-2 py-0.5 rounded bg-purple-500/10 text-purple-500 font-mono">
                            {repo.default_branch}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 font-semibold">
                        {repo.scan_count}
                      </td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">
                        {repo.last_scan_at
                          ? format(new Date(repo.last_scan_at), "PP")
                          : "Never"}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end">
                          <Link
                            href={`/dashboard/repositories/${repo.repository_id}`}
                            className="text-sm text-primary hover:underline"
                          >
                            View Details
                          </Link>
                        </div>
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
            <h2 className="text-xl font-bold mb-2">Archive Project</h2>
            <p className="text-muted-foreground mb-6">
              Are you sure you want to archive &quot;{project.name}&quot;?
              Repositories will be unassigned but not deleted.
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
                {deleteMutation.isPending ? "Archiving..." : "Archive Project"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
