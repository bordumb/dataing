/**
 * A steer the agent proposed with propose_steer. The agent can't change a run
 * itself (spec 0001 D5): a person sends, edits or dismisses the proposal.
 */

import { useState } from "react";
import { Loader2, Pencil, Send, X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/textarea";
import { errorText } from "@/lib/api/error-message";
import {
  STEER_KIND_LABEL,
  useCreateSteer,
  type Steer,
  type SteerKind,
} from "@/lib/api/investigation-runs";
import type { SteerProposal } from "@/lib/api/issue-threads";

import { Pill } from "./Pill";

/** A person's steer message that sent a proposal from this reply. */
export interface SentProposal {
  kind: string;
  hypothesis_id: string | null;
  author_user_id: string | null;
}

const STEER_KINDS = new Set<string>([
  "add_context",
  "rule_out",
  "add_hypothesis",
  "stop_and_synthesize",
]);

interface ProposalCardProps {
  proposal: SteerProposal;
  /** The proposal's run, numbered among the issue's runs, when known. */
  runNumber?: number;
  /** The agent reply carrying the proposal: sending it twice is a no-op. */
  replyId: string;
  canWrite: boolean;
  /** Set when someone already sent this proposal. */
  sent?: SentProposal | null;
  nameOf: (userId: string | null | undefined) => string;
}

export function ProposalCard({
  proposal,
  runNumber,
  replyId,
  canWrite,
  sent,
  nameOf,
}: ProposalCardProps) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(proposal.text);
  const [dismissed, setDismissed] = useState(false);
  const [result, setResult] = useState<Steer | null>(null);
  const create = useCreateSteer();
  const kindLabel = STEER_KIND_LABEL[proposal.kind] ?? proposal.kind;
  const runId = proposal.run_id;
  const validKind = STEER_KINDS.has(proposal.kind);
  const needsText =
    proposal.kind === "add_context" || proposal.kind === "add_hypothesis";
  const canSend =
    !!runId && validKind && !create.isPending && (!needsText || !!text.trim());

  const send = async () => {
    if (!canSend || !runId) return;
    try {
      const steer = await create.mutateAsync({
        investigationId: runId,
        body: {
          kind: proposal.kind as SteerKind,
          text: text.trim(),
          hypothesis_id: proposal.hypothesis_id,
          proposal_message_id: replyId,
        },
      });
      setResult(steer);
      setEditing(false);
      if (steer.status === "rejected") {
        toast.error("The investigation didn't take the steer", {
          description: steer.outcome ?? undefined,
        });
      }
    } catch (error) {
      toast.error("Couldn't send the steer", {
        description: errorText(error),
      });
    }
  };

  if (dismissed) {
    return (
      <p className="mt-2 text-xs italic text-muted-foreground">
        Proposed steer dismissed.{" "}
        <button
          type="button"
          className="not-italic text-primary hover:underline"
          onClick={() => setDismissed(false)}
        >
          Show
        </button>
      </p>
    );
  }

  const done = result ?? null;
  const alreadySent = !done && sent;

  return (
    <div
      className="mt-2 rounded-lg border border-dashed border-violet-400 px-3 py-2 text-sm"
      aria-label="Proposed steer"
    >
      <p>
        <span className="font-semibold">Proposed steer</span> ·{" "}
        {kindLabel.toLowerCase()}
        {proposal.hypothesis_id ? ` ${proposal.hypothesis_id}` : ""}
        {runNumber
          ? ` · #${runNumber}`
          : runId
            ? ` · investigation ${runId.slice(0, 8)}`
            : ""}
      </p>
      {editing ? (
        <Textarea
          aria-label="Steer text"
          className="mt-1.5"
          value={text}
          rows={2}
          maxLength={2000}
          onChange={(e) => setText(e.target.value)}
        />
      ) : (
        text && <p className="mt-1">&ldquo;{text}&rdquo;</p>
      )}

      {done ? (
        <p className="mt-1.5 text-xs text-muted-foreground">
          Sent ·{" "}
          <Pill
            tone={
              done.status === "applied"
                ? "ok"
                : done.status === "rejected"
                  ? "bad"
                  : "warn"
            }
          >
            {done.status === "rejected" ? "not applied" : done.status}
          </Pill>
          {done.outcome ? ` ${done.outcome}` : ""}
        </p>
      ) : alreadySent ? (
        <p className="mt-1.5 text-xs text-muted-foreground">
          Sent by {nameOf(alreadySent.author_user_id)}. Its outcome is on the
          investigation card.
        </p>
      ) : !runId ? (
        <p className="mt-1.5 text-xs text-muted-foreground">
          The agent didn't name an investigation, so this can't be sent.
        </p>
      ) : canWrite ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          <Button
            size="sm"
            className="h-7 gap-1 bg-violet-600 text-xs text-white hover:bg-violet-700"
            disabled={!canSend}
            onClick={() => void send()}
          >
            {create.isPending ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Send className="h-3 w-3" />
            )}
            Send steer
          </Button>
          {!editing && (
            <Button
              size="sm"
              variant="outline"
              className="h-7 gap-1 text-xs"
              onClick={() => setEditing(true)}
            >
              <Pencil className="h-3 w-3" />
              Edit
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            className="h-7 gap-1 text-xs"
            onClick={() => {
              setEditing(false);
              setText(proposal.text);
              setDismissed(true);
            }}
          >
            <X className="h-3 w-3" />
            Dismiss
          </Button>
        </div>
      ) : (
        <p className="mt-1.5 text-xs text-muted-foreground">
          A member can send this steer.
        </p>
      )}
    </div>
  );
}
