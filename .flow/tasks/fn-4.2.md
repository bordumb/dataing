# fn-4.2 Refactor GatherContextStep for DataRegistry

## Description

Modify `GatherContextStep` to load query results into the `DataRegistry` instead of embedding raw data in the `InvestigationContext` string buffer.

### Changes to InvestigationContext

Extend `backend/src/dataing/core/investigation/entities.py`:

```python
class InvestigationContext(BaseModel):
    # Existing fields...

    # New field for data references
    data_registry_refs: dict[str, str] = Field(default_factory=dict)
    # Maps variable_name -> description (e.g., "server_logs": "Apache access logs from last 24h")
```

Note: The actual DataRegistry with DataFrames lives outside the frozen context (passed to steps via dependency injection).

### Changes to GatherContextStep

Modify `backend/src/dataing/core/investigation/steps/gather_context.py`:

**Current behavior:**
```python
context.add_data("logs", raw_log_string)  # Embeds raw data in context
```

**New behavior:**
```python
# Register DataFrame in registry (passed via step deps)
self._data_registry.register(df, name="server_logs")

# Store reference in context
context = context.model_copy(update={
    "data_registry_refs": {
        **context.data_registry_refs,
        "server_logs": "Apache access logs from last 24h (1.2M rows)"
    }
})
```

### Prompt Update

When building LLM prompts, include data references instead of raw data:

```
You have access to the following data variables:
- server_logs: Apache access logs from last 24h (1.2M rows)

Use df.head() or df.describe() to inspect data. Never assume column names.
```

### Files to Modify

- `backend/src/dataing/core/investigation/entities.py` - Add `data_registry_refs` field
- `backend/src/dataing/core/investigation/steps/gather_context.py` - Inject DataRegistry, register data
- `backend/src/dataing/adapters/investigation/step_factory.py` - Wire DataRegistry dependency

### References

- GatherContextStep: `core/investigation/steps/gather_context.py:89-168`
- InvestigationContext: `core/investigation/entities.py:20-63`
- Step factory: `adapters/investigation/step_factory.py:42-127`
## Acceptance
- [ ] `InvestigationContext` extended with `data_registry_refs: dict[str, str]` field
- [ ] `GatherContextStep` modified to accept `DataRegistry` via dependency injection
- [ ] Query results registered in DataRegistry instead of embedded in context
- [ ] Context stores only variable name + description, not raw data
- [ ] Existing tests updated to work with new pattern
- [ ] New unit test: verify data is registered, not embedded
- [ ] mypy --strict passes
- [ ] ruff check passes
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
