# fn-5.9 Remove Legacy Orchestrator

## Description
Remove the legacy orchestrator now that maestro.Workflow handles execution.

## Implementation

1. Verify all functionality moved to maestro:
   - tick() loop → maestro.Workflow.run()
   - signal handlers → InvestigationSignalHandler
   - merge logic → InvestigationMergeStrategy

2. Delete legacy orchestrator files:
   - `dataing/src/dataing/core/investigation/orchestrator/base.py`
   - `dataing/src/dataing/core/investigation/orchestrator/types.py`
   - `dataing/src/dataing/core/investigation/orchestrator/__init__.py`

3. Keep signal_handlers.py if it has domain-specific logic used by InvestigationSignalHandler.

4. Update imports across codebase to use maestro.

5. Delete legacy protocol.py from steps if not already done.

## Key Files
- Delete: `dataing/src/dataing/core/investigation/orchestrator/base.py`
- Delete: `dataing/src/dataing/core/investigation/orchestrator/types.py`
- Delete: `dataing/src/dataing/core/investigation/orchestrator/protocol.py` (if exists)
- Modify: Imports across codebase
## Acceptance
- [ ] `dataing/core/investigation/orchestrator/` folder deleted or emptied
- [ ] No imports of legacy orchestrator in codebase
- [ ] All tests pass using maestro.Workflow
- [ ] Feature flag can be removed (v2 is now the only path)
- [ ] No dead code left behind
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
