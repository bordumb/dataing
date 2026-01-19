"""Action executor for automation rules."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from dataing.adapters.db.app_db import AppDatabase
from dataing.core.json_utils import to_json_string
from dataing_ee.models.automation import ActionType

logger = logging.getLogger(__name__)


@dataclass
class ActionResult:
    """Result of executing an action."""

    action_type: str
    success: bool
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class ExecutionContext:
    """Context for action execution."""

    db: AppDatabase
    tenant_id: UUID
    issue_id: UUID
    rule_id: UUID
    dry_run: bool = False


class ActionExecutor:
    """Execute automation rule actions."""

    async def execute_actions(
        self,
        actions: list[dict[str, Any]],
        ctx: ExecutionContext,
        issue_data: dict[str, Any],
    ) -> list[ActionResult]:
        """Execute all actions for a rule.

        Args:
            actions: List of action definitions
            ctx: Execution context
            issue_data: Current issue data

        Returns:
            List of ActionResults
        """
        results: list[ActionResult] = []

        for action in actions:
            action_type = action.get("type")
            params = action.get("params", {})

            try:
                result = await self._execute_action(action_type, params, ctx, issue_data)
                results.append(result)

                # Stop on failure (fail-fast)
                if not result.success:
                    break
            except Exception as e:
                logger.exception(
                    f"action_execution_error: {action_type} rule={ctx.rule_id} issue={ctx.issue_id}"
                )
                results.append(
                    ActionResult(
                        action_type=action_type or "unknown",
                        success=False,
                        error=str(e),
                    )
                )
                break

        return results

    async def _execute_action(
        self,
        action_type: str | None,
        params: dict[str, Any],
        ctx: ExecutionContext,
        issue_data: dict[str, Any],
    ) -> ActionResult:
        """Execute a single action."""
        if not action_type:
            return ActionResult(
                action_type="unknown",
                success=False,
                error="Action type not specified",
            )

        if ctx.dry_run:
            return ActionResult(
                action_type=action_type,
                success=True,
                result={"dry_run": True, "would_execute": params},
            )

        if action_type == ActionType.SET_PRIORITY:
            return await self._set_priority(params, ctx)

        if action_type == ActionType.SET_SEVERITY:
            return await self._set_severity(params, ctx)

        if action_type == ActionType.SET_STATUS:
            return await self._set_status(params, ctx)

        if action_type == ActionType.ADD_LABEL:
            return await self._add_label(params, ctx)

        if action_type == ActionType.REMOVE_LABEL:
            return await self._remove_label(params, ctx)

        if action_type == ActionType.ASSIGN_TO:
            return await self._assign_to(params, ctx)

        if action_type == ActionType.ADD_COMMENT:
            return await self._add_comment(params, ctx)

        if action_type == ActionType.SPAWN_INVESTIGATION:
            return await self._spawn_investigation(params, ctx, issue_data)

        if action_type == ActionType.NOTIFY:
            return await self._notify(params, ctx, issue_data)

        return ActionResult(
            action_type=action_type,
            success=False,
            error=f"Unknown action type: {action_type}",
        )

    async def _set_priority(
        self,
        params: dict[str, Any],
        ctx: ExecutionContext,
    ) -> ActionResult:
        """Set issue priority."""
        value = params.get("value")
        if not value:
            return ActionResult(
                action_type=ActionType.SET_PRIORITY,
                success=False,
                error="Priority value not specified",
            )

        await ctx.db.execute(
            "UPDATE issues SET priority = $1, updated_at = NOW() WHERE id = $2",
            value,
            ctx.issue_id,
        )

        await self._record_event(
            ctx, "priority_changed", {"new_value": value, "source": "automation"}
        )

        return ActionResult(
            action_type=ActionType.SET_PRIORITY,
            success=True,
            result={"priority": value},
        )

    async def _set_severity(
        self,
        params: dict[str, Any],
        ctx: ExecutionContext,
    ) -> ActionResult:
        """Set issue severity."""
        value = params.get("value")
        if not value:
            return ActionResult(
                action_type=ActionType.SET_SEVERITY,
                success=False,
                error="Severity value not specified",
            )

        await ctx.db.execute(
            "UPDATE issues SET severity = $1, updated_at = NOW() WHERE id = $2",
            value,
            ctx.issue_id,
        )

        await self._record_event(
            ctx, "severity_changed", {"new_value": value, "source": "automation"}
        )

        return ActionResult(
            action_type=ActionType.SET_SEVERITY,
            success=True,
            result={"severity": value},
        )

    async def _set_status(
        self,
        params: dict[str, Any],
        ctx: ExecutionContext,
    ) -> ActionResult:
        """Set issue status."""
        value = params.get("value")
        if not value:
            return ActionResult(
                action_type=ActionType.SET_STATUS,
                success=False,
                error="Status value not specified",
            )

        await ctx.db.execute(
            "UPDATE issues SET status = $1, updated_at = NOW() WHERE id = $2",
            value,
            ctx.issue_id,
        )

        await self._record_event(
            ctx, "status_changed", {"new_value": value, "source": "automation"}
        )

        return ActionResult(
            action_type=ActionType.SET_STATUS,
            success=True,
            result={"status": value},
        )

    async def _add_label(
        self,
        params: dict[str, Any],
        ctx: ExecutionContext,
    ) -> ActionResult:
        """Add label to issue."""
        label = params.get("value") or params.get("label")
        if not label:
            return ActionResult(
                action_type=ActionType.ADD_LABEL,
                success=False,
                error="Label not specified",
            )

        # Use UPSERT to avoid duplicate constraint error
        await ctx.db.execute(
            """
            INSERT INTO issue_labels (issue_id, label)
            VALUES ($1, $2)
            ON CONFLICT (issue_id, label) DO NOTHING
            """,
            ctx.issue_id,
            label,
        )

        return ActionResult(
            action_type=ActionType.ADD_LABEL,
            success=True,
            result={"label": label},
        )

    async def _remove_label(
        self,
        params: dict[str, Any],
        ctx: ExecutionContext,
    ) -> ActionResult:
        """Remove label from issue."""
        label = params.get("value") or params.get("label")
        if not label:
            return ActionResult(
                action_type=ActionType.REMOVE_LABEL,
                success=False,
                error="Label not specified",
            )

        await ctx.db.execute(
            "DELETE FROM issue_labels WHERE issue_id = $1 AND label = $2",
            ctx.issue_id,
            label,
        )

        return ActionResult(
            action_type=ActionType.REMOVE_LABEL,
            success=True,
            result={"label": label},
        )

    async def _assign_to(
        self,
        params: dict[str, Any],
        ctx: ExecutionContext,
    ) -> ActionResult:
        """Assign issue to user."""
        user_id = params.get("user_id")
        if not user_id:
            return ActionResult(
                action_type=ActionType.ASSIGN_TO,
                success=False,
                error="User ID not specified",
            )

        await ctx.db.execute(
            "UPDATE issues SET assignee_id = $1, updated_at = NOW() WHERE id = $2",
            user_id,
            ctx.issue_id,
        )

        await self._record_event(
            ctx, "assigned", {"assignee_id": str(user_id), "source": "automation"}
        )

        return ActionResult(
            action_type=ActionType.ASSIGN_TO,
            success=True,
            result={"assignee_id": str(user_id)},
        )

    async def _add_comment(
        self,
        params: dict[str, Any],
        ctx: ExecutionContext,
    ) -> ActionResult:
        """Add comment to issue."""
        text = params.get("text") or params.get("comment")
        if not text:
            return ActionResult(
                action_type=ActionType.ADD_COMMENT,
                success=False,
                error="Comment text not specified",
            )

        await ctx.db.execute(
            """
            INSERT INTO issue_comments (issue_id, author_type, body)
            VALUES ($1, 'automation', $2)
            """,
            ctx.issue_id,
            text,
        )

        return ActionResult(
            action_type=ActionType.ADD_COMMENT,
            success=True,
            result={"comment_added": True},
        )

    async def _spawn_investigation(
        self,
        params: dict[str, Any],
        ctx: ExecutionContext,
        issue_data: dict[str, Any],
    ) -> ActionResult:
        """Spawn an investigation for the issue."""
        profile = params.get("profile", "standard")

        # Check if investigation already exists
        existing = await ctx.db.fetch_one(
            "SELECT id FROM investigations WHERE issue_id = $1 LIMIT 1",
            ctx.issue_id,
        )

        if existing:
            return ActionResult(
                action_type=ActionType.SPAWN_INVESTIGATION,
                success=True,
                result={
                    "investigation_id": str(existing["id"]),
                    "already_exists": True,
                },
            )

        # Create investigation
        row = await ctx.db.fetch_one(
            """
            INSERT INTO investigations (
                tenant_id, issue_id, status, source, metadata
            )
            VALUES ($1, $2, 'pending', 'automation', $3)
            RETURNING id
            """,
            ctx.tenant_id,
            ctx.issue_id,
            to_json_string({"profile": profile, "rule_id": str(ctx.rule_id)}),
        )

        if not row:
            return ActionResult(
                action_type=ActionType.SPAWN_INVESTIGATION,
                success=False,
                error="Failed to create investigation",
            )

        await self._record_event(
            ctx,
            "investigation_started",
            {"investigation_id": str(row["id"]), "source": "automation"},
        )

        return ActionResult(
            action_type=ActionType.SPAWN_INVESTIGATION,
            success=True,
            result={"investigation_id": str(row["id"])},
        )

    async def _notify(
        self,
        params: dict[str, Any],
        ctx: ExecutionContext,
        issue_data: dict[str, Any],
    ) -> ActionResult:
        """Send notification."""
        channel = params.get("channel", "email")
        recipients = params.get("recipients", [])
        template = params.get("template", "automation_rule_triggered")

        # Create notification record
        await ctx.db.execute(
            """
            INSERT INTO notifications (
                tenant_id, type, channel, recipients, template_id, context, status
            )
            VALUES ($1, 'automation', $2, $3, $4, $5, 'pending')
            """,
            ctx.tenant_id,
            channel,
            to_json_string(recipients),
            template,
            to_json_string(
                {
                    "issue_id": str(ctx.issue_id),
                    "rule_id": str(ctx.rule_id),
                    "issue_title": issue_data.get("title", ""),
                }
            ),
        )

        return ActionResult(
            action_type=ActionType.NOTIFY,
            success=True,
            result={"notification_queued": True, "channel": channel},
        )

    async def _record_event(
        self,
        ctx: ExecutionContext,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        """Record an issue event."""
        await ctx.db.execute(
            """
            INSERT INTO issue_events (issue_id, event_type, actor_user_id, payload)
            VALUES ($1, $2, NULL, $3)
            """,
            ctx.issue_id,
            event_type,
            to_json_string(payload),
        )

    def validate_actions(
        self,
        actions: list[dict[str, Any]],
    ) -> list[str]:
        """Validate action definitions.

        Returns list of validation errors (empty if valid).
        """
        errors: list[str] = []

        if not isinstance(actions, list):
            errors.append("Actions must be a list")
            return errors

        valid_types = [
            ActionType.SPAWN_INVESTIGATION,
            ActionType.SET_PRIORITY,
            ActionType.SET_SEVERITY,
            ActionType.SET_STATUS,
            ActionType.ADD_LABEL,
            ActionType.REMOVE_LABEL,
            ActionType.ASSIGN_TO,
            ActionType.NOTIFY,
            ActionType.ADD_COMMENT,
        ]

        for i, action in enumerate(actions):
            if not isinstance(action, dict):
                errors.append(f"actions[{i}]: must be a dict")
                continue

            action_type = action.get("type")
            if not action_type:
                errors.append(f"actions[{i}]: missing 'type' key")
            elif action_type not in valid_types:
                errors.append(f"actions[{i}]: invalid action type '{action_type}'")

        return errors
