"""Type definitions for comments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID


@dataclass(frozen=True)
class SchemaComment:
    """A comment on a schema field."""

    id: UUID
    tenant_id: UUID
    dataset_id: UUID
    field_name: str
    parent_id: UUID | None
    content: str
    author_id: UUID | None
    author_name: str | None
    upvotes: int
    downvotes: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class KnowledgeComment:
    """A comment on dataset knowledge tab."""

    id: UUID
    tenant_id: UUID
    dataset_id: UUID
    parent_id: UUID | None
    content: str
    author_id: UUID | None
    author_name: str | None
    upvotes: int
    downvotes: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class CommentVote:
    """A vote on a comment."""

    id: UUID
    tenant_id: UUID
    comment_type: Literal["schema", "knowledge"]
    comment_id: UUID
    user_id: UUID
    vote: Literal[-1, 1]
    created_at: datetime
