/**
 * API client for repository management endpoints.
 *
 * Handles repository CRUD operations and summary retrieval.
 */

import { apiRequest } from "@/lib/api-client";

export interface Repository {
  repository_id: string;
  project_id?: string | null;
  project_name?: string | null;
  name: string;
  description?: string;
  repository_url?: string;
  default_branch?: string;
  tags: string[];
  scan_count: number;
  created_at: string;
  updated_at: string;
  last_scan_at?: string | null;
  active: boolean;
}

export interface CreateRepositoryRequest {
  name: string;
  project_id?: string;
  description?: string;
  repository_url?: string;
  default_branch?: string;
  tags?: string[];
}

export interface UpdateRepositoryRequest {
  name?: string;
  project_id?: string | null;
  description?: string;
  repository_url?: string;
  default_branch?: string;
  tags?: string[];
  active?: boolean;
}

export interface RepositorySummary {
  repository_id: string;
  repository_name: string;
  project_id?: string | null;
  project_name?: string | null;
  scan_count: number;
  first_scan: string | null;
  last_scan: string | null;
  current_findings: {
    critical: number;
    high: number;
    medium: number;
    low: number;
    total: number;
  };
  trends: {
    new_last_7_days: number;
    resolved_last_7_days: number;
    net_change: number;
  };
  top_vulnerabilities: Array<Record<string, any>>;
}

/**
 * Create a new repository.
 */
export async function createRepository(
  data: CreateRepositoryRequest
): Promise<{ success: boolean; data: Repository }> {
  return apiRequest<{ success: boolean; data: Repository }>(`/v1/repositories`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

/**
 * List all repositories for the organization.
 */
export async function listRepositories(params?: {
  project_id?: string;
  active?: boolean;
  limit?: number;
  offset?: number;
}): Promise<{ success: boolean; data: { repositories: Repository[]; total: number } }> {
  const queryParams = new URLSearchParams();
  if (params?.project_id) queryParams.append("project_id", params.project_id);
  if (params?.active !== undefined) queryParams.append("active", params.active.toString());
  if (params?.limit) queryParams.append("limit", params.limit.toString());
  if (params?.offset) queryParams.append("offset", params.offset.toString());

  const qs = queryParams.toString();
  return apiRequest(`/v1/repositories${qs ? `?${qs}` : ""}`);
}

/**
 * Get repository details by ID.
 */
export async function getRepository(
  repositoryId: string
): Promise<{ success: boolean; data: Repository }> {
  return apiRequest(`/v1/repositories/${repositoryId}`);
}

/**
 * Update a repository.
 */
export async function updateRepository(
  repositoryId: string,
  data: UpdateRepositoryRequest
): Promise<{ success: boolean; data: Repository }> {
  return apiRequest(`/v1/repositories/${repositoryId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

/**
 * Soft delete a repository.
 */
export async function deleteRepository(
  repositoryId: string
): Promise<{ success: boolean; data: { repository_id: string; name: string; deleted_at: string; message: string } }> {
  return apiRequest(`/v1/repositories/${repositoryId}`, {
    method: "DELETE",
  });
}

/**
 * Get repository summary with aggregated stats.
 */
export async function getRepositorySummary(
  repositoryId: string
): Promise<{ success: boolean; data: RepositorySummary }> {
  return apiRequest(`/v1/repositories/${repositoryId}/summary`);
}
