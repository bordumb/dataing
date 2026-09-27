"""Integration tests for dataset-to-repository mappings with real database."""

import asyncio
from uuid import UUID, uuid4

import pytest

from dataing.adapters.db.app_db import AppDatabase


@pytest.mark.integration
class TestRepoMappingCrudIntegration:
    """Integration tests for repo mapping CRUD operations."""

    async def test_create_and_get(self, migrated_db: AppDatabase, tenant_id: UUID) -> None:
        """create_repo_mapping + get_repo_mapping round-trip all fields."""
        mapping_data = {
            "dataset_pattern": "public.orders",
            "pattern_type": "exact",
            "repo_owner": "acme",
            "repo_name": "etl-pipeline",
            "file_path": "models/orders.sql",
            "branch": "main",
            "job_name": "dbt_run",
            "source": "manual",
            "confidence": 0.95,
            "confirmed": True,
            "metadata": {"notes": "test"},
        }

        created = await migrated_db.create_repo_mapping(tenant_id, mapping_data)
        try:
            assert created["dataset_pattern"] == "public.orders"
            assert created["repo_owner"] == "acme"
            assert created["repo_name"] == "etl-pipeline"
            assert created["file_path"] == "models/orders.sql"
            assert created["branch"] == "main"
            assert created["job_name"] == "dbt_run"
            assert created["source"] == "manual"
            assert created["confidence"] == pytest.approx(0.95)
            assert created["confirmed"] is True

            fetched = await migrated_db.get_repo_mapping(created["id"], tenant_id)
            assert fetched is not None
            assert fetched["id"] == created["id"]
            assert fetched["dataset_pattern"] == "public.orders"
            assert fetched["repo_owner"] == "acme"
        finally:
            await migrated_db.delete_repo_mapping(created["id"], tenant_id)

    async def test_list_with_filters(self, migrated_db: AppDatabase, tenant_id: UUID) -> None:
        """list_repo_mappings respects source, confirmed, and limit filters."""
        m1 = await migrated_db.create_repo_mapping(
            tenant_id,
            {
                "dataset_pattern": "public.users",
                "repo_owner": "acme",
                "repo_name": "etl",
                "source": "manual",
                "confirmed": True,
            },
        )
        m2 = await migrated_db.create_repo_mapping(
            tenant_id,
            {
                "dataset_pattern": "public.events",
                "repo_owner": "acme",
                "repo_name": "etl",
                "source": "dbt_manifest",
                "confirmed": False,
            },
        )

        try:
            # Filter by source
            manual = await migrated_db.list_repo_mappings(tenant_id, source="manual")
            manual_ids = [r["id"] for r in manual]
            assert m1["id"] in manual_ids
            assert m2["id"] not in manual_ids

            # Filter by confirmed
            confirmed = await migrated_db.list_repo_mappings(tenant_id, confirmed=True)
            confirmed_ids = [r["id"] for r in confirmed]
            assert m1["id"] in confirmed_ids
            assert m2["id"] not in confirmed_ids

            # Limit
            limited = await migrated_db.list_repo_mappings(tenant_id, limit=1)
            assert len(limited) == 1
        finally:
            await migrated_db.delete_repo_mapping(m1["id"], tenant_id)
            await migrated_db.delete_repo_mapping(m2["id"], tenant_id)

    async def test_update(self, migrated_db: AppDatabase, tenant_id: UUID) -> None:
        """update_repo_mapping changes fields and advances updated_at."""
        created = await migrated_db.create_repo_mapping(
            tenant_id,
            {
                "dataset_pattern": "public.products",
                "repo_owner": "acme",
                "repo_name": "etl",
                "file_path": "old/path.sql",
                "source": "manual",
            },
        )

        try:
            updated = await migrated_db.update_repo_mapping(
                created["id"],
                tenant_id,
                {"file_path": "new/path.sql", "confidence": 0.8},
            )
            assert updated is not None
            assert updated["file_path"] == "new/path.sql"
            assert updated["confidence"] == pytest.approx(0.8)
            assert updated["updated_at"] >= created["updated_at"]
        finally:
            await migrated_db.delete_repo_mapping(created["id"], tenant_id)

    async def test_delete(self, migrated_db: AppDatabase, tenant_id: UUID) -> None:
        """delete_repo_mapping returns True and get returns None afterward."""
        created = await migrated_db.create_repo_mapping(
            tenant_id,
            {
                "dataset_pattern": "public.to_delete",
                "repo_owner": "acme",
                "repo_name": "etl",
                "source": "manual",
            },
        )

        result = await migrated_db.delete_repo_mapping(created["id"], tenant_id)
        assert result is True

        fetched = await migrated_db.get_repo_mapping(created["id"], tenant_id)
        assert fetched is None

    async def test_delete_nonexistent(self, migrated_db: AppDatabase, tenant_id: UUID) -> None:
        """delete_repo_mapping returns False for unknown ID."""
        result = await migrated_db.delete_repo_mapping(uuid4(), tenant_id)
        assert result is False

    async def test_bulk_create(self, migrated_db: AppDatabase, tenant_id: UUID) -> None:
        """bulk_create_repo_mappings persists multiple rows."""
        mappings = [
            {
                "dataset_pattern": "public.bulk_a",
                "repo_owner": "acme",
                "repo_name": "etl",
                "source": "bulk_import",
            },
            {
                "dataset_pattern": "public.bulk_b",
                "repo_owner": "acme",
                "repo_name": "etl",
                "source": "bulk_import",
            },
        ]

        results = await migrated_db.bulk_create_repo_mappings(tenant_id, mappings)
        try:
            assert len(results) == 2
            patterns = {r["dataset_pattern"] for r in results}
            assert "public.bulk_a" in patterns
            assert "public.bulk_b" in patterns
        finally:
            for r in results:
                await migrated_db.delete_repo_mapping(r["id"], tenant_id)

    async def test_upsert(self, migrated_db: AppDatabase, tenant_id: UUID) -> None:
        """upsert_repo_mapping ON CONFLICT updates file_path, uses GREATEST for confidence."""
        first = await migrated_db.upsert_repo_mapping(
            tenant_id=tenant_id,
            dataset_pattern="public.upsert_test",
            repo_owner="acme",
            repo_name="etl",
            defaults={
                "file_path": "v1/model.sql",
                "confidence": 0.7,
                "source": "manual",
            },
        )

        try:
            second = await migrated_db.upsert_repo_mapping(
                tenant_id=tenant_id,
                dataset_pattern="public.upsert_test",
                repo_owner="acme",
                repo_name="etl",
                defaults={
                    "file_path": "v2/model.sql",
                    "confidence": 0.9,
                    "source": "manual",
                },
            )

            # Same row updated (upsert)
            assert second["id"] == first["id"]
            # file_path updated via COALESCE(EXCLUDED, existing)
            assert second["file_path"] == "v2/model.sql"
            # confidence uses GREATEST
            assert second["confidence"] == pytest.approx(0.9)

            # Upsert with lower confidence keeps the higher value
            third = await migrated_db.upsert_repo_mapping(
                tenant_id=tenant_id,
                dataset_pattern="public.upsert_test",
                repo_owner="acme",
                repo_name="etl",
                defaults={
                    "file_path": "v3/model.sql",
                    "confidence": 0.5,
                    "source": "manual",
                },
            )
            assert third["confidence"] == pytest.approx(0.9)
        finally:
            await migrated_db.delete_repo_mapping(first["id"], tenant_id)


