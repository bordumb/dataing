"""Console-based password recovery adapter for demo/dev mode.

Prints the reset link to stdout so developers can click it directly.
"""

from dataing.core.auth.recovery import PasswordRecoveryAdapter, RecoveryMethod


class ConsoleRecoveryAdapter:
    """Console-based password recovery for demo/dev mode.

    Instead of sending an email, prints the reset link to the console
    so developers can click it directly. This is useful for:
    - Local development without SMTP setup
    - Demo environments
    - Testing password reset flows
    """

    def __init__(self, frontend_url: str) -> None:
        """Initialize the console recovery adapter.

        Args:
            frontend_url: Base URL of the frontend for building reset links.
        """
        self._frontend_url = frontend_url.rstrip("/")

    async def get_recovery_method(self, user_email: str) -> RecoveryMethod:
        """Return the console recovery method.

        Args:
            user_email: The user's email address (unused for console recovery).

        Returns:
            RecoveryMethod indicating console-based reset.
        """
        return RecoveryMethod(
            type="console",
            message="Password reset link will appear in the server console.",
        )

    async def initiate_recovery(
        self,
        user_email: str,
        token: str,
        reset_url: str,
    ) -> bool:
        """Print the password reset link to the console.

        Args:
            user_email: The email address for the reset.
            token: The reset token (included in reset_url).
            reset_url: The full URL for password reset.

        Returns:
            True (console printing always succeeds).
        """
        # Print with clear formatting so it's visible in logs
        print("\n" + "=" * 70, flush=True)
        print("[PASSWORD RESET] Reset link generated for demo/dev mode", flush=True)
        print(f"  Email: {user_email}", flush=True)
        print(f"  Link:  {reset_url}", flush=True)
        print("=" * 70 + "\n", flush=True)
        return True


# Verify we implement the protocol
_adapter: PasswordRecoveryAdapter = ConsoleRecoveryAdapter(frontend_url="")
