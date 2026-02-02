"""Unit tests for Docker status tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dataing.agents.tools.docker import (
    ContainerStatus,
    ContainerSummary,
    DockerStatusResult,
    DockerStatusTool,
    _format_bytes,
    _format_ports,
    find_unhealthy_docker_containers,
    get_docker_container_status,
    list_docker_containers,
    register_docker_tools,
)
from dataing.agents.tools.registry import ToolCategory, ToolRegistry


class TestContainerDataclasses:
    """Tests for container dataclasses."""

    def test_container_status_create(self) -> None:
        """Test creating a ContainerStatus."""
        status = ContainerStatus(
            id="abc123",
            name="test-container",
            status="running",
            image="nginx:latest",
            created="2024-01-15T10:00:00Z",
            started="2024-01-15T10:00:01Z",
            ports={"80/tcp": [{"HostPort": "8080"}]},
            health={"Status": "healthy"},
        )

        assert status.id == "abc123"
        assert status.name == "test-container"
        assert status.status == "running"
        assert status.image == "nginx:latest"
        assert status.health["Status"] == "healthy"

    def test_container_status_minimal(self) -> None:
        """Test creating a minimal ContainerStatus."""
        status = ContainerStatus(
            id="xyz",
            name="minimal",
            status="exited",
            image="alpine",
        )

        assert status.id == "xyz"
        assert status.ports == {}
        assert status.health == {}
        assert status.error is None

    def test_container_summary(self) -> None:
        """Test creating a ContainerSummary."""
        summary = ContainerSummary(
            id="abc123",
            name="test-container",
            status="running",
            image="nginx:latest",
        )

        assert summary.id == "abc123"
        assert summary.name == "test-container"

    def test_docker_status_result_success(self) -> None:
        """Test successful DockerStatusResult."""
        result = DockerStatusResult(
            success=True,
            containers=[
                ContainerSummary(id="abc", name="container1", status="running", image="nginx"),
            ],
        )

        assert result.success is True
        assert len(result.containers) == 1
        assert result.error is None

    def test_docker_status_result_error(self) -> None:
        """Test error DockerStatusResult."""
        result = DockerStatusResult(success=False, error="Docker not available")

        assert result.success is False
        assert result.error == "Docker not available"


class TestDockerStatusTool:
    """Tests for DockerStatusTool class."""

    @pytest.fixture
    def mock_docker_client(self) -> MagicMock:
        """Create a mock Docker client."""
        client = MagicMock()
        client.ping.return_value = True
        return client

    @pytest.fixture
    def mock_container(self) -> MagicMock:
        """Create a mock container."""
        container = MagicMock()
        container.short_id = "abc123"
        container.name = "test-container"
        container.status = "running"

        mock_image = MagicMock()
        mock_image.tags = ["nginx:latest"]
        container.image = mock_image

        container.attrs = {
            "Created": "2024-01-15T10:00:00Z",
            "State": {
                "StartedAt": "2024-01-15T10:00:01Z",
                "Health": {"Status": "healthy"},
            },
            "NetworkSettings": {
                "Ports": {"80/tcp": [{"HostPort": "8080"}]},
            },
        }
        return container

    @pytest.mark.asyncio
    async def test_list_containers_success(
        self, mock_docker_client: MagicMock, mock_container: MagicMock
    ) -> None:
        """Test listing containers successfully."""
        mock_docker_client.containers.list.return_value = [mock_container]

        tool = DockerStatusTool()
        tool._client = mock_docker_client

        result = await tool.list_containers()

        assert result.success is True
        assert len(result.containers) == 1
        assert result.containers[0].name == "test-container"
        assert result.containers[0].status == "running"

    @pytest.mark.asyncio
    async def test_list_containers_no_docker(self) -> None:
        """Test listing containers when Docker is not installed."""
        tool = DockerStatusTool()
        tool._client = None  # Reset client

        # Mock _get_client to raise ImportError
        with patch.object(tool, "_get_client") as mock_get:
            mock_get.side_effect = ImportError("docker package required")

            result = await tool.list_containers()

            assert result.success is False
            assert "docker package required" in result.error

    @pytest.mark.asyncio
    async def test_get_container_status_success(
        self, mock_docker_client: MagicMock, mock_container: MagicMock
    ) -> None:
        """Test getting container status successfully."""
        mock_docker_client.containers.get.return_value = mock_container

        tool = DockerStatusTool()
        tool._client = mock_docker_client

        result = await tool.get_container_status("test-container")

        assert result.success is True
        assert result.container is not None
        assert result.container.name == "test-container"
        assert result.container.status == "running"
        assert result.container.health["Status"] == "healthy"

    @pytest.mark.asyncio
    async def test_get_container_status_not_found(self, mock_docker_client: MagicMock) -> None:
        """Test getting status for non-existent container."""
        mock_docker_client.containers.get.side_effect = Exception("Container not found")

        tool = DockerStatusTool()
        tool._client = mock_docker_client

        result = await tool.get_container_status("nonexistent")

        assert result.success is False
        assert "Container not found" in result.error

    @pytest.mark.asyncio
    async def test_get_container_health_healthy(
        self, mock_docker_client: MagicMock, mock_container: MagicMock
    ) -> None:
        """Test getting health for a healthy container."""
        mock_docker_client.containers.get.return_value = mock_container

        tool = DockerStatusTool()
        tool._client = mock_docker_client

        health = await tool.get_container_health("test-container")

        assert health["healthy"] is True
        assert health["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_get_container_health_no_healthcheck(
        self, mock_docker_client: MagicMock, mock_container: MagicMock
    ) -> None:
        """Test getting health for container without health check."""
        mock_container.attrs["State"]["Health"] = {}
        mock_docker_client.containers.get.return_value = mock_container

        tool = DockerStatusTool()
        tool._client = mock_docker_client

        health = await tool.get_container_health("test-container")

        assert health["healthy"] is None
        assert "No health check configured" in health["message"]

    @pytest.mark.asyncio
    async def test_get_container_stats_success(
        self, mock_docker_client: MagicMock, mock_container: MagicMock
    ) -> None:
        """Test getting container stats."""
        mock_container.stats.return_value = {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 200000000},
                "system_cpu_usage": 1000000000,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 100000000},
                "system_cpu_usage": 500000000,
            },
            "memory_stats": {
                "usage": 50 * 1024 * 1024,  # 50 MB
                "limit": 512 * 1024 * 1024,  # 512 MB
            },
            "networks": {
                "eth0": {
                    "rx_bytes": 1000000,
                    "tx_bytes": 500000,
                },
            },
        }
        mock_docker_client.containers.get.return_value = mock_container

        tool = DockerStatusTool()
        tool._client = mock_docker_client

        stats = await tool.get_container_stats("test-container")

        assert "error" not in stats
        assert stats["memory_usage_mb"] == 50.0
        assert stats["memory_limit_mb"] == 512.0

    @pytest.mark.asyncio
    async def test_get_container_stats_not_running(
        self, mock_docker_client: MagicMock, mock_container: MagicMock
    ) -> None:
        """Test getting stats for non-running container."""
        mock_container.status = "exited"
        mock_docker_client.containers.get.return_value = mock_container

        tool = DockerStatusTool()
        tool._client = mock_docker_client

        stats = await tool.get_container_stats("test-container")

        assert "error" in stats
        assert "not running" in stats["error"]

    @pytest.mark.asyncio
    async def test_find_unhealthy_containers(self, mock_docker_client: MagicMock) -> None:
        """Test finding unhealthy containers."""
        # Create running healthy container
        healthy_container = MagicMock()
        healthy_container.short_id = "abc123"
        healthy_container.name = "healthy-container"
        healthy_container.status = "running"
        healthy_container.image = MagicMock()
        healthy_container.image.tags = ["nginx:latest"]
        healthy_container.attrs = {
            "State": {"Health": {"Status": "healthy"}},
            "NetworkSettings": {"Ports": {}},
        }

        # Create stopped container
        stopped_container = MagicMock()
        stopped_container.short_id = "def456"
        stopped_container.name = "stopped-container"
        stopped_container.status = "exited"
        stopped_container.image = MagicMock()
        stopped_container.image.tags = ["alpine"]
        stopped_container.attrs = {
            "State": {},
            "NetworkSettings": {"Ports": {}},
        }

        mock_docker_client.containers.list.return_value = [
            healthy_container,
            stopped_container,
        ]
        mock_docker_client.containers.get.return_value = healthy_container

        tool = DockerStatusTool()
        tool._client = mock_docker_client

        unhealthy = await tool.find_unhealthy_containers()

        assert len(unhealthy) == 1
        assert unhealthy[0]["name"] == "stopped-container"
        assert unhealthy[0]["reason"] == "not_running"


class TestToolFunctions:
    """Tests for tool functions."""

    @pytest.mark.asyncio
    async def test_list_docker_containers_formatted(self) -> None:
        """Test list_docker_containers returns formatted output."""
        mock_result = DockerStatusResult(
            success=True,
            containers=[
                ContainerSummary(id="abc", name="web", status="running", image="nginx"),
                ContainerSummary(id="def", name="db", status="exited", image="postgres"),
            ],
        )

        with patch.object(
            DockerStatusTool,
            "list_containers",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            # Reset the global tool
            import dataing.agents.tools.docker as docker_module

            docker_module._default_tool = DockerStatusTool()

            output = await list_docker_containers()

            assert "Docker Containers:" in output
            assert "web" in output
            assert "db" in output
            assert "🟢" in output  # Running indicator
            assert "🔴" in output  # Stopped indicator

    @pytest.mark.asyncio
    async def test_list_docker_containers_error(self) -> None:
        """Test list_docker_containers handles errors."""
        mock_result = DockerStatusResult(success=False, error="Connection refused")

        with patch.object(
            DockerStatusTool,
            "list_containers",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            import dataing.agents.tools.docker as docker_module

            docker_module._default_tool = DockerStatusTool()

            output = await list_docker_containers()

            assert "Error" in output
            assert "Connection refused" in output

    @pytest.mark.asyncio
    async def test_get_docker_container_status_formatted(self) -> None:
        """Test get_docker_container_status returns formatted output."""
        mock_result = DockerStatusResult(
            success=True,
            container=ContainerStatus(
                id="abc123",
                name="test-container",
                status="running",
                image="nginx:latest",
                created="2024-01-15T10:00:00Z",
                ports={"80/tcp": [{"HostPort": "8080"}]},
                health={"Status": "healthy"},
            ),
        )

        with patch.object(
            DockerStatusTool,
            "get_container_status",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            import dataing.agents.tools.docker as docker_module

            docker_module._default_tool = DockerStatusTool()

            output = await get_docker_container_status("test-container")

            assert "test-container" in output
            assert "running" in output
            assert "nginx:latest" in output
            assert "8080->80/tcp" in output

    @pytest.mark.asyncio
    async def test_find_unhealthy_docker_containers_all_healthy(self) -> None:
        """Test find_unhealthy_docker_containers when all healthy."""
        with patch.object(
            DockerStatusTool,
            "find_unhealthy_containers",
            new_callable=AsyncMock,
            return_value=[],
        ):
            import dataing.agents.tools.docker as docker_module

            docker_module._default_tool = DockerStatusTool()

            output = await find_unhealthy_docker_containers()

            assert "All containers are healthy" in output
            assert "✅" in output


class TestFormatHelpers:
    """Tests for format helper functions."""

    def test_format_ports_with_bindings(self) -> None:
        """Test formatting ports with host bindings."""
        ports = {
            "80/tcp": [{"HostPort": "8080"}],
            "443/tcp": [{"HostPort": "8443"}],
        }

        result = _format_ports(ports)

        assert "8080->80/tcp" in result
        assert "8443->443/tcp" in result

    def test_format_ports_no_bindings(self) -> None:
        """Test formatting ports without host bindings."""
        ports = {
            "80/tcp": None,
            "443/tcp": [],
        }

        result = _format_ports(ports)

        assert "80/tcp" in result
        assert "443/tcp" in result

    def test_format_ports_empty(self) -> None:
        """Test formatting empty ports."""
        assert _format_ports({}) == "none"

    def test_format_bytes_bytes(self) -> None:
        """Test formatting bytes."""
        assert _format_bytes(100) == "100.0 B"

    def test_format_bytes_kilobytes(self) -> None:
        """Test formatting kilobytes."""
        assert _format_bytes(1024) == "1.0 KB"

    def test_format_bytes_megabytes(self) -> None:
        """Test formatting megabytes."""
        assert _format_bytes(1024 * 1024) == "1.0 MB"

    def test_format_bytes_gigabytes(self) -> None:
        """Test formatting gigabytes."""
        assert _format_bytes(1024 * 1024 * 1024) == "1.0 GB"


class TestToolRegistration:
    """Tests for tool registration."""

    def test_register_docker_tools(self) -> None:
        """Test registering Docker tools with registry."""
        registry = ToolRegistry()

        register_docker_tools(registry)

        # Check tools are registered in the global registry
        tool_names = list(registry._tools.keys())
        assert "list_docker_containers" in tool_names
        assert "get_docker_container_status" in tool_names
        assert "get_docker_container_health" in tool_names
        assert "get_docker_container_stats" in tool_names
        assert "find_unhealthy_docker_containers" in tool_names

    def test_docker_tools_have_correct_category(self) -> None:
        """Test that Docker tools have correct category."""
        registry = ToolRegistry()

        register_docker_tools(registry)

        for tool_config in registry._tools.values():
            assert tool_config.category == ToolCategory.DOCKER