@pytest.mark.integration
class TestRepoMappingSuggestionsIntegration:
    """Integration tests for repo mapping suggestion workflow."""

    async def test_list_suggestions(self, migrated_db: AppDatabase, tenant_id: UUID) -> None:
        """Unconfirmed mappings appear in suggestions, not in confirmed list."""
        suggestion = await migrated_db.create_repo_mapping(
            tenant_id,
            {
                "dataset_pattern": "public.suggested",
                "repo_owner": "acme",
                "repo_name": "etl",
                "source": "openlineage",
                "confidence": 0.6,
                "confirmed": False,
            },
        )

        try:
            suggestions = await migrated_db.list_repo_mapping_suggestions(tenant_id)
            suggestion_ids = [s["id"] for s in suggestions]
            assert suggestion["id"] in suggestion_ids

            confirmed = await migrated_db.list_repo_mappings(tenant_id, confirmed=True)
            confirmed_ids = [c["id"] for c in confirmed]
            assert suggestion["id"] not in confirmed_ids
        finally:
            await migrated_db.delete_repo_mapping(suggestion["id"], tenant_id)

    async def test_confirm(self, migrated_db: AppDatabase, tenant_id: UUID) -> None:
        """Confirming a suggestion sets confirmed=True and priority=0."""
        suggestion = await migrated_db.create_repo_mapping(
            tenant_id,
            {
                "dataset_pattern": "public.to_confirm",
                "repo_owner": "acme",
                "repo_name": "etl",
                "source": "dbt_manifest",
                "confidence": 0.75,
                "confirmed": False,
                "priority": 10,
            },
        )

        try:
            confirmed = await migrated_db.confirm_repo_mapping(suggestion["id"], tenant_id)
            assert confirmed is not None
            assert confirmed["confirmed"] is True
            assert confirmed["priority"] == 0
        finally:
            await migrated_db.delete_repo_mapping(suggestion["id"], tenant_id)

    async def test_dismiss(self, migrated_db: AppDatabase, tenant_id: UUID) -> None:
        """Dismissing deletes an unconfirmed mapping."""
        suggestion = await migrated_db.create_repo_mapping(
            tenant_id,
            {
                "dataset_pattern": "public.to_dismiss",
                "repo_owner": "acme",
                "repo_name": "etl",
                "source": "openlineage",
                "confirmed": False,
            },
        )

        result = await migrated_db.dismiss_repo_mapping(suggestion["id"], tenant_id)
        assert result is True

        fetched = await migrated_db.get_repo_mapping(suggestion["id"], tenant_id)
        assert fetched is None

    async def test_cannot_dismiss_confirmed(
        self, migrated_db: AppDatabase, tenant_id: UUID
    ) -> None:
        """dismiss_repo_mapping returns False for confirmed mappings."""
        confirmed = await migrated_db.create_repo_mapping(
            tenant_id,
            {
                "dataset_pattern": "public.no_dismiss",
                "repo_owner": "acme",
                "repo_name": "etl",
                "source": "manual",
                "confirmed": True,
            },
        )

        try:
            result = await migrated_db.dismiss_repo_mapping(confirmed["id"], tenant_id)
            assert result is False

            # Mapping still exists
            fetched = await migrated_db.get_repo_mapping(confirmed["id"], tenant_id)
            assert fetched is not None
        finally:
            await migrated_db.delete_repo_mapping(confirmed["id"], tenant_id)


