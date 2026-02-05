/**
 * Error bus for capturing frontend errors and exposing them to the assistant.
 *
 * Simple pub/sub so non-React code (HTTP client) can emit errors
 * that the PageContextProvider consumes.
 */

export interface PageError {
  type: "api" | "react" | "console";
  message: string;
  status?: number;
  url?: string;
  timestamp: number;
  stackPreview?: string;
}

type ErrorSubscriber = (error: PageError) => void;

const subscribers = new Set<ErrorSubscriber>();

export function emitApiError(error: {
  message: string;
  status?: number;
  url?: string;
}): void {
  const pageError: PageError = {
    type: "api",
    message: error.message,
    status: error.status,
    url: error.url,
    timestamp: Date.now(),
  };
  for (const fn of subscribers) {
    fn(pageError);
  }
}

export function emitReactError(error: Error, componentStack?: string): void {
  const pageError: PageError = {
    type: "react",
    message: error.message,
    timestamp: Date.now(),
    stackPreview: componentStack?.slice(0, 300),
  };
  for (const fn of subscribers) {
    fn(pageError);
  }
}

export function emitConsoleError(message: string): void {
  const pageError: PageError = {
    type: "console",
    message,
    timestamp: Date.now(),
  };
  for (const fn of subscribers) {
    fn(pageError);
  }
}

export function subscribeToErrors(fn: ErrorSubscriber): () => void {
  subscribers.add(fn);
  return () => {
    subscribers.delete(fn);
  };
}
