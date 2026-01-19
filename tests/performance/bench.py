#!/usr/bin/env python3
"""Performance benchmark comparing investigation runtime between git branches.

Usage:
    python tests/performance/bench.py
    python tests/performance/bench.py --branches fn-17 main --runs 10
    python tests/performance/bench.py --dry-run --verbose
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import random
import shutil
import signal
import socket
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Optional: use httpx if available, fall back to urllib
try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    import urllib.error
    import urllib.request

    HAS_HTTPX = False

# Load .env file from repo root
try:
    from dotenv import load_dotenv

    # Find repo root and load .env
    _repo_root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    if _repo_root:
        load_dotenv(Path(_repo_root) / ".env")
except ImportError:
    pass  # dotenv not installed, rely on shell environment

# ============================================================================
# Constants
# ============================================================================

DEFAULT_BRANCHES = ["fn-17", "main"]
DEFAULT_NUM_RUNS = 10
DEFAULT_WARMUP_RUNS = 2
DEFAULT_TIMEOUT = 300  # 5 minutes per investigation
DEFAULT_POLL_INTERVAL = 2.0
MAX_POLL_INTERVAL = 10.0
HEALTH_TIMEOUT = 120  # 2 minutes to wait for server to be ready

API_KEY = "dd_demo_12345"
BASE_PORT = 8000

TERMINAL_STATUSES = {"completed", "failed", "cancelled", "timed_out", "terminated"}

# Investigation payload (null_spike demo)
INVESTIGATION_PAYLOAD = {
    "alert": {
        "dataset_ids": ["orders"],
        "metric_spec": {
            "metric_type": "column",
            "expression": "null_count(customer_id)",
            "display_name": "Null Customer IDs",
            "columns_referenced": ["customer_id"],
        },
        "anomaly_type": "null_spike",
        "expected_value": 5,
        "actual_value": 200,
        "deviation_pct": 3900,
        "anomaly_date": "2026-01-10",
        "severity": "high",
    }
}

# ============================================================================
# Logging
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class RunResult:
    """Result of a single investigation run."""

    duration_seconds: float
    status: str
    investigation_id: str
    error: str | None = None


@dataclass
class BranchStats:
    """Statistics for a branch's runs."""

    mean: float
    median: float
    stdev: float
    p95: float
    min_val: float
    max_val: float


@dataclass
class BranchResult:
    """Complete result for a branch."""

    branch: str
    git_sha: str
    runs: list[RunResult] = field(default_factory=list)
    stats: BranchStats | None = None


@dataclass
class BenchmarkResults:
    """Complete benchmark results."""

    timestamp: str
    machine: str
    config: dict[str, Any]
    branches: dict[str, BranchResult] = field(default_factory=dict)
    comparison: dict[str, Any] | None = None


# ============================================================================
# HTTP Client (works with or without httpx)
# ============================================================================


