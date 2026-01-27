"""Dataset-to-repository mapping resolution algorithm.

Pure functions for matching datasets to their source code repositories.
No database access — callers fetch candidate mappings and pass them in.
"""

from __future__ import annotations

from datetime import datetime
from fnmatch import fnmatch
from typing import Any


def normalize_dataset_id(dataset_id: str) -> list[str]:
    """Normalize a dataset identifier into matchable forms.

    Returns a list of normalized forms to match against patterns.
    For "db.schema.table" returns both the full form and "schema.table".
    For "schema.table" returns just that form.
    """
    normalized = dataset_id.lower().strip()
    parts = normalized.split(".")

    if len(parts) >= 3:
        # database.schema.table -> try both full and schema.table
        schema_table = ".".join(parts[-2:])
        return [normalized, schema_table]
    return [normalized]


def match_pattern(pattern: str, pattern_type: str, dataset_id: str) -> bool:
    """Check if a dataset identifier matches a mapping pattern.

    Supports exact and glob (fnmatch) pattern types.
    Matches against all normalized forms of the dataset identifier.
    """
    forms = normalize_dataset_id(dataset_id)
    pattern_lower = pattern.lower().strip()

    if pattern_type == "exact":
        return any(form == pattern_lower for form in forms)
    elif pattern_type == "glob":
        return any(fnmatch(form, pattern_lower) for form in forms)
    return False


def resolve_file_path(template: str | None, dataset_id: str) -> str | None:
    """Resolve a file path template by substituting dataset components.

    Replaces {table}, {schema}, and {database} tokens with parsed
    components from the dataset identifier.
    """
    if template is None:
        return None

    if "{" not in template:
        return template

    parts = dataset_id.lower().strip().split(".")
    replacements: dict[str, str] = {}

    if len(parts) >= 3:
        replacements["database"] = parts[0]
        replacements["schema"] = parts[1]
        replacements["table"] = parts[2]
    elif len(parts) == 2:
        replacements["schema"] = parts[0]
        replacements["table"] = parts[1]
    elif len(parts) == 1:
        replacements["table"] = parts[0]

    result = template
    for token, value in replacements.items():
        result = result.replace(f"{{{token}}}", value)
    return result


def resolve_repo_mapping(mappings: list[dict[str, Any]], dataset_id: str) -> dict[str, Any] | None:
    """Find the best matching repo mapping for a dataset.

    Filters mappings by pattern match, sorts by priority (ASC),
    confidence (DESC), created_at (DESC), and returns the best match.
    Resolves file_path tokens in the result.
    """
    matches = _filter_and_sort(mappings, dataset_id)
    if not matches:
        return None

    best = dict(matches[0])
    best["file_path"] = resolve_file_path(best.get("file_path"), dataset_id)
    return best


def resolve_all_repo_mappings(
    mappings: list[dict[str, Any]], dataset_id: str
) -> list[dict[str, Any]]:
    """Find all matching repo mappings for a dataset, sorted by priority.

    Returns all matches with file_path tokens resolved.
    """
    matches = _filter_and_sort(mappings, dataset_id)
    results = []
    for m in matches:
        entry = dict(m)
        entry["file_path"] = resolve_file_path(entry.get("file_path"), dataset_id)
        results.append(entry)
    return results


def _filter_and_sort(mappings: list[dict[str, Any]], dataset_id: str) -> list[dict[str, Any]]:
    """Filter mappings by pattern match and sort by priority rules."""
    matched = [
        m for m in mappings if match_pattern(m["dataset_pattern"], m["pattern_type"], dataset_id)
    ]
    return sorted(
        matched,
        key=lambda m: (
            m.get("priority", 0),
            -m.get("confidence", 0.0),
            -_datetime_key(m.get("created_at")),
        ),
    )


def _datetime_key(dt: Any) -> float:
    """Convert a datetime to a sortable float."""
    if isinstance(dt, datetime):
        return dt.timestamp()
    return 0.0
