"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { FolderKanban, Plus, AlertCircle, X } from "lucide-react";
import {
  listProjects,
  createProject,
  type Project,
  type CreateProjectRequest,
} from "@/lib/api/projects";
import { format } from "date-fns";
import Link from "next/link";

export default function ProjectsPage() {
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [formName, setFormName] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formTags, setFormTags] = useState("");
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ["projects"],
    queryFn: () => listProjects(),
  });

  const projects = data?.data?.projects || [];

  const createMutation = useMutation({
    mutationFn: (req: CreateProjectRequest) => createProject(req),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setShowCreateModal(false);
      resetForm();
    },
  });

  const resetForm = () => {
    setFormName("");
    setFormDescription("");
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
      description: formDescription.trim() || undefined,
      tags: tags.length > 0 ? tags : undefined,
    });
  };

  const tagColors = [
    "blue",
    "green",
    "purple",
    "orange",
    "pink",
    "cyan",
    "yellow",
    "red",
  ];

  const getTagColor = (tag: string) => {
    let hash = 0;
    for (let i = 0; i < tag.length; i++) {
      hash = tag.charCodeAt(i) + ((hash << 5) - hash);
    }
    return tagColors[Math.abs(hash) % tagColors.length];
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Projects</h1>
          <p className="text-muted-foreground mt-1">
            Organize repositories into projects for aggregated reporting
          </p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium"
        >
          <Plus className="h-4 w-4" />
          New Project
        </button>
      </div>

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
            <p className="font-medium">Failed to load projects</p>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            {(error as Error).message}
          </p>
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && projects.length === 0 && (
        <div className="rounded-lg border border-border bg-card p-12 text-center">
          <FolderKanban className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <h3 className="text-lg font-semibold mb-2">No projects yet</h3>
          <p className="text-muted-foreground mb-6">
            Create your first project to start organizing repositories
          </p>
          <button
            onClick={() => setShowCreateModal(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium"
          >
            <Plus className="h-4 w-4" />
            New Project
          </button>
        </div>
      )}

      {/* Projects Table */}
      {!isLoading && !error && projects.length > 0 && (
        <div className="rounded-lg border border-border bg-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-muted/50 border-b border-border">
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-medium">
                    Name
                  </th>
                  <th className="px-4 py-3 text-left text-sm font-medium">
                    Description
                  </th>
                  <th className="px-4 py-3 text-left text-sm font-medium">
                    Tags
                  </th>
                  <th className="px-4 py-3 text-left text-sm font-medium">
                    Repositories
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
                {projects.map((project: Project) => (
                  <tr
                    key={project.project_id}
                    className="hover:bg-muted/30 transition-colors cursor-pointer"
                    onClick={() => {}}
                  >
                    <td className="px-4 py-3">
                      <Link
                        href={`/dashboard/projects/${project.project_id}`}
                        className="font-medium text-primary hover:underline"
                      >
                        {project.name}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-sm text-muted-foreground max-w-xs truncate">
                      {project.description || "--"}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {project.tags.map((tag) => {
                          const color = getTagColor(tag);
                          return (
                            <span
                              key={tag}
                              className={`text-xs px-2 py-0.5 rounded bg-${color}-500/10 text-${color}-500`}
                            >
                              {tag}
                            </span>
                          );
                        })}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="font-semibold">
                        {project.repository_count}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-muted-foreground">
                      {project.last_scan_at
                        ? format(new Date(project.last_scan_at), "PP")
                        : "Never"}
                    </td>
                    <td className="px-4 py-3">
                      {project.active ? (
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
                          href={`/dashboard/projects/${project.project_id}`}
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
              Showing {projects.length} projects
            </p>
          </div>
        </div>
      )}

      {/* Create Project Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-card border border-border rounded-lg max-w-lg w-full">
            <div className="flex items-center justify-between p-6 border-b border-border">
              <div>
                <h2 className="text-2xl font-bold">New Project</h2>
                <p className="text-sm text-muted-foreground mt-1">
                  Create a project to organize your repositories
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
                  Project Name
                </label>
                <input
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="e.g., Backend Services"
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">
                  Description
                </label>
                <textarea
                  value={formDescription}
                  onChange={(e) => setFormDescription(e.target.value)}
                  placeholder="Describe this project..."
                  rows={3}
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm resize-none"
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
                  placeholder="e.g., backend, production, critical"
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                />
              </div>

              {createMutation.isError && (
                <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4">
                  <div className="flex items-center gap-2 text-destructive">
                    <AlertCircle className="h-5 w-5" />
                    <p className="font-medium">Failed to create project</p>
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
                    Create Project
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
