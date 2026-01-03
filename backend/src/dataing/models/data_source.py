"""Data source configuration model."""
import enum
import json

from cryptography.fernet import Fernet
from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from dataing.models.base import BaseModel


class DataSourceType(str, enum.Enum):
    """Supported data source types."""

    POSTGRES = "postgres"
    TRINO = "trino"
    SNOWFLAKE = "snowflake"
    BIGQUERY = "bigquery"
    REDSHIFT = "redshift"


class DataSource(BaseModel):
    """Configured data source for investigations."""

    __tablename__ = "data_sources"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    name = Column(String(100), nullable=False)
    type = Column(Enum(DataSourceType), nullable=False)

    # Connection details (encrypted)
    connection_config_encrypted = Column(String, nullable=False)

    # Metadata
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    last_health_check_at = Column(DateTime(timezone=True), nullable=True)
    last_health_check_status = Column(String(50), nullable=True)  # "healthy" | "unhealthy"

    # Relationships
    tenant = relationship("Tenant", back_populates="data_sources")
    investigations = relationship("Investigation", back_populates="data_source")

    def get_connection_config(self, encryption_key: bytes) -> dict:
        """Decrypt and return connection config."""
        f = Fernet(encryption_key)
        decrypted = f.decrypt(self.connection_config_encrypted.encode())
        return json.loads(decrypted.decode())

    @staticmethod
    def encrypt_connection_config(config: dict, encryption_key: bytes) -> str:
        """Encrypt connection config for storage."""
        f = Fernet(encryption_key)
        encrypted = f.encrypt(json.dumps(config).encode())
        return encrypted.decode()
