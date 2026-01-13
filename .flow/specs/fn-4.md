# Prompt-as-Environment Investigation Engine

## Overview

Upgrade the investigation engine to handle "infinite" data contexts by implementing the Prompt-as-Environment paradigm. Instead of feeding raw data to the LLM, provide a code execution sandbox and allow the LLM to recursively branch investigations based on programmatic observations.

### Business Value

- **Scalability**: Analyze datasets with 1M+ rows (currently limited by context window)
- **Accuracy**: Reduces hallucination by forcing the model to "prove" findings via code execution
- **Auditability**: Every step of reasoning is backed by executed Python code

## Scope

### In Scope

- Phase 1: Data Sandbox & Registry infrastructure
- Phase 2: Recursive Analysis Step with Code-Observe-Loop
- Phase 3: Programmatic branch triggering and synthesis
- Phase 4: Safety guardrails and audit logging

### Out of Scope

- Frontend trace visualization (follow-up epic)
- Polars support (Pandas only for MVP)
- Multi-language sandbox (Python only)
- Distributed sandbox execution
- Container-level isolation (MVP uses process isolation only)
- Direct file uploads as DataFrame source
- Cross-process SandboxPool coordination (per-process only for MVP)
- Automatic resume on process restart (MVP: manual resume only)

## Architecture

### Key Components

```
┌─────────────────────────────────────────────────────────────┐
│                    InvestigationContext                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ schema_info │  │ lineage_info│  │ data_registry_refs  │  │
│  └─────────────┘  └─────────────┘  │ {"name": DataRef}   │  │
│                                     │  + columns/dtypes   │  │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ branch_id: str (Branch.id UUID for sandbox lookup)      ││
│  │ investigation_mode: InvestigationMode (persisted)       ││
│  │ datasource_id: str (set at investigation start)         ││
│  │ pending_data_request: str | None (cleared after use)    ││
│  │ pending_filter: FilterCondition | None (cleared on use) ││
│  │ code_execution_count: int (for CircuitBreaker)          ││
│  │ data_request_count: int (for CircuitBreaker)            ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                              │
        SandboxManager (passed to handlers via orchestrator methods)
        ├── AdapterFactory (for rehydration)
        └── SandboxPool (per-process, max 4 workers)
            └── workers: dict[branch_id, SandboxWorker]
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│         SandboxWorker (per-branch, cloned on fork)          │
│  - DataRegistry scoped to branch_id (no cross-branch leak) │
│  - Source DFs shared (immutable), ephemeral DFs cloned     │
│  - Derived DFs capped at 10K rows, marked ephemeral        │
│  - Branch filtering happens in-step via boolean masks      │
└─────────────────────────────────────────────────────────────┘
```

### Threat Model (MVP Scope)

**Sandbox provides defense-in-depth, NOT absolute isolation:**

The MVP sandbox is designed to prevent **accidental** misuse and **simple** attacks:
- AST-based import blocking prevents common dangerous imports
- Restricted builtins prevent obvious escape paths
- Resource limits prevent DoS via memory/CPU exhaustion

**Explicitly NOT protected (requires container isolation in future):**
- Determined attacker with Python expertise
- Native library exploits
- Side-channel attacks
- File system access (subprocess can read host files)

**Known Limitations:**
- `signal.alarm()` only interrupts main thread, may not stop C-level loops
- `RLIMIT_AS` applies to whole worker including cached DataFrames
- For guaranteed termination, use per-execution child process (future work)

**Recommendation**: For production with untrusted data, deploy in a container with read-only rootfs, no network, and dropped capabilities. MVP assumes semi-trusted environment.

### Design Decisions

