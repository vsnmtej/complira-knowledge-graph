/**
 * API client for reference data endpoints.
 *
 * Handles CVE/CWE lookups and threat intelligence enrichment.
 */

import { apiRequest } from "@/lib/api-client";

export interface CVEDetail {
  cve_id: string;
  description: string;
  cvss_score: number | null;
  cvss_vector: string | null;
  severity: string | null;
  published_date: string | null;
  last_modified_date: string | null;
  epss: {
    score: number;
    percentile: number;
    date: string;
  } | null;
  kev: {
    in_kev: boolean;
    known_ransomware?: string;
    due_date?: string;
    notes?: string;
  };
  weaknesses: Array<{
    cwe_id: string;
    name: string;
    description: string;
  }>;
  attack_patterns: Array<{
    capec_id: string;
    name: string;
    description: string;
  }>;
  attack_techniques: Array<{
    technique_id: string;
    name: string;
    description: string;
    tactics: string[];
  }>;
  nist_controls: Array<{
    control_id: string;
    title: string;
    family: string;
  }>;
  regulatory_requirements: Array<Record<string, any>>;
  d3fend_defenses: Array<{
    technique_id: string;
    name: string;
    description: string;
  }>;
  threat_groups: Array<Record<string, any>>;
  exploits: Array<{
    exploit_id: string;
    name: string;
    type: string;
    platform: string;
  }>;
  references: Array<Record<string, any>> | null;
  error?: string;
}

export interface CWEDetail {
  cwe_id: string;
  name: string;
  description: string;
  extended_description: string | null;
  parents: Array<{ cwe_id: string; name: string }>;
  children: Array<{ cwe_id: string; name: string }>;
  attack_patterns: Array<{
    capec_id: string;
    name: string;
    description: string;
  }>;
}

export interface MappedControls {
  cve_id: string;
  nist_controls: Array<{
    control_id: string;
    title: string;
    family: string;
    description: string;
  }>;
  regulatory_requirements: Array<Record<string, any>>;
}

/**
 * Get CVE details with full enrichment.
 */
export async function getCVEDetails(
  cveId: string
): Promise<{ success: boolean; data: CVEDetail }> {
  return apiRequest(`/v1/reference/cve/${cveId}`);
}

/**
 * Batch enrich multiple CVEs.
 */
export async function batchEnrichCVEs(
  cveIds: string[]
): Promise<{ success: boolean; data: CVEDetail[] }> {
  return apiRequest(`/v1/reference/enrich?cve_ids=${cveIds.join(",")}`);
}

/**
 * Get CWE weakness details.
 */
export async function getCWEDetails(
  cweId: string
): Promise<{ success: boolean; data: CWEDetail }> {
  return apiRequest(`/v1/reference/cwe/${cweId}`);
}

/**
 * Get mapped NIST controls for a CVE.
 */
export async function getMappedControls(
  cveId: string
): Promise<{ success: boolean; data: MappedControls }> {
  return apiRequest(`/v1/reference/controls/${cveId}`);
}
