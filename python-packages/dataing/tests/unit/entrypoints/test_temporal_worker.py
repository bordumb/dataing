"""Tests for the Temporal worker entrypoint."""

import json
import re
import uuid

import pytest
import structlog

from dataing.entrypoints import temporal_worker

# SGR color codes that ConsoleRenderer and Rich put around each field.
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def build_adapter(encryption_key: str) -> None:
    """Fail with a secret held in a frame local, like get_adapter() does."""
    raise RuntimeError("adapter construction failed")


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

        async def fake_run_worker() -> None:
            try:
                build_adapter(secret)
            except RuntimeError:
                structlog.get_logger(__name__).exception("adapter_failed")

        # The real run_worker() needs a Temporal server; main() still does its own setup.
        monkeypatch.setattr(temporal_worker, "run_worker", fake_run_worker)
        temporal_worker.main()

        output = capsys.readouterr().out
        assert "adapter_failed" in output
        assert "adapter construction failed" in output
        assert secret not in output

    @pytest.mark.parametrize("log_format", ["console", "json"])
    def test_worker_failure_is_logged_once_without_frame_locals(
        self,
        log_format: str,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """main() logs a crashed worker once, via its stdlib logger, with no frame locals."""
        secret = f"secret-{uuid.uuid4().hex[:12]}"
        monkeypatch.setenv("LOG_FORMAT", log_format)
        monkeypatch.setenv("COLUMNS", "200")

        async def fake_run_worker() -> None:
            build_adapter(secret)

        monkeypatch.setattr(temporal_worker, "run_worker", fake_run_worker)
        # Exiting instead of re-raising keeps the interpreter from printing the traceback
        # a second time, unformatted, on stderr.
        with pytest.raises(SystemExit) as exit_info:
            temporal_worker.main()

        assert exit_info.value.code == 1
        output = ANSI_ESCAPE.sub("", capsys.readouterr().out)
        assert "Worker failed: adapter construction failed" in output
        assert output.count("Traceback (most recent call last)") == 1
        assert secret not in output

    def test_json_worker_failure_is_one_json_line(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With LOG_FORMAT=json, main()'s stdlib failure log is JSON, traceback included."""
        monkeypatch.setenv("LOG_FORMAT", "json")

        async def fake_run_worker() -> None:
            raise RuntimeError("temporal unreachable")

        monkeypatch.setattr(temporal_worker, "run_worker", fake_run_worker)
        with pytest.raises(SystemExit):
            temporal_worker.main()

        entry = json.loads(capsys.readouterr().out)
        assert entry["logger"] == "dataing.entrypoints.temporal_worker"
        assert entry["level"] == "error"
        assert entry["event"] == "Worker failed: temporal unreachable"
        assert entry["exception"].endswith("RuntimeError: temporal unreachable")
