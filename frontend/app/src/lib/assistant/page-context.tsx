/**
 * Page context provider for the assistant.
 *
 * Tracks current route, page-specific data, and recent frontend errors
 * so the assistant always knows what the user is looking at.
 */

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useRef,
  type ReactNode,
} from "react";
import { useLocation } from "react-router-dom";
import { subscribeToErrors, emitConsoleError, type PageError } from "./error-bus";

const MAX_ERRORS = 10;

export interface PageContextData {
  route: string;
  routePattern: string;
  routeParams: Record<string, string>;
  pageType: string;
  pageTitle: string;
  pageData: Record<string, unknown>;
  errors: PageError[];
}

interface PageContextValue {
  context: PageContextData;
  registerPageContext: (data: {
    pageType: string;
    pageTitle: string;
    pageData?: Record<string, unknown>;
  }) => void;
}

const PageContext = createContext<PageContextValue | null>(null);

/** Route patterns we recognize, in order of specificity. */
const ROUTE_PATTERNS = [
  { pattern: "/investigations/:id", pageType: "investigation_detail" },
  { pattern: "/investigations/new", pageType: "investigation_new" },
  { pattern: "/investigations", pageType: "investigation_list" },
  { pattern: "/datasources/:datasourceId/datasets", pageType: "dataset_list" },
  { pattern: "/datasources", pageType: "datasource_list" },
  { pattern: "/datasets/:datasetId", pageType: "dataset_detail" },
  { pattern: "/issues/:id", pageType: "issue_detail" },
  { pattern: "/issues/new", pageType: "issue_create" },
  { pattern: "/issues", pageType: "issue_list" },
  { pattern: "/settings", pageType: "settings" },
  { pattern: "/usage", pageType: "usage" },
  { pattern: "/notifications", pageType: "notifications" },
  { pattern: "/admin", pageType: "admin" },
  { pattern: "/", pageType: "dashboard" },
] as const;

function useMatchedRoute(): { pattern: string; params: Record<string, string> } {
  const location = useLocation();

  // Try each pattern — useMatch can't be called conditionally,
  // so we match manually against the pathname.
  for (const route of ROUTE_PATTERNS) {
    const regex = new RegExp(
      "^" + route.pattern.replace(/:(\w+)/g, "(?<$1>[^/]+)") + "$",
    );
    const match = location.pathname.match(regex);
    if (match) {
      return {
        pattern: route.pattern,
        params: (match.groups ?? {}) as Record<string, string>,
      };
    }
  }

  return { pattern: location.pathname, params: {} };
}

export function PageContextProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const { pattern: routePattern, params: routeParams } = useMatchedRoute();

  const [pageInfo, setPageInfo] = useState<{
    pageType: string;
    pageTitle: string;
    pageData: Record<string, unknown>;
  }>({
    pageType: "unknown",
    pageTitle: "",
    pageData: {},
  });

  const [errors, setErrors] = useState<PageError[]>([]);
  const consoleGuardRef = useRef(false);

  // Subscribe to error bus
  useEffect(() => {
    return subscribeToErrors((err) => {
      setErrors((prev) => [...prev.slice(-(MAX_ERRORS - 1)), err]);
    });
  }, []);

  // Intercept console.error
  useEffect(() => {
    const original = console.error;
    console.error = (...args: unknown[]) => {
      original.apply(console, args);
      // Recursion guard
      if (consoleGuardRef.current) return;
      consoleGuardRef.current = true;
      try {
        const message = args
          .map((a) => (typeof a === "string" ? a : String(a)))
          .join(" ")
          .slice(0, 300);
        // Skip React internal errors that are already captured by ErrorBoundary
        if (!message.startsWith("Error caught by boundary:")) {
          emitConsoleError(message);
        }
      } finally {
        consoleGuardRef.current = false;
      }
    };
    return () => {
      console.error = original;
    };
  }, []);

  // Reset page info on route change
  useEffect(() => {
    const matched = ROUTE_PATTERNS.find((r) => r.pattern === routePattern);
    setPageInfo({
      pageType: matched?.pageType ?? "unknown",
      pageTitle: "",
      pageData: {},
    });
  }, [routePattern]);

  const registerPageContext = useCallback(
    (data: {
      pageType: string;
      pageTitle: string;
      pageData?: Record<string, unknown>;
    }) => {
      setPageInfo({
        pageType: data.pageType,
        pageTitle: data.pageTitle,
        pageData: data.pageData ?? {},
      });
    },
    [],
  );

  const contextValue: PageContextValue = {
    context: {
      route: location.pathname,
      routePattern,
      routeParams,
      pageType: pageInfo.pageType,
      pageTitle: pageInfo.pageTitle,
      pageData: pageInfo.pageData,
      errors,
    },
    registerPageContext,
  };

  return (
    <PageContext.Provider value={contextValue}>{children}</PageContext.Provider>
  );
}

/** Get the current page context (consumed by useAssistant). */
export function usePageContext(): PageContextData {
  const ctx = useContext(PageContext);
  if (!ctx) {
    throw new Error("usePageContext must be used within PageContextProvider");
  }
  return ctx.context;
}

/**
 * Register page-specific context from a page component.
 *
 * Call this in a useEffect or at the top-level of your page component
 * to advertise what the user is currently viewing.
 */
export function useRegisterPageContext(data: {
  pageType: string;
  pageTitle: string;
  pageData?: Record<string, unknown>;
}): void {
  const ctx = useContext(PageContext);
  useEffect(() => {
    if (ctx) {
      ctx.registerPageContext(data);
    }
    // Only re-register when the serialized data changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ctx, JSON.stringify(data)]);
}
