"""User model."""
from sqlalchemy import Boolean, Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from dataing.models.base import BaseModel


class User(BaseModel):
    """A user in the system."""

    __tablename__ = "users"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    email = Column(String(255), nullable=False)
    name = Column(String(100))
    role = Column(String(50), default="member")  # admin, member, viewer
    is_active = Column(Boolean, default=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="users")
    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")
    investigations = relationship("Investigation", back_populates="created_by_user")

    __table_args__ = (
        # Unique constraint on tenant_id + email
        {"sqlite_autoincrement": True},
    )
