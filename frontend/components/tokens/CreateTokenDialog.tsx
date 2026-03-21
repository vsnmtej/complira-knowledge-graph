"use client";

import { useState } from "react";
import { createToken } from "@/lib/api/tokens";

interface CreateTokenDialogProps {
  onClose: () => void;
  onSuccess: (
    token: string,
    tokenId: string,
    prefix: string,
    expiresAt: string
  ) => void;
}

const AVAILABLE_SCOPES = [
  {
    id: "scan:write",
    name: "Upload Scans",
    description: "Upload SBOM/SARIF files",
  },
  {
    id: "scan:read",
    name: "Read Scans",
    description: "Read scan results and analysis",
  },
  {
    id: "reference:read",
    name: "Query Reference Data",
    description: "Query CVEs, NIST controls, ATT&CK, etc.",
  },
  {
    id: "vex:generate",
    name: "Generate VEX",
    description: "Generate VEX documents",
  },
];

export default function CreateTokenDialog({
  onClose,
  onSuccess,
}: CreateTokenDialogProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [scopes, setScopes] = useState<string[]>(["scan:write", "reference:read"]);
  const [rateLimit, setRateLimit] = useState(1000);
  const [expiresInDays, setExpiresInDays] = useState(365);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!name.trim()) {
      setError("Token name is required");
      return;
    }

    if (scopes.length === 0) {
      setError("At least one scope must be selected");
      return;
    }

    setLoading(true);

    try {
      const response = await createToken({
        name: name.trim(),
        description: description.trim() || undefined,
        scopes,
        rate_limit: rateLimit,
        expires_in_days: expiresInDays,
      });

      onSuccess(
        response.token,
        response.token_id,
        response.token_prefix,
        response.expires_at
      );
    } catch (err: any) {
      setError(err.message || "Failed to create token");
      setLoading(false);
    }
  };

  const toggleScope = (scopeId: string) => {
    setScopes((prev) =>
      prev.includes(scopeId)
        ? prev.filter((s) => s !== scopeId)
        : [...prev, scopeId]
    );
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="bg-slate-800 border border-slate-700 rounded-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="p-6 border-b border-slate-700">
          <h2 className="text-2xl font-bold text-white">Create API Token</h2>
          <p className="text-slate-400 mt-1">
            Generate a new token for programmatic access
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          {error && (
            <div className="bg-red-900/50 border border-red-700 rounded p-3 text-red-200 text-sm">
              {error}
            </div>
          )}

          {/* Name */}
          <div>
            <label
              htmlFor="name"
              className="block text-sm font-medium text-slate-300 mb-2"
            >
              Token Name <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., CI/CD Pipeline Token"
              className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-md text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={loading}
              required
            />
          </div>

          {/* Description */}
          <div>
            <label
              htmlFor="description"
              className="block text-sm font-medium text-slate-300 mb-2"
            >
              Description <span className="text-slate-500">(Optional)</span>
            </label>
            <textarea
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g., GitHub Actions workflow for main repository"
              rows={3}
              className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-md text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={loading}
            />
          </div>

          {/* Scopes */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-3">
              Scopes <span className="text-red-400">*</span>
            </label>
            <div className="space-y-3">
              {AVAILABLE_SCOPES.map((scope) => (
                <label
                  key={scope.id}
                  className="flex items-start gap-3 p-3 bg-slate-900 border border-slate-700 rounded-md hover:border-slate-600 cursor-pointer transition-colors"
                >
                  <input
                    type="checkbox"
                    checked={scopes.includes(scope.id)}
                    onChange={() => toggleScope(scope.id)}
                    className="mt-0.5 rounded border-slate-600 bg-slate-800 text-blue-600 focus:ring-blue-500 focus:ring-offset-slate-900"
                    disabled={loading}
                  />
                  <div className="flex-1">
                    <div className="text-sm font-medium text-white">
                      {scope.name}
                    </div>
                    <div className="text-xs text-slate-400 mt-0.5">
                      {scope.description}
                    </div>
                    <code className="text-xs text-slate-500 mt-1 block">
                      {scope.id}
                    </code>
                  </div>
                </label>
              ))}
            </div>
            {scopes.length === 0 && (
              <p className="text-xs text-red-400 mt-2">
                Select at least one scope
              </p>
            )}
          </div>

          {/* Rate Limit */}
          <div>
            <label
              htmlFor="rateLimit"
              className="block text-sm font-medium text-slate-300 mb-2"
            >
              Rate Limit (requests per hour)
            </label>
            <div className="flex items-center gap-4">
              <input
                type="range"
                id="rateLimit"
                min="100"
                max="10000"
                step="100"
                value={rateLimit}
                onChange={(e) => setRateLimit(Number(e.target.value))}
                className="flex-1"
                disabled={loading}
              />
              <span className="text-white font-mono w-24 text-right">
                {rateLimit.toLocaleString()}/hr
              </span>
            </div>
          </div>

          {/* Expiration */}
          <div>
            <label
              htmlFor="expires"
              className="block text-sm font-medium text-slate-300 mb-2"
            >
              Expires In
            </label>
            <select
              id="expires"
              value={expiresInDays}
              onChange={(e) => setExpiresInDays(Number(e.target.value))}
              className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={loading}
            >
              <option value={30}>30 days</option>
              <option value={90}>90 days</option>
              <option value={180}>180 days</option>
              <option value={365}>1 year</option>
              <option value={730}>2 years</option>
              <option value={3650}>10 years (max)</option>
            </select>
          </div>

          {/* Actions */}
          <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-700">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-slate-300 hover:text-white transition-colors"
              disabled={loading}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !name.trim() || scopes.length === 0}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 disabled:cursor-not-allowed text-white font-medium rounded-md transition-colors"
            >
              {loading ? "Creating..." : "Create Token"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