1. **DataFrame Storage & Schema**: DataRef is a Pydantic model with all fields JSON-serializable:
   - `name: str` - unique name within branch
   - `query: str | None` - SQL query (None for derived DFs)
   - `datasource_id: str` - UUID as string (not UUID object)
   - `row_limit: int` - max rows (default 10,000)
   - `validated: bool` - whether query passed validation
   - `ephemeral: bool` - True for derived DFs (not rehydratable)
   - `derived_from: str | None` - parent DataRef name if derived
   - `columns: list[str]` - column names for LLM code generation
   - `dtypes: dict[str, str]` - column name to pandas dtype string
   Columns and dtypes populated on registration (including derived DFs). Query parameters inlined during validation. On rehydration, skip DataRefs where `ephemeral=True`.

2. **SandboxManager (Core Service)**: Create `SandboxManager` class in `dataing/src/dataing/core/investigation/sandbox/manager.py`:
   - Holds `AdapterFactory` for rehydration and `SandboxPool` for workers
   - `workers: dict[str, SandboxWorker]` keyed by `branch_id` (Branch.id UUID)
   - `get_worker(branch_id: str) -> SandboxWorker` - returns existing or creates new
   - `clone_for_branch(parent_branch_id: str, child_branch_id: str) -> SandboxWorker` - clones registry
   - `register_dataframe(branch_id: str, df: DataFrame, name: str, query: str | None, datasource_id: str) -> DataRef` - creates DataFrame in worker, returns DataRef to update context
   - `cleanup(investigation_id: str)` - terminates all workers for investigation
   **Handler Access**: Move signal handlers into orchestrator methods so they access `self.sandbox_manager` directly. Handlers become `_handle_continue()`, `_handle_branch()`, etc. as orchestrator methods.

