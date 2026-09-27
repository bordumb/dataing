"""Integration tests for schema comments with real database."""

from uuid import UUID, uuid4

import pytest

from dataing.adapters.db.app_db import AppDatabase


@pytest.mark.integration
class TestSchemaCommentsIntegration:
    """Integration tests for schema comments CRUD operations."""

    async def test_create_schema_comment(
        self,
        migrated_db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Schema comment can be created."""
        comment = await migrated_db.create_schema_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            field_name="user_id",
            content="This field is the primary key for user identification.",
            author_name="Test User",
        )

        assert comment is not None
        assert comment["tenant_id"] == tenant_id
        assert comment["dataset_id"] == dataset_id
        assert comment["field_name"] == "user_id"
        assert comment["content"] == "This field is the primary key for user identification."
        assert comment["author_name"] == "Test User"
        assert comment["upvotes"] == 0
        assert comment["downvotes"] == 0

        # Cleanup
        await migrated_db.delete_schema_comment(tenant_id, comment["id"])

    async def test_list_schema_comments(
        self,
        migrated_db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Schema comments can be listed for a dataset."""
        # Create test comments
        comment1 = await migrated_db.create_schema_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            field_name="user_id",
            content="First comment",
            author_name="User 1",
        )
        comment2 = await migrated_db.create_schema_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            field_name="email",
            content="Second comment",
            author_name="User 2",
        )

        try:
            # List all comments for dataset
            comments = await migrated_db.list_schema_comments(tenant_id, dataset_id)
            comment_ids = [c["id"] for c in comments]

            assert comment1["id"] in comment_ids
            assert comment2["id"] in comment_ids

            # List comments for specific field
            field_comments = await migrated_db.list_schema_comments(
                tenant_id, dataset_id, field_name="user_id"
            )
            field_comment_ids = [c["id"] for c in field_comments]

            assert comment1["id"] in field_comment_ids
            assert comment2["id"] not in field_comment_ids
        finally:
            # Cleanup
            await migrated_db.delete_schema_comment(tenant_id, comment1["id"])
            await migrated_db.delete_schema_comment(tenant_id, comment2["id"])

    async def test_get_schema_comment(
        self,
        migrated_db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Single schema comment can be retrieved by ID."""
        comment = await migrated_db.create_schema_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            field_name="status",
            content="Status field test",
            author_name="Tester",
        )

        try:
            retrieved = await migrated_db.get_schema_comment(tenant_id, comment["id"])

            assert retrieved is not None
            assert retrieved["id"] == comment["id"]
            assert retrieved["content"] == "Status field test"
            assert retrieved["field_name"] == "status"

            # Non-existent comment returns None
            non_existent = await migrated_db.get_schema_comment(tenant_id, uuid4())
            assert non_existent is None
        finally:
            await migrated_db.delete_schema_comment(tenant_id, comment["id"])

    async def test_update_schema_comment(
        self,
        migrated_db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Schema comment content can be updated."""
        comment = await migrated_db.create_schema_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            field_name="created_at",
            content="Original content",
            author_name="Author",
        )

        try:
            updated = await migrated_db.update_schema_comment(
                tenant_id=tenant_id,
                comment_id=comment["id"],
                content="Updated content with more detail",
            )

            assert updated is not None
            assert updated["id"] == comment["id"]
            assert updated["content"] == "Updated content with more detail"
            assert updated["updated_at"] > comment["created_at"]
        finally:
            await migrated_db.delete_schema_comment(tenant_id, comment["id"])

    async def test_delete_schema_comment(
        self,
        migrated_db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Schema comment can be deleted."""
        comment = await migrated_db.create_schema_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            field_name="deleted_at",
            content="This will be deleted",
            author_name="Deleter",
        )

        # Delete succeeds
        result = await migrated_db.delete_schema_comment(tenant_id, comment["id"])
        assert result is True

        # Comment no longer exists
        retrieved = await migrated_db.get_schema_comment(tenant_id, comment["id"])
        assert retrieved is None

        # Deleting non-existent comment returns False
        result = await migrated_db.delete_schema_comment(tenant_id, uuid4())
        assert result is False

    async def test_schema_comment_threading(
        self,
        migrated_db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Schema comments support parent-child threading."""
        # Create parent comment
        parent = await migrated_db.create_schema_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            field_name="amount",
            content="Is this field always positive?",
            author_name="Questioner",
        )

        try:
            # Create reply to parent
            reply = await migrated_db.create_schema_comment(
                tenant_id=tenant_id,
                dataset_id=dataset_id,
                field_name="amount",
                content="Yes, negative values are rejected by validation.",
                parent_id=parent["id"],
                author_name="Answerer",
            )

            assert reply["parent_id"] == parent["id"]

            # Both appear in field listing
            comments = await migrated_db.list_schema_comments(
                tenant_id, dataset_id, field_name="amount"
            )
            comment_ids = [c["id"] for c in comments]

            assert parent["id"] in comment_ids
            assert reply["id"] in comment_ids

            # Cleanup
            await migrated_db.delete_schema_comment(tenant_id, reply["id"])
        finally:
            await migrated_db.delete_schema_comment(tenant_id, parent["id"])


