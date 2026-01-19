"""Password recovery protocol and types.

This module defines the extensible interface for password recovery strategies.
Enterprises can implement different recovery methods:
- Email-based reset (default)
- "Contact your admin" flow (SSO orgs)
- Custom identity provider integrations
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class RecoveryMethod:
    """Describes how a user can recover their password.

    This is returned to the frontend to determine what UI to show.
    """

    type: str
    """Recovery type identifier: 'email', 'admin_contact', 'sso_redirect', etc."""

    message: str
    """User-facing message explaining the recovery method."""

    action_url: str | None = None
    """Optional URL for redirects (e.g., SSO provider login page)."""

    admin_email: str | None = None
    """Optional admin contact email for 'admin_contact' type."""


@runtime_checkable
class PasswordRecoveryAdapter(Protocol):
    """Protocol for password recovery strategies.

    Implementations provide different ways to handle password recovery
    based on organization configuration, user type, or other factors.

    Example implementations:
    - EmailPasswordRecoveryAdapter: Sends reset email with token link
    - AdminContactRecoveryAdapter: Returns admin contact info (no self-service)
    - SSORedirectRecoveryAdapter: Redirects to SSO provider
    """

    async def get_recovery_method(self, user_email: str) -> RecoveryMethod:
        """Get the recovery method available for this user.

        This determines what UI the frontend should show.

        Args:
            user_email: The email address of the user requesting recovery.

        Returns:
            RecoveryMethod describing how the user can recover their password.
        """
        ...

    async def initiate_recovery(
        self,
        user_email: str,
        token: str,
        reset_url: str,
    ) -> bool:
        """Initiate the recovery process.

        For email-based recovery, this sends the reset email.
        For admin contact, this might notify the admin.
        For SSO, this might be a no-op (redirect handled by get_recovery_method).

        Args:
            user_email: The email address of the user.
            token: The plaintext reset token (adapter decides how to use it).
            reset_url: The full URL for password reset (includes token).

        Returns:
            True if recovery was initiated successfully.
        """
        ...
