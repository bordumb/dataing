# fn-4.6 Hierarchical branch synthesis in SynthesizeStep

## Description


Update `SynthesizeStep` to handle hierarchical results from recursive branches, producing a coherent summary that includes child branch findings.

### Current Behavior

`SynthesizeStep` at `core/investigation/steps/synthesize.py:45-130`:
- Merges `context.evidence` list from all steps
- Calls LLM to generate summary
- Returns final finding

### New Behavior

When parent has spawned child branches:
1. Collect `StepResult` findings from all child branches
2. Build hierarchical summary showing branch tree
3. LLM synthesizes parent + child findings into unified conclusion

### Changes to Merge Logic

Modify `backend/src/dataing/core/investigation/orchestrator/merge.py`:

```python
def collect_branch_results(
    parent_snapshot: InvestigationSnapshot,
    repository: InvestigationRepository,
) -> list[BranchResult]:
    """Collect results from all child branches."""
    results = []
    for child_id in parent_snapshot.child_investigation_ids:
        child = repository.get(child_id)
        results.append(BranchResult(
            branch_name=child.branch_name,
            filter_condition=child.filter_condition,
            findings=child.context.findings,
            evidence_count=len(child.context.evidence),
        ))
    return results
```

### Synthesis Prompt Update

```
## Child Branch Findings

The investigation spawned {N} child branches:

### Branch: US-EAST-1 (filter: region == 'us-east-1')
Finding: Error rate spike of 47% due to misconfigured load balancer

### Branch: EU-WEST-1 (filter: region == 'eu-west-1')
Finding: Normal error rates within baseline

---

Synthesize these findings into a unified root cause analysis.
```

### Files to Modify

- `backend/src/dataing/core/investigation/orchestrator/merge.py` - Collect branch results
- `backend/src/dataing/core/investigation/steps/synthesize.py` - Handle hierarchical input
- `backend/src/dataing/adapters/investigation/llm_adapter.py` - Update SynthesisLLMAdapter prompt
- `backend/tests/unit/core/investigation/steps/test_synthesize.py` - Test hierarchical synthesis

### References

- Merge: `core/investigation/orchestrator/merge.py:15-75`
- SynthesizeStep: `core/investigation/steps/synthesize.py:45-130`
## Acceptance
- [ ] `collect_branch_results()` function gathers findings from child branches
- [ ] `SynthesizeStep` accepts hierarchical input (parent + child findings)
- [ ] LLM prompt includes child branch findings with filter conditions
- [ ] Final synthesis mentions which branches contributed to conclusion
- [ ] Empty child branches handled gracefully (branch found nothing)
- [ ] Unit test: synthesis with 0 child branches (unchanged behavior)
- [ ] Unit test: synthesis with 2+ child branches
- [ ] Unit test: synthesis when child branch failed
- [ ] mypy --strict passes
- [ ] ruff check passes
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
