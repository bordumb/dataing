/**
 * Reading an investigation's evidence items: the API has spelled their
 * fields several ways, so every reader goes through evidenceFields.
 */

import { CheckCircle2, HelpCircle, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/Badge";

// Evidence can come in various formats from the API
type EvidenceItem = Record<string, unknown>;

// Safe accessor functions for evidence properties
function getStringField(ev: EvidenceItem, ...keys: string[]): string {
  for (const key of keys) {
    const value = ev[key];
    if (typeof value === "string") return value;
  }
  return "";
}

function getNumberField(ev: EvidenceItem, ...keys: string[]): number {
  for (const key of keys) {
    const value = ev[key];
    if (typeof value === "number") return value;
  }
  return 0;
}

function getBoolOrNull(ev: EvidenceItem, ...keys: string[]): boolean | null {
  for (const key of keys) {
    const value = ev[key];
    if (typeof value === "boolean") return value;
  }
  return null;
}

/** An evidence item's fields, whichever spelling the API used. */
export interface EvidenceFields {
  hypothesisId: string;
  query: string;
  resultSummary: string;
  rowCount: number;
  supports: boolean | null;
  confidence: number;
  interpretation: string;
}

export function evidenceFields(
  evidence: EvidenceItem,
  index: number,
): EvidenceFields {
  return {
    hypothesisId:
      getStringField(evidence, "hypothesis_id", "hypothesisId", "id") ||
      `#${index + 1}`,
    query: getStringField(evidence, "query", "sql", "sql_query"),
    resultSummary: getStringField(
      evidence,
      "result_summary",
      "resultSummary",
      "summary",
      "result",
    ),
    rowCount: getNumberField(evidence, "row_count", "rowCount", "rows"),
    supports: getBoolOrNull(
      evidence,
      "supports_hypothesis",
      "supportsHypothesis",
      "supports",
    ),
    confidence: getNumberField(evidence, "confidence", "score"),
    interpretation: getStringField(
      evidence,
      "interpretation",
      "analysis",
      "explanation",
      "description",
    ),
  };
}

/** Whether a query's result supports its hypothesis. */
export function SupportBadge({ supports }: { supports: boolean | null }) {
  if (supports === true) {
    return (
      <Badge variant="success" className="gap-1">
        <CheckCircle2 className="h-3 w-3" />
        Supports
      </Badge>
    );
  }
  if (supports === false) {
    return (
      <Badge variant="destructive" className="gap-1">
        <XCircle className="h-3 w-3" />
        Refutes
      </Badge>
    );
  }
  return (
    <Badge variant="secondary" className="gap-1">
      <HelpCircle className="h-3 w-3" />
      Inconclusive
    </Badge>
  );
}
