"""Log provider interface and implementations.

Provides pluggable access to logs from various sources:
- Local file system
- Docker containers
- CloudWatch Logs
"""

from dataing.agents.tools.log_providers.base import LogProvider, LogProviderConfig
from dataing.agents.tools.log_providers.docker import DockerLogProvider
from dataing.agents.tools.log_providers.local import LocalFileLogProvider

__all__ = [
    "LogProvider",
    "LogProviderConfig",
    "LocalFileLogProvider",
    "DockerLogProvider",
]

# CloudWatch provider is optional - only available with boto3
try:
    from dataing.agents.tools.log_providers.cloudwatch import (  # noqa: F401
        CloudWatchLogProvider,
    )

    __all__.append("CloudWatchLogProvider")
except ImportError:
    pass
