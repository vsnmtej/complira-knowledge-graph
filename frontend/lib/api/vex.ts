/**
 * API client for VEX (Vulnerability Exploitability eXchange) endpoints.
 *
 * Handles VEX document CRUD operations and vulnerability status management.
 */

import { apiRequest } from "@/lib/api-client";

export interface VEXEnrichment {
  // KEV data
  in_kev: boolean;
  kev_date_added?: string;
  kev_due_date?: string;

  // EPSS data
  epss_score?: number;
  epss_percentile?: number;

  // CVSS data
  cvss_score?: number;
  cvss_severity?: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

  // CWE weaknesses
  weaknesses: Array<{
    cwe_id: string;
    name: string;
  }>;

  // ATT&CK techniques
  attack_techniques: Array<{
    technique_id: string;
    name: string;
  }>;

  // NIST controls
  nist_controls: Array<{
    control_id: string;
    title: string;
  }>;

  // D3FEND defenses
  d3fend_defenses: Array<{
    id: string;
    name: string;
  }>;

  // Regulatory violations
  regulatory_violations: Array<{
    framework: string;
    requirement_id: string;
  }>;
}

export interface VEXVulnerability {
  cve_id: string;
  state: "exploitable" | "not_affected" | "in_triage" | "resolved" | "false_positive";
  justification?: string;
  response?: string[];
  detail?: string;
  enrichment: VEXEnrichment;
}

export interface VEXDocument {
  vex_id: string;
  bomFormat: string;
  specVersion: string;
  version: number;
  vulnerabilities: VEXVulnerability[];
  metadata: Record<string, any>;
  created_at: string;
  updated_at: string;
  customer_id: string;
}

export interface VEXListItem {
  vex_id: string;
  vulnerabilities_count: number;
  created_at: string;
  updated_at: string;
  metadata: Record<string, any>;
}

export interface CreateVEXRequest {
  bomFormat?: string;
  specVersion?: string;
  vulnerabilities: Array<{
    id: string; // CVE ID
    analysis: {
      state: "exploitable" | "not_affected" | "in_triage" | "resolved" | "false_positive";
      justification?: string;
      response?: string[];
      detail?: string;
    };
  }>;
  metadata?: Record<string, any>;
}

export interface CreateVEXResponse {
  vex_id: string;
  vulnerabilities_count: number;
  enriched_count: number;
  created_at: string;
}

export interface UpdateVEXRequest {
  vulnerabilities: Array<{
    id: string;
    analysis: {
      state: string;
      justification?: string;
      response?: string[];
      detail?: string;
    };
  }>;
  metadata?: Record<string, any>;
}

export interface UpdateVEXResponse {
  vex_id: string;
  updated_at: string;
  vulnerabilities_count: number;
}

export interface PatchVulnerabilityRequest {
  analysis: {
    state: string;
    justification?: string;
    response?: string[];
    detail?: string;
  };
}

/**
 * Create a new VEX document.
 */
export async function createVEX(
  request: CreateVEXRequest
): Promise<{ success: boolean; data: CreateVEXResponse }> {
  return apiRequest<{ success: boolean; data: CreateVEXResponse }>(
    `/v1/vex`,
    {
      method: "POST",
      body: JSON.stringify(request),
    }
  );
}

/**
 * List all VEX documents.
 */
export async function listVEX(params?: {
  limit?: number;
  offset?: number;
}): Promise<{ success: boolean; data: VEXListItem[] }> {
  const queryParams = new URLSearchParams();
  if (params?.limit) queryParams.append("limit", params.limit.toString());
  if (params?.offset) queryParams.append("offset", params.offset.toString());

  return apiRequest<{ success: boolean; data: VEXListItem[] }>(
    `/v1/vex?${queryParams.toString()}`
  );
}

/**
 * Get VEX document by ID with full enrichment.
 */
export async function getVEX(
  vexId: string
): Promise<{ success: boolean; data: VEXDocument }> {
  return apiRequest<{ success: boolean; data: VEXDocument }>(
    `/v1/vex/${vexId}`
  );
}

/**
 * Update entire VEX document.
 */
export async function updateVEX(
  vexId: string,
  request: UpdateVEXRequest
): Promise<{ success: boolean; data: UpdateVEXResponse }> {
  return apiRequest<{ success: boolean; data: UpdateVEXResponse }>(
    `/v1/vex/${vexId}`,
    {
      method: "PUT",
      body: JSON.stringify(request),
    }
  );
}

/**
 * Update single vulnerability assessment.
 */
export async function patchVulnerability(
  vexId: string,
  cveId: string,
  request: PatchVulnerabilityRequest
): Promise<{ success: boolean; data: UpdateVEXResponse }> {
  return apiRequest<{ success: boolean; data: UpdateVEXResponse }>(
    `/v1/vex/${vexId}/vulnerability/${cveId}`,
    {
      method: "PATCH",
      body: JSON.stringify(request),
    }
  );
}

/**
 * Delete VEX document.
 */
export async function deleteVEX(
  vexId: string
): Promise<{ success: boolean; data: { deleted: boolean; vex_id: string } }> {
  return apiRequest<{ success: boolean; data: { deleted: boolean; vex_id: string } }>(
    `/v1/vex/${vexId}`,
    {
      method: "DELETE",
    }
  );
}
