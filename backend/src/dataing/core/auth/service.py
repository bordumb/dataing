"""Auth service for login, registration, and token management."""

import re
from typing import Any
from uuid import UUID

from dataing.core.auth.jwt import create_access_token, create_refresh_token, decode_token
from dataing.core.auth.password import hash_password, verify_password
from dataing.core.auth.repository import AuthRepository
from dataing.core.auth.types import OrgRole


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
