"""GET /system/llm: whether the Anthropic key and models work (spec 0001 §7.12)."""

from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key
from dataing.entrypoints.api.routes.system import router
from dataing.services.llm_status import LLMStatusChecker


def _client(checker: LLMStatusChecker | None, *, signed_in: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    if checker is not None:
        app.state.llm_status = checker
    if signed_in:
        app.dependency_overrides[verify_api_key] = lambda: ApiKeyContext(
            key_id=uuid4(),
            tenant_id=uuid4(),
            tenant_slug="t",
            tenant_name="T",
            user_id=uuid4(),
            scopes=["read"],
        )
    return TestClient(app)


async def test_any_signed_in_person_sees_the_last_check() -> None:
    """Viewers see the banner too: a broken key affects everyone."""
    checker = LLMStatusChecker(api_key="", models=["claude-opus-5-5"])
    await checker.check()

    response = _client(checker).get("/api/v1/system/llm")

    assert response.status_code == 200
    body = response.json()
    assert (body["state"], body["models"]) == ("missing_key", ["claude-opus-5-5"])
    assert body["message"].startswith("ANTHROPIC_API_KEY isn't set")
    assert body["checked_at"] is not None


def test_before_any_check_the_state_is_checking() -> None:
    """An app without a checker (tests, scripts) reports nothing wrong yet."""
    response = _client(None).get("/api/v1/system/llm")

    assert response.status_code == 200
    assert response.json()["state"] == "checking"


def test_it_needs_a_signed_in_caller() -> None:
    """The status names the configured models, so it isn't public."""
    response = _client(None, signed_in=False).get("/api/v1/system/llm")

    assert response.status_code == 401
