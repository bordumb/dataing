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
    api_key="your-api-key"  # pragma: allowlist secret
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

The main client for interacting with the Dataing API.

### Constructor

```python
DataingClient(
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: float = 30.0
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `base_url` | `str \| None` | API base URL. Falls back to `DATAING_BASE_URL` env var, then `http://localhost:8000` |
| `api_key` | `str \| None` | API key. Falls back to `DATAING_API_KEY` env var |
| `timeout` | `float` | Request timeout in seconds (default: 30.0) |

### Methods

#### `attach(datasource_id, name=None)`

Set the session default datasource for subsequent operations.

```python
client.attach("ds_prod", name="Production Analytics")
```

#### `detach()`

Clear the session default datasource.

#### `context(*urns, assets=None, window=None)`

Create a Context for the given assets. Returns a `Context` object with query and analysis methods.

```python
ctx = client.context("postgres://db.schema.orders", window="7d")
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `*urns` | `str` | URN strings (e.g., `postgres://db.schema.table`) |
| `assets` | `list[AssetRef] \| None` | Asset references |
| `window` | `str \| None` | Time window (e.g., `"7d"`, `"24h"`) |

#### `create_bundle(assets, window=None, ...)`

Create a context bundle for the given assets.

| Parameter | Type | Description |
|-----------|------|-------------|
| `assets` | `list[AssetRef]` | Assets to include |
| `window` | `str \| None` | Time window |
| `include_lineage` | `bool` | Include lineage graph (default: True) |
| `include_operational` | `bool` | Include operational metadata (default: True) |
| `include_anomalies` | `bool` | Include detected anomalies (default: True) |

#### `run(assets, goal, bundle_id=None)`

Start an investigation run.

```python
run = client.run(
    assets=[AssetRef(platform="postgres", name="db.schema.orders")],
    goal="Why are there null values spiking?"
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `assets` | `list[AssetRef]` | Assets to investigate |
| `goal` | `str` | Natural language investigation goal |
| `bundle_id` | `str \| None` | Optional bundle ID to reuse |

**Returns:** `Run` object with `run_id`, `status`, etc.

#### `get_run(run_id)`

Get the current status of a run.

#### `wait_for_run(run_id, poll_interval=1.0, timeout=300.0, on_progress=None)`

Wait for a run to complete by polling.

| Parameter | Type | Description |
|-----------|------|-------------|
| `run_id` | `str` | Run ID |
| `poll_interval` | `float` | Seconds between polls (default: 1.0) |
| `timeout` | `float \| None` | Max wait time (default: 300.0) |
| `on_progress` | `callable \| None` | Progress callback |

#### `stream_run(run_id, last_seq=None, timeout=300.0)`

Stream SSE events from a run in real-time.

```python
for event in client.stream_run(run.run_id):
    print(f"[{event.event}] {event.data}")
    if event.event in ("run_completed", "run_failed"):
        break
```

**Yields:** `RunEvent` objects

#### `health()`

Check API health and connectivity. Returns a dict with status info.

---

## Types

### AssetRef

Reference to a data asset (table, view, model).

| Field | Type | Description |
|-------|------|-------------|
| `platform` | `str` | Data platform (postgres, snowflake, dbt, etc.) |
| `name` | `str` | Fully qualified name (database.schema.table) |
| `datasource_id` | `str \| None` | Optional datasource ID for disambiguation |

**Methods:**

- `AssetRef.from_urn(urn)` — Parse from URN string
- `asset.to_urn()` — Convert to URN string

```python
# Direct construction
asset = AssetRef(platform="postgres", name="db.schema.orders")

# From URN
asset = AssetRef.from_urn("postgres://db.schema.orders")
```

### ContextBundle

Cached context snapshot for data assets.

| Field | Type | Description |
|-------|------|-------------|
| `bundle_id` | `str` | Unique bundle identifier |
| `resolved_assets` | `list[ResolvedAsset]` | Resolved assets with datasource bindings |
| `lineage` | `dict \| None` | Data lineage graph |
| `operational` | `dict \| None` | Operational metadata |
| `anomalies` | `list[dict] \| None` | Detected anomalies |
| `bundle_hash` | `str` | Content hash for caching |
| `expires_at` | `datetime` | Cache expiration time |

### Run

An investigation run.

| Field | Type | Description |
|-------|------|-------------|
| `run_id` | `str` | Unique run identifier |
| `bundle_id` | `str` | Context bundle used |
| `bundle_hash` | `str` | Bundle content hash |
| `status` | `RunStatus` | Current status |
| `error_code` | `str \| None` | Error code if failed |
| `created_at` | `datetime` | Creation timestamp |

### RunEvent

Real-time event from SSE streaming.

| Field | Type | Description |
|-------|------|-------------|
| `seq` | `int` | Sequence number for resumption |
| `event` | `str` | Event type (run_started, run_progress, etc.) |
| `run_id` | `str` | Run ID |
| `data` | `dict` | Event payload |
| `timestamp` | `str \| None` | ISO 8601 timestamp |

**Properties:**

- `is_terminal` — True if run_completed or run_failed
- `is_evidence` — True if run_evidence event
- `is_progress` — True if run_progress event

### RunStatus

Enum of run statuses.

| Value | Description |
|-------|-------------|
| `RUNNING` | Investigation is actively executing |
| `COMPLETED` | Finished successfully |
| `FAILED` | Encountered an error |
| `CANCELLED` | Manually cancelled |

---

## Exceptions

All exceptions inherit from `DataingError`.

| Exception | HTTP Code | Description |
|-----------|-----------|-------------|
| `DataingError` | — | Base exception for all SDK errors |
| `AuthError` | 401/403 | Authentication or authorization failed |
| `NotFoundError` | 404 | Resource not found |
| `ValidationError` | 422 | Request validation failed |
| `RateLimitError` | 429 | Rate limit exceeded (has `retry_after` attribute) |
| `ServerError` | 5xx | Server-side error |
| `TimeoutError` | — | Request timed out |
| `AmbiguousAssetError` | 409 | Multiple datasources match (has `candidates` attribute) |
| `StreamError` | — | SSE streaming error |
| `ReplayWindowExpiredError` | 410 | Replay window expired |

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
