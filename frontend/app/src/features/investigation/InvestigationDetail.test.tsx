import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import type { OrgRole } from "@/lib/auth/types";
import { renderAsRole } from "@/test/auth";
import { InvestigationDetail } from "./InvestigationDetail";

const investigation = vi.hoisted(() => ({
  current: {} as Record<string, unknown>,
}));

vi.mock("@/lib/api/investigations", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/investigations")>()),
  useInvestigation: () => ({
    data: investigation.current,
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }),
  useSendMessage: () => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
    error: null,
  }),
  subscribeToInvestigation: () => () => undefined,
}));

vi.mock(
  "@/lib/api/generated/investigations/investigations",
  async (importOriginal) => ({
    ...(await importOriginal<
      typeof import("@/lib/api/generated/investigations/investigations")
    >()),
    useCancelInvestigationApiV1InvestigationsInvestigationIdCancelPost: () => ({
      mutateAsync: vi.fn(),
      isPending: false,
    }),
  }),
);

function investigationWith(status: string, synthesis: unknown) {
  return {
    investigation_id: "inv-1",
    status,
    main_branch: {
      current_step: "gather_context",
      step_history: [],
      matched_patterns: [],
      synthesis,
      evidence: [],
    },
  };
}

function renderDetail(role: OrgRole) {
  return renderAsRole(
    <Routes>
      <Route path="/investigations/:id" element={<InvestigationDetail />} />
    </Routes>,
    role,
    "/investigations/inv-1",
  );
}

afterEach(() => localStorage.clear());

describe("InvestigationDetail while running", () => {
  it("does not let viewers steer, branch or cancel the investigation", async () => {
    investigation.current = investigationWith("in_progress", null);
    renderDetail("viewer");

    expect(
      await screen.findByText("Investigation Progress"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Cancel Investigation")).not.toBeInTheDocument();
    expect(screen.queryByText("Collaborate")).not.toBeInTheDocument();
    expect(
      screen.queryByPlaceholderText("Ask a question or provide direction..."),
    ).not.toBeInTheDocument();
  });

  it("lets members steer, branch and cancel the investigation", async () => {
    investigation.current = investigationWith("in_progress", null);
    renderDetail("member");

    expect(await screen.findByText("Cancel Investigation")).toBeInTheDocument();
    expect(screen.getByText("Collaborate")).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText("Ask a question or provide direction..."),
    ).toBeInTheDocument();
  });
});

describe("InvestigationDetail once completed", () => {
  const synthesis = {
    root_cause: "An upstream job skipped a partition",
    confidence: 0.9,
  };

  it("does not offer viewers test codification", async () => {
    investigation.current = investigationWith("completed", synthesis);
    renderDetail("viewer");

    expect(
      await screen.findByText("An upstream job skipped a partition"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Codify Test")).not.toBeInTheDocument();
  });

  it("offers members test codification", async () => {
    investigation.current = investigationWith("completed", synthesis);
    renderDetail("member");

    expect(await screen.findByText("Codify Test")).toBeInTheDocument();
  });
});
