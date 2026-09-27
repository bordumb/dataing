import { afterEach, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderAsRole } from "@/test/auth";
import { DemoRoleProvider, useDemoRoleContext } from "./demo-role-context";
import { useRole } from "./use-role";

function RoleProbe() {
  const demo = useDemoRoleContext();
  const { role, isAdmin } = useRole();
  return (
    <div>
      <p>
        demo:{demo.role} effective:{role} admin:{String(isAdmin)}
      </p>
      <button onClick={() => demo.setRole("admin")}>Preview as admin</button>
    </div>
  );
}

function renderProbe() {
  return renderAsRole(
    <DemoRoleProvider>
      <RoleProbe />
    </DemoRoleProvider>,
    "viewer",
  );
}

afterEach(() => localStorage.clear());

describe("DemoRoleProvider", () => {
  it("starts from the signed-in user's real role", async () => {
    renderProbe();

    expect(
      await screen.findByText("demo:viewer effective:viewer admin:false"),
    ).toBeInTheDocument();
  });

  it("previews another role through useRole", async () => {
    renderProbe();

    await userEvent.click(await screen.findByText("Preview as admin"));

    expect(
      await screen.findByText("demo:admin effective:admin admin:true"),
    ).toBeInTheDocument();
  });
});
