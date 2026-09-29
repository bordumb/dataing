/**
 * The brief editor's form state and its conversion to and from a brief.
 */

import {
  createEmptyDatePickerValue,
  type DatePickerValue,
} from "@/components/ui/DatePicker";
import type {
  BriefClaim,
  BriefTimeWindow,
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

/** A table in scope, as picked with DatasetEntry's autocomplete. */
export interface TableDraft {
  key: string;
  identifier: string;
}

export interface BriefForm {
  symptom: string;
  findings: ClaimDraft[];
  ruledOut: ClaimDraft[];
  leads: string[];
  /** One row per table; every table is in the datasource below. */
  tables: TableDraft[];
  /** The days to look at, as the date picker holds them; empty when unset. */
  window: DatePickerValue;
  notes: string;
  profile: ExecutionProfile;
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

let tableCounter = 0;

export function newTable(identifier = ""): TableDraft {
  tableCounter += 1;
  return { key: `table-${tableCounter}`, identifier };
}

/** An ISO timestamp's UTC calendar day, as the date picker's local Date. */
function dayOf(iso: string): Date | null {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return new Date(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
}

function addDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

/** A picked day as "YYYY-MM-DDT00:00:00Z": the brief's windows are whole UTC days. */
function utcMidnight(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}T00:00:00Z`;
}

function isMidnight(iso: string): boolean {
  const date = new Date(iso);
  return (
    date.getUTCHours() === 0 &&
    date.getUTCMinutes() === 0 &&
    date.getUTCSeconds() === 0
  );
}

/** A brief's window [from, to) as the inclusive days the date picker shows. */
function windowFromBrief(
  window: BriefTimeWindow | null | undefined,
): DatePickerValue {
  const start = window?.from ? dayOf(window.from) : null;
  const last = window?.to ? dayOf(window.to) : null;
  if (!window || !start || !last) return createEmptyDatePickerValue();
  // A window that ends at midnight doesn't include that day
  const end = isMidnight(window.to) && last > start ? addDays(last, -1) : last;
  return { mode: end > start ? "range" : "single", start, end };
}

/** The date picker's days as the brief's window [first day, day after the last). */
function windowFromForm(window: DatePickerValue): BriefTimeWindow | null {
  if (!window.start) return null;
  const end =
    window.end && window.end > window.start ? window.end : window.start;
  return { from: utcMidnight(window.start), to: utcMidnight(addDays(end, 1)) };
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
    tables: brief.scope?.tables?.length
      ? brief.scope.tables.map((table) => newTable(table))
      : [newTable()],
    window: windowFromBrief(brief.scope?.time_window),
    notes: brief.notes ?? "",
    profile,
    datasourceId: brief.scope?.datasource_id ?? "",
  };
}

function tableNames(tables: TableDraft[]): string[] {
  return tables.map((t) => t.identifier.trim()).filter(Boolean);
}

/** Why the form can't be sent yet, or null when it can. */
export function formProblem(
  form: BriefForm,
  rules: BriefRules = {},
): string | null {
  if (!form.symptom.trim()) return "Say what's wrong: the symptom is required.";
  if (rules.requireTables && tableNames(form.tables).length === 0)
    return "Pick at least one table to investigate.";
  if (rules.requireDatasource && !form.datasourceId)
    return "Pick the datasource to investigate.";
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
      tables: tableNames(form.tables),
      time_window: windowFromForm(form.window),
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
