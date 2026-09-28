/**
 * Investigate…: start a run from any page, one step from intent (spec 0001
 * D13, §8.2). The brief editor opens in new mode where the person is,
 * pre-filled with what the page knows. Start opens an issue for the run and
 * lands on its thread, where the run's card is already live.
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search } from "lucide-react";
import { toast } from "sonner";

import { Button, type ButtonProps } from "@/components/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ApiError } from "@/lib/api/client";
import { errorText } from "@/lib/api/error-message";
import type { InvestigationBrief } from "@/lib/api/investigation-runs";
import { useStartInvestigation } from "@/lib/api/investigations";
import { useRole } from "@/lib/auth/use-role";
import { cn } from "@/lib/utils";

import { BriefFormView } from "./BriefEditor";
import { briefFromForm, formFromBrief, type BriefForm } from "./brief-form";

/** What the page already knows about the problem. */
export interface InvestigationPrefill {
  symptom?: string;
  tables?: string[];
  datasourceId?: string | null;
}

const AMBIGUOUS_DATASOURCE_PROMPT =
  "More than one datasource could hold these tables. Pick the one to investigate.";

function prefillBrief(prefill: InvestigationPrefill = {}): InvestigationBrief {
  return {
    symptom: prefill.symptom ?? "",
    scope: {
      datasource_id: prefill.datasourceId ?? null,
      tables: prefill.tables ?? [],
      time_window: null,
    },
    // A new run has no thread to draft findings, exclusions or leads from.
    findings: [],
    ruled_out: [],
    leads: [],
    notes: "",
  };
}

function NewInvestigationForm({
  prefill,
  onDone,
}: {
  prefill?: InvestigationPrefill;
  onDone: () => void;
}) {
  const navigate = useNavigate();
  const start = useStartInvestigation();
  const [initial] = useState(() => formFromBrief(prefillBrief(prefill)));
  const [datasourcePrompt, setDatasourcePrompt] = useState<string | null>(null);

  const submit = async (form: BriefForm) => {
    setDatasourcePrompt(null);
    try {
      const started = await start.mutateAsync({
        brief: briefFromForm(form),
        execution_profile: form.profile,
        datasource_id: form.datasourceId || null,
      });
      toast.success(`Investigation started in issue #${started.issue_number}`, {
        description:
          "Its card in the issue's thread shows progress and steering.",
      });
      onDone();
      navigate(`/issues/${started.issue_id}`);
    } catch (error) {
      if (error instanceof ApiError && error.code === "ambiguous_datasource") {
        setDatasourcePrompt(AMBIGUOUS_DATASOURCE_PROMPT);
      }
      toast.error("Couldn't start the investigation", {
        description: errorText(error),
      });
    }
  };

  return (
    <BriefFormView
      mode="new"
      initial={initial}
      pending={start.isPending}
      datasourcePrompt={datasourcePrompt}
      onSubmit={(form) => void submit(form)}
      onCancel={onDone}
    />
  );
}

export interface StartInvestigationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  prefill?: InvestigationPrefill;
}

/** The brief editor in new mode, titled "Start an investigation". */
export function StartInvestigationDialog({
  open,
  onOpenChange,
  prefill,
}: StartInvestigationDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Start an investigation</DialogTitle>
          <DialogDescription>
            Say what's wrong and where to look. Starting opens an issue for the
            run; its thread shows the progress and lets the team steer it.
          </DialogDescription>
        </DialogHeader>
        {open && (
          <NewInvestigationForm
            prefill={prefill}
            onDone={() => onOpenChange(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

export interface InvestigateButtonProps extends Omit<
  ButtonProps,
  "onClick" | "children" | "asChild"
> {
  label?: string;
  prefill?: InvestigationPrefill;
}

/**
 * The start button every page uses. Members only: starting a run needs the
 * write scope, so viewers don't see it.
 */
export function InvestigateButton({
  label = "Investigate…",
  prefill,
  className,
  ...buttonProps
}: InvestigateButtonProps) {
  const { isMember } = useRole();
  const [open, setOpen] = useState(false);
  if (!isMember) return null;

  return (
    <>
      <Button
        type="button"
        className={cn("gap-2", className)}
        {...buttonProps}
        onClick={() => setOpen(true)}
      >
        <Search className="h-4 w-4" />
        {label}
      </Button>
      <StartInvestigationDialog
        open={open}
        onOpenChange={setOpen}
        prefill={prefill}
      />
    </>
  );
}
