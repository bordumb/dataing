"""Email-based password recovery adapter.

This is the default implementation of PasswordRecoveryAdapter that sends
password reset emails via SMTP.
"""

from dataing.adapters.notifications.email import EmailNotifier
from dataing.core.auth.recovery import PasswordRecoveryAdapter, RecoveryMethod


class EmailPasswordRecoveryAdapter:
    """Email-based password recovery.

    Sends password reset links via email. This is the default recovery
    method for most users.
    """

    def __init__(self, email_notifier: EmailNotifier, frontend_url: str) -> None:
        """Initialize the email recovery adapter.

        Args:
            email_notifier: Email notifier instance for sending emails.
            frontend_url: Base URL of the frontend (for building reset links).
        """
        self._email = email_notifier
        self._frontend_url = frontend_url.rstrip("/")

    async def get_recovery_method(self, user_email: str) -> RecoveryMethod:
        """Get the email recovery method.

        For email-based recovery, we always return the same method
        regardless of the user.

        Args:
            user_email: The user's email address (unused for email recovery).

        Returns:
            RecoveryMethod indicating email-based reset.
        """
        return RecoveryMethod(
            type="email",
            message="We'll send a password reset link to your email address.",
        )

    async def initiate_recovery(
        self,
        user_email: str,
        token: str,
        reset_url: str,
    ) -> bool:
        """Send the password reset email.

        Args:
            user_email: The email address to send the reset link to.
            token: The reset token (included in reset_url, kept for interface).
            reset_url: The full URL for password reset.

        Returns:
            True if email was sent successfully.
        """
        return await self._email.send_password_reset(
            to_email=user_email,
            reset_url=reset_url,
        )


# Verify we implement the protocol
_adapter: PasswordRecoveryAdapter = EmailPasswordRecoveryAdapter(
    email_notifier=None,  # type: ignore[arg-type]
    frontend_url="",
)
