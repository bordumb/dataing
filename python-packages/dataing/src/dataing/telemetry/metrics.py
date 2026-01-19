"""Pre-registered metrics instruments for SLO monitoring.

Instruments are created once at startup, not per-job.
Metrics are pushed to OTEL Collector via OTLP - no local Prometheus server.

Usage:
    from dataing.telemetry.metrics import init_metrics, record_queue_wait_time

    # At startup
    init_metrics()

    # During execution
    record_queue_wait_time(0.5)
"""

from opentelemetry.metrics import Counter, Histogram

from dataing.telemetry.config import get_meter

# Module-level instruments (created once at startup)
_investigation_e2e_duration: Histogram | None = None
_investigation_queue_wait: Histogram | None = None
_investigation_worker_duration: Histogram | None = None
_investigation_step_duration: Histogram | None = None
_investigation_total: Counter | None = None

_initialized = False


def init_metrics() -> None:
    """Initialize metric instruments. Call once at startup.

    Safe to call multiple times - subsequent calls are no-ops.
    """
    global _investigation_e2e_duration, _investigation_queue_wait
    global _investigation_worker_duration, _investigation_step_duration
    global _investigation_total, _initialized

    if _initialized:
        return

    meter = get_meter("dataing")

    _investigation_e2e_duration = meter.create_histogram(
        name="investigation_e2e_duration_seconds",
        description="End-to-end investigation duration (API to completion)",
        unit="s",
    )

    _investigation_queue_wait = meter.create_histogram(
        name="investigation_queue_wait_seconds",
        description="Time spent waiting in queue",
        unit="s",
    )

    _investigation_worker_duration = meter.create_histogram(
        name="investigation_worker_duration_seconds",
        description="Worker processing duration",
        unit="s",
    )

    _investigation_step_duration = meter.create_histogram(
        name="investigation_step_duration_seconds",
        description="Duration of individual workflow steps",
        unit="s",
    )

    _investigation_total = meter.create_counter(
        name="investigation_total",
        description="Total investigations processed",
    )

    _initialized = True


def reset_metrics() -> None:
    """Reset metrics state (for testing)."""
    global _investigation_e2e_duration, _investigation_queue_wait
    global _investigation_worker_duration, _investigation_step_duration
    global _investigation_total, _initialized

    _investigation_e2e_duration = None
    _investigation_queue_wait = None
    _investigation_worker_duration = None
    _investigation_step_duration = None
    _investigation_total = None
    _initialized = False


def is_metrics_initialized() -> bool:
    """Check if metrics have been initialized."""
    return _initialized


def record_investigation_duration(duration_seconds: float, status: str) -> None:
    """Record E2E investigation duration.

    Args:
        duration_seconds: Total duration from API request to completion.
        status: Investigation outcome (completed, failed, cancelled).
    """
    if _investigation_e2e_duration:
        # LOW CARDINALITY: status only (completed, failed, cancelled)
        _investigation_e2e_duration.record(duration_seconds, {"status": status})


def record_queue_wait_time(duration_seconds: float) -> None:
    """Record time spent waiting in queue.

    Args:
        duration_seconds: Time from enqueue to worker pickup.
    """
    if _investigation_queue_wait:
        # NO LABELS - just the duration
        _investigation_queue_wait.record(duration_seconds)


def record_worker_duration(duration_seconds: float, status: str) -> None:
    """Record worker processing duration.

    Args:
        duration_seconds: Time spent processing in worker.
        status: Investigation outcome (completed, failed, cancelled).
    """
    if _investigation_worker_duration:
        _investigation_worker_duration.record(duration_seconds, {"status": status})


def record_step_duration(step_name: str, duration_seconds: float) -> None:
    """Record workflow step duration.

    Args:
        step_name: Step identifier from StepType enum.
        duration_seconds: Time spent executing the step.
    """
    if _investigation_step_duration:
        # step_name is from StepType enum - bounded cardinality
        _investigation_step_duration.record(duration_seconds, {"step": step_name})


def record_investigation_completed(status: str) -> None:
    """Increment investigation counter.

    Args:
        status: Investigation outcome (completed, failed, cancelled).
    """
    if _investigation_total:
        _investigation_total.add(1, {"status": status})
