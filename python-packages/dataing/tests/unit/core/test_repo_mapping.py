"""Unit tests for dataset-to-repository mapping resolution algorithm."""

from datetime import UTC, datetime

from dataing.core.repo_mapping import (
    match_pattern,
    normalize_dataset_id,
    resolve_all_repo_mappings,
    resolve_file_path,
    resolve_repo_mapping,
)


class TestNormalizeDatasetId:
    """Test dataset identifier normalization."""

    def test_schema_table(self) -> None:
        """Test two-part identifier returns single form."""
        result = normalize_dataset_id("analytics.orders")
        assert result == ["analytics.orders"]

    def test_db_schema_table(self) -> None:
        """Test three-part identifier returns both full and short forms."""
        result = normalize_dataset_id("mydb.analytics.orders")
        assert result == ["mydb.analytics.orders", "analytics.orders"]

    def test_case_insensitive(self) -> None:
        """Test normalization lowercases input."""
        result = normalize_dataset_id("Analytics.Orders")
        assert result == ["analytics.orders"]

    def test_strips_whitespace(self) -> None:
        """Test normalization strips whitespace."""
        result = normalize_dataset_id("  analytics.orders  ")
        assert result == ["analytics.orders"]

    def test_single_part(self) -> None:
        """Test single-part identifier."""
        result = normalize_dataset_id("orders")
        assert result == ["orders"]


class TestMatchPattern:
    """Test pattern matching."""

    def test_exact_match(self) -> None:
        """Test exact pattern match."""
        assert match_pattern("analytics.orders", "exact", "analytics.orders")

    def test_exact_no_match(self) -> None:
        """Test exact pattern no match."""
        assert not match_pattern("analytics.orders", "exact", "staging.orders")

    def test_exact_case_insensitive(self) -> None:
        """Test exact match is case-insensitive."""
        assert match_pattern("analytics.orders", "exact", "Analytics.Orders")

    def test_glob_wildcard_suffix(self) -> None:
        """Test glob with wildcard suffix."""
        assert match_pattern("analytics.*", "glob", "analytics.orders")

    def test_glob_wildcard_prefix(self) -> None:
        """Test glob with wildcard prefix."""
        assert match_pattern("*.orders", "glob", "analytics.orders")

    def test_glob_no_match(self) -> None:
        """Test glob that doesn't match."""
        assert not match_pattern("analytics.*", "glob", "staging.orders")

    def test_glob_full_wildcard(self) -> None:
        """Test glob with full wildcard."""
        assert match_pattern("*.*", "glob", "analytics.orders")

    def test_exact_matches_db_schema_table(self) -> None:
        """Test exact matches against schema.table form of db.schema.table input."""
        assert match_pattern("analytics.orders", "exact", "mydb.analytics.orders")

    def test_glob_matches_db_schema_table(self) -> None:
        """Test glob matches against schema.table form of db.schema.table input."""
        assert match_pattern("analytics.*", "glob", "mydb.analytics.orders")

    def test_unknown_pattern_type(self) -> None:
        """Test unknown pattern type returns false."""
        assert not match_pattern("analytics.orders", "regex", "analytics.orders")


class TestResolveFilePath:
    """Test file path token substitution."""

    def test_no_tokens(self) -> None:
        """Test path without tokens returned as-is."""
        assert resolve_file_path("dags/orders.py", "analytics.orders") == "dags/orders.py"

    def test_table_token(self) -> None:
        """Test {table} token substitution."""
        assert resolve_file_path("models/{table}.sql", "analytics.orders") == "models/orders.sql"

    def test_schema_token(self) -> None:
        """Test {schema} token substitution."""
        result = resolve_file_path("{schema}/{table}.sql", "analytics.orders")
        assert result == "analytics/orders.sql"

    def test_database_token(self) -> None:
        """Test {database} token substitution."""
        result = resolve_file_path("{database}/{schema}/{table}.sql", "mydb.analytics.orders")
        assert result == "mydb/analytics/orders.sql"

    def test_none_template(self) -> None:
        """Test None template returns None."""
        assert resolve_file_path(None, "analytics.orders") is None


