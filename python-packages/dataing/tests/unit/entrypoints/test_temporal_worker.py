"""Tests for the Temporal worker entrypoint."""

import logging
import sys
import uuid

import pytest
import structlog

from dataing.entrypoints import temporal_worker


class TestWorkerLogging:
    """Tests for the logging configured by the worker entrypoint."""

    def setup_method(self) -> None:
        """Reset structlog so the test covers main()'s own logging setup."""
        # Other tests may have built the API app in this process, and create_app()
        # configures structlog. The worker must not depend on that.
        structlog.reset_defaults()

    def teardown_method(self) -> None:
        """Reset structlog configuration after each test."""
        structlog.reset_defaults()

    @pytest.mark.parametrize("log_format", ["console", "json"])
    def test_structlog_exception_output_hides_frame_locals(
        self,
        log_format: str,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Worker-side structlog tracebacks do not render frame locals such as encryption keys."""
        # Generated at runtime so the value never appears in rendered source lines.
        secret = f"secret-{uuid.uuid4().hex[:12]}"
        monkeypatch.setenv("LOG_FORMAT", log_format)
        # Wide enough that a rendered secret is never wrapped across lines and missed.
        monkeypatch.setenv("COLUMNS", "200")

        def build_adapter(encryption_key: str) -> None:
            raise RuntimeError("adapter construction failed")

        async def fake_run_worker() -> None:
            try:
                build_adapter(secret)
            except RuntimeError:
                structlog.get_logger(__name__).exception("adapter_failed")

        # The real run_worker() needs a Temporal server; main() still does its own setup.
        monkeypatch.setattr(temporal_worker, "run_worker", fake_run_worker)
        # pytest's logging plugin pre-installs root handlers, which makes basicConfig() a
        # no-op here; attach the stdout handler that basicConfig() installs in production.
        stdlib_logger = logging.getLogger(__name__)
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdlib_logger.addHandler(stdout_handler)
        try:
            temporal_worker.main()
        finally:
            stdlib_logger.removeHandler(stdout_handler)

        output = capsys.readouterr().out
        assert "adapter_failed" in output
        assert "adapter construction failed" in output
        assert secret not in output
