"""Route authorization policy for every mutating CE route.

Viewers (and read-only API keys) keep reads plus low-risk self-actions:
comments, votes, feedback, notification read-state and watching an issue.
Changing shared state or starting work needs the write scope (members and
up). Connections that hold credentials, and tenant-wide operations, need the
admin scope.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fixtures.route_authorization import (
    ANY_USER,
    JWT_VIAS,
    PUBLIC,
    ROLE_ADMIN,
    SCOPE_ADMIN,
    SCOPE_WRITE,
    concrete_path,
    jwt_request_kwargs,
    mutating_routes,
    route_gate,
    scope_denied_detail,
    stub_service_dependencies,
)

from dataing.core.auth.types import OrgRole
from dataing.entrypoints.api.routes import api_router
from dataing.entrypoints.api.routes.datasources import router as datasources_router

POLICY: dict[tuple[str, str], str] = {
    # analytics.py: refreshes a materialized view shared by every tenant
    ("POST", "/analytics/refresh"): SCOPE_ADMIN,
    # auth.py: sign-in and account recovery
    ("POST", "/auth/login"): PUBLIC,
    ("POST", "/auth/password-reset/confirm"): PUBLIC,
    ("POST", "/auth/password-reset/recovery-method"): PUBLIC,
    ("POST", "/auth/password-reset/request"): PUBLIC,
    ("POST", "/auth/refresh"): PUBLIC,
    ("POST", "/auth/register"): PUBLIC,
    # bundles.py: read-shaped SDK calls
    ("POST", "/context/bundles"): ANY_USER,
    ("POST", "/context/diff"): ANY_USER,
    ("POST", "/context/explain"): ANY_USER,
    # comment_votes.py
    ("DELETE", "/comments/{comment_type}/{comment_id}/vote"): ANY_USER,
    ("POST", "/comments/{comment_type}/{comment_id}/vote"): ANY_USER,
    # credentials.py: the caller's own warehouse credentials
    ("DELETE", "/datasources/{datasource_id}/credentials"): SCOPE_WRITE,
    ("POST", "/datasources/{datasource_id}/credentials"): SCOPE_WRITE,
    ("POST", "/datasources/{datasource_id}/credentials/test"): SCOPE_WRITE,
    # datasources.py: managing connections is admin-only; using one needs write
    ("POST", "/datasources"): SCOPE_ADMIN,
    ("POST", "/datasources/test"): SCOPE_ADMIN,
    ("DELETE", "/datasources/{datasource_id}"): SCOPE_ADMIN,
    ("POST", "/datasources/{datasource_id}/query"): SCOPE_ADMIN,  # arbitrary SQL
    ("POST", "/datasources/{datasource_id}/stats"): ANY_USER,
    ("POST", "/datasources/{datasource_id}/sync"): SCOPE_WRITE,
    ("POST", "/datasources/{datasource_id}/test"): SCOPE_WRITE,
    # git_repos.py: a connection stores an access token
    ("POST", "/git/repos"): SCOPE_ADMIN,
    ("DELETE", "/git/repos/{repo_id}"): SCOPE_ADMIN,
    ("PUT", "/git/repos/{repo_id}"): SCOPE_ADMIN,
    ("POST", "/git/repos/{repo_id}/sync"): SCOPE_WRITE,
    # integrations.py: creates issues on behalf of an external system
    ("POST", "/integrations/webhook-generic"): SCOPE_WRITE,
    # investigation_feedback.py
    ("POST", "/investigation-feedback/"): ANY_USER,
    # investigations.py
    ("POST", "/investigations"): SCOPE_WRITE,
    ("POST", "/investigations/import"): SCOPE_WRITE,
    ("POST", "/investigations/tests/adopt"): SCOPE_WRITE,
    ("POST", "/investigations/tests/run"): SCOPE_WRITE,
    ("POST", "/investigations/{investigation_id}/cancel"): SCOPE_WRITE,
    ("POST", "/investigations/{investigation_id}/outcome-review"): SCOPE_WRITE,
    ("POST", "/investigations/{investigation_id}/codify"): SCOPE_WRITE,
    # issues.py: commenting and watching stay open to viewers
    ("POST", "/issues"): SCOPE_WRITE,
    ("PATCH", "/issues/{issue_id}"): SCOPE_WRITE,
    # issue_threads.py: kind, owner and author checks happen in the handlers
    # (test_issue_threads.py); asking the agent needs write, checked there too
    ("POST", "/issues/{issue_id}/threads"): SCOPE_WRITE,
    ("DELETE", "/issues/{issue_id}/threads/{thread_id}"): ANY_USER,
    ("POST", "/issues/{issue_id}/threads/{thread_id}/messages"): ANY_USER,
    ("PATCH", "/issues/{issue_id}/threads/{thread_id}/messages/{message_id}"): ANY_USER,
    ("DELETE", "/issues/{issue_id}/threads/{thread_id}/messages/{message_id}"): ANY_USER,
    ("POST", "/issues/{issue_id}/threads/{thread_id}/messages/{message_id}/cancel"): ANY_USER,
    ("POST", "/issues/{issue_id}/threads/{thread_id}/brief-drafts"): SCOPE_WRITE,
    ("POST", "/issues/{issue_id}/threads/{thread_id}/publish"): ANY_USER,
    ("POST", "/issues/{issue_id}/investigation-runs"): SCOPE_WRITE,
    ("DELETE", "/issues/{issue_id}/watch"): ANY_USER,
    ("POST", "/issues/{issue_id}/watch"): ANY_USER,
    # knowledge_comments.py: only authors edit (test_comment_ownership.py)
    ("POST", "/datasets/{dataset_id}/knowledge-comments"): ANY_USER,
    ("DELETE", "/datasets/{dataset_id}/knowledge-comments/{comment_id}"): ANY_USER,
    ("PATCH", "/datasets/{dataset_id}/knowledge-comments/{comment_id}"): ANY_USER,
    # notifications.py
    ("POST", "/notifications/read-all"): ANY_USER,
    ("PUT", "/notifications/{notification_id}/read"): ANY_USER,
    # permissions.py
    ("POST", "/permissions/"): SCOPE_ADMIN,
    ("DELETE", "/permissions/{grant_id}"): SCOPE_ADMIN,
    # repo_mappings.py
    ("POST", "/dataset-repo-mappings"): SCOPE_WRITE,
    ("POST", "/dataset-repo-mappings/bulk"): SCOPE_WRITE,
    ("POST", "/dataset-repo-mappings/import-dbt-manifest"): SCOPE_WRITE,
    ("DELETE", "/dataset-repo-mappings/{mapping_id}"): SCOPE_WRITE,
    ("PUT", "/dataset-repo-mappings/{mapping_id}"): SCOPE_WRITE,
    ("POST", "/dataset-repo-mappings/{mapping_id}/confirm"): SCOPE_WRITE,
    ("POST", "/dataset-repo-mappings/{mapping_id}/dismiss"): SCOPE_WRITE,
    # schema_comments.py: only authors edit (test_comment_ownership.py)
    ("POST", "/datasets/{dataset_id}/schema-comments"): ANY_USER,
    ("DELETE", "/datasets/{dataset_id}/schema-comments/{comment_id}"): ANY_USER,
    ("PATCH", "/datasets/{dataset_id}/schema-comments/{comment_id}"): ANY_USER,
    # sla_policies.py
    ("POST", "/sla-policies"): SCOPE_ADMIN,
    ("DELETE", "/sla-policies/{policy_id}"): SCOPE_ADMIN,
    ("PATCH", "/sla-policies/{policy_id}"): SCOPE_ADMIN,
    # tags.py: defining tags is admin-only; tagging an investigation needs write
    ("POST", "/investigations/{investigation_id}/tags/"): SCOPE_WRITE,
    ("DELETE", "/investigations/{investigation_id}/tags/{tag_id}"): SCOPE_WRITE,
    ("POST", "/tags/"): SCOPE_ADMIN,
    ("DELETE", "/tags/{tag_id}"): SCOPE_ADMIN,
    ("PUT", "/tags/{tag_id}"): SCOPE_ADMIN,
    # teams.py
    ("POST", "/teams/"): SCOPE_ADMIN,
    ("DELETE", "/teams/{team_id}"): SCOPE_ADMIN,
    ("PUT", "/teams/{team_id}"): SCOPE_ADMIN,
    ("POST", "/teams/{team_id}/members"): SCOPE_ADMIN,
    ("DELETE", "/teams/{team_id}/members/{user_id}"): SCOPE_ADMIN,
    ("PUT", "/teams/{team_id}/policy"): SCOPE_ADMIN,
    ("POST", "/teams/{team_id}/policy/overrides"): SCOPE_ADMIN,
    ("DELETE", "/teams/{team_id}/policy/overrides/{override_id}"): SCOPE_ADMIN,
    ("PUT", "/teams/{team_id}/policy/overrides/{override_id}"): SCOPE_ADMIN,
    ("PUT", "/teams/{team_id}/policy/queue-limits"): SCOPE_ADMIN,
    # users.py
    ("POST", "/users/"): SCOPE_ADMIN,
    ("POST", "/users/invite"): ROLE_ADMIN,
    ("DELETE", "/users/{user_id}"): SCOPE_ADMIN,
    ("PATCH", "/users/{user_id}"): SCOPE_ADMIN,
    ("POST", "/users/{user_id}/remove"): ROLE_ADMIN,
    ("PATCH", "/users/{user_id}/role"): ROLE_ADMIN,
}

# The datasources router is mounted a second time under /v2
_DATASOURCE_PATHS = {route.path for route in datasources_router.routes}
POLICY |= {
    (method, f"/v2{path}"): gate
    for (method, path), gate in list(POLICY.items())
    if path in _DATASOURCE_PATHS
}

_SCOPE_GATED = sorted(key for key, gate in POLICY.items() if gate in (SCOPE_WRITE, SCOPE_ADMIN))
_ADMIN_ONLY = sorted(key for key, gate in POLICY.items() if gate == SCOPE_ADMIN)


@pytest.fixture(scope="module")
def stub() -> MagicMock:
    """Return the stand-in for every service dependency."""
    return MagicMock()


@pytest.fixture(scope="module")
def app(stub: MagicMock) -> FastAPI:
    """Return an app serving every CE route with real auth and stubbed services."""
    app = FastAPI()
    app.include_router(api_router)
    stub_service_dependencies(app, stub)
    return app


@pytest.fixture
def client(app: FastAPI, stub: MagicMock) -> TestClient:
    """Return a client for the app, with a fresh stub.

    Server errors become 500 responses so an open gate fails the status
    assertion instead of erroring inside the handler.
    """
    stub.reset_mock()
    return TestClient(app, raise_server_exceptions=False)


def test_policy_lists_every_mutating_route(app: FastAPI) -> None:
    """A new write route needs a deliberate entry in POLICY."""
    assert set(mutating_routes(app)) == set(POLICY)


@pytest.mark.parametrize(("method", "path"), sorted(POLICY))
def test_route_enforces_its_policy(app: FastAPI, method: str, path: str) -> None:
    """Each route's dependencies enforce exactly the gate POLICY names."""
    route = mutating_routes(app)[(method, path)]

    assert route_gate(route) == POLICY[(method, path)]


@pytest.mark.parametrize("via", JWT_VIAS)
@pytest.mark.parametrize(("method", "path"), _SCOPE_GATED)
def test_viewer_is_rejected_before_the_handler(
    client: TestClient, stub: MagicMock, method: str, path: str, via: str
) -> None:
    """A viewer JWT gets 403 and no service is touched."""
    response = client.request(
        method, concrete_path(path), **jwt_request_kwargs(OrgRole.VIEWER, via)
    )

    assert response.status_code == 403
    assert response.json()["detail"] == scope_denied_detail(POLICY[(method, path)])
    assert stub.mock_calls == []


@pytest.mark.parametrize("via", JWT_VIAS)
@pytest.mark.parametrize(("method", "path"), _ADMIN_ONLY)
def test_member_is_rejected_from_admin_routes(
    client: TestClient, stub: MagicMock, method: str, path: str, via: str
) -> None:
    """A member JWT gets 403 on admin routes and no service is touched."""
    response = client.request(
        method, concrete_path(path), **jwt_request_kwargs(OrgRole.MEMBER, via)
    )

    assert response.status_code == 403
    assert response.json()["detail"] == scope_denied_detail(SCOPE_ADMIN)
    assert stub.mock_calls == []
