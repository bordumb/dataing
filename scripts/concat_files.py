#!/usr/bin/env python3
"""
Generate a high-signal file tree and concatenate selected source/config files.

Run:
    python scripts/make_file_tree.py
"""

from pathlib import Path
from typing import Iterable

# ─────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────

ROOT_DIR = Path(".")

SEARCH_PREFIXES = [
    "backend",
    # "frontend",
    # "ee",
    # "docs",
    # "docs/feedback",
]

INCLUDE_ROOT_FILES = [
    # "Dockerfile",
    # "docker-compose.yml",
    # "Makefile",
    # "pyproject.toml",
    # ".env.example",
    # "README.md",
]

INCLUDE_EXTS = {
    ".py",
    ".yaml",
    ".yml",
    ".json",
    ".md",
    ".txt",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".css",
    ".html",
}

EXCLUDE = {
    ".git",
    "__pycache__",
    ".ruff_cache",
    ".pytest_cache",
    ".mypy_cache",
    ".egg-info",
    ".venv",
    "dist",
    "build",
    "out",
    "htmlcov",
    "coverage",
    "node_modules",
    ".next",
    ".nuxt",
    ".svelte-kit",
    ".angular",
    ".parcel-cache",
    ".turbo",
    ".vite",
    ".cache",
    "storybook-static",
    "site",
    "output",
}

ENCODING = "utf-8"

OUTPUT_FILE = "all_code_and_configs.txt"

BANNER_CHAR = "─"
BANNER_WIDTH = 160
JOIN_WITH = "\n\n" + BANNER_CHAR * BANNER_WIDTH + "\n"

# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────


def is_excluded_path(path: Path) -> bool:
    return any(part in EXCLUDE for part in path.parts)


def should_include_file(path: Path) -> bool:
    return path.is_file() and path.suffix in INCLUDE_EXTS


def iter_roots(root: Path, prefixes: Iterable[str]) -> list[Path]:
    roots = []
    for prefix in prefixes:
        p = (root / prefix).resolve()
        if p.exists() and p.is_dir() and not is_excluded_path(p):
            roots.append(p)
    return roots


def banner(title: str) -> str:
    pad = max(BANNER_WIDTH - len(title) - 2, 0)
    left = pad // 2
    right = pad - left
    return f"{BANNER_CHAR * left} {title} {BANNER_CHAR * right}\n"


def read_file(path: Path) -> str:
    try:
        return path.read_text(encoding=ENCODING)
    except Exception as e:
        return f"[ERROR READING FILE: {e}]"


# ─────────────────────────────────────────────────────────────
# TREE + FILE COLLECTION
# ─────────────────────────────────────────────────────────────


def print_tree(root: Path, prefix: str = "") -> None:
    try:
        entries = [
            p
            for p in root.iterdir()
            if not is_excluded_path(p) and (p.is_dir() or should_include_file(p))
        ]
    except PermissionError:
        return

    entries.sort(key=lambda p: (p.is_file(), p.name.lower()))

    for i, entry in enumerate(entries):
        is_last = i == len(entries) - 1
        connector = "└── " if is_last else "├── "
        print(f"{prefix}{connector}{entry.name}")

        if entry.is_dir():
            extension = "    " if is_last else "│   "
            print_tree(entry, prefix + extension)


def collect_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if is_excluded_path(path):
            continue
        if should_include_file(path):
            files.append(path)
    return sorted(files)


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────


def main() -> None:
    root = ROOT_DIR.resolve()

    # Print tree
    print(root)
    roots = iter_roots(root, SEARCH_PREFIXES)
    for i, subroot in enumerate(roots):
        is_last = i == len(roots) - 1
        connector = "└── " if is_last else "├── "
        print(f"{connector}{subroot.name}")
        extension = "    " if is_last else "│   "
        print_tree(subroot, prefix=extension)

    # Collect contents
    output: list[str] = []

    for filename in INCLUDE_ROOT_FILES:
        path = root / filename
        if path.exists() and should_include_file(path):
            output.append(banner(str(path.relative_to(root))))
            output.append(read_file(path))

    for subroot in roots:
        for file in collect_files(subroot):
            output.append(banner(str(file.relative_to(root))))
            output.append(read_file(file))

    out_path = root / OUTPUT_FILE
    out_path.write_text(JOIN_WITH.join(output), encoding=ENCODING)

    print(f"\n✓ Wrote {len(output) // 2} files to {out_path}")


if __name__ == "__main__":
    main()
