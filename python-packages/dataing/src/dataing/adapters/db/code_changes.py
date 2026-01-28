"""Repository for querying code changes relevant to investigated assets.

This module provides a repository class that fetches recent code changes
affecting a given asset, with relevance scoring for hypothesis generation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

from dataing.core.domain_types import RelevantCodeChange
from dataing.core.json_utils import to_json_string

if TYPE_CHECKING:
    from dataing.adapters.db.app_db import AppDatabase


class CodeChangesRepository:
    """Repository for fetching relevant code changes for investigation context."""

    def __init__(self, db: AppDatabase) -> None:
        """Initialize the repository."""
        self.db = db

    async def get_relevant_code_changes(
        self,
        tenant_id: UUID,
        asset_id: str,
        upstream_assets: list[str] | None = None,
        lookback_days: int = 14,
        max_results: int = 5,
    ) -> list[RelevantCodeChange]:
        """Get recent code changes relevant to an asset.

        Fetches commits that may have affected the given asset, ranked by relevance:
        - 1.0: Commit directly affected the target asset
        - 0.7: Commit affected an upstream dependency of the target
        - 0.4: Commit modified files matching dataset-to-repo mappings

        Args:
            tenant_id: The tenant ID for scoping the query.
            asset_id: The primary asset being investigated (e.g., "schema.table").
            upstream_assets: Optional list of upstream asset IDs for dependency matching.
            lookback_days: How many days back to search (default 14).
            max_results: Maximum number of results to return (default 5).

        Returns:
            List of RelevantCodeChange ordered by relevance_score DESC, committed_at DESC.
        """
        since = datetime.now(UTC) - timedelta(days=lookback_days)
        upstream_assets = upstream_assets or []

        # Build a unified query that scores changes by relevance
        # We use a CASE expression to assign scores:
        # - exact asset match: 1.0
        # - upstream asset match: 0.7
        # - path match from mappings: 0.4
        query = """
            WITH exact_matches AS (
                SELECT
                    cc.commit_hash,
                    cc.author_name,
                    cc.message,
                    cc.committed_at,
                    cc.affected_assets,
                    1.0::float AS relevance_score,
                    'directly_affects_asset' AS relevance_reason
                FROM code_changes cc
                JOIN git_repositories gr ON cc.repo_id = gr.id
                WHERE gr.tenant_id = $1
                  AND cc.committed_at >= $2
                  AND cc.affected_assets @> $3::jsonb
            ),
            upstream_matches AS (
                SELECT
                    cc.commit_hash,
                    cc.author_name,
                    cc.message,
                    cc.committed_at,
                    cc.affected_assets,
                    0.7::float AS relevance_score,
                    'affects_upstream_dependency' AS relevance_reason
                FROM code_changes cc
                JOIN git_repositories gr ON cc.repo_id = gr.id
                WHERE gr.tenant_id = $1
                  AND cc.committed_at >= $2
                  AND $4 != '{}'::jsonb
                  AND EXISTS (
                      SELECT 1
                      FROM jsonb_array_elements($4::jsonb) AS upstream(name)
                      WHERE cc.affected_assets @> jsonb_build_array(upstream.name)
                  )
                  AND NOT cc.affected_assets @> $3::jsonb
            ),
            path_matches AS (
                SELECT
                    cc.commit_hash,
                    cc.author_name,
                    cc.message,
                    cc.committed_at,
                    cc.affected_assets,
                    0.4::float AS relevance_score,
                    'matches_file_path_pattern' AS relevance_reason
                FROM code_changes cc
                JOIN git_repositories gr ON cc.repo_id = gr.id
                JOIN dataset_repo_mappings drm ON drm.tenant_id = gr.tenant_id
                WHERE gr.tenant_id = $1
                  AND cc.committed_at >= $2
                  AND drm.confirmed = true
                  AND (
                      (drm.pattern_type = 'exact' AND drm.dataset_pattern = $5)
                      OR drm.pattern_type = 'glob'
                  )
                  AND drm.file_path IS NOT NULL
                  AND cc.files_changed IS NOT NULL
                  AND EXISTS (
                      SELECT 1
                      FROM unnest(cc.files_changed) AS fc(path)
                      WHERE fc.path LIKE '%' || drm.file_path || '%'
                  )
                  AND NOT cc.affected_assets @> $3::jsonb
                  AND NOT EXISTS (
                      SELECT 1
                      FROM jsonb_array_elements($4::jsonb) AS upstream(name)
                      WHERE cc.affected_assets @> jsonb_build_array(upstream.name)
                  )
            ),
            all_changes AS (
                SELECT * FROM exact_matches
                UNION ALL
                SELECT * FROM upstream_matches
                UNION ALL
                SELECT * FROM path_matches
            )
            SELECT DISTINCT ON (commit_hash)
                commit_hash,
                author_name,
                message,
                committed_at,
                affected_assets,
                relevance_score,
                relevance_reason
            FROM all_changes
            ORDER BY commit_hash, relevance_score DESC, committed_at DESC
        """

        # Wrap to get final ordering and limit
        final_query = f"""
            SELECT * FROM ({query}) AS ranked
            ORDER BY relevance_score DESC, committed_at DESC
            LIMIT $6
        """

        # Build parameters
        exact_match_json = to_json_string([{"name": asset_id}])
        upstream_json = to_json_string([{"name": name} for name in upstream_assets])
        normalized_asset_id = asset_id.lower().strip()

        rows = await self.db.fetch_all(
            final_query,
            tenant_id,
            since,
            exact_match_json,
            upstream_json,
            normalized_asset_id,
            max_results,
        )

        return [self._row_to_domain(row) for row in rows]

    def _row_to_domain(self, row: dict[str, Any]) -> RelevantCodeChange:
        """Convert a database row to a RelevantCodeChange domain object."""
        affected = row.get("affected_assets", [])
        if isinstance(affected, str):
            import json

            affected = json.loads(affected)

        # Extract just the asset names from the affected_assets JSONB
        asset_names = [asset.get("name", "") for asset in affected if isinstance(asset, dict)]

        return RelevantCodeChange(
            commit_hash=row["commit_hash"],
            author_name=row.get("author_name"),
            message=row.get("message"),
            committed_at=row.get("committed_at"),
            affected_assets=asset_names,
            relevance_score=float(row["relevance_score"]),
            relevance_reason=row["relevance_reason"],
        )
