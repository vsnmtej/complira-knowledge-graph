/**
 * Tests for projects API client.
 * Verifies all 6 project endpoints match backend routes.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { createProject, listProjects, getProject, updateProject, deleteProject, getProjectSummary } from "../projects";

vi.mock("@/lib/api-client", () => ({ apiRequest: vi.fn() }));
import { apiRequest } from "@/lib/api-client";
const mockApiRequest = vi.mocked(apiRequest);

describe("Projects API Client", () => {
  beforeEach(() => vi.clearAllMocks());

  it("POST /v1/projects — create project", async () => {
    const req = { name: "Backend Services", description: "All backends", tags: ["backend"] };
    mockApiRequest.mockResolvedValueOnce({ success: true, data: { project_id: "proj_abc" } });
    await createProject(req);
    expect(mockApiRequest).toHaveBeenCalledWith("/v1/projects", { method: "POST", body: JSON.stringify(req) });
  });

  it("GET /v1/projects — list with filters", async () => {
    mockApiRequest.mockResolvedValueOnce({ success: true, data: [] });
    await listProjects({ tags: "backend", active: true, limit: 10 });
    const url = mockApiRequest.mock.calls[0][0] as string;
    expect(url).toContain("/v1/projects?");
    expect(url).toContain("tags=backend");
    expect(url).toContain("active=true");
    expect(url).toContain("limit=10");
  });

  it("GET /v1/projects/{id} — get project", async () => {
    mockApiRequest.mockResolvedValueOnce({ success: true, data: { project_id: "proj_abc" } });
    await getProject("proj_abc");
    expect(mockApiRequest).toHaveBeenCalledWith("/v1/projects/proj_abc");
  });

  it("PUT /v1/projects/{id} — update project", async () => {
    const req = { name: "Updated Name", tags: ["v2"] };
    mockApiRequest.mockResolvedValueOnce({ success: true, data: {} });
    await updateProject("proj_abc", req);
    expect(mockApiRequest).toHaveBeenCalledWith("/v1/projects/proj_abc", { method: "PUT", body: JSON.stringify(req) });
  });

  it("DELETE /v1/projects/{id} — soft delete", async () => {
    mockApiRequest.mockResolvedValueOnce({ success: true, data: { deleted: true } });
    await deleteProject("proj_abc");
    expect(mockApiRequest).toHaveBeenCalledWith("/v1/projects/proj_abc", { method: "DELETE" });
  });

  it("GET /v1/projects/{id}/summary — project summary", async () => {
    mockApiRequest.mockResolvedValueOnce({ success: true, data: { repository_count: 3 } });
    await getProjectSummary("proj_abc");
    expect(mockApiRequest).toHaveBeenCalledWith("/v1/projects/proj_abc/summary");
  });
});
