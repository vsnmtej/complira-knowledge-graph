/**
 * API client for scan endpoints.
 *
 * Handles SBOM/SARIF file uploads, scan listing, and vulnerability findings.
 */

import { apiRequest } from "@/lib/api-client";

export interface ScanSession {
  session_id: string;
  tool_name: string;
  tool_version: string;
  scan_type: "sast" | "dast" | "sca" | "sbom" | "unknown";
  scan_timestamp: string;
  status: "processing" | "completed" | "failed";
  findings_count: number;
  components_count: number;
  created_at: string;
  updated_at: string;
  metadata: Record<string, any>;
  project_id?: string;
  repository_id?: string;
}

export interface ScanFinding {
  finding_id: string;
  cve_id: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO";
  description: string;
  location: string;
  tool_name: string;
  created_at: string;
}

export interface ScanIngestRequest {
  format: "sarif" | "cyclonedx" | "spdx";
  scan_type: "sast" | "dast" | "sca" | "container" | "sbom" | "iac";
  payload: any;
  metadata?: {
    repository?: string;
    branch?: string;
    commit?: string;
    [key: string]: any;
  };
}

export interface ScanIngestResponse {
  scan_session_id: string;
  findings_count: number;
  components_count: number;
  status: "processing" | "completed" | "failed";
}

/**
 * Upload and ingest a scan file (SBOM or SARIF).
 */
export async function ingestScan(
  request: ScanIngestRequest
): Promise<{ success: boolean; data: ScanIngestResponse }> {
  return apiRequest<{ success: boolean; data: ScanIngestResponse }>(
    `/v1/scan/ingest`,
    {
      method: "POST",
      body: JSON.stringify(request),
    }
  );
}

/**
 * List all scans for the organization.
 */
export async function listScans(params?: {
  limit?: number;
  offset?: number;
  status?: string;
  scan_type?: string;
}): Promise<{ success: boolean; data: ScanSession[] }> {
  const queryParams = new URLSearchParams();
  if (params?.limit) queryParams.append("limit", params.limit.toString());
  if (params?.offset) queryParams.append("offset", params.offset.toString());
  if (params?.status) queryParams.append("status", params.status);
  if (params?.scan_type) queryParams.append("scan_type", params.scan_type);

  return apiRequest<{ success: boolean; data: ScanSession[] }>(
    `/v1/scans?${queryParams.toString()}`
  );
}

/**
 * Get scan session details by ID.
 */
export async function getScanSession(
  sessionId: string
): Promise<{ success: boolean; data: ScanSession }> {
  return apiRequest<{ success: boolean; data: ScanSession }>(
    `/v1/scan/${sessionId}`
  );
}

/**
 * List findings for a scan session.
 */
export async function getScanFindings(params: {
  sessionId: string;
  limit?: number;
  offset?: number;
  severity?: string;
}): Promise<{ success: boolean; data: ScanFinding[] }> {
  const queryParams = new URLSearchParams();
  if (params.limit) queryParams.append("limit", params.limit.toString());
  if (params.offset) queryParams.append("offset", params.offset.toString());
  if (params.severity) queryParams.append("severity", params.severity);

  return apiRequest<{ success: boolean; data: ScanFinding[] }>(
    `/v1/scan/${params.sessionId}/findings?${queryParams.toString()}`
  );
}

/**
 * Generate VEX document for a scan session.
 */
export async function generateVEX(sessionId: string): Promise<{
  success: boolean;
  data: {
    scan_session_id: string;
    vex_document: any;
    vulnerabilities_assessed: number;
    generated_at: string;
  };
}> {
  return apiRequest(`/v1/scan/${sessionId}/vex`, {
    method: "POST",
  });
}

/**
 * Match CPEs for a scan session.
 */
export async function matchCPEs(sessionId: string): Promise<{
  success: boolean;
  data: {
    scan_session_id: string;
    matched_components: number;
    total_components: number;
    matched_at: string;
  };
}> {
  return apiRequest(`/v1/scan/${sessionId}/cpe-match`, {
    method: "POST",
  });
}
