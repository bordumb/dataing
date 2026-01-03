#!/usr/bin/env python3
"""
Print a recursive file tree for selected top-level directories.

Usage:
    python scripts/make_file_tree.py

All configuration is done at the top of this file.
"""

from pathlib import Path
from typing import Iterable

# ─────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────

# Root of the repository
ROOT_DIR = Path(".")

# Only directories (or paths) starting with one of these prefixes
# will be scanned. Comment out entries to disable them.
SEARCH_PREFIXES = [
    "backend",
]

# Include hidden files / directories (starting with ".")
INCLUDE_HIDDEN = False

# Maximum recursion depth (None = unlimited)
MAX_DEPTH = None

# Sort entries alphabetically
SORT_ENTRIES = True

# ─────────────────────────────────────────────────────────────
# IMPLEMENTATION
# ─────────────────────────────────────────────────────────────


def should_include(path: Path) -> bool:
    if not INCLUDE_HIDDEN and path.name.startswith("."):
        return False
    return True


def iter_roots(root: Path, prefixes: Iterable[str]) -> list[Path]:
    resolved = []
    for prefix in prefixes:
        p = (root / prefix).resolve()
        if p.exists():
            resolved.append(p)
    return resolved


def print_tree(root: Path, prefix: str = "", depth: int = 0) -> None:
    if MAX_DEPTH is not None and depth > MAX_DEPTH:
        return

    try:
        entries = [p for p in root.iterdir() if should_include(p)]
    except PermissionError:
        print(f"{prefix}└── [permission denied]")
        return

    if SORT_ENTRIES:
        entries.sort(key=lambda p: (p.is_file(), p.name.lower()))

    for i, entry in enumerate(entries):
        is_last = i == len(entries) - 1
        connector = "└── " if is_last else "├── "
        print(f"{prefix}{connector}{entry.name}")

        if entry.is_dir():
            extension = "    " if is_last else "│   "
            print_tree(entry, prefix + extension, depth + 1)


def main() -> None:
    root = ROOT_DIR.resolve()
    print(root)

    roots = iter_roots(root, SEARCH_PREFIXES)

    for i, subroot in enumerate(roots):
        is_last = i == len(roots) - 1
        connector = "└── " if is_last else "├── "
        print(f"{connector}{subroot.name}")
        extension = "    " if is_last else "│   "
        print_tree(subroot, prefix=extension, depth=1)


if __name__ == "__main__":
    main()
