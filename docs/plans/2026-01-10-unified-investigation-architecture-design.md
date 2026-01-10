# DataDr Unified Investigation Architecture

## Overview

This document describes the unified architecture for Dataing's investigation system. The core insight: an investigation is not a linear process—it's a **tree of states** that can branch (hypothesis testing, user refinements), merge (synthesizing multiple paths), and fork (collaborative branching).

## 1. Core Data Model

### Current → New

**Current model:**
```
Investigation → Events[] → derived state
```

**New model:**
```
Investigation → Branches[] → Snapshots[] → InvestigationContext
```

### Key Entities

| Entity | Purpose |
|--------|---------|
| `Investigation` | Root aggregate. Contains alert, tracks main branch, stores final outcome |
| `Branch` | A line of exploration. Types: `main`, `hypothesis`, `user`, `counter`, `pattern` |
| `Snapshot` | Immutable point-in-time state. Contains full context, current step, version |
| `InvestigationContext` | The "brain" — accumulated knowledge (schema, hypotheses, evidence, synthesis) |

### Why Snapshots Instead of Events

- Events require replaying entire history to get current state
- Snapshots give O(1) access to any point in time
- Enables true branching — each branch has its own snapshot chain
- Simplifies crash recovery — just load latest snapshot

### Version Semantics

Format: `major.minor.patch`
- Major: synthesis iterations (v1.0.0 → v2.0.0 = re-synthesized)
- Minor: new evidence added
- Patch: refinements/corrections

### Visual: Investigation as Tree

```
                         Initial Alert
                              │
                              ▼
                        ┌───────────┐
                        │  v1.0.0   │  Initial investigation
                        └─────┬─────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
        ┌───────────┐   ┌───────────┐   ┌───────────┐
        │ v1.0.1    │   │ v1.0.2    │   │ v1.0.3    │  Hypotheses tested
        │ (h1)      │   │ (h2)      │   │ (h3)      │  (parallel branches)
        └─────┬─────┘   └─────┬─────┘   └─────┬─────┘
              │               │               │
              └───────────────┼───────────────┘
                              ▼
                        ┌───────────┐
                        │  v1.1.0   │  Synthesis (merge)
                        └─────┬─────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
        ┌───────────┐                   ┌───────────┐
        │ v1.1.1    │                   │ v1.1.1    │  User branches
        │ (alice)   │                   │ (bob)     │  (collaborative)
        └───────────┘                   └───────────┘
```

## 2. Step Abstraction

Steps are pure functions that transform context. The orchestrator handles persistence, locking, and flow control.

### Step Signature

```python
async def execute(context: InvestigationContext, input: T | None) -> StepResult[O]
```

### StepResult

```python
@dataclass(frozen=True)
class StepResult(Generic[OutputT]):
    context: InvestigationContext      # Updated context
    signal: ExecutionSignal            # What to do next
    output: OutputT | None = None      # Step-specific output
    next_step: StepType | None = None  # Explicit next step (if signal=CONTINUE)
    branch_request: BranchRequest | None = None  # If signal=BRANCH
```

### Execution Signals

| Signal | Meaning |
|--------|---------|
| `CONTINUE` | Proceed to next step |
| `BRANCH` | Fork execution into child branches |
| `MERGE` | Join child branches back |
| `AWAIT_USER` | Suspend, wait for user input |
| `REQUIRE_APPROVAL` | Suspend, wait for human approval |
| `COMPLETE` | Terminal success state |
| `FAIL` | Terminal failure state |

### Step Types

