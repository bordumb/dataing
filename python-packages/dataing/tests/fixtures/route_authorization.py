"""Route authorization helpers shared by the CE and EE policy tests.

``route_gate`` reports the gate a route enforces by walking its FastAPI
dependency tree, so a policy table can be checked against the live app.
``jwt_request_kwargs`` issues a real JWT for an org role, so gated routes are
exercised through the real verify_api_key -> require_scope chain.
"""

from __future__ import annotations

import inspect
import re
import uuid
from collections.abc import Callable, Iterator, Mapping
from typing import Any

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from dataing.core.auth.jwt import create_access_token
from dataing.core.auth.types import OrgRole
from dataing.entrypoints.api.middleware.auth import verify_api_key
from dataing.entrypoints.api.middleware.jwt_auth import ROLE_HIERARCHY, verify_jwt

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Gates a route can enforce
SCOPE_ADMIN = "scope:admin"  # admin/owner JWTs and API keys with the admin scope
ROLE_ADMIN = "role:admin"  # admin/owner JWTs only
SCOPE_WRITE = "scope:write"  # member JWTs and up, API keys with the write scope
ANY_USER = "any_user"  # any authenticated caller, viewers and read-only keys included
PUBLIC = "public"  # no auth dependency; the handler authenticates the caller, if at all

# How a JWT reaches verify_api_key: Authorization header, or ?token= for SSE
JWT_VIAS = ("bearer", "query_param")

_SCOPE_RANK = ("read", "write", "admin")
_PATH_PARAM = re.compile(r"\{[^}]+\}")

GateMap = Mapping[Callable[..., Any], str]


def _dependency_calls(dependant: Dependant) -> Iterator[Callable[..., Any]]:
    """Yield every dependency callable in a dependency tree."""
    for sub in dependant.dependencies:
        if sub.call is not None:
            yield sub.call
        yield from _dependency_calls(sub)


def _factory_arg(call: Callable[..., Any], factory: str, arg: str) -> Any:
    """Return the argument a dependency factory built this checker with, or None."""
    if not getattr(call, "__qualname__", "").startswith(f"{factory}.<locals>."):
        return None
    return inspect.getclosurevars(call).nonlocals[arg]


def _is_gate(call: Callable[..., Any], extra_gates: GateMap) -> bool:
    """Return whether a dependency authenticates or authorizes the caller."""
    return (
        call in (verify_api_key, verify_jwt)
        or call in extra_gates
        or _factory_arg(call, "require_scope", "required_scope") is not None
        or _factory_arg(call, "require_role", "min_role") is not None
    )


def route_gate(route: APIRoute, extra_gates: GateMap | None = None) -> str:
    """Return the strongest gate a route's dependencies enforce.

    Args:
        route: The route to inspect.
        extra_gates: Other auth dependencies (such as a SCIM token check),
            mapped to the gate name they report.
    """
    extra_gates = extra_gates or {}
    scopes: set[str] = set()
    roles: set[OrgRole] = set()
    named: set[str] = set()
    authenticated = False
    for call in _dependency_calls(route.dependant):
        if (scope := _factory_arg(call, "require_scope", "required_scope")) is not None:
            scopes.add(scope)
        elif (role := _factory_arg(call, "require_role", "min_role")) is not None:
            roles.add(role)
        elif call in extra_gates:
            named.add(extra_gates[call])
        elif call in (verify_api_key, verify_jwt):
            authenticated = True
    if scopes:
        return f"scope:{max(scopes, key=_SCOPE_RANK.index)}"
    if roles:
        return f"role:{max(roles, key=ROLE_HIERARCHY.index).value}"
    if named:
        return ",".join(sorted(named))
    return ANY_USER if authenticated else PUBLIC


def mutating_routes(app: FastAPI) -> dict[tuple[str, str], APIRoute]:
    """Map (method, path) to its route for every POST/PUT/PATCH/DELETE route."""
    return {
        (method, route.path): route
        for route in app.routes
        if isinstance(route, APIRoute)
        for method in route.methods & MUTATING_METHODS
    }


def stub_service_dependencies(
    app: FastAPI, stub: object, extra_gates: GateMap | None = None
) -> None:
    """Override every non-auth dependency of every route with ``stub``.

    Auth dependencies, and dependencies built on them, are kept, so requests
    still pass through the real auth chain. A handler reached by mistake can
    only touch the stub, which the caller then checks for calls.
    """
    gates = extra_gates or {}

    def visit(dependant: Dependant) -> None:
        for sub in dependant.dependencies:
            if sub.call is None or _is_gate(sub.call, gates):
                continue
            if any(_is_gate(call, gates) for call in _dependency_calls(sub)):
                visit(sub)
            else:
                app.dependency_overrides[sub.call] = lambda: stub

    for route in app.routes:
        if isinstance(route, APIRoute):
            visit(route.dependant)


def scope_denied_detail(gate: str) -> str:
    """Return the 403 detail require_scope sends for a scope gate."""
    return f"Scope '{gate.removeprefix('scope:')}' required"


def concrete_path(path: str) -> str:
    """Fill every path parameter of a route template with a fresh UUID."""
    return _PATH_PARAM.sub(lambda _: str(uuid.uuid4()), path)


def jwt_request_kwargs(
    role: OrgRole,
    via: str = "bearer",
    user_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Return request kwargs carrying a real JWT for a user with ``role``."""
    token = create_access_token(
        user_id=str(user_id or uuid.uuid4()),
        org_id=str(uuid.uuid4()),
        role=role.value,
        teams=[],
    )
    if via == "bearer":
        return {"headers": {"Authorization": f"Bearer {token}"}}
    return {"params": {"token": token}}
