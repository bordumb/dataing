"use client";

import { useState } from "react";

export function useOnboarding() {
  const [completedSteps, setCompletedSteps] = useState<string[]>(["connect_source"]);

  const completeStep = (id: string) => {
    setCompletedSteps((prev) => (prev.includes(id) ? prev : [...prev, id]));
  };

  return { completedSteps, completeStep };
}
