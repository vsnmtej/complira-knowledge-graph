/**
 * API client for account management endpoints.
 *
 * Handles legacy API key CRUD operations (separate from JWT tokens).
 */

import { apiRequest } from "@/lib/api-client";

// --- Types ---

export interface APIKey {
  key_id: string;
  name: string;
  description?: string;
  key_prefix: string;
  created_at: string;
  expires_at?: string;
  last_used_at?: string;
  revoked: boolean;
  revoked_at?: string;
  revoked_reason?: string;
}

export interface CreateAPIKeyRequest {
  name: string;
  description?: string;
  expires_days?: number;
}

export interface CreateAPIKeyResponse {
  success: boolean;
  data: {
    key_id: string;
    name: string;
    api_key: string;
    created_at: string;
    expires_at?: string;
    warning: string;
  };
}

export interface ListAPIKeysResponse {
  success: boolean;
  data: {
    keys: APIKey[];
    total: number;
    active: number;
  };
}

export interface RevokeAPIKeyResponse {
  success: boolean;
  data: {
    key_id: string;
    revoked: boolean;
    revoked_at: string;
    message: string;
  };
}

// --- API Functions ---

/**
 * Create a new legacy API key.
 */
export async function createAPIKey(
  data: CreateAPIKeyRequest
): Promise<CreateAPIKeyResponse> {
  return apiRequest<CreateAPIKeyResponse>("/v1/account/api-keys", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

/**
 * List all API keys for the current customer.
 */
export async function listAPIKeys(): Promise<ListAPIKeysResponse> {
  return apiRequest<ListAPIKeysResponse>("/v1/account/api-keys");
}

/**
 * Revoke an API key by ID.
 */
export async function revokeAPIKey(
  keyId: string,
  reason?: string
): Promise<RevokeAPIKeyResponse> {
  return apiRequest<RevokeAPIKeyResponse>(`/v1/account/api-keys/${keyId}`, {
    method: "DELETE",
    body: JSON.stringify({ reason }),
  });
}
