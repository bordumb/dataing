"""Docker status tool for the Dataing Assistant.

Provides tools to check Docker container status, health, and resource usage.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from dataing.agents.tools.registry import ToolCategory, ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class ContainerStatus:
    """Status information for a Docker container.

    Attributes:
        id: Container short ID.
        name: Container name.
        status: Container state (running, exited, etc.).
        image: Image name and tag.
        created: Creation timestamp.
        started: Start timestamp.
        ports: Port mappings.
        health: Health check status.
        error: Error message if status fetch failed.
    """

    id: str
    name: str
    status: str
    image: str
    created: str | None = None
    started: str | None = None
    ports: dict[str, Any] = field(default_factory=dict)
    health: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class ContainerSummary:
    """Summary of a container for listings.

    Attributes:
        id: Container short ID.
        name: Container name.
        status: Container state.
        image: Image name.
    """

    id: str
    name: str
    status: str
    image: str


@dataclass
class DockerStatusResult:
    """Result from Docker status operations.

    Attributes:
        success: Whether the operation succeeded.
        containers: List of container summaries.
        container: Single container status (for get_status).
        error: Error message if operation failed.
    """

    success: bool = True
    containers: list[ContainerSummary] = field(default_factory=list)
    container: ContainerStatus | None = None
    error: str | None = None


class DockerStatusTool:
    """Tool for checking Docker container status.

    Provides read-only access to Docker container information:
    - List all containers with status
    - Get detailed status for a specific container
    - Check container health
    - Get container resource usage
    """

    def __init__(self, docker_host: str | None = None) -> None:
        """Initialize the Docker status tool.

        Args:
            docker_host: Docker host URL. If None, uses environment defaults.
        """
        self._docker_host = docker_host
        self._client: Any = None

    def _get_client(self) -> Any:
        """Get or create Docker client.

        Returns:
            Docker client instance.

        Raises:
            ImportError: If docker package not installed.
            RuntimeError: If Docker connection fails.
        """
        if self._client is not None:
            return self._client

        try:
            import docker
        except ImportError as err:
            raise ImportError(
                "docker package is required for Docker tools. " "Install with: pip install docker"
            ) from err

        try:
            if self._docker_host:
                self._client = docker.DockerClient(base_url=self._docker_host)
            else:
                # Use default from environment
                self._client = docker.from_env()

            # Test connection
            self._client.ping()
            return self._client

        except Exception as e:
            raise RuntimeError(f"Failed to connect to Docker: {e}") from e

    async def list_containers(self, include_stopped: bool = True) -> DockerStatusResult:
        """List all Docker containers with their status.

        Args:
            include_stopped: Whether to include stopped containers.

        Returns:
            DockerStatusResult with container list.
        """
        try:
            client = self._get_client()

            loop = asyncio.get_event_loop()
            containers = await loop.run_in_executor(
                None, lambda: client.containers.list(all=include_stopped)
            )

            summaries = [
                ContainerSummary(
                    id=c.short_id,
                    name=c.name,
                    status=c.status,
                    image=c.image.tags[0] if c.image.tags else "unknown",
                )
                for c in containers
            ]

            return DockerStatusResult(success=True, containers=summaries)

        except ImportError as e:
            return DockerStatusResult(success=False, error=str(e))
        except RuntimeError as e:
            return DockerStatusResult(success=False, error=str(e))
        except Exception as e:
            logger.exception("Failed to list containers")
            return DockerStatusResult(success=False, error=f"Failed to list containers: {e}")

    async def get_container_status(self, container_id: str) -> DockerStatusResult:
        """Get detailed status for a specific container.

        Args:
            container_id: Container name or ID.

        Returns:
            DockerStatusResult with container details.
        """
        try:
            client = self._get_client()

            loop = asyncio.get_event_loop()
            container = await loop.run_in_executor(
                None, lambda: client.containers.get(container_id)
            )

            status = ContainerStatus(
                id=container.short_id,
                name=container.name,
                status=container.status,
                image=container.image.tags[0] if container.image.tags else "unknown",
                created=container.attrs.get("Created"),
                started=container.attrs.get("State", {}).get("StartedAt"),
                ports=container.attrs.get("NetworkSettings", {}).get("Ports", {}),
                health=container.attrs.get("State", {}).get("Health", {}),
            )

            return DockerStatusResult(success=True, container=status)

        except ImportError as e:
            return DockerStatusResult(success=False, error=str(e))
        except RuntimeError as e:
            return DockerStatusResult(success=False, error=str(e))
        except Exception as e:
            logger.exception(f"Failed to get container status: {container_id}")
            return DockerStatusResult(
                success=False,
                error=f"Failed to get container status: {e}",
                container=ContainerStatus(
                    id="", name=container_id, status="unknown", image="", error=str(e)
                ),
            )

    async def get_container_health(self, container_id: str) -> dict[str, Any]:
        """Get health check status for a container.

        Args:
            container_id: Container name or ID.

        Returns:
            Health check information dict.
        """
        result = await self.get_container_status(container_id)

        if not result.success or not result.container:
            return {
                "healthy": False,
                "error": result.error or "Container not found",
            }

        health = result.container.health

        if not health:
            return {
                "healthy": None,  # No health check configured
                "status": result.container.status,
                "message": "No health check configured for this container",
            }

        return {
            "healthy": health.get("Status") == "healthy",
            "status": health.get("Status", "unknown"),
            "failing_streak": health.get("FailingStreak", 0),
            "log": health.get("Log", [])[-3:],  # Last 3 health check results
        }

    async def get_container_stats(self, container_id: str) -> dict[str, Any]:
        """Get resource usage statistics for a container.

        Args:
            container_id: Container name or ID.

        Returns:
            Resource usage statistics.
        """
        try:
            client = self._get_client()

            loop = asyncio.get_event_loop()
            container = await loop.run_in_executor(
                None, lambda: client.containers.get(container_id)
            )

            if container.status != "running":
                return {
                    "error": f"Container is not running (status: {container.status})",
                    "container": container_id,
                }

            # Get stats (non-streaming)
            stats = await loop.run_in_executor(None, lambda: container.stats(stream=False))

            # Calculate CPU percentage
            cpu_delta = (
                stats["cpu_stats"]["cpu_usage"]["total_usage"]
                - stats["precpu_stats"]["cpu_usage"]["total_usage"]
            )
            system_delta = (
                stats["cpu_stats"]["system_cpu_usage"] - stats["precpu_stats"]["system_cpu_usage"]
            )
            cpu_percent = 0.0
            if system_delta > 0:
                cpu_percent = (cpu_delta / system_delta) * 100.0

            # Calculate memory usage
            mem_usage = stats["memory_stats"].get("usage", 0)
            mem_limit = stats["memory_stats"].get("limit", 1)
            mem_percent = (mem_usage / mem_limit) * 100.0 if mem_limit > 0 else 0.0

            return {
                "cpu_percent": round(cpu_percent, 2),
                "memory_usage_mb": round(mem_usage / (1024 * 1024), 2),
                "memory_limit_mb": round(mem_limit / (1024 * 1024), 2),
                "memory_percent": round(mem_percent, 2),
                "network_rx_bytes": stats.get("networks", {}).get("eth0", {}).get("rx_bytes", 0),
                "network_tx_bytes": stats.get("networks", {}).get("eth0", {}).get("tx_bytes", 0),
            }

        except ImportError as e:
            return {"error": str(e)}
        except RuntimeError as e:
            return {"error": str(e)}
        except Exception as e:
            logger.exception(f"Failed to get container stats: {container_id}")
            return {"error": f"Failed to get container stats: {e}"}

    async def find_unhealthy_containers(self) -> list[dict[str, Any]]:
        """Find all containers that are unhealthy or not running.

        Returns:
            List of unhealthy container information.
        """
        result = await self.list_containers(include_stopped=True)

        if not result.success:
            return [{"error": result.error}]

        unhealthy = []
        for container in result.containers:
            if container.status != "running":
                unhealthy.append(
                    {
                        "id": container.id,
                        "name": container.name,
                        "status": container.status,
                        "reason": "not_running",
                    }
                )
            else:
                # Check health for running containers
                health = await self.get_container_health(container.name)
                if health.get("healthy") is False:
                    unhealthy.append(
                        {
                            "id": container.id,
                            "name": container.name,
                            "status": container.status,
                            "reason": "unhealthy",
                            "health_status": str(health.get("status", "unknown")),
                        }
                    )

        return unhealthy


# Default tool instance
_default_tool: DockerStatusTool | None = None


def get_docker_tool(docker_host: str | None = None) -> DockerStatusTool:
    """Get the Docker status tool instance.

    Args:
        docker_host: Docker host URL.

    Returns:
        DockerStatusTool instance.
    """
    global _default_tool
    if _default_tool is None:
        _default_tool = DockerStatusTool(docker_host=docker_host)
    return _default_tool


# Tool functions for agent registration


async def list_docker_containers(include_stopped: bool = True) -> str:
    """List all Docker containers with their status.

    Args:
        include_stopped: Whether to include stopped containers (default: True).

    Returns:
        Formatted string with container list or error message.
    """
    logger.info(f"[TOOL CALLED] list_docker_containers: include_stopped={include_stopped}")
    tool = get_docker_tool()
    result = await tool.list_containers(include_stopped=include_stopped)

    if not result.success:
        if "Permission denied" in str(result.error):
            return (
                "Cannot access Docker (permission denied). "
                "Use file reading tools instead:\n"
                "- Read demo/docker-compose.demo.yml for container configuration\n"
                "- Read demo/init-pgduckdb.sql for database initialization\n"
                "- List demo/fixtures/ for data files"
            )
        return f"Error listing containers: {result.error}"

    if not result.containers:
        return "No containers found."

    lines = ["Docker Containers:"]
    for c in result.containers:
        status_indicator = "🟢" if c.status == "running" else "🔴"
        lines.append(f"  {status_indicator} {c.name} ({c.id}) - {c.status} [{c.image}]")

    return "\n".join(lines)


async def get_docker_container_status(container_id: str) -> str:
    """Get detailed status for a specific Docker container.

    Args:
        container_id: Container name or ID.

    Returns:
        Formatted string with container details or error message.
    """
    logger.info(f"[TOOL CALLED] get_docker_container_status: {container_id}")
    tool = get_docker_tool()
    result = await tool.get_container_status(container_id)

    if not result.success:
        return f"Error getting container status: {result.error}"

    if not result.container:
        return f"Container not found: {container_id}"

    c = result.container
    lines = [
        f"Container: {c.name}",
        f"  ID: {c.id}",
        f"  Status: {c.status}",
        f"  Image: {c.image}",
    ]

    if c.created:
        lines.append(f"  Created: {c.created}")
    if c.started:
        lines.append(f"  Started: {c.started}")
    if c.ports:
        lines.append(f"  Ports: {_format_ports(c.ports)}")
    if c.health:
        health_status = c.health.get("Status", "unknown")
        lines.append(f"  Health: {health_status}")

    return "\n".join(lines)


async def get_docker_container_health(container_id: str) -> str:
    """Get health check status for a Docker container.

    Args:
        container_id: Container name or ID.

    Returns:
        Formatted string with health information or error message.
    """
    tool = get_docker_tool()
    health = await tool.get_container_health(container_id)

    if "error" in health:
        return f"Error getting health status: {health['error']}"

    if health.get("healthy") is None:
        return f"Container {container_id}: {health.get('message', 'No health check configured')}"

    status_emoji = "✅" if health.get("healthy") else "❌"
    lines = [
        f"{status_emoji} Container {container_id}: {health.get('status', 'unknown')}",
    ]

    if health.get("failing_streak", 0) > 0:
        lines.append(f"  Failing streak: {health['failing_streak']}")

    if health.get("log"):
        lines.append("  Recent health checks:")
        for log_entry in health["log"]:
            exit_code = log_entry.get("ExitCode", "?")
            output = log_entry.get("Output", "").strip()[:100]
            lines.append(f"    - Exit {exit_code}: {output}")

    return "\n".join(lines)


async def get_docker_container_stats(container_id: str) -> str:
    """Get resource usage statistics for a Docker container.

    Args:
        container_id: Container name or ID.

    Returns:
        Formatted string with resource usage or error message.
    """
    tool = get_docker_tool()
    stats = await tool.get_container_stats(container_id)

    if "error" in stats:
        return f"Error getting container stats: {stats['error']}"

    lines = [
        f"Resource Usage for {container_id}:",
        f"  CPU: {stats['cpu_percent']}%",
        f"  Memory: {stats['memory_usage_mb']} MB / {stats['memory_limit_mb']} MB "
        f"({stats['memory_percent']}%)",
        f"  Network RX: {_format_bytes(stats['network_rx_bytes'])}",
        f"  Network TX: {_format_bytes(stats['network_tx_bytes'])}",
    ]

    return "\n".join(lines)


async def find_unhealthy_docker_containers() -> str:
    """Find all Docker containers that are unhealthy or not running.

    Returns:
        Formatted string with unhealthy container list or success message.
    """
    logger.info("[TOOL CALLED] find_unhealthy_docker_containers")
    tool = get_docker_tool()
    unhealthy = await tool.find_unhealthy_containers()

    if not unhealthy:
        return "✅ All containers are healthy and running."

    if len(unhealthy) == 1 and "error" in unhealthy[0]:
        error_msg = unhealthy[0]["error"]
        if "Permission denied" in str(error_msg):
            return (
                "Cannot access Docker (permission denied). "
                "Check container status manually with: docker ps\n"
                "For initialization issues, read demo/init-pgduckdb.sql"
            )
        return f"Error checking containers: {error_msg}"

    lines = ["⚠️ Unhealthy or stopped containers:"]
    for c in unhealthy:
        if "error" in c:
            continue
        reason = c.get("reason", "unknown")
        if reason == "not_running":
            lines.append(f"  🔴 {c['name']} - {c['status']}")
        else:
            lines.append(f"  ⚠️ {c['name']} - health: {c.get('health_status', 'unhealthy')}")

    return "\n".join(lines)


def _format_ports(ports: dict[str, Any]) -> str:
    """Format port mappings for display.

    Args:
        ports: Port mapping dict from Docker API.

    Returns:
        Formatted port string.
    """
    if not ports:
        return "none"

    formatted = []
    for container_port, host_bindings in ports.items():
        if host_bindings:
            for binding in host_bindings:
                host_port = binding.get("HostPort", "?")
                formatted.append(f"{host_port}->{container_port}")
        else:
            formatted.append(container_port)

    return ", ".join(formatted)


def _format_bytes(num_bytes: int) -> str:
    """Format bytes for human-readable display.

    Args:
        num_bytes: Number of bytes.

    Returns:
        Human-readable string.
    """
    value: float = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(value) < 1024.0:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} TB"


def register_docker_tools(registry: ToolRegistry) -> None:
    """Register Docker status tools with the tool registry.

    Args:
        registry: Tool registry instance.
    """
    from collections.abc import Callable

    tools: list[tuple[str, Callable[..., Any], str]] = [
        (
            "list_docker_containers",
            list_docker_containers,
            "List all Docker containers with their status",
        ),
        (
            "get_docker_container_status",
            get_docker_container_status,
            "Get detailed status for a specific Docker container",
        ),
        (
            "get_docker_container_health",
            get_docker_container_health,
            "Get health check status for a Docker container",
        ),
        (
            "get_docker_container_stats",
            get_docker_container_stats,
            "Get resource usage statistics for a Docker container",
        ),
        (
            "find_unhealthy_docker_containers",
            find_unhealthy_docker_containers,
            "Find all Docker containers that are unhealthy or not running",
        ),
    ]

    for name, func, description in tools:
        registry.register_tool(
            name=name,
            category=ToolCategory.DOCKER,
            description=description,
            func=func,
        )
