"use client";

import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Upload, FileSearch, AlertCircle, CheckCircle2, Clock, XCircle, X } from "lucide-react";
import { listScans, ingestScan, type ScanSession, type ScanIngestRequest } from "@/lib/api/scans";
import { format } from "date-fns";
import Link from "next/link";

export default function ScansPage() {
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [scanType, setScanType] = useState<"sast" | "dast" | "sca" | "container" | "sbom" | "iac">("sbom");
  const [fileFormat, setFileFormat] = useState<"sarif" | "cyclonedx" | "spdx">("cyclonedx");
  const [metadata, setMetadata] = useState({
    repository: "",
    branch: "",
    commit: "",
  });
  const queryClient = useQueryClient();

  // Fetch scans
  const { data, isLoading, error } = useQuery({
    queryKey: ["scans"],
    queryFn: () => listScans(),
  });

  const scans = data?.data || [];

  // Upload mutation
  const uploadMutation = useMutation({
    mutationFn: async (request: ScanIngestRequest) => {
      return ingestScan(request);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scans"] });
      setShowUploadModal(false);
      resetForm();
    },
  });

  const resetForm = () => {
    setUploadFile(null);
    setScanType("sbom");
    setFileFormat("cyclonedx");
    setMetadata({ repository: "", branch: "", commit: "" });
  };

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    const files = e.dataTransfer.files;
    if (files && files[0]) {
      handleFileSelect(files[0]);
    }
  }, []);

  const handleFileSelect = (file: File) => {
    setUploadFile(file);

    // Auto-detect format based on file extension or content
    if (file.name.endsWith('.json')) {
      // Could be CycloneDX, SPDX, or SARIF
      // Read first few bytes to detect
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const content = e.target?.result as string;
          const json = JSON.parse(content);

          if (json.$schema?.includes('sarif')) {
            setFileFormat('sarif');
            setScanType('sast');
          } else if (json.bomFormat === 'CycloneDX') {
            setFileFormat('cyclonedx');
            setScanType('sbom');
          } else if (json.spdxVersion) {
            setFileFormat('spdx');
            setScanType('sbom');
          }
        } catch (err) {
          console.error('Failed to parse file:', err);
        }
      };
      reader.readAsText(file.slice(0, 2000)); // Read first 2KB
    }
  };

  const handleUpload = async () => {
    if (!uploadFile) return;

    const reader = new FileReader();
    reader.onload = async (e) => {
      try {
        const content = e.target?.result as string;
        const payload = JSON.parse(content);

        const request: ScanIngestRequest = {
          format: fileFormat,
          scan_type: scanType,
          payload,
          metadata: metadata.repository || metadata.branch || metadata.commit
            ? metadata
            : undefined,
        };

        await uploadMutation.mutateAsync(request);
      } catch (err) {
        console.error('Failed to parse or upload file:', err);
      }
    };
    reader.readAsText(uploadFile);
  };

  const getSeverityColor = (severity: string) => {
    switch (severity?.toUpperCase()) {
      case "CRITICAL":
        return "text-red-600 bg-red-100";
      case "HIGH":
        return "text-orange-600 bg-orange-100";
      case "MEDIUM":
        return "text-yellow-600 bg-yellow-100";
      case "LOW":
        return "text-blue-600 bg-blue-100";
      default:
        return "text-gray-600 bg-gray-100";
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "completed":
        return <CheckCircle2 className="h-4 w-4 text-green-500" />;
      case "processing":
        return <Clock className="h-4 w-4 text-blue-500" />;
      case "failed":
        return <XCircle className="h-4 w-4 text-red-500" />;
      default:
        return <Clock className="h-4 w-4 text-gray-500" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">SBOM Scans</h1>
          <p className="text-muted-foreground mt-1">
            Upload and analyze SBOM and SARIF scan results
          </p>
        </div>
        <button
          onClick={() => setShowUploadModal(true)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium"
        >
          <Upload className="h-4 w-4" />
          Upload Scan
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
            <p className="font-medium">Failed to load scans</p>
          </div>
          <p className="text-sm text-muted-foreground mt-1">{(error as Error).message}</p>
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && scans.length === 0 && (
        <div className="rounded-lg border border-border bg-card p-12 text-center">
          <FileSearch className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <h3 className="text-lg font-semibold mb-2">No scans yet</h3>
          <p className="text-muted-foreground mb-6">
            Upload your first SBOM or SARIF file to start analyzing vulnerabilities
          </p>
          <button
            onClick={() => setShowUploadModal(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium"
          >
            <Upload className="h-4 w-4" />
            Upload Scan
          </button>
        </div>
      )}

      {/* Scans Table */}
      {!isLoading && !error && scans.length > 0 && (
        <div className="rounded-lg border border-border bg-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-muted/50 border-b border-border">
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-medium">Scan ID</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Tool</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Type</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Findings</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Components</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Status</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Scanned</th>
                  <th className="px-4 py-3 text-right text-sm font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {scans.map((scan: ScanSession) => (
                  <tr key={scan.session_id} className="hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3">
                      <Link
                        href={`/dashboard/scans/${scan.session_id}`}
                        className="font-mono text-sm text-primary hover:underline"
                      >
                        {scan.session_id}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <div>
                        <div className="font-medium">{scan.tool_name}</div>
                        <div className="text-xs text-muted-foreground">v{scan.tool_version}</div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-xs px-2 py-1 rounded bg-blue-500/10 text-blue-500 uppercase">
                        {scan.scan_type}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="font-semibold">{scan.findings_count}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-muted-foreground">{scan.components_count}</span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        {getStatusIcon(scan.status)}
                        <span className="text-sm capitalize">{scan.status}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-sm text-muted-foreground">
                      {scan.scan_timestamp ? format(new Date(scan.scan_timestamp), "PP") : "—"}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end">
                        <Link
                          href={`/dashboard/scans/${scan.session_id}`}
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

          {/* Pagination Info */}
          <div className="px-4 py-3 border-t border-border bg-muted/20">
            <p className="text-sm text-muted-foreground">
              Showing {scans.length} scans
            </p>
          </div>
        </div>
      )}

      {/* Upload Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-card border border-border rounded-lg max-w-3xl w-full max-h-[90vh] overflow-y-auto">
            {/* Header */}
            <div className="flex items-center justify-between p-6 border-b border-border">
              <div>
                <h2 className="text-2xl font-bold">Upload Scan</h2>
                <p className="text-sm text-muted-foreground mt-1">
                  Upload SBOM (CycloneDX, SPDX) or SARIF scan files
                </p>
              </div>
              <button
                onClick={() => {
                  setShowUploadModal(false);
                  resetForm();
                }}
                className="p-2 hover:bg-accent rounded-lg transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Body */}
            <div className="p-6 space-y-6">
              {/* File Upload Area */}
              <div>
                <label className="block text-sm font-medium mb-2">Scan File</label>
                <div
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
                    isDragging
                      ? "border-primary bg-primary/5"
                      : "border-border hover:border-primary/50"
                  }`}
                >
                  {uploadFile ? (
                    <div className="space-y-3">
                      <div className="flex items-center justify-center gap-2">
                        <CheckCircle2 className="h-8 w-8 text-green-500" />
                      </div>
                      <div>
                        <p className="font-medium">{uploadFile.name}</p>
                        <p className="text-sm text-muted-foreground">
                          {(uploadFile.size / 1024).toFixed(2)} KB
                        </p>
                      </div>
                      <button
                        onClick={() => setUploadFile(null)}
                        className="text-sm text-destructive hover:underline"
                      >
                        Remove file
                      </button>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      <Upload className="h-12 w-12 text-muted-foreground mx-auto" />
                      <div>
                        <p className="font-medium">Drag & drop your scan file here</p>
                        <p className="text-sm text-muted-foreground">or</p>
                      </div>
                      <label className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors cursor-pointer">
                        <Upload className="h-4 w-4" />
                        Browse Files
                        <input
                          type="file"
                          accept=".json"
                          className="hidden"
                          onChange={(e) => {
                            const file = e.target.files?.[0];
                            if (file) handleFileSelect(file);
                          }}
                        />
                      </label>
                      <p className="text-xs text-muted-foreground">
                        Supports: SARIF, CycloneDX, SPDX (JSON format)
                      </p>
                    </div>
                  )}
                </div>
              </div>

              {/* Format Selection */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Format</label>
                  <select
                    value={fileFormat}
                    onChange={(e) => setFileFormat(e.target.value as any)}
                    className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                  >
                    <option value="cyclonedx">CycloneDX</option>
                    <option value="spdx">SPDX</option>
                    <option value="sarif">SARIF</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">Scan Type</label>
                  <select
                    value={scanType}
                    onChange={(e) => setScanType(e.target.value as any)}
                    className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                  >
                    <option value="sbom">SBOM</option>
                    <option value="sast">SAST</option>
                    <option value="dast">DAST</option>
                    <option value="sca">SCA</option>
                    <option value="container">Container</option>
                    <option value="iac">IaC</option>
                  </select>
                </div>
              </div>

              {/* Metadata (Optional) */}
              <div>
                <h3 className="text-sm font-medium mb-3">Metadata (Optional)</h3>
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs text-muted-foreground mb-1">
                      Repository
                    </label>
                    <input
                      type="text"
                      value={metadata.repository}
                      onChange={(e) =>
                        setMetadata({ ...metadata, repository: e.target.value })
                      }
                      placeholder="e.g., owner/repo"
                      className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs text-muted-foreground mb-1">
                        Branch
                      </label>
                      <input
                        type="text"
                        value={metadata.branch}
                        onChange={(e) =>
                          setMetadata({ ...metadata, branch: e.target.value })
                        }
                        placeholder="e.g., main"
                        className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                      />
                    </div>

                    <div>
                      <label className="block text-xs text-muted-foreground mb-1">
                        Commit SHA
                      </label>
                      <input
                        type="text"
                        value={metadata.commit}
                        onChange={(e) =>
                          setMetadata({ ...metadata, commit: e.target.value })
                        }
                        placeholder="e.g., abc123..."
                        className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* Error Display */}
              {uploadMutation.isError && (
                <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4">
                  <div className="flex items-center gap-2 text-destructive">
                    <AlertCircle className="h-5 w-5" />
                    <p className="font-medium">Upload failed</p>
                  </div>
                  <p className="text-sm text-muted-foreground mt-1 whitespace-pre-wrap">
                    {uploadMutation.error instanceof Error
                      ? uploadMutation.error.message +
                        ((uploadMutation.error as any).data
                          ? "\n\n" + JSON.stringify((uploadMutation.error as any).data, null, 2)
                          : "")
                      : String(uploadMutation.error || "Unknown error")}
                  </p>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="flex items-center justify-end gap-3 p-6 border-t border-border">
              <button
                onClick={() => {
                  setShowUploadModal(false);
                  resetForm();
                }}
                className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg transition-colors"
                disabled={uploadMutation.isPending}
              >
                Cancel
              </button>
              <button
                onClick={handleUpload}
                disabled={!uploadFile || uploadMutation.isPending}
                className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {uploadMutation.isPending ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-primary-foreground"></div>
                    Uploading...
                  </>
                ) : (
                  <>
                    <Upload className="h-4 w-4" />
                    Upload Scan
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
