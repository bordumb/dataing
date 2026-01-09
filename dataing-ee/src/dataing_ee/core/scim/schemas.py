"""SCIM 2.0 schema definitions.

Based on RFC 7643 (SCIM Core Schema) and RFC 7644 (SCIM Protocol).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# SCIM Schema URNs
SCIM_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
SCIM_GROUP_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Group"
SCIM_ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"
SCIM_PATCH_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
SCIM_LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"


class SCIMPatchOp(str, Enum):
    """SCIM patch operation types."""

    ADD = "add"
    REMOVE = "remove"
    REPLACE = "replace"


@dataclass
class SCIMName:
    """SCIM user name component."""

    formatted: str | None = None
    family_name: str | None = None
    given_name: str | None = None
    middle_name: str | None = None
    honorific_prefix: str | None = None
    honorific_suffix: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to SCIM JSON format."""
        result: dict[str, Any] = {}
        if self.formatted:
            result["formatted"] = self.formatted
        if self.family_name:
            result["familyName"] = self.family_name
        if self.given_name:
            result["givenName"] = self.given_name
        if self.middle_name:
            result["middleName"] = self.middle_name
        if self.honorific_prefix:
            result["honorificPrefix"] = self.honorific_prefix
        if self.honorific_suffix:
            result["honorificSuffix"] = self.honorific_suffix
        return result


@dataclass
class SCIMUserEmail:
    """SCIM user email address."""

    value: str
    primary: bool = False
    type: str = "work"

    def to_dict(self) -> dict[str, Any]:
        """Convert to SCIM JSON format."""
        return {
            "value": self.value,
            "primary": self.primary,
            "type": self.type,
        }


@dataclass
class SCIMGroupMember:
    """SCIM group member reference."""

    value: str  # User ID
    display: str | None = None
    type: str = "User"

    def to_dict(self) -> dict[str, Any]:
        """Convert to SCIM JSON format."""
        result: dict[str, Any] = {"value": self.value, "type": self.type}
        if self.display:
            result["display"] = self.display
        return result


@dataclass
class SCIMUser:
    """SCIM 2.0 User resource."""

    id: str
    user_name: str
    active: bool = True
    name: SCIMName | None = None
    emails: list[SCIMUserEmail] = field(default_factory=list)
    display_name: str | None = None
    external_id: str | None = None
    groups: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to SCIM JSON format."""
        result: dict[str, Any] = {
            "schemas": [SCIM_USER_SCHEMA],
            "id": self.id,
            "userName": self.user_name,
            "active": self.active,
        }
        if self.name:
            result["name"] = self.name.to_dict()
        if self.emails:
            result["emails"] = [e.to_dict() for e in self.emails]
        if self.display_name:
            result["displayName"] = self.display_name
        if self.external_id:
            result["externalId"] = self.external_id
        if self.groups:
            result["groups"] = self.groups
        return result


@dataclass
class SCIMGroup:
    """SCIM 2.0 Group resource."""

    id: str
    display_name: str
    members: list[SCIMGroupMember] = field(default_factory=list)
    external_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to SCIM JSON format."""
        result: dict[str, Any] = {
            "schemas": [SCIM_GROUP_SCHEMA],
            "id": self.id,
            "displayName": self.display_name,
        }
        if self.members:
            result["members"] = [m.to_dict() for m in self.members]
        if self.external_id:
            result["externalId"] = self.external_id
        return result


@dataclass
class SCIMPatchOperation:
    """SCIM patch operation."""

    op: SCIMPatchOp
    path: str | None = None
    value: Any = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to SCIM JSON format."""
        result: dict[str, Any] = {"op": self.op.value}
        if self.path:
            result["path"] = self.path
        if self.value is not None:
            result["value"] = self.value
        return result


@dataclass
class SCIMListResponse:
    """SCIM list response for paginated results."""

    total_results: int
    resources: list[dict[str, Any]]
    start_index: int = 1
    items_per_page: int = 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to SCIM JSON format."""
        return {
            "schemas": [SCIM_LIST_SCHEMA],
            "totalResults": self.total_results,
            "startIndex": self.start_index,
            "itemsPerPage": self.items_per_page,
            "Resources": self.resources,
        }


@dataclass
class SCIMError:
    """SCIM error response."""

    status: int
    detail: str
    scim_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to SCIM JSON format."""
        result: dict[str, Any] = {
            "schemas": [SCIM_ERROR_SCHEMA],
            "status": str(self.status),
            "detail": self.detail,
        }
        if self.scim_type:
            result["scimType"] = self.scim_type
        return result
