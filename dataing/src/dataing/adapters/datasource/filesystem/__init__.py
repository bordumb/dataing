"""File system adapters.

This module provides adapters for file system data sources:
- S3
- GCS
- HDFS
- Local files
"""

from dataing.adapters.datasource.filesystem.base import FileSystemAdapter

__all__ = ["FileSystemAdapter"]
