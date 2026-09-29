import { afterEach, describe, expect, it, vi } from "vitest";
import { act, screen, waitFor } from "@testing-library/react";

import { stubApi, type StubResponse } from "@/test/api";
import { renderAsRole } from "@/test/auth";

import { LlmStatusBanner } from "./llm-status-banner";

const LLM = "/api/v1/system/llm";

function llm(state: string, message = "") {
  return {
    body: {
      state,
      message,
      models: ["claude-opus-5-5"],
      checked_at: "2026-09-28T08:00:00Z",
    },
  };
}

const INVALID_KEY = llm(
  "invalid_key",
  "Anthropic rejected the API key (401). Set a valid ANTHROPIC_API_KEY and restart the API and the worker.",
);

function renderBanner(response: StubResponse | (() => StubResponse)) {
  const api = stubApi({ [`GET ${LLM}`]: response });
  renderAsRole(
    <>
      <p>Page</p>
      <LlmStatusBanner />
    </>,
    "viewer",
  );
  return api;
}

/** React Query hands results over on a zero-delay timer. */
async function flush() {
  await act(() => new Promise((resolve) => setTimeout(resolve, 0)));
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("LlmStatusBanner", () => {
  it("says what to fix when the key is rejected", async () => {
    renderBanner(INVALID_KEY);

    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent(
      "Anthropic rejected the API key (401). Set a valid ANTHROPIC_API_KEY and restart the API and the worker.",
    );
    expect(banner).toHaveTextContent(
      "Investigations and the agent can't run until this is fixed.",
    );
    expect(banner.className).toContain("destructive");
    // It stays until the problem does: there is nothing to dismiss it with.
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it.each(["ok", "checking"])(
    "stays out of the way while %s",
    async (state) => {
      const api = renderBanner(llm(state));

      expect(await screen.findByText("Page")).toBeInTheDocument();
      await waitFor(() => expect(api.find("GET", LLM)).toHaveLength(1));
      await flush();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    },
  );

  it("warns, rather than alarms, when Anthropic is unreachable", async () => {
    renderBanner(
      llm("unreachable", "Couldn't reach Anthropic: connection timed out."),
    );

    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent(
      "Couldn't reach Anthropic: connection timed out.",
    );
    expect(banner.className).toContain("amber");
    expect(banner.className).not.toContain("destructive");
  });

  it("shows nothing when the status can't be read", async () => {
    const api = renderBanner({ status: 500, body: { detail: "boom" } });

    await waitFor(() => expect(api.find("GET", LLM)).toHaveLength(1));
    await flush();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("checks again once a minute and clears when the key works", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let response = INVALID_KEY;
    const api = renderBanner(() => response);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    response = llm("ok");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(59_000);
    });
    expect(api.find("GET", LLM)).toHaveLength(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_500);
    });
    expect(api.find("GET", LLM)).toHaveLength(2);
    await waitFor(() =>
      expect(screen.queryByRole("alert")).not.toBeInTheDocument(),
    );
  });
});
