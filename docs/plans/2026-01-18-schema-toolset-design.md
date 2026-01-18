# Schema Toolset Design

**Date:** 2026-01-18
**Status:** Approved

## Problem

The current `SchemaContextBuilder` dumps all table schemas to the agent upfront, wasting context window space. For databases with many tables, this floods the agent with irrelevant information.

## Solution

Create a schema toolset in `bond/src/bond/tools/schema/` that allows the agent to look up schema information on demand. Pre-load only the target table schema + related table names from lineage.

## Design

### Initial Context (Pre-loaded)

Small, focused context injected as raw JSON:

```json
{
  "target_table": {
    "name": "orders",
    "columns": [
      {
        "name": "customer_id",
        "data_type": "integer",
        "native_type": "BIGINT",
        "nullable": true,
        "is_primary_key": false,
        "is_partition_key": false
      }
    ]
  },
  "related_tables": ["customers", "order_items", "payments"]
}
```

Raw JSON preserves rich metadata (partition keys, primary keys, native types) that markdown formatting would strip out.

### Schema Toolset Structure

**Location:** `bond/src/bond/tools/schema/`

```
bond/src/bond/tools/schema/
├── __init__.py          # Public exports
├── _models.py           # Pydantic request/response models
├── _protocols.py        # SchemaLookupProtocol interface
└── tools.py             # Tool functions + schema_toolset export
```

### Protocol (Interface)

```python
# bond/src/bond/tools/schema/_protocols.py
class SchemaLookupProtocol(Protocol):
    async def get_table_schema(self, table_name: str) -> Table | None: ...
    async def list_tables(self) -> list[str]: ...
    async def get_upstream(self, table_name: str) -> list[str]: ...
    async def get_downstream(self, table_name: str) -> list[str]: ...
```

### Tools

| Tool | Input | Output |
|------|-------|--------|
| `get_table_schema` | table name | Table with columns/types (JSON) |
| `list_tables` | - | list of table names |
| `get_upstream_tables` | table name | list of upstream table names |
| `get_downstream_tables` | table name | list of downstream table names |

### Concrete Implementation

```python
# dataing/src/dataing/adapters/context/schema_lookup.py
class SchemaLookupAdapter:
    """Implements SchemaLookupProtocol using existing adapters."""

    def __init__(
        self,
        db_adapter: BaseAdapter,
        lineage_adapter: LineageAdapter | None = None,
    ):
        self.db_adapter = db_adapter
        self.lineage_adapter = lineage_adapter
        self._schema_cache: SchemaResponse | None = None

    async def get_table_schema(self, table_name: str) -> Table | None:
        # Uses existing adapter.get_schema(), caches result
        # Filters to requested table
        ...
```

**Key points:**
- bond defines the interface only (no dataing imports)
- dataing provides the concrete implementation
- Schema is fetched once and cached per investigation
- Reuses existing `BaseAdapter` and `LineageAdapter`

### Integration

```python
# In Temporal activities or agent invocation

async def run_investigation_agent(
    alert: AnomalyAlert,
    db_adapter: BaseAdapter,
    lineage_adapter: LineageAdapter | None,
):
    # Create the schema lookup adapter
    schema_lookup = SchemaLookupAdapter(db_adapter, lineage_adapter)

    # Build initial context (target table + related names only)
    initial_context = await schema_lookup.build_initial_context(alert.dataset_id)

    # Run agent with schema tools injected via deps
    agent = BondAgent(
        tools=[*schema_toolset],
        deps=schema_lookup,
    )

    result = await agent.run(
        prompt=f"Investigate anomaly. Context: {initial_context.model_dump_json()}"
    )
```

### Changes to Existing Code

**Remove/simplify:**
- `SchemaContextBuilder.format_for_llm()` - delete
- `ContextEngine.gather()` - simplify to return only target table + lineage names
- Remove `max_tables`/`max_columns` limits

### Testing

**Unit tests (bond layer):**
- Mock `SchemaLookupProtocol` for tool tests
- Test each tool function in isolation

**Integration tests (dataing layer):**
- Test `SchemaLookupAdapter` with real adapters (DuckDB, etc.)
- Verify caching behavior
- Test lineage integration

## Benefits

1. **Reduced context usage** - Agent only loads what it needs
2. **Decoupled** - bond defines interface, dataing implements
3. **Preserves metadata** - Raw JSON keeps partition keys, primary keys, etc.
4. **Follows existing patterns** - Same structure as memory toolset
