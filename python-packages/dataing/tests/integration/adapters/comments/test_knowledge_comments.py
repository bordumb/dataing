"""Integration tests for knowledge comments with real database."""

from uuid import UUID, uuid4

import pytest

from dataing.adapters.db.app_db import AppDatabase


@pytest.mark.integration
class TestKnowledgeCommentsIntegration:
    """Integration tests for knowledge comments CRUD operations."""

    async def test_create_knowledge_comment(
        self,
        migrated_db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Knowledge comment can be created."""
        comment = await migrated_db.create_knowledge_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            content="This dataset contains user events from the mobile app.",
            author_name="Data Engineer",
        )

        assert comment is not None
        assert comment["tenant_id"] == tenant_id
        assert comment["dataset_id"] == dataset_id
        assert comment["content"] == "This dataset contains user events from the mobile app."
        assert comment["author_name"] == "Data Engineer"
        assert comment["upvotes"] == 0
        assert comment["downvotes"] == 0
        assert comment["parent_id"] is None

        # Cleanup
        await migrated_db.delete_knowledge_comment(tenant_id, comment["id"])

    async def test_list_knowledge_comments(
        self,
        migrated_db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Knowledge comments can be listed for a dataset."""
        # Create test comments
        comment1 = await migrated_db.create_knowledge_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            content="First knowledge comment",
            author_name="User 1",
        )
        comment2 = await migrated_db.create_knowledge_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            content="Second knowledge comment",
            author_name="User 2",
        )

        try:
            comments = await migrated_db.list_knowledge_comments(tenant_id, dataset_id)
            comment_ids = [c["id"] for c in comments]

            assert comment1["id"] in comment_ids
            assert comment2["id"] in comment_ids
        finally:
            # Cleanup
            await migrated_db.delete_knowledge_comment(tenant_id, comment1["id"])
            await migrated_db.delete_knowledge_comment(tenant_id, comment2["id"])

    async def test_get_knowledge_comment(
        self,
        migrated_db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Single knowledge comment can be retrieved by ID."""
        comment = await migrated_db.create_knowledge_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            content="Knowledge comment for retrieval test",
            author_name="Tester",
        )

        try:
            retrieved = await migrated_db.get_knowledge_comment(tenant_id, comment["id"])

            assert retrieved is not None
            assert retrieved["id"] == comment["id"]
            assert retrieved["content"] == "Knowledge comment for retrieval test"

            # Non-existent comment returns None
            non_existent = await migrated_db.get_knowledge_comment(tenant_id, uuid4())
            assert non_existent is None
        finally:
            await migrated_db.delete_knowledge_comment(tenant_id, comment["id"])

    async def test_update_knowledge_comment(
        self,
        migrated_db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Knowledge comment content can be updated."""
        comment = await migrated_db.create_knowledge_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            content="Original knowledge content",
            author_name="Author",
        )

        try:
            updated = await migrated_db.update_knowledge_comment(
                tenant_id=tenant_id,
                comment_id=comment["id"],
                content="Updated knowledge content with better explanation",
            )

            assert updated is not None
            assert updated["id"] == comment["id"]
            assert updated["content"] == "Updated knowledge content with better explanation"
            assert updated["updated_at"] > comment["created_at"]
        finally:
            await migrated_db.delete_knowledge_comment(tenant_id, comment["id"])

    async def test_delete_knowledge_comment(
        self,
        migrated_db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Knowledge comment can be deleted."""
        comment = await migrated_db.create_knowledge_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            content="This knowledge comment will be deleted",
            author_name="Deleter",
        )

        # Delete succeeds
        result = await migrated_db.delete_knowledge_comment(tenant_id, comment["id"])
        assert result is True

        # Comment no longer exists
        retrieved = await migrated_db.get_knowledge_comment(tenant_id, comment["id"])
        assert retrieved is None

        # Deleting non-existent comment returns False
        result = await migrated_db.delete_knowledge_comment(tenant_id, uuid4())
        assert result is False

    async def test_knowledge_comment_threading(
        self,
        migrated_db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Knowledge comments support parent-child threading."""
        # Create parent comment
        parent = await migrated_db.create_knowledge_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            content="What is the SLA for this dataset?",
            author_name="Questioner",
        )

        try:
            # Create reply to parent
            reply = await migrated_db.create_knowledge_comment(
                tenant_id=tenant_id,
                dataset_id=dataset_id,
                content="The data is refreshed every 15 minutes with 99.9% availability.",
                parent_id=parent["id"],
                author_name="Answerer",
            )

            assert reply["parent_id"] == parent["id"]

            # Both appear in listing
            comments = await migrated_db.list_knowledge_comments(tenant_id, dataset_id)
            comment_ids = [c["id"] for c in comments]

            assert parent["id"] in comment_ids
            assert reply["id"] in comment_ids

            # Cleanup
            await migrated_db.delete_knowledge_comment(tenant_id, reply["id"])
        finally:
            await migrated_db.delete_knowledge_comment(tenant_id, parent["id"])

    async def test_knowledge_comment_with_author_id(
        self,
        migrated_db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Knowledge comment can be created with author_id."""
        author_id = uuid4()

        comment = await migrated_db.create_knowledge_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            content="Comment with author ID",
            author_id=author_id,
            author_name="Named Author",
        )

        try:
            assert comment["author_id"] == author_id
            assert comment["author_name"] == "Named Author"
        finally:
            await migrated_db.delete_knowledge_comment(tenant_id, comment["id"])


@pytest.mark.integration
class TestKnowledgeCommentVotingIntegration:
    """Integration tests for knowledge comment voting."""

    async def test_upvote_knowledge_comment(
        self,
        migrated_db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Knowledge comment can be upvoted."""
        comment = await migrated_db.create_knowledge_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            content="Upvote test knowledge comment",
            author_name="Author",
        )
        user_id = uuid4()

        try:
            await migrated_db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="knowledge",
                comment_id=comment["id"],
                user_id=user_id,
                vote=1,
            )

            updated = await migrated_db.get_knowledge_comment(tenant_id, comment["id"])
            assert updated is not None
            assert updated["upvotes"] == 1
            assert updated["downvotes"] == 0
        finally:
            await migrated_db.delete_comment_vote(tenant_id, "knowledge", comment["id"], user_id)
            await migrated_db.delete_knowledge_comment(tenant_id, comment["id"])

    async def test_downvote_knowledge_comment(
        self,
        migrated_db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Knowledge comment can be downvoted."""
        comment = await migrated_db.create_knowledge_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            content="Downvote test knowledge comment",
            author_name="Author",
        )
        user_id = uuid4()

        try:
            await migrated_db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="knowledge",
                comment_id=comment["id"],
                user_id=user_id,
                vote=-1,
            )

            updated = await migrated_db.get_knowledge_comment(tenant_id, comment["id"])
            assert updated is not None
            assert updated["upvotes"] == 0
            assert updated["downvotes"] == 1
        finally:
            await migrated_db.delete_comment_vote(tenant_id, "knowledge", comment["id"], user_id)
            await migrated_db.delete_knowledge_comment(tenant_id, comment["id"])

    async def test_change_vote_knowledge_comment(
        self,
        migrated_db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Vote can be changed from upvote to downvote."""
        comment = await migrated_db.create_knowledge_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            content="Change vote test knowledge comment",
            author_name="Author",
        )
        user_id = uuid4()

        try:
            # Initial upvote
            await migrated_db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="knowledge",
                comment_id=comment["id"],
                user_id=user_id,
                vote=1,
            )

            updated = await migrated_db.get_knowledge_comment(tenant_id, comment["id"])
            assert updated is not None
            assert updated["upvotes"] == 1
            assert updated["downvotes"] == 0

            # Change to downvote
            await migrated_db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="knowledge",
                comment_id=comment["id"],
                user_id=user_id,
                vote=-1,
            )

            updated = await migrated_db.get_knowledge_comment(tenant_id, comment["id"])
            assert updated is not None
            assert updated["upvotes"] == 0
            assert updated["downvotes"] == 1
        finally:
            await migrated_db.delete_comment_vote(tenant_id, "knowledge", comment["id"], user_id)
            await migrated_db.delete_knowledge_comment(tenant_id, comment["id"])

    async def test_remove_vote_knowledge_comment(
        self,
        migrated_db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Vote can be removed from knowledge comment."""
        comment = await migrated_db.create_knowledge_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            content="Remove vote test knowledge comment",
            author_name="Author",
        )
        user_id = uuid4()

        try:
            # Add vote
            await migrated_db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="knowledge",
                comment_id=comment["id"],
                user_id=user_id,
                vote=1,
            )

            updated = await migrated_db.get_knowledge_comment(tenant_id, comment["id"])
            assert updated is not None
            assert updated["upvotes"] == 1

            # Remove vote
            result = await migrated_db.delete_comment_vote(
                tenant_id, "knowledge", comment["id"], user_id
            )
            assert result is True

            updated = await migrated_db.get_knowledge_comment(tenant_id, comment["id"])
            assert updated is not None
            assert updated["upvotes"] == 0
            assert updated["downvotes"] == 0
        finally:
            await migrated_db.delete_knowledge_comment(tenant_id, comment["id"])

    async def test_multiple_users_voting_knowledge(
        self,
        migrated_db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Multiple users can vote on the same knowledge comment."""
        comment = await migrated_db.create_knowledge_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            content="Multiple voters test knowledge comment",
            author_name="Author",
        )
        user1 = uuid4()
        user2 = uuid4()
        user3 = uuid4()

        try:
            # User 1 upvotes
            await migrated_db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="knowledge",
                comment_id=comment["id"],
                user_id=user1,
                vote=1,
            )

            # User 2 upvotes
            await migrated_db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="knowledge",
                comment_id=comment["id"],
                user_id=user2,
                vote=1,
            )

            # User 3 downvotes
            await migrated_db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="knowledge",
                comment_id=comment["id"],
                user_id=user3,
                vote=-1,
            )

            updated = await migrated_db.get_knowledge_comment(tenant_id, comment["id"])
            assert updated is not None
            assert updated["upvotes"] == 2
            assert updated["downvotes"] == 1
        finally:
            await migrated_db.delete_comment_vote(tenant_id, "knowledge", comment["id"], user1)
            await migrated_db.delete_comment_vote(tenant_id, "knowledge", comment["id"], user2)
            await migrated_db.delete_comment_vote(tenant_id, "knowledge", comment["id"], user3)
            await migrated_db.delete_knowledge_comment(tenant_id, comment["id"])

    async def test_vote_ordering(
        self,
        migrated_db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Comments are ordered by vote score (upvotes - downvotes)."""
        # Create comments
        low_score = await migrated_db.create_knowledge_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            content="Low score comment",
            author_name="Author",
        )
        high_score = await migrated_db.create_knowledge_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            content="High score comment",
            author_name="Author",
        )

        user1 = uuid4()
        user2 = uuid4()

        try:
            # Give high_score comment more upvotes
            await migrated_db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="knowledge",
                comment_id=high_score["id"],
                user_id=user1,
                vote=1,
            )
            await migrated_db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="knowledge",
                comment_id=high_score["id"],
                user_id=user2,
                vote=1,
            )

            # Give low_score comment a downvote
            await migrated_db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="knowledge",
                comment_id=low_score["id"],
                user_id=user1,
                vote=-1,
            )

            comments = await migrated_db.list_knowledge_comments(tenant_id, dataset_id)

            # The dataset only has these two comments; high score comes first
            assert [c["id"] for c in comments] == [high_score["id"], low_score["id"]]
        finally:
            await migrated_db.delete_comment_vote(tenant_id, "knowledge", high_score["id"], user1)
            await migrated_db.delete_comment_vote(tenant_id, "knowledge", high_score["id"], user2)
            await migrated_db.delete_comment_vote(tenant_id, "knowledge", low_score["id"], user1)
            await migrated_db.delete_knowledge_comment(tenant_id, low_score["id"])
            await migrated_db.delete_knowledge_comment(tenant_id, high_score["id"])
