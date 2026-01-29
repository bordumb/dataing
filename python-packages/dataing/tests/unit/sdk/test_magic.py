"""Unit tests for SDK magic commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

# Check if IPython is available for full testing
try:
    import IPython  # noqa: F401

    IPYTHON_AVAILABLE = True
except ImportError:
    IPYTHON_AVAILABLE = False

from dataing.sdk.magic import (
    DataingMagics,
    _fetch_snapshot,
    _get_api_client,
    _list_investigations,
)


class TestGetApiClient:
    """Tests for _get_api_client function."""

    def test_raises_when_not_connected(self) -> None:
        """Test error when DATAING_API_URL not set."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(RuntimeError, match="Not connected"):
                _get_api_client()

    def test_returns_url_and_headers(self) -> None:
        """Test returns correct URL and headers."""
        with patch.dict(
            "os.environ",
            {"DATAING_API_URL": "http://localhost:8000", "DATAING_API_KEY": "test-key"},
        ):
            base_url, headers = _get_api_client()
            assert base_url == "http://localhost:8000"
            assert headers["X-API-Key"] == "test-key"

    def test_strips_trailing_slash(self) -> None:
        """Test trailing slash is removed from URL."""
        with patch.dict(
            "os.environ",
            {"DATAING_API_URL": "http://localhost:8000/"},
        ):
            base_url, _ = _get_api_client()
            assert base_url == "http://localhost:8000"


class TestFetchSnapshot:
    """Tests for _fetch_snapshot function."""

    @patch("dataing.sdk.magic._get_api_client")
    @patch("urllib.request.urlopen")
    def test_fetch_success(self, mock_urlopen: MagicMock, mock_get_client: MagicMock) -> None:
        """Test successful snapshot fetch."""
        mock_get_client.return_value = ("http://localhost:8000", {"X-API-Key": "key"})
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"version": "1.0"}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = _fetch_snapshot("abc-123", "complete")
        assert result == b'{"version": "1.0"}'

    @patch("dataing.sdk.magic._get_api_client")
    @patch("urllib.request.urlopen")
    def test_fetch_404(self, mock_urlopen: MagicMock, mock_get_client: MagicMock) -> None:
        """Test 404 error handling."""
        import urllib.error

        mock_get_client.return_value = ("http://localhost:8000", {})
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            404,
            "Not Found",
            {},
            None,  # type: ignore[arg-type]
        )

        with pytest.raises(RuntimeError, match="Snapshot not found"):
            _fetch_snapshot("abc-123", "complete")


class TestListInvestigations:
    """Tests for _list_investigations function."""

    @patch("dataing.sdk.magic._get_api_client")
    @patch("urllib.request.urlopen")
    def test_list_success(self, mock_urlopen: MagicMock, mock_get_client: MagicMock) -> None:
        """Test successful investigation listing."""
        mock_get_client.return_value = ("http://localhost:8000", {})
        investigations = [
            {"investigation_id": str(uuid4()), "status": "complete"},
            {"investigation_id": str(uuid4()), "status": "running"},
        ]
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(investigations).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = _list_investigations(limit=10)
        assert len(result) == 2

    @patch("dataing.sdk.magic._get_api_client")
    @patch("urllib.request.urlopen")
    def test_list_respects_limit(self, mock_urlopen: MagicMock, mock_get_client: MagicMock) -> None:
        """Test limit parameter is respected."""
        mock_get_client.return_value = ("http://localhost:8000", {})
        investigations = [{"id": i} for i in range(20)]
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(investigations).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = _list_investigations(limit=5)
        assert len(result) == 5


