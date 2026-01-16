"""Runbook and knowledge base models."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dataing.models.base import BaseModel


class LinkType:
    """Runbook link types."""

    SUGGESTED = "suggested"
    APPLIED = "applied"
    REFERENCED = "referenced"


class Runbook(BaseModel):
    """Knowledge base article generated from resolved issues."""

    __tablename__ = "runbooks"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)

    # Categorization
    dataset_id: Mapped[str | None] = mapped_column(Text)
    labels: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )

    # Origin tracking
    created_from_issue_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("issues.id", ondelete="SET NULL")
    )
    created_from_investigation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("investigations.id", ondelete="SET NULL")
    )

    # Structured content (extracted from investigation)
    symptoms: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    root_cause: Mapped[str | None] = mapped_column(Text)
    verification_steps: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    fix_steps: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    prevention_notes: Mapped[str | None] = mapped_column(Text)

    # Search (search_vector handled by trigger)
    embedding_vector: Mapped[list[float] | None] = mapped_column(ARRAY(Float))

    # Metadata
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    usefulness_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    # Relationships
    links: Mapped[list[RunbookLink]] = relationship(
        "RunbookLink", back_populates="runbook", cascade="all, delete-orphan"
    )


class RunbookLink(BaseModel):
    """Association between runbooks and issues."""

    __tablename__ = "runbook_links"

    runbook_id: Mapped[UUID] = mapped_column(
        ForeignKey("runbooks.id", ondelete="CASCADE"), nullable=False
    )
    issue_id: Mapped[UUID] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
    )

    # Similarity/relevance score (0.0 to 1.0)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Link type
    link_type: Mapped[str] = mapped_column(
        Text, nullable=False, default=LinkType.SUGGESTED
    )

    # Feedback
    was_helpful: Mapped[bool | None] = mapped_column(Boolean)
    feedback_notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    # Relationships
    runbook: Mapped[Runbook] = relationship("Runbook", back_populates="links")
