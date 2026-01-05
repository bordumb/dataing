"""Auth service for login, registration, and token management."""

import re
from typing import Any
from uuid import UUID

import structlog

from dataing.core.auth.jwt import create_access_token, create_refresh_token, decode_token
from dataing.core.auth.password import hash_password, verify_password
from dataing.core.auth.recovery import PasswordRecoveryAdapter, RecoveryMethod
from dataing.core.auth.repository import AuthRepository
from dataing.core.auth.tokens import (
    generate_reset_token,
    get_token_expiry,
    hash_token,
    is_token_expired,
)
from dataing.core.auth.types import OrgRole

logger = structlog.get_logger()


class AuthError(Exception):
    """Raised when authentication fails."""

    pass


class AuthService:
    """Service for authentication operations."""

    def __init__(self, repo: AuthRepository) -> None:
        """Initialize with auth repository.

        Args:
            repo: Auth repository for database operations.
        """
        self._repo = repo

    async def login(
        self,
        email: str,
        password: str,
        org_id: UUID,
    ) -> dict[str, Any]:
        """Authenticate user and return tokens.

        Args:
            email: User's email address.
            password: Plain text password.
            org_id: Organization to log into.

        Returns:
            Dict with access_token, refresh_token, user info, and org info.

        Raises:
            AuthError: If authentication fails.
        """
        # Get user
        user = await self._repo.get_user_by_email(email)
        if not user:
            raise AuthError("Invalid email or password")

        if not user.is_active:
            raise AuthError("User account is disabled")

        if not user.password_hash:
            raise AuthError("Password login not enabled for this account")

        # Verify password
        if not verify_password(password, user.password_hash):
            raise AuthError("Invalid email or password")

        # Get user's membership in org
        membership = await self._repo.get_user_org_membership(user.id, org_id)
        if not membership:
            raise AuthError("User is not a member of this organization")

        # Get org details
        org = await self._repo.get_org_by_id(org_id)
        if not org:
            raise AuthError("Organization not found")

        # Get user's teams in this org
        teams = await self._repo.get_user_teams(user.id, org_id)
        team_ids = [str(t.id) for t in teams]

        # Create tokens
        access_token = create_access_token(
            user_id=str(user.id),
            org_id=str(org_id),
            role=membership.role.value,
            teams=team_ids,
        )
        refresh_token = create_refresh_token(user_id=str(user.id))

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "name": user.name,
            },
            "org": {
                "id": str(org.id),
                "name": org.name,
                "slug": org.slug,
                "plan": org.plan,
            },
            "role": membership.role.value,
        }

    async def register(
        self,
        email: str,
        password: str,
        name: str,
        org_name: str,
        org_slug: str | None = None,
    ) -> dict[str, Any]:
        """Register new user and create organization.

        Args:
            email: User's email address.
            password: Plain text password.
            name: User's display name.
            org_name: Organization name.
            org_slug: Optional org slug (generated from name if not provided).

        Returns:
            Dict with access_token, refresh_token, user info, and org info.

        Raises:
            AuthError: If registration fails.
        """
        # Check if user already exists
        existing = await self._repo.get_user_by_email(email)
        if existing:
            raise AuthError("User with this email already exists")

        # Generate slug if not provided
        if not org_slug:
            org_slug = self._generate_slug(org_name)

        # Check if org slug is taken
        existing_org = await self._repo.get_org_by_slug(org_slug)
        if existing_org:
            raise AuthError("Organization with this slug already exists")

        # Create user
        password_hash_value = hash_password(password)
        user = await self._repo.create_user(
            email=email,
            name=name,
            password_hash=password_hash_value,
        )

        # Create org
        org = await self._repo.create_org(
            name=org_name,
            slug=org_slug,
            plan="free",
        )

        # Add user as owner
        await self._repo.add_user_to_org(
            user_id=user.id,
            org_id=org.id,
            role=OrgRole.OWNER,
        )

        # Create tokens
        access_token = create_access_token(
            user_id=str(user.id),
            org_id=str(org.id),
            role=OrgRole.OWNER.value,
            teams=[],
        )
        refresh_token = create_refresh_token(user_id=str(user.id))

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "name": user.name,
            },
            "org": {
                "id": str(org.id),
                "name": org.name,
                "slug": org.slug,
                "plan": org.plan,
            },
            "role": OrgRole.OWNER.value,
        }

    async def refresh(self, refresh_token: str, org_id: UUID) -> dict[str, Any]:
        """Refresh access token.

        Args:
            refresh_token: Valid refresh token.
            org_id: Organization to get new token for.

        Returns:
            Dict with new access_token.

        Raises:
            AuthError: If refresh fails.
        """
        # Decode refresh token
        try:
            payload = decode_token(refresh_token)
        except Exception as e:
            raise AuthError(f"Invalid refresh token: {e}") from None

        # Get user
        user = await self._repo.get_user_by_id(UUID(payload.sub))
        if not user or not user.is_active:
            raise AuthError("User not found or disabled")

        # Get membership
        membership = await self._repo.get_user_org_membership(user.id, org_id)
        if not membership:
            raise AuthError("User is not a member of this organization")

        # Get teams
        teams = await self._repo.get_user_teams(user.id, org_id)
        team_ids = [str(t.id) for t in teams]

        # Create new access token
        access_token = create_access_token(
            user_id=str(user.id),
            org_id=str(org_id),
            role=membership.role.value,
            teams=team_ids,
        )

        return {
            "access_token": access_token,
            "token_type": "bearer",
        }

    async def get_user_orgs(self, user_id: UUID) -> list[dict[str, Any]]:
        """Get all organizations a user belongs to.

        Args:
            user_id: User's ID.

        Returns:
            List of dicts with org info and role.
        """
        orgs = await self._repo.get_user_orgs(user_id)
        return [
            {
                "org": {
                    "id": str(org.id),
                    "name": org.name,
                    "slug": org.slug,
                    "plan": org.plan,
                },
                "role": role.value,
            }
            for org, role in orgs
        ]

    def _generate_slug(self, name: str) -> str:
        """Generate URL-safe slug from name."""
        slug = name.lower()
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        slug = slug.strip("-")
        return slug

    # Password reset methods

    async def get_recovery_method(
        self,
        email: str,
        recovery_adapter: PasswordRecoveryAdapter,
    ) -> RecoveryMethod:
        """Get the recovery method for a user.

        This tells the frontend what UI to show (email form, admin contact, etc.).

        Args:
            email: User's email address.
            recovery_adapter: The recovery adapter to use.

        Returns:
            RecoveryMethod describing how the user can recover their password.
        """
        return await recovery_adapter.get_recovery_method(email)

    async def request_password_reset(
        self,
        email: str,
        recovery_adapter: PasswordRecoveryAdapter,
        frontend_url: str,
    ) -> None:
        """Request a password reset.

        For security, this always succeeds (doesn't reveal if email exists).
        If the email exists and recovery is possible, sends a reset link.

        Args:
            email: User's email address.
            recovery_adapter: The recovery adapter to use.
            frontend_url: Base URL of the frontend for building reset links.
        """
        # Find user by email
        user = await self._repo.get_user_by_email(email)
        if not user:
            # Silently succeed - don't reveal if email exists
            logger.info("password_reset_requested_unknown_email", email=email)
            return

        if not user.is_active:
            # Silently succeed - don't reveal account status
            logger.info("password_reset_requested_inactive_user", user_id=str(user.id))
            return

        # Delete any existing tokens for this user
        await self._repo.delete_user_reset_tokens(user.id)

        # Generate new token
        token = generate_reset_token()
        token_hash_value = hash_token(token)
        expires_at = get_token_expiry()

        # Store token
        await self._repo.create_password_reset_token(
            user_id=user.id,
            token_hash=token_hash_value,
            expires_at=expires_at,
        )

        # Build reset URL
        reset_url = f"{frontend_url.rstrip('/')}/password-reset/confirm?token={token}"

        # Send via recovery adapter
        success = await recovery_adapter.initiate_recovery(
            user_email=email,
            token=token,
            reset_url=reset_url,
        )

        if success:
            logger.info("password_reset_email_sent", user_id=str(user.id))
        else:
            logger.error("password_reset_email_failed", user_id=str(user.id))
            # Don't raise - we don't want to reveal email delivery status

    async def reset_password(self, token: str, new_password: str) -> None:
        """Reset password using a valid token.

        Args:
            token: The reset token from the email link.
            new_password: The new password to set.

        Raises:
            AuthError: If token is invalid, expired, or already used.
        """
        # Hash token for lookup
        token_hash_value = hash_token(token)

        # Look up token
        token_record = await self._repo.get_password_reset_token(token_hash_value)
        if not token_record:
            logger.warning("password_reset_invalid_token")
            raise AuthError("Invalid or expired reset link")

        # Check if already used
        if token_record["used_at"] is not None:
            logger.warning("password_reset_token_already_used", token_id=str(token_record["id"]))
            raise AuthError("This reset link has already been used")

        # Check if expired
        if is_token_expired(token_record["expires_at"]):
            logger.warning("password_reset_token_expired", token_id=str(token_record["id"]))
            raise AuthError("This reset link has expired")

        # Get user
        user = await self._repo.get_user_by_id(token_record["user_id"])
        if not user or not user.is_active:
            logger.warning("password_reset_user_not_found", user_id=str(token_record["user_id"]))
            raise AuthError("User not found")

        # Update password
        password_hash_value = hash_password(new_password)
        await self._repo.update_user(
            user_id=user.id,
            password_hash=password_hash_value,
        )

        # Mark token as used
        await self._repo.mark_token_used(token_record["id"])

        # Delete all other reset tokens for this user
        await self._repo.delete_user_reset_tokens(user.id)

        logger.info("password_reset_successful", user_id=str(user.id))