@pytest.mark.skipif(not IPYTHON_AVAILABLE, reason="IPython not installed")
class TestDataingMagics:
    """Tests for DataingMagics class."""

    @pytest.fixture
    def magics(self) -> DataingMagics:
        """Create DataingMagics instance with mock shell."""
        mock_shell = MagicMock()
        mock_shell.user_ns = {}
        # Create instance without shell to avoid traitlets validation error,
        # then manually set shell attribute
        m = DataingMagics(shell=None)
        m.shell = mock_shell
        return m

    def test_hydrate_requires_investigation_id(
        self, magics: DataingMagics, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test hydrate command requires investigation ID."""
        magics.dataing("hydrate")
        captured = capsys.readouterr()
        assert "investigation_id required" in captured.out

    def test_hydrate_validates_uuid_format(
        self, magics: DataingMagics, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test hydrate validates UUID format."""
        magics.dataing("hydrate invalid-id")
        captured = capsys.readouterr()
        assert "Invalid investigation ID format" in captured.out

    @patch("dataing.sdk.magic._fetch_snapshot")
    @patch("dataing.sdk.snapshot.load_snapshot")
    def test_hydrate_success(
        self,
        mock_load: MagicMock,
        mock_fetch: MagicMock,
        magics: DataingMagics,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test successful hydration."""
        mock_fetch.return_value = b'{"version": "1.0"}'

        # Create mock state
        mock_state = MagicMock()
        mock_state.checkpoint = "complete"
        mock_state.hypotheses = [{"id": "h1"}]
        mock_state.evidence = [{"id": "e1"}]
        mock_state.synthesis = {"root_cause": "Test", "confidence": 0.9}
        mock_state.alert = {"dataset_id": "orders"}
        mock_state.schema = MagicMock()
        mock_state.lineage = None
        mock_state.dataframes = MagicMock()
        mock_state.dataframes.keys.return_value = ["orders"]
        mock_state.dataframes.get.return_value = None
        mock_load.return_value = mock_state

        inv_id = str(uuid4())
        magics.dataing(f"hydrate {inv_id}")

        captured = capsys.readouterr()
        assert "Hydrated investigation" in captured.out
        assert "dataing_alert" in captured.out

        # Check variables were injected
        assert "dataing_alert" in magics.shell.user_ns
        assert "dataing_hypotheses" in magics.shell.user_ns

    @patch("dataing.sdk.magic._fetch_snapshot")
    def test_hydrate_handles_fetch_error(
        self,
        mock_fetch: MagicMock,
        magics: DataingMagics,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test hydrate handles fetch errors."""
        mock_fetch.side_effect = RuntimeError("Connection failed")

        inv_id = str(uuid4())
        magics.dataing(f"hydrate {inv_id}")

        captured = capsys.readouterr()
        assert "Error: Connection failed" in captured.out

    @patch("dataing.sdk.magic._list_investigations")
    def test_list_command(
        self,
        mock_list: MagicMock,
        magics: DataingMagics,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test list command."""
        mock_list.return_value = [
            {
                "investigation_id": str(uuid4()),
                "status": "complete",
                "created_at": "2024-01-01T00:00:00",
                "dataset_id": "orders",
            }
        ]

        magics.dataing("list")

        captured = capsys.readouterr()
        assert "Recent investigations" in captured.out
        assert "complete" in captured.out

    def test_help_command(self, magics: DataingMagics, capsys: pytest.CaptureFixture[str]) -> None:
        """Test help command."""
        magics.dataing("help")

        captured = capsys.readouterr()
        assert "Dataing Magic Commands" in captured.out
        assert "%dataing hydrate" in captured.out

    def test_unknown_command(
        self, magics: DataingMagics, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test unknown command."""
        magics.dataing("unknown")

        captured = capsys.readouterr()
        assert "Unknown command" in captured.out

    @patch("dataing.sdk.magic._fetch_snapshot")
    @patch("dataing.sdk.snapshot.load_snapshot")
    def test_hydrate_with_namespace(
        self,
        mock_load: MagicMock,
        mock_fetch: MagicMock,
        magics: DataingMagics,
    ) -> None:
        """Test hydrate with custom namespace."""
        mock_fetch.return_value = b'{"version": "1.0"}'
        mock_state = MagicMock()
        mock_state.checkpoint = "complete"
        mock_state.hypotheses = []
        mock_state.evidence = []
        mock_state.synthesis = None
        mock_state.alert = None
        mock_state.schema = None
        mock_state.lineage = None
        mock_state.dataframes = MagicMock()
        mock_state.dataframes.keys.return_value = []
        mock_load.return_value = mock_state

        inv_id = str(uuid4())
        magics.dataing(f"hydrate {inv_id} --namespace myns")

        assert "myns_alert" in magics.shell.user_ns
        assert "myns_hypotheses" in magics.shell.user_ns

    @patch("dataing.sdk.magic._fetch_snapshot")
    @patch("dataing.sdk.snapshot.load_snapshot")
    def test_hydrate_warns_about_existing_vars(
        self,
        mock_load: MagicMock,
        mock_fetch: MagicMock,
        magics: DataingMagics,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test hydrate warns about existing variables."""
        mock_fetch.return_value = b'{"version": "1.0"}'
        mock_state = MagicMock()
        mock_state.checkpoint = "complete"
        mock_state.hypotheses = []
        mock_state.evidence = []
        mock_state.synthesis = None
        mock_state.alert = None
        mock_state.schema = None
        mock_state.lineage = None
        mock_state.dataframes = MagicMock()
        mock_state.dataframes.keys.return_value = []
        mock_load.return_value = mock_state

        # Pre-populate variable
        magics.shell.user_ns["dataing_alert"] = "existing"

        inv_id = str(uuid4())
        magics.dataing(f"hydrate {inv_id}")

        captured = capsys.readouterr()
        assert "already exist" in captured.out
        assert "dataing_alert" in captured.out

    @patch("dataing.sdk.magic._fetch_snapshot")
    @patch("dataing.sdk.snapshot.load_snapshot")
    def test_hydrate_with_overwrite(
        self,
        mock_load: MagicMock,
        mock_fetch: MagicMock,
        magics: DataingMagics,
    ) -> None:
        """Test hydrate with --overwrite flag."""
        mock_fetch.return_value = b'{"version": "1.0"}'
        mock_state = MagicMock()
        mock_state.checkpoint = "complete"
        mock_state.hypotheses = ["new"]
        mock_state.evidence = []
        mock_state.synthesis = None
        mock_state.alert = {"new": True}
        mock_state.schema = None
        mock_state.lineage = None
        mock_state.dataframes = MagicMock()
        mock_state.dataframes.keys.return_value = []
        mock_load.return_value = mock_state

        # Pre-populate variable
        magics.shell.user_ns["dataing_alert"] = "existing"

        inv_id = str(uuid4())
        magics.dataing(f"hydrate {inv_id} --overwrite")

        # Should have been overwritten
        assert magics.shell.user_ns["dataing_alert"] == {"new": True}


class TestExtensionLoading:
    """Tests for IPython extension loading."""

    def test_load_extension(self) -> None:
        """Test extension can be loaded."""
        from dataing.sdk.magic import load_ipython_extension

        mock_ipython = MagicMock()
        load_ipython_extension(mock_ipython)
        mock_ipython.register_magics.assert_called_once()

    def test_unload_extension(self) -> None:
        """Test extension can be unloaded."""
        from dataing.sdk.magic import unload_ipython_extension

        mock_ipython = MagicMock()
        # Should not raise
        unload_ipython_extension(mock_ipython)
