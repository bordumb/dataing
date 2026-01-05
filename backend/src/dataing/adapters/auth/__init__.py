"""Auth adapters."""

from dataing.adapters.auth.postgres import PostgresAuthRepository
from dataing.adapters.auth.recovery_email import EmailPasswordRecoveryAdapter

__all__ = ["PostgresAuthRepository", "EmailPasswordRecoveryAdapter"]