| Step | Input | Output | Typical Signal |
|------|-------|--------|----------------|
| `GatherContext` | — | ContextBundle | CONTINUE |
| `CheckPatterns` | — | PatternMatch[] | CONTINUE |
| `GenerateHypotheses` | — | Hypothesis[] | BRANCH (one per hypothesis) |
| `GenerateQuery` | Hypothesis | SQL string | CONTINUE |
| `ExecuteQuery` | QueryRequest | QueryResult | CONTINUE or REQUIRE_APPROVAL |
| `InterpretEvidence` | QueryResult | Evidence | CONTINUE |
| `Synthesize` | Evidence[] | SynthesisResponse | CONTINUE or COMPLETE |
| `CounterAnalyze` | Synthesis | CounterAnalysis | CONTINUE |
| `ClassifyIntent` | user message | RefinementIntent | CONTINUE |
| `ExecuteRefinement` | Intent | varies | CONTINUE |

### Key Principle

Steps don't know about databases, locks, or other steps. They receive context, do one thing, return result. The orchestrator interprets signals and manages state transitions.

## 3. Orchestrator & Durable Execution

The orchestrator is a tick-based loop that processes one step at a time, persisting state between steps.

### Tick Loop

```
1. Acquire lock on branch (with TTL)
2. Load current snapshot
3. Get pending input (approval result, user message)
4. Execute the step
5. Handle the signal:
   - CONTINUE → create snapshot, update head, tick again
   - BRANCH → create child branches, start them
   - AWAIT_USER → suspend branch, wait
   - REQUIRE_APPROVAL → suspend, create approval request
   - COMPLETE → finalize branch
   - FAIL → mark abandoned
6. Release lock
```

### Crash Recovery

If a worker dies mid-step, the lock expires (TTL). Another worker picks up from the last persisted snapshot. No work is lost because snapshots are immutable.

### Branching Behavior

1. `GenerateHypotheses` returns BRANCH signal with N hypothesis specs
2. Orchestrator creates N child branches, each starting at `GenerateQuery`
3. Child branches run in parallel (can be same worker or distributed)
4. Parent branch waits at a "merge point"
5. When all children complete, parent resumes at `Synthesize` with collected evidence

## 4. Collaboration & User Branches

When a user wants to explore a different direction, they get their own branch forked from main.

### Flow

1. User sends a message to an investigation
2. System checks if user already has a branch
3. If not, fork from main branch's current snapshot
4. Route message to user's branch
5. Branch processes via `ClassifyIntent` → appropriate step

### Intent Classification Routes

| Intent | Action |
|--------|--------|
| `modify_query` | Re-run with different SQL |
| `new_hypothesis` | Generate additional hypotheses |
| `clarify` | Answer question from context |
| `revise_synthesis` | Re-synthesize with new direction |
| `drill_down` | Investigate specific aspect deeper |
| `acknowledge` | Mark complete |

### Independence

- Alice's exploration doesn't affect Bob's
- Main branch is source of truth
- Users can optionally "merge" findings back (creates review request)

### Frontend Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Investigation Page                                                          │
│                                                                              │
│  ┌─────────────────────────────────┐  ┌──────────────────────────────────┐  │
│  │  Main Findings Panel            │  │  Your Exploration (Branch)       │  │
│  │                                 │  │                                  │  │
│  │  Shows: main branch synthesis   │  │  Shows: your branch state        │  │
│  │                                 │  │                                  │  │
│  │  Root Cause: ...                │  │  Chat interface for refinement   │  │
│  │  Confidence: 87%                │  │                                  │  │
│  │  Recommendations: ...           │  │  [Merge to Main] [Reset Branch]  │  │
│  └─────────────────────────────────┘  └──────────────────────────────────┘  │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  Branch Comparison (optional)                                           ││
│  │  Main Branch          Your Branch           Alice's Branch              ││
│  │  Cause: ETL timeout   Cause: API rate limit Cause: ETL timeout         ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

## 5. Pattern Learning & Root Cause Memory

The system learns from resolved investigations to speed up future ones.

### Pattern Matching Flow

1. After gathering context, `CheckPatterns` step runs
2. Queries `root_cause_patterns` table for matches based on:
   - Dataset/metric affected
   - Anomaly type and characteristics
   - Time patterns (e.g., "always happens during batch window")
