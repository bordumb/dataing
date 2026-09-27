import { afterEach, describe, expect, it, vi } from "vitest";

import { login } from "@/lib/auth/api";
import { apiErrorMessage } from "./error-message";

describe("apiErrorMessage", () => {
  it("returns a string detail as-is", () => {
    expect(apiErrorMessage({ detail: "Invalid email or password" }, 401)).toBe(
      "Invalid email or password",
    );
  });

  it("turns FastAPI validation errors into field messages", () => {
    const body = {
      detail: [
        {
          type: "uuid_parsing",
          loc: ["body", "org_id"],
          msg: "Input should be a valid UUID",
        },
        { type: "missing", loc: ["body", "email"], msg: "Field required" },
      ],
    };

    expect(apiErrorMessage(body, 422)).toBe(
      "org_id: Input should be a valid UUID; email: Field required",
    );
  });

  it("uses the message of a structured detail", () => {
    const body = {
      detail: { error: "limit_exceeded", message: "Seat limit reached" },
    };

    expect(apiErrorMessage(body, 403)).toBe("Seat limit reached");
  });

  it("falls back to the status when the body has no usable detail", () => {
    expect(apiErrorMessage({}, 500)).toBe("HTTP error 500");
    expect(apiErrorMessage({ detail: { code: 7 } }, 500)).toBe(
      "HTTP error 500",
    );
    expect(apiErrorMessage(null, 502)).toBe("HTTP error 502");
  });

  it("prefers a caller fallback over the bare status", () => {
    expect(apiErrorMessage({}, 401, "Invalid credentials")).toBe(
      "Invalid credentials",
    );
  });
});

describe("login errors", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows validation errors as text, not [object Object]", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: [
              {
                type: "uuid_parsing",
                loc: ["body", "org_id"],
                msg: "Input should be a valid UUID",
              },
            ],
          }),
          { status: 422, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    await expect(
      login({
        email: "demo@dataing.io",
        password: "demo123456", // pragma: allowlist secret
        org_id: "demo",
      }),
    ).rejects.toThrow("org_id: Input should be a valid UUID");
  });
});
