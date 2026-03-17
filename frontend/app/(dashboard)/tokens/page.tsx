"use client";

export default function TokensPage() {
  return (
    <div className="max-w-7xl">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white">API Tokens</h1>
        <p className="text-slate-400 mt-2">
          Manage API tokens for programmatic access to Complira
        </p>
      </div>

      {/* Placeholder content */}
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-12 text-center">
        <p className="text-slate-400 mb-4">No API tokens yet</p>
        <p className="text-sm text-slate-500">
          Token management UI components will be implemented here
        </p>
        <button
          className="mt-6 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-md transition-colors"
          onClick={() => alert("Token creation modal will open here")}
        >
          Create your first token
        </button>
      </div>
    </div>
  );
}
