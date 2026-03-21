/**
 * Tests for enrichment API client.
 *
 * Verifies all 3 enrichment endpoints match backend routes.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { batchEnrich, enrichSingleCVE, enrichRegulatory } from "../enrichment";

vi.mock("@/lib/api-client", () => ({
  apiRequest: vi.fn(),
}));

import { apiRequest } from "@/lib/api-client";
const mockApiRequest = vi.mocked(apiRequest);

describe("Enrichment API Client", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("batchEnrich", () => {
    it("calls POST /v1/enrich with CVE IDs and options", async () => {
      const request = {
        cve_ids: ["CVE-2024-21413", "CVE-2023-44487"],
        include_attack_paths: true,
        include_compliance: false,
      };

      mockApiRequest.mockResolvedValueOnce({
        enriched: [
          {
            cve_id: "CVE-2024-21413",
            cvss_score: 9.8,
            epss_score: 0.85,
            in_kev: true,
            risk_score: 0.92,
            priority: "CRITICAL",
          },
        ],
        total: 1,
        processing_time_ms: 250.5,
      });

      const result = await batchEnrich(request);

      expect(mockApiRequest).toHaveBeenCalledWith("/v1/enrich", {
        method: "POST",
        body: JSON.stringify(request),
      });
      expect(result.enriched).toHaveLength(1);
      expect(result.total).toBe(1);
      expect(result.processing_time_ms).toBe(250.5);
    });

    it("sends default options when not specified", async () => {
      const request = { cve_ids: ["CVE-2021-44228"] };

      mockApiRequest.mockResolvedValueOnce({
        enriched: [],
        total: 0,
        processing_time_ms: 10,
      });

      await batchEnrich(request);

      expect(mockApiRequest).toHaveBeenCalledWith("/v1/enrich", {
        method: "POST",
        body: JSON.stringify(request),
      });
    });
  });

  describe("enrichSingleCVE", () => {
    it("calls GET /v1/enrich/{cve_id} without query params by default", async () => {
      mockApiRequest.mockResolvedValueOnce({
        cve_id: "CVE-2024-21413",
        cvss_score: 9.8,
        risk_score: 0.92,
        priority: "CRITICAL",
      });

      const result = await enrichSingleCVE("CVE-2024-21413");

      expect(mockApiRequest).toHaveBeenCalledWith(
        "/v1/enrich/CVE-2024-21413"
      );
      expect(result.cve_id).toBe("CVE-2024-21413");
    });

    it("appends query params when options provided", async () => {
      mockApiRequest.mockResolvedValueOnce({
        cve_id: "CVE-2024-21413",
        risk_score: 0.92,
        priority: "CRITICAL",
      });

      await enrichSingleCVE("CVE-2024-21413", {
        include_attack_path: true,
        include_compliance: true,
      });

      const url = mockApiRequest.mock.calls[0][0] as string;
      expect(url).toContain("/v1/enrich/CVE-2024-21413?");
      expect(url).toContain("include_attack_path=true");
      expect(url).toContain("include_compliance=true");
    });

    it("does not append params when options are false", async () => {
      mockApiRequest.mockResolvedValueOnce({
        cve_id: "CVE-2021-44228",
        risk_score: 0.95,
        priority: "CRITICAL",
      });

      await enrichSingleCVE("CVE-2021-44228", {
        include_attack_path: false,
        include_compliance: false,
      });

      expect(mockApiRequest).toHaveBeenCalledWith(
        "/v1/enrich/CVE-2021-44228"
      );
    });
  });

  describe("enrichRegulatory", () => {
    it("calls POST /v1/enrich/regulatory with CVE ID", async () => {
      mockApiRequest.mockResolvedValueOnce({
        cve_id: "CVE-2021-44228",
        nvd_data: { published: "2021-12-10T10:15:00.000Z" },
        exploit_intelligence: { in_kev: true },
        regulatory_triggers: [
          {
            framework: "FDA 524B",
            requirement_id: "KEV_RESPONSE",
            requirement_title: "Known Exploited Vulnerability Response",
            urgency: "24h",
            trigger_rule: "kev_entry",
            confidence: 1.0,
            evidence: {},
            trigger_timestamp: "2026-03-05T12:00:00Z",
          },
        ],
      });

      const result = await enrichRegulatory("CVE-2021-44228");

      expect(mockApiRequest).toHaveBeenCalledWith("/v1/enrich/regulatory", {
        method: "POST",
        body: JSON.stringify({ cve_id: "CVE-2021-44228" }),
      });
      expect(result.cve_id).toBe("CVE-2021-44228");
      expect(result.regulatory_triggers).toHaveLength(1);
      expect(result.regulatory_triggers[0].framework).toBe("FDA 524B");
    });

    it("returns empty triggers when none found", async () => {
      mockApiRequest.mockResolvedValueOnce({
        cve_id: "CVE-2024-0001",
        nvd_data: null,
        exploit_intelligence: null,
        regulatory_triggers: [],
      });

      const result = await enrichRegulatory("CVE-2024-0001");

      expect(result.regulatory_triggers).toHaveLength(0);
    });
  });
});
