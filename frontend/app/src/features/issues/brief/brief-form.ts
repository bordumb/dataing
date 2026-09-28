/**
 * The brief editor's form state and its conversion to and from a brief.
 */

import type {
  BriefClaim,
  ExecutionProfile,
  InvestigationBrief,
} from "@/lib/api/investigation-runs";

export interface ClaimDraft {
  key: string;
  statement: string;
  include: boolean;
  message_id: string | null;
  query_result_id: string | null;
}

export interface BriefForm {
  symptom: string;
  findings: ClaimDraft[];
  ruledOut: ClaimDraft[];
  leads: string[];
  /** Comma- or newline-separated table names. */
  tables: string;
  /** datetime-local values, read as UTC. Empty when unset. */
  from: string;
  to: string;
  notes: string;
  profile: ExecutionProfile;
  /** "" leaves the datasource to the server (hand-off mode only). */
  datasourceId: string;
}

/** What a brief needs beyond a symptom before it can start a run. */
export interface BriefRules {
  /** Name at least one table: a new run has no thread to draft scope from. */
  requireTables?: boolean;
  /** Pick a datasource: the tenant has more than one. */
  requireDatasource?: boolean;
}

let claimCounter = 0;

export function newClaim(partial: Partial<BriefClaim> = {}): ClaimDraft {
  claimCounter += 1;
  return {
    key: `claim-${claimCounter}`,
    statement: partial.statement ?? "",
    include: true,
    message_id: partial.message_id ?? null,
    query_result_id: partial.query_result_id ?? null,
  };
}

/** "2026-09-10T00:00:00Z" → "2026-09-10T00:00" (UTC), for datetime-local. */
function toLocalInput(iso: string | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toISOString().slice(0, 16);
}

/** "2026-09-10T00:00" (UTC) → "2026-09-10T00:00:00Z". */
function fromLocalInput(value: string): string {
  return new Date(`${value}:00Z`).toISOString().replace(".000Z", "Z");
}

export function formFromBrief(
  brief: InvestigationBrief,
  profile: ExecutionProfile = "standard",
): BriefForm {
  return {
    symptom: brief.symptom ?? "",
    findings: (brief.findings ?? []).map((c) => newClaim(c)),
    ruledOut: (brief.ruled_out ?? []).map((c) => newClaim(c)),
    leads: [...(brief.leads ?? [])],
    tables: (brief.scope?.tables ?? []).join(", "),
    from: toLocalInput(brief.scope?.time_window?.from),
    to: toLocalInput(brief.scope?.time_window?.to),
    notes: brief.notes ?? "",
    profile,
    datasourceId: brief.scope?.datasource_id ?? "",
  };
}

export function parseTables(text: string): string[] {
  return text
    .split(/[,\n]/)
    .map((t) => t.trim())
    .filter(Boolean);
}

/** Why the form can't be sent yet, or null when it can. */
export function formProblem(
  form: BriefForm,
  rules: BriefRules = {},
): string | null {
  if (!form.symptom.trim()) return "Say what's wrong: the symptom is required.";
  if (rules.requireTables && parseTables(form.tables).length === 0)
    return "Name at least one table to investigate.";
  if (rules.requireDatasource && !form.datasourceId)
    return "Pick the datasource to investigate.";
  if (!!form.from !== !!form.to)
    return "Set both ends of the time window, or neither.";
  if (form.from && form.to && form.from >= form.to)
    return "The time window must end after it starts.";
  return null;
}

function claims(drafts: ClaimDraft[]): BriefClaim[] {
  return drafts
    .filter((c) => c.include && c.statement.trim())
    .map((c) => ({
      statement: c.statement.trim(),
      message_id: c.message_id,
      query_result_id: c.query_result_id,
    }));
}

/** The brief the form describes: unchecked claims and blank lines dropped. */
export function briefFromForm(form: BriefForm): InvestigationBrief {
  return {
    version: 1,
    symptom: form.symptom.trim(),
    scope: {
      datasource_id: form.datasourceId || null,
      tables: parseTables(form.tables),
      time_window:
        form.from && form.to
          ? { from: fromLocalInput(form.from), to: fromLocalInput(form.to) }
          : null,
    },
    findings: claims(form.findings),
    ruled_out: claims(form.ruledOut),
    leads: form.leads.map((l) => l.trim()).filter(Boolean),
    notes: form.notes.trim(),
  };
}

const MAX_STATEMENT = 500;

function clip(text: string): string {
  return text.length > MAX_STATEMENT
    ? `${text.slice(0, MAX_STATEMENT - 1)}…`
    : text;
}

/**
 * The brief for "Continue investigating": the prior run's brief plus what it
 * concluded, and an empty lead for the person's new instruction. A rejected
 * conclusion becomes an exclusion, with the reason it was rejected.
 */
export function continuationBrief(
  prior: InvestigationBrief,
  conclusion: string | null | undefined,
  rejection?: { note: string | null | undefined } | null,
): InvestigationBrief {
  const findings = [...(prior.findings ?? [])];
  const ruledOut = [...(prior.ruled_out ?? [])];
  if (conclusion) {
    if (rejection) {
      const why = rejection.note?.trim();
      ruledOut.push({
        statement: clip(
          `The previous run concluded "${conclusion}", which was rejected${why ? `: ${why}` : ""}`,
        ),
      });
    } else {
      findings.push({
        statement: clip(`The previous run concluded: ${conclusion}`),
      });
    }
  }
  return {
    ...prior,
    findings,
    ruled_out: ruledOut,
    leads: [...(prior.leads ?? []), ""],
  };
}
