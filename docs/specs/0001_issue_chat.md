# 0001: Issue hub: shared agent chat, handoff and steering

**Status:** M1–M4 shipped in PR #209. Revised 2026-09-28 with D12–D15 and M5: every run reaches the hub, one-step start, the run's details page, LLM failures, and the mockup as the acceptance reference.

**Edition:** CE. Nothing here is EE-only.

**Depends on:** principal-bound queries from [checks as code](../plans/2026-09-26-checks-as-code-design.md) §5.2 (`UserPrincipal` through `QueryGateway`).

**Related:**
- [0002](0002_dataset_connective_tissue.md): dataset tools the agent gains later (lineage, changes, code links)
- [0003](0003_okf_knowledge_layer.md): knowledge search for the agent
- PR #128, the stale "Dataing Assistant" draft (branch `feat/fn-56-dataing-assistant`). Reuse its ideas (per-turn activity, chat panel), not its code: it is 65 commits behind main and adds server-file, Docker and log tools that are out of scope here.

---

## 1. Summary

The issue page becomes the place where a team works a data problem:

- One **shared thread** per issue, where people and an agent talk.
- The agent answers ad-hoc questions by running **read-only queries as the person who asked**.
- Anyone with write access can **hand the thread's context to the investigation manager and its hypothesis subagents** as an editable brief.
- People can **steer a running investigation** (add context, rule out or add a hypothesis, stop and conclude) without restarting it.
- Each person can keep **private scratch chats** and publish from them.
- Results, confirmation and the resolution land back in the thread.
- **Every investigation lives in an issue**, however it started, and starting one is a single step from any page (D12, D13).

"Manager" is `InvestigationWorkflow`. "Subagents" are the `EvaluateHypothesisWorkflow` children it starts, one per hypothesis (`python-packages/dataing/src/dataing/temporal/workflows/`).

---

## 2. What's wrong today

Verified on main at `6e8812c8`. Paths are under `python-packages/dataing/src/dataing/` or `frontend/app/src/`.

| Area | Today | Where |
|---|---|---|
| Status menu | Lists all six statuses. The backend only allows some moves, `in_progress`/`blocked` need an assignee or acknowledgment, and `resolved` needs a note or a synthesized run. The UI sends only `{status}`, so those three statuses can't be reached. Failures go to `console.error`. | `entrypoints/api/routes/issues.py` (`STATE_TRANSITIONS`, `validate_state_transition`); `features/issues/IssueWorkspace.tsx` (`handleStatusChange`) |
| Other fields | Priority, severity, labels, assignee and description are read-only after creation. The create form collects "Issue Date" and "Column Name", then drops them. | `IssueWorkspace.tsx`; `features/issues/IssueCreate.tsx` (`handleSubmit`) |
| Comments | Single-line plain text. No edit or delete. | `IssueWorkspace.tsx` |
| Handoff | Starting an investigation from an issue takes only a free-text `focus_prompt`. Nothing the team learned reaches the manager. | `routes/issues.py` (`spawn_investigation`, `InvestigationRunCreate`) |
| Talking to a run | "Ask a question" and "Collaborate → Create Branch" send a `user_input` signal that the workflow stores and never reads: `_await_user_input` is never called. `BranchTree` and `MergeIndicator` are unused. | `temporal/workflows/investigation.py`; `features/investigation/InvestigationDetail.tsx` |
| Results | Nothing writes `issue_investigation_runs.synthesis_summary`. The summary card never renders, and "resolved via a linked investigation" can never pass. | `migrations/018_issues.sql`; `routes/issues.py` |
| Ad-hoc questions | No agent can answer them. The investigation agent is built with no tools. | `agents/client.py` |

**Found after M1–M4 shipped** (main at `245c9d2e`, 2026-09-28):

| Area | Today | Where |
|---|---|---|
| Starting a run | Every "New investigation" button opens `/investigations/new`. That page starts a run with no issue and no thread, then lands on the old run page, so nobody who starts there sees the hub. | `features/investigation/NewInvestigation.tsx` and 7 links to it |
| Runs outside the UI | `POST /investigations` (SDK, CLI, notebook) and both webhooks insert the run inline, with no run row and no start card. The EE rule action never writes its outcome back. Only one of 8 creation paths links fully to an issue. | `routes/investigations.py`, `routes/integrations.py`, EE `routes/integrations.py`, EE `core/automation/executor.py` |
| LLM failures | With a rejected key, every LLM step fails. The activities return empty results and the workflow logs warnings. The run "completes" at 0% confidence with "Unable to determine a definitive root cause". An interpretation failure reads as *refuted* evidence. The chat shows the raw `ModelHTTPError`. | `temporal/activities/*.py`, `agents/client.py`, `temporal/workflows/investigation.py` |
| Key check | Nothing checks the key. The first sign of a bad key is a run that did nothing. | `entrypoints/api/deps.py` |
| The issue page | It is close to the mockup but not the same: a separate description card, no Shared thread / scratch tabs, the sidebar split into three cards, tool calls without totals, and a card link labelled "Open". | `features/issues/` |
| The run page | Its Share menu is mocked. It has no hypotheses list, no snapshot export and no link back to the issue. | `features/investigation/InvestigationDetail.tsx` |

---

## 3. Goals and non-goals

**Goals**

1. One shared thread per issue for people and the agent.
2. Ad-hoc questions answered with read-only queries.
3. Handoff of the thread's context to the manager and subagents.
4. Steering a run while it runs.
5. Private scratch chats with explicit publishing.
6. Results, confirmation and resolution flow back into the thread.
7. A sidebar that only offers moves that will succeed, with inline editing.
8. Every investigation reaches the hub: one step to start from any page, and runs started by the API, SDK, webhooks or checks open an issue.
9. A run that can't reach the model fails with the reason, and a broken key is visible before anyone starts a run.
10. The issue page follows the mockup (`0001_issue_chat_mockup.html`), which is the acceptance reference for §8.

**Non-goals for v1**

- The agent changing anything on its own. It drafts briefs and proposes steers; a person sends them.
- A global or dataset-page assistant. The thread model here can be reused for that later.
- Writing to warehouses.
- Mirroring threads to Slack. PR #185 only creates issues from Slack.
- The server-file, Docker and log tools from PR #128.

---

## 4. The workflow this enables

Cast: Maya, the on-call data engineer who owns `orders`; Raj, an analyst whose dashboard reads `orders`; the agent.

