"""Code change (commit) model."""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import ARRAY, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dataing.models.base import BaseModel

if TYPE_CHECKING:
    from dataing.models.git_repository import GitRepository


class CodeChange(BaseModel):
    """A parsed git commit with affected asset metadata."""

    __tablename__ = "code_changes"

    repo_id: Mapped[UUID] = mapped_column(ForeignKey("git_repositories.id"), nullable=False)
    commit_hash: Mapped[str] = mapped_column(Text, nullable=False)
    author_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    committed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    affected_assets: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    raw_diff: Mapped[str | None] = mapped_column(Text, nullable=True)
    files_changed: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)

    # Relationships
    repository: Mapped["GitRepository"] = relationship(back_populates="code_changes")