3. High-confidence matches (>0.8) get injected as hints to hypothesis generation
4. LLM can confirm/reject the pattern hypothesis quickly

### Pattern Creation

- When investigation completes with high confidence + positive user feedback
- System extracts pattern: trigger signals, root cause, resolution steps
- Stored per-organization (tenant isolation)

### Training Signals

Every step transition captures input/output pairs with quality scores for future RL fine-tuning (uses existing `rl_training_signals` table).

## 6. Database Schema

### Core Tables

```sql
-- Root aggregate
CREATE TABLE investigations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    alert JSONB NOT NULL,
    main_branch_id UUID,  -- set after first branch created
    outcome JSONB,        -- final finding when complete
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES users(id)
);

-- Lines of exploration
CREATE TABLE investigation_branches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id UUID NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
    branch_type TEXT NOT NULL CHECK (branch_type IN ('main', 'hypothesis', 'user', 'counter', 'pattern')),
    name TEXT NOT NULL,
    parent_branch_id UUID REFERENCES investigation_branches(id),
    forked_from_snapshot_id UUID,
    owner_user_id UUID REFERENCES users(id),  -- for user branches
    head_snapshot_id UUID,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'merged', 'abandoned', 'completed')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Immutable state records
CREATE TABLE investigation_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id UUID NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
    branch_id UUID NOT NULL REFERENCES investigation_branches(id) ON DELETE CASCADE,
    version_major INT NOT NULL DEFAULT 0,
    version_minor INT NOT NULL DEFAULT 0,
    version_patch INT NOT NULL DEFAULT 0,
    parent_snapshot_id UUID REFERENCES investigation_snapshots(id),
    step TEXT NOT NULL,
    step_cursor JSONB DEFAULT '{}',
    context JSONB NOT NULL,  -- the full "brain"
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    trigger TEXT NOT NULL DEFAULT 'system'
);

-- Execution locks for durable processing
CREATE TABLE execution_locks (
    branch_id UUID PRIMARY KEY REFERENCES investigation_branches(id) ON DELETE CASCADE,
    locked_by TEXT NOT NULL,      -- worker instance ID
    locked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Chat messages linked to branches
CREATE TABLE branch_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    branch_id UUID NOT NULL REFERENCES investigation_branches(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    resulting_snapshot_id UUID REFERENCES investigation_snapshots(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Approval requests
CREATE TABLE approval_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    branch_id UUID NOT NULL REFERENCES investigation_branches(id) ON DELETE CASCADE,
    snapshot_id UUID NOT NULL REFERENCES investigation_snapshots(id),
    action_type TEXT NOT NULL,
    action_payload JSONB NOT NULL,
    risk_reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'expired')),
    decided_by UUID REFERENCES users(id),
    decided_at TIMESTAMPTZ,
    decision TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Known root cause patterns
CREATE TABLE root_cause_patterns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organizations(id),
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    trigger_signals JSONB NOT NULL,
    typical_root_cause TEXT NOT NULL,
    resolution_steps JSONB NOT NULL,
    affected_datasets JSONB DEFAULT '[]',
    affected_metrics JSONB DEFAULT '[]',
    time_patterns JSONB,
    occurrence_count INT DEFAULT 0,
    last_matched_at TIMESTAMPTZ,
    false_positive_count INT DEFAULT 0,
    avg_resolution_time_minutes INT,
    status TEXT DEFAULT 'active',
    created_from_investigation_id UUID REFERENCES investigations(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Merge point tracking
CREATE TABLE branch_merge_points (
    parent_branch_id UUID NOT NULL REFERENCES investigation_branches(id) ON DELETE CASCADE,
    child_branch_id UUID NOT NULL REFERENCES investigation_branches(id) ON DELETE CASCADE,
    merge_step TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (parent_branch_id, child_branch_id)
);
```

### Indexes

