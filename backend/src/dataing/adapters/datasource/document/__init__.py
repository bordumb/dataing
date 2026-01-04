"""Document/NoSQL database adapters.

This module provides adapters for document-oriented data sources:
- MongoDB
- DynamoDB
- Cassandra
"""

from dataing.adapters.datasource.document.base import DocumentAdapter

__all__ = ["DocumentAdapter"]
