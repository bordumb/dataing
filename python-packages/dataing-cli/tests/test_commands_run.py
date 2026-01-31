"""Tests for run commands."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from dataing_cli.main import app
from dataing_sdk import NotFoundError
from typer.testing import CliRunner

if TYPE_CHECKING:
    pass


class TestRunStartCommand:
    """Tests for run start command."""

    def test_run_start_success(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test run start creates an investigation."""
        mock_investigation = MagicMock()
        mock_investigation.investigation_id = "inv-xyz123"
        mock_investigation.run_id = "inv-xyz123"
        mock_investigation.model_dump.return_value = {"investigation_id": "inv-xyz123"}
        mock_client_patch.start_investigation.return_value = mock_investigation
        mock_client_patch.stream_run.return_value = iter([])

        result = runner.invoke(
            app,
            [
                "run",
                "start",
                "schema.table",
                "--anomaly-type",
                "null_rate",
                "--goal",
                "investigate null spike",
                "--no-watch",
            ],
        )

        assert result.exit_code == 0
        assert "Started investigation" in result.output
        assert "inv-xyz123" in result.output

    def test_run_start_with_datasource(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test run start with explicit datasource."""
        mock_investigation = MagicMock()
        mock_investigation.investigation_id = "inv-xyz123"
        mock_investigation.run_id = "inv-xyz123"
        mock_client_patch.start_investigation.return_value = mock_investigation
        mock_client_patch.stream_run.return_value = iter([])

        result = runner.invoke(
            app,
            [
                "run",
                "start",
                "schema.table",
                "--anomaly-type",
                "null_rate",
                "--goal",
                "test",
                "--datasource",
                "ds-custom",
                "--no-watch",
            ],
        )

        assert result.exit_code == 0
        # Verify start_investigation was called with correct datasource_id
        call_kwargs = mock_client_patch.start_investigation.call_args[1]
        assert call_kwargs["datasource_id"] == "ds-custom"

    def test_run_start_with_date(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test run start with --date flag passes anomaly_date to SDK."""
        mock_investigation = MagicMock()
        mock_investigation.investigation_id = "inv-xyz123"
        mock_investigation.run_id = "inv-xyz123"
        mock_client_patch.start_investigation.return_value = mock_investigation
        mock_client_patch.stream_run.return_value = iter([])

        result = runner.invoke(
            app,
            [
                "run",
                "start",
                "schema.table",
                "--anomaly-type",
                "null_rate",
                "--goal",
                "test",
                "--date",
                "2026-01-10",
                "--no-watch",
            ],
        )

        assert result.exit_code == 0
        # Verify start_investigation was called with correct anomaly_date
        call_kwargs = mock_client_patch.start_investigation.call_args[1]
        assert call_kwargs["anomaly_date"] == "2026-01-10"

    def test_run_start_no_datasource(
        self,
        runner: CliRunner,
        mock_config_dir: Path,
        mock_client_patch: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test run start fails when no datasource configured."""
        # Write minimal config without default datasource
        config_file = mock_config_dir / "config.toml"
        config_file.write_text('api_key = "test_key"\n')
        monkeypatch.setattr("dataing_cli.config._get_keyring_credential", lambda: None)

        result = runner.invoke(
            app,
            [
                "run",
                "start",
                "schema.table",
                "--anomaly-type",
                "null_rate",
                "--goal",
                "test",
            ],
        )

        assert result.exit_code == 1
        assert "No datasource" in result.output

    def test_run_start_json_output(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test run start with --json flag."""
        mock_investigation = MagicMock()
        mock_investigation.investigation_id = "inv-xyz123"
        mock_investigation.run_id = "inv-xyz123"
        mock_investigation.model_dump.return_value = {
            "investigation_id": "inv-xyz123",
            "status": "queued",
        }
        mock_client_patch.start_investigation.return_value = mock_investigation

        result = runner.invoke(
            app,
            [
                "--json",
                "run",
                "start",
                "schema.table",
                "--anomaly-type",
                "null_rate",
                "--goal",
                "test",
            ],
        )

        assert result.exit_code == 0
        # Should contain investigation ID in output
        assert "inv-xyz123" in result.output


class TestRunWatchCommand:
    """Tests for run watch command."""

    def test_run_watch_success(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test run watch streams events."""
        # Create mock events
        completed_event = MagicMock()
        completed_event.event = "run_completed"
        completed_event.data = {"root_cause": "Test root cause", "confidence": 0.85}
        completed_event.is_terminal = True

        mock_client_patch.stream_run.return_value = iter([completed_event])

        result = runner.invoke(app, ["run", "watch", "run-123"])

        assert result.exit_code == 0
        # Accept either Rich format or plain text format (non-TTY)
        assert (
            "Root Cause" in result.output
            or "Synthesis" in result.output
            or "run_completed" in result.output
        )

    def test_run_watch_with_evidence(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test run watch displays evidence events."""
        evidence_event = MagicMock()
        evidence_event.event = "run_evidence"
        evidence_event.data = {
            "hypothesis": "Test hypothesis",
            "query": "SELECT * FROM test",
            "interpretation": "Test finding",
        }
        evidence_event.is_terminal = False

        completed_event = MagicMock()
        completed_event.event = "run_completed"
        completed_event.data = {"root_cause": "Test", "confidence": 0.9}
        completed_event.is_terminal = True

        mock_client_patch.stream_run.return_value = iter([evidence_event, completed_event])

        result = runner.invoke(app, ["run", "watch", "run-123"])

        assert result.exit_code == 0

    def test_run_watch_failed(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test run watch handles failed run."""
        failed_event = MagicMock()
        failed_event.event = "run_failed"
        failed_event.data = {"error": "Investigation failed"}
        failed_event.is_terminal = True

        mock_client_patch.stream_run.return_value = iter([failed_event])

        result = runner.invoke(app, ["run", "watch", "run-123"])

        assert result.exit_code == 1
        assert "Failed" in result.output or "failed" in result.output

    def test_run_watch_json_output(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test run watch with --json flag."""
        started_event = MagicMock()
        started_event.event = "run_started"
        started_event.data = {"message": "Started"}
        started_event.is_terminal = False
        started_event.model_dump.return_value = {
            "event": "run_started",
            "data": {"message": "Started"},
        }

        completed_event = MagicMock()
        completed_event.event = "run_completed"
        completed_event.data = {"root_cause": "Test", "confidence": 0.9}
        completed_event.is_terminal = True
        completed_event.model_dump.return_value = {
            "event": "run_completed",
            "data": {"root_cause": "Test", "confidence": 0.9},
        }

        mock_client_patch.stream_run.return_value = iter([started_event, completed_event])

        result = runner.invoke(app, ["--json", "run", "watch", "run-123"])

        assert result.exit_code == 0
        # Output should contain JSON
        assert "run_completed" in result.output


class TestRunProgressEvents:
    """Tests for progress event handling."""

    def test_progress_events_are_handled(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test progress events are handled without error."""
        progress_event = MagicMock()
        progress_event.event = "run_progress"
        progress_event.data = {"message": "Gathering context..."}
        progress_event.is_terminal = False

        completed_event = MagicMock()
        completed_event.event = "run_completed"
        completed_event.data = {"root_cause": "Test", "confidence": 0.9}
        completed_event.is_terminal = True

        mock_client_patch.stream_run.return_value = iter([progress_event, completed_event])

        result = runner.invoke(app, ["run", "watch", "run-123"])

        assert result.exit_code == 0

    def test_hypothesis_testing_events(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test hypothesis testing events are handled."""
        hypothesis_event = MagicMock()
        hypothesis_event.event = "hypothesis_testing"
        hypothesis_event.data = {"message": "Testing hypothesis..."}
        hypothesis_event.is_terminal = False

        completed_event = MagicMock()
        completed_event.event = "run_completed"
        completed_event.data = {"root_cause": "Test", "confidence": 0.9}
        completed_event.is_terminal = True

        mock_client_patch.stream_run.return_value = iter([hypothesis_event, completed_event])

        result = runner.invoke(app, ["run", "watch", "run-123"])

        assert result.exit_code == 0

    def test_run_started_event(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test run_started event is handled."""
        started_event = MagicMock()
        started_event.event = "run_started"
        started_event.data = {}
        started_event.is_terminal = False

        completed_event = MagicMock()
        completed_event.event = "run_completed"
        completed_event.data = {"root_cause": "Test", "confidence": 0.9}
        completed_event.is_terminal = True

        mock_client_patch.stream_run.return_value = iter([started_event, completed_event])

        result = runner.invoke(app, ["run", "watch", "run-123"])

        assert result.exit_code == 0


class TestRunExportCommand:
    """Tests for run export command."""

    @pytest.fixture
    def mock_investigation_state(self) -> MagicMock:
        """Create a mock InvestigationState with realistic data."""
        main_branch = MagicMock()
        main_branch.status = "completed"
        main_branch.current_step = "synthesis"
        main_branch.synthesis = {
            "root_cause": "Null values appeared due to upstream ETL failure",
            "confidence": 0.85,
            "recommendations": ["Fix upstream ETL", "Add data validation"],
        }
        main_branch.evidence = [
            {
                "kind": "query_result",
                "query": "SELECT COUNT(*) FROM orders WHERE user_id IS NULL",
                "interpretation": "Found 1500 null values",
                "supports_hypothesis": True,
                "confidence": 0.9,
            },
            {
                "kind": "hypothesis",
                "interpretation": "ETL job failed at 2AM",
                "supports_hypothesis": True,
                "confidence": 0.8,
            },
        ]

        investigation = MagicMock()
        investigation.investigation_id = "inv-xyz123"
        investigation.status = "completed"
        investigation.main_branch = main_branch
        return investigation

    def test_export_markdown_to_stdout(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        mock_investigation_state: MagicMock,
    ) -> None:
        """Test export outputs markdown to stdout by default."""
        mock_client_patch.get_investigation.return_value = mock_investigation_state

        result = runner.invoke(app, ["run", "export", "inv-xyz123"])

        assert result.exit_code == 0
        assert "# Investigation Report: inv-xyz123" in result.output
        assert "Null values appeared" in result.output

    def test_export_to_file(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        mock_investigation_state: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test export writes to file with --output."""
        mock_client_patch.get_investigation.return_value = mock_investigation_state
        output_file = tmp_path / "report.md"

        result = runner.invoke(app, ["run", "export", "inv-xyz123", "--output", str(output_file)])

        assert result.exit_code == 0
        assert "Report written to" in result.output
        assert output_file.exists()
        content = output_file.read_text()
        assert "# Investigation Report: inv-xyz123" in content

    def test_export_json_format(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        mock_investigation_state: MagicMock,
    ) -> None:
        """Test export outputs valid JSON with --format json."""
        mock_client_patch.get_investigation.return_value = mock_investigation_state

        result = runner.invoke(app, ["run", "export", "inv-xyz123", "--format", "json"])

        assert result.exit_code == 0
        # Verify it's valid JSON
        data = json.loads(result.output)
        assert data["investigation_id"] == "inv-xyz123"
        assert data["status"] == "completed"
        assert "root_hash" in data
        assert "main_branch" in data

    def test_export_not_found(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test export handles not found error with exit code 1."""
        mock_client_patch.get_investigation.side_effect = NotFoundError("Investigation not found")

        result = runner.invoke(app, ["run", "export", "inv-notfound"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "error" in result.output.lower()

    def test_export_in_progress_investigation(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test export handles in-progress investigation with partial data."""
        main_branch = MagicMock()
        main_branch.status = "running"
        main_branch.current_step = "hypothesis_testing"
        main_branch.synthesis = None
        main_branch.evidence = []

        investigation = MagicMock()
        investigation.investigation_id = "inv-running"
        investigation.status = "running"
        investigation.main_branch = main_branch

        mock_client_patch.get_investigation.return_value = investigation

        result = runner.invoke(app, ["run", "export", "inv-running"])

        assert result.exit_code == 0
        assert "RUNNING" in result.output
        assert "No root cause identified yet" in result.output

    def test_export_no_evidence(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test export handles investigation with no evidence."""
        main_branch = MagicMock()
        main_branch.status = "completed"
        main_branch.current_step = "synthesis"
        main_branch.synthesis = {"root_cause": "Unknown", "confidence": 0.5}
        main_branch.evidence = []

        investigation = MagicMock()
        investigation.investigation_id = "inv-noevidence"
        investigation.status = "completed"
        investigation.main_branch = main_branch

        mock_client_patch.get_investigation.return_value = investigation

        result = runner.invoke(app, ["run", "export", "inv-noevidence"])

        assert result.exit_code == 0
        assert "No evidence collected" in result.output

    def test_export_markdown_contains_sql_blocks(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        mock_investigation_state: MagicMock,
    ) -> None:
        """Test markdown export contains fenced SQL code blocks."""
        mock_client_patch.get_investigation.return_value = mock_investigation_state

        result = runner.invoke(app, ["run", "export", "inv-xyz123"])

        assert result.exit_code == 0
        assert "```sql" in result.output
        assert "SELECT COUNT(*)" in result.output
        assert "```" in result.output

    def test_export_root_hash_format(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        mock_investigation_state: MagicMock,
    ) -> None:
        """Test root hash appears in export when set on investigation."""
        mock_investigation_state.root_hash = "a" * 64
        mock_client_patch.get_investigation.return_value = mock_investigation_state

        # Test markdown format
        result = runner.invoke(app, ["run", "export", "inv-xyz123"])
        assert result.exit_code == 0
        hash_match = re.search(r"Root Hash.*`([a-f0-9]{64})`", result.output)
        assert hash_match is not None, "Root hash not found in markdown output"

        # Test JSON format
        result = runner.invoke(app, ["run", "export", "inv-xyz123", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["root_hash"] == "a" * 64

    def test_export_json_structure_matches_api(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        mock_investigation_state: MagicMock,
    ) -> None:
        """Test JSON structure matches InvestigationStateResponse schema."""
        mock_client_patch.get_investigation.return_value = mock_investigation_state

        result = runner.invoke(app, ["run", "export", "inv-xyz123", "--format", "json"])

        assert result.exit_code == 0
        data = json.loads(result.output)

        # Verify required fields from API schema
        assert "investigation_id" in data
        assert "status" in data
        assert "main_branch" in data
        assert "generated_at" in data
        assert "root_hash" in data

        # Verify main_branch structure
        main_branch = data["main_branch"]
        assert "status" in main_branch
        assert "synthesis" in main_branch
        assert "evidence" in main_branch


class TestRunVerifyCommand:
    """Tests for run verify command."""

    def test_verify_valid_chain(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test verify outputs success for valid chain."""
        mock_result = MagicMock()
        mock_result.chain_available = True
        mock_result.is_valid = True
        mock_result.evidence_count = 5
        mock_result.root_hash = "a" * 64
        mock_result.root_hash_matches = True
        mock_result.first_broken_seq = None
        mock_result.error = None
        mock_client_patch.verify_investigation.return_value = mock_result

        result = runner.invoke(app, ["run", "verify", "inv-xyz123"])

        assert result.exit_code == 0
        assert "Chain valid" in result.output
        assert "5 evidence items" in result.output
        assert "a" * 64 in result.output

    def test_verify_broken_chain(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test verify exits 1 for broken chain."""
        mock_result = MagicMock()
        mock_result.chain_available = True
        mock_result.is_valid = False
        mock_result.evidence_count = 3
        mock_result.root_hash = "b" * 64
        mock_result.root_hash_matches = False
        mock_result.first_broken_seq = 2
        mock_result.error = "Item seq=2 content_hash mismatch"
        mock_client_patch.verify_investigation.return_value = mock_result

        result = runner.invoke(app, ["run", "verify", "inv-xyz123"])

        assert result.exit_code == 1
        assert "Chain broken" in result.output
        assert "seq 2" in result.output
        assert "content_hash mismatch" in result.output

    def test_verify_chain_not_available(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test verify exits 2 when chain not available."""
        mock_result = MagicMock()
        mock_result.chain_available = False
        mock_result.is_valid = True
        mock_result.evidence_count = 10
        mock_result.root_hash = None
        mock_result.root_hash_matches = None
        mock_result.first_broken_seq = None
        mock_result.error = None
        mock_client_patch.verify_investigation.return_value = mock_result

        result = runner.invoke(app, ["run", "verify", "inv-xyz123"])

        assert result.exit_code == 2
        assert "not available" in result.output.lower()

    def test_verify_not_found(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test verify handles not found error."""
        mock_client_patch.verify_investigation.side_effect = NotFoundError(
            "Investigation not found"
        )

        result = runner.invoke(app, ["run", "verify", "inv-notfound"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "error" in result.output.lower()

    def test_verify_root_hash_mismatch(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test verify shows warning when root hash doesn't match stored value."""
        mock_result = MagicMock()
        mock_result.chain_available = True
        mock_result.is_valid = True
        mock_result.evidence_count = 5
        mock_result.root_hash = "c" * 64
        mock_result.root_hash_matches = False
        mock_result.first_broken_seq = None
        mock_result.error = None
        mock_client_patch.verify_investigation.return_value = mock_result

        result = runner.invoke(app, ["run", "verify", "inv-xyz123"])

        assert result.exit_code == 0
        assert "does not match" in result.output


class TestExportChainMetadata:
    """Tests for chain metadata in export output."""

    @pytest.fixture
    def mock_investigation_with_chain(self) -> MagicMock:
        """Create a mock investigation with chain data on evidence."""
        main_branch = MagicMock()
        main_branch.status = "completed"
        main_branch.current_step = "synthesis"
        main_branch.synthesis = {
            "root_cause": "ETL failure",
            "confidence": 0.9,
        }
        main_branch.evidence = [
            {
                "kind": "query_result",
                "query": "SELECT COUNT(*) FROM orders",
                "interpretation": "Found anomaly",
                "seq": 1,
                "content_hash": "a" * 64,
                "prev_hash": None,
            },
            {
                "kind": "hypothesis",
                "interpretation": "ETL job failed",
                "seq": 2,
                "content_hash": "b" * 64,
                "prev_hash": "a" * 64,
            },
        ]

        investigation = MagicMock()
        investigation.investigation_id = "inv-chain"
        investigation.status = "completed"
        investigation.root_hash = "b" * 64
        investigation.main_branch = main_branch
        return investigation

    def test_export_json_includes_chain_metadata(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        mock_investigation_with_chain: MagicMock,
    ) -> None:
        """Test JSON export includes chain_metadata when evidence has chain data."""
        mock_client_patch.get_investigation.return_value = mock_investigation_with_chain

        result = runner.invoke(app, ["run", "export", "inv-chain", "--format", "json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["root_hash"] == "b" * 64
        assert "chain_metadata" in data
        assert data["chain_metadata"]["hash_algorithm"] == "sha256"
        assert data["chain_metadata"]["canonicalization"] == "rfc8785"
        assert data["chain_metadata"]["chain_version"] == "evidence_v1"

    def test_export_json_per_item_chain_fields(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        mock_investigation_with_chain: MagicMock,
    ) -> None:
        """Test JSON export includes per-item content_hash, prev_hash, seq."""
        mock_client_patch.get_investigation.return_value = mock_investigation_with_chain

        result = runner.invoke(app, ["run", "export", "inv-chain", "--format", "json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        evidence = data["main_branch"]["evidence"]
        assert evidence[0]["seq"] == 1
        assert evidence[0]["content_hash"] == "a" * 64
        assert evidence[0]["prev_hash"] is None
        assert evidence[1]["seq"] == 2
        assert evidence[1]["prev_hash"] == "a" * 64

    def test_export_markdown_shows_chain_info(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        mock_investigation_with_chain: MagicMock,
    ) -> None:
        """Test markdown export shows chain metadata and per-item chain info."""
        mock_client_patch.get_investigation.return_value = mock_investigation_with_chain

        result = runner.invoke(app, ["run", "export", "inv-chain"])

        assert result.exit_code == 0
        assert "Root Hash" in result.output
        assert "sha256" in result.output
        assert "rfc8785" in result.output
        assert "seq=" in result.output

    def test_export_json_no_chain_metadata_without_chain_data(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test JSON export omits chain_metadata when evidence lacks chain data."""
        main_branch = MagicMock()
        main_branch.status = "completed"
        main_branch.current_step = "synthesis"
        main_branch.synthesis = {"root_cause": "Test", "confidence": 0.5}
        main_branch.evidence = [
            {"kind": "query_result", "interpretation": "Found issue"},
        ]

        investigation = MagicMock()
        investigation.investigation_id = "inv-old"
        investigation.status = "completed"
        investigation.root_hash = None
        investigation.main_branch = main_branch

        mock_client_patch.get_investigation.return_value = investigation

        result = runner.invoke(app, ["run", "export", "inv-old", "--format", "json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["root_hash"] is None
        assert "chain_metadata" not in data


class TestRunSnapshotCommand:
    """Tests for run snapshot command."""

    def test_snapshot_success(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test snapshot downloads and saves archive."""
        # Return mock data
        mock_data = b"mock tar.gz content" * 1000  # ~19KB
        mock_client_patch.download_snapshot.return_value = mock_data

        output_file = tmp_path / "test-snapshot.tar.gz"
        result = runner.invoke(
            app,
            ["run", "snapshot", "inv-abc123", "--output", str(output_file)],
        )

        assert result.exit_code == 0
        assert "Snapshot saved" in result.output
        assert output_file.exists()
        assert output_file.read_bytes() == mock_data

    def test_snapshot_default_filename(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test snapshot uses default filename based on investigation ID."""
        mock_data = b"mock tar.gz content"
        mock_client_patch.download_snapshot.return_value = mock_data

        # Change to temp dir so default file is created there
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["run", "snapshot", "inv-xyz789"])

        assert result.exit_code == 0
        default_file = tmp_path / "snapshot-inv-xyz789.tar.gz"
        assert default_file.exists()

    def test_snapshot_max_size_exceeded(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test snapshot fails when size exceeds --max-size."""
        # Return 2MB of data
        mock_data = b"x" * (2 * 1024 * 1024)
        mock_client_patch.download_snapshot.return_value = mock_data

        output_file = tmp_path / "test-snapshot.tar.gz"
        result = runner.invoke(
            app,
            ["run", "snapshot", "inv-abc123", "--output", str(output_file), "--max-size", "1"],
        )

        assert result.exit_code == 1
        assert "exceeds" in result.output

    def test_snapshot_not_found(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test snapshot handles not found error."""
        mock_client_patch.download_snapshot.side_effect = NotFoundError("Investigation not found")

        result = runner.invoke(app, ["run", "snapshot", "inv-notfound"])

        assert result.exit_code == 1
        assert "Failed" in result.output or "not found" in result.output.lower()


class TestRunImportCommand:
    """Tests for run import command."""

    def test_import_success(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test import uploads and imports archive."""
        # Create a test file
        test_file = tmp_path / "test.tar.gz"
        test_file.write_bytes(b"mock archive content")

        mock_client_patch.import_snapshot.return_value = {
            "investigation_id": "new-inv-123",
            "original_investigation_id": "orig-inv-456",
            "evidence_count": 5,
            "status": "imported",
            "is_replay": True,
        }

        result = runner.invoke(app, ["run", "import", str(test_file)])

        assert result.exit_code == 0
        assert "Imported as" in result.output
        assert "new-inv-123" in result.output
        assert "orig-inv-456" in result.output
        assert "Evidence items: 5" in result.output

    def test_import_file_not_found(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test import fails when file not found."""
        result = runner.invoke(app, ["run", "import", str(tmp_path / "nonexistent.tar.gz")])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_import_api_error(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test import handles API errors."""
        test_file = tmp_path / "test.tar.gz"
        test_file.write_bytes(b"mock archive content")

        mock_client_patch.import_snapshot.side_effect = Exception("Invalid archive")

        result = runner.invoke(app, ["run", "import", str(test_file)])

        assert result.exit_code == 1
        assert "Failed" in result.output
