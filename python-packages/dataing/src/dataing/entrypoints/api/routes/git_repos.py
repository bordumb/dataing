"""Git repository connection API routes."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.git import GitHubProvider, GitSyncService
from dataing.config import settings
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import (
    ApiKeyContext,
    require_scope,
    verify_api_key,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/git", tags=["git"])

AppDbDep = Annotated[AppDatabase, Depends(get_app_db)]
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
WriteScopeDep = Annotated[ApiKeyContext, Depends(require_scope("write"))]
AdminScopeDep = Annotated[ApiKeyContext, Depends(require_scope("admin"))]


# --- Pydantic schemas ---


class ConnectGitRepoRequest(BaseModel):
    """Request to connect a git repository."""

    name: str = Field(..., min_length=1, max_length=200)
    url: str = Field(..., min_length=1, max_length=500)
    provider: str = Field(..., pattern=r"^(github|gitlab|bitbucket)$")
    access_token: str | None = None  # Encrypted before storage
    tracked_paths: list[str] | None = None
    default_branch: str = "main"


class UpdateGitRepoRequest(BaseModel):
    """Request to update a git repository."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    tracked_paths: list[str] | None = None
    default_branch: str | None = None


class GitRepoResponse(BaseModel):
    """Response for a git repository."""

    id: str
    name: str
    url: str
    provider: str
    tracked_paths: list[str] | None
    default_branch: str
    last_sync_at: datetime | None
    sync_status: str
    sync_error: str | None
    created_at: datetime
    updated_at: datetime | None


class GitRepoListResponse(BaseModel):
    """Response for a list of git repositories."""

    items: list[GitRepoResponse]
    total: int


class CodeChangeResponse(BaseModel):
    """Response for a code change (commit)."""

    id: str
    repo_id: str
    commit_hash: str
    author_name: str | None
    author_email: str | None
    message: str | None
    committed_at: datetime | None
    affected_assets: list[dict[str, Any]]
    files_changed: list[str] | None
    created_at: datetime


class CodeChangeListResponse(BaseModel):
    """Response for a list of code changes."""

    items: list[CodeChangeResponse]
    total: int


class SyncTriggerResponse(BaseModel):
    """Response for sync trigger."""

    message: str
    sync_status: str


# --- Helper functions ---


def _to_repo_response(row: dict[str, Any]) -> GitRepoResponse:
    """Convert a database row to a GitRepoResponse."""
    return GitRepoResponse(
        id=str(row["id"]),
        name=row["name"],
        url=row["url"],
        provider=row["provider"],
        tracked_paths=row.get("tracked_paths"),
        default_branch=row.get("default_branch", "main"),
        last_sync_at=row.get("last_sync_at"),
        sync_status=row.get("sync_status", "pending"),
        sync_error=row.get("sync_error"),
        created_at=row["created_at"],
        updated_at=row.get("updated_at"),
    )


def _to_code_change_response(row: dict[str, Any]) -> CodeChangeResponse:
    """Convert a database row to a CodeChangeResponse."""
    affected = row.get("affected_assets", [])
    if isinstance(affected, str):
        affected = json.loads(affected)
    return CodeChangeResponse(
        id=str(row["id"]),
        repo_id=str(row["repo_id"]),
        commit_hash=row["commit_hash"],
        author_name=row.get("author_name"),
        author_email=row.get("author_email"),
        message=row.get("message"),
        committed_at=row.get("committed_at"),
        affected_assets=affected or [],
        files_changed=row.get("files_changed"),
        created_at=row["created_at"],
    )


def _get_sync_service(db: AppDatabase) -> GitSyncService:
    """Create a GitSyncService with configured providers."""
    providers: dict[str, Any] = {}
    if settings.github_client_id and settings.github_client_secret:
        providers["github"] = GitHubProvider(
            client_id=settings.github_client_id,
            client_secret=settings.github_client_secret,
        )
    return GitSyncService(db=db, providers=providers)


# --- CRUD endpoints ---


@router.post("/repos")
async def connect_git_repo(
    req: ConnectGitRepoRequest,
    auth: AdminScopeDep,
    db: AppDbDep,
) -> GitRepoResponse:
    """Connect a new git repository for pipeline change tracking."""
    repo_data = {
        "name": req.name,
        "url": req.url.rstrip("/"),
        "provider": req.provider,
        "access_token_encrypted": req.access_token,  # TODO: encrypt before storage
        "tracked_paths": req.tracked_paths,
        "default_branch": req.default_branch,
    }
    try:
        row = await db.create_git_repository(auth.tenant_id, repo_data)
    except Exception as exc:
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise HTTPException(
                status_code=409,
                detail="A repository with this URL already exists for this tenant.",
            ) from exc
        raise
    logger.info(
        "git_repo_connected",
        tenant_id=str(auth.tenant_id),
        repo_id=str(row["id"]),
        provider=req.provider,
    )
    return _to_repo_response(row)


