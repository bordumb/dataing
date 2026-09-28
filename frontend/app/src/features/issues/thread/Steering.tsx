/**
 * Steering a running investigation (spec 0001 §7.8): rule out a hypothesis,
 * add context or a hypothesis, or stop and conclude, plus the list of steers
 * sent and how each ended.
 */

import { useState } from "react";
import { Loader2, Send } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/textarea";
import { errorText } from "@/lib/api/error-message";
import {
  STEER_KIND_LABEL,
  useCreateSteer,
  type HypothesisState,
  type Steer,
  type SteerCreate,
  type SteerKind,
} from "@/lib/api/investigation-runs";

import { Pill, hypothesisStatus, type PillTone } from "./Pill";

export interface HypothesisRowProps {
  hypothesis: HypothesisState;
  index: number;
  /** The pill's words, when they say more than the status, e.g. by whom. */
  label?: string;
  /** Muted words at the end of the row, e.g. "stopped". */
  note?: string;
  action?: React.ReactNode;
}

export function HypothesisRow({
  hypothesis,
  index,
  label,
  note,
  action,
}: HypothesisRowProps) {
  const status = hypothesisStatus(hypothesis.status);
  return (
    <li
      className="flex items-center gap-2 border-t border-border py-1.5 text-sm"
      aria-label={`Hypothesis ${hypothesis.title}`}
    >
      <Pill tone={status.tone}>{label ?? status.label}</Pill>
      <span
        className={
          hypothesis.status === "ruled_out"
            ? "flex-1 text-muted-foreground line-through"
            : "flex-1"
        }
      >
        H{index + 1} · {hypothesis.title || hypothesis.id}
      </span>
      {note && <span className="text-xs text-muted-foreground">{note}</span>}
      {action}
    </li>
  );
}

const STEER_STATUS: Record<string, { tone: PillTone; label: string }> = {
  pending: { tone: "warn", label: "pending" },
  applied: { tone: "ok", label: "applied" },
  rejected: { tone: "bad", label: "not applied" },
};

/** Hypotheses a person can still rule out. */
const OPEN_STATUSES = new Set(["pending", "running"]);

type Draft =
  | { kind: "rule_out"; hypothesis: HypothesisState; index: number }
  | { kind: "add_context" | "add_hypothesis" | "stop_and_synthesize" };

const DRAFT_COPY: Record<
  SteerKind,
  { title: string; placeholder: string; requireText: boolean; send: string }
> = {
  add_context: {
    title: "Add context",
    placeholder:
      "A fact or constraint, e.g. app_v2 shipped 2026-09-14 09:00 UTC",
    requireText: true,
    send: "Send context",
  },
  add_hypothesis: {
    title: "Add hypothesis",
    placeholder: "What else should be tested",
    requireText: true,
    send: "Send hypothesis",
  },
  rule_out: {
    title: "Rule out",
    placeholder: "Why (optional), e.g. events arrive within 5 minutes",
    requireText: false,
    send: "Rule out",
  },
  stop_and_synthesize: {
    title: "Stop and conclude",
    placeholder: "Why (optional)",
    requireText: false,
    send: "Stop and conclude",
  },
};

function steerTarget(
  steer: Pick<Steer, "hypothesis_id">,
  hypotheses: HypothesisState[],
): string {
  if (!steer.hypothesis_id) return "";
  const index = hypotheses.findIndex((h) => h.id === steer.hypothesis_id);
  return index >= 0 ? ` H${index + 1}` : ` ${steer.hypothesis_id}`;
}

function SteerForm({
  draft,
  pending,
  onSend,
  onCancel,
}: {
  draft: Draft;
  pending: boolean;
  onSend: (text: string) => void;
  onCancel: () => void;
}) {
  const [text, setText] = useState("");
  const copy = DRAFT_COPY[draft.kind];
  const title =
    draft.kind === "rule_out"
      ? `Rule out H${draft.index + 1} · ${draft.hypothesis.title || draft.hypothesis.id}`
      : copy.title;
  const canSend = !pending && (!copy.requireText || !!text.trim());
  const multiline =
    draft.kind === "add_context" || draft.kind === "add_hypothesis";

  return (
    <form
      className="mt-2 space-y-2 rounded-md border border-violet-300 bg-violet-50/50 p-2.5 dark:border-violet-900 dark:bg-violet-950/30"
      aria-label={title}
      onSubmit={(e) => {
        e.preventDefault();
        if (canSend) onSend(text.trim());
      }}
    >
      <p className="text-xs font-semibold">{title}</p>
      {draft.kind === "stop_and_synthesize" && (
        <p className="text-xs text-muted-foreground">
          The remaining subagents stop; their hypotheses stay untested and the
          manager concludes from what it has.
        </p>
      )}
      {multiline ? (
        <Textarea
          aria-label={draft.kind === "add_context" ? "Context" : "Hypothesis"}
          value={text}
          rows={2}
          maxLength={2000}
          placeholder={copy.placeholder}
          onChange={(e) => setText(e.target.value)}
        />
      ) : (
        <Input
          aria-label="Reason"
          value={text}
          maxLength={2000}
          placeholder={copy.placeholder}
          onChange={(e) => setText(e.target.value)}
        />
      )}
      <div className="flex gap-2">
        <Button
          type="submit"
          size="sm"
          className="h-7 gap-1 bg-violet-600 text-xs text-white hover:bg-violet-700"
          disabled={!canSend}
        >
          {pending ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <Send className="h-3 w-3" />
          )}
          {copy.send}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-7 text-xs"
          onClick={onCancel}
        >
          Cancel
        </Button>
      </div>
    </form>
  );
}