class HTTPClient:
    """Simple HTTP client that works with httpx or urllib."""

    def __init__(self, base_url: str, timeout: float = 30.0):
        """Initialize HTTP client."""
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = {
            "Content-Type": "application/json",
            "X-API-Key": API_KEY,
        }
        if HAS_HTTPX:
            self._client = httpx.Client(timeout=timeout)
        else:
            self._client = None

    def close(self) -> None:
        """Close the client."""
        if HAS_HTTPX and self._client:
            self._client.close()

    def get(self, path: str) -> dict[str, Any]:
        """Make a GET request."""
        url = f"{self.base_url}{path}"
        if HAS_HTTPX:
            resp = self._client.get(url, headers=self.headers)
            resp.raise_for_status()
            return resp.json()
        else:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())

    def post(self, path: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make a POST request."""
        url = f"{self.base_url}{path}"
        body = json.dumps(data).encode() if data else None
        if HAS_HTTPX:
            resp = self._client.post(url, headers=self.headers, content=body)
            resp.raise_for_status()
            return resp.json()
        else:
            req = urllib.request.Request(url, data=body, headers=self.headers, method="POST")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())

    def health_check(self) -> bool:
        """Check if server is healthy."""
        try:
            resp = self.get("/health")
            return resp.get("status") == "healthy"
        except Exception:
            return False


# ============================================================================
# Utility Functions
# ============================================================================


def find_free_port(start: int = BASE_PORT) -> int:
    """Find a free port starting from the given port."""
    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("localhost", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"Could not find a free port starting from {start}")


def get_git_sha(repo_path: Path, branch: str) -> str:
    """Get the git SHA for a branch."""
    result = subprocess.run(
        ["git", "rev-parse", "--short", branch],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def get_repo_root() -> Path:
    """Get the repository root directory."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip())


# ============================================================================
# Git Worktree Management
# ============================================================================


def get_current_branch(repo_root: Path) -> str:
    """Get the currently checked out branch name."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def setup_worktree(branch: str, base_dir: Path) -> tuple[Path, bool]:
    """Create a git worktree for the given branch.

    Returns:
        Tuple of (path, is_worktree) where is_worktree is False if using current dir.
    """
    # Check if we're already on this branch
    current_branch = get_current_branch(base_dir)
    if current_branch == branch:
        logger.info(f"Already on branch '{branch}', using current directory")
        return base_dir, False

    worktree_path = base_dir / "benchmarks" / "worktrees" / branch.replace("/", "-")

    # Remove existing worktree if it exists
    if worktree_path.exists():
        logger.info(f"Removing existing worktree at {worktree_path}")
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            cwd=base_dir,
            capture_output=True,
        )
        if worktree_path.exists():
            shutil.rmtree(worktree_path)

    # Create worktree directory
    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    # Add the worktree
    logger.info(f"Creating worktree for branch '{branch}' at {worktree_path}")
    result = subprocess.run(
        ["git", "worktree", "add", str(worktree_path), branch],
        cwd=base_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to create worktree: {result.stderr}")

    return worktree_path, True


def cleanup_worktree(worktree_path: Path, base_dir: Path, is_worktree: bool) -> None:
    """Remove a git worktree."""
    if not is_worktree:
        # Not a worktree, nothing to clean up
        return
    if worktree_path.exists():
        logger.info(f"Cleaning up worktree at {worktree_path}")
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            cwd=base_dir,
            capture_output=True,
        )
        if worktree_path.exists():
            shutil.rmtree(worktree_path)


# ============================================================================
# Docker Infrastructure
# ============================================================================


def start_docker_infrastructure() -> None:
    """Start shared Docker containers (PostgreSQL, Temporal, Jaeger)."""
    logger.info("Starting Docker infrastructure...")

    # Start PostgreSQL
    logger.info("Starting PostgreSQL...")
    subprocess.run(["docker", "rm", "-f", "dataing-demo-postgres"], capture_output=True)
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            "dataing-demo-postgres",
            "-e",
            "POSTGRES_DB=dataing_demo",
            "-e",
            "POSTGRES_USER=dataing",
            "-e",
            "POSTGRES_PASSWORD=dataing",
            "-p",
            "5432:5432",
            "pgvector/pgvector:pg16",
        ],
        check=True,
    )

    # Wait for PostgreSQL
    for _ in range(30):
        result = subprocess.run(
            [
                "docker",
                "exec",
                "dataing-demo-postgres",
                "pg_isready",
                "-U",
                "dataing",
            ],
            capture_output=True,
        )
        if result.returncode == 0:
            logger.info("PostgreSQL is ready")
            break
        time.sleep(1)
    else:
        raise RuntimeError("PostgreSQL did not become ready in time")

    # Start Temporal with persistent storage
    logger.info("Starting Temporal...")
    subprocess.run(["docker", "rm", "-f", "dataing-demo-temporal"], capture_output=True)

    # Create persistent data directory for Temporal
    temporal_data_dir = Path(__file__).parent / ".temporal"
    temporal_data_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            "dataing-demo-temporal",
            "-p",
            "7233:7233",
            "-p",
            "8233:8233",
            "-v",
            f"{temporal_data_dir.absolute()}:/data",
            "--entrypoint",
            "temporal",
            "temporalio/admin-tools:latest",
            "server",
            "start-dev",
            "--ip",
            "0.0.0.0",
            "--db-filename",
            "/data/temporal.db",
        ],
        check=True,
    )

    # Wait for Temporal
    for _ in range(30):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                s.connect(("localhost", 8233))
                logger.info("Temporal is ready")
                break
        except (OSError, socket.timeout):
            time.sleep(1)
    else:
        raise RuntimeError("Temporal did not become ready in time")

    # Start Jaeger
    logger.info("Starting Jaeger...")
    subprocess.run(["docker", "rm", "-f", "dataing-demo-jaeger"], capture_output=True)
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            "dataing-demo-jaeger",
            "-e",
            "COLLECTOR_OTLP_ENABLED=true",
            "-p",
            "16686:16686",
            "-p",
            "4317:4317",
            "-p",
            "4318:4318",
            "jaegertracing/all-in-one:1.76.0",
        ],
        check=True,
    )

    logger.info("Docker infrastructure started successfully")


def stop_docker_infrastructure() -> None:
    """Stop Docker containers."""
    logger.info("Stopping Docker infrastructure...")
    for container in ["dataing-demo-postgres", "dataing-demo-temporal", "dataing-demo-jaeger"]:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True)
    logger.info("Docker infrastructure stopped")


def run_migrations(worktree_path: Path) -> None:
    """Run database migrations."""
    logger.info("Running database migrations...")
    migrations_dir = worktree_path / "python-packages" / "dataing" / "migrations"

    if not migrations_dir.exists():
        logger.warning(f"Migrations directory not found: {migrations_dir}")
        return

    # Get all migration files sorted
    migration_files = sorted(migrations_dir.glob("*.sql"))

    for migration_file in migration_files:
        result = subprocess.run(
            [
                "psql",
                "-h",
                "localhost",
                "-U",
                "dataing",
                "-d",
                "dataing_demo",
                "-f",
                str(migration_file),
            ],
            capture_output=True,
            env={**os.environ, "PGPASSWORD": "dataing"},
        )
        if result.returncode != 0 and b"already exists" not in result.stderr:
            logger.debug(f"Migration {migration_file.name}: {result.stderr.decode()[:200]}")

    logger.info("Migrations complete")


# ============================================================================
# Server Management
# ============================================================================


class DemoServer:
    """Manages the demo server processes for a branch."""

    def __init__(self, worktree_path: Path, port: int, verbose: bool = False):
        """Initialize demo server manager."""
        self.worktree_path = worktree_path
        self.port = port
        self.verbose = verbose
        self.backend_process: subprocess.Popen | None = None
        self.worker_process: subprocess.Popen | None = None
        self._env = self._build_env()

    def _build_env(self) -> dict[str, str]:
        """Build environment variables for the server."""
        env = os.environ.copy()
        env.update(
            {
                "DATADR_DEMO_MODE": "true",
                "DATADR_FIXTURE_PATH": str(self.worktree_path / "demo" / "fixtures" / "null_spike"),
                "DATABASE_URL": "postgresql://dataing:dataing@localhost:5432/dataing_demo",
                "APP_DATABASE_URL": "postgresql://dataing:dataing@localhost:5432/dataing_demo",
                "INVESTIGATION_ENGINE": "temporal",
                "TEMPORAL_HOST": "localhost:7233",
                "ENCRYPTION_KEY": "ZnxhCyx4-ZjziPWtUguwGOFMMiLNioSwso5-qNPAGZI=",
                "OTEL_SERVICE_NAME": "dataing-bench",
                "OTEL_TRACES_ENABLED": "true",
                "OTEL_METRICS_ENABLED": "false",
                "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318",
            }
        )
        return env

    def start(self) -> None:
        """Start the backend and worker processes."""
        logger.info(f"Starting demo server on port {self.port}...")

        # Ensure uv dependencies are synced
        subprocess.run(
            ["uv", "sync", "--quiet"],
            cwd=self.worktree_path,
            env=self._env,
            capture_output=True,
        )

        # Output handling based on verbose mode
        if self.verbose:
            stdout = None  # Inherit from parent (show output)
            stderr = None
        else:
            stdout = subprocess.PIPE
            stderr = subprocess.PIPE

        # Start backend
        self.backend_process = subprocess.Popen(
            [
                "uv",
                "run",
                "fastapi",
                "dev",
                "python-packages/dataing/src/dataing/entrypoints/api/app.py",
                "--host",
                "0.0.0.0",
                "--port",
                str(self.port),
            ],
            cwd=self.worktree_path,
            env=self._env,
            stdout=stdout,
            stderr=stderr,
        )

        # Start Temporal worker
        self.worker_process = subprocess.Popen(
            ["uv", "run", "python", "-m", "dataing.entrypoints.temporal_worker"],
            cwd=self.worktree_path,
            env=self._env,
            stdout=stdout,
            stderr=stderr,
        )

        logger.info(f"Server processes started (backend PID: {self.backend_process.pid}, worker PID: {self.worker_process.pid})")

    def wait_for_ready(self, timeout: int = HEALTH_TIMEOUT) -> bool:
        """Wait for the server to be ready."""
        logger.info(f"Waiting for server to be ready on port {self.port}...")
        client = HTTPClient(f"http://localhost:{self.port}")
        try:
            start = time.time()
            while time.time() - start < timeout:
                # Check if processes have crashed
                if self.backend_process and self.backend_process.poll() is not None:
                    exit_code = self.backend_process.returncode
                    stderr_output = ""
                    if self.backend_process.stderr:
                        stderr_output = self.backend_process.stderr.read().decode()[:500]
                    logger.error(f"Backend process exited with code {exit_code}")
                    if stderr_output:
                        logger.error(f"Backend stderr: {stderr_output}")
                    return False

                if self.worker_process and self.worker_process.poll() is not None:
                    exit_code = self.worker_process.returncode
                    stderr_output = ""
                    if self.worker_process.stderr:
                        stderr_output = self.worker_process.stderr.read().decode()[:500]
                    logger.error(f"Worker process exited with code {exit_code}")
                    if stderr_output:
                        logger.error(f"Worker stderr: {stderr_output}")
                    return False

                if client.health_check():
                    logger.info("Server is ready")
                    return True
                time.sleep(1)
            logger.error(f"Server did not become ready within {timeout}s")
            return False
        finally:
            client.close()

    def stop(self) -> None:
        """Stop the backend and worker processes."""
        logger.info("Stopping demo server...")

        # Stop worker first
        if self.worker_process:
            self.worker_process.terminate()
            try:
                self.worker_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.worker_process.kill()
            self.worker_process = None

        # Stop backend
        if self.backend_process:
            self.backend_process.terminate()
            try:
                self.backend_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.backend_process.kill()
            self.backend_process = None

        # Clean up any orphan processes on the port
        subprocess.run(f"lsof -ti:{self.port} | xargs kill -9 2>/dev/null || true", shell=True)

        logger.info("Server stopped")


# ============================================================================
# Investigation Runner
# ============================================================================


def run_investigation(client: HTTPClient, timeout: int) -> RunResult:
    """Run a single investigation and measure its duration."""
    start_time = time.time()

    try:
        # Start investigation
        response = client.post("/api/v1/investigations", INVESTIGATION_PAYLOAD)
        investigation_id = response["investigation_id"]
        logger.debug(f"Started investigation {investigation_id}")

        # Poll for completion
        interval = DEFAULT_POLL_INTERVAL
        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                return RunResult(
                    duration_seconds=elapsed,
                    status="timeout",
                    investigation_id=investigation_id,
                    error=f"Investigation did not complete within {timeout}s",
                )

            try:
                status_response = client.get(f"/api/v1/investigations/{investigation_id}/status")
                workflow_status = status_response.get("workflow_status", "unknown")

                if workflow_status in TERMINAL_STATUSES:
                    duration = time.time() - start_time
                    logger.debug(f"Investigation {investigation_id} completed with status '{workflow_status}' in {duration:.2f}s")
                    return RunResult(
                        duration_seconds=duration,
                        status=workflow_status,
                        investigation_id=investigation_id,
                    )

            except Exception as e:
                logger.warning(f"Error polling status: {e}")

            # Exponential backoff with jitter
            jitter = random.uniform(0, 0.5 * interval)
            sleep_time = min(interval + jitter, MAX_POLL_INTERVAL)
            time.sleep(sleep_time)
            interval = min(interval * 1.2, MAX_POLL_INTERVAL)

    except Exception as e:
        duration = time.time() - start_time
        return RunResult(
            duration_seconds=duration,
            status="error",
            investigation_id="",
            error=str(e),
        )


def calculate_stats(runs: list[RunResult]) -> BranchStats:
    """Calculate statistics from run results."""
    durations = [r.duration_seconds for r in runs if r.status == "completed"]

    if not durations:
        return BranchStats(
            mean=0.0,
            median=0.0,
            stdev=0.0,
            p95=0.0,
            min_val=0.0,
            max_val=0.0,
        )

    durations.sort()
    n = len(durations)
    p95_idx = int(n * 0.95)

    return BranchStats(
        mean=statistics.mean(durations),
        median=statistics.median(durations),
        stdev=statistics.stdev(durations) if len(durations) > 1 else 0.0,
        p95=durations[min(p95_idx, n - 1)],
        min_val=min(durations),
        max_val=max(durations),
    )


# ============================================================================
# Benchmark Runner
# ============================================================================


def run_benchmark_for_branch(
    branch: str,
    repo_root: Path,
    num_runs: int,
    warmup_runs: int,
    timeout: int,
    dry_run: bool = False,
    verbose: bool = False,
    restart_between_runs: bool = False,
) -> BranchResult:
    """Run benchmark for a single branch."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Benchmarking branch: {branch}")
    logger.info(f"{'='*60}")

    git_sha = get_git_sha(repo_root, branch)
    result = BranchResult(branch=branch, git_sha=git_sha)

    # Create worktree (or use current dir if already on this branch)
    worktree_path, is_worktree = setup_worktree(branch, repo_root)

    # Find free port
    port = find_free_port()
    logger.info(f"Using port {port}")

    # Run migrations (safe to run multiple times)
    run_migrations(worktree_path)

    # Start server
    server = DemoServer(worktree_path, port, verbose=verbose)
    try:
        server.start()
        if not server.wait_for_ready():
            raise RuntimeError("Server failed to become ready")

        if dry_run:
            logger.info("Dry run - skipping investigations")
            return result

        client = HTTPClient(f"http://localhost:{port}")

        try:
            # Warmup runs
            logger.info(f"Running {warmup_runs} warmup investigations...")
            for i in range(warmup_runs):
                logger.info(f"  Warmup {i+1}/{warmup_runs}")
                run_investigation(client, timeout)

            # Timed runs
            logger.info(f"Running {num_runs} timed investigations...")
            for i in range(num_runs):
                logger.info(f"  Run {i+1}/{num_runs}")
                run_result = run_investigation(client, timeout)
                result.runs.append(run_result)
                logger.info(f"    Duration: {run_result.duration_seconds:.2f}s, Status: {run_result.status}")

                # Restart server between runs if requested (to isolate process vs DB issues)
                if restart_between_runs and i < num_runs - 1:
                    logger.info("  Restarting server for next run...")
                    client.close()
                    server.stop()
                    time.sleep(2)  # Brief pause for cleanup
                    server.start()
                    if not server.wait_for_ready():
                        raise RuntimeError("Server failed to restart")
                    client = HTTPClient(f"http://localhost:{port}")

        finally:
            client.close()

        # Calculate stats
        result.stats = calculate_stats(result.runs)

    finally:
        server.stop()
        cleanup_worktree(worktree_path, repo_root, is_worktree)

    return result


