"""Audit log API routes."""

import csv
from datetime import datetime
from io import StringIO
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from dataing.adapters.audit import AuditRepository

router = APIRouter(prefix="/audit-logs", tags=["audit"])


def get_audit_repo(request: Request) -> AuditRepository:
    """Get audit repository from app state.

    Args:
        request: The current request.

    Returns:
        Audit repository instance.
    """
    pool = request.app.state.db_pool
    return AuditRepository(pool=pool)


# Annotated type for dependency injection
AuditRepoDep = Annotated[AuditRepository, Depends(get_audit_repo)]


class AuditLogResponse(BaseModel):
    """Response for a single audit log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    timestamp: datetime
    actor_id: UUID | None = None
    actor_email: str | None = None
    actor_ip: str | None = None
    action: str
    resource_type: str | None = None
    resource_id: UUID | None = None
    resource_name: str | None = None
    request_method: str | None = None
    request_path: str | None = None
    status_code: int | None = None
    changes: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class AuditLogListResponse(BaseModel):
    """Paginated list of audit logs."""

    items: list[AuditLogResponse]
    total: int
    page: int
    pages: int
    limit: int


@router.get("", response_model=AuditLogListResponse)
async def list_audit_logs(
    request: Request,
    audit_repo: AuditRepoDep,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    action: str | None = None,
    actor_id: UUID | None = None,
    resource_type: str | None = None,
    search: str | None = None,
) -> AuditLogListResponse:
    """List audit logs with filtering and pagination.

    Args:
        request: The current request.
        audit_repo: Audit repository dependency.
        page: Page number (1-indexed).
        limit: Number of items per page.
        start_date: Filter entries after this date.
        end_date: Filter entries before this date.
        action: Filter by action type.
        actor_id: Filter by actor UUID.
        resource_type: Filter by resource type.
        search: Search in resource_name and action.

    Returns:
        Paginated list of audit log entries.
    """
    tenant_id: UUID = request.state.tenant_id
    offset = (page - 1) * limit

    entries, total = await audit_repo.list(
        tenant_id=tenant_id,
        limit=limit,
        offset=offset,
        start_date=start_date,
        end_date=end_date,
        action=action,
        actor_id=actor_id,
        resource_type=resource_type,
        search=search,
    )

    pages = (total + limit - 1) // limit if total > 0 else 1

    return AuditLogListResponse(
        items=[AuditLogResponse.model_validate(e) for e in entries],
        total=total,
        page=page,
        pages=pages,
        limit=limit,
    )


@router.get("/export")
async def export_audit_logs(
    request: Request,
    audit_repo: AuditRepoDep,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    action: str | None = None,
    actor_id: UUID | None = None,
    resource_type: str | None = None,
    search: str | None = None,
) -> StreamingResponse:
    """Export audit logs as CSV.

    Args:
        request: The current request.
        audit_repo: Audit repository dependency.
        start_date: Filter entries after this date.
        end_date: Filter entries before this date.
        action: Filter by action type.
        actor_id: Filter by actor UUID.
        resource_type: Filter by resource type.
        search: Search in resource_name and action.

    Returns:
        CSV file as streaming response.
    """
    tenant_id: UUID = request.state.tenant_id

    # Fetch all matching entries (up to 10000)
    entries, _ = await audit_repo.list(
        tenant_id=tenant_id,
        limit=10000,
        offset=0,
        start_date=start_date,
        end_date=end_date,
        action=action,
        actor_id=actor_id,
        resource_type=resource_type,
        search=search,
    )

    # Generate CSV
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Timestamp",
            "Actor Email",
            "Actor IP",
            "Action",
            "Resource Type",
            "Resource Name",
            "Request Method",
            "Request Path",
            "Status Code",
        ]
    )

    for entry in entries:
        writer.writerow(
            [
                entry.timestamp.isoformat(),
                entry.actor_email or "",
                entry.actor_ip or "",
                entry.action,
                entry.resource_type or "",
                entry.resource_name or "",
                entry.request_method or "",
                entry.request_path or "",
                entry.status_code or "",
            ]
        )

    output.seek(0)

    filename = f"audit-logs-{datetime.now().strftime('%Y%m%d')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/{entry_id}", response_model=AuditLogResponse)
async def get_audit_log(
    request: Request,
    entry_id: UUID,
    audit_repo: AuditRepoDep,
) -> AuditLogResponse:
    """Get a single audit log entry.

    Args:
        request: The current request.
        entry_id: UUID of the audit log entry.
        audit_repo: Audit repository dependency.

    Returns:
        Audit log entry details.

    Raises:
        HTTPException: If entry not found (404).
    """
    tenant_id: UUID = request.state.tenant_id

    entry = await audit_repo.get(tenant_id=tenant_id, entry_id=entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Audit log entry not found")

    return AuditLogResponse.model_validate(entry)
