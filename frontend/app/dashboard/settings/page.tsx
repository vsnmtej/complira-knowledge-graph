"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  Settings,
  Key,
  Plus,
  Ban,
  AlertCircle,
  Copy,
  Check,
  ShieldAlert,
  Building2,
} from "lucide-react";
import {
  listAPIKeys,
  createAPIKey,
  revokeAPIKey,
  type APIKey,
  type CreateAPIKeyRequest,
} from "@/lib/api/account";
import { format } from "date-fns";

export default function SettingsPage() {
  const { data: session } = useSession();
  const queryClient = useQueryClient();

  // Modal state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState(false);
  const [revokeTarget, setRevokeTarget] = useState<{
    key_id: string;
    name: string;
  } | null>(null);
  const [revokeReason, setRevokeReason] = useState("");

  // Create form state
  const [createName, setCreateName] = useState("");
  const [createDescription, setCreateDescription] = useState("");
  const [createExpiresDays, setCreateExpiresDays] = useState("");

  // Fetch API keys
  const {
    data: keysData,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["account-api-keys"],
    queryFn: () => listAPIKeys(),
  });

  // Create mutation
  const createMutation = useMutation({
    mutationFn: (data: CreateAPIKeyRequest) => createAPIKey(data),
    onSuccess: (response) => {
      setCreatedKey(response.data.api_key);
      setShowCreateModal(false);
      setCreateName("");
      setCreateDescription("");
      setCreateExpiresDays("");
      queryClient.invalidateQueries({ queryKey: ["account-api-keys"] });
    },
  });

  // Revoke mutation
  const revokeMutation = useMutation({
    mutationFn: ({ keyId, reason }: { keyId: string; reason?: string }) =>
      revokeAPIKey(keyId, reason),
    onSuccess: () => {
      setRevokeTarget(null);
      setRevokeReason("");
      queryClient.invalidateQueries({ queryKey: ["account-api-keys"] });
    },
  });

  const handleCreate = () => {
    const data: CreateAPIKeyRequest = {
      name: createName,
    };
    if (createDescription.trim()) {
      data.description = createDescription.trim();
    }
    if (createExpiresDays && parseInt(createExpiresDays) > 0) {
      data.expires_days = parseInt(createExpiresDays);
    }
    createMutation.mutate(data);
  };

  const handleCopyKey = async () => {
    if (createdKey) {
      await navigator.clipboard.writeText(createdKey);
      setCopiedKey(true);
      setTimeout(() => setCopiedKey(false), 2000);
    }
  };

  const handleRevoke = () => {
    if (revokeTarget) {
      revokeMutation.mutate({
        keyId: revokeTarget.key_id,
        reason: revokeReason.trim() || undefined,
      });
    }
  };

  const keys = keysData?.data?.keys ?? [];

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Account Settings</h1>
        <p className="text-muted-foreground mt-1">
          Manage your API keys and view organization details
        </p>
      </div>

      {/* Section 1: API Keys */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Key className="h-5 w-5 text-primary" />
            <h2 className="text-xl font-semibold">API Keys</h2>
          </div>
          <button
            onClick={() => setShowCreateModal(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium"
          >
            <Plus className="h-4 w-4" />
            Create API Key
          </button>
        </div>

        <p className="text-sm text-muted-foreground">
          Legacy API keys for direct API access. These are separate from JWT
          tokens used by the web application.
        </p>

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
              <p className="font-medium">Failed to load API keys</p>
            </div>
            <p className="text-sm text-muted-foreground mt-1">
              {(error as Error).message}
            </p>
          </div>
        )}

        {/* Empty State */}
        {!isLoading && !error && keys.length === 0 && (
          <div className="rounded-lg border border-border bg-card p-12 text-center">
            <Key className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-lg font-semibold mb-2">No API keys yet</h3>
            <p className="text-muted-foreground mb-6">
              Create your first API key for programmatic access to the Complira
              API
            </p>
            <button
              onClick={() => setShowCreateModal(true)}
              className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium"
            >
              <Plus className="h-4 w-4" />
              Create API Key
            </button>
          </div>
        )}

        {/* Keys Table */}
        {!isLoading && !error && keys.length > 0 && (
          <div className="rounded-lg border border-border bg-card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-muted/50 border-b border-border">
                  <tr>
                    <th className="px-4 py-3 text-left text-sm font-medium">
                      Name
                    </th>
                    <th className="px-4 py-3 text-left text-sm font-medium">
                      Prefix
                    </th>
                    <th className="px-4 py-3 text-left text-sm font-medium">
                      Created
                    </th>
                    <th className="px-4 py-3 text-left text-sm font-medium">
                      Expires
                    </th>
                    <th className="px-4 py-3 text-left text-sm font-medium">
                      Last Used
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
                  {keys.map((key: APIKey) => (
                    <tr
                      key={key.key_id}
                      className="hover:bg-muted/30 transition-colors"
                    >
                      <td className="px-4 py-3">
                        <div>
                          <div className="font-medium">{key.name}</div>
                          {key.description && (
                            <div className="text-sm text-muted-foreground">
                              {key.description}
                            </div>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <code className="text-sm bg-muted px-2 py-1 rounded">
                          {key.key_prefix}...
                        </code>
                      </td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">
                        {format(new Date(key.created_at), "PP")}
                      </td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">
                        {key.expires_at
                          ? format(new Date(key.expires_at), "PP")
                          : "Never"}
                      </td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">
                        {key.last_used_at
                          ? format(new Date(key.last_used_at), "PP")
                          : "Never"}
                      </td>
                      <td className="px-4 py-3">
                        {key.revoked ? (
                          <span className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded bg-destructive/10 text-destructive">
                            <Ban className="h-3 w-3" />
                            Revoked
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded bg-green-500/10 text-green-500">
                            Active
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end gap-2">
                          {!key.revoked && (
                            <button
                              onClick={() =>
                                setRevokeTarget({
                                  key_id: key.key_id,
                                  name: key.name,
                                })
                              }
                              className="p-1.5 hover:bg-destructive/10 rounded transition-colors"
                              title="Revoke API key"
                            >
                              <Ban className="h-4 w-4 text-muted-foreground hover:text-destructive" />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Summary */}
            <div className="px-4 py-3 border-t border-border bg-muted/20">
              <p className="text-sm text-muted-foreground">
                {keysData?.data?.active ?? 0} active of {keysData?.data?.total ?? 0} total keys
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Section 2: Organization Info */}
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Building2 className="h-5 w-5 text-primary" />
          <h2 className="text-xl font-semibold">Organization</h2>
        </div>

        <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
              <p className="text-sm text-muted-foreground mb-1">
                Organization Name
              </p>
              <p className="font-medium">
                {session?.user?.organizationName ?? "N/A"}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground mb-1">Tier</p>
              <span className="text-sm px-2 py-0.5 rounded bg-primary/10 text-primary font-medium">
                {session?.user?.tier ?? "N/A"}
              </span>
            </div>
            <div>
              <p className="text-sm text-muted-foreground mb-1">Frameworks</p>
              <div className="flex flex-wrap gap-1">
                {(session?.user as any)?.frameworks ? (
                  ((session?.user as any).frameworks as string[]).map(
                    (fw: string) => (
                      <span
                        key={fw}
                        className="text-xs px-2 py-0.5 rounded bg-secondary text-secondary-foreground"
                      >
                        {fw}
                      </span>
                    )
                  )
                ) : (
                  <span className="text-sm text-muted-foreground">
                    No frameworks configured
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Created Key Display Modal */}
      {createdKey && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-card border border-border rounded-lg shadow-lg p-6 max-w-lg w-full mx-4 space-y-4">
            <div className="flex items-center gap-2">
              <ShieldAlert className="h-5 w-5 text-yellow-500" />
              <h3 className="text-lg font-semibold">API Key Created</h3>
            </div>

            <div className="rounded-lg border border-yellow-500/50 bg-yellow-500/10 p-4">
              <p className="text-sm font-medium text-yellow-600 dark:text-yellow-400 mb-2">
                Save this key now. You will not be able to see it again.
              </p>
              <div className="flex items-center gap-2">
                <code className="flex-1 text-sm bg-muted p-3 rounded font-mono break-all">
                  {createdKey}
                </code>
                <button
                  onClick={handleCopyKey}
                  className="p-2 hover:bg-muted rounded transition-colors shrink-0"
                  title="Copy to clipboard"
                >
                  {copiedKey ? (
                    <Check className="h-4 w-4 text-green-500" />
                  ) : (
                    <Copy className="h-4 w-4 text-muted-foreground" />
                  )}
                </button>
              </div>
            </div>

            <div className="flex justify-end">
              <button
                onClick={() => {
                  setCreatedKey(null);
                  setCopiedKey(false);
                }}
                className="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create API Key Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-card border border-border rounded-lg shadow-lg p-6 max-w-md w-full mx-4 space-y-4">
            <h3 className="text-lg font-semibold">Create API Key</h3>

            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium mb-1">
                  Name <span className="text-destructive">*</span>
                </label>
                <input
                  type="text"
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                  placeholder="e.g., Production Server"
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-1">
                  Description
                </label>
                <input
                  type="text"
                  value={createDescription}
                  onChange={(e) => setCreateDescription(e.target.value)}
                  placeholder="Optional description"
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-1">
                  Expires in (days)
                </label>
                <input
                  type="number"
                  value={createExpiresDays}
                  onChange={(e) => setCreateExpiresDays(e.target.value)}
                  placeholder="Leave empty for no expiration"
                  min="1"
                  max="365"
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                />
                <p className="text-xs text-muted-foreground mt-1">
                  1-365 days. Leave empty for a key that never expires.
                </p>
              </div>
            </div>

            {createMutation.isError && (
              <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3">
                <div className="flex items-center gap-2 text-destructive text-sm">
                  <AlertCircle className="h-4 w-4" />
                  <p>{(createMutation.error as Error).message}</p>
                </div>
              </div>
            )}

            <div className="flex justify-end gap-3">
              <button
                onClick={() => {
                  setShowCreateModal(false);
                  setCreateName("");
                  setCreateDescription("");
                  setCreateExpiresDays("");
                  createMutation.reset();
                }}
                className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={
                  !createName.trim() ||
                  createName.trim().length < 3 ||
                  createMutation.isPending
                }
                className="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed text-sm"
              >
                {createMutation.isPending ? "Creating..." : "Create Key"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Revoke Confirmation Modal */}
      {revokeTarget && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-card border border-border rounded-lg shadow-lg p-6 max-w-md w-full mx-4 space-y-4">
            <h3 className="text-lg font-semibold">Revoke API Key</h3>
            <p className="text-sm text-muted-foreground">
              Are you sure you want to revoke{" "}
              <span className="font-medium text-foreground">
                &quot;{revokeTarget.name}&quot;
              </span>
              ? This action cannot be undone.
            </p>

            <div>
              <label className="block text-sm font-medium mb-1">
                Reason (optional)
              </label>
              <input
                type="text"
                value={revokeReason}
                onChange={(e) => setRevokeReason(e.target.value)}
                placeholder="e.g., Key compromised"
                className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
              />
            </div>

            {revokeMutation.isError && (
              <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3">
                <div className="flex items-center gap-2 text-destructive text-sm">
                  <AlertCircle className="h-4 w-4" />
                  <p>{(revokeMutation.error as Error).message}</p>
                </div>
              </div>
            )}

            <div className="flex justify-end gap-3">
              <button
                onClick={() => {
                  setRevokeTarget(null);
                  setRevokeReason("");
                  revokeMutation.reset();
                }}
                className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleRevoke}
                disabled={revokeMutation.isPending}
                className="px-4 py-2 bg-destructive text-destructive-foreground rounded-lg hover:bg-destructive/90 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed text-sm"
              >
                {revokeMutation.isPending ? "Revoking..." : "Revoke Key"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
