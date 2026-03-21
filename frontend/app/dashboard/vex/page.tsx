"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Shield, AlertCircle, FileText, Plus, Trash2 } from "lucide-react";
import { listVEX, deleteVEX, type VEXListItem } from "@/lib/api/vex";
import { format } from "date-fns";
import Link from "next/link";

export default function VEXPage() {
  const queryClient = useQueryClient();
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  // Fetch VEX documents
  const { data, isLoading, error } = useQuery({
    queryKey: ["vex"],
    queryFn: () => listVEX(),
  });

  const vexDocs = data?.data || [];

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (vexId: string) => deleteVEX(vexId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vex"] });
      setDeleteConfirm(null);
    },
  });

  const handleDelete = (vexId: string) => {
    deleteMutation.mutate(vexId);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">VEX Documents</h1>
          <p className="text-muted-foreground mt-1">
            Manage Vulnerability Exploitability eXchange documents
          </p>
        </div>
        <Link
          href="/dashboard/vex/new"
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium"
        >
          <Plus className="h-4 w-4" />
          Create VEX
        </Link>
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
            <p className="font-medium">Failed to load VEX documents</p>
          </div>
          <p className="text-sm text-muted-foreground mt-1">{(error as Error).message}</p>
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && vexDocs.length === 0 && (
        <div className="rounded-lg border border-border bg-card p-12 text-center">
          <Shield className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <h3 className="text-lg font-semibold mb-2">No VEX documents yet</h3>
          <p className="text-muted-foreground mb-6">
            Create your first VEX document to track vulnerability assessments
          </p>
          <Link
            href="/dashboard/vex/new"
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium"
          >
            <Plus className="h-4 w-4" />
            Create VEX
          </Link>
        </div>
      )}

      {/* VEX Documents Grid */}
      {!isLoading && !error && vexDocs.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {vexDocs.map((vex) => (
            <div
              key={vex.vex_id}
              className="rounded-lg border border-border bg-card p-6 shadow-sm hover:shadow-md transition-all hover:border-primary/50"
            >
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-primary/10">
                    <FileText className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <Link
                      href={`/dashboard/vex/${vex.vex_id}`}
                      className="font-mono text-sm font-medium hover:underline"
                    >
                      {vex.vex_id}
                    </Link>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {format(new Date(vex.created_at), "PPp")}
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => setDeleteConfirm(vex.vex_id)}
                  className="p-1.5 hover:bg-destructive/10 rounded transition-colors text-muted-foreground hover:text-destructive"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                  <div>
                    <p className="text-sm font-medium">Vulnerabilities</p>
                    <p className="text-xs text-muted-foreground">Assessed</p>
                  </div>
                  <p className="text-2xl font-bold">{vex.vulnerabilities_count}</p>
                </div>

                {vex.metadata?.component && (
                  <div className="p-3 rounded-lg bg-muted/30">
                    <p className="text-xs text-muted-foreground mb-1">Component</p>
                    <p className="text-sm font-medium truncate">
                      {vex.metadata.component.name}
                    </p>
                    {vex.metadata.component.version && (
                      <p className="text-xs text-muted-foreground">
                        v{vex.metadata.component.version}
                      </p>
                    )}
                  </div>
                )}

                <div className="pt-3 border-t border-border">
                  <Link
                    href={`/dashboard/vex/${vex.vex_id}`}
                    className="text-sm text-primary hover:underline font-medium"
                  >
                    View Details →
                  </Link>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-card border border-border rounded-lg max-w-md w-full p-6">
            <h2 className="text-xl font-bold mb-2">Delete VEX Document</h2>
            <p className="text-muted-foreground mb-6">
              Are you sure you want to delete this VEX document? This action cannot be undone.
            </p>
            <div className="flex items-center justify-end gap-3">
              <button
                onClick={() => setDeleteConfirm(null)}
                className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg transition-colors"
                disabled={deleteMutation.isPending}
              >
                Cancel
              </button>
              <button
                onClick={() => handleDelete(deleteConfirm)}
                disabled={deleteMutation.isPending}
                className="px-4 py-2 bg-destructive text-destructive-foreground rounded-lg hover:bg-destructive/90 transition-colors text-sm font-medium disabled:opacity-50"
              >
                {deleteMutation.isPending ? "Deleting..." : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
