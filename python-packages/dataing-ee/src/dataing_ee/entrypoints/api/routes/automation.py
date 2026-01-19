"""API routes for automation rules (EE)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from dataing.adapters.db.app_db import AppDatabase
from dataing.core.json_utils import to_json_string
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, require_scope, verify_api_key
from dataing_ee.core.automation.evaluator import RuleEvaluator
from dataing_ee.core.automation.executor import ActionExecutor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rules", tags=["automation"])

# Dependencies
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
AdminScopeDep = Annotated[ApiKeyContext, Depends(require_scope("admin"))]
AppDbDep = Annotated[AppDatabase, Depends(get_app_db)]


# ============================================================================
# Request/Response Schemas
# ============================================================================


class ConditionDef(BaseModel):
    """Single condition definition."""

    field: str
    operator: str = "equals"
    value: Any = None


class ConditionsDef(BaseModel):
    """Conditions definition (DSL)."""

    all: list[ConditionDef] | None = None
    any: list[ConditionDef] | None = None


class ActionDef(BaseModel):
    """Action definition."""

    type: str
    params: dict[str, Any] = Field(default_factory=dict)


class RuleCreate(BaseModel):
    """Request to create an automation rule."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    conditions: dict[str, Any] = Field(default_factory=dict)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    rate_limit_per_hour: int = Field(default=100, ge=1, le=10000)
    enabled: bool = True


