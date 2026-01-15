# Future Work: Robust Job State Machine & Concurrency Controls

**Type**: Technical Debt / Architecture
**Priority**: Medium (Post-Launch)
**Context**: "Hyper-scale" Robustness

## Background
Currently, we handle race conditions in job status updates (specifically preventing workers from overwriting a user's cancellation request) using conditional SQL updates (e.g., `CASE WHEN status = 'cancelling'...`). While effective for the current scale, this logic relies on the application layer correctly forming query constraints and does not strictly enforce invalid state transitions at the database level.

For a hyper-scale environment (Google/Apple scale) with high concurrency and multiple writer services, we should implement stricter database-level guarantees.

## Proposed Solutions

### 1. Database-Level State Machine Validation
Strictly enforce allowed state transitions to prevent illegal states (e.g., a job moving from `cancelling` back to `running`).

*   **Mechanism**: Database Triggers or `CHECK` constraints.
*   **Implementation**:
    *   Define a rigid transition matrix (e.g., `pending` -> `running` -> `completed` | `failed`).
    *   Create a Postgres trigger function `check_job_state_transition()` that runs `BEFORE UPDATE`.
    *   Raise an exception if `OLD.status` -> `NEW.status` is not a valid edge in the transition graph.
    *   *Specific invariant*: Once `status` is `cancelling` or `cancelled`, it cannot revert to `running`.

### 2. Optimistic Locking
Ensure no other process has modified the job row between read and write operations, preventing "lost updates" without relying on complex `CASE` logic.

*   **Mechanism**: Version column.
*   **Implementation**:
    *   Add `version` (integer) column to `investigation_jobs` table (default 1).
    *   Update queries must include the version check:
        ```sql
        UPDATE investigation_jobs
        SET status = $new_status, ..., version = version + 1
        WHERE id = $job_id AND version = $read_version
        ```
    *   If `UPDATE` returns 0 rows, the row was modified by another actor (e.g., user cancelled it).
    *   Application catches this case and re-fetches/retries or aborts based on the new state.

## Benefits
*   **Strict Consistency**: Impossible to put the database into an invalid state, regardless of application bugs.
*   **Traceability**: Clear errors when race conditions occur, rather than silent overwrites or conditional logic masking the conflict.
*   **Scalability**: Safe for multiple concurrent workers and API instances.
