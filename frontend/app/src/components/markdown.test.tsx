import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

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

  it("opens app pages in place and other links in a new tab", () => {
    render(
      <MemoryRouter>
        <Markdown>
          {
            "[Add your login](/settings/datasources/ds-1/credentials) or read [the docs](https://example.com)"
          }
        </Markdown>
      </MemoryRouter>,
    );

    const page = screen.getByRole("link", { name: "Add your login" });
    expect(page).toHaveAttribute(
      "href",
      "/settings/datasources/ds-1/credentials",
    );
    expect(page).not.toHaveAttribute("target");
    expect(screen.getByRole("link", { name: "the docs" })).toHaveAttribute(
      "target",
      "_blank",
    );
  });
});
