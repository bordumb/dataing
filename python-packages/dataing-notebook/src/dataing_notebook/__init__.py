"""Dataing notebook extension with IPython magics.

This module provides IPython magic commands for data quality investigation
in Jupyter notebooks.

Usage:
    %load_ext dataing_notebook

    # Attach context by URN
    %dataing attach postgres://db.schema.orders

    # Attach context from SQL (requires --datasource or default)
    %dataing attach "SELECT * FROM orders" --datasource ds-123

    # Display lineage
    %dataing lineage

    # Start an investigation
    %dataing ask "Why are there null values in the orders table?"
"""

from .magic import DataingMagics, load_ipython_extension, unload_ipython_extension
from .state import NotebookState

__version__ = "0.1.0"

__all__ = [
    "DataingMagics",
    "NotebookState",
    "load_ipython_extension",
    "unload_ipython_extension",
]
