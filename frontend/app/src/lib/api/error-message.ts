/**
 * Readable messages for API error responses.
 *
 * FastAPI returns `detail` as a string, as a list of validation errors (422),
 * or as an object with a `message`. Passing it straight to `new Error()` shows
 * "[object Object]" for the last two.
 */

interface ValidationIssue {
  loc?: (string | number)[];
  msg?: string;
}

export function apiErrorMessage(
  body: unknown,
  status: number,
  fallback?: string,
): string {
  const detail = (body as { detail?: unknown } | null)?.detail;

  if (typeof detail === "string" && detail) {
    return detail;
  }

  if (Array.isArray(detail) && detail.length > 0) {
    return (detail as ValidationIssue[])
      .map((issue) => {
        // loc starts with where the value came from ("body", "query", ...)
        const field = issue.loc?.slice(1).join(".") || "field";
        return `${field}: ${issue.msg || "invalid"}`;
      })
      .join("; ");
  }

  const message = (detail as { message?: unknown } | undefined)?.message;
  if (typeof message === "string" && message) {
    return message;
  }

  return fallback || `HTTP error ${status}`;
}
