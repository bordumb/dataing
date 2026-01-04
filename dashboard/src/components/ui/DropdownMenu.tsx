"use client";

import { createContext, useContext, useState } from "react";
import clsx from "clsx";

interface DropdownContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
}

const DropdownContext = createContext<DropdownContextValue | null>(null);

export function DropdownMenu({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <DropdownContext.Provider value={{ open, setOpen }}>
      <div className="relative inline-block">{children}</div>
    </DropdownContext.Provider>
  );
}

export function DropdownTrigger({ children }: { children: React.ReactNode }) {
  const context = useContext(DropdownContext);
  if (!context) return null;
  return (
    <button
      onClick={() => context.setOpen(!context.open)}
      className="inline-flex items-center gap-2 rounded-full border border-border bg-background-elevated/80 px-3 py-1.5 text-sm font-semibold text-foreground transition hover:border-border-strong hover:bg-background-subtle"
    >
      {children}
    </button>
  );
}

export function DropdownContent({ children, className }: { children: React.ReactNode; className?: string }) {
  const context = useContext(DropdownContext);
  if (!context?.open) return null;
  return (
    <div
      className={clsx(
        "absolute right-0 z-20 mt-2 min-w-[180px] rounded-xl border border-border bg-background-elevated p-2 text-foreground shadow-soft",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function DropdownItem({
  children,
  onClick,
}: {
  children: React.ReactNode;
  onClick?: () => void;
}) {
  const context = useContext(DropdownContext);
  return (
    <button
      className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-foreground hover:bg-background-subtle"
      onClick={() => {
        onClick?.();
        context?.setOpen(false);
      }}
    >
      {children}
    </button>
  );
}
