/**
 * Tests for reference API client.
 * Verifies CVE/CWE lookup and batch enrichment endpoints.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { getCVEDetails, batchEnrichCVEs, getCWEDetails, getMappedControls } from "../reference";

vi.mock("@/lib/api-client", () => ({ apiRequest: vi.fn() }));
import { apiRequest } from "@/lib/api-client";
const mockApiRequest = vi.mocked(apiRequest);

describe("Reference API Client", () => {
  beforeEach(() => vi.clearAllMocks());

  it("GET /v1/reference/cve/{cve_id} — CVE details", async () => {
    mockApiRequest.mockResolvedValueOnce({ success: true, data: { cve_id: "CVE-2024-1234" } });
    await getCVEDetails("CVE-2024-1234");
    expect(mockApiRequest).toHaveBeenCalledWith("/v1/reference/cve/CVE-2024-1234");
  });

  it("GET /v1/reference/enrich — batch enrich", async () => {
    mockApiRequest.mockResolvedValueOnce({ success: true, data: [] });
    await batchEnrichCVEs(["CVE-2024-1234", "CVE-2024-5678"]);
    const url = mockApiRequest.mock.calls[0][0] as string;
    expect(url).toContain("/v1/reference/enrich?");
    expect(url).toContain("CVE-2024-1234");
    expect(url).toContain("CVE-2024-5678");
  });

  it("GET /v1/reference/cwe/{cwe_id} — CWE details", async () => {
    mockApiRequest.mockResolvedValueOnce({ success: true, data: { cwe_id: "CWE-79" } });
    await getCWEDetails("CWE-79");
    expect(mockApiRequest).toHaveBeenCalledWith("/v1/reference/cwe/CWE-79");
  });

  it("GET /v1/reference/controls/{cve_id} — mapped controls", async () => {
    mockApiRequest.mockResolvedValueOnce({ success: true, data: { controls: [] } });
    await getMappedControls("CVE-2024-1234");
    expect(mockApiRequest).toHaveBeenCalledWith("/v1/reference/controls/CVE-2024-1234");
  });
});
