"""Teams API routes."""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from dataing.adapters.audit import audited
from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.db.team_policy_repository import (
    PolicyAction,
    TeamPolicyRepository,
)
from dataing.adapters.rbac import TeamsRepository
from dataing.core.entitlements.features import Feature
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, require_scope, verify_api_key
from dataing.entrypoints.api.middleware.entitlements import require_under_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/teams", tags=["teams"])

# Annotated types for dependency injection
AppDbDep = Annotated[AppDatabase, Depends(get_app_db)]
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
AdminScopeDep = Annotated[ApiKeyContext, Depends(require_scope("admin"))]


class TeamCreate(BaseModel):
    """Team creation request."""

    name: str


class TeamUpdate(BaseModel):
    """Team update request."""

    name: str


class TeamMemberAdd(BaseModel):
    """Add member request."""

    user_id: UUID


class TeamResponse(BaseModel):
    """Team response."""

    id: UUID
    name: str
    external_id: str | None
    is_scim_managed: bool
    member_count: int | None = None

    class Config:
        """Pydantic config."""

        from_attributes = True


class TeamListResponse(BaseModel):
    """Response for listing teams."""

    teams: list[TeamResponse]
    total: int


@router.get("/", response_model=TeamListResponse)
async def list_teams(
    auth: AuthDep,
    app_db: AppDbDep,
) -> TeamListResponse:
    """List all teams in the organization."""
    async with app_db.acquire() as conn:
        repo = TeamsRepository(conn)
        teams = await repo.list_by_org(auth.tenant_id)

        result = []
        for team in teams:
            members = await repo.get_members(team.id)
            result.append(
                TeamResponse(
                    id=team.id,
                    name=team.name,
                    external_id=team.external_id,
                    is_scim_managed=team.is_scim_managed,
                    member_count=len(members),
                )
            )
        return TeamListResponse(teams=result, total=len(result))