def run_benchmark(
    branches: list[str],
    num_runs: int,
    warmup_runs: int,
    timeout: int,
    output_dir: Path,
    dry_run: bool = False,
    verbose: bool = False,
    restart_between_runs: bool = False,
    keep_infra: bool = False,
) -> BenchmarkResults:
    """Run the complete benchmark."""
    repo_root = get_repo_root()

    results = BenchmarkResults(
        timestamp=datetime.now(timezone.utc).isoformat(),
        machine=platform.node(),
        config={
            "runs": num_runs,
            "warmup": warmup_runs,
            "timeout": timeout,
            "branches": branches,
        },
    )

    # Start Docker infrastructure
    start_docker_infrastructure()

    try:
        for branch in branches:
            branch_result = run_benchmark_for_branch(
                branch=branch,
                repo_root=repo_root,
                num_runs=num_runs,
                warmup_runs=warmup_runs,
                timeout=timeout,
                dry_run=dry_run,
                verbose=verbose,
                restart_between_runs=restart_between_runs,
            )
            results.branches[branch] = branch_result

        # Calculate comparison if we have two branches
        if len(branches) == 2 and not dry_run:
            b1, b2 = branches
            stats1 = results.branches[b1].stats
            stats2 = results.branches[b2].stats

            if stats1 and stats2 and stats1.mean > 0 and stats2.mean > 0:
                delta = stats1.mean - stats2.mean
                delta_pct = (delta / stats2.mean) * 100

                results.comparison = {
                    "delta_mean_seconds": delta,
                    "delta_mean_percent": delta_pct,
                    "faster_branch": b1 if delta < 0 else b2,
                }

    finally:
        if keep_infra:
            logger.info("Keeping Docker infrastructure running (--keep-infra)")
            logger.info("  Temporal UI: http://localhost:8233")
            logger.info("  Jaeger UI: http://localhost:16686")
            logger.info("  To stop: docker rm -f dataing-demo-postgres dataing-demo-temporal dataing-demo-jaeger")
        else:
            stop_docker_infrastructure()

    return results


