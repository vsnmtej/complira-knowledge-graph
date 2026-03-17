"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { GitBranch, Plus, AlertCircle, X, CheckCircle2, Clock } from "lucide-react";
import {
  listRepositories,
  createRepository,
  type Repository,
  type CreateRepositoryRequest,
} from "@/lib/api/repositories";
import { listProjects, type Project } from "@/lib/api/projects";
import { format } from "date-fns";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

export default function RepositoriesPage() {
  const searchParams = useSearchParams();
  const preselectedProject = searchParams.get("project") || "";

  const [showCreateModal, setShowCreateModal] = useState(!!preselectedProject);
  const [filterProject, setFilterProject] = useState("");
  const [formName, setFormName] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formProjectId, setFormProjectId] = useState(preselectedProject);
  const [formUrl, setFormUrl] = useState("");
  const [formBranch, setFormBranch] = useState("main");
  const [formTags, setFormTags] = useState("");
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ["repositories", { project_id: filterProject || undefined }],
    queryFn: () =>
      listRepositories(
        filterProject ? { project_id: filterProject } : undefined
      ),
  });

  const { data: projectsData } = useQuery({
    queryKey: ["projects"],
    queryFn: () => listProjects(),
  });

  const repositories = data?.data?.repositories || [];
  const projects = projectsData?.data?.projects || [];

  const createMutation = useMutation({
    mutationFn: (req: CreateRepositoryRequest) => createRepository(req),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["repositories"] });
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setShowCreateModal(false);
      resetForm();
    },
  });

  const resetForm = () => {
    setFormName("");
    setFormDescription("");
    setFormProjectId("");
    setFormUrl("");
    setFormBranch("main");
    setFormTags("");
  };

  const handleCreate = () => {
    if (!formName.trim()) return;
    const tags = formTags
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    createMutation.mutate({
      name: formName.trim(),
      project_id: formProjectId || undefined,
      description: formDescription.trim() || undefined,
      repository_url: formUrl.trim() || undefined,
      default_branch: formBranch.trim() || undefined,
      tags: tags.length > 0 ? tags : undefined,
    });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Repositories</h1>
          <p className="text-muted-foreground mt-1">
            Manage repositories and track vulnerability scans
          </p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium"
        >
          <Plus className="h-4 w-4" />
          New Repository
        </button>
      </div>

      {/* Filter */}
      {projects.length > 0 && (
        <div className="flex items-center gap-3">
          <label className="text-sm font-medium">Filter by project:</label>
          <select
            value={filterProject}
            onChange={(e) => setFilterProject(e.target.value)}
            className="px-3 py-1.5 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
          >
            <option value="">All Projects</option>
            {projects.map((p: Project) => (
              <option key={p.project_id} value={p.project_id}>
                {p.name}
              </option>
            ))}
          </select>
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
            <p className="font-medium">Failed to load repositories</p>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            {(error as Error).message}
          </p>
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && repositories.length === 0 && (
        <div className="rounded-lg border border-border bg-card p-12 text-center">
          <GitBranch className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <h3 className="text-lg font-semibold mb-2">No repositories yet</h3>
          <p className="text-muted-foreground mb-6">
            Register your first repository to start tracking vulnerabilities
          </p>
          <button
            onClick={() => setShowCreateModal(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium"
          >
            <Plus className="h-4 w-4" />
            New Repository
          </button>
        </div>
      )}

      {/* Repositories Table */}
      {!isLoading && !error && repositories.length > 0 && (
        <div className="rounded-lg border border-border bg-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-muted/50 border-b border-border">
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-medium">
                    Name
                  </th>
                  <th className="px-4 py-3 text-left text-sm font-medium">
                    Project
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
                  <th className="px-4 py-3 text-left text-sm font-medium">
                    Status
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
                    <td className="px-4 py-3 text-sm">
                      {repo.project_id ? (
                        <Link
                          href={`/dashboard/projects/${repo.project_id}`}
                          className="text-muted-foreground hover:text-foreground hover:underline"
                        >
                          {repo.project_name || repo.project_id}
                        </Link>
                      ) : (
                        <span className="text-muted-foreground">
                          Unassigned
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-sm text-muted-foreground truncate max-w-[200px]">
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
                      {repo.active ? (
                        <span className="text-xs px-2 py-1 rounded bg-green-500/10 text-green-500">
                          Active
                        </span>
                      ) : (
                        <span className="text-xs px-2 py-1 rounded bg-gray-500/10 text-gray-500">
                          Archived
                        </span>
                      )}
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

          <div className="px-4 py-3 border-t border-border bg-muted/20">
            <p className="text-sm text-muted-foreground">
              Showing {repositories.length} repositories
            </p>
          </div>
        </div>
      )}

      {/* Create Repository Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-card border border-border rounded-lg max-w-lg w-full max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between p-6 border-b border-border">
              <div>
                <h2 className="text-2xl font-bold">New Repository</h2>
                <p className="text-sm text-muted-foreground mt-1">
                  Register a repository for vulnerability scanning
                </p>
              </div>
              <button
                onClick={() => {
                  setShowCreateModal(false);
                  resetForm();
                }}
                className="p-2 hover:bg-accent rounded-lg transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">
                  Repository Name
                </label>
                <input
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="e.g., backend-api"
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">
                  Project
                </label>
                <select
                  value={formProjectId}
                  onChange={(e) => setFormProjectId(e.target.value)}
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                >
                  <option value="">No project (unassigned)</option>
                  {projects.map((p: Project) => (
                    <option key={p.project_id} value={p.project_id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">
                  Description
                </label>
                <textarea
                  value={formDescription}
                  onChange={(e) => setFormDescription(e.target.value)}
                  placeholder="Describe this repository..."
                  rows={2}
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm resize-none"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">
                  Repository URL
                </label>
                <input
                  type="text"
                  value={formUrl}
                  onChange={(e) => setFormUrl(e.target.value)}
                  placeholder="https://github.com/org/repo"
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">
                  Default Branch
                </label>
                <input
                  type="text"
                  value={formBranch}
                  onChange={(e) => setFormBranch(e.target.value)}
                  placeholder="main"
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">
                  Tags (comma-separated)
                </label>
                <input
                  type="text"
                  value={formTags}
                  onChange={(e) => setFormTags(e.target.value)}
                  placeholder="e.g., backend, production"
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                />
              </div>

              {createMutation.isError && (
                <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4">
                  <div className="flex items-center gap-2 text-destructive">
                    <AlertCircle className="h-5 w-5" />
                    <p className="font-medium">Failed to create repository</p>
                  </div>
                  <p className="text-sm text-muted-foreground mt-1">
                    {createMutation.error instanceof Error
                      ? createMutation.error.message
                      : "Unknown error"}
                  </p>
                </div>
              )}
            </div>

            <div className="flex items-center justify-end gap-3 p-6 border-t border-border">
              <button
                onClick={() => {
                  setShowCreateModal(false);
                  resetForm();
                }}
                className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg transition-colors"
                disabled={createMutation.isPending}
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={!formName.trim() || createMutation.isPending}
                className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {createMutation.isPending ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-primary-foreground"></div>
                    Creating...
                  </>
                ) : (
                  <>
                    <Plus className="h-4 w-4" />
                    Create Repository
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
