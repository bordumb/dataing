"""How LLM failures travel through Temporal (docs/specs/0001_issue_chat.md §7.12).

An LLM activity that the API refuses raises an ApplicationError whose type says
whether a retry can help: LLMRejected (a missing or rejected key, an unknown model,
a rejected request) is never retried; LLMUnavailable (rate limits, overload, server
and connection errors) is, by LLM_RETRY_POLICY. Its details carry the failure's code
and message, which the workflow reads back to fail the run with the reason.

Workflows import this module, so it imports nothing beyond temporalio.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError, ChildWorkflowError

if TYPE_CHECKING:
    from dataing.agents.errors import LLMFailure

LLM_REJECTED = "LLMRejected"
LLM_UNAVAILABLE = "LLMUnavailable"
# The error a failed investigation run ends with
INVESTIGATION_FAILED = "InvestigationFailed"

LLM_MAX_ATTEMPTS = 4
LLM_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=60),
    maximum_attempts=LLM_MAX_ATTEMPTS,
    non_retryable_error_types=[LLM_REJECTED],
)


def llm_activity_error(failure: LLMFailure) -> ApplicationError:
    """Return the error an activity raises for an LLM failure."""
    return ApplicationError(
        failure.message,
        failure.to_dict(),
        type=LLM_UNAVAILABLE if failure.retryable else LLM_REJECTED,
        non_retryable=not failure.retryable,
    )


def llm_failure_details(error: BaseException) -> dict[str, Any] | None:
    """Return an LLM failure's code and message from an activity or child failure.

    Temporal wraps the activity's ApplicationError in ActivityError, and a child
    workflow's failure in ChildWorkflowError; this unwraps both. `retried` is True
    when the failure was retryable, so the retry policy already gave up on it, and
    `activity` names the activity that failed.

    Returns:
        {"code", "message", "retried", "activity"}, or None when the failure wasn't
        the LLM's.
    """
    current: BaseException | None = error
    activity = None
    while isinstance(current, ChildWorkflowError | ActivityError):
        if isinstance(current, ActivityError):
            activity = current.activity_type
        current = current.cause
    if not isinstance(current, ApplicationError):
        return None
    if current.type not in (LLM_REJECTED, LLM_UNAVAILABLE):
        return None
    details = current.details[0] if current.details else {}
    if not isinstance(details, dict):
        details = {}
    return {
        "code": str(details.get("code") or "llm_error"),
        "message": str(details.get("message") or current.message),
        "retried": current.type == LLM_UNAVAILABLE,
        "activity": activity,
    }
