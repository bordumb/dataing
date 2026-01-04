"use client";

import { useState } from "react";

interface SavedView {
  id: string;
  name: string;
}

export function useSavedViews() {
  const [views, setViews] = useState<SavedView[]>([
    { id: "view-001", name: "Active incidents" },
    { id: "view-002", name: "Awaiting approval" },
  ]);

  const saveView = (name: string) => {
    setViews((prev) => [{ id: `view-${prev.length + 1}`, name }, ...prev]);
  };

  const deleteView = (id: string) => {
    setViews((prev) => prev.filter((view) => view.id !== id));
  };

  return { views, saveView, deleteView };
}
