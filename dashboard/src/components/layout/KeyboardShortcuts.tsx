"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export function KeyboardShortcuts() {
  const router = useRouter();

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "?" && !event.metaKey && !event.ctrlKey) {
        alert("Shortcuts: g h (home), g i (investigations), g d (datasets)");
      }
      if (event.key.toLowerCase() === "g") {
        const nextKey = (nextEvent: KeyboardEvent) => {
          if (nextEvent.key.toLowerCase() === "h") router.push("/home");
          if (nextEvent.key.toLowerCase() === "i") router.push("/investigations");
          if (nextEvent.key.toLowerCase() === "d") router.push("/datasets");
          window.removeEventListener("keydown", nextKey);
        };
        window.addEventListener("keydown", nextKey, { once: true });
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [router]);

  return null;
}