@pytest.mark.integration
class TestSchemaCommentVotingIntegration:
    """Integration tests for schema comment voting."""

    async def test_upvote_schema_comment(
        self,
        migrated_db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Schema comment can be upvoted."""
        comment = await migrated_db.create_schema_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            field_name="vote_test",
            content="Upvote test comment",
            author_name="Author",
        )
        user_id = uuid4()

        try:
            await migrated_db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="schema",
                comment_id=comment["id"],
                user_id=user_id,
                vote=1,
            )

            updated = await migrated_db.get_schema_comment(tenant_id, comment["id"])
            assert updated is not None
            assert updated["upvotes"] == 1
            assert updated["downvotes"] == 0
        finally:
            await migrated_db.delete_comment_vote(tenant_id, "schema", comment["id"], user_id)
            await migrated_db.delete_schema_comment(tenant_id, comment["id"])

    async def test_downvote_schema_comment(
        self,
        migrated_db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Schema comment can be downvoted."""
        comment = await migrated_db.create_schema_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            field_name="downvote_test",
            content="Downvote test comment",
            author_name="Author",
        )
        user_id = uuid4()

        try:
            await migrated_db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="schema",
                comment_id=comment["id"],
                user_id=user_id,
                vote=-1,
            )

            updated = await migrated_db.get_schema_comment(tenant_id, comment["id"])
            assert updated is not None
            assert updated["upvotes"] == 0
            assert updated["downvotes"] == 1
        finally:
            await migrated_db.delete_comment_vote(tenant_id, "schema", comment["id"], user_id)
            await migrated_db.delete_schema_comment(tenant_id, comment["id"])

    async def test_change_vote_schema_comment(
        self,
        migrated_db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Vote can be changed from upvote to downvote."""
        comment = await migrated_db.create_schema_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            field_name="change_vote_test",
            content="Change vote test comment",
            author_name="Author",
        )
        user_id = uuid4()

        try:
            # Initial upvote
            await migrated_db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="schema",
                comment_id=comment["id"],
                user_id=user_id,
                vote=1,
            )

            updated = await migrated_db.get_schema_comment(tenant_id, comment["id"])
            assert updated is not None
            assert updated["upvotes"] == 1
            assert updated["downvotes"] == 0

            # Change to downvote
            await migrated_db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="schema",
                comment_id=comment["id"],
                user_id=user_id,
                vote=-1,
            )

            updated = await migrated_db.get_schema_comment(tenant_id, comment["id"])
            assert updated is not None
            assert updated["upvotes"] == 0
            assert updated["downvotes"] == 1
        finally:
            await migrated_db.delete_comment_vote(tenant_id, "schema", comment["id"], user_id)
            await migrated_db.delete_schema_comment(tenant_id, comment["id"])

    async def test_remove_vote_schema_comment(
        self,
        migrated_db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Vote can be removed from schema comment."""
        comment = await migrated_db.create_schema_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            field_name="remove_vote_test",
            content="Remove vote test comment",
            author_name="Author",
        )
        user_id = uuid4()

        try:
            # Add vote
            await migrated_db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="schema",
                comment_id=comment["id"],
                user_id=user_id,
                vote=1,
            )

            updated = await migrated_db.get_schema_comment(tenant_id, comment["id"])
            assert updated is not None
            assert updated["upvotes"] == 1

            # Remove vote
            result = await migrated_db.delete_comment_vote(
                tenant_id, "schema", comment["id"], user_id
            )
            assert result is True

            updated = await migrated_db.get_schema_comment(tenant_id, comment["id"])
            assert updated is not None
            assert updated["upvotes"] == 0
            assert updated["downvotes"] == 0
        finally:
            await migrated_db.delete_schema_comment(tenant_id, comment["id"])

    async def test_multiple_users_voting(
        self,
        migrated_db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Multiple users can vote on the same comment."""
        comment = await migrated_db.create_schema_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            field_name="multi_vote_test",
            content="Multiple voters test comment",
            author_name="Author",
        )
        user1 = uuid4()
        user2 = uuid4()
        user3 = uuid4()

        try:
            # User 1 upvotes
            await migrated_db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="schema",
                comment_id=comment["id"],
                user_id=user1,
                vote=1,
            )

            # User 2 upvotes
            await migrated_db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="schema",
                comment_id=comment["id"],
                user_id=user2,
                vote=1,
            )

            # User 3 downvotes
            await migrated_db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="schema",
                comment_id=comment["id"],
                user_id=user3,
                vote=-1,
            )

            updated = await migrated_db.get_schema_comment(tenant_id, comment["id"])
            assert updated is not None
            assert updated["upvotes"] == 2
            assert updated["downvotes"] == 1
        finally:
            await migrated_db.delete_comment_vote(tenant_id, "schema", comment["id"], user1)
            await migrated_db.delete_comment_vote(tenant_id, "schema", comment["id"], user2)
            await migrated_db.delete_comment_vote(tenant_id, "schema", comment["id"], user3)
            await migrated_db.delete_schema_comment(tenant_id, comment["id"])
