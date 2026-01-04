"use client";

import clsx from "clsx";
import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "@/lib/theme";

export function ThemeSwitcher() {
  const { theme, setTheme } = useTheme();

  return (
    <div className="flex items-center gap-1 rounded-full border border-border bg-background-subtle p-1 text-foreground">
      <button
        onClick={() => setTheme("light")}
        className={clsx(
          "rounded-full p-2 transition-colors",
          theme === "light"
            ? "bg-background-elevated text-foreground shadow-sm"
            : "text-foreground-muted hover:text-foreground",
        )}
        aria-label="Light mode"
      >
        <Sun className="h-4 w-4" />
      </button>
      <button
        onClick={() => setTheme("dark")}
        className={clsx(
          "rounded-full p-2 transition-colors",
          theme === "dark"
            ? "bg-background-elevated text-foreground shadow-sm"
            : "text-foreground-muted hover:text-foreground",
        )}
        aria-label="Dark mode"
      >
        <Moon className="h-4 w-4" />
      </button>
      <button
        onClick={() => setTheme("system")}
        className={clsx(
          "rounded-full p-2 transition-colors",
          theme === "system"
            ? "bg-background-elevated text-foreground shadow-sm"
            : "text-foreground-muted hover:text-foreground",
        )}
        aria-label="System theme"
      >
        <Monitor className="h-4 w-4" />
      </button>
    </div>
  );
}
