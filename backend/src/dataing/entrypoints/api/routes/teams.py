"""Team management API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from dataing.adapters.auth.postgres import PostgresAuthRepository
from dataing.entrypoints.api.middleware.jwt_auth import (
    JwtContext,
    RequireAdmin,
    verify_jwt,
)

router = APIRouter(tags=["teams"])


class CreateTeamRequest(BaseModel):
    """Request to create a team."""

    name: str


class TeamResponse(BaseModel):
    """Team response model."""

    id: str
    name: str
    org_id: str
    created_at: str


class TeamMemberResponse(BaseModel):
    """Team member response model."""

    user_id: str
    user_email: str
    user_name: str | None


def get_repo(request: Request) -> PostgresAuthRepository:
    """Get auth repository from request context."""
    app_db = request.app.state.app_db
    return PostgresAuthRepository(app_db)


@router.get("")
async def list_teams(
    request: Request,
    auth: Annotated[JwtContext, Depends(verify_jwt)],
    repo: Annotated[PostgresAuthRepository, Depends(get_repo)],
) -> list[TeamResponse]:
    """List all teams in current organization."""
    teams = await repo.get_org_teams(auth.org_uuid)

    return [
        TeamResponse(
            id=str(team.id),
            name=team.name,
            org_id=str(team.org_id),
            created_at=team.created_at.isoformat(),
        )
        for team in teams
    ]


@router.post("", status_code=201)
async def create_team(
    body: CreateTeamRequest,
    auth: RequireAdmin,
    repo: Annotated[PostgresAuthRepository, Depends(get_repo)],
) -> TeamResponse:
    """Create a new team (admin only)."""
    org_id = auth.org_uuid

    team = await repo.create_team(org_id, body.name)

    return TeamResponse(
        id=str(team.id),
        name=team.name,
        org_id=str(team.org_id),
        created_at=team.created_at.isoformat(),
    )


@router.get("/{team_id}")
async def get_team(
    team_id: UUID,
    auth: Annotated[JwtContext, Depends(verify_jwt)],
    repo: Annotated[PostgresAuthRepository, Depends(get_repo)],
) -> TeamResponse:
    """Get a specific team."""
    team = await repo.get_team_by_id(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Verify team belongs to user's org
    if team.org_id != auth.org_uuid:
        raise HTTPException(status_code=404, detail="Team not found")

    return TeamResponse(
        id=str(team.id),
        name=team.name,
        org_id=str(team.org_id),
        created_at=team.created_at.isoformat(),
    )


@router.delete("/{team_id}", status_code=204)
async def delete_team(
    team_id: UUID,
    auth: RequireAdmin,
    repo: Annotated[PostgresAuthRepository, Depends(get_repo)],
) -> None:
    """Delete a team (admin only)."""
    team = await repo.get_team_by_id(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Verify team belongs to user's org
    if team.org_id != auth.org_uuid:
        raise HTTPException(status_code=404, detail="Team not found")

    await repo.delete_team(team_id)


@router.post("/{team_id}/members", status_code=201)
async def add_team_member(
    team_id: UUID,
    auth: RequireAdmin,
    repo: Annotated[PostgresAuthRepository, Depends(get_repo)],
    user_id: UUID | None = None,
) -> dict[str, str]:
    """Add a user to a team (admin only)."""
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    team = await repo.get_team_by_id(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Verify team belongs to user's org
    if team.org_id != auth.org_uuid:
        raise HTTPException(status_code=404, detail="Team not found")

    membership = await repo.add_user_to_team(user_id, team_id)

    return {
        "user_id": str(membership.user_id),
        "team_id": str(membership.team_id),
        "created_at": membership.created_at.isoformat(),
    }
