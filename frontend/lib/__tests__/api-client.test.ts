/**
 * Tests for the shared API client.
 *
 * Verifies auth headers, token refresh, and error handling.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Must mock next-auth/react before importing api-client
vi.mock("next-auth/react", () => ({
  getSession: vi.fn().mockResolvedValue({
    accessToken: "valid_token",
    refreshToken: "valid_refresh",
  }),
  signOut: vi.fn(),
}));

import { apiRequest, getAuthHeaders } from "../api-client";
import { getSession } from "next-auth/react";

describe("API Client", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("getAuthHeaders", () => {
    it("returns Authorization header with access token", async () => {
      const headers = await getAuthHeaders();

      expect(headers).toEqual({
        "Content-Type": "application/json",
        Authorization: "Bearer valid_token",
      });
    });

    it("throws when not authenticated", async () => {
      vi.mocked(getSession).mockResolvedValueOnce(null);

      await expect(getAuthHeaders()).rejects.toThrow("Not authenticated");
    });
  });

  describe("apiRequest", () => {
    it("makes authenticated request to correct URL", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true }),
      });

      const result = await apiRequest("/v1/test");

      expect(mockFetch).toHaveBeenCalledWith(
        "http://localhost:8000/v1/test",
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: "Bearer valid_token",
          }),
        })
      );
      expect(result).toEqual({ success: true });
    });

    it("retries with refreshed token on 401", async () => {
      // First call returns 401
      mockFetch
        .mockResolvedValueOnce({
          ok: false,
          status: 401,
          json: () => Promise.resolve({ detail: "Unauthorized" }),
        })
        // Refresh call succeeds
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({
            access_token: "new_token",
            refresh_token: "new_refresh",
            expires_in: 900,
          }),
        })
        // Retry succeeds
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ success: true }),
        })
        // Session update
        .mockResolvedValueOnce({ ok: true });

      const result = await apiRequest("/v1/test");

      expect(result).toEqual({ success: true });
      // Should have made 4 fetch calls: original, refresh, retry, session update
      expect(mockFetch).toHaveBeenCalledTimes(4);
    });

    it("throws with error detail on non-401 failure", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: "Not Found",
        json: () => Promise.resolve({ detail: "Resource not found" }),
      });

      await expect(apiRequest("/v1/missing")).rejects.toThrow("Resource not found");
    });

    it("passes custom headers and method", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({}),
      });

      await apiRequest("/v1/test", {
        method: "POST",
        body: JSON.stringify({ key: "value" }),
      });

      expect(mockFetch).toHaveBeenCalledWith(
        "http://localhost:8000/v1/test",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ key: "value" }),
        })
      );
    });
  });
});