1. **The issue opens** from a failing check (checks as code §7), an alert, Slack or by hand. The agent posts an opening summary: the dataset and its 7-day row counts, plus upstream tables, recent changes and similar past issues once 0002 lands.
2. **Back-and-forth.** Maya asks "@agent is it every region?" The agent runs a query as Maya and answers with a small table. Raj adds that his dashboard counts only `status = 'completed'`. The agent re-runs the query and narrows the drop to orders from `app_v2`. Maya assigns herself and moves the issue to In progress in one click.
3. **Hand off.** Maya clicks Investigate. The agent drafts a brief from the thread: symptom, findings, what's ruled out, leads and scope. Maya edits it and starts the run. A live card shows the manager's hypotheses and the subagents' progress.
4. **Steer.** Raj learns `app_v2` shipped on the 14th at 09:00 UTC and adds it as context. Maya rules out "late-arriving events" after seeing its first evidence. The run adapts: that subagent stops, and the new context reaches synthesis.
5. **Results.** The outcome card shows the root cause, confidence, evidence, what was ruled out and by whom, and what stayed untested. Maya confirms it.
6. **Resolve and remember.** The resolution note is pre-filled from the confirmed cause. "Add as check" (checks as code §7.6) turns the finding into a check. The confirmed cause becomes part of the dataset's history (0002, 0003).

At any point, Maya can explore in a private scratch chat, then publish the useful parts to the thread or start an investigation from the scratch chat.

---

## 5. Decisions

| # | Decision | Why |
|---|---|---|
| D1 | One **shared thread** per issue is the workspace. **Scratch chats** are private and published explicitly. | One record for the team. The handoff gets everyone's findings. Nobody re-runs a query someone already ran. Scratch chats cover exploration you don't want to share yet. |
| D2 | The agent replies only when addressed: the composer's "Ask agent" mode or an `@agent` mention. | Human discussion stays human, and cost stays predictable. |
| D3 | Queries run **as the person who asked**: a `UserPrincipal` through `QueryGateway`. They never fall back to the datasource's stored connection. If the person has no credentials, the agent says so and links to their credentials page. | Checks as code D11: "people run as themselves" and "no credentials = no queries". The database enforces each person's permissions. |
| D4 | An agent reply in the shared thread is **shared by the person who asked**. Everyone who can see the issue sees it, and the composer says so. | It's the same as pasting a result into a comment, and the UI is honest about it. Scratch chats exist for results you don't want to share. |
| D5 | The agent is **read-only**. It can't change the issue, and it can't start, steer or stop a run. It proposes; a person clicks. | Text inside query results can't turn into actions (prompt injection), and every change has a human actor. |
| D6 | The handoff sends an **editable, structured brief**, not the raw transcript. | The manager needs findings and exclusions, not chat noise. People control what's sent. |
| D7 | Steering is a Temporal **signal applied at checkpoints**, and nothing restarts. A steer that arrives during synthesis triggers one re-synthesis. After a run finishes, "Continue investigating" starts a linked follow-up run seeded with the result. | Steering mid-run replaces the restart-with-an-edited-brief approach. Checkpoints keep the workflow deterministic. |
| D8 | Agent turns in a thread run **one at a time, in order**, through one Temporal workflow per thread. | A shared thread stays coherent when two people ask at once. |
| D9 | Comments, agent replies and system events share **one timeline table**. Issue events also append a system entry. | One cursor for streaming, and no merging of sources in the UI. |
| D10 | Every result the agent saw is **snapshotted with its message**, and every query is in the gateway's audit log. | Data changes; the thread must show what the agent actually saw. |
| D11 | Model: `claude-sonnet-5-5` (Claude Sonnet 5.5), the same model as investigations; `dataing/config.py` is the one place that names models. Effort is `low` for chat turns and `medium` for brief drafting, configurable per route. Brief drafting returns JSON text instead of calling an output tool, because recent models (Claude Opus 5.5) reject a forced `tool_choice`. | Speed comes from effort. The owner moved chat from Claude Opus 5 to Opus 5.5 for cost, then on 2026-09-29 to Sonnet 5.5 with investigations, after Sonnet 4 was retired (§12). |
| D12 | **Every investigation belongs to an issue.** A run started without one (API, SDK, webhook, check) opens an issue, or reuses the open one for the same alert, and reports into its shared thread. There is no issue-less run. | One place to follow every run. The hub (thread, card, steering, outcome review) works for every run, not only the ones started from an issue. |
| D13 | **One step from intent to a running investigation.** Every start button opens the brief editor where the person already is, pre-filled with what that page knows (the dataset, the alert). Start opens the issue and the run together and lands on the issue's thread. `/investigations/new` is removed. | The old page was a middle layer that started runs outside the hub. Opening the issue on Start, not on click, means a cancelled editor leaves no empty issue, and the issue's title is the symptom the person typed. |
| D14 | **The thread's card is the main view of a run.** `/investigations/:id` becomes the run's details page, linked from the card and the sidebar. It keeps what the card has no room for: the evidence, every query with its result, share, snapshot export and Add as check. | The team works in the thread; the details page is for digging in. Nothing the old page did is lost. |
| D15 | **LLM failures fail the run, loudly.** Errors a retry can't fix (a missing or rejected key, an unknown model, a rejected request) fail the run at once with the reason on its card. Rate limits, overload and server errors retry with backoff first. A run never synthesizes a conclusion from steps that all failed. The API checks the key and models at startup, and every page shows a banner while they don't work. | A run that "completes" at 0% confidence after doing nothing hides the real problem. The fix is usually one environment variable, so say which. |

---

## 6. Data model

Add one migration at the next free number:
- Use the current tenant key: `tenants(id)` today, `organizations(id)` once fn-59 lands.
- Migrations are append-only and contain no `BEGIN`/`COMMIT`.