export function SteerList({
  steers,
  hypotheses,
  nameOf,
}: {
  steers: Steer[];
  hypotheses: HypothesisState[];
  nameOf: (userId: string | null | undefined) => string;
}) {
  if (steers.length === 0) return null;
  return (
    <ul className="mt-2 space-y-1.5" aria-label="Steers">
      {steers.map((steer) => {
        const status = STEER_STATUS[steer.status] ?? {
          tone: "neutral" as const,
          label: steer.status,
        };
        return (
          <li
            key={steer.id}
            className="rounded border-l-[3px] border-violet-500 bg-violet-50 px-2 py-1 text-xs dark:bg-violet-950/40"
          >
            Steer by {nameOf(steer.actor_user_id)} ·{" "}
            {(STEER_KIND_LABEL[steer.kind] ?? steer.kind).toLowerCase()}
            {steerTarget(steer, hypotheses)}
            {steer.text ? `: "${steer.text}"` : ""} ·{" "}
            <Pill tone={status.tone}>{status.label}</Pill>
            {steer.outcome ? ` ${steer.outcome}` : ""}
          </li>
        );
      })}
    </ul>
  );
}

interface SteeringProps {
  investigationId: string;
  running: boolean;
  hypotheses: HypothesisState[];
  steers: Steer[];
  canWrite: boolean;
  nameOf: (userId: string | null | undefined) => string;
}

/** Hypothesis rows with Rule out, the steer controls and the steer list. */
export function Steering({
  investigationId,
  running,
  hypotheses,
  steers,
  canWrite,
  nameOf,
}: SteeringProps) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const create = useCreateSteer();
  const canSteer = running && canWrite;

  const ruledOutBy = new Map<string, string | null>();
  for (const steer of steers) {
    if (
      steer.kind === "rule_out" &&
      steer.hypothesis_id &&
      steer.status === "applied"
    ) {
      ruledOutBy.set(steer.hypothesis_id, steer.actor_user_id);
    }
  }
  const pendingRuleOuts = new Set(
    steers
      .filter((s) => s.kind === "rule_out" && s.status === "pending")
      .map((s) => s.hypothesis_id),
  );

  const send = async (text: string) => {
    if (!draft) return;
    const body: SteerCreate =
      draft.kind === "rule_out"
        ? { kind: "rule_out", text, hypothesis_id: draft.hypothesis.id }
        : { kind: draft.kind, text };
    try {
      const steer = await create.mutateAsync({ investigationId, body });
      setDraft(null);
      if (steer.status === "rejected") {
        toast.error("The investigation didn't take the steer", {
          description: steer.outcome ?? undefined,
        });
      } else {
        toast.success("Steer sent", {
          description: "The run applies it at its next checkpoint.",
        });
      }
    } catch (error) {
      toast.error("Couldn't send the steer", {
        description: errorText(error),
      });
    }
  };

  return (
    <div>
      {hypotheses.length > 0 && (
        <ul className="mt-2">
          {hypotheses.map((h, i) => {
            // "ruled out by Maya · stopped", as the mockup writes it.
            const ruledOutByName =
              h.status === "ruled_out" && ruledOutBy.has(h.id)
                ? nameOf(ruledOutBy.get(h.id))
                : null;
            const note = ruledOutByName
              ? "stopped"
              : pendingRuleOuts.has(h.id)
                ? "rule-out pending"
                : undefined;
            const canRuleOut =
              canSteer &&
              OPEN_STATUSES.has(h.status) &&
              !pendingRuleOuts.has(h.id);
            return (
              <HypothesisRow
                key={h.id}
                hypothesis={h}
                index={i}
                label={
                  ruledOutByName ? `ruled out by ${ruledOutByName}` : undefined
                }
                note={note}
                action={
                  canRuleOut ? (
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-6 px-2 text-xs"
                      aria-label={`Rule out H${i + 1}`}
                      onClick={() =>
                        setDraft({ kind: "rule_out", hypothesis: h, index: i })
                      }
                    >
                      Rule out
                    </Button>
                  ) : null
                }
              />
            );
          })}
        </ul>
      )}

      <SteerList steers={steers} hypotheses={hypotheses} nameOf={nameOf} />

      {canSteer &&
        (draft ? (
          <SteerForm
            key={draft.kind === "rule_out" ? draft.hypothesis.id : draft.kind}
            draft={draft}
            pending={create.isPending}
            onSend={(text) => void send(text)}
            onCancel={() => setDraft(null)}
          />
        ) : (
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Button
              variant="outline"
              size="sm"
              className="h-7 gap-1 text-xs"
              onClick={() => setDraft({ kind: "add_context" })}
            >
              <span aria-hidden>＋</span>
              Add context
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-7 gap-1 text-xs"
              onClick={() => setDraft({ kind: "add_hypothesis" })}
            >
              <span aria-hidden>＋</span>
              Add hypothesis
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-7 gap-1 text-xs"
              disabled={hypotheses.length === 0}
              title={
                hypotheses.length === 0
                  ? "Available once the manager has hypotheses"
                  : undefined
              }
              onClick={() => setDraft({ kind: "stop_and_synthesize" })}
            >
              Stop and conclude
            </Button>
          </div>
        ))}
    </div>
  );
}
