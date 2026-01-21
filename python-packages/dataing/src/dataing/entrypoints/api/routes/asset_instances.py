"""Asset instances search routes for cross-datasource asset discovery."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from dataing.adapters.db.app_db import AppDatabase
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key

router = APIRouter(prefix="/asset-instances", tags=["asset-instances"])

# Annotated types for dependency injection
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
AppDbDep = Annotated[AppDatabase, Depends(get_app_db)]


class AssetInstanceResult(BaseModel):
    """Single asset instance in search results."""

    asset_urn: str = Field(
        description="Fully qualified URN: urn:dataing:{platform}:{datasource_id}:{native_path}"
    )
    display_name: str = Field(description="Human-readable table/view name")
    type: str = Field(description="Asset type: table, view, materialized_view")
    schema_name: str | None = Field(default=None, description="Database schema name")
    datasource_id: str = Field(description="Datasource ID")
    datasource_name: str = Field(description="Human-readable datasource name")
    platform: str = Field(description="Database platform type (postgres, snowflake, etc.)")
    match_reason: str = Field(
        description="Why this result matched: name_prefix, path_match, fuzzy"
    )


class AssetInstanceSearchResponse(BaseModel):
    """Response from asset instances search endpoint."""

    results: list[AssetInstanceResult]
    next_cursor: str | None = Field(
        default=None,
        description="Opaque cursor for fetching next page, null if no more results",
    )
    total_hint: int | None = Field(
        default=None,
        description="Approximate total matching results (may be expensive to compute exactly)",
    )


@router.get("/search", response_model=AssetInstanceSearchResponse)
async def search_asset_instances(
    auth: AuthDep,
    app_db: AppDbDep,
    q: str = Query(min_length=1, max_length=200, description="Search query (min 1 char)"),
    limit: int = Query(default=10, ge=1, le=100, description="Max results (default 10, max 100)"),
    cursor: str | None = Query(default=None, description="Opaque pagination cursor"),
    datasource_id: UUID | None = Query(default=None, description="Filter to single datasource"),  # noqa: B008
) -> AssetInstanceSearchResponse:
    """Search for asset instances (tables/views) across all tenant datasources.

    Returns fully qualified asset instances with datasource context,
    suitable for binding to a notebook context.

    Results are ranked by match quality:
    - name_prefix: Query matches start of table name
    - path_match: Query matches in native path
    - fuzzy: Query appears anywhere in name or path
    """
    rows, next_cursor, total_hint = await app_db.search_asset_instances(
        tenant_id=auth.tenant_id,
        query=q,
        limit=limit,
        cursor=cursor,
        datasource_id=datasource_id,
    )

    # Transform database rows to response model
    results = [
        AssetInstanceResult(
            asset_urn=f"urn:dataing:{row['platform']}:{row['datasource_id']}:{row['native_path']}",
            display_name=row["name"],
            type=row["table_type"] or "table",
            schema_name=row["schema_name"],
            datasource_id=str(row["datasource_id"]),
            datasource_name=row["datasource_name"],
            platform=row["platform"],
            match_reason=row["match_reason"],
        )
        for row in rows
    ]

    return AssetInstanceSearchResponse(
        results=results,
        next_cursor=next_cursor,
        total_hint=total_hint,
    )