@router.post("/", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
@audited(action="team.create", resource_type="team")
async def create_team(
    request: Request,
    body: TeamCreate,
    auth: AdminScopeDep,
    app_db: AppDbDep,
) -> TeamResponse:
    """Create a new team.

    Requires admin scope.
    """
    async with app_db.acquire() as conn:
        repo = TeamsRepository(conn)
        team = await repo.create(org_id=auth.tenant_id, name=body.name)
        return TeamResponse(
            id=team.id,
            name=team.name,
            external_id=team.external_id,
            is_scim_managed=team.is_scim_managed,
        )


@router.get("/{team_id}", response_model=TeamResponse)
async def get_team(
    team_id: UUID,
    auth: AuthDep,
    app_db: AppDbDep,
) -> TeamResponse:
    """Get a team by ID."""
    async with app_db.acquire() as conn:
        repo = TeamsRepository(conn)
        team = await repo.get_by_id(team_id)

        if not team or team.org_id != auth.tenant_id:
            raise HTTPException(status_code=404, detail="Team not found")

        members = await repo.get_members(team.id)
        return TeamResponse(
            id=team.id,
            name=team.name,
            external_id=team.external_id,
            is_scim_managed=team.is_scim_managed,
            member_count=len(members),
        )


@router.put("/{team_id}", response_model=TeamResponse)
@audited(action="team.update", resource_type="team")
async def update_team(
    request: Request,
    team_id: UUID,
    body: TeamUpdate,
    auth: AdminScopeDep,
    app_db: AppDbDep,
) -> TeamResponse:
    """Update a team.

    Requires admin scope. Cannot update SCIM-managed teams.
    """
    async with app_db.acquire() as conn:
        repo = TeamsRepository(conn)
        team = await repo.get_by_id(team_id)

        if not team or team.org_id != auth.tenant_id:
            raise HTTPException(status_code=404, detail="Team not found")

        if team.is_scim_managed:
            raise HTTPException(status_code=400, detail="Cannot update SCIM-managed team")

        updated = await repo.update(team_id, body.name)
        if not updated:
            raise HTTPException(status_code=404, detail="Team not found")

        return TeamResponse(
            id=updated.id,
            name=updated.name,
            external_id=updated.external_id,
            is_scim_managed=updated.is_scim_managed,
        )


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
@audited(action="team.delete", resource_type="team")
async def delete_team(
    request: Request,
    team_id: UUID,
    auth: AdminScopeDep,
    app_db: AppDbDep,
) -> Response:
    """Delete a team.

    Requires admin scope. Cannot delete SCIM-managed teams.
    """
    async with app_db.acquire() as conn:
        repo = TeamsRepository(conn)
        team = await repo.get_by_id(team_id)

        if not team or team.org_id != auth.tenant_id:
            raise HTTPException(status_code=404, detail="Team not found")

        if team.is_scim_managed:
            raise HTTPException(status_code=400, detail="Cannot delete SCIM-managed team")

        await repo.delete(team_id)
        return Response(status_code=204)


@router.get("/{team_id}/members")
async def get_team_members(
    team_id: UUID,
    auth: AuthDep,
    app_db: AppDbDep,
) -> list[UUID]:
    """Get team members."""
    async with app_db.acquire() as conn:
        repo = TeamsRepository(conn)
        team = await repo.get_by_id(team_id)

        if not team or team.org_id != auth.tenant_id:
            raise HTTPException(status_code=404, detail="Team not found")

        members: list[UUID] = await repo.get_members(team_id)
        return members


@router.post("/{team_id}/members", status_code=status.HTTP_201_CREATED)
@audited(action="team.member_add", resource_type="team")
@require_under_limit(Feature.MAX_SEATS)
async def add_team_member(
    request: Request,
    team_id: UUID,
    body: TeamMemberAdd,
    auth: AdminScopeDep,
    app_db: AppDbDep,
) -> dict[str, str]:
    """Add a member to a team.

    Requires admin scope.
    """
    async with app_db.acquire() as conn:
        repo = TeamsRepository(conn)
        team = await repo.get_by_id(team_id)

        if not team or team.org_id != auth.tenant_id:
            raise HTTPException(status_code=404, detail="Team not found")

        success = await repo.add_member(team_id, body.user_id)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to add member")

        return {"message": "Member added"}


@router.delete(
    "/{team_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
@audited(action="team.member_remove", resource_type="team")
async def remove_team_member(
    request: Request,
    team_id: UUID,
    user_id: UUID,
    auth: AdminScopeDep,
    app_db: AppDbDep,
) -> Response:
    """Remove a member from a team.

    Requires admin scope.
    """
    async with app_db.acquire() as conn:
        repo = TeamsRepository(conn)
        team = await repo.get_by_id(team_id)

        if not team or team.org_id != auth.tenant_id:
            raise HTTPException(status_code=404, detail="Team not found")

        await repo.remove_member(team_id, user_id)
        return Response(status_code=204)


# =============================================================================
# Team Policy Models
# =============================================================================


class TeamPolicyResponse(BaseModel):
    """Team policy response."""

    id: UUID
    team_id: UUID
    sources: list[str] = Field(default_factory=list)
    default_action: str
    auto_investigate_min_severity: str | None = None
    review_required_max_severity: str | None = None
    is_active: bool = True


class TeamPolicyUpdate(BaseModel):
    """Team policy update request."""

    sources: list[str] | None = None
    default_action: str | None = None
    auto_investigate_min_severity: str | None = None
    review_required_max_severity: str | None = None


class TeamPolicyOverrideResponse(BaseModel):
    """Team policy override response."""

    id: UUID
    team_id: UUID
    dataset_id: str | None = None
    tag_id: UUID | None = None
    default_action: str | None = None
    auto_investigate_min_severity: str | None = None
    review_required_max_severity: str | None = None
    is_active: bool = True


class TeamPolicyOverrideCreate(BaseModel):
    """Create a policy override."""

    dataset_id: str | None = None
    tag_id: UUID | None = None
    default_action: str | None = None
    auto_investigate_min_severity: str | None = None
    review_required_max_severity: str | None = None


class TeamPolicyOverrideUpdate(BaseModel):
    """Update a policy override."""

    default_action: str | None = None
    auto_investigate_min_severity: str | None = None
    review_required_max_severity: str | None = None


class TeamQueueLimitsResponse(BaseModel):
    """Team queue limits response."""

    id: UUID
    team_id: UUID
    rate_limit_per_minute: int = 60
    burst_size: int = 10
    max_concurrent: int = 5
    batch_size: int = 5
    is_active: bool = True


class TeamQueueLimitsUpdate(BaseModel):
    """Team queue limits update request."""

    rate_limit_per_minute: int | None = None
    burst_size: int | None = None
    max_concurrent: int | None = None
    batch_size: int | None = None


class TeamPolicyFullResponse(BaseModel):
    """Full team policy response including overrides and queue limits."""

    policy: TeamPolicyResponse | None = None
    overrides: list[TeamPolicyOverrideResponse] = Field(default_factory=list)
    queue_limits: TeamQueueLimitsResponse | None = None


# =============================================================================
# Team Policy Endpoints
# =============================================================================


@router.get("/{team_id}/policy", response_model=TeamPolicyFullResponse)
async def get_team_policy(
    team_id: UUID,
    auth: AuthDep,
    app_db: AppDbDep,
) -> TeamPolicyFullResponse:
    """Get the full policy configuration for a team.

    Returns the team policy, all overrides, and queue limits.
    """
    async with app_db.acquire() as conn:
        teams_repo = TeamsRepository(conn)
        team = await teams_repo.get_by_id(team_id)

        if not team or team.org_id != auth.tenant_id:
            raise HTTPException(status_code=404, detail="Team not found")

    policy_repo = TeamPolicyRepository(app_db)

    # Get policy
    policy = await policy_repo.get_policy_by_team(team_id)
    policy_response = None
    if policy:
        policy_response = TeamPolicyResponse(
            id=policy.id,
            team_id=policy.team_id,
            sources=policy.sources,
            default_action=policy.default_action.value,
            auto_investigate_min_severity=policy.auto_investigate_min_severity,
            review_required_max_severity=policy.review_required_max_severity,
            is_active=policy.is_active,
        )

    # Get overrides
    overrides = await policy_repo.get_overrides_for_team(team_id)
    override_responses = [
        TeamPolicyOverrideResponse(
            id=o.id,
            team_id=o.team_id,
            dataset_id=o.dataset_id,
            tag_id=o.tag_id,
            default_action=o.default_action.value if o.default_action else None,
            auto_investigate_min_severity=o.auto_investigate_min_severity,
            review_required_max_severity=o.review_required_max_severity,
            is_active=o.is_active,
        )
        for o in overrides
    ]

    # Get queue limits
    queue_limits = await policy_repo.get_queue_limits(team_id)
    queue_response = None
    if queue_limits:
        queue_response = TeamQueueLimitsResponse(
            id=queue_limits.id,
            team_id=queue_limits.team_id,
            rate_limit_per_minute=queue_limits.rate_limit_per_minute,
            burst_size=queue_limits.burst_size,
            max_concurrent=queue_limits.max_concurrent,
            batch_size=queue_limits.batch_size,
            is_active=queue_limits.is_active,
        )

    return TeamPolicyFullResponse(
        policy=policy_response,
        overrides=override_responses,
        queue_limits=queue_response,
    )


@router.put("/{team_id}/policy", response_model=TeamPolicyResponse)
@audited(action="team.policy_update", resource_type="team", resource_id_param="team_id")
async def update_team_policy(
    request: Request,
    team_id: UUID,
    body: TeamPolicyUpdate,
    auth: AdminScopeDep,
    app_db: AppDbDep,
) -> TeamPolicyResponse:
    """Update or create the team policy.

    Requires admin scope.
    """
    async with app_db.acquire() as conn:
        teams_repo = TeamsRepository(conn)
        team = await teams_repo.get_by_id(team_id)

        if not team or team.org_id != auth.tenant_id:
            raise HTTPException(status_code=404, detail="Team not found")

    policy_repo = TeamPolicyRepository(app_db)

    # Check if policy exists
    existing = await policy_repo.get_policy_by_team(team_id)

    if existing:
        # Update existing policy
        policy = await policy_repo.update_policy(
            existing.id,
            sources=body.sources,
            default_action=PolicyAction(body.default_action) if body.default_action else None,
            auto_investigate_min_severity=body.auto_investigate_min_severity,
            review_required_max_severity=body.review_required_max_severity,
        )
    else:
        # Create new policy
        action = (
            PolicyAction(body.default_action) if body.default_action else PolicyAction.ISSUE_ONLY
        )
        policy = await policy_repo.create_policy(
            org_id=auth.tenant_id,
            team_id=team_id,
            sources=body.sources or [],
            default_action=action,
            auto_investigate_min_severity=body.auto_investigate_min_severity,
            review_required_max_severity=body.review_required_max_severity,
        )

    if not policy:
        raise HTTPException(status_code=500, detail="Failed to update policy")

    return TeamPolicyResponse(
        id=policy.id,
        team_id=policy.team_id,
        sources=policy.sources,
        default_action=policy.default_action.value,
        auto_investigate_min_severity=policy.auto_investigate_min_severity,
        review_required_max_severity=policy.review_required_max_severity,
        is_active=policy.is_active,
    )


@router.post("/{team_id}/policy/overrides", response_model=TeamPolicyOverrideResponse)
@audited(action="team.policy_override_create", resource_type="team_policy_override")
async def create_policy_override(
    request: Request,
    team_id: UUID,
    body: TeamPolicyOverrideCreate,
    auth: AdminScopeDep,
    app_db: AppDbDep,
) -> TeamPolicyOverrideResponse:
    """Create a policy override for a dataset or tag.

    Requires admin scope.
    """
    async with app_db.acquire() as conn:
        teams_repo = TeamsRepository(conn)
        team = await teams_repo.get_by_id(team_id)

        if not team or team.org_id != auth.tenant_id:
            raise HTTPException(status_code=404, detail="Team not found")

    if (body.dataset_id is None) == (body.tag_id is None):
        raise HTTPException(
            status_code=400,
            detail="Exactly one of dataset_id or tag_id must be provided",
        )

    policy_repo = TeamPolicyRepository(app_db)

    override = await policy_repo.create_override(
        org_id=auth.tenant_id,
        team_id=team_id,
        dataset_id=body.dataset_id,
        tag_id=body.tag_id,
        default_action=PolicyAction(body.default_action) if body.default_action else None,
        auto_investigate_min_severity=body.auto_investigate_min_severity,
        review_required_max_severity=body.review_required_max_severity,
    )

    return TeamPolicyOverrideResponse(
        id=override.id,
        team_id=override.team_id,
        dataset_id=override.dataset_id,
        tag_id=override.tag_id,
        default_action=override.default_action.value if override.default_action else None,
        auto_investigate_min_severity=override.auto_investigate_min_severity,
        review_required_max_severity=override.review_required_max_severity,
        is_active=override.is_active,
    )


@router.put("/{team_id}/policy/overrides/{override_id}", response_model=TeamPolicyOverrideResponse)
@audited(
    action="team.policy_override_update",
    resource_type="team_policy_override",
    resource_id_param="override_id",
)
async def update_policy_override(
    request: Request,
    team_id: UUID,
    override_id: UUID,
    body: TeamPolicyOverrideUpdate,
    auth: AdminScopeDep,
    app_db: AppDbDep,
) -> TeamPolicyOverrideResponse:
    """Update a policy override.

    Requires admin scope.
    """
    policy_repo = TeamPolicyRepository(app_db)

    # Verify override exists and belongs to this team
    existing = await policy_repo.get_override(override_id)
    if not existing or existing.team_id != team_id:
        raise HTTPException(status_code=404, detail="Override not found")

    override = await policy_repo.update_override(
        override_id,
        default_action=PolicyAction(body.default_action) if body.default_action else None,
        auto_investigate_min_severity=body.auto_investigate_min_severity,
        review_required_max_severity=body.review_required_max_severity,
    )

    if not override:
        raise HTTPException(status_code=500, detail="Failed to update override")

    return TeamPolicyOverrideResponse(
        id=override.id,
        team_id=override.team_id,
        dataset_id=override.dataset_id,
        tag_id=override.tag_id,
        default_action=override.default_action.value if override.default_action else None,
        auto_investigate_min_severity=override.auto_investigate_min_severity,
        review_required_max_severity=override.review_required_max_severity,
        is_active=override.is_active,
    )


@router.delete(
    "/{team_id}/policy/overrides/{override_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
@audited(
    action="team.policy_override_delete",
    resource_type="team_policy_override",
    resource_id_param="override_id",
)
async def delete_policy_override(
    request: Request,
    team_id: UUID,
    override_id: UUID,
    auth: AdminScopeDep,
    app_db: AppDbDep,
) -> Response:
    """Delete a policy override.

    Requires admin scope.
    """
    policy_repo = TeamPolicyRepository(app_db)

    # Verify override exists and belongs to this team
    existing = await policy_repo.get_override(override_id)
    if not existing or existing.team_id != team_id:
        raise HTTPException(status_code=404, detail="Override not found")

    await policy_repo.delete_override(override_id)
    return Response(status_code=204)


@router.put("/{team_id}/policy/queue-limits", response_model=TeamQueueLimitsResponse)
@audited(action="team.queue_limits_update", resource_type="team", resource_id_param="team_id")
async def update_queue_limits(
    request: Request,
    team_id: UUID,
    body: TeamQueueLimitsUpdate,
    auth: AdminScopeDep,
    app_db: AppDbDep,
) -> TeamQueueLimitsResponse:
    """Update or create queue limits for a team.

    Requires admin scope.
    """
    async with app_db.acquire() as conn:
        teams_repo = TeamsRepository(conn)
        team = await teams_repo.get_by_id(team_id)

        if not team or team.org_id != auth.tenant_id:
            raise HTTPException(status_code=404, detail="Team not found")

    policy_repo = TeamPolicyRepository(app_db)

    # Check if limits exist
    existing = await policy_repo.get_queue_limits(team_id)

    if existing:
        # Update existing
        limits = await policy_repo.update_queue_limits(
            team_id,
            rate_limit_per_minute=body.rate_limit_per_minute,
            burst_size=body.burst_size,
            max_concurrent=body.max_concurrent,
            batch_size=body.batch_size,
        )
    else:
        # Create new
        limits = await policy_repo.create_queue_limits(
            org_id=auth.tenant_id,
            team_id=team_id,
            rate_limit_per_minute=body.rate_limit_per_minute or 60,
            burst_size=body.burst_size or 10,
            max_concurrent=body.max_concurrent or 5,
            batch_size=body.batch_size or 5,
        )

    if not limits:
        raise HTTPException(status_code=500, detail="Failed to update queue limits")

    return TeamQueueLimitsResponse(
        id=limits.id,
        team_id=limits.team_id,
        rate_limit_per_minute=limits.rate_limit_per_minute,
        burst_size=limits.burst_size,
        max_concurrent=limits.max_concurrent,
        batch_size=limits.batch_size,
        is_active=limits.is_active,
    )
