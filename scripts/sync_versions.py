#!/usr/bin/env python3
"""Sync version across all pyproject.toml files in the monorepo.

Usage:
    python scripts/sync_versions.py <version>   # Set version in all packages
    python scripts/sync_versions.py --check     # Verify all versions match

Examples:
    python scripts/sync_versions.py 0.2.0
    python scripts/sync_versions.py --check
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

PACKAGES = [
    REPO_ROOT / "python-packages/dataing/pyproject.toml",
    REPO_ROOT / "python-packages/dataing-ee/pyproject.toml",
    REPO_ROOT / "python-packages/dataing-cli/pyproject.toml",
    REPO_ROOT / "python-packages/dataing-sdk/pyproject.toml",
    REPO_ROOT / "python-packages/dataing-notebook/pyproject.toml",
    REPO_ROOT / "pyproject.toml",
]

VERSION_PATTERN = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)


def get_version(pyproject_path: Path) -> str | None:
    """Extract version from a pyproject.toml file."""
    if not pyproject_path.exists():
        return None
    content = pyproject_path.read_text()
    match = VERSION_PATTERN.search(content)
    return match.group(1) if match else None


def set_version(pyproject_path: Path, version: str) -> bool:
    """Set version in a pyproject.toml file."""
    if not pyproject_path.exists():
        print(f"  SKIP: {pyproject_path.relative_to(REPO_ROOT)} (not found)")
        return False

    content = pyproject_path.read_text()
    new_content, count = VERSION_PATTERN.subn(f'version = "{version}"', content, count=1)

    if count == 0:
        print(f"  WARN: {pyproject_path.relative_to(REPO_ROOT)} (no version field found)")
        return False

    pyproject_path.write_text(new_content)
    print(f"  SET:  {pyproject_path.relative_to(REPO_ROOT)} -> {version}")
    return True


def sync(version: str) -> int:
    """Set version in all pyproject.toml files."""
    print(f"Syncing version to {version}...")
    success_count = 0
    for pkg in PACKAGES:
        if set_version(pkg, version):
            success_count += 1
    print(f"\nUpdated {success_count}/{len(PACKAGES)} packages.")
    return 0 if success_count == len(PACKAGES) else 1


def check() -> int:
    """Verify all versions match. Returns 0 if all match, 1 otherwise."""
    print("Checking version consistency...")
    versions: dict[str, str] = {}

    for pkg in PACKAGES:
        version = get_version(pkg)
        rel_path = str(pkg.relative_to(REPO_ROOT))
        if version:
            versions[rel_path] = version
            print(f"  {rel_path}: {version}")
        else:
            print(f"  {rel_path}: NOT FOUND")
            versions[rel_path] = "NOT_FOUND"

    unique_versions = set(v for v in versions.values() if v != "NOT_FOUND")

    if len(unique_versions) == 1:
        print(f"\nAll packages are at version {unique_versions.pop()}")
        return 0
    else:
        print(f"\nVersion mismatch detected: {unique_versions}")
        return 1


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    arg = sys.argv[1]

    if arg == "--check":
        return check()
    elif arg.startswith("-"):
        print(f"Unknown option: {arg}")
        print(__doc__)
        return 1
    else:
        # Validate version format (basic semver check)
        if not re.match(r"^\d+\.\d+\.\d+", arg):
            print(f"Invalid version format: {arg}")
            print("Expected semver format: MAJOR.MINOR.PATCH (e.g., 0.1.0)")
            return 1
        return sync(arg)


if __name__ == "__main__":
    sys.exit(main())
