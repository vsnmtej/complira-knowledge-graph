/**
 * API client for enrichment endpoints.
 *
 * Handles batch CVE enrichment, single CVE enrichment,
 * and regulatory trigger enrichment.
 */

import { apiRequest } from "@/lib/api-client";

// --- Types ---

export interface RiskFactors {
  high_epss: boolean;
  actively_exploited: boolean;
  high_cvss: boolean;
  public_exploits: boolean;
  threat_groups_using: boolean;
}

export interface CVEEnrichment {
  cve_id: string;
  description?: string;
  cvss_score?: number;
  cvss_vector?: string;
  cvss_severity?: string;
  epss_score?: number;
  in_kev: boolean;
  exploit_count: number;
  published_date?: string;
  last_modified?: string;
  risk_score: number;
  priority: string;
  risk_factors: RiskFactors;
  cwe_list: string[];
  attack_techniques: string[];
  threat_groups: string[];
  attack_path?: {
    path: Array<{
      stage: string;
      node?: string;
      nodes?: string[];
      name?: string;
      description?: string;
    }>;
    defenses: Array<{
      d3fend_id: string;
      name: string;
      description?: string;
      coverage: string[];
    }>;
  };
  compliance?: {
    nist_controls: string[];
    frameworks: string[];
  };
  enriched_at: string;
}

export interface BatchEnrichRequest {
  cve_ids: string[];
  include_attack_paths?: boolean;
  include_compliance?: boolean;
}

export interface BatchEnrichResponse {
  enriched: CVEEnrichment[];
  total: number;
  processing_time_ms: number;
}

export interface RegulatoryTrigger {
  framework: string;
  requirement_id: string;
  requirement_title: string;
  urgency: string;
  trigger_rule: string;
  confidence: number;
  evidence: Record<string, unknown>;
  trigger_timestamp: string;
}

export interface RegulatoryEnrichResponse {
  cve_id: string;
  nvd_data: Record<string, unknown> | null;
  exploit_intelligence: Record<string, unknown> | null;
  regulatory_triggers: RegulatoryTrigger[];
}

// --- API Functions ---

/**
 * Batch enrich multiple CVEs with risk scoring and graph intelligence.
 */
export async function batchEnrich(
  data: BatchEnrichRequest
): Promise<BatchEnrichResponse> {
  return apiRequest<BatchEnrichResponse>("/v1/enrich", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

/**
 * Enrich a single CVE by ID.
 */
export async function enrichSingleCVE(
  cveId: string,
  options?: {
    include_attack_path?: boolean;
    include_compliance?: boolean;
  }
): Promise<CVEEnrichment> {
  const params = new URLSearchParams();
  if (options?.include_attack_path) {
    params.append("include_attack_path", "true");
  }
  if (options?.include_compliance) {
    params.append("include_compliance", "true");
  }
  const query = params.toString();
  const url = `/v1/enrich/${cveId}${query ? `?${query}` : ""}`;
  return apiRequest<CVEEnrichment>(url);
}

/**
 * Enrich a CVE with regulatory trigger analysis.
 */
export async function enrichRegulatory(
  cveId: string
): Promise<RegulatoryEnrichResponse> {
  return apiRequest<RegulatoryEnrichResponse>("/v1/enrich/regulatory", {
    method: "POST",
    body: JSON.stringify({ cve_id: cveId }),
  });
}
