"use client";

import { createContext, useContext, useState } from "react";
import clsx from "clsx";

interface TabsContextValue {
  value: string;
  setValue: (value: string) => void;
}

const TabsContext = createContext<TabsContextValue | null>(null);

export function Tabs({
  defaultValue,
  children,
}: {
  defaultValue: string;
  children: React.ReactNode;
}) {
  const [value, setValue] = useState(defaultValue);
  return <TabsContext.Provider value={{ value, setValue }}>{children}</TabsContext.Provider>;
}

export function TabsList({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap gap-2 rounded-full border border-border bg-background-elevated/60 p-1">
      {children}
    </div>
  );
}

export function TabsTrigger({ value, children }: { value: string; children: React.ReactNode }) {
  const context = useContext(TabsContext);
  if (!context) return null;
  const active = context.value === value;
  return (
    <button
      onClick={() => context.setValue(value)}
      className={clsx(
        "rounded-full px-4 py-1.5 text-sm font-semibold transition",
        active ? "bg-primary text-primary-foreground" : "text-foreground-muted hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

export function TabsContent({ value, children }: { value: string; children: React.ReactNode }) {
  const context = useContext(TabsContext);
  if (!context || context.value !== value) return null;
  return <div className="mt-6">{children}</div>;
}