```sql
CREATE TABLE issue_threads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    issue_id UUID NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('shared', 'scratch')),
    owner_user_id UUID REFERENCES users(id),
    title TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK ((kind = 'shared') = (owner_user_id IS NULL))
);
CREATE UNIQUE INDEX issue_threads_one_shared ON issue_threads (issue_id) WHERE kind = 'shared';

CREATE TABLE issue_thread_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id UUID NOT NULL REFERENCES issue_threads(id) ON DELETE CASCADE,
    seq BIGINT NOT NULL,
    author_kind TEXT NOT NULL CHECK (author_kind IN ('user', 'agent', 'system')),
    author_user_id UUID REFERENCES users(id),
    requested_by_user_id UUID REFERENCES users(id),  -- agent replies: who asked
    kind TEXT NOT NULL CHECK (kind IN (
        'comment', 'agent_reply', 'brief', 'steer', 'investigation', 'event', 'published')),
    body_md TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'complete' CHECK (status IN (
        'queued', 'streaming', 'complete', 'error', 'cancelled')),
    asks_agent BOOLEAN NOT NULL DEFAULT FALSE,
    reply_to_id UUID REFERENCES issue_thread_messages(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    edited_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    UNIQUE (thread_id, seq)
);
CREATE INDEX issue_thread_messages_cursor ON issue_thread_messages (thread_id, updated_at, id);

CREATE TABLE agent_query_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id UUID NOT NULL REFERENCES issue_thread_messages(id) ON DELETE CASCADE,
    tool_call_id TEXT NOT NULL,
    datasource_id UUID NOT NULL,
    sql TEXT NOT NULL,
    dialect TEXT NOT NULL,
    columns JSONB NOT NULL,
    rows JSONB NOT NULL,         -- snapshot, capped (§7.5)
    row_count INTEGER NOT NULL,  -- rows the query returned before the cap
    truncated BOOLEAN NOT NULL,
    duration_ms INTEGER NOT NULL,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE investigation_steers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id UUID NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
    issue_id UUID REFERENCES issues(id) ON DELETE SET NULL,
    message_id UUID REFERENCES issue_thread_messages(id) ON DELETE SET NULL,
    kind TEXT NOT NULL CHECK (kind IN (
        'add_context', 'rule_out', 'add_hypothesis', 'stop_and_synthesize')),
    text TEXT NOT NULL,
    hypothesis_id TEXT,
    actor_user_id UUID NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'applied', 'rejected')),
    applied_phase TEXT,
    outcome TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    applied_at TIMESTAMPTZ
);
```

**Assigning `seq`:** lock the thread row, then take `MAX(seq) + 1`. Order never depends on clocks.

**Changes to existing tables**

- **`issue_comments`:** copy the rows into each issue's shared thread as `comment` messages, then drop the table and its routes. We're pre-launch, so there's no compatibility layer.
- **`issue_investigation_runs`:**
  - Replace `focus_prompt` with `brief JSONB NOT NULL`.
  - Add `source_thread_id` and `parent_run_id` (for follow-up runs).
  - `synthesis_summary`, `confidence` and `root_cause_tag` are now actually written (§7.7).
- **`issues`:** add `context JSONB NOT NULL DEFAULT '{}'`. It holds what the create form collects today and drops: `observed_at` and `column`.

---

## 7. Backend

### 7.1 API

All paths are under `/api/v1`. Gates use the names from the route authorization policy (`tests/unit/entrypoints/api/routes/test_route_authorization.py`): `ANY_USER`, `SCOPE_WRITE`, `SCOPE_ADMIN`. Every new mutating route gets a `POLICY` entry.

| Method and path | Gate | Notes |
|---|---|---|
| `GET /issues/{issue_id}/threads` | ANY_USER | Returns the shared thread plus the caller's own scratch threads |
| `POST /issues/{issue_id}/threads` | SCOPE_WRITE | Creates a scratch thread |
| `DELETE /issues/{issue_id}/threads/{thread_id}` | Owner | Deletes the caller's own scratch thread |
| `GET /issues/{issue_id}/threads/{thread_id}/messages?after_seq=&limit=` | ANY_USER for the shared thread, owner for a scratch thread | Pages by `seq` |
| `POST /issues/{issue_id}/threads/{thread_id}/messages` | See note | Body: `body_md`, `ask_agent`, `reply_to_id`. A comment in the shared thread needs ANY_USER. `ask_agent: true` needs SCOPE_WRITE. A scratch thread is owner-only. |
| `PATCH .../messages/{message_id}` | Author | Edits the caller's own comment |
| `DELETE .../messages/{message_id}` | Author or SCOPE_ADMIN | Soft delete |
| `POST .../messages/{message_id}/cancel` | Requester or SCOPE_ADMIN | Cancels a queued or streaming agent turn |
| `GET .../threads/{thread_id}/stream?after=` | Same as reading the thread | SSE, see §7.3 |
| `POST .../threads/{thread_id}/publish` | Scratch-thread owner | Body: `message_ids`, `note` |
| `POST .../threads/{thread_id}/brief-drafts` | SCOPE_WRITE | Queues a `draft_brief` turn; the draft streams into a `brief` message |
| `POST /issues/{issue_id}/investigation-runs` | SCOPE_WRITE | Body: `brief`, `execution_profile`, `datasource_id`, `source_thread_id`, `parent_run_id`. Replaces `focus_prompt`, whose only caller is `IssueWorkspace.tsx`. |
| `POST /investigations/{investigation_id}/steers` | SCOPE_WRITE | Body: `kind`, `text`, `hypothesis_id` |
| `GET /investigations/{investigation_id}/steers` | ANY_USER | Includes each steer's status and outcome |
| `POST /investigations/{investigation_id}/outcome-review` | SCOPE_WRITE | Body: `verdict` (`confirmed` or `rejected`), `note` |
| `POST /investigations` | SCOPE_WRITE | Starts a run from a `brief` or an `alert`, opening an issue unless `issue_id` is given (§7.11) |
| `GET /system/llm` | ANY_USER | Whether the key and models work (§7.12) |

**Removed:** `GET/POST /issues/{issue_id}/comments`, `POST /investigations/{investigation_id}/messages` and `POST /investigations/{investigation_id}/input`.

### 7.2 Sidebar fixes

- **Only valid moves:** add `IssueResponse.allowed_transitions: list[str]`, computed from `STATE_TRANSITIONS` and the guards applied to the issue's current fields. The UI offers only these.
- **Missing fields are asked for inline:**
  - Moving to In progress or Blocked without an assignee prompts "Assign to me?" and sends both fields in one PATCH.
  - Moving to Resolved prompts for a note, pre-filled from a confirmed outcome.
