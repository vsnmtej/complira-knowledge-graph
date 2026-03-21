/**
 * Tests for VEX API client.
 *
 * Verifies all 6 VEX endpoints match backend routes.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { createVEX, listVEX, getVEX, updateVEX, patchVulnerability, deleteVEX } from "../vex";

vi.mock("@/lib/api-client", () => ({
  apiRequest: vi.fn(),
}));

import { apiRequest } from "@/lib/api-client";
const mockApiRequest = vi.mocked(apiRequest);

describe("VEX API Client", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("createVEX", () => {
    it("calls POST /v1/vex", async () => {
      const request = {
        vulnerabilities: [
          { id: "CVE-2024-1234", analysis: { state: "not_affected" as const, justification: "code_not_present" } },
        ],
      };

      mockApiRequest.mockResolvedValueOnce({
        success: true,
        data: { vex_id: "vex_abc", vulnerabilities_count: 1, enriched_count: 1 },
      });

      const result = await createVEX(request);

      expect(mockApiRequest).toHaveBeenCalledWith("/v1/vex", {
        method: "POST",
        body: JSON.stringify(request),
      });
      expect(result.data.vex_id).toBe("vex_abc");
    });
  });

  describe("listVEX", () => {
    it("calls GET /v1/vex with pagination", async () => {
      mockApiRequest.mockResolvedValueOnce({ success: true, data: [] });

      await listVEX({ limit: 10, offset: 5 });

      const url = mockApiRequest.mock.calls[0][0] as string;
      expect(url).toContain("/v1/vex?");
      expect(url).toContain("limit=10");
      expect(url).toContain("offset=5");
    });
  });

  describe("getVEX", () => {
    it("calls GET /v1/vex/{vexId}", async () => {
      mockApiRequest.mockResolvedValueOnce({ success: true, data: { vex_id: "vex_abc" } });

      await getVEX("vex_abc");

      expect(mockApiRequest).toHaveBeenCalledWith("/v1/vex/vex_abc");
    });
  });

  describe("updateVEX", () => {
    it("calls PUT /v1/vex/{vexId}", async () => {
      const request = {
        vulnerabilities: [
          { id: "CVE-2024-1234", analysis: { state: "resolved" } },
        ],
      };

      mockApiRequest.mockResolvedValueOnce({ success: true, data: { vex_id: "vex_abc" } });

      await updateVEX("vex_abc", request);

      expect(mockApiRequest).toHaveBeenCalledWith("/v1/vex/vex_abc", {
        method: "PUT",
        body: JSON.stringify(request),
      });
    });
  });

  describe("patchVulnerability", () => {
    it("calls PATCH /v1/vex/{vexId}/vulnerability/{cveId}", async () => {
      const request = { analysis: { state: "resolved", response: ["update"] } };

      mockApiRequest.mockResolvedValueOnce({ success: true, data: {} });

      await patchVulnerability("vex_abc", "CVE-2024-1234", request);

      expect(mockApiRequest).toHaveBeenCalledWith(
        "/v1/vex/vex_abc/vulnerability/CVE-2024-1234",
        { method: "PATCH", body: JSON.stringify(request) }
      );
    });
  });

  describe("deleteVEX", () => {
    it("calls DELETE /v1/vex/{vexId}", async () => {
      mockApiRequest.mockResolvedValueOnce({ success: true, data: { deleted: true, vex_id: "vex_abc" } });

      const result = await deleteVEX("vex_abc");

      expect(mockApiRequest).toHaveBeenCalledWith("/v1/vex/vex_abc", { method: "DELETE" });
      expect(result.data.deleted).toBe(true);
    });
  });
});
