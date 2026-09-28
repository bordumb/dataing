/**
 * Fixtures for issue hub tests: messages, a stubbed issue API and a thread
 * rendered inside the hub (brief editor included).
 */

import type { ThreadMessage } from "@/lib/api/issue-threads";
import type { OrgRole } from "@/lib/auth/types";
import { stubApi, type StubResponse } from "@/test/api";
import { renderAsRole } from "@/test/auth";

import { IssueThread } from "../thread/IssueThread";
import { IssueHubProvider } from "./IssueHub";

export const ISSUE = "issue-1";
export const THREAD = "thread-1";
export const THREADS = `/api/v1/issues/${ISSUE}/threads`;
export const MESSAGES = `${THREADS}/${THREAD}/messages`;
export const RUNS = `/api/v1/issues/${ISSUE}/investigation-runs`;
export const INV = "inv-1";
export const INVESTIGATION = `/api/v1/investigations/${INV}`;

type Responder =
  | StubResponse
  | ((request: {
      body: unknown;
      query: URLSearchParams;
    }) => StubResponse | Promise<StubResponse>);

export function message(overrides: Partial<ThreadMessage>): ThreadMessage {
  return {
    id: "m-1",
    thread_id: THREAD,
    seq: 1,
    rev: 1,
    author_kind: "user",
    author_user_id: "user-1",
    requested_by_user_id: null,
    request_message_id: null,
    kind: "comment",
    body_md: "",
    payload: {},
    status: "complete",
    asks_agent: false,
    reply_to_id: null,
    created_at: "2026-09-14T08:10:00Z",
    updated_at: "2026-09-14T08:10:00Z",
    edited_at: null,
    deleted_at: null,
    ...overrides,
  };
}

export const USERS = {
  users: [
    {
      id: "user-1",
      email: "maya@acme.test",
      name: "Maya Chen",
      role: "member",
      is_active: true,
      created_at: "2026-01-01T00:00:00Z",
    },
    {
      id: "user-2",
      email: "raj@acme.test",
      name: "Raj Patel",
      role: "member",
      is_active: true,
      created_at: "2026-01-01T00:00:00Z",
    },
  ],
  total: 2,
};

export const SHARED_THREAD = {
  id: THREAD,
  issue_id: ISSUE,
  kind: "shared",
  owner_user_id: null,
  title: null,
  created_at: "2026-09-14T08:00:00Z",
};

export function run(overrides: Record<string, unknown> = {}) {
  return {
    id: "run-1",
    issue_id: ISSUE,
    investigation_id: INV,
    trigger_type: "human",
    brief: {
      version: 1,
      symptom: "Completed orders dropped 30%",
      scope: { datasource_id: null, tables: [], time_window: null },
      findings: [{ statement: "Only app_v2 dropped" }],
      ruled_out: [],
      leads: ["app_v2 deploy"],
      notes: "",
    },
    source_thread_id: THREAD,
    parent_run_id: null,
    execution_profile: "standard",
    approval_status: null,
    confidence: 0.91,
    root_cause_tag: null,
    synthesis_summary: "app_v2 writes COMPLETE instead of completed",
    created_at: "2026-09-14T08:20:00Z",
    completed_at: "2026-09-14T08:44:00Z",
    outcome_verdict: null,
    outcome_note: null,
    outcome_reviewed_by: null,
    outcome_reviewed_at: null,
    ...overrides,
  };
}

/** Stub the routes a hub thread reads; `extra` adds or overrides routes. */
export function stubHub(
  messages: ThreadMessage[],
  extra: Record<string, Responder> = {},
) {
  return stubApi({
    "GET /api/v1/users/": { body: USERS },
    [`GET ${THREADS}`]: { body: { items: [SHARED_THREAD] } },
    [`GET ${MESSAGES}`]: { body: { items: messages } },
    [`GET ${RUNS}`]: { body: { items: [], total: 0 } },
    "GET /api/v1/datasources": {
      body: {
        items: [
          {
            id: "ds-1",
            name: "warehouse",
            type: "postgres",
            category: "database",
            is_active: true,
            is_default: true,
            status: "connected",
            created_at: "2026-01-01T00:00:00Z",
          },
          {
            id: "ds-2",
            name: "lake",
            type: "duckdb",
            category: "database",
            is_active: true,
            is_default: false,
            status: "connected",
            created_at: "2026-01-01T00:00:00Z",
          },
        ],
        total: 2,
      },
    },
    ...extra,
  });
}

export function renderHub(role: OrgRole = "member") {
  return renderAsRole(
    <IssueHubProvider
      issueId={ISSUE}
      issueTitle="Completed orders dropped"
      datasetId="analytics.public.orders"
    >
      <IssueThread issueId={ISSUE} />
    </IssueHubProvider>,
    role,
  );
}
