/**
 * Tests for account API client.
 *
 * Verifies all 3 account endpoints match backend routes.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { createAPIKey, listAPIKeys, revokeAPIKey } from "../account";

vi.mock("@/lib/api-client", () => ({
  apiRequest: vi.fn(),
}));

import { apiRequest } from "@/lib/api-client";
const mockApiRequest = vi.mocked(apiRequest);

describe("Account API Client", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("createAPIKey", () => {
    it("calls POST /v1/account/api-keys with correct body", async () => {
      const request = {
        name: "Production Server",
        description: "Key for production deployment",
        expires_days: 90,
      };

      mockApiRequest.mockResolvedValueOnce({
        success: true,
        data: {
          key_id: "key_abc123",
          name: "Production Server",
          api_key: "aBcDeFgHiJkLmNoPqRsTuVwXyZ123456789012345678",
          created_at: "2026-03-17T00:00:00Z",
          expires_at: "2026-06-15T00:00:00Z",
          warning: "Save this API key securely.",
        },
      });

      const result = await createAPIKey(request);

      expect(mockApiRequest).toHaveBeenCalledWith("/v1/account/api-keys", {
        method: "POST",
        body: JSON.stringify(request),
      });
      expect(result.success).toBe(true);
      expect(result.data.api_key).toBeTruthy();
      expect(result.data.key_id).toBe("key_abc123");
    });

    it("sends only name when optional fields are omitted", async () => {
      const request = { name: "Minimal Key" };

      mockApiRequest.mockResolvedValueOnce({
        success: true,
        data: {
          key_id: "key_def456",
          name: "Minimal Key",
          api_key: "someKey123",
          created_at: "2026-03-17T00:00:00Z",
          warning: "Save this API key securely.",
        },
      });

      await createAPIKey(request);

      expect(mockApiRequest).toHaveBeenCalledWith("/v1/account/api-keys", {
        method: "POST",
        body: JSON.stringify({ name: "Minimal Key" }),
      });
    });
  });

  describe("listAPIKeys", () => {
    it("calls GET /v1/account/api-keys", async () => {
      mockApiRequest.mockResolvedValueOnce({
        success: true,
        data: {
          keys: [
            {
              key_id: "key_abc123",
              name: "Production",
              key_prefix: "aBcDeFgH",
              created_at: "2026-03-17T00:00:00Z",
              revoked: false,
            },
          ],
          total: 1,
          active: 1,
        },
      });

      const result = await listAPIKeys();

      expect(mockApiRequest).toHaveBeenCalledWith("/v1/account/api-keys");
      expect(result.data.keys).toHaveLength(1);
      expect(result.data.total).toBe(1);
      expect(result.data.active).toBe(1);
    });

    it("returns empty list when no keys exist", async () => {
      mockApiRequest.mockResolvedValueOnce({
        success: true,
        data: { keys: [], total: 0, active: 0 },
      });

      const result = await listAPIKeys();

      expect(result.data.keys).toHaveLength(0);
    });
  });

  describe("revokeAPIKey", () => {
    it("calls DELETE /v1/account/api-keys/{key_id} with reason", async () => {
      mockApiRequest.mockResolvedValueOnce({
        success: true,
        data: {
          key_id: "key_abc123",
          revoked: true,
          revoked_at: "2026-03-17T12:00:00Z",
          message: "API key has been revoked and can no longer be used",
        },
      });

      const result = await revokeAPIKey("key_abc123", "Key compromised");

      expect(mockApiRequest).toHaveBeenCalledWith(
        "/v1/account/api-keys/key_abc123",
        {
          method: "DELETE",
          body: JSON.stringify({ reason: "Key compromised" }),
        }
      );
      expect(result.data.revoked).toBe(true);
    });

    it("calls DELETE without reason when not provided", async () => {
      mockApiRequest.mockResolvedValueOnce({
        success: true,
        data: {
          key_id: "key_abc123",
          revoked: true,
          revoked_at: "2026-03-17T12:00:00Z",
          message: "API key has been revoked",
        },
      });

      await revokeAPIKey("key_abc123");

      expect(mockApiRequest).toHaveBeenCalledWith(
        "/v1/account/api-keys/key_abc123",
        {
          method: "DELETE",
          body: JSON.stringify({ reason: undefined }),
        }
      );
    });
  });
});