@router.get("/repos")
async def list_git_repos(
    auth: AuthDep,
    db: AppDbDep,
    provider: str | None = Query(default=None, pattern=r"^(github|gitlab|bitbucket)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> GitRepoListResponse:
    """List connected git repositories."""
    rows = await db.list_git_repositories(
        auth.tenant_id,
        provider=provider,
        limit=limit,
        offset=offset,
    )
    return GitRepoListResponse(
        items=[_to_repo_response(r) for r in rows],
        total=len(rows),
    )


@router.get("/repos/{repo_id}")
async def get_git_repo(
    repo_id: UUID,
    auth: AuthDep,
    db: AppDbDep,
) -> GitRepoResponse:
    """Get a single git repository by ID."""
    row = await db.get_git_repository(repo_id, auth.tenant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    return _to_repo_response(row)


@router.put("/repos/{repo_id}")
async def update_git_repo(
    repo_id: UUID,
    req: UpdateGitRepoRequest,
    auth: AdminScopeDep,
    db: AppDbDep,
) -> GitRepoResponse:
    """Update a git repository's settings."""
    updates = req.model_dump(exclude_none=True)
    if not updates:
        # No updates provided, just return current state
        row = await db.get_git_repository(repo_id, auth.tenant_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Repository not found")
        return _to_repo_response(row)

    row = await db.update_git_repository(repo_id, auth.tenant_id, updates)
    if row is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    logger.info(
        "git_repo_updated",
        tenant_id=str(auth.tenant_id),
        repo_id=str(repo_id),
    )
    return _to_repo_response(row)


@router.delete("/repos/{repo_id}")
async def delete_git_repo(
    repo_id: UUID,
    auth: AdminScopeDep,
    db: AppDbDep,
) -> dict[str, bool]:
    """Disconnect a git repository (cascades to code_changes)."""
    deleted = await db.delete_git_repository(repo_id, auth.tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Repository not found")
    logger.info(
        "git_repo_deleted",
        tenant_id=str(auth.tenant_id),
        repo_id=str(repo_id),
    )
    return {"deleted": True}


# --- Sync endpoints ---


async def _run_sync(db: AppDatabase, repo_id: UUID, tenant_id: UUID) -> None:
    """Background task to run repository sync."""
    try:
        sync_service = _get_sync_service(db)
        await sync_service.sync_repository(repo_id, tenant_id)
    except Exception as e:
        logger.error(
            "git_sync_background_failed",
            repo_id=str(repo_id),
            error=str(e),
        )


@router.post("/repos/{repo_id}/sync", status_code=202)
async def trigger_sync(
    repo_id: UUID,
    auth: WriteScopeDep,
    db: AppDbDep,
    background_tasks: BackgroundTasks,
) -> SyncTriggerResponse:
    """Trigger an immediate sync for a repository.

    Returns 202 Accepted; sync runs in the background.
    """
    # Verify repo exists and belongs to tenant
    repo = await db.get_git_repository(repo_id, auth.tenant_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    # Check if already syncing
    if repo.get("sync_status") == "syncing":
        return SyncTriggerResponse(
            message="Sync already in progress",
            sync_status="syncing",
        )

    # Trigger background sync
    background_tasks.add_task(_run_sync, db, repo_id, auth.tenant_id)

    logger.info(
        "git_sync_triggered",
        tenant_id=str(auth.tenant_id),
        repo_id=str(repo_id),
    )
    return SyncTriggerResponse(
        message="Sync started",
        sync_status="syncing",
    )


# --- Code changes endpoints ---


@router.get("/repos/{repo_id}/changes")
async def list_repo_changes(
    repo_id: UUID,
    auth: AuthDep,
    db: AppDbDep,
    since: datetime | None = Query(default=None),  # noqa: B008
    until: datetime | None = Query(default=None),  # noqa: B008
    limit: int = Query(default=100, ge=1, le=500),  # noqa: B008
    offset: int = Query(default=0, ge=0),  # noqa: B008
) -> CodeChangeListResponse:
    """List code changes for a repository with optional time range filter."""
    # Verify repo exists and belongs to tenant
    repo = await db.get_git_repository(repo_id, auth.tenant_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    rows = await db.list_code_changes(
        repo_id,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    return CodeChangeListResponse(
        items=[_to_code_change_response(r) for r in rows],
        total=len(rows),
    )


@router.get("/changes/by-asset")
async def find_changes_by_asset(
    asset_name: str,
    auth: AuthDep,
    db: AppDbDep,
    since: datetime | None = Query(default=None),  # noqa: B008
    until: datetime | None = Query(default=None),  # noqa: B008
    limit: int = Query(default=50, ge=1, le=200),  # noqa: B008
) -> CodeChangeListResponse:
    """Find code changes affecting a given asset across all tenant repos.

    This endpoint is called by the investigation agent to correlate
    data anomalies with code changes.
    """
    rows = await db.find_code_changes_by_asset(
        auth.tenant_id,
        asset_name=asset_name,
        since=since,
        until=until,
        limit=limit,
    )
    return CodeChangeListResponse(
        items=[_to_code_change_response(r) for r in rows],
        total=len(rows),
    )