class RuleUpdate(BaseModel):
    """Request to update an automation rule."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    conditions: dict[str, Any] | None = None
    actions: list[dict[str, Any]] | None = None
    rate_limit_per_hour: int | None = Field(default=None, ge=1, le=10000)
    enabled: bool | None = None


class RuleResponse(BaseModel):
    """Automation rule response."""

    id: UUID
    tenant_id: UUID
    name: str
    description: str | None
    enabled: bool
    conditions: dict[str, Any]
    actions: list[dict[str, Any]]
    rate_limit_per_hour: int
    circuit_breaker_tripped: bool
    total_executions: int
    successful_executions: int
    failed_executions: int
    last_executed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RuleListResponse(BaseModel):
    """List of automation rules response."""

    items: list[RuleResponse]
    total: int


class DryRunRequest(BaseModel):
    """Request to dry-run a rule."""

    issue_id: UUID | None = None
    sample_data: dict[str, Any] | None = None


class DryRunResult(BaseModel):
    """Dry-run result."""

    matched: bool
    matched_conditions: dict[str, Any]
    failed_conditions: list[dict[str, Any]]
    would_execute: list[dict[str, Any]]


class ExecutionResponse(BaseModel):
    """Rule execution response."""

    id: UUID
    rule_id: UUID
    issue_id: UUID
    trigger_event: str
    status: str
    actions_executed: list[dict[str, Any]]
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int | None


# ============================================================================
# Helper Functions
# ============================================================================


def _row_to_response(row: dict[str, Any]) -> RuleResponse:
    """Convert database row to response model."""
    return RuleResponse(
        id=row["id"],
        tenant_id=row["tenant_id"],
        name=row["name"],
        description=row["description"],
        enabled=row["enabled"],
        conditions=row["conditions"] or {},
        actions=row["actions"] or [],
        rate_limit_per_hour=row["rate_limit_per_hour"],
        circuit_breaker_tripped=row["circuit_breaker_tripped"],
        total_executions=row["total_executions"],
        successful_executions=row["successful_executions"],
        failed_executions=row["failed_executions"],
        last_executed_at=row["last_executed_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def _check_rate_limit(
    db: AppDatabase,
    rule_id: UUID,
    rate_limit_per_hour: int,
) -> bool:
    """Check if rule is within rate limit.

    Returns True if execution is allowed.
    """
    now = datetime.now(UTC)
    window_start = now - timedelta(hours=1)

    # Get current rate limit state
    row = await db.fetch_one(
        """
        SELECT rate_limit_window_start, rate_limit_count
        FROM automation_rules WHERE id = $1
        """,
        rule_id,
    )

    if not row:
        return False

    rule_window_start = row["rate_limit_window_start"]
    count = row["rate_limit_count"]

    # Reset window if expired
    if rule_window_start is None or rule_window_start < window_start:
        await db.execute(
            """
            UPDATE automation_rules
            SET rate_limit_window_start = $1, rate_limit_count = 1
            WHERE id = $2
            """,
            now,
            rule_id,
        )
        return True

    # Check if within limit
    if count >= rate_limit_per_hour:
        return False

    # Increment count
    await db.execute(
        "UPDATE automation_rules SET rate_limit_count = rate_limit_count + 1 WHERE id = $1",
        rule_id,
    )
    return True


async def _check_circuit_breaker(
    db: AppDatabase,
    rule_id: UUID,
    max_failures: int = 5,
    cooldown_minutes: int = 30,
) -> bool:
    """Check circuit breaker state.

    Returns True if execution is allowed.
    """
    row = await db.fetch_one(
        """
        SELECT circuit_breaker_tripped, circuit_breaker_tripped_at, consecutive_failures
        FROM automation_rules WHERE id = $1
        """,
        rule_id,
    )

    if not row:
        return False

    if row["circuit_breaker_tripped"]:
        # Check if cooldown has passed
        tripped_at = row["circuit_breaker_tripped_at"]
        if tripped_at:
            cooldown_end = tripped_at + timedelta(minutes=cooldown_minutes)
            if datetime.now(UTC) < cooldown_end:
                return False

        # Reset circuit breaker
        await db.execute(
            """
            UPDATE automation_rules
            SET circuit_breaker_tripped = false,
                circuit_breaker_tripped_at = NULL,
                consecutive_failures = 0
            WHERE id = $1
            """,
            rule_id,
        )

    return True


async def _record_success(db: AppDatabase, rule_id: UUID) -> None:
    """Record successful execution."""
    await db.execute(
        """
        UPDATE automation_rules
        SET total_executions = total_executions + 1,
            successful_executions = successful_executions + 1,
            consecutive_failures = 0,
            last_executed_at = NOW()
        WHERE id = $1
        """,
        rule_id,
    )


async def _record_failure(
    db: AppDatabase,
    rule_id: UUID,
    max_failures: int = 5,
) -> None:
    """Record failed execution and potentially trip circuit breaker."""
    await db.execute(
        """
        UPDATE automation_rules
        SET total_executions = total_executions + 1,
            failed_executions = failed_executions + 1,
            consecutive_failures = consecutive_failures + 1,
            last_executed_at = NOW()
        WHERE id = $1
        """,
        rule_id,
    )

    # Check if circuit breaker should trip
    row = await db.fetch_one(
        "SELECT consecutive_failures FROM automation_rules WHERE id = $1",
        rule_id,
    )

    if row and row["consecutive_failures"] >= max_failures:
        await db.execute(
            """
            UPDATE automation_rules
            SET circuit_breaker_tripped = true,
                circuit_breaker_tripped_at = NOW()
            WHERE id = $1
            """,
            rule_id,
        )


# ============================================================================
# API Routes
# ============================================================================


@router.get("", response_model=RuleListResponse)
async def list_rules(
    auth: AuthDep,
    db: AppDbDep,
    enabled_only: bool = False,
) -> RuleListResponse:
    """List all automation rules for the tenant."""
    if enabled_only:
        rows = await db.fetch_all(
            """
            SELECT * FROM automation_rules
            WHERE tenant_id = $1 AND enabled = true
            ORDER BY name ASC
            """,
            auth.tenant_id,
        )
    else:
        rows = await db.fetch_all(
            """
            SELECT * FROM automation_rules
            WHERE tenant_id = $1
            ORDER BY name ASC
            """,
            auth.tenant_id,
        )

    items = [_row_to_response(row) for row in rows]
    return RuleListResponse(items=items, total=len(items))


@router.post("", response_model=RuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    auth: AdminScopeDep,
    db: AppDbDep,
    body: RuleCreate,
) -> RuleResponse:
    """Create a new automation rule.

    Requires admin scope.
    """
    # Validate conditions
    evaluator = RuleEvaluator()
    cond_errors = evaluator.validate_conditions(body.conditions)
    if cond_errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid conditions: {'; '.join(cond_errors)}",
        )

    # Validate actions
    executor = ActionExecutor()
    action_errors = executor.validate_actions(body.actions)
    if action_errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid actions: {'; '.join(action_errors)}",
        )

    row = await db.fetch_one(
        """
        INSERT INTO automation_rules (
            tenant_id, name, description, conditions, actions,
            rate_limit_per_hour, enabled, created_by
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING *
        """,
        auth.tenant_id,
        body.name,
        body.description,
        to_json_string(body.conditions),
        to_json_string(body.actions),
        body.rate_limit_per_hour,
        body.enabled,
        auth.user_id,
    )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create rule",
        )

    logger.info(f"automation_rule_created: {row['id']} name={body.name} tenant={auth.tenant_id}")

    return _row_to_response(row)


@router.get("/{rule_id}", response_model=RuleResponse)
async def get_rule(
    rule_id: UUID,
    auth: AuthDep,
    db: AppDbDep,
) -> RuleResponse:
    """Get an automation rule by ID."""
    row = await db.fetch_one(
        "SELECT * FROM automation_rules WHERE id = $1 AND tenant_id = $2",
        rule_id,
        auth.tenant_id,
    )

    if not row:
        raise HTTPException(status_code=404, detail="Rule not found")

    return _row_to_response(row)


@router.patch("/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: UUID,
    auth: AdminScopeDep,
    db: AppDbDep,
    body: RuleUpdate,
) -> RuleResponse:
    """Update an automation rule.

    Requires admin scope.
    """
    # Check exists
    existing = await db.fetch_one(
        "SELECT id FROM automation_rules WHERE id = $1 AND tenant_id = $2",
        rule_id,
        auth.tenant_id,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Rule not found")

    # Validate conditions if provided
    if body.conditions is not None:
        evaluator = RuleEvaluator()
        cond_errors = evaluator.validate_conditions(body.conditions)
        if cond_errors:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid conditions: {'; '.join(cond_errors)}",
            )

    # Validate actions if provided
    if body.actions is not None:
        executor = ActionExecutor()
        action_errors = executor.validate_actions(body.actions)
        if action_errors:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid actions: {'; '.join(action_errors)}",
            )

    # Build update query
    updates = []
    params: list[Any] = []
    param_idx = 1

    if body.name is not None:
        updates.append(f"name = ${param_idx}")
        params.append(body.name)
        param_idx += 1

    if body.description is not None:
        updates.append(f"description = ${param_idx}")
        params.append(body.description)
        param_idx += 1

    if body.conditions is not None:
        updates.append(f"conditions = ${param_idx}")
        params.append(to_json_string(body.conditions))
        param_idx += 1

    if body.actions is not None:
        updates.append(f"actions = ${param_idx}")
        params.append(to_json_string(body.actions))
        param_idx += 1

    if body.rate_limit_per_hour is not None:
        updates.append(f"rate_limit_per_hour = ${param_idx}")
        params.append(body.rate_limit_per_hour)
        param_idx += 1

    if body.enabled is not None:
        updates.append(f"enabled = ${param_idx}")
        params.append(body.enabled)
        param_idx += 1

    updates.append("updated_at = NOW()")

    params.extend([rule_id, auth.tenant_id])
    query = f"""
        UPDATE automation_rules
        SET {", ".join(updates)}
        WHERE id = ${param_idx} AND tenant_id = ${param_idx + 1}
        RETURNING *
    """

    row = await db.fetch_one(query, *params)
    if not row:
        raise HTTPException(status_code=404, detail="Rule not found")

    return _row_to_response(row)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: UUID,
    auth: AdminScopeDep,
    db: AppDbDep,
) -> None:
    """Delete an automation rule.

    Requires admin scope.
    """
    existing = await db.fetch_one(
        "SELECT id FROM automation_rules WHERE id = $1 AND tenant_id = $2",
        rule_id,
        auth.tenant_id,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Rule not found")

    await db.execute("DELETE FROM automation_rules WHERE id = $1", rule_id)

    logger.info(f"automation_rule_deleted: {rule_id} tenant={auth.tenant_id}")


@router.post("/{rule_id}/dry-run", response_model=DryRunResult)
async def dry_run_rule(
    rule_id: UUID,
    auth: AuthDep,
    db: AppDbDep,
    body: DryRunRequest,
) -> DryRunResult:
    """Dry-run a rule against sample data.

    Tests what would happen if the rule matched.
    """
    # Get rule
    rule = await db.fetch_one(
        "SELECT * FROM automation_rules WHERE id = $1 AND tenant_id = $2",
        rule_id,
        auth.tenant_id,
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    # Get issue data
    if body.issue_id:
        issue = await db.fetch_one(
            """
            SELECT id, title, description, status, priority, severity,
                   source_provider, dataset_id
            FROM issues WHERE id = $1 AND tenant_id = $2
            """,
            body.issue_id,
            auth.tenant_id,
        )
        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found")

        # Get labels
        labels_rows = await db.fetch_all(
            "SELECT label FROM issue_labels WHERE issue_id = $1",
            body.issue_id,
        )
        labels = [r["label"] for r in labels_rows]

        issue_data = {
            "id": str(issue["id"]),
            "title": issue["title"],
            "description": issue["description"],
            "status": issue["status"],
            "priority": issue["priority"],
            "severity": issue["severity"],
            "source_provider": issue["source_provider"],
            "dataset_id": issue["dataset_id"],
            "labels": labels,
        }
    elif body.sample_data:
        issue_data = body.sample_data
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either issue_id or sample_data must be provided",
        )

    # Evaluate conditions
    evaluator = RuleEvaluator()
    result = evaluator.evaluate(rule["conditions"], issue_data)

    # Build would-execute list
    would_execute = []
    if result.matched:
        for action in rule["actions"]:
            would_execute.append(
                {
                    "type": action.get("type"),
                    "params": action.get("params", {}),
                }
            )

    return DryRunResult(
        matched=result.matched,
        matched_conditions=result.matched_conditions,
        failed_conditions=result.failed_conditions,
        would_execute=would_execute,
    )


@router.post("/{rule_id}/reset-circuit-breaker", response_model=RuleResponse)
async def reset_circuit_breaker(
    rule_id: UUID,
    auth: AdminScopeDep,
    db: AppDbDep,
) -> RuleResponse:
    """Reset the circuit breaker for a rule.

    Requires admin scope.
    """
    existing = await db.fetch_one(
        "SELECT id FROM automation_rules WHERE id = $1 AND tenant_id = $2",
        rule_id,
        auth.tenant_id,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Rule not found")

    row = await db.fetch_one(
        """
        UPDATE automation_rules
        SET circuit_breaker_tripped = false,
            circuit_breaker_tripped_at = NULL,
            consecutive_failures = 0,
            updated_at = NOW()
        WHERE id = $1
        RETURNING *
        """,
        rule_id,
    )

    if not row:
        raise HTTPException(status_code=404, detail="Rule not found")

    logger.info(f"circuit_breaker_reset: {rule_id} tenant={auth.tenant_id}")

    return _row_to_response(row)


@router.get("/{rule_id}/executions", response_model=list[ExecutionResponse])
async def list_rule_executions(
    rule_id: UUID,
    auth: AuthDep,
    db: AppDbDep,
    limit: int = 50,
) -> list[ExecutionResponse]:
    """List recent executions for a rule."""
    # Check rule exists and belongs to tenant
    rule = await db.fetch_one(
        "SELECT id FROM automation_rules WHERE id = $1 AND tenant_id = $2",
        rule_id,
        auth.tenant_id,
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    rows = await db.fetch_all(
        """
        SELECT * FROM rule_executions
        WHERE rule_id = $1
        ORDER BY started_at DESC
        LIMIT $2
        """,
        rule_id,
        limit,
    )

    return [
        ExecutionResponse(
            id=row["id"],
            rule_id=row["rule_id"],
            issue_id=row["issue_id"],
            trigger_event=row["trigger_event"],
            status=row["status"],
            actions_executed=row["actions_executed"] or [],
            error_message=row["error_message"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            duration_ms=row["duration_ms"],
        )
        for row in rows
    ]