# ============================================================================
# Output
# ============================================================================


def save_results(results: BenchmarkResults, output_dir: Path) -> None:
    """Save results to JSON and Markdown files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Convert to dict for JSON serialization
    def to_dict(obj: Any) -> Any:
        if hasattr(obj, "__dict__"):
            return {k: to_dict(v) for k, v in asdict(obj).items()}
        elif isinstance(obj, list):
            return [to_dict(v) for v in obj]
        elif isinstance(obj, dict):
            return {k: to_dict(v) for k, v in obj.items()}
        return obj

    results_dict = to_dict(results)

    # Save JSON
    json_path = output_dir / "results.json"
    with open(json_path, "w") as f:
        json.dump(results_dict, f, indent=2)
    logger.info(f"Results saved to {json_path}")

    # Save Markdown
    md_path = output_dir / "results.md"
    with open(md_path, "w") as f:
        f.write(f"# Performance Benchmark Results\n\n")
        f.write(f"**Timestamp:** {results.timestamp}\n")
        f.write(f"**Machine:** {results.machine}\n")
        f.write(f"**Config:** {results.config['runs']} runs, {results.config['warmup']} warmup, {results.config['timeout']}s timeout\n\n")

        f.write("## Results\n\n")
        f.write("| Branch | SHA | Mean | Median | P95 | Stdev | Min | Max |\n")
        f.write("|--------|-----|------|--------|-----|-------|-----|-----|\n")

        for branch, br in results.branches.items():
            if br.stats:
                f.write(
                    f"| {branch} | {br.git_sha} | {br.stats.mean:.2f}s | {br.stats.median:.2f}s | "
                    f"{br.stats.p95:.2f}s | {br.stats.stdev:.2f}s | {br.stats.min_val:.2f}s | {br.stats.max_val:.2f}s |\n"
                )

        if results.comparison:
            f.write(f"\n**Delta:** {results.comparison['faster_branch']} is ")
            f.write(f"{abs(results.comparison['delta_mean_seconds']):.2f}s ")
            f.write(f"({abs(results.comparison['delta_mean_percent']):.1f}%) ")
            f.write(f"faster\n")

    logger.info(f"Results saved to {md_path}")


def print_summary(results: BenchmarkResults) -> None:
    """Print summary to console."""
    print("\n" + "=" * 60)
    print("  PERFORMANCE BENCHMARK RESULTS")
    print("=" * 60 + "\n")

    for branch, br in results.branches.items():
        print(f"{branch} ({br.git_sha}):")
        if br.stats:
            print(f"  Mean:   {br.stats.mean:.2f}s")
            print(f"  Median: {br.stats.median:.2f}s")
            print(f"  P95:    {br.stats.p95:.2f}s")
            print(f"  Stdev:  {br.stats.stdev:.2f}s")
            print(f"  Range:  {br.stats.min_val:.2f}s - {br.stats.max_val:.2f}s")
        else:
            print("  No successful runs")
        print()

    if results.comparison:
        faster = results.comparison["faster_branch"]
        delta_s = abs(results.comparison["delta_mean_seconds"])
        delta_pct = abs(results.comparison["delta_mean_percent"])
        print(f"Delta: {faster} is {delta_s:.2f}s ({delta_pct:.1f}%) FASTER")

    print("=" * 60 + "\n")


# ============================================================================
# Main
# ============================================================================


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Performance benchmark comparing investigation runtime between branches"
    )
    parser.add_argument(
        "--branches",
        nargs="+",
        default=DEFAULT_BRANCHES,
        help=f"Branches to compare (default: {DEFAULT_BRANCHES})",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=DEFAULT_NUM_RUNS,
        help=f"Number of timed runs per branch (default: {DEFAULT_NUM_RUNS})",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=DEFAULT_WARMUP_RUNS,
        help=f"Number of warmup runs per branch (default: {DEFAULT_WARMUP_RUNS})",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Timeout per investigation in seconds (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tests/performance"),
        help="Output directory for results (default: tests/performance)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Setup only, don't run investigations",
    )
    parser.add_argument(
        "--restart-between-runs",
        action="store_true",
        help="Restart server between each investigation (isolates process vs DB issues)",
    )
    parser.add_argument(
        "--keep-infra",
        action="store_true",
        help="Keep Docker containers running after benchmark (for Temporal UI analysis)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Handle SIGINT gracefully
    def signal_handler(sig: int, frame: Any) -> None:
        logger.info("\nInterrupted, cleaning up...")
        stop_docker_infrastructure()
        sys.exit(1)

    signal.signal(signal.SIGINT, signal_handler)

    logger.info(f"Starting benchmark: {args.branches}")
    logger.info(f"Config: {args.runs} runs, {args.warmup} warmup, {args.timeout}s timeout")

    try:
        results = run_benchmark(
            branches=args.branches,
            num_runs=args.runs,
            warmup_runs=args.warmup,
            timeout=args.timeout,
            output_dir=args.output_dir,
            dry_run=args.dry_run,
            verbose=args.verbose,
            restart_between_runs=args.restart_between_runs,
            keep_infra=args.keep_infra,
        )

        if not args.dry_run:
            save_results(results, args.output_dir)
            print_summary(results)

        return 0

    except Exception as e:
        logger.exception(f"Benchmark failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
