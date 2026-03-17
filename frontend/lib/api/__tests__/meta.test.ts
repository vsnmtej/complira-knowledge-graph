/**
 * Tests for meta API client.
 * Verifies coverage and stats endpoints.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { getCoverage, getStats } from "../meta";

vi.mock("@/lib/api-client", () => ({ apiRequest: vi.fn() }));
import { apiRequest } from "@/lib/api-client";
const mockApiRequest = vi.mocked(apiRequest);

describe("Meta API Client", () => {
  beforeEach(() => vi.clearAllMocks());

  it("GET /v1/meta/coverage — data coverage", async () => {
    mockApiRequest.mockResolvedValueOnce({ success: true, data: { vulnerabilities: 335000 } });
    await getCoverage();
    expect(mockApiRequest).toHaveBeenCalledWith("/v1/meta/coverage");
  });

  it("GET /v1/meta/stats — database stats", async () => {
    mockApiRequest.mockResolvedValueOnce({ success: true, data: { total_documents: 5000000 } });
    await getStats();
    expect(mockApiRequest).toHaveBeenCalledWith("/v1/meta/stats");
  });
});