3. **Branch ID = Branch.id UUID**: Add `branch_id: str` to `InvestigationContext`:
   - Root branch: `branch_id = str(branch.id)` (the UUID from Branch entity)
   - Child branches: `branch_id = str(child_branch.id)` (new Branch entity's UUID)
   - Steps access `context.branch_id` to locate their SandboxWorker via `SandboxManager.get_worker()`
   - `_handle_branch` generates child Branch entity, uses its UUID as `branch_id`
   - No composite keys - always real UUIDs from persisted Branch entities

4. **Adapter Factory (Core Service)**: Create `AdapterFactory` class in `dataing/src/dataing/core/investigation/adapter_factory.py`:
   - `get_adapter(datasource_id: str, tenant_id: str) -> BaseAdapter`
   - Injected into `SandboxManager` at construction
   - Uses `AppDatabase` and encryption key passed at construction
   - Enables rehydration from background/resume paths without request context
   API deps delegates to this factory. Context persistence uses `context.model_dump(mode="json")`.

5. **Datasource ID Persistence**: At investigation start:
   - API route passes explicit `datasource_id` to `start_investigation()`
   - If not provided, use tenant's default datasource and fetch its ID
   - Store `datasource_id` in `InvestigationContext` at creation
   - Propagate to child branches in `_handle_branch`

6. **Branch-Scoped DataRegistry with Shared Source DFs**: Each branch gets its own `DataRegistry` instance:
   - On investigation start: create root DataRegistry, store in `SandboxManager.workers[root_branch_id]`
   - On branch creation: `SandboxManager.clone_for_branch()`:
     - **Source (non-ephemeral) DataFrames**: Share reference (immutable, same object across branches)
     - **Ephemeral DataFrames**: Clone (deep copy) to prevent cross-branch mutation
   - Source DataFrames stored as read-only (via `df.flags.writeable = False`)
   - Code receives `.copy()` of source DFs to prevent mutation
   - **Fresh exec globals per execution** - reset namespace between runs

7. **Derived DataFrame Limits**: On derived DF registration:
   - Enforce max rows: `df = df.head(10000)` if exceeds limit
   - Log warning if truncation occurred
   - Mark with `ephemeral=True, derived_from="source_name"`
   - Include `columns` and `dtypes` extracted from DataFrame

8. **Sandbox Pool (MVP)**: Use **SandboxPool** with max 4 concurrent workers **per process** (not globally coordinated). Each SandboxWorker:
   - Long-lived subprocess per branch (avoids serialization overhead)
   - Executes code in restricted namespace with timeout via `signal.alarm(5)`
   - Memory limit via `resource.setrlimit(RLIMIT_AS, 256MB)` applied to worker process
   - **Known limitation**: alarm may not interrupt C extensions
   - **Not a security boundary** - defense-in-depth only.

9. **StepResult.metadata for Completion Signal**: Add `metadata: dict[str, Any] | None = None` to `StepResult` in `protocol.py`:
   - Steps can pass arbitrary metadata through the result
   - `RecursiveAnalysisStep` sets `metadata={"analysis_complete": True}` when done
   - Routing checks `step_result.metadata.get("analysis_complete")` to decide SYNTHESIZE transition

10. **Step Pipeline Integration with Routing Override**: New `InvestigationMode.CODE_ANALYSIS` persisted in context. Move handlers into orchestrator methods:
    - Add `_route_next_step(context, step_result, current_step: StepType) -> StepType | None` as orchestrator method
    - `_handle_continue` calls `_route_next_step()` with current step type
    - Routing logic:
      - If `context.investigation_mode == CODE_ANALYSIS`:
        - **Override** `step_result.next_step` for mode-gated steps
        - After `GATHER_CONTEXT`: force `GENERATE_HYPOTHESES`
        - After `GENERATE_HYPOTHESES`: force `RECURSIVE_ANALYZE` (not `CHECK_PATTERNS`)
        - After `REQUEST_DATA`: force `RECURSIVE_ANALYZE`
        - After `RECURSIVE_ANALYZE`: check `step_result.metadata.get("analysis_complete")`:
          - If True: force `SYNTHESIZE`
          - Else: continue loop (return `RECURSIVE_ANALYZE`)
      - Else use `step_result.next_step` if not None
      - Else use traditional mode routing
    - **No changes to existing steps** - routing handled entirely in `_route_next_step`
    - **RecursiveAnalysisStep always returns `signal=CONTINUE`**, sets `metadata["analysis_complete"]=True` when done

11. **Branch Start Step Override**: `_handle_branch` (orchestrator method):
    - If mode is `CODE_ANALYSIS`: force `child_start_step = StepType.RECURSIVE_ANALYZE`
    - If mode is `TRADITIONAL`: use existing default (`GENERATE_QUERY`)
    - Create child Branch entity, use `str(child_branch.id)` as `branch_id`
    - Propagate `investigation_mode`, `datasource_id`, and `branch_id` to child context
    - Clone parent's DataRegistry via `self.sandbox_manager.clone_for_branch(parent_branch_id, child_branch_id)`
    - **Clear `pending_filter` in parent context** after passing to child

12. **Data Access via Context Field with Lifecycle**: Use context field for data requests:
    - Add `pending_data_request: str | None` to `InvestigationContext`
    - `RecursiveAnalysisStep` sets `pending_data_request = query` and returns `signal=CONTINUE, next_step=REQUEST_DATA`
    - `RequestDataStep.execute()`:
      - Check `pending_data_request is not None` - if None, log warning and return CONTINUE
      - Read and **immediately clear** `pending_data_request` (set to None in updated context)
      - Validate via `validate_query()` (unchanged), then clamp via new `clamp_query_limit(sql, max_limit=10000) -> str`
      - Execute via `DatabaseAdapter.execute_query()` to get DataFrame
      - Call `sandbox_manager.register_dataframe(branch_id, df, name, query, datasource_id)` to register and get DataRef
      - Update `context.data_registry_refs[name] = data_ref`
      - Increment `data_request_count` in context
    - Returns `StepResult` with updated context
    - On retry: cleared field prevents re-execution

13. **Query Limit Enforcement**: Add new helper in `safety/validator.py`:
    - `clamp_query_limit(sql: str, max_limit: int = 10000) -> str` - rewrites SQL to enforce limit
    - Clamp existing LIMIT to `min(existing, max_limit)`
    - Add LIMIT if missing with `max_limit` value
    - Keep `validate_query()` pure (no breaking changes)
    - `RequestDataStep` calls `clamp_query_limit()` after `validate_query()`

14. **FilterCondition with Target Ref**: `FilterCondition` specifies which DataFrame to filter:
    - `target_ref: str` - name of DataRef in `data_registry_refs` to filter
    - `column: str` - validated against target DataFrame schema
    - `operator: Literal["eq", "ne", "gt", "lt", "gte", "lte", "in", "notin", "isnull", "notnull"]`
    - `value: str | int | float | bool | list[str | int | float] | None`
    - Validate `target_ref` exists in `data_registry_refs` before branching
    - Execution builds boolean mask directly: `df[col] == value`, etc.

15. **Branch Filtering with Lifecycle**: `FilterCondition` applied within `RecursiveAnalysisStep`:
    - `_handle_branch` passes filter to child context via `pending_filter: FilterCondition | None`
    - **Parent context has `pending_filter` cleared** when creating child
    - Child's `RecursiveAnalysisStep` on first iteration:
      - Check `pending_filter is not None`
      - Read `target_ref` and **immediately clear** `pending_filter` (set to None in updated context)
      - Get source DataFrame from `sandbox_manager.get_worker(branch_id).registry.get(target_ref)`
      - Apply filter via boolean mask in sandbox
      - Register filtered result as new ephemeral DataRef with name `f"{target_ref}_filtered"`
    - On retry: cleared field prevents re-application

16. **Evidence Model Integration**: Define `CodeEvidence` dataclass with `code: str`, `stdout: str`, `return_value: str`, `truncated: bool`, `error: str | None`. Update:
    - `domain_types.py`: `EvidenceType = Evidence | CodeEvidence`
    - `agents/prompts/synthesis.py`: Update `_format_evidence()` to render CodeEvidence as fenced code block
    - `agents/client.py`: Update `synthesize_findings_raw()` to accept `list[EvidenceType]`
    - Add integration test with mixed Evidence + CodeEvidence

17. **Context Field Preservation**: All step implementations use `context.model_copy(update={...})` pattern. Add `_preserve_registry_fields(old_ctx, new_updates) -> dict` helper that ensures `branch_id`, `data_registry_refs`, `investigation_mode`, `datasource_id`, `pending_data_request`, `pending_filter`, `code_execution_count`, and `data_request_count` are included in updates.

18. **CircuitBreaker via Context Counters**: Instead of event history, use context counters:
    - Add `code_execution_count: int = 0` and `data_request_count: int = 0` to InvestigationContext
    - `RecursiveAnalysisStep`: Before each sandbox call, check `code_execution_count < max_code_executions` (50)
    - Increment counter in context after successful execution
    - Emit `CODE_EXECUTED`/`CODE_FAILED` events for observability (not enforcement)
    - `RequestDataStep`: Increment `data_request_count`, emit `DATA_REQUESTED` event
    - Add `CODE_EXECUTED`, `CODE_FAILED`, `DATA_REQUESTED` to `EventType` enum in state.py
    - Trace storage in `adapters/audit/trace.py` keyed by investigation_id

19. **Resume Service Method**: Add `resume_investigation(investigation_id: str, tenant_id: str)` to `InvestigationService`:
    - Load snapshot from repository
    - **Prune ephemeral DataRefs** from `data_registry_refs` (skip those with `ephemeral=True`)
    - Rehydrate non-ephemeral DataRefs via `sandbox_manager.register_dataframe()` using stored queries
    - Rebuild `SandboxWorker` for each active branch via `SandboxManager`
    - Restart orchestrator from snapshot's step
    - Returns investigation ID for tracking

## Approach

### Phase 1: Data Sandbox & Registry Foundation

**Key Files:**
- `dataing/src/dataing/core/investigation/sandbox/__init__.py` (new)
- `dataing/src/dataing/core/investigation/sandbox/registry.py` (DataRegistry with branch-scoped cloning, DataRef with name/columns/dtypes/ephemeral)
- `dataing/src/dataing/core/investigation/sandbox/pool.py` (SandboxPool, per-process max workers)
- `dataing/src/dataing/core/investigation/sandbox/worker.py` (SandboxWorker, copy-on-access, fresh globals, derived DF limits)
- `dataing/src/dataing/core/investigation/sandbox/manager.py` (SandboxManager with register_dataframe, clone_for_branch)
- `dataing/src/dataing/core/investigation/sandbox/types.py` (ExecutionResult)
- `dataing/src/dataing/core/investigation/adapter_factory.py` (new, AdapterFactory for rehydration)
- `dataing/src/dataing/core/investigation/entities.py` (add branch_id, data_registry_refs, investigation_mode, datasource_id, pending_data_request, pending_filter, code_execution_count, data_request_count)
- `dataing/src/dataing/core/domain_types.py` (add DataRef, FilterCondition with target_ref, CodeEvidence)
- `dataing/src/dataing/core/investigation/steps/protocol.py` (add metadata: dict | None to StepResult)
- `dataing/src/dataing/safety/code_validator.py` (new, AST blocking)
- `dataing/src/dataing/safety/validator.py` (add clamp_query_limit helper, keep validate_query pure)
- `dataing/pyproject.toml` (add pandas>=2.0.0, RestrictedPython>=7.0)
- `dataing/src/dataing/adapters/db/investigation_repository.py` (use model_dump(mode="json"))

### Phase 2: Recursive Analysis Step

**Key Files:**
- `dataing/src/dataing/core/investigation/steps/recursive_analyze.py` (new step with counter checks, analysis_complete metadata)
- `dataing/src/dataing/core/investigation/steps/request_data.py` (new step, reads/clears pending_data_request, calls register_dataframe)
- `dataing/src/dataing/core/investigation/values.py` (StepType.RECURSIVE_ANALYZE, StepType.REQUEST_DATA, InvestigationMode)
- `dataing/src/dataing/core/investigation/orchestrator/base.py` (inject SandboxManager, move handlers to orchestrator methods)
- `dataing/src/dataing/adapters/investigation/llm_adapter.py` (RecursiveAnalysisLLMAdapter)
- `dataing/src/dataing/adapters/investigation/step_factory.py` (register new steps)
- `dataing/src/dataing/agents/prompts/synthesis.py` (update _format_evidence for CodeEvidence)
- `dataing/src/dataing/agents/client.py` (update synthesize_findings_raw signature)

### Phase 3: Recursive Branching

**Key Files:**
- `dataing/src/dataing/core/investigation/steps/protocol.py` (filter_condition: FilterCondition | None in BranchRequest)
- `dataing/src/dataing/core/investigation/orchestrator/base.py` (_handle_branch method: mode override + datasource_id + child branch_id + pending_filter + registry clone + clear parent pending_filter)
- `dataing/src/dataing/core/investigation/orchestrator/merge.py` (hierarchical synthesis)

### Phase 4: Safety & Observability

**Key Files:**
- `dataing/src/dataing/safety/code_validator.py` (AST blocking, restricted builtins)
- `dataing/src/dataing/safety/circuit_breaker.py` (update to use context counters for code analysis mode)
- `dataing/src/dataing/core/state.py` (CODE_EXECUTED, CODE_FAILED, DATA_REQUESTED events)
- `dataing/src/dataing/adapters/audit/trace.py` (CE in-memory trace storage)
- `dataing/src/dataing/core/investigation/service.py` (add resume_investigation method with ephemeral pruning)

## Quick Commands

```bash
# Run sandbox unit tests
cd dataing && uv run pytest tests/unit/core/investigation/sandbox/ -v

# Run full investigation tests
cd dataing && uv run pytest tests/unit/core/investigation/ -v

# Type check new modules
cd dataing && uv run mypy src/dataing/core/investigation/sandbox/ --strict

# Smoke test
cd dataing && uv run python -c "
from dataing.core.investigation.sandbox import DataRegistry, SandboxWorker
import pandas as pd
registry = DataRegistry(branch_id='test-uuid')
registry.register(pd.DataFrame({'a': [1,2,3]}), 'test_df')
with SandboxWorker(registry) as sandbox:
    result = sandbox.execute('print(test_df.describe())')
    print(result)
"
```

## Technical DoD

- [ ] No raw data in prompt (LLM sees references only)
- [ ] Code-first: LLM executes code before answering data questions
- [ ] Syntax errors trigger retry (up to 3)
- [ ] Safety tests: blocked imports raise errors
- [ ] Audit trail: code executions logged via events
- [ ] DataRef includes name, columns and dtypes for code generation
- [ ] investigation_mode persists across snapshots and branches
- [ ] SandboxPool limits concurrent workers to 4 per process
- [ ] Source DataFrames are immutable (copy-on-access), shared across branches
- [ ] Derived DataFrames capped at 10K rows, marked ephemeral, cloned on fork
- [ ] Query limits enforced via clamp_query_limit helper
- [ ] Branch-scoped DataRegistry (via real Branch.id UUIDs) prevents cross-branch leakage
- [ ] Context counters enforce CircuitBreaker limits
- [ ] pending_data_request/pending_filter cleared after use
- [ ] Resume service method prunes ephemeral refs and rehydrates
- [ ] FilterCondition specifies target_ref for unambiguous filtering
- [ ] StepResult.metadata enables completion signaling

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Sandbox escape | Critical | Defense-in-depth (AST + builtins + limits); container isolation for prod |
| Memory exhaustion | High | resource.setrlimit (256MB), query limit clamping (10K rows), derived DF cap, SandboxPool cap |
| Infinite loops | High | 5s timeout; limitation: may not stop C extensions |
| Branch explosion | Medium | Max 3 depth in CircuitBreaker |
| Invalid code | Medium | 3-retry reflexion |
| Worker process leak | Medium | SandboxPool tracks workers, cleanup on investigation complete |
| State leakage between executions | Medium | Fresh exec globals per execution |
| Cross-branch data leak | Medium | Branch-scoped registry with real UUID keys, source DFs shared immutably |
| Derived DF loss on restart | Low | Marked ephemeral; resume prunes and restarts from checkpoint |

## Platform Constraints

- **Production**: Linux (forkserver, setrlimit). Container recommended.
- **Development**: macOS works with spawn (slower)
- **Python**: 3.11+

## References

- Orchestrator: `dataing/src/dataing/core/investigation/orchestrator/base.py`
- Step Protocol: `dataing/src/dataing/core/investigation/steps/protocol.py`
- GatherContextStep: `dataing/src/dataing/core/investigation/steps/gather_context.py`
- SynthesizeStep: `dataing/src/dataing/core/investigation/steps/synthesize.py`
- BranchRequest: `dataing/src/dataing/core/investigation/steps/protocol.py`
- CircuitBreaker: `dataing/src/dataing/safety/circuit_breaker.py`
- QueryValidator: `dataing/src/dataing/safety/validator.py`
- InvestigationContext: `dataing/src/dataing/core/investigation/entities.py`
- Evidence: `dataing/src/dataing/core/domain_types.py`
- State: `dataing/src/dataing/core/state.py`
- StepFactory: `dataing/src/dataing/adapters/investigation/step_factory.py`
- InvestigationRepository: `dataing/src/dataing/adapters/db/investigation_repository.py`
- AgentClient: `dataing/src/dataing/agents/client.py`
- SynthesisPrompts: `dataing/src/dataing/agents/prompts/synthesis.py`
- DatabaseAdapter: `dataing/src/dataing/adapters/investigation/database_adapter.py`
- API Dependencies: `dataing/src/dataing/entrypoints/api/deps.py`
- InvestigationService: `dataing/src/dataing/core/investigation/service.py`
