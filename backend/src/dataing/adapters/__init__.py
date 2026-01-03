"""Adapters - Infrastructure implementations of core interfaces.

This package contains all the concrete implementations of the
Protocol interfaces defined in the core module.

Adapters are organized by type:
- db/: Database adapters (Postgres, Trino, Mock)
- llm/: LLM client adapters (Anthropic)
- context/: Context gathering adapters
"""

from .context.engine import DefaultContextEngine
from .context.lineage import LineageContext, OpenLineageClient
from .db.mock import MockDatabaseAdapter
from .db.postgres import PostgresAdapter
from .db.trino import TrinoAdapter
from .llm.client import AnthropicClient
from .llm.prompt_manager import PromptManager

__all__ = [
    # Database adapters
    "PostgresAdapter",
    "TrinoAdapter",
    "MockDatabaseAdapter",
    # LLM adapters
    "AnthropicClient",
    "PromptManager",
    # Context adapters
    "DefaultContextEngine",
    "OpenLineageClient",
    "LineageContext",
]
