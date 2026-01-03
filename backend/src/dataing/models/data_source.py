"""Data source configuration model."""

import enum
import json
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from cryptography.fernet import Fernet
from sqlalchemy import Boolean, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dataing.models.base import BaseModel

if TYPE_CHECKING:
    from dataing.models.investigation import Investigation
    from dataing.models.tenant import Tenant


class DataSourceType(str, enum.Enum):
    """Supported data source types."""

    POSTGRES = "postgres"
    TRINO = "trino"
    SNOWFLAKE = "snowflake"
    BIGQUERY = "bigquery"
    REDSHIFT = "redshift"
    DUCKDB = "duckdb"


class DataSource(BaseModel):
    """Configured data source for investigations."""

    __tablename__ = "data_sources"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[DataSourceType] = mapped_column(Enum(DataSourceType), nullable=False)

    # Connection details (encrypted)
    connection_config_encrypted: Mapped[str] = mapped_column(String, nullable=False)

    # Metadata
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_health_check_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_health_check_status: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # "healthy" | "unhealthy"

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="data_sources")
    investigations: Mapped[list["Investigation"]] = relationship(
        "Investigation", back_populates="data_source"
    )

    def get_connection_config(self, encryption_key: bytes) -> dict[str, Any]:
        """Decrypt and return connection config."""
        f = Fernet(encryption_key)
        decrypted = f.decrypt(self.connection_config_encrypted.encode())
        config: dict[str, Any] = json.loads(decrypted.decode())
        return config

    @staticmethod
    def encrypt_connection_config(config: dict[str, Any], encryption_key: bytes) -> str:
        """Encrypt connection config for storage."""
        f = Fernet(encryption_key)
        encrypted = f.encrypt(json.dumps(config).encode())
        return encrypted.decode()
