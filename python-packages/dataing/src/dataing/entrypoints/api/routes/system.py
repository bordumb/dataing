"""System status for the app's banner (docs/specs/0001_issue_chat.md §7.12)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key
from dataing.services.llm_status import LLMStatusChecker

router = APIRouter(prefix="/system", tags=["system"])

AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]


class LLMStatusResponse(BaseModel):
    """Whether the Anthropic key and models work."""

    state: str  # ok, checking, or a problem code such as invalid_key or unknown_model
    message: str  # What is wrong and what to fix, or that the key works
    models: list[str]
    checked_at: datetime | None = None


@router.get("/llm", response_model=LLMStatusResponse)
async def get_llm_status(request: Request, auth: AuthDep) -> LLMStatusResponse:
    """Return the startup check of the Anthropic key and models.

    Every page shows a banner while this reports a problem. A transient problem
    (Anthropic unreachable, overloaded) is checked again when it is over a minute old.
    """
    checker: LLMStatusChecker | None = getattr(request.app.state, "llm_status", None)
    if checker is None:
        return LLMStatusResponse(
            state="checking", message="The API key hasn't been checked yet.", models=[]
        )
    status = await checker.current()
    return LLMStatusResponse(**status.to_dict())
