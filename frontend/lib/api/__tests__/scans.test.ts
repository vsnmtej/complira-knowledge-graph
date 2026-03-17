/**
 * Tests for scan API client.
 *
 * Verifies all scan endpoints match backend routes and handle responses correctly.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { ingestScan, listScans, getScanSession, getScanFindings, generateVEX, matchCPEs } from "../scans";

// Mock the api-client module
vi.mock("@/lib/api-client", () => ({
  apiRequest: vi.fn(),
}));

import { apiRequest } from "@/lib/api-client";
const mockApiRequest = vi.mocked(apiRequest);

describe("Scans API Client", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("ingestScan", () => {
    it("calls POST /v1/scan/ingest with correct payload", async () => {
      const request = {
        format: "cyclonedx" as const,
        scan_type: "sbom" as const,
        payload: { bomFormat: "CycloneDX", components: [] },
        metadata: { repository: "test-repo" },
      };

      mockApiRequest.mockResolvedValueOnce({
        success: true,
        data: { scan_session_id: "session_123", findings_count: 5, components_count: 3, status: "completed" },
      });

      const result = await ingestScan(request);

      expect(mockApiRequest).toHaveBeenCalledWith("/v1/scan/ingest", {
        method: "POST",
        body: JSON.stringify(request),
      });
      expect(result.success).toBe(true);
      expect(result.data.scan_session_id).toBe("session_123");
    });
  });

  describe("listScans", () => {
    it("calls GET /v1/scans with query params", async () => {
      mockApiRequest.mockResolvedValueOnce({ success: true, data: [] });

      await listScans({ limit: 10, offset: 20, status: "completed" });

      expect(mockApiRequest).toHaveBeenCalledWith(
        expect.stringContaining("/v1/scans?")
      );
      const url = mockApiRequest.mock.calls[0][0] as string;
      expect(url).toContain("limit=10");
      expect(url).toContain("offset=20");
      expect(url).toContain("status=completed");
    });

    it("calls GET /v1/scans without params when none provided", async () => {
      mockApiRequest.mockResolvedValueOnce({ success: true, data: [] });

      await listScans();

      expect(mockApiRequest).toHaveBeenCalledWith("/v1/scans?");
    });
  });

  describe("getScanSession", () => {
    it("calls GET /v1/scan/{sessionId}", async () => {
      mockApiRequest.mockResolvedValueOnce({ success: true, data: { session_id: "abc" } });

      await getScanSession("abc");

      expect(mockApiRequest).toHaveBeenCalledWith("/v1/scan/abc");
    });
  });

  describe("getScanFindings", () => {
    it("calls GET /v1/scan/{sessionId}/findings with params", async () => {
      mockApiRequest.mockResolvedValueOnce({ success: true, data: [] });

      await getScanFindings({ sessionId: "abc", limit: 50, severity: "CRITICAL" });

      const url = mockApiRequest.mock.calls[0][0] as string;
      expect(url).toContain("/v1/scan/abc/findings");
      expect(url).toContain("limit=50");
      expect(url).toContain("severity=CRITICAL");
    });
  });

  describe("generateVEX", () => {
    it("calls POST /v1/scan/{sessionId}/vex without URL typo", async () => {
      mockApiRequest.mockResolvedValueOnce({ success: true, data: {} });

      await generateVEX("abc");

      // Verify no leading space in URL (bug fix validation)
      expect(mockApiRequest).toHaveBeenCalledWith("/v1/scan/abc/vex", { method: "POST" });
      const url = mockApiRequest.mock.calls[0][0] as string;
      expect(url).not.toMatch(/^\s/); // No leading whitespace
    });
  });

  describe("matchCPEs", () => {
    it("calls POST /v1/scan/{sessionId}/cpe-match", async () => {
      mockApiRequest.mockResolvedValueOnce({ success: true, data: {} });

      await matchCPEs("abc");

      expect(mockApiRequest).toHaveBeenCalledWith("/v1/scan/abc/cpe-match", { method: "POST" });
    });
  });
});
