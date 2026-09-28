-- Investigations start from an editable brief (docs/specs/0001_issue_chat.md §7.7).
-- 037 backfilled every run's brief from its focus prompt; nothing writes the focus
-- prompt any more, so drop it (pre-launch, no compatibility layer).

ALTER TABLE issue_investigation_runs DROP COLUMN focus_prompt;
