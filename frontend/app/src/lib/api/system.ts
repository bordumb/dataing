/**
 * Whether the LLM key and models work (spec 0001 §7.12). The API checks them
 * at startup; every page shows a banner while they don't.
 */

import { useQuery } from "@tanstack/react-query";

import { customInstance } from "./client";
import { queryKeys } from "./query-keys";

/** `ok`, `checking`, or the code classify_llm_error gives the failure. */
export type LlmState =
  | "ok"
  | "checking"
  | "missing_key"
  | "invalid_key"
  | "forbidden"
  | "unknown_model"
  | "bad_request"
  | "rate_limited"
  | "overloaded"
  | "server_error"
  | "unreachable";

export interface LlmStatus {
  state: LlmState | string;
  /** What is wrong and what to fix, e.g. which variable to set. */
  message: string;
  models: string[];
  checked_at: string | null;
}

/** How often the app asks again. */
export const LLM_STATUS_POLL_MS = 60_000;

export function getLlmStatus(signal?: AbortSignal) {
  return customInstance<LlmStatus>({
    url: "/api/v1/system/llm",
    method: "GET",
    signal,
  });
}

export function useLlmStatus() {
  return useQuery({
    queryKey: queryKeys.system.llm,
    queryFn: ({ signal }) => getLlmStatus(signal),
    refetchInterval: LLM_STATUS_POLL_MS,
    staleTime: LLM_STATUS_POLL_MS / 2,
  });
}
