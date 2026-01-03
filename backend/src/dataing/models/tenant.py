"""Tenant model for multi-tenancy."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dataing.models.base import BaseModel

if TYPE_CHECKING:
    from dataing.models.api_key import ApiKey
    from dataing.models.data_source import DataSource
    from dataing.models.investigation import Investigation
    from dataing.models.user import User
    from dataing.models.webhook import Webhook


class Tenant(BaseModel):
    """A tenant/organization in the system."""

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Relationships
    users: Mapped[list["User"]] = relationship(
        "User", back_populates="tenant", cascade="all, delete-orphan"
    )
    api_keys: Mapped[list["ApiKey"]] = relationship(
        "ApiKey", back_populates="tenant", cascade="all, delete-orphan"
    )
    data_sources: Mapped[list["DataSource"]] = relationship(
        "DataSource", back_populates="tenant", cascade="all, delete-orphan"
    )
    investigations: Mapped[list["Investigation"]] = relationship(
        "Investigation", back_populates="tenant", cascade="all, delete-orphan"
    )
    webhooks: Mapped[list["Webhook"]] = relationship(
        "Webhook", back_populates="tenant", cascade="all, delete-orphan"
    )
