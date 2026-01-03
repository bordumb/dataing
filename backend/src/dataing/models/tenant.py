"""Tenant model for multi-tenancy."""
from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from dataing.models.base import BaseModel


class Tenant(BaseModel):
    """A tenant/organization in the system."""

    __tablename__ = "tenants"

    name = Column(String(100), nullable=False)
    slug = Column(String(50), unique=True, nullable=False)
    settings = Column(JSONB, default=dict)

    # Relationships
    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    api_keys = relationship("ApiKey", back_populates="tenant", cascade="all, delete-orphan")
    data_sources = relationship("DataSource", back_populates="tenant", cascade="all, delete-orphan")
    investigations = relationship("Investigation", back_populates="tenant", cascade="all, delete-orphan")
    webhooks = relationship("Webhook", back_populates="tenant", cascade="all, delete-orphan")
