import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, customInstance } from "./client";
import { subscribeToSessionExpired } from "./session-expired";

const SESSION_EXPIRED = "Your session has expired. Sign in again.";

function answer401() {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: SESSION_EXPIRED }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }),
    ),
  );
}

afterEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
});

describe("customInstance and a rejected session", () => {
  it("ends the session when the API rejects a signed-in request", async () => {
    localStorage.setItem("dataing_access_token", "stale-token");
    answer401();
    const expired = vi.fn();
    const unsubscribe = subscribeToSessionExpired(expired);

    const request = customInstance({ url: "/api/v1/issues", method: "GET" });

    await expect(request).rejects.toBeInstanceOf(ApiError);
    await expect(request).rejects.toMatchObject({
      status: 401,
      message: SESSION_EXPIRED,
    });
    expect(expired).toHaveBeenCalledTimes(1);
    unsubscribe();
  });

  it("leaves a failed sign-in alone: wrong passwords are 401s too", async () => {
    localStorage.setItem("dataing_access_token", "stale-token");
    answer401();
    const expired = vi.fn();
    const unsubscribe = subscribeToSessionExpired(expired);

    await expect(
      customInstance({ url: "/api/v1/auth/login", method: "POST", data: {} }),
    ).rejects.toBeInstanceOf(ApiError);

    expect(expired).not.toHaveBeenCalled();
    unsubscribe();
  });

  it("has no session to end when nobody is signed in", async () => {
    answer401();
    const expired = vi.fn();
    const unsubscribe = subscribeToSessionExpired(expired);

    await expect(
      customInstance({ url: "/api/v1/issues", method: "GET" }),
    ).rejects.toBeInstanceOf(ApiError);

    expect(expired).not.toHaveBeenCalled();
    unsubscribe();
  });
});