class TestResolveRepoMapping:
    """Test repo mapping resolution algorithm."""

    def _make_mapping(
        self,
        pattern: str,
        pattern_type: str = "exact",
        priority: int = 0,
        confidence: float = 1.0,
        created_at: datetime | None = None,
        **kwargs: str | None,
    ) -> dict:
        """Create a test mapping dict."""
        return {
            "dataset_pattern": pattern,
            "pattern_type": pattern_type,
            "priority": priority,
            "confidence": confidence,
            "created_at": created_at or datetime(2024, 1, 1, tzinfo=UTC),
            "repo_owner": kwargs.get("repo_owner", "acme"),
            "repo_name": kwargs.get("repo_name", "etl"),
            "file_path": kwargs.get("file_path"),
            "branch": kwargs.get("branch"),
            "source": kwargs.get("source", "manual"),
            "job_name": kwargs.get("job_name"),
        }

    def test_exact_match(self) -> None:
        """Test returns exact match."""
        mappings = [self._make_mapping("analytics.orders")]
        result = resolve_repo_mapping(mappings, "analytics.orders")
        assert result is not None
        assert result["repo_owner"] == "acme"

    def test_no_match_returns_none(self) -> None:
        """Test returns None when no match."""
        mappings = [self._make_mapping("staging.orders")]
        result = resolve_repo_mapping(mappings, "analytics.orders")
        assert result is None

    def test_priority_order(self) -> None:
        """Test lower priority wins."""
        mappings = [
            self._make_mapping(
                "analytics.*", pattern_type="glob", priority=10, repo_owner="team-b"
            ),
            self._make_mapping("analytics.orders", priority=0, repo_owner="team-a"),
        ]
        result = resolve_repo_mapping(mappings, "analytics.orders")
        assert result is not None
        assert result["repo_owner"] == "team-a"

    def test_confidence_tiebreak(self) -> None:
        """Test higher confidence wins at same priority."""
        mappings = [
            self._make_mapping("analytics.orders", confidence=0.6, repo_owner="low"),
            self._make_mapping("analytics.orders", confidence=0.95, repo_owner="high"),
        ]
        result = resolve_repo_mapping(mappings, "analytics.orders")
        assert result is not None
        assert result["repo_owner"] == "high"

    def test_explicit_beats_pattern(self) -> None:
        """Test explicit mapping (priority=0) beats pattern (priority=10)."""
        mappings = [
            self._make_mapping(
                "analytics.*", pattern_type="glob", priority=10, repo_owner="pattern"
            ),
            self._make_mapping("analytics.orders", priority=0, repo_owner="explicit"),
        ]
        result = resolve_repo_mapping(mappings, "analytics.orders")
        assert result is not None
        assert result["repo_owner"] == "explicit"

    def test_file_path_resolved(self) -> None:
        """Test file_path tokens are resolved in result."""
        mappings = [
            self._make_mapping("analytics.orders", file_path="models/{table}.sql"),
        ]
        result = resolve_repo_mapping(mappings, "analytics.orders")
        assert result is not None
        assert result["file_path"] == "models/orders.sql"

    def test_created_at_tiebreak(self) -> None:
        """Test newer mapping wins at same priority and confidence."""
        older = datetime(2024, 1, 1, tzinfo=UTC)
        newer = datetime(2024, 6, 1, tzinfo=UTC)
        mappings = [
            self._make_mapping("analytics.orders", created_at=older, repo_owner="old"),
            self._make_mapping("analytics.orders", created_at=newer, repo_owner="new"),
        ]
        result = resolve_repo_mapping(mappings, "analytics.orders")
        assert result is not None
        assert result["repo_owner"] == "new"


