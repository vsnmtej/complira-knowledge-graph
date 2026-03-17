/**
 * Tests for token API client.
 *
 * Verifies all 7 token endpoints match backend routes.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { listTokens, createToken, getToken, updateToken, rotateToken, revokeToken, deleteToken } from "../tokens";

vi.mock("@/lib/api-client", () => ({
  apiRequest: vi.fn(),
}));

import { apiRequest } from "@/lib/api-client";
const mockApiRequest = vi.mocked(apiRequest);

describe("Tokens API Client", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("listTokens", () => {
    it("calls GET /v1/tokens with query params", async () => {
      mockApiRequest.mockResolvedValueOnce({ tokens: [], total: 0, page: 1, page_size: 20 });

      await listTokens({ include_revoked: true, page: 2, page_size: 10 });

      const url = mockApiRequest.mock.calls[0][0] as string;
      expect(url).toContain("/v1/tokens?");
      expect(url).toContain("include_revoked=true");
      expect(url).toContain("page=2");
      expect(url).toContain("page_size=10");
    });
  });

  describe("createToken", () => {
    it("calls POST /v1/tokens with correct body", async () => {
      const request = {
        name: "CI/CD Token",
        scopes: ["scan:write"],
        rate_limit: 1000,
        expires_in_days: 365,
      };

      mockApiRequest.mockResolvedValueOnce({
        success: true,
        token: "complira_tk_abc123",
        token_id: "token_abc",
        token_prefix: "complira_tk_abc",
        expires_at: "2027-01-01T00:00:00Z",
      });

      const result = await createToken(request);

      expect(mockApiRequest).toHaveBeenCalledWith("/v1/tokens", {
        method: "POST",
        body: JSON.stringify(request),
      });
      expect(result.token).toContain("complira_tk_");
    });
  });

  describe("getToken", () => {
    it("calls GET /v1/tokens/{tokenId}", async () => {
      mockApiRequest.mockResolvedValueOnce({ id: "token_abc" });

      await getToken("token_abc");

      expect(mockApiRequest).toHaveBeenCalledWith("/v1/tokens/token_abc");
    });
  });

  describe("updateToken", () => {
    it("calls PATCH /v1/tokens/{tokenId}", async () => {
      mockApiRequest.mockResolvedValueOnce({ id: "token_abc", name: "Updated" });

      await updateToken("token_abc", { name: "Updated" });

      expect(mockApiRequest).toHaveBeenCalledWith("/v1/tokens/token_abc", {
        method: "PATCH",
        body: JSON.stringify({ name: "Updated" }),
      });
    });
  });

  describe("rotateToken", () => {
    it("calls POST /v1/tokens/{tokenId}/rotate with grace period", async () => {
      mockApiRequest.mockResolvedValueOnce({ success: true, new_token: "complira_tk_new" });

      await rotateToken("token_abc", 48);

      expect(mockApiRequest).toHaveBeenCalledWith("/v1/tokens/token_abc/rotate", {
        method: "POST",
        body: JSON.stringify({ grace_period_hours: 48 }),
      });
    });

    it("defaults to 24h grace period", async () => {
      mockApiRequest.mockResolvedValueOnce({ success: true });

      await rotateToken("token_abc");

      const body = JSON.parse((mockApiRequest.mock.calls[0][1] as any).body);
      expect(body.grace_period_hours).toBe(24);
    });
  });

  describe("revokeToken", () => {
    it("calls POST /v1/tokens/{tokenId}/revoke", async () => {
      mockApiRequest.mockResolvedValueOnce({ success: true, token_id: "token_abc" });

      await revokeToken("token_abc");

      expect(mockApiRequest).toHaveBeenCalledWith("/v1/tokens/token_abc/revoke", {
        method: "POST",
      });
    });
  });

  describe("deleteToken", () => {
    it("calls DELETE /v1/tokens/{tokenId}", async () => {
      mockApiRequest.mockResolvedValueOnce(undefined);

      await deleteToken("token_abc");

      expect(mockApiRequest).toHaveBeenCalledWith("/v1/tokens/token_abc", {
        method: "DELETE",
      });
    });
  });
});
