import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { Markdown } from "./markdown";

describe("Markdown", () => {
  it("renders GitHub-flavoured markdown", () => {
    const { container } = render(
      <Markdown>
        {"**bold** and `code`\n\n| a | b |\n|---|---|\n| 1 | 2 |"}
      </Markdown>,
    );

    expect(screen.getByText("bold").tagName).toBe("STRONG");
    expect(screen.getByText("code").tagName).toBe("CODE");
    expect(container.querySelector("table")).not.toBeNull();
  });

  it("drops raw HTML and unsafe links", () => {
    const { container } = render(
      <Markdown>
        {'<img src=x onerror="alert(1)"> [click](javascript:alert(1))'}
      </Markdown>,
    );

    expect(container.querySelector("img")).toBeNull();
    const link = screen.getByText("click");
    expect(link.getAttribute("href") ?? "").not.toContain("javascript:");
  });
});
