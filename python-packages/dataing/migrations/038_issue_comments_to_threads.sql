-- Move issue comments into each issue's shared thread (docs/specs/0001_issue_chat.md).
-- Comments keep their author and timestamps and are numbered after any messages
-- already in the thread, oldest first. issue_comments is then dropped: the
-- thread API replaces the comments API (pre-launch, no compatibility layer).

INSERT INTO issue_threads (tenant_id, issue_id, kind)
SELECT DISTINCT issue.tenant_id, issue.id, 'shared'
FROM issue_comments AS comment
JOIN issues AS issue ON issue.id = comment.issue_id
ON CONFLICT (issue_id) WHERE kind = 'shared' DO NOTHING;

INSERT INTO issue_thread_messages (
    tenant_id, thread_id, seq, author_kind, author_user_id, kind, body_md,
    created_at, updated_at
)
SELECT thread.tenant_id,
       thread.id,
       COALESCE(existing.max_seq, 0)
           + ROW_NUMBER() OVER (PARTITION BY thread.id ORDER BY comment.created_at, comment.id),
       'user',
       comment.author_user_id,
       'comment',
       comment.body,
       comment.created_at,
       comment.updated_at
FROM issue_comments AS comment
JOIN issue_threads AS thread
    ON thread.issue_id = comment.issue_id AND thread.kind = 'shared'
LEFT JOIN (
    SELECT thread_id, MAX(seq) AS max_seq FROM issue_thread_messages GROUP BY thread_id
) AS existing ON existing.thread_id = thread.id;

DROP TABLE issue_comments;