@pytest.mark.integration
class TestRepoMappingResolutionIntegration:
    """Integration tests for dataset-to-repo resolution queries."""

    async def test_resolve_exact(self, migrated_db: AppDatabase, tenant_id: UUID) -> None:
        """Exact match returned from resolve_repo_for_dataset."""
        mapping = await migrated_db.create_repo_mapping(
            tenant_id,
            {
                "dataset_pattern": "public.orders",
                "pattern_type": "exact",
                "repo_owner": "acme",
                "repo_name": "warehouse",
                "file_path": "models/orders.sql",
                "source": "manual",
                "confirmed": True,
            },
        )

        try:
            results = await migrated_db.resolve_repo_for_dataset(tenant_id, "public.orders")
            matched_ids = [r["id"] for r in results]
            assert mapping["id"] in matched_ids

            match = next(r for r in results if r["id"] == mapping["id"])
            assert match["repo_owner"] == "acme"
            assert match["repo_name"] == "warehouse"
        finally:
            await migrated_db.delete_repo_mapping(mapping["id"], tenant_id)

    async def test_resolve_returns_glob_patterns(
        self, migrated_db: AppDatabase, tenant_id: UUID
    ) -> None:
        """Glob patterns returned for Python-side filtering."""
        glob_mapping = await migrated_db.create_repo_mapping(
            tenant_id,
            {
                "dataset_pattern": "public.*",
                "pattern_type": "glob",
                "repo_owner": "acme",
                "repo_name": "warehouse",
                "file_path": "models/{table}.sql",
                "source": "manual",
                "confirmed": True,
            },
        )

        try:
            # resolve_repo_for_dataset returns all glob patterns for the tenant
            results = await migrated_db.resolve_repo_for_dataset(tenant_id, "public.some_table")
            glob_ids = [r["id"] for r in results if r["pattern_type"] == "glob"]
            assert glob_mapping["id"] in glob_ids
        finally:
            await migrated_db.delete_repo_mapping(glob_mapping["id"], tenant_id)

    async def test_resolve_ordering(self, migrated_db: AppDatabase, tenant_id: UUID) -> None:
        """Results ordered by priority ASC, confidence DESC, created_at DESC."""
        low_priority = await migrated_db.create_repo_mapping(
            tenant_id,
            {
                "dataset_pattern": "public.ordered",
                "pattern_type": "exact",
                "repo_owner": "acme",
                "repo_name": "fallback",
                "source": "manual",
                "confidence": 0.5,
                "priority": 10,
                "confirmed": True,
            },
        )
        # Small delay to ensure created_at ordering is deterministic
        await asyncio.sleep(0.05)
        high_priority = await migrated_db.create_repo_mapping(
            tenant_id,
            {
                "dataset_pattern": "public.ordered",
                "pattern_type": "exact",
                "repo_owner": "acme",
                "repo_name": "primary",
                "source": "manual",
                "confidence": 0.9,
                "priority": 0,
                "confirmed": True,
            },
        )

        try:
            results = await migrated_db.resolve_repo_for_dataset(tenant_id, "public.ordered")
            our_results = [
                r for r in results if r["id"] in (low_priority["id"], high_priority["id"])
            ]

            assert len(our_results) == 2
            # priority=0 should come first
            assert our_results[0]["id"] == high_priority["id"]
            assert our_results[1]["id"] == low_priority["id"]
        finally:
            await migrated_db.delete_repo_mapping(low_priority["id"], tenant_id)
            await migrated_db.delete_repo_mapping(high_priority["id"], tenant_id)
