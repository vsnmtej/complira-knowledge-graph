/**
 * API client for project management endpoints.
 *
 * Handles project CRUD operations and summary retrieval.
 */

import { apiRequest } from "@/lib/api-client";

export interface Project {
  project_id: string;
  name: string;
  description?: string;
  tags: string[];
  repository_count: number;
  created_at: string;
  updated_at: string;
  last_scan_at?: string | null;
  active: boolean;
}

export interface CreateProjectRequest {
  name: string;
  description?: string;
  tags?: string[];
}

export interface UpdateProjectRequest {
  name?: string;
  description?: string;
  tags?: string[];
  active?: boolean;
}

export interface ProjectSummary {
  project_id: string;
  project_name: string;
  repository_count: number;
  total_scans: number;
  findings: {
    critical: number;
    high: number;
    medium: number;
    low: number;
    total: number;
  };
  top_vulnerabilities: Array<Record<string, any>>;
  compliance_status: Record<string, any> | null;
  repositories: Array<{
    repository_id: string;
    repository_name: string;
    scan_count: number;
    last_scan_at: string | null;
  }>;
}

/**
 * Create a new project.
 */
export async function createProject(
  data: CreateProjectRequest
): Promise<{ success: boolean; data: Project }> {
  return apiRequest<{ success: boolean; data: Project }>(`/v1/projects`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

/**
 * List all projects for the organization.
 */
export async function listProjects(params?: {
  tags?: string;
  active?: boolean;
  limit?: number;
  offset?: number;
}): Promise<{ success: boolean; data: { projects: Project[]; total: number } }> {
  const queryParams = new URLSearchParams();
  if (params?.tags) queryParams.append("tags", params.tags);
  if (params?.active !== undefined) queryParams.append("active", params.active.toString());
  if (params?.limit) queryParams.append("limit", params.limit.toString());
  if (params?.offset) queryParams.append("offset", params.offset.toString());

  const qs = queryParams.toString();
  return apiRequest(`/v1/projects${qs ? `?${qs}` : ""}`);
}

/**
 * Get project details by ID.
 */
export async function getProject(
  projectId: string
): Promise<{ success: boolean; data: Project }> {
  return apiRequest(`/v1/projects/${projectId}`);
}

/**
 * Update a project.
 */
export async function updateProject(
  projectId: string,
  data: UpdateProjectRequest
): Promise<{ success: boolean; data: Project }> {
  return apiRequest(`/v1/projects/${projectId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

/**
 * Soft delete a project.
 */
export async function deleteProject(
  projectId: string
): Promise<{ success: boolean; data: { project_id: string; name: string; deleted_at: string; message: string } }> {
  return apiRequest(`/v1/projects/${projectId}`, {
    method: "DELETE",
  });
}

/**
 * Get project summary with aggregated stats.
 */
export async function getProjectSummary(
  projectId: string
): Promise<{ success: boolean; data: ProjectSummary }> {
  return apiRequest(`/v1/projects/${projectId}/summary`);
}
