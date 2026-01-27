"""Dataset-to-repository mapping API routes."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from dataing.adapters.db.app_db import AppDatabase
from dataing.core.repo_mapping import resolve_all_repo_mappings, resolve_file_path
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import (
    ApiKeyContext,
    verify_api_key,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/dataset-repo-mappings", tags=["dataset-repo-mappings"])

AppDbDep = Annotated[AppDatabase, Depends(get_app_db)]
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]


# --- Pydantic schemas ---


class CreateRepoMappingRequest(BaseModel):
    """Request to create a dataset-to-repository mapping."""

    dataset_pattern: str = Field(..., min_length=1, max_length=500)
    pattern_type: str = Field(default="exact", pattern=r"^(exact|glob)$")
    repo_owner: str = Field(..., min_length=1, max_length=200)
    repo_name: str = Field(..., min_length=1, max_length=200)
    file_path: str | None = None
    branch: str | None = None
    job_name: str | None = None
    metadata: dict[str, Any] | None = None


class UpdateRepoMappingRequest(BaseModel):
    """Request to update a dataset-to-repository mapping."""

    dataset_pattern: str | None = Field(default=None, min_length=1, max_length=500)
    pattern_type: str | None = Field(default=None, pattern=r"^(exact|glob)$")
    repo_owner: str | None = Field(default=None, min_length=1, max_length=200)
    repo_name: str | None = Field(default=None, min_length=1, max_length=200)
    file_path: str | None = None
    branch: str | None = None
    job_name: str | None = None
    metadata: dict[str, Any] | None = None


class RepoMappingResponse(BaseModel):
    """Response for a dataset-to-repository mapping."""

    id: str
    dataset_pattern: str
    pattern_type: str
    priority: int
    repo_owner: str
    repo_name: str
    file_path: str | None
    branch: str | None
    job_name: str | None
    source: str
    confidence: float
    confirmed: bool
    metadata: dict[str, Any]
    last_verified_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None


class RepoMappingListResponse(BaseModel):
    """Response for a list of dataset-to-repository mappings."""

    items: list[RepoMappingResponse]
    total: int


# --- Helper ---


def _to_response(row: dict[str, Any]) -> RepoMappingResponse:
    """Convert a database row to a response model."""
    return RepoMappingResponse(
        id=str(row["id"]),
        dataset_pattern=row["dataset_pattern"],
        pattern_type=row["pattern_type"],
        priority=row["priority"],
        repo_owner=row["repo_owner"],
        repo_name=row["repo_name"],
        file_path=row.get("file_path"),
        branch=row.get("branch"),
        job_name=row.get("job_name"),
        source=row["source"],
        confidence=row["confidence"],
        confirmed=row["confirmed"],
        metadata=row.get("metadata", {}),
        last_verified_at=row.get("last_verified_at"),
        created_at=row["created_at"],
        updated_at=row.get("updated_at"),
    )


# --- CRUD endpoints ---


@router.post("")
async def create_repo_mapping(
    req: CreateRepoMappingRequest,
    auth: AuthDep,
    db: AppDbDep,
) -> RepoMappingResponse:
    """Create a dataset-to-repository mapping."""
    mapping_data = {
        "dataset_pattern": req.dataset_pattern.lower().strip(),
        "pattern_type": req.pattern_type,
        "repo_owner": req.repo_owner,
        "repo_name": req.repo_name,
        "file_path": req.file_path,
        "branch": req.branch,
        "job_name": req.job_name,
        "source": "manual",
        "confidence": 1.0,
        "confirmed": True,
        "priority": 0,
        "metadata": req.metadata or {},
    }
    row = await db.create_repo_mapping(auth.tenant_id, mapping_data)
    return _to_response(row)


@router.get("")
async def list_repo_mappings(
    auth: AuthDep,
    db: AppDbDep,
    source: str | None = Query(default=None),
    confirmed: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> RepoMappingListResponse:
    """List dataset-to-repository mappings with optional filters."""
    rows = await db.list_repo_mappings(
        auth.tenant_id,
        source=source,
        confirmed=confirmed,
        limit=limit,
        offset=offset,
    )
    return RepoMappingListResponse(
        items=[_to_response(r) for r in rows],
        total=len(rows),
    )


@router.put("/{mapping_id}")
async def update_repo_mapping(
    mapping_id: UUID,
    req: UpdateRepoMappingRequest,
    auth: AuthDep,
    db: AppDbDep,
) -> RepoMappingResponse:
    """Update a dataset-to-repository mapping."""
    updates = req.model_dump(exclude_none=True)
    if "dataset_pattern" in updates:
        updates["dataset_pattern"] = updates["dataset_pattern"].lower().strip()

    row = await db.update_repo_mapping(mapping_id, auth.tenant_id, updates)
    if row is None:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return _to_response(row)


@router.delete("/{mapping_id}")
async def delete_repo_mapping(
    mapping_id: UUID,
    auth: AuthDep,
    db: AppDbDep,
) -> dict[str, bool]:
    """Delete a dataset-to-repository mapping."""
    deleted = await db.delete_repo_mapping(mapping_id, auth.tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return {"deleted": True}


# --- Bulk import ---


class BulkRepoMappingItem(BaseModel):
    """Single item in a bulk import request."""

    dataset_pattern: str = Field(..., min_length=1, max_length=500)
    pattern_type: str = Field(default="exact", pattern=r"^(exact|glob)$")
    repo_owner: str = Field(..., min_length=1, max_length=200)
    repo_name: str = Field(..., min_length=1, max_length=200)
    file_path: str | None = None
    branch: str | None = None
    job_name: str | None = None


class BulkImportRequest(BaseModel):
    """Request to bulk import dataset-to-repository mappings."""

    mappings: list[BulkRepoMappingItem] = Field(..., min_length=1, max_length=1000)


class BulkImportResponse(BaseModel):
    """Response for bulk import."""

    created: int
    errors: list[str]


@router.post("/bulk")
async def bulk_import_repo_mappings(
    req: BulkImportRequest,
    auth: AuthDep,
    db: AppDbDep,
) -> BulkImportResponse:
    """Bulk import dataset-to-repository mappings."""
    created = 0
    errors: list[str] = []

    for i, item in enumerate(req.mappings):
        try:
            await db.upsert_repo_mapping(
                tenant_id=auth.tenant_id,
                dataset_pattern=item.dataset_pattern.lower().strip(),
                repo_owner=item.repo_owner,
                repo_name=item.repo_name,
                defaults={
                    "pattern_type": item.pattern_type,
                    "file_path": item.file_path,
                    "branch": item.branch,
                    "job_name": item.job_name,
                    "source": "bulk_import",
                    "confidence": 1.0,
                    "confirmed": True,
                    "priority": 0,
                    "metadata": {},
                },
            )
            created += 1
        except Exception as e:
            errors.append(f"Row {i}: {e}")

    return BulkImportResponse(created=created, errors=errors)


# --- dbt manifest import ---


class DbtManifestImportRequest(BaseModel):
    """Request metadata for dbt manifest import."""

    repo_owner: str = Field(..., min_length=1, max_length=200)
    repo_name: str = Field(..., min_length=1, max_length=200)
    branch: str | None = None


class DbtManifestImportResponse(BaseModel):
    """Response for dbt manifest import."""

    imported: int
    skipped: int
    models: list[str]


def _parse_dbt_manifest(
    manifest: dict[str, Any], repo_owner: str, repo_name: str, branch: str | None
) -> list[dict[str, Any]]:
    """Parse a dbt manifest.json and extract model mappings."""
    mappings = []
    for node_id, node in manifest.get("nodes", {}).items():
        if node.get("resource_type") != "model":
            continue
        schema = (node.get("schema") or "").lower()
        name = (node.get("name") or "").lower()
        if not schema or not name:
            continue
        mappings.append(
            {
                "dataset_pattern": f"{schema}.{name}",
                "pattern_type": "exact",
                "repo_owner": repo_owner,
                "repo_name": repo_name,
                "file_path": node.get("original_file_path"),
                "branch": branch,
                "job_name": node_id,
                "source": "dbt_manifest",
                "confirmed": False,
                "priority": 20,
                "confidence": 0.85,
                "metadata": {"dbt_unique_id": node_id},
            }
        )
    return mappings


@router.post("/import-dbt-manifest")
async def import_dbt_manifest(
    file: UploadFile,
    auth: AuthDep,
    db: AppDbDep,
    repo_owner: str = Query(..., min_length=1),
    repo_name: str = Query(..., min_length=1),
    branch: str | None = Query(default=None),
) -> DbtManifestImportResponse:
    """Import dataset-to-repository mappings from a dbt manifest.json."""
    try:
        content = await file.read()
        manifest = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid manifest file: {e}") from e

    model_mappings = _parse_dbt_manifest(manifest, repo_owner, repo_name, branch)
    if not model_mappings:
        return DbtManifestImportResponse(imported=0, skipped=0, models=[])

    imported = 0
    skipped = 0
    model_names: list[str] = []

    for mapping in model_mappings:
        try:
            await db.upsert_repo_mapping(
                tenant_id=auth.tenant_id,
                dataset_pattern=mapping["dataset_pattern"],
                repo_owner=mapping["repo_owner"],
                repo_name=mapping["repo_name"],
                defaults=mapping,
            )
            imported += 1
            model_names.append(mapping["dataset_pattern"])
        except Exception:
            logger.warning(
                "dbt_manifest_import_skip",
                dataset_pattern=mapping["dataset_pattern"],
            )
            skipped += 1

    return DbtManifestImportResponse(
        imported=imported,
        skipped=skipped,
        models=model_names,
    )


# --- Suggestions workflow ---


@router.get("/suggestions")
async def list_suggestions(
    auth: AuthDep,
    db: AppDbDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> RepoMappingListResponse:
    """List unconfirmed (suggested) dataset-to-repository mappings."""
    rows = await db.list_repo_mapping_suggestions(auth.tenant_id, limit=limit, offset=offset)
    return RepoMappingListResponse(
        items=[_to_response(r) for r in rows],
        total=len(rows),
    )


@router.post("/{mapping_id}/confirm")
async def confirm_suggestion(
    mapping_id: UUID,
    auth: AuthDep,
    db: AppDbDep,
) -> RepoMappingResponse:
    """Confirm a suggested mapping, promoting it to explicit."""
    row = await db.confirm_repo_mapping(mapping_id, auth.tenant_id)
    if row is None:
        existing = await db.get_repo_mapping(mapping_id, auth.tenant_id)
        if existing and existing.get("confirmed"):
            raise HTTPException(status_code=400, detail="Mapping already confirmed")
        raise HTTPException(status_code=404, detail="Suggestion not found")
    return _to_response(row)


@router.post("/{mapping_id}/dismiss")
async def dismiss_suggestion(
    mapping_id: UUID,
    auth: AuthDep,
    db: AppDbDep,
) -> dict[str, bool]:
    """Dismiss (delete) a suggested mapping."""
    dismissed = await db.dismiss_repo_mapping(mapping_id, auth.tenant_id)
    if not dismissed:
        existing = await db.get_repo_mapping(mapping_id, auth.tenant_id)
        if existing and existing.get("confirmed"):
            raise HTTPException(status_code=400, detail="Cannot dismiss a confirmed mapping")
        raise HTTPException(status_code=404, detail="Suggestion not found")
    return {"dismissed": True}


# --- Resolve endpoint ---


class ResolvedRepoResponse(BaseModel):
    """A resolved repository match for a dataset."""

    repo_owner: str
    repo_name: str
    file_path: str | None
    branch: str | None
    confidence: float
    source: str
    job_name: str | None


class DatasetRepoResponse(BaseModel):
    """Response for resolving a dataset's repository."""

    dataset_id: str
    primary: ResolvedRepoResponse | None = None
    all_matches: list[ResolvedRepoResponse] | None = None


