/**
 * Share API Client
 *
 * Functions for creating and accessing public share links for investigations.
 */

import { api } from "./client";

export interface ShareLink {
  id?: string;
  url: string;
  token: string;
  expires_at: string;
  expires_in?: string;
  investigation_id: string;
}

export interface SharedInvestigation {
  id: string;
  status: string;
  anomaly_type: string;
  input_context: string;
  result: string | null;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  user_name: string | null;
}

/**
 * Create a public share link for an investigation.
 *
 * @param investigationId - The investigation ID to share
 * @param expiresInDays - Number of days until the link expires (1-90)
 * @returns Share link details
 */
export async function createShareLink(
  investigationId: string,
  expiresInDays: number = 7
): Promise<ShareLink> {
  const response = await api.post<ShareLink>(
    `/api/v1/investigations/${investigationId}/share?expires_in_days=${expiresInDays}`,
    {}
  );

  return {
    ...response,
    expires_in: `${expiresInDays}d`,
  };
}

/**
 * Get investigation details from a public share token.
 *
 * This function does NOT require authentication - it's used by the public share page.
 *
 * @param token - The share token from the URL
 * @returns Investigation details for public viewing
 */
export async function getSharedInvestigation(
  token: string
): Promise<SharedInvestigation> {
  // Use direct fetch instead of api client to avoid auth headers
  const API_BASE_URL = typeof window === 'undefined'
    ? (process.env.API_INTERNAL_URL || "http://api:8000")
    : (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000");

  const response = await fetch(
    `${API_BASE_URL}/api/v1/investigations/shared/${token}`,
    {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
    }
  );

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error("Share link not found or expired");
    }
    throw new Error(`Failed to fetch shared investigation: ${response.statusText}`);
  }

  return response.json();
}
