"use client";

import { useState } from "react";

interface ShowTokenDialogProps {
  token: string;
  tokenId: string;
  prefix: string;
  expiresAt: string;
  onClose: () => void;
}

export default function ShowTokenDialog({
  token,
  tokenId,
  prefix,
  expiresAt,
  onClose,
}: ShowTokenDialogProps) {
  const [copied, setCopied] = useState(false);
  const [confirmed, setConfirmed] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(token);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      alert("Failed to copy to clipboard");
    }
  };

  const handleClose = () => {
    if (!confirmed) {
      if (
        confirm(
          "Have you saved this token? You won't be able to see it again.\n\nClick OK to confirm you've saved it."
        )
      ) {
        onClose();
      }
    } else {
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 bg-black/75 flex items-center justify-center p-4 z-50">
      <div className="bg-slate-800 border-2 border-yellow-600 rounded-lg max-w-2xl w-full">
        {/* Warning Header */}
        <div className="bg-yellow-900/30 border-b-2 border-yellow-600 p-6">
          <div className="flex items-start gap-4">
            <div className="text-4xl">⚠️</div>
            <div className="flex-1">
              <h2 className="text-2xl font-bold text-yellow-300">
                Important: Save This Token Now!
              </h2>
              <p className="text-yellow-200/90 mt-2 font-medium">
                This is the ONLY time you&apos;ll see this token. Copy it now and
                store it securely. Once you close this dialog, the token cannot
                be retrieved.
              </p>
            </div>
          </div>
        </div>

        {/* Token Display */}
        <div className="p-6 space-y-6">
          {/* Token Secret */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Token Secret
            </label>
            <div className="flex gap-2">
              <div className="flex-1 px-4 py-3 bg-slate-900 border-2 border-blue-500 rounded-md font-mono text-sm text-white break-all select-all">
                {token}
              </div>
              <button
                onClick={handleCopy}
                className={`px-4 py-2 rounded-md font-medium transition-colors ${
                  copied
                    ? "bg-green-600 text-white"
                    : "bg-blue-600 hover:bg-blue-700 text-white"
                }`}
              >
                {copied ? "✓ Copied!" : "📋 Copy"}
              </button>
            </div>
            <p className="text-xs text-slate-400 mt-2">
              Click the token to select all, then copy
            </p>
          </div>

          {/* Token Details */}
          <div className="grid grid-cols-2 gap-4 p-4 bg-slate-900 rounded-md border border-slate-700">
            <div>
              <div className="text-xs text-slate-400">Token ID</div>
              <div className="text-sm text-white font-mono mt-1">
                {tokenId}
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-400">Prefix (for UI)</div>
              <div className="text-sm text-white font-mono mt-1">
                {prefix}...
              </div>
            </div>
            <div className="col-span-2">
              <div className="text-xs text-slate-400">Expires</div>
              <div className="text-sm text-white mt-1">
                {new Date(expiresAt).toLocaleString()}
              </div>
            </div>
          </div>

          {/* Security Warning */}
          <div className="bg-red-900/30 border border-red-700 rounded-md p-4">
            <h3 className="text-sm font-semibold text-red-300 mb-2">
              Security Best Practices
            </h3>
            <ul className="text-xs text-red-200/90 space-y-1">
              <li>• Never commit this token to version control</li>
              <li>• Store it in environment variables or a secrets manager</li>
              <li>
                • Rotate regularly (every 90 days recommended for production)
              </li>
              <li>• Revoke immediately if compromised</li>
              <li>• Use different tokens for different environments</li>
            </ul>
          </div>

          {/* Confirmation */}
          <label className="flex items-start gap-3 p-4 bg-slate-900 border border-slate-700 rounded-md cursor-pointer hover:border-slate-600">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
              className="mt-0.5 rounded border-slate-600 bg-slate-800 text-blue-600 focus:ring-blue-500 focus:ring-offset-slate-900"
            />
            <div className="text-sm">
              <div className="text-white font-medium">
                I&apos;ve copied and securely stored this token
              </div>
              <div className="text-slate-400 text-xs mt-1">
                I understand I won&apos;t be able to see it again
              </div>
            </div>
          </label>

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-4 border-t border-slate-700">
            {confirmed ? (
              <button
                onClick={onClose}
                className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-md transition-colors"
              >
                Close
              </button>
            ) : (
              <button
                onClick={handleClose}
                className="px-6 py-2 bg-slate-700 hover:bg-slate-600 text-white font-medium rounded-md transition-colors"
              >
                I&apos;ll Copy It Later...
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
