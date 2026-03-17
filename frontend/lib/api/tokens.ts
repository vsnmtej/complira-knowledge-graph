/**
 * API client for token management endpoints.
 *
 * Handles all API token CRUD operations.
 */

import { apiRequest } from "@/lib/api-client";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface APIToken {
  id: string;
  organization_id: string;
  created_by_user_id: string;
  name: string;
  description?: string;
  token_prefix: string;
  scopes: string[];
  rate_limit: number;
  created_at: string;
  expires_at: string;
  last_used?: string;
  revoked: boolean;
  revoked_at?: string;
  revoked_by_user_id?: string;
}

export interface CreateTokenRequest {
  name: string;
  description?: string;
  scopes: string[];
  rate_limit?: number;
  expires_in_days?: number;
}

export interface CreateTokenResponse {
  success: boolean;
  message: string;
  token: string;
  token_id: string;
  token_prefix: string;
  expires_at: string;
}

export interface ListTokensResponse {
  tokens: APIToken[];
  total: number;
  page: number;
  page_size: number;
}

export interface RotateTokenResponse {
  success: boolean;
  message: string;
  new_token: string;
  token_id: string;
  token_prefix: string;
  old_token_expires_at: string;
  new_token_expires_at: string;
}

export interface RevokeTokenResponse {
  success: boolean;
  message: string;
  token_id: string;
  revoked_at: string;
}

/**
 * Get authentication headers with access token.
 */
async function getAuthHeaders(): Promise<HeadersInit> {
  // Get session from NextAuth
  const { getSession } = await import("next-auth/react");
  const session = await getSession();

  if (!session?.accessToken) {
    throw new Error("Not authenticated");
  }

  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${session.accessToken}`,
  };
}

/**
 * List all API tokens for the organization.
 */
export async function listTokens(params: {
  include_revoked?: boolean;
  page?: number;
  page_size?: number;
}): Promise<ListTokensResponse> {
  const queryParams = new URLSearchParams();
  if (params.include_revoked !== undefined) {
    queryParams.append("include_revoked", params.include_revoked.toString());
  }
  if (params.page) queryParams.append("page", params.page.toString());
  if (params.page_size)
    queryParams.append("page_size", params.page_size.toString());

  return apiRequest<ListTokensResponse>(
    `/v1/tokens?${queryParams.toString()}`
  );
}

/**
 * Create new API token.
 */
export async function createToken(
  data: CreateTokenRequest
): Promise<CreateTokenResponse> {
  return apiRequest<CreateTokenResponse>(`/v1/tokens`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

/**
 * Get API token by ID.
 */
export async function getToken(tokenId: string): Promise<APIToken> {
  return apiRequest<APIToken>(`/v1/tokens/${tokenId}`);
}

/**
 * Update API token metadata.
 */
export async function updateToken(
  tokenId: string,
  data: {
    name?: string;
    description?: string;
    scopes?: string[];
  }
): Promise<APIToken> {
  return apiRequest<APIToken>(`/v1/tokens/${tokenId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

/**
 * Rotate API token secret.
 */
export async function rotateToken(
  tokenId: string,
  gracePeriodHours: number = 24
): Promise<RotateTokenResponse> {
  return apiRequest<RotateTokenResponse>(`/v1/tokens/${tokenId}/rotate`, {
    method: "POST",
    body: JSON.stringify({ grace_period_hours: gracePeriodHours }),
  });
}

/**
 * Revoke API token (immediate, irreversible).
 */
export async function revokeToken(
  tokenId: string
): Promise<RevokeTokenResponse> {
  return apiRequest<RevokeTokenResponse>(`/v1/tokens/${tokenId}/revoke`, {
    method: "POST",
  });
}

/**
 * Delete API token (permanent).
 */
export async function deleteToken(tokenId: string): Promise<void> {
  return apiRequest<void>(`/v1/tokens/${tokenId}`, {
    method: "DELETE",
  });
}
