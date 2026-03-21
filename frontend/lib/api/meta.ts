/**
 * API client for metadata and data quality endpoints.
 *
 * Handles coverage metrics and database statistics.
 */

import { apiRequest } from "@/lib/api-client";

export interface CoverageData {
  vertices: Record<string, number>;
  edges: Record<string, number>;
  enrichment_funnel: {
    sample_size: number;
    sample_year: number;
    cve_to_cwe_percent: number;
    cve_to_capec_percent: number;
    cve_to_attack_percent: number;
    estimated_coverage: Record<string, string>;
  };
  data_limitations: Record<string, any>;
  total_edges: number;
  recommendations: string[];
}

export interface StatsData {
  database: string;
  collections: Record<string, number>;
  total_documents: number;
  total_edges: number;
}

/**
 * Get data coverage and quality metrics.
 */
export async function getCoverage(): Promise<{ success: boolean; data: CoverageData }> {
  return apiRequest(`/v1/meta/coverage`);
}

/**
 * Get aggregate database statistics.
 */
export async function getStats(): Promise<{ success: boolean; data: StatsData }> {
  return apiRequest(`/v1/meta/stats`);
}
