/**
 * CodifyWidget - "Add as check": turn a confirmed finding into a regression
 * test (checks as code §7.6).
 */

import { useState } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import {
  FlaskConical,
  Copy,
  Download,
  Check,
  Loader2,
  X,
  AlertCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import {
  codifyBlocker,
  useCodifyInvestigation,
} from "@/lib/api/investigations";

type OutputFormat = "gx" | "dbt" | "soda" | "sql";

interface FormatOption {
  value: OutputFormat;
  label: string;
  extension: string;
  language: string;
}

const FORMAT_OPTIONS: FormatOption[] = [
  { value: "sql", label: "SQL", extension: ".sql", language: "sql" },
  { value: "dbt", label: "dbt", extension: ".yml", language: "yaml" },
  {
    value: "gx",
    label: "Great Expectations",
    extension: ".json",
    language: "json",
  },
  { value: "soda", label: "Soda", extension: ".yml", language: "yaml" },
];

interface CodifyWidgetProps {
  investigationId: string;
  confidence: number;
  isComplete: boolean;
  /** The run's review: a confirmed cause can become a check at any confidence. */
  verdict?: string | null;
}

interface CodifyModalProps {
  isOpen: boolean;
  onClose: () => void;
  investigationId: string;
}

export function CodifyModal({
  isOpen,
  onClose,
  investigationId,
}: CodifyModalProps) {
  const [selectedFormat, setSelectedFormat] = useState<OutputFormat>("sql");
  const [copied, setCopied] = useState(false);

  const codifyMutation = useCodifyInvestigation();

  if (!isOpen) return null;

  const handleFormatChange = (format: OutputFormat) => {
    setSelectedFormat(format);
    setCopied(false);
    codifyMutation.mutate({ investigationId, format });
  };

  const handleCopy = async () => {
    if (codifyMutation.data?.content) {
      await navigator.clipboard.writeText(codifyMutation.data.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleDownload = () => {
    if (!codifyMutation.data?.content) return;

    const formatOption = FORMAT_OPTIONS.find((f) => f.value === selectedFormat);
    const filename = `investigation_${investigationId.slice(0, 8)}_tests${formatOption?.extension || ".txt"}`;

    const blob = new Blob([codifyMutation.data.content], {
      type: "text/plain",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Fetch on mount with default format
  if (
    !codifyMutation.data &&
    !codifyMutation.isPending &&
    !codifyMutation.isError
  ) {
    codifyMutation.mutate({ investigationId, format: selectedFormat });
  }

  const formatOption = FORMAT_OPTIONS.find((f) => f.value === selectedFormat);

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/50" onClick={onClose} />
      <div className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-full max-w-3xl max-h-[80vh] overflow-hidden">
        <Card className="flex flex-col max-h-[80vh]">
          <CardHeader className="pb-3 shrink-0">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <FlaskConical className="h-5 w-5 text-primary" />
                <CardTitle className="text-lg">Add as check</CardTitle>
              </div>
              <Button variant="ghost" size="icon" onClick={onClose}>
                <X className="h-4 w-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="flex-1 overflow-hidden flex flex-col">
            {/* Format Selector */}
            <div className="flex items-center gap-2 mb-4">
              <span className="text-sm text-muted-foreground">Format:</span>
              <div className="flex gap-1">
                {FORMAT_OPTIONS.map((option) => (
                  <Button
                    key={option.value}
                    variant={
                      selectedFormat === option.value ? "default" : "outline"
                    }
                    size="sm"
                    onClick={() => handleFormatChange(option.value)}
                    disabled={codifyMutation.isPending}
                  >
                    {option.label}
                  </Button>
                ))}
              </div>
            </div>

            {/* Content Area */}
            <div className="flex-1 overflow-auto rounded-md border bg-muted/30">
              {codifyMutation.isPending ? (
                <div className="flex items-center justify-center h-48">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : codifyMutation.isError ? (
                <div className="flex items-center justify-center h-48 text-destructive">
                  <AlertCircle className="h-5 w-5 mr-2" />
                  <span className="text-sm">
                    {codifyMutation.error instanceof Error
                      ? codifyMutation.error.message
                      : "Failed to generate tests"}
                  </span>
                </div>
              ) : codifyMutation.data?.content ? (
                <SyntaxHighlighter
                  language={formatOption?.language || "text"}
                  style={oneDark}
                  customStyle={{
                    margin: 0,
                    padding: "1rem",
                    fontSize: "0.75rem",
                    borderRadius: "0.375rem",
                    background: "transparent",
                  }}
                  wrapLines
                  wrapLongLines
                >
                  {codifyMutation.data.content}
                </SyntaxHighlighter>
              ) : (
                <div className="flex items-center justify-center h-48 text-muted-foreground">
                  <span className="text-sm">No content available</span>
                </div>
              )}
            </div>

            {/* Test Summary */}
            {codifyMutation.data?.tests &&
              codifyMutation.data.tests.length > 0 && (
                <div className="mt-4 p-3 bg-muted/50 rounded-md">
                  <p className="text-xs font-medium text-muted-foreground mb-2">
                    Generated Tests ({codifyMutation.data.tests.length})
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {codifyMutation.data.tests.map((test, i) => (
                      <Badge key={i} variant="outline" className="text-xs">
                        {test.test_type}
                        {test.column && `: ${test.column}`}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

            {/* Actions */}
            <div className="flex justify-end gap-2 mt-4 pt-4 border-t">
              <Button
                variant="outline"
                size="sm"
                onClick={handleCopy}
                disabled={
                  !codifyMutation.data?.content || codifyMutation.isPending
                }
                className="gap-2"
              >
                {copied ? (
                  <>
                    <Check className="h-4 w-4" />
                    Copied!
                  </>
                ) : (
                  <>
                    <Copy className="h-4 w-4" />
                    Copy to Clipboard
                  </>
                )}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleDownload}
                disabled={
                  !codifyMutation.data?.content || codifyMutation.isPending
                }
                className="gap-2"
              >
                <Download className="h-4 w-4" />
                Download {formatOption?.extension}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </>
  );
}

export function CodifyWidget({
  investigationId,
  confidence,
  isComplete,
  verdict,
}: CodifyWidgetProps) {
  const [isModalOpen, setIsModalOpen] = useState(false);

  if (!isComplete || codifyBlocker(confidence, verdict)) {
    return null;
  }

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        className="gap-1.5"
        onClick={() => setIsModalOpen(true)}
      >
        <FlaskConical className="h-4 w-4" />
        Add as check
      </Button>
      <CodifyModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        investigationId={investigationId}
      />
    </>
  );
}
