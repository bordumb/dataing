"""Tests for metrics module."""

from dataing.telemetry.metrics import (
    init_metrics,
    is_metrics_initialized,
    record_investigation_completed,
    record_investigation_duration,
    record_queue_wait_time,
    record_step_duration,
    record_worker_duration,
    reset_metrics,
)


class TestMetricsInitialization:
    """Tests for metrics initialization."""

    def setup_method(self) -> None:
        """Reset metrics state before each test."""
        reset_metrics()

    def teardown_method(self) -> None:
        """Reset metrics state after each test."""
        reset_metrics()

    def test_init_metrics_sets_initialized_flag(self) -> None:
        """init_metrics sets the initialized flag."""
        assert not is_metrics_initialized()
        init_metrics()
        assert is_metrics_initialized()

    def test_init_metrics_is_idempotent(self) -> None:
        """Calling init_metrics multiple times is safe."""
        init_metrics()
        init_metrics()  # Should not raise
        assert is_metrics_initialized()

    def test_reset_metrics_clears_state(self) -> None:
        """reset_metrics clears all state."""
        init_metrics()
        assert is_metrics_initialized()
        reset_metrics()
        assert not is_metrics_initialized()


class TestRecordingFunctions:
    """Tests for metric recording functions."""

    def setup_method(self) -> None:
        """Reset and initialize metrics before each test."""
        reset_metrics()
        init_metrics()

    def teardown_method(self) -> None:
        """Reset metrics state after each test."""
        reset_metrics()

    def test_record_investigation_duration(self) -> None:
        """record_investigation_duration works without error."""
        record_investigation_duration(1.5, "completed")
        record_investigation_duration(2.0, "failed")
        record_investigation_duration(0.5, "cancelled")
        # Should not raise

    def test_record_queue_wait_time(self) -> None:
        """record_queue_wait_time works without error."""
        record_queue_wait_time(0.1)
        record_queue_wait_time(5.0)
        # Should not raise

    def test_record_worker_duration(self) -> None:
        """record_worker_duration works without error."""
        record_worker_duration(10.0, "completed")
        record_worker_duration(5.0, "failed")
        # Should not raise

    def test_record_step_duration(self) -> None:
        """record_step_duration works without error."""
        record_step_duration("gather_context", 0.5)
        record_step_duration("generate_hypotheses", 1.2)
        record_step_duration("execute_query", 0.3)
        # Should not raise

    def test_record_investigation_completed(self) -> None:
        """record_investigation_completed works without error."""
        record_investigation_completed("completed")
        record_investigation_completed("failed")
        record_investigation_completed("cancelled")
        # Should not raise


class TestRecordingWithoutInit:
    """Tests for recording when metrics not initialized."""

    def setup_method(self) -> None:
        """Ensure metrics are not initialized."""
        reset_metrics()

    def teardown_method(self) -> None:
        """Reset metrics state after each test."""
        reset_metrics()

    def test_recording_without_init_is_safe(self) -> None:
        """Recording without init_metrics is a no-op (no error)."""
        assert not is_metrics_initialized()

        # All these should be no-ops, not errors
        record_investigation_duration(1.0, "completed")
        record_queue_wait_time(0.5)
        record_worker_duration(1.0, "completed")
        record_step_duration("gather_context", 0.5)
        record_investigation_completed("completed")
        # Should not raise
