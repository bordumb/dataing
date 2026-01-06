"""Teams API routes."""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.rbac import TeamsRepository
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, require_scope, verify_api_key

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
async def create_team(
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
async def update_team(
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
async def delete_team(
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

        return await repo.get_members(team_id)


@router.post("/{team_id}/members", status_code=status.HTTP_201_CREATED)
async def add_team_member(
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
async def remove_team_member(
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
