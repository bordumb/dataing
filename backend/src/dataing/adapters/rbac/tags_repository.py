"""Tags repository."""

import logging
from datetime import UTC
from typing import TYPE_CHECKING, Any
from uuid import UUID

from dataing.core.rbac import ResourceTag

if TYPE_CHECKING:
    from asyncpg import Connection

logger = logging.getLogger(__name__)


class TagsRepository:
    """Repository for resource tag operations."""

    def __init__(self, conn: "Connection") -> None:
        """Initialize the repository."""
        self._conn = conn

    async def create(self, org_id: UUID, name: str, color: str = "#6366f1") -> ResourceTag:
        """Create a new tag."""
        row = await self._conn.fetchrow(
            """
            INSERT INTO resource_tags (org_id, name, color)
            VALUES ($1, $2, $3)
            RETURNING id, org_id, name, color, created_at
            """,
            org_id,
            name,
            color,
        )
        return self._row_to_tag(row)

    async def get_by_id(self, tag_id: UUID) -> ResourceTag | None:
        """Get tag by ID."""
        row = await self._conn.fetchrow(
            "SELECT id, org_id, name, color, created_at FROM resource_tags WHERE id = $1",
            tag_id,
        )
        if not row:
            return None
        return self._row_to_tag(row)

    async def get_by_name(self, org_id: UUID, name: str) -> ResourceTag | None:
        """Get tag by name."""
        row = await self._conn.fetchrow(
            """
            SELECT id, org_id, name, color, created_at
            FROM resource_tags WHERE org_id = $1 AND name = $2
            """,
            org_id,
            name,
        )
        if not row:
            return None
        return self._row_to_tag(row)

    async def list_by_org(self, org_id: UUID) -> list[ResourceTag]:
        """List all tags in an organization."""
        rows = await self._conn.fetch(
            """
            SELECT id, org_id, name, color, created_at
            FROM resource_tags WHERE org_id = $1 ORDER BY name
            """,
            org_id,
        )
        return [self._row_to_tag(row) for row in rows]

    async def update(
        self, tag_id: UUID, name: str | None = None, color: str | None = None
    ) -> ResourceTag | None:
        """Update tag."""
        # Build dynamic update
        updates = []
        params: list[Any] = [tag_id]
        idx = 2

        if name is not None:
            updates.append(f"name = ${idx}")
            params.append(name)
            idx += 1

        if color is not None:
            updates.append(f"color = ${idx}")
            params.append(color)
            idx += 1

        if not updates:
            return await self.get_by_id(tag_id)

        query = f"""
            UPDATE resource_tags SET {', '.join(updates)}
            WHERE id = $1
            RETURNING id, org_id, name, color, created_at
        """

        row = await self._conn.fetchrow(query, *params)
        if not row:
            return None
        return self._row_to_tag(row)

    async def delete(self, tag_id: UUID) -> bool:
        """Delete a tag."""
        result: str = await self._conn.execute(
            "DELETE FROM resource_tags WHERE id = $1",
            tag_id,
        )
        return result == "DELETE 1"

    async def add_to_investigation(self, investigation_id: UUID, tag_id: UUID) -> bool:
        """Add tag to an investigation."""
        try:
            await self._conn.execute(
                """
                INSERT INTO investigation_tags (investigation_id, tag_id)
                VALUES ($1, $2)
                ON CONFLICT (investigation_id, tag_id) DO NOTHING
                """,
                investigation_id,
                tag_id,
            )
            return True
        except Exception:
            logger.exception(f"Failed to add tag {tag_id} to investigation {investigation_id}")
            return False

    async def remove_from_investigation(self, investigation_id: UUID, tag_id: UUID) -> bool:
        """Remove tag from an investigation."""
        result: str = await self._conn.execute(
            "DELETE FROM investigation_tags WHERE investigation_id = $1 AND tag_id = $2",
            investigation_id,
            tag_id,
        )
        return result == "DELETE 1"

    async def get_investigation_tags(self, investigation_id: UUID) -> list[ResourceTag]:
        """Get all tags on an investigation."""
        rows = await self._conn.fetch(
            """
            SELECT t.id, t.org_id, t.name, t.color, t.created_at
            FROM resource_tags t
            JOIN investigation_tags it ON t.id = it.tag_id
            WHERE it.investigation_id = $1
            ORDER BY t.name
            """,
            investigation_id,
        )
        return [self._row_to_tag(row) for row in rows]

    def _row_to_tag(self, row: dict[str, Any]) -> ResourceTag:
        """Convert database row to ResourceTag."""
        return ResourceTag(
            id=row["id"],
            org_id=row["org_id"],
            name=row["name"],
            color=row["color"],
            created_at=row["created_at"].replace(tzinfo=UTC),
        )
