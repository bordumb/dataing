# Dataing CLI

The Dataing CLI (`dataing`) provides a command-line interface for managing datasources and running investigations. It wraps the Python SDK with a user-friendly terminal experience using Rich formatting and streaming output.

---

## Installation

Install the CLI package:

```bash
pip install dataing-cli
```

Or with uv:

```bash
uv pip install dataing-cli
```

### Verify Installation

```bash
dataing --version
```

---

## Quick Start

### 1. Initialize Configuration

```bash
dataing init
```

You'll be prompted for:

- **Backend URL**: The Dataing API endpoint (default: `http://localhost:8000`)
- **API Key**: Your authentication key (stored securely in OS keychain)

### 2. List Datasources

```bash
dataing ds list
```

### 3. Set Default Datasource

```bash
dataing ds attach <datasource-id>
```

### 4. Run an Investigation

```bash
dataing run start main.orders --goal "investigate null spike in user_id"
```

---

## Commands Reference

### Global Options

| Option | Description |
|--------|-------------|
| `--version`, `-V` | Show version and exit |
| `--verbose`, `-v` | Enable verbose output |
| `--json` | Output as JSON (for scripting) |
| `--api-key` | Override API key |
| `--url` | Override backend URL |

### `dataing init`

Initialize CLI configuration with backend URL and API key.

```bash
dataing init --url https://api.dataing.io --api-key <key>
```

| Option | Description |
|--------|-------------|
| `--url`, `-u` | Backend URL (prompted if not provided) |
| `--api-key`, `-k` | API key (prompted securely if not provided) |
| `--no-keyring` | Store API key in config file instead of OS keychain |

The CLI tests the connection before saving configuration.

---

### `dataing status`

Check connection and show current configuration.

```bash
dataing status
```

Example output:

```
╭─────────── dataing CLI ───────────╮
│ Backend     http://localhost:8000 │
│ API Key     ***abcd               │
│ Default DS  prod-snowflake        │
│ Status      ● Connected           │
╰───────────────────────────────────╯
```

With `--json`:

```bash
dataing --json status
```

```json
{
  "connected": true,
  "url": "http://localhost:8000",
  "api_key_configured": true,
  "default_datasource": "prod-snowflake"
}
```

---

### Datasource Commands (`dataing ds`)

#### `dataing ds list`

List all available datasources.

```bash
dataing ds list
```

```
               Datasources
┏━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━┓
┃ ID             ┃ Name          ┃ Type      ┃ Status ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━┩
│ ds-abc123...   │ prod-snowflake│ snowflake │ *      │
│ ds-def456...   │ analytics-pg  │ postgres  │ *      │
└────────────────┴───────────────┴───────────┴────────┘
```

#### `dataing ds test <datasource-id>`

Test datasource connection.

```bash
dataing ds test ds-abc123
```

```
+ Connection successful (50ms)
```

#### `dataing ds attach <datasource-id>`

Set default datasource for future commands.

```bash
dataing ds attach ds-abc123
```

```
+ Default datasource set to prod-snowflake
```

#### `dataing ds schema [datasource-id]`

Show datasource schema. Uses default datasource if not specified.

```bash
dataing ds schema --table users
```

```
users
Column     Type      Nullable
id         integer
name       varchar   +
email      varchar   +
created_at timestamp
```

| Option | Description |
|--------|-------------|
| `--table`, `-t` | Filter to specific table |

---

### Investigation Commands (`dataing run`)

#### `dataing run start <dataset> --goal <goal>`

Start a new investigation.

```bash
dataing run start main.orders --goal "investigate null spike in user_id"
```

By default, the CLI streams a **progressive timeline** in real-time with color-coded panels:

```
╭─ [00:02] Hypothesis #1 ─────────────────────────────────╮
│ The user_id column may have null values due to a    │
│ failed upstream ETL job.                                │
╰─────────────────────────────────────────────────────────╯

╭─ [00:05] Executing Query ───────────────────────────────╮
│ SELECT COUNT(*) FROM raw.customers                      │
│ WHERE loaded_at > '2024-01-14'                          │
╰─────────────────────────────────────────────────────────╯

╭─ [00:08] Evidence: Supports ────────────────────────────╮
│ Finding: Upstream customers table has 0 rows loaded     │
│ since 2024-01-14, indicating a failed pipeline run.     │
│ Confidence: 85%                                         │
╰─────────────────────────────────────────────────────────╯

╭─ [00:15] Synthesis ─────────────────────────────────────╮
│ Root Cause: Upstream ETL job for raw.customers failed   │
│ at 03:00 UTC due to source API timeout.                 │
│ Confidence: 87%                                         │
│                                                         │
│ Recommendations:                                        │
│   • Check the ETL job logs for errors                   │
│   • Verify source API connectivity                      │
╰─────────────────────────────────────────────────────────╯
```

**Timeline color coding:**

| Event Type | Border Color | Description |
|------------|--------------|-------------|
| Hypothesis | Blue | Generated hypotheses with numbering |
| Query | Yellow | SQL queries with syntax highlighting |
| Evidence (supports) | Green | Evidence supporting the hypothesis |
| Evidence (refutes) | Red | Evidence refuting the hypothesis |
| Evidence (inconclusive) | Yellow | Inconclusive evidence |
| Synthesis | Cyan | Final root cause and recommendations |

