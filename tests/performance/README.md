# Performance Benchmark

Compares investigation runtime between git branches. Runs multiple investigations on each branch and produces statistical comparisons.

## Prerequisites

- Docker running (for PostgreSQL, Temporal, Jaeger)
- Both branches exist locally and have been fetched
- Python 3.11+ with `httpx` installed (`pip install httpx`)
- No other services on ports 8000, 7233, 8233, 5432, 16686

## Quick Start

```bash
# Recommended: compare branches with server restart (avoids degradation) and keep infra for analysis
python tests/performance/bench.py --restart-between-runs --keep-infra

# Compare specific branches
python tests/performance/bench.py --branches feature-x main --restart-between-runs --keep-infra

# Fewer runs for quick comparison
python tests/performance/bench.py --runs 5 --warmup 1 --restart-between-runs --keep-infra

# After benchmark, analyze Temporal data
python tests/performance/analyze_temporal.py

# When done, clean up Docker
docker rm -f dataing-demo-postgres dataing-demo-temporal dataing-demo-jaeger
```

## Command Line Options

| Option | Default | Description |
|--------|---------|-------------|
| `--branches` | `fn-17 main` | Space-separated list of branches to compare |
| `--runs` | `10` | Number of timed investigation runs per branch |
| `--warmup` | `2` | Number of warmup runs (not counted in stats) |
| `--timeout` | `300` | Max seconds per investigation before timeout |
| `--output-dir` | `tests/performance` | Directory for results files |
| `--dry-run` | `false` | Setup only, don't run investigations |
| `--restart-between-runs` | `false` | **Recommended.** Restart server between runs to avoid process-level degradation |
| `--keep-infra` | `false` | **Recommended.** Keep Docker running after benchmark for Temporal analysis |
| `--verbose` | `false` | Enable verbose logging |

## Why Use `--restart-between-runs`?

Without server restarts, investigations progressively slow down due to:
- **Memory accumulation** in the worker process
- **Cache growth** (adapters, schemas, patterns)
- **Connection pool state** buildup

Example degradation pattern without restarts:
```
Run 1:  48s   ████
Run 5: 112s   █████████
Run 10: 210s  █████████████████
```

With `--restart-between-runs`, each run starts fresh:
```
Run 1:  48s   ████
Run 5:  52s   ████
Run 10: 49s   ████
```

## What It Measures

**Wall-clock time** from the moment `POST /api/v1/investigations` returns (investigation created and queued) until the investigation reaches a **terminal status**:
- `completed` - Investigation finished successfully
- `failed` - Workflow failed
- `cancelled` - User cancelled
- `timed_out` - Exceeded timeout
- `terminated` - Forcefully terminated

Status is polled via `GET /api/v1/investigations/{id}/status` with exponential backoff (2s-10s intervals with jitter).

## How It Works

1. **Docker Infrastructure** - Shared PostgreSQL, Temporal, and Jaeger containers run for all branches
2. **Git Worktrees** - Each branch runs in an isolated worktree (no checkout switching)
3. **Server Lifecycle** - For each branch:
   - Create worktree
   - Start FastAPI backend + Temporal worker
   - Wait for `/health` endpoint
   - Run warmup investigations (not counted)
   - Run timed investigations (with optional server restart between each)
   - Stop processes
4. **Cleanup** - Remove worktrees; optionally keep Docker for analysis

## Output Files

### `results.json`

Machine-readable complete results:

```json
{
  "timestamp": "2025-01-19T10:30:00Z",
  "machine": "hostname",
  "config": {
    "runs": 10,
    "warmup": 2,
    "timeout": 300
  },
  "branches": {
    "fn-17": {
      "git_sha": "abc123",
      "runs": [
        {"duration_seconds": 45.2, "status": "completed", "investigation_id": "uuid"},
        ...
      ],
      "stats": {
        "mean": 47.3,
        "median": 46.5,
        "stdev": 2.1,
        "p95": 51.2,
        "min": 44.1,
        "max": 52.3
      }
    },
    "main": {...}
  },
  "comparison": {
    "delta_mean_seconds": -5.2,
    "delta_mean_percent": -11.0,
    "faster_branch": "fn-17"
  }
}
```

### `results.md`

