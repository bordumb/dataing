"""RBAC adapters."""

from dataing.adapters.rbac.tags_repository import TagsRepository
from dataing.adapters.rbac.teams_repository import TeamsRepository

__all__ = [
    "TagsRepository",
    "TeamsRepository",
]
