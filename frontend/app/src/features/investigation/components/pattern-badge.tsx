/**
 * Pattern matching badge component.
 * Shows detected patterns with confidence indicators.
 */

import { Lightbulb, AlertTriangle, CheckCircle } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import type { MatchedPattern } from "@/lib/api/investigations";

interface PatternBadgeProps {
  pattern: MatchedPattern;
  size?: "sm" | "md";
}

function getConfidenceColor(confidence: number): string {
  if (confidence >= 0.8) return "bg-green-100 text-green-800 border-green-200";
  if (confidence >= 0.5)
    return "bg-yellow-100 text-yellow-800 border-yellow-200";
  return "bg-gray-100 text-gray-800 border-gray-200";
}

function getConfidenceIcon(confidence: number) {
  if (confidence >= 0.8) return <CheckCircle className="h-3 w-3" />;
  if (confidence >= 0.5) return <AlertTriangle className="h-3 w-3" />;
  return <Lightbulb className="h-3 w-3" />;
}

export function PatternBadge({ pattern, size = "sm" }: PatternBadgeProps) {
  const confidencePercent = Math.round(pattern.confidence * 100);

  return (
    <Badge
      variant="outline"
      className={`
        gap-1.5 ${getConfidenceColor(pattern.confidence)}
        ${size === "md" ? "px-3 py-1" : "px-2 py-0.5"}
      `}
    >
      {getConfidenceIcon(pattern.confidence)}
      <span className={size === "md" ? "text-sm" : "text-xs"}>
        {pattern.pattern_name}
      </span>
      <span className="opacity-70 text-xs">{confidencePercent}%</span>
    </Badge>
  );
}

interface PatternListProps {
  patterns: MatchedPattern[];
  emptyMessage?: string;
}

export function PatternList({
  patterns,
  emptyMessage = "No patterns detected",
}: PatternListProps) {
  if (patterns.length === 0) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Lightbulb className="h-4 w-4" />
        <span>{emptyMessage}</span>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-sm font-medium">
        <Lightbulb className="h-4 w-4 text-yellow-500" />
        <span>Matched Patterns ({patterns.length})</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {patterns.map((pattern) => (
          <PatternBadge key={pattern.pattern_id} pattern={pattern} />
        ))}
      </div>
      {patterns.some((p) => p.description) && (
        <div className="mt-2 space-y-1">
          {patterns
            .filter((p) => p.description)
            .map((pattern) => (
              <p
                key={pattern.pattern_id}
                className="text-xs text-muted-foreground"
              >
                <strong>{pattern.pattern_name}:</strong> {pattern.description}
              </p>
            ))}
        </div>
      )}
    </div>
  );
}