Human-readable summary table:

```markdown
| Branch | SHA | Mean | Median | P95 | Stdev | Min | Max |
|--------|-----|------|--------|-----|-------|-----|-----|
| fn-17  | abc123 | 47.3s | 46.5s | 51.2s | 2.1s | 44.1s | 52.3s |
| main   | def456 | 52.5s | 51.8s | 56.1s | 2.8s | 49.2s | 58.7s |

**Delta:** fn-17 is 5.2s (9.9%) faster than main
```

### Console Output

```
=== Performance Benchmark Results ===

fn-17 (abc123):
  Mean:   47.3s
  Median: 46.5s
  P95:    51.2s
  Stdev:  2.1s

main (def456):
  Mean:   52.5s
  Median: 51.8s
  P95:    56.1s
  Stdev:  2.8s

Delta:
  fn-17 is 5.2s (9.9%) FASTER than main
```

## Temporal Analysis

After running a benchmark with `--keep-infra`, analyze workflow execution details:

```bash
# Aggregate stats across all workflows
python tests/performance/analyze_temporal.py

# Filter by workflow type
python tests/performance/analyze_temporal.py --workflow-type InvestigationWorkflow

# Analyze last N workflows
python tests/performance/analyze_temporal.py --last 20

# Save detailed JSON
python tests/performance/analyze_temporal.py --output temporal_analysis.json
```

### Sample Output

```
======================================================================
Temporal Workflow Analysis - 20 workflows
======================================================================

WORKFLOW TOTAL DURATION:
  Count:  20
  Mean:   47.39s
  Median: 46.12s
  P95:    52.53s
  Range:  44.39s - 54.20s

======================================================================
ACTIVITY BREAKDOWN:
======================================================================

Activity                                  Count     Mean   Median      P95      Max
--------------------------------------------------------------------------------
generate_hypotheses                          20   18.45s   17.12s   22.67s   24.34s
evaluate_hypothesis                          60   12.23s   11.89s   15.45s   18.12s
synthesize_findings                          20    8.34s    7.56s   10.90s   12.45s
gather_context                               20    5.67s    5.89s    7.34s    8.67s

======================================================================
PER-RUN PROGRESSION (to detect degradation):
======================================================================
  Run  1: 46.39s     846cbbc6-15c6-4b4b-bac8-1256cbcc2038
  Run  2: 47.80s     438ce2dc-0eae-40ff-97a8-7b4ca767a78c
  ...
  Run 10: 48.20s     30d0fc58-a6db-4c62-a4a8-048bd3fd7f97

  First third avg: 46.61s
  Last third avg:  47.89s
  ✓ Stable performance (±2.7%)
```

### Persistent Data

Temporal data is persisted in `tests/performance/.temporal/temporal.db` so you can:
- Re-analyze previous benchmark runs
- Compare activity timing across different branches
- Track degradation patterns over time

## Investigation Payload

Each investigation uses the null_spike demo fixture:

```json
{
  "alert": {
    "dataset_ids": ["orders"],
    "metric_spec": {
      "metric_type": "column",
      "expression": "null_count(customer_id)",
      "display_name": "Null Customer IDs",
      "columns_referenced": ["customer_id"]
    },
    "anomaly_type": "null_spike",
    "expected_value": 5,
    "actual_value": 200,
    "deviation_pct": 3900,
    "anomaly_date": "2026-01-10",
    "severity": "high"
  }
}
```

## Troubleshooting

### Port conflicts

The benchmark auto-selects ports if 8000 is in use. If you see port errors:
```bash
# Check what's using the port
lsof -i :8000
# Kill it if needed
kill -9 $(lsof -ti:8000)
```

### Worktree cleanup

If a benchmark fails mid-run, clean up orphan worktrees:
```bash
git worktree list
git worktree remove benchmarks/worktrees/fn-17 --force
git worktree remove benchmarks/worktrees/main --force
```

### Docker cleanup

```bash
docker rm -f dataing-demo-postgres dataing-demo-temporal dataing-demo-jaeger
```

### Investigation hangs

If investigations hang consistently:
1. Check Temporal UI at http://localhost:8233
2. Check Jaeger traces at http://localhost:16686
3. Increase `--timeout` or check backend logs