- **PATCH can clear fields:** a field sent explicitly as `null` clears it (tracked with Pydantic's `model_fields_set`); a missing field is left unchanged. PATCH also accepts `dataset_id` and `due_at`.
- **Inline editors** for priority, severity, labels and assignee. Watchers and the assignee show names, not UUIDs.
- **Errors are visible:** every failed change shows a toast with the server's message.

### 7.3 Streaming

Reuse the polling SSE pattern of `stream_issue_events` in `routes/issues.py` (cursor plus 30-second heartbeats), with two changes:
- Poll every 250 ms.
- Use an `(updated_at, id)` cursor, because streaming messages are updated in place.

Each event carries the full message row, and the client replaces it by `id`. Passing `after` makes reconnects lossless.

If polling load becomes a problem, switch to Postgres `LISTEN/NOTIFY` behind the same endpoint.

### 7.4 Agent turns

**`IssueThreadWorkflow`** runs once per thread, with id `issue-thread-{thread_id}`.
- It is started with signal-with-start on the first agent request. It holds a first-in-first-out queue of request message ids and runs one turn at a time.
- It completes after 30 minutes idle; the next request starts it again. It calls `continue_as_new` every 50 turns to keep its history bounded.
- It handles two request types: `answer` (a comment with `asks_agent`) and `draft_brief`.

**`run_agent_turn`** is a heartbeating activity. Each turn:
1. Builds the prompt (§7.6) and a `BondAgent` with the chat tools (§7.5).
2. Creates the reply message with `status = 'streaming'` and `requested_by_user_id` set to the asker.
3. Streams text into `body_md`, flushing every 250 ms or 200 characters.
4. Records each tool call in `payload.tool_calls` as `{id, tool, input, status, summary, query_result_id, duration_ms, row_count}`. The last two are set for `run_query` only.
5. Ends in `complete`, `error` (with the message) or `cancelled`, and records token usage, including cache reads, in `payload.usage`.

**Limits** (configuration now, per tenant later):
- 10 tool calls and 90 seconds per turn.
- 30 seconds per query.
- One running turn per thread, and three per person across all threads.

**Temporal notes:**
- Read activity results as dicts inside workflows; typed results fail in the workflow sandbox.
- Cover both workflows with Replayer tests on recorded histories.

### 7.5 Agent tools

| Tool | What it does | Notes |
|---|---|---|
| `get_issue_context()` | Issue fields and `context`, dataset, recent events, and linked runs with their status and outcome | |
| `list_tables(pattern?)` | Tables in the issue's datasource | Runs through the gateway as the asker, so the list shows what they can see |
| `describe_table(table)` | Columns and types, plus a row count when the adapter can get one cheaply | |
| `run_query(sql, purpose)` | Runs a read-only query | See the list below |
| `get_investigation(run_id)` | Hypotheses with status, evidence summaries, synthesis and steers | |
| `propose_steer(run_id, kind, text, hypothesis_id?)` | Adds a steer proposal card to the reply | Only a proposal; a person clicks "Send steer" |

How `run_query` works:
- **Validation:** the same path as the investigation `execute_query` activity (`temporal/activities/execute_query.py`, `safety/validator.py`). It is dialect-aware, allows a single `SELECT`, blocks forbidden statements, enforces a `LIMIT`, and returns at most 1,000 rows.
- **Execution:** through `QueryGateway` as `UserPrincipal(asker)`.
- **Snapshot:** at most 200 rows or 256 KB, stored in `agent_query_results`.
- **What the model sees:** the columns, the first 50 rows, `row_count`, `truncated`, and simple column stats.

Tools from the other specs join when they land: `get_lineage`, `get_recent_changes`, `get_code_links` and `get_dataset_knowledge` (0002), and `search_knowledge` (0003).

No tool writes anything. If the asker has no credentials for the datasource, `run_query` returns a typed `credentials_missing` error. The agent explains, and the UI links the asker to their credentials page (checks as code §5.2 adds that page).

### 7.6 Prompt assembly and caching

- **Stable prefix:** the order is frozen system prompt, then a fixed tool list, the issue context block, thread history, and finally the request. The system prompt holds no timestamps or ids, and rendered JSON uses sorted keys. This keeps the prefix byte-stable, so prompt caching reuses it across turns. Check `cache_read_input_tokens` in `payload.usage`.
- **What history contains:**
  - human comments, labeled by author
  - agent replies
  - tool calls, as summaries with `query_result_id` references rather than full tables
- **Long threads:** every 20 turns, the agent writes a visible "Thread summary" system message. Later turns send that summary plus the most recent turns.
- **Facts that arrive between turns** (a run finished, a status changed) go in as the latest context entry. Earlier prompt text is never edited.
- **Model settings:** verify that the bond-agent / pydantic-ai stack exposes cache control, effort and adaptive thinking for Anthropic models. If it doesn't, add them there rather than calling the SDK directly from dataing.

### 7.7 Handoff: brief → manager and subagents

The brief schema is `InvestigationBrief` (Pydantic, versioned):

```json
{
  "version": 1,
  "symptom": "Completed orders dropped about 30% on 2026-09-14",
  "scope": {
    "datasource_id": "…",
    "tables": ["analytics.public.orders", "raw.app_events"],
    "time_window": {"from": "2026-09-10T00:00:00Z", "to": "2026-09-16T00:00:00Z"}
  },
  "findings": [
    {"statement": "The drop is only in orders with source = app_v2",
     "message_id": "…", "query_result_id": "…"}
  ],
  "ruled_out": [
    {"statement": "Not region-specific", "message_id": "…", "query_result_id": "…"}
  ],
  "leads": ["app_v2 deploy on 2026-09-14"],
  "notes": "The dashboard counts status = 'completed' only"
}
```

**Flow:**
1. The person clicks Investigate, which calls `POST .../brief-drafts`. The draft is structured output, validated against the schema.
2. The person edits the draft in a dialog.
3. Submitting calls `POST /issues/{issue_id}/investigation-runs`.

`InvestigationInput` gains `brief: dict[str, Any]`. The manager uses it at each step:
- **`gather_context`:** fetches the schema for every table in `scope.tables`, not only the alert's dataset.
- **`generate_hypotheses`:** receives:
  - the symptom
  - findings, as observed facts
  - `ruled_out`, as exclusions ("do not propose")
  - leads, as hypotheses to test first
  - the notes
- **Each subagent:** gets the findings and notes along with its hypothesis.
- **`synthesize`:** gets findings, exclusions and steers, and keeps three outcomes apart: refuted by evidence, ruled out by a person, and untested.

**Thread entries:**
- An `investigation` message when the run starts, holding the run id, profile and brief. It updates as the run progresses; the card also subscribes to `GET /investigations/{investigation_id}/stream`.
- An agent message with the outcome when the run ends.

**Writing the outcome back:** a final activity, `publish_investigation_outcome`, runs when the run is linked to an issue. It writes `synthesis_summary`, `confidence` and `root_cause_tag` to `issue_investigation_runs`, and appends the outcome message.

**Credentials:**
- Runs that people start use `UserPrincipal(initiator)`. This needs investigation queries to go through the gateway, a follow-up already named in checks as code §5.2.
- Runs that checks start stay on `AutomationPrincipal`.
- Until that follow-up lands, runs use today's worker path, like every other investigation.

**"Continue investigating"** appears after a run ends. It starts a new run with `parent_run_id` set. The new brief is pre-filled with the prior synthesis as findings and the person's new instruction as a lead.

### 7.8 Steering

| Kind | Meaning | Before hypotheses exist | While subagents run | During synthesis |
|---|---|---|---|---|
| `add_context` | A new fact or constraint | Added to the generation input | Given to subagents started afterwards, and to synthesis | Triggers one re-synthesis |
| `rule_out` | Stop testing a hypothesis, with a reason | Stored as an exclusion | Cancels that subagent; the hypothesis is marked "ruled out by a person" | Triggers one re-synthesis |
| `add_hypothesis` | Test this too | Added as a seed | A `formulate_hypothesis` activity turns the text into a hypothesis and a new subagent starts. Capped at `max_hypotheses + 3` in total. | Rejected with "use Continue investigating" |
| `stop_and_synthesize` | That's enough; conclude now | Rejected | Cancels the remaining subagents; their hypotheses stay untested | No effect |

**Changes to `InvestigationWorkflow`:**
- **New signal:** `steer(payload: dict)`. Steers queue in workflow state.
- **Checkpoints:** `_apply_steers(phase)` runs after `gather_context`, after `generate_hypotheses` and before `synthesize`.
- **Evaluation loop:** `_evaluate_hypotheses_parallel` becomes an event loop in place of the single `asyncio.gather`. `workflow.wait_condition` wakes on either a finished child or a queued steer. Children are tracked by hypothesis id, so `rule_out` cancels the right one.
- **After the run finishes:** a steer is rejected with "Finished: use Continue investigating".
- **Status query:** `get_status` gains `hypotheses` (id, title, status) and `pending_steers`, so the card can show controls for each hypothesis.
- **Recording outcomes:** each steer ends as `applied` or `rejected`. The `record_steer_outcome` activity updates `investigation_steers` and appends a system message, for example "Applied during evaluation: cancelled H3 'late-arriving events'".
- **Removed:** the `user_input` signal, `_user_input`, `_await_user_input` and `is_awaiting_user`.
- **In-flight runs:** guard the new code path with `workflow.patched("steering-v1")` so runs already in flight still replay.

**Who can steer:**
- Steers need SCOPE_WRITE.
- People can steer runs that checks started. The steer records the person who sent it, and the run's credentials don't change.

**From chat:** "@agent tell the investigation that app_v2 shipped at 09:00" makes the agent answer with a `propose_steer` card. A person clicks Send.

### 7.9 Scratch chats

- **Creating:** people create them from the issue, and can have several per issue.
- **Privacy:** only the owner can read a scratch chat. Everyone else, admins included, gets a 404. Its queries still appear in the gateway's audit log.
- **Agent:** the same agent, tools and credentials as the shared thread, running as the owner.
- **Publish:** the owner selects messages, which produces one `published` message in the shared thread, authored by the owner. It contains the selected text and **copies** of the result snapshots, so deleting the scratch chat doesn't break the shared thread.
- **Investigate from here:** the brief draft reads both the scratch chat and the shared thread. The run, its card and its brief appear in the shared thread ("Maya started an investigation from her scratch chat").
- **Retention:** kept until the owner deletes them or the issue is deleted.

### 7.10 Results and resolution

- **The outcome card** shows:
  - the root cause and confidence
  - supporting evidence (queries with their snapshots)
  - hypotheses ruled out by evidence and by people
  - untested hypotheses
- **Confirm or Reject** (`outcome-review`, SCOPE_WRITE) records investigation feedback and posts to the thread.
  - Confirm pre-fills the resolution note.
  - Reject asks why and offers Continue investigating.
- **Add as check** works as described in checks as code §7.6.
- **Downstream:** resolving an issue with a confirmed outcome emits `issue.resolved_with_cause`. 0002 lists these on the dataset, and 0003 can export them.

### 7.11 Starting investigations (D12, D13)

**One starter.** `InvestigationStarterService.start()` (`services/investigation.py`) is the only code that starts an investigation. It:
1. **Resolves the issue.**
   - Given an `issue_id`, it uses that issue, which must belong to the tenant.
   - Otherwise it opens one with `open_issue()`. The title is the brief's symptom, the dataset is the first scope table, and the severity comes from the alert. `created_by` is the person, or NULL for API keys and webhooks.
2. **Builds the missing half** of the input:
   - Given a brief, it builds the workflow's alert from it, as the spawn route does today.
   - Given an alert (SDK, webhooks), it builds the brief:
     - the symptom from the alert's display name and values
     - the scope from its dataset ids and datasource
     - the time window as the anomaly date ± 1 day
3. **Writes the run.** It inserts the `investigations` row (with `created_by`), the `issue_investigation_runs` row and the thread's `investigation` card.
   - The run row's `trigger_type` is `human`, `api`, `webhook` or `rule`.
   - A run without a person is attributed to dataing ("dataing started an investigation").
4. **Starts the workflow** with `alert.issue_id` set, so the outcome is always written back.
   - If the start fails, the run gets a failed outcome ("Couldn't start the investigation: …") and the route returns 503.
5. **Returns** `investigation_id`, `run_id`, `issue_id` and `issue_number`.

**Opening issues.** `open_issue()` (`adapters/db/issues.py`) is the one way to insert an issue: `POST /issues`, both webhooks and the starter all use it.
- It records the `created` event, which also posts the thread's first entry: "Maya opened the issue", or "Issue opened by dataing from Monte Carlo".
- Today, webhook-opened issues get no thread entry.

**Every path, after this change:**

| Path | Today | After |
|---|---|---|
| `POST /issues/{id}/investigation-runs` | Starter, then the run row and card inline | Starter, with the issue |
| `POST /investigations` (UI, SDK, CLI, notebook) | Inline insert; no issue, run row or card | Starter; opens an issue unless `issue_id` is given |
| CE `webhook-generic` and EE provider webhooks, policy AUTO | Inline insert and a direct Temporal start. Only `alert.issue_id` links it: no run row, no start card, and outcome review returns 404. | Starter, with the issue the webhook opened, `trigger_type = webhook` |
| EE rule action `spawn_investigation` | Starter, but no `alert.issue_id`, so the outcome is never written back | Starter, with the issue, `trigger_type = rule` |
| `POST /investigations/import` | Inserts a finished replay record | Unchanged. It is a record, not a run, so it has no issue; its details page has no back link. |

Two dormant creation paths had no callers and are removed: the Redis queue worker (`adapters/queue/`) and `InvestigationService` with its branch/collaboration domain (`core/investigation/service.py` and friends, `adapters/db/investigation_repository.py`). The starter is the only code that creates an investigation.

**`POST /investigations`** (SCOPE_WRITE):

```json
{
  "brief": {"symptom": "…", "scope": {"tables": ["public.orders"]}},
  "alert": null,
  "datasource_id": null,
  "execution_profile": "standard",
  "issue_id": null
}
```

- **Body:**
  - Exactly one of `brief` and `alert`. A bad alert is a 422, not today's 500.
  - The datasource resolves as it does today; an ambiguous one is a 409 with `ambiguous_datasource`.
- **Response:** `investigation_id`, `run_id`, `issue_id`, `issue_number`, `status: "queued"`, and `main_branch_id` for the SDK.
- **SDK and CLI:** the SDK's `Investigation` gains `issue_id` and `issue_number`. `dataing run start` prints the issue's URL.

**Run numbers and status:**
- `InvestigationRunResponse` gains `number` (the run's position among the issue's runs, by start time), `status` (`running`, `completed` or `failed`, from the outcome) and `error`. Today a failed run shows "running" forever.
- `InvestigationStateResponse` (`GET /investigations/{id}`) gains `issue_id`, `issue_number`, `issue_title`, `run_number`, `brief`, `execution_profile` and `error`.

### 7.12 LLM failures and the key check (D15)

**Today:** a rejected key never fails a run.
1. Every LLM activity catches the exception and returns empty results.
2. `AgentClient.interpret_evidence` turns an LLM error into evidence, so the hypothesis reads as *refuted*.
3. The workflow logs each error as a warning, synthesizes from nothing, and publishes `status: "completed"` at confidence 0.

The chat agent shows the raw `ModelHTTPError` text.

**Classifying errors.** `classify_llm_error(exc)` (`agents/errors.py`) follows the exception chain (`LLMError` → pydantic-ai `ModelHTTPError`/`ModelAPIError` → `anthropic.*Error`) and returns a code, whether a retry can help, and a message that says what to fix:

| Code | Cause | Retry? | Message |
|---|---|---|---|
| `missing_key` | `ANTHROPIC_API_KEY` is empty | no | "ANTHROPIC_API_KEY isn't set. Set it and restart the API and the worker." |
| `invalid_key` | 401 | no | "Anthropic rejected the API key (401). Set a valid ANTHROPIC_API_KEY and restart the API and the worker." |
| `forbidden` | 403 | no | "The API key isn't allowed to use {model} (403)." |
| `unknown_model` | 404 | no | "Anthropic doesn't know the model {model} (404). Check LLM_MODEL and CHAT_AGENT_MODEL." |
| `bad_request` | 400, 413, 422 | no | "Anthropic rejected the request ({status}): {detail}" |
| `rate_limited` | 429 | yes | "Anthropic rate-limited the request (429)." |
| `overloaded` | 529 | yes | "Anthropic is overloaded (529)." |
| `server_error` | other 5xx | yes | "Anthropic returned an error ({status})." |
| `unreachable` | connection error, timeout | yes | "Couldn't reach Anthropic: {detail}" |

**Activities raise instead of returning an error.**
- On an LLM error, `generate_hypotheses`, `generate_query`, `interpret_evidence`, `synthesize` and `counter_analyze` raise a Temporal `ApplicationError`:
  - type `LLMRejected` and `non_retryable=True` when a retry can't help
  - type `LLMUnavailable` otherwise
  - details `{code, message}` in both cases
- Every LLM activity call gets an explicit retry policy: 4 attempts, 5 s initial backoff, ×2, capped at 60 s. `LLMRejected` is non-retryable. The Anthropic SDK already retries 429/5xx twice inside each attempt.
- `AgentClient` stops swallowing errors in `interpret_evidence`.

**The workflow fails the run.** New code paths are guarded with `workflow.patched("llm-failures-v1")`. The run fails when:
- hypothesis generation fails, or proposes nothing and no person added a hypothesis;
- any hypothesis evaluation fails with an LLM error. The key or model is broken for every subagent, so the others are cancelled.
- every hypothesis ended untested because of errors. Hypotheses a person ruled out or stopped don't count.
- synthesis fails.

Counter-analysis failing doesn't fail a run whose synthesis succeeded. The outcome records `counter_analysis.error` and the card says the check didn't run.

**What a failed run does:**
1. It publishes a failed outcome through `publish_investigation_outcome`: `{"status": "failed", "error": {"code", "message", "step"}}`. This writes `investigations.outcome`, the run row (`completed_at`) and the thread card.
2. It raises a non-retryable `ApplicationError`, so Temporal shows the execution as failed too.

The card shows a red "failed" pill, the message and **Retry**.

**Chat turns and brief drafts.** `run_agent_turn` classifies the error the same way. The reply shows the message, not the raw exception, and a turn that can't succeed on retry isn't retried.

**The key check.**
- At startup the API calls `GET /v1/models/{id}` for each configured model (`LLM_MODEL`, `CHAT_AGENT_MODEL`). This costs no tokens.
  - It runs in the background with a 10-second timeout and no SDK retries, so a slow or missing network never delays startup.
  - An empty key is reported without a request.
- `GET /system/llm` (ANY_USER) returns `{state, message, models, checked_at}`.
  - `state` is `ok`, `checking` or one of the codes above.
  - An `unreachable` result older than 60 seconds is checked again on read.
- The key is read from the environment, so a fixed key takes effect when the API and the worker restart; the check reruns at startup.

---

## 8. Frontend

- **Layout:** the thread on the left, the sidebar on the right. The sidebar collapses on narrow screens.
- **Thread:** a virtualized list that renders each message kind. Markdown goes through `react-markdown` with `remark-gfm` and `rehype-sanitize`; these are new dependencies, and the Knowledge tab reuses the same renderer in 0002.
- **Agent replies:** text streams in. Tool calls collapse to one line ("Ran 2 queries ▸"). Expanded, each shows the SQL with a copy button, the result table, the row count, a truncation note and the duration.
- **Composer:** a Comment / Ask agent toggle, plus `@agent` mentions.
  - For viewers, Ask agent is disabled and says why.
  - In the shared thread, a hint reads "Agent replies are visible to everyone on this issue".
- **Investigation card:**
  - the current phase
  - hypotheses with their status, each with a Rule out button
  - Add context, Add hypothesis and Stop and synthesize
  - a list of steers with their status
- **Brief editor:** the schema's fields, pre-filled from the draft. Each finding links to its source message. Includes execution profile and datasource pickers.
- **Scratch chats:** a drawer with the person's scratch chats. Each opens a chat panel with Publish selected and Investigate from here.
- **Sidebar:** status (allowed transitions only), assignee, priority, severity, labels, dataset, watchers by name, and linked runs.
- **Removed:** "Ask a question" and "Collaborate → Create Branch" on the investigation page, plus `BranchTree` and `MergeIndicator`.
- **API client:** regenerate the orval client for the new routes. The committed `openapi.json` has drifted from the app, so either regenerate only these operations or do the full refresh as a separate PR.

### 8.1 Following the mockup

`0001_issue_chat_mockup.html` is the acceptance reference for the issue page. Where the page and the mockup differ, the mockup wins:

- **Top bar:** the `#N` pill, the title, the status and priority pills, and the dataset on the right, in one row.
- **No separate description card.** The description is the thread's first entry: "Maya opened the issue", with the description as its body and Edit for its author. An issue opened by dataing starts with the event line instead ("Check … failed · issue opened by dataing").
- **Thread head:** two tabs, **Shared thread** and **My scratch chats (N)**, and "N watching · live" on the right. The scratch tab opens the scratch drawer.
- **One sidebar panel,** in this order:
  1. Status, with **Change ▾**. The menu starts with the note "Only moves that will succeed are shown", and Resolved says it asks for a note pre-filled from the confirmed cause.
  2. Details: assignee, priority, severity, labels, observed, column.
  3. Dataset, with "open dataset page →".
  4. Investigations: one row per run ("#2 · standard" and a status pill), linking to the run's details page.
  5. Watchers, by name.
  6. Your scratch chats, and **＋ New scratch chat**.

  The Timeline section goes; the thread already records when things happened.
- **Tool calls** collapse to one line with the totals: "▸ Ran 1 query · 212 ms · 4 rows" or "▸ Ran 2 queries · 480 ms". Expanded, the footer reads "Snapshot saved with this message · copy SQL". The tool-call record stores `duration_ms` and `row_count` so the line needs no extra request.
- **Pills** use the mockup's colours: purple for the agent and running work, green for supported and done, amber for in progress and untested, red for refuted and failed, blue for people's additions.
- **Investigation card:** "Investigation #N", where N counts the issue's runs in start order. It has a **details →** link to the run's page. A failed run shows a red "failed" pill, the reason and **Retry**, which reopens the brief editor with the same brief.

### 8.2 Starting an investigation (D13)

- **Removed:** the `investigations/new` route, `NewInvestigation.tsx`, and the unused `components/Layout.tsx`.
- **Every start button becomes Investigate…** and opens the brief editor in *new* mode where the person is:
  - the sidebar's quick action
  - the dashboard header and its empty recent-investigations card
  - the investigations list header and its empty state
  - the dataset page, as **Investigate this dataset** in the header, shown whether or not the dataset has runs
- **New mode** is the same editor, titled "Start an investigation":
  - It is pre-filled from the page. The dataset page supplies the table's `native_path` as the scope table and its `datasource_id`; the other pages supply nothing.
  - Symptom and at least one scope table are required.
  - Findings and ruled out start empty, and there are no leads; there is no thread to draft from.
  - **Start investigation** calls `POST /investigations` (§7.11) and navigates to `/issues/{issue_id}`, where the card is already live.
- **Both modes** pick scope with the removed page's components:
  - **Table(s)** is a list of `DatasetEntry` rows: a datasource select and a table field that looks tables up in that datasource's schema as the person types. **Add another table** adds a row.
  - A run investigates one datasource, so every row shows the same one and changing it in any row changes it for all. It starts as the brief's datasource, else the tenant's default, else its first; a datasource the tenant no longer has is replaced the same way. There is no "The issue's datasource" option: the server never used the issue for this (it falls back to the tenant's only datasource and answers 409 when there are several), so the page shows its pick instead.
  - **Time window (optional)** is the `DatePicker`: one day or a range, with quick picks. Days map to whole UTC days, `[first day 00:00Z, day after the last 00:00Z)`. A window that ends mid-day opens as the day it ends on.
- **Hand off** mode (from a thread) keeps its leads, tested first.

### 8.3 The run's details page (D14)

`/investigations/:id` keeps its URL and becomes the run's details page:

- **Header:**
  - a back link to the issue's thread ("← #42 Completed orders dropped")
  - "Investigation #N" with its status and depth pills
  - **Share**, which copies the link (the mocked user picker goes)
  - **Export snapshot**, which downloads `GET /investigations/{id}/snapshot`
  - **Add as check** (renamed from "Codify Test", same gating)
  - Cancel, while the run is running
- **Brief:** the brief the run was given.
- **Hypotheses:** each with its status pill (including "ruled out by a person" and "untested") and its evidence. Queries collapse like the thread's tool calls and expand to the SQL, the result summary and the interpretation.
- **Outcome:** the root cause card in the thread's style, with the causal chain, onset, affected scope and recommendations, plus the existing feedback buttons.
- **A failed run** shows the failure reason and what to fix in place of the outcome.
- **Backend:** `InvestigationStateResponse` gains `issue_id`, `issue_number` and `issue_title`.

### 8.4 LLM status banner (D15)

- The app polls `GET /system/llm` (§7.12) once a minute.
- While it reports a problem, a banner under the header on every page names it and says what to fix, for example "Anthropic rejected the API key. Investigations and the agent can't run until ANTHROPIC_API_KEY is fixed and the API and worker are restarted."
- It can't be dismissed while the problem lasts.

---

## 9. Security and privacy

- **Exposure:** see D3 and D4. The database enforces what each asker can read. Sharing a reply is the asker's act, and the UI says so.
- **Prompt injection:**
  - Query results, and later repository content, are untrusted and reach the model as clearly delimited data.
  - The agent has no write tools.
  - Briefs and steers need a person's click.
  - All markdown is sanitized.
- **PII:** `safety/pii.py` has redaction helpers, but nothing calls them today. v1 redacts detected PII in tool results before they reach the model. The snapshots people see are not redacted. Whether this is on by default is an open question.
- **Audit:** queries go to the gateway's `query_audit_log` under the user's credentials, and the thread records who asked what.
- **Cost:** the per-turn limits in §7.4, plus a per-tenant daily token budget, set in configuration for v1, with a clear message when it runs out.

---

## 10. Milestones

| # | Scope | Estimate |
|---|---|---|
| M1 | Shared thread and agent Q&A: <ul><li>threads, messages, SSE, comment migration</li><li>`IssueThreadWorkflow` and `run_agent_turn`</li><li>tools: `get_issue_context`, `list_tables`, `describe_table`, `run_query`, `get_investigation`</li><li>markdown, composer, sidebar fixes</li><li>removing the dead investigation chat</li></ul> | About 2 weeks |
| M2 | Handoff and results: <ul><li>brief drafting and editor</li><li>brief-aware manager and prompts</li><li>investigation card and outcome write-back</li><li>confirm/reject and resolution pre-fill</li><li>Continue investigating</li></ul> | About 1.5 weeks |
| M3 | Steering: <ul><li>signal and checkpoint application</li><li>evaluation-loop rewrite</li><li>steers API and UI, `propose_steer`</li><li>Replayer tests</li></ul> | About 1.5 weeks |
| M4 | Scratch chats, publishing, investigate from a scratch chat | About 1 week |
| M5 | Every run in the hub: <ul><li>one starter and `open_issue()` for every path, and `POST /investigations` with a brief</li><li>LLM failures fail the run, plus the key check and banner</li><li>Investigate… from every page, and `/investigations/new` removed</li><li>the issue page matching the mockup</li><li>the run's details page</li></ul> | About 1 week |

`run_query` in M1 needs `UserPrincipal` through `QueryGateway` (checks as code §5.2). If that hasn't landed yet, M1 builds the user path as specified there. Tools from 0002 and 0003 plug in as those specs land.

---

## 11. Testing

- **Unit:**
  - the brief schema
  - steer application as pure functions (state plus steer gives actions)
  - `allowed_transitions`
  - `run_query` validation and caps
  - PII redaction of tool results
  - deterministic prompt assembly: the same inputs give an identical prefix
- **Workflows** (Temporal test environment with time skipping):
  - first-in-first-out turns, idle completion and cancel
  - `rule_out` cancels the right child
  - `add_hypothesis` starts one
  - `stop_and_synthesize` works
  - a late steer re-synthesizes exactly once
  - a steer after completion is rejected
  - Replayer tests on recorded histories for both workflows
- **Agent:** pydantic-ai's `TestModel` and `FunctionModel` script tool calls; bond-agent is built on pydantic-ai. No live model runs in CI.
- **API:**
  - `POLICY` entries exist for every new route
  - a viewer can comment but gets a 403 on `ask_agent`
  - another person's scratch thread returns 404
  - publishing copies snapshots
  - SSE keeps order and resumes correctly with `after`
- **Frontend** (vitest):
  - composer modes
  - streaming render
  - tool-call expansion
  - the status menu shows only allowed moves
  - the brief editor
  - the steer controls
- **End to end,** on the `null_spike` demo fixture: open an issue, ask the agent, hand off with a brief, rule out a hypothesis, get the outcome, confirm, resolve.
- **M5:**
  - `classify_llm_error` for each row of the §7.12 table, through the real exception chain
  - each LLM activity raises `LLMRejected` or `LLMUnavailable` and never returns empty results
  - workflow tests with fake activities:
    - a rejected key fails the run with a failed outcome and a failed Temporal execution
    - one subagent's LLM error cancels the others and fails the run
    - all hypotheses untested from errors fails the run
    - a counter-analysis failure keeps the synthesis
    - Replayer tests still pass on the recorded histories
  - the starter:
    - each path in the §7.11 table writes the run row and the start card, and sets `alert.issue_id`
    - `POST /investigations` without `issue_id` opens exactly one issue
    - a failed workflow start leaves a failed outcome
  - `GET /system/llm` for missing, rejected and valid keys and an unknown model, with the Anthropic client faked
  - frontend:
    - Investigate… on each page opens the editor pre-filled and navigates to the new issue
    - the banner
    - the failed card with Retry
    - the tool-call totals
    - the tabs
    - the details page's back link and export

---

## 12. Open questions

1. **Model cost.** Resolved: chat and brief drafting run on `claude-sonnet-5-5`, like investigations (owner, 2026-09-29), after a stop at `claude-opus-5-5`. Effort stays `low` for chat turns and `medium` for briefs; both settings were checked against the API.
2. **Raw tables in the shared thread.** Should result tables be hidden from viewers who have no credentials for that datasource, showing them only the agent's text?
3. **PII redaction.** Should redacting tool results before they reach the model be on by default?
4. **Steering automated runs.** Can people steer investigations that checks started, or only start follow-ups?
5. **Scratch privacy.** Owner-only as written, or readable by admins?
6. **Slack.** Should agent replies be mirrored to the Slack thread that opened the issue (PR #185)?

---

## 13. Code references

- `python-packages/dataing/src/dataing/entrypoints/api/routes/issues.py`: `STATE_TRANSITIONS`, `validate_state_transition`, `spawn_investigation`, `InvestigationRunCreate`, `stream_issue_events`
- `python-packages/dataing/migrations/018_issues.sql`: `issue_comments`, `issue_events`, `issue_investigation_runs`
- `python-packages/dataing/src/dataing/temporal/workflows/investigation.py`: `InvestigationWorkflow`, `user_input`, `_await_user_input`, `_evaluate_hypotheses_parallel`, `get_status`
- `python-packages/dataing/src/dataing/temporal/workflows/evaluate_hypothesis.py`: `EvaluateHypothesisWorkflow`
- `python-packages/dataing/src/dataing/temporal/activities/execute_query.py` and `python-packages/dataing/src/dataing/safety/validator.py`: the query validation path
- `python-packages/dataing/src/dataing/safety/pii.py`: redaction helpers, unused today
- `python-packages/dataing/src/dataing/adapters/datasource/gateway.py`: `QueryGateway`, unused today
- `python-packages/dataing/src/dataing/entrypoints/temporal_worker.py`: the worker decrypts the datasource's stored connection
- `python-packages/dataing/src/dataing/agents/client.py`: `BondAgent` built without tools
- `frontend/app/src/features/issues/IssueWorkspace.tsx`, `IssueCreate.tsx`, `IssueList.tsx`
- `frontend/app/src/features/investigation/InvestigationDetail.tsx`, `components/index.ts` (`BranchTree`, `MergeIndicator`)
- `python-packages/dataing/tests/unit/entrypoints/api/routes/test_route_authorization.py`: `POLICY`
- M5:
  - `python-packages/dataing/src/dataing/services/investigation.py`: `InvestigationStarterService`
  - `python-packages/dataing/src/dataing/entrypoints/api/routes/investigations.py`: `start_investigation`, `InvestigationStateResponse`
  - `python-packages/dataing/src/dataing/entrypoints/api/routes/integrations.py`: `_start_auto_investigation`
  - `python-packages/dataing-ee/src/dataing_ee/entrypoints/api/routes/integrations.py`: `_evaluate_and_start_investigation`
  - `python-packages/dataing-ee/src/dataing_ee/core/automation/executor.py`: `spawn_investigation`
  - `python-packages/dataing/src/dataing/temporal/activities/`: `generate_hypotheses.py`, `generate_query.py`, `interpret_evidence.py`, `synthesize.py`, `counter_analyze.py`, `publish_outcome.py`
  - `python-packages/dataing/src/dataing/agents/client.py`: `LLMError` wrapping; `interpret_evidence` swallows errors today
  - `frontend/app/src/features/investigation/NewInvestigation.tsx`, `InvestigationDetail.tsx`
  - `frontend/app/src/features/issues/brief/BriefEditor.tsx`, `thread/ToolCalls.tsx`, `thread/InvestigationCard.tsx`, `IssueSidebar.tsx`, `IssueWorkspace.tsx`
  - `0001_issue_chat_mockup.html`: the acceptance reference for §8
- [Checks as code](../plans/2026-09-26-checks-as-code-design.md): §5.2 principals, §7 failure loop, §7.6 codify
