"use client";

import Link from "next/link";
import { Card } from "@/components/ui/Card";
import { useOnboarding } from "@/lib/hooks/useOnboarding";

const steps = [
  { id: "connect_source", label: "Connect anomaly source", href: "/integrations/anomaly-sources" },
  { id: "add_dataset", label: "Add your first dataset", href: "/datasets" },
  { id: "run_investigation", label: "Run your first investigation", href: "/investigations/new" },
  { id: "invite_team", label: "Invite team members", href: "/teams" },
];

export function OnboardingChecklist() {
  const { completedSteps, completeStep } = useOnboarding();

  return (
    <Card title="Getting Started" description="Complete these steps to finish setup.">
      <div className="space-y-3">
        {steps.map((step) => {
          const done = completedSteps.includes(step.id);
          return (
            <div key={step.id} className="flex items-center justify-between rounded-lg border border-border bg-background-elevated/70 p-3">
              <div>
                <p className={`text-sm font-semibold ${done ? "text-foreground-muted" : "text-foreground"}`}>{step.label}</p>
                <Link href={step.href} className="text-xs text-foreground-muted">
                  {step.href}
                </Link>
              </div>
              <button
                className={`rounded-full px-3 py-1 text-xs font-semibold ${done ? "bg-background-muted text-foreground/70" : "bg-primary text-primary-foreground"}`}
                onClick={() => completeStep(step.id)}
              >
                {done ? "Done" : "Mark done"}
              </button>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
