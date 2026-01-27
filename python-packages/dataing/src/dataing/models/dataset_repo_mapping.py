"""Dataset-to-repository mapping model."""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dataing.models.base import BaseModel

if TYPE_CHECKING:
    from dataing.models.tenant import Tenant


class DatasetRepoMapping(BaseModel):
    """Maps datasets to their source code repositories."""

    __tablename__ = "dataset_repo_mappings"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    dataset_pattern: Mapped[str] = mapped_column(Text, nullable=False)
    pattern_type: Mapped[str] = mapped_column(String(10), nullable=False, default="exact")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    repo_owner: Mapped[str] = mapped_column(Text, nullable=False)
    repo_name: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    branch: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