class TestResolveAllRepoMappings:
    """Test resolve_all returns sorted list of all matches."""

    def test_returns_all_sorted(self) -> None:
        """Test all matches returned in priority order."""
        mappings = [
            {
                "dataset_pattern": "analytics.*",
                "pattern_type": "glob",
                "priority": 10,
                "confidence": 0.8,
                "created_at": datetime(2024, 1, 1, tzinfo=UTC),
                "repo_owner": "team-b",
                "repo_name": "etl",
                "file_path": None,
                "branch": None,
                "source": "manual",
                "job_name": None,
            },
            {
                "dataset_pattern": "analytics.orders",
                "pattern_type": "exact",
                "priority": 0,
                "confidence": 1.0,
                "created_at": datetime(2024, 1, 1, tzinfo=UTC),
                "repo_owner": "team-a",
                "repo_name": "pipeline",
                "file_path": None,
                "branch": None,
                "source": "manual",
                "job_name": None,
            },
        ]
        results = resolve_all_repo_mappings(mappings, "analytics.orders")
        assert len(results) == 2
        assert results[0]["repo_owner"] == "team-a"
        assert results[1]["repo_owner"] == "team-b"

    def test_empty_when_no_match(self) -> None:
        """Test empty list when no matches."""
        mappings = [
            {
                "dataset_pattern": "staging.orders",
                "pattern_type": "exact",
                "priority": 0,
                "confidence": 1.0,
                "created_at": datetime(2024, 1, 1, tzinfo=UTC),
                "repo_owner": "acme",
                "repo_name": "etl",
                "file_path": None,
                "branch": None,
                "source": "manual",
                "job_name": None,
            },
        ]
        results = resolve_all_repo_mappings(mappings, "analytics.orders")
        assert results == []


class TestDbtManifestParsing:
    """Test dbt manifest parsing logic."""

    def test_models_only(self) -> None:
        """Test only model nodes are extracted."""
        from dataing.entrypoints.api.routes.repo_mappings import _parse_dbt_manifest

        manifest = {
            "nodes": {
                "model.my_project.orders": {
                    "resource_type": "model",
                    "schema": "analytics",
                    "name": "orders",
                    "original_file_path": "models/orders.sql",
                },
                "test.my_project.test_orders": {
                    "resource_type": "test",
                    "schema": "analytics",
                    "name": "test_orders",
                },
                "seed.my_project.raw_data": {
                    "resource_type": "seed",
                    "schema": "raw",
                    "name": "raw_data",
                },
            }
        }
        result = _parse_dbt_manifest(manifest, "acme", "etl", None)
        assert len(result) == 1
        assert result[0]["dataset_pattern"] == "analytics.orders"

    def test_schema_name_pattern(self) -> None:
        """Test dataset_pattern is schema.name format."""
        from dataing.entrypoints.api.routes.repo_mappings import _parse_dbt_manifest

        manifest = {
            "nodes": {
                "model.proj.users": {
                    "resource_type": "model",
                    "schema": "public",
                    "name": "users",
                    "original_file_path": "models/users.sql",
                }
            }
        }
        result = _parse_dbt_manifest(manifest, "acme", "etl", "main")
        assert len(result) == 1
        assert result[0]["dataset_pattern"] == "public.users"
        assert result[0]["file_path"] == "models/users.sql"
        assert result[0]["branch"] == "main"
        assert result[0]["confidence"] == 0.85
        assert result[0]["source"] == "dbt_manifest"

    def test_skips_missing_schema(self) -> None:
        """Test skips models without schema."""
        from dataing.entrypoints.api.routes.repo_mappings import _parse_dbt_manifest

        manifest = {
            "nodes": {
                "model.proj.bad": {
                    "resource_type": "model",
                    "schema": "",
                    "name": "bad",
                }
            }
        }
        result = _parse_dbt_manifest(manifest, "acme", "etl", None)
        assert len(result) == 0
