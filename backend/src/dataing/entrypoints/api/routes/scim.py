"""SCIM 2.0 provisioning endpoints.

Implements RFC 7643 (SCIM Core Schema) and RFC 7644 (SCIM Protocol).
"""

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel

from dataing.adapters.audit import audited
from dataing.core.scim import (
    SCIMError,
    SCIMGroup,
    SCIMGroupMember,
    SCIMListResponse,
    SCIMName,
    SCIMUser,
    SCIMUserEmail,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scim/v2", tags=["scim"])

# SCIM content type
SCIM_CONTENT_TYPE = "application/scim+json"


# Request/Response models
class SCIMUserCreateRequest(BaseModel):
    """SCIM user creation request."""

    schemas: list[str]
    userName: str
    name: dict[str, str] | None = None
    emails: list[dict[str, Any]] | None = None
    displayName: str | None = None
    externalId: str | None = None
    active: bool = True


class SCIMUserUpdateRequest(BaseModel):
    """SCIM user update request."""

    schemas: list[str]
    userName: str | None = None
    name: dict[str, str] | None = None
    emails: list[dict[str, Any]] | None = None
    displayName: str | None = None
    active: bool | None = None


class SCIMGroupCreateRequest(BaseModel):
    """SCIM group creation request."""

    schemas: list[str]
    displayName: str
    members: list[dict[str, str]] | None = None
    externalId: str | None = None


# Dependency to validate SCIM bearer token
async def validate_scim_token(
    authorization: Annotated[str | None, Header()] = None,
) -> UUID:
    """Validate SCIM bearer token and return org_id.

    Args:
        authorization: Authorization header.

    Returns:
        Organization ID.

    Raises:
        HTTPException: If token is invalid or missing.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # TODO: Validate token against database
    # For now, return a placeholder org_id
    # In production:
    # token = authorization.removeprefix("Bearer ")
    # org_id = await scim_repo.validate_token(token)
    # if not org_id:
    #     raise HTTPException(status_code=401, detail="Invalid token")

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="SCIM token validation not yet implemented",
    )


def scim_error_response(
    status_code: int, detail: str, scim_type: str | None = None
) -> dict[str, Any]:
    """Create SCIM error response.

    Args:
        status_code: HTTP status code.
        detail: Error detail message.
        scim_type: SCIM error type.

    Returns:
        SCIM error dict.
    """
    return SCIMError(status=status_code, detail=detail, scim_type=scim_type).to_dict()


# SCIM User Endpoints


@router.get("/Users")
async def list_users(
    org_id: Annotated[UUID, Depends(validate_scim_token)],
    filter: Annotated[str | None, Query()] = None,
    startIndex: Annotated[int, Query(ge=1)] = 1,
    count: Annotated[int, Query(ge=1, le=100)] = 100,
) -> dict[str, Any]:
    """List users (SCIM 2.0).

    Args:
        org_id: Organization ID from token.
        filter: SCIM filter expression.
        startIndex: 1-based start index for pagination.
        count: Maximum number of results.

    Returns:
        SCIM list response.
    """
    logger.info(f"SCIM list users for org {org_id}, filter={filter}")

    # TODO: Implement user listing
    # For now, return empty list
    return SCIMListResponse(
        total_results=0,
        resources=[],
        start_index=startIndex,
        items_per_page=count,
    ).to_dict()


@router.get("/Users/{user_id}")
async def get_user(
    user_id: str,
    org_id: Annotated[UUID, Depends(validate_scim_token)],
) -> dict[str, Any]:
    """Get a user by ID (SCIM 2.0).

    Args:
        user_id: User ID.
        org_id: Organization ID from token.

    Returns:
        SCIM user resource.
    """
    logger.info(f"SCIM get user {user_id} for org {org_id}")

    # TODO: Implement user lookup
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=scim_error_response(404, f"User {user_id} not found"),
    )


@router.post("/Users", status_code=status.HTTP_201_CREATED)
@audited(action="scim.user_provision", resource_type="scim_user")
async def create_user(
    body: SCIMUserCreateRequest,
    org_id: Annotated[UUID, Depends(validate_scim_token)],
) -> dict[str, Any]:
    """Create a user (SCIM 2.0).

    Args:
        body: SCIM user creation request.
        org_id: Organization ID from token.

    Returns:
        Created SCIM user resource.
    """
    logger.info(f"SCIM create user {body.userName} for org {org_id}")

    # TODO: Implement user creation
    # For now, return mock user
    user = SCIMUser(
        id=f"user-{body.userName}",
        user_name=body.userName,
        active=body.active,
        name=SCIMName(
            given_name=body.name.get("givenName") if body.name else None,
            family_name=body.name.get("familyName") if body.name else None,
        )
        if body.name
        else None,
        emails=[
            SCIMUserEmail(
                value=e.get("value", ""),
                primary=e.get("primary", False),
            )
            for e in (body.emails or [])
        ],
        display_name=body.displayName,
        external_id=body.externalId,
    )

    return user.to_dict()


@router.put("/Users/{user_id}")
@audited(action="scim.user_update", resource_type="scim_user")
async def replace_user(
    user_id: str,
    body: SCIMUserUpdateRequest,
    org_id: Annotated[UUID, Depends(validate_scim_token)],
) -> dict[str, Any]:
    """Replace a user (SCIM 2.0).

    Args:
        user_id: User ID.
        body: SCIM user update request.
        org_id: Organization ID from token.

    Returns:
        Updated SCIM user resource.
    """
    logger.info(f"SCIM replace user {user_id} for org {org_id}")

    # TODO: Implement user replacement
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=scim_error_response(404, f"User {user_id} not found"),
    )


@router.delete("/Users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
@audited(action="scim.user_deprovision", resource_type="scim_user")
async def delete_user(
    user_id: str,
    org_id: Annotated[UUID, Depends(validate_scim_token)],
) -> None:
    """Delete (deactivate) a user (SCIM 2.0).

    Args:
        user_id: User ID.
        org_id: Organization ID from token.
    """
    logger.info(f"SCIM delete user {user_id} for org {org_id}")

    # TODO: Implement user deletion/deactivation
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=scim_error_response(404, f"User {user_id} not found"),
    )


# SCIM Group Endpoints


@router.get("/Groups")
async def list_groups(
    org_id: Annotated[UUID, Depends(validate_scim_token)],
    filter: Annotated[str | None, Query()] = None,
    startIndex: Annotated[int, Query(ge=1)] = 1,
    count: Annotated[int, Query(ge=1, le=100)] = 100,
) -> dict[str, Any]:
    """List groups (SCIM 2.0).

    Args:
        org_id: Organization ID from token.
        filter: SCIM filter expression.
        startIndex: 1-based start index for pagination.
        count: Maximum number of results.

    Returns:
        SCIM list response.
    """
    logger.info(f"SCIM list groups for org {org_id}, filter={filter}")

    # TODO: Implement group listing (maps to teams)
    return SCIMListResponse(
        total_results=0,
        resources=[],
        start_index=startIndex,
        items_per_page=count,
    ).to_dict()


@router.get("/Groups/{group_id}")
async def get_group(
    group_id: str,
    org_id: Annotated[UUID, Depends(validate_scim_token)],
) -> dict[str, Any]:
    """Get a group by ID (SCIM 2.0).

    Args:
        group_id: Group ID.
        org_id: Organization ID from token.

    Returns:
        SCIM group resource.
    """
    logger.info(f"SCIM get group {group_id} for org {org_id}")

    # TODO: Implement group lookup
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=scim_error_response(404, f"Group {group_id} not found"),
    )


@router.post("/Groups", status_code=status.HTTP_201_CREATED)
@audited(action="scim.group_create", resource_type="scim_group")
async def create_group(
    body: SCIMGroupCreateRequest,
    org_id: Annotated[UUID, Depends(validate_scim_token)],
) -> dict[str, Any]:
    """Create a group (SCIM 2.0).

    Args:
        body: SCIM group creation request.
        org_id: Organization ID from token.

    Returns:
        Created SCIM group resource.
    """
    logger.info(f"SCIM create group {body.displayName} for org {org_id}")

    # TODO: Implement group creation (creates team)
    group = SCIMGroup(
        id=f"group-{body.displayName}",
        display_name=body.displayName,
        members=[
            SCIMGroupMember(
                value=m.get("value", ""),
                display=m.get("display"),
            )
            for m in (body.members or [])
        ],
        external_id=body.externalId,
    )

    return group.to_dict()


@router.delete("/Groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
@audited(action="scim.group_delete", resource_type="scim_group")
async def delete_group(
    group_id: str,
    org_id: Annotated[UUID, Depends(validate_scim_token)],
) -> None:
    """Delete a group (SCIM 2.0).

    Args:
        group_id: Group ID.
        org_id: Organization ID from token.
    """
    logger.info(f"SCIM delete group {group_id} for org {org_id}")

    # TODO: Implement group deletion
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=scim_error_response(404, f"Group {group_id} not found"),
    )
