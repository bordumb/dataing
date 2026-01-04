import type { InvestigationStatus } from "@/types/investigation";

export const statusClasses: Record<InvestigationStatus, string> = {
  active: "bg-primary text-primary-foreground",
  awaiting_approval: "bg-warning text-foreground-inverse",
  resolved: "bg-success text-foreground-inverse",
  escalated: "bg-error text-foreground-inverse",
  monitoring: "bg-primary/20 text-primary",
};

export const healthClasses: Record<string, string> = {
  healthy: "bg-success text-foreground-inverse",
  warning: "bg-warning text-foreground-inverse",
  critical: "bg-error text-foreground-inverse",
};