```sql
CREATE INDEX idx_snapshots_branch_head ON investigation_snapshots(branch_id, created_at DESC);
CREATE INDEX idx_snapshots_investigation ON investigation_snapshots(investigation_id, created_at DESC);
CREATE INDEX idx_branches_investigation ON investigation_branches(investigation_id);
CREATE INDEX idx_branches_owner ON investigation_branches(owner_user_id) WHERE owner_user_id IS NOT NULL;
CREATE INDEX idx_messages_branch ON branch_messages(branch_id, created_at);
CREATE INDEX idx_patterns_org ON root_cause_patterns(organization_id) WHERE status = 'active';
```

## 7. API Layer

### Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/investigations/{id}` | Get investigation with user's branch state |
| `POST` | `/investigations/{id}/chat` | Send message to user's branch |
| `GET` | `/investigations/{id}/stream` | SSE stream for real-time updates |
| `GET` | `/investigations/{id}/branches` | List all branches (for comparison view) |
| `POST` | `/investigations/{id}/branches/{branch_id}/merge` | Request merge to main |
| `POST` | `/approvals/{id}/decide` | Approve/reject pending action |

### SSE Events

- `step_started` — which step is running
- `step_completed` — step finished with output preview
- `snapshot_created` — new state version
- `synthesis_updated` — findings changed
- `approval_required` — needs human decision
- `branch_completed` — terminal state reached

## 8. Implementation Phases

### Phase 1: Foundation
- Database migration for new tables (investigations, branches, snapshots)
- Domain models (`Investigation`, `Branch`, `Snapshot`, `InvestigationContext`)
- Repository layer for CRUD operations
- Remove old `InvestigationState` class

### Phase 2: Step Abstraction
- `Step` protocol and `StepResult` dataclass
- Core steps: `GatherContext`, `GenerateHypotheses`, `GenerateQuery`, `ExecuteQuery`, `InterpretEvidence`, `Synthesize`
- `StepRegistry` for step lookup by type
- Migrate LLM calls from old orchestrator to new steps

### Phase 3: Orchestrator
- Execution lock table and acquisition logic
- `Orchestrator.tick()` loop with CONTINUE/COMPLETE signals
- Snapshot persistence after each step
- Basic crash recovery (lock expiry, resume from snapshot)

### Phase 4: Branching
- BRANCH signal handling in orchestrator
- Hypothesis branch creation and parallel execution
- Merge point tracking
- Evidence collection from child branches

### Phase 5: Collaboration
- User branch creation (fork from main)
- `CollaborationService` for branch management
- `ClassifyIntent` and `ExecuteRefinement` steps
- AWAIT_USER signal handling

### Phase 6: Quality & Patterns
- `CounterAnalyze` step
- `CheckPatterns` step
- `root_cause_patterns` table and matching logic
- Pattern extraction from completed investigations

### Phase 7: API & Frontend
- Branch-aware API endpoints
- SSE streaming for real-time updates
- Frontend: split panel (main findings + user exploration)
- Branch comparison view

## 9. Key Design Principles

1. **Snapshots are immutable** — Never update a snapshot; create a new one. Enables undo, audit, branching.

2. **Steps are pure functions** — `(Context, Input) → (Context, Signal, Output)`. No side effects except through orchestrator.

3. **Branches are first-class** — Not a special case bolted on. Every investigation is a tree of branches from day one.

4. **Signals control flow** — Steps don't call other steps. They return signals that the orchestrator interprets.

5. **User branches are independent** — Alice's exploration doesn't affect Bob's. Main branch is the source of truth until someone merges.

6. **Everything persists** — Crash at any point, resume from last snapshot. No in-memory state that isn't checkpointed.

## 10. Migration Notes

This is a full replacement of the existing orchestrator. Since we are pre-launch:
- No backwards compatibility required
- Existing `InvestigationState` and event-sourced model will be removed
- Old orchestrator (`orchestrator.py`) will be replaced entirely
- Existing tests will need to be rewritten for new architecture
