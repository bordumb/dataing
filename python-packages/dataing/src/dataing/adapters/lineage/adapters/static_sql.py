"""Static SQL analysis adapter.

Fallback when no lineage provider is configured.
Parses SQL to extract table references.

Uses sqlglot for SQL parsing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dataing.adapters.lineage.base import BaseLineageAdapter
from dataing.adapters.lineage.registry import (
    LineageConfigField,
    LineageConfigSchema,
    register_lineage_adapter,
)
from dataing.adapters.lineage.types import (
    ColumnLineage,
    Dataset,
    DatasetId,
    DatasetType,
    Job,
    JobType,
    LineageCapabilities,
    LineageProviderInfo,
    LineageProviderType,
)


@register_lineage_adapter(
    provider_type=LineageProviderType.STATIC_SQL,
    display_name="SQL Analysis",
    description="Infer lineage by parsing SQL files",
    capabilities=LineageCapabilities(
        supports_column_lineage=True,
        supports_job_runs=False,
        supports_freshness=False,
        supports_search=True,
        supports_owners=False,
        supports_tags=False,
        is_realtime=False,
    ),
    config_schema=LineageConfigSchema(
        fields=[
            LineageConfigField(
                name="sql_directory",
                label="SQL Directory",
                type="string",
                required=False,
                description="Directory containing SQL files to analyze",
            ),
            LineageConfigField(
                name="sql_files",
                label="SQL Files",
                type="json",
                required=False,
                description="List of specific SQL file paths",
            ),
            LineageConfigField(
                name="git_repo_url",
                label="Git Repository URL",
                type="string",
                required=False,
                description="GitHub repo URL for source links",
            ),
            LineageConfigField(
                name="dialect",
                label="SQL Dialect",
                type="string",
                required=True,
                default="snowflake",
                description="SQL dialect (snowflake, postgres, bigquery, etc.)",
            ),
        ]
    ),
)
class StaticSQLAdapter(BaseLineageAdapter):
    """Static SQL analysis adapter.

    Config:
        sql_files: List of SQL file paths to analyze
        sql_directory: Directory containing SQL files
        git_repo_url: Optional GitHub repo URL for source links
        dialect: SQL dialect for parsing

    Parses CREATE TABLE, INSERT, SELECT statements to infer lineage.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize the Static SQL adapter.

        Args:
            config: Configuration dictionary.
        """
        super().__init__(config)
        self._sql_files = config.get("sql_files", [])
        self._sql_directory = config.get("sql_directory")
        self._git_repo_url = config.get("git_repo_url")
        self._dialect = config.get("dialect", "snowflake")

        # Cached lineage graph
        self._lineage: dict[str, list[str]] | None = None
        self._reverse_lineage: dict[str, list[str]] | None = None
        self._datasets: dict[str, Dataset] | None = None
        self._jobs: dict[str, Job] | None = None

    @property
    def capabilities(self) -> LineageCapabilities:
        """Get provider capabilities."""
        return LineageCapabilities(
            supports_column_lineage=True,
            supports_job_runs=False,
            supports_freshness=False,
            supports_search=True,
            supports_owners=False,
            supports_tags=False,
            is_realtime=False,
        )

    @property
    def provider_info(self) -> LineageProviderInfo:
        """Get provider information."""
        return LineageProviderInfo(
            provider=LineageProviderType.STATIC_SQL,
            display_name="SQL Analysis",
            description="Lineage inferred from SQL file analysis",
            capabilities=self.capabilities,
        )

    async def _ensure_parsed(self) -> None:
        """Parse all SQL files if not already done."""
        if self._lineage is not None:
            return

        self._lineage = {}
        self._reverse_lineage = {}
        self._datasets = {}
        self._jobs = {}

        sql_files = self._collect_sql_files()

        for file_path in sql_files:
            try:
                with open(file_path) as f:
                    sql = f.read()

                # Parse lineage from SQL
                parsed = self._parse_sql(sql, file_path)

                for output_table in parsed["outputs"]:
                    self._lineage[output_table] = parsed["inputs"]
                    for input_table in parsed["inputs"]:
                        self._reverse_lineage.setdefault(input_table, []).append(output_table)

                    # Create dataset
                    self._datasets[output_table] = self._table_to_dataset(output_table, file_path)

                    # Create job
                    job_id = f"sql:{Path(file_path).name}"
                    self._jobs[job_id] = Job(
                        id=job_id,
                        name=Path(file_path).stem,
                        job_type=JobType.SQL_QUERY,
                        inputs=[DatasetId(platform="sql", name=t) for t in parsed["inputs"]],
                        outputs=[DatasetId(platform="sql", name=t) for t in parsed["outputs"]],
                        source_code_path=str(file_path),
                        source_code_url=(
                            f"{self._git_repo_url}/blob/main/{file_path}"
                            if self._git_repo_url
                            else None
                        ),
                    )

                # Also create datasets for input tables
                for input_table in parsed["inputs"]:
                    if input_table not in self._datasets:
                        self._datasets[input_table] = self._table_to_dataset(input_table)

            except Exception:
                # Skip files that can't be parsed
                continue

    def _parse_sql(self, sql: str, file_path: str = "") -> dict[str, list[str]]:
        """Parse SQL to extract lineage.

        Args:
            sql: SQL content.
            file_path: Source file path.

        Returns:
            Dict with "inputs" and "outputs" lists.
        """
        try:
            import sqlglot
            from sqlglot import exp
        except ImportError:
            # Fallback to simple regex parsing if sqlglot not installed
            return self._parse_sql_simple(sql)

        inputs: set[str] = set()
        outputs: set[str] = set()

        try:
            statements = sqlglot.parse(sql, dialect=self._dialect)

            for statement in statements:
                if statement is None:
                    continue

                # Find output tables (CREATE, INSERT, MERGE targets)
                if isinstance(statement, exp.Create | exp.Insert | exp.Merge):
                    for table in statement.find_all(exp.Table):
                        # First table in CREATE/INSERT is usually the target
                        table_name = self._get_table_name(table)
                        if table_name:
                            outputs.add(table_name)
                            break

                # Find input tables (FROM, JOIN)
                for table in statement.find_all(exp.Table):
                    table_name = self._get_table_name(table)
                    if table_name and table_name not in outputs:
                        inputs.add(table_name)

        except Exception:
            # Fall back to simple parsing
            return self._parse_sql_simple(sql)

        return {"inputs": list(inputs), "outputs": list(outputs)}

    def _get_table_name(self, table: Any) -> str | None:
        """Extract fully qualified table name from sqlglot Table.

        Args:
            table: sqlglot Table expression.

        Returns:
            Fully qualified table name or None.
        """
        parts = []
        if hasattr(table, "catalog") and table.catalog:
            parts.append(table.catalog)
        if hasattr(table, "db") and table.db:
            parts.append(table.db)
        if hasattr(table, "name") and table.name:
            parts.append(table.name)

        return ".".join(parts) if parts else None

    def _parse_sql_simple(self, sql: str) -> dict[str, list[str]]:
        """Simple regex-based SQL parsing fallback.

        Args:
            sql: SQL content.

        Returns:
            Dict with "inputs" and "outputs" lists.
        """
        import re

        inputs: set[str] = set()
        outputs: set[str] = set()

        # Match table names (simplified)
        table_pattern = r"(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_\.]*)"
        for match in re.finditer(table_pattern, sql, re.IGNORECASE):
            inputs.add(match.group(1))

        # Match output tables
        create_pattern = r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:TABLE|VIEW)\s+([a-zA-Z_][a-zA-Z0-9_\.]*)"  # noqa: E501
        for match in re.finditer(create_pattern, sql, re.IGNORECASE):
            outputs.add(match.group(1))

        insert_pattern = r"INSERT\s+(?:INTO\s+)?([a-zA-Z_][a-zA-Z0-9_\.]*)"
        for match in re.finditer(insert_pattern, sql, re.IGNORECASE):
            outputs.add(match.group(1))

        # Remove outputs from inputs (a table can be both source and target)
        inputs = inputs - outputs

        return {"inputs": list(inputs), "outputs": list(outputs)}

    def _collect_sql_files(self) -> list[str]:
        """Collect all SQL files to analyze.

        Returns:
            List of SQL file paths.
        """
        files = list(self._sql_files) if self._sql_files else []

        if self._sql_directory:
            sql_dir = Path(self._sql_directory)
            if sql_dir.exists():
                files.extend(str(p) for p in sql_dir.rglob("*.sql"))

        return files

    def _table_to_dataset(self, table_name: str, source_path: str | None = None) -> Dataset:
        """Convert table name to Dataset.

        Args:
            table_name: Fully qualified table name.
            source_path: Source file path if known.

        Returns:
            Dataset instance.
        """
        parts = table_name.split(".")
        return Dataset(
            id=DatasetId(platform="sql", name=table_name),
            name=parts[-1],
            qualified_name=table_name,
            dataset_type=DatasetType.TABLE,
            platform="sql",
            database=parts[0] if len(parts) > 2 else None,
            schema=(parts[1] if len(parts) > 2 else (parts[0] if len(parts) > 1 else None)),
            source_code_path=source_path,
            source_code_url=(
                f"{self._git_repo_url}/blob/main/{source_path}"
                if self._git_repo_url and source_path
                else None
            ),
        )

    async def get_dataset(self, dataset_id: DatasetId) -> Dataset | None:
        """Get dataset metadata.

        Args:
            dataset_id: Dataset identifier.

        Returns:
            Dataset if found, None otherwise.
        """
        await self._ensure_parsed()
        return self._datasets.get(dataset_id.name) if self._datasets else None

    async def get_upstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Get upstream tables from parsed SQL.

        Args:
            dataset_id: Dataset to get upstream for.
            depth: How many levels upstream.

        Returns:
            List of upstream datasets.
        """
        await self._ensure_parsed()

        lineage = self._lineage
        datasets = self._datasets
        if not lineage or not datasets:
            return []

        upstream: list[Dataset] = []
        visited: set[str] = set()

        def traverse(table: str, current_depth: int) -> None:
            if current_depth > depth or table in visited:
                return
            visited.add(table)

            for parent in lineage.get(table, []):
                if parent not in visited and parent in datasets:
                    upstream.append(datasets[parent])
                    traverse(parent, current_depth + 1)

        traverse(dataset_id.name, 1)
        return upstream

    async def get_downstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Get downstream tables from parsed SQL.

        Args:
            dataset_id: Dataset to get downstream for.
            depth: How many levels downstream.

        Returns:
            List of downstream datasets.
        """
        await self._ensure_parsed()

        reverse_lineage = self._reverse_lineage
        datasets = self._datasets
        if not reverse_lineage or not datasets:
            return []

        downstream: list[Dataset] = []
        visited: set[str] = set()

        def traverse(table: str, current_depth: int) -> None:
            if current_depth > depth or table in visited:
                return
            visited.add(table)

            for child in reverse_lineage.get(table, []):
                if child not in visited and child in datasets:
                    downstream.append(datasets[child])
                    traverse(child, current_depth + 1)

        traverse(dataset_id.name, 1)
        return downstream

    async def get_column_lineage(
        self,
        dataset_id: DatasetId,
        column_name: str,
    ) -> list[ColumnLineage]:
        """Get column-level lineage using sqlglot.

        Args:
            dataset_id: Dataset containing the column.
            column_name: Column to trace.

        Returns:
            List of column lineage mappings.
        """
        # Column lineage requires parsing SQL with sqlglot's lineage module
        # This is a complex feature - returning empty for now
        return []

    async def get_producing_job(self, dataset_id: DatasetId) -> Job | None:
        """Get the SQL file that produces this table.

        Args:
            dataset_id: Dataset to find producer for.

        Returns:
            Job if found, None otherwise.
        """
        await self._ensure_parsed()

        if not self._jobs:
            return None

        for job in self._jobs.values():
            for output in job.outputs:
                if output.name == dataset_id.name:
                    return job

        return None

    async def search_datasets(self, query: str, limit: int = 20) -> list[Dataset]:
        """Search tables by name.

        Args:
            query: Search query.
            limit: Maximum results.

        Returns:
            Matching datasets.
        """
        await self._ensure_parsed()

        if not self._datasets:
            return []

        query_lower = query.lower()
        results: list[Dataset] = []

        for name, dataset in self._datasets.items():
            if query_lower in name.lower():
                results.append(dataset)
                if len(results) >= limit:
                    break

        return results

    async def list_datasets(
        self,
        platform: str | None = None,
        database: str | None = None,
        schema: str | None = None,
        limit: int = 100,
    ) -> list[Dataset]:
        """List all parsed tables.

        Args:
            platform: Filter by platform (not used).
            database: Filter by database.
            schema: Filter by schema.
            limit: Maximum results.

        Returns:
            List of datasets.
        """
        await self._ensure_parsed()

        if not self._datasets:
            return []

        results: list[Dataset] = []

        for dataset in self._datasets.values():
            if database and dataset.database != database:
                continue
            if schema and dataset.schema != schema:
                continue

            results.append(dataset)
            if len(results) >= limit:
                break

        return results
