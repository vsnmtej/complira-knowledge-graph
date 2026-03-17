"use client";

import { useState } from "react";
import { rotateToken } from "@/lib/api/tokens";

interface RotateTokenDialogProps {
  tokenId: string;
  onClose: () => void;
  onSuccess: (newToken: string, prefix: string, expiresAt: string) => void;
}

const GRACE_PERIOD_OPTIONS = [
  { value: 6, label: "6 hours" },
  { value: 12, label: "12 hours" },
  { value: 24, label: "24 hours (recommended)" },
  { value: 48, label: "48 hours (2 days)" },
  { value: 168, label: "7 days" },
];

export default function RotateTokenDialog({
  tokenId,
  onClose,
  onSuccess,
}: RotateTokenDialogProps) {
  const [gracePeriodHours, setGracePeriodHours] = useState(24);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const response = await rotateToken(tokenId, gracePeriodHours);

      onSuccess(
        response.new_token,
        response.token_prefix,
        response.expires_at
      );
    } catch (err: any) {
      setError(err.message || "Failed to rotate token");
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="bg-slate-800 border border-slate-700 rounded-lg max-w-2xl w-full">
        {/* Header */}
        <div className="p-6 border-b border-slate-700">
          <h2 className="text-2xl font-bold text-white">Rotate Token Secret</h2>
          <p className="text-slate-400 mt-1">
            Generate a new secret for this token
          </p>
        </div>

        {/* Warning Banner */}
        <div className="bg-yellow-900/30 border-b border-yellow-700/50 p-4">
          <div className="flex items-start gap-3">
            <div className="text-2xl">⚠️</div>
            <div className="flex-1 text-sm">
              <p className="text-yellow-300 font-medium">
                This will generate a new token secret
              </p>
              <p className="text-yellow-200/90 mt-1">
                The old token will remain valid during the grace period, giving
                you time to update your integrations without downtime.
              </p>
            </div>
          </div>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          {error && (
            <div className="bg-red-900/50 border border-red-700 rounded p-3 text-red-200 text-sm">
              {error}
            </div>
          )}

          {/* Grace Period */}
          <div>
            <label
              htmlFor="gracePeriod"
              className="block text-sm font-medium text-slate-300 mb-2"
            >
              Grace Period
            </label>
            <select
              id="gracePeriod"
              value={gracePeriodHours}
              onChange={(e) => setGracePeriodHours(Number(e.target.value))}
              className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={loading}
            >
              {GRACE_PERIOD_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <p className="text-xs text-slate-400 mt-2">
              How long the old token will remain valid after rotation
            </p>
          </div>

          {/* Info Box */}
          <div className="bg-slate-900 border border-slate-700 rounded-md p-4 space-y-3">
            <div>
              <h3 className="text-sm font-semibold text-white mb-2">
                What happens when you rotate:
              </h3>
              <ul className="text-xs text-slate-300 space-y-2">
                <li className="flex items-start gap-2">
                  <span className="text-blue-400 mt-0.5">1.</span>
                  <span>
                    A new token secret is generated and the hash is updated
                  </span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-blue-400 mt-0.5">2.</span>
                  <span>
                    Both old and new tokens work during the grace period (
                    {gracePeriodHours}h)
                  </span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-blue-400 mt-0.5">3.</span>
                  <span>
                    You have time to update your integrations without downtime
                  </span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-blue-400 mt-0.5">4.</span>
                  <span>
                    After {gracePeriodHours}h, only the new token will work
                  </span>
                </li>
              </ul>
            </div>
          </div>

          {/* Best Practices */}
          <div className="bg-blue-900/30 border border-blue-700 rounded-md p-4">
            <h3 className="text-sm font-semibold text-blue-300 mb-2">
              Recommended Rotation Schedule
            </h3>
            <ul className="text-xs text-blue-200/90 space-y-1">
              <li>• Production tokens: Every 90 days</li>
              <li>• Development tokens: Every 180 days</li>
              <li>• After suspected compromise: Immediately</li>
              <li>• After team member departure: Within 24 hours</li>
            </ul>
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
              disabled={loading}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 disabled:cursor-not-allowed text-white font-medium rounded-md transition-colors"
            >
              {loading ? "Rotating..." : "Rotate Token"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
