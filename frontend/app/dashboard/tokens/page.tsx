"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, RefreshCw, Ban, Trash2, Key, AlertCircle } from "lucide-react";
import { listTokens, revokeToken, deleteToken, type APIToken } from "@/lib/api/tokens";
import { format } from "date-fns";
import CreateTokenDialog from "@/components/tokens/CreateTokenDialog";
import ShowTokenDialog from "@/components/tokens/ShowTokenDialog";
import RotateTokenDialog from "@/components/tokens/RotateTokenDialog";

export default function TokensPage() {
  const [includeRevoked, setIncludeRevoked] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showTokenModal, setShowTokenModal] = useState(false);
  const [rotateTokenId, setRotateTokenId] = useState<string | null>(null);
  const [newToken, setNewToken] = useState<{
    token: string;
    tokenId: string;
    prefix: string;
    expiresAt: string;
  } | null>(null);
  const queryClient = useQueryClient();

  // Fetch tokens
  const { data, isLoading, error } = useQuery({
    queryKey: ["tokens", includeRevoked],
    queryFn: () => listTokens({ include_revoked: includeRevoked }),
  });

  // Revoke mutation
  const revokeMutation = useMutation({
    mutationFn: revokeToken,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tokens"] });
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: deleteToken,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tokens"] });
    },
  });

  const handleRevoke = async (tokenId: string, tokenName: string) => {
    if (confirm(`Are you sure you want to revoke "${tokenName}"? This action cannot be undone.`)) {
      try {
        await revokeMutation.mutateAsync(tokenId);
      } catch (error: any) {
        alert(`Failed to revoke token: ${error.message}`);
      }
    }
  };

  const handleDelete = async (tokenId: string, tokenName: string) => {
    if (confirm(`Are you sure you want to permanently delete "${tokenName}"? This action cannot be undone.`)) {
      try {
        await deleteMutation.mutateAsync(tokenId);
      } catch (error: any) {
        alert(`Failed to delete token: ${error.message}`);
      }
    }
  };

  const handleCreateSuccess = (
    token: string,
    tokenId: string,
    prefix: string,
    expiresAt: string
  ) => {
    // Store the new token details
    setNewToken({ token, tokenId, prefix, expiresAt });
    // Close create modal
    setShowCreateModal(false);
    // Show token display modal
    setShowTokenModal(true);
    // Refresh the token list
    queryClient.invalidateQueries({ queryKey: ["tokens"] });
  };

  const handleShowTokenClose = () => {
    setShowTokenModal(false);
    setNewToken(null);
  };

  const handleRotateSuccess = (
    newToken: string,
    prefix: string,
    expiresAt: string
  ) => {
    // Store the new token details (tokenId is same as rotateTokenId)
    setNewToken({
      token: newToken,
      tokenId: rotateTokenId!,
      prefix,
      expiresAt,
    });
    // Close rotate modal
    setRotateTokenId(null);
    // Show token display modal
    setShowTokenModal(true);
    // Refresh the token list
    queryClient.invalidateQueries({ queryKey: ["tokens"] });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">API Tokens</h1>
          <p className="text-muted-foreground mt-1">
            Manage API tokens for programmatic access to Complira
          </p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium"
        >
          <Plus className="h-4 w-4" />
          Create Token
        </button>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={includeRevoked}
            onChange={(e) => setIncludeRevoked(e.target.checked)}
            className="rounded border-border"
          />
          <span className="text-muted-foreground">Include revoked tokens</span>
        </label>
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
            <p className="font-medium">Failed to load tokens</p>
          </div>
          <p className="text-sm text-muted-foreground mt-1">{(error as Error).message}</p>
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && data?.tokens.length === 0 && (
        <div className="rounded-lg border border-border bg-card p-12 text-center">
          <Key className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <h3 className="text-lg font-semibold mb-2">No API tokens yet</h3>
          <p className="text-muted-foreground mb-6">
            Create your first API token to start using the Complira API
          </p>
          <button
            onClick={() => setShowCreateModal(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium"
          >
            <Plus className="h-4 w-4" />
            Create Token
          </button>
        </div>
      )}

      {/* Tokens Table */}
      {!isLoading && !error && data && data.tokens.length > 0 && (
        <div className="rounded-lg border border-border bg-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-muted/50 border-b border-border">
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-medium">Name</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Prefix</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Scopes</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Last Used</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Expires</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Status</th>
                  <th className="px-4 py-3 text-right text-sm font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.tokens.map((token: APIToken) => (
                  <tr key={token.id} className="hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3">
                      <div>
                        <div className="font-medium">{token.name}</div>
                        {token.description && (
                          <div className="text-sm text-muted-foreground">{token.description}</div>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <code className="text-sm bg-muted px-2 py-1 rounded">{token.token_prefix}</code>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {token.scopes.map((scope) => (
                          <span
                            key={scope}
                            className="text-xs px-2 py-0.5 rounded bg-primary/10 text-primary"
                          >
                            {scope}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-sm text-muted-foreground">
                      {token.last_used ? format(new Date(token.last_used), "PP") : "Never"}
                    </td>
                    <td className="px-4 py-3 text-sm text-muted-foreground">
                      {token.expires_at ? format(new Date(token.expires_at), "PP") : "—"}
                    </td>
                    <td className="px-4 py-3">
                      {token.revoked ? (
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
                        {!token.revoked && (
                          <>
                            <button
                              onClick={() => setRotateTokenId(token.id)}
                              className="p-1.5 hover:bg-muted rounded transition-colors"
                              title="Rotate token secret"
                            >
                              <RefreshCw className="h-4 w-4 text-muted-foreground hover:text-foreground" />
                            </button>
                            <button
                              onClick={() => handleRevoke(token.id, token.name)}
                              disabled={revokeMutation.isPending}
                              className="p-1.5 hover:bg-muted rounded transition-colors"
                              title="Revoke token"
                            >
                              <Ban className="h-4 w-4 text-muted-foreground hover:text-foreground" />
                            </button>
                          </>
                        )}
                        <button
                          onClick={() => handleDelete(token.id, token.name)}
                          disabled={deleteMutation.isPending}
                          className="p-1.5 hover:bg-destructive/10 rounded transition-colors"
                          title="Delete token"
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination Info */}
          <div className="px-4 py-3 border-t border-border bg-muted/20">
            <p className="text-sm text-muted-foreground">
              Showing {data.tokens.length} of {data.total} tokens
            </p>
          </div>
        </div>
      )}

      {/* Create Token Modal */}
      {showCreateModal && (
        <CreateTokenDialog
          onClose={() => setShowCreateModal(false)}
          onSuccess={handleCreateSuccess}
        />
      )}

      {/* Rotate Token Modal */}
      {rotateTokenId && (
        <RotateTokenDialog
          tokenId={rotateTokenId}
          onClose={() => setRotateTokenId(null)}
          onSuccess={handleRotateSuccess}
        />
      )}

      {/* Show Token Modal */}
      {showTokenModal && newToken && (
        <ShowTokenDialog
          token={newToken.token}
          tokenId={newToken.tokenId}
          prefix={newToken.prefix}
          expiresAt={newToken.expiresAt}
          onClose={handleShowTokenClose}
        />
      )}
    </div>
  );
}
