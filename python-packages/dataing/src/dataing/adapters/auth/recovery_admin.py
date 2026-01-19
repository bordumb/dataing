"""Admin contact password recovery adapter for SSO organizations.

For organizations using SSO/SAML/OIDC, users cannot reset passwords
through Dataing - they need to contact their administrator or use
their identity provider's password reset flow.
"""

import structlog

from dataing.core.auth.recovery import PasswordRecoveryAdapter, RecoveryMethod

logger = structlog.get_logger()


class AdminContactRecoveryAdapter:
    """Admin contact recovery for SSO organizations.

    Instead of self-service password reset, instructs users to contact
    their administrator. This is appropriate for:
    - Organizations using SSO/SAML/OIDC
    - Enterprises with centralized identity management
    - Environments where password changes must go through IT
    """

    def __init__(self, admin_email: str | None = None) -> None:
        """Initialize the admin contact recovery adapter.

        Args:
            admin_email: Optional admin email to display to users.
        """
        self._admin_email = admin_email

    async def get_recovery_method(self, user_email: str) -> RecoveryMethod:
        """Return the admin contact recovery method.

        Args:
            user_email: The user's email address (unused for admin contact).

        Returns:
            RecoveryMethod indicating users should contact their admin.
        """
        return RecoveryMethod(
            type="admin_contact",
            message=(
                "Your organization uses single sign-on (SSO). "
                "Please contact your administrator to reset your password."
            ),
            admin_email=self._admin_email,
        )

    async def initiate_recovery(
        self,
        user_email: str,
        token: str,
        reset_url: str,
    ) -> bool:
        """Log the password reset request for admin visibility.

        For admin contact recovery, we don't actually send anything.
        We just log the request so administrators can see if users
        are trying to reset passwords.

        Args:
            user_email: The email address for the reset.
            token: The reset token (unused).
            reset_url: The reset URL (unused).

        Returns:
            True (logging always succeeds).
        """
        logger.info(
            "password_reset_admin_contact_requested",
            email=user_email,
            admin_email=self._admin_email,
        )
        return True


# Verify we implement the protocol
_adapter: PasswordRecoveryAdapter = AdminContactRecoveryAdapter()
