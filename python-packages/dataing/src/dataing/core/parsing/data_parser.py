"""Data file parser for CSV and Parquet sampling.

Provides utilities for reading samples from data files
without loading entire datasets into memory.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SampleResult:
    """Result of sampling a data file.

    Attributes:
        columns: List of column names.
        rows: Sample rows as list of dicts.
        total_rows: Total row count (if known).
        file_size: File size in bytes.
        format: Detected file format.
        schema: Column types if available.
        truncated: Whether sample was truncated.
    """

    columns: list[str]
    rows: list[dict[str, Any]]
    total_rows: int | None
    file_size: int
    format: str
    schema: dict[str, str] = field(default_factory=dict)
    truncated: bool = False


class DataParser:
    """Parser for data files (CSV, Parquet).

    Provides efficient sampling of data files without
    loading entire datasets into memory.
    """

    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
    DEFAULT_SAMPLE_ROWS = 100
    MAX_SAMPLE_ROWS = 1000

    def __init__(
        self,
        max_file_size: int = MAX_FILE_SIZE,
        default_sample_rows: int = DEFAULT_SAMPLE_ROWS,
    ) -> None:
        """Initialize the data parser.

        Args:
            max_file_size: Maximum file size in bytes.
            default_sample_rows: Default number of rows to sample.
        """
        self.max_file_size = max_file_size
        self.default_sample_rows = default_sample_rows

    def sample_file(
        self,
        path: Path | str,
        n_rows: int | None = None,
        columns: list[str] | None = None,
    ) -> SampleResult:
        """Sample rows from a data file.

        Automatically detects file format and uses appropriate parser.

        Args:
            path: Path to the data file.
            n_rows: Number of rows to sample (default: default_sample_rows).
            columns: Specific columns to include (default: all).

        Returns:
            SampleResult with sample data and metadata.

        Raises:
            FileNotFoundError: If file doesn't exist.
            ValueError: If file exceeds size limit or format unsupported.
        """
        path = Path(path)
        n_rows = min(n_rows or self.default_sample_rows, self.MAX_SAMPLE_ROWS)

        # Check file size
        file_size = path.stat().st_size
        if file_size > self.max_file_size:
            raise ValueError(
                f"Data file exceeds size limit: {file_size:,} > {self.max_file_size:,} bytes"
            )

        # Detect format and parse
        suffix = path.suffix.lower()
        if suffix == ".csv":
            return self._sample_csv(path, n_rows, columns, file_size)
        elif suffix == ".tsv":
            return self._sample_csv(path, n_rows, columns, file_size, delimiter="\t")
        elif suffix == ".parquet":
            return self._sample_parquet(path, n_rows, columns, file_size)
        else:
            raise ValueError(f"Unsupported data file format: {suffix}")

    def get_schema(self, path: Path | str) -> dict[str, str]:
        """Get column schema from a data file.

        Args:
            path: Path to the data file.

        Returns:
            Dict mapping column names to type descriptions.
        """
        path = Path(path)
        suffix = path.suffix.lower()

        if suffix in (".csv", ".tsv"):
            return self._get_csv_schema(path, delimiter="\t" if suffix == ".tsv" else ",")
        elif suffix == ".parquet":
            return self._get_parquet_schema(path)
        else:
            raise ValueError(f"Unsupported data file format: {suffix}")

    def count_rows(self, path: Path | str) -> int:
        """Count rows in a data file.

        Args:
            path: Path to the data file.

        Returns:
            Number of rows.
        """
        path = Path(path)
        suffix = path.suffix.lower()

        if suffix in (".csv", ".tsv"):
            return self._count_csv_rows(path)
        elif suffix == ".parquet":
            return self._count_parquet_rows(path)
        else:
            raise ValueError(f"Unsupported data file format: {suffix}")

    def _sample_csv(
        self,
        path: Path,
        n_rows: int,
        columns: list[str] | None,
        file_size: int,
        delimiter: str = ",",
    ) -> SampleResult:
        """Sample rows from a CSV file.

        Args:
            path: Path to the CSV file.
            n_rows: Number of rows to sample.
            columns: Columns to include.
            file_size: File size in bytes.
            delimiter: CSV delimiter.

        Returns:
            SampleResult.
        """
        rows: list[dict[str, Any]] = []
        all_columns: list[str] = []
        total_rows = 0

        with path.open(encoding="utf-8", errors="replace") as f:
            # Detect dialect
            sample = f.read(8192)
            f.seek(0)

            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=delimiter + ",;|")
            except csv.Error:
                dialect = csv.excel
                dialect.delimiter = delimiter

            reader = csv.DictReader(f, dialect=dialect)

            if reader.fieldnames:
                all_columns = list(reader.fieldnames)

            for row in reader:
                total_rows += 1
                if len(rows) < n_rows:
                    if columns:
                        row = {k: v for k, v in row.items() if k in columns}
                    rows.append(row)

        # Infer schema from sample
        schema = self._infer_csv_schema(rows, all_columns)

        return SampleResult(
            columns=columns if columns else all_columns,
            rows=rows,
            total_rows=total_rows,
            file_size=file_size,
            format="csv",
            schema=schema,
            truncated=total_rows > n_rows,
        )

    def _sample_parquet(
        self,
        path: Path,
        n_rows: int,
        columns: list[str] | None,
        file_size: int,
    ) -> SampleResult:
        """Sample rows from a Parquet file.

        Args:
            path: Path to the Parquet file.
            n_rows: Number of rows to sample.
            columns: Columns to include.
            file_size: File size in bytes.

        Returns:
            SampleResult.
        """
        try:
            import pyarrow.parquet as pq
        except ImportError as err:
            raise ImportError(
                "pyarrow is required for Parquet support. Install with: pip install pyarrow"
            ) from err

        # Read metadata first
        parquet_file = pq.ParquetFile(path)
        total_rows = parquet_file.metadata.num_rows
        all_columns = parquet_file.schema.names

        # Read sample
        table = parquet_file.read_row_groups(
            [0] if parquet_file.metadata.num_row_groups > 0 else [],
            columns=columns,
        )

        # Convert to dicts
        df = table.to_pandas()
        if len(df) > n_rows:
            df = df.head(n_rows)

        rows: list[dict[str, Any]] = df.to_dict(orient="records")

        # Get schema
        schema = {}
        for pq_field in parquet_file.schema:
            schema[pq_field.name] = str(pq_field.physical_type)

        return SampleResult(
            columns=columns if columns else all_columns,
            rows=rows,
            total_rows=total_rows,
            file_size=file_size,
            format="parquet",
            schema=schema,
            truncated=total_rows > n_rows,
        )

    def _get_csv_schema(self, path: Path, delimiter: str = ",") -> dict[str, str]:
        """Infer schema from CSV by sampling.

        Args:
            path: Path to CSV file.
            delimiter: CSV delimiter.

        Returns:
            Column type mapping.
        """
        sample = self._sample_csv(path, 100, None, 0, delimiter)
        return sample.schema

    def _get_parquet_schema(self, path: Path) -> dict[str, str]:
        """Get schema from Parquet file.

        Args:
            path: Path to Parquet file.

        Returns:
            Column type mapping.
        """
        try:
            import pyarrow.parquet as pq
        except ImportError as err:
            raise ImportError(
                "pyarrow is required for Parquet support. Install with: pip install pyarrow"
            ) from err

        parquet_file = pq.ParquetFile(path)
        schema = {}
        for pq_field in parquet_file.schema:
            schema[pq_field.name] = str(pq_field.physical_type)
        return schema

    def _count_csv_rows(self, path: Path) -> int:
        """Count rows in a CSV file.

        Args:
            path: Path to CSV file.

        Returns:
            Row count.
        """
        count = 0
        with path.open(encoding="utf-8", errors="replace") as f:
            # Skip header
            next(f, None)
            for _ in f:
                count += 1
        return count

    def _count_parquet_rows(self, path: Path) -> int:
        """Count rows in a Parquet file.

        Args:
            path: Path to Parquet file.

        Returns:
            Row count.
        """
        try:
            import pyarrow.parquet as pq
        except ImportError as err:
            raise ImportError(
                "pyarrow is required for Parquet support. Install with: pip install pyarrow"
            ) from err

        parquet_file = pq.ParquetFile(path)
        num_rows: int = parquet_file.metadata.num_rows
        return num_rows

    def _infer_csv_schema(self, rows: list[dict[str, Any]], columns: list[str]) -> dict[str, str]:
        """Infer column types from sample rows.

        Args:
            rows: Sample rows.
            columns: Column names.

        Returns:
            Column type mapping.
        """
        schema = {}

        for col in columns:
            values = [row.get(col) for row in rows if row.get(col)]

            if not values:
                schema[col] = "unknown"
                continue

            # Try to infer type from values
            col_type = self._infer_value_type(values)
            schema[col] = col_type

        return schema

    def _infer_value_type(self, values: list[Any]) -> str:
        """Infer type from a list of values.

        Args:
            values: Sample values.

        Returns:
            Type name.
        """
        # Sample up to 20 non-null values
        sample = [v for v in values[:20] if v is not None and v != ""]

        if not sample:
            return "unknown"

        # Check for common types
        int_count = 0
        float_count = 0
        bool_count = 0
        date_count = 0

        for v in sample:
            v_str = str(v).strip()

            # Check boolean
            if v_str.lower() in ("true", "false", "yes", "no", "1", "0"):
                bool_count += 1
                continue

            # Check integer
            try:
                int(v_str)
                int_count += 1
                continue
            except ValueError:
                pass

            # Check float
            try:
                float(v_str)
                float_count += 1
                continue
            except ValueError:
                pass

            # Check date-like
            if self._looks_like_date(v_str):
                date_count += 1
                continue

        total = len(sample)
        threshold = 0.8  # 80% must match type

        if int_count / total >= threshold:
            return "integer"
        elif float_count / total >= threshold:
            return "float"
        elif bool_count / total >= threshold:
            return "boolean"
        elif date_count / total >= threshold:
            return "datetime"
        else:
            return "string"

    def _looks_like_date(self, value: str) -> bool:
        """Check if a value looks like a date.

        Args:
            value: String value.

        Returns:
            True if date-like.
        """
        import re

        date_patterns = [
            r"^\d{4}-\d{2}-\d{2}",  # ISO date
            r"^\d{2}/\d{2}/\d{4}",  # US date
            r"^\d{2}-\d{2}-\d{4}",  # EU date
        ]

        for pattern in date_patterns:
            if re.match(pattern, value):
                return True

        return False

    def format_sample_as_markdown(self, result: SampleResult, max_rows: int = 10) -> str:
        """Format sample result as markdown table.

        Args:
            result: SampleResult to format.
            max_rows: Maximum rows to include.

        Returns:
            Markdown string.
        """
        if not result.rows:
            return "*No data*"

        rows_to_show = result.rows[:max_rows]
        columns = result.columns

        # Build table
        lines = []

        # Header
        lines.append("| " + " | ".join(columns) + " |")
        lines.append("| " + " | ".join(["---"] * len(columns)) + " |")

        # Rows
        for row in rows_to_show:
            cells = []
            for col in columns:
                value = row.get(col, "")
                # Truncate long values
                value_str = str(value)
                if len(value_str) > 50:
                    value_str = value_str[:47] + "..."
                # Escape pipes
                value_str = value_str.replace("|", "\\|")
                cells.append(value_str)
            lines.append("| " + " | ".join(cells) + " |")

        if len(result.rows) > max_rows:
            lines.append(f"\n*... and {len(result.rows) - max_rows} more rows*")

        if result.truncated:
            lines.append(f"\n*Total rows in file: {result.total_rows:,}*")

        return "\n".join(lines)
