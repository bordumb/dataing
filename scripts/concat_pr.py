#!/usr/bin/env python3
"""Generate a concatenated file of all changes in the current PR.

Uses git to detect files changed between the current branch and main.

Run:
    python scripts/concat_pr.py
    python scripts/concat_pr.py --base origin/main
    python scripts/concat_pr.py --base develop
"""

import argparse
import subprocess
from pathlib import Path

# ─────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────

ROOT_DIR = Path(".")

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
    ".toml",
    ".ipynb",
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

OUTPUT_FILE = "pr_changes.txt"

BANNER_CHAR = "─"
BANNER_WIDTH = 160
JOIN_WITH = "\n\n" + BANNER_CHAR * BANNER_WIDTH + "\n"

# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────


def is_excluded_path(path: Path) -> bool:
    """Check if path contains any excluded directory."""
    return any(part in EXCLUDE for part in path.parts)


def should_include_file(path: Path) -> bool:
    """Check if file should be included based on extension."""
    return path.is_file() and path.suffix in INCLUDE_EXTS


def banner(title: str) -> str:
    """Create a banner string for a file."""
    pad = max(BANNER_WIDTH - len(title) - 2, 0)
    left = pad // 2
    right = pad - left
    return f"{BANNER_CHAR * left} {title} {BANNER_CHAR * right}\n"


def read_file(path: Path) -> str:
    """Read file contents safely."""
    try:
        return path.read_text(encoding=ENCODING)
    except Exception as e:
        return f"[ERROR READING FILE: {e}]"


def get_changed_files(base_branch: str = "origin/main") -> list[str]:
    """Get list of files changed between base branch and HEAD.

    Args:
        base_branch: The base branch to compare against.

    Returns:
        List of changed file paths.
    """
    try:
        # Get files changed between base and HEAD
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base_branch}...HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        files = result.stdout.strip().split("\n")
        return [f for f in files if f]  # Filter empty strings
    except subprocess.CalledProcessError:
        # Fallback: try without the triple dot (for when base doesn't exist)
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", base_branch, "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )
            files = result.stdout.strip().split("\n")
            return [f for f in files if f]
        except subprocess.CalledProcessError as e:
            print(f"Error getting changed files: {e}")
            return []


def get_current_branch() -> str:
    """Get the current git branch name."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return "unknown"


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Concatenate files changed in current PR"
    )
    parser.add_argument(
        "--base",
        default="origin/main",
        help="Base branch to compare against (default: origin/main)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=OUTPUT_FILE,
        help=f"Output file path (default: {OUTPUT_FILE})",
    )
    args = parser.parse_args()

    root = ROOT_DIR.resolve()
    current_branch = get_current_branch()

    print(f"Current branch: {current_branch}")
    print(f"Comparing against: {args.base}")
    print()

    # Get changed files from git
    changed_files = get_changed_files(args.base)

    if not changed_files:
        print("No changed files found.")
        return

    print(f"Found {len(changed_files)} changed files:")

    # Filter and collect files
    output: list[str] = []
    included_files: list[Path] = []

    for file_str in changed_files:
        path = root / file_str

        # Skip excluded paths
        if is_excluded_path(path):
            print(f"  [excluded] {file_str}")
            continue

        # Skip files that don't exist (deleted files)
        if not path.exists():
            print(f"  [deleted]  {file_str}")
            continue

        # Skip files with unsupported extensions
        if not should_include_file(path):
            print(f"  [skipped]  {file_str}")
            continue

        print(f"  [included] {file_str}")
        included_files.append(path)

    print()

    # Build output
    for path in sorted(included_files):
        rel_path = path.relative_to(root)
        output.append(banner(str(rel_path)))
        output.append(read_file(path))

    # Write output
    out_path = root / args.output
    out_path.write_text(JOIN_WITH.join(output), encoding=ENCODING)

    print(f"✓ Wrote {len(included_files)} files to {out_path}")


if __name__ == "__main__":
    main()
