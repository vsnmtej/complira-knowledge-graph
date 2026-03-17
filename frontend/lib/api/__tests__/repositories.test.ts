/**
 * Tests for repositories API client.
 * Verifies all 6 repository endpoints match backend routes.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { createRepository, listRepositories, getRepository, updateRepository, deleteRepository, getRepositorySummary } from "../repositories";

vi.mock("@/lib/api-client", () => ({ apiRequest: vi.fn() }));
import { apiRequest } from "@/lib/api-client";
const mockApiRequest = vi.mocked(apiRequest);

describe("Repositories API Client", () => {
  beforeEach(() => vi.clearAllMocks());

  it("POST /v1/repositories — create repository", async () => {
    const req = { name: "backend-api", project_id: "proj_abc", repository_url: "https://github.com/org/repo" };
    mockApiRequest.mockResolvedValueOnce({ success: true, data: { repository_id: "repo_abc" } });
    await createRepository(req);
    expect(mockApiRequest).toHaveBeenCalledWith("/v1/repositories", { method: "POST", body: JSON.stringify(req) });
  });

  it("GET /v1/repositories — list with project filter", async () => {
    mockApiRequest.mockResolvedValueOnce({ success: true, data: [] });
    await listRepositories({ project_id: "proj_abc", limit: 20 });
    const url = mockApiRequest.mock.calls[0][0] as string;
    expect(url).toContain("/v1/repositories?");
    expect(url).toContain("project_id=proj_abc");
    expect(url).toContain("limit=20");
  });

  it("GET /v1/repositories/{id} — get repository", async () => {
    mockApiRequest.mockResolvedValueOnce({ success: true, data: { repository_id: "repo_abc" } });
    await getRepository("repo_abc");
    expect(mockApiRequest).toHaveBeenCalledWith("/v1/repositories/repo_abc");
  });

  it("PUT /v1/repositories/{id} — update repository", async () => {
    const req = { name: "updated-repo", tags: ["production"] };
    mockApiRequest.mockResolvedValueOnce({ success: true, data: {} });
    await updateRepository("repo_abc", req);
    expect(mockApiRequest).toHaveBeenCalledWith("/v1/repositories/repo_abc", { method: "PUT", body: JSON.stringify(req) });
  });

  it("DELETE /v1/repositories/{id} — soft delete", async () => {
    mockApiRequest.mockResolvedValueOnce({ success: true, data: { deleted: true } });
    await deleteRepository("repo_abc");
    expect(mockApiRequest).toHaveBeenCalledWith("/v1/repositories/repo_abc", { method: "DELETE" });
  });

  it("GET /v1/repositories/{id}/summary — repository summary", async () => {
    mockApiRequest.mockResolvedValueOnce({ success: true, data: { scan_count: 5 } });
    await getRepositorySummary("repo_abc");
    expect(mockApiRequest).toHaveBeenCalledWith("/v1/repositories/repo_abc/summary");
  });
});
