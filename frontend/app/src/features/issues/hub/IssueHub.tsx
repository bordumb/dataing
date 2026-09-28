/**
 * The issue hub: shares the issue with its thread and sidebar, and owns the
 * brief editor that hands the thread's context to an investigation.
 */

import { useCallback, useMemo, useState } from "react";
import { toast } from "sonner";

import { errorText } from "@/lib/api/error-message";
import { useIssueThreads, useRequestBriefDraft } from "@/lib/api/issue-threads";
import { useRole } from "@/lib/auth/use-role";

import { BriefEditorDialog } from "../brief/BriefEditor";
import { ScratchDrawer } from "../scratch/ScratchDrawer";
import {
  IssueHubContext,
  type BriefEditorRequest,
  type IssueHub,
} from "./hub-context";

interface IssueHubProviderProps {
  issueId: string;
  issueTitle: string;
  datasetId: string | null;
  children: React.ReactNode;
}

export function IssueHubProvider({
  issueId,
  issueTitle,
  datasetId,
  children,
}: IssueHubProviderProps) {
  const { isMember } = useRole();
  const threads = useIssueThreads(issueId);
  const sharedThreadId =
    threads.data?.items.find((t) => t.kind === "shared")?.id ?? null;
  const [briefRequest, setBriefRequest] = useState<BriefEditorRequest | null>(
    null,
  );
  const [scratch, setScratch] = useState<{
    open: boolean;
    threadId: string | null;
  }>({ open: false, threadId: null });
  const requestDraft = useRequestBriefDraft(issueId);
  const { mutateAsync: requestDraftAsync } = requestDraft;

  const investigateFrom = useCallback(
    async (threadId: string) => {
      try {
        const message = await requestDraftAsync(threadId);
        setBriefRequest({ kind: "draft", threadId, messageId: message.id });
      } catch (error) {
        toast.error("The agent couldn't draft a brief", {
          description: `${errorText(error)} You can write it yourself.`,
        });
        setBriefRequest({
          kind: "brief",
          brief: { symptom: issueTitle },
          sourceThreadId: threadId,
        });
      }
    },
    [requestDraftAsync, issueTitle],
  );

  const openScratch = useCallback(
    (threadId: string | null = null) => setScratch({ open: true, threadId }),
    [],
  );
  const selectScratch = useCallback(
    (threadId: string | null) =>
      setScratch((current) => ({ ...current, threadId })),
    [],
  );

  const hub: IssueHub = useMemo(
    () => ({
      issueId,
      issueTitle,
      datasetId,
      sharedThreadId,
      canWrite: isMember,
      investigateFrom,
      isRequestingDraft: requestDraft.isPending,
      openBriefEditor: setBriefRequest,
      openScratch,
    }),
    [
      issueId,
      issueTitle,
      datasetId,
      sharedThreadId,
      isMember,
      investigateFrom,
      requestDraft.isPending,
      openScratch,
    ],
  );

  return (
    <IssueHubContext.Provider value={hub}>
      {children}
      <BriefEditorDialog
        issueId={issueId}
        issueTitle={issueTitle}
        datasetId={datasetId}
        sharedThreadId={sharedThreadId}
        request={briefRequest}
        onClose={() => setBriefRequest(null)}
      />
      {isMember && (
        <ScratchDrawer
          issueId={issueId}
          open={scratch.open}
          threadId={scratch.threadId}
          onSelect={selectScratch}
          onClose={() => setScratch((current) => ({ ...current, open: false }))}
          onInvestigate={(threadId) => {
            // The brief editor opens over the page, so the drawer steps aside.
            setScratch((current) => ({ ...current, open: false }));
            void investigateFrom(threadId);
          }}
          isRequestingDraft={requestDraft.isPending}
        />
      )}
    </IssueHubContext.Provider>
  );
}
