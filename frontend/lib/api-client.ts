/**
 * Shared API client with automatic token refresh.
 *
 * Handles authentication, token refresh, and error handling for all API calls.
 */

import { getSession } from "next-auth/react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Refresh the access token using the refresh token.
 */
async function refreshAccessToken(refreshToken: string): Promise<{
  access_token: string;
  refresh_token: string;
  expires_in: number;
} | null> {
  try {
    const response = await fetch(`${API_URL}/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!response.ok) {
      console.error("Token refresh failed:", await response.text());
      return null;
    }

    return response.json();
  } catch (error) {
    console.error("Token refresh error:", error);
    return null;
  }
}

/**
 * Get authentication headers with valid access token.
 * Automatically refreshes token if expired.
 */
export async function getAuthHeaders(): Promise<HeadersInit> {
  const session = await getSession();

  if (!session?.accessToken) {
    throw new Error("Not authenticated");
  }

  // Try with current token first
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${session.accessToken}`,
  };
}

/**
 * Make an authenticated API request with automatic token refresh.
 */
export async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const session = await getSession();

  if (!session?.accessToken) {
    throw new Error("Not authenticated");
  }

  // First attempt with current token
  let response = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
      Authorization: `Bearer ${session.accessToken}`,
    },
  });

  // If unauthorized and we have a refresh token, try to refresh
  if (response.status === 401 && session.refreshToken) {
    console.log("Access token expired, refreshing...");

    const refreshed = await refreshAccessToken(session.refreshToken);

    if (refreshed) {
      // Retry with the new access token
      response = await fetch(`${API_URL}${endpoint}`, {
        ...options,
        headers: {
          "Content-Type": "application/json",
          ...options.headers,
          Authorization: `Bearer ${refreshed.access_token}`,
        },
      });

      // Trigger NextAuth session update so JWT callback refreshes tokens
      if (response.ok) {
        try {
          // Use NextAuth's CSRF-protected session update endpoint
          const csrfResponse = await fetch("/api/auth/csrf");
          const { csrfToken } = await csrfResponse.json();
          await fetch("/api/auth/session", {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: new URLSearchParams({ csrfToken }),
          });
        } catch {
          // Session update is best-effort; the retry already succeeded
        }
      }
    } else {
      // Refresh failed, sign out and redirect to login
      console.error("Token refresh failed, signing out...");
      const { signOut } = await import("next-auth/react");
      await signOut({ redirect: true, callbackUrl: "/login" });
      throw new Error("Session expired. Please log in again.");
    }
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({
      detail: `HTTP ${response.status}: ${response.statusText}`,
    }));

    // Create an error with the full error data attached
    const error: any = new Error(errorData.detail || "Request failed");
    error.statusCode = response.status;
    error.data = errorData;
    throw error;
  }

  return response.json();
}
