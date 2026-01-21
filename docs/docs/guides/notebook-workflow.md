# Notebook Workflow

Dataing integrates directly with Jupyter notebooks through magic commands, providing an interactive investigation experience with streaming timelines and one-click report export.

---

## Prerequisites

- JupyterLab 4.x or Jupyter Notebook
- Demo stack running (`just demo`) or a Dataing API endpoint
- Python 3.11+

---

## Getting Started

### 1. Load the Extension

```python
%load_ext dataing_notebook
```

### 2. Connect to the API

```python
%dataing connect --api-key dd_demo_12345 --base-url http://localhost:8000
```

!!! tip "Environment Variables"
    You can also set `DATAING_API_KEY` and `DATAING_BASE_URL` environment variables to skip the connect step.

### 3. Attach Context

Attach context to an asset using a URN:

```python
%dataing attach postgres://db.schema.orders
```

Or from a SQL query:

```python
%dataing attach "SELECT * FROM orders WHERE user_id IS NULL" --platform postgres
```

### 4. View Lineage

```python
%dataing lineage
```

This displays the upstream and downstream dependencies of your attached assets.

### 5. Start an Investigation

```python
%dataing ask "Why are nulls spiking in customer_id?"
```

The investigation runs with a streaming timeline showing:
- Hypothesis generation
- SQL query execution
- Evidence collection
- Final synthesis

### 6. Export Report

```python
%dataing export --format markdown
```

Generates a standalone incident report that can be shared with stakeholders.

---

## Commands Reference

| Command | Description |
|---------|-------------|
| `%dataing connect` | Connect to the Dataing API |
| `%dataing attach <URN\|SQL>` | Attach context to an asset |
| `%dataing lineage` | Display lineage graph |
| `%dataing ask "<question>"` | Start an investigation |
| `%dataing export` | Export investigation report |
| `%dataing status` | Show current context status |
| `%dataing clear` | Clear current context |
| `%dataing help` | Show help message |

---

## Connect Command

```
%dataing connect [--api-key KEY] [--base-url URL] [--timeout SECONDS]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--api-key`, `-k` | API key for authentication | `DATAING_API_KEY` env var |
| `--base-url`, `-u` | API endpoint URL | `http://localhost:8000` |
| `--timeout`, `-t` | Request timeout in seconds | `30.0` |

**Example:**

```python
%dataing connect --api-key sk-prod-xxxx --base-url https://api.dataing.io
```

---

## Attach Command

```
%dataing attach <URN|SQL> [--datasource ID] [--platform PLATFORM]
```

Attach context from a URN or SQL query. This resolves the asset and creates a context bundle.

### From URN

```python
# PostgreSQL table
%dataing attach postgres://analytics.public.orders

# With specific datasource
%dataing attach orders --datasource ds_prod_analytics
```

### From SQL Query

```python
# Extract tables from SQL
%dataing attach "SELECT * FROM orders JOIN customers ON orders.customer_id = customers.id" --platform postgres
```

| Option | Description |
|--------|-------------|
| `--datasource`, `-d` | Explicit datasource ID |
| `--platform`, `-p` | Default platform for SQL parsing |

---

## Ask Command

```
%dataing ask "<question>" [--no-stream]
```

Start an investigation with the given question. By default, events stream in real-time.

**Example:**

```python
%dataing ask "Why are there null values in customer_id?"
```

**Output:**

```
Starting investigation: Why are there null values in customer_id?
---
Run ID: run_abc123
Status: running

Streaming events...

[run_started] Investigation started
[run_progress] Generating hypotheses...
[run_progress] Testing: Issue is channel-specific
[run_evidence] Query: SELECT channel, COUNT(*) FROM orders WHERE user_id IS NULL GROUP BY channel
[run_progress] Testing: Issue correlates with app version
[run_evidence] Query: SELECT app_version, COUNT(*) FROM orders WHERE user_id IS NULL GROUP BY app_version
[run_completed] Root cause identified: Mobile app v2.3.1 bug

---
Investigation completed
View in UI: http://localhost:3000/investigations/run_abc123
```

| Option | Description |
|--------|-------------|
| `--no-stream` | Use polling instead of SSE streaming |

---

## Export Command

```
%dataing export [--format FORMAT] [--output FILE]
```

Export the last investigation as an incident report.

### Markdown (default)

```python
%dataing export
```

Renders a formatted markdown report directly in the notebook.

### Save to File

```python
%dataing export --output incident_2024-01-15.md
```

### JSON Export

```python
%dataing export --format json --output investigation.json
```

| Option | Description | Default |
|--------|-------------|---------|
| `--format`, `-f` | Output format (`markdown`, `json`) | `markdown` |
| `--output`, `-o` | File path to save report | Display in notebook |

---

## Status Command

```
%dataing status
```

Shows current connection and context status:

```
Dataing Notebook Status
=======================
API: http://localhost:8000
API Key: ***
Context: Attached
  Bundle ID: abc123def456...
  Bundle Hash: sha256:abc...
  Assets: 1
    - orders
Cached bundles: 3
```

---

## Clear Command

```
%dataing clear [--cache] [--all]
```

| Option | Description |
|--------|-------------|
| (none) | Clear current context only |
| `--cache`, `-c` | Also clear bundle cache |
| `--all`, `-a` | Clear everything including client |

---

## Complete Example

Here's a full workflow investigating a null spike:

```python
# Cell 1: Setup
%load_ext dataing_notebook

# Cell 2: Connect
%dataing connect --api-key dd_demo_12345

# Cell 3: Attach to the affected table
%dataing attach postgres://db.public.orders

# Cell 4: Check lineage
%dataing lineage

# Cell 5: Start investigation
%dataing ask "Why has the null rate for customer_id increased from 1% to 15%?"

# Cell 6: Export report for sharing
%dataing export --output incident_report.md
```

---

## Tips

### Auto-connect

If you don't explicitly connect, the client auto-connects on first `attach`:

```python
%dataing attach postgres://db.schema.orders  # Auto-connects to localhost:8000
```

### Bundle Caching

Context bundles are cached by content hash. Repeated `attach` calls with the same assets use the cached bundle:

```python
%dataing attach orders  # Creates bundle
%dataing attach orders  # Uses cached bundle (instant)
```

### Rich Output

Install `rich` for enhanced terminal output:

```bash
pip install rich
```

This improves lineage tree display and timeline formatting.

---

## Troubleshooting

### "No context attached"

Run `%dataing attach` before using `lineage` or `ask` commands.

### "Stream error"

Check that the API is running and accessible. Use `--no-stream` flag to fall back to polling.

### "No tables found in SQL query"

Ensure the SQL contains valid table references. The parser extracts tables from `FROM` and `JOIN` clauses.

---

## See Also

- [SDK Reference](sdk-reference.md) - Programmatic Python client
- [JupyterLab Extension](../integrations/jupyter.md) - Sidebar widget
- [Evidence Types](../concepts/evidence.md) - Understanding investigation outputs