def _to_resolved(row: dict[str, Any]) -> ResolvedRepoResponse:
    """Convert a mapping row to a resolved response."""
    return ResolvedRepoResponse(
        repo_owner=row["repo_owner"],
        repo_name=row["repo_name"],
        file_path=row.get("file_path"),
        branch=row.get("branch"),
        confidence=row["confidence"],
        source=row["source"],
        job_name=row.get("job_name"),
    )


# This endpoint is on a separate router to use /datasets/{id}/repo path
datasets_repo_router = APIRouter(prefix="/datasets", tags=["datasets"])


@datasets_repo_router.get("/{dataset_id}/repo")
async def resolve_dataset_repo(
    dataset_id: str,
    auth: AuthDep,
    db: AppDbDep,
    include_all: bool = Query(default=False),
) -> DatasetRepoResponse:
    """Resolve the best repository mapping for a dataset.

    Returns 200 with primary=null when no mapping found (never 404).
    This enables graceful degradation in investigations.
    """
    candidates = await db.resolve_repo_for_dataset(auth.tenant_id, dataset_id)

    # Apply glob matching in Python for non-exact patterns
    all_matches = resolve_all_repo_mappings(candidates, dataset_id)

    if not all_matches:
        return DatasetRepoResponse(dataset_id=dataset_id)

    # Resolve file path tokens for the primary match
    primary_match = dict(all_matches[0])
    primary_match["file_path"] = resolve_file_path(primary_match.get("file_path"), dataset_id)
    primary = _to_resolved(primary_match)

    result = DatasetRepoResponse(dataset_id=dataset_id, primary=primary)

    if include_all:
        resolved_all = []
        for m in all_matches:
            entry = dict(m)
            entry["file_path"] = resolve_file_path(entry.get("file_path"), dataset_id)
            resolved_all.append(_to_resolved(entry))
        result.all_matches = resolved_all

    return result
