"""Tests for SCIM 2.0 schemas."""

from dataing_ee.core.scim import (
    SCIMError,
    SCIMGroup,
    SCIMGroupMember,
    SCIMListResponse,
    SCIMName,
    SCIMPatchOp,
    SCIMPatchOperation,
    SCIMUser,
    SCIMUserEmail,
)
from dataing_ee.core.scim.schemas import (
    SCIM_ERROR_SCHEMA,
    SCIM_GROUP_SCHEMA,
    SCIM_LIST_SCHEMA,
    SCIM_USER_SCHEMA,
)


class TestSCIMUser:
    """Tests for SCIMUser."""

    def test_minimal_user(self) -> None:
        """Can create user with minimal fields."""
        user = SCIMUser(id="user-123", user_name="alice@example.com")
        result = user.to_dict()

        assert result["id"] == "user-123"
        assert result["userName"] == "alice@example.com"
        assert result["active"] is True
        assert result["schemas"] == [SCIM_USER_SCHEMA]

    def test_full_user(self) -> None:
        """Can create user with all fields."""
        user = SCIMUser(
            id="user-123",
            user_name="alice@example.com",
            active=True,
            name=SCIMName(given_name="Alice", family_name="Smith"),
            emails=[SCIMUserEmail(value="alice@example.com", primary=True)],
            display_name="Alice Smith",
            external_id="ext-123",
            groups=[{"value": "group-1", "display": "Engineering"}],
        )
        result = user.to_dict()

        assert result["displayName"] == "Alice Smith"
        assert result["externalId"] == "ext-123"
        assert result["name"]["givenName"] == "Alice"
        assert result["name"]["familyName"] == "Smith"
        assert len(result["emails"]) == 1
        assert result["emails"][0]["value"] == "alice@example.com"
        assert result["emails"][0]["primary"] is True


class TestSCIMGroup:
    """Tests for SCIMGroup."""

    def test_empty_group(self) -> None:
        """Can create group with no members."""
        group = SCIMGroup(id="group-123", display_name="Engineering")
        result = group.to_dict()

        assert result["id"] == "group-123"
        assert result["displayName"] == "Engineering"
        assert result["schemas"] == [SCIM_GROUP_SCHEMA]
        assert "members" not in result

    def test_group_with_members(self) -> None:
        """Can create group with members."""
        group = SCIMGroup(
            id="group-123",
            display_name="Engineering",
            members=[
                SCIMGroupMember(value="user-1", display="Alice"),
                SCIMGroupMember(value="user-2", display="Bob"),
            ],
        )
        result = group.to_dict()

        assert len(result["members"]) == 2
        assert result["members"][0]["value"] == "user-1"
        assert result["members"][0]["display"] == "Alice"


class TestSCIMListResponse:
    """Tests for SCIMListResponse."""

    def test_empty_list(self) -> None:
        """Can create empty list response."""
        response = SCIMListResponse(total_results=0, resources=[])
        result = response.to_dict()

        assert result["totalResults"] == 0
        assert result["Resources"] == []
        assert result["schemas"] == [SCIM_LIST_SCHEMA]

    def test_paginated_list(self) -> None:
        """Can create paginated list response."""
        response = SCIMListResponse(
            total_results=150,
            resources=[{"id": "1"}, {"id": "2"}],
            start_index=101,
            items_per_page=50,
        )
        result = response.to_dict()

        assert result["totalResults"] == 150
        assert result["startIndex"] == 101
        assert result["itemsPerPage"] == 50
        assert len(result["Resources"]) == 2


class TestSCIMError:
    """Tests for SCIMError."""

    def test_basic_error(self) -> None:
        """Can create basic error response."""
        error = SCIMError(status=404, detail="User not found")
        result = error.to_dict()

        assert result["status"] == "404"  # SCIM spec requires string
        assert result["detail"] == "User not found"
        assert result["schemas"] == [SCIM_ERROR_SCHEMA]

    def test_error_with_scim_type(self) -> None:
        """Can create error with SCIM type."""
        error = SCIMError(status=400, detail="Invalid filter", scim_type="invalidFilter")
        result = error.to_dict()

        assert result["scimType"] == "invalidFilter"


class TestSCIMPatchOperation:
    """Tests for SCIMPatchOperation."""

    def test_add_operation(self) -> None:
        """Can create add operation."""
        op = SCIMPatchOperation(op=SCIMPatchOp.ADD, path="members", value=["user-1"])
        result = op.to_dict()

        assert result["op"] == "add"
        assert result["path"] == "members"
        assert result["value"] == ["user-1"]

    def test_remove_operation(self) -> None:
        """Can create remove operation."""
        op = SCIMPatchOperation(op=SCIMPatchOp.REMOVE, path="members[value eq 'user-1']")
        result = op.to_dict()

        assert result["op"] == "remove"
        assert result["path"] == "members[value eq 'user-1']"
        assert "value" not in result

    def test_replace_operation(self) -> None:
        """Can create replace operation."""
        op = SCIMPatchOperation(op=SCIMPatchOp.REPLACE, path="active", value=False)
        result = op.to_dict()

        assert result["op"] == "replace"
        assert result["value"] is False
