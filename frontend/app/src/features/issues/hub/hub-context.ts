/**
 * What the issue page shares between its thread, sidebar and dialogs: which
 * issue it is, and how to open the brief editor.
 */

import { createContext, useContext } from "react";

import type { InvestigationBrief } from "@/lib/api/investigation-runs";

/** What the brief editor opens on. */
export type BriefEditorRequest =
  | {
      /** Wait for the agent's draft in this brief message, then edit it. */
      kind: "draft";
      threadId: string;
      messageId: string;
    }
  | {
      /** Edit this brief directly. */
      kind: "brief";
      brief: InvestigationBrief;
      sourceThreadId: string | null;
      /** Set for "Continue investigating": the run this one follows. */
      parentRunId?: string | null;
    };

export interface IssueHub {
  issueId: string;
  issueTitle: string;
  datasetId: string | null;
  sharedThreadId: string | null;
  /** Members can hand off, steer and review; viewers only read and comment. */
  canWrite: boolean;
  /** Ask the agent to draft a brief from a thread, then open the editor. */
  investigateFrom: (threadId: string) => Promise<void>;
  isRequestingDraft: boolean;
  openBriefEditor: (request: BriefEditorRequest) => void;
  /** Open the scratch drawer, on one chat or (without an id) the list. */
  openScratch: (threadId?: string | null) => void;
}

export const IssueHubContext = createContext<IssueHub | null>(null);

/** The issue hub, or null when a thread renders on its own (tests, embeds). */
export function useIssueHub(): IssueHub | null {
  return useContext(IssueHubContext);
}
