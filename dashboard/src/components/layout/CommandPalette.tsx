"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Command, Search } from "lucide-react";
import { Input } from "@/components/ui/Input";
import { COMMAND_PALETTE_ITEMS } from "@/lib/utils/constants";
import { useDebounce } from "@/lib/hooks/useDebounce";

export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const debounced = useDebounce(query, 150);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen(true);
      }
      if (event.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const filtered = useMemo(() => {
    const needle = debounced.toLowerCase();
    if (!needle) return COMMAND_PALETTE_ITEMS;
    return COMMAND_PALETTE_ITEMS.filter((item) => {
      const text = `${item.label} ${item.keywords.join(" ")}`.toLowerCase();
      return text.includes(needle);
    });
  }, [debounced]);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="hidden items-center gap-2 rounded-full border border-border bg-background-elevated/80 px-3 py-2 text-sm text-foreground-muted lg:flex"
      >
        <Search className="h-4 w-4" />
        Search...
        <span className="ml-2 flex items-center gap-1 rounded-full bg-background-subtle px-2 py-0.5 text-[10px] uppercase tracking-widest text-foreground-muted">
          <Command className="h-3 w-3" />K
        </span>
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-start justify-center bg-scrim/40 p-4 pt-24">
          <div className="w-full max-w-xl rounded-2xl bg-background-elevated p-5 shadow-soft">
            <div className="flex items-center gap-2">
              <Search className="h-4 w-4 text-foreground-muted" />
              <Input
                autoFocus
                placeholder="Search investigations, datasets, teams..."
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </div>
            <div className="mt-4 max-h-72 overflow-auto">
              {filtered.length === 0 ? (
                <p className="text-sm text-foreground-muted">No matches found.</p>
              ) : (
                <ul className="space-y-2">
                  {filtered.map((item) => (
                    <li key={item.href}>
                      <button
                        className="flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-sm font-medium text-foreground hover:bg-background-subtle"
                        onClick={() => {
                          router.push(item.href);
                          setOpen(false);
                          setQuery("");
                        }}
                      >
                        {item.label}
                        <span className="text-xs text-foreground-muted">{item.href}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="mt-4 text-xs text-foreground-muted">
              Tip: Use arrows to navigate. Press Esc to close.
            </div>
          </div>
        </div>
      )}
    </>
  );
}
