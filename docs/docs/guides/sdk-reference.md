# SDK Reference

The Dataing SDK provides a Python client for interacting with the Dataing API programmatically.

---

## Installation

=== "pip"

    ```bash
    pip install dataing-sdk
    ```

=== "uv"

    ```bash
    uv add dataing-sdk
    ```

---

## Quick Start

```python
from dataing_sdk import DataingClient, AssetRef

# Initialize client
client = DataingClient(
    base_url="http://localhost:8000",
    api_key="your-api-key"
)

# Create a context for an asset
ctx = client.context("postgres://db.schema.orders")

# Start an investigation
run = client.run(
    assets=[AssetRef(platform="postgres", name="db.schema.orders")],
    goal="Why are nulls spiking in customer_id?"
)

# Stream events
for event in client.stream_run(run.run_id):
    print(f"{event.event}: {event.data}")
```

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATAING_BASE_URL` | API base URL | `http://localhost:8000` |
| `DATAING_API_KEY` | API key for authentication | None |

---

## DataingClient

::: dataing_sdk.client.DataingClient
    options:
      show_source: false
      show_root_heading: true
      show_root_toc_entry: true
      members:
        - __init__
        - attach
        - detach
        - context
        - create_bundle
        - run
        - get_run
        - wait_for_run
        - stream_run
        - health

---

## Types

### AssetRef

::: dataing_sdk.types.AssetRef
    options:
      show_source: false
      show_root_heading: true

### ContextBundle

::: dataing_sdk.types.ContextBundle
    options:
      show_source: false
      show_root_heading: true

### Run

::: dataing_sdk.types.Run
    options:
      show_source: false
      show_root_heading: true

### RunEvent

::: dataing_sdk.types.RunEvent
    options:
      show_source: false
      show_root_heading: true

### RunStatus

::: dataing_sdk.types.RunStatus
    options:
      show_source: false
      show_root_heading: true

---

## Exceptions

::: dataing_sdk.exceptions
    options:
      show_source: false
      show_root_heading: true
      members:
        - DataingError
        - AuthError
        - NotFoundError
        - ValidationError
        - RateLimitError
        - ServerError

---

## Async Usage

The client supports async operations for use in asyncio applications:

```python
import asyncio
from dataing_sdk import DataingClient, AssetRef

async def main():
    client = DataingClient(api_key="your-key")

    async with client:
        # Create bundle asynchronously
        bundle = await client.async_create_bundle(
            assets=[AssetRef(platform="postgres", name="db.schema.orders")]
        )

        # Start run asynchronously
        run = await client.async_run(
            assets=[AssetRef(platform="postgres", name="db.schema.orders")],
            goal="Investigate null spike"
        )

        print(f"Run started: {run.run_id}")

asyncio.run(main())
```

---

## Error Handling

```python
from dataing_sdk import DataingClient
from dataing_sdk.exceptions import AuthError, RateLimitError, ValidationError

client = DataingClient(api_key="your-key")

try:
    run = client.run(assets=[], goal="test")
except AuthError:
    print("Invalid API key")
except ValidationError as e:
    print(f"Invalid request: {e}")
except RateLimitError as e:
    print(f"Rate limited, retry after {e.retry_after}s")
```

---

## See Also

- [Notebook Workflow](notebook-workflow.md) - Using the SDK with Jupyter notebooks
- [Evidence Types](../concepts/evidence.md) - Understanding investigation outputs
- [Datasource Resolution](../concepts/datasource-resolution.md) - How datasources are resolved