Each panel shows elapsed time `[MM:SS]` since the investigation started.

| Option | Description |
|--------|-------------|
| `--goal`, `-g` | Investigation goal (required) |
| `--datasource`, `-d` | Datasource ID (uses default if not set) |
| `--no-stream` | Wait for completion, output final result only |
| `--no-watch` | Don't stream progress, just start the run |

#### `--no-stream` Mode

Use `--no-stream` to wait for the investigation to complete and output only the final result:

```bash
dataing run start main.orders --goal "investigate null spike" --no-stream
```

This is useful for scripting or when you only care about the final outcome.

#### `dataing run watch <run-id>`

Watch a running investigation.

```bash
dataing run watch run_xyz789
```

Useful for reconnecting to an investigation started with `--no-watch`.

---

## Configuration

### Config File Location

The CLI follows XDG Base Directory Specification:

| Platform | Location |
|----------|----------|
| Linux/macOS | `~/.config/dataing/config.toml` |
| With `XDG_CONFIG_HOME` set | `$XDG_CONFIG_HOME/dataing/config.toml` |

### Config File Format

```toml
api_url = "http://localhost:8000"
default_datasource_id = "ds-abc123"
default_datasource_name = "prod-snowflake"
```

### Credential Storage

The CLI stores API keys securely using the OS keychain:

| Platform | Backend |
|----------|---------|
| macOS | Keychain |
| Linux | Secret Service (GNOME Keyring, KWallet) |
| Windows | Windows Credential Manager |

Use `--no-keyring` during `init` to store in config file instead (less secure).

### Credential Precedence

The CLI resolves credentials in this order (highest to lowest):

1. **Command-line flag**: `--api-key`
2. **Environment variable**: `DATAING_API_KEY`
3. **OS keychain**: Stored via `dataing init`
4. **Config file**: Fallback for systems without keychain

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DATAING_API_KEY` | API key (overrides keychain/config) |
| `DATAING_BASE_URL` | Backend URL (overrides config) |
| `XDG_CONFIG_HOME` | Custom config directory |

### Example: CI/CD Usage

```bash
export DATAING_API_KEY="${SECRETS_DATAING_API_KEY}"
export DATAING_BASE_URL="https://api.dataing.io"

dataing run start main.orders \
  --goal "post-deploy data validation" \
  --no-watch
```

---

## JSON Output Mode

All commands support `--json` for machine-readable output:

```bash
# List datasources as JSON
dataing --json ds list

# Get status as JSON
dataing --json status

# Stream events as NDJSON (newline-delimited JSON)
dataing --json run start main.orders --goal "investigate null spike"
```

### NDJSON Streaming Format

When streaming investigations, `--json` outputs **NDJSON** (one compact JSON object per line):

```bash
dataing --json run start main.orders --goal "investigate null spike"
```

```json
{"event":"hypothesis_generated","data":{"hypothesis":"Null values from upstream failure"},"is_terminal":false}
{"event":"query_executed","data":{"query":"SELECT COUNT(*) FROM main.orders WHERE user_id IS NULL"},"is_terminal":false}
{"event":"evidence_collected","data":{"supports_hypothesis":true,"interpretation":"Found 500 null rows"},"is_terminal":false}
{"event":"run_completed","data":{"root_cause":"Upstream ETL failed","confidence":0.87},"is_terminal":true}
```

This makes it easy to pipe to `jq` or other tools:

```bash
# Get only the final result
dataing --json run start main.orders --goal "..." | jq 'select(.event == "run_completed")'

# Extract all evidence
dataing --json run start main.orders --goal "..." | jq 'select(.event == "evidence_collected")'
```

### Non-TTY Output

When output is piped or redirected (non-TTY), the CLI automatically falls back to **plain text** without ANSI color codes:

```bash
# Piped output uses plain text
dataing run start main.orders --goal "..." | tee investigation.log

# Use --json for structured output in pipes
dataing --json run start main.orders --goal "..." > events.jsonl
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error (connection failed, not found, etc.) |
| 2 | Validation error (invalid input) |
| 130 | Interrupted (Ctrl+C) |

---

## Shell Completion

Enable tab completion for your shell:

```bash
# Bash
dataing --install-completion bash

# Zsh
dataing --install-completion zsh

# Fish
dataing --install-completion fish
```

After installation, restart your shell or source the config file.

---

## Troubleshooting

### "No API key configured"

Run `dataing init` to configure your API key, or set `DATAING_API_KEY` environment variable.

### "Connection failed"

1. Check the backend URL: `dataing status`
2. Verify the backend is running: `curl http://localhost:8000/health`
3. Check network connectivity

### "No datasource specified"

Either:

- Provide `--datasource` flag: `dataing run start table --goal "..." --datasource ds-123`
- Set a default: `dataing ds attach ds-123`

### Keychain Issues

If keychain storage fails:

```bash
# Store in config file instead
dataing init --no-keyring
```

Or use environment variable:

```bash
export DATAING_API_KEY="your-key"  # pragma: allowlist secret
```

---

## See Also

- [Python SDK Documentation](../sdk/python.md)
- [API Reference](../api/reference.md)
- [Getting Started Guide](../getting-started.md)
