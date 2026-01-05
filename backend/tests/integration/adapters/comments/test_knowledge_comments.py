"""Integration tests for knowledge comments with real database."""

from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import pytest
from dataing.adapters.db.app_db import AppDatabase


@pytest.mark.integration
class TestKnowledgeCommentsIntegration:
    """Integration tests for knowledge comments CRUD operations."""

    @pytest.fixture
    async def db(self) -> AsyncGenerator[AppDatabase, None]:
        """Create database connection."""
        db = AppDatabase(dsn="postgresql://localhost/dataing")  # pragma: allowlist secret
        try:
            await db.connect()
        except Exception as e:
            pytest.skip(f"Database not available: {e}")
        yield db
        await db.close()

    @pytest.fixture
    async def tenant_id(self, db: AppDatabase) -> UUID:
        """Get a valid tenant ID from the database."""
        tenant = await db.fetch_one("SELECT id FROM tenants LIMIT 1")
        if not tenant:
            pytest.skip("No tenant in database")
        return tenant["id"]

    @pytest.fixture
    async def dataset_id(self, db: AppDatabase, tenant_id: UUID) -> UUID:
        """Get a valid dataset ID from the database."""
        dataset = await db.fetch_one(
            "SELECT id FROM datasets WHERE tenant_id = $1 LIMIT 1",
            tenant_id,
        )
        if not dataset:
            pytest.skip("No dataset in database")
        return dataset["id"]

    async def test_create_knowledge_comment(
        self,
        db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Knowledge comment can be created."""
        comment = await db.create_knowledge_comment(
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
        await db.delete_knowledge_comment(tenant_id, comment["id"])

    async def test_list_knowledge_comments(
        self,
        db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Knowledge comments can be listed for a dataset."""
        # Create test comments
        comment1 = await db.create_knowledge_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            content="First knowledge comment",
            author_name="User 1",
        )
        comment2 = await db.create_knowledge_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            content="Second knowledge comment",
            author_name="User 2",
        )

        try:
            comments = await db.list_knowledge_comments(tenant_id, dataset_id)
            comment_ids = [c["id"] for c in comments]

            assert comment1["id"] in comment_ids
            assert comment2["id"] in comment_ids
        finally:
            # Cleanup
            await db.delete_knowledge_comment(tenant_id, comment1["id"])
            await db.delete_knowledge_comment(tenant_id, comment2["id"])

    async def test_get_knowledge_comment(
        self,
        db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Single knowledge comment can be retrieved by ID."""
        comment = await db.create_knowledge_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            content="Knowledge comment for retrieval test",
            author_name="Tester",
        )

        try:
            retrieved = await db.get_knowledge_comment(tenant_id, comment["id"])

            assert retrieved is not None
            assert retrieved["id"] == comment["id"]
            assert retrieved["content"] == "Knowledge comment for retrieval test"

            # Non-existent comment returns None
            non_existent = await db.get_knowledge_comment(tenant_id, uuid4())
            assert non_existent is None
        finally:
            await db.delete_knowledge_comment(tenant_id, comment["id"])

    async def test_update_knowledge_comment(
        self,
        db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Knowledge comment content can be updated."""
        comment = await db.create_knowledge_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            content="Original knowledge content",
            author_name="Author",
        )

        try:
            updated = await db.update_knowledge_comment(
                tenant_id=tenant_id,
                comment_id=comment["id"],
                content="Updated knowledge content with better explanation",
            )

            assert updated is not None
            assert updated["id"] == comment["id"]
            assert updated["content"] == "Updated knowledge content with better explanation"
            assert updated["updated_at"] > comment["created_at"]
        finally:
            await db.delete_knowledge_comment(tenant_id, comment["id"])

    async def test_delete_knowledge_comment(
        self,
        db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Knowledge comment can be deleted."""
        comment = await db.create_knowledge_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            content="This knowledge comment will be deleted",
            author_name="Deleter",
        )

        # Delete succeeds
        result = await db.delete_knowledge_comment(tenant_id, comment["id"])
        assert result is True

        # Comment no longer exists
        retrieved = await db.get_knowledge_comment(tenant_id, comment["id"])
        assert retrieved is None

        # Deleting non-existent comment returns False
        result = await db.delete_knowledge_comment(tenant_id, uuid4())
        assert result is False

    async def test_knowledge_comment_threading(
        self,
        db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Knowledge comments support parent-child threading."""
        # Create parent comment
        parent = await db.create_knowledge_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            content="What is the SLA for this dataset?",
            author_name="Questioner",
        )

        try:
            # Create reply to parent
            reply = await db.create_knowledge_comment(
                tenant_id=tenant_id,
                dataset_id=dataset_id,
                content="The data is refreshed every 15 minutes with 99.9% availability.",
                parent_id=parent["id"],
                author_name="Answerer",
            )

            assert reply["parent_id"] == parent["id"]

            # Both appear in listing
            comments = await db.list_knowledge_comments(tenant_id, dataset_id)
            comment_ids = [c["id"] for c in comments]

            assert parent["id"] in comment_ids
            assert reply["id"] in comment_ids

            # Cleanup
            await db.delete_knowledge_comment(tenant_id, reply["id"])
        finally:
            await db.delete_knowledge_comment(tenant_id, parent["id"])

    async def test_knowledge_comment_with_author_id(
        self,
        db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Knowledge comment can be created with author_id."""
        author_id = uuid4()

        comment = await db.create_knowledge_comment(
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
            await db.delete_knowledge_comment(tenant_id, comment["id"])


@pytest.mark.integration
class TestKnowledgeCommentVotingIntegration:
    """Integration tests for knowledge comment voting."""

    @pytest.fixture
    async def db(self) -> AsyncGenerator[AppDatabase, None]:
        """Create database connection."""
        db = AppDatabase(dsn="postgresql://localhost/dataing")  # pragma: allowlist secret
        try:
            await db.connect()
        except Exception as e:
            pytest.skip(f"Database not available: {e}")
        yield db
        await db.close()

    @pytest.fixture
    async def tenant_id(self, db: AppDatabase) -> UUID:
        """Get a valid tenant ID from the database."""
        tenant = await db.fetch_one("SELECT id FROM tenants LIMIT 1")
        if not tenant:
            pytest.skip("No tenant in database")
        return tenant["id"]

    @pytest.fixture
    async def dataset_id(self, db: AppDatabase, tenant_id: UUID) -> UUID:
        """Get a valid dataset ID from the database."""
        dataset = await db.fetch_one(
            "SELECT id FROM datasets WHERE tenant_id = $1 LIMIT 1",
            tenant_id,
        )
        if not dataset:
            pytest.skip("No dataset in database")
        return dataset["id"]

    async def test_upvote_knowledge_comment(
        self,
        db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Knowledge comment can be upvoted."""
        comment = await db.create_knowledge_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            content="Upvote test knowledge comment",
            author_name="Author",
        )
        user_id = uuid4()

        try:
            await db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="knowledge",
                comment_id=comment["id"],
                user_id=user_id,
                vote=1,
            )

            updated = await db.get_knowledge_comment(tenant_id, comment["id"])
            assert updated is not None
            assert updated["upvotes"] == 1
            assert updated["downvotes"] == 0
        finally:
            await db.delete_comment_vote(tenant_id, "knowledge", comment["id"], user_id)
            await db.delete_knowledge_comment(tenant_id, comment["id"])

    async def test_downvote_knowledge_comment(
        self,
        db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Knowledge comment can be downvoted."""
        comment = await db.create_knowledge_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            content="Downvote test knowledge comment",
            author_name="Author",
        )
        user_id = uuid4()

        try:
            await db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="knowledge",
                comment_id=comment["id"],
                user_id=user_id,
                vote=-1,
            )

            updated = await db.get_knowledge_comment(tenant_id, comment["id"])
            assert updated is not None
            assert updated["upvotes"] == 0
            assert updated["downvotes"] == 1
        finally:
            await db.delete_comment_vote(tenant_id, "knowledge", comment["id"], user_id)
            await db.delete_knowledge_comment(tenant_id, comment["id"])

    async def test_change_vote_knowledge_comment(
        self,
        db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Vote can be changed from upvote to downvote."""
        comment = await db.create_knowledge_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            content="Change vote test knowledge comment",
            author_name="Author",
        )
        user_id = uuid4()

        try:
            # Initial upvote
            await db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="knowledge",
                comment_id=comment["id"],
                user_id=user_id,
                vote=1,
            )

            updated = await db.get_knowledge_comment(tenant_id, comment["id"])
            assert updated is not None
            assert updated["upvotes"] == 1
            assert updated["downvotes"] == 0

            # Change to downvote
            await db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="knowledge",
                comment_id=comment["id"],
                user_id=user_id,
                vote=-1,
            )

            updated = await db.get_knowledge_comment(tenant_id, comment["id"])
            assert updated is not None
            assert updated["upvotes"] == 0
            assert updated["downvotes"] == 1
        finally:
            await db.delete_comment_vote(tenant_id, "knowledge", comment["id"], user_id)
            await db.delete_knowledge_comment(tenant_id, comment["id"])

    async def test_remove_vote_knowledge_comment(
        self,
        db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Vote can be removed from knowledge comment."""
        comment = await db.create_knowledge_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            content="Remove vote test knowledge comment",
            author_name="Author",
        )
        user_id = uuid4()

        try:
            # Add vote
            await db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="knowledge",
                comment_id=comment["id"],
                user_id=user_id,
                vote=1,
            )

            updated = await db.get_knowledge_comment(tenant_id, comment["id"])
            assert updated is not None
            assert updated["upvotes"] == 1

            # Remove vote
            result = await db.delete_comment_vote(tenant_id, "knowledge", comment["id"], user_id)
            assert result is True

            updated = await db.get_knowledge_comment(tenant_id, comment["id"])
            assert updated is not None
            assert updated["upvotes"] == 0
            assert updated["downvotes"] == 0
        finally:
            await db.delete_knowledge_comment(tenant_id, comment["id"])

    async def test_multiple_users_voting_knowledge(
        self,
        db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Multiple users can vote on the same knowledge comment."""
        comment = await db.create_knowledge_comment(
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
            await db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="knowledge",
                comment_id=comment["id"],
                user_id=user1,
                vote=1,
            )

            # User 2 upvotes
            await db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="knowledge",
                comment_id=comment["id"],
                user_id=user2,
                vote=1,
            )

            # User 3 downvotes
            await db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="knowledge",
                comment_id=comment["id"],
                user_id=user3,
                vote=-1,
            )

            updated = await db.get_knowledge_comment(tenant_id, comment["id"])
            assert updated is not None
            assert updated["upvotes"] == 2
            assert updated["downvotes"] == 1
        finally:
            await db.delete_comment_vote(tenant_id, "knowledge", comment["id"], user1)
            await db.delete_comment_vote(tenant_id, "knowledge", comment["id"], user2)
            await db.delete_comment_vote(tenant_id, "knowledge", comment["id"], user3)
            await db.delete_knowledge_comment(tenant_id, comment["id"])

    async def test_vote_ordering(
        self,
        db: AppDatabase,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> None:
        """Comments are ordered by vote score (upvotes - downvotes)."""
        # Create comments
        low_score = await db.create_knowledge_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            content="Low score comment",
            author_name="Author",
        )
        high_score = await db.create_knowledge_comment(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            content="High score comment",
            author_name="Author",
        )

        user1 = uuid4()
        user2 = uuid4()

        try:
            # Give high_score comment more upvotes
            await db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="knowledge",
                comment_id=high_score["id"],
                user_id=user1,
                vote=1,
            )
            await db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="knowledge",
                comment_id=high_score["id"],
                user_id=user2,
                vote=1,
            )

            # Give low_score comment a downvote
            await db.upsert_comment_vote(
                tenant_id=tenant_id,
                comment_type="knowledge",
                comment_id=low_score["id"],
                user_id=user1,
                vote=-1,
            )

            comments = await db.list_knowledge_comments(tenant_id, dataset_id)
            # Filter to just our test comments
            test_ids = {low_score["id"], high_score["id"]}
            test_comments = [c for c in comments if c["id"] in test_ids]

            # High score should come before low score
            if len(test_comments) >= 2:
                high_idx = next(
                    i for i, c in enumerate(test_comments) if c["id"] == high_score["id"]
                )
                low_idx = next(i for i, c in enumerate(test_comments) if c["id"] == low_score["id"])
                assert high_idx < low_idx
        finally:
            await db.delete_comment_vote(tenant_id, "knowledge", high_score["id"], user1)
            await db.delete_comment_vote(tenant_id, "knowledge", high_score["id"], user2)
            await db.delete_comment_vote(tenant_id, "knowledge", low_score["id"], user1)
            await db.delete_knowledge_comment(tenant_id, low_score["id"])
            await db.delete_knowledge_comment(tenant_id, high_score["id"])
