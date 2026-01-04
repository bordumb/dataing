"use client";

import { createContext, useContext, useState, useCallback } from "react";
import { X } from "lucide-react";
import clsx from "clsx";

interface DialogContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
}

const DialogContext = createContext<DialogContextValue | null>(null);

interface DialogProps {
  children: React.ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export function Dialog({ children, open: controlledOpen, onOpenChange }: DialogProps) {
  const [internalOpen, setInternalOpen] = useState(false);

  const isControlled = controlledOpen !== undefined;
  const open = isControlled ? controlledOpen : internalOpen;

  const setOpen = useCallback(
    (newOpen: boolean) => {
      if (onOpenChange) {
        onOpenChange(newOpen);
      }
      if (!isControlled) {
        setInternalOpen(newOpen);
      }
    },
    [isControlled, onOpenChange]
  );

  return <DialogContext.Provider value={{ open, setOpen }}>{children}</DialogContext.Provider>;
}

export function DialogTrigger({ children }: { children: React.ReactNode }) {
  const context = useContext(DialogContext);
  if (!context) return null;
  return <span onClick={() => context.setOpen(true)}>{children}</span>;
}

export function DialogClose({ children }: { children: React.ReactNode }) {
  const context = useContext(DialogContext);
  if (!context) return null;
  return <span onClick={() => context.setOpen(false)}>{children}</span>;
}

export function DialogContent({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const context = useContext(DialogContext);
  if (!context?.open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-scrim/40 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          context.setOpen(false);
        }
      }}
    >
      <div
        className={clsx(
          "w-full max-w-lg rounded-2xl bg-background-elevated p-6 shadow-soft",
          className
        )}
      >
        <button
          className="absolute right-4 top-4 rounded-full p-1.5 text-foreground-muted hover:bg-background-subtle hover:text-foreground"
          onClick={() => context.setOpen(false)}
          aria-label="Close dialog"
        >
          <X className="h-4 w-4" />
        </button>
        {children}
      </div>
    </div>
  );
}

export function DialogHeader({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={clsx("mb-4 space-y-1.5", className)}>{children}</div>;
}

export function DialogTitle({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <h2 className={clsx("text-lg font-semibold text-foreground", className)}>{children}</h2>
  );
}

export function DialogDescription({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <p className={clsx("text-sm text-foreground-muted", className)}>{children}</p>;
}
