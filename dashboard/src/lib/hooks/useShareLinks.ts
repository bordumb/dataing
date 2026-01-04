"use client";

import { useState } from "react";
import { createShareLink as apiCreateShareLink, type ShareLink } from "@/lib/api/share";

export function useShareLinks(investigationId: string) {
  const [shareLinks, setShareLinks] = useState<ShareLink[]>([]);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCreateShareLink = async (expiresIn = "7d") => {
    setIsCreating(true);
    setError(null);

    try {
      // Parse expiration format (e.g., "1d" -> 1, "7d" -> 7)
      const days = parseInt(expiresIn.replace(/\D/g, ""), 10) || 7;

      const newLink = await apiCreateShareLink(investigationId, days);

      setShareLinks((prev) => [
        {
          ...newLink,
          id: newLink.token,  // Use token as ID
        },
        ...prev,
      ]);
    } catch (err) {
      console.error("Failed to create share link:", err);
      setError(err instanceof Error ? err.message : "Failed to create share link");
    } finally {
      setIsCreating(false);
    }
  };

  return {
    shareLinks,
    createShareLink: handleCreateShareLink,
    isCreating,
    error,
  };
}
